"""scripts/_common.py must be a shared library, not IntravChip's constants (P3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _common  # noqa: E402


# ---- surviving shared API -------------------------------------------------

def test_mint_uid_signature():
    assert _common.mint_uid("RNA", "KAM", "260527", 1) == "RNA-260527KAM-1"


def test_mint_uid_format():
    assert _common.mint_uid("D.SEQ", "ENG", "260514", 42) == "D.SEQ-260514ENG-42"


def test_placeholder_marker_shape():
    """SKILL.md hard rule 8 — greppable marker, never a blank."""
    assert _common.placeholder("no tumor parent") == (
        "*** PLACEHOLDER: no tumor parent ***"
    )
    assert _common.PLACEHOLDER in _common.placeholder("x")


def test_schema_column_order_is_uid_then_schema_then_extras():
    """The genuinely shared capability from _common.py:212-227."""
    schema = {
        "SampleType": "TST",
        "Required Metadata": "Name, Parent",
        "Standard Metadata": "Notes",
        "Possible Metadata Fields": "Tags",
    }
    samples = [{"UID": "TST-1", "Name": "a", "Extra": "z"}]
    assert _common.schema_column_order(schema, samples) == [
        "UID", "Name", "Parent", "Notes", "Tags", "Extra",
    ]


def test_sampletype_schema_reads_the_plugin_catalog():
    rec = _common.sampletype_schema("MUS")
    assert rec["SampleType"] == "MUS"


def test_sampletype_schema_accepts_an_explicit_catalog(tmp_path):
    catalog = tmp_path / "types.json"
    catalog.write_text(json.dumps([{"SampleType": "ZZZ", "Name": "Fake"}]))
    rec = _common.sampletype_schema("ZZZ", catalog=catalog)
    assert rec["Name"] == "Fake"


def test_sampletype_schema_raises_on_unknown():
    with pytest.raises(KeyError):
        _common.sampletype_schema("NOT_A_REAL_TYPE")


# ---- IntravChip residue must be gone --------------------------------------

REMOVED = [
    "ROOT", "MANIFEST", "OMERO_CSV", "METNET_ALL", "SAMPLETYPES_DB",
    "OOC_UID_MAP", "ASSAY_SHEETS", "CEL_REUSE", "SCIENTIST", "MS_PROTOCOL",
    "_TUMOR_PARENT_PATTERNS", "tumor_parent_for", "load_metnet_all",
    "metnet_cel_lookup", "metnet_ooc_vocab",
]


@pytest.mark.parametrize("name", REMOVED)
def test_project_specific_name_is_gone(name):
    assert not hasattr(_common, name), (
        f"_common.{name} is IntravChip-specific and belongs in project config"
    )


def test_no_person_name_in_source():
    src = (REPO / "scripts" / "_common.py").read_text()
    assert "Marie Floryan" not in src
    assert "MetNet All 260527.xlsx" not in src
    assert "HUVEC" not in src
    assert "MDA-MB-231" not in src


def test_no_module_level_file_reads():
    """A module-level Path().read_text() would re-introduce plugin anchoring."""
    src = (REPO / "scripts" / "_common.py").read_text()
    for i, line in enumerate(src.splitlines(), 1):
        if line.startswith((" ", "\t", "#", "@")) or not line.strip():
            continue
        assert "read_text()" not in line, f"module-level read at line {i}: {line}"
        assert "load_workbook(" not in line, f"module-level read at line {i}: {line}"


# ---- the writer still works ------------------------------------------------

def test_write_4sheet_xlsx_emits_four_sheets(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-260527KAM-1", "Name": "m1"}],
        assay_titles=["Tissue Collection"],
    )
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Instructions", "Samples", "Assay", "Ontology"]


def test_write_4sheet_xlsx_populates_ontology_when_given(tmp_path):
    """The dead capability at _common.py:194 — nothing has ever passed this."""
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-260527KAM-1", "Strain": "C57BL/6J"}],
        assay_titles=[],
        ontology={"Strain": ["C57BL/6J", "BALB/c"]},
    )
    wb = openpyxl.load_workbook(out)
    rows = list(wb["Ontology"].iter_rows(values_only=True))
    assert rows[0] == ("Field", "Value")
    assert ("Strain", "C57BL/6J") in rows
    assert ("Strain", "BALB/c") in rows


def test_ontology_fields_are_declared_controlled_in_instructions(tmp_path):
    """schema-mode spec: Instructions declares the type, Ontology carries values."""
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-260527KAM-1", "Strain": "C57BL/6J"}],
        assay_titles=[],
        ontology={"Strain": ["C57BL/6J"]},
    )
    wb = openpyxl.load_workbook(out)
    rows = list(wb["Instructions"].iter_rows(values_only=True))
    assert rows[0] == ("Field", "Database Field", "Field Type", "Ontology")
    strain = [r for r in rows if r[0] == "Strain"][0]
    assert strain[1] == "MUS::Strain"
    assert strain[2] == "Controlled Ontology"
    assert strain[3] == "Strain"
    other = [r for r in rows if r[0] == "UID"][0]
    assert other[2] == "Text"
