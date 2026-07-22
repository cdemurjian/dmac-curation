"""PHASES.md must record the two decisions that are invisible in the code."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PHASES = REPO / "skills" / "curation" / "PHASES.md"


def _section(number: int) -> str:
    text = PHASES.read_text()
    marker = f"## Phase {number} "
    assert marker in text, f"no section for phase {number}"
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_phase_5_states_the_output_is_a_review_artifact():
    s = _section(5)
    assert "review artifact" in s.lower()
    assert "curator" in s.lower()


def test_phase_5_explains_why_it_does_not_collapse_into_phase_6():
    assert "not a build intermediate" in _section(5).lower()


def test_phase_5_documents_the_ontology_parameter():
    s = _section(5)
    assert "write_4sheet_xlsx" in s
    assert "ontology=" in s


def test_phase_6_warns_flat_cannot_carry_controlled_vocabulary():
    s = _section(6)
    assert "Ontology" in s
    assert "silently discard" in s.lower()


def test_phase_6_records_the_multiple_sample_types_constraint():
    assert "only allowed in flat" in _section(6).lower()


def test_phase_7_owns_the_synonyms_artifact():
    s = _section(7)
    assert "assay_synonyms.json" in s
    assert "formerly Phase 8" in s


def test_no_standalone_phase_4_or_8_sections():
    text = PHASES.read_text()
    assert "\n## Phase 4 " not in text
    assert "\n## Phase 8 " not in text


def test_phase_3_absorbed_the_task_plan_guidance():
    s = _section(3)
    assert "TaskCreate" in s or "task list" in s.lower()


def test_the_verify_flag_is_recorded():
    """The flat-vs-ontology claim is read from a 2026-05-27 API spec."""
    text = PHASES.read_text()
    assert "2026-05-27" in text
    assert "confirm with the nextseek api owner" in text.lower()
