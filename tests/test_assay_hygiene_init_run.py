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
