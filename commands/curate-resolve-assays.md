---
description: Fetch project assays via NExtSEEK API and curate synonyms (Phase 7-8)
---

The user wants Phase 7 — resolve assay titles to integer IDs by fetching the live project catalog from NExtSEEK.

Parse `$ARGUMENTS`: `--project-id N` (required).

## Prereqs

- `./.env` exists with `NEXTSEEK_USERNAME` and `NEXTSEEK_PASSWORD` (or `NEXTSEEK_TOKEN`)
- `assay_sheets/Arm*.xlsx` exists (so we have titles to resolve)

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id <N>`.
2. Verify `context/assay_ids_cache.json` written.
3. Diff cached assay titles against `assay_titles` columns in `assay_sheets/Arm*.xlsx`.
4. For each unresolved title, propose a synonym mapping. Use `AskUserQuestion` per mapping (don't batch — judgment per row).
5. Write `context/assay_synonyms.json` with structure:
   ```json
   {
     "_README": [...],
     "synonyms": {
       "<cited title>": "<actual project assay title>"
     },
     "intentionally_unmapped": ["<title>"]
   }
   ```
   Each synonym entry should have a `_notes` block explaining why.
6. Update `.dmac-curation.json` lockfile with `nextseek_project_id`.
7. Suggest re-running `/curate-consolidate` to apply the new assay_ids.

## Behavioral rules

- Auth fail (401): re-prompt for `.env` values; never log.
- Don't auto-map heuristically. Curate per-row with user input (this is the LLM-judgment step Charlie explicitly carved out).
- Note explicitly-unmapped assays (e.g., "Mouse Challenge" not registered as project-10 assay).
