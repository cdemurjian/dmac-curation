---
description: Collapse 4-sheet xlsx files into flat-format Arm{X}.xlsx (Phase 6)
---

The user wants Phase 6 — consolidate the per-sample-type 4-sheet xlsx files into per-arm flat-format upload sheets.

## Prereqs

- `assay_sheets/4sheet_originals/*.xlsx` exists with at least one file
- Or, if re-running, `assay_sheets/*.xlsx` already exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py [--assay-sheets ./assay_sheets] [--all-in-one <NAME>]`.
2. Verify per-arm xlsx files written to `assay_sheets/`.
3. If `context/assay_ids_cache.json` exists, the script populates the `assay_ids` column. Report resolution stats.
4. If `assay_ids` is mostly empty, suggest `/curate-resolve-assays --project-id N`.
5. Otherwise, suggest `/curate-qa`.

## Behavioral rules

- Check for manual edits in `assay_sheets/Arm*.xlsx` before regenerating. If files exist with mtime newer than `4sheet_originals/`, diff first; ask user.
- Idempotent — safe to re-run.
- Move `D.REF` or other pending-schema rows to `assay_sheets/pending_schema/`.
