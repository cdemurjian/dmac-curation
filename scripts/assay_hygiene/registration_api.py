# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "requests>=2.31"]
# ///
"""Client for NExtSEEK's batch assay-registration endpoint.

    POST /nextseek_api/assay-registrations/
    {"registrations": [{"sample_uid": "...", "assay_id": 1}], "dry_run": true}

NOT THE PRODUCTION WRITE PATH YET, AND THAT IS DELIBERATE. Verified
2026-09-01: `docker exec nextseek ls /app/nextseek_api/assay_registration/`
returns 0 on production, which runs a commit predating the merge. The dev box
has it. `/curate-assay-write` therefore keeps posting the UPDATE_ASSAY sheet for
production writes until prod is rebuilt and this is re-verified there. Adopting
an endpoint that is not deployed is how a run gets lost. `check_target` enforces
this rather than trusting a reader to remember it.

WHY IT WILL BE WORTH SWITCHING. The write goes through
`batch_insert_assay_assets`, whose docstring states it contains no DELETE and
whose test asserts it. That is the property the sheet was chosen for: registering
a membership adds a row and touches nothing else on the assay. The two modern
paths that were rejected -- `PATCH /nextseek_api/assays/{uid}/` and batch-upload
-- are COMPLETE-LIST writes, measured at 202,016 and 25,912 existing memberships
at risk respectively. This endpoint puts zero at risk for the same reason the
sheet did, without the workbook, the CSRF dance or the header-name sensitivity.

THE GATES STAY UPSTREAM OF TRANSPORT. `build_payload` goes through
`update_assay_sheet.build`, so a sheet and a payload refuse identically: an
ungated row, a duplicated edge, a non-integer target, a missing uid, and a
sample whose uid production holds more than once. That last one 500'd RUN1's
chunk 06 and blocked four of RUN2's rows; it is a property of the DATA, not of
the transport, and it must not be lost by changing how the rows are sent.

TWO THINGS THE ENDPOINT DOES THAT THE SHEET DID NOT, both of which a caller has
to handle rather than assume away:

  1. AT OR ABOVE 5,000 ROWS IT ANSWERS 202 WITH A DURABLE JOB. It was verified
     at 1,000 rows, twice, on the synchronous path. A full assay-hygiene write
     is ~26,000 rows and would cross the threshold into a path nobody has
     exercised, needing the worker running and a poll/cancel client. This module
     REFUSES at the threshold rather than submitting and reading the 202 as
     success.
  2. IT RECOMPUTES DERIVED_FROM LABELS AS PART OF THE WRITE -- 2,137 edges for
     1,000 registrations. Deleting the rows again does NOT revert them, and
     nothing re-derives them on an out-of-band delete. See `rollback_plan`.

ROLLBACK IS BY EXPLICIT ID. The response names `assay_assets_id` for every row
it created. A `MAX(id)` range -- which is what the sheet path uses and is correct
there -- is wrong here the moment another writer interleaves, and this endpoint
has no delete of its own to hang a correct one on. Filed upstream as issue #121.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pandas as pd

from .update_assay_sheet import SheetRefused, build

# `ASSAY_REGISTRATION_SYNC_ROW_THRESHOLD` on the server. At or above it the
# endpoint returns 202 and a durable job id instead of writing inline.
SYNC_ROW_THRESHOLD = 5000

ENDPOINT = "/nextseek_api/assay-registrations/"

# ALLOWLIST, NOT A DENYLIST, AND THAT IS THE WHOLE POINT. The first version of
# this named the production host and refused it. Four spellings walked straight
# past string equality -- `nextseek.mit.edu:443`, a trailing dot, `user@host`,
# a bare query -- and, decisively, THE HOUSE IDIOM FOR REACHING PRODUCTION IS A
# LOOPBACK URL: `submit_update_assay` defaults to http://127.0.0.1:8000 and the
# write command says to run it on the box. A hostname denylist structurally
# cannot see production when production is reached as localhost.
#
# So: name the hosts the endpoint IS deployed to, parse properly, and refuse
# everything else including loopback. A new dev host costs one edit here, which
# is the correct price for a gate on a production write.
DEPLOYED_HOSTS = ("nextseek-dev.mit.edu",)


class RegistrationRefused(RuntimeError):
    """A payload or a target that must not be submitted as-is."""


def check_target(base_url: str) -> str:
    """-> the normalised host, or raise if the endpoint is not deployed there.

    Called by `build_payload`, which is why that function requires a base URL:
    a guard a caller has to remember is not a guard. A 404 from an absent
    endpoint is easy to misread as "nothing to do", so this refuses before the
    request rather than interpreting the answer.
    """
    parsed = urlsplit(str(base_url) if "//" in str(base_url)
                      else f"//{base_url}")
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise RegistrationRefused(
            f"{base_url!r} names no host, so it cannot be checked against the "
            f"hosts this endpoint is deployed to: {list(DEPLOYED_HOSTS)}.")
    if host not in DEPLOYED_HOSTS:
        extra = ""
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            extra = (" A loopback URL is how this mode reaches PRODUCTION -- "
                     "`submit_update_assay` defaults to http://127.0.0.1:8000 "
                     "and runs on the box -- so it is refused outright rather "
                     "than assumed to be a local dev stack.")
        raise RegistrationRefused(
            f"the assay-registration endpoint is not deployed at {host!r}. "
            f"Deployed: {list(DEPLOYED_HOSTS)}. Production does NOT have it "
            f"(verified 2026-09-01: /app/nextseek_api/assay_registration/ is "
            f"empty there); use the UPDATE_ASSAY sheet path for production "
            f"writes until it is rebuilt, then add the host here and "
            f"re-verify.{extra}")
    return host


def build_payload(manifest: pd.DataFrame, uid_of: dict[int, str],
                  base_url: str, dry_run: bool = True) -> dict:
    """-> the request body for `manifest`, or raise.

    `base_url` IS REQUIRED AND IS CHECKED HERE. An earlier version made the
    target check a separate function a caller had to remember, which is not a
    guard -- the docstring claimed enforcement the code did not perform. You
    cannot now build a payload without naming where it is going.

    Goes through `update_assay_sheet.build` on purpose: the refusals it applies
    are about the DATA and hold whatever the transport is. Reimplementing them
    here would be a second definition, free to drift from the one the sheet
    path uses, on exactly the checks that stop an unrecoverable write.
    """
    check_target(base_url)
    try:
        sheet = build(manifest, uid_of)
    except SheetRefused as exc:
        raise RegistrationRefused(str(exc)) from exc

    rows = [{"sample_uid": str(uid), "assay_id": int(assay)}
            for uid, assay in zip(sheet["Sample UID"], sheet["New Assay ID"])]

    # REFUSED AT THE THRESHOLD REGARDLESS OF dry_run. Gating this on
    # `not dry_run` was defeated by the obvious workflow: build a dry-run
    # payload, then flip `payload["dry_run"] = False` and submit it. The size
    # of a submission is a property of the submission, not of whether this
    # particular call intends to commit, so it is refused either way.
    #
    # NOT CHUNKED SILENTLY. Chunking would be a reasonable answer, but it is a
    # different write shape -- the server plans a job across the whole
    # submission -- and inventing one here without the async path verified
    # would be guessing at the contract.
    if len(rows) >= SYNC_ROW_THRESHOLD:
        raise RegistrationRefused(
            f"{len(rows):,} rows is at or above the {SYNC_ROW_THRESHOLD:,} "
            f"synchronous threshold, so the endpoint answers 202 with a "
            f"durable job rather than writing inline. That path needs the "
            f"worker running and a poll/cancel client, and has not been "
            f"exercised -- the endpoint was verified at 1,000 rows. Split the "
            f"submission or build the asynchronous client first.")

    return {"registrations": rows, "dry_run": bool(dry_run)}


def rollback_plan(response: dict) -> dict:
    """-> what undoing this write actually requires. TWO steps, both needed.

    STEP 2 IS THE ONE THAT GETS SKIPPED. A registration recomputes the
    `DERIVED_FROM` labels of the edges touching its samples -- 2,137 edges for
    1,000 registrations, measured. `assay_assets` is the source of truth and the
    labels are derived from it, so deleting the rows leaves the graph asserting
    memberships that no longer exist. Nothing re-derives them, because the
    endpoint has no delete path to hang that on. It fails silently: no error,
    just a graph that is confidently wrong.

    THE IDS COME FROM THE RESPONSE. Rows that came back `already_present` were
    not created by this call and must not be deleted by its rollback.
    """
    created = [r for r in response.get("results", [])
               if r.get("assay_assets_id") is not None
               and r.get("status") == "created"]
    return {
        "assay_assets_ids": [int(r["assay_assets_id"]) for r in created],
        "sample_ids_needing_recompute": [str(r["sample_uid"]) for r in created],
        "steps": [
            "DELETE FROM assay_assets WHERE id IN (<assay_assets_ids>) -- by "
            "explicit id, never a MAX(id) range: another writer interleaving "
            "makes a range delete somebody else's rows.",
            "graph.recompute_for_samples(sample_ids, driver, db) -- with the "
            "driver from service._neo4j(). NOT optional and NOT afterwards: "
            "step 1 alone leaves DERIVED_FROM labels for memberships that are "
            "gone, and nothing reports it. This is the same repair "
            "/curate-assay-relabel performs; the two should be one procedure.",
        ],
    }
