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
    # Summary line shows the row count (3 rows = header + 2 data)
    assert "3 rows" in result.stdout
    # Headers section is printed even without --sample
    assert "Headers" in result.stdout
    # Without --sample, sample data rows should NOT appear
    assert "RNA-260527KAM-1" not in result.stdout


def test_inspect_with_sheet_filter():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE), "--sheet", "Samples", "--sample", "2"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "RNA-260527KAM-1" in result.stdout
    assert "RNA-260527KAM-2" in result.stdout
    # Filter active — Instructions sheet should not have a detail block
    assert "### Sheet: Instructions" not in result.stdout


def test_inspect_unknown_sheet_returns_nonzero():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE), "--sheet", "DoesNotExist"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "not found" in result.stdout or "not found" in result.stderr
