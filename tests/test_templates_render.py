"""Smoke-test each .j2 template against a minimal context dict."""
from pathlib import Path
import pytest
jinja2 = pytest.importorskip("jinja2")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    undefined=jinja2.StrictUndefined,
)

FIXTURES = {
    "CLAUDE.md.j2": {
        "pi_name": "marie", "lab": "kam", "init_date": "2026-05-27",
        "project_id": None,
    },
    "FILE_INDEX.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "files_summary": None, "manuscript_summary": None,
        "previous_metadata_summary": None, "email_summary": None,
        "master_xlsx": None, "master_sheets": [], "flags": None,
    },
    "SAMPLE_TREE.md.j2": {
        "pi_name": "marie", "paper_short_title": "IntravChip",
        "generated_date": "2026-05-27", "lab": "kam",
        "curation_date_stamp": "260527",
        "study_overview": "Test overview.", "existing_rows": [],
        "arms": [{"letter": "A", "title": "Test", "ascii_tree": "tree",
                  "new_rows": [], "questions": None}],
        "cross_arm_questions": None,
    },
    "QUESTIONS_FOR_PI.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "open_questions": [], "resolved_questions": [],
    },
    "CURATION_PLAN.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "goal": "test", "scope": "test", "arms": [], "deposits": [],
    },
    "EMAIL_TO_PI.md.j2": {
        "pi_name": "marie", "subject": None, "greeting": None,
        "summary_paragraph": "test", "sample_tree_svg": None,
        "files_curated_summary": "test", "questions": ["q1"],
        "deposits": [], "asks": "ask", "scientist_name": "Charlie",
    },
    "pyproject.toml.j2": {"project_slug": "marie_intravchip", "pi_name": "marie"},
    "env.example.j2": {},
    "gitignore.j2": {},
}

@pytest.mark.parametrize("template_name,context", list(FIXTURES.items()))
def test_template_renders(template_name, context):
    template = ENV.get_template(template_name)
    result = template.render(**context)
    assert isinstance(result, str)
    assert len(result) > 0
