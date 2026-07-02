# FairDomHub integration — design spec

**Date:** 2026-07-02
**Author:** Charlie Demurjian (with Claude Opus 4.8)
**Status:** Approved for planning

## 1. Problem statement

The `dmac-curation` plugin drives a 13-phase NExtSEEK curation pipeline. Its only
current SEEK-family API touch is `nextseek_api.py` (reads assays + dev-only validate
against `nextseek.mit.edu`). Two FairDomHub (FDH / `fairdomhub.org`) capabilities live
*outside* the plugin today and need to come in:

1. A comprehensive, battle-tested **interactive upload tool** (`submit.py`, 1953 lines)
   that pushes a study to FDH via the SEEK JSON:API (assays, protocols/SOPs, sample
   types, samples, batch-publish). Currently run manually in a separate directory.
2. No **general, programmatic FDH API access**. When Charlie needs an ad-hoc operation
   ("find every sample linked to assay X, then delete them"), there is no path for
   Claude to discover the right endpoints and act.

The original plugin design (`2026-05-27-dmac-curation-plugin-design.md`) explicitly
deferred both: §12 Non-goals ("Not handling FDH `submit.py` invocation") and §13 Open
questions ("Whether to add a `/curate-publish` command that drives FDH `submit.py`
… Currently a non-goal; may revisit"). **This spec reopens that thread.**

**Goal:** ship FDH upload and general FDH API access as two independent, self-contained
modules inside the plugin, matching the plugin's existing conventions (PEP 723 +
`uv run`, `.env` secrets, `context/` frozen specs, thin markdown commands, on-demand
skill reference docs).

## 2. Scope decisions (from brainstorming, 2026-07-02)

| Decision | Choice |
|---|---|
| Positioning | **Independent standalone track** — NOT wired into the 13-phase artifacts. FDH tooling has its own inputs and workflow. |
| Module 1 (upload) | Port `submit.py` **~untouched**. Stays interactive, human-run. A thin `/fdh-upload` command sets up assets + launches it. |
| Module 2 (API access) | A **self-extending toolkit**: clean client + auto-generated lightweight index + a growing library of Claude-authored task scripts with a registry. |
| submit.py ↔ client coupling | **Independent.** submit.py keeps its embedded client (don't destabilize a working interactive tool). Module 2 gets a fresh, clean `FairDomHubClient`. HTTP/auth logic duplicated across the two by design. |
| Generated-script storage | **Plugin library, review-then-commit.** Scripts land in `scripts/fdh/generated/`; Claude shows the diff, user approves, then git-commit. |
| API index | **Auto-generated** from the YAML (re-runnable on API bumps). Follows the existing `min_api_endpoints_enriched.json` pattern, extended with a `yaml_lines` back-pointer. Stored in `context/`. |
| Base URL | **Parameterized.** Default `https://fairdomhub.org`; override via `.env` `FDH_BASE_URL` or `--base-url` (mirrors `nextseek_api.py`). |
| Destructive ops | **Dry-run/preview default → explicit `--write`/`--yes` + confirmation.** Matches the plugin's deposit convention; DELETE on a live public repo is irreversible. |
| Command naming | `fdh-*` prefix (not `curate-*`) to signal a separate track. |
| Skill guidance home | New on-demand reference `skills/curation/FDH.md` (mirrors `PHASES.md`) + a short pointer in `SKILL.md`. Not a whole new skill. |

## 3. Directory layout

```
context/
  full-fdh-openapi-spec.yaml     # vendored full SEEK JSON:API spec (moved from working/); frozen like NExtSEEK_API.yaml
  fdh_api_index.json             # AUTO-GENERATED lightweight map (Claude reads this FIRST, never the 640KB YAML wholesale)

scripts/fdh/
  __init__.py
  fdh_api.py                     # FairDomHubClient (auth/retry/pagination/_get/_post/_patch/_delete) + thin read CLI
  build_api_index.py             # generator: full-fdh-openapi-spec.yaml -> context/fdh_api_index.json
  submit.py                      # Module 1, ported ~untouched
  generated/
    REGISTRY.md                  # index of Claude-authored task scripts: name | purpose | endpoints used | date
    __init__.py

commands/
  fdh-upload.md                  # Module 1 launcher/prereq-checker
  fdh-api.md                     # Module 2 entry point + maintenance (refresh-index / list-registry)

skills/curation/
  FDH.md                         # NEW load-on-demand reference; SKILL.md gets a ~5-line pointer

tests/
  test_fdh_api_cli.py            # help-text + client-construction smoke tests (mirrors test_nextseek_api_cli.py)
  test_build_api_index.py        # index-generator round-trip / shape assertions
  test_fdh_commands_present.py   # command files parse + reference correct script paths
```

## 4. Module 1 — FDH Upload

- `submit.py` moves into `scripts/fdh/` **verbatim** (it works; we don't refactor it).
  Its embedded JSON:API client, `--resume`/`--step` session persistence, `PROJECT_MAPPING`,
  and two-step SOP upload all stay. Only unavoidable path/import adjustments if any.
- **`/fdh-upload` command** (thin, human-handoff — mirrors how GEO/Zenodo/OMERO deposits
  are human-driven in this plugin):
  1. Verify `.env` has `FDH_API` (JSON `{user: token}`); warn + point at `.env.example` if absent.
  2. Verify the `Assets/` layout: metadata workbook (`.xlsx`, one sheet per Sample Type,
     `UID` column required) + `Assets/Protocols/`.
  3. Remind: the **Study must be created manually** via the FDH web UI first (note its numeric ID).
  4. Surface the 6-step flow (Config → Assays → Protocols → Metadata rewrite → Sample
     types → Samples → Publish) and the resume model.
  5. Hand off: user runs `uv run <plugin>/scripts/fdh/submit.py` interactively.
- submit.py's setup notes / `PROJECT_MAPPING` are echoed in `FDH.md`.

**Non-goal for Module 1:** making submit.py non-interactive or Claude-driven. It stays a
human-run interactive tool.

## 5. Module 2 — FDH API Access (the reuse loop)

### 5.1 Components

- **`context/fdh_api_index.json`** — the "light wrapper." A JSON list of enriched endpoint
  objects, one per operation, following `min_api_endpoints_enriched.json`'s shape:
  ```json
  {
    "path": "/samples/{id}",
    "method": "DELETE",
    "operation_id": "deleteSample",
    "summary": "Delete a sample by ID",
    "category": "sample_write",
    "primary_entities": ["samples"],
    "intent_patterns": ["delete", "remove", "destroy sample"],
    "llm_hint": "Destructive. Requires the numeric sample id. To find samples by assay, first GET /assays/{id} and follow relationships.samples.",
    "yaml_lines": [10432, 10510]
  }
  ```
  The `yaml_lines` back-pointer lets Claude `Read` the exact slice of
  `full-fdh-openapi-spec.yaml` for request/response schema detail, never the whole file.
- **`scripts/fdh/build_api_index.py`** — parses `full-fdh-openapi-spec.yaml`, emits
  `fdh_api_index.json`. Derives `summary`/`operation_id`/`method`/`path`/`yaml_lines`
  mechanically; `category`/`intent_patterns`/`llm_hint` from lightweight heuristics
  (method+path → category; verbs from summary → intent_patterns). Re-runnable when the
  API version bumps. PEP 723, stdlib + PyYAML.
- **`scripts/fdh/fdh_api.py`** — `FairDomHubClient`:
  - Auth: `Token <token>` from `.env` `FDH_API` (reuses submit.py's convention; picks a
    user or takes `--user`). Base URL parameterized.
  - Low-level: `_get/_post/_patch/_delete`, `_page_through` (JSON:API `links.next`),
    retry/backoff on 429/502/503 (ported patterns, cleaned).
  - **First-class read verbs** (CLI subcommands) so trivial reads never need a generated
    script: `search`, `get <type> <id>`, `download-blob <url|ids>`, `list <type>`
    (e.g. a project's studies/assays), `whoami`.
  - Importable by generated scripts: `from fdh_api import FairDomHubClient`.
- **`scripts/fdh/generated/`** — Claude-authored task scripts + `REGISTRY.md`.

### 5.2 The decision procedure (encoded in FDH.md + /fdh-api)

1. **Check the library first.** Read `scripts/fdh/generated/REGISTRY.md`. If a script
   already covers the task, run it (respecting its dry-run/`--write` contract).
2. **Else consult the index.** Read `context/fdh_api_index.json`; match on
   `intent_patterns`/`category`/`llm_hint`; select the endpoints.
3. **Pull only the relevant YAML.** `Read` `full-fdh-openapi-spec.yaml` at the
   `yaml_lines` ranges from the chosen entries — never the whole spec.
4. **Generate + run.** Write a PEP 723 script under `generated/` that
   `from fdh_api import FairDomHubClient` and does exactly the task. Writes default to
   **dry-run/preview**; require explicit `--write` + confirmation before mutating.
5. **Contribute back.** Add a `REGISTRY.md` row (name | one-line purpose | endpoints used
   | date), show the user the diff, and commit on approval.

### 5.3 Generated-script template (convention)

Each generated script:
- PEP 723 inline deps (`requests`, plus the plugin's `fdh_api`), stdlib-first.
- `sys.path` injects `scripts/fdh/` so `from fdh_api import FairDomHubClient` resolves.
- argparse CLI; a leading docstring block the `REGISTRY.md` row is derived from.
- For any write/delete: `--dry-run` is the default, prints a preview table of exactly
  what would change; `--write` (and an interactive confirm) required to execute.
- Never logs credentials.

## 6. Safety & secrets

- Auth via project `.env` (`FDH_API` JSON, optional `FDH_BASE_URL`); never logged.
  `.gitignore` already excludes `.env`.
- `full-fdh-openapi-spec.yaml` is a public spec — safe to commit to `context/`.
- Destructive generated scripts: dry-run default → preview → explicit `--write`/`--yes`.
  This is enforced by the template and stated as a hard rule in `FDH.md`.
- Review-then-commit gate on every generated script (no silent auto-commit of
  DELETE-capable code into the shared plugin).

## 7. SKILL.md + FDH.md

- **`FDH.md`** (new, load-on-demand, mirrors `PHASES.md`): Module 1 upload prereqs +
  flow; Module 2 reuse loop + index shape + generated-script template + safety rules;
  auth setup; base-URL parameterization; `PROJECT_MAPPING` reference.
- **`SKILL.md`** edits (minimal): add FDH activation triggers ("upload to FairDomHub",
  "access the FDH API", "delete/find … on FDH") to the activation section; add
  vocabulary entries; add a one-line pointer to `FDH.md`. Do not bloat the always-loaded
  playbook.

## 8. Deliverables

1. `context/full-fdh-openapi-spec.yaml` (moved from `working/`).
2. `context/fdh_api_index.json` (generated).
3. `scripts/fdh/{__init__.py, build_api_index.py, fdh_api.py, submit.py}`.
4. `scripts/fdh/generated/{__init__.py, REGISTRY.md}` (scaffold, seeded empty/example).
5. `commands/{fdh-upload.md, fdh-api.md}`.
6. `skills/curation/FDH.md` + `SKILL.md` pointer edits.
7. Tests: `test_fdh_api_cli.py`, `test_build_api_index.py`, `test_fdh_commands_present.py`.
8. `README.md` + `CHANGELOG.md` updates; `working/` cleaned up (spec + submit.py relocated).

## 9. Non-goals

- Making submit.py non-interactive or Claude-driven.
- Wiring FDH into the 13-phase pipeline artifacts (flat/Arm sheets). It's standalone.
- Refactoring submit.py onto the shared client (explicitly deferred; duplication accepted).
- A full hand-written CRUD CLI for every FDH resource — bespoke writes are generated on demand.
- Non-`fairdomhub.org` SEEK support beyond the `--base-url` parameter already provided.

## 10. Open questions (resolve during implementation planning)

- Exact `category` taxonomy + heuristic rules in `build_api_index.py` (e.g. how to bucket
  the `{asset_types}/{id}/content_blobs/...` download paths).
- Whether `download-blob` belongs as a first-class verb or the first seeded generated
  script (leaning first-class — it's universal).
- Whether `REGISTRY.md` should be Markdown (human-skimmable) or JSON (machine-queryable).
  Leaning Markdown to match `PHASES.md`/doc conventions; Claude greps it fine.
- Whether to add a couple of seed example scripts in `generated/` to establish the
  template, or ship it empty with the template documented only in `FDH.md`.

## 11. Success criteria

1. `uv run <plugin>/scripts/fdh/build_api_index.py` regenerates `context/fdh_api_index.json`
   from the vendored YAML deterministically.
2. `uv run <plugin>/scripts/fdh/fdh_api.py --help` and each read subcommand's `--help` work
   without network/credentials (smoke-tested).
3. `/fdh-upload` correctly checks prereqs and hands off to the interactive tool.
4. Given a natural-language ask ("find samples for assay X and delete them"), Claude can
   follow FDH.md: check REGISTRY → read the index → pull the right YAML slice → generate a
   dry-run-first script → (on `--write`) act → register it back.
5. No secret values anywhere in the repo or its git history.
6. All existing tests still pass; new FDH tests pass.
