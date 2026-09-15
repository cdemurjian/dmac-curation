---
description: Collapse 4-sheet xlsx files into flat-format Arm{X}-upload.xlsx (Phase 6)
---

The user wants Phase 6 — consolidate the per-sample-type 4-sheet xlsx files into per-arm flat-format upload sheets.

## Prereqs

- `assay_sheets/4sheet_originals/*.xlsx` exists with at least one file
- Or, if re-running, `assay_sheets/*.xlsx` already exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`.
2. Verify per-arm `Arm{X}-upload.xlsx` files written to `assay_sheets/`. The `-upload` suffix means retrieve/deposit read them as-is — no rename step.
3. If `context/assay_ids_cache.json` exists, the script populates the `assay_ids` column. Report resolution stats.
4. If `assay_ids` is mostly empty, suggest `/curate-resolve-assays --project-id N`.
5. Otherwise, suggest `/curate-qa`.

## What `assay_ids` means

`assay_ids` is **per row**, not per file: it is the union of the row's own assay
(the assay its sample type is the output of) and **every assay it is a parent
to**. `assay_titles` carries the matching titles in the same order.

This is deliberate and load-bearing. NExtSEEK can only put an assay label on a
`DERIVED_FROM` edge when the parent and the child are *both* members of that
assay. Registering only the output leaves every edge into that assay unlabelled
and the sample-type connection map does not draw the step at all. The 4-sheet
format has one assay per file and cannot express this; the flat format carries
`assay_ids` per row, which is the reason it exists.

**Closure:** the union only closes over parents present in the same output
workbook. A parent minted in another arm stays unregistered and is left for
`assay` mode to repair. Run `--all-in-one` when you want the union to close
across arms.

`/curate-qa` fails the sheet when a parent and child share no assay, so this
surfaces at phase 9A rather than as a graph gap found weeks later.

## Behavioral rules

- Check for manual edits in `assay_sheets/Arm*-upload.xlsx` before regenerating. If files exist with mtime newer than `4sheet_originals/`, diff first; ask user.
- Idempotent — safe to re-run. Re-runs delete and rewrite `Arm{X}-upload.xlsx` (and clean legacy `Arm{X}.xlsx`), but never touch a `-upload-new.xlsx` working copy (hard rule 2).
- Move `D.REF` or other pending-schema rows to `assay_sheets/pending_schema/`.
- Flat format has no Ontology sheet, so any controlled vocabulary in the 4-sheet
  originals is dropped here. That is expected. Tell the user which format they
  are uploading and why, rather than letting the loss be silent.
