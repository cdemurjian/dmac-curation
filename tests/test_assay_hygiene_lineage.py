"""Task 3: the lineage test, over DERIVED_FROM.

WHAT THIS TEST ESTABLISHES, stated once. The lineage test does not decide that
a claim is right. It decides that a claim is an ABSENCE -- a registration that
is missing rather than one that is wrong -- and which DIRECTION the missing
registration runs in. That is the whole of it. Increment 1 had no such test
ahead of the vocabulary gate and reported 866 absences as contradictions; the
gate (Task 2) now runs first and this file assumes nothing about it.

THE RELATION IS `DERIVED_FROM` AND NOT `CHILD_OF`, and the choice is material.

    CHILD_OF        742,534 distinct (child, parent) id pairs
    DERIVED_FROM    794,592 distinct (child, parent) id pairs
    divergence      52,184 DF-only, 126 CO-only

Measured on the 2026-08-14 extract: 9,878 of the 161,531 samples that appear in
either relation carry a DIFFERENT neighbour set under the two, which is 6.1% of
them. Precedent -- the evidence that decides Mode 2 -- is mined over
DERIVED_FROM by `precedent.mine_precedent`, so a lineage test run over CHILD_OF
would ask about a different graph than the one its own evidence was measured on.
`test_the_two_relations_are_not_interchangeable_on_the_real_extract` is the
regression for that and it is extract-backed, because the divergence is a
property of the data and no fixture can stand in for it.

LIN_CHILD BEATS LIN_PARENT ON A TIE, and the reason is evidence and not
convenience. LIN_CHILD proposes adding the PARENT, which is the direction the
operator's domain rule justifies and the measurements back -- 88 of 88
corroborated by co-registration against 15 of 263 for the mirror, and on the
very hop that justified Mode 2 (`TIS <- PAV`) the child's assay flows up at
0.931 while the parent's flows down at 0.006.
`test_LIN_CHILD_wins_a_tie_because_ADD_PARENT_is_the_evidenced_direction`
builds a sample with a qualifying neighbour on BOTH sides, because a fixture
that reaches only one side passes under a swap of the two.

NOTHING IS DROPPED SILENTLY. Three populations cannot be resolved against the
`samples` frame and all three are counted and named rather than skipped:
duplicate uuids, edge endpoints with no `samples` row, and membership rows whose
sample has no `samples` row. The tests assert the DOCUMENTED decision for each,
not whatever the code happens to do.

THE NEIGHBOUR'S UUID IS CARRIED OUT OF THE TRAVERSAL. `FINDING_COLUMNS` needs
`lineage_neighbour_uuid`, and the `samples` join that looks like the way to get
it is blank for the 243 unresolved endpoints -- 182 of them registered, so any
of them can be the neighbour that is named.
`test_the_neighbour_uuid_comes_off_the_edge_row_and_never_from_a_samples_join`
is the regression, and it asserts its neighbour is absent from `samples` first
so a join-based implementation cannot pass it.

A fourth population falls out of that: 79 edge-endpoint sample_ids carry TWO
uuids, so sample_id is not a function to uuid here. Those resolve to THE UUID
`samples` CARRIES FOR THAT ID, falling back to `min()` when there is no such
row. A first revision used `min()` alone on the ground that neither uuid is more
correct; measured, `min()` alone named a uuid appearing nowhere in
`samples.uuid` for 38 of the 38 REGISTERED ambiguous ids, which are exactly the
ones a curator can be shown. The fixtures for both branches are built so the
rule they name DISAGREES with the alternative -- an earlier one was not, and
passed under the bug it was written to catch.
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
from assay_hygiene import lineage as L  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"


# --- fixture plumbing --------------------------------------------------------


def _edges(*pairs):
    """An EDGE_COLUMNS frame from (child_id, parent_id) pairs.

    uuids are synthesised as `S-<id>` and are LOAD-BEARING: `uuid_of` is read
    off these columns and five tests assert against `S-10`, `S-30`, `S-1` and
    the like. An earlier version of this docstring said no property under test
    read them, which was true before the neighbour uuid was routed through the
    traversal and is false now. Types are still synthesised and still unread --
    lineage is a per-sample question.

    A test needing a uuid that is NOT `S-<id>` -- the ambiguity cases, which
    need two uuids on one id -- overwrites the column on the frame this returns.
    """
    return pd.DataFrame(
        [(c, p, f"S-{c}", f"S-{p}", "T", "T", None, None, None) for c, p in pairs],
        columns=S.EDGE_COLUMNS,
    )


def _samples(*rows):
    """A SAMPLE_COLUMNS frame from bare ids, or from (sample_id, uuid) pairs."""
    out = []
    for r in rows:
        sid, uuid = r if isinstance(r, tuple) else (r, f"S-{r}")
        out.append((sid, uuid, "{}", None, "10"))
    return pd.DataFrame(out, columns=S.SAMPLE_COLUMNS)


def _membership(*pairs):
    return pd.DataFrame(list(pairs), columns=S.MEMBERSHIP_COLUMNS)


def _fixture_world():
    """(children_of, parents_of, uuid_of, integrity, registered) for `make_fixture()`.

    `registered` comes from `audit.registered_internal`, which is the package's
    single crossing of the seek `assay_assets.assay_id` namespace into the dmac
    internal one. Building a second grouping of the membership frame here would
    compare a seek id against an internal id and read every claim as an absence.
    """
    fx = S.make_fixture()
    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        fx["edges"], fx["samples"], fx["membership"])
    registered = A.registered_internal(fx["membership"], fx["assays"])
    return children_of, parents_of, uuid_of, integrity, registered


# --- the four verdicts -------------------------------------------------------


def test_a_child_registering_the_assay_makes_the_parent_a_LIN_CHILD_absence():
    """TIS 202 is in 12 Tissue Collection; its child D.IMG 102 is in 11 Comet Chip.

    So 202 lacks 11 and a CHILD of it carries 11: the missing registration is on
    the PARENT, which is `LIN_CHILD` and which Task 6 turns into A_ADD_PARENT,
    the evidenced direction. The neighbour returned is the child that settled
    it, so a reviewer can check the claim against a specific edge rather than
    against the word of the classifier.
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    assert children_of[202] == frozenset({102})
    assert 11 in registered[102] and 11 not in registered[202]

    assert L.neighbour_registers(
        202, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_CHILD, 102, "D.IMG-3")


def test_a_parent_registering_the_assay_makes_the_child_a_LIN_PARENT_absence():
    """TIS 203 is in 12 Tissue Collection; its parent PAV 700 is in 13 Patient Visit.

    `make_fixture` added the 203 -> 700 hop for exactly this: every OTHER
    Mode-2-eligible hop in that world reaches both directions at once, so a
    classifier keying direction off "the edge is disjoint" rather than off the
    assay was indistinguishable from a correct one. 203 has no children at all,
    so `LIN_PARENT` here cannot be an accident of tie ordering.
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    assert 203 not in children_of, "203 has no children; the tie rule must not decide this"
    assert parents_of[203] == frozenset({500, 700})

    assert L.neighbour_registers(
        203, 13, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_PARENT, 700, "PAV-1")


def test_a_sample_that_already_registers_the_assay_has_no_absence_in_either_direction():
    """TIS 200 and its child D.IMG 100 are BOTH in 11 Comet Chip. Nothing is absent.

    The guard is on the SAMPLE'S OWN registration and not on an empty neighbour
    set: 200's child does carry 11, so a function that only looked at neighbours
    would answer `LIN_CHILD` and hand Task 6 a proposal to add 200 to an assay
    it is already in. The second assertion is what makes the first one mean
    that -- without it the case is indistinguishable from "no neighbour has it".
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    assert 11 in registered[200]
    assert 11 in registered[100] and 100 in children_of[200]

    assert L.neighbour_registers(
        200, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_NONE, None, None)


def test_neither_neighbour_registering_the_assay_is_LIN_NONE():
    """DNA 301 and its parent TIS 400 are registered in nothing at all.

    301 is Mode 1's population, and Mode 1 is not this module's business: the
    lineage test establishes nothing about it, which is exactly `LIN_NONE`.
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    assert parents_of[301] == frozenset({400})
    assert 301 not in registered and 400 not in registered

    assert L.neighbour_registers(
        301, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_NONE, None, None)


def test_a_sample_with_no_neighbours_is_LIN_NONE_and_does_not_raise():
    """An id in no edge at all, asked about. A `KeyError` here is a crashed run."""
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    assert 999 not in children_of and 999 not in parents_of

    assert L.neighbour_registers(
        999, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_NONE, None, None)


def test_the_returned_indexes_are_plain_dicts_so_a_lookup_cannot_invent_a_set():
    """A `defaultdict` answers a lookup by CREATING the entry, and this is Task 8's trap.

    `audit.registered_internal` states the reason: callers ask about samples
    with no neighbours, so a `defaultdict` makes `999 in children_of` true of
    every sample ever asked about, and a later membership test on the same index
    reads an isolated sample as connected.

    ASSERTED THROUGH `[]` AND NOT THROUGH `neighbour_registers`. This module
    reaches the index with `.get()`, which does not create an entry in a
    defaultdict either, so a test driven through `neighbour_registers` passes
    whichever type is returned and certifies nothing. The hazard is what a
    CONSUMER does with the object it is handed, and a consumer writing
    `children_of[sample_id]` is the natural spelling.
    """
    children_of, parents_of, _, _, _ = _fixture_world()

    with pytest.raises(KeyError):
        children_of[999]
    with pytest.raises(KeyError):
        parents_of[999]


# --- direction and determinism ----------------------------------------------


def test_LIN_CHILD_wins_a_tie_because_ADD_PARENT_is_the_evidenced_direction():
    """20 lacks assay 5; its child 10 has it AND its parent 30 has it.

    Both directions are available, so the answer is a choice and not a
    consequence of the data. It resolves to `LIN_CHILD` -> A_ADD_PARENT, the
    direction corroborated 88 of 88 times against 15 of 263 for the mirror, and
    the one whose measured hop rate is 0.931 against 0.006. Reporting the mirror
    when the strong direction is available would propose the weaker of two
    writes with no note that a better one existed.

    The second half asserts the tie is real: remove the child's registration and
    the same sample answers `LIN_PARENT`, so the fixture is not answering
    `LIN_CHILD` because `LIN_PARENT` was unreachable.
    """
    edges = _edges((10, 20), (20, 30))
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, _samples(10, 20, 30), _membership((10, 1), (20, 2), (30, 1)))
    assert children_of[20] == frozenset({10}) and parents_of[20] == frozenset({30})

    both = {10: {5}, 20: {6}, 30: {5}}
    assert L.neighbour_registers(
        20, 5, children_of, parents_of, uuid_of, both
    ) == (S.LIN_CHILD, 10, "S-10")

    parent_only = {10: {6}, 20: {6}, 30: {5}}
    assert L.neighbour_registers(
        20, 5, children_of, parents_of, uuid_of, parent_only
    ) == (S.LIN_PARENT, 30, "S-30")


def test_the_lowest_qualifying_neighbour_is_returned_when_several_register_it():
    """Three children of 20 carry assay 5. Which one is named must not be luck.

    Set iteration order is not part of any contract and the frame's row order is
    not stable across extracts -- `test_assay_hygiene_stage0.py` already records
    that -- so an unordered pick would make the artifact a curator diffs change
    between runs on identical data. The lowest sample_id is the rule.

    THE THREE IDS ARE 16, 8 AND 1, INSERTED IN THAT ORDER, AND THAT IS THE WHOLE
    TEST. A `set` of small consecutive ints iterates in ascending order, so a
    fixture of 10 / 11 / 12 returns 10 whether the code sorts or takes whatever
    comes first -- it would pass under the bug it exists to catch. `{16, 8, 1}`
    built in that order iterates 16, 8, 1, so "the first one seen" answers 16
    and only a sorted pick answers 1.
    """
    edges = _edges((16, 20), (8, 20), (1, 20))
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, _samples(1, 8, 16, 20), _membership((20, 1)))
    assert list(children_of[20]) != sorted(children_of[20]), (
        "the fixture no longer discriminates: this set iterates in sorted order")
    registered = {1: {5}, 8: {5}, 16: {5}}

    assert L.neighbour_registers(
        20, 5, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_CHILD, 1, "S-1")


def test_lineage_supports_names_every_support_in_both_directions():
    """Task 6 has to record that a proposal had MULTIPLE supports, and needs them all.

    `neighbour_registers` collapses the answer to one relation and one
    neighbour, which is what a classifier keys on; the full lists are what a
    curator reads and what "emitted ONCE, recording multiple supports" is
    counted from. Both come from the same scan so the two readings cannot
    disagree about which neighbours qualified.
    """
    edges = _edges((10, 20), (11, 20), (20, 30), (20, 31))
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, _samples(10, 11, 20, 30, 31), _membership((20, 1)))
    registered = {10: {5}, 11: {5}, 20: {6}, 30: {5}, 31: {7}}

    assert L.lineage_supports(
        20, 5, children_of, parents_of, registered) == ([10, 11], [30])
    # ...and the collapsed answer is drawn from exactly those lists
    assert L.neighbour_registers(
        20, 5, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_CHILD, 10, "S-10")


def test_the_neighbour_uuid_comes_off_the_edge_row_and_never_from_a_samples_join():
    """MUS 500 has NO `samples` row, and its uuid still reaches the caller.

    `FINDING_COLUMNS` requires `lineage_neighbour_uuid`. Handing a consumer only
    a neighbour sample_id makes the natural way to get that uuid a join through
    `samples.uuid` -- and that join is blank for the 243 edge endpoints with no
    `samples` row, 182 of which are registered and can therefore BE the named
    neighbour. The lossy path would blank the uuid on exactly the population
    this module fought to keep, in the artifact a curator reads.

    500 is that shape in miniature: uuid `MUS-1`, the MUS parent of TIS 203 on
    `make_fixture`'s TIS -> MUS hop, registered in 11 Comet Chip and absent from
    `samples`. The assertion that it IS absent is what makes the rest of this
    test mean anything -- without it a `samples` join would pass.
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    fx = S.make_fixture()
    assert 500 not in set(fx["samples"].sample_id), (
        "500 gained a samples row; this test no longer excludes the join")

    assert uuid_of[500] == "MUS-1"
    assert L.neighbour_registers(
        203, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_PARENT, 500, "MUS-1")


def test_uuid_of_is_total_over_the_index_so_no_neighbour_is_named_without_one():
    """Every id reachable as a neighbour has a uuid, by construction not by luck.

    `neighbour_registers` subscripts `uuid_of` with the neighbour it chose, so a
    partial map raises `KeyError` mid-run rather than returning a blank. The
    invariant making that subscript safe is that both indexes are built from the
    same edge rows the uuids are read off. Asserted rather than trusted.

    THE VALUES ARE ASSERTED, NOT ONLY THE KEYS. A resolution rule that reached
    for `samples` and fell back to `None` rather than to `min()` would leave
    every key in place and every value blank, so a key-only check would pass it
    -- and a blank `lineage_neighbour_uuid` is the exact outcome the whole uuid
    routing exists to prevent.
    """
    children_of, parents_of, uuid_of, _, _ = _fixture_world()

    reachable = {n for ns in children_of.values() for n in ns}
    reachable |= {n for ns in parents_of.values() for n in ns}
    reachable |= set(children_of) | set(parents_of)
    assert reachable and reachable <= set(uuid_of)
    assert all(isinstance(uuid_of[s], str) and uuid_of[s] for s in reachable)


def test_an_ambiguous_uuid_resolves_to_the_one_the_samples_frame_carries():
    """Of two uuids on one sample_id, name the one a curator can look up.

    sample_id is NOT a function to uuid here: 79 edge-endpoint sample_ids carry
    TWO uuids across the edge rows, 38 of them registered, 44 of the 79 pairs
    disagreeing on node type. Same 86-sample collision `gate.sample_type_index`
    documents, and why THAT index is keyed on uuid rather than sample_id.

    An earlier revision resolved by `min()` alone, on the stated ground that
    "neither uuid is more correct than the other". That is a checkable claim and
    the check goes the other way: `samples` holds one row per sample_id, and for
    79 of 79 ambiguous ids exactly one of the two uuids IS that id's own
    `samples.uuid` while the other appears nowhere in `samples.uuid` at all.
    `min()` alone picked the absent one for 38 of the 38 REGISTERED ambiguous
    ids -- the only ones that can be named as a qualifying neighbour -- so every
    such neighbour carried a uuid the curator could not find.

    THE FRAME IS BUILT SO `min()` WOULD GET IT WRONG. `samples` carries
    `Z-known` for sample 5 and the other edge row says `A-orphan`, so
    `min()` answers `A-orphan` and only the preference answers `Z-known`. A
    fixture where the preferred uuid is also the lowest cannot tell the two
    rules apart, which is exactly how the previous version of this test passed
    while the rule it named was untested.

    THIS FIXTURE COVERS `min()`-ALONE AND NOTHING ELSE. Two rows cannot separate
    the positional rules -- see the sibling fallback test, which carries three
    uuids for that reason. The guard below reads its values OFF THE FRAME rather
    than repeating them as literals: a guard that restates the fixture's strings
    stays green when the fixture is edited, which is precisely the rot it exists
    to prevent.
    """
    edges = _edges((5, 20), (5, 21))
    edges.loc[0, "child_uuid"] = "Z-known"
    edges.loc[1, "child_uuid"] = "A-orphan"
    samples = _samples((5, "Z-known"), 20, 21)

    own = samples.loc[samples.sample_id == 5, "uuid"].iloc[0]
    candidates = set(edges.loc[edges.child_id == 5, "child_uuid"])
    assert own in candidates and min(candidates) != own, (
        "the fixture no longer discriminates: the samples uuid must not also be "
        f"the lowest, got own={own!r} candidates={sorted(candidates)}")

    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        edges, samples, _membership((5, 1)))

    assert uuid_of[5] == "Z-known"
    assert integrity["ambiguous_uuid_samples"] == [5]
    # ...and an unambiguous neighbour is untouched by the rule
    assert uuid_of[20] == "S-20"
    assert L.neighbour_registers(
        20, 9, children_of, parents_of, uuid_of, {5: {9}}
    ) == (S.LIN_CHILD, 5, "Z-known")


def test_an_ambiguous_uuid_with_no_samples_row_falls_back_to_the_lowest():
    """The preference is a PREFERENCE, not a join, and this is what that means.

    A sample with no `samples` row has no preferred uuid, and it must still get
    one: `neighbour_registers` subscripts `uuid_of`, and the 243 unresolved
    endpoints -- 182 of them registered -- are exactly the population a join
    would blank. So the rule falls through to `min()` and `uuid_of` stays total.
    Measured, 0 of the 79 ambiguous ids lack a `samples` row today, so this
    branch is unexercised on the real extract and is covered only here.

    THREE UUIDS ON ONE SAMPLE_ID, ORDERED MIDDLE / LOWEST / HIGHEST, AND THE
    ORDERING IS THE ENTIRE POINT. A TWO-row fixture cannot separate both
    positional rules: killing last-row-wins needs `min == first`, killing
    first-row-wins needs `min != first`, and one frame cannot satisfy both. Two
    revisions of this test each picked one and silently left the other
    uncovered -- the first ordering caught first-row-wins and missed
    last-row-wins, the second did the reverse.

    With three, `min != first`, `min != last` and `min != max` all hold at once,
    so this single frame discriminates `min()` from first-row-wins,
    last-row-wins, `max()`, prefer-own-else-max and prefer-own-else-None
    together. Only `min()`-alone survives here, and the sibling preference test
    is what kills that.

    Verified by SIMULATING all seven candidate rules against this frame, not by
    watching this test pass -- a passing test is not evidence that a fixture
    discriminates, which is the whole lesson of the round that produced it.

    Nothing on the real extract backs this up: 0 of the 79 ambiguous ids lack a
    `samples` row, so the fallback branch is unexercised there, and last-row-wins
    happens to agree with the preferred uuid for 79 of 79 anyway. Fixture-level
    coverage is the ONLY coverage either positional rule has.
    """
    edges = _edges((5, 20), (5, 21), (5, 22))
    edges.loc[0, "child_uuid"] = "M-middle"
    edges.loc[1, "child_uuid"] = "A-lowest"
    edges.loc[2, "child_uuid"] = "Z-highest"

    rows = list(edges.child_uuid)
    assert len(set(rows)) == 3, "three distinct uuids or this frame proves less"
    assert min(rows) != rows[0], "would not discriminate first-row-wins"
    assert min(rows) != rows[-1], "would not discriminate last-row-wins"
    assert min(rows) != max(rows), "would not discriminate max()"

    _, _, uuid_of, integrity = L.lineage_index(
        edges, _samples(20, 21, 22), _membership((5, 1)))

    assert uuid_of[5] == min(rows) == "A-lowest"
    assert integrity["ambiguous_uuid_samples"] == [5]


def test_the_two_lineage_functions_cannot_be_swapped_for_one_another():
    """Call the wrong one and it must raise, not return a plausible shape.

    `neighbours_registering` and `neighbour_registers` differed by one character
    and both returned a 2-tuple, so `relation, neighbour = <plural>(...)` bound a
    LIST to `relation`, `relation == S.LIN_CHILD` was quietly False, and the
    proposal was dropped with no exception, no warning and no row-count
    anomaly -- this branch's named failure class, at the interface Tasks 6 and 8
    dispatch against.

    The names are now distinct AND so are the shapes: 5 arguments returning a
    2-tuple against 6 returning a 3-tuple. This asserts the SHAPES, because a
    rename on its own is a convention and a convention is not a test.
    """
    children_of, parents_of, uuid_of, _, registered = _fixture_world()
    plural = (202, 11, children_of, parents_of, registered)
    singular = (202, 11, children_of, parents_of, uuid_of, registered)

    assert len(L.lineage_supports(*plural)) == 2
    assert len(L.neighbour_registers(*singular)) == 3
    with pytest.raises(TypeError):
        L.lineage_supports(*singular)
    with pytest.raises(TypeError):
        L.neighbour_registers(*plural)


def test_a_sample_that_already_registers_the_assay_names_no_supports():
    """The self-registration guard lives in ONE place, and this is the proof.

    `neighbour_registers` is a collapse of `lineage_supports`, so if the
    guard were only in the collapse then Task 6's multiple-support count would
    still be non-zero for a sample with nothing absent, and the row would be
    reported as corroborated by two neighbours while proposing nothing.
    """
    edges = _edges((10, 20))
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, _samples(10, 20), _membership((20, 1)))
    registered = {10: {5}, 20: {5}}

    assert L.lineage_supports(
        20, 5, children_of, parents_of, registered) == ([], [])


# --- integrity: nothing is dropped silently ---------------------------------


def test_two_sample_ids_on_one_uuid_are_counted_and_neither_borrows_the_others_lineage():
    """The DOCUMENTED decision, asserted as such: report the pair, resolve nothing.

    `samples` carries 28 rows over 14 uuids that each name two sample_ids. The
    index is keyed on `edges.child_id` / `edges.parent_id`, which are the graph
    node's own `id` property and are the same id space `membership.sample_id`
    speaks, so no uuid hop happens and no resolution rule is needed or applied.

    An earlier draft of this task's brief required resolving a duplicated uuid
    to the LOWEST of its sample_ids. Measured on the 2026-08-14 extract that is
    backwards in all 14 cases: the graph node carries the HIGHER id every time,
    so the lower id has no edges at all and "lowest wins" would point the index
    at the endpoint with nothing on it. Aliasing the two the other way was
    rejected too -- `registered` is keyed on raw `membership.sample_id`, so a
    canonicalised index and a raw registration frame would be two identities one
    frame apart, which is this branch's signature defect.

    The cost is bounded and stated: at most 14 samples out of 163,393 read
    LIN_NONE where a sibling row carries their edges. `integrity` names them so
    an operator can see which.
    """
    samples = _samples((1, "U-1"), (2, "U-1"), (3, "U-3"))
    edges = _edges((2, 3))
    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        edges, samples, _membership((1, 7), (2, 7)))

    assert integrity["dup_uuid_rows"] == 2
    assert integrity["dup_uuid_samples"] == [1, 2]
    # 2 carries the edge; 1 shares its uuid and does not inherit it
    assert parents_of[2] == frozenset({3})
    assert 1 not in parents_of and 1 not in children_of
    assert L.neighbour_registers(
        1, 5, children_of, parents_of, uuid_of, {3: {5}}
    ) == (S.LIN_NONE, None, None)


def test_an_edge_endpoint_absent_from_samples_is_counted_and_kept_as_a_neighbour():
    """`make_fixture` has three such edges, and they must stay in the index.

    201, 400 and 500 are endpoints of edges and carry no `samples` row. Measured
    on the real extract the same shape covers 979 edge rows over 243 endpoints,
    and 182 of those 243 ARE registered in `membership` -- dropping them would
    delete real lineage evidence and turn genuine absences into `LIN_NONE`,
    which is the invisible failure direction this whole increment exists to fix.
    So they are RETAINED and counted, which is what "nothing is dropped
    silently" means when the row is still usable.
    """
    _, parents_of, _, integrity, _ = _fixture_world()

    assert integrity["unresolved_edges"] == 3
    assert integrity["unresolved_samples"] == [201, 400, 500]
    assert 500 in parents_of[203], "an unresolved endpoint was dropped from the index"


def test_unresolved_edges_counts_edge_rows_and_unresolved_samples_counts_endpoints():
    """One unresolved endpoint on three edges is 3 rows and 1 sample, never 3 and 3.

    In `make_fixture` the two readings both come to 3, so that fixture cannot
    tell them apart and a `len(unresolved_samples)` spelling of
    `unresolved_edges` passes on it. A count quoted without its unit is this
    project's signature defect -- `gate.gate_claims` renamed a parameter over
    exactly this, after 50 of 736 vocabulary terms turned out to rest on one
    sample while clearing an edge floor of 30 -- and these two sit on adjacent
    lines of one report.

    On the real extract the two readings are 979 and 243.
    """
    edges = _edges((1, 99), (2, 99), (3, 99))
    _, _, _, integrity = L.lineage_index(
        edges, _samples(1, 2, 3), _membership((1, 7)))

    assert integrity["unresolved_edges"] == 3
    assert integrity["unresolved_samples"] == [99]


def test_a_neighbour_in_membership_but_absent_from_samples_still_settles_the_absence():
    """The 362, decided: such a neighbour is a full neighbour and its registrations count.

    362 sample_ids over 368 rows of `membership` have no `samples` row on the
    real extract. A missing `samples` row means the sample has no mysql metadata
    row in this extract; it does not mean the sample is unregistered, and
    `neighbour_registers` reads `registered` and never `samples`. Excluding them
    would silently convert real absences into `LIN_NONE`.

    In `make_fixture`, MUS 500 is exactly this: registered in 11 Comet Chip,
    absent from `samples`, and the parent of TIS 203, which lacks 11.
    """
    children_of, parents_of, uuid_of, integrity, registered = _fixture_world()

    assert integrity["membership_without_sample"] == [201, 500]
    assert integrity["membership_without_sample_rows"] == 3
    assert 11 in registered[500]

    assert L.neighbour_registers(
        203, 11, children_of, parents_of, uuid_of, registered
    ) == (S.LIN_PARENT, 500, "MUS-1")


def test_a_self_loop_is_excluded_so_a_sample_cannot_settle_its_own_absence():
    """One real edge, CEL-200702FOR-1 -> itself, and it must not become a neighbour.

    Left in, `children_of[70]` would contain 70, and the lineage test would be
    satisfied by the sample's own registration -- a claim corroborating itself
    and reading in the artifact exactly like a corroborated one. The
    self-registration guard already stops the answer in that case, which is
    precisely why the exclusion needs its own test: the two defences are
    independent and the bug is invisible if only one of them is checked.
    """
    edges = _edges((10, 10), (10, 20))
    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        edges, _samples(10, 20), _membership((10, 1)))

    assert integrity["self_loop_edges"] == 1
    assert integrity["self_loop_samples"] == [10]
    assert 10 not in children_of.get(10, frozenset())
    assert 10 not in parents_of.get(10, frozenset())
    assert parents_of[10] == frozenset({20})
    assert children_of[20] == frozenset({10})


def test_duplicate_edge_rows_are_counted_because_a_set_collapses_them_silently():
    """Two rows on one (child, parent) pair. The index is a set; the count is not.

    The real extract carries 794,593 edge rows over 794,592 distinct id pairs,
    so exactly one row is collapsed today. A set is the right structure -- a
    neighbour asked about twice is one neighbour -- and the collapse is still a
    row that entered and did not leave, so it is counted.
    """
    edges = _edges((10, 20), (10, 20), (11, 20))
    children_of, _, _, integrity = L.lineage_index(
        edges, _samples(10, 11, 20), _membership((20, 1)))

    assert integrity["edge_rows"] == 3
    assert integrity["duplicate_edge_pairs"] == 1
    assert children_of[20] == frozenset({10, 11})


def test_integrity_names_every_population_even_when_all_of_them_are_empty():
    """A clean world reports zeroes rather than omitting the keys.

    A report that prints a line only when the number is non-zero cannot be read
    as evidence: an absent line and a line reading 0 are the same pixel, and the
    operator cannot tell "nothing was excluded" from "nobody looked". So every
    key is present on every call, and `main` prints all of them unconditionally.

    Every key ending `_rows`, `_edges` or `_pairs` counts ROWS. Every other key
    is a sorted list of SAMPLE IDS, and its `len()` is the sample-level figure.
    """
    edges = _edges((10, 20))
    _, _, _, integrity = L.lineage_index(
        edges, _samples(10, 20), _membership((10, 1), (20, 1)))

    assert set(integrity) == set(L.INTEGRITY_KEYS)
    assert integrity == {
        "edge_rows": 1,
        "duplicate_edge_pairs": 0,
        "self_loop_edges": 0,
        "self_loop_samples": [],
        "unresolved_edges": 0,
        "unresolved_samples": [],
        "dup_uuid_rows": 0,
        "dup_uuid_samples": [],
        "ambiguous_uuid_samples": [],
        "membership_without_sample": [],
        "membership_without_sample_rows": 0,
    }


def test_an_empty_edge_frame_yields_two_empty_indexes_and_does_not_raise():
    """The degenerate input, because `main` runs against whatever is on disk."""
    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        _edges(), _samples(10), _membership((10, 1)))

    assert children_of == {} and parents_of == {}
    assert integrity["edge_rows"] == 0
    assert set(integrity) == set(L.INTEGRITY_KEYS)


# --- extract-backed ----------------------------------------------------------


def _extract():
    if not (EXTRACT / "edges.parquet").exists():
        pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    return (pd.read_parquet(EXTRACT / "edges.parquet"),
            pd.read_parquet(EXTRACT / "samples.parquet"),
            pd.read_parquet(EXTRACT / "membership.parquet"))


def test_the_real_extract_reproduces_the_integrity_figures_this_module_documents():
    """Every number `lineage_index`'s docstring states, re-derived from the parquet.

    Two of them were carried into this task as expectations and one of those was
    wrong. 28 duplicate-uuid rows over 14 uuids and 362 membership-without-sample
    both hold. `unresolved_edges` was briefed as a figure measured over
    `CHILD_OF` and `samples`; over `DERIVED_FROM` it reads 979 rows over 243
    endpoints, and that is the number this module reports.
    """
    edges, samples, membership = _extract()
    children_of, parents_of, uuid_of, integrity = L.lineage_index(
        edges, samples, membership)

    assert (set(children_of) | set(parents_of)) <= set(uuid_of), (
        "uuid_of is not total over the index on the real extract")
    assert integrity["edge_rows"] == 794_593
    assert integrity["duplicate_edge_pairs"] == 1
    assert integrity["self_loop_edges"] == 1
    assert integrity["self_loop_samples"] == [70]
    assert integrity["unresolved_edges"] == 979
    assert len(integrity["unresolved_samples"]) == 243
    assert integrity["dup_uuid_rows"] == 28
    assert len(set(samples.uuid[samples.uuid.duplicated(keep=False)])) == 14
    assert len(integrity["ambiguous_uuid_samples"]) == 79
    assert len(integrity["membership_without_sample"]) == 362
    assert integrity["membership_without_sample_rows"] == 368


def test_every_ambiguous_neighbour_is_named_by_a_uuid_the_samples_frame_carries():
    """The measurement that overturned `min()`, re-derived rather than restated.

    For all 79 ambiguous sample_ids exactly ONE of the two uuids is that id's own
    `samples.uuid`, and the other appears nowhere in `samples.uuid` at all. The
    second assertion is the one that matters: `min()` alone would have named the
    nowhere-uuid for 38 of the 38 REGISTERED ambiguous ids, and a registered
    ambiguous id is precisely one that can be returned as a qualifying lineage
    neighbour and printed in `lineage_neighbour_uuid`.

    The `min()` counts are asserted too, so this test fails if the population
    stops being one where the two rules disagree -- at which point the rule is
    no longer evidenced and someone has to re-measure rather than inherit it.
    """
    edges, samples, membership = _extract()
    _, _, uuid_of, integrity = L.lineage_index(edges, samples, membership)

    own = dict(zip((int(s) for s in samples.sample_id), samples.uuid))
    everywhere = set(samples.uuid)
    seen = {}
    for i, u in zip(edges.child_id, edges.child_uuid):
        seen.setdefault(int(i), set()).add(u)
    for i, u in zip(edges.parent_id, edges.parent_uuid):
        seen.setdefault(int(i), set()).add(u)

    amb = integrity["ambiguous_uuid_samples"]
    assert len(amb) == 79
    assert all(len({u for u in seen[s] if u == own.get(s)}) == 1 for s in amb)
    assert not any(u in everywhere for s in amb for u in seen[s] if u != own.get(s))

    # every one of them is named by the uuid a curator can find...
    assert all(uuid_of[s] == own[s] for s in amb)
    # ...and min() alone would have named the other for the ones that matter
    registered_amb = [s for s in amb if s in set(membership.sample_id.astype(int))]
    assert len(registered_amb) == 38
    assert sum(1 for s in registered_amb if min(seen[s]) != own[s]) == 38
    assert sum(1 for s in amb if min(seen[s]) != own[s]) == 74


def test_dropping_the_unresolved_endpoints_would_delete_registered_neighbours():
    """The measurement behind the decision to KEEP them, not the decision restated.

    182 of the 243 edge endpoints with no `samples` row are registered in
    `membership`. Each one can settle a real absence for a neighbour, so a
    `samples`-resolving implementation would answer `LIN_NONE` for those
    neighbours and the loss would be invisible in every artifact.
    """
    edges, samples, membership = _extract()
    _, _, _, integrity = L.lineage_index(edges, samples, membership)

    registered_ids = set(membership.sample_id.astype(int))
    lost = sorted(set(integrity["unresolved_samples"]) & registered_ids)
    assert len(lost) == 182


def test_the_two_relations_are_not_interchangeable_on_the_real_extract():
    """The CHILD_OF ruling, checked against the data rather than asserted.

    `lineage_index` reads the DERIVED_FROM frame and `main` opens no other
    relation file. This test builds the CHILD_OF index the same way, resolving
    its uuid pairs through `nodes` and putting both relations through the same
    function, and measures the disagreement: 9,878 of the 161,531 samples
    appearing in either relation carry a different neighbour set. A test that
    only asserted which file is read would pass on a day the two relations
    agreed and prove nothing.

    The raw pair-set comparison reads 9,879. The extra sample is 70, whose
    DERIVED_FROM self-loop this module excludes and whose CHILD_OF row has no
    self-loop to exclude -- a difference between the frames, not between anyone's
    lineage. Both indexes are built by `lineage_index` here so that exclusion
    applies to both sides and the figure measures the relations rather than the
    handling.
    """
    edges, samples, membership = _extract()
    if not (EXTRACT / "childof.parquet").exists():
        pytest.skip("no childof.parquet in the extract")
    childof = pd.read_parquet(EXTRACT / "childof.parquet")
    nodes = pd.read_parquet(EXTRACT / "nodes.parquet")

    df_children, df_parents, _, _ = L.lineage_index(edges, samples, membership)

    ids = dict(zip(nodes.uuid, nodes.sample_id.astype(int)))
    co = pd.DataFrame(
        [(ids[c], ids[p], c, p, "T", "T", None, None, None)
         for c, p in zip(childof.child_uuid, childof.parent_uuid)],
        columns=S.EDGE_COLUMNS)
    co_children, co_parents, _, _ = L.lineage_index(co, samples, membership)

    everyone = set(df_children) | set(df_parents) | set(co_children) | set(co_parents)
    empty = frozenset()
    differ = [s for s in everyone
              if df_children.get(s, empty) != co_children.get(s, empty)
              or df_parents.get(s, empty) != co_parents.get(s, empty)]
    assert len(everyone) == 161_531
    assert len(differ) == 9_878


def test_the_module_opens_three_parquet_files_and_no_relation_but_DERIVED_FROM():
    """Read-only, and the CHILD_OF frame is not among the files it can reach.

    The filenames are extracted from the source rather than searched for one at
    a time, so a fourth file added later fails here and has to be named. That
    is the check that catches a CHILD_OF read being reintroduced -- searching
    for the absence of one known name passes the moment someone spells it
    differently.

    `stage0_apply` and `driver_stage0` carry live production Cypher and write to
    the graph. An import is the only way a read-only module acquires a write
    path by accident, so their absence is asserted here too.
    """
    src = (REPO / "scripts" / "assay_hygiene" / "lineage.py").read_text()

    assert set(re.findall(r"[\w.-]+\.parquet", src)) == {
        "edges.parquet", "samples.parquet", "membership.parquet",
        # named, per this docstring's own requirement, when `mode2_ceiling` was
        # added 2026-08-17. `main` hands it to `audit.registered_internal`,
        # which is the package's single crossing of the seek
        # `assay_assets.assay_id` junction, and the ceiling is exactly the
        # figure the two published readings disagreed on BECAUSE one of them
        # skipped that crossing for 17 assays. Reading it is the fix, not a
        # widening of what this module may touch: it is still read-only, and
        # `childof.parquet` is still absent, which is what this equality
        # exists to keep true.
        "assays.parquet"}
    assert "stage0_apply" not in src and "driver_stage0" not in src


# --- the Mode 2 ceiling -------------------------------------------------------


def test_the_mode_2_ceiling_counts_one_row_per_sample_and_assay_in_each_direction():
    """Hand-traced off `make_fixture()`, which reaches both directions.

    `registered_internal` over the fixture:

        100 {11}   101 {11}   102 {11}   200 {11,12}  201 {11,12}
        202 {12}   203 {12}   500 {11}   700 {12,13}  (300, 301, 400 nowhere)

    ADD_PARENT -- a parent lacking an assay one of its children holds:
        202 has {12}, child 102 holds {11}          -> (202, 11)
        500 has {11}, child 203 holds {12}          -> (500, 12)
        200, 201 and 700 already hold everything their children do; 400's only
        child is registered nowhere.                   2 rows over 2 samples

    ADD_CHILD -- a child lacking an assay one of its parents holds:
        100 -> (100,12)   101 -> (101,12)   102 -> (102,12)
        203 has {12}, parents 500 {11} and 700 {12,13} -> (203,11), (203,13)
        300 is registered nowhere, parent 200 {11,12}  -> (300,11), (300,12)
        301's parent 400 is registered nowhere.        7 rows over 5 samples

    THE GUARD IS THAT THE TWO DIRECTIONS DISAGREE ON BOTH NUMBERS. 2 against 7
    rows and 2 against 5 samples, so a swap of the two directions -- the defect
    `lineage_supports` and `neighbour_registers` were renamed to prevent -- reads
    differently rather than identically. 203 also contributes TWO rows from ONE
    scan, which is what proves the count is per (sample, assay) and not per
    neighbour: it has two parents and gains two proposals from three neighbour
    assays, and a per-neighbour count would read 3.
    """
    children_of, parents_of, _, _, registered = _fixture_world()
    ceiling = L.mode2_ceiling(children_of, parents_of, registered)

    assert set(ceiling) == set(L.CEILING_KEYS)
    assert ceiling["add_parent_rows"] == 2
    assert ceiling["add_parent_samples"] == 2
    assert ceiling["add_child_rows"] == 7
    assert ceiling["add_child_samples"] == 5
    assert ceiling["add_parent_rows"] != ceiling["add_child_rows"]
    assert ceiling["add_parent_samples"] != ceiling["add_child_samples"]

    # no (sample, assay) pair is reachable in both directions in this world, so
    # the union is the sum here and the real extract is what exercises the
    # overlap. Stated rather than left implicit: a fixture reading 0 for a key
    # cannot prove that key is computed at all.
    assert ceiling["both_directions"] == 0
    assert ceiling["union_rows"] == 9
    assert ceiling["union_samples"] == 7


@pytest.mark.skipif(not (EXTRACT / "edges.parquet").exists(),
                    reason="the extract is gitignored and is not always present")
def test_the_two_published_ceilings_differ_only_by_the_definition_of_registered():
    """55,007 / 117,463 is right. 54,780 / 116,365 dropped 17 assays' rows.

    Two independent computations of this number were published over the same
    relation and neither had been root-caused: the spec read 55,007 ADD_PARENT /
    117,463 ADD_CHILD and the plan read 54,780 / 116,365. Both are
    arithmetically correct. They differ by ONE thing, and this test derives BOTH
    from the same index so the claim is checkable rather than asserted:
    `audit.registered_internal` counts ANY membership row, and the other reading
    silently dropped the registrations of the 17 junction-less assays.

    ANY MEMBERSHIP ROW MEANS REGISTERED, so the larger pair is the correct one
    and the plan understated the ceiling by 227 and 1,098. `union_rows` closes
    it beyond doubt: the plan's own union line reads 171,013 over 115,599, which
    is what the MAPPABLE-only reading produces here to the row and the sample,
    while its two components sum to 171,145 -- so the whole block was computed
    that way rather than one figure being mistyped.

    A CEILING. Precedent cuts the weak direction to about 3% of it.
    """
    edges = pd.read_parquet(EXTRACT / "edges.parquet")
    samples = pd.read_parquet(EXTRACT / "samples.parquet")
    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")

    children_of, parents_of, _, _ = L.lineage_index(edges, samples, membership)
    any_membership = A.registered_internal(membership, assays)

    from assay_hygiene.precedent import fallback_assay_ids
    junctionless = fallback_assay_ids(assays)
    assert len(junctionless) == 17
    mappable_only = {s: v - junctionless for s, v in any_membership.items()}
    assert sum(1 for v in any_membership.values() if v) - sum(
        1 for v in mappable_only.values() if v) == 82, (
        "the two definitions must differ by the 82 samples this package "
        "documents, or this test is comparing something else")

    published = L.mode2_ceiling(children_of, parents_of, any_membership)
    dropped = L.mode2_ceiling(children_of, parents_of, mappable_only)

    assert (published["add_parent_rows"], published["add_child_rows"]) == (
        55_007, 117_463)
    assert (dropped["add_parent_rows"], dropped["add_child_rows"]) == (
        54_780, 116_365)
    assert published["union_rows"] == 172_338
    assert dropped["union_rows"] == 171_013      # the plan's own union line
    assert dropped["union_samples"] == 115_599   # ...and its own sample line
    assert published["both_directions"] == dropped["both_directions"] == 132

    # ...and neither self-loops nor duplicate edge pairs are the cause: a sample
    # that is its own neighbour has an empty gap by construction, so the raw
    # edge frame reads identically to the deduplicated index.
    raw_children, raw_parents = {}, {}
    for c, p in zip(edges.child_id, edges.parent_id):
        raw_children.setdefault(int(p), set()).add(int(c))
        raw_parents.setdefault(int(c), set()).add(int(p))
    assert L.mode2_ceiling(raw_children, raw_parents, any_membership) == published
