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


def close(root: Path) -> None:
    """Mark the run closed so another may open."""
    current = read(root)
    if not current:
        return
    current["open"] = False
    _write(root, current)
