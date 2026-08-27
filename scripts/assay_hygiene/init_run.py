# /// script
# requires-python = ">=3.11"
# ///
"""Open a run, having first proved the campaign's judgement still exists.

WHY THIS REFUSES RATHER THAN WARNS. Keeping rulings out of a PUBLIC repository
means their only protection is a backup on one machine. That is a real,
recorded limit -- a lost machine is a lost curation campaign -- and the one
thing that makes the backup load-bearing rather than decorative is that
something checks for it before a run starts. A warning above a fresh empty run
is a warning nobody reads.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .migrate_rulings import conflicts, migrate
from .protect_run import protect
from .rulings import PAIRS_NAME, save

TIERS = ("00-rulings", "01-extract", "02-agent-runs", "03-stage0-applied",
         "04-artifacts", "05-review", "06-findings", "07-process")
PROTECTED = TIERS[:-1]

_RUN_DIR = re.compile(r"^RUN(\d+)$")


class MissingRulingStore(RuntimeError):
    """No ruling store. Restore it before starting a run."""


def require_store(store: Path, backups: Path) -> None:
    """Raise unless `store` holds a pairs file."""
    store, backups = Path(store), Path(backups)
    if (store / PAIRS_NAME).exists():
        return
    raise MissingRulingStore(
        f"no ruling store at {store}/{PAIRS_NAME}.\n"
        f"NOTHING REGENERATES A HUMAN RULING -- not compute, not a re-run. If "
        f"this is not the very first run, judgement is missing and the run "
        f"must not start.\n"
        f"Restore the most recent backup from {backups}:\n"
        f"  tar -xzf {backups}/<newest>.tar.gz -C {store.parent}\n"
        f"If this genuinely IS the first run, create the store by migrating an "
        f"existing run: `curate-assay-init --migrate-from assets/RUN1`.")


def next_run_number(runs_root: Path) -> int:
    """-> one past the highest RUN<n> present. A fresh tree starts at 1."""
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return 1
    found = [int(m.group(1)) for m in
             (_RUN_DIR.match(p.name) for p in runs_root.iterdir() if p.is_dir())
             if m]
    return max(found, default=0) + 1


def create_run(runs_root: Path, run: int) -> Path:
    """Make RUN<n> with every tier, then protect all but `07-process`.

    PROTECTION IS APPLIED AT CREATION, not at the end of a run. A tier that is
    writable for the duration of the run is a tier the run can destroy, and the
    artifacts most worth protecting are written early.
    """
    base = Path(runs_root) / f"RUN{run}"
    for tier in TIERS:
        (base / tier).mkdir(parents=True, exist_ok=True)
    protect(base, PROTECTED)
    return base


def migrate_into_store(run_dir: Path, assays: pd.DataFrame,
                       store: Path) -> dict:
    """Move a completed run's judgement into the durable store.

    CONFLICTING KEYS ARE EXCLUDED, NOT RESOLVED. Measured on RUN1, 200 ruled
    rows collapse to 127 pair keys and 5 disagree. `rulings.save` refuses the
    whole batch if a conflict reaches it, so they are filtered here and
    returned for the operator to rule directly. Writing one of the two verdicts
    -- by recency, by majority, by source precedence -- silently overwrites a
    human decision with a guess.
    """
    found, prov = migrate(run_dir, assays)
    clashing = conflicts(found)
    blocked = {record["key"] for record in clashing}
    clean = [r for r in found if r.key not in blocked]
    written = save(store, clean) if clean else 0
    return {"written": written, "conflicts": clashing, "provenance": prov}
