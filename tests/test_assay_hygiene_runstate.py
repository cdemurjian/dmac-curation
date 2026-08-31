"""One run at a time, and a file that says which.

Two concurrent write phases could silently overwrite each other's rows: primary
keys are MAX(id)+1 computed in Python with no lock, so a second writer makes
Django's explicit-pk save() do UPDATE-then-INSERT and overwrite the first
writer's row, with both callers told they succeeded.
"""
import os
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


# --- resuming a run that was closed before it finished -----------------------


def test_a_closed_run_can_be_reopened_at_the_step_it_stopped_on(tmp_path):
    """RUN2 was closed at `resolve` so a fresh init would not hit the lock, and
    then had to be finished. Nothing could reopen it.

    `create` refuses while a run is open and allocates a NEW run number; there
    was no way back into an existing one, so resuming meant hand-editing the
    lockfile -- the one file whose whole job is to be the thing nobody
    hand-edits.
    """
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.update(tmp_path, step="resolve")
    S.close(tmp_path)
    assert S.read(tmp_path)["open"] is False

    back = S.reopen(tmp_path, run=2)
    assert back["open"] is True
    assert back["run"] == 2
    assert back["step"] == "resolve", "reopening must not rewind the run"
    assert back["extract_sha"] == "abc123"


def test_reopening_restamps_the_pid(tmp_path):
    """The closed run's pid belongs to a process that has since exited, and
    `create`'s refusal quotes it. Carrying it forward makes the next lock
    message name a process nobody can find."""
    S.create(tmp_path, run=2, extract_sha="abc123")
    stale = S.read(tmp_path)["pid"]
    S.close(tmp_path)
    S.reopen(tmp_path, run=2)
    assert S.read(tmp_path)["pid"] == os.getpid()
    assert isinstance(stale, int)


def test_reopening_a_different_run_than_the_lockfile_holds_is_refused(tmp_path):
    """Naming the run is how the caller proves it knows which one it resumes.

    Silently reopening whatever the lockfile happens to hold is how a session
    resumes RUN2 believing it is RUN3 and writes RUN2's rows a second time.
    """
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.close(tmp_path)
    with pytest.raises(S.RunLocked, match="holds run 2"):
        S.reopen(tmp_path, run=3)


def test_reopening_when_another_run_is_already_open_is_refused(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.close(tmp_path)
    S.create(tmp_path, run=3, extract_sha="def456")
    with pytest.raises(S.RunLocked, match="still open"):
        S.reopen(tmp_path, run=2)


def test_reopening_the_run_that_is_already_open_is_a_no_op(tmp_path):
    """Idempotent, because a resumed session cannot always tell whether the
    step before it got as far as reopening."""
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.update(tmp_path, step="write")
    again = S.reopen(tmp_path, run=2)
    assert again["open"] is True and again["step"] == "write"


def test_reopening_when_there_is_no_lockfile_at_all_is_refused(tmp_path):
    with pytest.raises(S.RunLocked, match="no run"):
        S.reopen(tmp_path, run=2)
