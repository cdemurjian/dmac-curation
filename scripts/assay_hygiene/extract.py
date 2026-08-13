# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=15"]
# ///
"""Stage A: read-only extract, run INSIDE the production nextseek container.

Runs under `manage.py shell` so it inherits the configured `seek` connection
and NEO4J_DATABASE settings. No credential is ever read, passed or stored here.

The correct Django alias is `seek` (seek_production). The `default` alias is
`dmac`, whose assay_assets table EXISTS but is EMPTY.

Nothing in this module judges anything. It reads, it names its columns, and it
writes parquet the laptop reasons over. The one piece of logic it does carry --
turning a sample's json_metadata into parent references -- is delegated to the
SERVER's own `collect_parent_tokens`, injected as an argument rather than
reimplemented, because a drifted reimplementation would silently create wrong
edges and that is the exact class of defect this project exists to clean up.

There is one deliberate exception, and it runs the other way: `UID_RE` is NOT
applied here. Production's copy demands a 3+ letter sample type and so discards
every two-letter `AB` (antibody) reference -- ~8,131 of them -- before an edge
is built. `build_parents` emits every token the helper yields, valid or not, and
the laptop applies the corrected pattern in `stage0.plan_edges`, which counts
what it drops. Filtering here would make those references invisible instead.
"""
from __future__ import annotations

import json
from typing import Callable, Iterable, Sequence

import pandas as pd

from . import _schema as S

# --- neo4j -------------------------------------------------------------------
#
# Node and relationship property names are the server's own, from
# nextseek_api/batch_upload/neo4j_sync.py:
#   bulk_merge_nodes         MERGE (s:Sample {uuid: ...}) SET s.id, s.type
#   bulk_merge_relationships SET r.protocol_id, r.protocol_title, r.assay_id,
#                                r.internal_assay_id, r.internal_assay_title,
#                                r.child_id, r.parent_id
# `uuid` (lowercase) is the node key and carries the sample UID; there is no
# `UID` property on a Sample node.
#
# NAMESPACE WARNING, read before joining `edge_assay_id` to anything.
# A DERIVED_FROM relationship carries BOTH `r.assay_id` -- a seek_production
# `assays`.id, 458 rows / 291 distinct titles -- and `r.internal_assay_id` -- a
# dmac `internal_assays`.id, 137 rows, reached from the first through the
# `assays_internal_assays` junction. They are different id spaces that overlap
# numerically and share no meaning.
#
# This projection deliberately takes the INTERNAL one, because internal_assay_id
# is the rule key (_schema.RULE_KEY). The column contract it lands in was frozen
# by task 1 and reads `edge_assay_id` / `edge_assay_title`, which do NOT say
# "internal". So: `edge_assay_id` reconciles against
# ASSAY_COLUMNS.internal_assay_id and against nothing else. Joining it to
# `assays.assay_id` downstream would silently cross the two spaces and produce
# plausible, wrong answers.
EDGES_CYPHER = """
MATCH (c:Sample)-[r:DERIVED_FROM]->(p:Sample)
RETURN c.id AS child_id, p.id AS parent_id,
       c.uuid AS child_uuid, p.uuid AS parent_uuid,
       c.type AS child_type, p.type AS parent_type,
       r.internal_assay_id AS edge_assay_id,
       r.internal_assay_title AS edge_assay_title,
       r.protocol_id AS edge_protocol_id
"""

CHILDOF_CYPHER = """
MATCH (c:Sample)-[:CHILD_OF]->(p:Sample)
RETURN c.uuid AS child_uuid, p.uuid AS parent_uuid
"""

# Every Sample node, not only the connected ones. stage0.plan_edges resolves
# every child_id and parent_id it writes through this index, and a parent that
# is not yet the endpoint of any relationship is the normal case for a backfill
# -- restricting the match to nodes that already have an edge would turn exactly
# the samples stage 0 exists to connect into `parent_not_a_node` drops.
NODES_CYPHER = """
MATCH (s:Sample)
RETURN s.uuid AS uuid, s.id AS sample_id, s.type AS type
"""

# --- mysql -------------------------------------------------------------------
#
# Every projected column carries an explicit `AS` alias, including the redundant
# ones (`a.title AS title`), so the whole projection can be pinned against its
# column contract mechanically instead of by a substring search that passes on
# almost anything. `_check_projection` enforces the same contract at run time.

# dmac has an assay_assets table too, and it is EMPTY. asset_type is what makes
# this the seek reading.
MEMBERSHIP_SQL = """
SELECT asset_id AS sample_id, assay_id AS assay_id
FROM assay_assets WHERE asset_type = 'Sample'
"""

# `investigations` has NO project_id column; the link is the
# investigations_projects join table. An assay mapped to several projects
# therefore yields several rows, which stage0.resolve_properties expects.
#
# The junction to the curated internal assays lives in the OTHER database, so it
# needs an explicit prefix -- the query runs on the `seek` connection. `{dmac}`
# is filled from settings at run time, exactly as the server does it
# (neo4j_sync._resolve_internal_assays builds `{nextseek_db}.` prefixes).
#
# Both junction joins are LEFT: 17 of 458 assays have no junction row, and an
# inner join would delete them from the extract, so resolve_properties' fallback
# to (assay_id, assays.title) would never fire for them.
ASSAYS_SQL = """
SELECT a.id AS assay_id, a.title AS title,
       a.sample_type_id AS sample_type_id, a.study_id AS study_id,
       i.id AS investigation_id, ip.project_id AS project_id,
       p.title AS project_title,
       ia.id AS internal_assay_id,
       ia.internal_assay_title AS internal_assay_title
FROM assays a
JOIN studies s              ON s.id  = a.study_id
JOIN investigations i       ON i.id  = s.investigation_id
JOIN investigations_projects ip ON ip.investigation_id = i.id
JOIN projects p             ON p.id  = ip.project_id
LEFT JOIN {dmac}.assays_internal_assays aia ON aia.assay_id = a.id
LEFT JOIN {dmac}.internal_assays ia         ON ia.id = aia.internal_assay_id
"""

# LEFT JOIN, or every sample belonging to no project silently disappears and
# takes its json_metadata -- the whole point of this extract -- with it.
SAMPLES_SQL = """
SELECT s.id AS sample_id, s.uuid AS uuid,
       s.json_metadata AS json_metadata, s.created_at AS created_at,
       GROUP_CONCAT(ps.project_id) AS project_ids
FROM samples s
LEFT JOIN projects_samples ps ON ps.sample_id = s.id
GROUP BY s.id
"""

SOPS_SQL = "SELECT id AS sop_id, title AS title FROM sops"

# One table both `main` and the tests read, so an extract added later is
# projection-checked without anyone remembering to add a case for it.
CYPHER_EXTRACTS: dict[str, tuple[str, list[str]]] = {
    "edges": (EDGES_CYPHER, S.EDGE_COLUMNS),
    "childof": (CHILDOF_CYPHER, S.CHILDOF_COLUMNS),
    "nodes": (NODES_CYPHER, S.NODES_COLUMNS),
}
SQL_EXTRACTS: dict[str, tuple[str, list[str]]] = {
    "membership": (MEMBERSHIP_SQL, S.MEMBERSHIP_COLUMNS),
    "assays": (ASSAYS_SQL, S.ASSAY_COLUMNS),
    "samples": (SAMPLES_SQL, S.SAMPLE_COLUMNS),
    "sops": (SOPS_SQL, S.SOP_COLUMNS),
}

# Frames whose ROW COUNT is not a sound acceptance signal, and the column whose
# distinct count is.
#
# `assays` is the only one, and it is the only query that can emit more than one
# row per entity. It fans out on two INDEPENDENT axes: once per
# investigations_projects mapping, and once per assays_internal_assays row. So a
# row count of 470 is equally consistent with "correct" and with "the 17
# junction-less assays were silently dropped by the inner joins, and 29 rows were
# duplicated by multi-project assays" -- which is exactly the failure the LEFT
# JOINs exist to prevent, and it resolves those 17 assays' edges wrong instead of
# firing resolve_properties' fallback. The step 6 assertion is therefore
# `nunique == 458`, never `len == 458`.
#
# No other frame is multiplicative: `edges`/`childof` are one row per
# relationship, `nodes` one per node, `membership` one per assay_assets row,
# `sops` one per SOP, `samples` one per GROUP BY s.id, and `parents` is built in
# Python. `nodes` additionally has a STRONGER guard than a printed distinct
# count -- duplicate_uuids() below, which raises rather than merely reporting.
DISTINCT_KEYS = {"assays": "assay_id"}

# What `field` says when the helper yielded a token no metadata field explains.
# Deliberately not a real field name: `field` is provenance a curator reads out
# of plan.parquet, and defaulting it to "Parent" would state in the artefact
# that a field declared something it never declared. A visible gap beats a
# plausible lie.
UNATTRIBUTED_FIELD = "(unattributed)"


def count_line(name: str, df: pd.DataFrame) -> str:
    """One line of `main`'s summary -- the operator's step 6 acceptance signal.

    For every frame but one the row count IS the signal. `assays` also reports
    its distinct assay_id, because its row count cannot distinguish a correct
    extract from a truncated one; see DISTINCT_KEYS.
    """
    line = f"{name:<12} {len(df):>10,} rows"
    key = DISTINCT_KEYS.get(name)
    if key:
        line += f"   ({df[key].nunique():,} distinct {key})"
    return line


def _check_projection(got: Iterable[str], want: Sequence[str]) -> None:
    """Fail loudly when a query stops projecting exactly its column contract.

    Order matters as much as membership: both frame builders below are
    positional, so a reordering swaps two columns' CONTENTS rather than raising.
    """
    got = list(got)
    if got != list(want):
        raise ValueError(
            f"projection {got} does not match the declared contract {list(want)}"
        )


def _frame(records: list[dict], columns: Sequence[str]) -> pd.DataFrame:
    """A neo4j result as a frame with exactly `columns`, in that order.

    `pd.DataFrame(records)` alone yields a 0x0 frame with NO header when the
    result set is empty, which writes a headerless parquet the laptop then
    KeyErrors on; and it takes its column order from the records, so a renamed
    alias would arrive as an extra column rather than as an error.
    """
    if not records:
        return pd.DataFrame(columns=list(columns))
    df = pd.DataFrame(records)
    _check_projection(df.columns, columns)
    return df


def duplicate_uuids(nodes: pd.DataFrame) -> list[str]:
    """uuids appearing more than once in the graph's node index.

    stage0.plan_edges resolves ids with `dict(zip(nodes.uuid, nodes.sample_id))`,
    which is silently last-wins: a duplicated uuid hands every edge touching it
    an arbitrary one of the two sample_ids, uncounted, and those ids are written
    onto real relationships. Neo4j declares a uniqueness constraint on
    :Sample(uuid) (neo4j_sync.py:80) so this should always be empty -- but the
    constraint is created `IF NOT EXISTS` by a migration that may not have run
    on every deployment, and "should be empty" is exactly the kind of assumption
    this pipeline exists to stop trusting. `main` checks it and refuses to
    finish quietly.
    """
    if nodes.empty:
        return []
    dup = nodes["uuid"][nodes["uuid"].duplicated()]
    return sorted(set(dup), key=str)


def build_parents(
    samples_rows: Iterable[tuple], collect_fn: Callable[[dict], list]
) -> pd.DataFrame:
    """One row per declared parent token.

    `collect_fn` is the SERVER's collect_parent_tokens, injected rather than
    reimplemented, so key matching and semicolon splitting cannot drift.
    UID validation is deliberately NOT done here: stage 0 applies the corrected
    regex on the laptop, and the raw token must survive to be reported.

    `field` -- which metadata key produced the token -- is the one thing the
    helper cannot tell us: it returns a flat, deduplicated list. So attribution
    is recomputed locally, and that local pass mirrors the helper
    (helpers.py:27-47: keys containing "parent" case-insensitively, str values
    only, split on ";", strip, drop empties, first occurrence wins). It is
    provenance only -- `field` reaches plan.parquet for a curator to read and
    never decides whether an edge is created -- so a drift here mislabels a
    column, it does not build a wrong edge. A token the pass cannot explain is
    labelled UNATTRIBUTED_FIELD rather than guessed at.
    """
    out: list[tuple[str, str, str]] = []
    for child_uuid, jmeta in samples_rows:
        try:
            meta = json.loads(jmeta) if jmeta else {}
        except (ValueError, TypeError):
            # A backfill over 163,000 rows cannot die on one malformed blob.
            # The sample still reaches the laptop in samples.parquet, which is
            # extracted wholesale, so nothing is lost -- only its parent
            # references, which could not be read in the first place.
            continue
        # Checked BEFORE the helper sees it: collect_parent_tokens does
        # meta.items() and would raise AttributeError on a list or a bare
        # string, killing the extract at an arbitrary row with every frame lost.
        if not isinstance(meta, dict):
            continue
        tokens = collect_fn(meta)
        if not tokens:
            continue
        origin: dict[str, str] = {}
        for key, value in meta.items():
            if "parent" not in key.lower() or not isinstance(value, str):
                continue
            for part in value.split(";"):
                part = part.strip()
                if part and part not in origin:
                    origin[part] = key
        for token in tokens:
            out.append((child_uuid, origin.get(token, UNATTRIBUTED_FIELD), token))
    # Built from the constant, not from a literal list that happens to match:
    # stage0.plan_edges selects `parents[S.PARENT_COLUMNS]` and unpacks the
    # result positionally.
    return pd.DataFrame(out, columns=S.PARENT_COLUMNS)


def main(outdir: str = "/tmp/assay-hygiene-extract") -> None:
    """Write every extract to `outdir` as parquet. Read-only against production."""
    import pathlib

    from django.conf import settings
    from django.db import connections
    from neo4j import GraphDatabase

    from nextseek_api.batch_upload.helpers import collect_parent_tokens

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    dmac = settings.DATABASES[settings.NEXTSEEK_DATABASE]["NAME"]
    nd = settings.NEO4J_DATABASE
    db = nd.get("NAME") or "neo4j"

    frames: dict[str, pd.DataFrame] = {}

    driver = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
    try:
        for name, (query, columns) in CYPHER_EXTRACTS.items():
            recs, _, _ = driver.execute_query(query, {}, database_=db)
            frames[name] = _frame([dict(r) for r in recs], columns)
    finally:
        # try/finally, not a trailing close(): a failed query on a production
        # box must not leave a bolt connection open in the container.
        driver.close()

    for name, (query, columns) in SQL_EXTRACTS.items():
        with connections["seek"].cursor() as cur:
            # Only ASSAYS_SQL carries a placeholder; format() is a no-op on the
            # rest, and raises loudly on a stray literal brace in a new query.
            cur.execute(query.format(dmac=dmac))
            _check_projection([c[0] for c in cur.description], columns)
            frames[name] = pd.DataFrame(cur.fetchall(), columns=list(columns))

    frames["parents"] = build_parents(
        list(zip(frames["samples"]["uuid"], frames["samples"]["json_metadata"])),
        collect_parent_tokens,
    )

    dupes = duplicate_uuids(frames["nodes"])

    for name, df in frames.items():
        df.to_parquet(out / f"{name}.parquet", compression="zstd", index=False)
        print(count_line(name, df))

    # Raised AFTER the writes, deliberately. The extract is minutes of work and
    # ~260 MB; destroying it would make the failure harder to diagnose, not
    # safer. Everything is on disk and copyable, and the run still exits
    # non-zero so nobody proceeds to stage 0 on an ambiguous node index.
    if dupes:
        raise RuntimeError(
            f"{len(dupes):,} uuid(s) appear more than once in the Sample node "
            f"index, so uuid -> sample_id is ambiguous and stage 0 would resolve "
            f"them arbitrarily. Extract written to {out} for diagnosis. "
            f"First few: {dupes[:10]}"
        )
