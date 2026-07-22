"""Phase 10's GEO route delegates its build to report mode."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEPOSIT = REPO / "commands" / "curate-deposit.md"
PHASES = REPO / "skills" / "curation" / "PHASES.md"


def _geo_route() -> str:
    text = DEPOSIT.read_text()
    return text.split("### `/curate-deposit geo", 1)[1].split("### ", 1)[0]


def test_geo_route_delegates_the_build():
    route = _geo_route()
    assert "/curate-report GEO" in route


def test_geo_route_no_longer_invokes_the_renderer_directly():
    """Two GEO paths is the exact divergence the spec warns against."""
    route = _geo_route()
    assert "geo_build_xlsx.py" not in route


def test_geo_route_no_longer_names_the_phantom_input():
    """Nothing has ever produced BULK_filled.json."""
    assert "BULK_filled.json" not in DEPOSIT.read_text()


def test_geo_route_keeps_upload_and_backfill():
    route = _geo_route()
    assert "upload_geo_ncftp.sh" in route
    assert "apply_geo_accessions.py" in route


def test_geo_route_explains_the_ordering():
    route = _geo_route()
    assert "before" in route.lower()
    assert "accession" in route.lower()


def test_phases_records_the_delegation():
    text = PHASES.read_text()
    section = text.split("## Phase 10 ", 1)[1].split("\n## ", 1)[0]
    assert "/curate-report GEO" in section
    assert "dead end" in section.lower()


def test_only_one_geo_build_path_exists_in_the_docs():
    blob = DEPOSIT.read_text() + PHASES.read_text()
    assert blob.count("geo_build_xlsx.py") <= 1, (
        "the renderer should be named once, by report mode's docs")
