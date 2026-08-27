"""Regression tests for the four defects the 2026-08-27 review found.

Copy to tests/test_assay_hygiene_review_fixes.py and run BEFORE applying
apply_review_fixes.py: all six must fail. Then apply and they must pass.
That order is the point -- a test written after the fix proves nothing about
the defect.

NO REAL COHORT KEY OR SAMPLE UID APPEARS HERE.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import init_run as I  # noqa: E402
from assay_hygiene import resolve_targets as T  # noqa: E402
from assay_hygiene import runstate as S  # noqa: E402
from assay_hygiene.rulings import Ruling, load, save  # noqa: E402


# ------------------------------------------------------------------ fix 1
def _assays():
    return pd.DataFrame({
        "assay_id": [1],
        "internal_assay_id": [74.0],
        "internal_assay_title": ["Tissue Collection"],
    })


def _run(tmp_path):
    d = tmp_path / "RUN1" / "00-rulings"
    d.mkdir(parents=True)
    (d / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    return tmp_path / "RUN1"


def test_migrating_does_not_delete_a_ruling_the_run_cannot_re_derive(tmp_path):
    """THE CRITICAL DEFECT. An operator's resolution of an earlier conflict is
    in no run's files, so a migration that overwrites the store erases it."""
    store = tmp_path / "rulings"
    resolved = ("MUS", "87", "ADD_PARENT_TO_ASSAY")
    save(store, [Ruling(resolved, "APPROVE", "2026-08-27", "operator")])

    I.migrate_into_store(_run(tmp_path), _assays(), store)

    after = load(store)
    assert resolved in after, (
        "the operator's conflict resolution was destroyed by a re-migration")
    assert after[resolved].verdict == "APPROVE"


def test_migrating_still_adds_the_runs_own_rulings(tmp_path):
    store = tmp_path / "rulings"
    save(store, [Ruling(("MUS", "87", "ADD_PARENT_TO_ASSAY"),
                        "APPROVE", "2026-08-27", "operator")])
    got = I.migrate_into_store(_run(tmp_path), _assays(), store)
    assert got["written"] == 1
    assert got["store_before"] == 1
    assert got["store_total"] == 2
    assert len(load(store)) == 2


def test_a_migrated_verdict_that_contradicts_the_store_escalates(tmp_path):
    """Merging must not silently prefer either side."""
    from assay_hygiene.rulings import ConflictingRulings
    store = tmp_path / "rulings"
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    save(store, [Ruling(key, "REJECT", "2026-08-27", "operator")])
    with pytest.raises(ConflictingRulings):
        I.migrate_into_store(_run(tmp_path), _assays(), store)


# ------------------------------------------------------------------ fix 3
def test_a_sample_in_two_projects_holding_the_assay_is_excluded_not_guessed():
    """Was resolved by project_ids list order -- an unrecoverable write
    decided by whichever project happened to come first."""
    assays = pd.DataFrame({"assay_id": [501, 502],
                           "internal_assay_id": [74.0, 74.0],
                           "project_id": [1, 2]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1, 2]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.empty, "an ambiguous target must not reach the manifest"
    assert excluded.reason.tolist() == [T.AMBIGUOUS]


def test_a_sample_in_two_projects_where_only_one_holds_it_still_resolves():
    """Multi-project is not itself ambiguous; two candidates are."""
    assays = pd.DataFrame({"assay_id": [501], "internal_assay_id": [74.0],
                           "project_id": [2]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1, 2]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501]
    assert excluded.empty


# ------------------------------------------------------------------ fix 4
def test_updating_one_write_field_keeps_the_others(tmp_path):
    """backup_verified silently reverting to False reads to preflight as
    'no backup', which is the check standing between a run and production."""
    S.create(tmp_path, run=2, extract_sha="abc")
    S.update(tmp_path, write={"backup_verified": True, "chunks_done": 3,
                              "rollback_id": 414935})
    S.update(tmp_path, write={"chunks_done": 4})
    w = S.read(tmp_path)["write"]
    assert w["chunks_done"] == 4
    assert w["backup_verified"] is True, "backup_verified was clobbered"
    assert w["rollback_id"] == 414935, "rollback_id was clobbered"
