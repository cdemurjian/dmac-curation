"""Phase 3b: protocol .docx rendering and the sample-tree coverage cross-check.

Three things are worth pinning here, because each of them is invisible in the
code and expensive to rediscover:

1. **3b, not 4.** Phases 4 and 8 are retired numbers that are never reused, so
   an inserted phase takes a letter suffix. `/curate-status` has to keep
   reporting it without resurrecting a retired integer.
2. **The consumption invariant.** Every section in `_methods.json` must be used
   exactly as often as it occurs. An unconsumed section is a protocol someone
   forgot to write; an overused one is a section pasted into two documents.
   Silence in either direction ships a wrong SOP set.
3. **Verbatim means verbatim.** The body of a protocol is the manuscript's own
   prose, round-tripped out of the written .docx. Only sections explicitly
   marked `"verbatim": false` are exempt.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import status as status_mod  # noqa: E402

BUILD = REPO / "scripts" / "build_protocols.py"
UPLOAD = REPO / "scripts" / "upload_sops.py"

METHODS = [
    {"heading": "Cell culture", "paras": ["NHEKs were grown in KSFM.",
                                          "Medium was changed daily."]},
    {"heading": "Imaging", "paras": ["Cells were imaged on a Leica SP8."]},
    {"heading": "Statistics", "paras": ["Values are mean ± SD."]},
]

MANIFEST = {
    "lab": "SHE", "stamp": "260807", "version": 1,
    "study": "Test et al. 2026",
    "protocols": [
        {"topic": "CellCulture", "headings": ["Cell culture"],
         "assays": ["Cell Culture"], "note": "the substrate rationale"},
        {"topic": "Imaging", "headings": ["Imaging"],
         "assays": ["Imaging - Data Linked"]},
        {"topic": "Statistics", "headings": ["Statistics"], "assays": []},
    ],
}

TREE = {
    "nodes": [{"id": "CEL", "label": "Cells", "count": 4},
              {"id": "D.IMG", "label": "Images", "count": 2},
              {"id": "A.IMG", "label": "Analysis", "count": 0}],
    "edges": [{"from": "CEL", "to": "CEL", "assays": ["Cell Culture"]},
              {"from": "CEL", "to": "D.IMG", "assays": ["Imaging - Data Linked"]},
              {"from": "D.IMG", "to": "A.IMG", "assays": ["Imaging Analysis"]}],
}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "protocols").mkdir()
    (tmp_path / "protocols" / "_methods.json").write_text(json.dumps(METHODS))
    (tmp_path / "protocols" / "_manifest.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "sample_tree.json").write_text(json.dumps(TREE))
    return tmp_path


def run(root: Path, *argv):
    return subprocess.run(
        ["uv", "run", "--script", str(BUILD), "--project-root", str(root), *argv],
        capture_output=True, text=True, timeout=180, cwd=str(root),
    )


def write_methods(root: Path, methods):
    (root / "protocols" / "_methods.json").write_text(json.dumps(methods))


def write_manifest(root: Path, manifest):
    (root / "protocols" / "_manifest.json").write_text(json.dumps(manifest))


# ── rendering ────────────────────────────────────────────────────────────────

def test_builds_one_docx_per_manifest_entry(project):
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr
    names = {p.name for p in (project / "protocols").glob("*.docx")}
    assert names == {"P.SHE-260807-V1_CellCulture.docx",
                     "P.SHE-260807-V1_Imaging.docx",
                     "P.SHE-260807-V1_Statistics.docx"}


def test_body_text_is_the_manuscript_prose_verbatim(project):
    docx = pytest.importorskip("docx")
    run(project)
    paras = [p.text for p in docx.Document(
        str(project / "protocols" / "P.SHE-260807-V1_CellCulture.docx")).paragraphs]
    assert paras[0] == "Cell culture"                    # italic heading
    assert paras[1:] == ["NHEKs were grown in KSFM.", "Medium was changed daily."]


def test_heading_is_italic_and_body_is_not(project):
    docx = pytest.importorskip("docx")
    run(project)
    doc = docx.Document(
        str(project / "protocols" / "P.SHE-260807-V1_CellCulture.docx"))
    assert doc.paragraphs[0].runs[0].italic is True
    assert not any(r.italic for r in doc.paragraphs[1].runs)


def test_nothing_but_the_excerpt_is_written(project):
    """No metadata block, no curation notes. A PI opens their own words."""
    docx = pytest.importorskip("docx")
    run(project)
    text = "\n".join(p.text for p in docx.Document(
        str(project / "protocols" / "P.SHE-260807-V1_Imaging.docx")).paragraphs)
    for leaked in ("SOP", "dmac", "curation", "Generated", "P.SHE-260807"):
        assert leaked not in text


def test_existing_docx_is_not_overwritten_without_force(project):
    run(project)
    target = project / "protocols" / "P.SHE-260807-V1_Imaging.docx"
    target.write_bytes(b"HANDED OVER ALREADY")
    r = run(project)
    assert target.read_bytes() == b"HANDED OVER ALREADY"
    assert "already exists" in r.stdout


def test_force_rewrites_an_existing_docx(project):
    run(project)
    target = project / "protocols" / "P.SHE-260807-V1_Imaging.docx"
    target.write_bytes(b"HANDED OVER ALREADY")
    run(project, "--force")
    assert target.read_bytes() != b"HANDED OVER ALREADY"


def test_only_renders_a_single_protocol(project):
    r = run(project, "--only", "Statistics")
    assert r.returncode == 0, r.stdout + r.stderr
    assert {p.name for p in (project / "protocols").glob("*.docx")} == {
        "P.SHE-260807-V1_Statistics.docx"}


def test_repeated_heading_is_consumed_in_document_order(project):
    """Oak et al. carries two distinct 'Nanoneedle AFM' sections."""
    write_methods(project, [
        {"heading": "AFM", "paras": ["First occurrence."]},
        {"heading": "AFM", "paras": ["Second occurrence."]},
    ])
    write_manifest(project, {**MANIFEST, "protocols": [
        {"topic": "AfmOne", "headings": ["AFM"]},
        {"topic": "AfmTwo", "headings": ["AFM"]},
    ]})
    docx = pytest.importorskip("docx")
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr

    def body(topic):
        return [p.text for p in docx.Document(str(
            project / "protocols" / f"P.SHE-260807-V1_{topic}.docx")).paragraphs][1:]

    assert body("AfmOne") == ["First occurrence."]
    assert body("AfmTwo") == ["Second occurrence."]


# ── the three checks ─────────────────────────────────────────────────────────

def test_unconsumed_section_is_reported_and_fails(project):
    """A Methods section no protocol carries is a protocol someone forgot."""
    write_methods(project, METHODS + [
        {"heading": "Western blot", "paras": ["Lysates were run on a Wes."]}])
    r = run(project)
    assert r.returncode != 0
    assert "UNCONSUMED" in r.stdout and "Western blot" in r.stdout


def test_overused_section_is_reported_and_fails(project):
    """One section pasted into two documents."""
    write_manifest(project, {**MANIFEST, "protocols": MANIFEST["protocols"] + [
        {"topic": "ImagingAgain", "headings": ["Imaging"]}]})
    r = run(project)
    assert r.returncode != 0
    assert "OVERUSED" in r.stdout


def test_heading_missing_from_methods_is_a_hard_error(project):
    write_manifest(project, {**MANIFEST, "protocols": [
        {"topic": "Ghost", "headings": ["No such section"]}]})
    r = run(project)
    assert r.returncode != 0
    assert "not\nin the methods file" in r.stderr or "methods file" in r.stderr


def test_declared_non_verbatim_section_is_exempt_from_the_check(project):
    """Transcribed display equations are the motivating case."""
    write_methods(project, [{"heading": "Sphere", "verbatim": False,
                             "paras": ["P = 4E√R / [3(1 − ν²)] δ³ᐟ² − 2πγR"]}])
    write_manifest(project, {**MANIFEST, "protocols": [
        {"topic": "Afm", "headings": ["Sphere"]}]})
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "NOT VERBATIM" not in r.stdout


# ── manifest validation ──────────────────────────────────────────────────────

@pytest.mark.parametrize("bad,expect", [
    ({"stamp": "260807", "protocols": []}, "lab"),
    ({"lab": "SHE", "protocols": []}, "stamp"),
    ({"lab": "SHE", "stamp": "26087", "protocols": [{"topic": "A", "headings": ["Imaging"]}]},
     "YYMMDD"),
    ({"lab": "SHE", "stamp": "260807", "protocols": []}, "declares no protocols"),
    ({"lab": "SHE", "stamp": "260807",
      "protocols": [{"topic": "has space", "headings": ["Imaging"]}]}, "CamelCase"),
    ({"lab": "SHE", "stamp": "260807",
      "protocols": [{"topic": "A", "headings": ["Imaging"]},
                    {"topic": "A", "headings": ["Imaging"]}]}, "duplicate topic"),
])
def test_malformed_manifest_is_rejected(project, bad, expect):
    write_manifest(project, bad)
    r = run(project)
    assert r.returncode != 0
    assert expect in r.stderr


# ── coverage ─────────────────────────────────────────────────────────────────

def coverage_text(project) -> str:
    return (project / "protocols" / "COVERAGE.md").read_text()


def test_coverage_joins_protocols_to_edges_by_exact_assay_title(project):
    run(project)
    text = coverage_text(project)
    assert "`CEL→CEL`" in text and "`CEL→D.IMG`" in text
    assert "✅ `CellCulture`" in text


def test_an_edge_with_no_protocol_is_reported_as_a_gap(project):
    """D.IMG→A.IMG is licensed by Imaging Analysis, which nothing documents."""
    run(project)
    text = coverage_text(project)
    assert "❌ none" in text
    assert "1 edge(s) with no protocol" in text


def test_a_protocol_with_no_edge_is_reported_but_is_not_an_error(project):
    r = run(project)
    assert r.returncode == 0
    assert "1 protocol(s) referenced by no edge" in coverage_text(project)
    assert "`Statistics`" in coverage_text(project)


def test_count_zero_child_tier_is_flagged_per_edge(project):
    """A protocol can document one built edge and one that is not."""
    write_manifest(project, {**MANIFEST, "protocols": [
        {"topic": "Imaging", "headings": ["Imaging"],
         "assays": ["Imaging - Data Linked", "Imaging Analysis"]},
        {"topic": "CellCulture", "headings": ["Cell culture"], "assays": []},
        {"topic": "Statistics", "headings": ["Statistics"], "assays": []},
    ]})
    run(project)
    row = [l for l in coverage_text(project).splitlines()
           if l.startswith("| `Imaging` |")][0]
    assert "`D.IMG→A.IMG` (count=0)" in row
    assert "`CEL→D.IMG`" in row and "`CEL→D.IMG` (count=0)" not in row


def test_coverage_only_refreshes_tables_without_writing_docx(project):
    r = run(project, "--coverage-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not list((project / "protocols").glob("*.docx"))
    assert (project / "protocols" / "COVERAGE.md").is_file()


def test_missing_sample_tree_still_renders_and_says_why(project):
    (project / "sample_tree.json").unlink()
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(list((project / "protocols").glob("*.docx"))) == 3
    assert "Run `/curate-sample-tree` first" in coverage_text(project)


def test_sop_ids_appear_once_registration_has_run(project):
    (project / "protocols" / "_sops.json").write_text(json.dumps({
        "P.SHE-260807-V1_CellCulture.docx": {
            "id": "649", "title": "P.SHE-260807-V1_CellCulture.docx",
            "url": "https://example.invalid/sops/649"}}))
    run(project, "--coverage-only")
    row = [l for l in coverage_text(project).splitlines()
           if l.startswith("| `CellCulture` |")][0]
    assert "| 649 |" in row


# ── phase wiring ─────────────────────────────────────────────────────────────

def test_status_reports_protocols_as_phase_3b_not_4(curation_project):
    (curation_project / "protocols").mkdir()
    (curation_project / "protocols" / "P.KAM-260807-V1_X.docx").write_bytes(b"x")
    st = status_mod.collect_status(curation_project)
    art = {a["name"]: a for a in st["modes"]["pipeline"]["artifacts"]}["protocols"]
    assert art["phase"] == "3b"
    assert art["present"] is True
    phases = {a["phase"] for a in st["modes"]["pipeline"]["artifacts"]}
    assert 4 not in phases, "phase 4 is retired and must never be reused"


def test_status_treats_an_empty_protocols_dir_as_absent(curation_project):
    (curation_project / "protocols").mkdir()
    st = status_mod.collect_status(curation_project)
    art = {a["name"]: a for a in st["modes"]["pipeline"]["artifacts"]}["protocols"]
    assert art["present"] is False


def test_status_flags_a_stale_coverage_file(curation_project):
    import os
    import time
    d = curation_project / "protocols"
    d.mkdir()
    (d / "COVERAGE.md").write_text("old")
    time.sleep(0.01)
    doc = d / "P.KAM-260807-V1_X.docx"
    doc.write_bytes(b"x")
    os.utime(doc, (time.time() + 10, time.time() + 10))
    st = status_mod.collect_status(curation_project)
    art = {a["name"]: a for a in st["modes"]["pipeline"]["artifacts"]}["protocols"]
    assert "stale" in art["detail"]


def test_upload_previews_by_default_and_never_names_dry_run():
    """Write-safety convention: --write is the only thing that touches the server."""
    text = UPLOAD.read_text()
    assert "--dry-run" not in text
    assert '"--write"' in text


# ── the upload confirm gate ──────────────────────────────────────────────────
#
# Authoring protocols is local and reversible. Registering them is neither: SOP
# records land in a catalog every curator on the project shares, get cited by row
# after row, and have no clean undo. Approval to run phase 3b is therefore not
# approval to upload, and the gate has to hold in the script rather than only in
# the command doc, because prose is skimmable and a flag is not.


def _upload(*argv, cwd):
    return subprocess.run(
        ["uv", "run", "--script", str(UPLOAD), *argv],
        capture_output=True, text=True, timeout=180, cwd=str(cwd),
    )


def test_bare_write_is_refused(tmp_path):
    r = _upload("--project-id", "4", "--write", cwd=tmp_path)
    assert r.returncode != 0
    assert "REFUSED" in r.stderr


def test_the_refusal_tells_you_to_ask_the_user(tmp_path):
    r = _upload("--project-id", "4", "--write", cwd=tmp_path)
    assert "Ask the user before uploading" in r.stderr
    assert "--write --confirmed" in r.stderr


def test_refusal_happens_before_any_network_call(tmp_path, monkeypatch):
    """No credentials, no protocols dir, no network: it must still refuse.

    If the gate ran after the client was built, this would fail on missing
    credentials instead, which would mean a correctly-credentialled run had
    already authenticated before anything checked for approval.
    """
    env = {k: v for k, v in __import__("os").environ.items()
           if not k.startswith("NEXTSEEK_")}
    r = subprocess.run(
        ["uv", "run", "--script", str(UPLOAD), "--project-id", "4", "--write"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path), env=env,
    )
    assert r.returncode != 0
    assert "REFUSED" in r.stderr
    assert "NEXTSEEK_USERNAME" not in r.stderr


def test_confirmed_alone_does_not_write(tmp_path):
    """--confirmed is an assertion about consent, not a write flag."""
    r = _upload("--project-id", "4", "--confirmed", cwd=tmp_path)
    assert "REFUSED" not in (r.stderr or "")


def test_command_doc_requires_asking_before_upload():
    doc = (REPO / "commands" / "curate-protocols.md").read_text()
    assert "AskUserQuestion" in doc, "the doc must name the mechanism for asking"
    assert "--write --confirmed" in doc
    assert "Ask the user before uploading anything to NExtSEEK" in doc


def test_phases_doc_records_that_approval_to_run_is_not_approval_to_upload():
    text = (REPO / "skills" / "curation" / "PHASES.md").read_text()
    section = text.split("## Phase 3b", 1)[1].split("\n## ", 1)[0]
    assert "not approval to upload" in section
    assert "AskUserQuestion" in section
