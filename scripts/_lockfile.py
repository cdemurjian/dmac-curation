# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read, migrate and write ``.dmac-curation.json`` (toolkit spec section 3).

The v0 lockfile was flat and single-mode: ``lab``, ``pi`` and
``nextseek_project_id`` sat at the top level next to plugin identity keys, with
no ``schema_version`` to hang a migration off. Its shape existed only in prose,
in two places that disagreed (curate-init.md hardcoded plugin_version 0.1.0
while plugin.json said 0.2.0).

v1 nests per-mode settings under ``modes``:

    {"schema_version": 1,
     "plugin_version": "0.3.0",
     "plugin_name": ..., "plugin_sha": ..., "schema_vintage": ...,
     "modes": {"pipeline": {"phase": 6, "lab": "KAM", ...}}}

Modes that need no project never read this file. ``schema`` mode must work from
any cwd; ``report`` mode reads it opportunistically but must not require it.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_VERSION = 1
PLUGIN_VERSION = "0.3.0"
LOCKFILE_NAME = ".dmac-curation.json"

# Keys describing the PLUGIN, not a mode. Everything else in a v0 lockfile was
# pipeline-mode state.
_PLUGIN_LEVEL_KEYS = {
    "plugin_name", "plugin_sha", "plugin_version", "schema_vintage",
    "init_date", "init_user", "schema_version", "modes",
}


class LockfileError(Exception):
    """Malformed lockfile, or one written by a newer plugin."""


def path_for(root: Path) -> Path:
    return Path(root) / LOCKFILE_NAME


def empty() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "modes": {}}


def migrate_v0(raw: dict) -> dict:
    """Map a flat v0 lockfile into v1. Idempotent on an already-v1 dict."""
    if raw.get("schema_version") == SCHEMA_VERSION:
        out = dict(raw)
        out.setdefault("modes", {})
        out["plugin_version"] = PLUGIN_VERSION
        return out

    out: dict = {"schema_version": SCHEMA_VERSION, "plugin_version": PLUGIN_VERSION}
    pipeline: dict = {}
    for key, value in raw.items():
        if key == "plugin_version":
            continue  # always bumped to the running plugin's version
        if key in _PLUGIN_LEVEL_KEYS:
            out[key] = value
        else:
            pipeline[key] = value
    out["modes"] = {"pipeline": pipeline} if pipeline else {}
    return out


def read(root: Path) -> dict:
    """Return the lockfile as v1. Migration is IN MEMORY; disk is untouched.

    Returns an empty v1 document when no lockfile exists, so callers that treat
    the project as optional need no existence check.
    """
    p = path_for(root)
    if not p.is_file():
        return empty()
    try:
        raw = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LockfileError(f"{p} is not readable JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise LockfileError(f"{p} does not contain a JSON object")
    version = raw.get("schema_version")
    if version is not None and version > SCHEMA_VERSION:
        raise LockfileError(
            f"{p} has schema_version {version}, but this plugin understands only "
            f"up to {SCHEMA_VERSION}. Upgrade dmac-curation."
        )
    return migrate_v0(raw)


def write(root: Path, data: dict) -> Path:
    """Persist a v1 document. Sorts modes for a stable diff."""
    p = path_for(root)
    out = dict(data)
    out["schema_version"] = SCHEMA_VERSION
    out["plugin_version"] = PLUGIN_VERSION
    modes = out.get("modes", {})
    out["modes"] = {k: modes[k] for k in sorted(modes)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n")
    return p


def mode(data: dict, name: str) -> dict:
    """A mode's settings from an already-read document; ``{}`` when absent."""
    return dict(data.get("modes", {}).get(name, {}))


def set_mode(root: Path, name: str, values: dict) -> dict:
    """Merge ``values`` into one mode's section and persist. Returns the doc.

    Merging, not replacing: ``/curate-resolve-assays`` recording a project id
    must not erase the phase ``/curate-status`` reads.
    """
    data = read(root)
    modes = data.setdefault("modes", {})
    section = dict(modes.get(name, {}))
    section.update(values)
    modes[name] = section
    write(root, data)
    return data
