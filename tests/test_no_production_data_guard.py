"""The production-data guard in conftest must cover every place real data lives.

`assay-hygiene/` was a symlink tree into `assets/RUN1/`, so the guard -- which
keys on the RESOLVED path's tier names -- covered it for free. On 2026-09-10 the
links were replaced with real copies, the resolved path stopped naming a tier,
and eight tests the guard had been refusing went back to loading the real
extract: the load that OOM-killed this machine twice on 2026-09-01.
"""
import pandas as pd
import pytest

from conftest import _is_production_data


@pytest.mark.parametrize("rel", [
    "assay-hygiene/extract/samples.parquet",
    "assay-hygiene/findings.csv",
    "assay-hygiene-bak/extract/edges.parquet",
    "assets/RUN1/01-extract/samples.parquet",
    "assets/RUN2/09-relabel/relabel-before.csv.gz",
])
def test_every_real_data_location_is_refused(tmp_path, rel):
    assert _is_production_data(tmp_path / rel)


@pytest.mark.parametrize("rel", [
    "assets/rulings/pairs.tsv",
    "tests/fixtures/mode2-rulings.tsv",
    "out/findings.csv",
    "assay-hygiene/mode2-rulings.tsv",
])
def test_the_ruling_store_and_scratch_output_are_not(tmp_path, rel):
    assert not _is_production_data(tmp_path / rel)


def test_a_read_under_the_copied_folder_raises_before_it_allocates(tmp_path):
    f = tmp_path / "assay-hygiene" / "extract" / "samples.csv"
    f.parent.mkdir(parents=True)
    f.write_text("sample_id\n1\n")
    with pytest.raises(RuntimeError, match="production extract tier"):
        pd.read_csv(f)
