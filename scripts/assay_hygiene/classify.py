# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage C. One pass, the precedence that orders it, and the three modes.

NOTHING DECIDES. EVERYTHING PROPOSES. Every row this module builds reaches the
operator as a proposal they approve or reject, no number in it authorises a
change, and no function here is named for a decision. It reads six parquet files
and one csv, and it writes exactly two csv files under `out_dir` --
`findings.csv` and `mode3-disposition.csv` -- and nothing else, ever. No
database is touched, no workbook is produced, and there is no APPROVE column.

THE PRECEDENCE IS THE CONTRACT, and it is the tuple `PRECEDENCE` rather than the
order of six `if` branches a later edit could reorder without failing anything:

    1. GATE        a rejected claim reaches no mode, ever
    2. MODE 1      registered in nothing (the ANY-membership definition)
    3. LINEAGE     a neighbour carries it AND the pair is reachable -> Mode 2
    4. UNREACHABLE a neighbour carries it and NO sample of this type is
                   registered in this assay anywhere -> Mode 2, GATE_UNREACHABLE
    5. COMPAT      routinely coexists -> Mode 2 candidate, unproven
                   never coexists     -> CLS_ALT_LABEL, no action
                   otherwise          -> CLS_UNRESOLVED
    6. MODE 3      emits nothing; no detector exists

Three of the five adjacent swaps in that list change a measured number, which is
what makes it a contract rather than a comment. Re-measured 2026-08-21 over the
175,339 input keys: GATE with MODE 1 moves 746 keys, MODE 1 with LINEAGE 749,
LINEAGE with UNREACHABLE 67,898, UNREACHABLE with COMPAT 0. The fifth moves none
either, because `PRE_MODE_3` claims no key under any evidence at all -- which is
a finding and not an oversight.

The 2026-08-17 reading of that sentence was 180,995 / 746 / 753 / 903, against a
vocabulary with no curator rows. The operator then retired `DataType: tif`,
`DataType: png`, `Type: illumina library` and the `Software: flowjo` family, and
every figure here was re-derived rather than adjusted. The FIRST swap is
unchanged at 746 -- it counts keys the gate refuses, and a retired term raises no
key for the gate to refuse -- which is the cross-check that the retirement moved
what it should and nothing else. That reading had no UNREACHABLE step at all;
its third figure, 903, is the LINEAGE-with-COMPAT swap this list no longer has,
and the 761 it later became is likewise gone rather than restated.

STEP 4 IS NEW ON 2026-08-21 AND IT IS NOT A NEW POPULATION. Step 3 used to claim
every lineage key without asking the question `gate.type_registration_index`
exists to answer -- so 99,449 of the 167,454 emitted MODE_2 rows proposed a
(type, assay) pair the house has never once made, while a metadata CLAIM on the
same pair was refused. Those rows are still emitted and `rows` did not move:
they now carry `GATE_UNREACHABLE` and `CLS_UNREACHABLE` and are counted as
`keys_unreachable`, so a curator can see and override them.

THE FOURTH SWAP'S ZERO IS THE DESIGN ARGUMENT FOR WHERE STEP 4 SITS, not a gap.
It could only move a key whose claim PASSED the gate on a pair the lineage lane
calls unreachable, and `gate.gate_claims` BLOCKS a claim on `registrations == 0`
outright, so `PRE_GATE` takes such a key three steps earlier. Step 4 therefore
sees only lineage-only keys and can test `e.lineage` alone.

MODE 3 EMITS ZERO ROWS AND THAT IS MEASURED, NOT ASSUMED. Increment 1 reported
866 contradictions. Under this precedence not one survives: 43 are gate rejects,
326 are lineage absences, 247 name a pair that routinely coexists, 205 are
unresolved and 45 are ALTERNATIVE LABELS -- D.IMG images sit in 127 Tissue
Imaging or in 145 Histopathology and never in both, because a curator picks one,
and 145 D.IMG samples are registered in Histopathology. Metadata disagreeing
with a registration is not evidence that the registration is wrong, so the
residue of the subtraction is empty and `mode3_findings` returns an EMPTY frame
rather than a small one. Undetected and small are different findings.

MODE 2 LIVES IN `mode2.py`. It was split out at about 780 lines when this file
reached roughly 1,340 and the compatibility lane, the precedence and the unified
emitter were still to be added. This module keeps what both modes read -- the
shared frame, the indexes, the `BY_*` family and `_registered_columns` -- so
`mode2` imports `classify` and `classify` imports `mode2` lazily inside `main`,
as it already does for `precedent` and `vocabulary`.

Mode 1 answers the operator's first question -- "what samples have no assays and
need some" -- and metadata is the only evidence available for it. Such a sample
has no membership to reason from, and under the precedence contract Mode 1 is
settled BEFORE the lineage and co-registration tests run. So a Mode 1 proposal is
exactly as good as the vocabulary row behind it, which is why `gate` runs in
front and why a blocked claim reaches no row.

THE POPULATION IS 6,242 AND NOT 6,324. "Registered" means ANY membership row,
which is the definition `audit.registered_internal` implements and this module
takes from it rather than re-deriving. The MAPPABLE-only reading -- ignore the
registrations that resolve through one of the 17 assays with no junction row --
is 82 samples larger. Every one of those 82 IS registered; only the INTERNAL
IDENTITY of its assay is unknown, because `precedent.assay_index` falls back to
the seek id, which is a different id space. Proposing a FIRST assay for a sample
that already has one is not a smaller error than missing one, and the same
confusion has already produced a wrong Mode 2 ceiling on this branch.

PASSAGE IS `gate.reaches_modes`, WHICH READS `gate_failures`. Never
`gate == GATE_PASS`: `gate` is the most severe outcome only, the two floors are
tuned numbers that are RECORDED rather than blocking, and reading passage off
that column drops 25,974 claims across the package and 612 Mode 1 rows.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \\
        python -m assay_hygiene.classify

Measured over the real extract 2026-08-17, and all four before-gate figures were
carried into this task correctly:

    population, registered in no assay                 6,242
      of which their metadata proposes nothing         4,415
      of which it proposes at least one assay          1,827   over 2,912 claims

    after the gate                                     1,657   over 2,166 claims
      blocked, every one of them GATE_UNREACHABLE        170   over   746 claims
      reaching Mode 1 carrying a recorded floor failure           612 claims

    at the strong and corroborated tiers, before the gate   671 / 671
    at the strong and corroborated tiers, after it          590 / 590

The after-gate figures had not been measured by anyone before this task.

And the unified pass, RE-MEASURED 2026-08-21 over the same extract, every figure
re-derived rather than adjusted. The INPUT is every (sample, proposed assay)
ABSENCE key -- one a metadata claim names, or one a lineage neighbour makes
available, or both -- and the SIX steps partition it:

    attached claims                                  130,764
      naming an assay the sample already holds       122,011   no absence, no key

    input keys                                       175,339
      PRE_GATE        refused, a rejected claim        4,553   emits nothing
      PRE_MODE_1      registered in nothing            1,373
      PRE_LINEAGE     a neighbour carries it,
                      and the pair is reachable       67,898
      PRE_UNREACHABLE a neighbour carries it, and no
                      sample of this type is
                      registered in this assay        99,449
      PRE_COMPAT      the co-registration test         2,066
      PRE_MODE_3      the residue                          0   no detector

    emitted rows                                     170,786
      MODE_1                                           1,373
      MODE_2     lineage 67,898 + unreachable 99,449
                 + compat 107                        167,454
      no mode    952 CLS_ALT_LABEL + 1,007 CLS_UNRESOLVED      1,959
      MODE_3                                               0

THE PRE_LINEAGE ROW OF THAT TABLE DENOTES A SMALLER POPULATION THAN IT USED TO,
and that is the only line whose MEANING moved rather than its value. It read
167,330 against a step that claimed every lineage key; `PRE_UNREACHABLE` now
takes the ones proposing a (type, assay) pair the house has never made, so the
two rows together are the whole lineage population and neither alone is it.
Nothing was dropped: 67,898 + 99,449 = 167,347 keys and `emitted rows` is
unchanged by the split.

THE LINEAGE CEILING IS 172,338 AND THE EMITTED MODE 2 IS SMALLER, by exactly the
precedence: the gate refuses 4,242 of those rows because a rejected claim names
the same pair, and Mode 1 takes 749 more because the sample is registered in
nothing and its own metadata proposes the assay. Both are counted by name; a
difference nobody names is how two readings of one number get published.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from . import _schema as S
from . import compatibility as CP
from . import gate as G
from . import lineage as L
from .audit import audit_contradictions, registered_internal

# --- what produced a proposal ------------------------------------------------
#
# A closed family that enumerates itself, the way `PROVENANCES` and
# `GATE_OUTCOMES` do: a consumer must be able to ask "is this one of the family"
# without restating the members, because a restatement is what drifts. (This
# sentence said "one of the four" until 2026-08-21, restating a count in the
# clause warning against restating it -- see below.)
#
# IT SAID "THREE" FOR ONE ROUND AFTER THE FOURTH MEMBER LANDED, one line above
# the tuple that already held four -- a restatement drifting from the thing it
# restates, in the block whose subject is that exact hazard. That is why the
# count is checked rather than written: `test_every_proposal_source_is_in_the_
# closed_family` derives the family from `vars()` and fails on a `BY_*` constant
# that never joins the tuple.
#
# IT THEN HAPPENED AGAIN, and the second time is the argument. `BY_CLAIM_NO_RULE`
# landed 2026-08-21 and the paragraph below still read "ALL FOUR" -- a prose
# count going stale twice in the one block that exists to warn about prose
# counts, because the test above derives the family and cannot see a comment. So
# the number is GONE rather than corrected to five: a restatement with no figure
# in it has nothing to drift.
#
# `FINDING_COLUMNS.proposed_by` is spelled `proposed_` and not `decided_` under
# the binding constraint, and these values inherit that: the column header is
# where a reader forms their belief about what the pipeline already did.
#
# EVERY MEMBER IS DECLARED HERE THOUGH MODE 1 EMITS ONLY THE FIRST. Tasks 6 and 8
# extend this module, and the alternative is each of them inventing its own
# spelling for one concept in one column -- two names one screen apart, which is
# this branch's signature defect. Declaring the family before its second producer
# exists is the same call `_schema` made for `MODE_3` and for
# `co_reg_registered_internal_assay_id`, and for the same reason: this is the
# cheapest it will ever be.
#
# `BY_CLAIM` HAS TWO PRODUCERS AND ONE MEANING, and the distinction matters
# because two MEANINGS under one name is what this family exists to stop. Mode 1
# and the compatibility lane both emit it, and on both the claim is the whole
# reason the row exists: without it there is no proposal, whereas a lineage row
# stands on the neighbour's registration with no claim at all. The
# co-registration band a compat row carries BANDS that proposal rather than
# making a second one, so it earns no member of its own.
BY_CLAIM = "BY_CLAIM"            # the gated vocabulary claim alone -- Mode 1,
                                 # and the compatibility lane
BY_PRECEDENT = "BY_PRECEDENT"    # stage B precedent on the hop alone
BY_BOTH = "BY_BOTH"              # precedent proposed, the claim disambiguated
# The neighbour's registration and NOTHING ELSE: a lineage absence on a hop with
# no precedent rule, so there is no measured rate behind the proposal at all.
#
# IT IS A FOURTH MEMBER AND NOT A WIDENING OF `BY_PRECEDENT`, which is defined
# three lines up as "stage B precedent on the hop alone" and would be a lie on
# these rows -- their own `evidence_summary` says "NO measured basis" and their
# `precedent_rate` is null. Two meanings under one name is the defect this branch
# has paid for five times, and it was shipped here for one review cycle: 10 rows
# of the real extract's 172,338 read `BY_PRECEDENT` while denying it.
BY_LINEAGE_ONLY = "BY_LINEAGE_ONLY"
# The fourth combination of (precedent rule, gated claim), which `mode2.
# _proposal_source` raised on until 2026-08-21. Its absence was a property of
# the 2026-08-17 extract and not of the logic, and the reachability rework moves
# exactly the populations that determine it. Named for what it IS -- a claim
# with no measured hop -- rather than widened out of `BY_BOTH`, which means
# "precedent proposed, the claim disambiguated" and would assert a rate that is
# not there.
BY_CLAIM_NO_RULE = "BY_CLAIM_NO_RULE"
PROPOSAL_SOURCES = (BY_CLAIM, BY_PRECEDENT, BY_BOTH, BY_LINEAGE_ONLY,
                    BY_CLAIM_NO_RULE)

# --- the joined frame every mode reads ---------------------------------------
#
# `CLAIM_COLUMNS` carries the tier and the contest flag; `GATE_COLUMNS` carries
# the outcome, the vocabulary evidence and the sample TYPE. Neither is sufficient
# on its own and every mode needs both, so the join is defined once here rather
# than three times in three modes.
#
# The claim's columns come FIRST and keep their own names, so this frame is the
# claims frame with evidence bolted behind it rather than a third vocabulary.
# `FINDING_COLUMNS` is where borrowed columns get prefixed with the frame they
# came from (`claim_tier`, `vocab_*`); an intermediate join that renamed them
# would put two names on one column between here and there.
ATTACHED_COLUMNS = S.CLAIM_COLUMNS + [
    c for c in G.GATE_COLUMNS if c not in S.CLAIM_COLUMNS
]

# The pair the two frames are joined on. Named, because `_SHARED_PAYLOAD` below
# is defined by subtracting it and `attach_gate` merges on it: three spellings of
# one list is how the payload check and the merge drift apart.
_MERGE_KEY = ["sample_id", "internal_assay_id"]

# The identity columns both frames carry, which the join CHECKS rather than
# assumes. They are not part of the key: a disagreement on them means the two
# frames describe different runs, and merging ON them would silently drop the
# disagreeing rows instead of reporting them.
#
# DERIVED FROM THE TWO CONTRACTS AND NEVER HAND-LISTED, because the change that
# breaks a hand-listed version is already scheduled. `gate.py:749-754`
# contemplates widening `GATE_COLUMNS` in increment 3. Should it gain a name
# `CLAIM_COLUMNS` already carries, the comprehension above emits that name ONCE,
# `merge` suffixes the gate's copy `_gate`, and `reindex` discards it -- so the
# CLAIM frame's value would win silently, with no payload check, for a column
# whose whole purpose is to prove the two frames describe one run. Derivation
# admits the new name to the check automatically, which is the only version of
# this that survives an edit made a task from here.
#
# `attach_gate` additionally reads the columns the FRAMES share, which is a
# superset when a caller hands in a pre-joined column, and
# `test_attach_gate_pins_both_of_the_contracts_it_computes` pins that on the
# declared frames the two agree and names today's four members.
_SHARED_PAYLOAD = sorted(
    (set(S.CLAIM_COLUMNS) & set(G.GATE_COLUMNS)) - set(_MERGE_KEY))

# Every key `mode1_census` returns, in report order, declared for the reason
# `CENSUS_KEYS`, `INTEGRITY_KEYS` and `CEILING_KEYS` are: the report prints them
# all, and a key that stops being produced must break rather than stop being
# printed.
#
# THREE IDENTITIES HOLD OVER THEM and a test asserts all three:
#
#     population      = population_no_claim + population_with_claim
#     population_with_claim
#                     = population_all_claims_blocked + population_proposed
#     claim_rows      = claim_rows_blocked + claim_rows_proposed
#
# The pre-gate keys are counted off the attached frame and the post-gate ones off
# the EMITTED findings, deliberately. Computing both sides from one frame would
# make the identities tautologies; this way a defect in `mode1_findings` breaks an
# identity rather than hiding inside it.
#
# `population_no_claim` is the largest slice by far -- 4,415 of the real 6,242 --
# and it exists because a mode reporting its coverage without it would quote the
# numerator as the population.
#
# EVERY KEY IS SCOPED TO MODE 1'S POPULATION, including the two `claim_rows`
# ones. A claim on a REGISTERED sample is Mode 2's or Mode 3's question and is
# counted nowhere here: `claim_rows` is 2,912 of the real extract's 138,007. The
# scope is in the name of the frame rather than of the key, so it is stated here
# once and `main` prints it under a header naming the mode.
MODE1_CENSUS_KEYS = (
    "population",
    "population_no_claim",
    "population_with_claim",
    "claim_rows",
    "claim_rows_blocked",
    "claim_rows_proposed",
    "population_all_claims_blocked",
    "population_proposed",
)


# --- indexes -----------------------------------------------------------------


def project_index(samples: pd.DataFrame) -> dict[int, str]:
    """sample_id -> its project ids, deduplicated, sorted, `;`-joined.

    THE VALUE IS A SET AND THE COLUMN IS NOW NAMED FOR ONE.
    `FINDING_COLUMNS` spelled this `project_id` until 2026-08-17; it is
    `project_ids`, renamed on the measurement this function's first run produced.
    Over Mode 1's real population, 1,052 of the 6,242 samples carry more than one
    project id, 34 carry the same id twice (the raw `GROUP_CONCAT` spells it
    `2,2`), and 193 carry none. The proposed assay's project would not have
    rescued the singular either -- 75 of the 137 internal assay ids the assays
    frame carries span more than one project, up to seven -- so there is no
    single-valued project anywhere on the row, from either side of it. (137 and
    not 154: see `mode3_findings`, which measures both and says which is which.)

    THE DECISIVE HALF IS THE COLLISION. `RULE_KEY.project_id` is the ONE project
    a precedent rule is scoped to, and `ASSAY_COLUMNS.project_id` the ONE project
    an assay record belongs to; both are genuinely singular. Mode 2 keys on
    `RULE_KEY` and emits `FINDING_COLUMNS`, so under the old spelling one name
    would mean "exactly one project" in the key and "a `;`-joined set" in the
    row, in two frames one function holds open at once.
    `test_no_finding_column_collides_with_the_rule_key` fails on any recurrence
    rather than leaving it to a reader.

    Truncating to one project was the alternative and it is the expensive
    failure: a `;`-joined value reads as plural at a glance, while a silently
    dropped project reads as correct.

    `;`-joined and not `,`-joined, matching `registered_internal_assay_ids`: one
    join convention across the finding row, so a consumer splitting one column
    splits them all the same way.

    Sorted NUMERICALLY where the id is a number, so `10` sorts after `2`. A
    string sort would order the same set differently between two samples that
    hold it, and this is an artifact a curator diffs between runs.

    A null becomes the empty string and never `None`: the sample's projects were
    read and there are none, which is a different statement from "not measured".
    """
    out: dict[int, str] = {}
    for sid, raw in zip(samples.sample_id, samples.project_ids):
        if pd.isna(raw):
            out[int(sid)] = ""
            continue
        parts = {t.strip() for t in str(raw).split(",") if t.strip()}
        out[int(sid)] = ";".join(
            sorted(parts, key=lambda t: (0, int(t), "") if t.isdigit()
                   else (1, 0, t)))
    return out


def unregistered_samples(
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> list[int]:
    """Mode 1's population: the samples with NO membership row at all, sorted.

    THE SINGLE DEFINITION, and every consumer in this module takes it from here
    rather than re-deriving "registered in nothing" beside it. Two definitions of
    registered, one module apart, have already produced a wrong population figure
    and a wrong Mode 2 ceiling on this branch, so `mode1_findings` is handed this
    list instead of the membership frame and cannot disagree with it.

    Built on `audit.registered_internal`, which is the package's one crossing of
    the seek `assay_assets.assay_id` junction and which RAISES on a membership
    row naming an assay absent from the assays frame. Grouping the membership
    frame directly here would be a fourth grouping of it and would skip that
    check -- and a dropped registration makes a registered sample look
    unregistered, which lands it in exactly this list.

    A sample_id present in `membership` but absent from `samples` is registered
    and is therefore not in this list, whichever frame it came from. It is
    counted by name by `registered_samples_absent_from_samples`; 362 exist on the
    real extract.
    """
    registered = registered_internal(membership, assays)
    return sorted({int(s) for s in samples.sample_id} - set(registered))


def registered_samples_absent_from_samples(
    samples: pd.DataFrame,
    membership: pd.DataFrame,
) -> list[int]:
    """Registered sample_ids with no row in the samples frame, sorted.

    Nothing is dropped silently. These samples are registered, so they are not
    Mode 1's population under either definition, and they carry no metadata in
    this extract so they can raise no claim either. They are absent from every
    figure this module reports, and this is where that absence is counted.

    Measured on the real extract 2026-08-17: 362 sample_ids over 368 of the
    214,296 membership rows. The direction to watch is upward -- a sample
    appearing here rather than in `samples` can only ever REMOVE it from Mode 1's
    population, never add it -- so growth here quietly shrinks the mode.

    Shaped after `gate.untyped_registration_samples`, which reports the same
    class of exclusion for the reachability index.
    """
    known = {int(s) for s in samples.sample_id}
    return sorted({int(s) for s in membership.sample_id} - known)


# --- the joined frame --------------------------------------------------------


def attach_gate(claims: pd.DataFrame, gated: pd.DataFrame) -> pd.DataFrame:
    """Every claim beside its own gate outcome, on `ATTACHED_COLUMNS`.

    `gate_claims` returns one row per claim in the claims frame's own order, and
    `sample_claims` emits at most one row per (sample, assay), so the two frames
    are a bijection on `(sample_id, internal_assay_id)`. That pair is the key
    here rather than row POSITION: a positional zip is correct today and gives a
    populated, wrong row the first time a caller filters one frame and not the
    other, which is this package's signature failure mode.

    RAISES rather than returning a smaller frame when the two disagree, following
    `precedent.mine_precedent`, `audit.registered_internal` and
    `gate.gate_claims`. A silently unmatched claim vanishes from Modes 1 and 2
    with no count anywhere; an inner join is exactly the shape that does that.

    The shared identity columns are CHECKED rather than joined on. Merging on
    `raw_value` too would look stricter and would in fact drop the disagreeing
    rows instead of naming them. Which columns those are is DERIVED -- see
    `_SHARED_PAYLOAD` for the scheduled `GATE_COLUMNS` widening that a hand-
    listed version would let through as a silent claim-side win.

    Neither input frame is mutated.
    """
    key = _MERGE_KEY
    for name, frame in (("claims", claims), ("gate", gated)):
        dup = frame.duplicated(key)
        if dup.any():
            offenders = frame.loc[dup, key].head(5).to_dict("records")
            raise ValueError(
                f"the {name} frame carries {int(dup.sum())} duplicate "
                f"(sample_id, internal_assay_id) claim key(s), so the two "
                f"frames cannot be paired one to one: {offenders}. "
                "`sample_claims` emits at most one row per (sample, assay); a "
                "duplicate here means the frame was concatenated or re-gated."
            )

    def _keys(frame):
        return set(zip((int(s) for s in frame.sample_id),
                       (int(a) for a in frame.internal_assay_id)))

    ck, gk = _keys(claims), _keys(gated)
    if ck != gk:
        raise ValueError(
            f"the claims frame and the gate frame describe different claim "
            f"sets: {len(ck - gk)} claim(s) are gated by nothing and "
            f"{len(gk - ck)} gate outcome(s) name no claim. Examples: "
            f"{sorted(ck - gk)[:5]} / {sorted(gk - ck)[:5]}. Gate the frame you "
            "are about to classify; pairing a claim with another run's outcome "
            "is a populated, wrong row rather than an error."
        )

    out = claims.merge(gated, on=key, how="inner", suffixes=("", "_gate"))
    # Read off the FRAMES rather than off the contracts, so a caller handing in
    # a pre-joined column gets it checked too instead of having the claim side
    # win by `reindex`. On the declared frames this equals `_SHARED_PAYLOAD`,
    # which is pinned.
    for col in sorted((set(claims.columns) & set(gated.columns)) - set(key)):
        left = out[col].where(out[col].notna(), "").astype(str)
        right = out[col + "_gate"].where(
            out[col + "_gate"].notna(), "").astype(str)
        bad = left != right
        if bad.any():
            raise ValueError(
                f"{int(bad.sum())} claim(s) disagree with their gate row on "
                f"{col!r}, so the two frames describe different runs: "
                f"{out.loc[bad, key].head(5).to_dict('records')}."
            )
    return out.reindex(columns=ATTACHED_COLUMNS)


# --- Mode 1 ------------------------------------------------------------------


def _evidence_summary(c, stype: str) -> str:
    """The sentence an operator reads, carrying what the columns cannot.

    `FINDING_COLUMNS` borrows `vocab_support` and `vocab_purity` and NEITHER of
    the two numbers a Mode 1 row is judged on. The gate's support floor reads
    `vocab_n_samples` and never `vocab_support` -- `support` counts labelled
    EDGES and one sample fans out to many, so a row printing 2,210 edges beside a
    `GATE_LOW_SUPPORT` ruling decided on 1 sample shows a number the ruling never
    looked at. And `type_registrations` is the reachability evidence, which for
    Mode 1 is the only corroboration outside the vocabulary row itself: it says
    how many samples of this type are already registered in the assay being
    proposed. Both reach the operator here or nowhere.
    """
    parts = [
        "registered in no assay",
        f"{c.source_field} {c.raw_value!r} maps to {int(c.internal_assay_id)} "
        f"{c.internal_assay_title} ({c.tier}, {c.vocab_provenance}, "
        f"{int(c.vocab_n_samples)} backing sample(s) at purity "
        f"{float(c.vocab_purity):.3f})",
        f"{int(c.type_registrations)} {stype} sample(s) are already registered "
        f"in {int(c.internal_assay_id)}",
    ]
    if bool(c.contested):
        parts.append("contested: this sample's own metadata names more than "
                     "one assay, and every candidate is emitted")
    if c.gate != S.GATE_PASS:
        parts.append(f"{c.gate}: {c.gate_reason}")
    return "; ".join(parts)


def mode1_findings(
    attached: pd.DataFrame,
    population,
    projects: dict[int, str],
) -> pd.DataFrame:
    """One row per (unregistered sample, proposed assay). Nothing is decided.

    The population is `unregistered_samples`' output and is passed in rather than
    re-derived, so this function cannot hold a second opinion about which samples
    are registered.

    THE GATE RUNS FIRST and passage is `gate.reaches_modes`, read off
    `gate_failures`. A claim failing reachability or coherence reaches no row,
    whatever else it also failed; a claim under one of the two tuned floors
    reaches its row CARRYING that outcome in `gate`, because a threshold ranks
    and triages and does not grant permission.

    `gate` alone is lossless here, which is why `FINDING_COLUMNS` needs no
    `gate_failures`: a row that reaches a mode has no blocking failure, so its
    failure set is a subset of `{GATE_LOW_SUPPORT}` and the two columns carry the
    same fact. 3,511 claims on the real extract fail a blocking test AND a floor
    at once, and every one of them is blocked before it gets here.

    A CONTESTED SAMPLE IS NOT SUPPRESSED and every candidate it names is emitted,
    each carrying the tier its OWN evidence earned. `T_CONFLICT` is retired:
    collapsing a disagreeing sample to one tier made the Mode 3 audit non-monotone
    -- adding evidence removed 102 flags while adding 13 -- so the disagreement
    rides in the `contested` column. Mode 3 excludes contested rows because a flag
    accuses a curator of an error; Mode 1 proposes a FIRST assay for a sample that
    has none, so a second candidate is a choice for the operator to make rather
    than a reason to say nothing to them.

    WHAT THIS MODE DOES NOT ASSERT, and the nulls are the assertion. `lineage`,
    the co-registration block, `compat_band` and the precedent block are ALL
    null, not zero and not `LIN_NONE` / `BAND_NO_SUPPORT`. Mode 1 is settled
    before the lineage test under the precedence contract, and a co-registration
    rate is a statement about an ORDERED PAIR (a registered assay, the proposed
    one): a Mode 1 sample has no registered assay, so there is no pair and no
    population -- now or under any wider extract. `BAND_NO_SUPPORT` would say
    "measured, and the population was too small to read", which invites an
    operator to wait for more data that cannot exist.

    `classification` is null for the same reason. All four `CLASSES` describe
    what an absence MEANS for a sample that already holds something and all four
    are OUTPUTS of the two tests above; `CLS_UNRESOLVED` would read "neither test
    settles it" where neither test applies. That is a bucket named for what
    someone assumed was in it, which is the error this spec records three times.

    THE NULLS ARE ALSO WHAT KEEPS TASK 8 FREE, and that is the second reason to
    prefer them. An unrun test has to stay distinguishable from a test that ran
    and found nothing: a later pass that gathers lineage or co-registration
    evidence for these rows can FILL a null without contradicting anything this
    task shipped, whereas it would have to OVERWRITE a `LIN_NONE` -- and an
    overwrite of a published value is indistinguishable, in a diff a curator
    reads, from the pipeline changing its mind.

    `registered_internal_assay_ids` is the EMPTY STRING and not null, which is
    the opposite statement and the one Mode 1 is built on: the sample's
    registrations were measured and there are none.

    Sorted on `(sample_id, proposed_internal_assay_id)`, a total order on this
    output, because a curator diffs this artifact between runs and the claims
    frame arrives in whatever order the extractor wrote `samples.parquet`.
    """
    pop = {int(s) for s in population}
    reaching = attached[G.reaches_modes(attached)]

    rows = []
    for c in reaching.itertuples(index=False):
        sample_id = int(c.sample_id)
        if sample_id not in pop:
            continue
        stype = str(c.sample_type)
        rows.append({
            "sample_id": sample_id,
            "uuid": c.uuid,
            "sample_type": stype,
            "project_ids": projects.get(sample_id, ""),
            # measured, and empty. Never null: see the docstring.
            "registered_internal_assay_ids": "",
            "registered_internal_assay_titles": "",
            "proposed_internal_assay_id": int(c.internal_assay_id),
            "proposed_internal_assay_title": c.internal_assay_title,
            "mode": S.MODE_1,
            "classification": None,
            "gate": c.gate,
            "claim_tier": c.tier,
            "contested": bool(c.contested),
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "vocab_support": int(c.vocab_support),
            "vocab_purity": float(c.vocab_purity),
            "vocab_provenance": c.vocab_provenance,
            # MEASURED, and by the gate rather than by this mode: it is the
            # reachability cell the gate already ruled on, so leaving it null
            # would say a test that ran did not. It is Mode 1's only
            # corroboration outside the vocabulary row, and it reached the
            # operator only through `evidence_summary` until Mode 2 gave it a
            # column.
            "type_registrations": int(c.type_registrations),
            # the tests Mode 1 never ran
            "lineage": None,
            "lineage_neighbour_uuid": None,
            "lineage_n_supports": None,
            "co_reg_rate": None,
            "co_reg_pop": None,
            "co_reg_registered_internal_assay_id": None,
            "co_reg_alt_label_internal_assay_id": None,
            "co_reg_alt_label_pop": None,
            "compat_band": None,
            "precedent_rate": None,
            "precedent_direction": None,
            "precedent_n_both": None,
            "precedent_n_child_only": None,
            "precedent_n_parent_only": None,
            "proposed_by": BY_CLAIM,
            "evidence_summary": _evidence_summary(c, stype),
            "action": S.A_ADD_TO_ASSAY,
        })

    return pd.DataFrame(rows, columns=S.FINDING_COLUMNS).sort_values(
        ["sample_id", "proposed_internal_assay_id"], ignore_index=True,
    )


def mode1_census(
    attached: pd.DataFrame,
    population,
    findings: pd.DataFrame,
) -> dict[str, int]:
    """Where every sample in Mode 1's population went. See `MODE1_CENSUS_KEYS`.

    Nothing is dropped silently: a sample of the population either reaches a
    proposal, proposes nothing at all, or has every claim it makes blocked by the
    gate, and the three buckets sum to the population.

    The pre-gate counts come off `attached` and the post-gate ones off
    `findings`, so the identities are a cross-check between two computations
    rather than a restatement of one.
    """
    pop = {int(s) for s in population}
    pre = attached[attached.sample_id.map(lambda s: int(s) in pop)]
    with_claim = {int(s) for s in pre.sample_id}
    proposed = {int(s) for s in findings.sample_id}
    blocked = pre[~G.reaches_modes(pre)]
    return {
        "population": len(pop),
        "population_no_claim": len(pop - with_claim),
        "population_with_claim": len(with_claim),
        "claim_rows": len(pre),
        "claim_rows_blocked": len(blocked),
        "claim_rows_proposed": len(findings),
        "population_all_claims_blocked": len(with_claim - proposed),
        "population_proposed": len(proposed),
    }


# --- shared row helpers ------------------------------------------------------
#
# Read by Mode 2 (`mode2.py`) and by the compatibility lane below. It stayed
# in this module when Mode 2 moved out because two callers in two modules
# would otherwise each grow their own copy, and the two halves of one row
# falling out of step is the defect its docstring is about.

def _registered_columns(
    sample_id: int,
    registered: dict[int, set[int]],
    titles: dict[int, str],
) -> tuple[str, str]:
    """-> (`;`-joined internal assay ids, the same ids decoded, in position).

    Index i of one names index i of the other, which is the contract
    `AUDIT_COLUMNS` and `FINDING_COLUMNS` both state; building the two
    independently is what lets them fall out of step.

    Sorted ascending so a curator diffing this artifact between runs sees a
    change only where the data changed -- set iteration order is part of no
    contract. `;` and not `,`, matching every other joined column on the row.

    The EMPTY STRING when the sample is registered nowhere, never null: its
    registrations were read and there are none, which is the statement Mode 1's
    whole population rests on and which a null would retract.
    """
    ids = sorted(registered.get(sample_id, ()))
    return (";".join(str(i) for i in ids),
            ";".join(str(titles.get(i)) for i in ids))



# --- the precedence ----------------------------------------------------------
#
# THE CONTRACT, AS DATA. Six steps in one tuple, each with one test, walked in
# order. An `if` chain would encode the same order and could be reordered by a
# later edit with nothing failing, which is the exact hazard the brief for this
# task names; a declared tuple is something a test can permute and re-run.
#
# WHAT A STEP CLAIMS IS A KEY, AND A KEY IS AN ABSENCE. One (sample, proposed
# assay) pair the sample does not hold, raised either by a metadata claim or by
# a lineage neighbour or by both. Adding a sample to an assay is ONE membership
# write however many kinds of evidence argue for it, so exactly one step claims
# each key and exactly one row is emitted for it -- or none, where the step that
# claimed it emits nothing.
#
# MEASURED 2026-08-21 ON THE SAME EXTRACT, EACH ADJACENT SWAP, over the 175,339
# input keys. The four-swap table this comment carried before that date was
# measured over "180,995 input keys", a population no test on this branch has
# reproduced since; these five were re-derived by permuting `PRECEDENCE` over
# the real extract and are the values
# `test_the_real_extract_reproduces_the_precedence_split_and_mode_3s_emptiness`
# asserts.
#
#     GATE        <-> MODE 1          746 keys change step
#     MODE 1      <-> LINEAGE         749
#     LINEAGE     <-> UNREACHABLE  67,898
#     UNREACHABLE <-> COMPAT            0
#     COMPAT      <-> MODE 3            0
#
# The last is zero because `PRE_MODE_3` claims no key under ANY evidence, which
# `test_the_precedence_is_a_declared_order_and_three_of_its_four_swaps_move_a_key`
# proves exhaustively over all thirty-two evidence tuples rather than over one
# world. That is the finding increment 2 exists to report.
#
# THE THIRD SWAP IS THE SIZE OF THIS REWORK. Putting `PRE_UNREACHABLE` before
# `PRE_LINEAGE` moves 67,898 keys -- every REACHABLE lineage key -- because its
# test is `e.lineage` alone and relies on `PRE_LINEAGE` having taken them
# already. That is the cascade rule working as designed and is why neither test
# restates the other's condition.
#
# THE FOURTH IS ZERO STRUCTURALLY AND THAT IS WHY STEP 4 SITS HERE. It could
# only move a key whose claim PASSED the gate on a pair this step calls
# unreachable, and `gate.gate_claims` blocks a claim on `registrations == 0`
# outright, so `PRE_GATE` claims such a key three steps earlier. The real
# extract test asserts the combination is absent directly rather than inferring
# it from this zero.
PRE_GATE = "PRE_GATE"          # a rejected claim reaches no mode, ever
PRE_MODE_1 = "PRE_MODE_1"      # the sample is registered in NOTHING
PRE_LINEAGE = "PRE_LINEAGE"    # a lineage neighbour carries the assay
PRE_UNREACHABLE = "PRE_UNREACHABLE"   # a neighbour carries it, but no sample of
                                      # this type ever has
PRE_COMPAT = "PRE_COMPAT"      # neither, so the co-registration test rules
PRE_MODE_3 = "PRE_MODE_3"      # the residue, and there is none
PRECEDENCE = (PRE_GATE, PRE_MODE_1, PRE_LINEAGE, PRE_UNREACHABLE, PRE_COMPAT,
              PRE_MODE_3)

# The steps that claim a key and emit NO row, DECLARED rather than implied.
#
# THIS TUPLE EXISTS BECAUSE `unify_findings` DERIVED ITS OWN EXPECTATION FROM
# `lanes`, WHICH MADE AN OMITTED LANE UNDETECTABLE. `expected` read
# `{k for k, step in steps.items() if step in lanes}`, so a step MISSING from
# `lanes` was excluded from the very check that should have failed on it. Run on
# the fixture world with `PRE_COMPAT` left out: no raise, 8 rows silently became
# 4, and the census reported `keys_compat: 4` beside `rows: 4`. The `unknown`
# guard one screen down catches only the TYPO case, which produces an EXTRA key;
# the OMISSION case produces only a missing one and passed. That is exactly the
# hazard `unify_findings`' own docstring names -- "a missing mode looks exactly
# like a mode that found nothing" -- and Task 9 re-assembles `lanes`, so it is
# the next consumer's footgun rather than a hypothetical.
#
# `PRE_MODE_3` IS DELIBERATELY NOT IN HERE. Mode 3 HAS a lane and that lane is
# empty, which is a different statement from "this step emits nothing by
# design": the empty frame is how the report names the mode in order to say it
# found nothing. So a key ever reaching `PRE_MODE_3` with no lane, or with a
# lane that does not carry it, now FAILS -- which is right, because such a key
# would be a proposal in no artifact at all.
NON_EMITTING_STEPS = (PRE_GATE,)

class Evidence(NamedTuple):
    """What is known about ONE absence key, and nothing else.

    FIVE BOOLEANS AND NOT THE ROW THEY CAME FROM, deliberately. The precedence
    is a statement about which EVIDENCE outranks which, and handing it a frame
    row would let a later edit reach past the evidence into the claim's tier,
    its vocabulary support or its co-registration rate -- every one of which is
    a tuned number, and none of which may decide whether a proposal is made.
    With five booleans there is nothing in scope to gate on.

    `reachable` IS A BOOLEAN AND NOT THE CELL COUNT, on that same rule. The
    reachability evidence is a distinct-sample count and a threshold on it would
    be a tuned number; the only question the precedence may ask is the one
    `gate.gate_claims` already asks of a claim -- has the house EVER made this
    (type, assay) registration -- so only the answer crosses this boundary.

    A NAMEDTUPLE AND NOT A 5-TUPLE, for the reason `compatibility.CoRegistration`
    and `mode2.Rule` give: all five fields are `bool` and any two of them
    transpose silently. `claim` and `claim_reaches` are one word apart and mean
    "a claim names this pair" against "...and the gate did not reject it", which
    is the distinction the whole first step is about.

    `claim_reaches` implies `claim`: a claim cannot pass a gate it never met.
    `precedence_step` checks that rather than assuming it, because the
    combination is constructible by hand and would otherwise route a key with no
    claim at all through `PRE_COMPAT`.
    """
    claim: bool             # a metadata claim names this (sample, assay)
    claim_reaches: bool     # ...and `gate.reaches_modes` is true for it
    unregistered: bool      # the sample is registered in NO assay at all
    lineage: bool           # a lineage neighbour registers this assay
    reachable: bool         # a sample of this TYPE is registered in this assay
                            # SOMEWHERE -- or no type could be resolved, which is
                            # not the same as a measured zero and does not block


# ONE TEST PER STEP, and the dict is what makes the tuple above load-bearing:
# `precedence_step` walks `PRECEDENCE` and looks each step up here, so permuting
# the tuple permutes the contract and nothing else has to change.
#
# READ THEM AS A CASCADE. Every test after the first assumes the earlier ones
# declined, which is why `PRE_MODE_1` does not re-check `claim_reaches`,
# `PRE_UNREACHABLE` does not re-check `not e.reachable`, and `PRE_COMPAT` does
# not re-check `lineage`. That is not an oversight to tidy up: a test that
# restates its predecessor's condition makes the ORDER unobservable, and an
# order no test can distinguish from its reverse is a comment. Measured,
# re-checking `claim_reaches` in `PRE_MODE_1` alone would make the first swap
# move 0 keys instead of 746, and adding `not e.reachable` to `PRE_UNREACHABLE`
# would make the LINEAGE <-> UNREACHABLE swap move 0 instead of the count below.
_PRECEDENCE_TESTS = {
    # 1. the vocabulary gate. A rejected claim is not evidence, and the key it
    #    named is refused OUTRIGHT rather than falling through to the neighbour
    #    that also names it. That is the third design error, reversed: 24 A.FLOW
    #    and A.SPC flags whose data parent registers the MEASUREMENT assay their
    #    analysis child claims were filed `ABSENCE_LINEAGE` and routed to Mode 2
    #    as write candidates, because lineage fired first and nothing tested the
    #    term. All 24 are lineage candidates, so the gate is the only step that
    #    can stop them.
    PRE_GATE: lambda e: e.claim and not e.claim_reaches,
    # 2. Mode 1. Registered in nothing, so there is no registration to reason
    #    from and metadata is the only evidence there is.
    PRE_MODE_1: lambda e: e.claim and e.unregistered,
    # 3. lineage. A neighbour holds it AND the house has made this (type, assay)
    #    registration before. The second half is new: `gate.
    #    type_registration_index` calls a pair absent from it "INCREDIBLE
    #    whatever the term's support" and BLOCKS a claim on it, and until
    #    2026-08-21 this lane never met that rule.
    PRE_LINEAGE: lambda e: e.lineage and e.reachable,
    # 4. a neighbour holds it and NO sample of this type ever has. Its own step
    #    and its own lane: the row is still emitted, carrying GATE_UNREACHABLE,
    #    so a curator can override it. Dropping it here would delete 99,449
    #    proposals with nothing in any artifact saying they existed.
    PRE_UNREACHABLE: lambda e: e.lineage,
    # 5. co-registration. A claim on a registered sample with no neighbour: the
    #    only test left asks whether this TYPE routinely holds both assays.
    PRE_COMPAT: lambda e: e.claim,
    # 6. Mode 3, which claims nothing. NOT `True` with an empty emitter: a step
    #    that swallowed the residue would make every later reader's "Mode 3
    #    found nothing" mean "Mode 3 was handed nothing", and undetected is a
    #    different and worse finding than small.
    PRE_MODE_3: lambda e: False,
}


def precedence_step(evidence: Evidence, order=PRECEDENCE) -> str:
    """Which step claims this key. One of `PRECEDENCE`.

    `order` is a parameter so a test can permute the contract and measure what
    moves; nothing in this module ever passes it. A default that a caller may
    override is the cheapest way to make an ordering testable without the test
    having to reimplement the cascade -- which is how a mutation harness ends up
    proving that its own copy of the rule works.

    RAISES when no step claims the key, which means the key carries no evidence
    at all and was never an absence. `absence_keys` cannot build such a key, so
    this fires only on one assembled by hand.
    """
    if evidence.claim_reaches and not evidence.claim:
        raise ValueError(
            f"{evidence} says a claim passed the gate while no claim names the "
            "pair. `claim_reaches` is a property OF the claim, so it cannot be "
            "true without it; a key built this way routes through PRE_COMPAT, "
            "which would band a co-registration rate for a proposal nothing "
            "made.")
    for step in order:
        if _PRECEDENCE_TESTS[step](evidence):
            return step
    raise ValueError(
        f"no step in {order} claims {evidence}. Every key carries a claim or a "
        "lineage neighbour by construction -- see `absence_keys` -- so this is "
        "a key assembled by hand out of an absence of evidence.")


def _reachable(sample_id, assay_id, type_reg, types, uuid_of) -> bool:
    """Is a sample of this TYPE registered in this assay anywhere?

    THREE STATES COLLAPSED TO TWO, AND THE DIRECTION IS DELIBERATE. A missing
    (type, assay) CELL is a measured zero -- `type_registration_index` holds a
    cell for every pair that occurs. A missing TYPE is not measured at all, and
    that answer is True: the gate refuses to assert what was not established,
    which is the same direction `audit.audit_contradictions` refuses a
    contradiction it cannot resolve.

    THE SAME DERIVATION `mode2.mode2_findings` RUNS FOR `type_registrations`,
    over the same two indexes, which is why both are handed the caller's own
    objects rather than building their own: the precedence deciding a key is
    unreachable while the row it emits reads a positive cell would be one world
    described twice.
    """
    stype = types.get(uuid_of.get(sample_id))
    if stype is None:
        return True
    return type_reg.get((stype, assay_id), 0) > 0


def absence_keys(
    attached: pd.DataFrame,
    *,
    population,
    registered: dict[int, set[int]],
    candidates,
    type_reg: dict[tuple[str, int], int],
    types: dict[str, str],
    uuid_of: dict[int, str],
) -> dict[tuple[int, int], Evidence]:
    """THE INPUT. Every (sample, proposed assay) absence, with its evidence.

    A key is here when the sample is NOT registered in the assay AND either a
    metadata claim names the pair or a lineage neighbour registers it. The union
    is the point: 166,427 of the real extract's 180,995 keys carry no claim and
    8,657 carry no neighbour, so neither source alone is the population and
    quoting either as the input understates the pass by more than an order of
    magnitude in one direction or 20x in the other.

    A CLAIM NAMING AN ASSAY THE SAMPLE ALREADY HOLDS RAISES NO KEY. There is no
    absence, so there is nothing to propose -- and it is the largest single
    exclusion in stage C by far: 123,439 of the 138,007 attached claims, 89% of
    them. `claims_agreeing_with_a_registration` names every one rather than
    leaving a reader to subtract, because the direction of that number is
    dangerous: it grows whenever a curator registers something, and every one it
    gains is a key this pass stops raising.

    A BLOCKED CLAIM STILL RAISES ITS KEY, and that is what makes the gate a STEP
    rather than a filter. Dropping it here would leave the key to the lineage
    neighbour that also names it -- which is the third design error exactly --
    and would leave 4,567 refusals uncounted. `precedence_step` refuses them
    visibly instead, and `findings_census` reports the count.

    "Registered" is ANY membership row, through `audit.registered_internal`,
    which is also where `population` comes from. The MAPPABLE-only reading is 82
    samples adrift and has produced a wrong Mode 1 population and a wrong Mode 2
    ceiling on this branch already.

    `population` and `candidates` are PASSED IN rather than re-derived, for the
    reason `mode1_findings` takes its population: a second opinion here about
    which samples are registered, or about which pairs a neighbour offers, would
    put the precedence and the lanes on two different worlds.

    `type_reg`, `types` and `uuid_of` ARE PASSED IN ON THAT SAME RULE, and it
    binds harder here than anywhere else in the function. They are the three
    objects `gate.gate_claims` and `mode2.mode2_findings` already hold --
    `gate.type_registration_index`, `gate.sample_type_index` and
    `lineage.lineage_index`'s uuid map -- and `_reachable` reads them to decide
    whether a lineage key is claimed by `PRE_LINEAGE` or by `PRE_UNREACHABLE`.
    A second opinion here about which pairs are reachable would put the
    PRECEDENCE and the GATE on two different worlds: a key the precedence sent
    down the ordinary lineage lane while the gate would have blocked the same
    pair as a claim is exactly the disagreement this step exists to end. Note
    `types` is keyed on UUID and not on `sample_id` -- see `gate.sample_type_index`,
    where 86 sample_ids carry two node rows and 51 of those disagree on type --
    so `uuid_of` is the third argument rather than a convenience.
    """
    pop = {int(s) for s in population}
    out: dict[tuple[int, int], Evidence] = {}

    for row, reaches in zip(attached.itertuples(index=False),
                            G.reaches_modes(attached)):
        sample_id, assay_id = int(row.sample_id), int(row.internal_assay_id)
        if assay_id in registered.get(sample_id, ()):
            continue                      # an absence of nothing
        out[(sample_id, assay_id)] = Evidence(
            claim=True, claim_reaches=bool(reaches),
            unregistered=sample_id in pop, lineage=False,
            reachable=_reachable(sample_id, assay_id, type_reg, types, uuid_of))

    for pair in candidates:
        sample_id, assay_id = int(pair[0]), int(pair[1])
        was = out.get((sample_id, assay_id))
        out[(sample_id, assay_id)] = Evidence(
            claim=was.claim if was else False,
            claim_reaches=was.claim_reaches if was else False,
            unregistered=sample_id in pop, lineage=True,
            reachable=(was.reachable if was else
                       _reachable(sample_id, assay_id, type_reg, types,
                                  uuid_of)))
    return out


def precedence_steps(keys: dict[tuple[int, int], Evidence]) -> dict[tuple[int, int], str]:
    """Every input key beside the step that claims it. See `precedence_step`."""
    return {key: precedence_step(evidence) for key, evidence in keys.items()}


def claims_agreeing_with_a_registration(
    attached: pd.DataFrame,
    registered: dict[int, set[int]],
) -> list[tuple[int, int]]:
    """The (sample, assay) claims naming an assay the sample already holds, sorted.

    Nothing is dropped silently. These claims raise no absence key, propose
    nothing and appear in no finding row, and this is where that exclusion is
    counted -- BY NAME, following `registered_samples_absent_from_samples` and
    `gate.untyped_registration_samples`, because a list a reader can spot-check
    is a different artifact from a number they must take on trust.

    Measured on the real extract 2026-08-17: 123,439 of the 138,007 attached
    claims, which is 89.4% of them and the largest exclusion anywhere in stage C.
    The direction to watch is UPWARD: every claim that joins this list is a key
    this pass stops raising, so silent growth shrinks all three modes at once
    while looking exactly like a curator doing their job.

    Sorted, because a curator diffs this between runs and dict iteration order
    is part of no contract.
    """
    return sorted(
        (int(r.sample_id), int(r.internal_assay_id))
        for r in attached.itertuples(index=False)
        if int(r.internal_assay_id) in registered.get(int(r.sample_id), ())
    )


# --- the compatibility lane --------------------------------------------------
#
# THE FOURTH STEP, and the only one this task builds from scratch. A gated claim
# on a REGISTERED sample that no lineage neighbour corroborates: the sample holds
# something, so there is a pair to measure, and the question is whether samples
# of this type that hold R routinely hold X too.
#
# The three outcomes are `compatibility.BAND_ESTABLISHES` and this module does
# not re-derive them. Measured over the real extract's 6,932 such keys:
#
#     BAND_ROUTINE     744   CLS_ABSENCE_COMPAT   Mode 2 candidate, unproven
#     BAND_NEVER     5,181   CLS_ALT_LABEL        alternative labels, no action
#     BAND_SOMETIMES   962   CLS_UNRESOLVED       neither test settles it
#     BAND_NO_SUPPORT   45   CLS_UNRESOLVED       the population is unreadable
#
# TWO OF THE THREE CLASSES PROPOSE NOTHING, and their rows carry a null `mode`,
# `A_NONE` and a null `proposed_by`. They are still EMITTED: the alternative
# label is the operator's own second correction and the finding they asked for,
# and `CLS_UNRESOLVED` is reported at its own size because silently absorbing
# what the pipeline cannot classify is how a bucket ends up named for what
# someone assumed was in it.

# Which of `_schema.CLASSES` proposes a membership change and which does not, in
# one place. `mode` and `action` are two columns that must agree -- a row with a
# mode and `A_NONE` says both "Mode 2 proposes this" and "nothing is proposed"
# -- so they are derived from one dict rather than written twice.
CLASS_PROPOSAL = {
    S.CLS_ABSENCE_COMPAT: (S.MODE_2, S.A_ADD_TO_ASSAY),
    S.CLS_ALT_LABEL: (None, S.A_NONE),
    S.CLS_UNRESOLVED: (None, S.A_NONE),
}


def _compat_summary(c, stype, band, got, cls) -> str:
    """The sentence an operator reads, carrying what the columns cannot.

    Shaped after `_evidence_summary` and `mode2._mode2_summary`: it names the
    claim, the pair the rate was measured over, the population under it, and --
    where there is one -- the well-supported zero that argues against the
    proposal. It also says out loud that no lineage neighbour was found, because
    the null `lineage_neighbour_uuid` is otherwise indistinguishable, to a
    reader, from a test nobody ran.
    """
    parts = [
        f"{c.source_field} {c.raw_value!r} maps to {int(c.internal_assay_id)} "
        f"{c.internal_assay_title} ({c.tier}, {c.vocab_provenance}, "
        f"{int(c.vocab_n_samples)} backing sample(s) at purity "
        f"{float(c.vocab_purity):.3f})",
        "no lineage neighbour registers it, so the co-registration test is the "
        "only evidence left",
    ]
    if got.registered_assay_id is None:
        parts.append(
            f"no assay this sample holds reaches a measured population with "
            f"{int(c.internal_assay_id)} for {stype}, so nothing was measured "
            "-- that is absent evidence and not a rate of zero")
    else:
        parts.append(
            f"{got.rate:.3f} of the {got.support} {stype} sample(s) registered "
            f"in {got.registered_assay_id} also hold "
            f"{int(c.internal_assay_id)} ({band})")
    if got.alt_label_assay_id is not None:
        parts.append(
            f"COUNTER-EVIDENCE: {int(c.internal_assay_id)} never co-registers "
            f"with {got.alt_label_assay_id}, which this sample HOLDS, over "
            f"{got.alt_label_support} {stype} sample(s)")
    if bool(c.contested):
        parts.append("contested: this sample's own metadata names more than "
                     "one assay, and every candidate is emitted")
    if c.gate != S.GATE_PASS:
        parts.append(f"{c.gate}: {c.gate_reason}")
    mode, action = CLASS_PROPOSAL[cls]
    parts.append(
        f"proposes {action}; nothing is written and nothing is decided"
        if mode is not None else
        f"{cls}: no membership change is proposed and no mode claims this row")
    return "; ".join(parts)


def compat_findings(
    attached: pd.DataFrame,
    *,
    steps: dict[tuple[int, int], str],
    registered: dict[int, set[int]],
    table: dict[tuple[str, int, int], tuple[float, int]],
    titles: dict[int, str],
    projects: dict[int, str],
) -> pd.DataFrame:
    """One row per key the co-registration step claims. Nothing is decided.

    THE LANE TAKES ITS POPULATION FROM THE PRECEDENCE AND NEVER RE-DERIVES IT.
    `mode1_findings` and `mode2.mode2_findings` are CEILING emitters with their
    own tests and their own published figures, so they offer more keys than the
    precedence grants them and `unify_findings` filters both. This lane is new
    and has no such obligation, so it is built from `steps` directly -- which
    means the gate test, the Mode 1 test and the lineage test appear here
    exactly once each, inside `_PRECEDENCE_TESTS`, rather than being restated as
    three `if`s a later edit could disagree with.

    KEYWORD-ONLY, for the reason `mode2_findings` gives at eleven arguments:
    `titles` and `projects` are both `dict[int, str]` and `registered` is
    `dict[int, set[int]]`, so a positional call could transpose two of them and
    produce a populated, wrong frame with no error.

    `BAND_ESTABLISHES` OWNS THE MAPPING FROM BAND TO CLASS and `CLASS_PROPOSAL`
    owns the mapping from class to (mode, action). Neither is restated here:
    `BAND_NEVER -> CLS_ALT_LABEL` is the operator's second correction and
    `BAND_NO_SUPPORT -> CLS_UNRESOLVED` is the guard that stops a rate of 0.000
    over four samples being reported as "these never coexist".

    WHAT THIS LANE DOES NOT ASSERT, and the nulls are the assertion. The
    precedent block is NULL on every row and not zero: precedent is measured per
    HOP, this lane's keys have no neighbour and therefore no hop, so there is no
    rule to miss. `lineage` is `LIN_NONE` and NOT null, because the lineage test
    DID run and found nothing -- that distinction is the one Task 5's nulls were
    reserved for and it runs the other way here.

    EVERY ROW HAS A TYPE, AND THAT IS A GUARD RATHER THAN A BRANCH.
    `mode2.mode2_findings` handles a typeless sample because its rows come from
    the lineage traversal, where a candidate need not carry a claim; these rows
    come from `attached`, and `gate.gate_claims` indexes `types[str(c.uuid)]`
    and raises `KeyError` on a claim whose uuid has no node row. So the type is
    total on this frame by construction, and the assertion says so rather than a
    null-handling branch saying it might not be -- a branch no data can enter is
    indistinguishable, to a reader, from one that is merely rare.

    Sorted on `(sample_id, proposed_internal_assay_id)`, a total order here.
    """
    rows = []
    for c in attached.itertuples(index=False):
        sample_id, assay_id = int(c.sample_id), int(c.internal_assay_id)
        if steps.get((sample_id, assay_id)) != PRE_COMPAT:
            continue
        have = registered.get(sample_id, set())
        assert pd.notna(c.sample_type), (
            f"({sample_id}, {assay_id}) reached the compatibility lane with no "
            "sample type; `gate_claims` raises on a claim whose uuid has no "
            "node row, so this frame did not come from it")
        stype = str(c.sample_type)
        got = CP.best_co_registration(stype, have, assay_id, table)
        band = CP.compat_band(got.rate, got.support)
        cls = CP.band_establishes(band)
        mode, action = CLASS_PROPOSAL[cls]
        reg_ids, reg_titles = _registered_columns(sample_id, registered, titles)
        rows.append({
            "sample_id": sample_id,
            "uuid": c.uuid,
            "sample_type": stype,
            # "" and not null: a claim comes off this sample's own metadata, so
            # it HAS a `samples` row and its projects were read
            "project_ids": projects.get(sample_id, ""),
            "registered_internal_assay_ids": reg_ids,
            "registered_internal_assay_titles": reg_titles,
            "proposed_internal_assay_id": assay_id,
            "proposed_internal_assay_title": titles.get(assay_id),
            "mode": mode,
            "classification": cls,
            "gate": c.gate,
            "claim_tier": c.tier,
            "contested": bool(c.contested),
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "vocab_support": int(c.vocab_support),
            "vocab_purity": float(c.vocab_purity),
            "vocab_provenance": c.vocab_provenance,
            "type_registrations": int(c.type_registrations),
            # the lineage test RAN and found nothing, which is not a null
            "lineage": S.LIN_NONE,
            "lineage_neighbour_uuid": None,
            "lineage_n_supports": 0,
            # NULL, NOT 0.0, WHERE NOTHING REACHED A POPULATION.
            # `best_co_registration` returns `(0.0, 0, None, None, 0)` when no
            # assay this sample holds reaches a key at all, and writing that
            # 0.0 into an operator-facing column would state a MEASURED rate of
            # zero -- "these never coexist" -- on the one row whose own
            # `evidence_summary` says "that is absent evidence and not a rate
            # of zero". `co_reg_pop` stays 0 beside it and is not null: the
            # population WAS read and it is empty, which is what makes
            # `compat_band` read `BAND_NO_SUPPORT` rather than `BAND_NEVER`.
            # 0 of the 6,932 compatibility rows on the real extract, and Task 8
            # is the first code to write these columns into an artifact, which
            # is what newly exposes it.
            "co_reg_rate": None if got.registered_assay_id is None else got.rate,
            "co_reg_pop": got.support,
            "co_reg_registered_internal_assay_id": got.registered_assay_id,
            "co_reg_alt_label_internal_assay_id": got.alt_label_assay_id,
            "co_reg_alt_label_pop": got.alt_label_support,
            "compat_band": band,
            # no neighbour means no hop, and precedent is measured per hop
            "precedent_rate": None,
            "precedent_direction": None,
            "precedent_n_both": None,
            "precedent_n_child_only": None,
            "precedent_n_parent_only": None,
            # null where nothing is proposed: a proposal source on a row that
            # proposes nothing names the author of a change no one suggested
            "proposed_by": BY_CLAIM if mode is not None else None,
            "evidence_summary": _compat_summary(c, stype, band, got, cls),
            "action": action,
        })

    return pd.DataFrame(rows, columns=S.FINDING_COLUMNS).sort_values(
        ["sample_id", "proposed_internal_assay_id"], ignore_index=True,
    )


# --- Mode 3, by subtraction --------------------------------------------------


def mode3_findings() -> pd.DataFrame:
    """Mode 3's rows. There are none, and there is no detector to produce any.

    NOT SMALL. UNDETECTED. The operator's Mode 3 is "what samples have INCORRECT
    assays". The detector built for it in increment 1 tests
    `claimed_assay not in registered_assays`, which is an ABSENCE test reported
    under a contradiction's name, and measurement has now twice shown its output
    is not contradictions:

      * the operator's first correction -- a PAV sample that had tissue
        collected from it belongs in 56 Patient Visit AND 74 Tissue Collection,
        one incoming and one outgoing, so the absence of the second is a
        MISSING REGISTRATION. 86 of those 97 PAV samples have a TIS child
        already registered in 74, on a hop running 0.931 in project 2;
      * the operator's second correction -- of the 51 flags that survived, 45
        name CORRECT assays under a different label. D.IMG images sit in 127
        Tissue Imaging or in 145 Histopathology and never in both, because a
        curator picks one, and 145 D.IMG samples are registered in
        Histopathology. The remaining 6 are vocabulary defects.

    Re-disposed under this precedence, all 866 land elsewhere: 43 gate rejects,
    326 lineage absences, 247 routinely-coexisting pairs, 205 unresolved, 45
    alternative labels. The residue of the subtraction is EMPTY.

    So metadata disagreeing with a registration is not evidence that the
    registration is wrong, and this mode reports and proposes nothing until a
    detector that does not depend on the vocabulary is built and validated.
    Candidates, all measurable today and none built: registration-side
    reachability (a sample registered in an assay its own type is otherwise
    never registered in, the mirror of the claim-side gate and needing no
    metadata at all); cross-project registration; and a removal lane, which
    ships last and separately because of the deletion hazard.

    THE CROSS-PROJECT FIGURE NEEDS ITS CONSTRUCTION STATED AND ONE HALF OF IT IS
    CORRECTED HERE. Measured 2026-08-18 over the real extract, taking the
    project of the SEEK ASSAY RECORD the membership row names -- which is
    single-valued -- against the sample's own `project_ids`: 1,340 of the
    214,296 membership rows, reproducing the spec exactly. Taking instead the
    project set of the INTERNAL assay, which unions every seek record sharing
    that internal id, the same rule reads 924. Two constructions, two answers,
    and the spec states neither.

    THE DENOMINATOR OF THE MULTI-PROJECT SHARE HAS TO SAY WHICH SET IT COUNTS,
    and this package had been quoting it without one. Measured 2026-08-18 over
    `assays.parquet`: 458 assay records carry 137 distinct non-null
    `internal_assay_id`s and 17 records carry none, so `precedent.assay_index`'s
    map holds 154 ids -- the 137 plus one fallback per junction-less record.
    **75 of the 137 GENUINE ids span more than one project, up to seven.**
    Pairing 75 with 154 is arithmetically true and misleading: not one of the 17
    fallback ids can span a project, since each stands for exactly one record,
    so all 75 come out of the 137 and 154 is the wrong denominator for THIS
    numerator.

    WHICH DENOMINATOR IS RIGHT DEPENDS ON THE NUMERATOR BESIDE IT, and the first
    version of this paragraph got that wrong in the act of correcting it. It
    said the pairing "appears in `mode2.registration_projects` and
    `mode2.assay_titles`, where 154 IS the right denominator". Measured:
    `assay_titles` does NOT carry the pairing -- its 154 sits beside a different
    numerator, "0 internal ids resolve to two distinct titles", where 154 is
    exactly right because that sentence counts what the MAP resolves.
    `registration_projects` DID carry it verbatim, with this numerator, and is
    corrected rather than blessed. So: 137 wherever the numerator is 75, and 154
    wherever the sentence is about the map -- `assay_titles`, `audit`'s title
    index, and `VOCAB_COLUMNS`.

    Every site is swept and the figures are PINNED, by
    `test_the_multi_project_share_is_measured_and_its_denominator_is_the_same_everywhere`,
    which re-derives all six numbers from the parquet and then reads every
    surviving sentence out of the source. Nothing here was pinned by any test
    before that, which is the same gap the R2 mutation exposed for the module
    docstring's swap counts, closed the same way.

    The spec's companion figure reads "plus 271 samples with no project at
    all". 271 is the ROW count; the SAMPLE count is 242. A unit stated wrongly
    beside a number measured rightly is this project's signature defect, and
    both figures are quoted here with their unit because the detector that would
    use them is not built.

    THE FRAME IS EMPTY AND CARRIES THE FULL CONTRACT. A mode absent from the
    artifact reads as a mode nobody ran, and Task 9's report has to name it in
    order to say it found nothing. It takes no argument, because a parameter it
    ignored would suggest a subtraction happening inside it: the subtraction is
    `PRECEDENCE`, and `PRE_MODE_3` sits at the end of it claiming no key.
    """
    return pd.DataFrame(columns=S.FINDING_COLUMNS)


# --- the unified pass --------------------------------------------------------


def unify_findings(
    steps: dict[tuple[int, int], str],
    lanes: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Every mode's rows in one frame, one row per proposal. `findings.csv`.

    `lanes` maps a step of `PRECEDENCE` to the frame that emits its rows, and
    the precedence is what resolves a key two lanes both offer. On the real
    extract that is 753 keys wanted by Mode 1 and by the lineage lane at once --
    a sample registered in nothing whose own metadata names an assay a neighbour
    also holds -- and adding it to that assay is ONE membership write, so one row
    is emitted and the loser is counted rather than silently absent.

    THE PARTITION IS ASSERTED AND NOT ASSUMED. Every key whose step has a lane
    appears exactly once; every key whose step has none appears zero times; and
    no (sample, assay) pair appears twice. A curator approves this file row by
    row, so a duplicate proposal is a duplicate write.

    RAISES BOTH WAYS on a `lanes` that does not match the contract, and the two
    directions are different bugs. A key that is not a step is a TYPO and
    produces an extra entry; a step the precedence granted keys to and `lanes`
    omits produces only a MISSING one, and the second is the one that bites --
    it drops every row that step claimed while the census beside it reads like a
    mode that found nothing. `NON_EMITTING_STEPS` is what makes the second
    checkable, and `expected` below is derived from it rather than from `lanes`,
    which is how the omission got through in the first place.

    ONE FRAME MAY APPEAR UNDER TWO STEPS, and the lineage frame does: it is
    handed in at both `PRE_LINEAGE` and `PRE_UNREACHABLE` because one lane
    generates both populations and the precedence, not the generator, decides
    which key is which. Each pass keeps only the rows the step below OWNS, so
    the pair partitions the frame rather than duplicating it -- and the
    duplicate-pair assertion below is what proves that rather than assuming it.

    Emitted in `PRECEDENCE` order and then SORTED on
    `(sample_id, proposed_internal_assay_id)`, a total order on this output. The
    lanes each sort themselves and their concatenation does not, so the sort has
    work to do.
    """
    unknown = sorted(set(lanes) - set(PRECEDENCE))
    if unknown:
        raise ValueError(
            f"{unknown} is not in PRECEDENCE {PRECEDENCE}. `lanes` is keyed on "
            "the step whose rows each frame emits; a key that is not a step "
            "silently drops a whole mode, which reads exactly like a mode that "
            "found nothing.")
    # ...and the MIRROR of that check, which is the one that actually bites. A
    # typo produces an extra key and is caught above; an OMISSION produces only
    # a missing one, and until this guard existed it passed -- 8 rows became 4
    # on the fixture world with `PRE_COMPAT` left out, silently.
    absent = sorted({step for step in steps.values()
                     if step not in lanes and step not in NON_EMITTING_STEPS})
    if absent:
        raise ValueError(
            f"the precedence granted {absent} at least one key and `lanes` "
            f"carries no frame for it. Every step is either emitting -- and "
            f"must hand over a frame -- or declared in NON_EMITTING_STEPS "
            f"{NON_EMITTING_STEPS}. A step omitted from `lanes` drops every row "
            "it claimed and reads, in the census beside it, exactly like a mode "
            "that found nothing.")

    kept = []
    for step in PRECEDENCE:
        frame = lanes.get(step)
        if frame is None:
            continue
        owned = [steps.get((int(s), int(a))) == step
                 for s, a in zip(frame.sample_id,
                                 frame.proposed_internal_assay_id)]
        kept.append(frame[owned])

    out = (pd.concat(kept, ignore_index=True) if kept
           else pd.DataFrame(columns=S.FINDING_COLUMNS))
    out = out.reindex(columns=S.FINDING_COLUMNS).sort_values(
        ["sample_id", "proposed_internal_assay_id"], ignore_index=True)

    emitted = list(zip((int(s) for s in out.sample_id),
                       (int(a) for a in out.proposed_internal_assay_id)))
    assert len(emitted) == len(set(emitted)), (
        "the unified frame carries a (sample, assay) pair twice, so one "
        "membership write would be proposed to the operator as two rows")
    # DERIVED FROM THE CONTRACT AND NEVER FROM `lanes`: see NON_EMITTING_STEPS.
    # `if step in lanes` excused the caller's own omission from the check.
    expected = {k for k, step in steps.items()
                if step not in NON_EMITTING_STEPS}
    assert set(emitted) == expected, (
        f"{len(expected - set(emitted))} key(s) the precedence granted a lane "
        f"reach no row and {len(set(emitted) - expected)} row(s) belong to no "
        "key: the lanes and the precedence disagree about the population")
    return out


# Every key `findings_census` returns, in report order, declared for the reason
# `MODE1_CENSUS_KEYS`, `mode2.MODE2_CENSUS_KEYS` and `lineage.CEILING_KEYS` are:
# the report prints them all, and a key that stops being produced must break
# rather than stop being printed.
#
# FOUR IDENTITIES HOLD OVER THEM and a test asserts all four:
#
#     input_keys  = keys_refused_by_the_gate + keys_mode_1 + keys_lineage
#                   + keys_unreachable + keys_compat + keys_mode_3
#     rows        = input_keys - the keys claimed by NON_EMITTING_STEPS
#     rows        = rows_mode_1 + rows_mode_2 + rows_mode_3 + rows_no_mode
#     rows        = the five rows_cls_* + rows_without_a_classification
#
# `keys_unreachable` AND `rows_cls_unreachable` ARE NOT A NEW POPULATION. They
# are a cut through the one `keys_lineage` used to hold whole: the lineage lane
# offers a pair no sample of the type is registered in anywhere, which
# `gate.type_registration_index` calls incredible and `gate.gate_claims` already
# blocks a CLAIM on. Before 2026-08-21 nothing tested it here, so
# `keys_unreachable + keys_lineage` equals the old `keys_lineage` exactly, and
# the rows are RECLASSIFIED rather than removed -- `rows` does not move.
# `PRE_UNREACHABLE` is deliberately NOT in `NON_EMITTING_STEPS`: it has a lane
# and it emits, so the second identity keeps subtracting `PRE_GATE` alone.
#
# THE SECOND IDENTITY SUBTRACTS `NON_EMITTING_STEPS` AND NOTHING ELSE, and this
# comment said "`input_keys - keys_refused_by_the_gate - keys_mode_3`" and "the
# two are equal only because `PRE_GATE` and `PRE_MODE_3` emit nothing" for one
# round after that tuple was declared -- eighteen lines above a runtime
# assertion that subtracts `PRE_GATE` alone and would FAIL on the world this
# comment described. `PRE_MODE_3` is NOT non-emitting: Mode 3 has a lane and it
# is empty, so a key ever reaching it must produce a row or `unify_findings`
# raises. The arithmetic agrees today only because `keys_mode_3` is 0, which is
# exactly the coincidence that lets a wrong contract read as right.
#
# So the identity is stated in terms of the tuple, `findings_census` derives the
# subtrahend from the tuple, and neither can drift from it.
#
# THE UNIT IS A KEY ABOVE AND A ROW BELOW, and the two differ by exactly those
# claimed keys. The prefixes carry it: `keys_*` counts what the precedence ruled
# on and `rows_*` counts what reached the operator, and quoting one for the
# other is this project's signature defect.
#
# `rows_mode_2` IS NOT THE LINEAGE CEILING and the three `lineage_*` keys are
# why. Re-measured 2026-08-21: the lane offers 172,338; the gate refuses 4,242
# and Mode 1 takes 749, leaving 167,347 lineage rows -- 67,898 at `PRE_LINEAGE`
# and 99,449 at `PRE_UNREACHABLE` -- which with 107 compatibility rows make
# 167,454. Every one of those numbers is a key here, because a difference nobody
# names is how two readings of one number get published -- which has happened on
# this branch.
#
# `keys_lineage` NO LONGER DENOTES THE WHOLE LINEAGE POPULATION and the name did
# not change, which is the trap this comment exists to spring. It is the
# REACHABLE half; `keys_unreachable` is the other. Any sentence that used to
# subtract `keys_lineage` from the ceiling must now subtract both, and
# `test_mode_1_takes_a_key_a_lineage_neighbour_also_offers_and_the_refusal_is_counted`
# asserts that four-term identity so the omission breaks rather than reads.
FINDINGS_CENSUS_KEYS = (
    "input_keys",
    "keys_from_a_claim",
    "keys_from_lineage",
    "claims_agreeing_with_a_registration",
    "keys_refused_by_the_gate",
    "keys_mode_1",
    "keys_lineage",
    "keys_unreachable",
    "keys_compat",
    "keys_mode_3",
    "rows",
    "rows_mode_1",
    "rows_mode_2",
    "rows_mode_3",
    "rows_no_mode",
    "rows_cls_absence_lineage",
    "rows_cls_absence_compat",
    "rows_cls_alt_label",
    "rows_cls_unresolved",
    "rows_cls_unreachable",
    "rows_without_a_classification",
    "lineage_ceiling_offered",
    "lineage_refused_by_the_gate",
    "lineage_taken_by_mode_1",
)


def findings_census(
    keys: dict[tuple[int, int], Evidence],
    steps: dict[tuple[int, int], str],
    findings: pd.DataFrame,
    lanes: dict[str, pd.DataFrame],
    *,
    agreeing,
) -> dict[str, int]:
    """Where every input key went and what every emitted row says. See the keys.

    The `keys_*` half is counted off the PRECEDENCE and the `rows_*` half off
    the EMITTED FRAME, deliberately and for the reason `mode1_census` splits its
    own two halves: computing both sides from one object would make the
    identities tautologies, and this way a defect in a lane breaks an identity
    rather than hiding inside it.

    `keys` AND `steps` are both taken, and neither is derived from the other
    here. `steps` says which step claimed each key and `keys` says what evidence
    it carried, and the second is not recoverable from the first: a
    `PRE_LINEAGE` key may or may not also carry a claim -- re-measured
    2026-08-21, 761 of the real extract's 67,898 do -- so `keys_from_a_claim`
    cannot be counted off the steps at all.

    THE SIBLING STEP MAKES THAT ARGUMENT SHARPER RATHER THAN WEAKER. 0 of the
    99,449 `PRE_UNREACHABLE` keys carry a claim, and that is a fact about the
    GATE and not about this step: a claim on a pair with no registrations is
    `GATE_UNREACHABLE`, which blocks, so `PRE_GATE` claims such a key four steps
    earlier. A reader who inferred "unreachable keys never carry claims" from
    the step alone would have the right number for the wrong reason.

    `agreeing` is `claims_agreeing_with_a_registration`'s output, passed in
    rather than recomputed, so the census cannot hold a second opinion about the
    largest exclusion in the stage.

    `keys_from_lineage` and `lineage_ceiling_offered` are the SAME population
    counted twice by two routes -- off the evidence and off the lane frame --
    and a test asserts they agree. That is deliberate: the lane and the
    precedence are built from two different traversals of the candidate list,
    and this is the one line that proves they still describe one world.

    Nothing pools the Mode 2 ceiling with the emitted Mode 2 count. The lane's
    own figure, the two refusals and the emitted total are four separate keys.
    """
    counts = {step: 0 for step in PRECEDENCE}
    for step in steps.values():
        counts[step] += 1
    cls = findings.classification
    lineage_lane = lanes.get(PRE_LINEAGE)
    offered = 0 if lineage_lane is None else len(lineage_lane)
    refused_gate = taken_by_mode_1 = 0
    if lineage_lane is not None:
        for s, a in zip(lineage_lane.sample_id,
                        lineage_lane.proposed_internal_assay_id):
            step = steps.get((int(s), int(a)))
            refused_gate += step == PRE_GATE
            taken_by_mode_1 += step == PRE_MODE_1
    out = {
        "input_keys": len(steps),
        "keys_from_a_claim": sum(1 for e in keys.values() if e.claim),
        "keys_from_lineage": sum(1 for e in keys.values() if e.lineage),
        "claims_agreeing_with_a_registration": len(agreeing),
        "keys_refused_by_the_gate": counts[PRE_GATE],
        "keys_mode_1": counts[PRE_MODE_1],
        "keys_lineage": counts[PRE_LINEAGE],
        "keys_unreachable": counts[PRE_UNREACHABLE],
        "keys_compat": counts[PRE_COMPAT],
        "keys_mode_3": counts[PRE_MODE_3],
        "rows": len(findings),
        "rows_mode_1": int((findings["mode"] == S.MODE_1).sum()),
        "rows_mode_2": int((findings["mode"] == S.MODE_2).sum()),
        "rows_mode_3": int((findings["mode"] == S.MODE_3).sum()),
        "rows_no_mode": int(findings["mode"].isna().sum()),
        "rows_cls_absence_lineage": int((cls == S.CLS_ABSENCE_LINEAGE).sum()),
        "rows_cls_absence_compat": int((cls == S.CLS_ABSENCE_COMPAT).sum()),
        "rows_cls_alt_label": int((cls == S.CLS_ALT_LABEL).sum()),
        "rows_cls_unresolved": int((cls == S.CLS_UNRESOLVED).sum()),
        "rows_cls_unreachable": int((cls == S.CLS_UNREACHABLE).sum()),
        "rows_without_a_classification": int(cls.isna().sum()),
        "lineage_ceiling_offered": offered,
        "lineage_refused_by_the_gate": refused_gate,
        "lineage_taken_by_mode_1": taken_by_mode_1,
    }
    assert set(out) == set(FINDINGS_CENSUS_KEYS), "FINDINGS_CENSUS_KEYS is out of date"
    # THE IDENTITY, ASSERTED AT RUNTIME AND NOT ONLY IN A TEST. Every key the
    # precedence granted an EMITTING step must have reached a row, so the input
    # minus the non-emitting steps IS the row count. It held silently while
    # `unify_findings` could drop a whole lane -- the census reported
    # `keys_compat: 4` beside `rows: 4` and nothing compared them -- and the
    # subtrahend is derived from `NON_EMITTING_STEPS` so it cannot drift from
    # the tuple that defines it.
    non_emitting = sum(counts[step] for step in NON_EMITTING_STEPS)
    assert out["input_keys"] - non_emitting == out["rows"], (
        f"{out['input_keys']} input key(s) minus {non_emitting} claimed by "
        f"{NON_EMITTING_STEPS} is not {out['rows']} emitted row(s): a step the "
        "precedence granted keys to reached no lane, or a lane emitted rows for "
        "keys nobody granted it")
    return {k: int(v) for k, v in out.items()}


# --- increment 1's 866 flags, superseded traceably ---------------------------
#
# One row per FLAG, which is one row per CLAIM, where `findings.csv` is one row
# per PROPOSAL. The two grains differ exactly where the gate refused a claim: 43
# of the 866 have a disposition row and no finding row, and that is the fact
# this file exists to carry.
#
# `prior_verdict` rides beside `precedence_step` so the supersession is legible
# IN THE ROW. A curator who reviewed the 866 opens this file and reads
# "MODE_3_FLAG -> PRE_GATE" or "MODE_3_FLAG -> CLS_ALT_LABEL" without holding
# two artifacts side by side, and increment 1's output is superseded rather than
# deleted.
#
# THIS FILE REPLACED `scripts/measure_absence_vs_contradiction.py`'S OUTPUT OF
# THE SAME NAME, AND THAT PROTOTYPE WAS DELETED 2026-08-18 -- recoverable from
# git history, and referred to here and in `compatibility.py` only as the
# historical OBSERVATION that motivated this work. It was left in the tree for
# one review cycle as a KNOWN SECOND WRITER OF THIS EXACT FILENAME: two
# writers, no coordination, last one wins, and an operator running both would
# silently read whichever finished last.
# It had no tests; it types samples by uuid prefix, drops
# unmapped membership rows, traverses the CHILD_OF relation rather than
# `DERIVED_FROM`, bands on `>` where `compatibility.compat_band` bands on `>=`,
# has no vocabulary gate at all, and labels a well-supported zero CONTRADICTION
# -- which is the relabelling this increment exists to perform. Its four-way
# split reads 351 / 250 / 214 / 51 against this classifier's 326 / 247 / 205 /
# 45 plus 43 refused, and the task report attributes every one of the
# differences.
DISPOSITION_COLUMNS = [
    "sample_id", "uuid", "sample_type",
    "registered_internal_assay_ids", "registered_internal_assay_titles",
    "claimed_internal_assay_id", "claimed_internal_assay_title",
    "tier", "source_field", "raw_value",
    "prior_verdict",
    "precedence_step", "mode", "classification", "action",
    "gate", "gate_reason",
    "lineage", "co_reg_rate", "co_reg_pop", "compat_band",
    "evidence_summary",
]


def disposition_breakdown(disposition: pd.DataFrame) -> pd.Series:
    """The 866's split: the step, or the CLASS where the step is `PRE_COMPAT`.

    The one aggregation the operator reads, so it is a named function rather
    than three lines inside a `print` loop -- which is what it was until review,
    and which is why the defect below had no test in front of it.

    NOTHING IS DROPPED SILENTLY, and `value_counts()` drops nulls by DEFAULT. A
    null `classification` on a `PRE_COMPAT` row would shrink this
    operator-facing total below the flag count with no error anywhere: the
    figure a curator uses to check that increment 1's population was fully
    re-disposed would simply be smaller, and smaller is exactly what "some of
    them turned out fine" looks like. So `dropna=False`, and the sum is CHECKED
    against the population it summarises rather than trusted.

    The partition test uses `Counter`, which counts NaN as a key, so it
    structurally could not have caught this: the guard existed on a path this
    aggregation does not take.

    Nothing can produce that null today -- `compat_findings` classifies every
    row it emits and `.where` keeps the STEP everywhere else -- so this is a
    tripwire rather than a fix for a live loss. It is here because the column it
    reads is nullable by contract and the cost of the tripwire is one keyword.

    RAISES rather than returning a short series. The branch is UNREACHABLE while
    `dropna=False` stands -- a `value_counts(dropna=False)` over a series of
    length n always sums to n -- so it is a tripwire for the keyword above it
    and not a branch any frame can enter. Stated plainly, because a guard that
    reads like live error handling and can never run is the same thing as a
    comment claiming a check that does not happen.
    """
    split = disposition.precedence_step.where(
        disposition.precedence_step != PRE_COMPAT,
        disposition.classification).value_counts(dropna=False)
    total = int(split.sum())
    if total != len(disposition):
        raise ValueError(
            f"the disposition breakdown sums to {total} over "
            f"{len(disposition)} flag(s), so {len(disposition) - total} of them "
            "are in no printed bucket. `value_counts` drops nulls by default "
            "and this one does not, so a short sum here means the frame changed "
            "shape rather than that a row was silently dropped.")
    return split


def mode3_disposition(
    flags: pd.DataFrame,
    steps: dict[tuple[int, int], str],
    findings: pd.DataFrame,
    attached: pd.DataFrame,
) -> pd.DataFrame:
    """Increment 1's flags, each beside the step that now claims it.

    Every column after `prior_verdict` is READ OFF the artifacts this run
    already produced rather than recomputed. A second computation of a
    classification, one function from the first, is how two answers to one
    question get shipped -- and a curator comparing this file with
    `findings.csv` would have no way to tell which was which.

    RAISES on a flag naming a pair the precedence never saw. A flag is a claim
    on a REGISTERED sample naming an assay it does not hold, which is an absence
    key by construction, so a miss means the flags came from a different extract
    than the steps -- and reporting that flag as unclassified would be a row
    silently absent from every count in this file.

    The gate-refused rows carry `gate` and `gate_reason` and NOTHING ELSE from
    the mode side: no mode, no classification, no action. A refused claim
    reached no mode, and filling those columns would be the laundering this
    precedence exists to stop, performed in the artifact rather than in the code.
    """
    by_key = {
        (int(r.sample_id), int(r.proposed_internal_assay_id)): r
        for r in findings.itertuples(index=False)
    }
    gate_of = {
        (int(r.sample_id), int(r.internal_assay_id)): (r.gate, r.gate_reason)
        for r in attached.itertuples(index=False)
    }

    rows = []
    for f in flags.itertuples(index=False):
        key = (int(f.sample_id), int(f.claimed_internal_assay_id))
        step = steps.get(key)
        if step is None:
            raise ValueError(
                f"flag {key} names a pair the precedence never ruled on. A flag "
                "is a claim on a registered sample naming an assay it lacks, "
                "which is an absence key by construction, so the flags frame "
                "and the steps describe different extracts.")
        found = by_key.get(key)
        gate, gate_reason = gate_of.get(key, (None, None))
        rows.append({
            "sample_id": int(f.sample_id),
            "uuid": f.uuid,
            "sample_type": f.sample_type,
            "registered_internal_assay_ids": f.registered_internal_assay_ids,
            "registered_internal_assay_titles": f.registered_internal_assay_titles,
            "claimed_internal_assay_id": int(f.claimed_internal_assay_id),
            "claimed_internal_assay_title": f.claimed_internal_assay_title,
            "tier": f.tier,
            "source_field": f.source_field,
            "raw_value": f.raw_value,
            "prior_verdict": f.verdict,
            "precedence_step": step,
            # `found.mode`, not `found["mode"]`: `itertuples` hands back a
            # namedtuple, and `mode` is a valid field name on one
            "mode": found.mode if found is not None else None,
            "classification": found.classification if found is not None else None,
            "action": found.action if found is not None else None,
            "gate": gate,
            "gate_reason": gate_reason,
            "lineage": found.lineage if found is not None else None,
            "co_reg_rate": found.co_reg_rate if found is not None else None,
            "co_reg_pop": found.co_reg_pop if found is not None else None,
            "compat_band": found.compat_band if found is not None else None,
            "evidence_summary": (found.evidence_summary if found is not None
                                 else None),
        })
    return pd.DataFrame(rows, columns=DISPOSITION_COLUMNS)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    """Run every mode over the extract on disk and write the two artifacts.

    WRITES EXACTLY TWO FILES, both csv, both under `out_dir`, both named here:
    `findings.csv` and `mode3-disposition.csv`. Every INPUT is left
    byte-identical, no parquet is rewritten, no database is touched and no
    workbook is produced. `test_main_writes_exactly_two_artifacts_and_leaves_
    every_other_byte_unchanged` hashes the whole tree before and after and
    diffs the two maps, because "it wrote exactly these two" is a claim about
    the directory rather than about the absence of a call.

    It also prints all four censuses, so that every figure this module's
    docstring states can be re-derived by running it. A number nobody can
    re-derive is what produced two conflicting readings of the Mode 2 ceiling on
    this branch.

    THE ARTIFACTS ARE WRITTEN AFTER THE FRAMES ARE BUILT, never as each is
    produced, and every frame-builder above is pure. A controller ledger on this
    branch once recorded a dispatch that never happened because the line was
    written before the call; here a run that fails part-way leaves the previous
    artifacts in place rather than half of a new pair.

    THE 866 FLAGS ARE RE-DERIVED HERE, THROUGH `audit.audit_contradictions`, AND
    NOT READ FROM THE CSV INCREMENT 1 LEFT IN THE SAME DIRECTORY -- which is why
    that name appears nowhere in this module as a path, exactly as with the
    precedent csv one paragraph down. Flags raised against
    another extract would be re-disposed against this one's steps, and
    `mode3_disposition` would raise on the first key the precedence never saw --
    or worse, agree by coincidence.

    PRECEDENT IS MINED HERE AND NOT READ FROM THE CSV STAGE B LEAVES IN THE SAME
    DIRECTORY -- which is why that name appears nowhere in this module as a path. The rules must describe the SAME edge frame the lineage
    index was built from, or a rule key this run constructs is looked up in a
    table mined from other data and the miss is reported as "no measured basis"
    -- absent evidence manufactured out of a stale file. Mining costs about three
    seconds, and re-derivability is this function's whole purpose.
    """
    from . import mode2 as M2        # local: `mode2` imports this module
    from . import precedent as B      # local: keeps the module import-light
    from . import vocabulary as V

    d, out = Path(extract_dir), Path(out_dir)

    samples = pd.read_parquet(d / "samples.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")
    edges = pd.read_parquet(d / "edges.parquet")
    claims = pd.read_parquet(out / "claims.parquet")
    vocab = V.load_vocabulary(out / "vocabulary.csv")

    type_reg = G.type_registration_index(membership, assays, nodes)
    # ONE type index, BOUND ONCE and handed to all three of `gate_claims`,
    # `mode2_findings` and `absence_keys`. It was built inline at each of the
    # first two before 2026-08-21, which was harmless while nothing else read
    # it; the precedence now decides reachability off the same map the gate
    # blocks a claim on, and two separately-constructed copies would be two
    # answers to "what type is this sample" one line apart.
    types = G.sample_type_index(nodes)
    gated = G.gate_claims(claims, vocab, type_reg, types)
    attached = attach_gate(claims, gated)
    population = unregistered_samples(samples, membership, assays)
    findings = mode1_findings(attached, population, project_index(samples))
    census = mode1_census(attached, population, findings)

    print(f"MODE 1 over {len(samples):,} sample records and "
          f"{len(membership):,} membership rows")
    for k in MODE1_CENSUS_KEYS:
        print(f"  {k:<32} {census[k]:>8,}")
    at_floor = findings[findings.claim_tier.isin(
        (S.T_STRONG, S.T_CORROBORATED))]
    print(f"  {'proposed at strong/corroborated':<32} {len(at_floor):>8,}"
          f"  over {at_floor.sample_id.nunique():,} samples")
    weak = int((findings.gate != S.GATE_PASS).sum())
    print(f"  {'proposed carrying a floor failure':<32} {weak:>8,}")
    absent = registered_samples_absent_from_samples(samples, membership)
    if absent:
        print(f"NOTE: {len(absent)} registered sample(s) have no row in the "
              f"samples frame and are in no figure above: {absent[:10]}"
              + (" ..." if len(absent) > 10 else ""))

    registered = registered_internal(membership, assays)
    children_of, parents_of, uuid_of, _ = L.lineage_index(
        edges, samples, membership)
    m2 = M2.mode2_findings(
        attached,
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=registered,
        rules=M2.precedent_rules(B.mine_precedent(edges, membership, assays)),
        reg_projects=M2.registration_projects(membership, assays),
        types=types,
        type_reg=type_reg,
        titles=M2.assay_titles(assays),
        projects=project_index(samples),
    )
    ceiling = L.mode2_ceiling(children_of, parents_of, registered)
    m2census = M2.mode2_census(m2, ceiling, attached)

    print(f"MODE 2 over the DERIVED_FROM CEILING -- every (sample, assay) a "
          f"lineage neighbour makes available BEFORE precedent is read:")
    for k in M2.MODE2_CENSUS_KEYS:
        print(f"  {k:<42} {m2census[k]:>8,}")
    print("  the CEILING is not a forecast. Precedent cuts the weak direction "
          "to about 2% of it, and the two directions are never one number: "
          "ADD_PARENT is corroborated by co-registration 88 times out of 88 "
          "over increment 1's 866 flags, ADD_CHILD 15 times out of 263.")
    print("  the ceiling includes samples registered in NO assay, which are "
          "also Mode 1's population, and it should: a sample registered "
          "nowhere has a full gap wherever a neighbour holds something.")
    print("survival by direction -- a READING ORDER and never a permission; "
          "every row above is emitted at every threshold:")
    for r in M2.precedent_survival(m2).itertuples(index=False):
        print(f"  rate >= {r.threshold:<5} {r.action:<22} {r.rows:>8,} rows"
              f"  over {r.samples:>8,} samples   of {r.of_rows:,}"
              f"   on {r.rule_groups:>3} evidence group(s)")
    print("  `evidence group(s)` is how many distinct (n_both, n_child_only, "
          "n_parent_only) triples those rows rest on -- a LOWER BOUND on the "
          "precedent rules behind them. A row count counts affected SAMPLES and "
          "not independent evidence: at rate >= 0.95 the weak direction's 371 "
          "rows rest on 13 groups, one of which keys 170 of them, against 46 "
          "rows on 2. That is why the crossover at the top of this curve is NOT "
          "evidence that ADD_CHILD is the stronger direction.")
    print(f"  {m2census['rows_without_precedent']:,} row(s) carry NO measured "
          "rate and survive no threshold, including 0.0: absent evidence is "
          "not a rate of zero")

    # --- the unified pass ---------------------------------------------------
    candidates = M2.mode2_candidates(children_of, parents_of, registered)
    keys = absence_keys(attached, population=population,
                        registered=registered, candidates=candidates,
                        type_reg=type_reg, types=types, uuid_of=uuid_of)
    steps = precedence_steps(keys)
    titles = M2.assay_titles(assays)
    projects = project_index(samples)
    compat = compat_findings(
        attached, steps=steps, registered=registered,
        table=CP.co_registration(membership, assays, nodes),
        titles=titles, projects=projects)
    lanes = {
        PRE_MODE_1: findings,
        PRE_LINEAGE: m2,
        PRE_UNREACHABLE: m2,        # the SAME frame; `unify_findings` filters
                                    # each lane by the step that owns each key,
                                    # so every row lands in exactly one
        PRE_COMPAT: compat,
        PRE_MODE_3: mode3_findings(),
    }
    unified = unify_findings(steps, lanes)
    agreeing = claims_agreeing_with_a_registration(attached, registered)
    ucensus = findings_census(keys, steps, unified, lanes, agreeing=agreeing)

    print("THE PRECEDENCE, over every (sample, proposed assay) ABSENCE key -- "
          "one a claim names, one a lineage neighbour offers, or both:")
    for k in FINDINGS_CENSUS_KEYS:
        print(f"  {k:<44} {ucensus[k]:>8,}")
    print(f"  the {ucensus['keys_refused_by_the_gate']:,} key(s) the gate "
          "refused emit NOTHING, and that is the third design error reversed: "
          "a rejected claim reaches no mode even where a lineage neighbour "
          "carries the same pair, which is the shape of the 24 flags "
          "increment 1 routed to Mode 2: A.FLOW claiming 30 Flow Cytometry "
          "and A.SPC claiming 130 Mass Spectrometry. THAT SCOPING IS PART OF "
          "THE FIGURE -- keyed on the TERM instead, `FlowJo*` and mass-spectra "
          "terms are 25 flags, the extra being one D.ADNKA sample carrying "
          "`FlowJo 10.3`. Both counts are right and they are not "
          "interchangeable; all of them are gate refusals either way.")
    print(f"  emitted MODE_2 is {ucensus['rows_mode_2']:,} against a lineage "
          f"CEILING of {ucensus['lineage_ceiling_offered']:,}: the gate refuses "
          f"{ucensus['lineage_refused_by_the_gate']:,} of the ceiling's rows "
          f"and Mode 1 takes {ucensus['lineage_taken_by_mode_1']:,} more, and "
          f"{ucensus['rows_cls_absence_compat']:,} compatibility rows join it.")
    print(f"  MODE_3 emitted {ucensus['rows_mode_3']:,} rows because there is "
          "no detector for it -- UNDETECTED and not small. Metadata "
          "disagreeing with a registration is not evidence the registration is "
          "wrong.")

    flags = audit_contradictions(claims, membership, assays, nodes)
    disposition = mode3_disposition(flags, steps, unified, attached)
    prior = disposition_breakdown(disposition)
    print(f"  increment 1 raised {len(flags):,} MODE_3 flags; not one is a "
          "contradiction under this precedence:")
    for k, v in prior.items():
        print(f"    {k:<42} {v:>8,}")

    unified.to_csv(out / "findings.csv", index=False)
    disposition.to_csv(out / "mode3-disposition.csv", index=False)
    print(f"wrote {out / 'findings.csv'} ({len(unified):,} rows) and "
          f"{out / 'mode3-disposition.csv'} ({len(disposition):,} rows). "
          "Nothing else was written: no parquet was rewritten, no database and "
          "no workbook was touched by THIS run, and every row in both files is "
          "a proposal awaiting operator approval. There is no APPROVE column "
          "and nothing here authorises a change.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
