# Ground-truth inventory: repo furniture

Worktree: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`
Branch `dev-docs`, HEAD `833e9bee85c22cb89ca399409187bb2cfcb9faf5` (2026-08-27 16:55:34 -0400).
`git status --short` is **clean** — nothing uncommitted in this worktree.

Every claim below was verified by reading the file named. Counts:
26 `commands/*.md`, 6 `skills/curation/*.md`, 86 `scripts/**/*.py`
(39 of them under `scripts/assay_hygiene/`), 10 `templates/*.j2`,
17 files under `context/`, 88 `tests/test_*.py` + `tests/conftest.py` +
`tests/test_e2e_init.sh`, 31 `docs/**/*.md`.

---

## 1. Versions, verbatim

| file | field | verbatim value |
|---|---|---|
| `.claude-plugin/plugin.json:3` | `version` | `"0.4.0"` |
| `.claude-plugin/marketplace.json:15` | `version` | `"0.4.0"` |
| `scripts/_lockfile.py:29` | `PLUGIN_VERSION` | `"0.4.0"` |
| `README.md:7` | status line | `**Status:** v0.3.0` |
| `CHANGELOG.md:5` | latest heading | `## 0.4.0 - 2026-07-31` |
| `pyproject.toml:3` | `version` | `version = "0.3.0"` |

`tests/test_identity_sync.py:90-96` asserts plugin.json == marketplace.json ==
`_lockfile.PLUGIN_VERSION` and pins the value to the literal `"0.4.0"`.
**Nothing asserts `README.md` or `pyproject.toml`**, and both are stranded at
`0.3.0`. The CHANGELOG's newest entry is dated 2026-07-31; everything from
2026-08-04 onward (init auto-detect, the entire assay-hygiene programme, the
schema-mode OBI/CEDAR work, dependency pinning) is unrecorded.

### The `description` field, verbatim (identical in both manifests)

`.claude-plugin/plugin.json:4` and `.claude-plugin/marketplace.json:8`:

> `Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts). Activate when working in a directory containing files/, manuscript/, previous_metadata/, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, or a GEO/SRA/PRIDE submission.`

`.claude-plugin/marketplace.json:6` `metadata.description`, verbatim:

> `Charlie Demurjian's personal Claude Code marketplace (DMAC tooling).`

**The canonical description names four modes and omits `assay`.** It is byte-pinned
in three places by `tests/test_identity_sync.py:16-28` (`CANONICAL_DESCRIPTION`) and
re-asserted against `skills/curation/SKILL.md:3` frontmatter. `test_description_names_every_mode`
(`tests/test_identity_sync.py:99-101`) iterates only
`("pipeline", "fdh", "schema", "report")` — the test itself was not updated when
`assay` was registered in commit `eb8777e`. Skill activation matches on this string,
so nothing in the activation surface mentions assay hygiene.

---

## 2. `context/` — every file, provenance, and who reads it

`context/PROVENANCE.json` (6,569 B) is the per-file record: `source_repo`,
`source_path`, `commit_sha`, `vendored_date`, `local_divergence`, `sha256`.
`context/VINTAGE.json` (3,445 B) is the bundle-level record: `bundled_date`
`2026-07-22`, source `chat_nextseek` commit `367d72732da3ffcc099a367b0ff6f87eaea0bed7`.

Eleven of the seventeen files carry a PROVENANCE entry. Six do **not**:
`fdh_api_index.json`, `full-fdh-openapi-spec.yaml`, `min_api_endpoints_enriched.json`,
`NExtSEEK_API.yaml`, `PROVENANCE.json` itself, `VINTAGE.json` itself. VINTAGE.json
labels the first four "hand-maintained; not auto-refreshed".

| file | bytes | vintage / provenance | read by |
|---|---|---|---|
| `assays_db.json` | 269,414 | chat_nextseek `367d727…`, vendored 2026-07-22, divergence `none`, sha256 `c8a7ebaf…`. VINTAGE: PRODUCTION, **217 assays** | `scripts/build_sample_tree_html.py:72` (`ASSAYS_DB`), `commands/curate-sample-tree.md:73`, `commands/curate-sampletype.md:173`, `skills/curation/PHASES.md:143`; refresh-managed at `scripts/refresh_context.py:42` |
| `sampletypes_db.json` | 129,051 | same commit/date, divergence `none`, sha256 `58ec12d1…`. VINTAGE: PRODUCTION, **101 sample types** | `scripts/_common.py:154`, `scripts/qa_flat_sheets.py:90` (project-local copy wins), `scripts/schema/field_index.py:61`, `scripts/_config.py:41`; `scripts/refresh_context.py:41` |
| `neo4j_schema.json` | 17,965 | same commit/date, sha256 `5aa69f43…`. VINTAGE: **PRODUCTION (nextseek.mit.edu), fetched_at 2026-05-11, 85 Sample properties**. VINTAGE carries a `neo4j_schema_vintages_seen` block warning against "upgrading" to a 200-property dump that the live system does not load | `scripts/refresh_context.py:44,153`. **No runtime script reads it** — it is reference material for the model |
| `neo4j_assay-sample-conn.json` | 17,915 | same commit/date, sha256 `2550143a…`. VINTAGE: PRODUCTION, fetched_at 2026-05-11, **163 allowed (assay, parent_type, child_type) edges**, wrapper `{fetched_at, connections}` | `scripts/build_sample_tree_html.py:73` (`CONN_DB`), `commands/curate-sample-tree.md:84`; `scripts/refresh_context.py:45,154` |
| `projects_db.json` | 7,297 | same commit/date, sha256 `110da7b4…`. VINTAGE: **10 projects** (Break Through Cancer, CSBC, GBM, Griffith, Impact, MetNet, PUBLISHED, RMS-NGC, Shoulders, SRP) | **no reader at all** outside `scripts/refresh_context.py:43` and `tests/test_refresh_context.py:19` |
| `NExtSEEK_API.yaml` | 278,299 | **no PROVENANCE entry.** VINTAGE: "hand-maintained; not auto-refreshed", bundled 2026-05-27 | prose-only: `skills/curation/PHASES.md:275,300`, `skills/curation/SCHEMA.md:106`. VINTAGE's `note` flags its ontology claim as unconfirmed since 2026-05-27 |
| `full-fdh-openapi-spec.yaml` | 640,626 | **no PROVENANCE entry.** VINTAGE: "640KB; never read whole, use the index" | `scripts/fdh/build_api_index.py:23` (`SPEC`), `commands/fdh-api.md:20`, `skills/curation/FDH.md:32`, `tests/test_build_api_index.py:8`, `tests/test_fdh_scaffold.py:8` |
| `fdh_api_index.json` | 50,198 | **no PROVENANCE entry.** Generated from the spec above | `scripts/fdh/build_api_index.py:24` (`OUT`), `commands/fdh-api.md:18,32`, `skills/curation/SKILL.md:50`, `skills/curation/FDH.md:29`, `tests/test_build_api_index.py:9`, `tests/test_fdh_commands_present.py:11` |
| `min_api_endpoints_enriched.json` | 11,657 | **no PROVENANCE entry.** VINTAGE: 13 enriched endpoint records, hand-maintained | **only** `scripts/fdh/build_api_index.py:8` (a docstring reference — no code path loads it) |
| `report_templates/GEO-updated.json` | 40,089 | `367d727…`, 2026-07-22, sha256 `4ce6bc4c…`; divergence note records it is byte-identical to dmac-assistant's copy, and that chat_nextseek's `geo.json` was deliberately NOT vendored | `commands/curate-report.md:70`; `scripts/report/*`; `tests/test_report_assets.py` |
| `report_templates/GEO_template.xlsx` | 364,692 | `367d727…`, sha256 `7442023e…` | report-mode renderer |
| `report_templates/SRA.json` | 35,121 | `367d727…`, sha256 `b8fc0ed6…`; divergence note: two row-bearing sections, `libraries`→`SRA_metadata.xlsx`, `biosamples`→`SRA_biosample.xlsx` | report-mode renderer |
| `report_templates/SRA_metadata.xlsx` | 55,328 | `367d727…`, sha256 `fad93328…` | renders SRA.json `libraries` |
| `report_templates/SRA_biosample.xlsx` | 11,805 | `367d727…`, sha256 `75508fe2…` | renders SRA.json `biosamples` |
| `report_templates/pride.json` | 29,125 | `367d727…`, sha256 `5508e6ed…`; divergence note: **NOT a spreadsheet** — tab-delimited ProteomeXchange `submission.px` with MTD/FMH/FME/SMH/SME/COM prefixes. No `pride.xlsx` is vendored | report-mode renderer |
| `PROVENANCE.json` | 6,569 | self | `scripts/refresh_context.py:104,111`; `tests/test_refresh_context.py:52,77`, `tests/test_report_assets.py:24`, `tests/test_validate_artifact.py:269` |
| `VINTAGE.json` | 3,445 | self | `commands/curate-init.md:54,150` (writes `bundled_date` into the lockfile), `tests/test_e2e_init.sh:46`, `scripts/refresh_context.py:129,206` |

PROVENANCE.json also records **one non-`context/` entry**: `scripts/report/validate_artifact.py`,
vendored from dmac-assistant `tools/hibayes/artifact_validator.py` at `dcca50c1…`, with a
long `local_divergence` describing it as a SUBSET plus extension (897-line upstream reduced;
SRA/PRIDE added; GEO header row auto-located rather than assumed at row 1).

**`scripts/assay_hygiene/` reads nothing from `context/`.** Grepped: the 39 modules
reference `neo4j` only as the live graph driver and as `neo4j_sync.py` line
cross-references into the NExtSEEK server source. The assay mode's vocabulary is
learned from the production extract (`scripts/assay_hygiene/vocabulary.py:225`,
`_schema.py:46`, `precedent.py:71` all cite `neo4j_sync.py:1418-1431`), not from
`assays_db.json`. So the newest and largest subsystem in the repo bypasses `context/`
entirely — a fact no doc states.

Refresh path (from `VINTAGE.json`, verified against the script):
`uv run --script scripts/refresh_context.py --check` reports staleness;
`--from-dir <DIR> --write` applies. It manages exactly five files
(`scripts/refresh_context.py:41-45`).

---

## 3. `templates/` — what renders each one

All ten are Jinja2. `scripts/_config.py:45-47` exposes `plugin_template(name)` as the
only sanctioned read path; `_config.py:16-19` states plugin paths are read-only and
limited to `context/` and `templates/`.

| template | renders to | rendered by |
|---|---|---|
| `CLAUDE.md.j2` (3,614 B) | `./CLAUDE.md` | `commands/curate-init.md:80`. Mode-aware: line 1 is `{%- set active = modes \| default(['pipeline']) -%}`; the pipeline step list at `:27` is emitted only for pipeline projects |
| `env.example.j2` (682 B) | `./.env.example` | `commands/curate-init.md:81`. Documents `$DMAC_ENV_FILE` (`env.example.j2:2-3`) as the out-of-repo credential source |
| `gitignore.j2` (406 B) | `./.gitignore` | `commands/curate-init.md:82` |
| `pyproject.toml.j2` (256 B) | `./pyproject.toml` | `commands/curate-init.md:83`, with a special case at `:88` |
| `FILE_INDEX.md.j2` (924 B) | `./FILE_INDEX.md` | `commands/curate-inventory.md:20`; `skills/curation/PHASES.md:129` |
| `SAMPLE_TREE.md.j2` (1,014 B) | `./SAMPLE_TREE.md` | `commands/curate-sample-tree.md:78`; `skills/curation/PHASES.md:152` |
| `EMAIL_TO_PI.md.j2` (729 B) | `./EMAIL_TO_PI.md` | `commands/curate-email.md:15`; `skills/curation/PHASES.md:488` |
| `SAMPLE_TREE.html.j2` (18,926 B) | `./SAMPLE_TREE.html` | `scripts/build_sample_tree_html.py:406` — the **only** template rendered by Python rather than by a command doc |
| `QUESTIONS_FOR_PI.md.j2` (496 B) | `./QUESTIONS_FOR_PI.md` | **No file names it.** `commands/curate-questions.md:16` says "or create from template if absent" without naming a path. Only `tests/test_templates_render.py:36` references it by name |
| `CURATION_PLAN.md.j2` (520 B) | *(nothing)* | **Orphan.** Zero references in `commands/`, `skills/`, `scripts/`. Its only mention anywhere is `tests/test_templates_render.py:40` and the 2026-05-27 plan. `CURATION_PLAN.md` appears in no phase table and no status probe |

`tests/test_templates_render.py` smoke-renders nine of the ten under
`jinja2.StrictUndefined` with MINIMAL and WITH_VALUES fixtures.
**`SAMPLE_TREE.html.j2` is in neither dict** — grep for `SAMPLE_TREE.html` under
`tests/` returns nothing. The largest template in the repo (18.9 KB) is untested,
and so is its renderer (§4).

---

## 4. `tests/` — counts, grouping, and the coverage holes

### Suite result (run in this worktree, offline, no network)

```
$ uv run pytest -q
1498 passed, 51 skipped, 3 xfailed in 33.99s     (exit 0)
```

Collection: **1552 tests** across 88 `tests/test_*.py` modules, plus `tests/conftest.py`
and one shell test `tests/test_e2e_init.sh` (not collected by pytest;
`pyproject.toml:22-23` sets `testpaths = ["tests"]`).

51 skips reported on 43 `SKIPPED` lines. By module:

| module | skipped | reason (verbatim from `-rs`) |
|---|---|---|
| `test_report_fixtures.py` | 7 | `not harvested yet` / `report_metadata.json not harvested yet; see tests/fixtures/nextseek/README.md` |
| `test_assay_hygiene_rulings.py` | 7 | `no extract; nothing to run the detector over` |
| `test_assay_hygiene_review_mode2.py` | 7 | no extract |
| `test_identifier_exposure.py` | 4 | `no extract; the pattern-only tiers still ran` |
| `test_assay_hygiene_review.py` | 3 | `no extract or findings; run run_detect.py first` |
| `test_no_plaintext_secrets.py` | 2 | `no working/ directory` |
| `test_assay_hygiene_{validation_sample,run_detect,lineage,compatibility,classify}.py` | 2 each | `no extract at …/assay-hygiene/extract; run driver_extract.py first` |
| `test_assay_hygiene_{precedent,gate,backtest}.py` | 1 each | no extract |

Every one of these is a *by-design* skip: the fixtures carry real sample identifiers
and this repository is PUBLIC (`.gitignore:87-96,105-112`), so a fresh clone and CI
always skip them. `tests/conftest.py:104-120` documents exactly this and installs a
skipped-measurement banner, because "a run with all 24 of them skipped therefore
reports FULLY GREEN while having measured nothing at all" — a `1196 passed / 16 skipped`
baseline was read as healthy for days while 21 tests silently skipped.
**A green suite in this worktree is not evidence the assay pipeline was measured.**

### Grouping (88 modules)

- **assay-hygiene, 44 modules** (`test_assay_hygiene_*.py`), the largest by far —
  `classify` (80 tests), `stage0` (61), `validation_sample` (51), `schema` (45),
  `extract` (45), `review_mode2` (44), `stage0_apply` (42), `review` (34), down to
  `missing_inputs` (2). Includes the mode-command contract test
  `test_assay_hygiene_commands.py` (8 command docs × 3 checks + 3 structural) and the
  end-to-end `test_assay_hygiene_workflow.py`.
- **report mode, 8**: `adapters`, `enrich`(via `protocols`), `execute`, `mapping`,
  `protocols`, `render`, `fixtures`, `assets`, plus `test_validate_artifact.py`,
  `test_curate_report.py`.
- **schema mode, 5**: `test_schema_{dictionary,ontology,templates,terms}.py`,
  `test_field_index.py`, `test_curate_sampletype.py`.
- **fdh mode, 6**: `test_fdh_{api_cli,commands_present,reference_docs,scaffold,upload_help}.py`,
  `test_build_api_index.py`.
- **pipeline scripts, ~10**: `test_flat_pipeline_cli.py`, `test_review_metadata.py`,
  `test_deposit_{delegates_geo,scripts_help,write_safety}.py`, `test_file_ops_cli.py`,
  `test_inspect_workbook.py`, `test_smb_pull_cli.py`, `test_nextseek_api_{cli,detect}.py`,
  `test_detect_context.py`.
- **repo hygiene / meta, ~12**: `test_identity_sync.py`, `test_mode_table.py`,
  `test_phases_doc.py`, `test_curate_commands_present.py`, `test_templates_render.py`,
  `test_path_anchoring.py`, `test_no_plaintext_secrets.py`, `test_identifier_exposure.py`,
  `test_dependency_pinning.py`, `test_conftest_banner.py`, `test_refresh_context.py`,
  `test_report_assets.py`, `test_init_additive.py`, `test_lockfile.py`, `test_config.py`,
  `test_common.py`, `test_status.py`.

`tests/conftest.py` ships two fixtures: `plugin_sentinel` (the P1 guard — sha256-snapshots
the whole checkout before and after a test and fails on any create/modify/delete inside it,
`conftest.py:68-88`) and `curation_project` (a minimal scaffold + v1 lockfile;
note `conftest.py:98` hardcodes `"plugin_version": "0.3.0"` in that fixture).

Fixtures on disk: `tests/fixtures/sample.xlsx` and `tests/fixtures/nextseek/README.md`
(a *procedure*, not data — it explains that the NExtSEEK API fixtures must be **harvested**
from `~/.local/state/chat_nextseek/outputs/`, never hand-authored, because the retrieve
response is nested five levels and lineage is a flat upward `Parent` UID pointer).

### Scripts with NO test coverage

Verified by grepping every script stem across `tests/`. Five files have **zero** hits:

| script | what it is | why the gap matters |
|---|---|---|
| `scripts/sampletype_attr.py` | drives NExtSEEK's native attribute editor via `GET /seek/attribute/save/`; `--apply` writes, production needs `--yes-production`. **It writes to a live server.** | The headline feature of CHANGELOG 0.4.0, and the only sanctioned schema write path. `tests/test_curate_commands_present.py` does not contract it |
| `scripts/build_sample_tree_html.py` | renders `templates/SAMPLE_TREE.html.j2` from `sample_tree.json`; reconciles `assays_db.json` against `neo4j_assay-sample-conn.json` (`:239-294`) | Phase 2's interactive artifact. Both the renderer and its 18.9 KB template are untested |
| `scripts/stamp_guard.py` | pre-mint UID-collision guard for `/curate-build`; `require_fresh_db_pull` + `guard_stamp` | Its own docstring calls it the "root-cause fix for the UID-stamp collision class of bug… the upload silently OVERWRITES the other study's records" |
| `scripts/assay_hygiene/review_verdicts.py` | the 1,012-cohort verdict review sheet (reasons lead, evidence folded) | The surface the operator actually reads at scale |
| `scripts/remeasure_post_stage0.py` | re-derives every A–F statistic against the post-stage-0 graph | Read-only measurement; the anchors other docs quote come from here |

Thinly covered (exactly one test file mentions the stem): `assay_hygiene/chunker.py`,
`assay_hygiene/migrate_rulings.py`, `assay_hygiene/registration_payload.py`,
`assay_hygiene/store_backup.py`, `detect_context.py`, `inspect_workbook.py`,
`measure_metadata_accuracy.py`, `omero_pull.py`, `rename_files.py`.

---

## 5. `pyproject.toml`

```toml
[project]
name = "dmac-curation"
version = "0.3.0"
requires-python = ">=3.11"
dependencies = ["pandas>=2.0", "pyarrow>=14.0", "openpyxl>=3.1", "jinja2>=3.1",
                "requests>=2.31", "pyyaml>=6.0", "python-dotenv>=1.0", "smbprotocol>=1.10"]
[dependency-groups]
dev = ["pytest>=8.0", "numpy>=1.26"]
[tool.pytest.ini_options]
testpaths = ["tests"]
```

Two live inconsistencies:

1. `version = "0.3.0"` while every other version marker says `0.4.0` (§1).
2. Commit `693f57e` is titled *"build: pin dependencies instead of lower-bounding them"*,
   but `pyproject.toml:5-7` says the opposite in a comment — "Floors are what the
   PEP-723 headers already declared; uv.lock records what was actually resolved…
   the lock is the reproducibility guarantee, not these bounds." **The bounds are
   floors, not pins.** `tests/test_dependency_pinning.py` (4 tests) only checks that
   `pyproject.toml` and `uv.lock` exist, that five package names appear in the
   dependency string, and that `name = "pandas"` appears in the lock — it never
   asserts an upper bound. `uv.lock` (217 KB) is deliberately tracked
   (`.gitignore:37-41`).

**`neo4j` is imported but declared nowhere** — not in `pyproject.toml`, not in
`uv.lock` (`grep -c 'name = "neo4j"' uv.lock` → 0), and not in any PEP 723 header
(`scripts/assay_hygiene/extract.py:1-4` declares only `pandas`/`pyarrow`;
`stage0_apply.py:1-4` only `pandas`). The three import sites —
`extract.py:308`, `stage0_apply.py:300` (inside a heredoc doc-block for
`ssh fairdata 'docker exec -i nextseek uv run manage.py shell'`), and
`driver_stage0.py:30` — all execute **inside the production container**, whose
environment supplies the driver. Correct by design, documented nowhere.

---

## 6. `.gitignore` — exclusion classes and why

5,350 bytes, unusually heavily commented; the comments are the rationale record and are
worth reading before touching it.

| class | patterns | stated reason |
|---|---|---|
| Secrets | `.env`, `*.env`, `*_token*`, `*_secret*`, `*_password*`, `*.key/pem/p12/pfx/crt`, `credentials*`, `secrets*`, `.netrc`, `.smbcreds`, `*.kdbx` | plus **negations** `!tests/test_*.py` etc. — without them `git add tests/test_no_plaintext_secrets.py` is silently refused (it matches `*_secret*`) and the guard vanishes from a fresh clone |
| Python / build | `__pycache__/`, `*.py[cod]`, `.venv/`, `build/`, `dist/`, `*.egg-info/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` | standard. A comment block explicitly records that **`uv.lock` is deliberately TRACKED** because `tests/test_dependency_pinning.py` asserts its presence |
| Editors / OS | `.vscode/`, `.idea/`, `*.sw[po]`, `.DS_Store`, `Thumbs.db` | standard |
| Curation-project artifacts | `Assets/Output/`, `GEO/`, `Zenodo_upload/`, `omero_images.csv`, `manifest.csv`, `RETRIEVE.TXT`, `*-upload-new.xlsx`, `*_AllMetadata*.xlsx`, `rclone.log`, `pull.log` | only relevant if the plugin checkout is accidentally used as a curation working dir |
| Logs / scratch | `*.log`, `.scratch/`, `scratch/`, `tmp/` | — |
| FDH staging | `working/` | "holds a real `.env` — never commit" |
| Agent scratch | `.worktrees/`, `.superpowers/` | SDD ledgers and briefs |
| Assay-hygiene working dir | `assay-hygiene/`, **`assay-hygiene-*/`** | extract carries "163k rows, 260 MB of real sample metadata". The prefix glob exists because `assay-hygiene-bak/` held 195 MB of the same data matching no pattern, "one `git add -A` away from a PUBLIC repo" |
| Run assets | `assets/` | "a complete curation run… real sample identifiers… already needed a history rewrite on 2026-08-21 to strip 1,570 of them" |
| Rulings / verdicts | **unanchored** `*rulings*.tsv`, `*verdicts*.csv` | scoped to the NAME, not to `tests/fixtures/`, because `mode2-rulings-backup-2026-08-20.tsv` sat untracked and unignored in the repo root on 2026-08-24 |
| Session state | `.claude/` | handoff reports carry protocol and sample identifiers; six were swept into the public repo on 2026-08-25 and the branch was rewritten |
| Generated FDH scripts | `scripts/fdh/generated/*.py` | "written per-task against live project ids and frequently carry sample uids; several are destructive (`delete_samples_*`)" |

Consequence worth stating plainly: **`assay-hygiene/`, `assets/` and `working/` are
absent from this worktree and that is correct.** The 51 skips in §4 follow directly.

Note on `scripts/fdh/generated/REGISTRY.md:10` — in *this* worktree the directory holds
only `__init__.py` and `REGISTRY.md`, so its `| _(none yet)_ | | | | |` row is accurate
here. The drift (7 generated scripts beside a registry claiming none) exists only in the
main tree, where those `*.py` files are gitignored-but-present; it is already fixed
uncommitted there.

---

## 7. `docs/` — every file, classified

Legend: **(a)** living reference · **(b)** historical design spec · **(c)** plan · **(d)** point-in-time finding

| file | lines | one line | class |
|---|---|---|---|
| `docs/SECURITY.md` | 80 | Credential-handling rule ("no credential ever lives in a file inside this checkout"), a table of where each credential comes from and which script consumes it, a table of the three places credentials have actually turned up on disk, and how `tests/test_no_plaintext_secrets.py` enforces it | **(a)** |
| `docs/assay-hygiene-increment-2-deferred-minors.md` | 161 | Deferred minors extracted 2026-08-18 from a gitignored SDD ledger before the worktree was torn down; each item found by review, judged real, deliberately not fixed | **(d)** |
| `docs/findings/2026-08-21-assay-143-name-collision.md` | 83 | Internal assay 143 is named "Alanine Aminotransferase (ALT/GPT) Activity Assay" but maps SEEK assay 26 "GPT Assay" — the wrong GPT | **(d)** |
| `docs/findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md` | 371 | Read-only audit of 170,786 findings rows; **explicitly warns that its `assay-hygiene-bak/` paths do not resolve in a clone** | **(d)** |
| `docs/findings/2026-08-21-mode2-lineage-lane-is-ungated.md` | 83 | Mode 2's lineage lane never meets `gate.type_registration_index`, the root cause of 99,449 impossible proposals | **(d)** |
| `docs/findings/2026-08-21-pre-rework-baseline.md` | 95 | The measured row table the rework's deltas are judged against, derived by a committed script | **(d)** |
| `docs/findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md` | 177 | What the chosen NExtSEEK assay API write route actually does, its cost, and the one open question | **(d)** |
| `docs/findings/2026-08-24-the-operators-rulings-against-the-reworked-detector.md` | 143 | The rework is exactly neutral against the operator's 111 hand rulings (100 APPROVE / 6 REJECT / 5 WRONG_ASSAY) | **(d)** |
| `docs/findings/2026-08-25-the-prose-figure-census.md` | 460 | AST+tokenize census of 6,984 numeric literals in `scripts/assay_hygiene/` comments; answers "which figures are trustworthy" | **(d)** |
| `docs/superpowers/specs/2026-05-27-dmac-curation-plugin-design.md` | 340 | Original design: the 13-phase pipeline as a plugin. Status "Draft for review" | **(b)** |
| `docs/superpowers/specs/2026-07-02-fdh-integration-design.md` | 216 | FDH as two standalone modules. Status "Approved for planning" | **(b)** |
| `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md` | 489 | **The architecture doc: what a "mode" is.** Status "proposed" | **(b)**, but the closest thing to a living architecture reference |
| `docs/superpowers/specs/2026-07-21-pipeline-rework-review.md` | 182 | Review verdict: "The pipeline is sound… it needs correcting", exactly two steps don't earn their place | **(b)/(d)** |
| `docs/superpowers/specs/2026-07-21-report-mode-design.md` | 287 | `report` mode design — one declarative mapping spec, O(columns), deterministic execution | **(b)** |
| `docs/superpowers/specs/2026-07-21-schema-mode-design.md` | 264 | `schema` mode design — sample-type authoring, human applies | **(b)** |
| `docs/superpowers/specs/2026-08-04-init-auto-detect-project-lab-design.md` | 119 | Auto-detect project/lab/PI at `/curate-init`. Status "Approved (design), pending implementation plan" — **stale: `scripts/detect_context.py` exists and is tested** | **(b)** |
| `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md` | 1,202 | Assay hygiene v1: complete the lineage graph, then backfill. Status line still says "stage 0 not implemented, stages A-F partially built (Task 1 only)… **Not a plugin mode yet**" — stale | **(b)** |
| `docs/superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md` | 853 | Three equal modes over one evidence layer. Header carries an **amendment warning**: "Do not plan from the sections below without reading that amendment first" | **(b)** |
| `docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` | 312 | Assay hygiene as the fifth curation mode. Line 3: "**Status:** design, approved 2026-08-27, all open questions closed. **Not implemented.**" — **stale; it shipped in `d1f4d14`…`833e9be` the same day.** Line 3 also says "Absorbs: `commands/curate-assay-vocabulary.md`", and that command file still exists (absorbed *into the mode*, not deleted — `64f233d`) | **(b)** |
| `docs/superpowers/plans/2026-05-27-dmac-curation-plugin.md` | 2,738 | SDD plan for the original 13-phase plugin | **(c)** |
| `docs/superpowers/plans/2026-07-02-fdh-integration.md` | 1,248 | SDD plan for the two FDH modules | **(c)** |
| `docs/superpowers/plans/2026-07-21-curation-toolkit.md` | 12,503 | SDD plan for the pipeline→toolkit conversion; **the single largest file in the repo** | **(c)** |
| `docs/superpowers/plans/2026-08-04-init-auto-detect.md` | 650 | SDD plan for `detect_context.py` + `nextseek_api.py detect-context` | **(c)** |
| `docs/superpowers/plans/2026-08-12-assay-hygiene.md` | 1,974 | SDD plan, six-stage assay pipeline | **(c)** |
| `docs/superpowers/plans/2026-08-13-assay-hygiene-stage0.md` | 1,726 | SDD plan, 90,534 `DERIVED_FROM` backfill | **(c)** |
| `docs/superpowers/plans/2026-08-14-assay-hygiene-evidence-layer-and-mode-3.md` | 2,189 | SDD plan, evidence layer + Mode 3 | **(c)** |
| `docs/superpowers/plans/2026-08-17-assay-hygiene-mode-1-and-2-detection.md` | 640 | SDD plan, vocabulary gate + Modes 1/2 detection | **(c)** |
| `docs/superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md` | 738 | SDD plan, stop the 99,449 unreachable proposals without deleting the 2,035 real ones | **(c)** |
| `docs/superpowers/plans/2026-08-27-assay-hygiene-prerequisites.md` | 794 | SDD plan, four defects that would let run 2 destroy run 1's evidence | **(c)** |
| `docs/superpowers/plans/2026-08-27-assay-hygiene-ruling-store.md` | 657 | SDD plan, the durable cross-run ruling store | **(c)** |
| `docs/superpowers/plans/2026-08-27-assay-hygiene-mode-commands.md` | 2,760 | SDD plan, the eight `curate-assay-*` commands | **(c)** |

Totals: 31 files, 34,534 lines. **1 living reference (a), 10 specs (b), 12 plans (c),
8 findings (d).** There is no `docs/README.md`, no index, and no file that states which
of the three overlapping assay-hygiene designs is current.

### What a new contributor should read

Only these, in order:

1. `README.md` — layout and commands *(but see §1: it self-declares v0.3.0 and knows four modes)*
2. `skills/curation/SKILL.md` — the mode table at `:29-35` is the one place all five modes are listed
3. `docs/SECURITY.md` — the only living reference doc under `docs/`, and mandatory before touching credentials or `working/`
4. `.gitignore` — read the comments; they are the incident record for a PUBLIC repo that has already needed one history rewrite
5. `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md` — what a "mode" is, why nothing is registered in `plugin.json`
6. `context/VINTAGE.json` + `context/PROVENANCE.json` — before trusting any bundled snapshot
7. `tests/conftest.py:104-120` — why a green suite may have measured nothing

**Do not read as current:** the twelve `plans/` (execution records, several with
superseded figures), and the three assay-hygiene specs, which contradict each other
by design — `2026-08-14` carries an explicit "do not plan from the sections below"
banner, `2026-08-12` still says "Not a plugin mode yet", and `2026-08-27` still says
"Not implemented" after it shipped.

---

## 8. Recent history — what the docs most likely missed

40 commits, **35 of them dated 2026-08-27**, the remaining five 2026-08-25/26.
This is one dense day of work landing three SDD plans back-to-back.

Sequence (oldest → newest of the 40):

1. **2026-08-25/26 — identifier hygiene.** `1ec9adf`, `5c93ce5` (registration payload
   "built so it cannot delete"), `572e844`, `c8baf9b` (ratchet the identifiers this
   PUBLIC repo already exposes), `1ec4c2b` (stale-figure re-derivation), `6e9badd`
   ("remove every real identifier from tracked files, and close two scan holes").
2. **Design + prerequisites.** `69aa4c7` designs assay hygiene as a mode; `9efcfb5`
   closes its three open questions; `272e6e7`/`3e3f951` plan the prerequisites;
   `0bdcdd3` refuses writes through a symlink into a preserved run; `2a57e12` applies
   write protection "four files claim exists"; `a32d8c4` names missing prerequisites;
   `d82d426` fixes the under-reporting banner; `693f57e` touches `pyproject.toml`.
   `5115789` separately grounds schema-mode attribute proposals in OBI + CEDAR.
3. **Ruling store.** `915eb72` plans it; `8143b85` builds `rulings.py`; `6a85540`
   migrates RUN1's three ruling shapes; `8c90490` surfaces conflicts rather than
   resolving them.
4. **Mode commands.** `7380f8d` plans; then `fb5bc92` (run lockfile), `7408bcd`,
   `9ad7db8` (numbered runs, protected tiers), `dbfa940`, `370f9c7` (backup +
   read-back), `fedd507` (carry-forward three-way split), `bcf5c16` (ingest join),
   `c2210af` (SEEK targets behind a project gate), `0e15464` (**the eight write
   refusals**), `4fa75e7` (chunk + reconcile), `6fabe13` (workflow-sequence test),
   `d1f4d14` (the seven new command docs), `64f233d` (absorb `curate-assay-vocabulary`),
   `eb8777e` (**register `assay` as the fifth curation mode**), `833e9be` (four
   review defects).

Files touched: all 8 `commands/curate-assay-*.md`, `skills/curation/ASSAY.md` (new),
`skills/curation/SKILL.md`, `skills/curation/SCHEMA.md`, 20 modules under
`scripts/assay_hygiene/`, `scripts/schema/{review,templates,terms}.py`,
`tests/conftest.py`, ~25 test modules, `.gitignore`, `pyproject.toml`,
`context/{NExtSEEK_API.yaml,min_api_endpoints_enriched.json}`.

Files conspicuously **not** touched: `README.md`, `CHANGELOG.md`,
`skills/curation/PHASES.md`, `commands/curate-status.md`, `scripts/status.py`,
`docs/SECURITY.md`.

### The concrete drifts this history produced

| # | drift | evidence |
|---|---|---|
| D1 | The canonical activation description names four modes; `assay` is missing | `plugin.json:4`, `marketplace.json:8`, `SKILL.md:3`, all pinned by `tests/test_identity_sync.py:16-28`; `test_description_names_every_mode:99-101` iterates four |
| D2 | `README.md` documents four modes and 19 commands across its five tables (13 pipeline + 2 fdh + 2 schema + 1 report + 1 any-mode); the repo ships five modes and 26 command files | `README.md:11` "organised as four **modes**"; `ls commands/*.md` → 26; the 8 `commands/curate-assay-*.md` are absent except `curate-assay-vocabulary`, which is filed under the wrong mode (D3) |
| D3 | `README.md` still lists `/curate-assay-vocabulary` under **schema** mode | `README.md:58` (schema table); `SKILL.md:34` and `skills/curation/ASSAY.md:35` place it in `assay`; commit `64f233d` moved it |
| D4 | `README.md:7` says v0.3.0; `pyproject.toml:3` says 0.3.0; everything else says 0.4.0 | §1 |
| D5 | `CHANGELOG.md` stops at 0.4.0 / 2026-07-31 — no entry for init auto-detect, the assay mode, or dependency pinning | `CHANGELOG.md:5` |
| D6 | `/curate-status` reports 4 of 5 modes | `scripts/status.py:180-187` `collect_status` has no `assay` key; `status.py:8` docstring says "the four modes"; `commands/curate-status.md:5` "across all four dmac-curation modes"; `tests/test_status.py:28` `test_collect_status_reports_all_four_modes` pins it |
| D7 | `README.md`'s repo-layout tree omits `skills/curation/ASSAY.md` and `scripts/assay_hygiene/` (39 modules, the largest package) | `README.md:88-107` |
| D8 | Three assay-hygiene specs disagree about their own status; the newest says "Not implemented" the day it shipped | `specs/2026-08-27-…-mode-design.md:3` vs commits `d1f4d14`…`833e9be` |
| D9 | `$DMAC_ENV_FILE` — the actual credential-bootstrap mechanism — appears only in `commands/curate-init.md:96-112,187` and `templates/env.example.j2:2-3`, in neither `README.md`'s Auth section nor `docs/SECURITY.md`'s table | grep |
| D10 | `templates/CURATION_PLAN.md.j2` is an orphan; `SAMPLE_TREE.html.j2` and its renderer are untested | §3, §4 |
| D11 | `pyproject.toml:5-7` says the bounds are floors while commit `693f57e` says "pin dependencies instead of lower-bounding them" | §5 |
| D12 | `PHASES.md:8` claims "14 commands drive 12 phases" but its own table has 11 numbered rows and omits `/curate-qc` (9b) entirely; `test_mode_table.py:87` asserts exactly 11 | `skills/curation/PHASES.md:17-30` |
