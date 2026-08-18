# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage C. Mode 1: a sample in NO assay. Mode 2 lives in `mode2.py`.

NOTHING DECIDES. EVERYTHING PROPOSES. Every row this module builds reaches the
operator as a proposal they approve or reject, no number in it authorises a
change, and no function here is named for a decision. It reads six parquet
files and one csv and writes nothing at all -- not even a findings file, which
belongs to the task that emits every mode at once.

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

"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import gate as G
from . import lineage as L
from .audit import registered_internal

# --- what produced a proposal ------------------------------------------------
#
# A closed family that enumerates itself, the way `PROVENANCES` and
# `GATE_OUTCOMES` do: a consumer must be able to ask "is this one of the four"
# without restating the four, because a restatement is what drifts.
#
# IT SAID "THREE" FOR ONE ROUND AFTER THE FOURTH MEMBER LANDED, one line above
# the tuple that already held four -- a restatement drifting from the thing it
# restates, in the block whose subject is that exact hazard. That is why the
# count is checked rather than written: `test_every_proposal_source_is_in_the_
# closed_family` derives the family from `vars()` and fails on a `BY_*` constant
# that never joins the tuple.
#
# `FINDING_COLUMNS.proposed_by` is spelled `proposed_` and not `decided_` under
# the binding constraint, and these values inherit that: the column header is
# where a reader forms their belief about what the pipeline already did.
#
# ALL FOUR ARE DECLARED HERE THOUGH MODE 1 EMITS ONLY THE FIRST. Tasks 6 and 8
# extend this module, and the alternative is each of them inventing its own
# spelling for one concept in one column -- two names one screen apart, which is
# this branch's signature defect. Declaring the family before its second producer
# exists is the same call `_schema` made for `MODE_3` and for
# `co_reg_registered_internal_assay_id`, and for the same reason: this is the
# cheapest it will ever be.
BY_CLAIM = "BY_CLAIM"            # the gated vocabulary claim alone -- Mode 1
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
PROPOSAL_SOURCES = (BY_CLAIM, BY_PRECEDENT, BY_BOTH, BY_LINEAGE_ONLY)

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
    m2 = M2.mode2_findings(
        attached,
        children_of=children_of, parents_of=parents_of, uuid_of=uuid_of,
        registered=registered,
        rules=M2.precedent_rules(B.mine_precedent(edges, membership, assays)),
        reg_projects=M2.registration_projects(membership, assays),
        types=G.sample_type_index(nodes),
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

    print("nothing was written: this run produced no file and no database "
          "change, and every row above is a proposal awaiting approval")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
