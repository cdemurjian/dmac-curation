"""Test inspect_workbook.py against a fixture xlsx."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "inspect_workbook.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.xlsx"


def test_inspect_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Samples" in result.stdout
    assert "Instructions" in result.stdout


def test_inspect_with_sheet_filter():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE), "--sheet", "Samples", "--sample", "2"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "RNA-260527KAM-1" in result.stdout
    assert "RNA-260527KAM-2" in result.stdout
