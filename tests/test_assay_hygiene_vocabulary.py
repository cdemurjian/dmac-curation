import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import vocabulary as V


def _edges(rows):
    """(child_id, edge_internal_assay_id[, parent_id]) as an EDGE_COLUMNS frame.

    `parent_id` defaults to 900 and is worth passing explicitly whenever a
    sample needs SEVERAL edges. With one edge per sample, a by-sample split and
    an edge-level split are indistinguishable, so the module's headline claim --
    that the hold-out is by sample, because a child fans out to as many as 146
    parents -- cannot be observed at all.
    """
    out = []
    for row in rows:
        child_id, assay_id = row[0], row[1]
        parent_id = row[2] if len(row) > 2 else 900
        out.append((child_id, parent_id, f"C-{child_id}", f"P-{parent_id}",
                    "D.IMG", "TIS", assay_id, None, None))
    return pd.DataFrame(out, columns=S.EDGE_COLUMNS)


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


def test_n_samples_separates_fan_out_from_independent_support():
    # `support` counts EDGES, so a term clears min_support off a single sample
    # that happens to have many parents. On the real extract 50 of the 736
    # learned terms are exactly that -- `Software: matlab` reads as support 132
    # from one sample. The two terms below are indistinguishable by support,
    # purity and provenance alike; n_samples is the only column separating one
    # curator's row from three independent ones.
    edges = _edges([(1, 11, 900), (1, 11, 901), (1, 11, 902),
                    (2, 11, 900), (3, 11, 900), (4, 11, 900)])
    meta = _meta([(1, {"Type": "one sample, three parents"})]
                 + [(i, {"Type": "three separate samples"}) for i in (2, 3, 4)])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    fan = vocab[vocab.raw_value == "one sample, three parents"].iloc[0]
    indep = vocab[vocab.raw_value == "three separate samples"].iloc[0]
    assert fan.support == 3 and indep.support == 3       # identical by support
    assert fan.purity == 1.0 and indep.purity == 1.0     # and by purity
    assert fan.n_samples == 1                            # but one sample backs it
    assert indep.n_samples == 3                          # against three


def test_learn_ignores_dark_edges_because_they_are_not_ground_truth():
    # A dark edge is the thing being fixed. Learning from it would launder the
    # defect into the vocabulary as if a curator had asserted it.
    #
    # Sample 4 is labelled and carries the SAME value as the three dark ones,
    # and it is here for two reasons. It makes the assertion below sharp: only
    # one labelled edge backs "cometchip", so a run that counted the dark three
    # would reach support 4, clear min_support and return a row. And an all-dark
    # column infers as object dtype holding None, whereas production's
    # edges.parquet is float64 holding NaN (434,566 of 794,593 rows); mixing a
    # labelled row in reproduces the production dtype, so a guard narrowed to
    # `iaid is None` fails here instead of passing here and raising on the real
    # extract.
    edges = _edges([(1, None), (2, None), (3, None), (4, 11)])
    meta = _meta([(i, {"Type": "cometchip"}) for i in (1, 2, 3, 4)])
    assert edges.edge_internal_assay_id.dtype == "float64"
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
    #   9      additionally FANS OUT to parents 901 and 903. Every other sample
    #          here has one edge, and with one edge per sample a by-sample split
    #          and an edge-level split are the same function, so the property
    #          this test is named for is unobservable. Under a split on
    #          (child_id + parent_id), 9's two extra edges land on the train
    #          side while 9 itself is test-side, which is precisely the leak the
    #          by-sample split exists to prevent: Instrument would be learned
    #          off a sample the scorer then grades.
    edges = _edges([(i, 12 if i == 2 else 11)
                    for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13)]
                   + [(9, 11, 901), (9, 11, 903)])
    meta = _meta(
        [(i, {"Type": "cometchip"}) for i in range(1, 9)]
        + [(10, {"Type": "seen once in train"})]
        + [(i, {"Type": "cometchip", "Instrument": "test side only"})
           for i in (9, 11)]
    )
    scored = V.score_vocabulary(edges, meta, min_support=2)
    typ = scored[scored.source_field == "Type"].iloc[0]
    assert typ.terms == 1
    assert typ.coverage == pytest.approx(8 / 9)
    assert typ.accuracy == 1.0       # sample 2's miss is on the train side
    inst = scored[scored.source_field == "Instrument"].iloc[0]
    assert inst.terms == 0           # a test-side-only value is never learned
    assert inst.coverage == 0.0


def _vocab(rows):
    return pd.DataFrame(rows, columns=S.VOCAB_COLUMNS)


def _assays():
    """Two registered assays plus one junction-less one, as production has.

    Row 3 mirrors the 17 production assays with no row in
    `dmac.assays_internal_assays`: a seek `assay_id` and a `title`, but NULL in
    both internal columns. It is what makes the seek-fallback guard below
    non-vacuous -- without such a row in the frame, a merge that wrongly keyed
    titles off `assay_id` would have nothing to wrongly find.

    Row 4 has a real internal_assay_id but a NULL internal_assay_title. No such
    row exists in today's extract, so it is here to keep a latent defect from
    going live: `str(float('nan'))` is the string `"nan"`, so an unguarded
    titles lookup would hand that string out as a display title.
    """
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
         (466, "Library Prep", 9, 3, 2, 10, "MIT_SRP", None, None),
         (3, "Untitled Internal", 9, 3, 2, 10, "MIT_SRP", 13, None)],
        columns=S.ASSAY_COLUMNS,
    )


def test_curator_rows_beat_learned_and_proposed():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    proposed = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_PROPOSED)])
    curator = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(learned, proposed, curator, _assays())
    row = out[out.raw_value == "cometchip"].iloc[0]
    assert row.internal_assay_id == 12
    assert row.provenance == S.P_CURATOR
    assert len(out) == 1


def test_learned_beats_proposed_when_no_curator_row_exists():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    proposed = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_PROPOSED)])
    out = V.merge_vocabulary(learned, proposed, _vocab([]), _assays())
    assert out.iloc[0].internal_assay_id == 11
    assert out.iloc[0].provenance == S.P_LEARNED
    # The evidence columns must survive the merge. `support` counts EDGES and
    # `n_samples` distinct child samples, and the second is the only thing that
    # tells a term backed by 850 curators from one backed by a single sample
    # fanned out over 900 edges. A merge that rebuilt rows from the mapping
    # alone, or zeroed the counts it did not understand, would still satisfy
    # every other assertion in this file.
    assert out.iloc[0].support == 900
    assert out.iloc[0].n_samples == 850
    assert out.iloc[0].purity == pytest.approx(0.99)


def test_merge_fills_the_display_title_from_the_assays_frame():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    out = V.merge_vocabulary(learned, _vocab([]), _vocab([]), _assays())
    assert out.iloc[0].internal_assay_title == "Comet Chip"


def test_merge_is_deterministic_when_one_source_repeats_a_key():
    # vocabulary.csv is hand-editable by design (load_vocabulary's docstring
    # says so), and the natural way to correct a hand-edited file is to append
    # the new row rather than find and rewrite the old one. That puts TWO
    # curator rows on one key, and precedence alone cannot separate them.
    #
    # This is not hypothetical ordering pedantry. pandas' default sort kind is
    # quicksort, which is not stable: measured 2026-08-14 on pandas 3.0.5, a
    # frame of 5,000 rows with ranks drawn from {0,1,2} had the default sort
    # hand drop_duplicates(keep="last") row 1 where a stable sort handed it row
    # 4,998. So without an explicit stable sort the curator's LATEST decision is
    # not merely unspecified, it is usually discarded -- and silently, because
    # the losing row leaves no trace in the output.
    #
    # The frame below is sized and shaped to actually observe that: the winner
    # is verified against a stable sort of the same input rather than asserted
    # from a hand-traced index, and the padding rows supply the rank variety
    # quicksort needs before it reorders anything.
    pad = _vocab([(f"Type", f"filler{i}", 11, None, 3, 3, 1.0,
                   (S.P_PROPOSED, S.P_LEARNED, S.P_CURATOR)[i % 3])
                  for i in range(3000)])
    dupes = _vocab([("Type", "cometchip", 11, None, 0, 0, 0.0, S.P_CURATOR),
                    ("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_CURATOR)])
    # curator rows first, then padding, so the duplicated pair sits at the head
    # of the frame where an unstable partition is most likely to move it.
    curator = pd.concat([dupes, pad], ignore_index=True)
    out = V.merge_vocabulary(_vocab([]), _vocab([]), curator, _assays())
    row = out[out.raw_value == "cometchip"].iloc[0]
    # last row for the key wins: the correction, not the row it corrected
    assert row.internal_assay_id == 12
    assert row.internal_assay_title == "Tissue Collection"
    assert len(out[out.raw_value == "cometchip"]) == 1
    # and it is reproducible: same input, same answer, every time
    for _ in range(5):
        again = V.merge_vocabulary(_vocab([]), _vocab([]), curator, _assays())
        assert again[again.raw_value == "cometchip"].iloc[0].internal_assay_id == 12


def test_unresolved_lists_frequent_terms_the_vocabulary_cannot_map():
    # Sample 1 and samples 6/7 all name the same assay as the vocabulary row,
    # but spell it three ways. The vocabulary row is spelled the way a CURATOR
    # would type it (`CometChip`), not the way learn_vocabulary emits it, which
    # is the case that separates a real lookup from a string compare: without
    # normalising BOTH sides, `cometchip` is reported as an unresolved term
    # backed by 3 samples even though the vocabulary maps it, and it lands in
    # Task 4's judgment queue for a human to rule on a question already answered.
    meta = {1: {"Type": "CometChip"}, 2: {"Type": "mystery"},
            3: {"Type": "mystery"}, 4: {"Type": "mystery"}, 5: {"Type": "once"},
            6: {"Type": "cometchip"}, 7: {"Type": "  COMETCHIP "}}
    uuids = {1: "A-1", 2: "A-2", 3: "A-3", 4: "A-4", 5: "A-5",
             6: "A-6", 7: "A-7"}
    vocab = _vocab([("Type", "CometChip", 11, "Comet Chip", 900, 850, 0.99,
                     S.P_LEARNED)])
    out = V.unresolved_terms(meta, vocab, uuids, min_occurrences=3)
    assert list(out.raw_value) == ["mystery"]     # 'once' is below the floor
    assert out.iloc[0].n_samples == 3
    assert "A-2" in out.iloc[0].example_uuids


def test_vocabulary_round_trips_through_csv(tmp_path):
    # Row 2 is the reason load_vocabulary passes keep_default_na=False. `nan`
    # and `null` are real strings a curator may have typed into a metadata
    # field, and pandas' default na_values would read them back as MISSING --
    # silently changing which value the row maps rather than failing. Verified
    # 2026-08-14 on pandas 3.0.5: a plain read_csv returns float nan here.
    df = _vocab([("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
                 ("Software", "nan", 12, "Tissue Collection", 5, 5, 1.0, S.P_CURATOR)])
    p = tmp_path / "vocabulary.csv"
    V.save_vocabulary(df, p)
    back = V.load_vocabulary(p)
    assert list(back.columns) == S.VOCAB_COLUMNS
    assert back.iloc[0].internal_assay_id == 11
    assert back.iloc[0].raw_value == "cometchip"
    assert back.iloc[1].raw_value == "nan"
    assert isinstance(back.iloc[1].raw_value, str)


def test_a_curator_spelling_variant_overrides_the_learned_row():
    # The curator writes the term the way it appears in the metadata; the
    # learned row carries it normalised. If the merge keys on the raw string
    # these are two terms, so BOTH rows survive and every consumer -- which
    # looks up the normalised metadata value -- finds the learned row. The
    # curator's override is not merely lost, it is unobservable: the artifact
    # shows their row sitting right there in the file, apparently in effect.
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    curator = _vocab([("Type", "CometChip", 12, None, 0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(learned, _vocab([]), curator, _assays())
    assert len(out) == 1                       # one term, not two
    assert out.iloc[0].raw_value == "cometchip"
    assert out.iloc[0].internal_assay_id == 12
    assert out.iloc[0].provenance == S.P_CURATOR


def test_a_junction_less_id_is_never_titled_from_the_seek_assays_frame():
    # THIS TEST IS A GUARD, and the edit it guards against is an attractive one:
    # id 466 is right there in the assays frame with the title "Library Prep",
    # and titling off `assay_id` fills 14 otherwise-blank rows with correct
    # strings. It is still wrong. `edge_internal_assay_id` carries a SEEK
    # assays.id for the 17 junction-less assays and a dmac internal_assays.id
    # for every other row, and the two spaces overlap: measured 2026-08-14,
    # 124 of the 458 seek assay_ids equal a genuine internal_assay_id, and 122
    # of those 124 name a DIFFERENT assay -- seek 13 is `Short Read Sequencing`
    # where internal 13 is `Cell Sorting`, seek 24 is `Single Cell Clustering
    # Analysis` where internal 24 is `DNA Extraction`. (Only ids 47 and 74 carry
    # the same title in both spaces.) Today's junction-less
    # ids happen to sit at 466-482, above the 1-188 internal range, and that
    # accident is the only reason such a fallback is not already mislabelling
    # rows. One new junction-less assay with a low id ends the accident.
    #
    # A blank title is also the only signal that the junction row is missing,
    # which is a hygiene defect of exactly the kind this package surfaces.
    learned = _vocab([("Type", "libraryprep", 466, None, 4, 4, 1.0, S.P_LEARNED)])
    out = V.merge_vocabulary(learned, _vocab([]), _vocab([]), _assays())
    assert out.iloc[0].internal_assay_id == 466
    assert pd.isna(out.iloc[0].internal_assay_title), (
        "a junction-less internal_assay_id was titled from assays.assay_id; "
        "see this test's comment for why that is wrong even though the title "
        "it produces looks right"
    )


def test_an_authoritative_title_overrides_a_hand_typed_one():
    # The rebuild half of the rule: where the assays frame has a title, it is
    # the truth, so a stale or wrong hand-edit cannot travel onward.
    curator = _vocab([("Type", "cometchip", 11, "Stale Renamed Assay",
                       0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(_vocab([]), _vocab([]), curator, _assays())
    assert out.iloc[0].internal_assay_title == "Comet Chip"


def test_a_hand_typed_title_survives_where_no_authoritative_title_exists():
    # The other half, and the reason the rebuild is conditional. vocabulary.csv
    # is the durable artifact this project produces and it exists to be
    # hand-corrected. For a junction-less id the assays frame has nothing to
    # rebuild from, so an unconditional rebuild would discard the curator's
    # title on every run and leave those 14 rows permanently blank -- the one
    # gap a curator can actually close, held open by the tool.
    curator = _vocab([("Type", "libraryprep", 466, "Library Prep (per PI)",
                       0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(_vocab([]), _vocab([]), curator, _assays())
    assert out.iloc[0].internal_assay_title == "Library Prep (per PI)"


def test_a_wholly_numeric_curator_file_survives_the_round_trip(tmp_path):
    # These are the 12 bare-numeric Protocol terms sitting in the live
    # unresolved queue on 2026-08-14. A curator ruling on exactly this batch is
    # a natural unit of work and writes a curator.csv whose raw_value column is
    # entirely numeric -- whereupon read_csv infers int64, the merge's
    # normalise_value returns None for every non-str, all 12 rows collapse onto
    # one None key and 11 curator decisions are deleted without a trace.
    # Measured before the dtype pin: 13 rows in, 2 out.
    #
    # The keys are text. They are read as text. The pin lives in the loader and
    # not in normalise_value, because this package has exactly one normaliser.
    ids = ["18032418", "22010444", "22071552", "23012317", "21048970",
           "17050656", "17029987", "15066174", "19014206", "24095281",
           "18052927", "25036254"]
    curator = _vocab([("Protocol", v, 11, None, 0, 0, 0.0, S.P_CURATOR)
                      for v in ids])
    p = tmp_path / "curator.csv"
    V.save_vocabulary(curator, p)
    back = V.load_vocabulary(p)

    assert list(back.raw_value) == ids, "numeric keys did not survive the load"
    assert all(isinstance(v, str) for v in back.raw_value)

    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    out = V.merge_vocabulary(learned, _vocab([]), back, _assays())
    assert len(out) == 13, "curator decisions were collapsed by the merge"
    assert sorted(out[out.provenance == S.P_CURATOR].raw_value) == sorted(ids)
    assert out.raw_value.notna().all()

    # A single-row numeric file is voided by the same mechanism, and a one-row
    # file cannot show up as a row-count drop, so pin it separately.
    solo = _vocab([("Protocol", "18032418", 11, None, 0, 0, 0.0, S.P_CURATOR)])
    q = tmp_path / "solo.csv"
    V.save_vocabulary(solo, q)
    assert V.load_vocabulary(q).iloc[0].raw_value == "18032418"


def test_a_null_authoritative_title_does_not_overwrite_a_hand_typed_one():
    # assays row 4 has internal_assay_id 13 and a NULL title. Unguarded, that
    # enters the titles dict as the literal string "nan" -- str(float('nan')) --
    # and because the rebuild prefers the dict over the row's own value, it
    # OVERWRITES the curator's title. That inverts the rule the conditional
    # rebuild exists to enforce: a null is not an authoritative title, so the
    # row must keep its own. No such assays row exists today; this is a latent
    # guard, and the failure mode it prevents is a curator seeing the word "nan"
    # where they typed a name.
    curator = _vocab([("Type", "somevalue", 13, "Hand Typed By Curator",
                       0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(_vocab([]), _vocab([]), curator, _assays())
    assert out.iloc[0].internal_assay_title == "Hand Typed By Curator"
