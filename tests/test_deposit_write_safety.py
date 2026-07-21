"""Deposit scripts must default to dry-run and mutate only under --write."""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

DEPOSIT_SCRIPTS = [
    "scripts/stage_zenodo.py",
    "scripts/apply_zenodo_links.py",
    "scripts/apply_geo_accessions.py",
    "scripts/apply_omero_ids.py",
    # Added post-Task-3: smb_pull.py also had --dry-run, gating a network pull.
    "scripts/smb_pull.py",
]

# Import the hardened detector rather than re-declaring a regex here.
# The naive `add_argument\(\s*["\'](--[a-z0-9-]+)` form FAILS OPEN on a
# short-form-first declaration -- `add_argument("-n", "--dry-run")` parses as
# [] -- which would make this file, where write-safety is the entire subject,
# ship with a guard that silently passes. Task 3's reviewer proved that against
# 13 declaration forms. pytest puts the tests dir on sys.path, so this import
# works without packaging.
from test_curate_commands_present import parsed_flags  # noqa: E402


def _flags(rel: str) -> set[str]:
    return parsed_flags(REPO / rel)


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_has_write_flag(rel):
    assert "--write" in _flags(rel), f"{rel} must expose --write"


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_has_no_dry_run_flag(rel):
    assert "--dry-run" not in _flags(rel), (
        f"{rel} still has --dry-run; its absence implies writing"
    )


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_help_documents_default_is_dry_run(rel):
    result = subprocess.run(
        ["uv", "run", "--script", str(REPO / rel), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "default is dry-run" in result.stdout, (
        f"{rel} --help must state 'default is dry-run' on the --write flag"
    )


def test_command_doc_states_the_write_convention():
    doc = (REPO / "commands" / "curate-deposit.md").read_text()
    assert "--dry-run" not in doc, (
        "curate-deposit.md still documents --dry-run"
    )
    assert "default to dry-run and require `--write`" in doc


def test_zenodo_backfill_flag_matches_its_command_doc():
    """curate-deposit.md:22 documents --record-id; the script had
    --zenodo-record. Renamed so the doc and the CLI agree."""
    flags = _flags("scripts/apply_zenodo_links.py")
    assert "--record-id" in flags
    assert "--zenodo-record" not in flags, (
        "old name still present; a two-name CLI is how drift restarts"
    )


def test_smb_pull_converted_too():
    """smb_pull.py's --dry-run gated an actual network transfer."""
    flags = _flags("scripts/smb_pull.py")
    assert "--write" in flags
    assert "--dry-run" not in flags


def test_no_script_anywhere_still_uses_dry_run():
    """Repo-wide sweep, so a fourth offender cannot hide."""
    offenders = [
        p.relative_to(REPO) for p in (REPO / "scripts").rglob("*.py")
        if "--dry-run" in _flags(str(p.relative_to(REPO)))
    ]
    assert not offenders, f"still using --dry-run: {offenders}"
