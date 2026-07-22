"""Every input adapter emits the identical normalized shape."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402


def _xlsx(path, sheets):
    """sheets: {name: (headers, rows)}"""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    first = True
    for name, (headers, rows) in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        ws.title = name
        first = False
        ws.append(headers)
        for r in rows:
            ws.append(r)
    wb.save(path)


API_RESPONSE = {
    "data": {
        "data": [
            {"samples": [
                {"metadata": {"UID": "D.SEQ-1", "SampleType": "D.SEQ",
                              "Parent": "RNA-1", "Name": "seq1"}},
                {"metadata": {"UID": "RNA-1", "SampleType": "RNA",
                              "Parent": "TIS-1", "Name": "rna1"}},
            ]},
            {"samples": [
                {"metadata": {"UID": "TIS-1", "SampleType": "TIS",
                              "Parent": None, "Tissue": "liver"}},
            ]},
        ]
    }
}


def test_adapt_uids_walks_the_five_level_response():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda uids: API_RESPONSE)
    assert len(got.samples) == 3
    by_uid = ad.index_by_uid(got)
    assert by_uid["D.SEQ-1"].sample_type == "D.SEQ"
    assert by_uid["D.SEQ-1"].parent == "RNA-1"
    assert by_uid["TIS-1"].metadata["Tissue"] == "liver"


def test_adapt_uids_records_its_source():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda uids: API_RESPONSE)
    assert got.source["adapter"] == "uids"
    assert got.source["uids"] == ["D.SEQ-1"]


def test_adapt_uids_with_no_fetcher_returns_empty():
    """Enrichment is additive, never required."""
    got = ad.adapt_uids(["D.SEQ-1"], fetch=None)
    assert got.samples == []


def test_adapt_retrieve_txt(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("D.SEQ-1\n\nD.SEQ-2\n")
    got = ad.adapt_retrieve_txt(p, fetch=lambda uids: API_RESPONSE)
    assert got.source["uids"] == ["D.SEQ-1", "D.SEQ-2"]


def test_adapt_nextseek_workbook_reads_per_type_sheets(tmp_path):
    p = tmp_path / "Lab_AllMetadata_260721.xlsx"
    _xlsx(p, {
        "D.SEQ": (["UID", "Parent", "LibraryLayout"],
                  [["D.SEQ-1", "RNA-1", "paired"]]),
        "RNA": (["UID", "Parent"], [["RNA-1", "TIS-1"]]),
    })
    got = ad.adapt_nextseek_workbook(p)
    by_uid = ad.index_by_uid(got)
    assert by_uid["D.SEQ-1"].sample_type == "D.SEQ"
    assert by_uid["D.SEQ-1"].parent == "RNA-1"
    assert by_uid["D.SEQ-1"].metadata["LibraryLayout"] == "paired"


def test_adapt_nextseek_workbook_infers_type_from_uid_when_no_column(tmp_path):
    p = tmp_path / "x_AllMetadata.xlsx"
    _xlsx(p, {"Sheet1": (["UID", "Parent"], [["D.SEQ-260721KAM-3", "RNA-1"]])})
    got = ad.adapt_nextseek_workbook(p)
    assert got.samples[0].sample_type == "D.SEQ"


def test_adapt_curated_sheet_parses_json_metadata(tmp_path):
    """The flat Arm{X}.xlsx shape: the payload lives in json_metadata."""
    p = tmp_path / "ArmA.xlsx"
    meta = json.dumps({"UID": "D.SEQ-1", "Parent": "RNA-1",
                       "LibraryLayout": "paired", "Notes": "n"})
    _xlsx(p, {"Samples": (["uid", "sampletype", "parent", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "RNA-1", meta]])})
    got = ad.adapt_curated_sheet(p)
    s = got.samples[0]
    assert s.uid == "D.SEQ-1"
    assert s.sample_type == "D.SEQ"
    assert s.parent == "RNA-1"
    assert s.metadata["LibraryLayout"] == "paired"


def test_adapt_curated_sheet_works_before_upload(tmp_path):
    """No API call, no network. That is the point of this adapter."""
    p = tmp_path / "ArmA.xlsx"
    _xlsx(p, {"Samples": (["uid", "sampletype", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "{}"]])})
    got = ad.adapt_curated_sheet(p)
    assert got.source["adapter"] == "curated_sheet"
    assert len(got.samples) == 1


def test_adapt_curated_sheet_survives_malformed_json(tmp_path):
    p = tmp_path / "ArmA.xlsx"
    _xlsx(p, {"Samples": (["uid", "sampletype", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "{not json"]])})
    got = ad.adapt_curated_sheet(p)
    assert got.samples[0].uid == "D.SEQ-1"
    assert got.samples[0].metadata.get("_json_metadata_error")


def test_adapt_curated_sheet_survives_non_dict_json(tmp_path):
    """Valid JSON that is not an object degrades, it does not crash the sheet."""
    p = tmp_path / "ArmA.xlsx"
    _xlsx(p, {"Samples": (["uid", "sampletype", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "[1,2,3]"]])})
    got = ad.adapt_curated_sheet(p)
    assert got.samples[0].uid == "D.SEQ-1"
    assert got.samples[0].metadata.get("_json_metadata_error")


def test_adapt_tabular_csv(tmp_path):
    p = tmp_path / "anything.csv"
    p.write_text("SampleName,Organism\nS1,Homo sapiens\nS2,Homo sapiens\n")
    got = ad.adapt_tabular(p, sample_type="D.SEQ")
    assert len(got.samples) == 2
    assert got.samples[0].metadata["Organism"] == "Homo sapiens"
    assert got.samples[0].sample_type == "D.SEQ"


def test_adapt_tabular_xlsx(tmp_path):
    p = tmp_path / "anything.xlsx"
    _xlsx(p, {"Sheet1": (["SampleName", "Organism"], [["S1", "Homo sapiens"]])})
    got = ad.adapt_tabular(p)
    assert got.samples[0].metadata["SampleName"] == "S1"


def test_every_adapter_emits_the_identical_shape(tmp_path):
    """The contract that makes downstream steps adapter-agnostic."""
    wb = tmp_path / "m_AllMetadata.xlsx"
    _xlsx(wb, {"D.SEQ": (["UID", "Parent"], [["D.SEQ-1", "RNA-1"]])})
    arm = tmp_path / "ArmA.xlsx"
    _xlsx(arm, {"Samples": (["uid", "sampletype", "parent", "json_metadata"],
                            [["D.SEQ-1", "D.SEQ", "RNA-1", "{}"]])})
    csv = tmp_path / "x.csv"
    csv.write_text("UID,Parent\nD.SEQ-1,RNA-1\n")

    for got in (ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE),
                ad.adapt_nextseek_workbook(wb),
                ad.adapt_curated_sheet(arm),
                ad.adapt_tabular(csv)):
        assert isinstance(got, ad.NormalizedInput)
        assert isinstance(got.samples, list)
        assert "adapter" in got.source
        for s in got.samples:
            assert isinstance(s, ad.NormalizedSample)
            assert isinstance(s.metadata, dict)
            assert s.parent is None or isinstance(s.parent, str)


def test_detect_adapter_by_filename(tmp_path):
    assert ad.detect_adapter(["D.SEQ-1", "RNA-2"]) == "uids"
    assert ad.detect_adapter(tmp_path / "RETRIEVE.TXT") == "retrieve_txt"
    assert ad.detect_adapter(tmp_path / "Lab_AllMetadata_260721.xlsx") == "nextseek_workbook"
    assert ad.detect_adapter(tmp_path / "ArmA.xlsx") == "curated_sheet"
    assert ad.detect_adapter(tmp_path / "whatever.csv") == "tabular"
    assert ad.detect_adapter(tmp_path / "whatever.xlsx") == "tabular"


def test_resolve_via_lineage_walks_upward():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "Tissue") == "liver"


def test_resolve_via_lineage_prefers_the_leaf_value():
    """Leaf-wins: an existing value on the sample is not overwritten."""
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    by_uid["D.SEQ-1"].metadata["Tissue"] = "tumor"
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "Tissue") == "tumor"


def test_resolve_via_lineage_returns_none_when_unreachable():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "CellLine") is None


def test_resolve_via_lineage_survives_a_parent_cycle():
    a = ad.NormalizedSample(sample_type="A", uid="A-1", metadata={}, parent="B-1")
    b = ad.NormalizedSample(sample_type="B", uid="B-1", metadata={}, parent="A-1")
    by_uid = {"A-1": a, "B-1": b}
    assert ad.resolve_via_lineage(a, by_uid, "Tissue") is None


def test_resolve_via_lineage_handles_semicolon_joined_multi_parents():
    leaf = ad.NormalizedSample(sample_type="OOC", uid="OOC-1", metadata={},
                               parent="CEL-1; CEL-2")
    cel2 = ad.NormalizedSample(sample_type="CEL", uid="CEL-2",
                               metadata={"CellLine": "MCF-7"}, parent=None)
    by_uid = {"OOC-1": leaf, "CEL-2": cel2}
    assert ad.resolve_via_lineage(leaf, by_uid, "CellLine") == "MCF-7"
