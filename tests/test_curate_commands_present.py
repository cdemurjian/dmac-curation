"""Contract tests binding `commands/curate-*.md` to the scripts they invoke.

Mirrors tests/test_fdh_commands_present.py, which does this for FDH only.

This file asserts four distinct things, kept in separate tables so a reader can
always tell a *drift bug* from a *planned addition*:

1. `CONTRACTS` -- flags a command doc promises **today**. A failure here is a
   real drift bug: an operator following the doc would pass a flag the script
   does not accept. (Root cause: `/curate-validate` documents `--metadata` and
   `--retrieve`; the script has `--metadata-xlsx` and no retrieve support at
   all, so RETRIEVE.TXT was silently ignored.)
2. `PLANNED_CONTRACTS` -- flags no doc promises yet, that a **named task** in
   docs/superpowers/plans/2026-07-21-curation-toolkit.md will add. These are
   RED on purpose until that task lands; each row carries its owning task.
3. `UNDOCUMENTED_BUT_PRESENT` -- flags that exist in a script but that no doc
   mentions. Green today; a regression guard only. Drift in this direction is
   under-documentation, not a broken instruction, so it is tracked separately.
4. Write-safety direction: no script may register `--dry-run` (its ABSENCE
   would imply writing) and no command doc may instruct an operator to pass
   `--dry-run`. Both halves are needed -- flipping only the scripts leaves the
   docs telling operators to pass a flag that no longer exists.

The suite is expected to be RED until Tasks 4, 5, 8 and 17 land.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

# (command file, script path, flags the command doc names TODAY)
CONTRACTS = [
    ("curate-consolidate.md", "scripts/consolidate_to_flat.py",
     ["--assay-sheets", "--all-in-one"]),
    # curate-qa.md documents no flags at all; see PLANNED_CONTRACTS.
    ("curate-qa.md", "scripts/qa_flat_sheets.py", []),
    ("curate-retrieve.md", "scripts/build_retrieve.py", ["--include-parents"]),
    ("curate-validate.md", "scripts/review_metadata_vs_uploads.py",
     ["--metadata", "--retrieve"]),
    # curate-deposit.md:20 still says `stage_zenodo.py --dry-run`; --write is
    # target state, so it lives in PLANNED_CONTRACTS.
    ("curate-deposit.md", "scripts/stage_zenodo.py", []),
    ("curate-deposit.md", "scripts/apply_zenodo_links.py",
     ["--write", "--record-id"]),
    ("curate-deposit.md", "scripts/apply_geo_accessions.py",
     ["--write", "--gse"]),
    ("curate-deposit.md", "scripts/apply_omero_ids.py", ["--write"]),
    ("curate-resolve-assays.md", "scripts/nextseek_api.py", ["--project-id"]),
]

# (command file, script path, flag, owning task) -- not promised by any doc
# today; the named task adds it. RED until that task lands.
PLANNED_CONTRACTS = [
    ("curate-qa.md", "scripts/qa_flat_sheets.py", "--upload", 8),
    ("curate-qa.md", "scripts/qa_flat_sheets.py", "--master-baseline", 8),
    ("curate-qa.md", "scripts/qa_flat_sheets.py", "--expected-counts", 8),
    ("curate-validate.md", "scripts/review_metadata_vs_uploads.py",
     "--assay-sheets", 8),
    ("curate-deposit.md", "scripts/stage_zenodo.py", "--write", 4),
]

# (script path, flag) -- exists in the script, named by no doc. Green today.
UNDOCUMENTED_BUT_PRESENT = [
    ("scripts/build_retrieve.py", "--assay-sheets"),
    ("scripts/build_retrieve.py", "--output"),
    ("scripts/apply_omero_ids.py", "--omero-csv"),
]

DOC_SCRIPT_PAIRS = sorted(
    {(c[0], c[1]) for c in CONTRACTS}
    | {(p[0], p[1]) for p in PLANNED_CONTRACTS}
)
ALL_SCRIPTS = sorted(
    {c[1] for c in CONTRACTS}
    | {p[1] for p in PLANNED_CONTRACTS}
    | {u[0] for u in UNDOCUMENTED_BUT_PRESENT}
)

# Captures the long option even when short forms precede it, e.g.
# add_argument("-n", "--dry-run", ...). Underscores count, so --dry_run is
# caught too. \s* spans newlines, so wrapped calls are covered.
_FLAG_RE = re.compile(
    r'add_argument\(\s*(?:["\']-{1,2}[\w-]+["\']\s*,\s*)*["\'](--[\w-]+)["\']'
)


def parsed_flags(script_path: Path) -> set[str]:
    """Return every long flag registered via add_argument() in a script."""
    return set(_FLAG_RE.findall(script_path.read_text()))


def test_parsed_flags_detects_long_option_after_short_form(tmp_path):
    """Regression guard on the detector itself.

    The first version of this regex only matched when the long flag was the
    first string literal in the call, so `add_argument("-n", "--dry-run")`
    parsed as `[]`. For a CONTRACTS row a miss is a harmless false RED, but
    for test_no_script_offers_a_dry_run_flag a miss is a false GREEN -- the
    detector is the only thing standing between the repo and a write-by-default
    flag, so it must not be defeatable by declaration style.
    """
    snippet = tmp_path / "sample.py"
    snippet.write_text(
        'p.add_argument("-n", "--dry-run", action="store_true")\n'
        'p.add_argument("--write", action="store_true")\n'
        'p.add_argument(\n'
        '    "-o", "--output", default="OUT",\n'
        ')\n'
        'p.add_argument("--dry_run")\n'
    )
    assert parsed_flags(snippet) == {
        "--dry-run", "--write", "--output", "--dry_run"}


@pytest.mark.parametrize("cmd_name,script_rel,flags", CONTRACTS)
def test_documented_flags_exist(cmd_name, script_rel, flags):
    """Every flag a command doc names today must exist in the script."""
    script = REPO / script_rel
    assert script.exists(), f"{script_rel} referenced by {cmd_name} does not exist"
    have = parsed_flags(script)
    missing = [f for f in flags if f not in have]
    assert not missing, (
        f"{cmd_name} documents {missing} but {script_rel} has no such argument. "
        f"Registered flags: {sorted(have)}"
    )


@pytest.mark.parametrize("cmd_name,script_rel,flag,task", PLANNED_CONTRACTS)
def test_planned_flags_exist(cmd_name, script_rel, flag, task):
    """Flags a named task will add. RED until that task lands -- by design."""
    have = parsed_flags(REPO / script_rel)
    assert flag in have, (
        f"{script_rel} has no {flag}; Task {task} adds it (for {cmd_name}). "
        f"Registered flags: {sorted(have)}"
    )


@pytest.mark.parametrize("script_rel,flag", UNDOCUMENTED_BUT_PRESENT)
def test_undocumented_but_present_flags_are_not_removed(script_rel, flag):
    """These exist but no doc names them. Guard against silent removal."""
    have = parsed_flags(REPO / script_rel)
    assert flag in have, (
        f"{script_rel} lost {flag}; it was present and callers may rely on it. "
        f"Registered flags: {sorted(have)}"
    )


@pytest.mark.parametrize("cmd_name,script_rel", DOC_SCRIPT_PAIRS)
def test_command_doc_mentions_the_script(cmd_name, script_rel):
    """Assert the full relative path, matching test_fdh_commands_present.py:29.

    Matching only the filename leaf would not notice a directory move.
    """
    doc = (COMMANDS / cmd_name).read_text()
    assert script_rel in doc, f"{cmd_name} never names {script_rel}"


def test_no_script_offers_a_dry_run_flag():
    """Write-safety convention is --write. --dry-run is forbidden: its ABSENCE
    would imply writing, which is exactly the trap this suite exists to close.

    Belt and braces: check the parsed flags AND the raw source text, so a
    declaration form parsed_flags() does not model cannot smuggle one in.
    """
    offenders = []
    for script in sorted((REPO / "scripts").rglob("*.py")):
        text = script.read_text()
        flags = parsed_flags(script)
        if ({"--dry-run", "--dry_run"} & flags
                or '"--dry-run"' in text or "'--dry-run'" in text
                or '"--dry_run"' in text or "'--dry_run'" in text):
            offenders.append(str(script.relative_to(REPO)))
    assert not offenders, (
        f"these scripts still use --dry-run instead of --write: {offenders}"
    )


def test_no_command_doc_instructs_dry_run():
    """The doc half of the same convention.

    Flipping the scripts to --write without flipping the docs leaves
    commands/curate-deposit.md:20 telling an operator to run
    `stage_zenodo.py --dry-run` -- a flag that would no longer exist. That is
    precisely the drift this suite claims to close, so guard both directions.
    """
    offenders = []
    for doc in sorted(COMMANDS.glob("*.md")):
        text = doc.read_text()
        hits = [ln for ln, line in enumerate(text.splitlines(), 1)
                if "--dry-run" in line or "--dry_run" in line]
        if hits:
            offenders.append(f"{doc.name}:{','.join(map(str, hits))}")
    assert not offenders, (
        f"these command docs still tell operators about --dry-run: {offenders}"
    )


@pytest.mark.parametrize("script_rel", ALL_SCRIPTS)
def test_script_help_runs(script_rel):
    result = subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"{script_rel} --help failed: {result.stderr}"
