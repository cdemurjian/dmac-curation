# /// script
# requires-python = ">=3.11"
# ///
"""Sort this run's cohorts against the rulings of every run before it.

THE MIDDLE BUCKET IS THE WHOLE POINT. A pair ruling is coarser than the cohort
it was made against, so "the operator approved this pair" and "the operator
approved a narrow slice of this pair and we widened it" are different facts. In
RUN1, 2,830 rows shared a cohort key with an approved cohort but sat below the
precedent floor the operator's sheet was built at; he never saw them. A
carry-forward matching on the pair alone registers every one of them silently.

AN UNKNOWN RULED WIDTH IS TREATED AS WIDENED, NOT CARRIED. Absence of evidence
that the ruling covered these rows is not evidence that it did, and the cost of
the two mistakes is not symmetric: a needless re-confirmation costs the
operator a line, an unearned carry-forward writes to production.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .rulings import PairKey, Ruling

CARRIED = "already_ruled"
WIDENED = "ruled_in_a_narrower_context"
UNSEEN = "never_seen"


@dataclass(frozen=True)
class Cohort:
    key: PairKey
    n_rows: int
    cohort_id: str


def split(cohorts: Iterable[Cohort],
          store: dict[PairKey, Ruling],
          ruled_width: dict[PairKey, int]) -> dict[str, list[Cohort]]:
    """-> {bucket: cohorts}. Every cohort lands in exactly one bucket."""
    out: dict[str, list[Cohort]] = {CARRIED: [], WIDENED: [], UNSEEN: []}
    for cohort in cohorts:
        if cohort.key not in store:
            out[UNSEEN].append(cohort)
            continue
        was = ruled_width.get(cohort.key)
        if was is not None and cohort.n_rows <= was:
            out[CARRIED].append(cohort)
        else:
            out[WIDENED].append(cohort)
    return out
