"""Turning RUN1's three ruling shapes into one durable store.

NO COHORT KEY OR LAB CODE IS WRITTEN INTO THIS FILE. Fixtures are synthetic.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import migrate_rulings as M  # noqa: E402


@pytest.fixture
def assays():
    return pd.DataFrame({
        "assay_id": [1, 2, 3],
        "internal_assay_id": [74.0, 130.0, 61.0],
        "internal_assay_title": ["Tissue Collection", "Mass Spectrometry",
                                 "RNA Extraction"],
    })


def test_a_title_resolves_to_a_bare_internal_id(assays):
    assert M.title_index(assays)["Tissue Collection"] == "74"


def test_an_ambiguous_title_is_refused_not_guessed():
    """Two assays sharing a display string must never silently merge."""
    frame = pd.DataFrame({
        "assay_id": [1, 2], "internal_assay_id": [74.0, 99.0],
        "internal_assay_title": ["Imaging", "Imaging"]})
    with pytest.raises(M.AmbiguousTitle, match="Imaging"):
        M.title_index(frame)


def test_a_mode2_lineage_row_takes_its_action_from_the_value_column(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].key == ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert got[0].verdict == "APPROVE"


def test_a_mode2_TERM_row_becomes_ADD_TO_ASSAY(tmp_path, assays):
    """A term row proposes on metadata, not on a lineage direction."""
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\tType\tMacrophages\tREJECT\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].key == ("TIS", "74", "ADD_TO_ASSAY")


def test_a_pair_ruling_maps_OVERRIDE_to_APPROVE(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "pair-rulings.tsv").write_text(
        "sample_type\tproposed_assay\tinternal_assay_id\tblocked_rows\truling\tstatus\tnote\n"
        "TIS\tTissue Collection\t74\t100\tOVERRIDE\truled\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].verdict == "APPROVE"


def test_an_UNRULED_pair_row_is_not_migrated(tmp_path, assays):
    """130 of 175 are UNRULED. Absence of a ruling is not a ruling."""
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "pair-rulings.tsv").write_text(
        "sample_type\tproposed_assay\tinternal_assay_id\tblocked_rows\truling\tstatus\tnote\n"
        "TIS\tTissue Collection\t74\t100\t\tUNRULED\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got == []


def test_provenance_records_the_cohort_the_ruling_was_made_against(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    _, prov = M.migrate(tmp_path / "RUN9", assays)
    assert prov[0]["key"] == ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert "ENG" in prov[0]["cohort"], "the cohort as ruled must be recoverable"


def test_a_missing_ruling_file_is_skipped_not_fatal(tmp_path, assays):
    (tmp_path / "RUN9" / "00-rulings").mkdir(parents=True)
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got == []


def test_conflicts_reports_a_key_ruled_two_ways(assays):
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    found = M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "REJECT", "2026-08-20", "operator")])
    assert len(found) == 1
    assert sorted(found[0]["verdicts"]) == ["APPROVE", "REJECT"]
    assert found[0]["key"] == key


def test_conflicts_is_empty_when_every_key_agrees(assays):
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                        Ruling(key, "APPROVE", "2026-08-21", "operator")]) == []


def test_a_conflict_is_never_resolved_by_majority(assays):
    """Two APPROVE and one REJECT is still a conflict, not an APPROVE."""
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    found = M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "REJECT", "2026-08-20", "operator")])
    assert len(found) == 1
