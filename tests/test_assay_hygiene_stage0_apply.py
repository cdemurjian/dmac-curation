"""Stage 0's write path: MERGE, manifest, rollback.

This is the only module in the pipeline that mutates production, so its three
safety properties are asserted directly rather than trusted:

  * it cannot delete            -- MERGE_CYPHER carries no removal clause
  * it cannot touch CHILD_OF    -- neither Cypher string names that type
  * a dry run is the default    -- `dry_run=False` is the only way to write

Each has at least one case that goes red the moment the property is removed;
that was verified by mutation, not assumed. The rest of the file exists because
the chunking loop and the NaN/float normalisation are the two places where a
silent defect writes wrong data to 90,000 relationships without failing.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import stage0, stage0_apply

DRIVER = REPO / "scripts" / "assay_hygiene" / "driver_stage0.py"

# nextseek_api/batch_upload/neo4j_sync.py:161-172, verbatim. Copied rather than
# imported: the server is a different checkout that this suite cannot import,
# and a paraphrase would make the mirror test a formality.
SERVER_CYPHER = """
    UNWIND $rows AS row
    MATCH (c:Sample {uuid: row.child_uuid})
    MATCH (p:Sample {uuid: row.parent_uuid})
    MERGE (c)-[r:DERIVED_FROM]->(p)
    SET r.protocol_id = row.protocol_id, r.protocol_title = row.protocol_title,
        r.assay_id = row.assay_id,
        r.internal_assay_id = row.internal_assay_id, r.internal_assay_title = row.internal_assay_title,
        r.child_id = row.child_id, r.parent_id = row.parent_id
    RETURN count(r) AS processed
    """


class FakeDriver:
    """Records every call instead of touching a database."""

    def __init__(self):
        self.calls = []

    def execute_query(self, cypher, params=None, database_=None):
        self.calls.append((cypher, params, database_))
        return None


def _resolved():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    return stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )


def _wide_plan(n: int) -> pd.DataFrame:
    """n synthetic edges carrying the exact plan column contract.

    The frozen fixture yields two edges, which cannot show an off-by-one in the
    chunking loop. This one can.
    """
    rows = [
        (1000 + i, f"D.IMG-260101ABC-{i}", 2000 + i, f"TIS-260101ABC-{i}",
         5, "Comet Chip SOP", 1, 11, "Comet Chip",
         "D.IMG", "TIS", "Parent", 1, "junction")
        for i in range(n)
    ]
    return pd.DataFrame(rows, columns=S.STAGE0_PLAN_COLUMNS)


def _labelled(payload):
    return [r for r in payload if r["parent_uuid"] == "TIS-260101ABC-1"][0]


def _dark(payload):
    return [r for r in payload if r["parent_uuid"] == "AB-260101ABC-1"][0]


# --- the three safety properties ---------------------------------------------

def test_dry_run_is_the_default_and_issues_no_query():
    driver = FakeDriver()
    manifest = stage0_apply.apply_edges(driver, "neo4j", _resolved())
    assert driver.calls == []
    assert len(manifest) == 2   # the manifest is still produced for review


def test_write_requires_an_explicit_flag():
    driver = FakeDriver()
    stage0_apply.apply_edges(driver, "neo4j", _resolved(), dry_run=False)
    assert len(driver.calls) == 1


def test_the_write_is_a_merge_and_can_never_delete():
    for forbidden in ("DELETE", "DETACH", "REMOVE"):
        assert forbidden not in stage0_apply.MERGE_CYPHER.upper()
    assert "MERGE" in stage0_apply.MERGE_CYPHER.upper()


def test_the_write_never_touches_child_of():
    # Operator ruling 2026-08-13.
    assert "CHILD_OF" not in stage0_apply.MERGE_CYPHER.upper()
    assert "CHILD_OF" not in stage0_apply.ROLLBACK_CYPHER.upper()


# --- the payload -------------------------------------------------------------

def test_payload_carries_only_the_server_model_fields():
    # DerivedFromRelRow is extra="forbid"; a reporting column leaking into the
    # payload is a hard rejection at the server.
    payload = stage0_apply.to_payload(_resolved())
    assert set(payload[0].keys()) == set(S.EDGE_ROW_COLUMNS)
    for extra in ("child_type", "parent_type", "field", "n_shared", "assay_source"):
        assert extra not in payload[0]


def test_dark_edges_carry_python_None_not_nan():
    # A dark edge's assay fields make those columns float64, so a naive
    # `.where(notna, None)` leaves NaN behind and the driver writes a float
    # rather than a null. Under this environment's pandas the same is true of a
    # STRING column: internal_assay_title is str dtype and its missing value
    # normalises to float nan, not None -- hence the title assertion, which is
    # the one Task 4 shipped a defect against.
    payload = stage0_apply.to_payload(_resolved())
    dark = _dark(payload)
    assert dark["assay_id"] is None
    assert dark["internal_assay_id"] is None
    assert dark["internal_assay_title"] is None


def test_an_all_null_optional_column_still_normalises_to_None():
    # The hostile shape the fixture cannot produce: every row dark, so the
    # column is float64 end to end and holds no object to fall back on. A title
    # column is included deliberately -- a null in a string column materialises
    # as float nan here just as it does in an id column.
    frame = _resolved().copy()
    for col in ("protocol_id", "protocol_title", "assay_id",
                "internal_assay_id", "internal_assay_title"):
        frame[col] = pd.Series([None, None], dtype="float64")
    for row in stage0_apply.to_payload(frame):
        for col in ("protocol_id", "protocol_title", "assay_id",
                    "internal_assay_id", "internal_assay_title"):
            assert row[col] is None, f"{col} came through as {row[col]!r}"


def test_integer_properties_are_written_as_integers_not_floats():
    # An optional id column is float64 the moment one row is dark, so the
    # labelled edge's internal_assay_id arrives as 11.0. Writing that stores a
    # Neo4j Float where the upload pipeline stores an Integer, and the design
    # rule is that a stage 0 edge is indistinguishable from a pipeline one.
    # `not isinstance(v, bool)` because bool is an int subclass; numpy scalars
    # fail the isinstance outright, which is the second thing this catches --
    # the Neo4j driver's packer rejects numpy.int64.
    labelled = _labelled(stage0_apply.to_payload(_resolved()))
    for field in ("child_id", "parent_id", "protocol_id", "assay_id",
                  "internal_assay_id"):
        value = labelled[field]
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{field} came through as {type(value).__name__} {value!r}"
        )
    assert labelled["assay_id"] == 1
    assert labelled["internal_assay_id"] == 11


def test_numpy_scalars_never_reach_the_driver():
    # The Neo4j driver's packstream packer rejects numpy.int64 outright -- it is
    # not an `int` subclass -- so it would fail mid-write, after earlier chunks
    # had already landed. numpy.float64 IS a float subclass and would pack
    # silently, as a Float. to_payload's astype(object) happens to strip both
    # today; apply_manifest takes rows from callers it does not control, so the
    # coercion is asserted rather than assumed.
    import numpy as np

    driver = FakeDriver()
    row = dict(stage0_apply.to_payload(_wide_plan(1))[0])
    row["child_id"] = np.int64(1000)
    row["internal_assay_id"] = np.float64(11.0)
    stage0_apply.apply_manifest(driver, "neo4j", [row])
    sent = driver.calls[0][1]["rows"][0]
    assert type(sent["child_id"]) is int
    assert type(sent["internal_assay_id"]) is int


def test_payload_is_json_round_trippable_with_no_nan():
    # driver_stage0.py reads the manifest back from jsonl. json.dumps accepts
    # NaN by DEFAULT and emits a bare `NaN` token that json.loads happily reads
    # back as a float and hands to Neo4j, so allow_nan=False is what makes this
    # a guard rather than a formality.
    payload = stage0_apply.to_payload(_resolved())
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_created_edges_carry_no_marker_property():
    # A marker would make stage 0 edges distinguishable from pipeline-produced
    # ones and would leak into every downstream query. The manifest is the record.
    payload = stage0_apply.to_payload(_resolved())
    for key in payload[0]:
        assert "backfill" not in key.lower()
        assert "stage0" not in key.lower()


# --- payload validation (mirrors DerivedFromRelRow's own validators) ----------

def test_a_non_integer_id_is_refused_rather_than_truncated():
    frame = _resolved().copy()
    frame["internal_assay_id"] = pd.Series([11.5, None], dtype="float64")
    with pytest.raises(ValueError, match="internal_assay_id"):
        stage0_apply.to_payload(frame)


def test_a_missing_required_id_is_refused():
    # DerivedFromRelRow declares child_id as a required positive int, and
    # nothing validates the payload between here and the graph, so a null would
    # go out as `r.child_id = null` on a real relationship.
    frame = _resolved().copy()
    frame["child_id"] = pd.Series([None, 100], dtype="float64")
    with pytest.raises(ValueError, match="child_id"):
        stage0_apply.to_payload(frame)


def test_a_non_positive_id_is_refused():
    frame = _resolved().copy()
    frame["parent_id"] = pd.Series([0, 300], dtype="int64")
    with pytest.raises(ValueError, match="parent_id"):
        stage0_apply.to_payload(frame)


def test_a_blank_uuid_is_refused():
    # An empty uuid matches no Sample node, so the MERGE creates nothing while
    # the manifest claims an edge -- a silent shortfall the operator cannot see.
    frame = _resolved().copy()
    frame["parent_uuid"] = ["   ", "AB-260101ABC-1"]
    with pytest.raises(ValueError, match="parent_uuid"):
        stage0_apply.to_payload(frame)


def test_uuids_are_passed_through_unmodified():
    # The server strips uuids (models.py:476) because it builds nodes from an
    # upload sheet. These uuids came from the graph's OWN node index and are
    # MATCH keys, so stripping one could silently fail to match a node that a
    # padded uuid would have found. Deliberate divergence.
    frame = _resolved().copy()
    frame["child_uuid"] = [" D.IMG-260101ABC-1 ", " D.IMG-260101ABC-1 "]
    for row in stage0_apply.to_payload(frame):
        assert row["child_uuid"] == " D.IMG-260101ABC-1 "


# --- the manifest ------------------------------------------------------------

def test_manifest_records_one_line_per_edge_with_full_properties():
    manifest = stage0_apply.apply_edges(FakeDriver(), "neo4j", _resolved(), dry_run=False)
    assert len(manifest) == 2
    for row in manifest:
        assert set(S.EDGE_ROW_COLUMNS) <= set(row.keys())


def test_the_dry_run_manifest_is_exactly_what_a_write_would_send():
    # The operator gates on the dry run's manifest. If the write recomputed a
    # different payload, the review would have been of something else.
    resolved = _resolved()
    reviewed = stage0_apply.apply_edges(FakeDriver(), "neo4j", resolved)
    driver = FakeDriver()
    stage0_apply.apply_edges(driver, "neo4j", resolved, dry_run=False)
    assert driver.calls[0][1]["rows"] == reviewed


# --- the write loop ----------------------------------------------------------

def test_every_edge_is_written_exactly_once_across_chunks():
    driver = FakeDriver()
    manifest = stage0_apply.apply_edges(
        driver, "neo4j", _wide_plan(5), dry_run=False, chunk_size=2
    )
    assert [len(params["rows"]) for _c, params, _d in driver.calls] == [2, 2, 1]
    sent = [row for _c, params, _d in driver.calls for row in params["rows"]]
    assert sent == manifest


def test_the_write_uses_the_reviewed_cypher_and_the_named_database():
    driver = FakeDriver()
    stage0_apply.apply_edges(driver, "graph.db", _resolved(), dry_run=False)
    cypher, _params, database = driver.calls[0]
    assert cypher == stage0_apply.MERGE_CYPHER
    assert database == "graph.db"


def test_a_chunk_size_below_one_is_refused():
    # `range(0, n, -1)` is empty, so a negative chunk size would issue no query
    # at all and still return a full manifest -- indistinguishable from a
    # successful run. Refused on the DRY RUN too, so the operator's gate catches
    # it rather than the write.
    with pytest.raises(ValueError, match="chunk_size"):
        stage0_apply.apply_edges(FakeDriver(), "neo4j", _resolved(), chunk_size=0)
    with pytest.raises(ValueError, match="chunk_size"):
        stage0_apply.apply_edges(
            FakeDriver(), "neo4j", _resolved(), dry_run=False, chunk_size=-1
        )


def test_an_empty_plan_issues_no_query():
    # The steady state after a successful run. Re-running must be a no-op.
    driver = FakeDriver()
    empty = pd.DataFrame(columns=S.STAGE0_PLAN_COLUMNS)
    assert stage0_apply.apply_edges(driver, "neo4j", empty, dry_run=False) == []
    assert driver.calls == []


def test_apply_refuses_a_frame_with_unexpected_columns():
    driver = FakeDriver()
    bad = _resolved().drop(columns=["assay_source"])
    with pytest.raises(ValueError, match="columns"):
        stage0_apply.apply_edges(driver, "neo4j", bad, dry_run=False)
    assert driver.calls == []


def test_apply_refuses_a_frame_whose_columns_are_out_of_order():
    # itertuples-style positional reads run through this pipeline; a reordered
    # frame that still holds the right names must not be quietly accepted.
    driver = FakeDriver()
    cols = list(S.STAGE0_PLAN_COLUMNS)
    cols[0], cols[2] = cols[2], cols[0]
    with pytest.raises(ValueError, match="columns"):
        stage0_apply.apply_edges(driver, "neo4j", _resolved()[cols], dry_run=False)
    assert driver.calls == []


# --- the manifest entry point the in-container driver uses -------------------

def test_apply_manifest_writes_the_rows_it_is_given():
    driver = FakeDriver()
    manifest = stage0_apply.to_payload(_wide_plan(5))
    assert stage0_apply.apply_manifest(driver, "neo4j", manifest, chunk_size=2) == 5
    sent = [row for _c, params, _d in driver.calls for row in params["rows"]]
    assert sent == manifest
    assert all(c == stage0_apply.MERGE_CYPHER for c, _p, _d in driver.calls)


def test_apply_manifest_reports_a_running_total_per_chunk():
    # The driver's only output during a ~90k write. It must be the RUNNING
    # total, not the chunk size: an operator watching "20,000" five times cannot
    # tell progress from a stuck loop, and after a part-way failure the last
    # line is what says how far the write got.
    seen = []
    stage0_apply.apply_manifest(
        FakeDriver(), "neo4j", stage0_apply.to_payload(_wide_plan(5)),
        chunk_size=2, progress=lambda done, total: seen.append((done, total)),
    )
    assert seen == [(2, 5), (4, 5), (5, 5)]


def test_apply_manifest_refuses_a_row_with_an_unexpected_key():
    # DerivedFromRelRow is extra="forbid". The manifest arrives from disk on the
    # box, so this is the last place a hand-edited key can be caught.
    driver = FakeDriver()
    rows = stage0_apply.to_payload(_resolved())
    rows[0]["assay_source"] = "junction"
    with pytest.raises(ValueError, match="assay_source"):
        stage0_apply.apply_manifest(driver, "neo4j", rows)
    assert driver.calls == []


def test_apply_manifest_refuses_a_nan_read_back_from_jsonl():
    # `json.loads('{"assay_id": NaN}')` succeeds and yields float nan. Without
    # this the in-container path would write a NaN property that the laptop's
    # dry run never showed.
    driver = FakeDriver()
    rows = json.loads(json.dumps(stage0_apply.to_payload(_resolved())).replace(
        '"assay_id": null', '"assay_id": NaN'))
    with pytest.raises(ValueError, match="assay_id"):
        stage0_apply.apply_manifest(driver, "neo4j", rows)
    assert driver.calls == []


def test_apply_manifest_validates_every_row_before_the_first_chunk_lands():
    # A bad row in the LAST chunk must abort before ANY chunk is sent.
    # Production is 90,534 rows across 5 chunks, and a partial write is the
    # expensive failure: the graph holds a prefix nobody recorded, and the
    # manifest that rollback needs describes the whole run. The two other
    # refusal cases use a 2-row manifest at the default chunk size, so both
    # would survive the validation being moved inside the loop; this one would
    # not.
    driver = FakeDriver()
    rows = stage0_apply.to_payload(_wide_plan(5))
    rows[4]["child_id"] = 0
    with pytest.raises(ValueError, match="child_id"):
        stage0_apply.apply_manifest(driver, "neo4j", rows, chunk_size=2)
    assert driver.calls == []


# --- rollback ----------------------------------------------------------------

def test_rollback_targets_exactly_the_manifest_pairs():
    driver = FakeDriver()
    manifest = stage0_apply.apply_edges(FakeDriver(), "neo4j", _resolved(), dry_run=False)
    n = stage0_apply.rollback(driver, "neo4j", manifest)
    assert n == 2
    cypher, params, _db = driver.calls[0]
    # Every OTHER rollback guard reads the module constant. Without this line
    # the constant can stay pristine while the call site sends an inlined
    # literal -- an unbound parent endpoint, an untyped `-[r]->` that reaches
    # CHILD_OF, or a DETACH DELETE of the Sample node itself. All four of those
    # were verified to pass the entire file before this assertion existed.
    assert cypher == stage0_apply.ROLLBACK_CYPHER
    pairs = {(r["child_uuid"], r["parent_uuid"]) for r in params["rows"]}
    assert pairs == {
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
        ("D.IMG-260101ABC-1", "AB-260101ABC-1"),
    }


def test_rollback_deletes_only_derived_from():
    assert "DERIVED_FROM" in stage0_apply.ROLLBACK_CYPHER
    assert "DELETE" in stage0_apply.ROLLBACK_CYPHER.upper()


def test_rollback_binds_both_endpoints_to_the_manifest_row():
    # Dropping `{uuid: row.parent_uuid}` from the MATCH turns the rollback into
    # "remove every DERIVED_FROM out of this child", which would delete lineage
    # stage 0 never created. Nothing about the call shape reveals that -- the
    # params are identical -- so it is asserted on the Cypher itself.
    for bound in ("row.child_uuid", "row.parent_uuid"):
        assert bound in stage0_apply.ROLLBACK_CYPHER, bound
    assert stage0_apply.ROLLBACK_CYPHER.count("uuid:") == 2


def test_rollback_cypher_is_pinned():
    """The delete path, pinned character for character.

    A change-detector on purpose, and the one place it is the right test: any
    edit to the only statement in this pipeline that removes production data
    should have to come here and be read alongside its reason. Compared on
    collapsed whitespace so re-wrapping alone is not the subject.
    """
    assert " ".join(stage0_apply.ROLLBACK_CYPHER.split()) == (
        "UNWIND $rows AS row "
        "MATCH (c:Sample {uuid: row.child_uuid})-[r:DERIVED_FROM]->"
        "(p:Sample {uuid: row.parent_uuid}) "
        "DELETE r "
        "RETURN count(*) AS removed"
    )


def test_rollback_can_never_create_or_set():
    # The inverse of the MERGE guard: a rollback that writes is not a rollback.
    for forbidden in ("MERGE", "CREATE", "SET "):
        assert forbidden not in stage0_apply.ROLLBACK_CYPHER.upper()


def test_rollback_carries_only_the_pair_and_chunks():
    driver = FakeDriver()
    manifest = stage0_apply.to_payload(_wide_plan(5))
    assert stage0_apply.rollback(driver, "neo4j", manifest, chunk_size=2) == 5
    assert [len(params["rows"]) for _c, params, _d in driver.calls] == [2, 2, 1]
    for cypher, params, _d in driver.calls:
        # EVERY chunk, not just the first: a call site that sent the constant
        # once and a literal thereafter would still satisfy a head-only check.
        assert cypher == stage0_apply.ROLLBACK_CYPHER
        for row in params["rows"]:
            # Properties must not travel: a rollback keyed on anything but the
            # pair could match a relationship this run did not create.
            assert set(row) == {"child_uuid", "parent_uuid"}


def test_rollback_of_an_empty_manifest_issues_no_query():
    driver = FakeDriver()
    assert stage0_apply.rollback(driver, "neo4j", []) == 0
    assert driver.calls == []


def test_rollback_refuses_a_chunk_size_below_one():
    with pytest.raises(ValueError, match="chunk_size"):
        stage0_apply.rollback(
            FakeDriver(), "neo4j", stage0_apply.to_payload(_resolved()), chunk_size=0
        )


def test_rollback_refuses_a_manifest_row_with_no_pair():
    driver = FakeDriver()
    with pytest.raises((KeyError, ValueError)):
        stage0_apply.rollback(driver, "neo4j", [{"child_id": 1}])
    assert driver.calls == []


# --- the mirror and the in-container driver ----------------------------------

def test_the_merge_cypher_mirrors_the_servers_own_write():
    # Compared on collapsed whitespace so line wrapping is not the subject.
    assert " ".join(stage0_apply.MERGE_CYPHER.split()) == " ".join(SERVER_CYPHER.split())


def test_the_merge_cypher_names_every_field_the_schema_declares():
    # A column added to EDGE_ROW_COLUMNS but not to the Cypher would ride in the
    # payload and never reach the relationship.
    for column in S.EDGE_ROW_COLUMNS:
        assert f"row.{column}" in stage0_apply.MERGE_CYPHER, column


def test_the_in_container_driver_reuses_the_reviewed_cypher():
    # The driver is where the real write happens. A copy of the Cypher there
    # would be a second string nobody reviewed and no test covers.
    src = DRIVER.read_text()
    assert "stage0_apply.apply_manifest" in src
    assert "UNWIND" not in src
    assert "MERGE" not in src


def test_the_in_container_driver_cannot_delete_and_never_names_child_of():
    """No destructive vocabulary anywhere in the file, code or prose.

    Deliberately stricter than "no reachable delete". This file is piped
    straight into a production shell, so a commented-out removal is one
    uncomment away from running, and a rollback call sitting beside the write is
    a rollback that gets run by mistake. The undo is documented in stage0_apply
    as a paste instead.
    """
    src = DRIVER.read_text().upper()
    for forbidden in ("DELETE", "DETACH", "REMOVE", "CHILD_OF", "ROLLBACK"):
        assert forbidden not in src, forbidden
