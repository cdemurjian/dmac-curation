# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The lineage lane's own tests. This file did not exist before this plan.

`mode2.py` is the largest module in the package and generates 167,454 of the
170,786 rows in `findings.csv`, and until now it was exercised only incidentally
through `tests/test_assay_hygiene_classify.py`. Both audits of 2026-08-21 noted
that the one module with no direct test file is where the defects concentrated.

Both figures re-derived 2026-08-21 by counting `mode` over the artifact:
`csv.DictReader(open('assay-hygiene/findings.csv'))` -> 170,786 rows total,
`MODE_2` 167,454, `MODE_1` 1,373, blank 1,959.

NO LINE COUNT HERE ON PURPOSE. The first revision of this docstring said "806
lines", which was already wrong at the commit that introduced it, since that
same commit removed three. Every subsequent edit to `mode2.py` invalidates the
figure again, and no test can check a comment -- which is the stale-figure
defect this package keeps shipping. The sentence means "large" and does not
need a number to say it.
"""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import mode2 as M2  # noqa: E402

# `_pipeline2` and its two helpers are the Mode 2 world, and they are IMPORTED
# rather than rebuilt: a second assembly of the same stages is a second
# definition of the run, which is the failure `run_detect`'s own docstring
# records paying for. `_pipeline2` returns `(w, bundle, findings)` where
# `bundle` is the keyword-argument dict `mode2_findings` takes, so a test that
# needs to perturb ONE index does it by name.
from test_assay_hygiene_classify import (  # noqa: E402
    _attached2, _pipeline2, _row)


class _Claim:
    """The duck-typed shape `_proposal_source` reads. It touches no attribute."""


def test_a_gated_claim_with_no_precedent_rule_names_its_own_source():
    """The combination the function used to raise on.

    It occurs 0 times on the 2026-08-17 extract, which is a fact about that
    extract. The reachability rework moves the populations that determine it,
    so the run must not abort the first time one appears.
    """
    got = M2._proposal_source(None, _Claim(), sample_id=1, assay_id=2)
    assert got == X.BY_CLAIM_NO_RULE
    assert got in X.PROPOSAL_SOURCES
    # No `!= BY_BOTH` / `!= BY_LINEAGE_ONLY` here: those follow from the `==`
    # above and would discriminate nothing while wearing this package's
    # "simulate the wrong rule by hand" discipline. The real counterfactual --
    # a row that a widening WOULD have mislabelled, with the row's own null rate
    # and its claim-bearing summary falsifying each alternative -- is in
    # `test_assay_hygiene_classify.py`, in
    # `test_a_claim_with_no_precedent_rule_names_its_own_source` and
    # `test_a_reduced_rule_set_relabels_the_row_rather_than_aborting_the_run`.


def test_the_other_three_combinations_are_unchanged():
    rule = M2.Rule(1, 2, 3, 0.5, 0.25)
    assert M2._proposal_source(rule, _Claim(), 1, 2) == X.BY_BOTH
    assert M2._proposal_source(rule, None, 1, 2) == X.BY_PRECEDENT
    assert M2._proposal_source(None, None, 1, 2) == X.BY_LINEAGE_ONLY


def _unify(w, bundle, findings, *, order=None, tests=None):
    """The lineage lane through the whole unified pass. -> (steps, unified).

    `order` and `tests` let a caller run the pass under the PRE-2026-08-21
    contract -- five steps, `PRE_LINEAGE: e.lineage` -- so "the row count did
    not move" is a comparison against the old rule actually executed, and not
    against a number copied out of a document.
    """
    attached = _attached2(w)
    candidates = M2.mode2_candidates(bundle["children_of"],
                                     bundle["parents_of"], bundle["registered"])
    population = X.unregistered_samples(w["samples"], w["membership"],
                                        w["assays"])
    keys = X.absence_keys(attached, population=population,
                          registered=bundle["registered"],
                          candidates=candidates, type_reg=bundle["type_reg"],
                          types=bundle["types"], uuid_of=bundle["uuid_of"])
    if order is None:
        steps = X.precedence_steps(keys)
        lanes = {X.PRE_LINEAGE: findings, X.PRE_UNREACHABLE: findings}
    else:
        steps = {k: next(s for s in order if tests[s](e))
                 for k, e in keys.items()}
        lanes = {X.PRE_LINEAGE: findings}
    return steps, X.unify_findings(steps, lanes)


def test_an_unreachable_lineage_row_is_classified_and_emitted_and_nothing_is_dropped():
    """The rework, end to end on one world. Two pairs, one of each shape.

    `_world2` registers three TIS samples in internal assay 11, so (TIS, 11) is
    a pair the house has made and (200, 11) is an ordinary lineage proposal. No
    D.IMG sample is registered in 12 anywhere, so (100, 12) proposes a
    (type, assay) pair that exists nowhere -- the shape
    `gate.type_registration_index` calls incredible and `gate.gate_claims`
    BLOCKS a claim on, and which this lane emitted unmarked until 2026-08-21.

    THE ROW COUNT IS THE ASSERTION. Both rows are emitted, before and after,
    and the old rule is RUN here rather than quoted: the same world goes through
    `unify_findings` under the five-step precedence with `PRE_LINEAGE` testing
    `e.lineage` alone, and the two passes emit the same pairs. Only the
    classification moved.
    """
    w, bundle, findings = _pipeline2()

    reachable = _row(findings, 200, 11)
    unreachable = _row(findings, 100, 12)
    assert reachable.type_registrations == 5
    assert unreachable.type_registrations == 0
    assert reachable.classification == S.CLS_ABSENCE_LINEAGE
    assert reachable.gate != S.GATE_UNREACHABLE or pd.isna(reachable.gate)
    # `CLS_BOOTSTRAP` and not `CLS_UNREACHABLE`: assay 12 holds 13 samples in
    # this world, under `BOOTSTRAP_POPULATION_FLOOR`. The two are one finding
    # under two review headings and this test is about the finding, so the
    # assertion is against the pair -- and the gate, which does not move with
    # the split, is pinned exactly.
    assert unreachable.classification in (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP)
    assert unreachable.gate == S.GATE_UNREACHABLE
    # both are MODE_2 proposals a curator will see, which is the point of
    # classifying rather than filtering
    assert reachable["mode"] == unreachable["mode"] == S.MODE_2
    assert reachable.action and unreachable.action

    steps, unified = _unify(w, bundle, findings)
    assert steps[(200, 11)] == X.PRE_LINEAGE
    assert steps[(100, 12)] == X.PRE_UNREACHABLE
    both = {(int(r.sample_id), int(r.proposed_internal_assay_id))
            for r in unified.itertuples(index=False)}
    assert {(200, 11), (100, 12)} <= both

    # THE OLD RULE, RUN. Five steps, `PRE_LINEAGE` testing `e.lineage` alone,
    # and ONE lane -- which is what the pipeline did before this change.
    old_order = (X.PRE_GATE, X.PRE_MODE_1, X.PRE_LINEAGE, X.PRE_COMPAT,
                 X.PRE_MODE_3)
    old_tests = {s: t for s, t in X._PRECEDENCE_TESTS.items()
                 if s != X.PRE_UNREACHABLE}
    old_tests[X.PRE_LINEAGE] = lambda e: e.lineage
    old_steps, old_unified = _unify(w, bundle, findings, order=old_order,
                                    tests=old_tests)

    # ...and the two passes emit the SAME PAIRS. Not the same count: the same
    # keys, so a row silently swapped for another could not pass either.
    assert both == {(int(r.sample_id), int(r.proposed_internal_assay_id))
                    for r in old_unified.itertuples(index=False)}
    assert len(unified) == len(old_unified) == 27
    # the old rule really did differ -- it put the unreachable key in the
    # ordinary lineage step -- or the comparison above proves nothing
    assert old_steps[(100, 12)] == X.PRE_LINEAGE != steps[(100, 12)]
    assert old_steps[(200, 11)] == steps[(200, 11)] == X.PRE_LINEAGE

    # the two steps PARTITION the lane rather than duplicating it, which is what
    # handing one frame to two lane keys has to mean
    by_step = Counter(steps.values())
    assert by_step[X.PRE_LINEAGE] + by_step[X.PRE_UNREACHABLE] == 27
    # 10 keys and not the 11 unreachable rows the LANE holds: (290, 14) is
    # unreachable AND carries a claim the gate rejected, so `PRE_GATE` takes it
    # and it reaches no row at all. The two numbers differing is the check that
    # the gate still outranks this step.
    assert by_step[X.PRE_UNREACHABLE] == 10
    assert int((findings.type_registrations == 0).sum()) == 11
    assert steps[(290, 14)] == X.PRE_GATE
    assert not unified.duplicated(
        ["sample_id", "proposed_internal_assay_id"]).any()
    unreachable_classes = Counter(unified.classification)
    assert (unreachable_classes[S.CLS_UNREACHABLE]
            + unreachable_classes[S.CLS_BOOTSTRAP]
            == by_step[X.PRE_UNREACHABLE])


def test_filling_the_reachability_cell_moves_a_row_between_classes_and_moves_no_row_out():
    """One index perturbed by name, and the frame keeps its shape.

    `_pipeline2` hands back the keyword-argument dict, so the ONLY difference
    between the two runs below is one `type_registration_index` cell. If
    reachability were a filter rather than a classification, the two frames
    would differ in LENGTH; they differ in the `classification` and `gate` of
    the rows that cell names, and in nothing else.

    THE CELL IS A (TYPE, ASSAY) PAIR AND IT MOVES EVERY ROW OF THAT PAIR, which
    is eight of the twenty-eight here and not one. That is the unit the gate
    reasons in, so a test that expected exactly one row to move would be
    asserting the wrong grain.
    """
    w, bundle, findings = _pipeline2()
    assert _row(findings, 100, 12).classification == S.CLS_BOOTSTRAP

    filled = dict(bundle)
    filled["type_reg"] = dict(bundle["type_reg"]) | {("D.IMG", 12): 1}
    after = M2.mode2_findings(_attached2(w), **filled)

    assert len(after) == len(findings) == 28
    assert list(zip(after.sample_id, after.proposed_internal_assay_id)) == list(
        zip(findings.sample_id, findings.proposed_internal_assay_id))
    moved = _row(after, 100, 12)
    assert moved.classification == S.CLS_ABSENCE_LINEAGE
    assert pd.isna(moved.gate)
    assert moved.type_registrations == 1

    # the cell's own population, named off the frame rather than listed
    pair = (findings.sample_type == "D.IMG") & (
        findings.proposed_internal_assay_id == 12)
    assert int(pair.sum()) == 8
    assert set(findings[pair].classification) == {S.CLS_BOOTSTRAP}
    assert set(after[pair.values].classification) == {S.CLS_ABSENCE_LINEAGE}
    # ...and EVERY ROW OUTSIDE IT is unchanged, column for column, so the cell
    # moved exactly the rows it names and the frame was not rebuilt around it
    pd.testing.assert_frame_equal(after[~pair.values].reset_index(drop=True),
                                  findings[~pair].reset_index(drop=True))
    assert set(after.columns) == set(findings.columns) == set(S.FINDING_COLUMNS)
    # the other three unreachable rows are OUTSIDE the cell and did not move:
    # 250/14 (MUS), 290/14 (TIS) and 430/490 (TIS)
    assert int((after.type_registrations == 0).sum()) == 3


# --- the bootstrap lane -------------------------------------------------------
#
# Task 4. An unreachable pair is a claim that the HOUSE HAS A GAP, and that
# claim is not automatically false: 47 unreachable cohorts were approved by
# agents reading the biology, and the assay-143 name-collision finding turned on
# one of them being right. What separates a gap from a type error is how heavily
# the proposed assay is used, and these tests are about that discriminator and
# about the namespace it is measured in.


def _pop_over_the_floor(bundle, assay_id):
    """`bundle` with one assay lifted to the D.FLOW -> Tissue Collection size.

    A COPY AND NEVER A MUTATION of the bundle `_pipeline2` returned, so the two
    frames a test compares are built from indexes that differ in exactly one
    entry and the caller can still read the original.

    89,263 is the real population of internal assay 74, Tissue Collection, on
    the 2026-08-21 extract -- 24,470 of the 99,449 unreachable rows propose it
    and not one of the 89,263 is a D.FLOW. That is the shape being reproduced,
    so the number is the real one rather than `FLOOR + 1`.
    """
    lifted = dict(bundle)
    lifted["assay_pop"] = dict(bundle["assay_pop"]) | {assay_id: 89_263}
    return lifted


def test_an_unreachable_pair_under_a_barely_used_assay_is_a_bootstrap_candidate():
    """The assay-143 case, generalised.

    47 unreachable cohorts were approved by agents reading the biology, and the
    gpt delta finding turned on one of them being right. A blanket block would
    have deleted every one; this lane keeps them reviewable and apart.

    (250, 14) IS THAT SHAPE IN THIS WORLD. Internal assay 14 holds two samples
    in total -- 350 and 390, both PAV -- and no MUS sample is registered in it
    anywhere, so the cell is empty AND the assay has never had the chance to
    refuse anything. It is emitted, it carries `GATE_UNREACHABLE`, and it is
    filed apart from the pairs a well-used assay has already declined.

    THE PRE-TASK-4 RULE IS RUN BY HAND, over the frame's own cells, and the two
    are asserted to DIFFER. That rule -- one class for every empty cell, however
    big the assay -- is what shipped between Tasks 3 and 4, so this is a
    comparison against the code that ran and not against a description of it.
    """
    w, bundle, findings = _pipeline2()

    assert bundle["assay_pop"][14] == 2, (
        "assay 14 must be barely used or this test discriminates nothing")
    assert bundle["assay_pop"][14] < M2.BOOTSTRAP_POPULATION_FLOOR

    row = _row(findings, 250, 14)
    assert row.type_registrations == 0
    assert row.classification == S.CLS_BOOTSTRAP
    # the row is UNCHANGED otherwise: the gate, the mode and the direction are
    # the unreachable population's, which is what "a cut through it" means
    assert row.gate == S.GATE_UNREACHABLE
    assert row["mode"] == S.MODE_2
    assert row.action == S.A_ADD_CHILD
    # ...and the sentence carries the number the split turned on, so a curator
    # can disagree with it without reading any code
    assert "2 sample(s) of ANY type" in row.evidence_summary
    assert str(M2.BOOTSTRAP_POPULATION_FLOOR) in row.evidence_summary
    assert "FIRST-OF-A-KIND" in row.evidence_summary

    # THE PRE-TASK-4 RULE, RUN BY HAND: `CLS_UNREACHABLE` for every empty cell,
    # `CLS_ABSENCE_LINEAGE` otherwise, and nothing consulted about the assay.
    old = [S.CLS_UNREACHABLE if n == 0 else S.CLS_ABSENCE_LINEAGE
           for n in findings.type_registrations]
    assert list(findings.classification) != old, (
        "the old rule already agrees with this frame, so nothing here "
        "discriminates the two")
    differ = [(int(s), int(a)) for s, a, was, now
              in zip(findings.sample_id, findings.proposed_internal_assay_id,
                     old, findings.classification) if was != now]
    # ...and it differs on EXACTLY the unreachable rows, because every assay in
    # a 33-sample world is under the floor. The row count did not move.
    assert differ == [(int(s), int(a)) for s, a, n
                      in zip(findings.sample_id,
                             findings.proposed_internal_assay_id,
                             findings.type_registrations) if n == 0]
    assert len(differ) == 11 == int((findings.type_registrations == 0).sum())
    assert len(findings) == 28


def test_an_unreachable_pair_under_a_heavily_used_assay_is_not():
    """D.FLOW -> Tissue Collection: 89,263 members, not one a D.FLOW.

    That is a type error, not a gap, and it must not reach the bootstrap sheet.

    ONE INDEX ENTRY IS PERTURBED AND NOTHING ELSE, which is why `_pipeline2`
    hands the bundle back. The two frames below differ in the population of
    assay 12 alone -- 13 samples against Tissue Collection's 89,263 -- so the
    8 `(D.IMG, 12)` rows are the same rows, raised by the same neighbours, on
    the same empty cell, and the only thing that moved is which question a
    curator is being asked about them.
    """
    w, bundle, findings = _pipeline2()
    assert bundle["assay_pop"][12] == 13
    before = _row(findings, 100, 12)
    assert before.classification == S.CLS_BOOTSTRAP

    heavy = M2.mode2_findings(_attached2(w), **_pop_over_the_floor(bundle, 12))
    row = _row(heavy, 100, 12)
    assert row.classification == S.CLS_UNREACHABLE
    # THE WRONG RULE, BY HAND: no population test at all, so every empty cell is
    # a bootstrap candidate. It answers CLS_BOOTSTRAP on this row and the two
    # differ -- without this the assertion above cannot tell a measured floor
    # from a lane that happens to be empty.
    wrong = S.CLS_BOOTSTRAP if row.type_registrations == 0 else None
    assert wrong == S.CLS_BOOTSTRAP != row.classification

    # ...and the finding itself is untouched: same gate, same cell, same
    # direction, same sentence about the pair
    assert row.gate == before.gate == S.GATE_UNREACHABLE
    assert row.type_registrations == before.type_registrations == 0
    assert row.action == before.action
    assert "NO D.IMG sample is registered in 12 anywhere" in row.evidence_summary
    assert "89,263 sample(s) of other types" in row.evidence_summary
    assert "FIRST-OF-A-KIND" not in row.evidence_summary

    # the whole (D.IMG, 12) cell moves together and NOTHING outside it moves,
    # column for column -- so the population test is per assay and not per row
    pair = ((findings.sample_type == "D.IMG")
            & (findings.proposed_internal_assay_id == 12))
    assert int(pair.sum()) == 8
    assert set(heavy[pair.values].classification) == {S.CLS_UNREACHABLE}
    assert len(heavy) == len(findings) == 28
    pd.testing.assert_frame_equal(heavy[~pair.values].reset_index(drop=True),
                                  findings[~pair].reset_index(drop=True))


def test_the_bootstrap_floor_is_a_reading_order_and_gates_nothing():
    """Every row is emitted at either population, and the precedence agrees.

    Under the binding constraint a threshold orders what an operator reads first
    and grants no permission. So the two frames above must carry the same PAIRS,
    and `PRE_UNREACHABLE` -- which knows nothing about the floor -- must claim
    the same keys either way. A step of its own would have had to re-derive
    reachability a second time, which is the second-definition defect this
    package has paid for three times.
    """
    w, bundle, findings = _pipeline2()
    heavy = M2.mode2_findings(_attached2(w), **_pop_over_the_floor(bundle, 12))

    pairs = list(zip(findings.sample_id, findings.proposed_internal_assay_id))
    assert pairs == list(zip(heavy.sample_id, heavy.proposed_internal_assay_id))
    assert set(findings.classification) == {S.CLS_ABSENCE_LINEAGE,
                                            S.CLS_BOOTSTRAP}
    assert set(heavy.classification) == {S.CLS_ABSENCE_LINEAGE,
                                         S.CLS_BOOTSTRAP, S.CLS_UNREACHABLE}

    steps, unified = _unify(w, bundle, findings)
    heavy_steps, heavy_unified = _unify(w, bundle, heavy)
    assert steps == heavy_steps
    assert len(unified) == len(heavy_unified) == 27
    claimed = {k for k, s in steps.items() if s == X.PRE_UNREACHABLE}
    for frame in (unified, heavy_unified):
        assert {(int(r.sample_id), int(r.proposed_internal_assay_id))
                for r in frame.itertuples(index=False)
                if r.classification in (S.CLS_UNREACHABLE,
                                        S.CLS_BOOTSTRAP)} == claimed
    # ...and the floor is read in ONE place, so no second copy of it can drift.
    # Read off the source, since a second literal 100 is exactly what a later
    # edit adds and no assertion over behaviour would see.
    src = (Path(M2.__file__)).read_text()
    body = src.split("def _bootstrap_evidence")[1].split("\ndef ")[0]
    assert body.count("BOOTSTRAP_POPULATION_FLOOR") == 3
    assert "100" not in body, (
        "a literal floor inside the discriminator is a second definition of "
        "the number the module constant documents, and the two would drift")
    assert src.count("BOOTSTRAP_POPULATION_FLOOR = ") == 1


def test_the_assay_population_resolves_the_junctionless_namespace():
    """The trap: a fallback id reports 0 members under the obvious lookup.

    `_world2`'s seek record 490 has no junction row, so `assay_index` gives it
    its OWN id as the internal one and sample 130 is registered there. Keying
    membership on `assays.internal_assay_id` and skipping the nulls -- the
    obvious spelling, and the one a scratch script reaches for -- drops that
    record entirely and reports assay 490 at a population of zero.

    ON THE REAL EXTRACT THAT MISS IS 1,122 ROWS. The 8 fallback ids any
    unreachable row proposes hold 5, 9, 8, 12, 43, 153, 26 and 13 samples; read
    naively all 8 read zero, so all 1,321 of their rows land in the bootstrap
    lane, where the correct reading puts 199 -- 472 holds 153 and is over the
    floor. `test_the_real_extract_reproduces_the_precedence_split_and_mode_3s_emptiness`
    pins that end of it; this end pins the index.

    THE NAIVE INDEX IS BUILT HERE AND COMPARED, so the assertion is a
    DIFFERENCE between two rules rather than a restatement of one.
    """
    w, _, findings = _pipeline2()
    pop = M2.assay_population(w["membership"], w["assays"])

    naive: dict[int, set[int]] = {}
    keyed = {int(a): int(i) for a, i in zip(w["assays"].assay_id,
                                            w["assays"].internal_assay_id)
             if pd.notna(i)}
    for sid, aid in zip(w["membership"].sample_id, w["membership"].assay_id):
        if int(aid) in keyed:
            naive.setdefault(keyed[int(aid)], set()).add(int(sid))
    naive = {k: len(v) for k, v in naive.items()}

    # the junction-less record: one member under the right rule, ABSENT under
    # the naive one, and the two therefore disagree
    assert pop[490] == 1
    assert 490 not in naive
    assert pop != naive
    # ...and they agree on every junctioned assay, so the disagreement is the
    # namespace and not an arithmetic difference
    assert {k: v for k, v in pop.items() if k != 490} == naive
    assert pop == {11: 15, 12: 13, 13: 8, 14: 2, 490: 1}

    # the row that rides on it is still classified from a MEASURED population
    row = _row(findings, 430, 490)
    assert row.type_registrations == 0
    assert row.classification == S.CLS_BOOTSTRAP
    assert "1 sample(s) of ANY type" in row.evidence_summary

    # a membership row naming an unknown assay RAISES rather than shrinking a
    # population, which is the direction that would fabricate a barely-used
    # assay out of a bad join
    broken = pd.concat([w["membership"],
                        pd.DataFrame([(1, 9999)],
                                     columns=S.MEMBERSHIP_COLUMNS)])
    with pytest.raises(ValueError, match="absent from the assays frame"):
        M2.assay_population(broken, w["assays"])


def test_bootstrap_evidence_speaks_on_both_sides_of_the_floor():
    """The discriminator alone, at the boundary, in both directions.

    THE COMPARISON IS `<` AND NOT `<=`, and the floor itself is the row that
    says so: an assay holding exactly `BOOTSTRAP_POPULATION_FLOOR` samples is
    NOT barely used. Both neighbours of the boundary are asserted, because an
    off-by-one here moves whichever assays sit on it and nothing else would
    fail.

    A MISSING KEY IS ZERO AND NOT A LOOKUP MISS. `assay_population` counts
    through `precedent.assay_index`, so every id `mode2_candidates` can propose
    is a key it holds -- but the default is asserted, since it is what a caller
    handing in a partial index would silently get.
    """
    floor = M2.BOOTSTRAP_POPULATION_FLOOR
    titles = {9: "Sensor Creation"}

    at, note = M2._bootstrap_evidence(9, "TIS", {9: floor}, titles)
    assert at is False
    assert f"holds {floor:,} sample(s) of other types" in note
    under, note = M2._bootstrap_evidence(9, "TIS", {9: floor - 1}, titles)
    assert under is True
    assert f"holds only {floor - 1:,} sample(s) of ANY type" in note

    # the title rides in the sentence, and a bare id where there is none
    assert "9 Sensor Creation" in note
    _, untitled = M2._bootstrap_evidence(9, "TIS", {9: 2}, {})
    assert "9 holds only 2" in untitled

    # an absent key is a population of zero, which is under any floor
    missing, note = M2._bootstrap_evidence(9, "TIS", {}, titles)
    assert missing is True
    assert "holds only 0 sample(s)" in note
    # ...and the sample type is named on both sides, since the sentence is what
    # a curator reads instead of the two indexes it was measured from
    assert "TIS" in note
