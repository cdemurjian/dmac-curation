---
description: Show pipeline state (any phase)
---

The user wants to know where the project is in the 13-phase pipeline.

## Steps

1. Read `.dmac-curation.json` (lockfile). If missing, advise `/curate-init`.
2. Check for presence of artifact files (per phase):
   - Phase 1: `FILE_INDEX.md`
   - Phase 2: `SAMPLE_TREE.md`
   - Phase 3: `QUESTIONS_FOR_PI.md` (with open vs resolved count)
   - Phase 5: `assay_sheets/4sheet_originals/*.xlsx` (count)
   - Phase 6: `assay_sheets/Arm*.xlsx` (excluding 4sheet_originals/)
   - Phase 7: `context/assay_ids_cache.json` + `context/assay_synonyms.json`
   - Phase 11: `RETRIEVE.TXT` (line count)
   - Phase 13: `EMAIL_TO_PI.md`
3. Read `assay_sheets/` for upload-new sheets vs upload sheets; report counts.
4. Print a status table:

   ```
   Project: marie (KAM) — initialized 2026-05-27
   Lockfile: plugin SHA abc123, schema vintage 2026-05-08

   Phase 1 Inventory:     ✓  FILE_INDEX.md (4.2 KB)
   Phase 2 Sample tree:   ✓  SAMPLE_TREE.md (8 arms)
   Phase 3 Questions:     ✓  12 open, 8 resolved
   Phase 5 Build:         ✓  6/8 arms built (20 4sheet files)
   Phase 6 Consolidate:   ✗
   Phase 7 Resolve:       ✗
   ...
   Phase 13 Email:        ✗

   Suggested next: /curate-build (arms C, G still pending)
   ```
5. Make a suggestion for next command based on current state.

## Behavioral rules

- Be honest about partial state (e.g., 6/8 arms).
- Don't reformat — terse table is fine.
- Always end with a single-line "Suggested next: …".
