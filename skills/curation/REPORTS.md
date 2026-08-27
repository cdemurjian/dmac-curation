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

| format | sections to map | row section | target type | artifact |
|---|---|---|---|---|
| GEO | `samples` (the spec also declares `study`, `protocols`, `paired_end_experiments`, `checksums`) | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries`, `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata_filled.xlsx` + `SRA_biosample_filled.xlsx` |
| PRIDE | `project_metadata`, `file_mapping`, `sample_metadata` | `sample_metadata` | `D.MSP` | `submission.px` |

**`project_metadata` is not optional for PRIDE.** `render_pride` writes one `MTD`
line per `project_metadata` key (`scripts/report/render.py:161-163`), and
`validate_pride_px` returns `SchemaInvalid` — HARD_REJECT — for a `.px` carrying
no `MTD` lines (`scripts/report/validate_artifact.py:308-309`). A PRIDE mapping
that omits the section renders a file that fails stage 2 every time.

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

**Caveat for GEO: synthesized study prose does not reach the xlsx.** `render_geo`
does not render — it writes `filled` to a temp JSON and shells out to
`scripts/deposit/geo_build_xlsx.py` (`scripts/report/render.py:55-62`, needs `uv`
on PATH, 300s timeout). That script reads only `data["samples"]` and
`data.get("paired_end_experiments", [])` and re-pastes the template's STUDY and
PROTOCOLS rows verbatim (`scripts/deposit/geo_build_xlsx.py:52-53`, `:23`). A
`study` block in a GEO mapping reaches `report/GEO_filled.json` and
`GEO.completeness.md` but **nothing transfers it into `GEO_filled.xlsx`** — the
curator still fills the STUDY block by hand before submitting, and should be told
so. SRA and PRIDE write every mapped section.

**The mapping is a cacheable artifact.** Same PI, same instrument, same assay
next quarter: reuse it and skip the mapping step entirely.

## Input adapters

Inputs are **not** a mode switch. Each adapter normalizes into one shape and
every downstream step is adapter-agnostic.

| input | behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | needs an injected `fetch` callable — see below |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}-upload.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

**The UID adapters ship no HTTP client.** `adapt_uids` / `adapt_retrieve_txt`
take a `fetch=` callable and unnest whatever it returns; the shape they expect is
the five-level `POST /nextseek_api/admin/samples/retrieve/` response
(`scripts/report/adapters.py:62-84`). **With `fetch=None` they return zero samples
silently** (`:70-71`) — not an error. Nothing in `scripts/` supplies that callable
today; only the tests do. So either wire the call yourself against
`scripts/nextseek_api.py`, or use one of the three local-read adapters. Prefer
the local ones — the curated sheet is the documented GEO input anyway, because GEO
deposit happens *before* NExtSEEK upload.

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
with a reason; every `source` column exists in the input; and a column that lives
only on ancestors carries `via_lineage`.

**CV checking is narrower than it sounds.** `const` and `map` outputs are checked
only for the nine fields `cv_for_field` recognises
(`scripts/report/mapping.py:44-60`, `:132-140`): eight SRA-keyed names plus GEO's
`*single or paired-end`, which uses a GEO-specific list held in code because the
vendored CV was mined from SRA and holds `paired`, not `paired-end`. GEO's
`*instrument model` is deliberately free text. **PRIDE has no controlled
vocabulary at all** — `pride.json` declares no `controlled_vocabulary` key — so
nothing in a PRIDE mapping is ever CV-checked.

**Stage 2, after rendering:** the vendored artifact validator. Its statuses map
onto the pipeline's vocabulary: `Valid` = CLEAN, `Incomplete` = SOFT_FLAG,
`SchemaInvalid` / `Missing` / `Unreadable` = HARD_REJECT.

**Known gap, verified: SRA `libraries` validation has no teeth.** `SRA.json`'s
`libraries` section stars nothing — `sample_name`, `library_ID`,
`library_strategy` and the rest are all bare — so `required_fields` returns `[]`
and any readable `SRA_metadata_filled.xlsx` reports `Valid` / CLEAN
(`scripts/report/validate_artifact.py:83-91`). `biosamples` does star its fields,
so SRA is not unguarded overall, but never read CLEAN on the metadata workbook as
evidence it is complete. Read `SRA.completeness.md` instead.

**Row parity is asserted only when the mapping declares it.** `RowParityError`
fires when `row_scope.expected_rows` is set and the produced row count differs
(`scripts/report/execute.py:153-159`); stage 1 checks the same number against the
input (`scripts/report/mapping.py:189-194`). Omit `expected_rows` and neither
check runs — which is how an adapter that silently returned zero samples ends up
as an empty artifact. **Always set it.** chat_nextseek's own assessment calls that
guard the single most valuable idea to carry over.

## Graceful degradation

Some GEO fields are derivable only from context an input may lack - organism,
tissue and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. First run the
Published-paper harvest (SKILL.md), all **five** sources in order: the manuscript
Methods, Supplemental Methods and Data Availability statement, then **the named
deposit itself**, then the master NExtSEEK sheet (`previous_metadata/*.xlsx`).
The deposit matters most here — for a report-mode run it is ground truth for the
data tier (file counts, filenames, checksums), which is precisely the tier GEO,
SRA and PRIDE ask about. Only when all five come up empty does the field degrade:

- write `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 -
  greppable; a blank is not), and
- record it in `<FORMAT>.completeness.md` with the field, the input searched,
  and why it failed.

Report mode keeps the placeholder even for published work (unlike pipeline
build, which blanks-and-flags): a blank required GEO/SRA field fails validation
silently, so the visible marker must stay. The `completeness.md` entry is the
flag.

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
tested; whether it is acceptable in practice is a curator's call. Note the GEO
caveat above before spending effort here: for GEO the answer currently lands only
in `GEO_filled.json` and `GEO.completeness.md`, never in `GEO_filled.xlsx`.
