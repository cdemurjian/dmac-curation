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
    """
    out: dict[int, tuple[int, int, str]] = {}
    for aid, pid, title, iaid, ititle in zip(
        assays.assay_id, assays.project_id, assays.title,
        assays.internal_assay_id, assays.internal_assay_title,
    ):
        if pd.isna(iaid):
            out[int(aid)] = (int(pid), int(aid), str(title))
        else:
            out[int(aid)] = (int(pid), int(iaid), str(ititle))
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
    """
    memb = membership_index(membership)
    ainfo = assay_index(assays)

    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])
    titles: dict[tuple, str] = {}

    for child_id, parent_id, child_type, parent_type in zip(
        edges.child_id, edges.parent_id, edges.child_type, edges.parent_type
    ):
        ca = memb.get(int(child_id), frozenset())
        pa = memb.get(int(parent_id), frozenset())
        for assay_id in ca | pa:
            info = ainfo.get(assay_id)
            if info is None:
                continue      # assay absent from the extract; skip rather than guess
            project_id, iaid, ititle = info
            key = (project_id, str(child_type), str(parent_type), iaid)
            titles[key] = ititle
            if assay_id in ca and assay_id in pa:
                counts[key][0] += 1
            elif assay_id in ca:
                counts[key][1] += 1
            else:
                counts[key][2] += 1

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
            "n_parent_only": parent_only,
            "propagation_rate": (both / fwd_den) if fwd_den else 0.0,
            "reverse_rate": (both / rev_den) if rev_den else 0.0,
        })

    out = pd.DataFrame(rows, columns=S.PRECEDENT_COLUMNS)
    # RULE_KEY rides behind the two evidence columns as a tiebreak. The
    # evidence order is unchanged; the tiebreak only orders rows that the
    # evidence columns leave equal, and 708 of the 961 real rules sit in such
    # a tie group, 440 of them at (0, 0). Without it their order falls to
    # `sort_values`' unstable quicksort over dict insertion order, so the
    # artifact a curator diffs between runs is ordered by an implementation
    # detail. Same reasoning as vocabulary_evidence's three-key sort.
    return out.sort_values(
        ["n_both", "n_child_only"] + S.RULE_KEY,
        ascending=[False, False, True, True, True, True],
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
    # "with precedent" means n_both > 0: a hop whose every observation is
    # child_only or parent_only has a rule row but has never once been seen
    # co-registered, so it is evidence AGAINST propagating, not precedent for
    # it. Reporting the looser count instead (306 here, every project/hop pair
    # with any row at all) would overstate what stage C has to work with.
    hops = out[out.n_both > 0][
        ["project_id", "child_type", "parent_type"]].drop_duplicates()
    print(f"{len(out)} rules over {len(hops)} hops with precedent -> {out_path}")
    print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
