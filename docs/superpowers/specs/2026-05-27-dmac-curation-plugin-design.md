# dmac-curation plugin — design spec

**Date:** 2026-05-27
**Author:** Charlie Demurjian (with Claude Opus 4.7)
**Status:** Draft for review

## 1. Problem statement

Across the last ~30 days, Charlie has run nine Claude Code sessions curating research-project metadata into NExtSEEK / FairDomHub for four labs (Engelward / Kamm / White / Griffith). The sessions converge on a stable 13-phase pipeline with reusable scripts (`nextseek_api.py`, `consolidate_to_flat.py`, `qa_flat_sheets.py`, `_common.py`, `rename_files.py`, `omero_pull.py`, etc.) and a recurring set of behavioral rules (Q&A before UIDs, copy `-upload.xlsx` → `-upload-new.xlsx` before edits, schema lies + workbook tells truth, etc.).

The reusable assets currently exist as **copies inside each project directory**, which means:
- Bug fixes don't propagate (e.g., the `nextseek_api.py` pagination bug was fixed in intravchip but stale copies remained in lee + yufei_gemm)
- Schema JSONs drift between projects (an intravchip `sampletypes_db.json` from 2026-05-08 sits next to a lee version from 2026-04-23)
- Onboarding a new curator means manually copying ~15 scripts and ~6 JSONs
- The behavioral rules live in individual session memory entries, not in any reusable artifact

**Goal:** package the pipeline as a Claude Code plugin (`dmac-curation`) so reusable assets live in one git-versioned location and per-project work is a thin layer over the plugin.

## 2. Audience and scope

**Audience:** MIT DMAC curators (Charlie + colleagues working with NExtSEEK / `fairdata.mit.edu`).

- MIT defaults stay baked in: `nextseek.mit.edu` host, `bmc-pub14.mit.edu` SMB, `ATHENA.MIT.EDU` Kerberos realm, `omero.mit.edu`.
- Lab codes (ENG / KAM / WHI / GRI / SAR) are parameterized at `/curate-init` time, not hardcoded.
- Not designed for: NExtSEEK installs at other institutions (would require host parameterization), or non-NExtSEEK LIMS (would require deeper abstraction).

**Paradigm:** general manuscript-driven PI curation. Curator gets a folder from a PI (manuscript + raw data + emails + an existing master spreadsheet), builds a sample-tree, populates upload sheets, deposits raw data to GEO/Zenodo/OMERO, retrieves metadata back, and sends a clarification email to the PI.

The CGR-style plate-map / researcher-Q&A paradigm is **not** the primary target. Its strongest insight — "round-trip with the researcher before minting UIDs" — is preserved as a soft rule in SKILL.md, applicable when scope is ambiguous.

## 3. The 13-phase pipeline

| # | Phase | Slash command | Primary artifact |
|---|---|---|---|
| 0 | Init | `/curate-init [--lab CODE] [--pi NAME]` | scaffold cwd + lockfile |
| 1 | Inventory | `/curate-inventory` | `FILE_INDEX.md` |
| 2 | Sample tree | `/curate-sample-tree` | `SAMPLE_TREE.md` |
| 3 | Questions | `/curate-questions [add\|list\|resolve]` | `QUESTIONS_FOR_PI.md` |
| 4 | (Task plan) | (uses TaskCreate, no command) | TaskList state |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}.xlsx` (flat format) |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` |
| 8 | Synonyms | (LLM-driven inside Phase 7) | `context/assay_synonyms.json` |
| 9 | QA | `/curate-qa` | console report (CLEAN / SOFT_FLAG / HARD_REJECT) |
| 10 | Deposit | `/curate-deposit <geo\|zenodo\|omero> [args]` | uploaded files + `Link_PrimaryData` backfilled |
| 11 | Retrieve | `/curate-retrieve` | `RETRIEVE.TXT` |
| 12 | Validate | `/curate-validate <metadata.xlsx>` | console diff report |
| 13 | Email | `/curate-email` | `EMAIL_TO_PI.md` |
| any | Status | `/curate-status` | console pipeline-state summary |

## 4. Plugin shape

Claude Code plugin (not a bare skill), so we get slash commands + skill loading + future plugin-marketplace distribution.

```
dmac-curation/
├── .claude-plugin/
│   └── plugin.json                  # plugin manifest
├── README.md
├── CHANGELOG.md
├── .gitignore                       # secrets-safe (.env, *.key, credentials, etc.)
├── skills/
│   └── curation/
│       ├── SKILL.md                 # always-loaded behavioral playbook (~150 lines)
│       ├── PHASES.md                # deep per-phase reference (~500 lines, read on demand)
│       └── examples/                # worked examples Claude can reference
├── commands/                        # the 13 slash commands (markdown)
│   ├── curate-init.md
│   ├── curate-inventory.md
│   ├── curate-sample-tree.md
│   ├── curate-questions.md
│   ├── curate-build.md
│   ├── curate-consolidate.md
│   ├── curate-resolve-assays.md
│   ├── curate-qa.md
│   ├── curate-deposit.md            # routes to geo/zenodo/omero sub-helpers
│   ├── curate-retrieve.md
│   ├── curate-validate.md
│   ├── curate-email.md
│   └── curate-status.md
├── scripts/                         # PEP 723 inline-deps, invoked via `uv run --script`
│   ├── nextseek_api.py
│   ├── consolidate_to_flat.py
│   ├── qa_flat_sheets.py
│   ├── inspect_workbook.py
│   ├── _common.py
│   ├── rename_files.py              # 5 subcommands: walk/checksums/apply/verify/rollback
│   ├── omero_pull.py
│   ├── build_retrieve.py
│   ├── apply_zenodo_links.py
│   ├── apply_geo_accessions.py
│   ├── apply_omero_ids.py
│   ├── review_metadata_vs_uploads.py
│   ├── stage_zenodo.py
│   ├── upload_geo_ncftp.sh
│   ├── smb_pull.py
│   └── deposit/
│       ├── geo_build_xlsx.py
│       └── omero_rest_client.py
├── context/                         # frozen NExtSEEK schema snapshots
│   ├── sampletypes_db.json
│   ├── assays_db.json
│   ├── projects_db.json
│   ├── neo4j_schema.json
│   ├── neo4j_assay-sample-conn.json
│   ├── NExtSEEK_API.yaml
│   └── min_api_endpoints_enriched.json
├── templates/                       # rendered into cwd by /curate-init
│   ├── CLAUDE.md.j2
│   ├── FILE_INDEX.md.j2
│   ├── SAMPLE_TREE.md.j2
│   ├── QUESTIONS_FOR_PI.md.j2
│   ├── CURATION_PLAN.md.j2
│   ├── EMAIL_TO_PI.md.j2
│   ├── pyproject.toml.j2
│   ├── env.example.j2
│   └── gitignore.j2
└── docs/
    └── superpowers/
        ├── specs/2026-05-27-dmac-curation-plugin-design.md   # this file
        └── plans/                                             # to be created by writing-plans
```

**No `labs/` directory.** Lab-level overrides (Marie's `D.IMG.Parent=OOC` precedent, Lee's misplaced-MUS pattern, the BMC G-vs-L plate convention) live in either:
- Per-project `CLAUDE.md` (written by `/curate-init --lab CODE`)
- Curator's persistent memory (`~/.claude/projects/.../memory/`)

Adding a third layer is over-engineering until durable cross-lab patterns emerge.

## 5. Plugin-owned vs project-owned

| Asset | Owner | Reasoning |
|---|---|---|
| Reusable scripts (nextseek_api, consolidate_to_flat, qa_flat_sheets, _common, rename_files, omero_pull, etc.) | Plugin | Bug fixes propagate via `git pull`. PEP 723 inline-deps + `uv run --script <plugin>/scripts/X.py` make invocation from cwd painless. |
| Schema JSONs (`context/*.json` + NExtSEEK_API.yaml) | Plugin | Frozen vintage. Lockfile records which vintage a project used at init. |
| Templates (`*.md.j2`, `*.j2`) | Plugin | One canonical version per artifact type. |
| `SKILL.md`, `PHASES.md` | Plugin | Behavioral playbook + deep reference. |
| Slash command markdown | Plugin | Same. |
| **Per-arm `build_<arm>.py`** | Project | Genuinely encode "for THIS paper, row N has these specific values" — not reusable. Imports plugin's `_common.py` via `sys.path` injection. |
| `files/`, `manuscript/`, `previous_metadata/` | Project | PI's actual inputs. |
| `assay_sheets/` | Project | Outputs. |
| `FILE_INDEX.md`, `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md`, `EMAIL_TO_PI.md` | Project | Project-specific artifacts. |
| `CLAUDE.md`, `.env`, `pyproject.toml`, `.gitignore` | Project | Per-project config. `.env` never in git. |
| `manifest.csv`, `omero_images.csv`, `RETRIEVE.TXT` | Project | Generated per-project. |
| `.dmac-curation.json` | Project | Lockfile (plugin SHA + schema vintage at init). |

## 6. Slash command pattern

Each `commands/curate-*.md` follows a uniform shape:

```markdown
---
description: <one-line description>
---

<intent: what the user wants when they invoke this command>

Args ($ARGUMENTS): <flag list>

Prereqs (verify before proceeding):
- <file/state that must exist>

Steps:
1. <step>
2. <step>
3. ...

Behavioral rules (specific to this command, in addition to SKILL.md):
- <rule>
```

**Worked example: `commands/curate-build.md`** (illustrative, full version in implementation):

```markdown
---
description: Build per-arm upload sheets (Phase 5)
---

User wants to build assay-sheet rows for a specific experimental arm.

Args: <arm> (optional). If omitted, list arms from SAMPLE_TREE.md and AskUserQuestion.

Prereqs:
- ./SAMPLE_TREE.md exists
- ./previous_metadata/*.xlsx exists
- ./CLAUDE.md has lab+pi resolved
- ./.env warning if missing (needed at /curate-resolve-assays)

Steps:
1. Read SAMPLE_TREE.md, identify sample types and counts for the arm.
2. Read previous_metadata to identify existing parent UIDs (don't recreate).
3. Read manuscript/ for protocol section names, instrument details.
4. Generate ./scripts/build_<arm>.py:
   - PEP 723 inline deps: openpyxl
   - sys.path inserts plugin scripts/ dir
   - Imports mint_uid, write_4sheet_xlsx from _common
   - Mints UIDs <TYPE>-YYMMDD<LAB>-N from N=1
   - Writes 4-sheet xlsx per sample type to assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx
5. Run the script. Report row counts.
6. Suggest /curate-build for next arm or /curate-consolidate if all arms done.

Behavioral rules:
- Follow precedent over schema (sample existing PI rows in previous_metadata first).
- Use *** PLACEHOLDER: ... *** markers, never blanks (greppable).
- Pre-assigned UIDs (no auto-gen).
- Don't include parent-tier records that already exist.
```

## 7. SKILL.md (the behavioral playbook)

Always-loaded when plugin is active. ~150 lines. Sections:

1. **Activation triggers** — cwd contains `.dmac-curation.json` or `files/`+`manuscript/`+`previous_metadata/`; or user invokes any `/curate-*` command; or user mentions NExtSEEK / FairDomHub / FDH curation.
2. **13-phase pipeline table** — brief index, pointer to `PHASES.md` for depth.
3. **Hard rules** (8) — never violate:
    1. Q&A before UIDs (draft `EMAIL_TO_PI.md` skeleton before minting if scope ambiguous)
    2. Copy `-upload.xlsx` → `-upload-new.xlsx` before editing
    3. Check for manual edits before regenerating (diff first)
    4. Schema lies; workbook tells truth (sample existing PI rows before consulting JSON)
    5. Re-mine email/manuscript before re-asking PI
    6. Use `uv`, not bare `python3`
    7. Pre-assigned UIDs, never auto-gen
    8. Placeholder markers over blanks
4. **Soft rules** — concrete trees not prose; Name-pattern email anchors; skeleton-first emails; no em dashes; File_PrimaryData required but Link/Checksum not enforced; many-to-many parents OK for legacy data; D.IMG.Parent follows PI precedent.
5. **Vocabulary** — "curate", "consolidate to flat", "QA the sheet", "build X sheet", "RETRIEVE.TXT", "the email", "all set" / "lets move on".
6. **Pitfalls** (15+) — openpyxl ghost rows; cell.style not reset by None; GEO literal validation; chat_nextseek auto-pulls parents; validate endpoint dev-only; VPN drops freeze SMB pulls; `_NNNN` vs `-NNNN`; year-prefix mouse-ID typos; `_Frzn` PI suffix noise; BMC SMB `cdemu@mit.edu` form; ATHENA realm but BMC ignores Kerberos; fig-7-style byte-identical duplicates.
7. **Routing** — PHASES.md for depth; `commands/curate-*.md` for command specifics.

## 8. Bundled scripts

All scripts use PEP 723 inline-script metadata, runnable via `uv run --script <plugin>/scripts/X.py`. Sourced from past sessions (mostly verbatim with consolidation):

| Script | Source pattern | Notes |
|---|---|---|
| `nextseek_api.py` | yufei-gemm + intravchip | Pagination via `next` link only, CSRF prime via `/login/`, dev-endpoint awareness for `validate`. Subcommands: `fetch-assays`, `validate`. |
| `consolidate_to_flat.py` | yufei-gemm + intravchip | REPO root from script location, UID preserved in `json_metadata`, `--all-in-one`, idempotent from `4sheet_originals/`. |
| `qa_flat_sheets.py` | yufei-gemm + intravchip | CLEAN/SOFT_FLAG/HARD_REJECT dispositions. UID uniqueness, parent resolvability, JSON validity, placeholder markers. |
| `_common.py` | intravchip (richest) | UID minting, manifest/OMERO/baseline readers, 4-sheet xlsx writer, placeholder emitter. |
| `inspect_workbook.py` | recurrent inline | New canonical file. Sheet names, dims, headers, row samples. |
| `rename_files.py` | intravchip-3 | 5 subcommands (walk/checksums/apply/verify/rollback). Stdlib-only. Manifest CSV source-of-truth. Regex matches `[_-]NNNN`. `--parser <name>` plugin point. |
| `omero_pull.py` | intravchip-3 | 3 subcommands (`images`, `diff`, `all`). Auth: sessionid or username+password. |
| `build_retrieve.py` | lee | Walks `*-upload-new.xlsx` preferred over `*-upload.xlsx`. **Excludes DNA/RNA by default** (retrieve auto-pulls parents). `--include-parents` override. |
| `apply_zenodo_links.py` | lee-3 | Join zip namelist → UID, patch Link_PrimaryData. `--dry-run`. |
| `apply_geo_accessions.py` | lee-3 | D.SEQ + A.GEX + A.SPTX link + accession patching. `--write` flag. |
| `apply_omero_ids.py` | intravchip-3 + lee-3 | D.IMG link patching from `omero_images.csv`. |
| `review_metadata_vs_uploads.py` | lee-3 | Diff downloaded `*_AllMetadata.xlsx` vs upload sheets. |
| `stage_zenodo.py` | lee-3 | Figure × sample-type bucketing into zips. `--dry-run`. |
| `upload_geo_ncftp.sh` | lee-3 | Parallel ncftpput with retry-loop, `stdbuf -oL`, per-job heartbeat. |
| `smb_pull.py` | lee-2 + lee-3 | Generic BMC stream-pull, `--dry-run`/`--resume`/`--from-manifest`/`--rows N-M`. `pigz -c` pipe. `share_access="rwd"`. `.env` creds. |
| `deposit/geo_build_xlsx.py` | lee-3 (`render_geo_xlsx.py`) | BULK/SPTX template render with capture-and-re-paste for >15 samples. Resets `cell.style="Normal"`. |
| `deposit/omero_rest_client.py` | extracted from `omero_pull.py` | Shared REST client logic. |

## 9. `/curate-init` flow + lockfile

**Render to cwd:**
```
./CLAUDE.md                  # rendered from CLAUDE.md.j2 with {lab, pi, project_date}
./.env.example               # NEXTSEEK_USERNAME, NEXTSEEK_PASSWORD, MIT_USER, MIT_PASS, NCFTP_*
./.gitignore                 # .env, .venv/, *.partial, GEO/, Zenodo_upload/, etc.
./pyproject.toml             # uv project, deps: openpyxl, requests, smbprotocol
./.dmac-curation.json        # lockfile
./files/                     # empty
./manuscript/                # empty
./previous_metadata/         # empty
./assay_sheets/              # empty
./scripts/                   # empty
```

**`.dmac-curation.json` lockfile shape:**
```json
{
  "plugin_name": "dmac-curation",
  "plugin_sha": "<git rev-parse HEAD at ~/.claude/plugins/dmac-curation>",
  "plugin_version": "0.1.0",
  "schema_vintage": "<date from context/sampletypes_db.json>",
  "init_date": "2026-05-27",
  "init_user": "<$USER>",
  "lab": "KAM",
  "pi": "marie",
  "nextseek_project_id": null
}
```

`nextseek_project_id` populated by `/curate-resolve-assays`. Other commands read the lockfile to recover lab/pi context.

**Behavioral rules for init:**
- Never overwrite existing `CLAUDE.md` without asking
- Prompt via `AskUserQuestion` if `--lab` or `--pi` not provided (don't guess)
- Refuse to init if cwd contains existing curation artifacts unless `--force`

## 10. Secrets handling

**Inviolable:**
- `.env` files never committed to plugin repo (gitignored at the repo root)
- `.env.example` shipped as template only, never with real values
- No credentials, tokens, keys, or passwords anywhere in `scripts/`, `templates/`, `commands/`, `skills/`, `context/`
- Scripts that need credentials read from `.env` via `python-dotenv` (or equivalent), warning if absent
- Plugin's `.gitignore` excludes: `.env`, `*.env`, `*.key`, `*.pem`, `credentials*`, `secrets*`, `.netrc`, `.smbcreds`, `*_token*`, `*_secret*`, `*_password*`, `*.kdbx`
- Before any commit, grep staged files for known secret-y patterns

**Per-project secrets** live in the project's own `.env` (also gitignored). Examples:
- `NEXTSEEK_USERNAME`, `NEXTSEEK_PASSWORD` (or `NEXTSEEK_TOKEN`)
- `MIT_USER=cdemu@mit.edu`, `MIT_PASS`, `MIT_DOMAIN=MIT.EDU`, `SMB_HOST=bmc-pub14.mit.edu`
- `NCFTP_HOST`, `NCFTP_USER=geoftp`, `NCFTP_PASS` (temporary upload ticket)
- `FDH_API` for fairdata.mit.edu

## 11. Distribution

- **Repo:** `github.com/cdemurjian/dmac-curation` (public, MIT-licensed)
- **Install (today):** `git clone git@github.com:cdemurjian/dmac-curation.git ~/.claude/plugins/dmac-curation`. Claude Code auto-discovers `.claude-plugin/plugin.json`.
- **Install (future):** plugin marketplace via `/plugin install dmac-curation`.
- **Updates:** `cd ~/.claude/plugins/dmac-curation && git pull`. Lockfile preserves init-time SHA for reproducibility.
- **Versioning:** semver. Schema vintage tracked separately in `CHANGELOG.md`.

## 12. Non-goals

- Not generating per-arm builder logic on the fly from a manuscript abstract — `/curate-build` produces a starter `build_<arm>.py` that the curator inspects and customizes.
- Not abstracting away NExtSEEK for non-MIT installs.
- Not automating GEO/Zenodo/OMERO web-UI uploads — those remain human-driven; the plugin handles preparation and post-upload URL backfill only.
- Not handling FDH `submit.py` invocation — that's a separate step outside the plugin (the user runs it manually in `PUBLISH-FDH/<project>/`).
- Not maintaining `labs/` profiles — over-engineering. Lab knowledge lives in per-project `CLAUDE.md` or curator memory.

## 13. Open questions / followups (to be resolved during implementation planning)

- Exact prompt structure for each `/curate-*.md` command (this spec gives the pattern; the implementation plan will write all 13).
- Whether `PHASES.md` should be a single long reference or split per-phase. Probably single — easier to grep.
- Whether to ship a `worktree`-based smoke test harness (run a fake curation against a fixture project) — defer to implementation plan.
- How to refresh `context/*.json` from live NExtSEEK — likely a `tools/refresh_context.py` for plugin maintainers, not for end-users.
- Whether to add a `/curate-publish` command that drives FDH `submit.py` invocation. Currently a non-goal; may revisit.

## 14. Success criteria

Implementation is done when:

1. Cloning the repo to `~/.claude/plugins/dmac-curation` makes all 13 slash commands available in any Claude Code session.
2. `/curate-init --lab KAM --pi marie` in an empty dir produces the scaffold + lockfile.
3. A new curation project (any of the four labs Charlie has worked with) can run end-to-end through phases 1-13 using only the slash commands, plugin scripts, and natural-language driving.
4. Bug fixes to `nextseek_api.py` or `consolidate_to_flat.py` propagate to existing project work via `git pull` (no copying).
5. No secret values are present anywhere in the repo's git history.
6. README + CHANGELOG + this spec are committed and visible on GitHub.
