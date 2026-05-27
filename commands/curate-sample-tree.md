---
description: Derive SAMPLE_TREE.md from manuscript + master + context (Phase 2)
---

The user wants Phase 2 — map the manuscript narrative to NExtSEEK sample types as ASCII trees.

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
8. Suggest `/curate-questions add` to formalize the open questions, or `/curate-build <arm>` to start.

## Behavioral rules

- Schema lies; workbook tells truth. Sample 5-10 existing PI rows per sample type before consulting the schema JSON.
- For sample types not in `sampletypes_db.json`, mark `PENDING_SCHEMA` and add a question for the NExtSEEK admin.
- Trees are ASCII art, not prose. The user explicitly prefers concrete trees with real UIDs.
- Distinguish `[EXIST]` (existing UID, reused) from `[NEW]` (to be minted this curation).
