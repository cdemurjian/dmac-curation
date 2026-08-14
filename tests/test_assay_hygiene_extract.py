"""Stage A extractor: the query text, the projection contracts, and build_parents.

`extract.main()` is deliberately not tested. It needs Django, Neo4j and MySQL,
and a mock stack deep enough to run it would be testing the mock. What can go
wrong in the *text* -- a join through a column that does not exist, a projection
that silently stops matching the contract the laptop reads, a query that writes
-- is what these cases pin. Two real schema bugs were caught this way during
design: `investigations` has no `project_id`, and 17 of 458 assays have no
junction row and are dropped by an inner join.

The pure transforms (`build_parents`, `_frame`, `_check_projection`,
`duplicate_uuids`) are tested directly, with hand-built frames. The stage 0
fixture is NOT reused for build_parents: its `samples.json_metadata` declares
one parent token while its `parents` frame carries six rows, so re-deriving
tokens from that fixture would "prove" build_parents wrong when it is right.
"""
import ast
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
EXTRACT_PY = REPO / "scripts" / "assay_hygiene" / "extract.py"
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import extract  # noqa: E402

# ---------------------------------------------------------------------------
# projection parsing
#
# Every projected column in every query carries an explicit `AS` alias --
# including redundant ones like `a.title AS title` -- precisely so the whole
# projection can be pinned against its column contract mechanically rather than
# by a substring search that passes on almost anything.
# ---------------------------------------------------------------------------

ALIAS_RE = re.compile(r"([^\s,]+)\s+AS\s+(\w+)")


def _projection(query: str) -> list[tuple[str, str]]:
    """(source expression, alias) for every projected column, in order."""
    return [(m.group(1), m.group(2)) for m in ALIAS_RE.finditer(query)]


def _sources(query: str) -> dict[str, str]:
    """alias -> the server property / column it is projected from."""
    return {alias: src for src, alias in _projection(query)}


ALL_EXTRACTS = [
    (name, query, columns)
    for name, (query, columns) in {
        **extract.CYPHER_EXTRACTS, **extract.SQL_EXTRACTS,
    }.items()
]


def test_the_projection_parser_reads_source_and_alias():
    """Self-test: the parser below carries the weight of most of this module.

    A parser that silently returned [] would make the source-expression cases
    vacuous (a missing key raises, but a wrong-source assertion would never be
    reached), so pin it against both shapes that appear in the real queries.
    """
    assert _projection(
        "RETURN c.id AS child_id, GROUP_CONCAT(ps.project_id) AS project_ids"
    ) == [("c.id", "child_id"), ("GROUP_CONCAT(ps.project_id)", "project_ids")]


# ---------------------------------------------------------------------------
# the queries
# ---------------------------------------------------------------------------

def test_assays_sql_joins_project_through_the_junction_table():
    # `investigations` has NO project_id column; the link is
    # investigations_projects. Getting this wrong yields an empty frame.
    assert "investigations_projects" in extract.ASSAYS_SQL
    assert "i.project_id" not in extract.ASSAYS_SQL
    # ...and the projected project_id must come from that junction, not from a
    # column on investigations that does not exist.
    assert _sources(extract.ASSAYS_SQL)["project_id"] == "ip.project_id"


def test_assays_sql_resolves_internal_assay_via_the_dmac_junction():
    # The rule key is internal_assay_id, so the extract must carry it.
    assert "assays_internal_assays" in extract.ASSAYS_SQL
    assert "internal_assays" in extract.ASSAYS_SQL
    srcs = _sources(extract.ASSAYS_SQL)
    assert srcs["internal_assay_id"] == "ia.id"
    assert srcs["internal_assay_title"] == "ia.internal_assay_title"


def test_assays_sql_left_joins_the_junction_so_no_assay_is_dropped():
    """17 of 458 assays have no junction row and fall back to (assay_id, title).

    An inner join here would delete them from the extract, and stage 0's
    fallback path (resolve_properties, neo4j_sync.py:1021) would then never
    fire. Asserted per-join rather than as `"LEFT JOIN" in SQL`, which passes
    as soon as ANY join is left-joined.
    """
    for table in ("assays_internal_assays", "internal_assays"):
        assert re.search(
            r"LEFT JOIN \{dmac\}\." + table + r"\b", extract.ASSAYS_SQL
        ), f"{table} must be LEFT JOINed"


def test_assays_sql_reads_the_junction_out_of_the_nextseek_database():
    """The junction lives in dmac, the assays in seek_production.

    The query runs on the `seek` connection, so the two junction tables need an
    explicit database prefix. The server does exactly this
    (neo4j_sync._resolve_internal_assays builds `{nextseek_db}.` prefixes), and
    the prefix is a placeholder rather than a literal because the database name
    is deployment-specific and is read from settings at run time.
    """
    assert "{dmac}" in extract.ASSAYS_SQL
    formatted = extract.ASSAYS_SQL.format(dmac="nextseekdb")
    assert "nextseekdb.assays_internal_assays" in formatted
    assert "nextseekdb.internal_assays" in formatted
    # the seek-side tables must NOT be prefixed onto the dmac database
    assert "nextseekdb.assays " not in formatted


def test_membership_sql_reads_the_seek_schema_not_dmac():
    assert "assay_assets" in extract.MEMBERSHIP_SQL
    assert "asset_type" in extract.MEMBERSHIP_SQL
    # dmac has an assay_assets table too, and it is EMPTY. The filter is what
    # makes this the seek reading: only seek's table carries asset_type rows.
    assert "'Sample'" in extract.MEMBERSHIP_SQL


def test_samples_sql_aggregates_projects_without_dropping_projectless_samples():
    """LEFT JOIN, or every sample in no project silently disappears."""
    assert re.search(r"LEFT JOIN projects_samples\b", extract.SAMPLES_SQL)
    assert _sources(extract.SAMPLES_SQL)["project_ids"] == (
        "GROUP_CONCAT(ps.project_id)"
    )


def test_the_two_extract_tables_are_disjoint():
    """main() builds ONE `frames` dict from both tables.

    A name in both would silently overwrite a frame with the other's contents,
    and every consumer downstream reads these by name out of the parquet
    directory.
    """
    assert not (set(extract.CYPHER_EXTRACTS) & set(extract.SQL_EXTRACTS))
    assert len(ALL_EXTRACTS) == (
        len(extract.CYPHER_EXTRACTS) + len(extract.SQL_EXTRACTS)
    )


def test_the_extract_produces_every_frame_stage_0_reads():
    """Cross-task contract: the plan's dry-run step reads these eight by name.

    `parents` is the one frame built in Python rather than queried, so it is
    absent from both query tables and has to be named here.
    """
    produced = set(extract.CYPHER_EXTRACTS) | set(extract.SQL_EXTRACTS) | {"parents"}
    assert produced == {"parents", "nodes", "edges", "membership",
                        "assays", "samples", "sops", "childof"}


@pytest.mark.parametrize("name,query,columns", ALL_EXTRACTS)
def test_every_extract_projects_exactly_its_declared_contract(name, query, columns):
    """The producer and the consumer must assert against the same contract.

    Pinned as an ordered list, not a set: `sql()` builds its frame positionally
    from the cursor description and `_frame` pins the record key order, so a
    reordering swaps two columns' contents rather than failing.
    """
    aliases = [alias for _, alias in _projection(query)]
    assert aliases == list(columns), (
        f"{name} projects {aliases}, contract is {list(columns)}"
    )


@pytest.mark.parametrize("name,query,columns", ALL_EXTRACTS)
def test_no_extract_can_write(name, query, columns):
    """Stage A is read-only against production. Nothing here may mutate.

    Word-boundary matched, not substring matched: `s.created_at` contains
    "CREATE" once uppercased, so a substring check would fail SAMPLES_SQL for
    the wrong reason and would then be "fixed" by weakening it.

    `FOREACH` and `CALL` are Cypher's own write routes, and neither carries a
    forbidden verb this check would otherwise see: `FOREACH (x IN xs | SET ...)`
    hides its mutation inside a clause, and `CALL` reaches both write procedures
    and write-capable subqueries. `CALL` is forbidden outright even though some
    procedures are read-only -- no query here needs one, so the safe default is
    that adding one has to weaken this guard deliberately first.
    """
    forbidden = ("MERGE", "CREATE", "DELETE", "SET", "REMOVE", "DETACH",
                 "FOREACH", "CALL",
                 "INSERT", "UPDATE", "REPLACE", "DROP", "ALTER", "TRUNCATE",
                 "GRANT", "LOAD")
    upper = query.upper()
    for verb in forbidden:
        assert not re.search(rf"\b{verb}\b", upper), f"{name} contains {verb}"


def test_edges_cypher_sources_every_column_from_the_server_property():
    """Pin which Neo4j property each edge column is read from.

    NAMESPACE. A DERIVED_FROM relationship carries BOTH `r.assay_id` (a
    seek_production `assays`.id: 458 rows, 291 distinct titles) and
    `r.internal_assay_id` (a dmac `internal_assays`.id: 137 rows), and
    neo4j_sync.bulk_merge_relationships writes both. They are different id
    spaces that overlap numerically and share no meaning. This extract
    deliberately takes the INTERNAL one, because internal_assay_id is the rule
    key (_schema.RULE_KEY).

    The column names say `internal` so the frame cannot misrepresent itself to
    a reader. That is a second line of defence, not the first: a name is a
    claim and this pin is the check on it, so the rename does not make the
    assertion redundant.
    """
    assert _sources(extract.EDGES_CYPHER) == {
        "child_id": "c.id",
        "parent_id": "p.id",
        "child_uuid": "c.uuid",
        "parent_uuid": "p.uuid",
        "child_type": "c.type",
        "parent_type": "p.type",
        "edge_internal_assay_id": "r.internal_assay_id",
        "edge_internal_assay_title": "r.internal_assay_title",
        "edge_protocol_id": "r.protocol_id",
    }


def test_edge_internal_assay_id_is_the_internal_namespace_not_the_seek_one():
    """The same claim as above, stated as the mistake it prevents."""
    srcs = _sources(extract.EDGES_CYPHER)
    assert srcs["edge_internal_assay_id"] != "r.assay_id"
    assert srcs["edge_internal_assay_title"] != "r.assay_title"
    # and the column it reconciles against downstream lives in the same space
    assert "internal_assay_id" in S.ASSAY_COLUMNS


def test_no_edge_column_is_spelled_assay_id_without_saying_internal():
    """The rename is the point, so a regression has to fail rather than read oddly.

    `MEMBERSHIP_COLUMNS.assay_id` is a seek `assay_assets.assay_id` and
    `EDGE_COLUMNS`' assay column is a dmac internal id. Membership is the frame
    stage B joins against, so reintroducing a bare `assay_id` on the edges frame
    puts two different id spaces under one name in adjacent frames, where
    picking the wrong one is a one-token edit that yields a populated, wrong
    column instead of an error.
    """
    for col in S.EDGE_COLUMNS:
        if "assay" in col:
            assert "internal" in col, f"{col} names an id space it does not hold"
    assert "assay_id" in S.MEMBERSHIP_COLUMNS  # the other space, deliberately bare


def test_nodes_cypher_aliases_the_declared_node_index():
    """Carry-in: the node index needs a contract both sides assert against.

    Pinned against a literal first, exactly as the schema test does for the
    fixture: asserting only projection-vs-constant is vacuous and would stay
    green through any reordering of the constant itself.
    """
    assert S.NODES_COLUMNS == ["uuid", "sample_id", "type"]
    assert _sources(extract.NODES_CYPHER) == {
        "uuid": "s.uuid", "sample_id": "s.id", "type": "s.type",
    }


def test_nodes_cypher_indexes_every_sample_node_not_just_connected_ones():
    """`MATCH (s:Sample)` and nothing else.

    plan_edges resolves every child_id and parent_id it writes through this
    frame, and a parent that is not yet the endpoint of any relationship is the
    normal case for the backfill. Restricting the match to nodes that already
    have an edge would turn exactly the samples stage 0 exists to connect into
    D_NO_NODE drops.
    """
    assert "-[" not in extract.NODES_CYPHER
    assert re.search(r"MATCH \(s:Sample\)\s*\n?\s*RETURN", extract.NODES_CYPHER)


def test_childof_cypher_reads_but_never_writes():
    for forbidden in ("MERGE", "CREATE", "DELETE", "SET "):
        assert forbidden not in extract.CHILDOF_CYPHER.upper()


def test_sop_columns_matches_the_frozen_stage0_fixture():
    """`sops` gained a contract in this task; the fixture predates it.

    make_stage0_fixture() is frozen and still hand-writes ["sop_id", "title"],
    and stage0.resolve_properties reads those names again. This is the link that
    stops the new constant drifting away from either of them.
    """
    assert S.SOP_COLUMNS == ["sop_id", "title"]
    assert list(S.make_stage0_fixture()["sops"].columns) == S.SOP_COLUMNS


# ---------------------------------------------------------------------------
# build_parents
# ---------------------------------------------------------------------------

def test_build_parents_uses_the_injected_server_helper():
    # The point of injection: key matching and semicolon splitting are the
    # server's, never reimplemented here.
    calls = []

    def fake_collect(meta):
        calls.append(meta)
        return ["TIS-260101ABC-1", "AB-260101ABC-1"]

    rows = [("D.IMG-260101ABC-1", '{"Parent": "TIS-260101ABC-1"}')]
    out = extract.build_parents(rows, fake_collect)
    assert calls == [{"Parent": "TIS-260101ABC-1"}]
    assert list(out.columns) == S.PARENT_COLUMNS
    assert set(out["token"]) == {"TIS-260101ABC-1", "AB-260101ABC-1"}


def test_build_parents_records_which_field_each_token_came_from():
    def fake_collect(meta):
        return ["TIS-260101ABC-1", "AB-260101ABC-1"]

    rows = [(
        "D.IMG-260101ABC-1",
        '{"Parent": "TIS-260101ABC-1", "AntibodyParent": "AB-260101ABC-1"}',
    )]
    out = extract.build_parents(rows, fake_collect)
    got = dict(zip(out["token"], out["field"]))
    assert got["TIS-260101ABC-1"] == "Parent"
    assert got["AB-260101ABC-1"] == "AntibodyParent"


def test_build_parents_survives_unparseable_metadata():
    def fake_collect(meta):
        return []

    out = extract.build_parents([("X-260101ABC-1", "not json")], fake_collect)
    assert len(out) == 0
    assert list(out.columns) == S.PARENT_COLUMNS


def test_build_parents_never_calls_the_helper_on_a_non_object_document():
    """A JSON document that parses to a list would make the server raise.

    collect_parent_tokens does `meta.items()`. A backfill over 163,000 rows
    cannot die on one malformed blob, so the row is skipped -- but it must be
    skipped BEFORE the helper sees it, or the extract dies in the container at
    an arbitrary point with every frame lost.
    """
    calls = []

    def fake_collect(meta):
        calls.append(meta)
        return []

    out = extract.build_parents(
        [("X-260101ABC-1", '["TIS-260101ABC-1"]'),
         ("Y-260101ABC-1", '"just a string"'),
         ("Z-260101ABC-1", "17")],
        fake_collect,
    )
    assert calls == []
    assert len(out) == 0


def test_build_parents_emits_tokens_the_production_regex_would_reject():
    """THE deliberate exception. Filtering here is the defect, not the fix.

    Production's UID_RE demands a 3+ letter sample type, so it discards every
    two-letter `AB` reference (~8,131 of them) before an edge is built -- the
    bug stage 0 exists to work around. The corrected regex is applied on the
    laptop by plan_edges, which COUNTS what it drops; a token filtered out here
    would be invisible to that ledger instead.
    """
    def fake_collect(meta):
        return ["AB-260101ABC-1", "some free text", "TIS-260101ABC-1"]

    out = extract.build_parents(
        [("D.IMG-260101ABC-1", '{"Parent": "x"}')], fake_collect
    )
    assert list(out["token"]) == ["AB-260101ABC-1", "some free text",
                                  "TIS-260101ABC-1"]
    # the two that the shipped patterns disagree about are both still here
    assert S.UID_RE_PROD.match("AB-260101ABC-1") is None
    assert S.UID_RE_FIXED.match("AB-260101ABC-1") is not None


def test_build_parents_preserves_the_helpers_order_and_deduplication():
    """collect_parent_tokens dedups first-seen across keys; do not re-sort it.

    The field attribution walks the metadata in key order, so an emitted order
    that diverged from the helper's would attribute a shared token to the wrong
    key.
    """
    def fake_collect(meta):
        return ["C-260101ABC-1", "A-260101ABC-1", "B-260101ABC-1"]

    out = extract.build_parents(
        [("D.IMG-260101ABC-1", '{"Parent": "x"}')], fake_collect
    )
    assert list(out["token"]) == ["C-260101ABC-1", "A-260101ABC-1",
                                  "B-260101ABC-1"]


def test_build_parents_attributes_a_token_shared_by_two_fields_to_the_first():
    """Matches the helper's own first-seen-wins dedup, so the two agree."""
    def fake_collect(meta):
        return ["TIS-260101ABC-1"]

    rows = [(
        "D.IMG-260101ABC-1",
        '{"Parent": "TIS-260101ABC-1", "AntibodyParent": "TIS-260101ABC-1"}',
    )]
    out = extract.build_parents(rows, fake_collect)
    assert list(out["field"]) == ["Parent"]


def test_build_parents_splits_a_semicolon_field_and_attributes_every_token():
    def fake_collect(meta):
        return ["TIS-260101ABC-1", "TIS-260101ABC-2"]

    rows = [("D.IMG-260101ABC-1",
             '{"Parent": "TIS-260101ABC-1; TIS-260101ABC-2"}')]
    out = extract.build_parents(rows, fake_collect)
    assert list(out["field"]) == ["Parent", "Parent"]


def test_build_parents_marks_an_unattributable_token_instead_of_guessing():
    """A token no metadata field explains must not be labelled "Parent".

    `field` is provenance the curator reads out of plan.parquet. Defaulting it
    to a real field name would state, in the artefact, that a field declared
    something it never declared -- a plausible-looking lie is worse than a
    visible gap.
    """
    def fake_collect(meta):
        return ["TIS-260101ABC-1"]

    rows = [("D.IMG-260101ABC-1", '{"Description": "no parent key here"}')]
    out = extract.build_parents(rows, fake_collect)
    assert list(out["field"]) == [extract.UNATTRIBUTED_FIELD]
    assert extract.UNATTRIBUTED_FIELD != "Parent"


def test_build_parents_ignores_a_non_string_parent_value_when_attributing():
    """The server skips non-str values; the attribution pass must agree.

    A list-valued Parent key would otherwise be str()-ed and produce a token
    that matches nothing, or crash on .split.
    """
    def fake_collect(meta):
        return ["TIS-260101ABC-1"]

    rows = [("D.IMG-260101ABC-1",
             '{"Parent": ["TIS-260101ABC-1"], "OtherParent": "TIS-260101ABC-1"}')]
    out = extract.build_parents(rows, fake_collect)
    assert list(out["field"]) == ["OtherParent"]


def test_build_parents_yields_nothing_for_empty_or_null_metadata():
    """NULL json_metadata must become an empty document, not a json.loads(None).

    All three shapes reach the helper as `{}` (which it handles) rather than
    raising, and none of them emits a row.
    """
    calls = []

    def fake_collect(meta):
        calls.append(meta)
        return []

    out = extract.build_parents(
        [("X-260101ABC-1", None), ("Y-260101ABC-1", ""),
         ("Z-260101ABC-1", "{}")],
        fake_collect,
    )
    assert len(out) == 0
    assert calls == [{}, {}, {}]
    assert all(isinstance(c, dict) for c in calls)


def test_build_parents_carries_one_row_per_token_across_samples():
    def fake_collect(meta):
        return [meta["Parent"]]

    out = extract.build_parents(
        [("D.IMG-260101ABC-1", '{"Parent": "TIS-260101ABC-1"}'),
         ("D.IMG-260101ABC-2", '{"Parent": "TIS-260101ABC-2"}')],
        fake_collect,
    )
    assert list(zip(out["child_uuid"], out["token"])) == [
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
        ("D.IMG-260101ABC-2", "TIS-260101ABC-2"),
    ]


def test_build_parents_output_feeds_plan_edges_unchanged():
    """End-to-end on the contract: the frame this task produces is the frame
    task 2 consumes. plan_edges selects `parents[S.PARENT_COLUMNS]`, so a
    producer that emitted the columns in another order would raise there --
    but only if the frame is built from the constant rather than a literal
    list that happens to match today."""
    from assay_hygiene import stage0

    def fake_collect(meta):
        return ["TIS-260101ABC-1"]

    parents = extract.build_parents(
        [("D.IMG-260101ABC-1", '{"Parent": "TIS-260101ABC-1"}')], fake_collect
    )
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(parents, fx["nodes"], fx["existing"])
    assert list(zip(plan["child_uuid"], plan["parent_uuid"])) == [
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1")
    ]


# ---------------------------------------------------------------------------
# projection guards and the node-index uniqueness check
# ---------------------------------------------------------------------------

def test_frame_declares_its_columns_even_for_an_empty_result():
    """A 0x0 frame writes a headerless parquet and KeyErrors on the laptop."""
    out = extract._frame([], S.CHILDOF_COLUMNS)
    assert list(out.columns) == S.CHILDOF_COLUMNS
    assert len(out) == 0


def test_frame_rejects_a_projection_that_does_not_match_the_contract():
    with pytest.raises(ValueError, match="contract"):
        extract._frame([{"uuid": "a", "sample_id": 1}], S.NODES_COLUMNS)
    with pytest.raises(ValueError, match="contract"):
        # right names, wrong order: silently swaps two columns' contents
        extract._frame([{"sample_id": 1, "uuid": "a", "type": "TIS"}],
                       S.NODES_COLUMNS)


def test_frame_keeps_the_declared_order():
    out = extract._frame(
        [{"uuid": "a", "sample_id": 1, "type": "TIS"}], S.NODES_COLUMNS
    )
    assert list(out.columns) == S.NODES_COLUMNS
    assert out.iloc[0]["sample_id"] == 1


def test_check_projection_reports_both_sides():
    with pytest.raises(ValueError) as exc:
        extract._check_projection(["a", "b"], ["a", "c"])
    assert "'b'" in str(exc.value) and "'c'" in str(exc.value)


def test_assays_row_count_is_not_the_acceptance_signal():
    """`assays` fans out on two independent axes, so len() cannot be trusted.

    A row count of 470 is equally consistent with a correct extract and with
    "the 17 junction-less assays were dropped by the inner joins, and 29 rows
    were duplicated by multi-project assays". The second is the exact failure
    the LEFT JOINs exist to prevent, and it makes those assays' edges resolve
    wrong instead of firing resolve_properties' fallback. The step 6 assertion
    is `nunique == 458`, never `len == 458`, so main must PRINT the distinct
    count -- the operator cannot recompute it from a number on a terminal.
    """
    assays = pd.DataFrame(
        [
            # assay 1 mapped to two projects -> two rows, one assay
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (1, "Comet Chip", 7, 3, 2, 11, "OTHER", 11, "Comet Chip"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", None, None),
        ],
        columns=S.ASSAY_COLUMNS,
    )
    line = extract.count_line("assays", assays)
    assert "3 rows" in line
    assert "2 distinct assay_id" in line


def test_count_line_leaves_an_unmultiplied_frame_as_a_bare_row_count():
    line = extract.count_line("nodes", S.make_stage0_fixture()["nodes"])
    assert "6 rows" in line
    assert "distinct" not in line


def test_assays_is_the_only_frame_whose_row_count_is_ambiguous():
    """Which frames need the distinct count, argued rather than assumed.

    `assays` is the only query that can emit more than one row per entity.
    `edges`/`childof` are one row per relationship, `nodes` one per node,
    `membership` one per assay_assets row, `sops` one per SOP, `samples` one per
    `GROUP BY s.id`, and `parents` is built in Python. `nodes` also has a
    strictly stronger guard already -- duplicate_uuids(), which RAISES rather
    than printing, and which catches the one thing a distinct count on `nodes`
    would catch.
    """
    assert set(extract.DISTINCT_KEYS) == {"assays"}
    assert extract.DISTINCT_KEYS["assays"] == "assay_id"
    # a typo here would only surface as a KeyError on the production box
    assert extract.DISTINCT_KEYS["assays"] in S.ASSAY_COLUMNS


def test_main_prints_the_acceptance_signal_through_count_line():
    """main() is untestable, so pin by ast the one line of it that matters here.

    The distinct assay count only helps if the operator SEES it. A revert of the
    print loop to a bare f-string would leave every other case green while
    removing the signal step 6 is judged on.
    """
    main_fn = [
        n for n in ast.walk(ast.parse(EXTRACT_PY.read_text()))
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    ][0]
    assert [
        n for n in ast.walk(main_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "count_line"
    ], "main must print through count_line"


def test_duplicate_uuids_finds_a_repeated_node_key():
    """plan_edges does dict(zip(nodes.uuid, nodes.sample_id)) -- last wins,
    silently. A duplicate uuid therefore resolves every edge touching it to an
    arbitrary one of the two sample_ids, uncounted. This extract is the
    producer of that index and the only place the ambiguity can be seen."""
    nodes = pd.DataFrame(
        [("TIS-260101ABC-1", 200, "TIS"),
         ("TIS-260101ABC-1", 999, "TIS"),
         ("D.IMG-260101ABC-1", 100, "D.IMG")],
        columns=S.NODES_COLUMNS,
    )
    assert extract.duplicate_uuids(nodes) == ["TIS-260101ABC-1"]


def test_duplicate_uuids_is_empty_for_a_unique_index():
    assert extract.duplicate_uuids(S.make_stage0_fixture()["nodes"]) == []


def test_duplicate_uuids_handles_an_empty_index():
    assert extract.duplicate_uuids(
        pd.DataFrame(columns=S.NODES_COLUMNS)
    ) == []


# ---------------------------------------------------------------------------
# the driver
# ---------------------------------------------------------------------------

DRIVER = REPO / "scripts" / "assay_hygiene" / "driver_extract.py"


def _driver_tree() -> ast.Module:
    return ast.parse(DRIVER.read_text())


def test_driver_imports_the_package_not_the_module():
    """Piping extract.py itself into `manage.py shell` raises.

    extract.py uses a relative import (`from . import _schema`), so executing it
    without package context fails on the import. The driver must therefore
    import it THROUGH the package, absolutely -- a relative import in the driver
    fails for the same reason.
    """
    imports = [n for n in ast.walk(_driver_tree())
               if isinstance(n, ast.ImportFrom)]
    package = [n for n in imports
               if n.module == "assay_hygiene" and n.level == 0
               and any(a.name == "extract" for a in n.names)]
    assert package, "driver must do `from assay_hygiene import extract`"
    assert not [n for n in imports if n.level], "no relative import in the driver"


def test_driver_puts_the_package_on_the_path_before_importing_it():
    tree = _driver_tree()
    inserts = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "insert"
        and any(isinstance(a, ast.Constant) and a.value == "/tmp/scripts"
                for a in n.args)
    ]
    assert inserts, "driver must sys.path.insert(0, '/tmp/scripts')"
    imp = [n for n in ast.walk(tree)
           if isinstance(n, ast.ImportFrom) and n.module == "assay_hygiene"][0]
    assert inserts[0].lineno < imp.lineno, "path insert must precede the import"


def test_driver_actually_runs_the_extraction():
    """A driver that imports and does nothing exits 0 and writes nothing."""
    calls = [
        n for n in ast.walk(_driver_tree())
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "main"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "extract"
    ]
    assert calls, "driver must call extract.main()"
