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

EXTRACT = Path("assay-hygiene/extract")

# Free-text fields that plausibly name an assay. Chosen by inspecting the
# populated keys on the CometChip block; scored independently below so a field
# that turns out to be noise is visible rather than averaged away.
CANDIDATE_FIELDS = [
    "Type", "Protocol", "DataType", "SlideStain", "Instrument",
    "Assay", "Software", "Channels", "Stains", "Stimulation",
]

MIN_SUPPORT = 3  # a value seen fewer times than this in train predicts nothing


def norm(v) -> str | None:
    """Free text, lowercased and stripped. `Liver/liver/LIVER` is three values."""
    if not isinstance(v, str):
        return None
    s = " ".join(v.split()).strip().lower()
    return s or None


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

    results = []
    for field in CANDIDATE_FIELDS:
        # learn: value -> most common internal_assay_id, from TRAIN only
        tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for child_id, iaid in rows:
            if not in_train(child_id):
                continue
            v = norm((meta.get(child_id) or {}).get(field))
            if v:
                tally[v][iaid] += 1

        mapping: dict[str, int] = {}
        purity_num = purity_den = 0
        for v, c in tally.items():
            total = sum(c.values())
            if total < MIN_SUPPORT:
                continue
            best, best_n = c.most_common(1)[0]
            mapping[v] = best
            purity_num += best_n
            purity_den += total

        # predict on TEST
        hit = miss = nopred = 0
        for child_id, iaid in rows:
            if in_train(child_id):
                continue
            v = norm((meta.get(child_id) or {}).get(field))
            pred = mapping.get(v) if v else None
            if pred is None:
                nopred += 1
            elif pred == iaid:
                hit += 1
            else:
                miss += 1

        covered = hit + miss
        acc = hit / covered if covered else 0.0
        cov = covered / (len(rows) - n_train) if rows else 0.0
        purity = purity_num / purity_den if purity_den else 0.0
        results.append((field, len(mapping), cov, acc, purity))

    print(f"{'field':<14} {'terms':>6} {'coverage':>9} {'accuracy':>9} {'train purity':>13}")
    print("-" * 56)
    for field, terms, cov, acc, purity in sorted(results, key=lambda r: -r[2] * r[3]):
        print(f"{field:<14} {terms:>6,} {cov:>8.1%} {acc:>8.1%} {purity:>12.1%}")

    # --- combined: first field that predicts wins, in the order above --------
    tallies = {}
    for field in CANDIDATE_FIELDS:
        t: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for child_id, iaid in rows:
            if in_train(child_id):
                v = norm((meta.get(child_id) or {}).get(field))
                if v:
                    t[v][iaid] += 1
        tallies[field] = {
            v: c.most_common(1)[0][0]
            for v, c in t.items() if sum(c.values()) >= MIN_SUPPORT
        }

    hit = miss = nopred = 0
    agree_hit = agree_miss = disagree = 0
    for child_id, iaid in rows:
        if in_train(child_id):
            continue
        d = meta.get(child_id) or {}
        preds = []
        for field in CANDIDATE_FIELDS:
            v = norm(d.get(field))
            p = tallies[field].get(v) if v else None
            if p is not None:
                preds.append(p)
        if not preds:
            nopred += 1
            continue
        if len(set(preds)) == 1:
            (p,) = set(preds)
            if p == iaid:
                agree_hit += 1
            else:
                agree_miss += 1
        else:
            disagree += 1
        if preds[0] == iaid:
            hit += 1
        else:
            miss += 1

    test_n = len(rows) - n_train
    print()
    print("--- combined, first populated field wins --------------------------")
    print(f"predicted   {hit + miss:>9,}  {(hit + miss) / test_n:>6.1%} of test")
    print(f"  correct   {hit:>9,}  {hit / (hit + miss) if hit + miss else 0:>6.1%} accuracy")
    print(f"no prediction {nopred:>7,}  {nopred / test_n:>6.1%}")
    print()
    print("--- when every populated field agrees ------------------------------")
    tot_agree = agree_hit + agree_miss
    print(f"unanimous   {tot_agree:>9,}  {tot_agree / test_n:>6.1%} of test")
    print(f"  correct   {agree_hit:>9,}  {agree_hit / tot_agree if tot_agree else 0:>6.1%} accuracy")
    print(f"fields disagree {disagree:>7,}  {disagree / test_n:>6.1%}  (-> the LLM slice)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
