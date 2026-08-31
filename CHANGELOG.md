# Changelog

All notable changes to dmac-curation will be documented in this file.

## 0.5.0 - 2026-08-17

Protocols become a pipeline phase instead of a per-project one-off.

### Added

- **`/curate-protocols` (phase 3b)** - author the protocol `.docx` set from the
  manuscript Materials and Methods, cross-check it against the sample tree, and
  register it on NExtSEEK as SOP records. It sits between Questions (3) and
  Build (5) for a hard reason: the `Protocol` column of every upload row carries
  a **SOP title verbatim**, so the SOP has to exist before Phase 5 writes rows
  that cite it, and the tree is what says which assays need documenting.

  Numbered 3b, not 4. Phases 4 and 8 are retired numbers that are never reused,
  so an inserted phase takes a letter suffix, the same convention `/curate-qc`
  uses for 9b.

- **`scripts/build_protocols.py`** - renders one
  `P.<LAB>-<STAMP>-V<n>_<Topic>.docx` per manifest entry, plus a
  `protocols/COVERAGE.md` carrying Table A (protocol to sample-tree edge) and
  Table B (edge to protocol coverage). The script is deterministic; the judgment
  lives in two JSON files the model writes, `protocols/_methods.json` (verbatim
  Methods sections) and `protocols/_manifest.json` (which sections group into
  which protocol, and the assay each documents). Three checks fail the build: a
  heading the manifest wants but the methods file lacks, a section consumed more
  or fewer times than it occurs, and a body paragraph that did not round-trip
  verbatim out of the written document. Ported from the hand-built Shenoy
  curation, and verified to reproduce all 15 of its delivered documents exactly.

- **`scripts/upload_sops.py`** - registers the set on NExtSEEK. Previews by
  default, and **asks a human before writing**: a bare `--write` is REFUSED
  before any network call and must be paired with `--confirmed`, which asserts
  that a person saw the preview and approved it. Approval to run phase 3b is not
  approval to upload, because SOP records land in a catalog every curator on the
  project shares and there is no clean undo. Same shape as `sampletype_attr.py`,
  where a live schema write costs `--apply` plus `--yes-production`. Works around
  two server behaviours reported as
  [BioMicroCenter/NExtSEEK#109](https://github.com/BioMicroCenter/NExtSEEK/issues/109):
  `POST /nextseek_api/sops/` can return HTTP 500 with an HTML body **while still
  creating the record**, so the result is verified against the server rather than
  the response; and it rewrites the submitted title with a `<YYMMDD>-V<n>_`
  prefix, so the canonical title is set by a following `PATCH`. Writes
  `protocols/_sops.json`, which fills the SOP column of Table A.

- **`templates/PROTOCOLS.md.j2`** - the narrative half of `protocols/README.md`:
  naming convention, provenance, and open items. `COVERAGE.md` stays a build
  artifact and is never hand-edited.

### Behavior worth knowing

- **A study with no written Methods gets no protocol files.** It gets the
  coverage report and a question per uncovered assay instead. A
  `*** PLACEHOLDER ***` marker is right in a spreadsheet cell, where QA greps for
  it; it is wrong in a SOP, which gets registered on a shared server and emailed
  to a PI as if it described a real procedure. Phase 5 proceeds with a blank
  `Protocol` column.
- **An existing `.docx` is never overwritten without `--force`.** If it is
  already registered or emailed, bump `version` to `V2` rather than rewriting
  `V1` underneath the record that cites it.
- Every batch authors its own protocol set. `upload_sops.py` skipping a filename
  it already sees is idempotency for re-runs, not reuse of another curator's SOP.

## 0.4.0 - 2026-07-31

Server-side validation, a human-readable review artifact, and a working route for
adding sample-type attributes.

### Added

- **`/curate-qc` (phase 9b)** - validate the consolidated upload file against the
  **live** NExtSEEK server before uploading, and triage what comes back. `/curate-qa`
  is entirely local: it checks row counts, parent resolvability and required fields,
  but cannot know which attribute names the server recognises. On its first real run
  `/curate-qa` reported 199/213 clean while the server rejected 121 rows outright.
  **A clean `/curate-qa` is not evidence an upload will succeed.** Run both.
- **`scripts/sampletype_attr.py`** - add an attribute to a live sample type. Dry-run by
  default; `--apply` to write; production additionally requires `--yes-production`
  (accepted anywhere on the command line). Verified end to end on dev then production.
- **`/curate-sampletype apply`** - the explicit write verb, wrapping the above. Schema
  writes stay in schema mode; `/curate-qc` only diagnoses and hands off. Patching a
  shared vocabulary must never be a side effect of a QA-shaped command.
- **`Arm{X}_review.xlsx`** from `/curate-consolidate` - the same rows as the upload
  file, one sheet per sample type, every field in its own column. The flat file packs
  each sample into a single `json_metadata` blob, which is right for NExtSEEK and
  unreadable for a person. Read the review file; upload the other.
- **Interactive `SAMPLE_TREE.html`** from `/curate-sample-tree`, rendered from a new
  `sample_tree.json` by `scripts/build_sample_tree_html.py`. Click any node or edge for
  its evidence quotes, rationale and flags. Contributed via PR #2.
- `nextseek_api.py sampletype-get` - read a sample type's real attribute list.

### Fixed

- **`PATCH /nextseek_api/sample_types/{id}/` does not work and never did** for any
  sample type that has samples. It proxies 1:1 to SEEK, which enforces
  `allow_new_attribute? = !samples?` and returns 422; the proxy never checks the
  upstream status, so it surfaces as a generic `502 "Invalid upstream response"` with
  the real message discarded. `sampletype-add-attribute` is retired and now fails with
  an explanation and a pointer to the working tool.
- Four attribute names in the shipped guidance that the live server rejects:
  `Bead_region` (does not exist on any type), `Bead_coating_vendor` (D.FCRB wants a
  capital V; D.ADCP has no such field), `Dilution` on D.ADCD, and
  `QuanitifcationMethod` - a typo carried by `context/sampletypes_db.json` itself.

### Known issues

- **A newly added sample-type attribute is invisible to `/curate-qc` and to the upload until
  the NExtSEEK app workers are restarted.** `prefetch_sample_type_attributes` caches attribute
  titles per worker process with no TTL and no invalidation on write, so each worker keeps
  whatever it saw first and requests round-robin across differing views. The web attributes
  page shows the new field while validation denies it. Documented in `/curate-qc`; the fix
  belongs upstream (invalidate on `sampleAttributeSave`, or add a TTL).
- `scripts/sampletype_attr.py` is a **stopgap** that drives an admin-UI endpoint: superuser-only,
  a GET with JSON in query params, and no Rails validation. It should be replaced by a proper
  `nextseek_api` REST write endpoint wrapping `DBtable_sampleattribute` + `updateSampleType`.

### Changed

- `/curate-init`'s rendered `CLAUDE.md` now lists 12 phases including `/curate-qc`, and
  names the review and sample-tree artifacts.
- Three new SKILL.md pitfalls: the live server outranks both the workbook and the
  bundled schema for attribute names; the sample-type PATCH constraint; and the fact
  that a row fails if *any* of its fields is invalid, so a schema patch can be correct
  and still not move the pass count.

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
