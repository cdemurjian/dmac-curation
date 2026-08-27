"""SKILL.md's mode table must match the reference docs actually present.

Toolkit spec O4: the naive version of this test globs SKILL.md itself.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CURATION = REPO / "skills" / "curation"
SKILL = CURATION / "SKILL.md"

EXPECTED_MODES = {
    "pipeline": "PHASES.md",
    "fdh": "FDH.md",
    "schema": "SCHEMA.md",
    "report": "REPORTS.md",
    "assay": "ASSAY.md",
}


def reference_docs() -> set[str]:
    return {p.name for p in CURATION.glob("*.md") if p.name != "SKILL.md"}


def mode_table_rows() -> dict[str, dict[str, str]]:
    """Parse the '## Modes' markdown table into {mode: {column: value}}."""
    parts = SKILL.read_text().split("## Modes", 1)
    assert len(parts) == 2, "SKILL.md has no '## Modes' section"
    body = parts[1].split("\n##", 1)[0]
    rows = [l for l in body.splitlines() if l.strip().startswith("|")]
    assert len(rows) >= 3, "mode table needs a header, a separator and rows"
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    out = {}
    for line in rows[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        record = dict(zip(header, cells))
        out[record["mode"].strip("`")] = record
    return out


def test_every_reference_doc_exists():
    assert not set(EXPECTED_MODES.values()) - reference_docs()


def test_mode_table_lists_exactly_the_reference_docs():
    listed = {r["reference"].strip("`") for r in mode_table_rows().values()}
    assert listed == reference_docs(), (
        f"mode table lists {listed}, but skills/curation/ has {reference_docs()} "
        f"(excluding SKILL.md)"
    )


def test_mode_table_has_every_mode():
    assert set(mode_table_rows()) == set(EXPECTED_MODES)


@pytest.mark.parametrize("mode,doc", sorted(EXPECTED_MODES.items()))
def test_each_mode_points_at_its_doc(mode, doc):
    assert mode_table_rows()[mode]["reference"].strip("`") == doc


def test_mode_table_declares_state_scope():
    rows = mode_table_rows()
    assert "project" in rows["pipeline"]["state scope"]
    assert "cwd" in rows["schema"]["state scope"]
    assert "input" in rows["report"]["state scope"]


def test_skill_md_no_longer_carries_the_phase_table():
    text = SKILL.read_text()
    assert "| 0 | Init |" not in text, "the phase table belongs in PHASES.md now"
    assert "13-phase pipeline" not in text


def test_phases_md_carries_the_phase_table():
    assert "| 0 | Init |" in (CURATION / "PHASES.md").read_text()


def _phase_table_labels():
    """-> the first-column labels of the PHASES.md phase table, in order.

    Labels, not ints: phase 9 appears as the two rows `9a` (local QA) and `9b`
    (server-side QC), which is why this cannot be an `isdigit()` filter.
    """
    text = (CURATION / "PHASES.md").read_text()
    table = text.split("## Phase table", 1)[1].split("\n---", 1)[0]
    rows = [l for l in table.splitlines() if l.strip().startswith("|")]
    labels = []
    for line in rows[2:]:
        first = line.strip("|").split("|")[0].strip()
        if first and first[0].isdigit():
            labels.append(first)
    return labels


def test_phase_table_omits_deleted_phases():
    """Phases 4 and 8 are retired as numbers in Task 16."""
    labels = _phase_table_labels()
    numbers = {int("".join(c for c in l if c.isdigit())) for l in labels}
    assert 4 not in numbers, "Phase 4 (task plan) is retired"
    assert 8 not in numbers, "Phase 8 (synonyms) is folded into Phase 7"
    assert len(numbers) == 11, f"expected 11 phase numbers, got {sorted(numbers)}"


def test_phase_table_carries_the_9a_9b_split():
    """9b is the last gate before upload; a table without it hides that.

    `/curate-qa` is entirely local and `/curate-qc` is the only thing that asks
    the live server. The table listed a single undifferentiated `9` for both,
    so the phase a curator most needs to run was absent from the roster.
    """
    labels = _phase_table_labels()
    assert "9a" in labels and "9b" in labels, labels
    assert "9" not in labels, "9 is split; it should not also appear undifferentiated"
    assert len(labels) == 12, f"12 phases across 11 numbers, got {labels}"


def test_fdh_is_no_longer_disclaimed_as_not_part_of_the_pipeline():
    """FDH was bolted on with a disclaimer because the pipeline was the only
    organising principle. It is a mode now."""
    assert "NOT part of the 13-phase pipeline" not in SKILL.read_text()


def test_no_doc_or_command_claims_thirteen_phases():
    """The ban was scoped to SKILL.md, so the phrase survived everywhere else.

    It outlived the retirement of phases 4 and 8 in FDH.md and
    commands/fdh-upload.md for two releases because no test looked there.
    """
    targets = sorted(CURATION.glob("*.md")) + sorted((CURATION.parent.parent / "commands").glob("*.md"))
    offenders = [p.name for p in targets if "13-phase" in p.read_text()]
    assert not offenders, f"'13-phase' is stale; found in {offenders}"


def test_vocabulary_section_covers_the_new_modes():
    text = SKILL.read_text()
    for phrase in ("bolster", "sample type", "GEO", "SRA", "PRIDE"):
        assert phrase in text, f"vocabulary section should mention {phrase!r}"
