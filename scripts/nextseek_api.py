#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "python-dotenv>=1.0"]
# ///
"""
Reusable NExtSEEK API client for resolving assay titles → assay IDs per project.

NExtSEEK structure: projects → studies → assays. The set of assays in any
given project is project-specific, so the same assay name (e.g. "RNA Extraction")
maps to different `Internal Assay ID` values depending on the project.

Auth: HTTP Basic (spec § securitySchemes.basicAuth at YAML line ~8976). Read
credentials from `.env` at the repo root or directly from env vars:
  NEXTSEEK_USERNAME=...
  NEXTSEEK_PASSWORD=...
Or pass `--username` / `--password` on the CLI (less safe — appears in shell
history). Token auth is also supported via NEXTSEEK_TOKEN / --token if you
later switch.

CLI usage:
  # populate .env then run:
  python scripts/nextseek_api.py fetch-assays --project-id 10
    → writes context/assay_ids_cache.json keyed by assay title

Module usage:
  from scripts.nextseek_api import NExtSEEKClient
  client = NExtSEEKClient(username="...", password="...")
  id_map = client.fetch_assay_id_map(project_id=10)
  # → {"RNA Extraction": 61, "Tissue Collection": 74, ...}
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

REPO = Path(__file__).resolve().parent.parent
# nextseek.mit.edu serves `/nextseek_api/` (line 3462 of the spec self-references
# nextseek-dev.mit.edu as the schema host). fairdata.mit.edu is the SEEK web UI,
# not the API. Override via --base-url if pointing at dev or a different deployment.
DEFAULT_BASE_URL = "https://nextseek.mit.edu"
DEFAULT_CACHE_PATH = REPO / "context" / "assay_ids_cache.json"


class NExtSEEKError(RuntimeError):
    """Wraps a NExtSEEK API failure with status + response body for debugging."""

    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"NExtSEEK {status} on {url}\n{body[:1000]}")
        self.status = status
        self.url = url
        self.body = body


class NExtSEEKClient:
    """Thin client for the read endpoints we need to resolve assay IDs.

    Not a full SDK — just enough to:
      - GET /projects/{id}/ → traverse relationships.assays.data for assay IDs
      - GET /assays/ (paginated) → harvest (id, title) pairs
      - intersect the two to produce {title: id} for project-scoped assays

    Auth: pass (username, password) for HTTP Basic, OR token for Token auth.
    If both are passed, Basic wins.
    """

    def __init__(self, username: Optional[str] = None,
                 password: Optional[str] = None,
                 token: Optional[str] = None,
                 base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0):
        if not (username and password) and not token:
            raise ValueError("provide (username, password) or token")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "yufei-gemm-curation/1.0",
        })
        if username and password:
            self.session.auth = HTTPBasicAuth(username, password)
            self.auth_mode = "basic"
        else:
            self.session.headers["Authorization"] = f"Token {token}"
            self.auth_mode = "token"

    # ── Low-level GET with consistent error surface ─────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}/nextseek_api{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if not resp.ok:
            raise NExtSEEKError(resp.status_code, url, resp.text)
        try:
            return resp.json()
        except ValueError:
            raise NExtSEEKError(resp.status_code, url,
                                f"Non-JSON response: {resp.text[:500]}")

    # ── Endpoint wrappers ───────────────────────────────────────────────────

    def get_project(self, project_id) -> dict:
        """GET /projects/{id}/ — returns the full JSON:API response dict."""
        return self._get(f"/projects/{project_id}/")

    def _prime_csrf(self) -> Optional[str]:
        """GET /login/ to populate the csrftoken cookie, then return its value.

        Django enforces CSRF on POST regardless of auth method. The csrftoken
        cookie is issued only by template-rendering views like /login/ — the
        /nextseek_api/* endpoints don't set it. We GET /login/ (which returns
        200 + Set-Cookie: csrftoken=…), pull the token from the session jar,
        then echo it on the POST as X-CSRFToken. The Referer header is also
        required by Django CSRF over HTTPS.
        """
        try:
            self.session.get(f"{self.base_url}/login/", timeout=self.timeout)
        except requests.RequestException:
            pass  # non-fatal; POST will fail with 403 if cookie missing
        return self.session.cookies.get("csrftoken")

    def validate_batch_upload(self, file_path: Path, project_id,
                              checks: str = "structure") -> dict:
        """POST /batch-upload/validate/ — dry-run validation, no side effects.

        Returns ValidationResult dict with: valid (bool), summary (str),
        totals (dict), errors (list), warnings (dict), checks_run (list),
        checks_skipped (list). See spec line 640.

        checks: comma-separated subset of 'structure,name_check,dag'.
                'structure' is fastest (CONVERT + json_metadata attr check).
                'dag' builds parent/child graph, reports orphans + cycles.
                'name_check' verifies sample Name doesn't already exist in DB.
        """
        # Django CSRF on POST: prime the cookie + echo it in X-CSRFToken header.
        csrf = self._prime_csrf()
        headers = {}
        if csrf:
            headers["X-CSRFToken"] = csrf
            headers["Referer"] = self.base_url  # Django CSRF also checks Referer for HTTPS

        url = f"{self.base_url}/nextseek_api/batch-upload/validate/"
        with open(file_path, "rb") as fh:
            files = {
                "file": (file_path.name, fh,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            }
            data = {
                "project_id": str(project_id),
                "checks": checks,
            }
            resp = self.session.post(url, files=files, data=data,
                                     headers=headers, timeout=self.timeout)
        if not resp.ok:
            raise NExtSEEKError(resp.status_code, url, resp.text)
        try:
            return resp.json()
        except ValueError:
            raise NExtSEEKError(resp.status_code, url,
                                f"Non-JSON response: {resp.text[:500]}")

    def list_assays_paginated(self, page_size: int = 100,
                              verbose: bool = True) -> Iterator[Tuple[str, str]]:
        """GET /assays/ — yields (id, title) tuples across all pages.

        Termination rule: stop when `links.next` is null/missing. The MIT
        NExtSEEK deployment ignores `page[size]` and returns the full result
        set in one response (with next=null), so this typically makes one
        request. We DON'T fall back to `len(records) < page_size` — that
        heuristic causes an infinite loop when the server ignores pagination.
        """
        page = 1
        while True:
            t0 = time.monotonic()
            body = self._get("/assays/", params={
                "page[number]": page,
                "page[size]": page_size,
            })
            envelope = body[0] if isinstance(body, list) and body else body
            records = envelope.get("data") or []
            elapsed = time.monotonic() - t0
            if verbose:
                print(f"    GET /assays/ page {page}: {len(records)} records "
                      f"in {elapsed:.2f}s", file=sys.stderr)

            for rec in records:
                aid = str(rec.get("id"))
                title = (rec.get("attributes") or {}).get("title", "")
                if aid and title:
                    yield aid, title

            # Trust the server's pagination link as the sole termination signal.
            next_link = (envelope.get("links") or {}).get("next")
            if not next_link:
                break
            page += 1
            time.sleep(0.05)

    # ── High-level: title → id map scoped to one project ────────────────────

    def fetch_assay_id_map(self, project_id, verbose: bool = True) -> Dict[str, int]:
        """Return {assay_title: assay_id} for assays linked to a project.

        Strategy:
          1. GET project → harvest its relationships.assays.data IDs
          2. GET /assays/ (paginated) → harvest all visible (id, title) pairs
          3. Intersect — keep only assays present in the project
          4. If a title appears multiple times, keep the lowest ID (oldest)
             and record duplicates in the cache's `_duplicates` block.
        """
        if verbose:
            print(f"  → GET /projects/{project_id}/ …", file=sys.stderr)
        t0 = time.monotonic()
        project = self.get_project(project_id)
        if verbose:
            print(f"    done in {time.monotonic()-t0:.2f}s", file=sys.stderr)
        rels = (project.get("data", {}).get("relationships", {})
                .get("assays", {}).get("data") or [])
        project_assay_ids = {str(item.get("id")) for item in rels if item.get("id")}
        if verbose:
            print(f"  → project has {len(project_assay_ids)} assay relationships",
                  file=sys.stderr)

        if not project_assay_ids:
            return {}

        if verbose:
            print(f"  → GET /assays/ (paginated) …", file=sys.stderr)
        # Collect all id→title from /assays/, then keep project-scoped ones
        by_title: Dict[str, list] = {}
        for aid, title in self.list_assays_paginated(verbose=verbose):
            if aid in project_assay_ids:
                by_title.setdefault(title, []).append(int(aid))

        result: Dict[str, int] = {}
        duplicates: Dict[str, list] = {}
        for title, ids in by_title.items():
            ids_sorted = sorted(ids)
            result[title] = ids_sorted[0]
            if len(ids_sorted) > 1:
                duplicates[title] = ids_sorted

        # Attach a metadata block for inspection if duplicates exist.
        # (Stripped before caller use — caller gets a clean title→id map.)
        if duplicates:
            result["__duplicates__"] = duplicates  # type: ignore[assignment]
        return result


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _load_dotenv():
    """Load REPO/.env into os.environ (stdlib only — no python-dotenv dep).

    Skips lines that are blank or start with '#'. Strips surrounding quotes.
    Existing env vars take precedence (we only setdefault).
    """
    env_path = REPO / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def cmd_fetch_assays(args: argparse.Namespace) -> int:
    _load_dotenv()

    username = args.username or os.environ.get("NEXTSEEK_USERNAME")
    password = args.password or os.environ.get("NEXTSEEK_PASSWORD")
    token = args.token or os.environ.get("NEXTSEEK_TOKEN")

    if not (username and password) and not token:
        print("error: provide credentials via one of:\n"
              "  --username + --password\n"
              "  NEXTSEEK_USERNAME + NEXTSEEK_PASSWORD env vars (or in .env)\n"
              "  --token / NEXTSEEK_TOKEN",
              file=sys.stderr)
        return 2

    client = NExtSEEKClient(username=username, password=password, token=token,
                            base_url=args.base_url)
    print(f"Fetching assays for project {args.project_id} from {args.base_url} "
          f"(auth: {client.auth_mode})…", file=sys.stderr)
    try:
        id_map = client.fetch_assay_id_map(args.project_id)
    except NExtSEEKError as e:
        print(f"\nAPI error: HTTP {e.status} on {e.url}\n{e.body[:1000]}",
              file=sys.stderr)
        return 1

    duplicates = id_map.pop("__duplicates__", None)

    out_path = Path(args.output) if args.output else DEFAULT_CACHE_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_id": args.project_id,
        "base_url": args.base_url,
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assay_id_by_title": id_map,
    }
    if duplicates:
        payload["duplicate_titles"] = duplicates

    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"  ✓ wrote {len(id_map)} assays to {out_path}", file=sys.stderr)
    if duplicates:
        print(f"  ⚠ {len(duplicates)} titles have multiple IDs in this project "
              f"(see duplicate_titles in the cache file)", file=sys.stderr)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Dry-run validate one or more xlsx files against NExtSEEK without inserting."""
    _load_dotenv()

    username = args.username or os.environ.get("NEXTSEEK_USERNAME")
    password = args.password or os.environ.get("NEXTSEEK_PASSWORD")
    token = args.token or os.environ.get("NEXTSEEK_TOKEN")

    if not (username and password) and not token:
        print("error: provide credentials via --username/--password, .env, "
              "or --token / NEXTSEEK_TOKEN", file=sys.stderr)
        return 2

    client = NExtSEEKClient(username=username, password=password, token=token,
                            base_url=args.base_url, timeout=120.0)

    files = [Path(p) for p in args.files]
    for fp in files:
        if not fp.is_file():
            print(f"error: file not found: {fp}", file=sys.stderr)
            return 2

    print(f"Validating {len(files)} file(s) against {args.base_url} "
          f"(project {args.project_id}, checks={args.checks}, "
          f"auth={client.auth_mode})\n", file=sys.stderr)

    overall_valid = True
    for fp in files:
        print(f"━━ {fp.name} ━━")
        try:
            result = client.validate_batch_upload(
                fp, project_id=args.project_id, checks=args.checks)
        except NExtSEEKError as e:
            print(f"  ✗ API error: HTTP {e.status}\n    {e.body[:500]}")
            overall_valid = False
            continue

        valid = result.get("valid", False)
        summary = result.get("summary", "")
        totals = result.get("totals") or {}
        errors = result.get("errors") or []
        warnings = result.get("warnings") or {}
        checks_run = result.get("checks_run") or []
        checks_skipped = result.get("checks_skipped") or []

        flag = "✓ VALID" if valid else "✗ INVALID"
        print(f"  {flag}  — {summary}")
        if totals:
            print(f"  totals: processed={totals.get('processed', '?')}, "
                  f"success={totals.get('success', '?')}, "
                  f"failed={totals.get('failed', '?')}, "
                  f"skipped={totals.get('skipped', '?')}")
        if checks_run:
            print(f"  checks_run: {', '.join(checks_run)}")
        if checks_skipped:
            print(f"  checks_skipped: {', '.join(checks_skipped)}")
        if errors:
            print(f"  ERRORS ({len(errors)}):")
            for e in errors[:20]:
                etype = e.get("type", "?")
                emsg = e.get("message", "?")
                print(f"    [{etype}] {emsg}")
            if len(errors) > 20:
                print(f"    ... and {len(errors) - 20} more")
        if warnings:
            n = len(warnings) if isinstance(warnings, dict) else 0
            print(f"  warnings: {n} group(s)")
            for k, v in list(warnings.items())[:10]:
                vs = v if isinstance(v, str) else json.dumps(v)[:200]
                print(f"    {k}: {vs}")

        # Optional: dump full result to JSON for inspection
        if args.dump_dir:
            dump_path = Path(args.dump_dir) / f"{fp.stem}.validate.json"
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text(json.dumps(result, indent=2, sort_keys=True))
            print(f"  → full response: {dump_path}")

        if not valid:
            overall_valid = False
        print()

    print(f"{'━'*60}")
    print(f"{'ALL FILES VALID ✓' if overall_valid else 'SOME FILES INVALID ✗'}")
    return 0 if overall_valid else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="NExtSEEK API helper for resolving assay titles → IDs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ── fetch-assays ────────────────────────────────────────────────────────
    fa = sub.add_parser(
        "fetch-assays",
        help="Fetch project-scoped assay title→id map and cache it locally.")
    fa.add_argument("--project-id", required=True,
                    help="SEEK project ID (numeric) or NExtSEEK UID (string).")
    fa.add_argument("--username", default=None,
                    help="Basic auth username. If omitted, reads $NEXTSEEK_USERNAME "
                         "(also auto-loaded from REPO/.env).")
    fa.add_argument("--password", default=None,
                    help="Basic auth password. If omitted, reads $NEXTSEEK_PASSWORD. "
                         "CLI use is discouraged (shell history); prefer .env.")
    fa.add_argument("--token", default=None,
                    help="API token (alternative to basic auth). "
                         "If omitted, reads $NEXTSEEK_TOKEN.")
    fa.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help=f"NExtSEEK API base URL (default: {DEFAULT_BASE_URL}).")
    fa.add_argument("--output", default=None,
                    help=f"Output JSON cache (default: {DEFAULT_CACHE_PATH}).")
    fa.set_defaults(func=cmd_fetch_assays)

    # ── validate ────────────────────────────────────────────────────────────
    va = sub.add_parser(
        "validate",
        help="Dry-run validate xlsx files against NExtSEEK (no INSERT, no side effects).")
    va.add_argument("--project-id", required=True,
                    help="SEEK project ID — required even for dry-run.")
    va.add_argument("files", nargs="+",
                    help="One or more .xlsx files to validate.")
    va.add_argument("--checks", default="structure",
                    help="Comma-separated subset of: structure, name_check, dag. "
                         "Default: structure (fastest). Use 'structure,dag,name_check' "
                         "for the most thorough check.")
    va.add_argument("--dump-dir", default=None,
                    help="If set, write each file's full ValidationResult JSON here.")
    va.add_argument("--username", default=None)
    va.add_argument("--password", default=None)
    va.add_argument("--token", default=None)
    va.add_argument("--base-url", default=DEFAULT_BASE_URL)
    va.set_defaults(func=cmd_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
