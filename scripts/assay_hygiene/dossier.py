# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""One reviewable dossier per Mode 2 cohort: three hops and everyone's assays.

WHY THIS EXISTS. The review sheet asks a human "should this sample be in this
assay" and hands them the sample, its lineage neighbour and the precedent rate.
That works at 111 cohorts and does not work at 901, which is where the operator
stopped: "there is no possible way I can manually review 901 cohorts."

The question itself is not hard -- `DNA` missing `Short Read Sequencing` is
plainly a gap, `D.IMG` missing `Tissue Collection` is plainly not -- it is
domain reading, repeated 901 times. So this module packages each cohort as a
self-contained dossier that a reader can answer from, WITHOUT a database.

WHAT A DOSSIER CARRIES, and why each part is needed:

  the_evidence          the SPECIFIC relative that raised this proposal, named
                        by the finding row rather than guessed from a capped
                        list, with whether it holds the assay. Without it 86
                        cohorts asked the question with the answer invisible.
  the three hops        parent -> sample -> child, with the TYPE and the
                        REGISTERED ASSAYS of all three. This is the operator's
                        own framing and it is the thing the sheet was missing:
                        an assay's rightness depends on what the sample IS and
                        what sits either side of it in the chain.
  the precedent counts  not just the rate. `0.000 over 3 pairs` and `0.000 over
                        71,499 pairs` are different facts and the rate hides it.
  the metadata          the sample's own fields, which frequently name the assay
                        outright.
  the direction         ADD_PARENT and ADD_CHILD are different questions.
                        Measured over the operator's 111 rulings: ADD_PARENT
                        approved 72/74, ADD_CHILD 28/37. The asymmetry is real
                        and a reader must know which one they are looking at.

PUNTING IS A FIRST-CLASS ANSWER. A reader who cannot tell must say so rather
than guess, because the output of this is a database write. `UNSURE` costs one
cohort of human attention; a wrong `APPROVE` costs a wrong registration on every
row in the cohort, up to 29,763 of them.

NOTHING HERE DECIDES ANYTHING. This module builds evidence packets. It holds no
verdict logic and writes to no database.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import review as R
from . import review_mode2 as M2

MAX_EXAMPLES = 3
MAX_RELATIVES = 4
MAX_META_FIELDS = 12
MAX_META_CHARS = 140
DOSSIER_NAME = "mode2-dossiers.json"


SIBLING_OVERLAP = 0.6
MAX_SIBLINGS = 6
MAX_TYPE_ASSAYS = 8


def _title_tokens(title: str) -> set:
    """Words that distinguish one assay title from another.

    `assay` and `analysis` are dropped: they are the two words that appear
    across the whole vocabulary and would make everything look alike, and
    `analysis` in particular is the exact distinction a sibling list exists to
    SURFACE rather than to collapse.
    """
    return set(re.findall(r"[a-z]+", title.lower())) - {
        "assay", "analysis", "the", "of", "and", "a", "for", "in"}


def sibling_assays(assays: pd.DataFrame) -> dict[int, list[dict]]:
    """internal id -> the assays whose NAME is close enough to be confusable.

    62 of the 137 internal assays sit in such a pair on the 2026-08-20 extract.
    A reader handed one title and asked "does this belong" cannot answer well
    without knowing that `MALDI Mass Spectrometry Imaging`, `High Resolution
    Mass Spectrometry (HRMS)` and `Mass Spectrometry Analysis` all exist beside
    `Mass Spectrometry` -- the question is usually WHICH of them, not whether.
    """
    titles = {int(i): str(t) for i, t in
              zip(assays.internal_assay_id, assays.internal_assay_title)
              if pd.notna(i) and pd.notna(t)}
    toks = {i: _title_tokens(t) for i, t in titles.items()}
    out: dict[int, list[dict]] = defaultdict(list)
    for i, a_t in toks.items():
        if not a_t:
            continue
        for j, b_t in toks.items():
            if i == j or not b_t:
                continue
            if len(a_t & b_t) / min(len(a_t), len(b_t)) >= SIBLING_OVERLAP:
                out[i].append({"internal_id": j, "title": titles[j]})
    return {k: v[:MAX_SIBLINGS] for k, v in out.items()}


def type_assay_counts(membership, assays, nodes) -> dict:
    """(sample_type, internal assay id) -> how many samples the house registers.

    THIS IS THE HOUSE CONVENTION, AS DATA. The agents' one consistent weakness
    in calibration was not knowing it: they approved NHP into Tissue Collection
    on sound biology, where the house puts NHP in Patient Visit 616 times and in
    Tissue Collection 54. Nobody has to write that rule down -- the memberships
    already state it, and stating it as a COUNT rather than a rule keeps "rare"
    distinguishable from "never".
    """
    idx = assays.dropna(subset=["internal_assay_id"]).set_index("assay_id")
    j = membership.join(idx[["internal_assay_id"]], on="assay_id").dropna(
        subset=["internal_assay_id"])
    types = dict(zip(nodes.sample_id, nodes.type))
    j = j.assign(type=j.sample_id.map(types)).dropna(subset=["type"])
    pair = j.groupby(["type", "internal_assay_id"]).sample_id.nunique()
    by_type: dict[str, list] = defaultdict(list)
    titles = {int(i): str(t) for i, t in
              zip(assays.internal_assay_id, assays.internal_assay_title)
              if pd.notna(i) and pd.notna(t)}
    for (t, aid), n in pair.items():
        by_type[str(t)].append((titles.get(int(aid), str(int(aid))), int(aid),
                                int(n)))
    for t in by_type:
        by_type[t].sort(key=lambda x: -x[2])
    return {"pair": {(str(t), int(a)): int(n) for (t, a), n in pair.items()},
            "by_type": dict(by_type)}


def seek_records(assays: pd.DataFrame, internal_id, project_ids) -> list[dict]:
    """The PROJECT-SCOPED seek records for an internal assay.

    The internal title is a harmonisation key and loses what the project calls
    the thing. On the 2026-08-20 extract internal 130 `Mass Spectrometry` is
    instantiated in project 9 as `Mass Spectrometry PROTEOMICS` -- so a proposal
    to add a MALDI metabolomics image to "Mass Spectrometry" is really a
    proposal to file it under proteomics, which is obvious in the seek title and
    invisible in the internal one. An agent approved exactly that in
    calibration.
    """
    if internal_id is None:
        return []
    hit = assays[(assays.internal_assay_id == internal_id)
                 & (assays.project_id.isin(project_ids))]
    return [{"assay_id": int(r.assay_id), "title": str(r.title),
             "project_id": int(r.project_id)}
            for r in hit.itertuples(index=False)][:MAX_SIBLINGS]


def _regs(sample_id, context) -> list[str]:
    """The sample's registered assays as plain titles, deduped and sorted."""
    out = {t for _seek, _internal, t in context["registrations"].get(
        int(sample_id), []) if t}
    return sorted(out)


def _relative(sample_id, context) -> dict:
    uuid = context["uuid_of"].get(int(sample_id), str(sample_id))
    return {"uuid": uuid,
            "type": context["types"].get(uuid, R.UNTYPED),
            "registered_assays": _regs(sample_id, context)}


def _meta(sample_id, context) -> dict:
    """The sample's own non-empty metadata, capped and with blanks dropped.

    A sample carries up to ~90 fields and most are empty; the ones that matter
    for this question are the handful naming a technique, an instrument or a
    protocol. Capping keeps a dossier readable rather than exhaustive.
    """
    meta = context["metadata"].get(int(sample_id), {}) or {}
    live = {}
    for k, v in meta.items():
        if v in (None, "") or not str(v).strip():
            continue
        # A `Parent` field can list several hundred uuids -- 4 KB in one value,
        # on a packet whose whole point is being readable. Clipped with the
        # count kept, because "56 parents" is the fact a reader needs and the
        # uuids are not.
        text = str(v)
        if len(text) > MAX_META_CHARS:
            parts = text.count(";") + 1
            text = (text[:MAX_META_CHARS] + f" ... [{parts} values total]"
                    if parts > 1 else text[:MAX_META_CHARS] + " ...")
        live[k] = text
        if len(live) >= MAX_META_FIELDS:
            break
    return live


def build_dossiers(findings: pd.DataFrame, context: dict,
                   assays=None, membership=None, nodes=None) -> list[dict]:
    """One dossier per Mode 2 cohort, over the WHOLE population.

    No floor. The floor was the thing that made 157,839 rows unreviewable, and
    a dossier is cheap where a human sitting is not.
    """
    m2 = findings[findings["mode"] == S.MODE_2].copy()
    uid = R._uid_columns(m2.uuid)
    m2["lab"] = uid["lab"].values
    m2["parent_types"] = [R._parent_types(s, context) for s in m2.sample_id]
    m2["assay"] = m2.proposed_internal_assay_title.astype(str)
    m2["field"] = [f if isinstance(f, str) and f else M2.LINEAGE_FIELD
                   for f in m2.source_field]
    m2["value"] = [v if isinstance(v, str) and v else str(a)
                   for v, a in zip(m2.raw_value, m2.action)]

    children_of = M2._children_index(context)
    parents_of = context["parents_of"]
    sid_of = {uuid: sid for sid, uuid in context["uuid_of"].items()}
    sibs = sibling_assays(assays) if assays is not None else {}
    conv = (type_assay_counts(membership, assays, nodes)
            if assays is not None and membership is not None else
            {"pair": {}, "by_type": {}})
    projects_of = dict(zip(m2.sample_id, m2.project_ids.astype(str)))

    out = []
    for key, rows in m2.groupby(list(R.BLOCK_KEY), dropna=False, sort=False):
        rows = rows.sort_values("sample_id")
        first = rows.iloc[0]
        action = str(first.action)
        examples = []
        for r in rows.head(MAX_EXAMPLES).itertuples(index=False):
            sid = int(r.sample_id)
            # THE SPECIFIC RELATIVE THAT RAISED THIS ROW, named separately.
            # `parents` and `children` below are capped, and a capped list is
            # not evidence: measured on the first build, 8.1% of examples and 86
            # whole cohorts showed the assay-holding relative in NO example,
            # so a reader was asked "does this belong" with the reason it was
            # proposed invisible. That is the same defect the html sheet shipped
            # and it is fixed the same way -- carry the neighbour the finding
            # row NAMES, never the first few relatives and a hope.
            nb_uuid = (None if pd.isna(r.lineage_neighbour_uuid)
                       else str(r.lineage_neighbour_uuid))
            nb_sid = sid_of.get(nb_uuid) if nb_uuid else None
            evidence = None
            if nb_sid is not None:
                evidence = _relative(nb_sid, context)
                evidence["relationship"] = (
                    "CHILD of this sample"
                    if action == "ADD_PARENT_TO_ASSAY" else
                    "PARENT of this sample")
                evidence["holds_the_proposed_assay"] = (
                    str(key[3]) in evidence["registered_assays"])
            examples.append({
                "the_evidence": evidence,
                "sample": {
                    "uuid": str(r.uuid),
                    "type": str(r.sample_type),
                    "registered_assays": _regs(sid, context),
                    "metadata": _meta(sid, context),
                },
                "parents": [_relative(p, context)
                            for p in sorted(parents_of.get(sid, ()) or ())
                            [:MAX_RELATIVES]],
                "children": [_relative(c, context)
                             for c in sorted(children_of.get(sid, ()))
                             [:MAX_RELATIVES]],
            })
        # --- the three derived aids, per cohort -------------------------
        iaid = (int(first.proposed_internal_assay_id)
                if pd.notna(first.proposed_internal_assay_id) else None)
        sample_type = str(key[1])
        projs = set()
        for r in rows.head(MAX_EXAMPLES).itertuples(index=False):
            for tok in str(projects_of.get(r.sample_id, "")).replace(
                    ";", ",").split(","):
                if tok.strip().isdigit():
                    projs.add(int(tok))
        already = conv["pair"].get((sample_type, iaid), 0)
        usual = [{"assay": t, "internal_id": a, "samples": n}
                 for t, a, n in conv["by_type"].get(sample_type, ())
                 ][:MAX_TYPE_ASSAYS]

        n_both = first.precedent_n_both
        n_missing = (first.precedent_n_child_only
                     if action == "ADD_PARENT_TO_ASSAY"
                     else first.precedent_n_parent_only)
        out.append({
            "cohort_key": R.KEY_DELIMITER.join(str(k) for k in key),
            "lab": str(key[0]),
            "sample_type": str(key[1]),
            "parent_types": str(key[2]),
            "proposed_assay": str(key[3]),
            "proposed_internal_assay_id": (
                int(first.proposed_internal_assay_id)
                if pd.notna(first.proposed_internal_assay_id) else None),
            "action": action,
            "question": (
                f"Should this {key[1]} sample be registered in "
                f"'{key[3]}'?"),
            "direction_note": (
                "ADD_PARENT: a CHILD of this sample is registered in the "
                "assay; the proposal is to register THIS sample too."
                if action == "ADD_PARENT_TO_ASSAY" else
                "ADD_CHILD: a PARENT of this sample is registered in the "
                "assay; the proposal is to register THIS sample too."),
            "proposed_assay_detail": {
                "internal_id": iaid,
                "internal_title": str(key[3]),
                "what_the_project_actually_calls_it": seek_records(
                    assays, iaid, projs) if assays is not None else [],
                "confusable_sibling_assays": sibs.get(iaid, []),
                # 48 cohorts over 2,906 rows have NO seek record in the
                # sample's own project. A membership row is written against a
                # seek id, so those cannot be written whatever anyone rules --
                # said in words here rather than left as an empty list, which
                # reads as "not looked up".
                # THREE STATES, NEVER TWO. `project_ids` is null on some
                # findings rows -- the sample is absent from samples.parquet, as
                # the 448 `rows_without_a_samples_row` in the detect census --
                # and an empty project set finds no seek record, which the first
                # cut reported as NOT WRITABLE. That is an absence rendered as a
                # verdict, and two round-3 agents rejected real cohorts on it.
                # "I cannot tell" is its own answer here as everywhere else.
                "IS_WRITABLE_IN_THIS_PROJECT": (
                    None if assays is None or not projs
                    else bool(seek_records(assays, iaid, projs))),
                "writability_note": (
                    "UNKNOWN -- no project recorded for these samples, so "
                    "writability could not be checked. Do NOT treat this as "
                    "unwritable." if not projs else
                    "checked against the seek records in the sample's own "
                    "project(s)"),
                "note": ("the internal title is a harmonisation key. The seek "
                         "record is what the project calls it and is the thing "
                         "a membership row is written against."),
            },
            "house_convention": {
                "samples_of_this_type_already_in_this_assay": already,
                "assays_this_sample_type_usually_holds": usual,
                "note": ("what the house ALREADY does, as counts. A type that "
                         "appears in an assay 54 times and in a sibling 616 "
                         "times is not forbidden there -- it is unusual, and "
                         "the sibling is the house's answer."),
            },
            "n_rows": int(len(rows)),
            "n_samples": int(rows.sample_id.nunique()),
            "precedent": {
                "rate": (None if pd.isna(first.precedent_rate)
                         else round(float(first.precedent_rate), 4)),
                "pairs_where_both_registered": (
                    0 if pd.isna(n_both) else int(n_both)),
                "pairs_where_only_the_relative_is": (
                    0 if pd.isna(n_missing) else int(n_missing)),
                "reading": (
                    "how often the house has ALREADY made this registration "
                    "on comparable pairs. A low rate over MANY pairs is the "
                    "house repeatedly declining it; a low rate over FEW pairs "
                    "means nothing either way."),
            },
            "examples": examples,
        })
    return out


def main(artifacts="assay-hygiene", extract=None) -> int:
    a = Path(artifacts)
    e = Path(extract) if extract else a / "extract"
    findings = pd.read_csv(a / "findings.csv", low_memory=False)
    context = R.load_context(e)
    assays = pd.read_parquet(e / "assays.parquet")
    membership = pd.read_parquet(e / "membership.parquet")
    nodes = pd.read_parquet(e / "nodes.parquet")
    dossiers = build_dossiers(findings, context, assays, membership, nodes)
    (a / DOSSIER_NAME).write_text(json.dumps(dossiers, indent=1))
    rows = sum(d["n_rows"] for d in dossiers)
    print(f"wrote {a / DOSSIER_NAME}")
    print(f"  {len(dossiers):,} cohort(s), {rows:,} row(s) -- the WHOLE Mode 2 "
          "population, no floor")
    by = defaultdict(int)
    for d in dossiers:
        by[d["action"]] += 1
    for k, v in sorted(by.items()):
        print(f"  {k:22s} {v:>4} cohort(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
