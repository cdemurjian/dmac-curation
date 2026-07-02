# FairDomHub Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two independent, standalone FairDomHub modules to the `dmac-curation` plugin — an interactive study-upload tool (`submit.py`, ported ~as-is) and a self-extending programmatic API-access toolkit (client + auto-generated enriched index + generated-script library).

**Architecture:** Neither module is wired into the 13-phase NExtSEEK pipeline. Module 1 is a human-run interactive tool launched via `/fdh-upload`. Module 2 is a reuse-or-generate loop: Claude checks a registry, else consults a lightweight JSON index (auto-derived from the vendored 640 KB OpenAPI spec, with `yaml_lines` back-pointers), pulls only the relevant spec slice, then writes/runs a thin script built on a shared `FairDomHubClient`, and contributes it back on review.

**Tech Stack:** Python 3.11+, PEP 723 inline-deps run via `uv run --script`, `requests`, `PyYAML`, existing conventions from `scripts/nextseek_api.py`. Tests are `subprocess`-based smoke/shape tests run via `uvx pytest`.

## Global Constraints

- **Runner:** every script is PEP 723 with an inline `# /// script` deps block; invoked via `uv run --script <path>`. Never bare `python3`. (SKILL.md rule 6.)
- **Tests run with:** `uvx pytest tests/<file>.py -v` (there is no root `pyproject.toml`; bare `pytest` and `uv run pytest` are NOT available).
- **Base URL:** default `https://fairdomhub.org`; overridable via `--base-url` or `.env` `FDH_BASE_URL`.
- **Secrets:** credentials only from `.env` (`FDH_API` = JSON `{username: token}`, optional `FDH_BASE_URL`/`FDH_TOKEN`). Never log tokens. `.env` is already gitignored. **Never `git add working/`** — it holds a real secret `.env`.
- **Destructive ops:** any generated write/delete script defaults to `--dry-run` (prints a preview) and requires explicit `--write` + confirmation.
- **Plugin path in commands/docs:** refer to the plugin root as `<PLUGIN>` (matches existing command files).
- **Repo anchoring in scripts:** `REPO = Path(__file__).resolve().parents[N]` — for `scripts/fdh/X.py`, `parents[2]` is the plugin root.
- **Commit style:** end messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Work happens on branch `fdh-integration` (already created).

---

## File Structure

**Created:**
- `context/full-fdh-openapi-spec.yaml` — vendored full SEEK JSON:API spec (moved from `working/`).
- `context/fdh_api_index.json` — auto-generated lightweight enriched index.
- `scripts/fdh/__init__.py` — package marker (empty).
- `scripts/fdh/build_api_index.py` — index generator (spec → index).
- `scripts/fdh/fdh_api.py` — `FairDomHubClient` + read-only CLI.
- `scripts/fdh/submit.py` — Module 1 interactive tool (moved from `working/`).
- `scripts/fdh/generated/__init__.py` — package marker (empty).
- `scripts/fdh/generated/REGISTRY.md` — registry of Claude-authored task scripts.
- `commands/fdh-upload.md` — Module 1 launcher/prereq-checker.
- `commands/fdh-api.md` — Module 2 reuse-or-generate entry point.
- `skills/curation/FDH.md` — load-on-demand reference for both modules.
- `tests/test_build_api_index.py`, `tests/test_fdh_api_cli.py`, `tests/test_fdh_upload_help.py`, `tests/test_fdh_commands_present.py`.

**Modified:**
- `.gitignore` — add `working/`.
- `skills/curation/SKILL.md` — short FDH pointer + vocabulary.
- `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json` — docs + version bump to 0.2.0.

---

## Task 1: Vendor the spec + scaffold `scripts/fdh/` + protect `working/`

**Files:**
- Create: `context/full-fdh-openapi-spec.yaml` (moved), `scripts/fdh/__init__.py`, `scripts/fdh/generated/__init__.py`
- Modify: `.gitignore`
- Test: `tests/test_fdh_scaffold.py`

**Interfaces:**
- Produces: the vendored spec at `context/full-fdh-openapi-spec.yaml` (Task 2 reads it); the `scripts/fdh/` package dir (all later tasks write into it).

- [ ] **Step 1: Add `working/` to `.gitignore`**

Append to `.gitignore` (under the "Logs / scratch" section):

```gitignore

# ============================================================
# FDH staging scratch (holds a real .env — never commit)
# ============================================================
working/
```

- [ ] **Step 2: Relocate the spec and scaffold the package (plain `mv`, files are untracked)**

Run:
```bash
mkdir -p scripts/fdh/generated
mv working/full-fdh-openapi-spec.yaml context/full-fdh-openapi-spec.yaml
: > scripts/fdh/__init__.py
: > scripts/fdh/generated/__init__.py
```
Expected: `context/full-fdh-openapi-spec.yaml` exists; `working/full-fdh-openapi-spec.yaml` gone.

- [ ] **Step 3: Write the scaffold test**

Create `tests/test_fdh_scaffold.py`:
```python
"""Structural checks: the FDH spec is vendored and the package dir exists."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_spec_vendored():
    spec = REPO / "context" / "full-fdh-openapi-spec.yaml"
    assert spec.exists(), "spec must be moved into context/"
    head = spec.read_text().splitlines()[0]
    assert head.startswith("openapi:"), f"unexpected first line: {head!r}"


def test_spec_not_left_in_working():
    assert not (REPO / "working" / "full-fdh-openapi-spec.yaml").exists()


def test_package_scaffold_present():
    assert (REPO / "scripts" / "fdh" / "__init__.py").exists()
    assert (REPO / "scripts" / "fdh" / "generated" / "__init__.py").exists()
```

- [ ] **Step 4: Run the test**

Run: `uvx pytest tests/test_fdh_scaffold.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add .gitignore context/full-fdh-openapi-spec.yaml scripts/fdh/__init__.py scripts/fdh/generated/__init__.py tests/test_fdh_scaffold.py
git commit -m "$(printf 'feat(fdh): vendor SEEK OpenAPI spec + scaffold scripts/fdh\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```
Note: do NOT `git add working/` — it holds a gitignored secret `.env`.

---

## Task 2: `build_api_index.py` — the enriched API index generator

**Files:**
- Create: `scripts/fdh/build_api_index.py`, `context/fdh_api_index.json` (generated output)
- Test: `tests/test_build_api_index.py`

**Interfaces:**
- Consumes: `context/full-fdh-openapi-spec.yaml` (Task 1).
- Produces: `context/fdh_api_index.json` — a JSON list; each entry has keys
  `path, method, operation_id, summary, category, primary_entities, intent_patterns, llm_hint, yaml_lines`.
  `yaml_lines` is `[start, end]` (1-indexed, inclusive) into the vendored spec. Module 2 (`/fdh-api`, FDH.md) reads this file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_api_index.py`:
```python
"""Tests for the FDH API index generator (deterministic, no network)."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fdh" / "build_api_index.py"
SPEC = REPO / "context" / "full-fdh-openapi-spec.yaml"
INDEX = REPO / "context" / "fdh_api_index.json"

REQUIRED_KEYS = {
    "path", "method", "operation_id", "summary", "category",
    "primary_entities", "intent_patterns", "llm_hint", "yaml_lines",
}


def test_generator_runs_and_writes_index():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT)],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert INDEX.exists()


def test_index_shape_and_known_ops():
    data = json.loads(INDEX.read_text())
    assert isinstance(data, list) and len(data) >= 100
    keyset = {(e["path"], e["method"]) for e in data}
    for e in data:
        assert REQUIRED_KEYS <= set(e), f"missing keys in {e.get('path')}"
        start, end = e["yaml_lines"]
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 < start <= end
    # GET /samples/{id} (operationId readSample) is definitely present:
    assert ("/samples/{id}", "GET") in keyset
    read = next(e for e in data if e["path"] == "/samples/{id}" and e["method"] == "GET")
    assert read["category"] == "samples_read"
    assert "samples" in read["primary_entities"]
    # every DELETE op is flagged destructive:
    deletes = [e for e in data if e["method"] == "DELETE"]
    assert deletes, "spec has DELETE operations"
    for e in deletes:
        assert e["category"].endswith("_delete")
        assert "DESTRUCTIVE" in e["llm_hint"]


def test_yaml_lines_point_at_the_operation():
    data = json.loads(INDEX.read_text())
    spec_lines = SPEC.read_text().splitlines()
    e = next(x for x in data if x["path"] == "/samples/{id}" and x["method"] == "GET")
    start, end = e["yaml_lines"]
    assert 1 <= start <= end <= len(spec_lines)
    slice_text = "\n".join(spec_lines[start - 1:end])
    assert "operationId: readSample" in slice_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uvx pytest tests/test_build_api_index.py -v`
Expected: FAIL (script does not exist → `test_generator_runs_and_writes_index` errors/nonzero).

- [ ] **Step 3: Write the generator**

Create `scripts/fdh/build_api_index.py`:
```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Generate context/fdh_api_index.json from context/full-fdh-openapi-spec.yaml.

A lightweight, enriched map of every FDH/SEEK API operation. Mirrors the shape of
context/min_api_endpoints_enriched.json but adds a `yaml_lines` back-pointer so Claude
can Read the exact slice of the 640KB spec for schema detail instead of the whole file.

Re-run whenever the vendored spec changes:
    uv run --script scripts/fdh/build_api_index.py
"""
import bisect
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "context" / "full-fdh-openapi-spec.yaml"
OUT = REPO / "context" / "fdh_api_index.json"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")

# path header at 2-space indent, optional quotes:  "/samples/{id}":  or  /search:
_PATH_RE = re.compile(r'^  "?(/[^"\s:]*)"?:\s*$')
# method header at 4-space indent:  get:  post:  put:  patch:  delete:
_METHOD_RE = re.compile(r'^    (get|post|put|patch|delete):\s*$')


def scan(lines):
    """Return (markers, boundaries).

    markers: ordered [(path, method, start_line)] for each operation.
    boundaries: sorted line numbers of every path-header AND method-header line,
                used to bound each operation's range.
    """
    markers, boundaries, cur_path = [], [], None
    for i, line in enumerate(lines, start=1):
        pm = _PATH_RE.match(line)
        if pm:
            cur_path = pm.group(1)
            boundaries.append(i)
            continue
        mm = _METHOD_RE.match(line)
        if mm and cur_path is not None:
            markers.append((cur_path, mm.group(1), i))
            boundaries.append(i)
    return markers, sorted(boundaries)


def compute_ranges(markers, boundaries, total):
    """end = (next boundary after start) - 1, or EOF for the last operation."""
    ranges = {}
    for path, method, start in markers:
        j = bisect.bisect_right(boundaries, start)
        end = (boundaries[j] - 1) if j < len(boundaries) else total
        ranges[(path, method)] = [start, end]
    return ranges


def entity_of(path):
    """First non-placeholder path segment (e.g. /studies/{id}/assays -> studies)."""
    for seg in path.strip("/").split("/"):
        if seg and not seg.startswith("{"):
            return seg
    return "resource"


def categorize(path, method):
    if path == "/search":
        return "search"
    if "content_blobs" in path:
        return "file_download" if path.endswith("/download") else "file_read"
    entity = entity_of(path)
    is_item = path.rstrip("/").endswith("}")
    if method == "get":
        return f"{entity}_read" if is_item else f"{entity}_list"
    if method == "post":
        return f"{entity}_create"
    if method in ("patch", "put"):
        return f"{entity}_update"
    if method == "delete":
        return f"{entity}_delete"
    return f"{entity}_{method}"


_INTENTS = {
    "get_list": ["list", "all", "show", "browse"],
    "get_item": ["get", "fetch", "read", "view", "inspect"],
    "post": ["create", "add", "new", "upload"],
    "patch": ["update", "edit", "modify", "patch"],
    "put": ["update", "replace"],
    "delete": ["delete", "remove", "destroy"],
}


def intent_patterns(path, method):
    is_item = path.rstrip("/").endswith("}")
    key = "get_item" if (method == "get" and is_item) else ("get_list" if method == "get" else method)
    return list(_INTENTS.get(key, [])) + [entity_of(path)]


def llm_hint(path, method, summary):
    is_item = path.rstrip("/").endswith("}")
    bits = []
    if method == "delete":
        bits.append("DESTRUCTIVE — irreversible on the live repo; dry-run and confirm before writing.")
    if method in ("patch", "put", "delete") or (method == "get" and is_item):
        bits.append("Requires the numeric resource id.")
    if "content_blobs" in path:
        bits.append("Two-step: resolve the blob link from the parent resource first.")
    if summary:
        bits.append(f"Summary: {summary}.")
    return " ".join(bits).strip()


def main():
    if not SPEC.exists():
        print(f"error: spec not found: {SPEC}", file=sys.stderr)
        return 1
    text = SPEC.read_text()
    lines = text.splitlines()
    spec = yaml.safe_load(text)
    paths = spec.get("paths") or {}

    markers, boundaries = scan(lines)
    ranges = compute_ranges(markers, boundaries, len(lines))

    entries = []
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method not in HTTP_METHODS or not isinstance(op, dict):
                continue
            summary = (op.get("summary") or "").strip()
            op_id = op.get("operationId") or ""
            entries.append({
                "path": path,
                "method": method.upper(),
                "operation_id": op_id,
                "summary": summary or op_id or f"{method.upper()} {path}",
                "category": categorize(path, method),
                "primary_entities": [entity_of(path)],
                "intent_patterns": intent_patterns(path, method),
                "llm_hint": llm_hint(path, method, summary),
                "yaml_lines": ranges.get((path, method)),
            })

    missing = [e for e in entries if e["yaml_lines"] is None]
    if missing:
        print(f"warning: {len(missing)} ops had no line range", file=sys.stderr)

    entries.sort(key=lambda e: (e["path"], e["method"]))
    OUT.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"wrote {len(entries)} operations to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the index, then run the tests**

Run:
```bash
uv run --script scripts/fdh/build_api_index.py
uvx pytest tests/test_build_api_index.py -v
```
Expected: generator prints `wrote 106 operations to .../context/fdh_api_index.json` (count may differ slightly if the spec changes; test only requires ≥100), then 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/fdh/build_api_index.py context/fdh_api_index.json tests/test_build_api_index.py
git commit -m "$(printf 'feat(fdh): generate enriched API index with yaml_lines back-pointers\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: `fdh_api.py` — `FairDomHubClient` + read-only CLI

**Files:**
- Create: `scripts/fdh/fdh_api.py`
- Test: `tests/test_fdh_api_cli.py`

**Interfaces:**
- Produces:
  - `class FairDomHubClient(token, base_url="https://fairdomhub.org", timeout=60.0)` — raises `ValueError` if `token` is falsy. Methods: `get(resource_type, rid)`, `search(q, search_type=None)`, `page_through(path_or_url)`, `list_related(resource_type, rid, relationship)`, `whoami()`, `post(resource_type, payload)`, `patch(resource_type, rid, payload)`, `delete(resource_type, rid)`, `download_blob(url, dest)`. Generated scripts (Task 5+ usage, documented in FDH.md) import this.
  - CLI subcommands: `whoami`, `search`, `get`, `list`, `download-blob`, with global `--token/--user/--base-url`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fdh_api_cli.py`:
```python
"""Smoke + unit tests for fdh_api.py (no network, no credentials)."""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fdh" / "fdh_api.py"


def _run(*args):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=90,
    )


def test_help_lists_subcommands():
    r = _run("--help")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    for cmd in ("whoami", "search", "get", "list", "download-blob"):
        assert cmd in out, f"{cmd} missing from --help"


@pytest.mark.parametrize("cmd", ["whoami", "search", "get", "list", "download-blob"])
def test_subcommand_help(cmd):
    r = _run(cmd, "--help")
    assert r.returncode == 0, f"{cmd}: {r.stderr}"


def test_client_requires_token():
    prog = (
        "import sys; sys.path.insert(0, r'{d}')\n"
        "import fdh_api\n"
        "raised = False\n"
        "try:\n"
        "    fdh_api.FairDomHubClient(token=None)\n"
        "except ValueError:\n"
        "    raised = True\n"
        "assert raised, 'expected ValueError for missing token'\n"
        "print('ok')\n"
    ).format(d=str(SCRIPT.parent))
    r = subprocess.run(
        ["uv", "run", "--with", "requests", "python", "-"],
        input=prog, capture_output=True, text=True, timeout=90,
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uvx pytest tests/test_fdh_api_cli.py -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Write the client + CLI**

Create `scripts/fdh/fdh_api.py`:
```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""FairDomHub / FAIRDOM-SEEK JSON:API client + read-only CLI.

Foundation for Module 2 (general FDH API access). Generated task scripts under
scripts/fdh/generated/ import FairDomHubClient from here so they stay thin and share
one auth / retry / pagination implementation.

Auth: token from .env FDH_API (a JSON object {username: token}); select with --user,
or pass --token, or set FDH_TOKEN. Base URL defaults to https://fairdomhub.org and is
overridable via --base-url or FDH_BASE_URL.

Read CLI (bespoke/destructive ops are generated on demand, not baked in here):
    uv run --script scripts/fdh/fdh_api.py whoami
    uv run --script scripts/fdh/fdh_api.py search "lactate" --type data_files
    uv run --script scripts/fdh/fdh_api.py get samples 153
    uv run --script scripts/fdh/fdh_api.py list studies 1421 assays
    uv run --script scripts/fdh/fdh_api.py download-blob <url> --out ./file.bin
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://fairdomhub.org"
RETRY_STATUS = (429, 502, 503)


class FDHError(RuntimeError):
    """Wraps an FDH API failure with status + response body for debugging."""

    def __init__(self, status, url, body):
        super().__init__(f"FDH {status} on {url}\n{body[:1000]}")
        self.status, self.url, self.body = status, url, body


class FairDomHubClient:
    """Thin JSON:API client. Token auth. Retries transient 429/502/503 with backoff."""

    def __init__(self, token: Optional[str] = None,
                 base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0):
        if not token:
            raise ValueError("FairDomHubClient requires an API token")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "dmac-curation-fdh/0.1",
        })

    # ── request core ──────────────────────────────────────────────────────
    def _abs(self, path_or_url: str) -> str:
        if urlparse(path_or_url).scheme:
            return path_or_url
        return f"{self.base_url}/{path_or_url.lstrip('/')}"

    def _request(self, method, path_or_url, *, params=None, json_body=None,
                 max_retries=5, backoff=2.0):
        url = self._abs(path_or_url)
        attempt = 0
        while True:
            try:
                r = self.session.request(method, url, params=params,
                                         json=json_body, timeout=self.timeout)
            except requests.RequestException:
                if attempt < max_retries:
                    time.sleep(backoff ** attempt)
                    attempt += 1
                    continue
                raise
            if r.status_code in RETRY_STATUS and attempt < max_retries:
                time.sleep(backoff ** attempt)
                attempt += 1
                continue
            if r.status_code >= 400:
                raise FDHError(r.status_code, url, r.text)
            return r

    def _json(self, method, path, **kw):
        r = self._request(method, path, **kw)
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            raise FDHError(r.status_code, r.url, f"non-JSON response: {r.text[:500]}")

    # ── read verbs ────────────────────────────────────────────────────────
    def get(self, resource_type, rid):
        return self._json("GET", f"/{resource_type}/{rid}")

    def search(self, q, search_type=None):
        params = {"q": q}
        if search_type:
            params["search_type"] = search_type
        return self._json("GET", "/search", params=params)

    def page_through(self, path_or_url):
        items, url = [], path_or_url
        while url:
            payload = self._json("GET", url)
            items.extend(payload.get("data") or [])
            url = (payload.get("links") or {}).get("next")
        return items

    def list_related(self, resource_type, rid, relationship):
        obj = self.get(resource_type, rid)
        rels = (obj.get("data") or {}).get("relationships") or {}
        rel = rels.get(relationship) or {}
        related = (rel.get("links") or {}).get("related")
        if related:
            return self.page_through(related)
        data = rel.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def whoami(self):
        return self._json("GET", "/people/current")

    def download_blob(self, url, dest):
        r = self._request("GET", url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest

    # ── write verbs (used by generated scripts, never by this read CLI) ────
    def post(self, resource_type, payload):
        return self._json("POST", f"/{resource_type}", json_body=payload)

    def patch(self, resource_type, rid, payload):
        return self._json("PATCH", f"/{resource_type}/{rid}", json_body=payload)

    def delete(self, resource_type, rid):
        self._request("DELETE", f"/{resource_type}/{rid}")
        return True


# ── credential loading (stdlib; mirrors nextseek_api.py) ───────────────────
def _load_dotenv():
    """setdefault env vars from cwd/.env then <plugin>/.env (idempotent)."""
    for candidate in (Path.cwd() / ".env", REPO / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _resolve_token(args):
    if args.token:
        return args.token
    if os.environ.get("FDH_TOKEN"):
        return os.environ["FDH_TOKEN"]
    raw = os.environ.get("FDH_API", "")
    if not raw:
        print("error: no token. Set FDH_API={\"user\": \"token\"} or FDH_TOKEN in .env, "
              "or pass --token.", file=sys.stderr)
        sys.exit(2)
    try:
        users = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: FDH_API is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if args.user:
        if args.user not in users:
            print(f"error: user {args.user!r} not in FDH_API", file=sys.stderr)
            sys.exit(2)
        return users[args.user]
    if len(users) == 1:
        return next(iter(users.values()))
    print(f"error: multiple users in FDH_API {list(users)}; pass --user NAME", file=sys.stderr)
    sys.exit(2)


def make_client(args):
    _load_dotenv()
    base = args.base_url or os.environ.get("FDH_BASE_URL") or DEFAULT_BASE_URL
    return FairDomHubClient(token=_resolve_token(args), base_url=base)


def _emit(obj):
    print(json.dumps(obj, indent=2))


def cmd_whoami(args):
    _emit(make_client(args).whoami())
    return 0


def cmd_search(args):
    _emit(make_client(args).search(args.query, args.type))
    return 0


def cmd_get(args):
    _emit(make_client(args).get(args.resource_type, args.id))
    return 0


def cmd_list(args):
    _emit(make_client(args).list_related(args.resource_type, args.id, args.relationship))
    return 0


def cmd_download_blob(args):
    dest = make_client(args).download_blob(args.url, args.out)
    print(f"wrote {dest}", file=sys.stderr)
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--token", default=None, help="API token (overrides .env).")
    common.add_argument("--user", default=None, help="Which FDH_API user's token to use.")
    common.add_argument("--base-url", default=None,
                        help="Default https://fairdomhub.org; or set FDH_BASE_URL.")

    p = argparse.ArgumentParser(
        prog="fdh_api.py",
        description="FairDomHub JSON:API read client. Bespoke/destructive operations "
                    "are generated on demand under scripts/fdh/generated/.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("whoami", parents=[common],
                       help="Show the authenticated person (GET /people/current).")
    s.set_defaults(func=cmd_whoami)

    s = sub.add_parser("search", parents=[common], help="Search SEEK (GET /search).")
    s.add_argument("query")
    s.add_argument("--type", default=None,
                   help="Restrict to a resource type, e.g. data_files, samples, assays.")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("get", parents=[common], help="Fetch one resource by type + id.")
    s.add_argument("resource_type")
    s.add_argument("id")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("list", parents=[common],
                       help="List related resources via a relationship (paginated).")
    s.add_argument("resource_type")
    s.add_argument("id")
    s.add_argument("relationship")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("download-blob", parents=[common],
                       help="Download a content_blob by URL to disk.")
    s.add_argument("url")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_download_blob)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uvx pytest tests/test_fdh_api_cli.py -v`
Expected: 7 passed (1 help + 5 parametrized subcommand-help + 1 token check).

- [ ] **Step 5: Commit**

```bash
git add scripts/fdh/fdh_api.py tests/test_fdh_api_cli.py
git commit -m "$(printf 'feat(fdh): FairDomHubClient + read-only CLI (search/get/list/whoami/download-blob)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: Port `submit.py` (Module 1)

**Files:**
- Create: `scripts/fdh/submit.py` (moved from `working/fdh-upload-script/submit.py`, verbatim)
- Test: `tests/test_fdh_upload_help.py`

**Interfaces:**
- Produces: `scripts/fdh/submit.py` runnable via `uv run --script`. `/fdh-upload` (Task 5) references this path.

- [ ] **Step 1: Move the tool verbatim (plain `mv` — it is untracked)**

Run:
```bash
mv working/fdh-upload-script/submit.py scripts/fdh/submit.py
```
Do not edit its logic. (Its `Assets/` and `Assets/Output/` paths are cwd-relative by design; it is run from a project directory.)

- [ ] **Step 2: Write the smoke test**

Create `tests/test_fdh_upload_help.py`:
```python
"""Smoke test: submit.py --help runs (interactive tool, ported verbatim)."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fdh" / "submit.py"


def test_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = result.stdout + result.stderr
    assert "--resume" in out and "--step" in out
```

- [ ] **Step 3: Run the test**

Run: `uvx pytest tests/test_fdh_upload_help.py -v`
Expected: 1 passed. (First run installs submit.py's deps — pandas/questionary/rich/rapidfuzz — so allow time.)

- [ ] **Step 4: Commit**

```bash
git add scripts/fdh/submit.py tests/test_fdh_upload_help.py
git commit -m "$(printf 'feat(fdh): port interactive study-upload tool submit.py into plugin\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Slash commands `/fdh-upload` + `/fdh-api`

**Files:**
- Create: `commands/fdh-upload.md`, `commands/fdh-api.md`
- Test: `tests/test_fdh_commands_present.py`

**Interfaces:**
- Consumes: `scripts/fdh/submit.py` (Task 4), `scripts/fdh/fdh_api.py` + `scripts/fdh/build_api_index.py` + `context/fdh_api_index.json` (Tasks 2–3), `scripts/fdh/generated/REGISTRY.md` (Task 6).
- Produces: two command files matching the existing `commands/curate-*.md` shape.

- [ ] **Step 1: Write `commands/fdh-upload.md`**

```markdown
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
- `Assets/Output/session.json` stores the API token in plain text — remind the user it is
  gitignored and must not be committed.
- Known project IDs live in `PROJECT_MAPPING` inside `submit.py`; new projects are added there.
```

- [ ] **Step 2: Write `commands/fdh-api.md`**

```markdown
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
   using the template in FDH.md: it imports `FairDomHubClient` from `../fdh_api.py`,
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
```

- [ ] **Step 3: Write the presence test**

Create `tests/test_fdh_commands_present.py`:
```python
"""The two FDH command files exist, have frontmatter, and reference real paths."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

REFERENCED = [
    "scripts/fdh/submit.py",
    "scripts/fdh/fdh_api.py",
    "scripts/fdh/build_api_index.py",
    "context/fdh_api_index.json",
    "scripts/fdh/generated/REGISTRY.md",
]


def test_command_files_exist_with_frontmatter():
    for name in ("fdh-upload.md", "fdh-api.md"):
        f = COMMANDS / name
        assert f.exists(), f"missing {f}"
        text = f.read_text()
        assert text.startswith("---"), f"{name} missing frontmatter"
        assert "description:" in text.split("---")[1], f"{name} missing description"


def test_referenced_paths_exist():
    # Union of paths referenced across both command files must all resolve.
    blob = (COMMANDS / "fdh-upload.md").read_text() + (COMMANDS / "fdh-api.md").read_text()
    for rel in REFERENCED:
        assert rel in blob, f"expected {rel} to be referenced in the FDH commands"
        assert (REPO / rel).exists(), f"referenced path does not exist: {rel}"
```
Note: this test requires `scripts/fdh/generated/REGISTRY.md` (Task 6). If executing strictly in order, create the empty file first or run this test after Task 6. To keep Task 5 independently green, add a placeholder now:
```bash
printf '# Generated FDH API scripts — registry\n' > scripts/fdh/generated/REGISTRY.md
```
(Task 6 overwrites it with the full scaffold.)

- [ ] **Step 4: Run the test**

Run: `uvx pytest tests/test_fdh_commands_present.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add commands/fdh-upload.md commands/fdh-api.md tests/test_fdh_commands_present.py scripts/fdh/generated/REGISTRY.md
git commit -m "$(printf 'feat(fdh): add /fdh-upload and /fdh-api slash commands\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: `FDH.md` reference + `REGISTRY.md` scaffold + `SKILL.md` pointer

**Files:**
- Create: `skills/curation/FDH.md`
- Modify: `scripts/fdh/generated/REGISTRY.md` (full scaffold), `skills/curation/SKILL.md`
- Test: `tests/test_fdh_reference_docs.py`

**Interfaces:**
- Produces: the load-on-demand reference that `/fdh-api` and `/fdh-upload` point to; the registry Claude reads first in the reuse loop; the SKILL.md routing hooks.

- [ ] **Step 1: Write `skills/curation/FDH.md`**

```markdown
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
```

- [ ] **Step 2: Write the full `scripts/fdh/generated/REGISTRY.md` scaffold**

```markdown
# Generated FDH API scripts — registry

Claude reads this FIRST when asked to do an FDH API task (see `/fdh-api` and
`skills/curation/FDH.md`). If a script here already covers the task, run it instead of
generating a new one. Each script lives beside this file and imports `FairDomHubClient`
from `../fdh_api.py`. Writes default to `--dry-run`; `--write` is required to mutate.

| Script | Purpose | Endpoints used | Writes? | Added |
|---|---|---|---|---|
| _(none yet)_ | | | | |
```

- [ ] **Step 3: Add the FDH pointer to `SKILL.md`**

In `skills/curation/SKILL.md`, insert this section immediately AFTER the "The 13-phase pipeline" table (before "## Hard rules"):

```markdown
## FairDomHub direct API (standalone — NOT part of the 13-phase pipeline)

Two FDH capabilities independent of NExtSEEK curation:
- **Upload a study** → `/fdh-upload` drives the interactive `scripts/fdh/submit.py`.
- **Programmatic API access** ("find / delete / patch … on FDH") → `/fdh-api` runs a
  reuse-or-generate loop over `scripts/fdh/fdh_api.py` + `context/fdh_api_index.json`.

Deep reference: `skills/curation/FDH.md` (load on demand). Auth: `.env` `FDH_API`.
```

Also add to the "## Vocabulary the user uses" list these two bullets:

```markdown
- "upload to FairDomHub" / "FDH upload" → `/fdh-upload` (interactive `submit.py`)
- "access the FDH API" / "find/delete/patch … on FDH" → `/fdh-api` reuse-or-generate loop
```

- [ ] **Step 4: Write the reference-docs test**

Create `tests/test_fdh_reference_docs.py`:
```python
"""FDH.md, REGISTRY.md scaffold, and the SKILL.md pointer are present and wired."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_fdh_reference_exists():
    f = REPO / "skills" / "curation" / "FDH.md"
    assert f.exists()
    text = f.read_text()
    for anchor in ("Module 1", "Module 2", "reuse-or-generate", "fdh_api_index.json",
                   "yaml_lines", "dry-run"):
        assert anchor in text, f"FDH.md missing: {anchor}"


def test_registry_scaffold():
    f = REPO / "scripts" / "fdh" / "generated" / "REGISTRY.md"
    assert f.exists()
    text = f.read_text()
    assert "| Script | Purpose |" in text


def test_skill_points_to_fdh():
    text = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert "FDH.md" in text
    assert "/fdh-upload" in text and "/fdh-api" in text
```

- [ ] **Step 5: Run the test**

Run: `uvx pytest tests/test_fdh_reference_docs.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/curation/FDH.md skills/curation/SKILL.md scripts/fdh/generated/REGISTRY.md tests/test_fdh_reference_docs.py
git commit -m "$(printf 'docs(fdh): FDH.md reference, registry scaffold, SKILL.md routing\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: Top-level docs, version bump, and full-suite verification

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: everything above. No new interfaces.

- [ ] **Step 1: Bump plugin version to 0.2.0**

In `.claude-plugin/plugin.json`, change `"version": "0.1.0"` to `"version": "0.2.0"`.

- [ ] **Step 2: Add a README section**

In `README.md`, after the "What it does" / pipeline list section, add:

```markdown
## FairDomHub (standalone, not part of the 13-phase pipeline)

Two independent FDH capabilities ship alongside the pipeline:

- **`/fdh-upload`** — launches the interactive study-upload tool
  (`scripts/fdh/submit.py`): assays, protocols/SOPs, sample types, samples, publish.
- **`/fdh-api`** — programmatic API access. Claude reuses an existing generated script
  or, guided by `context/fdh_api_index.json` (auto-derived from the vendored SEEK
  OpenAPI spec), writes a new one built on `scripts/fdh/fdh_api.py` — dry-run first for
  any write. New scripts accrue in `scripts/fdh/generated/` (review-then-commit).

Auth for both: per-project `.env` `FDH_API={"name": "token"}`.
```

- [ ] **Step 3: Add a CHANGELOG entry**

Prepend a new entry at the top of `CHANGELOG.md`'s entries:

```markdown
## 0.2.0

Added FairDomHub integration as two standalone modules:
- `/fdh-upload` — ported the interactive `submit.py` study-upload tool into `scripts/fdh/`.
- `/fdh-api` — self-extending API-access toolkit: `FairDomHubClient` (`scripts/fdh/fdh_api.py`),
  an auto-generated enriched endpoint index (`context/fdh_api_index.json` via
  `build_api_index.py`) with `yaml_lines` pointers into the vendored full OpenAPI spec, and a
  review-then-commit generated-script registry.
- New `skills/curation/FDH.md` reference; SKILL.md routing hooks.
```

- [ ] **Step 4: Run the ENTIRE test suite**

Run: `uvx pytest tests/ -v`
Expected: all tests pass — the pre-existing suite (`test_common.py`, `test_nextseek_api_cli.py`, `test_deposit_scripts_help.py`, `test_flat_pipeline_cli.py`, `test_file_ops_cli.py`, `test_inspect_workbook.py`, `test_smb_pull_cli.py`, `test_templates_render.py`) plus the 6 new FDH test files, all green.

- [ ] **Step 5: Secret-safety sweep before committing**

Run:
```bash
git status --porcelain | grep -i working || echo "OK: nothing under working/ is staged"
git diff --cached --name-only | grep -E '\.env$' && echo "DANGER: .env staged" || echo "OK: no .env staged"
```
Expected: "OK" on both lines.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md .claude-plugin/plugin.json
git commit -m "$(printf 'docs(fdh): README + CHANGELOG + bump to v0.2.0\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- §4 Module 1 (port submit.py, `/fdh-upload`) → Tasks 4, 5. ✓
- §5 Module 2 client → Task 3; index + generator → Task 2; reuse loop + template + registry → Tasks 5, 6. ✓
- §3 layout (context/ spec+index, scripts/fdh/*, commands, FDH.md, tests) → Tasks 1–7. ✓
- §6 Safety (dry-run, review-then-commit, secret handling) → Task 6 (FDH.md rules + template), Task 7 Step 5 (sweep), Task 1 (`working/` gitignore). ✓
- §7 SKILL.md pointer + FDH.md → Task 6. ✓
- §8 Deliverables incl. README/CHANGELOG/working cleanup → Tasks 1, 7. ✓
- §2 base-URL parameterization → Task 3 (`--base-url`/`FDH_BASE_URL`). ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — every code and doc step contains full content. ✓

**Type consistency:** `FairDomHubClient` method names (`get/search/page_through/list_related/whoami/post/patch/delete/download_blob`) and `make_client` are defined in Task 3 and used identically in the FDH.md template (Task 6) and the CLI. The index entry keys (`path/method/operation_id/summary/category/primary_entities/intent_patterns/llm_hint/yaml_lines`) are produced in Task 2 and asserted with the same names in `test_build_api_index.py` and described identically in FDH.md. ✓

**Known risk flagged for the executor:** Task 2's tests assume `GET /samples/{id}` (operationId `readSample`) and at least one `DELETE` operation exist in the vendored spec — both confirmed present during planning. If a future spec revision removes them, adjust the concrete assertions (the shape assertions are spec-independent).
