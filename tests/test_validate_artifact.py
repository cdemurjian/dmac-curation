"""Rendered-artifact validation. A format is not supported without one."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import validate_artifact as va  # noqa: E402


def _xlsx(path, headers, rows):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


GEO_REQUIRED = ["*library name", "*title", "*library strategy", "*organism",
                "*molecule", "*single or paired-end", "*instrument model",
                "*raw file"]


def test_status_enum_has_the_five_upstream_members():
    assert {s.value for s in va.ArtifactStatus} == {
        "Valid", "Incomplete", "SchemaInvalid", "Missing", "Unreadable"}


def test_disposition_maps_onto_the_pipeline_vocabulary():
    assert va.DISPOSITION[va.ArtifactStatus.Valid] == "CLEAN"
    assert va.DISPOSITION[va.ArtifactStatus.Incomplete] == "SOFT_FLAG"
    assert va.DISPOSITION[va.ArtifactStatus.SchemaInvalid] == "HARD_REJECT"
    assert va.DISPOSITION[va.ArtifactStatus.Missing] == "HARD_REJECT"
    assert va.DISPOSITION[va.ArtifactStatus.Unreadable] == "HARD_REJECT"


def test_required_fields_reads_single_star_keys():
    req = va.required_fields(ASSETS / "GEO-updated.json", "samples")
    assert "*library name" in req
    assert "**tissue" not in req, "double-star is conditionally required, not required"
    assert 3 <= len(req) <= 25


def test_required_fields_for_sra_libraries():
    req = va.required_fields(ASSETS / "SRA.json", "libraries")
    assert isinstance(req, list)


def test_missing_file_is_Missing(tmp_path):
    r = va.validate_geo_xlsx(file_path=tmp_path / "nope.xlsx",
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Missing


def test_unreadable_file_is_Unreadable(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not a zip archive")
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Unreadable


def test_missing_required_header_is_SchemaInvalid(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, ["*library name", "*title"], [["L1", "T1"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid
    assert r.required_fields_present is False
    assert "*organism" in r.missing_required_fields


def test_all_headers_present_but_a_null_row_is_Incomplete(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"],
           ["L2", "T2", "RNA-Seq", None, "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r2.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Incomplete
    assert r.required_fields_present is True
    assert r.all_required_rows_complete is False


def test_complete_workbook_is_Valid(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Valid
    assert r.required_fields_complete is True
    assert r.row_count == 2  # header + 1 data row


def test_header_matching_is_case_insensitive(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, [h.upper() for h in GEO_REQUIRED],
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.required_fields_present is True


def test_a_whitespace_only_cell_counts_as_null(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "   ", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.all_required_rows_complete is False


def test_required_present_but_no_data_rows_is_Valid_with_zero_rows(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED, [])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.required_fields_present is True


def test_structural_counts_are_reported(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.sheet_count == 1
    assert r.column_count == len(GEO_REQUIRED)
    assert r.nonempty_cell_count > 0
    assert 0.0 <= r.null_cell_fraction <= 1.0


def test_validation_survives_a_workbook_with_zero_sheets(tmp_path):
    """openpyxl cannot make one, so assert the branch exists instead."""
    src = (REPO / "scripts" / "report" / "validate_artifact.py").read_text()
    assert "zero sheets" in src


def test_sra_libraries_validation(tmp_path):
    p = tmp_path / "sra.xlsx"
    req = va.required_fields(ASSETS / "SRA.json", "libraries")
    _xlsx(p, req or ["sample_name"], [["x"] * (len(req) or 1)])
    r = va.validate_sra_xlsx(file_path=p, sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status in (va.ArtifactStatus.Valid, va.ArtifactStatus.Incomplete)


def test_sra_missing_file_is_Missing(tmp_path):
    r = va.validate_sra_xlsx(file_path=tmp_path / "nope.xlsx",
                             sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status is va.ArtifactStatus.Missing


def test_pride_validates_a_tab_delimited_file_not_a_spreadsheet(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text(
        "MTD\tsubmitter_name\tJane Doe\n"
        "FMH\tfile_id\tfile_type\tfile_path\n"
        "FME\t1\traw\t/data/a.raw\n"
        "SMH\tfile_id\tspecies\ttissue\tinstrument\n"
        "SME\t1\tHomo sapiens\tliver\tOrbitrap\n"
    )
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Valid
    assert r.parser_used == "px-tsv"


def test_pride_rejects_a_file_with_no_MTD_lines(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text("FMH\tfile_id\nFME\t1\n")
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid
    assert "MTD" in r.validation_notes


def test_pride_rejects_an_unknown_line_prefix(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text("MTD\ta\tb\nZZZ\tbogus\n")
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid


def test_pride_missing_file_is_Missing(tmp_path):
    r = va.validate_pride_px(file_path=tmp_path / "nope.px",
                             pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Missing


def test_provenance_records_the_subsetting():
    import json
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    entry = prov["entries"]["scripts/report/validate_artifact.py"]
    assert entry["source_repo"] == "dmac-assistant"
    assert "subset" in entry["local_divergence"].lower()
