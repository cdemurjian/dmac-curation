"""One run at a time, and a file that says which.

Two concurrent write phases could silently overwrite each other's rows: primary
keys are MAX(id)+1 computed in Python with no lock, so a second writer makes
Django's explicit-pk save() do UPDATE-then-INSERT and overwrite the first
writer's row, with both callers told they succeeded.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import runstate as S  # noqa: E402


def test_reading_an_absent_lockfile_is_empty_not_an_error(tmp_path):
    assert S.read(tmp_path) == {}


def test_create_writes_a_readable_lockfile(tmp_path):
    made = S.create(tmp_path, run=2, extract_sha="abc123")
    assert made["run"] == 2
    assert made["extract_sha"] == "abc123"
    assert S.read(tmp_path)["run"] == 2


def test_a_second_run_is_refused_while_one_is_open(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    with pytest.raises(S.RunLocked, match="2"):
        S.create(tmp_path, run=3, extract_sha="def456")


def test_a_new_run_opens_once_the_previous_is_closed(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.close(tmp_path)
    assert S.create(tmp_path, run=3, extract_sha="def456")["run"] == 3


def test_update_merges_without_dropping_existing_fields(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.update(tmp_path, step="review", carried_pairs=479)
    got = S.read(tmp_path)
    assert got["step"] == "review"
    assert got["carried_pairs"] == 479
    assert got["extract_sha"] == "abc123", "update must not clobber"


def test_update_on_no_open_run_refuses(tmp_path):
    with pytest.raises(S.RunLocked):
        S.update(tmp_path, step="review")


def test_a_fresh_run_records_that_nothing_is_written_yet(tmp_path):
    made = S.create(tmp_path, run=2, extract_sha="abc123")
    assert made["write"]["chunks_done"] == 0
    assert made["write"]["rollback_id"] is None
    assert made["write"]["backup_verified"] is False
