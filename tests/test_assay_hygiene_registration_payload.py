"""The payload a registration write actually sends, and the five ways it could destroy data.

WHY A SEPARATE MODULE FOR WHAT LOOKS LIKE A JOIN. Both candidate write
mechanisms are COMPLETE-LIST semantics, which is the dangerous kind: the
payload is not "add these", it is "this is now the entire membership", and
anything omitted from it is deleted. The NExtSEEK API's
`PATCH /nextseek_api/assays/{uid}/` is complete-list per ASSAY; the batch
upload sheet's `smart_merge_assay_assets` is complete-list per SAMPLE. So the
one payload that is correct under BOTH is `existing UNION additions`, and the
union is the entire safety argument. It is worth a module and a test file
because getting it wrong is not a bug that raises -- it is a silent deletion
that looks like a successful write.

THE MEASURED STAKES, against `assets/RUN1/`: the 26,188 resolved registration
rows touch 102 SEEK assays that between them already hold 202,016 memberships,
and 24,007 samples that already hold 25,912. Every one of those is resent in
the payload and would be destroyed by an omission. The largest single assay
payload is 48,951 references, of which 48,440 are pre-existing and none are
this project's to lose.

THE PROPERTY THAT IS NOT ABOUT THE UNION. `test_an_assay_no_row_targets_is_not
_in_the_payload` is the blast-radius containment guard. A payload that included
untouched assays would still be arithmetically correct -- existing UNION
nothing is existing -- and would still rewrite the complete membership of
records this project has no ruling for. The 102 must stay 102.

NO REAL IDENTIFIERS APPEAR HERE. Every fixture below is synthetic integers as
strings. The real registration set carries sample uids and this repository is
PUBLIC; see the header of `tests/test_assay_hygiene_rulings.py`.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import registration_payload as P  # noqa: E402


# --- fixtures ----------------------------------------------------------------
# assay 10 holds samples 1 and 2 and is targeted by NOTHING -- it is the
# containment control. assay 20 holds sample 3 and gains sample 1. assay 30
# holds nobody and gains sample 2, the empty-existing case.


@pytest.fixture
def membership():
    return pd.DataFrame(
        [("1", "10"), ("2", "10"), ("3", "20")],
        columns=["sample_id", "assay_id"])


@pytest.fixture
def registration():
    return pd.DataFrame([
        {"sample_id": "1", "write_target_seek_assay_id": "20"},
        {"sample_id": "2", "write_target_seek_assay_id": "30"},
        {"sample_id": "9", "write_target_seek_assay_id": ""},
    ])


def _pairs(frame, left, right):
    return set(zip(frame[left], frame[right]))


# --- the union, from both ends -----------------------------------------------


def test_every_existing_member_of_a_touched_assay_survives_the_payload(
        registration, membership):
    """The data-loss guard. Sample 3 has no ruling and must not be dropped.

    Under complete-list-per-assay, assay 20's payload IS its new membership.
    Sample 3 is in it today and nothing in the registration set mentions it, so
    a payload built from additions alone would delete it.
    """
    out = P.build_payloads(registration, membership)
    assert ("20", "3") in _pairs(out.per_assay, "assay_id", "sample_id")


def test_every_approved_addition_is_in_the_payload(registration, membership):
    out = P.build_payloads(registration, membership)
    got = _pairs(out.per_assay, "assay_id", "sample_id")
    assert ("20", "1") in got
    assert ("30", "2") in got


def test_the_payload_contains_nothing_that_is_not_existing_or_approved(
        registration, membership):
    """No invented memberships. The union is exact, not approximate."""
    out = P.build_payloads(registration, membership)
    assert _pairs(out.per_assay, "assay_id", "sample_id") == {
        ("20", "3"), ("20", "1"), ("30", "2")}


def test_an_assay_no_row_targets_is_not_in_the_payload(
        registration, membership):
    """Blast-radius containment. Assay 10 has no ruling; do not rewrite it."""
    out = P.build_payloads(registration, membership)
    assert "10" not in set(out.per_assay.assay_id)


def test_every_existing_assay_of_a_touched_sample_survives_the_payload(
        registration, membership):
    """The same guard from the other end, for the batch-upload mechanism.

    Sample 1 is in assay 10 today and gains assay 20. Under complete-list-per-
    sample its payload IS its new assay list, so omitting 10 unregisters it.
    """
    out = P.build_payloads(registration, membership)
    assert _pairs(out.per_sample, "sample_id", "assay_id") >= {
        ("1", "10"), ("1", "20")}


def test_a_sample_no_row_targets_is_not_in_the_payload(
        registration, membership):
    """Sample 3 gains nothing, so its assay list must not be rewritten."""
    out = P.build_payloads(registration, membership)
    assert "3" not in set(out.per_sample.sample_id)


# --- the rows that cannot be written -----------------------------------------


def test_a_row_with_no_resolvable_target_is_excluded_not_guessed(
        registration, membership):
    out = P.build_payloads(registration, membership)
    assert "9" not in set(out.per_sample.sample_id)


def test_a_row_with_no_resolvable_target_is_reported_rather_than_dropped(
        registration, membership):
    """Silence here is the failure mode: 5 real rows are in this state."""
    out = P.build_payloads(registration, membership)
    assert list(out.excluded.sample_id) == ["9"]


# --- idempotence -------------------------------------------------------------


def test_the_same_pair_ruled_twice_appears_once_in_the_payload(membership):
    """26,193 rows collapse to 26,188 pairs; two rulings are not two writes."""
    twice = pd.DataFrame([
        {"sample_id": "1", "write_target_seek_assay_id": "20"},
        {"sample_id": "1", "write_target_seek_assay_id": "20"},
    ])
    out = P.build_payloads(twice, membership)
    assert len(out.per_assay[(out.per_assay.assay_id == "20")
                             & (out.per_assay.sample_id == "1")]) == 1


def test_registering_a_pair_that_already_exists_is_a_no_op(membership):
    """Re-ruling an existing membership must not duplicate it."""
    already = pd.DataFrame(
        [{"sample_id": "3", "write_target_seek_assay_id": "20"}])
    out = P.build_payloads(already, membership)
    assert _pairs(out.per_assay, "assay_id", "sample_id") == {("20", "3")}


# --- the reconciliation that makes the rest non-vacuous ----------------------


def test_a_payload_that_would_drop_an_existing_member_raises(
        registration, membership):
    """The invariant is checked, not merely intended.

    Every assertion above is a statement about one hand-built fixture. This is
    the one that fires on data the fixtures do not describe: if the union is
    ever built in a way that loses a pre-existing member, the builder must
    refuse rather than return a payload that silently deletes.
    """
    with pytest.raises(ValueError, match="existing"):
        P.assert_no_membership_lost(
            per_assay=pd.DataFrame(
                [("20", "1")], columns=["assay_id", "sample_id"]),
            membership=membership,
            touched_assays={"20"})
