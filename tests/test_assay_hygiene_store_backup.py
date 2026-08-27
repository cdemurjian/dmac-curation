"""A backup that is not read back is not a backup.

On 2026-08-27 a mysqldump exited 0 having written 0 bytes; only an `ls` caught
it. `back_up` therefore opens the archive it just wrote and asserts the store's
files are inside, rather than trusting that tar returned cleanly.
"""
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import store_backup as B  # noqa: E402


def _store(tmp_path):
    store = tmp_path / "rulings"
    (store / "provenance").mkdir(parents=True)
    (store / "pairs.tsv").write_text(
        "sample_type\tinternal_assay_id\taction\tverdict\truled_on\tactor\n"
        "TIS\t74\tADD_TO_ASSAY\tAPPROVE\t2026-08-20\toperator\n")
    (store / "provenance" / "run1.jsonl").write_text('{"key": "x"}\n')
    return store


def test_a_backup_is_written_where_asked(tmp_path):
    made = B.back_up(_store(tmp_path), tmp_path / "backups", "20260827-1200")
    assert made.exists()
    assert made.name == "rulings-20260827-1200.tar.gz"


def test_the_backup_actually_contains_the_pairs_file(tmp_path):
    made = B.back_up(_store(tmp_path), tmp_path / "backups", "20260827-1200")
    with tarfile.open(made) as archive:
        names = archive.getnames()
    assert any(n.endswith("pairs.tsv") for n in names), names


def test_the_backup_round_trips_byte_identical(tmp_path):
    store = _store(tmp_path)
    original = (store / "pairs.tsv").read_bytes()
    made = B.back_up(store, tmp_path / "backups", "20260827-1200")
    out = tmp_path / "restored"; out.mkdir()
    with tarfile.open(made) as archive:
        archive.extractall(out, filter="data")
    restored = next(out.rglob("pairs.tsv"))
    assert restored.read_bytes() == original


def test_backing_up_an_absent_store_refuses(tmp_path):
    """An empty archive that reports success is the failure mode being stopped."""
    with pytest.raises(B.BackupUnverified, match="nothing to back up"):
        B.back_up(tmp_path / "gone", tmp_path / "backups", "20260827-1200")


def test_two_backups_on_the_same_day_do_not_collide(tmp_path):
    store = _store(tmp_path)
    a = B.back_up(store, tmp_path / "backups", "20260827-1200")
    b = B.back_up(store, tmp_path / "backups", "20260827-1830")
    assert a != b and a.exists() and b.exists()
