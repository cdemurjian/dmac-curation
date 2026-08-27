"""Joining an operator-edited CSV back onto the cohorts it was built from.

Spec section 9's four required properties, one test each. This is the one place
RUN1 was hand-assembled and it is where a mistake registers rows nobody
approved.

NO REAL COHORT KEY APPEARS HERE. Keys are synthetic.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import ingest as G  # noqa: E402

COHORTS = {"cohort-a": ("TIS", "74", "ADD_TO_ASSAY"),
           "cohort-b": ("MUS", "87", "ADD_PARENT_TO_ASSAY")}


def _edited(rows):
    return pd.DataFrame(rows, columns=["cohort_key", "ruling"])


def test_a_ruled_row_becomes_a_ruling():
    got = G.ingest(_edited([["cohort-a", "APPROVE"]]), COHORTS, "2026-09-01")
    assert len(got) == 1
    assert got[0].key == ("TIS", "74", "ADD_TO_ASSAY")
    assert got[0].verdict == "APPROVE"
    assert got[0].ruled_on == "2026-09-01"


def test_a_blank_ruling_is_skipped_not_defaulted():
    """An unruled row is not a rejection."""
    assert G.ingest(_edited([["cohort-a", ""]]), COHORTS, "2026-09-01") == []


def test_a_row_matching_NO_cohort_refuses_the_whole_file():
    """Property 1: a partial match is never resolved by a rule."""
    with pytest.raises(G.IngestRefused, match="cohort-zzz"):
        G.ingest(_edited([["cohort-a", "APPROVE"],
                          ["cohort-zzz", "APPROVE"]]), COHORTS, "2026-09-01")


def test_a_verdict_outside_the_vocabulary_refuses():
    """Property 2: refuse rather than default."""
    with pytest.raises(G.IngestRefused, match="probably fine"):
        G.ingest(_edited([["cohort-a", "probably fine"]]), COHORTS, "2026-09-01")


def test_ingesting_the_same_file_twice_is_a_no_op():
    """Property 3: idempotent, not a duplicate ruling."""
    edited = _edited([["cohort-a", "APPROVE"]])
    once = G.ingest(edited, COHORTS, "2026-09-01")
    twice = G.ingest(edited, COHORTS, "2026-09-01")
    assert once == twice
    assert len({r.key for r in once + twice}) == 1


def test_the_same_cohort_ruled_twice_in_ONE_file_refuses_if_it_disagrees():
    with pytest.raises(G.IngestRefused, match="cohort-a"):
        G.ingest(_edited([["cohort-a", "APPROVE"],
                          ["cohort-a", "REJECT"]]), COHORTS, "2026-09-01")


def test_a_missing_cohort_key_column_refuses():
    """Property 4: the key is the one the surface emitted, never rebuilt."""
    with pytest.raises(G.IngestRefused, match="cohort_key"):
        G.ingest(pd.DataFrame([{"key": "cohort-a", "ruling": "APPROVE"}]),
                 COHORTS, "2026-09-01")


def test_whitespace_around_a_verdict_does_not_defeat_the_vocabulary():
    got = G.ingest(_edited([["cohort-a", " APPROVE "]]), COHORTS, "2026-09-01")
    assert got[0].verdict == "APPROVE"
