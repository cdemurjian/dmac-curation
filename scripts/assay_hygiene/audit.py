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
subset the winning claim's mapping is still wrong about 30% of the time. And a
sample registered under a junction-less assay has a registration whose internal
identity is unknown, so nothing can be said to contradict it.

All three floors are parameters (`tiers`, `include_contested`,
`include_unmappable`) so a curator can widen them deliberately, never by
accident, and so no row this mode refuses is unrecoverable.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S
from .precedent import assay_index, fallback_assay_ids, membership_index

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

    This is `precedent.membership_index` COMPOSED with `assay_index` and not a
    third grouping of the membership frame: the seek-side grouping is defined
    once, in the module that owns the funnel, and this function is only the
    namespace crossing on top of it. It inherits the plain-dict return that
    docstring argues for -- callers ask about samples registered nowhere, and a
    defaultdict would answer by CREATING the entry, so `999 in idx` would be
    true of every sample ever asked about.
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

    return {
        sample_id: {ainfo[a][1] for a in assay_ids}
        for sample_id, assay_ids in membership_index(membership).items()
    }


def audit_contradictions(
    claims: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
    tiers: tuple[str, ...] = DEFAULT_TIERS,
    include_contested: bool = False,
    include_unmappable: bool = False,
) -> pd.DataFrame:
    """Flag samples whose claim names an assay they are not registered in.

    A sample registered in NOTHING is not flagged: that is Mode 1's population,
    and Mode 3 needs something to contradict.

    A sample whose registered set contains an UNMAPPABLE id is not flagged
    either, and this one is about namespaces rather than population. A claim
    speaks a dmac internal id; a junction-less registration resolves to a seek
    `assays.id`, which is a different namespace (see `assay_index`). That
    function's collision guard makes a false AGREEMENT impossible -- no
    fallback id can equal a genuine one -- but it does nothing about a false
    CONTRADICTION, because an id in the wrong namespace can never match and so
    reads as disagreement every time. A fallback id in `have` is therefore a
    registration whose internal identity is UNKNOWN, not one known to differ,
    and recovering that identity could only ever ADD to `have`. Adding to
    `have` can only ever REMOVE a flag -- the same monotone direction this
    whole mode rests on -- so the contradiction is NOT ESTABLISHED and the
    audit refuses to assert it.

    Excluded by ID SPACE and never by title. A title rule would make the
    display string load-bearing for identity, which this package refuses (124
    seek ids collide numerically with genuine internal ids under 122 different
    titles), and it also misses cases: measured on the real extract, 14 flags
    carry a fallback id while only 13 have a title equal to the claimed one.
    The 14th (sample 244038, registered 466;467, claiming 24 DNA Extraction) is
    exactly the row a title rule would let through.

    Measured 2026-08-14: the exclusion removes 13 of 879 at the default and 14
    of 1,570 with contested admitted. It is one of only 23 distinct flag
    patterns, so it is 4.3% of a curator's actual judgement surface rather than
    1.5% of a row count. Four of the 17 junction-less assays share a normalised
    title with a genuine internal id (467/64, 468/34, 481/61, 482/99); only 481
    produces flags today and the other three are latent, waiting on an at-floor
    claim. The real repair is upstream -- 17 junction rows in
    dmac.assays_internal_assays -- which is strictly better and also clears the
    latent collision `assay_index` raises on. This rule holds while that is
    outstanding, and after it, should a junction row ever go missing again.

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
    unmappable = fallback_assay_ids(assays)
    # internal id -> title, read off the SAME funnel that produced the ids in
    # `registered`, so the decoded column cannot disagree with the id column it
    # sits beside. Every id in `have` resolves by construction: both come from
    # `assay_index`. Measured on the real extract, 0 of 458 assay records carry
    # an internal id with no title and no internal id resolves to two distinct
    # titles, so `titles` is total and single-valued over its 154 keys.
    titles = {iaid: title for _, iaid, title in assay_index(assays).values()}
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
        if (have & unmappable) and not include_unmappable:
            continue                      # identity unknown -> not established
        # Sorted once and read twice, so index i of the id column names index i
        # of the title column. Building either independently would let the two
        # drift into a row that decodes to the wrong assay -- the failure the
        # column was added to prevent.
        reg = sorted(have)
        rows.append({
            "sample_id": int(c.sample_id),
            "uuid": c.uuid,
            "sample_type": types.get(c.uuid),
            "registered_internal_assay_ids": ";".join(str(i) for i in reg),
            "registered_internal_assay_titles": ";".join(
                str(titles.get(i)) for i in reg),
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
