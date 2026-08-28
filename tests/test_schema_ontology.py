"""schema mode's ontology artifact, and its round trip into the 4-sheet writer."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _common  # noqa: E402
from schema import field_index as fi  # noqa: E402
from schema import ontology as so  # noqa: E402

DVIA = {
    "SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
    "Tags": "viability data, MTS assay, MTT assay, WST-1, CellTiter-Glo",
    "Required Metadata": "UID, Scientist, Parent",
    "Standard Metadata": "Protocol, CellLine, Type",
    "Possible Metadata Fields": "Notes",
    "Associated Assay Parents": "Cell Viability Assay",
}


def test_propose_values_from_tags():
    out = so.propose_values(DVIA, "Type")
    values = [p.value for p in out]
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in values
    assert all(p.source == "tags" for p in out)


def test_propose_values_merges_observed_values():
    out = so.propose_values(DVIA, "Type", observed=["MTS assay", "alamarBlue"])
    by_value = {p.value: p for p in out}
    assert by_value["alamarBlue"].source == "observed"
    # A value present in BOTH is credited to the stronger source: observed.
    assert by_value["MTS assay"].source == "observed"


def test_propose_values_dedupes():
    out = so.propose_values(DVIA, "Type", observed=["MTS assay"])
    assert len(out) == len({p.value for p in out})


def test_propose_values_on_a_type_with_no_tags_and_no_observations():
    assert so.propose_values({"SampleType": "X"}, "Type") == []


def test_every_proposal_carries_its_source():
    for p in so.propose_values(DVIA, "Type", observed=["alamarBlue"]):
        assert p.source in {"tags", "observed", "bioportal", "sibling"}
        assert p.value


def test_to_ontology_json_is_the_write_4sheet_shape():
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    out = so.to_ontology_json(proposals)
    assert isinstance(out, dict)
    assert isinstance(out["Type"], list)
    assert all(isinstance(v, str) for v in out["Type"])


def test_ontology_artifact_round_trips_on_disk(tmp_path):
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    path = so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    assert path == tmp_path / "schema" / "D.VIA.ontology.json"
    assert so.load_ontology_artifact(tmp_path, "D.VIA")["Type"]


def test_artifact_records_the_source_of_every_value(tmp_path):
    """A bare value list cannot be judged; a list with sources can."""
    proposals = {"Type": so.propose_values(DVIA, "Type", observed=["alamarBlue"])}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    doc = json.loads((tmp_path / "schema" / "D.VIA.ontology.json").read_text())
    assert "_sources" in doc
    assert doc["_sources"]["Type"]["alamarBlue"] == "observed"


def test_load_ontology_artifact_strips_the_sources_block(tmp_path):
    """What feeds write_4sheet_xlsx must be exactly {field: [values]}."""
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    loaded = so.load_ontology_artifact(tmp_path, "D.VIA")
    assert "_sources" not in loaded


def test_load_ontology_artifact_missing_returns_empty(tmp_path):
    assert so.load_ontology_artifact(tmp_path, "NOPE") == {}


def test_artifact_feeds_write_4sheet_xlsx_end_to_end(tmp_path):
    """The dead capability, brought to life: schema mode -> Ontology sheet."""
    openpyxl = pytest.importorskip("openpyxl")
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    ontology = so.load_ontology_artifact(tmp_path, "D.VIA")

    out = tmp_path / "ArmA_D.VIA.xlsx"
    _common.write_4sheet_xlsx(
        out, "D.VIA",
        samples=[{"UID": "D.VIA-190903KAM-1", "Type": "MTS assay"}],
        assay_titles=["Cell Viability Assay"],
        ontology=ontology,
    )
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Instructions", "Samples", "Assay", "Ontology"]

    ont_rows = list(wb["Ontology"].iter_rows(values_only=True))
    assert ont_rows[0] == ("Field", "Value")
    assert ("Type", "MTS assay") in ont_rows

    instr = {r[0]: r for r in wb["Instructions"].iter_rows(values_only=True)}
    assert instr["Type"][1] == "D.VIA::Type"
    assert instr["Type"][2] == "Controlled Ontology"
    assert instr["Type"][3] == "Type"
    assert instr["UID"][2] == "Text"


def test_real_dvia_tags_yield_the_expected_value_set():
    rec = fi.type_record(fi.load_catalog(), "D.VIA")
    values = {p.value for p in so.propose_values(rec, "Type")}
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in values


def test_bioportal_availability_is_env_driven(monkeypatch):
    monkeypatch.delenv(so.BIOPORTAL_ENV_VAR, raising=False)
    assert so.bioportal_available() is False
    monkeypatch.setenv(so.BIOPORTAL_ENV_VAR, "k")
    assert so.bioportal_available() is True


def test_nothing_is_written_inside_the_plugin(tmp_path, plugin_sentinel):
    so.write_ontology_artifact(tmp_path, "D.VIA",
                               {"Type": so.propose_values(DVIA, "Type")})


# --- precedence -------------------------------------------------------------
#
# A submission is literally rejected against a repository vocabulary, so it
# outranks everything except a real observed workbook value (hard rule 4).
# Tags drops to the floor: it is a per-sample-type prose list, not a per-field
# vocabulary, and binding it to one field is an unverifiable assertion.

RECORD_WITH_TAGS = {"SampleType": "D.SEQ", "Tags": "RNA-Seq, FASTQ"}


def test_repository_outranks_bioportal_for_the_same_value():
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            bioportal=["RNA-Seq"], repository=["RNA-Seq"])
    assert [p.source for p in out if p.value == "RNA-Seq"] == ["repository"]


def test_observed_still_outranks_repository():
    """Hard rule 4: the workbook beats every declared schema."""
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            repository=["RNA-Seq"], observed=["RNA-Seq"])
    assert [p.source for p in out if p.value == "RNA-Seq"] == ["observed"]


def test_bioportal_outranks_a_cedar_branch_value():
    out = so.propose_values({}, "assay footprint", tags=[],
                            cedar_branch=["microplate"], bioportal=["microplate"])
    assert [p.source for p in out if p.value == "microplate"] == ["bioportal"]


def test_cedar_branch_outranks_a_tag():
    out = so.propose_values({}, "x", tags=["microplate"], cedar_branch=["microplate"])
    assert [p.source for p in out if p.value == "microplate"] == ["cedar_branch"]


def test_a_repository_value_carries_an_explanatory_note():
    out = so.propose_values({}, "LibraryStrategy", tags=[], repository=["WGS"])
    assert "reject" in out[0].note.lower()


def test_every_source_still_contributes_its_unique_values():
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            repository=["WGS"], bioportal=["exome sequencing"])
    assert {p.value for p in out} == {"RNA-Seq", "FASTQ", "WGS", "exome sequencing"}
