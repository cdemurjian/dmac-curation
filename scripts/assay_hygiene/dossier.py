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


def build_dossiers(findings: pd.DataFrame, context: dict) -> list[dict]:
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

    out = []
    for key, rows in m2.groupby(list(R.BLOCK_KEY), dropna=False, sort=False):
        rows = rows.sort_values("sample_id")
        first = rows.iloc[0]
        action = str(first.action)
        examples = []
        for r in rows.head(MAX_EXAMPLES).itertuples(index=False):
            sid = int(r.sample_id)
            examples.append({
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
    dossiers = build_dossiers(findings, context)
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
