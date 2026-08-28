"""GEO / SRA / PRIDE requirements, read from the templates report mode vendors.

These files already ship in context/report_templates/ and schema mode has never
opened them. They are the only source that says which fields a submission is
REJECTED without, and they carry the vocabularies those repositories enforce.

A leading `*` marks required; `**` marks conditionally required (GEO uses it for
`**tissue`, `**cell line`, `**cell type`; PRIDE for `**file_mapping`).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import repositories as sr  # noqa: E402

GEO_DOC = {
    "study": {"*title": None, "contributor": []},
    "samples": [{"*library strategy": None, "*organism": None,
                 "**tissue": None, "genotype": None}],
    "protocols": {"*extract protocol": None, "growth protocol": None},
}


def test_every_known_repository_has_a_file():
    assert set(sr.REPOSITORY_FILES) == {"GEO", "SRA", "PRIDE"}


def test_each_repository_file_actually_exists():
    for name in sr.REPOSITORY_FILES:
        assert sr.load_template(name)


def test_required_fields_collects_star_prefixed_keys():
    out = sr.required_fields(GEO_DOC, "GEO")
    assert {f.name for f in out} == {
        "title", "library strategy", "organism", "tissue", "extract protocol"}


def test_required_fields_strips_the_marker_from_the_name():
    out = sr.required_fields(GEO_DOC, "GEO")
    assert not any(f.name.startswith("*") for f in out)


def test_a_double_star_field_is_conditional_not_required():
    out = {f.name: f for f in sr.required_fields(GEO_DOC, "GEO")}
    assert out["tissue"].conditional is True
    assert out["tissue"].required is False
    assert out["organism"].required is True
    assert out["organism"].conditional is False


def test_required_fields_records_the_section_it_came_from():
    out = {f.name: f for f in sr.required_fields(GEO_DOC, "GEO")}
    assert out["title"].section == "study"
    assert out["library strategy"].section == "samples"
    assert out["extract protocol"].section == "protocols"


def test_unmarked_fields_are_not_returned():
    names = {f.name for f in sr.required_fields(GEO_DOC, "GEO")}
    assert "contributor" not in names and "genotype" not in names


def test_required_fields_tags_the_repository():
    assert all(f.repository == "GEO" for f in sr.required_fields(GEO_DOC, "GEO"))


def test_the_real_geo_template_declares_its_known_required_fields():
    out = {f.name for f in sr.required_fields(sr.load_template("GEO"), "GEO")}
    assert {"library strategy", "organism", "genome build/assembly"} <= out


def test_the_real_sra_template_declares_its_known_required_fields():
    out = {f.name for f in sr.required_fields(sr.load_template("SRA"), "SRA")}
    assert {"sample_name", "organism", "collection_date"} <= out


def test_a_malformed_document_yields_nothing_rather_than_raising():
    assert sr.required_fields({"study": "not a dict"}, "GEO") == []
