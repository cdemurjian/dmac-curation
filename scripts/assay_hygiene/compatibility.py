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
it is the reason this module exists. Increment 1 reported 866 "contradictions";
measurement showed 45 of the 51 that survived the first correction name CORRECT
assays. D.IMG images sit in 127 Tissue Imaging OR in 145 Histopathology, never
both, because a curator picks one -- and 145 D.IMG samples ARE registered in
Histopathology, so the pair is reachable in both directions and the gate passes
the claim. Measured 2026-08-17 over the real extract, `(D.IMG, 127, 145)` reads
0.000 over 2,035 samples of the type. Nothing is wrong with those registrations.

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


def best_co_registration(
    sample_type: str,
    registered_assay_ids,
    proposed_assay_id: int,
    table: dict[tuple[str, int, int], tuple[float, int]],
) -> tuple[float, int, int | None]:
    """-> (rate, support, the registered assay that produced them).

    THE COLLAPSE LIVES HERE AND NOT IN EACH CONSUMER. `FINDING_COLUMNS` carries
    ONE `co_reg_rate` / `co_reg_pop` / `compat_band` triple per row and a row is
    per (sample, proposed assay), while a sample registered in several assays
    offers one rate per registered assay -- up to 7 on the real extract. Two
    consumers each inventing a collapse is the same class of defect as two
    definitions of "registered", which has now produced three wrong figures on
    this branch.

    THE BEST RATE WINS, because any registered assay that routinely coexists
    with the proposed one supports the proposal, and a sample's other
    registrations do not weaken evidence they say nothing about. The winner is
    returned rather than discarded so `evidence_summary` can name which
    registration the rate was measured against; without it a finding row states
    a rate whose denominator's assay appears nowhere on the row, and the
    operator cannot audit the number they are being asked to approve.

    Ties break on the larger support and then on the LOWEST assay id. Both are
    stable under any iteration order; a bare `max` over a set would make the
    artifact a curator diffs change between runs on identical data, which is the
    hazard `precedent.mine_precedent` and `audit.audit_contradictions` both sort
    against.

    A REGISTERED ASSAY WITH NO KEY CONTRIBUTES NOTHING rather than a zero. A
    missing key means the proposed assay is unreachable for this type, which is
    `GATE_UNREACHABLE` and not a measured absence of coexistence; see
    `co_registration`.

    RETURNS `(0.0, 0, None)` WHEN NOTHING REACHES A POPULATION, and the zero
    rate is safe only because the zero support rides beside it and `compat_band`
    tests support FIRST. Banded, that pair reads `BAND_NO_SUPPORT`. Were the
    order reversed it would read `BAND_NEVER` -- "these assays never coexist" --
    asserted on no population at all.

    The caller drops a proposal for an assay the sample already holds, as
    `lineage.neighbour_registers` does; nothing here can manufacture one,
    because `co_registration` emits no diagonal.
    """
    best: tuple[float, int, int] | None = None
    for r in registered_assay_ids:
        hit = table.get((sample_type, int(r), int(proposed_assay_id)))
        if hit is None:
            continue
        rate, pop = hit
        key = (rate, pop, -int(r))
        if best is None or key > (best[0], best[1], -best[2]):
            best = (rate, pop, int(r))
    return best if best is not None else (0.0, 0, None)


def main(extract_dir: str = "assay-hygiene/extract") -> int:
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
    print("a rate of 0.000 on a REACHABLE, well-supported pair means the two "
          "assays are ALTERNATIVE LABELS a curator chooses between. It is not a "
          "contradiction and it proposes nothing.")
    print("nothing was written, and this module proposes no membership change")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
