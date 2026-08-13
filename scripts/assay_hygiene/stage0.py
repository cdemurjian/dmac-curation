# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage 0: complete the lineage graph.

Creates the DERIVED_FROM relationships that production already records in
samples.json_metadata but has never written to the graph. Writes only Neo4j,
never MySQL, and never deletes.

See docs/superpowers/specs/2026-08-12-assay-hygiene-design.md.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from . import _schema as S


def plan_edges(
    parents: pd.DataFrame,
    nodes: pd.DataFrame,
    existing: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Decide which declared parent references need a DERIVED_FROM edge.

    parents  : child_uuid | field | token   (every token collect_parent_tokens
               yielded, valid or not)
    nodes    : uuid | sample_id | type      (the graph's node index)
    existing : child_uuid | parent_uuid     (DERIVED_FROM edges already present)

    Returns (plan, residues). Nothing is dropped silently: every excluded
    reference is counted under a drop reason, so

        len(plan) + <every drop reason in residues> == len(parents)

    holds for any input. "prod_regex_would_reject" is NOT a drop reason and is
    excluded from that sum -- it is a report-only count that overlaps the
    keepers, recording what the live server would have thrown away.
    """
    residues = {
        S.D_NOT_UID: 0,
        S.D_NO_NODE: 0,
        S.D_SELF_LOOP: 0,
        S.D_ALREADY_EXISTS: 0,
        "duplicate_reference": 0,
        "prod_regex_would_reject": 0,
    }

    node_id = dict(zip(nodes["uuid"], nodes["sample_id"]))
    node_type = dict(zip(nodes["uuid"], nodes["type"]))
    have = set(zip(existing["child_uuid"], existing["parent_uuid"]))

    kept: list[tuple] = []
    seen: set[tuple[str, str]] = set()

    # Selected by name before iterating: itertuples unpacks POSITIONALLY, so a
    # producer emitting these three columns in another order would swap field
    # and token and fail every reference on UID validation. This is a no-op for
    # a correctly-ordered frame and a KeyError for a missing column.
    for child_uuid, field, token in parents[S.PARENT_COLUMNS].itertuples(index=False):
        if not S.UID_RE_FIXED.match(str(token)):
            residues[S.D_NOT_UID] += 1
            continue
        # Report, do not act on, what the live server would have thrown away.
        if not S.UID_RE_PROD.match(str(token)):
            residues["prod_regex_would_reject"] += 1
        if child_uuid == token:
            residues[S.D_SELF_LOOP] += 1
            continue
        if token not in node_id or child_uuid not in node_id:
            residues[S.D_NO_NODE] += 1
            continue
        if (child_uuid, token) in have:
            residues[S.D_ALREADY_EXISTS] += 1
            continue
        if (child_uuid, token) in seen:
            # The same pair declared under two fields is one edge, not two.
            # Counted, not skipped silently: an operator reading the ledger
            # must be able to tell a collapsed duplicate from a lost reference.
            residues["duplicate_reference"] += 1
            continue
        seen.add((child_uuid, token))
        kept.append((
            child_uuid, token,
            node_id[child_uuid], node_id[token],
            node_type[child_uuid], node_type[token],
            field,
        ))

    plan = pd.DataFrame(kept, columns=[
        "child_uuid", "parent_uuid", "child_id", "parent_id",
        "child_type", "parent_type", "field",
    ])
    return plan, residues


# Matches the server's protocol extraction: the Protocol metadata value is a
# SOP URL and the trailing integer is the sops.id. Identical to _SOP_URL_RE
# (neo4j_sync.py:42) -- keep the two in step.
SOP_URL_RE = re.compile(r"/sops/(\d+)")


def resolve_properties(
    plan: pd.DataFrame,
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    sops: pd.DataFrame,
) -> pd.DataFrame:
    """Compute each new edge's properties exactly as the server would.

    Mirrors nextseek_api/batch_upload/neo4j_sync.py:888-1098. Deliberately does
    not improve on two behaviours, so that an edge stage 0 writes is
    indistinguishable from one the upload pipeline would have written:
      - when several assays are shared, the minimum internal_assay_id wins
      - an assay with no junction row falls back to (assay_id, assays.title)

    Both are arbitrary rather than wrong, so neither is hidden: ``n_shared``
    reports how many assays the tiebreak had to choose between, and
    ``assay_source`` says which of the two id spaces the label came from. An
    edge with n_shared > 1 is a curator's to settle, not this stage's to guess.

    The one server input with no counterpart here is the upload sheet itself:
    the server lets a submitted row override the sop_id and the assay title
    (neo4j_sync.py:903-928). Stage 0 backfills edges for samples uploaded long
    ago, so there is no sheet to override with and the database always wins.
    """
    meta_by_id: dict[int, dict] = {}
    # Selected by name before iterating, as in plan_edges: itertuples unpacks
    # POSITIONALLY, and a frame emitting sample_id | json_metadata | uuid would
    # otherwise read the uuid as the metadata blob and silently NULL every
    # protocol instead of failing.
    for sid, _uuid, jmeta, _created, _projects in samples[
        S.SAMPLE_COLUMNS
    ].itertuples(index=False):
        try:
            parsed = json.loads(jmeta) if jmeta else {}
        except (ValueError, TypeError):
            parsed = {}
        # The server would raise AttributeError on a non-dict here; a backfill
        # over 400k rows cannot die on one malformed blob, so treat it as empty.
        meta_by_id[sid] = parsed if isinstance(parsed, dict) else {}

    sop_title = dict(zip(sops["sop_id"], sops["title"]))

    assays_by_sample: dict[int, set[int]] = {}
    for sid, aid in membership[S.MEMBERSHIP_COLUMNS].itertuples(index=False):
        assays_by_sample.setdefault(sid, set()).add(aid)

    # assay_id -> (internal_assay_id, internal_assay_title, source)
    #
    # Two passes, mirroring the server's steps 3b-3d (neo4j_sync.py:1003-1027).
    # Pass 1 is the junction table, and an assay mapped to several internal
    # assays keeps the SMALLEST internal_assay_id -- the server's own rule, and
    # its own comment: "Keep smallest internal_assay_id per assay_id
    # (deterministic for 1:N)" (neo4j_sync.py:879-881). Duplicate assay_id rows
    # are normal input, not corruption: the extractor LEFT JOINs the junction
    # table and joins through investigations_projects, so one assay yields one
    # row per (internal assay x project) and their order is not stable across
    # extracts. Last-row-wins would therefore be non-deterministic.
    #
    # Pass 2 is the fallback and only fills assay_ids pass 1 never resolved, so
    # a real junction row beats a fallback for the same assay in any row order.
    # The passes must stay separate: a fallback's id is an assays.id, not an
    # internal_assays.id, so letting it into the minimum above would compare two
    # unrelated id spaces and could hand the edge the wrong internal assay.
    resolved_assay: dict[int, tuple[int, str, str]] = {}
    assay_rows = assays[S.ASSAY_COLUMNS]
    for row in assay_rows.itertuples(index=False):
        if pd.isna(row.internal_assay_id):
            continue
        ia_id = int(row.internal_assay_id)
        prev = resolved_assay.get(row.assay_id)
        if prev is None or ia_id < prev[0]:
            resolved_assay[row.assay_id] = (
                ia_id, row.internal_assay_title, "junction",
            )
    for row in assay_rows.itertuples(index=False):
        if row.assay_id in resolved_assay:
            continue
        # neo4j_sync.py:1021 coerces a NULL assays.title to "" here.
        title = row.title if pd.notna(row.title) else ""
        resolved_assay[row.assay_id] = (row.assay_id, title, "fallback")

    out: list[tuple] = []
    for r in plan.itertuples(index=False):
        meta = meta_by_id.get(r.child_id, {})
        protocol_val = meta.get("Protocol") or meta.get("protocol") or ""
        m = SOP_URL_RE.search(str(protocol_val))
        protocol_id = int(m.group(1)) if m else None
        # `if protocol_id` and not `is not None`, mirroring neo4j_sync.py:1060.
        protocol_title = sop_title.get(protocol_id) if protocol_id else None

        shared = (assays_by_sample.get(r.child_id, set())
                  & assays_by_sample.get(r.parent_id, set()))
        assay_id = internal_id = internal_title = None
        source = "none"
        if shared:
            best = None
            for aid in shared:
                if aid not in resolved_assay:
                    continue
                ia_id, ia_title, src = resolved_assay[aid]
                if best is None or ia_id < best[0]:
                    best = (ia_id, ia_title, src, aid)
            # A shared assay the assays frame does not describe stays
            # unresolved and the edge goes out dark with n_shared standing --
            # visibly an extract gap rather than a genuinely dark edge.
            if best is not None:
                internal_id, internal_title, source, assay_id = best

        out.append((
            r.child_id, r.child_uuid, r.parent_id, r.parent_uuid,
            protocol_id, protocol_title, assay_id,
            internal_id, internal_title,
            r.child_type, r.parent_type, r.field, len(shared), source,
        ))

    return pd.DataFrame(out, columns=S.STAGE0_PLAN_COLUMNS)
