# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The Mode 2 review surface: a cohort csv and a self-contained html sheet.

WHY THIS IS NOT A FLAG ON `review.py`. That module is Mode 1's and asserts Mode
1's invariants -- `_check_no_registrations` raises unless EVERY sample in the
population holds no registration, which is what Mode 1 IS and which every Mode 2
row violates by construction, since a Mode 2 row exists precisely because a
sample IS registered somewhere and a lineage neighbour carries an assay it does
not hold. Its cohort key also requires a non-null `field` and `value`, and 587
of the 611 Mode 2 cohorts are raised by lineage with no metadata term at all.
Adding a mode switch would mean disabling both guards, which is how a guard
stops guarding.

WHAT IS REUSED RATHER THAN REBUILT: `load_context`, `_uid_columns`,
`_parent_types`, `_child`, `_registrations`, `_metadata`, `_cohort_html`, `CSS`,
`BAR` and `SCRIPT` all come from `review.py`. A child rendered here is the same
object rendered there, so a reviewer reads one page shape across both modes and
this file cannot drift into a second definition of "registration".

THE BANDS ARE THE ONE THING THAT MUST NOT BE REUSED, and it is the whole reason
this file has its own `render`. Mode 1's bands describe METADATA FIELD
AGREEMENT -- "Type and Protocol both predict and AGREE", measured coverage and
accuracy for those fields. Not one of those sentences is true of a lineage row,
which carries no metadata term at all. Printing them over a Mode 2 cohort would
be a page whose stated evidence is not the evidence, which is worse than no
banding.

Mode 2's evidence axis is PRECEDENT, named in `precedent.py` as the thing "a
Mode 2 verdict rests on": when the child is in this assay, how often is the
parent in it too. So the bands here are precedent bands, and each blurb states
the rate rather than borrowing a claim about fields.

THE FLOOR IS A CURATOR'S RULING AND NOT A DEFAULT THIS FILE INVENTED. Measured
on the 2026-08-20 extract, 68.7% of the 167,454 Mode 2 rows sit at a propagation
rate of essentially 0.000 and 94.3% below 0.50 -- writing those would create
registrations for which the database holds no example. The operator set the
floor at 0.50 on that measurement; `FLOOR` records it and `main` prints what it
excluded, so a run can never look like it covered everything.

A PRECEDENT FLOOR EXCLUDES A WHOLE LANE, AND THAT IS REPORTED SEPARATELY. 115
Mode 2 rows carry NO propagation rate, and `rate >= floor` is False on a null,
so a floor drops them with the low ones while meaning something entirely
different by it. 107 of the 115 are `CLS_ABSENCE_COMPAT`, proposed BY_CLAIM off
the co-registration table rather than by lineage: they have no propagation rate
because nothing propagated, and their evidence lives in `co_reg_rate` and
`compat_band`. That is not weak evidence, it is OTHER evidence, and folding it
into "below the floor" would hide an entire lane behind a number that does not
describe it. The remaining 8 are lineage rows that genuinely have none.

`main` therefore reports three buckets and never two. Reviewing the
co-registration lane needs its own axis and is not attempted here.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import review as R

FLOOR = 0.50

PRESET_NAME = "mode2-rulings.tsv"
MAX_CHILDREN = 4

CSV_NAME = "mode2-cohorts-to-review.csv"
REVIEW_NAME = "mode2-review.html"

# The storage prefix MUST differ from Mode 1's or the two sheets share a
# keyspace and a Mode 2 ruling silently overwrites a Mode 1 one on a cohort
# whose six-field key happens to match. Substituted rather than re-declared, and
# asserted below, so a rename in `review.py` fails loudly here instead of
# quietly reuniting the two stores.
_LS_MODE1 = 'var LS = "mode1-review:";'
# BUMPED FROM `mode2-review:` ON 2026-08-20, deliberately, and the old store is
# left where it is rather than migrated.
#
# The sheet's script does `saved = sget(key); if (saved !== null) el.value =
# saved`, so STORAGE WINS over anything rendered into the page. That is right --
# a reviewer's typing must survive a rebuild -- and it makes a preset
# unreachable on any cohort already stored. The operator asked for eight of his
# own rulings to be pre-filled with a verdict he had reached on evidence the
# page had been hiding, so the presets have to win exactly once.
#
# A fresh keyspace is how they win without the script ever overriding a stored
# value, which would be the more dangerous mechanism to build. The cost is that
# the v1 store is orphaned, so PRESETS MUST CARRY EVERY RULING ALREADY MADE and
# not only the eight changed -- see `load_presets`, and the assertion in `main`
# that refuses to ship a preset file smaller than the count it was told to
# expect.
_LS_MODE2 = 'var LS = "mode2-review-v2:";'

BAND_A = "A_precedent_0.95+"
BAND_B = "B_precedent_0.90+"
BAND_C = "C_precedent_0.75+"
BAND_D = "D_precedent_0.50+"

BANDS = (
    (BAND_A, "A", "The propagation is all but universal: 95%+ of comparable "
                  "pairs are already registered this way."),
    (BAND_B, "B", "90-95% of comparable pairs already carry it."),
    (BAND_C, "C", "75-90%. A clear majority, and the largest band still "
                  "comfortable to approve in bulk."),
    (BAND_D, "D", "50-75%. A majority, but a thin one -- the pattern holds "
                  "more often than not and no more than that."),
)
BAND_ORDER = {name: i for i, (name, _l, _b) in enumerate(BANDS)}

LINEAGE_FIELD = "(lineage)"

# A MEASUREMENT ASSAY AND ITS ANALYSIS TWIN ARE DIFFERENT ASSAYS WITH DIFFERENT
# MEMBERSHIPS, and proposing one where the other belongs is a defect the
# operator found twice in his first 43 rulings ("should be ADFP Analysis",
# "ADFP Analysis"). `/curate-assay-vocabulary` rule 6 names the hazard and
# tables nine pairs; the tabled nine are exactly the ones whose titles differ by
# the suffix ` Analysis`, so they are DERIVED here rather than copied, and only
# the pairs that do NOT follow the suffix are written down.
#
# Every id below was measured against `assays.parquet` on 2026-08-20 and
# `analysis_twins` ASSERTS both halves still resolve, so a pair that stops
# existing fails the run instead of silently flagging nothing.
EXPLICIT_ANALYSIS_PAIRS = {
    153: 186,   # Antibody-Dependent Functional Profiling (ADFP) -> ADFP Analysis
    106: 104,   # Titer Assay -> Antibody Titer Assay Analysis
    27: 177,    # Fc Receptor Binding Assay -> FC Receptor Binding Analysis
    69: 2,      # Spatial Proteomics -> Analyzed Spatial Proteomics
    138: 185,   # CometChip Assay -> Comet Chip Analysis
    150: 154,   # Antibody-Dependent Neutrophil Phagocytosis (ADNP) -> ... Analysis
    122: 180,   # Cyclic Immunofluorescence (CyCIF) -> cyCIF Analysis
    90: 176,    # Magnetic Resonance Imaging (MRI) -> MRI Analysis
}

ANALYSIS_TYPE_PREFIX = "A."


def analysis_twins(assays: pd.DataFrame) -> dict[int, tuple[int, str]]:
    """measurement internal id -> (analysis twin id, its title).

    The suffix half is DERIVED so a new `X` / `X Analysis` pair is picked up
    without an edit here; the explicit half is written down because no rule
    turns "Antibody-Dependent Functional Profiling (ADFP)" into "ADFP Analysis".
    """
    titles = {int(i): str(t) for i, t in
              zip(assays.internal_assay_id, assays.internal_assay_title)
              if pd.notna(i) and pd.notna(t)}
    by_name = {t.strip().lower(): i for i, t in titles.items()}

    out: dict[int, tuple[int, str]] = {}
    for analysis_id, title in titles.items():
        low = title.strip().lower()
        if low.endswith(" analysis"):
            measurement = by_name.get(low[: -len(" analysis")])
            if measurement is not None:
                out[measurement] = (analysis_id, title)
    for measurement, analysis_id in EXPLICIT_ANALYSIS_PAIRS.items():
        if measurement not in titles or analysis_id not in titles:
            raise ValueError(
                f"EXPLICIT_ANALYSIS_PAIRS names {measurement} -> {analysis_id} "
                "and one of them is not an internal assay on this extract. A "
                "pair that stopped existing must fail the run, not silently "
                "flag nothing.")
        out[measurement] = (analysis_id, titles[analysis_id])
    return out


def _band(rate: float) -> str:
    if rate >= 0.95:
        return BAND_A
    if rate >= 0.90:
        return BAND_B
    if rate >= 0.75:
        return BAND_C
    return BAND_D


def load_presets(path) -> dict[str, tuple[str, str]]:
    """cohort key -> (ruling, note), from a sheet EXPORT fed back in.

    The file is the sheet's own export format verbatim -- the six key columns
    then `ruling` and `note` -- so a reviewer round-trips their work by pasting
    the export back into a file, with no second format to learn and no importer
    to keep in step with the exporter.

    Returns {} when the file is absent, which is the normal case: presets exist
    only because a rebuild orphaned a store, and a run without one is not an
    error.
    """
    path = Path(path)
    if not path.exists():
        return {}
    frame = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    columns = list(frame.columns)
    # BOTH SHAPES ARE READ. The sheet gained a `cohort_key` column; the rulings
    # exported before it did not carry one, and those files are a human's
    # judgement that no run regenerates. Refusing them to keep one code path
    # would strand the only copy of that judgement.
    if columns not in (list(R.EXPORT_COLUMNS), list(R.LEGACY_EXPORT_COLUMNS)):
        raise ValueError(
            f"{path} has columns {columns}; the sheet exports "
            f"{list(R.EXPORT_COLUMNS)}, or {list(R.LEGACY_EXPORT_COLUMNS)} if "
            "it was exported before the sheet carried the key. The preset "
            "file IS an export -- paste it unchanged.")
    known = {value for value, _label in R.RULING_OPTIONS}
    bad = sorted({r for r in frame.ruling if r not in known})
    if bad:
        raise ValueError(
            f"{path} carries ruling(s) the sheet cannot render: {bad}. "
            f"RULING_OPTIONS is {sorted(known)}.")

    out = {}
    for i, row in frame.iterrows():
        # ONE DEFINITION: the key is `R.cohort_key` over the row's own six
        # fields, here as everywhere else. When the file also carries the key
        # the two are CHECKED AGAINST EACH OTHER rather than one being picked
        # -- a row edited on one side only is a ruling on a cohort nobody
        # ruled, and either choice files it silently against the wrong pair.
        key = R.cohort_key(row)
        if R.KEY_COLUMN in columns and row[R.KEY_COLUMN] != key:
            raise ValueError(
                f"{path} row {i}: the {R.KEY_COLUMN} column says "
                f"{row[R.KEY_COLUMN]!r} and the row's own six key fields join "
                f"to {key!r}. The key disagrees with the row it sits on, so "
                "one of the two was hand-edited; filing this ruling against "
                "either would record it on a cohort nobody ruled.")
        out[key] = (row["ruling"], row["note"])
    return out


def _children_index(context: dict) -> dict[int, set]:
    """sample_id -> its children, INVERTED from `parents_of`.

    `lineage.lineage_index` returns a children map and `review.load_context`
    discards it. Inverting the parents map it does keep is one definition read
    backwards rather than a second traversal of the edge frame, which is the
    rule this package keeps about indexes.
    """
    out: dict[int, set] = defaultdict(set)
    for child, parents in context["parents_of"].items():
        for parent in parents or ():
            out[int(parent)].add(int(child))
    return dict(out)


def check_presets(presets: dict, blocks: list[dict], expect: int = 0) -> None:
    """Refuse to ship a preset file that would LOSE a ruling. Raises or returns.

    Both failures are silent by default and both destroy work, which is why
    they are checks rather than warnings.

    SHORT FILE. The storage prefix is bumped whenever presets must win over an
    orphaned store, so the previous store stops being read -- and any ruling not
    in the preset file is simply gone from the reviewer's page. `expect` is the
    count the caller believes was already made.

    UNMATCHED KEY. A preset naming no cohort renders nowhere, so the ruling is
    dropped with nothing on the page to notice. That happens when the cohort key
    changes, or when the floor moves and takes a ruled cohort off the sheet --
    the second is easy to do by accident and impossible to see afterwards.
    """
    if len(presets) < int(expect):
        raise ValueError(
            f"the preset file carries {len(presets)} ruling(s) and {expect} "
            "were expected. The storage prefix changes with this sheet, so "
            "every ruling already made must be in the preset file or it is "
            "LOST. Export the current sheet and pass the full file.")
    unmatched = sorted(set(presets) - {R.cohort_key(b) for b in blocks})
    if unmatched:
        raise ValueError(
            f"{len(unmatched)} preset(s) name no cohort on this sheet, so "
            f"those rulings would vanish: {unmatched[:3]}")


def _neighbour_index(context: dict) -> dict[str, int]:
    """uuid -> sample_id, the inverse of `context["uuid_of"]`.

    The findings frame names the lineage neighbour by UUID and every index in
    `load_context` is keyed by sample id, so exactly one inversion is needed.
    It is built once per run rather than per row.
    """
    return {uuid: sid for sid, uuid in context["uuid_of"].items()}


def _pair(row, context, sid_of, twins, children_of, proposed_holders) -> dict:
    """One example, rendered as the WRITE TARGET beside its EVIDENCE.

    THIS IS THE CORRECTION THAT COST TEN RULINGS. The first cut reused
    `review._child`, which walks the sample's PARENTS -- correct for Mode 1,
    where the evidence is a parent, and wrong for half of Mode 2. On an
    ADD_PARENT row the row's own sample IS the parent being written to and the
    evidence is its CHILD, so the page reported "no shown parent holds this
    assay" while the child holding it sat one hop away, unrendered. The operator
    rejected ten cohorts asking to see exactly that child.

    `lineage` names the direction and it is 1:1 with the action, measured over
    all 167,347 rows: LIN_CHILD <-> ADD_PARENT_TO_ASSAY (54,852), LIN_PARENT
    <-> ADD_CHILD_TO_ASSAY (112,495). So the neighbour is read off the row
    rather than guessed from the type.

    `neighbour_holds` is True on every Mode 2 row by construction -- the
    neighbour carrying the assay is WHY the row exists -- and it is rendered
    anyway. It is not a discriminator and the page must not imply it is; it is
    the evidence the reviewer asked to see, and its VALUE is in the neighbour's
    uuid and TYPE, which is what the operator actually reasons about ("if this
    has a child that is A.TITR, then yes").
    """
    nb_uuid = None if pd.isna(row.lineage_neighbour_uuid) else str(
        row.lineage_neighbour_uuid)
    nb_sid = sid_of.get(nb_uuid) if nb_uuid else None
    proposed = row.proposed_internal_assay_id
    proposed = int(proposed) if pd.notna(proposed) else None

    nb_regs, nb_hidden = ((R._registrations(nb_sid, context)) if nb_sid
                          else ([], 0))

    # THE SECOND HOP. The operator rejected two cohorts on "depends on what the
    # CELs children are" -- a question about the row sample's OWN children, one
    # hop past the neighbour, which no view built so far could answer. On an
    # ADD_CHILD row the row sample IS the child, so its children are the only
    # place the answer can come from.
    kids = sorted(children_of.get(int(row.sample_id), ()))[:MAX_CHILDREN]
    children = [{
        "uuid": context["uuid_of"].get(k, str(k)),
        "type": context["types"].get(context["uuid_of"].get(k, ""), R.UNTYPED),
        "holds": bool(proposed is not None and k in proposed_holders),
    } for k in kids]
    n_kids = len(children_of.get(int(row.sample_id), ()))
    own, own_hidden = R._registrations(row.sample_id, context)
    twin = twins.get(proposed)
    sample_type = str(row.sample_type)
    return {
        "uuid": str(row.uuid),
        "sample_id": int(row.sample_id),
        "sample_type": sample_type,
        "projects": "--" if pd.isna(row.project_ids) else str(row.project_ids),
        "action": str(row.action),
        # which of the two is being WRITTEN to, in the reviewer's words
        "target_role": ("PARENT" if str(row.action) == "ADD_PARENT_TO_ASSAY"
                        else "CHILD"),
        "neighbour_role": ("CHILD" if str(row.action) == "ADD_PARENT_TO_ASSAY"
                           else "PARENT"),
        "own_regs": own, "n_own_regs_hidden": own_hidden,
        "meta": R._metadata(row.sample_id, context),
        "neighbour_uuid": nb_uuid,
        "neighbour_type": context["types"].get(nb_uuid, R.UNTYPED)
                          if nb_uuid else None,
        "neighbour_regs": nb_regs, "n_neighbour_regs_hidden": nb_hidden,
        "neighbour_meta": R._metadata(nb_sid, context) if nb_sid else {},
        "neighbour_holds": bool(
            proposed is not None
            and any(reg["internal"] == proposed for reg in nb_regs)),
        # the measurement-vs-analysis flag
        "children": children,
        "n_children": n_kids,
        "n_children_hidden": max(0, n_kids - len(children)),
        "n_children_holding": sum(1 for c in children if c["holds"]),
        "twin_id": None if twin is None else twin[0],
        "twin_title": None if twin is None else twin[1],
        "type_is_analysis": sample_type.startswith(ANALYSIS_TYPE_PREFIX),
    }


def label_mode2(findings: pd.DataFrame, context: dict,
                floor: float = FLOOR) -> pd.DataFrame:
    """Mode 2 rows at or above `floor`, carrying the six cohort key columns.

    EXTRACTED SO THE ROW->COHORT ASSIGNMENT HAS ONE DEFINITION. `build_blocks`
    groups on these columns and returns only aggregates, so a caller needing to
    know WHICH rows a ruled cohort holds -- the registration set is built per
    row, not per cohort -- had no way to ask, and the obvious workaround is to
    re-derive `lab`, `parent_types`, `field` and `value` beside it. That is the
    second key definition `review.cohort_key` exists to prevent, and it would
    disagree with the first the day either changes.

    Returns the labelled frame, empty if nothing clears the floor. `build_blocks`
    groups it; `approved_rows` filters it. Neither spells the derivation itself.
    """
    m2 = findings[(findings["mode"] == S.MODE_2)
                  & (findings.precedent_rate >= floor)].copy()
    if m2.empty:
        return m2

    uid = R._uid_columns(m2.uuid)
    m2["lab"] = uid["lab"].values
    m2["date"] = uid["date"].values
    m2["parent_types"] = [R._parent_types(s, context) for s in m2.sample_id]
    m2["assay"] = m2.proposed_internal_assay_title.astype(str)
    m2["field"] = [f if isinstance(f, str) and f else LINEAGE_FIELD
                   for f in m2.source_field]
    m2["value"] = [v if isinstance(v, str) and v else str(a)
                   for v, a in zip(m2.raw_value, m2.action)]
    m2["band"] = [_band(r) for r in m2.precedent_rate]
    m2["contested_flag"] = m2.contested.fillna(False).astype(bool)
    return m2


def build_blocks(findings: pd.DataFrame, context: dict,
                 floor: float = FLOOR) -> list[dict]:
    """Mode 2 rows at or above `floor`, grouped into review cohorts.

    The key is Mode 1's six fields, with the last two carrying what a lineage
    row has instead of a term: `field` is `(lineage)` and `value` is the ACTION.
    The action belongs in the key because ADD_PARENT and ADD_CHILD are different
    writes against the same pair, and a cohort pooling them would take one
    ruling for two decisions.
    """
    m2 = label_mode2(findings, context, floor)
    if m2.empty:
        return []

    sid_of = _neighbour_index(context)
    twins = context.get("analysis_twins", {})
    children_of = _children_index(context)
    # sample ids holding each proposed assay, so the second hop can be answered
    # without a per-child registration scan inside the loop
    wanted = {int(a) for a in m2.proposed_internal_assay_id.dropna().unique()}
    proposed_holders = {
        a: {sid for sid, regs in context["registrations"].items()
            if any(r[1] == a for r in regs)}
        for a in wanted}

    blocks = []
    for key, rows in m2.groupby(list(R.BLOCK_KEY), dropna=False, sort=False):
        rows = rows.sort_values("sample_id")
        examples = rows.head(R.MAX_EXAMPLES)
        children = [_pair(r, context, sid_of, twins, children_of,
                          proposed_holders.get(
                              int(r.proposed_internal_assay_id)
                              if pd.notna(r.proposed_internal_assay_id) else -1,
                              set()))
                    for r in examples.itertuples(index=False)]
        dates = sorted(rows.date.unique())
        blocks.append(dict(
            zip(R.BLOCK_KEY, (str(k) for k in key)),
            # banded by its STRONGEST row, as Mode 1 is: the band is a reading
            # order, and the spread it was chosen from travels in `precedent`.
            band=min(rows.band, key=BAND_ORDER.__getitem__),
            n_rows=int(len(rows)),
            n_samples=int(rows.sample_id.nunique()),
            n_contested=int(rows.contested_flag.sum()),
            precedent_min=float(rows.precedent_rate.min()),
            precedent_max=float(rows.precedent_rate.max()),
            # `tiers` and `gates` are the columns `_cohort_html` prints. A
            # lineage row has no claim and therefore neither, and the honest
            # rendering of "no claim" is the words, not a blank that reads as a
            # missing value.
            tiers=";".join(sorted({str(t) for t in rows.claim_tier
                                   if pd.notna(t)})) or "NO_CLAIM",
            gates=";".join(sorted({str(g) for g in rows.gate
                                   if pd.notna(g)})) or "NO_CLAIM",
            dates=dates[0] if len(dates) == 1 else f"{dates[0]}-{dates[-1]}",
            n_dates=len(dates),
            shown=len(children),
            n_corroborated_shown=sum(1 for c in children
                                     if c["neighbour_holds"]),
            # the measurement-vs-analysis flag rides on the COHORT because it is
            # a property of (sample type, proposed assay) and not of a sample
            twin_id=children[0]["twin_id"],
            twin_title=children[0]["twin_title"],
            flag_analysis_twin=bool(children[0]["type_is_analysis"]
                                    and children[0]["twin_id"] is not None),
            children=children,
        ))

    total = sum(b["n_rows"] for b in blocks)
    if total != len(m2):
        raise ValueError(
            f"the cohorts hold {total:,} rows and the population at floor "
            f"{floor} is {len(m2):,}. Every finding must land in exactly one "
            "cohort: a surface that double-counts invites two rulings on one "
            "proposal, and one that under-counts hides proposals the run made.")
    if len({R.cohort_key(b) for b in blocks}) != len(blocks):
        raise ValueError("two cohorts share a key; their rulings would collide")

    blocks.sort(key=lambda b: (BAND_ORDER[b["band"]], -b["n_rows"],
                               R.cohort_key(b)))
    return blocks


def to_csv(blocks: list[dict], presets: dict | None = None) -> pd.DataFrame:
    """The cohort csv -- the operator reads this BEFORE the sheet.

    One row per cohort, carrying the key, the size, the precedent range that
    banded it, and empty `ruling` and `note` columns to fill in. It holds no
    per-sample examples on purpose: this is the triage pass, and the examples
    are what the html is for.
    """
    presets = presets or {}
    return pd.DataFrame([{
        # THE KEY LEADS, and it is `R.cohort_key` and never a join written
        # here. `ingest` refuses whole-file without this column, so a sheet
        # that omits it cannot be read back by the ingester this mode
        # documents -- which is exactly what RUN2 hit, and worked around by
        # hand. A second join written locally is the other half of that
        # failure: one edit away from keying rulings differently from storage.
        R.KEY_COLUMN: (key := R.cohort_key(b)),
        "band": b["band"],
        "lab": b["lab"], "sample_type": b["sample_type"],
        "parent_types": b["parent_types"], "assay": b["assay"],
        "field": b["field"], "value": b["value"],
        "n_rows": b["n_rows"], "n_samples": b["n_samples"],
        "precedent_min": round(b["precedent_min"], 4),
        "precedent_max": round(b["precedent_max"], 4),
        "n_contested": b["n_contested"],
        "neighbour_role": b["children"][0]["neighbour_role"],
        "neighbours_holding_it": f'{b["n_corroborated_shown"]}/{b["shown"]}',
        "example_neighbours": ";".join(
            str(c["neighbour_uuid"]) for c in b["children"]),
        "example_neighbour_types": ";".join(
            str(c["neighbour_type"]) for c in b["children"]),
        "FLAG_analysis_twin": (b["twin_title"] if b["flag_analysis_twin"]
                               else ""),
        "tiers": b["tiers"], "gates": b["gates"], "dates": b["dates"],
        "example_uuids": ";".join(c["uuid"] for c in b["children"]),
        "ruling": presets.get(key, ("", ""))[0],
        "note": presets.get(key, ("", ""))[1],
    } for b in blocks])


def _pair_html(pair: dict) -> list[str]:
    """The write target with its own children, then the neighbour that is the
    evidence for it.

    THE LABELS ARE COMPUTED, NEVER CONSTANT. `review._child_html` prints CHILD
    then PARENT because in Mode 1 that is always what they are. In Mode 2 the
    row's own sample is the PARENT on an ADD_PARENT row, so a constant label is
    wrong on 54,852 of 167,347 rows -- and wrong in the direction that hides the
    evidence, which is how ten cohorts came back rejected for want of it.

    THE SECOND HOP IS RENDERED INSIDE THE TARGET'S OWN BLOCK, and that placement
    is the fix for a defect the operator caught on sight. It shipped once as a
    SIBLING of the neighbour block, at almost the same indent (`.kids` 1.1rem
    against `.parent` 1.4rem) and after the neighbour's metadata, so it read as
    the NEIGHBOUR's children -- on a page whose entire purpose is telling a
    reviewer which sample a fact is about. Nesting it inside the target's div
    and naming the sample in the label makes the ownership structural rather
    than a matter of reading the indentation correctly.
    """
    role = pair["target_role"]
    nb_role = pair["neighbour_role"]

    # the second hop: types, and whether each child holds the proposed assay,
    # is the whole question, so no metadata is expanded here
    if pair["children"]:
        held = pair["n_children_holding"]
        kids = ", ".join(
            f'<code>{R._e(c["uuid"])}</code> '
            f'<span class="{"ok" if c["holds"] else "mut"}">{R._e(c["type"])}'
            f'{" &check;" if c["holds"] else ""}</span>'
            for c in pair["children"])
        more = (f' &middot; {pair["n_children_hidden"]} more of '
                f'{pair["n_children"]}' if pair["n_children_hidden"] else "")
        kids_html = (
            f'<div class="kids"><span class="lbl">CHILDREN OF '
            f'{R._e(pair["uuid"])}</span> {kids}{more} &middot; '
            f'{held} of {len(pair["children"])} shown hold the proposed assay'
            "</div>")
    else:
        kids_html = (
            f'<div class="kids"><span class="lbl">CHILDREN OF '
            f'{R._e(pair["uuid"])}</span> <span class="empty">none</span></div>')

    out = [
        f'<div class="pair{" corroborated" if pair["neighbour_holds"] else ""}">',
        f'<div class="child"><span class="lbl">{R._e(role)} &mdash; WRITE HERE'
        f'</span> <code>{R._e(pair["uuid"])}</code>'
        f'<span class="ids">{R._e(pair["sample_type"])} &middot; project '
        f'{R._e(pair["projects"])} &middot; {R._e(pair["action"])}</span>'
        '<div class="regline">holds: '
        f'{R._registrations_html(pair["own_regs"], pair["n_own_regs_hidden"])}'
        "</div>"
        f'{R._metadata_html(pair["meta"])}'
        f'{kids_html}'
        "</div>",
    ]
    if not pair["neighbour_uuid"]:
        out.append('<div class="parent"><span class="empty">'
                   "no lineage neighbour on this row</span></div>")
    else:
        holds = ('<span class="ok">holds the proposed assay</span>'
                 if pair["neighbour_holds"] else
                 '<span class="warn">does NOT hold the proposed assay</span>')
        out.append(
            f'<div class="parent"><span class="lbl">{R._e(nb_role)} &mdash; '
            f'THE EVIDENCE</span> <code>{R._e(pair["neighbour_uuid"])}</code>'
            f'<span class="ids">{R._e(pair["neighbour_type"])} &middot; '
            f'{holds}</span>'
            '<div class="regline">holds: '
            f'{R._registrations_html(pair["neighbour_regs"], pair["n_neighbour_regs_hidden"])}'
            "</div>"
            f'{R._metadata_html(pair["neighbour_meta"])}'
            "</div>")
    out.append("</div>")
    return out


def _notes_html(block: dict, presets: dict) -> str:
    """The ruling control, with a PRESET rendered as the selected option.

    `review._notes_html` renders every option unselected and lets the script
    restore from storage. This one also accepts a preset, and marks it both in
    the markup AND visibly on the page, because a verdict that appears in a
    reviewer's export without their having chosen it must not be silent.

    `selected` is emitted ONLY for a real ruling, never for the empty option --
    which is the first one and therefore already the default. The token then
    means "a preset chose this" rather than "this is first", which is what makes
    it testable.
    """
    key = R.cohort_key(block)
    ruling, note = presets.get(key, ("", ""))
    options = "".join(
        f'<option value="{R._e(value)}"'
        f'{" selected" if ruling and value == ruling else ""}>'
        f'{R._e(label)}</option>'
        for value, label in R.RULING_OPTIONS)
    banner = ("" if not ruling else
              f'<div class="preset">pre-filled <b>{R._e(ruling)}</b> from your '
              "earlier export &mdash; change it if it is wrong</div>")
    return (
        f'<div class="notes{" done" if ruling or note else ""}">{banner}'
        f'<label>ruling <select class="dec" data-k="{R._e(key)}">{options}'
        "</select></label>"
        f'<textarea class="note" data-k="{R._e(key)}" rows="2" '
        'placeholder="Why. What the right answer is, if it is not this one."'
        f">{R._e(note)}</textarea></div>")


def _cohort_html(block: dict, presets: dict) -> list[str]:
    held = block["n_corroborated_shown"]
    badge = (f'<span class="ok">{held} of {block["shown"]} shown have a '
             f'{R._e(block["children"][0]["neighbour_role"].lower())} ALREADY '
             "in this assay</span>" if held else
             '<span class="warn">no shown neighbour holds this assay</span>')
    out = [
        '<section class="cohort">'
        f'<h3>{R._e(block["lab"])} &middot; {R._e(block["sample_type"])} '
        f'<span class="arrow">&larr;</span> parent '
        f'{R._e(block["parent_types"])}</h3>'
        f'<div class="propose">propose <b>{R._e(block["assay"])}</b>'
        f'<span class="ids">from {R._e(block["field"])} = '
        f'&ldquo;{R._clip(block["value"])}&rdquo; &middot; precedent '
        f'{block["precedent_min"]:.3f}&ndash;{block["precedent_max"]:.3f}'
        "</span></div>"
    ]
    if block["flag_analysis_twin"]:
        out.append(
            '<div class="callout"><b>Check the assay, not just the pair.</b> '
            f'This is an <code>{R._e(block["sample_type"])}</code> sample &mdash; '
            "an ANALYSIS type &mdash; proposed into a MEASUREMENT assay whose "
            f'analysis twin exists: <b>{R._e(block["twin_title"])}</b> '
            f'(internal {block["twin_id"]}). A measurement assay and its '
            "analysis twin are different assays with different memberships."
            "</div>")
    out.append(
        f'<div class="stats">{block["n_rows"]:,} row(s) &middot; '
        f'{block["n_samples"]:,} sample(s) &middot; tier(s) '
        f'{R._e(block["tiers"])} &middot; gate(s) {R._e(block["gates"])} '
        f'&middot; {R._e(block["dates"])} &middot; showing {block["shown"]} '
        f'of {block["n_rows"]:,} &middot; {badge}</div>')
    for pair in block["children"]:
        out += _pair_html(pair)
    out.append(_notes_html(block, presets))
    out.append("</section>")
    return out


def render(blocks: list[dict], floor: float = FLOOR,
           excluded: int | None = None, no_rate: int | None = None,
           presets: dict | None = None) -> str:
    """The whole page: one file, no network, both themes. See `review.render`."""
    assert _LS_MODE1 in R.SCRIPT, (
        "review.SCRIPT no longer declares the Mode 1 storage prefix verbatim, "
        "so this module cannot rebind it and the two sheets would SHARE a "
        "keyspace -- a Mode 2 ruling would overwrite a Mode 1 one. Re-pin it.")
    script = R.SCRIPT.replace(_LS_MODE1, _LS_MODE2)

    presets = presets or {}
    total = sum(b["n_rows"] for b in blocks)
    parts = []
    for band, letter, blurb in BANDS:
        in_band = [b for b in blocks if b["band"] == band]
        if not in_band:
            continue
        rows = sum(b["n_rows"] for b in in_band)
        parts.append(
            f'<h2 class="band b{letter}">{R._e(band)} '
            f'<span class="bmeta">{len(in_band)} cohort(s) &middot; '
            f"{rows:,} row(s)</span></h2>"
            f'<p class="bandblurb">{R._e(blurb)}</p>')
        for block in in_band:
            parts += _cohort_html(block, presets)

    excl = ("" if excluded is None else
            f" {excluded:,} row(s) below the floor are NOT on this page.")
    if no_rate:
        excl += (f" A further {no_rate:,} carry NO propagation rate at all -- "
                 "mostly the co-registration lane, whose evidence is a "
                 "different measure and which this page does not rank.")
    return (f"<title>Mode 2 review, {len(blocks)} cohorts</title>"
            f"<style>{R.CSS}{_CSS_EXTRA}</style>"
            f'<h1>Mode 2 &mdash; {len(blocks):,} cohort(s), '
            f"{total:,} proposal(s)</h1>"
            f'<p class="lede">Samples that ARE registered somewhere, whose '
            "lineage neighbour carries an assay they do not hold. Banded by "
            "<b>propagation rate</b>: when the child is in this assay, how "
            f"often the parent is too. Floor {floor:g}.{R._e(excl)} Up to "
            f"{R.MAX_EXAMPLES} examples per cohort.</p>"
            f"{_CALLOUT}{''.join(parts)}{R.BAR}{script}\n")


_CSS_EXTRA = """
.kids{margin:.4rem 0 .1rem 0;padding:.25rem .5rem;font-size:.83rem;
 color:var(--mut);line-height:1.7;background:var(--code);border-radius:4px}
.kids .lbl{margin-right:.4rem}
.kids .mut{color:var(--mut)}
.kids .ok{color:var(--ok);font-weight:600}
.preset{font-size:.8rem;color:var(--warn);margin-bottom:.35rem}
"""


_CALLOUT = (
    '<div class="callout">'
    "<b>Nothing here is decided and nothing here writes.</b> Every cohort is a "
    "PROPOSAL awaiting your ruling. A ruling you record below is text you "
    "export and hand on; no stage in this package reads it back, and none of "
    "it reaches MySQL, Neo4j or the API."
    "<br><br>"
    "<b>The proposed assay is an INTERNAL id, and that is not a writable "
    "target.</b> Every registration below is rendered <code>seek &rarr; "
    "internal</code>. A membership row keys on the SEEK id; one internal id "
    "spans up to 23 SEEK records. Unlike Mode 1, a Mode 2 row DOES have a "
    "registered neighbour to resolve one from &mdash; that is the rule the "
    "design states and no stage implements yet."
    "<br><br>"
    "<b>A green pair means the neighbour ALREADY holds the proposed assay.</b> "
    "For an ADD_CHILD row that neighbour is the whole evidence, so a cohort "
    "showing green throughout is the strongest shape Mode 2 has."
    "<br><br>"
    "<b>The floor is a ruling, not a filter this tool chose.</b> 68.7% of all "
    "Mode 2 rows sit at a propagation rate of essentially zero and 94.3% below "
    "0.50; those name registrations the database holds no example of."
    "</div>")


def main(artifacts="assay-hygiene", extract=None, floor: float = FLOOR,
         expect_presets: int = 0) -> int:
    a = Path(artifacts)
    e = Path(extract) if extract else a / "extract"
    findings = pd.read_csv(a / "findings.csv", low_memory=False)
    m2 = findings[findings["mode"] == S.MODE_2]
    all_m2 = int(len(m2))
    # THREE buckets, never two. See the module docstring: a null rate is not a
    # low one, and 107 of the 115 nulls are a different lane entirely.
    below = int((m2.precedent_rate < floor).sum())
    no_rate = int(m2.precedent_rate.isna().sum())
    no_rate_compat = int((m2.precedent_rate.isna()
                          & (m2.classification == S.CLS_ABSENCE_COMPAT)).sum())

    context = R.load_context(e)
    context["analysis_twins"] = analysis_twins(
        pd.read_parquet(e / "assays.parquet"))
    blocks = build_blocks(findings, context, floor=floor)
    kept = sum(b["n_rows"] for b in blocks)
    if kept + below + no_rate != all_m2:
        raise ValueError(
            f"{kept:,} kept + {below:,} below the floor + {no_rate:,} with no "
            f"rate != {all_m2:,} Mode 2 rows. Every row must be accounted for "
            "in exactly one bucket, or this run is hiding proposals behind a "
            "number that does not describe them.")

    presets = load_presets(a / PRESET_NAME)
    check_presets(presets, blocks, expect_presets)

    to_csv(blocks, presets).to_csv(a / CSV_NAME, index=False)
    (a / REVIEW_NAME).write_text(
        render(blocks, floor=floor, excluded=below, no_rate=no_rate,
               presets=presets))
    print(f"wrote {a / CSV_NAME} and {a / REVIEW_NAME}")
    if presets:
        print(f"  PRE-FILLED {len(presets)} ruling(s) from {PRESET_NAME}; the "
              "sheet's storage prefix is bumped so they take effect")
    print(f"  {len(blocks):,} cohort(s), {kept:,} row(s) at precedent >= {floor:g}")
    print(f"  EXCLUDED {below:,} of {all_m2:,} Mode 2 row(s) BELOW the floor")
    print(f"  EXCLUDED {no_rate:,} more carrying NO propagation rate at all, "
          f"{no_rate_compat:,} of them CLS_ABSENCE_COMPAT -- the "
          f"co-registration lane, whose evidence is co_reg_rate and which a "
          f"precedent floor cannot rank. NOT reviewed here.")
    for band, _l, _b in BANDS:
        n = [b for b in blocks if b["band"] == band]
        if n:
            print(f"  {band:20s} {len(n):>4} cohort(s)  "
                  f"{sum(b['n_rows'] for b in n):>7,} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
