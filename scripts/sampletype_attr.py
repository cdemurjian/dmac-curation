#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Programmatic client for NExtSEEK's native sample-attribute editor.

Stopgap for the missing REST write path. The REST proxy
(PATCH /nextseek_api/sample_types/{id}/) forwards to SEEK, and SEEK refuses to
add an attribute to a sample type that has samples:

    # lib/seek/samples/sample_type_editing_constraints.rb
    def allow_new_attribute?
      !samples?
    end

NExtSEEK's own editor at /seek/samples/attributes/ writes via the Django ORM and
never invokes Rails, so it is not subject to that constraint. This drives the
same endpoint that page's "Save an attribute" button drives:

    GET /seek/attribute/save/?sampletype_id=<id>&records=<json>

Because that path bypasses Rails, it also bypasses every SampleType validation.
We re-implement the ones that matter (see _validate) so this stays a tool rather
than a footgun.

Reads go through the REST API, which works fine and is schema-validated.

STOPGAP. This drives an admin-UI endpoint, not a designed API: superuser-only, a GET with
JSON in query params, and no Rails validation (see _validate for the three guards that
replace it). It is expected to be superseded by a proper nextseek_api REST write endpoint
wrapping DBtable_sampleattribute + updateSampleType; when that exists, make this a thin
client of it.

ALSO: a change made here is INVISIBLE to batch-upload validation and to the upload itself
until the NExtSEEK app workers are restarted. prefetch_sample_type_attributes caches
sample_type_id -> attribute titles in a module-level dict with no TTL and no invalidation
on write. The web attributes page will show your new attribute while /curate-qc still
denies it; that disagreement is the bug, not a failed write.

Usage:
    uv run scripts/sampletype_attr.py types
    uv run scripts/sampletype_attr.py list A.TITR
    uv run scripts/sampletype_attr.py add A.TITR --title Titer_Method --type Text
    uv run scripts/sampletype_attr.py add A.TITR --title Titer_Method --type Text --apply
    uv run scripts/sampletype_attr.py selftest A.TITR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import requests
from pathlib import Path

# Production. Override with --base-url or NEXTSEEK_BASE_URL (e.g. the dev
# deployment at https://nextseek-dev.mit.edu) when rehearsing a change.
DEFAULT_BASE_URL = os.environ.get("NEXTSEEK_BASE_URL", "https://nextseek.mit.edu")
PRODUCTION_HOSTS = ("nextseek.mit.edu",)
SAVE_PATH = "/seek/attribute/save/"
DELETE_PATH = "/seek/attribute/delete/"
ATTR_PAGE_PATH = "/seek/samples/attributes/"
LOGIN_PATH = "/login/"

# reformatRecordForDB drops this key outright (dbtable_sampleattribute.py:536).
IGNORED_ON_WRITE = ("sample_controlled_vocab_id",)


def _load_dotenv() -> None:
    """Populate os.environ from the project's .env, then the plugin's, without overriding.

    Mirrors nextseek_api.py so both tools read credentials from the same place.
    """
    here = Path.cwd()
    candidates = [here / ".env"] + [p / ".env" for p in here.parents] \
        + [Path(__file__).resolve().parent.parent / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
        return


class AttrClientError(RuntimeError):
    pass


class SampleTypeAttrClient:
    """Drives the native editor. Reads over REST, writes over /seek/attribute/save/."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._logged_in = False

    # ---- auth -------------------------------------------------------------

    def login(self) -> None:
        """Django session login. The save endpoint needs a session AND is_superuser."""
        if self._logged_in:
            return
        url = f"{self.base_url}{LOGIN_PATH}"
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        token = self.session.cookies.get("csrftoken")
        if not token:
            m = re.search(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)", r.text)
            token = m.group(1) if m else ""
        r = self.session.post(
            url,
            data={
                "username": self.username,
                "password": self.password,
                "csrfmiddlewaretoken": token,
                "next": ATTR_PAGE_PATH,
            },
            headers={"Referer": url},
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()
        # The attributes page redirects to /login/ when unauthenticated, so a
        # successful fetch of it is the real proof the session took.
        probe = self.session.get(f"{self.base_url}{ATTR_PAGE_PATH}", timeout=30)
        if LOGIN_PATH in probe.url:
            raise AttrClientError(
                f"login failed for user {self.username!r} (redirected to {probe.url}). "
                "The save endpoint also requires is_superuser."
            )
        self._logged_in = True

    # ---- reads ------------------------------------------------------------

    def attribute_types(self) -> List[Dict[str, Any]]:
        """Scrape the type id/title map the editor page embeds for its combobox."""
        self.login()
        r = self.session.get(f"{self.base_url}{ATTR_PAGE_PATH}", timeout=30)
        r.raise_for_status()
        m = re.search(r"var\s+sample_attribute_types\s*=\s*(\[.*?\]);", r.text, re.S)
        if not m:
            raise AttrClientError("could not find sample_attribute_types on the attributes page")
        return json.loads(m.group(1))

    def resolve_type_id(self, type_name: str) -> str:
        for opt in self.attribute_types():
            if str(opt["sample_attribute_type_title"]).strip().lower() == type_name.strip().lower():
                return str(opt["sample_attribute_type_id"])
        raise AttrClientError(f"unknown attribute type {type_name!r}")

    def get_sample_type(self, ident: str) -> Dict[str, Any]:
        """Read via REST. Accepts a numeric id or a title such as 'A.TITR'."""
        self.login()
        r = self.session.get(
            f"{self.base_url}/nextseek_api/sample_types/{ident}/",
            headers={"Accept": "application/json"},
            auth=(self.username, self.password),
            timeout=30,
        )
        if r.status_code != 200:
            raise AttrClientError(f"GET sample_type {ident} -> {r.status_code}: {r.text[:400]}")
        return r.json()["data"]

    def list_attributes(self, ident: str) -> List[Dict[str, Any]]:
        return self.get_sample_type(ident)["attributes"]["sample_attributes"]

    # ---- validation (Rails is bypassed, so we do this ourselves) ----------

    @staticmethod
    def _validate(existing: List[Dict[str, Any]], new_attr: Dict[str, Any]) -> None:
        title = str(new_attr["title"]).strip()
        if not title:
            raise AttrClientError("attribute title is required")

        # validate_attribute_title_unique
        for a in existing:
            if str(a["title"]).strip().lower() == title.lower():
                raise AttrClientError(
                    f"attribute {title!r} already exists on this sample type "
                    f"(id={a.get('id')}); saving would UPDATE it, not add a new one"
                )

        # validate_attribute_accessor_names_unique (original_accessor_name = title.lower())
        accessor = title.lower()
        clashes = [a["title"] for a in existing if str(a["title"]).strip().lower() == accessor]
        if clashes:
            raise AttrClientError(f"accessor name {accessor!r} collides with {clashes}")

        # validate_one_title_attribute_present
        if int(new_attr.get("is_title", 0)):
            current = [a["title"] for a in existing if a.get("is_title")]
            if current:
                raise AttrClientError(
                    f"cannot set is_title: {current[0]!r} is already the title attribute. "
                    "A sample type must have exactly 1."
                )

    # ---- write ------------------------------------------------------------

    def build_record(
        self,
        sample_type_id: str,
        title: str,
        type_id: str,
        pos: Optional[int] = None,
        required: bool = False,
        is_title: bool = False,
        existing: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build one grid row exactly as the editor's JS would.

        Gotcha: the combobox uses sample_attribute_type_id as its valueField, so
        the *numeric type id* travels in the key named sample_attribute_type_title.
        reformatRecordForDB:518 reads the id back out of that key.
        'id' is omitted entirely for a new attribute; any id>0 means update.
        """
        if pos is None:
            positions = [int(a.get("pos") or 0) for a in (existing or [])]
            pos = (max(positions) + 1) if positions else 1
        return {
            "title": title,
            "sample_attribute_type_title": str(type_id),
            "pos": int(pos),
            "required": 1 if required else 0,
            "is_title": 1 if is_title else 0,
            "sample_type_id": str(sample_type_id),
        }

    def save(self, sample_type_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.login()
        r = self.session.get(
            f"{self.base_url}{SAVE_PATH}",
            params={"records": json.dumps(records), "sampletype_id": str(sample_type_id)},
            timeout=120,
        )
        if r.status_code != 200:
            raise AttrClientError(f"save -> HTTP {r.status_code}: {r.text[:400]}")
        try:
            return json.loads(r.text)
        except ValueError:
            raise AttrClientError(f"save returned non-JSON (likely an auth redirect): {r.text[:400]}")

    def delete(self, attribute_ids: List[str]) -> Dict[str, Any]:
        """Remove attributes by id.

        Unlike save, sampleAttributeDelete does NOT call updateSampleType, so
        existing samples keep the now-orphaned key in their json_metadata. That
        is harmless (SEEK renders from sample_attributes) but worth knowing.
        """
        self.login()
        # id must be an int: deleteOneRecord does `if primarykey>0` on the raw
        # value (dmac/dbtable.py:178), which raises TypeError on a str under py3.
        records = [{"id": int(i)} for i in attribute_ids]
        r = self.session.get(
            f"{self.base_url}{DELETE_PATH}",
            params={"records": json.dumps(records)},
            timeout=120,
        )
        if r.status_code != 200:
            raise AttrClientError(f"delete -> HTTP {r.status_code}: {r.text[:400]}")
        try:
            return json.loads(r.text)
        except ValueError:
            raise AttrClientError(f"delete returned non-JSON: {r.text[:400]}")


# ---- CLI ------------------------------------------------------------------


def _client(args) -> SampleTypeAttrClient:
    if not args.username or not args.password:
        raise SystemExit(
            "error: no credentials. Set NEXTSEEK_USERNAME + NEXTSEEK_PASSWORD in the\n"
            "project's .env (or pass --username/--password). The save endpoint also\n"
            "requires the account to be is_superuser."
        )
    return SampleTypeAttrClient(args.base_url, args.username, args.password)


def _confirm_production(args) -> None:
    """Refuse an unattended production write.

    This path writes to sample_attributes through the Django ORM, bypassing every
    SEEK/Rails validation. On production that is a shared-schema change affecting
    every project and every existing record of the type. Require the operator to
    say so explicitly rather than inferring it from --apply alone.
    """
    if not getattr(args, "apply", False):
        return
    host = args.base_url.split("//", 1)[-1].split("/", 1)[0]
    if host not in PRODUCTION_HOSTS:
        return
    if getattr(args, "yes_production", False):
        return
    raise SystemExit(
        f"REFUSED: --apply against PRODUCTION ({host}).\n"
        "\n"
        "This writes directly to sample_attributes via the Django ORM. It bypasses\n"
        "every SEEK validation, including the editing constraint that normally\n"
        "forbids adding an attribute to a sample type that has samples. Sample types\n"
        "are GLOBAL: this changes the type for every project and every existing\n"
        "record of it.\n"
        "\n"
        "Rehearse on dev first:\n"
        "  --base-url https://nextseek-dev.mit.edu --apply\n"
        "\n"
        "Then, if you are certain, re-run with --yes-production."
    )


def cmd_types(args) -> int:
    for opt in _client(args).attribute_types():
        print(f"{opt['sample_attribute_type_id']:>4}  {opt['sample_attribute_type_title']}")
    return 0


def cmd_list(args) -> int:
    c = _client(args)
    st = c.get_sample_type(args.sampletype)
    attrs = st["attributes"]["sample_attributes"]
    n_samples = len(st["relationships"]["samples"].get("data", []))
    print(f"{st['attributes']['title']}  (id={st['id']}, samples={n_samples}, attributes={len(attrs)})")
    print(f"{'pos':>4} {'id':>6}  {'title':<32} {'type':<14} req  is_title")
    for a in sorted(attrs, key=lambda x: int(x.get("pos") or 0)):
        print(
            f"{a.get('pos'):>4} {a.get('id'):>6}  {a['title']:<32} "
            f"{a['sample_attribute_type']['title']:<14} "
            f"{'Y' if a.get('required') else 'n':<4} {'Y' if a.get('is_title') else 'n'}"
        )
    return 0


def cmd_add(args) -> int:
    _confirm_production(args)
    c = _client(args)
    st = c.get_sample_type(args.sampletype)
    st_id = st["id"]
    existing = st["attributes"]["sample_attributes"]
    type_id = args.type_id or c.resolve_type_id(args.type)

    record = c.build_record(
        sample_type_id=st_id,
        title=args.title,
        type_id=type_id,
        pos=args.pos,
        required=args.required,
        is_title=args.is_title,
        existing=existing,
    )
    try:
        c._validate(existing, record)
    except AttrClientError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    print(f"sample type : {st['attributes']['title']} (id={st_id}, samples="
          f"{len(st['relationships']['samples'].get('data', []))})")
    print(f"endpoint    : GET {c.base_url}{SAVE_PATH}")
    print(f"record      : {json.dumps(record, indent=2)}")
    for k in IGNORED_ON_WRITE:
        print(f"note        : {k} is silently dropped by reformatRecordForDB and will NOT be written")

    if not args.apply:
        print("\nDRY RUN. Nothing sent. Re-run with --apply to submit.")
        return 0

    resp = c.save(st_id, [record])
    print(f"\nresponse    : {json.dumps(resp)[:600]}")
    if not resp.get("status"):
        print("FAILED", file=sys.stderr)
        return 1

    after = c.list_attributes(st_id)
    got = [a for a in after if str(a["title"]).strip().lower() == args.title.strip().lower()]
    if not got:
        print(f"FAILED: {args.title!r} not present after save", file=sys.stderr)
        return 1
    print(f"VERIFIED    : {args.title!r} present (id={got[0]['id']}, "
          f"type={got[0]['sample_attribute_type']['title']}, pos={got[0].get('pos')})")
    return 0


def cmd_remove(args) -> int:
    """Remove an attribute by title. Dry run unless --apply."""
    c = _client(args)
    st = c.get_sample_type(args.sampletype)
    st_id = st["id"]
    existing = st["attributes"]["sample_attributes"]
    target = [a for a in existing if str(a["title"]).strip().lower() == args.title.strip().lower()]
    if not target:
        print(f"ERROR: {args.title!r} not found on {st['attributes']['title']}", file=sys.stderr)
        return 1
    attr = target[0]
    if attr.get("is_title"):
        print(f"REFUSED: {args.title!r} is the title attribute; removing it would leave 0.", file=sys.stderr)
        return 2

    print(f"sample type : {st['attributes']['title']} (id={st_id})")
    print(f"will remove : {attr['title']} (id={attr['id']}, pos={attr.get('pos')})")
    if not args.apply:
        print("\nDRY RUN. Nothing sent. Re-run with --apply to submit.")
        return 0

    resp = c.delete([attr["id"]])
    print(f"response    : {json.dumps(resp)[:400]}")
    after = c.list_attributes(st_id)
    if any(str(a["title"]).strip().lower() == args.title.strip().lower() for a in after):
        print(f"FAILED: {args.title!r} still present", file=sys.stderr)
        return 1
    print(f"VERIFIED    : {args.title!r} removed. attributes now {len(after)}")
    return 0


def cmd_selftest(args) -> int:
    """Add a probe attribute, verify it landed, and report. Requires --apply to write."""
    c = _client(args)
    st = c.get_sample_type(args.sampletype)
    st_id = st["id"]
    before = st["attributes"]["sample_attributes"]
    n_samples = len(st["relationships"]["samples"].get("data", []))
    probe = args.title

    print(f"sample type      : {st['attributes']['title']} (id={st_id})")
    print(f"samples          : {n_samples}  <- REST PATCH is blocked when this is > 0")
    print(f"attributes before: {len(before)}")

    record = c.build_record(st_id, probe, c.resolve_type_id(args.type), existing=before)
    try:
        c._validate(before, record)
    except AttrClientError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    if not args.apply:
        print(f"\nwould send       : {json.dumps(record)}")
        print("DRY RUN. Nothing sent. Re-run with --apply to submit.")
        return 0

    resp = c.save(st_id, [record])
    print(f"save response    : {json.dumps(resp)[:400]}")

    after = c.list_attributes(st_id)
    got = [a for a in after if str(a["title"]).strip().lower() == probe.lower()]
    print(f"attributes after : {len(after)}")
    if got:
        print(f"RESULT: PASS. {probe!r} added to a sample type with {n_samples} samples, "
              "which the REST PATCH cannot do.")
        return 0
    print(f"RESULT: FAIL. {probe!r} not found after save.", file=sys.stderr)
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    _load_dotenv()

    # Pull --yes-production out of argv up front. As a parent-parser flag it would
    # otherwise have to precede the subcommand, and a confirmation flag that fails
    # when written in the obvious place is worse than no flag at all.
    argv = list(sys.argv[1:] if argv is None else argv)
    yes_production = "--yes-production" in argv
    argv = [a for a in argv if a != "--yes-production"]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"default: {DEFAULT_BASE_URL}")
    # Plugin convention is NEXTSEEK_USERNAME; NEXTSEEK_USER is the older name this
    # script shipped with. No demo/demopassword default - those are dev-only creds
    # and silently using them against production would be worse than failing.
    p.add_argument("--username",
                   default=os.environ.get("NEXTSEEK_USERNAME") or os.environ.get("NEXTSEEK_USER"))
    p.add_argument("--password", default=os.environ.get("NEXTSEEK_PASSWORD"))
    # NB: --yes-production is consumed from argv before parsing (see below) so it
    # works in any position. Declared here only so it shows up in --help.
    p.add_argument("--yes-production", dest="yes_production", action="store_true",
                   help="Required alongside --apply when targeting production. "
                        "Accepted anywhere on the command line.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("types", help="list available attribute type ids").set_defaults(func=cmd_types)

    sp = sub.add_parser("list", help="list a sample type's attributes")
    sp.add_argument("sampletype")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("add", help="add an attribute (dry run unless --apply)")
    sp.add_argument("sampletype")
    sp.add_argument("--title", required=True)
    sp.add_argument("--type", default="Text", help="attribute type name, default: Text")
    sp.add_argument("--type-id", help="numeric type id, overrides --type")
    sp.add_argument("--pos", type=int, help="default: max(existing pos) + 1")
    sp.add_argument("--required", action="store_true")
    sp.add_argument("--is-title", dest="is_title", action="store_true")
    sp.add_argument("--apply", action="store_true", help="actually submit")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("remove", help="remove an attribute by title (dry run unless --apply)")
    sp.add_argument("sampletype")
    sp.add_argument("--title", required=True)
    sp.add_argument("--apply", action="store_true", help="actually submit")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("selftest", help="add a probe attribute and verify it landed")
    sp.add_argument("sampletype")
    sp.add_argument("--title", default="ZZZ_Probe_Attr")
    sp.add_argument("--type", default="Text")
    sp.add_argument("--apply", action="store_true", help="actually submit")
    sp.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    args.yes_production = yes_production
    _confirm_production(args)   # no-op unless --apply
    try:
        return args.func(args)
    except AttrClientError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
