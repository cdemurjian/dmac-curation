"""The durable ruling store: what a verdict is filed under, and what it costs.

RUN1's rulings were keyed on `lab|sample_type|parent_types|assay_title|field|value`.
Four of those six fields move with the extract, so a new run matched almost
none of them and 261 rulings became worthless -- not because the judgement
changed but because the string they were filed under did. This stores judgement
under (sample_type, internal_assay_id, action), all three of which survive a
title edit, a lab change and lineage drift.

NO COHORT KEY IS WRITTEN INTO THIS FILE. They carry lab codes and, in one RUN1
case, a protocol filename with a person's name.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import rulings as R  # noqa: E402


def test_a_saved_ruling_reads_back_identical(tmp_path):
    one = R.Ruling(key=("TIS", "74", "ADD_PARENT_TO_ASSAY"),
                   verdict="APPROVE", ruled_on="2026-08-20", actor="operator")
    R.save(tmp_path, [one])
    assert R.load(tmp_path)[one.key] == one


def test_the_internal_id_normalises_away_a_float_suffix():
    """Titles resolve through pandas, which yields 74.0 for an int column."""
    assert R.normalise_id(74.0) == "74"
    assert R.normalise_id("74.0") == "74"
    assert R.normalise_id(" 74 ") == "74"


def test_a_verdict_outside_the_vocabulary_is_refused(tmp_path):
    bad = R.Ruling(key=("TIS", "74", "ADD_PARENT_TO_ASSAY"),
                   verdict="probably fine", ruled_on="2026-08-20", actor="operator")
    with pytest.raises(ValueError, match="probably fine"):
        R.save(tmp_path, [bad])


def test_saving_the_same_key_twice_with_the_same_verdict_is_one_row(tmp_path):
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    R.save(tmp_path, [R.Ruling(key, "APPROVE", "2026-08-20", "operator"),
                      R.Ruling(key, "APPROVE", "2026-08-21", "operator")])
    assert len(R.load(tmp_path)) == 1


def test_saving_the_same_key_with_DIFFERENT_verdicts_refuses(tmp_path):
    """A conflict is the operator's to resolve, never a rule's."""
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    with pytest.raises(R.ConflictingRulings, match="TIS"):
        R.save(tmp_path, [R.Ruling(key, "APPROVE", "2026-08-20", "operator"),
                          R.Ruling(key, "REJECT", "2026-08-21", "operator")])


def test_loading_an_absent_store_is_empty_not_an_error(tmp_path):
    assert R.load(tmp_path / "nothing-here") == {}


def test_the_store_survives_a_round_trip_of_many(tmp_path):
    many = [R.Ruling((f"T{i}", str(i), "ADD_TO_ASSAY"), "APPROVE",
                     "2026-08-20", "operator") for i in range(500)]
    R.save(tmp_path, many)
    assert len(R.load(tmp_path)) == 500
