import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import vocabulary as V


def _edges(rows):
    """(child_id, edge_internal_assay_id) pairs as an EDGE_COLUMNS frame."""
    return pd.DataFrame(
        [(c, 900, f"C-{c}", "P-900", "D.IMG", "TIS", a, None, None)
         for c, a in rows],
        columns=S.EDGE_COLUMNS,
    )


def _meta(rows):
    return {sid: d for sid, d in rows}


def test_parse_metadata_skips_unparseable_blobs_without_dropping_the_sample():
    # An unparseable blob is a data defect, not a missing sample. It must read
    # as "no metadata" rather than raising or vanishing silently.
    samples = pd.DataFrame(
        [(1, "A-1", '{"Type": "CometChip"}', None, "10"),
         (2, "A-2", "not json at all", None, "10"),
         (3, "A-3", "", None, "10")],
        columns=S.SAMPLE_COLUMNS,
    )
    meta = V.parse_metadata(samples)
    assert meta[1]["Type"] == "CometChip"
    assert 2 not in meta
    assert 3 not in meta


def test_learn_maps_a_value_to_the_assay_curators_assigned():
    edges = _edges([(1, 11), (2, 11), (3, 11)])
    meta = _meta([(1, {"Type": "CometChip"}),
                  (2, {"Type": "cometchip"}),
                  (3, {"Type": "  CometChip  "})])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    assert list(vocab.columns) == S.VOCAB_COLUMNS
    row = vocab[(vocab.source_field == "Type") & (vocab.raw_value == "cometchip")].iloc[0]
    assert row.internal_assay_id == 11
    assert row.support == 3          # all three normalise to one value
    assert row.purity == 1.0
    assert row.provenance == S.P_LEARNED


def test_learn_drops_values_below_min_support():
    edges = _edges([(1, 11), (2, 12)])
    meta = _meta([(1, {"Type": "rare"}), (2, {"Type": "alsorare"})])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    assert vocab.empty


def test_learn_takes_the_majority_and_records_impurity():
    # A value that mostly means one assay but not always is still usable; the
    # purity column is how a reader sees that it is not clean.
    edges = _edges([(1, 11), (2, 11), (3, 11), (4, 12)])
    meta = _meta([(i, {"Type": "mixed"}) for i in (1, 2, 3, 4)])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    row = vocab.iloc[0]
    assert row.internal_assay_id == 11
    assert row.support == 4
    assert row.purity == pytest.approx(0.75)


def test_learn_ignores_dark_edges_because_they_are_not_ground_truth():
    # A dark edge is the thing being fixed. Learning from it would launder the
    # defect into the vocabulary as if a curator had asserted it.
    edges = _edges([(1, None), (2, None), (3, None)])
    meta = _meta([(i, {"Type": "cometchip"}) for i in (1, 2, 3)])
    assert V.learn_vocabulary(edges, meta, min_support=3).empty


def test_score_holds_out_by_sample_and_reports_per_field():
    # 8 samples, ids alternating parity so the split is even.
    edges = _edges([(i, 11) for i in range(1, 9)])
    meta = _meta([(i, {"Type": "cometchip"}) for i in range(1, 9)])
    scored = V.score_vocabulary(edges, meta, min_support=2)
    row = scored[scored.source_field == "Type"].iloc[0]
    assert row.coverage == 1.0
    assert row.accuracy == 1.0

    # Above, every sample carries the same value on the same assay, so a run
    # that trained on everything and scored everything reports 100% too --
    # confirmed by mutating each split guard out and watching the block above
    # stay green. Each sample below breaks one specific way of getting it wrong:
    #
    #   2      TRAIN side, and its edge DISAGREES with what "cometchip"
    #          predicts -> scoring the train side surfaces it as a miss
    #   10     TRAIN side, Type value seen once, under min_support
    #          -> ignoring min_support surfaces it as a second learned term
    #   9, 11  TEST side only, and the only samples carrying Instrument
    #          -> training on everything surfaces Instrument as learned
    #   13     TEST side, no metadata at all -> it still counts against
    #          coverage, whose denominator is labelled EDGES and not
    #          edges-that-have-the-field
    edges = _edges([(i, 12 if i == 2 else 11)
                    for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13)])
    meta = _meta(
        [(i, {"Type": "cometchip"}) for i in range(1, 9)]
        + [(10, {"Type": "seen once in train"})]
        + [(i, {"Type": "cometchip", "Instrument": "test side only"})
           for i in (9, 11)]
    )
    scored = V.score_vocabulary(edges, meta, min_support=2)
    typ = scored[scored.source_field == "Type"].iloc[0]
    assert typ.terms == 1
    assert typ.coverage == pytest.approx(6 / 7)
    assert typ.accuracy == 1.0       # sample 2's miss is on the train side
    inst = scored[scored.source_field == "Instrument"].iloc[0]
    assert inst.terms == 0           # a test-side-only value is never learned
    assert inst.coverage == 0.0
