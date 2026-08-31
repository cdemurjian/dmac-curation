"""The stratified validation sample, and the sheet a human rules it on.

WHAT THIS FILE IS PROTECTING. `tests/test_assay_hygiene_rulings.py` proved that
the operator's 128 hand rulings CANNOT validate the reachability gate -- an
unreachable pair's precedent rate is structurally 0.0 and the sheet he ruled on
starts at 0.50, so the two populations are disjoint. The 99,309 rows the rework
moves have never been judged by anyone. `validation_sample.py` draws the sample
that closes that, and the three properties below are the ones whose failure
would make the whole sitting worthless rather than merely wrong.

    1. THE DRAW IS REPRODUCIBLE, AND THE SECOND HALF OF THAT TEST IS WHAT MAKES
       THE FIRST NON-VACUOUS. "Two draws at one seed are identical" is green on
       a function that ignores its seed and returns the first n keys; it is only
       a statement about seeding when a DIFFERENT seed is shown to give a
       different sample. Both halves are written, and the second is the one
       that fails under `SEED`-ignoring code.
    2. THE POWER IS STATED BEFORE ANYONE RULES, including the part the sample
       cannot support. A sheet that printed only the per-cohort bound would
       imply a row-weighted precision it does not have -- stratum A's draw
       covers 10.2% of its rows.
    3. THE RATER CAN PUNT. `UNSURE` is on the sheet, in the html select and in
       the vocabulary check. Forcing a binary is how a false-approve floor is
       manufactured, and this project has measured one at ~5%.

EXTRACT-BACKED TESTS ARE NAMED `..._real_extract_...`, the convention the rest
of the suite selects on with `-k 'not real_extract'`. The one here runs
`classify.main` over the real extract into `tmp_path_factory` -- about 20
seconds -- because `assay-hygiene/findings.csv` is the PRE-rework artifact and
carries neither of the two classes strata A and B are cut from, so a test
reading it would measure nothing.
"""
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assay_hygiene import _schema as S              # noqa: E402
from assay_hygiene import classify as X             # noqa: E402
from assay_hygiene import gate as G                 # noqa: E402
from assay_hygiene import mode2 as M2               # noqa: E402
from assay_hygiene import precedent as P            # noqa: E402
from assay_hygiene import review as R               # noqa: E402
from assay_hygiene import review_mode2 as M         # noqa: E402
from assay_hygiene import validation_sample as V    # noqa: E402

from test_assay_hygiene_review import _findings     # noqa: E402
from test_assay_hygiene_review_mode2 import _m2     # noqa: E402

def _section(report: str, heading: str) -> str:
    """One `##` section of the power document, heading included.

    THE RENDERED TEXT IS WHAT THESE TESTS MUST ASSERT ON, not the stat dict
    that produced it. Four guards in this file have already shipped unable to
    fail because they compared a document against the very field a mutation
    would corrupt; slicing the document and reading it back is the only shape
    that catches a table printing the wrong population.
    """
    assert heading in report, f"no section {heading!r} in the document"
    start = report.index(heading)
    rest = report.index("\n## ", start + len(heading))
    return report[start:rest]


EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"
EVIDENCE_INPUTS = ("claims.parquet", "vocabulary.csv")

# The synthetic world's three assays, and the facts the sheet must recompute
# rather than read off a row.
A_ASSAY, A_TITLE = 30, "Flow Cytometry"        # unreachable: 0 registrations
B_ASSAY, B_TITLE = 31, "Histopathology"        # bootstrap: a tiny assay
C_ASSAY, C_TITLE = 32, "Mass Spectrometry"     # on the primary surface

TYPE_REG = {("D.IMG", A_ASSAY): 0, ("D.IMG", B_ASSAY): 0,
            ("D.IMG", C_ASSAY): 12}
ASSAY_POP = {A_ASSAY: 4000, B_ASSAY: 12, C_ASSAY: 900}
FALLBACK: set[int] = set()

# DELIBERATELY NOT THIS HOUSE'S THREE-LETTER LAB CODES. The lab is the one key
# component that lives only inside a uuid, so a fixture needs a set of them --
# and this repository is PUBLIC and has already had to rewrite 66 commits to
# strip identifiers out of that namespace. Four-letter NATO words cannot be
# mistaken for a real lab and exercise `parse_uid` exactly as well.
LABS = ("ALFA", "BRAV", "CHAR", "DELT", "ECHO", "FOXT", "GOLF", "HOTL",
        "INDI", "JULI", "KILO", "LIMA")


def _row(lab, serial, *, cls, assay, title, counts, rate, direction,
         type_regs, action="ADD_PARENT_TO_ASSAY"):
    """One MODE_2 finding, consistent with the three indexes above.

    `counts` is `(n_both, n_child_only, n_parent_only)` and `rate` is what the
    detector wrote in `direction`. They are passed separately, not derived,
    precisely so a test can hand in a pair that DISAGREE and watch
    `check_rates_reproduce_the_row` refuse them.
    """
    row = _m2(serial, f"TIS-2401{serial % 100:02d}{lab}-{serial}",
              rate=rate, action=action, neighbour="TIS-240101ENG-800",
              sample_type="D.IMG", assay_id=assay, assay_title=title,
              type_regs=type_regs)
    both, child, parent = counts
    row.update({
        "classification": cls,
        "gate": S.GATE_UNREACHABLE if type_regs == 0 else None,
        "precedent_direction": direction,
        "precedent_n_both": both,
        "precedent_n_child_only": child,
        "precedent_n_parent_only": parent,
        "precedent_supports": both > 0,
        "id_namespace": S.NS_INTERNAL,
        "evidence_summary": f"{lab}: the detector's sentence for {serial}",
    })
    return row


def _world(n_a=8, n_b=6, n_c=5):
    """-> (findings, context). One cohort per lab per stratum.

    THE LAB IS WHAT SEPARATES THE COHORTS, because it is a key component that
    lives only in the uuid; varying it gives distinct cohort keys without
    varying the evidence, which is what a draw test needs -- cohorts that
    differ in nothing a sampler should be able to see.
    """
    rows = []
    for i, lab in enumerate(LABS[:n_a]):
        rows.append(_row(lab, 900 + i, cls=S.CLS_UNREACHABLE, assay=A_ASSAY,
                         title=A_TITLE, counts=(0, 3, 0), rate=0.0,
                         direction="propagation_rate", type_regs=0))
    for i, lab in enumerate(LABS[:n_b]):
        rows.append(_row(lab, 920 + i, cls=S.CLS_BOOTSTRAP, assay=B_ASSAY,
                         title=B_TITLE, counts=(0, 0, 5), rate=0.0,
                         direction="reverse_rate", type_regs=0,
                         action="ADD_CHILD_TO_ASSAY"))
    for i, lab in enumerate(LABS[:n_c]):
        rows.append(_row(lab, 940 + i, cls=S.CLS_ABSENCE_LINEAGE,
                         assay=C_ASSAY, title=C_TITLE, counts=(2, 3, 0),
                         rate=0.4, direction="propagation_rate",
                         type_regs=12))
    findings = _findings(rows)

    # 998 and 999 are the spare sample ids two tests below add a row under.
    # They are given the same parent HERE so that the extra row joins an
    # EXISTING cohort rather than founding a new `NO_PARENT` one -- which would
    # change the population size and so change the draw for a reason that has
    # nothing to do with what those tests are about.
    sids = [r["sample_id"] for r in rows] + [998, 999]
    context = {
        "parents_of": {sid: frozenset({800}) for sid in sids},
        "uuid_of": {800: "TIS-240101ENG-800"},
        "types": {"TIS-240101ENG-800": "TIS"},
        "registrations": {800: [(1030, A_ASSAY, A_TITLE),
                                (1031, B_ASSAY, B_TITLE),
                                (1032, C_ASSAY, C_TITLE)]},
        "metadata": {sid: {"Type": "tif", "Tissue": "liver"} for sid in sids},
    }
    return findings, context


def _verdicts(keys, verdict="REJECT"):
    """The agent verdict file, in its own columns, for the given cohort keys."""
    return pd.DataFrame([{"cohort_key": k, "verdict": verdict,
                          "confidence": "HIGH",
                          "reason": f"an agent's argument about {k}"}
                         for k in keys])


def _c_keys(findings, context):
    """The cohort keys of the primary-surface (stratum C candidate) rows."""
    primary = findings[~findings.classification.isin(V.OFF_PRIMARY)]
    return [R.cohort_key(b) for b in M.build_blocks(primary, context,
                                                    floor=0.0)]


TARGET = {V.STRATUM_A: 2, V.STRATUM_B: 2, V.STRATUM_C: 2}


def _built(target=None, n_c=5, verdict="REJECT", certainty_share=None):
    findings, context = _world(n_c=n_c)
    verdicts = _verdicts(_c_keys(findings, context), verdict)
    drawn, stats = V.build_sample(
        findings, verdicts, context, type_reg=TYPE_REG, assay_pop=ASSAY_POP,
        fallback=FALLBACK, target=target or TARGET,
        certainty_share=certainty_share)
    return findings, context, verdicts, drawn, stats


def _fake_blocks(sizes):
    """Cohort-shaped dicts carrying only what `certainty_slice` reads.

    The slice needs a row count and a key and nothing else, so a fixture that
    built real blocks would be testing `build_blocks` again. The labs are
    ordered so that the KEY order and the SIZE order disagree, which is what
    makes the tie-break assertions able to say anything.
    """
    return [{"lab": f"L{i:02d}", "sample_type": "D.IMG", "parent_types": "TIS",
             "assay": A_TITLE, "field": M.LINEAGE_FIELD,
             "value": "ADD_PARENT_TO_ASSAY", "n_rows": size}
            for i, size in enumerate(sizes)]


# --- 1. the draw is reproducible, and provably not by accident ---------------


def test_the_docstring_records_the_seed():
    """The seed must be readable without reading the code that uses it.

    The brief's requirement is that a LATER reader can satisfy themselves the
    sample was not chosen after someone saw the answers. That reader starts at
    the module docstring, so the number has to be there and has to be the one
    the module actually draws with -- two places, pinned to each other here.
    """
    assert V.SEED == 20260824
    assert str(V.SEED) in V.__doc__


def test_two_draws_at_one_seed_are_identical():
    keys = [f"cohort-{i}" for i in range(60)]
    assert V.draw(keys, 20, seed=V.SEED) == V.draw(keys, 20, seed=V.SEED)


def test_a_different_seed_draws_a_different_sample():
    """THE HALF THAT MAKES THE TEST ABOVE MEAN ANYTHING.

    `draw` returning `keys[:n]` and ignoring the seed entirely passes the
    identity test perfectly. This is the one it fails. It is not a statement
    about randomness -- it is the statement that the seed is an INPUT, which is
    the whole claim the reproducibility argument rests on.
    """
    keys = [f"cohort-{i}" for i in range(60)]
    assert V.draw(keys, 20, seed=V.SEED) != V.draw(keys, 20, seed=V.SEED + 1)


def test_the_draw_does_not_depend_on_the_order_the_cohorts_arrive_in():
    """Shuffled input, identical sample.

    `build_blocks` returns cohorts sorted on band and row count, so a draw that
    preserved its input order would be a draw weighted by cohort size wearing a
    hash's clothes. A sample that moves when its input is reordered is not
    reproducible from a seed; it is reproducible from a seed AND an accident.

    WHAT THIS COVERS, EXACTLY. It fails when the sort is REMOVED (verified by
    mutation: `ranked = list(keys)` turns it red). It does NOT fail when only
    the `key` tiebreak is dropped, because two sha256 digests never collide
    over a few hundred cohorts -- so the tiebreak is documentation and this
    test does not pretend to cover it.
    """
    keys = [f"cohort-{i}" for i in range(60)]
    assert V.draw(keys, 20) == V.draw(list(reversed(keys)), 20)
    assert V.draw(keys, 20) == V.draw(sorted(keys, key=len), 20)


def test_the_draw_is_a_pure_function_of_the_seed_and_the_key():
    """Recomputable by hand, in any language, with no dependency on this file.

    This is the property an RNG cannot offer and the reason the module uses a
    hash order instead. A reader checking that the sample predates the answers
    needs to be able to verify one membership without running the package.
    """
    keys = [f"cohort-{i}" for i in range(60)]
    import hashlib
    expected = sorted(
        keys,
        key=lambda k: (hashlib.sha256(
            f"{V.SEED}|draw|{k}".encode("utf-8")).hexdigest(), k))[:20]
    assert V.draw(keys, 20) == expected


def test_the_draw_refuses_a_duplicate_cohort_key():
    with pytest.raises(ValueError, match="duplicate cohort key"):
        V.draw(["a", "b", "a"], 2)


def test_a_draw_larger_than_the_population_takes_all_of_it():
    assert sorted(V.draw(["a", "b", "c"], 99)) == ["a", "b", "c"]


def test_the_sample_is_drawn_at_cohort_level_and_never_weighted_by_rows():
    """A cohort of 10,745 rows and a cohort of 9 are one draw each.

    The real stratum A holds both. A row-weighted draw would put the operator
    in front of the same question hundreds of times and make the resulting rate
    a statement about big cohorts rather than about the gate.

    THE INFLATED COHORT IS CHOSEN BECAUSE THE CLEAN DRAW MISSED IT, and that
    choice is what makes the test able to fail. Inflating an already-drawn
    cohort leaves the SET unchanged under any size-ordered rule, so an earlier
    version of this test stayed green against a draw sorted on `-n_rows`
    (verified by mutation). Inflating a cohort the draw passed over means a
    size-aware sampler must pull it in.
    """
    findings, context = _world()
    verdicts = _verdicts(_c_keys(findings, context))
    # THE CERTAINTY SLICE IS SWITCHED OFF HERE, through the argument and never
    # by rebinding the constant. It is deliberately size-aware, so leaving it
    # on would make this test red against correct code -- and the property
    # under test belongs to the RANDOM half.
    kw = dict(type_reg=TYPE_REG, assay_pop=ASSAY_POP, fallback=FALLBACK,
              target={V.STRATUM_A: 4, V.STRATUM_B: 3, V.STRATUM_C: 2},
              certainty_share=0.0)
    lean, _ = V.build_sample(findings, verdicts, context, **kw)

    a_rows = findings[findings.classification == S.CLS_UNREACHABLE]
    drawn = {d["cohort_key"] for d in lean}
    missed = [k for k in
              (R.cohort_key(b) for b in M.build_blocks(a_rows, context,
                                                       floor=0.0))
              if k not in drawn]
    assert missed, "the draw took every cohort; nothing is left to inflate"
    lab = missed[0].split(R.KEY_DELIMITER)[0]

    twin = a_rows[a_rows.uuid.str.contains(lab)].head(1).assign(
        sample_id=999, uuid=f"TIS-240199{lab}-999")
    assert len(twin) == 1
    fat = pd.concat([findings, twin], ignore_index=True)

    heavy, _ = V.build_sample(fat, verdicts, context, **kw)
    assert ([d["cohort_key"] for d in lean]
            == [d["cohort_key"] for d in heavy])


def test_the_sheet_records_each_cohorts_row_count():
    """Step 2's requirement: the eventual rate must be reportable BOTH ways.

    Without `n_rows` on every row of the sheet, only the per-cohort rate can
    ever be computed, and the two differ by an order of magnitude on this
    population.
    """
    _f, _c, _v, drawn, _s = _built()
    sheet = V.to_csv(drawn)
    assert "n_rows" in sheet.columns and "n_samples" in sheet.columns
    assert (sheet.n_rows > 0).all()
    assert list(sheet.n_rows) == [d["block"]["n_rows"] for d in drawn]


def test_the_seed_rides_on_every_row_of_the_sheet():
    """A csv has no header comment a spreadsheet keeps. So the seed is a column.

    A sheet that cannot say which draw produced it cannot be re-derived, and
    the operator's copy will have been through at least one round trip.
    """
    _f, _c, _v, drawn, _s = _built()
    assert set(V.to_csv(drawn).seed) == {V.SEED}
    assert set(V.to_key(drawn, _v).seed) == {V.SEED}


# --- the certainty slice: observed rows, not sampled ones --------------------


def test_the_certainty_slice_takes_the_largest_cohorts_and_not_a_hash_draw():
    """Probability 1, largest first. Not a draw wearing a different name.

    The whole value of the slice is that a row inside it is OBSERVED, so it
    must be chosen by size and nothing else. A slice that ran through `draw`
    would be the same count of cohorts carrying the same sampling error, and
    the power document would then be printing an observation table over
    inferred rows.
    """
    blocks = _fake_blocks([5, 100, 20, 60, 1])
    taken, capped = V.certainty_slice(blocks, share=0.45, cap=20)
    assert not capped
    assert taken == [R.cohort_key(blocks[1])]        # 100 of 186 = 53.8%
    assert taken != V.draw([R.cohort_key(b) for b in blocks], 1)


def test_the_certainty_slice_stops_at_the_stated_share():
    """At or just above the target, never below it, and never one cohort more.

    Ten equal cohorts and a 0.45 target: five reach exactly 50%, four reach
    40%. Taking four would leave the slice under its own stated coverage and
    the document would print a share that does not match the claim above it.
    """
    blocks = _fake_blocks([10] * 10)
    taken, _capped = V.certainty_slice(blocks, share=0.45, cap=20)
    assert len(taken) == 5
    assert V.certainty_slice(blocks, share=0.0)[0] == []
    assert len(V.certainty_slice(blocks, share=0.71)[0]) == 8


def test_the_certainty_slice_is_capped_so_the_sitting_cannot_grow_silently():
    """A flat population would demand half the cohorts. The cap refuses.

    And it must SAY it refused: a slice that quietly stopped short would
    print a covered share below its stated target with nothing explaining
    why, which reads as a bug in the arithmetic rather than as a budget.
    """
    blocks = _fake_blocks([10] * 100)
    taken, capped = V.certainty_slice(blocks, share=0.45, cap=3)
    assert len(taken) == 3 and capped is True
    assert V.certainty_slice(blocks, share=0.45, cap=90)[1] is False


def test_the_certainty_slice_breaks_ties_on_the_cohort_key():
    """Equal-sized cohorts straddling the cut must not be picked by luck.

    Measured on the real extract: stratum A holds three cohorts of exactly
    1,071 rows at ranks 15, 16 and 17, and the 0.45 cut lands among them. A
    size-only sort is stable, so which of the three is inside the slice would
    be decided by the order `build_blocks` happened to return.
    """
    blocks = _fake_blocks([10] * 10)
    forward, _ = V.certainty_slice(blocks, share=0.45)
    backward, _ = V.certainty_slice(list(reversed(blocks)), share=0.45)
    assert forward == backward
    assert forward == sorted(forward)


def test_stratum_c_gets_no_certainty_slice():
    """Half its cohorts are already drawn; a slice there buys almost nothing.

    Asserted rather than left to the constant, because `CERTAINTY_STRATA`
    silently gaining a member would add cohorts to the operator's sitting for
    a stratum whose row coverage is already 69%.
    """
    _f, _c, _v, drawn, stats = _built()
    by_name = {s["stratum"]: s for s in stats}
    assert V.STRATUM_C not in V.CERTAINTY_STRATA
    assert by_name[V.STRATUM_C]["certainty_cohorts"] == 0
    assert not [d for d in drawn
                if d["stratum"] == V.STRATUM_C and d["part"] == "certainty"]
    for name in V.CERTAINTY_STRATA:
        assert by_name[name]["certainty_cohorts"] > 0


def test_the_certainty_slice_leaves_the_population_it_is_drawn_from():
    """Removed before the draw, not overlaid on it.

    Overlaying would let one cohort be both certain and sampled: counted twice
    in the coverage, and an OBSERVED row sitting inside a bound whose whole
    derivation assumes it was not observed.
    """
    _f, _c, _v, drawn, stats = _built()
    keys = [d["cohort_key"] for d in drawn]
    assert len(keys) == len(set(keys))
    for stat in stats:
        assert (stat["random_population_cohorts"]
                == stat["population_cohorts"] - stat["certainty_cohorts"])
        assert (stat["random_population_rows"]
                == stat["population_rows"] - stat["certainty_rows"])


def test_the_certainty_slice_displaces_no_random_pick():
    """Everything the pure random draw chose is still in the sitting.

    Shrinking the population the draw runs over only PROMOTES the cohorts left
    in it, so nothing chosen before can fall out -- but that is an argument,
    and this is the measurement. Without it a later change to the slice could
    quietly drop cohorts the operator was already going to be asked about.
    """
    _f, _c, _v, before, _s = _built(certainty_share=0.0)
    _f2, _c2, _v2, after, _s2 = _built()
    kept = {d["cohort_key"] for d in after}
    assert {d["cohort_key"] for d in before} <= kept
    assert len(kept) > len(before)


# --- the declared disagreement slice: selected on outcome, carrying no rate --


def _disputed_world():
    """A world where the gate removed some cohorts an agent ruled APPROVE."""
    findings, context = _world()
    a_keys = [R.cohort_key(b) for b in M.build_blocks(
        findings[findings.classification == S.CLS_UNREACHABLE], context,
        floor=0.0)]
    verdicts = pd.concat([_verdicts(_c_keys(findings, context), "REJECT"),
                          _verdicts(a_keys, "APPROVE")])
    return findings, context, verdicts, a_keys


def test_the_disagreement_slice_is_every_approve_the_gate_removed():
    """All of them, minus what the draw already has. Not a sample of them.

    Taking a random half would be strictly worse: the slice answers a
    which-one question, so every cohort in it is a case where an answer exists,
    and there is nothing about it that a smaller random subset improves.
    """
    findings, context, verdicts, a_keys = _disputed_world()
    on_surface = V.on_primary_surface(findings, context)
    blocks = M.build_blocks(
        findings[findings.classification == S.CLS_UNREACHABLE], context,
        floor=0.0)
    got = V.disagreement_slice(blocks, verdicts, on_surface, exclude=set())
    assert sorted(got) == sorted(a_keys)
    # and nothing an agent did NOT approve gets in
    only_rejects = _verdicts(a_keys, "REJECT")
    assert V.disagreement_slice(blocks, only_rejects, on_surface,
                                exclude=set()) == []


def test_the_disagreement_slice_never_repeats_a_cohort_already_drawn():
    """`exclude` is the draw, and it is honoured. A repeat is a double ruling.

    It is also a silent double count: the same cohort would appear once inside
    a bounded population and once inside a group that carries no rate.
    """
    findings, context, verdicts, a_keys = _disputed_world()
    on_surface = V.on_primary_surface(findings, context)
    blocks = M.build_blocks(
        findings[findings.classification == S.CLS_UNREACHABLE], context,
        floor=0.0)
    got = V.disagreement_slice(blocks, verdicts, on_surface,
                               exclude={a_keys[0], a_keys[1]})
    assert a_keys[0] not in got and a_keys[1] not in got
    assert len(got) == len(a_keys) - 2


def test_the_disputed_cohorts_are_additive_and_enter_no_bound():
    """They add to the sitting and to NO population any bound is taken over.

    THIS IS THE FAILURE THE GROUP INVITES. A cohort selected because two
    instruments disagreed about it is, by construction, enriched for exactly
    the outcome being measured; letting it into the random draw's denominator
    or its numerator would bias the one number the sitting exists to produce.
    """
    findings, context, verdicts, _a = _disputed_world()
    drawn, stats = V.build_sample(
        findings, verdicts, context, type_reg=TYPE_REG, assay_pop=ASSAY_POP,
        fallback=FALLBACK, target=TARGET)
    disputed = [d for d in drawn if d["part"] == V.DISAGREEMENT]
    assert disputed, "this fixture produced no disagreement at all"

    keys = [d["cohort_key"] for d in drawn]
    assert len(keys) == len(set(keys))
    for stat in stats:
        # the bounds are unchanged by the group's existence
        assert (stat["random_population_cohorts"]
                == stat["population_cohorts"] - stat["certainty_cohorts"])
        assert stat["cohort_bound_k"] == V.zero_event_bound(
            stat["random_population_cohorts"], stat["random_cohorts"])
        # and the coverage count deliberately excludes them
        assert (stat["rows_seen"]
                == stat["certainty_rows"] + stat["random_rows"])
        assert (stat["cohorts_to_rule"] == stat["sampled_cohorts"]
                + stat["disagreement_cohorts"])


def test_the_document_prints_the_disputed_group_with_no_bound_beside_it():
    """Its own heading, and not one bound word inside it.

    The group is the sharpest evidence in the population and the easiest thing
    in this document to misuse: 32 cohorts enriched for false blocks would give
    a spectacular and completely meaningless "false-block rate".
    """
    findings, context, verdicts, _a = _disputed_world()
    _d, stats = V.build_sample(
        findings, verdicts, context, type_reg=TYPE_REG, assay_pop=ASSAY_POP,
        fallback=FALLBACK, target=TARGET)
    part3 = _section(V.power_report(stats), "## Part 3 -- declared disagreement")
    for forbidden in ("<=", "at most", "0-event", "hypergeometric",
                      "kish", "bounds the"):
        assert forbidden not in part3.lower(), (
            f"Part 3 carries {forbidden!r}; it is selected on outcome and can "
            "carry no rate")
    assert "selected on" in part3.lower() and "outcome" in part3.lower()
    assert "no rate, bound or extrapolation" in part3.lower()
    for stat in stats:
        if stat["disagreement_cohorts"]:
            assert f'| {stat["disagreement_cohorts"]} ' in part3


# --- 2. the power, stated before anyone rules --------------------------------


def test_zero_event_bound_is_the_exact_hypergeometric_one():
    """Checked against the definition, computed independently here.

    The bound is the largest K with `C(N-K,n)/C(N,n) > 0.05`. Recomputing it
    from `math.comb` is a different arithmetic path to the same number, so an
    off-by-one or a flipped comparison in the running product shows up.
    """
    from math import comb
    for population, sample in ((655, 100), (137, 50), (106, 50), (20, 3)):
        expected = max(k for k in range(population - sample + 1)
                       if comb(population - k, sample) / comb(population,
                                                              sample) > 0.05)
        assert V.zero_event_bound(population, sample) == expected


def test_a_census_bounds_the_rate_at_zero():
    """Every cohort was looked at, so 0 found means 0 exist. Exactly.

    Reporting a positive bound on a census would understate what the sitting
    achieved, and stratum B and C are close enough to their populations that
    this is not a theoretical branch.
    """
    assert V.zero_event_bound(50, 50) == 0
    assert V.zero_event_bound(50, 80) == 0
    # 49 of 50 is not a census and still bounds at 0: missing one bad cohort
    # has probability 1/50 = 0.02, under the 0.05 the bound is set at. 40 of
    # 50 is where the first non-zero answer appears.
    assert V.zero_event_bound(50, 49) == 0
    assert V.zero_event_bound(50, 40) == 1


def test_the_finite_population_correction_actually_bites():
    """The exact bound must be TIGHTER than the rule of three, and visibly.

    Without this the hypergeometric arithmetic could be replaced by `3/n` and
    nothing would notice. At 50 of 137 the binomial answer is ~5.8% and the
    exact one is materially below it, because a third of the population was
    seen.
    """
    n, population = 50, 137
    binomial = 1 - 0.05 ** (1 / n)
    exact = V.zero_event_bound(population, n) / population
    assert exact < binomial * 0.85, (exact, binomial)


def test_kish_effective_n_collapses_when_one_cohort_dominates():
    """The number that says a row-weighted estimate is worth almost nothing.

    Stratum C's draw is 50 cohorts of which one holds 24,050 of 30,122 rows.
    Fifty equal cohorts would be worth fifty; this says what it is really
    worth, and a `kish_effective_n` that just returned the count would pass
    every other test in this file.
    """
    assert V.kish_effective_n([1] * 50) == pytest.approx(50)
    assert V.kish_effective_n([24050] + [120] * 49) < 3


def test_the_power_statement_refuses_to_bound_the_row_rate():
    """The row bound is 1 - coverage, and it is named a refusal in the report.

    A cohort-level draw says nothing about rows in cohorts it never drew. The
    figure is arithmetic; the WORDING is the deliverable, because a table of
    bounds with no sentence beside it reads as a precision claim.
    """
    stat = V.power(V.STRATUM_A, population_cohorts=655, population_rows=90478,
                   sampled_rows=[100] * 100)
    assert stat["random_row_coverage"] == pytest.approx(10000 / 90478)
    assert stat["row_bound_worst_case"] == pytest.approx(1 - 10000 / 90478)
    report = V.power_report([stat])
    assert "refusal, not a result" in report
    assert "cannot speak" in report or "says nothing whatever" in report


def test_the_power_report_states_both_bounds_for_every_stratum():
    """Neither table may be dropped, and neither may lose a stratum.

    Printing only the per-cohort table is the specific failure Step 4 forbids:
    it lets the sample imply a row-weighted precision it does not have.
    """
    _f, _c, _v, _d, stats = _built()
    report = V.power_report(stats)
    assert "taken with certainty" in report and "the random draw" in report
    assert "per row" in report
    for stat in stats:
        assert stat["stratum"] in report
        assert stat["question"] in report
    assert str(V.SEED) in report


def test_the_two_parts_are_never_pooled_in_the_power_document():
    """No error bound in the document spans an observed row and a sampled one.

    THIS IS THE FAILURE MODE THE SLICE INTRODUCES. Once part of a stratum is
    observed, the tempting thing to print is one flattering "row error <= X%"
    over the union -- and it would be wrong in the direction that matters,
    because the certainty rows carry no error and would drag the figure down
    over rows nobody looked at. The bounds in the document belong to the
    RANDOM population; the only figure spanning both parts is a count, and it
    is labelled one.
    """
    _f, _c, _v, _d, stats = _built()
    report = V.power_report(stats)

    # THE BOUND IS RECOMPUTED FROM THE POPULATION FIGURES, NOT READ OFF THE
    # FIELD THE REPORT PRINTS. An earlier version of this test asserted
    # `row_bound_worst_case` appeared in the document and that the pooled value
    # did not -- which is vacuous, because a `power` that POOLS puts the pooled
    # number in that field and the two comparisons agree with each other.
    # Verified by mutation: pooling survived it. These two expressions are
    # independent of the implementation and of each other.
    checked = 0
    for stat in stats:
        random_only = 1.0 - stat["random_rows"] / stat["random_population_rows"]
        pooled = 1.0 - stat["rows_seen"] / stat["population_rows"]
        assert stat["row_bound_worst_case"] == pytest.approx(random_only), (
            f'{stat["stratum"]}: the row bound is not the random part\'s')
        assert f"<= {random_only:.1%}" in report
        if abs(pooled - random_only) > 5e-4:
            checked += 1
            assert f"<= {pooled:.1%}" not in report, (
                f'{stat["stratum"]}: the document prints a row bound pooled '
                "over observed and sampled rows")
    assert checked, (
        "no stratum in this fixture has a pooled bound differing from its "
        "random one, so the assertion above could not have caught pooling")

    assert "a count, not a bound" in report.lower()
    assert "never be quoted as one" in report
    assert "Observed, not inferred" in report


def test_every_bound_is_scoped_to_the_population_it_was_measured_on():
    """The cohort bound is over what is LEFT after part 1, not the stratum.

    THE OTHER HALF OF THE POOLING FAILURE, and it flatters in the same
    direction. Computing the bound against the full stratum quietly widens the
    denominator with cohorts that were never in the random population -- 655
    rather than 640 on the real extract -- so a clean sitting reports a rate
    over a set the sample did not describe. Verified by mutation: scoping the
    bound to `population_cohorts` survived every other test in this file.

    Both expressions below are recomputed from the reported population
    figures, so neither can agree with a mutation by construction, and the
    last assertion refuses to pass on a fixture where the two coincide.
    """
    _f, _c, _v, _d, stats = _built()
    differed = 0
    for stat in stats:
        scoped = V.zero_event_bound(stat["random_population_cohorts"],
                                    stat["random_cohorts"])
        whole = V.zero_event_bound(stat["population_cohorts"],
                                   stat["random_cohorts"])
        assert stat["cohort_bound_k"] == scoped, (
            f'{stat["stratum"]}: the cohort bound is not the random part\'s')
        assert stat["cohort_bound_rate"] == pytest.approx(
            scoped / stat["random_population_cohorts"])
        differed += int(scoped != whole)
    assert differed, (
        "no stratum here has a bound that differs between the two scopings, "
        "so the assertion above could not have caught the wrong one")


def test_the_rendered_part_2_table_names_the_population_the_bound_belongs_to():
    """The DOCUMENT, not the dict. Part 2's table must print 640, never 655.

    THE STAT DICT WAS ALREADY GUARDED AND THE RENDERING WAS NOT. A reviewer
    mutated `power_report` to print `population_cohorts` in Part 2's table and
    every test in this file stayed green: the numbers were right in the dict
    and wrong on the page the operator reads. This slices the section out of
    the rendered markdown and reads it.
    """
    _f, _c, _v, _d, stats = _built()
    part2 = _section(V.power_report(stats),
                     "## Part 2 -- the random draw.")
    differed = 0
    for stat in stats:
        assert f'| {stat["random_population_cohorts"]:,} |' in part2, (
            f'{stat["stratum"]}: Part 2 does not name the population its '
            "bound belongs to")
        if stat["population_cohorts"] != stat["random_population_cohorts"]:
            differed += 1
            assert f'| {stat["population_cohorts"]:,} |' not in part2, (
                f'{stat["stratum"]}: Part 2 prints the whole stratum as the '
                "population its bound is over")
    assert differed, (
        "every stratum here has an empty certainty slice, so the assertion "
        "above could not have caught the wrong population")


def test_the_rendered_part_1_carries_no_bound_of_any_kind():
    """An observation table with a confidence bound on it is a category error.

    A reviewer mutated Part 1 to gain a 0-event bound column and nothing went
    red. The rows in part 1 were LOOKED AT; attaching a sampling bound to them
    would invite the operator to read observed rows as estimated ones, which is
    the precise confusion the two-part split exists to prevent.
    """
    _f, _c, _v, _d, stats = _built()
    part1 = _section(V.power_report(stats), "## Part 1 -- taken with certainty")
    for forbidden in ("<=", "at most", "0-event", "bounds", "hypergeometric"):
        assert forbidden not in part1.lower(), (
            f"Part 1 carries {forbidden!r}; it describes observed rows and "
            "must carry no bound")
    assert "Observed, not inferred" in part1
    # the share it DOES carry is not a bound, and must still be there
    for stat in stats:
        if stat["certainty_cohorts"]:
            assert f'{stat["certainty_row_share"]:.1%}' in part1


def test_the_rendered_lede_does_not_pool_the_parts():
    """The rater-facing artifact, guarded on its own text.

    IT SHIPPED POOLED. The lede read "115 drawn of 655 (0 found bounds the rate
    at 2.7%)" -- a count spanning parts 1 and 2, a population spanning the
    stratum, and a rate belonging to neither. Numerically conservative and
    still wrong, on the one page a reviewer actually reads. Three separate
    mutations of it -- the bound going to 0.0%, the bound vanishing, the
    population reverting to the stratum -- all stayed green before this.
    """
    _f, _c, _v, drawn, stats = _built()
    page = V.render(drawn, stats)
    lede = page[page.index('<p class="lede">'):page.index('<div class="callout"')]
    differed = 0
    for stat in stats:
        assert f'{stat["random_population_cohorts"]:,} left' in lede
        assert f'{stat["cohort_bound_rate"]:.1%}' in lede
        assert str(stat["certainty_cohorts"]) + " certain" in lede
        if stat["population_cohorts"] != stat["random_population_cohorts"]:
            differed += 1
            assert f'{stat["population_cohorts"]:,} left' not in lede
        # the bound must be a real number, not a rendered zero
        assert stat["cohort_bound_rate"] > 0
    assert differed, "no stratum here could have shown the pooled population"
    assert "belong to the drawn part alone" in lede
    assert "&amp;" not in lede, "the lede is double-escaped"


def test_the_power_document_records_the_convergence_and_the_blinding_caveat():
    """Two facts the operator must see beside the table, not in a report to me.

    The convergence is the only evidence of any kind bearing on the 99,309
    rows, and it is NOT human validation -- a document that printed the
    agreement without that sentence would be handing him a reason to rule
    quickly. The blinding caveat is the mirror: nobody may later read this
    sitting as fully blind, because `classification` recovers the stratum.
    """
    _f, _c, _v, _d, stats = _built()
    convergence = {"judged": 1012, "judged_left": 801, "rejected": 756,
                   "rejected_left": 650, "rejected_still": 106,
                   "approved": 126, "approved_left": 49,
                   "nonreject": 256, "nonreject_left": 151}
    report = V.power_report(stats, convergence=convergence)
    # BOTH HALVES, and the disagreement half is the one that was missing. The
    # document once printed only the REJECT figures and told the reader the two
    # instruments "agree on the large majority" -- while the same gate had
    # removed 38.9% of what that instrument said should be registered.
    for figure in ("1,012", "801", "756", "650", "126", "49", "256", "151",
                   "86.0%", "38.9%"):
        assert figure in report, figure
    assert "diverge materially on inclusion" in report
    assert "none of this is human validation" in report.lower()
    assert "converge" in report.lower() and "diverge" in report.lower()
    # WAS `"not blind" in report.lower() or "NOT" in report`, WHICH COULD NOT
    # FAIL: "NOT" survives in "if NOTHING is found" and "the claim it does NOT
    # support" with the whole blinding section deleted. The section is
    # identified by its own heading now, and the sentence inside it that a
    # later reader would rely on.
    caveat = _section(report, "## What the sample is NOT")
    assert "fully blind" in caveat
    assert "only partly unanchored" in caveat
    assert S.CLS_ABSENCE_LINEAGE in caveat

    # and it must not appear when there is nothing measured to report
    assert "1,012" not in V.power_report(stats)


def test_agent_convergence_counts_what_left_the_primary_surface():
    """The figures in the document are measured here, never written down.

    A hard-coded 801 would be a number that stops being true the first time a
    lane changes and says nothing when it does.
    """
    findings, context = _world()
    keys = _c_keys(findings, context)
    a_keys = [R.cohort_key(b) for b in M.build_blocks(
        findings[findings.classification == S.CLS_UNREACHABLE], context,
        floor=0.0)]
    # one REJECT still on the surface, one REJECT that never reaches it, one
    # APPROVE still on it, and two APPROVEs the gate removed -- so BOTH halves
    # of the return carry a non-zero count and a mutation to either is visible
    verdicts = pd.concat([
        _verdicts(keys[:1], "REJECT"),
        _verdicts(["GONE|D.IMG|TIS|" + A_TITLE + "|(lineage)|X"], "REJECT"),
        _verdicts(keys[1:2], "APPROVE"),
        _verdicts(a_keys[:2], "APPROVE"),
        _verdicts(a_keys[2:3], "UNSURE")])
    got = V.agent_convergence(findings, verdicts, context)
    assert got == {"judged": 6, "judged_left": 4,
                   "rejected": 2, "rejected_left": 1, "rejected_still": 1,
                   "approved": 3, "approved_left": 2,
                   "nonreject": 4, "nonreject_left": 3}


# --- 3. the rater can punt ---------------------------------------------------


def test_the_sheet_offers_a_punt_the_rater_cannot_miss():
    """`UNSURE` on the page, in the vocabulary, and argued for in the callout.

    Forcing a binary is how a false-approve floor gets manufactured, and this
    project measured one at ~5% across 15 agents. The option existing in a
    tuple is not enough: it has to be rendered, and the page has to tell the
    rater it is a legitimate answer rather than a failure to do the work.
    """
    _f, _c, _v, drawn, stats = _built()
    page = V.render(drawn, stats)
    assert V.PUNT in V.VERDICTS
    assert f'<option value="{V.PUNT}">' in page
    assert "I CANNOT TELL" in page
    assert "real answer" in page


def test_the_verdict_vocabulary_must_cover_every_verdict_the_agents_used():
    """A verdict this sheet cannot render is one Step 6 cannot pool.

    The failure is silent in the worst direction: an unrecognised REJECT-like
    verdict would simply shrink the stratum C population and nothing on the
    sheet would say the population had shrunk.
    """
    good = _verdicts(["a|b|c|d|e|f"], verdict="WRONG_ASSAY")
    V.check_verdict_vocabulary(good)
    bad = _verdicts(["a|b|c|d|e|f"], verdict="MAYBE_LATER")
    with pytest.raises(ValueError, match="MAYBE_LATER"):
        V.check_verdict_vocabulary(bad)


# --- the sheet withholds the answer key --------------------------------------


def test_the_sheet_carries_no_agent_verdict():
    """Stratum C measures the reject side, not agreement with a shown reject.

    The agent's ARGUMENT is the anchor -- a rater handed a reason tends to
    ratify it -- so neither the verdict nor the reason may appear on the sheet
    or in the page. Asserted on the rendered text and not only on the column
    names, because a reason leaking into an evidence cell would pass a column
    check.
    """
    _f, _c, verdicts, drawn, stats = _built()
    sheet = V.to_csv(drawn)
    page = V.render(drawn, stats)
    assert not [c for c in sheet.columns if "agent" in c or "verdict" == c[:7]
                and c != "verdict"]
    assert "verdict" in sheet.columns and set(sheet.verdict) == {""}
    blob = sheet.to_csv(index=False)
    for reason in verdicts.reason:
        assert reason not in blob
        assert reason not in page
    assert "stratum" not in sheet.columns


def test_the_key_file_carries_the_stratum_and_the_agent_verdict():
    """The half the sheet withholds, kept where Step 6 can find it.

    Withholding the anchor is only defensible if the analysis can still
    stratify. Every drawn cohort must appear here with its stratum, its size
    and whatever an agent said about it.
    """
    _f, _c, verdicts, drawn, _s = _built()
    key = V.to_key(drawn, verdicts)
    assert len(key) == len(drawn)
    assert set(key.stratum) <= set(V.STRATA)
    assert set(key.columns) >= {"cohort_id", "stratum", "part", "cohort_key",
                                "n_rows", "agent_verdict", "agent_reason",
                                "seed", "draw_digest"}
    assert set(key.part) <= {"certainty", "random"}
    c_rows = key[key.stratum == V.STRATUM_C]
    assert len(c_rows) and set(c_rows.agent_verdict) == {"REJECT"}


def test_the_csv_the_html_and_the_key_describe_one_selection():
    """Three renderings of one draw, not three draws that agree today."""
    _f, _c, verdicts, drawn, stats = _built()
    sheet, key, page = (V.to_csv(drawn), V.to_key(drawn, verdicts),
                        V.render(drawn, stats))
    assert list(sheet.cohort_id) == list(key.cohort_id)
    assert list(sheet.cohort_key) == list(key.cohort_key)
    for cid in sheet.cohort_id:
        assert f'>{cid}</span>' in page


# --- the populations ---------------------------------------------------------


def test_the_three_strata_must_be_disjoint():
    """A cohort in two strata is ruled once and counted in two rates.

    It looks structural -- A and B are cuts of one column and C is the
    complement -- but the cohort key holds the assay TITLE, and four titles on
    the real extract resolve to two internal ids each. Here the collision is
    forced by giving a primary-surface row the same key as an unreachable one.
    """
    findings, context = _world()
    collide = findings[findings.classification == S.CLS_UNREACHABLE].head(1)
    # the SAME lab, so the six-field key matches; only the class differs
    collide = collide.assign(classification=S.CLS_ABSENCE_LINEAGE,
                             sample_id=998, uuid=f"TIS-240198{LABS[0]}-998")
    findings = pd.concat([findings, collide], ignore_index=True)
    verdicts = _verdicts(_c_keys(findings, context))
    with pytest.raises(ValueError, match="in both"):
        V.strata(findings, verdicts, context)


def test_row_accounting_names_the_rows_that_reach_no_cohort():
    """`build_blocks` drops a null precedent rate silently. This does not.

    `rate >= floor` is False on a null, so a row with no rate reaches no
    cohort and the population the sample claims to describe is quietly larger
    than the population it was drawn from. On the real extract that is 8 of
    stratum A's 90,338 -- small, and a silent shortfall is not.
    """
    blocks = [{"n_rows": 10}, {"n_rows": 5}]
    V.check_row_accounting("A", blocks, population=16, unrated=1)
    with pytest.raises(ValueError, match="no precedent rate"):
        V.check_row_accounting("A", blocks, population=16, unrated=0)


def test_stratum_c_is_only_the_agent_rejects_still_on_a_primary_surface():
    """Not every judged cohort, and not every primary cohort. The intersection.

    A stratum C built from all agent verdicts would ask about proposals the
    rework already routed away; one built from the whole primary surface would
    not be measuring the reject side at all.
    """
    findings, context = _world()
    keys = _c_keys(findings, context)
    verdicts = pd.concat([_verdicts(keys[:2], "REJECT"),
                          _verdicts(keys[2:], "APPROVE")])
    parts = V.strata(findings, verdicts, context)
    assert {R.cohort_key(b) for b in parts[V.STRATUM_C]["blocks"]} == set(
        keys[:2])


# --- the facts on the sheet are measured, not copied -------------------------


def test_the_facts_are_recomputed_from_the_indexes_and_checked_on_the_rows():
    """`type_registrations` disagreeing with `gate.type_registration_index`.

    Reading the number off the row would make this sheet a second RENDERING of
    the detector's output; computing it from the package's own index and then
    asserting the row agrees makes it a second MEASUREMENT. Only the second can
    notice a detector that wrote the wrong number.
    """
    findings, context = _world()
    verdicts = _verdicts(_c_keys(findings, context))
    wrong = {**TYPE_REG, ("D.IMG", A_ASSAY): 77}
    with pytest.raises(ValueError, match="registration"):
        V.build_sample(findings, verdicts, context, type_reg=wrong,
                       assay_pop=ASSAY_POP, fallback=FALLBACK,
                       target={V.STRATUM_A: 2, V.STRATUM_B: 1,
                               V.STRATUM_C: 1})


def test_the_namespace_is_recomputed_and_checked_the_same_way():
    """`id_namespace` against `_schema.id_namespace` over the fallback set.

    A consumer joining a `seek_fallback` id against `dmac.internal_assays`
    drops it, and one joining an `internal` id against `seek_production.assays`
    gets a populated wrong answer. The sheet must not be the place that gets
    it wrong quietly.
    """
    findings, context = _world()
    verdicts = _verdicts(_c_keys(findings, context))
    with pytest.raises(ValueError, match="id_namespace"):
        V.build_sample(findings, verdicts, context, type_reg=TYPE_REG,
                       assay_pop=ASSAY_POP, fallback={A_ASSAY},
                       target={V.STRATUM_A: 2, V.STRATUM_B: 1,
                               V.STRATUM_C: 1})


def test_both_precedent_grains_reproduce_the_column_the_detector_wrote():
    """The two rates are recomputed here; they must equal `precedent_rate`.

    The row carries one rate and `precedent_direction` says which. The sheet
    shows both directions, computed from the row's own three counts, so the
    arithmetic here can silently drift from `precedent.mine_precedent`'s. This
    is the only thing that stops it.
    """
    ok = _findings([_row(LABS[0], 900, cls=S.CLS_UNREACHABLE, assay=A_ASSAY,
                         title=A_TITLE, counts=(2, 3, 0), rate=0.4,
                         direction="propagation_rate", type_regs=0)])
    V.check_rates_reproduce_the_row(ok)

    lying = _findings([_row(LABS[0], 900, cls=S.CLS_UNREACHABLE, assay=A_ASSAY,
                            title=A_TITLE, counts=(2, 3, 0), rate=0.9,
                            direction="propagation_rate", type_regs=0)])
    with pytest.raises(ValueError, match="do not reproduce"):
        V.check_rates_reproduce_the_row(lying)


def test_the_sheet_carries_every_field_the_brief_names():
    """Step 3's list, asserted as columns rather than trusted to review.

    Each of these answers a question a rater asked on an earlier sitting:
    `assay_population` is the number the bootstrap split turned on and has no
    column anywhere else in the package, and `precedent_supports` is the one
    predicate that says whether the house has EVER made this co-registration.
    """
    _f, _c, _v, drawn, _s = _built()
    sheet = V.to_csv(drawn)
    for column in ("evidence", "type_registrations", "assay_population",
                   "precedent_supports", "precedent_rate_propagation",
                   "precedent_rate_reverse", "id_namespace", "example_uuids",
                   "example_metadata", "n_examples_shown"):
        assert column in sheet.columns, column
    assert (sheet.example_uuids.str.len() > 0).all()
    assert (sheet.example_metadata.str.len() > 0).all()
    assert set(sheet.assay_population) == {ASSAY_POP[A_ASSAY],
                                           ASSAY_POP[B_ASSAY],
                                           ASSAY_POP[C_ASSAY]}


# --- the page cannot overwrite a ruling the operator already made ------------


def test_this_sheet_cannot_overwrite_a_mode_1_or_a_mode_2_ruling():
    """A third sheet on a shared localStorage prefix loses work silently.

    Stratum C's cohorts ARE Mode 2 cohorts and carry Mode 2 keys, so a shared
    keyspace here is not a hypothetical collision -- it is a guaranteed one on
    every stratum C cohort the operator has already seen.
    """
    _f, _c, _v, drawn, stats = _built()
    page = V.render(drawn, stats)
    assert V._LS_VALIDATION not in (V._LS_MODE1, M._LS_MODE2)
    assert V._LS_VALIDATION in page
    assert "mode1-review:" not in page and "mode2-review-v2:" not in page


def test_render_refuses_to_ship_if_reviews_literals_moved():
    """Two string substitutions into another module's script. Both must be loud.

    A silent `.replace` miss ships the page under Mode 1's storage prefix, or
    exports a column called `ruling` out of a sheet whose csv calls it
    `verdict` -- and neither shows up anywhere except in the operator's
    exported file, after the sitting.
    """
    original = R.SCRIPT
    _f, _c, _v, drawn, stats = _built()
    try:
        R.SCRIPT = original.replace(V._LS_MODE1, 'var LS = "renamed:";')
        with pytest.raises(AssertionError, match="storage prefix"):
            V.render(drawn, stats)
        R.SCRIPT = original.replace(V._HDR_MODE1, '"a","b"')
        with pytest.raises(AssertionError, match="export header"):
            V.render(drawn, stats)
    finally:
        R.SCRIPT = original


def test_the_exported_file_names_the_columns_the_csv_names():
    """The html export and the csv must be one format, not two.

    The operator rules the csv or the page, whichever is in front of him, and
    hands back one file. If the page exports `ruling` and the csv says
    `verdict`, Step 6 silently reads a column of NaN.
    """
    _f, _c, _v, drawn, stats = _built()
    page = V.render(drawn, stats)
    assert V._HDR_VALIDATION in page
    for field in V.FILL_IN:
        assert f'"{field}"' in page
        assert field in V.to_csv(drawn).columns


# --- the real extract --------------------------------------------------------


@pytest.fixture(scope="module")
def reworked(tmp_path_factory) -> pd.DataFrame:
    """The REWORKED detector, run over the real extract into a scratch dir.

    NOT a csv read off disk, for the reason `test_assay_hygiene_rulings.py`
    gives: `assay-hygiene/findings.csv` is the PRE-rework artifact and carries
    neither `CLS_UNREACHABLE` nor `CLS_BOOTSTRAP`, so strata A and B would both
    be empty and every figure below would be zero.
    """
    if not (EXTRACT / "samples.parquet").exists():
        pytest.skip("no extract; nothing to run the detector over")
    missing = [f for f in EVIDENCE_INPUTS if not (ARTIFACTS / f).exists()]
    if missing:
        pytest.skip(f"no {missing}; run run_evidence.py first")
    out = tmp_path_factory.mktemp("reworked")
    for name in EVIDENCE_INPUTS:
        shutil.copy(ARTIFACTS / name, out / name)
        (out / name).chmod(0o644)
    assert X.main(str(EXTRACT), str(out)) == 0
    return pd.read_csv(out / "findings.csv", low_memory=False)


def test_the_real_extract_draws_the_stratified_sample_it_documents(reworked):
    """Every figure this task reports, re-derived by the suite.

    Re-measured 2026-08-31 over `assets/RUN1/01-extract`. Populations: stratum
    A is 655 cohorts over 90,338 rows (8 of which carry no precedent rate and
    reach no cohort), B is 137 over 8,971, and C is 106 of the 756 agent
    REJECT cohorts still on a primary surface, over 43,468 rows.

    THE ROW COUNTS MOVED AND THE COHORT COUNTS DID NOT, which is the shape to
    expect: the samples-row refusal of 2026-08-31 removed 448 proposals about
    samples with no `samples` row -- 140 of them in stratum A, 136 in C -- and
    not one cohort was emptied by it in either. A read 90,478 and C 43,604
    before that date.

    The sitting is **251 cohorts**. The certainty slice takes A's 15 largest
    (41,281 rows, 45.7%) and B's 4 largest (4,054 rows, 45.2%) with
    probability 1; C gets none. The random draw then takes 100 of A's
    remaining 640, 50 of B's remaining 133 and 50 of C's 106, and the sampled
    design ends up looking at 52.3% / 68.5% / 69.0% of each stratum's rows.

    On top of that, the declared disagreement slice adds **32 cohorts / 1,578
    rows** an agent ruled APPROVE and the gate removed -- 17 in A and 15 in B,
    being the 45 such cohorts inside those two strata (21 + 24) minus the 13
    the draw already had. Four more sit outside A and B entirely.
    """
    verdicts_path = ARTIFACTS / "mode2-verdicts-review.csv"
    if not verdicts_path.exists():
        pytest.skip("no mode2-verdicts-review.csv; stratum C cannot be built")
    verdicts = pd.read_csv(verdicts_path)

    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")
    nodes = pd.read_parquet(EXTRACT / "nodes.parquet")
    context = R.load_context(EXTRACT)
    context["analysis_twins"] = M.analysis_twins(assays)

    drawn, stats = V.build_sample(
        reworked, verdicts, context,
        type_reg=G.type_registration_index(membership, assays, nodes),
        assay_pop=M2.assay_population(membership, assays),
        fallback=P.fallback_assay_ids(assays))

    by_name = {s["stratum"]: s for s in stats}
    assert by_name[V.STRATUM_A]["population_cohorts"] == 655
    assert by_name[V.STRATUM_A]["population_rows"] == 90338
    assert by_name[V.STRATUM_B]["population_cohorts"] == 137
    assert by_name[V.STRATUM_B]["population_rows"] == 8971
    assert by_name[V.STRATUM_C]["population_cohorts"] == 106
    assert by_name[V.STRATUM_C]["population_rows"] == 43468

    assert len(drawn) == 251
    assert [by_name[n]["cohorts_to_rule"] for n in V.STRATA] == [132, 69, 50]
    assert [by_name[n]["sampled_cohorts"] for n in V.STRATA] == [115, 54, 50]
    assert [by_name[n]["disagreement_cohorts"] for n in V.STRATA] == [17, 15, 0]
    assert by_name[V.STRATUM_A]["disagreement_rows"] == 874
    assert by_name[V.STRATUM_B]["disagreement_rows"] == 704
    assert [by_name[n]["certainty_cohorts"] for n in V.STRATA] == [15, 4, 0]
    assert by_name[V.STRATUM_A]["certainty_rows"] == 41281
    assert by_name[V.STRATUM_B]["certainty_rows"] == 4054
    for name in (V.STRATUM_A, V.STRATUM_B):
        assert by_name[name]["certainty_row_share"] == pytest.approx(
            0.45, abs=0.01)
        assert not by_name[name]["certainty_capped"]
    assert [by_name[n]["random_cohorts"] for n in V.STRATA] == [100, 50, 50]
    assert [by_name[n]["random_population_cohorts"] for n in V.STRATA] == [
        640, 133, 106]
    assert by_name[V.STRATUM_A]["rows_seen_share"] == pytest.approx(
        0.523, abs=5e-4)
    assert by_name[V.STRATUM_B]["rows_seen_share"] == pytest.approx(
        0.685, abs=5e-4)
    assert by_name[V.STRATUM_C]["rows_seen_share"] == pytest.approx(
        0.690, abs=5e-4)
    assert by_name[V.STRATUM_C]["kish_n_eff"] < 3

    # the certainty slice cost the operator 19 cohorts and lost him nothing:
    # every cohort the pure random draw would have chosen is still in the
    # sitting, because removing cohorts from a hash order only promotes others
    pure, _ = V.build_sample(
        reworked, verdicts, context,
        type_reg=G.type_registration_index(membership, assays, nodes),
        assay_pop=M2.assay_population(membership, assays),
        fallback=P.fallback_assay_ids(assays), certainty_share=0.0)
    # the RANDOM half of that run is the pre-slice draw; its disagreement
    # group is larger there only because fewer of its members were displaced
    # into a certainty slice that does not exist in this comparison run
    pure_random = {d["cohort_key"] for d in pure if d["part"] == "random"}
    assert len(pure_random) == 200
    assert pure_random <= {d["cohort_key"] for d in drawn}

    convergence = V.agent_convergence(reworked, verdicts, context)
    assert convergence == {"judged": 1012, "judged_left": 801,
                           "rejected": 756, "rejected_left": 650,
                           "rejected_still": 106,
                           "approved": 126, "approved_left": 49,
                           "nonreject": 256, "nonreject_left": 151}


def test_the_real_extract_sample_is_the_same_one_tomorrow(reworked):
    """The draw over the real population, twice, must be identical.

    The synthetic determinism tests run over 60 invented keys. This one runs
    over the 655 / 137 / 106 real ones, where the cohort keys carry the
    punctuation, spacing and unicode of real assay titles -- a digest computed
    over a differently-encoded key would still be deterministic and would still
    be the wrong sample.
    """
    verdicts_path = ARTIFACTS / "mode2-verdicts-review.csv"
    if not verdicts_path.exists():
        pytest.skip("no mode2-verdicts-review.csv; stratum C cannot be built")
    verdicts = pd.read_csv(verdicts_path)
    context = R.load_context(EXTRACT)
    parts = V.strata(reworked, verdicts, context)
    for name in V.STRATA:
        keys = [R.cohort_key(b) for b in parts[name]["blocks"]]
        assert V.draw(keys, V.TARGET[name]) == V.draw(keys, V.TARGET[name])
        assert (V.draw(keys, V.TARGET[name])
                != V.draw(keys, V.TARGET[name], seed=V.SEED + 1))
