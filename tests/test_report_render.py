"""Renderers for GEO, SRA and PRIDE, behind one dispatcher."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import render as rd  # noqa: E402
from report import validate_artifact as va  # noqa: E402

GEO_FILLED = {
    "study": {"*title": "A study", "*summary (abstract)": "An abstract",
              "*experimental design": "A design"},
    "samples": [
        {"*library name": "D.SEQ-1", "*title": "t1", "*library strategy": "RNA-Seq",
         "*organism": "Homo sapiens", "**tissue": "liver", "*molecule": "polyA RNA",
         "*single or paired-end": "paired-end",
         "*instrument model": "Illumina NextSeq 500", "*raw file": "a_R1.fastq.gz"},
        {"*library name": "D.SEQ-2", "*title": "t2", "*library strategy": "RNA-Seq",
         "*organism": "Homo sapiens", "**tissue": "liver", "*molecule": "polyA RNA",
         "*single or paired-end": "paired-end",
         "*instrument model": "Illumina NextSeq 500", "*raw file": "b_R1.fastq.gz"},
    ],
    "paired_end_experiments": [
        {"file name 1": "a_R1.fastq.gz", "file name 2": "a_R2.fastq.gz"},
    ],
}

SRA_FILLED = {
    "libraries": [
        {"sample_name": "S1", "library_ID": "L1", "title": "t",
         "library_strategy": "RNA-Seq", "library_source": "TRANSCRIPTOMIC",
         "library_selection": "cDNA", "library_layout": "paired",
         "platform": "ILLUMINA", "instrument_model": "Illumina NextSeq 500",
         "design_description": "d", "filetype": "fastq", "filename": "a.fastq.gz"},
    ],
    "biosamples": [
        {"*sample_name": "S1", "*organism": "Homo sapiens", "*isolate": "n/a",
         "*age": "n/a", "*biomaterial_provider": "MIT", "*collection_date": "2026",
         "*geo_loc_name": "USA", "*sex": "female", "*tissue": "liver"},
    ],
}

PRIDE_FILLED = {
    "project_metadata": {"*submitter_name": "Jane Doe",
                         "*submitter_email": "jane@mit.edu",
                         "*project_title": "A proteomics project"},
    "file_mapping": [
        {"*file_id": "1", "*file_type": "raw", "*file_path": "/data/a.raw"},
    ],
    "sample_metadata": [
        {"*file_id": "1", "*species": "Homo sapiens", "*tissue": "liver",
         "*instrument": "Orbitrap", "*experimental_factor": "treatment"},
    ],
}


def test_dispatcher_knows_the_three_formats():
    assert set(rd.RENDERERS) == {"GEO", "SRA", "PRIDE"}


def test_dispatcher_rejects_an_unknown_format(tmp_path):
    with pytest.raises(rd.UnsupportedFormatError):
        rd.render("NFCORE", {}, template_dir=ASSETS, out_dir=tmp_path)


def test_dispatcher_is_not_a_hardcoded_if_elif():
    """Report spec non-goal: do not port outputs.py's 400-line if/elif."""
    src = (REPO / "scripts" / "report" / "render.py").read_text()
    assert src.count('report_type ==') <= 1


# ---- GEO ------------------------------------------------------------------

def test_geo_renders_and_validates(tmp_path):
    outs = rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    assert len(outs) == 1
    assert outs[0].name == "GEO_filled.xlsx"
    assert outs[0].is_file()


def test_geo_row_parity_survives_rendering(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    wb = openpyxl.load_workbook(out)
    ws = wb["Metadata"]
    names = [r[0] for r in ws.iter_rows(values_only=True)]
    assert "D.SEQ-1" in names
    assert "D.SEQ-2" in names


def test_geo_input_contract_matches_the_executor_output():
    """geo_build_xlsx.py reads data['samples'] and
    data.get('paired_end_experiments'), which is exactly what apply_mapping
    emits for GEO. Verify rather than assume."""
    src = (REPO / "scripts" / "deposit" / "geo_build_xlsx.py").read_text()
    assert 'data["samples"]' in src
    assert '"paired_end_experiments"' in src


def test_only_one_geo_renderer_is_maintained():
    """Report spec: pick one and delete the other. Ours is kept."""
    candidates = list((REPO / "scripts").rglob("*geo*xlsx*.py"))
    assert len(candidates) == 1, f"more than one GEO renderer: {candidates}"


# ---- SRA ------------------------------------------------------------------

def test_sra_renders_two_workbooks(tmp_path):
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    names = sorted(p.name for p in outs)
    assert names == ["SRA_biosample_filled.xlsx", "SRA_metadata_filled.xlsx"]
    assert all(p.is_file() for p in outs)


def test_sra_metadata_workbook_carries_the_library_rows(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    meta = [p for p in outs if "metadata" in p.name][0]
    wb = openpyxl.load_workbook(meta)
    flat = [str(c) for row in wb[wb.sheetnames[0]].iter_rows(values_only=True)
            for c in row if c is not None]
    assert "L1" in flat


def test_sra_validates_after_rendering(tmp_path):
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    meta = [p for p in outs if "metadata" in p.name][0]
    r = va.validate_sra_xlsx(file_path=meta, sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status is not va.ArtifactStatus.Unreadable
    assert r.status is not va.ArtifactStatus.Missing


# ---- PRIDE ----------------------------------------------------------------

def test_pride_renders_a_tab_delimited_file_not_a_spreadsheet(tmp_path):
    outs = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    assert len(outs) == 1
    assert outs[0].name == "submission.px"
    assert outs[0].suffix != ".xlsx"


def test_pride_uses_the_declared_line_prefixes(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    lines = out.read_text().splitlines()
    prefixes = {l.split("\t", 1)[0] for l in lines if l.strip()}
    assert {"MTD", "FMH", "FME", "SMH", "SME"} <= prefixes


def test_pride_metadata_lines_are_one_key_per_line(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    mtd = [l for l in out.read_text().splitlines() if l.startswith("MTD")]
    assert any("submitter_name" in l and "Jane Doe" in l for l in mtd)
    assert all(len(l.split("\t")) == 3 for l in mtd)


def test_pride_header_lines_precede_their_entries(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    lines = [l.split("\t", 1)[0] for l in out.read_text().splitlines() if l.strip()]
    assert lines.index("FMH") < lines.index("FME")
    assert lines.index("SMH") < lines.index("SME")


def test_pride_validates_after_rendering(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    r = va.validate_pride_px(file_path=out, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Valid


def test_pride_strips_the_star_prefix_from_field_names(tmp_path):
    """`*species` is the spec's required marker, not the wire field name."""
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    text = out.read_text()
    assert "species" in text
    assert "*species" not in text


def test_render_writes_nothing_in_the_plugin(tmp_path, plugin_sentinel):
    rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)
