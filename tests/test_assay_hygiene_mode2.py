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
    assert unreachable.classification == S.CLS_UNREACHABLE
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
    assert (Counter(unified.classification)[S.CLS_UNREACHABLE]
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
    assert _row(findings, 100, 12).classification == S.CLS_UNREACHABLE

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
    assert set(findings[pair].classification) == {S.CLS_UNREACHABLE}
    assert set(after[pair.values].classification) == {S.CLS_ABSENCE_LINEAGE}
    # ...and EVERY ROW OUTSIDE IT is unchanged, column for column, so the cell
    # moved exactly the rows it names and the frame was not rebuilt around it
    pd.testing.assert_frame_equal(after[~pair.values].reset_index(drop=True),
                                  findings[~pair].reset_index(drop=True))
    assert set(after.columns) == set(findings.columns) == set(S.FINDING_COLUMNS)
    # the other three unreachable rows are OUTSIDE the cell and did not move:
    # 250/14 (MUS), 290/14 (TIS) and 430/490 (TIS)
    assert int((after.type_registrations == 0).sum()) == 3
