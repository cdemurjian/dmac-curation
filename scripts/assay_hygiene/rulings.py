# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""The durable ruling store: human judgement, separated from the run that made it.

WHY THE KEY IS WHAT IT IS. RUN1 filed verdicts under
`lab|sample_type|parent_types|assay_title|field|value`. Four of those six fields
move with the extract -- the lab is whichever happened to fall in that cohort,
parent_types depends on that extract's lineage, the assay is a TITLE and titles
are editable, and the value is a raw metadata term. So a new extract produced
cohorts that matched almost nothing and 261 rulings became worthless, though
none of the judgement had changed.

`(sample_type, internal_assay_id, action)` survives all four. It is also the
unit the reachability gate decides on, which is why ~150 pair questions settled
97% of a 99,449-row population when 251 cohort rulings could only estimate it.

WHAT THE KEY COSTS, stated because it is real: a pair ruling is COARSER than
the cohort it was made against. Measured on RUN1 over all three ruling files,
200 ruled rows collapse to 127 keys and 5 of those carry conflicting verdicts --
the operator approved one cohort and rejected another sharing the same triple,
because his judgement rested on something the triple discards. `save` refuses to
resolve that. A conflict is escalated, never averaged.

(An earlier figure of 156 rows / 114 keys / 3 conflicts circulated in the plan
and the handoff. It omitted the 44 Mode 1 rows -- 111 + 45 = 156 -- and
excluding Mode 1 reproduces it exactly. 5 of 127 keys is the true cost, not
3 of 114.)

PROVENANCE IS NOT STORED HERE. Cohort strings carry lab codes and at least one
protocol filename containing a person's name; they live in a gitignored sidecar
written by the migration, not in this module's tracked output.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PAIRS_NAME = "pairs.tsv"
VERDICTS = ("APPROVE", "REJECT", "WRONG_ASSAY", "UNSURE")

PairKey = tuple[str, str, str]


class ConflictingRulings(ValueError):
    """One key, two different verdicts. The operator resolves this, not a rule."""


@dataclass(frozen=True)
class Ruling:
    key: PairKey
    verdict: str
    ruled_on: str
    actor: str


def normalise_id(value) -> str:
    """-> the internal assay id as a bare decimal string.

    Titles resolve through pandas, whose integer columns yield `74.0`. A key
    that is sometimes `74` and sometimes `74.0` silently fails to match, which
    is the same class of defect as the internal-vs-SEEK id collision.
    """
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _collapse(rulings: Iterable[Ruling]) -> dict[PairKey, Ruling]:
    out: dict[PairKey, Ruling] = {}
    for r in rulings:
        if r.verdict not in VERDICTS:
            raise ValueError(
                f"verdict {r.verdict!r} is not one of {list(VERDICTS)}. A "
                f"typo must refuse rather than default.")
        seen = out.get(r.key)
        if seen is not None and seen.verdict != r.verdict:
            raise ConflictingRulings(
                f"{r.key} carries both {seen.verdict} and {r.verdict}. A pair "
                f"ruling is coarser than the cohort it was made against; this "
                f"is a real disagreement and must be put to the operator.")
        out[r.key] = r
    return out


def save(store: Path, rulings: Iterable[Ruling]) -> int:
    """Write the store. Refuses an unknown verdict or a conflicting key."""
    collapsed = _collapse(rulings)
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [{"sample_type": k[0], "internal_assay_id": k[1], "action": k[2],
          "verdict": r.verdict, "ruled_on": r.ruled_on, "actor": r.actor}
         for k, r in sorted(collapsed.items())])
    frame.to_csv(store / PAIRS_NAME, sep="\t", index=False)
    return len(collapsed)


def load(store: Path) -> dict[PairKey, Ruling]:
    """-> key -> Ruling. An absent store is empty, not an error."""
    path = Path(store) / PAIRS_NAME
    if not path.exists():
        return {}
    frame = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    return {(r.sample_type, normalise_id(r.internal_assay_id), r.action):
            Ruling((r.sample_type, normalise_id(r.internal_assay_id), r.action),
                   r.verdict, r.ruled_on, r.actor)
            for r in frame.itertuples()}
