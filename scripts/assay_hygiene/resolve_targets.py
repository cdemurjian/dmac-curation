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
correct target, and it is reported as such rather than silently discarded. The
reason must be true of the row it is attached to: `NOT_IN_EXTRACT` and
`NO_PROJECT` were one reason until 2026-08-31, which told a curator that 179
RUN2 rows had a sample belonging to no project when those rows have no sample in
the extract to belong to anything.
"""
from __future__ import annotations

import pandas as pd

from .classify import project_index
from .rulings import normalise_id

TARGET_COLUMN = "write_target_seek_assay_id"
NOT_IN_EXTRACT = "sample not present in the extract"
NO_PROJECT = "sample belongs to no project"
NO_CANDIDATE = "no assay with that internal id in the sample's project"
AMBIGUOUS = "internal assay exists in more than one of the sample's projects"


class CrossProjectTarget(ValueError):
    """A row targets an assay outside the sample's own project."""


def resolve(rows: pd.DataFrame, assays: pd.DataFrame,
            samples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (manifest, excluded). Every manifest row is project-consistent."""
    by_project: dict[tuple[str, int], int] = {}
    for a in assays.itertuples():
        by_project[(normalise_id(a.internal_assay_id), int(a.project_id))] = int(a.assay_id)

    # PARSED THROUGH `classify.project_index`, NEVER ITERATED. `extract.py`
    # builds this column with `GROUP_CONCAT(ps.project_id)`, so on the real
    # extract it is a COMMA-JOINED STRING -- and null, not empty, for a sample
    # in no project. `list("10")` is `["1", "0"]`, which resolves a sample in
    # project 10 against projects 1 and 0 and, where either holds the internal
    # assay, writes a WRONG TARGET carrying `project_ok=True`. That is the
    # unrecoverable cross-project write this module exists to prevent, reached
    # through the gate meant to stop it. `project_index` is the package's one
    # reader of the column: it splits on `,`, dedupes the `2,2` GROUP_CONCAT
    # spelling, sorts numerically and maps null to no projects at all.
    projects = {sid: [p for p in ids.split(";") if p]
                for sid, ids in project_index(samples).items()}

    kept, dropped = [], []
    for row in rows.itertuples():
        sample_id = int(row.sample_id)
        internal = normalise_id(row.internal_assay_id)
        # TWO ABSENCES, TWO REASONS, AND ONLY ONE OF THEM IS ABOUT PROJECTS.
        # `project_index` keys EVERY sample in the extract, mapping to the empty
        # string where the sample is in no project, so a missing key and an
        # empty list are different findings. A missing key means there is no
        # `samples` row at all -- on the real data a Neo4j node with nothing
        # behind it in MySQL -- and "belongs to no project" then asserts
        # something about a sample that was never read. An empty list is the
        # sample being there and genuinely in nothing. On the RUN2 approved rows
        # the one old reason covered 242: 63 projectless and 179 absent. The
        # curator's next move differs (fix the membership, versus find out why
        # the sample is missing from the extract), so the two are reported
        # apart. Neither is kept: both still lack a resolvable target.
        if sample_id not in projects:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NOT_IN_EXTRACT})
            continue
        owned = projects[sample_id] or []
        if not owned:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_PROJECT})
            continue
        # EVERY candidate, not the first. A sample can belong to several
        # projects and the internal assay can exist in more than one of them,
        # in which case `next()` picked whichever came first in project_ids --
        # an unrecoverable write decided by list order. Ambiguity is excluded
        # and reported, exactly like the other two exclusions.
        candidates = {by_project[(internal, int(p))] for p in owned
                      if (internal, int(p)) in by_project}
        if not candidates:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_CANDIDATE})
            continue
        if len(candidates) > 1:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": AMBIGUOUS})
            continue
        target = candidates.pop()
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
