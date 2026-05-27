#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl>=3.1"]
# ///
# Lifted from lee/scripts/review_nar_vs_uploads.py; renamed and generalized
# for dmac-curation plugin. Lee-specific ACTIVE_UPLOADS map replaced with
# auto-discovery from assay_sheets/. Hardcoded metadata path replaced with
# --metadata-xlsx arg.
"""Comprehensive review: metadata workbook vs assay_sheets/*-upload*.xlsx.

  1) For each upload sheet found in assay_sheets/:
       - row-count delta vs the corresponding sheet in the metadata workbook
       - UIDs only in metadata / only in upload sheet / common
       - For common UIDs: per-field diff on key columns
         (File_PrimaryData, Link_PrimaryData, Parent, Accession, Checksum_PrimaryData)
       - Link_PrimaryData fill rate + URL-type tally (zenodo/omero/geo/other)

  2) Unique Protocol values across all metadata sheets — printed at end, deduplicated.

Usage:
  uv run scripts/review_metadata_vs_uploads.py --metadata-xlsx path/to/All-Metadata.xlsx
  uv run scripts/review_metadata_vs_uploads.py   # auto-discovers previous_metadata/*All*.xlsx

Output is a single readable report on stdout.
"""
from __future__ import annotations
import argparse
import glob
import re
import sys
from pathlib import Path
from collections import Counter
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "assay_sheets"

COMPARE_COLS = [
    "File_PrimaryData", "Link_PrimaryData", "Parent",
    "Accession", "Checksum_PrimaryData",
]

# TODO(v0.2): support a project-level ACTIVE_UPLOADS JSON override to handle
# multi-sheet merges (e.g. D.IMG has 4 upload sheets). Auto-discovery uses
# a simple stype -> single sheet mapping.


def find_metadata_xlsx(explicit: str | None) -> Path:
    """Resolve the metadata XLSX path: explicit arg > glob > error."""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            print(f"ERROR: --metadata-xlsx path does not exist: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    candidates = sorted(glob.glob(str(ROOT / "previous_metadata" / "*All*.xlsx")))
    if candidates:
        return Path(candidates[0])
    print("ERROR: no metadata xlsx found. Pass --metadata-xlsx <path>.", file=sys.stderr)
    sys.exit(1)


def discover_active_uploads(sheets_dir: Path) -> dict[str, list[str]]:
    """Auto-discover sample-type → [upload sheet filenames] from assay_sheets/ glob."""
    result: dict[str, list[str]] = {}
    for p in sorted(sheets_dir.glob("*-upload*.xlsx")):
        stem = p.stem  # e.g. "A.FLOW-upload"
        stype = stem.split("-upload")[0]
        if stype:
            result.setdefault(stype, []).append(p.name)
    return result


def load_sheet_rows(path: Path, sheet_name: str | None = None) -> tuple[list[str], list[dict]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name] if sheet_name else (wb["Samples"] if "Samples" in wb.sheetnames else wb.active)
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []
        hdr = [str(c) if c is not None else "" for c in rows[0]]
        data = []
        for r in rows[1:]:
            if not r or not r[0]:
                continue
            d = {k: v for k, v in zip(hdr, r)}
            data.append(d)
        return hdr, data
    finally:
        wb.close()


def url_type(s: str | None) -> str:
    if not s:
        return "empty"
    s = str(s).lower()
    if "zenodo.org" in s: return "zenodo"
    if "omero" in s: return "omero"
    if "geo/query" in s or "ncbi.nlm.nih.gov/geo" in s: return "geo"
    if s.startswith("http"): return "other_url"
    return "non_url"


def normalize(v):
    if v is None: return ""
    return str(v).strip()


def compare_sheet(meta: Path, sheets_dir: Path, stype: str, upload_files: list[str]) -> None:
    print(f"\n{'='*78}")
    print(f"  {stype}")
    print(f"{'='*78}")

    # Metadata side
    meta_hdr, meta_rows = load_sheet_rows(meta, stype)
    meta_uids = {r.get("UID") for r in meta_rows if r.get("UID")}
    meta_map = {r["UID"]: r for r in meta_rows if r.get("UID")}

    # Upload side — merge multiple sheets if needed (later overrides earlier on UID conflict)
    up_map: dict[str, dict] = {}
    up_hdrs_seen: set[str] = set()
    for fname in upload_files:
        path = sheets_dir / fname
        if not path.exists():
            print(f"  WARNING: upload sheet not found: {fname}")
            continue
        h, rows = load_sheet_rows(path)
        for col in h:
            up_hdrs_seen.add(col)
        for r in rows:
            if r.get("UID"):
                up_map[r["UID"]] = r
    up_uids = set(up_map.keys())

    print(f"  metadata rows:    {len(meta_rows)}")
    print(f"  upload rows:      {len(up_map)}  (from {', '.join(upload_files)})")

    only_meta = meta_uids - up_uids
    only_up = up_uids - meta_uids
    common = meta_uids & up_uids
    print(f"  common UIDs:      {len(common)}")
    print(f"  only in metadata: {len(only_meta)}")
    print(f"  only in upload:   {len(only_up)}")

    if only_meta and len(only_meta) <= 10:
        print(f"    metadata-only: {sorted(only_meta)}")
    elif only_meta:
        print(f"    metadata-only (first 10 of {len(only_meta)}): {sorted(only_meta)[:10]}")

    if only_up and len(only_up) <= 10:
        print(f"    upload-only: {sorted(only_up)}")
    elif only_up:
        print(f"    upload-only (first 10 of {len(only_up)}): {sorted(only_up)[:10]}")

    # Per-field diff for common UIDs
    diffs_by_col: dict[str, list[tuple[str, str, str]]] = {c: [] for c in COMPARE_COLS}
    for uid in common:
        n = meta_map[uid]
        u = up_map[uid]
        for col in COMPARE_COLS:
            if col not in n and col not in u:
                continue
            nv = normalize(n.get(col))
            uv = normalize(u.get(col))
            if nv != uv:
                diffs_by_col[col].append((uid, nv, uv))

    for col, lst in diffs_by_col.items():
        if not lst: continue
        print(f"\n  diff {col}: {len(lst)} differences")
        for uid, nv, uv in lst[:5]:
            nv_show = (nv[:60] + "...") if len(nv) > 60 else nv
            uv_show = (uv[:60] + "...") if len(uv) > 60 else uv
            print(f"     {uid}")
            print(f"       metadata: {nv_show!r}")
            print(f"       upload:   {uv_show!r}")
        if len(lst) > 5:
            print(f"     ... +{len(lst) - 5} more")

    # Link fill rate / URL type tally (metadata side, source of truth for FDH push)
    if "Link_PrimaryData" in meta_hdr:
        type_counts = Counter(url_type(r.get("Link_PrimaryData")) for r in meta_rows)
        types_str = ", ".join(f"{t}={c}" for t, c in sorted(type_counts.items()))
        filled = sum(c for t, c in type_counts.items() if t != "empty")
        print(f"\n  metadata Link_PrimaryData: {filled}/{len(meta_rows)} filled  ({types_str})")
    elif "Link_PrimaryData" in up_hdrs_seen:
        print(f"\n  metadata sheet has no Link_PrimaryData column (schema needs update on FDH)")


def collect_protocols(meta: Path) -> dict[str, int]:
    """Return {protocol: count} aggregated across all metadata sheets."""
    counts: Counter[str] = Counter()
    sources: dict[str, set[str]] = {}
    wb = load_workbook(meta, read_only=True, data_only=True)
    try:
        for sname in wb.sheetnames:
            ws = wb[sname]
            rows = list(ws.iter_rows(values_only=True))
            if not rows: continue
            hdr = [str(c) if c is not None else "" for c in rows[0]]
            if "Protocol" not in hdr:
                continue
            i = hdr.index("Protocol")
            for r in rows[1:]:
                if not r or len(r) <= i:
                    continue
                p = r[i]
                if p is None or str(p).strip() == "":
                    continue
                # Split semicolon-separated protocol lists
                for tok in re.split(r"[;]+", str(p)):
                    tok = tok.strip()
                    if not tok: continue
                    counts[tok] += 1
                    sources.setdefault(tok, set()).add(sname)
    finally:
        wb.close()
    # Print
    print(f"\n{'='*78}")
    print(f"  UNIQUE PROTOCOLS  ({len(counts)} distinct)")
    print(f"{'='*78}")
    for proto, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        src = ", ".join(sorted(sources[proto]))
        print(f"  [{c:4}x]  {proto}")
        print(f"           seen in: {src}")
    return dict(counts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--metadata-xlsx",
        metavar="XLSX",
        help="Path to All-Metadata workbook (default: previous_metadata/*All*.xlsx glob)",
    )
    ap.add_argument(
        "--sheets-dir",
        type=Path,
        default=SHEETS,
        metavar="DIR",
        help="Directory containing upload sheets (default: <project>/assay_sheets/)",
    )
    args = ap.parse_args()

    meta = find_metadata_xlsx(args.metadata_xlsx)
    sheets_dir = args.sheets_dir
    active_uploads = discover_active_uploads(sheets_dir)

    print(f"REVIEW: metadata vs assay_sheets/")
    print(f"  metadata: {meta.name}")
    print(f"  sheets dir: {sheets_dir}")
    print(f"  discovered {len(active_uploads)} sample types\n")

    for stype, files in sorted(active_uploads.items()):
        compare_sheet(meta, sheets_dir, stype, files)

    # Check for metadata sheets with no corresponding upload sheet
    wb = load_workbook(meta, read_only=True, data_only=True)
    try:
        for sname in wb.sheetnames:
            if sname not in active_uploads:
                ws = wb[sname]
                rows = list(ws.iter_rows(values_only=True))
                n = sum(1 for r in rows[1:] if r and r[0])
                if n > 0:
                    print(f"\n{'='*78}")
                    print(f"  {sname}  (no local upload sheet)")
                    print(f"{'='*78}")
                    print(f"  metadata rows: {n}")
    finally:
        wb.close()

    collect_protocols(meta)


if __name__ == "__main__":
    main()
