# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report dmac-curation state per MODE, not per phase.

The old /curate-status was a hand-written phase-to-artifact map living in
markdown. Detection lives here so it is testable, and so the four modes each
report on their own terms: pipeline has phase artifacts, schema and report have
output directories, fdh has credentials and nothing else.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ProjectRootError, find_project_root  # noqa: E402
from _lockfile import LockfileError, mode as lock_mode, read as lock_read  # noqa: E402

# (phase number, path relative to project root or None, human label)
PIPELINE_ARTIFACTS = [
    (1, "FILE_INDEX.md", "Inventory"),
    (2, "SAMPLE_TREE.md", "Sample tree"),
    (3, "QUESTIONS_FOR_PI.md", "Questions"),
    (5, "assay_sheets/4sheet_originals", "Build (4-sheet review artifacts)"),
    (6, "assay_sheets", "Consolidate (flat Arm*-upload.xlsx)"),
    (7, "context/assay_ids_cache.json", "Resolve assays"),
    (7, "context/assay_synonyms.json", "Resolve assays (synonyms)"),
    (9, None, "QA (console report, no artifact)"),
    (10, "Zenodo_upload", "Deposit"),
    (11, "RETRIEVE.TXT", "Retrieve"),
    (12, None, "Validate (console report, no artifact)"),
    (13, "EMAIL_TO_PI.md", "Email"),
]

NEXT_COMMAND = {
    1: "/curate-inventory",
    2: "/curate-sample-tree",
    3: "/curate-questions add",
    5: "/curate-build <arm>",
    6: "/curate-consolidate",
    7: "/curate-resolve-assays --project-id N",
    9: "/curate-qa",
    10: "/curate-deposit <geo|zenodo|omero>",
    11: "/curate-retrieve",
    12: "/curate-validate <downloaded.xlsx>",
    13: "/curate-email",
}


def _count_xlsx(d: Path, *, with_underscore: bool | None = None) -> int:
    if not d.is_dir():
        return 0
    n = 0
    for p in d.glob("*.xlsx"):
        if p.name.startswith("~"):
            continue
        if with_underscore is True and "_" not in p.stem:
            continue
        if with_underscore is False and "_" in p.stem:
            continue
        n += 1
    return n


def _pipeline_status(root: Path, locked: dict) -> dict:
    artifacts = []
    for phase, rel, label in PIPELINE_ARTIFACTS:
        if rel is None:
            artifacts.append({"phase": phase, "name": label,
                              "present": None, "detail": "no artifact"})
            continue
        target = root / rel
        if rel == "assay_sheets/4sheet_originals":
            n = _count_xlsx(target, with_underscore=True)
            artifacts.append({"phase": phase, "name": rel,
                              "present": n > 0, "detail": f"{n} four-sheet files"})
        elif rel == "assay_sheets":
            n = _count_xlsx(target, with_underscore=False)
            artifacts.append({"phase": phase, "name": "assay_sheets/Arm*.xlsx",
                              "present": n > 0, "detail": f"{n} flat files"})
        elif rel == "SAMPLE_TREE.md":
            # Phase 2 also produces sample_tree.json and the SAMPLE_TREE.html
            # viewer. The HTML is a build artifact: flag it stale when older
            # than the JSON it renders, so a re-run of the tree is visible here.
            present = target.exists()
            html = root / "SAMPLE_TREE.html"
            js = root / "sample_tree.json"
            detail = ""
            if html.is_file():
                stale = (js.is_file()
                         and html.stat().st_mtime < js.stat().st_mtime)
                detail = "+ HTML (stale, re-run tree)" if stale else "+ HTML"
            elif present:
                detail = "no HTML viewer"
            artifacts.append({"phase": phase, "name": rel,
                              "present": present, "detail": detail})
        elif rel == "RETRIEVE.TXT":
            present = target.is_file()
            lines = len(target.read_text().split()) if present else 0
            artifacts.append({"phase": phase, "name": rel, "present": present,
                              "detail": f"{lines} UIDs" if present else ""})
        else:
            artifacts.append({"phase": phase, "name": rel,
                              "present": target.exists(), "detail": ""})

    present_any = bool(locked) or any(a["present"] for a in artifacts)
    detail = ""
    if locked:
        detail = (f"lab={locked.get('lab')} pi={locked.get('pi')} "
                  f"project_id={locked.get('nextseek_project_id')}")
    return {"present": present_any, "detail": detail, "artifacts": artifacts}


def _dir_status(root: Path, subdir: str, glob: str, label: str) -> dict:
    d = root / subdir
    if not d.is_dir():
        return {"present": False, "detail": "", "artifacts": []}
    found = sorted(p.name for p in d.glob(glob))
    # Strip the glob's trailing literal ('.review.md' / '.mapping.json') rather
    # than splitting on the first dot, so a dotted sample type like 'D.VIA'
    # survives intact instead of collapsing to 'D'.
    suffix = glob.lstrip("*")
    stems = sorted({n[: -len(suffix)] if suffix and n.endswith(suffix) else n
                    for n in found})
    return {
        "present": bool(found),
        "detail": f"{label}: {', '.join(stems)}" if stems else "",
        "artifacts": [{"name": f"{subdir}/{n}", "present": True, "detail": ""}
                      for n in found],
    }


def _fdh_status(root: Path) -> dict:
    """Credentials only. NEVER surface the token value."""
    sources = []
    if os.environ.get("FDH_API") or os.environ.get("FDH_TOKEN"):
        sources.append("environment")
    env_file = root / ".env"
    if env_file.is_file():
        try:
            text = env_file.read_text()
        except OSError:
            text = ""
        if "FDH_API" in text or "FDH_TOKEN" in text:
            sources.append(".env")
    return {
        "present": bool(sources),
        "detail": (f"credentials from {', '.join(sources)}" if sources
                   else "no FDH_API configured"),
        "artifacts": [],
    }


def _suggest(pipeline: dict, has_lockfile: bool) -> str:
    if not has_lockfile and not pipeline["present"]:
        return ("/curate-init --lab <CODE> --pi <NAME>  "
                "(or /curate-sampletype <TYPE> for schema mode)")
    for a in pipeline["artifacts"]:
        if a["present"] is False and a["phase"] in NEXT_COMMAND:
            return NEXT_COMMAND[a["phase"]]
    return ("pipeline artifacts all present - /curate-email, "
            "or /curate-report GEO <input>")


def collect_status(root: Path) -> dict:
    root = Path(root).resolve()
    has_lockfile = (root / ".dmac-curation.json").is_file()
    try:
        doc = lock_read(root)
    except LockfileError as exc:
        doc = {"modes": {}}
        print(f"warning: {exc}", file=sys.stderr)

    pipeline = _pipeline_status(root, lock_mode(doc, "pipeline"))
    return {
        "project_root": str(root),
        "lockfile": doc if has_lockfile else None,
        "modes": {
            "pipeline": pipeline,
            "fdh": _fdh_status(root),
            "schema": _dir_status(root, "schema", "*.review.md", "types"),
            "report": _dir_status(root, "report", "*.mapping.json", "formats"),
        },
        "suggested_next": _suggest(pipeline, has_lockfile),
    }


def _render(st: dict) -> str:
    lines = [f"Project root: {st['project_root']}"]
    lock = st["lockfile"]
    if lock:
        lines.append(
            f"Lockfile:     schema v{lock.get('schema_version')} "
            f"plugin {lock.get('plugin_version')} "
            f"vintage {lock.get('schema_vintage', '?')} "
            f"modes {sorted(lock.get('modes', {}))}"
        )
    else:
        lines.append("Lockfile:     none - run /curate-init")
    lines.append("")

    for name, m in st["modes"].items():
        lines.append(f"{'OK ' if m['present'] else '-- '}{name:<9} {m['detail']}")
        if name == "pipeline" and m["present"]:
            for a in m["artifacts"]:
                sym = "-" if a["present"] is None else ("OK" if a["present"] else "--")
                lines.append(f"    {sym:<3} phase {a.get('phase', ''):>2}  "
                             f"{a['name']:<38} {a['detail']}")
    lines.append("")
    lines.append(f"Suggested next: {st['suggested_next']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="Emit JSON, not a table")
    args = ap.parse_args(argv)
    try:
        root = args.project_root or find_project_root()
    except ProjectRootError as exc:
        msg = {
            "project_root": None,
            "lockfile": None,
            "modes": {},
            "suggested_next": "/curate-init  (no curation project here)",
            "note": str(exc),
        }
        if args.json:
            print(json.dumps(msg, indent=2))
        else:
            print("Not a curation project (no .dmac-curation.json at or above "
                  "cwd).")
            print(f"  {exc}")
            print("\nSuggested next: /curate-init  "
                  "(or run schema/report mode from any dir)")
        return 0
    st = collect_status(root)
    print(json.dumps(st, indent=2) if args.json else _render(st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
