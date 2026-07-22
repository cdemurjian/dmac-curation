# `report` mode — submission artifact generation

Deep reference for the `report` mode. Load on demand.

**Status: stub.** Filled by Task 34 of
`docs/superpowers/plans/2026-07-21-curation-toolkit.md`.
Design: `docs/superpowers/specs/2026-07-21-report-mode-design.md`.

Purpose: "I have file X.xlsx with metadata, turn it into a GEO report."
Produces GEO / SRA / PRIDE submission artifacts from whatever metadata the
curator has. The LLM emits a declarative mapping spec once; execution across
all rows is deterministic.

State scope: **input**. Reads a project lockfile when present, for lab and
project id, but must run without one from any cwd.
