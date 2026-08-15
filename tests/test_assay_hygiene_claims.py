import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import claims as C
from assay_hygiene import vocabulary as V


def _vocab():
    """Maps the fixture's raw values: comet terms -> 11, tissue terms -> 12."""
    return pd.DataFrame(
        [("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
         ("Protocol", "comet.docx", 11, "Comet Chip", 400, 380, 0.95, S.P_LEARNED),
         ("Instrument", "tissue scope", 12, "Tissue Collection", 50, 50, 1.0, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )


def _fixture_claims():
    fx = S.make_fixture()
    meta = V.parse_metadata(fx["samples"])
    uuids = dict(zip(fx["samples"].sample_id.astype(int), fx["samples"].uuid))
    return C.sample_claims(meta, uuids, _vocab())


def test_output_matches_the_contract():
    out = _fixture_claims()
    assert list(out.columns) == S.CLAIM_COLUMNS


def test_strong_and_weak_agreeing_is_corroborated():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-1"].iloc[0]
    assert row.tier == S.T_CORROBORATED
    assert row.internal_assay_id == 11


def test_strong_field_alone_is_strong():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-2"].iloc[0]
    assert row.tier == S.T_STRONG
    assert row.source_field == "Type"


def test_weak_field_alone_is_weak():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-3"].iloc[0]
    assert row.tier == S.T_WEAK
    assert row.source_field == "Protocol"


def test_fields_naming_different_assays_are_contested_and_both_survive():
    # Disagreement is data, not an error. Both candidates survive, each tiered
    # on ITS OWN evidence, and the disagreement is recorded in a column instead
    # of collapsing both rows into one unaudited tier.
    out = _fixture_claims()
    rows = out[out.uuid == "TIS-1"]
    assert len(rows) == 2
    assert set(rows.internal_assay_id) == {11, 12}
    assert rows.contested.all()
    # each row keeps the tier its own evidence earns
    assert set(rows.tier) == {S.T_STRONG}


def test_a_contested_sample_keeps_a_tier_the_audit_can_read():
    # The defect this design replaced: any disagreement collapsed the sample to
    # T_CONFLICT, which sits below the audit floor, so ADDING a claim REMOVED an
    # existing flag. Measured at 102 suppressed against 13 added. A tier must
    # never be lowered by the arrival of a second claim.
    out = _fixture_claims()
    assert S.T_CONFLICT not in set(out.tier)


def test_a_proposed_mapping_is_capped_at_weak_even_on_a_strong_field():
    # A proposal has support=0 and no empirical anchor. Graded by field alone it
    # would inherit the strong tier's measured 98.4%, which it has not earned.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Type", "mystery", 11, "Comet Chip", 0, 0, 0.0,
                             S.P_PROPOSED)
    meta = {700: {"Type": "mystery"}}
    out = C.sample_claims(meta, {700: "X-1"}, vocab)
    assert out.iloc[0].tier == S.T_WEAK
    assert out.iloc[0].provenance == S.P_PROPOSED


def test_a_proposal_cannot_corroborate_its_way_past_the_audit_floor():
    # The hole the cap was aimed at. Grading tier strength over ALL sources lets
    # a proposal on a STRONG field supply the strong half of a corroboration for
    # a claim whose only real evidence is a weak field -- and `corroborated` is
    # above the audit floor, so a support=0 model guess ends up able to accuse a
    # curator's registration. Measured at 104 such claims on the real extract.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Instrument", "comet scope", 11, "Comet Chip", 0, 0,
                             0.0, S.P_PROPOSED)
    meta = {702: {"Protocol": "comet.docx", "Instrument": "comet scope"}}
    out = C.sample_claims(meta, {702: "X-3"}, vocab)
    row = out.iloc[0]
    assert row.internal_assay_id == 11
    assert row.tier == S.T_WEAK          # NOT corroborated
    assert row.provenance == S.P_LEARNED  # the learned weak field still owns it
    # ...and the evidence columns must name the row that owns it. `provenance`,
    # `source_field` and `raw_value` describe ONE vocabulary row or they
    # describe nothing: `Instrument` sorts ahead of `Protocol` in CLAIM_FIELDS,
    # so reporting the first source found here would print the PROPOSED
    # Instrument value beside a `learned` provenance and a tier that value did
    # not earn. Task 7 puts these three columns in front of a curator as the
    # reason for a flag, and that curator would go and check a field whose
    # mapping nothing measured.
    assert row.source_field == "Protocol"
    assert row.raw_value == "comet.docx"


def test_provenance_names_the_row_the_evidence_columns_name():
    # `provenance` is ROW-level, not claim-level. This claim is backed by a
    # LEARNED strong field and a CURATOR weak field, and it reports `learned`:
    # the provenance of the row that `source_field` and `raw_value` point at.
    #
    # The alternative -- ranking provenance across the claim's sources, which is
    # what the brief's `sorted(provs - {P_PROPOSED})[0]` did by alphabetical
    # accident -- reports `curator` beside `source_field="Type"`, whose mapping
    # no curator ever touched. That is the same incoherence the representative
    # source rule was added to remove, and it is worse here than a cosmetic
    # mismatch: Task 7 shows these columns to a curator as the reason for a
    # flag, and `curator` is the one provenance that reads as "a human already
    # decided this", so the misattribution lands on the value most likely to
    # stop someone looking further.
    #
    # The curator's ruling is not lost by this choice. It supplied the weak half
    # and is therefore what made this claim `corroborated` rather than `strong`,
    # and vocabulary.csv remains the record of who ruled what.
    #
    # Unreachable today (0 curator rows of 736) but reachable through exactly
    # the escalation path the design names: a curator promoting a proposal they
    # agree with.
    vocab = _vocab()
    vocab.loc[vocab.source_field == "Protocol", "provenance"] = S.P_CURATOR
    meta = {703: {"Type": "cometchip", "Protocol": "comet.docx"}}
    out = C.sample_claims(meta, {703: "X-4"}, vocab)
    row = out.iloc[0]
    assert len(out) == 1
    assert row.tier == S.T_CORROBORATED   # the curator row supplied the weak half
    assert row.source_field == "Type"
    assert row.raw_value == "cometchip"
    assert row.provenance == S.P_LEARNED  # NOT curator: it names the Type row


def test_a_proposal_never_contests_a_learned_claim():
    # A proposal may corroborate, never contest. Otherwise a support=0 model
    # guess can push a curator's own registration out of the audit.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Software", "imagej", 12, "Tissue Collection", 0, 0,
                             0.0, S.P_PROPOSED)
    meta = {701: {"Type": "cometchip", "Software": "imagej"}}
    out = C.sample_claims(meta, {701: "X-2"}, vocab)
    learned = out[out.internal_assay_id == 11].iloc[0]
    assert learned.tier == S.T_STRONG
    assert not out.contested.any()


def test_a_sample_whose_values_resolve_to_nothing_emits_no_row():
    # DNA-1 has a populated Protocol that the vocabulary does not map. The tier
    # depends on whether values RESOLVE, not on whether fields are populated.
    out = _fixture_claims()
    assert out[out.uuid == "DNA-1"].empty


def test_one_assay_id_is_one_claim_even_when_the_titles_disagree():
    # A claim is about an assay ID. The title is display, and it is NOT stable
    # per id across the vocabulary: merge_vocabulary rebuilds titles from the
    # assays frame only where that frame HAS one, so the 14 junction-less rows
    # (ids 466, 469, 470, 471, 472, measured on the real vocabulary) keep
    # whatever title they carry -- None on a learned row, hand-typed on a
    # curator row that rules on the same term.
    #
    # Grouping a sample's hits by (id, title) would then split ONE assay into
    # two claims and mark both `contested`, which is precisely the
    # audit-suppressing shape this design was rewritten to remove: two
    # spellings of one title would demote a corroborated claim and delete a
    # Mode 3 flag. Zero ids carry two titles in today's file, so this is a
    # guard on a reachable state, not a repair of a live one.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Protocol", "comet.docx", 11, None, 400, 380, 0.95,
                             S.P_LEARNED)
    meta = {100: {"Type": "cometchip", "Protocol": "comet.docx"}}
    out = C.sample_claims(meta, {100: "D.IMG-1"}, vocab)
    assert len(out) == 1
    assert out.iloc[0].tier == S.T_CORROBORATED
    assert not out.contested.any()
    # the id's one real title survives; a NULL on another row does not erase it
    assert out.iloc[0].internal_assay_title == "Comet Chip"


def test_claim_index_is_keyed_on_field_and_value_together_and_carries_provenance():
    # The same string can mean different assays under different fields, so the
    # field is part of the key. A value-only index would collide them.
    # Provenance rides along because the tier cap and the contest rule both
    # need it, and claim_index is the only place claims.py sees the vocabulary.
    idx = C.claim_index(_vocab())
    assert idx[("Type", "cometchip")] == (11, "Comet Chip", S.P_LEARNED)
    assert ("cometchip",) not in idx

    # The VOCABULARY side of the key is normalised too, and it has to be.
    # vocabulary.csv exists to be hand-corrected, and a curator naturally types
    # the value the way it appears in the metadata (`Tissue Scope`), which is
    # not the normalised key. sample_claims looks values up by their NORMALISED
    # metadata value, and vocabulary.unresolved_terms normalises both sides too
    # -- so an un-normalised vocabulary key is matched by nothing and is absent
    # from the judgment queue that would have surfaced it. The curator's
    # decision would sit in the file, be counted as resolved, and be invisible
    # to every consumer. Zero of the 736 live rows are un-normalised today
    # because all 736 are `learned` and learn_vocabulary emits normalised
    # values; the first hand-edited row is the one that breaks.
    hand = _vocab()
    hand.loc[len(hand)] = ("Type", "  Tissue Scope ", 12, "Tissue Collection",
                           5, 5, 1.0, S.P_CURATOR)
    assert C.claim_index(hand)[("Type", "tissue scope")] == (
        12, "Tissue Collection", S.P_CURATOR)
