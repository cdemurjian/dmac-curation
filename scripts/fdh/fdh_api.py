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
