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
never reach a membership proposal, and because a claim failing two tests must
report the one that names its actual defect. Increment 1 had no reachability
test at all, which is what produced the 24 above.

The gate is not a mode. It proposes no membership change, and a claim it rejects
is excluded from Modes 1 and 2 entirely and routed to `/curate-assay-vocabulary`
through `vocabulary-defects.csv`. Nothing here writes to the database; it reads
parquet and csv off disk and writes one csv.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.gate

Measured over the real extract 2026-08-17, at the defaults below, over all
138,007 claims: 107,424 PASS, 25,974 GATE_LOW_SUPPORT, 4,554 GATE_UNREACHABLE,
55 GATE_INCOHERENT. Over the 866 flags increment 1 reported: 225 PASS, 598
GATE_LOW_SUPPORT, 31 GATE_UNREACHABLE, 12 GATE_INCOHERENT.
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
# module here but `_schema.py`, which is why this comment does not spell either.
# These two floors are the gate's and nothing else reads them.
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
# The value: 3 rejects 83 of 736 vocabulary rows, 2,131 of 138,007 claims and 4
# of the 866 flags. It is deliberately the weakest of the three tests, because
# held-out accuracy shows NO penalty for thin support -- scored by sample over
# 333,717 test edges, terms resting on 2 samples predict at 99.8% and terms
# resting on 100+ at 93.6%. The floor is therefore justified on provenance and
# not on accuracy: a mapping backed by one sample is one curator's one row, which
# is indistinguishable in kind from a `proposed` guess, and the package already
# caps those below the audit floor.
MIN_VOCAB_SAMPLES = 3

# `MIN_VOCAB_PURITY` is the discriminating floor and it IS anchored on a
# measurement, the one `run_evidence.purity_band_accuracy` publishes. Held out
# by sample over 333,717 test edges: terms below 0.75 purity predict at 65.8%,
# terms in 0.75-0.90 at 88.1%, terms at or above 0.90 at 99.9%. A mapping right
# two times in three does not get to author a membership proposal; it goes to
# the curator who can fix it.
#
# It is what catches `Type: Illumina Library` -> 24 DNA Extraction at purity
# 0.707 over 2,210 samples, which drove 212 of increment 1's 250 ABSENCE_COMPAT
# flags and 269 of the 866. No support floor in either unit touches that row.
#
# KNOWN LIMITATION, stated because `evidence-report.md` measured it and this
# module must not read as though it had not. Against a PEER-REGISTRATION axis --
# of every sample carrying a term, how many are registered in the assay it names
# -- a 0.75 purity floor sorts 151 of the 866 the wrong way, most visibly
# `Type: Blood` at purity 0.693 and peer rate 98.7%, whose 97 flags this gate
# routes to vocabulary curation. That is the right destination for a mapping at
# 0.693 even so: the artifact tells a curator to fix `Blood`, which is upstream
# of and strictly better than proposing 97 memberships on it. Peer rate is not
# computable here -- it needs the co-registration layer Task 4 builds -- so when
# it exists this floor should be re-derived against it rather than kept because
# it was written first.
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
GATE_COLUMNS = [
    "sample_id", "uuid", "sample_type",
    "internal_assay_id", "internal_assay_title",
    "source_field", "raw_value",
    "gate", "gate_reason",
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
DEFECT_COLUMNS = [
    "defect", "source_field", "raw_value", "sample_type",
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

    types: dict[int, set[str]] = defaultdict(set)
    for sid, t in zip(nodes.sample_id, nodes.type):
        if pd.notna(sid) and pd.notna(t):
            types[int(sid)].add(str(t))

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
        value = S.normalise_value(r.raw_value)
        if not value or pd.isna(r.internal_assay_id):
            continue
        out[(str(r.source_field), term_stem(value))].append(r)
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


def reaches_modes(gated: pd.DataFrame) -> pd.Series:
    """Which gated rows are allowed to reach Mode 1 or Mode 2.

    A MEMBERSHIP test against `GATE_REJECTIONS` rather than `gate == GATE_PASS`,
    which is the shape `_schema` argues for and the same argument
    `EVIDENCE_PROVENANCES` makes against `p != P_PROPOSED`: a fourth rejection
    kind added later is then admitted by the tuple rather than by every consumer
    remembering to extend an inequality.
    """
    return ~gated.gate.isin(S.GATE_REJECTIONS)


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

    Precedence, in order, first match winning:

      1. reachability   -> GATE_UNREACHABLE
      2. curator provenance -> GATE_PASS
      3. term family    -> GATE_INCOHERENT
      4. either floor   -> GATE_LOW_SUPPORT
      5.                -> GATE_PASS

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
    extract, 10,497 of the 138,007 claims pass on their representative row while
    another row also backing that same assay would have been rejected. The
    defective row is still reported in `vocabulary-defects.csv`, which is keyed
    on the vocabulary and not on claims, so nothing is hidden -- but a claim
    corroborated by a clean row and a defective one is admitted, and closing
    that would mean gating on the metadata rather than on the claims frame.

    RAISES rather than skipping on a claim whose term has no vocabulary row or
    whose uuid has no type, following `precedent.mine_precedent` and
    `audit.registered_internal`. Both are silent-wrong-answer failures: a
    skipped claim disappears from Modes 1 and 2 with no count anywhere, and an
    untyped claim cannot be tested for reachability and would read as a PASS,
    which is the laundering this gate exists to stop. 0 of the 138,007 claims
    hit either today.

    Neither input frame is mutated.
    """
    index = {}
    for r in vocabulary.itertuples(index=False):
        value = S.normalise_value(r.raw_value)
        if value:
            index[(str(r.source_field), value)] = r
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
        if registrations == 0:
            gate, why = S.GATE_UNREACHABLE, (
                f"no {stype} sample is registered in internal assay {iaid} "
                "anywhere, so the claim is not credible")
        elif provenance == S.P_CURATOR and (family or thin or impure):
            gate, why = S.GATE_PASS, (
                "a curator ruled on this mapping, which outranks the family "
                "and both floors")
        elif family:
            gate, why = S.GATE_INCOHERENT, (
                f"the {family_key[0]}/{family_key[1]} term family maps to "
                f"{len(family)} assays: {';'.join(str(i) for i in family)}")
        elif thin:
            gate, why = S.GATE_LOW_SUPPORT, (
                f"{n_samples} distinct sample(s) back this mapping, under the "
                f"floor of {min_samples}")
        elif impure:
            gate, why = S.GATE_LOW_SUPPORT, (
                f"purity {purity:.3f} is under the floor of {min_purity}")
        else:
            gate, why = S.GATE_PASS, ""

        rows.append({
            "sample_id": int(c.sample_id),
            "uuid": c.uuid,
            "sample_type": stype,
            "internal_assay_id": iaid,
            "internal_assay_title": c.internal_assay_title,
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "gate": gate,
            "gate_reason": why,
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
) -> pd.DataFrame:
    """The gate's one artifact: what a curator has to fix, never what to write.

    THE WHOLE FAMILY IS EMITTED, including members no claim rests on. On the
    real vocabulary `flowjo 10.8.1` backs 0 of the 138,007 claims while sitting
    in the family that splits across 30, 31 and 153, and a file naming only the
    members a claim happened to reach would ask a curator to fix one row of a
    split they cannot see. Members with no claim carry `n_claims` 0, which is a
    fact about this run rather than an absence.

    `GATE_UNREACHABLE` rows key on the (term, sample_type, assay) triple and the
    other two key on the vocabulary row alone, because reachability is a
    property of the CLAIM -- the same term is credible for one type and not
    another -- while a family split and a thin mapping are properties of the
    MAPPING.

    Sorted, because this is an artifact a curator diffs between runs and the
    claims frame arrives in whatever order the extractor wrote samples.parquet,
    an order `test_assay_hygiene_stage0.py` already records as unstable across
    extracts. Same hazard and same fix as `audit.audit_contradictions`.
    """
    vocab_rows = {}
    for r in vocabulary.itertuples(index=False):
        value = S.normalise_value(r.raw_value)
        if value:
            vocab_rows[(str(r.source_field), value)] = r
    families = term_families(vocabulary)
    incoherent = incoherent_families(vocabulary)

    # (defect, field, value, sample_type, assay) -> the claims that landed there
    buckets: dict[tuple, list] = defaultdict(list)
    for g in gated.itertuples(index=False):
        if g.gate not in S.GATE_REJECTIONS:
            continue
        value = S.normalise_value(g.raw_value)
        if g.gate == S.GATE_UNREACHABLE:
            key = (g.gate, str(g.source_field), value,
                   g.sample_type, int(g.internal_assay_id))
        else:
            row = vocab_rows[(str(g.source_field), value)]
            key = (g.gate, str(g.source_field), value, "",
                   int(row.internal_assay_id))
        buckets[key].append(g)

    # every member of every family a rejection touched, claims or not
    for key in {(str(g.source_field), term_stem(S.normalise_value(g.raw_value)))
                for g in gated.itertuples(index=False)
                if g.gate == S.GATE_INCOHERENT}:
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
            detail = (f"{n} distinct sample(s) at purity {p:.3f}, against floors "
                      f"of {MIN_VOCAB_SAMPLES} samples and {MIN_VOCAB_PURITY}")
        samples = sorted({int(g.sample_id) for g in hits})
        rows.append({
            "defect": defect,
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
         out_dir: str = "assay-hygiene") -> int:
    """Gate every claim on disk and write `vocabulary-defects.csv`.

    Read-only. It reads five files and writes one, and the one it writes is
    routed to `/curate-assay-vocabulary` and to no mode. `claims.parquet` and
    `vocabulary.csv` are inputs and are left byte-identical; a test asserts it.
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
    gated = gate_claims(claims, vocab, type_reg, sample_type_index(nodes))
    defects = vocabulary_defects(gated, vocab)
    defects.to_csv(out / "vocabulary-defects.csv", index=False)

    counts = gated.gate.value_counts().to_dict()
    print(f"gated {len(gated):,} claims over {gated.sample_id.nunique():,} "
          f"samples against {len(vocab):,} vocabulary rows")
    for outcome in S.GATE_OUTCOMES:
        print(f"  {outcome:<20} {counts.get(outcome, 0):>8,}")
    print(f"{int((~reaches_modes(gated)).sum()):,} claims reach no mode and are "
          f"routed to /curate-assay-vocabulary")
    print(f"{len(defects):,} vocabulary defects written to "
          f"{out / 'vocabulary-defects.csv'}")
    if untyped:
        print(f"NOTE: {len(untyped)} registered sample(s) have no node row and "
              f"so no type; their registrations are absent from the "
              f"reachability index: {untyped[:10]}"
              + (" ..." if len(untyped) > 10 else ""))
    print("nothing was written to the database, and this file proposes no "
          "membership change")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
