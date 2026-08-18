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
import ast
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import audit as A  # noqa: E402
from assay_hygiene import claims as C  # noqa: E402
from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import compatibility as CP  # noqa: E402
from assay_hygiene import gate as G  # noqa: E402
from assay_hygiene import lineage as L  # noqa: E402
from assay_hygiene import mode2 as M2  # noqa: E402
from assay_hygiene import precedent as P  # noqa: E402
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

# A SECOND SEEK RECORD FOR INTERNAL ASSAY 11, IN A DIFFERENT PROJECT. The same
# logical assay is instantiated once per study, so 458 seek records collapse to
# 154 internal ids and 75 of those ids span more than one project -- up to seven.
# "The project of assay 11" is therefore not single-valued, and a rule key built
# from the ASSAY rather than from the REGISTRATION picks whichever project sorts
# first.
#
# IT IS HERE BECAUSE ITS ABSENCE MADE TWO MUTATIONS UNDETECTABLE, measured on
# this file's first mutation run. A lookup ignoring the project component
# entirely changed NOT ONE ROW of this world, because every registration in it
# resolved to exactly one project; the mutation was caught only by the
# extract-backed test while its named owner passed. That is the same class as
# Task 4's WORLD C, which could not see a first-wins rule because the correct
# answer happened to be first. Used by `_world2` only.
SECOND_STUDY_SEEK_ID = 1141


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
    _, claims, _, attached, population, findings = _pipeline()

    census = X.mode1_census(attached, population, findings)
    # read off the CLAIMS frame, one stage upstream of anything this module
    # builds, so the bucket is defined by the absence of a claim and not by
    # subtracting whatever the classifier happened to emit
    silent = set(population) - set(claims.sample_id)
    assert silent == {103, 111, 112}
    assert census["population_no_claim"] == len(silent) == 3

    # ...and the OTHER two samples that reach no row are not in this bucket.
    # 104 and 109 claim loudly and are stopped by the gate, which is a different
    # fact about a curator's data and is counted separately.
    assert not ({104, 109} & silent)
    assert census["population_all_claims_blocked"] == 2
    assert census["population_no_claim"] != census["population_all_claims_blocked"]


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

    # NON-VACUITY FIRST. Every assertion below passes on an EMPTY frame -- the 14
    # `isna().all()` calls, the `== ""`, and both closed-family intersections are
    # all vacuously true of no rows -- so this test owns five mutations that fire
    # only because the world emits rows. `_world`'s docstring derives the 8.
    assert len(findings) == 8

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
    """`SAMPLE_COLUMNS.project_ids` is PLURAL, and so, since 2026-08-17, is the
    column that reads it.

    1,052 of the real 6,242 population samples carry more than one project id,
    34 carry a DUPLICATED one ("2,2"), and 193 carry none. The proposed assay's
    project is no better a source: 75 of the 154 internal assay ids span more
    than one project, up to seven. So the sample's whole project set is emitted,
    `;`-joined in the convention `registered_internal_assay_ids` already uses.

    `FINDING_COLUMNS` called this `project_id` until this task measured the
    value. `RULE_KEY.project_id` and `ASSAY_COLUMNS.project_id` are genuinely
    singular and stay, and Mode 2 holds `RULE_KEY` and `FINDING_COLUMNS` open at
    once, so the old spelling put two meanings under one name one frame apart.
    `tests/test_assay_hygiene_schema.py::test_no_finding_column_collides_with_the_rule_key`
    owns that half and fails on any recurrence.

    The wrong rule -- take the first project and drop the rest -- is simulated
    and asserted to differ.
    """
    _, _, _, _, _, findings = _pipeline()

    assert findings[findings.sample_id == 108].iloc[0].project_ids == "2;6"
    assert findings[findings.sample_id == 105].iloc[0].project_ids == "2"
    assert findings[findings.sample_id == 106].iloc[0].project_ids == ""
    assert findings[findings.sample_id == 100].iloc[0].project_ids == "3"
    # the column is the plural one, and the singular name is gone from the row
    assert "project_ids" in findings.columns
    assert "project_id" not in findings.columns

    # THE WRONG RULE: first id only
    raw = _world()["samples"]
    first_only = {int(s): (str(p).split(",")[0] if pd.notna(p) else "")
                  for s, p in zip(raw.sample_id, raw.project_ids)}
    assert first_only[108] == "6"
    assert first_only[108] != findings[findings.sample_id == 108].iloc[0].project_ids
    # ...and the un-deduplicated rule, which reads plausibly and is not right
    assert ";".join(str(raw[raw.sample_id == 105].iloc[0].project_ids)
                    .split(",")) == "2;2"
    assert findings[findings.sample_id == 105].iloc[0].project_ids == "2"


# --- the frames --------------------------------------------------------------


def test_the_finding_frame_is_exactly_the_shared_contract_and_is_totally_sorted():
    """`FINDING_COLUMNS`, all 36, in order, sorted on BOTH keys of the grain.

    A curator diffs this artifact between runs and the claims frame arrives in
    whatever order the extractor wrote `samples.parquet`, an order
    `test_assay_hygiene_stage0.py` already records as unstable across extracts.

    The fixture is built out of order in both keys on purpose -- see `_world`'s
    docstring -- and this test asserts that BEFORE asserting the sort, so a world
    that happened to arrive sorted cannot certify a sort that is not happening.

    34 until Mode 2 was written the same day, which added `type_registrations`
    and `lineage_n_supports`. Mode 1 FILLS the first -- the gate measured it, so
    a null there would say a test that ran did not -- and leaves the second null,
    because Mode 1 never runs the lineage test.
    `tests/test_assay_hygiene_schema.py::test_the_finding_contract_is_the_per_sample_one`
    carries the literal pin and the argument for both.
    """
    _, _, _, attached, population, findings = _pipeline()
    assert list(findings.columns) == S.FINDING_COLUMNS
    assert len(S.FINDING_COLUMNS) == 36
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

    # A COLUMN THE FRAMES SHARE BEYOND THE TWO CONTRACTS is checked too, and
    # this is the case a contract-derived loop would miss. `sample_type` belongs
    # to `GATE_COLUMNS` alone, so a caller who pre-joined it onto the claims
    # frame creates a shared column no constant names; `reindex` would then hand
    # back the CLAIM frame's value and discard the gate's, silently, which is
    # the same shape as the `GATE_COLUMNS` widening the pin test describes.
    prejoined = claims.assign(sample_type="WRONG")
    with pytest.raises(ValueError, match="sample_type"):
        X.attach_gate(prejoined, gated)


def test_attach_gate_pins_both_of_the_contracts_it_computes():
    """`ATTACHED_COLUMNS` and `_SHARED_PAYLOAD` are COMPUTED, so they are pinned.

    Neither is written down anywhere else, and the change that breaks them is
    already contemplated: `gate.py` reserves widening `GATE_COLUMNS` in
    increment 3. Should it gain a name `CLAIM_COLUMNS` already carries, the
    comprehension building `ATTACHED_COLUMNS` emits that name once, `merge`
    suffixes the gate's copy `_gate`, and `reindex` discards it -- so the CLAIM
    frame's value would win silently, for a column whose only job is to prove the
    two frames describe one run.

    Two assertions close that and they differ in kind. The literal pin makes the
    widening VISIBLE: a new column fails here and has to be named. The derivation
    makes it SAFE: `_SHARED_PAYLOAD` is computed from the two contracts, so a
    newly shared name joins the payload check without anyone remembering to
    extend a list -- the same argument `EVIDENCE_PROVENANCES` makes against
    `p != P_PROPOSED`, and `blocks_mode` against three inequalities.
    """
    assert X.ATTACHED_COLUMNS == [
        # the claim's own columns, first and unrenamed
        "sample_id", "uuid", "internal_assay_id", "internal_assay_title",
        "tier", "source_field", "raw_value", "contested", "source_provenance",
        # ...then everything the gate adds
        "sample_type", "gate", "gate_failures", "gate_reason",
        "vocab_support", "vocab_n_samples", "vocab_purity", "vocab_provenance",
        "term_family", "family_internal_assay_ids", "type_registrations",
    ]
    assert len(set(X.ATTACHED_COLUMNS)) == len(X.ATTACHED_COLUMNS) == 20

    # NOTHING EITHER CONTRACT CARRIES IS LOST IN THE JOIN. This is the assertion
    # a dropped gate column fails, and it is a SET EQUALITY rather than a length,
    # because a widening that both adds and drops a column keeps the count.
    assert set(X.ATTACHED_COLUMNS) == set(S.CLAIM_COLUMNS) | set(G.GATE_COLUMNS)

    # the derivation, and separately what it yields today
    assert X._SHARED_PAYLOAD == sorted(
        (set(S.CLAIM_COLUMNS) & set(G.GATE_COLUMNS))
        - {"sample_id", "internal_assay_id"})
    assert X._SHARED_PAYLOAD == [
        "internal_assay_title", "raw_value", "source_field", "uuid"]

    # the merge key is subtracted because `merge` does not suffix it, and it is
    # the one list the key, the payload and this pin are all built from
    assert X._MERGE_KEY == ["sample_id", "internal_assay_id"]
    assert not (set(X._SHARED_PAYLOAD) & set(X._MERGE_KEY))
    assert set(X._MERGE_KEY) <= set(S.CLAIM_COLUMNS) & set(G.GATE_COLUMNS)


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

    `BY_PRECEDENT`, `BY_BOTH` and `BY_LINEAGE_ONLY` are declared for Mode 2,
    which is the reason `PROPOSAL_SOURCES` is a closed tuple: a consumer must be
    able to ask "is this one of the four" without restating the four, the way
    `PROVENANCES` and `GATE_OUTCOMES` are enumerable. Mode 1 emits exactly one of
    them.

    This docstring said "one of the three" for a round after the fourth member
    landed -- the drift this family exists to prevent, in the test that owns it.
    `test_every_proposal_source_is_in_the_closed_family` now derives the members
    from the module so the count cannot be restated wrongly again.
    """
    _, _, _, _, _, findings = _pipeline()
    assert set(findings.proposed_by) == {X.BY_CLAIM}
    assert X.BY_CLAIM in X.PROPOSAL_SOURCES
    assert len(set(X.PROPOSAL_SOURCES)) == len(X.PROPOSAL_SOURCES)
    assert set(findings["mode"]) == {S.MODE_1}
    assert S.MODE_1 in S.EMITTED_MODES

    # NO VALUE COLLIDES WITH ANOTHER CLOSED FAMILY. `_schema`'s own families are
    # checked against each other by
    # `test_stage_c_vocabulary_does_not_collide_with_the_verdict_action_or_tier_families`,
    # and this one lives in `classify.py` where that test cannot see it. A value
    # equal to a mode, a gate outcome, a class, a lineage relation, a band, a
    # tier, an action or a provenance would be readable in the wrong column
    # without erroring, which is the failure this package is shaped around.
    others = (set(S.MODES) | set(S.GATE_OUTCOMES) | set(S.CLASSES)
              | set(S.LINEAGE_RELATIONS) | set(S.COMPAT_BANDS)
              | set(S.PROVENANCES)
              | {S.T_STRONG, S.T_WEAK, S.T_CORROBORATED, S.T_CONFLICT,
                 S.T_NONE}
              | {S.A_NONE, S.A_ADD_PARENT, S.A_ADD_CHILD, S.A_ADD_TO_ASSAY,
                 S.A_FLAG_ONLY})
    assert not (set(X.PROPOSAL_SOURCES) & others)


PACKAGE = REPO / "scripts" / "assay_hygiene"

# The two modules that own the live production write path. Every OTHER module in
# the package must be free of them, and naming the pair here rather than in each
# assertion is what lets the scan below cover files nobody has written yet.
WRITERS = {"stage0_apply.py", "driver_stage0.py"}


def _stage_c_sources() -> dict[str, str]:
    """{filename: source} for stage C's own modules. DERIVED, never hand-listed.

    THE GUARD READ ONE PATH UNTIL TASK 8 SPLIT MODE 2 OUT, at which point half
    the code it was guarding moved to a file it did not open -- the exact way a
    source-scanning test goes quietly blind. So the set is derived: follow
    `classify.py`'s own relative imports and subtract the modules that belong to
    an earlier stage and carry their own guards. A module added to stage C and
    imported by `classify` joins this set with no edit here; one added and NOT
    imported by anything is dead code, and the package-wide scan above still
    covers it for the write path.

    `EARLIER` is the hand-listed half and it is the safe half: forgetting to add
    a name to it makes this test FAIL loudly on an unexpected module, where
    forgetting to add one to a hand-listed stage C set would make it pass
    silently on an unguarded one.
    """
    EARLIER = {"_schema", "gate", "lineage", "audit", "precedent",
               "compatibility", "vocabulary", "claims", "extract"}
    src = (PACKAGE / "classify.py").read_text()
    named = set(re.findall(r"^\s*from \. import (\w+)", src, re.M))
    named |= set(re.findall(r"^\s*from \.(\w+) import", src, re.M))
    own = (named - EARLIER) | {"classify"}
    missing = sorted(m for m in own if not (PACKAGE / f"{m}.py").exists())
    assert not missing, f"classify imports {missing}, which is not in {PACKAGE}"
    return {f"{m}.py": (PACKAGE / f"{m}.py").read_text() for m in sorted(own)}


def test_no_module_in_the_package_imports_the_writer_or_names_a_function_for_a_decision():
    """The two package-wide invariants, scanned over the DIRECTORY.

    `stage0_apply` and `driver_stage0` carry live production Cypher, and an
    import is the only way a read-only module acquires a write path by accident.
    Scanning the directory rather than one path means a module added tomorrow is
    covered without anyone remembering to add it, which is the whole reason this
    moved off a single `read_text` when Mode 2 was split out.

    `decide_` is the naming half of "nothing decides, everything proposes". It
    is checked package-wide for the same reason: the binding constraint is on
    the package, not on one file.

    THE IMPORT IS PARSED AND NOT GREPPED, which the single-file version could
    afford not to do. Package-wide, a substring scan fails on `run_evidence.py`,
    whose docstring NAMES both writers in order to say that nothing reaches
    them -- so the crude test would forbid the very sentence a reader needs.
    `ast` distinguishes an import from a mention; a comment cannot execute.
    """
    seen = sorted(p.name for p in PACKAGE.glob("*.py"))
    assert "classify.py" in seen and "mode2.py" in seen, seen
    assert WRITERS <= set(seen), seen
    forbidden = {w[:-3] for w in WRITERS}

    scanned = 0
    for path in PACKAGE.glob("*.py"):
        src = path.read_text()
        assert not re.findall(r"^def decide_", src, re.M), path.name
        if path.name in WRITERS:
            continue
        scanned += 1
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                names = {a.name for a in node.names} | {node.module or ""}
            elif isinstance(node, ast.Import):
                names = {a.name.rsplit(".", 1)[-1] for a in node.names}
            else:
                continue
            assert not (names & forbidden), f"{path.name} imports a writer"
    assert scanned == len(seen) - len(WRITERS) > 10, scanned


def test_stage_c_names_every_file_it_opens_and_the_two_it_writes():
    """Every filename stage C touches, extracted from its source rather than searched.

    Searching for the absence of one known name passes the moment someone
    spells it differently, so the filenames are pulled out of the source and
    compared as a SET -- a further file added later fails here and has to be
    named.

    STAGE C WRITES TWO FILES AND IT DID NOT UNTIL TASK 8. Task 5 shipped this
    guard as `"to_csv" not in src`, on the stated ground that the findings file
    belongs to the task that emits every mode at once. This is that task, so the
    guard changes from "writes nothing" to "writes exactly these two, both csv,
    both from `main`". That is not a weaker assertion: an unnamed third file now
    fails here, and so does a `to_csv` anywhere but in `main`.
    """
    sources = _stage_c_sources()
    assert set(sources) == {"classify.py", "mode2.py"}, (
        "stage C's module set changed; re-derive the guard rather than the pin")
    src = "\n".join(sources.values())

    assert set(re.findall(r"[\w.-]+\.parquet", src)) == {
        "samples.parquet", "membership.parquet", "assays.parquet",
        "nodes.parquet", "claims.parquet",
        # Mode 2's lineage index and its precedent, which `main` MINES from this
        # frame rather than reading `precedent.csv` beside it: rules mined from
        # another extract would report a real hop as never measured
        "edges.parquet"}
    assert set(re.findall(r"[\w.-]+\.csv", src)) == {
        "vocabulary.csv", "findings.csv", "mode3-disposition.csv"}
    assert "to_parquet" not in src, "nothing here rewrites an input"
    # THE TWO WRITES ARE IN `main` AND NOWHERE ELSE, so every frame-building
    # function stays callable by Task 9's driver without producing a file.
    for name, text in sources.items():
        for chunk in text.split("\ndef ")[1:]:
            if "to_csv" in chunk:
                assert chunk.startswith("main("), f"{name} writes outside main"


def test_main_writes_exactly_two_artifacts_and_leaves_every_other_byte_unchanged(
        tmp_path, capsys):
    """A full `main` run over the fixture: two files created, nothing modified.

    Asserted by hashing BOTH directories before and after and DIFFING the two
    maps, rather than by checking for one filename. "It wrote exactly these two"
    is a claim about the directory and not about the absence of a `to_csv` call,
    which the guard above covers separately -- and the half that matters most is
    that every INPUT byte is identical afterwards, since this pass reads the
    extract a production writer also reads.

    BOTH MODES RUN, over one world. Mode 1's world carries no edges of its own --
    its population is samples registered in nothing and no edge could change a
    figure it reports -- so two are added HERE, and only here, to give Mode 2
    something to emit: 100 is unregistered and hangs off 102, which is registered
    in 12, and off 101, which is registered through the junction-less assay. Both
    proposals are ADD_CHILD, and neither moves a Mode 1 count.
    """
    w = _world()
    # (child, parent) plus the six identity columns `EDGE_COLUMNS` carries
    w["edges"] = pd.DataFrame(
        [(100, 102, "TIS-100", "TIS-102", "TIS", "TIS", None, None, None),
         (100, 101, "TIS-100", "TIS-101", "TIS", "TIS", None, None, None)],
        columns=S.EDGE_COLUMNS,
    )
    extract, out = tmp_path / "extract", tmp_path / "out"
    extract.mkdir(), out.mkdir()
    for name in ("samples", "membership", "assays", "nodes", "edges"):
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
    after = _digests()

    # exactly two new files, both named, both under `out_dir`
    assert set(after) - set(before) == {"out/findings.csv",
                                        "out/mode3-disposition.csv"}
    # ...and every byte that was there before is unchanged, inputs included
    assert {k: v for k, v in after.items() if k in before} == before

    findings = pd.read_csv(out / "findings.csv")
    assert list(findings.columns) == S.FINDING_COLUMNS
    assert len(findings[findings["mode"] == S.MODE_3]) == 0
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    assert list(disposition.columns) == X.DISPOSITION_COLUMNS

    printed = capsys.readouterr().out
    for k in (X.MODE1_CENSUS_KEYS + M2.MODE2_CENSUS_KEYS
              + X.FINDINGS_CENSUS_KEYS):
        assert k in printed
    # the two artifacts are NAMED in what the operator reads, and the claim
    # about writes is scoped to this run rather than to the package
    assert "findings.csv" in printed and "mode3-disposition.csv" in printed
    assert "no database" in printed
    # MODE 3 IS REPORTED AS UNDETECTED AND NEVER AS SMALL
    assert "no detector" in printed
    # the census reaches the operator as numbers, not only as key names
    assert "10" in printed and "999" in printed
    # THE WORD CEILING RIDES WITH THE MODE 2 NUMBERS, wherever they appear: an
    # unqualified 172,338 reads as an intent to write, and precedent cuts the
    # weak direction to about 2% of it
    assert "CEILING" in printed
    # ...and the two directions are printed apart at every threshold, never as
    # one figure
    for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
        assert printed.count(action) >= len(M2.SURVIVAL_THRESHOLDS)
    assert "survival by direction" in printed
    # the two Mode 2 rows this world produces
    assert "rows_add_child" in printed


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


# --- Mode 2: two directions of unequal strength -------------------------------
#
# A SECOND WORLD, and not a wider `_world`. Mode 1's population is samples
# registered in NOTHING and its world carries no edges at all; Mode 2's trigger
# is a lineage NEIGHBOUR, so every row it emits needs an edge and a registered
# neighbour. Growing one world to serve both would have made every Mode 1 count
# above a function of edges Mode 1 never reads, and `_world`'s docstring derives
# eight census figures by hand off its own rows.
#
# THE PRECEDENT FRAME IS HAND-AUTHORED AND NOT MINED, the same call
# `_schema.make_fixture` makes for its vocabulary. Two rates that a miner
# happened to make similar cannot discriminate a direction swap, and this file's
# whole reason for existing is that `propagation_rate` and `reverse_rate` are
# substitutable at the type level. Every rule below is arithmetically consistent
# with its own counts -- `propagation_rate == n_both / (n_both + n_child_only)`
# and `reverse_rate == n_both / (n_both + n_parent_only)` -- and
# `test_the_hand_authored_precedent_frame_is_internally_consistent` checks all
# of them, so the fixture cannot state a rate its own evidence does not support.
# `test_the_key_construction_speaks_the_language_mine_precedent_writes` mines the
# same world for real and proves the keys this module builds are the keys stage B
# emits.

# The five decoys all read a rate of EXACTLY 0.0, which is the value that makes a
# wrong lookup maximally expensive: 0.000 is a real, readable rate meaning
# "these have never once been seen co-registered on this hop", so a three-of-four
# key match does not merely report the wrong number, it reports evidence AGAINST
# a proposal whose own rule reads 0.90.
DECOY_RATE = 0.0


def _world2():
    """One synthetic lineage world. Every count in this docstring is derived here.

    Assays. internal 11, 12, 13, 14 are junctioned in project 10 (seek
    1011/1012/1013/1014); seek 490 has NO junction row and falls back to internal
    id 490, in project 20. The fallback is what puts a SECOND project in the rule
    key, so `RULE_KEY.project_id` is not constant across this world.

    Background, registered and edgeless, so the reachability cells are populated:

        1, 2, 3    TIS in 11        6, 7    TIS in 12        9    TIS in 13
        4, 5       PAV in 13        8       D.IMG in 11

    The SIXTEEN edges and the TWENTY-EIGHT proposals they produce. `->` is
    `child -> parent`, and the assay in parentheses is what each endpoint holds.
    Both counts are re-derived by
    `test_the_fixture_world_carries_exactly_the_populations_its_docstring_states`,
    which reads them off the world rather than trusting this sentence.

        E1   100 D.IMG(11) -> 200 TIS(12)    (200,11) ADD_PARENT  (100,12) ADD_CHILD
        E2   103 D.IMG(11) -> 200 TIS(12)    (200,11) 2nd support (103,12) ADD_CHILD
        E3   230 TIS(11)   -> 330 PAV(12)    (330,11) ADD_PARENT  (230,12) ADD_CHILD
        E4   240 TIS(13)   -> 340 PAV(11)    (340,13) ADD_PARENT  (240,11) ADD_CHILD
        E5   250 MUS(11)   -> 350 PAV(14)    (350,11) ADD_PARENT  (250,14) ADD_CHILD
        E6   260 D.IMG(11) -> 360 MUS(12)    (360,11) ADD_PARENT  (260,12) ADD_CHILD
        E7   170 D.IMG(11) -> 270 TIS(11,12) NO ROW              (170,12) ADD_CHILD
        E8   280 TIS(12)   -> 380 PAV(13,11) (380,12) ADD_PARENT  (280,13) ADD_CHILD
                                                                  (280,11) ADD_CHILD
        E9   290 TIS(12)   -> 390 PAV(14)    (390,12) ADD_PARENT  (290,14) ADD_CHILD
        E10  295 TIS()     -> 395 PAV(12)                         (295,12) ADD_CHILD
        E11  295 TIS()     -> 396 PAV(13)                         (295,13) ADD_CHILD
        E12  110 D.IMG(13) -> 210 TIS(12)    (210,13) ADD_PARENT  (110,12) ADD_CHILD
        E13  210 TIS(12)   -> 310 PAV(13)    (310,12) ADD_PARENT  (210,13) 2nd support
        E14  130 D.IMG(490)-> 430 TIS(12)    (430,490) ADD_PARENT (130,12) ADD_CHILD
        E15  501 D.IMG(11) -> 500 TIS(12)    (500,11) ADD_PARENT  (501,12) ADD_CHILD
        E16  600 D.IMG(11*)-> 610 TIS(12)    (610,11) ADD_PARENT  (600,12) ADD_CHILD

    `11*` is internal assay 11 reached through the PROJECT 40 seek record rather
    than the project 10 one.

    EVERY REQUIRED CASE, AND WHICH ROW CARRIES IT:

      (200,11)  ADD_PARENT keyed on `propagation_rate` 0.90, whose rule's
                `reverse_rate` is 0.10. TWO SUPPORTS (children 100 and 103) on
                ONE row, because one row is one write.
      (230,12)  ADD_CHILD keyed on `reverse_rate` 0.80 on hop (TIS, PAV), whose
      (340,13)  rule's `propagation_rate` is 0.20 -- against ADD_PARENT 0.95 on
                the SAME HOP under assay 13, whose `reverse_rate` is 0.05. That
                is the fixture's copy of the flagship datum: on one hop the
                child's assay flows up and the parent's does not flow down.
      (360,11)  NO precedent rule. Its key is (10, D.IMG, MUS, 11) and the
                world's strongest rule is (10, D.IMG, TIS, 11) at 0.90 -- three
                of four components equal -- so a parent-type-blind lookup reads
                0.90 where the answer is that nothing was measured.
      (270,11)  ABSENT. 270 holds 11 already and its child holds 11, so there is
                no absence for the neighbour to corroborate.
      (280,13)  the metadata claim disambiguates. 380 holds 13 AND 11 and 280
                lacks both, so the hop offers two candidate assays; 280's own
                `Type: alpha` names 13, and only that row reads BY_BOTH.
      (290,14)  a metadata claim exists and the GATE REJECTED it -- no TIS sample
                is registered in 14 anywhere -- so it corroborates nothing and
                the row is BY_PRECEDENT.
      (240,11)  240 carries a gate-passing claim naming 13, and its only row is
                for 11. The claim attaches per (sample, ASSAY) and not per
                sample, so this row is BY_PRECEDENT.
      (210,13)  reachable in BOTH directions -- child 110 holds 13 and parent 310
                holds 13 -- and emitted ONCE, as ADD_PARENT, the strong direction.
      (430,490) the rule key's PROJECT is 20, because 130's registration is
                through the junction-less assay. The world also carries a decoy
                rule at project 10 for the same hop and assay.
      (500,11)  500 has no row in the `samples` frame, the shape of the real
                extract's 185 candidate samples. Its `project_ids` is NULL --
                not measured -- where Mode 1's empty string means measured and
                none.
      (610,11)  the rule key's PROJECT again, this time where it is the ONLY
                component in dispute. 600 holds internal assay 11 through the
                project-40 seek record alone, so the hop keys
                (40, D.IMG, TIS, 11) at 0.65 -- while (10, D.IMG, TIS, 11), the
                same hop and the same assay, reads 0.90. A key taking its project
                from the ASSAY finds both 10 and 40 and reports 0.90.
      (295,12)  295 is registered NOWHERE, so it is in Mode 1's population AND in
      (295,13)  Mode 2's. Two rows, one sample: the ceiling counts a sample
                registered nowhere at its full gap.

    The (type, assay) cells, counted in DISTINCT samples and re-derived here
    rather than read off the membership block, because six samples below are
    registered as well as edged:

        (TIS,11)=5   1,2,3,230,270          (D.IMG,11)=7  8,100,103,170,260,
        (TIS,12)=10  6,7,200,210,270,280,                 501,600
                     290,430,500,610        (D.IMG,12)=0
        (TIS,13)=2   9,240                  (D.IMG,13)=1  110
        (TIS,14)=0   -- nothing             (D.IMG,490)=1 130
        (TIS,490)=0  -- nothing             (MUS,11)=1    250
        (PAV,11)=2   340,380                (MUS,12)=1    360
        (PAV,12)=2   330,395                (MUS,14)=0
        (PAV,13)=5   4,5,310,380,396
        (PAV,14)=2   350,390

    THIS TABLE SAID `(PAV,12)=3` INCLUDING 310, AND `(PAV,13)=4` EXCLUDING IT,
    until it was measured. 310 holds assay 13, so it was filed in the wrong cell
    and BOTH cells were wrong. No test read either one, which is exactly the
    "a stale fixture docstring cannot fail this suite" class -- in the one
    fixture whose whole premise is that every count is hand-derived. Every cell
    above is now pinned by
    `test_the_fixture_world_carries_exactly_the_populations_its_docstring_states`,
    so the table cannot drift from the world again.

    `(D.IMG,11)` counts 600 even though 600 is registered through the OTHER seek
    record: `type_registration_index` crosses to the internal namespace, so both
    records are assay 11 there. That is the same crossing the whole package makes
    and it is why the PROJECT is not recoverable from the cell.

    So `(TIS,14)` is empty, which is BOTH why 290's claim is GATE_UNREACHABLE and
    why the (290,14) row would create a (type, assay) pair existing nowhere. They
    are the same fact read by two rules: the gate BLOCKS a claim resting on it,
    Mode 2 only FLAGS a row, because Mode 2's evidence is the neighbour's
    registration rather than the vocabulary.

    The census, hand-traced off the table above:

        rows                                28
        samples                             26
        rows_add_parent                     12   200,330,340,350,360,380,390,
                                                 210,310,430,500,610
        samples_add_parent                  12
        rows_add_child                      16   100,103,230,240,250,260,170,
                                                 280x2,290,295x2,110,130,501,600
        samples_add_child                   14
        rows_reachable_both_ways             1   (210,13)
        rows_with_multiple_supports          2   (200,11) and (210,13)
        rows_with_precedent                 27
        rows_without_precedent               1   (360,11)
        rows_proposed_by_both                1   (280,13)
        rows_with_a_blocked_claim            1   (290,14)
        rows_creating_an_unseen_pair_add_parent  1   (430,490)
        rows_creating_an_unseen_pair_add_child  10   (100,12) (103,12) (250,14)
                                                     (260,12) (170,12) (290,14)
                                                     (110,12) (130,12) (501,12)
                                                     (600,12)
        rows_on_a_sample_registered_nowhere  2   (295,12) and (295,13)
        samples_registered_nowhere           1   295
        rows_without_a_sample_type           0
        rows_without_a_samples_row           1   (500,11)

    And against `lineage.mode2_ceiling`, which counts the same world by another
    route: `add_parent_rows` 12, `add_child_rows` 17, `union_rows` 28,
    `union_samples` 26, `both_directions` 1. The ceiling's ADD_CHILD is ONE
    larger than the emitted one, and (210,13) is that one.

    The two unseen-pair counts are 1 and 10 rather than 0 and n, deliberately: a
    direction split where one side is empty cannot show that the split is being
    made. Measured on the real extract they are 55.4% and 62.4%.

    THE EDGES ARRIVE IN NEITHER SORT ORDER, so the emitted sort has work to do.
    E15 is last and carries sample 500, and 280's two proposals are reached as
    13 then 11 because 380's registrations are read in membership order.
    """
    nodes, membership, samples, edges = [], [], [], []
    known: dict[int, str] = {}

    def add(sid, stype, assay_ids=(), meta="{}", projects="3",
            in_samples=True, in_nodes=True):
        known[sid] = stype
        if in_nodes:
            nodes.append((f"{stype}-{sid}", sid, stype))
        if in_samples:
            samples.append((sid, f"{stype}-{sid}", meta, None, projects))
        for a in assay_ids:
            membership.append((sid, a))

    def edge(child, parent):
        edges.append((child, parent, f"{known[child]}-{child}",
                      f"{known[parent]}-{parent}", known[child], known[parent],
                      None, None, None))

    for sid in (1, 2, 3):
        add(sid, "TIS", [11 + SEEK_OFFSET])
    for sid in (6, 7):
        add(sid, "TIS", [12 + SEEK_OFFSET])
    add(9, "TIS", [13 + SEEK_OFFSET])
    for sid in (4, 5):
        add(sid, "PAV", [13 + SEEK_OFFSET])
    add(8, "D.IMG", [11 + SEEK_OFFSET])

    add(100, "D.IMG", [11 + SEEK_OFFSET])
    add(103, "D.IMG", [11 + SEEK_OFFSET])
    add(200, "TIS", [12 + SEEK_OFFSET])
    add(230, "TIS", [11 + SEEK_OFFSET])
    add(330, "PAV", [12 + SEEK_OFFSET])
    # a gate-passing claim naming 13, an assay 240 ALREADY HOLDS, so the claim
    # attaches to no row of 240's and the one row it has stays BY_PRECEDENT
    add(240, "TIS", [13 + SEEK_OFFSET], meta='{"Type": "alpha"}')
    add(340, "PAV", [11 + SEEK_OFFSET])
    add(250, "MUS", [11 + SEEK_OFFSET])
    add(350, "PAV", [14 + SEEK_OFFSET])
    add(260, "D.IMG", [11 + SEEK_OFFSET])
    add(360, "MUS", [12 + SEEK_OFFSET])
    add(170, "D.IMG", [11 + SEEK_OFFSET])
    add(270, "TIS", [11 + SEEK_OFFSET, 12 + SEEK_OFFSET])
    add(280, "TIS", [12 + SEEK_OFFSET], meta='{"Type": "alpha"}')
    add(380, "PAV", [13 + SEEK_OFFSET, 11 + SEEK_OFFSET])
    add(290, "TIS", [12 + SEEK_OFFSET], meta='{"Type": "beta"}')
    add(390, "PAV", [14 + SEEK_OFFSET])
    add(295, "TIS")
    add(395, "PAV", [12 + SEEK_OFFSET])
    add(396, "PAV", [13 + SEEK_OFFSET])
    add(110, "D.IMG", [13 + SEEK_OFFSET])
    add(210, "TIS", [12 + SEEK_OFFSET])
    add(310, "PAV", [13 + SEEK_OFFSET])
    add(130, "D.IMG", [JUNCTIONLESS_SEEK_ID])
    add(430, "TIS", [12 + SEEK_OFFSET])
    # registered, edged, and ABSENT from the samples frame: 185 such samples
    # carry 448 of the real extract's candidate rows
    add(500, "TIS", [12 + SEEK_OFFSET], in_samples=False)
    add(501, "D.IMG", [11 + SEEK_OFFSET])
    # internal assay 11 through the PROJECT 40 seek record, and only that one, so
    # 600's hop keys (40, D.IMG, TIS, 11) while the project-10 rule for the same
    # hop and the same assay reads 0.90 against this one's 0.65
    add(600, "D.IMG", [SECOND_STUDY_SEEK_ID])
    add(610, "TIS", [12 + SEEK_OFFSET])

    for c, p in ((100, 200), (103, 200), (230, 330), (240, 340), (250, 350),
                 (260, 360), (170, 270), (280, 380), (290, 390), (295, 395),
                 (295, 396), (110, 210), (210, 310), (130, 430), (501, 500),
                 (600, 610)):
        edge(c, p)

    assays = pd.DataFrame(
        [(11 + SEEK_OFFSET, "Assay 11", 3, 2, 1, 10, "P", 11, "Assay 11"),
         (12 + SEEK_OFFSET, "Assay 12", 3, 2, 1, 10, "P", 12, "Assay 12"),
         (13 + SEEK_OFFSET, "Assay 13", 3, 2, 1, 10, "P", 13, "Assay 13"),
         (14 + SEEK_OFFSET, "Assay 14", 3, 2, 1, 10, "P", 14, "Assay 14"),
         # the SAME internal assay 11, instantiated again in project 40
         (SECOND_STUDY_SEEK_ID, "Assay 11", 3, 5, 4, 40, "R", 11, "Assay 11"),
         (JUNCTIONLESS_SEEK_ID, "Junctionless", 3, 2, 1, 20, "Q", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    vocabulary = pd.DataFrame(
        [("Type", "alpha", 13, "Assay 13", 900, 50, 0.99, S.P_LEARNED),
         # 14 is reachable for NO type in this world, so every claim on it is
         # GATE_UNREACHABLE while the mapping itself is beyond reproach
         ("Type", "beta", 14, "Assay 14", 800, 40, 0.98, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    return {
        "nodes": pd.DataFrame(nodes, columns=S.NODES_COLUMNS),
        "membership": pd.DataFrame(membership, columns=S.MEMBERSHIP_COLUMNS),
        "samples": pd.DataFrame(samples, columns=S.SAMPLE_COLUMNS),
        "edges": pd.DataFrame(edges, columns=S.EDGE_COLUMNS),
        "assays": assays,
        "vocabulary": vocabulary,
        "precedent": _precedent2(),
    }


def _rule(project, child_type, parent_type, assay, title, both, child_only,
          parent_only):
    """One precedent row whose two RATES ARE DERIVED FROM ITS OWN COUNTS.

    Never hand-written beside them. A fixture stating `propagation_rate = 0.90`
    next to counts that yield 0.75 is a fixture that lies about the one
    arithmetic this module is built on, and every test reading the rate off the
    frame would then agree with it.
    """
    fwd, rev = both + child_only, both + parent_only
    return (project, child_type, parent_type, assay, title, both, child_only,
            parent_only, (both / fwd) if fwd else 0.0,
            (both / rev) if rev else 0.0)


def _precedent2():
    """The hand-authored rules, and five decoys that match three key components.

    Rates, chosen so that no two rules a test reads share a value and so that
    each rule's two rates are far apart:

        (10, D.IMG, TIS, 11)    0.90 / 0.10    the ADD_PARENT case
        (10, D.IMG, TIS, 12)    0.15 / 0.25
        (10, D.IMG, TIS, 13)    0.85 / 0.15    the both-directions row
        (10, D.IMG, MUS, 12)    0.25 / 0.50
        (10, TIS, PAV, 11)      0.40 / 0.45
        (10, TIS, PAV, 12)      0.20 / 0.80    the flagship, downward
        (10, TIS, PAV, 13)      0.95 / 0.05    the flagship, upward
        (10, TIS, PAV, 14)      0.30 / 0.70
        (10, MUS, PAV, 11)      0.00 / 0.00    a MEASURED zero
        (10, MUS, PAV, 14)      0.35 / 0.60
        (20, D.IMG, TIS, 490)   0.75 / 0.25    the project component

    `(10, MUS, PAV, 11)` is the reason `(360,11)`'s missing rule is a different
    statement from a rate of zero: this world contains both, on two rows, and a
    test asserts they do not collapse.

    THERE IS NO RULE AT `(10, D.IMG, MUS, 11)`, deliberately. Three of its four
    components match `(10, D.IMG, TIS, 11)`, whose `propagation_rate` is the
    highest in the world.
    """
    rows = [
        _rule(10, "D.IMG", "TIS", 11, "Assay 11", 9, 1, 81),      # 0.90 / 0.10
        _rule(10, "D.IMG", "TIS", 12, "Assay 12", 3, 17, 9),      # 0.15 / 0.25
        _rule(10, "D.IMG", "TIS", 13, "Assay 13", 51, 9, 289),    # 0.85 / 0.15
        _rule(10, "D.IMG", "MUS", 12, "Assay 12", 1, 3, 1),       # 0.25 / 0.50
        _rule(10, "TIS", "PAV", 11, "Assay 11", 36, 54, 44),      # 0.40 / 0.45
        _rule(10, "TIS", "PAV", 12, "Assay 12", 4, 16, 1),        # 0.20 / 0.80
        _rule(10, "TIS", "PAV", 13, "Assay 13", 19, 1, 361),      # 0.95 / 0.05
        _rule(10, "TIS", "PAV", 14, "Assay 14", 21, 49, 9),       # 0.30 / 0.70
        _rule(10, "MUS", "PAV", 11, "Assay 11", 0, 1, 1),         # 0.00 / 0.00
        _rule(10, "MUS", "PAV", 14, "Assay 14", 21, 39, 14),      # 0.35 / 0.60
        _rule(20, "D.IMG", "TIS", 490, "Junctionless", 3, 1, 9),  # 0.75 / 0.25
        # THE SAME HOP AND THE SAME ASSAY AS THE FIRST RULE, IN ANOTHER PROJECT.
        # Only the project separates (40, D.IMG, TIS, 11) at 0.65 from
        # (10, D.IMG, TIS, 11) at 0.90, so a lookup that takes the project from
        # the ASSAY -- which resolves to both 10 and 40 -- reads 0.90 here.
        _rule(40, "D.IMG", "TIS", 11, "Assay 11", 13, 7, 39),     # 0.65 / 0.25
        # the decoys: one wrong component each, all reading 0.000
        _rule(99, "D.IMG", "TIS", 11, "Assay 11", 0, 1, 1),       # wrong project
        _rule(10, "MUS", "TIS", 11, "Assay 11", 0, 1, 1),         # wrong child
        _rule(10, "D.IMG", "PAV", 11, "Assay 11", 0, 1, 1),       # wrong parent
        _rule(10, "D.IMG", "TIS", 99, "Assay 99", 0, 1, 1),       # wrong assay
        _rule(10, "D.IMG", "TIS", 490, "Junctionless", 0, 1, 1),  # wrong project
    ]
    return pd.DataFrame(rows, columns=S.PRECEDENT_COLUMNS)


def _attached2(w):
    """The gated, attached claims frame for a Mode 2 world."""
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    claims = C.sample_claims(meta, uuids, w["vocabulary"])
    gated = G.gate_claims(
        claims, w["vocabulary"],
        G.type_registration_index(w["membership"], w["assays"], w["nodes"]),
        G.sample_type_index(w["nodes"]))
    return X.attach_gate(claims, gated)


def _pipeline2(w=None):
    """The Mode 2 world, indexed, gated and classified. -> (w, bundle, findings).

    `bundle` is the keyword argument dict `mode2_findings` takes, so a test that
    needs to perturb ONE index can do it by name rather than by rebuilding the
    call.
    """
    w = w or _world2()
    attached = _attached2(w)
    type_reg = G.type_registration_index(w["membership"], w["assays"], w["nodes"])
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        w["edges"], w["samples"], w["membership"])
    bundle = dict(
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=A.registered_internal(w["membership"], w["assays"]),
        rules=M2.precedent_rules(w["precedent"]),
        reg_projects=M2.registration_projects(w["membership"], w["assays"]),
        types=G.sample_type_index(w["nodes"]),
        type_reg=type_reg,
        titles=M2.assay_titles(w["assays"]),
        projects=X.project_index(w["samples"]),
    )
    return w, bundle, M2.mode2_findings(attached, **bundle)


def _row(findings, sample_id, assay_id):
    """The one row for a (sample, proposed assay) pair, or a readable failure."""
    hit = findings[(findings.sample_id == sample_id)
                   & (findings.proposed_internal_assay_id == assay_id)]
    assert len(hit) == 1, f"expected exactly one ({sample_id}, {assay_id}) row"
    return hit.iloc[0]


def _census2(w, bundle, findings):
    """The Mode 2 census over a world, so no test rebuilds the two extra inputs."""
    return M2.mode2_census(
        findings,
        L.mode2_ceiling(bundle["children_of"], bundle["parents_of"],
                        bundle["registered"]),
        _attached2(w))


def test_the_hand_authored_precedent_frame_is_internally_consistent():
    """Every fixture rate equals the arithmetic its own counts imply.

    A stale fixture docstring cannot fail a suite that only asserts what the
    fixture says, so the fixture's two rates are DERIVED from its counts by
    `_rule` and re-derived here from the frame. Without this, a rule stating 0.90
    beside counts yielding 0.75 would make every direction test agree with a
    world that does not exist.
    """
    prec = _precedent2()
    assert len(prec) == 17
    for r in prec.itertuples(index=False):
        fwd, rev = r.n_both + r.n_child_only, r.n_both + r.n_parent_only
        assert r.propagation_rate == ((r.n_both / fwd) if fwd else 0.0)
        assert r.reverse_rate == ((r.n_both / rev) if rev else 0.0)
        # the two rates are never equal on a rule a test reads, or a swap is
        # invisible on it
        if r.n_both:
            assert r.propagation_rate != r.reverse_rate
    assert list(prec.columns) == S.PRECEDENT_COLUMNS
    # the five decoys, and nothing a test reads, sit at the dangerous value
    assert int((prec.propagation_rate == DECOY_RATE).sum()) == 6   # 5 + the zero rule


def test_a_child_registering_an_assay_its_parent_lacks_proposes_adding_the_parent():
    """(200,11): two D.IMG children hold 11 and their TIS parent does not.

    The strong direction. Corroborated by co-registration 88 times out of 88 over
    the 866 flags, against 15 of 263 for the mirror, and 0.931 against 0.006 on
    the hop that justified Mode 2.
    """
    w, _, findings = _pipeline2()
    row = _row(findings, 200, 11)

    assert row["mode"] == S.MODE_2
    assert row.action == S.A_ADD_PARENT
    assert row.lineage == S.LIN_CHILD
    assert row.lineage_neighbour_uuid == "D.IMG-100"
    assert row.classification == S.CLS_ABSENCE_LINEAGE
    assert row.proposed_by == X.BY_PRECEDENT
    assert row.proposed_internal_assay_title == "Assay 11"
    assert row.sample_type == "TIS" and row.uuid == "TIS-200"
    # the sample's OWN registrations, decoded in position
    assert row.registered_internal_assay_ids == "12"
    assert row.registered_internal_assay_titles == "Assay 12"


def test_add_parent_keys_on_the_propagation_rate_and_add_child_on_the_reverse_rate():
    """THE TRAP. One hop, both directions, and two rates that are nowhere near.

    `(10, TIS, PAV, 12)` reads 0.20 up and 0.80 down; `(10, TIS, PAV, 13)` reads
    0.95 up and 0.05 down. So on the hop `TIS <- PAV` the child's assay flows up
    at 0.95 while the parent's flows down at 0.80 under a different assay, and
    every one of those four numbers is distinct. Reading the wrong column
    produces a plausible number and no error, which is why this test simulates
    the swap by hand and asserts the answers DIFFER.

    Measured on the real extract, the same hop reads `propagation_rate` 0.931
    under 74 Tissue Collection and `reverse_rate` 0.006 under 56 Patient Visit.
    """
    w, bundle, findings = _pipeline2()
    rules = bundle["rules"]

    up = _row(findings, 340, 13)        # ADD_PARENT on (10, TIS, PAV, 13)
    down = _row(findings, 230, 12)      # ADD_CHILD  on (10, TIS, PAV, 12)

    assert up.action == S.A_ADD_PARENT and down.action == S.A_ADD_CHILD
    # the direction column NAMES the precedent column the rate was read from, so
    # the row can be audited against `precedent.csv` without this test's help
    assert up.precedent_direction == "propagation_rate"
    assert down.precedent_direction == "reverse_rate"
    assert set(M2.PRECEDENT_DIRECTIONS) <= set(S.PRECEDENT_COLUMNS)

    # READ OFF THE RULE FRAME, never off a literal
    up_rule = rules[(10, "TIS", "PAV", 13)]
    down_rule = rules[(10, "TIS", "PAV", 12)]
    assert up.precedent_rate == up_rule.propagation_rate
    assert down.precedent_rate == down_rule.reverse_rate
    assert up.precedent_n_both == up_rule.n_both
    assert up.precedent_n_child_only == up_rule.n_child_only
    assert up.precedent_n_parent_only == up_rule.n_parent_only

    # THE SWAP, run by hand. It is silent: both substitutes are real rates on
    # real rules and neither raises.
    assert up_rule.reverse_rate != up_rule.propagation_rate
    assert down_rule.propagation_rate != down_rule.reverse_rate
    assert up.precedent_rate != up_rule.reverse_rate
    assert down.precedent_rate != down_rule.propagation_rate
    # ...and the four values are mutually distinct, so no pair of them can be
    # confused for the other by coincidence
    assert len({up_rule.propagation_rate, up_rule.reverse_rate,
                down_rule.propagation_rate, down_rule.reverse_rate}) == 4

    # the mapping has exactly one definition and it is the one the rows used
    assert M2.ACTION_PRECEDENT_DIRECTION == {
        S.A_ADD_PARENT: "propagation_rate", S.A_ADD_CHILD: "reverse_rate"}
    for r in findings[findings.precedent_rate.notna()].itertuples():
        assert r.precedent_direction == M2.ACTION_PRECEDENT_DIRECTION[r.action]


def test_a_hop_with_no_precedent_rule_has_no_measured_basis_and_never_a_rate_of_zero():
    """(360,11) has no rule; (350,11) has one reading 0.000. Both exist here.

    Absent evidence and evidence of absence are different statements and this
    world carries one of each, one row apart. A rate of 0.000 says the hop has
    been observed and the two have never once been co-registered; a null says
    nobody measured. Defaulting the second to the first would present an
    unmeasured proposal as a refuted one.

    The missing key is `(10, D.IMG, MUS, 11)` and the world's strongest rule is
    `(10, D.IMG, TIS, 11)` at 0.90 -- three of four components equal -- so a
    parent-type-blind lookup would fill this row with the highest rate in the
    world.
    """
    w, bundle, findings = _pipeline2()

    unmeasured = _row(findings, 360, 11)
    measured_zero = _row(findings, 350, 11)

    assert pd.isna(unmeasured.precedent_rate)
    assert pd.isna(unmeasured.precedent_direction)
    assert pd.isna(unmeasured.precedent_n_both)
    assert pd.isna(unmeasured.precedent_n_child_only)
    assert pd.isna(unmeasured.precedent_n_parent_only)
    assert "no precedent" in unmeasured.evidence_summary

    assert measured_zero.precedent_rate == 0.0
    assert measured_zero.precedent_n_both == 0
    assert measured_zero.precedent_rate != unmeasured.precedent_rate

    # ...and the row is still EMITTED. A proposal with no measured basis is a
    # proposal an operator must be shown, not one the pipeline may drop.
    assert unmeasured.action == S.A_ADD_PARENT
    assert unmeasured.lineage == S.LIN_CHILD

    # THE WRONG RULE, run by hand: the three-of-four match this row would find
    assert (10, "D.IMG", "MUS", 11) not in bundle["rules"]
    assert bundle["rules"][(10, "D.IMG", "TIS", 11)].propagation_rate == 0.90


def test_the_rule_key_is_all_four_components_and_three_of_four_does_not_match():
    """Five decoys, one wrong component each, every one reading 0.000.

    The key is `(project_id, child_type, parent_type, internal_assay_id)`. A
    lookup blind to any single component finds a decoy here, and a decoy reads
    0.000 -- not a missing value but a REAL rate meaning "never once
    co-registered", which is evidence against the very proposal the row makes.

    THE PROJECT COMPONENT IS PROVEN ON `(610, 11)` AND NOT ON THE DECOY ALONE.
    A decoy at project 99 proves only that a rule nobody can reach is not
    reached; the discriminating case needs TWO reachable rules differing in the
    project and nothing else, which is what internal assay 11's second seek
    record supplies. Both halves are here because the harness measured that the
    first half alone could not see a project-blind lookup.
    """
    w, bundle, findings = _pipeline2()
    rules = bundle["rules"]

    for decoy in ((99, "D.IMG", "TIS", 11), (10, "MUS", "TIS", 11),
                  (10, "D.IMG", "PAV", 11), (10, "D.IMG", "TIS", 99),
                  (10, "D.IMG", "TIS", 490)):
        assert decoy in rules, "the decoy must exist or it proves nothing"
        assert rules[decoy].propagation_rate == DECOY_RATE
        assert rules[decoy].reverse_rate == DECOY_RATE

    # the PROJECT component decides between the true rule and its decoy, and the
    # true one is reached through the junction-less assay's own project
    row = _row(findings, 430, 490)
    assert row.precedent_rate == rules[(20, "D.IMG", "TIS", 490)].propagation_rate
    assert row.precedent_rate == 0.75
    assert row.precedent_rate != rules[(10, "D.IMG", "TIS", 490)].propagation_rate

    # THE PROJECT COMPONENT AGAIN, ON THE CASE THAT CAN ACTUALLY SEE IT -- and
    # the 430/490 row above CANNOT. Internal assay 490 is registered through one
    # project only, so a lookup ignoring the project entirely still finds project
    # 20 and returns the same rate; measured, a project-blind mutation changed
    # not one row of this world until internal assay 11 was given a second seek
    # record. That mutation was then reported MISLABELLED because it died in the
    # index test while THIS one -- which claims the rule key in its name -- passed.
    #
    # 600 holds internal assay 11 through the project-40 record alone, so its
    # hop keys (40, D.IMG, TIS, 11) at 0.65 while (10, D.IMG, TIS, 11) -- the
    # same hop, the same assay, differing in NOTHING but the project -- is 0.90.
    row = _row(findings, 610, 11)
    assert row.precedent_rate == rules[(40, "D.IMG", "TIS", 11)].propagation_rate
    assert row.precedent_rate == 0.65

    # THE WRONG RULE, run by hand: take the project off the ASSAY. It is not
    # single-valued -- 75 of the real extract's 154 internal assay ids span more
    # than one project, up to seven -- so such a lookup picks whichever sorts
    # first and finds a real, confident, different number rather than an error.
    assay_projects = {p for p, i, _ in P.assay_index(w["assays"]).values() if i == 11}
    assert assay_projects == {10, 40}
    assert rules[(min(assay_projects), "D.IMG", "TIS", 11)].propagation_rate == 0.90
    assert row.precedent_rate != 0.90
    assert {k for k in rules if k[1:] == ("D.IMG", "TIS", 11)} == {
        (10, "D.IMG", "TIS", 11), (40, "D.IMG", "TIS", 11),
        (99, "D.IMG", "TIS", 11)}

    # NO EMITTED ROW CARRIES A DECOY'S RATE, and the only 0.000 in the frame is
    # the one measured rule that genuinely reads zero
    zeros = findings[findings.precedent_rate == DECOY_RATE]
    assert list(zip(zeros.sample_id, zeros.proposed_internal_assay_id)) == [(350, 11)]


def test_a_pair_reachable_from_two_neighbours_is_one_row_carrying_two_supports():
    """(200,11) has two children holding 11. Adding 200 to 11 is ONE write.

    A row per neighbour would ask the operator to approve the same membership
    twice and would double every figure the report quotes. The support COUNT
    still has to reach them, or a proposal backed by twelve neighbours reads
    exactly like one backed by a single edge.
    """
    w, bundle, findings = _pipeline2()

    row = _row(findings, 200, 11)
    kids, rents = L.lineage_supports(200, 11, bundle["children_of"],
                                     bundle["parents_of"], bundle["registered"])
    assert kids == [100, 103] and rents == []
    assert row.lineage_n_supports == len(kids) + len(rents) == 2
    # the row NAMES one of them, and it is the one `neighbour_registers` picks
    assert row.lineage_neighbour_uuid == bundle["uuid_of"][kids[0]]

    # ...and a single-support row is distinguishable from it
    assert _row(findings, 330, 11).lineage_n_supports == 1
    assert not findings.duplicated(
        ["sample_id", "proposed_internal_assay_id"]).any()


def test_a_pair_reachable_in_both_directions_is_one_row_in_the_strong_direction():
    """(210,13): a child holds 13 and so does a parent. One write, one row.

    `LIN_CHILD` beats `LIN_PARENT` because ADD_PARENT is the corroborated
    direction, and `lineage_supports` hands back both lists so the choice hides
    nothing -- the row records two supports.

    132 such pairs exist on the real extract, which is exactly why the emitted
    ADD_CHILD count (117,331) is smaller than the ceiling's (117,463).
    """
    w, bundle, findings = _pipeline2()

    row = _row(findings, 210, 13)
    kids, rents = L.lineage_supports(210, 13, bundle["children_of"],
                                     bundle["parents_of"], bundle["registered"])
    assert kids == [110] and rents == [310], "the pair must be reachable both ways"
    assert row.action == S.A_ADD_PARENT
    assert row.lineage == S.LIN_CHILD
    assert row.lineage_n_supports == 2
    assert row.precedent_direction == "propagation_rate"
    assert row.precedent_rate == bundle["rules"][
        (10, "D.IMG", "TIS", 13)].propagation_rate

    # THE WRONG RULE: one row per direction. It doubles the write.
    assert len(findings[(findings.sample_id == 210)
                        & (findings.proposed_internal_assay_id == 13)]) == 1


def test_a_sample_already_registered_in_the_proposed_assay_yields_no_row():
    """270 holds 11 and its child holds 11. Nothing is absent, so nothing is proposed."""
    w, bundle, findings = _pipeline2()

    assert 11 in bundle["registered"][270]
    assert 11 in bundle["registered"][170]
    assert 170 in bundle["children_of"][270]
    assert list(findings[findings.sample_id == 270].proposed_internal_assay_id) == []
    # the guard is the one `lineage_supports` places at the top of its own scan
    assert L.lineage_supports(270, 11, bundle["children_of"],
                              bundle["parents_of"], bundle["registered"]) == ([], [])
    # ...while the same edge DOES produce the other direction's row, so the edge
    # is not inert and this absence is a ruling rather than a gap
    assert _row(findings, 170, 12).action == S.A_ADD_CHILD


def test_the_metadata_claim_disambiguates_which_assay_and_proposed_by_records_it():
    """380 holds 13 and 11; 280 lacks both; 280's own metadata names 13.

    Precedent speaks about the HOP and cannot choose between two assays on it --
    `D.IMG -> TIS` carries 23 assay rules on the real extract. Metadata is the
    one evidence that varies per sample, so it disambiguates, and `proposed_by`
    is where that is recorded.

    BOTH CANDIDATES ARE STILL EMITTED. Suppressing the uncorroborated one would
    be a decision, and nothing here decides; the operator chooses, and the column
    tells them which choice the sample's own metadata agrees with.
    """
    w, bundle, findings = _pipeline2()

    named = _row(findings, 280, 13)
    other = _row(findings, 280, 11)

    assert named.proposed_by == X.BY_BOTH
    assert other.proposed_by == X.BY_PRECEDENT
    assert X.BY_BOTH in X.PROPOSAL_SOURCES and X.BY_PRECEDENT in X.PROPOSAL_SOURCES

    # the claim's own evidence rides onto the corroborated row and nowhere else
    assert named.claim_tier == S.T_STRONG
    assert named.source_field == "Type" and named.raw_value == "alpha"
    assert named.gate == S.GATE_PASS
    assert named.vocab_support == 900 and named.vocab_purity == 0.99
    assert pd.notna(named.contested) and bool(named.contested) is False
    for col in ("claim_tier", "source_field", "raw_value", "gate",
                "vocab_support", "vocab_purity", "vocab_provenance", "contested"):
        assert pd.isna(other[col]), f"{col} is claim evidence and there is no claim"

    # THE CLAIM ATTACHES PER (SAMPLE, ASSAY), NOT PER SAMPLE. 240 carries a
    # gate-passing claim naming 13 -- an assay it already holds, so no row -- and
    # its one row, for 11, must not inherit it.
    attached = _attached2(w)
    reaching = attached[G.reaches_modes(attached)]
    claimed = {(int(c.sample_id), int(c.internal_assay_id))
               for c in reaching.itertuples(index=False)}
    assert (240, 13) in claimed and (240, 11) not in claimed
    assert _row(findings, 240, 11).proposed_by == X.BY_PRECEDENT
    # ...and the wrong rule -- attach any of the sample's claims -- would reach it
    assert 240 in {s for s, _ in claimed}


def test_a_gate_rejected_claim_corroborates_nothing_and_the_row_records_it():
    """290 claims 14, and no TIS sample is registered in 14 anywhere.

    That is `GATE_UNREACHABLE`, which BLOCKS: a claim the gate rejected reaches
    no mode, so it cannot promote a Mode 2 row to BY_BOTH either. The row still
    exists -- its evidence is the parent's registration, which the gate has no
    opinion about -- and it stays BY_PRECEDENT.

    The claim is not dropped silently: the census counts it and the summary says
    a rejected claim was found.
    """
    w, bundle, findings = _pipeline2()

    row = _row(findings, 290, 14)
    assert row.proposed_by == X.BY_PRECEDENT
    assert pd.isna(row.gate), "the gate ruled on the CLAIM, not on this proposal"
    assert "rejected" in row.evidence_summary

    census = _census2(w, bundle, findings)
    assert census["rows_with_a_blocked_claim"] == 1
    assert census["rows_proposed_by_both"] == 1

    # the claim really was rejected, and for reachability
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    claims = C.sample_claims(meta, uuids, w["vocabulary"])
    gated = G.gate_claims(claims, w["vocabulary"],
                          G.type_registration_index(w["membership"], w["assays"],
                                                    w["nodes"]),
                          G.sample_type_index(w["nodes"]))
    hit = gated[(gated.sample_id == 290) & (gated.internal_assay_id == 14)].iloc[0]
    assert hit.gate == S.GATE_UNREACHABLE and G.blocks_mode(hit.gate)


def test_a_row_creating_a_type_assay_pair_existing_nowhere_is_flagged_on_the_row():
    """`type_registrations == 0` means no sample of this type holds this assay.

    67.6% of ADD_CHILD rows do this by the brief's reading and 62.4% by
    measurement; 55.4% of ADD_PARENT rows do. It is the SAME cell the gate's
    reachability test reads, and the two rules differ in what they do with it: a
    claim resting on an empty cell is BLOCKED, because the vocabulary is the only
    evidence behind it, while a Mode 2 row is FLAGGED, because its evidence is a
    neighbour's registration and the gate has no opinion on that.

    A COUNT AND NOT A BOOLEAN, so the row that would create a pair from nothing
    is distinguishable from the row joining 5 existing registrations, and both
    from the row whose type could not be resolved at all.
    """
    w, bundle, findings = _pipeline2()

    unseen = _row(findings, 250, 14)         # MUS proposed 14; no MUS holds 14
    seen = _row(findings, 200, 11)           # TIS proposed 11; five TIS hold it
    assert unseen.type_registrations == 0
    assert seen.type_registrations == bundle["type_reg"][("TIS", 11)] == 5
    assert ("MUS", 14) not in bundle["type_reg"]

    # the two directions are counted SEPARATELY and never pooled
    census = _census2(w, bundle, findings)
    assert census["rows_creating_an_unseen_pair_add_parent"] == 1
    assert census["rows_creating_an_unseen_pair_add_child"] == 10
    # read off the frame as well, so the census cannot be the only witness
    for act, key in ((S.A_ADD_PARENT, "rows_creating_an_unseen_pair_add_parent"),
                     (S.A_ADD_CHILD, "rows_creating_an_unseen_pair_add_child")):
        sub = findings[findings.action == act]
        assert int((sub.type_registrations == 0).sum()) == census[key]
    assert (census["rows_creating_an_unseen_pair_add_parent"]
            != census["rows_creating_an_unseen_pair_add_child"])

    # Mode 1 fills the same column off the gate, because the gate DID measure it
    _, _, _, attached1, population1, findings1 = _pipeline()
    src = attached1[(attached1.sample_id == 100)
                    & (attached1.internal_assay_id == 11)].iloc[0]
    assert findings1[findings1.sample_id == 100].iloc[0].type_registrations \
        == int(src.type_registrations) == 5


def test_a_sample_with_no_resolvable_type_measures_neither_cell_and_is_counted():
    """No type means no hop and no (type, assay) cell, and both columns say null.

    Zero rows on the real extract, where every edge endpoint carries a node row.
    The guard exists because the failure is silent: `type_reg.get((None, 11))`
    misses and would otherwise read as a pair existing nowhere -- the strongest
    negative flag the row can carry -- asserted about a type nobody knows.
    """
    w, bundle, findings = _pipeline2()
    assert not findings.sample_type.isna().any()

    blinded = dict(bundle)
    blinded["types"] = {u: t for u, t in bundle["types"].items() if u != "TIS-200"}
    out = M2.mode2_findings(_attached2(w), **blinded)

    row = _row(out, 200, 11)
    assert pd.isna(row.sample_type)
    assert pd.isna(row.type_registrations), "a missed cell is not a measured zero"
    assert pd.isna(row.precedent_rate), "no type means no hop and so no rule"
    census = _census2(w, bundle, out)
    assert census["rows_without_a_sample_type"] == 1
    assert len(out) == len(findings), "the row is still emitted"


def test_a_sample_absent_from_the_samples_frame_reports_null_projects_not_empty():
    """500 is registered and edged and has no `samples` row. 185 such samples
    carry 448 of the real extract's candidate rows.

    Mode 1's empty string means MEASURED AND NONE, which is the statement its
    whole population rests on. Here the projects were never read, so the column
    is null and the two are not the same claim.
    """
    w, bundle, findings = _pipeline2()

    assert 500 not in set(w["samples"].sample_id)
    row = _row(findings, 500, 11)
    assert pd.isna(row.project_ids)
    assert row.uuid == "TIS-500", "the uuid comes out of the traversal, not a join"
    # a sample WITH a row reports its projects, so null here is not the default
    assert _row(findings, 200, 11).project_ids == "3"
    census = _census2(w, bundle, findings)
    assert census["rows_without_a_samples_row"] == 1


def test_a_sample_registered_nowhere_reaches_mode_2_and_is_counted_there():
    """295 holds nothing and has two parents holding two assays. Two rows.

    Mode 1's population and Mode 2's overlap, and the ceiling says so: a sample
    registered nowhere contributes its FULL gap in the direction its neighbour
    supports. Measured on the real extract, 2,405 of Mode 1's 6,242 samples reach
    Mode 2 as well -- 2.1% of each direction's samples, against the ~6% the brief
    carried.
    """
    w, bundle, findings = _pipeline2()

    rows = findings[findings.sample_id == 295]
    assert sorted(rows.proposed_internal_assay_id) == [12, 13]
    assert set(rows.action) == {S.A_ADD_CHILD}
    assert (rows.registered_internal_assay_ids == "").all()
    assert (rows.registered_internal_assay_titles == "").all()
    assert 295 in set(X.unregistered_samples(w["samples"], w["membership"],
                                             w["assays"]))
    census = _census2(w, bundle, findings)
    assert census["rows_on_a_sample_registered_nowhere"] == 2
    assert census["samples_registered_nowhere"] == 1


def test_mode_2_asserts_nothing_about_the_co_registration_test_it_never_ran():
    """The compat block is NULL on every Mode 2 row, and that is the contract.

    Lineage runs BEFORE co-registration and a neighbour already holding the assay
    settles it, so the test never runs. `BAND_NO_SUPPORT` would say "measured,
    and the population was too small to read"; a zero rate would say "these never
    coexist", which is the alternative-label finding. Both are claims this mode
    did not make, and Task 8 can fill a null without contradicting anything
    shipped here.
    """
    _, _, findings = _pipeline2()

    assert len(findings) == 28, "every assertion below is vacuous on an empty frame"
    for col in ("co_reg_rate", "co_reg_pop", "co_reg_registered_internal_assay_id",
                "co_reg_alt_label_internal_assay_id", "co_reg_alt_label_pop",
                "compat_band"):
        assert findings[col].isna().all(), f"{col} asserts an untried test"
    assert not (set(findings.compat_band.dropna()) & set(S.COMPAT_BANDS))
    # ...while the test lineage DID run is asserted, on every row
    assert set(findings.lineage) <= {S.LIN_CHILD, S.LIN_PARENT}
    assert S.LIN_NONE not in set(findings.lineage)
    assert set(findings.classification) == {S.CLS_ABSENCE_LINEAGE}
    assert set(findings["mode"]) == {S.MODE_2}


def test_the_mode_2_frame_is_the_shared_contract_and_is_totally_sorted():
    """`FINDING_COLUMNS`, all 36, in order, sorted on both keys of the grain."""
    w, bundle, findings = _pipeline2()

    assert list(findings.columns) == S.FINDING_COLUMNS
    assert len(S.FINDING_COLUMNS) == 36
    assert not findings.duplicated(
        ["sample_id", "proposed_internal_assay_id"]).any()

    emitted = [(int(a), int(b)) for a, b in
               zip(findings.sample_id, findings.proposed_internal_assay_id)]
    assert emitted == sorted(emitted)
    # the sort is TOTAL and not on `sample_id` alone: 280 carries two proposals
    # and they are reached 13 before 11
    assert emitted.index((280, 11)) < emitted.index((280, 13))
    assert M2.mode2_candidates(bundle["children_of"], bundle["parents_of"],
                              bundle["registered"]) != emitted


def test_the_census_reconciles_the_emitted_rows_against_the_independent_ceiling():
    """Every figure `_world2` hand-traces, and the two the ceiling checks.

    `lineage.mode2_ceiling` counts the same population by a different route and
    does not know this module exists, so the identities below are a cross-check
    between two computations rather than a restatement of one. The ceiling counts
    a both-ways pair TWICE, once per direction; the emitted frame counts it once,
    as one write. `both_directions` is exactly that difference.
    """
    w, bundle, findings = _pipeline2()
    ceiling = L.mode2_ceiling(bundle["children_of"], bundle["parents_of"],
                              bundle["registered"])
    census = M2.mode2_census(findings, ceiling, _attached2(w))
    assert set(census) == set(M2.MODE2_CENSUS_KEYS)

    assert census["rows"] == 28
    assert census["samples"] == 26
    assert census["rows_add_parent"] == 12
    assert census["samples_add_parent"] == 12
    assert census["rows_add_child"] == 16
    assert census["samples_add_child"] == 14
    assert census["rows_reachable_both_ways"] == 1
    assert census["rows_with_multiple_supports"] == 2
    assert census["rows_with_precedent"] == 27
    assert census["rows_without_precedent"] == 1

    # the identities
    assert census["rows"] == census["rows_add_parent"] + census["rows_add_child"]
    assert census["rows"] == (census["rows_with_precedent"]
                              + census["rows_without_precedent"])
    assert census["rows"] == len(findings)
    assert census["samples"] == findings.sample_id.nunique()

    # ...and against the ceiling, which counted the same world independently
    assert census["rows"] == ceiling["union_rows"] == 28
    assert census["samples"] == ceiling["union_samples"] == 26
    assert census["rows_add_parent"] == ceiling["add_parent_rows"] == 12
    assert census["rows_reachable_both_ways"] == ceiling["both_directions"] == 1
    assert census["rows_add_child"] == (ceiling["add_child_rows"]
                                        - ceiling["both_directions"]) == 16
    assert ceiling["add_child_rows"] == 17, "the ceiling counts the pair twice"


def test_the_survival_table_reports_the_two_directions_apart_and_drops_no_evidence():
    """A row with no measured rate survives no threshold, including 0.0.

    Never a pooled figure: ADD_PARENT is corroborated 88 times out of 88 over the
    866 flags and ADD_CHILD 15 times out of 263, so one number covering both
    would present the weak direction as carrying the strong one's evidence.
    Measured on the real extract at `rate >= 0.5`, ADD_PARENT survives 8,170 rows
    and ADD_CHILD 2,067 -- of a ceiling of 55,007 and 117,331.

    A THRESHOLD ORDERS READING AND GRANTS NOTHING. Every row above is emitted
    whatever this table says.
    """
    w, bundle, findings = _pipeline2()
    table = M2.precedent_survival(findings)

    assert list(table.columns) == M2.SURVIVAL_COLUMNS
    assert set(table.action) == {S.A_ADD_PARENT, S.A_ADD_CHILD}
    assert len(table) == len(M2.SURVIVAL_THRESHOLDS) * 2
    # no row of the table pools the two directions
    assert table.action.isin((S.A_ADD_PARENT, S.A_ADD_CHILD)).all()

    at_zero = table[table.threshold == 0.0].set_index("action")
    # ADD_PARENT: 12 rows, every one with a rule except (360,11)
    assert at_zero.loc[S.A_ADD_PARENT, "of_rows"] == 12
    assert at_zero.loc[S.A_ADD_PARENT, "rows"] == 11
    assert at_zero.loc[S.A_ADD_CHILD, "of_rows"] == 16
    assert at_zero.loc[S.A_ADD_CHILD, "rows"] == 16
    # ...which is the assertion an unmeasured row defaulting to 0.0 would fail
    assert int(findings.precedent_rate.isna().sum()) == 1

    for t in M2.SURVIVAL_THRESHOLDS:
        for act in (S.A_ADD_PARENT, S.A_ADD_CHILD):
            hit = table[(table.threshold == t) & (table.action == act)].iloc[0]
            sub = findings[(findings.action == act)
                           & findings.precedent_rate.notna()
                           & (findings.precedent_rate >= t)]
            assert hit.rows == len(sub)
            assert hit.samples == sub.sample_id.nunique()


def test_precedent_rules_refuses_a_null_key_a_groupby_would_drop_in_silence():
    """`internal_assay_id` is nullable at source and is a RULE_KEY component.

    `frame.groupby(RULE_KEY)` defaults to `dropna=True`, so the natural pandas
    spelling of this index discards every rule keyed on one of the 17
    junction-less assays -- silently, with no error and a table that still looks
    right. `mine_precedent` counts into a dict for exactly this reason and this
    index must not undo it.

    A duplicate key is the other silent loss and is refused too: two rules for
    one key means one of them would win by row order.
    """
    prec = _precedent2()
    rules = M2.precedent_rules(prec)
    assert len(rules) == len(prec)
    # the junction-less assay's fallback id keys a rule like any other
    assert (20, "D.IMG", "TIS", 490) in rules

    holed = prec.copy()
    holed.loc[holed.index[0], "internal_assay_id"] = None
    with pytest.raises(ValueError, match="internal_assay_id"):
        M2.precedent_rules(holed)
    # THE WRONG RULE, run by hand: groupby drops it and says nothing
    assert len(holed.groupby(S.RULE_KEY)) == len(prec) - 1

    with pytest.raises(ValueError, match="duplicate"):
        M2.precedent_rules(pd.concat([prec, prec.iloc[:1]], ignore_index=True))


def test_registration_projects_and_registered_internal_describe_one_registration_set():
    """The project index and the registration index cannot disagree about what exists.

    Both cross the seek `assay_assets.assay_id` junction through
    `precedent.assay_index`, and the rule key's project comes from the NEIGHBOUR's
    own registration rather than from the assay's project list -- 75 of the real
    extract's 154 internal assay ids span more than one project, up to seven, so
    an assay-level project is not single-valued and would key the wrong rule.
    Measured, 1 of 214,124 (sample, internal assay) registrations spans two
    projects at all.
    """
    w, bundle, findings = _pipeline2()
    reg = bundle["registered"]
    proj = bundle["reg_projects"]

    assert set(proj) == {(s, a) for s, aa in reg.items() for a in aa}
    assert proj[(130, 490)] == frozenset({20})     # through the junction-less assay
    assert proj[(100, 11)] == frozenset({10})
    # ...and the titles decode off the SAME funnel, including the fallback
    assert bundle["titles"][490] == "Junctionless"
    assert bundle["titles"][11] == "Assay 11"

    # THE PROJECT COMES FROM THE REGISTRATION AND NOT FROM THE ASSAY, and this
    # index is where that is decided. Internal assay 11 is instantiated twice, in
    # projects 10 and 40, and 600 holds it through the project-40 record ALONE.
    assert proj[(600, 11)] == frozenset({40})
    assay_projects = {p for p, i, _ in P.assay_index(w["assays"]).values() if i == 11}
    assert assay_projects == {10, 40}, "the assay-level answer is not single-valued"
    # ...so an assay-level rule would have to pick one, and picking gives 10
    assert min(assay_projects) == 10 != 40

    # WHAT THE ROW DOES WITH THIS INDEX IS THE RULE KEY'S PROPERTY AND IS TESTED
    # UNDER THAT NAME, in
    # `test_the_rule_key_is_all_four_components_and_three_of_four_does_not_match`.
    # It lived here until the mutation harness reported a project-blind lookup as
    # MISLABELLED: this test caught it while the test whose NAME claims the rule
    # key passed. Coverage filed under the wrong name is what that branch exists
    # to find, so the assertions moved rather than being duplicated.


def test_the_key_construction_speaks_the_language_mine_precedent_writes():
    """Mine the fixture's OWN edges and every emitted row finds its rule.

    The hand-authored frame proves the two rates are read from the right columns;
    it cannot prove the KEY is the one stage B emits, because a hand-authored
    frame agrees with whatever the classifier looks up. So this test throws it
    away, mines `precedent.mine_precedent` over the same world, and asserts that
    every row finds a rule -- which holds only if the project, both types and the
    assay are all built the way the miner builds them.

    ONE ROW IS EXEMPT AND IT IS NAMED. Sample 500 has no `samples` row, so
    nothing about it changes here; the exemption is empty on this world, and a
    future row that stops resolving fails this test rather than quietly losing
    its evidence.
    """
    w, bundle, findings = _pipeline2()
    mined = P.mine_precedent(w["edges"], w["membership"], w["assays"])
    live = dict(bundle, rules=M2.precedent_rules(mined))
    out = M2.mode2_findings(_attached2(w), **live)

    assert len(out) == 28
    unresolved = out[out.precedent_rate.isna()]
    assert list(zip(unresolved.sample_id, unresolved.proposed_internal_assay_id)) \
        == [], "every key this module builds must exist in the mined frame"

    # the mined frame really is a different frame, or this proves nothing: it
    # carries none of the five decoys and its rates are its own
    assert not (set(M2.precedent_rules(mined)) & {
        (99, "D.IMG", "TIS", 11), (10, "MUS", "TIS", 11),
        (10, "D.IMG", "PAV", 11), (10, "D.IMG", "TIS", 99),
        (10, "D.IMG", "TIS", 490)})
    assert sorted(out.precedent_rate.dropna()) != sorted(
        findings.precedent_rate.dropna())


def test_every_proposal_source_is_in_the_closed_family():
    """A `BY_*` constant that never joins `PROPOSAL_SOURCES` must FAIL, not pass.

    DERIVED FROM THE MODULE AND NOT HAND-LISTED, which is the whole point and is
    the pattern `tests/test_assay_hygiene_schema.py::test_every_stage_c_family_is_closed`
    already applies to `_schema`'s five families. `classify.py`'s family had only
    a literal pin, so a fifth member declared beside the other four and never
    added to the tuple would pass every test in this file -- and this round is
    exactly that scenario, since it added one.

    The `str` filter keeps the tuple itself out of its own membership check, as
    the schema version's does.
    """
    family = {n: v for n, v in vars(X).items()
              if n.startswith("BY_") and isinstance(v, str)}
    assert family, "the derivation found nothing, so it proves nothing"
    assert set(family.values()) == set(X.PROPOSAL_SOURCES), (
        f"BY_* constants {sorted(family)} disagree with the closed tuple "
        f"{X.PROPOSAL_SOURCES}")
    assert len(set(X.PROPOSAL_SOURCES)) == len(X.PROPOSAL_SOURCES)
    assert len(X.PROPOSAL_SOURCES) == 4

    # THE WRONG RULE, run by hand: a literal pin alone. It passes on a family
    # that has gained a member the tuple does not know about, which is what this
    # test exists to stop.
    assert set(family) == {"BY_CLAIM", "BY_PRECEDENT", "BY_BOTH",
                           "BY_LINEAGE_ONLY"}

    # no value collides with another closed family, checked against `_schema`'s
    # own, since a value readable in the wrong column errors nowhere
    others = (set(S.MODES) | set(S.GATE_OUTCOMES) | set(S.CLASSES)
              | set(S.LINEAGE_RELATIONS) | set(S.COMPAT_BANDS)
              | set(S.PROVENANCES)
              | {S.A_NONE, S.A_ADD_PARENT, S.A_ADD_CHILD, S.A_ADD_TO_ASSAY,
                 S.A_FLAG_ONLY})
    assert not (set(X.PROPOSAL_SOURCES) & others)


def test_the_fixture_world_carries_exactly_the_populations_its_docstring_states():
    """`_world2`'s hand-derived table, read off the world instead of trusted.

    THE ONE TEST THAT CAN FAIL A STALE FIXTURE DOCSTRING. Every other test here
    asserts a band or a count that the docstring merely explains, so the
    explanation can drift from the data without a single failure -- and it did:
    the reachability table filed sample 310 under `(PAV,12)` when 310 holds assay
    13, making BOTH that cell and `(PAV,13)` wrong, and the header still said
    thirteen edges and twenty-six proposals after the world had grown to sixteen
    and twenty-eight. Neither could fail anything, in the one fixture whose whole
    premise is that its counts are derived by hand.

    So the two populations a reader checks the table against are pinned here.
    """
    w = _world2()
    _, _, findings = _pipeline2(w)

    # the header sentence
    assert len(w["edges"]) == 16
    assert len(findings) == 28

    # every reachability cell the docstring states, and NO cell it omits
    cells = G.type_registration_index(w["membership"], w["assays"], w["nodes"])
    assert cells == {
        ("TIS", 11): 5, ("TIS", 12): 10, ("TIS", 13): 2,
        ("PAV", 11): 2, ("PAV", 12): 2, ("PAV", 13): 5, ("PAV", 14): 2,
        ("D.IMG", 11): 7, ("D.IMG", 13): 1, ("D.IMG", 490): 1,
        ("MUS", 11): 1, ("MUS", 12): 1,
    }
    # the cells the docstring calls EMPTY are absent rather than zero, which is
    # the distinction `type_registration_index` is built on and the one the
    # unseen-pair flag reads
    for empty in (("TIS", 14), ("TIS", 490), ("D.IMG", 12), ("MUS", 14)):
        assert empty not in cells
    # 310 is in the cell it is actually registered in
    assert 13 in A.registered_internal(w["membership"], w["assays"])[310]


def test_a_proposal_with_no_measured_rate_says_lineage_only_not_precedent():
    """(360,11) has no rule, so `BY_PRECEDENT` would assert what the row denies.

    `BY_PRECEDENT` is defined as "stage B precedent on the hop alone" and this
    row's `precedent_rate` is NULL and its own summary says "NO measured basis".
    Labelling it `BY_PRECEDENT` put two meanings under one name -- the defect
    this package documents for `edge_internal_assay_id`, for `provenance` /
    `source_provenance` and for the `FINDING_COLUMNS` grain change -- and it
    shipped that way for one review cycle. 10 rows of the real extract's 172,338
    carried it.

    The fix is a FOURTH member, not a wider definition of the third.
    """
    _, _, findings = _pipeline2()

    unmeasured = _row(findings, 360, 11)
    assert pd.isna(unmeasured.precedent_rate)
    assert unmeasured.proposed_by == X.BY_LINEAGE_ONLY
    assert unmeasured.proposed_by != X.BY_PRECEDENT
    assert "no precedent" in unmeasured.evidence_summary

    # ...and a row that DOES have a rule still says so, so the new member did not
    # swallow the third
    measured = _row(findings, 200, 11)
    assert pd.notna(measured.precedent_rate)
    assert measured.proposed_by == X.BY_PRECEDENT

    # the family stays closed, enumerable and collision-free
    assert X.PROPOSAL_SOURCES == (X.BY_CLAIM, X.BY_PRECEDENT, X.BY_BOTH,
                                  X.BY_LINEAGE_ONLY)
    assert len(set(X.PROPOSAL_SOURCES)) == 4
    assert set(findings.proposed_by) <= set(X.PROPOSAL_SOURCES)
    # EVERY row with a null rate carries the new member, and every row with the
    # new member has a null rate -- read off the frame, not off the two ids above
    null_rate = set(findings[findings.precedent_rate.isna()].index)
    lineage_only = set(findings[findings.proposed_by == X.BY_LINEAGE_ONLY].index)
    assert null_rate == lineage_only == {unmeasured.name}


def test_a_claim_with_no_precedent_rule_is_refused_rather_than_mislabelled():
    """The fourth combination has no value, and inventing one is how buckets lie.

    (precedent rule, gated claim) has four combinations and three have honest
    labels. The fourth -- a claim on a hop with NO rule -- occurs 0 times on the
    real extract, so no member was invented for it: `BY_BOTH` would assert a
    precedent that is not there and `BY_LINEAGE_ONLY` would hide the claim.

    It is refused in the emitter rather than only in a test, following
    `precedent.assay_index`, which raises on a collision that also holds today
    only by luck of the data. This test CONSTRUCTS the combination, which is the
    only way to know the guard fires rather than merely exists.
    """
    w = _world2()
    # give 360 -- the sample whose (10, D.IMG, MUS, 11) hop has no rule -- a
    # gate-passing claim naming the very assay its rule-less row proposes
    w["samples"] = w["samples"].copy()
    w["samples"].loc[w["samples"].sample_id == 360, "json_metadata"] = \
        '{"Type": "omega"}'
    w["vocabulary"] = pd.concat([w["vocabulary"], pd.DataFrame(
        [("Type", "omega", 11, "Assay 11", 700, 45, 0.97, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS)], ignore_index=True)

    # the claim must REACH a mode, or the guard is not the thing being tested
    attached = _attached2(w)
    hit = attached[(attached.sample_id == 360) & (attached.internal_assay_id == 11)]
    assert len(hit) == 1 and G.reaches_modes(attached)[hit.index[0]]

    with pytest.raises(ValueError, match="fifth member"):
        _pipeline2(w)


def test_the_survival_table_says_how_much_evidence_its_survivors_rest_on():
    """A row count is not an evidence count, and the table now carries both.

    Measured on the real extract at `rate >= 0.95`, the WEAK direction survives
    371 rows against the strong direction's 46 -- and the obvious reading, that
    `reverse_rate` reaches 1.0 easily on a thin denominator, is FALSE: those 371
    sit on a median direction denominator of 27,344 against 919, and not one is
    thin. The real driver is hop concentration, 371 rows over 13 evidence groups
    with one group keying 170 of them, against 46 rows over 2.

    `of_rows` is the denominator of the SHARE and answers none of that, so the
    printed table deferred the question to whoever held the parquet.
    """
    _, _, findings = _pipeline2()
    table = M2.precedent_survival(findings)

    assert list(table.columns) == M2.SURVIVAL_COLUMNS
    assert "rule_groups" in M2.SURVIVAL_COLUMNS

    for r in table.itertuples(index=False):
        sub = findings[(findings.action == r.action)
                       & findings.precedent_rate.notna()
                       & (findings.precedent_rate >= r.threshold)]
        groups = sub[["precedent_n_both", "precedent_n_child_only",
                      "precedent_n_parent_only"]].drop_duplicates()
        assert r.rule_groups == len(groups)
        # a lower bound on rules and never more than the rows it summarises
        assert r.rule_groups <= r.rows

    # in this world the two directions genuinely differ, so the column is not a
    # restatement of `rows`
    at_zero = table[table.threshold == 0.0].set_index("action")
    assert at_zero.loc[S.A_ADD_PARENT, "rule_groups"] \
        != at_zero.loc[S.A_ADD_PARENT, "rows"]
    assert (at_zero.loc[S.A_ADD_CHILD, "rule_groups"]
            != at_zero.loc[S.A_ADD_PARENT, "rule_groups"])


def test_a_world_with_no_lineage_at_all_yields_an_empty_mode_2_frame():
    """Zero proposals is a shape, not a crash, and Task 9 has to report it.

    Mode 2's whole trigger is an edge, so a world with none emits nothing and
    must still carry `FINDING_COLUMNS` in order: a bare `DataFrame([])` carries
    no columns and a consumer concatenating the modes would silently produce a
    frame with the wrong header.

    It is also where the dtypes are at their most degenerate. Every column of an
    empty frame is `object`, so `precedent_rate >= threshold` becomes a
    comparison against nothing at all; the census and the survival table are both
    exercised on it rather than assumed to cope.
    """
    w = _world2()
    w["edges"] = pd.DataFrame(columns=S.EDGE_COLUMNS)
    _, bundle, findings = _pipeline2(w)

    assert len(findings) == 0
    assert list(findings.columns) == S.FINDING_COLUMNS

    census = _census2(w, bundle, findings)
    assert set(census) == set(M2.MODE2_CENSUS_KEYS)
    assert set(census.values()) == {0}, "every population is zero and none is absent"

    # the curve still reports BOTH directions at EVERY threshold, at zero. A
    # table that reported nothing would be indistinguishable, in the operator's
    # report, from a direction nobody measured.
    table = M2.precedent_survival(findings)
    assert len(table) == len(M2.SURVIVAL_THRESHOLDS) * 2
    assert set(table.action) == {S.A_ADD_PARENT, S.A_ADD_CHILD}
    assert set(table["rows"]) == {0} and set(table["of_rows"]) == {0}


def test_nothing_in_mode_2_is_named_for_a_decision_or_reads_a_reporting_number():
    """No `decide_*`, and neither reporting constant is compared against here.

    `MIN_CO_REG_SUPPORT` and `CO_OCCUR_BAND` have exactly one approved reader,
    `compatibility.compat_band`, and it BANDS a rate. A threshold in this module
    deciding whether a row is emitted would be the defect
    `test_the_two_reporting_numbers_gate_nothing` exists to catch, one module
    over.
    """
    src = (PACKAGE / "mode2.py").read_text()
    assert not re.findall(r"^def decide_", src, re.M)
    assert "MIN_CO_REG_SUPPORT" not in src and "CO_OCCUR_BAND" not in src
    # ...and the module Mode 2 was split out of stays clean of them too, so the
    # split cannot be the thing that lets a reporting number into an emitter
    assert "MIN_CO_REG_SUPPORT" not in (PACKAGE / "classify.py").read_text()
    assert "CO_OCCUR_BAND" not in (PACKAGE / "classify.py").read_text()

    # THE SURVIVAL THRESHOLDS ARE REPORTING AND THE EMITTER NEVER SEES THEM.
    # `mode2_findings` is the function that decides which rows exist, and a
    # threshold read inside it would be a number granting permission -- the exact
    # defect `test_the_two_reporting_numbers_gate_nothing` polices one module
    # over. Read off the source between the two `def` lines rather than by
    # inspection, so a later edit that moves the comparison fails here.
    emitter = src.split("def mode2_findings")[1].split("\ndef ")[0]
    assert "SURVIVAL_THRESHOLDS" not in emitter
    assert "precedent_rate >=" not in emitter and "rate >= " not in emitter


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


def _real2():
    """The extract plus the edges Mode 2 needs, or a skip."""
    for f in ("samples.parquet", "membership.parquet", "assays.parquet",
              "nodes.parquet", "edges.parquet"):
        if not (EXTRACT / f).exists():
            pytest.skip(f"no extract at {EXTRACT}; run driver_extract.py first")
    if not (ARTIFACTS / "claims.parquet").exists():
        pytest.skip("no claims.parquet; run claims first")
    r = _real()
    r["edges"] = pd.read_parquet(EXTRACT / "edges.parquet")
    return r


def test_the_real_extract_reproduces_the_ceiling_and_both_directions_separately():
    """Every Mode 2 figure this module states, re-derived from the parquet.

    THE CEILING IS A CEILING. 172,338 rows are what lineage alone makes
    available BEFORE precedent is read, and precedent cuts the weak direction to
    about 2% of it. Quoting the ceiling as an expected output overstates
    ADD_CHILD by more than an order of magnitude, so the word rides with the
    number here as it does everywhere else.

    THE EMITTED SPLIT IS NOT THE CEILING SPLIT and the difference is exactly
    `both_directions`: the ceiling counts a pair reachable both ways once per
    direction, and the emitted frame counts it once, because it is one write.

    Three figures the brief carried are corrected here, each measured:

      candidate rows at rate >= 0.5   brief 79,488 / 3,663; measured 8,170 /
                                      2,067. The ADD_PARENT figure exceeds the
                                      whole ADD_PARENT ceiling of 55,007 and so
                                      cannot be a row count over this relation.
      rows creating an unseen (type,  brief 55.6% / 67.6%; measured 55.4% /
      assay) pair                     62.4% over the emitted rows.
      Mode 1 samples inside the       brief ~6% of ADD_CHILD samples; measured
      ceiling                         2.1%, and 2,405 of Mode 1's 6,242.
    """
    r = _real2()
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        r["edges"], r["samples"], r["membership"])
    registered = A.registered_internal(r["membership"], r["assays"])
    ceiling = L.mode2_ceiling(children_of, parents_of, registered)

    # the CEILING, unfiltered by precedent, as Task 4 reconciled it
    assert ceiling["add_parent_rows"] == 55007
    assert ceiling["add_parent_samples"] == 42654
    assert ceiling["add_child_rows"] == 117463
    assert ceiling["add_child_samples"] == 102582
    assert ceiling["union_rows"] == 172338
    assert ceiling["union_samples"] == 115626
    assert ceiling["both_directions"] == 132

    type_reg = G.type_registration_index(r["membership"], r["assays"], r["nodes"])
    gated = G.gate_claims(r["claims"], r["vocabulary"], type_reg,
                          G.sample_type_index(r["nodes"]))
    findings = M2.mode2_findings(
        X.attach_gate(r["claims"], gated),
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=registered,
        rules=M2.precedent_rules(
            P.mine_precedent(r["edges"], r["membership"], r["assays"])),
        reg_projects=M2.registration_projects(r["membership"], r["assays"]),
        types=G.sample_type_index(r["nodes"]),
        type_reg=type_reg,
        titles=M2.assay_titles(r["assays"]),
        projects=X.project_index(r["samples"]),
    )
    census = M2.mode2_census(findings, ceiling, X.attach_gate(r["claims"], gated))

    # THE EMITTED SPLIT, never pooled
    assert census["rows_add_parent"] == 55007
    assert census["samples_add_parent"] == 42654
    assert census["rows_add_child"] == 117331 == 117463 - 132
    assert census["samples_add_child"] == 102561
    assert census["rows"] == 172338
    assert census["samples"] == 115626

    # the two evidence populations
    assert census["rows_without_precedent"] == 10
    assert census["rows_with_multiple_supports"] == 31180
    assert census["rows_proposed_by_both"] == 1656
    assert census["rows_with_a_blocked_claim"] == 4255
    assert census["rows_without_a_samples_row"] == 448
    assert census["rows_without_a_sample_type"] == 0

    # the unseen (type, assay) pair, BY DIRECTION and never as one share
    assert census["rows_creating_an_unseen_pair_add_parent"] == 30496
    assert census["rows_creating_an_unseen_pair_add_child"] == 73195

    # Mode 1's population inside Mode 2's, which the ceiling includes by design
    assert census["rows_on_a_sample_registered_nowhere"] == 4243
    assert census["samples_registered_nowhere"] == 2405
    assert len(X.unregistered_samples(r["samples"], r["membership"],
                                      r["assays"])) == 6242

    # SURVIVAL, the two directions apart at every threshold
    table = M2.precedent_survival(findings).set_index(["threshold", "action"])
    assert table.loc[(0.5, S.A_ADD_PARENT), "rows"] == 8170
    assert table.loc[(0.5, S.A_ADD_CHILD), "rows"] == 2067
    assert table.loc[(0.75, S.A_ADD_PARENT), "rows"] == 2171
    assert table.loc[(0.75, S.A_ADD_CHILD), "rows"] == 1340
    assert table.loc[(0.95, S.A_ADD_PARENT), "rows"] == 46
    assert table.loc[(0.95, S.A_ADD_CHILD), "rows"] == 371

    # THE THREE FIGURES `main` PRINTS AS LITERALS INTO THE OPERATOR-FACING
    # REPORT. It says the weak direction's 371 rows rest on 13 evidence groups,
    # one of which keys 170 of them, against 46 rows on 2 -- and until this pin
    # nothing checked any of the three. A hard-coded figure in a printed report
    # with no test behind it is the same class as the stale fixture docstring
    # this task already fixed, one layer out.
    assert table.loc[(0.95, S.A_ADD_PARENT), "rule_groups"] == 2
    assert table.loc[(0.95, S.A_ADD_CHILD), "rule_groups"] == 13
    biggest = Counter(
        zip(*(findings[(findings.action == S.A_ADD_CHILD)
                       & findings.precedent_rate.notna()
                       & (findings.precedent_rate >= 0.95)][c]
              for c in ("precedent_n_both", "precedent_n_child_only",
                        "precedent_n_parent_only")))).most_common(1)[0][1]
    assert biggest == 170, "one evidence group keys 170 of the 371"
    # ...and the numbers in `main`'s printed SENTENCE are those same measured
    # values, read out of the source rather than eyeballed. This is what makes
    # the pin cover the OPERATOR-FACING report and not merely the frame: an edit
    # that changes the prose without re-measuring now fails here.
    #
    # The source is normalised first -- string concatenation and line wrapping
    # split that sentence across four literals -- so the pattern matches the
    # sentence a curator reads rather than the way it is spelled in the file.
    printed = (REPO / "scripts" / "assay_hygiene" / "classify.py").read_text()
    flat = re.sub(r'"\s*"', "", printed)
    flat = re.sub(r"\s+", " ", flat)
    claim = re.search(
        r"the weak direction's ([\d,]+) rows rest on (\d+) groups, one of "
        r"which keys (\d+) of them, against (\d+) rows on (\d+)", flat)
    assert claim is not None, "main's printed sentence changed shape; re-pin it"
    weak_rows, weak_groups, biggest_group, strong_rows, strong_groups = (
        int(g.replace(",", "")) for g in claim.groups())
    assert weak_rows == int(table.loc[(0.95, S.A_ADD_CHILD), "rows"]) == 371
    assert weak_groups == int(table.loc[(0.95, S.A_ADD_CHILD), "rule_groups"]) == 13
    assert biggest_group == biggest == 170
    assert strong_rows == int(table.loc[(0.95, S.A_ADD_PARENT), "rows"]) == 46
    assert strong_groups == int(
        table.loc[(0.95, S.A_ADD_PARENT), "rule_groups"]) == 2

    # ...and the unmeasured rows survive nothing, including 0.0
    assert table.loc[(0.0, S.A_ADD_PARENT), "rows"] == 55007 - 5
    assert table.loc[(0.0, S.A_ADD_CHILD), "rows"] == 117331 - 5

    # THE FLAGSHIP DATUM, read off the mined rules rather than quoted
    rules = M2.precedent_rules(
        P.mine_precedent(r["edges"], r["membership"], r["assays"]))
    assert round(rules[(2, "TIS", "PAV", 74)].propagation_rate, 3) == 0.931
    assert round(rules[(2, "TIS", "PAV", 56)].reverse_rate, 3) == 0.006


# --- Task 8: the precedence, the compatibility lane and the unified pass ------
#
# A THIRD WORLD, and the reason is arithmetic rather than taste.
# `compatibility.compat_band` reads a rate only over `MIN_CO_REG_SUPPORT` = 30
# samples of the type, and `_world2`'s largest reachability cell is 10. Every
# band it can produce there is `BAND_NO_SUPPORT`, so a world that reaches the
# other three bands has to carry populations an order of magnitude larger --
# and growing `_world2` to 44 registered TIS samples would move every count in
# its hand-derived census table.
#
# THE RATES ARE READ OFF THE WORLD AND NEVER HARD-CODED HERE. `_world3`'s
# denominators are the whole of `pop(TIS, 11)`, which grows by one every time a
# TIS sample registered in 11 is added for some unrelated reason. A fixture
# asserting `rate == 0.75` would then fail for a reason that has nothing to do
# with the rule under test, and -- worse -- a fixture asserting it in a
# DOCSTRING would drift silently. The tests assert the BAND, which is stable
# under any denominator that keeps the rate on its own side of the boundary,
# and `test_world_3_carries_exactly_the_cells_and_rates_its_docstring_states`
# pins the cells themselves.


def _world3():
    """One synthetic world for the precedence. Every count here is derived here.

    Assays 11..16 are junctioned in project 10 (seek 1011..1016).

    THE BACKGROUND EXISTS TO REACH THREE OF THE FOUR COMPATIBILITY BANDS, which
    needs populations over `MIN_CO_REG_SUPPORT` = 30:

         1..40   TIS in 11    of which  1..30 are ALSO in 12
                                        1..10 are ALSO in 14
                                        none is in 13
        41..75   TIS in 13    35 samples, so `(TIS, 13)` is a reachable cell
                              and a zero rate against it is a MEASURED zero
       200..204  MUS in 11    5 samples -- deliberately under the floor
       205..209  MUS in 12    5 samples, so `(MUS, 12)` is reachable

    The four compatibility subjects, each registered in 11 ALONE, each claiming
    an assay it does not hold, none of them carrying an edge:

        600  Type alpha  -> 12   rate over pop(TIS,11)  BAND_ROUTINE
        601  Type beta   -> 13   a measured 0.0         BAND_NEVER
        602  Type gamma  -> 14   between 0 and 0.5      BAND_SOMETIMES
        200  Type alpha  -> 12   MUS, pop 5             BAND_NO_SUPPORT

    600 and 200 make the same claim and land in different bands, and 602 and 200
    land in different BANDS and the same CLASS. Both pairs are deliberate: a
    world where band and class move together cannot show that
    `BAND_ESTABLISHES` is being consulted.

    THE FOUR PRECEDENCE CASES, one per adjacent pair in `PRECEDENCE`, because a
    declared order that changes no answer when reordered is a comment:

        (700, 15)  GATE over LINEAGE.  700 is A.SPC registered in 16 and claims
                   15 through `Type: spectra`; NO A.SPC sample is registered in
                   15 anywhere, so the gate rejects the claim -- while 700's
                   PARENT 701 is a D.SPC registered in 15, so a lineage
                   neighbour does carry the pair. This is the shape of the 24
                   FlowJo / mass-spectra rows the spec calls the third design
                   error, where the analysis sample claims the MEASUREMENT
                   assay its data parent holds.
        (730, 15)  GATE over MODE 1.   730 is A.SPC registered in NOTHING and
                   makes the same rejected claim, and its parent 731 is a second
                   D.SPC registered in 15. Without this row the first swap
                   changes nothing: 700 is registered, so Mode 1 declines it for
                   a second reason. Its EDGE is here for a different reason
                   again -- without it `lineage_refused_by_the_gate` and
                   `lineage_taken_by_mode_1` would both read 1, and two buckets
                   holding the same value cannot discriminate a rule that
                   confuses them.
        (710, 12)  MODE 1 over LINEAGE. 710 is registered in nothing, claims 12,
                   and its parent 711 registers 12. Both steps want the key.
        (720, 12)  LINEAGE over COMPAT. 720 is TIS in 11, claims 12, and its
                   parent 721 registers 12. Both steps want the key.

    The lineage lane offers SIX candidate pairs over the four edges, and two of
    them carry no claim at all:

        (700, 15) ADD_CHILD    (701, 16) ADD_PARENT   (710, 12) ADD_CHILD
        (720, 12) ADD_CHILD    (721, 11) ADD_PARENT   (730, 15) ADD_CHILD

    ...of which the precedence keeps 3, the gate refuses 2 and Mode 1 takes 1.

    THE INPUT AND THE STEPS, hand-traced and re-derived by
    `test_the_classes_partition_every_claim_backed_absence_and_every_lineage_pair`:

        input keys                        10
          PRE_GATE                         2   (700,15) (730,15)
          PRE_MODE_1                       1   (710,12)
          PRE_LINEAGE                      3   (701,16) (720,12) (721,11)
          PRE_COMPAT                       4   (600,12) (601,13) (602,14) (200,12)
          PRE_MODE_3                       0

        emitted rows                       8
          MODE_1                           1   (710,12)
          MODE_2                           4   3 lineage + (600,12)
          no mode                          3   (601,13) (602,14) (200,12)
          MODE_3                           0

        CLS_ABSENCE_LINEAGE                3
        CLS_ABSENCE_COMPAT                 1
        CLS_ALT_LABEL                      1
        CLS_UNRESOLVED                     2
        no classification (Mode 1)         1

    ALSO: 620 is TIS in 11 and claims 11, which it already holds. It is an
    absence of nothing, it is in no input key, and it is counted by name --
    123,439 claims on the real extract are this shape, which is 89% of them.
    """
    nodes, membership, samples, edges = [], [], [], []
    known: dict[int, str] = {}

    def add(sid, stype, assay_ids=(), meta="{}", projects="3"):
        known[sid] = stype
        nodes.append((f"{stype}-{sid}", sid, stype))
        samples.append((sid, f"{stype}-{sid}", meta, None, projects))
        for a in assay_ids:
            membership.append((sid, a))

    def edge(child, parent):
        edges.append((child, parent, f"{known[child]}-{child}",
                      f"{known[parent]}-{parent}", known[child], known[parent],
                      None, None, None))

    for sid in range(1, 41):
        held = [11 + SEEK_OFFSET]
        if sid <= 30:
            held.append(12 + SEEK_OFFSET)
        if sid <= 10:
            held.append(14 + SEEK_OFFSET)
        add(sid, "TIS", held)
    for sid in range(41, 76):
        add(sid, "TIS", [13 + SEEK_OFFSET])
    for sid in range(200, 205):
        add(sid, "MUS", [11 + SEEK_OFFSET],
            meta='{"Type": "alpha"}' if sid == 200 else "{}")
    for sid in range(205, 210):
        add(sid, "MUS", [12 + SEEK_OFFSET])

    add(600, "TIS", [11 + SEEK_OFFSET], meta='{"Type": "alpha"}')
    add(601, "TIS", [11 + SEEK_OFFSET], meta='{"Type": "beta"}')
    add(602, "TIS", [11 + SEEK_OFFSET], meta='{"Type": "gamma"}')
    # claims an assay it ALREADY HOLDS: an absence of nothing
    add(620, "TIS", [11 + SEEK_OFFSET], meta='{"Type": "delta"}')

    add(700, "A.SPC", [16 + SEEK_OFFSET], meta='{"Type": "spectra"}')
    add(701, "D.SPC", [15 + SEEK_OFFSET])
    add(730, "A.SPC", meta='{"Type": "spectra"}')
    add(731, "D.SPC", [15 + SEEK_OFFSET])
    add(710, "TIS", meta='{"Type": "alpha"}')
    add(711, "TIS", [12 + SEEK_OFFSET])
    add(720, "TIS", [11 + SEEK_OFFSET], meta='{"Type": "alpha"}')
    add(721, "TIS", [12 + SEEK_OFFSET])

    for c, p in ((700, 701), (710, 711), (720, 721), (730, 731)):
        edge(c, p)

    assays = pd.DataFrame(
        [(a + SEEK_OFFSET, f"Assay {a}", 3, 2, 1, 10, "P", a, f"Assay {a}")
         for a in range(11, 17)],
        columns=S.ASSAY_COLUMNS,
    )
    vocabulary = pd.DataFrame(
        [("Type", "alpha", 12, "Assay 12", 900, 50, 0.99, S.P_LEARNED),
         ("Type", "beta", 13, "Assay 13", 800, 45, 0.98, S.P_LEARNED),
         ("Type", "gamma", 14, "Assay 14", 700, 40, 0.97, S.P_LEARNED),
         # beyond reproach as a MAPPING, so the only thing that can stop a claim
         # resting on it is reachability -- which is the point of (700,15)
         ("Type", "spectra", 15, "Assay 15", 600, 35, 0.96, S.P_LEARNED),
         ("Type", "delta", 11, "Assay 11", 500, 30, 0.95, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    # Only the hop a REACHING claim rides on needs a rule: `_proposal_source`
    # refuses the (no rule, gated claim) combination, and (720,12) is the one
    # row in this world that is both claim-backed and lineage-backed.
    precedent = pd.DataFrame(
        [_rule(10, "TIS", "TIS", 12, "Assay 12", 9, 1, 81),
         _rule(10, "TIS", "TIS", 11, "Assay 11", 4, 16, 1)],
        columns=S.PRECEDENT_COLUMNS,
    )
    return {
        "nodes": pd.DataFrame(nodes, columns=S.NODES_COLUMNS),
        "membership": pd.DataFrame(membership, columns=S.MEMBERSHIP_COLUMNS),
        "samples": pd.DataFrame(samples, columns=S.SAMPLE_COLUMNS),
        "edges": pd.DataFrame(edges, columns=S.EDGE_COLUMNS),
        "assays": assays,
        "vocabulary": vocabulary,
        "precedent": precedent,
    }


def _pipeline3(w=None):
    """The whole unified pass over a world. -> (w, parts).

    One helper, so no test rebuilds the wiring and a test naming a behaviour
    cannot exercise a different composition of the stages than its siblings.
    """
    w = w or _world3()
    attached = _attached2(w)
    type_reg = G.type_registration_index(w["membership"], w["assays"], w["nodes"])
    registered = A.registered_internal(w["membership"], w["assays"])
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        w["edges"], w["samples"], w["membership"])
    candidates = M2.mode2_candidates(children_of, parents_of, registered)
    population = X.unregistered_samples(w["samples"], w["membership"], w["assays"])
    projects = X.project_index(w["samples"])
    titles = M2.assay_titles(w["assays"])
    table = CP.co_registration(w["membership"], w["assays"], w["nodes"])

    keys = X.absence_keys(attached, population=population,
                          registered=registered, candidates=candidates)
    steps = X.precedence_steps(keys)
    m1 = X.mode1_findings(attached, population, projects)
    m2 = M2.mode2_findings(
        attached, children_of=children_of, parents_of=parents_of,
        uuid_of=uuid_of, registered=registered,
        rules=M2.precedent_rules(w["precedent"]),
        reg_projects=M2.registration_projects(w["membership"], w["assays"]),
        types=G.sample_type_index(w["nodes"]), type_reg=type_reg,
        titles=titles, projects=projects)
    compat = X.compat_findings(attached, steps=steps, registered=registered,
                               table=table, titles=titles, projects=projects)
    lanes = {X.PRE_MODE_1: m1, X.PRE_LINEAGE: m2, X.PRE_COMPAT: compat,
             X.PRE_MODE_3: X.mode3_findings()}
    findings = X.unify_findings(steps, lanes)
    census = X.findings_census(keys, steps, findings, lanes,
                               agreeing=X.claims_agreeing_with_a_registration(
                                   attached, registered))
    return w, {"attached": attached, "registered": registered,
               "candidates": candidates, "population": population,
               "keys": keys, "steps": steps, "table": table, "titles": titles,
               "projects": projects, "lanes": lanes, "findings": findings,
               "census": census}


def _key_step(parts, sample_id, assay_id):
    """The precedence step for one key, or a readable failure."""
    key = (sample_id, assay_id)
    assert key in parts["steps"], f"{key} is not an input key"
    return parts["steps"][key]


def _found(findings, sample_id, assay_id):
    """The one unified row for a (sample, proposed assay), or a readable failure."""
    hit = findings[(findings.sample_id == sample_id)
                   & (findings.proposed_internal_assay_id == assay_id)]
    assert len(hit) == 1, f"expected exactly one ({sample_id}, {assay_id}) row"
    return hit.iloc[0]


def test_world_3_carries_exactly_the_cells_and_rates_its_docstring_states():
    """The fixture's own table, read off the world instead of trusted.

    THE ONE TEST THAT CAN FAIL A STALE `_world3` DOCSTRING, for the reason
    `test_the_fixture_world_carries_exactly_the_populations_its_docstring_states`
    exists one world over: every other test here asserts a band or a step that
    the docstring merely explains, so the explanation can drift from the data
    without a single failure -- and in `_world2` it did, twice.

    The RATES are derived here and not stated in the docstring, because their
    denominator is the whole of `pop(TIS, 11)` and grows with any TIS sample
    added to 11 for an unrelated reason. What the docstring states is which side
    of a boundary each rate falls on, and that is what is asserted.
    """
    w = _world3()
    cells = G.type_registration_index(w["membership"], w["assays"], w["nodes"])
    assert cells == {
        ("TIS", 11): 45, ("TIS", 12): 32, ("TIS", 13): 35, ("TIS", 14): 10,
        ("MUS", 11): 5, ("MUS", 12): 5,
        ("A.SPC", 16): 1, ("D.SPC", 15): 2,
    }
    # the cell the whole (700,15) case rests on is ABSENT rather than zero,
    # which is what makes its claim GATE_UNREACHABLE
    assert ("A.SPC", 15) not in cells

    table = CP.co_registration(w["membership"], w["assays"], w["nodes"])
    routine = table[("TIS", 11, 12)]
    never = table[("TIS", 11, 13)]
    sometimes = table[("TIS", 11, 14)]
    no_support = table[("MUS", 11, 12)]
    assert CP.compat_band(*routine) == S.BAND_ROUTINE
    assert CP.compat_band(*never) == S.BAND_NEVER
    assert CP.compat_band(*sometimes) == S.BAND_SOMETIMES
    assert CP.compat_band(*no_support) == S.BAND_NO_SUPPORT
    # ...and all four are genuinely different bands, so a world where the band
    # never moves cannot pass this file
    assert len({CP.compat_band(*c) for c in
                (routine, never, sometimes, no_support)}) == 4
    # the zero is MEASURED and the unread one is not: both rates are 0.0 and
    # only the support tells them apart, which is the distinction
    # `BAND_NO_SUPPORT` exists for
    assert never[0] == no_support[0] == 0.0
    assert never[1] >= S.MIN_CO_REG_SUPPORT > no_support[1]


def test_the_precedence_is_a_declared_order_and_three_of_its_four_swaps_move_a_key():
    """`PRECEDENCE` is data, and reordering it changes a measured answer.

    THE POINT OF THE TASK, in one test. An `if` chain in `precedence_step` would
    encode the same order and could be reordered by a later edit with nothing
    failing; a declared tuple that three of its four adjacent swaps demonstrably
    move cannot.

    The fourth swap moves nothing, and that is the finding rather than a gap:
    `PRE_MODE_3` claims no key under any evidence at all, because Mode 3 has no
    detector. The exhaustive check below proves that over all sixteen possible
    evidence tuples rather than over this world's ten.
    """
    _, parts = _pipeline3()
    keys = parts["keys"]
    assert X.PRECEDENCE == (X.PRE_GATE, X.PRE_MODE_1, X.PRE_LINEAGE,
                            X.PRE_COMPAT, X.PRE_MODE_3)
    assert len(set(X.PRECEDENCE)) == len(X.PRECEDENCE) == 5

    moved = []
    for i in range(len(X.PRECEDENCE) - 1):
        wrong = list(X.PRECEDENCE)
        wrong[i], wrong[i + 1] = wrong[i + 1], wrong[i]
        n = sum(1 for e in keys.values()
                if X.precedence_step(e) != X.precedence_step(e, tuple(wrong)))
        moved.append(n)
    # GATE over MODE 1, MODE 1 over LINEAGE, LINEAGE over COMPAT, and the fourth
    assert moved == [1, 1, 1, 0], moved

    # ...and each of the three is a NAMED key rather than an anonymous count
    assert _key_step(parts, 730, 15) == X.PRE_GATE
    assert _key_step(parts, 710, 12) == X.PRE_MODE_1
    assert _key_step(parts, 720, 12) == X.PRE_LINEAGE

    # MODE 3 CLAIMS NO KEY UNDER ANY EVIDENCE. Sixteen tuples, exhaustively, so
    # this is a proof rather than an observation about one world.
    reached = set()
    for bits in range(16):
        e = X.Evidence(*(bool(bits >> b & 1) for b in range(4)))
        if e.claim_reaches and not e.claim:
            continue                      # not a state the input can produce
        try:
            reached.add(X.precedence_step(e))
        except ValueError:
            reached.add(None)             # no evidence at all: not an input key
    assert X.PRE_MODE_3 not in reached
    assert reached == {None, X.PRE_GATE, X.PRE_MODE_1, X.PRE_LINEAGE,
                       X.PRE_COMPAT}


def test_a_gate_rejected_claim_reaches_no_mode_even_when_a_lineage_neighbour_carries_the_pair():
    """The regression for the third design error. (700,15) is the 24's shape.

    Measured over the real extract: all 24 of the FlowJo and mass-spectra flags
    the spec names ARE lineage candidates -- a D.FLOW or D.SPC data parent
    registers the measurement assay the analysis child claims -- so under
    increment 1's precedence, where lineage fired first and nothing tested the
    vocabulary, all 24 were filed `ABSENCE_LINEAGE` and routed to Mode 2 as
    write candidates. `mode3-disposition.csv` files them inside the 351.

    Under this precedence the gate claims the key outright and it reaches no
    mode: no row is emitted for it at all. That is stronger than leaving the
    claim block null on a row the neighbour justifies, and it is what the
    spec asks for -- the 24 must be pulled out BY THE VOCABULARY GATE and not
    by the lineage test.

    The wrong rule -- lineage first, the gate consulted afterwards or not at all
    -- is run by hand and asserted to give a DIFFERENT answer.
    """
    _, parts = _pipeline3()
    findings, attached = parts["findings"], parts["attached"]

    # the claim exists, names 15, and the gate rejects it on REACHABILITY: no
    # A.SPC sample is registered in 15 anywhere
    claim = attached[(attached.sample_id == 700)
                     & (attached.internal_assay_id == 15)]
    assert len(claim) == 1
    assert claim.iloc[0].gate == S.GATE_UNREACHABLE
    assert G.blocks_mode(claim.iloc[0].gate)

    # ...and a lineage neighbour DOES carry the pair, so this is the "even when"
    assert (700, 15) in set(parts["candidates"])
    assert X.Evidence(True, False, False, True) == parts["keys"][(700, 15)]

    # the key is the gate's, and NOTHING is emitted for it
    assert _key_step(parts, 700, 15) == X.PRE_GATE
    assert len(findings[(findings.sample_id == 700)
                        & (findings.proposed_internal_assay_id == 15)]) == 0
    # nor does the raw value that produced it reach any row anywhere
    assert "spectra" not in set(findings.raw_value.dropna())

    # THE WRONG RULE, run by hand: lineage before the gate. The lineage LANE
    # offers the row, and only the precedence refuses it.
    lineage_lane = parts["lanes"][X.PRE_LINEAGE]
    offered = lineage_lane[(lineage_lane.sample_id == 700)
                           & (lineage_lane.proposed_internal_assay_id == 15)]
    assert len(offered) == 1, "the lane must offer it or this proves nothing"
    assert offered.iloc[0]["mode"] == S.MODE_2
    assert offered.iloc[0].classification == S.CLS_ABSENCE_LINEAGE
    wrong = list(X.PRECEDENCE)
    wrong[0], wrong[2] = wrong[2], wrong[0]
    assert X.precedence_step(parts["keys"][(700, 15)],
                             tuple(wrong)) == X.PRE_LINEAGE


def test_a_row_corroborated_by_lineage_is_mode_2_and_carries_no_error_class():
    """(720,12): a neighbour holds it, so the absence is a missing registration.

    `CLS_ABSENCE_LINEAGE` and not any contradiction class, and the distinction
    is the operator's first correction: a PAV sample with tissue collected from
    it belongs in Patient Visit AND Tissue Collection, one incoming and one
    outgoing, so the absence of the second is a registration to add.

    The row also outranks the compatibility lane, which is the third adjacent
    swap: 720 is registered, carries a gate-passing claim and has a neighbour,
    so both LINEAGE and COMPAT want the key.
    """
    _, parts = _pipeline3()
    row = _found(parts["findings"], 720, 12)

    assert _key_step(parts, 720, 12) == X.PRE_LINEAGE
    assert row["mode"] == S.MODE_2
    assert row.classification == S.CLS_ABSENCE_LINEAGE
    assert row.classification in S.CLASSES
    assert row.action == S.A_ADD_CHILD
    assert row.lineage == S.LIN_PARENT
    # the claim agrees, so the row says BOTH pieces of evidence produced it
    assert row.proposed_by == M2.BY_BOTH
    # ...and the co-registration test never ran, so it asserts nothing
    assert pd.isna(row.compat_band) and pd.isna(row.co_reg_rate)

    # THE WRONG RULE: compatibility before lineage. The pair `(TIS, 11, 12)`
    # bands ROUTINE, so the row would read CLS_ABSENCE_COMPAT and lose the
    # neighbour that actually settles it.
    wrong = list(X.PRECEDENCE)
    wrong[2], wrong[3] = wrong[3], wrong[2]
    assert X.precedence_step(parts["keys"][(720, 12)],
                             tuple(wrong)) == X.PRE_COMPAT
    assert CP.compat_band(*parts["table"][("TIS", 11, 12)]) == S.BAND_ROUTINE


def test_a_zero_co_registration_row_on_a_reachable_pair_is_an_alternative_label_and_proposes_nothing():
    """(601,13): 13 is reachable for TIS and never once coexists with 11.

    This is the operator's SECOND correction. 45 of the 51 flags that survived
    increment 1's two tests are this: D.IMG images sit in 127 Tissue Imaging or
    in 145 Histopathology and never in both, because a curator picks one, and
    145 D.IMG samples are registered in Histopathology. Two names for one thing
    is not an error, so the row proposes NOTHING -- no mode, no action, and no
    proposal source, because nothing proposed it.

    THE ZERO IS MEASURED AND THE ROW SAYS OVER WHAT. `co_reg_pop` rides beside
    `co_reg_rate` for the reason `BAND_NO_SUPPORT` exists: a rate of 0.000 over
    four samples is noise and would manufacture this finding out of an empty
    population.
    """
    _, parts = _pipeline3()
    row = _found(parts["findings"], 601, 13)

    assert _key_step(parts, 601, 13) == X.PRE_COMPAT
    assert row.compat_band == S.BAND_NEVER
    assert row.classification == S.CLS_ALT_LABEL
    assert row.co_reg_rate == 0.0
    assert row.co_reg_pop >= S.MIN_CO_REG_SUPPORT
    assert row.co_reg_registered_internal_assay_id == 11

    # proposes nothing, and every column that would say otherwise is empty
    assert pd.isna(row["mode"])
    assert row.action == S.A_NONE
    assert pd.isna(row.proposed_by)
    # the lineage test RAN and found nothing, which is LIN_NONE and not null
    assert row.lineage == S.LIN_NONE
    assert row.lineage_n_supports == 0

    # THE WRONG RULE: reading a zero as a contradiction. That is what increment
    # 1 did and what `measure_absence_vs_contradiction.py` still does; the rate
    # is identical and only the LABEL changed.
    assert S.CLS_ALT_LABEL in S.CLASSES
    assert "CONTRADICTION" not in S.CLASSES
    assert CP.band_establishes(S.BAND_NEVER) == S.CLS_ALT_LABEL


def test_cls_unresolved_is_its_own_class_and_is_folded_into_no_mode():
    """(602,14) and (200,12): two BANDS, one CLASS, and neither reaches a mode.

    `BAND_SOMETIMES` and `BAND_NO_SUPPORT` are different findings -- "they
    coexist sometimes" against "the population was too small to read" -- and
    both establish that neither test settles the row. `CLS_UNRESOLVED` is
    reported at its own size rather than banded into a mode, because silently
    absorbing what the pipeline cannot classify is how a bucket ends up named
    for what someone assumed was in it, which has happened three times on this
    branch.
    """
    _, parts = _pipeline3()
    sometimes = _found(parts["findings"], 602, 14)
    unread = _found(parts["findings"], 200, 12)

    assert sometimes.compat_band == S.BAND_SOMETIMES
    assert unread.compat_band == S.BAND_NO_SUPPORT
    assert sometimes.compat_band != unread.compat_band
    for row in (sometimes, unread):
        assert row.classification == S.CLS_UNRESOLVED
        assert pd.isna(row["mode"])
        assert row.action == S.A_NONE
        assert pd.isna(row.proposed_by)

    # the unread one carries its population so the reader can see WHY it is
    # unread, rather than being told a rate of zero
    assert unread.co_reg_rate == 0.0
    assert unread.co_reg_pop < S.MIN_CO_REG_SUPPORT
    # ...and it is NOT the alternative-label finding, which is the whole reason
    # `_schema` declares the two bands apart
    assert unread.classification != S.CLS_ALT_LABEL

    census = parts["census"]
    assert census["rows_cls_unresolved"] == 2
    assert census["rows_no_mode"] == 3


def test_a_routinely_coexisting_pair_is_a_mode_2_candidate_and_says_it_is_unproven():
    """(600,12): the pair coexists, so the absence is the anomaly. Unproven.

    The spec routes this class to "Mode 2 candidate, unproven" -- 250 of the
    866 -- and unproven is the operative word: there is no neighbour and so no
    hop, which means there is no precedent rate behind it at all. The precedent
    block is NULL rather than zero, on the same rule Mode 2 applies to a hop
    with no rule: 0.000 is a measured rate and a null means nobody measured.
    """
    _, parts = _pipeline3()
    row = _found(parts["findings"], 600, 12)

    assert _key_step(parts, 600, 12) == X.PRE_COMPAT
    assert row.compat_band == S.BAND_ROUTINE
    assert row.classification == S.CLS_ABSENCE_COMPAT
    assert row["mode"] == S.MODE_2
    assert row.action == S.A_ADD_TO_ASSAY
    assert row.proposed_by == X.BY_CLAIM
    assert row.co_reg_rate >= S.CO_OCCUR_BAND
    assert row.co_reg_registered_internal_assay_id == 11

    # UNPROVEN: no hop, so no precedent, and the whole block is null
    for col in ("precedent_rate", "precedent_direction", "precedent_n_both",
                "precedent_n_child_only", "precedent_n_parent_only",
                "lineage_neighbour_uuid"):
        assert pd.isna(row[col]), col
    assert row.lineage == S.LIN_NONE
    assert "no lineage neighbour" in row.evidence_summary

    # ...and the claim that produced it rides on the row, because the claim IS
    # the proposal here
    assert row.source_field == "Type" and row.raw_value == "alpha"
    assert row.gate == S.GATE_PASS


def test_mode_3_emits_zero_rows_because_no_detector_exists():
    """Not small. UNDETECTED. The two are different findings and only one is true.

    The operator's Mode 3 is "what samples have INCORRECT assays". The detector
    built for it in increment 1 finds claims that disagree with registrations,
    and measurement showed that population is alternative labels and vocabulary
    defects with approximately zero genuine mis-registrations: of increment 1's
    866 flags, 43 are gate rejects, 326 are lineage absences, 247 routinely
    coexist, 205 are unresolved and 45 are alternative labels. Metadata
    disagreeing with a registration is simply not evidence that the registration
    is wrong.

    So Mode 3 is what SURVIVES the subtraction, and nothing does. The frame is
    empty and carries the full contract, because Task 9's report has to name the
    mode in order to say it found nothing -- a mode absent from the artifact
    reads as a mode nobody ran.
    """
    _, parts = _pipeline3()
    findings = parts["findings"]

    empty = X.mode3_findings()
    assert len(empty) == 0
    assert list(empty.columns) == S.FINDING_COLUMNS

    assert len(findings[findings["mode"] == S.MODE_3]) == 0
    assert parts["census"]["rows_mode_3"] == 0
    assert parts["census"]["keys_mode_3"] == 0

    # the mode is NAMED and never emitted, which is the ruling `_schema` records
    assert S.MODE_3 in S.MODES
    assert S.MODE_3 not in S.EMITTED_MODES
    assert set(findings["mode"].dropna()) <= set(S.EMITTED_MODES)

    # NO DETECTOR EXISTS, asserted off the source rather than off the output: a
    # zero row count is also what a detector that ran and found nothing looks
    # like, and those are the two findings this test exists to keep apart.
    src = "\n".join(_stage_c_sources().values())
    assert not re.findall(r"^def mode3_\w*detect", src, re.M)
    body = src.split("def mode3_findings")[1].split("\ndef ")[0]
    assert "no detector" in body


def test_the_classes_partition_every_claim_backed_absence_and_every_lineage_pair():
    """THE INPUT, defined: every (sample, assay) ABSENCE key from either source.

    A key is in the input when the sample is NOT registered in the assay AND
    either a metadata claim names the pair or a lineage neighbour registers it.
    A claim naming an assay the sample already holds is an absence of nothing
    and is in no key; 123,439 claims on the real extract are that shape, which
    is 89% of the 138,007, and they are counted by name rather than dropped.

    Every key gets exactly one step, the five steps sum to the input, and the
    two that emit nothing -- `PRE_GATE` and `PRE_MODE_3` -- are the difference
    between the input and the emitted rows. Every emitted row gets exactly one
    classification or an explicit null, and those sum to the rows.
    """
    _, parts = _pipeline3()
    keys, steps, findings, census = (parts["keys"], parts["steps"],
                                     parts["findings"], parts["census"])

    # THE INPUT, re-derived here from the two sources rather than taken
    from_claims = {
        (int(r.sample_id), int(r.internal_assay_id))
        for r in parts["attached"].itertuples(index=False)
        if int(r.internal_assay_id) not in parts["registered"].get(
            int(r.sample_id), set())
    }
    from_lineage = set(parts["candidates"])
    assert set(keys) == from_claims | from_lineage
    assert len(keys) == 10
    assert (620, 11) not in keys, "an absence of nothing is not an input key"

    counts = Counter(steps.values())
    assert dict(counts) == {X.PRE_GATE: 2, X.PRE_MODE_1: 1,
                            X.PRE_LINEAGE: 3, X.PRE_COMPAT: 4}
    assert sum(counts.values()) == len(keys) == census["input_keys"]
    assert set(counts) <= set(X.PRECEDENCE)

    # the emitted rows are the input minus the two steps that emit nothing
    assert len(findings) == len(keys) - counts[X.PRE_GATE] == 8
    assert census["rows"] == len(findings)
    assert (census["input_keys"] - census["keys_refused_by_the_gate"]
            - census["keys_mode_3"]) == census["rows"]

    # ...and the modes partition the rows
    assert (census["rows_mode_1"] + census["rows_mode_2"]
            + census["rows_mode_3"] + census["rows_no_mode"]) == census["rows"]
    assert (census["rows_mode_1"], census["rows_mode_2"],
            census["rows_mode_3"], census["rows_no_mode"]) == (1, 4, 0, 3)

    # ...and the CLASSES partition them too, with the unclassified counted
    by_class = Counter(findings.classification.dropna())
    assert dict(by_class) == {S.CLS_ABSENCE_LINEAGE: 3, S.CLS_ABSENCE_COMPAT: 1,
                              S.CLS_ALT_LABEL: 1, S.CLS_UNRESOLVED: 2}
    assert set(by_class) <= set(S.CLASSES)
    assert (sum(by_class.values())
            + census["rows_without_a_classification"]) == census["rows"]
    assert census["rows_without_a_classification"] == 1   # Mode 1 asserts none


def test_mode_1_takes_a_key_a_lineage_neighbour_also_offers_and_the_refusal_is_counted():
    """(710,12) is wanted by two lanes, and nothing is dropped silently.

    A sample registered in NOTHING can still hang off a neighbour that holds
    something, so Mode 1's population and Mode 2's ceiling genuinely overlap:
    2,405 of Mode 1's 6,242 samples reach a Mode 2 row on the real extract, and
    753 (sample, assay) keys are wanted by both lanes. Adding a sample to an
    assay is ONE membership write whichever lane argues for it, so one row is
    emitted -- and the lane that lost is counted by name rather than being
    quietly absent from a census that still reports the ceiling.
    """
    _, parts = _pipeline3()
    row = _found(parts["findings"], 710, 12)

    assert _key_step(parts, 710, 12) == X.PRE_MODE_1
    assert row["mode"] == S.MODE_1
    assert row.action == S.A_ADD_TO_ASSAY
    assert row.proposed_by == X.BY_CLAIM
    # Mode 1 asserts nothing about the tests it never ran, and that is unchanged
    # by the unified pass: a null here can still be FILLED by a later task
    # without contradicting a shipped value
    assert pd.isna(row.classification) and pd.isna(row.lineage)

    # both lanes offered the key
    lineage_lane = parts["lanes"][X.PRE_LINEAGE]
    assert len(lineage_lane[(lineage_lane.sample_id == 710)
                            & (lineage_lane.proposed_internal_assay_id == 12)]) == 1
    census = parts["census"]
    assert census["lineage_taken_by_mode_1"] == 1
    assert census["lineage_ceiling_offered"] == len(lineage_lane) == 6
    assert (census["keys_lineage"] + census["lineage_refused_by_the_gate"]
            + census["lineage_taken_by_mode_1"]) == census["lineage_ceiling_offered"]
    # (700,15) and (730,15) -- a DIFFERENT number from the one above, so a rule
    # that confused the two refusals could not pass this world
    assert census["lineage_refused_by_the_gate"] == 2
    assert census["lineage_refused_by_the_gate"] != census["lineage_taken_by_mode_1"]
    # the two routes to the same population agree
    assert census["keys_from_lineage"] == census["lineage_ceiling_offered"]


def test_a_claim_agreeing_with_a_registration_proposes_nothing_and_is_counted_by_name():
    """620 claims 11 and holds 11. There is no absence, so there is no key.

    Nothing is dropped silently: the excluded pairs are returned by name, not
    merely counted, following `registered_samples_absent_from_samples` and
    `gate.untyped_registration_samples`. On the real extract this is 123,439 of
    the 138,007 attached claims -- the single largest exclusion in stage C, and
    the one whose silent growth would shrink every mode at once.
    """
    _, parts = _pipeline3()

    agreeing = X.claims_agreeing_with_a_registration(parts["attached"],
                                                     parts["registered"])
    assert (620, 11) in agreeing
    assert agreeing == sorted(agreeing), "the artifact must be stable across runs"
    assert parts["census"]["claims_agreeing_with_a_registration"] == len(agreeing)

    # ...and every one of them really does hold what it claims, read off the
    # registrations rather than trusted
    for sample_id, assay_id in agreeing:
        assert assay_id in parts["registered"][sample_id]
    # ...while no input key does
    for sample_id, assay_id in parts["keys"]:
        assert assay_id not in parts["registered"].get(sample_id, set())


def test_the_unified_frame_is_the_shared_contract_totally_sorted_and_one_row_per_proposal():
    """One row per (sample, proposed assay), whichever lane produced it.

    THE KEY IS THE WRITE. Adding sample S to assay X is one membership row
    however many lanes argue for it, so a curator reading `findings.csv` must
    never meet the same proposal twice under two modes -- and the precedence is
    what guarantees they do not.

    Sorted on `(sample_id, proposed_internal_assay_id)`, a TOTAL order on this
    output, because a curator diffs this artifact between runs and the three
    lanes arrive in three different orders.
    """
    _, parts = _pipeline3()
    findings = parts["findings"]

    assert list(findings.columns) == S.FINDING_COLUMNS
    assert len(S.FINDING_COLUMNS) == 36
    keys = list(zip(findings.sample_id, findings.proposed_internal_assay_id))
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys)
    assert list(findings.index) == list(range(len(findings)))

    # ...and the sort is not a no-op: the lanes really do arrive out of order
    unsorted = pd.concat(
        [parts["lanes"][s] for s in (X.PRE_MODE_1, X.PRE_LINEAGE, X.PRE_COMPAT)],
        ignore_index=True)
    raw = list(zip(unsorted.sample_id, unsorted.proposed_internal_assay_id))
    assert raw != sorted(raw), "the lanes must arrive unsorted or this is vacuous"


def test_a_lane_that_drops_or_duplicates_a_key_the_precedence_granted_it_fails_loudly():
    """`unify_findings` asserts the partition rather than trusting the lanes.

    TWO LANES OVER-OFFER BY DESIGN and one cannot. `mode1_findings` and
    `mode2.mode2_findings` are CEILING emitters with their own published
    figures, so they hand over every row their own rule produces and the
    precedence FILTERS them -- 5 lineage rows offered here against 3 emitted.
    The compatibility lane is built from `steps` and can only offer its own.

    So a foreign key is filtered silently and correctly, and what must NOT be
    silent is the other direction: a lane that fails to produce a row for a key
    the precedence granted it, or that produces two. The first would leave a
    proposal in no artifact at all, and the second would put one membership
    write in front of a curator twice -- and both look, in a row count, exactly
    like a slightly different population.
    """
    _, parts = _pipeline3()
    steps, lanes = parts["steps"], dict(parts["lanes"])

    # the ceiling lanes over-offer, and that is filtered rather than refused
    assert len(lanes[X.PRE_LINEAGE]) == 6
    assert len(parts["findings"][parts["findings"]["mode"] == S.MODE_2]) == 4
    assert len(lanes[X.PRE_MODE_1]) == 1

    # A LANE THAT DROPS ONE OF ITS OWN KEYS
    short = dict(lanes)
    short[X.PRE_COMPAT] = lanes[X.PRE_COMPAT].iloc[1:]
    with pytest.raises(AssertionError, match="reach no row"):
        X.unify_findings(steps, short)

    # A LANE THAT EMITS ONE OF ITS OWN KEYS TWICE
    doubled = dict(lanes)
    doubled[X.PRE_COMPAT] = pd.concat(
        [lanes[X.PRE_COMPAT], lanes[X.PRE_COMPAT].iloc[:1]], ignore_index=True)
    with pytest.raises(AssertionError, match="twice"):
        X.unify_findings(steps, doubled)

    # ...and a lane keyed on a step that is not in the precedence at all, which
    # would drop a whole mode and read exactly like a mode that found nothing
    with pytest.raises(ValueError, match="PRECEDENCE"):
        X.unify_findings(steps, {"PRE_INVENTED": lanes[X.PRE_COMPAT]})


def test_the_disposition_carries_every_prior_flag_with_the_step_that_now_claims_it():
    """Increment 1's output is superseded traceably rather than deleted.

    Every flag it raised is re-emitted with `prior_verdict` beside the step and
    classification this run gives it, so a curator who reviewed the 866 can see
    what changed and why in the same row. The file is keyed by CLAIM, which is
    what a flag is, while `findings.csv` is keyed by PROPOSAL -- so a flag the
    gate refused has a disposition row and no finding row, which is precisely
    the fact the file exists to carry.
    """
    w, parts = _pipeline3()
    flags = A.audit_contradictions(
        C.sample_claims(V.parse_metadata(w["samples"]),
                        dict(zip(w["samples"].sample_id.astype(int),
                                 w["samples"].uuid)),
                        w["vocabulary"]),
        w["membership"], w["assays"], w["nodes"])
    assert len(flags) > 0, "the world must raise flags or this proves nothing"

    out = X.mode3_disposition(flags, parts["steps"], parts["findings"],
                              parts["attached"])
    assert list(out.columns) == X.DISPOSITION_COLUMNS
    assert len(out) == len(flags)
    assert set(out.prior_verdict) == {S.V_MODE3_FLAG}
    assert set(out.precedence_step) <= set(X.PRECEDENCE)
    # NOT ONE of them is a Mode 3 row, which is the whole finding
    assert not (set(out["mode"].dropna()) & {S.MODE_3})

    # a gate-refused flag has a step and no finding, and says why
    refused = out[out.precedence_step == X.PRE_GATE]
    assert len(refused) >= 1
    assert set(refused.gate) <= set(S.GATE_REJECTIONS)
    assert refused.classification.isna().all()
    assert refused["mode"].isna().all()

    # ...and a flag that reached a row carries that row's own classification,
    # read off `findings` rather than recomputed
    for r in out[out.precedence_step != X.PRE_GATE].itertuples(index=False):
        row = _found(parts["findings"], r.sample_id,
                     r.claimed_internal_assay_id)
        assert r.classification == row.classification or (
            pd.isna(r.classification) and pd.isna(row.classification))
        assert r.evidence_summary == row.evidence_summary


def test_the_proposal_source_refusal_fires_under_a_reduced_rule_set():
    """The guard has held on the real extract by luck of the data. Not here.

    `_proposal_source` refuses the (no precedent rule, gated claim) combination
    because no honest value exists for it, and that combination occurs 0 times
    on the 2026-08-17 extract -- so every test of the raise until now had to
    CONSTRUCT it by adding a claim. Task 7's backtest measured the same
    combination arising 6, 4 and 23 times at its 20%, seed-7 and 50% hold-outs,
    because a backtest mines its rules from TRAINING edges alone and a reduced
    rule set is exactly what makes a hop rule-less.

    So the guard is exercised from the other direction here: the claim stays put
    and the RULE is removed, which is what any caller mining precedent over a
    subset does.
    """
    w = _world3()
    # (720,12) is the one row in this world that is both claim-backed and
    # lineage-backed, and (10, TIS, TIS, 12) is the rule it reads
    full = M2.precedent_rules(w["precedent"])
    assert (10, "TIS", "TIS", 12) in full, "the fixture must carry the rule"
    _, parts = _pipeline3(w)
    assert _found(parts["findings"], 720, 12).proposed_by == M2.BY_BOTH

    reduced = w["precedent"][
        ~((w["precedent"].child_type == "TIS")
          & (w["precedent"].parent_type == "TIS")
          & (w["precedent"].internal_assay_id == 12))]
    assert len(reduced) == len(w["precedent"]) - 1
    w2 = dict(w, precedent=reduced)
    with pytest.raises(ValueError, match="fifth member"):
        _pipeline3(w2)


def test_the_real_extract_reproduces_the_precedence_split_and_mode_3s_emptiness():
    """Every figure the unified pass states, re-derived from the parquet.

    THE INPUT IS 180,995 KEYS AND NOT 172,338 OR 138,007. It is the union of
    every claim-backed absence with the whole lineage ceiling, and neither
    number alone is it: 123,439 of the 138,007 attached claims name an assay the
    sample already holds and raise no key at all.

    THE MODE 2 COUNT IN `findings.csv` IS SMALLER THAN THE CEILING AND THE GAP
    IS THE PRECEDENCE. The lineage lane offers 172,338 rows; the gate refuses
    4,255 of them because a rejected claim names the same pair, and Mode 1 takes
    753 more because the sample is registered in nothing and its own metadata
    proposes the assay. Both are counted here rather than inferred from a
    difference.

    MODE 3 EMITS NOTHING and the 866 flags increment 1 raised are re-disposed:
    43 gate rejects, 326 lineage absences, 247 routinely-coexisting pairs, 205
    unresolved and 45 alternative labels. Not one is a contradiction.
    """
    r = _real2()
    type_reg = G.type_registration_index(r["membership"], r["assays"], r["nodes"])
    gated = G.gate_claims(r["claims"], r["vocabulary"], type_reg,
                          G.sample_type_index(r["nodes"]))
    attached = X.attach_gate(r["claims"], gated)
    registered = A.registered_internal(r["membership"], r["assays"])
    population = X.unregistered_samples(r["samples"], r["membership"],
                                        r["assays"])
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        r["edges"], r["samples"], r["membership"])
    candidates = M2.mode2_candidates(children_of, parents_of, registered)
    projects = X.project_index(r["samples"])
    titles = M2.assay_titles(r["assays"])
    table = CP.co_registration(r["membership"], r["assays"], r["nodes"])

    keys = X.absence_keys(attached, population=population,
                          registered=registered, candidates=candidates)
    steps = X.precedence_steps(keys)
    counts = Counter(steps.values())
    assert len(keys) == 180995
    assert counts[X.PRE_GATE] == 4567
    assert counts[X.PRE_MODE_1] == 2166
    assert counts[X.PRE_LINEAGE] == 167330
    assert counts[X.PRE_COMPAT] == 6932
    assert counts[X.PRE_MODE_3] == 0
    assert sum(counts.values()) == len(keys)

    # THE PRECEDENCE IS LOAD-BEARING ON THIS DATA, not only on the fixture
    moved = []
    for i in range(len(X.PRECEDENCE) - 1):
        wrong = list(X.PRECEDENCE)
        wrong[i], wrong[i + 1] = wrong[i + 1], wrong[i]
        moved.append(sum(1 for e in keys.values()
                         if X.precedence_step(e)
                         != X.precedence_step(e, tuple(wrong))))
    assert moved == [746, 753, 903, 0]

    # ...and the THREE FIGURES THE MODULE DOCSTRING STATES are those same
    # measured values, read out of the source rather than eyeballed. Task 6
    # closed the identical gap for `main`'s printed sentence and it reopened
    # here: a hard-coded figure in a docstring with no test behind it is the
    # same class as the stale fixture docstring this branch has already paid
    # for twice. The source is normalised first, since the sentence is wrapped
    # across three literals.
    flat = re.sub(r"\s+", " ", (PACKAGE / "classify.py").read_text())
    claim = re.search(
        r"([\d,]+) input keys: GATE with MODE 1 moves ([\d,]+) keys, MODE 1 "
        r"with LINEAGE ([\d,]+), LINEAGE with COMPAT ([\d,]+)", flat)
    assert claim is not None, "the docstring sentence changed shape; re-pin it"
    stated = [int(g.replace(",", "")) for g in claim.groups()]
    assert stated == [len(keys)] + moved[:3] == [180995, 746, 753, 903]

    m1 = X.mode1_findings(attached, population, projects)
    m2 = M2.mode2_findings(
        attached, children_of=children_of, parents_of=parents_of,
        uuid_of=uuid_of, registered=registered,
        rules=M2.precedent_rules(
            P.mine_precedent(r["edges"], r["membership"], r["assays"])),
        reg_projects=M2.registration_projects(r["membership"], r["assays"]),
        types=G.sample_type_index(r["nodes"]), type_reg=type_reg,
        titles=titles, projects=projects)
    compat = X.compat_findings(attached, steps=steps, registered=registered,
                               table=table, titles=titles, projects=projects)
    lanes = {X.PRE_MODE_1: m1, X.PRE_LINEAGE: m2, X.PRE_COMPAT: compat,
             X.PRE_MODE_3: X.mode3_findings()}
    findings = X.unify_findings(steps, lanes)
    agreeing = X.claims_agreeing_with_a_registration(attached, registered)
    census = X.findings_census(keys, steps, findings, lanes, agreeing=agreeing)

    assert census["claims_agreeing_with_a_registration"] == 123439
    assert len(attached) == 138007
    assert census["rows"] == len(findings) == 176428
    assert census["rows_mode_1"] == 2166
    assert census["rows_mode_2"] == 168074 == 167330 + 744
    assert census["rows_mode_3"] == 0
    assert census["rows_no_mode"] == 6188
    assert census["rows_cls_absence_lineage"] == 167330
    assert census["rows_cls_absence_compat"] == 744
    assert census["rows_cls_alt_label"] == 5181
    assert census["rows_cls_unresolved"] == 1007
    assert census["rows_without_a_classification"] == 2166

    # THE CEILING IS A CEILING, and the precedence takes 5,008 off it
    assert census["lineage_ceiling_offered"] == 172338
    assert census["lineage_refused_by_the_gate"] == 4255
    assert census["lineage_taken_by_mode_1"] == 753
    assert census["keys_lineage"] == 172338 - 4255 - 753
    assert census["keys_from_lineage"] == census["lineage_ceiling_offered"]
    assert census["keys_from_a_claim"] == 14568 == 138007 - 123439

    # ONE ROW PER PROPOSAL over the whole extract, which is what makes the
    # artifact safe for a curator to approve row by row
    pairs = list(zip(findings.sample_id, findings.proposed_internal_assay_id))
    assert len(set(pairs)) == len(pairs)

    # --- the 866, re-disposed -------------------------------------------------
    flags = A.audit_contradictions(r["claims"], r["membership"], r["assays"],
                                   r["nodes"])
    assert len(flags) == 866
    disposition = X.mode3_disposition(flags, steps, findings, attached)
    assert len(disposition) == 866
    lane = Counter(
        s if s != X.PRE_COMPAT else c
        for s, c in zip(disposition.precedence_step, disposition.classification))
    assert lane[X.PRE_GATE] == 43
    assert lane[X.PRE_LINEAGE] == 326
    assert lane[S.CLS_ABSENCE_COMPAT] == 247
    assert lane[S.CLS_UNRESOLVED] == 205
    assert lane[S.CLS_ALT_LABEL] == 45
    assert sum(lane.values()) == 866
    assert lane[X.PRE_MODE_1] == 0, "a flagged sample is registered by definition"
    assert not (set(disposition["mode"].dropna()) & {S.MODE_3})

    # THE 24, which increment 1 filed inside its 351 ABSENCE_LINEAGE and which
    # the spec says must be pulled out BY THE VOCABULARY GATE. All 24 are
    # lineage candidates -- a D.FLOW or D.SPC data parent registers the
    # measurement assay -- so the gate is the only thing that can stop them.
    twenty_four = flags[
        ((flags.sample_type == "A.FLOW") & (flags.claimed_internal_assay_id == 30))
        | ((flags.sample_type == "A.SPC")
           & (flags.claimed_internal_assay_id == 130))]
    assert len(twenty_four) == 24
    k24 = set(zip(twenty_four.sample_id.astype(int),
                  twenty_four.claimed_internal_assay_id.astype(int)))
    assert k24 <= set(candidates), "all 24 must be lineage candidates"
    assert {steps[k] for k in k24} == {X.PRE_GATE}
    emitted = set(zip(findings.sample_id, findings.proposed_internal_assay_id))
    assert not (k24 & emitted), "not one of the 24 reaches a row"


def test_a_lane_omitted_from_the_unified_pass_fails_rather_than_dropping_a_whole_mode():
    """The OMISSION case, which the typo guard could not see and review found live.

    `unify_findings` derived its own expectation as
    `{k for k, step in steps.items() if step in lanes}`, so a step MISSING from
    `lanes` was excluded from the very check that should have failed on it. Run
    on this world with `PRE_COMPAT` left out, that version raised nothing: 8 rows
    silently became 4, and `findings_census` reported `keys_compat: 4` beside
    `rows: 4` with the identity `input - non-emitting == rows` false and nothing
    comparing them.

    The `unknown` guard catches only the TYPO case, which produces an EXTRA key.
    Task 9 re-assembles `lanes`, so this is the next consumer's live footgun
    rather than a hypothetical, and `NON_EMITTING_STEPS` is what makes the
    omission checkable: every step is either emitting -- and must hand over a
    frame -- or declared.

    THE WRONG RULE IS RUN BY HAND and asserted to give a different answer: the
    lanes-derived expectation is computed here and shown to be SATISFIED by the
    four rows the truncated call would have published.
    """
    _, parts = _pipeline3()
    steps, lanes = parts["steps"], dict(parts["lanes"])
    assert X.NON_EMITTING_STEPS == (X.PRE_GATE,)
    assert set(X.NON_EMITTING_STEPS) < set(X.PRECEDENCE)
    # Mode 3 is NOT declared non-emitting: it has a lane and that lane is empty,
    # which is a different statement from "this step emits nothing by design"
    assert X.PRE_MODE_3 not in X.NON_EMITTING_STEPS

    del lanes[X.PRE_COMPAT]
    with pytest.raises(ValueError, match="NON_EMITTING_STEPS"):
        X.unify_findings(steps, lanes)

    # THE WRONG RULE, run by hand: derive the expectation FROM `lanes`. The four
    # rows the truncated call would have emitted satisfy it exactly, which is
    # why the old guard passed while half the artifact went missing.
    survivors = pd.concat(
        [lanes[s] for s in X.PRECEDENCE if s in lanes], ignore_index=True)
    kept = {(int(s), int(a)) for s, a in
            zip(survivors.sample_id, survivors.proposed_internal_assay_id)
            if steps.get((int(s), int(a))) is not None}
    kept = {k for k in kept if steps[k] in lanes}
    lanes_derived = {k for k, step in steps.items() if step in lanes}
    assert kept == lanes_derived, "the wrong rule must be satisfied or this proves nothing"
    assert len(kept) == 4 and len(parts["findings"]) == 8

    # ...and the contract-derived expectation, which is what the emitter now
    # uses, is NOT satisfied by those four
    contract = {k for k, step in steps.items()
                if step not in X.NON_EMITTING_STEPS}
    assert contract != lanes_derived
    assert len(contract) == 8

    # the identity the census now asserts at runtime is the same fact
    census = parts["census"]
    assert (census["input_keys"] - census["keys_refused_by_the_gate"]
            == census["rows"] == 8)

    # THE OTHER DIRECTION, which is what separates the two derivations. A lane
    # offered for a NON-EMITTING step is refused: its rows carry that step, so
    # the filter would KEEP them, while the contract says the step emits
    # nothing. Under the lanes-derived expectation those rows are silently
    # admitted -- `step in lanes` is true of them -- and 2 gate-refused
    # proposals reach `findings.csv`. This is the case the two rules disagree
    # about, and it is the reason the derivation had to move off `lanes`.
    smuggled = dict(parts["lanes"])
    smuggled[X.PRE_GATE] = parts["lanes"][X.PRE_LINEAGE]
    lanes_derived_wrong = {k for k, step in steps.items() if step in smuggled}
    contract_here = {k for k, step in steps.items()
                     if step not in X.NON_EMITTING_STEPS}
    assert lanes_derived_wrong != contract_here, (
        "the two derivations must disagree here or this proves nothing")
    assert len(lanes_derived_wrong) == 10 and len(contract_here) == 8
    with pytest.raises(AssertionError, match="belong to no"):
        X.unify_findings(steps, smuggled)


def test_the_census_refuses_a_row_count_that_contradicts_its_own_key_count():
    """`input_keys` minus the non-emitting steps IS `rows`, asserted at runtime.

    The identity held silently while `unify_findings` could drop a whole lane:
    the census reported `keys_compat: 4` beside `rows: 4` and nothing compared
    them. `unify_findings` now refuses that assembly before the census is
    reached, so the two guards are belt and braces -- but `findings_census` is a
    public function and a caller can hand it a frame that never went through the
    emitter, which is exactly what a report assembled from a filtered artifact
    would be.

    The subtrahend is derived from `NON_EMITTING_STEPS` rather than written, so
    it cannot drift from the tuple that defines it.
    """
    _, parts = _pipeline3()
    keys, steps, lanes = parts["keys"], parts["steps"], parts["lanes"]
    agreeing = X.claims_agreeing_with_a_registration(parts["attached"],
                                                     parts["registered"])

    # the honest call is green, so the guard is not firing unconditionally
    census = X.findings_census(keys, steps, parts["findings"], lanes,
                               agreeing=agreeing)
    assert census["rows"] == 8

    # a frame one row short of what the precedence granted
    with pytest.raises(AssertionError, match="emitted row"):
        X.findings_census(keys, steps, parts["findings"].iloc[1:], lanes,
                          agreeing=agreeing)
    # ...and one row too many
    with pytest.raises(AssertionError, match="emitted row"):
        X.findings_census(
            keys, steps,
            pd.concat([parts["findings"], parts["findings"].iloc[:1]],
                      ignore_index=True),
            lanes, agreeing=agreeing)


def test_a_row_where_nothing_reached_a_population_carries_a_null_rate_not_a_measured_zero():
    """`best_co_registration` returns 0.0 for "nothing measured", and 0.0 is a rate.

    It returns `(0.0, 0, None, None, 0)` when no assay the sample holds reaches
    a key at all, and the zero is safe THERE only because `compat_band` tests
    support before rate. Written into `findings.csv` unguarded it becomes an
    operator-facing `co_reg_rate` of 0.000 -- "these two never coexist" -- on
    the one row whose own `evidence_summary` says "that is absent evidence and
    not a rate of zero". Task 8 is the first code to write these columns into an
    artifact, which is what newly exposes it.

    0 of the 6,932 compatibility rows on the real extract reach this, because
    the gate guarantees the proposed assay is reachable for the type and the
    sample's own registration guarantees the other cell. So the state is
    constructed here through the `table` argument, which is what the function
    takes and what a caller measuring over a subset would hand it.

    `co_reg_pop` stays 0 and is NOT null, deliberately: the population was read
    and it is empty, which is exactly what makes `compat_band` read
    `BAND_NO_SUPPORT` rather than `BAND_NEVER`.
    """
    _, parts = _pipeline3()
    row = _found(parts["findings"], 600, 12)
    assert pd.notna(row.co_reg_rate) and row.co_reg_rate > 0.0, (
        "the unmutated world must measure a rate here or this proves nothing")

    empty = X.compat_findings(
        parts["attached"], steps=parts["steps"], registered=parts["registered"],
        table={}, titles=parts["titles"], projects=parts["projects"])
    assert len(empty) == len(parts["lanes"][X.PRE_COMPAT]) == 4

    got = empty[(empty.sample_id == 600)
                & (empty.proposed_internal_assay_id == 12)].iloc[0]
    assert pd.isna(got.co_reg_rate), "0.0 would state a rate nobody measured"
    assert got.co_reg_pop == 0            # read, and empty
    assert pd.isna(got.co_reg_registered_internal_assay_id)
    assert got.compat_band == S.BAND_NO_SUPPORT
    assert got.classification == S.CLS_UNRESOLVED
    assert pd.isna(got["mode"]) and got.action == S.A_NONE
    assert "absent evidence and not a rate of zero" in got.evidence_summary
    # every row on this path says the same thing, not just the one read above
    assert empty.co_reg_rate.isna().all()
    assert set(empty.compat_band) == {S.BAND_NO_SUPPORT}


def test_the_disposition_breakdown_counts_a_null_class_rather_than_dropping_it():
    """`value_counts()` drops nulls by default, and this one must not.

    The breakdown is the figure a curator uses to check that increment 1's whole
    866 was re-disposed. A null `classification` on a `PRE_COMPAT` row would
    shrink it below 866 with no error, and smaller is exactly what "some of them
    turned out fine" looks like to a reader.

    Nothing can produce that null through the real path -- `compat_findings`
    classifies every row it emits -- so it is INJECTED here, which is the only
    way to know the guard fires rather than merely exists. The wrong rule,
    `value_counts()` with its default, is run by hand on the same frame and
    asserted to give a SMALLER total.
    """
    w, parts = _pipeline3()
    flags = A.audit_contradictions(
        C.sample_claims(V.parse_metadata(w["samples"]),
                        dict(zip(w["samples"].sample_id.astype(int),
                                 w["samples"].uuid)),
                        w["vocabulary"]),
        w["membership"], w["assays"], w["nodes"])
    out = X.mode3_disposition(flags, parts["steps"], parts["findings"],
                              parts["attached"])

    clean = X.disposition_breakdown(out)
    assert int(clean.sum()) == len(out) == len(flags)
    assert not clean.index.isna().any(), "the real path produces no null"

    # INJECT one, on a PRE_COMPAT row, which is the only place it could arise
    holed = out.copy()
    target = holed.index[holed.precedence_step == X.PRE_COMPAT][0]
    holed.loc[target, "classification"] = None

    # THE WRONG RULE, run by hand: the pandas default
    wrong = holed.precedence_step.where(
        holed.precedence_step != X.PRE_COMPAT,
        holed.classification).value_counts()
    assert int(wrong.sum()) == len(holed) - 1, (
        "the default must lose the row or this proves nothing")

    got = X.disposition_breakdown(holed)
    assert int(got.sum()) == len(holed)
    assert got.index.isna().any(), "the null is a bucket, not a deletion"
    assert int(wrong.sum()) != int(got.sum())

    # ...and the function's own sum check is what would REJECT the wrong rule's
    # answer. The raise is unreachable while `dropna=False` stands -- a
    # `value_counts(dropna=False)` over a series of length n always sums to n --
    # so it is a tripwire for the keyword rather than a branch this frame can
    # enter, and this is the assertion that says what it would have caught.
    assert int(wrong.sum()) != len(holed)
