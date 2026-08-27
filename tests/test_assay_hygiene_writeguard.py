"""A run must never write through a symlink into the preserved baseline.

`assay-hygiene/` is 33 symlinks into `assets/RUN1/`. Writing `findings.csv`
there does not create a file -- it follows the link and overwrites the RUN1
artifact that every before/after measurement is compared against. The tiers
that hold rulings are chmod a-w and resist; `04-artifacts` is writable and does
not.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene._writeguard import assert_writable, SymlinkWriteRefused  # noqa: E402


def test_a_plain_directory_is_writable(tmp_path):
    assert_writable(tmp_path, ["findings.csv"])          # must not raise


def test_a_symlinked_target_is_refused(tmp_path):
    real = tmp_path / "baseline"; real.mkdir()
    (real / "findings.csv").write_text("the RUN1 baseline")
    out = tmp_path / "out"; out.mkdir()
    (out / "findings.csv").symlink_to(real / "findings.csv")

    with pytest.raises(SymlinkWriteRefused, match="findings.csv"):
        assert_writable(out, ["findings.csv"])


def test_the_refusal_names_every_offender_not_just_the_first(tmp_path):
    real = tmp_path / "baseline"; real.mkdir()
    out = tmp_path / "out"; out.mkdir()
    for name in ("findings.csv", "claims.parquet"):
        (real / name).write_text("x")
        (out / name).symlink_to(real / name)

    with pytest.raises(SymlinkWriteRefused) as excinfo:
        assert_writable(out, ["findings.csv", "claims.parquet"])
    assert "findings.csv" in str(excinfo.value)
    assert "claims.parquet" in str(excinfo.value)


def test_a_missing_name_is_fine(tmp_path):
    """A file that does not exist yet is the normal case, not an error."""
    assert_writable(tmp_path, ["not-created-yet.csv"])


def test_a_symlinked_OUT_DIR_is_refused(tmp_path):
    """The whole directory being a link is the same hazard one level up."""
    real = tmp_path / "baseline"; real.mkdir()
    out = tmp_path / "out"
    out.symlink_to(real, target_is_directory=True)

    with pytest.raises(SymlinkWriteRefused):
        assert_writable(out, ["findings.csv"])
