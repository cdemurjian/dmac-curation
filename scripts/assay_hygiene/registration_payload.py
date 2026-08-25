# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""The complete-list payload a registration write sends, built so it cannot delete.

WHAT THIS IS FOR. `assets/RUN1/00-rulings/REGISTRATION-ROWS.csv` holds 26,193
(sample, assay) registrations, each carrying a human ruling. Writing them means
telling SEEK what an assay's -- or a sample's -- membership now IS, because both
candidate mechanisms are COMPLETE-LIST rather than append:

    NExtSEEK API   PATCH /nextseek_api/assays/{uid}/   complete list per ASSAY
    batch upload   smart_merge_assay_assets            complete list per SAMPLE

Under either, anything absent from the payload is deleted. So the payload that
is correct under BOTH is `existing UNION additions`, and building that union is
this module's entire job. It is deliberately not a join helper inside a writer:
an omission here does not raise, it returns a well-formed payload that destroys
memberships nobody ruled on, and that failure mode deserves its own tests.

THE MEASURED STAKES, against the real set: 26,188 resolved rows touch 102 SEEK
assays already holding 202,016 memberships, and 24,007 samples already holding
25,912. The largest single assay payload is 48,951 references of which 48,440
are pre-existing. None of those are this project's to lose.

CONTAINMENT IS A SEPARATE PROPERTY FROM THE UNION. Only assays and samples that
some approved row actually targets appear in the payload. An untouched record
included with `existing UNION nothing` would be arithmetically correct and would
still rewrite the complete membership of something no ruling covers.

THIS MODULE NEVER TALKS TO A DATABASE and never decides WHICH mechanism to use.
It takes frames and returns frames, so the payload can be reviewed before a
write mechanism is chosen.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TARGET_COLUMN = "write_target_seek_assay_id"


@dataclass
class Payloads:
    """The two shapes of the same union, plus what could not be written.

    `per_assay` and `per_sample` describe THE SAME set of memberships from
    opposite ends. Whichever mechanism is chosen sends one of them; they are
    both built so the choice can be made after the payload is reviewed.
    """

    per_assay: pd.DataFrame     # assay_id, sample_id -- complete list per assay
    per_sample: pd.DataFrame    # sample_id, assay_id -- complete list per sample
    excluded: pd.DataFrame      # registration rows with no resolvable target


def _additions(registration: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """-> the distinct (sample_id, assay_id) pairs to add, and the unresolved mask."""
    target = (registration[TARGET_COLUMN].fillna("").astype(str).str.strip()
              .str.replace(r"\.0$", "", regex=True))
    unresolved = target == ""
    adds = pd.DataFrame({
        "sample_id": registration.sample_id[~unresolved].astype(str).str.strip(),
        "assay_id": target[~unresolved],
    }).drop_duplicates()
    return adds, unresolved


def build_payloads(registration: pd.DataFrame,
                   membership: pd.DataFrame) -> Payloads:
    """-> `existing UNION additions`, in both shapes, for touched records only."""
    adds, unresolved = _additions(registration)
    have = pd.DataFrame({
        "sample_id": membership.sample_id.astype(str),
        "assay_id": membership.assay_id.astype(str),
    }).drop_duplicates()

    touched_assays = set(adds.assay_id)
    touched_samples = set(adds.sample_id)

    # The union, taken once and then cut two ways. Cutting the SAME frame is
    # what keeps the two shapes describing one set of memberships: building
    # them independently is one edit away from two payloads that disagree.
    per_assay = (pd.concat([have[have.assay_id.isin(touched_assays)], adds])
                 .drop_duplicates()[["assay_id", "sample_id"]]
                 .sort_values(["assay_id", "sample_id"], key=_numeric_key)
                 .reset_index(drop=True))
    per_sample = (pd.concat([have[have.sample_id.isin(touched_samples)], adds])
                  .drop_duplicates()[["sample_id", "assay_id"]]
                  .sort_values(["sample_id", "assay_id"], key=_numeric_key)
                  .reset_index(drop=True))

    return Payloads(per_assay=per_assay, per_sample=per_sample,
                    excluded=registration[unresolved])


def _numeric_key(col: pd.Series) -> pd.Series:
    """Sort ids by value, not lexically, so 9 precedes 10 in every artifact."""
    return pd.to_numeric(col, errors="coerce").fillna(-1)


def assert_no_membership_lost(per_assay: pd.DataFrame,
                              membership: pd.DataFrame,
                              touched_assays: set[str]) -> None:
    """Raise unless every existing member of a touched assay is in the payload.

    This is the check that fires on data the unit fixtures do not describe. It
    is stated as a refusal rather than a report because the caller's next act
    is a write, and a payload that has lost a member is not a payload to send
    with a warning attached.
    """
    have = set(zip(membership.assay_id.astype(str),
                   membership.sample_id.astype(str)))
    sending = set(zip(per_assay.assay_id.astype(str),
                      per_assay.sample_id.astype(str)))
    lost = {(a, s) for a, s in have if a in touched_assays} - sending
    if lost:
        by_assay: dict[str, int] = {}
        for a, _ in lost:
            by_assay[a] = by_assay.get(a, 0) + 1
        worst = sorted(by_assay.items(), key=lambda kv: -kv[1])[:5]
        raise ValueError(
            f"the payload would DELETE {len(lost):,} existing membership(s) "
            f"across {len(by_assay)} assay(s): every one is a registration "
            f"nobody ruled on, held by a record this write only meant to add "
            f"to. Worst: " + ", ".join(f"assay {a} loses {n:,}"
                                       for a, n in worst))


def assert_no_assay_lost(per_sample: pd.DataFrame,
                         membership: pd.DataFrame,
                         touched_samples: set[str]) -> None:
    """The same refusal from the sample end, for the batch-upload mechanism."""
    have = set(zip(membership.sample_id.astype(str),
                   membership.assay_id.astype(str)))
    sending = set(zip(per_sample.sample_id.astype(str),
                      per_sample.assay_id.astype(str)))
    lost = {(s, a) for s, a in have if s in touched_samples} - sending
    if lost:
        raise ValueError(
            f"the payload would DELETE {len(lost):,} existing assay "
            f"membership(s) across {len({s for s, _ in lost})} sample(s), "
            f"unregistering samples this write only meant to add to.")
