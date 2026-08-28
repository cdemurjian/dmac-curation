---
description: Propose or bolster a NExtSEEK sample type (schema mode)
---

The user wants to define a new NExtSEEK sample type, or bolster an existing one:
"help me bolster D.VIA", "what should we be collecting for this assay?"

Parse `$ARGUMENTS` for a sample type short code, e.g. `D.VIA`. If absent, ask
which type - do not guess.

**Load `skills/curation/SCHEMA.md` before starting.**

## State scope

**cwd-scoped.** Read the plugin's `context/` read-only. Write every artifact
into the current working directory, under `schema/`. There is **no lockfile**
requirement, no scaffold, and no project. This works from anywhere.

## The default mode never applies anything

By default it **never writes to NExtSEEK** and never edits `sampletypes_db.json`.
Its product is a proposal with rationale, which a human reviews and applies by hand.

The one exception is the explicit `apply` verb below, which exists so a validated,
agreed schema gap can be closed without hand-editing through the web UI. Everything
else in this mode stays read-only.

## `apply` — add an attribute to a live sample type

Invoked as `/curate-sampletype apply <TYPE> --add <FIELD>`, normally as the handoff
from `/curate-qc` after the server rejected a field that genuinely ought to exist.

**This is a GLOBAL, SHARED-SCHEMA WRITE.** Sample types are not project-scoped:
adding `Notes` to `A.TITR` changes that type for every project and every existing
`A.TITR` record across NExtSEEK. Treat it accordingly.

### Steps

The REST route does not work for this. `PATCH /nextseek_api/sample_types/{id}/` is a
1:1 pass-through to SEEK, and SEEK enforces

```ruby
# lib/seek/samples/sample_type_editing_constraints.rb
def allow_new_attribute?
  !samples?
end
```

so it returns 422 for any sample type that already has samples — which is nearly all
of them. NExtSEEK's proxy does not check the upstream status, so it surfaces as a
generic `502 "Invalid upstream response"`. No payload shape works around it.

Use `scripts/sampletype_attr.py`, which drives NExtSEEK's OWN native editor
(`/seek/attribute/save/` → Django ORM → `sample_attributes`), never invoking Rails
and therefore never hitting the constraint. It also calls `updateSampleType` to
reconcile existing samples' `json_metadata`.

1. Read the current state. Note the sample count — that is what blocks the REST route:

   ```bash
   uv run --script <PLUGIN>/scripts/sampletype_attr.py list <TYPE>
   ```

2. Dry run. Prints the exact record and sends nothing:

   ```bash
   uv run --script <PLUGIN>/scripts/sampletype_attr.py \
     add <TYPE> --title <FIELD> --type Text
   ```

3. **Rehearse on dev before touching production.** `A.TITR` and friends exist there in
   the same shape:

   ```bash
   uv run --script <PLUGIN>/scripts/sampletype_attr.py \
     --base-url https://nextseek-dev.mit.edu add <TYPE> --title <FIELD> --type Text --apply
   ```

4. **Get explicit confirmation for this specific type and field**, stating the blast
   radius. Then apply. Production requires `--yes-production` in addition to `--apply`;
   the tool refuses otherwise.

   ```bash
   uv run --script <PLUGIN>/scripts/sampletype_attr.py \
     add <TYPE> --title <FIELD> --type Text --apply --yes-production
   ```

5. Verify with `list`, then re-run `/curate-qc` to confirm the failing rows now validate.

6. Do one type first and verify end to end before batching.

### This is a stopgap, not the intended interface

`sampletype_attr.py` drives the admin UI's own endpoint because there is currently no REST
write path that works. That makes it a deliberate workaround with real limitations:

- it is **superuser-only**
- it is a **GET with JSON in query params**, shaped for a datagrid rather than for tooling
- it **bypasses every Rails validation** (see below), so its three client-side guards are the
  only thing standing in
- a change is **invisible until the NExtSEEK workers restart** (see `/curate-qc`)

The intended replacement is a proper `nextseek_api` REST write endpoint wrapping
`DBtable_sampleattribute` plus `DBtable_sample.updateSampleType`. When that lands, this tool
should become a thin client of it and these caveats mostly disappear.

**If you are the one building that endpoint:** port the three guards from
`sampletype_attr.py::_validate`, call `updateSampleType` so existing samples' `json_metadata`
is reconciled, invalidate `_SAMPLE_TYPE_ATTRIBUTES_CACHE` on write so no restart is needed, and
do NOT proxy to SEEK or the `allow_new_attribute?` editing constraint comes straight back.

Until then, prefer this tool over hand-editing through the web page: the page offers none of
the validation.

### Why this path is dangerous, and what protects you

Because the write goes through the Django ORM, **every SEEK model validation is
bypassed**. `sampletype_attr.py::_validate` re-implements the three that matter —
`validate_attribute_title_unique`, `validate_attribute_accessor_names_unique`, and
`validate_one_title_attribute_present`. Those guards are the ONLY protection on this
path. Anyone using the `/seek/samples/attributes/` web page directly gets none.

Three wire-format gotchas, all easy to get wrong and all already handled by the tool:

- The numeric attribute-type id travels in the key named `sample_attribute_type_title`,
  because the grid combobox uses `sample_attribute_type_id` as its `valueField`.
- `id` must be OMITTED for a new attribute. Any `id > 0` means update.
- `sample_controlled_vocab_id` is silently dropped and never written.

A partial `records` list is safe: the save path only touches the records passed and has
no delete-missing pass.

**Open question, unverified:** the ORM path skips the Rails callbacks that trigger Solr
reindexing, so a newly added attribute may not be searchable in SEEK until a reindex.

### Verified end to end (2026-07-31)

`Notes` was added to `A.TITR` on dev then production, and the change was confirmed to
have the intended effect:

| | dev (id 35) | production (id 99) |
|---|---|---|
| before | 10 attributes | 10 attributes |
| after | 11, `Notes` id 2651 | 11, `Notes` id 3603 |
| originals | intact, ids 1324-1333 | intact, ids 2238-2980 |
| existing samples | reconciled, `total: 7` | reconciled, `total: 7` |

Server validation then stopped rejecting `Notes` on `A.TITR` while every other
rejection stayed put — a clean, targeted change.

**`--yes-production` may appear anywhere on the command line.** It is stripped from
argv before parsing precisely so it does not have to precede the subcommand.

**Expect the row count NOT to move after a single patch.** A row fails if any one of
its fields is undefined, so `A.TITR` rows kept failing on `Lab` and `Name`. Judge
progress by the distinct (type, field) rejection list.

### When NOT to apply

If the server rejected a field because *we* got it wrong — invented it, mis-cased it
(`Bead_coating_vendor` vs `Bead_coating_Vendor`), or copied a typo out of
`sampletypes_db.json` (`QuanitifcationMethod`) — **fix the build script instead**.
Patching the schema to accommodate our own error pollutes a shared vocabulary.

## The loop

1. **Read the current definition.** Use `scripts/schema/field_index.py`:
   `load_catalog()`, then `type_record(catalog, TYPE)`. Report the
   required / standard / possible counts.

2. **Gather evidence.**
   - the producing assay from `Associated Assay Parents`, described in
     `context/assays_db.json`
   - sibling types in the same clade via `siblings_in_clade(catalog, TYPE)` -
     what do they collect that this type does not?
   - real observed values from any `previous_metadata/*.xlsx` in cwd, via
     `scripts/schema/dictionary.py` `observe_values()`. Real values beat
     guessed ones (SKILL.md hard rule 4).
   - **external clade evidence** via `scripts/schema/terms.py`: resolve the
     producing assay with `resolve_class(assay, ontologies=("OBI",))` - NOT
     `search_terms(...)[0]`, which returns BioPortal's lexical ranking and put
     `Short Read Sequencing` on `linked-read sequencing assay`, a 10x-specific
     technique, while `sequencing assay` sat at rank five. `resolve_class`
     returns a `ClassMatch` carrying `confidence`; **a `weak` confidence must be
     rendered as weak and nothing may rest on it.** Then `clade_neighbors(m.hit)`
     for that class's parents and children. Where an
     ontology splits one class into several, the axis it splits on is often a
     field this type lacks - OBI divides `cell viability assay` by detection
     chemistry (Annexin V, ATP bioluminescence, resorufin), which is a field
     D.VIA does not have. Degrades to nothing without `BIOPORTAL_API_KEY`.
   - **a CEDAR template, SELECTED BY YOU, not by a query.** This step is
     judgement, and the tooling deliberately provides no `select_template`.
     `templates.search_templates(query)` is the primitive; you drive it.

     **How CEDAR's search actually behaves** - learn this before concluding
     anything, because getting it wrong produced a wrong answer once already:

     - It matches **token prefixes against template NAMES**, not descriptions
       and not content. `NGS`, `Illumina` and `library` all return 0.
     - So the assay's own name is often the WRONG query. `sequencing` returns
       **0** while `*seq*` returns **18** - RNA-Seq Metadata, ATAC-Seq Metadata
       2.0, DBiT-seq, Seq-Scope, RNAseq (Bulk), RNAseq (sc-sn), Pixel-seqV2,
       MiAIRR. The templates are named `seq`, never `sequencing`.
     - Wildcards work and you should use them: `seq*` gives 10, `*seq*` gives 18.
     - The token **`assay` is a stopword that poisons results.** Searching
       `Cell Viability Assay` returns `common assay template` and
       `Pistoia Alliance assay template` - generic templates matching on that
       one word, with nothing viability-specific among them. A score-based
       picker calls the highest one type-specific. It is not.

     **The loop.** Search on the assay name. If you get 0 hits, or only generic
     `*assay template*` names, DO NOT conclude the library has nothing. Retry:
     strip the stopwords, wildcard the distinctive stem (`*seq*`, `*proteom*`),
     try the abbreviation and the expansion, try terms from the type's Tags.
     Then read the NAMES that come back and judge whether any is actually about
     this assay. Report which queries you ran.

     **Only after that may you fall back.** `templates.fallback_template()`
     returns the pinned generic, and you must pass `is_fallback: True` so the
     review says the checklist is generic. Absence is a real answer when you
     have earned it: `*viab*`, `*cytotox*`, `*cytom*`, `*flow*` and `*facs*` all
     return 0, so D.VIA genuinely has no template and its review should say so.
     `sequencing` returning 0 is NOT that - it is a bad query.

     Then `template_fields(candidate.template_id)` for the field list, and
     `coverage(fields, resolver)` to partition it. Degrades to nothing without
     `CEDAR_API_KEY`.

3. **Identify gaps.** What does this assay actually produce that the record does
   not capture? For a viability assay: readout type, instrument, timepoint, dose,
   units, replicate, controls.

   The external clade from step 2 is evidence here, not an answer. Read the
   sibling definitions and name the axis they differ on yourself; nothing
   extracts a field name from an ontology label, and the review says so.

   The template checklist is the sharper instrument: it names concrete fields
   with descriptions and vocabularies. Treat each as a question for the
   curator - does this house collect it, under another name, or not at all? -
   never as an instruction to add it.

4. **Run the reuse check before minting any new name.** For each candidate,
   `rank_candidates(name, index, clade=..., assay=..., catalog=...)`. Show the
   user the candidate name, how many types use it, which ones, and example
   values. **The curator judges** - the tool never decides.

   A field name shared across sample types is **not** a defect. `Type` appears
   on many types and legitimately means different things on each. Never propose
   a rename or a split.

5. **Propose controlled values.** `scripts/schema/ontology.py` `propose_values()`
   merges Tags, observed values, siblings and BioPortal, ranking observed
   highest (hard rule 4). Without a key the first three still work; say so
   rather than failing.

   **`propose_values` does NOT call BioPortal.** It accepts `bioportal=[...]`
   and you must produce that list, or every value comes from Tags no matter
   what key is set. Use `terms.field_vocabulary(field, concept, ontologies=...)`,
   which walks the CHILDREN of the concept a field names. Two ways in:

   - **a current attribute** - compose the concept from the field AND the
     producing assay, then pass it. A bare field name is not its concept:
     `Type` resolves EXACT to a generic class called "Type" and `Protocol` to
     kinds-of-protocol. Nothing can tell that apart from `Sequencer` ->
     `sequencer`, which is correct, so the values come back for you to look at.
   - **a CEDAR-proposed attribute** - pass that field's own declared branch as
     `ontologies`. The template was authored against BAO, so `assay footprint`
     inside BAO resolves exactly and yields array, microplate, vial, cuvette.
     Unbranched, `assay title` returns "Performed Patient Note Title". The
     branch is doing the work; do not drop it.

   Read `_sources` in the artifact before trusting any of it. Some branches
   yield nothing usable - `applies to disease` in DOID lexically matches
   `susceptibility to legionnaire disease` and has no children.

6. **Emit the artifacts** into `./schema/`:

   | file | what it is |
   |---|---|
   | `<TYPE>.review.md` | **the product** - written for a human deciding what to apply |
   | `<TYPE>.proposed.json` | a `sampletypes_db.json`-shaped record, for diffing |
   | `<TYPE>.ontology.json` | `{field: [allowed values]}` - feeds `write_4sheet_xlsx(ontology=)` |
   | `field_dictionary.json` | entries for fields this run touched, only |

## Hard rules for this mode

- **Every ontology binding is emitted `"confirmed": false`.** Only a human flips
  it. The MUS prototype bound `Strain` to `NCBITaxon_10090`, which is a species,
  not a laboratory strain like C57BL/6J. It was plausible enough to pass
  unreviewed.
- **Rationale per change.** A bare field list cannot be judged. Every proposed
  addition states why, with evidence: the producing assay, sibling usage, or
  observed values.
- **State reuse decisions explicitly** so the curator can overrule them.
- **Never rename or split** an existing field name.
- **No CEDAR template is emitted.** See `SCHEMA.md` for why.
- Anything unresolved goes in "Open questions and placeholders", never a guess.

## Report

Print the counts, the reuse decisions, and the paths written. End by pointing
the user at `schema/<TYPE>.review.md` as the thing to read.
