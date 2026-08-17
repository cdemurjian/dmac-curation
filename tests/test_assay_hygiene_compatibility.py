# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Task 4: the co-registration test, and what a zero rate actually means.

WHY THIS FILE EXISTS, stated once. Increment 1 reported 866 "contradictions".
Reviewing the 51 that survived the FIRST correction, 45 were found to name
correct assays -- alternative labels, not contradictions: D.IMG images sit in
127 Tissue Imaging or in 145 Histopathology, never both, because a curator picks
one, and 145 D.IMG samples are registered in Histopathology.

**THAT 45/51 WAS PRODUCED BY `scripts/measure_absence_vs_contradiction.py`, NOT
BY THE MODULE UNDER TEST, AND ITS SCOPE IS NOT THIS MODULE'S.** That script types
samples by the uuid prefix in `samples.parquet`, drops membership rows whose
assay has no junction row (the MAPPABLE-only definition of "registered", the same
one that understated the Mode 2 ceiling by 227 and 1,098), and takes lineage over
`childof.parquet` rather than DERIVED_FROM. It is the OBSERVATION that motivated
this test and never a figure these tests reproduce. Every figure asserted below
is measured on this module's own rule, typing samples off `nodes.type` and
counting ANY membership row as registered.

An earlier version of this paragraph said "the first TWO corrections", which is
wrong and disagreed with `compatibility.py`: the 45/51 finding IS the second
correction, so the 51 survived the first one only.

The first draft of this task's plan called a zero co-registration rate a
contradiction. It is not one, and
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
from assay_hygiene import audit as A  # noqa: E402
from assay_hygiene import compatibility as K  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"


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

    got = K.best_co_registration("CEL", {21, 22, 23}, 24, table)
    rate, pop, winner = got.rate, got.support, got.registered_assay_id
    assert winner == 23
    assert (rate, pop) == (0.90, 40)
    # nothing here is a well-supported zero, so there is no counter-evidence
    assert (got.alt_label_assay_id, got.alt_label_support) == (None, 0)

    # what the three wrong rules would have chosen, computed off the table
    by_support = max([21, 22, 23], key=lambda a: table[("CEL", a, 24)][1])
    by_id = min([21, 22, 23])
    by_iteration = next(iter({21, 22, 23}))
    assert by_support == by_id == by_iteration == 21 != winner
    assert K.compat_band(rate, pop) == S.BAND_ROUTINE
    assert K.compat_band(*table[("CEL", 21, 24)]) == S.BAND_SOMETIMES, (
        "the losing candidate bands differently, so the choice is material")

    # The winner has somewhere to go on the finding row, and it is one of the
    # sample's OWN registrations -- so an operator reads it against the
    # `registered_internal_assay_titles` already on that row instead of guessing
    # which of several registrations produced 0.90. Returning a winner with no
    # column to put it in is how it gets discarded by one consumer of three.
    assert winner in {21, 22, 23}
    assert "co_reg_registered_internal_assay_id" in S.FINDING_COLUMNS


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

    got = K.best_co_registration("TIS", {11}, 14, table)
    assert got == (0.0, 0, None, None, 0)
    assert K.compat_band(got.rate, got.support) == S.BAND_NO_SUPPORT
    assert K.compat_band(got.rate, got.support) != S.BAND_NEVER
    # ...and no counter-evidence is manufactured out of the empty population
    assert got.alt_label_assay_id is None and got.alt_label_support == 0

    # a type nobody in this world carries: same answer, still not BAND_NEVER
    assert K.best_co_registration("NOPE", {11, 12}, 13, table) == (0.0, 0, None,
                                                                   None, 0)


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


def test_a_well_supported_zero_survives_the_best_of_and_names_what_it_opposes():
    """The counter-evidence a best-of rate would otherwise discard.

    WORLD C is the shape the reviewer described. A sample holds 25, 31 and 32
    and is proposed X=33.

        pop(CON,25) =  50, n_both(25,33) =   0  -> 0.000, BAND_NEVER
        pop(CON,31) = 200, n_both(31,33) =   0  -> 0.000, BAND_NEVER
        pop(CON,32) =  40, n_both(32,33) =  36  -> 0.900, BAND_ROUTINE

    So the winner is 32 at 0.900 and the row says CLS_ABSENCE_COMPAT, "the
    absence is the anomaly, propose 33" -- while 200 samples of this type say 33
    never co-occurs with 31, which this sample HOLDS. That zero is the evidence
    that 33 and 31 are alternative labels and the proposal may be adding a
    synonym to a sample that already carries the thing.

    THE THREE IDS ARE CHOSEN SO THAT EVERY WRONG RULE ANSWERS 25 AND THE RIGHT
    ONE ANSWERS 31. Two earlier versions of this test could not see a
    first-wins rule: with `{31, 32, 34}` CPython iterates `[32, 34, 31]`, so the
    first well-supported zero encountered was already the correct answer and
    deleting the comparison entirely survived. Here `{25, 31, 32}` iterates
    `[32, 25, 31]`, so:

        first zero in iteration order   25   WRONG
        smallest population             25   WRONG
        lowest assay id                 25   WRONG
        LARGEST POPULATION              31   correct

    All four are computed off the frame below, never typed in, and the
    iteration-order simulation is the same one the sibling winner test performs
    with `next(iter(...))`. The counter-evidence side had no such simulation
    until the reviewer proved the omission by running the mutant.

    THE WINNER AND THE COUNTER-EVIDENCE ALSO DISAGREE ON EVERY FIELD. Winner 32
    against opponent 31; support 40 against population 200; rate 0.9 against
    0.0. A single-value collapse -- the shape this function had before
    2026-08-17 -- cannot express any of it.

    IT DOES NOT RE-CLASSIFY THE ROW, and this test pins that too. The band still
    reads BAND_ROUTINE and `band_establishes` still reads CLS_ABSENCE_COMPAT,
    because `compat_band` bands the WINNER. Whether a populated counter-evidence
    column should demote the classification is a ruling Tasks 5 and 6 own, and
    asserting today's behaviour is what makes that change visible when they make
    it.
    """
    nodes, membership = _population([
        ("CON", 50, [25]),           # a well-supported zero: SMALL pop, LOW id
        ("CON", 200, [31]),          # a well-supported zero: LARGE pop, HIGH id
        ("CON", 36, [32, 33]),       # 36 of the 40 in 32 are also in X
        ("CON", 4, [32]),
        ("CON", 40, [33]),           # X is reachable for the type in its own right
    ])
    assays = _assays(25, 31, 32, 33)
    table = K.co_registration(membership, assays, nodes)
    held = {25, 31, 32}

    assert table[("CON", 25, 33)] == (0.0, 50)
    assert table[("CON", 31, 33)] == (0.0, 200)
    assert table[("CON", 32, 33)] == (0.90, 40)
    assert K.compat_band(*table[("CON", 25, 33)]) == S.BAND_NEVER
    assert K.compat_band(*table[("CON", 31, 33)]) == S.BAND_NEVER
    assert K.compat_band(*table[("CON", 32, 33)]) == S.BAND_ROUTINE

    got = K.best_co_registration("CON", held, 33, table)

    # the winner is unchanged: the best-rate rule is plan-mandated
    assert (got.rate, got.support, got.registered_assay_id) == (0.90, 40, 32)
    # ...and the STRONGEST counter-evidence survives beside it, with its
    # population.
    assert got.alt_label_assay_id == 31
    assert got.alt_label_support == 200

    # the three wrong rules, each computed off the frame
    zeros = {a: table[("CON", a, 33)][1] for a in held
             if K.compat_band(*table[("CON", a, 33)]) == S.BAND_NEVER}
    by_iteration = next(a for a in held if a in zeros)
    by_smallest = min(zeros, key=lambda a: zeros[a])
    by_lowest_id = min(zeros)
    assert by_iteration == by_smallest == by_lowest_id == 25, (
        "the fixture must make every wrong rule answer 25, or it cannot "
        "discriminate the right one")
    assert got.alt_label_assay_id != by_iteration, (
        "a first-wins rule -- deleting the comparison entirely -- would answer "
        "25, and this is the assertion two earlier fixtures could not make")

    # every field disagrees, so no single-value collapse can stand in for this
    assert got.registered_assay_id != got.alt_label_assay_id
    assert got.support != got.alt_label_support
    assert got.rate != table[("CON", got.alt_label_assay_id, 33)][0]

    # THE CLASSIFICATION IS NOT CHANGED BY THIS TASK, asserted here so the change
    # is visible when Tasks 5/6 make it. An edit on 2026-08-17 left these four
    # lines attached to the NEXT test in the file while this docstring went on
    # claiming them -- no coverage was lost, but the guard Tasks 5 and 6 have to
    # find lived in a world named for something else.
    band = K.compat_band(got.rate, got.support)
    assert band == S.BAND_ROUTINE
    assert K.band_establishes(band) == S.CLS_ABSENCE_COMPAT

    # the row has somewhere to put both halves
    assert "co_reg_alt_label_internal_assay_id" in S.FINDING_COLUMNS
    assert "co_reg_alt_label_pop" in S.FINDING_COLUMNS


def test_two_equally_supported_zeros_break_to_the_lowest_assay_id():
    """The counter-evidence tie-break, which had no test at all.

    `best_co_registration` documents that its tie-breaks exist so the artifact a
    curator diffs does not change between runs under set iteration order. The
    WINNER's tie-break is exercised by
    `test_a_sample_in_three_assays_yields_the_best_rate_and_this_names_the_winner`;
    the counter-evidence's was asserted nowhere, so a highest-id-on-tie mutation
    was uncaught across the whole file.

    Two zeros, EQUAL populations of 60, so population cannot separate them and
    only the id rule can. The ids are chosen so the tie-break disagrees with
    iteration order too: `{33, 34, 40}` iterates `[40, 33, 34]`, so the first
    zero encountered is 40 while the answer is 33.

        first zero in iteration order   40   WRONG
        highest assay id               40   WRONG
        LOWEST ASSAY ID                33   correct
    """
    nodes, membership = _population([
        ("TIE", 60, [40]),           # a well-supported zero, HIGHER id
        ("TIE", 60, [33]),           # a well-supported zero, LOWER id, same pop
        ("TIE", 36, [34, 35]),       # the winner, 36 of 40
        ("TIE", 4, [34]),
    ])
    table = K.co_registration(membership, _assays(33, 34, 35, 40), nodes)
    held = {33, 34, 40}

    assert table[("TIE", 40, 35)] == table[("TIE", 33, 35)] == (0.0, 60), (
        "the two populations must be EQUAL, or this is not a tie")
    assert table[("TIE", 34, 35)] == (0.90, 40)

    got = K.best_co_registration("TIE", held, 35, table)
    assert (got.rate, got.registered_assay_id) == (0.90, 34)
    assert got.alt_label_assay_id == 33
    assert got.alt_label_support == 60

    zeros = [a for a in held
             if K.compat_band(*table[("TIE", a, 35)]) == S.BAND_NEVER]
    assert next(a for a in held if a in zeros) == 40 != got.alt_label_assay_id, (
        "a first-wins rule would answer 40")
    assert max(zeros) == 40 != got.alt_label_assay_id, (
        "a highest-id-on-tie rule would answer 40")
    assert got.alt_label_assay_id == min(zeros)


def test_a_thinly_supported_zero_is_not_counter_evidence():
    """BAND_NO_SUPPORT is not BAND_NEVER, in the counter-evidence too.

    The distinction `_schema` declares BAND_NO_SUPPORT for applies on BOTH sides
    of the row. A zero over 29 samples is noise, and reporting it as "these two
    are alternative labels" would manufacture counter-evidence out of an empty
    population -- the same error, one column over, and the place it would next
    appear now that the winner is guarded against it.

    THE GUARD IS ONE SAMPLE. The two worlds differ only in the size of the zero
    population, 29 against 30, so nothing but the support can have moved the
    answer. `best_co_registration` spells this `compat_band(...) == BAND_NEVER`
    rather than comparing to the floor itself, which is what keeps the only
    comparison against `MIN_CO_REG_SUPPORT` inside `compat_band`.
    """
    floor = S.MIN_CO_REG_SUPPORT
    nodes, membership = _population([
        ("THIN", floor - 1, [31]), ("THIN", 36, [32, 33]), ("THIN", 4, [32]),
        ("FAT", floor, [31]), ("FAT", 36, [32, 33]), ("FAT", 4, [32]),
    ])
    table = K.co_registration(membership, _assays(31, 32, 33), nodes)

    assert table[("THIN", 31, 33)] == (0.0, floor - 1)
    assert table[("FAT", 31, 33)] == (0.0, floor)

    thin = K.best_co_registration("THIN", {31, 32}, 33, table)
    fat = K.best_co_registration("FAT", {31, 32}, 33, table)

    # identical winners, so only the counter-evidence can differ
    assert (thin.rate, thin.support, thin.registered_assay_id) == \
           (fat.rate, fat.support, fat.registered_assay_id)

    assert (thin.alt_label_assay_id, thin.alt_label_support) == (None, 0), (
        "a zero over an unreadable population is noise, not an alternative "
        "label")
    assert (fat.alt_label_assay_id, fat.alt_label_support) == (31, floor)


# --- the census that justifies the two counter-evidence columns ---------------


def _gated(*rows):
    """A GATE_COLUMNS frame from (sample_id, internal_assay_id, gate_failures).

    Only the three columns `counter_evidence_census` reads carry meaning; the
    rest are filled so the frame matches its declared contract. `gate_failures`
    is the column `gate.reaches_modes` rules on -- never `gate`, which holds only
    the most severe outcome.
    """
    return pd.DataFrame(
        [(sid, f"U-{sid}", "CEN", iaid, f"Assay {iaid}", "Type", "t",
          (fails.split(";")[0] if fails else S.GATE_PASS), fails, "",
          100, 100, 0.99, S.P_LEARNED, "Type/t", "", 1)
         for sid, iaid, fails in rows],
        columns=G.GATE_COLUMNS,
    )


def _census_world():
    """A world where every census outcome is reached by exactly one sample.

        pop(CEN,25) =  55  zero against 33   -> counter-evidence, SMALL
        pop(CEN,31) = 203  zero against 33   -> counter-evidence, LARGE
        pop(CEN,26) =  41  10 also in 33     -> 0.244, BAND_SOMETIMES
        pop(CEN,32) =  44  36 also in 33     -> 0.818, BAND_ROUTINE

    THE `BAND_SOMETIMES` WINNER (26) IS WHAT SEPARATES THE TWO CONFLICT SENSES.
    Without it every conflicted row in this world bands ROUTINE, so
    `conflicts_any_band` and `conflicts_at_band_routine` are forced equal and
    the collapse mutant -- computing the loose count with the strict test -- is
    invisible. Measured: with 26 absent the mutant produced byte-identical
    counts. That is the exact distinction `CENSUS_KEYS` was split to preserve,
    and only the skipif-guarded real-extract test killed it, so it went
    unguarded on any clone without the gitignored extract.
    """
    nodes, membership = _population([
        ("CEN", 50, [25]),
        ("CEN", 200, [31]),
        ("CEN", 10, [26, 33]),         # 10 of 41 -> a BAND_SOMETIMES winner
        ("CEN", 30, [26]),
        ("CEN", 36, [32, 33]),
        ("CEN", 4, [32]),
        ("CEN", 40, [33]),
    ])
    extra_nodes, extra_membership = _population([
        ("CEN", 1, [25, 31, 32]),      # 9001 conflict at ROUTINE, clean gate
        ("CEN", 1, [25, 31, 32]),      # 9002 conflict at ROUTINE, FLOOR failure
        ("CEN", 1, [25, 31, 32]),      # 9003 BLOCKED, must not be counted
        ("CEN", 1, [25]),              # 9004 winner is itself a zero
        ("CEN", 1, [32]),              # 9005 no counter-evidence at all
        ("CEN", 1, [33]),              # 9006 already holds the claim
        ("CEN", 1, [25, 26]),          # 9007 conflict at SOMETIMES, NOT ROUTINE
    ], start=9001)
    # 9009 is registered NOWHERE, so it needs a node row and no membership row.
    # `_population` hands ids out in ONE ascending run and consumed 9001-9007
    # above, so the next free id is 9008; 9009 is used to leave an obvious gap
    # rather than to abut the block.
    extra_nodes = pd.concat(
        [extra_nodes, pd.DataFrame([("CEN-9009", 9009, "CEN")],
                                   columns=S.NODES_COLUMNS)], ignore_index=True)
    return (pd.concat([nodes, extra_nodes], ignore_index=True),
            pd.concat([membership, extra_membership], ignore_index=True),
            _assays(25, 26, 31, 32, 33))


def test_the_census_counts_only_rows_a_finding_could_actually_be_written_for():
    """Each of the four population rules excludes a sample this world contains.

    THE MEASUREMENT THAT JUSTIFIED A SCHEMA CHANGE HAS TO BE COMPUTABLE.
    `co_reg_alt_label_internal_assay_id` and `co_reg_alt_label_pop` were added
    to `FINDING_COLUMNS` on the strength of "5.5% of rows are conflicts" and
    nothing in the tree computed it -- the same standing this package refused
    for the Mode 2 ceiling, where two prose readings disagreed and neither could
    be re-derived.

    THE GUARD IS THAT ALL FIVE COUNTS DIFFER, and that each excluded sample is
    excluded by a DIFFERENT rule:

        9001  conflict, winner bands ROUTINE      counted in BOTH conflict senses
        9002  the same, plus GATE_LOW_SUPPORT     counted -- a tuned floor MARKS
                                                  and does not block, so dropping
                                                  it would silently apply the
                                                  blocking rule this package
                                                  spent a task removing
        9003  GATE_UNREACHABLE                    excluded, rule 1
        9004  winner is itself a well-supported   counted, and it is the
              zero                                self-consistent bucket
        9005  no zero among its registrations     counted in `rows` only
        9006  already registered in the claim     excluded, rule 3
        9007  conflict, winner bands SOMETIMES    counted in the LOOSE sense
                                                  only -- the row that makes the
                                                  two conflict counts differ
        9009  registered nowhere (Mode 1)         excluded, rule 2

    A rule that admitted 9003, 9006 or 9009, or dropped 9002 or 9007, moves a
    count that no other row can restore.

    THREE OF THE FOUR POPULATION RULES EXCLUDE A SAMPLE HERE; the fourth cannot.
    Rule 4 -- one row per (claim, TYPE) -- is a MULTIPLICITY rule and excludes
    nothing by construction, so no sample can demonstrate it by absence. It is
    exercised instead by
    `test_a_sample_typed_under_two_nodes_counts_under_both_types`, which shows a
    dual-typed sample counting under both. An earlier version of this docstring
    said all four rules exclude a sample, which overstated by one.
    """
    nodes, membership, assays = _census_world()
    table = K.co_registration(membership, assays, nodes)
    registered = A.registered_internal(membership, assays)
    types = G.sample_type_sets(nodes)

    gated = _gated(
        (9001, 33, ""),
        (9002, 33, S.GATE_LOW_SUPPORT),
        (9003, 33, S.GATE_UNREACHABLE),
        (9004, 33, ""),
        (9005, 33, ""),
        (9006, 33, ""),
        (9007, 33, ""),
        (9009, 33, ""),
    )
    counts, conflicts, alt_labels = K.counter_evidence_census(
        gated, table, registered, types)

    assert set(counts) == set(K.CENSUS_KEYS)
    assert counts["rows"] == 5                        # 9001 9002 9004 9005 9007
    assert counts["rows_with_counter_evidence"] == 4  # ...minus 9005
    assert counts["conflicts_any_band"] == 3          # 9001 9002 9007
    assert counts["conflicts_at_band_routine"] == 2   # ...minus 9007, SOMETIMES
    assert counts["self_consistent_alt_labels"] == 1  # 9004
    assert len(set(counts.values())) == 5, (
        "ALL FIVE counts must differ, or a rule could move one unseen. An "
        "earlier version of this world conceded 4 here while the docstring "
        "claimed 5, and the count it could not separate was exactly the pair "
        "CENSUS_KEYS was split to preserve.")
    assert counts["conflicts_any_band"] != counts["conflicts_at_band_routine"], (
        "9007's winner bands SOMETIMES, so it is a conflict in the loose sense "
        "and not in the strict one; without it the collapse mutant -- computing "
        "the loose count with the strict test -- is invisible")

    # the blocked row is the one a `gate == GATE_PASS` test would ALSO have
    # dropped 9002 for; this asserts the correct rule, not the convenient one
    blocked = K.counter_evidence_census(
        _gated((9002, 33, S.GATE_UNREACHABLE)), table, registered, types)[0]
    kept = K.counter_evidence_census(
        _gated((9002, 33, S.GATE_LOW_SUPPORT)), table, registered, types)[0]
    assert blocked["rows"] == 0 and kept["rows"] == 1, (
        "GATE_LOW_SUPPORT marks and must not block; GATE_UNREACHABLE blocks")

    # the patterns name the winner AND the opponent, and they differ
    assert conflicts == [(2, ("CEN", 33, 32, 31))]
    assert alt_labels == [(1, ("CEN", 33, 25))]
    assert conflicts[0][1][2] != conflicts[0][1][3]


@pytest.mark.skipif(not (EXTRACT / "membership.parquet").exists()
                    or not (ARTIFACTS / "claims.parquet").exists(),
                    reason="the extract and stage B outputs are gitignored")
def test_the_census_reproduces_the_figures_that_justified_the_two_columns():
    """7,831 / 5,839 / 625 / 428, and the 408 that are one known-bad mapping.

    These four numbers are why `co_reg_alt_label_internal_assay_id` and
    `co_reg_alt_label_pop` exist. They appeared only as prose in a report until
    2026-08-17; this is the assertion that makes them re-derivable, and it fails
    if the population definition drifts.

    408 of the 428 conflicts are ONE pattern and it is the spec's own flagship
    vocabulary defect: DNA samples proposed 24 DNA Extraction through
    `Type: Illumina Library` (purity 0.707, 212 of 250 compat flags), whose
    winner is 64 Short Read Sequencing at 0.797 over 5,437 while 173 cDNA
    Synthesis -- which the sample already holds -- never co-registers with 24
    over 420 samples. The counter-evidence points at rows the spec identified as
    wrong by a completely different route, which is the strongest evidence
    available that it is measuring something real.
    """
    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")
    nodes = pd.read_parquet(EXTRACT / "nodes.parquet")
    claims = pd.read_parquet(ARTIFACTS / "claims.parquet")
    vocab = V.load_vocabulary(ARTIFACTS / "vocabulary.csv")

    table = K.co_registration(membership, assays, nodes)
    gated = G.gate_claims(claims, vocab,
                          G.type_registration_index(membership, assays, nodes),
                          G.sample_type_index(nodes))
    counts, conflicts, alt_labels = K.counter_evidence_census(
        gated, table, A.registered_internal(membership, assays),
        G.sample_type_sets(nodes))

    assert counts["rows"] == 7_831
    assert counts["rows_with_counter_evidence"] == 5_839
    assert counts["conflicts_any_band"] == 625
    assert counts["conflicts_at_band_routine"] == 428
    assert counts["self_consistent_alt_labels"] == 5_214

    # the two conflict senses are DIFFERENT numbers, which is why they are two
    # keys; a write-up quoted one for the other before they were named apart
    assert counts["conflicts_any_band"] != counts["conflicts_at_band_routine"]

    # 408 of the 428 are the Illumina-Library mapping the spec already flags
    assert conflicts[0] == (408, ("DNA", 24, 64, 173))
    assert table[("DNA", 64, 24)] == pytest.approx((0.797, 5437), abs=1e-3)
    assert table[("DNA", 173, 24)] == (0.0, 420)
    assert sum(n for n, _ in conflicts[:2]) == 428, (
        "the top two patterns account for every conflict")

    # and the largest self-consistent bucket names what the proposal duplicates
    assert alt_labels[0] == (1_755, ("D.IMG", 138, 37))
    assert table[("D.IMG", 37, 138)] == (0.0, 8179)
