"""A fresh run must not silently discard a campaign's judgement.

No amount of compute regenerates a human ruling. `init` finding no ruling store
stops and names the restore command; it never starts an empty run quietly.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import init_run as I  # noqa: E402


def test_an_absent_store_refuses_and_names_the_restore_path(tmp_path):
    with pytest.raises(I.MissingRulingStore) as excinfo:
        I.require_store(tmp_path / "rulings", tmp_path / "backups")
    message = str(excinfo.value)
    assert "backups" in message, "the message must say where backups live"
    assert "tar" in message, "the message must carry a runnable restore command"


def test_a_store_directory_without_pairs_is_still_missing(tmp_path):
    """An empty directory is the shape a half-finished restore leaves."""
    (tmp_path / "rulings").mkdir()
    with pytest.raises(I.MissingRulingStore):
        I.require_store(tmp_path / "rulings", tmp_path / "backups")


def test_a_populated_store_passes(tmp_path):
    store = tmp_path / "rulings"; store.mkdir()
    (store / "pairs.tsv").write_text(
        "sample_type\tinternal_assay_id\taction\tverdict\truled_on\tactor\n")
    I.require_store(store, tmp_path / "backups")   # must not raise


def test_the_next_run_number_follows_the_highest_present(tmp_path):
    (tmp_path / "RUN1").mkdir()
    (tmp_path / "RUN2").mkdir()
    assert I.next_run_number(tmp_path) == 3


def test_the_first_run_is_number_one(tmp_path):
    assert I.next_run_number(tmp_path) == 1


def test_a_stray_directory_does_not_confuse_the_numbering(tmp_path):
    (tmp_path / "RUN1").mkdir()
    (tmp_path / "rulings").mkdir()
    (tmp_path / "RUNaway").mkdir()
    assert I.next_run_number(tmp_path) == 2


def test_create_run_makes_every_tier(tmp_path):
    run = I.create_run(tmp_path, 2)
    assert run.name == "RUN2"
    for tier in I.TIERS:
        assert (run / tier).is_dir(), f"{tier} missing"


def test_a_created_run_is_protected_except_the_process_tier(tmp_path):
    """07-process holds the workspace a later run appends to."""
    from assay_hygiene.protect_run import verify
    run = I.create_run(tmp_path, 2)
    assert verify(run, I.PROTECTED) == []
    assert verify(run, ["07-process"]) == [run / "07-process"]
