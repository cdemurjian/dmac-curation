"""Three buckets, and why the middle one exists.

A pair ruling carries forward only while the new cohort is no wider than the
one it was made against. In RUN1, 2,830 rows shared a cohort key with an
approved cohort but sat below the precedent floor the operator's sheet was
built at, so he never saw them. Matching on the pair alone registers all of
them silently; that is what this splits apart.

NO REAL COHORT KEY APPEARS HERE. Keys are synthetic.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import carryforward as C  # noqa: E402
from assay_hygiene.rulings import Ruling  # noqa: E402

KEY = ("TIS", "74", "ADD_TO_ASSAY")
OTHER = ("MUS", "87", "ADD_PARENT_TO_ASSAY")


def _store(*keys):
    return {k: Ruling(k, "APPROVE", "2026-08-20", "operator") for k in keys}


def test_a_pair_never_ruled_is_unseen():
    got = C.split([C.Cohort(KEY, 10, "c1")], {}, {})
    assert [c.cohort_id for c in got[C.UNSEEN]] == ["c1"]
    assert got[C.CARRIED] == [] and got[C.WIDENED] == []


def test_a_pair_ruled_at_the_same_width_is_carried():
    got = C.split([C.Cohort(KEY, 10, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.CARRIED]] == ["c1"]


def test_a_pair_ruled_against_MORE_rows_is_carried():
    """Narrower than what was ruled is covered by that ruling."""
    got = C.split([C.Cohort(KEY, 4, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.CARRIED]] == ["c1"]


def test_a_pair_ruled_against_FEWER_rows_is_widened_not_carried():
    """RUN1's trap: the ruling exists but never covered these rows."""
    got = C.split([C.Cohort(KEY, 900, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["c1"]
    assert got[C.CARRIED] == [], "a widened cohort must never auto-apply"


def test_a_widened_cohort_with_no_recorded_width_is_widened_not_carried():
    """An unknown width is not evidence of coverage."""
    got = C.split([C.Cohort(KEY, 900, "c1")], _store(KEY), {})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["c1"]


def test_every_cohort_lands_in_exactly_one_bucket():
    cohorts = [C.Cohort(KEY, 4, "carried"),
               C.Cohort(OTHER, 900, "widened"),
               C.Cohort(("X", "1", "ADD_TO_ASSAY"), 5, "unseen")]
    got = C.split(cohorts, _store(KEY, OTHER), {KEY: 10, OTHER: 10})
    landed = [c.cohort_id for bucket in got.values() for c in bucket]
    assert sorted(landed) == ["carried", "unseen", "widened"]
    assert len(landed) == len(set(landed)), "a cohort was double-counted"
