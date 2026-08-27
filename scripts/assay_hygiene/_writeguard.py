# /// script
# requires-python = ">=3.11"
# ///
"""Refuse to write through a symlink into a preserved run.

WHY THIS EXISTS. `run_evidence.main` and `run_detect.main` default
`out_dir="assay-hygiene"`, and that directory is 33 symlinks into
`assets/RUN1/`. Writing `findings.csv` there follows the link and destroys the
baseline every before/after measurement in this package is compared against.
Four separate files claimed `chmod a-w` protected this; nothing applied it, and
the tiers that ARE read-only are the ones the pipeline never writes to.

This raises rather than warns because the caller's next act is a write, and a
warning attached to a destroyed baseline is not a warning.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class SymlinkWriteRefused(RuntimeError):
    """A write would have followed a symlink out of `out_dir`."""


def assert_writable(out: Path, names: Iterable[str]) -> None:
    """Raise unless every `name` under `out` can be written without following a link."""
    out = Path(out)
    offenders: list[str] = []
    if out.is_symlink():
        offenders.append(f"{out}/ (the output directory itself) -> {out.readlink()}")
    else:
        for name in names:
            target = out / name
            if target.is_symlink():
                offenders.append(f"{target} -> {target.readlink()}")
    if offenders:
        raise SymlinkWriteRefused(
            "refusing to write through a symlink; this would overwrite a "
            "preserved artifact rather than create a file. Pass an out_dir "
            "that is a real directory:\n  " + "\n  ".join(offenders))
