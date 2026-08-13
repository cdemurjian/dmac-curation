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
