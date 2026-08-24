"""The stratified validation sample, and the sheet a human rules it on.

WHAT THIS FILE IS PROTECTING. `tests/test_assay_hygiene_rulings.py` proved that
the operator's 128 hand rulings CANNOT validate the reachability gate -- an
unreachable pair's precedent rate is structurally 0.0 and the sheet he ruled on
starts at 0.50, so the two populations are disjoint. The 99,449 rows the rework
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


def _built(target=None, n_c=5, verdict="REJECT"):
    findings, context = _world(n_c=n_c)
    verdicts = _verdicts(_c_keys(findings, context), verdict)
    drawn, stats = V.build_sample(
        findings, verdicts, context, type_reg=TYPE_REG, assay_pop=ASSAY_POP,
        fallback=FALLBACK,
        target=target or {V.STRATUM_A: 4, V.STRATUM_B: 3, V.STRATUM_C: 2})
    return findings, context, verdicts, drawn, stats


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
    kw = dict(type_reg=TYPE_REG, assay_pop=ASSAY_POP, fallback=FALLBACK,
              target={V.STRATUM_A: 4, V.STRATUM_B: 3, V.STRATUM_C: 2})
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
    assert stat["row_coverage"] == pytest.approx(10000 / 90478)
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
    assert "Per cohort" in report and "Per row" in report
    for stat in stats:
        assert stat["stratum"] in report
        assert stat["question"] in report
    assert str(V.SEED) in report


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
    assert set(key.columns) >= {"cohort_id", "stratum", "cohort_key", "n_rows",
                                "agent_verdict", "agent_reason", "seed",
                                "draw_digest"}
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
    stratum A's 90,478 -- small, and a silent shortfall is not.
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

    Measured 2026-08-24 over `assay-hygiene-bak/extract`: stratum A is 655
    cohorts over 90,478 rows (8 of which carry no precedent rate and reach no
    cohort), B is 137 over 8,971, and C is 106 of the 756 agent REJECT cohorts
    still on a primary surface, over 43,604 rows. The draw takes 100 / 50 / 50
    and covers 10.2% / 23.3% / 69.1% of their rows.
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
    assert by_name[V.STRATUM_A]["population_rows"] == 90478
    assert by_name[V.STRATUM_B]["population_cohorts"] == 137
    assert by_name[V.STRATUM_B]["population_rows"] == 8971
    assert by_name[V.STRATUM_C]["population_cohorts"] == 106
    assert by_name[V.STRATUM_C]["population_rows"] == 43604
    assert len(drawn) == 200
    assert [by_name[n]["sampled_cohorts"] for n in V.STRATA] == [100, 50, 50]
    assert by_name[V.STRATUM_A]["row_coverage"] == pytest.approx(0.102, abs=5e-4)
    assert by_name[V.STRATUM_C]["kish_n_eff"] < 3


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
