# `schema` mode - sample type authoring

Deep reference. Load when entering schema mode.
Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

## Purpose

Answer "what are we collecting?" for a NExtSEEK sample type. Given a type - say
`D.VIA` - produce resources a human reviews and then applies by hand.

The problem it attacks: of **1059 distinct field names across 101 sample types,
857 are used by exactly one type**, and none of the 1059 carries a description,
datatype or vocabulary anywhere. There is no way for an author to answer "does a
field for this already exist?", so new near-duplicates get minted by default.

## State scope

**cwd.** Reads the plugin's `context/` read-only; writes everything into the
current working directory under `schema/`. No lockfile, no scaffold, no project.

The single exception is `/curate-sampletype apply`, which writes to a **live
NExtSEEK server** and defaults to production. See
[Applying: the one live-write path](#applying-the-one-live-write-path).

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
| `scripts/schema/templates.py` | CEDAR reference-template checklist — the only source that names *fields*; the only consumer of `CEDAR_API_KEY`; degrades to an empty section without one |
| `scripts/schema/review.py` | renders `<TYPE>.review.md` (the deliverable) and `<TYPE>.proposed.json` (a catalog-shaped record, for diffing) |

**None of these is a CLI.** There is no `main()`, no `argparse` and no
`if __name__` anywhere in `scripts/schema/`, so SKILL.md hard rule 6
(`uv run --script …`) does not apply here. The contract is
`sys.path.insert(0, "<PLUGIN>/scripts")` then `from schema import field_index`.

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
`REFERENCE_TEMPLATES` (`scripts/schema/templates.py:52-55`) holds exactly one,
`common assay template`, while the Pistoia Alliance template carries 7 fields
with no descriptions and no bindings and is deliberately left out. **Field counts
are not quoted here on purpose:** the pinned template is a third-party
`bibo:draft` at v0.0.1, fetched live and never vendored, so any number goes stale
without warning. Run `template_fields(REFERENCE_TEMPLATES["common assay
template"])` and report what actually comes back.

**Elements nest, and a flat reader is silently wrong.** `_ui.order` at the top
level of ATACseq Metadata lists ONE property - a `TemplateElement` holding
fourteen fields. RNA-Seq Metadata reports 1 and carries 21. `_walk` recurses and
records the dotted element path; `_ui.order` is also what excludes the JSON-LD
scaffolding (`@context`, `schema:name`, `pav:createdOn`) that shares `properties`
with the real fields.

**Coverage is decided by the existing reuse check**, not by new matching logic.
Each uncovered field goes through `field_index.rank_candidates()`, so the
curator sees the same ranked-candidates output they already read elsewhere.

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

- Writing to NExtSEEK *from the proposal path*, or editing `sampletypes_db.json`
  in place. The one exception is the explicit `apply` verb — see
  [Applying: the one live-write path](#applying-the-one-live-write-path).
- Emitting CEDAR templates (see tree vs graph).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).

## Applying: the one live-write path

Everything above produces artifacts a human applies by hand. `/curate-sampletype
apply <TYPE> --add <FIELD>` is the one exception: it adds an attribute to a live
sample type through `scripts/sampletype_attr.py`, normally as the handoff from
`/curate-qc` after the server rejected a field that genuinely ought to exist.
`commands/curate-sampletype.md` is the authority; this is what a reader of
SCHEMA.md needs to know before they get there.

**Why a bespoke tool.** `PATCH /nextseek_api/sample_types/{id}/` is a 1:1
pass-through to SEEK, and SEEK's `allow_new_attribute?` refuses any sample type
that already has samples — nearly all of them — surfacing through NExtSEEK's
proxy as a generic `502 "Invalid upstream response"`. `sampletype_attr.py`
instead drives NExtSEEK's own native editor (`GET /seek/attribute/save/` → Django
ORM → `sample_attributes`) and calls `updateSampleType` to reconcile existing
samples' `json_metadata`.

**This is a GLOBAL, SHARED-SCHEMA WRITE.** Sample types are not project-scoped:
adding `Notes` to `A.TITR` changes that type for every project and every existing
`A.TITR` record across NExtSEEK.

**The guards, exactly.** The ORM path bypasses Rails, and therefore bypasses every
SEEK model validation. Four things stand in:

1. `sampletype_attr.py::_validate` (`scripts/sampletype_attr.py:180-206`)
   re-implements the three validations that matter —
   `validate_attribute_title_unique`, `validate_attribute_accessor_names_unique`,
   `validate_one_title_attribute_present`. These are the ONLY protection on this
   path; the `/seek/samples/attributes/` web page offers none of them.
2. **Dry run is the default.** `add`, `remove` and `selftest` print the exact
   record and send nothing unless `--apply` is passed.
3. **Production needs a second flag.** `_confirm_production`
   (`scripts/sampletype_attr.py:290-317`) refuses `--apply` against
   `nextseek.mit.edu` (`PRODUCTION_HOSTS`, `:63`) unless `--yes-production` is
   given too. `--yes-production` is stripped from `argv` before parsing, so it may
   appear anywhere on the command line.
4. **Rehearse on dev.** `--base-url https://nextseek-dev.mit.edu` (or
   `NEXTSEEK_BASE_URL`) targets dev, where the same types exist in the same shape.
   `DEFAULT_BASE_URL` is production (`:62`).

```bash
uv run --script <PLUGIN>/scripts/sampletype_attr.py list <TYPE>
uv run --script <PLUGIN>/scripts/sampletype_attr.py add <TYPE> --title <FIELD> --type Text
uv run --script <PLUGIN>/scripts/sampletype_attr.py --base-url https://nextseek-dev.mit.edu \
    add <TYPE> --title <FIELD> --type Text --apply
uv run --script <PLUGIN>/scripts/sampletype_attr.py \
    add <TYPE> --title <FIELD> --type Text --apply --yes-production
```

**Two things that will bite.** A change is invisible to `/curate-qc` and to batch
upload until the NExtSEEK app workers restart —
`prefetch_sample_type_attributes` caches sample_type_id → attribute titles in a
module-level dict with no TTL and no invalidation on write, so the web page shows
your attribute while validation still denies it. And the ORM path skips the Rails
callbacks that trigger Solr reindexing, so a new attribute may not be searchable
in SEEK until a reindex (unverified).

**When NOT to apply.** If the server rejected a field because *we* got it wrong —
invented it, mis-cased it, or copied a typo out of `sampletypes_db.json` — fix the
build script instead. Patching a shared schema to accommodate our own error
pollutes a shared vocabulary.

## Open question

**What "apply" means beyond adding an attribute.** Adding an attribute to an
existing type is settled, tooled and verified end to end (`Notes` on `A.TITR`,
dev then production, 2026-07-31). Still unsettled: how a human applies a *whole
proposed sample type record* — NExtSEEK's admin UI, a SQL update, or a PR against
a schema repo. Confirm with the NExtSEEK admin before telling a curator to create
a type; `<TYPE>.review.md` says exactly that. `sampletype_attr.py` is itself a
declared stopgap — superuser-only, a GET with JSON in query params — expected to
be superseded by a proper `nextseek_api` REST write endpoint wrapping
`DBtable_sampleattribute` + `DBtable_sample.updateSampleType`.
