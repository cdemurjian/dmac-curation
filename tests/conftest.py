"""Shared fixtures. The plugin_sentinel fixture is the P1 regression guard:
no script may create, modify, or delete anything inside the plugin checkout.
"""
import hashlib
import json
from pathlib import Path

import pathlib

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
# Matches `real_extract` ANYWHERE in a nodeid. The earlier `_real_extract_`
# required delimiting underscores on both sides and so could not see the two
# tests ending `..._on_the_real_extract`, nor any `skipif` that does not follow
# the naming convention -- 13 of 40 skips on a fresh clone. A guard whose job
# is to report unmeasured work must not itself under-report.
_MEASUREMENT_CONVENTION = "real_extract"


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


# --- NO TEST READS PRODUCTION DATA. EVER. ------------------------------------
#
# WHY THIS IS A HARD BLOCK AND NOT A CONVENTION. The extract tiers under
# `assets/RUN*/` hold real production dumps -- 166k-row `samples`, 802k-row
# `edges`, a 106MB `findings.csv`. Loading them inside a test run twice drove
# this machine into the OOM killer and forced a restart on 2026-09-01. The
# suite is SERIAL (no xdist, one core of sixteen), so this was never a CPU
# problem and no CPU cap would have helped: it is resident memory, on a box
# that is routinely at 26 of 30 GB before pytest starts.
#
# A naming convention could not hold this. `..._real_extract_...` catches the
# tests someone remembered to name that way; this catches the path, so a new
# test cannot reintroduce the hazard by being called something else.
#
# The ruling store (`assets/rulings/`) is deliberately NOT blocked: it is a few
# hundred rows of human judgement, not a production dump, and it is what the
# store-integrity tests exist to check.
PRODUCTION_TIERS = ("01-extract", "04-artifacts", "06-findings",
                    "08-extract-post-write", "09-relabel")


def _is_production_data(path) -> bool:
    try:
        parts = pathlib.Path(str(path)).resolve().parts
    except (TypeError, ValueError, OSError):
        return False
    return any(tier in parts for tier in PRODUCTION_TIERS)


@pytest.fixture(autouse=True)
def _no_production_data_in_tests(monkeypatch):
    """Refuse a read of any production extract tier, before it allocates."""
    import pandas as pd

    for name in ("read_parquet", "read_csv", "read_excel"):
        real = getattr(pd, name)

        def guarded(path, *args, _real=real, _name=name, **kwargs):
            if _is_production_data(path):
                raise RuntimeError(
                    f"pd.{_name}({path!r}) reads a production extract tier. "
                    "Tests must not load production data: it is hundreds of "
                    "megabytes resident and has OOM-killed this machine. Build "
                    "a synthetic frame of the shape you need instead -- the "
                    "shapes are documented in `assay_hygiene._schema`.")
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(pd, name, guarded)
