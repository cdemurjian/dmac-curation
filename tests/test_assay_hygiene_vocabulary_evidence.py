import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import vocabulary_evidence as VE
from assay_hygiene.precedent import assay_index


def _assays():
    """Two junction-resolved assays and one junction-less one.

    Row 3 mirrors the 17 production assay records with no row in
    `dmac.assays_internal_assays`. Every registration test below turns on it:
    without such a row, filtering on `internal_assay_id.notna()` and falling
    back to `(assay_id, title)` are indistinguishable.
    """
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
         (481, "RNA Extraction", 9, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )


def _membership(rows):
    return pd.DataFrame(rows, columns=S.MEMBERSHIP_COLUMNS)


def _nodes(rows):
    return pd.DataFrame(rows, columns=S.NODES_COLUMNS)


def _tail(rows):
    return pd.DataFrame(rows, columns=["source_field", "raw_value",
                                       "n_samples", "example_uuids"])


def test_assay_index_falls_back_for_a_junction_less_assay():
    idx = assay_index(_assays())
    assert idx[1] == (10, 11, "Comet Chip")
    # not dropped, and not keyed null: its own (assay_id, title)
    assert idx[481] == (10, 481, "RNA Extraction")


def test_a_junction_less_registration_is_not_invisible():
    """The defect this module was rewritten to remove.

    Sample 300 is registered ONLY under the junction-less assay 481. Building
    the map by filtering `internal_assay_id.notna()` drops that row, so 300
    reads as registered nowhere, the term looks unanimous on assay 11, and a
    proposal built on it contradicts 300's actual registration. Measured on the
    real extract that exact reading turned `Type: m397` from 2 candidates at
    share 0.835 into 1 candidate at share 1.00 and invented 13 Mode 3 flags.
    """
    membership = _membership([(100, 1), (200, 1), (300, 481)])
    reg = VE.registered_assays(membership, _assays())
    assert reg[300] == {(481, "RNA Extraction")}
    assert reg[100] == {(11, "Comet Chip")}

    tail = _tail([("Type", "mystery", 3, "A-1; A-2; A-3")])
    meta = {sid: {"Type": "Mystery"} for sid in (100, 200, 300)}
    nodes = _nodes([("A-1", 100, "CEL"), ("A-2", 200, "CEL"), ("A-3", 300, "CEL")])
    row = VE.build_evidence(tail, meta, membership, _assays(), nodes).iloc[0]
    assert row.n_registered == 3, "a junction-less registration went missing"
    assert row.n_candidate_assays == 2, "the term must not read as unanimous"
    assert row.share == round(2 / 3, 3)


def test_base_rate_exposes_a_candidate_that_is_just_the_sample_type():
    """share 1.00 and base_rate 1.00 is the sample type talking, not the term.

    Both NHP samples carry the term and both are registered in assay 11, so
    share is 1.00. But EVERY registered NHP sample is in assay 11 whether or
    not it carries the term, so the term has told you nothing. This is the live
    IACUC-protocol-number case in miniature.
    """
    membership = _membership([(100, 1), (200, 1), (300, 1)])
    tail = _tail([("Protocol", "18032418", 2, "N-1; N-2")])
    meta = {100: {"Protocol": "18032418"}, 200: {"Protocol": "18032418"},
            300: {"Protocol": "something else"}}
    nodes = _nodes([("N-1", 100, "NHP"), ("N-2", 200, "NHP"),
                    ("N-3", 300, "NHP")])
    row = VE.build_evidence(tail, meta, membership, _assays(), nodes).iloc[0]
    assert row.share == 1.0
    assert row.base_rate == 1.0
    assert row.sample_types == "NHP:2"


def test_base_rate_stays_low_when_the_term_is_doing_the_work():
    # same shape as above, but the other samples of this type are registered
    # elsewhere, so the candidate is NOT the type's default
    membership = _membership([(100, 1), (200, 1), (300, 2), (400, 2)])
    tail = _tail([("Type", "cometchip", 2, "C-1; C-2")])
    meta = {100: {"Type": "CometChip"}, 200: {"Type": "cometchip"},
            300: {"Type": "other"}, 400: {"Type": "other"}}
    nodes = _nodes([("C-1", 100, "CEL"), ("C-2", 200, "CEL"),
                    ("C-3", 300, "CEL"), ("C-4", 400, "CEL")])
    row = VE.build_evidence(tail, meta, membership, _assays(), nodes).iloc[0]
    assert row.share == 1.0
    assert row.base_rate == 0.5
    assert (row.cand_id, row.cand_title) == (11, "Comet Chip")


def test_a_term_no_carrier_is_registered_under_reports_nothing_rather_than_guessing():
    membership = _membership([(999, 1)])
    tail = _tail([("Type", "orphan", 2, "O-1; O-2")])
    meta = {100: {"Type": "orphan"}, 200: {"Type": "orphan"}}
    nodes = _nodes([("O-1", 100, "CEL"), ("O-2", 200, "CEL")])
    row = VE.build_evidence(tail, meta, membership, _assays(), nodes).iloc[0]
    assert row.n_registered == 0
    assert row.n_candidate_assays == 0
    assert row.cand_id is None
    assert row.share == 0.0 and row.base_rate == 0.0


_SEED_PROBE = """
import sys
sys.path.insert(0, __SCRIPTS__)
import pandas as pd
from assay_hygiene import _schema as S
from assay_hygiene import vocabulary_evidence as VE

assays = pd.DataFrame(
    [(i, "Assay %d" % i, 7, 3, 2, 10, "MIT_SRP", 100 + i, "Internal %d" % i)
     for i in range(1, 9)],
    columns=S.ASSAY_COLUMNS,
)
# Every carrier registered in ALL EIGHT assays, so each sample's registration
# is an eight-element SET and every candidate ties at 3. Both halves matter: a
# singleton set has no iteration order to get wrong, and untied counts do not
# reach the tie-break. This is the only shape that exercises the defect.
membership = pd.DataFrame([(100 + s, a) for s in range(1, 4)
                           for a in range(1, 9)],
                          columns=S.MEMBERSHIP_COLUMNS)
tail = pd.DataFrame([("Type", "tied", 3, "T-1")],
                    columns=["source_field", "raw_value", "n_samples",
                             "example_uuids"])
meta = {100 + s: {"Type": "tied"} for s in range(1, 4)}
nodes = pd.DataFrame([("T-%d" % s, 100 + s, "CEL") for s in range(1, 4)],
                     columns=S.NODES_COLUMNS)
print(VE.build_evidence(tail, meta, membership, assays, nodes).to_csv(index=False))
"""


def test_the_table_is_byte_identical_under_any_hash_seed():
    """The bug that shipped once, in the form that can actually catch it.

    Sets of tuples iterate in PYTHONHASHSEED order and `Counter.most_common`
    breaks ties by insertion order, so the first version of this code reported
    61, 58 and 59 confounded terms on three consecutive runs of an unchanged
    script. Building the frame repeatedly in ONE process cannot see that: the
    seed is fixed for the life of an interpreter. It has to be a subprocess.

    Eight assays shared by all three carriers is an eight-way tie over
    eight-element sets, which is the input the defect needs.

    STABILITY ALONE IS NOT THE PROPERTY, so this pins the expected row too.
    Dropping the explicit tie-break while keeping `sorted()` yields a perfectly
    stable table that names a DIFFERENT assay on 23 of the real extract's 266
    rows, 8 of them flipping between an assay and its own `X Analysis` twin
    (30/31, 25/71, 89/91). A test asserting only "the same every time" is blind
    to the guard that decides 23 answers. With `sorted()` feeding
    `Counter.most_common` the eight-way tie resolves to the LOWEST key, 101,
    and the pinned row below is what catches it.

    `sorted()` on its own is decorative given the tie-break -- removing it
    leaves the output byte-identical, measured on the real extract -- so no
    assertion here goes red for that one. It stays because insertion order
    should be defined for whatever is aggregated here next.
    """
    import subprocess

    src = _SEED_PROBE.replace("__SCRIPTS__", repr(str(REPO / "scripts")))
    expected = (
        "source_field,raw_value,n_samples,sample_types,n_registered,"
        "n_candidate_assays,cand_id,cand_title,share,base_rate,example_uuids\n"
        "Type,tied,3,CEL:3,3,8,108,Internal 8,1.0,1.0,T-1"
    )
    outs = set()
    for seed in ("0", "1", "42", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-c", src], capture_output=True,
                           text=True, env=env, timeout=120)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout)
    assert len(outs) == 1, (
        f"the evidence table changed with PYTHONHASHSEED: {len(outs)} distinct "
        "outputs across four seeds"
    )
    assert outs.pop().strip() == expected, (
        "the table is stable but is no longer the expected table: an eight-way "
        "tie must resolve to the highest key by string form, not the first one "
        "inserted"
    )


def test_carriers_finds_every_sample_not_only_the_five_examples():
    # example_uuids caps at five; a share computed off five examples would be
    # wrong for exactly the high-volume terms that matter most
    tail = _tail([("Type", "cometchip", 7, "C-1; C-2; C-3; C-4; C-5")])
    meta = {i: {"Type": "CometChip"} for i in range(100, 107)}
    assert len(VE.carriers(meta, tail)[("Type", "cometchip")]) == 7


def test_a_numeric_looking_term_is_read_as_text(tmp_path):
    # the queue holds 12 bare-numeric Protocol values; an inferred int64 column
    # would make every lookup in carriers() miss
    p = tmp_path / "vocabulary-unresolved.csv"
    _tail([("Protocol", "18032418", 3, "N-1"),
           ("Protocol", "22010444", 3, "N-2")]).to_csv(p, index=False)
    back = VE.load_tail(p)
    assert list(back.raw_value) == ["18032418", "22010444"]
    assert all(isinstance(v, str) for v in back.raw_value)


def test_summarise_says_the_confounded_count_is_not_a_fourth_group():
    ev = pd.DataFrame(
        [("Type", "a", 3, "CEL:3", 3, 1, 11, "Comet Chip", 1.0, 1.0, "x")],
        columns=VE.EVIDENCE_COLUMNS,
    )
    text = VE.summarise(ev)
    assert "1 unresolved terms" in text
    assert "not a fourth group" in text
