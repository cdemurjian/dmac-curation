# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage B2. What assay does each sample's own metadata say it belongs to.

Independent of stage B by design: that one counts graph membership, this one
reads text. They fail in unrelated ways, and when a number looks wrong you need
to know which half to distrust.

Tiers come from measurement, not intuition. Against the 360,027 curator-labelled
edges, held out by sample: strong fields alone are 98.4% accurate over 65.9% of
the population, Protocol and DataType raise coverage to 92.3% at 90.4%
accuracy, and where Type and Protocol agree the answer is right 99.9% of the
time. So strong fields decide, weak fields corroborate, and agreement between
the two is the strongest signal available.

A claim is not a decision. This module says what a sample asserts about itself;
what to do about it belongs to stage C and the modes.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S


def claim_index(vocab: pd.DataFrame) -> dict[tuple[str, str], tuple[int, str, str]]:
    """(field, normalised value) -> (internal_assay_id, title, provenance).

    Keyed on the field as well as the value: the same string can name different
    assays under different fields, and a value-only index would collide them.

    Provenance rides along because this is the only place claims.py sees the
    vocabulary, and both the proposal tier cap and the contest rule need it.

    The VALUE half of the key is normalised, and that is load-bearing rather
    than defensive. `sample_claims` looks up the normalised metadata value, so
    an un-normalised vocabulary key is matched by nothing; and
    `vocabulary.unresolved_terms` normalises both of its sides too, so the term
    does not come back in the judgment queue either. A curator who rules on
    `Tissue Scope` -- spelled the way it appears in the metadata, which is the
    natural way to hand-edit the csv -- would have their decision counted as
    resolved and applied to zero samples, with nothing anywhere to notice. All
    736 rows in today's vocabulary are `learned` and `learn_vocabulary` emits
    normalised values, so the live file is unaffected; the first hand-edited
    row is what this is for. `normalise_value` is idempotent, so it costs the
    learned rows nothing.

    Rows whose id or whose key normalises away are skipped rather than raised
    on. A key that normalises to None can never equal a normalised metadata
    value, so it is unreachable either way -- and `merge_vocabulary` already
    raises on that input, at the point where it would have DELETED rows.
    """
    out: dict[tuple[str, str], tuple[int, str, str]] = {}
    for r in vocab.itertuples():
        if pd.isna(r.internal_assay_id):
            continue
        value = S.normalise_value(r.raw_value)
        if not value:
            continue
        out[(str(r.source_field), value)] = (
            int(r.internal_assay_id),
            None if pd.isna(r.internal_assay_title) else str(r.internal_assay_title),
            str(r.provenance),
        )
    return out


def sample_claims(
    meta: dict[int, dict],
    uuids: dict[int, str],
    vocab: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (sample, claimed assay). Samples claiming nothing emit none.

    Each row is tiered on the evidence backing ITS OWN assay, so the arrival of
    a second claim can never lower the first one's tier. That property is what
    keeps the Mode 3 audit monotone: under the previous per-sample design, any
    disagreement collapsed the whole sample to T_CONFLICT, which sits below the
    audit floor, and adding evidence measurably REMOVED 102 existing flags while
    adding 13.

    Disagreement is recorded in `contested` instead. Only learned and curator
    mappings can contest; a proposal may corroborate a claim but never unseat
    one, because it carries support = 0 and no empirical anchor.
    """
    idx = claim_index(vocab)
    rows = []

    for sample_id, d in meta.items():
        # internal_assay_id -> the (field, raw, provenance) triples that named
        # it, strong fields first because CLAIM_FIELDS is ordered that way.
        #
        # Keyed on the ID ALONE, never on (id, title). The title is display and
        # it is not stable per id across the vocabulary: merge_vocabulary
        # rebuilds titles from the assays frame only where that frame has one,
        # so the 14 junction-less rows (ids 466, 469-472) keep whatever title
        # they carry -- None on a learned row, hand-typed on a curator row
        # ruling on the same id. Grouping by (id, title) would split ONE assay
        # into two claims and mark both contested, which is exactly the
        # audit-suppressing shape this design was rewritten to remove: two
        # spellings of one title would demote a corroborated claim below the
        # floor and delete a Mode 3 flag.
        found: dict[int, list[tuple[str, str, str]]] = {}
        titles: dict[int, str | None] = {}
        for field in S.CLAIM_FIELDS:
            raw = d.get(field)
            value = S.normalise_value(raw)
            if not value:
                continue
            hit = idx.get((field, value))
            if hit is None:
                continue
            iaid, title, prov = hit
            found.setdefault(iaid, []).append((field, str(raw), prov))
            # first non-null title wins: a NULL on one row must not erase the
            # only title the id has.
            if titles.get(iaid) is None:
                titles[iaid] = title

        if not found:
            continue

        # Contestedness is decided by the EVIDENCE-BACKED claims only. A
        # proposal that happens to name a different assay does not make the
        # sample contested, or a support=0 guess could push a curator's own
        # registration below the audit floor.
        #
        # Tested by MEMBERSHIP of S.EVIDENCE_PROVENANCES, never by `!=
        # S.P_PROPOSED`. The inequality made `proposed` the only untrusted
        # spelling, so `Proposed`, `PROPOSED`, `proposal` and `` all read as
        # evidence-backed here while `merge_vocabulary` ranked those same rows
        # LEAST trusted -- one column, two opposite defaults, and the cap
        # defeated by a casing typo. See S.EVIDENCE_PROVENANCES.
        backed = {
            iaid for iaid, sources in found.items()
            if any(p in S.EVIDENCE_PROVENANCES for _, _, p in sources)
        }
        contested = len(backed) > 1

        for iaid, sources in found.items():
            # Tier strength is computed over EVIDENCE-BACKED sources ONLY.
            #
            # Grading over all sources leaves a hole the cap was aimed squarely
            # at: a proposal landing on a strong field supplies the strong half
            # of a corroboration for a claim that already has a learned weak
            # field, and the claim crosses the audit floor on a model's guess.
            # Measured on the real extract, 104 claims rise weak -> corroborated
            # exactly that way. None contradicts its registration in today's
            # data, so the effect is zero by DATA, not by design -- and the risk
            # shape is the `m397` case, where a term's carriers split across
            # assays, the proposal takes the modal one, and the promoted claim
            # then accuses the minority carriers.
            #
            # Excluding proposals here also makes the cap structural rather than
            # a special case: a proposal-only claim has no backing sources at
            # all, so it falls to T_WEAK on its own. A proposal therefore never
            # raises ANY claim's tier, not merely a proposal-only one -- so a
            # proposal naming the same assay as an existing evidence-backed
            # claim cannot promote it either. Measured 2026-08-14, proposing all
            # 180 unresolved terms that have a candidate adds 8,442 new `weak`
            # claims and changes no existing claim's tier at all.
            #
            # Membership again, not `!= S.P_PROPOSED`: the same casing typo that
            # defeated the contest rule above defeated the cap here.
            backing = [s for s in sources if s[2] in S.EVIDENCE_PROVENANCES]
            has_strong = any(f in S.STRONG_FIELDS for f, _, _ in backing)
            has_weak = any(f in S.WEAK_FIELDS for f, _, _ in backing)
            if has_strong and has_weak:
                tier = S.T_CORROBORATED
            elif has_strong:
                tier = S.T_STRONG
            else:
                tier = S.T_WEAK
            # `source_field`, `raw_value` and `source_provenance` describe ONE
            # vocabulary row, or they describe nothing -- which is what the
            # `source_` prefix on that last name is promising. So the
            # representative source is the first BACKED one -- first in
            # CLAIM_FIELDS order, hence the strongest field that actually
            # earned the tier -- and its provenance is read off that same
            # source rather than ranked separately across the claim. Reporting
            # sources[0] instead would print a PROPOSED value beside a
            # `learned` provenance whenever the proposal lands on a stronger
            # field than the real evidence, which is the common shape: Task 7
            # puts these columns in front of a curator as the reason for a
            # flag, and they would go check a field whose mapping nothing
            # measured. A proposal-only claim has no backed source and falls
            # back to its own, which is the only one it has.
            field, raw, source_provenance = (backing or sources)[0]
            rows.append({
                "sample_id": sample_id, "uuid": uuids.get(sample_id),
                "internal_assay_id": iaid, "internal_assay_title": titles[iaid],
                "tier": tier, "source_field": field, "raw_value": raw,
                "contested": contested, "source_provenance": source_provenance,
            })

    return pd.DataFrame(rows, columns=S.CLAIM_COLUMNS)
