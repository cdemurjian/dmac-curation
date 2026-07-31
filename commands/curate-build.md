---
description: Build per-arm upload sheets (Phase 5)
---

The user wants to build assay-sheet rows for a specific experimental arm.

Parse `$ARGUMENTS`: optional `<arm>` (letter or short name). If omitted, list arms from `SAMPLE_TREE.md` and use `AskUserQuestion`.

## Prereqs

- `./SAMPLE_TREE.md` exists
- `./previous_metadata/*.xlsx` exists (master)
- `./CLAUDE.md` exists (lab + pi)
- `./.env` exists (warn if missing — needed at consolidate)

## Steps

1. Read `SAMPLE_TREE.md`, identify the arm. Read sample types and counts.
2. Read master xlsx for existing parent UIDs (cell-line CEL UIDs, patient PAT UIDs, etc.) — don't recreate.
3. Gather field values. For a **published/submitted** study (Data Availability statement, an accession, or a DOI in the manuscript — or the user says so), run the Published-paper harvest (SKILL.md): check the manuscript Methods, Supplemental Methods, and Data Availability statement, plus the master NExtSEEK sheet (`previous_metadata/`), for instrument, platform, and protocol details before deciding a value is missing.
4. Generate `./scripts/build_<arm>.py`. The file must:
   - Begin with PEP 723 inline-deps header (`openpyxl>=3.1`)
   - Insert `<PLUGIN_PATH>/scripts` into `sys.path`
   - `from _common import mint_uid, write_4sheet_xlsx, ...` (use functions that actually exist; consult `<PLUGIN>/scripts/_common.py`)
   - Define `ROW_INFO` / `ARM_BY_COL` / `TIMEPOINT_BY_COL` constants encoding the arm's structure
   - Mint UIDs from N=1 per sample type
   - Write 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type to `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`
5. Save the script. Run it: `uv run --script ./scripts/build_<arm>.py`.
6. Report row counts per file.
7. Suggest the next arm or `/curate-consolidate`.

## Behavioral rules

- Follow precedent over schema (sample existing PI rows in `previous_metadata/` before writing new ones — schema lies, workbook tells truth).
- Unknown values: for an **in-prep** study use `*** PLACEHOLDER: ... ***` markers, never blanks (greppable). For a **published/submitted** study, harvest the four sources first (SKILL.md); if a value is genuinely absent, leave it blank and add a name-pattern-anchored question to `QUESTIONS_FOR_PI.md` — no placeholder.
- Pre-assigned UIDs (no auto-gen). Format `<TYPE>-YYMMDD<LAB>-N`.
- Don't include parent-tier records that already exist — `/curate-retrieve` auto-pulls them.
- If the arm has new sample types not in `sampletypes_db.json` (e.g., `D.REF`), write to `assay_sheets/pending_schema/` and note in `QUESTIONS_FOR_PI.md`.
- The 4-sheet files you write are a **curator review artifact**, not a build
  intermediate. They are what a person eyeballs per sample type before
  `/curate-consolidate` collapses them. Do not propose skipping them.
- If `schema/<TYPE>.ontology.json` exists in the project, pass it to
  `write_4sheet_xlsx(ontology=...)`. The Ontology sheet is the only place
  NExtSEEK enforces controlled vocabulary.
