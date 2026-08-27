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


def _assays():
    return pd.DataFrame({
        "assay_id": [1, 2],
        "internal_assay_id": [74.0, 130.0],
        "internal_assay_title": ["Tissue Collection", "Mass Spectrometry"],
    })


def _run_with(tmp_path, rows):
    run = tmp_path / "RUN1" / "00-rulings"
    run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        + rows)
    return tmp_path / "RUN1"


APPROVE_ROW = ("ENG\tTIS\tPAV\tTissue Collection\t(lineage)\t"
               "ADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
REJECT_ROW = ("OTH\tTIS\tXXX\tTissue Collection\t(lineage)\t"
              "ADD_PARENT_TO_ASSAY\tREJECT\t\n")
OTHER_ROW = ("ENG\tMUS\tPAV\tMass Spectrometry\t(lineage)\t"
             "ADD_CHILD_TO_ASSAY\tAPPROVE\t\n")


def test_a_clean_migration_writes_every_key(tmp_path):
    run = _run_with(tmp_path, APPROVE_ROW)
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 1
    assert got["conflicts"] == []


def test_a_conflicting_key_is_EXCLUDED_and_reported(tmp_path):
    """The store must not contain a key the operator ruled two ways."""
    run = _run_with(tmp_path, APPROVE_ROW + REJECT_ROW)
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 0, "a conflicting key must not be written"
    assert len(got["conflicts"]) == 1
    assert got["conflicts"][0]["key"] == ("TIS", "74", "ADD_PARENT_TO_ASSAY")


def test_a_conflict_does_not_block_the_keys_that_agree(tmp_path):
    run = _run_with(tmp_path, APPROVE_ROW + REJECT_ROW + OTHER_ROW)
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 1, "the agreeing key must still land"
    assert len(got["conflicts"]) == 1


def test_the_written_store_reads_back_through_rulings_load(tmp_path):
    from assay_hygiene.rulings import load
    run = _run_with(tmp_path, APPROVE_ROW)
    I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    store = load(tmp_path / "rulings")
    assert store[("TIS", "74", "ADD_PARENT_TO_ASSAY")].verdict == "APPROVE"
