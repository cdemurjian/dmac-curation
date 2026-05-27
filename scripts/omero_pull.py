#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# TODO(v0.2): extract REST client into deposit/omero_rest_client.py for reuse
"""
Pull OMERO image IDs via the REST API and reconcile against the local manifest.

Usage examples
--------------
# 1) Pull all images under a project (recursively across its datasets)
python3 scripts/omero_pull.py images \\
    --project 1252 \\
    --sessionid "<sessionid cookie>" \\
    --out omero_images.csv

# 2) Pull from one or more specific datasets
python3 scripts/omero_pull.py images \\
    --dataset 4711 --dataset 4712 \\
    --sessionid "$OMERO_SESSIONID" \\
    --out omero_images.csv

# 3) Diff manifest vs pulled images (find failed uploads)
python3 scripts/omero_pull.py diff \\
    --manifest manifest.csv --images omero_images.csv

# 4) One-shot: pull + diff + emit per-figure CSVs ready for D.IMG
python3 scripts/omero_pull.py all \\
    --project 1252 --sessionid "<cookie>" \\
    --manifest manifest.csv --out omero_images.csv

Authentication
--------------
OMERO.web requires a logged-in session cookie. Get it from your browser
DevTools after logging into omero.mit.edu:
    Application → Storage → Cookies → omero.mit.edu → sessionid

Pass via --sessionid, or stash in env var OMERO_SESSIONID.
Optional --csrftoken (only needed for state-changing requests; not GETs).

Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterator

DEFAULT_BASE = "https://omero.mit.edu"
DEFAULT_PAGE = 500  # OMERO.web typically caps at 500
USER_AGENT = "intravchip-curation/1.0 (omero-pull)"

CSV_COLS = [
    "filename",        # OMERO Image.Name (== our renamed filename)
    "image_id",        # OMERO Image.@id
    "dataset_id",
    "dataset_name",
    "project_id",
    "project_name",
    "fileset_id",
    "web_url",         # https://omero.mit.edu/webclient/img_detail/<image_id>/?dataset=<dataset_id>
    "show_url",        # https://omero.mit.edu/webclient/?show=image-<image_id>
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class OmeroClient:
    def __init__(self, base: str, sessionid: str | None = None,
                 csrftoken: str | None = None):
        self.base = base.rstrip("/")
        # Use a CookieJar so login flow can stash sessionid/csrftoken automatically
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        if sessionid:
            self._set_cookie("sessionid", sessionid)
        if csrftoken:
            self._set_cookie("csrftoken", csrftoken)

    def _set_cookie(self, name: str, value: str) -> None:
        host = urllib.parse.urlparse(self.base).hostname or ""
        c = http.cookiejar.Cookie(
            version=0, name=name, value=value,
            port=None, port_specified=False,
            domain=host, domain_specified=True, domain_initial_dot=False,
            path="/", path_specified=True,
            secure=False, expires=None, discard=True,
            comment=None, comment_url=None, rest={}, rfc2109=False,
        )
        self.jar.set_cookie(c)

    def _csrf(self) -> str | None:
        for c in self.jar:
            if c.name == "csrftoken":
                return c.value
        return None

    def _request(self, path: str, params: dict | None = None,
                 method: str = "GET", data: dict | None = None) -> dict:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": self.base + "/webclient/",
        }
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if method != "GET":
            tok = self._csrf()
            if tok:
                headers["X-CSRFToken"] = tok
        req = urllib.request.Request(url, headers=headers, data=body, method=method)
        try:
            with self.opener.open(req, timeout=60) as r:
                txt = r.read().decode("utf-8")
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            sys.exit(f"HTTP {e.code} on {url}\n  body: {body}\n"
                     f"  (auth issue? try fresh login)")
        except urllib.error.URLError as e:
            sys.exit(f"URLError on {url}: {e.reason}\n"
                     f"  (on MIT VPN? omero.mit.edu is internal)")

    # ------ programmatic login flow ------

    def login(self, username: str, password: str, server_id: int | None = None) -> None:
        """Log in via /api/v0/login/. Populates sessionid + csrftoken cookies."""
        # Step 1: discover API base + server list
        api = self._request("/api/v0/")
        # Step 2: pick server id (default = the only one if not specified)
        if server_id is None:
            servers = self._request("/api/v0/servers/").get("data", [])
            if not servers:
                sys.exit("/api/v0/servers/ returned no servers")
            if len(servers) > 1 and server_id is None:
                ids = [(s.get("id"), s.get("host"), s.get("port")) for s in servers]
                sys.exit(f"multiple servers — pass --server-id one of: {ids}")
            server_id = servers[0]["id"]
        # Step 3: pull CSRF token (sets csrftoken cookie)
        self._request("/api/v0/token/")
        if not self._csrf():
            sys.exit("did not receive csrftoken after /api/v0/token/")
        # Step 4: login
        login_url = api.get("data", {}).get("url:login", "/api/v0/login/")
        # urllib's RequestProcessor strips leading host if present
        login_path = urllib.parse.urlparse(login_url).path if login_url.startswith("http") else login_url
        resp = self._request(
            login_path, method="POST",
            data={"username": username, "password": password, "server": server_id},
        )
        if not any(c.name == "sessionid" for c in self.jar):
            sys.exit(f"login did not return a sessionid (server response: {resp})")
        if resp.get("success") is False:
            sys.exit(f"login rejected: {resp}")

    def paginate(self, path: str, params: dict | None = None,
                 page: int = DEFAULT_PAGE) -> Iterator[dict]:
        params = dict(params or {})
        offset = 0
        while True:
            params["limit"] = page
            params["offset"] = offset
            payload = self._request(path, params)
            data = payload.get("data", [])
            yield from data
            meta = payload.get("meta", {}) or {}
            total = meta.get("totalCount")
            if len(data) < page:
                break
            offset += page
            if total is not None and offset >= total:
                break


# ---------------------------------------------------------------------------
# OMERO traversal
# ---------------------------------------------------------------------------


def list_project_datasets(client: OmeroClient, project_id: int) -> list[dict]:
    return list(client.paginate(f"/api/v0/m/projects/{project_id}/datasets/"))


def list_dataset_images(client: OmeroClient, dataset_id: int) -> list[dict]:
    return list(client.paginate(f"/api/v0/m/datasets/{dataset_id}/images/"))


def get_dataset(client: OmeroClient, dataset_id: int) -> dict:
    return client._request(f"/api/v0/m/datasets/{dataset_id}/").get("data", {})


def get_project(client: OmeroClient, project_id: int) -> dict:
    return client._request(f"/api/v0/m/projects/{project_id}/").get("data", {})


def image_fileset_id(client: OmeroClient, image_id: int) -> int | None:
    """Optional: pull Fileset ID for an image (one extra request per image)."""
    try:
        d = client._request(f"/api/v0/m/images/{image_id}/").get("data", {})
        fs = d.get("Fileset")
        if isinstance(fs, dict):
            return fs.get("@id")
        return fs
    except SystemExit:
        return None


def build_web_url(base: str, image_id: int, dataset_id: int | None) -> str:
    if dataset_id:
        return f"{base}/webclient/img_detail/{image_id}/?dataset={dataset_id}"
    return f"{base}/webclient/img_detail/{image_id}/"


def build_show_url(base: str, image_id: int) -> str:
    return f"{base}/webclient/?show=image-{image_id}"


# ---------------------------------------------------------------------------
# images command
# ---------------------------------------------------------------------------


def _client_from_args(args: argparse.Namespace) -> OmeroClient:
    client = OmeroClient(args.base, args.sessionid, args.csrftoken)
    if args.username:
        password = (
            os.environ.get("OMERO_PASSWORD")
            or getpass.getpass(f"OMERO password for {args.username}: ")
        )
        client.login(args.username, password, args.server_id)
    elif not args.sessionid:
        sys.exit("provide either --username (interactive login) "
                 "or --sessionid / $OMERO_SESSIONID")
    return client


def cmd_images(args: argparse.Namespace) -> None:
    client = _client_from_args(args)
    rows: list[dict] = []

    targets: list[tuple[int | None, int]] = []  # (project_id, dataset_id)
    if args.project:
        for pid in args.project:
            proj = get_project(client, pid)
            print(f"  project {pid}: {proj.get('Name', '?')!r}")
            for ds in list_project_datasets(client, pid):
                targets.append((pid, ds["@id"]))
    if args.dataset:
        for did in args.dataset:
            targets.append((None, did))
    if not targets:
        sys.exit("must pass --project or --dataset")

    for project_id, dataset_id in targets:
        ds = get_dataset(client, dataset_id)
        ds_name = ds.get("Name", "?")
        # If we don't already know the project, see if dataset links us back
        if project_id is None:
            # Datasets don't directly expose their parent in /api/v0/m/datasets/<id>/
            # — we'll leave project_* blank for explicit-dataset mode
            proj_name = ""
        else:
            proj_name = get_project(client, project_id).get("Name", "")
        images = list_dataset_images(client, dataset_id)
        print(f"  dataset {dataset_id} ({ds_name!r}): {len(images)} images")
        for img in images:
            iid = img["@id"]
            rows.append({
                "filename":    img.get("Name", ""),
                "image_id":    iid,
                "dataset_id":  dataset_id,
                "dataset_name": ds_name,
                "project_id":  project_id or "",
                "project_name": proj_name,
                "fileset_id":  "",  # populate via --with-filesets
                "web_url":     build_web_url(args.base, iid, dataset_id),
                "show_url":    build_show_url(args.base, iid),
            })

    if args.with_filesets:
        print(f"  fetching fileset IDs for {len(rows)} images …")
        for i, r in enumerate(rows, 1):
            r["fileset_id"] = image_fileset_id(client, int(r["image_id"])) or ""
            if i % 100 == 0:
                print(f"    {i}/{len(rows)}")

    with Path(args.out).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {len(rows)} rows → {args.out}")


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


def _expected_omero_filenames(manifest_path: Path) -> dict[str, dict]:
    """Map target_filename → manifest row for every OMERO-bound entry."""
    out: dict[str, dict] = {}
    with manifest_path.open() as f:
        for r in csv.DictReader(f):
            if r["target_storage"] == "omero" and r["target_filename"]:
                out[r["target_filename"]] = r
    return out


def _pulled_filenames(images_csv: Path) -> dict[str, list[dict]]:
    """Map filename → list of rows (handles dupes if a file imported twice)."""
    out: dict[str, list[dict]] = defaultdict(list)
    with images_csv.open() as f:
        for r in csv.DictReader(f):
            out[r["filename"]].append(r)
    return out


def cmd_diff(args: argparse.Namespace) -> None:
    expected = _expected_omero_filenames(Path(args.manifest))
    pulled = _pulled_filenames(Path(args.images))

    missing = sorted(set(expected) - set(pulled))
    extra = sorted(set(pulled) - set(expected))
    dupes = sorted(name for name, rows in pulled.items() if len(rows) > 1)

    print(f"\n  expected (manifest, OMERO-bound): {len(expected)}")
    print(f"  pulled  (OMERO):                   {sum(len(v) for v in pulled.values())}")
    print(f"  missing (failed uploads):          {len(missing)}")
    print(f"  extra   (in OMERO, not manifest):  {len(extra)}")
    print(f"  duplicate imports:                 {len(dupes)}")

    if missing:
        print(f"\n  ── FAILED UPLOADS — re-upload these via Insight: ──")
        for m in missing:
            print(f"    {m}")
            print(f"      original: {expected[m]['original_path']}")
            print(f"      md5:      {expected[m]['md5']}")
            print(f"      figure:   {expected[m]['figure']}")
    if extra:
        print(f"\n  ── EXTRA (in OMERO but not in manifest): ──")
        for e in extra[:20]:
            print(f"    {e}  (image_id={pulled[e][0]['image_id']})")
        if len(extra) > 20:
            print(f"    ... +{len(extra) - 20} more")
    if dupes:
        print(f"\n  ── DUPLICATE IMPORTS (same filename, multiple image_ids): ──")
        for d in dupes:
            ids = [r["image_id"] for r in pulled[d]]
            print(f"    {d}  image_ids={ids}")


# ---------------------------------------------------------------------------
# all command (pull + diff)
# ---------------------------------------------------------------------------


def cmd_all(args: argparse.Namespace) -> None:
    cmd_images(args)
    args.images = args.out
    cmd_diff(args)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=DEFAULT_BASE, help=f"default: {DEFAULT_BASE}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _add_auth(parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("OMERO_USER"),
            help="OMERO username (prompts for password unless $OMERO_PASSWORD set)",
        )
        parser.add_argument(
            "--server-id", type=int, default=None,
            help="OMERO server id (auto-detected if there's only one)",
        )
        parser.add_argument(
            "--sessionid",
            default=os.environ.get("OMERO_SESSIONID"),
            help="alternative to --username: existing OMERO.web session cookie ($OMERO_SESSIONID)",
        )
        parser.add_argument(
            "--csrftoken",
            default=os.environ.get("OMERO_CSRFTOKEN"),
            help="optional, if pairing with --sessionid",
        )

    def _add_targets(parser):
        parser.add_argument("--project", type=int, action="append", default=[],
                            help="project ID (repeatable)")
        parser.add_argument("--dataset", type=int, action="append", default=[],
                            help="dataset ID (repeatable)")

    pi = sub.add_parser("images", help="pull images from project(s)/dataset(s)")
    _add_auth(pi); _add_targets(pi)
    pi.add_argument("--out", default="omero_images.csv")
    pi.add_argument("--with-filesets", action="store_true",
                    help="fetch Fileset ID per image (slow; one extra request per image)")

    pd = sub.add_parser("diff", help="diff manifest vs pulled images")
    pd.add_argument("--manifest", default="manifest.csv")
    pd.add_argument("--images", default="omero_images.csv")

    pa = sub.add_parser("all", help="pull then diff")
    _add_auth(pa); _add_targets(pa)
    pa.add_argument("--manifest", default="manifest.csv")
    pa.add_argument("--out", default="omero_images.csv")
    pa.add_argument("--with-filesets", action="store_true")
    pa.add_argument("--images", default=None, help=argparse.SUPPRESS)

    args = p.parse_args()
    if args.cmd == "images":
        cmd_images(args)
    elif args.cmd == "diff":
        cmd_diff(args)
    elif args.cmd == "all":
        cmd_all(args)


if __name__ == "__main__":
    main()
