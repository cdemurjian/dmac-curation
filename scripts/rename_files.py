#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""File rename + flatten tool for curation-project `files/` trees.

Walks a directory of raw data organized by Figure subfolders (`files/Figure 1/`,
`files/Figure 2/`, ...), classifies each file by type, proposes new canonical
filenames, and applies the rename atomically.

5 subcommands:

    walk        --root files/ --manifest manifest.csv
                Parse the tree, emit manifest.csv. No filesystem changes.

    checksums   --manifest manifest.csv [--workers 8]
                Compute MD5 for every row missing one. Updates in place.

    apply       --manifest manifest.csv [--delete-fig7-dupes]
                Rename + move files per the manifest. Removes emptied subdirs.
                Idempotent. Refuses to run if any non-skipped row is missing an md5.

    verify      --manifest manifest.csv
                Re-stat files/ and report drift vs the manifest.

    rollback    --manifest manifest.csv
                Reverse a previous apply using the manifest's original_path mapping.

Manifest CSV (`manifest.csv` at repo root) is the source of truth — every rename
flows through it. Stdlib only (no openpyxl, no requests).

The default classifier rules in this script (FIGURE_DIRS, FIG5_CHAMBER_TO_CANONICAL,
SUBSTITUTIONS, and the `intrav_sim_final.mph` Figure 1 COMSOL pattern) reflect
the IntravChip dataset. For other projects, fork these constants or pass
`--config <yaml>` (planned for v0.2).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, NamedTuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# TODO(v0.2): These constants are IntravChip-specific. For other projects,
# fork the script or load from a per-project YAML config file.
FIGURE_DIRS = [f"Figure {n}" for n in range(1, 8)]

# Canonical case restoration. After path components are lowercased + whitespace
# is hyphenized, walk this dict and replace each variant with the canonical form.
# Longer keys are applied first so prefixes don't shadow them.
SUBSTITUTIONS: list[tuple[str, list[str]]] = [
    # canonical, [lowercase variants seen in the wild]
    ("1000TCs", ["1000tcs", "1000-tcs"]),
    ("100TCs",  ["100tcs", "100-tcs"]),
    ("TC1000",  ["tc1000", "tc-1000"]),
    ("TC100",   ["tc100", "tc-100"]),
    ("TC10",    ["tc10", "tc-10"]),
    ("MCF7",    ["mcf7"]),
    ("MVN",     ["mvn"]),
    ("MV3",     ["mv3"]),
    ("PM6",     ["pm6"]),
    ("DMSO",    ["dmso"]),
    ("EGFP",    ["egfp"]),
    ("GFP",     ["gfp"]),
    ("BFP",     ["bfp"]),
    ("RFP",     ["rfp"]),
]

# Fig 5: tissue (root) name → chamber (subfolder) name. The script uses
# the inverse direction (subfolder stem → canonical tissue stem) to canonicalize
# device IDs. Keys are *normalized* subfolder stems; values are canonical IDs.
FIG5_CHAMBER_TO_CANONICAL = {
    # 231-day9-dev-N → canonical 231-day9-gel-dev-N
    re.compile(r"^231-day9-dev-(\d+)$"): r"231-day9-gel-dev-\1",
    # MCF7-day9-dev-N → MCF7-day9-gel-dev-N
    re.compile(r"^MCF7-day9-dev-(\d+)$"): r"MCF7-day9-gel-dev-\1",
    # d9-231-flow-dev-N → d9-MVN-231-flow-dev-N
    re.compile(r"^d9-231-flow-dev-(\d+)$"): r"d9-MVN-231-flow-dev-\1",
    # PM6 / MV3 already match → no rewrite needed
}

# Manifest column order. Edit with care — apply/verify/rollback read by name.
MANIFEST_COLUMNS = [
    "id",
    "original_path",
    "size_bytes",
    "mtime_iso",
    "md5",
    "figure",
    "device_id",
    "region",        # tissue | chamber | na
    "acquisition",   # NNNN or empty
    "roi",           # R<R>_<TT> or empty
    "category",      # imaging-raw | imaging-tile | quantification | mosaic-log |
                     # stitch-config | stitched-image | velocity-sim |
                     # storm-coords | storm-density | comsol-model |
                     # tc-area | tc-area-early | duplicate | excluded-movie
    "target_storage",  # omero | zenodo | skip
    "sampletype",      # D.IMG | A.IMG | D.SIM | MDL | (empty if skip)
    "target_filename",
    "target_relpath",
    "skip_reason",
    "notes",
]


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_MULTI_HYPHEN_RE = re.compile(r"-+")


def normalize_stem(s: str) -> str:
    """Normalize a single path component (no extension) to a canonical form.

    - drop non-ASCII
    - replace any whitespace run with '-'
    - replace '_' with '-' (treat underscore as a separator at the device level)
    - collapse '--+' to '-'
    - lowercase, then restore canonical case for known keywords
    - strip leading/trailing '-'
    """
    # ASCII only
    s = s.encode("ascii", errors="ignore").decode("ascii")
    # Treat underscores in stems as separators
    s = s.replace("_", "-")
    # Whitespace → hyphen
    s = _WS_RE.sub("-", s)
    # Collapse multi-hyphens
    s = _MULTI_HYPHEN_RE.sub("-", s)
    s = s.strip("-")
    # Lowercase, then restore canonical case for each known keyword
    s = s.lower()
    for canon, variants in SUBSTITUTIONS:
        for v in variants:
            s = s.replace(v, canon)
    return s


# Strip a trailing `_NNNN` or `-NNNN` acquisition suffix from a subfolder stem.
_ACQ_SUFFIX_RE = re.compile(r"[_-](\d{4})$")


def split_acquisition(stem: str) -> tuple[str, str]:
    """(device_stem_without_acq, NNNN) -- or ('original', '') if no match."""
    m = _ACQ_SUFFIX_RE.search(stem)
    if m:
        return stem[: m.start()], m.group(1)
    return stem, ""


def canonical_device_id(figure: int, raw_stem: str, *, is_chamber: bool) -> str:
    """Resolve the canonical device ID for a tissue (root) or chamber (subfolder)
    file. For Fig 5, the chamber form is rewritten to match the tissue form."""
    stem = normalize_stem(raw_stem)
    if figure == 5 and is_chamber:
        for pat, repl in FIG5_CHAMBER_TO_CANONICAL.items():
            if pat.match(stem):
                return pat.sub(repl, stem)
    return stem


# ---------------------------------------------------------------------------
# File classification (the heart of the rename logic)
# ---------------------------------------------------------------------------


class FileSpec(NamedTuple):
    """Per-file plan emitted by classify()."""

    figure: int
    device_id: str
    region: str        # 'tissue' | 'chamber' | 'na'
    acquisition: str   # '0001' or ''
    roi: str           # 'R3_02' or ''
    category: str
    target_storage: str  # 'omero' | 'zenodo' | 'skip'
    sampletype: str      # 'D.IMG' | 'A.IMG' | 'D.SIM' | 'MDL' | ''
    target_filename: str
    skip_reason: str = ""
    notes: str = ""


def _is_excluded_movie(rel_path: Path) -> bool:
    """Fig 2 movies — explicitly excluded per Marie's email."""
    if rel_path.parts[0] == "Figure 2" and len(rel_path.parts) == 2:
        name = rel_path.name.lower()
        return name.startswith("movie") and name.endswith(".tif")
    return False


def _is_fig7_duplicate(rel_path: Path) -> bool:
    """Files under Figure 7/Figure {1..6}/ are byte-identical mirrors."""
    parts = rel_path.parts
    return (
        len(parts) >= 2
        and parts[0] == "Figure 7"
        and re.match(r"^Figure [1-6]$", parts[1])
    )


_ROI_FILE_RE = re.compile(r"^ROI(\d+)[_-](\d+)\.oib(?:\.csv)?$", re.IGNORECASE)
_ROI_CSV_RE = re.compile(r"^ROI(\d+)[_-](\d+)\.oib\.csv$", re.IGNORECASE)
_ROI_OIB_RE = re.compile(r"^ROI(\d+)[_-](\d+)\.oib$", re.IGNORECASE)

# Numeric-only tile naming used in Fig 4 TC10/TC100/TC1000 dirs: e.g. "01_01.oib", "016_01.oib"
_TILE_NUMERIC_OIB_RE = re.compile(r"^(\d+)_(\d+)\.oib$")
_TILE_NUMERIC_CSV_RE = re.compile(r"^(\d+)_(\d+)\.oib\.csv$")

# Labeled tile naming used in Fig 4 TC1000 day-6/-7 dirs: e.g. "15uM Bottom left10_01.oib"
# The leading "<digits>uM" is a Marie-naming quirk (NOT a sorafenib dose; these are
# Fig 4 acquisitions). We strip it for the tile id and stash the original prefix in notes.
_TILE_BL_OIB_RE = re.compile(r"^(.+?)Bottom left(\d+)_(\d+)\.oib$", re.IGNORECASE)
_TILE_BL_CSV_RE = re.compile(r"^(.+?)Bottom left(\d+)_(\d+)\.oib\.csv$", re.IGNORECASE)


def _classify_subfolder_file(
    figure: int,
    subfolder_name: str,
    inner_name: str,
    is_two_region_fig: bool,
) -> FileSpec | None:
    """Classify a file inside a `<dev>_NNNN/` subfolder."""
    subfolder_stem, acq = split_acquisition(subfolder_name)
    if not acq:
        # Subfolder without _NNNN — treat as acq 0001 (e.g. Fig 4 '231-day7-TC1000-dev2')
        acq = "0001"
        subfolder_stem = subfolder_name
    region = "chamber" if is_two_region_fig else "na"
    device_id = canonical_device_id(figure, subfolder_stem, is_chamber=True)
    region_tag = "c" if is_two_region_fig else "a"

    # ROI tile (.oib) — "ROI<R>_<TT>.oib"
    m = _ROI_OIB_RE.match(inner_name)
    if m:
        r, tt = m.group(1), m.group(2)
        roi = f"R{r}_{tt}"
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.oib"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="imaging-tile",
            target_storage="omero", sampletype="D.IMG",
            target_filename=new_name,
        )

    # Numeric tile (.oib) — "<MM>_<NN>.oib" (Fig 4 TC10/TC100/TC1000 16-tile scans)
    m = _TILE_NUMERIC_OIB_RE.match(inner_name)
    if m:
        mm, nn = m.group(1), m.group(2)
        roi = f"T{mm}_{nn}"  # T for "tile" — distinguishes from ROI naming
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.oib"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="imaging-tile",
            target_storage="omero", sampletype="D.IMG",
            target_filename=new_name,
        )

    # Labeled tile (.oib) — "<prefix>Bottom left<MM>_<NN>.oib"
    m = _TILE_BL_OIB_RE.match(inner_name)
    if m:
        prefix, mm, nn = m.group(1).strip(), m.group(2), m.group(3)
        roi = f"BL{mm}_{nn}"
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.oib"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="imaging-tile",
            target_storage="omero", sampletype="D.IMG",
            target_filename=new_name,
            notes=f"original tile prefix: {prefix!r} (Marie quirk, not a dose)",
        )

    # ROI quantification csv — "ROI<R>_<TT>.oib.csv"
    m = _ROI_CSV_RE.match(inner_name)
    if m:
        r, tt = m.group(1), m.group(2)
        roi = f"R{r}_{tt}"
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.csv"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="quantification",
            target_storage="zenodo", sampletype="A.IMG",
            target_filename=new_name,
        )

    # Numeric quantification csv — "<MM>_<NN>.oib.csv"
    m = _TILE_NUMERIC_CSV_RE.match(inner_name)
    if m:
        mm, nn = m.group(1), m.group(2)
        roi = f"T{mm}_{nn}"
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.csv"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="quantification",
            target_storage="zenodo", sampletype="A.IMG",
            target_filename=new_name,
        )

    # Labeled quantification csv
    m = _TILE_BL_CSV_RE.match(inner_name)
    if m:
        prefix, mm, nn = m.group(1).strip(), m.group(2), m.group(3)
        roi = f"BL{mm}_{nn}"
        new_name = f"{device_id}_{region_tag}{acq}_{roi}.csv"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi=roi,
            category="quantification",
            target_storage="zenodo", sampletype="A.IMG",
            target_filename=new_name,
            notes=f"original tile prefix: {prefix!r}",
        )

    # Misfiled .oib named after the parent device (e.g. "d9-sor 10um-3.oib"
    # inside "d9-sor 10um-3_0001/") — a FluoView-stitched single composite,
    # NOT a tile. Distinct content, much larger than the root tissue file.
    if inner_name.lower().endswith(".oib"):
        inner_stem = Path(inner_name).stem
        if normalize_stem(inner_stem) == normalize_stem(subfolder_stem):
            new_name = f"{device_id}_{region_tag}{acq}_chamber-fused.oib"
            return FileSpec(
                figure=figure, device_id=device_id, region=region,
                acquisition=acq, roi="",
                category="stitched-image",
                target_storage="zenodo", sampletype="A.IMG",
                target_filename=new_name,
                notes="FluoView-stitched composite saved under device name",
            )

    # Mosaic log
    if inner_name.lower() == "matl_mosaic.log":
        new_name = f"{device_id}_{region_tag}{acq}_mosaic.log"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi="",
            category="mosaic-log",
            target_storage="zenodo", sampletype="",  # secondary, no separate row
            target_filename=new_name,
            notes="attach as Link_SecondaryData on parent D.IMG row(s)",
        )

    # Tile configuration files
    if inner_name == "TileConfiguration.txt":
        new_name = f"{device_id}_{region_tag}{acq}_tilecfg.txt"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi="",
            category="stitch-config",
            target_storage="zenodo", sampletype="",
            target_filename=new_name,
            notes="Fiji stitching input",
        )
    if inner_name == "TileConfiguration.registered.txt":
        new_name = f"{device_id}_{region_tag}{acq}_tilecfg-reg.txt"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi="",
            category="stitch-config",
            target_storage="zenodo", sampletype="",
            target_filename=new_name,
            notes="Fiji stitching output (registered)",
        )

    # Fused.tif (stitched composite)
    if inner_name.lower() == "fused.tif":
        new_name = f"{device_id}_{region_tag}{acq}_fused.tif"
        return FileSpec(
            figure=figure, device_id=device_id, region=region,
            acquisition=acq, roi="",
            category="stitched-image",
            target_storage="zenodo", sampletype="A.IMG",
            target_filename=new_name,
            notes="stitched composite of ROI tiles",
        )

    return None  # unknown → caller flags as skip


def classify(rel_path: Path) -> FileSpec:
    """Map a path (relative to files/) to a FileSpec."""
    parts = rel_path.parts
    name = rel_path.name

    # ---- skip rules ---------------------------------------------------------
    if _is_excluded_movie(rel_path):
        return FileSpec(
            figure=2, device_id="", region="na", acquisition="", roi="",
            category="excluded-movie",
            target_storage="skip", sampletype="",
            target_filename="", skip_reason="excluded from submitted manuscript",
        )
    if _is_fig7_duplicate(rel_path):
        return FileSpec(
            figure=7, device_id="", region="na", acquisition="", roi="",
            category="duplicate",
            target_storage="skip", sampletype="",
            target_filename="",
            skip_reason=f"byte-identical mirror of top-level {parts[1]}",
        )

    # Determine figure
    m = re.match(r"^Figure (\d+)$", parts[0])
    if not m:
        return FileSpec(0, "", "na", "", "", "unknown", "skip", "", "",
                        skip_reason=f"not under Figure N: {rel_path}")
    figure = int(m.group(1))

    # ---- Figure 1: single COMSOL file ---------------------------------------
    if figure == 1:
        # TODO(v0.2): IntravChip-specific Figure 1 classifier. For other projects,
        # replace this filename pattern or move to a per-project config file.
        if name == "intrav_sim_final.mph":
            return FileSpec(
                figure=1, device_id="", region="na", acquisition="", roi="",
                category="comsol-model",
                target_storage="zenodo", sampletype="MDL",
                target_filename="intrav_sim_final.mph",
            )
        return FileSpec(1, "", "na", "", "", "unknown", "skip", "", "",
                        skip_reason="unexpected file under Figure 1")

    # ---- Figure 6: STORM data (already cleanly named) ----------------------
    if figure == 6:
        if len(parts) >= 3 and parts[1] in ("ImgLib", "STORMLib"):
            if name.lower().endswith(".png"):
                return FileSpec(
                    figure=6, device_id="", region="na", acquisition="", roi="",
                    category="storm-density",
                    target_storage="zenodo", sampletype="A.IMG",
                    target_filename=name,  # already unique
                    notes=f"STORM density map ({parts[1]})",
                )
            if name.lower().endswith(".txt"):
                return FileSpec(
                    figure=6, device_id="", region="na", acquisition="", roi="",
                    category="storm-coords",
                    target_storage="zenodo", sampletype="A.IMG",
                    target_filename=name,
                    notes=f"STORM coordinates ({parts[1]})",
                )
        return FileSpec(6, "", "na", "", "", "unknown", "skip", "", "",
                        skip_reason="unexpected file under Figure 6")

    # ---- Figure 2 sub-trees ------------------------------------------------
    if figure == 2:
        # velocity sims
        if len(parts) >= 3 and parts[1] == "velocity sims":
            m = re.match(r"^Fused-dev-(\d+)\.tif$", name, re.IGNORECASE)
            if m:
                new_name = f"velsim-dev-{m.group(1)}.tif"
                return FileSpec(
                    figure=2, device_id="", region="na",
                    acquisition="", roi="",
                    category="velocity-sim",
                    target_storage="zenodo", sampletype="D.SIM",
                    target_filename=new_name,
                    notes="muVes simulation output",
                )

        # TC area over time
        if len(parts) >= 3 and parts[1] == "TC area over time":
            # 2a) root-level .oib in this dir
            if len(parts) == 3 and name.lower().endswith(".oib"):
                stem = normalize_stem(Path(name).stem)
                new_name = f"tc-area-{stem}.oib"
                return FileSpec(
                    figure=2, device_id=stem, region="na",
                    acquisition="", roi="",
                    category="tc-area",
                    target_storage="omero", sampletype="D.IMG",
                    target_filename=new_name,
                )
            # 2b) d1/d4/d5 subdirs — early timepoint tifs
            if (len(parts) == 4 and parts[2] in ("d1", "d4", "d5")
                    and name.lower().endswith(".tif")):
                stem = normalize_stem(Path(name).stem)
                new_name = f"tc-area-{parts[2]}-{stem}.tif"
                return FileSpec(
                    figure=2, device_id=stem, region="na",
                    acquisition="", roi="",
                    category="tc-area-early",
                    target_storage="omero", sampletype="D.IMG",
                    target_filename=new_name,
                    notes=f"early timepoint {parts[2]}",
                )

        # device subfolders (d7-1000TCs-dev-N_NNNN, d7-MVN only-dev-N_NNNN, etc.)
        if len(parts) == 3:
            subfolder = parts[1]
            spec = _classify_subfolder_file(2, subfolder, name, is_two_region_fig=False)
            if spec:
                return spec

    # ---- Figures 3, 4, 5, 7: two-region pattern ----------------------------
    if figure in (3, 4, 5, 7):
        # 4a) root-level imaging (.oib or .tif) = tissue region
        if len(parts) == 2:
            stem = Path(name).stem
            ext = Path(name).suffix.lower()
            if ext in (".oib", ".tif"):
                device_id = canonical_device_id(figure, stem, is_chamber=False)
                new_name = f"{device_id}_t{ext}"
                return FileSpec(
                    figure=figure, device_id=device_id, region="tissue",
                    acquisition="", roi="",
                    category="imaging-raw",
                    target_storage="omero", sampletype="D.IMG",
                    target_filename=new_name,
                )
        # 4b) subfolder = chamber region
        if len(parts) == 3:
            subfolder = parts[1]
            spec = _classify_subfolder_file(figure, subfolder, name, is_two_region_fig=True)
            if spec:
                return spec

    # Fallback — unknown shape
    return FileSpec(
        figure=figure, device_id="", region="na", acquisition="", roi="",
        category="unknown",
        target_storage="skip", sampletype="",
        target_filename="",
        skip_reason=f"unrecognized pattern: {rel_path}",
    )


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def manifest_rows_to_csv(rows: list[dict], out_path: Path) -> None:
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def manifest_load(path: Path) -> list[dict]:
    with path.open("r", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# walk
# ---------------------------------------------------------------------------


def _target_relpath(figure: int, target_filename: str, target_storage: str) -> str:
    if not target_filename:
        return ""
    if target_storage == "omero":
        return f"Figure {figure}/{target_filename}"
    if target_storage == "zenodo":
        return f"Figure {figure} - secondary/{target_filename}"
    return ""


def cmd_walk(root: Path, manifest_path: Path) -> None:
    rows: list[dict] = []
    next_id = 1
    for fig_dir in sorted(root.iterdir()):
        if not fig_dir.is_dir() or fig_dir.name not in FIGURE_DIRS:
            continue
        for path in sorted(fig_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            spec = classify(rel)
            try:
                st = path.stat()
                size, mtime = st.st_size, st.st_mtime
            except OSError as e:
                size, mtime = 0, 0
                spec = spec._replace(skip_reason=(spec.skip_reason or f"stat failed: {e}"),
                                     target_storage="skip")
            row = {
                "id": f"{next_id:06d}",
                "original_path": str(rel),
                "size_bytes": size,
                "mtime_iso": (
                    __import__("datetime").datetime
                    .fromtimestamp(mtime).isoformat(timespec="seconds")
                ) if mtime else "",
                "md5": "",
                "figure": spec.figure or "",
                "device_id": spec.device_id,
                "region": spec.region,
                "acquisition": spec.acquisition,
                "roi": spec.roi,
                "category": spec.category,
                "target_storage": spec.target_storage,
                "sampletype": spec.sampletype,
                "target_filename": spec.target_filename,
                "target_relpath": _target_relpath(
                    spec.figure, spec.target_filename, spec.target_storage),
                "skip_reason": spec.skip_reason,
                "notes": spec.notes,
            }
            rows.append(row)
            next_id += 1

    manifest_rows_to_csv(rows, manifest_path)
    _walk_summary(rows)


def _walk_summary(rows: list[dict]) -> None:
    from collections import Counter
    total = len(rows)
    storage = Counter(r["target_storage"] for r in rows)
    category = Counter(r["category"] for r in rows)
    figure = Counter(r["figure"] for r in rows)
    skipped = [r for r in rows if r["target_storage"] == "skip"]
    print(f"\n  total files: {total}")
    print(f"  by storage:  {dict(storage)}")
    print(f"  by figure:   {dict(figure)}")
    print(f"  by category: {dict(category)}")
    # Surface any unknowns
    unknowns = [r for r in rows if r["category"] in ("unknown", "")]
    if unknowns:
        print(f"\n  WARNING: {len(unknowns)} unclassified files — review manifest 'skip_reason' col")
        for r in unknowns[:10]:
            print(f"    {r['original_path']}  →  {r['skip_reason']}")
        if len(unknowns) > 10:
            print(f"    ... and {len(unknowns) - 10} more")

    # Collision check: any two non-skip rows with the same target_relpath?
    by_target: dict[str, list[str]] = {}
    for r in rows:
        if r["target_storage"] == "skip" or not r["target_relpath"]:
            continue
        by_target.setdefault(r["target_relpath"], []).append(r["original_path"])
    collisions = {k: v for k, v in by_target.items() if len(v) > 1}
    if collisions:
        print(f"\n  ERROR: {len(collisions)} target-filename collisions:")
        for tgt, srcs in list(collisions.items())[:10]:
            print(f"    {tgt}")
            for s in srcs:
                print(f"      ← {s}")


# ---------------------------------------------------------------------------
# checksums
# ---------------------------------------------------------------------------


def _md5_of(path: Path, block: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(block):
            h.update(chunk)
    return h.hexdigest()


def cmd_checksums(root: Path, manifest_path: Path, workers: int) -> None:
    rows = manifest_load(manifest_path)
    need: list[tuple[int, dict]] = [
        (i, r) for i, r in enumerate(rows)
        if not r["md5"] and r["target_storage"] != "skip"
    ]
    print(f"  {len(need)} files need checksums (skipping {len(rows) - len(need)} already-done or skipped)")
    if not need:
        return

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(_md5_of, root / r["original_path"]): (i, r)
            for i, r in need
        }
        for fut in as_completed(futs):
            i, r = futs[fut]
            try:
                rows[i]["md5"] = fut.result()
            except OSError as e:
                rows[i]["md5"] = ""
                rows[i]["skip_reason"] = (rows[i]["skip_reason"] or f"md5 failed: {e}")
            done += 1
            if done % 50 == 0 or done == len(need):
                print(f"  checksummed {done}/{len(need)}")
    manifest_rows_to_csv(rows, manifest_path)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def cmd_apply(root: Path, manifest_path: Path, delete_fig7_dupes: bool) -> None:
    rows = manifest_load(manifest_path)

    # Safety: every non-skip row must have an md5
    missing = [r for r in rows if r["target_storage"] != "skip" and not r["md5"]]
    if missing:
        sys.exit(f"  ERROR: {len(missing)} rows missing md5 — run `checksums` first.")

    # Collision guard
    by_target: dict[str, list[dict]] = {}
    for r in rows:
        if r["target_storage"] == "skip" or not r["target_relpath"]:
            continue
        by_target.setdefault(r["target_relpath"], []).append(r)
    collisions = {k: v for k, v in by_target.items() if len(v) > 1}
    if collisions:
        sys.exit(f"  ERROR: {len(collisions)} target collisions — refusing to apply.")

    moved, already, skipped = 0, 0, 0
    for r in rows:
        if r["target_storage"] == "skip":
            skipped += 1
            continue
        src = root / r["original_path"]
        dst = root / r["target_relpath"]
        if not src.exists():
            if dst.exists():
                already += 1
                continue
            print(f"  WARNING: missing source {src} (target also missing)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            already += 1
            continue
        # Rename (move) — same filesystem so this is atomic
        src.rename(dst)
        moved += 1

    print(f"  moved {moved}, already-in-place {already}, skipped {skipped}")

    # Clean up emptied subdirectories under each Figure N/
    for fig_dir in sorted(root.iterdir()):
        if not fig_dir.is_dir() or fig_dir.name not in FIGURE_DIRS:
            continue
        # Walk bottom-up so empty parents are removed too
        removed = 0
        for sub in sorted(fig_dir.rglob("*"), key=lambda p: -len(p.parts)):
            if sub.is_dir():
                try:
                    sub.rmdir()
                    removed += 1
                except OSError:
                    pass  # not empty
        if removed:
            print(f"  removed {removed} empty subdirs under {fig_dir.name}")

    # Delete Figure 7 nested duplicates if asked
    if delete_fig7_dupes:
        nested = root / "Figure 7"
        for sub in sorted(nested.iterdir()) if nested.exists() else []:
            if sub.is_dir() and re.match(r"^Figure [1-6]$", sub.name):
                shutil.rmtree(sub)
                print(f"  deleted duplicate tree: {sub.relative_to(root)}")


# ---------------------------------------------------------------------------
# verify + rollback
# ---------------------------------------------------------------------------


def cmd_verify(root: Path, manifest_path: Path) -> None:
    rows = manifest_load(manifest_path)
    missing_src = missing_dst = drift = 0
    for r in rows:
        if r["target_storage"] == "skip":
            continue
        src = root / r["original_path"]
        dst = root / r["target_relpath"]
        if not dst.exists():
            missing_dst += 1
            if src.exists():
                # Pre-apply state
                continue
            print(f"  MISSING both src+dst: {r['original_path']}")
        else:
            if dst.stat().st_size != int(r["size_bytes"]):
                drift += 1
                print(f"  SIZE DRIFT: {r['target_relpath']} "
                      f"manifest={r['size_bytes']} disk={dst.stat().st_size}")
    print(f"  missing destinations: {missing_dst}, size drifts: {drift}")


def cmd_rollback(root: Path, manifest_path: Path) -> None:
    rows = manifest_load(manifest_path)
    restored = 0
    for r in rows:
        if r["target_storage"] == "skip":
            continue
        src = root / r["original_path"]      # where it used to be
        dst = root / r["target_relpath"]     # where it is now
        if dst.exists() and not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            dst.rename(src)
            restored += 1
    print(f"  restored {restored} files to original locations")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pw = sub.add_parser("walk", help="parse files/ and emit manifest")
    pw.add_argument("--root", type=Path, default=Path("files"))
    pw.add_argument("--manifest", type=Path, default=Path("manifest.csv"))

    pc = sub.add_parser("checksums", help="compute MD5s into the manifest")
    pc.add_argument("--root", type=Path, default=Path("files"))
    pc.add_argument("--manifest", type=Path, default=Path("manifest.csv"))
    pc.add_argument("--workers", type=int, default=8)

    pa = sub.add_parser("apply", help="rename + flatten in place")
    pa.add_argument("--root", type=Path, default=Path("files"))
    pa.add_argument("--manifest", type=Path, default=Path("manifest.csv"))
    pa.add_argument("--delete-fig7-dupes", action="store_true")

    pv = sub.add_parser("verify", help="check fs against manifest")
    pv.add_argument("--root", type=Path, default=Path("files"))
    pv.add_argument("--manifest", type=Path, default=Path("manifest.csv"))

    pr = sub.add_parser("rollback", help="reverse an apply")
    pr.add_argument("--root", type=Path, default=Path("files"))
    pr.add_argument("--manifest", type=Path, default=Path("manifest.csv"))

    args = p.parse_args()
    if args.cmd == "walk":
        cmd_walk(args.root, args.manifest)
    elif args.cmd == "checksums":
        cmd_checksums(args.root, args.manifest, args.workers)
    elif args.cmd == "apply":
        cmd_apply(args.root, args.manifest, args.delete_fig7_dupes)
    elif args.cmd == "verify":
        cmd_verify(args.root, args.manifest)
    elif args.cmd == "rollback":
        cmd_rollback(args.root, args.manifest)


if __name__ == "__main__":
    main()
