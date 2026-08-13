import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import stage0


def test_planner_keeps_only_creatable_references():
    fx = S.make_stage0_fixture()
    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    pairs = set(zip(plan["child_uuid"], plan["parent_uuid"]))
    assert pairs == {
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
        ("D.IMG-260101ABC-1", "AB-260101ABC-1"),
    }


def test_planner_counts_every_exclusion_by_reason():
    fx = S.make_stage0_fixture()
    _, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert residues[S.D_NOT_UID] == 1
    assert residues[S.D_NO_NODE] == 1
    assert residues[S.D_SELF_LOOP] == 1
    assert residues[S.D_ALREADY_EXISTS] == 1


def test_planner_reports_what_the_production_regex_would_have_dropped():
    # The whole point of the override: without it the AB edge never exists.
    fx = S.make_stage0_fixture()
    _, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert residues["prod_regex_would_reject"] == 1


def test_planner_resolves_ids_and_types_from_the_node_index():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    row = plan[plan["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert row["child_id"] == 100
    assert row["parent_id"] == 300
    assert row["child_type"] == "D.IMG"
    assert row["parent_type"] == "AB"
    assert row["field"] == "AntibodyParent"


def test_planner_is_idempotent_against_its_own_output():
    # Re-running after a successful write must plan nothing.
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    import pandas as pd
    now_existing = pd.concat([
        fx["existing"],
        plan[["child_uuid", "parent_uuid"]],
    ], ignore_index=True)
    plan2, residues2 = stage0.plan_edges(fx["parents"], fx["nodes"], now_existing)
    assert len(plan2) == 0
    assert residues2[S.D_ALREADY_EXISTS] == 3


# The cases below cover what the five above cannot: two branches the frozen
# fixture never reaches (found by mutation-testing -- deleting either left all
# five green), and the column-order contract. All of them build their own frames
# rather than growing make_stage0_fixture(), whose rows are pinned by three
# later tasks.


def _drops(residues):
    """Every drop reason in a residue dict.

    "prod_regex_would_reject" is excluded because it is report-only: it
    overlaps the keepers (the AB reference is counted there AND planned) rather
    than excluding anything, so including it would break the identity below.
    Everything else is summed by iteration, not by an enumerated key list, so a
    drop reason added later without a matching assertion update turns the
    accounting test red instead of slipping past it.
    """
    return sum(v for k, v in residues.items() if k != "prod_regex_would_reject")


def test_planner_collapses_a_pair_declared_under_two_fields():
    """One edge per (child, parent), no matter how many fields declare it.

    Also pins the docstring's accounting claim: nothing is dropped silently, so
    len(plan) + every drop reason == len(parents), on plain input AND on input
    carrying a duplicate. The collapsed duplicate used to be the sole reference
    that left no trace, which made the same sum come up one short.
    """
    fx = S.make_stage0_fixture()

    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert len(plan) + _drops(residues) == len(fx["parents"])

    dup = pd.concat([
        fx["parents"],
        pd.DataFrame([("D.IMG-260101ABC-1", "AntibodyParent", "TIS-260101ABC-1")],
                     columns=S.PARENT_COLUMNS),
    ], ignore_index=True)
    plan2, residues2 = stage0.plan_edges(dup, fx["nodes"], fx["existing"])

    pairs = list(zip(plan2["child_uuid"], plan2["parent_uuid"]))
    assert pairs.count(("D.IMG-260101ABC-1", "TIS-260101ABC-1")) == 1
    assert len(pairs) == len(set(pairs))
    # first declaration wins, so the surviving row keeps the field it came with
    assert plan2.loc[plan2["parent_uuid"] == "TIS-260101ABC-1",
                     "field"].iloc[0] == "Parent"
    # the collapsed duplicate is accounted for under its own reason, so the
    # ledger still balances -- an operator can tell it from a lost reference
    assert residues2["duplicate_reference"] == 1
    assert len(plan2) + _drops(residues2) == len(dup)


def test_planner_drops_a_reference_whose_child_is_not_a_node():
    """The child half of the node-index guard.

    Every child in the fixture is registered, so dropping `child_uuid not in
    node_id` from the guard changes nothing there. Against real data it turns a
    counted drop into `KeyError: node_id[child_uuid]`, which kills the whole
    run. D_NO_NODE is reused here for lack of a child-side constant; its literal
    value reads "parent_not_a_node", which understates this case.
    """
    fx = S.make_stage0_fixture()
    orphan = pd.DataFrame(
        [("D.IMG-260101ABC-9", "Parent", "TIS-260101ABC-1")],
        columns=S.PARENT_COLUMNS,
    )
    plan, residues = stage0.plan_edges(orphan, fx["nodes"], fx["existing"])
    assert len(plan) == 0
    assert residues[S.D_NO_NODE] == 1


def test_planner_is_not_fooled_by_parents_columns_in_a_different_order():
    """Column ORDER of `parents` must not change the answer.

    plan_edges unpacks the frame positionally. A producer emitting
    child_uuid | token | field swaps two of the three, every token then fails
    UID validation, and the run returns an EMPTY plan with a fully-populated
    not_a_uid count -- a silent wrong answer on a production data fix, not a
    crash. Asserted against the correctly-ordered result rather than against
    literals, so it cannot pass by both paths being equally broken: the plan it
    compares to is non-empty and is itself pinned by the cases above.
    """
    fx = S.make_stage0_fixture()
    expected_plan, expected_res = stage0.plan_edges(
        fx["parents"], fx["nodes"], fx["existing"])
    assert len(expected_plan) == 2, "non-vacuity: the reference plan must have rows"

    swapped = fx["parents"][["child_uuid", "token", "field"]]
    assert list(swapped.columns) != S.PARENT_COLUMNS
    plan, residues = stage0.plan_edges(swapped, fx["nodes"], fx["existing"])

    pd.testing.assert_frame_equal(plan, expected_plan)
    assert residues == expected_res

    # ...and a frame genuinely missing a declared column must fail loudly
    with pytest.raises(KeyError):
        stage0.plan_edges(
            fx["parents"].drop(columns=["field"]), fx["nodes"], fx["existing"])


# --- resolve_properties ------------------------------------------------------


def _resolved():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    return stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )


def test_shared_assay_is_stamped_when_both_endpoints_are_registered():
    out = _resolved()
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["assay_id"] == 1
    assert row["internal_assay_id"] == 11
    assert row["internal_assay_title"] == "Comet Chip"
    assert row["n_shared"] == 1
    assert row["assay_source"] == "junction"


def test_disjoint_endpoints_produce_a_dark_edge_rather_than_a_guess():
    # The AB parent is in assay 2, the child in assay 1. Stage 0 infers nothing;
    # the edge is created dark and stages A-F deal with it.
    out = _resolved()
    row = out[out["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert pd.isna(row["assay_id"])
    assert pd.isna(row["internal_assay_id"])
    assert row["n_shared"] == 0
    assert row["assay_source"] == "none"


def test_protocol_is_extracted_from_the_child_and_titled_from_sops():
    out = _resolved()
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["protocol_id"] == 5
    assert row["protocol_title"] == "Comet Chip SOP"


def test_output_carries_exactly_the_server_model_fields_plus_reporting_columns():
    out = _resolved()
    assert list(out.columns) == S.STAGE0_PLAN_COLUMNS
    # the first nine must match DerivedFromRelRow in order, because the applier
    # slices them straight into the payload
    assert list(out.columns)[:9] == S.EDGE_ROW_COLUMNS


def test_an_empty_plan_still_yields_a_well_formed_frame():
    """The idempotent re-run: everything already written, so nothing is planned.

    plan_edges returning zero rows is the normal steady state once stage 0 has
    applied, and the report and the applier both read the frame's columns before
    they read its rows. An empty list of tuples must therefore still produce the
    full column set rather than a bare 0x0 frame.
    """
    fx = S.make_stage0_fixture()
    empty, _ = stage0.plan_edges(
        fx["parents"], fx["nodes"],
        pd.DataFrame(list(zip(fx["parents"]["child_uuid"], fx["parents"]["token"])),
                     columns=S.CHILDOF_COLUMNS))
    assert len(empty) == 0
    out = stage0.resolve_properties(
        empty, fx["samples"], fx["membership"], fx["assays"], fx["sops"])
    assert len(out) == 0
    assert list(out.columns) == S.STAGE0_PLAN_COLUMNS


def test_the_plans_own_columns_ride_through_unchanged_and_in_order():
    """The seven planner columns are re-emitted, not re-derived.

    resolve_properties rebuilds every row positionally into a wider frame, and
    nothing downstream recovers these: stage B keys its precedent rules on
    (child_type, parent_type) and the dry-run report prints `field`. Swapping
    the two type columns or dropping `field` is a silent wrong answer three
    stages later, not a crash, and no other case here reads them. Compared
    against the plan itself, which also pins that row order is preserved.
    """
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"])
    carried = ["child_uuid", "parent_uuid", "child_id", "parent_id",
               "child_type", "parent_type", "field"]
    # non-vacuity: a swap is only detectable if the columns actually differ
    assert len(plan) == 2
    assert plan["child_type"].tolist() != plan["parent_type"].tolist()
    pd.testing.assert_frame_equal(out[carried], plan[carried])


def test_assay_with_no_junction_row_falls_back_to_assay_id_and_title():
    # neo4j_sync.py:1011-1021. 17 of 458 production assays have no junction row;
    # the server does NOT skip them, it uses (assay_id, assays.title).
    fx = S.make_stage0_fixture()
    # put BOTH endpoints of the AB edge in assay 2, which has no junction row
    membership = pd.concat([
        fx["membership"],
        pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS),
    ], ignore_index=True)
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan, fx["samples"], membership, fx["assays"], fx["sops"]
    )
    row = out[out["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert row["assay_id"] == 2
    assert row["internal_assay_id"] == 2
    assert row["internal_assay_title"] == "Antibody Panel"
    assert row["assay_source"] == "fallback"


def test_multiple_shared_assays_pick_the_minimum_internal_assay_id():
    # neo4j_sync.py:1064-1078. Arbitrary but deterministic; stage 0 reproduces
    # it and reports the count so a curator can settle those edges by hand.
    fx = S.make_stage0_fixture()
    assays = pd.concat([
        fx["assays"],
        pd.DataFrame([(3, "Other", 9, 3, 2, 10, "MIT_SRP", 4, "Other")],
                     columns=S.ASSAY_COLUMNS),
    ], ignore_index=True)
    membership = pd.concat([
        fx["membership"],
        pd.DataFrame([(100, 3), (200, 3)], columns=S.MEMBERSHIP_COLUMNS),
    ], ignore_index=True)
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan, fx["samples"], membership, assays, fx["sops"]
    )
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["n_shared"] == 2
    assert row["internal_assay_id"] == 4      # min(11, 4)
    assert row["assay_id"] == 3               # the assay that carried it


# The cases below are not in the task brief. The brief's resolution loop was
# last-row-wins over the assays frame; the server is minimum-wins
# (_resolve_internal_assays, neo4j_sync.py:879-881), and the assays frame
# genuinely carries duplicate assay_id rows because the extractor LEFT JOINs the
# junction table and joins through investigations_projects. The first two pin
# that; the rest cover branches the frozen fixture never reaches, all found by
# mutation-testing the assertions above.


def _assay_row(assay_id, title, internal_assay_id, internal_assay_title):
    """One ASSAY_COLUMNS row; only the four columns under test vary."""
    return (assay_id, title, 7, 3, 2, 10, "MIT_SRP",
            internal_assay_id, internal_assay_title)


def _resolve_with(assays, fx=None, membership=None):
    fx = fx or S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    return stage0.resolve_properties(
        plan, fx["samples"],
        fx["membership"] if membership is None else membership,
        assays, fx["sops"],
    )


def test_duplicate_assay_rows_keep_the_minimum_internal_assay_id():
    """One assay_id mapped to several internal assays keeps the SMALLEST.

    The server's own rule (neo4j_sync.py:879-881, "Keep smallest
    internal_assay_id per assay_id (deterministic for 1:N)"). Asserted under both
    row orders because the alternative reading -- last row wins -- passes under
    one order and fails under the other, which is exactly the non-determinism
    this guards: the extractor's row order is not stable across extracts.
    """
    rows = [
        _assay_row(1, "Comet Chip", 11, "Comet Chip A"),
        _assay_row(1, "Comet Chip", 4, "Comet Chip B"),
    ]
    for order in (rows, list(reversed(rows))):
        out = _resolve_with(pd.DataFrame(order, columns=S.ASSAY_COLUMNS))
        row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
        assert row["internal_assay_id"] == 4
        # the title must travel with the winning id, not with some other row
        assert row["internal_assay_title"] == "Comet Chip B"
        assert row["assay_source"] == "junction"
        # n_shared counts shared ASSAYS, not junction rows: still one assay
        assert row["n_shared"] == 1


def test_a_junction_row_beats_a_fallback_row_for_the_same_assay():
    """Precedence between the two id spaces, in both row orders.

    An assay with a junction row AND a row whose internal_assay_id is NULL (the
    LEFT JOIN emits both when the join through investigations_projects
    multiplies rows) must resolve through the junction. Two ways to get this
    wrong: let the NULL row overwrite the resolved one (order-dependent), or let
    the fallback candidate into the minimum comparison -- its id is an
    assays.id, and 1 < 11 numerically even though the two ids name nothing
    comparable. The server cannot make either mistake because it computes the
    fallback only for assay_ids the junction never resolved
    (neo4j_sync.py:1011-1027).
    """
    rows = [
        _assay_row(1, "Comet Chip", 11, "Comet Chip"),
        _assay_row(1, "Comet Chip", None, None),
    ]
    for order in (rows, list(reversed(rows))):
        out = _resolve_with(pd.DataFrame(order, columns=S.ASSAY_COLUMNS))
        row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
        assert row["assay_id"] == 1
        assert row["internal_assay_id"] == 11
        assert row["internal_assay_title"] == "Comet Chip"
        assert row["assay_source"] == "junction"


def test_a_fallback_assay_with_no_title_carries_an_empty_string():
    """neo4j_sync.py:1021 writes `title or ""` on the fallback path, never NULL.

    Mirrored rather than improved. The applier ships internal_assay_title
    straight into DerivedFromRelRow, so an edge carrying "" is what the upload
    pipeline would have produced for a titleless assay; emitting None instead
    would make stage 0's edges distinguishable from the server's.
    """
    out = _resolve_with(
        pd.DataFrame([_assay_row(1, None, None, None)], columns=S.ASSAY_COLUMNS))
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["assay_source"] == "fallback"
    assert row["assay_id"] == 1
    assert row["internal_assay_id"] == 1
    assert row["internal_assay_title"] == ""


def test_a_shared_assay_missing_from_the_assays_frame_is_reported_not_guessed():
    """n_shared > 0 with assay_source "none" is a real, visible state.

    The server resolves shared assay_ids against the junction table and then the
    assays table; one that neither knows leaves best_assay_id None and the edge
    goes out dark (neo4j_sync.py:1064-1080). Stage 0 does the same and leaves
    n_shared standing, so the report shows an edge that HAD a shared assay and
    still could not be labelled -- an extract bug, not a dark edge.
    """
    fx = S.make_stage0_fixture()
    assays = fx["assays"][fx["assays"]["assay_id"] != 1]
    out = _resolve_with(assays, fx=fx)
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["n_shared"] == 1
    assert pd.isna(row["assay_id"])
    assert pd.isna(row["internal_assay_id"])
    assert row["assay_source"] == "none"


def test_protocol_lookup_mirrors_every_server_miss():
    """The four protocol outcomes, none of which the fixture's plan reaches.

    Both planned fixture edges share child 100, so the fixture proves only the
    happy path. neo4j_sync.py:969-985 also accepts a lowercase "protocol" key,
    swallows unparseable json_metadata, tolerates a child with no samples row,
    and emits protocol_id with a NULL title when the sop is unknown.

    Child 5 pins the server's `if protocol_id` truthiness test (neo4j_sync.py:
    1060), which suppresses the title lookup for sop id 0. sops.id is an
    auto-increment key so no live row can hit it; the case is here because it is
    the only thing separating the server's expression from `is not None`, and an
    unpinned mirror is one nobody can tell has drifted.
    """
    plan = pd.DataFrame(
        [(f"C-260101ABC-{i}", "TIS-260101ABC-1", i, 900, "DNA", "TIS", "Parent")
         for i in (1, 2, 3, 4, 5)],
        columns=["child_uuid", "parent_uuid", "child_id", "parent_id",
                 "child_type", "parent_type", "field"],
    )
    samples = pd.DataFrame(
        [
            (1, "C-260101ABC-1", '{"protocol": "http://x/sops/5"}', None, "10"),
            (2, "C-260101ABC-2", "not json at all", None, "10"),
            (3, "C-260101ABC-3", '{"Protocol": "http://x/sops/77"}', None, "10"),
            # child 4 has no samples row at all
            (5, "C-260101ABC-5", '{"Protocol": "http://x/sops/0"}', None, "10"),
        ],
        columns=S.SAMPLE_COLUMNS,
    )
    out = stage0.resolve_properties(
        plan, samples,
        pd.DataFrame([], columns=S.MEMBERSHIP_COLUMNS),
        pd.DataFrame([], columns=S.ASSAY_COLUMNS),
        pd.DataFrame([(5, "Comet Chip SOP"), (0, "Sop Zero")],
                     columns=["sop_id", "title"]),
    ).set_index("child_id")

    assert out.loc[1, "protocol_id"] == 5          # lowercase key is accepted
    assert out.loc[1, "protocol_title"] == "Comet Chip SOP"
    assert pd.isna(out.loc[2, "protocol_id"])      # unparseable metadata
    assert out.loc[3, "protocol_id"] == 77         # sop id kept...
    assert pd.isna(out.loc[3, "protocol_title"])   # ...title unknown
    assert pd.isna(out.loc[4, "protocol_id"])      # no samples row
    assert out.loc[5, "protocol_id"] == 0          # falsy id kept...
    assert pd.isna(out.loc[5, "protocol_title"])   # ...but its title suppressed


def test_resolve_is_not_fooled_by_frames_whose_columns_are_reordered():
    """Column ORDER of `samples` and `membership` must not change the answer.

    Both are unpacked positionally. A producer emitting sample_id |
    json_metadata | uuid silently reads the uuid as the metadata blob and every
    protocol comes back NULL; a membership frame emitting assay_id | sample_id
    indexes the world by the wrong key and every edge comes back dark. Neither
    crashes. Asserted against the correctly-ordered result, which the cases
    above pin and which is checked non-vacuous here, so it cannot pass by both
    paths being equally broken.
    """
    fx = S.make_stage0_fixture()
    expected = _resolved()
    assert expected["protocol_id"].notna().any(), "non-vacuity: a protocol resolved"
    assert (expected["n_shared"] > 0).any(), "non-vacuity: an assay was shared"

    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan,
        fx["samples"][["sample_id", "json_metadata", "uuid",
                       "created_at", "project_ids"]],
        fx["membership"][["assay_id", "sample_id"]],
        fx["assays"],
        fx["sops"],
    )
    pd.testing.assert_frame_equal(out, expected)

    # ...and a frame genuinely missing a declared column must fail loudly
    with pytest.raises(KeyError):
        stage0.resolve_properties(
            plan, fx["samples"].drop(columns=["json_metadata"]),
            fx["membership"], fx["assays"], fx["sops"])
