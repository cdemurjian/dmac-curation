---
description: Round-trip diff downloaded metadata vs uploads (Phase 12)
---

The user wants Phase 12 — verify the downloaded `*_AllMetadata.xlsx` matches what was supposed to upload.

Parse `$ARGUMENTS`: `<metadata.xlsx>` (path to downloaded file).

## Prereqs

- `assay_sheets/*-upload-new.xlsx` exists
- `RETRIEVE.TXT` exists
- Downloaded `*_AllMetadata.xlsx` path provided

## Steps

1. Invoke the reviewer:

   ```bash
   uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py \
       --metadata-xlsx <PATH> \
       --retrieve RETRIEVE.TXT \
       --assay-sheets assay_sheets
   ```

   `--retrieve` defaults to `<project-root>/RETRIEVE.TXT` when it exists. Pass
   it explicitly when validating a download from a different retrieve set.

2. Read the three sections of the report:
   - **Field drift** - upload-sheet values vs the round-tripped values
   - **RETRIEVE round trip** - requested UIDs missing from the download, plus
     auto-pulled parents (expected) and unexpected extras
   - **Counts**

3. Distinguish formatting drift (whitespace, case) from semantic drift (a
   genuinely different value). Only the latter is a problem.

4. Auto-pulled parents are **expected**. `chat_nextseek` walks lineage upward,
   so MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL rows appear in the download without being
   requested. Subtract them before alarming about extra rows.

## Behavioral rules

- Don't auto-fix drift. Surface it to the user for resolution.
