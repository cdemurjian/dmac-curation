"""The lazy, cwd-only field dictionary (schema spec)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import dictionary as sd  # noqa: E402
from schema import field_index as fi  # noqa: E402


def _workbook(path: Path, sheet: str, headers: list[str], rows: list[list]):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_observe_values_collects_distinct_values(tmp_path):
    wb = tmp_path / "master.xlsx"
    _workbook(wb, "D.VIA", ["UID", "Instrument", "Timepoint"],
              [["A-1", "BioTek Synergy H1", "24h"],
               ["A-2", "BioTek Synergy H1", "48h"],
               ["A-3", "Tecan Spark", "24h"]])
    out = sd.observe_values([wb], {"Instrument", "Timepoint"})
    assert out["Instrument"] == ["BioTek Synergy H1", "Tecan Spark"]
    assert out["Timepoint"] == ["24h", "48h"]


def test_observe_values_ignores_fields_not_asked_for(tmp_path):
    wb = tmp_path / "m.xlsx"
    _workbook(wb, "S", ["UID", "Instrument"], [["A-1", "X"]])
    assert "UID" not in sd.observe_values([wb], {"Instrument"})


def test_observe_values_skips_blanks_and_placeholders(tmp_path):
    wb = tmp_path / "m.xlsx"
    _workbook(wb, "S", ["Instrument"],
              [["BioTek"], [None], [""], ["*** PLACEHOLDER: unknown ***"]])
    assert sd.observe_values([wb], {"Instrument"}) == {"Instrument": ["BioTek"]}


def test_observe_values_reads_every_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb_path = tmp_path / "m.xlsx"
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "D.VIA"
    a.append(["Instrument"])
    a.append(["BioTek"])
    b = wb.create_sheet("D.FLOW")
    b.append(["Instrument"])
    b.append(["Cytek"])
    wb.save(wb_path)
    assert sd.observe_values([wb_path], {"Instrument"}) == {
        "Instrument": ["BioTek", "Cytek"]}


def test_observe_values_on_no_workbooks_returns_empty():
    assert sd.observe_values([], {"Instrument"}) == {}


def test_build_entry_shape():
    usage = fi.FieldUsage(name="Instrument", used_by=["D.VIA", "D.FLOW"])
    e = sd.build_entry("Instrument", usage,
                       observed=["BioTek Synergy H1"],
                       description="Plate reader or analyzer used")
    assert e["used_by"] == ["D.VIA", "D.FLOW"]
    assert e["observed_values"] == ["BioTek Synergy H1"]
    assert e["datatype"] == "string"
    assert e["ontology"] is None
    assert "2 existing usages" in e["provenance"]
    assert "1 observed value" in e["provenance"]


def test_build_entry_ontology_is_always_unconfirmed():
    """schema spec: only a human flips confirmed. The MUS prototype bound
    Strain to NCBITaxon_10090, which is wrong -- NCBITaxon covers species, not
    laboratory strains like C57BL/6J."""
    usage = fi.FieldUsage(name="Strain", used_by=["MUS"])
    e = sd.build_entry("Strain", usage, observed=[],
                       ontology={"iri": "http://purl.obolibrary.org/obo/NCBITaxon_10090",
                                 "label": "Mus musculus", "source": "NCBITaxon"})
    assert e["ontology"]["confirmed"] is False


def test_build_entry_rejects_a_preconfirmed_ontology():
    usage = fi.FieldUsage(name="Strain", used_by=["MUS"])
    e = sd.build_entry("Strain", usage, observed=[],
                       ontology={"iri": "x", "label": "y", "source": "z",
                                 "confirmed": True})
    assert e["ontology"]["confirmed"] is False


def test_merge_dictionary_adds_new_entries():
    merged = sd.merge_dictionary({"A": {"observed_values": ["1"]}},
                                 {"B": {"observed_values": ["2"]}})
    assert set(merged) == {"A", "B"}


def test_merge_dictionary_unions_observed_values():
    merged = sd.merge_dictionary(
        {"A": {"observed_values": ["1", "2"], "used_by": ["X"]}},
        {"A": {"observed_values": ["2", "3"], "used_by": ["X", "Y"]}})
    assert merged["A"]["observed_values"] == ["1", "2", "3"]
    assert merged["A"]["used_by"] == ["X", "Y"]


def test_merge_dictionary_never_downgrades_a_confirmed_ontology():
    """A human confirmed it. A later automated run must not un-confirm it."""
    existing = {"A": {"ontology": {"iri": "i", "label": "l", "source": "s",
                                   "confirmed": True}}}
    new = {"A": {"ontology": {"iri": "i", "label": "l", "source": "s",
                              "confirmed": False}}}
    assert sd.merge_dictionary(existing, new)["A"]["ontology"]["confirmed"] is True


def test_merge_dictionary_keeps_a_human_written_description():
    existing = {"A": {"description": "written by a curator"}}
    new = {"A": {"description": ""}}
    assert sd.merge_dictionary(existing, new)["A"]["description"] == "written by a curator"


def test_dictionary_round_trips_through_disk(tmp_path):
    doc = {"Instrument": {"observed_values": ["BioTek"]}}
    sd.save_dictionary(tmp_path, doc)
    assert sd.load_dictionary(tmp_path) == doc


def test_load_dictionary_on_absent_file_returns_empty(tmp_path):
    assert sd.load_dictionary(tmp_path) == {}


def test_dictionary_is_written_to_cwd_not_the_plugin(tmp_path, plugin_sentinel):
    sd.save_dictionary(tmp_path, {"A": {}})
    assert (tmp_path / "schema" / sd.DICTIONARY_NAME).is_file()


def test_no_prebuilt_dictionary_ships_with_the_plugin():
    """schema spec: lazy and cwd-only. Shipping one would repeat the
    three-copies-of-context problem."""
    assert not (REPO / "context" / "field_dictionary.json").exists()
    assert not (REPO / "schema").exists()
