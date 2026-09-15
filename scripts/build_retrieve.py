# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Build RETRIEVE.TXT from assay_sheets/ — newline-separated UIDs for chat_nextseek.

By default emits only downstream sample types (D.*/A.*/SLD/etc.) — the retrieve
function auto-pulls parents via the lineage chain. Use --include-parents to emit
all UIDs including DNA/RNA/TIS/MUS intermediates.

A parent-type row is only dropped when it ACTUALLY has a child in the sheets.
Excluding by sample type alone silently loses any branch that terminates in a
parent type (e.g. PAT -> PAV -> TIS with nothing downstream): no UID on that
branch is ever requested, so retrieve's lineage walk never reaches it.

Prefers `*-upload-new.xlsx` over `*-upload.xlsx` over a bare `*.xlsx`. The bare
tier matters because `consolidate_to_flat --all-in-one NAME` writes exactly
`NAME.xlsx`; without it a single-project curation yields an empty RETRIEVE.TXT
and still exits 0. `*_review.xlsx` is never an upload file and is always skipped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

# Sample types treated as PARENTS (auto-pulled by retrieve; excluded by default)
PARENT_TYPES = {"MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}


def _preferred_files(assay_sheets_dir: Path) -> list[Path]:
    """One file per basename, ranked -upload-new > -upload > bare."""
    # rank -> (basename, path); higher rank wins
    best: dict[str, tuple[int, Path]] = {}
    for p in sorted(assay_sheets_dir.glob("*.xlsx")):
        if p.name.startswith("~") or p.name.startswith("."):  # lock / resource forks
            continue
        if p.stem.endswith("_review"):  # companion review file, never uploaded
            continue
        if "-upload-new" in p.stem:
            base, rank = p.stem.replace("-upload-new", ""), 3
        elif "-upload" in p.stem:
            base, rank = p.stem.replace("-upload", ""), 2
        else:
            base, rank = p.stem, 1
        if rank > best.get(base, (0, None))[0]:
            best[base] = (rank, p)
    return [path for _, path in best.values()]


def _read_rows(path: Path) -> list[tuple[str, str]]:
    """Return (uid, parent) pairs from a workbook's Samples sheet."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Samples" not in wb.sheetnames:
            return []
        rows_iter = wb["Samples"].iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            return []
        cols = {str(h).strip().lower(): i for i, h in enumerate(header) if h}
        uid_col = cols.get("uid")
        if uid_col is None:
            return []
        parent_col = cols.get("parent")
        out: list[tuple[str, str]] = []
        for row in rows_iter:
            if uid_col >= len(row) or not row[uid_col]:
                continue
            uid = str(row[uid_col]).strip()
            if "-" not in uid:
                continue
            parent = ""
            if parent_col is not None and parent_col < len(row) and row[parent_col]:
                parent = str(row[parent_col]).strip()
            out.append((uid, parent))
        return out
    finally:
        wb.close()


def collect_uids(assay_sheets_dir: Path, include_parents: bool) -> list[str]:
    """Walk assay_sheets/, dedupe + sort UIDs, drop parents that have children."""
    pairs: list[tuple[str, str]] = []
    for path in _preferred_files(assay_sheets_dir):
        pairs.extend(_read_rows(path))

    if include_parents:
        return sorted({uid for uid, _ in pairs})

    # A parent-type row is redundant only if something else derives from it;
    # a leaf keeps its place in the list whatever its sample type.
    has_child = {parent for _, parent in pairs if parent}
    return sorted({
        uid for uid, _ in pairs
        if uid.split("-", 1)[0] not in PARENT_TYPES or uid not in has_child
    })


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assay-sheets", default="assay_sheets",
                   help="Directory of upload workbooks: *-upload-new.xlsx / "
                        "*-upload.xlsx / *.xlsx (default: assay_sheets)")
    p.add_argument("--output", default="RETRIEVE.TXT", help="Output file (default: RETRIEVE.TXT)")
    p.add_argument("--include-parents", action="store_true",
                   help="Include every MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL UID, even "
                        "those with children (default: leaves and downstream only)")
    args = p.parse_args()

    assay_dir = Path(args.assay_sheets).resolve()
    if not assay_dir.is_dir():
        print(f"ERROR: {assay_dir} is not a directory", file=sys.stderr)
        return 2

    uids = collect_uids(assay_dir, include_parents=args.include_parents)
    out = Path(args.output).resolve()
    out.write_text("\n".join(uids) + "\n")

    by_type: dict[str, int] = {}
    for u in uids:
        t = u.split("-", 1)[0]
        by_type[t] = by_type.get(t, 0) + 1

    print(f"Wrote {len(uids)} UIDs to {out}")
    for t in sorted(by_type):
        print(f"  {t}: {by_type[t]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
