"""Every flag documented in a commands/curate-*.md exists in the script it names.

Mirrors tests/test_fdh_commands_present.py, which does this for FDH only.
Root cause it guards: five documented flags had no corresponding
add_argument() call, so /curate-validate silently ignored RETRIEVE.TXT and
/curate-deposit's documented dry-run default was the opposite of reality.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

# (command file, script path, flags the command doc promises)
CONTRACTS = [
    ("curate-consolidate.md", "scripts/consolidate_to_flat.py",
     ["--assay-sheets", "--all-in-one"]),
    ("curate-qa.md", "scripts/qa_flat_sheets.py",
     ["--upload", "--master-baseline", "--expected-counts"]),
    ("curate-retrieve.md", "scripts/build_retrieve.py",
     ["--assay-sheets", "--output", "--include-parents"]),
    ("curate-validate.md", "scripts/review_metadata_vs_uploads.py",
     ["--retrieve", "--assay-sheets"]),
    ("curate-deposit.md", "scripts/stage_zenodo.py", ["--write"]),
    ("curate-deposit.md", "scripts/apply_zenodo_links.py",
     ["--write", "--record-id"]),
    ("curate-deposit.md", "scripts/apply_geo_accessions.py",
     ["--write", "--gse"]),
    ("curate-deposit.md", "scripts/apply_omero_ids.py",
     ["--write", "--omero-csv"]),
    ("curate-resolve-assays.md", "scripts/nextseek_api.py", ["--project-id"]),
]

_FLAG_RE = re.compile(r'add_argument\(\s*\n?\s*["\'](--[a-z0-9-]+)["\']')


def parsed_flags(script_path: Path) -> set[str]:
    """Return every long flag registered via add_argument() in a script."""
    return set(_FLAG_RE.findall(script_path.read_text()))


@pytest.mark.parametrize("cmd_name,script_rel,flags", CONTRACTS)
def test_documented_flags_exist(cmd_name, script_rel, flags):
    script = REPO / script_rel
    assert script.exists(), f"{script_rel} referenced by {cmd_name} does not exist"
    have = parsed_flags(script)
    missing = [f for f in flags if f not in have]
    assert not missing, (
        f"{cmd_name} documents {missing} but {script_rel} has no such argument. "
        f"Registered flags: {sorted(have)}"
    )


@pytest.mark.parametrize("cmd_name,script_rel,flags", CONTRACTS)
def test_command_doc_mentions_the_script(cmd_name, script_rel, flags):
    doc = (COMMANDS / cmd_name).read_text()
    leaf = Path(script_rel).name
    assert leaf in doc, f"{cmd_name} never names {leaf}"


def test_no_script_offers_a_dry_run_flag():
    """Write-safety convention is --write. --dry-run is forbidden: its ABSENCE
    would imply writing, which is exactly the trap this suite exists to close."""
    offenders = []
    for script in (REPO / "scripts").rglob("*.py"):
        if "--dry-run" in parsed_flags(script):
            offenders.append(script.relative_to(REPO))
    assert not offenders, (
        f"these scripts still use --dry-run instead of --write: {offenders}"
    )


@pytest.mark.parametrize("script_rel", sorted({c[1] for c in CONTRACTS}))
def test_script_help_runs(script_rel):
    result = subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"{script_rel} --help failed: {result.stderr}"
