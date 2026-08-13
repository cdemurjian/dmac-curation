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

    Returns (plan, residues). Every excluded reference is counted in residues,
    so the row count of `parents` is fully accounted for.
    """
    residues = {
        S.D_NOT_UID: 0,
        S.D_NO_NODE: 0,
        S.D_SELF_LOOP: 0,
        S.D_ALREADY_EXISTS: 0,
        "prod_regex_would_reject": 0,
    }

    node_id = dict(zip(nodes["uuid"], nodes["sample_id"]))
    node_type = dict(zip(nodes["uuid"], nodes["type"]))
    have = set(zip(existing["child_uuid"], existing["parent_uuid"]))

    kept: list[tuple] = []
    seen: set[tuple[str, str]] = set()

    for child_uuid, field, token in parents.itertuples(index=False):
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
