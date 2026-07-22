---
description: Derive SAMPLE_TREE.md + interactive SAMPLE_TREE.html from manuscript + master + context (Phase 2)
---

The user wants Phase 2 — map the manuscript narrative to NExtSEEK sample types.

Phase 2 emits **three artifacts describing one tree**:

| File | Purpose |
|---|---|
| `SAMPLE_TREE.md` | Narrative + ASCII trees + UID assignment. The document curators read and edit. |
| `sample_tree.json` | Machine-readable nodes/edges. The source the HTML renders from. |
| `SAMPLE_TREE.html` | Interactive graph for PI/curator review — click any node or edge for its evidence quotes, rationale, and flags. |

Derive the tree **once**, then emit all three from that single derivation. They must never
disagree; a reviewer who spots the HTML and the Markdown telling different stories has to
discard both.

## Prereqs

- `./FILE_INDEX.md` exists (or run `/curate-inventory` first)
- `./manuscript/` non-empty
- `./previous_metadata/*.xlsx` exists

## Steps

1. Read `manuscript/*.docx` extracted text. Identify experimental arms.
2. Read `<PLUGIN>/context/sampletypes_db.json` (101 types) and `<PLUGIN>/context/assays_db.json` (217 assays).
3. For each arm, identify required sample types. Use the master xlsx to determine `[EXIST]` (existing UIDs) vs `[NEW]` (to be created).
4. For each new sample type, infer parent type — **sample existing PI rows first**, fall back to `sampletypes_db.json` if no precedent.
5. Build ASCII trees per arm.
6. Surface 5-15 open structural questions at the bottom (cohort sizes, parentage ambiguity, vocabulary gaps, file path completeness, deposit destinations).
7. Render `<PLUGIN>/templates/SAMPLE_TREE.md.j2` → `./SAMPLE_TREE.md`.
8. Write `./sample_tree.json` from the same derivation. Full schema is in the module docstring of
   `<PLUGIN>/scripts/build_sample_tree_html.py`. In short:
   - **one node per sample type**, not per specimen — set `count` to the number of rows that type
     will produce, and it renders as `TIS ×39`
   - **one edge per parent→child connection**, with `assays` naming the assay that licenses it
     (the same assay you verified in `context/neo4j_assay-sample-conn.json`)
   - **omit `clade`** — it is derived from the assay's `Parent Clade Type` / `Child Clade Type`
   - carry the manuscript evidence you already gathered in step 1 onto each node and edge:
     `quotes` (verbatim), `sources`, `rationale`, `evidence_strength`
9. Run `uv run --script <PLUGIN>/scripts/build_sample_tree_html.py` → `./SAMPLE_TREE.html`.
   Resolve every clade warning it prints rather than ignoring it — a warning means the assay
   definition and the declared clade disagree, which is a real modelling error, not noise.
10. Suggest `/curate-questions add` to formalize the open questions, or `/curate-build <arm>` to start.

## Behavioral rules

- Schema lies; workbook tells truth. Sample 5-10 existing PI rows per sample type before consulting the schema JSON.
- For sample types not in `sampletypes_db.json`, mark `PENDING_SCHEMA` and add a question for the NExtSEEK admin.
  In `sample_tree.json` the same node gets `"match_type": "proposed_new"`, which draws it with a
  dashed amber border so a reviewer can see at a glance what does not yet exist in NExtSEEK.
- Trees are ASCII art, not prose. The user explicitly prefers concrete trees with real UIDs.
- Distinguish `[EXIST]` (existing UID, reused) from `[NEW]` (to be minted this curation).
- Never hand-write `SAMPLE_TREE.html` or edit it after generation — it is a build artifact.
  Change `sample_tree.json` and re-run the script.
- Prefix any caveat in a `rationale` with `NOTE FOR CURATOR` or `FLAG FOR CURATOR`; the viewer
  pulls those into a highlighted callout. Use it for offline holdings, partial file coverage,
  placeholder parentage, and anything a reviewer would otherwise have to read the Markdown to find.
- Evidence fields are optional and render only when present, so emit the tree even when the
  manuscript is thin — then enrich `sample_tree.json` and re-run as answers arrive.
- The HTML loads Cytoscape and dagre from unpkg, so first render needs a network connection.
  It is a single self-contained file otherwise, safe to email to a PI.
