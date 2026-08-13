import sys
from pathlib import Path

import pandas as pd

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


# The two cases below cover branches the frozen fixture cannot reach. Both were
# found by mutation-testing the five cases above: deleting either branch left
# all five green. They build their own frames rather than growing
# make_stage0_fixture(), whose rows are pinned by three later tasks.


def test_planner_collapses_a_pair_declared_under_two_fields():
    """One edge per (child, parent), no matter how many fields declare it.

    Also pins the docstring's accounting claim -- and its one exception. Every
    reference in the fixture is either planned or counted in a residue, so the
    two sides balance exactly. A *collapsed duplicate* is the sole reference
    that leaves no trace: it is dropped silently and counted in no residue, so
    the same sum comes up one short. If a residue for it is ever added, the
    second assertion goes red and must be updated deliberately.
    """
    fx = S.make_stage0_fixture()

    def drops(res):
        # every residue except prod_regex_would_reject, which is advisory and
        # overlaps the keepers rather than excluding anything
        return sum(v for k, v in res.items() if k != "prod_regex_would_reject")

    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert len(plan) + drops(residues) == len(fx["parents"])

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
    assert len(plan2) + drops(residues2) == len(dup) - 1


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
