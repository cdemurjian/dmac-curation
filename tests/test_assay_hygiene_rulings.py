"""Task 9: the operator's rulings, as a regression suite over the rework.

WHAT THIS FILE IS FOR. The 2026-08-21 rework reclassified 99,309 of the
170,338 proposals in the real-extract run as `CLS_UNREACHABLE` (90,338) or
`CLS_BOOTSTRAP` (8,971) -- re-measured 2026-08-31 by running `run_evidence` then
`run_detect` over `assets/RUN1/01-extract` into a scratch directory; it read
99,449 of 170,786 with 90,478 unreachable until the samples-row refusal of that
date removed 448 proposals outright. That is a large
claim to put in front of a human, and the only ground truth this package owns
about house convention is the 111 Mode 2 cohorts and 17 Mode 1 cohorts he ruled
BY HAND. If the reworked detector drops a cohort he approved, or still proposes
one he rejected, he has to be told, BY NAME, before he is asked to review
anything else.

THE FAILURE IS THE DELIVERABLE, NOT THE PASS.
`test_the_real_extract_drops_every_cohort_the_operator_rejected` IS EXPECTED TO
BE RED on this branch, and it is red with a list of 13 cohort names rather than
a count. That list is the measured BENEFIT of the rework against ground truth,
and the benefit is zero: not one of the 13 proposals he rejected was removed by
the reachability gate. Do not make it green by moving a threshold or a
classification. It goes green when a detector stops emitting them.

WHY THE FIXTURES ARE NOT IN GIT, AND WHY THAT IS NOT AN OVERSIGHT. This
repository is PUBLIC and needed a history rewrite on 2026-08-21 to strip 1,570
sample identifiers out of 66 commits, because a file deleted in a later commit
is still public in its history. `mode2-rulings.tsv` keys cohorts on strings
from that same namespace -- one of them is a protocol filename. So the rulings
live under `assets/RUN1/00-rulings/`, they are copied into `tests/fixtures/`
by hand, `.gitignore` refuses `*rulings*.tsv` at any depth, and
`test_the_restored_rulings_can_never_reach_this_public_repository` asserts that
refusal rather than trusting it. Everything below reads the cohort keys OUT of
those files at runtime; NO RULED COHORT KEY IS WRITTEN INTO THIS SOURCE FILE,
which is why the failure messages name them and the docstrings do not.

A fresh clone therefore SKIPS every test here. That is the intended state: the
suite is green without the fixtures and measures the rework with them.

THE VACUITY THAT WOULD HAVE MADE THIS WHOLE FILE WORTHLESS. Every "no approved
cohort was lost" assertion below is trivially true against a run in which
nothing was reclassified -- revert the rework and they all stay green while
measuring nothing.
`test_the_real_extract_rework_reclassified_rows_the_pre_rework_run_did_not` is
the precondition that makes the rest non-vacuous: it requires the reworked
frame to carry both new classes AND the pre-rework baseline to carry neither.
If someone regenerates `assay-hygiene/findings.csv` with the reworked code, the
before/after comparison in
`test_the_real_extract_moves_no_cohort_on_either_review_surface` would silently
become a frame compared with itself; that test refuses to run rather than pass
in that state.

THE COHORT KEY IS NEVER RECONSTRUCTED HERE. `review_mode2.build_blocks` is
called with `floor=0.0` to key EVERY rated Mode 2 row, and with its own default
floor to key the 111-cohort sheet, so the key a ruling is matched against is
built by the module that built the sheet the operator ruled on. A local
`lab|type|parents|assay|field|value` join would be a second definition of the
key one edit away from disagreeing, which is the defect this package's review
modules already document twice.

EXTRACT-BACKED TESTS ARE NAMED `..._real_extract_...`, the convention
`test_assay_hygiene_review.py` and `test_assay_hygiene_run_detect.py` both
keep: the fast lane selects with `-k 'not real_extract'` against the test NAME,
so a `pytest.mark` would be an unregistered marker no mutation harness honours.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S       # noqa: E402
from assay_hygiene import classify as X      # noqa: E402
from assay_hygiene import review as R        # noqa: E402
from assay_hygiene import review_mode2 as M  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
M1_RULINGS = FIXTURES / "mode1-rulings.tsv"
M2_RULINGS = FIXTURES / "mode2-rulings.tsv"

# The two classes the rework invented. Grouped, because a row moved off the
# primary surface is off it whichever of the two it landed in: `CLS_BOOTSTRAP`
# is a split of the unreachable population, not a separate finding about
# reachability.
RECLASSIFIED = (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP)

# The evidence layer's two outputs that the detection layer READS. They are
# copied into the scratch run rather than re-mined because `run_evidence` over
# this extract reproduces BOTH OF THEM byte-identically -- re-verified
# 2026-08-25 by md5 against `assets/RUN1/04-artifacts/`: vocabulary.csv
# 211f91ff..., claims.parquet e7810d97... -- so re-mining them would cost the
# run without changing a byte of its input. `precedent.csv` NO LONGER matches
# that baseline and the comment claimed it did until 2026-08-25: commit 9090d20
# gave the frame its two `_samples` columns, so it now reads acb7f3b5... against
# the baseline's 37f0add1.... It is not in `EVIDENCE_INPUTS` and is re-mined by
# `classify.main`, so the drift costs this file nothing -- but a reader
# checking the md5s would have found one that does not reconcile. What is NOT copied is `findings.csv`: every classification this
# file judges is produced by `classify.main` inside the fixture below.
EVIDENCE_INPUTS = ("claims.parquet", "vocabulary.csv")

_MISSING_RULINGS = (
    "no {name}. The rulings are CURATION OUTPUT and are kept out of this "
    "repository, which is public and whose fixtures would otherwise carry "
    "identifiers from the namespace a history rewrite already had to strip. "
    "They live beside the other assay-hygiene artifacts under "
    "assets/RUN1/00-rulings/; copy them into tests/fixtures/ to run this.")


def _rulings(path) -> pd.DataFrame:
    """-> the ruling rows, or a skip naming the file that is absent."""
    if not path.exists():
        pytest.skip(_MISSING_RULINGS.format(name=path.name))
    return pd.read_csv(path, sep="\t").fillna("")


def _keys(rulings: pd.DataFrame) -> dict[str, str]:
    """-> {cohort key: ruling} for a Mode 2 ruling file.

    Mode 1's file already carries the joined key; Mode 2's carries the six
    fields as columns. Both are joined with `review.KEY_DELIMITER` on
    `review.BLOCK_KEY`, which is the one definition of the order.
    """
    return {R.KEY_DELIMITER.join(str(row[c]) for c in R.BLOCK_KEY): row.ruling
            for _, row in rulings.iterrows()}


@pytest.fixture(scope="session")
def context():
    if not (EXTRACT / "samples.parquet").exists():
        pytest.skip("no extract; nothing to run the detector over")
    return R.load_context(EXTRACT)


@pytest.fixture(scope="session")
def reworked(tmp_path_factory) -> pd.DataFrame:
    """The REWORKED detector, run over the real extract into a scratch dir.

    NOT a csv read off disk. `assay-hygiene/findings.csv` is the PRE-rework
    artifact the operator's sheet was built from, and `assets/RUN1/` is
    read-only on purpose so that a default-path run fails rather than
    overwriting the baseline this file compares against. So the run happens
    here, in `tmp_path_factory`, and the frame under test is the one this
    process just produced -- about 20 seconds over 163,393 samples.
    """
    if not (EXTRACT / "samples.parquet").exists():
        pytest.skip("no extract; nothing to run the detector over")
    missing = [f for f in EVIDENCE_INPUTS if not (ARTIFACTS / f).exists()]
    if missing:
        pytest.skip(f"no {missing}; run run_evidence.py first")

    out = tmp_path_factory.mktemp("reworked")
    for f in EVIDENCE_INPUTS:
        shutil.copy(ARTIFACTS / f, out / f)
        (out / f).chmod(0o644)      # the baseline copies are read-only
    # `classify.main` has ONE `return` and it is the literal 0, so comparing
    # its result to 0 asserts nothing; it stood here until 2026-08-25. What is
    # worth asserting is that the run produced the artifact this fixture is
    # about, which a raise inside `main` or a silent early exit would not.
    X.main(str(EXTRACT), str(out))
    findings = out / "findings.csv"
    assert findings.exists(), (
        "classify.main returned without writing findings.csv; there is nothing "
        "for this file to judge")
    return pd.read_csv(findings, low_memory=False)


@pytest.fixture(scope="session")
def baseline() -> pd.DataFrame:
    """The PRE-rework findings the operator's two review sheets came from."""
    if not (ARTIFACTS / "findings.csv").exists():
        pytest.skip("no baseline findings.csv; nothing to compare against")
    return pd.read_csv(ARTIFACTS / "findings.csv", low_memory=False)


def _sheet_keys(findings, context) -> set[str]:
    """The Mode 2 cohorts the review sheet shows, at the operator's floor."""
    return {R.cohort_key(b) for b in M.build_blocks(findings, context)}


def _all_mode2_keys(findings, context) -> set[str]:
    """Every Mode 2 cohort with a measured precedent rate, floor removed."""
    return {R.cohort_key(b)
            for b in M.build_blocks(findings, context, floor=0.0)}


def _mode1_keys(findings, context) -> set[str]:
    return {R.cohort_key(b) for b in R.build_blocks(findings, context)}


def _cohort_keys_per_row(findings, context) -> pd.Series:
    """One cohort key per Mode 2 sheet row, off `label_mode2` and nothing else.

    THE KEY IS NEVER RECONSTRUCTED HERE, which is this file's standing rule:
    `review_mode2.label_mode2` derives the six columns and `review.cohort_key`
    joins them, so a row's cohort and a block's cohort come from one definition.
    """
    labelled = M.label_mode2(findings, context)
    return labelled[list(R.BLOCK_KEY)].astype(str).agg(
        R.KEY_DELIMITER.join, axis=1)


@pytest.fixture(scope="session")
def cohorts_wholly_on_absent_samples(baseline, context) -> set[str]:
    """Sheet cohorts EVERY row of which is about a sample MySQL does not have.

    WHY THIS EXEMPTION EXISTS AND WHY IT IS DERIVED RATHER THAN LISTED. On
    2026-08-31 `mode2.mode2_candidates` began refusing every proposal whose
    SUBJECT has no row in the `samples` extract -- 448 rows over 185 samples,
    which the detect census reports as `rows_refused_without_a_samples_row`.
    Those samples exist as graph nodes and in `membership` and MySQL has no
    record of them, so there is nothing to register, no project to write into
    and no metadata the operator could have been ruling on.

    ONE COHORT ON THE SHEET IS MADE ENTIRELY OF SUCH ROWS, 35 of 35, AND THE
    OPERATOR RULED IT APPROVE. That approval cannot be honoured by any code:
    `resolve_targets` already excluded all 35 at the far end of the pipeline
    under "sample belongs to no project", which is how a proposal about a
    non-existent sample looks once it reaches a project gate. So the cohort is
    now refused at the front instead, visibly and by name, and the two tests
    below EXPECT to lose it.

    DERIVED FROM THE BASELINE FRAME, NEVER NAMED. No ruled cohort key may be
    written into this public source file -- see the module docstring -- and a
    hard-coded key would in any case exempt one string rather than one
    condition. This computes the condition, so a cohort that disappears for any
    OTHER reason still fails the tests below, and this exemption empties itself
    the day the upstream data is fixed.

    Read off `baseline`, the PRE-refusal artifact, because the reworked frame no
    longer carries these rows at all: the population has to be counted where it
    still exists.
    """
    known = {int(s) for s in
             pd.read_parquet(EXTRACT / "samples.parquet").sample_id}
    labelled = M.label_mode2(baseline, context)
    keys = _cohort_keys_per_row(baseline, context)
    absent = ~labelled.sample_id.map(lambda s: int(s) in known)
    per_key = keys.groupby(keys).size()
    absent_per_key = keys[absent.values].groupby(keys[absent.values]).size()
    return {k for k, n in absent_per_key.items() if n == per_key[k]}


# --- the fixtures must never become part of this repository ------------------


def test_the_restored_rulings_can_never_reach_this_public_repository():
    """`.gitignore` refuses both ruling files, asserted and not assumed.

    THE COST OF GETTING THIS WRONG IS NOT A FAILED TEST. A ruling file added by
    a `git add -A` is public the moment it is pushed and stays public in the
    history after it is deleted -- which is precisely what happened here on
    2026-08-21 and cost a rewrite of 66 commits. So the guard is `git
    check-ignore`, which answers the question git will actually be asked,
    rather than a substring search of `.gitignore` that would pass on a rule
    written under the wrong path.

    It runs whether or not the fixtures are present: `--no-index` asks the rule
    about a PATH, so an absent file is still answered, and the rule is what
    must survive. The third path is checked for the same reason and has never
    existed under that name -- a copy of the whole ruling file was found
    untracked and unignored in the repository ROOT on 2026-08-24, so a rule
    scoped to `tests/fixtures/` is not enough and this asserts it is not what
    is there.
    """
    for path in (M1_RULINGS, M2_RULINGS, REPO / "mode2-rulings-anywhere.tsv"):
        rel = path.relative_to(REPO)
        r = subprocess.run(["git", "check-ignore", "--no-index", "-v",
                            str(rel)], cwd=REPO, capture_output=True,
                           text=True)
        assert r.returncode == 0, (
            f"{rel} is NOT gitignored. It is a human's ruling file carrying "
            "identifiers from the namespace this PUBLIC repository already "
            "had to rewrite its history to remove. Add a rule before running "
            "anything that stages files.")


# --- the precondition that makes every measurement below non-vacuous ---------


def test_the_real_extract_rework_reclassified_rows_the_pre_rework_run_did_not(
        reworked, baseline):
    """Without this, every "nothing was lost" test here is green on nothing.

    The rework's whole effect is the two new classes. A tree in which the
    reachability gate is reverted, or in which the baseline has been
    REGENERATED with the reworked code, produces two frames that agree
    everywhere -- and then the four tests below assert that a change which did
    not happen cost nothing, which is true and worthless.

    So both halves are required: the reworked frame must carry both new
    classes, and the baseline must carry neither.
    """
    new = set(reworked.classification.dropna().unique())
    old = set(baseline.classification.dropna().unique())
    assert set(RECLASSIFIED) <= new, (
        f"the reworked run emitted {sorted(new)} and none of "
        f"{[c for c in RECLASSIFIED if c not in new]}. The reachability gate "
        "is not in this tree, and every test below measures nothing.")
    assert not (set(RECLASSIFIED) & old), (
        f"the baseline at {ARTIFACTS / 'findings.csv'} already carries "
        f"{sorted(set(RECLASSIFIED) & old)}, so it is NOT the pre-rework "
        "artifact the operator's sheets were built from -- someone "
        "regenerated it. The before/after comparison would be a frame "
        "compared with itself. Restore the pre-rework findings.csv.")


# --- what the rework COSTS: the cohorts he approved --------------------------


def test_the_real_extract_keeps_every_mode2_cohort_the_operator_approved(
        reworked, context, cohorts_wholly_on_absent_samples):
    """No approval may vanish from the Mode 2 sheet -- with ONE stated exception.

    These are the write candidates. A cohort he approved that the reworked
    detector no longer emits is a decision silently discarded, and the operator
    would have no way to notice: the sheet regenerates, the cohort is simply
    not on it, and the ruling file still says APPROVE.

    THE EXCEPTION IS A COHORT THAT COULD NEVER HAVE BEEN WRITTEN, and it is
    subtracted by CONDITION and not by name -- see
    `cohorts_wholly_on_absent_samples`. Since 2026-08-31 a proposal about a
    sample with no `samples` row is refused before any mode runs, and one sheet
    cohort of 35 rows is made entirely of those. All 35 were already excluded at
    the other end of the pipeline by `resolve_targets`' project gate, under the
    milder and misleading reason "sample belongs to no project", so the
    operator's APPROVE has never had a writable row behind it. The refusal moves
    that fact from the end of the run to the front, where the census names it.

    THE EXEMPTION IS ASSERTED NON-EMPTY AND EXACT, in both directions. If it
    were empty this test would silently go back to asserting what it asserted
    before; if it covered more than the cohorts actually lost it would be
    licensing losses that have not happened.
    """
    ruled = _keys(_rulings(M2_RULINGS))
    approved = [k for k, r in ruled.items() if r == "APPROVE"]
    emitted = _sheet_keys(reworked, context)
    expected_gone = cohorts_wholly_on_absent_samples
    assert expected_gone, (
        "no sheet cohort rests wholly on samples absent from the `samples` "
        "frame, so the exemption below excuses nothing and this test would "
        "pass without measuring the condition it names")
    lost = sorted(k for k in approved if k not in emitted)
    assert set(lost) <= expected_gone, (
        f"the rework dropped {len(lost)} of {len(approved)} Mode 2 cohorts "
        f"the operator APPROVED, and {len(set(lost) - expected_gone)} of them "
        f"is NOT explained by the samples-row refusal. Each one is a ruling "
        f"that no longer has a proposal behind it:\n  "
        + "\n  ".join(sorted(set(lost) - expected_gone)))
    # ...and the exemption is spent rather than merely available: every cohort
    # it excuses really is gone, so it cannot quietly grow to cover a future
    # loss it was not measured against.
    assert set(lost) == expected_gone & set(approved)


def test_the_real_extract_puts_no_approved_cohort_behind_the_gate(
        reworked, context):
    """The stronger half: not merely emitted, but still on the PRIMARY surface.

    A cohort can survive the sheet's 0.50 precedent floor while some of the
    rows under its key are reclassified as unreachable -- the sheet would still
    show it, smaller, and nothing would say so. THE FLOOR IS REMOVED HERE for
    exactly that reason: the question is whether the reachability gate touched
    ANY row of a pattern he ruled legitimate, not whether the top of that
    pattern survived.

    Re-measured 2026-08-31: 0 of the 100 approved cohorts hold a reclassified
    row, and the reclassified population is disjoint from the ruled one -- 792
    of the 1,113 rated Mode 2 cohorts hold such a row and none of them is on the
    110-cohort sheet. (1,114 and 111 before the samples-row refusal took one
    cohort off the sheet; the 792 did not move, the refused rows being
    reachable-lane and unreachable-lane alike but never on the sheet.)
    """
    ruled = _keys(_rulings(M2_RULINGS))
    approved = {k for k, r in ruled.items() if r == "APPROVE"}
    gated = _all_mode2_keys(
        reworked[reworked.classification.isin(RECLASSIFIED)], context)
    hit = sorted(approved & gated)
    assert not hit, (
        f"{len(hit)} of {len(approved)} Mode 2 cohorts the operator APPROVED "
        f"hold at least one row the reachability gate reclassified as "
        f"{' or '.join(RECLASSIFIED)}. He ruled the pattern legitimate; the "
        f"gate says the house has never made it:\n  " + "\n  ".join(hit))


def test_the_real_extract_keeps_every_mode1_cohort_the_operator_approved(
        reworked, context):
    """The same floor, over the other surface he ruled.

    Mode 1 has no precedent floor and no classification -- its rows are samples
    registered in nothing -- so the only way to lose one of his approvals here
    is to stop emitting the proposal. A vocabulary retirement is the one
    legitimate way to lose a Mode 1 KEY and it may never take an APPROVE, which
    `test_assay_hygiene_review.py` already asserts against the PRE-rework
    artifact; this is the same claim re-measured against the run this branch
    now produces.
    """
    rulings = _rulings(M1_RULINGS)
    approved = [k for k, r in zip(rulings.key, rulings.ruling)
                if r == "APPROVE"]
    emitted = _mode1_keys(reworked, context)
    lost = sorted(k for k in approved if k not in emitted)
    assert not lost, (
        f"the rework dropped {len(lost)} of {len(approved)} Mode 1 cohorts "
        f"the operator APPROVED:\n  " + "\n  ".join(lost))


# --- what the rework BUYS: the cohorts he rejected ---------------------------


@pytest.mark.xfail(strict=True, reason=(
    "EXPECTED RED and it is a DELIVERABLE, not a defect: the rework removed "
    "none of the 13 rejected cohorts still on a primary surface, and the "
    "failure message names them. strict=True is the guard the docstring asks "
    "for -- if this ever passes, pytest reports an UNEXPECTED PASS and the "
    "suite goes red, so nobody can retire the measurement by moving a "
    "threshold. A real fix (a detector stops emitting them) must delete this "
    "marker deliberately. NOTE: on a checkout with no fixtures the test SKIPS "
    "and this marker never applies -- see pytest_terminal_summary in "
    "tests/conftest.py, which refuses to let that read as a green measurement."
))
def test_the_real_extract_drops_every_cohort_the_operator_rejected(
        reworked, context):
    """EXPECTED RED. The list in the failure message is this task's deliverable.

    He looked at 128 cohorts and said no to 20 of them: 11 on the Mode 2 sheet
    (6 REJECT, 5 WRONG_ASSAY) and 9 on the Mode 1 sheet (all WRONG_ASSAY).
    Those 20 are the only false positives this package has ever had confirmed
    by a human, so they are the only measurement of what the rework BUYS.

    A rejected cohort has left the primary surface if it is no longer emitted
    at all, or if what remains of it is `CLS_UNREACHABLE`, `CLS_BOOTSTRAP` or
    `CLS_ALT_LABEL`. NOTHING ROUTES ON CLASSIFICATION and this docstring said
    otherwise until 2026-08-25: `review_mode2.build_blocks` filters on
    `mode == MODE_2` and `precedent_rate >= floor` and reads no `classification`
    column at all. The three are off the sheet for two DIFFERENT structural
    reasons, and both are properties of the data rather than a routing rule --
    `CLS_ALT_LABEL` rows carry no mode, so the first predicate drops them; and
    an unreachable or bootstrap pair has a structurally zero precedent rate, so
    the second does. `test_no_reclassified_row_could_have_reached_the_sheet`
    below asserts the second half directly. A reader who believed the routing
    story would expect a classification change alone to move a cohort off the
    sheet, and it cannot.
    Seven of the nine Mode 1 rejections already qualify, discharged by the
    `tif`/`png` vocabulary retirements the operator's own rulings caused; that
    is a vocabulary fix working and it is counted as a pass here.

    MEASURED 2026-08-24: 13 of the 20 are still on the primary surface -- all
    11 Mode 2 rejections, unchanged and classified `CLS_ABSENCE_LINEAGE`, plus
    the 2 Mode 1 rejections no retirement reached. THE REACHABILITY GATE
    REMOVED NONE OF THEM. That is not a bug in this test; it is the finding.
    Against the only ground truth in the package the rework is exactly neutral:
    it costs nothing he approved and it buys nothing he rejected.
    """
    m2_ruled = _keys(_rulings(M2_RULINGS))
    m1_rulings = _rulings(M1_RULINGS)

    still = []
    surface = _sheet_keys(reworked, context)
    for key, ruling in sorted(m2_ruled.items()):
        if ruling != "APPROVE" and key in surface:
            still.append(f"MODE_2 {ruling:<12} {key}")

    m1_surface = _mode1_keys(reworked, context)
    for key, ruling in sorted(zip(m1_rulings.key, m1_rulings.ruling)):
        if ruling != "APPROVE" and key in m1_surface:
            still.append(f"MODE_1 {ruling:<12} {key}")

    rejected = (sum(1 for r in m2_ruled.values() if r != "APPROVE")
                + int((m1_rulings.ruling != "APPROVE").sum()))
    assert not still, (
        f"{len(still)} of {rejected} cohorts the operator REJECTED are still "
        f"on a primary review surface. Every one of them will be put in front "
        f"of him again, carrying a proposal he has already refused:\n  "
        + "\n  ".join(still))


# --- the rework's footprint on the two surfaces ------------------------------


def test_the_real_extract_moves_no_cohort_on_either_review_surface(
        reworked, baseline, context, cohorts_wholly_on_absent_samples):
    """Before and after, cohort for cohort. The rework's whole visible cost.

    A count cannot answer this: the sheet could lose four cohorts and gain four
    others and stay at 111. So the two key SETS are compared, both directions,
    and any difference is named.

    Measured 2026-08-24: Mode 1 holds 37 cohorts and Mode 2's sheet 111 over
    9,500 rows, identical before and after. The 99,449 rows the gate
    reclassified are disjoint from both surfaces.

    RE-MEASURED 2026-08-31: Mode 1 is still identical, and the Mode 2 sheet
    holds 110 cohorts over 9,463 rows -- 37 fewer rows than the 9,500 of
    2026-08-24, being one 35-row cohort lost whole and 2 rows off a cohort that
    survives. The one cohort it lost is made entirely
    of proposals about samples with no `samples` row, which
    `mode2.mode2_candidates` now refuses; it is subtracted by CONDITION and not
    by name -- see `cohorts_wholly_on_absent_samples`. NOTHING WAS GAINED on
    either surface, in either reading, and that half of the assertion is
    untouched: a refusal may only remove.
    """
    for mode, before, after, excused in (
            ("MODE_1", _mode1_keys(baseline, context),
             _mode1_keys(reworked, context), set()),
            ("MODE_2 sheet", _sheet_keys(baseline, context),
             _sheet_keys(reworked, context),
             cohorts_wholly_on_absent_samples)):
        assert not (after - before), (
            f"the {mode} surface GAINED {len(after - before)} cohort(s), which "
            f"no refusal can do:\n  GAINED: "
            + "\n  GAINED: ".join(sorted(after - before)))
        assert (before - after) <= excused, (
            f"the {mode} surface moved: "
            f"{len((before - after) - excused)} cohort(s) lost for a reason "
            f"other than the samples-row refusal.\n  LOST: "
            + "\n  LOST: ".join(sorted((before - after) - excused)))
    # THE EXEMPTION IS SPENT, not merely held: the Mode 2 sheet really did lose
    # every cohort it excuses, so it cannot silently cover a later loss.
    assert (_sheet_keys(baseline, context) - _sheet_keys(reworked, context)) \
        == cohorts_wholly_on_absent_samples


def test_the_real_extract_reclassifies_no_row_that_could_reach_the_sheet(
        reworked):
    """WHY the rulings cannot validate the reachability gate, made structural.

    An unreachable pair has zero type registrations, so its precedent rate
    cannot exceed zero; the sheet the operator ruled on starts at 0.50. The two
    populations therefore cannot intersect, and that is the reason the four
    tests above are green -- NOT evidence that the gate agrees with him. This
    test states the disjointness so a reader of the report cannot mistake one
    for the other, and so a future change that lets a reclassified row carry a
    real precedent rate goes red here rather than silently invalidating the
    argument.

    Measured 2026-08-24: 99,449 reclassified rows, max precedent rate 0.0, none
    at or above the 0.50 floor; and all 9,500 rows on the sheet are
    `CLS_ABSENCE_LINEAGE`.
    """
    gated = reworked[reworked.classification.isin(RECLASSIFIED)]
    assert len(gated), "nothing was reclassified; this asserts nothing"
    top = gated.precedent_rate.max()
    assert top == 0.0, (
        f"a reclassified row carries precedent rate {top}, above the 0.0 an "
        "unreachable pair can structurally have. The claim that the gate "
        "cannot have touched the operator's sheet no longer holds.")
    # `top == 0.0` above already forbids any row at or above M.FLOOR (0.50),
    # so the `reached` assertion that stood here until 2026-08-25 could not
    # fail. Struck: the max IS the check, and a second line that cannot go red
    # reads as a second check.

    sheet = reworked[(reworked["mode"] == S.MODE_2)
                     & (reworked.precedent_rate >= M.FLOOR)]
    off = sheet[sheet.classification != S.CLS_ABSENCE_LINEAGE]
    assert not len(off), (
        f"{len(off)} of {len(sheet)} rows above the floor are not "
        f"{S.CLS_ABSENCE_LINEAGE}: "
        f"{off.classification.value_counts().to_dict()}")
