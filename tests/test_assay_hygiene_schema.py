import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S


def _registration(fx):
    """sample_id -> set of assay_ids it is registered in, derived from membership.

    The structural assertions below are computed through this helper rather than
    written against literal ids, so they describe the fixture's shape instead of
    restating its rows.
    """
    reg = {}
    for sid, aid in zip(fx["membership"]["sample_id"], fx["membership"]["assay_id"]):
        reg.setdefault(sid, set()).add(aid)
    return reg


def _edge_registration(fx):
    """One (child_assays, parent_assays) pair per edge, in edge order."""
    reg = _registration(fx)
    return [(reg.get(c, set()), reg.get(p, set()))
            for c, p in zip(fx["edges"]["child_id"], fx["edges"]["parent_id"])]


def test_verdict_constants_are_distinct():
    verdicts = [S.V_CLEAN, S.V_MODE1_CHILD, S.V_MODE1_PARENT,
                S.V_MODE1_BOTH_DARK, S.V_MODE2_PROPAGATE,
                S.V_MODE2_AMBIGUOUS, S.V_MODE3_FLAG]
    assert len(set(verdicts)) == len(verdicts)


def test_rule_key_is_internal_assay_id():
    # 458 assay records collapse to 137 curated internal assays via
    # dmac.assays_internal_assays. assays.id is too fine (the same logical
    # assay is instantiated per study); assays.title is a different namespace
    # from DERIVED_FROM.internal_assay_title, so findings and edges would not
    # reconcile.
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type", "internal_assay_id"]
    assert "assay_title" not in S.RULE_KEY


def test_precedent_carries_internal_assay_title_for_display():
    assert "internal_assay_title" in S.PRECEDENT_COLUMNS


def test_precedent_columns_carry_both_directions():
    for col in ("n_both", "n_child_only", "n_parent_only",
                "propagation_rate", "reverse_rate"):
        assert col in S.PRECEDENT_COLUMNS


def test_fixture_shapes_match_declared_columns():
    fx = S.make_fixture()
    assert list(fx["edges"].columns) == S.EDGE_COLUMNS
    assert list(fx["membership"].columns) == S.MEMBERSHIP_COLUMNS
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS


def test_finding_columns_are_one_row_per_sample_and_proposed_assay():
    """The stage C contract, pinned as a literal and in order.

    REPLACES `test_finding_columns_end_with_candidates`, which pinned the
    per-EDGE shape: `candidates` last, because stage D's tiebreak read it off
    the end. That shape is gone -- the row is now keyed
    `(sample_id, proposed_internal_assay_id)` and membership rides on the row
    itself as `registered_internal_assay_ids`, so there is nothing for a
    tiebreak to recover later and nothing at the end to protect. The successor
    below is strictly stronger than the assertion it replaces: the old test
    pinned two facts about one column, this one pins all 34 columns, their
    order, and their uniqueness.

    34 and not 31 since 2026-08-17. `co_reg_registered_internal_assay_id` names
    which pair the winning rate measured, and
    `co_reg_alt_label_internal_assay_id` / `co_reg_alt_label_pop` carry the
    counter-evidence a best-of rate would otherwise hide. See
    `test_a_co_registration_rate_names_the_registration_it_was_measured_against`
    and `test_a_best_of_rate_carries_the_well_supported_zero_it_beat`.

    36 and not 34 since Mode 2 was written, the same day and by the same rule:
    the moment before a column's first consumer exists is the one moment it
    costs nothing, and both were required by a Mode 2 row rather than invented
    for it. `type_registrations` is the reachability cell -- ZERO means the
    proposal would create a (sample type, assay) pair existing nowhere, which
    55.4% of ADD_PARENT and 62.4% of ADD_CHILD rows do -- and it is filled by
    Mode 1 as well, because the gate measured it there too. `lineage_n_supports`
    is how many neighbours back a proposal that is emitted ONCE because it is
    one write; 31,180 of the 172,338 rows carry more than one, up to 1,526.
    See `test_a_row_creating_a_type_assay_pair_existing_nowhere_is_flagged_on_the_row`
    and `test_a_pair_reachable_from_two_neighbours_is_one_row_carrying_two_supports`.

    `project_ids` is PLURAL and was `project_id` until 2026-08-17, renamed when
    the first emitter was written and measured the value: 1,052 of Mode 1's
    6,242 population samples hold more than one project id and 34 hold a
    duplicate. `test_no_finding_column_collides_with_the_rule_key` carries the
    decisive half of that argument.

    Pinned against a literal for the reason `VOCAB_COLUMNS` and `CLAIM_COLUMNS`
    are: a test asserting only "the frame matches the constant" stays green
    through any reordering of the constant itself.
    """
    assert S.FINDING_COLUMNS == [
        "sample_id", "uuid", "sample_type", "project_ids",
        "registered_internal_assay_ids", "registered_internal_assay_titles",
        "proposed_internal_assay_id", "proposed_internal_assay_title",
        "mode", "classification", "gate",
        "claim_tier", "contested", "source_field", "raw_value",
        "vocab_support", "vocab_purity", "vocab_provenance", "type_registrations",
        "lineage", "lineage_neighbour_uuid", "lineage_n_supports",
        "co_reg_rate", "co_reg_pop", "co_reg_registered_internal_assay_id",
        "co_reg_alt_label_internal_assay_id", "co_reg_alt_label_pop",
        "compat_band",
        "precedent_rate", "precedent_direction",
        "precedent_n_both", "precedent_n_child_only", "precedent_n_parent_only",
        "proposed_by", "evidence_summary", "action",
    ]
    assert len(set(S.FINDING_COLUMNS)) == len(S.FINDING_COLUMNS)


def test_no_finding_column_collides_with_the_rule_key():
    """One name, one meaning, across the two frames a Mode 2 classifier holds open.

    `RULE_KEY` is `(project_id, child_type, parent_type, internal_assay_id)` and
    every component of it is SINGULAR by construction: a precedent rule is scoped
    to exactly one project and exactly one hop. `FINDING_COLUMNS` describes a
    sample, whose project set is not singular at all -- 1,052 of Mode 1's 6,242
    population samples hold more than one project id, 34 hold the same id twice,
    and 193 hold none.

    Mode 2 keys on `RULE_KEY` and emits `FINDING_COLUMNS`, so the two constants
    are in scope in one function. Until 2026-08-17 both spelled `project_id`,
    which put "exactly one project" and "a `;`-joined set of projects" under one
    name one frame apart -- this module's signature defect, the one it has
    documented for `edge_internal_assay_id`, for `provenance` / `source_provenance`
    and for the grain change above, and the one that has cost this branch four
    tasks. The finding column is now `project_ids`.

    THE ASSERTION IS DISJOINTNESS AND NOT AN INEQUALITY ON ONE NAME. A test
    spelling `"project_id" not in FINDING_COLUMNS` would pin the instance and
    miss the class; the next collision would be `internal_assay_id`, which
    `FINDING_COLUMNS` deliberately carries only under the prefixes
    `proposed_`, `co_reg_registered_` and `co_reg_alt_label_` precisely because
    the bare name is the rule key's.

    A future column MAY share a name with a rule-key component -- if it genuinely
    carries the same thing, this test is the place to say so and to record why.
    Silence here means no such column has ever been justified.
    """
    shared = sorted(set(S.FINDING_COLUMNS) & set(S.RULE_KEY))
    assert not shared, (
        f"{shared} appear in both FINDING_COLUMNS and RULE_KEY. A rule-key "
        "component is singular by construction and a finding column describes "
        "a sample; if the two genuinely mean the same thing, say so here and "
        "name the column in an exemption. Otherwise prefix or pluralise it.")

    # ...and the same for the whole precedent frame, which the finding row
    # borrows from under `precedent_*` prefixes for exactly this reason.
    shared = sorted(set(S.FINDING_COLUMNS) & set(S.PRECEDENT_COLUMNS))
    assert not shared, (
        f"{shared} appear in both FINDING_COLUMNS and PRECEDENT_COLUMNS. Every "
        "borrowed column carries the prefix of the frame it came from, so a "
        "reader can tell `precedent_rate` from a co-registration rate.")

    # The rule key's own components are unchanged, so this test cannot be made
    # to pass by renaming the OTHER side of the collision: a precedent rule is
    # scoped to one project and that name is correct where it lives.
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type",
                          "internal_assay_id"]
    assert "project_id" in S.ASSAY_COLUMNS      # one assay, one project
    assert "project_ids" in S.SAMPLE_COLUMNS    # one sample, a GROUP_CONCAT
    assert "project_ids" in S.FINDING_COLUMNS   # ...and the row reads the sample


def test_a_co_registration_rate_names_the_registration_it_was_measured_against():
    """The co-registration block is rate, support, and WHICH pair was measured.

    A co-registration rate is a statement about an ORDERED PAIR: across samples
    of this type registered in R, what share also register X. The row already
    names X (`proposed_internal_assay_id`) and lists every R the sample holds
    (`registered_internal_assay_ids`, up to 7 on the real extract), but
    `compatibility.best_co_registration` collapses those to the ONE R yielding
    the best rate -- so without this column the row reads
    `registered 56;74;112;133, rate 0.805` and the operator cannot tell which
    registration produced 0.805, cannot check it, and cannot see that the others
    were weaker. That is an unexplainable row in the artifact whose whole
    premise is that a human approves it.

    ADDED BEFORE ITS FIRST CONSUMER, the same call
    `registered_internal_assay_titles` was added under. Tasks 5, 6 and 8 would
    otherwise each decide independently whether to keep the winner the function
    already returns, and the one that discards it ships the unexplainable row.

    THE ORDER IS THE ARGUMENT. rate, then the support that checks it, then the
    registration the support counted -- each column is the check on the one
    before it, which is the same reason `co_reg_pop` rides behind `co_reg_rate`
    and `n_samples` rides behind `support` in `VOCAB_COLUMNS`. `compat_band` is
    the LABEL and comes after all three facts it labels.

    AN ID AND NEVER A TITLE. It deliberately has no `_title` partner and the
    "every title column has its id" sweep in
    `test_both_sides_of_a_finding_row_are_decoded_and_the_title_is_display_only`
    is unaffected, because that sweep runs from titles to ids and not back. The
    assay named here is always a member of `registered_internal_assay_ids`,
    whose `_titles` column already decodes the whole set in position, so nothing
    is undecodable for the operator.
    """
    rate = S.FINDING_COLUMNS.index("co_reg_rate")
    pop = S.FINDING_COLUMNS.index("co_reg_pop")
    against = S.FINDING_COLUMNS.index("co_reg_registered_internal_assay_id")
    band = S.FINDING_COLUMNS.index("compat_band")

    assert pop == rate + 1
    assert against == pop + 1, (
        "the registration the rate was measured against belongs with the rate "
        "and its support, not adrift from them")
    assert band > against, (
        "the band LABELS the facts before it and must never sit among them")

    # an id, and it takes no title partner
    assert S.FINDING_COLUMNS[against].endswith("_id")
    assert "co_reg_registered_internal_assay_title" not in S.FINDING_COLUMNS

    # ...and the assay it names comes from the set the row already carries, so
    # it is decodable without a second artifact. This is the assertion that
    # would fail if someone "helpfully" made this column a title.
    assert "registered_internal_assay_ids" in S.FINDING_COLUMNS
    assert "registered_internal_assay_titles" in S.FINDING_COLUMNS
    assert not S.FINDING_COLUMNS[against].endswith("_title")

    # the whole co-registration block, in order, so a reordering fails here too
    assert S.FINDING_COLUMNS[rate:band + 1] == [
        "co_reg_rate", "co_reg_pop", "co_reg_registered_internal_assay_id",
        "co_reg_alt_label_internal_assay_id", "co_reg_alt_label_pop",
        "compat_band",
    ]


def test_a_best_of_rate_carries_the_well_supported_zero_it_beat():
    """The winning rate is a BEST-OF, and a best-of hides its losers.

    A sample holding R1 and R2, proposed X, with `(T,R1,X)` = 0.000 over 2,000
    and `(T,R2,X)` = 0.9 over 100, reports 0.9 -> BAND_ROUTINE ->
    CLS_ABSENCE_COMPAT, "the absence is the anomaly, propose X" -- while the
    well-supported zero, saying X is an ALTERNATIVE LABEL for R1 which the
    sample ALREADY CARRIES, reaches nobody. A well-supported zero is not
    silence; it is counter-evidence, and it is strongest in exactly the case
    where the winner is loudest.

    NOT RARE, which is why these are columns rather than a footnote. Measured
    2026-08-17 over the 7,831 (gated claim, type) rows on a registered sample
    whose proposed assay it does not hold: 5,839 (74.6%) have a well-supported
    zero available and 428 (5.5%) are outright conflicts. 408 of the 428 are one
    pattern, and it is the spec's own flagship vocabulary defect -- DNA samples
    proposed 24 DNA Extraction on the `Type: Illumina Library` mapping.

    THE POPULATION RIDES WITH THE ID, because the whole meaning of a zero is its
    support -- which is what `BAND_NO_SUPPORT` exists to say. An alt-label id
    with no population beside it repeats the error that band was declared to
    prevent.
    """
    aid = S.FINDING_COLUMNS.index("co_reg_alt_label_internal_assay_id")
    apop = S.FINDING_COLUMNS.index("co_reg_alt_label_pop")
    against = S.FINDING_COLUMNS.index("co_reg_registered_internal_assay_id")
    band = S.FINDING_COLUMNS.index("compat_band")

    assert aid == against + 1, (
        "the counter-evidence belongs in the co-registration block, beside the "
        "rate it opposes, not adrift at the end of the row")
    assert apop == aid + 1, (
        "a zero with no population is exactly what BAND_NO_SUPPORT exists to "
        "refuse; the id may never travel without its support")
    assert band == apop + 1, (
        "the band is the LABEL and comes after every fact it labels")

    # an id and never a title, like every other identity in this module
    assert S.FINDING_COLUMNS[aid].endswith("_id")
    assert "co_reg_alt_label_internal_assay_title" not in S.FINDING_COLUMNS

    # the winner and the counter-evidence are DIFFERENT columns. One column
    # doing both jobs would report whichever the code looked at last.
    assert len({against, aid, apop}) == 3


def test_no_per_edge_finding_column_survives_the_grain_change():
    """The grain moved from per-EDGE to per-SAMPLE under an unchanged name.

    That is this branch's signature defect -- two meanings one frame apart --
    and the mitigation is that the two column sets are disjoint except for
    `project_id`, which means the same thing in both. Every name the per-edge
    shape carried is now ABSENT, so code written against the old grain dies with
    a KeyError instead of reading a populated, wrong column.

    Verified at the time of the change: `FINDING_COLUMNS` had exactly one
    reference outside `_schema.py` in the whole tree, the schema test replaced
    above. There was no per-edge consumer to migrate.
    """
    for col in ("child_id", "parent_id", "child_uuid", "parent_uuid",
                "child_type", "parent_type", "verdict", "candidates",
                "matched_internal_assay_id", "matched_internal_assay_title",
                "matched_rate", "target_assay_id"):
        assert col not in S.FINDING_COLUMNS, f"per-edge column {col} survived"
    # the new key, which is what makes the row per (sample, proposed assay)
    assert "sample_id" in S.FINDING_COLUMNS
    assert "proposed_internal_assay_id" in S.FINDING_COLUMNS


def test_nothing_in_a_finding_row_is_named_as_a_decision():
    """"Nothing decides. Everything proposes." is binding and it is a NAME rule.

    The assay column is `proposed_*` and not `claimed_*` or `target_*`, and the
    evidence column is `proposed_by` and not `decided_by`, because the artifact
    an operator reads is where a wrong name does its damage: a column headed
    `decided_by` tells a reader the pipeline already ruled, in a file whose
    whole premise is that it has not.

    `RULE_COLUMNS` is asserted here too. It is increment 3's constant and has no
    consumer anywhere in the tree, but it sat one screen away carrying
    `decided_by`, which is the same two-names-for-one-concept hazard the rest of
    this module documents.
    """
    for col in S.FINDING_COLUMNS + S.RULE_COLUMNS:
        assert not col.startswith("decided"), f"{col} names a decision"
        assert not col.startswith("claimed_"), f"{col} predates the proposal rule"
        assert not col.startswith("target_"), f"{col} predates the proposal rule"
    assert "proposed_by" in S.FINDING_COLUMNS
    assert "proposed_by" in S.RULE_COLUMNS
    assert "proposed_internal_assay_id" in S.FINDING_COLUMNS
    assert "proposed_internal_assay_title" in S.FINDING_COLUMNS


def test_both_sides_of_a_finding_row_are_decoded_and_the_title_is_display_only():
    """Registered ids and titles ride together, and no key is ever a title.

    Without the titles a row reads `registered 115, proposes 24 DNA Extraction`
    -- a bare id on the registered side against a decoded one on the proposed
    side -- so the operator cannot judge the proposal the row makes without a
    lookup they have no artifact for. `AUDIT_COLUMNS` settled this exact
    asymmetry one section down in `_schema.py` and the same argument applies
    here unchanged; the column carries the SAME name in both frames because it
    means the same thing, which is the opposite of the hazard this module
    usually guards.

    The two columns are PLURAL and the proposed pair is SINGULAR, and that is
    the grain: one row proposes exactly one assay and lists every assay the
    sample already holds.

    A title is display and never identity. `assay_index` raises on a
    junction-less assay whose fallback id collides with a genuine internal id,
    which makes ids safe to key on; nothing makes titles safe -- 458 seek assay
    records collapse to 291 normalised titles, so titles are not unique even
    within one namespace. The last assertion is the general form of
    `test_rule_key_is_internal_assay_id`: a title may only appear beside the id
    it decodes, never alone and never in a key.
    """
    ids = S.FINDING_COLUMNS.index("registered_internal_assay_ids")
    titles = S.FINDING_COLUMNS.index("registered_internal_assay_titles")
    assert titles == ids + 1, (
        "the titles must ride immediately behind the ids they decode, so a "
        "reader scanning the header meets the two halves of one fact together")

    # plural on the registered side, singular on the proposed side
    assert S.FINDING_COLUMNS[ids].endswith("_ids")
    assert S.FINDING_COLUMNS[titles].endswith("_titles")
    assert "proposed_internal_assay_id" in S.FINDING_COLUMNS
    assert "proposed_internal_assay_titles" not in S.FINDING_COLUMNS

    # every title column has the id column it decodes, on both sides
    for col in S.FINDING_COLUMNS:
        if col.endswith("_title"):
            assert col[: -len("_title")] + "_id" in S.FINDING_COLUMNS, col
        if col.endswith("_titles"):
            assert col[: -len("_titles")] + "_ids" in S.FINDING_COLUMNS, col

    # ...and no key anywhere in this module is a title
    assert not [c for c in S.RULE_KEY if "title" in c]


def test_the_registered_pair_lines_up_positionally_for_a_multi_assay_sample():
    """Index i of the ids names index i of the titles, on a PLURAL row.

    A sample legitimately holds more than one assay -- the domain rule -- so the
    single-assay case cannot exercise the pairing at all: with one element the
    two strings agree under any decode, including a wrong one. This builds the
    two `;`-joined strings the way a producer must, off a sample that holds two,
    and asserts they line up.

    The decode itself is asserted total and single-valued over the fixture,
    which is the property `AUDIT_COLUMNS` measured on the real extract: 0 of the
    458 assay records carry an internal id with no title, and 0 internal ids
    resolve to more than one distinct title. Titles come from the SAME funnel
    that produced the ids, so no id can decode to a title its own registration
    does not carry and no second source of truth appears.
    """
    fx = S.make_fixture()
    reg = _registered_internal(fx)

    decode = {}
    for iaid, title in zip(fx["assays"]["internal_assay_id"],
                           fx["assays"]["internal_assay_title"]):
        decode.setdefault(iaid, set()).add(title)
    assert all(len(t) == 1 for t in decode.values()), "an id decodes two ways"
    decode = {k: v.pop() for k, v in decode.items()}
    assert set().union(*reg.values()) <= set(decode), "an id does not decode"

    plural = sorted(s for s, a in reg.items() if len(a) > 1)
    assert plural, (
        "no sample holds two registered assays, so the plural pairing is "
        "untested -- with one element any decode agrees, including a wrong one")

    for sid in plural:
        ordered = sorted(reg[sid])
        ids = ";".join(str(a) for a in ordered)
        titles = ";".join(decode[a] for a in ordered)
        assert len(ids.split(";")) == len(titles.split(";")) > 1
        for i, a in enumerate(ordered):
            assert titles.split(";")[i] == decode[int(ids.split(";")[i])]
            assert ids.split(";")[i] == str(a)


def test_fixture_encodes_the_four_canonical_situations():
    fx = S.make_fixture()
    # 1 propagating hop, 1 non-propagating hop, 1 dark child, 1 dark pair,
    # plus the TIS -> PAV hop carrying the domain rule (see the fixture
    # docstring): a PAV legitimately registered in the assay that produced it
    # AND the one that consumed it.
    assert len(fx["edges"]) == 7
    assert set(fx["assays"]["title"]) == {"Comet Chip", "Tissue Collection",
                                          "Patient Visit"}

    # The four situations, derived from the frames rather than asserted by id.
    pairs = _edge_registration(fx)
    co_registered = [1 for c, p in pairs if c & p]
    disjoint_but_registered = [1 for c, p in pairs if c and p and not (c & p)]
    dark_child = [1 for c, _ in pairs if not c]
    both_dark = [1 for c, p in pairs if not c and not p]

    assert len(co_registered) == 3           # 2 precedent-establishing + TIS/PAV
    assert len(disjoint_but_registered) == 2  # mode-2 candidate + the CLEAN hop
    assert len(dark_child) == 2               # mode-1 child + the both-dark pair
    assert len(both_dark) == 1

    # Type columns are part of the frozen contract: the rule key is
    # (project, child_type, parent_type, internal_assay_id), so a changed type
    # silently re-buckets precedent. Count the hops rather than collecting the distinct
    # set -- a set still matches after a type is flipped to one that already
    # appears on another edge, which is exactly the silent edit to catch.
    hops = Counter(zip(fx["edges"]["child_type"], fx["edges"]["parent_type"]))
    assert dict(hops) == {("D.IMG", "TIS"): 3, ("DNA", "TIS"): 2,
                          ("TIS", "MUS"): 1, ("TIS", "PAV"): 1}


def test_comet_chip_hop_carries_the_frozen_propagation_counts():
    # Later stages hand-trace n_both=2 / n_child_only=1 -> propagation_rate 2/3
    # off these exact rows. Pin the counts here so an edit to a membership row
    # fails at its source instead of as mysterious arithmetic three tasks later.
    fx = S.make_fixture()
    reg = _registration(fx)
    assays = fx["assays"]
    comet = assays.loc[assays["title"] == "Comet Chip", "assay_id"].iloc[0]
    edges = fx["edges"]
    hop = edges[(edges["child_type"] == "D.IMG") & (edges["parent_type"] == "TIS")]

    n_both = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                 if comet in reg.get(c, set()) and comet in reg.get(p, set()))
    n_child_only = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                       if comet in reg.get(c, set()) and comet not in reg.get(p, set()))

    assert (n_both, n_child_only) == (2, 1)


def test_fixture_cannot_reach_ambiguity_or_a_dark_parent():
    """Pins the branches make_fixture's docstring says it does NOT reach.

    Executable so the frozen data and that docstring cannot drift apart. If one
    of these ever starts failing, the fixture gained a branch and the docstring
    is now lying -- update both together.
    """
    fx = S.make_fixture()
    reg = _registration(fx)
    edges = fx["edges"]

    # No child sits in 2+ assays, so `candidates` is single-element on every
    # row and no stage-D tiebreak can fire against this fixture.
    assert not [c for c in edges["child_id"] if len(reg.get(c, set())) > 1]

    # No edge pairs a registered child with a wholly dark parent (MODE_1_PARENT).
    assert not [(c, p) for c, p in zip(edges["child_id"], edges["parent_id"])
                if reg.get(c) and not reg.get(p)]


def test_prod_uid_regex_rejects_the_two_letter_antibody_type():
    # This is the production defect stage 0 works around. If this test ever
    # goes green-by-passing, production has been fixed and the override can go.
    assert S.UID_RE_PROD.match("AB-250723FOR-3") is None
    assert S.UID_RE_FIXED.match("AB-250723FOR-3") is not None


def test_both_regexes_agree_on_three_letter_types():
    for uid in ("TIS-260107SES-1", "D.ADNKA-250917FOR-98", "MUS-220122SAS-125"):
        assert S.UID_RE_PROD.match(uid) is not None
        assert S.UID_RE_FIXED.match(uid) is not None


def test_edge_row_columns_mirror_the_server_model():
    # nextseek_api/batch_upload/models.py:457 DerivedFromRelRow, extra="forbid".
    # A column stage 0 invents here is a field bulk_merge_relationships rejects.
    assert S.EDGE_ROW_COLUMNS == [
        "child_id", "child_uuid", "parent_id", "parent_uuid",
        "protocol_id", "protocol_title", "assay_id",
        "internal_assay_id", "internal_assay_title",
    ]


def test_protocol_source_is_appended_after_the_payload_columns():
    """A reporting column added anywhere but the end breaks the payload slice.

    stage0_apply.to_payload slices S.EDGE_ROW_COLUMNS by name, but apply_edges
    asserts the whole frame equals STAGE0_PLAN_COLUMNS in order and the manifest
    is read positionally alongside the report. DerivedFromRelRow is
    extra="forbid", so a reporting column that reached the payload would be a
    hard rejection at the server rather than a wrong value.
    """
    assert S.STAGE0_PLAN_COLUMNS[-1] == "protocol_source"
    assert "protocol_source" not in S.EDGE_ROW_COLUMNS
    assert S.STAGE0_PLAN_COLUMNS[:len(S.EDGE_ROW_COLUMNS)] == S.EDGE_ROW_COLUMNS
    assert len(set(S.STAGE0_PLAN_COLUMNS)) == len(S.STAGE0_PLAN_COLUMNS)


def test_drop_reasons_are_distinct():
    reasons = [S.D_NOT_UID, S.D_NO_NODE, S.D_SELF_LOOP, S.D_ALREADY_EXISTS]
    assert len(set(reasons)) == len(reasons)


def test_original_fixture_still_matches_the_widened_assay_contract():
    # ASSAY_COLUMNS grew by two; make_fixture() builds against that constant and
    # would raise if its rows were not widened to match.
    fx = S.make_fixture()
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS
    assert fx["assays"].iloc[0]["internal_assay_id"] == 11


def test_frozen_fixture_arithmetic_is_unaffected_by_the_new_column():
    # The companion plan hand-traces n_both=2 / n_child_only=1 off these rows.
    # Adding a column to `assays` must not disturb edges or membership.
    fx = S.make_fixture()
    assert len(fx["edges"]) == 7
    assert len(fx["membership"]) == 12
    # `samples` is pinned here too, and it was the frame this world grew MOST
    # (5 rows -> 9) while being the only one with no count. That gap was not
    # theoretical: tests/test_assay_hygiene_claims.py derives claims from this
    # frame against its own vocabulary, so `_fixture_claims()` silently gained
    # two rows -- DNA-2 and PAV-1 -- and nothing in the tree measured it. A row
    # added here changes another file's arithmetic, so it fails here first.
    assert len(fx["samples"]) == 9


def test_stage0_fixture_covers_every_drop_reason_and_one_keeper():
    fx = S.make_stage0_fixture()
    parents = fx["parents"]
    # one token per drop reason, plus two that survive to be created
    assert len(parents) == 6
    # Pinned as a LIST, like `nodes` two cases below. stage0.plan_edges unpacks
    # this frame positionally, so order is part of the contract: a producer
    # emitting child_uuid | token | field swaps two fields and every reference
    # then fails UID validation -- an empty plan with a full not_a_uid count,
    # which is a silent wrong answer rather than a crash.
    assert list(parents.columns) == S.PARENT_COLUMNS
    # exactly one token is AB-*, valid only under the corrected regex
    ab = [t for t in parents["token"] if t.startswith("AB-")]
    assert len(ab) == 1
    assert S.UID_RE_PROD.match(ab[0]) is None

    # Every drop reason must be REACHABLE. Tasks 2-6 hand-trace their drop
    # accounting off this one fixture, so each branch is derived from the frames
    # rather than restated as a literal row: retyping the free text as a UID or
    # deleting the single `existing` row would otherwise remove a branch with
    # all of these tests still green.
    nodes = set(fx["nodes"]["uuid"])
    pairs = list(zip(parents["child_uuid"], parents["token"]))
    not_uid = [(c, t) for c, t in pairs if not S.UID_RE_FIXED.match(t)]
    no_node = [(c, t) for c, t in pairs if S.UID_RE_FIXED.match(t) and t not in nodes]
    self_loop = [(c, t) for c, t in pairs if c == t]
    already = set(zip(fx["existing"]["child_uuid"], fx["existing"]["parent_uuid"]))

    assert len(not_uid) == 1                       # D_NOT_UID
    assert len(no_node) == 1                       # D_NO_NODE
    assert len(self_loop) == 1                     # D_SELF_LOOP
    # a pre-existing edge only causes a drop if some parent row DECLARES it
    assert len(already) == 1 and already <= set(pairs)   # D_ALREADY_EXISTS

    # the four reasons must land on four distinct rows, or one of them is
    # shadowed by another and the branch it names is never exercised
    dropped = set(not_uid) | set(no_node) | set(self_loop) | already
    assert len(dropped) == 4

    # ...leaving exactly two keepers, both of which must resolve in the node
    # index. Drop the AB node and the AB keeper silently becomes a D_NO_NODE.
    keepers = [(c, t) for c, t in pairs if (c, t) not in dropped]
    assert len(keepers) == 2
    assert {t for _, t in keepers} <= nodes


def test_stage0_nodes_frame_matches_the_declared_node_index_contract():
    # `nodes` supplies every child_id / parent_id that reaches the graph, so it
    # needs a contract its producer and consumer can both assert against.
    # Pinned against a literal first: the fixture builds its frame FROM this
    # constant, so asserting only frame-vs-constant is vacuous and stays green
    # through any reordering of the constant itself.
    assert S.NODES_COLUMNS == ["uuid", "sample_id", "type"]
    assert list(S.make_stage0_fixture()["nodes"].columns) == S.NODES_COLUMNS


def test_claim_and_vocab_contracts_are_declared():
    for col in ("sample_id", "uuid", "internal_assay_id",
                "internal_assay_title", "tier", "source_field", "raw_value",
                "contested", "source_provenance"):
        assert col in S.CLAIM_COLUMNS
    for col in ("source_field", "raw_value", "internal_assay_id",
                "internal_assay_title", "support", "n_samples", "purity",
                "provenance"):
        assert col in S.VOCAB_COLUMNS

    # Membership alone cannot see position, and position is part of this
    # contract: `n_samples` qualifies `support` and is only read as its
    # qualifier if it sits next to it. Pinned against a literal, like
    # NODES_COLUMNS above, so that reordering the constant cannot satisfy its
    # own test.
    assert S.VOCAB_COLUMNS == [
        "source_field", "raw_value", "internal_assay_id", "internal_assay_title",
        "support", "n_samples", "purity", "provenance",
    ]

    # CLAIM_COLUMNS is pinned literally for the same reason, and one more.
    # `contested` is a COLUMN and not a tier: disagreement between a sample's
    # claims must not be able to lower any claim's tier, because the audit floor
    # then deletes evidence (102 flags suppressed by 13 added, measured
    # 2026-08-14). A `contested` that drifted back into `tier` would be a
    # membership-only test's blind spot -- both spellings satisfy "the name
    # exists somewhere" -- so assert the shape, in order.
    assert S.CLAIM_COLUMNS == [
        "sample_id", "uuid", "internal_assay_id", "internal_assay_title",
        "tier", "source_field", "raw_value", "contested", "source_provenance",
    ]
    assert "contested" not in (S.T_CORROBORATED, S.T_STRONG, S.T_WEAK,
                               S.T_CONFLICT, S.T_NONE)


def test_tier_and_provenance_constants_are_distinct():
    tiers = [S.T_CORROBORATED, S.T_STRONG, S.T_WEAK, S.T_CONFLICT, S.T_NONE]
    assert len(set(tiers)) == len(tiers)
    prov = [S.P_LEARNED, S.P_PROPOSED, S.P_CURATOR]
    assert len(set(prov)) == len(prov)


def test_strong_and_weak_fields_are_disjoint_and_ordered_strong_first():
    # Tier assignment reads CLAIM_FIELDS in order and the strong fields must be
    # seen first, so a sample carrying both a strong and a weak field is graded
    # on the strong one. Overlap would make a field both deciding and merely
    # corroborating, which is not a state the tier logic can represent.
    assert not set(S.STRONG_FIELDS) & set(S.WEAK_FIELDS)
    assert S.CLAIM_FIELDS == S.STRONG_FIELDS + S.WEAK_FIELDS


def test_protocol_is_a_weak_field_not_a_strong_one():
    # Measured 2026-08-14, held out by sample against the 360,027 labelled
    # edges: strong fields alone score 98.4% accuracy at 65.9% coverage;
    # adding Protocol and DataType raises coverage to 92.3% and drops accuracy
    # to 90.4%, under the 95% bar. Protocol corroborates, it does not decide.
    assert "Protocol" in S.WEAK_FIELDS
    assert "Protocol" not in S.STRONG_FIELDS
    assert "Type" in S.STRONG_FIELDS


def test_normalise_value_folds_case_and_whitespace():
    # `Liver`, `liver` and `LIVER` occur as three values on the same field in
    # production; these are curator-entered free text with no controlled
    # vocabulary.
    assert S.normalise_value("  CometChip ") == "cometchip"
    assert S.normalise_value("Comet  Chip") == "comet chip"
    assert S.normalise_value("") is None
    assert S.normalise_value(None) is None
    assert S.normalise_value(7) is None


def test_fixture_samples_exercise_every_tier():
    fx = S.make_fixture()
    assert list(fx["samples"].columns) == S.SAMPLE_COLUMNS
    by_uuid = {r.uuid: json.loads(r.json_metadata)
               for r in fx["samples"].itertuples()}
    assert by_uuid["D.IMG-1"]["Type"] == "CometChip"      # -> corroborated
    assert by_uuid["D.IMG-1"]["Protocol"] == "comet.docx"
    assert by_uuid["D.IMG-2"]["Type"] == "CometChip"      # -> strong
    assert "Protocol" not in by_uuid["D.IMG-2"]
    assert by_uuid["D.IMG-3"]["Protocol"] == "comet.docx"  # -> weak
    assert "Type" not in by_uuid["D.IMG-3"]
    assert by_uuid["TIS-1"]["Type"] == "CometChip"        # -> conflict
    assert by_uuid["TIS-1"]["Instrument"] == "tissue scope"
    assert "Type" not in by_uuid["DNA-1"]                 # -> none

    # The four rows added 2026-08-17 for the gate, pinned by uuid beside the
    # original five. Each names the ONE term whose rejection it exists to
    # exercise, so retyping a raw value here fails at its source rather than as
    # a gate case that quietly stopped firing.
    assert by_uuid["DNA-2"]["Type"] == "CometChip"          # -> GATE_UNREACHABLE
    assert by_uuid["TIS-3"]["Software"] == "cometchip"      # -> GATE_INCOHERENT
    assert by_uuid["TIS-3"]["Instrument"] == "curator call"  # -> passes anyway
    assert by_uuid["TIS-4"]["Type"] == "rare term"          # -> low support
    assert by_uuid["TIS-4"]["DataType"] == "illumina library"  # -> low purity
    assert by_uuid["PAV-1"]["Instrument"] == "tissue scope"  # -> already held
    # ...and the pairing that makes TIS-3 the per-CLAIM case: one rejected and
    # one passing claim on ONE sample. Two keys, not one.
    assert set(by_uuid["TIS-3"]) == {"Software", "Instrument"}


def test_fixture_membership_content_pins_the_propagation_arithmetic():
    """The rows n_both=2 / n_child_only=1 / propagation_rate=2/3 are computed FROM.

    Those counts are a function of the membership frame's CONTENT, not of its
    length: retyping row (102, 1) to (102, 2) moves n_child_only from 1 to 0
    while `len(membership) == 10` stays green. The derived assertions further up
    do catch that particular edit, but each of them averages the frame down to a
    handful of numbers, so a compensating pair of edits -- or any edit to the
    TIS -> MUS rows, which no derived test resolves individually -- can still
    slip past. This is the literal pin, in the same spirit as the NODES_COLUMNS
    test above: assert the rows, then re-derive the headline rate from them so
    the two cannot drift apart.

    Deliberately NOT re-asserted here: len(edges), the assay titles, the hop
    Counter and (n_both, n_child_only) itself. All four are already covered
    above, and restating them was what made the previous version of this test
    vacuous.
    """
    fx = S.make_fixture()
    assert set(zip(fx["membership"]["sample_id"], fx["membership"]["assay_id"])) == {
        (100, 1), (200, 1),          # both in Comet Chip
        (101, 1), (201, 1),          # both in Comet Chip
        (102, 1), (202, 2),          # disjoint -> the mode 2 case
        (203, 2), (500, 1),          # disjoint, but hop does not propagate
        (200, 2), (201, 2),          # parents also in Tissue Collection
        (700, 2), (700, 3),          # the domain rule: produced by 3, consumed by 2
    }

    # the rate Tasks 5 and 6 actually quote, re-derived from the rows above
    reg = _registration(fx)
    assays = fx["assays"]
    comet = assays.loc[assays["title"] == "Comet Chip", "assay_id"].iloc[0]
    edges = fx["edges"]
    hop = edges[(edges["child_type"] == "D.IMG") & (edges["parent_type"] == "TIS")]
    n_both = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                 if comet in reg.get(c, set()) and comet in reg.get(p, set()))
    n_child_only = sum(1 for c, p in zip(hop["child_id"], hop["parent_id"])
                       if comet in reg.get(c, set()) and comet not in reg.get(p, set()))
    assert n_both / (n_both + n_child_only) == 2 / 3


def test_fixture_sample_uuids_agree_with_the_edge_frame():
    # The samples frame gained three rows (101, 102, 200) when the claim tiers
    # were added, and besides edges it is the only frame carrying sample_id and
    # uuid TOGETHER. Stage B2 and the mode-3 audit produce claims keyed by uuid
    # and join them to edges, so a uuid that disagrees with the edge frame's
    # child_uuid / parent_uuid for the same id does not raise -- it drops or
    # mis-joins rows and reports a smaller, entirely plausible answer.
    fx = S.make_fixture()
    edges = fx["edges"]
    by_id = dict(zip(edges["child_id"], edges["child_uuid"]))
    by_id.update(zip(edges["parent_id"], edges["parent_uuid"]))
    for sid, uuid in zip(fx["samples"]["sample_id"], fx["samples"]["uuid"]):
        assert by_id[sid] == uuid, f"sample {sid} uuid disagrees with the edge frame"


def test_audit_columns_carry_both_sides_of_the_comparison():
    # Mode 3 flags a sample whose own metadata claims an assay it is NOT
    # registered in, so an audit row has to carry both sides -- the registered
    # ids and the claimed one -- or a curator cannot see what the disagreement
    # was. The claim's evidence rides along for the same reason: a verdict with
    # no tier / source_field / raw_value is not auditable, it is just an
    # assertion.
    for col in ("sample_id", "uuid", "sample_type",
                "registered_internal_assay_ids", "claimed_internal_assay_id",
                "claimed_internal_assay_title", "tier", "source_field",
                "raw_value", "verdict"):
        assert col in S.AUDIT_COLUMNS
    # The claimed side is named distinctly from the registered side on purpose.
    # A bare `internal_assay_id` here would sit in an adjacent frame to
    # CLAIM_COLUMNS' column of that exact name, where joining the wrong one is a
    # one-token edit that yields a populated, wrong column rather than an error
    # -- the same hazard EDGE_COLUMNS documents for edge_internal_assay_id.
    assert "internal_assay_id" not in S.AUDIT_COLUMNS
    assert "internal_assay_title" not in S.AUDIT_COLUMNS
    assert len(set(S.AUDIT_COLUMNS)) == len(S.AUDIT_COLUMNS)


# --- stage C vocabulary ------------------------------------------------------


def _string_constants(prefix):
    """Every module-level `str` constant named `prefix*`, as {name: value}.

    Derived from the module rather than hand-listed, so a constant added to the
    family without being added to its closed tuple fails the closure test below
    instead of quietly becoming a value nothing recognises. The `str` filter is
    what keeps the tuples themselves (`GATE_OUTCOMES`, `MODES`) out of their own
    membership check.
    """
    return {n: v for n, v in vars(S).items()
            if n.startswith(prefix) and isinstance(v, str)}


def test_every_stage_c_family_is_closed():
    """Each family enumerates itself, and the tuple is the enumeration.

    A closed vocabulary that cannot be enumerated cannot be checked for closure
    by any consumer, which is the whole point: the gate, the classifier and the
    report all have to answer "is this one of the four" without restating the
    four. `PROVENANCES` is the same pattern one section up.
    """
    for prefix, closed in (("MODE_", S.MODES),
                           ("GATE_", S.GATE_OUTCOMES),
                           ("CLS_", S.CLASSES),
                           ("LIN_", S.LINEAGE_RELATIONS),
                           ("BAND_", S.COMPAT_BANDS)):
        family = _string_constants(prefix)
        assert set(family.values()) == set(closed), (
            f"{prefix}* constants {sorted(family)} disagree with the closed "
            f"tuple {closed}")
        assert len(set(closed)) == len(closed), f"{prefix}* has a duplicate value"

    # The class vocabulary is the one the spec names as closed, so it is pinned
    # literally as well: closure against a tuple that itself grew is vacuous.
    assert S.CLASSES == (S.CLS_ABSENCE_LINEAGE, S.CLS_ABSENCE_COMPAT,
                         S.CLS_ALT_LABEL, S.CLS_UNRESOLVED)
    # Rejections are a SUBSET of the outcomes, in the same shape
    # EVIDENCE_PROVENANCES takes to PROVENANCES: precedence rule 1 ("a rejected
    # claim reaches no mode, ever") is then a membership test rather than three
    # inequalities a later edit can forget to extend.
    assert set(S.GATE_REJECTIONS) < set(S.GATE_OUTCOMES)
    assert S.GATE_PASS not in S.GATE_REJECTIONS


def test_stage_c_vocabulary_does_not_collide_with_the_verdict_action_or_tier_families():
    """New families, not overloads of the per-edge ones.

    `V_*` is the retired per-edge verdict vocabulary (only `V_MODE3_FLAG` still
    has a producer, in `audit.py`), `A_*` the action vocabulary and `T_*` the
    claim tiers. A stage C value equal to one of theirs would be readable in the
    wrong column without erroring, which is the failure this whole module is
    shaped around.
    """
    existing = set()
    for prefix in ("V_", "A_", "T_", "D_", "P_"):
        existing |= set(_string_constants(prefix).values())
    new = set()
    for prefix in ("MODE_", "GATE_", "CLS_", "LIN_", "BAND_"):
        new |= set(_string_constants(prefix).values())

    assert not (existing & new), f"colliding values: {sorted(existing & new)}"
    # ...and distinct within the new families too, across all five of them
    all_new = [v for prefix in ("MODE_", "GATE_", "CLS_", "LIN_", "BAND_")
               for v in _string_constants(prefix).values()]
    assert len(set(all_new)) == len(all_new)


def test_mode_3_is_named_but_has_no_detector_so_it_is_never_emitted():
    """Mode 3 exists in the design and emits nothing.

    Measured 2026-08-17 over increment 1's 866 audit flags: not one is a
    contradiction. 576 are absences, 31 vocabulary defects, 45 alternative
    labels, 214 unclassified. The detector built for "what samples have
    INCORRECT assays" finds claims that disagree with registrations, and that
    population is alternative labels, so the mode is UNDETECTED rather than
    small.

    The constant stays, because the report has to name the mode in order to say
    it found nothing, and a mode the vocabulary cannot spell would be reported
    as absent instead of as undetected. `EMITTED_MODES` is what a producer
    checks against, and it is the pair.
    """
    assert S.MODE_3 in S.MODES
    assert S.MODE_3 not in S.EMITTED_MODES
    assert S.EMITTED_MODES == (S.MODE_1, S.MODE_2)


def test_the_two_reporting_numbers_gate_nothing():
    """Nothing in the package reads either number, which is the whole claim.

    An earlier version of this test asserted the two values, their types and a
    band distinctness `test_every_stage_c_family_is_closed` already covers, and
    then called itself "gate nothing". None of that is evidence about gating:
    the title certified a property the body never exercised, which is the
    self-certifying-test failure increment 1 shipped five of.

    The checkable form until 2026-08-17 was that NO module under
    `scripts/assay_hygiene/` references either name. That version has now done
    its job: Task 4 needed them for banding, this test failed, and the reader
    had to be named and confirmed. THE BAN IS NOT LIFTED, IT IS NARROWED to one
    approved module, so the same cost falls on the next reader.

    THE APPROVED READER IS `compatibility.py`, AND WHAT IT DOES WITH THEM IS
    BAND. `compat_band` maps a measured rate onto one of `COMPAT_BANDS` so an
    operator reads the strongest evidence first. Confirmed by reading it:

      * `MIN_CO_REG_SUPPORT` decides only which LABEL an unread rate gets --
        `BAND_NO_SUPPORT` rather than `BAND_NEVER` -- which is the distinction
        that stops a rate of 0.000 over four samples being reported as "these
        two assays never coexist".
      * `CO_OCCUR_BAND` separates `BAND_ROUTINE` from `BAND_SOMETIMES`. BOTH are
        reported and both reach the operator, so moving it changes reading
        order and changes nothing else. `BAND_NEVER`, the band that carries the
        alternative-label finding, rests on a rate of exactly 0.0 and so has no
        tuned number in it at all.
      * Neither appears in any expression deciding whether a row reaches Mode 1
        or Mode 2. That is `gate.blocks_mode`, it tests membership of a closed
        tuple, and `test_assay_hygiene_gate.py` pins it.

    A THIRD READER FAILS THIS TEST AGAIN, deliberately.
    """
    package = REPO / "scripts" / "assay_hygiene"
    APPROVED = {"compatibility.py"}
    readers = sorted(
        p.name for p in package.glob("*.py")
        if p.name != "_schema.py" and p.name not in APPROVED
        and ("MIN_CO_REG_SUPPORT" in p.read_text()
             or "CO_OCCUR_BAND" in p.read_text())
    )
    assert not readers, (
        f"{readers} read a reporting number. Both are declared bands with no "
        "backtest behind them: under universal approval there is no autonomous "
        "write for a threshold to gate, so a reader may BAND on them and must "
        "never decide whether a row is PROPOSED. Confirm that, then name the "
        f"reader here beside {sorted(APPROVED)}.")

    # ...and the approved reader is still THERE. A test that only forbids
    # readers passes trivially once the approved one is deleted or renamed, and
    # would then re-arm against nothing.
    assert (package / "compatibility.py").exists()
    compat = (package / "compatibility.py").read_text()
    assert "MIN_CO_REG_SUPPORT" in compat and "CO_OCCUR_BAND" in compat
    # the shape of the read: both appear inside `compat_band` and the only
    # comparison against either is the one that picks a label.
    banding = compat.split("def compat_band(")[1].split("\ndef ")[0]
    assert "S.MIN_CO_REG_SUPPORT" in banding and "S.CO_OCCUR_BAND" in banding
    assert compat.count("S.MIN_CO_REG_SUPPORT") == banding.count(
        "S.MIN_CO_REG_SUPPORT"), (
        "MIN_CO_REG_SUPPORT is compared outside compat_band, which is where a "
        "band turns into a gate")
    assert compat.count("S.CO_OCCUR_BAND") == banding.count("S.CO_OCCUR_BAND"), (
        "CO_OCCUR_BAND is compared outside compat_band, which is where a band "
        "turns into a gate")

    # ...and the declarations themselves, so the values cannot drift silently
    assert S.MIN_CO_REG_SUPPORT == 30
    assert S.CO_OCCUR_BAND == 0.5
    assert isinstance(S.MIN_CO_REG_SUPPORT, int)   # a count of samples of a type
    assert 0.0 < S.CO_OCCUR_BAND < 1.0             # a rate
    assert S.BAND_NO_SUPPORT != S.BAND_NEVER
    assert {S.BAND_NO_SUPPORT, S.BAND_NEVER} <= set(S.COMPAT_BANDS)


# --- what the extended fixture must express ----------------------------------


def _types(fx):
    """sample_id -> sample type, read off the only frame that carries it."""
    t = dict(zip(fx["edges"]["child_id"], fx["edges"]["child_type"]))
    t.update(zip(fx["edges"]["parent_id"], fx["edges"]["parent_type"]))
    return t


def _internal(fx):
    """seek assay_id -> internal_assay_id, for the fixture's fully-junctioned frame."""
    return dict(zip(fx["assays"]["assay_id"], fx["assays"]["internal_assay_id"]))


def _registered_internal(fx):
    """sample_id -> set of INTERNAL assay ids, ANY-membership definition.

    ANY membership row counts, which is the definition `audit.registered_internal`
    uses and the one that differs from "has a MAPPABLE membership row" by 82
    samples on the real extract, because 17 assays carry no junction row. The
    fixture is fully junctioned, so the two agree here; the helper is named for
    the definition anyway so a later reader does not have to guess which one a
    derived count came from.
    """
    internal = _internal(fx)
    out = {}
    for sid, aid in zip(fx["membership"]["sample_id"], fx["membership"]["assay_id"]):
        out.setdefault(sid, set()).add(internal[aid])
    return out


def _claims(fx):
    """(sample_id, sample_type, internal_assay_id, vocab row) per claim.

    Resolved here from the samples and vocabulary frames rather than by calling
    `claims.sample_claims`, so this file keeps testing the DATA and not stage
    B2's implementation of it.
    """
    vocab = {(r.source_field, r.raw_value): r
             for r in fx["vocabulary"].itertuples(index=False)}
    types = _types(fx)
    out = []
    for r in fx["samples"].itertuples(index=False):
        for field, value in json.loads(r.json_metadata).items():
            row = vocab.get((field, S.normalise_value(value)))
            if row is not None:
                out.append((r.sample_id, types[r.sample_id],
                            row.internal_assay_id, row))
    return out


def test_fixture_expresses_a_sample_legitimately_in_two_assays():
    """The domain rule increment 1's code could not represent.

    A PAV that had tissue collected from it belongs in the assay that PRODUCED
    it and the one that CONSUMED it; neither registration excludes the other,
    and reading the second as a contradiction is the error the operator
    corrected twice. Derived from the frames: some sample holds two internal
    assays AND shares one of them with a lineage neighbour, which is what makes
    the pair evidence rather than coincidence.

    Stated so nobody over-reads this test: the 2026-08-14 rows ALREADY satisfied
    it -- TIS 200 and 201 each hold Comet Chip and Tissue Collection -- so it
    passed before the fixture was extended and it survives deleting the new
    `TIS -> PAV` rows. It is a drift pin on a property the fixture has, not
    evidence for the addition. The new structural case is pinned by
    `test_fixture_reaches_both_mode_2_directions`, which does fail without it.
    """
    fx = S.make_fixture()
    reg = _registered_internal(fx)
    pairs = list(zip(fx["edges"]["child_id"], fx["edges"]["parent_id"]))

    two_assay = {s for s, a in reg.items() if len(a) > 1}
    assert two_assay, "no sample is registered in two assays"

    # ...and at least one of them proves the rule: it shares an assay with a
    # neighbour (the consuming side) while holding one the neighbour lacks (the
    # producing side). Without the second half this is just a co-registration.
    proved = [(c, p) for c, p in pairs
              if (p in two_assay and reg.get(c, set()) & reg[p]
                  and reg[p] - reg.get(c, set()))]
    assert proved, "no edge shows one shared assay and one legitimately unshared"


def test_fixture_reaches_both_mode_2_directions():
    """Both directions occur, and one hop reaches ONLY the weak one.

    A child carrying an assay its parent lacks proposes A_ADD_PARENT, the
    direction the domain rule justifies and co-registration corroborates 88/88.
    A parent carrying one its child lacks proposes A_ADD_CHILD, the mirror,
    corroborated 15/263. Mode 2 needs both, and a Mode 2 case needs BOTH
    endpoints registered -- a dark endpoint is Mode 1 and takes precedence, so
    the `300 -> 200` edge is not an A_ADD_CHILD case however it reads.

    The second assertion is the one that costs something. Before this task every
    Mode-2-eligible hop reached both directions at once, so a classifier reading
    direction off "the edge is disjoint" rather than off the ASSAY was
    indistinguishable from a correct one. The `TIS -> PAV` hop reaches
    A_ADD_CHILD and nothing else.
    """
    fx = S.make_fixture()
    reg = _registered_internal(fx)
    lin_child, lin_parent = set(), set()
    for c, p, ct, pt in zip(fx["edges"]["child_id"], fx["edges"]["parent_id"],
                            fx["edges"]["child_type"], fx["edges"]["parent_type"]):
        ca, pa = reg.get(c, set()), reg.get(p, set())
        if not (ca and pa):
            continue                      # a dark endpoint is Mode 1, not Mode 2
        if ca - pa:
            lin_child.add((ct, pt))
        if pa - ca:
            lin_parent.add((ct, pt))

    assert lin_child, "no Mode 2 edge where the child carries an unshared assay"
    assert lin_parent, "no Mode 2 edge where the parent carries an unshared assay"
    assert lin_parent - lin_child, (
        "every Mode 2 hop reaches both directions, so a classifier that keys "
        "direction off the edge rather than off the assay would pass")


def test_fixture_hop_rates_differ_so_a_direction_swap_cannot_pass():
    """`propagation_rate` and `reverse_rate` differ on at least one hop.

    Mode 2 reads `propagation_rate` for A_ADD_PARENT and `reverse_rate` for
    A_ADD_CHILD. On a fixture where the two are equal, a classifier that reads
    the wrong one passes every test written against it. Re-derived from the
    frames here rather than imported from `precedent`, so this pins the DATA:
    if a membership edit ever equalised the two, stage B would still be correct
    and every Mode 2 direction test downstream would go quietly vacuous.
    """
    fx = S.make_fixture()
    reg = _registered_internal(fx)
    edges = fx["edges"]
    hop = edges[(edges["child_type"] == "D.IMG") & (edges["parent_type"] == "TIS")]
    comet = 11

    n_both = n_child_only = n_parent_only = 0
    for c, p in zip(hop["child_id"], hop["parent_id"]):
        in_c, in_p = comet in reg.get(c, set()), comet in reg.get(p, set())
        n_both += in_c and in_p
        n_child_only += in_c and not in_p
        n_parent_only += in_p and not in_c

    propagation = n_both / (n_both + n_child_only)
    reverse = n_both / (n_both + n_parent_only)
    assert (propagation, reverse) == (2 / 3, 1.0)
    assert propagation != reverse


def _incoherent_families(fx):
    """(field, leading token) groups whose members map to more than one assay.

    The leading token is a stand-in for whatever stem rule the gate ships; what
    is asserted below is the DATA -- that such a group exists and that a claim
    rests on it -- and never this grouping.
    """
    families = {}
    for r in fx["vocabulary"].itertuples(index=False):
        families.setdefault((r.source_field, r.raw_value.split()[0]),
                            set()).add(r.internal_assay_id)
    return {k for k, v in families.items() if len(v) > 1}


# Floors used ONLY by the helper below, to show the fixture can reach each
# rejection kind. NEITHER IS A SHIPPED THRESHOLD and neither is imported from
# `_schema`. Task 2 owns the real ones and takes them as `min_support` and
# `min_purity` parameters.
#
# `_TEST_MIN_SUPPORT` is deliberately NOT `S.MIN_CO_REG_SUPPORT`, which an
# earlier version of this file borrowed. That was a units mismatch and it is
# this branch's signature defect one level down: `MIN_CO_REG_SUPPORT` counts
# SAMPLES OF A TYPE and sizes the co-registration population, while
# `VOCAB_COLUMNS.support` counts EDGES -- `_schema.py` warns about exactly that
# gap and records that 50 of the 736 learned terms rest on a single sample. The
# two numbers happen to share the value 30 and mean different things, so the
# comparison read plausibly and was wrong. Borrowing it here also made this file
# the only gate-shaped use of a reporting number in the tree, in the same file
# as a test asserting those numbers gate nothing.
_TEST_MIN_SUPPORT = 30      # a floor on the EDGE count in VOCAB_COLUMNS.support
_TEST_MIN_PURITY = 0.8


def _gate_kinds(fx):
    """claim -> the set of rejection KINDS that fire on it, ANY-membership based.

    Kinds, not outcomes: the support and purity floors are both
    GATE_LOW_SUPPORT, so they count as one. A curator mapping is exempt from the
    floors and from the family check, because a human ruling outranks the data.

    The floors are the test-local ones above, never the shipped constants.
    """
    reg = _registered_internal(fx)
    types = _types(fx)
    type_reg = {(types[s], a) for s, assays in reg.items() for a in assays}
    incoherent = _incoherent_families(fx)

    out = {}
    for claim in _claims(fx):
        sid, stype, aid, row = claim
        kinds = set()
        if (stype, aid) not in type_reg:
            kinds.add(S.GATE_UNREACHABLE)
        if row.provenance != S.P_CURATOR:
            if (row.source_field, row.raw_value.split()[0]) in incoherent:
                kinds.add(S.GATE_INCOHERENT)
            if row.support < _TEST_MIN_SUPPORT or row.purity < _TEST_MIN_PURITY:
                kinds.add(S.GATE_LOW_SUPPORT)
        out[claim] = kinds
    return out


def test_fixture_vocabulary_reaches_every_gate_rejection():
    """One claim per rejection kind, each isolated to the kind it exercises.

    Everything here is derived from the frames rather than asserted by id. Two
    isolation properties are asserted and both were violated by the first
    version of this fixture:

    1. **Exactly one kind fires per rejected claim.** A claim failing two tests
       at once cannot show which one caught it, which is how increment 1 filed
       24 vocabulary defects as lineage absences.
    2. **No rejected claim names an assay its sample already holds.** That was
       true of three of the five cases as first written, and it is the quieter
       defect: such a claim yields no proposal for a reason that has nothing to
       do with the gate, so a downstream gate regression test built on it passes
       whether the gate works or not.
    """
    fx = S.make_fixture()
    reg = _registered_internal(fx)
    kinds = _gate_kinds(fx)
    assert kinds, "the fixture's samples produce no claims against its vocabulary"

    fired = {k for ks in kinds.values() for k in ks}
    assert fired == set(S.GATE_REJECTIONS), (
        f"the fixture reaches {sorted(fired)}, not every rejection kind")

    for claim, ks in kinds.items():
        assert len(ks) <= 1, f"{claim[0]} is rejected by {sorted(ks)}, not one kind"
        if ks:
            assert claim[2] not in reg.get(claim[0], set()), (
                f"sample {claim[0]}'s rejected claim names assay {claim[2]}, "
                "which it already holds, so nothing downstream can tell the "
                "gate's rejection from an already-registered drop")

    # The unreachable claim's TERM must be reachable for some other type, or the
    # case does not distinguish an incredible claim from a term nothing maps.
    unreachable = [c for c, ks in kinds.items() if S.GATE_UNREACHABLE in ks]
    elsewhere = {c[3].raw_value for c, ks in kinds.items() if not ks}
    assert {c[3].raw_value for c in unreachable} & elsewhere

    # Both floors are reached separately, or GATE_LOW_SUPPORT is only half tested
    floored = [c for c, ks in kinds.items() if S.GATE_LOW_SUPPORT in ks]
    assert any(c[3].support < _TEST_MIN_SUPPORT for c in floored)
    assert any(c[3].purity < _TEST_MIN_PURITY for c in floored)

    # The whole incoherent family is reportable, not just its minority member.
    incoherent = _incoherent_families(fx)
    assert incoherent
    for field, token in incoherent:
        members = [r for r in fx["vocabulary"].itertuples(index=False)
                   if (r.source_field, r.raw_value.split()[0]) == (field, token)]
        assert len(members) >= 2

    # The negative case for stem extraction: same field, DIFFERENT products,
    # different assays, sharing a substring but not a leading token. A substring
    # rule collapses these and reports a family that is not one.
    rows = list(fx["vocabulary"].itertuples(index=False))
    negatives = [(a, b) for a in rows for b in rows
                 if a.source_field == b.source_field
                 and a.raw_value < b.raw_value
                 and a.internal_assay_id != b.internal_assay_id
                 and a.raw_value.split()[0] != b.raw_value.split()[0]
                 and (a.raw_value.split()[0] in b.raw_value
                      or b.raw_value.split()[0] in a.raw_value)]
    assert negatives, "no pair a substring-based stem rule would wrongly collapse"

    # A curator mapping below EVERY floor, which must still pass: a human
    # decision outranks the data, whatever its support.
    curator = [c for c in kinds if c[3].provenance == S.P_CURATOR]
    assert curator, "no curator-provenance claim"
    for c in curator:
        assert c[3].support < _TEST_MIN_SUPPORT and c[3].purity < _TEST_MIN_PURITY, (
            "the curator claim clears the floors, so it cannot show that "
            "provenance overrides them")
        assert not kinds[c]

    # ...and one sample carrying both a rejected and a passing claim, so the
    # gate is forced to be per CLAIM and not per sample.
    by_sample = {}
    for claim, ks in kinds.items():
        by_sample.setdefault(claim[0], []).append(bool(ks))
    assert any(any(v) and not all(v) for v in by_sample.values()), (
        "no sample carries both a rejected and a passing claim")


def test_fixture_frames_round_trip_through_parquet(tmp_path):
    """The fixture must survive the format the real extract is stored in.

    Every frame stage A produces is written to and read back from parquet, and
    a fixture that cannot make that trip is not a stand-in for one: a column of
    ints-with-nulls, or the vocabulary's mixed int / float / str row, is exactly
    where a synthetic frame and a real one diverge. Written under `tmp_path`,
    never into the checkout, because `plugin_sentinel` treats a file appearing
    there as a P1.
    """
    fx = S.make_fixture()
    for name, frame in fx.items():
        path = tmp_path / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        back = pd.read_parquet(path)
        assert list(back.columns) == list(frame.columns), name
        assert len(back) == len(frame), name
        pd.testing.assert_frame_equal(back, frame, check_dtype=False)


def test_fixture_vocabulary_matches_the_declared_contract():
    fx = S.make_fixture()
    assert list(fx["vocabulary"].columns) == S.VOCAB_COLUMNS
    assert set(fx["vocabulary"]["provenance"]) <= set(S.PROVENANCES)
    # normalised already, because `normalise_value` is what every lookup goes
    # through and a fixture carrying `CometChip` would match nothing
    assert all(v == S.normalise_value(v) for v in fx["vocabulary"]["raw_value"])
