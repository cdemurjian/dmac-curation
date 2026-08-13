import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S


def _registration(fx):
    """sample_id -> set of assay_ids it is registered in, derived from membership.

    The structural assertions below are computed through this helper rather than
    written against literal ids, so they describe the fixture's shape instead of
    restating its rows.
    """
    reg = {}
    for sid, aid in zip(fx["membership"]["sample_id"], fx["membership"]["assay_id"]):
        reg.setdefault(sid, set()).add(aid)
    return reg


def _edge_registration(fx):
    """One (child_assays, parent_assays) pair per edge, in edge order."""
    reg = _registration(fx)
    return [(reg.get(c, set()), reg.get(p, set()))
            for c, p in zip(fx["edges"]["child_id"], fx["edges"]["parent_id"])]


def test_verdict_constants_are_distinct():
    verdicts = [S.V_CLEAN, S.V_MODE1_CHILD, S.V_MODE1_PARENT,
                S.V_MODE1_BOTH_DARK, S.V_MODE2_PROPAGATE,
                S.V_MODE2_AMBIGUOUS, S.V_MODE3_FLAG]
    assert len(set(verdicts)) == len(verdicts)


def test_rule_key_is_internal_assay_id():
    # 458 assay records collapse to 137 curated internal assays via
    # dmac.assays_internal_assays. assays.id is too fine (the same logical
    # assay is instantiated per study); assays.title is a different namespace
    # from DERIVED_FROM.internal_assay_title, so findings and edges would not
    # reconcile.
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type", "internal_assay_id"]
    assert "assay_title" not in S.RULE_KEY


def test_precedent_carries_internal_assay_title_for_display():
    assert "internal_assay_title" in S.PRECEDENT_COLUMNS


def test_precedent_columns_carry_both_directions():
    for col in ("n_both", "n_child_only", "n_parent_only",
                "propagation_rate", "reverse_rate"):
        assert col in S.PRECEDENT_COLUMNS


def test_fixture_shapes_match_declared_columns():
    fx = S.make_fixture()
    assert list(fx["edges"].columns) == S.EDGE_COLUMNS
    assert list(fx["membership"].columns) == S.MEMBERSHIP_COLUMNS
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS


def test_finding_columns_end_with_candidates():
    # `candidates` carries every assay title the child belongs to. Stage D's
    # tiebreak reads it and membership is NOT carried into findings, so if this
    # column is dropped or reordered off the end the tiebreak silently never
    # fires -- which looks exactly like a tiebreak that is working.
    assert "candidates" in S.FINDING_COLUMNS
    assert S.FINDING_COLUMNS[-1] == "candidates"


def test_fixture_encodes_the_four_canonical_situations():
    fx = S.make_fixture()
    # 1 propagating hop, 1 non-propagating hop, 1 dark child, 1 dark pair
    assert len(fx["edges"]) == 6
    assert set(fx["assays"]["title"]) == {"Comet Chip", "Tissue Collection"}

    # The four situations, derived from the frames rather than asserted by id.
    pairs = _edge_registration(fx)
    co_registered = [1 for c, p in pairs if c & p]
    disjoint_but_registered = [1 for c, p in pairs if c and p and not (c & p)]
    dark_child = [1 for c, _ in pairs if not c]
    both_dark = [1 for c, p in pairs if not c and not p]

    assert len(co_registered) == 2           # the precedent-establishing hops
    assert len(disjoint_but_registered) == 2  # mode-2 candidate + the CLEAN hop
    assert len(dark_child) == 2               # mode-1 child + the both-dark pair
    assert len(both_dark) == 1

    # Type columns are part of the frozen contract: the rule key is
    # (project, child_type, parent_type, internal_assay_id), so a changed type
    # silently re-buckets precedent. Count the hops rather than collecting the distinct
    # set -- a set still matches after a type is flipped to one that already
    # appears on another edge, which is exactly the silent edit to catch.
    hops = Counter(zip(fx["edges"]["child_type"], fx["edges"]["parent_type"]))
    assert dict(hops) == {("D.IMG", "TIS"): 3, ("DNA", "TIS"): 2, ("TIS", "MUS"): 1}


def test_comet_chip_hop_carries_the_frozen_propagation_counts():
    # Later stages hand-trace n_both=2 / n_child_only=1 -> propagation_rate 2/3
    # off these exact rows. Pin the counts here so an edit to a membership row
    # fails at its source instead of as mysterious arithmetic three tasks later.
    fx = S.make_fixture()
    reg = _registration(fx)
    assays = fx["assays"]
    comet = assays.loc[assays["title"] == "Comet Chip", "assay_id"].iloc[0]
    edges = fx["edges"]
    hop = edges[(edges["child_type"] == "D.IMG") & (edges["parent_type"] == "TIS")]

    n_both = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                 if comet in reg.get(c, set()) and comet in reg.get(p, set()))
    n_child_only = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                       if comet in reg.get(c, set()) and comet not in reg.get(p, set()))

    assert (n_both, n_child_only) == (2, 1)


def test_fixture_cannot_reach_ambiguity_or_a_dark_parent():
    """Pins the branches make_fixture's docstring says it does NOT reach.

    Executable so the frozen data and that docstring cannot drift apart. If one
    of these ever starts failing, the fixture gained a branch and the docstring
    is now lying -- update both together.
    """
    fx = S.make_fixture()
    reg = _registration(fx)
    edges = fx["edges"]

    # No child sits in 2+ assays, so `candidates` is single-element on every
    # row and no stage-D tiebreak can fire against this fixture.
    assert not [c for c in edges["child_id"] if len(reg.get(c, set())) > 1]

    # No edge pairs a registered child with a wholly dark parent (MODE_1_PARENT).
    assert not [(c, p) for c, p in zip(edges["child_id"], edges["parent_id"])
                if reg.get(c) and not reg.get(p)]


def test_prod_uid_regex_rejects_the_two_letter_antibody_type():
    # This is the production defect stage 0 works around. If this test ever
    # goes green-by-passing, production has been fixed and the override can go.
    assert S.UID_RE_PROD.match("AB-250723FOR-3") is None
    assert S.UID_RE_FIXED.match("AB-250723FOR-3") is not None


def test_both_regexes_agree_on_three_letter_types():
    for uid in ("TIS-260107SES-1", "D.ADNKA-250917FOR-98", "MUS-220122SAS-125"):
        assert S.UID_RE_PROD.match(uid) is not None
        assert S.UID_RE_FIXED.match(uid) is not None


def test_edge_row_columns_mirror_the_server_model():
    # nextseek_api/batch_upload/models.py:457 DerivedFromRelRow, extra="forbid".
    # A column stage 0 invents here is a field bulk_merge_relationships rejects.
    assert S.EDGE_ROW_COLUMNS == [
        "child_id", "child_uuid", "parent_id", "parent_uuid",
        "protocol_id", "protocol_title", "assay_id",
        "internal_assay_id", "internal_assay_title",
    ]


def test_drop_reasons_are_distinct():
    reasons = [S.D_NOT_UID, S.D_NO_NODE, S.D_SELF_LOOP, S.D_ALREADY_EXISTS]
    assert len(set(reasons)) == len(reasons)


def test_original_fixture_still_matches_the_widened_assay_contract():
    # ASSAY_COLUMNS grew by two; make_fixture() builds against that constant and
    # would raise if its rows were not widened to match.
    fx = S.make_fixture()
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS
    assert fx["assays"].iloc[0]["internal_assay_id"] == 11


def test_frozen_fixture_arithmetic_is_unaffected_by_the_new_column():
    # The companion plan hand-traces n_both=2 / n_child_only=1 off these rows.
    # Adding a column to `assays` must not disturb edges or membership.
    fx = S.make_fixture()
    assert len(fx["edges"]) == 6
    assert len(fx["membership"]) == 10


def test_stage0_fixture_covers_every_drop_reason_and_one_keeper():
    fx = S.make_stage0_fixture()
    parents = fx["parents"]
    # one token per drop reason, plus two that survive to be created
    assert len(parents) == 6
    # Pinned as a LIST, like `nodes` two cases below. stage0.plan_edges unpacks
    # this frame positionally, so order is part of the contract: a producer
    # emitting child_uuid | token | field swaps two fields and every reference
    # then fails UID validation -- an empty plan with a full not_a_uid count,
    # which is a silent wrong answer rather than a crash.
    assert list(parents.columns) == S.PARENT_COLUMNS
    # exactly one token is AB-*, valid only under the corrected regex
    ab = [t for t in parents["token"] if t.startswith("AB-")]
    assert len(ab) == 1
    assert S.UID_RE_PROD.match(ab[0]) is None

    # Every drop reason must be REACHABLE. Tasks 2-6 hand-trace their drop
    # accounting off this one fixture, so each branch is derived from the frames
    # rather than restated as a literal row: retyping the free text as a UID or
    # deleting the single `existing` row would otherwise remove a branch with
    # all of these tests still green.
    nodes = set(fx["nodes"]["uuid"])
    pairs = list(zip(parents["child_uuid"], parents["token"]))
    not_uid = [(c, t) for c, t in pairs if not S.UID_RE_FIXED.match(t)]
    no_node = [(c, t) for c, t in pairs if S.UID_RE_FIXED.match(t) and t not in nodes]
    self_loop = [(c, t) for c, t in pairs if c == t]
    already = set(zip(fx["existing"]["child_uuid"], fx["existing"]["parent_uuid"]))

    assert len(not_uid) == 1                       # D_NOT_UID
    assert len(no_node) == 1                       # D_NO_NODE
    assert len(self_loop) == 1                     # D_SELF_LOOP
    # a pre-existing edge only causes a drop if some parent row DECLARES it
    assert len(already) == 1 and already <= set(pairs)   # D_ALREADY_EXISTS

    # the four reasons must land on four distinct rows, or one of them is
    # shadowed by another and the branch it names is never exercised
    dropped = set(not_uid) | set(no_node) | set(self_loop) | already
    assert len(dropped) == 4

    # ...leaving exactly two keepers, both of which must resolve in the node
    # index. Drop the AB node and the AB keeper silently becomes a D_NO_NODE.
    keepers = [(c, t) for c, t in pairs if (c, t) not in dropped]
    assert len(keepers) == 2
    assert {t for _, t in keepers} <= nodes


def test_stage0_nodes_frame_matches_the_declared_node_index_contract():
    # `nodes` supplies every child_id / parent_id that reaches the graph, so it
    # needs a contract its producer and consumer can both assert against.
    # Pinned against a literal first: the fixture builds its frame FROM this
    # constant, so asserting only frame-vs-constant is vacuous and stays green
    # through any reordering of the constant itself.
    assert S.NODES_COLUMNS == ["uuid", "sample_id", "type"]
    assert list(S.make_stage0_fixture()["nodes"].columns) == S.NODES_COLUMNS
