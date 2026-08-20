"""Task 2: the vocabulary gate, which runs before every mode.

WHY THIS FILE EXISTS, stated once. Increment 1 shipped an audit reporting 866
"contradictions" and measurement later showed essentially none of them were.
A large share are defects in the learned vocabulary that maps a metadata term
to an assay, and because nothing tested the vocabulary those defects were
laundered into membership write proposals: 11 A.FLOW rows registered in 31 Flow
Cytometry ANALYSIS claiming 30 Flow Cytometry through a `Software: FlowJo`
family that splits across three assays, and 13 A.SPC rows claiming 130 Mass
Spectrometry, an assay no A.SPC sample is registered in anywhere. Both sets
were filed as lineage absences. `test_the_24_flowjo_and_mass_spectra_rows_are
_all_rejected_by_the_gate` is the regression for exactly those 24 and it is the
hard acceptance test for this task: if they pass the gate, the gate does not
work, whatever the aggregate numbers say.

THE THRESHOLDS ARE TESTED IN THEIR UNITS, not by value. `VOCAB_COLUMNS` carries
both `support` (EDGES) and `n_samples` (DISTINCT SAMPLES) and one sample fans
out to many edges: measured on the real extract, 50 of 736 learned terms rest
on exactly ONE sample and 21 of those clear an edge floor of 30. So
`test_the_support_floor_counts_distinct_samples_and_not_edges` builds one row
that is thick in edges and thin in samples and one that is the reverse, and
asserts which way each is ruled. A threshold quoted without its unit is the
defect this project keeps repeating.

NOTHING HERE IMPORTS `MIN_CO_REG_SUPPORT` OR `CO_OCCUR_BAND`. Those are
co-registration reporting bands, they size a population of samples of a type,
and `tests/test_assay_hygiene_schema.py` asserts that `compatibility.py` is the
ONLY module under `scripts/assay_hygiene/` outside `_schema.py` reading either
name, and that it BANDS on them rather than gating. The gate's floors are its
own and live in `gate.py`.
"""
import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import audit as A  # noqa: E402
from assay_hygiene import claims as C  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"


# --- fixture plumbing --------------------------------------------------------


def _nodes(fx):
    """The fixture's node index, built from the one frame carrying a type.

    `make_fixture()` has no `nodes` frame and `SAMPLE_COLUMNS` carries no type,
    so the uuid -> (sample_id, type) index is assembled from the edge frame,
    which names both endpoints of every hop. This is the same derivation
    `tests/test_assay_hygiene_schema.py::_types` performs, in the shape
    `NODES_COLUMNS` declares.
    """
    seen = {}
    for r in fx["edges"].itertuples(index=False):
        seen[r.child_uuid] = (int(r.child_id), r.child_type)
        seen[r.parent_uuid] = (int(r.parent_id), r.parent_type)
    return pd.DataFrame(
        [(u, sid, t) for u, (sid, t) in sorted(seen.items())],
        columns=S.NODES_COLUMNS,
    )


def _world(fx=None):
    """(claims, vocabulary, type_reg, types) for the shared fixture."""
    fx = fx or S.make_fixture()
    nodes = _nodes(fx)
    meta = V.parse_metadata(fx["samples"])
    uuids = dict(zip(fx["samples"].sample_id.astype(int), fx["samples"].uuid))
    claims = C.sample_claims(meta, uuids, fx["vocabulary"])
    return (
        claims,
        fx["vocabulary"],
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )


def _claim(sample_id, uuid, iaid, title, field, raw, *,
           tier=S.T_STRONG, contested=False, provenance=S.P_LEARNED):
    """One CLAIM_COLUMNS row, positionally.

    Hand-built rather than derived through `claims.sample_claims` wherever the
    property under test needs a claim that stage B2's collapse cannot express.
    That collapse is real and is documented in `gate_claims`: a sample whose
    metadata names ONE assay through two fields emits ONE claim row carrying
    the first backed source in `CLAIM_FIELDS` order, so the fixture's
    `Software: cometchip` and `DataType: illumina library` rows never reach the
    gate as the representative of their own sample.
    """
    return (sample_id, uuid, iaid, title, tier, field, raw, contested, provenance)


def _claims(*rows):
    return pd.DataFrame(list(rows), columns=S.CLAIM_COLUMNS)


def _vocab(*rows):
    return pd.DataFrame(list(rows), columns=S.VOCAB_COLUMNS)


# --- reachability ------------------------------------------------------------


def test_a_type_never_registered_in_the_claimed_assay_is_unreachable_and_reaches_no_mode():
    """DNA 301 claims Comet Chip through the same term that passes for D.IMG.

    No DNA sample is registered in any assay in this world, so the claim is not
    credible however good the term is. 301 is also Mode 1's population -- it is
    registered nowhere -- which is what makes the second assertion load-bearing:
    the gate has to stop this becoming a Mode 1 proposal, and `reaches_modes`
    is the membership test that says so rather than an inequality a later edit
    can forget to extend.
    """
    claims, vocab, type_reg, types = _world()
    gated = G.gate_claims(claims, vocab, type_reg, types)

    row = gated[gated.sample_id == 301]
    assert len(row) == 1
    assert row.gate.iloc[0] == S.GATE_UNREACHABLE
    assert row.sample_type.iloc[0] == "DNA"
    assert row.type_registrations.iloc[0] == 0
    assert "DNA" in row.gate_reason.iloc[0]

    assert not G.reaches_modes(gated)[row.index[0]]
    assert G.blocks_mode(S.GATE_UNREACHABLE)

    # ...and the term itself is fine: it is the CLAIM that is incredible, not
    # the mapping. D.IMG 100 carries the same value and passes.
    same_term = gated[(gated.sample_id == 100)]
    assert same_term.raw_value.iloc[0] == row.raw_value.iloc[0]
    assert same_term.gate.iloc[0] == S.GATE_PASS


def test_reachability_is_about_the_type_not_about_this_samples_own_registration():
    """The A.FLOW shape: type IS registered there, this sample's assays are not.

    The 11 rows this gate exists for sit at co-registration 0.000 over 57
    samples -- 31 Flow Cytometry Analysis and 30 Flow Cytometry never co-occur
    on an A.FLOW -- and they must still pass REACHABILITY, because a claim
    naming an assay the type does hold is credible whatever this one sample
    holds. A reachability test that folded in co-registration would reject them
    here and the gate could no longer tell an incredible claim from an
    alternative label.
    """
    membership = pd.DataFrame(
        [(1, 10), (2, 10), (3, 11), (4, 11)], columns=S.MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [(10, "Flow Cytometry", 7, 3, 2, 10, "P", 30, "Flow Cytometry"),
         (11, "Flow Cytometry Analysis", 7, 3, 2, 10, "P", 31,
          "Flow Cytometry Analysis")],
        columns=S.ASSAY_COLUMNS,
    )
    nodes = pd.DataFrame(
        [(f"A.FLOW-{i}", i, "A.FLOW") for i in (1, 2, 3, 4)],
        columns=S.NODES_COLUMNS,
    )
    vocab = _vocab(("Software", "flowjo", 30, "Flow Cytometry",
                    2433, 155, 0.99, S.P_LEARNED))
    # sample 3 holds 31 and nothing else; 30 and 31 never co-occur here
    claims = _claims(_claim(3, "A.FLOW-3", 30, "Flow Cytometry",
                            "Software", "FlowJo"))

    type_reg = G.type_registration_index(membership, assays, nodes)
    assert type_reg[("A.FLOW", 30)] == 2
    gated = G.gate_claims(claims, vocab, type_reg, G.sample_type_index(nodes))
    assert gated.gate.iloc[0] == S.GATE_PASS
    assert gated.type_registrations.iloc[0] == 2


def test_type_registration_index_counts_distinct_samples_of_the_type():
    """The value is samples, not membership rows, and the key crosses the junction.

    `membership.assay_id` is a seek `assays.id` and the gate speaks internal
    ids, so the index has to cross `assay_index`'s funnel or it compares two id
    spaces that overlap numerically and share no meaning.

    THE SECOND WORLD BELOW IS THE ONE THAT MAKES THE TITLE TRUE, and it is here
    because self-review caught its absence: over the shared fixture alone, no
    sample is registered twice in one INTERNAL assay, so rows and distinct
    samples are equal in every cell and a row-counting index passes every
    assertion above. That is the self-certifying-test failure increment 1
    shipped five of. The real shape it stands in for is ordinary -- seek
    instantiates the same logical assay once per study, 458 records collapsing
    to 137 internal ids, 154 in `precedent.assay_index`'s map once the 17
    junction-less records take a fallback -- so a sample in two studies' Tissue
    Collection is two membership rows and one sample of that type.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    idx = G.type_registration_index(fx["membership"], fx["assays"], nodes)

    # seek 1 -> internal 11, seek 2 -> internal 12, seek 3 -> internal 13
    assert idx[("TIS", 11)] == 2          # 200, 201
    assert idx[("TIS", 12)] == 4          # 200, 201, 202, 203
    assert idx[("PAV", 13)] == 1          # 700
    assert idx[("D.IMG", 11)] == 3        # 100, 101, 102
    assert ("DNA", 11) not in idx         # no DNA sample is registered anywhere
    assert all(isinstance(v, int) and v > 0 for v in idx.values())

    # two seek assays, one internal assay, one sample registered under both:
    # three membership rows over two distinct samples.
    assays = pd.DataFrame(
        [(1, "Tissue Collection", 7, 3, 2, 10, "P", 74, "Tissue Collection"),
         (2, "Tissue Collection", 8, 4, 2, 11, "Q", 74, "Tissue Collection")],
        columns=S.ASSAY_COLUMNS,
    )
    membership = pd.DataFrame(
        [(1, 1), (1, 2), (2, 1)], columns=S.MEMBERSHIP_COLUMNS,
    )
    nodes = pd.DataFrame(
        [("TIS-1", 1, "TIS"), ("TIS-2", 2, "TIS")], columns=S.NODES_COLUMNS,
    )
    assert G.type_registration_index(membership, assays, nodes) == {("TIS", 74): 2}


def test_registrations_whose_sample_has_no_node_row_are_named_and_not_dropped():
    """This package's house rule: nothing is dropped silently.

    A membership row whose sample has no node row carries no type, so it can
    contribute to no (type, assay) cell. Measured on the real extract, 194
    samples over 210 of the 214,296 membership rows are in that state. They are
    excluded from the index of necessity and are therefore NAMED, the way
    `stage0.plan_edges` counts its drops, so a growing number is visible rather
    than being absorbed into a reachability answer.
    """
    membership = pd.DataFrame(
        [(1, 10), (999, 10), (998, 10)], columns=S.MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [(10, "Flow Cytometry", 7, 3, 2, 10, "P", 30, "Flow Cytometry")],
        columns=S.ASSAY_COLUMNS,
    )
    nodes = pd.DataFrame([("A.FLOW-1", 1, "A.FLOW")], columns=S.NODES_COLUMNS)

    assert G.untyped_registration_samples(membership, nodes) == [998, 999]
    idx = G.type_registration_index(membership, assays, nodes)
    assert idx == {("A.FLOW", 30): 1}


# --- term families -----------------------------------------------------------


def test_a_term_family_mapping_to_two_assays_is_incoherent():
    """`Software: cometchip` and `cometchip v2` are one product and two assays.

    Both members clear every floor, so nothing but the family can reject them,
    which is what stops this test passing for the wrong reason. The claim is
    hand-built because stage B2 collapses sample 202's two fields onto one
    assay and hands the gate the curator row instead; see `_claim`.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    claims = _claims(_claim(202, "TIS-3", 11, "Comet Chip",
                            "Software", "cometchip"))
    gated = G.gate_claims(
        claims, fx["vocabulary"],
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    assert gated.gate.iloc[0] == S.GATE_INCOHERENT
    assert gated.term_family.iloc[0] == "Software/cometchip"
    assert gated.family_internal_assay_ids.iloc[0] == "11;12"
    assert not G.reaches_modes(gated).iloc[0]

    # the row clears both floors, so only the family can have caught it
    assert gated.vocab_n_samples.iloc[0] >= G.MIN_VOCAB_SAMPLES
    assert gated.vocab_purity.iloc[0] >= G.MIN_VOCAB_PURITY


def test_the_whole_family_is_reported_and_not_only_the_member_a_claim_rests_on():
    """Report the family; do not auto-resolve it.

    Only `cometchip` carries a claim here, and `cometchip v2` carries none --
    exactly the real shape, where `flowjo 10.8.1` backs 0 of the 138,007 claims
    while sitting in the family that splits across 30, 31 and 153. A defect
    file naming only the member a claim happened to rest on would tell a
    curator to fix one row of a split they cannot see, so every member is
    emitted, claim or no claim.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    claims = _claims(_claim(202, "TIS-3", 11, "Comet Chip",
                            "Software", "cometchip"))
    gated = G.gate_claims(
        claims, fx["vocabulary"],
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    defects = G.vocabulary_defects(gated, fx["vocabulary"])

    fam = defects[defects.defect == S.GATE_INCOHERENT]
    assert set(zip(fam.source_field, fam.raw_value)) == {
        ("Software", "cometchip"), ("Software", "cometchip v2")}
    assert list(fam.term_family) == ["Software/cometchip"] * 2
    assert set(fam.family_internal_assay_ids) == {"11;12"}
    # the member no claim rests on is reported with a zero count, not omitted
    silent = fam[fam.raw_value == "cometchip v2"]
    assert silent.n_claims.iloc[0] == 0
    assert fam[fam.raw_value == "cometchip"].n_claims.iloc[0] == 1


def test_stem_extraction_does_not_collapse_genuinely_different_products():
    """The stem strips a trailing VERSION, and nothing else.

    Three negative cases, each aimed at a rule that would have shipped
    otherwise:

      substring       `chip seq` -> 12 against `chipper` -> 11, the fixture's
                      own negative, which a substring rule collapses
      leading token   `total rna` -> 61 against `total igg` -> 155. This is the
                      one that matters: a first-token stem is the obvious rule,
                      and measured over the real vocabulary it manufactures 27
                      incoherent families covering 14,957 claims, including all
                      204 `total RNA` flags the spec reads as ordinary
                      absences. The version rule finds ONE family, the real one.
      analysis pair   `agilent masshunter` -> 130 against `agilent masshunter
                      quantitative analysis` -> 47, the measurement/analysis
                      distinction this project has already mistaken for an
                      error twice.

    The positive control is in the same test on purpose: a stem rule that
    collapses nothing passes every negative case there is.
    """
    fx = S.make_fixture()
    negatives = _vocab(
        ("Type", "total rna", 61, "RNA Extraction", 644, 644, 0.99, S.P_LEARNED),
        ("Type", "total igg", 155, "Glycosylation Assay", 54, 40, 1.0,
         S.P_LEARNED),
        ("Software", "agilent masshunter", 130, "Mass Spectrometry",
         1622, 80, 1.0, S.P_LEARNED),
        ("Software", "agilent masshunter quantitative analysis", 47,
         "Mass Spectrometry Analysis", 38, 23, 1.0, S.P_LEARNED),
    )
    assert G.incoherent_families(negatives) == {}
    assert G.incoherent_families(fx["vocabulary"]) == {
        ("Software", "cometchip"): [11, 12]}

    # the positive control, in the real spelling
    flowjo = _vocab(
        ("Software", "flowjo", 30, "Flow Cytometry", 2433, 155, 0.85,
         S.P_LEARNED),
        ("Software", "flowjo 10.3", 153, "ADFP", 110, 2, 1.0, S.P_LEARNED),
        ("Software", "flowjo v10.8.1", 31, "Flow Cytometry Analysis",
         607, 2, 1.0, S.P_LEARNED),
        ("Software", "flowjo version 10", 31, "Flow Cytometry Analysis",
         2340, 24, 1.0, S.P_LEARNED),
    )
    assert G.incoherent_families(flowjo) == {("Software", "flowjo"): [30, 31, 153]}

    # and the stem itself, term by term, so a failure names the term
    assert G.term_stem("flowjo version 10.8.1") == "flowjo"
    assert G.term_stem("flowjo v10.8.1") == "flowjo"
    assert G.term_stem("cometchip v2") == "cometchip"
    assert G.term_stem("total igg") == "total igg"
    assert G.term_stem("chipper") == "chipper"
    assert G.term_stem("10.3") == "10.3"     # all version, so no stem to take


# --- the floors, and their units ---------------------------------------------


def test_the_support_floor_counts_distinct_samples_and_not_edges():
    """The units ruling, asserted in both directions.

    `support` counts EDGES and `n_samples` counts DISTINCT SAMPLES, and one
    sample fans out to many edges: on the real extract `Software: matlab` reads
    support 132 from ONE sample and `Type: github` support 73 from one, 50 of
    the 736 learned terms rest on a single sample and 21 of those clear an edge
    floor of 30. The floor asks how many independent curator decisions back a
    mapping, so it reads `n_samples`; a floor over `support` passes both rows
    above and rejects nothing this test would notice.

    Both directions are asserted because only the pair is evidence. `thick` is
    thick in edges and thin in samples and must be REJECTED; `thin` is thin in
    edges and rests on enough samples and must PASS. A floor over the wrong
    column gets both backwards.
    """
    vocab = _vocab(
        ("Type", "thick", 11, "Comet Chip", 132, 1, 1.0, S.P_LEARNED),
        ("Type", "thin", 11, "Comet Chip", 8, 8, 1.0, S.P_LEARNED),
    )
    type_reg = {("TIS", 11): 40}
    types = {"TIS-1": "TIS", "TIS-2": "TIS"}
    claims = _claims(
        _claim(1, "TIS-1", 11, "Comet Chip", "Type", "thick"),
        _claim(2, "TIS-2", 11, "Comet Chip", "Type", "thin"),
    )
    gated = G.gate_claims(claims, vocab, type_reg, types, min_samples=3)

    assert list(gated.gate) == [S.GATE_LOW_SUPPORT, S.GATE_PASS]
    assert gated.vocab_support.iloc[0] == 132     # would clear any edge floor
    assert gated.vocab_n_samples.iloc[0] == 1
    assert "sample" in gated.gate_reason.iloc[0]
    assert "1" in gated.gate_reason.iloc[0]
    # the shipped default is the same number in the honest unit
    assert G.MIN_VOCAB_SAMPLES == 3


def test_the_purity_floor_marks_the_mapping_behind_212_of_250_compat_flags():
    """`Type: Illumina Library` -> 24 DNA Extraction, purity 0.707.

    Measured on the real extract: support 2,210 edges over 2,210 distinct
    samples, so no support floor in either unit touches it and purity is the
    only axis that does. It drove 212 of increment 1's 250 `ABSENCE_COMPAT`
    flags and 269 of the 866 overall, and an Illumina library is a library --
    those DNA samples are already correctly registered in 115 Library Creation.

    MARKS AND DOES NOT REJECT, which is the whole point of the name. This test
    was called `..._rejects_...` and said the claim "does not get to author a
    membership proposal unreviewed", and ruling A made both false while the body
    -- which only ever asserted the outcome LABEL -- stayed green. So the title
    promised passage semantics the module contradicts and the test never
    exercised, which is the self-certifying failure this file has now produced
    three times. The `reaches_modes` assertion below is what makes the name
    load-bearing.

    The floor is 0.75, anchored on a measurement this repo publishes: held out
    by sample over 333,717 test edges, terms below 0.75 purity predict at 65.8%,
    0.75-0.90 at 88.1%, at or above 0.90 at 99.9%. So a mapping under it is
    right about two times in three, and the claim reaches its mode carrying that
    fact for the operator to rank on.
    """
    vocab = _vocab(
        ("Type", "illumina library", 24, "DNA Extraction",
         2210, 2210, 0.706787, S.P_LEARNED),
        ("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
    )
    type_reg = {("DNA", 24): 500, ("D.IMG", 11): 500}
    types = {"DNA-1": "DNA", "D.IMG-1": "D.IMG"}
    claims = _claims(
        _claim(1, "DNA-1", 24, "DNA Extraction", "Type", "Illumina Library"),
        _claim(2, "D.IMG-1", 11, "Comet Chip", "Type", "CometChip"),
    )
    gated = G.gate_claims(claims, vocab, type_reg, types)

    assert list(gated.gate) == [S.GATE_LOW_SUPPORT, S.GATE_PASS]
    assert "purity" in gated.gate_reason.iloc[0]
    # neither support column can explain the mark, which is the point
    assert gated.vocab_support.iloc[0] == 2210
    assert gated.vocab_n_samples.iloc[0] == 2210
    assert G.MIN_VOCAB_PURITY == 0.75
    # MARKED, NOT STOPPED: both claims reach a mode, the first carrying its
    # purity failure. This is the assertion the old title lacked.
    assert list(G.reaches_modes(gated)) == [True, True]
    assert not G.blocks_mode(S.GATE_LOW_SUPPORT)


def test_the_defect_file_states_the_floors_the_run_applied_not_the_defaults():
    """One concept, one number, across the two frames a curator reads together.

    `vocabulary_defects` writes the floors into the `detail` a curator triages
    on and cannot see the arguments `gate_claims` was ruled under, so before
    this it interpolated the module constants: gating at 10 and 0.95 produced a
    per-claim reason naming 10 and 0.95 beside a defect row naming 3 and 0.75.
    Two numbers for one concept, one function apart, in the artifact the
    decision is made in.

    It was inert only because `main` took the defaults for both calls, and it
    was not going to stay inert -- `MIN_VOCAB_PURITY` commits Task 4 to
    re-deriving that floor, and a sweep at a new value is exactly the caller
    that sets one and not the other. So the floors are parameters here too, and
    `main` binds the pair once and hands the same two values to both.

    Asserted at NON-DEFAULT values, which is the only setting that can tell the
    passed number from the constant.
    """
    vocab = _vocab(("Type", "midling", 11, "Comet Chip", 800, 8, 0.90,
                    S.P_LEARNED))
    claims = _claims(_claim(1, "TIS-1", 11, "Comet Chip", "Type", "midling"))

    # clears both defaults, fails both of these
    gated = G.gate_claims(claims, vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"},
                          min_samples=10, min_purity=0.95)
    assert gated.gate.iloc[0] == S.GATE_LOW_SUPPORT
    assert "floor of 10" in gated.gate_reason.iloc[0]
    assert "floor of 0.95" in gated.gate_reason.iloc[0]

    defects = G.vocabulary_defects(gated, vocab, min_samples=10, min_purity=0.95)
    assert "10 samples and 0.95" in defects.detail.iloc[0]
    for stale in ("3 samples", "0.75"):
        assert stale not in defects.detail.iloc[0], (
            f"the defect row states {stale!r}, which is a module default and not"
            " the floor this run applied")

    # ...and at the defaults the two agree the other way, so the assertion above
    # is about the passed value rather than about the literal 10
    plain = G.gate_claims(claims, vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})
    assert plain.gate.iloc[0] == S.GATE_PASS
    assert G.vocabulary_defects(plain, vocab).empty


def test_a_curator_row_is_never_marked_low_support_whatever_its_support():
    """A human decision outranks the data, and the data outranks a guess.

    RENAMED from `..._never_gated_out_by_the_floors_...`, which overstated after
    ruling A: the floors gate nobody out any more, so what this exemption
    changes is the LABEL and nothing else. The body was always about the label
    and is unchanged; only the promise on the front of it was wrong.

    The fixture's `Instrument: curator call` sits at support 0, n_samples 0 and
    purity 0.0 -- below every floor there is, in either unit -- and must not be
    marked. `vocabulary.merge_vocabulary` already ranks curator above learned
    above proposed; a floor that marked it anyway would print "weak evidence"
    beside the one kind of row whose evidence is a person.

    The gate says so in the reason, because a PASS earned by provenance and a
    PASS earned by evidence are different facts and the artifact is read by the
    person who wrote the ruling.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    claims = _claims(_claim(202, "TIS-3", 11, "Comet Chip",
                            "Instrument", "curator call",
                            provenance=S.P_CURATOR))
    gated = G.gate_claims(
        claims, fx["vocabulary"],
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    assert gated.gate.iloc[0] == S.GATE_PASS
    assert gated.vocab_support.iloc[0] < G.MIN_VOCAB_SAMPLES
    assert gated.vocab_n_samples.iloc[0] < G.MIN_VOCAB_SAMPLES
    assert gated.vocab_purity.iloc[0] < G.MIN_VOCAB_PURITY
    assert "curator" in gated.gate_reason.iloc[0]

    # ...and a LEARNED row with those same numbers is rejected, or provenance
    # is not what carried it
    learned = fx["vocabulary"].copy()
    learned.loc[learned.raw_value == "curator call", "provenance"] = S.P_LEARNED
    again = G.gate_claims(
        _claims(_claim(202, "TIS-3", 11, "Comet Chip",
                       "Instrument", "curator call")),
        learned,
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    assert again.gate.iloc[0] == S.GATE_LOW_SUPPORT


def test_a_curator_row_inside_a_split_family_still_reaches_its_mode():
    """The only curator branch that still changes PASSAGE, and it had no test.

    After ruling A the floors block nobody, so exempting a curator row from them
    moves a label. The exemption from the FAMILY test is different in kind:
    `GATE_INCOHERENT` blocks, so this branch is the one deciding whether a
    curator's own claim reaches a mode at all. It was untested. The existing
    curator case uses `Instrument: curator call`, which belongs to no family,
    and the shared fixture's one incoherent family carries no curator row, so an
    edit reordering the curator check below the family test would have started
    silently blocking curator claims with the whole suite green.

    Built by appending one row to the fixture's vocabulary rather than by
    editing `make_fixture`, whose contents are pinned by
    `tests/test_assay_hygiene_schema.py`. Two properties keep the case honest:

    * the split is carried by the two pre-existing LEARNED members, so the
      family is incoherent with or without the curator row. Otherwise the test
      could pass because there was no family left rather than because the
      exemption works.
    * the curator row names an assay TIS samples ARE registered in. A first
      draft pointed it at 13 Patient Visit, which no TIS holds, and the claim
      came back `GATE_UNREACHABLE` -- correct behaviour, and it would have
      tested reachability while claiming to test the family exemption.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    vocab = pd.concat(
        [fx["vocabulary"],
         _vocab(("Software", "cometchip v3", 11, "Comet Chip",
                 0, 0, 0.0, S.P_CURATOR))],
        ignore_index=True,
    )
    # the family is split by the learned members alone, and the curator row
    # joins that same family
    assert G.incoherent_families(fx["vocabulary"]) == {
        ("Software", "cometchip"): [11, 12]}
    assert G.incoherent_families(vocab) == {("Software", "cometchip"): [11, 12]}
    assert G.term_stem("cometchip v3") == "cometchip"

    claims = _claims(
        _claim(202, "TIS-3", 11, "Comet Chip", "Software", "cometchip v3",
               provenance=S.P_CURATOR),
        # the learned member of the SAME family, which must still be blocked
        _claim(202, "TIS-3", 11, "Comet Chip", "Software", "cometchip"),
    )
    gated = G.gate_claims(
        claims, vocab,
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    assert list(gated.gate) == [S.GATE_PASS, S.GATE_INCOHERENT]
    assert list(gated.gate_failures) == ["", S.GATE_INCOHERENT]
    assert list(G.reaches_modes(gated)) == [True, False]
    assert "curator" in gated.gate_reason.iloc[0]


def test_a_curator_row_is_still_subject_to_reachability():
    """The exemption is scoped to what a ruling can actually speak about.

    A curator ruling says what a TERM means. It says nothing about whether a
    sample of this type belongs in that assay, which is a fact about the
    database's registrations and not about the vocabulary. So `P_CURATOR`
    exempts a row from the family test and from both floors -- all three are
    judgments about the mapping's evidence -- and never from reachability.
    Exempting it there would let a single ruling authorise a proposal for a
    (type, assay) pair that exists nowhere, which is the 13 A.SPC shape.
    """
    vocab = _vocab(("Type", "rare term", 130, "Mass Spectrometry",
                    0, 0, 0.0, S.P_CURATOR))
    claims = _claims(_claim(1, "A.SPC-1", 130, "Mass Spectrometry",
                            "Type", "rare term", provenance=S.P_CURATOR))
    gated = G.gate_claims(claims, vocab, {("A.SPC", 47): 90},
                          {"A.SPC-1": "A.SPC"})
    assert gated.gate.iloc[0] == S.GATE_UNREACHABLE


# --- grain, precedence and contract ------------------------------------------


def test_outcomes_are_per_claim_not_per_sample():
    """A sample with one good and one bad claim keeps the good one.

    Increment 1's collapses ran the other way -- a per-sample tier made a
    second claim lower the first one's tier and measurably deleted 102 existing
    flags -- so the grain is asserted rather than assumed. One sample, two
    claims naming two different assays, one reachable and one not.
    """
    vocab = _vocab(
        ("Type", "good", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
        ("Instrument", "bad", 99, "Nowhere", 900, 850, 0.99, S.P_LEARNED),
    )
    claims = _claims(
        _claim(1, "TIS-1", 11, "Comet Chip", "Type", "good"),
        _claim(1, "TIS-1", 99, "Nowhere", "Instrument", "bad"),
    )
    gated = G.gate_claims(claims, vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})

    assert list(gated.sample_id) == [1, 1]
    assert list(gated.gate) == [S.GATE_PASS, S.GATE_UNREACHABLE]
    assert list(G.reaches_modes(gated)) == [True, False]


def test_reachability_is_evaluated_before_the_family_and_the_floors():
    """Order matters and is a contract.

    Increment 1's precedence ran lineage first with no reachability test at
    all, and that is what let 24 vocabulary defects be filed as lineage
    absences. A claim failing two tests at once must report the FIRST one, so a
    bucket is named for the test that caught it and not for whichever branch
    happened to run last. One claim here fails all three.
    """
    vocab = _vocab(
        ("Software", "flowjo", 30, "Flow Cytometry", 4, 1, 0.5, S.P_LEARNED),
        ("Software", "flowjo v10", 31, "Flow Cytometry Analysis",
         600, 90, 1.0, S.P_LEARNED),
    )
    claims = _claims(_claim(1, "A.SPC-1", 30, "Flow Cytometry",
                            "Software", "flowjo"))
    gated = G.gate_claims(claims, vocab, {}, {"A.SPC-1": "A.SPC"})
    assert gated.gate.iloc[0] == S.GATE_UNREACHABLE

    # reachable, and the family still outranks the floors
    gated = G.gate_claims(claims, vocab, {("A.SPC", 30): 12},
                          {"A.SPC-1": "A.SPC"})
    assert gated.gate.iloc[0] == S.GATE_INCOHERENT


def test_the_gate_frame_matches_its_contract_and_emits_only_closed_outcomes():
    """One row per input claim, in order, and every `gate` value is in the family.

    The row count and order matter because Modes 1 and 2 exclude a rejected
    claim by lining this frame up against the claims frame; a gate that dropped
    or reordered rows would silently exclude the wrong ones.
    """
    claims, vocab, type_reg, types = _world()
    gated = G.gate_claims(claims, vocab, type_reg, types)

    assert list(gated.columns) == G.GATE_COLUMNS
    assert len(gated) == len(claims)
    assert list(gated.sample_id) == list(claims.sample_id)
    assert list(gated.internal_assay_id) == list(claims.internal_assay_id)
    assert set(gated.gate) <= set(S.GATE_OUTCOMES)
    # a PASS states no failure; every rejection states one
    for g, why in zip(gated.gate, gated.gate_reason):
        if g in S.GATE_REJECTIONS:
            assert why, f"{g} with no reason"
    # `gate` is the FIRST entry of `gate_failures`, and a clean claim lists none
    for g, failures in zip(gated.gate, gated.gate_failures):
        listed = [f for f in failures.split(";") if f]
        assert set(listed) <= set(S.GATE_REJECTIONS)
        assert (listed[0] if listed else S.GATE_PASS) == g
        assert (g == S.GATE_PASS) == (not listed)


def test_only_the_two_evidence_backed_outcomes_block_a_claim():
    """The blocking rule, at the predicate, over the whole closed family.

    Reachability and coherence carry no tuned number: either a sample of this
    type is registered in the claimed assay somewhere or it is not, and either
    the term family maps coherently or it does not. Neither answer moves if
    somebody picks a different constant, so they may stop a claim.

    Both floors ARE tuned numbers and neither may. "Nothing decides, everything
    proposes" is binding and a threshold that blocks is a threshold that
    decides; the spec also holds a threshold to be the OUTPUT of a backtest
    curve, and both of these were chosen ahead of one.

    Enumerated over `GATE_OUTCOMES` rather than spot-checked, so an outcome
    added later has to be classified here rather than defaulting into blocking
    by being forgotten.
    """
    assert set(G.BLOCKING_OUTCOMES) == {S.GATE_UNREACHABLE, S.GATE_INCOHERENT}
    assert set(G.BLOCKING_OUTCOMES) < set(S.GATE_REJECTIONS)
    for outcome in S.GATE_OUTCOMES:
        assert G.blocks_mode(outcome) is (outcome in G.BLOCKING_OUTCOMES)
    assert not G.blocks_mode(S.GATE_LOW_SUPPORT)
    assert not G.blocks_mode(S.GATE_PASS)
    # anything unanticipated defaults to NON-blocking, which fails visibly
    assert not G.blocks_mode("GATE_SOMETHING_ADDED_LATER")


def test_a_tuned_floor_is_recorded_on_the_row_and_does_not_stop_it():
    """The behaviour change ruled on 2026-08-17. It ranks; it does not decide.

    Both floors fire here -- 1 distinct sample at purity 0.40, under a floor of
    3 and one of 0.75 -- and the claim still reaches its mode. What must NOT
    happen alongside that is the weakness going unrecorded: the outcome, both
    reasons and the two evidence columns are all still on the row, because a
    Task 4 operator ranks on them and a silently-clean row is worse than a
    blocked one.
    """
    vocab = _vocab(("Type", "thin", 11, "Comet Chip", 132, 1, 0.40, S.P_LEARNED))
    claims = _claims(_claim(1, "TIS-1", 11, "Comet Chip", "Type", "thin"))
    gated = G.gate_claims(claims, vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})

    assert gated.gate.iloc[0] == S.GATE_LOW_SUPPORT
    assert G.reaches_modes(gated).iloc[0], "a tuned floor must not block"
    # ...and it is recorded, in both units, with both reasons
    assert gated.gate_failures.iloc[0] == S.GATE_LOW_SUPPORT
    assert gated.vocab_n_samples.iloc[0] == 1
    assert gated.vocab_purity.iloc[0] == 0.40
    assert "sample" in gated.gate_reason.iloc[0]
    assert "purity" in gated.gate_reason.iloc[0]

    # the defect is still routed to the curator, marked as having blocked nothing
    defects = G.vocabulary_defects(gated, vocab)
    assert list(defects.defect) == [S.GATE_LOW_SUPPORT]
    assert list(defects.blocks_modes) == [False]


def test_a_claim_failing_a_blocking_and_a_tuned_test_carries_both():
    """One claim, two defects, and neither may hide the other.

    Measured on the real extract, 3,511 of the 138,007 claims are in this state.
    An earlier revision reported only the most severe, so a blocked claim's
    finding row showed a clean mapping for a mapping that is not clean -- and a
    curator fixing the reachability problem would have been handed a term still
    resting on one sample, with nothing anywhere saying so.

    The negative half is asserted too: the tuned failure must not turn a
    passing claim's neighbour into a blocked one, so a sibling claim failing
    ONLY the floor reaches its mode in the same frame.
    """
    vocab = _vocab(
        ("Type", "thin", 99, "Nowhere", 132, 1, 1.0, S.P_LEARNED),
        ("Instrument", "alsothin", 11, "Comet Chip", 132, 1, 1.0, S.P_LEARNED),
    )
    claims = _claims(
        _claim(1, "TIS-1", 99, "Nowhere", "Type", "thin"),
        _claim(1, "TIS-1", 11, "Comet Chip", "Instrument", "alsothin"),
    )
    gated = G.gate_claims(claims, vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})

    both = gated.iloc[0]
    assert both.gate_failures == f"{S.GATE_UNREACHABLE};{S.GATE_LOW_SUPPORT}"
    assert both.gate == S.GATE_UNREACHABLE          # the most severe
    assert "not credible" in both.gate_reason and "sample" in both.gate_reason
    assert list(G.reaches_modes(gated)) == [False, True]

    # both defects reach the curator's file, from the one claim
    defects = G.vocabulary_defects(gated, vocab)
    thin = defects[defects.raw_value == "thin"]
    assert set(thin.defect) == {S.GATE_UNREACHABLE, S.GATE_LOW_SUPPORT}
    assert set(thin.blocks_modes) == {True, False}
    assert set(thin.n_claims) == {1}


def test_an_unresolvable_claim_raises_rather_than_being_skipped():
    """`precedent.mine_precedent` and `audit.registered_internal` both raise here.

    Skipping is worse than failing in both directions. A claim whose term has
    no vocabulary row cannot be gated, and dropping it removes a row Modes 1
    and 2 would otherwise have proposed on -- silently, with no count anywhere.
    A claim whose uuid has no type cannot be tested for reachability and would
    read as PASS, which is the laundering this gate exists to stop. Measured on
    the real extract, 0 of the 138,007 claims hit either, so both are guards on
    a property that holds today rather than on one that does not.
    """
    vocab = _vocab(("Type", "good", 11, "Comet Chip", 900, 850, 0.99,
                    S.P_LEARNED))
    with pytest.raises(ValueError, match="vocabulary"):
        G.gate_claims(
            _claims(_claim(1, "TIS-1", 11, "Comet Chip", "Type", "unknown")),
            vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})

    with pytest.raises(ValueError, match="type"):
        G.gate_claims(
            _claims(_claim(1, "TIS-9", 11, "Comet Chip", "Type", "good")),
            vocab, {("TIS", 11): 40}, {"TIS-1": "TIS"})


def test_the_gate_mutates_neither_the_claims_frame_nor_the_vocabulary_frame():
    """Read-only, asserted on the frames and then on the files.

    The gate is the one stage that runs before everything, so a frame it
    quietly normalised in place would change what every later stage reads. The
    file half is the one that matters operationally: `main` reads
    `claims.parquet` and `vocabulary.csv` and writes exactly one new artifact.
    """
    claims, vocab, type_reg, types = _world()
    before_claims, before_vocab = claims.copy(deep=True), vocab.copy(deep=True)
    G.gate_claims(claims, vocab, type_reg, types)
    pd.testing.assert_frame_equal(claims, before_claims)
    pd.testing.assert_frame_equal(vocab, before_vocab)


def test_main_writes_one_artifact_and_leaves_its_inputs_byte_identical(tmp_path,
                                                                      plugin_sentinel):
    """The whole command, on the fixture, in a directory of its own.

    `plugin_sentinel` is the P1 guard: nothing may be created inside the plugin
    checkout, and a driver that defaulted its output path into the repo is
    exactly the failure it catches.

    THE INPUTS ARE MADE READ-ONLY, and the digests alone are not enough. Self
    review caught this: `save_vocabulary` round-trips byte-identically, so a
    `main` that rewrote `vocabulary.csv` on the way through passed the hash
    check and the title's promise held only by luck of the serialiser. The mode
    bits make it structural -- the file is an INPUT, so a write of any kind
    raises rather than being judged by whether it happened to preserve bytes.
    The digests stay, because they are what catches a write through a path the
    mode bits do not cover.
    """
    fx = S.make_fixture()
    extract, out = tmp_path / "extract", tmp_path / "out"
    extract.mkdir()
    out.mkdir()
    for name in ("membership", "assays"):
        fx[name].to_parquet(extract / f"{name}.parquet", index=False)
    _nodes(fx).to_parquet(extract / "nodes.parquet", index=False)
    claims, vocab, _, _ = _world(fx)
    # A BOUNDARY TERM, appended here and not to the shared fixture: n_samples 8
    # at purity 0.90 clears (3, 0.75) and fails (10, 0.95). Without one, every
    # term in this world is ruled the same way at both settings, so `main`
    # threading the floors to only ONE of its two callees is invisible -- which
    # it was, until this row existed.
    vocab = pd.concat(
        [vocab, _vocab(("Type", "midling", 11, "Comet Chip",
                        800, 8, 0.90, S.P_LEARNED))],
        ignore_index=True,
    )
    claims = pd.concat(
        [claims, _claims(_claim(202, "TIS-3", 11, "Comet Chip",
                                "Type", "midling"))],
        ignore_index=True,
    )
    claims.to_parquet(out / "claims.parquet", index=False)
    V.save_vocabulary(vocab, out / "vocabulary.csv")

    digests = {p: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (out / "claims.parquet", out / "vocabulary.csv")}
    for p in digests:
        p.chmod(0o444)
    assert G.main(str(extract), str(out)) == 0

    defects = out / "vocabulary-defects.csv"
    assert defects.exists()
    assert list(pd.read_csv(defects).columns) == G.DEFECT_COLUMNS
    assert sorted(p.name for p in out.iterdir()) == [
        "claims.parquet", "vocabulary-defects.csv", "vocabulary.csv"]
    for p, digest in digests.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, f"{p} changed"

    # at the defaults the boundary term is clean and reaches no defect row
    assert "midling" not in set(pd.read_csv(defects).raw_value)

    # ...and the same run at NON-DEFAULT floors both RULES and REPORTS at them.
    # `main` binds the pair once and hands it to both `gate_claims` and
    # `vocabulary_defects`; threading it to either one alone passes every
    # assertion above, because at the defaults the two agree.
    assert G.main(str(extract), str(out), 10, 0.95) == 0
    tightened = pd.read_csv(defects)
    detail = " ".join(tightened.detail.astype(str))
    assert "10 samples and 0.95" in detail
    assert "3 samples and 0.75" not in detail, (
        "the file states the module defaults, not the floors this run applied")
    # the ruling moved too, not only the text describing it
    assert "midling" in set(tightened.raw_value), (
        "gate_claims ruled at the defaults while the file reports the tightened"
        " floors")


def test_the_defect_file_routes_to_vocabulary_curation_and_never_to_a_mode():
    """The gate produces no membership change, so its artifact carries none.

    Every defect names a vocabulary row a curator can fix, and no column here
    can express "add this sample to this assay". That is checked structurally
    against `FINDING_COLUMNS`, which is the shape a mode's proposal takes: the
    two frames share only the columns that mean the same thing in both.
    """
    fx = S.make_fixture()
    nodes = _nodes(fx)
    claims = _claims(
        _claim(301, "DNA-2", 11, "Comet Chip", "Type", "CometChip"),
        _claim(202, "TIS-3", 11, "Comet Chip", "Software", "cometchip"),
        _claim(203, "TIS-4", 11, "Comet Chip", "Type", "rare term"),
    )
    gated = G.gate_claims(
        claims, fx["vocabulary"],
        G.type_registration_index(fx["membership"], fx["assays"], nodes),
        G.sample_type_index(nodes),
    )
    defects = G.vocabulary_defects(gated, fx["vocabulary"])

    assert set(defects.defect) == set(S.GATE_REJECTIONS)
    assert list(defects.columns) == G.DEFECT_COLUMNS
    assert not ({"proposed_internal_assay_id", "mode", "action", "lineage"}
                & set(G.DEFECT_COLUMNS))
    # the unreachable defect is keyed on the (type, assay) pair, because that
    # and not the term is what is not credible
    un = defects[defects.defect == S.GATE_UNREACHABLE]
    assert list(un.sample_type) == ["DNA"]
    assert list(un.example_uuids) == ["DNA-2"]
    # the floor defect is keyed on the vocabulary row and carries no type
    floor = defects[defects.defect == S.GATE_LOW_SUPPORT]
    assert list(floor.raw_value) == ["rare term"]
    assert not floor.sample_type.iloc[0]


# --- the real extract --------------------------------------------------------


def test_the_24_flowjo_and_mass_spectra_rows_are_all_rejected_by_the_gate():
    """The acceptance test for this task, on today's real data.

    24 rows of increment 1's 866 are vocabulary defects that lineage precedence
    filed as `ABSENCE_LINEAGE` future write candidates:

      11  A.FLOW registered in 31 Flow Cytometry ANALYSIS, claiming 30 Flow
          Cytometry, through the `Software: flowjo` family that splits 30 / 31 /
          153 across six terms
      13  A.SPC registered in 47 Mass Spectrometry ANALYSIS, claiming 130 Mass
          Spectrometry, an assay NO A.SPC sample is registered in anywhere

    Both are the analysis-versus-measurement pair. If they still pass the gate,
    the gate does not work, whatever the aggregate numbers say -- so this test
    asserts the population size first (or it could pass vacuously on an empty
    filter) and then that not one of them reaches a mode.
    """
    if not (EXTRACT / "assays.parquet").exists():
        pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    if not (ARTIFACTS / "claims.parquet").exists():
        pytest.skip("no claims.parquet; run run_evidence.py first")

    membership = pd.read_parquet(EXTRACT / "membership.parquet")
    assays = pd.read_parquet(EXTRACT / "assays.parquet")
    nodes = pd.read_parquet(EXTRACT / "nodes.parquet")
    claims = pd.read_parquet(ARTIFACTS / "claims.parquet")
    vocab = V.load_vocabulary(ARTIFACTS / "vocabulary.csv")

    flags = A.audit_contradictions(claims, membership, assays, nodes)
    twenty_four = flags[
        ((flags.sample_type == "A.FLOW")
         & (flags.claimed_internal_assay_id == 30)
         & (flags.registered_internal_assay_ids == "31"))
        | ((flags.sample_type == "A.SPC")
           & (flags.claimed_internal_assay_id == 130)
           & (flags.registered_internal_assay_ids == "47"))]
    assert len(twenty_four) == 24, "the population moved; re-measure before editing"

    gated = G.gate_claims(
        claims, vocab,
        G.type_registration_index(membership, assays, nodes),
        G.sample_type_index(nodes),
    )
    keyed = gated.set_index(["sample_id", "internal_assay_id"])
    verdicts = keyed.loc[
        list(zip(twenty_four.sample_id, twenty_four.claimed_internal_assay_id))]
    assert set(verdicts.gate) <= set(S.GATE_REJECTIONS), (
        f"{verdicts.gate.value_counts().to_dict()} -- the gate does not work")
    assert not G.reaches_modes(verdicts).any()

    # ...and each is caught by the test that names its actual defect
    by_type = dict(zip(verdicts.sample_type, verdicts.gate))
    assert by_type["A.FLOW"] == S.GATE_INCOHERENT
    assert by_type["A.SPC"] == S.GATE_UNREACHABLE


def test_a_claim_surviving_from_before_a_retirement_raises_rather_than_passing():
    """The run-order guard for the first curator retirement.

    `run_evidence` writes both `vocabulary.csv` and `claims.parquet`, and
    `run_detect` reads both. Retiring `DataType/tif` and re-running only the
    second stage leaves 4,750 claims on disk that name a term the vocabulary no
    longer maps -- the exact shape this raise exists for, and the reason the
    handoff's instruction is "re-run run_evidence THEN run_detect" rather than
    either order.

    What makes it worth a test is the alternative. `_vocab_index` skips a null
    `internal_assay_id`, so the retired row is absent from the index rather
    than present-and-empty, and a `gate_claims` that skipped an unindexed key
    instead of raising would drop all 4,750 from Modes 1 and 2 with no count
    anywhere -- a stale-input error reading as a clean run that found less.
    """
    vocab = _vocab(("DataType", "tif", None, None, 0, 0, 0.0, S.P_CURATOR))
    stale = _claims(_claim(1, "D.IMG-1", 138, "CometChip Assay",
                           "DataType", "tif"))
    with pytest.raises(ValueError, match="no vocabulary row"):
        G.gate_claims(stale, vocab, {("D.IMG", 138): 50}, {"D.IMG-1": "D.IMG"})


def test_a_retired_term_is_skipped_by_every_vocabulary_reader_not_just_one():
    """`_maps_an_assay` is the ONE policy, and a retirement is what exercises it.

    Its docstring calls the null case "unreachable on the 2026-08-14 extract:
    0 of 736 vocabulary rows carry a null". The first curator file makes it
    reachable, so the three readers that disagreed before it existed --
    `_vocab_index`, `term_families` and `vocabulary_defects` -- are asserted
    here to agree on the same row rather than left to the comment.
    """
    vocab = _vocab(("DataType", "tif", None, None, 0, 0, 0.0, S.P_CURATOR),
                   ("DataType", "tiff", 145, "Histopathology",
                    53, 53, 0.962264, S.P_LEARNED))
    assert ("DataType", "tif") not in G._vocab_index(vocab)
    assert ("DataType", "tiff") in G._vocab_index(vocab)
    # no family anywhere carries the retired row, which is what `term_families`
    # got right while the two indexes got it wrong
    assert not any(pd.isna(r.internal_assay_id)
                   for fam in G.term_families(vocab).values() for r in fam)
    assert ("DataType", G.term_stem("tiff")) in G.term_families(vocab)
    # and the defect report cannot crash on it, which is how the old asymmetry
    # surfaced: one reader kept the null and fed it to `int()`
    gated = G.gate_claims(
        _claims(_claim(1, "TIS-1", 145, "Histopathology", "DataType", "tiff")),
        vocab, {("TIS", 145): 50}, {"TIS-1": "TIS"})
    defects = G.vocabulary_defects(gated, vocab)
    assert "tif" not in set(defects.raw_value)
