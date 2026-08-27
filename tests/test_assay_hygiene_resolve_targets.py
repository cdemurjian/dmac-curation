"""SEEK assay ids are per-project, and a wrong one is unrecoverable.

The 2026-08-26 audit found 578 of 26,188 rows targeting an assay in a different
project than the sample. Once written, the sample joins a project it does not
belong to and nothing undoes that from the outside.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import resolve_targets as T  # noqa: E402


@pytest.fixture
def assays():
    # internal assay 74 exists in project 1 (as seek 501) and project 2 (as 502)
    return pd.DataFrame({
        "assay_id": [501, 502, 503],
        "internal_assay_id": [74.0, 74.0, 99.0],
        "project_id": [1, 2, 1],
    })


@pytest.fixture
def samples():
    return pd.DataFrame({
        "sample_id": [10, 20, 30],
        "project_ids": [[1], [2], []],
    })


def test_a_sample_resolves_to_its_OWN_projects_assay(assays, samples):
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501]
    assert excluded.empty


def test_the_same_internal_id_resolves_DIFFERENTLY_per_project(assays, samples):
    rows = pd.DataFrame({"sample_id": [10, 20], "internal_assay_id": [74, 74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501, 502]


def test_a_sample_with_no_project_is_excluded_not_guessed(assays, samples):
    """374 RUN1 rows were in this state. No correct target exists."""
    rows = pd.DataFrame({"sample_id": [30], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.empty
    assert excluded.reason.tolist() == [T.NO_PROJECT]


def test_a_project_with_no_such_assay_is_excluded(assays, samples):
    """45 RUN1 rows were in this state."""
    rows = pd.DataFrame({"sample_id": [20], "internal_assay_id": [99]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.empty
    assert excluded.reason.tolist() == [T.NO_CANDIDATE]


def test_every_manifest_row_is_project_ok(assays, samples):
    rows = pd.DataFrame({"sample_id": [10, 20, 30],
                         "internal_assay_id": [74, 74, 74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.project_ok.all()


def test_assert_subset_passes_for_a_sheet_built_from_the_manifest(assays, samples):
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    sheet = manifest[["sample_id", T.TARGET_COLUMN]].rename(
        columns={T.TARGET_COLUMN: "assay_id"})
    T.assert_subset(sheet, manifest)          # must not raise


def test_assert_subset_refuses_an_INJECTED_cross_project_row(assays, samples):
    """Proven by injection, as the spec requires."""
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [502]})   # other project
    with pytest.raises(T.CrossProjectTarget, match="502"):
        T.assert_subset(sheet, manifest)
