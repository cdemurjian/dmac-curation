"""The eight refusals from spec section 5, one test each.

Every one is a live failure mode of /seek/sampleupload/, not a hypothesis.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import preflight as P  # noqa: E402

GOOD_BACKUP = {"size": 17_000_000, "trailer_ok": True}
EXAMPLE_UID = "TIS-190101ENG-901"


def _sheet(**over):
    base = {"sample_id": [10], "assay_id": [501],
            "uid": [EXAMPLE_UID],
            "current_pair": [""], "new_pair": ["10:501"]}
    base.update(over)
    return pd.DataFrame(base)


def _manifest():
    return pd.DataFrame({"sample_id": [10],
                         "write_target_seek_assay_id": [501],
                         "project_ok": [True]})


def test_a_clean_sheet_passes():
    P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_current_pair_of_two_ints_is_refused():
    """The sole combination that reaches deleteOneRecord."""
    with pytest.raises(P.PreflightRefused, match="delete"):
        P.check(_sheet(current_pair=["10:501"]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_an_unparseable_new_pair_is_refused():
    """Silently drops the registration and reports success."""
    with pytest.raises(P.PreflightRefused, match="New pair"):
        P.check(_sheet(new_pair=["not-a-pair"]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_blank_uid_is_refused():
    """getSampleID returns None; None > 0 raises; 500s mid-run."""
    with pytest.raises(P.PreflightRefused, match="uid"):
        P.check(_sheet(uid=["   "]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_sheet_named_UPDATE_anywhere_is_refused():
    """Hijacks dispatch into the metadata-update path, tested first."""
    with pytest.raises(P.PreflightRefused, match="UPDATE"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY", "UPDATE"],
                GOOD_BACKUP, 414935)


def test_a_row_absent_from_the_manifest_is_refused():
    with pytest.raises(P.PreflightRefused, match="manifest"):
        P.check(_sheet(assay_id=[999]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_no_rollback_handle_is_refused():
    with pytest.raises(P.PreflightRefused, match="rollback"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"], GOOD_BACKUP, None)


def test_an_unverified_backup_is_refused():
    """Non-zero size AND a Dump completed trailer. A 0-byte file exited 0."""
    with pytest.raises(P.PreflightRefused, match="backup"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"],
                {"size": 0, "trailer_ok": False}, 414935)


def test_a_backup_with_size_but_no_trailer_is_still_refused():
    with pytest.raises(P.PreflightRefused, match="backup"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"],
                {"size": 17_000_000, "trailer_ok": False}, 414935)


def test_a_chunk_above_the_cap_is_refused():
    """20-minute gunicorn SIGKILL, and this path has no transaction."""
    n = P.CHUNK_CAP + 1
    big = pd.DataFrame({
        "sample_id": range(n),
        "assay_id": [501] * n,
        "uid": [EXAMPLE_UID] * n,
        "current_pair": [""] * n,
        "new_pair": ["10:501"] * n})
    manifest = pd.DataFrame({
        "sample_id": range(n),
        "write_target_seek_assay_id": [501] * n,
        "project_ok": [True] * n})
    with pytest.raises(P.PreflightRefused, match="2000"):
        P.check(big, manifest, ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)
