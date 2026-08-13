# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage 0 write path: MERGE DERIVED_FROM, record a manifest, support rollback.

Mirrors neo4j_sync.bulk_merge_relationships (neo4j_sync.py:157). The driver is
duck-typed so the whole path is unit-testable with a fake; the real Neo4j
driver is bound only in driver_stage0.py.

Three properties hold by construction rather than by care, and each has a test
that goes red the moment it is removed:

  * it cannot delete -- MERGE_CYPHER carries no removal clause, and the only
    removal path in the module is `rollback`, which targets exactly the
    (child_uuid, parent_uuid) pairs a prior run recorded in a manifest;
  * it cannot touch CHILD_OF -- operator ruling 2026-08-13; neither Cypher
    string names that relationship type;
  * a dry run is the default -- `dry_run=False` is the only way to write, and a
    dry run still produces the full manifest so the operator reviews exactly
    what would go out.

`apply_edges` is the laptop's entry point (a plan frame in, a manifest out).
`apply_manifest` is the box's (manifest rows in, a write out). They share the
same chunking and the same row normalisation, so the loop that actually writes
production is the loop the tests exercise.
"""
from __future__ import annotations

import math
import numbers

import pandas as pd

from . import _schema as S

# Matches the server's own default (neo4j_sync.py:158). Named here so
# driver_stage0.py does not restate it.
CHUNK_SIZE = 20_000

MERGE_CYPHER = """
UNWIND $rows AS row
MATCH (c:Sample {uuid: row.child_uuid})
MATCH (p:Sample {uuid: row.parent_uuid})
MERGE (c)-[r:DERIVED_FROM]->(p)
SET r.protocol_id = row.protocol_id, r.protocol_title = row.protocol_title,
    r.assay_id = row.assay_id,
    r.internal_assay_id = row.internal_assay_id,
    r.internal_assay_title = row.internal_assay_title,
    r.child_id = row.child_id, r.parent_id = row.parent_id
RETURN count(r) AS processed
"""

# Keyed on the pair alone, so it removes what the manifest says was created --
# but "what the manifest says" was decided when `existing` was extracted, and
# the write happens later. Two DIFFERENT things live in that window, and the
# operator owns both:
#
#   Benign. Some other process added a SECOND DERIVED_FROM between the same two
#   nodes after the write. This removes that one too. Stage 0 cannot create a
#   duplicate (the planner drops any pair that already has an edge --
#   stage0.py:77-79 -- and MERGE is idempotent), so only an intervening write
#   can reach that state.
#
#   NOT benign, and NOT recoverable. batch_upload creates a DERIVED_FROM for a
#   PLANNED pair inside the extract->write window. The planner never saw it, so
#   the pair is still in the manifest; the MERGE then MATCHES that edge instead
#   of creating it and overwrites all seven properties through the unconditional
#   SET above; and this rollback then DELETEs a relationship stage 0 never
#   created. Rollback restores NOTHING here -- the overwritten property values
#   are gone with no record of what they were, and the edge itself is removed.
#   The unconditional SET is inherited from the server mirror
#   (neo4j_sync.py:167-172) and is not ours to change, so the mitigation is
#   procedural: re-extract `existing` immediately before the write and reconcile
#   the two counts, or quiesce batch_upload for the window.
ROLLBACK_CYPHER = """
UNWIND $rows AS row
MATCH (c:Sample {uuid: row.child_uuid})-[r:DERIVED_FROM]->(p:Sample {uuid: row.parent_uuid})
DELETE r
RETURN count(*) AS removed
"""

# The properties DerivedFromRelRow (models.py:457) types as integers. A pandas
# column holding one null is float64 for the whole frame, so without this the
# labelled edges go out carrying 11.0 and the graph stores a Float where the
# upload pipeline stores an Integer -- which would make a stage 0 edge
# distinguishable from a pipeline one, the one thing this stage must not be.
_INT_FIELDS = frozenset({
    "child_id", "parent_id", "protocol_id", "assay_id", "internal_assay_id",
})
# Required and positive on the server model; Optional[int] for the rest.
_REQUIRED_INT_FIELDS = frozenset({"child_id", "parent_id"})
_UUID_FIELDS = frozenset({"child_uuid", "parent_uuid"})


def _check_chunk_size(chunk_size) -> None:
    """A chunk size below 1 must fail loudly, not write nothing.

    `range(0, n, -1)` is empty and `range(0, n, 0)` raises an unhelpful
    ValueError about the step -- the first would issue no query at all while
    still returning a full manifest, which reads exactly like a successful run.
    """
    if not isinstance(chunk_size, numbers.Integral) or chunk_size < 1:
        raise ValueError(f"chunk_size must be a positive integer, got {chunk_size!r}")


def _coerce_int(field: str, value):
    """An integer-typed property as a Python `int`, or None.

    Handles three things a DataFrame hands over that the Neo4j driver must not
    see: an integral float (11.0), a numpy scalar (the packer rejects
    numpy.int64 outright, since it is not an `int` subclass), and NaN. A
    non-integral float is refused rather than truncated -- an id ending in .5 is
    a defect upstream, not a rounding question.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; nothing here is ever legitimately a bool.
        raise ValueError(f"{field} is a bool, not an id: {value!r}")
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        as_float = float(value)
        if math.isnan(as_float):
            # Reachable only from a manifest read back off disk: json.dumps
            # emits a bare `NaN` token by default and json.loads reads it back
            # as a float. A NaN property is not a null property.
            raise ValueError(f"{field} is NaN, which is not a null")
        if not as_float.is_integer():
            raise ValueError(f"{field} is not an integer: {value!r}")
        return int(as_float)
    raise ValueError(f"{field} is not a number: {value!r}")


def _normalise_row(row: dict) -> dict:
    """One payload row, typed and validated as DerivedFromRelRow would be.

    Nothing between here and the graph validates anything: the applier speaks
    Cypher directly rather than going through the pydantic model, so a null
    child_id would go out as `r.child_id = null` on a real relationship and a
    stray reporting column would be written as a property instead of being
    rejected. This is that model's `extra="forbid"`, its `Optional[int]` typing
    and its positive-id validator, restated at the one funnel every row passes
    through.

    One deliberate divergence: the server strips uuids (models.py:476) because
    it builds nodes from an upload sheet. These uuids came from the graph's OWN
    node index and are MATCH keys, so stripping one could silently fail to find
    a node that the padded uuid would have matched. Blank is refused; anything
    else passes through byte for byte.
    """
    if set(row) != set(S.EDGE_ROW_COLUMNS):
        unexpected = sorted(set(row) - set(S.EDGE_ROW_COLUMNS))
        missing = sorted(set(S.EDGE_ROW_COLUMNS) - set(row))
        raise ValueError(
            "row does not match DerivedFromRelRow: "
            f"unexpected={unexpected} missing={missing}"
        )
    out: dict = {}
    for field in S.EDGE_ROW_COLUMNS:
        value = row[field]
        if field in _INT_FIELDS:
            value = _coerce_int(field, value)
            if field in _REQUIRED_INT_FIELDS:
                if value is None:
                    raise ValueError(f"{field} is required and must be a positive int")
                if value <= 0:
                    raise ValueError(f"{field} must be positive, got {value!r}")
        elif field in _UUID_FIELDS:
            if not isinstance(value, str) or not value.strip():
                # An empty uuid matches no Sample node, so the MERGE creates
                # nothing while the manifest claims an edge.
                raise ValueError(f"{field} must be a non-empty string, got {value!r}")
        out[field] = value
    return out


def _chunks(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def to_payload(resolved: pd.DataFrame) -> list[dict]:
    """Slice the plan down to exactly DerivedFromRelRow's fields, typed.

    That model is extra="forbid", so a reporting column reaching the server is
    a hard rejection. Row order is the plan's order and is preserved, because
    the manifest is read alongside the report the same plan produced.

    Every row also goes through _normalise_row, so the manifest an operator
    reviews is already typed the way the graph will store it. apply_manifest
    normalises again on the box -- the manifest crosses a disk in between, and
    the second pass costs a fraction of a second at production scale.
    """
    frame = resolved[S.EDGE_ROW_COLUMNS]
    # astype(object) FIRST: on a float column `.where(..., None)` leaves NaN in
    # place, because the column keeps its dtype and None is cast straight back
    # to NaN -- and a NaN reaching the Neo4j driver is not the same as a null
    # property. Every optional field here (protocol_id, assay_id,
    # internal_assay_id) is float64 the moment one row is dark. So is every
    # optional STRING field: under this environment's pandas, protocol_title and
    # internal_assay_title carry the `str` dtype whose missing value is float
    # nan, which the naive form leaves behind exactly the same way.
    frame = frame.astype(object).where(pd.notna(frame), None)
    return [_normalise_row(row) for row in frame.to_dict(orient="records")]


def apply_edges(
    driver,
    db_name: str,
    resolved: pd.DataFrame,
    dry_run: bool = True,
    chunk_size: int = CHUNK_SIZE,
) -> list[dict]:
    """MERGE every planned edge. Dry run by default; `dry_run=False` is explicit.

    Returns the manifest: one dict per edge, produced whether or not the run
    touched the database, so a dry run is reviewable and so the write sends the
    reviewed object rather than recomputing a second one.

    chunk_size and the column contract are both checked before the dry run
    returns, so a bad invocation fails at the operator's gate and not at the
    write.
    """
    _check_chunk_size(chunk_size)
    if list(resolved.columns) != S.STAGE0_PLAN_COLUMNS:
        raise ValueError(
            f"unexpected columns: {list(resolved.columns)} != {S.STAGE0_PLAN_COLUMNS}"
        )
    payload = to_payload(resolved)
    if not dry_run:
        apply_manifest(driver, db_name, payload, chunk_size=chunk_size)
    return payload


def apply_manifest(
    driver,
    db_name: str,
    manifest_rows: list[dict],
    chunk_size: int = CHUNK_SIZE,
    progress=None,
) -> int:
    """MERGE exactly the rows a manifest records. Returns rows sent.

    The in-container driver's entry point. It exists so driver_stage0.py holds
    no loop of its own: an untested chunking loop on the path that writes ~90k
    production relationships is precisely the thing this stage is meant not to
    have. Every row is re-validated here because the manifest arrives off disk,
    where a NaN token or a hand-edited key can appear between the review and the
    write.

    `progress`, if given, is called `(rows_sent_so_far, total)` after each chunk
    lands. That is the only reason the driver needs no loop of its own: a write
    this size with no output leaves the operator unable to tell a slow chunk
    from a hung one, and the running total is also what tells them how far a
    part-way failure got.

    Returns rows sent, not relationships created. The two differ if a Sample
    node named in the manifest no longer exists: the MATCH finds nothing and
    that row silently creates no edge. Stage 8's post-write count is what
    settles that, not this number.
    """
    _check_chunk_size(chunk_size)
    rows = [_normalise_row(row) for row in manifest_rows]
    sent = 0
    for chunk in _chunks(rows, chunk_size):
        driver.execute_query(MERGE_CYPHER, {"rows": chunk}, database_=db_name)
        sent += len(chunk)
        if progress is not None:
            progress(sent, len(rows))
    return sent


def rollback(
    driver,
    db_name: str,
    manifest_rows: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    """Delete exactly the DERIVED_FROM edges a manifest records creating.

    Returns pairs targeted, not relationships removed. Only the pair travels:
    keying on anything else could match a relationship this run did not create.

    There is deliberately no driver_stage0_rollback.py. A file sitting next to
    the write driver that deletes 90,000 relationships is a file that gets piped
    by mistake, so the undo is an explicit paste instead.

    Paste the block below verbatim, from `ssh` through `PY`. Its body is at
    column 0 on purpose: `<<'PY'` preserves leading whitespace, so an indented
    copy reaches python as an IndentationError. It echoes the row count BEFORE
    it deletes anything, so a manifest that is not the one you meant is visible
    while there is still time to interrupt it.

ssh fairdata 'docker exec -i nextseek uv run manage.py shell' <<'PY'
import json, sys
sys.path.insert(0, "/tmp/scripts")
from django.conf import settings
from neo4j import GraphDatabase
from assay_hygiene import stage0_apply
rows = [json.loads(x) for x in open("/tmp/stage0-manifest.jsonl") if x.strip()]
print(f"manifest: {len(rows):,} pairs -- about to remove their DERIVED_FROM")
nd = settings.NEO4J_DATABASE
d = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
try:
    targeted = stage0_apply.rollback(d, nd.get("NAME") or "neo4j", rows)
    print(f"done: {targeted:,} pairs targeted")
finally:
    d.close()
PY
    """
    _check_chunk_size(chunk_size)
    pairs = [
        {"child_uuid": r["child_uuid"], "parent_uuid": r["parent_uuid"]}
        for r in manifest_rows
    ]
    for chunk in _chunks(pairs, chunk_size):
        driver.execute_query(ROLLBACK_CYPHER, {"rows": chunk}, database_=db_name)
    return len(pairs)
