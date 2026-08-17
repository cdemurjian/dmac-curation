# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The co-registration test. Do these two assays coexist, or are they aliases?

Third and last of the three deterministic tests, and it runs after the
vocabulary gate and after lineage. Each is named for what it establishes:

    reachability     is a sample of this TYPE ever registered in the claimed
                     assay, anywhere?          -> is the CLAIM credible at all
    lineage          does a parent or child already register it?
                                               -> is this an ABSENCE, and which
                                                  DIRECTION does it run in
    co-registration  across samples of this type registered in R, what share
                     also register X?          -> do R and X COEXIST, or are
                                                  they alternative labels

**A ZERO RATE ON A REACHABLE, WELL-SUPPORTED PAIR MEANS ALTERNATIVE LABELS. IT
IS NOT A CONTRADICTION, AND THE FIRST DRAFT OF THIS TASK'S PLAN SAID IT WAS.**
That is the second of the two corrections the operator made to this design, and
it is the reason this module exists.

Increment 1 reported 866 "contradictions". Reviewing the 51 that survived the
first correction, 45 were found to name CORRECT assays -- **but that 45/51 was
produced by `scripts/measure_absence_vs_contradiction.py`, NOT by this module,
and its scope is not this module's.** That script types samples by the uuid
prefix in `samples.parquet`, drops membership rows whose assay has no junction
row (the MAPPABLE-only definition of "registered", the same one that understated
the Mode 2 ceiling by 227 and 1,098), and takes lineage over `childof.parquet`
rather than DERIVED_FROM. It is quoted here as the OBSERVATION that motivated
this test and never as a figure this test reproduces; nothing in this package
re-derives it, and it should not be repeated without this sentence.

What this module measures, on its own rule and stated in its own scope: over the
real extract 2026-08-17, typing samples off `nodes.type` and counting ANY
membership row as registered, `(D.IMG, 127, 145)` reads 0.000 over 2,035 samples
of the type. D.IMG images sit in 127 Tissue Imaging OR in 145 Histopathology,
never both, because a curator picks one -- and 145 D.IMG samples ARE registered
in Histopathology, so the pair is reachable in both directions and the gate
passes the claim. Nothing is wrong with those registrations.

The mirror reading is the useful one: a HIGH rate means the two assays routinely
coexist on this type, so the absence of the second IS the anomaly. `(PAV, 56,
74)` reads 0.805 over 13,220 -- a Patient Visit that had tissue collected from
it belongs in Patient Visit, which produced it, and in Tissue Collection, which
consumed it. That is the operator's domain rule, measured.

THE RATE IS DIRECTIONAL AND THE TWO DIRECTIONS ARE DIFFERENT QUESTIONS.
`(PAV, 56, 74)` is 0.805 over 13,220 and `(PAV, 74, 56)` is 0.987 over 10,782,
on the same 10,642 samples holding both. The numerator is shared; the
denominator is the population of the REGISTERED side, so the key is ordered and
a symmetric measure answers neither question.

SUPPORT IS COUNTED IN SAMPLES OF THE TYPE, NEVER IN MEMBERSHIP ROWS. Task 2
ruled this for the vocabulary floor after finding 21 of 50 single-sample terms
clearing an edge floor of 30, and the same trap is here in another unit: a
sample registered in one internal assay through two seek `assays` records
carries two membership rows. The support of `(T, R, X)` is exactly the
`gate.type_registration_index` cell `(T, R)` -- the same number the gate's
reachability test rules on -- so a claim's support and its reachability
evidence cannot disagree.

NOTHING HERE DECIDES. `MIN_CO_REG_SUPPORT` and `CO_OCCUR_BAND` are read for
BANDING only: `compat_band` assigns a label to a measured rate so an operator
reads the strongest evidence first. Neither number stops a row reaching a mode.
Blocking lives in `gate.blocks_mode` and nowhere else, and
`tests/test_assay_hygiene_schema.py::test_the_two_reporting_numbers_gate_nothing`
names this module as the ONE approved reader while keeping the ban on every
other module in the package.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.compatibility

Read-only. It opens three parquet files, writes none, proposes nothing and
touches no database.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from . import _schema as S
from .audit import registered_internal
from .gate import (sample_type_sets, type_registration_index,
                   untyped_registration_samples)

# What each band ESTABLISHES -- reported, never enforced, and valid only in one
# position in the pipeline: AFTER the gate has passed the claim and AFTER
# `lineage.neighbour_registers` has returned `LIN_NONE`. A neighbour already
# carrying the assay is `CLS_ABSENCE_LINEAGE` whatever this test says, because
# lineage runs first and a registration a neighbour actually holds outranks a
# population statistic.
#
# THE ONLY ENTRY RESTING ON A TUNED NUMBER IS THE ROUTINE / SOMETIMES SPLIT, and
# both sides of it are REPORTED classes. `CLS_ALT_LABEL` rests on a rate of
# exactly 0.0, which has no tuned number in it at all -- the same criterion
# `gate.BLOCKING_OUTCOMES` uses to decide what may stop a claim. So moving
# `CO_OCCUR_BAND` moves which of two reported classes a row carries and moves
# nothing else; it cannot create or destroy an alternative-label finding, and it
# cannot stop a row reaching a mode.
#
# `BAND_NO_SUPPORT` maps to `CLS_UNRESOLVED` and NOT to `CLS_ALT_LABEL`, which
# is the whole reason `_schema` declares the two bands separately: a rate of
# 0.000 over four samples reported as "these never coexist" manufactures an
# alternative-label finding out of an empty population. `CLS_UNRESOLVED` is
# reported at its own size rather than absorbed, because silently banding what
# the pipeline cannot classify is how a bucket ends up named for what someone
# assumed was in it -- three times on this branch so far.
BAND_ESTABLISHES = {
    S.BAND_NEVER: S.CLS_ALT_LABEL,
    S.BAND_ROUTINE: S.CLS_ABSENCE_COMPAT,
    S.BAND_SOMETIMES: S.CLS_UNRESOLVED,
    S.BAND_NO_SUPPORT: S.CLS_UNRESOLVED,
}


def co_registration(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
) -> dict[tuple[str, int, int], tuple[float, int]]:
    """(sample_type, registered assay, proposed assay) -> (rate, support).

    `rate` is the share of samples of `sample_type` registered in the REGISTERED
    assay that also register the PROPOSED one. `support` is the size of that
    denominator, in SAMPLES OF THE TYPE.

    THE THIRD ARGUMENT IS `nodes` AND NOT `samples`, a deliberate departure from
    the briefed interface and the same one `gate.type_registration_index` made.
    `SAMPLE_COLUMNS` carries no type column at all, and deriving one from the
    uuid prefix is wrong on 5 of the 177,392 nodes. It is not a cosmetic
    difference: measured 2026-08-17, typing samples off `samples.parquet`'s uuid
    prefix reads 1,907 for the `(D.IMG, 127)` population where `nodes.type`
    reads 2,035, because 132 samples registered in 127 and typed D.IMG by the
    graph have no `samples.parquet` row at all. Both RATES are identical either
    way, so the finding is robust to the choice and the support is not.

    THE KEY SPACE IS PAIRS BOTH REACHABLE FOR THE TYPE, and the restriction is
    load-bearing. A key is emitted for every ordered `(R, X)` with `R != X`
    where `gate.type_registration_index` holds a cell for `(T, R)` AND for
    `(T, X)`. So:

      A MISSING KEY MEANS THE PROPOSED ASSAY IS UNREACHABLE FOR THE TYPE, WHICH
      IS THE GATE'S RULING AND NEVER A RATE OF ZERO. Emitting `(T, R, X)` at
      0.0 for an X no sample of type T is registered in anywhere would band it
      `BAND_NEVER` on a full-sized support and report a vocabulary defect as an
      alternative label -- the bucket-naming error this branch has now made
      three times. `gate.gate_claims` has already stopped such a claim as
      `GATE_UNREACHABLE`; callers must treat a `.get` miss as that, and
      `best_co_registration` does.

      THE DIAGONAL IS ABSENT. `(T, R, R)` would read 1.0 by construction, and a
      sample already registered in the assay has no absence for anything to
      explain. That is the same guard `lineage.lineage_supports` places at the
      top of its scan.

    Registrations are crossed to the internal namespace by
    `audit.registered_internal`, the package's single crossing of the seek
    `assay_assets.assay_id` junction, and "registered" is ANY MEMBERSHIP ROW.
    The MAPPABLE-only set is 82 samples smaller, the two have now been confused
    three times in this project, and the third instance is the Mode 2 ceiling:
    55,007 / 117,463 under ANY against 54,780 / 116,365 under MAPPABLE-only, two
    published readings of one number that differ by nothing but this definition.
    See `lineage.mode2_ceiling`.

    Sample types come from `gate.sample_type_sets`, shared with
    `type_registration_index` so the numerator and the denominator cannot type a
    sample differently. A sample carrying two node rows that disagree on type
    counts under BOTH types, in both.

    A REGISTERED SAMPLE WITH NO NODE ROW CARRIES NO TYPE and so reaches no cell,
    in the numerator or the denominator. 194 exist on the real extract over 210
    of the 214,296 membership rows. They are not dropped silently:
    `gate.untyped_registration_samples` names every one, `main` prints them, and
    a test asserts both halves.

    RAISES, through `registered_internal` and `type_registration_index`, on a
    membership row naming an assay absent from the assays frame. Both refuse to
    skip for the same reason: a dropped registration can only SHRINK a cell, and
    a shrunk denominator inflates every rate resting on it with no error, no
    warning and no row-count anomaly.

    Neither input frame is mutated.
    """
    type_reg = type_registration_index(membership, assays, nodes)
    registered = registered_internal(membership, assays)
    types = sample_type_sets(nodes)

    both: dict[tuple[str, int, int], int] = defaultdict(int)
    for sample_id, assay_ids in registered.items():
        if len(assay_ids) < 2:
            continue                      # no pair to co-register
        for stype in types.get(sample_id, ()):
            for r in assay_ids:
                for x in assay_ids:
                    if r != x:
                        both[(stype, r, x)] += 1

    reachable: dict[str, list[int]] = defaultdict(list)
    for stype, assay_id in type_reg:
        reachable[stype].append(assay_id)

    out: dict[tuple[str, int, int], tuple[float, int]] = {}
    for stype, assay_ids in reachable.items():
        for r in assay_ids:
            pop = type_reg[(stype, r)]
            for x in assay_ids:
                if r == x:
                    continue
                n = both.get((stype, r, x), 0)
                # The numerator counts samples of this type registered in BOTH,
                # the denominator counts those registered in R, so the first is
                # a subset of the second BY CONSTRUCTION -- but only while both
                # passes agree about which samples are registered and what type
                # they are. They come from two different functions over two
                # different frames, and this is the one line that proves they
                # still agree. A rate over 1.0 is what a numerator and a
                # denominator built on two definitions of "registered" look
                # like, and it is silent everywhere else.
                assert n <= pop, (
                    f"co-registration numerator {n} exceeds its own population "
                    f"{pop} at {(stype, r, x)}: registered_internal and "
                    "type_registration_index disagree about which samples of "
                    "this type are registered in this assay")
                out[(stype, r, x)] = (n / pop, pop)
    return out


def compat_band(rate: float, support: int) -> str:
    """Label a measured rate. It bands, it does not decide.

    SUPPORT IS TESTED FIRST AND THAT ORDER IS THE CONTRACT. A rate of 0.000 over
    four samples is noise, and reporting it as `BAND_NEVER` -- "these two never
    coexist" -- manufactures an alternative-label finding out of an empty
    population. `_schema` declares `BAND_NO_SUPPORT` as a separate outcome for
    exactly this, and the ordering here is what makes the declaration true.
    It is also what makes `best_co_registration`'s `(0.0, 0, None)` safe to
    return when nothing reaches a population.

    The bands, in the order they are tested:

        support < MIN_CO_REG_SUPPORT  BAND_NO_SUPPORT   the rate is unread
        rate == 0.0                   BAND_NEVER        alternative labels
        rate >= CO_OCCUR_BAND         BAND_ROUTINE      they coexist; the
                                                        absence is the anomaly
        otherwise                     BAND_SOMETIMES    neither settles it

    `BAND_NEVER` IS EXACTLY ZERO AND NOT "NEARLY ZERO". A pair that coexists on
    one sample in a thousand is not two names for one thing -- somebody
    registered both once -- and admitting a near-zero cutoff would put a second
    tuned number in the one band that has none. `BAND_NEVER` is therefore the
    only band whose meaning does not move when a constant does, which is why the
    alternative-label finding survives any recalibration of `CO_OCCUR_BAND`.

    THE TWO CONSTANTS ARE READ HERE AND NOWHERE ELSE IN THE PACKAGE, and they
    are read to LABEL a rate. Neither is compared against to decide whether a
    row reaches Mode 1 or Mode 2: that is `gate.blocks_mode`, it tests
    membership of a closed tuple, and `GATE_LOW_SUPPORT` is already excluded
    from it on the same argument. Under the binding constraint -- nothing
    decides, everything proposes -- a threshold ranks and triages, and there is
    no autonomous write for it to gate.

    They are constants rather than parameters deliberately. A sweepable band
    would let one caller band at one boundary and report another, which is the
    divergence `gate.vocabulary_defects` documents at length; there is nothing
    to diverge while the boundary is bound once and the rate it labels is
    computed independently of it.
    """
    if support < S.MIN_CO_REG_SUPPORT:
        return S.BAND_NO_SUPPORT
    if rate == 0.0:
        return S.BAND_NEVER
    if rate >= S.CO_OCCUR_BAND:
        return S.BAND_ROUTINE
    return S.BAND_SOMETIMES


def band_establishes(band: str) -> str:
    """What this band establishes once the gate passed and lineage found nothing.

    `BAND_NEVER` -> `CLS_ALT_LABEL`, and that mapping is the whole point of Task
    4. See `BAND_ESTABLISHES` for the argument, including why only one entry
    rests on a tuned number and why `BAND_NO_SUPPORT` maps to `CLS_UNRESOLVED`
    rather than to `CLS_ALT_LABEL`.

    RAISES on anything that is not a band. The argument is a `str` and so is the
    return, so a caller handing this a classification, a gate outcome or a
    lineage relation would otherwise get a plausible-looking `None` back and
    file the row under it. This module's other `str`-returning function takes
    two numbers, so the two cannot be confused by argument shape alone.
    """
    try:
        return BAND_ESTABLISHES[band]
    except KeyError:
        raise ValueError(
            f"{band!r} is not one of {S.COMPAT_BANDS}. `band_establishes` takes "
            "the OUTPUT of `compat_band` and nothing else -- not a "
            "classification, not a gate outcome and not a lineage relation."
        ) from None


class CoRegistration(NamedTuple):
    """What one (sample, proposed assay) row's co-registration evidence says.

    A NAMEDTUPLE AND NOT A BARE 5-TUPLE, because three of these five fields are
    ints and two of them are POPULATIONS. `support` and `alt_label_support` are
    the same type, mean different things and sit three positions apart, which is
    this package's signature defect in its most literal form -- a positional
    unpack that swapped them would produce a populated, wrong row rather than an
    error. It still compares equal to a plain tuple, so tests may assert either.

    `support` and `alt_label_support` are BOTH counts of samples of the type,
    and each is the check on the rate beside it: `rate` over `support` for the
    winner, and an implied 0.000 over `alt_label_support` for the counter-
    evidence. See `best_co_registration` for what the pair means together.
    """
    rate: float
    support: int
    registered_assay_id: int | None
    alt_label_assay_id: int | None
    alt_label_support: int


def best_co_registration(
    sample_type: str,
    registered_assay_ids,
    proposed_assay_id: int,
    table: dict[tuple[str, int, int], tuple[float, int]],
) -> CoRegistration:
    """The winning rate, AND the strongest evidence against it.

    THE COLLAPSE LIVES HERE AND NOT IN EACH CONSUMER. `FINDING_COLUMNS` carries
    ONE co-registration block per row and a row is per (sample, proposed assay),
    while a sample registered in several assays offers one rate per registered
    assay -- up to 7 on the real extract. Two consumers each inventing a collapse
    is the same class of defect as two definitions of "registered", which has now
    produced three wrong figures on this branch.

    THE BEST RATE WINS, because any registered assay that routinely coexists
    with the proposed one supports the proposal. The rule is mandated by the
    plan and is unchanged.

    BUT A WELL-SUPPORTED ZERO IS NOT SILENCE, IT IS COUNTER-EVIDENCE, and an
    earlier version of this docstring argued that "a sample's other
    registrations do not weaken evidence they say nothing about". That is true
    of a weak or middling rate and FALSE of a `BAND_NEVER` one. If the sample
    holds R1, and X never co-registers with R1 across a well-supported
    population, then X and R1 are ALTERNATIVE LABELS -- so proposing X may be
    adding a synonym to a sample that already carries the thing. Reporting only
    the winner discards that in exactly the case where it is strongest.

    So `alt_label_assay_id` carries the best well-supported zero among the
    sample's own registrations, with `alt_label_support` beside it, and both
    reach the operator through `FINDING_COLUMNS`. MEASURED 2026-08-17 over the
    7,831 (gated claim, type) rows on a registered sample whose proposed assay
    it does not hold:

      5,839 of 7,831 (74.6%)  have a well-supported zero available at all
        428 of 7,831 ( 5.5%)  are OUTRIGHT CONFLICTS -- the winner bands
                              BAND_ROUTINE, so `BAND_ESTABLISHES` reads
                              CLS_ABSENCE_COMPAT and the row says "propose X",
                              while a well-supported zero says X is an
                              alternative label for something the sample HOLDS

    408 of those 428 are one pattern, and it is the pattern the spec already
    calls its flagship vocabulary defect: DNA samples proposed 24 DNA Extraction
    on the `Type: Illumina Library` mapping (purity 0.707, 212 of 250 compat
    flags), winner 64 Short Read Sequencing at 0.797 over 5,437, against a zero
    on 173 cDNA Synthesis over 420 that the sample already holds. The
    counter-evidence points at the rows the spec independently identified as
    wrong.

    THIS DOES NOT RE-CLASSIFY ANYTHING, AND THE OPEN QUESTION IS HANDED FORWARD.
    `BAND_ESTABLISHES` still maps the WINNER's band, so a conflicted row still
    reads CLS_ABSENCE_COMPAT today. Whether a populated `alt_label_assay_id`
    should demote such a row -- to CLS_UNRESOLVED, or to a contested class of
    its own -- is a classification ruling, Tasks 5 and 6 own classification, and
    inventing it here would be a fourth bucket named for what someone assumed
    was in it. What this module owes them is the evidence and its size, and
    those are above.

    WHEN THE WINNER IS ITSELF A ZERO the two agree by construction and the row
    is self-consistent: `compat_band` reads BAND_NEVER, `BAND_ESTABLISHES` reads
    CLS_ALT_LABEL, and `alt_label_assay_id` NAMES the registration X duplicates
    -- which is the D.IMG finding made legible. 1,755 rows read "propose 138
    CometChip Assay" against a zero on 37 Device Imaging over 8,179. Without the
    column the operator is told these are alternative labels and never told of
    WHAT.

    THE WINNER IS RETURNED AND IT HAS A COLUMN OF ITS OWN,
    `FINDING_COLUMNS.co_reg_registered_internal_assay_id`, which rides between
    `co_reg_pop` and `compat_band`. A rate is a statement about an ORDERED PAIR,
    and a row listing four registrations beside one rate does not say which pair
    was measured: the operator cannot audit the number they are being asked to
    approve, nor see that the other candidates were weaker. Returning the winner
    with nowhere to put it would leave Tasks 5, 6 and 8 to decide separately
    whether to keep it, and the one that discarded it would ship that row.

    The column is EMPTY exactly when this returns `None` -- no registered assay
    reached a key at all -- which `compat_band` bands `BAND_NO_SUPPORT` because
    it tests support before rate. An id beside a support of 0 would name a
    population nobody measured.

    "WELL-SUPPORTED ZERO" IS SPELLED `compat_band(...) == BAND_NEVER` AND NOT AS
    A COMPARISON AGAINST `MIN_CO_REG_SUPPORT`. That band already means "zero,
    over a population big enough to read", so re-deriving it here would be a
    second definition of the same idea -- and it would put a floor comparison
    outside `compat_band`, which is the line
    `test_the_two_reporting_numbers_gate_nothing` draws between BANDING on a
    reporting number and GATING on one.

    Ties break on the larger support and then on the LOWEST assay id. Both are
    stable under any iteration order; a bare `max` over a set would make the
    artifact a curator diffs change between runs on identical data, which is the
    hazard `precedent.mine_precedent` and `audit.audit_contradictions` both sort
    against.

    A REGISTERED ASSAY WITH NO KEY CONTRIBUTES NOTHING rather than a zero. A
    missing key means the proposed assay is unreachable for this type, which is
    `GATE_UNREACHABLE` and not a measured absence of coexistence; see
    `co_registration`.

    RETURNS `(0.0, 0, None, None, 0)` WHEN NOTHING REACHES A POPULATION, and the
    zero rate is safe only because the zero support rides beside it and
    `compat_band` tests support FIRST. Banded, that pair reads `BAND_NO_SUPPORT`. Were the
    order reversed it would read `BAND_NEVER` -- "these assays never coexist" --
    asserted on no population at all.

    The caller drops a proposal for an assay the sample already holds, as
    `lineage.neighbour_registers` does; nothing here can manufacture one,
    because `co_registration` emits no diagonal.
    """
    best: tuple[float, int, int] | None = None
    # the strongest counter-evidence: the well-supported zero over the LARGEST
    # population, because a zero over 8,179 samples is a firmer statement that
    # two assays are alternative labels than a zero over 30.
    worst: tuple[int, int] | None = None
    for r in registered_assay_ids:
        hit = table.get((sample_type, int(r), int(proposed_assay_id)))
        if hit is None:
            continue
        rate, pop = hit
        key = (rate, pop, -int(r))
        if best is None or key > (best[0], best[1], -best[2]):
            best = (rate, pop, int(r))
        if compat_band(rate, pop) == S.BAND_NEVER:
            zkey = (pop, -int(r))
            if worst is None or zkey > (worst[0], -worst[1]):
                worst = (pop, int(r))
    rate, pop, winner = best if best is not None else (0.0, 0, None)
    alt_pop, alt = worst if worst is not None else (0, None)
    return CoRegistration(rate, pop, winner, alt, alt_pop)


# Every key `counter_evidence_census` returns, in report order, declared for the
# reason `INTEGRITY_KEYS` and `CEILING_KEYS` are: the report prints them all, and
# a key that stops being produced must break rather than stop being printed.
#
# THE TWO CONFLICT KEYS ARE DIFFERENT NUMBERS AND BOTH ARE NAMED. An earlier
# write-up of this measurement used "conflicted" in two senses one paragraph
# apart -- the loose any-band sense and the strict banded-ROUTINE one -- and
# quoted 12,360 for one population against 428 for the other. They differ by a
# factor of 29 on the Mode 2 ceiling. Two names, so the ambiguity cannot recur.
CENSUS_KEYS = (
    "rows",
    "rows_with_counter_evidence",
    "conflicts_any_band",
    "conflicts_at_band_routine",
    "self_consistent_alt_labels",
)


def counter_evidence_census(
    gated: pd.DataFrame,
    table: dict[tuple[str, int, int], tuple[float, int]],
    registered: dict[int, set[int]],
    types: dict[int, frozenset[str]],
    top: int = 5,
) -> tuple[dict[str, int], list[tuple], list[tuple]]:
    """How often the counter-evidence columns actually carry something.

    -> (counts over CENSUS_KEYS, top conflict patterns, top alt-label patterns)

    THIS EXISTS BECAUSE A SCHEMA CHANGE WAS JUSTIFIED BY A NUMBER THAT LIVED
    ONLY IN PROSE. `co_reg_alt_label_internal_assay_id` and `co_reg_alt_label_pop`
    were added to `FINDING_COLUMNS` on the strength of "5.5% of rows are
    conflicts", and nothing in the tree computed it. That is the same standing
    this package refused for the Mode 2 ceiling, where two prose readings
    disagreed by 227 and 1,098 and neither could be re-derived; `mode2_ceiling`
    was written as code for exactly that reason and two columns in a shared
    contract deserve at least as much.

    THE POPULATION, STATED PRECISELY ENOUGH TO REPRODUCE WITHOUT READING THIS
    CODE. One row per (gated claim, sample type) pair satisfying ALL of:

      1. the claim REACHES A MODE -- `gate.reaches_modes` is true, meaning
         `gate_failures` contains neither `GATE_UNREACHABLE` nor
         `GATE_INCOHERENT`. A recorded `GATE_LOW_SUPPORT` does NOT exclude it,
         because a tuned floor marks and does not block;
      2. the sample is registered in at least one internal assay, under the
         ANY-MEMBERSHIP definition (`audit.registered_internal`), not the
         MAPPABLE-only one;
      3. the sample is NOT already registered in the claimed assay, since a
         sample holding it has no absence to propose;
      4. one row per (claim, TYPE): a sample carrying two node rows that
         disagree on type contributes TWO rows, matching
         `gate.type_registration_index`, which counts such a sample under both.

    Mode 1's population cannot appear here: rule 2 excludes it by construction,
    because a sample registered nowhere has no registration to carry
    counter-evidence.

    THE COUNTS:

      rows                        the population above
      rows_with_counter_evidence  `alt_label_assay_id` is not None
      conflicts_any_band          the winner's rate is above zero AND
                                  counter-evidence exists -- the LOOSE sense
      conflicts_at_band_routine   the winner bands `BAND_ROUTINE`, so
                                  `BAND_ESTABLISHES` reads `CLS_ABSENCE_COMPAT`
                                  and the row says "propose X", AND
                                  counter-evidence exists -- the STRICT sense,
                                  and the one that justified the columns
      self_consistent_alt_labels  the winner is ITSELF a well-supported zero, so
                                  the row already reads `CLS_ALT_LABEL` and the
                                  column names WHAT the proposal duplicates

    The two conflict counts are separate keys because they are separate numbers:
    over the Mode 2 ceiling they read 12,360 and 14, a factor of 29 apart, and a
    single name for both is how one gets quoted for the other.

    Read-only, like everything here. It counts; it proposes nothing.
    """
    from .gate import reaches_modes    # local: keeps the module import-light

    counts = dict.fromkeys(CENSUS_KEYS, 0)
    conflicts: dict[tuple, int] = defaultdict(int)
    alt_labels: dict[tuple, int] = defaultdict(int)

    for row, ok in zip(gated.itertuples(index=False), reaches_modes(gated)):
        if not ok:
            continue
        sample_id, proposed = int(row.sample_id), int(row.internal_assay_id)
        have = registered.get(sample_id)
        if not have or proposed in have:
            continue
        for stype in types.get(sample_id, ()):
            counts["rows"] += 1
            got = best_co_registration(stype, have, proposed, table)
            if got.alt_label_assay_id is None:
                continue
            counts["rows_with_counter_evidence"] += 1
            band = compat_band(got.rate, got.support)
            if got.rate > 0.0:
                counts["conflicts_any_band"] += 1
            if band == S.BAND_ROUTINE:
                counts["conflicts_at_band_routine"] += 1
                conflicts[(stype, proposed, got.registered_assay_id,
                           got.alt_label_assay_id)] += 1
            elif band == S.BAND_NEVER:
                counts["self_consistent_alt_labels"] += 1
                alt_labels[(stype, proposed, got.alt_label_assay_id)] += 1

    assert set(counts) == set(CENSUS_KEYS), "CENSUS_KEYS is out of date"
    # sorted by count then by key, so the artifact is stable across runs over
    # identical data -- the hazard every sort in this package guards
    rank = lambda d: sorted(  # noqa: E731
        ((n, k) for k, n in d.items()), key=lambda t: (-t[0], t[1]))[:top]
    return counts, rank(conflicts), rank(alt_labels)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    """Measure co-registration off the extract on disk and print the headlines.

    Read-only. Three files opened, none written, nothing proposed, no database
    touched. It exists so every figure this module's docstring states can be
    re-derived by anyone in one command, and so the excluded population is
    printed EVEN AT ZERO.
    """
    d = Path(extract_dir)
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")

    table = co_registration(membership, assays, nodes)
    untyped = untyped_registration_samples(membership, nodes)

    counts: dict[str, int] = defaultdict(int)
    for rate, pop in table.values():
        counts[compat_band(rate, pop)] += 1
    print(f"co-registration over {len(table):,} reachable ordered (type, "
          f"registered, proposed) pairs")
    print("by band, printed at zero as well:")
    for band in S.COMPAT_BANDS:
        print(f"  {band:<18} {counts[band]:>8,}   establishes "
              f"{band_establishes(band)}")

    print("the two pairs this test was built to separate:")
    for key in (("D.IMG", 127, 145), ("D.IMG", 145, 127),
                ("PAV", 56, 74), ("PAV", 74, 56)):
        hit = table.get(key)
        if hit is None:
            print(f"  {str(key):<24} absent: the proposed assay is unreachable "
                  "for this type, which is the gate's ruling and not a rate")
            continue
        rate, pop = hit
        print(f"  {str(key):<24} rate {rate:.3f} over {pop:>6,} samples of the "
              f"type -> {compat_band(rate, pop)}")

    print(f"NOTE: {len(untyped)} registered sample(s) have no node row and so no "
          f"type; they reach no cell, in the numerator or the denominator: "
          f"{untyped[:10]}" + (" ..." if len(untyped) > 10 else ""))

    _census(Path(out_dir), membership, assays, nodes, table)
    print("a rate of 0.000 on a REACHABLE, well-supported pair means the two "
          "assays are ALTERNATIVE LABELS a curator chooses between. It is not a "
          "contradiction and it proposes nothing.")
    print("nothing was written, and this module proposes no membership change")
    return 0


def _census(out: Path, membership, assays, nodes, table) -> None:
    """Print the counter-evidence census, or say why it could not be computed.

    Split out of `main` because it needs two files `main`'s other half does not
    -- `claims.parquet` and `vocabulary.csv`, which are stage B outputs rather
    than extract inputs -- and a co-registration table is still worth printing
    on an extract that has not been through stage B. Absence is REPORTED and
    never silent, per the house rule.
    """
    from . import gate as G, vocabulary as V

    missing = [f for f in ("claims.parquet", "vocabulary.csv")
               if not (out / f).exists()]
    if missing:
        print(f"NOTE: the counter-evidence census needs {missing} under {out} "
              "and they are not there, so it was NOT computed. Run "
              "`python -m assay_hygiene.gate` first.")
        return

    claims = pd.read_parquet(out / "claims.parquet")
    vocab = V.load_vocabulary(out / "vocabulary.csv")
    type_reg = type_registration_index(membership, assays, nodes)
    gated = G.gate_claims(claims, vocab, type_reg, G.sample_type_index(nodes))
    counts, conflicts, alt_labels = counter_evidence_census(
        gated, table, registered_internal(membership, assays),
        sample_type_sets(nodes))

    print("counter-evidence census, over (gated claim, sample type) rows that "
          "reach a mode, on a sample registered somewhere and NOT already "
          "registered in the claimed assay:")
    for key in CENSUS_KEYS:
        share = f"{100 * counts[key] / counts['rows']:5.1f}%" if counts["rows"] else "    --"
        print(f"  {key:<28} {counts[key]:>8,}  {share}")
    print("  the two conflict counts are DIFFERENT numbers: the first is any "
          "positive winning rate, the second is only the rows banded "
          "BAND_ROUTINE, which are the ones that say 'propose X'.")
    print("top conflicts -- the row proposes X while a well-supported zero says "
          "X is an alternative label for something the sample HOLDS:")
    for n, (stype, proposed, winner, alt) in conflicts:
        print(f"  {n:>6,}  {stype:<7} propose {proposed:<4} winner {winner:<4} "
              f"rate {table[(stype, winner, proposed)][0]:.3f} over "
              f"{table[(stype, winner, proposed)][1]:>6,}  |  ZERO against {alt} "
              f"over {table[(stype, alt, proposed)][1]:>6,}")
    print("top self-consistent alternative labels -- the row already reads "
          "CLS_ALT_LABEL and the column names WHAT it duplicates:")
    for n, (stype, proposed, alt) in alt_labels:
        print(f"  {n:>6,}  {stype:<7} propose {proposed:<4} is an alt label for "
              f"{alt} over {table[(stype, alt, proposed)][1]:>6,}")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
