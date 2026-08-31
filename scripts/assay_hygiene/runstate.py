# /// script
# requires-python = ">=3.11"
# ///
"""Which run is open, what step it is on, and whether anyone else holds one.

WHY A SECOND FILE RATHER THAN `scripts/_lockfile.py`. That one is keyed to a
project directory and its `mode()` helper assumes a project lockfile. Assay
hygiene is house-scoped -- one extract, all projects, no PI -- so its state
lives at the runs root instead.

ONE RUN AT A TIME IS A SAFETY PROPERTY, NOT TIDINESS. Primary keys in the write
path are MAX(id)+1 computed in Python with no lock. A concurrent insert makes
Django's explicit-pk save() perform UPDATE-then-INSERT and silently overwrite
the other writer's row, with both callers told they succeeded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

LOCK_NAME = "assay-run.json"
SCHEMA_VERSION = 1


class RunLocked(RuntimeError):
    """A run is already open, or none is and one was expected."""


def _path(root: Path) -> Path:
    return Path(root) / LOCK_NAME


def read(root: Path) -> dict:
    """-> the lockfile, or {} when absent. Never raises on absence."""
    path = _path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write(root: Path, data: dict) -> dict:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def create(root: Path, run: int, extract_sha: str) -> dict:
    """Open a run. Refuses while another is open."""
    current = read(root)
    if current and current.get("open"):
        raise RunLocked(
            f"run {current['run']} is still open (pid {current.get('pid')}). "
            f"Close it before opening run {run}: two concurrent write phases "
            f"can silently overwrite each other's rows.")
    return _write(root, {
        "schema_version": SCHEMA_VERSION,
        "run": run,
        "open": True,
        "pid": os.getpid(),
        "extract_sha": extract_sha,
        "step": "init",
        "rulings_ingested": {},
        "carried_from_run": None,
        "carried_pairs": 0,
        "write": {"chunks_done": 0, "rollback_id": None,
                  "backup_verified": False},
    })


def update(root: Path, **fields) -> dict:
    """Merge `fields` into the open run. Refuses when none is open.

    NESTED DICTS MERGE ONE LEVEL rather than being replaced. `write` carries
    three independent facts -- chunks_done, rollback_id, backup_verified --
    recorded at three different moments by three different steps. A plain
    `dict.update` lets `update(root, write={"rollback_id": n})` silently drop
    the other two, and the one most often dropped is backup_verified, whose
    absence preflight reads as "no backup at all".
    """
    current = read(root)
    if not current or not current.get("open"):
        raise RunLocked("no run is open; `curate-assay-init` opens one.")
    for key, value in fields.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key] = {**current[key], **value}
        else:
            current[key] = value
    return _write(root, current)


def reopen(root: Path, run: int) -> dict:
    """Resume a run that was closed before it finished. -> the lockfile.

    WHY THIS EXISTS. `close` is called to release the lock -- RUN2 was closed at
    `resolve` precisely so a fresh `init` would not hit it -- and `create`
    allocates a NEW run number and refuses while anything is open. Between them
    there was no way back into an existing run, so finishing one meant editing
    the lockfile by hand: the single file whose entire job is to be the thing
    nobody edits by hand.

    THE RUN NUMBER IS AN ARGUMENT AND NOT A LOOKUP. Reopening whatever the
    lockfile happens to hold is how a session resumes RUN2 believing it is
    RUN3, and re-submits rows that are already in production. Naming it is how
    the caller proves which run it means.

    IT DOES NOT TOUCH `step`. The run resumes where it stopped; rewinding it
    would re-run a stage whose output is already on disk and, at `write`,
    already in the database.
    """
    current = read(root)
    if not current:
        raise RunLocked(
            f"no run has been opened under {root}; there is nothing to reopen. "
            f"`curate-assay-init` opens run {run}.")
    # THE LIVE LOCK IS REPORTED FIRST. When a different run is open, both facts
    # are true and only one of them is dangerous: a second write phase against
    # an open run is the MAX(id)+1 overwrite this lockfile exists to prevent.
    if current.get("open") and current["run"] != run:
        raise RunLocked(
            f"run {current['run']} is still open (pid {current.get('pid')}). "
            f"Close it before resuming run {run}: two concurrent write phases "
            f"can silently overwrite each other's rows.")
    if current["run"] != run:
        raise RunLocked(
            f"the lockfile holds run {current['run']}, not run {run}. Reopening "
            f"a run you have misidentified re-submits its rows; check "
            f"`curate-assay-status` before resuming.")
    if current.get("open"):
        return current
    # RE-STAMPED, because the closed run's pid belongs to a process that has
    # since exited and `create`'s refusal quotes it back at the next caller.
    current["open"] = True
    current["pid"] = os.getpid()
    return _write(root, current)


def close(root: Path) -> None:
    """Mark the run closed so another may open."""
    current = read(root)
    if not current:
        return
    current["open"] = False
    _write(root, current)
