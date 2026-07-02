# FairDomHub (FDH) integration — reference

Load on demand when the user wants to **upload to FairDomHub** or **access the FDH API**.
These are two independent, standalone capabilities — NOT part of the 13-phase NExtSEEK
pipeline (they do not consume `assay_sheets/` / flat sheets).

- Host: `https://fairdomhub.org` (default). Override via `.env` `FDH_BASE_URL` or `--base-url`.
- Auth: `.env` `FDH_API` = JSON `{ "<name>": "<token>" }`. Token from fairdomhub.org →
  Profile → Actions → API Token. Never log tokens.

## Module 1 — Upload a study (`/fdh-upload`)

Interactive, human-run tool: `scripts/fdh/submit.py`. Claude checks prereqs and hands off;
it cannot answer the tool's prompts. See `commands/fdh-upload.md`.

Flow: Config → Assays → Protocols (SOPs) → Metadata rewrite → Sample types → Samples →
Publish. Resumable via `--resume` / `--step N`; each step writes a CSV to `Assets/Output/`.

Workbook format: each sheet = one Sample Type; each column = one attribute; a `UID` column
is required (becomes the record title). Columns that are entirely URLs/DOIs are typed URI.
Known project IDs live in `PROJECT_MAPPING` in `submit.py`.

## Module 2 — Programmatic API access (`/fdh-api`)

A self-extending toolkit. When the user asks for an API operation
("find all samples for assay X and delete them"), follow the reuse-or-generate loop:

1. **Check the library first** — read `scripts/fdh/generated/REGISTRY.md`. Reuse a script if one fits.
2. **Consult the index** — `context/fdh_api_index.json`, a list of enriched endpoint entries:
   `path, method, operation_id, summary, category, primary_entities, intent_patterns,
   llm_hint, yaml_lines`. Match on `intent_patterns` / `category` / `llm_hint`.
3. **Pull only the relevant YAML** — `Read` `context/full-fdh-openapi-spec.yaml` at each
   chosen entry's `yaml_lines` `[start, end]`. Never load the whole 640 KB file.
4. **Generate + run** — write a script under `scripts/fdh/generated/` (template below).
5. **Contribute back** — add a `REGISTRY.md` row, show the diff, commit on approval.

Regenerate the index after an API bump: `uv run --script scripts/fdh/build_api_index.py`.

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
  (from submit.py) holds a token in plaintext and is gitignored.
