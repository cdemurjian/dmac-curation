"""Shared fixtures. The plugin_sentinel fixture is the P1 regression guard:
no script may create, modify, or delete anything inside the plugin checkout.
"""
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Paths that legitimately change during a test run and must not trip the sentinel.
# `.claude/` and `.superpowers/` are agent-tooling scratch: they exist untracked in
# this checkout and may be written to *while* the suite runs. A RED-by-design
# harness must never go red for that reason, so both are ignored.
SENTINEL_IGNORE_PARTS = {
    ".git", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache",
    ".superpowers", ".claude", "working", ".venv",
}

# Marker stored in the snapshot for a directory entry. Directories have no
# content hash, but their *existence* is exactly what several scripts get
# wrong: stage_zenodo.py, smb_pull.py and consolidate_to_flat.py all call
# mkdir(parents=True, exist_ok=True) / os.makedirs() against a path anchored
# at the plugin install dir. An empty directory materialising inside the
# checkout is a P1 symptom, so it must trip the sentinel too.
_DIR_MARKER = "<dir>"


def _snapshot(root: Path) -> dict[str, str]:
    """Map repo-relative path -> sha256 of contents (files) or "<dir>" (dirs)."""
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if SENTINEL_IGNORE_PARTS & set(rel.parts):
            continue
        if p.is_symlink():
            # Don't follow; record the link target so a retarget is caught.
            out[str(rel)] = "<symlink>" + str(p.readlink())
        elif p.is_dir():
            out[str(rel)] = _DIR_MARKER
        elif p.is_file():
            out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _remove_created(root: Path, created: list[str], snap: dict[str, str]) -> None:
    """Delete entries that did not exist when the fixture started.

    The harness is RED by design: some cases genuinely provoke a write into the
    checkout (e.g. nextseek_api.py caching into <plugin>/context/). Leaving that
    artifact behind would dirty the working tree on every run and would sit in
    the *next* test's baseline snapshot, silently masking a repeat offence. Only
    entries absent at setup are removed, so nothing pre-existing can be lost;
    modifications and deletions are reported but left for `git checkout -- .`.
    """
    for rel in sorted(created, key=lambda p: p.count("/"), reverse=True):
        target = root / rel
        try:
            if snap.get(rel) == _DIR_MARKER and target.is_dir():
                target.rmdir()
            elif target.is_symlink() or target.is_file():
                target.unlink()
        except OSError:
            pass  # best-effort; the assertion below still reports the entry


@pytest.fixture
def plugin_sentinel():
    """Fail the test if the plugin checkout changed while it ran."""
    before = _snapshot(REPO)
    yield REPO
    after = _snapshot(REPO)
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])

    def _label(paths, snap):
        return [p + ("/" if snap.get(p) == _DIR_MARKER else "") for p in paths]

    created_labelled = _label(created, after)
    _remove_created(REPO, created, after)

    assert not (created or deleted or modified), (
        "a script wrote inside the plugin checkout:\n"
        f"  created:  {created_labelled}  (removed by the sentinel)\n"
        f"  deleted:  {_label(deleted, before)}\n"
        f"  modified: {_label(modified, after)}"
    )


@pytest.fixture
def curation_project(tmp_path):
    """A minimal curation project: the directory layout plus a v1 lockfile."""
    for d in ("files", "manuscript", "previous_metadata", "assay_sheets",
              "assay_sheets/4sheet_originals", "context", "scripts"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".dmac-curation.json").write_text(json.dumps({
        "schema_version": 1,
        "plugin_version": "0.3.0",
        "modes": {
            "pipeline": {"phase": 5, "lab": "KAM", "nextseek_project_id": 42}
        },
    }, indent=2))
    return tmp_path


# --- the skipped-measurement banner ------------------------------------------
# WHY THIS EXISTS. This package's extract-backed tests are the only thing that
# measures the rework against production data, and they `pytest.skip` when
# `assay-hygiene/extract` is absent -- which is the state of CI and of every
# fresh clone, because the fixtures carry sample identifiers and this repository
# is PUBLIC. A run with all 24 of them skipped therefore reports FULLY GREEN
# while having measured nothing at all.
#
# That is not hypothetical. A "1196 passed / 16 skipped" baseline was read as
# healthy for several days on this project while 21 tests were skipping on a
# missing path. It also hides a DELIVERABLE: the strict-xfail in
# test_assay_hygiene_rulings.py is red on purpose and names the 13 rejected
# cohorts a primary surface still proposes; where it skips, that measurement
# silently ceases to exist.
#
# The skip itself is correct -- you cannot measure without data. What is wrong
# is that it is SILENT. This makes it loud without making it fail, so CI stays
# green for the right reason and a human reading the tail of a local run cannot
# mistake "did not measure" for "measured and found nothing".
_MEASUREMENT_CONVENTION = "_real_extract_"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Announce, at the end of the run, any measurement that did not happen."""
    skipped = terminalreporter.stats.get("skipped", [])
    missed = sorted({r.nodeid for r in skipped
                     if _MEASUREMENT_CONVENTION in getattr(r, "nodeid", "")})
    if not missed:
        return
    tr = terminalreporter
    tr.write_sep("=", "MEASUREMENTS THAT DID NOT RUN", red=True, bold=True)
    tr.write_line(
        f"{len(missed)} extract-backed test(s) skipped. This run did NOT "
        f"measure the rework against production data, and a green result "
        f"above does not mean the measurement passed -- it means it was "
        f"never taken.")
    tr.write_line(
        "  Cause: assay-hygiene/extract is absent (expected on CI and on any "
        "fresh clone; the fixtures carry sample identifiers and are not in "
        "git).")
    tr.write_line(
        "  Hidden by this: test_the_real_extract_drops_every_cohort_the_"
        "operator_rejected is xfail(strict=True) and names 13 cohorts a "
        "primary surface still proposes. Skipped, it reports nothing.")
    for nodeid in missed:
        tr.write_line(f"    - {nodeid}")
