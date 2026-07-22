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
import re
import sys
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


class ProjectRootError(Exception):
    """No curation project found and the only fallback would be the plugin.

    Raised by ``find_project_root`` when there is no lockfile at or above the
    starting directory and that directory is the plugin checkout (or lives
    inside it). Silently adopting the plugin as "the project" is the P1
    read/write-inside-the-checkout bug, so we refuse loudly instead.
    """


def find_project_root(start: Path | None = None) -> Path:
    """Nearest ancestor holding a lockfile; else `start` itself.

    Never returns the plugin checkout (or anything inside it) as a project. An
    explicit ``.dmac-curation.json`` at or above ``start`` always wins, even
    inside a plugin subtree — someone deliberately made a project there. But
    when there is no lockfile anywhere above ``start`` and the fallback would be
    the plugin (a developer running a script straight from the checkout, or
    from a plugin subdir), we raise ``ProjectRootError`` rather than resolve
    every project path inside the install directory (the P1 bug).
    """
    start = Path(start).resolve() if start is not None else Path.cwd().resolve()
    # A real lockfile at or above `start` is honoured unconditionally, including
    # the pathological case where it sits inside the plugin subtree.
    for candidate in (start, *start.parents):
        if (candidate / LOCKFILE_NAME).is_file():
            return candidate
    # No lockfile found. Falling back to `start` is safe only when `start` is
    # not the plugin checkout or a directory inside it.
    if start == _PLUGIN_ROOT or _PLUGIN_ROOT in start.parents:
        raise ProjectRootError(
            f"no {LOCKFILE_NAME} found at or above {start}, and the fallback "
            f"would be the plugin checkout ({_PLUGIN_ROOT}). cd into a curation "
            f"project (a directory with a {LOCKFILE_NAME}, or one you scaffold "
            f"with /curate-init) or pass --project-root."
        )
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


def _embedded_date(name: str) -> tuple[int, int, int] | None:
    """A ``(yy, mm, dd)`` tuple from a 6-digit ``YYMMDD`` token in ``name``, else None.

    Only a *standalone* 6-digit run counts — ``(?<!\\d)\\d{6}(?!\\d)`` — so an
    8-digit ``YYYYMMDD`` or a longer serial does not match, and the month/day
    are range-checked. Version tokens (``v1``, ``vFinal``), free-text names, and
    stray digit runs therefore parse to None and fall through to the mtime path.
    This deliberately UNDER-matches: a name we cannot confidently date is dated
    by mtime rather than by a guessed token. When several standalone tokens are
    valid dates (not seen in the real corpus), the last one wins, since the date
    conventionally trails the name (``MetNet All 260527.xlsx``).

    Note the two-digit year is compared as-is (26 > 25), so ``(yy, mm, dd)``
    ordering is only meaningful within the same century — fine for the corpus,
    which is entirely 25xxxx/26xxxx.
    """
    best: tuple[int, int, int] | None = None
    for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", name):
        tok = match.group(1)
        yy, mm, dd = int(tok[:2]), int(tok[2:4]), int(tok[4:6])
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            best = (yy, mm, dd)  # last valid token wins (date trails the name)
    return best


def _find_master_workbook(previous_metadata: Path) -> Path | None:
    """Select the master ``*All*.xlsx`` in previous_metadata/, or None.

    DELIBERATE BEHAVIOUR CHANGE from the inline helpers this replaces
    (stage_zenodo.py:52, apply_zenodo_links.py:46, review_metadata_vs_uploads.py:57).
    Those all do ``sorted(glob("*All*.xlsx"))[0]`` — alphabetically FIRST, with
    no lock-file exclusion. For date-stamped names (``Lab All 260527.xlsx``)
    alphabetically-first picks the OLDEST-dated workbook, a latent bug. This
    function instead selects, and additionally:

      * globs the same ``*All*.xlsx`` pattern, but excludes Excel ``~$`` lock
        files (a name starting with ``~``);
      * SELECTS newest by embedded ``YYMMDD`` date when a filename carries one
        (robust for the common date-named single-master case), else newest by
        mtime (graceful for version-named files like ``*_AllMetadata_v1.xlsx``
        that have no parseable date). A dated candidate outranks an undated one.
      * SURFACES AMBIGUITY: when more than one candidate survives the glob it
        prints a warning to stderr listing every candidate and the one selected,
        because auto-picking one master silently baselines the whole pipeline
        (SKILL.md: surface ambiguity, don't guess). The curator can override
        with an explicit ``--master-baseline`` path.

    Task 8, deleting the three inline helpers and routing through here, must
    treat this as an intentional change of selection semantics, NOT a pure
    refactor.
    """
    if not previous_metadata.is_dir():
        return None
    candidates = [
        p for p in previous_metadata.glob("*All*.xlsx")
        if p.is_file() and not p.name.startswith("~")
    ]
    if not candidates:
        return None

    def _rank(p: Path) -> tuple[int, tuple[int, int, int], float]:
        date = _embedded_date(p.name)
        # dated files outrank undated; newest date wins; mtime breaks ties and
        # decides among undated (version-named) files.
        return (1 if date is not None else 0,
                date or (0, 0, 0),
                p.stat().st_mtime)

    selected = max(candidates, key=_rank)

    if len(candidates) > 1:
        listing = "\n".join(
            f"    - {p.name}{'  <- selected' if p == selected else ''}"
            for p in sorted(candidates, key=lambda p: p.name)
        )
        print(
            f"[_config] {len(candidates)} master workbooks match "
            f"'*All*.xlsx' in {previous_metadata}; selected '{selected.name}'. "
            f"If that is the wrong baseline, pass an explicit master path "
            f"(e.g. --master-baseline).\n{listing}",
            file=sys.stderr,
        )
    return selected


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
