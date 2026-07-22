# Changelog

All notable changes to dmac-curation will be documented in this file.

## 0.3.0 - 2026-07-22

Reframed from a 13-phase pipeline into a four-mode curator's workbench.

### Added

- **`schema` mode** (`/curate-sampletype <TYPE>`) - propose or bolster a
  NExtSEEK sample type. Field index and reuse check over the 1059 field names
  (857 of which are used by exactly one type), controlled-vocabulary proposals
  sourced from the Tags column, observed values and BioPortal, and a
  `<TYPE>.review.md` written for a human deciding what to apply. cwd-scoped;
  needs no project. Never writes to NExtSEEK.
- **`report` mode** (`/curate-report <FORMAT> <input>`) - GEO, SRA and PRIDE
  submission artifacts from UIDs, a NExtSEEK workbook, a curated `Arm{X}.xlsx`,
  or arbitrary tabular data. The LLM emits one declarative mapping spec,
  O(columns); execution across rows is deterministic. Every format ships both a
  renderer and a validator (two-stage: render the artifact, then validate it) -
  GEO and SRA render workbooks, PRIDE renders a tab-delimited `submission.px`.
  Input-scoped; runs without a lockfile.
- `scripts/_config.py` - the single project-config seam, resolved from cwd.
- `scripts/_lockfile.py` - lockfile schema v1 with `modes{}`, and in-memory v0
  migration.
- `scripts/status.py` - `/curate-status` now reports per mode.
- `scripts/refresh_context.py` - a real refresh path for bundled `context/`,
  plus `context/PROVENANCE.json` recording source, commit and sha256 per
  vendored file.
- `--gse-bulk`/`--gsm-csv` and `--gse-sptx`/`--sptx-gsm-csv` on
  `apply_geo_accessions.py`; `--retrieve` and `--assay-sheets` on
  `review_metadata_vs_uploads.py`; `--upload`, `--master-baseline` and
  `--expected-counts` on `qa_flat_sheets.py`; `--assay-sheets` on
  `consolidate_to_flat.py`.
- `docs/SECURITY.md`, and a test that fails if a plaintext token reappears.

### Changed

- **Identity.** The plugin is the curator's workbench, not a pipeline. One
  canonical description in `plugin.json`, `marketplace.json` and `SKILL.md`,
  asserted identical by test.
- **`SKILL.md` carries a mode table**; the phase table moved to `PHASES.md`.
- **`/curate-init` is additive** - creates what is missing, never overwrites,
  and merges a mode into an existing lockfile rather than refusing to run.
- **13 phases became 11.** Phase 4 (task plan) and Phase 8 (synonyms) are
  retired as numbers; neither had a command of its own. Surviving numbers are
  deliberately not renumbered.
- **Phase 10's GEO build delegates to `report` mode.** It keeps external upload
  and accession backfill only.
- `templates/CLAUDE.md.j2` is mode-aware.

### Fixed

- **Ten scripts resolved project paths against the plugin install directory**,
  so `/curate-consolidate` and `/curate-qa` read and wrote *inside the plugin
  checkout* - `consolidate_to_flat.py` deleted xlsx files there. All now resolve
  from cwd. A regression harness hashes the plugin tree around every script run.
- **`stage_zenodo.py` and `apply_zenodo_links.py` used `--dry-run` and therefore
  defaulted to WRITING**, while `curate-deposit.md` claimed all four deposit
  scripts defaulted to dry-run. All four now default to dry-run and require
  `--write`.
- **Phase 12 never read `RETRIEVE.TXT`** despite `PHASES.md` naming it as an
  input. It now does, separating auto-pulled lineage parents from genuinely
  unexpected extra rows.
- **`scripts/_common.py` carried one project's constants** - a scientist's name,
  a hardcoded master filename, a cell-line UID table, manuscript section titles
  - and every importer inherited them. It is a library now.
- Plaintext FairDomHub tokens on disk under `working/`. Rotated and removed.
- `context/neo4j_schema.json` was a **dev-instance** snapshot with 23 `Sample`
  properties where the live schema has 85, and `VINTAGE.json` pointed at a
  refresh tool that did not exist.

### Documented

- **Phase 5's 4-sheet output is a curator review artifact, not a build
  intermediate.** That is why Phases 5 and 6 do not collapse, and it appeared in
  no file in the repo.
- **Ontology validation exists only in the 4-sheet format.** An ontology column
  added to a flat sheet is accepted and *silently discarded*, because
  `InputRowModel` is `additionalProperties: true`. Read from a 2026-05-27 API
  spec and flagged for confirmation with the API owner.
- **PRIDE is not a spreadsheet.** `pride.json` declares a tab-delimited
  ProteomeXchange submission summary file. chat_nextseek's e2e catalog asserting
  `pride.xlsx` names the wrong artifact type.
- Why CEDAR templates are out of scope: CEDAR's model is a nested tree with no
  cross-record reference concept; NExtSEEK lineage is a graph, so referential
  integrity would live entirely outside it.

### Known open questions

- Whether the flat upload format has gained ontology support since 2026-05-27.
  Both `schema` and `pipeline` mode docs depend on it still lacking one.
  **Confirm with the NExtSEEK API owner.**
- What "apply" concretely means for a proposed sample type record: admin UI,
  SQL update, or a PR against a schema repo. `<TYPE>.review.md` says to ask.

## 0.2.0

Added FairDomHub integration as two standalone modules:
- `/fdh-upload` — ported the interactive `submit.py` study-upload tool into `scripts/fdh/`.
- `/fdh-api` — self-extending API-access toolkit: `FairDomHubClient` (`scripts/fdh/fdh_api.py`),
  an auto-generated enriched endpoint index (`context/fdh_api_index.json` via
  `build_api_index.py`) with `yaml_lines` pointers into the vendored full OpenAPI spec, and a
  review-then-commit generated-script registry.
- New `skills/curation/FDH.md` reference; SKILL.md routing hooks.

## [0.1.0] — 2026-05-27

### Added
- Plugin manifest (`.claude-plugin/plugin.json`)
- Skill playbook (`skills/curation/SKILL.md` — 8 hard rules, 7 soft rules, 13 pitfalls)
- Deep phase reference (`skills/curation/PHASES.md`)
- 13 slash commands (`commands/curate-*.md`)
- 16 bundled scripts (NExtSEEK API, consolidate, QA, retrieve, rename, OMERO, SMB, deposits)
- 7 NExtSEEK schema snapshots (2026-05-27 vintage in `context/VINTAGE.json`)
- 9 Jinja2 templates for `/curate-init` to render into project working directories
- Comprehensive secrets-safe `.gitignore`
- Test suite: 9 test files covering template rendering + script CLI smoke tests + e2e init

### Sources
Scripts lifted from prior curation sessions:
- intravchip (Marie Floryan, Kamm lab) — `_common.py`, `nextseek_api.py`, `consolidate_to_flat.py`, `qa_flat_sheets.py`, `rename_files.py`, `omero_pull.py`
- srp/lee (Lee Pribyl, Engelward lab) — `smb_pull.py`, `stage_zenodo.py`, `apply_*_links.py`, `apply_geo_accessions.py`, `upload_geo_ncftp.sh`, `review_metadata_vs_uploads.py`, `deposit/geo_build_xlsx.py`

### Known limitations / v0.2 TODOs
- Several scripts contain IntravChip-specific defaults marked `TODO(v0.2)` for generalization (column indices in apply_geo_accessions; expected counts in qa_flat_sheets; figure-bucket defaults in stage_zenodo; plate-strategy table in smb_pull)
- GEO `validate` endpoint is dev-only — production validation not yet wired up
- `labs/` per-lab profile directory not yet shipped; lab knowledge lives in per-project CLAUDE.md + curator memory for now
- Per-arm `build_<arm>.py` scripts are generated by `/curate-build` per-project; no automated regression testing of the generator yet
- E2E init smoke test verifies template rendering + lockfile creation but doesn't verify Claude Code plugin loader behavior (requires manual session)
