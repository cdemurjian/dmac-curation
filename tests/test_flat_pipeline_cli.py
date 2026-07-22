"""Smoke tests for flat-pipeline scripts."""
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
PLUGIN_ROOT = SCRIPTS_DIR.parent

# consolidate_to_flat imports `_config` from scripts/, so scripts/ must be on
# the path before importing it for the guard-predicate unit test below.
sys.path.insert(0, str(SCRIPTS_DIR))
import consolidate_to_flat  # noqa: E402
from _config import plugin_root  # noqa: E402


def _help_runs(script_name: str) -> None:
    script = SCRIPTS_DIR / script_name
    result = subprocess.run(
        ["uv", "run", "--script", str(script), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"{script_name} --help failed: {result.stderr}"


def test_consolidate_to_flat_help():
    _help_runs("consolidate_to_flat.py")


def test_qa_flat_sheets_help():
    _help_runs("qa_flat_sheets.py")


def test_build_retrieve_help():
    _help_runs("build_retrieve.py")


def test_build_retrieve_empty_dir(tmp_path):
    (tmp_path / "assay_sheets").mkdir()
    out = tmp_path / "RETRIEVE.TXT"
    script = SCRIPTS_DIR / "build_retrieve.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(script),
         "--assay-sheets", str(tmp_path / "assay_sheets"),
         "--output", str(out)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert out.exists()
    assert out.read_text() == "\n"  # empty file with trailing newline


# ─── Delete-loop guard: never operate inside the plugin checkout ────────────
#
# consolidate_to_flat.py DELETES every underscore-free .xlsx from its target
# dir. If a curator points --assay-sheets at the plugin's own tree (run from a
# legit project, so ProjectRootError never fires), the loop would delete files
# inside the plugin checkout. These tests prove the guard PREDICATE rejects any
# plugin-tree target; they never hand the loop a deletable file inside the real
# plugin, so even a broken guard could not destroy anything here.

def test_consolidate_guard_predicate_rejects_plugin_and_accepts_project(tmp_path):
    """The guard predicate: reject the plugin tree, accept a real project's dir."""
    plugin = plugin_root()
    # The plugin root itself must be rejected...
    assert consolidate_to_flat._is_inside_plugin(plugin) is True
    # ...as must any path under it — the exact --assay-sheets <plugin>/assay_sheets
    # threat (asserted even though that dir does not exist on disk).
    assert consolidate_to_flat._is_inside_plugin(plugin / "assay_sheets") is True
    # ...but a legitimate project's assay_sheets dir must pass.
    project_sheets = tmp_path / "assay_sheets"
    project_sheets.mkdir()
    assert consolidate_to_flat._is_inside_plugin(project_sheets) is False


def test_consolidate_refuses_assay_sheets_inside_the_plugin(tmp_path):
    """CLI: from a valid project cwd, --assay-sheets <plugin>/assay_sheets is
    refused before any deletion. We target a plugin path with no deletable files,
    so this proves the guard fires — not that the blast happened to spare us."""
    # A lockfile so find_project_root resolves this cwd instead of raising.
    (tmp_path / ".dmac-curation.json").write_text("{}")
    target = PLUGIN_ROOT / "assay_sheets"
    script = SCRIPTS_DIR / "consolidate_to_flat.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(script), "--assay-sheets", str(target)],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0, f"expected refusal, got rc=0:\n{result.stdout}"
    assert "refusing" in result.stderr.lower(), result.stderr
    assert "plugin" in result.stderr.lower(), result.stderr
    # The guard fires before any mkdir/delete, so the plugin tree is untouched.
    assert not target.exists(), "guard must not create <plugin>/assay_sheets"
