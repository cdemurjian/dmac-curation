# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Strip credentials and host-specific URLs from a harvested API fixture.

Fixtures are HARVESTED from chat_nextseek run directories, not authored. Every
report run persists exactly the responses this plugin needs
(reports/outputs.py:555-563). Authoring one by hand would risk a shape the API
never returns -- the retrieve response is nested five levels and it is easy to
get wrong from memory.

Scrubbing is required before committing: run directories contain real tokens and
localhost URLs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECRET_KEY_RE = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|authorization|cookie)",
    re.IGNORECASE)
LOCALHOST_RE = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", re.IGNORECASE)
BASIC_AUTH_RE = re.compile(r"://[^/@\s:]+:[^/@\s]+@")

REDACTED = "***REDACTED***"
PLACEHOLDER_HOST = "https://nextseek.example.org"


def _scrub_text(text: str) -> str:
    text = LOCALHOST_RE.sub(PLACEHOLDER_HOST, text)
    return BASIC_AUTH_RE.sub("://", text)


def scrub(doc):
    """Recursively redact secret-looking keys and rewrite host-specific URLs."""
    if isinstance(doc, dict):
        out = {}
        for key, value in doc.items():
            if SECRET_KEY_RE.search(str(key)):
                out[key] = REDACTED
            else:
                out[key] = scrub(value)
        return out
    if isinstance(doc, list):
        return [scrub(v) for v in doc]
    if isinstance(doc, str):
        return _scrub_text(doc)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Harvested JSON artifact")
    ap.add_argument("dest", type=Path, help="Where to write the scrubbed copy")
    args = ap.parse_args(argv)
    doc = json.loads(args.source.read_text())
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(json.dumps(scrub(doc), indent=2) + "\n")
    print(f"scrubbed {args.source} -> {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
