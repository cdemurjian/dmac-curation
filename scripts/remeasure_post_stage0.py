# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Re-derive every A-F statistic against the post-stage-0 graph.

The A-F plan's figures -- 87.8% unambiguous, the 97.2% disjoint split, a
216,114-edge backtest population, the whole stage B distribution -- were all
measured before stage 0 ran. Stage 0 added 90,534 edges of which 82,663 are
labelled, and its largest hop (D.FLOW -> D.FCS, 66,529 edges, 73% of the
addition) did not exist in the graph at all. So the precedent tables A-F mines
were computed over a graph missing its biggest hop, and no threshold may be
selected from those numbers.

This is a measurement, not a stage: read-only over the extract, no writes, no
decisions. It exists so the rewritten plan can carry re-derived anchors instead
of stale ones.

    uv run scripts/remeasure_post_stage0.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

EXTRACT = Path("assay-hygiene/extract")


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def main() -> int:
    edges = pd.read_parquet(EXTRACT / "edges.parquet")
    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")

    print(f"edges                {len(edges):>10,}")
    print(f"membership rows      {len(membership):>10,}")
    print(f"assays               {len(assays):>10,}")

    # --- assay_id -> internal identity, with the documented fallback ----------
    # 17 assays have no junction row and resolve to no internal_assay_id. They
    # fall back to (assay_id, title), the same rule neo4j_sync.py:1418-1431
    # (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge) uses, so the key is
    # never null and nothing is dropped.
    no_junction = assays.internal_assay_id.isna().sum()
    ainfo: dict[int, tuple[int, int, str]] = {}
    for a, p, t, ia, it in zip(assays.assay_id, assays.project_id, assays.title,
                               assays.internal_assay_id, assays.internal_assay_title):
        if pd.isna(ia):
            ainfo[int(a)] = (int(p), int(a), str(t))       # fallback identity
        else:
            ainfo[int(a)] = (int(p), int(ia), str(it))
    print(f"assays w/o junction row {no_junction:>7,}  (fall back to (assay_id, title))")
    print(f"distinct internal ids {len({v[1] for v in ainfo.values()}):>9,}")

    # --- membership index -----------------------------------------------------
    memb: dict[int, set[int]] = defaultdict(set)
    for s, a in zip(membership.sample_id, membership.assay_id):
        memb[int(s)].add(int(a))
    print(f"samples with >=1 assay {len(memb):>8,}")

    # --- labelled / dark ------------------------------------------------------
    labelled = int(edges.edge_internal_assay_id.notna().sum())
    dark = len(edges) - labelled
    print()
    print("--- labelled vs dark -------------------------------------------------")
    print(f"labelled             {labelled:>10,}  {pct(labelled, len(edges))}")
    print(f"dark                 {dark:>10,}  {pct(dark, len(edges))}")

    # --- why is a dark edge dark? --------------------------------------------
    # The 2026-08-13 root cause: the overwhelming majority of dark edges have
    # BOTH endpoints registered, in assays that do not intersect -- not a
    # missing registration.
    both_reg = child_only = parent_only = neither = disjoint = shared = 0
    for c, p, ia in zip(edges.child_id, edges.parent_id, edges.edge_internal_assay_id):
        if pd.notna(ia):
            continue
        ca = memb.get(int(c), set())
        pa = memb.get(int(p), set())
        if ca and pa:
            both_reg += 1
            if ca & pa:
                shared += 1
            else:
                disjoint += 1
        elif ca:
            child_only += 1
        elif pa:
            parent_only += 1
        else:
            neither += 1

    print()
    print("--- dark edges, by cause --------------------------------------------")
    print(f"both endpoints registered   {both_reg:>10,}  {pct(both_reg, dark)}")
    print(f"  ... in DISJOINT assays    {disjoint:>10,}  {pct(disjoint, dark)}")
    print(f"  ... sharing an assay      {shared:>10,}  {pct(shared, dark)}")
    print(f"only the child registered   {child_only:>10,}  {pct(child_only, dark)}")
    print(f"only the parent registered  {parent_only:>10,}  {pct(parent_only, dark)}")
    print(f"neither registered          {neither:>10,}  {pct(neither, dark)}")

    # --- backtest population --------------------------------------------------
    # The spec's 216,114 is "full assay + protocol" (design doc line 107): an
    # edge-property count, NOT a membership count. Measuring "both endpoints
    # registered" instead answers a different question and returns roughly
    # 778k, which would look like the population had quadrupled.
    full = int((edges.edge_internal_assay_id.notna()
                & edges.edge_protocol_id.notna()).sum())
    both_ends = sum(
        1 for c, p in zip(edges.child_id, edges.parent_id)
        if memb.get(int(c)) and memb.get(int(p))
    )
    print()
    print("--- backtest population ---------------------------------------------")
    print(f"full assay + protocol (the spec's 216,114) {full:>10,}  {pct(full, len(edges))}")
    print(f"    separately: both endpoints registered  {both_ends:>10,}  "
          f"{pct(both_ends, len(edges))}")

    # --- unambiguous ----------------------------------------------------------
    # The spec's 87.8% is per-EDGE: "child has exactly one assay" (design doc
    # line 655). A per-HOP reading -- hops where exactly one assay carries the
    # precedent -- also lands on 87.8% here, which is a coincidence and not a
    # confirmation. Report both, labelled.
    child_one = child_many = child_none = 0
    for c in edges.child_id:
        n = len(memb.get(int(c), ()))
        if n == 1:
            child_one += 1
        elif n:
            child_many += 1
        else:
            child_none += 1
    print()
    print("--- unambiguous, per EDGE (the spec's definition) --------------------")
    print(f"child in exactly one assay {child_one:>10,}  {pct(child_one, len(edges))}")
    print(f"child in two or more       {child_many:>10,}  {pct(child_many, len(edges))}")
    print(f"child in none              {child_none:>10,}  {pct(child_none, len(edges))}")

    # The 87.8% came from an adjudication dry run, and adjudication only sees
    # edges that need a decision -- the dark ones. Scoped that way the figure
    # means something different again. The spec does not say which scope it
    # used, which is why all three are reported rather than one asserted.
    d_one = d_many = d_none = 0
    for c, ia in zip(edges.child_id, edges.edge_internal_assay_id):
        if pd.notna(ia):
            continue
        n = len(memb.get(int(c), ()))
        if n == 1:
            d_one += 1
        elif n:
            d_many += 1
        else:
            d_none += 1
    print()
    print("--- the same, scoped to DARK edges (what adjudication sees) ----------")
    print(f"child in exactly one assay {d_one:>10,}  {pct(d_one, dark)}")
    print(f"child in two or more       {d_many:>10,}  {pct(d_many, dark)}")
    print(f"child in none              {d_none:>10,}  {pct(d_none, dark)}")

    # --- stage B precedent distribution --------------------------------------
    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])
    titles: dict[tuple, str] = {}
    for c, p, ct, pt in zip(edges.child_id, edges.parent_id,
                            edges.child_type, edges.parent_type):
        ca = memb.get(int(c), set())
        pa = memb.get(int(p), set())
        for aid in ca | pa:
            info = ainfo.get(aid)
            if info is None:
                continue
            project_id, iaid, ititle = info
            key = (project_id, str(ct), str(pt), iaid)
            titles[key] = ititle
            if aid in ca and aid in pa:
                counts[key][0] += 1
            elif aid in ca:
                counts[key][1] += 1
            else:
                counts[key][2] += 1

    rows = []
    for key, (both, child_o, parent_o) in counts.items():
        den = both + child_o
        rows.append({
            "project_id": key[0], "child_type": key[1], "parent_type": key[2],
            "internal_assay_id": key[3], "internal_assay_title": titles[key],
            "n_both": both, "n_child_only": child_o, "n_parent_only": parent_o,
            "propagation_rate": (both / den) if den else 0.0,
        })
    prec = pd.DataFrame(rows)
    print()
    print("--- stage B precedent -----------------------------------------------")
    print(f"rules mined          {len(prec):>10,}")

    # Per-HOP ambiguity: for this (project, hop), how many assays carry
    # evidence. Where two or more do, the deterministic band cannot decide and
    # the tiebreak or the LLM slice is reached. This is NOT the spec's 87.8%,
    # which is per-edge; see above.
    hop = prec[prec.n_both > 0].groupby(
        ["project_id", "child_type", "parent_type"], dropna=False
    ).size()
    unambiguous = int((hop == 1).sum())
    print(f"hops with precedent  {len(hop):>10,}")
    print(f"  exactly one assay  {unambiguous:>10,}  {pct(unambiguous, len(hop))}")
    print(f"  two or more        {len(hop) - unambiguous:>10,}  "
          f"{pct(len(hop) - unambiguous, len(hop))}")

    for lo in (0.95, 0.90, 0.80, 0.608):
        sel = prec[(prec.propagation_rate >= lo) & (prec.n_both > 0)]
        print(f"rules with rate >= {lo:<5}  {len(sel):>6,}  "
              f"covering {int(sel.n_child_only.sum()):>8,} child-only edges")

    out = Path("assay-hygiene/precedent-remeasured.csv")
    prec.sort_values(["n_both", "n_child_only"], ascending=False).to_csv(out, index=False)
    print(f"\nwrote {out}")

    # The plan's named sanity anchor, re-measured.
    titr = prec[(prec.child_type == "D.TITR") & (prec.parent_type == "TIS")]
    if not titr.empty:
        print("\n--- plan anchor: D.TITR -> TIS --------------------------------------")
        print(titr.sort_values("n_both", ascending=False)
                  .head(5)[["internal_assay_id", "internal_assay_title",
                            "n_both", "n_child_only", "propagation_rate"]]
                  .to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
