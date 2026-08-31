"""The post-write graph relabel: recompute DERIVED_FROM assay labels.

Reference figures come from the production run of 2026-08-28, recorded in
`docs/superpowers/specs/2026-08-31-assay-relabel-final-stage-handoff.md`. This
module reproduces that run's arithmetic offline against `assets/RUN2/01-extract`,
which is the pre-relabel state: 367,493 of 802,231 edges carried a label.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import relabel as R  # noqa: E402


@pytest.fixture
def assays():
    """Assay 100 has a junction row; 200 falls back to being its own id."""
    return pd.DataFrame({
        "assay_id": [100, 200],
        "title": ["Flow Cytometry", "Bare Assay"],
        "sample_type_id": [1, 1], "study_id": [1, 1],
        "investigation_id": [1, 1], "project_id": [1, 1],
        "project_title": ["p", "p"],
        "internal_assay_id": [30.0, None],
        "internal_assay_title": ["Flow Cytometry", None],
    })


@pytest.fixture
def samples():
    return pd.DataFrame({
        "sample_id": [1, 2],
        "uuid": ["CEL-1", "TIS-2"],
        "json_metadata": ["{}", "{}"],
        "created_at": ["2026-01-01", "2026-01-01"],
        "project_ids": ["1", "1"],
    })


@pytest.fixture
def sops():
    return pd.DataFrame({"sop_id": [], "title": []})


@pytest.fixture
def membership():
    """Both endpoints registered in assay 100, so they share it."""
    return pd.DataFrame({"sample_id": [1, 2], "assay_id": [100, 100]})


def _edge(current):
    return pd.DataFrame({
        "child_id": [1], "parent_id": [2],
        "child_uuid": ["CEL-1"], "parent_uuid": ["TIS-2"],
        "child_type": ["CEL"], "parent_type": ["TIS"],
        "edge_internal_assay_id": [current],
        "edge_internal_assay_title": [None],
        "edge_protocol_id": [None],
    })


def test_an_unlabelled_edge_whose_endpoints_share_an_assay_is_a_gain(
        samples, membership, assays, sops):
    """The 416,355 bucket: no label, endpoints share one, so it gains it."""
    plan = R.plan_relabel(_edge(None), samples, membership, assays, sops)

    assert list(plan.disposition) == [R.D_GAIN]
    assert list(plan.after_internal_assay_id) == [30]
    assert pd.isna(plan.before_internal_assay_id.iloc[0])
    assert len(R.write_set(plan)) == 1


def test_a_correctly_labelled_edge_is_unchanged_and_is_not_written(
        samples, membership, assays, sops):
    """The 367,198 bucket: computed and then deliberately not touched."""
    plan = R.plan_relabel(_edge(30.0), samples, membership, assays, sops)

    assert list(plan.disposition) == [R.D_UNCHANGED]
    assert R.write_set(plan).empty


def test_an_edge_carrying_the_wrong_label_is_a_change(
        samples, membership, assays, sops):
    """The 213 bucket: it has a label, but not the one the rule computes."""
    plan = R.plan_relabel(_edge(999.0), samples, membership, assays, sops)

    assert list(plan.disposition) == [R.D_CHANGE]
    assert list(plan.before_internal_assay_id) == [999]
    assert list(plan.after_internal_assay_id) == [30]
    assert len(R.write_set(plan)) == 1


def test_an_unlabelled_edge_with_no_shared_assay_stays_dark(
        samples, assays, sops):
    """The 18,383 bucket: no label is possible, so none is invented."""
    apart = pd.DataFrame({"sample_id": [1, 2], "assay_id": [100, 200]})
    plan = R.plan_relabel(_edge(None), samples, apart, assays, sops)

    assert list(plan.disposition) == [R.D_NO_SHARED]
    assert R.write_set(plan).empty


def test_an_edge_whose_endpoints_no_longer_share_an_assay_is_never_cleared(
        samples, assays, sops):
    """The 82 bucket. Reported, and left alone unless explicitly opted into.

    Clearing is the one destructive thing this stage could do, so the default
    refuses it: the edge keeps a label its endpoints no longer justify, and the
    count is surfaced rather than acted on.
    """
    apart = pd.DataFrame({"sample_id": [1, 2], "assay_id": [100, 200]})
    plan = R.plan_relabel(_edge(30.0), samples, apart, assays, sops)

    assert list(plan.disposition) == [R.D_WOULD_CLEAR]
    assert R.write_set(plan).empty, "would_clear must not be written by default"
    assert len(R.write_set(plan, allow_clear=True)) == 1


# --- the golden test: reproduce the production run of 2026-08-28 -------------

EXTRACT = REPO / "assets" / "RUN2" / "01-extract"

# From the hand run on production, recorded in the handoff spec. RUN2's extract
# IS that run's input: it was pulled 2026-08-27, after the registration write
# and before the relabel, and holds 367,493 labelled edges of 802,231. If this
# module's arithmetic is right it must land on these five numbers exactly.
PRODUCTION_2026_08_28 = {
    R.D_GAIN: 416_355,
    R.D_CHANGE: 213,
    R.D_UNCHANGED: 367_198,
    R.D_NO_SHARED: 18_383,
    R.D_WOULD_CLEAR: 82,
}


def test_the_real_extract_reproduces_the_production_relabel():
    """The whole stage, measured against a run that actually happened.

    This is the only evidence that the reimplementation agrees with what was
    applied to production. The five counts are independent -- a rule that is
    subtly wrong moves at least two of them -- and they must sum to the edge
    count, which is the check that no edge fell out of the plan.
    """
    if not (EXTRACT / "edges.parquet").exists():
        pytest.skip("no extract; nothing to measure the relabel over")

    read = lambda n: pd.read_parquet(EXTRACT / f"{n}.parquet")  # noqa: E731
    edges = read("edges")
    plan = R.plan_relabel(edges, read("samples"), read("membership"),
                          read("assays"), read("sops"))

    assert R.census(plan) == PRODUCTION_2026_08_28
    assert len(plan) == len(edges) == 802_231
    assert sum(R.census(plan).values()) == len(edges)
    # 416,355 + 213 -- the writes the production run actually applied
    assert len(R.write_set(plan)) == 416_568


# --- step one: the backup, before anything is computed or written ------------


def test_the_backup_holds_EVERY_edge_not_just_the_ones_being_written(tmp_path):
    """The undo has to reach edges this run does not touch.

    A backup of the write set alone cannot restore an edge some *other* process
    changed inside the window, and it is exactly as expensive to take the whole
    graph -- one pass over a frame already in memory.
    """
    edges = pd.concat([_edge(30.0), _edge(None)], ignore_index=True)
    target = tmp_path / "before.csv.gz"

    R.back_up_edges(edges, target)

    assert target.exists()
    assert len(pd.read_csv(target)) == 2


def test_backing_up_nothing_refuses_rather_than_writing_an_empty_file(tmp_path):
    """An archive of an absent graph reports success and restores nothing."""
    with pytest.raises(R.BackupUnverified):
        R.back_up_edges(pd.DataFrame(columns=["child_uuid"]),
                        tmp_path / "before.csv.gz")


def test_the_undo_restores_the_before_label_and_never_deletes(samples,
                                                              membership,
                                                              assays, sops):
    """`stage0_apply.rollback` DELETEs its manifest's edges. Here that would
    destroy 416,568 relationships that already existed, so the undo is a
    SET-back built from the `before_` half of the plan."""
    plan = R.plan_relabel(_edge(999.0), samples, membership, assays, sops)
    undo = R.undo_set(R.write_set(plan))

    assert list(undo.internal_assay_id) == [999]
    assert list(undo.child_uuid) == ["CEL-1"]
    assert "DELETE" not in R.SET_CYPHER.upper()
    assert "MERGE" not in R.SET_CYPHER.upper(), "MERGE could create an edge"


def test_a_missing_label_travels_as_null_and_never_as_nan(samples, assays,
                                                          sops):
    """NaN is a float. Sent to the graph it stores a Float where the server
    writes null, and it is not valid JSON on the way there either."""
    apart = pd.DataFrame({"sample_id": [1, 2], "assay_id": [100, 200]})
    plan = R.plan_relabel(_edge(30.0), samples, apart, assays, sops)
    rows = R.to_rows(R.write_set(plan, allow_clear=True), half="after")

    assert rows[0]["internal_assay_id"] is None
    assert rows[0]["internal_assay_title"] is None
    assert list(rows[0]) == R.SET_ROW_COLUMNS


def test_to_rows_before_half_is_the_undo(samples, membership, assays, sops):
    plan = R.plan_relabel(_edge(999.0), samples, membership, assays, sops)
    written = R.write_set(plan)

    assert R.to_rows(written, half="after")[0]["internal_assay_id"] == 30
    assert R.to_rows(written, half="before")[0]["internal_assay_id"] == 999


# --- the write itself --------------------------------------------------------


class FakeDriver:
    """Records what would have been sent. No graph, no network."""

    def __init__(self):
        self.calls = []

    def execute_query(self, query, params, database_=None):
        self.calls.append((query, params["rows"], database_))
        return [], None, None


def test_the_write_is_chunked_and_reports_progress():
    """A write this size with no output leaves the operator unable to tell a
    slow chunk from a hung one, and the running total is what says how far a
    part-way failure got."""
    rows = [{"child_uuid": f"C-{i}", "parent_uuid": "P", "assay_id": 1,
             "internal_assay_id": 1, "internal_assay_title": "t"}
            for i in range(250)]
    driver, seen = FakeDriver(), []

    sent = R.apply_rows(driver, "neo4j", rows, chunk_size=100,
                        progress=lambda d, t: seen.append((d, t)))

    assert sent == 250
    assert [len(c[1]) for c in driver.calls] == [100, 100, 50]
    assert seen == [(100, 250), (200, 250), (250, 250)]
    assert all(c[0] is R.SET_CYPHER for c in driver.calls)


def test_the_in_container_driver_carries_no_destructive_vocabulary():
    """`driver_relabel.py` is pipeable into a production shell. The undo is a
    documented paste in this module, deliberately not a second pipeable file,
    so it cannot be run by accident."""
    src = (REPO / "scripts" / "assay_hygiene" / "driver_relabel.py").read_text()

    for word in ("DELETE", "DETACH", "REMOVE", "MERGE", "undo_set"):
        assert word not in src, f"{word} must not appear in the piped driver"
