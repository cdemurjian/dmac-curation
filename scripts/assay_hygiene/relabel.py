# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""The closing stage: recompute DERIVED_FROM assay labels after a write.

WHY THIS EXISTS. A `DERIVED_FROM` edge's assay label is
`parent_assays INTERSECT child_assays`, computed over `assay_assets`.
`curate-assay-write` adds rows to `assay_assets`. So every successful write
invalidates the graph labels for edges touching the written samples, and until
this stage nothing repaired it -- the labels are stored properties, not a view,
so they simply go stale and nothing notices.

Measured on production 2026-08-28, after a curator added ~25,765 registrations:
416,355 of 802,231 edges were carrying no label they should have had, and
DERIVED_FROM assay coverage was 46%. After the repair it was 98%.

THE RULE IS NOT RESTATED HERE. `stage0.resolve_properties` already mirrors
`nextseek_api/batch_upload/neo4j_sync.py` -- the intersection, the minimum
resolved `internal_assay_id` on a tie, and the fallback to `(assay_id,
assays.title)` for an assay with no junction row. It exists twice already (there
and in the server); a third copy is how two of them silently disagree. This
module diffs its output against what the graph currently stores and does nothing
else.

NEVER CLEARS BY DEFAULT. An edge that HAS a label whose endpoints no longer
share an assay is `D_WOULD_CLEAR`: reported, counted, and left alone. On the
production run that was 82 edges. Blanking them is the one destructive thing
this stage could do, so it is opt-in (`allow_clear=True`) rather than a
consequence of running the repair.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import _schema as S
from .stage0 import resolve_properties

# `field` is required by the plan frame `resolve_properties` consumes and is
# reported back out of it. Stage 0's values name the metadata key a parent
# reference came from; a relabel has no such key -- it revisits edges that
# already exist -- so it says so rather than borrowing a name that would read
# as provenance it does not have.
RELABEL_FIELD = "(relabel)"

D_GAIN = "GAIN"                  # had no label, now has one
D_CHANGE = "CHANGE"              # had a label, the rule computes a different one
D_UNCHANGED = "UNCHANGED"        # the stored label is already correct
D_NO_SHARED = "NO_SHARED"        # no label, and none is possible
D_WOULD_CLEAR = "WOULD_CLEAR"    # has a label its endpoints no longer justify

DISPOSITIONS = (D_GAIN, D_CHANGE, D_UNCHANGED, D_NO_SHARED, D_WOULD_CLEAR)

# The write set. WOULD_CLEAR joins it only under `allow_clear`.
WRITTEN = (D_GAIN, D_CHANGE)

# ITS OWN COLUMN CONTRACT, not `S.EDGE_ROW_COLUMNS`. That list mirrors the
# server's `DerivedFromRelRow`, which is `extra="forbid"`, so a frame carrying
# before/after pairs cannot be spelled in it. The `before_` half is what makes
# the undo a SET-back rather than a DELETE, which is the whole safety argument:
# `stage0_apply.ROLLBACK_CYPHER` deletes the edges its manifest names, and every
# edge here already existed.
PLAN_COLUMNS = [
    "child_uuid", "parent_uuid", "child_id", "parent_id",
    "before_assay_id", "before_internal_assay_id", "before_internal_assay_title",
    "after_assay_id", "after_internal_assay_id", "after_internal_assay_title",
    "n_shared", "assay_source", "disposition",
]


def _nullable_int(values) -> pd.Series:
    """-> Int64, so a missing label stays missing instead of becoming 0.0.

    The graph stores these as integers and the extract reads a column holding
    one null as float64, which would send `11.0` where the server expects `11`
    -- the same coercion `stage0_apply` guards. Int64 keeps both facts: the
    value is an integer, and absent is absent.
    """
    return pd.to_numeric(pd.Series(values), errors="coerce").astype("Int64")


def _disposition(before, after) -> str:
    """One edge's bucket, from what it holds and what the rule computes."""
    had, has = pd.notna(before), pd.notna(after)
    if not has:
        return D_WOULD_CLEAR if had else D_NO_SHARED
    if not had:
        return D_GAIN
    return D_UNCHANGED if int(before) == int(after) else D_CHANGE


def plan_relabel(edges: pd.DataFrame, samples: pd.DataFrame,
                 membership: pd.DataFrame, assays: pd.DataFrame,
                 sops: pd.DataFrame) -> pd.DataFrame:
    """-> one row per EXISTING edge: what it holds, what it should, which bucket.

    Every edge is returned, including the ones nothing will be done to. A plan
    that listed only the writes would report `unchanged` and `no_shared` as
    absences, and those two are 385,581 of the 802,231 rows -- the bulk of the
    graph, and the evidence that the stage read it rather than skipped it.
    """
    plan = pd.DataFrame({
        "child_id": edges.child_id.values,
        "child_uuid": edges.child_uuid.values,
        "parent_id": edges.parent_id.values,
        "parent_uuid": edges.parent_uuid.values,
        "child_type": edges.child_type.values,
        "parent_type": edges.parent_type.values,
        "field": RELABEL_FIELD,
    })
    resolved = resolve_properties(plan, samples, membership, assays, sops)

    before = _nullable_int(edges.edge_internal_assay_id.values)
    after = _nullable_int(resolved.internal_assay_id.values)
    out = pd.DataFrame({
        "child_uuid": edges.child_uuid.values,
        "parent_uuid": edges.parent_uuid.values,
        "child_id": _nullable_int(edges.child_id.values),
        "parent_id": _nullable_int(edges.parent_id.values),
        "before_assay_id": _nullable_int(
            edges.get("edge_assay_id", pd.Series([None] * len(edges))).values),
        "before_internal_assay_id": before,
        "before_internal_assay_title": edges.edge_internal_assay_title.values,
        "after_assay_id": _nullable_int(resolved.assay_id.values),
        "after_internal_assay_id": after,
        "after_internal_assay_title": resolved.internal_assay_title.values,
        "n_shared": _nullable_int(resolved.n_shared.values),
        "assay_source": resolved.assay_source.values,
        "disposition": [_disposition(b, a) for b, a in zip(before, after)],
    })
    return out[PLAN_COLUMNS]


def write_set(plan: pd.DataFrame, allow_clear: bool = False) -> pd.DataFrame:
    """-> only the rows the graph write should touch.

    `UNCHANGED` is excluded on purpose rather than written idempotently: on the
    production run it was 367,198 of 802,231 edges, and a SET that rewrites them
    with the values they already hold is 367,198 rows of risk buying nothing.
    """
    wanted = list(WRITTEN) + ([D_WOULD_CLEAR] if allow_clear else [])
    return plan[plan.disposition.isin(wanted)].reset_index(drop=True)


def census(plan: pd.DataFrame) -> dict[str, int]:
    """-> {disposition: rows}, every bucket present even at zero."""
    counts = plan.disposition.value_counts().to_dict()
    return {d: int(counts.get(d, 0)) for d in DISPOSITIONS}


# --- the backup, and the undo it makes possible ------------------------------

# MATCH, never MERGE. Every edge this stage touches already exists, and MERGE on
# a wrong uuid pair would silently CREATE one instead of failing. Three
# properties and no more: `stage0_apply.MERGE_CYPHER` also sets protocol_id,
# protocol_title, child_id and parent_id, and a relabel has no business
# rewriting any of them.
SET_CYPHER = """
UNWIND $rows AS row
MATCH (c:Sample {uuid: row.child_uuid})-[r:DERIVED_FROM]->(p:Sample {uuid: row.parent_uuid})
SET r.assay_id = row.assay_id,
    r.internal_assay_id = row.internal_assay_id,
    r.internal_assay_title = row.internal_assay_title
RETURN count(r) AS processed
"""

# What one row of SET_CYPHER's `$rows` carries. The apply and the undo use the
# SAME statement and the same shape -- the undo is not a different operation,
# it is this one fed the `before_` half of the plan.
SET_ROW_COLUMNS = ["child_uuid", "parent_uuid", "assay_id",
                   "internal_assay_id", "internal_assay_title"]

BACKUP_COLUMNS = ["child_uuid", "parent_uuid", "child_id", "parent_id",
                  "edge_assay_id", "edge_internal_assay_id",
                  "edge_internal_assay_title"]


class BackupUnverified(RuntimeError):
    """The before-state was not written, or does not read back."""


def back_up_edges(edges: pd.DataFrame, target) -> Path:
    """Write every edge's CURRENT label, then prove the file holds them.

    STEP ONE, BEFORE ANYTHING IS COMPUTED. The graph write is the only
    irreversible thing this stage does and the manifest alone cannot undo an
    edge some other writer changed inside the window. Taking the whole graph
    costs one pass over a frame already in memory -- 802,231 rows compressed to
    about 2.5MB on production -- so there is no reason to take less.

    Refuses an empty frame for the reason `store_backup.back_up` refuses an
    absent store: an archive that holds nothing reports success and restores
    nothing, which is worse than having no backup at all.
    """
    target = Path(target)
    if edges.empty:
        raise BackupUnverified(
            "refusing to back up an empty edge frame. An archive of no edges "
            "would report success and restore nothing; check the extract "
            "before running the relabel.")

    target.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({
        c: edges[c].values if c in edges.columns else None
        for c in BACKUP_COLUMNS
    })
    out.to_csv(target, index=False, compression="gzip")

    # READ IT BACK. `to_csv` returning without raising says the call ran, not
    # that the bytes are on disk and parse -- a truncated or half-flushed
    # archive is exactly the failure a backup exists to survive.
    back = pd.read_csv(target)
    if len(back) != len(edges):
        raise BackupUnverified(
            f"{target} holds {len(back):,} rows but {len(edges):,} edges were "
            f"backed up. The undo would be incomplete; nothing has been "
            f"written to the graph.")
    return target


def to_rows(frame: pd.DataFrame, half: str = "after") -> list[dict]:
    """-> `$rows` for SET_CYPHER, taking the `after_` or `before_` half.

    `half="before"` IS the undo. One statement, one row shape, two directions.
    """
    if half not in ("before", "after"):
        raise ValueError(f"half must be 'before' or 'after', not {half!r}")
    out = frame[[
        "child_uuid", "parent_uuid",
        f"{half}_assay_id", f"{half}_internal_assay_id",
        f"{half}_internal_assay_title",
    ]].copy()
    out.columns = SET_ROW_COLUMNS
    return out.astype(object).where(pd.notna(out), None).to_dict("records")


# 5,000 is the hand run's chunk size, which moved 416,568 edges in 30 seconds.
CHUNK_SIZE = 5_000


def apply_rows(driver, db_name: str, rows: list[dict],
               chunk_size: int = CHUNK_SIZE, progress=None) -> int:
    """SET the three assay fields for each row. Returns rows sent.

    The in-container driver's entry point, so `driver_relabel.py` holds no loop
    of its own -- an untested chunking loop on the path that rewrites 416,568
    production relationships is exactly what this stage must not have.

    Returns rows SENT, not relationships matched. The two differ when a uuid
    pair names an edge that no longer exists: the MATCH finds nothing and that
    row changes nothing, silently. The post-write coverage count is what settles
    that, not this number.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be positive, not {chunk_size}")
    sent = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        driver.execute_query(SET_CYPHER, {"rows": chunk}, database_=db_name)
        sent += len(chunk)
        if progress is not None:
            progress(sent, len(rows))
    return sent


def undo_set(written: pd.DataFrame) -> pd.DataFrame:
    """-> the frame that puts back what `written` overwrote.

    A SET-back and never a DELETE. `stage0_apply.ROLLBACK_CYPHER` deletes the
    relationships its manifest names, which is correct there because stage 0
    created every one of them. Every edge here predates the run: applying that
    rollback would destroy 416,568 real relationships.
    """
    out = written[[
        "child_uuid", "parent_uuid",
        "before_assay_id", "before_internal_assay_id",
        "before_internal_assay_title",
    ]].copy()
    out.columns = SET_ROW_COLUMNS
    return out.reset_index(drop=True)
