"""Task 8: the end-to-end run, and the report an operator judges the layer by.

DELIBERATE STRENGTHENING OF THE BRIEF'S FIRST CASE. As written in the brief,
`test_report_states_every_headline_count` asserted three things: that the
precedent count appeared, that the literal "Mode 3" appeared, and that one
vocabulary term appeared. It never looked at the claims count, the sample
count, the flag count or the unresolved count -- so a report that silently
dropped any of them stayed green under a title promising the opposite. Four
tests in this package have already certified a property in their own title
without testing it; this one now asserts every count the report is responsible
for.

FIXTURE NUMBERS ARE ALL DISTINCT, on purpose. A report is a wall of formatted
integers, so an assertion looking for `2` in a fixture where three different
facts are all 2 passes on whichever one happens to be printed. Every headline
here is a different number (vocabulary 4, thin 1, unresolved 2 over 12
occurrences, rules 1 over 1 pair, claims 6 over 5 samples, flags 3 over 3
samples in 2 patterns) and each is asserted against ITS OWN line rather than
against the whole document.

THE `samples` ASSERTION ON THE UNRESOLVED LINE IS THE ONE THAT CAUGHT A REAL
DEFECT. `unresolved.n_samples.sum()` adds per-term sample counts, so a sample
carrying two unresolved terms is counted twice; the brief's report printed that
sum and labelled it "samples". Measured on the real extract the two differ by
65% (24,322 occurrences against 14,753 distinct samples), and the second is the
figure the design quotes. See test_the_unresolved_line_does_not_call_the
_occurrence_sum_a_sample_count, folded into the first case below.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import run_evidence as R  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402


def _frames():
    """One coherent little world, every headline a different integer."""
    # the two `_samples` counts equal their edge counts: one relative each, so
    # this world has no fan-out and nothing here reads the difference. See
    # `precedent.mine_precedent` for the grain and the case where they differ.
    precedent = pd.DataFrame(
        [(10, "D.IMG", "TIS", 11, "Comet Chip", 2, 1, 1, 0, 0, 2 / 3, 1.0)],
        columns=S.PRECEDENT_COLUMNS,
    )
    # 6 claims over 5 distinct samples; tiers 1 corroborated / 4 strong / 1
    # weak; sample 104 contests itself with two strong claims.
    claims = pd.DataFrame(
        [
            (100, "D.IMG-1", 11, "Comet Chip", S.T_CORROBORATED,
             "Type", "CometChip", False, S.P_LEARNED),
            (101, "D.IMG-2", 11, "Comet Chip", S.T_STRONG,
             "Type", "CometChip", False, S.P_LEARNED),
            (102, "RNA-1", 24, "RNA Extraction", S.T_STRONG,
             "Type", "total RNA", False, S.P_LEARNED),
            (103, "A.FLOW-1", 30, "Flow Cytometry", S.T_WEAK,
             "Protocol", "flow.docx", False, S.P_LEARNED),
            (104, "DNA-1", 11, "Comet Chip", S.T_STRONG,
             "Type", "CometChip", True, S.P_LEARNED),
            (104, "DNA-1", 24, "RNA Extraction", S.T_STRONG,
             "Type", "total RNA", True, S.P_LEARNED),
        ],
        columns=S.CLAIM_COLUMNS,
    )
    # 3 flags over 3 samples, collapsing to 2 patterns: the first two rows are
    # the same contradiction seen twice, which is exactly the structure the
    # rollup exists to expose.
    audit = pd.DataFrame(
        [
            (101, "D.IMG-2", "D.IMG", "12", "Tissue Collection", 11,
             "Comet Chip", S.T_STRONG, "Type", "CometChip", S.V_MODE3_FLAG),
            (105, "D.IMG-9", "D.IMG", "12", "Tissue Collection", 11,
             "Comet Chip", S.T_STRONG, "Type", "CometChip", S.V_MODE3_FLAG),
            (102, "RNA-1", "RNA", "115", "Library Creation", 24,
             "RNA Extraction", S.T_CORROBORATED, "Type", "total RNA",
             S.V_MODE3_FLAG),
        ],
        columns=S.AUDIT_COLUMNS,
    )
    # 4 terms, one of which rests on a single sample despite support 60 --
    # the pathology `n_samples` was added to make visible.
    vocab = pd.DataFrame(
        [
            ("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
            ("Type", "total rna", 24, "RNA Extraction", 400, 380, 0.95,
             S.P_LEARNED),
            ("Software", "flowjo", 30, "Flow Cytometry", 120, 95, 0.98,
             S.P_LEARNED),
            ("Protocol", "comet.docx", 11, "Comet Chip", 60, 1, 0.80,
             S.P_CURATOR),
        ],
        columns=S.VOCAB_COLUMNS,
    )
    unresolved = pd.DataFrame(
        [("Type", "mystery", 7, "A-2; A-3; A-4"),
         ("Protocol", "12345", 5, "B-1; B-2; B-3")],
        columns=["source_field", "raw_value", "n_samples", "example_uuids"],
    )
    return precedent, claims, audit, vocab, unresolved


def _line(md: str, needle: str) -> str:
    """The report line(s) mentioning `needle`, joined.

    Asserting against a whole document lets a number satisfy an assertion from
    an unrelated line; every count below is checked against the line that is
    supposed to carry it.
    """
    hits = [ln for ln in md.splitlines() if needle in ln]
    assert hits, f"no line mentioning {needle!r} in report:\n{md}"
    return " ".join(hits)


def test_report_states_every_headline_count():
    md = R.build_report(*_frames())

    # vocabulary: size, and the single-sample weakness that `n_samples` exists
    # to surface
    assert "**4**" in _line(md, "mapped terms")
    assert "**1**" in _line(md, "distinct sample")

    # unresolved: the term count, and the occurrence sum NOT called a sample
    # count. See the module docstring -- this is the defect the case caught.
    unresolved_line = _line(md, "unresolved terms")
    assert "**2**" in unresolved_line
    assert "12" in unresolved_line and "occurrence" in unresolved_line
    assert "sample" not in unresolved_line, (
        "the sum of per-term n_samples is an OCCURRENCE count, not a sample "
        "count: a sample carrying two unresolved terms is counted twice. "
        "Measured on the real extract the two differ by 65% -- 24,322 "
        "occurrences against 14,753 distinct samples -- and the second is the "
        f"figure the design quotes. Line was: {unresolved_line!r}"
    )

    # precedent: rules, and the project/hop pairs they cover
    rules_line = _line(md, "rules mined")
    assert "**1**" in rules_line and "pair" in rules_line

    # claims: rows and the distinct samples carrying them, which differ
    claims_line = _line(md, "claims:")
    assert "**6**" in claims_line and "**5**" in claims_line
    assert "**4**" in _line(md, S.T_STRONG)

    # Mode 3: flags, samples, and the pattern structure a curator rules on
    assert "Mode 3" in md
    flag_line = _line(md, "flagged")
    assert "**3**" in flag_line
    assert "**2**" in _line(md, "pattern")

    # the vocabulary is SHOWN, not merely counted
    assert "cometchip" in md


def test_unresolved_sample_count_counts_samples_not_occurrences():
    """The function that fixes the occurrence/sample defect, tested on its own.

    Sample 1 carries BOTH unresolved terms and sample 2 carries one, so the
    per-term sum is 3 and the answer is 2. That gap is the entire reason the
    function exists; a fixture where every sample carried exactly one term
    would be satisfied by the very implementation it replaced.

    Also pinned: a term the vocabulary DID resolve contributes nothing (sample
    3 carries only `cometchip`, which is not in the tail), the sample's raw
    value is normalised before comparison (`MYSTERY` matches `mystery`), and a
    sample carrying no claim field at all is not counted.
    """
    unresolved = pd.DataFrame(
        [("Type", "mystery", 2, "u-1; u-2"),
         ("Protocol", "12345", 1, "u-1")],
        columns=["source_field", "raw_value", "n_samples", "example_uuids"],
    )
    meta = {
        1: {"Type": "MYSTERY", "Protocol": "12345"},   # both terms, one sample
        2: {"Type": "mystery"},                        # one term
        3: {"Type": "cometchip"},                      # resolved -> not counted
        4: {"Name": "no claim fields at all"},         # nothing -> not counted
    }
    assert int(unresolved.n_samples.sum()) == 3, "fixture must carry the gap"
    assert R.unresolved_sample_count(meta, unresolved) == 2
    # an empty tail is 0, not a crash
    assert R.unresolved_sample_count(meta, unresolved.iloc[:0]) == 0


def _heldout():
    """A held-out tally over the _frames() vocabulary, spanning two bands.

    `comet.docx` sits at purity 0.80 and the other three at 0.95-0.99, so the
    0.75-0.90 band and the >=0.90 band both carry test edges and the worst band
    is decided by the numbers rather than by which row it is.
    """
    return {("Protocol", "comet.docx"): (60, 100),      # 60.0%, band 0.75-0.90
            ("Type", "cometchip"): (990, 1000),         # 99.0%, band >=0.90
            ("Type", "total rna"): (90, 100),           # 90.0%, band >=0.90
            ("Software", "flowjo"): (100, 100)}         # 100%,  band >=0.90


def test_the_flag_accuracy_caveat_travels_with_the_tier_accuracies():
    """98.4% must not be readable as the accuracy of a flag.

    A flag is by construction drawn from the ambiguous tail the aggregate
    averages away -- measured on the real extract, median purity 0.707 behind a
    flag against 1.000 across all flag-eligible claims, and the purity<0.75 band
    scoring far below the >=0.90 one. So the caveat is pinned to the SAME
    stretch of report as the numbers it qualifies, rather than left to a
    footnote a reader reaches after the flag table.

    The band figure is asserted AGAINST THE COMPUTED TABLE and never against a
    literal. Those figures sat hard-coded in the markdown ten lines below a
    docstring saying such a number must be computed "because ... a hard-coded
    one goes stale the first time the vocabulary moves", and this test's
    `65.8%` is what cemented them there.
    """
    frames = _frames()
    heldout = _heldout()
    bands = R.purity_band_accuracy(heldout, frames[3])
    md = R.build_report(*frames, purity_bands=bands,
                        flag_drivers=R.flag_driver_accuracy(frames[2], heldout))
    head = md.split("## Mode 3")[0]
    assert "98.4%" in head, "fixture no longer exercises the tier accuracies"
    between = head.split("98.4%")[1]
    assert "Mode 3" in between, (
        "the tier accuracies are printed with no caveat before the flag "
        "section; a reader carries 98.4% straight into the flag table"
    )
    banded = bands.iloc[1:]
    worst = banded[banded.tested > 0].sort_values("accuracy").iloc[0]
    assert f"{worst.accuracy:.1%}" in between and "purity" in between, (
        "the caveat must carry the measured band accuracy, not just a warning"
    )
    # and the emphasised band is the worst one, chosen by measurement
    assert f"**{worst.accuracy:.1%}**" in between


def test_the_field_accuracies_name_their_population_and_their_source():
    """90.4% is the CASCADE, not the accuracy of a weak claim.

    Re-measured 2026-08-15 with `scripts/measure_metadata_accuracy.py` over the
    real extract, held out by sample against 179,848 labelled test edges:

        strong fields only                  98.4%   118,493
        strong, then Protocol / DataType    90.4%   166,082   <- the cascade
        weak fields ONLY                    89.2%   153,309
        Type and Protocol agree             99.9%    62,957

    The report printed "`weak` 90.4%" directly beneath the count of weak claims,
    where it reads as their accuracy -- while 90.4% is the whole cascade, and
    the strong half is what carries it.

    These three are the only figures in the report its own run does not compute,
    so the text must say so and name what does. Otherwise a reader re-runs the
    layer and believes they revalidated them.
    """
    section = R.build_report(*_frames()).split("## Claims")[1].split("## Mode 3")[0]
    assert "`weak` 90.4%" not in section, (
        "90.4% is the strong-then-weak cascade over 166,082 edges, printed "
        "beside the weak claim count where it reads as their accuracy"
    )
    assert "89.2%" in section and "153,309" in section, (
        "the weak-fields-only figure and its population must both appear"
    )
    assert "98.4%" in section and "118,493" in section
    assert "measure_metadata_accuracy.py" in section, (
        "the three quoted figures must name the script that produces them"
    )
    assert "not recomputed" in section, (
        "the report must say these are quoted, or a reader re-running the "
        "layer believes they revalidated them"
    )


def test_the_purity_bands_are_computed_and_always_sum_to_the_total():
    vocab = pd.DataFrame(
        [("Type", "low", 11, "A", 10, 10, 0.50, S.P_LEARNED),
         ("Type", "mid", 11, "A", 10, 10, 0.80, S.P_LEARNED),
         ("Type", "high", 11, "A", 10, 10, 0.99, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    heldout = {("Type", "low"): (1, 4), ("Type", "mid"): (3, 4),
               ("Type", "high"): (4, 4),
               # a term the vocabulary carries no purity for. None exist today,
               # and a silent skip is how "none exist today" becomes a total
               # that does not match the rows beneath it.
               ("Type", "orphan"): (5, 10)}
    out = R.purity_band_accuracy(heldout, vocab)
    # The total row names the SCORED population and never the vocabulary. The
    # fixture separates the two deliberately -- 3 terms in the vocabulary, 4
    # scored -- because a `len(vocab)` label reads as maintained and is wrong
    # the moment a curator writes the proposals file this package asks them
    # for: 736 becomes 916 while the measurement does not move, attributing a
    # fixed 333,717-edge result to 180 untrusted proposal rows.
    assert out.iloc[0].band == "all 4 scored terms", out.iloc[0].band
    by_band = dict(zip(out.band, zip(out.hits, out.tested)))
    assert by_band["< 0.75"] == (1, 4)
    assert by_band["0.75 - 0.90"] == (3, 4)
    assert by_band[">= 0.90"] == (4, 4)
    assert by_band["unbanded (no purity in the vocabulary)"] == (5, 10)
    assert out.iloc[0].tested == 22 and out.iloc[0].hits == 13
    assert int(out.iloc[1:].tested.sum()) == int(out.iloc[0].tested)
    assert out.iloc[0].accuracy == pytest.approx(13 / 22)


def test_the_flag_drivers_are_the_largest_by_a_stated_rule():
    """The sentence names N terms, so N has to come from a rule, not a hand.

    The literal this replaces read "the six terms driving 764 of the 866 flags
    ... score 77.1%". Measured on the real extract, that set skips the
    third-largest driver (`Type: histopathology`, 44 flags, 100.0% held out) and
    reaches past it to the seventh (`Type: necropsy`, 25). The six LARGEST
    drivers are 783 flags at 77.4%. A selection whose only excluded member in
    range is the one scoring 100% is not a measurement.
    """
    audit = pd.DataFrame(
        [(i, f"S-{i}", "TIS", "12", "Tissue Collection", 11, "Comet Chip",
          S.T_STRONG, "Type", value, S.V_MODE3_FLAG)
         for i, value in enumerate(["big"] * 5 + ["mid"] * 3 + ["small"])],
        columns=S.AUDIT_COLUMNS,
    )
    heldout = {("Type", "big"): (5, 10), ("Type", "mid"): (9, 10),
               ("Type", "small"): (10, 10)}
    out = R.flag_driver_accuracy(audit, heldout, top=2)
    assert out["terms"] == 2
    assert out["flags"] == 8 and out["total_flags"] == 9
    assert out["tested"] == 20
    assert out["accuracy"] == pytest.approx(14 / 20)
    # `small` scores 100% and is left out because it is the smallest driver --
    # the rule -- not because of what it scores
    assert R.flag_driver_accuracy(audit, heldout, top=3)["accuracy"] == \
        pytest.approx(24 / 30)


def test_the_band_section_is_omitted_rather_than_remembered():
    # No bands passed, no band table: a report that cannot measure the figure
    # says nothing, instead of printing the last one anybody wrote down.
    assert "held-out accuracy" not in R.build_report(*_frames()).lower()


def test_heldout_by_term_holds_out_by_sample_and_scores_per_term():
    # Samples 0, 4 and 6 are even, so they train the mapping: three labelled
    # edges, all naming assay 11, which clears min_support. Sample 5 is odd and
    # is the only scored one; its labelled edge also says 11, so `cometchip`
    # scores 1 of 1. Two things must NOT appear: sample 5's `Protocol: mystery`
    # has no train support and contributes nothing rather than counting as a
    # miss, and sample 3's edge is dark, which is not ground truth.
    edges = pd.DataFrame(
        [(0, 900, "C-0", "P", "D.IMG", "TIS", 11, None, None),
         (4, 900, "C-4", "P", "D.IMG", "TIS", 11, None, None),
         (6, 900, "C-6", "P", "D.IMG", "TIS", 11, None, None),
         (5, 900, "C-5", "P", "D.IMG", "TIS", 11, None, None),
         (3, 900, "C-3", "P", "D.IMG", "TIS", None, None, None)],
        columns=S.EDGE_COLUMNS,
    )
    meta = {0: {"Type": "CometChip"}, 4: {"Type": "cometchip"},
            6: {"Type": "  COMETCHIP"},
            5: {"Type": "CometChip", "Protocol": "mystery"},
            3: {"Type": "CometChip"}}
    out = R.heldout_by_term(edges, meta)
    assert out == {("Type", "cometchip"): (1, 1)}


def test_peer_rate_is_measured_against_the_whole_carrier_cohort():
    """`peers` is the column the report tells a curator to read first.

    It must be the share of ALL samples carrying the term that are registered
    in the assay the pattern claims -- not the share of the flagged ones, and
    not the labelled-edge population `n_samples` counts. The fixture separates
    all three: 5 samples carry `Blood`, 4 are registered in 74, and the 1 that
    is not is the flagged one. Computed off the flags the rate would be 0/1;
    off `n_samples` (3 here) it would be 4/3.
    """
    audit = pd.DataFrame(
        [(500, "PAV-1", "PAV", "56", "Patient Visit", 74, "Tissue Collection",
          S.T_STRONG, "Type", "Blood", S.V_MODE3_FLAG)],
        columns=S.AUDIT_COLUMNS,
    )
    vocab = pd.DataFrame(
        [("Type", "blood", 74, "Tissue Collection", 100, 3, 0.69, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    meta = {i: {"Type": "Blood"} for i in (500, 501, 502, 503, 504)}
    registered = {500: {56}, 501: {74}, 502: {74}, 503: {74}, 504: {74}}

    pat = R.review_patterns(
        audit, vocab=vocab, carriers=R.term_carriers(meta),
        registered=registered,
        runners={("Type", "blood"): "56 Patient Visit 31%"},
        projects={i: "10" for i in meta},
    )
    row = pat.iloc[0]
    assert row.peer_carriers == 5, "denominator must be every carrier"
    assert row.peer_registered == 4
    assert row.peer_rate == pytest.approx(0.8)
    # the vocabulary's own evidence count rides alongside and is NOT the same
    assert row.n_samples == 3 and row.purity == pytest.approx(0.69)
    assert row.runner_up == "56 Patient Visit 31%"
    assert row.n_projects == 1

    # the bare rollup still works with no enrichment at all
    bare = R.review_patterns(audit)
    assert bare.iloc[0].n == 1 and pd.isna(bare.iloc[0].peer_rate)


def test_runner_up_comes_from_the_same_tally_learn_vocabulary_votes_on():
    """Pins the reach into `vocabulary._tally`, and the unanimity branch.

    `runner_up_index` deliberately uses the module-private tally because it is
    the only thing holding the full Counter, which makes it the one function
    here a change in vocabulary.py can break silently. The fixture keeps the
    two branches distinguishable: `blood` splits 2/1 across two assays,
    `granuloma` is 2/0 on one.
    """
    edges = pd.DataFrame(
        [(1, 10, "c1", "p1", "TIS", "PAV", 74, "Tissue Collection", None),
         (2, 11, "c2", "p2", "TIS", "PAV", 74, "Tissue Collection", None),
         (3, 12, "c3", "p3", "TIS", "PAV", 56, "Patient Visit", None),
         (4, 13, "c4", "p4", "TIS", "PAV", 74, "Tissue Collection", None),
         (5, 14, "c5", "p5", "TIS", "PAV", 74, "Tissue Collection", None)],
        columns=S.EDGE_COLUMNS,
    )
    meta = {1: {"Type": "Blood"}, 2: {"Type": "Blood"}, 3: {"Type": "Blood"},
            4: {"Type": "Granuloma"}, 5: {"Type": "Granuloma"}}

    idx = R.runner_up_index(edges, meta,
                            {74: "Tissue Collection", 56: "Patient Visit"})
    assert idx[("Type", "blood")] == "56 Patient Visit 33%"
    # one assay only: no runner-up may be fabricated
    assert "none" in idx[("Type", "granuloma")]

    # the reach itself: fail here, not at the next full run
    assert hasattr(V, "_tally"), (
        "runner_up_index depends on vocabulary._tally; it has been renamed or "
        "removed, and the runner-up column will be wrong or absent"
    )


def test_flag_purity_contrast_compares_flagged_against_eligible():
    """The contrast that stops 98.4% being read as a flag's accuracy.

    Eligible means tier in DEFAULT_TIERS and not contested -- the population
    the audit can draw from. The fixture makes the flagged term ambiguous
    (0.60) and the eligible population otherwise clean (1.00), so a function
    comparing the wrong two populations cannot produce this answer.
    """
    claims = pd.DataFrame(
        [(1, "u1", 11, "A", S.T_STRONG, "Type", "clean", False, S.P_LEARNED),
         (2, "u2", 11, "A", S.T_STRONG, "Type", "clean", False, S.P_LEARNED),
         (3, "u3", 11, "A", S.T_STRONG, "Type", "murky", False, S.P_LEARNED),
         (4, "u4", 11, "A", S.T_WEAK, "Type", "murky", False, S.P_LEARNED),
         (5, "u5", 11, "A", S.T_STRONG, "Type", "murky", True, S.P_LEARNED)],
        columns=S.CLAIM_COLUMNS,
    )
    audit = pd.DataFrame(
        [(3, "u3", "TIS", "12", "B", 11, "A", S.T_STRONG, "Type", "murky",
          S.V_MODE3_FLAG)],
        columns=S.AUDIT_COLUMNS,
    )
    vocab = pd.DataFrame(
        [("Type", "clean", 11, "A", 10, 10, 1.00, S.P_LEARNED),
         ("Type", "murky", 11, "A", 10, 10, 0.60, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    c = R.flag_purity_contrast(claims, audit, vocab)
    # eligible = the 3 strong uncontested rows; the weak and contested are out
    assert c["eligible_n"] == 3
    assert c["eligible_median"] == pytest.approx(1.00)
    assert c["flagged_median"] == pytest.approx(0.60)
    assert c["flagged_below"] == pytest.approx(1.0)
    assert c["eligible_below"] == pytest.approx(1 / 3)


def test_the_report_refuses_a_blanket_dismissal_and_defers_on_peer_rate():
    """R4b and R5: both must reach the ARTIFACT, not just the task report.

    The report explains that most flags trace to a vocabulary plurality vote,
    which invites "so they are all artifacts". They are not: on the real
    extract 280 of 866 sit at 93%+ peer registration, including one term where
    4,628 of 4,629 carriers are registered and the single flagged sample is the
    only one that is not. And because the report names `peers` as the column to
    read first, the deferred threshold question must be framed on that axis --
    a purity floor mis-sorts 151 of the 866 flags in both directions.
    """
    precedent, claims, audit, vocab, unresolved = _frames()
    # two patterns: one clean gap (95% of peers registered), one likely artifact
    pat = R.review_patterns(
        audit,
        vocab=pd.DataFrame(
            [("Type", "cometchip", 11, "Comet Chip", 100, 40, 0.70, S.P_LEARNED),
             ("Type", "total rna", 24, "RNA Extraction", 100, 40, 0.95,
              S.P_LEARNED)],
            columns=S.VOCAB_COLUMNS),
        carriers={("Type", "cometchip"): set(range(100)),
                  ("Type", "total rna"): set(range(200, 300))},
        registered={**{i: {11} for i in range(95)},
                    **{i: {24} for i in range(200, 240)}},
        projects={},
    )
    md = R.build_report(precedent, claims, audit, vocab, unresolved,
                        patterns=pat)
    low = md.lower()
    # Asserted as three separate properties, never as an `or`. An either/or
    # here would let half the section be deleted and stay green -- which is
    # exactly what happened the first time this case was written: renaming the
    # heading left the word "mixed" in the body and satisfied the assertion.
    assert "genuine" in low, "the true-positive population must be named"
    assert "discard" in low, (
        "the report never warns that dismissing Mode 3 wholesale throws away "
        "the genuine gaps"
    )
    assert "mixed" in low, "the mixed reading must be stated outright"
    # and the size of the genuine-looking population must be quantified, not
    # merely asserted: the fixture's clean pattern carries 2 of the 3 flags.
    assert "**2 of the 3 flags" in md, (
        "the population that looks like genuine gaps is not counted, so a "
        "curator cannot tell whether it is 2 flags or 200"
    )
    # the deferred question rides on peer rate, and says so before purity
    tail = md.split("open question")[1].lower()
    assert "peer rate, not purity" in tail or "peer rate**, not purity" in tail, (
        "the deferred threshold is still framed on purity, contradicting the "
        "report's own instruction to read peer rate first"
    )
    assert "no threshold is chosen" in tail


def test_report_says_plainly_that_nothing_was_written():
    """Also the empty-frame smoke test: every rollup must survive no rows.

    `build_report` groups, sorts and sums four frames. An operator's first run
    against a fresh extract -- or any run whose audit comes back clean -- hands
    it empty ones, and a report that raises there is a report nobody reads.
    """
    md = R.build_report(*[pd.DataFrame(columns=c) for c in (
        S.PRECEDENT_COLUMNS, S.CLAIM_COLUMNS, S.AUDIT_COLUMNS, S.VOCAB_COLUMNS,
        ["source_field", "raw_value", "n_samples", "example_uuids"])])
    # An operator reading a hygiene report must not have to infer this.
    assert "writes nothing" in md.lower() or "nothing was written" in md.lower()
    # and the three destinations are named, so "nothing" is not left abstract
    low = md.lower()
    assert "mysql" in low and "neo4j" in low and "api" in low
