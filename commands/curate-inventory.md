---
description: Build FILE_INDEX.md from PI inputs (Phase 1)
---

The user wants Phase 1 — inventory of inputs.

## Prereqs

- `.dmac-curation.json` exists (or run `/curate-init` first)
- At least one of `files/`, `manuscript/`, `previous_metadata/` has content (warn if all empty but proceed anyway with empty FILE_INDEX)

## Steps

1. Walk `files/` with `tree -L 2 -h` or `ls -lh`. Capture sizes per top-level subdir.
2. List `manuscript/`. If a `.docx` is present, extract text via Python+zipfile and grep for "Methods" / "Results" section headers.
3. For each xlsx in `previous_metadata/`, invoke `uv run --script <PLUGIN>/scripts/inspect_workbook.py <path>`. Capture sheet names, row counts.
4. Read `email_convo.md` if present; summarize sender list and topic threads.
5. Identify the PI's existing rows in the master xlsx — filter `Scientist` column or Notes column for the PI's name. Count per sample type.
6. Surface "things to flag now" — anything that looks like a blocker (missing master xlsx, manuscript without Methods, file types you can't parse).
7. Render `<PLUGIN>/templates/FILE_INDEX.md.j2` with the gathered context → `./FILE_INDEX.md`.
8. Suggest `/curate-sample-tree`.

## Behavioral rules

- If `previous_metadata/` has multiple xlsxs, list them all; mark the most-recent as master.
- For very large `files/` trees, summarize per-figure / per-arm without listing every file.
- Use the `inspect_workbook.py` script — don't reimplement inline.
