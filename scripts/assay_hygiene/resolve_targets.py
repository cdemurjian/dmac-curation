# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Turn an internal assay id into the SEEK assay of the sample's own project.

WHY THIS IS A HARD GATE. SEEK assay ids are per-project: the same internal
assay exists as a different `assay_id` in every project that runs it. A
registration that lands on another project's assay puts the sample into a
project it does not belong to, and nothing undoes that from the outside. The
2026-08-26 audit found 578 of 26,188 rows in exactly that state, every one
produced by a rule that resolved through a lineage neighbour without checking
the neighbour lived in the same project. 159 were repairable, 419 were not.

THE CHECK CANNOT BE MADE FROM THE WORKBOOK. It needs each sample's project set
and each assay's project, so `resolve` emits a manifest gate-checked at build
time and `assert_subset` is what `write` uses to prove the sheet never grew a
row the gate did not see.

EXCLUSION IS NOT REJECTION. A dropped row is an authorised registration with no
correct target, and it is reported as such rather than silently discarded.
"""
from __future__ import annotations

import pandas as pd

from .rulings import normalise_id

TARGET_COLUMN = "write_target_seek_assay_id"
NO_PROJECT = "sample belongs to no project"
NO_CANDIDATE = "no assay with that internal id in the sample's project"


class CrossProjectTarget(ValueError):
    """A row targets an assay outside the sample's own project."""


def resolve(rows: pd.DataFrame, assays: pd.DataFrame,
            samples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (manifest, excluded). Every manifest row is project-consistent."""
    by_project: dict[tuple[str, int], int] = {}
    for a in assays.itertuples():
        by_project[(normalise_id(a.internal_assay_id), int(a.project_id))] = int(a.assay_id)

    projects = {int(s.sample_id): list(s.project_ids)
                for s in samples.itertuples()}

    kept, dropped = [], []
    for row in rows.itertuples():
        sample_id = int(row.sample_id)
        internal = normalise_id(row.internal_assay_id)
        owned = projects.get(sample_id) or []
        if not owned:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_PROJECT})
            continue
        target = next((by_project[(internal, int(p))] for p in owned
                       if (internal, int(p)) in by_project), None)
        if target is None:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_CANDIDATE})
            continue
        kept.append({"sample_id": sample_id, "internal_assay_id": internal,
                     TARGET_COLUMN: target, "project_ok": True})

    manifest = pd.DataFrame(
        kept, columns=["sample_id", "internal_assay_id", TARGET_COLUMN,
                       "project_ok"])
    excluded = pd.DataFrame(
        dropped, columns=["sample_id", "internal_assay_id", "reason"])
    return manifest, excluded


def assert_subset(sheet: pd.DataFrame, manifest: pd.DataFrame) -> None:
    """Raise unless every (sample, assay) pair in `sheet` is in `manifest`."""
    allowed = {(int(r.sample_id), int(getattr(r, TARGET_COLUMN)))
               for r in manifest.itertuples()}
    strays = [(int(r.sample_id), int(r.assay_id)) for r in sheet.itertuples()
              if (int(r.sample_id), int(r.assay_id)) not in allowed]
    if strays:
        raise CrossProjectTarget(
            f"{len(strays)} row(s) target an assay the project gate never "
            f"approved, e.g. {strays[:5]}. The sheet must be a subset of the "
            f"manifest; a row that is not was never project-checked.")
