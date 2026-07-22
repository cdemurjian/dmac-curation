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
    """Map a flat v0 lockfile into v1. Idempotent on an already-v1 dict.

    This only RESHAPES; it never validates. Structural checks (``modes`` is a
    dict of dicts, ``schema_version`` is a usable int) belong to ``read`` so
    that v0 and v1 inputs are vetted on one path.
    """
    if raw.get("schema_version") == SCHEMA_VERSION:
        out = dict(raw)
        out.setdefault("modes", {})
        out["plugin_version"] = PLUGIN_VERSION
        return out

    out: dict = {"schema_version": SCHEMA_VERSION, "plugin_version": PLUGIN_VERSION}
    pipeline: dict = {}
    for key, value in raw.items():
        if key in ("plugin_version", "modes"):
            continue  # plugin_version is bumped; modes is folded in below
        if key in _PLUGIN_LEVEL_KEYS:
            out[key] = value
        else:
            pipeline[key] = value

    # Real v0 never carried a `modes` key, but a hand-edited hybrid might. Keep
    # any pre-existing modes mapping instead of dropping it (its data is real
    # user state), folding the migrated flat keys into its pipeline section. A
    # non-dict `modes` is passed through untouched for read() to reject.
    existing = raw.get("modes")
    if isinstance(existing, dict):
        modes = dict(existing)
        prior = modes.get("pipeline")
        if pipeline or isinstance(prior, dict):
            section = dict(prior) if isinstance(prior, dict) else {}
            section.update(pipeline)
            modes["pipeline"] = section
        out["modes"] = modes
    elif existing is not None:
        out["modes"] = existing  # malformed shape; read() raises on it
    else:
        out["modes"] = {"pipeline": pipeline} if pipeline else {}
    return out


def _validate_v1(data: dict, p: Path) -> None:
    """Raise LockfileError unless ``data`` is a structurally valid v1 document.

    The single chokepoint that lets every downstream consumer (``mode``,
    ``set_mode``, ``_config``, status.py) assume a known-good shape instead of
    guarding each attribute access against a hand-edited or corrupt file.
    """
    modes = data.get("modes")
    if not isinstance(modes, dict):
        raise LockfileError(
            f"{p} has a non-object `modes` ({type(modes).__name__}); expected a "
            f"mapping of mode name to its settings."
        )
    for name, section in modes.items():
        if not isinstance(section, dict):
            raise LockfileError(
                f"{p} mode {name!r} is a {type(section).__name__}, not an object."
            )


def read(root: Path) -> dict:
    """Return the lockfile as v1. Migration is IN MEMORY; disk is untouched.

    Returns an empty v1 document when no lockfile exists, so callers that treat
    the project as optional need no existence check. Any malformed-but-parseable
    shape raises ``LockfileError`` (never a raw ``TypeError``/``AttributeError``)
    so a single ``except LockfileError`` upstream degrades cleanly.
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
    # bool is an int subclass, so True/False must be rejected before the numeric
    # comparison, which would otherwise blow up on a string version.
    if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
        raise LockfileError(
            f"{p} has a non-integer schema_version {version!r}; expected an "
            f"integer up to {SCHEMA_VERSION}."
        )
    if version is not None and version > SCHEMA_VERSION:
        raise LockfileError(
            f"{p} has schema_version {version}, but this plugin understands only "
            f"up to {SCHEMA_VERSION}. Upgrade dmac-curation."
        )
    data = migrate_v0(raw)
    _validate_v1(data, p)
    return data


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
    """A mode's settings from an already-read document; ``{}`` when absent.

    Defensive second layer: a non-dict ``modes`` or a non-dict section yields
    ``{}`` rather than raising. ``read`` already rejects such documents, but
    ``mode`` may be handed a hand-built dict in tests or by status.py.
    """
    modes = data.get("modes")
    if not isinstance(modes, dict):
        return {}
    section = modes.get(name, {})
    return dict(section) if isinstance(section, dict) else {}


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
