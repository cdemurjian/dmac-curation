# /// script
# requires-python = ">=3.11"
# ///
"""Make a completed run read-only, and check that it is.

WHY. `assets/RUN1/README.md` and three source files state that the first four
tiers of a run are `chmod a-w`. No code applied it. The tiers that are in fact
read-only are the ones the pipeline never writes to, so the protection that
exists protects nothing and the protection that matters was never there.

Directories are set to 0o555 rather than files alone, because a writable
directory accepts a NEW file even when every existing file is read-only -- and
an artifact appearing beside the baseline is the symptom this is meant to stop.
"""
from __future__ import annotations

import stat
from collections.abc import Iterable
from pathlib import Path

DIR_MODE = 0o555
FILE_MODE = 0o444


def protect(run_dir: Path, tiers: Iterable[str]) -> list[Path]:
    """-> the paths whose mode this call actually changed."""
    changed: list[Path] = []
    for tier in tiers:
        base = Path(run_dir) / tier
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*"), reverse=True):
            want = DIR_MODE if path.is_dir() else FILE_MODE
            if stat.S_IMODE(path.stat().st_mode) != want:
                path.chmod(want); changed.append(path)
        if stat.S_IMODE(base.stat().st_mode) != DIR_MODE:
            base.chmod(DIR_MODE); changed.append(base)
    return changed


def verify(run_dir: Path, tiers: Iterable[str]) -> list[Path]:
    """-> the tiers that are NOT protected. Empty means every tier is."""
    bad: list[Path] = []
    for tier in tiers:
        base = Path(run_dir) / tier
        if base.is_dir() and (stat.S_IMODE(base.stat().st_mode) & stat.S_IWUSR):
            bad.append(base)
    return bad
