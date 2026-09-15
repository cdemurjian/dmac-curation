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


# ─── build_retrieve: file discovery and leaf retention ─────────────────────
#
# Two defects found curating a single-project study (Jones, study 88):
#   1. the glob only matched `-upload`, so `--all-in-one NAME` output (NAME.xlsx)
#      produced an empty RETRIEVE.TXT and still exited 0;
#   2. parent-type rows were excluded by TYPE, so a branch terminating in a
#      parent type (PAT -> PAV -> TIS) was never requested and never retrieved.


def _write_samples(path, rows):
    """Write a flat-format upload workbook: uid/sampletype/name/parent."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Samples"
    ws.append(["uid", "sampletype", "name", "parent"])
    for uid, parent in rows:
        ws.append([uid, uid.split("-", 1)[0], uid, parent])
    wb.save(path)


def _run_retrieve(sheets_dir, out, *extra):
    script = SCRIPTS_DIR / "build_retrieve.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(script),
         "--assay-sheets", str(sheets_dir), "--output", str(out), *extra],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return [line for line in out.read_text().split("\n") if line]


# The chain every case below draws from: a normal branch whose TIS has a D.SEQ
# child, and a branch that dead-ends at a TIS leaf.
CHAIN = [
    ("MUS-190914JON-1", ""),
    ("TIS-190914JON-1", "MUS-190914JON-1"),
    ("D.SEQ-190914JON-1", "TIS-190914JON-1"),
    ("PAT-190914JON-1", ""),
    ("PAV-190914JON-1", "PAT-190914JON-1"),
    ("TIS-190914JON-2", "PAV-190914JON-1"),  # leaf: nothing derives from it
]


def test_build_retrieve_reads_all_in_one_output(tmp_path):
    """`--all-in-one NAME` writes NAME.xlsx, with no `-upload` in the name."""
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "Jones_spatial.xlsx", CHAIN)
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT")
    assert "D.SEQ-190914JON-1" in uids


def test_build_retrieve_skips_review_companion(tmp_path):
    """The `_review` workbook is never uploaded, so it is never retrieved from."""
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "ArmA-upload.xlsx", CHAIN)
    _write_samples(sheets / "ArmA_review.xlsx", [("D.SEQ-190914JON-99", "")])
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT")
    assert "D.SEQ-190914JON-99" not in uids


def test_build_retrieve_prefers_upload_new_then_upload_then_bare(tmp_path):
    """Ranking is per basename: the freshest curation of ArmA wins outright."""
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "ArmA.xlsx", [("D.SEQ-190914JON-1", "")])
    _write_samples(sheets / "ArmA-upload.xlsx", [("D.SEQ-190914JON-2", "")])
    _write_samples(sheets / "ArmA-upload-new.xlsx", [("D.SEQ-190914JON-3", "")])
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT")
    assert uids == ["D.SEQ-190914JON-3"]


def test_build_retrieve_keeps_parent_type_leaf(tmp_path):
    """A TIS that nothing derives from is the only way to reach its branch."""
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "ArmE-upload.xlsx", CHAIN)
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT")
    assert "TIS-190914JON-2" in uids, "leaf TIS dropped — its branch is unreachable"
    assert "TIS-190914JON-1" not in uids, "TIS with a child is pulled by lineage"
    assert "MUS-190914JON-1" not in uids
    assert "PAT-190914JON-1" not in uids
    assert "PAV-190914JON-1" not in uids


def test_build_retrieve_splits_semicolon_joined_parents(tmp_path):
    """A row deriving from several samples names them all in one `parent` cell.

    Treating the raw cell as one key makes every uid but the first look
    childless, so each would be emitted as a leaf.
    """
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "ArmB-upload.xlsx", [
        ("CEL-190914JON-1", ""),
        ("CEL-190914JON-2", ""),
        ("CEL-190914JON-3", ""),
        # derives from all three above
        ("CEL-190914JON-4", "CEL-190914JON-1;CEL-190914JON-2;CEL-190914JON-3"),
        ("D.PCR-190914JON-1", "CEL-190914JON-4"),
    ])
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT")
    assert uids == ["D.PCR-190914JON-1"], "a co-parent was mistaken for a leaf"


def test_build_retrieve_include_parents_keeps_everything(tmp_path):
    """The override is unchanged: every UID, children or not."""
    sheets = tmp_path / "assay_sheets"
    sheets.mkdir()
    _write_samples(sheets / "ArmE-upload.xlsx", CHAIN)
    uids = _run_retrieve(sheets, tmp_path / "RETRIEVE.TXT", "--include-parents")
    assert sorted(uids) == sorted(uid for uid, _ in CHAIN)


# ─── Delete-loop guard: never operate inside the plugin checkout ────────────
#
# consolidate_to_flat.py DELETES every underscore-free .xlsx from its target
# dir. If a curator points --assay-sheets at the plugin's own tree (run from a
# legit project, so ProjectRootError never fires), the loop would delete files
# inside the plugin checkout. These tests prove the guard PREDICATE rejects any
# plugin-tree target; they never hand the loop a deletable file inside the real
# plugin, so even a broken guard could not destroy anything here.

def test_consolidated_output_predicate_protects_upload_new():
    """The cleanup predicate deletes owned outputs but keeps working copies."""
    f = consolidate_to_flat.is_consolidated_output
    # Owned outputs — deletable before a re-run.
    assert f("ArmA-upload.xlsx") is True        # current suffixed output
    assert f("ArmA.xlsx") is True               # legacy bare-arm output
    # NEVER deletable.
    assert f("ArmA-upload-new.xlsx") is False   # protected hand-edited copy
    assert f("ArmA_RNA.xlsx") is False          # 4-sheet source (has underscore)
    assert f("~$ArmA-upload.xlsx") is False     # openpyxl lock file
    assert f("notes.txt") is False              # not an xlsx


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
