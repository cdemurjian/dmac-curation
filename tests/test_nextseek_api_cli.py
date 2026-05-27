"""Smoke test: nextseek_api.py --help runs without errors."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "nextseek_api.py"


def test_help_runs():
    """--help should succeed and mention fetch-assays subcommand."""
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "fetch-assays" in result.stdout or "fetch-assays" in result.stderr


def test_fetch_assays_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "fetch-assays", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "project-id" in result.stdout or "project-id" in result.stderr


def test_validate_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "validate", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "project-id" in result.stdout or "project-id" in result.stderr
