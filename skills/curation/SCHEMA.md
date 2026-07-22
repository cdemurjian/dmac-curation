# `schema` mode - sample type authoring

Deep reference. Load when entering schema mode.
Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

## Purpose

Answer "what are we collecting?" for a NExtSEEK sample type. Given a type - say
`D.VIA` - produce resources a human reviews and then applies by hand.

The problem it attacks: of **1059 distinct field names across 101 sample types,
856 are used by exactly one type**, and none of the 1059 carries a description,
datatype or vocabulary anywhere. There is no way for an author to answer "does a
field for this already exist?", so new near-duplicates get minted by default.

## State scope

**cwd.** Reads the plugin's `context/` read-only; writes everything into the
current working directory under `schema/`. No lockfile, no scaffold, no project.

## Scope: ontology grounding, not CEDAR templates

Despite the shorthand ("use CEDAR to bolster D.VIA"),
**no CEDAR template is emitted**. CEDAR's contribution is ontology term
resolution via BioPortal, which is usable standalone: no CEDAR account, no
hosted service, no template machinery.

### Why templates are out of scope: tree vs graph

CEDAR's artifact model is a nested **tree** - template contains elements,
elements contain fields. It has no concept of one record referencing another.
NExtSEEK lineage is a **graph**: `MUS -> TIS -> DNA`, many-to-many parents,
expressed as cross-record UID references.

A CEDAR template could hold a UID in a text field, but referential integrity -
is this parent UID real, is the parent of a legal type, does the lineage
terminate - would live entirely outside CEDAR. That integrity work is most of
what the curation pipeline actually does. CEDAR is a strong model for
field-level typing and controlled vocabulary and a weak one for sample lineage,
which is the part that matters most here.

Three further mismatches, any one of which would need resolving first:

- CEDAR mints UUID-based IRIs; NExtSEEK UIDs are `<TYPE>-YYMMDD<LAB>-N`.
- CEDAR emits JSON-LD; the pipeline's deliverable is xlsx.
- Adopting CEDAR templates means committing to the schema being correct, which
  reverses SKILL.md hard rule 4, *"Schema lies; workbook tells truth."* That is
  a curation-policy decision, not a tooling one.

## Modules

| module | responsibility |
|---|---|
| `scripts/schema/field_index.py` | catalog loading, field usage index, the reuse check, Tags mining |
| `scripts/schema/dictionary.py` | observed-value mining, the lazy cwd-only field dictionary |
| `scripts/schema/ontology.py` | controlled-value proposals with sources, the `<TYPE>.ontology.json` artifact |
| `scripts/schema/terms.py` | BioPortal lookup; suggests, never binds; degrades with no key |
| `scripts/schema/review.py` | renders `<TYPE>.review.md`, the deliverable |

## The reuse check

Ranked candidates, never a yes/no. Passes in order of confidence: exact name,
normalized name (case, separators, plural), synonym match against dictionary
entries, semantic match over shared word stems. Ranked within a pass by usage
count, then clade proximity, then assay proximity.

The curator is shown the candidate name, how many types use it, which ones, and
example values - then judges.

**A field name shared across types is not a defect.** `Type` appears on many
sample types and legitimately means different things on each. The mode records
what it means *here*; it never proposes a rename or a split.

## The Ontology sheet - the shortest path to value

`_common.write_4sheet_xlsx` accepts `ontology={field: [values]}` and writes a
real Ontology sheet, declaring those fields `Controlled Ontology` on the
Instructions sheet:

```
| Field  | Database Field  | Field Type          | Ontology |
| Strain | MUS::Strain     | Controlled Ontology | Strain   |
```

**No caller had ever passed it.** Nothing populated it; `consolidate_to_flat.py`
never read it. So NExtSEEK had a controlled-vocabulary mechanism, the plugin
could write it, and nothing populated or consumed it. `<TYPE>.ontology.json` is
exactly that parameter's shape.

Since Phase 5's 4-sheet output is a **curator review artifact**, populating the
Ontology sheet puts permissible values in front of the reviewer at the moment
they are checking the data - with no new plumbing.

### Enforcement exists only in 4-sheet

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | "Ontology validation is not performed in rows mode" |
| flat xlsx | none - the format has no Ontology sheet |
| 4-sheet xlsx | "Validation is strict; violations reject the file" |

Adding an ontology column to a flat sheet does **not** work: `InputRowModel` is
`additionalProperties: true` and unknown columns are "ignored, with a warning",
so it would be accepted and silently discarded - worse than rejection.

**Verify before relying on this.** Read from `context/NExtSEEK_API.yaml`,
bundled 2026-05-27. Confirm with the NExtSEEK API owner that flat still lacks
ontology support.

## The field dictionary

**Lazy and cwd-only.** No pre-built dictionary ships, and none is generated for
all 1059 names. Each run creates entries only for the fields it touched.

Accepting the non-accumulation is deliberate: the plugin already has a
three-copies-of-context problem, and shipping another data file that drifts
would repeat it. Lazy ships no state - nothing to version, refresh or go stale.

Entry shape:

```json
"Instrument": {
  "description": "...",
  "datatype": "string",
  "used_by": ["D.VIA", "D.FLOW"],
  "observed_values": ["BioTek Synergy H1"],
  "ontology": {"iri": "...", "label": "...", "source": "NCIT", "confirmed": false},
  "synonyms": ["PlateReader", "Analyzer"],
  "provenance": "16 existing usages + 3 observed values"
}
```

## BioPortal - suggests, never binds

Every binding is emitted `"confirmed": false` with its source. Only a human
flips it.

This is not caution for its own sake. In the `MUS` prototype `Strain` was bound
to `NCBITaxon_10090` - **wrong**: NCBITaxon covers species, not laboratory
strains such as C57BL/6J or BALB/c. It was plausible enough to pass unreviewed.

Requires a free BioPortal API key in `BIOPORTAL_API_KEY`. Without one,
`search_terms()` returns `[]` without touching the network, and vocabulary still
comes from Tags, observed values and sibling types.

## Non-goals

- Writing to NExtSEEK, or editing `sampletypes_db.json` in place.
- Emitting CEDAR templates (see tree vs graph).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).

## Open question

**What "apply" concretely means.** Application is manual and the mode only
produces artifacts. Not settled: whether a human applying a proposed sample type
record means editing NExtSEEK's admin UI, running a SQL update, or opening a PR
against a schema repo. Confirm with the NExtSEEK admin before telling a curator
to edit anything. Until then, `<TYPE>.review.md` says exactly that.
