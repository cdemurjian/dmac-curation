"""Smoke tests for rename_files.py and omero_pull.py."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def test_rename_files_help():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPTS_DIR / "rename_files.py"), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    for sub in ["walk", "checksums", "apply", "verify", "rollback"]:
        assert sub in result.stdout, f"subcommand {sub} not in --help"


def test_omero_pull_help():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPTS_DIR / "omero_pull.py"), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    for sub in ["images", "diff", "all"]:
        assert sub in result.stdout, f"subcommand {sub} not in --help"
