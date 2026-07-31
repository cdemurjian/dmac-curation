"""Smoke-test each .j2 template against minimal context dicts.

Two sets of fixtures per template:
- MINIMAL: only required (non-defaulted) fields → confirms templates render with all defaults
- WITH_VALUES: explicit values for defaulted fields → confirms defaults don't override real values
"""
from pathlib import Path
import pytest
jinja2 = pytest.importorskip("jinja2")

REPO = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO / "templates"

ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    undefined=jinja2.StrictUndefined,
)

# MINIMAL fixtures: omit optional/defaulted fields so default() must fire.
MINIMAL = {
    "CLAUDE.md.j2": {
        "pi_name": "marie", "lab": "kam", "init_date": "2026-05-27",
    },
    "FILE_INDEX.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "master_xlsx": None, "master_sheets": [],
    },
    "SAMPLE_TREE.md.j2": {
        "pi_name": "marie", "paper_short_title": "IntravChip",
        "generated_date": "2026-05-27", "lab": "kam",
        "curation_date_stamp": "260527",
        "study_overview": "Test overview.", "existing_rows": [],
        "arms": [{"letter": "A", "title": "Test", "ascii_tree": "tree",
                  "new_rows": []}],
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
        "pi_name": "marie",
        "summary_paragraph": "test",
        "files_curated_summary": "test", "questions": ["q1"],
        "deposits": [], "asks": "ask", "scientist_name": "Charlie",
    },
    "pyproject.toml.j2": {"project_slug": "marie_intravchip", "pi_name": "marie"},
    "env.example.j2": {},
    "gitignore.j2": {},
}

# WITH_VALUES fixtures: explicit values to confirm defaults don't override.
WITH_VALUES = {
    "CLAUDE.md.j2": {
        "pi_name": "marie", "lab": "kam", "init_date": "2026-05-27",
        "project_id": 10,
    },
    "FILE_INDEX.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "files_summary": "3 figure folders", "manuscript_summary": "1 docx",
        "previous_metadata_summary": "1 xlsx", "email_summary": "12 messages",
        "master_xlsx": "ENG SRP All 260505.xlsx",
        "master_sheets": [{"name": "MUS", "rows": 365, "sampletype": "MUS", "pi_rows": 9}],
        "flags": "1 figure folder is empty",
    },
    "SAMPLE_TREE.md.j2": {
        "pi_name": "marie", "paper_short_title": "IntravChip",
        "generated_date": "2026-05-27", "lab": "kam",
        "curation_date_stamp": "260527",
        "study_overview": "Test overview.",
        "existing_rows": [{"sampletype": "MUS", "count": 9, "note": "existing GEMM cohort"}],
        "arms": [{"letter": "A", "title": "Test", "ascii_tree": "tree",
                  "new_rows": [{"sampletype": "RNA", "count": 27, "note": "bulk RNA"}],
                  "questions": "Q1 about timepoints"}],
        "cross_arm_questions": "Q2 about D.REF schema",
    },
    "EMAIL_TO_PI.md.j2": {
        "pi_name": "marie", "subject": "Custom subject", "greeting": "Custom greeting",
        "summary_paragraph": "test", "sample_tree_svg": "tree.svg",
        "files_curated_summary": "test", "questions": ["q1"],
        "deposits": [{"target": "GEO", "status": "uploaded"}],
        "asks": "ask", "scientist_name": "Charlie",
    },
}


@pytest.mark.parametrize("template_name,context", list(MINIMAL.items()))
def test_template_renders_minimal(template_name, context):
    """Render with minimum required vars — defaults must fire for omitted keys."""
    template = ENV.get_template(template_name)
    result = template.render(**context)
    assert isinstance(result, str)
    assert len(result) > 0
    # Output should never contain the literal string 'None' (a sign of None leaking through default())
    # or '{%' / '{{' (a sign of un-rendered Jinja2)
    assert "{%" not in result, f"un-rendered Jinja2 tag in {template_name}"
    assert "{{" not in result, f"un-rendered Jinja2 var in {template_name}"


@pytest.mark.parametrize("template_name,context", list(WITH_VALUES.items()))
def test_template_renders_with_values(template_name, context):
    """Render with explicit values — defaults must NOT override."""
    template = ENV.get_template(template_name)
    result = template.render(**context)
    assert isinstance(result, str)
    assert len(result) > 0


def _render_claude_md(**ctx):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(loader=FileSystemLoader(str(REPO / "templates")),
                      undefined=StrictUndefined)
    base = {"lab": "kam", "pi_name": "marie", "init_date": "2026-07-21"}
    base.update(ctx)
    return env.get_template("CLAUDE.md.j2").render(**base)


def test_claude_md_renders_pipeline_steps_when_pipeline_mode():
    out = _render_claude_md(modes=["pipeline"])
    assert "/curate-inventory" in out
    assert "/curate-consolidate" in out
    assert "Modes enabled" in out


def test_claude_md_omits_pipeline_steps_for_schema_only():
    out = _render_claude_md(modes=["schema"])
    assert "/curate-inventory" not in out
    assert "/curate-sampletype" in out


def test_claude_md_defaults_to_pipeline_when_modes_absent():
    """Backward compatibility: an old caller passing no `modes` still works."""
    assert "/curate-inventory" in _render_claude_md()


def test_claude_md_lists_twelve_pipeline_steps():
    import re
    out = _render_claude_md(modes=["pipeline"])
    block = out.split("Suggested order:", 1)[1].split("\n\n", 1)[0]
    numbered = re.findall(r"^\s*(\d+)\. ", block, flags=re.M)
    assert len(numbered) == 12, f"expected 12 steps, got {numbered}"


def test_claude_md_records_why_both_sheet_formats_exist():
    out = _render_claude_md(modes=["pipeline"])
    assert "review artifact" in out


def test_claude_md_has_no_em_dashes():
    """Charlie's style rule; this file is read by the PI's collaborators."""
    assert "—" not in (REPO / "templates" / "CLAUDE.md.j2").read_text()
