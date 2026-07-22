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

## The mode never applies anything

It **never writes to NExtSEEK** and never edits `sampletypes_db.json`. Its
product is a proposal with rationale, which a human reviews and applies by hand.

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

3. **Identify gaps.** What does this assay actually produce that the record does
   not capture? For a viability assay: readout type, instrument, timepoint, dose,
   units, replicate, controls.

4. **Run the reuse check before minting any new name.** For each candidate,
   `rank_candidates(name, index, clade=..., assay=..., catalog=...)`. Show the
   user the candidate name, how many types use it, which ones, and example
   values. **The curator judges** - the tool never decides.

   A field name shared across sample types is **not** a defect. `Type` appears
   on many types and legitimately means different things on each. Never propose
   a rename or a split.

5. **Propose controlled values.** `scripts/schema/ontology.py` `propose_values()`
   mines the Tags column first (it is often already a list of permissible
   values), then observed values, then siblings, then BioPortal via
   `scripts/schema/terms.py` if `BIOPORTAL_API_KEY` is set. Without a key the
   first three still work; say so rather than failing.

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
