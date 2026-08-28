# `schema` mode — four evidence sources for attribute proposals

Supersedes the single-source checklist added 2026-08-27. Extends
`2026-07-21-schema-mode-design.md`; nothing in the reuse check, the field
dictionary, or the never-writes-to-NExtSEEK rule changes.

## Purpose

Answer "what attributes should this sample type carry?" from evidence rather
than from one house's precedent. The curator asks for research knowledge,
repository requirements, CEDAR templates and BioPortal ontologies; this spec
wires all four and says which one wins when they disagree.

## What this replaces, and why

The 2026-08-27 implementation pinned ONE CEDAR template —
`common assay template` — and diffed every sample type against it. D.VIA and
D.SEQ therefore produced an identical 28-row checklist, because the input was
identical. A generic assay questionnaire is not a sample-type template.

The justification was also wrong. Type-specific templates were dismissed on a
single query returning zero (`sequencing` → 0) while the library in fact holds
them:

| query | templates | | query | templates |
|---|---|---|---|---|
| `RNA-Seq` | 8 | | `flow` | 0 |
| `seq` | 9 | | `viability` | 0 |
| `ATAC` | 2 | | `cytometry` | 0 |
| `proteomics` | 7 | | `microscopy` | 0 |
| `metadata` | 287 | | | |

D.SEQ has ~9 relevant sequencing templates that were never consulted. D.VIA
genuinely has none — that is a real result, not a search failure, and the two
cases must be distinguished rather than collapsed.

## The four sources

Each answers a different question. None of them mints a field.

| # | source | answers | cost |
|---|---|---|---|
| 1 | repository templates | which fields a submission is REJECTED without | local, no key |
| 2 | CEDAR templates | which fields a community records for this assay | `CEDAR_API_KEY` |
| 3 | BioPortal | which VALUES a field may take | `BIOPORTAL_API_KEY` |
| 4 | research knowledge | why any of it applies here | none |

### 1. Repository requirements — the strongest, and already local

`context/report_templates/` ships GEO, SRA and PRIDE templates that `report`
mode uses and `schema` mode has never opened. They carry two things schema mode
needs:

- **Required fields**, marked by a `*` prefix. GEO: `*library strategy`,
  `*organism`, `*genome build/assembly`, `*extract protocol`,
  `*library construction protocol`. SRA adds 9 more (`*collection_date`,
  `*isolate`, `*sex`, `*geo_loc_name`). PRIDE carries 24.
- **The controlled vocabularies those repositories enforce**:
  `library_strategy` (41), `instrument_model_flat` (82), `library_selection`
  (33), `platform` (17), `filetype` (10), plus
  `instrument_model_by_platform` keyed by 17 platforms.

This outranks every other source for a type whose data is deposited publicly.
D.SEQ's `Sequencer` should be validated against GEO's 82 instrument models —
the list a submission is actually rejected against — not the 6 OBI classes
BioPortal returns. `SKILL.md` already records the consequence of getting this
wrong: *"GEO literal validation. `paired-end` not `paired`; `Illumina NextSeq
500` not `NextSeq 500`."*

Selection is by data type, not by sample type code: sequencing → GEO + SRA,
proteomics → PRIDE. A type mapping to no public repository gets nothing here,
and the review says so.

### 2. CEDAR templates — searched per type, pinned only as fallback

Search CEDAR using the producing assay from `Associated Assay Parents`. Rank
candidate templates by field count, description coverage and ontology binding —
quality varies enormously, and an unusable template is worse than none:

| template | fields | described | ontology-bound |
|---|---|---|---|
| `common assay template` | 28 | 27 | 22 |
| `RNA-Seq Metadata` | 21 | — | — |
| `ATACseq Metadata` | 14 | — | — |
| `Pistoia Alliance assay template` | 7 | 0 | 0 |

`common assay template` demotes to the fallback used ONLY when no domain
template matches. When it is the fallback, the review must say so, because a
generic checklist read as a type-specific one is what this spec exists to fix.

Elements nest and a flat reader is silently wrong — ATACseq declares one
top-level property holding 14 fields, RNA-Seq 21. `templates._walk` already
recurses; that behaviour is unchanged.

### 3. BioPortal — values, never fields

`terms.field_vocabulary(field, concept, ontologies=…)` returns the CHILDREN of
the concept a field names. Built and green as of this spec.

The concept is composed by the caller, never taken from the bare field name: a
field name resolves confidently to the wrong class (`Type` → a generic ontology
class "Type"; `Protocol` → kinds-of-protocol) and is indistinguishable by shape
from `Sequencer` → `sequencer`, which is correct.

For a CEDAR-proposed field, pass that field's **declared branch**. The templates
are authored against BAO, so `assay footprint` inside BAO resolves exactly and
yields `array, microplate, vial, cuvette`; unbranched, `assay title` returns
"Performed Patient Note Title".

Obsolete classes are filtered in `search_terms` on two signals, because neither
suffices alone: OBO marks deprecation in the LABEL (`obsolete biological
process`) while BioPortal reports `obsolete: false` for that very class.

### 4. Research knowledge

The rationale attached to each proposal, per the existing "rationale per change"
rule. This is the only source that explains why a field applies to THIS assay,
and it is the model's and curator's work, not a lookup.

## Precedence when sources disagree

For **values**, strongest last (the existing `_SOURCE_RANK` shape):

```
tags  <  cedar_branch  <  bioportal  <  repository  <  observed
```

`observed` stays top: hard rule 4, the workbook outranks the schema. `repository`
sits directly beneath it because a submission is literally rejected against those
lists. `tags` drops to the floor — it is a per-sample-type prose list, not a
per-field vocabulary, and binding it to a field is an unverifiable assertion.

For **fields**, no precedence: every source contributes candidates and the
curator judges. A field required by GEO and absent here is a strong signal; it
is still not an instruction.

## Outputs

`<TYPE>.review.md` gains one section and changes one:

```
## Current state
## Repository requirements          ← NEW: GEO/SRA/PRIDE required fields
## External clade evidence          ← unchanged
## Reference template checklist     ← now type-specific; says when it fell back
## Proposed additions
## Reuse decisions
## Controlled vocabularies proposed ← values now carry repository provenance
## Open questions and placeholders
## How to apply
```

Every new section keeps the existing contract: always rendered, and when empty
it states WHY. Silence cannot distinguish "checked, found nothing" from "never
checked" in a document written to be judged.

## Non-goals

- Emitting CEDAR templates. The tree-vs-graph argument is unchanged.
- Writing to NExtSEEK, or editing `sampletypes_db.json`.
- Vendoring CEDAR or BioPortal responses. Both stay live and degrade to an empty
  section naming its reason.
- Auto-applying any proposal, or flipping any `"confirmed": false`.
- Inventing a source for assay types no repository covers (see below).

## Testing

Injected-HTTP fakes for every network path, modelled on shapes verified against
the live services — a fake that smooths over the real structure hides the only
bugs this code can have. Both prior defects were caught by live smoke runs after
unit tests passed (`/parents` returns a bare array; CEDAR nests elements), so a
live smoke run against each service is required before any of this is called
done, and a full-suite baseline diff before it is committed.

## Open questions

**The one decision outstanding.** Types mapping to no public repository — D.VIA
among them, where `viability`, `cytometry` and `flow` all return zero CEDAR
templates too — get source 1 empty and source 2 on its generic fallback. They
will stay materially thinner than D.SEQ.

The recommendation is to accept that and state it plainly in the review rather
than invent a fourth fallback: a thin honest review is worth more than a padded
one, and the alternative is proposing fields with no evidence behind them, which
is what this mode exists to prevent. **Needs the operator's sign-off before
implementation.**
