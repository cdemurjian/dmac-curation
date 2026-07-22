# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Refresh the plugin's bundled context/ snapshots, with provenance.

context/VINTAGE.json used to promise "Refresh via tools/refresh_context.py
(planned, not yet implemented)" while tools/ did not exist. Meanwhile
context/neo4j_schema.json was byte-identical to chat_nextseek's DEV-instance
snapshot from 2026-03-26, carrying 23 Sample properties where the live copy had
85. Every mode reasons about the graph from these files.

This script copies a set of managed files from a source export directory into
context/, records provenance for each, and refuses to write without --write.

This is a plugin-MAINTENANCE script: unlike the curation scripts (which must
never write inside the plugin checkout), it is run by a maintainer against the
plugin and legitimately writes into context/. It is excluded from the P1
path-anchoring harness for exactly that reason -- see tests/test_path_anchoring.py.

Usage:
  uv run --script scripts/refresh_context.py --check
  uv run --script scripts/refresh_context.py --from-dir <DIR>
  uv run --script scripts/refresh_context.py --from-dir <DIR> --write
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"

# Files this script manages. Anything not listed is hand-maintained and is left
# alone even if it appears in the source directory.
MANAGED_FILES = [
    "sampletypes_db.json",
    "assays_db.json",
    "projects_db.json",
    "neo4j_schema.json",
    "neo4j_assay-sample-conn.json",
]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sample_property_count(schema_path: Path) -> int:
    """Number of properties on the Sample label. The 23-vs-85 staleness signal.

    Tolerant of shape: tries a few plausible key paths and returns 0 rather than
    raising on an export whose layout changed.
    """
    try:
        doc = json.loads(Path(schema_path).read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    for key in ("labels", "nodes", "node_properties", "schema"):
        container = doc.get(key)
        if isinstance(container, dict) and hasattr(container.get("Sample"), "__len__"):
            return len(container["Sample"])
    sample = doc.get("Sample")
    return len(sample) if hasattr(sample, "__len__") else 0


def edge_count(conn_path: Path) -> int:
    try:
        doc = json.loads(Path(conn_path).read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    conns = doc.get("connections", doc) if isinstance(doc, dict) else doc
    return len(conns) if hasattr(conns, "__len__") else 0


def provenance_entry(*, source_repo: str, source_path: str,
                     commit_sha: str | None, vendored_date: str,
                     local_divergence: str, sha256: str | None = None) -> dict:
    """One PROVENANCE.json record. Every vendored file gets exactly one.

    Rationale: sampletypes_db.json already exists in three copies at three
    vintages with no record of which is authoritative. Do not add a fourth
    instance of that problem.
    """
    entry = {
        "source_repo": source_repo,
        "source_path": source_path,
        "commit_sha": commit_sha,
        "vendored_date": vendored_date,
        "local_divergence": local_divergence,
    }
    if sha256 is not None:
        entry["sha256"] = sha256
    return entry


def read_provenance() -> dict:
    p = CONTEXT_DIR / "PROVENANCE.json"
    if not p.is_file():
        return {"description": "", "entries": {}}
    return json.loads(p.read_text())


def write_provenance(doc: dict) -> Path:
    p = CONTEXT_DIR / "PROVENANCE.json"
    doc["entries"] = {k: doc["entries"][k] for k in sorted(doc["entries"])}
    p.write_text(json.dumps(doc, indent=2) + "\n")
    return p


def _git_sha(directory: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def check() -> int:
    """Report staleness signals without touching anything. Returns 1 if stale."""
    print(f"Context dir: {CONTEXT_DIR}")
    vintage_path = CONTEXT_DIR / "VINTAGE.json"
    if vintage_path.is_file():
        v = json.loads(vintage_path.read_text())
        print(f"Bundled date: {v.get('bundled_date')}")
        print(f"Instance:     {json.dumps(v.get('instance', {}))}")
    prov = read_provenance()
    stale = False
    print()
    for name in MANAGED_FILES:
        p = CONTEXT_DIR / name
        entry = prov["entries"].get(f"context/{name}")
        if not p.is_file():
            print(f"  MISSING  {name}")
            stale = True
            continue
        digest = sha256_of(p)
        note = ""
        if entry is None:
            note = "  (no provenance entry)"
            stale = True
        elif entry.get("sha256") and entry["sha256"] != digest:
            note = "  (diverged from recorded sha256)"
        print(f"  ok       {name:<34} {digest[:12]}{note}")
    print()
    n = sample_property_count(CONTEXT_DIR / "neo4j_schema.json")
    e = edge_count(CONTEXT_DIR / "neo4j_assay-sample-conn.json")
    print(f"Sample properties in neo4j_schema.json: {n}")
    print(f"Edges in neo4j_assay-sample-conn.json:  {e}")
    if n and n < 50:
        print("  WARNING: a DEV-instance snapshot carries ~23 Sample properties; "
              "a live one carries ~85. This looks like the dev snapshot.")
        stale = True
    return 1 if stale else 0


def refresh(from_dir: Path, *, write: bool, commit_sha: str | None = None,
            today: str | None = None) -> int:
    from_dir = Path(from_dir)
    today = today or datetime.date.today().isoformat()
    commit_sha = commit_sha if commit_sha is not None else _git_sha(from_dir)
    prov = read_provenance()
    changed = []

    for name in MANAGED_FILES:
        src = from_dir / name
        dst = CONTEXT_DIR / name
        if not src.is_file():
            print(f"  -  {name:<34} not in source dir, leaving as-is")
            continue
        src_digest = sha256_of(src)
        dst_digest = sha256_of(dst) if dst.is_file() else None
        if src_digest == dst_digest:
            print(f"  =  {name:<34} unchanged")
            continue
        changed.append(name)
        if write:
            dst.write_bytes(src.read_bytes())
            prov["entries"][f"context/{name}"] = provenance_entry(
                source_repo=from_dir.parent.name or str(from_dir),
                source_path=str(src),
                commit_sha=commit_sha,
                vendored_date=today,
                local_divergence="none",
                sha256=src_digest,
            )
            print(f"  ok {name:<34} updated -> {src_digest[:12]}")
        else:
            print(f"  ~  {name:<34} would update "
                  f"{(dst_digest or 'absent')[:12]} -> {src_digest[:12]}")

    if not changed:
        print("\nNothing to do; every managed file already matches the source.")
        return 0
    if write:
        write_provenance(prov)
        print(f"\nUpdated {len(changed)} file(s) and recorded provenance "
              f"(commit {commit_sha}).")
        print("Now update context/VINTAGE.json bundled_date and instance by hand.")
    else:
        print(f"\ndry-run: {len(changed)} file(s) would change. "
              f"Re-run with --write to apply.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-dir", type=Path, default=None,
                    help="Directory holding fresh exports of the managed files")
    ap.add_argument("--check", action="store_true",
                    help="Report staleness and provenance gaps; write nothing")
    ap.add_argument("--write", action="store_true",
                    help="Apply the refresh; default is dry-run.")
    args = ap.parse_args(argv)
    if args.check or args.from_dir is None:
        return check()
    return refresh(args.from_dir, write=args.write)


if __name__ == "__main__":
    sys.exit(main())
