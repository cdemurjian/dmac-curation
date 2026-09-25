"""Field index and reuse check over the 1118-name sample type catalog."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import field_index as fi  # noqa: E402

CATALOG = [
    {"SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
     "Tags": "viability data, MTS assay, MTT assay, WST-1, CellTiter-Glo",
     "Required Metadata": "UID, Scientist, Parent",
     "Standard Metadata": "Protocol, CellLine, Type",
     "Possible Metadata Fields": "Notes",
     "Associated Assay Parents": "Cell Viability Assay",
     "Parent_SampleTypes": "CEL"},
    {"SampleType": "D.FLOW", "Name": "Flow Data", "Clade": "Raw",
     "Tags": "flow cytometry",
     "Required Metadata": "UID, Scientist, Parent",
     "Standard Metadata": "Protocol, Instrument",
     "Possible Metadata Fields": "Notes, Timepoint",
     "Associated Assay Parents": "Flow Cytometry",
     "Parent_SampleTypes": "CEL"},
    {"SampleType": "MUS", "Name": "Mouse", "Clade": "Organism",
     "Tags": "mouse",
     "Required Metadata": "UID, Scientist",
     "Standard Metadata": "Strain",
     "Possible Metadata Fields": "Notes",
     "Associated Assay Parents": "", "Parent_SampleTypes": ""},
]


def test_load_catalog_reads_the_bundled_file():
    types = fi.load_catalog()
    assert len(types) == 109
    assert all("SampleType" in t for t in types)


def test_build_field_index_counts_usage():
    idx = fi.build_field_index(CATALOG)
    assert idx["UID"].count == 3
    assert sorted(idx["Notes"].used_by) == ["D.FLOW", "D.VIA", "MUS"]
    assert idx["Instrument"].count == 1
    assert idx["Instrument"].used_by == ["D.FLOW"]


def test_build_field_index_covers_all_three_sources():
    idx = fi.build_field_index(CATALOG)
    assert "Scientist" in idx      # Required
    assert "Protocol" in idx       # Standard
    assert "Timepoint" in idx      # Possible


def test_real_catalog_shape_matches_the_spec():
    """Guards the numbers the schema spec reasons from."""
    idx = fi.build_field_index(fi.load_catalog())
    assert len(idx) == 1118
    singletons = [f for f in idx.values() if f.count == 1]
    assert len(singletons) == 901
    assert idx["UID"].count == 109


def test_normalize_field_name_handles_case_underscores_and_plurals():
    assert fi.normalize_field_name("Cell_Line") == "cellline"
    assert fi.normalize_field_name("cellLine") == "cellline"
    assert fi.normalize_field_name("Instruments") == "instrument"
    assert fi.normalize_field_name(" Timepoint ") == "timepoint"


def test_normalize_does_not_over_singularize():
    """'Status' must not become 'Statu'."""
    assert fi.normalize_field_name("Status") == "status"
    assert fi.normalize_field_name("Analysis") == "analysis"


def test_rank_candidates_finds_an_exact_match_first():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("Instrument", idx)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "exact"


def test_rank_candidates_finds_a_normalized_match():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("instruments", idx)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "normalized"


def test_rank_candidates_finds_a_synonym_from_the_dictionary():
    idx = fi.build_field_index(CATALOG)
    dictionary = {"Instrument": {"synonyms": ["PlateReader", "Analyzer"]}}
    out = fi.rank_candidates("PlateReader", idx, dictionary=dictionary)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "synonym"


def test_rank_candidates_does_not_force_match_a_genuinely_novel_name():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("HydrogelStiffnessKPa", idx)
    assert all(c.match_pass != "exact" for c in out)
    assert not out or out[0].name != "HydrogelStiffnessKPa"


def test_rank_candidates_prefers_higher_usage_within_a_pass():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("Note", idx)
    names = [c.name for c in out]
    assert "Notes" in names


def test_rank_candidates_boosts_same_clade():
    idx = fi.build_field_index(CATALOG)
    with_clade = fi.rank_candidates("Instrument", idx, clade="Raw",
                                    catalog=CATALOG)
    assert with_clade[0].name == "Instrument"
    assert "D.FLOW" in with_clade[0].used_by


def test_rank_candidates_respects_limit():
    idx = fi.build_field_index(fi.load_catalog())
    assert len(fi.rank_candidates("Type", idx, limit=3)) <= 3


def test_a_name_on_many_types_is_not_flagged_as_a_defect():
    """schema spec / user correction: `Type` meaning different things on
    different sample types is fine, not a homonym problem."""
    idx = fi.build_field_index(fi.load_catalog())
    assert idx["Type"].count > 1
    assert not hasattr(fi, "split_homonyms")
    assert not hasattr(fi, "propose_rename")


def test_mine_tags_splits_the_tags_column():
    assert fi.mine_tags(CATALOG[0]) == [
        "viability data", "MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"]


def test_mine_tags_on_real_dvia_yields_the_assay_vocabulary():
    rec = fi.type_record(fi.load_catalog(), "D.VIA")
    tags = fi.mine_tags(rec)
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in tags


def test_mine_tags_on_a_type_with_no_tags_returns_empty():
    assert fi.mine_tags({"SampleType": "X"}) == []


def test_type_record_raises_on_unknown_type():
    with pytest.raises(KeyError):
        fi.type_record(CATALOG, "NOPE")


def test_siblings_in_clade_excludes_the_type_itself():
    sibs = fi.siblings_in_clade(CATALOG, "D.VIA")
    assert [s["SampleType"] for s in sibs] == ["D.FLOW"]


# --- the reuse check's word splitter ----------------------------------------
#
# `_words` feeds the semantic pass, which is the last line of defence against
# minting a duplicate. Two bugs made it blind exactly where it matters:
# an uppercase RUN never split, so `QCPlatform` stayed one token and a
# `Platform` query could not see it - on the very type that owns it - and a
# `len(w) > 2` filter deleted real stems, leaving `F_bp` with no words at all.

def test_words_splits_a_leading_acronym_from_the_word_it_qualifies():
    assert fi._words("QCPlatform") == {"qc", "platform"}
    assert fi._words("QCAssay") == {"qc", "assay"}


def test_words_keeps_two_letter_stems():
    assert fi._words("F_bp") == {"bp"}
    assert fi._words("R_bp") == {"bp"}


def test_words_still_splits_ordinary_camel_case():
    assert fi._words("LibraryStrategy") == {"library", "strategy"}
    assert fi._words("File_PrimaryData") == {"file", "primary", "data"}


def test_the_reuse_check_can_now_see_a_field_behind_an_acronym():
    """D.SEQ owns `QCPlatform`; a `Platform` query returned nothing at all."""
    catalog = fi.load_catalog()
    index = fi.build_field_index(catalog)
    names = [c.name for c in fi.rank_candidates("Platform", index,
                                             catalog=catalog, limit=10)]
    assert "QCPlatform" in names


# --- parent lineage ---------------------------------------------------------
#
# `Parent_SampleTypes` was PROSE, not a list, and every naive split was wrong.
# The 2026-05 catalog used four separators - `,` (6 records), ` or ` (15),
# ` and ` (1) and `.` (MUS read 'AB, BAC. CHM') - CEL was missing a comma
# entirely ('CEL, TIS MUS, NHP, PAV'), and splitting on `.` shatters the type
# codes themselves, which contain one. So parents are FOUND by matching known
# codes rather than split out by delimiter.
#
# The curated 2026-09 catalog writes every one of those as a plain `, ` list,
# so the bundled file no longer exercises the messy separators. The tests for
# them therefore carry the old prose as inline fixtures (a project can still
# point `load_catalog` at an older vintage), and one test pins that every
# bundled row parses to exactly its own comma list.

# Every code the prose fixtures below mention, so `parents_of` can find them.
_CODES = ("AB", "ABP", "BAC", "CEL", "CHM", "D.ELSA", "D.SEQ", "DNA", "MUS",
          "NHP", "PAV", "RNA", "SEQ", "TIS")


def _prose_catalog(sampletype: str, parents: str) -> list[dict]:
    rows = [{"SampleType": c} for c in _CODES if c != sampletype]
    return rows + [{"SampleType": sampletype, "Parent_SampleTypes": parents}]


def test_a_single_parent_is_returned():
    catalog = fi.load_catalog()
    assert fi.parents_of(catalog, "D.SEQ") == ["DNA"]


def test_or_separated_parents_are_all_returned():
    catalog = _prose_catalog("DNA", "CEL or RNA or DNA or TIS or BAC")
    assert fi.parents_of(catalog, "DNA") == ["CEL", "RNA", "DNA", "TIS", "BAC"]


def test_mixed_or_and_and_separators():
    catalog = _prose_catalog("D.ELSA", "AB or ABP and CEL or TIS")
    assert fi.parents_of(catalog, "D.ELSA") == ["AB", "ABP", "CEL", "TIS"]


def test_a_missing_comma_does_not_lose_a_parent():
    """CEL read 'CEL, TIS MUS, NHP, PAV' - TIS and MUS share a separator."""
    catalog = _prose_catalog("CEL", "CEL, TIS MUS, NHP, PAV")
    assert fi.parents_of(catalog, "CEL") == ["CEL", "TIS", "MUS", "NHP", "PAV"]


def test_a_period_separator_does_not_shatter_the_codes():
    """MUS read 'AB, BAC. CHM'. Splitting on '.' would also break `D.SEQ`."""
    catalog = _prose_catalog("MUS", "AB, BAC. CHM")
    assert fi.parents_of(catalog, "MUS") == ["AB", "BAC", "CHM"]
    catalog = _prose_catalog("D.ELSA", "D.SEQ. DNA")
    assert fi.parents_of(catalog, "D.ELSA") == ["D.SEQ", "DNA"]


def test_every_bundled_row_parses_to_its_own_comma_list():
    """The curated catalog is `, `-separated; the finder must agree with it.

    Only codes that are real sample types count, which is what `parents_of`
    promises, so a listed parent that is not in the catalog is dropped from
    the expectation too.
    """
    catalog = fi.load_catalog()
    codes = {r["SampleType"] for r in catalog if r.get("SampleType")}
    checked = 0
    for row in catalog:
        raw = row.get("Parent_SampleTypes") or ""
        expected = []
        for part in (p.strip() for p in raw.split(",")):
            if part in codes and part not in expected:
                expected.append(part)
        assert fi.parents_of(catalog, row["SampleType"]) == expected, row["SampleType"]
        checked += bool(expected)
    assert checked >= 90, "the bundled catalog should declare parents on most rows"


def test_a_type_with_no_declared_parents_returns_empty():
    catalog = fi.load_catalog()
    assert fi.parents_of(catalog, "MUS") != []          # sanity: MUS has some
    assert fi.parents_of([{"SampleType": "X"}], "X") == []


def test_only_real_sample_type_codes_are_returned():
    catalog = fi.load_catalog()
    codes = {r["SampleType"] for r in catalog if r.get("SampleType")}
    for t in ("DNA", "CEL", "MUS", "D.ELSA"):
        assert set(fi.parents_of(catalog, t)) <= codes


def test_an_unknown_sample_type_returns_an_empty_list_not_an_empty_string():
    """`type_record` raises for an unknown code; the fallback must stay a list."""
    out = fi.parents_of(fi.load_catalog(), "NOT.A.TYPE")
    assert out == []
    assert isinstance(out, list)
