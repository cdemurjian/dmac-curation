# `report` mode — submission artifact generation

Date: 2026-07-21
Status: proposed
Parent: `2026-07-21-curation-toolkit-design.md`

## Purpose

*"I have file X.xlsx with metadata — turn it into a GEO report."*

Produce repository submission artifacts (GEO, SRA, PRIDE) from whatever metadata
the curator has. The work is not rendering — the renderer already exists. It is
**mapping**: deciding which source field feeds which target field, and which
target fields must be written by hand.

## Scope

**In:** GEO, SRA, PRIDE.

**Out: nf-core samplesheets.** In chat_nextseek the nf-core path is a multi-turn
interactive wizard (`pipeline_agent`) that cannot complete in one shot, and it
carries Seqera/Tower launch concerns. Different problem; not this mode.

## Trigger and state

`/curate-report <FORMAT> <input>`, or conversationally.

**Input-scoped.** Reads a project lockfile when one is present (for lab and
project id) but must run without one, from any cwd.

## Input adapters

Inputs are **not** a mode switch. Each adapter normalizes into one internal shape.

| input | adapter behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | `POST /nextseek_api/admin/samples/retrieve/` |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

**Normalized shape** — what every adapter emits and every downstream step sees:

```
{ "samples": [ { "sample_type": "D.SEQ",
                 "uid": "D.SEQ-...",
                 "metadata": { <flat key/value> },   # lineage via "Parent" UID
                 "parent": "TIS-..." } ] }
```

This mirrors what `/admin/samples/retrieve/` returns, flattened. The API response
is nested five levels
(`data.data[i].samples[j].metadata`); lineage is the flat `Parent` key, an
upward UID pointer, **not** nesting.

**Enrichment is additive, never required.** If a UID resolves in NExtSEEK, fetch
and merge (existing values win — the leaf-wins rule). If a `Protocol` value
resolves to a SOP id, fetch it. Neither gates output.

## The chain

```
1. adapter -> normalized shape                                    deterministic
2. (optional) NExtSEEK enrichment for resolvable UIDs             deterministic
3. protocol resolution: find `Protocol` keys -> GET /sops/{id}/   deterministic
     -> download content_blobs -> docx/pdf text -> truncate
4. LLM emits a MAPPING SPEC                                       *** LLM ***
5. validate the mapping spec against the template + CV            deterministic
6. LLM writes only the `synthesize:` fields                       *** LLM ***
7. apply the mapping across all rows -> <FORMAT>_filled.json      deterministic
8. render to xlsx                                                 deterministic
9. validate the rendered artifact                                 deterministic
```

Only steps 4 and 6 need an LLM, and both are **O(columns), not O(rows)**.

## The mapping spec — the core of this design

The LLM does **not** write cell values. It writes a declarative mapping, once,
which is then applied deterministically to every row.

```json
{ "report_type": "GEO",
  "source": {"adapter": "curated_sheet", "path": "assay_sheets/ArmA.xlsx"},
  "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 117},
  "samples": {
    "*library name":          {"source": "UID"},
    "*organism":              {"const": "Homo sapiens"},
    "**tissue":               {"source": "Tissue", "via_lineage": true},
    "*instrument model":      {"const": "Illumina NextSeq 500"},
    "*single or paired-end":  {"source": "LibraryLayout",
                               "map": {"paired": "paired-end"}},
    "processed data file":    {"unmapped": "no processed files in source"} },
  "study": {
    "*title":   {"synthesize": "study title from manuscript context"},
    "*summary (abstract)": {"synthesize": "abstract"} } }
```

Directives:

| directive | meaning |
|---|---|
| `source` | copy from this source column |
| `via_lineage` | resolve by walking the `Parent` chain upward |
| `const` | same literal for every row |
| `map` | value normalization table |
| `synthesize` | free prose; the LLM writes it once (study-level only) |
| `unmapped` | deliberately empty, with a stated reason |

**Why this shape.** chat_nextseek's `report_writer_agent` has the LLM emit every
cell; that cost *"a 5.1M-token prompt on a 195-UID flow"*
(`reports/outputs.py:349-355`) and was hard-bypassed for nf-core. Its
`report_coder_agent` improves on that by having the LLM write extraction
**Python**, executed in an AST sandbox with a row-parity guard. A declarative
mapping achieves the same LLM-decides/code-executes split while being
validatable, human-reviewable, cacheable, and needing no sandbox.

**`map` earns its place.** SKILL.md already records the pitfall: GEO dropdowns
are word- and case-exact — `paired-end` not `paired`, `Illumina NextSeq 500` not
`NextSeq 500`. Value normalization belongs in the mapping, checked before any
row is written.

**The mapping is a cacheable artifact.** Same PI, same instrument, same assay
next quarter: reuse the mapping, skip step 4 entirely.

## Validation

**Step 5 — validate the mapping before applying it.** Cheapest place to fail.

- every target field exists in the template's field list
- every required (`*`) field is `source`/`const`/`synthesize`, or explicitly
  `unmapped` with a reason
- every `const` and every `map` output is a member of the template's controlled
  vocabulary where one exists
- every `source` column exists in the input

**Step 9 — validate the rendered artifact.** `validate_geo_xlsx` from
dmac-assistant's `artifact_validator.py`; its `ArtifactStatus` enum
(`Valid | Incomplete | SchemaInvalid | Missing | Unreadable`) maps onto
CLEAN / SOFT_FLAG / HARD_REJECT.

**Row-parity assertion.** Assert `len(rows) == expected_rows`. The executor
controls row count by construction, so this is structural rather than the
after-the-fact check chat_nextseek needs — but assert it anyway. Their own
assessment calls that guard the single most valuable idea to carry over.

## Outputs — to cwd

```
report/
  <FORMAT>.mapping.json        the mapping spec — reviewable, editable, reusable
  <FORMAT>.completeness.md     what could not be filled, and why
  <FORMAT>_filled.json         the applied result
  <FORMAT>_filled.xlsx         the rendered artifact
```

### Graceful degradation

Some GEO fields are derivable only from context an input may lack — organism,
tissue, and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. When an input cannot
supply them:

- write `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 —
  greppable; a blank is not), and
- record it in `<FORMAT>.completeness.md` with the field, the input searched,
  and why it failed.

The curator decides whether to fill by hand, enrich from another source, or
proceed. **Never silently fabricate; never refuse outright.**

## Rendering — pick one implementation

Two exist and they differ:

- ours: `scripts/deposit/geo_build_xlsx.py JSON TEMPLATE OUTPUT` (positional);
  capture/wipe/re-paste of static blocks
- chat_nextseek: `export_geo_report_to_seq_xlsx(report_json_path,
  template_xlsx_path, out_dir, *, one_workbook_per_uid=False)`; label-anchored
  row insertion; expects JSON keyed by UID (or `"all_samples"`), filtering
  entries where `payload["report_type"].upper() == "GEO"`, filling from
  `payload["report"]`

**Keep ours** — it is already a PEP 723 `uv` script, cwd-relative and
arg-driven — and match its input contract to whichever JSON shape is chosen.
Do not maintain both.

## Vendored assets

From `chat_nextseek/src/chat_nextseek/reports/templates/`:
`GEO-updated.json` (field spec + SRA-derived controlled vocabulary),
`GEO_template.xlsx`, `SRA_metadata.xlsx`, `SRA_biosample.xlsx`, `SRA.json`,
`pride.json`.

From `tavjo/dmac-assistant`: `tools/hibayes/artifact_validator.py`. Note
dmac-assistant also carries its own `GEO-updated.json` with a documented refresh
recipe — pick one, record which.

**Every vendored file needs a provenance manifest entry** (source repo, path,
commit SHA, date, local divergence). `sampletypes_db.json` already exists in
three copies at three vintages with no record of which is authoritative. Do not
add a fourth instance.

Do **not** cut from `docker/v3/docker/cc-runtime/build_context/plugins/nextseek/`
— that is a pre-hardening copy from an older commit.

## Fixtures — harvest, do not author

chat_nextseek persists exactly the API responses needed, on every report run
(`reports/outputs.py:555-563`):

| artifact | content |
|---|---|
| `report_metadata.json` | the `/admin/samples/retrieve/` response |
| `protocols.json` | the `/sops/{id}/` responses |
| `protocol_files.json` | downloaded blobs + extracted docx/pdf text |

Procedure: take UIDs from `e2e/catalog.json` family `reporting` (64 variants
with real production UIDs — `D.SEQ-221031SHA-67-PUB`, `D.SEQ-230512FOR-288-PUB`,
`D.MSP-230828GRI-4-PUB`), run
`uv run cli.py -q "Build me a GEO Submission for <UIDs>"` once, and copy the
three artifacts out of `~/.local/state/chat_nextseek/outputs/<run>/`.

Scrub credentials and localhost URLs, then commit. chat_nextseek has **no**
committed fixtures for this path — its entire corpus is two inline dicts — so
this is new coverage, not a copy.

## Protocol-chain gotchas

- Refs to `fairdata.mit.edu` are **not** fetched from that host — they are
  redirected to whatever `NEXTSEEK_BASE_URL` is. Only `fairdomhub.org` goes
  off-host, and it requires `FDH_API` as a bearer token with **no fallback**.
- Protocol refs are discovered from any metadata key literally named `Protocol`,
  matching a `/sops/{id}` URL or a bare `P.*` name.
- DOCX extraction is stdlib-only (unzip, read `word/document.xml`, strip tags).
  PDF needs `PyPDF2` and **silently yields nothing if absent** — fail loudly
  instead.
- Protocol text is truncated at ~3000 tokens upstream. Record truncation in the
  completeness report rather than letting it pass unnoticed.

## Relationship to Phase 10

`/curate-deposit geo` **delegates the build** to this mode and keeps only the
genuinely pipeline-specific parts: external upload (`upload_geo_ncftp.sh`) and
accession backfill (`apply_geo_accessions.py`).

Phase 10's GEO route is a dead end today — nothing produces the required
`BULK_filled.json` and no GEO template xlsx ships — so delegation is closer to a
free fix than a rewrite. Note the ordering is deliberate: GEO deposit happens
**before** NExtSEEK upload, because accessions must be backfilled into the sheets
first. That is why the curated-sheet adapter matters.

## Non-goals

- nf-core samplesheets (multi-turn wizard; different problem).
- An LLM API client. Steps 4 and 6 are skill instructions. This avoids porting
  `config.py` (83KB), `llm_clients.py` (30KB), and all provider credentials.
- Porting `reports/outputs.py` — a 400-line function with a hardcoded `if/elif`
  format dispatch. Write a real dispatcher.
- Uploading anything. This mode builds and validates; deposit uploads.

## Testing

- Mapping-spec validation rejects: unknown target field, missing required field
  with no `unmapped` reason, `const` outside the controlled vocabulary,
  `source` naming a column absent from the input.
- Round trip per format: fixture -> mapping -> filled JSON -> xlsx -> validator
  reports `Valid`.
- Row parity: N input rows produce exactly N sample rows.
- Each adapter produces the identical normalized shape from equivalent inputs.
- Degradation: an input lacking lineage produces `*** PLACEHOLDER: ... ***` and
  a completeness entry — not an exception, and not a silent blank.
- **A format is not "supported" until it has a renderer AND a validator.**
  chat_nextseek has a PRIDE template and row-key but no exporter, so PRIDE
  silently yields JSON only while its e2e catalog asserts `pride.xlsx`. Do not
  inherit that shape.

## Open questions

1. **Which `GEO-updated.json`** — chat_nextseek's or dmac-assistant's (which
   adds a documented refresh recipe)? Diff them, pick one, record it.
2. **Does `synthesize` need manuscript access?** Study title, summary, and
   experimental design are prose that likely live in `manuscript/`. In a
   curation project that is available; input-scoped runs elsewhere may have
   nothing, in which case these become placeholders.
3. **Is PRIDE in v1?** It needs a renderer written from scratch — chat_nextseek
   has none. GEO and SRA can reuse existing exporters. Consider deferring.
