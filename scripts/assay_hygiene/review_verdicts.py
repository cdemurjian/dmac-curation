# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The verdict review sheet: a human scans REASONS, not evidence.

WHY THIS IS A DIFFERENT SHEET FROM `review_mode2`. That one is built for
investigating a cohort -- three hops, full metadata, five examples -- and it is
the right surface for 111 cohorts. It is the wrong surface for 1,012, which is
where the operator stopped: "there is no possible way I can manually review 901
cohorts."

Here every cohort already carries an agent verdict and a one-line reason, so the
task changes from INVESTIGATE to CHECK. The reason leads, the evidence is folded
behind it, and the reader stops only where a sentence sounds wrong. Measured over
three blind calibration rounds against the operator's own 111 rulings, the
agents agree ~80% of the time and their false-approve rate floors at ~5%, so the
reading is worth doing and cannot be skipped.

ORDERED BY WHAT A MISTAKE COSTS, which is the whole layout argument:

  APPROVE      first, biggest first. These are the ONLY verdicts that write, so
               a wrong one here puts wrong data in the database -- up to 29,763
               rows in a single cohort. This is where the reading time goes.
  WRONG_ASSAY  second. Needs a target decision, and the agent names a candidate.
  UNSURE       third. The agent punted; the cohort needs a human.
  REJECT       last and collapsed. Nothing is written, so a wrong REJECT costs
               coverage and not correctness. Scannable, not demanding.

THE COUNTS ARE ROWS AND NOT COHORTS EVERYWHERE, because a cohort is a unit of
attention and a row is a unit of consequence, and they differ by three orders of
magnitude here.
"""
from __future__ import annotations

import glob
import html
import sys
from pathlib import Path

import pandas as pd

from . import review as R

SHEET_NAME = "mode2-verdicts-review.html"
CSV_NAME = "mode2-verdicts-review.csv"
LS = 'var LS = "mode2-verdicts:";'

ORDER = ["APPROVE", "WRONG_ASSAY", "UNSURE", "REJECT"]
BLURB = {
    "APPROVE": ("These WRITE. A wrong one here puts a wrong registration on "
                "every sample in the cohort. Read every reason."),
    "WRONG_ASSAY": ("The agent says a different assay is right and names it. "
                    "Needs your decision on the target."),
    "UNSURE": "The agent could not tell. These need you.",
    "REJECT": ("Nothing is written for these. A wrong reject costs coverage, "
               "not correctness -- scan, do not study."),
}


VERDICT_GLOB = "full-*-verdicts.tsv"


def load_verdicts(batch_dir, pattern: str = VERDICT_GLOB) -> pd.DataFrame:
    """The run's verdict files, concatenated, deduped, checked.

    THE PATTERN IS NARROW ON PURPOSE. A bare `*-verdicts.tsv` also matches the
    calibration outputs, which judge 111 of these same cohorts three times over
    -- so the first run of this loader raised on 111 duplicates. That was the
    guard working, and the fix is to name the run rather than to widen the
    dedup: calibration verdicts are a DIFFERENT experiment and must never be
    silently averaged into the review sheet.

    RAISES on a duplicate cohort_key rather than keeping one. Two verdicts for
    one cohort means a batch was judged twice, and silently keeping either makes
    the sheet a coin toss on that row.
    """
    files = sorted(glob.glob(str(Path(batch_dir) / pattern)))
    if not files:
        raise FileNotFoundError(f"no {pattern} under {batch_dir}")
    frame = pd.concat([pd.read_csv(f, sep="\t", dtype=str) for f in files],
                      ignore_index=True).fillna("")
    missing = {"cohort_key", "verdict", "confidence", "reason"} - set(frame.columns)
    if missing:
        raise ValueError(f"verdict files are missing column(s): {sorted(missing)}")
    dupes = frame[frame.duplicated("cohort_key", keep=False)]
    if len(dupes):
        raise ValueError(
            f"{dupes.cohort_key.nunique()} cohort(s) carry more than one "
            f"verdict, e.g. {dupes.cohort_key.iloc[0]}. A batch was judged "
            "twice; resolve before reviewing.")
    bad = sorted(set(frame.verdict) - set(ORDER))
    if bad:
        raise ValueError(f"unknown verdict(s) {bad}; expected {ORDER}")
    return frame


def join_dossiers(verdicts: pd.DataFrame, dossiers: list[dict]) -> pd.DataFrame:
    """Verdicts with the size and evidence each one is about.

    A verdict with no dossier is an ORPHAN and raises: it means the agent
    invented or mangled a cohort_key, and a sheet that quietly drops it hides a
    cohort nobody will ever rule on.
    """
    by = {d["cohort_key"]: d for d in dossiers}
    orphan = [k for k in verdicts.cohort_key if k not in by]
    if orphan:
        raise ValueError(
            f"{len(orphan)} verdict(s) name no cohort: {orphan[:3]}. The key "
            "was not copied verbatim; the cohort would be lost.")
    rows = []
    for r in verdicts.itertuples(index=False):
        d = by[r.cohort_key]
        det = d["proposed_assay_detail"]
        ev = (d["examples"][0].get("the_evidence") if d["examples"] else None) or {}
        rows.append({
            "cohort_key": r.cohort_key, "verdict": r.verdict,
            "confidence": r.confidence, "reason": r.reason,
            "lab": d["lab"], "sample_type": d["sample_type"],
            "parent_types": d["parent_types"], "assay": d["proposed_assay"],
            "action": d["action"], "n_rows": d["n_rows"],
            "n_samples": d["n_samples"],
            "precedent": d["precedent"]["rate"],
            # BOTH GRAINS, because both are on the dossier and the edge count
            # alone is what a reader mistakes for refusals. See
            # `dossier.build_dossiers`.
            "precedent_both_edges": d["precedent"][
                "edges_where_both_registered"],
            "precedent_missing_edges": d["precedent"][
                "edges_where_only_the_relative_is"],
            "precedent_missing_samples": d["precedent"][
                "samples_where_only_the_relative_is"],
            "writable": det.get("IS_WRITABLE_IN_THIS_PROJECT"),
            "project_calls_it": "; ".join(
                x["title"] for x in det["what_the_project_actually_calls_it"]),
            "siblings": "; ".join(
                x["title"] for x in det["confusable_sibling_assays"]),
            "evidence_uuid": ev.get("uuid", ""),
            "evidence_type": ev.get("type", ""),
            "evidence_holds": ev.get("holds_the_proposed_assay"),
            "sample_holds": "; ".join(
                d["examples"][0]["sample"]["registered_assays"]) if d["examples"] else "",
            "already_this_type": d["house_convention"][
                "samples_of_this_type_already_in_this_assay"],
            "type_usually": "; ".join(
                f'{u["assay"]} {u["samples"]}' for u in
                d["house_convention"]["assays_this_sample_type_usually_holds"][:4]),
        })
    return pd.DataFrame(rows)


def _e(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _row_html(r) -> str:
    conf = f'<span class="c{_e(r.confidence)}">{_e(r.confidence)}</span>'
    warn = ""
    if r.writable is False:
        warn = ('<span class="flag">NOT WRITABLE in this project</span>')
    elif r.writable is None:
        warn = '<span class="flag unk">writability unknown</span>'
    prec = ("--" if r.precedent is None or pd.isna(r.precedent)
            else f"{float(r.precedent):.3f}")
    return (
        f'<details class="v {_e(r.verdict)}"><summary>'
        f'<span class="n">{int(r.n_rows):,}</span> '
        f'<b>{_e(r.lab)} &middot; {_e(r.sample_type)}</b> '
        f'<span class="arrow">&rarr;</span> {_e(r.assay)} '
        f'<span class="ids">{_e(r.action)}</span> {conf} {warn}'
        f'<div class="why">{_e(r.reason)}</div></summary>'
        f'<div class="ev">'
        f'<div><b>evidence</b> {_e(r.evidence_type)} <code>{_e(r.evidence_uuid)}</code>'
        f'{" holds it" if r.evidence_holds else " does NOT hold it"}</div>'
        f'<div><b>sample already holds</b> {_e(r.sample_holds) or "(nothing)"}</div>'
        f'<div><b>project calls the assay</b> {_e(r.project_calls_it) or "(no record)"}</div>'
        f'<div><b>confusable siblings</b> {_e(r.siblings) or "(none)"}</div>'
        f'<div><b>house</b> {int(r.already_this_type):,} of this type already in '
        f'it &middot; usually: {_e(r.type_usually)}</div>'
        f'<div><b>precedent</b> {prec} '
        f'({int(r.precedent_both_edges):,} edges both / '
        f'{int(r.precedent_missing_edges):,} edges over '
        f'{int(r.precedent_missing_samples):,} samples with only the '
        f'relative &mdash; EDGES, not refusals)</div>'
        f'<div class="key"><code>{_e(r.cohort_key)}</code></div>'
        f'</div>{_notes(r)}</details>')


def _notes(r) -> str:
    key = _e(r.cohort_key)
    opts = "".join(
        f'<option value="{_e(v)}"{" selected" if v == r.verdict else ""}>{_e(l)}</option>'
        for v, l in R.RULING_OPTIONS if v)
    return (f'<div class="notes"><label>your ruling '
            f'<select class="dec" data-k="{key}">'
            f'<option value="">-- agree with the agent --</option>{opts}</select>'
            f'</label><textarea class="note" data-k="{key}" rows="1" '
            f'placeholder="only if you disagree"></textarea></div>')


CSS = """
.v{border:1px solid var(--line);border-radius:6px;margin:.35rem 0;
 padding:.4rem .6rem;background:var(--card)}
.v>summary{cursor:pointer;list-style:none}
.v>summary::-webkit-details-marker{display:none}
.n{display:inline-block;min-width:4.5rem;font-variant-numeric:tabular-nums;
 font-weight:700;text-align:right;margin-right:.5rem}
.why{margin:.25rem 0 0 5rem;font-size:.9rem;color:var(--fg)}
.ev{margin:.5rem 0 .4rem 5rem;font-size:.82rem;color:var(--mut);line-height:1.75}
.ev code{font-size:.78rem}
.key{margin-top:.3rem;opacity:.65}
.cHIGH{font-size:.66rem;border:1px solid var(--ok);color:var(--ok);
 border-radius:3px;padding:0 .3rem}
.cMEDIUM{font-size:.66rem;border:1px solid var(--mut);color:var(--mut);
 border-radius:3px;padding:0 .3rem}
.cLOW{font-size:.66rem;border:1px solid var(--warn);color:var(--warn);
 border-radius:3px;padding:0 .3rem}
.flag{font-size:.66rem;color:var(--warn);border:1px solid var(--warn);
 border-radius:3px;padding:0 .3rem;margin-left:.3rem}
.flag.unk{color:var(--mut);border-color:var(--mut)}
.notes{margin:.4rem 0 .1rem 5rem;display:flex;gap:.5rem;align-items:center}
.notes select,.notes textarea{font:inherit;font-size:.82rem}
.notes textarea{flex:1;resize:vertical}
h2.g{margin:1.6rem 0 .2rem;padding-bottom:.2rem;border-bottom:2px solid var(--line)}
"""


def render(frame: pd.DataFrame) -> str:
    assert LS.replace("mode2-verdicts", "mode1-review") in R.SCRIPT or True
    script = R.SCRIPT.replace('var LS = "mode1-review:";', LS)
    if LS not in script:
        raise ValueError("could not rebind the storage prefix; review.SCRIPT "
                         "no longer declares it verbatim")
    parts = []
    for v in ORDER:
        sub = frame[frame.verdict == v].sort_values("n_rows", ascending=False)
        if not len(sub):
            continue
        parts.append(
            f'<h2 class="g">{_e(v)} <span class="ids">{len(sub):,} cohort(s) '
            f'&middot; {int(sub.n_rows.sum()):,} row(s)</span></h2>'
            f'<p class="bandblurb">{_e(BLURB[v])}</p>')
        parts += [_row_html(r) for r in sub.itertuples(index=False)]
    total = int(frame.n_rows.sum())
    appr = frame[frame.verdict == "APPROVE"]
    return (f"<title>Mode 2 verdicts, {len(frame)} cohorts</title>"
            f"<style>{R.CSS}{CSS}</style>"
            f'<h1>Mode 2 &mdash; {len(frame):,} agent verdict(s), '
            f"{total:,} row(s)</h1>"
            f'<p class="lede">Every cohort has been read by an agent and '
            f"carries a one-line reason. <b>You are checking reasons, not "
            f"investigating cohorts.</b> Only the "
            f'{len(appr):,} APPROVE cohorts ({int(appr.n_rows.sum()):,} rows) '
            f"would be written; the rest write nothing. Open a row for the "
            f"evidence behind it. Leave a ruling only where you disagree.</p>"
            f"{_CALLOUT}{''.join(parts)}{R.BAR}{script}\n")


_CALLOUT = (
    '<div class="callout">'
    "<b>Nothing here is decided and nothing here writes.</b> These are agent "
    "verdicts awaiting your check; no stage reads them back and none of it "
    "reaches MySQL, Neo4j or the API."
    "<br><br>"
    "<b>Measured against your own 111 rulings, over three blind rounds:</b> the "
    "agents agreed ~80% of the time, punted ~10%, and their FALSE APPROVE rate "
    "floored at ~5% and would not go lower &mdash; two independent rounds made "
    "the SAME mistakes, so redundancy does not fix it. Roughly one APPROVE in "
    "twenty is expected to be wrong. That is why you read them."
    "<br><br>"
    "<b>They are strong on metadata and weak on house convention.</b> They "
    "found the assay-143 name collision, identified MALDI-MSI unprompted, and "
    "spotted Maxpar/cadmium as CyTOF. They also approved registrations that "
    "are biologically reasonable and contrary to how this lab records things."
    "</div>")


def main(artifacts="assay-hygiene", batches=None) -> int:
    a = Path(artifacts)
    b = Path(batches) if batches else a / "batches"
    import json
    dossiers = json.loads((a / "mode2-dossiers.json").read_text())
    frame = join_dossiers(load_verdicts(b), dossiers)
    frame.to_csv(a / CSV_NAME, index=False)
    (a / SHEET_NAME).write_text(render(frame))
    print(f"wrote {a / CSV_NAME} and {a / SHEET_NAME}")
    print(f"  {len(frame):,} cohort(s), {int(frame.n_rows.sum()):,} row(s)")
    for v in ORDER:
        s = frame[frame.verdict == v]
        if len(s):
            print(f"  {v:12s} {len(s):>5,} cohort(s)  {int(s.n_rows.sum()):>8,} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
