# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Measure how well sample metadata predicts the assay a curator actually assigned.

The question this answers, before any of stages B2/C/D get built:

    When a sample's json_metadata names an assay, how often is that the assay a
    human curator independently put on the edge?

Why it has to be answered first. The design now lets metadata evidence carry a
rule to PROPAGATE where precedent is silent. The largest such block is
D.IMG -> TIS under CometChip Assay: 303,866 dark edges, metadata naming the
assay on both sides, and ZERO instances anywhere of a curator registering both
endpoints in it. That means the 95% precision bar CANNOT validate that class --
a backtest measures recovery of known-good labels, and there are no labels to
recover. Precision there is unmeasurable by construction.

What IS measurable is metadata's accuracy on the 360,027 edges that DO carry a
curator-assigned assay. If metadata predicts those reliably, that is a real
quantified basis for trusting it where precedent is silent, honestly labelled as
transferred evidence rather than direct. If it does not, the CometChip proposal
should not ship.

METHOD. Learn the (metadata value -> internal_assay_id) mapping empirically from
a training split, then predict on a held-out split and score. Learning the
mapping from data rather than asking an LLM keeps this measurement independent
of the vocabulary-alignment step it is meant to justify.

The split is BY CHILD SAMPLE, not by edge. A sample fans out to many edges, so
an edge-level split would put the same sample on both sides and score memorised
answers. Splitting on a stable hash of sample_id prevents that. Metadata VALUES
are deliberately shared across the split: aligning the vocabulary once and
applying it everywhere is exactly the production behaviour.

    uv run scripts/measure_metadata_accuracy.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assay_hygiene import _schema as S  # noqa: E402

EXTRACT = Path("assay-hygiene/extract")

# The candidate fields, their strong/weak split and the cascade ORDER all come
# from _schema now. They used to be a local CANDIDATE_FIELDS list holding the
# same ten fields in a different order, with Protocol second; that ordering is
# what made this script disagree with the figures it is cited for, because the
# cascade below is decided by whichever field predicts FIRST. Reading the
# constants means the script and the contract cannot drift again.
#
# Likewise the normaliser: `norm()` used to be defined here, byte-identical to
# _schema.normalise_value. Two copies of the key function in a measurement and
# the code the measurement justifies is one edit away from silently scoring a
# different vocabulary than production uses.
MIN_SUPPORT = 3  # a value seen fewer times than this in train predicts nothing


def learn(field: str, rows, meta, in_train) -> dict[str, int]:
    """value -> most common internal_assay_id, learned from TRAIN rows only.

    Values seen fewer than MIN_SUPPORT times in train predict nothing: a value
    that appeared once and happened to sit on one assay is memorisation, not a
    mapping.
    """
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for child_id, iaid in rows:
        if not in_train(child_id):
            continue
        v = S.normalise_value((meta.get(child_id) or {}).get(field))
        if v:
            tally[v][iaid] += 1
    return {v: c.most_common(1)[0][0]
            for v, c in tally.items() if sum(c.values()) >= MIN_SUPPORT}


def predict(fields, tallies, d) -> int | None:
    """First field in `fields` that resolves wins. ORDER IS THE MEASUREMENT.

    Put a weak field early and it decides rows a strong field would have decided
    correctly, which lowers accuracy without moving coverage by a single edge --
    the fields are the same ten either way.
    """
    for field in fields:
        v = S.normalise_value(d.get(field))
        if v:
            p = tallies[field].get(v)
            if p is not None:
                return p
    return None


def score(fields, tallies, rows, meta, in_train, test_n) -> tuple[float, float, int]:
    """(coverage, accuracy, n_covered) of a cascade, on HELD-OUT rows only."""
    hit = miss = 0
    for child_id, iaid in rows:
        if in_train(child_id):
            continue
        p = predict(fields, tallies, meta.get(child_id) or {})
        if p is None:
            continue
        if p == iaid:
            hit += 1
        else:
            miss += 1
    covered = hit + miss
    return (covered / test_n if test_n else 0.0,
            hit / covered if covered else 0.0,
            covered)


def score_agreement(a, b, tallies, rows, meta, in_train, test_n):
    """(coverage, accuracy, n) over held-out rows where BOTH a and b predict and agree."""
    hit = miss = 0
    for child_id, iaid in rows:
        if in_train(child_id):
            continue
        d = meta.get(child_id) or {}
        va, vb = S.normalise_value(d.get(a)), S.normalise_value(d.get(b))
        pa = tallies[a].get(va) if va else None
        pb = tallies[b].get(vb) if vb else None
        if pa is None or pb is None or pa != pb:
            continue
        if pa == iaid:
            hit += 1
        else:
            miss += 1
    covered = hit + miss
    return (covered / test_n if test_n else 0.0,
            hit / covered if covered else 0.0,
            covered)


def main() -> int:
    edges = pd.read_parquet(EXTRACT / "edges.parquet")
    samples = pd.read_parquet(EXTRACT / "samples.parquet")

    labelled = edges[edges.edge_internal_assay_id.notna()].copy()
    print(f"labelled edges (curator ground truth) {len(labelled):>10,}")

    meta: dict[int, dict] = {}
    for sid, jm in zip(samples.sample_id, samples.json_metadata):
        if not jm:
            continue
        try:
            d = json.loads(jm)
        except Exception:
            continue          # unparseable blob: counted as no metadata, not dropped
        if isinstance(d, dict):
            meta[int(sid)] = d
    print(f"samples with parseable metadata        {len(meta):>10,}")

    # --- split by child sample, deterministically ----------------------------
    def in_train(sample_id: int) -> bool:
        return sample_id % 2 == 0

    rows = list(zip(labelled.child_id.astype(int),
                    labelled.edge_internal_assay_id.astype(int)))
    n_train = sum(1 for c, _ in rows if in_train(c))
    print(f"train edges {n_train:>10,}   test edges {len(rows) - n_train:>10,}")
    print()

    test_n = len(rows) - n_train

    # learn every field's mapping once; the per-field table and all three tiers
    # below read the same tallies, so no tier can be scored against a mapping
    # the others did not see
    tallies = {f: learn(f, rows, meta, in_train) for f in S.CLAIM_FIELDS}

    results = []
    for field in S.CLAIM_FIELDS:
        cov, acc, covered = score([field], tallies, rows, meta, in_train, test_n)
        kind = "strong" if field in S.STRONG_FIELDS else "weak"
        results.append((field, kind, len(tallies[field]), cov, acc, covered))

    print(f"{'field':<14} {'':<7} {'terms':>6} {'coverage':>9} {'accuracy':>9} {'n':>9}")
    print("-" * 60)
    for field, kind, terms, cov, acc, covered in sorted(results, key=lambda r: -r[3] * r[4]):
        print(f"{field:<14} {kind:<7} {terms:>6,} {cov:>8.1%} {acc:>8.1%} {covered:>9,}")

    # --- the tiered cascade --------------------------------------------------
    #
    # These three rows are the ones quoted in the design spec and in _schema's
    # CLAIM_FIELDS comment, so they are computed here rather than assembled by
    # hand from the per-field table above.
    #
    # Rows 1 and 2 differ ONLY in whether the two weak fields are allowed to
    # decide. They see the same held-out edges and the same learned mappings, so
    # the gap between them is the price of the extra coverage and nothing else.
    strong_cov, strong_acc, strong_n = score(
        S.STRONG_FIELDS, tallies, rows, meta, in_train, test_n)
    all_cov, all_acc, all_n = score(
        S.CLAIM_FIELDS, tallies, rows, meta, in_train, test_n)
    agree_cov, agree_acc, agree_n = score_agreement(
        "Type", "Protocol", tallies, rows, meta, in_train, test_n)

    print()
    print("--- tiered cascade, held out by sample ------------------------------")
    print(f"{'tier':<38} {'coverage':>9} {'accuracy':>9} {'n':>9}")
    print("-" * 68)
    print(f"{'strong fields only':<38} {strong_cov:>8.1%} {strong_acc:>8.1%} {strong_n:>9,}")
    print(f"{'strong, then Protocol / DataType':<38} {all_cov:>8.1%} {all_acc:>8.1%} {all_n:>9,}")
    print(f"{'Type and Protocol predict and agree':<38} {agree_cov:>8.1%} {agree_acc:>8.1%} {agree_n:>9,}")
    print()
    print(f"the weak fields buy {all_cov - strong_cov:+.1%} coverage "
          f"for {all_acc - strong_acc:+.1%} accuracy")
    print(f"uncovered by any field {test_n - all_n:>9,}  {1 - all_cov:>6.1%}"
          "  (-> the LLM slice)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
