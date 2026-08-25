# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The vocabulary gate. It runs before every mode and it writes nothing.

A claim is only as good as the term that produced it, and until 2026-08-17 no
stage tested the term. Increment 1's precedence ran lineage first, so vocabulary
defects were laundered into membership write proposals: measured on today's
extract, 11 A.FLOW samples registered in 31 Flow Cytometry ANALYSIS were filed
as future write candidates for 30 Flow Cytometry on a `Software: flowjo` family
that splits across three assays, and 13 A.SPC samples were filed against 130
Mass Spectrometry, an assay no A.SPC sample is registered in anywhere. Both are
the analysis-versus-measurement pair, and neither is a membership gap.

Three tests, each named for what it establishes, in a fixed order:

    reachability   is a sample of this TYPE ever registered in the claimed
                   assay, anywhere?              -> is the CLAIM credible at all
    coherence      does this term's family map to one assay?
                                                 -> is the MAPPING self-consistent
    floors         is the mapping backed by enough independent samples, at
                   enough purity?                -> is the MAPPING trustworthy

**Order is a contract.** Reachability first, because an incredible claim must
never reach a membership proposal, and because `gate` reports the most severe
outcome and that must be the test naming the claim's actual defect. Increment 1
had no reachability test at all, which is what produced the 24 above.

**ONLY TWO OF THE THREE BLOCK, and the split is the design.** See
`BLOCKING_OUTCOMES` and `blocks_mode`, which is the single place that rule lives
and the one every consumer must call:

    BLOCKING      reachability, coherence. Neither has a tuned number in it.
                  Either a sample of this type is registered in the claimed
                  assay somewhere or it is not; either the term family maps
                  coherently or it does not. A claim failing one reaches no mode.
    NON-BLOCKING  the support and purity floors. These ARE tuned numbers. They
                  are computed, recorded on the row and carried onto the finding
                  so an operator sees weak evidence and reads the strongest rows
                  first. They rank and triage. They do not decide.

The binding constraint is "nothing decides, everything proposes", and a
threshold that blocks is a threshold that decides. The spec also holds that a
threshold is an OUTPUT of a backtest curve rather than a number chosen ahead of
one, and both floors below were chosen ahead of one. The asymmetry of the two
errors settles it: a weak claim reaching a mode costs an operator a row they
reject, which is recoverable by reading, while a correct claim silently stopped
by an uncalibrated number is invisible to them -- and invisible is the failure
this whole increment is a response to.

So a claim carries a SET of outcomes and not one. `gate` is the most severe,
`gate_failures` is all of them, and whether the claim proceeds is neither of
those: it is `reaches_modes`. Comparing `gate` to `GATE_PASS` to decide passage
is wrong and will silently drop 18,652 claims.

The gate is not a mode. It proposes no membership change, every claim it rules
on is reported in `vocabulary-defects.csv` and routed to
`/curate-assay-vocabulary`, and the blocked subset additionally reaches no mode.
Nothing here writes to the database; it reads parquet and csv off disk and
writes one csv.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.gate

RE-MEASURED 2026-08-25 over the real extract at the defaults below, every
figure re-derived rather than adjusted.

Over all 130,764 claims, by most severe outcome: 107,559 PASS, 18,652
GATE_LOW_SUPPORT, 4,553 GATE_UNREACHABLE, 0 GATE_INCOHERENT. **4,553 are
BLOCKED (3.5%) and 126,211 reach a mode, 18,652 of them carrying a recorded
floor failure.**

THE DENOMINATOR MOVED AND SO DID EVERY NUMERATOR. It read 138,007 / 107,424 /
25,974 / 4,554 / 55 / 4,609 / 133,398 until 2026-08-25, measured 2026-08-17 and
never re-derived after the operator retired four vocabulary terms on 2026-08-21.
Correcting the denominator alone would have been worse than leaving it: not one
of the seven survived.

GATE_INCOHERENT NOW FIRES ON NOTHING, and that is a finding rather than a
rounding. `incoherent_families` returns `{}` on the shipped vocabulary -- no
term family maps to two assays any more -- so the coherence test is a guard
against a state the data is not currently in, and the 55 it once caught are
gone with the retired terms. It is kept because the state is reachable, not
because it is occupied.

Over the 866 flags increment 1 reported: 225 PASS, 598 GATE_LOW_SUPPORT, 31
GATE_UNREACHABLE, 12 GATE_INCOHERENT. **43 are BLOCKED and 823 reach a mode**,
598 of those carrying a recorded floor failure. Under an earlier revision where
the floors blocked, 641 of the 866 were stopped; that is the change this split
made and it is why it was made. THAT PARAGRAPH IS HISTORY AND IS SCOPED TO
INCREMENT 1'S ARTIFACT. `audit.audit_contradictions` re-derives that population
at 585 on this extract; see `docs/findings/2026-08-25-the-prose-figure-census.md`.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S
from .precedent import assay_index

# --- the two floors ----------------------------------------------------------
#
# THEY LIVE HERE AND NOT IN `_schema`, deliberately. `_schema` already declares
# a co-registration reporting band of 30 that counts SAMPLES OF A TYPE and sizes
# a co-registration population, and a second floor beside it under a similar
# name is how the units confusion below happened the first time -- a test in
# `tests/test_assay_hygiene_schema.py` pins that those two names appear in no
# module here but `_schema.py` and `compatibility.py`, which is why this comment
# does not spell either. THIS MODULE IS NOT AN APPROVED READER OF THEM and the
# test would fail if it became one. These two floors are the gate's, and nothing
# else reads them.
#
# `MIN_VOCAB_SAMPLES` COUNTS DISTINCT SAMPLES. It reads `VOCAB_COLUMNS.n_samples`
# and never `VOCAB_COLUMNS.support`, and the choice is material rather than
# cosmetic. `support` counts labelled EDGES and one sample fans out to many, so
# an edge floor measures fan-out and not evidence: measured 2026-08-17 on the
# real extract, 50 of the 736 learned terms rest on exactly ONE sample and 21 of
# those clear an edge floor of 30 -- `Software: matlab` reads support 132 from
# one sample, `Type: github` support 73 from one. The question this floor asks
# is how many INDEPENDENT curator decisions back a mapping that is about to
# author a membership proposal, and that is a count of samples.
#
# `vocabulary.learn_vocabulary` keeps its own `min_support=3` in EDGES and that
# is not changed: it is an EXISTENCE floor (does this term appear at all), every
# figure this design rests on was measured against it, and moving it would
# invalidate the measurement rather than improve it. This is a TRUST floor. Two
# different questions, two different units, and the value 3 means "three
# independent samples" here and "three labelled edges" there.
#
# The value: 3 rejects 90 of 736 vocabulary rows and 2,119 of 130,764 claims
# (re-measured 2026-08-25; it read 83 and 2,131 of 138,007 before the four
# vocabulary retirements), and 4 of increment 1's 866 flags. It is deliberately the weakest of the three tests, because
# held-out accuracy shows NO penalty for thin support -- scored by sample over
# 333,717 test edges, terms resting on 2 samples predict at 99.8% and terms
# resting on 100+ at 93.6%. The floor is therefore justified on provenance and
# not on accuracy: a mapping backed by one sample is one curator's one row, which
# is indistinguishable in kind from a `proposed` guess, and the package already
# caps those below the audit floor.
MIN_VOCAB_SAMPLES = 3

# `MIN_VOCAB_PURITY` is the discriminating floor and it IS anchored on a
# measurement, the one `run_evidence.purity_band_accuracy` publishes. Held out
# by sample over 333,717 test edges: terms below 0.75 purity predict at 68.1%,
# terms in 0.75-0.90 at 81.4%, terms at or above 0.90 at 99.9%. So a mapping
# under it is right about two times in three, and a proposal resting on one is
# marked as such for the operator reading it.
#
# It is what MARKED `Type: Illumina Library` -> 24 DNA Extraction at purity
# 0.707 over 2,210 samples, which drove 212 of increment 1's 250
# ABSENCE_COMPAT flags and 269 of the 866. No support floor in either unit
# touched that row. Note MARKED and not stopped: those 269 claims still reached
# their mode and arrived carrying `GATE_LOW_SUPPORT` and the purity that earned
# it. THE WORKED EXAMPLE IS NOW HISTORY: as of 2026-08-25 that term carries a
# null `internal_assay_id`, support 0 and purity 0.0 -- it was one of the four
# the operator retired -- so it maps nothing and marks nothing. The mechanism it
# illustrates is unchanged and the floor still has that job.
#
# THIS FLOOR IS UNCALIBRATED, AND IT IS A REPORTING BAND UNTIL IT IS NOT.
# It does not block. `blocks_mode` excludes `GATE_LOW_SUPPORT`, so a claim under
# this floor is RECORDED as weak and still reaches its mode, and the number
# ranks a curator's reading order rather than granting permission. NOTHING IS
# GATED ON AN UNCALIBRATED NUMBER, which is what makes shipping it uncalibrated
# survivable.
#
# The deferral is not caution, it is a measurement. `evidence-report.md` scores
# this axis against a PEER-REGISTRATION one -- of every sample carrying a term,
# how many are registered in the assay it names -- and finds they correlate at
# only 0.43 and that a 0.75 purity floor sorts 151 of the 866 THE WRONG WAY. It
# would discard `Type: Blood`'s 97 flags at 98.7% peer registration, the
# cleanest gaps in the set, while keeping `Histopathology`'s 44 at 71.1%. Peer
# rate is the question a curator is actually asking and it is not computable in
# this stage; it needs the co-registration layer, which now exists in
# `compatibility.co_registration`.
#
# THE RE-DERIVATION IS DEFERRED TO INCREMENT 3 AND HAS NOT HAPPENED. An earlier
# version of this comment said the co-registration task would do it. It did not,
# and the commitment is withdrawn here rather than left standing, because code
# naming an unkept promise is worse than code saying "not yet calibrated".
#
# The deferral is now a ruling and not a slip. Under the split above this floor
# is NON-BLOCKING, so re-deriving it changes only which rows are MARKED weak and
# never which rows reach a mode -- that makes it a reporting refinement, and its
# right home is the increment where an operator actually reads the approval
# surface. Until then: 0.75 IS A NUMBER SOMEONE CHOSE, it is not the output of
# any curve, and every row it marks says so.
#
# Blocking on the two floors would stop 22,147 of the 130,764 claims -- purity
# on an axis measured to be the wrong one -- silently, ahead of every mode.
# (Re-measured 2026-08-25; it read 30,583 of 138,007. It would also have
# stopped 641 of increment 1's 866 flags, which is scoped to that artifact.)
MIN_VOCAB_PURITY = 0.75


# --- output contracts --------------------------------------------------------
#
# `vocab_*` prefixes match `FINDING_COLUMNS`, which borrows the same three
# columns under the same names; every borrowed column is prefixed with the frame
# it came from so a reader can tell `vocab_purity` from a co-registration rate.
#
# `vocab_n_samples` is carried even though `FINDING_COLUMNS` does not have it,
# because the support floor READS it. A gate frame that printed only
# `vocab_support` beside a `GATE_LOW_SUPPORT` ruling would show the reader a
# number the ruling never looked at -- 2,210 edges beside a rejection decided on
# 1 sample -- and the ruling would be unauditable from its own artifact.
#
# `type_registrations` is the evidence behind the reachability ruling: how many
# distinct samples of this type are registered in the claimed assay. It rides
# beside `gate` for the reason `co_reg_pop` rides beside `co_reg_rate` in
# `FINDING_COLUMNS`: the check on a number belongs next to the number.
#
# `family_internal_assay_ids` holds IDS and not titles. A title is display and
# never identity here as everywhere: 124 seek assay ids collide numerically with
# genuine internal ids under 122 different titles.
# `gate` is the MOST SEVERE outcome and `gate_failures` is ALL of them,
# `;`-joined in the order the tests run. The pair exists because a claim can
# fail a blocking test and a tuned one at once -- 3,495 of the 130,764 do, and
# none fails both blocking tests today -- and a single column collapsing to
# whichever fired first would lose the other. On
# the real extract that loss runs in the dangerous direction: it would hide a
# recorded weakness behind a block, so the finding row an operator reads would
# show a clean mapping for a claim whose mapping is not clean.
#
# `gate_failures` is EMPTY for a clean claim rather than holding `GATE_PASS`. A
# pass is the absence of a failure, and a list of failures containing "passed"
# is a category error a consumer filtering on membership would trip over.
#
# NEITHER COLUMN DECIDES PASSAGE. `reaches_modes` does, through `blocks_mode`.
# `gate == GATE_PASS` is not that test and using it drops 18,652 claims the
# design intends to propose on. (Re-measured 2026-08-25; it read 25,974 before
# the four vocabulary retirements of 2026-08-21.)
GATE_COLUMNS = [
    "sample_id", "uuid", "sample_type",
    "internal_assay_id", "internal_assay_title",
    "source_field", "raw_value",
    "gate", "gate_failures", "gate_reason",
    "vocab_support", "vocab_n_samples", "vocab_purity", "vocab_provenance",
    "term_family", "family_internal_assay_ids",
    "type_registrations",
]

# One row per DEFECT, which is not one row per claim and not one row per
# vocabulary row either. `GATE_INCOHERENT` and `GATE_LOW_SUPPORT` are properties
# of a mapping, so they key on `(source_field, raw_value)` and carry no type.
# `GATE_UNREACHABLE` is a property of a CLAIM -- the same term is credible for
# one sample type and not another -- so it keys on
# `(source_field, raw_value, sample_type, internal_assay_id)` and `sample_type`
# is populated.
#
# NOTHING HERE CAN EXPRESS A MEMBERSHIP CHANGE, by construction and by test.
# There is no `proposed_*`, no `mode` and no `action`: the gate produces no
# membership change, so its artifact carries no column capable of stating one,
# and the file routes to `/curate-assay-vocabulary` rather than to a mode.
#
# The four evidence columns keep the `vocab_` prefix they carry in
# `GATE_COLUMNS` -- one concept, one name, across both of this module's frames.
# It also separates them from the two CLAIM-side counts beside them:
# `vocab_n_samples` is how many distinct samples back the MAPPING and
# `n_samples_affected` is how many samples' claims this run gated on it. Those
# are different numbers under names one column apart, which is this package's
# signature hazard, so the prefix is doing real work rather than matching a
# convention.
#
# `blocks_modes` is derived from `blocks_mode(defect)` at write time and is the
# column a curator triages on: a blocking defect stopped claims from reaching a
# mode and a non-blocking one only annotated them. Both are still defects and
# both are still theirs to fix, which is why both are in the file.
DEFECT_COLUMNS = [
    "defect", "blocks_modes", "source_field", "raw_value", "sample_type",
    "internal_assay_id", "internal_assay_title",
    "vocab_support", "vocab_n_samples", "vocab_purity", "vocab_provenance",
    "term_family", "family_internal_assay_ids",
    "n_claims", "n_samples_affected", "example_uuids", "detail",
]


# --- type indexes ------------------------------------------------------------


def sample_type_index(nodes: pd.DataFrame) -> dict[str, str]:
    """uuid -> sample type, from the graph's node index.

    KEYED ON UUID AND NOT `sample_id`, which is the same ruling
    `audit.audit_contradictions` made and for the same measured reason:
    `sample_id` is not unique in `nodes` -- 86 sample_ids carry two node rows
    under two uuids and 51 of those pairs disagree on type (165987 is both
    MUS-250620SAR-2 and RNA-250620SAR-2) -- while uuid is unique over all
    177,392 rows. A sample_id-keyed dict resolves the disagreements by
    last-write-wins over a frame whose row order is not stable across extracts.

    The type is read off `nodes` rather than derived from the uuid prefix, which
    looks equivalent and is not: measured on the real extract, 5 of the 177,392
    uuids disagree with their own node's type, including four A.SPTX-prefixed
    uuids typed A.MSP.
    """
    return {
        str(u): str(t)
        for u, t in zip(nodes.uuid, nodes.type)
        if pd.notna(u) and pd.notna(t)
    }


def sample_type_sets(nodes: pd.DataFrame) -> dict[int, frozenset[str]]:
    """sample_id -> the SET of types its node rows carry.

    THE SECOND INDEX OFF `nodes`, AND THE PAIR IS NOT A DUPLICATION.
    `sample_type_index` is keyed on UUID and returns ONE type, because uuid is
    unique over all 177,392 node rows. This one is keyed on SAMPLE_ID and
    returns a SET, because sample_id is NOT unique there: 86 sample_ids carry
    two node rows under two uuids and 51 of those pairs disagree on type. The
    two questions are different -- "what type is this uuid" against "what types
    does this id answer to" -- and neither is derivable from the other, since
    the uuid-keyed map has thrown the id away.

    IT EXISTS AS A FUNCTION BECAUSE TWO CALLERS NEED IT.
    `type_registration_index` built this map inline until 2026-08-17, when
    `compatibility.co_registration` needed the identical map to count the
    NUMERATOR of a rate whose denominator is a `type_registration_index` cell.
    A second copy would be two definitions of "what type is this sample" one
    module apart, and the failure mode is arithmetic rather than an error: a
    numerator counting a dual-typed sample once against a denominator counting
    it twice halves a rate silently, and the reverse pushes it over 1.0. So the
    map is defined once, here, and both read it.

    A DUAL-TYPED SAMPLE APPEARS UNDER BOTH TYPES, which is the ruling
    `type_registration_index` documents and the reason its value is a set. Rows
    with a null sample_id or a null type are skipped; a sample with no node row
    at all is absent from this map entirely and is reported by
    `untyped_registration_samples`.

    Returns a PLAIN dict, for the reason `audit.registered_internal` gives:
    a `defaultdict` answers `types[999]` by CREATING the entry, so `999 in
    types` becomes true of every sample ever asked about. Callers use
    `.get(sid, frozenset())`.
    """
    acc: dict[int, set[str]] = {}
    for sid, t in zip(nodes.sample_id, nodes.type):
        if pd.notna(sid) and pd.notna(t):
            acc.setdefault(int(sid), set()).add(str(t))
    return {sid: frozenset(v) for sid, v in acc.items()}


def untyped_registration_samples(
    membership: pd.DataFrame,
    nodes: pd.DataFrame,
) -> list[int]:
    """Registered samples with no node row, sorted. Nothing is dropped silently.

    Such a sample carries no type, so its registrations can contribute to no
    (type, assay) cell of `type_registration_index` and are of necessity absent
    from it. This package's house rule is that every excluded row is counted and
    reported by name, so they are returned rather than skipped inside the index.

    Measured on the real extract 2026-08-17: 194 samples over 210 of the 214,296
    membership rows, which is 0.10% of the registrations. That number is the one
    to watch -- reachability gets more permissive as it grows, never less, so a
    silent increase would loosen the gate rather than break it.
    """
    typed = {int(s) for s in nodes.sample_id if pd.notna(s)}
    return sorted({int(s) for s in membership.sample_id} - typed)


def type_registration_index(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
) -> dict[tuple[str, int], int]:
    """(sample_type, internal_assay_id) -> distinct samples of that type there.

    The reachability evidence. A claim naming a pair absent from this index is
    naming an assay no sample of its type has ever been registered in, anywhere
    in the database, which makes the claim incredible whatever the term's
    support.

    THE THIRD ARGUMENT IS `nodes` AND NOT `samples`, which is a deliberate
    departure from the interface as briefed. `SAMPLE_COLUMNS` carries no type
    column at all, and deriving one from the uuid prefix is wrong on 5 of the
    177,392 nodes (see `sample_type_index`). `nodes` is the frame documented as
    the graph's uuid -> (sample_id, type) index and is the frame
    `audit.audit_contradictions` already takes for the same purpose.

    Registrations are crossed to the internal namespace through
    `precedent.assay_index`, the package's single definition of "which internal
    assay is this seek assay", including the fallback for the 17 junction-less
    records. `membership.assay_id` is a seek `assays.id` and a claim speaks a
    dmac internal id; the two overlap numerically and share no meaning.

    "Registered" is ANY MEMBERSHIP, the definition `audit.registered_internal`
    uses. The MAPPABLE-only set is 82 samples smaller and the two have been
    confused once already in this project.

    The value counts DISTINCT SAMPLES and not membership rows, so a sample
    registered in one assay through two seek records counts once.

    RAISES on a membership row naming an assay absent from the assays frame,
    following `precedent.mine_precedent` and `audit.registered_internal`, which
    both raise rather than skip. Skipping here is a one-directional harm: it can
    only SHRINK a cell, and a cell shrinking to zero turns a credible claim into
    `GATE_UNREACHABLE` -- a finding deleted silently, reported as a vocabulary
    defect that is not one.

    The sample-to-type map comes from `sample_type_sets`, which is shared with
    `compatibility.co_registration` so the NUMERATOR of a co-registration rate
    and the DENOMINATOR it divides -- this cell -- cannot type a sample
    differently.

    A sample with two node rows disagreeing on type counts under BOTH types, and
    that direction is chosen on purpose. 20 of the 214,296 membership rows are
    affected. Counting it under one type would make reachability depend on a row
    order that is not stable across extracts; counting it under both can only
    ADD to a cell, and adding to a cell can only ever turn a rejection into a
    pass. The gate refuses to assert what is not established, which is the same
    direction `audit.audit_contradictions` refuses a contradiction it cannot
    resolve.
    """
    ainfo = assay_index(assays)
    unknown = sorted({int(a) for a in membership.assay_id} - set(ainfo))
    if unknown:
        raise ValueError(
            f"membership registers samples in {len(unknown)} assay(s) absent "
            f"from the assays frame: {unknown}. Those registrations cannot be "
            "crossed to the internal namespace, and skipping them would shrink "
            "a reachability cell -- which reads as a vocabulary defect, not as "
            "an error. Re-extract so the two frames agree."
        )

    types = sample_type_sets(nodes)

    cells: dict[tuple[str, int], set[int]] = defaultdict(set)
    for sid, aid in zip(membership.sample_id, membership.assay_id):
        sid = int(sid)
        iaid = ainfo[int(aid)][1]
        for t in types.get(sid, ()):
            cells[(t, iaid)].add(sid)
    return {k: len(v) for k, v in cells.items()}


# --- term families -----------------------------------------------------------
#
# A VERSION token: `10`, `10.3`, `3.0`, `v2`, `v10.8.1`, `10x`. The trailing
# single letter is what catches `v10.8.1a` and `10x` without admitting a word.
_VERSION_TOKEN = re.compile(r"^v?\d+(\.\d+)*[a-z]?$")
# ...and the words that introduce one.
_VERSION_WORDS = {"version", "ver", "v"}


def term_stem(value: str) -> str:
    """A normalised term with its trailing VERSION suffix removed.

    THE RULE STRIPS A VERSION AND NOTHING ELSE, and the narrowness is the whole
    design. Two wider rules were measured against the real vocabulary first:

      substring     collapses `chip seq` -> 12 with `chipper` -> 11, reporting a
                    family that is not one. This is the negative case
                    `_schema.make_fixture` carries.
      leading token collapses `Type: total rna` -> 61 with `Type: total igg` ->
                    155. Measured over the 736 learned terms it manufactures 27
                    incoherent families spanning 75 rows and 14,957 claims,
                    including all 204 `total RNA` rows the design reads as
                    ordinary absences, and `confocal ihc` against `confocal
                    laser scanning microscopy`, and six unrelated Bruker
                    instruments.

    The version rule finds exactly ONE incoherent family on the real vocabulary,
    `Software: flowjo` -> {30, 31, 153} over six terms, which is the family the
    design named. It is a precision instrument and it will miss defects of other
    shapes -- `zeiss z.1 observer` -> 75 against `zeiss z1 observer` -> 145 is
    one product under two spellings and two assays, and this rule does not see
    it. A gate that catches what it claims to catch and says what it misses is
    worth more than one that reports 27 families of which 26 are wrong.

    A term that is ENTIRELY version tokens (`10.3`) keeps its whole value: it
    has no stem to take, and returning the empty string would collapse every
    such term in a field into one family.
    """
    tokens = value.split()
    end = len(tokens)
    while end and (_VERSION_TOKEN.match(tokens[end - 1])
                   or tokens[end - 1] in _VERSION_WORDS):
        end -= 1
    return " ".join(tokens[:end]) if end else value


def _maps_an_assay(row) -> bool:
    """Is this vocabulary row a MAPPING? ONE POLICY, declared once.

    THE POLICY IS WHAT WAS DUPLICATED, NOT THE LOOP. This module built the
    vocabulary index in three places and they DISAGREED about nulls:
    `term_families` skipped a row whose `internal_assay_id` is null, while the
    indexes in `gate_claims` and `vocabulary_defects` kept it. That asymmetry
    is the defect -- one of the two survivors feeds `int(row.internal_assay_id)`
    in `vocabulary_defects`, which raises `ValueError` on a null, so the same
    frame was safe through one reader and a crash through another.

    Unreachable on the 2026-08-14 extract: 0 of 736 vocabulary rows carry a
    null. It is fixed as a POLICY rather than as a guard at the crash site
    because the next reader would have made the same choice independently and
    had no way to know which of the three it was agreeing with.

    A row naming no assay is not a mapping: it cannot support a claim and
    cannot be a defect's target. Skipping it everywhere makes `gate_claims`
    raise its named "term with no vocabulary row" error rather than gate a
    claim against a row with no assay -- a loud failure replacing a silent one,
    which is this package's stated preference.
    """
    return bool(S.normalise_value(row.raw_value)) and not pd.isna(
        row.internal_assay_id)


def _vocab_index(vocabulary: pd.DataFrame) -> dict[tuple[str, str], object]:
    """(source_field, normalised value) -> the vocabulary row.

    Last row wins on a duplicate key, which is what both call sites did before
    they shared this. `merge_vocabulary` is what guarantees the key is unique.
    """
    return {(str(r.source_field), S.normalise_value(r.raw_value)): r
            for r in vocabulary.itertuples(index=False)
            if _maps_an_assay(r)}


def term_families(vocabulary: pd.DataFrame) -> dict[tuple[str, str], list]:
    """(source_field, stem) -> the vocabulary rows sharing it.

    Keyed on the FIELD as well as the stem. The same string names different
    assays under different fields -- `claims.claim_index` keys on the pair for
    exactly that reason -- and a stem-only family would collide them and report
    a split that is an artifact of the grouping.

    Values are normalised through `_schema.normalise_value` before the stem is
    taken, because that is what every lookup in this package compares.
    """
    out: dict[tuple[str, str], list] = defaultdict(list)
    for r in vocabulary.itertuples(index=False):
        if not _maps_an_assay(r):
            continue
        out[(str(r.source_field),
             term_stem(S.normalise_value(r.raw_value)))].append(r)
    return dict(out)


def incoherent_families(vocabulary: pd.DataFrame) -> dict[tuple[str, str], list[int]]:
    """The families mapping to more than one assay, with the assays they name.

    REPORTED, NEVER RESOLVED. Which of `flowjo` -> 30, `flowjo v10.8.1` -> 31
    and `flowjo 10.3` -> 153 is right is a curator's ruling and there is no
    evidence in this layer that settles it: all three are learned from
    curator-labelled edges, so picking the modal one would overwrite two
    curators with a third.
    """
    return {
        key: sorted({int(r.internal_assay_id) for r in rows})
        for key, rows in term_families(vocabulary).items()
        if len({int(r.internal_assay_id) for r in rows}) > 1
    }


# --- the gate ----------------------------------------------------------------


# The two outcomes that STOP a claim. Both rest on evidence with no tuned number
# in them, which is the whole criterion for membership here: either a sample of
# this type is registered in the claimed assay somewhere or it is not, and
# either the term family maps coherently or it does not. Neither answer moves if
# someone picks a different constant.
#
# `GATE_LOW_SUPPORT` is deliberately ABSENT. It is the outcome of two tuned
# floors, and under "nothing decides, everything proposes" a threshold ranks and
# triages -- it does not grant permission. See the module docstring for the
# argument and `MIN_VOCAB_PURITY` for the measurement showing this particular
# number is not yet calibrated on the right axis.
#
# This is a strict subset of `_schema.GATE_REJECTIONS`, which is the set of
# non-PASS outcomes and NOT the set that stops a claim. The two were the same
# thing for one revision of this module and are not any more.
BLOCKING_OUTCOMES = (S.GATE_UNREACHABLE, S.GATE_INCOHERENT)


def blocks_mode(outcome: str) -> bool:
    """Does this outcome stop a claim reaching Mode 1 or Mode 2?

    THE SINGLE PLACE THAT RULE LIVES. Tasks 3 through 9 call this rather than
    re-deriving which outcomes block; a second copy of the rule is the same class
    of bug as a second definition of "registered", which produced 13 spurious
    findings earlier in this increment.

    A MEMBERSHIP test against a closed tuple rather than a comparison against
    `GATE_PASS`, for the reason `EVIDENCE_PROVENANCES` gives against
    `p != P_PROPOSED`: a fifth outcome added later is admitted by the tuple
    rather than by every consumer remembering to extend an inequality, and the
    default for anything unanticipated is NON-blocking, which is the direction
    that fails visibly.
    """
    return outcome in BLOCKING_OUTCOMES


def reaches_modes(gated: pd.DataFrame) -> pd.Series:
    """Which gated rows are allowed to reach Mode 1 or Mode 2.

    Read off `gate_failures`, the COMPLETE set, and never off `gate`, which
    holds only the most severe. A claim failing a tuned floor and nothing else
    reaches its mode carrying a recorded weakness; a claim failing reachability
    or coherence does not, whatever else it also failed.

    Recomputed through `blocks_mode` on every call rather than read from a
    stored boolean, so there is exactly one definition of blocking in the
    package and no column that can drift out of agreement with it.
    """
    return ~gated.gate_failures.map(
        lambda s: any(blocks_mode(o) for o in str(s).split(";") if o))


def gate_claims(
    claims: pd.DataFrame,
    vocabulary: pd.DataFrame,
    type_reg: dict[tuple[str, int], int],
    types: dict[str, str],
    min_samples: int = MIN_VOCAB_SAMPLES,
    min_purity: float = MIN_VOCAB_PURITY,
) -> pd.DataFrame:
    """One row per claim, in the claims frame's own order, with its outcome.

    THE SUPPORT FLOOR IS `min_samples` AND IT COUNTS DISTINCT SAMPLES. The brief
    named this parameter `min_support`; it is renamed because it reads
    `VOCAB_COLUMNS.n_samples` and never `VOCAB_COLUMNS.support`, and a parameter
    named for the column it does not read is this branch's signature defect. See
    `MIN_VOCAB_SAMPLES` for the measurement behind the choice and behind the
    value.

    `types` is a fourth argument the briefed interface did not carry, and it is
    needed because `CLAIM_COLUMNS` has no `sample_type`: reachability is a
    question about the sample's TYPE, and the claims frame cannot answer it. It
    is keyed on uuid for the reason `sample_type_index` gives.

    Every test runs and every failure is recorded. NOTHING SHORT-CIRCUITS:

      1. reachability       -> GATE_UNREACHABLE   BLOCKS
      2. curator provenance -> suppresses 3 and 4
      3. term family        -> GATE_INCOHERENT    BLOCKS
      4. either floor       -> GATE_LOW_SUPPORT   recorded, does not block

    `gate` holds the first failure in that order, which is the most severe;
    `gate_failures` holds all of them; and passage is `reaches_modes`, which is
    neither. Re-measured 2026-08-25: 3,495 of the 130,764 claims fail a
    blocking test AND a floor, and an earlier revision reported only the first
    -- so the finding row for a blocked claim showed a clean mapping for a
    mapping that is not clean.

    The curator exemption sits BELOW reachability and above everything else, and
    that placement is the ruling rather than an accident. A human decision
    outranks the data about what a TERM means, which is what the family test and
    both floors judge. It says nothing about whether a sample of this type
    belongs in that assay, which is a fact about the database's registrations;
    exempting a curator row there would let one ruling authorise a proposal for
    a (type, assay) pair that exists nowhere, which is the 13 A.SPC shape this
    gate was built for.

    THE GRAIN IS THE CLAIMS FRAME'S, one row per (sample, proposed assay), and
    that carries a limitation worth naming. `claims.sample_claims` collapses a
    sample's several fields onto one row per assay and reports the first BACKED
    source in `CLAIM_FIELDS` order, so a claim backed by two vocabulary rows is
    gated on the one the frame names and not on both. Measured on the real
    extract 2026-08-25, 6,677 of the 130,764 claims pass on their
    representative row while another row also backing that same assay would
    have been rejected. The
    defective row is still reported in `vocabulary-defects.csv`, which is keyed
    on the vocabulary and not on claims, so nothing is hidden -- but a claim
    corroborated by a clean row and a defective one is admitted, and closing
    that would mean gating on the metadata rather than on the claims frame.

    RAISES rather than skipping on a claim whose term has no vocabulary row or
    whose uuid has no type, following `precedent.mine_precedent` and
    `audit.registered_internal`. Both are silent-wrong-answer failures: a
    skipped claim disappears from Modes 1 and 2 with no count anywhere, and an
    untyped claim cannot be tested for reachability and would read as a PASS,
    which is the laundering this gate exists to stop. 0 of the 130,764 claims
    hit either today.

    Neither input frame is mutated.
    """
    index = _vocab_index(vocabulary)
    incoherent = incoherent_families(vocabulary)

    missing_terms, missing_types = [], []
    for c in claims.itertuples(index=False):
        key = (str(c.source_field), S.normalise_value(c.raw_value))
        if key not in index:
            missing_terms.append(f"{key[0]}/{c.raw_value!r}")
        if str(c.uuid) not in types:
            missing_types.append(str(c.uuid))
    if missing_terms:
        raise ValueError(
            f"{len(missing_terms)} claim(s) name a term with no vocabulary row: "
            f"{'; '.join(sorted(set(missing_terms))[:10])}"
            + (" ..." if len(set(missing_terms)) > 10 else "")
            + ". A claim cannot be gated on a mapping that is not there, and "
            "skipping it would drop the row from Modes 1 and 2 with no count "
            "anywhere. Re-run the vocabulary stage against these claims."
        )
    if missing_types:
        raise ValueError(
            f"{len(missing_types)} claim(s) carry a uuid with no node row, so "
            f"their sample type is unknown: {sorted(set(missing_types))[:10]}"
            + (" ..." if len(set(missing_types)) > 10 else "")
            + ". Reachability is a question about the TYPE, so an untyped claim "
            "cannot be tested and would read as a PASS. Re-extract so nodes and "
            "claims agree."
        )

    rows = []
    for c in claims.itertuples(index=False):
        row = index[(str(c.source_field), S.normalise_value(c.raw_value))]
        stype = types[str(c.uuid)]
        iaid = int(c.internal_assay_id)
        registrations = int(type_reg.get((stype, iaid), 0))

        value = S.normalise_value(c.raw_value)
        family_key = (str(c.source_field), term_stem(value))
        family = incoherent.get(family_key)
        support = int(row.support) if pd.notna(row.support) else 0
        n_samples = int(row.n_samples) if pd.notna(row.n_samples) else 0
        purity = float(row.purity) if pd.notna(row.purity) else 0.0
        provenance = str(row.provenance)

        thin = n_samples < min_samples
        impure = purity < min_purity

        # EVERY failing test is recorded, in the order the tests run, and the
        # loop no longer stops at the first. A claim can be unreachable AND rest
        # on a thin mapping, and collapsing to the first would tell an operator
        # reading the finding row that the mapping was clean.
        failures: list[str] = []
        reasons: list[str] = []
        if registrations == 0:
            failures.append(S.GATE_UNREACHABLE)
            reasons.append(
                f"no {stype} sample is registered in internal assay {iaid} "
                "anywhere, so the claim is not credible")
        if provenance == S.P_CURATOR and (family or thin or impure):
            reasons.append(
                "a curator ruled on this mapping, which outranks the family "
                "and both floors")
        else:
            if family:
                failures.append(S.GATE_INCOHERENT)
                reasons.append(
                    f"the {family_key[0]}/{family_key[1]} term family maps to "
                    f"{len(family)} assays: {';'.join(str(i) for i in family)}")
            if thin or impure:
                failures.append(S.GATE_LOW_SUPPORT)
            # both floors are reported when both fire: they are one OUTCOME and
            # two facts, and a curator fixing the mapping needs both.
            if thin:
                reasons.append(
                    f"{n_samples} distinct sample(s) back this mapping, under "
                    f"the floor of {min_samples}")
            if impure:
                reasons.append(
                    f"purity {purity:.3f} is under the floor of {min_purity}")

        gate = failures[0] if failures else S.GATE_PASS

        rows.append({
            "sample_id": int(c.sample_id),
            "uuid": c.uuid,
            "sample_type": stype,
            "internal_assay_id": iaid,
            "internal_assay_title": c.internal_assay_title,
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "gate": gate,
            "gate_failures": ";".join(failures),
            "gate_reason": "; ".join(reasons),
            "vocab_support": support,
            "vocab_n_samples": n_samples,
            "vocab_purity": purity,
            "vocab_provenance": provenance,
            "term_family": f"{family_key[0]}/{family_key[1]}",
            "family_internal_assay_ids": (
                ";".join(str(i) for i in family) if family else ""),
            "type_registrations": registrations,
        })
    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def vocabulary_defects(
    gated: pd.DataFrame,
    vocabulary: pd.DataFrame,
    min_samples: int = MIN_VOCAB_SAMPLES,
    min_purity: float = MIN_VOCAB_PURITY,
) -> pd.DataFrame:
    """The gate's one artifact: what a curator has to fix, never what to write.

    **PASS THE SAME FLOORS `gate_claims` WAS GIVEN.** They default to the module
    constants, which is right only while the caller took the defaults too. This
    function states the floors in the `detail` a curator reads, and it cannot
    see the arguments the ruling was actually made under, so a caller gating at
    one pair and reporting at another prints two numbers for one concept -- a
    per-claim reason naming a floor of 0.95 beside a defect row naming 0.75, in
    the artifact the triage happens in. That is the defect class this package
    polices in nine other places, and it is inert today only because `main`
    takes the defaults for both calls.
    IT IS STILL INERT AND IT IS A DEFERRED MINOR, not a live defect. The
    re-derivation of `MIN_VOCAB_PURITY` against peer rate is deferred to
    increment 3, so no caller sweeps a floor yet and none can diverge today. The
    fix that would make the mistake unrepresentable -- carrying the applied
    floors on the gate frame -- changes `GATE_COLUMNS`, a shared output contract
    later tasks are already written against, and changing it mid-increment costs
    more than the hazard it closes. It belongs to whichever task first sweeps a
    floor. `main` binds the pair once, in one place, and hands the same two
    values to both functions, which is what keeps it inert meanwhile.

    THE WHOLE FAMILY IS EMITTED, including members no claim rests on. On the
    real vocabulary `flowjo 10.8.1` backs 0 of the 130,764 claims, and until
    2026-08-21 it sat in a family that split across 30, 31 and 153 -- a file
    naming only the members a claim happened to reach would ask a curator to fix
    one row of a split they cannot see. That family is now retired: all six
    `flowjo*` rows carry a null `internal_assay_id`, so it splits across nothing
    and `incoherent_families` returns `{}`. The rule is unchanged; the example
    is history. Members with no claim carry `n_claims` 0, which is a
    fact about this run rather than an absence.

    `GATE_UNREACHABLE` rows key on the (term, sample_type, assay) triple and the
    other two key on the vocabulary row alone, because reachability is a
    property of the CLAIM -- the same term is credible for one type and not
    another -- while a family split and a thin mapping are properties of the
    MAPPING.

    BOTH BLOCKING AND NON-BLOCKING DEFECTS ARE HERE, and `blocks_modes` says
    which is which. A mapping under a tuned floor no longer stops a claim
    reaching its mode, but it is still a defect and still this curator's to fix;
    dropping it from the file because it stopped nothing would hide the largest
    class of vocabulary problem the layer can see -- 107 of the 202 rows today.

    Sorted, because this is an artifact a curator diffs between runs and the
    claims frame arrives in whatever order the extractor wrote samples.parquet,
    an order `test_assay_hygiene_stage0.py` already records as unstable across
    extracts. Same hazard and same fix as `audit.audit_contradictions`.
    """
    vocab_rows = _vocab_index(vocabulary)
    families = term_families(vocabulary)
    incoherent = incoherent_families(vocabulary)

    # (defect, field, value, sample_type, assay) -> the claims that landed there
    #
    # EVERY failing test lands a claim in its own bucket, read off
    # `gate_failures` and never off `gate`. A claim that is both unreachable and
    # thinly supported is two defects for a curator, and keying on the most
    # severe alone would drop the second from the file that exists to list them.
    buckets: dict[tuple, list] = defaultdict(list)
    for g in gated.itertuples(index=False):
        value = S.normalise_value(g.raw_value)
        for defect in str(g.gate_failures).split(";"):
            if not defect:
                continue
            if defect == S.GATE_UNREACHABLE:
                key = (defect, str(g.source_field), value,
                       g.sample_type, int(g.internal_assay_id))
            else:
                row = vocab_rows[(str(g.source_field), value)]
                key = (defect, str(g.source_field), value, "",
                       int(row.internal_assay_id))
            buckets[key].append(g)

    # every member of every family a rejection touched, claims or not
    for key in {(str(g.source_field), term_stem(S.normalise_value(g.raw_value)))
                for g in gated.itertuples(index=False)
                if S.GATE_INCOHERENT in str(g.gate_failures).split(";")}:
        for r in families[key]:
            buckets.setdefault(
                (S.GATE_INCOHERENT, str(r.source_field),
                 S.normalise_value(r.raw_value), "", int(r.internal_assay_id)),
                [])

    rows = []
    for (defect, field, value, stype, iaid), hits in buckets.items():
        row = vocab_rows[(field, value)]
        family_key = (field, term_stem(value))
        family = incoherent.get(family_key)
        if defect == S.GATE_UNREACHABLE:
            detail = (f"no {stype} sample is registered in internal assay "
                      f"{iaid} anywhere")
        elif defect == S.GATE_INCOHERENT:
            detail = (f"the {family_key[0]}/{family_key[1]} term family maps to "
                      f"{len(family)} assays: {';'.join(str(i) for i in family)}")
        else:
            n = int(row.n_samples) if pd.notna(row.n_samples) else 0
            p = float(row.purity) if pd.notna(row.purity) else 0.0
            # the floors this run APPLIED, never the module defaults
            detail = (f"{n} distinct sample(s) at purity {p:.3f}, against floors "
                      f"of {min_samples} samples and {min_purity}")
        samples = sorted({int(g.sample_id) for g in hits})
        rows.append({
            "defect": defect,
            "blocks_modes": blocks_mode(defect),
            "source_field": field,
            "raw_value": value,
            "sample_type": stype,
            "internal_assay_id": iaid,
            "internal_assay_title": row.internal_assay_title,
            "vocab_support": row.support,
            "vocab_n_samples": row.n_samples,
            "vocab_purity": row.purity,
            "vocab_provenance": row.provenance,
            "term_family": f"{family_key[0]}/{family_key[1]}",
            "family_internal_assay_ids": (
                ";".join(str(i) for i in family) if family else ""),
            "n_claims": len(hits),
            "n_samples_affected": len(samples),
            "example_uuids": "; ".join(
                str(g.uuid) for g in sorted(hits, key=lambda x: int(x.sample_id))[:5]),
            "detail": detail,
        })
    out = pd.DataFrame(rows, columns=DEFECT_COLUMNS)
    return out.sort_values(
        ["defect", "n_claims", "source_field", "raw_value", "sample_type"],
        ascending=[True, False, True, True, True], ignore_index=True,
    )


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene",
         min_samples: int = MIN_VOCAB_SAMPLES,
         min_purity: float = MIN_VOCAB_PURITY) -> int:
    """Gate every claim on disk and write `vocabulary-defects.csv`.

    Read-only. It reads five files and writes one, and the one it writes is
    routed to `/curate-assay-vocabulary` and to no mode. `claims.parquet` and
    `vocabulary.csv` are inputs and are left byte-identical; a test asserts it.

    THE TWO FLOORS ARE BOUND ONCE HERE and handed to both `gate_claims` and
    `vocabulary_defects`, so the number a claim was ruled under and the number
    the curator's file states cannot diverge. They are parameters rather than
    constants read twice because `MIN_VOCAB_PURITY` is uncalibrated and its
    re-derivation against peer rate is deferred to increment 3; the sweep that
    does it is the caller that would otherwise set one and not the other.
    """
    from . import vocabulary as V   # local: keeps the module import-light

    d, out = Path(extract_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")
    claims = pd.read_parquet(out / "claims.parquet")
    vocab = V.load_vocabulary(out / "vocabulary.csv")

    untyped = untyped_registration_samples(membership, nodes)
    type_reg = type_registration_index(membership, assays, nodes)
    gated = gate_claims(claims, vocab, type_reg, sample_type_index(nodes),
                        min_samples=min_samples, min_purity=min_purity)
    defects = vocabulary_defects(gated, vocab,
                                 min_samples=min_samples, min_purity=min_purity)
    defects.to_csv(out / "vocabulary-defects.csv", index=False)

    counts = gated.gate.value_counts().to_dict()
    print(f"gated {len(gated):,} claims over {gated.sample_id.nunique():,} "
          f"samples against {len(vocab):,} vocabulary rows")
    print("by most severe outcome:")
    for outcome in S.GATE_OUTCOMES:
        mark = "  BLOCKS" if blocks_mode(outcome) else ""
        print(f"  {outcome:<20} {counts.get(outcome, 0):>8,}{mark}")
    ok = reaches_modes(gated)
    blocked = int((~ok).sum())
    weak = int((ok & (gated.gate_failures != "")).sum())
    print(f"BLOCKED, reaching no mode:      {blocked:>8,}")
    print(f"reaching a mode:                {int(ok.sum()):>8,}"
          f"  ({weak:,} of them carrying a recorded floor failure)")
    print(f"{len(defects):,} vocabulary defects written to "
          f"{out / 'vocabulary-defects.csv'} "
          f"({int(defects.blocks_modes.sum())} blocking, "
          f"{int((~defects.blocks_modes).sum())} reported only)")
    if untyped:
        print(f"NOTE: {len(untyped)} registered sample(s) have no node row and "
              f"so no type; their registrations are absent from the "
              f"reachability index: {untyped[:10]}"
              + (" ..." if len(untyped) > 10 else ""))
    print("nothing was written to the database, and this file proposes no "
          "membership change")
    return 0


if __name__ == "__main__":
    # argv is text and the last two arguments are numbers, so they are parsed
    # HERE rather than by `main`, whose parameters are typed. Without this a
    # sweep invoked as `... extract out 10 0.95` compares an int against the
    # string "10" and raises inside the ruling loop, one frame from anything
    # that names the argument.
    #
    # THE ARITY IS CHECKED BEFORE THE ZIP, because `zip` stops at the shorter
    # of the two. Casting through it silently DISCARDED a fifth argument that
    # the previous `main(*sys.argv[1:])` spelling raised `TypeError` on, so
    # adding the casts traded a loud failure for a quiet one -- a typo'd
    # invocation would run at the DEFAULT floors and report figures for numbers
    # the caller never asked for. That is exactly the class of silent
    # substitution this module's floors exist to make visible.
    _argv = list(sys.argv[1:])
    _casts = (str, str, int, float)
    if len(_argv) > len(_casts):
        sys.exit(f"gate: expected at most {len(_casts)} arguments "
                 "(extract_dir out_dir min_samples min_purity), got "
                 f"{len(_argv)}: {_argv!r}")
    sys.exit(main(*(cast(a) for cast, a in zip(_casts, _argv))))
