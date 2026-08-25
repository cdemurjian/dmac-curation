# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage B. Mine the sample-type -> assay -> sample-type map from what exists.

One question per (project, hop, internal assay): when the child is in this
assay, how often is the parent in it too. That is `propagation_rate`, and it is
the evidence a Mode 2 verdict rests on.

Keyed on `internal_assay_id`. dmac.internal_assays is 137 rows under 137
distinct titles and is canonical; seek_production.assays is 458 rows under 291
titles (295 raw; 291 once case and whitespace are normalised as
`_schema.normalise_value` does, which is the count meant here) because the same
logical assay is instantiated once per study. Keying on
assays.id fragments the evidence; keying on the raw title speaks a different
namespace from DERIVED_FROM.internal_assay_title and leaves findings and edges
unreconcilable.

`assay_index` landed here one task ahead of the rest of stage B, because it is
the single definition of "which internal assay is this seek assay", and a second
copy of that definition is a silent-wrong-answer bug rather than a duplication
nit. See vocabulary_evidence.py, which was the second caller and the reason this
file existed before `mine_precedent` did.

The output is independently useful. It answers "what assay normally connects
D.IMG to TIS in this project" as a lookup, mined rather than hand-authored, and
nothing like it exists today.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S


def fallback_assay_ids(assays: pd.DataFrame) -> set[int]:
    """The resolved ids that are SEEK `assays.id`s rather than dmac internal ones.

    These are exactly the ids `assay_index` invents for the 17 junction-less
    records, so a value here is a value that reaches a consumer's resolved set
    for one of those records. An id in this set names a registration whose
    internal identity is UNKNOWN -- not one known to differ from anything.

    Split out of `assay_index`, which now consumes it, so that
    `pd.isna(internal_assay_id)` -- the predicate deciding which id space a
    registration belongs to -- has exactly ONE definition in the package. A
    second copy of that predicate is the same class of bug as a second
    definition of "registered", which is what produced 13 spurious findings
    earlier in this increment.

    Mode 3 is the caller that needs it separately. `assay_index`'s collision
    guard makes a false AGREEMENT impossible, but it does nothing about a false
    CONTRADICTION: an id in one namespace can never match an id in the other, so
    it always reads as disagreement. See `audit.audit_contradictions`.
    """
    return {
        int(aid)
        for aid, iaid in zip(assays.assay_id, assays.internal_assay_id)
        if pd.isna(iaid)
    }


def assay_index(assays: pd.DataFrame) -> dict[int, tuple[int, int, str]]:
    """assay_id -> (project_id, internal_assay_id, internal_assay_title).

    17 assay records have no junction row and resolve to no internal id. They
    fall back to their own (assay_id, title), matching neo4j_sync.py:1418-1431
    (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge), so the rule key is never
    null. Dropping them would violate the spec's binding "nothing is dropped
    silently"; leaving the key null would collapse all 17 into a single
    meaningless rule.

    The fallback means the returned internal id is NOT always a
    dmac.internal_assays id: on those 17 it is a seek assays.id, in a different
    id space. That is deliberate and it is what the graph itself does. Every
    consumer must use THIS function rather than filtering on
    `internal_assay_id.notna()`, or two parts of one run will disagree about
    which samples are registered.

    Measured on the real extract 2026-08-14, filtering instead of falling back
    loses 279 of 214,124 sample-assay registrations across 239 samples, and
    drops 82 samples out of the registered population entirely. That is 0.13%
    and it is not harmless. `Type: m397` has 79 carriers. Filtered, 13 of them
    vanish from the registered population entirely -- they are registered under
    fallback assay 481 and nowhere else -- so the term reads `n_registered` 66
    at share 1.00, a unanimous single candidate. Under this function the same
    term reads 79 registered, 2 candidates, share 0.835, which is a term you
    leave alone. The filtered reading is the one that recommends a proposal
    contradicting 13 samples' actual registration.
    See vocabulary_evidence.build_evidence.

    RAISES `ValueError` if a fallback id is also a genuine internal id. That
    invariant is what makes the fallback safe, and it holds today only by luck
    of numbering: the 17 junction-less assays sit at 466-482 and the genuine
    internal ids run 1-188. It is checked HERE, in the single funnel every
    consumer passes through, rather than only in a test, because the test can
    only run beside a 17 MB gitignored extract and an operator's real run
    cannot. See tests/test_assay_hygiene_precedent.py for the extract-backed
    case that proves the live data satisfies it.
    """
    out: dict[int, tuple[int, int, str]] = {}
    # One definition of "this record has no junction row", shared with every
    # other caller that has to reason about the two id spaces.
    fallback = fallback_assay_ids(assays)
    genuine: set[int] = set()
    for aid, pid, title, iaid, ititle in zip(
        assays.assay_id, assays.project_id, assays.title,
        assays.internal_assay_id, assays.internal_assay_title,
    ):
        if int(aid) in fallback:
            out[int(aid)] = (int(pid), int(aid), str(title))
        else:
            out[int(aid)] = (int(pid), int(iaid), str(ititle))
            genuine.add(int(iaid))
    # set intersection, never min()/max(): a fully-fixed junction table leaves
    # `fallback` empty, and a range comparison would raise ValueError on the
    # empty sequence in exactly the state this message tells the operator to
    # reach. An empty intersection is simply falsy.
    collision = sorted(fallback & genuine)
    if collision:
        raise ValueError(
            f"{len(collision)} junction-less assay(s) fall back to a seek "
            f"assays.id that is also a genuine dmac.internal_assays id: "
            f"{collision}. RULE_KEY carries project_id, so this merges the "
            "two assays' precedent only where both occur in the SAME project "
            "-- which is not hypothetical: 12 such pairs already share a hop "
            "within one project. Fix the junction rows in "
            "dmac.assays_internal_assays, or give the fallback its own id "
            "space."
        )
    return out


def membership_index(membership: pd.DataFrame) -> dict[int, set[int]]:
    """sample_id -> the set of seek assay_ids it is registered in.

    Returns a plain dict and not the defaultdict it is built as: callers ask
    `memb.get(id, frozenset())` about samples that are registered nowhere, and
    a defaultdict would answer by CREATING an empty entry, so an "is this
    sample registered" test would come back true for every sample ever asked
    about. `tests/test_assay_hygiene_precedent.py` pins `999 not in idx`.
    """
    idx: dict[int, set[int]] = defaultdict(set)
    for sample_id, assay_id in zip(membership.sample_id, membership.assay_id):
        idx[int(sample_id)].add(int(assay_id))
    return dict(idx)


def mine_precedent(
    edges: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (project, hop, internal assay), from the edges that exist.

    NO GROUPBY, AND THAT IS THE POINT. `internal_assay_id` is nullable at
    source -- 17 assay records have no junction row -- and it is a RULE_KEY
    component. `edges.groupby(S.RULE_KEY)` defaults to `dropna=True`, so the
    natural pandas spelling of this function would discard every observation
    keyed on one of those 17, silently, with no error and a table that still
    looks right. That violates the spec's binding "nothing is dropped
    silently". Counting into a dict makes a null key impossible by
    construction rather than by remembering a keyword argument, and
    `assay_index`'s fallback is what supplies the non-null key. Do not
    reintroduce a groupby here.

    An edge is read from BOTH ends. For each assay either endpoint belongs to,
    the edge lands in exactly one of three counters: `n_both` (co-registered),
    `n_child_only`, `n_parent_only`. So `propagation_rate` = both / (both +
    child_only) asks "given the child is in this assay, how often is the
    parent", and `reverse_rate` asks the mirror. An edge with a wholly
    unregistered child still contributes `n_parent_only`, which is real
    evidence and is what the mode-1 population is ruled on; only an edge with
    BOTH endpoints unregistered contributes nothing, because there is no assay
    to count into.

    THOSE THREE COUNT EDGES, AND TWO OF THEM ARE ALSO REPORTED IN SAMPLES.
    `n_child_only_samples` is the distinct PARENTS the child-only edges name
    and `n_parent_only_samples` is the distinct CHILDREN the parent-only edges
    name -- in each case the endpoint that is NOT registered, which is the
    endpoint a Mode 2 proposal would be made about. Measured over the whole
    extract, the two grains differ by an order of magnitude:

        n_child_only, summed over the 961 rules  (EDGES)     666,939
        distinct (parent, internal assay) those edges raise    55,032   12.1x
        largest single rule    303,866 edges over    616 samples         493x
        largest fan-out ratio    1,575 edges over      3 samples         525x

    THAT SECOND LINE READ 55,007 UNTIL 2026-08-25 AND 55,007 IS A DIFFERENT
    QUANTITY. Re-derived at the edge grain the child-only edges raise 55,032
    distinct (parent, internal assay) pairs, and 55,057 at the SEEK assay grain.
    55,007 is `lineage.mode2_ceiling`'s `add_parent_rows`, which walks the
    lineage index rather than the edge frame and lands 25 lower. The two
    corroborate each other and are not the same number: every child-only edge
    names a parent the house has NOT registered in that assay, which is the
    definition of an ADD_PARENT candidate. Summing `n_child_only_samples` instead gives 57,946,
    because a rule is scoped to one (project, hop) and a parent with children
    of two types is counted once per rule.

    THE INFLATION IS FAN-OUT AND NOT REFUSAL, which is the reason the sample
    counts exist at all. The denominator is made of the proposals themselves,
    so "the house declined this N times" is not a reading of it at any grain.
    The worked case is `(2, D.ADCD, TIS, 153)` -- the cohort a reviewer sees as
    `ALT|TIS|ADFP` -- which reads `n_child_only` 1,300 over
    `n_child_only_samples` 325: 325 parents times 4 children, one sample
    counted four times, zero refusals. `dossier.build_dossiers` renders both
    numbers and says which is which; until 2026-08-21 it rendered only the edge
    count, under a reading that called it repeated refusal.

    NEITHER RATE IS RECOMPUTED OVER THEM AND THE ROW ORDER IS UNCHANGED. The
    fan-out inflates numerator and denominator together, so regraining the RATE
    moves it materially on only 8 of the 270 hops carrying >= 50 forward edge
    observations (median |delta| 0.000, max 0.622; 119 clear a 0.50 floor
    against 121 regrained). The defect is in the count reviewers were shown,
    not in the rate that ranked them, and a rate change here would move a
    ranking 1,012 agent adjudications and 128 operator rulings already rest on.

    A SET PER KEY BESIDE EACH INTEGER, not a post-hoc groupby over the frame.
    The integers and the sets are filled in ONE pass off the same branch, so
    the two grains cannot come to describe different edges -- which is the
    failure a second traversal invites and the reason this function has no
    groupby anywhere.
    """
    memb = membership_index(membership)
    ainfo = assay_index(assays)

    # Checked up front and not per-edge. This was a `continue` inside the loop,
    # which made it the module's one silent drop, against the spec's binding
    # "nothing is dropped silently". Hoisting it also widens it: the loop
    # version could only trip on an assay_id reached by an edge endpoint, so a
    # registration on a sample with no edges was invisible either way. 0 of the
    # 173 membership assay_ids hit this today; the list is reported whole
    # rather than one id at a time so a broken extract is diagnosed in one run.
    unknown = sorted({int(a) for a in membership.assay_id} - set(ainfo))
    if unknown:
        raise ValueError(
            f"membership registers samples in {len(unknown)} assay(s) absent "
            f"from the assays frame: {unknown}. Those registrations cannot be "
            "resolved to an internal assay, and skipping them would drop "
            "evidence silently. Re-extract so the two frames agree."
        )

    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])
    # The sample-grained halves of the two directional counters. Keyed and
    # branched exactly as `counts` is, one line further down the same `if`, so
    # a future edit cannot move an edge into one grain and not the other. The
    # UNREGISTERED endpoint goes in each: the parent on a child-only edge, the
    # child on a parent-only one.
    child_only_parents: dict[tuple, set[int]] = defaultdict(set)
    parent_only_children: dict[tuple, set[int]] = defaultdict(set)
    titles: dict[tuple, str] = {}

    for child_id, parent_id, child_type, parent_type in zip(
        edges.child_id, edges.parent_id, edges.child_type, edges.parent_type
    ):
        ca = memb.get(int(child_id), frozenset())
        pa = memb.get(int(parent_id), frozenset())
        for assay_id in ca | pa:
            project_id, iaid, ititle = ainfo[assay_id]
            key = (project_id, str(child_type), str(parent_type), iaid)
            titles[key] = ititle
            if assay_id in ca and assay_id in pa:
                counts[key][0] += 1
            elif assay_id in ca:
                counts[key][1] += 1
                child_only_parents[key].add(int(parent_id))
            else:
                counts[key][2] += 1
                parent_only_children[key].add(int(child_id))

    rows = []
    for key, (both, child_only, parent_only) in counts.items():
        project_id, child_type, parent_type, iaid = key
        fwd_den = both + child_only
        rev_den = both + parent_only
        rows.append({
            "project_id": project_id,
            "child_type": child_type,
            "parent_type": parent_type,
            "internal_assay_id": iaid,
            "internal_assay_title": titles[key],
            "n_both": both,
            "n_child_only": child_only,
            "n_child_only_samples": len(child_only_parents.get(key, ())),
            "n_parent_only": parent_only,
            "n_parent_only_samples": len(parent_only_children.get(key, ())),
            # Both rates stay over the EDGE counts. See the docstring: the
            # fan-out inflates numerator and denominator together, and a
            # regrained rate would move a ranking that 1,012 adjudications and
            # the operator's 128 rulings already rest on.
            "propagation_rate": (both / fwd_den) if fwd_den else 0.0,
            "reverse_rate": (both / rev_den) if rev_den else 0.0,
        })

    out = pd.DataFrame(rows, columns=S.PRECEDENT_COLUMNS)
    # RULE_KEY rides behind the two evidence columns as a tiebreak. The
    # evidence order is unchanged; the tiebreak only orders rows the evidence
    # columns leave equal, and 708 of the 961 real rules sit in such a group,
    # 440 of them at (0, 0).
    #
    # NOT because the sort is unstable -- an earlier version of this comment
    # said that and it is wrong. `sort_values` over a LIST of columns goes
    # through `np.lexsort` and IS stable; `kind` applies only to a single-column
    # sort (verified on pandas 3.0.5). So the two-column sort is perfectly
    # reproducible for a GIVEN input order, and the hazard is the input order
    # itself: with no tiebreak those 708 rows come out in `counts` insertion
    # order, which is the order edges happen to sit in edges.parquet.
    # test_assay_hygiene_stage0.py already records that "the extractor's row
    # order is not stable across extracts". Measured: permuting the edge frame
    # changes the two-column output while leaving the full-key output
    # byte-identical, so a curator diffing this artifact between extracts would
    # read the difference as change. How MANY rows move under a permutation is
    # a property of the permutation and not of the code -- 615 at
    # random_state=7, and 631 / 635 / 621 at seeds 0 / 1 / 42 -- so no bare
    # count belongs in that sentence. The seed-free figure is the two sorts
    # against each other on the SAME as-extracted input: 647 of the 961 rows
    # land at a different index. Same reasoning as vocabulary_evidence's
    # three-key sort, and pinned by
    # test_row_order_does_not_depend_on_the_order_edges_arrive_in.
    return out.sort_values(
        ["n_both", "n_child_only"] + S.RULE_KEY,
        # built from RULE_KEY, not six hard-coded booleans: a fifth key
        # component would otherwise raise at runtime rather than at review
        ascending=[False, False] + [True] * len(S.RULE_KEY),
        ignore_index=True,
    )


def main(extract_dir: str = "assay-hygiene/extract",
         out_path: str = "assay-hygiene/precedent.csv") -> None:
    d = Path(extract_dir)
    out = mine_precedent(
        pd.read_parquet(d / "edges.parquet"),
        pd.read_parquet(d / "membership.parquet"),
        pd.read_parquet(d / "assays.parquet"),
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    # "with precedent" means n_both > 0: a project/hop pair whose every
    # observation is child_only or parent_only has a rule row but has never
    # once been seen co-registered, so it is evidence AGAINST propagating, not
    # precedent for it. The looser count is 306 here.
    #
    # It says "project/hop pairs" and not "hops" because the unit is the
    # TRIPLE (project_id, child_type, parent_type). The extract happens to
    # contain exactly 213 distinct (child_type, parent_type) pairs, so the
    # bare word "hops" made this line read as "every hop in the graph has
    # precedent" against a coincidence. The true type-pair figure is 153 of
    # 208.
    hops = out[out.n_both > 0][
        ["project_id", "child_type", "parent_type"]].drop_duplicates()
    print(f"{len(out)} rules over {len(hops)} project/hop pairs "
          f"with precedent -> {out_path}")
    print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
