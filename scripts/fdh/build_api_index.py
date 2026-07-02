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


# Non-{id} paths that still address a single resource (e.g. /people/current).
_SINGLETON_SUFFIXES = ("current",)


def _is_item(path):
    """True when the path addresses a single resource: it ends in a {placeholder}
    or a known singleton suffix like /current."""
    tail = path.rstrip("/").split("/")[-1]
    return tail.endswith("}") or tail in _SINGLETON_SUFFIXES


def categorize(path, method):
    if path == "/search":
        return "search"
    if "content_blobs" in path:
        # Method-aware so writes/deletes on blobs are not mislabeled as reads.
        if method == "get":
            return "file_download" if path.endswith("/download") else "file_read"
        if method in ("put", "post", "patch"):
            return "file_update"
        if method == "delete":
            return "file_delete"
        return f"file_{method}"
    entity = entity_of(path)
    is_item = _is_item(path)
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
    is_item = _is_item(path)
    key = "get_item" if (method == "get" and is_item) else ("get_list" if method == "get" else method)
    return list(_INTENTS.get(key, [])) + [entity_of(path)]


def llm_hint(path, method, summary):
    needs_id = "{" in path  # a real path placeholder like {id}; excludes /people/current
    bits = []
    if method == "delete":
        bits.append("DESTRUCTIVE — irreversible on the live repo; dry-run and confirm before writing.")
    if needs_id and method in ("get", "patch", "put", "delete"):
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
