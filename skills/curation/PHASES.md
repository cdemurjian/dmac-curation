# Phase reference for dmac-curation

Deep per-phase contract. Read on demand when SKILL.md or a command needs to consult specifics.

For each phase: inputs, outputs, scripts invoked, error modes, edge cases.

## Phase table

15 commands drive 13 phases. Phase 9 is split into 9a (`/curate-qa`, local) and
9b (`/curate-qc`, server-side); phases 4 and 8 were retired as numbers (see
"Retired phases"); the surviving numbers are deliberately **not** renumbered,
because every scaffolded project's `CLAUDE.md` bakes in the order,
`/curate-status` maps artifacts by number, and curators speak in phase numbers.

**A phase inserted later takes a letter suffix, never a retired number.**
Protocols slot between Questions and Build as 3b, the same way server-side QC
slots after QA as 9b. Reusing 4 would silently redefine a number that older
project notes still use for the task plan.

The 12 pipeline phases run inventory (1) through email (13):

| # | Phase | Command | Artifact |
|---|---|---|---|
| 1 | Inventory | `/curate-inventory` | `FILE_INDEX.md` |
| 2 | Sample tree | `/curate-sample-tree` | `SAMPLE_TREE.md` |
| 3 | Questions | `/curate-questions [add\|list\|resolve]` | `QUESTIONS_FOR_PI.md` |
| 3b | Protocols | `/curate-protocols [--project-id N]` | `protocols/P.*.docx` + `protocols/COVERAGE.md` |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}-upload.xlsx` (flat format) |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` + `context/assay_synonyms.json` |
| 9 | QA | `/curate-qa` | console disposition report |
| 10 | Deposit | `/curate-deposit <geo\|zenodo\|omero>` | external uploads + `Link_PrimaryData` backfilled |
| 11 | Retrieve | `/curate-retrieve` | `RETRIEVE.TXT` |
| 12 | Validate | `/curate-validate <metadata.xlsx>` | console diff report |
| 13 | Email | `/curate-email` | `EMAIL_TO_PI.md` |

---

Phase 0 precedes them all: `/curate-init` scaffolds the project. It is the init
step, not one of the 11 pipeline phases.

| # | Phase | Command | Artifact |
|---|---|---|---|
| 0 | Init | `/curate-init [--lab CODE] [--pi NAME] [--mode NAME]` | scaffold cwd + `.dmac-curation.json` lockfile |

### Retired phases

**Phase 4 (task plan)** had no command, no script and no artifact; it existed
only as TaskList state. Using a task list is good practice, not a pipeline
stage. Its guidance is folded into Phase 3's tail.

**Phase 8 (synonyms)** was always the same command and invocation as Phase 7.
It existed in the table only because `assay_synonyms.json` is a second
artifact, and artifacts are not phases. It is documented as a Phase 7 output.

Neither number is reused.

---

## What an "arm" is

An **arm is a unit of build work** — the granularity at which the pipeline chunks, checkpoints,
and parallelises a curation. It is not a formal NExtSEEK concept; it exists only in this pipeline.

An arm is what flows through the whole back half:

| Phase | What the arm is |
|---|---|
| 2 | one ASCII tree per arm in `SAMPLE_TREE.md` |
| 4 | one task per arm, optionally `blockedBy` other arms |
| 5 | one `scripts/build_<arm>.py` + a set of `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx` |
| 6 | one flat `assay_sheets/Arm{X}-upload.xlsx` |
| 7, 9, 12 | iterated over as `Arm*-upload.xlsx` |

Arms are labelled by letter (`A`, `B`, `C`, …) and are the argument to `/curate-build <arm>`.
`/curate-status` reports progress as "6/8 arms built".

**The word borrows clinical-trial language, but do not take it literally.** A trial arm is a
treatment group, and treatment groups are independent by construction. Arms here are not: Phase 4
explicitly supports "Arm G blocked by Arm E + Arm F". An arm is better read as *a coherent chunk of
the dataset that can be built in one pass* — sometimes a
treatment group, sometimes a downstream product that needs two upstream chunks finished first.

### When to split into separate arms

Split when the arms **differ in structure** — different sample types, different assays, different
depth of tree. Splitting then buys real isolation: each arm builds, QAs and uploads on its own, and
a problem in one does not block the others.

Do NOT split when the groups differ only in the **value of an attribute**. Three treatment groups
that share an identical sample-type chain and differ only in a `Treatment` field are one arm with a
column, not three arms. Splitting them produces near-identical trees and multiplies the workbook
count for no isolation benefit, and gives the copies room to drift apart.

Rule of thumb: if two candidate arms would produce the same ASCII tree with only a label changed,
they are one arm.

## Phase 0 — Init

**Command:** `/curate-init [--lab CODE] [--pi NAME] [--mode NAME]`

**Inputs:** flags. Any cwd - empty, populated with PI inputs, or an existing
curation project.

**Action:** the command is **additive**. It creates what is missing and never
overwrites what exists.

1. Create any missing directories: `files/ manuscript/ previous_metadata/ assay_sheets/ scripts/`.
2. Render any missing templates (`CLAUDE.md`, `.env.example`, `.gitignore`, `pyproject.toml`). Existing files are reported and left alone.
3. Merge the requested mode into `./.dmac-curation.json` via `scripts/_lockfile.py`, which also migrates a v0 lockfile to v1 in place.
4. Report what was created, what was skipped, and which modes the lockfile records.

**Edge cases:**
- Existing project: adding a mode is the normal path, not an error. Prior mode sections are preserved.
- v0 lockfile (no `schema_version`): flat keys migrate into `modes.pipeline`. No data is lost.
- `--lab` or `--pi` missing for pipeline mode: use `AskUserQuestion`, don't guess. A wrong lab code contaminates every minted UID.
- `schema` / `report` mode: no scaffold and no lab/pi needed. These modes must work from any cwd.
- Plugin git dir unreadable: record `"plugin_sha": null` and warn.
- A `.env` in cwd: report it, continue, never read or print it.

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
8. Write `./sample_tree.json` — one node per sample type (with `count` = rows to create), one edge
   per parent→child assay connection, carrying manuscript quotes and rationale. Omit `clade`; it is
   derived from the assay's `Parent Clade Type` / `Child Clade Type`.
9. Run `scripts/build_sample_tree_html.py` → `./SAMPLE_TREE.html`, the interactive review view.

**Outputs:** `SAMPLE_TREE.md` (narrative, edited by hand), `sample_tree.json` (source of truth for
the graph), `SAMPLE_TREE.html` (build artifact — regenerate, never edit). All three describe one
tree derived once; they must not disagree.

**Edge cases:**
- New sample type not in `sampletypes_db.json` (e.g., proposed D.REF): mark as PENDING_SCHEMA, add admin question, and set `"match_type": "proposed_new"` so the viewer draws it dashed
- Manuscript has no Methods section: pull from email + supplementary docs; flag as a question
- Parent type ambiguous (e.g., D.IMG.Parent = OOC vs CEL/CHM/TIS): follow PI precedent in master, document the deviation
- Clade warning on render: the declared clade contradicts the assay definition, or no assay covers the edge. Fix the model — don't suppress the warning
- No organism-tier type for the study system (e.g., insects): fold organism attributes onto the tissue node, leave `Parent` a placeholder, and raise a vocabulary question

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

### Task-plan guidance (formerly Phase 4)

Use `TaskCreate` to record one task per arm, with `blockedBy` dependencies (e.g.
Arm G blocked by Arm E plus Arm F). This is good practice, not a pipeline stage
- it has no command, no script and no artifact, which is why it is no longer
numbered.

---

## Phase 3b - Protocols

**Command:** `/curate-protocols [--project-id N] [--only <topic>]`

**Inputs:** `sample_tree.json` (which assays need documenting), `manuscript/`
(the Methods text), `.dmac-curation.json` (lab + stamp), `.env` (registration only)

**Outputs:** `protocols/P.<LAB>-<STAMP>-V<n>_<Topic>.docx` (one per topic),
`protocols/COVERAGE.md` (build artifact), `protocols/README.md` (narrative),
`protocols/_sops.json` (registration index, written by the upload)

### Why it sits between 3 and 5

The `Protocol` column of every upload row carries a **SOP title verbatim**, so
the SOPs must exist before Phase 5 writes rows that cite them. And the tree is
what says which assays need documenting, so it must exist first. That fixes the
position: after 2, before 5.

### The judgment is in two JSON files, not in the script

`scripts/build_protocols.py` is deterministic. It renders, verifies and reports;
it never decides which manuscript section belongs in which protocol. That
decision lives in:

- `protocols/_methods.json` - verbatim Methods sections, one entry per heading,
  a transcription rather than a summary. A section may repeat; occurrences are
  consumed in document order.
- `protocols/_manifest.json` - `lab`, `stamp`, `version`, and one entry per
  protocol giving its `topic`, the `headings` it consumes, the `assays` it
  documents, and a `note` carried into Table A.

Splitting it this way is what makes the extraction reproducible and the coverage
tables derivable. A curator can re-read the manifest and see every mapping
decision in one screen.

**The `assays` strings must match the tree's edge assays exactly**, `- Metadata`
and `- Data Linked` suffixes included. That string is the join key between a
protocol and an edge; a near-miss reports the edge as uncovered and nothing
errors.

### Three checks the build enforces

1. **Every heading the manifest names exists** in the methods file.
2. **Every section is consumed exactly as often as it occurs.** An unconsumed
   section is a protocol someone forgot to write; an overused one is a section
   pasted into two documents.
3. **Every body paragraph round-trips verbatim** out of the written `.docx`.
   Sections marked `"verbatim": false` are exempt, which is how a transcribed
   display equation (the PDF floats it as un-extractable math) passes without
   weakening the check for everything else.

### No Methods text means no protocol files

A study with no written Methods and no PI-supplied protocol documents gets the
coverage report and a question per uncovered assay, and nothing else. **Do not
write placeholder protocols.** A `*** PLACEHOLDER ***` marker is right in a
spreadsheet cell, where QA greps for it; it is wrong in a SOP, which gets
registered on a shared server and emailed to a PI as if it described a real
procedure. Phase 5 can proceed with a blank `Protocol` column.

### Registration writes to a live server, so ask the user first

**Approval to run phase 3b is not approval to upload.** Authoring the documents
is local and reversible; registering them is neither. SOP records land in a
catalog every curator on the project shares, they get cited by row after row,
and there is no clean undo. So registration is always three steps:

1. `scripts/upload_sops.py --project-id N` previews and writes nothing.
2. Show that preview to the user and put the decision to them with
   `AskUserQuestion`, naming the server, the project id, and the record count.
3. Only after a clear yes: `--write --confirmed`.

`--write` on its own is REFUSED before any network call. `--confirmed` asserts
that a human saw the preview and approved it, which makes a false assertion a
visible act rather than a silent omission. This mirrors `sampletype_attr.py`,
where a live schema write needs `--apply` plus `--yes-production`: in this
codebase a shared-server write always costs a second, deliberate flag.

A re-run is still an upload. Resuming an interrupted batch, or adding one more
protocol with `--only`, needs its own yes.

Two NExtSEEK behaviours are already handled and should not be "fixed" again:
`POST /nextseek_api/sops/` can return HTTP 500 with an HTML body **while still
creating the record**, and it rewrites the submitted title with a
`<YYMMDD>-V<n>_` prefix. The script therefore verifies against the server rather
than the response, then `PATCH`es the canonical title. Reported upstream as
[BioMicroCenter/NExtSEEK#109](https://github.com/BioMicroCenter/NExtSEEK/issues/109).

**Edge cases:**
- Document already exists: skipped. `--force` rewrites it, but if it is already
  registered or emailed, bump `version` to `V2` instead of rewriting `V1`
  underneath the record that cites it.
- A protocol matching no edge is not automatically wrong. Study-wide statistics
  and analysis methods for an out-of-scope tier are real methods with no row.
  Keep them registered and say why in the `note`.
- An edge matching no protocol IS a gap. Table B is the checklist.
- Half-finished upload: re-run it. The skip list is built from the server, so a
  batch interrupted mid-way resumes cleanly.
- `COVERAGE.md` is regenerated, never hand-edited. After registering, re-run
  `--coverage-only` so Table A carries the SOP ids.

---

## Phase 5 — Build

**Command:** `/curate-build [<arm>]`

**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master), `manuscript/`, `.dmac-curation.json` (lab + pi)

**Output:** `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`, one per sample
type, plus the generated `./scripts/build_<arm>.py` that produced them.

### The 4-sheet output is a review artifact, not a build intermediate

This is the single most important thing to know about Phases 5 and 6, and it is
invisible in the code.

The obvious challenge is: why build 4-sheet at all, when flat is what NExtSEEK
ingests? There is a hard technical reason for two formats, stated in
`consolidate_to_flat.py:19-21` - multiple sample types in one file are **only
allowed in flat format**, so a per-arm file mixing types must be flat. But that
alone would still allow building flat directly.

**The deciding reason is human: curators review the per-sample-type 4-sheet
files before consolidation.** The per-type split is what makes eyeballing
tractable. A future reader without this will re-derive the challenge and reach
the wrong conclusion, as the 2026-07-21 pipeline review nearly did.

So: Phase 5's output is what a person looks at. Phase 6's output is what a
machine ingests. Neither replaces the other.

### The Ontology sheet is where controlled vocabulary lives

`_common.write_4sheet_xlsx` accepts `ontology={fieldname: [allowed values]}`,
writes a real Ontology sheet, and declares those fields `Controlled Ontology` on
the Instructions sheet. **Ontology validation is strict in this format and
violations reject the file** - and this is the *only* upload format where that
is true (see Phase 6).

Because Phase 5's output is a review artifact, populating the Ontology sheet
puts the allowed values in front of the curator at exactly the moment they are
checking the data. `schema` mode produces `schema/<TYPE>.ontology.json` in
precisely the shape `write_4sheet_xlsx(ontology=...)` expects.

The generated `build_<arm>.py` should pass `ontology=` when a
`schema/<TYPE>.ontology.json` exists in the project. Historically no caller ever
passed it, so the mechanism existed and nothing populated it.

**Action:**
1. Identify arm. If not supplied, list arms from `SAMPLE_TREE.md` and `AskUserQuestion`.
2. Read sample types and counts for the arm.
3. Read master to identify existing parent UIDs. Workbook precedent beats the schema (hard rule 4).
4. Gather field values. For a **published/submitted** study run the Published-paper harvest (SKILL.md): check the manuscript **Methods**, **Supplemental Methods**, and **Data Availability statement**, plus the **master NExtSEEK sheet** (`previous_metadata/*.xlsx`), for instrument, platform, protocol, and manifest details before deciding any value is missing. A value genuinely absent from all four is left blank and logged to `QUESTIONS_FOR_PI.md`, never placeholdered.
5. Generate `./scripts/build_<arm>.py`:
   - PEP 723 inline deps (openpyxl)
   - `sys.path.insert(0, "<PLUGIN_PATH>/scripts")`
   - `from _common import mint_uid, write_4sheet_xlsx, schema_column_order, placeholder`
   - Per-project constants come from `./scripts/_project_constants.py` (copy `<PLUGIN>/scripts/_project_constants.py.example`), never from `_common`
   - Mint UIDs `<TYPE>-YYMMDD<LAB>-N`
   - Write one 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type into `assay_sheets/4sheet_originals/`
6. Run the script. Report row counts.
7. Suggest the next arm, or `/curate-consolidate`.

**Edge cases:**
- Missing manifest data, **in-prep study**: use `placeholder("<what is missing>")`, never a blank.
- Missing manifest data, **published/submitted study**: run the Published-paper harvest first (SKILL.md). If still absent, leave blank and add a question to `QUESTIONS_FOR_PI.md` — no placeholder.
- Sample type new to the schema: write to `assay_sheets/pending_schema/`.
- Mid-arm scope ambiguity: stop, add to `QUESTIONS_FOR_PI.md`, propose to the user.

---

## Phase 6 — Consolidate

**Command:** `/curate-consolidate`

**Inputs:** `assay_sheets/4sheet_originals/*.xlsx`, optional `context/assay_ids_cache.json` + `context/assay_synonyms.json`

**Output:** `assay_sheets/Arm{X}-upload.xlsx`, flat format, one per arm. The
`-upload` suffix is what `/curate-retrieve` and `/curate-deposit` read, so the
sheet does not need renaming between here and Phase 11.

### Flat cannot carry controlled vocabulary

Verified against `context/NExtSEEK_API.yaml`:

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | "Ontology validation is not performed in rows mode" |
| flat xlsx (this phase's output) | **none** - the format has no Ontology sheet |
| 4-sheet xlsx (Phase 5's output) | "Validation is strict; violations reject the file" |

So this phase converts the format that **can** enforce vocabulary into the one
that cannot. That costs nothing while nothing populates the Ontology sheet; it
becomes a live loss the moment `schema` mode does.

**Adding an ontology column to a flat sheet does not work.** `InputRowModel`'s
complete field set is `UID, SampleType, json_metadata, assay_ids, project_id,
study_title, study_id, sop_id, assay_titles, original_row_index` - no ontology
field. The model is `additionalProperties: true` and unknown columns are
"ignored, with a warning", so the column would be **accepted and
silently discarded**. That is a worse failure than rejection.

**Decision: keep both formats and let the curator choose per upload.** 4-sheet
when vocabulary enforcement is wanted, flat for convenience and for multi-type
files. Multiple sample types in one file are **only allowed in flat format**
(`consolidate_to_flat.py:19-21`), which is why per-arm files are flat.

**Verify before relying on this.** The table above is read from
`context/NExtSEEK_API.yaml`, bundled **2026-05-27**.
Confirm with the NExtSEEK API owner that flat still lacks ontology support
before designing anything new around it.

**Action:**
1. Invoke `scripts/consolidate_to_flat.py --assay-sheets assay_sheets`.
2. Archive 4-sheet originals into `4sheet_originals/` if not already there.
3. Per arm, produce a flat xlsx with a `Samples` sheet (`uid, sampletype, name, parent, notes_summary, assay_titles, assay_ids, json_metadata`) and a `README` sheet.
4. Report per-arm row counts and assay-ID resolution coverage.

**Edge cases:**
- Cache or synonyms missing: leave `assay_ids` blank, suggest `/curate-resolve-assays`.
- Pending-schema sample types: write to `assay_sheets/pending_schema/Arm<X>.xlsx`.
- Re-run: prior consolidated outputs (`Arm{X}-upload.xlsx` and legacy `Arm{X}.xlsx`) in the target dir are deleted first, so a stale arm file cannot survive. A `-upload-new.xlsx` working copy is **never** deleted — it holds curator hand-edits and GEO/Zenodo backfill (hard rule 2). The deletion is scoped to the resolved project's assay-sheets dir and refuses to run inside the plugin checkout.

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

### `assay_synonyms.json` (formerly Phase 8)

Synonym curation is part of this phase, not a separate one - same command, same
invocation. It existed as its own number only because it produces a second
artifact, and artifacts are not phases.

After the cache is written: read `context/assay_ids_cache.json`, compare against
the `assay_titles` column in `assay_sheets/Arm*.xlsx`, propose mappings for
cited titles that did not resolve, and ask the user to confirm. Write
`context/assay_synonyms.json` with `_README` and `synonyms_by_cited_name` keys,
each entry annotated with a `_notes` block explaining the reasoning.

Assay IDs are **project-scoped**: the same title maps to different IDs across
projects. Re-run the fetch and re-review the synonyms whenever switching
projects.

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

## Phase 9b — QC (server-side validation)

**Command:** `/curate-qc`

**Inputs:** `assay_sheets/<name>.xlsx` (consolidated flat), `.env` credentials, project id

**Action:**
1. `scripts/nextseek_api.py validate --project-id N --checks structure,dag,name_check --dump-dir <scratch> <file>`
2. If invalid, parse the DUMP (the console truncates at 20 of potentially hundreds).
3. Group `VALIDATION_ATTRIBUTE_NAME` errors by sample type. Decide per field whether it is
   our error (invented / mis-cased / a typo copied from `sampletypes_db.json`) or a genuine
   schema gap.
4. Our error -> fix the build script. Genuine gap -> discuss with the user, then hand off to
   `/curate-sampletype apply <TYPE> --add <FIELD>`.
5. Re-run to confirm.

**Why it exists:** Phase 9's `/curate-qa` is entirely local. It cannot know which attribute
names the live server recognises, so it will happily pass a file the server rejects outright.
Run 9a for build correctness and 9b for server conformance; 9b is the last gate before upload.

**Edge cases:**
- `CONVERT failed: Missing required columns: ['assay_ids']` — the flat file needs `uid`,
  `sampletype`, `assay_ids`, `json_metadata`. Rebuild it.
- `Unknown columns (ignored): ['name','parent','notes_summary']` — expected. Those are the
  consolidator's denormalized review columns; the server ignores them.
- Bundled `sampletypes_db.json` contradicts the server in BOTH directions: it lists fields the
  server rejects, carries at least one typo (`QuanitifcationMethod`), and hides case
  distinctions the server enforces (`Bead_coating_vendor` on D.TITR vs `Bead_coating_Vendor`
  on D.FCRB). Probe the server; record findings in the project's
  `context/live_sampletype_attributes.json`.
- A sample-type patch is a GLOBAL write. Never do it without explicit per-type agreement.

---

## Phase 10 — Deposit

**Command:** `/curate-deposit <geo|zenodo|omero> [args]`

Routes by first arg:

### `/curate-deposit geo [--type bulk|spatial]`

- **The build is delegated to `report` mode.** Run `/curate-report GEO <input>`; Phase 10 keeps only the genuinely pipeline-specific parts — external upload and accession backfill. This route was a **dead end** before the delegation: nothing produced the input it named and no GEO template xlsx shipped with the plugin, so delegating to report mode was closer to a free fix than a rewrite, and it avoids maintaining two divergent GEO build paths — the exact divergence the toolkit spec warns about elsewhere. Ordering is deliberate: GEO deposit happens **before** NExtSEEK upload because accessions must be backfilled into the sheets first, which is why report mode's curated-sheet adapter reads `assay_sheets/Arm{X}-upload.xlsx` locally with no API call.
- Drives `scripts/upload_geo_ncftp.sh` for upload.
- After GEO acceptance (manual confirmation): `scripts/apply_geo_accessions.py` patches D.SEQ/A.GEX/A.SPTX with GSM and series URLs. Bulk and spatial are separate GEO submissions with separate series accessions, so the script takes a flag pair per submission. See `commands/curate-deposit.md` for the full invocation and roster format.

### `/curate-deposit zenodo [--record-id N]`

- Drives `scripts/stage_zenodo.py` to preview, then (after user confirms) re-runs it with `--write`. This **moves** curated non-image files into per-bucket folders `files/Figure {N}/Figure{N}_{SampleType}/`. The script creates no archives.
- **Manual step, unautomated:** the user creates one archive per bucket folder and drops the `.zip` files into `Zenodo_upload/`. No script in this plugin does the zipping.
- User uploads those zips to Zenodo manually via web UI.
- After upload: `scripts/apply_zenodo_links.py --write --record-id N` reads each zip's namelist from `Zenodo_upload/` (or `--zip-dir`) and patches `Link_PrimaryData` by filename.

### `/curate-deposit omero [--project-id N]`

- User uploads images manually via OMERO Insight.
- `scripts/omero_pull.py all --project N` → `omero_images.csv`.
- `scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData`.

**Edge cases:**
- GEO literal validation failures: re-prompt user with corrected literals
- ncftp timeout on big file: script already has retry loop
- OMERO upload partial: diff `omero_images.csv` against manifest, identify missing IDs
- Zenodo record not created yet: surface to user, suggest creating record first
- No `.zip` files in `Zenodo_upload/`: the manual archive step was skipped. `apply_zenodo_links.py` finds nothing to read and patches zero rows without erroring — check for archives before reporting the backfill as done

---

## Phase 11 — Retrieve

**Command:** `/curate-retrieve [--include-parents]`

**Inputs:** `assay_sheets/*-upload-new.xlsx` (preferred), else `*-upload.xlsx` — the latter is what `/curate-consolidate` now writes directly, so no rename step is needed.

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
1. Invoke `scripts/review_metadata_vs_uploads.py --metadata-xlsx <xlsx> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`.
2. Report three diffs:
   - which upload-sheet field values differ from the round-tripped values
   - which `RETRIEVE.TXT` UIDs are missing from the download
   - which downloaded rows were auto-pulled parents (expected) vs genuinely unexpected
3. `--retrieve` defaults to `<project-root>/RETRIEVE.TXT` when present, and is skipped with a printed note when absent.

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
