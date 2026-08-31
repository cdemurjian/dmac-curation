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
        # the real extract's shape: GROUP_CONCAT string, null for no project
        "project_ids": ["1", "2", None],
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


# --- the shape the REAL extract emits ----------------------------------------
#
# `extract.py` builds this column with `GROUP_CONCAT(ps.project_id)`, so on the
# production extract `project_ids` is a COMMA-JOINED STRING and not a list --
# and it is null, not empty, for a sample in no project. The fixtures above feed
# lists, so every test in this file passed against a shape the pipeline never
# produces. Measured on the RUN2 extract: 166,235 samples, 47,684 of them
# carrying a multi-character value and 435 carrying null.
#
# `list("10")` is `["1", "0"]`. That resolves a sample in project 10 against
# projects 1 and 0, and if either holds the internal assay the row gets a
# WRONG TARGET with `project_ok=True` on it. This is the exact defect the
# module docstring calls unrecoverable, reached through the gate meant to stop
# it. `classify.project_index` is the package's one reader of this column.


@pytest.fixture
def real_shape_samples():
    return pd.DataFrame({
        "sample_id": [10, 20, 30, 40, 50],
        "project_ids": ["1", "2", None, "10", "2,2"],
    })


@pytest.fixture
def wide_assays():
    # internal 74 in projects 1, 2 and 10; internal 99 only in project 1
    return pd.DataFrame({
        "assay_id": [501, 502, 503, 510],
        "internal_assay_id": [74.0, 74.0, 99.0, 74.0],
        "project_id": [1, 2, 1, 10],
    })


def test_a_comma_joined_project_string_is_parsed_not_iterated(
        wide_assays, real_shape_samples):
    """`10` is one project, not the two projects `1` and `0`."""
    rows = pd.DataFrame({"sample_id": [40], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert excluded.empty, f"sample 40 was dropped: {excluded.to_dict('records')}"
    assert manifest.write_target_seek_assay_id.tolist() == [510], (
        "a sample in project 10 must resolve to project 10's assay; iterating "
        "the string yields projects 1 and 0 and silently targets another one")


def test_a_null_project_string_is_excluded_and_does_not_raise(
        wide_assays, real_shape_samples):
    rows = pd.DataFrame({"sample_id": [30], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert manifest.empty
    assert excluded.reason.tolist() == [T.NO_PROJECT]


def test_group_concat_repeating_one_project_is_not_ambiguous(
        wide_assays, real_shape_samples):
    """`2,2` is the raw GROUP_CONCAT spelling of one project, seen in the real data."""
    rows = pd.DataFrame({"sample_id": [50], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert excluded.empty
    assert manifest.write_target_seek_assay_id.tolist() == [502]


# --- absent from the extract is not the same as absent from every project -----
#
# `project_index` returns a key for EVERY sample in the extract, mapping to the
# empty string where the sample is in no project. So an id missing from that
# dict was never in the extract at all, and saying it "belongs to no project"
# states something about a sample that is not there to state it about. On the
# RUN2 approved rows the single old reason covered 242 rows: 63 samples that are
# in the extract with no project membership, and 179 that have no `samples` row
# to check -- Neo4j nodes with no MySQL row behind them. The two need different
# work from a curator (fix the membership, versus find out why the sample is not
# in the extract), so they are reported apart.


def test_a_sample_absent_from_the_extract_is_NOT_reported_as_projectless(
        wide_assays, real_shape_samples):
    """Sample 60 has no row in the extract; there is nothing to have a project."""
    rows = pd.DataFrame({"sample_id": [60], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert manifest.empty
    assert excluded.reason.tolist() == [T.NOT_IN_EXTRACT]


def test_the_two_absences_are_reported_under_DIFFERENT_reasons(
        wide_assays, real_shape_samples):
    """30 is in the extract with a null project; 60 is not in the extract."""
    rows = pd.DataFrame({"sample_id": [30, 60], "internal_assay_id": [74, 74]})
    _, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert excluded.reason.tolist() == [T.NO_PROJECT, T.NOT_IN_EXTRACT]
    assert T.NOT_IN_EXTRACT != T.NO_PROJECT


def test_splitting_the_reason_excludes_exactly_the_same_rows(
        wide_assays, real_shape_samples):
    """Only the reporting changed: no row moves between kept and dropped."""
    rows = pd.DataFrame({"sample_id": [10, 20, 30, 40, 50, 60],
                         "internal_assay_id": [74, 74, 74, 74, 74, 74]})
    manifest, excluded = T.resolve(rows, wide_assays, real_shape_samples)
    assert manifest.sample_id.tolist() == [10, 20, 40, 50]
    assert excluded.sample_id.tolist() == [30, 60]
