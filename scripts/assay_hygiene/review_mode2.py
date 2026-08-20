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
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import review as R

FLOOR = 0.50

CSV_NAME = "mode2-cohorts-to-review.csv"
REVIEW_NAME = "mode2-review.html"

# The storage prefix MUST differ from Mode 1's or the two sheets share a
# keyspace and a Mode 2 ruling silently overwrites a Mode 1 one on a cohort
# whose six-field key happens to match. Substituted rather than re-declared, and
# asserted below, so a rename in `review.py` fails loudly here instead of
# quietly reuniting the two stores.
_LS_MODE1 = 'var LS = "mode1-review:";'
_LS_MODE2 = 'var LS = "mode2-review:";'

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


def _band(rate: float) -> str:
    if rate >= 0.95:
        return BAND_A
    if rate >= 0.90:
        return BAND_B
    if rate >= 0.75:
        return BAND_C
    return BAND_D


def build_blocks(findings: pd.DataFrame, context: dict,
                 floor: float = FLOOR) -> list[dict]:
    """Mode 2 rows at or above `floor`, grouped into review cohorts.

    The key is Mode 1's six fields, with the last two carrying what a lineage
    row has instead of a term: `field` is `(lineage)` and `value` is the ACTION.
    The action belongs in the key because ADD_PARENT and ADD_CHILD are different
    writes against the same pair, and a cohort pooling them would take one
    ruling for two decisions.
    """
    m2 = findings[(findings["mode"] == S.MODE_2)
                  & (findings.precedent_rate >= floor)].copy()
    if m2.empty:
        return []

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

    blocks = []
    for key, rows in m2.groupby(list(R.BLOCK_KEY), dropna=False, sort=False):
        rows = rows.sort_values("sample_id")
        examples = rows.head(R.MAX_EXAMPLES)
        children = [R._child(r, context)
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
                                     if c["parent_has_proposed"]),
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


def to_csv(blocks: list[dict]) -> pd.DataFrame:
    """The cohort csv -- the operator reads this BEFORE the sheet.

    One row per cohort, carrying the key, the size, the precedent range that
    banded it, and empty `ruling` and `note` columns to fill in. It holds no
    per-sample examples on purpose: this is the triage pass, and the examples
    are what the html is for.
    """
    return pd.DataFrame([{
        "band": b["band"],
        "lab": b["lab"], "sample_type": b["sample_type"],
        "parent_types": b["parent_types"], "assay": b["assay"],
        "field": b["field"], "value": b["value"],
        "n_rows": b["n_rows"], "n_samples": b["n_samples"],
        "precedent_min": round(b["precedent_min"], 4),
        "precedent_max": round(b["precedent_max"], 4),
        "n_contested": b["n_contested"],
        "parents_already_holding_it": f'{b["n_corroborated_shown"]}/{b["shown"]}',
        "tiers": b["tiers"], "gates": b["gates"], "dates": b["dates"],
        "example_uuids": ";".join(c["uuid"] for c in b["children"]),
        "ruling": "", "note": "",
    } for b in blocks])


def render(blocks: list[dict], floor: float = FLOOR,
           excluded: int | None = None, no_rate: int | None = None) -> str:
    """The whole page: one file, no network, both themes. See `review.render`."""
    assert _LS_MODE1 in R.SCRIPT, (
        "review.SCRIPT no longer declares the Mode 1 storage prefix verbatim, "
        "so this module cannot rebind it and the two sheets would SHARE a "
        "keyspace -- a Mode 2 ruling would overwrite a Mode 1 one. Re-pin it.")
    script = R.SCRIPT.replace(_LS_MODE1, _LS_MODE2)

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
            parts += R._cohort_html(block)

    excl = ("" if excluded is None else
            f" {excluded:,} row(s) below the floor are NOT on this page.")
    if no_rate:
        excl += (f" A further {no_rate:,} carry NO propagation rate at all -- "
                 "mostly the co-registration lane, whose evidence is a "
                 "different measure and which this page does not rank.")
    return (f"<title>Mode 2 review, {len(blocks)} cohorts</title>"
            f"<style>{R.CSS}</style>"
            f'<h1>Mode 2 &mdash; {len(blocks):,} cohort(s), '
            f"{total:,} proposal(s)</h1>"
            f'<p class="lede">Samples that ARE registered somewhere, whose '
            "lineage neighbour carries an assay they do not hold. Banded by "
            "<b>propagation rate</b>: when the child is in this assay, how "
            f"often the parent is too. Floor {floor:g}.{R._e(excl)} Up to "
            f"{R.MAX_EXAMPLES} examples per cohort.</p>"
            f"{_CALLOUT}{''.join(parts)}{R.BAR}{script}\n")


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


def main(artifacts="assay-hygiene", extract=None, floor: float = FLOOR) -> int:
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
    blocks = build_blocks(findings, context, floor=floor)
    kept = sum(b["n_rows"] for b in blocks)
    if kept + below + no_rate != all_m2:
        raise ValueError(
            f"{kept:,} kept + {below:,} below the floor + {no_rate:,} with no "
            f"rate != {all_m2:,} Mode 2 rows. Every row must be accounted for "
            "in exactly one bucket, or this run is hiding proposals behind a "
            "number that does not describe them.")

    to_csv(blocks).to_csv(a / CSV_NAME, index=False)
    (a / REVIEW_NAME).write_text(
        render(blocks, floor=floor, excluded=below, no_rate=no_rate))
    print(f"wrote {a / CSV_NAME} and {a / REVIEW_NAME}")
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
