"""Smoke test: submit.py --help runs (interactive tool, ported verbatim)."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fdh" / "submit.py"


def test_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = result.stdout + result.stderr
    assert "--resume" in out and "--step" in out
