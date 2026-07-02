---
description: Programmatic FairDomHub API access — reuse-or-generate a task script (Module 2)
---

The user wants Claude to perform an FDH/SEEK API operation programmatically
(e.g. "find every sample linked to assay 2809 and delete them"). Follow the
reuse-first loop below. Full detail lives in `<PLUGIN>/skills/curation/FDH.md`.

Parse `$ARGUMENTS`:
- `refresh-index` → regenerate the API index (maintenance).
- `list` → print the generated-script registry.
- (anything else / empty) → treat as a natural-language task and run the loop.

## The reuse-or-generate loop

1. **Check the library first.** Read `<PLUGIN>/scripts/fdh/generated/REGISTRY.md`. If a
   script already covers the task, run it (respecting its `--dry-run` default).
2. **Else consult the index.** Read `<PLUGIN>/context/fdh_api_index.json`. Match the task
   against `intent_patterns` / `category` / `llm_hint`; pick the endpoint(s).
3. **Pull only the relevant YAML.** `Read` `<PLUGIN>/context/full-fdh-openapi-spec.yaml`
   at the `yaml_lines` ranges of the chosen entries — never the whole file.
4. **Generate + run.** Write a PEP 723 script under `<PLUGIN>/scripts/fdh/generated/`
   using the template in FDH.md: it imports `FairDomHubClient` from `../fdh_api.py`
   (i.e. `<PLUGIN>/scripts/fdh/fdh_api.py`),
   defaults writes to `--dry-run` (prints a preview), and requires `--write` +
   confirmation before mutating anything.
5. **Contribute back.** Add a `REGISTRY.md` row, show the user the diff, and commit on approval.

## Maintenance sub-routes

- `refresh-index`: run `uv run --script <PLUGIN>/scripts/fdh/build_api_index.py`, then
  show the diff of `context/fdh_api_index.json`.
- `list`: print the `REGISTRY.md` table.

## Behavioral rules

- Destructive ops (DELETE/PATCH) are dry-run first, always. Show exactly what will change,
  get explicit confirmation, then re-run with `--write`.
- Credentials come from `.env` (`FDH_API`); never log them.
- New generated scripts are committed only after the user reviews the diff.
