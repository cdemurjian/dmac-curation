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

**Run it from a PROJECT directory when one exists.** "Works from anywhere" is
not "works equally well anywhere": `dictionary.observe_values()` reads
`previous_metadata/*.xlsx` **from cwd**, so running outside a project silently
yields zero observed values - and observed values are the highest-ranked source
there is (SKILL.md hard rule 4, the workbook outranks the schema). Nothing warns
you. Every proposal then rests on schema and ontology evidence alone. If no
workbook is in reach, SAY SO in the review's open questions, as a limitation of
the run rather than a property of the type.

**Never run it from the plugin repo itself** - `schema/` there breaks
`tests/test_schema_dictionary.py::test_no_prebuilt_dictionary_ships_with_the_plugin`.

**Invoke python as `uv run --with openpyxl`.** `dictionary.py` and `ontology.py`
import openpyxl at module scope, so a bare `uv run` dies with
`ModuleNotFoundError` before you touch a workbook. Hard rule 6's
`uv run --script` does not apply to these modules; import them via
`sys.path.insert(0, "<plugin>/scripts")` and `from schema import ...`.

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

### The route

`POST /nextseek_api/attributes/batch-create/`, live on production since 2026-08-31.
Wrapped by `scripts/nextseek_api.py sampletype-add-attribute`.

**Not** `PATCH /nextseek_api/sample_types/{id}/`. That one is a 1:1 pass-through to
SEEK, which enforces `allow_new_attribute? = !samples?` and returns 422 for any type
that already has samples — surfacing as a generic `502`. That is still true and is
why this command does not use it. The attributes API is a different, purpose-built
route and is not subject to the constraint. See `/curate-qc` for the root cause.

Mutations require the SEEK login's Django user to have **`is_superuser=1`**. This is
not the same population as a SEEK admin and the two are not nested: a SEEK admin who
is not a Django superuser gets `403 permission_denied` ("Superuser access required").
Reads need only a SEEK login.

### Steps

1. Read the current state:

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py sampletype-get <TYPE>
   ```

2. Dry run. **The server plans it and writes nothing** — this is its answer, not a
   client-side guess:

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py \
     sampletype-add-attribute <TYPE> --name <FIELD> --type Text
   ```

3. **Rehearse on dev before touching production.**

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py \
     sampletype-add-attribute <TYPE> --name <FIELD> --type Text \
     --base-url https://nextseek-dev.mit.edu --apply
   ```

4. **Get explicit confirmation for this specific type and field**, stating the blast
   radius. Then apply:

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py \
     sampletype-add-attribute <TYPE> --name <FIELD> --type Text \
     --apply --yes-production
   ```

   **Production requires `--yes-production` in addition to `--apply`.** The tool
   refuses otherwise; prose is not the gate.

5. Re-run `/curate-qc` to confirm the failing rows now validate. **No worker restart
   is needed** — see below.

6. Do one type first and verify end to end before batching.

### What the server enforces, so you do not have to

The endpoint validates title uniqueness and the single-title-attribute rule itself,
and returns structured JSON rather than an HTML page:

| status | meaning |
|---|---|
| 401 `authentication_failed` | bad or missing credentials |
| 403 `permission_denied` | authenticated, but not a Django superuser |
| 422 `request_validation_error` | names the offending field |
| 409 | per-target error document, e.g. `sample_type_not_found` carrying `submitted_identifier` |

`sample_type` and `sample_attribute_type` are **Identifiers**: a database id, a
numeric string, or the exact title.

### Read `automatic_changes` in the dry run before you apply

A request that adds ONE attribute can emit dozens of side effects. Measured on
production: creating one attribute on `BLD` produced **68 `position_changed`
automatic changes**, renumbering every definition from position 8 down.

**Deleting the attribute afterwards does not undo them.** The count is in the
dry-run response and the command prints it as `AUTOMATIC CHANGES`. Read it. A
number far above the number of attributes you asked for is the signal to stop
and check what else the type holds.

### Undoing a rehearsal

Step 3 writes to dev for real, so the rehearsal leaves an attribute behind:

```bash
uv run --script <PLUGIN>/scripts/nextseek_api.py \
    sampletype-remove-attribute <TYPE> --name <FIELD> \
    --base-url https://nextseek-dev.mit.edu --apply
```

**Destructive and global** — it removes the field from every record of the type,
with no undo through this API, and it renumbers positions again. Same
`--yes-production` requirement against production.

### No restart is required, and that is new

Adding an attribute used to be invisible to validation until the NExtSEEK workers
restarted, because `_SAMPLE_TYPE_ATTRIBUTES_CACHE` had no TTL and no invalidation and
gunicorn runs four of them. That was fixed on 2026-08-31 with a database-side
generation stamp — `SELECT COUNT(*), MAX(updated_at) FROM sample_attributes`, read
once per batch — so every worker sees the write through the one thing they share.

It is **writer-agnostic**: it equally catches writes made through this API, through
the `/seek/samples/attributes/` web page, or by hand in SQL.

### When NOT to apply

If the server rejected a field because *we* got it wrong — invented it, mis-cased it
(`Bead_coating_vendor` vs `Bead_coating_Vendor`), or copied a typo out of
`sampletypes_db.json` (`QuanitifcationMethod`) — **fix the build script instead**.
Patching the schema to accommodate our own error pollutes a shared vocabulary.

**Expect the row count NOT to move after a single patch.** A row fails if any one of
its fields is undefined, so `A.TITR` rows kept failing on `Lab` and `Name`. Judge
progress by the distinct (type, field) rejection list.

## The loop

1. **Read the current definition.** Use `scripts/schema/field_index.py`:
   `load_catalog()`, then `type_record(catalog, TYPE)`. Report the
   required / standard / possible counts.

2. **Gather evidence.**
   - the producing assay from `Associated Assay Parents`, described in
     `context/assays_db.json`
   - sibling types in the same clade via `siblings_in_clade(catalog, TYPE)` -
     what do they collect that this type does not?
   - **the PARENT types via `parents_of(catalog, TYPE)`** - a different question
     from clade siblings, and usually a more useful one. D.SEQ's 38 Raw-clade
     siblings are unrelated assays, while its `DNA` parent carries `Barcode`,
     `Concentration`, `NumPrepCycles` and `LibraryType` - fields you would
     otherwise propose as new. **A field held upstream through lineage is NOT a
     gap**, and `Parent_SampleTypes` is prose you must not split by hand: four
     separators are in use, CEL is missing a comma, and `.` appears inside the
     codes themselves. `parents_of` matches known codes instead.
   - real observed values from any `previous_metadata/*.xlsx` in cwd, via
     `scripts/schema/dictionary.py` `observe_values()`. Real values beat
     guessed ones (SKILL.md hard rule 4).
   - **repository requirements** via `scripts/schema/repositories.py` - the
     strongest source, and entirely local. `repositories_for(record)` says which
     of GEO / SRA / PRIDE cover this data type;
     `required_fields(load_template(r), r)` gives the fields a submission is
     REJECTED without (`*` required, `**` conditional - do not flatten them);
     `controlled_vocabularies(load_template(r))` gives the value lists those
     repositories enforce. GEO alone ships 41 library strategies and 82
     instrument models. No key, no network.

     A type no repository covers comes back EMPTY - D.VIA, D.FLOW and D.PRM all
     do - and that is a fact about the type, not a failed lookup. Pass a
     `reason` so the review says which.

     **`held` is YOUR judgement. No matcher computes it.** Repositories write
     prose names (`instrument model`) and NExtSEEK writes compact ones
     (`Sequencer`); the two vocabularies share almost no word stems, so nothing
     lexical bridges them. `rank_candidates("instrument model")` never returns
     `Sequencer` at any pass, and everything it does return is `semantic` -
     an earlier version of this file prescribed a pass-based rule and it failed
     on that very example. `tests/test_schema_repositories.py` pins this.

     So: run `rank_candidates()` for evidence, then decide yourself, and say in
     the review that you decided. Two directions to check, because the error is
     symmetric - an over-strict rule HIDES a duplicate you are about to mint,
     and an over-loose one HIDES a required field you do not have.

     Scope the index to THIS TYPE when judging `held`. Build it from the whole
     catalog and GEO's `tissue`, `cell line`, `cell type`, `age` and `sex` all
     report held for D.SEQ, which declares none of them - they live on CEL, PAT
     and MUS. Step 4's reuse check is the opposite: it genuinely wants the
     full-catalog index. Same function, two scopes, and only you know which.

   - **external clade evidence** via `scripts/schema/terms.py`. A `weak`
     resolution is a starting point, not a dead end: retry it the way you retry
     a CEDAR search. Drop qualifiers (`Short Read Sequencing` -> `sequencing
     assay`), try the parent concept, try a synonym. `Short Read Sequencing`
     resolves weakly to `linked-read sequencing assay` and yields ONE neighbour,
     while `DNA sequencing assay` resolves EXACT and yields 21. Render both if
     you probe twice, each labelled with the query that produced it, and never
     let a weak result stand unlabelled.

     The primitives: resolve the
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
     - **Substring traps.** `*plate*` returns ~25 hits by matching
       "Tem**plate**". Check that a hit's NAME is about your assay, not about
       CEDAR itself.
     - The tokens **`assay` AND `cell` are stopwords that poison results.**
       Searching `Cell Viability Assay` returns 20 hits of which 17 match on
       `Cell` alone (`Cell DIVE`, `iPS Cell`, `Cell Line Metadata`), plus
       `common assay template` and
       `Pistoia Alliance assay template` - generic templates matching on that
       one word, with nothing viability-specific among them. A score-based
       picker calls the highest one type-specific. It is not.

     **The loop.** Search on the assay name. If you get 0 hits, or only generic
     `*assay template*` names, DO NOT conclude the library has nothing. Retry:
     strip the stopwords, wildcard the distinctive stem (`*seq*`, `*proteom*`),
     try the abbreviation and the expansion, try terms from the type's Tags.
     Then read the NAMES that come back and judge whether any is actually about
     this assay. Report which queries you ran.

     **Run a POSITIVE CONTROL before concluding absence.** Every network
     function here - `search_templates`, `template_fields`, `search_terms`,
     `clade_neighbors`, `field_vocabulary` - ends in `except Exception: return
     []`. That is deliberate, so one dead endpoint never breaks a run, but it
     means an expired key, a revoked template or a network blip is
     INDISTINGUISHABLE from a genuine zero. "`*viab*` returns 0, so nothing
     exists" is also exactly what you would conclude with a dead key.

     So before you record an absence, run a query you KNOW returns hits and
     check it does: `*seq*` should give 18 for CEDAR, and
     `search_terms("cell viability assay", ontologies=("OBI",))` should resolve
     exact for BioPortal. Report the control alongside the zeros. An absence
     without a control is not evidence.

     **Only after that may you fall back.** `templates.fallback_template()`
     returns the pinned generic, and you must pass `is_fallback: True` so the
     review says the checklist is generic. Absence is a real answer when you
     have earned it: `*viab*`, `*cytotox*`, `*cytom*`, `*flow*` and `*facs*` all
     return 0, so D.VIA genuinely has no template and its review should say so.
     `sequencing` returning 0 is NOT that - it is a bad query.

     Then `template_fields(candidate.template_id)` for the field list, and
     `coverage(fields, resolver)` to partition it. **The resolver decides what
     "covered" means, so say which index you gave it** - the full catalog
     answers "does this house have such a field anywhere", the type-scoped index
     answers "does THIS type have it". The review reads as the second; passing
     the first quietly inflates the strong count with fields another type owns. Degrades to nothing without
     `CEDAR_API_KEY`.

3. **Identify gaps.** What does this assay produce that the record does not
   capture? Weigh the four sources by what each can actually establish:

   - a **repository-required** field this type lacks is the strongest signal
     available - a submission fails without it
   - a **type-specific CEDAR** field is a community convention; a **fallback**
     CEDAR field is only a question about assays in general, and the review must
     say which one you are looking at
   - **OBI clade** evidence suggests an AXIS to think about, never a field. Read
     the sibling definitions and name the axis yourself
   - your own **research knowledge** is what explains why any of it applies to
     THIS assay, and it belongs in the rationale of every proposal

   None of them is an instruction. A field required by GEO and absent here is
   still a question for the curator, not a change to make.

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

   **An EXACT resolution is not a usable vocabulary.** Confidence describes the
   class match, never the fitness of its children, and the children are scoped
   to the BRANCH rather than to your assay. `physical detection method` resolves
   exact in BAO and returns 12 modalities covering all bioassays - `mass
   spectrometry`, `radiometry`, `isometric tension recording` cannot produce a
   viability readout. `detection instrument` resolves exact and returns 39
   specific commercial products, including BAO's own typo `Infinte M200`; bind
   that under strict 4-sheet validation and every instrument BAO omits is
   rejected. Filter to what this assay can actually produce, and record the
   filtering as your judgement so it can be overruled.

   **A repository vocabulary usually outranks an ontology one - but check WHOSE
   list it is.** The literals really do diverge: BioPortal offers `PacBio Revio`
   where the vendored list has `Revio`, and only one passes a strict validator.
   That is the `Illumina NextSeq 500` vs `NextSeq 500` trap in SKILL.md.

   **Do not assume the list belongs to the repository whose file you opened.**
   `GEO-updated.json`'s own `controlled_vocabulary.authority` says the block was
   "mined directly from the uploaded SRA_metadata.xlsx workbook", and
   `REPORTS.md` records that GEO's `*instrument model` is deliberately FREE
   TEXT, never CV-checked. So the 82 instrument models are SRA's, and binding
   them as GEO's is an error this file previously made. Read the `authority`
   note before citing any vocabulary as enforced.

   **And a vendored list can be wrong for its own repository.** The GEO template
   ships `library_layout: ["single", "paired"]`, but
   `scripts/report/mapping.py` keeps `_GEO_LAYOUT_CV = ["single", "paired-end"]`
   in code precisely because GEO rejects `paired` - while CEDAR's HRAVS branch
   returns `single-end`/`paired-end`. Three sources, three literals, one strict
   validator. Where report mode has already corrected a vocabulary, prefer ITS
   list; where the sources simply disagree, bind nothing and raise it as an open
   question.

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
