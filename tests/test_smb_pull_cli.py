"""Smoke test for smb_pull.py — verify --help and key flags are advertised without credentials."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smb_pull.py"


def test_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    for flag in ["--dry-run", "--resume", "--from-manifest", "--rows"]:
        assert flag in result.stdout, f"flag {flag} not in --help output"
