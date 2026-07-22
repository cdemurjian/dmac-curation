# `report` mode - submission artifact generation

Deep reference. Load when entering report mode.
Design: `docs/superpowers/specs/2026-07-21-report-mode-design.md`.

## Purpose

*"I have file X.xlsx with metadata, turn it into a GEO report."*

The work is not rendering - the renderer already existed. It is **mapping**:
deciding which source field feeds which target field, and which target fields
must be written by hand.

## State scope

**Input.** Reads a project lockfile when present, for lab and project id, but
runs without one from any cwd. Output goes to `./report/`.

## Formats

| format | row section | row key | target type | artifact |
|---|---|---|---|---|
| GEO | `samples` | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries` + `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata_filled.xlsx` + `SRA_biosample_filled.xlsx` |
| PRIDE | `sample_metadata` + `file_mapping` | `sample_metadata` | `D.MSP` | `submission.px` |

**PRIDE is not a spreadsheet.** `pride.json` declares a tab-delimited
ProteomeXchange Submission Summary File v2.2.1 with `MTD` / `FMH` / `FME` /
`SMH` / `SME` / `COM` line prefixes. chat_nextseek's e2e catalog asserts
`pride.xlsx`, which names the wrong artifact type; it has no exporter at all.
Ours is written from scratch and validated.

**Out of scope: nf-core samplesheets.** A multi-turn interactive wizard with
Seqera/Tower launch concerns. Different problem.

## The mapping spec - the core of the design

The LLM does **not** write cell values. It writes a declarative mapping, once,
applied deterministically to every row. Both LLM steps are **O(columns), not
O(rows)**.

Why: chat_nextseek's `report_writer_agent` has the LLM emit every cell, which
cost *"a 5.1M-token prompt on a 195-UID flow"* (`reports/outputs.py:349-355`)
and was hard-bypassed for nf-core. Its `report_coder_agent` improves on that by
having the LLM write extraction Python, run in an AST sandbox with a row-parity
guard. A declarative mapping achieves the same LLM-decides / code-executes split
while being validatable, human-reviewable, cacheable, and needing no sandbox.

Directives: `source`, `via_lineage`, `const`, `map`, `synthesize`, `unmapped`.
`synthesize` is study-level only, so it stays O(1).

**The mapping is a cacheable artifact.** Same PI, same instrument, same assay
next quarter: reuse it and skip the mapping step entirely.

## Input adapters

Inputs are **not** a mode switch. Each adapter normalizes into one shape and
every downstream step is adapter-agnostic.

| input | behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | `POST /nextseek_api/admin/samples/retrieve/` |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

Normalized shape:

```
{"samples": [{"sample_type": "D.SEQ", "uid": "D.SEQ-...",
              "metadata": {<flat key/value>}, "parent": "TIS-..."}]}
```

The API response is nested five levels (`data.data[i].samples[j].metadata`);
lineage is the flat `Parent` key, an upward UID pointer, **not** nesting.

## Two-stage validation

**Stage 1, before applying:** every target field exists in the template; every
required (`*`) field is `source`/`const`/`synthesize` or explicitly `unmapped`
with a reason; every `const` and every `map` output is in the controlled
vocabulary where one exists; every `source` column exists in the input; and a
column that lives only on ancestors carries `via_lineage`.

**Stage 2, after rendering:** the vendored artifact validator. Its statuses map
onto the pipeline's vocabulary: `Valid` = CLEAN, `Incomplete` = SOFT_FLAG,
`SchemaInvalid` / `Missing` / `Unreadable` = HARD_REJECT.

**Row parity is asserted** even though the executor controls row count by
construction. chat_nextseek's own assessment calls that guard the single most
valuable idea to carry over.

## Graceful degradation

Some GEO fields are derivable only from context an input may lack - organism,
tissue and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. When an input cannot
supply them:

- write `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 -
  greppable; a blank is not), and
- record it in `<FORMAT>.completeness.md` with the field, the input searched,
  and why it failed.

**Never silently fabricate; never refuse outright.**

## No LLM API client

chat_nextseek's `call_llm_structured` is a 20-parameter wrapper over four
provider clients with JSON-repair retries. In a Claude Code plugin the mapping
and synthesize steps are **skill instructions** - the agent reads the template
plus a metadata profile and emits the mapping directly. That removes `config.py`
(83KB, eagerly loads 10+ context files and fetches a remote API schema),
`llm_clients.py` (30KB), and all provider credentials from the port.

## Protocol-chain gotchas

- Refs to `fairdata.mit.edu` are **not** fetched from that host; they are
  redirected to whatever `NEXTSEEK_BASE_URL` is. Only `fairdomhub.org` goes
  off-host, and it needs `FDH_API` as a bearer token with **no fallback**.
- Refs come from a metadata key named literally `Protocol`, matching a
  `/sops/{id}` URL or a bare `P.*` name.
- DOCX extraction is stdlib-only. **PDF needs `PyPDF2`**; upstream silently
  yielded nothing without it, so ours raises `PdfSupportError` instead.
- Protocol text is truncated at ~3000 tokens, and the truncation is recorded in
  the completeness report rather than passing unnoticed.

## Modules

| module | responsibility |
|---|---|
| `scripts/report/adapters.py` | every input to one normalized shape; lineage walking |
| `scripts/report/enrich.py` | additive leaf-wins merge |
| `scripts/report/protocols.py` | SOP discovery, fetch, DOCX/PDF text, truncation |
| `scripts/report/mapping.py` | template spec loading, mapping validation |
| `scripts/report/execute.py` | deterministic application, row parity, completeness |
| `scripts/report/render.py` | format dispatcher and the three renderers |
| `scripts/report/validate_artifact.py` | rendered-artifact validation |

## Relationship to Phase 10

`/curate-deposit geo` **delegates the build** here and keeps only the genuinely
pipeline-specific parts: external upload (`upload_geo_ncftp.sh`) and accession
backfill (`apply_geo_accessions.py`).

Phase 10's GEO route was a dead end - nothing produced the required
`BULK_filled.json` and no GEO template xlsx shipped - so delegation was closer
to a free fix than a rewrite. The ordering is deliberate: GEO deposit happens
**before** NExtSEEK upload, because accessions must be backfilled into the
sheets first. That is why the curated-sheet adapter matters.

## Non-goals

- nf-core samplesheets.
- An LLM API client.
- Porting `reports/outputs.py` - a 400-line function with a hardcoded if/elif
  format dispatch. Ours is a real dispatcher.
- Uploading anything. This mode builds and validates; deposit uploads.

## Open question

**Does `synthesize` need manuscript access?** Study title, summary and
experimental design are prose that likely live in `manuscript/`. In a curation
project that is available; input-scoped runs elsewhere may have nothing, in
which case these become placeholders. That degradation is implemented and
tested; whether it is acceptable in practice is a curator's call.
