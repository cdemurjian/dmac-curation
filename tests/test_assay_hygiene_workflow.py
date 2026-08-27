"""The sequence, not the units.

Each module is already tested in isolation. These assert the order they must
run in -- the property that a correct set of parts can still get wrong.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import carryforward as C  # noqa: E402
from assay_hygiene import init_run as I  # noqa: E402
from assay_hygiene import preflight as P  # noqa: E402
from assay_hygiene import resolve_targets as T  # noqa: E402
from assay_hygiene import runstate as S  # noqa: E402
from assay_hygiene.rulings import Ruling  # noqa: E402

EXAMPLE_UID = "TIS-190101ENG-901"


def test_a_fresh_run_refuses_to_write_before_rulings_are_ingested(tmp_path):
    """No rollback handle and no backup: the write path is closed by default."""
    S.create(tmp_path, run=2, extract_sha="abc")
    state = S.read(tmp_path)
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [501],
                          "uid": [EXAMPLE_UID],
                          "current_pair": [""], "new_pair": ["10:501"]})
    manifest = pd.DataFrame({"sample_id": [10],
                             "write_target_seek_assay_id": [501],
                             "project_ok": [True]})
    with pytest.raises(P.PreflightRefused):
        P.check(sheet, manifest, ["UPDATE_ASSAY"],
                {"size": 0, "trailer_ok": False},
                state["write"]["rollback_id"])


def test_a_carried_ruling_applied_to_a_wider_cohort_is_surfaced_not_applied():
    """The RUN1 trap, asserted end to end."""
    key = ("TIS", "74", "ADD_TO_ASSAY")
    store = {key: Ruling(key, "APPROVE", "2026-08-20", "operator")}
    got = C.split([C.Cohort(key, 2830, "wide")], store, {key: 12})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["wide"]
    assert got[C.CARRIED] == [], "a widened cohort must not reach the write set"


def test_the_project_gate_refuses_a_cross_project_row_by_injection():
    """Spec section 7 requires this be proven by injection, not by argument."""
    assays = pd.DataFrame({"assay_id": [501, 502],
                           "internal_assay_id": [74.0, 74.0],
                           "project_id": [1, 2]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501]

    # The injected row is well-formed in EVERY other respect -- a parseable New
    # pair, a blank Current pair, a real uid -- so the only thing that can
    # refuse it is the project gate. An incomplete row would be caught earlier
    # by the New-pair check and the test would pass without proving anything.
    injected = pd.DataFrame({"sample_id": [10], "assay_id": [502],
                             "uid": [EXAMPLE_UID],
                             "current_pair": [""], "new_pair": ["10:502"]})
    with pytest.raises(P.PreflightRefused, match="manifest"):
        P.check(injected, manifest, ["UPDATE_ASSAY"],
                {"size": 17_000_000, "trailer_ok": True}, 414935)


def test_a_run_cannot_be_opened_twice(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc")
    with pytest.raises(S.RunLocked):
        S.create(tmp_path, run=3, extract_sha="def")


def test_init_refuses_a_run_when_the_store_is_gone(tmp_path):
    with pytest.raises(I.MissingRulingStore):
        I.require_store(tmp_path / "rulings", tmp_path / "backups")


def test_the_happy_path_reaches_preflight_clean(tmp_path):
    """The same sequence, with every precondition met, must NOT raise."""
    S.create(tmp_path, run=2, extract_sha="abc")
    S.update(tmp_path, write={"chunks_done": 0, "rollback_id": 414935,
                              "backup_verified": True})
    assays = pd.DataFrame({"assay_id": [501], "internal_assay_id": [74.0],
                           "project_id": [1]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert excluded.empty
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [501],
                          "uid": [EXAMPLE_UID],
                          "current_pair": [""], "new_pair": ["10:501"]})
    P.check(sheet, manifest, ["UPDATE_ASSAY"],
            {"size": 17_000_000, "trailer_ok": True},
            S.read(tmp_path)["write"]["rollback_id"])
