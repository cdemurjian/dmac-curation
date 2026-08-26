---
description: Build per-arm upload sheets (Phase 5)
---

The user wants to build assay-sheet rows for a specific experimental arm.

Parse `$ARGUMENTS`: optional `<arm>` (letter or short name). If omitted, list arms from `SAMPLE_TREE.md` and use `AskUserQuestion`.

## Prereqs

- `./SAMPLE_TREE.md` exists
- `./previous_metadata/*.xlsx` exists — and must be a **fresh DB pull** (a NExtSEEK
  `CSBC All …` / AllMetadata export pulled right before this session). The build
  guard checks the intended UID stamp against it; a stale pull won't show a stamp
  another curator claimed since it was exported, so the check would pass falsely.
  Grab one with:
  `uv run --script <PLUGIN>/scripts/nextseek_api.py pull-db --project-id N`
  (downloads the project's master export straight into `previous_metadata/`).
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
   - **`from stamp_guard import preflight`, and call it BEFORE minting any UID:**
     `preflight([<sample types this arm mints>], LAB, DATE, project_root=".")`.
     This is the root-cause guard against UID-stamp collisions — it refuses to
     mint into a `<DATE><LAB>` stamp that already has rows in the DB pull (which
     would OVERWRITE another study on upload) and refuses if the pull is
     missing/stale. On a collision it raises with a suggested free stamp; pick a
     fresh `DATE` and retry. Never delete the call to "make it run."
   - Define `ROW_INFO` / `ARM_BY_COL` / `TIMEPOINT_BY_COL` constants encoding the arm's structure
   - Mint UIDs from N=1 per sample type — **safe only because the guard proved the
     stamp is unused.** When multiple arms share one batch, keep the stamp constant
     and offset N per arm (arm A `1..k`, arm B `k+1..`), never restart at 1.
   - Write 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type to `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`
5. Save the script. Run it: `uv run --script ./scripts/build_<arm>.py`.
6. Report row counts per file.
7. Suggest the next arm or `/curate-consolidate`.

## Behavioral rules

- **UID stamp is not free until proven free.** `<DATE><LAB>` (e.g. `190221WHI`) is
  shared across every curator's batches. Minting from N=1 into a stamp another
  batch already used silently overwrites their records on upload — a real
  incident (Flower_Tyro clobbered 18 Leddy immunopeptidomics rows). The
  `stamp_guard.preflight` call is mandatory and must run against a fresh DB pull;
  do not pick a stamp by hand without it. `STAMP_GUARD_OVERRIDE=1` exists only for
  a deliberate, eyes-open re-upload into an existing stamp — never as a way to
  silence a real collision.
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
