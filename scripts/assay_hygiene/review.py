"""The Mode 1 review sheet: one self-contained HTML page a curator rules on.

`run_detect` writes five machine-readable artifacts and a report. None of them
is a review surface for MODE 1. The cohort csv it writes is keyed on (sample
type, proposed assay, term) and carries counts; ruling on a Mode 1 proposal
needs the thing a count cannot carry -- WHAT THE SAMPLE ACTUALLY SAYS, and what
the samples it was derived from say. A curator asked to approve "propose Tissue
Imaging for 412 D.IMG rows raised by DataType=tif" has no way to answer without
opening the database. Shown the same cohort with five of its children, their
non-empty metadata, and each child's DERIVED_FROM parents with the assays those
parents already hold, they answered seventeen cohorts in one sitting. Every
design decision below comes out of that sitting.

THIS PAGE DETECTS AND PROPOSES. IT DOES NOT ADJUDICATE. It captures a ruling as
text a human exports and pastes back somewhere else; nothing in this package
reads that text, and nothing here imports the write path. The ruling control is
a `<select>` whose values are words, not a column in a file some later stage
consumes. That boundary is asserted from the outside, in
`test_the_sheet_has_no_approval_surface_and_imports_no_write_path`.

AND THE PROPOSED ASSAY IS AN INTERNAL ID, WHICH IS NOT A WRITABLE TARGET.
`proposed_internal_assay_id` is a harmonisation key this package DERIVES by
crossing `dmac.assays_internal_assays`; a membership row natively carries a
SEEK `assays.id`, and one internal id spans up to 23 SEEK records. The report
states this and the sheet has to state it too, in front of the same reader, or
a page with an APPROVE option in a dropdown reads as a page where APPROVE is
something the system can then do. Mode 1 is the worst case for it: Mode 2 at
least has the rule "target the record the registered neighbour is in", and a
Mode 1 sample has no registered neighbour by definition.

FOUR THINGS THIS MODULE DOES DIFFERENTLY FROM THE PROTOTYPE IT REPLACES, each
because the prototype's way shipped a defect:

  * ONE FRAME, ONE PASS. The first version was three scripts writing csv for
    each other to read, and the artifacts went inconsistent TWICE -- once
    emitting internal assay 31 "Flow Cytometry Analysis" in the review context
    where the findings artifact said 30 "Flow Cytometry". `build_blocks` takes
    the frame in memory and derives the cohorts, their stats and their context
    in one pass. It reads no csv at all, which is asserted over this file's
    source, and the two reads that produced the divergence cannot be spelled.

  * THE CLASS TOKENS ARE PARTITIONED between elements a curator types into and
    elements that merely render. The prototype styled a band blurb as
    `<p class="note">` beside `<textarea class="note">`; the script's
    `querySelectorAll(".dec, .note")` collected the paragraphs, `closest(
    ".notes")` returned null on the first, `paint(null)` threw, and the throw
    aborted the loop before ANY storage listener or EITHER button handler was
    attached. The page still rendered, still accepted typing, saved nothing and
    could not export. Structural markers are named for structure and never for
    the control beside them.

  * EVERY STORAGE CALL IS WRAPPED. `window.localStorage` THROWS on access in a
    sandboxed viewer rather than returning null, and an unguarded throw at load
    is the same silent-dead-form outcome by a different route. It is also not
    enough to guard: the page has to SAY when it cannot save, because a curator
    who loses an afternoon of rulings to a reload has no way to tell that from
    a page that saved them.

  * THE UID PARSE IS GUARDED AND RAISES. See `parse_uid`.

WHAT A COHORT IS. Six fields: `(lab, sample_type, parent_types,
proposed_internal_assay_title, source_field, raw_value)`. `run_detect`'s
PATTERN_KEY is three of those, which is the right key for the report -- it
answers "which terms produce the most rows". It is the wrong key for a ruling,
because a curator rules per lab (the D.IMG convention in one lab is not the
convention in another), and because the same term under a different parent
shape is a different question: measured on the 2026-08-14 extract, `DataType`
= `tif` under a `TIS` parent and the same term under `SLD` were ruled
differently by the operator, to Tissue Imaging and to Spatial Transcriptomics.
A key without `parent_types` would have presented those as one cohort and taken
one ruling for both.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import gate as G
from . import lineage as L
from . import precedent as P
from . import vocabulary as V

REVIEW_NAME = "mode1-review.html"

# `<TYPE>-<YYMMDD><LAB>-<serial>`. The lab and the date are split at the
# digit/letter boundary; nothing else in the uuid is read.
UID_RE = re.compile(
    r"^(?P<type>[^-]+)-(?P<date>\d{6})(?P<lab>[A-Za-z]+)-(?P<serial>\d+)$")

# A sample derived from nothing is a POPULATION and gets a name, not a blank.
# The operator ruled on three such cohorts and read them as a group.
NO_PARENT = "NO_PARENT"
UNTYPED = "UNTYPED"

# The cohort key, in the order it is joined into the storage key and the export
# row. `assay` is the internal assay TITLE and not its id, because the key is
# also what a human reads in an exported ruling file; the id travels beside it
# in the rendered header, and the flag comparing a parent's registration to the
# proposal is keyed on the ID for the reason `merge_vocabulary` and
# `audit_contradictions` both refuse a title key: two assays sharing a display
# string would compare equal.
BLOCK_KEY = ("lab", "sample_type", "parent_types", "assay", "field", "value")
KEY_DELIMITER = "|"

# The exported ruling row: the six key fields, then what the human decided.
EXPORT_COLUMNS = BLOCK_KEY + ("ruling", "note")

# Caps. Each one is RENDERED WITH ITS DENOMINATOR wherever it bites, which is
# the same rule `run_detect._more` keeps: a cohort of 400 showing 5 and not
# saying so reads as a cohort of 5.
MAX_EXAMPLES = 5
MAX_PARENTS = 4
MAX_REGISTRATIONS = 6
MAX_VALUE_CHARS = 90

# The bands, best first. A BAND IS A READING ORDER AND NEVER A PERMISSION --
# the same statement the report makes about every threshold in it. Nothing here
# approves anything; the order decides what a curator opens first, and the
# blurbs carry the accuracy each band was measured at so the order is
# falsifiable rather than asserted.
BAND_A = "A_corroborated"
BAND_B = "B_strong"
BAND_CONTESTED = "C_CONTESTED_pick_one"
BAND_WEAK = "D_weak"
BAND_THIN = "D_THIN_mapping"

BANDS = (
    (BAND_A, "A", "Type and Protocol both predict and AGREE. Measured 92.3% "
                  "coverage at 90.4% accuracy for the pair, and 99.9% where "
                  "they agree, held out BY SAMPLE."),
    (BAND_B, "B", "One strong field, uncontested, mapping at full purity. "
                  "Strong fields alone: 65.9% coverage at 98.4% accuracy."),
    (BAND_CONTESTED, "C", "The sample's own metadata names MORE THAN ONE "
                          "assay. Not a yes/no question -- a which-one."),
    (BAND_WEAK, "D", "A weak field only. The term predicts, but weakly."),
    (BAND_THIN, "D", "The vocabulary mapping itself is under the support or "
                     "purity floor and was RECORDED rather than blocked. Fix "
                     "the term, not the row."),
)
BAND_ORDER = {name: i for i, (name, _letter, _blurb) in enumerate(BANDS)}

# The words a curator may record. They are values in a dropdown and text in an
# exported file. NOTHING IN THIS PACKAGE READS THEM BACK -- see the module
# docstring on the boundary this increment does not cross.
RULING_OPTIONS = (
    ("", "-- not ruled --"),
    ("APPROVE", "APPROVE, register as proposed"),
    ("REJECT", "REJECT, do not register"),
    ("WRONG_ASSAY", "WRONG ASSAY, a different one is right"),
    ("FIX_VOCAB", "FIX VOCAB, the term is the problem"),
    ("ASK_PI", "ASK PI"),
    ("HOLD", "HOLD"),
)


def _truthy(series: pd.Series) -> pd.Series:
    """A boolean column that has been through csv, coerced back.

    `contested` round-trips as the STRINGS "True"/"False" when the frame is
    read back off disk, and a bare `.astype(bool)` on those is True for both --
    a non-empty string is truthy -- so a contested count would equal the row
    count and look like a finding.

    THIS IS THE ONE DEFINITION. `run_detect` used to carry its own copy and now
    imports this one. It lives here rather than there because the import
    direction is `run_detect -> review`, and two spellings of one coercion one
    module apart is the shape of three defects this branch has already found.
    """
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().isin(("true", "1"))


# --- the UID, which is a convention and not a column -------------------------


def parse_uid(uuid: str) -> dict:
    """`<TYPE>-<YYMMDD><LAB>-<serial>` -> its four parts. RAISES on anything else.

    THE LAB IS NOT A MODELLED FIELD ANYWHERE IN THIS EXTRACT. Neither `samples`
    nor `nodes` nor the findings frame carries it; it exists only inside the
    uuid, by a naming convention curators follow, and this sheet groups on it
    because a curator rules lab by lab -- the imaging conventions in one lab are
    not the conventions in another, and the operator's rulings split on exactly
    that.

    SO IT RAISES RATHER THAN RETURNING NOTHING. The prototype spelled this
    `Series.str.extract`, which yields NaN on a non-match; `groupby(dropna=
    False)` then puts EVERY unparseable uuid into ONE cohort keyed `lab = nan`,
    and rows from unrelated labs are presented to a curator as one population
    and ruled on together. Nothing about the page would look wrong. A crash is
    strictly better than that, and this is the crash.

    MEASURED on the 2026-08-14 extract: 0 of the 2,166 MODE_1 uuids fail this
    parse, so the guard costs the real run nothing today. 2 of the 163,379
    sample uuids DO fail it -- `2720-Group 01-G181_TMZ_IC_PD`, which is not a
    UID at all, and `MUS-191001LAU-68` carrying a trailing NON-BREAKING SPACE.
    The second is the case that argues for raising rather than repairing: it is
    one invisible character away from valid, `.strip()` would silently swallow
    it, and this module would then be quietly correcting someone else's data
    defect in a surface whose entire purpose is to show a curator what the data
    says.

    The date is NOT validated as a calendar date, only as six digits. The sheet
    uses it to order and to show a batch range, and a `YYMMDD` string sorts
    chronologically as a string; rejecting an impossible day here would fail a
    run over a typo in a field nothing depends on.
    """
    m = UID_RE.match(uuid) if isinstance(uuid, str) else None
    if m is None:
        raise ValueError(
            f"uuid {uuid!r} does not match the house UID shape "
            "<TYPE>-<YYMMDD><LAB>-<serial>, so it carries no lab and no date. "
            "This is refused rather than skipped or grouped under a null: a "
            "cohort keyed on a missing lab pools rows from unrelated labs and "
            "takes one ruling for all of them.")
    return m.groupdict()


def _uid_columns(uuids: pd.Series) -> pd.DataFrame:
    """-> a frame of `lab` and `date`, or a raise naming every offender.

    Every bad uuid is collected before raising rather than raising on the
    first, so one run tells an operator the whole population to fix.
    """
    bad = [u for u in uuids.unique() if UID_RE.match(str(u)) is None]
    if bad:
        raise ValueError(
            f"{len(bad)} uuid(s) in the MODE_1 population do not match the "
            f"house UID shape <TYPE>-<YYMMDD><LAB>-<serial>: {bad[:10]!r}"
            f"{' ...' if len(bad) > 10 else ''}. The review sheet groups on "
            "the lab parsed out of the uuid; it will not emit a cohort whose "
            "lab it had to guess.")
    parts = [parse_uid(str(u)) for u in uuids]
    return pd.DataFrame({"lab": [p["lab"] for p in parts],
                         "date": [p["date"] for p in parts]},
                        index=uuids.index)


# --- the extract-side context ------------------------------------------------


def load_context(extract_dir) -> dict:
    """Everything the sheet needs that the findings frame does not carry.

    -> `{parents_of, uuid_of, types, registrations, metadata}`.

    EVERY INDEX HERE COMES FROM THE ONE FUNCTION THAT DEFINES IT --
    `lineage.lineage_index`, `gate.sample_type_index`, `precedent.assay_index`,
    `vocabulary.parse_metadata`. Not one of them is re-derived with a groupby,
    which is the rule the rest of this package keeps and the reason it keeps
    it: `registered` was once defined in three places and two of them published
    wrong figures.

    It calls `lineage_index` a second time in a `run_detect` run rather than
    threading `_lineage_facts`'s intermediates out of it. That is a second CALL
    of one definition and not a second definition -- the distinction
    `run_detect`'s docstring draws -- and it costs one extra traversal of the
    edge frame.

    `registrations` crosses the SEEK junction through `assay_index`, and keeps
    BOTH ids on every row. A parent's registration is rendered `seek ->
    internal` for the reason the module docstring gives: the write goes against
    the seek id, the proposal names the internal one, and a page showing only
    one of them would let a reader believe a row names a single writable
    record.
    """
    d = Path(extract_dir)
    samples = pd.read_parquet(d / "samples.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    edges = pd.read_parquet(d / "edges.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")

    _children_of, parents_of, uuid_of, _integrity = L.lineage_index(
        edges, samples, membership)
    index = P.assay_index(assays)

    registrations: dict[int, list[tuple]] = defaultdict(list)
    for sid, aid in zip(membership.sample_id.astype(int),
                        membership.assay_id.astype(int)):
        _project, internal, title = index.get(aid, (None, None, None))
        registrations[int(sid)].append(
            (int(aid),
             int(internal) if internal is not None and pd.notna(internal)
             else None,
             str(title) if title is not None and pd.notna(title) else None))

    return {
        "parents_of": parents_of,
        "uuid_of": uuid_of,
        "types": G.sample_type_index(nodes),
        "registrations": dict(registrations),
        "metadata": V.parse_metadata(samples),
    }


# --- the one pass ------------------------------------------------------------


def review_band(*, contested: bool, gate, claim_tier) -> str:
    """Which band a single MODE_1 row belongs in.

    CONTESTED OUTRANKS EVERYTHING, including a corroborated tier, because a
    contested row is not a harder yes/no -- it is a different question. The
    sample's own metadata names more than one assay and the curator has to pick
    one; presenting it beside the rows that need a yes invites a yes.

    A recorded gate failure outranks the tier for the opposite reason: the tier
    describes the claim and the gate describes the TERM, and a claim resting on
    a mapping under the support floor is a vocabulary repair rather than a
    registration. `gate.blocks_mode` is what stops a claim; a GATE_LOW_SUPPORT
    row reaches Mode 1 anyway and is banded here rather than hidden.
    """
    if contested:
        return BAND_CONTESTED
    if gate != S.GATE_PASS:
        return BAND_THIN
    if claim_tier == S.T_CORROBORATED:
        return BAND_A
    if claim_tier == S.T_STRONG:
        return BAND_B
    return BAND_WEAK


def _parent_types(sample_id, context) -> str:
    parents = context["parents_of"].get(int(sample_id)) or ()
    if not parents:
        return NO_PARENT
    types = context["types"]
    uuid_of = context["uuid_of"]
    return ";".join(sorted({types.get(uuid_of.get(p, ""), UNTYPED)
                            for p in parents}))


def _registrations(sample_id, context) -> tuple[list[dict], int]:
    """-> (up to `MAX_REGISTRATIONS` rendered rows, how many were held back).

    SORTED ON THE SEEK ID ALONE, which is total. Sorting the whole tuple is
    the obvious spelling and can raise: `internal` is `None` on the 17
    junction-less assay records (`precedent.assay_index` falls back rather than
    dropping them, and a consumer that filtered instead would lose 279 of
    214,124 registrations), and a tuple comparison that reaches that slot
    compares `None` with an int. The seek id is unique per registration, so
    nothing after it is ever read.
    """
    held = sorted(context["registrations"].get(int(sample_id), []),
                  key=lambda row: row[0])
    shown = [{"seek": seek, "internal": internal,
              "title": title or "(no internal assay)"}
             for seek, internal, title in held[:MAX_REGISTRATIONS]]
    return shown, max(0, len(held) - MAX_REGISTRATIONS)


def _metadata(sample_id, context) -> dict:
    """Non-empty fields, claim-bearing ones first, blanks COUNTED not dropped.

    The D.IMG sheet carries sixty-odd columns and a typical row fills six.
    Rendering the blanks buries the six; dropping them silently hides that the
    record is mostly empty, and how empty a record is is itself evidence about
    a claim drawn from it.
    """
    fields = context["metadata"].get(int(sample_id), {}) or {}
    items = [(str(k), str(v)) for k, v in fields.items()
             if v is not None and str(v).strip() not in ("", "nan")]
    return {
        "claim": [(k, v) for k, v in items if k in S.CLAIM_FIELDS],
        "rest": [(k, v) for k, v in items if k not in S.CLAIM_FIELDS],
        "n_blank": len(fields) - len(items),
    }


def _check_key_components(frame: pd.DataFrame) -> None:
    """No key field may be null, or carry the delimiter, a tab or a newline.

    THE DELIMITER HALF. The storage key and the exported row are `|`-joined and
    tab-separated. A term containing either splits into the wrong number of
    fields, and a ruling file that splits into seven columns silently resolves
    to no cohort at all on the way back in. Measured on the 2026-08-14 extract,
    no MODE_1 value in any of the six components carries one; this is the guard
    for the extract that does.

    THE NULL HALF IS THE UNPARSEABLE-UID DEFECT ONE COLUMN OVER. A null term
    reaching the key does not fail -- it groups. Every null term collapses into
    ONE cohort whose label is a rendering of the missing value, pooling rows
    from unrelated claims for a single ruling, which is exactly the silent
    mis-grouping `parse_uid` refuses. `source_field` and `raw_value` are
    non-null on every MODE_1 row by construction, because the mode IS "the
    sample's own metadata names an assay": measured on the 2026-08-14 extract,
    0 of the 2,166 are null. A null reaching here means that construction
    changed, and the sheet says so rather than rendering a cohort named after
    the failure.

    IT READS THE SOURCE COLUMN AND NOT THE DERIVED ONE, and the reason is
    version-dependent rather than universal, so it is stated as measured.
    `build_blocks` derives `assay`, `field` and `value` through `astype(str)`.
    On the pandas this ran under -- 3.0.5, `future.infer_string` on --
    `astype(str)` PRESERVES the null for object, `str` and float dtypes alike,
    so a derived-column check would work and a mutation swapping one for the
    other survives the suite. That is recorded rather than hidden. The package
    declares `pandas>=2.0`, and under pandas 2 the same call renders a null as
    the STRING "None" or "nan" on an object column, where `.isna()` is False
    for every row and the guard is silently vacuous. The source column is the
    one the invariant is actually about and is correct under both.
    """
    for derived, source in (("assay", "proposed_internal_assay_title"),
                            ("field", "source_field"),
                            ("value", "raw_value")):
        n_null = int(frame[source].isna().sum())
        if n_null:
            raise ValueError(
                f"{n_null:,} MODE_1 row(s) carry a null {source!r}, which is "
                f"the cohort key's {derived!r}. Every MODE_1 row is raised by a "
                "claim the sample's own metadata makes, so none of these can "
                "be null; rendered, they would collapse into one cohort "
                "labelled `nan` holding unrelated claims.")
    for column in ("lab", "sample_type", "parent_types", "assay", "field",
                   "value"):
        values = frame[column].astype(str)
        bad = sorted(set(values[values.str.contains(r"[|\t\r\n]", regex=True,
                                                    na=False)]))
        if bad:
            raise ValueError(
                f"{len(bad)} value(s) of the cohort key component {column!r} "
                f"carry a delimiter this sheet joins on: {bad[:5]!r}. An "
                "exported ruling keyed on them would split into the wrong "
                "number of fields and resolve back to no cohort.")


def _check_no_registrations(frame: pd.DataFrame, context) -> None:
    """A MODE_1 sample holds NO registration. That is what makes it MODE_1.

    Measured on the 2026-08-14 extract, 0 of the 1,657 Mode 1 samples carry any
    membership row, so this costs nothing today. It is the guard that goes red
    if the precedence between the modes is ever reordered, because a child that
    already holds an assay is not a sample with a missing registration and
    putting one in front of a curator asks them to approve something already
    done.
    """
    holders = sorted({int(s) for s in frame.sample_id
                      if context["registrations"].get(int(s))})
    if holders:
        raise ValueError(
            f"{len(holders)} sample(s) in the MODE_1 population hold a "
            f"registration: {holders[:10]}. MODE_1 is 'registered in nothing'; "
            "a row here that holds an assay means the mode precedence changed "
            "and this sheet is describing a population it is not named for.")


def build_blocks(findings: pd.DataFrame, context: dict) -> list[dict]:
    """-> the cohorts, their header stats and their examples, in ONE pass.

    THE FRAME IS THE RUN. Everything below is derived from the argument; this
    module reads no csv, so there is no second read of a file this run wrote
    and no opportunity for the two artifacts to describe different populations.
    That is not a hypothetical failure: the prototype's earlier form was
    separate scripts reading each other's output and it went inconsistent
    twice.

    THE COUNTS PARTITION AND THAT IS ASSERTED HERE. Every MODE_1 row lands in
    exactly one cohort and the cohort sizes sum to the population. A review
    surface whose rows overlap invites two rulings on one proposal, and one
    whose rows do not cover presents fewer proposals than the run found and
    hides the rest -- and neither is visible by reading the page.

    THE CORROBORATION FLAG IS KEYED ON THE ASSAY ID. Mode 1 outranks the
    lineage step in this package's precedence, so a sample registered in
    nothing is claimed by Mode 1 EVEN WHERE a DERIVED_FROM neighbour already
    carries the proposed pair. Where that happens the neighbour is independent
    evidence, and it is the only evidence a Mode 1 row can have beyond its own
    metadata -- so the sheet finds it and marks it rather than leaving a
    curator to notice. Keyed on the id, never the title: two assays sharing a
    display string would compare equal, which is the same ruling
    `merge_vocabulary` and `audit_contradictions` both make.
    """
    m1 = findings[findings["mode"] == S.MODE_1].copy()
    if not len(m1):
        return []

    missing = [c for c in ("uuid", "sample_id", "sample_type", "source_field",
                           "raw_value", "proposed_internal_assay_id",
                           "proposed_internal_assay_title", "claim_tier",
                           "gate", "contested") if c not in m1.columns]
    if missing:
        raise ValueError(f"the findings frame is missing {missing}")

    uid = _uid_columns(m1.uuid.astype(str))
    m1["lab"] = uid["lab"]
    m1["date"] = uid["date"]
    m1["assay"] = m1.proposed_internal_assay_title.astype(str)
    m1["field"] = m1.source_field.astype(str)
    m1["value"] = m1.raw_value.astype(str)
    m1["sample_type"] = m1.sample_type.astype(str)
    m1["contested_flag"] = _truthy(m1.contested)
    m1["parent_types"] = [_parent_types(s, context) for s in m1.sample_id]
    m1["band"] = [review_band(contested=c, gate=g, claim_tier=t)
                  for c, g, t in zip(m1.contested_flag, m1.gate, m1.claim_tier)]

    _check_key_components(m1)
    _check_no_registrations(m1, context)

    blocks = []
    for key, rows in m1.groupby(list(BLOCK_KEY), dropna=False, sort=False):
        rows = rows.sort_values("sample_id")
        examples = rows.head(MAX_EXAMPLES)
        children = [_child(r, context) for r in examples.itertuples(index=False)]
        dates = sorted(rows.date.unique())
        blocks.append(dict(
            zip(BLOCK_KEY, (str(k) for k in key)),
            # BANDED BY ITS STRONGEST ROW, because the band is a reading order:
            # a cohort holding one corroborated row is worth opening with the
            # corroborated ones, and the per-row tiers travel in `tiers` beside
            # it so the band never hides the spread it was chosen from.
            band=min(rows.band, key=BAND_ORDER.__getitem__),
            n_rows=int(len(rows)),
            n_samples=int(rows.sample_id.nunique()),
            n_contested=int(rows.contested_flag.sum()),
            tiers=";".join(sorted({str(t) for t in rows.claim_tier})),
            gates=";".join(sorted({str(g) for g in rows.gate})),
            dates=dates[0] if len(dates) == 1 else f"{dates[0]}-{dates[-1]}",
            n_dates=len(dates),
            shown=len(children),
            n_corroborated_shown=sum(1 for c in children
                                     if c["parent_has_proposed"]),
            children=children,
        ))

    total = sum(b["n_rows"] for b in blocks)
    if total != len(m1):
        raise ValueError(
            f"the cohorts hold {total:,} rows and the MODE_1 population is "
            f"{len(m1):,}. Every finding must land in exactly one cohort: a "
            "surface that double-counts invites two rulings on one proposal, "
            "and one that under-counts hides proposals the run made.")
    if len({cohort_key(b) for b in blocks}) != len(blocks):
        raise ValueError("two cohorts share a key; their rulings would collide")

    blocks.sort(key=lambda b: (BAND_ORDER[b["band"]], -b["n_rows"],
                               cohort_key(b)))
    return blocks


def _child(row, context) -> dict:
    """One example child, with its DERIVED_FROM parents and everyone's metadata."""
    parents = sorted(context["parents_of"].get(int(row.sample_id)) or ())
    rendered = []
    for pid in parents[:MAX_PARENTS]:
        uuid = context["uuid_of"].get(pid, str(pid))
        regs, hidden = _registrations(pid, context)
        rendered.append({"uuid": uuid,
                         "type": context["types"].get(uuid, UNTYPED),
                         "regs": regs, "n_regs_hidden": hidden,
                         "meta": _metadata(pid, context)})

    proposed = row.proposed_internal_assay_id
    proposed = int(proposed) if pd.notna(proposed) else None
    own, own_hidden = _registrations(row.sample_id, context)
    return {
        "uuid": str(row.uuid),
        "sample_id": int(row.sample_id),
        "projects": "--" if pd.isna(row.project_ids) else str(row.project_ids),
        "tier": str(row.claim_tier),
        "gate": str(row.gate),
        "field": str(row.source_field),
        "value": str(row.raw_value),
        "purity": None if pd.isna(row.vocab_purity) else float(row.vocab_purity),
        "type_regs": (None if pd.isna(row.type_registrations)
                      else int(row.type_registrations)),
        "own_regs": own,
        "n_own_regs_hidden": own_hidden,
        "meta": _metadata(row.sample_id, context),
        "parents": rendered,
        "n_parents": len(parents),
        "n_parents_hidden": max(0, len(parents) - MAX_PARENTS),
        "parent_has_proposed": bool(
            proposed is not None
            and any(reg["internal"] == proposed
                    for parent in rendered for reg in parent["regs"])),
    }


def cohort_key(block: dict) -> str:
    """The stable identity of a cohort, joined for storage and for export.

    KEYED ON THE COHORT AND NEVER ON ITS POSITION. Re-running the detection
    must not orphan a curator's notes, and an index-keyed store orphans all of
    them the first time a cohort's size changes and the sort moves it.
    """
    return KEY_DELIMITER.join(str(block[c]) for c in BLOCK_KEY)


# --- the page ----------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value))


def _clip(value: str) -> str:
    """Long values truncated VISIBLY. A silent clip reads as the whole value."""
    text = str(value)
    if len(text) <= MAX_VALUE_CHARS:
        return _e(text)
    return _e(text[:MAX_VALUE_CHARS]) + '<span class="clip">&hellip;</span>'


def _metadata_html(meta: dict, source_field: str | None = None) -> str:
    """The non-empty metadata, with the field that raised THIS proposal marked.

    Claim-bearing fields are outlined and the source field is FILLED, and the
    two markings have to differ: on a contested row the entire question is
    which of several claim-bearing fields to believe, and a panel that marks
    them identically answers nothing.
    """
    if not meta or (not meta["claim"] and not meta["rest"]):
        return '<div class="meta"><span class="empty">no metadata</span></div>'
    out = ['<div class="meta"><div class="mrow">']
    for k, v in meta["claim"]:
        mark = " src" if source_field and k == source_field else ""
        out.append(f'<span class="mf claim{mark}"><b>{_e(k)}</b> '
                   f'{_clip(v)}</span>')
    out.append("</div>")
    if meta["rest"]:
        out.append(f'<details><summary>{len(meta["rest"])} other field(s) '
                   f'&middot; {meta["n_blank"]} blank</summary>'
                   '<div class="mrow">')
        for k, v in meta["rest"]:
            out.append(f'<span class="mf"><b>{_e(k)}</b> {_clip(v)}</span>')
        out.append("</div></details>")
    elif meta["n_blank"]:
        out.append(f'<div class="empty">{meta["n_blank"]} blank field(s)'
                   "</div>")
    out.append("</div>")
    return "".join(out)


def _registrations_html(regs: list[dict], hidden: int) -> str:
    if not regs:
        return '<span class="empty">registered in nothing</span>'
    out = []
    for reg in regs:
        internal = reg["internal"]
        tail = (f"&rarr; internal {internal}" if internal is not None
                else "&rarr; <i>no internal assay</i>")
        out.append(f'<span class="reg"><b>{_e(reg["title"])}</b>'
                   f'<span class="ids">seek {reg["seek"]} {tail}</span></span>')
    if hidden:
        out.append(f'<span class="empty">and {hidden} more</span>')
    return "".join(out)


def _child_html(child: dict) -> list[str]:
    purity = "--" if child["purity"] is None else f'{child["purity"]:.2f}'
    type_regs = "--" if child["type_regs"] is None else child["type_regs"]
    out = [
        f'<div class="pair{" corroborated" if child["parent_has_proposed"] else ""}">',
        '<div class="child"><span class="lbl">CHILD</span> '
        f'<code>{_e(child["uuid"])}</code>'
        f'<span class="ids">project {_e(child["projects"])} &middot; '
        f'{_e(child["tier"])} &middot; {_e(child["gate"])} &middot; '
        f'purity {purity} &middot; this type seen in this assay '
        f'{type_regs}x</span>'
        '<div class="regline">holds: '
        f'{_registrations_html(child["own_regs"], child["n_own_regs_hidden"])}'
        "</div>"
        f'{_metadata_html(child["meta"], child["field"])}'
        "</div>",
    ]
    if not child["parents"]:
        out.append('<div class="parent"><span class="empty">'
                   "no DERIVED_FROM parent</span></div>")
    for parent in child["parents"]:
        out.append(
            '<div class="parent"><span class="lbl">PARENT</span> '
            f'<code>{_e(parent["uuid"])}</code>'
            f'<span class="ids">{_e(parent["type"])}</span>'
            '<div class="regline">holds: '
            f'{_registrations_html(parent["regs"], parent["n_regs_hidden"])}'
            "</div>"
            f'{_metadata_html(parent["meta"])}'
            "</div>")
    if child["n_parents_hidden"]:
        out.append(f'<div class="parent"><span class="empty">'
                   f'{child["n_parents_hidden"]} further parent(s) not shown '
                   f'of {child["n_parents"]}</span></div>')
    out.append("</div>")
    return out


def _notes_html(block: dict) -> str:
    """The ruling control and the free-text note, both inside ONE `.notes`.

    THE CLASS TOKENS ON THESE TWO ELEMENTS ARE USED BY NOTHING ELSE ON THE
    PAGE. The script selects `.dec, .note` and then calls `closest(".notes")`
    on each hit; a structural element wearing either token makes that return
    null, and the throw kills every handler on the page. Structure is never
    named for the control beside it -- see the module docstring for what that
    cost.
    """
    key = _e(cohort_key(block))
    options = "".join(
        f'<option value="{_e(value)}">{_e(label)}</option>'
        for value, label in RULING_OPTIONS)
    return (
        '<div class="notes">'
        f'<label>ruling <select class="dec" data-k="{key}">{options}'
        "</select></label>"
        f'<textarea class="note" data-k="{key}" rows="2" '
        'placeholder="Why. What the right answer is, if it is not this one."'
        "></textarea></div>")


CSS = """
:root{--bg:#fff;--fg:#16181d;--mut:#6b7280;--line:#e5e7eb;--card:#fafafa;
 --ok:#0f766e;--okbg:#ecfdf5;--warn:#9a3412;--code:#f3f4f6;--acc:#1d4ed8;
 --on-acc:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
 --bg:#0f1115;--fg:#e6e8ec;--mut:#9aa1ac;--line:#272b33;--card:#151821;
 --ok:#5eead4;--okbg:#0d2b26;--warn:#fdba74;--code:#1b1f27;--acc:#93b4ff;
 --on-acc:#0f1115}}
:root[data-theme=dark]{--bg:#0f1115;--fg:#e6e8ec;--mut:#9aa1ac;--line:#272b33;
 --card:#151821;--ok:#5eead4;--okbg:#0d2b26;--warn:#fdba74;--code:#1b1f27;
 --acc:#93b4ff;--on-acc:#0f1115}
*{box-sizing:border-box}
html{overflow-x:hidden}
body{margin:0 auto;padding:2rem 1.25rem 5rem;background:var(--bg);
 color:var(--fg);max-width:68rem;overflow-wrap:anywhere;
 font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:1.5rem;margin:0 0 .25rem}
h2.band{margin:2.5rem 0 .25rem;font-size:1.05rem;letter-spacing:.04em;
 border-top:2px solid var(--line);padding-top:1rem}
.bmeta{font-weight:400;color:var(--mut);letter-spacing:0}
.bandblurb{color:var(--mut);margin:.1rem 0 1rem;font-size:.9rem}
.lede{color:var(--mut);margin:.25rem 0 1.5rem}
.cohort{border:1px solid var(--line);border-radius:10px;padding:1rem 1.1rem;
 margin:0 0 1.1rem;background:var(--card);overflow-wrap:anywhere}
.cohort h3{margin:0 0 .2rem;font-size:1rem}
.arrow{color:var(--mut)}
.propose{font-size:.95rem;margin-bottom:.35rem}
.stats{color:var(--mut);font-size:.83rem;margin-bottom:.85rem}
.pair{border-left:3px solid var(--line);padding:.5rem 0 .5rem .75rem;
 margin:.55rem 0}
.pair.corroborated{border-left-color:var(--ok);background:var(--okbg);
 border-radius:0 6px 6px 0}
.lbl{font-size:.66rem;letter-spacing:.09em;color:var(--mut);
 border:1px solid var(--line);border-radius:3px;padding:.05rem .3rem;
 margin-right:.35rem}
.parent{margin:.3rem 0 0 1.4rem;padding-left:.7rem;
 border-left:1px dashed var(--line)}
code{background:var(--code);padding:.1rem .32rem;border-radius:4px;
 font-size:.86em;overflow-wrap:anywhere;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.ids{color:var(--mut);font-size:.8rem;margin-left:.35rem}
.regline{margin:.2rem 0 0 .1rem;font-size:.85rem}
.reg{display:inline-block;margin:.15rem .4rem .15rem 0;padding:.1rem .4rem;
 border:1px solid var(--line);border-radius:5px;background:var(--bg);
 max-width:100%;overflow-wrap:anywhere}
.reg .ids{display:block;margin:0}
.empty{color:var(--mut);font-style:italic}
.clip{color:var(--mut)}
.ok{color:var(--ok);font-weight:600}
.warn{color:var(--warn)}
.meta{margin:.35rem 0 0 .1rem}
.mrow{display:flex;flex-wrap:wrap;gap:.3rem;margin:.2rem 0}
.mf{font-size:.79rem;border:1px solid var(--line);border-radius:5px;
 padding:.08rem .38rem;background:var(--bg);max-width:100%;
 overflow-wrap:anywhere}
.mf b{color:var(--mut);font-weight:600;margin-right:.3rem;font-size:.92em}
.mf.claim{border-color:var(--acc)}
.mf.src{background:var(--acc);color:var(--on-acc)}
.mf.src b{color:var(--on-acc);opacity:.85}
details{margin:.25rem 0 0}
summary{cursor:pointer;color:var(--mut);font-size:.78rem}
.notes{margin:.9rem 0 0;padding:.7rem .8rem;border:1px dashed var(--line);
 border-radius:8px;background:var(--bg)}
.notes label{font-size:.76rem;letter-spacing:.05em;color:var(--mut);
 display:block;margin-bottom:.35rem}
.notes select,.notes textarea{font:inherit;font-size:.87rem;color:var(--fg);
 background:var(--bg);border:1px solid var(--line);border-radius:6px;
 padding:.35rem .5rem;max-width:100%}
.notes select{margin-left:.4rem}
.notes textarea{width:100%;margin-top:.45rem;resize:vertical}
.notes.done{border-style:solid;border-color:var(--ok);background:var(--okbg)}
.callout{border:1px solid var(--line);border-left:3px solid var(--acc);
 border-radius:0 8px 8px 0;padding:.8rem 1rem;margin:1.25rem 0;
 background:var(--card);font-size:.92rem}
#bar{position:sticky;bottom:0;margin-top:2rem;padding:.7rem .9rem;
 background:var(--card);border:1px solid var(--line);border-radius:10px;
 display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
#bar button{font:inherit;font-size:.86rem;padding:.4rem .8rem;border-radius:6px;
 border:1px solid var(--line);background:var(--bg);color:var(--fg);
 cursor:pointer}
#bar button:hover{border-color:var(--acc)}
#cnt{color:var(--mut);font-size:.84rem}
#out{width:100%;margin-top:.6rem;font-size:.78rem;background:var(--code);
 color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:.5rem;
 display:none;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
"""

# EVERY STORAGE CALL SITS INSIDE A `try` BODY, and a test brace-matches this
# script to prove it. `window.localStorage` THROWS `SecurityError` on ACCESS in
# a sandboxed frame or with site data blocked -- it does not return null -- and
# an unguarded throw at load aborts the rest of the script. This script is one
# `forEach` that attaches every listener and both button handlers, so an abort
# inside it leaves a page that renders correctly, accepts typing into every
# field, saves nothing and has two dead buttons. That failure shipped once.
#
# The `if (!w) return;` in `paint` is belt and braces over the class-token
# partition rather than a substitute for it: the partition is what keeps
# `closest` from returning null, and this is what keeps a future violation from
# taking the whole page down with it.
SCRIPT = r"""
<script>
var STORE = null;
try {
  window.localStorage.setItem("__probe", "1");
  window.localStorage.removeItem("__probe");
  STORE = window.localStorage;
} catch (err) { STORE = null; }
function sget(k){ try { return STORE && STORE.getItem(k); } catch (err) { return null; } }
function sset(k, v){ try { if (STORE) STORE.setItem(k, v); } catch (err) { return; } }

var LS = "mode1-review:";
function widgets(){
  return Array.prototype.slice.call(document.querySelectorAll(".notes"));
}
function paint(w){
  if (!w) return;
  var d = w.querySelector(".dec"), n = w.querySelector(".note");
  if (!d || !n) return;
  w.classList.toggle("done", !!(d.value || n.value.trim()));
}
function count(){
  var all = widgets(), n = 0;
  all.forEach(function(w){ if (w.classList.contains("done")) n++; });
  var warn = STORE ? "" : "  -- NOT saved in this browser: export before you close this tab";
  var cnt = document.getElementById("cnt");
  cnt.textContent = n + " of " + all.length + " cohorts annotated" + warn;
  cnt.style.color = STORE ? "" : "#b45309";
}
function build(){
  var rows = [["lab","sample_type","parent_types","assay","field","value","ruling","note"].join("\t")];
  widgets().forEach(function(w){
    var d = w.querySelector(".dec"), n = w.querySelector(".note");
    if (!d || !n) return;
    if (!d.value && !n.value.trim()) return;
    rows.push(d.dataset.k.split("|").concat([d.value, n.value.replace(/\s+/g, " ").trim()]).join("\t"));
  });
  return rows.length > 1 ? rows.join("\n") : "(nothing ruled on yet)";
}
function show(){
  var out = document.getElementById("out");
  out.value = build();
  out.style.display = "block";
  out.focus();
  out.select();
  return out;
}
document.querySelectorAll(".dec, .note").forEach(function(el){
  var kind = el.classList.contains("dec") ? "dec" : "note";
  var key = LS + el.dataset.k + ":" + kind;
  var saved = sget(key);
  if (saved !== null && saved !== undefined) el.value = saved;
  function changed(){ sset(key, el.value); paint(el.closest(".notes")); count(); }
  el.addEventListener("input", changed);
  el.addEventListener("change", changed);
  paint(el.closest(".notes"));
});
count();
document.getElementById("exp").addEventListener("click", show);
document.getElementById("cp").addEventListener("click", function(){
  var out = show(), btn = this;
  var ok = function(){
    btn.textContent = "Copied";
    setTimeout(function(){ btn.textContent = "Copy"; }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(out.value).then(ok, function(){
      try { if (document.execCommand("copy")) ok(); } catch (err) { return; }
    });
  } else {
    try { if (document.execCommand("copy")) ok(); } catch (err) { return; }
  }
});
</script>"""

BAR = """
<div id="bar">
  <button id="exp" type="button">Export rulings</button>
  <button id="cp" type="button">Copy</button>
  <span id="cnt"></span>
  <textarea id="out" rows="10" readonly
     placeholder="The exported rulings appear here"></textarea>
</div>"""


def render(blocks: list[dict]) -> str:
    """The whole page: one file, no network, both themes.

    SELF-CONTAINED BECAUSE OF WHERE IT IS READ. This is opened off a laptop, on
    a train, beside a database the reviewer cannot reach. A CDN font or an
    external stylesheet makes a review surface depend on a network the reviewer
    may not have, and tells a third party which cohorts a curator opened.

    THEME-AWARE BECAUSE THE VIEWER'S THEME IS NOT KNOWABLE HERE, and there are
    three states rather than two: an explicit choice stamps `data-theme` on the
    root, and the default stamps nothing and leaves only `prefers-color-scheme`.
    So the light palette is defined on bare `:root`, the dark one is redefined
    under the media query guarded against an explicit light choice, and again
    under `[data-theme=dark]` so an explicit choice wins in both directions.
    """
    total = sum(b["n_rows"] for b in blocks)
    parts = []
    for band, letter, blurb in BANDS:
        in_band = [b for b in blocks if b["band"] == band]
        if not in_band:
            continue
        rows = sum(b["n_rows"] for b in in_band)
        parts.append(
            f'<h2 class="band b{letter}">{_e(band)} '
            f'<span class="bmeta">{len(in_band)} cohort(s) &middot; '
            f"{rows:,} row(s)</span></h2>"
            f'<p class="bandblurb">{_e(blurb)}</p>')
        for block in in_band:
            parts += _cohort_html(block)

    return (f"<title>Mode 1 review, {len(blocks)} cohorts</title>"
            f"<style>{CSS}</style>"
            f'<h1>Mode 1 &mdash; {len(blocks):,} cohort(s), '
            f"{total:,} proposal(s)</h1>"
            f'<p class="lede">Samples registered in <b>no assay</b> whose own '
            "metadata names one. Every child below is confirmed to hold "
            "<b>no registration</b>; that is what makes it Mode 1. Up to "
            f"{MAX_EXAMPLES} examples per cohort.</p>"
            f"{_CALLOUT}{''.join(parts)}{BAR}{SCRIPT}\n")


_CALLOUT = (
    '<div class="callout">'
    "<b>Nothing here is decided and nothing here writes.</b> Every cohort is a "
    "PROPOSAL awaiting your ruling. A ruling you record below is text you "
    "export and hand on; no stage in this package reads it back, and none of "
    "it reaches MySQL, Neo4j or the API."
    "<br><br>"
    "<b>The proposed assay is an INTERNAL id, and that is not a writable "
    "target.</b> Every registration below is rendered <code>seek &rarr; "
    "internal</code>. A membership row keys on the SEEK id; the internal id is "
    "a harmonisation key this package derives, and one internal id spans up to "
    "23 SEEK records. Approving a cohort here does not name a record to write "
    "to, and for Mode 1 there is no registered neighbour to resolve one from."
    "<br><br>"
    "<b>A green pair means a parent ALREADY holds the proposed assay.</b> Mode "
    "1 outranks the lineage step, so a sample registered in nothing is claimed "
    "by Mode 1 even where a neighbour carries the pair. Where that happens it "
    "is the strongest corroboration a Mode 1 row can have."
    "<br><br>"
    "<b>Metadata is shown for every sample with blanks dropped and counted.</b> "
    "Claim-bearing fields are outlined and the one field that produced THIS "
    "proposal is filled. On a contested cohort the whole question is which "
    "field to believe."
    "<br><br>"
    "<b>Rulings are kept in this browser as you type</b>, and the count at the "
    "bottom says so if they are not. Use <b>Export rulings</b> for a "
    "tab-separated block you can paste back."
    "</div>")


def _cohort_html(block: dict) -> list[str]:
    corroborated = block["n_corroborated_shown"]
    badge = (f'<span class="ok">{corroborated} of {block["shown"]} shown have '
             "a parent ALREADY in this assay</span>" if corroborated else
             '<span class="warn">no shown parent holds this assay</span>')
    out = [
        '<section class="cohort">'
        f'<h3>{_e(block["lab"])} &middot; {_e(block["sample_type"])} '
        f'<span class="arrow">&larr;</span> parent '
        f'{_e(block["parent_types"])}</h3>'
        f'<div class="propose">propose <b>{_e(block["assay"])}</b>'
        f'<span class="ids">from {_e(block["field"])} = '
        f'&ldquo;{_clip(block["value"])}&rdquo;</span></div>'
        f'<div class="stats">{block["n_rows"]:,} row(s) &middot; '
        f'{block["n_samples"]:,} sample(s) &middot; '
        f'{block["n_contested"]:,} contested &middot; tier(s) '
        f'{_e(block["tiers"])} &middot; gate(s) {_e(block["gates"])} &middot; '
        f'{_e(block["dates"])} &middot; showing {block["shown"]} of '
        f'{block["n_rows"]:,} &middot; {badge}</div>'
    ]
    for child in block["children"]:
        out += _child_html(child)
    out.append(_notes_html(block))
    out.append("</section>")
    return out


def write_review(findings: pd.DataFrame, context: dict, out_dir) -> Path:
    """Render the sheet from the frame and write it. -> the path written.

    THERE IS NO `main` IN THIS MODULE AND THAT IS DELIBERATE. Every other
    module in the package has one, and one here would need a findings frame it
    could only get by reading the run's own output back off disk -- which is
    precisely the shape that made the review context and the findings artifact
    disagree about internal assay 30 and 31. `run_detect.main` already holds
    the frame; it passes it, and the sheet has one definition of the run.
    """
    path = Path(out_dir) / REVIEW_NAME
    path.write_text(render(build_blocks(findings, context)))
    return path
