# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Mode 3. Where a sample's metadata contradicts what it is registered in.

Writes nothing, ever. A flag costs a curator's attention; a wrong write costs
data, and this pipeline's writer deletes by omission. That asymmetry is why
Mode 3 ships before the write path is proven.

Only high-confidence claims raise a flag. Strong-field claims are 98.4%
accurate and corroborated ones 99.9% (measured 2026-08-14, held out by sample);
weak claims are 90.4%, so flagging on them would hand a curator roughly one
false positive in ten. Contested claims -- ones whose sample's own evidence
names more than one assay -- have not settled what they assert, and on that
subset the winning claim's mapping is still wrong about 30% of the time. Both
floors are parameters so a curator can widen them deliberately, never by
accident.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S
from .precedent import assay_index

# Tiers trusted enough to contradict a curator's own registration.
DEFAULT_TIERS = (S.T_CORROBORATED, S.T_STRONG)


def registered_internal(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> dict[int, set[int]]:
    """sample_id -> the set of INTERNAL assay ids it is registered in.

    membership.assay_id is a seek_production assay_assets.assay_id and claims
    speak internal ids, so the junction has to be crossed before anything is
    compared. Comparing the two id spaces directly is the silent-wrong-answer
    failure this whole package is shaped to avoid.

    RAISES `ValueError` on a membership row naming an assay absent from the
    assays frame, rather than skipping it -- the same up-front, whole-frame
    check `precedent.mine_precedent` and `vocabulary_evidence.registered_assays`
    perform, reported all at once so a broken extract is diagnosed in one run.

    The skip is worse here than in either sibling, and in BOTH directions. A
    dropped registration SHRINKS the set a claim is compared against, so a
    claim that agrees with the dropped registration is promoted into a
    MODE_3_FLAG: the audit accuses a curator of a contradiction using a
    registration it discarded itself, and the flag reads exactly like a real
    one. Drop every registration a sample has and the opposite happens -- the
    sample looks unregistered, falls to Mode 1's population, and its genuine
    contradiction is never reported. Neither shows up as an error, a warning,
    or a row-count anomaly. 0 of the 173 membership assay_ids on the real
    extract hit this today.

    Returns a plain dict built with `setdefault`, not a defaultdict, for the
    same reason `precedent.membership_index` does: callers ask about samples
    registered nowhere, and a defaultdict answers by CREATING the entry.
    """
    ainfo = assay_index(assays)

    unknown = sorted({int(a) for a in membership.assay_id} - set(ainfo))
    if unknown:
        raise ValueError(
            f"membership registers samples in {len(unknown)} assay(s) absent "
            f"from the assays frame: {unknown}. Those registrations cannot be "
            "crossed to the internal namespace, and skipping them would let "
            "the audit flag a sample for contradicting a registration it "
            "dropped itself. Re-extract so the two frames agree."
        )

    out: dict[int, set[int]] = {}
    for sample_id, assay_id in zip(membership.sample_id, membership.assay_id):
        out.setdefault(int(sample_id), set()).add(ainfo[int(assay_id)][1])
    return out


def audit_contradictions(
    claims: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
    tiers: tuple[str, ...] = DEFAULT_TIERS,
    include_contested: bool = False,
) -> pd.DataFrame:
    """Flag samples whose claim names an assay they are not registered in.

    A sample registered in NOTHING is not flagged: that is Mode 1's population,
    and Mode 3 needs something to contradict.

    Contested rows are excluded by a SEPARATE parameter rather than by tier.
    Folding contestedness into the tier is what made the previous design
    non-monotone -- a second claim lowered the first one's tier and its flag
    disappeared, measured at 102 suppressed against 13 added over the real
    extract. Here a contested row keeps whatever tier its own evidence earned
    and is filtered at the audit, so admitting them later is a parameter change
    rather than a re-derivation. They are excluded by default because on the
    disagreement subset the winning claim's mapping is wrong about 30% of the
    time, three times the rate the weak floor already refuses.

    One flag per (sample, claimed assay), never per sample: a sample claiming
    two assays it is not registered in has two things wrong with it, and
    collapsing them would make the count depend on the claims frame's row
    order.
    """
    registered = registered_internal(membership, assays)
    # Keyed on uuid and NOT sample_id. `nodes` is documented as a uuid index
    # and sample_id is not unique in it: measured on the real extract
    # 2026-08-14, 86 sample_ids carry two node rows under two uuids and 51 of
    # those pairs disagree on type (165987 is both MUS-250620SAR-2 and
    # RNA-250620SAR-2). A sample_id-keyed dict resolves those by last-write-
    # wins over a frame whose row order is not stable across extracts, and 85
    # claims land on such an id -- 7 of which would report the other node's
    # type. uuid is unique there (0 duplicates over 177,392 rows) and all
    # 138,007 claims carry one that resolves.
    types = {
        u: (None if pd.isna(t) else str(t))
        for u, t in zip(nodes.uuid, nodes.type)
    }

    rows = []
    for c in claims.itertuples():
        if c.tier not in tiers:
            continue
        if bool(c.contested) and not include_contested:
            continue
        have = registered.get(int(c.sample_id))
        if not have:
            continue                      # unregistered -> Mode 1, not Mode 3
        if int(c.internal_assay_id) in have:
            continue                      # claim agrees with the record
        rows.append({
            "sample_id": int(c.sample_id),
            "uuid": c.uuid,
            "sample_type": types.get(c.uuid),
            "registered_internal_assay_ids": ";".join(str(i) for i in sorted(have)),
            "claimed_internal_assay_id": int(c.internal_assay_id),
            "claimed_internal_assay_title": c.internal_assay_title,
            "tier": c.tier,
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "verdict": S.V_MODE3_FLAG,
        })

    # Sorted, because this is an artifact a curator diffs between runs and
    # `claims` arrives in whatever order the extractor wrote samples.parquet --
    # an order test_assay_hygiene_stage0.py already records as unstable across
    # extracts. Emitting in arrival order means a re-extract reshuffles the csv
    # with no change in content, which reads as change in a diff. Same hazard
    # and same fix as precedent.mine_precedent's RULE_KEY tiebreak.
    #
    # (sample_id, claimed_internal_assay_id) is a TOTAL order on this output,
    # not a partial one: sample_claims emits at most one row per (sample,
    # assay), so no two flags can tie on the pair and nothing is left to an
    # underlying sort's stability. It also groups a sample's flags together,
    # which is how a curator reads them.
    return pd.DataFrame(rows, columns=S.AUDIT_COLUMNS).sort_values(
        ["sample_id", "claimed_internal_assay_id"], ignore_index=True,
    )
