---
description: QA the upload sheets — CLEAN / SOFT_FLAG / HARD_REJECT (Phase 9)
---

The user wants Phase 9 — QA pass on the consolidated upload sheets.

## Prereqs

- `assay_sheets/Arm*.xlsx` exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/qa_flat_sheets.py`.
2. Read the script's report. The script outputs raw `[BLOCKER]` / `[INFO]` findings. Categorize each row CLEAN / SOFT_FLAG / HARD_REJECT.
3. Print per-arm summary table:
   ```
   ArmA.xlsx (117 rows): 88 CLEAN, 12 SOFT_FLAG, 17 HARD_REJECT
     HARD_REJECT reasons:
       - missing File_PrimaryData (15)
       - dangling Parent UID (2)
     SOFT_FLAG reasons:
       - PLACEHOLDER marker in metadata (10)
       - assay_id unresolved (2)
   ...
   ```
4. Suggest fixes for HARD_REJECT rows:
   - Missing files → use placeholder markers + `/curate-questions add`
   - Dangling parents → check `previous_metadata` master, possibly build the missing parent
   - Pending schema → move to `assay_sheets/pending_schema/`

## Behavioral rules

- `File_PrimaryData` blank → HARD_REJECT (skill rule 8)
- `Link_PrimaryData` / `Checksum_PrimaryData` blank → SOFT_FLAG (not enforced)
- Parent UID not in new sheets or master → HARD_REJECT
- Pending-schema type → HARD_REJECT (move out of upload set)
- `*** PLACEHOLDER: ... ***` marker in `File_PrimaryData` → SOFT_FLAG (intentional)
- Don't be the last gate — surface dispositions to user for confirmation.
