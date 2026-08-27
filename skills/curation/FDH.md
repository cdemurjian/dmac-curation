# FairDomHub (FDH) integration — reference

Load on demand when the user wants to **upload to FairDomHub** or **access the FDH API**.
These are two independent, standalone capabilities — NOT part of the NExtSEEK curation
pipeline (12 phases across 11 numbers, `PHASES.md`); they do not consume
`assay_sheets/` / flat sheets.

- **Module 2 (`/fdh-api`)** — host `https://fairdomhub.org` by default; override
  with `--base-url` or `.env` `FDH_BASE_URL` (`scripts/fdh/fdh_api.py:198-201`).
- **Module 1 (`/fdh-upload`) is production-only.** `submit.py` hardcodes
  `BASE_URL = "https://fairdomhub.org/"` (`scripts/fdh/submit.py:73`) and reads no
  host from the environment; its only flags are `--step N` and `--resume`
  (`:1780-1841`). There is no staging mode. Every run writes to fairdomhub.org.
- Auth: `.env` `FDH_API` = JSON `{ "<name>": "<token>" }`. Token from
  fairdomhub.org → Profile → Actions → API Token. Never log tokens.
  - Module 2 resolves in order `--token` → `$FDH_TOKEN` → `$FDH_API`
    (`scripts/fdh/fdh_api.py:172-195`). Inside `FDH_API`: `--user NAME` selects;
    a one-entry map auto-selects; **two or more entries with no `--user` exits 2.**
  - `.env` is read from the current directory first, then the plugin checkout,
    with `setdefault` semantics — an exported shell variable wins over both
    (`fdh_api.py:159-169`).
  - Module 1 reads only `FDH_API` and picks the user through an interactive
    prompt (`submit.py:1281`, `:1295-1301`); it honours neither `FDH_TOKEN` nor
    `--token`.

## Module 1 — Upload a study (`/fdh-upload`)

Interactive, human-run tool: `scripts/fdh/submit.py`. Claude checks prereqs and
hands off; it cannot answer the tool's prompts. See `commands/fdh-upload.md`.
**Production-only** — see the host note above.

Workbook format: each sheet = one Sample Type; each column = one attribute; a
`UID` column is required (it becomes the record title,
`scripts/fdh/submit.py:700`, `:869-870`). Columns whose every non-empty cell is a
URL/DOI are auto-typed URI (`column_is_all_links`, `:630-633`). Known project IDs
live in `PROJECT_MAPPING` (`:77-83`); a manual numeric id can also be entered.

Resumable via `--resume` / `--step N` (mutually exclusive; the only two flags).
Most steps write a CSV to `Assets/Output/` — step 3 does not.

| step | what it does | gate |
|---|---|---|
| 0 Config | pick user, study id, project(s), workbook | — |
| 1 Assays | `POST /assays` | confirm, default **no** |
| 2 Protocols | `POST /sops` then `PUT` the bytes | confirm, default yes |
| 3 Metadata rewrite | **overwrites your workbook in place** | confirm, default yes |
| 4 Sample types | `POST /sample_types`, one per sheet | **none** |
| 5 Samples | `POST /samples` | confirm, default yes |
| 6 Publish | PATCHes every study asset to public | confirm, default **no** |

Three of those deserve saying out loud before a run:

- **Step 3 destroys workbook formatting.** It rewrites `cfg["workbook"]` to its own
  path through a `read_excel` → `ExcelWriter` round trip (`:1495`, `:570-622`):
  cell formatting, data validation, merged cells and formulas do not survive.
  Take a copy of the workbook first — the tool keeps no backup.
- **Step 4 has no confirmation.** If `Assets/Output/sample_types_created.csv` is
  absent or does not cover the workbook's sheets, one SampleType is created on
  fairdomhub.org per sheet with no prompt (`:1568-1573`, reuse offer `:1512-1547`).
- **Step 6 always runs.** `step_publish(cfg)` is called unconditionally at `:1940`,
  outside every start-step guard, so even `--step 5` reaches it. It sets
  `policy.access` to `view` or `download` on every discovered asset — assays, SOPs,
  sample types, samples, data files, models, presentations, publications — plus a
  `manage` permission for the **first** selected project only (`:1023-1024`, `:1654`,
  `:1107-1146`). Its deny-by-default confirm is the only thing stopping it. The
  study record itself is not published.

## Module 2 — Programmatic API access (`/fdh-api`)

A self-extending toolkit — but the extension is **local to your checkout**.
`scripts/fdh/generated/*.py` is gitignored (`.gitignore:154-156`: the scripts are
written against live project ids, frequently carry sample uids, and several are
destructive), so generated scripts never ship with the plugin and a fresh install
always starts with an empty library.

When the user asks for an API operation ("find all samples for assay X and delete
them"), follow the reuse-or-generate loop:

1. **Try the read CLI first** — see "The read-only CLI" below. Many tasks
   ("what is linked to assay 123?") need no script at all.
2. **Check the local library** — read `scripts/fdh/generated/REGISTRY.md`. Reuse a
   script if one fits. Expect it to be empty on a fresh checkout; that is normal.
3. **Consult the index** — `context/fdh_api_index.json`, a list of enriched
   endpoint entries: `path, method, operation_id, summary, category,
   primary_entities, intent_patterns, llm_hint, yaml_lines`. Match on
   `intent_patterns` / `category` / `llm_hint`. Every DELETE entry's `llm_hint` is
   prefixed "DESTRUCTIVE — irreversible on the live repo"
   (`scripts/fdh/build_api_index.py:129`).
4. **Pull only the relevant YAML** — `Read` `context/full-fdh-openapi-spec.yaml` at
   each chosen entry's `yaml_lines` `[start, end]`. Never load the whole 640 KB file.
5. **Generate + run** — write a script under `scripts/fdh/generated/` (template below).
6. **Record it** — add a `REGISTRY.md` row and show the diff. `REGISTRY.md` is
   tracked and the script is not, so committing the row alone would ship a pointer
   to a file nobody else has: commit the row only if the user wants the *description*
   shared, and say plainly that the script itself stays local.

Nothing enforces the dry-run/`--write` convention — no lint, no test, no shared
helper. It holds only because the generating agent follows the template.

Regenerate the index after an API bump: `uv run --script scripts/fdh/build_api_index.py`.
It rewrites `context/fdh_api_index.json` **inside the plugin checkout**
(`build_api_index.py:22-24`, `:177`); show the diff.

### The read-only CLI — try this before generating anything

`fdh_api.py` is also a CLI with five read verbs
(`scripts/fdh/fdh_api.py:234-274`). Every subcommand takes `--token`, `--user`
and `--base-url`.

```bash
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py whoami
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py search "<query>" [--type samples]
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py get assays 123
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py list assays 123 samples
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py download-blob <url> --out <path>
```

**There is no write verb, by design.** `post` / `patch` / `delete` exist on the
client but are wired to no subcommand — "used by generated scripts, never by this
read CLI" (`fdh_api.py:146`). Every FDH write goes through a per-task generated
script carrying its own `--write` gate. Transient `429/502/503` are retried up to
5 times with exponential backoff (`fdh_api.py:35`, `:69-89`); anything else `>=400`
raises `FDHError`.

### The shared client

`from fdh_api import FairDomHubClient` (add `scripts/fdh/` to `sys.path` — see template).
Methods: `get(type, id)`, `search(q, search_type=None)`, `page_through(url)`,
`list_related(type, id, relationship)`, `whoami()`, `post(type, payload)`,
`patch(type, id, payload)`, `delete(type, id)`, `download_blob(url, dest)`.
Common patterns:
- Samples linked to an assay: `client.list_related("assays", assay_id, "samples")` →
  list of `{id, type}` refs.
- Delete a sample: `client.delete("samples", sample_id)`.

### Generated-script template (dry-run first, always)

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""<one-line purpose — becomes the REGISTRY.md row>.

Endpoints: GET /assays/{id} (relationships.samples), DELETE /samples/{id}.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # -> scripts/fdh/
from fdh_api import FairDomHubClient, make_client  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--token")
    p.add_argument("--user")
    p.add_argument("--base-url", default=None)
    p.add_argument("assay_id")
    p.add_argument("--write", action="store_true",
                   help="Actually perform deletes (default is a dry-run preview).")
    args = p.parse_args()
    client = make_client(args)

    refs = client.list_related("assays", args.assay_id, "samples")
    ids = [r["id"] for r in refs]
    print(f"{len(ids)} samples linked to assay {args.assay_id}: {ids}")
    if not args.write:
        print("DRY-RUN — pass --write to delete. Nothing changed.")
        return 0
    confirm = input(f"Delete {len(ids)} samples? type 'yes': ")
    if confirm.strip().lower() != "yes":
        print("aborted."); return 1
    for sid in ids:
        client.delete("samples", sid)
        print(f"deleted sample {sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Safety (hard rules)

- Destructive generated scripts default to dry-run; require `--write` + an interactive
  confirmation before any DELETE/PATCH.
- New generated scripts are committed only after the user reviews the diff (review-then-commit).
- Credentials come from `.env` only; never printed or committed. `Assets/Output/session.json`
  (from submit.py) holds a token in plaintext — the user must add `Assets/Output/` to their
  project's `.gitignore`; the plugin cannot guarantee it since submit.py runs in the user's
  own working directory.
