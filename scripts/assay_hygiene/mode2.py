# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Mode 2. A lineage NEIGHBOUR registers an assay this sample lacks.

SPLIT OUT OF `classify.py` BY TASK 8, AND THE SEAM IS MODE 2 ITSELF. That file
had grown to about 1,340 lines with Mode 1, Mode 2, the shared frame and the
indexes in it, and Task 8 adds the compatibility lane, the precedence and the
unified emitter on top. The seam the plan originally proposed -- `attach_gate`
plus the indexes into a `_frames.py` -- moves about 200 lines and leaves 1,100
behind; this one moves roughly half the file, and it moves the half that has
its own trigger, its own census, its own survival table and its own headline
figures.

WHAT STAYED BEHIND, AND WHY THE IMPORT POINTS THIS WAY. `classify.py` owns the
shared frame (`attach_gate`, `ATTACHED_COLUMNS`), the indexes every mode reads,
the `BY_*` proposal-source family -- whose first member is Mode 1's, so it
belongs to neither mode alone -- and `_registered_columns`, which Mode 2 and the
compatibility lane both call. So this module imports `classify` and `classify`
imports this one LAZILY, inside `main`, exactly as it already does for
`precedent` and `vocabulary`. A module-level import in both directions is a
cycle; the lazy one costs a single lookup per run.

NOTHING DECIDES. EVERYTHING PROPOSES. Every row this module builds reaches the
operator as a proposal they approve or reject, no number in it authorises a
change, and no function here is named for a decision.

THE TWO DIRECTIONS ARE NOT PEERS AND NO FIGURE MAY POOL THEM, and every
pre-precedent count here carries the word CEILING. Measured 2026-08-17 over
`DERIVED_FROM`: 55,007 ADD_PARENT rows and 117,463 ADD_CHILD, 172,338 in union
-- what lineage alone makes available BEFORE precedent is read, and before the
precedence contract in `classify.py` refuses any of them.
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from . import _schema as S
from . import gate as G
from . import lineage as L
from .classify import (BY_BOTH, BY_CLAIM_NO_RULE, BY_LINEAGE_ONLY,
                       BY_PRECEDENT, _registered_columns)
from .precedent import assay_index, membership_index

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
SURVIVAL_COLUMNS = ["threshold", "action", "rows", "samples", "rule_groups",
                    "of_rows"]

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
# partitions nothing: a rejected claim contributes NOTHING to `proposed_by`, so
# such a row carries whatever its precedent evidence earns -- `BY_PRECEDENT` on a
# hop with a rule, and `BY_LINEAGE_ONLY` on one without. This key exists so the
# rejected claim is counted rather than silently unused. 4,255 rows on the real
# extract carry one, and 2 of them are `BY_LINEAGE_ONLY`.
#
# THE COUNT DOES NOT MOVE WITH THAT SPLIT, because it is read off the GATE frame
# and never off `proposed_by`. This comment said "proposed BY_PRECEDENT like any
# other" for one round after `BY_LINEAGE_ONLY` landed, which was false on 2 rows
# -- the key's own justification describing a value the rows do not carry.
#
# THE TWO ACCEPTED-CLAIM KEYS ARE A PAIR AND NEITHER IS EXHAUSTIVE ALONE.
# `rows_proposed_by_both` was the only key counting "a gated claim contributed to
# this row's label", and it was exhaustive ONLY because `_proposal_source` raised
# on the rule-less half of that population -- the census surface inherited its
# completeness from an exception. That raise is gone as of 2026-08-21, so
# `rows_proposed_by_claim_no_rule` counts the other half. The population is 0
# today and goes non-zero under exactly the reachability rework this change
# enables, which is why the key lands NOW: a key added after the number moves
# cannot tell an operator whether it was ever zero.
#
#     accepted-claim rows = rows_proposed_by_both + rows_proposed_by_claim_no_rule
#
# The two are disjoint by construction -- one has a rule and one does not -- so
# each nests inside the precedent split, and a test asserts both containments
# rather than the sum alone, which would pass if the pair were swapped.
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
    "rows_proposed_by_claim_no_rule",
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

    THE ASSAY'S PROJECT LIST IS NOT A SUBSTITUTE. 75 of the 137 internal assay
    ids the assays frame carries span more than one project, up to seven, so
    "the project of assay X" is not single-valued and choosing one of them would
    key the wrong rule silently. The denominator is 137 and not 154, corrected
    2026-08-18: 154 is what `assay_index`'s MAP holds once the 17 junction-less
    records take a fallback id, and not one of those 17 can span a project. The
    154 in `assay_titles` one function up is a different sentence with a
    different numerator and is right as it stands. Measured 2026-08-17, only 1 of 214,124 (sample, internal
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


def _proposal_source(rule, claim, sample_id: int, assay_id: int) -> str:
    """Which evidence produced this proposal. One of `PROPOSAL_SOURCES`.

    THE FOUR COMBINATIONS OF (precedent rule, gated claim), ENUMERATED, because
    three of them were collapsed into two values for one review cycle:

        rule, claim   -> BY_BOTH           precedent proposed, the claim chose
        rule, -       -> BY_PRECEDENT      the rule alone
        -,    -       -> BY_LINEAGE_ONLY   the neighbour's registration alone
        -,    claim   -> BY_CLAIM_NO_RULE  the claim with no measured hop

    THE FOURTH IS NAMED AS OF 2026-08-21, and until then it raised. The refusal
    was the honest answer while the population was zero and the logic was
    stable, and it was neither once the reachability rework began. Measured
    2026-08-17 over the real extract, the combination occurs 0 times: all 10
    rows with no rule also carry no gated claim, and all 1,656 claim-backed rows
    have a rule. That is a property of THAT EXTRACT, not of this function --
    which rows reach a hop at all is exactly what the rework moves, so the first
    run under the new gate could produce one and abort on it, having already
    spent the whole detection pass. A named member costs nothing and cannot
    abort anything.

    `sample_id` AND `assay_id` ARE UNUSED AND STAY. They only ever built the
    exception message, but `mode2_findings` passes all four positionally and the
    next hand to touch this will want the pair identified when it adds a branch
    or a log line -- removing them costs a caller edit now to save nothing.

    `BY_CLAIM_NO_RULE` IS A FIFTH MEMBER AND NOT A WIDENING of either existing
    value, for the reason the raise itself gave: `BY_BOTH` is defined as
    "precedent proposed, the claim disambiguated" and would assert a precedent
    that is not there, and `BY_LINEAGE_ONLY` means the neighbour's registration
    ALONE and would hide the claim. Two meanings under one name is the defect
    this family exists to stop, and it is the defect that put `BY_LINEAGE_ONLY`
    here one combination over.
    """
    if rule is not None:
        return BY_BOTH if claim is not None else BY_PRECEDENT
    if claim is None:
        return BY_LINEAGE_ONLY
    return BY_CLAIM_NO_RULE


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

    `classification` is NEVER null, because the lineage test DID run and that is
    precisely what it establishes. It is `CLS_ABSENCE_LINEAGE` except where the
    pair is UNREACHABLE -- no sample of this type is registered in this assay
    anywhere, `type_registrations == 0` -- and there it is `CLS_UNREACHABLE`
    and `gate` reads `GATE_UNREACHABLE`. That is the gate's own rule, which
    `gate.gate_claims` has always applied to a CLAIM and which nothing applied
    to this lane until 2026-08-21: measured on the 2026-08-21 artifact tree,
    99,449 of the 167,454 emitted MODE_2 rows read a zero there. The row is
    still emitted and `classify.PRE_UNREACHABLE` gives it its own lane, because
    a proposal a curator never sees is not a proposal that was refused.

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
        # THE GATE'S OWN RULE, APPLIED TO THIS LANE AT LAST. `registrations == 0`
        # is what `gate.gate_claims` calls GATE_UNREACHABLE and BLOCKS a claim
        # on. `None` is a sample with no resolvable type -- nobody measured, so
        # nothing is asserted and the row passes. `== 0` and never `not
        # registrations`, which would read the None as a refusal and is the bug
        # class both audits of 2026-08-21 named.
        #
        # THE ROW IS STILL EMITTED. Classifying it is the whole point: 99,449 of
        # the 167,454 MODE_2 rows in the 2026-08-21 artifact are of this shape,
        # and a proposal that vanishes reads to a curator exactly like one that
        # was never generated. `classify.PRE_UNREACHABLE` gives them their own
        # lane and `findings_census` counts them.
        unreachable = registrations == 0
        row_gate = (S.GATE_UNREACHABLE if unreachable
                    else (claim.gate if claim is not None else None))
        row_class = (S.CLS_UNREACHABLE if unreachable else S.CLS_ABSENCE_LINEAGE)
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
            "classification": row_class,
            # the claim block, null wherever no GATED claim names this pair --
            # except `gate`, which an unreachable pair fills in from the lane's
            # own measurement whether or not a claim exists. See `row_gate`.
            "gate": row_gate,
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
            "proposed_by": _proposal_source(rule, claim, sample_id, assay_id),
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
    taken rather than read back out of `evidence_summary`. A rejected claim
    contributes nothing to `proposed_by`, so such a row carries whatever its
    precedent evidence earns -- `BY_PRECEDENT` with a rule, `BY_LINEAGE_ONLY`
    without, and 2 of the real extract's 4,255 are the latter -- and NO column
    says a claim was found and refused. The fact lives in the gate frame, so the
    census reads the gate frame, and the count is therefore unaffected by which
    proposal source the row ends up with. Recovering it by matching a sentence would make an
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
        # the rule-less half of the accepted-claim population, which used to be
        # unreachable because `_proposal_source` raised on it
        "rows_proposed_by_claim_no_rule": int(
            (findings.proposed_by == BY_CLAIM_NO_RULE).sum()),
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

    THE CURVE CROSSES OVER AT THE TOP AND THE REASON IS NOT WHAT IT LOOKS LIKE.
    At `rate >= 0.95` the WEAK direction survives 371 rows against the strong
    direction's 46. The obvious reading -- that `reverse_rate` reaches 1.0 easily
    on a thin denominator -- is MEASURABLY FALSE, and it was written into this
    task's report for one review cycle before being measured:

        rate >= 0.95     rows   median direction denominator   min   n <= 10
        ADD_PARENT         46                            919   919         0
        ADD_CHILD         371                         27,344   196         0

    The weak direction's survivors sit on denominators about THIRTY TIMES LARGER
    and not one of the 371 is thin. At rule level the same holds: the 15 reverse
    rules clearing 0.95 with a real gap run denominators 196..35,547 against the
    5 propagation rules' 105..7,177.

    WHAT THE ROW COUNTS ACTUALLY REFLECT IS HOP CONCENTRATION, which is why
    `rule_groups` is a column. Those 371 rows rest on 13 distinct evidence
    groups and ONE of them keys 170 rows by itself; the 46 rest on 2, one keying
    42. A row count counts affected samples, not independent evidence, and the
    two directions fan out differently -- so a survivor count is not a strength
    comparison in either direction, for this reason rather than the other one.

    `rule_groups` counts distinct `(n_both, n_child_only, n_parent_only)` triples
    and is therefore a LOWER BOUND on the number of precedent rules: two rules
    with identical counts collapse into one group here. The bias is toward
    reporting MORE concentration than there is, which is the safe direction for a
    number whose job is to discount a row count.

    None of this touches the demotion, which rests on the corroboration
    measurement -- 88 of 88 against 15 of 263 over the 866 flags -- and on the
    flagship hop. See the task report; Task 7's backtest is what settles the
    curve.
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
                # HOW MANY DISTINCT PIECES OF EVIDENCE THOSE ROWS REST ON. See
                # the docstring: 371 rows over 13 groups is a different claim
                # from 371 rows over 371.
                "rule_groups": len(survives[[
                    "precedent_n_both", "precedent_n_child_only",
                    "precedent_n_parent_only"]].drop_duplicates()),
                "of_rows": len(direction),
            })
    return pd.DataFrame(rows, columns=SURVIVAL_COLUMNS)
