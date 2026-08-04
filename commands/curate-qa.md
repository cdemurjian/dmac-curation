---
description: QA the upload sheets — CLEAN / SOFT_FLAG / HARD_REJECT (Phase 9)
---

The user wants Phase 9 — QA pass on the consolidated upload sheets.

## Prereqs

- `assay_sheets/Arm*-upload.xlsx` exists (or a `-upload-new.xlsx` working copy)

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/qa_flat_sheets.py --upload assay_sheets/Arm{X}-upload.xlsx [--master-baseline previous_metadata/<master>.xlsx] [--expected-counts <sampletype>=<n>,...]`.
   **Always pass `--master-baseline` with a FRESH DB pull** — it powers the
   UID-vs-DB collision net (a new UID that already exists in the pull would
   overwrite another study on upload). Without a baseline the net can't run.
   Refresh it with `nextseek_api.py pull-db --project-id N` before QA.
2. Read the script's report. The script outputs raw `[BLOCKER]` / `[INFO]` findings. Categorize each row CLEAN / SOFT_FLAG / HARD_REJECT.
3. Print per-arm summary table:
   ```
   ArmA-upload.xlsx (117 rows): 88 CLEAN, 12 SOFT_FLAG, 17 HARD_REJECT
     HARD_REJECT reasons:
       - missing File_PrimaryData (15)
       - dangling Parent UID (2)
     SOFT_FLAG reasons:
       - PLACEHOLDER marker in metadata (10)
       - assay_id unresolved (2)
   ...
   ```
4. Suggest fixes for HARD_REJECT rows:
   - Missing values, **in-prep** study → placeholder markers + `/curate-questions add`
   - Missing values, **published/submitted** study → run the Published-paper harvest (SKILL.md) across manuscript Methods / Supplemental Methods / Data Availability + the master sheet; if still absent, leave blank and `/curate-questions add` — no placeholder
   - Dangling parents → check `previous_metadata` master, possibly build the missing parent
   - Pending schema → move to `assay_sheets/pending_schema/`

## Behavioral rules

- **New UID already in the DB baseline → HARD_REJECT (stamp collision).** On
  upload it OVERWRITES that record. This is the second net behind
  `stamp_guard` (the build guard) — if a build was hand-edited to skip the guard,
  QA still catches it. Exception: a deliberate update/restore batch (e.g. fixing
  a prior collision) legitimately targets existing UIDs — re-run with
  `QA_ALLOW_DB_UPDATES=1` to downgrade it to `[INFO]`, and only after confirming
  every listed UID is one you intend to overwrite.
- `File_PrimaryData` blank → HARD_REJECT (skill rule 8)
- `Link_PrimaryData` / `Checksum_PrimaryData` blank → SOFT_FLAG (not enforced)
- Parent UID not in new sheets or master → HARD_REJECT
- Pending-schema type → HARD_REJECT (move out of upload set)
- `*** PLACEHOLDER: ... ***` marker in `File_PrimaryData` → SOFT_FLAG (intentional; in-prep studies)
- A blank required field on a **published/submitted** study is still HARD_REJECT, but expect a matching entry in `QUESTIONS_FOR_PI.md` — cross-reference it rather than proposing a placeholder (SKILL.md Published-paper harvest).
- Don't be the last gate — surface dispositions to user for confirmation.
