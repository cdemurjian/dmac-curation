# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The lineage test. Does a parent or a child already register this assay?

Second of the three deterministic tests, and it runs after the vocabulary gate
and before co-registration. Each test is named for what it establishes:

    reachability   is a sample of this TYPE ever registered in the claimed
                   assay, anywhere?            -> is the CLAIM credible at all
    lineage        does a parent or child already register it?
                                               -> is this an ABSENCE, and which
                                                  DIRECTION does it run in
    co-registration  across samples of this type in R, what share hold X?
                                               -> do R and X coexist at all

**This module establishes an absence and a direction. It establishes nothing
else, and in particular it does not establish that the claim is right.** That
is the gate's business and it has already run. Increment 1 ran lineage FIRST,
with no reachability test at all, and so filed 24 vocabulary defects -- 11
A.FLOW rows on a split `Software: flowjo` family, 13 A.SPC rows naming an assay
no A.SPC sample is registered in anywhere -- as membership write proposals. The
order is a contract precisely because of those 24.

THE RELATION IS `DERIVED_FROM`, AND THE CHOICE IS MATERIAL.

    CHILD_OF        742,534 distinct (child, parent) id pairs
    DERIVED_FROM    794,592 distinct (child, parent) id pairs
    divergence      52,184 DF-only, 126 CO-only

Measured on the 2026-08-14 extract, 9,878 of the 161,531 samples appearing in
either relation carry a DIFFERENT neighbour set under the two, both relations
read through this module so both have their self-loop excluded. The raw
comparison reads 9,879, and the extra one is sample 70: DERIVED_FROM carries a
self-loop on it and CHILD_OF does not, which is a difference in the frames and
not in anyone's lineage.

`precedent.mine_precedent` mines its rates over `DERIVED_FROM`, so a lineage
test run over the other relation would ask about a different graph than the one
its own evidence was measured on, and would move every Mode 2 figure by roughly
9%. This module reads the DERIVED_FROM frame and opens no other relation file.
The spec quotes 52,185 DF-only on a uuid-pair basis; in id space, which is the
space `membership.sample_id` speaks and so the space this module works in, it is
52,184, and the one row between the two readings is the same duplicated pair
`duplicate_edge_pairs` counts.

THE TWO DIRECTIONS ARE NOT PEERS, AND A TIE RESOLVES TO THE STRONG ONE.

    LIN_CHILD   a CHILD carries it   -> the PARENT's registration is missing
                                     -> Task 6 emits A_ADD_PARENT
    LIN_PARENT  a PARENT carries it  -> the CHILD's registration is missing
                                     -> Task 6 emits A_ADD_CHILD

Measured over the 866 flags, A_ADD_PARENT is corroborated by co-registration
88 times out of 88 and A_ADD_CHILD 15 times out of 263. On the single hop that
justified Mode 2, `TIS <- PAV`, the child's assay flows up under 74 Tissue
Collection at 0.931 while the parent's flows down under 56 Patient Visit at
0.006. The mechanism is that a sample has ONE producing assay and many
consuming ones, so "the child is in X" pins the parent tightly while "the
parent is in X" says little about any one child. So when both directions are
available `neighbour_registers` reports LIN_CHILD, and `lineage_supports` hands
the caller both lists so nothing is hidden by that choice.

THE NEIGHBOUR'S UUID COMES OUT OF THE TRAVERSAL, NOT OUT OF A `samples` JOIN.
`FINDING_COLUMNS` needs `lineage_neighbour_uuid`, and the join that looks like
the way to get it is blank for the 243 edge endpoints with no `samples` row --
182 of which are registered and can be the named neighbour. `uuid_of` is
returned beside the two indexes and `neighbour_registers` hands the uuid back
directly, so the lossy path is never the convenient one.

NOTHING DECIDES. This module proposes nothing, writes nothing and reads no
database. It builds two dicts and answers a question about them.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.lineage
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import _schema as S

# Every key `lineage_index` returns, in report order. Declared rather than
# implied by whatever the function happened to put in the dict, because the
# report prints them EVEN AT ZERO: an omitted line and a line reading 0 are the
# same pixel to an operator, and they must be able to tell "nothing was
# excluded" from "nobody looked".
#
# THE SUFFIX IS THE UNIT. A key ending `_rows`, `_edges` or `_pairs` counts
# ROWS of an input frame. Every other key is a SORTED LIST OF SAMPLE IDS and
# its `len()` is the sample-level figure. A count quoted without its unit is
# this project's signature defect -- `gate.gate_claims` renamed a parameter for
# the same reason -- and these are read side by side in one report.
INTEGRITY_KEYS = (
    "edge_rows",
    "duplicate_edge_pairs",
    "self_loop_edges",
    "self_loop_samples",
    "unresolved_edges",
    "unresolved_samples",
    "dup_uuid_rows",
    "dup_uuid_samples",
    "ambiguous_uuid_samples",
    "membership_without_sample",
    "membership_without_sample_rows",
)


def lineage_index(
    edges: pd.DataFrame,
    samples: pd.DataFrame,
    membership: pd.DataFrame,
) -> tuple[dict[int, frozenset[int]], dict[int, frozenset[int]],
           dict[int, str], dict]:
    """-> (children_of, parents_of, uuid_of, integrity), keyed by sample_id.

    Over DERIVED_FROM. `children_of[s]` is every sample DERIVED FROM `s`;
    `parents_of[s]` is every sample `s` was derived from.

    `uuid_of` IS CARRIED OUT OF THIS TRAVERSAL AND IS NOT A `samples` JOIN, and
    that is the whole reason it exists. `FINDING_COLUMNS` demands
    `lineage_neighbour_uuid`, so a consumer handed only a neighbour sample_id
    has to recover the uuid, and the natural spelling is a join through
    `samples.uuid` -- the exact path this docstring documents below as lossy.
    It would blank the uuid on the 243 unresolved endpoints, 182 of which are
    registered and can therefore BE the named neighbour, in the artifact a
    curator reads. `EDGE_COLUMNS` carries `child_uuid` / `parent_uuid` on every
    row, so the uuid costs one dict and no join. It is total over every id in
    `children_of` and `parents_of` by construction, and a test asserts that.

    THE SIGNATURE DROPS THE `assays` ARGUMENT THE BRIEF SPECIFIED, and takes
    `samples` and `membership` for one purpose each. `edges.child_id` /
    `edges.parent_id` are the graph node's own `id` property (see
    `extract.EDGES_CYPHER`), which is the same id space `membership.sample_id`
    speaks, so the index joins ids to ids and crosses no namespace. `assays`
    exists in this package to cross the seek `assay_assets.assay_id` junction
    into the dmac internal one, and this function never reads an assay id at
    all -- taking the frame would advertise a validation it does not perform.
    The caller crosses that junction once, in `audit.registered_internal`, and
    hands the result to `neighbour_registers`.

    `samples` is here for the integrity report and for nothing else: it supplies
    `dup_uuid_rows` and it is the frame `membership_without_sample` is measured
    against. `membership` is here because the brief's first draft required that
    count from a signature that could not see the frame carrying it.

    NO SAMPLE TYPE IS READ, so no second sample-type index is created.
    `gate.sample_type_index` remains the only one in the package and is
    untouched. Reachability and co-registration are per-TYPE questions; lineage
    is a per-SAMPLE one, and the type of either endpoint changes no answer here.

    THREE POPULATIONS CANNOT BE RESOLVED AGAINST `samples`, AND ALL THREE ARE
    KEPT. Measured on the 2026-08-14 extract:

      dup_uuid_rows        28 rows of `samples` over 14 uuids name two
                           sample_ids each. NOTHING IS RESOLVED and nothing is
                           aliased. An earlier draft of this task required
                           resolving such a uuid to the LOWEST of its
                           sample_ids; on this extract the graph node carries
                           the HIGHER id in all 14 cases, so "lowest wins"
                           would point the index at the endpoint with no edges
                           on it every time. Aliasing the other way was
                           rejected too: `registered` is keyed on raw
                           `membership.sample_id`, so a canonicalised index
                           beside a raw registration frame would be two
                           identities one frame apart. The bounded, stated cost
                           is that at most 14 of 163,393 samples read LIN_NONE
                           while a sibling row carries their edges, and
                           `dup_uuid_samples` names them.
      unresolved_edges     979 edge rows have an endpoint with no `samples`
                           row, over 243 distinct endpoints. THEY STAY IN THE
                           INDEX. 182 of those 243 are registered in
                           `membership`, so each can settle a real absence for
                           a neighbour; resolving edges through `samples`
                           instead would answer LIN_NONE for those neighbours
                           and the loss would show up in no artifact. A missing
                           `samples` row means the sample has no mysql metadata
                           row in this extract, not that it is unregistered.
      membership_without_  362 sample_ids over 368 membership rows have no
      sample               `samples` row. Same decision and the same reason:
                           `neighbour_registers` reads `registered` and never
                           `samples`, so these register assays like any other
                           sample.
      ambiguous_uuid_      79 edge-endpoint sample_ids carry TWO uuids across
      samples              the edge rows, 38 of them registered. SAMPLE_ID IS
                           NOT A FUNCTION TO UUID ON THIS EXTRACT, which is the
                           same 86-sample collision `gate.sample_type_index`
                           documents and is why that index is keyed on uuid.
                           44 of the 79 pairs disagree on node TYPE (`OOC` vs
                           `D.SPC`, `D.IMG` vs `D.SPC`) and all 79 carry edges
                           under both uuids, so the id-keyed neighbour set is
                           genuinely merging two nodes' lineage before any uuid
                           is chosen.

                           RESOLUTION: THE UUID THE `samples` FRAME CARRIES FOR
                           THAT SAMPLE_ID, ELSE THE LEXICOGRAPHICALLY LOWEST.
                           An earlier revision resolved by `min()` alone on the
                           stated ground that "neither uuid is more correct than
                           the other". That is a checkable claim and the check
                           goes the other way. Measured: `samples` holds exactly
                           one row per sample_id, and for 79 of 79 ambiguous ids
                           exactly ONE of the two uuids is that id's own
                           `samples.uuid` while the other appears NOWHERE in
                           `samples.uuid` at all -- not merely on a different
                           row, nowhere. `min()` alone picked the one absent
                           from `samples` for 74 of 79, and for 38 of 38 of the
                           REGISTERED ones, which are precisely the ambiguous
                           samples that can be named as a qualifying lineage
                           neighbour. So every ambiguous neighbour a curator
                           could actually be shown carried a uuid they cannot
                           look up, in the artifact they read.

                           This is a PREFERENCE, not a join, and the difference
                           is what keeps the 182-registered hole closed: both
                           candidates already came out of the edge frame, and a
                           sample with no `samples` row falls through to `min()`
                           rather than to a blank. `uuid_of` stays total. It is
                           also a no-op for the 161,451 unambiguous endpoints,
                           whose single edge uuid is used whatever `samples`
                           says -- which is what keeps the one NBSP-suffixed
                           mysql uuid (sample 243066) from displacing the
                           graph's own.

                           `min()` remains the tiebreak because it is stable
                           under any row order; last-write-wins over a frame
                           whose row order is not stable across extracts is the
                           silent-wrong-answer bug this package is shaped to
                           avoid.

                           WHICH OF THE TWO NODES HOLDS THE REGISTRATION IS
                           UNKNOWABLE FROM THESE FRAMES. `membership` is keyed
                           on sample_id, so it names the id and not the node.
                           This rule picks the uuid a curator can find; it does
                           not and cannot establish which node was registered.
                           The neighbour SET stays keyed on sample_id, because
                           keying it on (id, uuid) would count these 79 as two
                           neighbours apiece, which is worse than naming one
                           uuid and saying so.

    Two more populations leave the index and are counted:

      self_loop_edges      1 row, `CEL-190701FOR-1` -> itself. Excluded, because
                           a sample that is its own neighbour can satisfy the
                           lineage test with its own registration, and a claim
                           corroborating itself reads in the artifact exactly
                           like a corroborated one.
      duplicate_edge_      1 row. 794,593 edge rows carry 794,592 distinct id
      pairs                pairs. A set is the right structure -- a neighbour
                           asked about twice is one neighbour -- and a set
                           collapses silently, so the collapse is counted.

    The counts are NOT a partition of `edge_rows`: `unresolved_edges` is
    measured over every row read, including the rows the other two remove, so
    one row can appear in two counts. They describe the input frame, and a
    partition would hide a self-loop that is also unresolved.

    Returns PLAIN dicts, for the reason `audit.registered_internal` states: a
    `defaultdict` answers `children_of[999]` by CREATING the entry, so after one
    lookup `999 in children_of` is true of every sample ever asked about and a
    later membership test on the same index reads an isolated sample as
    connected. Callers use `.get(sid, frozenset())`.
    """
    children: dict[int, set[int]] = {}
    parents: dict[int, set[int]] = {}
    seen: set[tuple[int, int]] = set()

    edge_rows = 0
    duplicate_pairs = 0
    self_loop_edges = 0
    self_loops: set[int] = set()
    endpoints: set[int] = set()
    seen_uuids: dict[int, set[str]] = {}

    for raw_child, raw_parent, child_uuid, parent_uuid in zip(
        edges.child_id, edges.parent_id, edges.child_uuid, edges.parent_uuid
    ):
        edge_rows += 1
        child, parent = int(raw_child), int(raw_parent)
        endpoints.add(child)
        endpoints.add(parent)
        # Recorded from EVERY row, including the self-loops and duplicate pairs
        # the index drops: those rows are still evidence of how an id and a uuid
        # pair up, and a neighbour reached through a different row would
        # otherwise have no uuid at all.
        seen_uuids.setdefault(child, set()).add(str(child_uuid))
        seen_uuids.setdefault(parent, set()).add(str(parent_uuid))
        if child == parent:
            self_loop_edges += 1
            self_loops.add(child)
            continue
        if (child, parent) in seen:
            duplicate_pairs += 1
            continue
        seen.add((child, parent))
        children.setdefault(parent, set()).add(child)
        parents.setdefault(child, set()).add(parent)

    known = {int(s) for s in samples.sample_id}
    unresolved = sorted(endpoints - known)
    unresolved_set = set(unresolved)
    unresolved_edges = sum(
        1 for c, p in zip(edges.child_id, edges.parent_id)
        if int(c) in unresolved_set or int(p) in unresolved_set
    )

    dup_uuid = sorted(
        int(s) for s in samples.sample_id[samples.uuid.duplicated(keep=False)])

    missing_membership = sorted(
        {int(s) for s in membership.sample_id} - known)
    missing_set = set(missing_membership)
    missing_rows = sum(1 for s in membership.sample_id if int(s) in missing_set)

    # Prefer the uuid `samples` carries for this id, else min(). Never "the last
    # one seen": the extractor's row order is not stable across extracts, so a
    # positional rule would change the uuid printed on a curator's row between
    # two runs over identical data. `own` is absent from `us` for every
    # unambiguous endpoint whose graph uuid differs from its mysql one, and for
    # every sample with no `samples` row, and both fall through to min().
    own_uuid = dict(zip((int(s) for s in samples.sample_id), samples.uuid))
    uuid_of = {}
    for sid, us in seen_uuids.items():
        own = own_uuid.get(sid)
        uuid_of[sid] = own if own in us else min(us)
    ambiguous = sorted(sid for sid, us in seen_uuids.items() if len(us) > 1)

    integrity = {
        "edge_rows": edge_rows,
        "duplicate_edge_pairs": duplicate_pairs,
        "self_loop_edges": self_loop_edges,
        "self_loop_samples": sorted(self_loops),
        "unresolved_edges": unresolved_edges,
        "unresolved_samples": unresolved,
        "dup_uuid_rows": len(dup_uuid),
        "dup_uuid_samples": dup_uuid,
        "ambiguous_uuid_samples": ambiguous,
        "membership_without_sample": missing_membership,
        "membership_without_sample_rows": missing_rows,
    }
    # Declared once, above, and built here: a report that iterates the constant
    # and a function that fills the dict ad hoc drift apart silently, and the
    # symptom is a population that stops being printed rather than an error.
    assert set(integrity) == set(INTEGRITY_KEYS), "INTEGRITY_KEYS is out of date"

    return (
        {s: frozenset(v) for s, v in children.items()},
        {s: frozenset(v) for s, v in parents.items()},
        uuid_of,
        integrity,
    )


def lineage_supports(
    sample_id: int,
    assay_id: int,
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    registered: dict[int, set[int]],
) -> tuple[list[int], list[int]]:
    """-> (children registering it, parents registering it), each sorted ascending.

    NAMED `lineage_supports` AND NOT `neighbours_registering`, which is one
    character from `neighbour_registers` and returned a 2-tuple exactly as that
    function did. Calling the wrong one bound a `list` to `relation`,
    `relation == S.LIN_CHILD` was quietly False, and the proposal vanished with
    no exception, no warning and no row-count anomaly -- this branch's named
    failure class, reproduced at the interface two unwritten tasks dispatch
    against. The names are now structurally distinct AND the shapes are: this
    returns a 2-tuple from 5 arguments, `neighbour_registers` returns a 3-tuple
    from 6, so a call swapped in either direction raises `TypeError` on the
    argument count instead of returning something plausible.

    The full evidence behind one lineage verdict. `neighbour_registers` is this
    function collapsed to one relation and one neighbour, which is what a
    classifier keys on; these lists are what a curator reads, and Task 6 counts
    the supports behind a proposal from them -- a `(sample, assay)` pair
    reachable from two neighbours is ONE write and has to record that it had
    two supports. Both readings come from this one scan so they cannot disagree
    about which neighbours qualified. Resolve any of these ids to a uuid through
    `uuid_of`, never through a `samples` join.

    RETURNS TWO EMPTY LISTS IF `sample_id` ITSELF REGISTERS `assay_id`, and the
    guard lives here rather than in the collapse. Nothing is absent from a
    sample that already holds the assay, so there is no absence for a neighbour
    to corroborate; a guard placed only in `neighbour_registers` would leave
    Task 6 counting two supports for a proposal that does not exist.

    `assay_id` is a dmac INTERNAL assay id, and so are the ids in `registered`.
    Build `registered` with `audit.registered_internal`, which is the package's
    single crossing of the seek `assay_assets.assay_id` junction. A raw grouping
    of the membership frame speaks the other id space, and the two overlap
    numerically, so the comparison would silently read every claim as an
    absence.

    Sorted ascending because set iteration order is not part of any contract and
    the extractor's row order is not stable across extracts, so an unordered
    pick would make the artifact a curator diffs change between runs on
    identical data.
    """
    if assay_id in registered.get(sample_id, ()):
        return ([], [])
    empty: frozenset[int] = frozenset()
    return (
        sorted(n for n in children_of.get(sample_id, empty)
               if assay_id in registered.get(n, ())),
        sorted(n for n in parents_of.get(sample_id, empty)
               if assay_id in registered.get(n, ())),
    )


def neighbour_registers(
    sample_id: int,
    assay_id: int,
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    uuid_of: dict[int, str],
    registered: dict[int, set[int]],
) -> tuple[str, int | None, str | None]:
    """-> (LIN_CHILD | LIN_PARENT | LIN_NONE, neighbour sample_id, neighbour uuid).

    The last two are `None` together on `LIN_NONE`, and never `None` otherwise:
    `uuid_of` is total over every id in the two indexes by construction.

    THE UUID IS RETURNED HERE RATHER THAN LEFT TO THE CALLER because
    `FINDING_COLUMNS` requires `lineage_neighbour_uuid` and the only other way
    to get it is a `samples` join, which is blank for the 243 unresolved
    endpoints -- 182 of them registered, so any of them can be the neighbour
    this function names. Handing back an id alone made the lossy path the
    natural one. `uuid_of` comes out of `lineage_index` beside the two indexes.

    LIN_CHILD BEATS LIN_PARENT WHEN BOTH ARE AVAILABLE. LIN_CHILD means a child
    carries the assay and the PARENT's registration is missing, which is
    A_ADD_PARENT: corroborated 88 times out of 88 against 15 of 263 for the
    mirror, and 0.931 against 0.006 on the hop that justified Mode 2. Reporting
    the mirror when the strong direction is available would propose the weaker
    of two writes with no note that a better one existed. `lineage_supports`
    returns both lists whole, so the choice hides nothing.

    LIN_NONE MEANS NO ABSENCE IS ESTABLISHED IN EITHER DIRECTION, which covers
    two situations that are the same answer here and different everywhere else:
    no neighbour carries the assay, and `sample_id` already carries it itself.
    Both mean PROPOSE NOTHING, which is why they share an outcome and why
    `LINEAGE_RELATIONS` needs no fourth member -- a sample that already holds
    the assay has nothing absent to point a direction at. Task 6 still drops a
    sample already registered in the assay on its own account; the two guards
    are independent and both are cheap.

    SIX ARGUMENTS AND A 3-TUPLE, against `lineage_supports`' five and a 2-tuple.
    That is deliberate: a call swapped between the two raises `TypeError` on the
    argument count rather than returning a plausible shape. See
    `lineage_supports`.
    """
    kids, rents = lineage_supports(
        sample_id, assay_id, children_of, parents_of, registered)
    if kids:
        return (S.LIN_CHILD, kids[0], uuid_of[kids[0]])
    if rents:
        return (S.LIN_PARENT, rents[0], uuid_of[rents[0]])
    return (S.LIN_NONE, None, None)


# Every key `mode2_ceiling` returns, in report order, and declared for the same
# reason `INTEGRITY_KEYS` is: the report prints them all, and a key that stops
# being produced must break rather than stop being printed.
#
# THE SUFFIX IS THE UNIT AGAIN. `_rows` counts (sample, assay) PROPOSALS and
# `_samples` counts distinct samples; the two differ by a factor of about 1.3 on
# the real extract and quoting either without its unit is this project's
# signature defect. `both_directions` counts (sample, assay) pairs reachable in
# BOTH directions, which is why `union_rows` is smaller than the two row counts
# added together.
CEILING_KEYS = (
    "add_parent_rows", "add_parent_samples",
    "add_child_rows", "add_child_samples",
    "union_rows", "union_samples", "both_directions",
)


def mode2_ceiling(
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    registered: dict[int, set[int]],
) -> dict[str, int]:
    """How many membership proposals Mode 2 could make before precedent cuts it.

    A CEILING, and the word must accompany the numbers everywhere. Nothing here
    consults precedent, the vocabulary or the gate; it counts every (sample,
    assay) pair where a lineage neighbour registers an assay the sample lacks.
    Precedent cuts it down hard -- at `rate >= 0.5` the ADD_CHILD direction
    survives at about 3% -- so a ceiling quoted as an expected output is wrong by
    more than an order of magnitude in the weak direction.

    THIS FUNCTION EXISTS BECAUSE TWO PUBLISHED READINGS OF THIS NUMBER DISAGREED
    AND NEITHER WAS REPRODUCIBLE. The spec read 55,007 ADD_PARENT / 117,463
    ADD_CHILD over DERIVED_FROM; the plan read 54,780 / 116,365 over the same
    relation. Measured 2026-08-17, both are arithmetically correct and they
    differ by ONE THING: the definition of "registered".

        registered = audit.registered_internal(membership, assays)
            -> 55,007 / 117,463, union 172,338 rows over 115,626 samples
        the same, minus the 17 junction-less assays' registrations
            -> 54,780 / 116,365, union 171,013 rows over 115,599 samples

    ANY MEMBERSHIP ROW MEANS REGISTERED, so 55,007 / 117,463 is the correct
    reading and the plan's understated the ceiling by 227 and 1,098. The
    MAPPABLE-only set is 82 samples smaller, this is the THIRD time the two have
    been confused on this branch, and the direction of the error is worth
    naming: dropping a registration shrinks `have` AND `want` at once, so the
    damage is not one-directional and cannot be reasoned about without measuring.
    Build `registered` with `audit.registered_internal` and nothing else.

    Self-loops and duplicate edge pairs change no answer here and that is a
    property rather than luck: a sample is its own neighbour under a self-loop,
    so its gap is `registered[s] - registered[s]`, which is empty, and the
    neighbour sets are sets so a repeated pair is one neighbour. Measured, the
    raw edge frame and `lineage_index`'s deduplicated one give identical counts
    to the row. Reading `membership.assay_id` without crossing the junction gives
    55,057 / 118,141 and matches neither published figure, so that was never the
    cause.

    ONE ROW PER (SAMPLE, ASSAY), never per edge and never per neighbour. Mode 2's
    proposal is a membership row, which is per (sample, assay) however many
    neighbours support it; `lineage_supports` is what counts the supports behind
    one proposal. An edge-grained count would report the fan-out of the lineage
    graph rather than the size of the proposal set.

    `registered` is read with `.get`, so a sample registered nowhere contributes
    a full gap in the direction its neighbour supports -- which is right: it is
    exactly the sample Mode 2 has something to say about. Mode 1's population is
    a sample registered nowhere with no neighbour carrying anything.
    """
    add_parent: set[tuple[int, int]] = set()
    add_child: set[tuple[int, int]] = set()
    empty: set[int] = set()

    for parent, kids in children_of.items():
        have = registered.get(parent, empty)
        for kid in kids:
            for assay_id in registered.get(kid, empty):
                if assay_id not in have:
                    add_parent.add((parent, assay_id))
    for child, rents in parents_of.items():
        have = registered.get(child, empty)
        for rent in rents:
            for assay_id in registered.get(rent, empty):
                if assay_id not in have:
                    add_child.add((child, assay_id))

    union = add_parent | add_child
    out = {
        "add_parent_rows": len(add_parent),
        "add_parent_samples": len({s for s, _ in add_parent}),
        "add_child_rows": len(add_child),
        "add_child_samples": len({s for s, _ in add_child}),
        "union_rows": len(union),
        "union_samples": len({s for s, _ in union}),
        "both_directions": len(add_parent & add_child),
    }
    assert set(out) == set(CEILING_KEYS), "CEILING_KEYS is out of date"
    return out


def main(extract_dir: str = "assay-hygiene/extract") -> int:
    """Build the index off the extract on disk and print its integrity report.

    Read-only in the strongest sense available: it opens three files, writes
    none, proposes nothing and touches no database. It exists so the numbers
    this module's docstring states can be re-derived by anyone in one command,
    and so the excluded populations are printed EVEN AT ZERO.
    """
    from .audit import registered_internal   # local: keeps the import light

    d = Path(extract_dir)
    edges = pd.read_parquet(d / "edges.parquet")
    samples = pd.read_parquet(d / "samples.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")

    children_of, parents_of, uuid_of, integrity = lineage_index(
        edges, samples, membership)

    connected = set(children_of) | set(parents_of)
    assert connected <= set(uuid_of), (
        "uuid_of must be total over the index; a neighbour with no uuid would "
        "reach FINDING_COLUMNS.lineage_neighbour_uuid blank")
    print(f"DERIVED_FROM lineage over {integrity['edge_rows']:,} edge rows: "
          f"{len(connected):,} samples with at least one neighbour "
          f"({len(children_of):,} with a child, {len(parents_of):,} with a parent)")
    print("integrity -- every population, printed at zero as well:")
    for key in INTEGRITY_KEYS:
        value = integrity[key]
        if isinstance(value, list):
            head = ", ".join(str(v) for v in value[:10])
            more = " ..." if len(value) > 10 else ""
            print(f"  {key:<32} {len(value):>8,}  [{head}{more}]")
        else:
            print(f"  {key:<32} {value:>8,}")
    ceiling = mode2_ceiling(children_of, parents_of,
                            registered_internal(membership, assays))
    print("MODE 2 CEILING, unfiltered by precedent -- a ceiling, not a forecast:")
    for key in CEILING_KEYS:
        print(f"  {key:<32} {ceiling[key]:>8,}")
    print("  \"registered\" here is ANY membership row, crossed to the internal "
          "namespace by audit.registered_internal. The MAPPABLE-only definition "
          "reads 54,780 / 116,365 and is the only difference between the two "
          "published figures for this number.")
    print("no row here was dropped: the unresolved endpoints, the duplicate "
          "uuids and the membership rows without a sample all stay in play, "
          "because a sample with no `samples` row can still be registered and "
          "can still settle a real absence")
    print("nothing was written, and this module proposes no membership change")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
