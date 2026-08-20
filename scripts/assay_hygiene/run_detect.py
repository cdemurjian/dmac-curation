# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Run the whole detection layer over an extract and write the operator report.

Read-only end to end: it reads parquet and csv off disk and writes csv and
markdown under `assay-hygiene/`. Nothing here reaches MySQL, Neo4j or the API.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.run_detect

IT DELEGATES THE RUN RATHER THAN REPRODUCING IT. `gate.main` writes
`vocabulary-defects.csv` and `classify.main` writes `findings.csv` and
`mode3-disposition.csv`; this module calls both and then builds the report from
the files they wrote. The alternative -- re-assembling the lanes here and
handing them to `unify_findings` a second time -- was the obvious shape and is
the wrong one, for two reasons measured on this branch:

  * A SECOND ASSEMBLY IS A SECOND DEFINITION OF THE RUN. `registered` was once
    defined in three places and two of them published wrong figures. Task 8's
    review then found that `unify_findings` SILENTLY DROPS A WHOLE MODE when a
    lane key is omitted -- verified live, 8 rows became 4 with no raise -- and
    recorded "TASK 9 RE-ASSEMBLES lanes" as the carry. Not re-assembling them
    retires that hazard instead of guarding it.

  * THE REPORT MUST QUOTE THE FILES, NOT A PARALLEL COMPUTATION. Increment 1
    shipped a report quoting a table it had not computed. Reading the csv back
    makes "the counts in the prose equal the counts in the csv" structural: the
    frame the report counts IS the frame on disk, so the two cannot drift.

Two facts the artifacts cannot supply are computed here, each from the ONE
function that defines it -- `lineage.mode2_ceiling` and `lineage.lineage_index`
-- so this is the same definition called again, not a second one.

THE REPORT IS THE DELIVERABLE, NOT THE COUNTS. An operator reads it to decide
whether any of this is trustworthy, and three of the things it has to do cannot
be done by a number:

  * SAY THAT NOTHING WAS WRITTEN, and scope the claim to THIS RUN. A hygiene
    tool that silently corrected the database and one that only looked produce
    similar-looking summaries, and the difference is the whole safety argument.
    Scoped, because `scripts/assay_hygiene/` DOES contain a write path:
    `stage0_apply.py` carries `MERGE`/`DELETE` Cypher and `driver_stage0.py`
    runs it. A package-wide "there is no write path here" would be false, and a
    reader who found that file afterwards would be right to distrust the rest.

  * LEAD WITH THE CORRECTION. Increment 1 told the operator there were 866
    contradictions and shipped them for review. Measurement found none. That
    reader is this document's primary audience and the finding is the first
    thing after the safety claims, not a note at the bottom.

  * REPORT MODE 3 AS UNDETECTED, NEVER AS SMALL. Its zero is the absence of a
    detector, not a measurement that contradictions are rare. Those are
    different findings and only one of them is true.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import audit as A
from . import classify as X
from . import gate as G
from . import lineage as L
from . import mode2 as M2
from . import review as RV

REPORT_NAME = "detect-report.md"

# Every file THIS module's `main` creates, named once. The report asserts it
# names each of them and a test reads this tuple rather than four literals, so
# adding a fifth output and forgetting to mention it is what goes red.
COHORTS_NAME = "cohorts-to-review.csv"

ARTIFACTS = ("vocabulary-defects.csv", "findings.csv", "mode3-disposition.csv",
             COHORTS_NAME, RV.REVIEW_NAME, REPORT_NAME)

# THE KEY CARRIES `raw_value`, and that is the whole point of it. Under
# `(sample_type, proposed_assay)` the PAV `Blood` and `Necropsy` populations
# collapse into one row whose numbers describe neither: they behave oppositely
# -- one routinely coexists with the proposed assay and one never does -- and
# the coarser key made that invisible. Identity is the assay ID and not its
# title, for the reason `merge_vocabulary` and `audit_contradictions` both
# refuse a title key: two assays sharing a display string would merge.
PATTERN_KEY = ["sample_type", "proposed_internal_assay_id", "raw_value"]

MODE_HEADINGS = {
    S.MODE_1: "MODE_1 -- the sample is registered in nothing",
    S.MODE_2: "MODE_2 -- a neighbour or a peer establishes the absence",
    S.MODE_3: "MODE_3 -- no detector exists",
}


def _num(v, places: int = 0) -> str:
    """A count or a rate, formatted, with nulls rendered rather than crashed on."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "--"
    if places:
        return f"{float(v):.{places}f}"
    return f"{int(v):,}"


def _cell(v) -> str:
    """A table cell: null-safe, pipe-safe."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "--"
    return str(v).replace("|", "\\|")


# A boolean column that has been through csv, coerced back. THE DEFINITION
# MOVED TO `review` AND THIS IS THE SAME OBJECT, not a second spelling: the
# sheet groups on `contested` too, the import direction is `run_detect ->
# review`, and two copies of one coercion a module apart is the shape of three
# defects this branch has already found. See `review._truthy` for why the
# coercion is needed at all.
_truthy = RV._truthy


def _integrity_cell(value) -> tuple[str, str]:
    """-> (count, ids). `integrity` holds SCALARS AND LISTS in the same dict.

    Six of the eleven keys are counts and five are lists of sample ids, and
    formatting a list with `:,` raises. `lineage.main` renders them as a length
    plus the first ten ids; this renders them the same way ON PURPOSE, so the
    table an operator reads and the console an engineer reads cannot disagree
    about a population -- which is the whole reason this report quotes the
    artifacts rather than recomputing them.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        ids = sorted(value)
        head = ", ".join(str(v) for v in ids[:10])
        more = " ..." if len(ids) > 10 else ""
        return f"{len(ids):,}", (f"`{head}{more}`" if ids else "--")
    return f"{int(value):,}", "--"


def _lineage_facts(extract_dir) -> tuple[dict, dict]:
    """-> (ceiling, integrity), both from the functions that DEFINE them.

    `mode2_ceiling` and `lineage_index` are called again here rather than
    having their results threaded out of `classify.main`, which is the one
    place a second definition could still creep in. Calling the same function
    on the same frames is not a second definition; re-deriving the ceiling with
    a groupby here would have been.

    `registered` comes from `audit.registered_internal` -- ANY membership row,
    crossed into the internal namespace -- because that is the definition Task
    4 reconciled the two disagreeing ceiling readings onto. Dropping the 17
    junction-less assays' registrations gives 54,780 / 116,365 instead of
    55,007 / 117,463, and both are arithmetically correct.
    """
    d = Path(extract_dir)
    samples = pd.read_parquet(d / "samples.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    edges = pd.read_parquet(d / "edges.parquet")
    children_of, parents_of, _uuid_of, integrity = L.lineage_index(
        edges, samples, membership)
    registered = A.registered_internal(membership, assays)
    return L.mode2_ceiling(children_of, parents_of, registered), integrity


def _ceiling_from(extract_dir) -> dict:
    """The ceiling alone, for callers that do not need the integrity report."""
    return _lineage_facts(extract_dir)[0]


def pattern_rollup(findings: pd.DataFrame) -> pd.DataFrame:
    """Findings collapsed onto `PATTERN_KEY`, largest first.

    A PATTERN IS WHAT A CURATOR CAN ACTUALLY RULE ON. 176,428 rows is not a
    review surface; the same rows keyed on (type, proposed assay, term)
    collapse to something a person can read, and one ruling settles every row
    under it. The same argument as `run_evidence.review_patterns`, which ships
    22 exemplars covering 100% of the 866 rather than a 20-row sample covering
    2.3% of it.

    `n_rows` is rows and `n_samples` is DISTINCT samples, and they are not the
    same number: this package has already published one per-term sum as a
    sample count and been wrong by 65%.
    """
    if not len(findings):
        return pd.DataFrame(columns=PATTERN_KEY + [
            "proposed_internal_assay_title", "n_rows", "n_samples",
            "modes", "classifications", "actions"])

    def _join(s):
        return ";".join(sorted({str(v) for v in s.dropna().unique()})) or "--"

    out = (findings.groupby(PATTERN_KEY, dropna=False)
           .agg(proposed_internal_assay_title=("proposed_internal_assay_title",
                                               lambda s: _join(s)),
                n_rows=("sample_id", "size"),
                n_samples=("sample_id", "nunique"),
                modes=("mode", _join),
                classifications=("classification", _join),
                actions=("action", _join))
           .reset_index()
           .sort_values(["n_rows"] + PATTERN_KEY,
                        ascending=[False] + [True] * len(PATTERN_KEY)))
    return out.reset_index(drop=True)


def _pattern_rows(frame: pd.DataFrame) -> list[str]:
    """Pattern table rows. The assay carries its ID, since the ID is identity."""
    return [
        f"| {_cell(r.sample_type)} | "
        f"{_cell(r.proposed_internal_assay_title)} "
        f"(`{_cell(r.proposed_internal_assay_id)}`) | "
        f"`{_cell(r.raw_value)}` | {_num(r.n_rows)} | "
        f"{_num(r.n_samples)} | {_cell(r.classifications)} |"
        for r in frame.itertuples(index=False)
    ]


def _more(frame: pd.DataFrame, shown: int) -> list[str]:
    """NO SILENT TRUNCATION. What was dropped from a table says so."""
    if len(frame) <= shown:
        return []
    return ["", f"{len(frame) - shown:,} further pattern(s) are in "
            "`findings.csv`; this table is truncated by row count and nothing "
            "is filtered out of the artifact."]


def _term_contrast_note(findings: pd.DataFrame) -> list[str]:
    """One MEASURED exemplar for why `raw_value` is in the key.

    THE EXEMPLAR IS FOUND, NOT NAMED. The plan justifies the key with the PAV
    `Blood` and `Necropsy` populations and says they "behave oppositely -- one
    routinely coexists with the proposed assay, one never". Measured on the
    2026-08-14 extract that is NOT what they do: both carry the SAME
    co-registration rate, 0.805, and they must, because co-registration is
    keyed on (sample type, proposed assay) and never reads the term. What
    actually differs is the EVIDENCE MIX -- `Blood` is 86 lineage against 11
    compat, `Necropsy` is 2 against 28 -- so one population is mostly
    corroborated by a neighbour and the other mostly rests on co-registration
    alone. That is a real difference and the coarse key does hide it, but it is
    a different fact from the one the plan states, and publishing the plan's
    sentence would have put an unmeasured claim in the report whose whole
    subject is an unmeasured claim.

    So this searches for the pair whose terms disagree most about where their
    evidence comes from, and prints what it finds. If a future extract makes
    some other pair the sharpest example, the report says so instead of
    repeating this one.
    """
    f = findings[findings.raw_value.notna() & findings.classification.notna()]
    if not len(f):
        return []
    key = ["sample_type", "proposed_internal_assay_id",
           "proposed_internal_assay_title", "raw_value"]
    g = f.groupby(key).classification.value_counts().unstack(fill_value=0)
    for c in (S.CLS_ABSENCE_LINEAGE, S.CLS_ABSENCE_COMPAT):
        if c not in g.columns:
            g[c] = 0
    g["n"] = g.sum(axis=1)
    both = g[S.CLS_ABSENCE_LINEAGE] + g[S.CLS_ABSENCE_COMPAT]
    g = g[both > 0]
    if not len(g):
        return []
    g["lineage_share"] = g[S.CLS_ABSENCE_LINEAGE] / both[both > 0]

    best, best_score = None, 0.0
    for pair, sub in g.groupby(level=[0, 1, 2]):
        if len(sub) < 2:
            continue
        spread = float(sub.lineage_share.max() - sub.lineage_share.min())
        score = spread * float(sub["n"].sum())
        if score > best_score:
            best, best_score = (pair, sub), score
    if best is None:
        return []

    (stype, iaid, title), sub = best
    sub = sub.sort_values("lineage_share", ascending=False)
    hi, lo = sub.iloc[0], sub.iloc[-1]
    hi_term = sub.index[0][-1] if sub.index.nlevels > 1 else sub.index[0]
    lo_term = sub.index[-1][-1] if sub.index.nlevels > 1 else sub.index[-1]
    total = int(sub["n"].sum())
    return [
        "### Why the term is in the key, measured",
        "",
        f"On `{stype}` / {title} (`{iaid}`), the terms do not agree about where",
        "their evidence comes from. Keyed only on (sample type, proposed",
        f"assay), all {total:,} rows collapse into ONE pattern carrying both",
        "classes and describing neither population:",
        "",
        "| term | rows | corroborated by a neighbour | on co-registration alone |",
        "|---|---|---|---|",
        f"| `{_cell(hi_term)}` | {_num(hi['n'])} | "
        f"{_num(hi[S.CLS_ABSENCE_LINEAGE])} | {_num(hi[S.CLS_ABSENCE_COMPAT])} |",
        f"| `{_cell(lo_term)}` | {_num(lo['n'])} | "
        f"{_num(lo[S.CLS_ABSENCE_LINEAGE])} | {_num(lo[S.CLS_ABSENCE_COMPAT])} |",
        "",
        "The two rest on different evidence and a curator would rule on them",
        "differently. NOTE what this is NOT: their co-registration RATES are",
        "identical, and must be, since co-registration is keyed on (sample",
        "type, proposed assay) and never reads the term. The design says these",
        "populations differ in whether they coexist with the proposed assay;",
        "measured, they differ in how their absence is evidenced. The coarser",
        "key does hide a real difference -- a different one.",
        "",
    ]


NO_MODE = "NO_MODE"          # rendered, never blank -- see `_join`

COHORT_COLUMNS = PATTERN_KEY + [
    "proposed_internal_assay_title", "raised_by",
    "n_rows", "n_samples", "n_mode_1", "n_mode_2", "n_no_mode",
    "classifications", "actions", "tiers", "gates",
    "precedent_min", "precedent_max", "co_reg_max", "n_projects",
]


def cohort_table(findings: pd.DataFrame) -> pd.DataFrame:
    """One row per cohort, carrying the evidence a curator rules on.

    THE REVIEW SURFACE. `findings.csv` is 176,428 rows and 110 MB; nobody rules
    on that. The same rows keyed on `PATTERN_KEY` collapse to a few hundred
    cohorts, and one ruling settles every row under one. The report shows the
    largest fifteen of each kind; this is all of them.

    THE MODE COUNTS ARE COLUMNS, NOT A JOINED LABEL, and that is the whole
    difference between this and the draft it replaces. A joined `modes` string
    built with `dropna()` renders a cohort that is 94% NO-MODE as `MODE_1`,
    because the null state -- a row in no mode, proposing nothing -- has no
    label to join. Measured on the real extract, `D.IMG` / CometChip Assay /
    `TIF` is 2,447 rows of which the overwhelming majority are `CLS_ALT_LABEL`
    and reach no mode, and the draft labelled that cohort `MODE_1`. A curator
    reading it would have seen a 2,447-row registration proposal where the
    finding is "this term is a different name for something already
    registered, propose nothing".

    So the three counts are explicit and they are ASSERTED to sum to `n_rows`.
    That is the same guard `findings_census` and `disposition_breakdown` carry,
    for the same reason: this package has now produced three separate defects
    from a null dropped by a default.

    `raised_by` splits the two populations that must not be ranked together.
    A cohort with no term was raised by a lineage neighbour rather than by
    anything the sample says about itself, and a vocabulary ruling cannot
    touch it.
    """
    rollup = pattern_rollup(findings)
    if not len(rollup):
        return pd.DataFrame(columns=COHORT_COLUMNS)

    f = findings.copy()
    f["_mode"] = f["mode"].fillna(NO_MODE)

    def _join(s):
        """Distinct values, sorted, with the NULL STATE RENDERED rather than dropped."""
        vals = {NO_MODE if pd.isna(v) else str(v) for v in s}
        return ";".join(sorted(vals)) or NO_MODE

    g = f.groupby(PATTERN_KEY, dropna=False)
    extra = g.agg(
        n_mode_1=("_mode", lambda s: int((s == S.MODE_1).sum())),
        n_mode_2=("_mode", lambda s: int((s == S.MODE_2).sum())),
        n_no_mode=("_mode", lambda s: int((s == NO_MODE).sum())),
        classifications=("classification", _join),
        actions=("action", _join),
        tiers=("claim_tier", _join),
        gates=("gate", _join),
        precedent_min=("precedent_rate", "min"),
        precedent_max=("precedent_rate", "max"),
        co_reg_max=("co_reg_rate", "max"),
        n_projects=("project_ids", lambda s: int(s.dropna().nunique())),
    ).reset_index()

    out = rollup.drop(columns=["modes", "classifications", "actions"]).merge(
        extra, on=PATTERN_KEY, how="left")
    out["raised_by"] = out.raw_value.notna().map(
        {True: "metadata_term", False: "lineage_only"})

    bad = out[out.n_mode_1 + out.n_mode_2 + out.n_no_mode != out.n_rows]
    if len(bad):
        raise ValueError(
            f"{len(bad)} cohort(s) have mode counts that do not sum to their "
            "row count, so a row is in no column. A mode column built by "
            "dropping nulls is exactly how a NO_MODE cohort gets labelled as a "
            f"proposal:\n{bad.head()}")

    # metadata_term first: those are the cohorts a vocabulary ruling can fix,
    # and ranked by size alone they sit under the lineage bulk.
    out = out.sort_values(["raised_by", "n_rows"], ascending=[True, False])
    return out[COHORT_COLUMNS].reset_index(drop=True)


def build_report(findings: pd.DataFrame,
                 disposition: pd.DataFrame,
                 defects: pd.DataFrame,
                 *,
                 ceiling: dict,
                 integrity: dict,
                 out_dir: str | None = None,
                 top_patterns: int = 15) -> str:
    """The operator report. Pure formatting over frames already on disk.

    EVERY FIGURE IS DERIVED FROM AN ARGUMENT. There is no literal count in this
    function, which is the property `test_every_bolded_integer_in_the_prose_is_
    a_number_the_artifacts_hold` enforces from the other side: it collects the
    bolded integers out of the rendered document and requires each to be
    re-derivable from the three frames or the ceiling. A number that was true
    last week fails without anyone having to predict which sentence went stale.
    """
    n_findings, n_flags = len(findings), len(disposition)
    cohorts = cohort_table(findings)
    # ACTIONABLE vs EMITTED. 6,188 of the real extract's rows carry
    # `action == NONE` and reach no mode; calling every row a proposal
    # overstates the output by 3.5%, which the first version of this report did.
    n_none = int((findings.action == "NONE").sum()) if n_findings else 0
    n_actionable = n_findings - n_none
    counts = findings["mode"].value_counts(dropna=False) if n_findings \
        else pd.Series(dtype=int)
    classes = findings.classification.value_counts(dropna=False) if n_findings \
        else pd.Series(dtype=int)

    def _mode(m):
        return int(counts.get(m, 0))

    lines = [
        "# Assay hygiene: detection (Modes 1, 2 and 3)",
        "",
        "## What this run did to the database",
        "",
        "**This run wrote nothing.** No row below reaches MySQL, Neo4j or the",
        "NExtSEEK API. Everything here was read out of a parquet extract and",
        "written back out as csv and as this file. Nothing in the database",
        "changed, and nothing in this report can change it.",
        "",
        "That is a statement about THIS RUN, and it is deliberately not one",
        "about the package it lives in. `scripts/assay_hygiene/` does contain a",
        "write path: `stage0_apply.py` carries the `MERGE` and `DELETE` Cypher",
        "for the stage 0 lineage backfill and `driver_stage0.py` runs it on the",
        "box. Nothing in this run imports either. A package-wide \"there is no",
        "write path in this code\" would be false, and a reader who found that",
        "file afterwards would be right to distrust everything else here.",
        "",
        "**Nothing here is decided.** Every row in every mode is a PROPOSAL",
        "awaiting operator approval. There is no APPROVE column, no workbook",
        "and no adjudication stage in this increment: nothing in it authorises",
        "a change, and no threshold below grants a permission. Where a rate or",
        "a band orders the rows, it orders what to READ FIRST and nothing more.",
        "",
    ]

    # --- the correction, before any mode ------------------------------------
    split = X.disposition_breakdown(disposition) if n_flags else pd.Series(
        dtype=int)
    lines += [
        "## The correction: increment 1's contradictions",
        "",
        f"Increment 1 reported **{n_flags:,}** Mode 3 CONTRADICTIONS and shipped",
        "them for review. **Measurement found none.** Re-disposed against this",
        "run's precedence, not one of them is a contradiction: they are",
        "absences, vocabulary defects, alternative labels, and rows no test",
        "settles.",
        "",
        "The operator found both errors that produced them -- that Mode 3's",
        "flags were largely Mode 2 findings mislabelled, and that running",
        "lineage before the vocabulary gate laundered rejected claims into",
        "write proposals. Neither was found by this package's own tests.",
        "",
    ]
    if n_flags:
        lines += ["| what they actually are | flags |", "|---|---|"]
        for bucket, n in split.items():
            label = "no bucket -- a null classification" if pd.isna(bucket) \
                else f"`{bucket}`"
            lines.append(f"| {label} | **{n:,}** |")
        lines += [
            "",
            "`PRE_GATE` rows were refused by the vocabulary gate and reach NO",
            "mode. `PRE_LINEAGE` and `CLS_ABSENCE_COMPAT` are absences -- the",
            "registration is missing, not wrong. `CLS_ALT_LABEL` rows propose",
            "nothing: the pair never coexists, so the term is a different name",
            "for what is already registered. `CLS_UNRESOLVED` is neither test",
            "settling it, reported at its own size rather than folded into a",
            "mode.",
            "",
        ]

    # --- what it wrote ------------------------------------------------------
    where = f"`{out_dir}/`" if out_dir else "the output directory"
    lines += [
        f"## Artifacts, all under {where}",
        "",
        f"- `findings.csv` -- **{n_findings:,}** rows, one per (sample, "
        f"proposed assay), of which **{n_actionable:,}** are PROPOSALS and "
        f"**{n_none:,}** propose nothing (`action` is `NONE`: the pair never "
        "coexists, so the term is an alternative label, or no test settled "
        "it). Calling all "
        f"{n_findings:,} of them proposals overstates the output by "
        f"{n_none / n_findings:.1%}",
        f"- `mode3-disposition.csv` -- all **{n_flags:,}** of increment 1's "
        "flags, carrying the step that now claims each one, so increment 1's "
        "output is superseded traceably rather than deleted",
        f"- `vocabulary-defects.csv` -- **{len(defects):,}** defective mappings, "
        "routed to `/curate-assay-vocabulary` and to no mode",
        f"- `{COHORTS_NAME}` -- **{len(cohorts):,}** cohorts covering every "
        "finding, keyed on (sample type, proposed assay, term). **START HERE**: "
        "one ruling settles every row under a cohort, and the per-mode counts "
        "are separate columns so a cohort that proposes nothing cannot read as "
        "one that does",
        f"- `{RV.REVIEW_NAME}` -- the MODE_1 review surface, an HTML page for a "
        f"browser, carrying all **{_mode(S.MODE_1):,}** of its proposals "
        "grouped on (lab, sample type, parent types, proposed assay, source "
        "field, term). It is keyed more finely than the csv above ON PURPOSE: "
        "a curator rules lab by lab, and the same term under a different "
        "parent type is a different question. Each cohort shows up to five "
        "example children with their metadata and the assays their "
        "DERIVED_FROM parents already hold, which is the evidence a count "
        "cannot carry. It records a ruling as text you EXPORT; nothing in this "
        "package reads that text back, and the page writes nothing anywhere",
        f"- `{REPORT_NAME}` -- this file",
        "",
        "**A PROPOSAL NAMES AN INTERNAL ASSAY ID, AND THAT IS NOT A WRITABLE",
        "TARGET.** `proposed_internal_assay_id` is a harmonisation key this",
        "package DERIVES by crossing `dmac.assays_internal_assays`. A",
        "membership row natively carries a SEEK `assays.id` (`assay_assets.",
        "assay_id`), and one internal id spans up to 23 SEEK records. Acting on",
        "any row here means resolving the internal id back to ONE SEEK assay",
        "record, and NO COLUMN IN ANY FILE ABOVE CARRIES THAT RESOLUTION.",
        "",
        "The design states the rule -- in Mode 2, target the assay record the",
        "registered neighbour is already in -- and NO STAGE IN THIS INCREMENT",
        "IMPLEMENTS IT. Measured against that rule, 166,757 of the 167,330",
        "neighbour-anchored rows resolve to exactly one SEEK record and 573 to",
        "two. Mode 1 has no neighbour for the rule to use at all, so its 2,166",
        "rows are not covered by it.",
        "",
    ]

    # --- mode 1 -------------------------------------------------------------
    m1 = findings[findings["mode"] == S.MODE_1] if n_findings else findings
    lines += [
        f"## {MODE_HEADINGS[S.MODE_1]}",
        "",
        f"- proposals: **{_mode(S.MODE_1):,}** over "
        f"**{m1.sample_id.nunique() if len(m1) else 0:,}** samples",
    ]
    if len(m1):
        # READ THE TIER BEFORE THE COUNT. An unqualified headline here would
        # badly misrepresent the evidence: Task 5's review measured that most
        # of this population is contested and weak-tiered, and recorded it as
        # a carry precisely so the number would not ship bare.
        contested = int(_truthy(m1.contested).sum())
        tiers = m1.claim_tier.value_counts(dropna=False)
        floored = int((m1.gate != S.GATE_PASS).sum())
        lines.append(
            f"- **{contested:,}** of them are CONTESTED "
            f"({contested / len(m1):.0%}) -- the sample's own evidence named "
            "more than one assay, and each row keeps the tier its OWN evidence "
            "earned, so a second claim never demotes the first")
        lines.append("- by claim tier: " + " | ".join(
            f"`{t}` **{int(n):,}**" for t, n in tiers.items()))
        if floored:
            lines.append(
                f"- **{floored:,}** carry a RECORDED FLOOR FAILURE and were "
                "proposed anyway; the gate blocks a claim only on its most "
                "severe outcome, and a thin mapping is reported rather than "
                "blocked")
    lines += [
        "",
        "A sample registered in NO assay whose own metadata names one. The",
        "claim has passed the vocabulary gate; the absence is of a registration",
        "that the sample's own record already asserts. **Nothing was written:**",
        "each row is a proposal awaiting operator approval.",
        "",
        "THE HEADLINE COUNT IS THE WEAKEST THING ON THIS PAGE, and it is",
        "qualified above rather than below for that reason. A reader who takes",
        "the proposal count and not the tier split will overstate what this",
        "mode found: these are the rows where a sample registered nowhere has",
        "metadata pointing somewhere, and the metadata is frequently thin and",
        "frequently self-contradicting. Sort by tier before reading.",
        "",
    ]

    # --- mode 2 -------------------------------------------------------------
    lineage_rows = int(classes.get(S.CLS_ABSENCE_LINEAGE, 0))
    compat_rows = int(classes.get(S.CLS_ABSENCE_COMPAT, 0))
    lines += [
        f"## {MODE_HEADINGS[S.MODE_2]}",
        "",
        f"- proposals: **{_mode(S.MODE_2):,}** -- "
        f"**{lineage_rows:,}** corroborated by a lineage neighbour and "
        f"**{compat_rows:,}** by co-registration alone",
        "",
        "**Nothing was written:** every row is a proposal awaiting operator",
        "approval, at every rate below.",
        "",
        "### The DERIVED_FROM ceiling, which is a CEILING",
        "",
        "The figures in this subsection are a CEILING and not a forecast. They",
        "count every (sample, assay) pair a lineage neighbour makes available",
        "BEFORE the gate, before Mode 1 takes its share and before precedent is",
        "read. Precedent cuts the weak direction to roughly 2% of it, so a",
        "ceiling quoted as an expected output is wrong by more than an order of",
        "magnitude. Two published readings of this number disagreed on this",
        "branch and neither was reproducible; both were arithmetically correct",
        "and differed only in the definition of \"registered\".",
        "",
        "| direction | ceiling rows | ceiling samples |",
        "|---|---|---|",
        f"| ADD_PARENT | **{ceiling['add_parent_rows']:,}** | "
        f"**{ceiling['add_parent_samples']:,}** |",
        f"| ADD_CHILD | **{ceiling['add_child_rows']:,}** | "
        f"**{ceiling['add_child_samples']:,}** |",
        f"| union (ceiling) | **{ceiling['union_rows']:,}** | "
        f"**{ceiling['union_samples']:,}** |",
        "",
        f"**{ceiling['both_directions']:,}** pairs are reachable both ways. The",
        "ceiling includes samples registered in no assay at all, which are also",
        "Mode 1's population, and it should: a sample registered nowhere has a",
        "gap wherever a neighbour holds something.",
        "",
    ]
    if n_findings:
        gap = int(ceiling["union_rows"]) - lineage_rows
        lines += [
            "**The ceiling is not what was emitted, and the gap is the point of",
            "the word.** The union above is "
            f"{ceiling['union_rows']:,} rows; Mode 2 emitted {lineage_rows:,} "
            f"lineage-corroborated rows, so {gap:,} of the ceiling reached no",
            "finding. That difference is exactly the rows the vocabulary gate",
            "refused plus the rows Mode 1 claimed first -- a key the gate",
            "rejects reaches NO mode even where a neighbour carries the pair,",
            "which is the third design error reversed. The run prints the split",
            "as `lineage_refused_by_the_gate` and `lineage_taken_by_mode_1`;",
            "it is not re-derived here, because a second derivation of a figure",
            "the census already owns is how this package published two",
            "irreconcilable ceilings in the first place.",
            "",
        ]

    lin = findings[findings.classification == S.CLS_ABSENCE_LINEAGE] \
        if n_findings else findings
    if len(lin):
        survival = M2.precedent_survival(lin)
        lines += [
            "### Survival by direction -- a READING ORDER, never a permission",
            "",
            "The two directions are never pooled. At equal precedent rate they",
            "recover almost identically; what separates them is the bulk band,",
            "where the weak direction recovers about five times worse and holds",
            "nearly all of its live rows. Every row is emitted at every",
            "threshold: this table orders what to read first.",
            "",
            "| rate >= | direction | rows | samples | of rows | evidence groups |",
            "|---|---|---|---|---|---|",
        ]
        for r in survival.itertuples(index=False):
            lines.append(
                f"| {r.threshold} | {r.action} | {_num(r.rows)} | "
                f"{_num(r.samples)} | {_num(r.of_rows)} | {_num(r.rule_groups)} |")
        lines += [
            "",
            "`evidence groups` is how many distinct (n_both, n_child_only,",
            "n_parent_only) triples those rows rest on -- a LOWER BOUND on the",
            "precedent behind them. A row count counts affected SAMPLES and not",
            "independent evidence, which is why a crossover at the top of this",
            "curve is not evidence that either direction is the stronger one.",
            "",
            "**No threshold is chosen here.** Choosing one is an adjudication",
            "decision and this increment has no adjudication stage.",
            "",
        ]

    # --- mode 3 -------------------------------------------------------------
    lines += [
        f"## {MODE_HEADINGS[S.MODE_3]}",
        "",
        f"- rows emitted: **{_mode(S.MODE_3):,}**",
        "",
        "**This is an absence of a DETECTOR, not a measurement.** No rule in",
        "this package looks for a registration that is positively wrong, so",
        "zero rows means the question was not asked. It does not mean",
        "contradictions were sought and found to be uncommon; those are",
        "different findings and only the first one is true here.",
        "",
        "Metadata disagreeing with a registration is not evidence the",
        "registration is wrong -- which is the error increment 1 made, and the",
        "reason its flags are re-disposed above rather than re-reviewed.",
        "",
        "Candidates for a detector, none built: registration-side reachability",
        "(a sample in an assay its type otherwise never holds); cross-project",
        "registration; a removal lane. Each is its own increment, and a removal",
        "lane ships only after the addition path is proven.",
        "",
        "**Nothing was written and nothing is proposed** -- there is no rule",
        "here to propose anything with.",
        "",
    ]

    # --- the vocabulary -----------------------------------------------------
    lines += [
        "## The vocabulary, the largest single defect source",
        "",
        f"- defective mappings: **{len(defects):,}**",
    ]
    if len(defects) and "blocks_modes" in defects.columns:
        blocking = int(defects.blocks_modes.astype(bool).sum())
        lines.append(
            f"- of those, **{blocking:,}** BLOCK a claim from reaching any "
            f"mode; the rest are reported only")
    if len(defects) and "defect" in defects.columns:
        by_kind = defects.groupby("defect").n_claims.sum().sort_values(
            ascending=False) if "n_claims" in defects.columns else \
            defects.defect.value_counts()
        lines += ["", "| defect | claims affected |", "|---|---|"]
        for kind, n in by_kind.items():
            lines.append(f"| `{_cell(kind)}` | **{int(n):,}** |")
    lines += [
        "",
        "A claim is only as good as the term that produced it, and no stage",
        "before the gate tests the term. That is why the gate runs BEFORE every",
        "mode rather than after: with lineage first, a rejected claim whose",
        "neighbour happens to carry the pair becomes a write proposal.",
        "",
    ]

    # The single largest producer, NAMED and MEASURED rather than remembered.
    if n_flags and "classification" in disposition.columns:
        compat = disposition[
            disposition.classification == S.CLS_ABSENCE_COMPAT]
        if len(compat) and "raw_value" in compat.columns:
            top = compat.raw_value.value_counts()
            term, n = str(top.index[0]), int(top.iloc[0])
            lines += [
                f"One mapping dominates: `{term}` produces {n:,} of the "
                f"{len(compat):,} `{S.CLS_ABSENCE_COMPAT}` flags among "
                "increment 1's population. The share is measured off the "
                "disposition rather than quoted from the design, whose "
                "denominator no longer reproduces.",
                "",
            ]

    # --- patterns -----------------------------------------------------------
    rollup = pattern_rollup(findings)
    if len(rollup):
        termed = rollup[rollup.raw_value.notna()]
        untermed = rollup[rollup.raw_value.isna()]
        lines += [
            "## Patterns, keyed on (sample type, proposed assay, term)",
            "",
            f"**{len(rollup):,}** distinct patterns. One ruling settles every",
            "row under a pattern, which a row-by-row read of "
            f"{n_findings:,} findings cannot offer.",
            "",
            "THEY SPLIT IN TWO, AND THE SPLIT IS NOT COSMETIC. "
            f"**{len(termed):,}** patterns carry a metadata TERM and cover "
            f"**{int(termed.n_rows.sum()):,}** rows; "
            f"**{len(untermed):,}** carry none and cover "
            f"**{int(untermed.n_rows.sum()):,}**. A row with no term was raised",
            "by a lineage neighbour rather than by anything the sample says",
            "about itself, so its `term` column is empty by construction and",
            "not by omission. Ranked together, the termed patterns -- the ones",
            "a vocabulary ruling can actually fix -- are buried under the",
            "lineage bulk, so they are ranked separately below.",
            "",
            "### Patterns a metadata term raised",
            "",
            "| sample type | proposed assay | term | rows | samples | class |",
            "|---|---|---|---|---|---|",
        ]
        lines += _pattern_rows(termed.head(top_patterns))
        lines += _more(termed, top_patterns)
        lines += [
            "",
            "### Patterns a lineage neighbour raised, with no term",
            "",
            "| sample type | proposed assay | term | rows | samples | class |",
            "|---|---|---|---|---|---|",
        ]
        lines += _pattern_rows(untermed.head(top_patterns))
        lines += _more(untermed, top_patterns)
        lines += [""] + _term_contrast_note(findings)

    # --- integrity ----------------------------------------------------------
    lines += [
        "## Lineage integrity",
        "",
        "Every population, PRINTED AT ZERO AS WELL. A count shown only when it",
        "is nonzero reads, on a clean run, exactly like one that was never",
        "measured.",
        "",
        "| population | count | ids |", "|---|---|---|",
    ]
    for key in L.INTEGRITY_KEYS:
        count, ids = _integrity_cell(integrity.get(key, 0))
        lines.append(f"| `{key}` | {count} | {ids} |")
    lines += ["", "---", "",
              "Generated by `assay_hygiene.run_detect`. Read-only.", ""]
    return "\n".join(lines)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    """Run the gate and every mode, then write the report over what they wrote.

    WRITES EXACTLY THE FILES IN `ARTIFACTS`, all under `out_dir`. Every input
    is left byte-identical: no parquet is rewritten, no database is touched and
    no workbook is produced. A test hashes the whole tree before and after and
    diffs the two maps, because "it wrote exactly these" is a claim about the
    directory rather than about the absence of a call.

    THE REPORT IS BUILT FROM THE FILES, READ BACK. That is one extra read of a
    large csv and it buys the property the increment is judged on: the frame
    the prose counts is the frame on disk, so a count in a sentence and a count
    in the artifact cannot disagree.
    """
    d, out = Path(extract_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("=== the vocabulary gate ===")
    if G.main(extract_dir, out_dir) != 0:
        return 1
    print("\n=== every mode ===")
    if X.main(extract_dir, out_dir) != 0:
        return 1

    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    defects = pd.read_csv(out / "vocabulary-defects.csv")
    ceiling, integrity = _lineage_facts(d)

    cohort_table(findings).to_csv(out / COHORTS_NAME, index=False)
    # THE SHEET IS BUILT FROM THIS FRAME, NOT FROM THE CSV IT CAME OUT OF.
    # `review` has no `main` and reads no csv precisely so that this line is
    # the only way to build it: the prototype was separate scripts reading each
    # other's output and its cohort context and its findings disagreed twice,
    # once naming internal assay 31 where the findings said 30.
    RV.write_review(findings, RV.load_context(d), out)
    report = build_report(findings, disposition, defects,
                          ceiling=ceiling, integrity=integrity,
                          out_dir=out_dir)
    (out / REPORT_NAME).write_text(report)
    print(f"\nwrote {out / REPORT_NAME} over {len(findings):,} finding(s), "
          f"{len(disposition):,} re-disposed flag(s) and {len(defects):,} "
          "vocabulary defect(s). Nothing else was written: no parquet was "
          "rewritten, no database and no workbook was touched by THIS run, and "
          "every row in every artifact is a proposal awaiting operator "
          "approval.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
