# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Read RUN1's three ruling shapes and emit the durable store.

THREE SHAPES, ONE TARGET. `pair-rulings.tsv` already carries sample_type and
internal_assay_id and needs only a verdict rename. `mode2-rulings-2026-08-20.tsv`
carries the assay as a TITLE and the action in a column whose meaning depends on
another column. `mode1-rulings-COMPLETE.tsv` carries a 6-field composite key.

MEASURED ON RUN1 2026-08-27: all 111 Mode 2 titles resolve to a unique internal
id -- 0 ambiguous, 0 unresolvable. 100 rows are lineage (70 ADD_PARENT, 30
ADD_CHILD) and 11 are term rows. 45 of 175 pair rows are ruled; 130 are UNRULED
and are NOT migrated, because the absence of a ruling is not a ruling.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .rulings import Ruling, normalise_id

LINEAGE_FIELD = "(lineage)"
TERM_ACTION = "ADD_TO_ASSAY"
PAIR_VERDICT = {"OVERRIDE": "APPROVE", "CONFIRM_BLOCK": "REJECT"}


class AmbiguousTitle(ValueError):
    """Two internal assays share a display string. Never merge them silently."""


def title_index(assays: pd.DataFrame) -> dict[str, str]:
    """-> internal assay title -> internal id, refusing any ambiguity."""
    seen: dict[str, set[str]] = {}
    for title, iid in zip(assays.internal_assay_title, assays.internal_assay_id):
        if pd.isna(title) or pd.isna(iid):
            continue
        seen.setdefault(str(title).strip(), set()).add(normalise_id(iid))
    bad = {t: sorted(v) for t, v in seen.items() if len(v) > 1}
    if bad:
        raise AmbiguousTitle(
            f"these titles map to more than one internal assay and must not "
            f"be merged: {bad}")
    return {t: v.pop() for t, v in seen.items()}


def migrate(run_dir: Path, assays: pd.DataFrame) -> tuple[list[Ruling], list[dict]]:
    """-> (rulings, provenance records) from every ruling file present."""
    base = Path(run_dir) / "00-rulings"
    index = title_index(assays)
    out: list[Ruling] = []
    prov: list[dict] = []

    m2 = base / "mode2-rulings-2026-08-20.tsv"
    if m2.exists():
        frame = pd.read_csv(m2, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            iid = index.get(str(row.assay).strip())
            if iid is None:
                continue
            action = (str(row.value).strip()
                      if str(row.field).strip() == LINEAGE_FIELD else TERM_ACTION)
            key = (str(row.sample_type).strip(), iid, action)
            out.append(Ruling(key, str(row.ruling).strip(), "2026-08-20", "operator"))
            prov.append({"key": key, "source": "mode2",
                         "cohort": "|".join([row.lab, row.sample_type,
                                             row.parent_types, row.assay,
                                             row.field, row.value])})

    pr = base / "pair-rulings.tsv"
    if pr.exists():
        frame = pd.read_csv(pr, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            if str(row.status).strip() != "ruled":
                continue
            verdict = PAIR_VERDICT.get(str(row.ruling).strip())
            if verdict is None:
                continue
            key = (str(row.sample_type).strip(),
                   normalise_id(row.internal_assay_id), TERM_ACTION)
            out.append(Ruling(key, verdict, "2026-08-25", "operator"))
            prov.append({"key": key, "source": "pair",
                         "cohort": f"{row.sample_type}|{row.proposed_assay}"})

    m1 = base / "mode1-rulings-COMPLETE.tsv"
    if m1.exists():
        frame = pd.read_csv(m1, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            parts = str(row.key).split("|")
            if len(parts) != 6:
                continue
            _lab, sample_type, _parents, assay, _field, _value = parts
            iid = index.get(assay.strip())
            if iid is None:
                continue
            key = (sample_type.strip(), iid, TERM_ACTION)
            out.append(Ruling(key, str(row.ruling).strip(), "2026-08-25", "operator"))
            prov.append({"key": key, "source": "mode1", "cohort": str(row.key)})

    return out, prov
