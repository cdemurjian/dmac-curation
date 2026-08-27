# /// script
# requires-python = ">=3.11"
# ///
"""A dated tarball of the ruling store, verified by reading it back.

WHY VERIFICATION IS PART OF THE FUNCTION. On 2026-08-27 a backup command exited
0 having written a 0-byte file, and only a sanity `ls` caught it. An exit code
describes the call; the archive describes the backup. This opens what it wrote
and asserts the store's files are inside before returning a path anyone treats
as a recovery point.

The stamp is passed in rather than read from the clock so the caller controls
naming and the function stays testable.
"""
from __future__ import annotations

import tarfile
from pathlib import Path

from .rulings import PAIRS_NAME


class BackupUnverified(RuntimeError):
    """The archive does not contain what it was supposed to preserve."""


def back_up(store: Path, backups: Path, stamp: str) -> Path:
    """Write `<backups>/rulings-<stamp>.tar.gz` and prove it holds the store."""
    store, backups = Path(store), Path(backups)
    if not (store / PAIRS_NAME).exists():
        raise BackupUnverified(
            f"nothing to back up: {store / PAIRS_NAME} does not exist. An "
            f"archive of an absent store is an empty file that reports "
            f"success, which is worse than no backup at all.")

    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"rulings-{stamp}.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        archive.add(store, arcname=store.name)

    with tarfile.open(target) as archive:
        names = archive.getnames()
    if not any(n.endswith(PAIRS_NAME) for n in names):
        raise BackupUnverified(
            f"{target} was written but does not contain {PAIRS_NAME}; "
            f"it holds {names}")
    return target
