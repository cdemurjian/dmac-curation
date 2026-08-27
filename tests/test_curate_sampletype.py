"""The schema-mode deliverable: <TYPE>.review.md and its siblings."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import review as sr  # noqa: E402
from schema import ontology as so  # noqa: E402

COMMAND = REPO / "commands" / "curate-sampletype.md"
SCHEMA_DOC = REPO / "skills" / "curation" / "SCHEMA.md"

RECORD = {
    "SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
    "Description": "Quantitative results from viability experiments.",
    "Tags": "MTS assay, MTT assay, WST-1, CellTiter-Glo",
    "Required Metadata": "UID, File_PrimaryData, Scientist, Parent",
    "Standard Metadata": "Protocol, CellLine, Type",
    "Possible Metadata Fields": "Notes",
    "Associated Assay Parents": "Cell Viability Assay",
    "Parent_SampleTypes": "CEL",
}


def _render():
    return sr.render_review(
        "D.VIA",
        record=RECORD,
        current_fields={"required": ["UID", "File_PrimaryData", "Scientist", "Parent"],
                        "standard": ["Protocol", "CellLine", "Type"],
                        "possible": ["Notes"]},
        proposals=[
            {"field": "Timepoint", "rationale":
             "the producing assay is time-series by nature; 3 sibling Raw types "
             "carry it; observed in previous_metadata as 24h, 48h",
             "evidence": ["sibling: D.FLOW", "observed: 24h, 48h"]},
        ],
        reuse_decisions=[
            {"proposed": "PlateReaderModel", "used_instead": "Instrument",
             "reason": "16 existing usages across the catalog"},
        ],
        ontology={"Type": so.propose_values(RECORD, "Type")},
        open_questions=["Is dose in uM or mg/mL? Both appear in previous_metadata."],
        dictionary_entries=["Timepoint", "Instrument"],
    )


def test_command_file_exists_with_frontmatter():
    assert COMMAND.exists()
    text = COMMAND.read_text()
    assert text.startswith("---")
    assert "description:" in text.split("---")[1]


def test_command_states_it_writes_to_cwd():
    text = COMMAND.read_text()
    assert "current working directory" in text
    assert "no lockfile" in text.lower()


def test_command_states_a_human_applies_the_proposal():
    text = COMMAND.read_text()
    assert "never writes to NExtSEEK" in text
    assert "sampletypes_db.json" in text


def test_command_references_the_real_scripts():
    text = COMMAND.read_text()
    for rel in ("scripts/schema/field_index.py", "scripts/schema/ontology.py",
                "scripts/schema/dictionary.py", "scripts/schema/terms.py"):
        assert rel in text
        assert (REPO / rel).exists()


def test_schema_doc_is_no_longer_a_stub():
    text = SCHEMA_DOC.read_text()
    assert "Status: stub" not in text
    assert "reuse check" in text.lower()
    assert "Ontology sheet" in text


def test_schema_doc_states_templates_are_out_of_scope():
    """tree vs graph: CEDAR has no cross-record reference concept."""
    text = SCHEMA_DOC.read_text()
    assert "tree" in text.lower() and "graph" in text.lower()
    assert "no CEDAR template is emitted" in text


def test_review_contains_every_required_section():
    md = _render()
    for heading in sr.REQUIRED_SECTIONS:
        assert heading in md, f"review is missing section {heading!r}"


def test_review_states_current_state():
    md = _render()
    assert "6 required" in md or "4 required" in md
    assert "Protocol" in md


def test_every_proposal_carries_its_rationale():
    md = _render()
    assert "Timepoint" in md
    assert "time-series by nature" in md
    assert "observed: 24h, 48h" in md


def test_reuse_decisions_are_stated_so_they_can_be_overruled():
    md = _render()
    assert "PlateReaderModel" in md
    assert "Instrument" in md
    assert "16 existing usages" in md


def test_controlled_vocabulary_lists_the_source_of_every_value():
    md = _render()
    assert "MTS assay" in md
    assert "tags" in md


def test_open_questions_are_surfaced():
    assert "uM or mg/mL" in _render()


def test_how_to_apply_is_concrete():
    md = _render()
    section = md.split("## How to apply", 1)[1]
    assert "write_4sheet_xlsx" in section or "ontology.json" in section
    assert "by hand" in section.lower() or "manual" in section.lower()


def test_review_never_proposes_a_rename_or_split():
    """A field name shared across types is not a defect."""
    src = (REPO / "scripts" / "schema" / "review.py").read_text()
    assert "rename" not in src.lower() or "never" in src.lower()
    assert "homonym" not in src.lower()


def test_write_review_lands_in_cwd_schema_dir(tmp_path, plugin_sentinel):
    p = sr.write_review(tmp_path, "D.VIA", _render())
    assert p == tmp_path / "schema" / "D.VIA.review.md"
    assert p.read_text()


def test_write_proposed_record_is_catalog_shaped(tmp_path):
    p = sr.write_proposed_record(tmp_path, "D.VIA", RECORD)
    doc = json.loads(p.read_text())
    assert doc["SampleType"] == "D.VIA"
    assert "Required Metadata" in doc


def test_proposed_record_is_a_proposal_not_an_edit(tmp_path):
    """It must be diffable against the catalog, never written over it."""
    sr.write_proposed_record(tmp_path, "D.VIA", RECORD)
    assert not (REPO / "context" / "D.VIA.proposed.json").exists()


# --- external clade evidence ------------------------------------------------

NEIGHBORS = [
    {"relation": "parent", "label": "cytometry assay",
     "definition": "An assay that counts and/or measures characteristics of cells."},
    {"relation": "child", "label": "cell viability assay using Annexin V staining",
     "definition": "A cell viability assay that uses Annexin V staining."},
    {"relation": "child", "label": "cell viability assay based on detection of resorufin",
     "definition": ""},
]


def _render_with_clade(external_clade):
    return sr.render_review(
        "D.VIA", record=RECORD,
        current_fields={"required": [], "standard": [], "possible": []},
        proposals=[], reuse_decisions=[], ontology={},
        open_questions=[], dictionary_entries=[],
        external_clade=external_clade,
    )


def test_external_clade_is_a_required_section():
    assert "## External clade evidence" in sr.REQUIRED_SECTIONS


def test_external_clade_feeds_the_proposals_so_it_precedes_them():
    text = _render()
    assert text.index("## Current state") \
        < text.index("## External clade evidence") \
        < text.index("## Proposed additions")


def test_external_clade_renders_each_neighbour_with_relation_and_definition():
    text = _render_with_clade({
        "matched": "cell viability assay", "source": "OBI",
        "neighbors": NEIGHBORS, "reason": ""})
    assert "cell viability assay" in text
    assert "OBI" in text
    assert "cytometry assay" in text
    assert "parent" in text and "child" in text
    assert "Annexin V staining" in text


def test_external_clade_states_why_it_is_empty_rather_than_going_silent():
    """Silence cannot distinguish 'checked, found nothing' from 'never checked'."""
    text = _render_with_clade({
        "matched": "", "source": "", "neighbors": [],
        "reason": "no BIOPORTAL_API_KEY"})
    assert "no BIOPORTAL_API_KEY" in text


def test_external_clade_defaults_to_not_consulted():
    text = _render_with_clade(None)
    section = text.split("## External clade evidence")[1].split("##")[0]
    assert "not consulted" in section.lower()


def test_external_clade_never_presents_a_neighbour_as_a_field():
    """Evidence a curator reads. Nothing here mints a field name."""
    text = _render_with_clade({
        "matched": "cell viability assay", "source": "OBI",
        "neighbors": NEIGHBORS, "reason": ""})
    section = text.split("## External clade evidence")[1].split("## Proposed")[0]
    assert "evidence" in section.lower()
    assert "propos" not in section.lower().replace("## proposed", "")


# --- reference template checklist -------------------------------------------

CHECKLIST = {
    "template": "common assay template",
    "covered": 3, "total": 28,
    "missing": [
        {"name": "detection instrument", "branches": ["BAO"], "required": False,
         "description": "The names of equipment used for measurement/readout.",
         "reuse": "closest existing: `Instrument` (16 usages)"},
        {"name": "assay footprint", "branches": ["BAO"], "required": False,
         "description": "Physical format such as plate density.", "reuse": ""},
    ],
    "reason": "",
}


def _render_with_checklist(checklist):
    return sr.render_review(
        "D.VIA", record=RECORD,
        current_fields={"required": [], "standard": [], "possible": []},
        proposals=[], reuse_decisions=[], ontology={},
        open_questions=[], dictionary_entries=[],
        template_checklist=checklist,
    )


def test_template_checklist_is_a_required_section():
    assert "## Reference template checklist" in sr.REQUIRED_SECTIONS


def test_template_checklist_follows_the_clade_evidence_and_precedes_proposals():
    text = _render()
    assert text.index("## External clade evidence") \
        < text.index("## Reference template checklist") \
        < text.index("## Proposed additions")


def test_template_checklist_reports_coverage_against_the_reference():
    text = _render_with_checklist(CHECKLIST)
    assert "common assay template" in text
    assert "3" in text and "28" in text


def test_template_checklist_renders_each_uncovered_field_with_its_description():
    text = _render_with_checklist(CHECKLIST)
    assert "detection instrument" in text
    assert "equipment used for measurement" in text.lower()
    assert "BAO" in text


def test_template_checklist_shows_the_reuse_verdict_where_there_is_one():
    text = _render_with_checklist(CHECKLIST)
    assert "`Instrument`" in text


def test_template_checklist_states_why_it_is_empty_rather_than_going_silent():
    text = _render_with_checklist(
        {"template": "", "covered": 0, "total": 0, "missing": [],
         "reason": "no CEDAR_API_KEY"})
    assert "no CEDAR_API_KEY" in text


def test_template_checklist_defaults_to_not_consulted():
    text = _render_with_checklist(None)
    section = text.split("## Reference template checklist")[1].split("##")[0]
    assert "not consulted" in section.lower()
