---
description: Build a GEO / SRA / PRIDE submission artifact from metadata you have (report mode)
---

The user wants a repository submission artifact: *"I have file X.xlsx with
metadata, turn it into a GEO report."*

Parse `$ARGUMENTS` for a format (`GEO`, `SRA`, `PRIDE`) and an input. If either
is missing, ask - do not guess a format.

**Load `skills/curation/REPORTS.md` before starting.**

## Scope

**In:** GEO, SRA, PRIDE. Each has a renderer AND a validator; a format is not
supported without both.

**Out: nf-core samplesheets.** In chat_nextseek that path is a multi-turn
interactive wizard carrying Seqera/Tower launch concerns. Different problem,
out of scope for this mode.

## State scope

**Input-scoped.** Read a project lockfile when one is present, for lab and
project id. Run **without** one, from any cwd. All output goes to `./report/`.

## The chain

Only steps 4 and 6 need you. Everything else is a script.

```
1. adapter -> normalized shape                                    deterministic
2. (optional) NExtSEEK enrichment for resolvable UIDs             deterministic
3. protocol resolution: Protocol keys -> GET /sops/{id}/          deterministic
4. YOU emit a MAPPING SPEC                                        *** LLM ***
5. validate the mapping against the template + CV                 deterministic
6. YOU write only the `synthesize:` fields                        *** LLM ***
7. apply the mapping across all rows -> <FORMAT>_filled.json      deterministic
8. render                                                         deterministic
9. validate the rendered artifact                                 deterministic
```

Both LLM steps are **O(columns), not O(rows)**. That is the whole design.

### Step 1 - adapt the input

`scripts/report/adapters.py`. `detect_adapter()` picks by shape:

| input | adapter |
|---|---|
| UIDs on the command line | `adapt_uids` - POST `/nextseek_api/admin/samples/retrieve/` |
| `RETRIEVE.TXT` | `adapt_retrieve_txt` |
| `*_AllMetadata*.xlsx` | `adapt_nextseek_workbook` - local read, no API call |
| `Arm{X}-upload.xlsx` | `adapt_curated_sheet` - local read, works **before** upload (matches any `Arm*` sheet without an underscore) |
| any other xlsx / csv | `adapt_tabular` |

All emit the same shape. Everything downstream is adapter-agnostic.

### Steps 2 and 3 - enrichment, never required

`scripts/report/enrich.py` merges leaf-wins: values already in the input are
never overwritten. `scripts/report/protocols.py` resolves `Protocol` refs.
Neither gates output. If NExtSEEK is unreachable, say so and continue.

### Step 4 - emit the mapping spec

**Do not write cell values.** Write a declarative mapping, once, which the
executor applies to every row.

Read the template spec (`context/report_templates/GEO-updated.json` or
`SRA.json` or `pride.json`) and a profile of the input's columns, then emit
`report/<FORMAT>.mapping.json`:

```json
{ "report_type": "GEO",
  "source": {"adapter": "curated_sheet", "path": "assay_sheets/ArmA-upload.xlsx"},
  "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 117},
  "samples": {
    "*library name":         {"source": "UID"},
    "*organism":             {"const": "Homo sapiens"},
    "**tissue":              {"source": "Tissue", "via_lineage": true},
    "*instrument model":     {"const": "Illumina NextSeq 500"},
    "*single or paired-end": {"source": "LibraryLayout",
                              "map": {"paired": "paired-end"}},
    "processed data file":   {"unmapped": "no processed files in source"} },
  "study": {
    "*title":              {"synthesize": "study title from manuscript context"},
    "*summary (abstract)": {"synthesize": "abstract"} } }
```

| directive | meaning |
|---|---|
| `source` | copy from this source column |
| `via_lineage` | resolve by walking the `Parent` chain upward |
| `const` | same literal for every row |
| `map` | value normalization table |
| `synthesize` | free prose you write once. **Study-level only.** |
| `unmapped` | deliberately empty, with a stated reason |

**Use `via_lineage` whenever a column lives on ancestor samples.** Organism,
tissue and cell line usually live on an ancestor, not the `D.SEQ` row. Without
it every row is blank - the validator catches this as `needs_via_lineage`.

**`map` matters.** GEO dropdowns are word- and case-exact: `paired-end` not
`paired`, `Illumina NextSeq 500` not `NextSeq 500`.

### Step 5 - validate the mapping before applying it

`scripts/report/mapping.py` `validate_mapping()`. Cheapest place to fail. Fix
every error and re-validate. Do not proceed with errors outstanding.

### Step 6 - write only the synthesize fields

Study title, summary and experimental design. Report mode is inherently a
published/submitted path, so run the Published-paper harvest (SKILL.md) before
degrading anything — all **five** sources: the manuscript **Methods**,
**Supplemental Methods** and **Data Availability statement**, then **the named
deposit itself** (fetch it and enumerate its files — it is ground truth for the
data tier this artifact is about), then the **master NExtSEEK sheet**
(`previous_metadata/*.xlsx`). Only after that harvest comes up empty does a
field degrade — and here that means a placeholder in the artifact plus a
`<FORMAT>.completeness.md` entry (unlike pipeline build, a blank required GEO/SRA
field fails validation silently, so the visible marker stays). Never invent
prose.

### Steps 7 through 9

`scripts/report/execute.py` applies the mapping and asserts row parity.
`scripts/report/render.py` renders. `scripts/report/validate_artifact.py`
validates the result, reporting CLEAN / SOFT_FLAG / HARD_REJECT.

## Outputs, all to `./report/`

```
<FORMAT>.mapping.json        the mapping spec - reviewable, editable, REUSABLE
<FORMAT>.completeness.md     what could not be filled, and why
<FORMAT>_filled.json         the applied result
<FORMAT>_filled.xlsx         GEO
SRA_metadata_filled.xlsx     SRA
SRA_biosample_filled.xlsx    SRA
submission.px                PRIDE - tab-delimited, NOT a spreadsheet
```

**Reuse the mapping.** Same PI, same instrument, same assay next quarter: read
the existing `<FORMAT>.mapping.json`, confirm the source columns still exist,
and skip step 4 entirely.

## Hard rules

- **Never silently fabricate a value.** Unfillable fields become
  `*** PLACEHOLDER: ... ***` and appear in the completeness report.
- **Never refuse outright.** Degrade and report. The curator decides.
- **Never write cell values directly.** If you find yourself producing rows,
  you are doing step 4 wrong.
- Show the user the completeness report before declaring success.
- Report the validator's disposition honestly. A `SOFT_FLAG` is not a pass.

## Relationship to `/curate-deposit geo`

Phase 10 delegates its build step here and keeps only external upload and
accession backfill. GEO deposit happens **before** NExtSEEK upload, because
accessions must be backfilled into the sheets first - which is exactly why the
curated-sheet adapter matters.
