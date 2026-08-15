import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import precedent as P


def test_membership_index_groups_assays_by_sample():
    fx = S.make_fixture()
    idx = P.membership_index(fx["membership"])
    assert idx[100] == {1}
    assert idx[200] == {1, 2}
    assert 999 not in idx


def test_assay_index_resolves_to_the_internal_namespace():
    fx = S.make_fixture()
    idx = P.assay_index(fx["assays"])
    assert idx[1] == (10, 11, "Comet Chip")


def test_assay_index_falls_back_when_there_is_no_junction_row():
    # 17 assay records resolve to no internal_assay_id. They fall back to
    # (assay_id, title) -- the same rule neo4j_sync.py:1418-1431 (v4-stable-wt;
    # 944-957 in NExtSEEK/dev-v3-merge) uses -- so the RULE_KEY is never null.
    # A null would collapse all 17 into one rule.
    assays = pd.DataFrame(
        [(2, "Antibody Panel", 8, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    assert P.assay_index(assays)[2] == (10, 2, "Antibody Panel")


def test_comet_chip_hop_records_two_both_sides_and_one_child_only():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "D.IMG")
              & (out.internal_assay_title == "Comet Chip")].iloc[0]
    assert row.n_both == 2
    assert row.n_child_only == 1
    assert row.propagation_rate == pytest.approx(2 / 3)


def test_propagation_rate_is_zero_when_never_both_sides():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "TIS") & (out.parent_type == "MUS")].iloc[0]
    assert row.n_both == 0
    assert row.propagation_rate == 0.0


def test_output_columns_and_key_match_the_contract():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    assert list(out.columns) == S.PRECEDENT_COLUMNS
    assert not out.duplicated(subset=S.RULE_KEY).any()


def test_a_wholly_dark_edge_contributes_nothing():
    """Both endpoints unregistered -> no observation, in either direction.

    DEVIATION FROM THE TASK BRIEF, decided by the brief's own anchor figure.
    The brief asserted `out[out.child_type == "DNA"].empty`, on the reading
    that an edge with an unregistered ENDPOINT contributes nothing. Two
    DNA -> TIS edges exist in the fixture and they are not the same case:

      301 -> 400   neither endpoint registered. Contributes nothing, because
                   there is no assay to count into. That is this test.
      300 -> 200   child registered nowhere, parent registered in BOTH assays.
                   Contributes `n_parent_only` twice, which is a real
                   observation and exactly what `reverse_rate` measures: the
                   parent is in Comet Chip and the child is not.

    So `child_type == "DNA"` is not empty, and the brief's assertion fails
    against the brief's own implementation. Making it pass means dropping
    every edge with a dark endpoint, and the arbiter is the brief's stated
    anchor: measured on the real extract, keeping those edges yields **961
    rules**, which is the anchor; dropping them yields 919. The dropped
    reading also loses 12,007 `n_parent_only` observations (931,196 ->
    919,189) and 3,487 `n_child_only` (666,939 -> 663,452), which is
    precisely the evidence about the mode-1 population -- the population this
    layer exists to rule on. `n_both` is identical either way (361,420), so
    no propagation_rate anchor could have caught the difference; only the
    rule count did.
    """
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    dark = out[(out.child_type == "DNA") & (out.parent_type == "TIS")]
    # the 301 -> 400 edge is invisible; only 300 -> 200 is represented, and
    # only as a parent-side observation
    assert list(dark.n_both) == [0, 0]
    assert list(dark.n_child_only) == [0, 0]
    assert sorted(dark.n_parent_only) == [1, 1]


def test_reverse_rate_counts_the_other_direction():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "TIS")
              & (out.internal_assay_title == "Comet Chip")].iloc[0]
    assert row.n_parent_only == 1
    assert row.reverse_rate == 0.0


def test_nothing_is_dropped_by_a_null_key_component():
    """`internal_assay_id` is nullable AND a RULE_KEY component.

    A `groupby(S.RULE_KEY)` defaults to `dropna=True` and would discard every
    row keyed on a junction-less assay -- silently, with no error and a
    plausible-looking table. `mine_precedent` counts into a dict, so a None
    key is impossible by construction rather than by discipline; the fallback
    in `assay_index` is what keeps it out. This pins the composition of the
    two: a junction-less assay's observations survive into the output.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (481, "RNA Extraction", 9, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    edges = pd.DataFrame(
        [(100, 200, "D.IMG-1", "TIS-1", "D.IMG", "TIS", None, None, None)],
        columns=S.EDGE_COLUMNS,
    )
    membership = pd.DataFrame([(100, 481), (200, 481)],
                              columns=S.MEMBERSHIP_COLUMNS)
    out = P.mine_precedent(edges, membership, assays)
    assert len(out) == 1
    assert out.internal_assay_id.notna().all()
    assert out.iloc[0].internal_assay_id == 481
    assert out.iloc[0].internal_assay_title == "RNA Extraction"
    assert out.iloc[0].n_both == 1


EXTRACT = REPO / "assay-hygiene" / "extract"


def test_the_fallback_id_space_does_not_collide_with_the_internal_one():
    """The guard the fallback rests on, and it holds only by luck of numbering.

    A junction-less assay is keyed on its own seek `assays.id`, in a column
    whose every other value is a dmac `internal_assays.id`. The two id spaces
    are unrelated. Measured on this extract 2026-08-14: of the 458 seek
    assay_ids, 124 collide numerically with a genuine internal id and 122 of
    those 124 name a DIFFERENT assay -- seek 13 `Short Read Sequencing`
    against internal 13 `Cell Sorting`, seek 24 `Single Cell Clustering
    Analysis` against internal 24 `DNA Extraction`. Only 47 `Mass Spectrometry
    Analysis` and 74 `Tissue Collection` agree.

    Nothing is broken today only because the 17 junction-less assays sit at
    466-482 and the genuine internal ids run 1-188. One new junction-less
    assay with a low seek id merges two unrelated assays' precedent into a
    single rule, with no error and a table that still balances. This test is
    the only thing between that and a silent wrong answer, and it is not
    hypothetical: 473 of the 360,027 labelled edges already carry a seek id in
    `edge_internal_assay_id` because the server applies this same fallback.

    Asserted against the REAL extract, because the hazard is a property of
    production numbering and a fixture cannot exhibit it.
    """
    if not (EXTRACT / "assays.parquet").exists():
        pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")
    fallback = {int(a) for a, i in zip(assays.assay_id, assays.internal_assay_id)
                if pd.isna(i)}
    genuine = {int(i) for i in assays.internal_assay_id if pd.notna(i)}
    collision = sorted(fallback & genuine)
    assert not collision, (
        f"{len(collision)} junction-less assay(s) are keyed on a seek id that "
        f"is also a genuine internal_assays id: {collision}. Their precedent "
        "is now merged with an unrelated assay's. Fix the junction rows in "
        "dmac.assays_internal_assays, or give the fallback its own id space."
    )
    # and the reason it holds, stated so a future move of either range is
    # visible in the failure rather than only in the assertion above
    assert min(fallback) > max(genuine)
