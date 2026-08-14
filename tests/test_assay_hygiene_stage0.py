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


# --- reconcile_childof -------------------------------------------------------


def test_reconciliation_surfaces_childof_edges_metadata_no_longer_declares():
    fx = S.make_stage0_fixture()
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    pairs = set(zip(recon["child_uuid"], recon["parent_uuid"]))
    assert pairs == {("D.IMG-260101ABC-1", "TIS-260101ABC-77")}
    assert recon.iloc[0]["reason"] == "not_declared_by_metadata"


def test_reconciliation_never_proposes_an_action():
    # Operator ruling 2026-08-13: CHILD_OF is left alone. This file is a report.
    fx = S.make_stage0_fixture()
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    assert list(recon.columns) == ["child_uuid", "parent_uuid", "reason"]


def test_reconciliation_of_a_fully_declared_graph_keeps_its_columns():
    """Zero unmatched edges is the good outcome, and it still has to be a frame.

    Task 7 writes this straight to `reconciliation.csv`, and a bare 0x0 frame
    writes a file with no header row -- an empty CSV and a CSV of an empty
    result are the same artifact, which is precisely the confusion the
    reconciliation exists to avoid.
    """
    fx = S.make_stage0_fixture()
    declared = pd.DataFrame(
        list(zip(fx["parents"]["child_uuid"], fx["parents"]["token"])),
        columns=S.CHILDOF_COLUMNS,
    )
    recon = stage0.reconcile_childof(declared, fx["parents"])
    assert len(recon) == 0
    assert list(recon.columns) == ["child_uuid", "parent_uuid", "reason"]


# --- build_report ------------------------------------------------------------
#
# The report IS the gate: the operator reads it and then authorises a ~90,000
# relationship write. So these cases assert what an operator would act on -- a
# count next to the noun it counts -- rather than that a digit appears
# somewhere. Every one was mutation-tested; `assert "1" in report` passes
# against almost any report and pins nothing.


def _residues(overrides=None):
    """A residues dict in plan_edges' own key order."""
    base = {
        S.D_NOT_UID: 0, S.D_NO_NODE: 0, S.D_SELF_LOOP: 0, S.D_ALREADY_EXISTS: 0,
        "duplicate_reference": 0, "prod_regex_would_reject": 0,
    }
    base.update(overrides or {})
    return base


def _edge(**kw):
    """One STAGE0_PLAN_COLUMNS row; only the columns under test vary."""
    row = dict.fromkeys(S.STAGE0_PLAN_COLUMNS, None)
    row.update(
        child_id=1, child_uuid="C-260101ABC-1",
        parent_id=2, parent_uuid="P-260101ABC-1",
        child_type="DNA", parent_type="TIS", field="Parent",
        n_shared=0, assay_source="none",
    )
    row.update(kw)
    return row


def _resolved_frame(*rows):
    return pd.DataFrame(list(rows), columns=S.STAGE0_PLAN_COLUMNS)


def _no_childof():
    return pd.DataFrame([], columns=["child_uuid", "parent_uuid", "reason"])


def _para(report, needle):
    """The one blank-line-delimited block containing `needle`.

    Asserting on the block rather than the whole report is what makes an
    attribution testable: a claim is wrong if it sits in the same paragraph as
    the wrong cause, not merely if both words appear in the document. The
    uniqueness check is load-bearing too -- a needle that starts matching twice
    means the report says the same thing in two places, and the case that reads
    it is no longer reading what it thinks.
    """
    blocks = [b for b in report.split("\n\n") if needle in b]
    assert len(blocks) == 1, f"expected 1 paragraph containing {needle!r}, got {len(blocks)}"
    return blocks[0]


def _row(report, needle):
    """The one line containing `needle`, so a count can be pinned to its row."""
    lines = [ln for ln in report.splitlines() if needle in ln]
    assert len(lines) == 1, f"expected 1 line containing {needle!r}, got {len(lines)}"
    return lines[0]


def _fixture_report():
    fx = S.make_stage0_fixture()
    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    resolved = stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    return stage0.build_report(resolved, residues, recon), residues


def test_report_states_every_residue_and_the_regex_override():
    report, residues = _fixture_report()

    assert "2 edges to create" in report
    # Per-reason accounting, so nothing is dropped silently. Iterated off the
    # dict rather than a hardcoded list of the four D_* constants: plan_edges
    # has already gained a fifth reason since this case was specified, and a
    # sixth must turn this red rather than quietly vanish from the gate.
    assert "duplicate_reference" in residues, "non-vacuity: the fifth reason exists"
    for reason in residues:
        assert reason in report, f"{reason} is counted but never rendered"
    # the override must be stated, not buried
    assert "prod_regex_would_reject" in report
    # labelled vs dark split
    assert "1 labelled" in report and "1 dark" in report
    # the tiebreak count is a standing regression guard
    assert "min-internal_assay_id tiebreak" in report
    # reconciliation is reported but not actioned
    assert "**1** CHILD_OF edges are not declared" in report
    assert "Nothing acts on them" in report


def test_report_lists_hops_so_a_reviewer_can_spot_an_unexpected_one():
    report, _ = _fixture_report()
    assert "D.IMG -> TIS" in report
    assert "D.IMG -> AB" in report


def test_report_renders_a_drop_reason_it_has_never_heard_of():
    """A reason added to plan_edges later must not vanish from the operator's gate.

    The report cannot know what plan_edges will count next, so it iterates the
    residues dict instead of an enumerated key list. An unlabelled reason is
    rendered with its raw key and its count, and it still lands in the ledger
    total -- being counted but unrendered is the same as being dropped silently,
    which is the spec's one binding constraint.
    """
    report = stage0.build_report(
        _resolved_frame(_edge()),
        _residues({S.D_NOT_UID: 2, "invented_later": 7}),
        _no_childof(),
    )
    row = _row(report, "| `invented_later` |")
    assert row.endswith("| 7 |")
    assert "**9**" in _row(report, "excluded, total")


def test_report_ledger_reconciles_created_plus_excluded():
    """created + excluded == references considered, and the override is not summed.

    `prod_regex_would_reject` overlaps the keepers rather than excluding
    anything (plan_edges counts it and then keeps the reference), so summing it
    here would report more references than the parents extract holds and make
    the operator's one external cross-check fail on a correct run.
    """
    report = stage0.build_report(
        _resolved_frame(_edge(), _edge(child_uuid="C-260101ABC-2")),
        _residues({S.D_NOT_UID: 3, S.D_SELF_LOOP: 1, "prod_regex_would_reject": 5}),
        _no_childof(),
    )
    assert "**4**" in _row(report, "excluded, total")
    assert "**2**" in _row(report, "| **created**")
    assert "**6**" in _row(report, "| **references considered**")


def test_report_calls_the_node_gap_an_endpoint_not_a_parent():
    """D_NO_NODE's literal value understates the branch it names.

    plan_edges raises it when EITHER endpoint is missing from the node index,
    but the constant reads `parent_not_a_node` and Tasks 5-6 depend on its
    value, so it is frozen. The operator reads the label, not the constant, so
    the label is where this gets told truthfully.
    """
    report = stage0.build_report(
        _resolved_frame(_edge()), _residues({S.D_NO_NODE: 4}), _no_childof())
    row = _row(report, f"| `{S.D_NO_NODE}` |")
    assert "endpoint" in row and "child" in row
    assert row.endswith("| 4 |")


def test_report_does_not_blame_the_antibody_fix_for_the_anchor_difference():
    """The two regexes differ in three ways and the counter separates none of them.

    Verified against the patterns themselves: `AB-260101ABC-1` (two-letter type)
    and `X.TIS-260101ABC-1` (a dotted prefix other than A. or D.) are both
    accepted by UID_RE_FIXED and rejected by UID_RE_PROD, so both feed this
    count. The anchor difference runs the OTHER way -- `TIS-260101ABC-1\\n` is
    accepted by production's `$` and rejected by `\\Z` -- so it can only ever
    land in not_a_uid. Attributing the whole count to the antibody fix would be
    an overclaim; attributing any of it to the anchors would be wrong in the
    opposite direction.
    """
    report = stage0.build_report(
        _resolved_frame(_edge()),
        _residues({"prod_regex_would_reject": 9}),
        _no_childof(),
    )
    for difference in (r"[A-Z]{3,}", r"[A-Z]{2,}", r"([AD]\.)?", r"([A-Z]\.)?",
                       r"\A", r"\Z"):
        assert difference in report, f"{difference} is never shown"
    assert "**9**" in _para(report, "`prod_regex_would_reject`:")

    # Presence is not enough: a mutant that SWAPS the table's two data columns
    # leaves all six tokens above present and every other assertion here green,
    # while telling the operator production allows the two-letter type and the
    # fix requires three -- the exact inverse of why the override exists. Pinned
    # per row, and against the header, so the columns cannot silently trade
    # places in either direction.
    header = _row(report, "| Difference |")
    assert header.index("UID_RE_PROD") < header.index("UID_RE_FIXED")
    type_row = _row(report, "| sample-type code |")
    assert type_row.index(r"[A-Z]{3,}") < type_row.index(r"[A-Z]{2,}"), \
        "production is the stricter pattern; the fix is what allows `AB`"
    prefix_row = _row(report, "| dotted prefix |")
    assert prefix_row.index(r"([AD]\.)?") < prefix_row.index(r"([A-Z]\.)?"), \
        "production is the stricter pattern; the fix is what allows any prefix"

    # Keyed on the claim, not on the evidence: pinning only that "trailing
    # newline" and "not_a_uid" share a paragraph lets the sentence that states
    # the DIRECTION be deleted with every assertion still green (mutation M4).
    anchors = _para(report, "cannot add to this count")
    assert "trailing newline" in anchors
    assert S.D_NOT_UID in anchors, "the anchor difference must be sent to not_a_uid"
    assert "antibody" not in anchors.lower()
    assert "AB" not in anchors


def test_the_regex_section_reports_what_this_run_saw_not_a_past_extract():
    """The report is regenerated against every extract; a dated claim is not.

    It used to state that on the 2026-08-13 extract every reference in this count
    was `AB`-prefixed: true of that data, and printed verbatim against every
    extract after it. Derived from the plan in hand instead. `X.TIS-...` is
    rejected by production for its PREFIX exactly as `AB-...` is rejected for its
    LENGTH, so a run carrying both must name both rather than credit the whole
    count to the antibody fix.
    """
    # non-vacuity, read off the patterns themselves rather than assumed
    for token in ("AB-260101ABC-1", "X.TIS-260101ABC-1"):
        assert S.UID_RE_FIXED.match(token) and not S.UID_RE_PROD.match(token)
    assert S.UID_RE_PROD.match("TIS-260101ABC-2"), "the control is in neither count"

    report = stage0.build_report(
        _resolved_frame(
            _edge(child_uuid="C-260101ABC-1", parent_uuid="AB-260101ABC-1"),
            _edge(child_uuid="C-260101ABC-2", parent_uuid="AB-260101ABC-2"),
            _edge(child_uuid="C-260101ABC-3", parent_uuid="X.TIS-260101ABC-1"),
            _edge(child_uuid="C-260101ABC-4", parent_uuid="TIS-260101ABC-2"),
        ),
        _residues({"prod_regex_would_reject": 3}),
        _no_childof(),
    )
    observed = _para(report, "sample-type codes seen on this run")
    assert "`AB` (2)" in observed
    assert "`TIS` (1)" in observed, "the dotted prefix feeds the same count"
    assert "**3**" in observed
    assert "2026-08-13" not in report, "no run may print another run's observation"

    # A run with no such reference says so, rather than inheriting the claim.
    clean = stage0.build_report(
        _resolved_frame(_edge(parent_uuid="TIS-260101ABC-2")),
        _residues({"prod_regex_would_reject": 3}), _no_childof())
    assert "sample-type codes seen on this run" not in clean
    assert "no planned edge carries" in _para(clean, "measured, not assumed")


def test_the_override_paragraph_does_not_promise_every_counted_reference_is_created():
    """"Stage 0 includes them" is true of the counter, not of every reference in it.

    The counter increments at the validation point, ahead of the self-loop,
    missing-node, already-exists and duplicate checks. That placement is correct
    -- it measures what the live pattern would throw away, not what survives
    everything else -- so the sentence is what has to move: on the real extract
    8,120 of the 8,127 counted become edges and seven are counted and then
    excluded for another reason. The operator reads this line as a statement
    about the write.
    """
    report = stage0.build_report(
        _resolved_frame(_edge()),
        _residues({"prod_regex_would_reject": 9, S.D_SELF_LOOP: 1}),
        _no_childof(),
    )
    para = _para(report, "`prod_regex_would_reject`:")
    assert "**9**" in para
    assert "excluded for another reason" in para, "the qualifying clause is the fix"
    # and it says WHEN the count is taken, so a reader can see why it can exceed
    # the edges created rather than having to take the qualification on trust
    assert "before" in para and "duplicate" in para


def test_the_tiebreak_count_covers_only_edges_that_actually_got_a_label():
    """n_shared > 1 alone is not a tiebreak.

    The spec measures 28 tiebreaks "out of 82,663 labelled edges". An edge whose
    shared assays are all missing from the assays extract goes out dark: nothing
    was chosen, so reporting it as resting on the tiebreak tells the operator a
    curator can settle an edge that has no label to settle.
    """
    report = stage0.build_report(
        _resolved_frame(
            _edge(child_uuid="C-260101ABC-1", n_shared=3, assay_source="none"),
            _edge(child_uuid="C-260101ABC-2", n_shared=2, assay_source="junction",
                  assay_id=4, internal_assay_id=11, internal_assay_title="Comet Chip"),
        ),
        _residues(), _no_childof(),
    )
    assert "**1**" in _row(report, "min-internal_assay_id tiebreak")


def test_report_lists_the_tiebreak_edges_so_a_curator_can_settle_them():
    # Spec: "report.md carries the count and lists those 28 edges, so a curator
    # can settle them by hand if they choose." A count alone is not actionable.
    report = stage0.build_report(
        _resolved_frame(
            _edge(child_uuid="C-260101ABC-7", parent_uuid="P-260101ABC-7",
                  n_shared=3, assay_source="junction", assay_id=4,
                  internal_assay_id=11, internal_assay_title="Comet Chip"),
            _edge(child_uuid="C-260101ABC-8", n_shared=1, assay_source="junction",
                  internal_assay_id=12),
            # one dark edge, as production has 7,871 of: it makes the whole
            # internal_assay_id column float64, which is how a labelled id
            # reaches the report as 11.0
            _edge(child_uuid="C-260101ABC-9", internal_assay_id=None),
        ),
        _residues(), _no_childof(),
    )
    row = _row(report, "C-260101ABC-7")
    # `| 11 |`, not `11`: any id column holding one null is float64, so a bare
    # substring check passes against the useless `11.0` this used to print
    for cell in ("| P-260101ABC-7 |", "| 3 |", "| 11 |", "| Comet Chip |"):
        assert cell in row
    assert "C-260101ABC-8" not in report, "one shared assay is no tiebreak"


def test_a_truncated_tiebreak_list_says_how_many_it_left_out():
    """Truncation is fine; silent truncation in the gate report is not."""
    rows = [
        _edge(child_uuid=f"C-260101ABC-{i}", n_shared=2, assay_source="junction",
              internal_assay_id=11)
        for i in range(stage0.TIEBREAK_LIST_CAP + 3)
    ]
    report = stage0.build_report(_resolved_frame(*rows), _residues(), _no_childof())
    assert f"C-260101ABC-{stage0.TIEBREAK_LIST_CAP - 1}" in report
    assert f"C-260101ABC-{stage0.TIEBREAK_LIST_CAP}" not in report
    # Anchored on "and <n> more", not on the bare "3 more" this used to carry:
    # with a cap of 50 and 53 rows, a mutant printing the RAW tiebreak count
    # renders "and 53 more", which contains the substring "3 more" and passed.
    # The overstatement it hides is the whole cap.
    left_out = _row(report, "more, in `plan.parquet`")
    assert f"and {len(rows) - stage0.TIEBREAK_LIST_CAP:,} more," in left_out
    assert f"and {len(rows):,} more" not in left_out, "that is the total, not the remainder"


def test_report_separates_a_dark_edge_from_an_unresolvable_shared_assay():
    """An edge with n_shared > 0 and no label is an extract gap, not a dark edge.

    resolve_properties keeps the two apart on purpose. Pooling them in the
    report hides a broken assays extract behind a plausible-looking dark count,
    and the operator authorises ~90,000 writes off this document.
    """
    report = stage0.build_report(
        _resolved_frame(
            _edge(child_uuid="C-260101ABC-1", n_shared=0, assay_source="none"),
            _edge(child_uuid="C-260101ABC-2", n_shared=2, assay_source="none"),
            _edge(child_uuid="C-260101ABC-3", n_shared=1, assay_source="junction",
                  assay_id=1, internal_assay_id=11),
        ),
        _residues(), _no_childof(),
    )
    assert "3 edges to create" in report
    assert "1 labelled" in report and "2 dark" in report
    assert "**1**" in _row(report, "no assay is shared by both endpoints")
    assert "**1**" in _row(report, "the assays extract does not describe")


def test_report_counts_labelled_edges_per_hop():
    """The hop table's own arithmetic, including on an untyped node.

    A Sample node with no `type` is possible in the graph, and `x == NaN` is
    False for every x, so recomputing each row by re-filtering the frame on its
    own group key reports 0 labelled for that hop while the same row's total
    says 1 -- a table that disagrees with itself. Aggregated inside the groupby
    instead, which cannot.
    """
    report = stage0.build_report(
        _resolved_frame(
            _edge(child_type="D.FLOW", parent_type="D.FCS", internal_assay_id=11),
            _edge(child_type="D.FLOW", parent_type="D.FCS", internal_assay_id=None),
            _edge(child_type="D.FLOW", parent_type="D.FCS", internal_assay_id=12),
            _edge(child_type="MUS", parent_type=None, internal_assay_id=13),
        ),
        _residues(), _no_childof(),
    )
    assert _row(report, "D.FLOW -> D.FCS").endswith("| 3 | 2 |")
    assert _row(report, "MUS ->").endswith("| 1 | 1 |")
    # and the untyped endpoint is named as one, not printed as a float nan
    assert "MUS -> (none)" in report


def test_report_states_protocol_coverage_without_claiming_why_it_is_missing():
    """A null protocol_id pools a data defect with a genuine absence.

    resolve_properties swallows unparseable or non-object json_metadata into
    empty metadata, so `protocol_id.isna()` cannot distinguish "the child
    declares no Protocol" from "the child's metadata could not be read". With no
    samples frame to recount from, the report states the coverage figure and
    says which question it is not answering.
    """
    report = stage0.build_report(
        _resolved_frame(
            _edge(child_id=1, protocol_id=5),
            _edge(child_id=2, protocol_id=None),
            _edge(child_id=3, protocol_id=None),
        ),
        _residues(), _no_childof(),
    )
    assert "**1** of **3**" in _para(report, "carry a resolvable protocol id")
    pooled = _para(report, "samples frame was not supplied")
    assert "**2**" in pooled
    assert "did not parse as a JSON object" in pooled


def test_report_recounts_metadata_parse_failures_off_the_samples_frame():
    """Given `samples`, the four causes are separated by re-reading the metadata.

    The bucket that matters is the unreadable one: it is a data defect the
    operator can act on before the write, and it is invisible in `resolved`.
    A JSON document that parses to a list rather than an object belongs there
    too -- resolve_properties treats it as empty metadata exactly like a parse
    failure, and the server would have raised on it.
    """
    resolved = _resolved_frame(
        _edge(child_id=1, protocol_id=5),      # resolved, not in the breakdown
        _edge(child_id=2, protocol_id=None),   # no samples row
        _edge(child_id=3, protocol_id=None),   # empty metadata
        _edge(child_id=4, protocol_id=None),   # unparseable
        _edge(child_id=5, protocol_id=None),   # parses, but to a list
        _edge(child_id=6, protocol_id=None),   # readable, declares no Protocol
    )
    samples = pd.DataFrame(
        [
            (1, "C-260101ABC-1", '{"Protocol": "http://x/sops/5"}', None, "10"),
            (3, "C-260101ABC-3", "", None, "10"),
            (4, "C-260101ABC-4", "not json at all", None, "10"),
            (5, "C-260101ABC-5", '["Protocol"]', None, "10"),
            (6, "C-260101ABC-6", '{"Name": "x"}', None, "10"),
        ],
        columns=S.SAMPLE_COLUMNS,
    )
    report = stage0.build_report(resolved, _residues(), _no_childof(), samples)

    # needles anchored to the leading pipe: these causes are also named in the
    # prose beneath the table, and a bare phrase would match both
    assert "**1** of **6**" in _para(report, "carry a resolvable protocol id")
    assert _row(report, "| the child has no row in the samples").endswith("| 1 |")
    assert _row(report, "| the child's json_metadata is empty").endswith("| 1 |")
    assert _row(report, "| the child's json_metadata did not parse").endswith("| 2 |")
    assert _row(report, "| the child's metadata names no").endswith("| 1 |")


def test_full_protocol_coverage_prints_no_breakdown_to_read():
    """Complete coverage is the good outcome and needs no four-row table of zeros.

    Both explanatory branches are written for edges that are missing one, and
    printing either against nothing makes the gate longer without making it say
    more. The coverage figure itself is still stated.
    """
    report = stage0.build_report(
        _resolved_frame(_edge(protocol_id=5)), _residues(), _no_childof())
    assert "**1** of **1**" in _para(report, "carry a resolvable protocol id")
    assert "nothing to explain" in report
    assert "samples frame was not supplied" not in report
    assert "no row in the samples extract" not in report


def test_the_protocol_recount_is_not_fooled_by_reordered_sample_columns():
    """`samples` is unpacked positionally, as in resolve_properties.

    A producer emitting sample_id | json_metadata | uuid reads every uuid as the
    metadata blob; each one then fails to parse and the report announces a
    catastrophic parse failure that never happened. Compared against the
    correctly-ordered report, which the case above pins.
    """
    resolved = _resolved_frame(_edge(child_id=1, protocol_id=None))
    samples = pd.DataFrame(
        [(1, "C-260101ABC-1", '{"Name": "x"}', None, "10")],
        columns=S.SAMPLE_COLUMNS,
    )
    expected = stage0.build_report(resolved, _residues(), _no_childof(), samples)
    assert _row(expected, "| the child's metadata names no").endswith("| 1 |")

    swapped = samples[["sample_id", "json_metadata", "uuid",
                       "created_at", "project_ids"]]
    assert list(swapped.columns) != S.SAMPLE_COLUMNS
    assert stage0.build_report(resolved, _residues(), _no_childof(), swapped) == expected


def test_report_survives_the_steady_state_where_nothing_is_left_to_create():
    """The idempotent re-run still has to produce a receipt.

    Once stage 0 has applied, every reference is already an edge and the plan is
    empty -- and the report's percentages divide by the edge count.
    """
    fx = S.make_stage0_fixture()
    empty, _ = stage0.plan_edges(
        fx["parents"], fx["nodes"],
        pd.DataFrame(list(zip(fx["parents"]["child_uuid"], fx["parents"]["token"])),
                     columns=S.CHILDOF_COLUMNS))
    resolved = stage0.resolve_properties(
        empty, fx["samples"], fx["membership"], fx["assays"], fx["sops"])
    assert len(resolved) == 0, "non-vacuity: this is the empty-plan path"

    report = stage0.build_report(
        resolved, _residues({S.D_ALREADY_EXISTS: 6}), _no_childof())
    assert "0 edges to create" in report
    assert "0 labelled" in report and "0 dark" in report
    assert "**6**" in _row(report, "excluded, total")
