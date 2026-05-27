"""Smoke tests: --help works for each deposit/backfill script."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

PY_SCRIPTS = [
    "stage_zenodo.py",
    "apply_zenodo_links.py",
    "apply_geo_accessions.py",
    "apply_omero_ids.py",
    "review_metadata_vs_uploads.py",
    "deposit/geo_build_xlsx.py",
]


def test_each_help_runs():
    for name in PY_SCRIPTS:
        path = SCRIPTS_DIR / name
        assert path.exists(), f"missing {path}"
        result = subprocess.run(
            ["uv", "run", "--script", str(path), "--help"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"{name}: stderr: {result.stderr}"


def test_upload_geo_ncftp_executable():
    path = SCRIPTS_DIR / "upload_geo_ncftp.sh"
    assert path.exists()
    assert path.stat().st_mode & 0o111, "upload_geo_ncftp.sh should be executable"
