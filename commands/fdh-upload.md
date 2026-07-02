---
description: Launch the interactive FairDomHub study-upload tool (Module 1)
---

The user wants to upload a study to FairDomHub (fairdomhub.org) using the interactive
submission tool `submit.py`. This is a standalone track — it does NOT consume the
13-phase NExtSEEK artifacts.

## Prereqs (verify before handing off)

- `./.env` in the cwd has `FDH_API={"<name>": "<token>"}` (JSON). If absent, show the
  format from `<PLUGIN>/skills/curation/FDH.md` and stop.
- An `Assets/` folder in the cwd with:
  - one metadata workbook `Assets/<name>.xlsx` — each sheet = one Sample Type, and a
    `UID` column is required (it becomes each record's title),
  - `Assets/Protocols/` holding protocol files (`.pdf`, `.docx`, …) to upload as SOPs.
- The **Study has already been created manually** on the FDH web UI, and its numeric ID
  is known (from the URL, e.g. `/studies/1421` → `1421`).

## Steps

1. Confirm the prereqs above. Do not mint anything — this tool is human-driven.
2. Summarize the flow so the user knows what to expect:
   Config → Assays → Protocols → Metadata rewrite → Sample types → Samples → Publish.
   Each step writes a CSV to `Assets/Output/` and can be resumed (`--resume` / `--step N`).
3. Hand off — the user runs it interactively themselves (Claude cannot answer the
   questionary prompts):
   `uv run --script <PLUGIN>/scripts/fdh/submit.py`
4. Offer to review `Assets/Output/*.csv` afterward to sanity-check results.

## Behavioral rules

- Never edit `submit.py` to bypass its prompts. It is intentionally interactive.
- `Assets/Output/session.json` stores the API token in plain text. The plugin cannot ignore it
  for the user (submit.py runs in their own working directory), so tell the user to add
  `Assets/Output/` to their project's `.gitignore` and never commit it.
- Known project IDs live in `PROJECT_MAPPING` inside `submit.py`; new projects are added there.
