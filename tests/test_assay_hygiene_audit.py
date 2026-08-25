import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import audit as A


def _assays():
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection")],
        columns=S.ASSAY_COLUMNS,
    )


def _assays_with_a_junction_less_row():
    """assay 2 has no junction row, so it falls back to its own (id, title).

    Its resolved id is then 2 -- a seek assays.id, in a namespace no claim ever
    speaks -- which is what makes a sample registered in it unmappable rather
    than known-different.
    """
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )


def _nodes(rows):
    return pd.DataFrame(rows, columns=S.NODES_COLUMNS)


def _claims(rows):
    return pd.DataFrame(rows, columns=S.CLAIM_COLUMNS)


def test_registered_internal_maps_through_the_junction():
    membership = pd.DataFrame([(100, 1), (100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    assert A.registered_internal(membership, _assays())[100] == {11, 12}


def test_a_claim_matching_the_registration_is_not_flagged():
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([(100, 1)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_claim_contradicting_the_registration_is_flagged():
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    out = A.audit_contradictions(claims, membership, _assays(), nodes)
    assert list(out.columns) == S.AUDIT_COLUMNS
    row = out.iloc[0]
    assert row.verdict == S.V_MODE3_FLAG
    assert row.claimed_internal_assay_id == 11
    assert "12" in str(row.registered_internal_assay_ids)
    assert row.sample_type == "D.IMG"


def test_an_unregistered_sample_is_not_a_contradiction():
    # A sample in no assay is Mode 1's problem, not Mode 3's. Mode 3 needs
    # something to contradict.
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_weak_claim_does_not_raise_a_flag_by_default():
    # Weak claims are 90.4% accurate, so flagging on them would put a ~10%
    # false-positive rate in front of a curator.
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_WEAK, "Protocol", "x", False, S.P_LEARNED)])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_contested_claim_does_not_raise_a_flag_by_default():
    # A contested sample's evidence disagrees with itself, so it has not decided
    # what it asserts. Excluded by a SEPARATE parameter rather than by tier: on
    # the disagreement subset the winning claim's mapping is still wrong about
    # 30% of the time, three times the rate the weak floor already refuses.
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", True, S.P_LEARNED)])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_contested_claims_can_be_admitted_deliberately():
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", True, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership, _assays(), nodes,
                                 include_contested=True)
    assert len(out) == 1


def test_adding_a_claim_never_removes_an_existing_flag():
    """The monotonicity property the per-claim design exists to guarantee.

    Under the previous per-sample tiering, a second claim collapsed the sample
    to T_CONFLICT and its flag vanished: measured at 102 suppressed against 13
    added over the real extract. Adding a row must only ever add flags.

    Asserted as SET INCLUSION on the flag identity, not as `len(after) >=
    len(before)`. The brief's count comparison is satisfied by an
    implementation that deletes one flag and invents two, which is precisely
    the failure being guarded -- the defect was 102 deletions alongside 13
    additions, and a count test reads that as -89 only because the numbers
    happen to fall that way. The `before` frame is pinned non-empty first, or
    every assertion below is vacuously true against an implementation that
    flags nothing at all.
    """
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    one = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    before = A.audit_contradictions(one, membership, _assays(), nodes)
    two = _claims([
        (100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
        (100, "D.IMG-1", 13, "Other", S.T_WEAK, "Protocol", "y", False, S.P_PROPOSED),
    ])
    after = A.audit_contradictions(two, membership, _assays(), nodes)

    assert len(before) == 1, "non-vacuity: there must be a flag to suppress"
    assert len(after) >= len(before)
    flags_before = set(zip(before.sample_id, before.claimed_internal_assay_id))
    flags_after = set(zip(after.sample_id, after.claimed_internal_assay_id))
    assert flags_before <= flags_after, (
        f"a claim was added and the flag {flags_before - flags_after} "
        "disappeared; this is the non-monotone defect"
    )


def test_the_tier_floor_can_be_widened_deliberately():
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_WEAK, "Protocol", "x", False, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership, _assays(), nodes,
                                 tiers=(S.T_CORROBORATED, S.T_STRONG, S.T_WEAK))
    assert len(out) == 1


def test_a_registration_in_an_unknown_assay_is_not_dropped_silently():
    """A membership row naming an assay absent from the assays frame RAISES.

    This is the third consumer of the `assay_index` funnel to be hardened the
    same way (mine_precedent, vocabulary_evidence.registered_assays), and here
    the silent skip is the most damaging of the three. Dropping a registration
    SHRINKS the set a claim is compared against, so a claim that agrees with
    the dropped registration is promoted into a MODE_3_FLAG -- the audit
    accuses a curator of a contradiction using a registration it threw away
    itself. The other direction is a miss: drop every registration a sample has
    and it looks unregistered, so its real contradiction is never reported.

    Neither shows up as an error, a warning or a row-count anomaly, which is
    what the spec's "nothing is dropped silently" constraint forbids. 0 of the
    173 membership assay_ids on the real extract hit this today.
    """
    membership = pd.DataFrame([(100, 1), (100, 77)], columns=S.MEMBERSHIP_COLUMNS)
    with pytest.raises(ValueError, match="77"):
        A.registered_internal(membership, _assays())


def test_the_flagged_row_reports_the_type_of_its_own_node():
    """sample_type is resolved through uuid, because sample_id is not unique.

    Measured on the real extract 2026-08-14: 86 sample_ids carry TWO node rows
    under two different uuids, 51 of those pairs disagree on type (a MUS node
    and an RNA node sharing one sample_id, e.g. 165987 = MUS-250620SAR-2 and
    RNA-250620SAR-2), and 85 claim rows land on such a sample_id. Keyed on
    sample_id, 7 of those claims report the OTHER node's type -- and which one
    wins is whichever row sits later in nodes.parquet, whose order
    test_assay_hygiene_stage0.py already records as unstable across extracts.
    uuid is unique in that frame (0 duplicates over 177,392 rows) and every one
    of the 130,764 claims carries one that resolves, so it is both the correct
    key and an available one.
    """
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    # Two nodes, one sample_id, different types. The contradicting claim names
    # the FIRST; a sample_id-keyed dict would report the second.
    nodes = _nodes([("MUS-1", 100, "MUS"), ("RNA-1", 100, "RNA")])
    claims = _claims([(100, "MUS-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership, _assays(), nodes)
    assert out.iloc[0].sample_type == "MUS"


def test_a_registration_in_an_unmappable_id_space_is_not_a_contradiction():
    """A junction-less registration cannot establish a contradiction.

    The sample is registered in fallback id 2, a seek assays.id. The claim
    names internal id 11. They cannot be equal -- they are different namespaces
    -- so the comparison reads as disagreement no matter what the registration
    actually is. `assay_index`'s collision guard makes a false AGREEMENT
    impossible but says nothing about this, the false CONTRADICTION.

    Excluded by ID SPACE and not by title: the two titles here differ ("Comet
    Chip" against "Tissue Collection"), so a title-equality rule would let this
    row through. That is not hypothetical -- on the real extract 14 flags carry
    a fallback id and only 13 have a matching title, and the 14th (sample
    244038, registered 466;467, claiming 24 DNA Extraction) is precisely this
    shape.
    """
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    assays = _assays_with_a_junction_less_row()

    assert A.audit_contradictions(claims, membership, assays, nodes).empty
    # The identical world with the junction row present DOES flag, or the case
    # above proves only that something else swallowed the row.
    assert len(A.audit_contradictions(claims, membership, _assays(), nodes)) == 1


def test_unmappable_registrations_can_be_admitted_deliberately():
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership,
                                 _assays_with_a_junction_less_row(), nodes,
                                 include_unmappable=True)
    assert len(out) == 1


def test_one_mappable_registration_does_not_rescue_an_unmappable_one():
    """The exclusion is on ANY unmappable id in the set, not on all of them.

    A sample registered in both a mappable and a junction-less assay still has
    a registration whose identity is unknown, and that unknown one could be the
    assay the claim names. Recovering it could only ADD to the compared set,
    and adding can only ever REMOVE a flag.
    """
    membership = pd.DataFrame([(100, 1), (100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    # claims internal 13: registered in neither 11 (mappable) nor 2 (fallback)
    claims = _claims([(100, "D.IMG-1", 13, "Other", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    assays = _assays_with_a_junction_less_row()

    assert A.audit_contradictions(claims, membership, assays, nodes).empty
    assert len(A.audit_contradictions(claims, membership, assays, nodes,
                                      include_unmappable=True)) == 1


def test_the_registered_titles_align_positionally_with_the_registered_ids():
    """Index i of the id column names index i of the title column.

    The two columns are one fact split in half, and a reader judging a flag
    reads across them. Built independently they could drift into a row that
    decodes to the wrong assay, which is worse than the bare id column this
    replaced: a wrong title is confidently wrong, a missing one is only
    unhelpful. Both are built from one sorted list off `assay_index`, the same
    funnel the ids came from.

    The titles here are deliberately ANTI-alphabetical against their ids (11
    Zebrafish, 12 Alpha), so an implementation that collects or sorts the
    titles independently of the ids emits a different string and fails. Under
    the shared fixture's "Comet Chip" / "Tissue Collection" the id order and
    the alphabetical order coincide, so this case would pass against a
    decoupled implementation -- it would certify the alignment in its own title
    without testing it, which is the failure mode this file has already had to
    correct once.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Zebrafish Imaging"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Alpha Screening")],
        columns=S.ASSAY_COLUMNS,
    )
    membership = pd.DataFrame(
        [(100, 1), (100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 13, "Other", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    row = A.audit_contradictions(claims, membership, assays, nodes).iloc[0]

    ids = row.registered_internal_assay_ids.split(";")
    names = row.registered_internal_assay_titles.split(";")
    assert ids == ["11", "12"]
    assert len(ids) == len(names)
    assert names == ["Zebrafish Imaging", "Alpha Screening"]
    assert dict(zip(ids, names)) == {"11": "Zebrafish Imaging",
                                     "12": "Alpha Screening"}


def test_row_order_does_not_depend_on_the_order_claims_arrive_in():
    """The flag list is an artifact a curator diffs between runs.

    `claims` arrives in the order `sample_claims` walked the metadata dict,
    which is the order samples sit in samples.parquet -- and the extractor's
    row order is not stable across extracts (see
    test_assay_hygiene_stage0.py). Emitting flags in arrival order means a
    re-extract reorders the csv with no change in content, and a curator
    reading a diff cannot tell that apart from a new flag. Same reasoning, and
    the same fix, as precedent.mine_precedent's RULE_KEY tiebreak.

    Asserts BOTH halves: that the order is reproducible under a permutation,
    and that the specific answer is ascending (sample_id,
    claimed_internal_assay_id) -- so a merely-deterministic order (arrival,
    reversed, by title) still fails this.
    """
    membership = pd.DataFrame(
        [(100, 2), (101, 2), (102, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG"), ("D.IMG-2", 101, "D.IMG"),
                    ("D.IMG-3", 102, "D.IMG")])
    rows = [
        (102, "D.IMG-3", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
        (100, "D.IMG-1", 13, "Other", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
        (100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
        (101, "D.IMG-2", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
    ]
    forward = A.audit_contradictions(_claims(rows), membership, _assays(), nodes)
    reverse = A.audit_contradictions(_claims(rows[::-1]), membership, _assays(), nodes)

    assert len(forward) == 4, "non-vacuity: every row must reach the output"
    assert forward.equals(reverse)
    assert list(zip(forward.sample_id, forward.claimed_internal_assay_id)) == [
        (100, 11), (100, 13), (101, 11), (102, 11)]
