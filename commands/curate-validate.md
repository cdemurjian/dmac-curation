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

1. Invoke `uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata <PATH> --retrieve RETRIEVE.TXT`.
2. Read the diff report:
   - Missing UIDs (in RETRIEVE but not in download)
   - Extra UIDs (auto-pulled parents — expected; count separately)
   - Field drift per sample type (compare upload-sheet values to round-tripped values)
3. Print a summary table.
4. Surface any field drift to the user for resolution.

## Behavioral rules

- Auto-pulled parents are expected — don't flag as missing.
- Whitespace / case differences in fields = formatting only, soft note. Different values = real drift, hard flag.
- Don't auto-fix drift. Surface to user.
