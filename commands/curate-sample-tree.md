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

## If the paper is already curated (uncommon — check, don't dwell)

**Most papers reaching this pipeline are NOT yet curated; deriving the tree from the manuscript is
the normal path.** But a minority are already deposited, and re-deriving one of those by hand
produces a tree that silently disagrees with the published structure. So spend one grep on it,
then move on.

Do NOT go looking online beyond this check, and never treat the absence of a deposit as a problem —
it is the expected case.

1. Grep the manuscript for `fairdomhub.org`, `SEEK`, `BioStudies`, `PRJNA`, `GSE`, `zenodo`, `dryad`.
   No hit — which is usual — means derive from the manuscript and skip the rest of this section.
2. If, and only if, a FairDomHub study is explicitly named, read its real structure — public
   studies need no auth — and prefer it over inference:

   ```bash
   curl -sS -H "Accept: application/json" https://fairdomhub.org/studies/<ID>.json   # -> assay ids
   curl -sS -H "Accept: application/json" https://fairdomhub.org/assays/<ID>.json    # -> title + sample ids
   curl -sS -H "Accept: application/json" https://fairdomhub.org/samples/<ID>.json   # -> title = the UID
   ```

   Each assay lists the samples on **both** ends of the edge it licenses. Sample titles are UIDs
   (`PAV-240116FLY-1`), so the prefix gives you the sample type. Probe a handful of samples per
   assay and the real node set and edge set fall out directly.
3. Use that structure as the tree. Fall back to manuscript inference only for what the deposit
   does not cover, and say plainly in the rationale which nodes came from which source.

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
     will produce, and it renders as `TIS ×24`
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
- **`proposed_new` means "the schema does not license this", not "I could not find it in a deposit".**
  Those are different failures. A schema-legal edge that is missing from an existing deposit is a
  *coverage* gap — record it in the rationale and leave `match_type` alone. Marking it proposed
  renders it dashed and tells the curator to file a vocabulary request that would be rejected.
  The generator now checks this against the connection graph and warns either way, so run it and
  read the output before believing your own tree.
- **Use the exact assay name, including the `- Metadata` and `- Data Linked` suffixes.** These are
  distinct assays, not decoration: `Tissue Collection` and `Tissue Collection - Metadata` are
  separate entries in `assays_db.json` and the connection graph. The suffix records whether the
  tier carries data files (`- Data Linked`) or only registers rows (`- Metadata`). Picking the bare
  name when the curated deposit uses the suffixed one silently misstates whether files are attached.
- **Take the shortest legal path that is actually attested; never invent an intermediate.** If
  `TIS -> D.FLOW` is legal, use it. Inserting a `CEL` node because a cell suspension physically
  exists adds a tier that the schema does not model and that no real deposit contains. Model the
  wet-lab step as an attribute, not a node.
- **Follow the biological chain for molecular data.** Sequencing an organism recovered from a host
  goes `TIS -> BAC -> DNA -> D.SEQ`, not `TIS -> DNA`: the DNA belongs to the extracted organism,
  not to the host tissue. Getting this wrong collapses a real tier and orphans the isolate.
- **Before declaring a vocabulary gap, check whether an existing sample type already carries the
  measurement as an attribute.** A quantitative readout is not automatically its own data type.
  Bacterial burden lives on the `BAC` sample produced by `Bacterial Extraction`, not on a separate
  CFU data node. Only propose a new type after confirming no existing tier is the intended home —
  a false `proposed_new` sends the curator to the NExtSEEK admins for nothing.
- **UID lab code and date stamp are per curation batch, not per project.** One study can legitimately
  mix them: FairDomHub study 1395 carries `NHP-240116FLY-*` and `PAV-240116FLY-*` for the animal tier
  alongside `DNA-250702FOR-*` and `D.SEQ-250722FOR-*` for the molecular tier — two labs, three dates,
  one tree. Do not force a single stamp across every tier; record the batch each tier belongs to.
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
