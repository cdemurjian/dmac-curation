# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Mode 2's backtest. Hide a slice of the curators' work and see if it comes back.

WHAT THIS MEASURES, IN ONE SENTENCE. Hide every membership row of a held-out
slice of SAMPLES, mine precedent on the subgraph induced by the samples that were
kept, run Mode 2 cold, and ask of every proposal it makes about a held-out
sample: did a curator actually put that sample in that assay. RECOVERY, not rate.

NOTHING DECIDES AND NOTHING IS WRITTEN. This module reads five parquet files and
produces two frames and a dict. Under the binding constraint every proposed
change reaches the operator for approval, so a band on this curve sets READING
ORDER and grants no permission; there is no cutoff chosen anywhere in this file
and `backtest` filters not one proposal by a rate.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \\
        python -m assay_hygiene.backtest

THE SPLIT IS BY SAMPLE AND NEVER BY EDGE. A sample fans out to many edges -- one
(sample, assay) pair of the real extract is supported by 1,526 lineage
neighbours, and the largest single child set is 1,528 -- so an edge-level split
puts the same sample in both halves and scores answers the run was trained on.
The spec records this as a mistake already made once on this project.
`check_split` refuses a sample appearing in both halves, and refuses one
appearing in neither, because an unassigned sample is silently treated as kept
and its registrations then train the run that is meant to be blind to them.

THE TRAINING SET IS THE INDUCED SUBGRAPH ON THE KEPT SAMPLES, AND THE OBVIOUS
ALTERNATIVE IS BIASED. Mining over EVERY edge with a blinded membership frame
looks equivalent and is not: an edge whose endpoint was blinded moves out of
`n_both` and into a one-sided counter, which multiplies every mined rate by
about `(1 - fraction)`. Measured at a 20% hold-out on seed 0 over the real
extract, with the biased mining as the ONLY difference, that version all but
empties the `[0.95,1.00]` band -- 1 ADD_PARENT row and 6 ADD_CHILD rows, against
4,151 and 19,337 once the training edges are restricted to kept-kept -- and the
mass lands one band down in `[0.75,0.90)` instead, at 5,424 and 19,165. Both
readings came out of this module during development and the first one is wrong.

THE COLD RUN CARRIES NO METADATA CLAIM AT ALL, and that is a scope statement
rather than an oversight. The vocabulary was learned over the FULL labelled edge
set, held-out samples included, so no split this module can make blinds it;
scoring a claim-corroborated proposal would be scoring a model that had seen the
answer. So `backtest` hands `mode2_findings` an EMPTY claims frame and measures
precedent and lineage alone, and it CHECKS that nothing else got in:
`proposed_by` must be `BY_PRECEDENT` or `BY_LINEAGE_ONLY` on every row.

WHAT THIS CANNOT MEASURE, STATED PLAINLY. The scored population is enriched with
the registrations the split hid -- pairs the live run would never propose,
because the sample already holds them. So a precision here is the precision of a
proposal about a sample whose registrations were hidden. It is NOT the precision
of the live dark rows, which have no ground truth by construction; the spec says
so under "What cannot be validated, stated plainly". And a proposal counted wrong
here may be a genuine missing registration the pipeline correctly found, since a
curator's assay set is not known to be complete -- that is the premise of Modes 1
and 2. Every precision this module reports is therefore a LOWER BOUND.

MEASURED 2026-08-18 OVER THE 2026-08-14 EXTRACT, at a 20% hold-out on seed 0.
32,793 of 163,816 samples held out, 42,867 of 214,296 membership rows hidden,
509,875 of 794,593 edges in the training set, 36,090 curator-assigned pairs to
recover, 59,182 proposals scored:

    band          ADD_PARENT                     ADD_CHILD
                  rows   correct  precision      rows   correct  precision
    NO_RATE          11        4     0.364          28        7     0.250
    [0.00,0.50)   8,806      519     0.059      18,996      210     0.011
    [0.50,0.75)   2,869    1,757     0.612         318      172     0.541
    [0.75,0.90)   1,814    1,529     0.843         949      815     0.859
    [0.90,0.95)   1,626    1,548     0.952         277      263     0.949
    [0.95,1.00]   4,151    4,143     0.998      19,337   19,270     0.997

STABLE ACROSS THE SPLIT, so the curve is not an artifact of one hold-out. Re-run
at seed 7 and at fractions 0.1 and 0.5, the `[0.95,1.00]` precision reads
0.997 / 0.997, 0.999 / 0.997 and 0.998 / 0.996 (ADD_PARENT / ADD_CHILD).

AND THE RATE IS WELL CALIBRATED OUT OF SAMPLE, IN BOTH DIRECTIONS, which is the
strongest form of the finding: every band's measured precision falls inside the
band's own interval, the one recurring exception being `[0.90,0.95)` ADD_PARENT
at 0.952 / 0.965 / 0.960 across the three configurations, up to 1.5 points above
the band's top edge. A `reverse_rate` of 0.97 means what a `propagation_rate` of
0.97 means.

THE CURVE CUTS AGAINST THE SPEC'S DEMOTION OF `A_ADD_CHILD`, AND ONLY IN ITS TOP
BAND. At equal precedent rate the two directions recover a curator's assay at
indistinguishable precision -- 0.998 against 0.997 at `[0.95,1.00]` over 4,151
and 19,337 proposals, and the demoted direction's top band is NOT one hop doing
the work: drop its largest evidence group and the remaining 13,649 rows still
recover at 0.996. So `reverse_rate` at a given value is as good a guide to
reading order as `propagation_rate` at that value.

THAT CLAIM IS NARROW ON PURPOSE, AND `118 EVIDENCE GROUPS` MUST NOT BE READ AS
THE DISCOUNT. The top band's 118 groups are heavily unequal: the largest keys
5,688 rows, 29.4%, the top two 10,163, 52.6%, and the top three 11,720, 60.6%.
Worse for any independence reading, the largest group is the SAME triple
`(22615, 0, 34)` that tops the ADD_PARENT band, where it keys 617 of 4,151 -- so
the two directions' top bands are not independent evidence of each other. What
survives is only what was measured: the band is not ONE hop.

THE TOP BAND IS NOT THIN, WHICH IS A DIFFERENT QUESTION AND WAS ASKED
SEPARATELY. Row-weighted, the demoted direction's `[0.95,1.00]` rows sit on a
median direction denominator of 17,720 with 117 of 19,337 below 30; the mirror's
sit on 1,341 with 130 of 4,151 below 30. Neither band rests on thin evidence,
and the demoted one rests on the thicker.

What the demotion does survive on is the direction's BULK. In `[0.00,0.50)` the
demoted direction recovers 210 of 18,996 against 519 of 8,806, five times worse,
and that is where almost all of its 117,331 live rows sit. It also survives on
the two measurements the spec actually rests it on, neither of which this
instrument touches: co-registration corroboration over increment 1's 866 flags,
88 of 88 against 15 of 263, and the flagship hop `TIS <- PAV`, 0.006 reverse
under assay 56 against 0.931 propagation under 74.

ONE BAND CLEARS THE SPEC'S 95% BAR AND IT CLEARS IT IN BOTH DIRECTIONS. Nothing
below `0.90` clears it in either. That is the finding, and the honest form of it
is that a threshold was not chosen here: `[0.95,1.00]` is where an operator
should start reading, not a permission anyone has been granted.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from . import _schema as S
from . import classify as X
from . import mode2 as M2
from . import gate as G
from . import lineage as L
from . import precedent as B
from .audit import registered_internal

# --- the bands ----------------------------------------------------------------
#
# WHERE THE CURVE REPORTS, AND NOTHING ELSE. These are not gates: every proposal
# the cold run makes is scored and banded, `backtest` compares no proposal
# against any of them, and a test asserts the band table's row count equals the
# scored population exactly.
#
# DISJOINT AND EXHAUSTIVE, where `mode2.SURVIVAL_THRESHOLDS` is cumulative,
# and the difference is the whole point of this table. A cumulative `>= 0.5`
# bucket mixes a rule at 0.50 with one at 1.00, and precision is precisely the
# thing that differs between them -- 0.059 and 0.998 in the ADD_PARENT
# direction. Because the bands partition the scored rows, an operator wanting
# the cumulative reading sums a suffix, so nothing is lost by reporting the
# finer grain.
#
# THE EDGES ARE `SURVIVAL_THRESHOLDS`' OWN VALUES so the two tables can be read
# against each other. They are taken from that constant rather than re-typed:
# two spellings of one list, one module apart, is this branch's signature defect.
BAND_EDGES = tuple(sorted(M2.SURVIVAL_THRESHOLDS)) + (1.0,)

# A ROW WITH NO MEASURED RATE IS ITS OWN BAND AND IS NEVER FILED UNDER 0.0.
# 0.000 is a real rate meaning "observed on this hop, and never once
# co-registered"; a null means nobody measured. `mode2.precedent_survival`
# keeps 0.0 in its threshold list for the same reason -- it is where absent
# evidence visibly fails to count as a rate of zero.
BAND_NO_RATE = "NO_RATE"

# Built from `BAND_EDGES` rather than written beside it, so an edge added to the
# curve cannot leave a label behind. The last band is CLOSED at 1.0, because a
# rate of exactly 1.0 is the commonest value in the top band and a half-open
# spelling would drop it out of the table with no error.
BAND_LABELS = (BAND_NO_RATE,) + tuple(
    f"[{lo:.2f},{hi:.2f}{')' if hi < 1.0 else ']'}"
    for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:]))

# THE SUPPORT RIDES BESIDE THE RATE, for the reason `co_reg_pop` rides beside
# `co_reg_rate` and `of_rows` beside a survival count: a precision quoted without
# its denominator is unreadable, and an EMPTY band quoted as 0.000 says a
# measurement was made and failed where none was made at all.
#
# `rule_groups`, `largest_group_rows` and `largest_group_correct` are here
# because a ROW COUNT COUNTS AFFECTED SAMPLES AND NOT INDEPENDENT EVIDENCE. The
# question the demoted direction's top band raises is whether one hop is doing
# all the work, and these three columns are what answers it on the table rather
# than in whoever holds the parquet.
RECOVERY_COLUMNS = ["band", "action", "rows", "correct", "precision", "samples",
                    "rule_groups", "largest_group_rows", "largest_group_correct"]

# Every key `backtest` returns in its census, in report order, declared for the
# reason `INTEGRITY_KEYS`, `MODE1_CENSUS_KEYS` and `MODE2_CENSUS_KEYS` are: the
# report prints them all, and a key that stops being produced must break rather
# than stop being printed.
#
# NOTHING IS DROPPED SILENTLY, and four identities hold over these, all asserted:
#
#     membership_rows       = membership_rows_hidden + membership_rows_kept
#     samples_in_the_universe = samples_held_out + samples_kept
#     held_out_registrations  = truth_pairs
#                             + held_out_registrations_with_no_neighbour
#     truth_pairs           = truth_pairs_add_parent + truth_pairs_add_child
#     proposals             = proposals_scored + proposals_on_a_kept_sample
#
# and per direction, which is where the split-by-sample cost is paid visibly:
#
#     truth_pairs_X = recovered_X + recovered_in_the_other_direction_X
#                                 + not_recovered_X
#
# `recovered_in_the_other_direction_*` exists because blinding can FLIP a
# direction. A pair whose curator-world support is a child, where that child is
# held out too and a kept parent also holds the assay, is proposed as the mirror
# action. Counting it as a miss would understate recovery and counting it as a
# plain recovery would overstate the direction it was filed under.
#
# THE TWO SETS OF PER-DIRECTION KEYS READ THE DIRECTION OFF DIFFERENT WORLDS AND
# ARE NOT EXPECTED TO AGREE. `recovered_*` and `not_recovered_*` are keyed on the
# direction the CURATOR's own world supports, because that is what makes their
# denominators a population one can miss; `proposals_scored_correct_*` is keyed
# on the action the BLINDED run actually emitted, because that is the row an
# operator reads. Measured on the real extract they differ by exactly the flipped
# pairs -- 20,737 correct ADD_CHILD proposals against 20,683 recovered ADD_CHILD
# truth pairs, the 54 being ADD_PARENT pairs recovered as the mirror -- and a
# final identity asserts that the two totals reconcile through them.
BACKTEST_CENSUS_KEYS = (
    "samples_in_the_universe",
    "samples_held_out",
    "samples_kept",
    "membership_rows",
    "membership_rows_hidden",
    "membership_rows_kept",
    "edge_rows",
    "edge_rows_training",
    "held_out_registrations",
    "held_out_registrations_with_no_neighbour",
    "truth_pairs",
    "truth_pairs_add_parent",
    "truth_pairs_add_child",
    "recovered_add_parent",
    "recovered_add_child",
    "recovered_in_the_other_direction_add_parent",
    "recovered_in_the_other_direction_add_child",
    "not_recovered_add_parent",
    "not_recovered_add_child",
    "proposals",
    "proposals_scored",
    "proposals_on_a_kept_sample",
    "proposals_scored_correct_add_parent",
    "proposals_scored_correct_add_child",
)

# Which census suffix names which action. One lookup, so a key and the action it
# counts cannot drift apart, exactly as `ACTION_PRECEDENT_DIRECTION` keeps a rate
# and the column naming it together.
ACTION_SUFFIX = {S.A_ADD_PARENT: "add_parent", S.A_ADD_CHILD: "add_child"}


class Split(NamedTuple):
    """The two halves, as SAMPLE ids. Both sides are carried, and that is the guard.

    A split that returned only the held-out half would make "which samples were
    kept" a derivation every caller repeats, and the derivation is exactly where
    an edge-level split hides: a sample can appear in both halves only if the two
    are computed separately, so both are computed once and `check_split` compares
    them against the universe they came from.
    """
    held_out: frozenset[int]
    kept: frozenset[int]


class Backtest(NamedTuple):
    """What one cold run measured. Nothing here authorises anything.

    `findings` is the WHOLE cold-run proposal set, including the proposals about
    kept samples that are unscorable by construction, so a reader can check the
    census's partition rather than take it. `truth` is the curator's own answer
    key: `(sample_id, internal_assay_id) -> the action the FULL world supports`.
    """
    bands: pd.DataFrame
    census: dict[str, int]
    findings: pd.DataFrame
    truth: dict[tuple[int, int], str]


# --- the split ----------------------------------------------------------------


def sample_universe(
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    edges: pd.DataFrame,
) -> frozenset[int]:
    """Every sample id any of the three frames names, sorted into one set.

    THE UNION AND NOT `samples.sample_id`, because three populations live outside
    that frame and every one of them can carry or settle a registration. 362
    sample ids appear in `membership` with no `samples` row, 243 edge endpoints
    have none either, and 182 of those are registered. A universe taken from the
    samples frame alone would leave all of them unassigned, and an unassigned
    sample is silently kept -- so a held-out sample's registered neighbour would
    keep its registration while the split believed it had blinded the pair.
    """
    return frozenset(
        {int(s) for s in samples.sample_id}
        | {int(s) for s in membership.sample_id}
        | {int(s) for s in edges.child_id}
        | {int(s) for s in edges.parent_id})


def split_by_sample(universe, *, fraction: float, seed: int) -> Split:
    """A stable, order-independent split of SAMPLE ids into (held_out, kept).

    BY A DIGEST OF THE ID AND NEVER BY `PYTHONHASHSEED` IS SALTED PER PROCESS, so
    a split built on the interpreter's own string digest changes between two runs
    over identical data and no figure this module reports could be reproduced.
    `blake2b` is stable across processes, platforms and releases.

    ORDER-INDEPENDENT, and that matters here rather than being tidy: the
    extractor's row order is not stable across extracts -- `precedent.py` records
    the same hazard for its own sort -- so a split built by shuffling a list read
    off a frame would assign different samples on two runs over the same data.
    Each id is bucketed on its own, so the input may arrive in any order at all.

    `fraction` is the SHARE OF SAMPLES held out, not of rows and not of edges,
    because the split's whole contract is that it is by sample. The realised
    share differs from the requested one by the granularity of the bucket, which
    is one part in a million.

    NOT A DEFAULT ANYWHERE. Both parameters are keyword-only and required: a
    hold-out size silently inherited from a default is a choice nobody recorded,
    and every figure in this module's docstring carries the fraction and the seed
    that produced it.
    """
    if not 0.0 < fraction < 1.0:
        raise ValueError(
            f"fraction is {fraction!r} and must lie strictly between 0 and 1: "
            "holding out nothing measures nothing, and holding out everything "
            "leaves no kept neighbour to support a single proposal.")
    cut = fraction * 1_000_000
    ids = {int(s) for s in universe}
    held = frozenset(
        s for s in ids
        if int.from_bytes(hashlib.blake2b(f"{seed}:{s}".encode(),
                                          digest_size=8).digest(),
                          "big") % 1_000_000 < cut)
    return Split(held, frozenset(ids) - held)


def check_split(split: Split, universe) -> None:
    """Refuse a split that is not a partition of the universe. Raises `ValueError`.

    TWO FAILURES, AND THE FIRST IS THE ONE AN EDGE-LEVEL SPLIT PRODUCES. A sample
    fans out to many edges, so dividing the EDGE frame and letting endpoints
    follow puts the same sample in both halves: its membership is hidden on one
    side and trains the run on the other, and the run then scores answers it was
    given. Nothing about that shows up as an error, a warning or a row-count
    anomaly -- the curve simply reads better than it is.

    The second is quieter. A sample in NEITHER half is treated as kept by every
    consumer here, so its registrations reach the training set while the split
    believes nothing was decided about it. Refusing it is what makes "held out"
    and "not kept" the same statement.

    Checked HERE, in the one function every entry point passes through, rather
    than only in a test, following `precedent.assay_index` and
    `mode2._proposal_source`. A caller who builds a `Split` by hand -- which
    is the supported way to run a stratified or hand-chosen hold-out -- gets the
    same guard as one who calls `split_by_sample`.
    """
    ids = {int(s) for s in universe}
    both = sorted(split.held_out & split.kept)
    if both:
        raise ValueError(
            f"{len(both)} sample(s) are in both halves of the split: "
            f"{both[:10]}. Splitting by EDGE produces exactly this, because a "
            "sample fans out to many edges; the run would then hide a "
            "registration on one side and train on it from the other, and "
            "score the answer it was given. Split by SAMPLE.")
    neither = sorted(ids - split.held_out - split.kept)
    if neither:
        raise ValueError(
            f"{len(neither)} sample(s) are in neither half of the split: "
            f"{neither[:10]}. An unassigned sample is treated as kept by every "
            "consumer here, so its registrations would train a run that "
            "believes it has blinded them. Build the split from "
            "`sample_universe`.")
    stray = sorted((split.held_out | split.kept) - ids)
    if stray:
        raise ValueError(
            f"{len(stray)} sample(s) in the split are absent from the "
            f"universe: {stray[:10]}. The split and the frames describe "
            "different runs.")


# --- hiding, reversibly -------------------------------------------------------


def blind_membership(
    membership: pd.DataFrame,
    held_out,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (the rows a kept sample holds, the rows a held-out sample held).

    EVERY ROW OF A HELD-OUT SAMPLE GOES, NOT ONLY THE ONE BEING RECOVERED. Hiding
    a single `(sample, assay)` leaves the sample's other registrations visible,
    and precision is only definable against a COMPLETE answer key: with the rest
    of its memberships in place, a proposal naming one of them is not a proposal
    at all -- `mode2_candidates` never offers an assay a sample already holds --
    so the scorable population would be one pair per sample and the false-
    positive population would be missing exactly the assays the curator did
    assign. Blinding the sample whole makes its whole registration set the answer
    key.

    PURE, AND THE REVERSIBILITY IS CHECKED HERE RATHER THAN ASSUMED. Neither
    returned frame shares storage with a mutation of the input, the input is not
    touched, and the two halves are re-joined and compared against it before
    either is returned. A backtest that quietly dropped a row would produce a
    membership frame the live classifier could pick up in the same process, and
    the symptom would be a Mode 2 run missing precisely the rows this function
    hid.

    Row ORDER is not preserved and row CONTENT is: both halves are re-indexed, so
    the comparison is over the sorted row multiset. The index of a membership
    frame carries no meaning -- `MEMBERSHIP_COLUMNS` is the whole record -- and a
    check that demanded positional identity would fail on a frame that had merely
    been re-read from parquet.
    """
    held = {int(s) for s in held_out}
    is_hidden = membership.sample_id.map(lambda s: int(s) in held)
    kept_rows = membership[~is_hidden].reset_index(drop=True)
    hidden_rows = membership[is_hidden].reset_index(drop=True)
    key = list(S.MEMBERSHIP_COLUMNS)
    restored = restore_membership(kept_rows, hidden_rows)
    if not restored.sort_values(key, ignore_index=True).equals(
            membership[key].sort_values(key, ignore_index=True)):
        raise ValueError(
            f"hiding {len(hidden_rows)} of {len(membership)} membership row(s) "
            "is not reversible: putting the two halves back does not reproduce "
            "the frame they came from. A backtest whose hiding leaks is "
            "indistinguishable, in its own output, from one that measured "
            "something.")
    return kept_rows, hidden_rows


def restore_membership(
    kept_rows: pd.DataFrame,
    hidden_rows: pd.DataFrame,
) -> pd.DataFrame:
    """Put the two halves of `blind_membership` back, on `MEMBERSHIP_COLUMNS`.

    A function rather than a `concat` at each call site, because the reversibility
    check inside `blind_membership` and any caller's own restore have to be the
    SAME operation or the check proves nothing about the restore.
    """
    return pd.concat(
        [kept_rows[list(S.MEMBERSHIP_COLUMNS)],
         hidden_rows[list(S.MEMBERSHIP_COLUMNS)]],
        ignore_index=True)


def training_edges(edges: pd.DataFrame, held_out) -> pd.DataFrame:
    """The subgraph induced on the KEPT samples: no endpoint is held out.

    THIS IS NOT AN EDGE-LEVEL SPLIT AND THE DIFFERENCE IS THE WHOLE METHOD. The
    split is made over samples; this filter is its consequence, and a sample is
    on exactly one side of it however many edges it touches.

    THE ALTERNATIVE IS BIASED AND LOOKS IDENTICAL. Mining over EVERY edge with a
    blinded membership frame keeps an edge whose endpoint was blinded, and that
    edge moves out of `n_both` into a one-sided counter -- so a hop whose true
    propagation rate is `p` reads about `(1 - fraction) * p`. Measured at a 20%
    hold-out on seed 0 over the real extract, with the biased mining as the only
    difference, the `[0.95,1.00]` band all but empties: 1 ADD_PARENT row and 6
    ADD_CHILD rows against 4,151 and 19,337, the mass landing in `[0.75,0.90)`
    instead at 5,424 and 19,165. Both readings came out of this module during
    development and the first one was wrong.

    Neither self-loops nor duplicate pairs are touched here. `mine_precedent`
    reads the frame it is given as-is, and this function's contract is one thing
    only: no held-out sample's own edge contributes to the evidence its recovery
    is judged by.
    """
    held = {int(s) for s in held_out}
    keep = [int(c) not in held and int(p) not in held
            for c, p in zip(edges.child_id, edges.parent_id)]
    return edges[pd.Series(keep, index=edges.index)]


# --- the curator's answer key -------------------------------------------------


def held_out_truth(
    registered: dict[int, set[int]],
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    held_out,
) -> tuple[dict[tuple[int, int], str], list[tuple[int, int]]]:
    """-> (the pairs Mode 2 could recover and their direction, the ones it cannot).

    A pair is `(sample_id, internal assay id)` a curator registered on a held-out
    sample. It is RECOVERABLE only if a lineage neighbour holds the same assay in
    the FULL world -- that is the spec's "both sides registered" population -- and
    the direction is the one `neighbour_registers` would report on that world,
    with `LIN_CHILD` beating `LIN_PARENT` so the two functions cannot disagree
    about which action a pair belongs to.

    THE DIRECTION COMES FROM THE FULL WORLD AND THE PROPOSAL FROM THE BLINDED
    ONE, deliberately, and they can differ. If the child that supported the pair
    is held out as well, and a kept parent also holds the assay, the cold run
    proposes the mirror action. The census counts that as
    `recovered_in_the_other_direction_*` rather than as a miss or as a plain
    recovery, and it can only do so because the two readings are kept apart.

    THE SECOND RETURN IS NOT AN ERROR AND IS NOT DROPPED. A registration no
    neighbour holds is outside Mode 2's reach in any world -- no split makes it
    recoverable -- so it is excluded from the population and counted by name.
    Leaving it in the denominator would report Mode 2 as missing work it never
    claimed, and dropping it unrecorded is the silent loss this package raises
    over everywhere else.

    Two returns from ONE scan, following `lineage_supports`: a pair is in exactly
    one of them, and computing the two separately is how they come to disagree.
    Both are ordered on `sorted(held_out)` so the artifact is stable across runs;
    the dicts they are built from follow the edge frame, whose row order is not.

    "Registered" is ANY membership row, crossed by `audit.registered_internal`.
    The MAPPABLE-only reading is 82 samples smaller and has already produced a
    wrong population figure and a wrong Mode 2 ceiling on this branch.
    """
    truth: dict[tuple[int, int], str] = {}
    no_neighbour: list[tuple[int, int]] = []
    empty: frozenset[int] = frozenset()
    nothing: set[int] = set()
    for sample_id in sorted(int(s) for s in held_out):
        have = registered.get(sample_id, nothing)
        if not have:
            continue
        kids = children_of.get(sample_id, empty)
        rents = parents_of.get(sample_id, empty)
        for assay_id in sorted(have):
            if any(assay_id in registered.get(n, nothing) for n in kids):
                truth[(sample_id, assay_id)] = S.A_ADD_PARENT
            elif any(assay_id in registered.get(n, nothing) for n in rents):
                truth[(sample_id, assay_id)] = S.A_ADD_CHILD
            else:
                no_neighbour.append((sample_id, assay_id))
    return truth, no_neighbour


# --- the curve ----------------------------------------------------------------


def band_of(rate) -> str:
    """Which band a `precedent_rate` falls in. `BAND_NO_RATE` for a null.

    HALF-OPEN EXCEPT AT THE TOP, where the band is closed so that a rate of
    exactly 1.0 -- the commonest value in the top band, and the one the whole
    question turns on -- lands in the table rather than falling off it.

    A NULL IS ITS OWN BAND AND IS NEVER 0.0. `precedent_rate` is null where the
    hop carries no mined rule at all, which is a statement that nobody measured;
    0.000 is a real rate meaning "observed here, and never once co-registered".
    Filing the first under the second is the "absent evidence read as evidence of
    absence" defect this package raises over in four other places.

    RAISES on a rate outside `[0, 1]`. Both rates are `n_both / (n_both + x)`, so
    a value above 1 means the frame was not mined by `mine_precedent`, and
    silently banding it would put an impossible number in a curator's table.
    """
    if rate is None or pd.isna(rate):
        return BAND_NO_RATE
    value = float(rate)
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"a precedent rate of {value!r} is outside [0, 1]. Both rates are "
            "n_both / (n_both + n_*_only), so this frame was not mined by "
            "`mine_precedent` and banding it would print an impossible number.")
    for label, hi in zip(BAND_LABELS[1:], BAND_EDGES[1:]):
        if value < hi:
            return label
    return BAND_LABELS[-1]


def recovery_bands(
    scored: pd.DataFrame,
    truth: dict[tuple[int, int], str],
) -> pd.DataFrame:
    """Precision by band and by direction, with the support behind every cell.

    THE TWO DIRECTIONS ARE NEVER POOLED, at any band. Measured over the real
    extract at a 20% hold-out, `[0.00,0.50)` recovers 519 of 8,806 ADD_PARENT
    proposals and 210 of 18,996 ADD_CHILD ones -- five times apart -- while
    `[0.95,1.00]` recovers 4,143 of 4,151 and 19,270 of 19,337, which is the same
    number twice. One figure covering both would hide the first fact and
    manufacture the second.

    A BAND WITH NO OBSERVATIONS REPORTS EMPTY AND NEVER A PRECISION OF 0.0. The
    two are different statements: 0.000 says every proposal in the band named an
    assay the curator did not assign, and a null says there was nothing to read.
    An operator shown 0.000 for an unmeasured band would take a measurement to
    have been made and to have failed.

    `rule_groups` COUNTS DISTINCT `(n_both, n_child_only, n_parent_only)`
    TRIPLES, so it is a LOWER BOUND on the precedent rules behind a band: two
    rules with identical counts collapse into one group. The bias is toward
    reporting MORE concentration than there is, which is the safe direction for a
    number whose job is to discount a row count. Measured on the LIVE extract it
    is exact at the 0.95 cut -- 15 qualifying reverse rules occupy 15 distinct
    triples and 5 propagation rules 5 -- and loose across the whole mined set,
    where the 961 mined rules occupy 537 distinct triples. Re-measured
    2026-08-18, the inherited "961 mined rules collapse to 537 triples, 44%" is
    EXACT: the excess is 961 - 537 = 424, which is 44.1%. The number that
    answers "how much of the mined set is affected" is a different one and is
    larger -- 561 rules, 58.4%, actually share a triple with another, over 137
    multi-rule groups whose largest holds 32. Neither figure has been
    re-measured on a blinded world, so `rule_groups` is read here as a lower
    bound only.

    THE `NO_RATE` BAND REPORTS ZERO GROUPS AND NOT ONE. Those rows carry a null
    triple, and `drop_duplicates` treats two nulls as equal, so the natural
    spelling reports "1 evidence group" for rows whose evidence is that nobody
    measured. A group of nulls is not a group.

    `largest_group_rows` and `largest_group_correct` answer the question the top
    band raises -- whether one hop is doing all the work -- on the table itself.
    Subtract them from `rows` and `correct` and what remains is the band with its
    biggest single piece of evidence removed.
    """
    bands = scored.precedent_rate.map(band_of)
    correct = pd.Series(
        [(int(s), int(a)) in truth
         for s, a in zip(scored.sample_id, scored.proposed_internal_assay_id)],
        index=scored.index, dtype=bool)

    rows = []
    for label in BAND_LABELS:
        for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
            in_cell = (scored.action == action) & (bands == label)
            cell, hit = scored[in_cell], correct[in_cell]
            groups: dict[tuple, list[int]] = {}
            if label != BAND_NO_RATE:
                for triple, good in zip(
                        zip(cell.precedent_n_both, cell.precedent_n_child_only,
                            cell.precedent_n_parent_only), hit):
                    tally = groups.setdefault(triple, [0, 0])
                    tally[0] += 1
                    tally[1] += int(bool(good))
            # Ties broken by the higher `correct` and then by insertion order,
            # which is the emitted frame's total sort -- so the reported largest
            # group does not change between two runs over identical data.
            biggest = max(groups.values(), default=[0, 0])
            rows.append({
                "band": label,
                "action": action,
                "rows": len(cell),
                "correct": int(hit.sum()),
                # EMPTY, and never 0.0: see the docstring
                "precision": (int(hit.sum()) / len(cell)) if len(cell) else None,
                "samples": cell.sample_id.nunique(),
                "rule_groups": len(groups),
                "largest_group_rows": biggest[0],
                "largest_group_correct": biggest[1],
            })
    return pd.DataFrame(rows, columns=RECOVERY_COLUMNS)


# --- the run ------------------------------------------------------------------


def _digest(frame: pd.DataFrame) -> str:
    """A stable fingerprint of a frame's columns and contents.

    Used only to prove that `backtest` left its inputs alone. `pd.util.
    hash_pandas_object` is vectorised, so this costs milliseconds on the 794,593
    edge rows and can run on every input twice per call.
    """
    body = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    return hashlib.sha256(repr(list(frame.columns)).encode() + body).hexdigest()


def backtest(
    *,
    edges: pd.DataFrame,
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
    split: Split,
) -> Backtest:
    """Run Mode 2 blind on a held-out slice and score it against the curators.

    FIVE KEYWORD-ONLY FRAMES, and the keyword is the guard, following
    `mode2_findings`. All five are `pd.DataFrame` and three of them carry a
    `sample_id`, so a positional call could transpose `membership` with `nodes`
    and get a populated, wrong curve with no error -- this package's named
    failure class.

    NOTHING IS MUTATED AND THE GUARD IS RUN, NOT ASSERTED. Every input frame is
    fingerprinted before and after, because this function's inputs are the frames
    a live classification is reading in the same process, and a hidden row that
    escaped would take exactly the shape of a Mode 2 run that lost proposals.

    THE COLD RUN CARRIES NO CLAIM. `mode2_findings` is handed an EMPTY claims
    frame, so the curve measures precedent and lineage alone -- see this module's
    docstring for why the vocabulary cannot be blinded by any split made here --
    and the run is CHECKED afterwards to have used nothing else.

    NOT ONE PROPOSAL IS FILTERED BY A RATE. The whole cold-run output is returned
    and banded, and the census's `proposals` equals its length. A band orders what
    an operator reads first; under the binding constraint it grants no permission
    and there is no cutoff to choose.
    """
    check_split(split, sample_universe(samples, membership, edges))
    before = {name: _digest(frame) for name, frame in (
        ("edges", edges), ("samples", samples), ("membership", membership),
        ("assays", assays), ("nodes", nodes))}

    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, samples, membership)
    truth, no_neighbour = held_out_truth(
        registered_internal(membership, assays), children_of, parents_of,
        split.held_out)

    kept_rows, hidden_rows = blind_membership(membership, split.held_out)
    train = training_edges(edges, split.held_out)
    type_reg = G.type_registration_index(kept_rows, assays, nodes)
    findings = M2.mode2_findings(
        pd.DataFrame(columns=X.ATTACHED_COLUMNS),
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=registered_internal(kept_rows, assays),
        rules=M2.precedent_rules(B.mine_precedent(train, kept_rows, assays)),
        reg_projects=M2.registration_projects(kept_rows, assays),
        types=G.sample_type_index(nodes),
        type_reg=type_reg,
        # BLINDED WITH THE OTHER TWO. `registered`, `type_reg` and `assay_pop`
        # are all read off `kept_rows`: a population built off the full
        # membership would let a held-out registration decide whether a cold
        # proposal reads `CLS_UNREACHABLE` or `CLS_BOOTSTRAP`.
        assay_pop=M2.assay_population(kept_rows, assays),
        titles=M2.assay_titles(assays),
        projects=X.project_index(samples),
        # NOT BLINDED, AND IT CANNOT BE. Which assay records have a junction
        # row in `dmac.assays_internal_assays` is a property of the assays
        # frame, which no split touches; holding out a registration reveals
        # nothing about it. So this reads the FULL frame beside the three
        # indexes above that are deliberately built off `kept_rows`.
        fallback_assay_ids=B.fallback_assay_ids(assays),
    )
    leaked = set(findings.proposed_by) - {X.BY_PRECEDENT, X.BY_LINEAGE_ONLY}
    if leaked:
        raise ValueError(
            f"the cold run produced proposal source(s) {sorted(leaked)}, which "
            "can only come from a metadata claim. The vocabulary was learned "
            "over the FULL labelled edge set, so a claim-corroborated proposal "
            "has seen the answer and this curve would be scoring it.")

    held = set(split.held_out)
    is_scored = findings.sample_id.map(lambda s: int(s) in held)
    scored = findings[is_scored]
    bands = recovery_bands(scored, truth)

    recovered: dict[tuple[int, int], str] = {}
    for sample_id, assay_id, action in zip(
            scored.sample_id, scored.proposed_internal_assay_id, scored.action):
        pair = (int(sample_id), int(assay_id))
        if pair in truth:
            recovered[pair] = action

    census = {
        "samples_in_the_universe": len(split.held_out) + len(split.kept),
        "samples_held_out": len(split.held_out),
        "samples_kept": len(split.kept),
        "membership_rows": len(membership),
        "membership_rows_hidden": len(hidden_rows),
        "membership_rows_kept": len(kept_rows),
        "edge_rows": len(edges),
        "edge_rows_training": len(train),
        "held_out_registrations": len(truth) + len(no_neighbour),
        "held_out_registrations_with_no_neighbour": len(no_neighbour),
        "truth_pairs": len(truth),
        "proposals": len(findings),
        "proposals_scored": len(scored),
        "proposals_on_a_kept_sample": len(findings) - len(scored),
    }
    for action, suffix in ACTION_SUFFIX.items():
        population = [p for p, a in truth.items() if a == action]
        census[f"truth_pairs_{suffix}"] = len(population)
        census[f"recovered_{suffix}"] = sum(
            1 for p in population if recovered.get(p) == action)
        census[f"recovered_in_the_other_direction_{suffix}"] = sum(
            1 for p in population if p in recovered and recovered[p] != action)
        census[f"not_recovered_{suffix}"] = sum(
            1 for p in population if p not in recovered)
        census[f"proposals_scored_correct_{suffix}"] = int(
            bands[bands.action == action]["correct"].sum())

    assert set(census) == set(BACKTEST_CENSUS_KEYS), \
        "BACKTEST_CENSUS_KEYS is out of date"
    assert census["membership_rows"] == (census["membership_rows_hidden"]
                                         + census["membership_rows_kept"])
    assert census["held_out_registrations"] == (
        census["truth_pairs"]
        + census["held_out_registrations_with_no_neighbour"])
    assert census["truth_pairs"] == (census["truth_pairs_add_parent"]
                                     + census["truth_pairs_add_child"])
    assert census["proposals"] == (census["proposals_scored"]
                                   + census["proposals_on_a_kept_sample"])
    for suffix in ACTION_SUFFIX.values():
        assert census[f"truth_pairs_{suffix}"] == (
            census[f"recovered_{suffix}"]
            + census[f"recovered_in_the_other_direction_{suffix}"]
            + census[f"not_recovered_{suffix}"])
    assert int(bands["rows"].sum()) == census["proposals_scored"], \
        "the bands must partition the scored rows and filter none of them"
    # The band table and the census count the same recoveries by two routes and
    # key them on two different worlds' directions, so this is a cross-check
    # rather than a restatement: it holds only if every flipped pair is counted
    # once on each side.
    assert (census["proposals_scored_correct_add_parent"]
            + census["proposals_scored_correct_add_child"]) == sum(
        census[f"{k}_{s}"] for s in ACTION_SUFFIX.values()
        for k in ("recovered", "recovered_in_the_other_direction"))

    after = {name: _digest(frame) for name, frame in (
        ("edges", edges), ("samples", samples), ("membership", membership),
        ("assays", assays), ("nodes", nodes))}
    if after != before:
        raise ValueError(
            "the backtest modified an input frame: "
            f"{sorted(k for k in before if before[k] != after[k])}. Hiding must "
            "be perfectly reversible, and these frames are what a live "
            "classification reads.")

    return Backtest(bands, {k: int(v) for k, v in census.items()}, findings,
                    truth)


def main(extract_dir: str = "assay-hygiene/extract",
         fraction="0.2", seed="0") -> int:
    """Backtest Mode 2 over the extract on disk. Read-only, no file written.

    The fraction and the seed are printed beside every figure they produced,
    because a recovery curve without its hold-out size is not reproducible and
    this project has already published two irreproducible readings of one number.

    Nothing here chooses a threshold. The band table is a READING ORDER: under
    the binding constraint every proposed change reaches the operator for
    approval, so the strongest band is where they start, not what they are
    allowed to write.
    """
    d = Path(extract_dir)
    fraction, seed = float(fraction), int(seed)
    # Named one at a time rather than built from a loop over a name list, so
    # every file this module opens is greppable in its own source. A read-only
    # guard that searches for filenames finds none at all under an f-string, and
    # a further file added later then reaches production unnamed.
    samples = pd.read_parquet(d / "samples.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")
    edges = pd.read_parquet(d / "edges.parquet")

    universe = sample_universe(samples, membership, edges)
    split = split_by_sample(universe, fraction=fraction, seed=seed)
    out = backtest(edges=edges, samples=samples, membership=membership,
                   assays=assays, nodes=nodes, split=split)

    print(f"MODE 2 BACKTEST at a {fraction:.0%} hold-out on seed {seed}, split "
          f"by SAMPLE and never by edge")
    for key in BACKTEST_CENSUS_KEYS:
        print(f"  {key:<44} {out.census[key]:>9,}")
    print("  a registration with no neighbour holding the same assay is "
          "outside Mode 2's reach in ANY world, so it is counted above and "
          "excluded from the population rather than scored as a miss.")
    print("  a proposal about a KEPT sample is unscorable by construction -- "
          "Mode 2 never proposes an assay a sample already holds, so every one "
          "of them names an assay the curator did not assign.")

    print("recovery by band -- a READING ORDER and never a permission; every "
          "proposal above is banded and none is filtered:")
    for r in out.bands.itertuples(index=False):
        rate = "EMPTY" if r.precision is None or pd.isna(r.precision) \
            else f"{r.precision:.3f}"
        print(f"  {r.band:<12} {r.action:<22} {r.rows:>8,} rows  "
              f"{r.correct:>8,} recovered   precision {rate:>6}   over "
              f"{r.samples:>8,} sample(s) on {r.rule_groups:>4} evidence "
              f"group(s), the largest keying {r.largest_group_rows:,}")
    print("  EMPTY is not 0.000. A band with no observations was not measured; "
          "0.000 means every proposal in it named an assay the curator did not "
          "assign.")
    print("  `evidence group(s)` counts distinct (n_both, n_child_only, "
          "n_parent_only) triples and is a LOWER BOUND on the precedent rules "
          "behind a band, so a row count is not an evidence count.")
    print("  every precision here is a LOWER BOUND: a curator's assay set is "
          "not known to be complete -- that is the premise of Modes 1 and 2 -- "
          "so a proposal counted wrong may be a genuine gap correctly found.")
    print("  this scores proposals about samples whose registrations were "
          "HIDDEN. It is not the precision of the live dark rows, which have no "
          "ground truth by construction.")
    print("nothing was written: this run produced no file and no database "
          "change, and no threshold was chosen")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
