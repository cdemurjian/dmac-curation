"""Report-mode vendored assets and their provenance.

Stage G begins by vendoring six field-spec templates from chat_nextseek into
context/report_templates/, each with a PROVENANCE.json entry (source repo/path/
commit/date/sha256). The plugin must never hold an unattributed copy of external
data -- the sampletypes_db.json-in-three-places problem the plan warns about.

These tests also pin three findings the report-mode review approved full scope on:

1. PRIDE is NOT a spreadsheet. pride.json declares a tab-delimited ProteomeXchange
   Submission Summary File (submission.px), not an xlsx. No pride.xlsx is vendored.
2. SRA has TWO row-bearing sections -- `libraries` (feeds SRA_metadata.xlsx) and
   `biosamples` (feeds SRA_biosample.xlsx). Both templates ship.
3. chat_nextseek's and dmac-assistant's GEO-updated.json copies were byte-identical,
   so report-spec open question 1 ("which is authoritative?") is moot; the choice is
   arbitrary and the provenance record says so.
"""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO / "context" / "report_templates"
PROVENANCE_PATH = REPO / "context" / "PROVENANCE.json"

# The six assets vendored by this task. geo.json is deliberately excluded --
# GEO-updated.json supersedes it (it adds the SRA-derived controlled vocabulary).
VENDORED_ASSETS = (
    "GEO-updated.json",
    "GEO_template.xlsx",
    "SRA.json",
    "SRA_metadata.xlsx",
    "SRA_biosample.xlsx",
    "pride.json",
)

PROVENANCE_FIELDS = (
    "source_repo", "source_path", "commit_sha",
    "vendored_date", "local_divergence", "sha256",
)


def _prov_key(asset: str) -> str:
    return f"context/report_templates/{asset}"


def _load_provenance() -> dict:
    return json.loads(PROVENANCE_PATH.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_six_assets_were_vendored():
    for asset in VENDORED_ASSETS:
        assert (TEMPLATES_DIR / asset).is_file(), f"missing vendored asset: {asset}"


def test_superseded_geo_json_was_not_vendored():
    """geo.json is the pre-CV spec; GEO-updated.json replaces it. Do not carry both."""
    assert not (TEMPLATES_DIR / "geo.json").exists()


def test_pride_spec_declares_a_tab_delimited_output_not_a_spreadsheet():
    spec = json.loads((TEMPLATES_DIR / "pride.json").read_text())
    fmt = spec["format"]
    assert fmt["field_separator"] == "tab"
    assert "tab-delimited" in fmt["output_type"]
    prefixes = fmt["line_prefixes"]
    assert prefixes == {
        "metadata": "MTD",
        "file_mapping_header": "FMH",
        "file_mapping_entry": "FME",
        "sample_metadata_header": "SMH",
        "sample_metadata_entry": "SME",
        "comment": "COM",
    }


def test_no_pride_xlsx_was_vendored():
    """PRIDE is submission.px, not a workbook. chat_nextseek's e2e catalog asserting
    `pride.xlsx` is asserting the wrong artifact type; do not inherit that shape."""
    assert not (TEMPLATES_DIR / "pride.xlsx").exists()
    assert list(TEMPLATES_DIR.glob("pride*.xlsx")) == []


def test_sra_spec_has_two_row_bearing_sections():
    spec = json.loads((TEMPLATES_DIR / "SRA.json").read_text())
    assert "libraries" in spec, "SRA.json must carry the `libraries` section"
    assert "biosamples" in spec, "SRA.json must carry the `biosamples` section"
    # Both row-bearing sections have a companion rendered template.
    assert (TEMPLATES_DIR / "SRA_metadata.xlsx").is_file()   # feeds `libraries`
    assert (TEMPLATES_DIR / "SRA_biosample.xlsx").is_file()  # feeds `biosamples`


def test_geo_and_dmac_assistant_copies_were_identical():
    """Open question 1 is moot: the two GEO-updated.json copies were byte-identical,
    so which repo is authoritative does not matter. The provenance record says so."""
    entry = _load_provenance()["entries"][_prov_key("GEO-updated.json")]
    assert "identical" in entry["local_divergence"].lower()


def test_pride_provenance_notes_it_is_not_a_spreadsheet():
    entry = _load_provenance()["entries"][_prov_key("pride.json")]
    note = entry["local_divergence"].lower()
    assert "tab" in note and "xlsx" in note


def test_every_asset_has_a_provenance_entry():
    entries = _load_provenance()["entries"]
    for asset in VENDORED_ASSETS:
        key = _prov_key(asset)
        assert key in entries, f"no provenance entry for {asset}"
        entry = entries[key]
        for field in PROVENANCE_FIELDS:
            assert field in entry, f"{key} provenance missing field {field}"
        assert entry["source_repo"] == "chat_nextseek"
        assert entry["commit_sha"]


def test_provenance_sha256_matches_the_file_on_disk():
    entries = _load_provenance()["entries"]
    for asset in VENDORED_ASSETS:
        entry = entries[_prov_key(asset)]
        assert entry["sha256"] == _sha256(TEMPLATES_DIR / asset), (
            f"provenance sha256 for {asset} does not match the file on disk"
        )
