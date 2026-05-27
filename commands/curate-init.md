---
description: Scaffold a new dmac-curation project (Phase 0)
---

The user wants to scaffold a new curation project in the current working directory.

Parse from $ARGUMENTS: `--lab <CODE>` (e.g., `KAM`, `ENG`, `WHI`, `GRI`) and `--pi <NAME>` (e.g., `marie`, `lee`, `yufei`). Both required. If missing, use `AskUserQuestion` to prompt — do NOT guess.

## Prereqs check

1. Verify cwd is empty or contains only PI inputs. The following must NOT already exist (else abort unless user adds `--force`):
   - `CLAUDE.md`
   - `.dmac-curation.json`
   - `scripts/` (with contents)
   - `context/` (with contents)
2. Verify the plugin is reachable. The plugin path is the directory containing this command file's grandparent (`<plugin>/commands/curate-init.md` → `<plugin>/`).

## Steps

1. Resolve plugin path from `$PLUGIN_PATH` env or via the path of this command file.
2. Read plugin's git SHA: `git -C <PLUGIN_PATH> rev-parse HEAD` (gracefully handle missing git).
3. Read schema vintage: `<PLUGIN_PATH>/context/VINTAGE.json` → `bundled_date` field.
4. Create directories: `mkdir -p files manuscript previous_metadata assay_sheets scripts`.
5. Render templates by reading `<PLUGIN_PATH>/templates/<NAME>.j2` and substituting placeholders. Inline render via Python + Jinja2:

   ```bash
   uv run --with jinja2 python3 <<'PY'
   from jinja2 import Environment, FileSystemLoader, StrictUndefined
   import json, datetime, os
   plugin = os.environ.get("PLUGIN_PATH", "<PATH>")
   env = Environment(loader=FileSystemLoader(plugin + "/templates"), undefined=StrictUndefined)
   ctx = {"lab": "$LAB", "pi_name": "$PI", "init_date": datetime.date.today().isoformat()}
   for tpl, dest in [("CLAUDE.md.j2", "CLAUDE.md"),
                     ("env.example.j2", ".env.example"),
                     ("gitignore.j2", ".gitignore"),
                     ("pyproject.toml.j2", "pyproject.toml")]:
       template = env.get_template(tpl)
       extra = {}
       if tpl == "pyproject.toml.j2":
           extra["project_slug"] = f"{ctx['pi_name']}_curation"
       with open(dest, "w") as f:
           f.write(template.render(**ctx, **extra))
   PY
   ```

6. Write `.dmac-curation.json` lockfile:
   ```json
   {
     "plugin_name": "dmac-curation",
     "plugin_sha": "<git rev-parse output>",
     "plugin_version": "0.1.0",
     "schema_vintage": "<VINTAGE.json bundled_date>",
     "init_date": "<today>",
     "init_user": "<$USER>",
     "lab": "<LAB uppercased>",
     "pi": "<PI lowercased>",
     "nextseek_project_id": null
   }
   ```
7. Report to user:
   - Which files were written
   - Reminder to drop inputs into `files/`, `manuscript/`, `previous_metadata/`
   - Suggested next: `/curate-inventory`

## Behavioral rules

- Never overwrite an existing `CLAUDE.md` without explicit `--force` (and even then, confirm).
- If `--lab` or `--pi` missing, use `AskUserQuestion` with single-select options derived from any `<plugin>/labs/` (if exists), else prompt freely.
- If plugin has no `.git` (e.g., installed as a tarball), record `"plugin_sha": null` and continue.
- Don't initialize git in the project dir — let the user decide. But suggest it in the report.
- Refuse if cwd contains `.env` (might be a real project already) unless `--force`.
