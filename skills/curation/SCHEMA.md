# `schema` mode — sample type authoring

Deep reference for the `schema` mode. Load on demand.

**Status: stub.** Filled by Task 23 of
`docs/superpowers/plans/2026-07-21-curation-toolkit.md`.
Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

Purpose: answer "what are we collecting?" for a NExtSEEK sample type. Produces
a proposed sample type record, a controlled vocabulary, and a rationale
document a human reviews and applies by hand. Never writes to NExtSEEK, never
edits `sampletypes_db.json`.

State scope: **cwd**. Reads the plugin's `context/` read-only; writes every
artifact into the current working directory. No lockfile, no scaffold.
