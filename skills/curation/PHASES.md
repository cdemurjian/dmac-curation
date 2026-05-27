# Phase reference for dmac-curation

Deep per-phase contract. Read on demand when SKILL.md or a command needs to consult specifics.

For each phase: inputs, outputs, scripts invoked, error modes, edge cases.

---

## Phase 0 — Init

**Command:** `/curate-init [--lab CODE] [--pi NAME]`

**Inputs:** flags. Optionally an empty cwd.

**Action:**
1. Verify cwd is empty (or contains only PI inputs — no `scripts/`, no `context/`, no `CLAUDE.md`). Refuse if not, unless `--force`.
2. Render `templates/CLAUDE.md.j2` → `./CLAUDE.md` with `{lab, pi, init_date}`.
3. Render `templates/env.example.j2` → `./.env.example`.
4. Render `templates/gitignore.j2` → `./.gitignore`.
5. Render `templates/pyproject.toml.j2` → `./pyproject.toml`.
6. Create empty dirs: `files/ manuscript/ previous_metadata/ assay_sheets/ scripts/`.
7. Write `./.dmac-curation.json` lockfile with plugin SHA + schema vintage + lab + pi.
8. Report status.

**Edge cases:**
- cwd not empty: prompt for `--force` or abort
- `--lab` or `--pi` missing: use `AskUserQuestion`, don't guess
- plugin git dir unreadable (no SHA): record `"plugin_sha": null` and warn

---

## Phase 1 — Inventory

**Command:** `/curate-inventory`

**Inputs:** populated `files/`, `manuscript/`, `previous_metadata/`, optional `email_convo.md`

**Action:**
1. Walk `files/` (record `tree -L 2` output + total size).
2. List `manuscript/` (extract docx text if present via zipfile + xml.etree).
3. Inspect every `previous_metadata/*.xlsx` via `scripts/inspect_workbook.py`.
4. Read `email_convo.md` if present.
5. Identify the PI's existing rows in the master xlsx (filter by Scientist column or per-row Notes).
6. Render `templates/FILE_INDEX.md.j2` → `./FILE_INDEX.md`.
7. Suggest `/curate-sample-tree`.

**Edge cases:**
- `files/` empty: still produce a `FILE_INDEX.md` flagging the gap
- Master xlsx absent: flag as a blocker question for the PI
- Multiple master xlsxs (e.g. master + LJP-edits): pick most recent by mtime, note both

---

## Phase 2 — Sample tree

**Command:** `/curate-sample-tree`

**Inputs:** `manuscript/`, `previous_metadata/*.xlsx`, `context/sampletypes_db.json`, `context/assays_db.json`

**Action:**
1. Read manuscript text. Identify experimental arms.
2. For each arm: extract sample types touched. Map to NExtSEEK short codes.
3. Cross-reference against master: which UIDs already exist (`[EXIST]`), which need creating (`[NEW]`).
4. For each new sample type, identify parent type and naming convention from existing rows.
5. Render ASCII trees per arm.
6. Surface open structural questions (Q1, Q2, …) at the bottom.
7. Render `templates/SAMPLE_TREE.md.j2` → `./SAMPLE_TREE.md`.

**Edge cases:**
- New sample type not in `sampletypes_db.json` (e.g., proposed D.REF): mark as PENDING_SCHEMA, add admin question
- Manuscript has no Methods section: pull from email + supplementary docs; flag as a question
- Parent type ambiguous (e.g., D.IMG.Parent = OOC vs CEL/CHM/TIS): follow PI precedent in master, document the deviation

---

## Phase 3 — Questions

**Command:** `/curate-questions [add|list|resolve]`

**Inputs:** conversation context, prior `QUESTIONS_FOR_PI.md`

**Action:**
- `add`: prompt for topic + body + originating phase; append to file
- `list`: print all open questions with IDs
- `resolve <id>`: move from open to resolved, prompt for answer

**Edge cases:**
- File doesn't exist yet: create from template on first `add`
- ID collision: increment until unique

---

## Phase 4 — Task plan

Uses `TaskCreate` directly. No standalone command. SKILL.md instructs Claude to create one task per arm with `blockedBy` dependencies (e.g., Arm G blocked by Arm E + Arm F).

---

## Phase 5 — Build

**Command:** `/curate-build [<arm>]`

**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master), `manuscript/`, `CLAUDE.md` (lab + pi)

**Action:**
1. Identify arm. If not supplied, list arms from `SAMPLE_TREE.md` and `AskUserQuestion`.
2. Read sample types and counts for the arm.
3. Read master to identify existing parent UIDs.
4. Read manuscript for protocol section names, instrument details.
5. Generate `./scripts/build_<arm>.py`:
   - PEP 723 inline deps (openpyxl)
   - `sys.path.insert(0, "<PLUGIN_PATH>/scripts")`
   - `from _common import mint_uid, write_4sheet_xlsx, ...`
   - Mint UIDs `<TYPE>-YYMMDD<LAB>-N`
   - Write 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type → `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`
6. Run the script. Report row counts.
7. Suggest next arm or `/curate-consolidate`.

**Edge cases:**
- Missing manifest data (e.g., 27 phospho rows have no file paths): use placeholder markers
- Sample type new to schema: write to `assay_sheets/pending_schema/`
- Mid-arm scope ambiguity: stop, add to QUESTIONS, propose to user

---

## Phase 6 — Consolidate

**Command:** `/curate-consolidate`

**Inputs:** `assay_sheets/4sheet_originals/*.xlsx`, optional `context/assay_ids_cache.json` + `context/assay_synonyms.json`

**Action:**
1. Invoke `scripts/consolidate_to_flat.py`.
2. Archive 4-sheet originals if not already in `4sheet_originals/`.
3. Per arm: produce flat-format xlsx with `Samples` sheet (cols: uid, sampletype, name, parent, notes_summary, assay_titles, assay_ids, json_metadata) + `README` sheet.
4. Report per-arm row counts.

**Edge cases:**
- Cache or synonyms missing: leave `assay_ids` blank, suggest `/curate-resolve-assays`
- Pending-schema sample types: write to `assay_sheets/pending_schema/Arm<X>.xlsx`
- D.REF leak-back on re-run: warn user

---

## Phase 7 — Resolve assays

**Command:** `/curate-resolve-assays --project-id N`

**Inputs:** `.env` with `NEXTSEEK_USERNAME` + `NEXTSEEK_PASSWORD`, project ID

**Action:**
1. Invoke `scripts/nextseek_api.py fetch-assays --project-id N`.
2. Write `context/assay_ids_cache.json` in cwd.
3. Diff cached assay titles vs cited titles in build scripts.
4. For unresolved titles, prompt user to curate `context/assay_synonyms.json` (LLM-judgment layer, per yufei-gemm-2 design).
5. Update `.dmac-curation.json` lockfile with `nextseek_project_id`.

**Edge cases:**
- Auth fail (401): re-prompt for `.env` values, don't log
- Pagination hang: `nextseek_api.py` already fixed (next-link-only termination)
- Project has zero assays: warn, ask user to verify project ID

---

## Phase 8 — Synonyms (no command, LLM-driven)

Embedded in Phase 7 flow. SKILL.md instructs: read `assay_ids_cache.json`, compare against `assay_titles` columns in `assay_sheets/Arm*.xlsx`, propose mappings, ask user to confirm. Write `context/assay_synonyms.json` with `_README` + `synonyms` keys, each entry annotated with a `_notes` block.

---

## Phase 9 — QA

**Command:** `/curate-qa`

**Inputs:** `assay_sheets/Arm*.xlsx`, master xlsx for parent resolvability

**Action:**
1. Invoke `scripts/qa_flat_sheets.py`.
2. Per row: classify CLEAN / SOFT_FLAG / HARD_REJECT (the command interprets the script's raw [BLOCKER]/[INFO] findings into these disposition labels).
3. Report counts + per-row dispositions.
4. Surface specific gaps (missing File_PrimaryData, dangling parents, malformed json_metadata, surprise placeholder markers).

**Edge cases:**
- File_PrimaryData blank: HARD_REJECT (per skill rule 8 — required)
- Link_PrimaryData / Checksum_PrimaryData blank: SOFT_FLAG (not enforced)
- Parent UID not in new sheets or master: HARD_REJECT (dangling)
- Pending-schema type: HARD_REJECT (move to pending_schema/)
- Marker like `*** PLACEHOLDER: ... ***` in `File_PrimaryData`: SOFT_FLAG (acceptable)

---

## Phase 10 — Deposit

**Command:** `/curate-deposit <geo|zenodo|omero> [args]`

Routes by first arg:

### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

- Drives `scripts/deposit/geo_build_xlsx.py` to render BULK_filled.xlsx or SPTX_filled.xlsx from filled metadata.
- Drives `scripts/upload_geo_ncftp.sh` for upload.
- After GEO acceptance (manual confirmation): `scripts/apply_geo_accessions.py --write` patches D.SEQ/A.GEX/A.SPTX with GSM URLs.

### `/curate-deposit zenodo [--record-id N]`

- Drives `scripts/stage_zenodo.py --dry-run` then (after user confirms) without `--dry-run`.
- User uploads zips to Zenodo manually via web UI.
- After upload: `scripts/apply_zenodo_links.py --write --record-id N` patches `Link_PrimaryData`.

### `/curate-deposit omero [--project-id N]`

- User uploads images manually via OMERO Insight.
- `scripts/omero_pull.py all --project N` → `omero_images.csv`.
- `scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData`.

**Edge cases:**
- GEO literal validation failures: re-prompt user with corrected literals
- ncftp timeout on big file: script already has retry loop
- OMERO upload partial: diff `omero_images.csv` against manifest, identify missing IDs
- Zenodo record not created yet: surface to user, suggest creating record first

---

## Phase 11 — Retrieve

**Command:** `/curate-retrieve [--include-parents]`

**Inputs:** `assay_sheets/*-upload-new.xlsx`

**Action:**
1. Invoke `scripts/build_retrieve.py`.
2. By default exclude DNA/RNA/MUS/TIS/PAT/PAV/CHM/CEL (auto-pulled by `chat_nextseek`).
3. Write `./RETRIEVE.TXT` (newline-separated, sorted).
4. Report per-sample-type counts.

**Edge cases:**
- No upload-new sheets present: refuse, suggest `/curate-build` + `/curate-consolidate`
- User passes UIDs to fetch via `chat_nextseek`; auto-pulls parents; returns `*_AllMetadata.xlsx`

---

## Phase 12 — Validate

**Command:** `/curate-validate <metadata.xlsx>`

**Inputs:** downloaded `*_AllMetadata.xlsx` from `chat_nextseek`, current `RETRIEVE.TXT`, upload sheets

**Action:**
1. Invoke `scripts/review_metadata_vs_uploads.py`.
2. Diff: which RETRIEVE UIDs are missing from the download; which upload-sheet field values differ from the round-tripped values; which parents auto-pulled.
3. Report.

**Edge cases:**
- Auto-pulled parents count: subtract from "extra rows" before alarming
- Field drift: distinguish formatting changes (whitespace, case) from semantic drift (different value)

---

## Phase 13 — Email

**Command:** `/curate-email`

**Inputs:** `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md`, deposit state, `CLAUDE.md` (lab + pi)

**Action:**
1. Read project state.
2. Render `templates/EMAIL_TO_PI.md.j2` → `./EMAIL_TO_PI.md` with: subject, greeting, summary paragraph, files-curated summary, questions, deposit status, asks.
3. Iterate per-section with the user (skeleton-first; user writes final voice).
4. Hard rules: Name-pattern anchors not row numbers; no em dashes.

**Edge cases:**
- Manuscript references in questions: use Name-patterns (`the 27 rows ending in _phospho`)
- Long deposit lists: bullet, don't paragraph
- Multiple PIs: address all in greeting, ask user

---

## Phase any — Status

**Command:** `/curate-status`

**Action:** scan cwd for artifact files, lockfile, read state. Print:
- Phase artifacts present (✓ / ✗)
- Lockfile contents (lab, pi, project_id, plugin SHA)
- Suggested next command
