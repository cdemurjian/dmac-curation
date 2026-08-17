# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Reproduce the absence-versus-contradiction figures in the three-mode spec.

Read-only over `assay-hygiene/extract/` and `assay-hygiene/mode3-*.csv`. It
writes one csv to `assay-hygiene/` and touches nothing else.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python scripts/measure_absence_vs_contradiction.py

WHY THIS EXISTS. Increment 1 shipped a Mode 3 audit that tests
`claimed_assay not in registered_assays`. That is an ABSENCE test, and the spec
sells Mode 3 as finding CONTRADICTIONS. The gap was found by the operator, who
observed that a PAV sample with tissue collected from it belongs in Patient
Visit AND Tissue Collection, one incoming and one outgoing, so the absence of
the second is a missing registration rather than a contradicted one.

This script applies two deterministic tests to every flag and reports how the
866 actually divide. Both tests are cheap, neither needs a model, and they are
independent: one asks the graph about this sample's neighbours, the other asks
the graph about this sample TYPE's habits.

  LINEAGE        does a parent or child already register the claimed assay?
                 If so the claim is corroborated by the sample's own lineage
                 and what is missing is a registration. Mode 2 shaped.

  COMPATIBILITY  across every sample of this type registered in R, what share
                 ALSO register the claimed X? A high rate means the two assays
                 routinely coexist, so absence is the anomaly. A rate of zero
                 on a well supported population means they never coexist, which
                 is the only evidence in this pipeline that actually supports
                 the word "contradiction".

SCOPE, because this package has been bitten four times by two meanings under
one name. Every figure printed is scoped to THE 866 ROWS OF
`mode3-contradictions.csv` as produced by increment 1 at its default tiers, and
never to the graph as a whole. `co_reg_pop` is a SAMPLE count of the sample
type, not an edge count and not a row count.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# A co-registration rate computed over a handful of samples is noise. 30 is a
# reporting floor, not a tuned threshold: it exists so a rate of 0.000 over 4
# samples is never read as "these assays never coexist". Rows below it are
# reported as their own band and are never called a contradiction.
MIN_SUPPORT = 30

# Above this share of the type's population, the two assays plainly coexist.
# Deliberately not tuned. The spec's position is that thresholds are an OUTPUT
# of a backtest curve, and no backtest exists for this axis yet, so this is a
# reporting band and the residue it produces is reviewed by a human.
CO_OCCUR = 0.5


def load(base: Path) -> dict[str, pd.DataFrame]:
    ex = base / "extract"
    flags_path = base / "mode3-contradictions.csv"
    if not flags_path.exists():
        sys.exit(
            f"{flags_path} not found. Run the evidence layer first:\n"
            "  PYTHONPATH=scripts uv run --with pandas --with pyarrow "
            "python -m assay_hygiene.run_evidence"
        )
    return {
        "samples": pd.read_parquet(ex / "samples.parquet",
                                   columns=["sample_id", "uuid"]),
        "membership": pd.read_parquet(ex / "membership.parquet"),
        "assays": pd.read_parquet(ex / "assays.parquet",
                                  columns=["assay_id", "internal_assay_id"]),
        "childof": pd.read_parquet(ex / "childof.parquet"),
        "flags": pd.read_csv(flags_path),
    }


def build_indexes(d: dict[str, pd.DataFrame]):
    samples, membership, assays, childof = (
        d["samples"], d["membership"], d["assays"], d["childof"])

    # 14 uuids carry more than one sample_id. Resolve deterministically to the
    # lowest, and SAY SO rather than letting pandas raise on a non-unique index
    # or, worse, silently fan the join out.
    dup = samples["uuid"].duplicated(keep=False).sum()
    id_of = (samples.sort_values("sample_id")
             .drop_duplicates("uuid", keep="first")
             .set_index("uuid")["sample_id"])

    # membership.assay_id is a seek id; claims speak internal ids. Cross the
    # junction before comparing anything. Rows with no junction row are the 17
    # known assays; they are counted and excluded from the COMPATIBILITY
    # population rather than silently dropped, because an unmappable id can
    # never match and would read as disagreement every time.
    a = assays.dropna(subset=["internal_assay_id"]).copy()
    a["internal_assay_id"] = a["internal_assay_id"].astype(int)
    m = membership.merge(a, on="assay_id", how="left")
    unmapped = int(m["internal_assay_id"].isna().sum())
    m = m.dropna(subset=["internal_assay_id"])
    m["internal_assay_id"] = m["internal_assay_id"].astype(int)
    reg = m.groupby("sample_id")["internal_assay_id"].apply(set).to_dict()

    co = childof.copy()
    co["child_id"] = co["child_uuid"].map(id_of)
    co["parent_id"] = co["parent_uuid"].map(id_of)
    unresolved = int(len(co) - len(co.dropna(subset=["child_id", "parent_id"])))
    co = co.dropna(subset=["child_id", "parent_id"]).astype(
        {"child_id": int, "parent_id": int})
    children_of = co.groupby("parent_id")["child_id"].apply(list).to_dict()
    parents_of = co.groupby("child_id")["parent_id"].apply(list).to_dict()

    st = samples.copy()
    st["sample_type"] = st["uuid"].str.rsplit("-", n=2).str[0]
    type_of = st.drop_duplicates("sample_id").set_index(
        "sample_id")["sample_type"].to_dict()

    by_type_assay: dict[tuple[str, int], set[int]] = {}
    for sid, aset in reg.items():
        t = type_of.get(sid)
        if t is None:
            continue
        for x in aset:
            by_type_assay.setdefault((t, x), set()).add(sid)

    stats = {"dup_uuid_rows": dup, "unmapped_membership": unmapped,
             "unresolved_childof": unresolved}
    return reg, children_of, parents_of, type_of, by_type_assay, stats


def classify(d, reg, children_of, parents_of, type_of, by_type_assay):
    def lineage(sid: int, claimed: int) -> str:
        if any(claimed in reg.get(n, ()) for n in children_of.get(sid, ())):
            return "child"
        if any(claimed in reg.get(n, ()) for n in parents_of.get(sid, ())):
            return "parent"
        return "none"

    def compatibility(sid: int, claimed: int) -> tuple[float | None, int]:
        """Best co-registration rate over the assays this sample IS in."""
        t = type_of.get(sid)
        best_rate, best_pop = None, 0
        for r in reg.get(sid, ()):
            pop = by_type_assay.get((t, r), set())
            if not pop:
                continue
            rate = len(pop & by_type_assay.get((t, claimed), set())) / len(pop)
            if best_rate is None or rate > best_rate:
                best_rate, best_pop = rate, len(pop)
        return best_rate, best_pop

    rows = []
    for r in d["flags"].itertuples(index=False):
        sid, claimed = int(r.sample_id), int(r.claimed_internal_assay_id)
        rate, pop = compatibility(sid, claimed)
        lin = lineage(sid, claimed)
        if pop < MIN_SUPPORT:
            band = "no_support"
        elif rate == 0:
            band = "never_co_occurs"
        elif rate > CO_OCCUR:
            band = "routinely_co_occurs"
        else:
            band = "sometimes"

        if lin != "none":
            disp = "ABSENCE_LINEAGE"
        elif band == "routinely_co_occurs":
            disp = "ABSENCE_COMPAT"
        elif band == "never_co_occurs":
            disp = "CONTRADICTION"
        else:
            disp = "UNRESOLVED"

        rows.append({
            "sample_id": sid, "uuid": r.uuid, "sample_type": r.sample_type,
            "registered_internal_assay_ids": r.registered_internal_assay_ids,
            "claimed_internal_assay_id": claimed,
            "claimed_internal_assay_title": r.claimed_internal_assay_title,
            "tier": r.tier, "source_field": r.source_field,
            "raw_value": r.raw_value,
            "lineage": lin, "co_reg_rate": rate, "co_reg_pop": pop,
            "compat_band": band, "disposition": disp,
        })
    return pd.DataFrame(rows)


def main(base_dir: str = "assay-hygiene") -> int:
    base = Path(base_dir)
    d = load(base)
    reg, ch, pa, type_of, by_ta, stats = build_indexes(d)
    out = classify(d, reg, ch, pa, type_of, by_ta)
    n = len(out)

    print(f"Mode 3 flags read from {base / 'mode3-contradictions.csv'}: {n}")
    print(f"  samples rows on a duplicate uuid   "
          f"{stats['dup_uuid_rows']} (resolved to lowest sample_id)")
    print(f"  membership rows with no junction   "
          f"{stats['unmapped_membership']}")
    print(f"  childof rows not resolvable        "
          f"{stats['unresolved_childof']}")

    print(f"\n=== TEST 1 lineage, over the {n} flags ===")
    for k, v in out["lineage"].value_counts().items():
        print(f"  {k:22s} {v:5d}  {v / n:6.1%}")

    print(f"\n=== TEST 2 compatibility, over the {n} flags ===")
    print(f"  (support floor {MIN_SUPPORT} samples of the type, "
          f"co-occur band > {CO_OCCUR})")
    for k, v in out["compat_band"].value_counts().items():
        print(f"  {k:22s} {v:5d}  {v / n:6.1%}")

    print(f"\n=== JOINT, over the {n} flags ===")
    print(pd.crosstab(out["lineage"], out["compat_band"]).to_string())

    print(f"\n=== DISPOSITION, over the {n} flags ===")
    for k in ("ABSENCE_LINEAGE", "ABSENCE_COMPAT", "UNRESOLVED",
              "CONTRADICTION"):
        v = int((out["disposition"] == k).sum())
        print(f"  {k:18s} {v:5d}  {v / n:6.1%}")

    res = out[out["disposition"] == "CONTRADICTION"]
    print(f"\n=== the residue that survives both tests: {len(res)} flags "
          f"over {res.groupby(['sample_type', 'claimed_internal_assay_id']).ngroups}"
          f" (type, claimed) patterns ===")
    if len(res):
        print(res.groupby(["sample_type", "claimed_internal_assay_title",
                           "raw_value"]).size()
              .sort_values(ascending=False).to_string())

    pav = out[(out["sample_type"] == "PAV")
              & (out["claimed_internal_assay_id"] == 74)]
    if len(pav):
        print("\n=== the PAV flagship, split by raw_value ===")
        for rv, g in pav.groupby("raw_value"):
            k = int((g["lineage"] != "none").sum())
            print(f"  {rv:12s} n={len(g):4d}  lineage-explained {k:4d} "
                  f"({k / len(g):.1%})")

    dest = base / "mode3-disposition.csv"
    out.to_csv(dest, index=False)
    print(f"\nwrote {dest} ({len(out)} rows). Nothing else was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
