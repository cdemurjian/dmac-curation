"""Smoke tests for flat-pipeline scripts."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


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
