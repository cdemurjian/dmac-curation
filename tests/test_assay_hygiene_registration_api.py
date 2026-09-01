"""The batch assay-registration API client.

WHY THIS IS NOT YET THE PRODUCTION WRITE PATH. The endpoint is deployed on the
dev box and NOT on production -- verified 2026-09-01, `ls
/app/nextseek_api/assay_registration/` returns 0 there. `/curate-assay-write`
therefore keeps using the UPDATE_ASSAY sheet for production until prod is
rebuilt, and this client is built and tested against dev in the meantime.
Adopting an undeployed endpoint is the obvious way to lose a run.

WHAT THE CLIENT IS FOR, once it is. The endpoint is ADDITIVE -- it writes
through `batch_insert_assay_assets`, which contains no DELETE -- which is the
property the sheet was chosen for and the reason `PATCH /assays/{uid}/` and
batch-upload were rejected. Both of those are complete-list writes that would
silently drop every other membership on the assay.

THE TWO PROPERTIES THIS SUITE EXISTS FOR are the two that bite silently:

  1. the per-row `assay_assets_id` must be captured, because rollback is by
     EXPLICIT ID and not by a range -- a MAX(id) range is wrong the moment
     another writer interleaves
  2. a payload at or above the sync threshold must not be submitted as though
     it were synchronous, because the endpoint answers 202 with a durable job
     and a client that reads that as success reports a write that has not
     happened yet
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import registration_api as A  # noqa: E402

UID_A = "TIS-190101ENG-901"
UID_B = "TIS-190101ENG-902"
DEV = "https://nextseek-dev.mit.edu"


def _manifest():
    return pd.DataFrame({"sample_id": [10, 11],
                         "internal_assay_id": [24, 24],
                         "write_target_seek_assay_id": [501, 502],
                         "project_ok": [True, True]})


def _uids():
    return {10: UID_A, 11: UID_B}


# --- the payload -------------------------------------------------------------


def test_the_payload_is_one_registration_per_row_keyed_on_uid_and_assay_id():
    payload = A.build_payload(_manifest(), _uids(), DEV, dry_run=True)
    assert payload["dry_run"] is True
    assert payload["registrations"] == [
        {"sample_uid": UID_A, "assay_id": 501},
        {"sample_uid": UID_B, "assay_id": 502}]


def test_the_payload_sends_assay_id_and_never_the_internal_id():
    """`assay_id` is SEEK's, validated against the sample's own project.

    `internal_assay_id` is this house's numbering. The two id spaces overlap
    numerically and share no meaning, so sending the wrong one registers into
    whatever assay happens to carry that number.
    """
    payload = A.build_payload(_manifest(), _uids(), DEV, dry_run=True)
    assert [r["assay_id"] for r in payload["registrations"]] == [501, 502]
    assert not any("internal" in k for r in payload["registrations"] for k in r)


def test_exactly_one_of_assay_or_assay_id_is_sent():
    """The endpoint requires exactly one. Sending both is a 422."""
    for row in A.build_payload(_manifest(), _uids(), DEV, dry_run=True)["registrations"]:
        assert ("assay" in row) ^ ("assay_id" in row)


def test_the_payload_inherits_the_sheet_builders_refusals():
    """The gates live upstream of transport and must survive the migration.

    A sample whose uid production holds twice killed RUN1's chunk 06. That
    refusal is computed from the extract at build time, so it protects any
    transport -- but only if the payload builder goes through it rather than
    assembling rows itself.
    """
    doubled = _uids() | {12: UID_A}
    with pytest.raises(A.RegistrationRefused, match="more than one sample"):
        A.build_payload(_manifest(), doubled, DEV, dry_run=True)

    with pytest.raises(A.RegistrationRefused, match="project"):
        A.build_payload(_manifest().assign(project_ok=[True, False]),
                        _uids(), DEV, dry_run=True)


# --- the synchronous threshold ----------------------------------------------


def test_a_payload_at_the_threshold_is_refused_as_synchronous():
    """5000 rows is where the endpoint switches to 202 + a durable job.

    A client that submits at or above it and reads the 202 as success reports
    a write that has not happened yet. Refusing is the honest default until
    the async path is built and verified.
    """
    assert A.SYNC_ROW_THRESHOLD == 5000
    big = pd.DataFrame({"sample_id": range(A.SYNC_ROW_THRESHOLD),
                        "internal_assay_id": 24,
                        "write_target_seek_assay_id": 501,
                        "project_ok": True})
    uids = {i: f"TIS-190101ENG-{i}" for i in range(A.SYNC_ROW_THRESHOLD)}
    with pytest.raises(A.RegistrationRefused, match="durable job|asynchronous"):
        A.build_payload(big, uids, DEV, dry_run=False)


def test_just_below_the_threshold_is_allowed():
    n = A.SYNC_ROW_THRESHOLD - 1
    frame = pd.DataFrame({"sample_id": range(n), "internal_assay_id": 24,
                          "write_target_seek_assay_id": 501, "project_ok": True})
    uids = {i: f"TIS-190101ENG-{i}" for i in range(n)}
    assert len(A.build_payload(frame, uids, DEV, dry_run=False)["registrations"]) == n


# --- rollback ----------------------------------------------------------------


def test_rollback_ids_come_from_the_response_and_not_from_a_range():
    """Issue #121. A MAX(id) range is wrong the moment another writer
    interleaves; the response names every row it created."""
    response = {"results": [
        {"sample_uid": UID_A, "assay_id": 501, "assay_assets_id": 801226,
         "status": "created"},
        {"sample_uid": UID_B, "assay_id": 502, "assay_assets_id": 801227,
         "status": "created"},
        {"sample_uid": "x", "assay_id": 9, "status": "already_present"}]}
    plan = A.rollback_plan(response)
    assert plan["assay_assets_ids"] == [801226, 801227]
    assert plan["sample_ids_needing_recompute"] == [UID_A, UID_B]


def test_the_rollback_plan_says_the_graph_recompute_is_step_two():
    """Deleting the rows does NOT revert the DERIVED_FROM labels derived from
    them, and nothing re-derives them on an out-of-band delete. Skipping it is
    silent: no error, and the graph keeps labels for memberships that are gone.
    """
    plan = A.rollback_plan({"results": [
        {"sample_uid": UID_A, "assay_id": 1, "assay_assets_id": 5,
         "status": "created"}]})
    assert "recompute" in plan["steps"][1].lower()
    assert "delete" in plan["steps"][0].lower()
    assert len(plan["steps"]) == 2


def test_a_response_that_created_nothing_yields_an_empty_rollback():
    plan = A.rollback_plan({"results": [
        {"sample_uid": UID_A, "assay_id": 1, "status": "already_present"}]})
    assert plan["assay_assets_ids"] == []


# --- deployment gate ---------------------------------------------------------


def test_production_is_refused_until_the_endpoint_is_deployed_there():
    """The endpoint is dev-only as of 2026-09-01. Pointing this client at
    production would 404, and a 404 read as 'nothing to do' is the failure."""
    with pytest.raises(A.RegistrationRefused, match="not deployed|production"):
        A.check_target("https://nextseek.mit.edu")
    A.check_target("https://nextseek-dev.mit.edu")     # allowed


def test_every_spelling_of_production_is_refused():
    """The first guard was string equality on a hand-split host. Four
    spellings walked past it, all measured."""
    for spelling in ("https://nextseek.mit.edu",
                     "https://nextseek.mit.edu:443/",
                     "https://nextseek.mit.edu./",
                     "https://user@nextseek.mit.edu/",
                     "https://nextseek.mit.edu?x=1",
                     "NEXTSEEK.MIT.EDU"):
        with pytest.raises(A.RegistrationRefused):
            A.check_target(spelling)


def test_a_loopback_url_is_refused_because_that_is_how_production_is_reached():
    """THE ONE A HOSTNAME DENYLIST CANNOT CATCH. `submit_update_assay` defaults
    to http://127.0.0.1:8000 and the write command says to run it ON THE BOX,
    so on production, production IS localhost."""
    for local in ("http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]/"):
        with pytest.raises(A.RegistrationRefused, match="loopback|not deployed"):
            A.check_target(local)


def test_building_a_payload_requires_a_target_and_checks_it():
    """A guard a caller has to remember is not a guard. The earlier version
    made this a separate function and the docstring claimed an enforcement the
    code never performed."""
    with pytest.raises(A.RegistrationRefused):
        A.build_payload(_manifest(), _uids(), "https://nextseek.mit.edu")


def test_the_threshold_cannot_be_flipped_past_by_editing_dry_run():
    """Gating on `not dry_run` was defeated by the obvious workflow: build a
    dry-run payload, set payload['dry_run'] = False, submit it."""
    n = A.SYNC_ROW_THRESHOLD
    frame = pd.DataFrame({"sample_id": range(n), "internal_assay_id": 24,
                          "write_target_seek_assay_id": 501, "project_ok": True})
    uids = {i: f"TIS-190101ENG-{i}" for i in range(n)}
    with pytest.raises(A.RegistrationRefused, match="durable job"):
        A.build_payload(frame, uids, DEV, dry_run=True)
