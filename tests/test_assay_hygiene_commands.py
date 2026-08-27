"""Every assay-mode command exists, is addressed, and never writes by default.

Mirrors tests/test_curate_commands_present.py's write-safety direction: no
command doc may instruct an operator to pass --dry-run, because its absence
would imply writing.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

EXPECTED = ["curate-assay-init.md", "curate-assay-vocabulary.md",
            "curate-assay-detect.md", "curate-assay-review.md",
            "curate-assay-resolve.md", "curate-assay-write.md",
            "curate-assay-status.md", "curate-assay-backup.md"]


@pytest.mark.parametrize("name", EXPECTED)
def test_the_command_exists(name):
    assert (COMMANDS / name).is_file()


@pytest.mark.parametrize("name", EXPECTED)
def test_the_command_has_a_description(name):
    text = (COMMANDS / name).read_text()
    assert text.startswith("---\n"), "needs YAML frontmatter"
    front = text.split("---", 2)[1]
    assert "description:" in front


@pytest.mark.parametrize("name", EXPECTED)
def test_no_command_instructs_a_dry_run_flag(name):
    assert "--dry-run" not in (COMMANDS / name).read_text()


def test_the_write_command_names_confirm_and_every_refusal():
    text = (COMMANDS / "curate-assay-write.md").read_text()
    assert "--confirm" in text, "writing must be opt-in"
    for phrase in ("rollback", "backup", "manifest", "chunk"):
        assert phrase in text.lower(), f"write doc does not mention {phrase}"


def test_the_init_command_names_the_restore_path():
    text = (COMMANDS / "curate-assay-init.md").read_text()
    assert "tar" in text and "backup" in text.lower()


def test_no_assay_command_tells_the_operator_to_omit_out_dir():
    """The clobbering hazard: run_evidence with no out_dir writes through
    the symlink tree into the preserved baseline."""
    for name in EXPECTED:
        text = (COMMANDS / name).read_text()
        for line in text.splitlines():
            if "assay_hygiene.run_evidence" in line or "assay_hygiene.run_detect" in line:
                assert "RUN" in line or "out" in line or line.rstrip().endswith("\\"), (
                    f"{name} invokes a driver with no output directory: {line!r}")
