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


# --- vocabularies and applicability ----------------------------------------

D_SEQ = {"SampleType": "D.SEQ",
         "Associated Assay Parents": "Short Read Sequencing",
         "Tags": "sequencing data, FASTQ, raw reads, NGS data"}
D_MSP = {"SampleType": "D.MSP",
         "Associated Assay Parents": "Mass Spectrometry Proteomics",
         "Tags": "mass spectrometry data, proteomics data"}
D_VIA = {"SampleType": "D.VIA",
         "Associated Assay Parents": "Cell Viability Assay",
         "Tags": "viability data, cell viability, cytotoxicity data"}


def test_controlled_vocabularies_reads_the_top_level_block():
    doc = {"controlled_vocabulary": {"library_strategy": ["WGS", "RNA-Seq"],
                                     "authority": "a prose note"}}
    assert sr.controlled_vocabularies(doc) == {"library_strategy": ["WGS", "RNA-Seq"]}


def test_controlled_vocabularies_drops_non_list_entries():
    """`authority` is a prose string, not a vocabulary."""
    doc = {"controlled_vocabulary": {"authority": "mined from the template"}}
    assert sr.controlled_vocabularies(doc) == {}


def test_controlled_vocabularies_falls_back_to_the_schema_block():
    """PRIDE nests its vocabularies under `schema`, not at the top level."""
    doc = {"schema": {"controlled_vocabularies": {"modification": ["Oxidation"]}}}
    assert sr.controlled_vocabularies(doc) == {"modification": ["Oxidation"]}


def test_controlled_vocabularies_of_a_document_with_none():
    assert sr.controlled_vocabularies({"study": {}}) == {}


def test_the_real_geo_template_carries_its_enforced_vocabularies():
    cv = sr.controlled_vocabularies(sr.load_template("GEO"))
    assert len(cv["library_strategy"]) == 41
    assert len(cv["instrument_model_flat"]) == 82
    assert "RNA-Seq" in cv["library_strategy"]


def test_a_sequencing_type_maps_to_geo_and_sra():
    assert sr.repositories_for(D_SEQ) == ("GEO", "SRA")


def test_a_proteomics_type_maps_to_pride():
    assert sr.repositories_for(D_MSP) == ("PRIDE",)


def test_a_type_no_public_repository_covers_maps_to_nothing():
    """D.VIA is thin by fact, not by failure. The review must be able to say so."""
    assert sr.repositories_for(D_VIA) == ()


def test_matching_is_case_insensitive():
    assert sr.repositories_for({"Associated Assay Parents": "SHORT READ SEQUENCING",
                                "Tags": ""}) == ("GEO", "SRA")


def test_a_record_missing_both_fields_maps_to_nothing():
    assert sr.repositories_for({}) == ()
