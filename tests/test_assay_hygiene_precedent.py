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


def test_fallback_assay_ids_names_the_ids_assay_index_invents():
    """The two agree by construction, not by both being maintained.

    `fallback_assay_ids` is the one definition of "this record has no junction
    row" and `assay_index` consumes it, so the set returned here is exactly the
    set of resolved ids living in the seek namespace rather than the dmac one.
    Mode 3 needs that distinction separately: an id in one namespace can never
    equal an id in the other, so it always reads as a contradiction (see
    audit.audit_contradictions).

    Asserted against `assay_index`'s own output rather than a hand-written set,
    so the two cannot drift apart.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Antibody Panel", 8, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    fallback = P.fallback_assay_ids(assays)
    assert fallback == {2}

    resolved = {aid: info[1] for aid, info in P.assay_index(assays).items()}
    # a fallback record resolves to its OWN assay_id; a genuine one does not
    assert {aid for aid, iaid in resolved.items() if aid == iaid} == fallback
    # a fully-junctioned frame has none, which is the state the guard's
    # remediation message tells an operator to reach
    assert P.fallback_assay_ids(S.make_fixture()["assays"]) == set()


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


def _tied_world(n=12):
    """n rules that tie exactly on (n_both, n_child_only), keyed in reverse.

    Every edge is the same D.IMG -> TIS hop in project 10, and each of the n
    sample pairs is co-registered in one assay of its own, so every rule comes
    out at n_both=1, n_child_only=0 and the RULE_KEY is the only thing telling
    them apart. Assay k carries internal id n-k, so insertion order (the order
    the edges arrive in) is the exact REVERSE of RULE_KEY order. Without a
    tiebreak the output is one or the other depending on nothing but arrival.
    """
    assays = pd.DataFrame(
        [(k, f"Assay {k}", 7, 3, 2, 10, "MIT_SRP", n - k, f"Internal {n - k}")
         for k in range(n)],
        columns=S.ASSAY_COLUMNS,
    )
    edges = pd.DataFrame(
        [(100 + k, 200 + k, f"D.IMG-{k}", f"TIS-{k}", "D.IMG", "TIS",
          None, None, None) for k in range(n)],
        columns=S.EDGE_COLUMNS,
    )
    membership = pd.DataFrame(
        [(100 + k, k) for k in range(n)] + [(200 + k, k) for k in range(n)],
        columns=S.MEMBERSHIP_COLUMNS,
    )
    return edges, membership, assays


def test_row_order_does_not_depend_on_the_order_edges_arrive_in():
    """The output is an artifact a curator DIFFS between extracts.

    Sorting on `["n_both", "n_child_only"]` alone leaves 708 of the 961 real
    rules tied, 440 of them at (0, 0). That sort is not unstable -- pandas
    routes a multi-column `sort_values` through `np.lexsort` and ignores
    `kind` -- so it is reproducible for a GIVEN input order, and the exposure
    is the input order itself: tied rows come out in `counts` insertion order,
    which is the order rows sit in edges.parquet.
    `test_assay_hygiene_stage0.py` already records that "the extractor's row
    order is not stable across extracts". Measured on the real extract,
    permuting the edge frame changes the two-column output and leaves the
    full-key output byte-identical, so a curator would read the difference as
    change. The COUNT of rows that move is a property of the permutation
    rather than of the code -- 615 at `random_state=7`, and 631 / 635 / 621 at
    seeds 0 / 1 / 42 -- so it is quoted with its seed or not at all. The
    seed-free figure is the two sorts against each other on the SAME
    as-extracted input: 647 of the 961 rows land at a different index.

    Both halves are asserted. Reproducibility alone is not the property --
    vocabulary_evidence's docstring makes the same point -- so the second
    assertion pins the specific answer, ascending RULE_KEY, and would catch a
    tiebreak that was merely deterministic (e.g. descending, or on the title).
    """
    edges, membership, assays = _tied_world()
    forward = P.mine_precedent(edges, membership, assays)
    reverse = P.mine_precedent(edges.iloc[::-1], membership, assays)
    # every rule really is tied, or this case proves nothing
    assert set(forward.n_both) == {1} and set(forward.n_child_only) == {0}
    assert len(forward) == 12
    assert forward.equals(reverse)
    assert list(forward.internal_assay_id) == sorted(forward.internal_assay_id)


def test_assay_index_rejects_a_fallback_id_that_is_also_an_internal_id():
    """The collision invariant, enforced where an operator's real run hits it.

    This is the same property as the extract-backed case at the bottom of this
    file, checked in the single funnel every consumer passes through
    (`vocabulary_evidence.py:58` imports `assay_index` for exactly this
    reason). That case can only run beside a 17 MB gitignored extract, so on a
    fresh clone or in CI it skips and the invariant goes unchecked; this one
    always runs, and more importantly it fires during a real `main()` rather
    than only under pytest.

    Assay 11 has no junction row, so it falls back to seek id 11 -- which is
    also assay 1's genuine internal id. Both sit in project 10, so RULE_KEY
    cannot separate them and their precedent would silently merge.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (11, "Library Prep", 9, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    with pytest.raises(ValueError, match=r"junction-less assay.*\[11\]"):
        P.assay_index(assays)


def test_an_empty_fallback_set_is_not_a_collision():
    """The fully-repaired state passes rather than crashing.

    Every assay has a junction row, so there is no fallback id at all. The
    check is a set intersection precisely so this case is falsy; a range
    comparison would raise on the empty sequence and fail the one state the
    error message tells the operator to reach.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Library Prep", 9, 3, 2, 10, "MIT_SRP", 1, "Library Prep")],
        columns=S.ASSAY_COLUMNS,
    )
    # internal id 1 equals assay_id 1, which is only a collision if assay 1
    # were ALSO falling back. It is not, so this must pass.
    assert P.assay_index(assays)[2] == (10, 1, "Library Prep")


def test_a_registration_in_an_unknown_assay_is_not_dropped_silently():
    """The module's one silent drop, removed.

    A membership row naming an assay absent from the assays frame used to hit
    a `continue`, so the registration vanished from every rate with no signal
    -- against the spec's binding "nothing is dropped silently". 0 of the 173
    membership assay_ids hit this on the real extract, so it is dead defence
    today; it raises rather than skipping so that an extract where the two
    frames disagree is diagnosed instead of quietly under-counted.
    """
    assays = pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip")],
        columns=S.ASSAY_COLUMNS,
    )
    edges = pd.DataFrame(
        [(100, 200, "D.IMG-1", "TIS-1", "D.IMG", "TIS", None, None, None)],
        columns=S.EDGE_COLUMNS,
    )
    membership = pd.DataFrame([(100, 1), (200, 1), (999, 7)],
                              columns=S.MEMBERSHIP_COLUMNS)
    with pytest.raises(ValueError, match=r"absent from the assays frame: \[7\]"):
        P.mine_precedent(edges, membership, assays)


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
    assay with a low seek id merges two unrelated assays' precedent, with no
    error and a table that still balances. `RULE_KEY` carries `project_id`, so
    that merge happens only where both assays occur in the SAME project --
    which is not a mitigation worth relying on: measured on this extract, 12
    (junction-less, genuine) id pairs already share at least one project/hop,
    across 4 distinct junction-less assays. Nor is the fallback itself
    hypothetical: 473 of the 360,027 labelled edges already carry a seek id in
    `edge_internal_assay_id` because the server applies this same rule.

    This case asserts against the REAL extract, because only production
    numbering can show that the LIVE data satisfies the invariant. The
    invariant itself is enforced in `assay_index`, which raises, so an
    operator's real run fails loudly without needing a 17 MB gitignored file
    next to it. Both are needed: this one would skip on every fresh clone.
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
        f"is also a genuine internal_assays id: {collision}. Within a project "
        "their precedent is now merged. Fix the junction rows in "
        "dmac.assays_internal_assays, or give the fallback its own id space."
    )
    # The reason it holds, stated so a future move of EITHER range shows up
    # here rather than only as a mysterious intersection above.
    #
    # `if fallback` is load-bearing, not defensive noise. Fixing the junction
    # rows -- the exact remediation the assertion above prints -- empties
    # `fallback`, and a bare `min()` would then die with "min() iterable
    # argument is empty" and report a FAILURE for the fully-repaired state.
    # A guard that breaks when you follow its own advice trains people to
    # ignore it.
    if fallback:
        assert min(fallback) > max(genuine)
