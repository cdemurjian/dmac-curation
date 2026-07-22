# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one project-config seam for dmac-curation scripts (toolkit spec P2).

Before this module, four scripts each carried a `TODO(v0.2)` proposing their
own project config, and ten resolved project paths against the PLUGIN install
directory — so `/curate-consolidate` with no args read and wrote inside the
plugin checkout (toolkit spec P1).

Two rules this module exists to enforce:

  1. PROJECT paths resolve from the current working directory, never from
     ``Path(__file__).parent.parent``.
  2. PLUGIN paths are read-only and limited to ``context/`` and ``templates/``.

Resolution order for any value, highest priority first:
  explicit CLI flag  ->  project lockfile  ->  derived default
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

LOCKFILE_NAME = ".dmac-curation.json"

# Anchored at THIS file, and used only for read-only bundled data.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def plugin_root() -> Path:
    """Absolute path of the plugin checkout. Read-only for everything but tests."""
    return _PLUGIN_ROOT


def plugin_context(name: str) -> Path:
    """A read-only bundled context file, e.g. plugin_context('sampletypes_db.json')."""
    return _PLUGIN_ROOT / "context" / name


def plugin_template(name: str) -> Path:
    """A read-only bundled Jinja2 template, e.g. plugin_template('CLAUDE.md.j2')."""
    return _PLUGIN_ROOT / "templates" / name


def find_project_root(start: Path | None = None) -> Path:
    """Nearest ancestor holding a lockfile; else `start` itself.

    Never returns the plugin checkout: a mode may legitimately run from any
    cwd, and silently adopting the plugin as "the project" is the P1 bug.
    """
    start = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if candidate == _PLUGIN_ROOT:
            break
        if (candidate / LOCKFILE_NAME).is_file():
            return candidate
    return start


def parse_expected_counts(raw: str | None) -> dict[str, int]:
    """Parse ``--expected-counts 'OOC=122,CEL=2'`` into a dict."""
    if not raw:
        return {}
    out: dict[str, int] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(
                f"malformed --expected-counts entry {chunk!r}; want SAMPLETYPE=N"
            )
        key, _, value = chunk.partition("=")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"--expected-counts {key.strip()!r} value {value.strip()!r} "
                f"is not an integer"
            ) from exc
    return out


@dataclass
class ProjectConfig:
    """Everything a pipeline script needs to know about where it is running."""

    root: Path
    lab: str | None = None
    pi: str | None = None
    nextseek_project_id: int | None = None
    scientist: str | None = None
    master_workbook: Path | None = None
    expected_counts: dict[str, int] = field(default_factory=dict)
    always_root: set[str] = field(default_factory=set)

    # ---- derived directories (always under root) --------------------------
    @property
    def files(self) -> Path:
        return self.root / "files"

    @property
    def manuscript(self) -> Path:
        return self.root / "manuscript"

    @property
    def previous_metadata(self) -> Path:
        return self.root / "previous_metadata"

    @property
    def assay_sheets(self) -> Path:
        return self.root / "assay_sheets"

    @property
    def four_sheet_dir(self) -> Path:
        return self.assay_sheets / "4sheet_originals"

    @property
    def context(self) -> Path:
        return self.root / "context"

    @property
    def lockfile(self) -> Path:
        return self.root / LOCKFILE_NAME


def _read_lockfile_pipeline(root: Path) -> dict:
    """Pipeline-mode settings from a v0 or v1 lockfile. Never raises."""
    path = root / LOCKFILE_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if raw.get("schema_version") == 1:
        return dict(raw.get("modes", {}).get("pipeline", {}))
    # v0: flat keys ARE the pipeline mode's settings.
    return {k: v for k, v in raw.items() if not k.startswith("plugin_")}


def _find_master_workbook(previous_metadata: Path) -> Path | None:
    """Most recently modified ``*All*.xlsx`` in previous_metadata/, or None.

    Matches the existing glob in stage_zenodo.py:52, apply_zenodo_links.py:46
    and review_metadata_vs_uploads.py:57 — but rooted at the PROJECT.
    """
    if not previous_metadata.is_dir():
        return None
    candidates = [
        p for p in previous_metadata.glob("*All*.xlsx")
        if p.is_file() and not p.name.startswith("~")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_config(root: Path | None = None, **overrides) -> ProjectConfig:
    """Build a ProjectConfig. Non-None keyword overrides beat the lockfile.

    ``None`` overrides are dropped, so an argparse default of None does not
    clobber a real lockfile value.
    """
    root = Path(root).resolve() if root is not None else find_project_root()
    locked = _read_lockfile_pipeline(root)
    overrides = {k: v for k, v in overrides.items() if v is not None}

    cfg = ProjectConfig(
        root=root,
        lab=overrides.get("lab", locked.get("lab")),
        pi=overrides.get("pi", locked.get("pi")),
        nextseek_project_id=overrides.get(
            "nextseek_project_id", locked.get("nextseek_project_id")),
        scientist=overrides.get("scientist", locked.get("scientist")),
        expected_counts=overrides.get(
            "expected_counts", dict(locked.get("expected_counts") or {})),
        always_root=set(overrides.get(
            "always_root", locked.get("always_root") or [])),
    )
    master = overrides.get("master_workbook")
    cfg.master_workbook = (
        Path(master).resolve() if master else _find_master_workbook(cfg.previous_metadata)
    )
    return cfg


def add_config_args(parser: argparse.ArgumentParser) -> None:
    """Register the standard project-config overrides on any script's parser."""
    g = parser.add_argument_group("project config")
    g.add_argument("--project-root", type=Path, default=None,
                   help="Curation project root (default: nearest ancestor with "
                        f"{LOCKFILE_NAME}, else cwd)")
    g.add_argument("--lab", default=None, help="Lab code, e.g. KAM")
    g.add_argument("--pi", default=None, help="PI short name")
    g.add_argument("--master-baseline", type=Path, default=None,
                   help="Master workbook (default: newest previous_metadata/*All*.xlsx)")
    g.add_argument("--expected-counts", default=None,
                   help="Per-sampletype row expectations, e.g. 'OOC=122,CEL=2'")


def config_from_args(args) -> ProjectConfig:
    """Build a ProjectConfig from a parser that used add_config_args()."""
    return load_config(
        getattr(args, "project_root", None),
        lab=getattr(args, "lab", None),
        pi=getattr(args, "pi", None),
        master_workbook=getattr(args, "master_baseline", None),
        expected_counts=parse_expected_counts(
            getattr(args, "expected_counts", None)) or None,
    )
