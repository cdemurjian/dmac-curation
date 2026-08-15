# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""What the samples carrying an unresolved term are actually REGISTERED in.

`vocabulary-unresolved.csv` carries an occurrence count and five example UIDs,
which is not enough to rule on a term. The decisive evidence is registration:
measured 2026-08-14 on the real extract, of 266 unresolved terms, 120 have every
registered carrier sitting in exactly one internal assay. Reading five UIDs of
free text will not tell you that `Instrument: nikon ti2-e inverted microscope`
belongs to CometChip Assay; 2,271 unanimous registrations will.

This module is deterministic and does no judgment. It exists so that
`/curate-assay-vocabulary`, which is judgment, has a table to judge from.

TWO THINGS HERE ARE LOAD-BEARING AND BOTH WERE BUGS FIRST.

1. Registration is resolved through `precedent.assay_index`, never by filtering
   `internal_assay_id.notna()`. The 17 junction-less assays fall back to their
   own (assay_id, title) everywhere else in this package, so filtering them out
   here would mean two definitions of "registered" in one run: this table would
   report a term at share 1.00 while the Mode 3 audit saw a different
   registration for the same sample. Measured, the filtered version reported
   `Type: m397` as 66 registered, 1 candidate, share 1.00, where this one
   reports 79 registered, 2 candidates, 0.835: the 13 missing carriers are
   registered under fallback assay 481 and nowhere else. So the filtered table
   recommends a mapping that contradicts 13 samples' own registration. Under
   the plan as first written that surfaced as 13 Mode 3 flags; since the Mode 3
   amendment a proposal caps at T_WEAK and raises no flag at all, so the same
   defect now buys a wrong vocabulary entry and no symptom. That is a reason to
   get this table right, not a reason to relax. It also moved 3 terms out of
   "no registered carrier" (89 -> 86).

2. Every set is iterated in sorted order and every modal pick breaks ties
   explicitly. `Counter.most_common` breaks ties by insertion order, and these
   counters are filled from SETS of tuples whose iteration order depends on
   PYTHONHASHSEED. Three consecutive runs of the first version of this code
   reported 61, 58 and 59 confounded terms. The two guards are not equals. The
   TIE-BREAK is the one that decides answers: keep `sorted()` and drop it, and
   the table is perfectly stable and 23 of 266 rows name a DIFFERENT assay --
   `p.eng-251216-v1_rna-extraction-protocol.docx` moving from 64 Short Read
   Sequencing to 61 RNA Extraction, and 8 rows flipping between an assay and
   its own `X Analysis` twin (30/31, 25/71, 89/91). `sorted()` on its own is
   decorative given the tie-break -- byte-identical output, measured -- and is
   kept so insertion order stays defined for anything added here later.
   Stability is not the property to test for; the specific stable answer is.
"""
from __future__ import annotations

import collections
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import vocabulary as V
from .precedent import assay_index

EVIDENCE_COLUMNS = [
    "source_field", "raw_value", "n_samples", "sample_types",
    "n_registered", "n_candidate_assays", "cand_id", "cand_title",
    "share", "base_rate", "example_uuids",
]


def _winner(counter: collections.Counter):
    """Most frequent key, ties broken by the key's string form.

    `str()` and not `sorted()` on the keys: sample-type keys mix `str` and the
    `None` of a sample absent from the node index, and `sorted` raises
    TypeError on that pair. See the module docstring for why the tie-break
    exists at all.
    """
    if not counter:
        return None, 0
    return max(counter.items(), key=lambda kv: (kv[1], str(kv[0])))


def registered_assays(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> dict[int, set[tuple[int, str]]]:
    """sample_id -> {(internal_assay_id, title)} it is registered in.

    Same junction crossing as `audit.registered_internal`, carrying the title
    as well because this table is read by a human. If those two ever disagree,
    this one is wrong: the audit defines what "registered" means for a verdict.
    """
    ainfo = assay_index(assays)
    out: dict[int, set[tuple[int, str]]] = {}
    for sample_id, assay_id in zip(membership.sample_id, membership.assay_id):
        info = ainfo.get(int(assay_id))
        if info is None:
            continue
        out.setdefault(int(sample_id), set()).add((info[1], info[2]))
    return out


def carriers(
    meta: dict[int, dict],
    tail: pd.DataFrame,
) -> dict[tuple[str, str], list[int]]:
    """(field, value) -> every sample_id whose metadata carries it.

    The tail file records a count, not the ids, and five examples cannot
    support a share or a base rate.
    """
    want = {(r.source_field, r.raw_value) for r in tail.itertuples()}
    out: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for sid, d in meta.items():
        for field in S.CLAIM_FIELDS:
            value = S.normalise_value(d.get(field))
            if value and (field, value) in want:
                out[(field, value)].append(sid)
    return out


def build_evidence(
    tail: pd.DataFrame,
    meta: dict[int, dict],
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
) -> pd.DataFrame:
    """One row per unresolved term, with the registration evidence beside it.

    `base_rate` is the column that stops a reader believing `share`. It is the
    candidate assay's share among ALL registered samples of the term's modal
    sample type, term ignored. A `share` of 1.00 against a `base_rate` of 0.88
    is the sample type talking, not the term: the 12 bare-numeric Protocol
    values in the live queue are IACUC animal-use protocol numbers on NHP
    records, they sit at share 1.00 on `Patient Visit`, and 87.5% of registered
    NHP samples are in `Patient Visit` whatever protocol they were housed
    under. They name no assay at all.

    A high base_rate means THIS evidence is void, not that the answer is wrong.
    """
    reg = registered_assays(membership, assays)
    stype = {int(s): t for s, t in zip(nodes.sample_id, nodes.type)
             if pd.notna(s)}

    # what each sample TYPE is registered in anyway, every term ignored
    base: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    seen_type: collections.Counter = collections.Counter()
    for sid, t in stype.items():
        if reg.get(sid):
            seen_type[t] += 1
            for x in sorted(reg[sid]):
                base[t][x] += 1

    carry = carriers(meta, tail)
    rows = []
    for r in tail.itertuples():
        ids = carry.get((r.source_field, r.raw_value), [])
        counts: collections.Counter = collections.Counter()
        for sid in ids:
            for x in sorted(reg.get(sid, ())):
                counts[x] += 1
        n_registered = sum(1 for sid in ids if reg.get(sid))
        types = collections.Counter(stype.get(s) or "?" for s in ids)
        modal_type = _winner(types)[0]
        cand, n = _winner(counts)
        cand_id, cand_title = cand if cand else (None, None)
        rows.append({
            "source_field": r.source_field,
            "raw_value": r.raw_value,
            "n_samples": r.n_samples,
            "sample_types": ";".join(
                f"{k}:{v}" for k, v in sorted(
                    types.items(), key=lambda kv: (-kv[1], str(kv[0])))[:3]),
            "n_registered": n_registered,
            "n_candidate_assays": len(counts),
            "cand_id": cand_id,
            "cand_title": cand_title,
            "share": round(n / n_registered, 3) if n_registered else 0.0,
            "base_rate": (round(base[modal_type][cand] / seen_type[modal_type], 3)
                          if cand and seen_type.get(modal_type) else 0.0),
            "example_uuids": r.example_uuids,
        })
    out = pd.DataFrame(rows, columns=EVIDENCE_COLUMNS)
    # sorted on all three keys, not just the count, so equal counts cannot
    # reorder between runs
    return out.sort_values(["n_samples", "source_field", "raw_value"],
                           ascending=[False, True, True], ignore_index=True)


def summarise(ev: pd.DataFrame) -> str:
    silent = int((ev.n_registered == 0).sum())
    clean = int(((ev.n_candidate_assays == 1) & (ev.n_registered > 0)).sum())
    ambiguous = int((ev.n_candidate_assays > 1).sum())
    confounded = int(((ev.share >= 0.9) & (ev.base_rate >= 0.9)).sum())
    return "\n".join([
        f"{len(ev)} unresolved terms",
        f"  {silent} with no registered carrier",
        f"  {clean} whose registered carriers sit in exactly one internal assay",
        f"  {ambiguous} with two or more candidate assays",
        f"  {confounded} whose candidate is just the sample type's base rate "
        "(not a fourth group; these sit inside the two above)",
    ])


def load_tail(path) -> pd.DataFrame:
    """Read the unresolved queue, keys pinned to str.

    Same reason as `vocabulary.load_vocabulary`: the queue holds 12 bare-numeric
    Protocol values, and an inferred int64 column would make every lookup here
    miss the metadata it is supposed to match.
    """
    return pd.read_csv(Path(path), keep_default_na=False, na_values=[""],
                       dtype={"source_field": str, "raw_value": str})


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    d, out = Path(extract_dir), Path(out_dir)
    samples = pd.read_parquet(d / "samples.parquet")
    tail = load_tail(out / "vocabulary-unresolved.csv")
    ev = build_evidence(
        tail,
        V.parse_metadata(samples),
        pd.read_parquet(d / "membership.parquet"),
        pd.read_parquet(d / "assays.parquet"),
        pd.read_parquet(d / "nodes.parquet"),
    )
    out.mkdir(parents=True, exist_ok=True)
    ev.to_csv(out / "vocabulary-evidence.csv", index=False)
    print(summarise(ev))
    print(f"\nwrote {out}/vocabulary-evidence.csv")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(*sys.argv[1:]))
