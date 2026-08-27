# Ground-truth inventory — "commands-other"

Scope: `commands/fdh-upload.md`, `commands/fdh-api.md`, `commands/curate-sampletype.md`,
`commands/curate-report.md`, plus every script each one actually invokes.

Worktree: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs` (branch `dev-docs`,
tip `833e9be`, `git status` clean). All paths below are repo-relative to that worktree unless
absolute. Every assertion here was verified by reading the file cited. Nothing was executed
against a network or a live server.

---

## 0. Facts common to all four

- **Frontmatter is one key.** All four files are exactly `---` / `description: <text>` / `---`.
  No `argument-hint`, no `allowed-tools`, no `model`, no `disable-model-invocation`.
  - `commands/fdh-upload.md:1-3` — `description: Launch the interactive FairDomHub study-upload tool (Module 1)`
  - `commands/fdh-api.md:1-3` — `description: Programmatic FairDomHub API access — reuse-or-generate a task script (Module 2)`
  - `commands/curate-sampletype.md:1-3` — `description: Propose or bolster a NExtSEEK sample type (schema mode)`
  - `commands/curate-report.md:1-3` — `description: Build a GEO / SRA / PRIDE submission artifact from metadata you have (report mode)`
- **`$ARGUMENTS`**: parsed by `fdh-api.md:9`, `curate-sampletype.md:8`, `curate-report.md:8`.
  `fdh-upload.md` never references `$ARGUMENTS` — it takes no arguments.
- **`<PLUGIN>` placeholder.** `fdh-upload.md:28`, `fdh-api.md:16,18,20,22,24,31`,
  `curate-sampletype.md:61,67,75,84` write literal `<PLUGIN>` in the invocation lines. The command
  files never define it. `curate-report.md` uses bare repo-relative paths instead
  (`scripts/report/adapters.py`, `context/report_templates/...`) — an inconsistency between the
  two conventions inside the same set of four files.
- **Plugin version** is `0.4.0` (`.claude-plugin/plugin.json`, and the marketplace entry in
  `.claude-plugin/marketplace.json`).
- Every Python script referenced is PEP 723 inline-deps, run as `uv run --script <path>`.

---

## 1. `commands/fdh-upload.md` — launch `scripts/fdh/submit.py`

### 1.1 What the command does

It is a **prereq check + handoff**. It never runs anything itself: `fdh-upload.md:22` "Do not mint
anything — this tool is human-driven"; `:26-28` "Hand off — the user runs it interactively
themselves (Claude cannot answer the questionary prompts)".

**The one invocation line, verbatim (`fdh-upload.md:28`):**

```
uv run --script <PLUGIN>/scripts/fdh/submit.py
```

No flags are passed by the command. `--resume` / `--step N` are mentioned as resumability
(`:25`) but never given a concrete invocation.

### 1.2 Prerequisites the command asserts (`fdh-upload.md:9-19`)

| prereq | verified against |
|---|---|
| `./.env` in cwd holds `FDH_API={"<name>": "<token>"}` (JSON) | `submit.py:1281-1292` (`load_dotenv()`, `os.environ.get("FDH_API")`, `json.loads`, `sys.exit(1)` on absent/invalid/empty) |
| show the format from `<PLUGIN>/skills/curation/FDH.md` and stop if absent | format is at `skills/curation/FDH.md:8-9` |
| `Assets/<name>.xlsx`, one sheet per Sample Type, `UID` column required | `submit.py:34-36` (docstring); workbook path is prompted, not fixed (`submit.py:1334-1341`) |
| `Assets/Protocols/` holding `.pdf`/`.docx` SOPs | hard-coded in `submit.py:1417` — `build_protocols_dataframe("Assets/Protocols")`; the default arg is `submit.py:340` |
| Study already created manually on the FDH web UI, numeric ID known | prompted at `submit.py:1303` |

### 1.3 `scripts/fdh/submit.py` — actual behaviour

- 1953 lines. Deps: `requests`, `pandas`, `openpyxl`, `xlsxwriter`, `rapidfuzz`, `questionary`,
  `rich`, `python-dotenv` (`submit.py:4-13`).
- Host is **hard-coded**: `BASE_URL = "https://fairdomhub.org/"` (`submit.py:73`). There is no
  `--base-url` and it does **not** read `FDH_BASE_URL`, unlike `fdh_api.py:200`.
- `PROJECT_MAPPING` (`submit.py:77-83`) — exactly five entries:
  `222: Impact`, `221: SRP`, `340: MetNet`, `343: Endo-Griffith`, `441: CSBC`. A manual numeric
  project id can also be entered (`submit.py:1312-1312`, `1321-1332`).
- `OUTPUT_DIR = "Assets/Output"`, `SESSION_FILE = "Assets/Output/session.json"` (`submit.py:85-86`).
  Both are **relative to the process cwd**, not to the plugin.

**CLI surface (`submit.py:1780-1844`), the complete set:**

| flag | values | meaning |
|---|---|---|
| `--step N` | `1,2,3,4,5,6` (`submit.py:1821`) | run Step 0 (config) then start at N |
| `--resume` | store_true | load `Assets/Output/session.json`, resume at `last_completed_step + 1`; skips Step 0 |
| (none) | | full run from Step 1 |

`--step` and `--resume` are mutually exclusive (`submit.py:1817`).

**Steps, outputs by exact filename, and which ones write to fairdomhub.org:**

| step | function | writes to FDH? | file outputs |
|---|---|---|---|
| 0 Config | `step_config` `submit.py:1262` | no | `Assets/Output/session.json` (`_save_session(cfg, 0)`, `submit.py:1360`) |
| 1 Assays | `step_assays` `submit.py:1364` | **yes** — `bulk_create_assays_df` → `create_assay` POST (`submit.py:241,284`), only if the operator answers "Create new assays?" (`:1381`, default `False`) | `Assets/Output/assays_from_study.csv` (`:1393`) |
| 2 Protocols | `step_protocols` `submit.py:1399` | **yes** — `upload_protocols_df` (`:524`), two-step SOP create-then-PUT-bytes (`create_sop_with_placeholder` `:423`, `upload_sop_binary_with_retry` `:489`); gated by a confirm defaulting **True** (`:1463`) | `Assets/Output/protocols_preupload.csv` (`:1459`), `Assets/Output/protocols_uploaded.csv` (`:1468`) |
| 3 Metadata rewrite | `step_metadata_rewrite` `submit.py:1474` | no (local) | **overwrites `cfg["workbook"]` IN PLACE** — `replace_anywhere_in_metadata(cfg["workbook"], uploaded_csv, cfg["workbook"])` (`:1495`); confirm defaults **True** (`:1488`) |
| 4 Sample types | `step_sample_types` `submit.py:1549` | **yes** — `create_sample_types_from_workbook` (`:784`) → `create_sample_type` (`:744`) | `Assets/Output/sample_types_created.csv` (`:1583`) |
| 5 Samples | `step_samples` `submit.py:1589` | **yes** — `create_samples_from_workbook` (`:944`); confirm defaults **True** (`:1614`) | `Assets/Output/samples_created.csv` (`:1621`) |
| 6 Publish | `step_publish` `submit.py:1627` | **yes, and this is the destructive one** | `Assets/Output/published_assets.csv` (`:1715`) |

Confirm-prompt line numbers, exact: step 2 upload `:1463`, step 3 rewrite `:1488`, step 5 samples
`:1614`, step 6 access level `:1645`, step 6 publish `:1675`, parallel PATCH `:1699`.

**Step 6 in detail — the visibility write.** `step_publish` prompts for an access level
(`view` or `download`, `submit.py:1645-1653`), calls `collect_study_assets` (`:1027`) which walks
the study's relationships in three passes (links.related → inline relationships.data → recurse into
each assay for nested `data_files` and `samples`), then `PATCH`es every discovered asset with
`policy.access = <level>` plus a `manage` permission for **`cfg["project_id"][0]` only — the first
selected project** (`step_publish`: `submit.py:1654`; payload: `publish_resource` `:1107-1143`).
Publishable types are `assays, sops, sample_types, samples, data_files, models, presentations,
publications` (`_PUBLISHABLE_TYPES`, `submit.py:1023-1024`). Samples are PATCHed by a 5-worker
`ThreadPoolExecutor` when there are more than 5 (`:1697-1699`). The confirm defaults **False**
(`:1675-1679`) — the only step whose confirm is deny-by-default. The study record itself is not
published (`:1636-1637`, `:1946-1947`).

**Step 6 always runs on a default full run.** `main()` calls `step_publish(cfg)` unconditionally at
`submit.py:1940` — it is outside every `if start_step <= N` guard. The only escape is the
deny-by-default confirm inside it.

**Resume/skip semantics (`submit.py:1883-1937`)**: with `--step 6`, `df_assays` and `summary_df` are
set to empty DataFrames (`:1891`, `:1915`) rather than loaded from CSV. With `--step 2..5`, earlier
steps load from `Assets/Output/*.csv` via `_load_assays_from_csv` (`:1733`) and
`_load_summary_from_csv` (`:1753`). After Step 5 there is an "additional workbook" loop that re-runs
sample types + samples for a second workbook (`:1925-1935`).

### 1.4 Auth

Token only, selected interactively from the `FDH_API` JSON map (`submit.py:1295-1301`). Header is
`Authorization: Token <token>` (`submit.py:97-121`). The token is echoed as `**********` in the
config summary (`submit.py:1357`) but **written in plain text** to `Assets/Output/session.json`
(`_save_session` `submit.py:1225-1230`, called with step 0 at `submit.py:1360`; warned at
`submit.py:1222`).

### 1.5 Verified drift in this command / its script

- `fdh-upload.md:34-36` says "The plugin cannot ignore it for the user… tell the user to add
  `Assets/Output/` to their project's `.gitignore`." Correct reasoning, and the plugin's own
  `.gitignore:70` already lists `Assets/Output/` for the plugin checkout itself.
- `submit.py:37` and `submit.py:1811` both tell the user to "copy `.env.example`". **There is no
  `.env.example` in the repo** (`git ls-files | grep env.example` → only `templates/env.example.j2`).
  The template is rendered into a *project* by `/curate-init`, not shipped at the plugin root.
- `templates/env.example.j2:25` declares `FDH_API=` bare — it does not show the required JSON
  `{"name": "token"}` shape that `submit.py:1290` and `fdh_api.py:182` both demand.
- `submit.py:41` (docstring) says "Review the data on FairDOMHub, then publish manually via the web
  UI" — stale relative to Step 6, which publishes every asset programmatically.
- The command's flow line (`fdh-upload.md:24`) does list "Publish", but says nothing about what it
  does (batch policy change to public across every study asset).
- Test coverage is one smoke test: `tests/test_fdh_upload_help.py` asserts `--help` exits 0 and
  mentions `--resume` and `--step`. No behavioural coverage of any step.

---

## 2. `commands/fdh-api.md` — reuse-or-generate FDH API scripts

### 2.1 Argument parsing (`fdh-api.md:9-12`)

| `$ARGUMENTS` | route |
|---|---|
| `refresh-index` | regenerate the API index |
| `list` | print the generated-script registry |
| anything else / empty | natural-language task → the reuse-or-generate loop |

### 2.2 Exact invocation lines the command specifies

- `fdh-api.md:31` — `uv run --script <PLUGIN>/scripts/fdh/build_api_index.py`, "then show the diff
  of `context/fdh_api_index.json`".
- `fdh-api.md:33` — `list`: "print the `REGISTRY.md` table" (a Read, not a script).
- The loop's own steps are Read operations plus a Write, not script invocations:
  - `:16-17` Read `<PLUGIN>/scripts/fdh/generated/REGISTRY.md`
  - `:18-19` Read `<PLUGIN>/context/fdh_api_index.json`
  - `:20-22` Read `<PLUGIN>/context/full-fdh-openapi-spec.yaml` at the entry's `yaml_lines` range
  - `:22-26` Write a PEP 723 script under `<PLUGIN>/scripts/fdh/generated/`
  - `:27` Add a `REGISTRY.md` row, show the diff, commit on approval

### 2.3 Inputs by exact filename (all present, all in `context/`)

| file | size | produced by |
|---|---|---|
| `context/fdh_api_index.json` | 50,198 B | `scripts/fdh/build_api_index.py` |
| `context/full-fdh-openapi-spec.yaml` | 640,626 B | vendored |
| `context/min_api_endpoints_enriched.json` | 11,657 B | vendored (the shape `build_api_index.py:7-8` mirrors) |
| `scripts/fdh/generated/REGISTRY.md` | 488 B | hand-maintained |

`scripts/fdh/build_api_index.py:22-24` anchors `REPO = Path(__file__).resolve().parents[2]` and
writes `REPO/context/fdh_api_index.json`, i.e. **into the plugin checkout**, not the project.
Deps: `pyyaml>=6.0` (`:1-4`). It scans the YAML for 2-space path headers and 4-space method headers
(`_PATH_RE`/`_METHOD_RE`, `:29-31`), computes `yaml_lines` back-pointers (`compute_ranges`, `:55-62`),
and derives `category` (`categorize`, `:84-106`) and `intent_patterns` (`_INTENTS`, `:109-116`).

### 2.4 `scripts/fdh/fdh_api.py` — the shared client and read-only CLI

Deps: `requests>=2.31` (`:1-4`). `DEFAULT_BASE_URL = "https://fairdomhub.org"` (`:34`), overridable
by `--base-url` or `FDH_BASE_URL` (`make_client`, `:198-201`).

**Auth resolution order (`_resolve_token`, `fdh_api.py:172-195`):** `--token` → `$FDH_TOKEN` →
`$FDH_API` JSON map. With multiple users in the map and no `--user`, it exits 2 (`:194-195`). `.env`
is loaded from `Path.cwd()/.env` then `REPO/.env` with `setdefault` semantics (`_load_dotenv`,
`:159-169`; `REPO = parents[2]` at `:33`). Header is `Authorization: Token <token>` (`:57`).

**Complete CLI (`build_parser`, `fdh_api.py:234-274`) — read-only, five subcommands:**

```
uv run --script scripts/fdh/fdh_api.py whoami
uv run --script scripts/fdh/fdh_api.py search "<query>" [--type <resource_type>]
uv run --script scripts/fdh/fdh_api.py get <resource_type> <id>
uv run --script scripts/fdh/fdh_api.py list <resource_type> <id> <relationship>
uv run --script scripts/fdh/fdh_api.py download-blob <url> --out <path>
```

Common flags on every subcommand: `--token`, `--user`, `--base-url` (`:236-239`).
There is **no `--write`, no `--dry-run`, and no mutating subcommand in this CLI** — writes exist only
as library methods `post` / `patch` / `delete` (`:147-155`), explicitly labelled
"used by generated scripts, never by this read CLI" (`:146`). Transient `429/502/503` are retried
with exponential backoff, max 5 attempts (`RETRY_STATUS` `:35`, `_request` `:69-89`).

### 2.5 The `--write` guard the command promises

`fdh-api.md:25-26` and `:37-38` require generated scripts to default to a dry-run preview and demand
`--write` plus explicit confirmation. That guard exists **only as a template in prose**
(`skills/curation/FDH.md:50-101`, with `p.add_argument("--write", ...)` at `FDH.md:75-76` and the
`DRY-RUN — pass --write` print at `FDH.md:84`). Nothing in the codebase enforces it: there is no
lint, no test, and no shared helper. It is a convention the generating agent must honour.

### 2.6 The load-bearing defect in this command's step 1

`scripts/fdh/generated/*.py` is **gitignored** — `.gitignore:156`, confirmed by
`git check-ignore -v scripts/fdh/generated/foo.py`. In this worktree `scripts/fdh/generated/` contains
only `__init__.py` (0 B) and `REGISTRY.md`, and `REGISTRY.md:10` reads `| _(none yet)_ | | | | |`.

The user's live main tree at `/home/cdemurjian/code/dmac/curation_skill/scripts/fdh/generated/` holds
seven untracked scripts — `audit_project_policies.py`, `delete_samples_by_id.py`,
`delete_samples_by_uid.py`, `find_study_protocols.py`, `find_study_sample_ids.py`,
`patch_sample_links.py`, `set_project_asset_visibility.py` — and a 2,566-byte `REGISTRY.md`
(uncommitted, per the session brief).

Consequence: **for any user who installs this plugin, step 1 of the reuse-or-generate loop
("Check the library first") is guaranteed to find an empty library**, and step 5 ("commit on
approval") cannot commit the script it just wrote because the path is ignored. The registry row
survives the ignore rule (`REGISTRY.md` is not `*.py`), so a shipped registry would point at scripts
that do not exist. This is a design property of `.gitignore:156`, not a stale-file accident.

Structural test coverage only: `tests/test_fdh_scaffold.py:22-24` asserts
`scripts/fdh/generated/__init__.py` exists. `tests/test_fdh_api_cli.py` covers the read CLI.

### 2.7 Minor drift

`fdh-api.md:23-24` says a generated script "imports `FairDomHubClient` from `../fdh_api.py`", while
`skills/curation/FDH.md:41` and the template say `from fdh_api import FairDomHubClient` after adding
`scripts/fdh/` to `sys.path`. The second is the one that actually works.

---

## 3. `commands/curate-sampletype.md` — schema mode

### 3.1 Shape

- Parse `$ARGUMENTS` for a sample type short code, e.g. `D.VIA`; if absent **ask, do not guess**
  (`:8-9`).
- Hard instruction: **Load `skills/curation/SCHEMA.md` before starting** (`:11`).
- State scope (`:15-18`): cwd-scoped. Plugin `context/` is read-only. All artifacts go to
  `./schema/`. No lockfile, no scaffold, no project — "This works from anywhere."
- Default mode never writes (`:20-26`): never writes to NExtSEEK, never edits `sampletypes_db.json`.
  The single exception is the `apply` verb.

### 3.2 The read-only loop (`curate-sampletype.md:165-237`)

Every step names a **Python function**, not a CLI. **None of `scripts/schema/*.py` has a
`__main__` block** (verified: `grep -rn '__main__' scripts/schema/` → no matches), and neither the
command nor `skills/curation/SCHEMA.md` contains a single `uv run`, `python`, `import` or `sys.path`
line (verified by grep over both). The read-only half of schema mode therefore has **no documented
invocation mechanism at all** — the agent must import the modules itself.

| step | module + function | notes verified in source |
|---|---|---|
| 1 read current def | `scripts/schema/field_index.py` `load_catalog()`, `type_record(catalog, TYPE)` | `load_catalog` defaults to `plugin_context("sampletypes_db.json")` = `<plugin>/context/sampletypes_db.json` (`field_index.py:59-61`, `_config.py:40-42`) |
| 2 evidence: producing assay | `context/assays_db.json` (269,414 B, present) | |
| 2 evidence: siblings | `siblings_in_clade(catalog, TYPE)` (`field_index.py:71-79`) | matches on the `Clade` key |
| 2 evidence: observed values | `scripts/schema/dictionary.py` `observe_values()` (`:34`) over `previous_metadata/*.xlsx` in cwd | strips `*** PLACEHOLDER` markers (`dictionary.py:31`) |
| 2 evidence: external clade | `scripts/schema/terms.py` `search_terms(..., ontologies=("OBI",))` then `clade_neighbors(hit)` | **returns `[]` and makes no network call without `BIOPORTAL_API_KEY`** (`terms.py:98`, `:156`). Default ontologies otherwise are `NCIT, OBI, EFO, UBERON, CL` (`terms.py:36`) |
| 2 evidence: template checklist | `scripts/schema/templates.py` `template_fields(REFERENCE_TEMPLATES["common assay template"])` | pinned by `@id` to `https://repo.metadatacenter.org/templates/303429bb-b7a8-4cbe-b4e2-8c3be6b95f5c` (`templates.py:53-55`); **returns `[]` with no network call without `CEDAR_API_KEY`** (`templates.py:121-123`), and swallows every exception into `[]` (`:129-132`) |
| 4 reuse check | `rank_candidates(name, index, clade=, assay=, catalog=)` (`field_index.py:120`) | `Candidate.match_pass ∈ {exact, normalized, synonym, semantic}` (`field_index.py:54`) |
| 5 controlled values | `scripts/schema/ontology.py` `propose_values()` (`:56`) | source precedence, strongest last: `tags(0) < sibling(1) < bioportal(2) < observed(3)` (`ontology.py:35`) |

**Outputs — all into `./schema/` (`OUTPUT_SUBDIR = "schema"` in every writer):**

| file | writer |
|---|---|
| `schema/<TYPE>.review.md` | `schema/review.py:238-243` `write_review` |
| `schema/<TYPE>.proposed.json` | `schema/review.py:245-250` `write_proposed_record` |
| `schema/<TYPE>.ontology.json` | `schema/ontology.py:110-133` `write_ontology_artifact` (adds `_sources` and `_note` sidecar keys) |
| `schema/field_dictionary.json` | `schema/dictionary.py:154-157` `save_dictionary` (path from `dictionary_path`, `:143-145`) |

`schema/review.py:26-35` enumerates the eight required section headings of the review:
`## Current state`, `## External clade evidence`, `## Reference template checklist`,
`## Proposed additions`, `## Reuse decisions`, `## Controlled vocabularies proposed`,
`## Open questions and placeholders`, `## How to apply`.

`/curate-status` detects schema mode by globbing `schema/*.review.md` (`scripts/status.py:186`).

### 3.3 THE VERB TABLE — `scripts/sampletype_attr.py`

The command documents only two of the script's five verbs. Here is the complete surface, from
`main()` at `sampletype_attr.py:463-524`.

| verb | argparse | arguments / flags | reaches network? | **can write to a live server?** | guards |
|---|---|---|---|---|---|
| `types` | `:487` | none | yes (session login + scrape of `/seek/samples/attributes/`) | **no** | — |
| `list <SAMPLETYPE>` | `:489-491` | positional `sampletype` (numeric id or title, `:162`) | yes (REST `GET /nextseek_api/sample_types/{ident}/`, `:165-169`) | **no** | — |
| `add <SAMPLETYPE>` | `:493-502` | `--title` (**required**), `--type` (default `Text`), `--type-id`, `--pos`, `--required`, `--is-title`, `--apply` | yes | **YES** — `GET /seek/attribute/save/` (`SAVE_PATH`, `:64`; `save()` `:239-251`) | `_validate` (3 checks) + dry-run default + `--apply` + `--yes-production` |
| `remove <SAMPLETYPE>` | `:504-508` | `--title` (**required**), `--apply` | yes | **YES** — `GET /seek/attribute/delete/` (`DELETE_PATH`, `:65`; `delete()` `:253-274`) | **only** the is-title refusal + dry-run default + `--apply` + `--yes-production` |
| `selftest <SAMPLETYPE>` | `:510-515` | `--title` (default `ZZZ_Probe_Attr`), `--type` (default `Text`), `--apply` | yes | **YES** — same save path as `add` (`:449`) | `_validate` + dry-run default + `--apply` + `--yes-production` |

Global flags on the top-level parser (`:473-484`): `--base-url` (default `DEFAULT_BASE_URL`),
`--username`, `--password`, `--yes-production`.

**So three of five verbs write to a live server: `add`, `remove`, `selftest`.**
`commands/curate-sampletype.md` documents `list` (`:61`) and `add` (`:67,75,84`) only. `types`,
`remove` and `selftest` appear nowhere in the command file, nowhere in `skills/curation/SKILL.md`
(refs at `:174,179,181`), nowhere in `commands/curate-qc.md` (refs at `:70,74,89,152,193`), and
nowhere in `README.md` (`:57,97`) or `CHANGELOG.md` (`:18,54`). The only place they are written down
is the script's own usage docstring (`sampletype_attr.py:42-46`), which lists `types`, `list`, `add`,
`add --apply`, `selftest` — and omits `remove`.

### 3.4 Exactly what guards each write

**Guard A — dry-run by default.** Every writing verb returns before sending unless `--apply`:
`cmd_add` `:373-375`, `cmd_remove` `:410-412`, `cmd_selftest` `:444-447`.

**Guard B — the production refusal.** `_confirm_production` (`sampletype_attr.py:290-318`):

```python
if not getattr(args, "apply", False): return          # :298-299
host = args.base_url.split("//", 1)[-1].split("/", 1)[0]
if host not in PRODUCTION_HOSTS: return               # :300-302
if getattr(args, "yes_production", False): return     # :303-304
raise SystemExit("REFUSED: --apply against PRODUCTION ...")
```

- `PRODUCTION_HOSTS = ("nextseek.mit.edu",)` — a **one-element tuple** (`:63`). Any other host,
  including an alias or IP for the same box, silently passes the guard.
- `DEFAULT_BASE_URL = os.environ.get("NEXTSEEK_BASE_URL", "https://nextseek.mit.edu")` (`:62`) —
  **production is the default target**; dev requires `--base-url https://nextseek-dev.mit.edu`
  explicitly. Note that setting `NEXTSEEK_BASE_URL` to a non-production host is enough to disable the
  refusal entirely.
- It is called once generically for **every** subcommand in `main()` at `:519` (which is what covers
  `remove` and `selftest`, neither of which calls it itself), and a second, redundant time inside
  `cmd_add` at `:344`.
- `--yes-production` is stripped from `argv` before parsing (`:469-471`) so it works in any position;
  it is re-attached at `:518`. It is declared on the parser at `:482-484` for `--help` only.
  `curate-sampletype.md:151-152` documents this correctly.

**Guard C — `_validate`, the three re-implemented Rails validations** (`sampletype_attr.py:179-206`),
applied by `add` (`:361`) and `selftest` (`:439`), **not** by `remove`:

1. `validate_attribute_title_unique` — case-insensitive title collision (`:185-191`).
2. `validate_attribute_accessor_names_unique` — `:193-197`. **Note: `accessor = title.lower()` and the
   clash test is the same case-insensitive comparison as check 1, so check 1 always fires first and
   check 2 is unreachable.** The command file's claim of "three client-side guards"
   (`curate-sampletype.md:99`, `:118-121`) is accurate as to code but two of the three are the same
   test.
3. `validate_one_title_attribute_present` — refuses `--is-title` when a title attribute exists
   (`:199-206`).

**Guard D — `remove`'s only content check** (`cmd_remove` `:404-406`): refuses to delete the
attribute flagged `is_title`. There is no uniqueness check, no reconciliation, and — per the
`delete()` docstring (`:253-258`) — **`sampleAttributeDelete` does NOT call `updateSampleType`**, so
existing samples keep the orphaned key in their `json_metadata`.

**Guard E — post-write verification.** `add` re-reads and confirms the attribute is present
(`:383-389`); `remove` re-reads and confirms it is gone (`:416-420`); `selftest` re-reads and reports
PASS/FAIL (`:452-460`).

### 3.5 Auth and prerequisites for `apply`

- `NEXTSEEK_USERNAME` (or legacy `NEXTSEEK_USER`) + `NEXTSEEK_PASSWORD`, from `.env` or
  `--username`/`--password` (`:477-479`, `_client` `:280-287`). `_load_dotenv` walks cwd then every
  parent then `<plugin>/.env` (`:73-90`).
- **The account must be `is_superuser`** — the save endpoint requires it (`:110`, and the login-probe
  error text at `:138-140`). `login()` proves the session by fetching `/seek/samples/attributes/` and
  checking it did not redirect to `/login/` (`:133-141`).
- Reads go over REST with HTTP basic auth **and** the session cookie (`get_sample_type` `:161-172`).

### 3.6 Wire-format facts the command states, all verified

- The numeric attribute-type id travels in the key literally named `sample_attribute_type_title`
  (`build_record` `:230-237`, explained `:220-226`) — matches `curate-sampletype.md:124-126`.
- `id` is omitted entirely for a new attribute; any `id > 0` means update (`:225`, `:230-237`) —
  matches `:127`.
- `sample_controlled_vocab_id` is silently dropped (`IGNORED_ON_WRITE` `:70`, printed as a note at
  `:370-371`) — matches `:128`.
- `delete` coerces ids to `int` because `deleteOneRecord` does `if primarykey > 0` on the raw value
  (`:261-263`).

### 3.7 Command-level argument shape vs. script flags

`curate-sampletype.md:29` gives the slash-command form as
`/curate-sampletype apply <TYPE> --add <FIELD>`. The underlying script has **no `--add` flag**; the
field name goes in `--title` (`:495`), which the command's own step 2-4 examples use correctly
(`:67-69`, `:75-77`, `:84-86`). `--add` exists only at the slash-command layer.

### 3.8 Test coverage

`grep -rn 'sampletype_attr' tests/` → **zero matches**. The three live-server write verbs have **no
automated test of any kind**. `tests/test_curate_sampletype.py` tests the review/ontology renderers
and asserts prose strings in the command file; `tests/test_field_index.py`,
`tests/test_schema_dictionary.py`, `tests/test_schema_ontology.py`, `tests/test_schema_terms.py`,
`tests/test_schema_templates.py` cover the read-only modules.

### 3.9 Internal contradiction in the CEDAR template counts

- `commands/curate-sampletype.md:187-190`: "returns **28** fields, **27** described and **22** bound".
- `skills/curation/SCHEMA.md:153`: "carries **28** fields, **27** described and **22** BAO-bound".
- `scripts/schema/templates.py:17-18`: "carries **25** fields, **24** of them described and **20**
  bound to a BioAssay Ontology branch."

Unresolvable offline (the template is a third-party `bibo:draft` at v0.0.1, read at runtime,
`templates.py:49-51`), and no test pins a count.

### 3.10 Missing from the env template

`templates/env.example.j2` declares `NEXTSEEK_USERNAME`, `NEXTSEEK_PASSWORD`, `NEXTSEEK_TOKEN`,
SMB, NCFTP and `FDH_API`. It has **no `BIOPORTAL_API_KEY` and no `CEDAR_API_KEY`**, the two keys
schema mode's steps 2 and 5 depend on. Both degrade silently to empty rather than erroring
(`terms.py:98`, `templates.py:121-123`), which the command documents at `:185` and `:198-199`.

---

## 4. `commands/curate-report.md` — report mode

### 4.1 Shape

- Parse `$ARGUMENTS` for a format (`GEO`, `SRA`, `PRIDE`) and an input; if either is missing,
  **ask — do not guess a format** (`:8-10`).
- **Load `skills/curation/REPORTS.md` before starting** (`:13`).
- State scope (`:19-21`): input-scoped. Reads a project lockfile when present, for lab and project
  id; runs **without** one from any cwd. All output to `./report/`.

### 4.2 SUPPORTED TARGET REPOSITORIES — exactly three

`curate-report.md:15-17`: "**In:** GEO, SRA, PRIDE. Each has a renderer AND a validator; a format is
not supported without both." Verified on both halves:

| target | renderer | validator | artifact(s) |
|---|---|---|---|
| **GEO** | `render.py:191-193` `_geo` → `render_geo` (`:44-66`) | `validate_artifact.py:251-256` `validate_geo_xlsx` | `report/GEO_filled.xlsx` |
| **SRA** | `render.py:196-198` `_sra` → `render_sra` (`:130-143`) | `validate_artifact.py:259-264` `validate_sra_xlsx` (section defaults to `libraries`) | `report/SRA_metadata_filled.xlsx`, `report/SRA_biosample_filled.xlsx` |
| **PRIDE** | `render.py:201-203` `_pride` → `render_pride` (`:148-186`) | `validate_artifact.py:267-325` `validate_pride_px` | `report/submission.px` |

`RENDERERS = {"GEO": _geo, "SRA": _sra, "PRIDE": _pride}` (`render.py:206`); anything else raises
`UnsupportedFormatError` with the message "A format is not supported until it has a renderer AND a
validator" (`render.py:214-218`).

**Explicitly out of scope: nf-core samplesheets** (`curate-report.md:17-19`) — "a multi-turn
interactive wizard carrying Seqera/Tower launch concerns. Different problem, out of scope."

Template specs, all present in `context/report_templates/`:
`GEO-updated.json` (40,089 B), `SRA.json` (35,121 B), `pride.json` (29,125 B), plus the three xlsx
render templates `GEO_template.xlsx` (364,692 B), `SRA_metadata.xlsx` (55,328 B),
`SRA_biosample.xlsx` (11,805 B).

Per-format sections and required-field counts, read from the JSON:

| format | `schema.sections` | row section (`mapping.py:33`) | default target sampletype (`mapping.py:34`) | starred-required fields |
|---|---|---|---|---|
| GEO | `study, samples, protocols, paired_end_experiments, checksums` | `samples` | `D.SEQ` | study 3/5, samples 8/20, protocols 6/9, paired_end 0/4, checksums 0/3 |
| SRA | `libraries, biosamples` | `libraries` | `D.SEQ` | libraries **0/17**, biosamples 9/27 |
| PRIDE | `project_metadata, file_mapping, sample_metadata` | `sample_metadata` | `D.MSP` | project_metadata 18/28, file_mapping 3/4, sample_metadata 5/9 |

Neither the row-section map nor the default target sampletypes are stated anywhere in
`curate-report.md`; `D.SEQ` appears only inside the illustrative JSON at `:78`.

`validate_artifact.py:83-91` records the verified gap: **SRA's `libraries` section stars nothing**,
so `required_fields()` returns `[]` and `_validate_xlsx` reports `Valid` for any readable workbook.

### 4.3 ACCEPTED INPUT SHAPES — five adapters

`detect_adapter(target)` (`scripts/report/adapters.py:193-205`) dispatches, in this order:

| # | condition in code | adapter | network? |
|---|---|---|---|
| 1 | `isinstance(target, (list, tuple))` (`:195-196`) | `adapt_uids` (`:62-83`) | conditional — see below |
| 2 | `name.upper() == "RETRIEVE.TXT"` (`:199-200`) | `adapt_retrieve_txt` (`:86-90`) | conditional |
| 3 | `"AllMetadata" in name` (`:201-202`) | `adapt_nextseek_workbook` (`:107-125`) | **no** |
| 4 | `suffix == ".xlsx" and name.startswith("Arm") and "_" not in p.stem` (`:203-204`) | `adapt_curated_sheet` (`:128-165`) | **no** |
| 5 | fallback (`:205`) | `adapt_tabular` (`:168-188`) — `.csv` via `csv.DictReader`, else first sheet of the xlsx | **no** |

All five emit `NormalizedInput{samples: [NormalizedSample{sample_type, uid, metadata, parent}]}`
(`adapters.py:35-46`). The command's table at `:49-56` matches this exactly, including the
parenthetical "matches any `Arm*` sheet without an underscore".

Adapter-specific facts the command does not state:
- `adapt_nextseek_workbook` reads **every sheet**; sample type falls back to the sheet name
  (`:113-118`).
- `adapt_curated_sheet` reads the sheet named `Samples` if present, else the first sheet (`:138`);
  parses the `json_metadata` column as JSON and records `_json_metadata_error` on failure rather than
  raising (`:141-149`); backfills `Name` and `Parent` from the denormalized `name`/`parent` columns
  (`:151-153`).
- Lineage is the flat `Parent` key, **semicolon-separated**, walked breadth-first, cycle-safe, bounded
  at `_MAX_LINEAGE_DEPTH = 12` (`adapters.py:32`, `resolve_via_lineage` `:226-256`). Leaf wins.

**The API-backed adapters have no fetcher.** `adapt_uids(uids, *, fetch=None)`: "With no fetcher,
returns no samples" (`adapters.py:66-71`). The command (`:51`) and `skills/curation/REPORTS.md:62`
both name `POST /nextseek_api/admin/samples/retrieve/`, but that route appears **only** in those two
prose lines, in the `adapt_uids` docstring (`adapters.py:63`), and in
`context/min_api_endpoints_enriched.json:3`. **No code in the plugin implements or supplies that
fetch callable** — `scripts/nextseek_api.py` has no `samples/retrieve` route
(grep across `scripts/` returns only the docstring hit). So the UID and `RETRIEVE.TXT` paths return
zero samples unless the operating agent writes the fetcher itself. The same is true of
`enrich.merge_leaf_wins` (caller must produce `extra`) and `protocols.resolve_protocols`
(`fetch_sop=None, fetch_blob=None` by default, `protocols.py:131-133`).

### 4.4 The nine-step chain, and who actually runs it

`curate-report.md:29` claims "Only steps 4 and 6 need you. Everything else is a script."

**No module under `scripts/report/` has a `__main__` block or a CLI** — verified:
`grep -rn '__main__' scripts/report/` matches only `scrub_fixture.py:68` (a fixture-scrubbing
utility, not part of the chain). `skills/curation/REPORTS.md` contains **no** `uv run`, `import`,
`python`, `sys.path`, "driver" or "orchestrator" string (grep over all 174 lines). The one executable
in the chain is `scripts/deposit/geo_build_xlsx.py`, and it is invoked **by `render_geo` itself** via
subprocess:

```python
subprocess.run(["uv", "run", "--script", str(script),
                str(tmp_json), str(template_xlsx), str(out_path)], ...)   # render.py:58-62
```

(`script = <plugin>/scripts/deposit/geo_build_xlsx.py`, `render.py:57`; `_PLUGIN` = `parents[2]` at
`render.py:27`; its own CLI is `JSON TEMPLATE OUTPUT`, `geo_build_xlsx.py:189-194`). It writes and
then unlinks a temporary `report/GEO_filled.render-input.json` (`render.py:55-56`, `:65`).

Everything else in steps 1-3 and 5-9 is a **library function the agent must import and call**:

| step | entry point |
|---|---|
| 1 adapt | `adapters.adapt(target, **kwargs)` (`adapters.py:208-217`) |
| 2 enrich | `enrich.merge_leaf_wins(base, extra)` (`enrich.py:20-48`) |
| 3 protocols | `protocols.resolve_protocols(...)` (`protocols.py:131-198`) |
| 5 validate mapping | `mapping.validate_mapping(mapping, spec, normalized)` (`mapping.py:167-293`), spec from `mapping.load_template_spec(path)` (`:81-131`) |
| 7 apply | `execute.apply_mapping(mapping, spec, normalized, synthesized=)` (`execute.py:86-160`) |
| 8 render | `render.render(report_type, filled, template_dir=, out_dir=)` (`render.py:209-219`) |
| 9 validate artifact | `validate_geo_xlsx` / `validate_sra_xlsx` / `validate_pride_px` |

### 4.5 The mapping spec — directives and validation

`DIRECTIVES = ("source", "via_lineage", "const", "map", "synthesize", "unmapped")` (`mapping.py:27`);
`_PRIMARY_DIRECTIVES = ("source", "const", "synthesize", "unmapped")` — exactly one per field
(`mapping.py:31`, enforced `:226-236`). `via_lineage` and `map` are modifiers on `source`.
The command's directive table (`:91-98`) matches.

`validate_mapping` error codes, all in `mapping.py`: `report_type_mismatch` (`:176-180`),
`row_count_mismatch` (`:188-192`), `unknown_section` (`:200-206`), `unknown_field` (`:209-213`),
`no_directive` (`:215-217`, `:227-230`), `unknown_directive` (`:220-224`),
`conflicting_directives` (`:232-235`), `unmapped_without_reason` (`:240-243`),
`synthesize_in_row_section` (`:245-249`), `source_column_missing` (`:251-256`),
`needs_via_lineage` (`:257-262`), `const_not_in_cv` (`:266-271`),
`map_output_not_in_cv` (`:272-278`), `required_unmapped` (`:280-291`).
The command names only `needs_via_lineage` (`:104`).

Controlled-vocabulary enforcement is narrow. `cv_for_field` (`mapping.py:134-142`) hard-codes
`*single or paired-end` → `["single", "paired-end"]` (`_GEO_LAYOUT_CV`, `:40`) and otherwise consults
`_CV_KEY_FOR_FIELD` (`:44-60`) — eight keys only. **GEO's `*instrument model` is deliberately left as
free text** (`:51-57`), because the vendored `instrument_model_flat` CV was mined from SRA and holds
`NextSeq 500` rather than GEO's `Illumina NextSeq 500`. The command's advice at `:106-107` ("`map`
matters… `Illumina NextSeq 500` not `NextSeq 500`") is therefore *unenforced* by the validator for
that field.

The mapping example at `curate-report.md:74-88` uses only real GEO field names — `study` has
`*title`, `*summary (abstract)`, `*experimental design`, `contributor`, `supplementary file`;
`samples` has `*library name`, `**tissue`, `*instrument model`, `*single or paired-end`,
`processed data file` among its 20 keys. The example would pass `validate_mapping`'s
`unknown_field` check.

### 4.6 Execution and degradation

`execute.apply_mapping` (`execute.py:86-160`):
- Row scope = `mapping["row_scope"]["target_sampletype"]` else `TARGET_SAMPLETYPE[report_type]`
  (`:102-106`).
- Unfillable → `*** PLACEHOLDER: <what> ***` via `_common.placeholder` (`_common.py:36-38`), plus a
  `Gap` record (`execute.py:45-53`, `_fill_row` `:56-83`). Never fabricates, never aborts.
- `synthesize` outside the row section: text supplied by the agent, else a placeholder + a Gap
  (`:128-139`).
- **Row parity is asserted**: `RowParityError` when `expected_rows` ≠ produced
  (`:41-42`, `:153-159`) — "Refusing to emit a partial artifact."

### 4.7 Outputs by exact filename, all under `./report/`

| file | written by |
|---|---|
| `report/<FORMAT>.mapping.json` | **nobody — the agent writes it by hand.** No `load_mapping`/`write_mapping` exists in `scripts/report/`; the only other reference is `scripts/status.py:187`, which globs `report/*.mapping.json` to report mode state, and `tests/test_status.py:67` |
| `report/<FORMAT>_filled.json` | `execute.write_filled` (`execute.py:163-167`) — `GEO_filled.json`, `SRA_filled.json`, `PRIDE_filled.json` |
| `report/<FORMAT>.completeness.md` | `execute.write_completeness` (`execute.py:225-229`), content from `render_completeness` (`:170-222`) |
| `report/GEO_filled.xlsx` | `render.py:192-193` |
| `report/SRA_metadata_filled.xlsx`, `report/SRA_biosample_filled.xlsx` | `render.py:136-142` |
| `report/submission.px` | `render.py:202-203` |

The command's output block (`:132-140`) matches, except it writes `<FORMAT>_filled.xlsx  GEO` where
the actual name is `GEO_filled.xlsx`, and it omits `SRA_filled.json` / `PRIDE_filled.json`.

### 4.8 Validator dispositions

`ArtifactStatus` → `DISPOSITION` (`validate_artifact.py:35-50`):
`Valid → CLEAN`, `Incomplete → SOFT_FLAG`, `SchemaInvalid → HARD_REJECT`, `Missing → HARD_REJECT`,
`Unreadable → HARD_REJECT`. The command states CLEAN / SOFT_FLAG / HARD_REJECT at `:128` and
"a `SOFT_FLAG` is not a pass" at `:154`.
For PRIDE the check is line-prefix based: unknown prefix or no `MTD` → `SchemaInvalid`; no `SME` →
`Incomplete` (`validate_artifact.py:300-313`). Prefixes come from `pride.json`'s
`format.line_prefixes`: `MTD/FMH/FME/SMH/SME/COM`.

### 4.9 Prerequisites and auth

None are mandatory. Report mode has **no auth requirement** on any of its three no-network adapters,
its mapping validator, its executor, its renderers or its validators. NExtSEEK/FDH credentials matter
only if the agent supplies a fetcher for `adapt_uids` / `enrich` / `resolve_protocols`. Protocol
resolution redirects `fairdata.mit.edu` refs to `NEXTSEEK_BASE_URL`; only `fairdomhub.org` goes
off-host, and it needs `FDH_API` as a bearer token with **no fallback**
(`protocols.py:10-12`, `resolve_host` `:75-90`). PDF extraction needs `PyPDF2` and raises
`PdfSupportError` when absent rather than silently returning empty text (`protocols.py:104-117`).

### 4.10 Relationship to `/curate-deposit geo`

`curate-report.md:156-160`: Phase 10 delegates its build step here and keeps only external upload and
accession backfill; GEO deposit happens **before** NExtSEEK upload. Consistent with
`adapt_curated_sheet`'s docstring (`adapters.py:129-133`) and with `render_geo` delegating to
`scripts/deposit/geo_build_xlsx.py`. Cross-check: `tests/test_deposit_delegates_geo.py` exists.

---

## 5. Cross-cutting, for the fixer

1. **`/curate-sampletype` under-documents the live-write surface.** Three of five verbs write;
   two of those three (`remove`, `selftest`) are undocumented everywhere outside the script, and
   `remove` runs with only one content guard and no `updateSampleType` reconciliation. Zero tests.
2. **`/fdh-api`'s reuse loop cannot work as shipped** — `.gitignore:156` ignores every generated
   script, so the library step 1 reads is empty for every installed copy.
3. **"Everything else is a script" is false for report mode and for schema mode's read-only loop.**
   Both are import-only libraries with no CLI and no documented invocation path. The only executables
   are `scripts/deposit/geo_build_xlsx.py` (called by `render_geo`, not by the agent) and
   `scripts/sampletype_attr.py`.
4. **The UID / `RETRIEVE.TXT` adapters are documented as API-backed but ship no fetcher**, so two of
   the five documented input shapes yield zero rows out of the box.
5. Adjacent, outside these four commands: `scripts/status.py:183-188` enumerates only four modes
   (`pipeline`, `fdh`, `schema`, `report`). The newly registered fifth mode `assay` is absent from
   `/curate-status`.
