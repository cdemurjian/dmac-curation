# Ground-truth inventory — top-level `scripts/*.py`

Scope: every file directly in `scripts/` of the `dev-docs` worktree
(`/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`). 24 `.py`
files + `_project_constants.py.example` + `upload_geo_ncftp.sh`. Subpackages
(`assay_hygiene/`, `fdh/`, `report/`, `schema/`, `deposit/`) are OUT of scope.

Every claim below was read out of the file at the cited line. Worktree is clean
at `833e9be` (`git status --short` empty), so line numbers are the committed
state. `<PLUGIN>` = the plugin checkout root.

Reference-scan method: `grep -rIl <stem> commands skills scripts tests docs
README.md CHANGELOG.md templates`, then narrowed to `commands/ skills/ README.md`
to decide orphan status.

---

## Summary tables

### A. What each file is

| file | kind | entry point | wired to a command? |
|---|---|---|---|
| `_common.py` | library | none | `curate-build.md:30` (import target) |
| `_config.py` | library | none | indirect (imported by 9 scripts) |
| `_lockfile.py` | library | none | `curate-init.md:39,121` |
| `_project_constants.py.example` | template (not runnable) | none | no |
| `apply_geo_accessions.py` | CLI (argparse, flat) | `main()` :189 | `curate-deposit.md:23` |
| `apply_omero_ids.py` | CLI (argparse, flat) | `main()` :71 | `curate-deposit.md:54` |
| `apply_zenodo_links.py` | CLI (argparse, flat) | `main()` :77 | `curate-deposit.md:47` |
| `build_retrieve.py` | CLI (argparse, flat) | `main()` :77 | `curate-retrieve.md:15` |
| `build_sample_tree_html.py` | CLI (argparse, flat) | `main()` :366 | `curate-sample-tree.md:88` |
| `consolidate_to_flat.py` | CLI (argparse inline in `__main__`) | :392 | `curate-consolidate.md:14` |
| `detect_context.py` | library (no PEP 723, no CLI) | none | indirect via `nextseek_api detect-context` |
| `inspect_workbook.py` | CLI (argparse, flat) | `main()` :64 | `curate-inventory.md:16` |
| `measure_metadata_accuracy.py` | CLI (no argparse; zero-arg script) | `main()` :142 | **no** |
| `nextseek_api.py` | CLI (argparse, 6 subcommands) + client class | `main()` :775 | 8 command files |
| `omero_pull.py` | CLI (argparse, 3 subcommands) | `main()` :390 | `curate-deposit.md:53` |
| `qa_flat_sheets.py` | CLI (argparse inline in `__main__`) | :372 | `curate-qa.md:13` |
| `refresh_context.py` | CLI (argparse, flat) — plugin maintenance | `main()` :213 | **no** |
| `remeasure_post_stage0.py` | CLI (no argparse; zero-arg script) | `main()` :48 | **no** |
| `rename_files.py` | CLI (argparse, 5 subcommands) | `main()` :826 | **no** |
| `review_metadata_vs_uploads.py` | CLI (argparse, flat) | `main()` :255 | `curate-validate.md:20` |
| `sampletype_attr.py` | CLI (argparse, 5 subcommands) + client class | `main()` :463 | `curate-sampletype.md:61+`, `curate-qc.md:74` |
| `smb_pull.py` | CLI (argparse, flat) | `main()` :317 | **no** (only `SKILL.md:157` prose) |
| `stage_zenodo.py` | CLI (argparse, flat) | `main()` :86 | `curate-deposit.md:44` |
| `stamp_guard.py` | library (no `main`, no `__main__`) | none | `curate-build.md`, `curate-qa.md` (prose) |
| `status.py` | CLI (argparse, flat) | `main()` :219 | `curate-status.md:13` |
| `upload_geo_ncftp.sh` | bash CLI (positional job names) | :116 | `curate-deposit.md` |

### B. PEP 723 dependency blocks

| file | requires-python | dependencies |
|---|---|---|
| `_common.py:1-4` | `>=3.11` | `["openpyxl>=3.1"]` |
| `_config.py:1-4` | `>=3.11` | `[]` |
| `_lockfile.py:1-4` | `>=3.11` | `[]` |
| `_project_constants.py.example` | — | **no PEP 723 block at all** (line 1 is a docstring) |
| `apply_geo_accessions.py:2-5` | `>=3.10` | `["openpyxl>=3.1"]` |
| `apply_omero_ids.py:2-5` | `>=3.11` | `["openpyxl>=3.1"]` |
| `apply_zenodo_links.py:2-5` | `>=3.10` | `["openpyxl>=3.1"]` |
| `build_retrieve.py:1-4` | `>=3.11` | `["openpyxl>=3.1"]` |
| `build_sample_tree_html.py:2-5` | `>=3.11` | `["jinja2>=3.1"]` |
| `consolidate_to_flat.py:2-5` | `>=3.11` | `["openpyxl>=3.1"]` |
| `detect_context.py` | — | **no PEP 723 block** (line 1 is the docstring) — yet it `import openpyxl` at :13 |
| `inspect_workbook.py:1-4` | `>=3.11` | `["openpyxl>=3.1"]` |
| `measure_metadata_accuracy.py:1-4` | `>=3.11` | `["pandas>=2.0", "pyarrow>=14"]` |
| `nextseek_api.py:2-5` | `>=3.11` | `["requests>=2.31", "openpyxl>=3.1"]` |
| `omero_pull.py:2-5` | `>=3.11` | `[]` (stdlib `urllib`) |
| `qa_flat_sheets.py:2-5` | `>=3.11` | `["openpyxl>=3.1"]` |
| `refresh_context.py:1-4` | `>=3.11` | `[]` |
| `remeasure_post_stage0.py:1-4` | `>=3.11` | `["pandas>=2.0", "pyarrow>=14"]` |
| `rename_files.py:2-5` | `>=3.11` | `[]` |
| `review_metadata_vs_uploads.py:2-5` | `>=3.10` | `["openpyxl>=3.1"]` |
| `sampletype_attr.py:2-5` | `>=3.11` | `["requests>=2.31"]` |
| `smb_pull.py:2-5` | `>=3.11` | `["smbprotocol>=1.16", "python-dotenv>=1.0"]` (openpyxl imported lazily at :100, NOT declared) |
| `stage_zenodo.py:2-5` | `>=3.10` | `["openpyxl>=3.1"]` |
| `stamp_guard.py:1-4` | `>=3.11` | `["openpyxl>=3.1"]` |
| `status.py:1-4` | `>=3.11` | `[]` |

Version floors are inconsistent: five files pin `>=3.10` (the four "lifted from
lee/" scripts plus `review_metadata_vs_uploads.py`), the rest `>=3.11`.
`tests/test_dependency_pinning.py` only checks that `pyproject.toml`/`uv.lock`
name pandas, pyarrow, openpyxl, jinja2, requests — it does not check the inline
blocks.

### C. Write capability and its guard

| file | writes what | guard |
|---|---|---|
| `apply_geo_accessions.py` | in-place edits to `assay_sheets/*-upload-new.xlsx` | `--write` (default dry-run, :192); `.bak` copy before save (:119,144,180); refuses to save while unmapped rows exist (:118-123, :181-185) — **except `patch_agex`, which has no unmapped-row gate (:143-147)** |
| `apply_omero_ids.py` | in-place edit of one xlsx | `--write` (:75), `.bak` (:63) |
| `apply_zenodo_links.py` | in-place edits to every discovered upload sheet | `--write` (:81), `.bak` per sheet (:181) |
| `build_retrieve.py` | `RETRIEVE.TXT` (overwrite, :93) | none — always writes |
| `build_sample_tree_html.py` | `SAMPLE_TREE.html` (overwrite, :422) | none; validation runs first (:384-418) |
| `consolidate_to_flat.py` | **deletes** every underscore-free `.xlsx` in `assay_sheets/` (:471-473), **moves** the 4-sheet originals into `4sheet_originals/` (:498-499), writes `Arm*-upload.xlsx` + `*_review.xlsx` | **no dry-run flag at all**; only guards are `is_consolidated_output()` (:355-372, spares `-upload-new` and `~$`) and `_is_inside_plugin()` refusal (:375-387, :424-427) |
| `nextseek_api.py` | `context/assay_ids_cache.json` (:399), `previous_metadata/<export>.xlsx` (:699), `<dump-dir>/*.validate.json` (:656) | none needed for reads; the one server-mutating route (`patch_sample_type`, :158) is reachable only from `_cmd_sampletype_add_attribute_dead`, which is unreachable |
| `omero_pull.py` | `omero_images.csv` (:309-312) | none; all HTTP is GET |
| `refresh_context.py` | **inside the plugin checkout**: `context/<managed file>` + `context/PROVENANCE.json` (:185-193, :203) | `--write` (:220-221); default is `check()` (:223-224) |
| `remeasure_post_stage0.py` | `assay-hygiene/precedent-remeasured.csv` (:235-239) | none (docstring at :16 claims "no writes" — see flags) |
| `rename_files.py` | `apply` **renames/moves every non-skip file** (:749), `rmdir`s emptied subdirs (:763), `--delete-fig7-dupes` `shutil.rmtree`s whole trees (:775); `walk`/`checksums` rewrite `manifest.csv` | **no dry-run flag**; `apply` refuses only on missing md5 (:717-719) and target collisions (:727-729). `rollback` (:806) is the undo. |
| `sampletype_attr.py` | **production DB schema** via `/seek/attribute/save/` (:239) and `/seek/attribute/delete/` (:253) | `--apply` per subcommand (:501,507,514) + `--yes-production` when host ∈ `PRODUCTION_HOSTS` (:63, `_confirm_production` :290-318, called at :519 and again at :344) + `_validate()` re-implementing three Rails checks (:180-206) |
| `smb_pull.py` | local `.fastq.gz` under `GEO/bulk_rna/fastq` (:303) and `manifest.tsv` (:429) | `--write` (:324); aborts if plan has errors (:474-476); `pigz` presence checked first (:383-386). Note `write_manifest` runs **before** the `--write` check (:428-429), so a dry run does write the manifest. |
| `stage_zenodo.py` | **moves** curated files inside `files/` (:210) | `--write` (:89-92); collisions skipped, never overwritten (:155-157) |
| `status.py` | nothing | read-only |
| `upload_geo_ncftp.sh` | uploads to a remote FTP (:89-92) | none — no dry-run; runs on invocation, `.env` vars required (:30-33) |
| everything else | nothing | — |

Live-server reach: `nextseek_api.py` (GET + one dead PATCH + POST validate),
`sampletype_attr.py` (**writes production schema**), `omero_pull.py` (GET only,
plus POST login), `smb_pull.py` (SMB read), `upload_geo_ncftp.sh` (FTP write).
`tests/test_deposit_write_safety.py:14-21` enforces `--write` (and the absence of
`--dry-run`) on exactly five scripts: `stage_zenodo`, `apply_zenodo_links`,
`apply_geo_accessions`, `apply_omero_ids`, `smb_pull`. `consolidate_to_flat.py`
and `rename_files.py` are not in that list and have no such flag.

---

## Per-file detail

### `scripts/_common.py` — library
Shared helpers for generated `build_<arm>.py` scripts. Explicitly de-projected
(:8-11): "holds nothing project-specific". Exports `placeholder()` :36,
`mint_uid(sample_type, lab, date, n) -> "<TYPE>-YYMMDD<LAB>-N"` :44,
`load_manifest` :62, `load_omero` :68, `load_master_workbook` :74,
`master_lookup` :100, `master_vocab` :108, `save_uid_map`/`load_uid_map` :123/:130,
`sampletype_schema(sampletype, catalog=None)` :142 (falls back to
`plugin_context("sampletypes_db.json")` :151-154), `schema_column_order` :162,
`write_4sheet_xlsx(out_path, sampletype, samples, assay_titles, ontology=None,
catalog=None)` :188. Reads: the sample-type catalog JSON, arbitrary CSV/xlsx
paths the caller passes. Writes: only what the caller asks (`save_uid_map`,
`write_4sheet_xlsx`). Docstring at :207-209 records a real behavioural fact —
the Ontology sheet exists only in the 4-sheet format; the flat format silently
discards ontology columns.

### `scripts/_config.py` — library
The single project-config seam (toolkit spec P2). `plugin_root()` :35,
`plugin_context(name)` :40, `plugin_template(name)` :45,
`ProjectRootError` :50, `find_project_root(start=None)` :60 (nearest ancestor
with `.dmac-curation.json`; raises rather than adopting the plugin checkout,
:79-85), `parse_expected_counts("OOC=122,CEL=2")` :89, `ProjectConfig` dataclass
:113 with derived dirs `files`/`manuscript`/`previous_metadata`/`assay_sheets`/
`four_sheet_dir`/`context`/`lockfile` (:127-153), `_embedded_date` :167,
`_find_master_workbook` :192, `load_config` :252, `add_config_args(parser)` :281,
`config_from_args(args)` :295.
`add_config_args` registers exactly four flags in a "project config" group
(:283-292): `--project-root` (Path, default None → `find_project_root()`),
`--lab` (default None), `--pi` (default None), `--master-baseline` (Path,
default None), `--expected-counts` (str, default None). Every script that calls
`add_config_args` inherits all five.
`_find_master_workbook` (:192-249) is a **deliberate behaviour change** from the
three inline helpers it replaced: it picks the NEWEST `*All*.xlsx` (embedded
`YYMMDD` beats mtime; dated beats undated), excludes `~$` lock files, and prints
a stderr warning listing every candidate when more than one matches. The old
helpers took `sorted(glob(...))[0]` — alphabetically first, i.e. oldest.

### `scripts/_lockfile.py` — library
Reads/migrates/writes `.dmac-curation.json`. `SCHEMA_VERSION = 1` :28,
**`PLUGIN_VERSION = "0.4.0"` :29**, `LOCKFILE_NAME` :30. API: `path_for` :44,
`empty()` :48, `migrate_v0(raw)` :54 (v0 flat → v1 `modes.pipeline`, idempotent),
`_validate_v1` :97, `read(root)` :117 (migration is in memory; disk untouched;
returns `empty()` when absent; raises `LockfileError` on a newer
`schema_version`, :142-146), `write(root, data)` :152 (sorts modes; always
stamps `schema_version` and `plugin_version`), `mode(data, name)` :165,
`set_mode(root, name, values)` :179 (merges, never replaces).

### `scripts/_project_constants.py.example` — template, not code
Copy-to-project template for `SCIENTIST` :13, `PARENT_UID_REUSE` :17,
`MS_PROTOCOL` :22, `EXPECTED_COUNTS` :29, `ALWAYS_ROOT = {"CEL", "MDL"}` :34.
No PEP 723 block, no imports, never imported by anything in-tree.

### `scripts/apply_geo_accessions.py` — CLI
Purpose: patch GEO accession URLs into upload sheets after GSE/GSM assignment.
Flags (:190-227) — `add_config_args` five, plus `--write` (store_true, default
dry-run), `--gse-bulk GSE_ID` (**required**), `--gsm-csv CSV` (**required**,
Path), `--gse-sptx GSE_ID` (default None; when omitted the spatial patch is
skipped entirely, :262), `--sptx-gsm-csv CSV` (default None → falls back to
filtering `--gsm-csv` for `D\d{2}-\d{4}` tokens, :245-246), `--sheets-dir DIR`
(default `cfg.assay_sheets`).
Reads: the whitespace-delimited GSM roster (`parse_gsm_csv` :48, two columns,
`#` comments skipped, D-id extracted by `_(D\d+)$` or `\((D\d{2}-\d{4})\)`), and
three **hardcoded filenames** in the sheets dir: `D.SEQ-upload-new.xlsx`,
`A.GEX-upload-new.xlsx`, `A.SPTX-upload-new.xlsx` (:248-250).
Writes: those same files in place, with a `.bak`.
Hardcoded column INDEXES, not header lookups: `patch_dseq` reads
`File_PrimaryData` at col E (`row[4]`, :97), writes `Link_PrimaryData` at col F
(`row[5]`, :108) and `Accession` at col Q (`row[16]`, :111); `patch_agex` writes
col G (`row[6]`, :139); `patch_asptx` reads `Name` at col J (`row[9]`, :163).
A sheet whose column order differs is silently corrupted.
`uv run --script <PLUGIN>/scripts/apply_geo_accessions.py --gse-bulk GSE000001 --gsm-csv bulk.csv [--write]`

### `scripts/apply_omero_ids.py` — CLI
Purpose: write OMERO image URLs into `Link_PrimaryData` by filename match.
Args (:72-77): positional `xlsx` (Path), `--omero-csv` (Path, default
`omero_images.csv`), `--write` (default dry-run).
Reads `omero_images.csv` keyed on `filename` (:23-28); requires both
`File_PrimaryData` and `Link_PrimaryData` headers on the `Samples` sheet
(:38-43) — exits 2 otherwise. Prefers `web_url`, falls back to `show_url` (:54).
Idempotent. Does NOT use `_config` — the xlsx path is positional and
cwd-relative.
`uv run --script <PLUGIN>/scripts/apply_omero_ids.py assay_sheets/D.IMG-upload-new.xlsx --omero-csv omero_images.csv [--write]`

### `scripts/apply_zenodo_links.py` — CLI
Purpose: walk each `.zip` in `Zenodo_upload/`, map its member filenames to
(sheet, UID) via the master workbook, patch `Link_PrimaryData`.
Flags (:78-101): `add_config_args` five, `--write`, `--record-id` (**required**),
`--zip-dir` (default `<project>/Zenodo_upload`, :111), `--metadata-xlsx`
(default `cfg.master_workbook`, :112).
URL template is built at :109:
`https://zenodo.org/records/{record}/files/{zipname}?download=1&preview=1`.
`discover_sheet_map` :64 maps sample type → sheet, preferring `-upload-new` over
`-upload`. Adds a `Link_PrimaryData` column when the sheet lacks one (:163-166).
Dead code: the module constant `SHEET_FOR_TYPE: dict[str, Path] = {}` (:36),
carrying a `TODO(v0.2)`, is never read anywhere in the file.
`uv run --script <PLUGIN>/scripts/apply_zenodo_links.py --record-id 12345678 [--write]`

### `scripts/build_retrieve.py` — CLI
Purpose: emit newline-separated UIDs for `chat_nextseek` from the upload sheets.
Flags (:78-84): `--assay-sheets` (str, default `"assay_sheets"`), `--output`
(str, default `"RETRIEVE.TXT"`), `--include-parents` (store_true).
`PARENT_TYPES = {"MUS","TIS","DNA","RNA","PAT","PAV","CHM","CEL"}` :22 are
excluded by default. Prefers `*-upload-new.xlsx` over `*-upload.xlsx` (:32-39),
skips `~` lock files, requires a `Samples` sheet and a case-insensitive `uid`
header (:44-56). Writes `RETRIEVE.TXT` unconditionally (:93) — no `--write`.
This is the ONE pipeline script that deliberately does not use `_config`: paths
resolve straight off cwd (`tests/test_path_anchoring.py:448` calls it and
`fdh_api.py` "the models Task 8 refactors toward").
`uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]`

### `scripts/build_sample_tree_html.py` — CLI
Purpose: render `sample_tree.json` → interactive `SAMPLE_TREE.html` via the
bundled Jinja2 template.
Flags (:368-374): `--input` (Path, default `sample_tree.json`), `--output`
(Path, default `SAMPLE_TREE.html`), `--title`, `--subtitle`, `--footer` (all
default None → taken from the JSON, then a computed default at :392-398),
`--strict` (exit 1 if any clade warning was raised, :431-432).
Reads plugin-owned, read-only: `context/assays_db.json` (:72),
`context/neo4j_assay-sample-conn.json` (:73), `templates/SAMPLE_TREE.html.j2`
(:74, :406). Validates the JSON schema (:336-363), checks every edge against the
Neo4j connection graph (`validate_edges` :106 — catches an invented assay name
and a `proposed_new` flag on a pair the schema already licenses), derives missing
clades, and refuses to write if any node still lacks a clade (:416-418). Escapes
`</` in the embedded JSON (:402) and aborts if `{{` survives the render (:409).
`uv run --script <PLUGIN>/scripts/build_sample_tree_html.py [--input sample_tree.json] [--output SAMPLE_TREE.html] [--strict]`

### `scripts/consolidate_to_flat.py` — CLI, DESTRUCTIVE, no dry run
Purpose: collapse the per-sample-type 4-sheet xlsx files into per-arm
flat-format upload files plus a human-readable review twin.
Flags (:394-408): `add_config_args` five, `--assay-sheets DIR` (default
`cfg.assay_sheets`), `--all-in-one NAME` (default None; writes exactly
`NAME.xlsx` instead of grouping by the `Arm` prefix, :490).
Reads: `4sheet_originals/` if it holds any underscore-bearing `.xlsx`, else the
`assay_sheets/` root (:446-451); `context/assay_ids_cache.json` and
`context/assay_synonyms.json` from the PROJECT context dir (:98-133).
Writes: `<arm>-upload.xlsx` (:349-350) and `<arm>_review.xlsx` (:253-254).
Deletes/moves: `os.remove` on every `is_consolidated_output` file in `src`
(:471-473) then `shutil.move` of each source into `4sheet_originals/`
(:498-499). The only protections are the `is_consolidated_output` carve-outs for
`-upload-new` / `_` / `~` (:355-372) and the up-front
`_is_inside_plugin(src)` refusal (:424-427).
Resolution order for assay ids: direct cache hit → synonym → blank (:136-151);
coverage is reported at :536-549.
`uv run --script <PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`

### `scripts/detect_context.py` — library, no PEP 723
Network-free logic for `/curate-init` auto-detection, deliberately split out so
it is unit-testable offline (:1-5). `UID_RE` :15, `tokenize` :19 (lowercase
alphanumeric tokens of length ≥3), `Evidence` dataclass :24,
`gather_evidence(project_root)` :35 (path parts + `manuscript/` filenames +
`previous_metadata/*.xlsx` stems), `rank_projects` :60 (token overlap with the
project title), `LabInfo` :71, `extract_labs(xlsx_bytes)` :80 (aggregates UIDs
per lab across every sheet of a project export), `rank_labs` :116 (author-surname
match wins, then count, then latest date), `guess_pi` :126.
Imported only by `nextseek_api.py:723` and `tests/test_detect_context.py`.
It has **no `# /// script` block** yet imports `openpyxl` at :13, so
`uv run --script scripts/detect_context.py` would resolve no dependencies — but
nothing runs it directly, so this is latent, not live.

### `scripts/inspect_workbook.py` — CLI
Purpose: dump sheet names, dimensions, headers and sample rows of any `.xlsx`.
Args (:66-68): positional `path` (Path), `--sheet` (default None → all sheets),
`--sample N` (int, default `0` = headers only).
Read-only. Counts rows manually because `max_row`/`max_col` are unreliable in
read-only mode (:32-35). Exit 2 on missing/unopenable file, 1 if a named sheet
was not found (:59).
`uv run --script <PLUGIN>/scripts/inspect_workbook.py previous_metadata/foo.xlsx --sheet Samples --sample 5`

### `scripts/measure_metadata_accuracy.py` — one-shot measurement, ORPHAN
Purpose: measure how often a sample's `json_metadata` predicts the assay a
curator independently assigned, to justify (or kill) metadata-based propagation
where precedent is silent (:5-38).
No argparse. Hardcoded input `EXTRACT = Path("assay-hygiene/extract")` :51 —
resolved off cwd — reading `edges.parquet` and `samples.parquet` (:143-144).
Writes nothing; prints a per-field table and a three-tier cascade.
Method: learns `value -> most-common internal_assay_id` from a train split
(`MIN_SUPPORT = 3` :64), predicts on held-out rows, splits **by child sample**
via `sample_id % 2 == 0` (:162-163). Field list and order come from
`assay_hygiene._schema` (`CLAIM_FIELDS`, `STRONG_FIELDS`, `normalise_value`) —
the comment at :52-63 records that a local copy of both previously caused the
script to disagree with the figures it is cited for.
Referenced only from comments in `scripts/assay_hygiene/run_evidence.py:579,587`
and from `docs/superpowers/specs/2026-08-14-...`. No command file runs it.
`uv run --script <PLUGIN>/scripts/measure_metadata_accuracy.py` (must be run from
a dir containing `assay-hygiene/extract/`)

### `scripts/nextseek_api.py` — CLI, 6 subcommands + reusable client
`NExtSEEKClient` :66 — auth is HTTP Basic (username+password wins) or
`Token` header (:83-97). `DEFAULT_BASE_URL = "https://nextseek.mit.edu"` :53;
all paths are prefixed `/nextseek_api` (:102). `NExtSEEKError` :56 carries
status + body.
Client methods: `export_project(project_id, output_format="xlsx")` :114 (timeout
raised to ≥300 s, returns raw bytes + server filename),
`get_project` :135, `list_projects` :139, `get_sample_type` :154,
`patch_sample_type` :158 (**server treats `sample_attributes` as the complete
list — omitting one drops it; sample types are GLOBAL**),
`_prime_csrf` :188, `validate_batch_upload(file, project_id, checks)` :204,
`list_assays_paginated(page_size=100)` :244 (terminates only on
`links.next` being falsy, :274-278), `fetch_assay_id_map(project_id)` :283
(lowest id wins on a duplicate title; extras recorded under `__duplicates__`).
Credential loading: `_load_dotenv()` :334 reads `cwd/.env` then `<plugin>/.env`,
`setdefault` only. Env names `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD` /
`NEXTSEEK_TOKEN`.

Subcommands (parser at :775-896):
- **`fetch-assays`** :781 — `--project-id` (required), `--username`,
  `--password`, `--token`, `--base-url` (default `DEFAULT_BASE_URL`),
  `--output` (Path, default `<project>/context/assay_ids_cache.json`, :388),
  plus `add_config_args`. Writes that JSON with `project_id`, `base_url`,
  `fetched_at_utc`, `assay_id_by_title`, optional `duplicate_titles` (:390-399).
- **`pull-db`** :804 — `--project-id` (required), `--output-format`
  (`xlsx`|`json`, default `xlsx`), `--dest` (default
  `<project>/previous_metadata/`, :681), `--filename` (default: server-provided),
  creds, `--base-url`, `add_config_args`. Writes the export file (:698-700) and
  prints sheet/row counts for xlsx (:702-711).
- **`detect-context`** :826 — `--project-id` (force a project instead of
  auto-ranking), creds, `--base-url`, `add_config_args`. NOTE at :832-836: `--pi`
  is deliberately NOT declared here because `add_config_args` already provides
  it. **Side effect: it downloads the project export into
  `previous_metadata/` (:750-753)** even though it is presented as a suggestion
  command. Prints a JSON blob (:758-771).
- **`validate`** :845 — `--project-id` (required), positional `files` (1+),
  `--checks` (default `"structure"`; subset of `structure,name_check,dag`),
  `--dump-dir` (default None), creds, `--base-url`, `add_config_args`. POSTs each
  file to `/batch-upload/validate/`; **no insert**. Exit 0 only if every file is
  valid (:665).
- **`sampletype-get`** :866 — positional `sampletype`, creds, `--base-url`.
  Read-only attribute listing.
- **`sampletype-add-attribute`** :876 — **RETIRED**. `cmd_sampletype_add_attribute`
  :454 prints an explanation and returns 2 unconditionally; the real
  implementation is `_cmd_sampletype_add_attribute_dead` :489, never wired to any
  parser. Root cause at :455-471: SEEK's `allow_new_attribute? = !samples?`
  returns 422, surfaced as a 502 by the proxy. Its flags (`--name` required,
  `--type` default `Text`, `--required`, `--debug`, `--apply`) are still declared
  (:880-888) and are all inert.
`uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id 10`
`uv run --script <PLUGIN>/scripts/nextseek_api.py pull-db --project-id 10`
`uv run --script <PLUGIN>/scripts/nextseek_api.py validate --project-id 10 assay_sheets/ArmA-upload.xlsx --checks structure,dag`

### `scripts/omero_pull.py` — CLI, 3 subcommands
Purpose: pull image ids from OMERO.web's REST API and reconcile against
`manifest.csv`. Stdlib-only HTTP via `urllib` (`OmeroClient` :83).
Global flag `--base` (default `https://omero.mit.edu`, :393).
Auth (`_add_auth` :396): `--username` (default `$OMERO_USER`; password from
`$OMERO_PASSWORD` else `getpass` prompt, :248-251), `--server-id` (int, default
None → auto if exactly one server), `--sessionid` (default `$OMERO_SESSIONID`),
`--csrftoken` (default `$OMERO_CSRFTOKEN`). `_client_from_args` :245 exits if
neither `--username` nor `--sessionid` is present.
- **`images`** :423 — `--project N` (repeatable), `--dataset N` (repeatable),
  `--out` (default `omero_images.csv`), `--with-filesets` (one extra request per
  image). Writes the CSV with columns listed at :65-75.
- **`diff`** :429 — `--manifest` (default `manifest.csv`), `--images` (default
  `omero_images.csv`). Reports missing (failed uploads), extra, and duplicate
  imports. Prints only.
- **`all`** :433 — `images` then `diff` (`cmd_all` :379 sets `args.images =
  args.out`). Carries `--manifest`, `--out`, `--with-filesets`, and a suppressed
  `--images`.
`uv run --script <PLUGIN>/scripts/omero_pull.py all --project 1252 --sessionid "$OMERO_SESSIONID" --manifest manifest.csv --out omero_images.csv`

### `scripts/qa_flat_sheets.py` — CLI
Purpose: local QA of a consolidated flat upload sheet — 7 checks, exit 1 on any
blocker.
Flags are declared INLINE rather than through `add_config_args`, deliberately, so
`/curate-qa`'s documented contract is verifiable by a source scan
(:375-380): `--project-root` (Path, default None), `--master-baseline` (Path,
default = newest `previous_metadata/*All*.xlsx`), `--expected-counts`
(`OOC=122,CEL=2`, default from the lockfile), `--upload` (Path, default: the
single underscore-free `*.xlsx` under `<project>/assay_sheets`, :420-430), plus a
deprecated positional alias `upload_pos` (:402-405; passing both exits 2).
Checks: UID uniqueness (:154-163); **UID already present in the master baseline**
(:165-170) — the stamp-collision net, a BLOCKER unless `QA_ALLOW_DB_UPDATES=1`
(:319-334); sampletype validity against `sampletypes_db.json` (project copy wins
over the bundled one, :83-98); `json_metadata` JSON parse (:177-185); parent
resolvability against intra-upload ∪ baseline UIDs (:230-246); required-field
coverage (informational, :201-209); name uniqueness within a sampletype
(:211-217); placeholder/sentinel sniff (`*** PLACEHOLDER` counted as expected,
`XXX/TODO/FIXME/???/TBD/UNCONFIRMED` surfaced as surprises, :48-55, :219-227).
Blocker keys listed at :335-339. Read-only.
`uv run --script <PLUGIN>/scripts/qa_flat_sheets.py --upload assay_sheets/ArmA-upload.xlsx [--master-baseline previous_metadata/X.xlsx] [--expected-counts OOC=122]`

### `scripts/refresh_context.py` — CLI, plugin maintenance, ORPHAN to commands
Purpose: refresh the plugin's bundled `context/` snapshots and record provenance.
The ONE script that legitimately writes inside the plugin checkout, and is
excluded from the P1 anchoring harness for that reason (:16-19; the exclusion is
`MAINTENANCE_SCRIPTS` in `tests/test_path_anchoring.py:133`).
Flags (:216-221): `--from-dir DIR` (default None), `--check` (store_true),
`--write` (store_true; default is dry-run). Dispatch at :223-225: `--check` OR a
missing `--from-dir` both fall through to `check()`.
`MANAGED_FILES` :40-46 — `sampletypes_db.json`, `assays_db.json`,
`projects_db.json`, `neo4j_schema.json`, `neo4j_assay-sample-conn.json`. Anything
else in `context/` is hand-maintained and untouched.
`check()` :126 returns 1 when stale; its named staleness signal is
`sample_property_count(neo4j_schema.json) < 50` (dev snapshot ≈23 properties,
live ≈85, :153-160). `refresh()` :164 copies changed files, writes a
`PROVENANCE.json` entry each (source repo/path, `git rev-parse HEAD` of the
source dir via `_git_sha` :117, vendored date, sha256), and prints the reminder
that `VINTAGE.json` must still be updated by hand (:206).
`uv run --script <PLUGIN>/scripts/refresh_context.py --check`
`uv run --script <PLUGIN>/scripts/refresh_context.py --from-dir <DIR> --write`

### `scripts/remeasure_post_stage0.py` — one-shot measurement, ORPHAN
Purpose: re-derive every A–F statistic against the post-stage-0 graph, because
the plan's headline figures (87.8% unambiguous, 97.2% disjoint, a 216,114-edge
backtest population) were measured before stage 0 added 90,534 edges (:5-14).
No argparse. `EXTRACT = Path("assay-hygiene/extract")` :41; reads
`edges.parquet`, `membership.parquet`, `assays.parquet` (:49-51). Imports
`assay_index`, `membership_index`, `mine_precedent` from
`assay_hygiene.precedent` (:37-39) rather than re-implementing them — the
comment at :29-35 records that its previous inline copies silently dropped rows.
Reports each contested figure at BOTH scopes rather than asserting one
(:130-169, :208-215).
`uv run --script <PLUGIN>/scripts/remeasure_post_stage0.py`

### `scripts/rename_files.py` — CLI, 5 subcommands, DESTRUCTIVE, ORPHAN
Purpose: walk a `files/Figure N/` tree, classify every file, propose canonical
names, apply the rename, verify, roll back. Stdlib only.
Every subcommand takes `--root` (Path, default `files`) and `--manifest` (Path,
default `manifest.csv`), plus `--figure-dirs` (default `"Figure 1..7"`, parsed by
`parse_figure_dirs` :54 — either an `A..B` range or a comma list) — note
`--figure-dirs` is declared on all five subcommands (:841,847,853,858,863) but
`verify` and `rollback` never use it (:873-876).
- **`walk`** :838 — parses the tree, writes `manifest.csv` (17 columns listed at
  :98-119), prints a summary plus unclassified-file and target-collision
  warnings (:630-663). No filesystem changes beyond the manifest.
- **`checksums`** :843 — extra `--workers` (int, default `8`). Computes MD5 for
  every non-skip row lacking one and rewrites the manifest in place.
- **`apply`** :849 — extra `--delete-fig7-dupes` (store_true). **Moves every
  non-skip file to its `target_relpath` (`src.rename(dst)` :749), `rmdir`s
  emptied subdirs (:755-768), and with the flag `shutil.rmtree`s
  `files/Figure 7/Figure {1..6}/` (:771-776).** Guards: refuses if any non-skip
  row lacks an md5 (:717-719), refuses on target collisions (:727-729), never
  overwrites an existing destination (:745-747). **There is no `--dry-run` /
  `--write`.**
- **`verify`** :855 — re-stats and reports missing destinations and size drift.
- **`rollback`** :860 — reverses an apply using `original_path` (:806-818).
Classification rules are IntravChip-specific by the file's own admission
(:33-36): `SUBSTITUTIONS` :66, `FIG5_CHAMBER_TO_CANONICAL` :87, the Figure 1
`intrav_sim_final.mph` pattern (:432-440, carrying a `TODO(v0.2)`), the Figure 2
excluded-movie rule (:201-206), the Figure 6 `ImgLib`/`STORMLib` layout (:446).
The promised `--config <yaml>` (:36) does not exist.
No command file, skill or README references this script — only
`tests/test_file_ops_cli.py` and historical plan/spec docs.
`uv run --script <PLUGIN>/scripts/rename_files.py walk --root files --manifest manifest.csv`
`uv run --script <PLUGIN>/scripts/rename_files.py checksums --manifest manifest.csv --workers 8`
`uv run --script <PLUGIN>/scripts/rename_files.py apply --manifest manifest.csv [--delete-fig7-dupes]`

### `scripts/review_metadata_vs_uploads.py` — CLI
Purpose: round-trip diff of a downloaded metadata workbook against the local
upload sheets, plus a RETRIEVE round-trip and a protocol census.
Flags (:256-275): `add_config_args` five, `--metadata-xlsx` (default
`cfg.master_workbook`), `--assay-sheets DIR` (default `cfg.assay_sheets`),
`--retrieve PATH` (default `<project>/RETRIEVE.TXT` when present, :331).
`discover_active_uploads` :89 maps `<stype>-upload*.xlsx` → sample type.
`COMPARE_COLS` :39 = `File_PrimaryData, Link_PrimaryData, Parent, Accession,
Checksum_PrimaryData`. `diff_retrieve` :61 classifies the download into missing /
auto-pulled parents (`AUTO_PULLED_PARENT_TYPES` :46) / unexpected extra.
`collect_protocols` :216 prints every distinct `Protocol` value with counts and
source sheets. Read-only; output is a single stdout report.
The docstring header records that PHASES.md named `RETRIEVE.TXT` as a Phase 12
input while the script had no flag to read it (:52-56, :328-330) — now fixed.
Live `TODO(v0.2)` at :84-86: no project-level `ACTIVE_UPLOADS` override, so a
sample type split across several upload sheets is handled only by the glob.
`uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata-xlsx previous_metadata/All.xlsx`

### `scripts/sampletype_attr.py` — CLI, 5 subcommands, WRITES PRODUCTION
Purpose: add/remove sample-type attributes by driving NExtSEEK's own native
editor (`GET /seek/attribute/save/` :64), because the REST PATCH route is blocked
by SEEK's `allow_new_attribute? = !samples?` (:8-19). Self-declared STOPGAP
(:29-33). Requires a superuser Django session (:110, :138-140).
Also documents that a change here is invisible to batch-upload validation until
the app workers restart, because `prefetch_sample_type_attributes` caches
attribute titles in a module-level dict with no invalidation (:35-39).
Global flags (:473-484): `--base-url` (default `$NEXTSEEK_BASE_URL` else
`https://nextseek.mit.edu`, :62), `--username` (default `$NEXTSEEK_USERNAME` else
legacy `$NEXTSEEK_USER`), `--password` (default `$NEXTSEEK_PASSWORD`),
`--yes-production`. `--yes-production` is **stripped from `argv` before parsing**
(:469-471) specifically so it works in any position; it is declared only so it
shows in `--help`.
- **`types`** :487 — no args. Scrapes the editor page's
  `var sample_attribute_types` (:150) and lists type id/title.
- **`list <sampletype>`** :489 — read-only via REST; prints pos/id/title/type/
  required/is_title plus the sample count (:327-340).
- **`add <sampletype>`** :493 — `--title` (**required**), `--type` (default
  `Text`), `--type-id` (overrides `--type`), `--pos` (int, default
  `max(existing pos)+1`, :228-230), `--required`, `--is-title`, `--apply`.
  Runs `_validate` :180 first (title uniqueness, accessor-name collision,
  exactly-one-title-attribute), prints the exact record, and verifies by
  re-reading after the save (:383-389).
- **`remove <sampletype>`** :504 — `--title` (**required**), `--apply`. Refuses
  to remove the title attribute (:404-406). Note at :253-258: delete does not
  call `updateSampleType`, so existing samples keep the orphaned key.
- **`selftest <sampletype>`** :510 — `--title` (default `ZZZ_Probe_Attr`),
  `--type` (default `Text`), `--apply`. Adds a probe attribute to prove the
  route works on a type that has samples.
Production guard: `_confirm_production` :290 raises `SystemExit` when `--apply`
targets a host in `PRODUCTION_HOSTS = ("nextseek.mit.edu",)` :63 without
`--yes-production`. It is called once centrally at :519 (covering every
subcommand) and redundantly again inside `cmd_add` :344. `cmd_remove` and
`cmd_selftest` are covered only by the central call.
`uv run --script <PLUGIN>/scripts/sampletype_attr.py list A.TITR`
`uv run --script <PLUGIN>/scripts/sampletype_attr.py add A.TITR --title Titer_Method --type Text --apply --yes-production`

### `scripts/smb_pull.py` — CLI
Purpose: stream files off an MIT SMB share through `pigz` into local `.gz`.
Credentials via `.env` (`load_dotenv` at :52-54, cwd first then plugin):
`MIT_USER`, `MIT_PASS`, `SMB_HOST` (default `bmc-pub14.mit.edu`, :58),
`SMB_SHARE` (**no default; exits 2 if unset**, :378-380). VPN required.
Flags (:322-358): `add_config_args` five, `--write` (default dry-run),
`--out-dir` (default `<project>/GEO/bulk_rna/fastq`, :367), `--manifest`
(default `<project>/GEO/bulk_rna/manifest.tsv`, :368), `--batch ID` (planning
only), `--resume`, `--from-manifest`, `--rows N-M`, `--rows-from FILE`.
Order of operations: credentials → share → `pigz` presence (only when `--write`,
:383-386) → plan (SMB round trips, or load from manifest) → **write the full
manifest before row filtering** (:425-429, a deliberate fix so a slice cannot
destroy the full plan) → summary → abort on `--write` if the plan holds errors
(:474-476) → pull.
Project-specific by its own admission: `PLATE_STRATEGY` :69 (five Engelward
batch ids), `load_manuscript_samples` :85 (requires columns `Sample Annotation`,
`Mouse Acc.# ID#`, `Folder Name`), and the hardcoded server path
`\\{HOST}\{SHARE}\users\noraho\...` :166. `--from-manifest` is the only fully
generic path (:31).
`openpyxl` is imported lazily at :100 with an explicit note that it is not in the
PEP 723 deps, and exits with guidance if absent (:99-106).
`uv run --script <PLUGIN>/scripts/smb_pull.py` (dry run)
`uv run --script <PLUGIN>/scripts/smb_pull.py --write --resume`
`uv run --script <PLUGIN>/scripts/smb_pull.py --write --from-manifest --rows 1-107`

### `scripts/stage_zenodo.py` — CLI
Purpose: move curated, non-image files into per-figure/per-sampletype staging
folders ready for zipping.
Flags (:87-98): `add_config_args` five, `--write` (default dry-run),
`--metadata-xlsx` (default `cfg.master_workbook`).
`IMAGE_TYPES = {"D.IMG","A.IMG","SLD","A.SPTX"}` :36 are excluded (they go to
OMERO/GEO). `files/Figures/` is skipped entirely (:127). Destination is
`files/Figure {N}/Figure{N}_{stype}/<name>` (:153). Already-staged files are
detected by regex and skipped (:81-84). Collisions are collected and NEVER
overwritten (:155-157).
`SHARED_FIGURE_DEFAULT: dict = {}` :40 is empty with a `TODO(v0.2)` — so any
curated file outside a `Figure N/` directory falls into `skipped_other` (:149-152)
and is silently not staged.
`uv run --script <PLUGIN>/scripts/stage_zenodo.py` then `--write`

### `scripts/stamp_guard.py` — library
Pre-mint collision guard for `/curate-build`. No `main`, no `__main__` block; it
is imported by generated `build_<arm>.py` scripts (usage at :30-33).
`StampGuardError` :51. Two gates:
`require_fresh_db_pull(master_path=None, project_root=".", max_age_hours=24.0)`
:68 — raises if no `previous_metadata/*.xlsx` exists (`find_db_pull` :56, `~$`
lock files ignored) or the newest one is older than 24 h, on the stated ground
that a stale pull cannot prove a stamp is free (:88-92).
`guard_stamp(master_path, sample_types, lab, date)` :134 — scans every sheet for
UIDs (`scan_used` :97), refuses if any target sample type already has rows under
`<date><lab>`, and suggests the nearest free stamp (`_suggest_free_stamp` :120,
walks forward up to 30 days).
`preflight(...)` :169 runs both and returns the pull path.
**Escape hatch: `STAMP_GUARD_OVERRIDE=1` in the environment downgrades the
collision error to a printed warning (:163-165).**

### `scripts/status.py` — CLI
Purpose: report toolkit state per MODE. Flags (:221-222): `--project-root`
(Path, default `find_project_root()`), `--json`. Read-only; always exits 0,
including when there is no project at all (:224-242).
Modes reported (`collect_status` :170-190): `pipeline`, `fdh`, `schema`,
`report`. **There is no `assay` mode** — see flags below.
`PIPELINE_ARTIFACTS` :25-38 covers phases 1,2,3,5,6,7,7,9,10,11,12,13 (4 and 8
are absent by design). Special cases: 4-sheet files counted by underscore
presence, flat files by its absence (`_count_xlsx` :55); `SAMPLE_TREE.html` is
flagged stale when older than `sample_tree.json` (:86-101); `RETRIEVE.TXT`
reports a UID count (:102-106). `_fdh_status` :138 reports only whether
`FDH_API`/`FDH_TOKEN` is set in the environment or named in `.env` — never the
value. `NEXT_COMMAND` :40-52 drives the single-line "Suggested next".
`uv run --script <PLUGIN>/scripts/status.py [--project-root DIR] [--json]`

### `scripts/upload_geo_ncftp.sh` — bash CLI
Overnight resilient GEO uploader. Positional job names, `JOBS=(${@:-bulk
spatial})` :116 — so a bare invocation runs BOTH. Requires `NCFTP_HOST`,
`NCFTP_USER`, `NCFTP_PASS`, `NCFTP_REMOTE_BASE` in `.env`/environment (`:?`
guards at :30-33), plus `ncftpput` and `stdbuf` on PATH (:35-36). Remote
sub-paths overridable via `NCFTP_REMOTE_BULK` (default `bulk_rna`) and
`NCFTP_REMOTE_SPATIAL` (default `spatial`) :113-114. Local sources are hardcoded:
`GEO/bulk_rna/GEO` :122 and `GEO/spatial` :126. Retries forever with a 30 s
cooldown (:104-106); heartbeat every 30 s into `GEO/upload_logs/<label>.log`
(:44-70). Deliberately does NOT `cd` to the script directory (:20-22) — a fix
for uploads that ran from inside the plugin checkout. **No dry-run: invoking it
starts the transfer.**
`bash <PLUGIN>/scripts/upload_geo_ncftp.sh [bulk|spatial]`

---

## Flags

### 1. Orphans — no command file, no skill, no other script references them
| script | only referenced by |
|---|---|
| `rename_files.py` | `tests/test_file_ops_cli.py` + 2026-05/07 plan+spec docs |
| `refresh_context.py` | `tests/test_refresh_context.py`, `tests/test_path_anchoring.py:133` + plan/spec docs. Intentional — it is plugin maintenance, not a curation step — but nothing tells a maintainer it exists. |
| `remeasure_post_stage0.py` | itself + `docs/superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md` |
| `measure_metadata_accuracy.py` | two comments in `scripts/assay_hygiene/run_evidence.py:579,587` + specs |
| `smb_pull.py` | one prose line, `skills/curation/SKILL.md:157`. No command file invokes it despite being a full pipeline-grade tool with `--write`. |
| `_project_constants.py.example` | `commands/curate-build.md` never mentions it; only `_common.py`'s docstring lineage and the file itself. |

`detect_context.py` and `stamp_guard.py` are libraries with a single caller each
(`nextseek_api.py:723`, generated `build_<arm>.py`) — not orphans, but invisible
to anyone reading the command files.

### 2. Docstrings that contradict behaviour
- **`qa_flat_sheets.py:6-32`** — the docstring is entirely IntravChip-specific:
  it names a default target `assay_sheets/IntravChip_upload.xlsx`, a baseline
  `previous_metadata/MetNet All 260527.xlsx`, "Marie fills these post-upload",
  and a CLI of `python3 scripts/qa_flat_sheets.py [path]`. The code has none of
  that: the default upload is the single underscore-free `*.xlsx` under
  `<project>/assay_sheets` (:420-430), the baseline comes from
  `cfg.master_workbook`, and the documented interface is `--upload`. The
  docstring is also what `--help` prints (`description=__doc__`, :374).
- **`consolidate_to_flat.py:6-54`** — describes a fixed CSBC job: "the 20
  per-sample-type 4-sheet xlsx files … into 5 per-arm flat-format xlsx files",
  then lists five named outputs with exact row counts (117/74/78/96/2). The code
  groups by whatever prefix precedes the first `_` in each input filename
  (:465-466) and knows nothing about arms A/B/E/F/H. Same `--help` exposure
  (:394).
- **`remeasure_post_stage0.py:16-17`** — "This is a measurement, not a stage:
  read-only over the extract, **no writes**, no decisions." It writes
  `assay-hygiene/precedent-remeasured.csv` at :235-239.
- **`rename_files.py:36`** — "or pass `--config <yaml>` (planned for v0.2)". No
  `--config` flag exists on any subcommand (:838-863).
- **`nextseek_api.py:23`** — CLI usage line says `python scripts/nextseek_api.py
  fetch-assays --project-id 10 → writes context/assay_ids_cache.json`, without
  saying that this is the PROJECT's `context/`, not the plugin's (:388).
- **`smb_pull.py:22`** and `SKILL.md:157` both correctly say dry-run is the
  default, but a dry run still writes `manifest.tsv` (:428-429). Neither says so.
- **`apply_zenodo_links.py:33-36`** — the `TODO(v0.2)` describes a `--sheet-map`
  flag as an alternative to auto-discovery. No such flag exists (:80-100).

### 3. Superseded / retired code still present
- `nextseek_api.py` **`sampletype-add-attribute`** — the subcommand is
  registered (:876-893) and prints a retirement notice, exit 2 (:454-486). Its
  original implementation survives as dead code at `_cmd_sampletype_add_attribute_dead`
  :489-578 and is not wired to any parser. `patch_sample_type` :158 is now
  reachable only from that dead function.
- `apply_zenodo_links.py:36` `SHEET_FOR_TYPE = {}` — declared, never read.
- `smb_pull.py:282` `total_in` — computed, never read; carries its own
  `TODO(v0.2): dead code, remove`.
- `consolidate_to_flat.py:355-372` `is_consolidated_output` also spares legacy
  bare-arm outputs (`ArmA.xlsx`) "from before the `-upload` suffix" — a
  compatibility shim for an output shape the script no longer produces.

### 4. Guard asymmetries worth documenting
- `consolidate_to_flat.py` and `rename_files.py apply` are the two most
  destructive top-level scripts and are the only two with **no dry-run at all**.
  `tests/test_deposit_write_safety.py:14-21` covers neither.
- `apply_geo_accessions.py`: `patch_dseq` and `patch_asptx` refuse to save while
  unmapped rows exist (:118-123, :181-185); `patch_agex` has no such gate
  (:143-147) and will save on `--write` regardless.
- `stamp_guard.py` can be fully disabled by an environment variable
  (`STAMP_GUARD_OVERRIDE=1`, :163) with no CLI trace.
- `qa_flat_sheets.py`'s DB-collision blocker can be waived by
  `QA_ALLOW_DB_UPDATES=1` (:319) — also environment-only.
- `nextseek_api.py detect-context` is presented as a read-only suggestion
  command but downloads a project export into `previous_metadata/` (:750-753).

### 5. The `assay` mode gap
`scripts/status.py` reports four modes — `pipeline`, `fdh`, `schema`, `report`
(:183-188) — and its `NEXT_COMMAND` table (:40-52) offers only pipeline
commands. The fifth mode, `assay` (8 `/curate-assay-*` commands, registered in
recent history), is invisible to it: no artifact row, no mode entry, no
suggestion. `commands/curate-status.md:5` says "all four dmac-curation modes" and
its mode table (:26-31) lists the same four. `/curate-assay-status` does not call
`status.py` at all — it runs inline `PYTHONPATH=scripts uv run python -c "…"`
against `scripts/assay_hygiene/` (`commands/curate-assay-status.md:8,27`).
