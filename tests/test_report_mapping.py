"""The mapping spec and its validator - the core of report mode's design."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import mapping as mp  # noqa: E402


def _input(**metadata):
    base = {"UID": "D.SEQ-1", "Parent": "TIS-1", "LibraryLayout": "paired"}
    base.update(metadata)
    return ad.NormalizedInput(
        samples=[
            ad.NormalizedSample(sample_type="D.SEQ", uid="D.SEQ-1",
                                metadata=base, parent="TIS-1"),
            ad.NormalizedSample(sample_type="TIS", uid="TIS-1",
                                metadata={"UID": "TIS-1", "Tissue": "liver"},
                                parent=None),
        ],
        source={"adapter": "curated_sheet", "path": "ArmA.xlsx"},
    )


def _mapping(**samples_over):
    samples = {
        "*library name": {"source": "UID"},
        "*title": {"source": "UID"},
        "*library strategy": {"const": "RNA-Seq"},
        "*organism": {"const": "Homo sapiens"},
        "*molecule": {"const": "polyA RNA"},
        "*single or paired-end": {"source": "LibraryLayout",
                                  "map": {"paired": "paired-end"}},
        "*instrument model": {"const": "Illumina NextSeq 500"},
        "*raw file": {"unmapped": "raw file names are added at deposit time"},
    }
    samples.update(samples_over)
    return {
        "report_type": "GEO",
        "source": {"adapter": "curated_sheet", "path": "ArmA.xlsx"},
        "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 1},
        "samples": samples,
        "study": {"*title": {"synthesize": "study title from manuscript"},
                  "*summary (abstract)": {"synthesize": "abstract"},
                  "*experimental design": {"synthesize": "design"}},
    }


SPEC = None


def spec():
    global SPEC
    if SPEC is None:
        SPEC = mp.load_template_spec(ASSETS / "GEO-updated.json")
    return SPEC


# ---- template spec loading ------------------------------------------------

def test_load_template_spec_reads_sections():
    s = spec()
    assert s.report_type == "GEO"
    assert "*library name" in s.sections["samples"]
    assert "*title" in s.sections["study"]
    assert s.row_section == "samples"


def test_required_excludes_double_star():
    s = spec()
    assert "*organism" in s.required["samples"]
    assert "**tissue" not in s.required["samples"]
    assert "**tissue" in s.sections["samples"]


def test_controlled_vocabulary_is_loaded():
    s = spec()
    assert "RNA-Seq" in s.cv["library_strategy"]
    assert s.cv["library_layout"]


def test_row_section_constants_match_upstream():
    assert mp.ROW_SECTION == {"GEO": "samples", "SRA": "libraries",
                              "PRIDE": "sample_metadata"}
    assert mp.TARGET_SAMPLETYPE == {"GEO": "D.SEQ", "SRA": "D.SEQ",
                                    "PRIDE": "D.MSP"}


def test_sra_spec_loads_with_libraries_as_the_row_section():
    s = mp.load_template_spec(ASSETS / "SRA.json")
    assert s.row_section == "libraries"
    assert "biosamples" in s.sections


def test_pride_spec_loads_with_sample_metadata_as_the_row_section():
    s = mp.load_template_spec(ASSETS / "pride.json")
    assert s.row_section == "sample_metadata"
    assert "project_metadata" in s.sections


# ---- mapping validation ---------------------------------------------------

def test_a_complete_mapping_validates_clean():
    assert mp.validate_mapping(_mapping(), spec(), _input()) == []


def test_unknown_target_field_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"not a real field": {"const": "x"}}), spec(), _input())
    assert any(e.code == "unknown_field" for e in errs)


def test_missing_required_field_is_rejected():
    m = _mapping()
    del m["samples"]["*organism"]
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "required_unmapped" and e.field == "*organism"
               for e in errs)


def test_unmapped_without_a_reason_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"unmapped": ""}}), spec(), _input())
    assert any(e.code == "unmapped_without_reason" for e in errs)


def test_unmapped_with_a_reason_is_accepted():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"unmapped": "not recorded by this PI"}}),
        spec(), _input())
    assert errs == []


def test_source_column_absent_from_the_input_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "NoSuchColumn"}}), spec(), _input())
    assert any(e.code == "source_column_missing" for e in errs)


def test_source_column_found_on_an_ancestor_needs_via_lineage():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "Tissue"}}), spec(), _input())
    assert any(e.code == "needs_via_lineage" for e in errs)


def test_via_lineage_accepts_an_ancestor_only_column():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "Tissue", "via_lineage": True}}),
        spec(), _input())
    assert errs == []


def test_const_outside_the_controlled_vocabulary_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*library strategy": {"const": "RNAseq"}}), spec(), _input())
    assert any(e.code == "const_not_in_cv" for e in errs)
    assert any("RNA-Seq" in e.message for e in errs)


def test_const_inside_the_controlled_vocabulary_is_accepted():
    errs = mp.validate_mapping(
        _mapping(**{"*library strategy": {"const": "RNA-Seq"}}), spec(), _input())
    assert errs == []


def test_map_output_outside_the_controlled_vocabulary_is_rejected():
    """SKILL.md pitfall: GEO dropdowns are word- and case-exact.
    `paired-end` not `paired`; `Illumina NextSeq 500` not `NextSeq 500`."""
    errs = mp.validate_mapping(
        _mapping(**{"*single or paired-end":
                    {"source": "LibraryLayout", "map": {"paired": "paired"}}}),
        spec(), _input())
    assert any(e.code == "map_output_not_in_cv" for e in errs)


def test_a_field_with_no_controlled_vocabulary_accepts_any_const():
    errs = mp.validate_mapping(
        _mapping(**{"*title": {"const": "anything at all"}}), spec(), _input())
    assert errs == []


def test_two_directives_on_one_field_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"const": "Homo sapiens", "source": "UID"}}),
        spec(), _input())
    assert any(e.code == "conflicting_directives" for e in errs)


def test_no_directive_at_all_is_rejected():
    errs = mp.validate_mapping(_mapping(**{"*organism": {}}), spec(), _input())
    assert any(e.code == "no_directive" for e in errs)


def test_an_unrecognized_directive_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"compute": "x"}}), spec(), _input())
    assert any(e.code == "unknown_directive" for e in errs)


def test_synthesize_is_rejected_in_the_row_section():
    """synthesize is study-level only: it is O(1), not O(rows)."""
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"synthesize": "the organism"}}),
        spec(), _input())
    assert any(e.code == "synthesize_in_row_section" for e in errs)


def test_row_scope_mismatch_is_rejected():
    m = _mapping()
    m["row_scope"]["expected_rows"] = 99
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "row_count_mismatch" for e in errs)


def test_row_scope_counts_only_the_target_sampletype():
    """The input has a TIS row too; only D.SEQ rows count."""
    assert mp.validate_mapping(_mapping(), spec(), _input()) == []


def test_report_type_mismatch_is_rejected():
    m = _mapping()
    m["report_type"] = "SRA"
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "report_type_mismatch" for e in errs)


def test_errors_carry_section_field_code_and_message():
    errs = mp.validate_mapping(
        _mapping(**{"zzz": {"const": "x"}}), spec(), _input())
    e = errs[0]
    assert e.section and e.field and e.code and e.message


def test_source_columns_unions_every_sample():
    cols = mp.source_columns(_input())
    assert "LibraryLayout" in cols
    assert "Tissue" in cols


def test_cv_for_field_maps_geo_field_names_to_cv_keys():
    s = spec()
    assert "RNA-Seq" in mp.cv_for_field(s, "*library strategy")
    assert mp.cv_for_field(s, "*title") is None
