# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Join an operator-edited CSV back onto the cohorts it was built from.

THIS IS THE ONE PLACE RUN1 WAS HAND-ASSEMBLED, and it is where a mistake
registers rows nobody approved. Four properties, all from spec section 9:

  1. every ingested row matches exactly one cohort, or the ingest REFUSES --
     a partial match is never resolved by a rule
  2. a verdict outside the vocabulary refuses rather than defaults
  3. ingesting the same file twice is a no-op, not a duplicate ruling
  4. the cohort key is the one the review surface EMITTED, looked up in the
     map it emitted -- never reconstructed here, because a second definition
     of the key is one edit away from disagreeing with the first

REFUSAL IS WHOLE-FILE, NOT PER-ROW. A file with one unmatched row is a file
built against different cohorts, and ingesting the rows that happen to match
would file a subset of the operator's judgement while reporting success.
"""
from __future__ import annotations

import pandas as pd

from .rulings import PairKey, Ruling, VERDICTS

KEY_COLUMN = "cohort_key"
RULING_COLUMN = "ruling"


class IngestRefused(ValueError):
    """The edited sheet does not join cleanly onto the cohorts it came from."""


def ingest(edited: pd.DataFrame, cohorts: dict[str, PairKey],
           ruled_on: str, actor: str = "operator") -> list[Ruling]:
    """-> the rulings this sheet carries, or raise."""
    for column in (KEY_COLUMN, RULING_COLUMN):
        if column not in edited.columns:
            raise IngestRefused(
                f"the sheet has no {column!r} column; it carries "
                f"{list(edited.columns)}. This must be the file the review "
                f"surface emitted, not one rebuilt by hand.")

    seen: dict[PairKey, str] = {}
    out: list[Ruling] = []
    for row in edited.itertuples():
        key = str(getattr(row, KEY_COLUMN)).strip()
        verdict = str(getattr(row, RULING_COLUMN)).strip()
        if not verdict or verdict.lower() == "nan":
            continue
        if key not in cohorts:
            raise IngestRefused(
                f"{key!r} matches no cohort in this run. The sheet was built "
                f"against a different set; ingesting only the rows that match "
                f"would file part of your judgement and report success.")
        if verdict not in VERDICTS:
            raise IngestRefused(
                f"verdict {verdict!r} on {key!r} is not one of "
                f"{list(VERDICTS)}. A typo must refuse rather than default.")
        pair = cohorts[key]
        if pair in seen and seen[pair] != verdict:
            raise IngestRefused(
                f"{key!r} is ruled both {seen[pair]} and {verdict} in this "
                f"one file. That is a disagreement to settle before ingest, "
                f"not something to resolve by row order.")
        if pair in seen:
            continue
        seen[pair] = verdict
        out.append(Ruling(pair, verdict, ruled_on, actor))
    return out
