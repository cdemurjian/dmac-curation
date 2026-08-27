# Ground-truth inventory — `scripts/` subpackages (`fdh/`, `report/`, `schema/`, `deposit/`)

Audit root: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs` (branch `dev-docs`).
All paths below are repo-relative to that root. Every claim was verified by reading the
named file at the named line. Line numbers are from the worktree state at audit time
(`git status --short` was clean).

Scope: 24 tracked files across four subpackages.

| subpackage | tracked files | total lines | has a CLI |
|---|---|---|---|
| `scripts/fdh/` | 5 (+1 `generated/REGISTRY.md`) | 2,419 py | 3 of 3 real modules |
| `scripts/report/` | 9 | 1,550 | 1 of 8 real modules |
| `scripts/schema/` | 7 | 1,096 | 0 of 6 real modules |
| `scripts/deposit/` | 2 | 198 | 1 of 1 |

---

## 1. `scripts/fdh/`

### 1.1 `scripts/fdh/__init__.py` — 0 bytes

Empty package marker. Asserted present by `tests/test_fdh_scaffold.py:22`.

### 1.2 `scripts/fdh/submit.py` — 1,953 lines, CLI, **writes to production FairDomHub**

PEP 723 header `scripts/fdh/submit.py:2-14`; deps `requests`, `pandas`, `openpyxl`,
`xlsxwriter`, `rapidfuzz`, `questionary`, `rich`, `python-dotenv`. Executable bit set
(`-rwxr-xr-x`), shebang at `:1`.

Invocation (the only supported form; the tool cannot be driven by an agent because every
step blocks on `questionary` prompts):

```
uv run --script <PLUGIN>/scripts/fdh/submit.py [--step {1,2,3,4,5,6} | --resume]
```

`parse_args` `scripts/fdh/submit.py:1780-1845`. `--step` and `--resume` are mutually
exclusive (`:1838`). **There are no other flags** — no `--base-url`, no `--dry-run`, no
`--write`, no `--study-id`.

**Base URL is hardcoded to production.** `BASE_URL = "https://fairdomhub.org/"` at
`scripts/fdh/submit.py:73`, used directly by every step function (e.g. `:1379`, `:1467`,
`:1571`, `:1697`). Unlike `fdh_api.py` there is no `FDH_BASE_URL` env override and no
flag. Every run of `submit.py` writes to fairdomhub.org.

`PROJECT_MAPPING` `scripts/fdh/submit.py:77-83` — the hardcoded project id → name table
offered in the Step 0 picker: `222` Impact, `221` SRP, `340` MetNet, `343` Endo-Griffith,
`441` CSBC. A manual numeric id can also be entered (`:1300-1317`).

Reads:
- `./.env` via `dotenv.load_dotenv()` `:1319`, key `FDH_API` = JSON `{username: token}` `:1320-1332`.
- `Assets/<workbook>.xlsx`, path prompted `:1354-1361`.
- `Assets/Protocols/` — `build_protocols_dataframe(base_dir="Assets/Protocols")` `:340`, called `:1418`.
- `Assets/Output/*.csv` on resume: `assays_from_study.csv` `:1741`, `sample_types_created.csv` `:1763`.
- `Assets/Output/session.json` on `--resume` `:1233-1256`.

Writes to local disk (`OUTPUT_DIR = "Assets/Output"` `:85`, `SESSION_FILE` `:86`):
`session.json` `:1227-1230`, `assays_from_study.csv` `:1393`, `protocols_preupload.csv`
`:1459`, `protocols_uploaded.csv` `:1468`, `sample_types_created.csv` `:1583`,
`samples_created.csv` `:1621`, `published_assets.csv` `:1715`.
**`session.json` contains the API token in cleartext** — `cfg` carries `api_token`
(`:1341`) and `_save_session` dumps `cfg` verbatim `:1225-1230`. `commands/fdh-upload.md:33-35`
documents this and tells the user to gitignore `Assets/Output/`.

Live-server writes, all against `https://fairdomhub.org`:

| step | verb + endpoint | code | guard |
|---|---|---|---|
| 1 Assays | `POST /assays` | `create_assay` `:281` via `bulk_create_assays_df` `:284` | `questionary.confirm("Create new assays?", default=False)` `:1379` |
| 2 Protocols | `POST /sops` (reserve blob) | `create_sop_with_placeholder` `:462` | `questionary.confirm("Upload protocols to FairDOMHub now?", default=True)` `:1462` |
| 2 Protocols | `PUT <upload_link>` (raw bytes) | `upload_sop_binary_with_retry` `:506` | same confirm; 5 retries, `backoff * 2**attempt` `:489-521` |
| 4 Sample types | `POST /sample_types` | `create_sample_type` `:756` | **none** — see below |
| 5 Samples | `POST /samples` | `create_sample` `:920` | `questionary.confirm("Create all samples now?", default=True)` `:1614` |
| 6 Publish | `PATCH /{type}/{id}` policy | `publish_resource` `:1142` via `_patch_jsonapi` `:186` | `questionary.confirm(..., default=False)` `:1676` |

**Step 4 has no confirmation prompt before creating SampleTypes on the live server.**
`step_sample_types` `:1549` calls `_reuse_existing_sample_types(cfg)` `:1570`; if that
returns `None` it calls `create_sample_types_from_workbook(...)` `:1571-1573` immediately.
The only prompt on that path is the *reuse* offer (`:1539-1547`), which is shown **only**
when `Assets/Output/sample_types_created.csv` already exists AND its `sheet_name` set is a
subset of the current workbook's sheets (`:1512-1531`). On a first run, or after the CSV
is deleted, one `POST /sample_types` fires per workbook sheet with no prompt.

**Step 3 rewrites the curator's workbook in place, destructively, with no backup.**
`step_metadata_rewrite` `:1474-1495` calls
`replace_anywhere_in_metadata(cfg["workbook"], uploaded_csv, cfg["workbook"])` `:1495` —
input path == output path. The implementation `:570-622` reads every sheet with
`pd.read_excel` and re-emits via `pd.ExcelWriter(engine="xlsxwriter")` `:617-620`. Cell
formatting, data validation, merged cells, formulas, sheet order metadata and any
non-tabular structure are not preserved by that round trip. Guarded only by
`questionary.confirm(..., default=True)` `:1487-1490`.

Step 6 detail: `_PUBLISHABLE_TYPES` `:1023-1024` = assays, sops, sample_types, samples,
data_files, models, presentations, publications. `collect_study_assets` `:1027` does three
discovery passes (links.related → inline relationships.data → recurse into assays for
nested data_files/samples). `publish_resource` `:1107-1146` PATCHes
`policy.access` to `view` or `download` plus a project `manage` permission entry. Samples
are published with a 5-worker `ThreadPoolExecutor` when there are >5 (`:1697-1704`).
The study itself is deliberately not published (`:1634-1635`, `:1015-1020`).

HTTP core: `_post_jsonapi` `:124`, `_patch_jsonapi` `:172`, `_page_through` `:210`,
header builders `:97/:106/:115`. `get_sample_attribute_type_ids` `:661` falls back to
hardcoded `Text=7`, `URI=14` `:685-686` when the API call fails. `column_is_all_links`
`:633` auto-types a column as URI when every non-empty cell matches
`_URL_RX = (https?://|ftp://|doi:)` `:630`.

### 1.3 `scripts/fdh/fdh_api.py` — 283 lines, library + **read-only** CLI

PEP 723 `:2-4`, dep `requests>=2.31`.

```
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py whoami
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py search QUERY [--type TYPE]
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py get RESOURCE_TYPE ID
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py list RESOURCE_TYPE ID RELATIONSHIP
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py download-blob URL --out PATH
```

Parser `:234-274`. Every subcommand also accepts `--token`, `--user`, `--base-url`
(shared `common` parent parser `:235-239`). Subcommand table: `whoami` `:247`, `search`
`:251`, `get` `:257`, `list` `:262`, `download-blob` `:269`.

The **CLI exposes only reads**. `FairDomHubClient.post/patch/delete` exist
(`:147`, `:150`, `:153`) but are wired to no subcommand — the comment at `:146` states
they are "used by generated scripts, never by this read CLI". This is the mechanism by
which every FDH write goes through a per-task generated script that must implement its own
`--write` gate.

Client surface (`class FairDomHubClient` `:46`): `get(type, rid)` `:101`,
`search(q, search_type=None)` `:104`, `page_through(url)` `:110` (cycle-guarded via a
`seen` set `:113-115`), `list_related(type, rid, relationship)` `:121`, `whoami()` `:135`
(`GET /people/current`), `download_blob(url, dest)` `:138` (sends `Accept: */*`, writes
bytes to disk, `mkdir -p` on the parent `:142-143`), `post` `:147`, `patch` `:150`,
`delete` `:153`. Transport `_request` `:69` retries `429/502/503` (`RETRY_STATUS` `:35`)
up to 5 times with `backoff ** attempt` and raises `FDHError` `:38` on any other `>=400`.
Timeout default 60s `:50`.

Credentials `_load_dotenv` `:159-169`: `os.environ.setdefault` from `cwd/.env` then
`<plugin>/.env`. `_resolve_token` `:172-195` precedence: `--token` → `FDH_TOKEN` →
`FDH_API` JSON, selected by `--user`, or auto-selected when the JSON holds exactly one
user; multiple users with no `--user` is a hard exit(2) `:194-195`.
Base URL: `--base-url` → `FDH_BASE_URL` → `DEFAULT_BASE_URL = "https://fairdomhub.org"`
(`:34`, `:200`).

### 1.4 `scripts/fdh/build_api_index.py` — 183 lines, CLI (no args)

PEP 723 `:2-4`, dep `pyyaml>=6.0`.

```
uv run --script <PLUGIN>/scripts/fdh/build_api_index.py
```

Reads `context/full-fdh-openapi-spec.yaml` (`SPEC` `:23`, 640,626 bytes on disk).
**Writes `context/fdh_api_index.json` (`OUT` `:24`, `:177`) — i.e. it writes *inside the
plugin checkout*.** It is the only script in these four subpackages that does so.
`tests/test_build_api_index.py:18-24` runs it for real via `subprocess`, and the
`plugin_sentinel` fixture in `tests/conftest.py` (content-hash based) tolerates that only
because the regeneration is byte-identical.

Emits one entry per (path, method) with keys
`path, method, operation_id, summary, category, primary_entities, intent_patterns,
llm_hint, yaml_lines` (`:160-170`). `yaml_lines` is a `[start, end]` back-pointer into the
spec computed by `scan` `:34` + `compute_ranges` `:55`, so an agent can `Read` a slice
instead of the whole file. `categorize` `:84-106` is method-aware for `content_blobs` so
blob writes/deletes are not mislabeled reads (`:87-95`). `llm_hint` `:125-136` prefixes
every DELETE with `"DESTRUCTIVE — irreversible on the live repo; dry-run and confirm
before writing."` (`:129`). No network access.

### 1.5 `scripts/fdh/generated/`

Contains exactly two files in this worktree: `__init__.py` (0 bytes) and `REGISTRY.md`
(488 bytes, 10 lines).

**`scripts/fdh/generated/*.py` is gitignored** — `.gitignore:154-156`:

```
# Generated FairDomHub task scripts. Written per-task against live project ids
# and frequently carry sample uids; several are destructive (delete_samples_*).
scripts/fdh/generated/*.py
```

Consequence: **the generated task scripts do not exist in this worktree.** `ls -A
scripts/fdh/generated/` returns `__init__.py` and `REGISTRY.md` only, and
`git status --short scripts/fdh/` is empty. The 7 generated scripts referred to in the
audit brief live only in the main working tree, which this audit is barred from reading, so
their individual purposes/endpoints/write-guards **were not verified here and are not
asserted below.** Anyone needing that inventory must run it against the main tree.

`REGISTRY.md` contract (`scripts/fdh/generated/REGISTRY.md:1-10`): a header telling Claude
to read it first, the statement that each script imports `FairDomHubClient` from
`../fdh_api.py` and that "Writes are dry-run by default; `--write` is required", then a
5-column table `Script | Purpose | Endpoints used | Writes? | Added`. The single data row is
`| _(none yet)_ | | | | |` (`:10`). `tests/test_fdh_reference_docs.py:16-20` only asserts
the header string `"| Script | Purpose |"` is present — nothing checks that the table
matches the directory contents, which is why the drift is invisible to the suite.

### 1.6 `fdh` subpackage — commands, true capability, doc deltas

Driven by two slash commands:
- `/fdh-upload` (`commands/fdh-upload.md`) → hands off `submit.py`; step 3 of that file
  gives the exact `uv run --script <PLUGIN>/scripts/fdh/submit.py` line (`:28`).
- `/fdh-api` (`commands/fdh-api.md`) → the reuse-or-generate loop over
  `generated/REGISTRY.md` → `context/fdh_api_index.json` → `full-fdh-openapi-spec.yaml`
  slices → a new script under `generated/`. Sub-routes `refresh-index` (`:31`) and `list`
  (`:32`).
Reference doc: `skills/curation/FDH.md`.

True capability: one interactive 6-step production uploader; one read-only API CLI with
five verbs; one deterministic index generator; and an empty generated-script library whose
contents are gitignored.

Doc deltas found:
- **`submit.py` is production-only.** No doc states this. `skills/curation/FDH.md:5` says
  "Host: `https://fairdomhub.org` (default). Override via `.env` `FDH_BASE_URL` or
  `--base-url`" in a section that covers *both* modules. That override exists in
  `fdh_api.py:200` and does **not** exist in `submit.py` (hardcoded `:73`, no such flag in
  `parse_args` `:1780-1845`). A reader will believe they can point the uploader at a
  staging host. They cannot.
- Step 4's missing confirmation and Step 3's in-place destructive workbook rewrite are
  undocumented in `commands/fdh-upload.md` and `skills/curation/FDH.md`.
- `REGISTRY.md` says `_(none yet)_` while generated scripts exist beside it in the main
  tree (pre-known; already fixed uncommitted there).

---

## 2. `scripts/report/`

Eight real modules plus an empty `__init__.py`. **Seven of the eight are library-only** —
`grep 'if __name__'` matches only `scrub_fixture.py:68`. `scrub_fixture.py` is the sole
module with `argparse`.

Import contract used by every caller (tests, and by extension the agent): put
`scripts/` on `sys.path`, then `from report import <module>` — see
`tests/test_report_execute.py:10-14`. `scripts/report/execute.py:33-36` does this itself.

### 2.1 `adapters.py` — 256 lines, library. **The complete adapter set.**

PEP 723 dep `openpyxl>=3.1` `:3`; `from openpyxl import load_workbook` `:30`.

Normalized shape: `NormalizedSample(sample_type, uid, metadata, parent)` `:35-40` and
`NormalizedInput(samples, source)` `:43-46`.

Exactly **five** adapters exist:

| function | line | input | network |
|---|---|---|---|
| `adapt_uids(uids, *, fetch=None)` | `:62` | UID list; `fetch` is an injected callable, no HTTP in this module | via caller only |
| `adapt_retrieve_txt(path, *, fetch=None)` | `:86` | one UID per line, delegates to `adapt_uids` | via caller only |
| `adapt_nextseek_workbook(path)` | `:107` | `*_AllMetadata*.xlsx`, one sheet per sample type | none |
| `adapt_curated_sheet(path)` | `:128` | flat `Arm{X}.xlsx`; prefers the `Samples` sheet `:138`; parses a `json_metadata` column `:141-149` | none |
| `adapt_tabular(path, *, sample_type=None)` | `:168` | arbitrary `.csv` (via `csv.DictReader` `:174`) or first sheet of an `.xlsx` | none |

`adapt_uids` makes **no HTTP call itself** — with `fetch=None` it returns an empty sample
list (`:70-71`). The five-level unnest `payload["data"]["data"][i]["samples"][j]["metadata"]`
is at `:73-82`.

`detect_adapter(target)` `:193-205` dispatch order: list/tuple → `uids`; basename
`RETRIEVE.TXT` (case-insensitive) → `retrieve_txt`; `"AllMetadata" in name` →
`nextseek_workbook`; `.xlsx` AND name starts `Arm` AND no `_` in the stem →
`curated_sheet`; else `tabular`. `adapt(target, **kwargs)` `:208-217` is the façade;
kwargs it forwards are `fetch` and `sample_type`.

Lineage: `index_by_uid` `:222`; `resolve_via_lineage(sample, by_uid, key, max_depth=12)`
`:226-256` — breadth-first, leaf-wins, cycle-safe via a `seen` set, multi-parent via
`str(node.parent).split(";")` `:250`. `_MAX_LINEAGE_DEPTH = 12` `:32`.

### 2.2 `enrich.py` — 49 lines, library

Deps `[]`. One function: `merge_leaf_wins(base, extra)` `:20-49`. Copies `base`, then for
each `extra` sample fills only keys whose current value is `None`/`""` (`:38-40`); adds
unseen UIDs (`:32-36`); backfills `parent`/`sample_type` only when empty (`:41-44`).
Records provenance as `source["enriched_from"]` `:48`. No I/O, no network.

### 2.3 `protocols.py` — 198 lines, library

Deps `[]` `:3` — **`PyPDF2` is deliberately absent** and imported lazily at `:111`/`:118`.

- `find_protocol_refs(normalized)` `:47-61` — reads only a metadata key literally named
  `Protocol` (`:52`); skips values containing `*** PLACEHOLDER` / `***PLACEHOLDER`
  (`_PLACEHOLDER_MARKERS` `:32`, check `:55`); splits on `;`; keeps only refs that
  `parse_sop_id` accepts.
- `parse_sop_id(ref)` `:64-72` — `/sops/{id}` URL (`_SOP_URL_RE` `:29`) or a bare
  `P.<alnum._->` name (`_BARE_SOP_RE` `:30`). Free prose → `None`.
- `resolve_host(url, *, nextseek_base_url)` `:75-90` — relative → prefixed with the
  NExtSEEK base; `fairdomhub.org`/`*.fairdomhub.org` → left alone; **every other host,
  including `fairdata.mit.edu`, is rewritten onto the NExtSEEK netloc** `:88-90`.
- `extract_docx_text(data)` `:93-101` — stdlib zipfile, reads `word/document.xml`, strips
  tags; returns `""` on `BadZipFile`/`KeyError`/`OSError`.
- `extract_pdf_text(data)` `:104-120` — raises `PdfSupportError` `:43` when PyPDF2 is not
  importable rather than returning `""`.
- `truncate_tokens(text, limit=3000)` `:123-128` → `(text, was_truncated)`;
  `DEFAULT_TOKEN_LIMIT = 3000` `:40`.
- `resolve_protocols(normalized, *, fetch_sop=None, fetch_blob=None, nextseek_base_url,
  token_limit=3000)` `:131-198` → `({ref: {id,title,text,truncated}}, notes)`. **Both
  fetchers are injected**; this module never opens a socket. With `fetch_sop=None` it
  returns empty plus one note `:148-151`. Every failure path appends to `notes` and
  continues (`:157-158`, `:170`, `:174-176`, `:183-190`).

`DOCX_CONTENT_TYPES` `:34-37`, `PDF_CONTENT_TYPES` `:38`.

### 2.4 `mapping.py` — 304 lines, library. **The template loader + stage-1 validator.**

Deps `[]`.

Constants: `DIRECTIVES = ("source","via_lineage","const","map","synthesize","unmapped")`
`:27`; `_PRIMARY_DIRECTIVES = ("source","const","synthesize","unmapped")` `:31`;
`ROW_SECTION = {"GEO":"samples","SRA":"libraries","PRIDE":"sample_metadata"}` `:33`;
`TARGET_SAMPLETYPE = {"GEO":"D.SEQ","SRA":"D.SEQ","PRIDE":"D.MSP"}` `:34`.

`_GEO_LAYOUT_CV = ["single","paired-end"]` `:40` — a GEO-only CV held **in code** because
the vendored `controlled_vocabulary.library_layout` was mined from SRA/ENA and holds
`['single','paired']`. `_CV_KEY_FOR_FIELD` `:44-60` maps 8 target fields to CV keys; GEO's
`*instrument model` is deliberately **absent** so it stays free text (`:51-57`), while
SRA's `instrument_model` keeps `instrument_model_flat`.

`load_template_spec(path)` `:81-131` → `TemplateSpec(report_type, sections, required, cv,
row_section, raw)` `:63-70`. Section names come from `doc["schema"]["sections"]` `:93`;
field keys come from the top-level `doc[name]` object, using row 0 for list sections
(`:96-101`) — reading keys from `schema.sections[name]` would `KeyError` on PRIDE's
`sample_metadata`. `required` = single-`*` keys only, `**` excluded `:116-120`.

`cv_for_field(spec, field)` `:134-142`. `source_columns` `:145`, `_leaf_columns` `:153`.

`validate_mapping(mapping, spec, normalized)` `:167-293` emits `MappingError(section,
field, code, message)` `:73-78` with these codes: `report_type_mismatch` `:179`,
`row_count_mismatch` `:191`, `unknown_section` `:203`, `unknown_field` `:211`,
`no_directive` `:216`/`:229`, `unknown_directive` `:222`, `conflicting_directives` `:234`,
`unmapped_without_reason` `:242`, `synthesize_in_row_section` `:247`,
`source_column_missing` `:255`, `needs_via_lineage` `:259`, `const_not_in_cv` `:268`,
`map_output_not_in_cv` `:275`, `required_unmapped` `:288`. `_nearest` `:296-304` uses
`difflib.get_close_matches(cutoff=0.4)` to make CV errors actionable.

### 2.5 `execute.py` — 229 lines, library

Deps `[]`. Bootstraps `sys.path` to `scripts/` `:33` then imports `_common.placeholder`
`:34` (defined `scripts/_common.py:36-38`, returns `*** PLACEHOLDER: <what> ***`),
`report.adapters.index_by_uid/resolve_via_lineage` `:35`, `report.mapping.TARGET_SAMPLETYPE`
`:36`. `OUTPUT_SUBDIR = "report"` `:38`.

`apply_mapping(mapping, spec, normalized, *, synthesized=None)` `:86-160` → `(filled, gaps)`.
Row set = samples whose `sample_type` equals `row_scope.target_sampletype` or the
`TARGET_SAMPLETYPE` default `:102-106`. `_fill_row` `:56-83` handles `unmapped` → `""`,
`const`, `source` (+ `via_lineage`, + `map`), and records a `Gap(section, field, reason,
searched, uid)` `:45-53` on every miss. Non-row sections take `synthesize` text from the
caller-supplied dict or degrade to a placeholder `:128-139`; a `source` directive in a
non-row section is filled from `rows_in[0]` `:144-148`.

`RowParityError` `:41` is raised at `:155-159` when `row_scope.expected_rows` is set and
does not equal the produced row count — "Refusing to emit a partial artifact."

`write_filled(root, report_type, filled)` `:163-167` → `<root>/report/<TYPE>_filled.json`.
`render_completeness(...)` `:170-222` builds the markdown (gap table grouped by
(section, field) `:189-197`; a "Deliberately unmapped" section `:200-214`).
`write_completeness` `:225-229` → `<root>/report/<TYPE>.completeness.md`.

### 2.6 `render.py` — 219 lines, library. **Exactly three renderers.**

Deps `openpyxl>=3.1` `:3`. `_PLUGIN = Path(__file__).resolve().parent.parent.parent` `:27`
(= plugin root).

`RENDERERS = {"GEO": _geo, "SRA": _sra, "PRIDE": _pride}` `:206`. `render(report_type,
filled, *, template_dir, out_dir)` `:209-219` raises `UnsupportedFormatError` `:30` for
anything else. **No fourth format is implemented.**

- `_geo` `:191-193` → `render_geo(filled, template_dir/"GEO_template.xlsx",
  out_dir/"GEO_filled.xlsx")`. `render_geo` `:44-66` writes a temp
  `<out>.render-input.json` `:55-56` and **shells out**:
  `subprocess.run(["uv","run","--script", <plugin>/scripts/deposit/geo_build_xlsx.py,
  tmp_json, template_xlsx, out_path], timeout=300)` `:57-62`, unlinks the temp on success
  `:65`, raises `RuntimeError` with the child's stderr on non-zero `:63-64`.
- `_sra` `:196-198` → `render_sra(filled, template_dir/"SRA_metadata.xlsx",
  template_dir/"SRA_biosample.xlsx", out_dir)`. `render_sra` `:130-143` emits
  `SRA_metadata_filled.xlsx` from `filled["libraries"]` and `SRA_biosample_filled.xlsx`
  from `filled["biosamples"]`; each section is optional (`if filled.get(...)`).
  `_find_header` `:71-95` locates the sheet+row with the most header matches within the
  first 50 rows rather than assuming row 1 — required because SRA_metadata's real header is
  row 1 of the *second* sheet and SRA_biosample's is row 12. `_fill_sheet_from_rows`
  `:98-127` promotes the matched sheet to index 0 (`wb.move_sheet` `:114`) and writes by
  marker-insensitive, case-insensitive header name (`_strip_marker` `:34-39`).
- `_pride` `:201-203` → `render_pride(filled, template_dir/"pride.json",
  out_dir/"submission.px")`. `render_pride` `:148-186` writes a **tab-delimited** file, not
  a spreadsheet: a `COM` header line `:159-160`, one `MTD` line per `project_metadata` key
  `:161-163`, `FMH`/`FME` for `file_mapping` `:165-172`, `SMH`/`SME` for `sample_metadata`
  `:174-181`. Prefixes are read from `spec["format"]["line_prefixes"]` `:156`.

Template files these paths require all exist in `context/report_templates/`:
`GEO_template.xlsx`, `GEO-updated.json`, `SRA.json`, `SRA_metadata.xlsx`,
`SRA_biosample.xlsx`, `pride.json`. Each has a `context/PROVENANCE.json` entry.
`render.py` takes `template_dir` as a parameter and does **not** default it to
`context/report_templates` — the caller must supply it.

### 2.7 `validate_artifact.py` — 326 lines, library. Vendored subset.

Deps `openpyxl>=3.1` `:3`, imported lazily at `:195`. Provenance entry:
`context/PROVENANCE.json` → `scripts/report/validate_artifact.py`, from dmac-assistant
`tools/hibayes/artifact_validator.py` @ `dcca50c…`, "SUBSET plus extension".

`ArtifactStatus` `:35-40` = Valid / Incomplete / SchemaInvalid / Missing / Unreadable.
`DISPOSITION` `:44-50` maps them to CLEAN / SOFT_FLAG / HARD_REJECT / HARD_REJECT /
HARD_REJECT; exposed as `ValidatorResult.disposition` `:71-73`. `ValidatorResult` carries
14 fields `:53-69`.

Three public validators — one per supported format, matching `render.py` exactly:
- `validate_geo_xlsx(*, file_path, geo_template_path)` `:251-256`.
- `validate_sra_xlsx(*, file_path, sra_spec_path, section="libraries")` `:259-264`.
- `validate_pride_px(*, file_path, pride_spec_path)` `:267-326` — parses line prefixes,
  `SchemaInvalid` on an unknown prefix or missing `MTD`, `Incomplete` on missing `SME`
  `:308-313`.

`required_fields(spec_path, section)` `:76-101` returns single-`*` keys of `spec[section][0]`;
its docstring `:83-91` records a **verified known gap**: SRA's `libraries` section stars
nothing, so this returns `[]` and any readable SRA_metadata workbook validates `Valid`.
`_read_sheet_once` `:104-157` locates the header row by best overlap with the required
names (falling back to row 0) and stops data collection at the first entirely-empty row —
necessary because the real GEO `Metadata` sheet is a vertical multi-section form.
`_check_required` `:160-185` is the two-part check: header presence, then per-row
non-null.

### 2.8 `scrub_fixture.py` — 69 lines, **the only report CLI**

Deps `[]`.

```
uv run --script <PLUGIN>/scripts/report/scrub_fixture.py SOURCE DEST
```

`main` `:56-65`. Reads a harvested JSON artifact, writes a scrubbed copy (creating parent
dirs `:62`). `scrub(doc)` `:39-53` recursively replaces the value of any key matching
`(token|password|passwd|secret|api[_-]?key|authorization|cookie)` `:24-26` with
`***REDACTED***` `:30`, rewrites `http(s)://localhost|127.0.0.1[:port]` to
`https://nextseek.example.org` `:27`/`:31`, and strips `user:pass@` basic-auth from URLs
`:28`.

### 2.9 `report` subpackage — commands, true capability, doc deltas

Driven by one command: `/curate-report <FORMAT> <input>` (`commands/curate-report.md`),
with `/curate-deposit geo` delegating its build step to it (`commands/curate-deposit.md:13`,
enforced by `tests/test_deposit_delegates_geo.py:14-16`). Reference doc:
`skills/curation/REPORTS.md`.

**True capability, stated exactly:**
- Target repositories implemented: **GEO, SRA, PRIDE — three, no more.** Each has both a
  renderer (`render.py:206`) and a validator (`validate_artifact.py:251/259/267`).
  nf-core is genuinely absent, as documented.
- Input adapters implemented: **five** — `uids`, `retrieve_txt`, `nextseek_workbook`,
  `curated_sheet`, `tabular` (`adapters.py:210-217`). Two of the five (`uids`,
  `retrieve_txt`) require the caller to inject a `fetch` callable; the module itself
  contains no HTTP client, and **no code in this subpackage or elsewhere in `scripts/`
  supplies that callable.** The NExtSEEK retrieve call named in
  `commands/curate-report.md:52` and `skills/curation/REPORTS.md:66` is therefore a
  contract, not a shipped code path, unless the agent wires `scripts/nextseek_api.py` to it
  by hand.
- Live-server writes: **none.** Nothing in `scripts/report/` performs an HTTP write. The
  only outbound-capable code is `render_geo`'s local `subprocess` call `:58-62`.

Doc deltas found:
- **No invocation is documented for seven of the eight modules.** `grep 'uv run'
  commands/curate-report.md skills/curation/REPORTS.md` returns nothing. Both docs name
  modules ("`scripts/report/execute.py` applies the mapping…",
  `commands/curate-report.md:126-128`) as if they were runnable scripts, but only
  `scrub_fixture.py` has a `main()`. `uv run --script scripts/report/execute.py` exits 0
  having done nothing. Meanwhile `skills/curation/SKILL.md` hard rule 6 states "All scripts
  have PEP 723 inline-deps. Invoke via `uv run --script <plugin>/scripts/X.py`", which is
  false for this subpackage. The real contract — `sys.path.insert(0, <plugin>/scripts)`
  then `from report import execute` — appears nowhere outside the test files.
- `scrub_fixture.py` is **absent from the module table** in
  `skills/curation/REPORTS.md:139-147` (7 rows, one per other module). It is documented
  only in `tests/fixtures/nextseek/README.md:45,58`.
- `render.py`'s `template_dir` parameter has no documented default; `commands/curate-report.md:70-72`
  names the JSON specs (`GEO-updated.json`, `SRA.json`, `pride.json`) but never mentions
  that rendering additionally needs `GEO_template.xlsx`, `SRA_metadata.xlsx` and
  `SRA_biosample.xlsx` from the same directory.

---

## 3. `scripts/schema/`

Six real modules plus an empty `__init__.py`. **Zero CLIs** — no `main()`, no `argparse`,
no `if __name__` anywhere in the subpackage. Import contract:
`sys.path.insert(0, <plugin>/scripts)` then `from schema import field_index`
(`tests/test_field_index.py:8-10`).

### 3.1 `field_index.py` — 220 lines. Catalog loading, usage index, the reuse check.

Deps `[]` `:3`. Bootstraps `sys.path` to `scripts/` `:25` and imports
`_config.plugin_context` `:26` (defined `scripts/_config.py:40-42`, resolves
`<plugin>/context/<name>`).

- `FIELD_SOURCES = ("Required Metadata","Standard Metadata","Possible Metadata Fields")` `:28`.
- `load_catalog(path=None)` `:59-61` — reads `sampletypes_db.json`, defaulting to the
  plugin's read-only copy. Read-only; nothing here writes.
- `type_record(catalog, sampletype)` `:64-68` — raises `KeyError` on miss.
- `siblings_in_clade(catalog, sampletype)` `:71-78` — other types sharing `Clade`.
- `build_field_index(types)` `:85-95` → `{name: FieldUsage(name, used_by)}` `:35-44`.
- `normalize_field_name(name)` `:98-111` — casefold, strip non-alnum, `ies`→`y`, trailing
  `s` (not `ss`), with `_PLURAL_EXCEPTIONS = {status, analysis, series, species, apparatus}`
  `:32`.
- `rank_candidates(candidate, index, *, clade, assay, catalog, dictionary, limit=10)`
  `:120-191` — **the reuse check.** Four passes with fixed weights
  `{exact:1000, normalized:500, synonym:400, semantic:100}` `:158-159`, `+ usage.count`,
  `+25` for a clade-type overlap, `+15` for an assay-type overlap `:176-179`. Returns
  `Candidate(name, usage_count, used_by, match_pass, example_values, score)` `:47-56`.
  Never returns a yes/no.
- `_words(name)` `:194-209` — CamelCase/underscore/hyphen/space splitter, words ≤2 chars
  dropped. This is what makes the `semantic` pass fire on a single shared stem.
- `mine_tags(record)` `:212-220` — splits the catalog `Tags` column on commas.

Verified against the shipped catalog (`context/sampletypes_db.json`): **101 sample types,
1,059 distinct field names, 857 used by exactly one type.**

### 3.2 `dictionary.py` — 158 lines. The lazy, cwd-only field dictionary.

Deps `openpyxl>=3.1` `:3`, `from openpyxl import load_workbook` `:25`.
`DICTIONARY_NAME = "field_dictionary.json"` `:27`, `OUTPUT_SUBDIR = "schema"` `:28`.

- `observe_values(workbooks, fields)` `:34-72` — mines distinct real values for the named
  fields across every sheet of every workbook; first-seen order, deduped; skips values
  containing `*** PLACEHOLDER` / `***PLACEHOLDER` (`_NON_VALUES` `:31`, check `:65`).
- `build_entry(name, usage, observed, *, description, datatype="string", synonyms,
  ontology, extra_provenance)` `:75-106` — **forces `ontology["confirmed"] = False`
  whatever the caller passed** `:87-89`. Entry keys: `description, datatype, used_by,
  observed_values, ontology, synonyms, provenance`.
- `merge_dictionary(existing, new)` `:109-140` — unions `observed_values`, `used_by`,
  `synonyms` preserving order `:123-128`; a human-confirmed ontology is never downgraded
  `:133-136`; a non-empty description/datatype overwrites, an empty one does not
  `:129-132`.
- `dictionary_path` `:143`, `load_dictionary` `:147` (returns `{}` when absent),
  `save_dictionary` `:154-158` → `<cwd>/schema/field_dictionary.json`, `mkdir -p`, sorted
  keys.

No pre-built dictionary ships with the plugin (docstring `:7-8`); nothing accumulates
across projects (`:16-18`).

### 3.3 `ontology.py` — 141 lines. Controlled-vocabulary proposals + the `<TYPE>.ontology.json` artifact.

Deps declared `openpyxl>=3.1` `:3` — **but the module never imports openpyxl** (imports are
`json`, `os`, `dataclasses`, `pathlib`, `:25-28`). Spurious declaration.

- `BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"` `:30`; `bioportal_available()` `:47-53` is a
  bare env check.
- `_SOURCE_RANK = {"tags":0, "sibling":1, "bioportal":2, "observed":3}` `:35` — strongest
  last, so a value both tagged and observed is credited `observed`.
- `propose_values(record, field_name, *, observed, tags, siblings, bioportal)` `:56-97` —
  when `tags is None` it mines the record's `Tags` column itself `:69-70`. Returns
  `ProposedValue(value, source, note)` `:38-44` with a fixed note per source `:90-95`.
  Note: `field_name` is accepted but unused in the body.
- `to_ontology_json(proposals)` `:100-103` — exactly the `{field: [values]}` shape
  `_common.write_4sheet_xlsx(ontology=...)` expects (verified: `scripts/_common.py:188-210`,
  `ontology` parameter at `:193`, semantics documented `:204-209`).
- `artifact_path` `:106`, `write_ontology_artifact` `:110-132` → `<cwd>/schema/<TYPE>.ontology.json`
  with a `_sources` sidecar `:119-122` and a `_note` `:123-128`; `load_ontology_artifact`
  `:135-141` reads back only the non-`_` keys.

### 3.4 `terms.py` — 188 lines. BioPortal lookup. **Live outbound HTTP.**

Deps `[]` `:3` — uses stdlib `urllib.request` `:28`.
`BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"` `:32`;
`BIOPORTAL_CLASS_URL = ".../ontologies/{acronym}/classes/{iri}"` `:33`;
`DEFAULT_ONTOLOGIES = ("NCIT","OBI","EFO","UBERON","CL")` `:36`; timeout 20s `:38`.

- `search_terms(query, *, ontologies, api_key, limit=5, http=None)` `:88-133` → `[TermHit(iri,
  label, source, score, definition)]` `:41-49`. **Returns `[]` and makes no network call
  without `BIOPORTAL_API_KEY`** `:98-100`. Key travels in the `Authorization` header, never
  the query string `:109`. Any exception → `[]` `:132-133`.
- `clade_neighbors(hit, *, api_key, limit=10, http=None)` `:136-182` → `[CladeNeighbor(label,
  iri, definition, relation)]` `:52-59`; fetches `/parents` and `/children`, tolerating
  BioPortal's two list shapes via `_collection` `:68-80`; one dead endpoint never discards
  the other `:169-170`.
- `to_binding(hit)` `:185-188` — always `{"confirmed": False}`.

The `http=` parameter on both functions is the injection point the tests use; production
calls fall through to `_default_http` `:62-65`.

### 3.5 `templates.py` — 139 lines. CEDAR reference-template checklist. **Live outbound HTTP.**

Deps `[]` `:3`, stdlib `urllib.request` `:35`.
`CEDAR_ENV_VAR = "CEDAR_API_KEY"` `:38`;
`CEDAR_TEMPLATE_URL = "https://resource.metadatacenter.org/templates/{id}"` `:39`;
timeout 30s `:57`.

`REFERENCE_TEMPLATES` `:52-55` holds **exactly one** pinned template:
`"common assay template"` → `https://repo.metadatacenter.org/templates/303429bb-b7a8-4cbe-b4e2-8c3be6b95f5c`.
The docstring records it as third-party, `bibo:draft` v0.0.1, read at runtime and never
vendored `:49-51`.

`template_fields(template_id, *, api_key, http=None)` `:114-139` → `[TemplateField(name,
description, branches, required, path)]` `:60-68`. **Returns `[]` with no network call
absent a key** `:121-123`; any exception → `[]` `:131-132`. `_walk` `:77-111` is driven by
`_ui.order` (not `properties`) so JSON-LD scaffolding is never reported `:80-84`, unwraps
`{"type":"array","items":{…}}` `:93-94`, and recurses into `TemplateElement` nodes `:96-98`.

### 3.6 `review.py` — 250 lines. Renders `<TYPE>.review.md`, the deliverable.

Deps `[]` `:3`. `OUTPUT_SUBDIR = "schema"` `:24`.

`REQUIRED_SECTIONS` `:26-35` — the eight headings the review must carry: Current state,
External clade evidence, Reference template checklist, Proposed additions, Reuse decisions,
Controlled vocabularies proposed, Open questions and placeholders, How to apply.

`render_review(sampletype, *, record, current_fields, proposals, reuse_decisions, ontology,
open_questions, dictionary_entries, external_clade=None, template_checklist=None)`
`:38-235` — pure string building, no I/O. Opens every review with "**This is a proposal.**
Nothing here has been applied. schema mode never writes to NExtSEEK and never edits
`sampletypes_db.json`." `:67-69`. The "How to apply" block `:194-220` is five manual steps.

`write_review(root, sampletype, markdown)` `:238-242` → `<cwd>/schema/<TYPE>.review.md`.
`write_proposed_record(root, sampletype, record)` `:245-250` → `<cwd>/schema/<TYPE>.proposed.json`,
sorted keys — for diffing against the catalog record. Never edits the catalog.

### 3.7 `schema` subpackage — commands, true capability, doc deltas

Driven by one command: `/curate-sampletype <TYPE>` (`commands/curate-sampletype.md`; the
6-step loop is `:167-234`). Reference doc: `skills/curation/SCHEMA.md`.
`scripts/status.py:186` reports schema-mode state by counting `schema/*.review.md`.

**True capability, stated exactly:**
- `field_index.py` — loads the catalog read-only, builds a name→types usage index, and
  ranks reuse candidates in four passes; also splits the `Tags` column. It never proposes a
  rename or a split (docstring `:11-16`).
- `ontology.py` — merges four value sources (tags / observed / sibling / bioportal) into a
  deduped, source-attributed proposal and writes `<TYPE>.ontology.json` in exactly the shape
  `_common.write_4sheet_xlsx(ontology=)` consumes. It does **not** call BioPortal itself;
  `bioportal` values are passed in by the caller.
- `dictionary.py` — mines observed values from local workbooks, builds/merges the lazy
  `schema/field_dictionary.json`, and hard-forces every ontology binding unconfirmed.
- `terms.py` — the only BioPortal client: `search_terms` and `clade_neighbors`. Suggests
  IRIs, never binds them.
- Outputs, all under `<cwd>/schema/`: `<TYPE>.review.md`, `<TYPE>.proposed.json`,
  `<TYPE>.ontology.json`, `field_dictionary.json`. Nothing writes to NExtSEEK or to the
  plugin's `context/`.
- Network reach: two hosts, both key-gated and both degrading to `[]` —
  `data.bioontology.org` (`terms.py`) and `resource.metadatacenter.org` (`templates.py`).

Doc deltas found:
- **`scripts/schema/templates.py` is missing from the module table** in
  `skills/curation/SCHEMA.md:52-58`, which lists five modules and omits the sixth. It is
  the only source in the mode that names *fields* rather than values, and it is the only
  consumer of `CEDAR_API_KEY`. `commands/curate-sampletype.md:186-198` does document it.
- **Contradictory template counts.** `scripts/schema/templates.py:17-18` says
  `common assay template` "carries 25 fields, 24 of them described and 20 bound to a
  BioAssay Ontology branch"; `commands/curate-sampletype.md:187-188` says "returns 28
  fields, 27 described and 22 bound". Both cannot be right; the value is fetched live from
  a third-party draft template, so neither is stable.
- **`skills/curation/SCHEMA.md:12` says "856 are used by exactly one type".** The true
  figure computed from the shipped `context/sampletypes_db.json` is **857**, which is what
  `scripts/schema/field_index.py:8` says. SCHEMA.md is off by one.
- No invocation is documented for any schema module (`grep 'uv run'
  skills/curation/SCHEMA.md` → nothing; `commands/curate-sampletype.md`'s four `uv run`
  lines `:61,67,75,84` are all for `scripts/sampletype_attr.py`, a different, top-level
  script). Same `sys.path` + import contract as `report/`, documented nowhere outside tests.

---

## 4. `scripts/deposit/`

### 4.1 `scripts/deposit/__init__.py` — 0 bytes.

### 4.2 `scripts/deposit/geo_build_xlsx.py` — 198 lines, CLI. **The single GEO build path.**

PEP 723 `:2-5`, `requires-python >=3.10` (the only module in these subpackages not on
`>=3.11`), dep `openpyxl>=3.1`. Provenance comment `:6`: lifted from
`lee/scripts/render_geo_xlsx.py`.

```
uv run --script <PLUGIN>/scripts/deposit/geo_build_xlsx.py JSON TEMPLATE OUTPUT
```

Three positional args, no flags: `json_path`, `template_path`, `out_path`
(`main` `:188-194`). **There is no `--write` gate and no dry-run** — it always writes
`OUTPUT`. That is consistent with its role (it writes a new local xlsx, never a server),
and it is correspondingly absent from the `DEPOSIT_SCRIPTS` list in
`tests/test_deposit_write_safety.py:16-22`, which covers only top-level scripts
(`stage_zenodo.py`, `apply_zenodo_links.py`, `apply_geo_accessions.py`, `apply_omero_ids.py`,
`smb_pull.py`).

Input contract `render` `:44-185`: `data["samples"]` `:52` and
`data.get("paired_end_experiments", [])` `:53` — exactly what `execute.apply_mapping`
emits for GEO. Template contract: the `Metadata` worksheet `:48` must contain a row whose
column A is `*library name` `:56`, one that is `PROTOCOLS` `:57`, and one that is
`file name 1` `:58`; any missing anchor raises `ValueError` `:60-65`.

Algorithm: capture the static PROTOCOLS→PE-header block over `STATIC_BLOCK_COLS = 8`
columns `:33`, `:72-77`; wipe from the SAMPLES header row to the end of sheet `:123-127`;
write a header of 14 base columns `:80-85` plus dynamically sized `processed data file`
and `raw file` columns `:102-119`; write sample rows `:134-154`; re-paste the static block
after a one-row gap `:158-165`; write paired-end rows into columns 1-4 `:167-172`.

`:108-112` carries an unresolved TODO(v0.2) about GEO's column naming for 3+ raw files per
sample — a reviewer claimed plain `raw file`, a real submission used numbered
`raw file (N)`; unverified against the actual template.

### 4.3 `deposit` subpackage — commands, true capability, doc deltas

**No slash command invokes this file directly.** `commands/curate-deposit.md:13` explicitly
forbids it ("Do **not** invoke a renderer here: there is exactly one GEO build path and it
lives in report mode"), and `tests/test_deposit_delegates_geo.py:19-22` asserts the string
`geo_build_xlsx.py` does not appear in the GEO route. Its only caller is
`scripts/report/render.py:57-62`, which shells out to it.

True capability of the subpackage: **one script, GEO xlsx rendering only.** There is no
SRA, PRIDE, Zenodo or OMERO code under `scripts/deposit/`. The Zenodo/OMERO/GEO-accession
machinery `/curate-deposit` actually drives lives at the top level
(`scripts/stage_zenodo.py`, `scripts/apply_zenodo_links.py`, `scripts/apply_geo_accessions.py`,
`scripts/omero_pull.py`, `scripts/apply_omero_ids.py`, `scripts/upload_geo_ncftp.sh`) and is
outside this inventory's scope.

Doc delta found: `README.md:94-104`'s tree lists `scripts/fdh/`, `scripts/report/` and
`scripts/schema/` with one-line descriptions but **does not list `scripts/deposit/` at
all**, so a reader has no way to learn that a `deposit` package exists or that it holds
exactly one file. The name also invites the assumption that `/curate-deposit` is driven
from it, which is false.

---

## 5. Cross-cutting findings

### 5.1 Implemented but undocumented

| what | where | not documented in |
|---|---|---|
| `scripts/schema/templates.py` (CEDAR checklist, `CEDAR_API_KEY`) | whole module | `skills/curation/SCHEMA.md:52-58` module table |
| `scripts/report/scrub_fixture.py` (the only report CLI) | whole module | `skills/curation/REPORTS.md:139-147` module table |
| `scripts/deposit/` as a package | `README.md:94-104` tree | README repo layout |
| `submit.py` Step 4 creates SampleTypes with no confirm | `scripts/fdh/submit.py:1570-1573` | `commands/fdh-upload.md`, `skills/curation/FDH.md` |
| `submit.py` Step 3 rewrites the workbook in place via xlsxwriter, losing formatting, no backup | `scripts/fdh/submit.py:1495`, `:617-620` | `commands/fdh-upload.md`, `skills/curation/FDH.md` |
| `build_api_index.py` writes inside the plugin checkout | `scripts/fdh/build_api_index.py:24`, `:177` | anywhere; contradicts the `plugin_sentinel` P1 rule in `tests/conftest.py:1-2` |
| `field_index.mine_tags` | `scripts/schema/field_index.py:212` | named only obliquely as "Tags mining" in the SCHEMA.md table |
| `ontology.py` declares an unused `openpyxl` dependency | `scripts/schema/ontology.py:3` vs imports `:25-28` | — |

### 5.2 Referenced by docs but absent / wrong in reality

| doc claim | reality |
|---|---|
| `skills/curation/SKILL.md` hard rule 6: "All scripts have PEP 723 inline-deps. Invoke via `uv run --script …`" | False for 13 of 16 modules in `report/` + `schema/`. Only `scrub_fixture.py`, `fdh_api.py`, `submit.py`, `build_api_index.py`, `geo_build_xlsx.py` have a `main()`. The rest are import-only and silently no-op under `uv run --script`. |
| `skills/curation/FDH.md:5`: host "Override via `.env` `FDH_BASE_URL` or `--base-url`" (section covers both modules) | True for `fdh_api.py:200`. False for `submit.py` — hardcoded production at `:73`, no such flag at `:1780-1845`. |
| `skills/curation/SCHEMA.md:12`: "856 are used by exactly one type" | 857 (computed from `context/sampletypes_db.json`; matches `field_index.py:8`). |
| `commands/curate-sampletype.md:187`: CEDAR template "returns 28 fields, 27 described and 22 bound" | `scripts/schema/templates.py:17-18` says 25 / 24 / 20. Live third-party draft; unverifiable without `CEDAR_API_KEY`. |
| `commands/curate-report.md:52` / `REPORTS.md:66`: UID adapters `POST /nextseek_api/admin/samples/retrieve/` | `adapters.adapt_uids:62-83` takes an injected `fetch` callable and returns zero samples when it is `None`. No shipped code supplies it. |
| `scripts/fdh/generated/REGISTRY.md:10`: `_(none yet)_` | Generated scripts exist in the main tree; they are gitignored (`.gitignore:156`) and therefore **absent from this worktree entirely** — `generated/` here holds only `__init__.py` and `REGISTRY.md`. |
| `skills/curation/SKILL.md` mode table lists 5 modes incl. `assay` | Confirmed present at `skills/curation/SKILL.md:30-35`; `README.md:17-22` still lists only four modes and never mentions `assay`. (Out of this inventory's scope, noted for the docs owner.) |

### 5.3 Not verified here

The contents of `scripts/fdh/generated/*.py` (the 7 generated task scripts). They are
gitignored and do not exist in this worktree; reading the main working tree was out of
bounds for this audit. Their purposes, endpoints and `--write` guards are therefore
**unknown** and must be inventoried separately, against the main tree.
