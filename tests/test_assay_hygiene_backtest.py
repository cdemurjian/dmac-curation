# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Task 7: Mode 2's backtest, and the two recovery curves it measures.

WHAT THE INSTRUMENT IS. Hide every membership row of a held-out slice of
SAMPLES, mine precedent on the induced subgraph of the samples that were kept,
run Mode 2 cold, and ask of each proposal it makes about a held-out sample:
did a curator actually put that sample in that assay. Recovery, not rate.

THE SPLIT IS BY SAMPLE AND NEVER BY EDGE. A sample fans out to many edges -- one
sample of the real extract has 1,528 children -- so an edge-level split puts the
same sample on both sides and scores memorised answers. The spec
records this as a mistake already made once on this project, which is why
`check_split` refuses a sample appearing in both halves and why
`test_a_sample_on_both_sides_of_the_split_is_refused_and_an_edge_split_makes_one`
builds the edge-level split by hand and watches it be refused.

EVERY GUARD READS ITS EXPECTED VALUE OFF THE FRAME AND ALSO SIMULATES THE WRONG
RULE BY HAND, following `tests/test_assay_hygiene_classify.py`. Nine harness
defects on this branch have produced false results. A test that asserts a count
proves only that the code produced that count; a test that also computes what the
rule it exists to reject would have produced, and asserts the two DIFFER, proves
the rule under test is the one running.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import audit as A  # noqa: E402
from assay_hygiene import backtest as B  # noqa: E402
from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402
from assay_hygiene import precedent as P  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"

# The two id spaces are kept VISIBLY apart, as in
# `tests/test_assay_hygiene_classify.py`: a seek `assays.id` is the internal id
# plus 1000, so anything reading `membership.assay_id` as an internal id looks up
# an assay in the 1000s and finds nothing instead of a populated, wrong cell.
SEEK_OFFSET = 1000


# --- the world ---------------------------------------------------------------


def _world():
    """One synthetic world whose BOTH-ENDPOINTS-REGISTERED population is the point.

    `test_assay_hygiene_classify._world2` is shaped for the opposite case: its
    proposals are DARK pairs, where a neighbour holds an assay the sample lacks.
    A backtest needs the mirror -- pairs a curator registered on BOTH endpoints,
    so that hiding one side has a known right answer -- and it needs enough edges
    per hop to place a mined rate in a chosen band. So this is a second world,
    not a widening of that one.

    THE RATES ARE MINED, NOT HAND-AUTHORED, because `backtest` mines them itself:
    that is the whole cold-run guarantee, and a fixture that injected rules would
    test a pipeline the operator will never run.
    `test_the_worlds_mined_rates_are_what_its_own_edge_counts_imply` re-derives
    every rate below from the world rather than trusting this docstring.

    Assays: internal 11, 12, 13 are junctioned in project 10 (seek
    1011/1012/1013).

    THREE BACKGROUND HOPS, every endpoint KEPT, which are the only edges the
    training set sees. Counts are stated as (n_both, n_child_only,
    n_parent_only) AFTER the one probe edge that also lands in training:

        (10, D.IMG, TIS, 11)   19, 1, 20   propagation 0.950   reverse 0.487
        (10, TIS,   PAV, 12)   19, 20, 1   propagation 0.487   reverse 0.950
        (10, MUS,   TIS, 12)    6,  4, 1   propagation 0.600   reverse 0.857

    The one probe edge in training is P9's, `c9 -> p9`, which contributes the
    single `n_child_only` on the first hop. Every other probe edge has a held-out
    endpoint and is excluded by construction.

    THE PROBES. `->` is `child -> parent`; `[H]` marks a held-out sample. Every
    held-out sample loses ALL of its membership, so it is the sample whose
    registration Mode 2 has to recover.

        P1   c1  D.IMG(11) -> p1  TIS[H](11)    ADD_PARENT [0.95,1.00]  correct
        P2   c2  D.IMG(11) -> p2  TIS[H](12)    ADD_PARENT [0.95,1.00]  wrong
        P3   c3  TIS(12)   -> p3  PAV[H](12)    ADD_PARENT [0.00,0.50)  correct
        P3b  c3b TIS(12)   -> p3b PAV[H](11)    ADD_PARENT [0.00,0.50)  wrong
        P4   c4  TIS[H](12)-> p4  PAV(12)       ADD_CHILD  [0.95,1.00]  correct
        P5   c5  TIS[H](11)-> p5  PAV(12)       ADD_CHILD  [0.95,1.00]  wrong
        P6   c6  D.IMG[H](11)->p6 TIS(11)       ADD_CHILD  [0.00,0.50)  correct
        P6b  c6b D.IMG[H](13)->p6b TIS(11)      ADD_CHILD  [0.00,0.50)  wrong
        P6c  c6c D.IMG[H](13)->p6c TIS(11)      ADD_CHILD  [0.00,0.50)  wrong
        P7   c7  MUS[H](13)-> p7  PAV(13)       ADD_CHILD  NO_RATE      correct
        P8   c8  D.IMG[H](11)->p8 TIS[H](11)    NO PROPOSAL, both blinded
        P9   c9  D.IMG(11) -> p9  TIS()         ADD_PARENT on a KEPT sample
        P10  c10 D.IMG[H](11)->s10 TIS[H](11)-> p10 PAV(11)
                                                ADD_CHILD  NO_RATE      correct,
                                                and the direction FLIPPED
        P11  c11 MUS(12)   -> p11 TIS[H](11)    ADD_PARENT [0.50,0.75)  wrong
        P12  c12 MUS[H](12)-> p12 TIS(12)       ADD_CHILD  [0.75,0.90)  correct
        P13  c13a D.IMG(11)-> s13 TIS[H](11,12) ADD_PARENT [0.95,1.00]  correct
             c13b D.IMG(13)-> s13                ADD_PARENT NO_RATE     wrong

    EVERY REQUIRED CASE, AND WHICH PROBE CARRIES IT:

      P1/P4     the plain recovery, one per direction, in the top band.
      P2/P5     A PROPOSAL WAS MADE AND THE CURATOR'S ASSAY IS A DIFFERENT ONE.
                p2 was registered in 12 and the proposal names 11; c5 was in 11
                and the proposal names 12. Scoring "a proposal was made" instead
                of "the curator assigned it" reads both as recovered, which is
                the wrong rule this fixture exists to discriminate.
      P8        both endpoints held out, so the neighbour that would have
                supported the proposal is blinded too and NOTHING is proposed.
                Two truth pairs are lost this way and both are counted by name;
                this is the honest cost of splitting by sample and it may not be
                quietly dropped from the denominator.
      P9        a proposal about a KEPT sample. Its ground truth is empty by
                construction -- `mode2_candidates` never proposes an assay a
                sample already holds, so every proposal about a kept sample names
                an assay the curator did not assign, and scoring them would
                report a precision of zero that measures nothing. Counted apart.
      P10       the direction FLIPS under blinding. In the full world s10's child
                c10 holds 11, so a curator-world direction of ADD_PARENT; c10 is
                held out too, and the kept parent p10 holds 11, so the blinded
                world proposes ADD_CHILD. Recovered, in the other direction, and
                the census says so rather than counting it as a miss or as a
                plain recovery.
      P11       the ONLY row in `[0.50,0.75)`, and it is WRONG, so that band
                reports a precision of exactly 0.0 -- which is what makes the
                EMPTY bands' null precision a different statement rather than a
                formatting choice.
      P12       a middle band that is populated and fully correct.
      P13       ONE HELD-OUT SAMPLE CARRYING BOTH OUTCOMES. s13 was registered
                in 11 and 12; one kept child holds 11, so (s13, 11) is a
                recovery, and another holds 13, so (s13, 13) is a proposal
                naming an assay the curator never assigned. Without this probe
                no held-out sample has both, and a rule that matched recovery on
                the SAMPLE while ignoring the ASSAY gives this world exactly the
                same table as the correct one -- measured, that mutation was
                caught only by the extract-backed test while the test whose name
                claims the property passed.

    Registrations a curator made on a held-out sample that NO neighbour holds are
    outside the mode's reach and are counted by name rather than scored: (p2,12),
    (p3b,11), (c5,11), (c6b,13), (c6c,13), (p11,11) and (s13,12), seven of them.

    THE EXPECTED BAND TABLE, hand-traced off the probes above and re-derived by
    `test_the_two_directions_are_scored_and_reported_apart_and_never_pooled`:

        band          ADD_PARENT               ADD_CHILD
                      rows correct precision   rows correct precision
        NO_RATE          1       0   0.000        2       2   1.000
        [0.00,0.50)      2       1   0.500        3       1   0.333
        [0.50,0.75)      1       0   0.000        0       0   EMPTY
        [0.75,0.90)      0       0   EMPTY        1       1   1.000
        [0.90,0.95)      0       0   EMPTY        0       0   EMPTY
        [0.95,1.00]      3       2   0.667        2       1   0.500

    Four of the twelve cells are EMPTY and two read 0.000, deliberately: a table
    where no band is empty cannot show that an empty band is reported as empty,
    and one where no band is 0.000 cannot show that the two are different
    statements.
    """
    nodes, membership, samples, edges = [], [], [], []
    known: dict[int, str] = {}

    def add(sid, stype, assay_ids=()):
        known[sid] = stype
        nodes.append((f"{stype}-{sid}", sid, stype))
        samples.append((sid, f"{stype}-{sid}", "{}", None, "3"))
        for a in assay_ids:
            membership.append((sid, a + SEEK_OFFSET))

    def edge(child, parent):
        edges.append((child, parent, f"{known[child]}-{child}",
                      f"{known[parent]}-{parent}", known[child], known[parent],
                      None, None, None))

    def background(base, child_type, parent_type, assay,
                   n_both, n_child_only, n_parent_only):
        """`n_both` + `n_child_only` + `n_parent_only` KEPT edges on one hop.

        THE ONE-SIDED GROUPS FAN OUT FROM A SINGLE SHARED ENDPOINT, which is what
        the real graph does -- 2,074 CometChip images declare 146 tissue parents
        each -- and is also what lets this world show the hazard the split guard
        exists for. A world whose every edge had its own two endpoints would let
        an EDGE-level split come out disjoint by accident, and the guard would
        then be asserted against a world that cannot violate it.

        The unregistered endpoint of a one-sided edge is registered in NOTHING
        rather than in another assay, so the hop carries observations for `assay`
        alone and the three counts are exactly what the miner reads.
        """
        sid = base
        for _ in range(n_both):
            add(sid, child_type, [assay]), add(sid + 1, parent_type, [assay])
            edge(sid, sid + 1)
            sid += 2
        if n_child_only:
            child = sid
            add(child, child_type, [assay])
            sid += 1
            for _ in range(n_child_only):
                add(sid, parent_type)
                edge(child, sid)
                sid += 1
        if n_parent_only:
            parent = sid
            add(parent, parent_type, [assay])
            sid += 1
            for _ in range(n_parent_only):
                add(sid, child_type)
                edge(sid, parent)
                sid += 1

    # (n_both, n_child_only, n_parent_only) BEFORE P9's edge, which adds the one
    # `n_child_only` on the first hop.
    background(1000, "D.IMG", "TIS", 11, 19, 0, 20)
    background(2000, "TIS", "PAV", 12, 19, 20, 1)
    background(3000, "MUS", "TIS", 12, 6, 4, 1)

    probes = [
        # (child, child type, child assays, parent, parent type, parent assays)
        (101, "D.IMG", [11], 201, "TIS", [11]),        # P1
        (102, "D.IMG", [11], 202, "TIS", [12]),        # P2
        (103, "TIS", [12], 203, "PAV", [12]),          # P3
        (104, "TIS", [12], 204, "PAV", [11]),          # P3b
        (105, "TIS", [12], 205, "PAV", [12]),          # P4
        (106, "TIS", [11], 206, "PAV", [12]),          # P5
        (107, "D.IMG", [11], 207, "TIS", [11]),        # P6
        (108, "D.IMG", [13], 208, "TIS", [11]),        # P6b
        (109, "D.IMG", [13], 209, "TIS", [11]),        # P6c
        (110, "MUS", [13], 210, "PAV", [13]),          # P7
        (111, "D.IMG", [11], 211, "TIS", [11]),        # P8
        (112, "D.IMG", [11], 212, "TIS", []),          # P9
        (113, "MUS", [12], 213, "TIS", [11]),          # P11
        (114, "MUS", [12], 214, "TIS", [12]),          # P12
    ]
    for child, ctype, cassays, parent, ptype, passays in probes:
        add(child, ctype, cassays), add(parent, ptype, passays)
        edge(child, parent)
    # P10 is the only three-node probe: c10 -> s10 -> p10
    add(115, "D.IMG", [11]), add(215, "TIS", [11]), add(315, "PAV", [11])
    edge(115, 215), edge(215, 315)
    # P13, one held-out sample carrying BOTH outcomes at once
    add(216, "TIS", [11, 12]), add(116, "D.IMG", [11]), add(117, "D.IMG", [13])
    edge(116, 216), edge(117, 216)

    assays = pd.DataFrame(
        [(11 + SEEK_OFFSET, "Assay 11", 3, 2, 1, 10, "P", 11, "Assay 11"),
         (12 + SEEK_OFFSET, "Assay 12", 3, 2, 1, 10, "P", 12, "Assay 12"),
         (13 + SEEK_OFFSET, "Assay 13", 3, 2, 1, 10, "P", 13, "Assay 13")],
        columns=S.ASSAY_COLUMNS,
    )
    return {
        "nodes": pd.DataFrame(nodes, columns=S.NODES_COLUMNS),
        "membership": pd.DataFrame(membership, columns=S.MEMBERSHIP_COLUMNS),
        "samples": pd.DataFrame(samples, columns=S.SAMPLE_COLUMNS),
        "edges": pd.DataFrame(edges, columns=S.EDGE_COLUMNS),
        "assays": assays,
    }


# Every held-out sample, named. The split is handed in rather than hashed here so
# a test names the samples it is reasoning about; `split_by_sample` is what
# `main` uses and is exercised on its own.
HELD_OUT = frozenset({
    201,        # P1  the plain ADD_PARENT recovery
    202,        # P2  a proposal is made and names the wrong assay
    203, 204,   # P3 / P3b
    105, 106,   # P4 / P5
    107, 108, 109,   # P6 / P6b / P6c
    110,        # P7  a hop with no rule at all
    111, 211,   # P8  BOTH endpoints, so nothing is proposed
    213,        # P11 the only row in [0.50,0.75), and it is wrong
    114,        # P12
    115, 215,   # P10 c10 and s10; p10 (315) stays kept, and flips the direction
    216,        # P13 one recovery and one wrong proposal on the SAME sample
})


def _split(w, held_out=HELD_OUT):
    universe = B.sample_universe(w["samples"], w["membership"], w["edges"])
    return B.Split(frozenset(held_out), universe - frozenset(held_out))


def _run(w=None, held_out=HELD_OUT):
    """The world, backtested. -> (w, split, Backtest)."""
    w = w or _world()
    split = _split(w, held_out)
    return w, split, B.backtest(
        edges=w["edges"], samples=w["samples"], membership=w["membership"],
        assays=w["assays"], nodes=w["nodes"], split=split)


def _cell(bands, band, action):
    hit = bands[(bands.band == band) & (bands.action == action)]
    assert len(hit) == 1, f"expected exactly one ({band}, {action}) row"
    return hit.iloc[0]


# --- the split ---------------------------------------------------------------


def test_a_sample_on_both_sides_of_the_split_is_refused_and_an_edge_split_makes_one():
    """The guard is real, and the split it refuses is the one an edge split builds.

    A sample fans out to many edges, so splitting the EDGE frame assigns the same
    sample to both halves and the run scores answers it was trained on. The wrong
    rule is built here by hand, and it is THIS MODULE'S OWN SPLITTER applied to
    the wrong unit -- the edge frame's row positions instead of the sample ids --
    with each edge's endpoints following it. The overlap it produces is measured
    rather than assumed, so this test cannot pass on a world whose two halves
    happen to come out disjoint.
    """
    w = _world()
    universe = B.sample_universe(w["samples"], w["membership"], w["edges"])

    # THE WRONG RULE, run by hand, and it is the SAME splitter applied to the
    # wrong unit: the edge frame's row positions instead of the sample ids. That
    # is the mistake the guard exists for, spelled exactly as someone would make
    # it, rather than a partition chosen to overlap.
    edge_split = B.split_by_sample(range(len(w["edges"])), fraction=0.5, seed=0)
    left = w["edges"].iloc[sorted(edge_split.held_out)]
    right = w["edges"].iloc[sorted(edge_split.kept)]

    def _ends(frame):
        return frozenset(int(v) for v in frame.child_id) | frozenset(
            int(v) for v in frame.parent_id)

    a, b = _ends(left), _ends(right)
    assert a & b, "an edge-level split must put some sample on both sides"
    with pytest.raises(ValueError, match="both halves"):
        B.check_split(B.Split(a, b), universe)

    # ...and a sample assigned to NEITHER half is refused too, because it is
    # silently treated as kept and its registrations then train the run that is
    # supposed to be blind to them.
    good = _split(w)
    B.check_split(good, universe)
    orphan = sorted(good.kept)[0]
    with pytest.raises(ValueError, match="neither half"):
        B.check_split(B.Split(good.held_out, good.kept - {orphan}), universe)

    # the good split is what `backtest` accepts, and the bad one is refused
    # THROUGH it rather than only through the checker a caller might not run
    with pytest.raises(ValueError, match="both halves"):
        B.backtest(edges=w["edges"], samples=w["samples"],
                   membership=w["membership"], assays=w["assays"],
                   nodes=w["nodes"], split=B.Split(a, b))


def test_the_split_is_deterministic_and_does_not_depend_on_row_order_or_hash():
    """The same universe gives the same split, whatever order it arrives in.

    `hash()` is salted per process by `PYTHONHASHSEED`, so a split built on it
    changes between two runs over identical data and no measurement in this
    module could be reproduced. A stable digest is used instead, and its absence
    is asserted off the source rather than left to review.
    """
    universe = frozenset(range(1, 501))
    one = B.split_by_sample(universe, fraction=0.2, seed=0)
    two = B.split_by_sample(sorted(universe, reverse=True), fraction=0.2, seed=0)
    assert one == two
    assert one.held_out | one.kept == universe
    assert not (one.held_out & one.kept)
    # the fraction is honoured to within the granularity of 500 samples
    assert 0.15 < len(one.held_out) / len(universe) < 0.25

    # a different seed gives a different split of the same universe, or the seed
    # is not reaching the digest at all
    assert B.split_by_sample(universe, fraction=0.2, seed=1) != one

    src = (REPO / "scripts" / "assay_hygiene" / "backtest.py").read_text()
    assert not re.findall(r"[^_\w]hash\(", src), "hash() is salted per process"


# --- hiding, and putting it back ---------------------------------------------


def test_hiding_is_perfectly_reversible_and_leaves_the_input_frames_untouched():
    """Restoring reproduces the membership frame, and no input frame is mutated.

    Byte-identity is checked on the SERIALISED frames rather than with
    `frame.equals`, which compares values and would pass on a frame whose dtypes
    or column order had been rewritten under it. A backtest that mutated the
    membership frame would leak into the live classification running beside it in
    the same process, and the symptom would be a Mode 2 run missing exactly the
    rows this module hid.
    """
    w = _world()
    before = {name: frame.to_csv(index=True).encode()
              for name, frame in w.items()}

    kept_rows, hidden_rows = B.blind_membership(w["membership"], HELD_OUT)
    assert len(kept_rows) + len(hidden_rows) == len(w["membership"])
    assert len(hidden_rows) > 0, "the world must hide something"
    # nothing a held-out sample holds survives, and nothing a kept sample holds
    # is taken -- the hiding is per SAMPLE and not per (sample, assay)
    assert not (set(int(s) for s in kept_rows.sample_id) & HELD_OUT)
    assert set(int(s) for s in hidden_rows.sample_id) <= HELD_OUT

    restored = B.restore_membership(kept_rows, hidden_rows)
    key = list(S.MEMBERSHIP_COLUMNS)
    assert (restored.sort_values(key, ignore_index=True).to_csv(index=False)
            == w["membership"].sort_values(key, ignore_index=True)
            .to_csv(index=False))

    # ...and the whole backtest leaves every input byte-identical
    B.backtest(edges=w["edges"], samples=w["samples"],
               membership=w["membership"], assays=w["assays"],
               nodes=w["nodes"], split=_split(w))
    assert {name: frame.to_csv(index=True).encode()
            for name, frame in w.items()} == before


def test_the_cold_run_sees_no_held_out_membership_and_no_metadata_claim():
    """Nothing the run is asked to recover is in the evidence it reasons from.

    Four leaks are possible and each is closed structurally rather than by
    inspection. The membership of a held-out sample is removed outright, and the
    TRAINING EDGE SET is the subgraph induced on the KEPT samples, so a held-out
    sample's own edge cannot contribute to the rate its recovery is judged by.
    Mining over every edge with a blinded membership frame is the version that
    looks right and is not: measured, it multiplies every rate by about
    (1 - fraction), because an edge whose endpoint was blinded moves out of
    `n_both` and into a one-sided counter -- at a 20% hold-out on seed 0 over the
    real extract the `[0.95,1.00]` ADD_PARENT band reports 1 row where the
    corrected training set reports 4,151.

    THE THIRD LEAK IS THE REACHABILITY CELL, one column over from the rate: a
    held-out sample counting its own hidden registration into its own
    (type, assay) population. `type_registrations` is built from the kept rows
    for that reason, and it is pinned below against both readings, because a
    mutation building it warm SURVIVED this file's first mutation run.

    The fourth leak is the vocabulary, and it is closed by exclusion: the terms
    were learned over the FULL labelled edge set, held-out samples included, so
    no split this module can make blinds them. The cold run therefore carries no
    claims at all and measures precedent and lineage alone.
    """
    w, split, out = _run()

    train = B.training_edges(w["edges"], split.held_out)
    assert len(train) < len(w["edges"])
    assert not [1 for c, p in zip(train.child_id, train.parent_id)
                if int(c) in split.held_out or int(p) in split.held_out]
    # THE WRONG RULE, run by hand: mining over every edge with the blinded
    # membership frame gives a materially different -- and deflated -- rate on
    # the world's top hop, so this test cannot pass under it
    kept_rows, _ = B.blind_membership(w["membership"], split.held_out)
    cold = X.precedent_rules(P.mine_precedent(train, kept_rows, w["assays"]))
    warm = X.precedent_rules(
        P.mine_precedent(w["edges"], kept_rows, w["assays"]))
    hop = (10, "D.IMG", "TIS", 11)
    assert cold[hop].propagation_rate == 0.95
    assert warm[hop].propagation_rate < cold[hop].propagation_rate

    # ...and the rate the RUN put on a row is the cold one, so this test fails
    # on a backtest that mined the warm rules while the comparison above still
    # passed
    row = out.findings[(out.findings.sample_id == 201)
                       & (out.findings.proposed_internal_assay_id == 11)].iloc[0]
    assert row.precedent_rate == cold[hop].propagation_rate
    assert row.precedent_rate != warm[hop].propagation_rate

    # NOTHING A HELD-OUT SAMPLE HELD IS VISIBLE TO THE RUN. 201 was registered
    # in 11 and the run has to propose it, which it can only do if 201 reads as
    # registered in nothing at all.
    assert row.registered_internal_assay_ids == ""
    assert row.action == S.A_ADD_PARENT

    # ...INCLUDING THE REACHABILITY CELL THE ROW REPORTS. `type_registrations`
    # counts the samples of this type already registered in the proposed assay,
    # and a held-out sample counting itself into its own cell is the same leak
    # one column over. The warm and cold counts are both computed here, so this
    # fails on a run that built the index from the full membership frame.
    cold_cell = G.type_registration_index(kept_rows, w["assays"], w["nodes"])
    warm_cell = G.type_registration_index(
        w["membership"], w["assays"], w["nodes"])
    assert warm_cell[("TIS", 11)] > cold_cell[("TIS", 11)]
    assert row.type_registrations == cold_cell[("TIS", 11)]

    # no claim reached the run: every proposal rests on precedent or on the
    # neighbour's registration alone
    assert set(out.findings.proposed_by) <= {X.BY_PRECEDENT, X.BY_LINEAGE_ONLY}


# --- what recovery means -----------------------------------------------------


def test_recovery_is_measured_against_the_curators_assay_and_not_a_proposal():
    """A proposal naming an assay the curator did not assign is NOT a recovery.

    p2 was registered in 12 and the run proposes 11 for it; c5 was registered in
    11 and the run proposes 12. Both are proposals, both are in the top band, and
    neither recovers anything. Scoring "a proposal was made" -- the wrong rule --
    is computed here and asserted to give a DIFFERENT answer, because a test that
    only asserts the right answer cannot tell which rule produced it.
    """
    w, split, out = _run()
    proposed = set(zip((int(s) for s in out.findings.sample_id),
                       (int(a) for a in out.findings.proposed_internal_assay_id)))

    # the two probes, by name
    assert (202, 11) in proposed and (202, 11) not in out.truth
    assert (106, 12) in proposed and (106, 12) not in out.truth
    # ...and what the curator DID assign them, which is a different assay
    registered = A.registered_internal(w["membership"], w["assays"])
    assert registered[202] == {12} and registered[106] == {11}

    top = _cell(out.bands, "[0.95,1.00]", S.A_ADD_PARENT)
    assert top.rows == 3 and top.correct == 2
    # THE WRONG RULE, run by hand: "was any proposal made" scores every row
    scored = out.findings[
        out.findings.sample_id.map(lambda s: int(s) in split.held_out)]
    any_proposal = scored[(scored.action == S.A_ADD_PARENT)
                          & (scored.precedent_rate >= 0.95)]
    assert len(any_proposal) == 3, "the wrong rule counts every proposal correct"
    assert top.correct != len(any_proposal)

    # THE OTHER WRONG RULE: matching on the SAMPLE and ignoring which ASSAY. P13
    # is the probe that discriminates it -- s13 has a recovery AND a wrong
    # proposal -- and without such a sample the two rules agree on every row.
    assert (216, 11) in out.truth and (216, 13) in proposed
    assert (216, 13) not in out.truth
    by_sample = sum(
        1 for s, a in zip(scored.sample_id, scored.proposed_internal_assay_id)
        if any(k[0] == int(s) for k in out.truth))
    by_pair = sum(
        1 for s, a in zip(scored.sample_id, scored.proposed_internal_assay_id)
        if (int(s), int(a)) in out.truth)
    assert by_sample != by_pair

    # and the whole scored population, so the difference is not one row
    assert out.census["proposals_scored"] == 15
    assert (out.census["proposals_scored_correct_add_parent"]
            + out.census["proposals_scored_correct_add_child"]) == by_pair == 8


def test_a_proposal_about_a_kept_sample_is_unscorable_and_is_counted_apart():
    """A kept sample's ground truth is empty by construction, so it is not scored.

    `mode2_candidates` never proposes an assay a sample already holds, so EVERY
    proposal about a kept sample names an assay the curator did not assign.
    Scoring them would report a precision of zero measuring nothing at all, and
    dropping them silently would leave the largest population in the run
    uncounted. P9 is the named probe -- kept parent 212 holds nothing, its kept
    child 112 holds 11 -- and the background hops supply the rest.
    """
    w, split, out = _run()
    scored = out.findings[
        out.findings.sample_id.map(lambda s: int(s) in split.held_out)]
    unscored = out.findings[
        out.findings.sample_id.map(lambda s: int(s) not in split.held_out)]

    assert (212, 11) in set(zip(
        (int(s) for s in unscored.sample_id),
        (int(a) for a in unscored.proposed_internal_assay_id)))
    assert out.census["proposals"] == len(out.findings)
    assert out.census["proposals_scored"] == len(scored)
    assert out.census["proposals_on_a_kept_sample"] == len(unscored)
    assert (out.census["proposals"]
            == out.census["proposals_scored"]
            + out.census["proposals_on_a_kept_sample"])
    assert out.census["proposals_on_a_kept_sample"] > 0

    # THE WRONG RULE, run by hand: scoring every proposal buries the measurement
    registered = A.registered_internal(w["membership"], w["assays"])
    all_correct = sum(
        1 for s, a in zip(out.findings.sample_id,
                          out.findings.proposed_internal_assay_id)
        if int(a) in registered.get(int(s), ()))
    assert all_correct == out.census["proposals_scored_correct_add_parent"] \
        + out.census["proposals_scored_correct_add_child"]
    pooled = all_correct / len(out.findings)
    measured = all_correct / out.census["proposals_scored"]
    assert pooled < measured / 2, "scoring kept samples halves the answer or worse"


def test_the_census_partitions_every_truth_pair_and_names_what_it_cannot_recover():
    """Nothing is dropped silently, in either direction, at any stage.

    Three things can happen to a registration a curator made on a held-out
    sample: it is recovered in the direction the curator's own world supports, it
    is recovered in the OTHER direction because the neighbour that supported the
    first one was held out too, or it is not recovered at all because every
    supporting neighbour was blinded. The three sum to the population, per
    direction, and a fourth outcome -- a registration no neighbour holds, which
    Mode 2 cannot reach in any world -- is counted before the population is even
    formed.
    """
    _, _, out = _run()
    c = out.census
    assert set(c) == set(B.BACKTEST_CENSUS_KEYS)

    assert c["truth_pairs"] == 11
    assert c["truth_pairs_add_parent"] == 5     # p1, p3, p8, s10, s13
    assert c["truth_pairs_add_child"] == 6      # c4, c6, c7, c8, c10, c12
    assert c["held_out_registrations_with_no_neighbour"] == 7
    assert c["held_out_registrations"] == (
        c["truth_pairs"] + c["held_out_registrations_with_no_neighbour"])
    assert c["truth_pairs"] == (c["truth_pairs_add_parent"]
                                + c["truth_pairs_add_child"])

    assert c["recovered_add_parent"] == 3               # p1, p3, s13
    assert c["recovered_in_the_other_direction_add_parent"] == 1   # s10
    assert c["not_recovered_add_parent"] == 1           # p8, blinded on both sides
    assert c["recovered_add_child"] == 4                # c4, c6, c7, c12
    assert c["recovered_in_the_other_direction_add_child"] == 0
    assert c["not_recovered_add_child"] == 2            # c8 and c10

    for action, key in ((S.A_ADD_PARENT, "add_parent"),
                        (S.A_ADD_CHILD, "add_child")):
        assert c[f"truth_pairs_{key}"] == (
            c[f"recovered_{key}"]
            + c[f"recovered_in_the_other_direction_{key}"]
            + c[f"not_recovered_{key}"]), action

    assert c["membership_rows"] == (c["membership_rows_hidden"]
                                    + c["membership_rows_kept"])
    assert c["samples_in_the_universe"] == (c["samples_held_out"]
                                            + c["samples_kept"])
    assert c["edge_rows_training"] < c["edge_rows"]


# --- the curve ---------------------------------------------------------------


def test_an_empty_band_reports_empty_and_a_null_rate_is_its_own_band_not_zero():
    """No observation is a different statement from every observation wrong.

    `[0.50,0.75)` holds exactly one ADD_PARENT row and it is wrong, so that cell
    reads a precision of 0.000 over a support of 1. Five cells hold nothing at
    all and read EMPTY. A table that printed 0.0 for both would tell an operator
    that a band nobody could measure had been measured and had failed.

    THE SAME DISTINCTION ONE LEVEL DOWN. A row whose hop carries no mined rule
    has a NULL rate, which means nobody measured; a rate of 0.000 means the hop
    was observed and its endpoints were never once co-registered. Filing the
    first under the second is the "absent evidence read as evidence of absence"
    defect this package raises over in four other places.
    """
    # the two are different bands, and the top band is CLOSED so a rate of
    # exactly 1.0 -- the commonest value up there, and the one the whole
    # question turns on -- lands in the table rather than falling off it
    assert B.band_of(None) == B.BAND_NO_RATE
    assert B.band_of(float("nan")) == B.BAND_NO_RATE
    assert B.band_of(0.0) == "[0.00,0.50)" != B.BAND_NO_RATE
    assert B.band_of(1.0) == "[0.95,1.00]"
    assert B.band_of(0.95) == "[0.95,1.00]" and B.band_of(0.9499) == "[0.90,0.95)"
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        B.band_of(1.5)

    _, _, out = _run()

    measured_zero = _cell(out.bands, "[0.50,0.75)", S.A_ADD_PARENT)
    assert measured_zero.rows == 1 and measured_zero.correct == 0
    assert measured_zero.precision == 0.0
    assert not pd.isna(measured_zero.precision)

    for band, action in (("[0.50,0.75)", S.A_ADD_CHILD),
                         ("[0.75,0.90)", S.A_ADD_PARENT),
                         ("[0.90,0.95)", S.A_ADD_PARENT),
                         ("[0.90,0.95)", S.A_ADD_CHILD)):
        cell = _cell(out.bands, band, action)
        assert cell.rows == 0, (band, action)
        assert pd.isna(cell.precision), f"{band} {action} must be EMPTY, not 0.0"

    # the fixture's own shape, pinned so its docstring cannot drift: FOUR cells
    # hold nothing and TWO hold only wrong proposals. A table with no empty cell
    # cannot show that an empty cell is reported as empty, and one with no 0.000
    # cannot show that the two are different statements.
    assert int((out.bands["rows"] == 0).sum()) == 4
    assert int(((out.bands["rows"] > 0) & (out.bands.precision == 0.0)).sum()) == 2

    # every cell carries its own support beside its rate, for the reason
    # `co_reg_pop` rides beside `co_reg_rate`
    assert "rows" in B.RECOVERY_COLUMNS and "correct" in B.RECOVERY_COLUMNS
    for r in out.bands.itertuples(index=False):
        assert (r.precision is None or pd.isna(r.precision)) == (r.rows == 0)
        if r.rows:
            assert r.precision == r.correct / r.rows

    # ZERO PROPOSALS IS A SHAPE, NOT A CRASH, and it is where every column is at
    # its most degenerate: an empty frame's columns are all `object`, so
    # `precedent_rate >= x` compares against nothing at all. The whole table is
    # still emitted, at EMPTY, because a report printing nothing would be
    # indistinguishable from a direction nobody measured.
    empty = B.recovery_bands(pd.DataFrame(columns=S.FINDING_COLUMNS), {})
    assert len(empty) == len(B.BAND_LABELS) * 2
    assert set(empty["rows"]) == {0}
    assert empty.precision.isna().all()


def test_the_two_directions_are_scored_and_reported_apart_and_never_pooled():
    """Every cell of the hand-traced table, and what pooling them would say.

    The two directions carry different evidential weight, so no figure this
    module reports may cover both. Measured on the real extract, the demoted
    direction recovers the curator's assay on 19,270 of 19,337 proposals in the
    `[0.95,1.00]` band against 4,143 of 4,151 -- indistinguishable -- while in
    `[0.00,0.50)` it recovers 210 of 18,996 against 519 of 8,806, five times
    worse. One pooled number would hide both halves of that.
    """
    _, _, out = _run()
    assert list(out.bands.columns) == B.RECOVERY_COLUMNS
    assert set(out.bands.action) == {S.A_ADD_PARENT, S.A_ADD_CHILD}
    assert len(out.bands) == len(B.BAND_LABELS) * 2
    # band-major, in the curve's own order, so the table reads top to bottom as
    # a curve rather than as two interleaved ones
    assert list(dict.fromkeys(out.bands.band)) == list(B.BAND_LABELS)
    assert list(out.bands.band).count(B.BAND_NO_RATE) == 2

    expected = {
        (S.A_ADD_PARENT, "NO_RATE"): (1, 0),
        (S.A_ADD_PARENT, "[0.00,0.50)"): (2, 1),
        (S.A_ADD_PARENT, "[0.50,0.75)"): (1, 0),
        (S.A_ADD_PARENT, "[0.75,0.90)"): (0, 0),
        (S.A_ADD_PARENT, "[0.90,0.95)"): (0, 0),
        (S.A_ADD_PARENT, "[0.95,1.00]"): (3, 2),
        (S.A_ADD_CHILD, "NO_RATE"): (2, 2),
        (S.A_ADD_CHILD, "[0.00,0.50)"): (3, 1),
        (S.A_ADD_CHILD, "[0.50,0.75)"): (0, 0),
        (S.A_ADD_CHILD, "[0.75,0.90)"): (1, 1),
        (S.A_ADD_CHILD, "[0.90,0.95)"): (0, 0),
        (S.A_ADD_CHILD, "[0.95,1.00]"): (2, 1),
    }
    for (action, band), (rows, correct) in expected.items():
        cell = _cell(out.bands, band, action)
        assert (int(cell.rows), int(cell.correct)) == (rows, correct), (
            band, action)

    # the two directions genuinely differ, or this table could not show a pooling
    assert (_cell(out.bands, "[0.00,0.50)", S.A_ADD_PARENT).precision
            != _cell(out.bands, "[0.00,0.50)", S.A_ADD_CHILD).precision)
    # THE WRONG RULE, run by hand: one figure over both directions agrees with
    # neither of them
    pooled = sum(v[1] for k, v in expected.items() if k[1] == "[0.00,0.50)") \
        / sum(v[0] for k, v in expected.items() if k[1] == "[0.00,0.50)")
    assert pooled != _cell(out.bands, "[0.00,0.50)", S.A_ADD_PARENT).precision
    assert pooled != _cell(out.bands, "[0.00,0.50)", S.A_ADD_CHILD).precision

    # the bands are disjoint and exhaustive, so an operator reading a suffix of
    # them gets the cumulative figure and no row is counted twice or lost
    for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
        side = out.bands[out.bands.action == action]
        assert int(side["rows"].sum()) == sum(
            v[0] for k, v in expected.items() if k[0] == action)


def test_a_band_says_how_much_independent_evidence_its_rows_rest_on():
    """A row count counts affected samples, not distinct precedent.

    Measured on the real extract, the `[0.95,1.00]` ADD_CHILD band's 19,337 rows
    rest on 118 distinct `(n_both, n_child_only, n_parent_only)` triples and its
    largest keys 5,688 of them; drop that group and the remaining 13,649 rows
    still recover at 0.996. That is what rules out "one hop is doing all the
    work" as the explanation, so the column has to be on the table rather than
    left to whoever holds the parquet.

    THE TRIPLE IS A PROXY AND IT IS LOOSE IN GENERAL. Two rules with identical
    counts collapse into one group, so it is a LOWER bound on the rules behind a
    band. Measured over the live extract it is EXACT at the 0.95 cut -- 15
    qualifying reverse rules occupy 15 distinct triples and 5 propagation rules 5
    -- and loose across the whole mined set, where the 961 mined rules occupy
    537 distinct triples, 55.9%, so 44.1% of them share a triple with another
    rule. Neither figure has been re-measured on a BLINDED world, so it is read
    here as a lower bound and nothing else.
    """
    _, _, out = _run()

    for r in out.bands.itertuples(index=False):
        assert r.rule_groups <= r.rows
        assert r.largest_group_rows <= r.rows
        assert r.largest_group_correct <= r.largest_group_rows
        assert r.largest_group_correct <= r.correct

    # the three ADD_CHILD rows in [0.00,0.50) are ONE rule -- all three sit on
    # the same hop -- so the column is not a restatement of `rows`
    low = _cell(out.bands, "[0.00,0.50)", S.A_ADD_CHILD)
    assert low.rows == 3 and low.rule_groups == 1 and low.largest_group_rows == 3

    # A ROW WITH NO RULE RESTS ON NO EVIDENCE, so the NO_RATE band reports ZERO
    # groups and never one group of nulls. `drop_duplicates` treats two null
    # triples as equal, so the natural spelling reports "1 evidence group" for
    # rows whose own evidence is that nobody measured.
    no_rate = _cell(out.bands, "NO_RATE", S.A_ADD_CHILD)
    assert no_rate.rows == 2 and no_rate.rule_groups == 0
    assert no_rate.largest_group_rows == 0


def test_the_module_is_read_only_and_names_every_file_it_opens():
    """No write path, and no function whose name says it decides.

    `stage0_apply` and `driver_stage0` carry live production Cypher, and an
    import is the only way a read-only module acquires a write path by accident.
    The filenames are extracted from the source rather than searched for one at a
    time, so a further file added later fails here and has to be named.

    THE THRESHOLDS ARE AN OUTPUT AND NOTHING IN THIS MODULE COMPARES AGAINST ONE.
    `BAND_EDGES` labels a curve; under the binding constraint every proposed
    change reaches the operator, so a band sets READING ORDER and grants no
    permission. A module that filtered its own proposals by a band would be
    choosing a cutoff, which is exactly what this task may not do.
    """
    src = (REPO / "scripts" / "assay_hygiene" / "backtest.py").read_text()

    assert set(re.findall(r"[\w.-]+\.parquet", src)) == {
        "samples.parquet", "membership.parquet", "assays.parquet",
        "nodes.parquet", "edges.parquet"}
    assert not re.findall(r"[\w.-]+\.csv", src)
    assert "stage0_apply" not in src and "driver_stage0" not in src
    assert "to_csv" not in src and "to_parquet" not in src
    assert not re.findall(r"^def decide_", src, re.M)

    # NO CUTOFF IS CHOSEN, asserted on behaviour rather than on the source: the
    # bands partition the scored proposals exactly, so nothing was dropped by
    # falling below one. A band that filtered rows would be a cutoff picked in
    # code, which is what this task may not do.
    _, _, out = _run()
    assert int(out.bands["rows"].sum()) == out.census["proposals_scored"]
    assert out.census["proposals_scored"] > 0
    # ...and the emitter it drives is handed no threshold constant at all
    assert "SURVIVAL_THRESHOLDS" in src, "the band edges are taken from stage C"
    runner = src.split("def backtest")[1].split("\ndef ")[0]
    assert "BAND_EDGES" not in runner and "precedent_rate >=" not in runner


def test_the_worlds_mined_rates_are_what_its_own_edge_counts_imply():
    """A stale fixture docstring cannot fail a suite that only asserts counts.

    The three background hops state their `(n_both, n_child_only, n_parent_only)`
    and the band each probe lands in, and both are consequences of edges built by
    a loop. So every rate is re-derived here from the mined frame and checked
    against the arithmetic its own counts imply, and the probes' bands are read
    off `band_of` rather than off the sentence that claims them.
    """
    w, split, out = _run()
    kept_rows, _ = B.blind_membership(w["membership"], split.held_out)
    rules = X.precedent_rules(P.mine_precedent(
        B.training_edges(w["edges"], split.held_out), kept_rows, w["assays"]))

    for hop, counts in (((10, "D.IMG", "TIS", 11), (19, 1, 20)),
                        ((10, "TIS", "PAV", 12), (19, 20, 1)),
                        ((10, "MUS", "TIS", 12), (6, 4, 1))):
        rule = rules[hop]
        assert (rule.n_both, rule.n_child_only, rule.n_parent_only) == counts
        both, child_only, parent_only = counts
        assert rule.propagation_rate == both / (both + child_only)
        assert rule.reverse_rate == both / (both + parent_only)

    # the hops P7, P10 and P13's second row land on have NO rule at all, which
    # is what puts them in the NO_RATE band rather than at a rate of zero
    assert (10, "MUS", "PAV", 13) not in rules
    assert (10, "TIS", "PAV", 11) not in rules
    assert (10, "D.IMG", "TIS", 13) not in rules

    # every probe's band, read off the emitted rate rather than off the docstring
    rows = {(int(s), int(a)): (band, act) for s, a, band, act in zip(
        out.findings.sample_id, out.findings.proposed_internal_assay_id,
        out.findings.precedent_rate.map(B.band_of), out.findings.action)}
    assert rows[(201, 11)] == ("[0.95,1.00]", S.A_ADD_PARENT)
    assert rows[(203, 12)] == ("[0.00,0.50)", S.A_ADD_PARENT)
    assert rows[(213, 12)] == ("[0.50,0.75)", S.A_ADD_PARENT)
    assert rows[(105, 12)] == ("[0.95,1.00]", S.A_ADD_CHILD)
    assert rows[(107, 11)] == ("[0.00,0.50)", S.A_ADD_CHILD)
    assert rows[(114, 12)] == ("[0.75,0.90)", S.A_ADD_CHILD)
    assert rows[(110, 13)] == ("NO_RATE", S.A_ADD_CHILD)
    assert rows[(215, 11)] == ("NO_RATE", S.A_ADD_CHILD)
    assert rows[(216, 11)] == ("[0.95,1.00]", S.A_ADD_PARENT)
    assert rows[(216, 13)] == ("NO_RATE", S.A_ADD_PARENT)
    # ...and P8's two endpoints, blinded on both sides, propose nothing at all
    assert (211, 11) not in rows and (111, 11) not in rows


def test_main_reports_both_curves_and_leaves_every_byte_on_disk_unchanged(
        tmp_path, capsys):
    """A full `main` run over the fixture: nothing created, nothing modified.

    Asserted by hashing the directory before and after rather than by checking
    for one filename, following `classify.main`'s own guard. The backtest is a
    measurement and produces no artifact at all.
    """
    import hashlib

    w = _world()
    extract = tmp_path / "extract"
    extract.mkdir()
    for name in ("samples", "membership", "assays", "nodes", "edges"):
        w[name].to_parquet(extract / f"{name}.parquet", index=False)

    def _digests():
        return {p.relative_to(tmp_path).as_posix():
                hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(tmp_path.rglob("*")) if p.is_file()}

    before = _digests()
    assert B.main(str(extract), "0.2", "0") == 0
    assert _digests() == before

    printed = capsys.readouterr().out
    for k in B.BACKTEST_CENSUS_KEYS:
        assert k in printed
    # the two directions are printed apart at every band, never as one figure
    for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
        assert printed.count(action) >= len(B.BAND_LABELS)

    # THE TABLE ITSELF, not the sentence explaining it. `"EMPTY" in printed` is
    # vacuous, because the report prints an explanatory line containing the word
    # whatever the data says -- measured, a mutation that formatted an
    # unmeasured band as a number SURVIVED that check while printing `nan` into
    # a curator's table.
    table = [ln for ln in printed.splitlines()
             if "precision" in ln and " recovered " in ln]
    assert len(table) == len(B.BAND_LABELS) * 2
    for band in B.BAND_LABELS:
        assert sum(1 for ln in table if band in ln) == 2
    assert [ln for ln in table if "EMPTY" in ln], "this world has empty bands"
    assert "nan" not in printed.lower()

    assert "nothing was written" in printed
    # the threshold is an OUTPUT: the report may not name a chosen one
    assert "reading order" in printed.lower()


# --- extract-backed ----------------------------------------------------------


def _real():
    for f in ("samples.parquet", "membership.parquet", "assays.parquet",
              "nodes.parquet", "edges.parquet"):
        if not (EXTRACT / f).exists():
            pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    return {n: pd.read_parquet(EXTRACT / f"{n}.parquet")
            for n in ("samples", "membership", "assays", "nodes", "edges")}


def test_the_real_extract_reproduces_both_recovery_curves_separately():
    """The measurement this task exists to make, at a 20% hold-out on seed 0.

    THE HEADLINE, AND IT CUTS AGAINST THE SPEC'S DEMOTION OF `A_ADD_CHILD`. In
    the `[0.95,1.00]` band the demoted direction recovers the curator's assay on
    19,270 of 19,337 proposals, 0.9965, over 118 evidence groups; the favoured
    direction recovers 4,143 of 4,151, 0.9981, over 95. At equal precedent rate
    the two directions are indistinguishable, so `reverse_rate` at a given value
    is as good a guide to reading order as `propagation_rate` at that value.

    THE DEMOTION SURVIVES ON THE DIRECTION'S BULK AND NOT ON ITS TOP BAND. In
    `[0.00,0.50)` the demoted direction recovers 210 of 18,996 against 519 of
    8,806, five times worse -- and that is where almost all of its 117,331 rows
    sit.

    WHAT THIS DOES NOT MEASURE. The scored population is enriched with the
    registrations the split hid, which the live run would never propose because
    the sample already holds them. So this is the precision of a proposal about a
    sample whose registrations were hidden, and it is not the precision of the
    live dark rows, which have no ground truth by construction -- the spec says
    so under "What cannot be validated, stated plainly". A proposal counted wrong
    here may also be a genuine gap the pipeline correctly found, so every
    precision below is a LOWER bound.
    """
    r = _real()
    universe = B.sample_universe(r["samples"], r["membership"], r["edges"])
    split = B.split_by_sample(universe, fraction=0.2, seed=0)
    out = B.backtest(edges=r["edges"], samples=r["samples"],
                     membership=r["membership"], assays=r["assays"],
                     nodes=r["nodes"], split=split)
    c = out.census

    assert c["samples_in_the_universe"] == 163816
    assert c["samples_held_out"] == 32793
    assert c["membership_rows"] == 214296
    assert c["membership_rows_hidden"] == 42867
    assert c["edge_rows"] == 794593
    assert c["edge_rows_training"] == 509875

    # the population, never pooled
    assert c["truth_pairs"] == 36090
    assert c["truth_pairs_add_parent"] == 10739
    assert c["truth_pairs_add_child"] == 25351
    # outside Mode 2's reach in ANY world, counted rather than scored as a miss
    assert c["held_out_registrations"] == 42829
    assert c["held_out_registrations_with_no_neighbour"] == 6739
    assert c["recovered_add_parent"] == 9500
    assert c["recovered_add_child"] == 20683
    assert c["not_recovered_add_parent"] == 1185
    assert c["not_recovered_add_child"] == 4668
    assert c["recovered_in_the_other_direction_add_parent"] == 54
    assert c["recovered_in_the_other_direction_add_child"] == 0

    assert c["proposals"] == 174788
    assert c["proposals_scored"] == 59182
    assert c["proposals_on_a_kept_sample"] == 115606
    # the two per-direction views read the direction off DIFFERENT worlds -- the
    # curator's for `recovered_*` and the blinded run's for
    # `proposals_scored_correct_*` -- and differ by exactly the flipped pairs
    assert c["proposals_scored_correct_add_parent"] == 9500
    assert c["proposals_scored_correct_add_child"] == 20737 == 20683 + 54

    # BOTH CURVES, apart, with support
    def cell(band, action):
        return _cell(out.bands, band, action)

    parent = {b: (int(cell(b, S.A_ADD_PARENT).rows),
                  int(cell(b, S.A_ADD_PARENT).correct)) for b in B.BAND_LABELS}
    child = {b: (int(cell(b, S.A_ADD_CHILD).rows),
                 int(cell(b, S.A_ADD_CHILD).correct)) for b in B.BAND_LABELS}
    assert parent == {
        "NO_RATE": (11, 4),
        "[0.00,0.50)": (8806, 519),
        "[0.50,0.75)": (2869, 1757),
        "[0.75,0.90)": (1814, 1529),
        "[0.90,0.95)": (1626, 1548),
        "[0.95,1.00]": (4151, 4143),
    }
    assert child == {
        "NO_RATE": (28, 7),
        "[0.00,0.50)": (18996, 210),
        "[0.50,0.75)": (318, 172),
        "[0.75,0.90)": (949, 815),
        "[0.90,0.95)": (277, 263),
        "[0.95,1.00]": (19337, 19270),
    }

    # THE 95% BAR, per direction and per band, and the answer is that ONE band
    # clears it in BOTH directions rather than none clearing it in either
    top_parent = cell("[0.95,1.00]", S.A_ADD_PARENT)
    top_child = cell("[0.95,1.00]", S.A_ADD_CHILD)
    assert round(float(top_parent.precision), 4) == 0.9981
    assert round(float(top_child.precision), 4) == 0.9965
    assert top_parent.precision > 0.95 and top_child.precision > 0.95
    assert cell("[0.90,0.95)", S.A_ADD_PARENT).precision > 0.95
    assert cell("[0.90,0.95)", S.A_ADD_CHILD).precision < 0.95
    for band in ("[0.00,0.50)", "[0.50,0.75)", "[0.75,0.90)"):
        for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
            assert cell(band, action).precision < 0.95, (band, action)

    # ...and it is not one hop doing the work in the direction that wins
    assert int(top_child.rule_groups) == 118
    assert int(top_child.largest_group_rows) == 5688
    rest_rows = int(top_child.rows) - int(top_child.largest_group_rows)
    rest_correct = int(top_child.correct) - int(top_child.largest_group_correct)
    assert rest_rows == 13649
    assert round(rest_correct / rest_rows, 4) == 0.9958
    assert int(top_parent.rule_groups) == 95
