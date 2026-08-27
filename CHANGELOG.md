# Changelog

All notable changes to dmac-curation will be documented in this file.

## 0.5.0 - 2026-08-27

A fifth mode. `assay` is house-scoped assay hygiene — one production extract, all
projects, no PI — and it is the first thing in this plugin that writes to production.
Alongside it: `/curate-init` learned to guess the project, the lab and the PI;
`/curate-build` gained a UID-stamp collision guard; and `schema` mode gained two
external grounding sources.

### Added

- **`assay` mode - 8 commands, `skills/curation/ASSAY.md`, 39 modules under
  `scripts/assay_hygiene/`.** It finds NExtSEEK samples that should be registered
  against an internal assay and are not, puts every proposal in front of a human, and
  writes the approved ones to production. The order is `/curate-assay-init` →
  `-vocabulary` → `-detect` → `-review` → `-resolve` → `-write`, with `-status` and
  `-backup` safe at any point. **House-scoped, not project-scoped:** one extract, all
  projects, no lockfile, no PI. 40 test modules cover it.
- **Numbered immutable runs.** `/curate-assay-init` creates `assets/RUN<n>/` with eight
  tiers and chmods `00-rulings` through `06-findings` read-only **at creation**, not at
  the end - a tier that is writable for the duration of a run is a tier the run can
  destroy, and the artifacts most worth protecting are written first. State is
  `assets/assay-run.json`; a second `init` refuses while one is open, because two
  concurrent write phases assign `MAX(id)+1` primary keys with no lock.
- **A durable ruling store that outlives the runs** - `assets/rulings/pairs.tsv`, keyed
  on `(sample_type, internal_assay_id, action)`. RUN1 filed verdicts under
  `lab|sample_type|parent_types|assay_title|field|value`; four of those six fields move
  with the extract, so a new extract matched almost none of them and **261 rulings
  became worthless without a single judgement having changed**. The pair key survives
  all four. It is also *coarser* than the cohort it was ruled against: measured on
  RUN1, 200 ruled rows collapse to 127 keys and 5 of those carry conflicting verdicts.
  **A conflict is escalated, never averaged** - `rulings.save` raises rather than
  picking a winner, and `/curate-assay-init` reports conflicting keys instead of
  merging them.
- **`/curate-assay-write`, behind eight refusals** (`scripts/assay_hygiene/preflight.py`).
  Every one is a live failure mode of `/seek/sampleupload/`, not a hypothesis: a Current
  pair of two ints is the sole combination that reaches `deleteOneRecord`; an
  unparseable New pair drops the registration and reports success; a blank UID raises
  mid-run on a path with no transaction, leaving a committed prefix; a sheet named
  `UPDATE` hijacks dispatch into the metadata-update path; a row absent from the
  gate-checked manifest was never project-checked; no rollback handle means `MAX(id)`
  was never captured and the run cannot be undone; a backup without both non-zero size
  and a verified trailer is not a backup (a `mysqldump` once exited 0 having written 0
  bytes); and a chunk above 2,000 rows meets gunicorn's 1200 s SIGKILL. Rows go up in
  2,000-row chunks, each reconciled against a `COUNT(*)` - `chunker.reconcile` refuses
  an over-count as well as a short write.
- **A hard project gate on SEEK assay ids** (`scripts/assay_hygiene/resolve_targets.py`).
  SEEK assay ids are per-project: the same internal assay is a different `assay_id` in
  every project that runs it, and a registration landing on the wrong one puts the
  sample into a project it does not belong to, which nothing undoes from outside. The
  2026-08-26 audit found **578 of 26,188 rows** in exactly that state - 159 repairable,
  419 not. `resolve` now emits a manifest gate-checked at build time, and
  `assert_subset` is what `write` uses to prove the submitted sheet never grew a row the
  gate did not see. An excluded row is an authorised registration with no correct
  target, and is reported as such rather than silently dropped.
- **Backups that are read back before they are believed.** `store_backup.back_up`
  re-opens the tarball it just wrote and refuses unless `pairs.tsv` is inside.
  `/curate-assay-review` backs up on every ingest; `/curate-assay-backup` does it on
  demand. `/curate-assay-init` refuses to open a run at all when the store is missing,
  because **nothing regenerates a human ruling** - not compute, not a re-run.
- **`/curate-init` auto-detects project, lab and PI.** `scripts/detect_context.py` ranks
  projects by token overlap with your inputs, aggregates UIDs per lab code across a
  project export, boosts the lab whose author surname matches, then guesses the PI.
  Surfaced as `nextseek_api.py detect-context` and confirmed with one tap. The ranking
  logic is network-free so it is unit-testable offline.
- **`nextseek_api.py pull-db`** - download a project's full DB export into
  `previous_metadata/` and print sheet and row counts. This is the fresh pull the stamp
  guard requires.
- **`scripts/stamp_guard.py` - the UID-stamp collision guard.** Minting from N=1 into a
  `<YYMMDD><LAB>` stamp another curation batch already owns **silently overwrites that
  study on upload** (two consecutive-day collisions in one lab, 2026-07). `preflight()`
  refuses a build
  unless a DB pull under 24 hours old is present and the intended stamp is unused, and
  names the nearest free stamp when it refuses. `/curate-qa` carries the matching net: a
  new UID already in the master baseline is a HARD_REJECT. Both carry environment-only
  escape hatches - `STAMP_GUARD_OVERRIDE=1` and `QA_ALLOW_DB_UPDATES=1` - which leave no
  trace on the command line.
- **`.env` provisioning from `$DMAC_ENV_FILE`.** `/curate-init` copies the file that
  variable points at to `./.env` and `chmod 600`s the copy; it never reads the values.
  Keep the filled credentials file outside every git repo and export the variable from
  your shell profile.
- **`schema` mode grounds attribute proposals in OBI and CEDAR.** BioPortal can say
  which *values* a field may take but not which *fields* a sample type should carry -
  its REST API exposes only a class's annotation properties, never the OWL restrictions
  describing an assay's inputs and outputs. Two sources now fill that gap and **neither
  mints a field**: `terms.clade_neighbors` walks a matched class's parents and children
  (OBI splits `cell viability assay` by detection chemistry - Annexin V, ATP
  bioluminescence, resorufin - which D.VIA does not capture), and
  `templates.template_fields` reads one pinned CEDAR template as a **checklist**. The
  shared library cannot be selected by assay name, so `common assay template` is pinned
  by `@id` and diffed against the type. Nothing is vendored; both degrade to an empty
  section that states its reason when `BIOPORTAL_API_KEY` / `CEDAR_API_KEY` is absent.
- **`tests/test_identifier_exposure.py`** - a ratchet on the identifier-shaped strings
  this **public** repository exposes, beside the existing credential guard. It goes red
  when the count grows *and* when it shrinks, so a cleanup tightens the baseline rather
  than leaving it stale. The two holes it started with each hid a real identifier: case
  (four protocol titles were written lowercase and an `[A-Z]{3}` pattern cannot see
  them) and binaries (`git grep -I` skips them by design, and `tests/fixtures/sample.xlsx`
  carried three UIDs inside its zipped sheet XML).

### Changed

- **The plugin has five modes, not four.** `skills/curation/SKILL.md`'s mode table now
  lists all 26 commands across `pipeline` / `fdh` / `schema` / `report` / `assay`, and
  `/curate-assay-vocabulary` moved from the `schema` row to the `assay` row.
- **The canonical description names `assay` and carries an activation cue for it.** The
  string is byte-identical across `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `skills/curation/SKILL.md` frontmatter and
  `tests/test_identity_sync.py`, and skill activation matches on it - so until now
  nothing in the activation surface mentioned assay hygiene, and `assay` is house-scoped,
  so not one of the four path cues fired for any of its work. `assets/assay-run.json` and
  "assay hygiene" are now cues, and a new test asserts every mode has one.
- **The documentation was audited against the code and rewritten where it disagreed.**
  55 confirmed drift findings across `README.md`, all five reference docs, both
  manifests and `docs/`; the full audit, with per-file evidence, is preserved at
  `docs/audit/2026-08-27-docs-audit/`. Three documents asserted the plugin *cannot* do
  something it demonstrably does - see the first three Fixed entries below.
- **CEDAR is no longer wholly out of scope.** 0.3.0 recorded why CEDAR *templates* are
  not adopted as an artifact model; that reasoning stands and nothing emits a CEDAR
  template. What changed is that a pinned CEDAR template is now *read*, over the live
  API, as a field checklist in `schema` mode.
- **The test suite now reports what it did not measure.** `tests/conftest.py` prints a
  banner naming every test skipped for a missing extract. Those fixtures carry real
  sample identifiers and this repository is public, so a fresh clone and CI always skip
  them - and a `1196 passed / 16 skipped` baseline was read as healthy for days while 21
  tests silently skipped. **A green suite is not evidence the assay pipeline was
  measured.**
- **Dependencies are declared once, in `pyproject.toml` plus a tracked `uv.lock`.** The
  bounds in `pyproject.toml` are floors - the same ones the PEP 723 headers already
  declared - and `uv.lock` is the reproducibility guarantee, which is why it is
  deliberately committed. `pyproject.toml`'s version had drifted two releases behind
  without a test noticing; it is now asserted equal to `plugin.json`.
- **`.gitignore` gained seven exclusion classes**, each with the incident that caused it
  written above it: `assay-hygiene/` and the prefix glob `assay-hygiene-*/`; `assets/`;
  unanchored `*rulings*.tsv` and `*verdicts*.csv`; `.claude/`; and
  `scripts/fdh/generated/*.py`. Read the comments before editing it - they are the
  incident record, not decoration.

### Fixed

- **`README.md` claimed the plugin never writes to NExtSEEK.** Both "What this is not"
  promises were false: `/curate-sampletype apply` edits a live sample type and
  `/curate-assay-write` writes registrations to production. The README already said so
  in its own schema-mode table, and contradicted itself four sections later. Both write
  paths and their guards are now named where the denial used to be.
- **`SCHEMA.md` listed "writing to NExtSEEK" as a non-goal** while being the doc
  `commands/curate-sampletype.md` orders the operator to read *first*, before the one
  command in the mode that writes to production. It now carries the full guard chain.
- **`FDH.md` promised a host override that the uploader does not honour.** The
  `FDH_BASE_URL` / `--base-url` bullet covered both modules; `scripts/fdh/submit.py`
  hardcodes `https://fairdomhub.org/` and takes neither, so every `/fdh-upload` run
  writes to production. The bullet is now split per module.
- **Mode 2's lineage lane never met the reachability gate.**
  `gate.type_registration_index` calls a (sample type, assay) pair absent from it
  incredible whatever the term's support, and the gate has always blocked a metadata
  claim on such a pair - but a lineage neighbour carries no claim, so nothing ever put
  the lineage lane in front of that rule. Measured on the 2026-08-21 extract, **99,449
  of 167,454 emitted Mode 2 rows - 59.4% - proposed a (type, assay) pair the house has
  never once made**, and every one reached the operator with a blank `gate`. `Evidence`
  gains a `reachable` boolean derived from the same index the gate already holds.
  **Nothing was deleted**: the rows are reclassified into their own step and still
  emitted, and the before/after `findings.csv` differ only in `classification` and
  `gate`, on exactly those 99,449 rows.
- **Internal assay 143 was named for the wrong GPT** - "Alanine Aminotransferase
  (ALT/GPT) Activity Assay", while SEEK assay 26 that it maps is the gpt delta mutation
  assay. Found by two independent agent readings during Mode 2 calibration and confirmed
  against the extract.
- **The write protection that four files claimed existed was never applied.** Resolved
  through the symlink tree, 27 of 33 artifacts were clobberable by a run left on default
  paths. `/curate-assay-init` now performs the chmod in code, and
  `_writeguard.assert_writable` refuses to write through a symlink into a preserved run.
- **A missing prerequisite is named instead of raising a bare traceback**, and the
  under-reporting in the unmeasured-work banner itself was closed.
- **Every real sample and protocol identifier is out of the tracked tree.** Each was
  *replaced*, not deleted - the surrounding assertions and prose need a well-formed
  identifier - by moving its `<YYMMDD><LAB>` batch stamp into a reserved synthetic band,
  `19MMDD`, which no uuid in the extract carries for any lab. Keep new fixtures in that
  band.

### Known issues

- **`/curate-status` has no `assay` branch.** `scripts/status.py` builds exactly four
  mode keys, and `commands/curate-status.md` still says "all four dmac-curation modes".
  The mode carries its own `/curate-assay-status` instead.
- **Carry-forward carries nothing.** `carryforward.split` sorts every cohort three ways -
  already ruled, ruled in a narrower context, never seen - but nothing derives
  `ruled_width`, so callers pass `{}`, every matched pair lands in *widened*, and
  `/curate-assay-detect` re-asks everything. The split is real; the carry-forward is not
  the finished feature. Root cause is the provenance sidecar that `rulings.py` and
  `carryforward.py` both describe and nothing writes.
- **Three artifacts in the assay workflow have no producer.** `ingest.ingest` refuses a
  sheet without a literal `cohort_key` column and no review surface emits one;
  `/curate-assay-resolve` reads `approved-rows.csv`, which nothing writes; and nothing
  builds the `UPDATE_ASSAY` sheet `/curate-assay-write` submits. Until those close,
  review → resolve → write is driven by hand.
- **Two documented flags do not exist.** `curate-assay-write.md` says "It writes nothing
  without `--confirm`", and `init_run.py`'s refusal message names
  `curate-assay-init --migrate-from`. There is no CLI in the assay mode at all - every
  command is `python -c` / `python -m` snippets and the production write is a manual
  submission - so there is no flag to pass.
- **The assay commands do not follow hard rule 6.** They invoke
  `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -m assay_hygiene.<module>`
  rather than `uv run --script`, because the PEP 723 headers on those modules are inert
  under `-m` and `-c`, which is why the dependencies are passed explicitly. Rule 6 now
  documents both forms rather than prescribing one that does not work.
- **A lost machine is a lost campaign.** The ruling store is gitignored and its only
  protection is a tarball on the same machine - the accepted cost of keeping identifiers
  out of a public repository. `git clean -xdf` lists `assets/` for removal.

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
