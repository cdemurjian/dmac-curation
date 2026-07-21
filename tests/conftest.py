"""Shared fixtures. The plugin_sentinel fixture is the P1 regression guard:
no script may create, modify, or delete anything inside the plugin checkout.
"""
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Paths that legitimately change during a test run and must not trip the sentinel.
SENTINEL_IGNORE_PARTS = {
    ".git", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache",
    ".superpowers", "working", ".venv",
}

# Marker stored in the snapshot for a directory entry. Directories have no
# content hash, but their *existence* is exactly what several scripts get
# wrong: stage_zenodo.py, smb_pull.py and consolidate_to_flat.py all call
# mkdir(parents=True, exist_ok=True) / os.makedirs() against a path anchored
# at the plugin install dir. An empty directory materialising inside the
# checkout is a P1 symptom, so it must trip the sentinel too.
_DIR_MARKER = "<dir>"


def _snapshot(root: Path) -> dict[str, str]:
    """Map repo-relative path -> sha256 of contents (files) or "<dir>" (dirs)."""
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if SENTINEL_IGNORE_PARTS & set(rel.parts):
            continue
        if p.is_symlink():
            # Don't follow; record the link target so a retarget is caught.
            out[str(rel)] = "<symlink>" + str(p.readlink())
        elif p.is_dir():
            out[str(rel)] = _DIR_MARKER
        elif p.is_file():
            out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def plugin_sentinel():
    """Fail the test if the plugin checkout changed while it ran."""
    before = _snapshot(REPO)
    yield REPO
    after = _snapshot(REPO)
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])

    def _label(paths, snap):
        return [p + ("/" if snap.get(p) == _DIR_MARKER else "") for p in paths]

    assert not (created or deleted or modified), (
        "a script wrote inside the plugin checkout:\n"
        f"  created:  {_label(created, after)}\n"
        f"  deleted:  {_label(deleted, before)}\n"
        f"  modified: {_label(modified, after)}"
    )


@pytest.fixture
def curation_project(tmp_path):
    """A minimal curation project: the directory layout plus a v1 lockfile."""
    for d in ("files", "manuscript", "previous_metadata", "assay_sheets",
              "assay_sheets/4sheet_originals", "context", "scripts"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".dmac-curation.json").write_text(json.dumps({
        "schema_version": 1,
        "plugin_version": "0.3.0",
        "modes": {
            "pipeline": {"phase": 5, "lab": "KAM", "nextseek_project_id": 42}
        },
    }, indent=2))
    return tmp_path
