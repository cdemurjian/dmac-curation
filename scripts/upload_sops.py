#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Register a project's protocol .docx files on NExtSEEK as SOP records.

Usage (from a curation project root):

    uv run --script <PLUGIN>/scripts/upload_sops.py --project-id 4
    uv run --script <PLUGIN>/scripts/upload_sops.py --project-id 4 --write --confirmed
    uv run --script <PLUGIN>/scripts/upload_sops.py --project-id 4 --only AFM --write --confirmed

**Preview by default, and ask a human before writing.** Every run without `--write`
lists exactly what would be POSTed and creates nothing. `--write` on its own is
REFUSED before any network call; it must be paired with `--confirmed`, which
asserts that a person saw the preview and approved it. Registering a protocol set
is a separate decision from authoring one, and the records land in a catalog every
curator on the project shares.

The rest of the plugin can only READ SOPs (scripts/report/protocols.py resolves
/sops/{id} and extracts text), and the FairDomHub uploader is a different system
with a two-step blob reservation. NExtSEEK's own POST /nextseek_api/sops/ is
single-step multipart, so this adds it, reusing NExtSEEKClient for auth and the
Django CSRF dance.

Two server behaviours are worked around, both observed on MetNet (project 4) and
reported upstream as BioMicroCenter/NExtSEEK#109:

  1. **POST returns HTTP 500 with an HTML body while still creating the record.**
     SOPs 646 and 648 both arrived that way. The response is therefore not
     evidence in either direction, so a create that looks failed is confirmed by
     re-querying the server rather than by reading the response.
  2. **POST rewrites the submitted title**, prefixing it `<YYMMDD>-V<n>_`. PATCH
     does not re-prefix, so the canonical title is set in a second call.

Re-running is safe: a filename already registered is skipped, never duplicated.
That is idempotency, not reuse: this command always registers the batch it was
given, and does not go looking for someone else's SOP to cite instead.

Writes protocols/_sops.json, a {filename: {"id", "title", "url"}} index, which
build_protocols.py reads to fill the SOP column of COVERAGE.md, and which
/curate-build reads for the `Protocol` column of the upload sheets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nextseek_api as N  # noqa: E402

DOCX_CT = ("application/vnd.openxmlformats-officedocument."
           "wordprocessingml.document")
DEFAULT_LICENSE = "CC-BY-4.0"
MAX_PAGES = 40

REFUSAL = (
    "REFUSED: --write creates SOP records on a live shared NExtSEEK server.\n"
    "\n"
    "Ask the user before uploading. Show them the preview (this command with no\n"
    "--write), get a clear yes, and only then re-run with:\n"
    "\n"
    "    --write --confirmed\n"
    "\n"
    "--confirmed asserts that a human saw what would be created and approved it.\n"
    "Do not pass it on the strength of a general instruction to run the phase:\n"
    "registering a protocol set is a separate decision from authoring one, and\n"
    "the records land in a catalog every curator on the project shares."
)


def client() -> "N.NExtSEEKClient":
    N._load_dotenv()
    user, pw = os.environ.get("NEXTSEEK_USERNAME"), os.environ.get("NEXTSEEK_PASSWORD")
    if not (user and pw):
        sys.exit("NEXTSEEK_USERNAME / NEXTSEEK_PASSWORD not set (put them in .env)")
    return N.NExtSEEKClient(username=user, password=pw)


def _csrf_headers(c) -> dict:
    csrf = c._prime_csrf()
    return {"X-CSRFToken": csrf, "Referer": c.base_url} if csrf else {}


def all_titles(c) -> dict[int, str]:
    """{sop_id: title} across every page. `page[size]` is honoured here."""
    out, page = {}, 1
    while page <= MAX_PAGES:
        body = c._get("/sops/", params={"page[number]": page, "page[size]": 100})
        data = body.get("data", [])
        if not data:
            break
        for rec in data:
            out[int(rec["id"])] = rec.get("attributes", {}).get("title", "")
        if len(data) < 100:
            break
        page += 1
    return out


def registered(c) -> dict[str, str]:
    """filename -> id, accepting the canonical AND the server-prefixed title."""
    out: dict[str, str] = {}
    for sop_id, title in sorted(all_titles(c).items()):
        out[title] = str(sop_id)
        if "_" in title:                       # also key by the un-prefixed tail
            out[title.split("_", 1)[1]] = str(sop_id)
    return out


def metadata_for(title: str, project_id: str, description: str,
                 license_: str) -> dict:
    return {
        "data": {
            "type": "sops",
            "attributes": {
                "title": title,
                "description": description,
                "license": license_,
                "policy": {
                    "access": "no_access",
                    "permissions": [
                        {"resource": {"id": project_id, "type": "projects"},
                         "access": "manage"},
                    ],
                },
            },
            "relationships": {
                "projects": {"data": [{"id": project_id, "type": "projects"}]},
            },
        }
    }


def find_existing(c, filename: str) -> str | None:
    """Newest SOP id titled `filename`, or the server-prefixed form.

    Matching on content_blobs does not work (the list representation omits
    them), so the title is the only handle.
    """
    hits = [i for i, t in all_titles(c).items()
            if t == filename or t.endswith("_" + filename)]
    return str(max(hits)) if hits else None


def set_title(c, sop_id: str, title: str) -> str:
    url = f"{c.base_url}/nextseek_api/sops/{sop_id}/"
    headers = {**_csrf_headers(c), "Content-Type": "application/json"}
    payload = {"data": {"type": "sops", "id": str(sop_id),
                        "attributes": {"title": title}}}
    r = c.session.patch(url, data=json.dumps(payload), headers=headers,
                        timeout=c.timeout)
    if not r.ok:
        raise N.NExtSEEKError(r.status_code, url, r.text[:500])
    d = r.json().get("data", {})
    d = d[0].get("data", d) if isinstance(d, list) else d
    return d.get("attributes", {}).get("title", "")


def create_sop(c, path: Path, metadata: dict) -> tuple[str, str]:
    """POST then PATCH. Returns (sop_id, final_title)."""
    url = f"{c.base_url}/nextseek_api/sops/"
    with open(path, "rb") as fh:
        resp = c.session.post(
            url,
            files={"file": (path.name, fh, DOCX_CT)},
            data={"metadata": json.dumps(metadata)},
            headers=_csrf_headers(c),
            timeout=c.timeout,
        )
    sop_id = None
    if resp.ok:
        try:
            d = resp.json().get("data", {})
            d = d[0].get("data", d) if isinstance(d, list) else d
            sop_id = d.get("id")
        except ValueError:
            pass
    if not sop_id:                     # response unusable; ask the server
        sop_id = find_existing(c, path.name)
    if not sop_id:
        raise N.NExtSEEKError(resp.status_code, url,
                              f"no record created; body: {resp.text[:400]}")
    return sop_id, set_title(c, sop_id, path.name)


def description_from_manifest(pdir: Path, override: str | None) -> str:
    if override:
        return override
    mf = pdir / "_manifest.json"
    if mf.is_file():
        m = json.loads(mf.read_text())
        bits = [b for b in (m.get("study"), m.get("doi")) if b]
        if bits:
            return "Materials and Methods excerpt, " + ", ".join(bits)
    return "Protocol registered by dmac-curation"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-id", required=True,
                    help="NExtSEEK project id the SOPs are filed under")
    ap.add_argument("--protocols-dir", default="protocols",
                    help="directory holding the P.*.docx files (default protocols/)")
    ap.add_argument("--only", help="substring of a filename; register just that one")
    ap.add_argument("--license", default=DEFAULT_LICENSE,
                    help=f"SOP license (default {DEFAULT_LICENSE})")
    ap.add_argument("--description",
                    help="SOP description; default is built from _manifest.json")
    ap.add_argument("--write", action="store_true",
                    help="actually create the records (default: preview only). "
                         "Requires --confirmed.")
    ap.add_argument("--confirmed", action="store_true",
                    help="you showed a human the preview and they said yes. "
                         "Required alongside --write.")
    args = ap.parse_args()

    # The confirm gate runs BEFORE anything else, so a --write typed on a hunch
    # cannot even authenticate, let alone create a record.
    if args.write and not args.confirmed:
        sys.exit(REFUSAL)

    pdir = Path(args.protocols_dir).resolve()
    files = sorted(p for p in pdir.glob("P.*.docx") if not p.name.startswith("~"))
    if args.only:
        files = [f for f in files if args.only.lower() in f.name.lower()]
    if not files:
        sys.exit(f"no matching P.*.docx in {pdir}; run build_protocols.py first")

    description = description_from_manifest(pdir, args.description)
    c = client()
    have = registered(c)
    print(f"{len(have)} SOP titles currently on {c.base_url}\n")

    todo = [f for f in files if f.name not in have]
    for f in files:
        if f.name in have:
            print(f"  SKIP  {f.name}  (already registered as SOP {have[f.name]})")

    if not args.write:
        for f in todo:
            print(f"\n  WOULD POST {f.name}  ({f.stat().st_size} bytes)")
            print(f"    -> {c.base_url}/nextseek_api/sops/")
            print(f"    file:     ({f.name}, {DOCX_CT})")
            print(f"    metadata: {json.dumps(metadata_for(f.name, args.project_id, description, args.license))}")
        print(f"\npreview: {len(todo)} would be created, {len(files) - len(todo)} "
              f"already registered.")
        if todo:
            print("Show this to the user. Once they approve, re-run with "
                  "--write --confirmed.")
        return

    index_path = pdir / "_sops.json"
    index = json.loads(index_path.read_text()) if index_path.is_file() else {}
    for f in files:                       # keep prior registrations in the index
        if f.name in have:
            index[f.name] = {"id": have[f.name], "title": f.name,
                             "url": f"{c.base_url}/sops/{have[f.name]}"}

    created = []
    for f in todo:
        try:
            sop_id, final = create_sop(c, f, metadata_for(
                f.name, args.project_id, description, args.license))
        except N.NExtSEEKError as e:
            print(f"  ✗ {f.name}  FAILED: {e}")
            break
        created.append(f.name)
        index[f.name] = {"id": sop_id, "title": final,
                         "url": f"{c.base_url}/sops/{sop_id}"}
        flag = "" if final == f.name else f"   TITLE MISMATCH: {final!r}"
        print(f"  ✓ {f.name}  -> SOP {sop_id}  {c.base_url}/sops/{sop_id}{flag}")

    index_path.write_text(json.dumps(dict(sorted(index.items())), indent=2) + "\n")
    print(f"\ncreated {len(created)}, already registered {len(files) - len(todo)}, "
          f"remaining {len(todo) - len(created)}")
    print(f"index written to {index_path}")
    if created:
        print("re-run build_protocols.py --coverage-only to fill the SOP column")


if __name__ == "__main__":
    main()
