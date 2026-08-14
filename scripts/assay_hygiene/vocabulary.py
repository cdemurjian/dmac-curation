# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Learn which assay a metadata value names, from what curators actually did.

Free text like `cometchip` has to become `internal_assay_id 138` before any
claim can be compared with a registration. That mapping is not guesswork: it is
observed in 1,364 curator-labelled edges. This module derives it from the
labelled population, scores it on held-out samples, and leaves only the
unanchored tail for a human or a model to settle.

Ground truth here is a labelled edge, meaning one where a curator's own
registration caused `internal_assay_id` to be written. Dark edges are excluded
deliberately: a dark edge is the defect this project exists to fix, and learning
from it would launder that defect into the vocabulary as though someone had
asserted it.
"""
from __future__ import annotations

import collections
import json

import pandas as pd

from . import _schema as S


def parse_metadata(samples: pd.DataFrame) -> dict[int, dict]:
    """sample_id -> its parsed json_metadata, skipping blobs that do not parse.

    An unparseable blob reads as "no metadata" rather than raising: it is a data
    defect on one row and must not stop a run over 163,393 samples. It is not
    silently dropped either -- the sample is simply absent from the index, which
    every caller treats as "claims nothing".
    """
    out: dict[int, dict] = {}
    for sid, blob in zip(samples.sample_id, samples.json_metadata):
        if not blob:
            continue
        try:
            d = json.loads(blob)
        except (ValueError, TypeError):
            continue
        if isinstance(d, dict):
            out[int(sid)] = d
    return out


def _tally(edges: pd.DataFrame, meta: dict[int, dict], keep) -> tuple[dict, dict]:
    """Two views of one walk, both keyed by (field, normalised value).

    The Counter is EDGE-weighted -- how many labelled edges named each assay --
    and is what `support`, `purity` and every measured figure in this design are
    defined against. The set of child sample ids is that same evidence counted
    the other way, and it is the only thing separating a term backed by many
    curators from one backed by a single heavily fanned-out sample.
    """
    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    samples: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    for child_id, iaid in zip(edges.child_id, edges.edge_internal_assay_id):
        if pd.isna(iaid):
            continue                      # dark: not ground truth, see module docstring
        child_id = int(child_id)
        if not keep(child_id):
            continue
        d = meta.get(child_id)
        if not d:
            continue
        for field in S.CLAIM_FIELDS:
            value = S.normalise_value(d.get(field))
            if value:
                tally[(field, value)][int(iaid)] += 1
                samples[(field, value)].add(child_id)
    return tally, samples


def learn_vocabulary(
    edges: pd.DataFrame,
    meta: dict[int, dict],
    min_support: int = 3,
) -> pd.DataFrame:
    """Derive the (field, value) -> internal assay mapping from labelled edges.

    `support` is how many labelled EDGES back the mapping and `purity` is the
    winning assay's share of them. Both are carried so a reader can tell a term
    seen 40,000 times at 0.99 from one seen 3 times at 0.67 -- a distinction the
    mapping alone destroys.

    `n_samples` is the check on `support`, and reading support without it is the
    trap. A sample fans out to many edges, so support cannot distinguish a term
    backed by 132 curator-labelled samples from one backed by a single sample
    with 132 edges; on the real extract 50 of 736 learned terms are the latter,
    `Software: matlab` and `Type: github` among them. `min_support` still counts
    edges on purpose -- every figure this design rests on was measured that way,
    so changing it would invalidate the measurement rather than improve it. The
    column makes the weakness legible without moving a number.
    """
    rows = []
    tally, samples = _tally(edges, meta, lambda _: True)
    for (field, value), counter in tally.items():
        total = sum(counter.values())
        if total < min_support:
            continue
        best, best_n = counter.most_common(1)[0]
        rows.append({
            "source_field": field,
            "raw_value": value,
            "internal_assay_id": best,
            "internal_assay_title": None,   # filled by merge_vocabulary from assays
            "support": total,
            "n_samples": len(samples[(field, value)]),
            "purity": best_n / total,
            "provenance": S.P_LEARNED,
        })
    return pd.DataFrame(rows, columns=S.VOCAB_COLUMNS)


def score_vocabulary(
    edges: pd.DataFrame,
    meta: dict[int, dict],
    min_support: int = 3,
) -> pd.DataFrame:
    """Learn on half the samples, predict the other half, report per field.

    The split is BY SAMPLE (`sample_id % 2`), not by edge. A sample fans out to
    many edges -- 146 parents per child in the largest block -- so an
    edge-level split puts the same sample on both sides and scores memorised
    answers rather than generalisation.

    Metadata VALUES are deliberately shared across the split. Aligning a
    vocabulary once and applying it everywhere is the production behaviour; it
    is specific samples that must not leak.
    """
    train, _ = _tally(edges, meta, lambda sid: sid % 2 == 0)
    mapping = {
        k: c.most_common(1)[0][0]
        for k, c in train.items() if sum(c.values()) >= min_support
    }

    per_field: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for child_id, iaid in zip(edges.child_id, edges.edge_internal_assay_id):
        if pd.isna(iaid):
            continue
        child_id = int(child_id)
        if child_id % 2 == 0:
            continue                       # train side
        d = meta.get(child_id) or {}
        for field in S.CLAIM_FIELDS:
            slot = per_field[field]
            slot[2] += 1                   # every test-side edge counts for coverage
            value = S.normalise_value(d.get(field))
            pred = mapping.get((field, value)) if value else None
            if pred is None:
                continue
            if pred == int(iaid):
                slot[0] += 1
            else:
                slot[1] += 1

    rows = []
    for field, (hit, miss, seen) in per_field.items():
        covered = hit + miss
        terms = sum(1 for f, _ in mapping if f == field)
        rows.append({
            "source_field": field,
            "terms": terms,
            "coverage": covered / seen if seen else 0.0,
            "accuracy": hit / covered if covered else 0.0,
        })
    return pd.DataFrame(rows, columns=["source_field", "terms", "coverage", "accuracy"])
