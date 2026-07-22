"""The /curate-report entry point and its reference doc."""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMAND = REPO / "commands" / "curate-report.md"
DOC = REPO / "skills" / "curation" / "REPORTS.md"


def test_command_exists_with_frontmatter():
    assert COMMAND.exists()
    text = COMMAND.read_text()
    assert text.startswith("---")
    assert "description:" in text.split("---")[1]


def test_command_names_the_three_supported_formats():
    text = COMMAND.read_text()
    for fmt in ("GEO", "SRA", "PRIDE"):
        assert fmt in text


def test_command_excludes_nfcore():
    text = COMMAND.read_text()
    assert "nf-core" in text.lower()
    assert "not this mode" in text.lower() or "out of scope" in text.lower()


def test_command_states_it_runs_without_a_lockfile():
    text = COMMAND.read_text()
    assert "without" in text.lower()
    assert "lockfile" in text.lower()


@pytest.mark.parametrize("rel", [
    "scripts/report/adapters.py",
    "scripts/report/mapping.py",
    "scripts/report/execute.py",
    "scripts/report/render.py",
    "scripts/report/validate_artifact.py",
    "scripts/report/protocols.py",
])
def test_command_references_real_scripts(rel):
    assert rel in COMMAND.read_text()
    assert (REPO / rel).exists()


def test_command_puts_the_llm_only_at_steps_4_and_6():
    text = COMMAND.read_text()
    assert "O(columns)" in text
    assert "not O(rows)" in text


def test_command_forbids_writing_cell_values_directly():
    text = COMMAND.read_text()
    assert "do not write cell values" in text.lower()


def test_doc_is_no_longer_a_stub():
    text = DOC.read_text()
    assert "Status: stub" not in text
    assert "mapping spec" in text.lower()


def test_doc_records_the_5m_token_lesson():
    assert "5.1M-token" in DOC.read_text()


def test_doc_records_that_pride_is_not_a_spreadsheet():
    text = DOC.read_text()
    assert "submission.px" in text
    assert "not a spreadsheet" in text.lower()


def test_doc_states_no_llm_client_is_needed():
    text = DOC.read_text()
    assert "llm_clients.py" in text or "LLM API client" in text


def test_doc_lists_every_adapter():
    text = DOC.read_text()
    for phrase in ("UID", "AllMetadata", "Arm{X}.xlsx", "csv"):
        assert phrase in text


def test_doc_records_the_protocol_gotchas():
    text = DOC.read_text()
    assert "fairdata.mit.edu" in text
    assert "PyPDF2" in text


def test_mode_table_still_matches_after_filling_the_doc():
    skill = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert "REPORTS.md" in skill
