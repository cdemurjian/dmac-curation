# `schema` mode — sample type authoring

Date: 2026-07-21
Status: proposed
Parent: `2026-07-21-curation-toolkit-design.md`
Research: `/home/cdemu/code/dmac/research/CEDAR/`

## Purpose

Answer the "what are we collecting?" question for a NExtSEEK sample type.

Given a sample type — say `D.VIA` — produce **resources a human reviews and then
applies by hand**. The mode never writes to NExtSEEK and never edits
`sampletypes_db.json`. Its product is a proposal with rationale.

The problem it attacks: of 1059 distinct field names across 101 sample types,
**857 (81%) are used by exactly one type**, and none of the 1059 carries a
description, datatype, or vocabulary anywhere. There is no way for an author to
answer "does a field for this already exist?", so new near-duplicates get minted
by default.

## Scope: ontology grounding, not CEDAR templates

Despite the shorthand ("use CEDAR to bolster D.VIA"), **no CEDAR template is
emitted.** CEDAR's contribution is *ontology term resolution* via
`bioportal-term-mcp`, which is usable standalone — no CEDAR account, no hosted
service, no template machinery.

### Why templates are out of scope: tree vs graph

CEDAR's artifact model is a **nested tree** — template contains elements,
elements contain fields. It has no concept of one record referencing another.
NExtSEEK lineage is a **graph**: `MUS -> TIS -> DNA`, with many-to-many parents,
expressed as cross-record UID references.

A CEDAR template could hold a UID in a text or link field, but referential
integrity — is this parent UID real, is the parent of a legal type, does the
lineage terminate — would live entirely outside CEDAR. That integrity work is
most of what the curation pipeline actually does. So CEDAR is a strong model for
**field-level typing and controlled vocabulary** and a weak one for **sample
lineage**, which is the part that matters most here.

Three further mismatches, any one of which would need resolving first:

- CEDAR mints UUID-based IRIs; NExtSEEK UIDs are `<TYPE>-YYMMDD<LAB>-N`.
- CEDAR emits JSON-LD; the pipeline's deliverable is xlsx.
- **Adopting CEDAR templates means committing to the schema being correct** —
  which reverses SKILL.md hard rule 4, *"Schema lies; workbook tells truth."*
  That is a curation-policy decision, not a tooling one, and it is not this
  spec's to make.

Template emission may return once the field dictionary exists and the policy
question is settled. Not in v1.

## Trigger and state

`/curate-sampletype <TYPE>`, or conversationally *"help me bolster D.VIA"*.

**cwd-scoped** (toolkit spec O1): reads the plugin's `context/` **read-only**,
writes everything into the current working directory. No lockfile, no scaffold,
no project required. Works from anywhere.

## Inputs, all read-only

| input | use |
|---|---|
| `context/sampletypes_db.json` | current record; all 1059 names for the reuse check |
| `context/assays_db.json` | the producing assay's description and `Alternative Assay Names` |
| the type's own `Tags` | **already contains candidate vocabulary** — see below |
| `previous_metadata/*.xlsx` (when present) | real observed values beat guessed ones |

**Mining `Tags` is the cheapest win available.** `D.VIA`'s Tags field reads:

```
viability data, cell viability, cytotoxicity data, MTS assay, MTT assay,
WST-1, live/dead assay, CellTiter-Glo, proliferation assay, cell death data
```

Those are permissible values for D.VIA's `Type` field, already written down — as
prose, in a tags column, where nothing can enforce them. Half the controlled
vocabulary this mode needs to propose is already in the schema.

## The loop

1. **Read** the current definition. `D.VIA` today: 6 required / 4 standard /
   5 possible = 15 fields.
2. **Gather evidence** — producing assay (`Cell Viability Assay`), sibling types
   in the same clade (`Raw`), observed values from `previous_metadata`.
3. **Identify gaps.** For a viability assay: readout type, instrument, timepoint,
   dose, units, replicate, controls. None present today.
4. **Reuse check before minting any new name** (see below).
5. **Propose controlled values** — from Tags, from `bioportal-term-mcp`, or from
   observed values.
6. **Emit** the artifacts.

## Outputs — all to cwd

```
schema/
  <TYPE>.review.md        <- THE PRODUCT. Written for a human deciding what to apply.
  <TYPE>.proposed.json    sampletypes_db-shaped record, for diffing
  <TYPE>.ontology.json    {fieldname: [allowed values]} -> write_4sheet_xlsx(ontology=)
  field_dictionary.json   entries for fields touched this run only
```

### `<TYPE>.review.md` is the deliverable

The JSON exists to feed tooling. The markdown is what the work is *for*. Required
sections:

- **Current state** — what the type has today
- **Proposed additions**, each with **rationale and evidence**, e.g.
  *"`Timepoint` — the producing assay is time-series by nature; 3 sibling Raw
  types carry it; observed in `previous_metadata` as `24h`, `48h`"*
- **Reuse decisions** — *"used existing `Instrument` (16 types) rather than
  minting `PlateReaderModel`"* — stated so they can be overruled
- **Controlled vocabularies proposed**, with the source of every value
- **Open questions and placeholders** — what could not be resolved and why
- **How to apply** — the concrete manual steps

Rationale-per-change is the point. A bare field list cannot be judged; a field
list with evidence can.

## Field dictionary

**Lazy and cwd-only.** No pre-built dictionary ships with the plugin, and none is
generated for all 1059 names. Each run creates entries only for the fields it
touched.

Rationale for accepting the non-accumulation: the plugin already has a
three-copies-of-context problem (`sampletypes_db.json` in three places;
`curation_skill/context/neo4j_schema.json` is a stale *dev-instance* snapshot
with 23 Sample properties where the live one has 85). Shipping another data file
that drifts would repeat that. Lazy ships no state — nothing to version, refresh,
or go stale.

Entry shape:

```json
"Instrument": {
  "description": "...",
  "datatype": "string",
  "used_by": ["D.VIA", "D.FLOW", "..."],
  "observed_values": ["BioTek Synergy H1", "..."],
  "ontology": {"iri": "...", "label": "...", "source": "NCIT", "confirmed": false},
  "synonyms": ["PlateReader", "Analyzer"],
  "provenance": "16 existing usages + 3 observed values in previous_metadata"
}
```

## Reuse check

Ranked candidates, never a yes/no. Matching passes, in order:

1. exact name
2. normalized name (case, underscores, plurals)
3. synonym match against dictionary entries
4. semantic match over descriptions and observed values

Ranked by usage count, clade proximity, and assay proximity. The curator is shown
the candidate name, how many types use it, which ones, and example values — then
judges.

**A field name shared across types is not a defect.** `Type` appears on 57 sample
types and legitimately means different things on each. The mode records what it
means *here*; it never proposes a rename or a split.

## bioportal-term-mcp — suggests, never binds

Every ontology binding is emitted as `"confirmed": false` with its source. Only a
human flips it.

This is not caution for its own sake. In the `MUS` prototype
(`research/CEDAR/prototype/MUS-template.yaml`) `Strain` was bound to
`NCBITaxon_10090` — which is **wrong**: NCBITaxon covers species, not laboratory
strains such as C57BL/6J or BALB/c. It was plausible enough to pass unreviewed.
Ontology binding is per-field human judgment, and the tooling must not pretend
otherwise.

Requires a free BioPortal API key.

## The Ontology sheet — shortest path to value

`_common.py:194` already accepts `ontology: dict[str, list[str]] | None = None`
and `_common.py:249-252` writes a real Ontology sheet
(`Field / Database Field / Field Type / Ontology`). **No caller has ever passed
it.** Nothing populates it; `consolidate_to_flat.py` never reads it.

`<TYPE>.ontology.json` is exactly that parameter's shape. Since Phase 5's 4-sheet
output is confirmed to be a **curator review artifact**
(`2026-07-21-pipeline-rework-review.md`), populating the Ontology sheet puts
permissible values in front of the reviewer at the moment they are checking the
data — with no new plumbing.

### Schema mode feeds TWO sheets, not one

Per the NExtSEEK batch-upload spec, the per-field *declaration* lives in the
**Instructions** sheet and the *values* live in the **Ontology** sheet:

```
| Field  | Database Field  | Field Type          | Ontology |
| Strain | M.Mice::Strain  | Controlled Ontology | Strain   |
```

`Database Field` is `SampleType::AttributeName`. `_common.py:235` already writes
exactly these four headers, so both halves of the plumbing exist.

### Enforcement only exists in 4-sheet — verified

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | *"Ontology validation is not performed in rows mode"* |
| flat xlsx | **none** — no Ontology sheet in the format |
| 4-sheet xlsx | *"Validation is strict; violations reject the file"* |

`InputRowModel`'s complete field set is `UID, SampleType, json_metadata,
assay_ids, project_id, study_title, study_id, sop_id, assay_titles,
original_row_index`. There is no ontology field. Because the model is
`additionalProperties: true` and the spec states *"unknown extra columns are
ignored, with a warning"*, an ontology column added to a flat sheet would be
**accepted and silently discarded** — a worse failure than rejection.

**Decision: produce both formats.** Phase 5 emits 4-sheet with Instructions and
Ontology populated; Phase 6 continues to emit flat. The curator chooses per
upload — 4-sheet when vocabulary enforcement is wanted, flat for convenience.
Schema mode's output serves the 4-sheet path.

**Verify before relying on this.** The above is read from
`context/NExtSEEK_API.yaml`, bundled 2026-05-27. It is the better of the two
copies in the tree (41 paths vs chat_nextseek's 24) but is ~2 months old.
Confirm with the NExtSEEK API owner that flat still lacks ontology support.

## Non-goals

- Writing to NExtSEEK, or editing `sampletypes_db.json` in place.
- Emitting CEDAR templates (see tree-vs-graph, above).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).

## Testing

- Reuse check: given a candidate synonymous with an existing field, assert the
  existing name is ranked first and that a genuinely novel name is not
  force-matched.
- `<TYPE>.ontology.json` round-trips through `write_4sheet_xlsx(ontology=...)`
  and produces a readable Ontology sheet.
- Every ontology binding is emitted `confirmed: false`.
- The mode runs from a tmpdir with no lockfile and no scaffold, and writes
  nothing inside the plugin checkout (shares the P1 regression harness).
- Tags mining: `D.VIA` yields the MTS/MTT/WST-1/CellTiter-Glo value set.

## Open questions

1. **RESOLVED — vocabulary must reach NExtSEEK.** Both formats are produced;
   the 4-sheet path carries enforcement. See above. Still to confirm with the
   API owner: whether flat has gained ontology support since 2026-05-27.
2. **RESOLVED — application is manual.** The mode produces artifacts a human
   uses; it never applies anything. "How to apply" in `<TYPE>.review.md` is
   written for a person, and `<TYPE>.ontology.json` is directly consumable by
   `write_4sheet_xlsx(ontology=...)` when they choose to rebuild.
3. **Should `field_dictionary.json` ever be promoted?** Deferred by the lazy
   decision, but if the same enrichment is produced repeatedly across projects
   that is evidence to revisit.
