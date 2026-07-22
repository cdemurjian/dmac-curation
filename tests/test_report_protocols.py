"""Protocol resolution and additive NExtSEEK enrichment."""
import io
import sys
import types
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import enrich as en  # noqa: E402
from report import protocols as pr  # noqa: E402

BASE = "https://nextseek.mit.edu"


def _docx(paragraphs):
    buf = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document><w:body>{body}'
                   f"</w:body></w:document>")
    return buf.getvalue()


def _input(*metas):
    return ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid=f"D.SEQ-{i}",
                                     metadata=m, parent=None)
                 for i, m in enumerate(metas, start=1)],
        source={"adapter": "tabular"})


# ---- discovery ------------------------------------------------------------

def test_finds_refs_in_a_key_literally_named_Protocol():
    got = pr.find_protocol_refs(_input({"Protocol": "P.RNAseq-1"}))
    assert got["D.SEQ-1"] == ["P.RNAseq-1"]


def test_ignores_keys_that_merely_contain_protocol():
    assert pr.find_protocol_refs(_input({"ProtocolNotes": "x"})) == {}


def test_finds_a_sops_url():
    got = pr.find_protocol_refs(
        _input({"Protocol": "https://fairdata.mit.edu/nextseek_api/sops/42/"}))
    assert got["D.SEQ-1"]


def test_splits_semicolon_joined_refs():
    got = pr.find_protocol_refs(_input({"Protocol": "P.A-1; P.B-2"}))
    assert got["D.SEQ-1"] == ["P.A-1", "P.B-2"]


def test_skips_placeholder_markers():
    assert pr.find_protocol_refs(
        _input({"Protocol": "*** PLACEHOLDER: unknown ***"})) == {}


def test_parse_sop_id_from_a_url():
    assert pr.parse_sop_id("https://x/nextseek_api/sops/42/") == "42"
    assert pr.parse_sop_id("/sops/7") == "7"


def test_parse_sop_id_from_a_bare_p_name():
    assert pr.parse_sop_id("P.RNAseq-1") == "P.RNAseq-1"


def test_parse_sop_id_rejects_free_prose():
    assert pr.parse_sop_id("see the methods section") is None


# ---- host redirection -----------------------------------------------------

def test_fairdata_urls_are_redirected_to_the_nextseek_base():
    """The trap: fairdata.mit.edu refs are NOT fetched from that host."""
    out = pr.resolve_host("https://fairdata.mit.edu/nextseek_api/sops/42/",
                          nextseek_base_url=BASE)
    assert out == "https://nextseek.mit.edu/nextseek_api/sops/42/"


def test_fairdomhub_urls_stay_off_host():
    url = "https://fairdomhub.org/sops/9"
    assert pr.resolve_host(url, nextseek_base_url=BASE) == url


def test_fairdomhub_allowlist_matches_the_host_not_a_netloc_suffix():
    """The trap: a netloc-suffix check lets `evilfairdomhub.org` go off-host
    with the FDH_API bearer token. Match the parsed HOST instead."""
    # A spoofed lookalike is NOT fairdomhub.org -> redirected on-host.
    out = pr.resolve_host(
        "https://evilfairdomhub.org/nextseek_api/sops/9/",
        nextseek_base_url=BASE)
    assert urlparse(out).hostname == "nextseek.mit.edu"
    assert urlparse(out).hostname != "evilfairdomhub.org"
    # The genuine host and its subdomains stay off-host, unchanged.
    genuine = "https://fairdomhub.org/sops/9"
    sub = "https://sub.fairdomhub.org/sops/9"
    assert pr.resolve_host(genuine, nextseek_base_url=BASE) == genuine
    assert pr.resolve_host(sub, nextseek_base_url=BASE) == sub


def test_a_relative_ref_is_joined_onto_the_nextseek_base():
    assert pr.resolve_host("/nextseek_api/sops/42/", nextseek_base_url=BASE) == \
        "https://nextseek.mit.edu/nextseek_api/sops/42/"


def test_fairdomhub_requires_a_bearer_token_with_no_fallback():
    src = (REPO / "scripts" / "report" / "protocols.py").read_text()
    assert "FDH_API" in src
    assert "no fallback" in src.lower()


# ---- text extraction ------------------------------------------------------

def test_docx_extraction_is_stdlib_only():
    text = pr.extract_docx_text(_docx(["Step one.", "Step two."]))
    assert "Step one." in text
    assert "Step two." in text


def test_docx_extraction_strips_tags():
    assert "<w:t>" not in pr.extract_docx_text(_docx(["Hello"]))


def test_docx_extraction_on_a_non_zip_returns_empty():
    assert pr.extract_docx_text(b"not a zip") == ""


def test_pdf_extraction_fails_loudly_without_PyPDF2(monkeypatch):
    """The trap: upstream silently yields nothing when PyPDF2 is absent."""
    monkeypatch.setitem(sys.modules, "PyPDF2", None)
    with pytest.raises(pr.PdfSupportError):
        pr.extract_pdf_text(b"%PDF-1.4 whatever")


def test_truncation_reports_whether_it_truncated():
    short, was_cut = pr.truncate_tokens("a b c", limit=10)
    assert short == "a b c" and was_cut is False
    long, was_cut = pr.truncate_tokens(" ".join(["w"] * 5000), limit=10)
    assert was_cut is True
    assert len(long.split()) <= 11


def test_truncation_default_limit_matches_upstream():
    import inspect
    assert inspect.signature(pr.truncate_tokens).parameters["limit"].default == 3000


# ---- resolution -----------------------------------------------------------

def test_resolve_protocols_fetches_and_extracts():
    calls = []

    def fetch_sop(sop_id):
        calls.append(sop_id)
        return {"id": sop_id, "title": "RNA-seq SOP",
                "content_blobs": [{"url": f"{BASE}/blob/1", "content_type":
                                   "application/vnd.openxmlformats-officedocument"
                                   ".wordprocessingml.document"}]}

    def fetch_blob(url):
        return _docx(["Extract RNA with TRIzol."])

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.RNAseq-1"}),
        fetch_sop=fetch_sop, fetch_blob=fetch_blob, nextseek_base_url=BASE)
    assert calls == ["P.RNAseq-1"]
    assert "TRIzol" in resolved["P.RNAseq-1"]["text"]
    assert resolved["P.RNAseq-1"]["title"] == "RNA-seq SOP"


def test_resolve_protocols_with_no_fetcher_is_a_no_op():
    """Neither enrichment nor protocol resolution gates output."""
    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}), nextseek_base_url=BASE)
    assert resolved == {}
    assert any("not resolved" in n for n in notes)


def test_resolve_protocols_records_truncation_in_its_notes():
    def fetch_sop(sop_id):
        return {"id": sop_id, "title": "t",
                "content_blobs": [{"url": "u", "content_type": "application/"
                                   "vnd.openxmlformats-officedocument."
                                   "wordprocessingml.document"}]}

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}),
        fetch_sop=fetch_sop,
        fetch_blob=lambda u: _docx(["word"] * 6000),
        nextseek_base_url=BASE)
    assert any("truncat" in n.lower() for n in notes)


def test_resolve_protocols_survives_a_fetch_error():
    def boom(sop_id):
        raise OSError("502")

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}), fetch_sop=boom, nextseek_base_url=BASE)
    assert resolved == {}
    assert any("P.A-1" in n for n in notes)


def test_resolve_protocols_survives_a_malformed_pdf_with_PyPDF2_present(monkeypatch):
    """Never gates output: a bad PDF blob degrades to a note even when PyPDF2
    IS installed and its reader raises a non-PdfSupportError."""
    def _raise(*a, **k):
        raise ValueError("bad pdf")

    stub = types.SimpleNamespace(PdfReader=_raise)
    monkeypatch.setitem(sys.modules, "PyPDF2", stub)

    def fetch_sop(sop_id):
        return {"id": sop_id, "title": "t",
                "content_blobs": [{"url": f"{BASE}/blob/1",
                                   "content_type": "application/pdf"}]}

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}),
        fetch_sop=fetch_sop,
        fetch_blob=lambda u: b"%PDF-1.4 malformed",
        nextseek_base_url=BASE)
    assert "P.A-1" in resolved
    assert any("P.A-1" in n and "PDF extraction failed" in n for n in notes)


# ---- enrichment -----------------------------------------------------------

def test_merge_is_leaf_wins():
    base = _input({"UID": "D.SEQ-1", "Tissue": "liver"})
    extra = _input({"UID": "D.SEQ-1", "Tissue": "kidney", "Organism": "Homo sapiens"})
    merged = en.merge_leaf_wins(base, extra)
    s = {x.uid: x for x in merged.samples}["D.SEQ-1"]
    assert s.metadata["Tissue"] == "liver"
    assert s.metadata["Organism"] == "Homo sapiens"


def test_merge_adds_samples_absent_from_the_base():
    base = _input({"UID": "D.SEQ-1"})
    extra = ad.NormalizedInput(samples=[
        ad.NormalizedSample(sample_type="TIS", uid="TIS-9",
                            metadata={"UID": "TIS-9"}, parent=None)],
        source={"adapter": "uids"})
    merged = en.merge_leaf_wins(base, extra)
    assert "TIS-9" in {s.uid for s in merged.samples}


def test_merge_with_nothing_to_add_is_identity():
    base = _input({"UID": "D.SEQ-1", "Tissue": "liver"})
    merged = en.merge_leaf_wins(base, ad.NormalizedInput())
    assert merged.samples[0].metadata == {"UID": "D.SEQ-1", "Tissue": "liver"}


def test_merge_records_both_sources():
    base = _input({"UID": "D.SEQ-1"})
    extra = ad.NormalizedInput(samples=[], source={"adapter": "uids"})
    merged = en.merge_leaf_wins(base, extra)
    assert "enriched_from" in merged.source
