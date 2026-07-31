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

## Harvest the real evidence BEFORE you derive the tree (not optional)

The tree's structure — especially the **data tier** (how many `D.*`/`A.*` rows, and their
files) — must come from primary sources you have actually read, not from precedent inference or a
skim. Run the SKILL.md **Published-paper harvest** in full *before* writing any node, because the
data tier's row counts are fixed by what was actually generated and deposited, and you cannot know
that from the abstract. Doing this after the fact means re-deriving the tree — the exact failure
this ordering prevents.

1. **Read the whole Methods**, main text AND SI appendix, end to end. Detailed Materials and
   Methods frequently sit at the END of a PNAS/Nature main text or only in the SI — never conclude
   "Methods is thin" from a skim. Extract the sample-prep chain, instrument, treatment dose/time,
   and replicate/plex structure — these fix both the tree shape and the build-phase field values.
   (Manuscript may be `.pdf` or `.docx`; extract text accordingly.)

2. **Grep the manuscript's Data Availability statement for a deposit accession** — cover every
   repository, not just SEEK:
   `PXD`, `ProteomeXchange`, `PRIDE`, `MassIVE`/`MSV`, `GSE`/`GEO`, `PRJNA`/`SRA`, `fairdomhub.org`,
   `SEEK`, `BioStudies`, `zenodo`, `dryad`, `figshare`, and the literal `Data availability`.

3. **If any accession is named, FETCH the deposit and enumerate its files — this is ground truth
   for the data tier**, overriding precedent. Public archives need no auth:

   ```bash
   # PRIDE / ProteomeXchange (PXDxxxxxx): the file manifest + checksums
   curl -sS https://ftp.pride.ebi.ac.uk/pride/data/archive/<YYYY>/<MM>/<PXD>/          # dir index
   curl -sS https://ftp.pride.ebi.ac.uk/pride/data/archive/<YYYY>/<MM>/<PXD>/checksum.txt

   # FairDomHub (already-curated structure): sample titles ARE the UIDs
   curl -sS -H "Accept: application/json" https://fairdomhub.org/studies/<ID>.json   # -> assay ids
   curl -sS -H "Accept: application/json" https://fairdomhub.org/assays/<ID>.json    # -> sample ids
   curl -sS -H "Accept: application/json" https://fairdomhub.org/samples/<ID>.json   # -> title = UID
   ```

   The manifest's raw/processed file set fixes the `D.*`/`A.*` node counts, filenames, and
   checksums. **Cross-check it against the supplementary data files already in `files/`** (e.g. a
   processed-data workbook with one sheet per plex independently confirms the per-branch count).
   Say plainly in each node's `rationale` which source it came from (deposit vs. Methods vs.
   precedent), and prefer deposit > Methods > precedent whenever they disagree on structure.

4. Only a study with **no** Data Availability accession and no deposit is derived from the
   manuscript narrative alone — and even then the full Methods (step 1) still governs the shape.

## Steps

1. Complete the **Harvest** above first (whole Methods main + SI; fetch any named deposit; cross-check
   `files/`). From it, identify the experimental arms AND the deposit-anchored data-tier structure
   (`D.*`/`A.*` counts and their files). Manuscript may be `.pdf` or `.docx` — extract text accordingly.
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
- **For the DATA tier, the deposit and the paper's Methods outrank precedent.** The workbook tells
  you the *format and attribute names* of a `D.*`/`A.*` row; it does NOT tell you how many raw or
  processed files THIS study generated — only the study's own deposit manifest and Methods do. When
  a precedent-based count (e.g. "2 raw files per plex") disagrees with the fetched deposit (e.g. 3
  raw files, one per plex), the deposit wins. Reconciling this after the sheets are built is the
  rework the Harvest step exists to prevent.
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
  manuscript is genuinely thin — then enrich `sample_tree.json` and re-run as answers arrive.
  But "thin" is a conclusion you may reach only AFTER the full Harvest (whole Methods + any named
  deposit), never a reason to skip it. A missing value on an in-prep study is a real gap; a missing
  value on a published/deposited study is almost always a failure to look.
- The HTML loads Cytoscape and dagre from unpkg, so first render needs a network connection.
  It is a single self-contained file otherwise, safe to email to a PI.
