# pipeline mode — review

Date: 2026-07-21
Status: review complete, changes proposed
Companion to `2026-07-21-curation-toolkit-design.md` (see its O2)

## Verdict

**The pipeline is sound. It does not need reworking — it needs correcting.**

The expected finding was that a 13-step sequence had accreted steps that did not
earn their place. That is true of exactly two, and both are bookkeeping artifacts
rather than real phases. The substantive question — whether the 4-sheet
intermediate should be eliminated — resolves in favour of keeping it, for a
reason that is not visible in the code.

Net change: **13 phases -> 11**, plus five defect fixes and one dead capability
brought to life.

## The central question, resolved: keep 4-sheet

Phase 5 builds 20 per-sample-type 4-sheet workbooks; Phase 6 consolidates them
into 5 per-arm flat files. The obvious challenge is why build 4-sheet at all when
flat is what gets uploaded — especially since dmac-assistant's batch-upload
design explicitly drops the 4-sheet workbook.

There is a hard technical reason for two formats, stated in
`consolidate_to_flat.py:19-21`:

> When file has all 4 sheet names (Instructions/Samples/Assay/Ontology), the
> 4-sheet format is auto-detected; otherwise flat. **Multiple sample types in one
> file are ONLY allowed in flat format.**

So per-sample-type files *must* be 4-sheet or must be flat; per-arm files mixing
sample types *must* be flat. But that alone would still allow building flat
directly, since `assay_titles` — the only Assay-tab payload that survives
consolidation — is itself a flat column.

**The deciding reason is human: curators review the per-sample-type 4-sheet files
before consolidation.** The split is what makes eyeballing tractable. This is
institutional knowledge, absent from every doc in the repo, and it is why the
intermediate stays.

**Action:** document this in `PHASES.md`. Phase 5's output is a *review artifact*,
not a build intermediate. A future reader will otherwise re-derive the same
challenge and reach the wrong conclusion.

## The dead capability: the Ontology sheet

`_common.py:194` accepts `ontology: dict[str, list[str]] | None = None` and
`_common.py:249-252` writes a real Ontology sheet with headers
`Field / Database Field / Field Type / Ontology`. This is NExtSEEK's native
controlled-vocabulary mechanism.

It is entirely unused:

| check | result |
|---|---|
| any caller passing `ontology=` | **none** — always `None` |
| `curate-build.md` / `PHASES.md` instructing it be populated | **no** — named only as part of the format |
| `consolidate_to_flat.py` reading it | **no** — the word appears only in the docstring |

So NExtSEEK has a controlled-vocabulary mechanism, the plugin can already write
it, and nothing populates or consumes it.

This matters more now that Phase 5's output is confirmed as a **review artifact**:
populating the Ontology sheet would put allowed values in front of the curator at
exactly the moment they are checking the data.

**Action:** this is `schema` mode's shortest path to value. A field dictionary
produces `{fieldname: [allowed values]}` — precisely `write_4sheet_xlsx`'s
`ontology` parameter shape. `schema` mode gains a native NExtSEEK delivery target
that already exists, instead of emitting CEDAR templates into a vacuum.

### Consolidation discards enforcement — and that is now decided

Verified against `context/NExtSEEK_API.yaml`: ontology validation exists **only**
in the 4-sheet format.

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | *"Ontology validation is not performed in rows mode"* |
| flat xlsx (Phase 6 output) | **none** — the format has no Ontology sheet |
| 4-sheet xlsx (Phase 5 output) | *"Validation is strict; violations reject the file"* |

So Phase 6 converts the format that **can** enforce vocabulary into the one that
cannot. This costs nothing today because nothing populates the Ontology sheet;
it becomes a live loss the moment `schema` mode does.

**Decision: keep both formats.** Phase 5 emits 4-sheet with Instructions and
Ontology populated; Phase 6 continues to emit flat. The curator chooses per
upload. This is a strictly larger capability than today and requires no change to
either phase's mechanics — only that the Ontology sheet stop being empty.

**Action:** `PHASES.md` must state that Phase 6's output cannot carry controlled
vocabulary, so the choice is made knowingly. Adding an ontology column to a flat
sheet does **not** work: `InputRowModel` is `additionalProperties: true` and
unknown columns are *"ignored, with a warning"* — silently discarded rather than
rejected.

**Verify:** the spec read is from 2026-05-27. Confirm with the API owner that
flat still lacks ontology support.

## Per-phase assessment

| Ph | Command | Script | Verdict |
|---|---|---|---|
| 0 | `curate-init` | inline heredoc | **Keep**, made additive (toolkit spec §3) |
| 1 | `curate-inventory` | `inspect_workbook.py` | Keep |
| 2 | `curate-sample-tree` | none | Keep — pure LLM, high value |
| 3 | `curate-questions` | none | Keep |
| 4 | **none** | none | **DELETE as a phase** |
| 5 | `curate-build` | generated `build_<arm>.py` | Keep — review artifact |
| 6 | `curate-consolidate` | `consolidate_to_flat.py` | Keep |
| 7 | `curate-resolve-assays` | `nextseek_api.py` | Keep |
| 8 | **none** | none | **DELETE as a phase** |
| 9 | `curate-qa` | `qa_flat_sheets.py` | Keep |
| 10 | `curate-deposit` | several | Keep; GEO build delegates to `report` |
| 11 | `curate-retrieve` | `build_retrieve.py` | Keep |
| 12 | `curate-validate` | `review_metadata_vs_uploads.py` | Keep |
| 13 | `curate-email` | none | Keep |

### Phase 4 — delete

"Task plan" has no command, no script, and no artifact; `PHASES.md:93-95` records
that it exists only as TaskList state. Using a task list is good practice, not a
pipeline stage. It inflates the count and implies a step the user must invoke.

**Action:** remove from the phase table; fold the guidance into Phase 3's tail.

### Phase 8 — delete

"Synonyms" is already documented as folded into Phase 7 — same command, same
invocation. It exists in the table because `assay_synonyms.json` is a second
artifact, but artifacts are not phases.

**Action:** remove; document `assay_synonyms.json` as a Phase 7 output.

### Renumbering

Deleting 4 and 8 leaves 11 phases. **Do not renumber.** Every project's scaffolded
`CLAUDE.md` (`CLAUDE.md.j2:17-35`) bakes in the current order, `curate-status`
maps phases to artifacts by number, and curators speak in phase numbers ("we're
at 6"). Retire 4 and 8 as numbers and keep the rest stable — the cost of
renumbering is borne by humans, not code.

*(Aside: `CLAUDE.md.j2` currently lists **11 steps** while the table claims 13 —
the template already reflects the corrected count.)*

## Defects to fix (detail in the toolkit spec)

1. **Phase 12 never reads `RETRIEVE.TXT`.** `PHASES.md:246` names it as an input;
   `review_metadata_vs_uploads.py` has no `--retrieve` flag. Either wire it or
   correct the doc — silently ignoring a documented input is the worse failure.
2. **Phase 10 GEO is a dead end.** Nothing produces `BULK_filled.json`; no GEO
   template xlsx ships. Fixed by delegating the build to `report` mode.
3. **Contradictory dry-run conventions inside Phase 10.** `stage_zenodo.py` and
   `apply_zenodo_links.py` default to **writing**; `apply_geo_accessions.py` and
   `apply_omero_ids.py` default to dry-run. `curate-deposit.md:33` claims all
   default to dry-run. Data-loss trap.
4. **Four more documented-but-nonexistent flags** (toolkit spec, Immediate items).
5. **Ontology silently dropped at consolidation** — acceptable today only because
   it is never populated. Revisit when `schema` mode starts populating it.

## What this review did not find

No evidence for the larger rework that prompted it. Specifically:

- **No redundant phases** beyond the two bookkeeping entries.
- **No phase in the wrong order.** Deposit-before-upload is deliberate: GEO
  accessions must be backfilled into the sheets before they go to NExtSEEK.
- **No case for dropping 4-sheet**, once the human-review reason is known.
- **The five script-less phases (2, 3, 4, 8, 13) are not a smell.** Sample tree,
  questions, and the PI email are judgment work; that they are prompt-and-template
  is correct, not incomplete.

The pipeline's problems are **documentation drift and two unfixed defects**, not
structure. The complexity Charlie perceived is better explained by the toolkit
spec's finding: the pipeline was the plugin's *only* organising principle, so
everything — including FDH, and now schema and report — had to be described
relative to it. Making it one mode among several removes the felt complexity
without changing the pipeline at all.
