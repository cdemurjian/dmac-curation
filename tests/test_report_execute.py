"""Deterministic execution of a validated mapping."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import execute as ex  # noqa: E402
from report import mapping as mp  # noqa: E402

SPEC = mp.load_template_spec(ASSETS / "GEO-updated.json")


def _input(n=2):
    samples = [ad.NormalizedSample(
        sample_type="D.SEQ", uid=f"D.SEQ-{i}",
        metadata={"UID": f"D.SEQ-{i}", "Parent": "TIS-1",
                  "LibraryLayout": "paired"},
        parent="TIS-1") for i in range(1, n + 1)]
    samples.append(ad.NormalizedSample(
        sample_type="TIS", uid="TIS-1",
        metadata={"UID": "TIS-1", "Tissue": "liver"}, parent=None))
    return ad.NormalizedInput(samples=samples,
                              source={"adapter": "curated_sheet"})


def _mapping(n=2, **over):
    samples = {
        "*library name": {"source": "UID"},
        "*title": {"source": "UID"},
        "*library strategy": {"const": "RNA-Seq"},
        "*organism": {"const": "Homo sapiens"},
        "**tissue": {"source": "Tissue", "via_lineage": True},
        "*molecule": {"const": "polyA RNA"},
        "*single or paired-end": {"source": "LibraryLayout",
                                  "map": {"paired": "paired-end"}},
        "*instrument model": {"const": "Illumina NextSeq 500"},
        "*raw file": {"unmapped": "added at deposit time"},
    }
    samples.update(over)
    return {"report_type": "GEO",
            "source": {"adapter": "curated_sheet"},
            "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": n},
            "samples": samples,
            "study": {"*title": {"synthesize": "study title"},
                      "*summary (abstract)": {"synthesize": "abstract"},
                      "*experimental design": {"synthesize": "design"}}}


# ---- row production -------------------------------------------------------

def test_one_row_per_target_sample():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert len(filled["samples"]) == 2


def test_non_target_sampletypes_do_not_become_rows():
    """The TIS ancestor must not appear as a GEO sample row."""
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert all(r["*library name"].startswith("D.SEQ") for r in filled["samples"])


def test_row_parity_holds_for_a_large_input():
    n = 195  # the size that cost chat_nextseek a 5.1M-token prompt
    filled, _ = ex.apply_mapping(_mapping(n), SPEC, _input(n))
    assert len(filled["samples"]) == n


def test_row_parity_violation_raises():
    m = _mapping()
    m["row_scope"]["expected_rows"] = 99
    with pytest.raises(ex.RowParityError):
        ex.apply_mapping(m, SPEC, _input())


# ---- directives -----------------------------------------------------------

def test_source_copies_the_column():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*library name"] == "D.SEQ-1"


def test_const_is_identical_on_every_row():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert {r["*organism"] for r in filled["samples"]} == {"Homo sapiens"}


def test_map_normalizes_the_value():
    """paired -> paired-end. GEO dropdowns are word- and case-exact."""
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*single or paired-end"] == "paired-end"


def test_map_passes_through_a_value_it_has_no_entry_for():
    m = _mapping(**{"*single or paired-end":
                    {"source": "LibraryLayout", "map": {"single": "single"}}})
    filled, _ = ex.apply_mapping(m, SPEC, _input())
    assert filled["samples"][0]["*single or paired-end"] == "paired"


def test_via_lineage_pulls_from_an_ancestor():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["**tissue"] == "liver"


def test_unmapped_produces_an_empty_string_not_a_placeholder():
    """Deliberately empty with a stated reason is not a gap."""
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*raw file"] == ""
    assert not any(g.field == "*raw file" for g in gaps)


def test_synthesize_uses_the_supplied_text():
    filled, _ = ex.apply_mapping(
        _mapping(), SPEC, _input(),
        synthesized={"study": {"*title": "Endothelial response to flow"}})
    assert filled["study"]["*title"] == "Endothelial response to flow"


def test_synthesize_without_supplied_text_becomes_a_placeholder():
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    assert "*** PLACEHOLDER:" in filled["study"]["*title"]
    assert any(g.field == "*title" and g.section == "study" for g in gaps)


# ---- degradation ----------------------------------------------------------

def test_a_missing_source_value_becomes_a_placeholder_not_a_blank():
    """SKILL.md hard rule 8: greppable marker, never a blank."""
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    assert "*** PLACEHOLDER:" in filled["samples"][0]["*single or paired-end"]
    assert any(g.field == "*single or paired-end" for g in gaps)


def test_an_unresolvable_lineage_value_becomes_a_placeholder():
    lonely = ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid="D.SEQ-1",
                                     metadata={"UID": "D.SEQ-1",
                                               "LibraryLayout": "paired"},
                                     parent=None)],
        source={"adapter": "tabular"})
    filled, gaps = ex.apply_mapping(_mapping(1), SPEC, lonely)
    assert "*** PLACEHOLDER:" in filled["samples"][0]["**tissue"]
    assert any(g.field == "**tissue" for g in gaps)


def test_degradation_never_raises():
    """Never refuse outright; the curator decides what to do about gaps."""
    empty = ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid="X",
                                     metadata={}, parent=None)],
        source={"adapter": "tabular"})
    filled, gaps = ex.apply_mapping(_mapping(1), SPEC, empty)
    assert filled["samples"]
    assert gaps


def test_gap_records_what_was_searched_and_why_it_failed():
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    _, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    g = [g for g in gaps if g.field == "*single or paired-end"][0]
    assert g.uid == "D.SEQ-1"
    assert "LibraryLayout" in g.searched
    assert g.reason


def test_nothing_is_ever_fabricated():
    """A gap is a placeholder, never a plausible invented value."""
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, _ = ex.apply_mapping(_mapping(), SPEC, bad)
    assert filled["samples"][0]["*single or paired-end"] != "paired-end"


# ---- artifacts ------------------------------------------------------------

def test_filled_json_round_trips(tmp_path, plugin_sentinel):
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    p = ex.write_filled(tmp_path, "GEO", filled)
    assert p == tmp_path / "report" / "GEO_filled.json"
    assert json.loads(p.read_text())["samples"]


def test_completeness_report_names_every_gap(tmp_path):
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    md = ex.render_completeness("GEO", gaps, _mapping(), bad)
    assert "*single or paired-end" in md
    assert "D.SEQ-1" in md
    assert "LibraryLayout" in md


def test_completeness_report_lists_deliberate_omissions_separately(tmp_path):
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    md = ex.render_completeness("GEO", gaps, _mapping(), _input())
    assert "Deliberately unmapped" in md
    assert "added at deposit time" in md


def test_completeness_report_written_to_cwd(tmp_path, plugin_sentinel):
    p = ex.write_completeness(tmp_path, "GEO", "# x")
    assert p == tmp_path / "report" / "GEO.completeness.md"


def test_clean_run_says_so():
    filled, gaps = ex.apply_mapping(
        _mapping(), SPEC, _input(),
        synthesized={"study": {"*title": "t", "*summary (abstract)": "s",
                               "*experimental design": "d"}})
    assert gaps == []
    assert "no gaps" in ex.render_completeness("GEO", gaps, _mapping(), _input()).lower()
