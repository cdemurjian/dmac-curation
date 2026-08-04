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

If `--mode` is any value outside `{pipeline, schema, report}`, stop with a clear
error (e.g. `unknown mode: <value>`) before doing anything else. Never call
`set_mode` with an unrecognised mode - a typo like `--mode piepline` must not
mint a junk mode section.

## Additive contract

**Create what is missing; never overwrite what exists.** There is no
all-or-nothing prerequisite check and no `--force`. Adding a mode to an existing
project is a first-class path, not an error.

| condition | action |
|---|---|
| file absent | create it |
| file present | leave it, report "exists - not modified" |

The check is presence-only: the command does not compare contents. If you happen
to notice by eye that an existing file looks stale, you may mention it - but that
is best-effort prose, not a guaranteed step, and nothing is ever rewritten.

The one exception is the lockfile, which is *merged*, never replaced. Use
`scripts/_lockfile.py` for that; never hand-write the JSON.

## Steps

1. Resolve the plugin path from `$PLUGIN_PATH`, or from this command file's
   grandparent (`<plugin>/commands/curate-init.md` -> `<plugin>/`).

2. Read the plugin's git SHA: `git -C <PLUGIN_PATH> rev-parse HEAD`. If the
   plugin has no `.git` (installed as a tarball), record `null` and warn.

3. Read the schema vintage: `<PLUGIN_PATH>/context/VINTAGE.json` -> `bundled_date`.

**Steps 4 and 5 - the pipeline scaffold (directories AND rendered templates) -
run only in pipeline mode.** For `--mode schema` and `--mode report`, do both
skips: create no directories and render no templates. Skip straight to the
lockfile merge in Step 6. `schema` and `report` produce nothing but a lockfile
entry (Step 6) and a report (Step 7); they never collect a `lab`/`pi`, so there
is nothing to render.

4. In pipeline mode only, create the missing directories:
   `mkdir -p files manuscript previous_metadata assay_sheets scripts`.

5. In pipeline mode only, render any missing templates. Existing files are
   never touched:

   ```bash
   # render scaffold only in pipeline mode; schema and report skip this step
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

   **In pipeline mode, also provision the working `.env`** by copying a
   pre-filled credentials file pointed to by `$DMAC_ENV_FILE`. This is what lets
   the curator immediately pull a fresh DB export into `previous_metadata/` with
   `nextseek_api.py pull-db --project-id N` (which the build guard then checks).
   The source MUST live OUTSIDE any git repo so credentials are never committed.
   Additive: never overwrite an existing `.env`; never read or print its
   contents.

   ```bash
   # pipeline mode only: copy the filled credentials file into the project
   if [ "$MODE" = "pipeline" ]; then
     if [ -f "./.env" ]; then
       echo "  exists - not modified: .env"
     elif [ -n "$DMAC_ENV_FILE" ] && [ -f "$DMAC_ENV_FILE" ]; then
       cp "$DMAC_ENV_FILE" "./.env" && chmod 600 "./.env"
       echo "  created: .env  (copied from \$DMAC_ENV_FILE)"
     else
       echo "  NOTE: no .env copied — set DMAC_ENV_FILE to your filled credentials"
       echo "        file (kept outside any git repo) and re-run, or fill"
       echo "        .env.example by hand. NExtSEEK creds in .env are what the"
       echo "        DB pull and the build stamp-guard need."
     fi
   fi
   ```

6. Merge the mode into the lockfile. **Do not hand-write this JSON** - the
   schema version and plugin version come from `scripts/_lockfile.py`, which is
   the single source of truth and migrates a v0 lockfile in place:

   ```bash
   uv run python3 - <<'PY'
   import sys, pathlib
   sys.path.insert(0, "<PLUGIN_PATH>/scripts")
   import _lockfile
   # normalize before storing so the lockfile matches the shape below:
   # LAB uppercased, PI lowercased. schema/report collect no lab/pi -> {}
   values = ({"lab": "$LAB".upper(), "pi": "$PI".lower()}
             if "$MODE" == "pipeline" else {})
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
- **`.env` is copied, never rendered with secrets.** The filled source is
  `$DMAC_ENV_FILE`; init only `cp`s it and `chmod 600`s the copy — it never reads
  the values. If `$DMAC_ENV_FILE` is unset/missing, fall back to `.env.example`
  (the template, which stays blank) and tell the user. Never write real
  credentials into a template or commit a filled `.env`; the project `.gitignore`
  already ignores `.env`, and the source must live outside any git repo.
- Don't `git init` in the project dir; let the user decide. Suggest it.
- `schema` and `report` modes require no scaffold at all. Running
  `/curate-init --mode schema` in a bare directory creates nothing but a
  lockfile entry, and even that is optional.
