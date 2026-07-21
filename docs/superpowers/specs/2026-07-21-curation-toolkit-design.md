# dmac-curation: from pipeline to toolkit

Date: 2026-07-21
Status: proposed
Scope: **architecture only.** Three follow-on specs — `schema` mode, `report`
mode, and a `pipeline-rework` review — each get their own document, following
the precedent of `2026-07-02-fdh-integration-design.md`.

## Problem

The plugin's identity is a *sequence*. `skills/curation/SKILL.md:3` describes it
as operating "via the 13-phase pipeline (inventory -> ... -> email PI)";
`SKILL.md:17-37` is a phase table with a hardcoded `#` column;
`commands/curate-status.md:10-18` is a hand-written phase->artifact map. Anything
that is not a point on that line has nowhere to live.

This is already a real constraint, not a hypothetical one. FDH — the plugin's
only non-pipeline capability — had to be bolted on as a separate `SKILL.md`
stanza (L39-46) carrying the disclaimer "NOT part of the 13-phase pipeline", plus
its own reference file, because `PHASES.md` is organized strictly as `## Phase N`.

Two more capabilities are now wanted: **schema authoring** (CEDAR-backed sample
type design) and **report generation** (GEO/SRA/PRIDE submission artifacts).
Neither is a phase.

## Insight: the mode pattern already exists and works

FDH is not a workaround. It is a working proof of the pattern, and it should be
generalized rather than replaced. It touches no phase artifact, no
`assay_sheets/`, and never writes the lockfile.

A **mode** is a convention, not a framework. Five slots; only the first two are
required:

| # | slot | path | required |
|---|---|---|---|
| 1 | entry points | `commands/<prefix>-*.md` | yes — auto-discovered, no registration |
| 2 | reference doc | `skills/curation/<MODE>.md` | yes — loaded on demand |
| 3 | routing prose | `SKILL.md` mode-table row + vocabulary lines | yes |
| 4 | intent index | `context/<mode>_index.json` | optional |
| 5 | code | `scripts/<mode>/` (+ `generated/REGISTRY.md`) | optional |

FDH fills all five: `commands/fdh-{upload,api}.md`, `skills/curation/FDH.md`,
`SKILL.md:39-46`, `context/fdh_api_index.json` (106 entries with `yaml_lines`
back-pointers so the 640KB spec is never read whole), `scripts/fdh/`.

`.claude-plugin/plugin.json` declares no commands, skills, hooks, or agents.
Everything is convention-discovered — **adding a file is registering it.** There
is no manifest to fight. The friction is entirely in prose and in path bugs.

## Changes

### 1. Identity prose

Rewrite the activation description in **three places that must stay in sync**
(they are currently duplicated verbatim, and `plugin.json` vs the lockfile
already disagree on version):

- `skills/curation/SKILL.md:3`
- `.claude-plugin/plugin.json:4`
- `.claude-plugin/marketplace.json:14`

New framing: dmac-curation is the **curator's workbench** for NExtSEEK /
FairDomHub — human-in-the-loop, PI-facing. The curation pipeline is one mode.

This is load-bearing: the description string is what the model matches on, so
non-pipeline modes are invisible to skill activation until it changes.

### 2. Phase table -> mode table

`SKILL.md:17-37` becomes a mode table. The phase table moves into `PHASES.md`,
which is already the pipeline's deep reference.

| mode | entry points | reference | state scope |
|---|---|---|---|
| `pipeline` | `/curate-*` (13 commands, 11 phases) | `PHASES.md` | project |
| `fdh` | `/fdh-*` | `FDH.md` | credentials only |
| `schema` | defined in the schema-mode spec | `SCHEMA.md` | **cwd-scoped** (see O1) |
| `report` | defined in the report-mode spec | `REPORTS.md` | **input-scoped** (see O3) |

"Cwd-scoped" for `schema`: reads plugin `context/` read-only, writes artifacts
into the current working directory. No lockfile, no scaffold required.

"Input-scoped" for `report`: the motivating request is *"I have file X.xlsx with
metadata, turn it into a GEO report"*, which need not be inside a curation
project. It reads a project lockfile when one is present (to pick up lab and
project id) but must run without one.

`commands/curate-status.md` reports **per mode**, not per phase.

### 3. Lockfile schema

`.dmac-curation.json` is flat and single-mode. Its schema exists only in prose,
in two places that already disagree (`commands/curate-init.md:46-59` hardcodes
`plugin_version: "0.1.0"` while `plugin.json` says `0.2.0`), and it has no
`schema_version`.

```json
{ "schema_version": 1,
  "plugin_version": "0.2.0",
  "modes": {
    "pipeline": { "phase": 6, "lab": "MF", "nextseek_project_id": 42 }
  } }
```

Rules:
- Modes that need no project never read it. `schema` must work from any cwd;
  `report` reads it opportunistically when present but must not require it.
- `curate-init.md:11-16` currently **refuses to run** if `CLAUDE.md` or
  `.dmac-curation.json` exist, so there is no "add a mode to an existing
  project" path. Init becomes additive: create missing scaffold, add the mode
  section, leave everything else alone.
- Migration: a lockfile with no `schema_version` is read as v0 and its flat keys
  are mapped into `modes.pipeline`.

## Prerequisites (blocking — do these first)

### P1. Path anchoring

Ten scripts resolve project paths against the **plugin install directory**:

```
_common.py:33                    ROOT = <plugin>
consolidate_to_flat.py:55        REPO -> SRC = <plugin>/assay_sheets
qa_flat_sheets.py:42             REPO -> DEFAULT_UPLOAD = <plugin>/assay_sheets/IntravChip_upload.xlsx
nextseek_api.py:44,49            REPO -> DEFAULT_CACHE_PATH, _load_dotenv
stage_zenodo.py:33               ROOT -> FILES = <plugin>/files
apply_zenodo_links.py:29         ROOT -> ASSAY = <plugin>/assay_sheets
apply_geo_accessions.py:39       ROOT -> SHEETS = <plugin>/assay_sheets
review_metadata_vs_uploads.py:36 ROOT -> SHEETS = <plugin>/assay_sheets
smb_pull.py:46,73-74             ROOT -> OUT_DIR = <plugin>/GEO/bulk_rna/fastq
upload_geo_ncftp.sh:19           cd "$(dirname "$0")/.."
```

`/curate-consolidate` and `/curate-qa` with no arguments therefore read and
write **inside the plugin checkout**. More modes means more entry points and
more ways to hit this.

Reference implementations that already do it right: `build_retrieve.py`
(cwd-relative, all paths as flags) and `fdh/fdh_api.py:161` (cwd `.env` first,
then plugin).

### P2. One project-config seam

Four scripts independently propose a project config in `TODO(v0.2)` comments
(`qa_flat_sheets.py:47-49`, `apply_zenodo_links.py:32`, `stage_zenodo.py:39`,
`review_metadata_vs_uploads.py:44`). Consolidate into one, resolved from cwd,
with CLI flags overriding. This is what makes the scripts mode-agnostic and is
the highest-leverage refactor in the plugin.

### P3. De-project `_common.py`

`scripts/_common.py` is not a shared library; it is IntravChip's constants.
`L38` hardcodes the literal filename `MetNet All 260527.xlsx`; `L46-51` hardcodes
HUVEC/MCF-7 UIDs; **`L55` is `SCIENTIST = "Marie Floryan"`**; `L58-66` carries
IntravChip section titles. Anything importing it inherits all of it.

Same residue in `qa_flat_sheets.py:52-70` (IntravChip row counts),
`rename_files.py:56-90` (Figure 1-7 dirs), `smb_pull.py:52` (`engelward` share).

Move project constants into the P2 config. Keep only genuinely shared logic
(`mint_uid`, the schema-driven column ordering at `_common.py:212-227`, which is
a real NExtSEEK-schema capability rather than a pipeline one).

## Immediate items (not part of this redesign — do now, separately)

**Secrets.** `working/fdh-upload-script/` contains a `.env` with a real FDH
token and `Assets/Output/session.json` with a plaintext token. Gitignored, so
not in history, but present on disk. Rotate and remove.

**Contradictory write-safety conventions in one phase.** `apply_geo_accessions.py`
and `apply_omero_ids.py` default to dry-run and require `--write`.
`stage_zenodo.py:107` and `apply_zenodo_links.py:93` use `--dry-run` and
therefore **default to writing**. `curate-deposit.md:33` claims all of them
default to dry-run. This is a data-loss trap; standardize on `--write`.

**Curation's context data is stale, and there is no way to refresh it.**
`context/neo4j_schema.json` is byte-identical (modulo `fetched_at`) to
chat_nextseek's `neo4j_schema_dev.json` — a **dev-instance** snapshot from
2026-03-26 carrying **23 `Sample` properties** where chat_nextseek's live copy
(2026-05-11) has **85**. `context/neo4j_assay-sample-conn.json` likewise differs
(176 edges vs 163). `context/VINTAGE.json` admits the gap: *"Refresh via
tools/refresh_context.py (planned, not yet implemented)"* — and `tools/` does not
exist.

chat_nextseek solves this already: `config.py:534 _fetch_context_files_from_db()`
pulls the source tables and writes full + `min_` pairs, gated by an `_is_today()`
freshness check. Four of curation's context files are **byte-identical** to
chat_nextseek's, so the shared-source case is not theoretical.

Action: either implement the promised refresh, or re-bundle from chat_nextseek's
current exports and record the vintage. Doing neither means every mode built on
this spec reasons about the graph from a stale dev snapshot.

**Command<->script drift.** Documented flags that do not exist:
`consolidate_to_flat.py --assay-sheets`; `review_metadata_vs_uploads.py
--retrieve` (so Phase 12 never reads `RETRIEVE.TXT`, contradicting
`PHASES.md:246`); `apply_geo_accessions.py --gse`; `apply_zenodo_links.py --write`;
`apply_omero_ids.py` invoked without its required positional. Root cause: no test
asserts command docs match script CLIs — `test_fdh_commands_present.py` does this
for FDH only. Add the `curate-*` analogue.

## Decomposition

This spec covers architecture. Three follow-on specs — `schema` mode, `report`
mode, and `pipeline-rework` (scoped in O2):

**`schema` mode** — CEDAR-backed sample type authoring. A field dictionary over
the ~1059 field names (none of which have any description, type, or vocabulary
today), ontology grounding via `bioportal-term-mcp` (standalone; needs no CEDAR
account or hosting), and mechanical CEDAR template emission. Output is a
*proposed* sample type record; **a human applies it.** Research and a worked
`MUS` prototype are at `/home/cdemu/code/dmac/research/CEDAR/`.

**`report` mode** — GEO/SRA/PRIDE generation. Design: the LLM produces a
**declarative mapping spec** (source column -> target field, constants, and which
fields need synthesis), which is validated against the template's field list and
controlled vocabulary, then applied deterministically across all rows. This
generalizes two lessons chat_nextseek learned the hard way: its per-value LLM
writer cost "a 5.1M-token prompt on a 195-UID flow" (`reports/outputs.py:349-355`)
and was hard-bypassed for nf-core; its `report_coder_agent` already does
LLM-decides/code-executes but via generated Python needing an AST sandbox and a
row-parity guard. A declarative spec is validatable, inspectable, cacheable, and
needs neither.

The plugin already owns the last mile: `scripts/deposit/geo_build_xlsx.py`
(filled JSON + template -> xlsx). It lacks the template xlsx, the field spec, and
the filler.

**The full chain, traced. Only step 4 requires an LLM.** Steps 1-2 below show
the *UID adapter* path; the local-xlsx adapters (see O3) replace them with a
file read and skip the API call entirely. Steps 3-6 are adapter-agnostic.

```
1. UIDs (from an xlsx, or RETRIEVE.TXT)                          deterministic
2. POST {NEXTSEEK_BASE_URL}/nextseek_api/admin/samples/retrieve/ deterministic
     body {"identifiers": [...]}, HTTP Basic, ?page_size=1000
     -> data.data[i].samples[j].metadata   (five levels deep;
        lineage is the flat `Parent` key, an upward UID pointer)
3. discover Protocol refs -> GET /nextseek_api/sops/{id}/        deterministic
     -> download content_blobs -> docx/pdf text -> truncate 3000 tok
4. map metadata -> report body matching GEO-updated.json         *** LLM ***
5. write {"all_samples": {"report_type":"GEO","report": <body>}} deterministic
6. render to xlsx                                                deterministic
```

Step 6 has two candidate implementations and they differ: our
`geo_build_xlsx.py` takes `JSON TEMPLATE OUTPUT` positionally, while
chat_nextseek's `export_geo_report_to_seq_xlsx(report_json_path,
template_xlsx_path, out_dir, *, one_workbook_per_uid=False)` expects a JSON
whose top level is keyed by UID (or `"all_samples"`), filters entries where
`payload["report_type"].upper() == "GEO"`, and fills from `payload["report"]`.
Pick one and delete the other; do not maintain both.

**Carry over the row-parity guard.** chat_nextseek gates on
`_REPORT_CODE_PATH_THRESHOLD = 20` target-type samples, and — crucially —
discards the deterministic result and falls back if
`len(result[row_key]) != expected_count`. Target types and row keys:
`{GEO: D.SEQ/samples, SRA: D.SEQ/libraries, PRIDE: D.MSP/sample_metadata}`.
Their own assessment calls this guard "the single most valuable idea to carry
over". Our mapping-spec design gets it more cheaply: the executor controls row
count by construction, so parity is structural rather than checked after the
fact. Keep the assertion anyway.

**A Claude Code plugin does not need an LLM API client.** chat_nextseek's
`call_llm_structured` is a 20-parameter wrapper over four provider clients with
JSON-repair retries. In a plugin, step 4 becomes *skill instructions* — the
agent reads the template plus a metadata profile and emits the mapping spec
directly. This removes `config.py` (83KB, eagerly loads 10+ context files and
fetches a remote API schema), `llm_clients.py` (30KB), and all provider
credentials from the port.

**Protocol-chain gotchas** (`reports/protocols.py`): refs to `fairdata.mit.edu`
are **not** fetched from that host — they are redirected to whatever
`NEXTSEEK_BASE_URL` is. Only `fairdomhub.org` goes off-host, and it needs
`FDH_API` as a bearer token with no fallback. DOCX text extraction is
stdlib-only (unzip, read `word/document.xml`, strip tags); PDF needs `PyPDF2`
and silently yields nothing if absent.

**Seeding fixtures — the pipeline already records them.** Every report run
persists three artifacts (`reports/outputs.py:555-563`), which are exactly the
API responses this work needs:

| artifact | content |
|---|---|
| `report_metadata.json` | the `/admin/samples/retrieve/` response |
| `protocols.json` | the `/sops/{id}/` responses |
| `protocol_files.json` | downloaded blobs + extracted docx/pdf text |

Non-report runs already leave `api_requests.json` and `api_result_bundle_*.json`
in the same run dirs (confirmed: four such dirs exist under
`~/.local/state/chat_nextseek/outputs/`).

So fixtures are harvested, not authored. Procedure: take a UID set from
`e2e/catalog.json` family `reporting` (64 variants with real production UIDs —
`D.SEQ-221031SHA-67-PUB`, `D.SEQ-230512FOR-288-PUB`, `D.MSP-230828GRI-4-PUB`),
run `uv run cli.py -q "Build me a GEO Submission for <UIDs>"` once, and copy the
three artifacts out of the run directory.

What is genuinely absent is fixtures **committed under `tests/`** — the whole
committed corpus is two inline dicts in `test_report_code.py` and
`test_report_outputs_gating.py`. Committing harvested artifacts (scrubbed of
credentials and any localhost URLs) is a deliverable of the report-mode work.

**Known broken:** PRIDE has a template and a row-key entry but **no exporter
branch**, so it emits JSON only — while `e2e/catalog.json` asserts
`api_artifact.pride.xlsx`. That variant appears unable to pass (UNVERIFIED).
Do not inherit this shape: in our design a format is not "supported" until it
has a renderer *and* a validator.

## Vendoring

Assets to bring from `tavjo/dmac-assistant` (private; MIT; active — 531 commits,
last push 2026-07-10) and from chat_nextseek:

- batch-upload module (~1,250 lines, plain `httpx`, no framework coupling) —
  notably its assay-superset guard and `invented_attribute` check
- `artifact_validator.py` — `validate_geo_xlsx` etc; its `ArtifactStatus` enum
  maps onto CLEAN / SOFT_FLAG / HARD_REJECT
- `GEO-updated.json` (field spec + SRA-derived controlled vocabulary),
  `GEO_template.xlsx`, `SRA_{metadata,biosample}.xlsx`

**Every vendored file gets a provenance manifest entry**: source repo, path,
commit SHA, date, and local divergence. Rationale: `sampletypes_db.json` already
exists in three copies at different vintages with no record of which is
authoritative — `curation_skill/context/neo4j_schema.json` is a *dev-instance*
snapshot from 2026-03-26 with 23 Sample properties, while chat_nextseek's live
copy has 85. Do not add a fourth instance of that problem.

Two traps: `_cmd_build_payload` raises `GateError("staging")` when `--out` is
under `/data/scratch`, which is where its own default env var points — the
default always fails. And **do not cut from
`docker/v3/docker/cc-runtime/build_context/plugins/nextseek/`**; that is a
pre-hardening copy from an older commit. Cut from `dmac-assistant` main.

## Relationship to dmac-assistant

Complementary, not converging. dmac-curation is the curator's workbench;
dmac-assistant is a containerized self-serve service for lab users. The boundary
is clean: dmac-assistant has **no FairDomHub client at all**, no PI-facing
workflow, and no CEDAR work; dmac-curation has no batch-upload hard gate and no
write-safety posture worth the name.

Near-term interop is free — both are Claude Code plugins and can be installed in
the same session, each providing what the other lacks. Anything richer (curation
calling the containerized service) is deferred.

## Open issues — must be resolved before implementation

### O1. RESOLVED — `schema` mode writes to cwd

`schema` mode reads the plugin's `context/` **read-only** and writes all
artifacts into the current working directory, wherever Claude was started. This
removes the P1 contradiction: no mode ever writes inside the plugin checkout.

Revised state scope: `schema` is **cwd-scoped**, not global. It requires no
project lockfile and no scaffold, but its outputs land where you are.

**Known consequence, accepted:** the field dictionary does not accumulate across
projects. Descriptions and ontology IRIs curated while bolstering `D.VIA` in one
directory do not help the next curator elsewhere. The read-only inputs
(`sampletypes_db.json`, ~1059 field names) are shared; the enrichment is not.

Mitigation, deferred to the schema-mode spec: allow a curated dictionary to be
*promoted* back into the plugin repo by an explicit, human-reviewed commit —
the same "propose, human applies" posture used for sample type records. Not a
v1 requirement.

### O2. `report` mode overlaps Phase 10 — and triggers a pipeline review (blocking)

**Status: the review is complete** — see
`2026-07-21-pipeline-rework-review.md`. Its verdict: the pipeline is sound and
needs correcting, not reworking. Net change **13 phases -> 11** (delete Phase 4,
which has no command, and Phase 8, already folded into Phase 7), keep the 4-sheet
intermediate because curators review it, and keep both upload formats.

Evidence that prompted the review:

- Phase 4 has **no command** — TaskList state only.
- Phase 8 is **folded into Phase 7** — same command, same invocation.
- 5 of 14 phases (2, 3, 4, 8, 13) invoke **no script** — pure prompt + template.
- Phase 10's GEO route is a **dead end** (no producer for `BULK_filled.json`,
  no template xlsx shipped).
- Phase 12 **never reads `RETRIEVE.TXT`** despite `PHASES.md:246` naming it as
  an input — the documented flag does not exist.
- Five documented flags do not exist in their target scripts.

**The central question:** Phase 5 builds 4-sheet workbooks and Phase 6
consolidates them to flat — but flat is what NExtSEEK ingests, and
dmac-assistant's batch-upload design *explicitly drops the 4-sheet workbook* for
a flat sheet. Do Phases 5 and 6 collapse, eliminating `4sheet_originals/`?
There may be a good reason to keep it (4-sheet as the human-readable working
form, flat as the machine format) — the review must establish this, not assume
it either way.

Scope for that review: per phase, what it does, whether it is load-bearing,
whether it earns being a separate step, and what merges or deletions the
evidence supports.

**Phase 10 overlap — decided: delegate.** `pipeline` mode's Phase 10
(`/curate-deposit geo`) already claims GEO, and `scripts/deposit/geo_build_xlsx.py`
is the renderer both would use. Phase 10 delegates the build to `report` mode and
keeps only the genuinely pipeline-specific parts — external upload
(`upload_geo_ncftp.sh`) and accession backfill (`apply_geo_accessions.py`). The
alternative, two GEO paths, is the exact divergence this spec warns against
elsewhere. Because the route is a dead end today, delegation is closer to a free
fix than a rewrite.

### O3. RESOLVED — variable inputs via adapters, with graceful degradation

`report` mode must accept whatever the curator has. Inputs are **not** a mode
switch; they are adapters that normalize into one internal shape.

| input | adapter behaviour |
|---|---|
| NExtSEEK UIDs (args, or a `RETRIEVE.TXT`) | `POST /admin/samples/retrieve/` |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | read locally; no API call |
| curated upload sheet (`Arm{X}.xlsx`) | read locally; works **before** upload |
| arbitrary xlsx / csv | read locally; columns mapped by the LLM step |

All adapters emit the same normalized structure the chain already expects:
typed sample groups, each sample a flat metadata dict, lineage carried as a
`Parent` UID pointer. Downstream steps — protocol resolution, the LLM mapping
step, rendering, validation — are adapter-agnostic and see only that shape.

**Enrichment is additive, never required.** If a UID happens to resolve in
NExtSEEK, fetch and merge it (existing values win, matching the leaf-wins rule
in `build_accession_metadata_lookup`). If a `Protocol` value resolves to a SOP
id, fetch it. Neither is a precondition for producing output.

**Unfillable fields degrade, they do not abort.** Some GEO fields are commonly
derivable only from context an input may lack — organism / tissue / cell line
frequently live on *ancestor* samples rather than the `D.SEQ` row, and protocol
prose requires a resolvable SOP id. When an input cannot supply these:

- emit the plugin's existing `*** PLACEHOLDER: <what is missing> ***` marker
  (SKILL.md hard rule 8 — greppable, unlike a blank), and
- emit a **completeness report** naming each unfilled required field, the input
  that was searched, and why it failed.

The curator decides whether to fill by hand, enrich from another source, or
proceed. The tool never silently fabricates and never refuses outright.

This also explains why Phase 10 is currently a dead end in a more useful way
than "missing file": it was already designed around a local-xlsx input
(`previous_metadata/*_AllMetadata*.xlsx`) and already has the renderer. Only the
mapping step was missing.

### O4. Minor — the proposed mode-table test as written is wrong

"a test asserting the mode table lists exactly the `skills/curation/*.md`
reference docs present" would glob `SKILL.md` itself. Exclude `SKILL.md`, or
keep an explicit list of reference-doc names.

## Non-goals

- Migrating the 101 existing sample types to CEDAR templates.
- Changing the NExtSEEK schema or upload format.
- Rewriting the curation pipeline. The `pipeline-rework` review is complete
  (`2026-07-21-pipeline-rework-review.md`) and concluded it is sound: 13 phases
  become 11 by deleting two bookkeeping entries, plus defect fixes. No
  structural rework.
- Self-hosting CEDAR (see the research: single-Nexus supply chain, no published
  images, no documented production install path).
- Merging with dmac-assistant.

## Testing

- Lockfile v0 -> v1 migration, both directions of the "does this mode need a
  project?" branch.
- A `curate-*` analogue of `test_fdh_commands_present.py` asserting every
  documented flag exists in the target script's parser. This would have caught
  all five drift bugs above.
- Path-anchoring regression: run each script from a tmpdir and assert nothing is
  written inside the plugin checkout.
- Existing template-render tests (`test_templates_render.py`) extended for the
  mode-aware `CLAUDE.md.j2`, which currently bakes the 11-step pipeline order
  into every scaffolded project (`CLAUDE.md.j2:17-35`).

## Risks

- **Prose drift.** With no manifest, the mode table, `curate-status`, and the
  three identity strings are hand-maintained. Mitigation: a test asserting the
  mode table matches the reference docs actually present — globbing
  `skills/curation/*.md` **excluding `SKILL.md` itself** (see O4).
- **P1/P2/P3 touch working scripts.** They are the pipeline's guts and have only
  `--help` smoke tests. Sequence: add path-anchoring tests first, then refactor.
- **Scope.** Three modes plus prerequisites is more than one implementation
  plan. This spec deliberately stops at architecture.
