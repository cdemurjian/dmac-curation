"""The first test file `dossier.py` has ever had.

IT IS THE MODULE THAT FED 1,012 AGENT ADJUDICATIONS on 2026-08-21 and it had no
test at all. It is also where the precedent-denominator defect was RENDERED: the
packet showed `n_child_only` -- a count of EDGES -- labelled "pairs", under the
reading "A low rate over MANY pairs is the house repeatedly declining it". That
reading is never valid, because every edge in that count names a sample the
house has not registered, which is the proposal itself.

WHAT THESE TESTS GUARD AND HOW, because the defining defect of this rework is
asserting a rendering against the field that renders it. Every case below

  * slices the rendered object out by its OWN key (`d["precedent"]`), so a
    number moving to another block fails rather than being found anyway; and
  * recomputes its expected value from the RAW EDGE FRAME -- `len(edges)`,
    `edges.parent_id.nunique()` -- and never from the findings column, the
    precedent frame or the dossier itself. The numbers travel
    edges -> `mine_precedent` -> a findings row -> `build_dossiers`, and the
    test computes the answer off the first of those four.

Each test's docstring says what would make it fail. A guard nobody can falsify
is a comment.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import dossier as D
from assay_hygiene import precedent as P
from assay_hygiene import review as R

ASSAY_TITLE = "Antibody-Dependent Functional Profiling (ADFP)"
INTERNAL_ID = 11
SEEK_ID = 1
PROJECT = 10

# The parent of the ADD_PARENT hop and the child of the ADD_CHILD hop: the two
# samples a proposal is ABOUT, and the two the sample-grained counts count.
PARENT_UUID = "TIS-260101ALT-1"
CHILD_UUID = "AB-260101ALT-1"

N_CHILDREN = 4      # the ALT|TIS|ADFP fan-out, which is 325 parents x 4
N_PARENTS = 3       # deliberately NOT 4, so the two directions cannot pass
                    # each other's assertions


def _world():
    """Two hops in one extract, one fanning out each way. -> five frames.

    ADD_PARENT hop   parent 800 `TIS` with `N_CHILDREN` `D.ADCD` children, all
                     of them registered in the assay and the parent in nothing.
                     This is `ALT|TIS|ADFP` minimised: the real rule reads
                     `n_child_only` 1,300 over `n_child_only_samples` 325.
    ADD_CHILD  hop   child 810 `AB` with `N_PARENTS` `ABP` parents, all
                     registered and the child in nothing.

    The two hops share no sample and no type pair, so `mine_precedent` keys
    them as two rules and neither direction can read the other's counts.
    """
    assays = pd.DataFrame(
        [(SEEK_ID, "ADFP", 7, 3, 2, PROJECT, "MIT_SRP", INTERNAL_ID,
          ASSAY_TITLE)],
        columns=S.ASSAY_COLUMNS,
    )
    kids = [(900 + k, f"D.ADCD-260101ALT-{k}") for k in range(N_CHILDREN)]
    rents = [(920 + k, f"ABP-260101ALT-{k}") for k in range(N_PARENTS)]
    edges = pd.DataFrame(
        [(sid, 800, uuid, PARENT_UUID, "D.ADCD", "TIS", None, None, None)
         for sid, uuid in kids]
        + [(810, sid, CHILD_UUID, uuid, "AB", "ABP", None, None, None)
           for sid, uuid in rents],
        columns=S.EDGE_COLUMNS,
    )
    # every neighbour registered; neither proposal target registered anywhere
    membership = pd.DataFrame(
        [(sid, SEEK_ID) for sid, _ in kids + rents],
        columns=S.MEMBERSHIP_COLUMNS,
    )
    nodes = pd.DataFrame(
        [(PARENT_UUID, 800, "TIS"), (CHILD_UUID, 810, "AB")]
        + [(uuid, sid, "D.ADCD") for sid, uuid in kids]
        + [(uuid, sid, "ABP") for sid, uuid in rents],
        columns=S.NODES_COLUMNS,
    )
    samples = pd.DataFrame(
        [(800, PARENT_UUID, json.dumps({"Type": "tissue"}), None, str(PROJECT)),
         (810, CHILD_UUID, json.dumps({"Type": "antibody"}), None, str(PROJECT))]
        + [(sid, uuid, "{}", None, str(PROJECT))
           for sid, uuid in kids + rents],
        columns=S.SAMPLE_COLUMNS,
    )
    return edges, membership, assays, nodes, samples


def _findings(prec: pd.DataFrame) -> pd.DataFrame:
    """Two MODE_2 rows, each carrying the counts of ITS OWN mined rule.

    The counts are read out of `mine_precedent`'s frame by RULE KEY rather than
    hand-written, which is what makes the assertions end-to-end: a test that
    typed 4 and 1 in here would prove only that `build_dossiers` copies cells.
    """
    def rule(child_type, parent_type):
        hit = prec[(prec.child_type == child_type)
                   & (prec.parent_type == parent_type)]
        assert len(hit) == 1, f"{child_type}->{parent_type} is not one rule"
        return hit.iloc[0]

    fwd, rev = rule("D.ADCD", "TIS"), rule("AB", "ABP")
    rows = []
    for r, sid, uuid, stype, action, neighbour, direction in (
        # NEITHER NEIGHBOUR IS THE FIRST RELATIVE IN SORT ORDER, deliberately.
        # `the_evidence` must be the neighbour the finding row NAMES; a
        # fixture whose named neighbour is also `sorted(...)[0]` cannot tell
        # the two apart, and "the first few relatives and a hope" is the
        # defect this field exists to fix.
        (fwd, 800, PARENT_UUID, "TIS", "ADD_PARENT_TO_ASSAY",
         "D.ADCD-260101ALT-2", "propagation_rate"),
        (rev, 810, CHILD_UUID, "AB", "ADD_CHILD_TO_ASSAY",
         "ABP-260101ALT-1", "reverse_rate"),
    ):
        row = {c: None for c in S.FINDING_COLUMNS}
        row.update({
            "sample_id": sid, "uuid": uuid, "sample_type": stype,
            "project_ids": str(PROJECT),
            "proposed_internal_assay_id": INTERNAL_ID,
            "proposed_internal_assay_title": ASSAY_TITLE,
            "mode": S.MODE_2, "classification": S.CLS_ABSENCE_LINEAGE,
            "lineage": True, "lineage_neighbour_uuid": neighbour,
            "precedent_rate": float(getattr(r, direction)),
            "precedent_direction": direction,
            "precedent_n_both": int(r.n_both),
            "precedent_n_child_only": int(r.n_child_only),
            "precedent_n_child_only_samples": int(r.n_child_only_samples),
            "precedent_n_parent_only": int(r.n_parent_only),
            "precedent_n_parent_only_samples": int(r.n_parent_only_samples),
            "action": action,
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=S.FINDING_COLUMNS)


@pytest.fixture
def built(tmp_path):
    """-> (dossiers by action, the raw edge frame). One build, several cases."""
    edges, membership, assays, nodes, samples = _world()
    for name, frame in (("edges", edges), ("membership", membership),
                        ("assays", assays), ("nodes", nodes),
                        ("samples", samples)):
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    context = R.load_context(tmp_path)
    prec = P.mine_precedent(edges, membership, assays)
    out = D.build_dossiers(_findings(prec), context, assays, membership, nodes)
    by_action = {d["action"]: d for d in out}
    assert len(out) == len(by_action) == 2, out
    return by_action, edges


def test_the_precedent_block_reports_edges_and_samples_and_they_differ(built):
    """The defect, in the object a reviewer actually reads.

    `edges_where_only_the_relative_is` is `N_CHILDREN` because that many EDGES
    have a registered child and an unregistered parent;
    `samples_where_only_the_relative_is` is 1 because all of them name the same
    parent. Both expectations come from the EDGE FRAME -- `len` and `nunique`
    on `edges` -- so an implementation that rendered the same cell twice, or
    that counted the registered CHILDREN instead of the proposed parent, fails.

    WHAT MAKES THIS FAIL: rendering only the edge count (the shipped
    behaviour); rendering the sample count in both slots; counting children;
    dropping either key. Verified by mutation -- setting the sample slot to
    `n_missing` turns the third assertion red.
    """
    by_action, edges = built
    block = by_action["ADD_PARENT_TO_ASSAY"]["precedent"]

    child_only = edges[edges.parent_id == 800]
    assert block["edges_where_only_the_relative_is"] == len(child_only) \
        == N_CHILDREN
    assert block["samples_where_only_the_relative_is"] \
        == child_only.parent_id.nunique() == 1
    assert (block["edges_where_only_the_relative_is"]
            != block["samples_where_only_the_relative_is"])

    # the rate is untouched and still reads over the edge counts
    assert block["rate"] == 0.0
    assert block["edges_where_both_registered"] == 0


def test_the_direction_chooses_the_column_pair_and_not_one_column(built):
    """ADD_CHILD reads the reverse counts, in BOTH grains.

    The two hops carry deliberately different fan-outs -- 4 and 3 -- so a
    dossier reading the wrong direction's column shows the other cohort's
    number rather than a plausible one. Expected values again come from the
    edge frame.

    WHAT MAKES THIS FAIL: taking the edge count from one direction and the
    sample count from the other (the shape the old single-column lookup would
    have grown into); reading `precedent_n_child_only` for ADD_CHILD.
    """
    by_action, edges = built
    block = by_action["ADD_CHILD_TO_ASSAY"]["precedent"]

    parent_only = edges[edges.child_id == 810]
    assert block["edges_where_only_the_relative_is"] == len(parent_only) \
        == N_PARENTS
    assert block["samples_where_only_the_relative_is"] \
        == parent_only.child_id.nunique() == 1

    # ...and it is NOT the other direction's number, which is the whole point
    other = by_action["ADD_PARENT_TO_ASSAY"]["precedent"]
    assert (block["edges_where_only_the_relative_is"]
            != other["edges_where_only_the_relative_is"])


def test_the_reading_no_longer_calls_the_denominator_a_refusal(built):
    """The retired sentence, and the claim that replaced it.

    The shipped string said "A low rate over MANY pairs is the house repeatedly
    declining it". It is retired rather than softened, and the replacement has
    to state the grain, because the count is of edges belonging to the samples
    being proposed.

    THE KEY-NAMING ASSERTION IS THE ONE THAT CANNOT GO STALE. It reads the
    block's OWN keys and requires the prose to name them, so renaming a key
    without rewriting the sentence fails here rather than shipping a reading
    that points at a field nobody can find.

    WHAT MAKES THIS FAIL: restoring the old sentence (`declin` fires); renaming
    a rendered key; a reading that mentions neither grain.
    """
    block = built[0]["ADD_PARENT_TO_ASSAY"]["precedent"]
    reading = block["reading"]

    assert "declin" not in reading.lower(), (
        "the retired reading told a curator that a large denominator was the "
        "house refusing; every edge in it is a proposal")
    assert "pairs" not in " ".join(k for k in block if k != "reading"), (
        "'pairs' is the word that let an EDGE count read as a count of "
        "sample pairs")

    # the prose names the two counts it is explaining, by their own key names
    for key in ("edges_where_only_the_relative_is",
                "samples_where_only_the_relative_is"):
        assert key in block
        assert key in reading, (
            f"the reading explains {key} without naming it, so a curator "
            "cannot tell which number the sentence is about")
    assert "EDGES" in reading


def test_the_evidence_names_the_neighbour_the_finding_row_named(built):
    """The packet's other load-bearing field, since this module had no test.

    A capped relative list is not evidence: on the first build 8.1% of examples
    and 86 whole cohorts showed the assay-holding relative in no example. The
    dossier therefore carries `the_evidence`, taken from
    `lineage_neighbour_uuid`, and it must be THAT neighbour rather than the
    first one sorted.

    WHAT MAKES THIS FAIL: reverting `the_evidence` to `parents[0]` /
    `children[0]`; getting the relationship backwards for a direction;
    computing `holds_the_proposed_assay` off the wrong sample. The fixture
    names the THIRD child and the SECOND parent, so `sorted(...)[0]` is a
    different uuid in both directions and the substitution is visible.
    """
    by_action, _ = built
    ev = by_action["ADD_PARENT_TO_ASSAY"]["examples"][0]["the_evidence"]
    assert ev["uuid"] == "D.ADCD-260101ALT-2"
    assert ev["relationship"] == "CHILD of this sample"
    assert ev["holds_the_proposed_assay"] is True
    assert ev["registered_assays"] == [ASSAY_TITLE]

    # the mirror, so a direction swap cannot pass both
    ev = by_action["ADD_CHILD_TO_ASSAY"]["examples"][0]["the_evidence"]
    assert ev["uuid"] == "ABP-260101ALT-1"
    assert ev["relationship"] == "PARENT of this sample"
    assert ev["holds_the_proposed_assay"] is True


def test_the_sample_being_proposed_holds_nothing_yet(built):
    """The absence the whole packet is about, asserted rather than assumed.

    Every case above rests on the proposal target being unregistered -- that is
    what makes each child-only edge a candidate rather than a refusal. If the
    fixture ever registered it, the counts would collapse to `n_both` and the
    two grains would agree for the wrong reason.
    """
    by_action, _ = built
    for action, uuid in (("ADD_PARENT_TO_ASSAY", PARENT_UUID),
                         ("ADD_CHILD_TO_ASSAY", CHILD_UUID)):
        sample = by_action[action]["examples"][0]["sample"]
        assert sample["uuid"] == uuid
        assert sample["registered_assays"] == []
