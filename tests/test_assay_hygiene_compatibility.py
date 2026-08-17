# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Task 4: the co-registration test, and what a zero rate actually means.

WHY THIS FILE EXISTS, stated once. Increment 1 reported 866 "contradictions".
Measurement showed 45 of the 51 that survived the first two corrections are
ALTERNATIVE LABELS: D.IMG images sit in 127 Tissue Imaging or in 145
Histopathology, never both, because a curator picks one, and 145 D.IMG samples
are registered in Histopathology. The first draft of this task's plan called a
zero co-registration rate a contradiction. It is not one, and
`test_a_zero_rate_on_a_reachable_pair_is_an_alternative_label_and_never_an_error`
is the regression for exactly that mislabelling.

EVERY GUARD IN THIS FILE READS ITS EXPECTED VALUE OFF THE FRAME AND ALSO
SIMULATES THE WRONG RULE BY HAND. Three mutation harnesses on this branch have
produced false greens and one regression test shipped twice unable to
discriminate the bug it was written to catch. A test that asserts 0.6667 proves
only that the code produced 0.6667; a test that also computes what a symmetric
rule, a row-counting rule or a first-wins rule would have produced, and asserts
those DIFFER, proves the rule under test is the one running.

THE TWO REPORTING NUMBERS ARE READ HERE FOR BANDING AND FOR NOTHING ELSE.
`compat_band` assigns a label to a measured rate. Nothing in `compatibility.py`
uses `MIN_CO_REG_SUPPORT` or `CO_OCCUR_BAND` to decide whether a row reaches a
mode -- that is `gate.blocks_mode` and it is the only place blocking lives.
`tests/test_assay_hygiene_schema.py::test_the_two_reporting_numbers_gate_nothing`
names this module as the one approved reader and keeps the ban on every other.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import compatibility as K  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"


# --- fixture plumbing --------------------------------------------------------
#
# The two id spaces are kept VISIBLY apart: a seek `assays.id` is the internal
# id plus 1000 here, so a test (or an implementation) that reads
# `membership.assay_id` as an internal id looks up an assay in the 1000s and
# finds nothing, instead of finding a populated, wrong cell. That is this
# package's signature hazard and the fixture is shaped to make it loud.

SEEK_OFFSET = 1000


def _assays(*internal_ids, extra_records=()):
    """One seek assay record per internal id, all fully junctioned.

    `extra_records` adds (seek_id, internal_id) pairs so a single internal assay
    can be reached through TWO seek records, which is how a sample acquires two
    membership rows naming one internal assay. That is the shape the support
    count has to collapse.
    """
    rows = [
        (i + SEEK_OFFSET, f"Assay {i}", 3, 2, 1, 10, "P", i, f"Assay {i}")
        for i in internal_ids
    ]
    rows += [
        (seek, f"Assay {i} (second record)", 3, 2, 1, 10, "P", i, f"Assay {i}")
        for seek, i in extra_records
    ]
    return pd.DataFrame(rows, columns=S.ASSAY_COLUMNS)


def _population(spec, start=1):
    """(nodes, membership) from [(sample_type, n, [internal ids]), ...].

    Sample ids are handed out in one ascending run so no two blocks collide,
    and every sample gets exactly one node row. `_nodes_extra` and
    `_membership_extra` bolt on the frames' pathological rows.
    """
    nodes, membership = [], []
    sid = start
    for stype, n, assay_ids in spec:
        for _ in range(n):
            nodes.append((f"{stype}-{sid}", sid, stype))
            for a in assay_ids:
                membership.append((sid, a + SEEK_OFFSET))
            sid += 1
    return (
        pd.DataFrame(nodes, columns=S.NODES_COLUMNS),
        pd.DataFrame(membership, columns=S.MEMBERSHIP_COLUMNS),
    )


def _world_a():
    """60 TIS in 11, 40 of them also in 12; a disjoint 30 in 13.

    Hand-traced, and every later test that names WORLD A reads these:

        pop(TIS,11) = 60   pop(TIS,12) = 40   pop(TIS,13) = 30
        n_both(11,12) = 40, n_both(11,13) = 0, n_both(12,13) = 0

        rate(TIS, 11 -> 12) = 40/60 = 0.6667 over 60
        rate(TIS, 12 -> 11) = 40/40 = 1.0000 over 40   <- always coexists
        rate(TIS, 11 -> 13) =  0/60 = 0.0000 over 60   <- never coexists
        rate(TIS, 13 -> 11) =  0/30 = 0.0000 over 30   <- never, and supported

    11 and 13 are BOTH reachable for TIS -- 60 and 30 samples of the type are
    registered in them -- so a claim naming either passes the gate's
    reachability test. That is what makes the zero rate between them an
    alternative label rather than a gate rejection wearing another hat.
    """
    nodes, membership = _population([
        ("TIS", 40, [11, 12]),
        ("TIS", 20, [11]),
        ("TIS", 30, [13]),
    ])
    return nodes, membership, _assays(11, 12, 13)


def _world_b():
    """Three registered assays reaching one proposed assay 24 at three rates.

        pop(CEL,21) = 100, n_both(21,24) =  10 -> 0.10
        pop(CEL,22) =  50, n_both(22,24) =  30 -> 0.60
        pop(CEL,23) =  40, n_both(23,24) =  36 -> 0.90

    The three rates, the three supports and the three ids all order
    DIFFERENTLY, which is what makes the best-rate rule distinguishable from a
    largest-support rule (21) and from a lowest-id rule (21). Every support
    clears the floor, so no band collapses to BAND_NO_SUPPORT and the winner is
    decided on rate alone.
    """
    nodes, membership = _population([
        ("CEL", 10, [21, 24]),
        ("CEL", 90, [21]),
        ("CEL", 30, [22, 24]),
        ("CEL", 20, [22]),
        ("CEL", 36, [23, 24]),
        ("CEL", 4, [23]),
    ])
    return nodes, membership, _assays(21, 22, 23, 24)


# --- the rate ----------------------------------------------------------------


def test_a_pair_that_always_coexists_reads_one_and_a_pair_that_never_does_reads_zero():
    """The two ends of the scale, both on populations well over the floor.

    Every 12 sample is also a 11 sample, so 12 -> 11 is 1.0; no 13 sample is
    ever a 11 sample, so 11 -> 13 is 0.0. Both denominators are read off
    `gate.type_registration_index`, the same cell the gate's reachability test
    uses, so a support that disagreed with reachability would fail here.
    """
    nodes, membership, assays = _world_a()
    table = K.co_registration(membership, assays, nodes)
    type_reg = G.type_registration_index(membership, assays, nodes)

    always_rate, always_pop = table[("TIS", 12, 11)]
    never_rate, never_pop = table[("TIS", 11, 13)]

    assert always_rate == 1.0
    assert always_pop == type_reg[("TIS", 12)] == 40
    assert never_rate == 0.0
    assert never_pop == type_reg[("TIS", 11)] == 60

    # ...and the middle of the scale is neither, so "always" and "never" are
    # answers this data can fail to give rather than the only two it has.
    mid_rate, mid_pop = table[("TIS", 11, 12)]
    assert mid_pop == 60 and abs(mid_rate - 40 / 60) < 1e-12
    assert 0.0 < mid_rate < 1.0


def test_the_rate_is_directional_because_the_denominators_differ():
    """(T,R,X) and (T,X,R) are different questions and this world separates them.

    THE GUARD IS A HAND-SIMULATED SYMMETRIC RULE. The obvious wrong
    implementation measures how often the pair co-occurs against the samples
    holding EITHER assay, which is symmetric by construction. On WORLD A that
    rule reads 40/60 in both directions, so it agrees with the correct answer in
    one direction and not the other -- a test asserting only 0.6667 would pass
    under it. Both numbers below are computed from the frame, never typed in.
    """
    nodes, membership, assays = _world_a()
    table = K.co_registration(membership, assays, nodes)

    forward_rate, forward_pop = table[("TIS", 11, 12)]
    reverse_rate, reverse_pop = table[("TIS", 12, 11)]

    assert forward_pop != reverse_pop, "the two denominators must differ here"
    assert forward_rate != reverse_rate

    # the symmetric rule, computed off the same frames
    in_11 = {int(s) for s, a in zip(membership.sample_id, membership.assay_id)
             if int(a) == 11 + SEEK_OFFSET}
    in_12 = {int(s) for s, a in zip(membership.sample_id, membership.assay_id)
             if int(a) == 12 + SEEK_OFFSET}
    symmetric = len(in_11 & in_12) / len(in_11 | in_12)
    assert symmetric == pytest.approx(forward_rate), (
        "on this fixture the symmetric rule coincides with the FORWARD "
        "direction, which is exactly why it is undetectable from that "
        "direction alone")
    assert symmetric != reverse_rate, (
        "the reverse direction is where a symmetric rule shows itself, and it "
        "is the assertion that makes this test able to fail")


def test_the_support_counts_samples_of_the_type_and_never_membership_rows():
    """One internal assay reached through two seek records is still one sample.

    `VOCAB_COLUMNS.support` counts EDGES and `n_samples` counts distinct
    samples; Task 2 found 21 of 50 single-sample terms clearing an edge floor of
    30 on that confusion. The same trap is here in another unit: a sample
    registered in one internal assay through two seek `assays` records has TWO
    membership rows, and a support that counted rows would inflate the
    denominator and deflate every rate resting on it.

    THE GUARD IS THE ROW COUNT, read off the frame. It is deliberately
    different from the sample count, so a row-counting implementation reads a
    different number rather than the same one.
    """
    nodes, membership, _ = _world_a()
    assays = _assays(11, 12, 13, extra_records=[(9011, 11)])
    # sample 1 is a TIS already registered in 11; give it a SECOND membership
    # row into the same internal assay through the other seek record
    membership = pd.concat(
        [membership, pd.DataFrame([(1, 9011)], columns=S.MEMBERSHIP_COLUMNS)],
        ignore_index=True)

    rows_into_11 = sum(
        1 for a in membership.assay_id if int(a) in (11 + SEEK_OFFSET, 9011))
    samples_in_11 = len({
        int(s) for s, a in zip(membership.sample_id, membership.assay_id)
        if int(a) in (11 + SEEK_OFFSET, 9011)})
    assert rows_into_11 == samples_in_11 + 1, (
        "the fixture must contain the duplicate this test exists to collapse")

    _, pop = K.co_registration(membership, assays, nodes)[("TIS", 11, 12)]
    assert pop == samples_in_11 == 60
    assert pop != rows_into_11


def test_a_sample_typed_under_two_nodes_counts_under_both_types():
    """`type_registration_index` counts it under both, and the numerator must too.

    A sample_id carrying two node rows that disagree on type is not
    hypothetical: 86 of them exist on the real extract and 51 disagree.
    `gate.type_registration_index` counts such a sample under BOTH types on
    purpose, because counting it under one makes reachability depend on a row
    order that is not stable across extracts. The numerator here has to follow
    the SAME rule as the denominator it divides -- if it counted the sample once
    and the denominator twice, the rate would silently halve, and if it counted
    it twice against a denominator of one the rate would exceed 1.0.

    THE GUARD IS THE **TIS** ASSERTION, and this docstring said otherwise until
    self-review. It claimed the guard was "both types read the same rate", which
    the body does not assert and which is not even true here: MUS reads 1.0 over
    1 and TIS reads 0.667 over 60. The discriminating assertion is that the TIS
    population is still 60 AFTER the sample acquires a second type. Under a
    one-type-per-sample_id rule the second node row displaces the first, TIS
    reads 59, and it is that line which fails -- the MUS assertions pass under
    both rules, because the sample lands in MUS either way. The `<= 1.0` sweep
    is the second half: it catches the mirror error, a numerator counting the
    sample under both types against a denominator counting it under one.
    """
    nodes, membership, assays = _world_a()
    # sample 1 (TIS, in 11 and 12) gains a second node row typed MUS
    nodes = pd.concat(
        [nodes, pd.DataFrame([("MUS-1", 1, "MUS")], columns=S.NODES_COLUMNS)],
        ignore_index=True)

    table = K.co_registration(membership, assays, nodes)
    type_reg = G.type_registration_index(membership, assays, nodes)

    assert type_reg[("MUS", 11)] == 1 and type_reg[("MUS", 12)] == 1
    assert table[("MUS", 11, 12)] == (1.0, 1)
    assert table[("MUS", 12, 11)] == (1.0, 1)
    # the TIS reading is untouched: the sample counts under both, not instead of
    assert table[("TIS", 11, 12)][1] == type_reg[("TIS", 11)] == 60
    assert all(rate <= 1.0 for rate, _ in table.values()), (
        "a numerator counted under a rule its denominator does not share is "
        "what pushes a rate over 1.0")


def test_a_registered_sample_with_no_node_row_is_counted_by_name_and_not_dropped():
    """It carries no type, so it can reach no cell -- and it is still reported.

    194 such samples exist on the real extract over 210 of the 214,296
    membership rows. They cannot contribute to a per-TYPE cell because they have
    no type, which is a fact about the frames rather than a decision; the house
    rule is that every excluded row is counted and reported BY NAME, and
    `gate.untyped_registration_samples` is the package's one function for it.
    This test asserts BOTH halves: that the cells do not move, and that the
    sample is named.

    THE THIRD ASSERTION IS WHAT MAKES THE FIRST ABLE TO FAIL. `after == before`
    holds under any implementation whose key space comes from
    `type_registration_index`, because an untyped sample reaches no cell there
    either -- so on its own it cannot see an implementation that gave such
    samples a synthetic type. The discriminating property is that every type in
    the table is a type some node row actually carries, which a table keyed off
    the co-occurrence counts instead would break the moment an untyped sample
    was filed under `""`.
    """
    nodes, membership, assays = _world_a()
    before = K.co_registration(membership, assays, nodes)
    membership = pd.concat(
        [membership, pd.DataFrame([(9999, 11 + SEEK_OFFSET),
                                   (9999, 12 + SEEK_OFFSET)],
                                  columns=S.MEMBERSHIP_COLUMNS)],
        ignore_index=True)
    after = K.co_registration(membership, assays, nodes)

    assert after == before, (
        "an untyped sample belongs to no type, so it can move no per-type cell")
    assert G.untyped_registration_samples(membership, nodes) == [9999], (
        "silence here is the failure: the sample left the measurement and no "
        "artifact says so")
    assert {k[0] for k in after} <= set(nodes.type), (
        "every type in the table must be a type some node row carries; a "
        "synthetic type for the untyped population would appear here")
    type_reg = G.type_registration_index(membership, assays, nodes)
    assert {(t, r) for t, r, _ in after} <= set(type_reg), (
        "every support must BE a reachability cell, which is what ties the "
        "denominator to the gate's own evidence")


def test_an_assay_unreachable_for_the_type_has_no_key_at_all():
    """A missing key is the gate's ruling, and reading it as 0.0 is the mislabel.

    No TIS sample is registered in 14, so `(TIS, 11, 14)` is not a rate of zero
    -- there is no population to measure and the gate has already stopped the
    claim as GATE_UNREACHABLE. Emitting the key with rate 0.0 would band it
    BAND_NEVER on a support of 60, which reports a vocabulary defect as an
    alternative label: a bucket named for what someone assumed was in it, for
    the fourth time on this branch.

    THE FIXTURE REGISTERS 40 MUS SAMPLES IN 14, and that is what makes this test
    able to fail. Reachability is PER TYPE, so an assay nothing at all is
    registered in tests only "does this assay exist in the frame" -- the first
    version of this test used one, and a mutation that keyed the table on every
    assay reachable for ANY type went undetected. 14 is reachable, for MUS, and
    unreachable for TIS.

    THE GUARD names what the wrong answer would have been, off the frame.
    """
    nodes, membership, _ = _world_a()
    assays = _assays(11, 12, 13, 14)
    mus_nodes, mus_membership = _population([("MUS", 40, [14])], start=5000)
    nodes = pd.concat([nodes, mus_nodes], ignore_index=True)
    membership = pd.concat([membership, mus_membership], ignore_index=True)

    table = K.co_registration(membership, assays, nodes)
    type_reg = G.type_registration_index(membership, assays, nodes)

    assert type_reg[("MUS", 14)] == 40, "14 is reachable, but for MUS"
    assert ("TIS", 14) not in type_reg, "14 must be unreachable for TIS"
    assert ("TIS", 11, 14) not in table
    assert ("TIS", 14, 11) not in table
    # what the wrong answer would have looked like, and why it is worse than
    # absence: a well-supported BAND_NEVER, indistinguishable from D.IMG's
    # genuine alternative-label finding.
    would_have_been = K.compat_band(0.0, type_reg[("TIS", 11)])
    assert would_have_been == S.BAND_NEVER


def test_the_diagonal_is_absent_because_a_sample_already_holding_it_lacks_nothing():
    """(T, R, R) is not a rate of 1.0, it is not a question.

    Co-registration answers "this sample is in R and lacks X, do R and X
    coexist". Where X is R there is no absence to explain, which is the same
    guard `lineage.lineage_supports` places on a sample that already registers
    the assay. A diagonal at 1.0 would corroborate every proposal a caller made
    by mistake.
    """
    nodes, membership, assays = _world_a()
    table = K.co_registration(membership, assays, nodes)
    assert not [k for k in table if k[1] == k[2]]
    assert ("TIS", 11, 11) not in table


# --- the bands ---------------------------------------------------------------


def test_support_under_the_floor_is_no_support_and_never_never():
    """29 samples at rate 0.000 is noise. 30 is a finding. Only support differs.

    This is the distinction `_schema` declares BAND_NO_SUPPORT for: a rate of
    0.000 over four samples reported as "these never coexist" manufactures an
    alternative-label finding out of an empty population. Both worlds below
    have the IDENTICAL rate, so the band can only have moved on support.

    The floor is read off `S.MIN_CO_REG_SUPPORT` rather than typed, so the test
    tracks the constant instead of pinning today's value -- which
    `test_the_two_reporting_numbers_gate_nothing` already pins.
    """
    floor = S.MIN_CO_REG_SUPPORT
    nodes, membership = _population([
        ("THIN", floor - 1, [11]), ("THIN", 1, [12]),
        ("FAT", floor, [11]), ("FAT", 1, [12]),
    ])
    table = K.co_registration(membership, _assays(11, 12), nodes)

    thin_rate, thin_pop = table[("THIN", 11, 12)]
    fat_rate, fat_pop = table[("FAT", 11, 12)]
    assert thin_rate == fat_rate == 0.0, "the rate must be the same in both"
    assert (thin_pop, fat_pop) == (floor - 1, floor)

    assert K.compat_band(thin_rate, thin_pop) == S.BAND_NO_SUPPORT
    assert K.compat_band(fat_rate, fat_pop) == S.BAND_NEVER
    assert S.BAND_NO_SUPPORT != S.BAND_NEVER


def test_the_routine_boundary_is_inclusive_and_a_hair_under_it_is_not():
    """Exactly CO_OCCUR_BAND is ROUTINE; one sample fewer is SOMETIMES.

    THE GUARD IS THAT THE TWO POPULATIONS DIFFER BY ONE SAMPLE. A `>` where the
    band means `>=` moves only the exact-boundary case, so a test built at 0.6
    and 0.4 cannot see it. 20/40 is exactly representable in binary, so the
    boundary case is not a floating-point coincidence.
    """
    band = S.CO_OCCUR_BAND
    nodes, membership = _population([
        ("ONBND", 20, [11, 12]), ("ONBND", 20, [11]),
        ("UNDER", 19, [11, 12]), ("UNDER", 21, [11]),
    ])
    table = K.co_registration(membership, _assays(11, 12), nodes)

    on_rate, on_pop = table[("ONBND", 11, 12)]
    under_rate, under_pop = table[("UNDER", 11, 12)]
    assert on_rate == band and on_pop == 40
    assert under_rate < band and under_pop == 40

    assert K.compat_band(on_rate, on_pop) == S.BAND_ROUTINE
    assert K.compat_band(under_rate, under_pop) == S.BAND_SOMETIMES


def test_a_zero_rate_on_a_reachable_pair_is_an_alternative_label_and_never_an_error():
    """The regression for the second design error, and it is the point of Task 4.

    Increment 1 reported 866 contradictions; the operator observed that the
    survivors name CORRECT assays. 45 of 51 are alternative labels -- D.IMG
    images sit in 127 Tissue Imaging or in 145 Histopathology, never both,
    because a curator picks one, and 145 D.IMG samples ARE registered in
    Histopathology. The first draft of this task's plan called that a
    contradiction.

    THE PAIR HAS TO BE REACHABLE IN BOTH DIRECTIONS for the finding to mean
    anything, and this test asserts that first: if 13 were unreachable for TIS
    the gate would already have stopped the claim, and a zero rate would be
    reporting a vocabulary defect under a second name. It is reachable -- 30 TIS
    samples are registered in 13 -- so the zero is about the pair and not about
    the claim.
    """
    nodes, membership, assays = _world_a()
    table = K.co_registration(membership, assays, nodes)
    type_reg = G.type_registration_index(membership, assays, nodes)

    # both halves of the pair are reachable, so the gate passes the claim
    assert type_reg[("TIS", 11)] == 60 and type_reg[("TIS", 13)] == 30

    rate, pop = table[("TIS", 11, 13)]
    assert (rate, pop) == (0.0, 60)
    assert pop >= S.MIN_CO_REG_SUPPORT

    band = K.compat_band(rate, pop)
    assert band == S.BAND_NEVER
    assert K.band_establishes(band) == S.CLS_ALT_LABEL

    # ...and CLS_ALT_LABEL is a CLASS, not a rejection and not a Mode 3 flag.
    # This is the assertion the first draft would have failed.
    assert S.CLS_ALT_LABEL in S.CLASSES
    assert S.CLS_ALT_LABEL not in S.GATE_REJECTIONS
    assert S.CLS_ALT_LABEL != S.V_MODE3_FLAG
    assert not G.blocks_mode(S.CLS_ALT_LABEL), (
        "an alternative label is a finding a curator reads, not a block")


# --- collapsing a sample's several registered assays --------------------------


def test_a_sample_in_three_assays_yields_the_best_rate_and_this_names_the_winner():
    """21 -> 0.10, 22 -> 0.60, 23 -> 0.90. 23 wins, and the test says so.

    A finding row carries ONE `co_reg_rate` and one `co_reg_pop`, and a sample
    registered in three assays offers three. The collapse belongs here rather
    than in each of Tasks 5 and 6, which is the same argument that put
    "registered" in one function.

    THE GUARD IS THAT THREE PLAUSIBLE WRONG RULES ALL PICK 21. Largest support
    picks 21 (100 samples), lowest id picks 21, and first-in-iteration-order on
    a set of small ints picks 21 in CPython. Only best-rate picks 23, so the
    winner is what discriminates the rule -- the rate alone does not, and this
    test asserts both.
    """
    nodes, membership, assays = _world_b()
    table = K.co_registration(membership, assays, nodes)

    assert table[("CEL", 21, 24)] == (0.10, 100)
    assert table[("CEL", 22, 24)] == (0.60, 50)
    assert table[("CEL", 23, 24)] == (0.90, 40)

    rate, pop, winner = K.best_co_registration("CEL", {21, 22, 23}, 24, table)
    assert winner == 23
    assert (rate, pop) == (0.90, 40)

    # what the three wrong rules would have chosen, computed off the table
    by_support = max([21, 22, 23], key=lambda a: table[("CEL", a, 24)][1])
    by_id = min([21, 22, 23])
    by_iteration = next(iter({21, 22, 23}))
    assert by_support == by_id == by_iteration == 21 != winner
    assert K.compat_band(rate, pop) == S.BAND_ROUTINE
    assert K.compat_band(*table[("CEL", 21, 24)]) == S.BAND_SOMETIMES, (
        "the losing candidate bands differently, so the choice is material")


def test_a_collapse_that_reaches_no_population_reads_no_support_never_never():
    """Zero candidates must not read as a well-supported zero rate.

    `best_co_registration` returns a rate of 0.0 when nothing reaches a key,
    which is safe ONLY because it returns a support of 0 beside it and
    `compat_band` tests support BEFORE rate. If those two were the other way
    round, a sample whose registered assays are all unreachable for its type
    would be reported as "these assays never coexist" on no evidence at all --
    the same manufacture `BAND_NO_SUPPORT` exists to prevent.
    """
    nodes, membership, assays = _world_a()
    table = K.co_registration(membership, assays, nodes)

    rate, pop, winner = K.best_co_registration("TIS", {11}, 14, table)
    assert (rate, pop, winner) == (0.0, 0, None)
    assert K.compat_band(rate, pop) == S.BAND_NO_SUPPORT
    assert K.compat_band(rate, pop) != S.BAND_NEVER

    # a type nobody in this world carries: same answer, still not BAND_NEVER
    assert K.best_co_registration("NOPE", {11, 12}, 13, table) == (0.0, 0, None)


# --- against the real extract -------------------------------------------------


@pytest.mark.skipif(not (EXTRACT / "membership.parquet").exists(),
                    reason="the extract is gitignored and is not always present")
def test_the_alternative_label_and_coexistence_figures_on_the_real_extract():
    """D.IMG's 127/145 pair reads 0.000; PAV's 56/74 pair reads 0.805.

    THE POPULATIONS ARE NOT THE ONES THE BRIEF QUOTED and the difference is
    which frame supplies the sample type. The brief's 1,907 and 13,229 come from
    the uuid prefix in `samples.parquet`; this package types samples off
    `nodes.type`, per `gate.sample_type_index`, and reads 2,035 and 13,220. The
    gap decomposes exactly: 132 samples registered in 127 and typed D.IMG by the
    graph have no `samples.parquet` row at all, and 4 (D.IMG) / 9 (PAV) samples
    have a mysql row but no node row, so they carry no type here and are
    reported by `gate.untyped_registration_samples` instead.

    Both RATES are unchanged by the choice, which is what makes the finding
    robust: the alternative-label reading of D.IMG does not depend on it.
    """
    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")
    nodes = pd.read_parquet(EXTRACT / "nodes.parquet")

    table = K.co_registration(membership, assays, nodes)

    img_rate, img_pop = table[("D.IMG", 127, 145)]
    assert (img_rate, img_pop) == (0.0, 2035)
    assert K.compat_band(img_rate, img_pop) == S.BAND_NEVER
    assert K.band_establishes(S.BAND_NEVER) == S.CLS_ALT_LABEL
    # 145 D.IMG samples ARE in Histopathology, which is what makes this an
    # alternative label rather than an absence nobody has ever registered.
    assert table[("D.IMG", 145, 127)] == (0.0, 145)

    pav_rate, pav_pop = table[("PAV", 56, 74)]
    assert pav_pop == 13220
    assert round(pav_rate, 3) == 0.805
    assert K.compat_band(pav_rate, pav_pop) == S.BAND_ROUTINE
    # and it is directional on the real data too, at a materially different rate
    rev_rate, rev_pop = table[("PAV", 74, 56)]
    assert rev_pop == 10782 and round(rev_rate, 3) == 0.987
    assert rev_rate != pav_rate
