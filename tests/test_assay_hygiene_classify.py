# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Task 5: Mode 1 -- a sample registered in NO assay, and what proposes one.

WHY THIS FILE EXISTS. The operator's first question is "what samples have no
assays and need some". Metadata is the only evidence available for such a
sample: it has no membership to reason from and, under the precedence contract,
Mode 1 is settled before the lineage and co-registration tests run at all. So a
Mode 1 row is exactly as good as its vocabulary row, which is why the gate runs
in front of it.

THE POPULATION IS 6,242 AND NOT 6,324, and the 82 between them is this branch's
most expensive defect. "Registered" means ANY membership row. The MAPPABLE-only
reading -- drop the registrations that resolve through one of the 17 assays with
no junction row -- is 82 samples larger, and every one of those 82 IS registered;
only the INTERNAL IDENTITY of its assay is unknown. Proposing a first assay for
a sample that already has one is not a smaller error than missing one, and the
same confusion has already produced a wrong Mode 2 ceiling on this branch.
`test_a_sample_registered_only_through_a_junction_less_assay_is_not_mode_1`
simulates the wrong rule by hand and asserts the two answers DIFFER.

PASSAGE IS `gate.reaches_modes` AND NEVER `gate == GATE_PASS`. The two floors are
tuned numbers, so they are RECORDED on the row and do not block; reachability and
coherence rest on evidence with no tuned number in them, and they do. Reading
passage off the `gate` column instead drops 25,974 claims across the package and
one row here, and
`test_a_claim_under_a_tuned_floor_still_reaches_mode_1_carrying_its_gate_outcome`
is the regression for it.

EVERY GUARD READS ITS EXPECTED VALUE OFF THE FRAME AND ALSO SIMULATES THE WRONG
RULE BY HAND, following `tests/test_assay_hygiene_compatibility.py`. Six mutation
harnesses on this branch have produced false results and two regression tests
shipped unable to discriminate the bug they were written to catch. A test that
asserts a count proves only that the code produced that count; a test that also
computes what the rule it exists to reject would have produced, and asserts the
two DIFFER, proves the rule under test is the one running.
"""
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import audit as A  # noqa: E402
from assay_hygiene import claims as C  # noqa: E402
from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"

# The two id spaces are kept VISIBLY apart, as in
# `tests/test_assay_hygiene_compatibility.py`: a seek `assays.id` is the internal
# id plus 1000, so a test or an implementation reading `membership.assay_id` as an
# internal id looks up an assay in the 1000s and finds nothing instead of finding
# a populated, wrong cell.
SEEK_OFFSET = 1000

# The junction-less assay. It carries a NULL `internal_assay_id`, so
# `precedent.assay_index` falls back to its own seek id -- a value in the SEEK id
# space wearing an internal id's column. 490 collides with no genuine internal id
# here (11, 12, 13), which is the invariant `assay_index` raises on.
JUNCTIONLESS_SEEK_ID = 490


# --- the world ---------------------------------------------------------------


def _world():
    """One synthetic world, hand-traced, and every count below is derived here.

    Assays.  internal 11, 12, 13 fully junctioned (seek 1011/1012/1013), plus
             seek 490 with NO junction row, which falls back to internal id 490.

    Background, registered and claiming nothing, so the reachability cells are
    non-empty and the DNA rejections below are about the TYPE and not about an
    unknown term:

        1-5    TIS in 11
        6-8    TIS in 12
        9-10   TIS in 13

    The reachability cells that result, counting DISTINCT samples of the type
    and re-derived here rather than copied off the block above, because 101 and
    102 below are also TIS and also registered:

        pop(TIS, 11) = 5     1-5
        pop(TIS, 12) = 4     6-8 and 102
        pop(TIS, 13) = 2     9-10
        pop(TIS, 490) = 1    101, through the junction-less assay

        NO DNA SAMPLE IS REGISTERED ANYWHERE, so every (DNA, assay) cell is 0
        and every DNA claim below is GATE_UNREACHABLE. 999 has no node row, so
        it carries no type and contributes to no cell at all.

    Registered, and therefore NOT Mode 1's population however loudly their
    metadata claims:

        101    TIS, registered ONLY through seek 490 -- the 82-sample case
        102    TIS, registered in 12, claiming 11
        999    a membership row for a sample_id absent from the samples frame,
               the shape of the real extract's 362. It is registered, it is not
               in the population, and it is counted BY NAME rather than dropped.

    The population, registered in nothing (10 samples):

        100    Type alpha -> 11          strong, passes           1 row
        103    no term maps              no claim at all          0 rows
        104    DNA, Type alpha -> 11     GATE_UNREACHABLE         1 row, blocked
        105    Type alpha -> 11, Instrument beta -> 12,
               Software epsilon -> 13    contested, all pass      3 rows
        106    Protocol gamma -> 11      weak, passes             1 row
        107    Type delta -> 12          GATE_LOW_SUPPORT, passes 1 row
        108    Type zeta -> 13, Instrument beta -> 12
                                         contested, both pass     2 rows
        109    DNA, three claims         all GATE_UNREACHABLE     3 rows, blocked
        111    no term maps              no claim at all          0 rows
        112    no term maps              no claim at all          0 rows

    THE FRAME IS DELIBERATELY OUT OF ORDER IN BOTH KEYS, or the emitted sort is
    a no-op and the assertion on it is vacuous. 100 is added LAST, so the claims
    frame -- and therefore the gate frame and the attached frame, both of which
    preserve its order -- ends with the lowest sample id in the population; and
    108's strong fields resolve to 13 before 12, because `CLAIM_FIELDS` puts
    `Type` ahead of `Instrument` and `zeta` names the higher assay. Every other
    sample here would arrive already sorted in both keys.

    The census, hand-traced off the table above and re-derived by
    `test_the_census_partitions_the_population_and_names_every_excluded_sample`:

        population                     10   = 3 + 7
        population_no_claim             3   103, 111, 112
        population_with_claim           7
        claim_rows                     12   = 4 + 8
        claim_rows_blocked              4   104 (1) + 109 (3)
        claim_rows_proposed             8   100 (1) + 105 (3) + 106 (1)
                                            + 107 (1) + 108 (2)
        population_all_claims_blocked   2   104, 109
        population_proposed             5   100, 105, 106, 107, 108

    ALL EIGHT COUNTS ARE DISTINCT, which is deliberate. Task 4's review found a
    census world whose buckets could be swapped without changing a number, so a
    collapse mutant was byte-identical to the correct rule. Two buckets holding
    the same value cannot discriminate a rule that confuses them.

    project_ids are set so the three real shapes appear: a plain single id, the
    comma-joined multi-project form (108 carries "6,2", which is 1,052 of the
    real population), a DUPLICATED id (105 carries "2,2", which occurs 34 times),
    and a NULL (106, which is 193 of the real population).
    """
    nodes, membership, samples = [], [], []

    def add(sid, stype, meta, projects="3", assay_ids=()):
        nodes.append((f"{stype}-{sid}", sid, stype))
        samples.append((sid, f"{stype}-{sid}", meta, None, projects))
        for a in assay_ids:
            membership.append((sid, a))

    for sid in range(1, 6):
        add(sid, "TIS", "{}", assay_ids=[11 + SEEK_OFFSET])
    for sid in range(6, 9):
        add(sid, "TIS", "{}", assay_ids=[12 + SEEK_OFFSET])
    for sid in range(9, 11):
        add(sid, "TIS", "{}", assay_ids=[13 + SEEK_OFFSET])

    add(101, "TIS", '{"Type": "alpha"}', assay_ids=[JUNCTIONLESS_SEEK_ID])
    add(102, "TIS", '{"Type": "alpha"}', assay_ids=[12 + SEEK_OFFSET])

    add(103, "TIS", '{"Name": "nothing maps"}')
    add(104, "DNA", '{"Type": "alpha"}')
    add(105, "TIS",
        '{"Type": "alpha", "Instrument": "beta", "Software": "epsilon"}',
        projects="2,2")
    add(106, "TIS", '{"Protocol": "gamma"}', projects=None)
    add(107, "TIS", '{"Type": "delta"}')
    add(108, "TIS", '{"Type": "zeta", "Instrument": "beta"}', projects="6,2")
    add(109, "DNA",
        '{"Type": "alpha", "Instrument": "beta", "Software": "epsilon"}')
    add(111, "TIS", '{"Name": "nothing maps"}')
    add(112, "TIS", '{"Name": "nothing maps"}')
    # LAST, and the lowest id in the population: see the docstring on ordering
    add(100, "TIS", '{"Type": "alpha"}')

    # registered, and absent from the samples frame: the real extract's 362
    membership.append((999, 11 + SEEK_OFFSET))

    assays = pd.DataFrame(
        [(11 + SEEK_OFFSET, "Assay 11", 3, 2, 1, 10, "P", 11, "Assay 11"),
         (12 + SEEK_OFFSET, "Assay 12", 3, 2, 1, 10, "P", 12, "Assay 12"),
         (13 + SEEK_OFFSET, "Assay 13", 3, 2, 1, 10, "P", 13, "Assay 13"),
         (JUNCTIONLESS_SEEK_ID, "Junctionless", 3, 2, 1, 10, "P", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    # Every value is already normalised: `normalise_value` is what each lookup
    # goes through, so a row spelled `Alpha` would match nothing.
    #
    # `delta` is the FLOOR case and it fails ONE test only -- 1 backing sample
    # against the floor of 3, at full purity, in a coherent family, naming an
    # assay TIS samples do hold. A claim failing two tests at once cannot show
    # which one caught it.
    vocabulary = pd.DataFrame(
        [("Type", "alpha", 11, "Assay 11", 900, 50, 0.99, S.P_LEARNED),
         ("Instrument", "beta", 12, "Assay 12", 300, 40, 0.95, S.P_LEARNED),
         ("Software", "epsilon", 13, "Assay 13", 200, 30, 0.98, S.P_LEARNED),
         ("Protocol", "gamma", 11, "Assay 11", 400, 60, 0.90, S.P_LEARNED),
         ("Type", "delta", 12, "Assay 12", 5, 1, 1.00, S.P_LEARNED),
         # names the HIGHER assay off the EARLIER strong field, so 108's two
         # claims arrive descending and the emitted sort has something to do
         ("Type", "zeta", 13, "Assay 13", 250, 35, 0.97, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    return {
        "nodes": pd.DataFrame(nodes, columns=S.NODES_COLUMNS),
        "membership": pd.DataFrame(membership, columns=S.MEMBERSHIP_COLUMNS),
        "samples": pd.DataFrame(samples, columns=S.SAMPLE_COLUMNS),
        "assays": assays,
        "vocabulary": vocabulary,
    }


def _pipeline(w=None):
    """The world, gated and attached, plus the population and the findings.

    One helper so no test re-derives the wiring, and so a test naming a
    behaviour cannot accidentally exercise a different composition of the
    stages than its siblings do.
    """
    w = w or _world()
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    claims = C.sample_claims(meta, uuids, w["vocabulary"])
    type_reg = G.type_registration_index(w["membership"], w["assays"], w["nodes"])
    gated = G.gate_claims(claims, w["vocabulary"], type_reg,
                          G.sample_type_index(w["nodes"]))
    attached = X.attach_gate(claims, gated)
    population = X.unregistered_samples(w["samples"], w["membership"], w["assays"])
    findings = X.mode1_findings(attached, population,
                                X.project_index(w["samples"]))
    return w, claims, gated, attached, population, findings


# --- the population ----------------------------------------------------------


def test_a_sample_registered_in_nothing_with_a_gate_passing_claim_becomes_a_mode_1_proposal():
    """Sample 100: no membership row, one strong claim, one row proposing it.

    The row's registered side is EMPTY STRING and not null, and the difference
    is the whole point of Mode 1: the sample's registrations were measured and
    there are none. A null there would say the question was never asked.
    """
    _, _, _, _, _, findings = _pipeline()

    rows = findings[findings.sample_id == 100]
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["mode"] == S.MODE_1
    assert row.action == S.A_ADD_TO_ASSAY
    assert row.proposed_internal_assay_id == 11
    assert row.proposed_internal_assay_title == "Assay 11"
    assert row.claim_tier == S.T_STRONG
    assert row.gate == S.GATE_PASS
    assert row.proposed_by == X.BY_CLAIM
    assert row.uuid == "TIS-100" and row.sample_type == "TIS"
    # measured and empty, never "not measured"
    assert row.registered_internal_assay_ids == ""
    assert row.registered_internal_assay_titles == ""


def test_a_sample_registered_only_through_a_junction_less_assay_is_not_mode_1():
    """The 82-sample case. ANY membership row means registered.

    Sample 101 holds one membership row, naming an assay with no junction row.
    Crossed through `assay_index` that resolves to a SEEK id wearing an internal
    id's column, so its assay's internal identity is UNKNOWN -- not absent. It
    claims 11 and would be a perfectly plausible-looking Mode 1 proposal, which
    is exactly why it must not be one: the proposal would be a FIRST assay for a
    sample that already has one.

    The wrong rule -- registered means holding a MAPPABLE registration -- is
    simulated here and asserted to give a DIFFERENT answer, so this test cannot
    pass under it.
    """
    w, _, _, _, population, findings = _pipeline()

    assert 101 not in population
    assert 101 not in set(findings.sample_id)
    # ...and it claims something, so its absence is a ruling and not a vacuum
    assert 101 in set(
        C.sample_claims(V.parse_metadata(w["samples"]),
                        dict(zip(w["samples"].sample_id.astype(int),
                                 w["samples"].uuid)),
                        w["vocabulary"]).sample_id)

    # THE WRONG RULE, run by hand: drop registrations resolving to a fallback id
    from assay_hygiene.precedent import fallback_assay_ids
    registered = A.registered_internal(w["membership"], w["assays"])
    unmappable = fallback_assay_ids(w["assays"])
    mappable_only = {
        int(s) for s in w["samples"].sample_id
        if not (registered.get(int(s), set()) - unmappable)
    }
    assert 101 in mappable_only, "the wrong rule must reach 101 or it proves nothing"
    assert mappable_only != set(population)
    assert sorted(mappable_only - set(population)) == [101]


def test_a_sample_registered_in_any_assay_never_reaches_mode_1():
    """Sample 102 is in 12 and claims 11. That is Mode 2's or Mode 3's question.

    Read off the frame rather than asserted as a literal: every sample carrying
    a membership row is absent from both the population and the findings.
    """
    w, _, _, _, population, findings = _pipeline()

    registered = set(int(s) for s in w["membership"].sample_id)
    assert 102 in registered
    assert not (registered & set(population))
    assert not (registered & set(findings.sample_id))


def test_a_sample_registered_in_nothing_with_no_claim_is_counted_not_dropped():
    """Samples 103, 111 and 112 propose nothing, so nothing proposes for them.

    They are the largest slice of Mode 1's population by far -- 4,415 of the
    real 6,242 -- and reporting a mode's coverage without them would quote the
    numerator as the population.
    """
    _, _, _, attached, population, findings = _pipeline()

    census = X.mode1_census(attached, population, findings)
    silent = set(population) - set(attached.sample_id) - set(findings.sample_id)
    assert silent == {103, 111, 112}
    assert census["population_no_claim"] == len(silent) == 3
    assert not (silent & set(findings.sample_id))


# --- the gate runs first -----------------------------------------------------


def test_a_gate_blocked_claim_produces_no_mode_1_row_on_an_unregistered_sample():
    """104 and 109 are DNA, and no DNA sample is registered anywhere here.

    Their claims name assays that are credible for TIS and not for DNA, so
    reachability rejects them and reachability BLOCKS. Both samples are in the
    population; neither reaches a row.

    The wrong rule -- Mode 1 is the population crossed with its claims, gate
    ignored -- is simulated and asserted to give a different answer.
    """
    _, _, _, attached, population, findings = _pipeline()

    assert 104 in population and 109 in population
    blocked = attached[~G.reaches_modes(attached)]
    assert set(blocked.sample_id) == {104, 109}
    assert set(blocked.gate) == {S.GATE_UNREACHABLE}
    assert not ({104, 109} & set(findings.sample_id))

    # THE WRONG RULE: no gate at all
    ungated = attached[attached.sample_id.isin(population)]
    assert len(ungated) == 12
    assert len(findings) == 8
    assert set(ungated.sample_id) - set(findings.sample_id) == {104, 109}


def test_a_claim_under_a_tuned_floor_still_reaches_mode_1_carrying_its_gate_outcome():
    """Sample 107's mapping rests on ONE sample, under the floor of three.

    That is `GATE_LOW_SUPPORT`, which is the outcome of a tuned number, so it is
    RECORDED and does not block: under "nothing decides, everything proposes" a
    threshold ranks and triages and does not grant permission. The row reaches
    Mode 1 carrying the weakness an operator reads.

    The wrong rule -- passage is `gate == GATE_PASS` -- is simulated and drops
    this row. Across the package it drops 25,974 claims.
    """
    _, _, _, attached, _, findings = _pipeline()

    row = findings[findings.sample_id == 107].iloc[0]
    assert row.gate == S.GATE_LOW_SUPPORT
    assert not G.blocks_mode(row.gate)
    assert row.action == S.A_ADD_TO_ASSAY
    # the vocabulary row's own weakness rides onto the finding
    assert row.vocab_support == 5 and row.vocab_purity == 1.0

    # THE WRONG RULE: passage read off `gate` rather than off `gate_failures`
    by_gate = set(attached[attached.gate == S.GATE_PASS].sample_id)
    by_rule = set(attached[G.reaches_modes(attached)].sample_id)
    assert by_gate != by_rule
    assert 107 in by_rule and 107 not in by_gate


def test_the_gate_column_carries_every_failure_a_row_that_reaches_a_mode_can_have():
    """`FINDING_COLUMNS` has `gate` and no `gate_failures`, and that is lossless.

    Only here. `gate` holds the most severe outcome and `gate_failures` the
    complete set, and 3,511 claims on the real extract fail a blocking test AND
    a floor at once -- but every one of those is BLOCKED and reaches no finding
    row. A row that reaches a mode has no blocking failure, so its failure set is
    a subset of {GATE_LOW_SUPPORT} and the two columns are equivalent by
    construction. Asserted rather than assumed, because the equivalence is what
    makes the narrower column safe.
    """
    _, _, _, attached, _, _ = _pipeline()

    reaching = attached[G.reaches_modes(attached)]
    # the interesting half of the claim is about a row that DID fail something,
    # so the world must contain one or the loop below is vacuous
    assert int((reaching.gate_failures != "").sum()) == 1
    assert int((reaching.gate_failures == "").sum()) > 0
    for r in reaching.itertuples():
        failures = [f for f in str(r.gate_failures).split(";") if f]
        assert failures == ([] if r.gate == S.GATE_PASS else [r.gate])
        assert set(failures) <= {S.GATE_LOW_SUPPORT}
    # ...and the rows where the two columns genuinely diverge are all BLOCKED,
    # which is what makes the narrower finding column safe
    blocked = attached[~G.reaches_modes(attached)]
    assert set(blocked.gate) <= set(G.BLOCKING_OUTCOMES)


# --- what a row says and does not say ----------------------------------------


def test_two_disagreeing_claims_emit_both_rows_and_the_retired_tier_is_not_used():
    """Sample 105 names three assays. Three rows, each tiered on its own evidence.

    `T_CONFLICT` is RETIRED (`_schema.py:137-141`). Collapsing a disagreeing
    sample to it made the Mode 3 audit non-monotone -- adding evidence removed
    102 flags while adding 13 -- so the disagreement rides in the `contested`
    COLUMN and each claim keeps the tier its own evidence earned.
    """
    _, _, _, _, _, findings = _pipeline()

    rows = findings[findings.sample_id == 105]
    assert len(rows) == 3
    assert set(rows.proposed_internal_assay_id) == {11, 12, 13}
    assert rows.contested.all()
    assert set(rows.claim_tier) == {S.T_STRONG}
    assert S.T_CONFLICT not in set(findings.claim_tier)
    # and a contested sample is not suppressed: Mode 1 proposes a FIRST assay,
    # so a second candidate is a choice for the operator and not a reason to
    # say nothing
    assert 105 in set(findings.sample_id)


def test_the_tier_rides_onto_the_row_so_a_weak_proposal_is_distinguishable():
    """106's only evidence is a weak field; 100's is a strong one.

    Weak fields predict at 90.4% against a strong field's 98.4%, so a row that
    did not carry its tier would present the two as peers to the operator who
    approves them.
    """
    _, _, _, _, _, findings = _pipeline()

    weak = findings[findings.sample_id == 106].iloc[0]
    strong = findings[findings.sample_id == 100].iloc[0]
    assert weak.claim_tier == S.T_WEAK
    assert strong.claim_tier == S.T_STRONG
    assert weak.claim_tier != strong.claim_tier
    assert weak.source_field in S.WEAK_FIELDS
    assert strong.source_field in S.STRONG_FIELDS
    # both are still proposals; the tier ranks them, it does not gate them
    assert set(findings.action) == {S.A_ADD_TO_ASSAY}


def test_mode_1_asserts_nothing_about_the_tests_it_never_ran():
    """Lineage, co-registration and precedent are NULL on a Mode 1 row.

    Not zero, not `LIN_NONE`, not `BAND_NO_SUPPORT`. Mode 1 is settled before
    the lineage test under the precedence contract, and a co-registration rate
    is a statement about an ORDERED PAIR (registered assay, proposed assay) --
    a Mode 1 sample has no registered assay, so there is no pair and no
    population, now or under any wider extract. `LIN_NONE` would assert "no
    absence established" and `BAND_NO_SUPPORT` "measured, and the population was
    too small", and both are claims this mode did not make. That is the whole
    difference between absent evidence and evidence of absence.

    `classification` is null for the same reason: all four `CLASSES` describe
    what an absence MEANS for a sample that already holds something, and they
    are the OUTPUT of the two tests above. `CLS_UNRESOLVED` would say "neither
    test settles it" where neither test applies -- a bucket named for what
    someone assumed was in it, which is the error this spec records three times.
    """
    _, _, _, _, _, findings = _pipeline()

    not_run = ["classification", "lineage", "lineage_neighbour_uuid",
               "co_reg_rate", "co_reg_pop",
               "co_reg_registered_internal_assay_id",
               "co_reg_alt_label_internal_assay_id", "co_reg_alt_label_pop",
               "compat_band", "precedent_rate", "precedent_direction",
               "precedent_n_both", "precedent_n_child_only",
               "precedent_n_parent_only"]
    for col in not_run:
        assert findings[col].isna().all(), f"{col} asserts an untried test"
    # ...while the registered side is MEASURED and empty, which is a different
    # statement and must not be null
    assert (findings.registered_internal_assay_ids == "").all()
    assert findings.registered_internal_assay_ids.notna().all()
    # the closed families this mode does not draw from stay unspelled
    assert not (set(findings.lineage.dropna()) & set(S.LINEAGE_RELATIONS))
    assert not (set(findings.compat_band.dropna()) & set(S.COMPAT_BANDS))


def test_the_evidence_summary_carries_the_two_numbers_the_finding_columns_drop():
    """`vocab_n_samples` and `type_registrations` reach the operator here or nowhere.

    `FINDING_COLUMNS` borrows `vocab_support` and `vocab_purity` and neither of
    the two numbers a Mode 1 row is actually judged on: the gate's support floor
    reads `vocab_n_samples` and never `vocab_support`, so a row showing only the
    edge count beside a `GATE_LOW_SUPPORT` ruling shows a number the ruling never
    looked at; and `type_registrations` is the reachability evidence, which for
    Mode 1 is the ONLY corroboration outside the vocabulary row itself.
    """
    _, _, _, attached, _, findings = _pipeline()

    row = findings[findings.sample_id == 100].iloc[0]
    src = attached[(attached.sample_id == 100)
                   & (attached.internal_assay_id == 11)].iloc[0]
    assert int(src.vocab_n_samples) == 50 and int(src.type_registrations) == 5
    assert int(src.vocab_support) == 900

    # Each number is matched WITH ITS UNIT and on word boundaries, never as a
    # bare substring: 50 contains 5, so `"5" in summary` would pass on the
    # backing-sample count alone and prove nothing about the reachability
    # evidence, and 900 would satisfy a bare `"0" in summary` too.
    def _has(n, unit, text):
        return re.search(rf"(?<!\d){n}(?!\d) {unit}", text) is not None

    assert _has(50, "backing sample", row.evidence_summary)
    assert _has(5, "TIS sample", row.evidence_summary)
    # ...and the substitutable number is NOT what the sentence printed, so a row
    # reporting `vocab_support` where the gate's floor reads `vocab_n_samples`
    # fails here rather than reading plausibly
    assert not _has(900, "backing sample", row.evidence_summary)

    # the floor case names its outcome and both of its own numbers
    weak = findings[findings.sample_id == 107].iloc[0]
    src107 = attached[attached.sample_id == 107].iloc[0]
    assert int(src107.vocab_n_samples) == 1 and int(src107.type_registrations) == 4
    assert S.GATE_LOW_SUPPORT in weak.evidence_summary
    assert _has(1, "backing sample", weak.evidence_summary)
    assert _has(4, "TIS sample", weak.evidence_summary)


def test_the_project_column_carries_every_project_a_sample_holds_deduped_and_sorted():
    """`SAMPLE_COLUMNS.project_ids` is PLURAL and `FINDING_COLUMNS.project_id` is not.

    1,052 of the real 6,242 population samples carry more than one project id,
    34 carry a DUPLICATED one ("2,2"), and 193 carry none. The proposed assay's
    project is no better a source: 75 of the 154 internal assay ids span more
    than one project, up to seven. So the sample's whole project set is emitted,
    `;`-joined in the convention `registered_internal_assay_ids` already uses,
    and the singular column NAME is reported as a schema defect rather than
    quietly satisfied by dropping projects.

    The wrong rule -- take the first project and drop the rest -- is simulated
    and asserted to differ.
    """
    _, _, _, _, _, findings = _pipeline()

    assert findings[findings.sample_id == 108].iloc[0].project_id == "2;6"
    assert findings[findings.sample_id == 105].iloc[0].project_id == "2"
    assert findings[findings.sample_id == 106].iloc[0].project_id == ""
    assert findings[findings.sample_id == 100].iloc[0].project_id == "3"

    # THE WRONG RULE: first id only
    raw = _world()["samples"]
    first_only = {int(s): (str(p).split(",")[0] if pd.notna(p) else "")
                  for s, p in zip(raw.sample_id, raw.project_ids)}
    assert first_only[108] == "6"
    assert first_only[108] != findings[findings.sample_id == 108].iloc[0].project_id
    # ...and the un-deduplicated rule, which reads plausibly and is not right
    assert ";".join(str(raw[raw.sample_id == 105].iloc[0].project_ids)
                    .split(",")) == "2;2"
    assert findings[findings.sample_id == 105].iloc[0].project_id == "2"


# --- the frames --------------------------------------------------------------


def test_the_finding_frame_is_exactly_the_shared_contract_and_is_totally_sorted():
    """`FINDING_COLUMNS`, all 34, in order, sorted on BOTH keys of the grain.

    A curator diffs this artifact between runs and the claims frame arrives in
    whatever order the extractor wrote `samples.parquet`, an order
    `test_assay_hygiene_stage0.py` already records as unstable across extracts.

    The fixture is built out of order in both keys on purpose -- see `_world`'s
    docstring -- and this test asserts that BEFORE asserting the sort, so a world
    that happened to arrive sorted cannot certify a sort that is not happening.
    """
    _, _, _, attached, population, findings = _pipeline()
    assert list(findings.columns) == S.FINDING_COLUMNS
    assert len(S.FINDING_COLUMNS) == 34
    # one row per (sample, proposed assay), which is the grain the writer takes
    assert not findings.duplicated(
        ["sample_id", "proposed_internal_assay_id"]).any()

    pop = set(population)
    arrival = [(int(r.sample_id), int(r.internal_assay_id))
               for r in attached[G.reaches_modes(attached)].itertuples()
               if int(r.sample_id) in pop]
    emitted = [(int(a), int(b)) for a, b in
               zip(findings.sample_id, findings.proposed_internal_assay_id)]
    assert arrival != emitted, "the fixture arrives sorted and cannot see the sort"
    assert emitted == sorted(arrival)
    # the sort is TOTAL and not just on `sample_id`: a stable sort on the first
    # key alone leaves 108's two claims in arrival order, 13 before 12
    by_sample_only = sorted(arrival, key=lambda p: p[0])
    assert by_sample_only != emitted
    assert (108, 13) in arrival and by_sample_only.index((108, 13)) < \
        by_sample_only.index((108, 12))


def test_attach_gate_raises_rather_than_silently_pairing_two_different_runs():
    """The join is a bijection on (sample_id, proposed assay), or it is an error.

    `gate_claims` returns one row per claim in the claims frame's own order, so
    the two frames pair exactly. A caller handing it a gate frame built from a
    different claims frame gets a smaller answer with no count anywhere -- a
    claim dropped out of Mode 1 silently, which is the failure this package
    raises on everywhere else.
    """
    _, claims, gated, attached, _, _ = _pipeline()

    assert len(attached) == len(claims) == len(gated)
    assert list(attached.columns) == X.ATTACHED_COLUMNS
    # the claim's own columns survive the join unrenamed
    for col in S.CLAIM_COLUMNS:
        assert col in attached.columns

    with pytest.raises(ValueError, match="claim"):
        X.attach_gate(claims, gated.iloc[1:])
    with pytest.raises(ValueError, match="claim"):
        X.attach_gate(claims.iloc[1:], gated)

    # A DUPLICATE KEY is a different failure and is also refused: two rows for
    # one (sample, assay) pair would fan the join out and double a proposal.
    with pytest.raises(ValueError, match="duplicate"):
        X.attach_gate(pd.concat([claims, claims.iloc[:1]], ignore_index=True),
                      pd.concat([gated, gated.iloc[:1]], ignore_index=True))

    # ...and so is a frame whose key set matches while its PAYLOAD does not.
    # The two frames then describe different runs, and the check is what makes
    # the key-only join safe: joining on `raw_value` as well would look stricter
    # and would in fact drop the disagreeing rows instead of naming them.
    drifted = gated.copy()
    drifted.loc[drifted.index[0], "raw_value"] = "something else entirely"
    with pytest.raises(ValueError, match="raw_value"):
        X.attach_gate(claims, drifted)


def test_the_census_partitions_the_population_and_names_every_excluded_sample():
    """Three identities, and a bucket for every sample the mode does not propose on.

    The pre-gate halves are counted off the attached frame and the post-gate ones
    off the emitted findings, on purpose: computing both from one side would make
    the identities tautologies, and this way a defect in `mode1_findings` breaks
    an identity instead of hiding inside it.
    """
    w, _, _, attached, population, findings = _pipeline()

    census = X.mode1_census(attached, population, findings)
    assert set(census) == set(X.MODE1_CENSUS_KEYS)

    assert census["population"] == 10
    assert census["population_no_claim"] == 3
    assert census["population_with_claim"] == 7
    assert census["claim_rows"] == 12
    assert census["claim_rows_blocked"] == 4
    assert census["claim_rows_proposed"] == 8
    assert census["population_all_claims_blocked"] == 2
    assert census["population_proposed"] == 5

    # the identities, read off the census rather than off the literals above
    assert (census["population"]
            == census["population_no_claim"] + census["population_with_claim"])
    assert (census["population_with_claim"]
            == census["population_all_claims_blocked"]
            + census["population_proposed"])
    assert (census["claim_rows"]
            == census["claim_rows_blocked"] + census["claim_rows_proposed"])
    assert census["claim_rows_proposed"] == len(findings)
    assert census["population_proposed"] == findings.sample_id.nunique()

    # no two buckets share a value, so a rule that confuses two of them cannot
    # produce the same eight numbers
    values = [census[k] for k in X.MODE1_CENSUS_KEYS]
    assert len(set(values)) == len(values)

    # 999 is registered and has no row in the samples frame, so it is in no
    # bucket above. It is reported by name rather than dropped, which is what
    # keeps it from being an unexplained gap between the two frames' sizes.
    assert X.registered_samples_absent_from_samples(
        w["samples"], w["membership"]) == [999]
    assert 999 not in set(population)
    assert 999 not in set(findings.sample_id)


def test_nothing_proposes_by_a_source_this_mode_did_not_use():
    """Mode 1's only evidence is the gated claim, and the row says so.

    `BY_PRECEDENT` and `BY_BOTH` are declared for Mode 2, which is the reason
    `PROPOSAL_SOURCES` is a closed tuple: a consumer must be able to ask "is this
    one of the three" without restating the three, the way `PROVENANCES` and
    `GATE_OUTCOMES` are enumerable. Mode 1 emits exactly one of them.
    """
    _, _, _, _, _, findings = _pipeline()
    assert set(findings.proposed_by) == {X.BY_CLAIM}
    assert X.BY_CLAIM in X.PROPOSAL_SOURCES
    assert len(set(X.PROPOSAL_SOURCES)) == len(X.PROPOSAL_SOURCES)
    assert set(findings["mode"]) == {S.MODE_1}
    assert S.MODE_1 in S.EMITTED_MODES


def test_the_module_is_read_only_and_names_every_file_it_opens():
    """No write path, and no function whose name says it decides.

    `stage0_apply` and `driver_stage0` carry live production Cypher. An import is
    the only way a read-only module acquires a write path by accident, so their
    absence is asserted rather than assumed. The filenames are extracted from the
    source, so a sixth file added later fails here and has to be named.
    """
    src = (REPO / "scripts" / "assay_hygiene" / "classify.py").read_text()

    assert set(re.findall(r"[\w.-]+\.parquet", src)) == {
        "samples.parquet", "membership.parquet", "assays.parquet",
        "nodes.parquet", "claims.parquet"}
    assert set(re.findall(r"[\w.-]+\.csv", src)) == {"vocabulary.csv"}
    assert "stage0_apply" not in src and "driver_stage0" not in src
    assert "to_csv" not in src and "to_parquet" not in src
    assert not re.findall(r"^def decide_", src, re.M)


def test_main_reports_the_whole_world_and_leaves_every_byte_on_disk_unchanged(
        tmp_path, capsys):
    """A full `main` run over the fixture: nothing created, nothing modified.

    Asserted by hashing BOTH directories before and after, rather than by
    checking for one filename. Stage C's unified artifact belongs to the task
    that emits every mode at once, so a Mode-1-only file written here would put
    two files with one name in the operator's directory -- and "it wrote no file"
    is a claim that has to be checked against the directory, not against the
    absence of a `to_csv` call, which the guard above already covers separately.
    """
    w = _world()
    extract, out = tmp_path / "extract", tmp_path / "out"
    extract.mkdir(), out.mkdir()
    for name in ("samples", "membership", "assays", "nodes"):
        w[name].to_parquet(extract / f"{name}.parquet", index=False)
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    C.sample_claims(meta, uuids, w["vocabulary"]).to_parquet(
        out / "claims.parquet", index=False)
    V.save_vocabulary(w["vocabulary"], out / "vocabulary.csv")

    def _digests():
        return {p.relative_to(tmp_path).as_posix():
                hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(tmp_path.rglob("*")) if p.is_file()}

    before = _digests()
    assert X.main(str(extract), str(out)) == 0
    assert _digests() == before

    printed = capsys.readouterr().out
    for k in X.MODE1_CENSUS_KEYS:
        assert k in printed
    assert "nothing was written" in printed
    # the census reaches the operator as numbers, not only as key names
    assert "10" in printed and "999" in printed


def test_a_world_where_nothing_is_proposed_yields_an_empty_frame_of_the_right_shape():
    """Zero findings is a shape, not a crash, and Task 9 has to report it.

    Every claim in this world is blocked, so the emitted frame is empty and must
    still carry `FINDING_COLUMNS` in order -- a bare `DataFrame([])` would carry
    no columns and a consumer concatenating the modes would silently produce a
    frame with the wrong header.
    """
    w = _world()
    # nobody is registered anywhere, so every reachability cell is 0 and every
    # claim in the world is GATE_UNREACHABLE -- while the whole sample frame
    # becomes Mode 1's population
    w["membership"] = pd.DataFrame(columns=S.MEMBERSHIP_COLUMNS)
    _, _, _, attached, population, findings = _pipeline(w)

    assert len(attached) > 0, "the world must still raise claims"
    assert len(population) == len(w["samples"])
    assert len(findings) == 0
    assert list(findings.columns) == S.FINDING_COLUMNS
    census = X.mode1_census(attached, population, findings)
    assert census["claim_rows_proposed"] == 0
    assert census["population_proposed"] == 0
    assert census["claim_rows"] == census["claim_rows_blocked"]


# --- extract-backed ----------------------------------------------------------


def _real():
    for f in ("samples.parquet", "membership.parquet", "assays.parquet",
              "nodes.parquet"):
        if not (EXTRACT / f).exists():
            pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    if not (ARTIFACTS / "claims.parquet").exists():
        pytest.skip("no claims.parquet; run claims first")
    return {
        "samples": pd.read_parquet(EXTRACT / "samples.parquet"),
        "membership": pd.read_parquet(EXTRACT / "membership.parquet"),
        "assays": pd.read_parquet(EXTRACT / "assays.parquet"),
        "nodes": pd.read_parquet(EXTRACT / "nodes.parquet"),
        "claims": pd.read_parquet(ARTIFACTS / "claims.parquet"),
        "vocabulary": V.load_vocabulary(ARTIFACTS / "vocabulary.csv"),
    }


def test_the_real_extract_reproduces_mode_1s_population_before_and_after_the_gate():
    """Every figure this module's docstring states, re-derived from the parquet.

    All four before-gate figures carried into this task were exact, which is the
    first brief on this branch that needed no correction. The after-gate figures
    had never been measured by anyone and are published here.
    """
    r = _real()
    population = X.unregistered_samples(r["samples"], r["membership"],
                                        r["assays"])
    assert len(population) == 6242

    type_reg = G.type_registration_index(r["membership"], r["assays"], r["nodes"])
    gated = G.gate_claims(r["claims"], r["vocabulary"], type_reg,
                          G.sample_type_index(r["nodes"]))
    attached = X.attach_gate(r["claims"], gated)
    findings = X.mode1_findings(attached, population,
                                X.project_index(r["samples"]))
    census = X.mode1_census(attached, population, findings)

    # BEFORE the gate
    assert census["claim_rows"] == 2912
    assert census["population_with_claim"] == 1827
    assert census["population_no_claim"] == 4415
    pre = attached[attached.sample_id.isin(set(population))]
    at_floor = pre[pre.tier.isin((S.T_STRONG, S.T_CORROBORATED))]
    assert len(at_floor) == 671 and at_floor.sample_id.nunique() == 671

    # AFTER the gate
    assert census["claim_rows_proposed"] == 2166
    assert census["population_proposed"] == 1657
    assert census["claim_rows_blocked"] == 746
    assert census["population_all_claims_blocked"] == 170
    strong = findings[findings.claim_tier.isin((S.T_STRONG, S.T_CORROBORATED))]
    assert len(strong) == 590 and strong.sample_id.nunique() == 590
    # every blocked row is unreachable; no term family splits on this population
    blocked = pre[~G.reaches_modes(pre)]
    assert set(blocked.gate) == {S.GATE_UNREACHABLE}
    # the recorded-but-not-blocking floor, which is the whole reason the two
    # rules differ: 612 rows reach Mode 1 carrying a floor failure
    assert int((findings.gate == S.GATE_LOW_SUPPORT).sum()) == 612

    # the 82, measured rather than quoted
    from assay_hygiene.precedent import fallback_assay_ids
    registered = A.registered_internal(r["membership"], r["assays"])
    unmappable = fallback_assay_ids(r["assays"])
    mappable_only = {int(s) for s in r["samples"].sample_id
                     if not (registered.get(int(s), set()) - unmappable)}
    assert len(mappable_only) - len(population) == 82

    # nothing is dropped silently
    assert len(X.registered_samples_absent_from_samples(
        r["samples"], r["membership"])) == 362
