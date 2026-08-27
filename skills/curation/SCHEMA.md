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

## External clade evidence

`terms.clade_neighbors(hit)` walks a matched class's parents and children in an
external ontology and hands the labels **with their definitions** to the review.

The reuse check already mines siblings from the internal catalog, where the
prior is one house's precedent. This mines the same shape from a curated
ontology. The payoff is not the terms - it is the *axis*: OBI splits `cell
viability assay` into Annexin V staining, ATP bioluminescence, resorufin
detection and cell death, so detection chemistry is a real field D.VIA lacks.
Definitions are carried because the label alone is usually too terse to judge.

**It suggests an axis, never a field.** Nothing extracts a field name from an
ontology label; inferring the axis is the curator's work. `## External clade
evidence` in the review renders the neighbours and stops there.

The section is always rendered, and when empty it says why - no key, or no
class matched. Silence cannot distinguish "checked, found nothing" from "never
checked", and this document exists to be judged.

Two wire-shape facts, both already handled: BioPortal's `/children` paginates
its results under a `collection` key while `/parents` returns a **bare JSON
array**, and a class fetched through the REST API exposes only *annotation*
properties - definition, editor, curation status, `subClassOf`. The logical
axioms (`has_specified_input`, `has_specified_output`) live in OWL restrictions
and are **not** reachable this way. BioPortal cannot tell you what fields an
assay has; that is why this mines clade structure instead.

## The reference template checklist

`templates.template_fields(id)` reads a pinned CEDAR template and returns every
field it declares, with description, ontology branch and required flag.

This is the **only** source in the mode that names fields rather than values.
BioPortal cannot: its REST API exposes a class's annotation properties and
nothing else, so the OWL restrictions describing an assay's inputs and outputs
are unreachable. CEDAR templates are literally field lists, which is exactly the
artifact the "does a field for this already exist?" problem needs.

**A checklist, not a lookup.** The shared library cannot be selected by assay
name - `viability`, `flow cytometry`, `sequencing` and `metabolomics` all return
zero hits - so templates are pinned by `@id` and diffed against the type.
Quality varies enormously and only well-specified templates are worth pinning:
`common assay template` carries 28 fields, 27 described and 22 BAO-bound, while
the Pistoia Alliance template carries 7 with no descriptions and no bindings.

**Elements nest, and a flat reader is silently wrong.** `_ui.order` at the top
level of ATACseq Metadata lists ONE property - a `TemplateElement` holding
fourteen fields. RNA-Seq Metadata reports 1 and carries 21. `_walk` recurses and
records the dotted element path; `_ui.order` is also what excludes the JSON-LD
scaffolding (`@context`, `schema:name`, `pav:createdOn`) that shares `properties`
with the real fields.

**Resolution is confidence-tagged.** `resolve_class` prefers an exact or
normalised label match over BioPortal's lexical ranking and flags everything else
`weak`. It does not guess better than BioPortal; it refuses to present a guess as
a match. `Short Read Sequencing` has no OBI class of that name, so it resolves
weakly to `linked-read sequencing assay` and the review says so rather than
asserting a match.

**Coverage is decided by the existing reuse check**, not by new matching logic.
Each uncovered field goes through `field_index.rank_candidates()`, so the
curator sees the same ranked-candidates output they already read elsewhere.

`coverage()` partitions the reference fields into strong / weak / uncovered by
that verdict. An exact-NAME count is never reported: it placed D.SEQ, which
carries 84 fields, at "0 of 28", because CEDAR writes prose names and NExtSEEK
writes compact ones and the two conventions almost never collide.

Carry `Candidate.match_pass` into what the review renders. The semantic pass
matches on shared word stems and will happily return `Checksum_PrimaryType` for
`bioassay type` on the strength of "type" alone; presented bare as "closest
existing" that reads as a ruling rather than the weak hint it is. This is the
same trap as the `Strain` -> `NCBITaxon_10090` binding: plausible enough to pass
unreviewed.

The pinned templates are third-party, `isOpen: false`, and shared rather than
public - `common assay template` is `bibo:draft` at v0.0.1. They are read at
runtime and never vendored, so upstream change shows up as a changed checklist
instead of silently stale shipped state. An owner revoking access degrades to an
empty section that states its reason.

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
