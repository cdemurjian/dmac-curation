# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage C. Mode 1: a sample in NO assay. Mode 2: a neighbour holds one it lacks.

NOTHING DECIDES. EVERYTHING PROPOSES. Every row this module builds reaches the
operator as a proposal they approve or reject, no number in it authorises a
change, and no function here is named for a decision. It reads six parquet
files and one csv and writes nothing at all -- not even a findings file, which
belongs to the task that emits every mode at once.

MODE 2 IS BELOW MODE 1 IN THIS FILE AND THE SECTIONS DO NOT INTERLEAVE. The two
modes share `attach_gate`, the indexes and `FINDING_COLUMNS`, and nothing else:
Mode 1's evidence is a metadata claim on a sample with no membership to reason
from, and Mode 2's is a registration a neighbour actually holds. See the
`--- Mode 2 ---` banner for its own headline figures, all of which carry the
word CEILING where they are pre-precedent counts.

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
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from . import _schema as S
from . import gate as G
from . import lineage as L
from .audit import registered_internal
from .precedent import assay_index, membership_index

# --- what produced a proposal ------------------------------------------------
#
# A closed family that enumerates itself, the way `PROVENANCES` and
# `GATE_OUTCOMES` do: a consumer must be able to ask "is this one of the three"
# without restating the three, because a restatement is what drifts.
#
# `FINDING_COLUMNS.proposed_by` is spelled `proposed_` and not `decided_` under
# the binding constraint, and these values inherit that: the column header is
# where a reader forms their belief about what the pipeline already did.
#
# ALL THREE ARE DECLARED HERE THOUGH MODE 1 EMITS ONLY THE FIRST. Tasks 6 and 8
# extend this module, and the alternative is each of them inventing its own
# spelling for one concept in one column -- two names one screen apart, which is
# this branch's signature defect. Declaring the family before its second producer
# exists is the same call `_schema` made for `MODE_3` and for
# `co_reg_registered_internal_assay_id`, and for the same reason: this is the
# cheapest it will ever be.
BY_CLAIM = "BY_CLAIM"            # the gated vocabulary claim alone -- Mode 1
BY_PRECEDENT = "BY_PRECEDENT"    # stage B precedent on the hop alone
BY_BOTH = "BY_BOTH"              # precedent proposed, the claim disambiguated
PROPOSAL_SOURCES = (BY_CLAIM, BY_PRECEDENT, BY_BOTH)

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
    rescued the singular either -- 75 of the 154 internal assay ids span more
    than one project, up to seven -- so there is no single-valued project
    anywhere on the row, from either side of it.

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


# --- Mode 2 ------------------------------------------------------------------
#
# A lineage NEIGHBOUR registers an assay this sample lacks. Precedent on the hop
# says how often that gap gets closed elsewhere, and the sample's own metadata
# says WHICH assay when the hop offers several. Neither authorises a write and
# neither is compared against a threshold here.
#
# THE TWO DIRECTIONS ARE NOT PEERS AND NO FIGURE MAY POOL THEM. Measured over
# increment 1's 866 flags, A_ADD_PARENT is corroborated by co-registration 88
# times out of 88 and A_ADD_CHILD 15 times out of 263. On the single hop that
# justified this mode, `TIS <- PAV`, the child's assay flows up under 74 Tissue
# Collection at 0.931 while the parent's flows down under 56 Patient Visit at
# 0.006. The mechanism is that a sample has ONE producing assay and many
# consuming ones, so "the child is in X" pins the parent tightly while "the
# parent is in X" says little about any one child.

# The two precedent rates, spelled as the `PRECEDENT_COLUMNS` names they are.
#
# THE VALUE OF `FINDING_COLUMNS.precedent_direction` IS THIS STRING, so a row
# carries the NAME of the column its rate came from and an operator can join it
# back to the precedent csv stage B writes and check the number without reading
# any code. Spelling
# the direction `up` / `down`, or as the action, would leave the audit trail one
# lookup short in exactly the artifact whose premise is that a human checks it.
DIR_PROPAGATION = "propagation_rate"   # given the CHILD is in it, is the parent
DIR_REVERSE = "reverse_rate"           # given the PARENT is in it, is the child
PRECEDENT_DIRECTIONS = (DIR_PROPAGATION, DIR_REVERSE)

# Which action a lineage relation proposes. `LIN_CHILD` means a CHILD carries the
# assay, so what is missing is the PARENT's registration.
RELATION_ACTION = {S.LIN_CHILD: S.A_ADD_PARENT, S.LIN_PARENT: S.A_ADD_CHILD}

# WHICH RATE EACH ACTION IS JUDGED ON, AND THE ONE PLACE THAT MAPPING LIVES.
# This is the defect the whole task is shaped around: reading `propagation_rate`
# for an A_ADD_CHILD row produces a plausible number, no error and no row-count
# anomaly, and the two rates genuinely differ -- 1.000 against 0.006 on
# `(2, TIS, PAV, 56)` alone. The rate is fetched with `getattr(rule, DIRECTION)`
# so the emitted `precedent_direction` column and the number beside it cannot
# disagree, whatever a later edit does to this dict.
ACTION_PRECEDENT_DIRECTION = {
    S.A_ADD_PARENT: DIR_PROPAGATION,
    S.A_ADD_CHILD: DIR_REVERSE,
}

# Where `precedent_survival` reports, and nothing else. NOT a set of gates: under
# the binding constraint a threshold orders what an operator reads first and
# grants no permission, so every row is emitted whatever these say, and
# `mode2_findings` never sees them. 0.0 is included deliberately -- it is where a
# row with NO measured rate visibly fails to appear.
SURVIVAL_THRESHOLDS = (0.0, 0.5, 0.75, 0.9, 0.95)
SURVIVAL_COLUMNS = ["threshold", "action", "rows", "samples", "of_rows"]

# Every key `mode2_census` returns, in report order, declared for the reason
# `MODE1_CENSUS_KEYS`, `INTEGRITY_KEYS` and `CEILING_KEYS` are: the report prints
# them all, and a key that stops being produced must break rather than stop being
# printed.
#
# THE SUFFIX IS THE UNIT. `rows_*` counts (sample, assay) PROPOSALS and
# `samples_*` counts distinct samples; the two differ by about 1.5x on the real
# extract and a count quoted without its unit is this project's signature defect.
#
# THE UNSEEN-PAIR KEY IS SPLIT BY DIRECTION AND THE OTHERS ARE NOT, which is a
# deliberate line rather than an oversight. The two directions carry different
# evidential weight, so any figure a reader would compare ACROSS them is reported
# apart -- the split, the survival curve, and the share of rows creating a
# (type, assay) pair from nothing. The remaining keys describe the mode's own
# bookkeeping and are totals, each printed beside the split above it.
#
# TWO IDENTITIES HOLD OVER THEM and a test asserts both, plus two more against
# `lineage.mode2_ceiling`, which counts the same population by a different route:
#
#     rows = rows_add_parent + rows_add_child
#     rows = rows_with_precedent + rows_without_precedent
#
# `rows_with_a_blocked_claim` OVERLAPS `rows` minus `rows_proposed_by_both` and
# partitions nothing: a row whose claim the gate rejected is proposed BY_PRECEDENT
# like any other, and this key exists so the rejected claim is counted rather than
# silently unused. 4,255 rows on the real extract carry one.
MODE2_CENSUS_KEYS = (
    "rows",
    "samples",
    "rows_add_parent",
    "samples_add_parent",
    "rows_add_child",
    "samples_add_child",
    "rows_reachable_both_ways",
    "rows_with_multiple_supports",
    "rows_with_precedent",
    "rows_without_precedent",
    "rows_proposed_by_both",
    "rows_with_a_blocked_claim",
    "rows_creating_an_unseen_pair_add_parent",
    "rows_creating_an_unseen_pair_add_child",
    "rows_on_a_sample_registered_nowhere",
    "samples_registered_nowhere",
    "rows_without_a_sample_type",
    "rows_without_a_samples_row",
)


class Rule(NamedTuple):
    """One precedent row's evidence, keyed out of `precedent_rules`.

    A NAMEDTUPLE AND NOT A BARE 5-TUPLE, for the reason
    `compatibility.CoRegistration` gives: three of these fields are counts and
    two are rates, and the two rates are the substitutable pair this entire task
    exists to keep apart. A positional unpack that swapped them would produce a
    populated, wrong row rather than an error.

    THE FIELD NAMES ARE THE `PRECEDENT_COLUMNS` NAMES, exactly, and that is
    load-bearing rather than tidy: `mode2_findings` reads the rate with
    `getattr(rule, ACTION_PRECEDENT_DIRECTION[action])` and emits that same
    string into `precedent_direction`, so the column naming the rate and the rate
    itself come from one lookup and cannot drift apart.
    """
    n_both: int
    n_child_only: int
    n_parent_only: int
    propagation_rate: float
    reverse_rate: float


def assay_titles(assays: pd.DataFrame) -> dict[int, str]:
    """internal assay id -> its title, through `precedent.assay_index`.

    The SAME one-line derivation `audit.audit_contradictions` performs at
    audit.py:71, off the same funnel, so the two cannot disagree about what an id
    decodes to; it is a function here because Mode 2 needs it on rows that carry
    no claim, where `CLAIM_COLUMNS.internal_assay_title` is not available.

    Total and single-valued on the real extract: 0 of the 458 assay records carry
    an internal id with no title, and no internal id resolves to two distinct
    titles over the 154 in the map. The 17 junction-less records decode to their
    OWN title under their fallback id, which is what keeps a registration through
    one of them printable rather than blank.

    A TITLE IS DISPLAY AND NEVER IDENTITY. Nothing keys, joins or groups on the
    output: 458 seek assay records collapse to 291 normalised titles and 124 seek
    ids collide numerically with genuine internal ids under 122 different titles.
    """
    return {iaid: title for _, iaid, title in assay_index(assays).values()}


def registration_projects(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> dict[tuple[int, int], frozenset[int]]:
    """(sample_id, internal assay id) -> the projects its registrations name.

    THE RULE KEY'S PROJECT COMES FROM THE NEIGHBOUR'S OWN REGISTRATION, and this
    index is what makes that possible. `precedent.mine_precedent` keys each
    observation on `assay_index(assays)[seek_assay_id]`'s project -- the project
    of the SEEK RECORD the membership row names -- so a lookup keyed any other
    way asks for a rule stage B never wrote.

    THE ASSAY'S PROJECT LIST IS NOT A SUBSTITUTE. 75 of the real extract's 154
    internal assay ids span more than one project, up to seven, so "the project
    of assay X" is not single-valued and choosing one of them would key the wrong
    rule silently. Measured 2026-08-17, only 1 of 214,124 (sample, internal
    assay) registrations spans two projects at all, so the multiplicity this
    returns is real and rare; `mode2_findings` walks it in ascending order and
    takes the first rule that exists, which is stable across runs.

    Built on `precedent.membership_index` composed with `assay_index`, which is
    exactly how `audit.registered_internal` is built, so the two describe ONE
    registration set: a test asserts their key sets are equal. A second grouping
    of the membership frame here would be a third definition of "registered" in a
    package where two have already produced wrong figures.

    RAISES on a membership row naming an assay absent from the assays frame,
    following every other crossing in this package. A skipped registration would
    remove a project from the key and turn a rule that exists into one that does
    not -- reported as "no measured basis", which is a lie with no error beside
    it.

    Returns frozensets in a PLAIN dict: callers ask about pairs that are not
    registered, and a defaultdict would answer by creating the entry.
    """
    ainfo = assay_index(assays)
    unknown = sorted({int(a) for a in membership.assay_id} - set(ainfo))
    if unknown:
        raise ValueError(
            f"membership registers samples in {len(unknown)} assay(s) absent "
            f"from the assays frame: {unknown}. Those registrations carry no "
            "project, so the precedent rule key cannot be built and the row "
            "would report 'no measured basis' for a hop that has one. "
            "Re-extract so the two frames agree."
        )
    out: dict[tuple[int, int], set[int]] = {}
    for sample_id, assay_ids in membership_index(membership).items():
        for seek_id in assay_ids:
            project_id, internal_id, _ = ainfo[seek_id]
            out.setdefault((sample_id, internal_id), set()).add(project_id)
    return {k: frozenset(v) for k, v in out.items()}


def precedent_rules(precedent: pd.DataFrame) -> dict[tuple, Rule]:
    """`RULE_KEY` -> `Rule`, over stage B's mined frame. Nothing is dropped.

    NO GROUPBY, AND THAT IS THE POINT -- the same ruling `mine_precedent` states
    and for the same reason. `internal_assay_id` is nullable at source, 17 assay
    records have no junction row, and it is a `RULE_KEY` component:
    `frame.groupby(S.RULE_KEY)` defaults to `dropna=True`, so the natural pandas
    spelling of this index silently discards every rule keyed on one of those 17
    and returns a table that still looks right. Counting into a dict makes the
    drop impossible by construction rather than by remembering a keyword.

    RAISES on a null key component rather than skipping it, because a rule that
    vanishes here does not surface as an error anywhere downstream: the row it
    would have keyed simply reports that nothing was measured on its hop.

    RAISES on a duplicate key too. `mine_precedent` emits one row per key by
    construction, so a duplicate means the frame was concatenated or re-mined,
    and taking either row would be a choice made by row order over an artifact
    whose order is explicitly not stable across extracts.

    The key components are cast to `int` and `str` on the way in, so a frame
    round-tripped through csv -- where `project_id` returns as `numpy.int64` and
    a type as `object` -- keys identically to one held in memory. A key that
    matches only before a save is the same silent miss this function raises over.
    """
    out: dict[tuple, Rule] = {}
    for r in precedent.itertuples(index=False):
        null = [c for c in S.RULE_KEY if pd.isna(getattr(r, c))]
        if null:
            raise ValueError(
                f"a precedent rule carries a null {null} and every component of "
                f"RULE_KEY {S.RULE_KEY} is part of its identity. `assay_index` "
                "gives the 17 junction-less assays a fallback id precisely so "
                "this cannot happen; a null here means the frame was built "
                "without it. Dropping the row -- which `groupby` would do "
                "silently -- reports its hop as never measured."
            )
        key = (int(r.project_id), str(r.child_type), str(r.parent_type),
               int(r.internal_assay_id))
        if key in out:
            raise ValueError(
                f"the precedent frame carries a duplicate rule key {key}. "
                "`mine_precedent` emits one row per key, so this frame was "
                "concatenated or re-mined; picking either row would settle a "
                "rate by row order.")
        out[key] = Rule(int(r.n_both), int(r.n_child_only), int(r.n_parent_only),
                        float(r.propagation_rate), float(r.reverse_rate))
    return out


def mode2_candidates(
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    registered: dict[int, set[int]],
) -> list[tuple[int, int]]:
    """Every (sample, assay) a lineage neighbour makes available. THE CEILING.

    ONE ENTRY PER (SAMPLE, ASSAY) AND NEVER PER EDGE OR PER NEIGHBOUR, because
    the proposal is a membership row: adding sample S to assay X is one write
    however many neighbours support it, and `lineage.lineage_supports` is what
    counts the supports behind it. An edge-grained enumeration would report the
    fan-out of the lineage graph -- 1,526 neighbours on one row of the real
    extract -- as the size of the proposal set.

    A CEILING AND NOT A FORECAST, and the word must accompany the number
    everywhere. Nothing here consults precedent, the vocabulary or the gate.
    Measured 2026-08-17 over `DERIVED_FROM`: 172,338 pairs over 115,626 samples,
    which `lineage.mode2_ceiling` counts independently and which a test
    reconciles against this list.

    IN ARRIVAL ORDER, deduplicated, and NOT sorted. The order follows
    `lineage_index`'s dicts, which follow the edge frame, whose row order is not
    stable across extracts -- which is exactly why `mode2_findings` sorts its
    output. Returning a sorted list here would make that sort a no-op and the
    test on it vacuous, while leaving the artifact's stability resting on an
    order nobody guarantees.

    "Registered" is ANY membership row, crossed by `audit.registered_internal`.
    The MAPPABLE-only reading is 82 samples smaller and understates this ceiling
    by 227 ADD_PARENT and 1,098 ADD_CHILD rows; it is the difference between the
    two published readings of this number and it has been confused three times on
    this branch.

    A sample registered NOWHERE contributes its full gap, which is right and is
    where Mode 1's population and Mode 2's overlap: 2,405 of Mode 1's 6,242 reach
    a Mode 2 row, 2.1% of each direction's samples.
    """
    out: dict[tuple[int, int], None] = {}
    empty: frozenset[int] = frozenset()
    nothing: set[int] = set()
    for sample_id in dict.fromkeys(list(children_of) + list(parents_of)):
        have = registered.get(sample_id, nothing)
        for neighbour in (list(children_of.get(sample_id, empty))
                          + list(parents_of.get(sample_id, empty))):
            for assay_id in registered.get(neighbour, nothing):
                if assay_id not in have:
                    out[(sample_id, assay_id)] = None
    return list(out)


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


def _mode2_summary(
    action: str, relation: str, neighbour_uuid: str, n_supports: int,
    proposed: int, title: str, hop: tuple, project_id, rule: Rule | None,
    direction: str | None, sample_type, type_registrations, claim, blocked: bool,
) -> str:
    """The sentence an operator reads, carrying what the columns cannot.

    THE RULE KEY IS HERE OR NOWHERE. `FINDING_COLUMNS` has no `child_type`, no
    `parent_type` and no singular `project_id` -- `RULE_KEY` owns all three and
    the row deliberately does not repeat them, since the same names mean
    different things on the two frames. So a reader who wants to check
    `precedent_rate` against stage B's precedent csv needs the key spelled out,
    and this
    is where it is spelled.

    It also says which direction was read and in which units, because
    `precedent_rate` alone is the number this task exists to keep from being
    silently the wrong one.
    """
    parts = [
        f"{relation}: {neighbour_uuid} registers {proposed} {title}, which this "
        f"sample does not"
    ]
    if n_supports > 1:
        parts.append(f"{n_supports} lineage neighbour(s) register it; this is "
                     f"ONE membership proposal, not {n_supports}")
    child_type, parent_type = hop
    key = (f"(project {project_id}, {child_type} -> {parent_type}, assay "
           f"{proposed})")
    if rule is None:
        parts.append(
            f"no precedent rule for {key}, so this proposal has NO measured "
            "basis; that is absent evidence and not a rate of zero")
    else:
        parts.append(
            f"precedent {key} {direction} {getattr(rule, direction):.3f} over "
            f"n_both {rule.n_both}, n_child_only {rule.n_child_only}, "
            f"n_parent_only {rule.n_parent_only}")
    if type_registrations is None:
        parts.append("this sample carries no resolvable type, so no (type, "
                     "assay) population could be counted")
    elif type_registrations == 0:
        parts.append(
            f"NO {sample_type} sample is registered in {proposed} anywhere, so "
            "this would create a (sample type, assay) pair that exists nowhere")
    else:
        parts.append(f"{type_registrations} {sample_type} sample(s) are already "
                     f"registered in {proposed}")
    if claim is not None:
        parts.append(
            f"the sample's own metadata agrees: {claim.source_field} "
            f"{claim.raw_value!r} maps to {proposed} ({claim.tier}, "
            f"{claim.vocab_provenance}, {claim.gate})")
    elif blocked:
        parts.append("a metadata claim naming this assay exists and the gate "
                     "rejected it, so it corroborates nothing here")
    parts.append(f"proposes {action}; nothing is written and nothing is decided")
    return "; ".join(parts)


def mode2_findings(
    attached: pd.DataFrame,
    *,
    children_of: dict[int, frozenset[int]],
    parents_of: dict[int, frozenset[int]],
    uuid_of: dict[int, str],
    registered: dict[int, set[int]],
    rules: dict[tuple, Rule],
    reg_projects: dict[tuple[int, int], frozenset[int]],
    types: dict[str, str],
    type_reg: dict[tuple[str, int], int],
    titles: dict[int, str],
    projects: dict[int, str],
) -> pd.DataFrame:
    """One row per (sample, assay) a lineage neighbour holds. Nothing is decided.

    TEN KEYWORD-ONLY INDEXES, and the keyword is the guard. Four of them are
    `dict[int, ...]` and two more are keyed on a 2-tuple, so a positional call
    could transpose `children_of` with `parents_of`, `titles` with `projects` or
    `type_reg` with `reg_projects` and get a populated, wrong frame with no
    error -- this package's named failure class, at an interface Task 8 calls.
    `lineage.py` separates its own two near-identical functions by arity for the
    same reason; at eleven arguments only the name is left to separate them.

    THE DIRECTION AND THE RATE. `lineage.neighbour_registers` returns the
    relation and names ONE neighbour, `RELATION_ACTION` turns that into the
    action, and `ACTION_PRECEDENT_DIRECTION` names which of stage B's two rates
    judges it. Reading `propagation_rate` for an `A_ADD_CHILD` row is silent and
    plausible -- and wrong by 1.000 against 0.006 on `(2, TIS, PAV, 56)` alone --
    so the mapping has exactly one definition and the emitted
    `precedent_direction` is the very attribute name the rate was fetched by.

    ONE ROW PER (SAMPLE, ASSAY), INCLUDING A PAIR REACHABLE BOTH WAYS. Adding a
    sample to an assay is one membership write whichever neighbour argues for it,
    so 132 pairs on the real extract that qualify in both directions are emitted
    once, as `A_ADD_PARENT`, the corroborated direction -- and that, exactly, is
    why the emitted ADD_CHILD count (117,331) is smaller than the ceiling's
    (117,463). `lineage_n_supports` records how many neighbours there were, so
    the collapse hides nothing.

    THE RULE KEY IS ALL FOUR COMPONENTS and its PROJECT comes from the
    neighbour's own registration, through `registration_projects`. A
    three-of-four match is the dangerous near miss: the world's strongest rule
    for an assay is usually on a different hop, so a component-blind lookup
    returns a real, confident, wrong number. Where a registration spans several
    projects -- 1 of 214,124 on the real extract -- they are walked in ascending
    order and the first rule that exists wins, which is stable across runs.

    A HOP WITH NO RULE IS NULL AND NEVER 0.0, and the row is still emitted. 0.000
    is a real rate meaning "observed, and never once co-registered"; a null means
    nobody measured. 10 rows of the real extract's 172,338 are null, all of them
    samples whose two node uuids disagree on TYPE -- the 79 `lineage_index`
    counts -- so the hop the miner keyed is not the hop this row's type builds.

    METADATA DISAMBIGUATES AND DOES NOT SELECT. A hop can offer several candidate
    assays, and precedent speaks only about the hop; the sample's own gated claim
    is what varies per sample. So a claim on the SAME (sample, assay) marks the
    row `BY_BOTH` and every other candidate is still emitted as `BY_PRECEDENT`.
    Suppressing them would be a decision, and the operator makes those.

    A GATE-REJECTED CLAIM CORROBORATES NOTHING. Passage is `gate.reaches_modes`,
    read off `gate_failures`; a blocked claim reaches no mode and so cannot
    promote a row here either. It is not silently unused -- the census counts it
    and the summary says one was found. 4,255 rows on the real extract carry one.

    WHAT THIS MODE DOES NOT ASSERT, and the nulls are the assertion. The whole
    co-registration block and `compat_band` are NULL because lineage runs BEFORE
    co-registration under the precedence contract and a neighbour already holding
    the assay settles it, so the test never ran. `BAND_NO_SUPPORT` would say
    "measured, and the population was too small"; a zero would say "these never
    coexist", which is the alternative-label finding. Task 8 can FILL a null
    without contradicting anything shipped here, and would have to OVERWRITE a
    value -- indistinguishable, in a diff a curator reads, from the pipeline
    changing its mind. The claim block is null on the same rule wherever no
    gated claim names the pair.

    `classification` is `CLS_ABSENCE_LINEAGE` on every row and is NOT null,
    because the lineage test DID run and that is precisely what it establishes.

    Sorted on `(sample_id, proposed_internal_assay_id)`, a total order on this
    output. `mode2_candidates` returns arrival order on purpose so this sort has
    work to do.
    """
    claim_of: dict[tuple[int, int], object] = {}
    blocked_pairs: set[tuple[int, int]] = set()
    for row, reaches in zip(attached.itertuples(index=False),
                            G.reaches_modes(attached)):
        pair = (int(row.sample_id), int(row.internal_assay_id))
        if reaches:
            claim_of[pair] = row
        else:
            blocked_pairs.add(pair)

    rows = []
    for sample_id, assay_id in mode2_candidates(children_of, parents_of,
                                                registered):
        relation, neighbour, neighbour_uuid = L.neighbour_registers(
            sample_id, assay_id, children_of, parents_of, uuid_of, registered)
        kids, rents = L.lineage_supports(
            sample_id, assay_id, children_of, parents_of, registered)
        # `mode2_candidates` emits a pair only where a neighbour registers the
        # assay and the sample does not, which is the same condition both
        # functions test. If they ever disagree the row would carry a relation
        # from one and a support count from the other.
        assert relation in RELATION_ACTION, (
            f"({sample_id}, {assay_id}) reached the candidate list and "
            f"`neighbour_registers` reports {relation}")
        assert neighbour == (kids[0] if kids else rents[0]), (
            "`neighbour_registers` and `lineage_supports` disagree about which "
            f"neighbour settles ({sample_id}, {assay_id})")

        action = RELATION_ACTION[relation]
        sample_type = types.get(uuid_of.get(sample_id))
        neighbour_type = types.get(uuid_of.get(neighbour))
        hop = ((neighbour_type, sample_type) if relation == S.LIN_CHILD
               else (sample_type, neighbour_type))

        rule: Rule | None = None
        project_id = None
        if None not in hop:
            for candidate in sorted(reg_projects.get((neighbour, assay_id), ())):
                if (candidate, *hop, assay_id) in rules:
                    rule = rules[(candidate, *hop, assay_id)]
                    project_id = candidate
                    break
        # `is not None` and never a bare truth test: a `Rule` is a 5-tuple and so
        # is always truthy, which makes `if rule` correct today and silently
        # wrong the first time the shape changes.
        direction = (ACTION_PRECEDENT_DIRECTION[action]
                     if rule is not None else None)
        # A MISSING (type, assay) CELL IS A MEASURED ZERO and a missing TYPE is
        # not: `type_registration_index` holds a cell for every pair that occurs,
        # so an absent key means no sample of the type is registered there
        # anywhere -- the gate's own reachability ruling. With no type there is
        # no cell to look for and the answer is that nobody measured.
        registrations = (None if sample_type is None
                         else type_reg.get((sample_type, assay_id), 0))
        claim = claim_of.get((sample_id, assay_id))
        blocked = (sample_id, assay_id) in blocked_pairs
        reg_ids, reg_titles = _registered_columns(sample_id, registered, titles)
        title = titles.get(assay_id)

        rows.append({
            "sample_id": sample_id,
            # out of the traversal and never a `samples` join, which is blank for
            # the 243 unresolved endpoints, 182 of them registered
            "uuid": uuid_of.get(sample_id),
            "sample_type": sample_type,
            # NULL and not "" for the 185 candidate samples with no `samples`
            # row: their projects were never read, where "" means read and none
            "project_ids": projects.get(sample_id),
            "registered_internal_assay_ids": reg_ids,
            "registered_internal_assay_titles": reg_titles,
            "proposed_internal_assay_id": assay_id,
            "proposed_internal_assay_title": title,
            "mode": S.MODE_2,
            "classification": S.CLS_ABSENCE_LINEAGE,
            # the claim block, null wherever no GATED claim names this pair
            "gate": claim.gate if claim is not None else None,
            "claim_tier": claim.tier if claim is not None else None,
            "contested": bool(claim.contested) if claim is not None else None,
            "source_field": claim.source_field if claim is not None else None,
            "raw_value": claim.raw_value if claim is not None else None,
            "vocab_support": (int(claim.vocab_support)
                              if claim is not None else None),
            "vocab_purity": (float(claim.vocab_purity)
                             if claim is not None else None),
            "vocab_provenance": (claim.vocab_provenance
                                 if claim is not None else None),
            "type_registrations": registrations,
            "lineage": relation,
            "lineage_neighbour_uuid": neighbour_uuid,
            "lineage_n_supports": len(kids) + len(rents),
            # the test this mode never ran: see the docstring
            "co_reg_rate": None,
            "co_reg_pop": None,
            "co_reg_registered_internal_assay_id": None,
            "co_reg_alt_label_internal_assay_id": None,
            "co_reg_alt_label_pop": None,
            "compat_band": None,
            "precedent_rate": (getattr(rule, direction)
                               if rule is not None else None),
            "precedent_direction": direction,
            "precedent_n_both": rule.n_both if rule is not None else None,
            "precedent_n_child_only": (rule.n_child_only
                                       if rule is not None else None),
            "precedent_n_parent_only": (rule.n_parent_only
                                        if rule is not None else None),
            "proposed_by": BY_BOTH if claim is not None else BY_PRECEDENT,
            "evidence_summary": _mode2_summary(
                action, relation, neighbour_uuid, len(kids) + len(rents),
                assay_id, title, hop, project_id, rule, direction, sample_type,
                registrations, claim, blocked),
            "action": action,
        })

    return pd.DataFrame(rows, columns=S.FINDING_COLUMNS).sort_values(
        ["sample_id", "proposed_internal_assay_id"], ignore_index=True,
    )


def mode2_census(
    findings: pd.DataFrame,
    ceiling: dict[str, int],
    attached: pd.DataFrame,
) -> dict[str, int]:
    """Where every Mode 2 proposal sits. See `MODE2_CENSUS_KEYS`.

    `ceiling` is `lineage.mode2_ceiling`'s output, taken rather than re-derived,
    and it is a CROSS-CHECK and not a source: it counts the same population by a
    different route and knows nothing about this module, so a defect in
    `mode2_findings` breaks an identity instead of hiding inside it. The one
    place the two legitimately differ is a pair reachable BOTH ways, which the
    ceiling counts once per direction and the emitted frame counts once, because
    it is one write -- so `rows_add_child` is the ceiling's minus
    `both_directions`, and that is asserted rather than assumed.

    `attached` IS TAKEN FOR ONE COUNT, `rows_with_a_blocked_claim`, and it is
    taken rather than read back out of `evidence_summary`. A row whose claim the
    gate rejected is BY_PRECEDENT like any other and carries no column saying a
    claim was found and refused; the fact lives in the gate frame, so the census
    reads the gate frame. Recovering it by matching a sentence would make an
    operator-facing prose string load-bearing, where an edit to the wording
    silently zeroes a reported population.

    Nothing pools the two directions. The split, and the share of rows that would
    create a (type, assay) pair existing nowhere, are reported per direction,
    because ADD_PARENT is corroborated 88 times out of 88 over the 866 flags and
    ADD_CHILD 15 times out of 263.
    """
    add_parent = findings[findings.action == S.A_ADD_PARENT]
    add_child = findings[findings.action == S.A_ADD_CHILD]
    nowhere = findings[findings.registered_internal_assay_ids == ""]
    blocked = {
        (int(r.sample_id), int(r.internal_assay_id))
        for r, reaches in zip(attached.itertuples(index=False),
                              G.reaches_modes(attached))
        if not reaches
    }
    emitted = set(zip((int(s) for s in findings.sample_id),
                      (int(a) for a in findings.proposed_internal_assay_id)))
    out = {
        "rows": len(findings),
        "samples": findings.sample_id.nunique(),
        "rows_add_parent": len(add_parent),
        "samples_add_parent": add_parent.sample_id.nunique(),
        "rows_add_child": len(add_child),
        "samples_add_child": add_child.sample_id.nunique(),
        # the ceiling counts a both-ways pair in BOTH directions and this frame
        # emits it once, so their difference IS this population
        "rows_reachable_both_ways": ceiling["both_directions"],
        "rows_with_multiple_supports": int((findings.lineage_n_supports > 1).sum()),
        "rows_with_precedent": int(findings.precedent_rate.notna().sum()),
        "rows_without_precedent": int(findings.precedent_rate.isna().sum()),
        "rows_proposed_by_both": int((findings.proposed_by == BY_BOTH).sum()),
        "rows_with_a_blocked_claim": len(emitted & blocked),
        "rows_creating_an_unseen_pair_add_parent": int(
            (add_parent.type_registrations == 0).sum()),
        "rows_creating_an_unseen_pair_add_child": int(
            (add_child.type_registrations == 0).sum()),
        "rows_on_a_sample_registered_nowhere": len(nowhere),
        "samples_registered_nowhere": nowhere.sample_id.nunique(),
        "rows_without_a_sample_type": int(findings.sample_type.isna().sum()),
        "rows_without_a_samples_row": int(findings.project_ids.isna().sum()),
    }
    assert set(out) == set(MODE2_CENSUS_KEYS), "MODE2_CENSUS_KEYS is out of date"
    return {k: int(v) for k, v in out.items()}


def precedent_survival(
    findings: pd.DataFrame,
    thresholds=SURVIVAL_THRESHOLDS,
) -> pd.DataFrame:
    """How many rows carry a MEASURED rate at or above each threshold, per direction.

    REPORTING, AND IT GATES NOTHING. Every row `mode2_findings` emitted is
    emitted whatever this says: under the binding constraint a threshold orders
    what an operator reads first and grants no permission, and there is no
    autonomous write for it to gate. `mode2_findings` never reads
    `SURVIVAL_THRESHOLDS`, and a test asserts that off the source.

    THE TWO DIRECTIONS ARE NEVER POOLED, at any threshold. Measured 2026-08-17 at
    `rate >= 0.5`: 8,170 ADD_PARENT rows survive of 55,007, and 2,067 ADD_CHILD
    of 117,331 -- so the weak direction is cut to 1.8% of its ceiling and the
    strong one to 14.9%. One combined figure would present the mirror as carrying
    the evidence of the direction that is corroborated 88 times out of 88.

    A ROW WITH NO MEASURED RATE SURVIVES NOTHING, INCLUDING THRESHOLD 0.0, which
    is why 0.0 is in the default list: it is where absent evidence visibly fails
    to count as a rate of zero. `of_rows` rides beside every count as its
    denominator, for the reason `co_reg_pop` rides beside `co_reg_rate`.
    """
    rows = []
    for threshold in thresholds:
        for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
            direction = findings[findings.action == action]
            # `notna()` first and explicitly: a null rate compares False against
            # any threshold in pandas, so this is belt and braces -- but the
            # comparison alone would silently start counting nulls if the column
            # ever arrived as a float64 NaN-free cast.
            survives = direction[direction.precedent_rate.notna()
                                 & (direction.precedent_rate >= threshold)]
            rows.append({
                "threshold": threshold,
                "action": action,
                "rows": len(survives),
                "samples": survives.sample_id.nunique(),
                "of_rows": len(direction),
            })
    return pd.DataFrame(rows, columns=SURVIVAL_COLUMNS)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    """Report Modes 1 and 2 over the extract on disk. Read-only, no file written.

    Every input is left byte-identical and no artifact is produced: the
    `findings` file is stage C's unified output and belongs to the task that
    emits all the modes at once, so publishing a Mode-1-only version of it here
    would put two files with one name in the operator's directory.

    What this does produce is the census, printed, so that every figure this
    module's docstring states can be re-derived by running it. A number nobody
    can re-derive is what produced two conflicting readings of the Mode 2
    ceiling on this branch.

    PRECEDENT IS MINED HERE AND NOT READ FROM THE CSV STAGE B LEAVES IN THE SAME
    DIRECTORY -- which is why that name appears nowhere in this module as a path. The rules must describe the SAME edge frame the lineage
    index was built from, or a rule key this run constructs is looked up in a
    table mined from other data and the miss is reported as "no measured basis"
    -- absent evidence manufactured out of a stale file. Mining costs about three
    seconds, and re-derivability is this function's whole purpose.
    """
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
    gated = G.gate_claims(claims, vocab, type_reg, G.sample_type_index(nodes))
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
    m2 = mode2_findings(
        attached,
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=registered,
        rules=precedent_rules(B.mine_precedent(edges, membership, assays)),
        reg_projects=registration_projects(membership, assays),
        types=G.sample_type_index(nodes),
        type_reg=type_reg,
        titles=assay_titles(assays),
        projects=project_index(samples),
    )
    ceiling = L.mode2_ceiling(children_of, parents_of, registered)
    m2census = mode2_census(m2, ceiling, attached)

    print(f"MODE 2 over the DERIVED_FROM CEILING -- every (sample, assay) a "
          f"lineage neighbour makes available BEFORE precedent is read:")
    for k in MODE2_CENSUS_KEYS:
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
    for r in precedent_survival(m2).itertuples(index=False):
        print(f"  rate >= {r.threshold:<5} {r.action:<22} {r.rows:>8,} rows"
              f"  over {r.samples:>8,} samples   of {r.of_rows:,}")
    print(f"  {m2census['rows_without_precedent']:,} row(s) carry NO measured "
          "rate and survive no threshold, including 0.0: absent evidence is "
          "not a rate of zero")

    print("nothing was written: this run produced no file and no database "
          "change, and every row above is a proposal awaiting approval")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
