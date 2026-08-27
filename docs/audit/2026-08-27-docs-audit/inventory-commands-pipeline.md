# Ground-truth inventory — pipeline-mode slash commands

Scope: the 14 `commands/curate-*.md` files that constitute `pipeline` mode, as they exist
on branch `dev-docs` in worktree
`/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`.

Every assertion below was read out of the named file at the named line. Line numbers are
1-indexed and relative to the worktree root. Scripts were read, not executed.

Method note: all 24 top-level `scripts/*.py` are mode `-rw-r--r--` (non-executable) and
carry PEP 723 headers; the only executable is `scripts/upload_geo_ncftp.sh`. So the
correct invocation form for every `.py` is `uv run --script <path>`, and for the shell
script `bash <path>`.

---

## 0. Frontmatter, verbatim

Every one of the 14 files has exactly one frontmatter key, `description`. No
`argument-hint`, no `allowed-tools`, no `model`. Verbatim:

| file | `description:` |
|---|---|
| `commands/curate-init.md` | `Scaffold or extend a dmac-curation project (Phase 0)` |
| `commands/curate-inventory.md` | `Build FILE_INDEX.md from PI inputs (Phase 1)` |
| `commands/curate-sample-tree.md` | `Derive SAMPLE_TREE.md + interactive SAMPLE_TREE.html from manuscript + master + context (Phase 2)` |
| `commands/curate-questions.md` | `Maintain QUESTIONS_FOR_PI.md (Phase 3)` |
| `commands/curate-build.md` | `Build per-arm upload sheets (Phase 5)` |
| `commands/curate-consolidate.md` | `Collapse 4-sheet xlsx files into flat-format Arm{X}-upload.xlsx (Phase 6)` |
| `commands/curate-resolve-assays.md` | `Fetch project assays via NExtSEEK API and curate synonyms (Phase 7-8)` |
| `commands/curate-qa.md` | `QA the upload sheets — CLEAN / SOFT_FLAG / HARD_REJECT (Phase 9)` |
| `commands/curate-qc.md` | `Server-side validation of the upload sheets, and triage of any schema gaps (Phase 9b)` |
| `commands/curate-deposit.md` | `Stage external deposits and backfill URLs (Phase 10)` |
| `commands/curate-retrieve.md` | `Build RETRIEVE.TXT for chat_nextseek (Phase 11)` |
| `commands/curate-validate.md` | `Round-trip diff downloaded metadata vs uploads (Phase 12)` |
| `commands/curate-email.md` | `Draft EMAIL_TO_PI.md iteratively (Phase 13)` |
| `commands/curate-status.md` | `Show toolkit state per mode (any mode, any phase)` |

---

## 1. True phase numbering and ordering, as the files declare it

The authoritative statement is `skills/curation/PHASES.md:9-13`: *"14 commands drive 12
phases. Phase 9 is split into 9a (`/curate-qa`, local) and 9b (`/curate-qc`, server-side);
phases 4 and 8 were retired as numbers … the surviving numbers are deliberately **not**
renumbered."*

Numbers actually in use, in execution order:

| # | command | rationale for the number |
|---|---|---|
| 0 | `/curate-init` | `PHASES.md:35-39` — init step, explicitly *not* one of the 11 pipeline phases |
| 1 | `/curate-inventory` | frontmatter + `PHASES.md:20` |
| 2 | `/curate-sample-tree` | frontmatter + `PHASES.md:21` |
| 3 | `/curate-questions` | frontmatter + `PHASES.md:22` |
| — | *(4 retired)* | `PHASES.md:43-46` — was TaskList state only; no command, script or artifact. Number never reused. |
| 5 | `/curate-build` | frontmatter + `PHASES.md:23` |
| 6 | `/curate-consolidate` | frontmatter + `PHASES.md:24` |
| 7 | `/curate-resolve-assays` | `PHASES.md:25` |
| — | *(8 retired)* | `PHASES.md:47-50` — "artifacts are not phases"; folded into 7. Number never reused. |
| 9 (=9a) | `/curate-qa` | frontmatter + `PHASES.md:26` |
| 9b | `/curate-qc` | frontmatter + `PHASES.md:374` |
| 10 | `/curate-deposit` | frontmatter + `PHASES.md:27` |
| 11 | `/curate-retrieve` | frontmatter + `PHASES.md:28` |
| 12 | `/curate-validate` | frontmatter + `PHASES.md:29` |
| 13 | `/curate-email` | frontmatter + `PHASES.md:30` |
| any | `/curate-status` | `PHASES.md:499` ("Phase any") |

Machine-readable confirmation: `scripts/status.py:25-37` (`PIPELINE_ARTIFACTS`) enumerates
phases `1, 2, 3, 5, 6, 7, 7, 9, 10, 11, 12, 13` — no 0, no 4, no 8, **no 9b**. The
`NEXT_COMMAND` map at `scripts/status.py:39-52` uses the same key set.

Two arithmetic framings coexist and are both self-consistent:
- "12 phases" = `{1,2,3,5,6,7,9a,9b,10,11,12,13}` (`PHASES.md:9`, `SKILL.md:3`,
  `SKILL.md:42`, `templates/CLAUDE.md.j2:24`).
- "11 pipeline phases" = the same set counting 9 once (`PHASES.md:15`).

---

## 2. Per-command records

### `/curate-init` — Phase 0

- **File:** `commands/curate-init.md` (193 lines)
- **Arguments** (`curate-init.md:8-11`): `--lab <CODE>`, `--pi <NAME>`,
  `--mode <NAME>` (default `pipeline`; one of `pipeline`, `report`, `schema`).
  `--project-id` is referenced at `curate-init.md:172` but is **not** in the parse list at
  lines 8-11.
- **Mode validation** (`curate-init.md:18-21`): any `--mode` outside
  `{pipeline, schema, report}` must stop with an error. Note: `assay` is now a fifth mode
  (`skills/curation/SKILL.md:34`) and is **not** in this allow-list.
- **Prereqs** (`curate-init.md:43-44`): a copied `.env` for auto-detect; init still works
  without it.
- **Scripts invoked:**
  - `git -C <PLUGIN_PATH> rev-parse HEAD` (`curate-init.md:51`)
  - `uv run --with jinja2 python3 <<'PY'` — inline Jinja2 render (`curate-init.md:71-92`)
  - `uv run python3 - <<'PY'` importing `scripts/_lockfile.py` and calling
    `_lockfile.set_mode(cwd, MODE, values)` (`curate-init.md:125-139`; script side
    `scripts/_lockfile.py:179`)
  - `uv run --script <PLUGIN>/scripts/nextseek_api.py detect-context` (`curate-init.md:174`)
- **Inputs read:** `$PLUGIN_PATH` or grandparent of the command file (`curate-init.md:48-49`);
  `<PLUGIN_PATH>/context/VINTAGE.json` → `bundled_date` (`curate-init.md:54`);
  `$DMAC_ENV_FILE` (`curate-init.md:105-117`).
- **Artifacts written** (pipeline mode only, `curate-init.md:56-61`):
  - directories `files manuscript previous_metadata assay_sheets scripts` (`curate-init.md:64`)
  - `CLAUDE.md`, `.env.example`, `.gitignore`, `pyproject.toml` from
    `templates/{CLAUDE.md.j2, env.example.j2, gitignore.j2, pyproject.toml.j2}`
    (`curate-init.md:80-83`). All four templates exist.
  - `.env`, **copied** from `$DMAC_ENV_FILE`, `chmod 600` (`curate-init.md:105-110`)
  - `.dmac-curation.json` (merged, never replaced — `curate-init.md:38-39`)
- **Contract:** additive; presence-only check; no `--force` (`curate-init.md:25-36`,
  `curate-init.md:170-172`).
- **Lockfile shape asserted at `curate-init.md:144-161`.** Verified against
  `scripts/_lockfile.py:28-29`: `SCHEMA_VERSION = 1`, `PLUGIN_VERSION = "0.4.0"`.

### `/curate-inventory` — Phase 1

- **File:** `commands/curate-inventory.md` (27 lines)
- **Arguments:** none.
- **Prereqs** (`curate-inventory.md:9-10`): `.dmac-curation.json` exists; at least one of
  `files/`, `manuscript/`, `previous_metadata/` non-empty (warn but proceed).
- **Scripts invoked:** `uv run --script <PLUGIN>/scripts/inspect_workbook.py <path>` per
  xlsx in `previous_metadata/` (`curate-inventory.md:16`). Script args
  (`scripts/inspect_workbook.py:66-68`): positional `path`, `--sheet`, `--sample N`
  (default 0). The command passes only the positional — correct.
- **Other tooling named:** `tree -L 2 -h` or `ls -lh` (`curate-inventory.md:14`); Python
  `zipfile` docx text extraction (`curate-inventory.md:15`).
- **Inputs read:** `files/`, `manuscript/`, `previous_metadata/*.xlsx`, `email_convo.md`
  (`curate-inventory.md:14-18`).
- **Artifact written:** `./FILE_INDEX.md`, rendered from
  `<PLUGIN>/templates/FILE_INDEX.md.j2` (`curate-inventory.md:20`). Template exists.

### `/curate-sample-tree` — Phase 2

- **File:** `commands/curate-sample-tree.md` (145 lines)
- **Arguments:** none.
- **Prereqs** (`curate-sample-tree.md:21-23`): `./FILE_INDEX.md`, non-empty `./manuscript/`,
  `./previous_metadata/*.xlsx`.
- **Scripts invoked:**
  `uv run --script <PLUGIN>/scripts/build_sample_tree_html.py` (`curate-sample-tree.md:88`),
  bare. Script args (`scripts/build_sample_tree_html.py:368-373`): `--input`
  (default `sample_tree.json`), `--output` (default `SAMPLE_TREE.html`), `--title`,
  `--subtitle`, `--footer`, `--strict`. Bare invocation therefore resolves relative to cwd
  — correct only when run from the project root. `--strict` is never mentioned by the
  command even though the command demands every clade warning be resolved
  (`curate-sample-tree.md:89-90`).
- **Network calls the command instructs** (`curate-sample-tree.md:50-56`): `curl` against
  `ftp.pride.ebi.ac.uk` and `fairdomhub.org`.
- **Inputs read:** `<PLUGIN>/context/sampletypes_db.json` ("101 types") and
  `<PLUGIN>/context/assays_db.json` ("217 assays") (`curate-sample-tree.md:73`);
  `<PLUGIN>/context/neo4j_assay-sample-conn.json` (`curate-sample-tree.md:84`). All three
  files exist under `context/`.
- **Artifacts written** (three, `curate-sample-tree.md:9-13`):
  - `./SAMPLE_TREE.md` from `templates/SAMPLE_TREE.md.j2` (`curate-sample-tree.md:78`)
  - `./sample_tree.json`, schema in the module docstring of
    `scripts/build_sample_tree_html.py` (`curate-sample-tree.md:79-80`)
  - `./SAMPLE_TREE.html` (`curate-sample-tree.md:88`)
- **Hard rule:** never hand-edit `SAMPLE_TREE.html` (`curate-sample-tree.md:134-135`).
- **Note:** `curate-sample-tree.md:144` says the HTML loads Cytoscape and dagre from unpkg
  and so needs a network connection on first render. `templates/SAMPLE_TREE.html.j2` exists
  but the command never names it; the generator owns the HTML.

### `/curate-questions` — Phase 3

- **File:** `commands/curate-questions.md` (37 lines)
- **Arguments** (`curate-questions.md:7-10`): `add` (or no args), `list`, `resolve <id>`.
- **Prereqs:** none stated.
- **Scripts invoked:** none. Pure agent behavior + `AskUserQuestion`.
- **Artifact:** `./QUESTIONS_FOR_PI.md`, created from template if absent
  (`curate-questions.md:16`). `templates/QUESTIONS_FOR_PI.md.j2` exists; the command does
  not name it by path.
- **ID format:** `Q<N>`, numeric, monotonic (`curate-questions.md:35`). Resolved questions
  are never deleted (`curate-questions.md:37`).

### `/curate-build` — Phase 5

- **File:** `commands/curate-build.md` (67 lines)
- **Arguments** (`curate-build.md:7`): optional `<arm>` (letter or short name); otherwise
  list arms from `SAMPLE_TREE.md` and ask.
- **Prereqs** (`curate-build.md:11-20`): `./SAMPLE_TREE.md`; `./previous_metadata/*.xlsx`
  that is a **fresh DB pull**; `./CLAUDE.md`; `./.env` (warn only).
- **Scripts invoked:**
  - `uv run --script <PLUGIN>/scripts/nextseek_api.py pull-db --project-id N`
    (`curate-build.md:17`). Verified: `scripts/nextseek_api.py:804-823` registers `pull-db`
    with required `--project-id`, plus `--output-format {xlsx,json}` (default `xlsx`),
    `--dest` (default `<project-root>/previous_metadata/`), `--filename`, `--username`,
    `--password`, `--token`, `--base-url`, and `add_config_args`.
  - `uv run --script ./scripts/build_<arm>.py` — a script the command *generates*
    (`curate-build.md:27`, run at `curate-build.md:43`).
- **Generated script contract** (`curate-build.md:28-42`):
  - PEP 723 header with `openpyxl>=3.1`
  - `sys.path` insert of `<PLUGIN_PATH>/scripts`
  - `from _common import mint_uid, write_4sheet_xlsx, ...`. Verified present:
    `scripts/_common.py:44` (`mint_uid`), `scripts/_common.py:188` (`write_4sheet_xlsx`).
  - `from stamp_guard import preflight`, called as
    `preflight([<types>], LAB, DATE, project_root=".")`. Verified exactly against
    `scripts/stamp_guard.py:169-177`: `preflight(sample_types, lab, date, *, project_root=".",
    master_path=None, max_age_hours=24.0)`. The documented call site is correct.
  - constants `ROW_INFO` / `ARM_BY_COL` / `TIMEPOINT_BY_COL`
  - mint from N=1 per sample type; offset N across arms sharing a stamp
- **Artifacts written:** `./scripts/build_<arm>.py`, and 4-sheet xlsx
  (`Instructions / Samples / Assay / Ontology`) per sample type at
  `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx` (`curate-build.md:42`).
  Pending-schema types go to `assay_sheets/pending_schema/` (`curate-build.md:61`).
- **UID format:** `<TYPE>-YYMMDD<LAB>-N` (`curate-build.md:59`).
- **Escape hatch:** `STAMP_GUARD_OVERRIDE=1` (`curate-build.md:55`), verified at
  `scripts/stamp_guard.py:163`.
- **Ontology:** if `schema/<TYPE>.ontology.json` exists, pass to
  `write_4sheet_xlsx(ontology=...)` (`curate-build.md:65-67`).

### `/curate-consolidate` — Phase 6

- **File:** `commands/curate-consolidate.md` (29 lines)
- **Arguments:** none of its own; passes `[--all-in-one NAME]` through.
- **Prereqs** (`curate-consolidate.md:9-10`): `assay_sheets/4sheet_originals/*.xlsx` with at
  least one file; or, re-running, `assay_sheets/*.xlsx`.
- **Script invoked** (`curate-consolidate.md:14`), exact line:
  `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`
  Script args (`scripts/consolidate_to_flat.py:393-406`): `add_config_args(parser)`
  (i.e. `--project-root`, `--lab`, `--pi`, `--master-baseline`, `--expected-counts` per
  `scripts/_config.py:281-292`) plus `--assay-sheets` and `--all-in-one NAME`.
- **Artifacts written — the exact question:**
  - **`Arm{X}-upload.xlsx`**, per arm, in `assay_sheets/`. Ground truth:
    `scripts/consolidate_to_flat.py:490` — `out_name = f"{arm}.xlsx" if args.all_in_one else f"{arm}-upload.xlsx"`.
    The bare `Arm{X}.xlsx` name is produced **only** under `--all-in-one`, and then the
    name is the literal `NAME` the user supplied, not an arm letter.
  - **`{Arm}_review.xlsx`**, per arm, alongside it —
    `scripts/consolidate_to_flat.py:253` (`out = out_dir / f"{arm_name}_review.xlsx"`),
    called unconditionally at `scripts/consolidate_to_flat.py:492`. One sheet per sample
    type, every field its own column, never uploaded
    (`scripts/consolidate_to_flat.py:44-49`). **`curate-consolidate.md` never mentions this
    file.**
  - 4-sheet originals moved into `assay_sheets/4sheet_originals/`
    (`scripts/consolidate_to_flat.py:494-497`).
- **Flat sheet columns** (`scripts/consolidate_to_flat.py:270-271`):
  `uid, sampletype, name, parent, notes_summary, assay_titles, assay_ids, json_metadata`,
  on a sheet named `Samples`, plus a `README` sheet
  (`scripts/consolidate_to_flat.py:267`, `:314`).
- **assay_ids population** (`curate-consolidate.md:16`): reads
  `context/assay_ids_cache.json` key `assay_id_by_title`
  (`scripts/consolidate_to_flat.py:112`) and `context/assay_synonyms.json` key
  **`synonyms_by_cited_name`** (`scripts/consolidate_to_flat.py:125`).
- **Idempotence / safety** (`curate-consolidate.md:22-23`): re-runs delete every
  underscore-free `.xlsx` in the target dir, including legacy `Arm{X}.xlsx`, but never
  `-upload-new.xlsx` (`scripts/consolidate_to_flat.py:357-372`, guard at `:370`); the script
  additionally refuses to operate inside the plugin checkout
  (`scripts/consolidate_to_flat.py:424-427`).
- **Vocabulary loss** (`curate-consolidate.md:25-28`): flat format has no Ontology sheet, so
  controlled vocabulary is dropped. Corroborated at `PHASES.md:271-296`.

### `/curate-resolve-assays` — Phase 7 (frontmatter says "Phase 7-8")

- **File:** `commands/curate-resolve-assays.md` (41 lines)
- **Arguments** (`curate-resolve-assays.md:7`): `--project-id N` (required).
- **Prereqs** (`curate-resolve-assays.md:11-13`): `./.env` with `NEXTSEEK_USERNAME` +
  `NEXTSEEK_PASSWORD` (or `NEXTSEEK_TOKEN`); `assay_sheets/Arm*.xlsx`.
- **Script invoked** (`curate-resolve-assays.md:16`):
  `uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id <N>`.
  Script args (`scripts/nextseek_api.py:781-800`): required `--project-id`, plus
  `--username`, `--password`, `--token`, `--base-url`, `--output`, and `add_config_args`.
- **Artifacts written:**
  - `context/assay_ids_cache.json` (`curate-resolve-assays.md:17`). Written by
    `scripts/nextseek_api.py:398` to `cfg.context / "assay_ids_cache.json"`. Payload keys
    (`scripts/nextseek_api.py:390-397`): `project_id`, `base_url`, `fetched_at_utc`,
    `assay_id_by_title`, and optionally `duplicate_titles`.
  - `context/assay_synonyms.json` — written by the **agent**, not the script
    (`curate-resolve-assays.md:20-30`).
- **Lockfile update** (`curate-resolve-assays.md:31`): set `nextseek_project_id`. No script
  does this — `cmd_fetch_assays` (`scripts/nextseek_api.py:352-404`) never touches the
  lockfile. It is an unautomated agent step.
- **Judgment rule** (`curate-resolve-assays.md:19`, `:37`): one `AskUserQuestion` per
  mapping; no heuristic auto-mapping.

### `/curate-qa` — Phase 9 (9a)

- **File:** `commands/curate-qa.md` (51 lines)
- **Arguments:** none of its own.
- **Prereqs** (`curate-qa.md:9`): `assay_sheets/Arm*-upload.xlsx` (or an
  `-upload-new.xlsx` working copy).
- **Script invoked** (`curate-qa.md:13`), exact line:
  `uv run --script <PLUGIN>/scripts/qa_flat_sheets.py --upload assay_sheets/Arm{X}-upload.xlsx [--master-baseline previous_metadata/<master>.xlsx] [--expected-counts <sampletype>=<n>,...]`
  Script args (`scripts/qa_flat_sheets.py:381-403`): `--project-root`, `--master-baseline`,
  `--expected-counts`, `--upload`, and a deprecated positional alias `upload_pos`. All three
  documented flags exist.
- **`--upload` default** (`scripts/qa_flat_sheets.py:420-430`): the single `.xlsx` under
  `<project>/assay_sheets` whose stem has no underscore. `_review.xlsx` files are excluded
  by the underscore test; a multi-arm project therefore always errors out with
  "pass `--upload`", which is why the command shows it explicitly.
- **Artifact written:** none. QA is a console report (`PHASES.md:26`,
  `scripts/status.py:33`).
- **Output vocabulary:** the script emits `[BLOCKER]` / `[INFO]`
  (`scripts/qa_flat_sheets.py:342`, `:350`); the command translates those into
  CLEAN / SOFT_FLAG / HARD_REJECT (`curate-qa.md:18`). The three-way disposition exists
  only in the command, not in the script.
- **Escape hatch:** `QA_ALLOW_DB_UPDATES=1` (`curate-qa.md:41-44`), verified at
  `scripts/qa_flat_sheets.py:319-327` — it downgrades the DB-collision blocker to
  `INFO — updates acknowledged`.
- **Disposition rules:** `curate-qa.md:38-51`.

### `/curate-qc` — Phase 9b

- **File:** `commands/curate-qc.md` (206 lines) — the longest pipeline command.
- **Arguments:** none parsed; needs a project id from
  `modes.pipeline.nextseek_project_id` or by asking (`curate-qc.md:26`).
- **Prereqs** (`curate-qc.md:23-26`): `assay_sheets/<name>.xlsx` (a consolidated flat file);
  `.env` with `NEXTSEEK_USERNAME` + `NEXTSEEK_PASSWORD`; a project id.
- **Scripts invoked:**
  - `uv run --script <PLUGIN>/scripts/nextseek_api.py validate --project-id <N> --checks structure,dag,name_check --dump-dir <scratch> assay_sheets/<name>.xlsx`
    (`curate-qc.md:32-34`). Verified against `scripts/nextseek_api.py:845-863`: required
    `--project-id`, positional `files` (nargs="+"), `--checks` (default `structure`),
    `--dump-dir`, `--username`, `--password`, `--token`, `--base-url`, `add_config_args`.
  - `uv run --script <PLUGIN>/scripts/sampletype_attr.py list <TYPE>`
    (`curate-qc.md:74`, `:89`).
  - `uv run --script <PLUGIN>/scripts/nextseek_api.py sampletype-get A.TITR`
    (`curate-qc.md:88`). Verified at `scripts/nextseek_api.py:866-874`: positional
    `sampletype`, `--username`, `--password`, `--token`, `--base-url`. Note it does **not**
    take `add_config_args`.
- **Artifacts written:** the validator dump directory the caller names, and — instructed at
  `curate-qc.md:99-100` — the project's `context/live_sampletype_attributes.json`. Nothing
  else; QC has no artifact in `scripts/status.py`.
- **Hand-off:** schema patches go to `/curate-sampletype apply <TYPE> --add <FIELD>`
  (`curate-qc.md:69`), which owns the write.
- **Two long root-caused sections carried in this command file:**
  - `curate-qc.md:121-161` — after any schema change NExtSEEK workers must be restarted;
    `_SAMPLE_TYPE_ATTRIBUTES_CACHE` has no TTL or write invalidation. Cites NExtSEEK code
    (`nextseek_api/batch_upload/prefetch.py`, `validation.py:179`, `orchestrator.py:584`),
    not this repo.
  - `curate-qc.md:163-206` — why `PATCH /nextseek_api/sample_types/{id}/` returns 502; SEEK's
    `allow_new_attribute?` refuses any type that already has samples. Confirms
    `nextseek_api.py sampletype-add-attribute` is retired — verified at
    `scripts/nextseek_api.py:876-878`, whose help string reads
    `"RETIRED - cannot work. Use scripts/sampletype_attr.py instead."`

### `/curate-deposit` — Phase 10

- **File:** `commands/curate-deposit.md` (61 lines)
- **Arguments** (`curate-deposit.md:7`): first arg routes to a sub-target — `geo`, `zenodo`,
  or `omero`.
- **Prereqs:** none stated as a section. Implied: `.env` for `NCFTP_*` (`curate-deposit.md:18`)
  and credentials generally (`curate-deposit.md:61`).

**`/curate-deposit geo [--type bulk|spatial]`** (`curate-deposit.md:13-40`)

1. Build is **delegated** to `/curate-report GEO <input>`, producing `report/GEO_filled.xlsx`
   and `report/GEO.completeness.md` (`curate-deposit.md:13`). Verified:
   `scripts/report/render.py:193` writes `out_dir / "GEO_filled.xlsx"`;
   `scripts/report/execute.py:225-226` writes `<root>/<OUTPUT_SUBDIR>/<TYPE>.completeness.md`.
   `scripts/deposit/geo_build_xlsx.py` exists but is deliberately *not* named here —
   asserted by `tests/test_deposit_delegates_geo.py:19-23`.
   Input is usually `assay_sheets/Arm{X}-upload.xlsx`; the report adapter matches any file
   starting with `Arm` whose stem has no underscore
   (`curate-deposit.md:15`; `scripts/report/adapters.py:203-204`) — so `ArmA-upload.xlsx`
   matches and `ArmA_review.xlsx` does not. Correct as documented.
2. Upload: `<PLUGIN>/scripts/upload_geo_ncftp.sh GEO/<subfolder>/` (`curate-deposit.md:18`).
   The script reads `.env` for `NCFTP_HOST`, `NCFTP_USER`, `NCFTP_PASS`,
   `NCFTP_REMOTE_BASE` (`scripts/upload_geo_ncftp.sh:25-34`) and optionally
   `NCFTP_REMOTE_BULK` / `NCFTP_REMOTE_SPATIAL` (`:110-114`).
3. Validate manually at submit.ncbi.nlm.nih.gov/geo/submission (`curate-deposit.md:19`).
4. Backfill (`curate-deposit.md:20-40`):
   `uv run --script <PLUGIN>/scripts/apply_geo_accessions.py --gse-bulk GSE###### --gsm-csv <roster> [--gse-sptx GSE###### --sptx-gsm-csv <roster>] [--write]`
   Verified (`scripts/apply_geo_accessions.py:190-226`): `add_config_args`, `--write`,
   required `--gse-bulk`, required `--gsm-csv`, optional `--gse-sptx`, `--sptx-gsm-csv`,
   `--sheets-dir` (default `<project>/assay_sheets/`). `--sheets-dir` is documented nowhere.
   Roster format documented at `curate-deposit.md:31-36` (whitespace-delimited, no header,
   GSM in col 1, title in col 2, D-token extracted from the title) matches the script
   docstring `scripts/apply_geo_accessions.py:11-24`.
   Patches: D.SEQ `Accession` + per-sample GSM `Link_PrimaryData`; A.GEX series-level
   `Link_PrimaryData`; A.SPTX per-sample GSM (`curate-deposit.md:38`;
   `scripts/apply_geo_accessions.py:13-16`). `.bak` written alongside each patched sheet.
   D.SEQ is all-or-nothing (`curate-deposit.md:40`).

**`/curate-deposit zenodo [--record-id N] [--from-figures]`** (`curate-deposit.md:42-47`)

1. Stage: `<PLUGIN>/scripts/stage_zenodo.py`, dry-run then `--write`
   (`curate-deposit.md:44`). Script args (`scripts/stage_zenodo.py:88-98`):
   `add_config_args`, `--write`, `--metadata-xlsx`. **Moves** files into
   `files/Figure {N}/Figure{N}_{SampleType}/` (`scripts/stage_zenodo.py:153`,
   `:207-211`). Creates no archives (`curate-deposit.md:44`).
2. Archive: **manual**, no script (`curate-deposit.md:45`). Zips go into `Zenodo_upload/`.
3. User uploads manually, reports back the record ID (`curate-deposit.md:46`).
4. Backfill: `<PLUGIN>/scripts/apply_zenodo_links.py --write --record-id <N>`
   (`curate-deposit.md:47`). Script args (`scripts/apply_zenodo_links.py:79-99`):
   `add_config_args`, `--write`, required `--record-id`, `--zip-dir`
   (default `<project>/Zenodo_upload/`, `scripts/apply_zenodo_links.py:111`),
   `--metadata-xlsx` (undocumented by the command). Joins each zip's namelist to
   upload-sheet rows by filename (`scripts/apply_zenodo_links.py:127-132`).
   Preference order for upload sheets: `-upload-new` beats `-upload`
   (`scripts/apply_zenodo_links.py:68-73`).

**`/curate-deposit omero [--project-id N]`** (`curate-deposit.md:49-54`)

1. Identify files in `images_to_upload_to_omero/` (`curate-deposit.md:51`).
2. User uploads via Insight or web UI.
3. `<PLUGIN>/scripts/omero_pull.py all --project <N>` → `omero_images.csv`
   (`curate-deposit.md:53`). Verified: `scripts/omero_pull.py:433-438` registers the `all`
   subcommand with `--manifest` (default `manifest.csv`), `--out`
   (default `omero_images.csv`), `--with-filesets`; `--project` (int, `action="append"`) is
   added by the shared decorator at `scripts/omero_pull.py:418`.
4. `<PLUGIN>/scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData`
   (`curate-deposit.md:54`). Script args (`scripts/apply_omero_ids.py:72-75`): **positional
   `xlsx` (required)**, `--omero-csv` (default `omero_images.csv`), `--write`.

- **Behavioral rules** (`curate-deposit.md:56-61`): every deposit script defaults to dry-run
  and needs `--write`; OMERO requires MIT VPN; never log credentials.
- **Artifact tracked by `/curate-status`:** the directory `Zenodo_upload`
  (`scripts/status.py:34`). No script creates it — step 2 is manual.

### `/curate-retrieve` — Phase 11

- **File:** `commands/curate-retrieve.md` (23 lines)
- **Arguments** (`curate-retrieve.md:7`): optional `--include-parents`.
- **Prereqs** (`curate-retrieve.md:11`): `assay_sheets/*-upload-new.xlsx` or `-upload.xlsx`.
- **Script invoked** (`curate-retrieve.md:15`):
  `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]`.
  Script args (`scripts/build_retrieve.py:79-83`): `--assay-sheets`
  (default the **relative** string `assay_sheets`), `--output` (default the relative
  `RETRIEVE.TXT`), `--include-parents`.
- **Artifact written:** `RETRIEVE.TXT`, newline-separated, sorted, deduped
  (`scripts/build_retrieve.py:92-93`).
- **Default exclusions** (`curate-retrieve.md:21`): `MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL`.
  Verified verbatim at `scripts/build_retrieve.py:22` —
  `PARENT_TYPES = {"MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}`.
- **Sheet preference** (`curate-retrieve.md:23`): `-upload-new` over `-upload`. Verified at
  `scripts/build_retrieve.py:34-39`.
- **Reads only the `Samples` sheet and only a header cell equal to `uid`**
  (`scripts/build_retrieve.py:44-57`) — a sheet missing either is silently skipped.

### `/curate-validate` — Phase 12

- **File:** `commands/curate-validate.md` (44 lines)
- **Arguments** (`curate-validate.md:7`): `<metadata.xlsx>`.
- **Prereqs** (`curate-validate.md:11-13`): `assay_sheets/*-upload-new.xlsx`; `RETRIEVE.TXT`;
  the downloaded `*_AllMetadata.xlsx`.
- **Script invoked** (`curate-validate.md:20-23`):
  `uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata-xlsx <PATH> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`
  Verified (`scripts/review_metadata_vs_uploads.py:256-276`): `add_config_args`,
  `--metadata-xlsx` (default: newest `previous_metadata/*All*.xlsx`), `--assay-sheets`
  (default `<project-root>/assay_sheets`), `--retrieve` (default
  `<project-root>/RETRIEVE.TXT` when present). All three documented flags exist and the
  documented defaults match.
- **Artifact written:** none — console report in three sections (field drift, RETRIEVE round
  trip, counts) (`curate-validate.md:29-35`).
- **Interpretation rules:** distinguish formatting from semantic drift
  (`curate-validate.md:35-36`); auto-pulled parents are expected
  (`curate-validate.md:38-40`); never auto-fix (`curate-validate.md:44`).

### `/curate-email` — Phase 13

- **File:** `commands/curate-email.md` (28 lines)
- **Arguments:** none.
- **Prereqs** (`curate-email.md:9-10`): `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md`, and
  `CLAUDE.md` carrying lab + pi.
- **Scripts invoked:** none.
- **Artifact written:** `./EMAIL_TO_PI.md`, rendered from
  `<PLUGIN>/templates/EMAIL_TO_PI.md.j2` (`curate-email.md:15`). Template exists.
- **Style rules:** skeleton-first, iterate per section (`curate-email.md:16`); Name-pattern
  anchors, never row numbers (`curate-email.md:17`); strip em dashes
  (`curate-email.md:18`).

### `/curate-status` — any phase

- **File:** `commands/curate-status.md` (41 lines)
- **Arguments:** none of its own; passes `--project-root DIR` and `--json` through
  (`curate-status.md:17-18`).
- **Prereqs:** none. Explicitly works with no lockfile (`curate-status.md:21-22`).
- **Script invoked** (`curate-status.md:13`):
  `uv run --script <PLUGIN>/scripts/status.py`.
- **Artifact written:** none.
- **Reported state per mode** (`curate-status.md:26-33`): pipeline (per-phase artifacts +
  lab/pi/project id), fdh (whether `FDH_API` or `FDH_TOKEN` is configured and from where,
  never the value), schema (`schema/<TYPE>.review.md` in cwd), report
  (`report/<FORMAT>.mapping.json` in cwd). Phases 4 and 8 are explicitly not reported
  (`curate-status.md:33`).
- **Rules:** never print a credential value (`curate-status.md:38-39`); always end with a
  single-line "Suggested next:" (`curate-status.md:40`); surface a malformed-lockfile
  warning rather than swallowing it (`curate-status.md:41`).

---

## 3. Disagreements found

Ordered by blast radius. Each is a disagreement between a command file and either another
command file, its own body, or the script it calls.

### D1 — `/curate-resolve-assays` documents a synonyms key no consumer reads (BREAKS THE FEATURE)

`commands/curate-resolve-assays.md:20-29` instructs writing `context/assay_synonyms.json`
with a top-level key `"synonyms"`:

```json
{ "_README": [...], "synonyms": { "<cited title>": "<actual project assay title>" },
  "intentionally_unmapped": ["<title>"] }
```

The only consumer is `scripts/consolidate_to_flat.py:125`:

```python
synonyms = syn_doc.get("synonyms_by_cited_name") or {}
```

A synonyms file written exactly as the command specifies parses without error and yields
`{}` — every cited title that needed a synonym silently stays unresolved and its
`assay_ids` cell stays blank. The script's own error text (`consolidate_to_flat.py:548-549`)
tells the operator to add the entry "under synonyms_by_cited_name", and
`skills/curation/PHASES.md:344` also says `synonyms_by_cited_name`. The command file is the
outlier and it is the file the operator follows. `intentionally_unmapped` is read by
nothing in the repo.

### D2 — `/curate-deposit` omero backfill omits a required positional argument

`commands/curate-deposit.md:54` says `apply_omero_ids.py --write`. The script requires a
positional workbook: `scripts/apply_omero_ids.py:73` — `p.add_argument("xlsx", type=Path)`.
Following the doc produces an argparse error before anything runs. The contract test that
would have caught this only scans long flags (`tests/test_curate_commands_present.py:92-95`,
`_FLAG_RE`), so positional drift is invisible to the suite.

### D3 — `/curate-deposit` GEO upload passes a directory where the script takes a job label

`commands/curate-deposit.md:18` says invoke `upload_geo_ncftp.sh GEO/<subfolder>/`. The
script treats its positional arguments as job names:
`scripts/upload_geo_ncftp.sh:116` — `JOBS=(${@:-bulk spatial})`, dispatched through a `case`
at `:120-134` accepting only `bulk` and `spatial`, whose default branch prints
`unknown job: $j (use 'bulk' or 'spatial')` and exits 1
(`scripts/upload_geo_ncftp.sh:129-131`). The local source directories are hardcoded inside
the script (`GEO/bulk_rna/GEO` at `:122`, `GEO/spatial` at `:126`), not taken from the
command line. Passing `GEO/<subfolder>/` always fails.

### D4 — `/curate-consolidate` never mentions the review workbook it produces

`scripts/consolidate_to_flat.py:492` writes `{Arm}_review.xlsx` for every arm,
unconditionally, and the flat file's own README sheet points the curator at it
(`scripts/consolidate_to_flat.py:333-336`). `commands/curate-consolidate.md` names only
`Arm{X}-upload.xlsx` (`:15`). The review workbook is the file a human is supposed to read —
the flat file packs each sample into one unreadable `json_metadata` blob
(`scripts/consolidate_to_flat.py:44-49`) — so the command omits the artifact that makes the
phase reviewable. `templates/CLAUDE.md.j2:43-44` and `README.md:37` do document it.

### D5 — `/curate-resolve-assays` frontmatter asserts a retired phase number

Frontmatter says `(Phase 7-8)`. Its own body says "The user wants Phase 7"
(`curate-resolve-assays.md:5`) and "Synonym curation is part of this command, not a separate
phase" (`:39`). `skills/curation/PHASES.md:47-50` states phase 8 was retired and the number
is never reused; `scripts/status.py:31-32` maps both assay artifacts to phase `7`. The
frontmatter is the only surviving reference to a phase 8.

### D6 — Four of five `/curate-deposit` script invocations omit `uv run --script`

`curate-deposit.md:44`, `:47`, `:53`, `:54` write bare paths
(`<PLUGIN>/scripts/stage_zenodo.py`, `apply_zenodo_links.py`, `omero_pull.py`,
`apply_omero_ids.py`). All four files are mode `-rw-r--r--` and carry PEP 723 dependency
headers (`scripts/stage_zenodo.py:1-5`, `scripts/apply_zenodo_links.py:1-5`,
`scripts/apply_omero_ids.py:1-5`, `scripts/omero_pull.py:1-5`), so a bare invocation is
neither executable nor dependency-resolved. `curate-deposit.md:23` gets it right for
`apply_geo_accessions.py`; the others are inconsistent with it and with every other pipeline
command. `curate-deposit.md:18` likewise omits `bash` for the one file that *is* executable.

### D7 — `/curate-init`'s mode allow-list predates the fifth mode

`curate-init.md:11` and `:18-21` restrict `--mode` to `{pipeline, schema, report}` and
require an error on anything else. `skills/curation/SKILL.md:34` now documents a fifth mode,
`assay`, with eight `/curate-assay-*` commands. `curate-status.md:5` similarly says "all
four dmac-curation modes" and its table (`:26-32`) has no `assay` row;
`scripts/status.py:8` says "the four modes". Whether `assay` should be lockfile-registrable
through `/curate-init` is a design question, but the docs currently contradict the mode
roster.

### D8 — `pending_schema/` is promised by three commands and implemented by no script

`curate-build.md:61`, `curate-consolidate.md:24` and `curate-qa.md:34` all instruct moving
rows or files into `assay_sheets/pending_schema/`. `grep -rn pending_schema scripts/`
returns nothing. It is entirely agent behavior. Worse, `curate-consolidate.md:24` implies
the consolidate step performs the move, but `consolidate_to_flat.py` has no such logic — and
any pending-schema 4-sheet file left in `assay_sheets/` with an underscore in its name is
picked up as a normal source (`scripts/consolidate_to_flat.py:443-444`) and consolidated
into the upload sheet.

### D9 — `/curate-status` claims a phase list that omits 9b, which is correct but undocumented as a gap

`curate-status.md:28` says pipeline reports "phases 1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13" —
exactly `scripts/status.py:25-37`. But `/curate-qc` is phase 9b (its own frontmatter,
`PHASES.md:374`) and `PHASES.md:379` calls it "the last gate before upload". The status
collector cannot report whether the last gate ran, and `curate-status.md` does not say so.
Same for phase 0: `.dmac-curation.json` presence is checked
(`scripts/status.py:176-183`) but is not a numbered artifact row.

### D10 — Adjacent stale artifact names that contradict `/curate-consolidate`'s own frontmatter

Outside `commands/` but directly contradicting D-question above, and read by operators
alongside these commands:

- `templates/CLAUDE.md.j2:29` — `5. /curate-consolidate -> assay_sheets/Arm{X}.xlsx + Arm{X}_review.xlsx`.
  This template is rendered into **every scaffolded project's `CLAUDE.md`**
  (`curate-init.md:80`), so the wrong name is baked into each new project.
- `README.md:37`, `README.md:64`, `README.md:124` — all say `Arm{X}.xlsx` / `Arm*.xlsx`.

Ground truth remains `scripts/consolidate_to_flat.py:490`: per-arm output is
`Arm{X}-upload.xlsx`; the bare `Arm{X}.xlsx` form only ever appears as a *legacy* name the
script deletes on re-run (`scripts/consolidate_to_flat.py:357-359`) or as the literal
`--all-in-one NAME`.

### D11 — Minor imprecisions worth correcting, not blocking

- `curate-deposit.md:44` says stage_zenodo walks `files/Figure*/` + `files/Source Data/`.
  The script explicitly **skips** `files/Figures/` (`scripts/stage_zenodo.py:14`, `:127`),
  which the glob `Figure*` would include.
- `curate-init.md:64` creates `files manuscript previous_metadata assay_sheets scripts` but
  not `context/`, which phases 6 and 7 read and write (`scripts/_config.py:147-149`).
  `cmd_fetch_assays` mkdirs it on demand (`scripts/nextseek_api.py:389`), so nothing breaks,
  but the scaffold is incomplete relative to what the pipeline uses.
- `curate-init.md:172` names a `--project-id` flag absent from the argument list at
  `curate-init.md:8-11`.
- `curate-sample-tree.md:88` invokes `build_sample_tree_html.py` with no arguments; both its
  input and output default to cwd-relative paths
  (`scripts/build_sample_tree_html.py:368-369`), and the `--strict` flag
  (`scripts/build_sample_tree_html.py:373`) that would enforce the command's own
  "resolve every clade warning" rule (`curate-sample-tree.md:89-90`) is never mentioned.
- `curate-retrieve.md:15` likewise invokes `build_retrieve.py` bare; unlike most pipeline
  scripts it does **not** use `_config.add_config_args` / project-root discovery
  (`scripts/build_retrieve.py:77-84`), so it silently writes `RETRIEVE.TXT` into whatever
  cwd it was launched from.
- `curate-resolve-assays.md:31` instructs a lockfile write that no script performs.
- `templates/CURATION_PLAN.md.j2` exists but is referenced by no command and no skill —
  only by `tests/test_templates_render.py:40`. It is the orphan of retired phase 4.
- `README.md:7` says `**Status:** v0.3.0` while `scripts/_lockfile.py:29` sets
  `PLUGIN_VERSION = "0.4.0"`, the value `/curate-init` stamps into every lockfile
  (`curate-init.md:147`).
