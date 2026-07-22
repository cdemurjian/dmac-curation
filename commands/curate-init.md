---
description: Scaffold or extend a dmac-curation project (Phase 0)
---

The user wants to scaffold a new curation project in the current working
directory, or add a mode to an existing one.

Parse from `$ARGUMENTS`:
- `--lab <CODE>` (e.g. `KAM`, `ENG`, `WHI`, `GRI`)
- `--pi <NAME>` (e.g. `marie`, `lee`, `yufei`)
- `--mode <NAME>` (default `pipeline`; one of `pipeline`, `report`, `schema`)

`--lab` and `--pi` are required for `pipeline` mode only. If missing there, use
`AskUserQuestion` - do NOT guess. `schema` and `report` modes need neither.

## Additive contract

**Create what is missing; never overwrite what exists.** There is no
all-or-nothing prerequisite check and no `--force`. Adding a mode to an existing
project is a first-class path, not an error.

| condition | action |
|---|---|
| file absent | create it |
| file present, this run would produce identical content | leave it, report "unchanged" |
| file present, content would differ | leave it, report "exists - not modified", print a diff summary |

The one exception is the lockfile, which is *merged*, never replaced. Use
`scripts/_lockfile.py` for that; never hand-write the JSON.

## Steps

1. Resolve the plugin path from `$PLUGIN_PATH`, or from this command file's
   grandparent (`<plugin>/commands/curate-init.md` -> `<plugin>/`).

2. Read the plugin's git SHA: `git -C <PLUGIN_PATH> rev-parse HEAD`. If the
   plugin has no `.git` (installed as a tarball), record `null` and warn.

3. Read the schema vintage: `<PLUGIN_PATH>/context/VINTAGE.json` -> `bundled_date`.

4. Create only the missing directories:
   `mkdir -p files manuscript previous_metadata assay_sheets scripts`.
   Skip this entirely for `schema` and `report` modes; they need no scaffold.

5. Render any missing templates. Existing files are never touched:

   ```bash
   uv run --with jinja2 python3 <<'PY'
   from jinja2 import Environment, FileSystemLoader, StrictUndefined
   import datetime, os, pathlib
   plugin = os.environ.get("PLUGIN_PATH", "<PATH>")
   env = Environment(loader=FileSystemLoader(plugin + "/templates"),
                     undefined=StrictUndefined)
   ctx = {"lab": "$LAB", "pi_name": "$PI",
          "init_date": datetime.date.today().isoformat(),
          "modes": ["$MODE"]}
   for tpl, dest in [("CLAUDE.md.j2", "CLAUDE.md"),
                     ("env.example.j2", ".env.example"),
                     ("gitignore.j2", ".gitignore"),
                     ("pyproject.toml.j2", "pyproject.toml")]:
       if pathlib.Path(dest).exists():
           print(f"  exists - not modified: {dest}")
           continue
       extra = {}
       if tpl == "pyproject.toml.j2":
           extra["project_slug"] = f"{ctx['pi_name']}_curation"
       pathlib.Path(dest).write_text(env.get_template(tpl).render(**ctx, **extra))
       print(f"  created: {dest}")
   PY
   ```

6. Merge the mode into the lockfile. **Do not hand-write this JSON** - the
   schema version and plugin version come from `scripts/_lockfile.py`, which is
   the single source of truth and migrates a v0 lockfile in place:

   ```bash
   uv run python3 - <<'PY'
   import sys, pathlib
   sys.path.insert(0, "<PLUGIN_PATH>/scripts")
   import _lockfile
   values = {"lab": "$LAB", "pi": "$PI"} if "$MODE" == "pipeline" else {}
   doc = _lockfile.set_mode(pathlib.Path.cwd(), "$MODE", values)
   print(f"lockfile schema_version={doc['schema_version']} "
         f"plugin_version={doc['plugin_version']} modes={sorted(doc['modes'])}")
   PY
   ```

   The resulting shape:

   ```json
   {
     "schema_version": 1,
     "plugin_version": "<from _lockfile.PLUGIN_VERSION>",
     "plugin_name": "dmac-curation",
     "plugin_sha": "<git rev-parse output, or null>",
     "schema_vintage": "<VINTAGE.json bundled_date>",
     "init_date": "<today>",
     "init_user": "<$USER>",
     "modes": {
       "pipeline": {
         "lab": "<LAB uppercased>",
         "pi": "<PI lowercased>",
         "nextseek_project_id": null
       }
     }
   }
   ```

7. Report: which files were created, which were left alone, which modes the
   lockfile now records, and the suggested next command - `/curate-inventory`
   for pipeline, `/curate-sampletype <TYPE>` for schema,
   `/curate-report <FORMAT> <input>` for report.

## Behavioral rules

- **Create what is missing; never overwrite.** No `--force` flag exists. If the
  user genuinely wants a file replaced, they delete it first.
- If `--lab` or `--pi` is missing for pipeline mode, use `AskUserQuestion`.
  Never guess a lab code; it becomes part of every minted UID.
- A `.env` already present in cwd is a strong signal this is a real project.
  Report it and continue. Never read or print its contents.
- Don't `git init` in the project dir; let the user decide. Suggest it.
- `schema` and `report` modes require no scaffold at all. Running
  `/curate-init --mode schema` in a bare directory creates nothing but a
  lockfile entry, and even that is optional.
