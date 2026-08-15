# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Run the whole evidence layer over an extract and write the operator report.

Read-only end to end: it reads parquet off disk and writes csv, parquet and
markdown under `assay-hygiene/`. Nothing here reaches MySQL, Neo4j or the API.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.run_evidence

The report is the deliverable, not the counts. An operator reads it to decide
whether any of this is trustworthy, and two of the things it has to do cannot
be done by a count:

  * SAY that nothing was written. A hygiene tool that silently corrected the
    database and a hygiene tool that only looked produce similar-looking
    summaries, and the difference is the whole safety argument. It is stated in
    the first paragraph, in the section that lists the artifacts, and again
    under Mode 3, because a reader who skims one will meet another.

    Scoped to THIS STAGE, and the scope is load-bearing. The report is the one
    artifact written for a reader who was not present, and `scripts/
    assay_hygiene/` does contain a write path: `stage0_apply.py` carries the
    `MERGE` and `DELETE` Cypher for the stage 0 lineage backfill and
    `driver_stage0.py` runs it on the box. Nothing here reaches them, but a
    package-scope "there is no write path in this code" is false and a reader
    who found stage0_apply.py afterwards would be right to distrust the rest.

  * MAKE MODE 3 JUDGEABLE. Its precision is agreement with a human and there is
    no automated proxy for that, so the report must hand a curator something
    they can actually rule on. 866 rows is not that. Those 866 flags collapse
    to 22 distinct (sample type, registered assays, claimed assay, field,
    value) patterns, so the report ships the PATTERNS with one real example
    each: ruling on 22 exemplars adjudicates all 866, while a 20-row random
    sample would land almost entirely inside the three largest patterns and
    leave most of the judgement surface untouched. That is a deliberate
    departure from the brief's "sample of 20 flagged rows"; the exemplar set is
    22 rows and it covers 100% of the flags rather than 2.3% of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import audit as A
from . import claims as C
from . import precedent as P
from . import vocabulary as V

# Identity is the ID tuple, display is the titles. Grouping on the titles
# instead would let two assays that share a display string collapse into one
# pattern -- the same title-as-identity mistake `merge_vocabulary` and
# `audit_contradictions` both refuse. Measured on the real extract both
# groupings happen to give 22 today, which is exactly why the choice has to be
# made on the rule rather than on the number.
PATTERN_KEY = ["sample_type", "registered_internal_assay_ids",
               "claimed_internal_assay_id", "source_field", "raw_value"]

TIER_ORDER = (S.T_CORROBORATED, S.T_STRONG, S.T_WEAK)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _cell(v) -> str:
    """A value safe to drop into a markdown table cell.

    `raw_value` is curator free text and a literal `|` in it silently splits
    the row into extra columns, shifting every later cell one place left --
    a table that still renders, with the wrong assay beside the wrong sample.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return str(v).replace("|", "\\|").replace("\n", " ")


def _num(v, places: int = 0) -> str:
    """A count or a rate for a table cell, tolerating a missing value.

    `n_samples` is NaN on any row a producer left it off -- a `proposed` batch
    written by hand is the live case -- and `int(nan)` raises, which would take
    down the whole report over a display column.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _cell(v)
    if pd.isna(f):
        return "-"
    return f"{f:,.{places}f}"


def _registered(ids, titles) -> str:
    """`12 Tissue Collection | 115 Library Creation` from the two `;` columns.

    `registered_internal_assay_titles` is positionally aligned with
    `registered_internal_assay_ids` by construction (audit.py builds both from
    one sorted list), so zipping them is the intended read. Where the two ever
    disagree in length the ids are printed alone rather than mispaired: a
    silently shifted pairing would name the wrong assay in the one artifact a
    curator rules on.
    """
    id_list = [i for i in str(ids).split(";") if i]
    title_list = [t for t in str(titles).split(";")] if isinstance(titles, str) else []
    if len(title_list) != len(id_list):
        return " | ".join(id_list)
    return " | ".join(f"{i} {t}" for i, t in zip(id_list, title_list))


PATTERN_COLUMNS = PATTERN_KEY + [
    "registered_display", "claimed_internal_assay_title", "tiers", "n",
    "n_projects", "purity", "n_samples", "runner_up",
    "peer_carriers", "peer_registered", "peer_rate",
    "n_examples", "example_sample_id", "example_uuids",
]


def term_carriers(meta: dict[int, dict]) -> dict[tuple[str, str], set[int]]:
    """(field, normalised value) -> every sample whose metadata carries it.

    This is the denominator behind `peer_rate`, and it is deliberately the
    WHOLE population rather than the labelled-edge population `n_samples`
    counts: the question it answers is "of everyone who says this, how many are
    registered where this one claims", and a sample with no labelled producing
    edge still has a registration and still counts as a peer.
    """
    out: dict[tuple[str, str], set[int]] = {}
    for sid, d in meta.items():
        for field in S.CLAIM_FIELDS:
            value = S.normalise_value(d.get(field))
            if value:
                out.setdefault((field, value), set()).add(sid)
    return out


def runner_up_index(edges: pd.DataFrame, meta: dict[int, dict],
                    titles: dict[int, str] | None = None,
                    ) -> dict[tuple[str, str], str]:
    """(field, value) -> the SECOND-place assay in the vote, rendered.

    `learn_vocabulary` takes the mode of an edge-weighted tally and emits only
    the winner, which is what makes a Mode 3 flag possible in the first place:
    where a term's vote is split, the minority class is registered in the
    runner-up and gets accused of contradicting the winner. A curator cannot
    see that from the flag row -- `Blood` reads as an unambiguous claim on
    Tissue Collection until you learn it split 69/31 against the very assay the
    flagged samples are registered in.

    Reaches for `vocabulary._tally`, the module-private walk, on purpose: it is
    the one function holding the full Counter, and re-deriving the vote here
    would put a second copy of the tally rule in the tree. Same package, which
    is exactly what a single leading underscore permits.
    """
    tally, _ = V._tally(edges, meta, lambda _: True)
    titles = titles or {}
    out: dict[tuple[str, str], str] = {}
    for key, counter in tally.items():
        total = sum(counter.values())
        top = counter.most_common(2)
        if len(top) < 2 or not total:
            out[key] = "none (unanimous)"
            continue
        iaid, n = top[1]
        out[key] = f"{iaid} {titles.get(iaid, '?')} {n / total:.0%}"
    return out


def flag_purity_contrast(claims: pd.DataFrame, audit: pd.DataFrame,
                         vocab: pd.DataFrame) -> dict:
    """How much more ambiguous the FLAGGED terms are than the eligible ones.

    Computed rather than quoted, because it is the number that stops a reader
    carrying the aggregate tier accuracy into the flag table, and a hard-coded
    one goes stale the first time the vocabulary moves.
    """
    pur = {(r.source_field, S.normalise_value(r.raw_value)): r.purity
           for r in vocab.itertuples()}

    def series(frame):
        return pd.Series([
            pur[k] for k in (
                (r.source_field, S.normalise_value(r.raw_value))
                for r in frame.itertuples())
            if k in pur], dtype="float64")

    eligible = claims[claims.tier.isin(A.DEFAULT_TIERS)
                      & ~pd.Series(claims.contested).fillna(False).astype(bool)] \
        if len(claims) else claims
    ep, fp = series(eligible), series(audit)
    if not len(ep) or not len(fp):
        return {}
    return {
        "eligible_n": len(ep), "flagged_n": len(fp),
        "eligible_median": float(ep.median()), "flagged_median": float(fp.median()),
        "eligible_below": float((ep < 0.80).mean()),
        "flagged_below": float((fp < 0.80).mean()),
    }


def review_patterns(audit: pd.DataFrame, *,
                    vocab: pd.DataFrame | None = None,
                    runners: dict | None = None,
                    carriers: dict | None = None,
                    registered: dict | None = None,
                    projects: dict | None = None) -> pd.DataFrame:
    """The distinct contradictions behind the flags, commonest first.

    This is the artifact Mode 3 is actually judged on. It is a rollup and not a
    sample: every flag is represented by the pattern it belongs to, so a
    curator ruling on the table rules on all of them, and `n` tells them what
    each ruling is worth.

    Every enrichment argument is optional and the bare `review_patterns(audit)`
    call still returns the pure rollup, so the grouping stays testable without
    five indexes in hand. What each adds, and why a curator needs it:

      `vocab`       `purity` and `n_samples` for the term that drove the flag.
          A flag off a term at purity 1.00 and one at 0.52 are different claims
          and the row does not otherwise say which it is.
      `runners`     the runner-up label. See `runner_up_index`.
      `carriers` + `registered`   `peer_rate`: of every sample carrying this
          term, how many ARE registered in the assay this pattern claims. This
          is the strongest true/false discriminator measured on this data and
          it is independent of purity -- `Blood` sits at purity 0.69 and yet
          98.7% of its 7,195 carriers are registered in Tissue Collection, so
          the 97 that are not look like a genuine gap rather than a vote
          artifact. Sorting the 22 patterns by it separates them far more
          cleanly than sorting by purity does.
      `projects`    `n_projects`, and with it the exemplar count: a pattern
          spanning three projects gets three exemplars, one per project, because
          a single example cannot show a curator that the pattern recurs under
          different curators' conventions.
    """
    if not len(audit):
        return pd.DataFrame(columns=PATTERN_COLUMNS)
    pur = {(r.source_field, S.normalise_value(r.raw_value)):
           (r.purity, r.n_samples)
           for r in (vocab.itertuples() if vocab is not None else ())}
    rows = []
    for key, part in audit.groupby(PATTERN_KEY, dropna=False, sort=False):
        first = part.iloc[0]
        term = (first.source_field, S.normalise_value(first.raw_value))
        claimed = int(first.claimed_internal_assay_id)

        # exemplars: one per project, capped at 3. Deterministic -- projects in
        # sorted order, lowest sample_id within each -- so the csv a curator
        # diffs does not reshuffle between runs.
        by_project: dict[str, int] = {}
        for sid in sorted(int(s) for s in part.sample_id):
            by_project.setdefault(
                str(projects.get(sid, "?")) if projects else "?", sid)
        picked = [by_project[p] for p in sorted(by_project)][:3]
        uuid_of = dict(zip((int(s) for s in part.sample_id), part.uuid))

        peers = carriers.get(term, set()) if carriers else set()
        have = (sum(1 for s in peers if claimed in registered.get(s, set()))
                if peers and registered else 0)

        rows.append({
            **dict(zip(PATTERN_KEY, key)),
            "registered_display": _registered(
                first.registered_internal_assay_ids,
                first.registered_internal_assay_titles),
            "claimed_internal_assay_title": first.claimed_internal_assay_title,
            "tiers": "; ".join(sorted(set(part.tier))),
            "n": len(part),
            "n_projects": len(by_project) if projects else None,
            "purity": pur.get(term, (None, None))[0],
            "n_samples": pur.get(term, (None, None))[1],
            "runner_up": runners.get(term) if runners else None,
            "peer_carriers": len(peers) if peers else None,
            "peer_registered": have if peers else None,
            "peer_rate": (have / len(peers)) if peers else None,
            "n_examples": len(picked),
            "example_sample_id": picked[0],
            "example_uuids": "; ".join(str(uuid_of[s]) for s in picked),
        })
    out = pd.DataFrame(rows, columns=PATTERN_COLUMNS)
    # Sorted by size then by the whole key, so the ordering is total and the
    # csv a curator diffs between runs does not reshuffle on a tie.
    return out.sort_values(["n"] + PATTERN_KEY,
                           ascending=[False] + [True] * len(PATTERN_KEY),
                           ignore_index=True)


def build_report(precedent, claims, audit, vocab, unresolved, *,
                 unresolved_samples: int | None = None,
                 dial_counts: dict | None = None,
                 flag_purity: dict | None = None,
                 patterns: pd.DataFrame | None = None,
                 out_dir: str | None = None) -> str:
    """The operator report. Pure formatting over frames already computed.

    The three keyword arguments are facts the frames cannot supply and are all
    optional, so the five-positional contract still holds:

      `unresolved_samples`  how many DISTINCT samples carry an unresolved term.
          `unresolved.n_samples.sum()` is not that number -- it adds per-term
          counts, so a sample carrying two unresolved terms is counted twice.
          Measured on the real extract the two differ by 65% (24,322
          occurrences against 14,753 samples). Without it the report names the
          sum as occurrences, which is what it is, and stays silent about
          samples rather than guessing.
      `dial_counts`   {(include_contested, include_unmappable): n_flags}, so
          the report can price the two exclusions instead of asserting them.
      `out_dir`       where the rows this summarises were written.
    """
    lines = [
        "# Assay hygiene: evidence layer",
        "",
        "**This stage writes nothing.** No row here reaches MySQL, Neo4j or the",
        "NExtSEEK API. Everything below is read out of a parquet extract and",
        "written back out as csv, parquet and this file. Nothing in the database",
        "changed, and nothing in this report can change it: nothing this stage",
        "runs has a write path to enable.",
        "",
        "That is a statement about this stage, and it is deliberately not one",
        "about the package it lives in. `scripts/assay_hygiene/` also ships",
        "`stage0_apply.py`, which carries `MERGE` and `DELETE` Cypher for",
        "Neo4j `DERIVED_FROM` relationships, and `driver_stage0.py`, which is",
        "piped into `manage.py shell` on the box to run it. That is the stage 0",
        "lineage backfill -- a separate increment, already applied to",
        "production, off an operator-reviewed manifest. Nothing in this stage",
        "calls, imports or can reach either of them.",
        "",
    ]

    # --- vocabulary ---------------------------------------------------------
    lines += ["## Vocabulary", "",
              f"- mapped terms: **{len(vocab):,}**"]
    if len(vocab):
        thin = int((pd.to_numeric(vocab.n_samples, errors="coerce") < 2).sum())
        untitled = int(vocab.internal_assay_title.isna().sum())
        for prov, n in vocab.provenance.value_counts().items():
            lines.append(f"  - `{prov}`: {n:,}")
        lines.append(
            f"- **{thin:,}** of those terms rest on a single distinct sample."
            " `support` counts EDGES and one sample fans out to many, so a term"
            " can clear the support floor off one curator's one row; read"
            " `n_samples` beside it."
        )
        if untitled:
            lines.append(
                f"- **{untitled:,}** carry no title: their assay has no row in"
                " `dmac.assays_internal_assays`, so the id is a seek"
                " `assays.id` in a different id space. That is an upstream"
                " hygiene defect, surfaced rather than papered over."
            )

    occ = int(pd.to_numeric(unresolved.n_samples, errors="coerce").sum()) \
        if len(unresolved) else 0
    tail = (f"- unresolved terms above the floor: **{len(unresolved):,}**"
            f" ({occ:,} term occurrences)")
    if unresolved_samples is not None:
        tail += f", carried by **{unresolved_samples:,}** distinct samples"
    lines += [tail, ""]

    if len(vocab):
        lines += ["Highest-support mappings:", "",
                  "| field | value | assay | support | samples | purity |",
                  "|---|---|---|---|---|---|"]
        top = vocab.sort_values("support", ascending=False).head(10)
        for r in top.itertuples():
            lines.append(
                f"| {_cell(r.source_field)} | `{_cell(r.raw_value)}` | "
                f"{_cell(r.internal_assay_title)} | {_num(r.support)} | "
                f"{_num(r.n_samples)} | {_num(r.purity, 2)} |"
            )
        lines.append("")

    # --- precedent ----------------------------------------------------------
    pairs = 0
    if len(precedent):
        pairs = len(precedent[precedent.n_both > 0][
            ["project_id", "child_type", "parent_type"]].drop_duplicates())
    lines += [
        "## Precedent (stage B)",
        "",
        f"- rules mined: **{len(precedent):,}** over **{pairs:,}**"
        f" project/hop {_plural(pairs, 'pair', 'pairs')} with precedent",
        "",
        "A rule is one (project, child type, parent type, internal assay)"
        " observed on edges that already exist. `n_both > 0` is what makes it"
        " precedent FOR propagating; a pair seen only child-only or parent-only"
        " is evidence against.",
        "",
    ]

    # --- claims -------------------------------------------------------------
    n_samples = claims.sample_id.nunique() if len(claims) else 0
    lines += [
        "## Claims (stage B2)",
        "",
        f"- claims: **{len(claims):,}** over **{n_samples:,}** samples",
    ]
    if len(claims):
        counts = claims.tier.value_counts()
        for tier in list(TIER_ORDER) + [t for t in counts.index
                                        if t not in TIER_ORDER]:
            if tier in counts:
                lines.append(f"  - `{tier}`: **{int(counts[tier]):,}**")
        contested = int(pd.Series(claims.contested).fillna(False).astype(bool).sum())
        lines.append(
            f"- contested rows: **{contested:,}** -- the sample's own evidence"
            " named more than one assay. Each row keeps the tier its OWN"
            " evidence earned, so a second claim can never demote the first;"
            " contestedness is a column, not a tier."
        )
    lines += [
        "",
        "Tiers are measured, not asserted (2026-08-14, held out BY SAMPLE"
        " against curator-labelled edges): `corroborated` 99.9% accurate,"
        " `strong` 98.4%, `weak` 90.4%.",
        "",
        "**Do not carry those numbers into the Mode 3 table below.** They are"
        " averages over all claims, and a flag is by construction drawn from"
        " the ambiguous tail they average away: a claim can only contradict a"
        " registration when the term behind it is one the vocabulary was NOT"
        " sure about.",
        "",
    ]
    if flag_purity:
        lines += [
            f"- median purity of the term behind a **flag**:"
            f" **{flag_purity['flagged_median']:.3f}**, against"
            f" **{flag_purity['eligible_median']:.3f}** for all"
            f" {flag_purity['eligible_n']:,} flag-eligible claims",
            f"- share of flags whose term sits below 0.80 purity:"
            f" **{flag_purity['flagged_below']:.1%}**, against"
            f" **{flag_purity['eligible_below']:.1%}** of flag-eligible claims",
            "",
        ]
    lines += [
        "Held-out accuracy by the purity of the driving term, measured the same"
        " way as the tier figures above (2026-08-14, train on even sample ids,"
        " score the odd half against labelled producing edges):",
        "",
        "| purity of term | held-out accuracy | test edges |",
        "|---|---|---|",
        "| all 736 terms | 94.1% | 333,717 |",
        "| < 0.75 | **65.8%** | 55,849 |",
        "| 0.75 - 0.90 | 88.1% | 2,916 |",
        "| >= 0.90 | 99.9% | 274,952 |",
        "",
        "So the aggregate is carried by the unambiguous majority, and the band"
        " the flags come from is the one that performs worst. The six terms"
        " driving **764** of the 866 flags -- across 8 patterns, not the six"
        " largest ones -- score **77.1%** held out, not 98.4%.",
        "",
    ]

    # --- mode 3 -------------------------------------------------------------
    pat = patterns if patterns is not None else review_patterns(audit)
    flag_samples = audit.sample_id.nunique() if len(audit) else 0
    lines += [
        "## Mode 3: contradictions",
        "",
        f"- flagged: **{len(audit):,}**"
        f" {_plural(len(audit), 'flag', 'flags')} over"
        f" **{flag_samples:,}** {_plural(flag_samples, 'sample', 'samples')}",
        f"- they collapse to **{len(pat):,}** distinct"
        f" {_plural(len(pat), 'pattern', 'patterns')}",
        "",
        "A flag says: this sample's own metadata names an assay it is not"
        " registered in. It does NOT say which side is wrong. The metadata may"
        " be stale, the registration may be missing, or the vocabulary may have"
        " mapped the term to the wrong assay -- and only a curator can tell"
        " those apart. **Nothing is written either way.**",
        "",
        "Only `corroborated` and `strong` claims can raise one. Contested"
        " claims and samples whose registration cannot be resolved into the"
        " internal id space are excluded by default, both by their own"
        " parameter, so widening either is a deliberate act and no excluded row"
        " is unrecoverable.",
        "",
    ]
    if dial_counts:
        lines += ["| `include_contested` | `include_unmappable` | flags |",
                  "|---|---|---|"]
        for ic in (False, True):
            for iu in (False, True):
                n = dial_counts.get((ic, iu))
                if n is None:
                    continue
                # "(default)" marks the default CONFIGURATION, not each dial
                # that happens to be off. Marking the cells instead put
                # "(default)" beside the off dial of the contested-admitted
                # row, which reads as if that row were a default too -- in a
                # table whose only job is to show what widening costs.
                default = not ic and not iu
                lines.append(
                    f"| {'on' if ic else 'off'} | {'on' if iu else 'off'} |"
                    f" {n:,}{' (default)' if default else ''} |"
                )
        lines.append("")

    if len(pat):
        lines += [
            "### The judgement surface",
            "",
            "Mode 3's precision is agreement with a human and has no automated"
            " proxy, so this is the table to rule on rather than the row dump."
            f" Every one of the {len(audit):,} flags belongs to a pattern below,"
            " and `n` is what each ruling is worth.",
            "",
            "`purity` is the driving term's share of the vote that mapped it,"
            " `evidence` the distinct samples backing that vote, `runner-up`"
            " the assay it beat -- which for most of these IS the assay the"
            " sample is registered in, so the flag is the vocabulary's own"
            " minority class being accused by its majority. **`peers` is the"
            " column to read first**: of every sample carrying this term, how"
            " many ARE registered in the assay this pattern claims. A high peer"
            " rate makes a flag look like a genuine gap; a low one makes it look"
            " like a mapping the term never really supported.",
            "",
            "| n | sample type | registered in | metadata claims | via | purity"
            " | evidence | runner-up | peers in claimed | examples |",
            "|---:|---|---|---|---|---:|---:|---|---|---|",
        ]
        for r in pat.itertuples():
            peers = "-"
            if getattr(r, "peer_carriers", None) and not pd.isna(r.peer_carriers):
                peers = (f"{int(r.peer_registered):,} / {int(r.peer_carriers):,}"
                         f" ({r.peer_rate:.1%})")
            proj = ""
            if getattr(r, "n_projects", None) and not pd.isna(r.n_projects) \
                    and int(r.n_projects) > 1:
                proj = f" _({int(r.n_projects)} projects)_"
            lines.append(
                f"| {r.n:,}{proj} | {_cell(r.sample_type)} |"
                f" {_cell(r.registered_display)} |"
                f" {_cell(r.claimed_internal_assay_id)}"
                f" {_cell(r.claimed_internal_assay_title)} |"
                f" {_cell(r.source_field)} = `{_cell(r.raw_value)}` |"
                f" {_num(r.purity, 2)} | {_num(r.n_samples)} |"
                f" {_cell(r.runner_up)} | {peers} |"
                f" {_cell(r.example_uuids)} |"
            )
        lines.append("")
        if pat.peer_rate.notna().any():
            hi = pat[pat.peer_rate >= 0.93]
            mid = pat[(pat.peer_rate >= 0.85) & (pat.peer_rate < 0.93)]
            lo = pat[pat.peer_rate < 0.85]
            best = hi.sort_values("peer_rate", ascending=False).head(1)
            lines += [
                "### This is not a dismissal",
                "",
                f"**{int(hi.n.sum()):,} of the {len(audit):,} flags"
                f" ({len(hi)} of the {len(pat)} patterns) sit at 93% or higher"
                " peer registration**, and those read as genuine missing"
                " registrations rather than artifacts: nearly every other sample"
                " saying the same thing IS registered where this one claims, and"
                " these are the ones that are not.",
                "",
            ]
            if len(best):
                b = best.iloc[0]
                lines += [
                    f"The clearest case is `{_cell(b.raw_value)}`:"
                    f" {int(b.peer_registered):,} of its"
                    f" {int(b.peer_carriers):,} carriers are registered in"
                    f" {_cell(b.claimed_internal_assay_id)}"
                    f" {_cell(b.claimed_internal_assay_title)}, and the"
                    f" {int(b.n)} flagged here"
                    f" {_plural(int(b.n), 'is the one that is', 'are the ones that are')}"
                    " not.",
                    "",
                ]
            lines += [
                f"A reader who concludes from the mechanism above that Mode 3 is"
                " all vote artifact would discard these. The right reading is"
                " that the flags are MIXED:"
                f" ~{int(hi.n.sum()):,} look like genuine gaps,"
                f" ~{int(lo.n.sum()):,} in {len(lo)} patterns sit below 85% peer"
                f" registration and look like mapping artifacts, and"
                f" {int(mid.n.sum()):,} sit in between. Sorting them is the"
                " curator's job and this table is the instrument for it.",
                "",
                "### The open question this layer does NOT answer",
                "",
                "A floor on what reaches Mode 3 would remove most of the"
                " low-confidence flags. **No threshold is chosen here** -- it is"
                " an output of a curator ruling on these patterns, not a number"
                " to pick off a distribution. But the axis it should ride on is"
                " **peer rate, not purity**, and that is worth stating before"
                " anyone picks one.",
                "",
            ]
            if pat.purity.notna().any():
                corr = pat.purity.corr(pat.peer_rate)
                drop = pat[(pat.purity < 0.75) & (pat.peer_rate >= 0.93)]
                keep = pat[(pat.purity >= 0.75) & (pat.peer_rate < 0.85)]
                missorted = int(drop.n.sum()) + int(keep.n.sum())
                lines += [
                    f"The two axes correlate at only **{corr:.2f}** across these"
                    " patterns, and they disagree in both directions with real"
                    " mass behind the disagreement. A 0.75 purity floor would:",
                    "",
                    f"- **discard {int(drop.n.sum()):,} flags** that sit at 93%+"
                    " peer registration -- "
                    + (", ".join(f"`{_cell(r.raw_value)}` ({r.n} at"
                                 f" {r.peer_rate:.1%})" for r in drop.itertuples())
                       or "none") + ", the cleanest gaps in the set;",
                    f"- **keep {int(keep.n.sum()):,} flags** below 85% peer"
                    " registration -- "
                    + (", ".join(f"`{_cell(r.raw_value)}` ({r.n} at purity"
                                 f" {r.purity:.2f}, peer {r.peer_rate:.1%})"
                                 for r in keep.itertuples()) or "none")
                    + ", the likeliest artifacts.",
                    "",
                    f"That is **{missorted:,} of {len(audit):,} flags"
                    f" ({missorted / len(audit):.1%}) sorted the wrong way** by"
                    " the purity axis alone. Purity measures how consistently a"
                    " term was used across the whole corpus; peer rate measures"
                    " how anomalous THIS registration is against its own cohort,"
                    " which is the question a curator is actually asking. The"
                    " purity band table above remains evidence -- it is why a"
                    " flag's claim should not be trusted at the aggregate tier"
                    " accuracy -- but it is not the axis a floor should ride on.",
                    "",
                ]
        else:
            lines += [
                "### The open question this layer does NOT answer",
                "",
                "A floor on what reaches Mode 3 would remove most of the"
                " low-confidence flags. **No threshold is chosen here**: it is an"
                " output of a curator ruling on these patterns, not a number to"
                " pick off a distribution.",
                "",
            ]

    # --- artifacts ----------------------------------------------------------
    if out_dir:
        lines += [
            "## Artifacts",
            "",
            f"Everything below was written under `{out_dir}/`, and that is the"
            " complete list of what this run touched:",
            "",
            "- `vocabulary.csv` -- the merged term -> assay mapping",
            "- `vocabulary-unresolved.csv` -- the judgement queue",
            "- `precedent.csv` -- stage B rules",
            "- `claims.parquet` -- one row per (sample, claimed assay)",
            "- `mode3-contradictions.csv` -- the flags, at the defaults",
            "- `mode3-contradictions-with-contested.csv` -- the widened set",
            "- `mode3-review-patterns.csv` -- the table above, as rows",
            "- `evidence-report.md` -- this file",
            "",
            "No database, no API, no graph.",
            "",
        ]
    return "\n".join(lines)


def unresolved_sample_count(meta: dict[int, dict],
                            unresolved: pd.DataFrame) -> int:
    """Distinct samples carrying at least one term from the unresolved tail.

    Derived from the frame `unresolved_terms` RETURNED, not from a second copy
    of its filtering rule: which terms are unresolved is decided in exactly one
    place, and this only re-does the sample attribution that the per-term
    counts destroy by summing. `unresolved_terms` emits `raw_value` already
    normalised, and `normalise_value` is idempotent, so normalising here is
    free and keeps the lookup correct if that ever changes.
    """
    if not len(unresolved):
        return 0
    # field -> the unresolved values on it. Keyed by field rather than kept as
    # a flat set of pairs so the scan costs one normalise per (sample, FIELD)
    # rather than one per (sample, TERM): 163,393 samples against 266 terms is
    # 43M normalisations the other way round, for the same answer.
    want: dict[str, set[str]] = {}
    for r in unresolved.itertuples():
        want.setdefault(str(r.source_field), set()).add(
            S.normalise_value(r.raw_value))
    hits = set()
    for sid, d in meta.items():
        for field, values in want.items():
            if S.normalise_value(d.get(field)) in values:
                hits.add(sid)
                break
    return len(hits)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    d, out = Path(extract_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    edges = pd.read_parquet(d / "edges.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    samples = pd.read_parquet(d / "samples.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")

    meta = V.parse_metadata(samples)
    uuids = dict(zip(samples.sample_id.astype(int), samples.uuid))

    learned = V.learn_vocabulary(edges, meta)
    proposed = V.load_vocabulary(out / "vocabulary-proposed.csv")
    curator = V.load_vocabulary(out / "vocabulary-curator.csv")
    vocab = V.merge_vocabulary(learned, proposed, curator, assays)
    V.save_vocabulary(vocab, out / "vocabulary.csv")

    unresolved = V.unresolved_terms(meta, vocab, uuids)
    unresolved.to_csv(out / "vocabulary-unresolved.csv", index=False)

    prec = P.mine_precedent(edges, membership, assays)
    prec.to_csv(out / "precedent.csv", index=False)

    cl = C.sample_claims(meta, uuids, vocab)
    cl.to_parquet(out / "claims.parquet", compression="zstd", index=False)

    au = A.audit_contradictions(cl, membership, assays, nodes)
    au.to_csv(out / "mode3-contradictions.csv", index=False)

    # Both dials priced in the same run. A curator deciding whether to widen
    # one needs the cost in front of them, and re-deriving it later means
    # re-running the whole layer.
    dial_counts = {(False, False): len(au)}
    for ic, iu in ((False, True), (True, False), (True, True)):
        wide = A.audit_contradictions(cl, membership, assays, nodes,
                                      include_contested=ic,
                                      include_unmappable=iu)
        dial_counts[(ic, iu)] = len(wide)
        if (ic, iu) == (True, False):
            wide.to_csv(out / "mode3-contradictions-with-contested.csv",
                        index=False)

    # The five indexes the pattern rollup needs to be judgeable rather than
    # merely counted. `assay_index` supplies the titles the runner-up is
    # rendered with, from the same funnel the audit decoded its ids through, so
    # no second source of truth for a title appears.
    titles = {iaid: title
              for _, iaid, title in P.assay_index(assays).values()}
    pat = review_patterns(
        au,
        vocab=vocab,
        runners=runner_up_index(edges, meta, titles),
        carriers=term_carriers(meta),
        registered=A.registered_internal(membership, assays),
        projects=dict(zip(samples.sample_id.astype(int),
                          samples.project_ids.astype(str))),
    )
    pat.to_csv(out / "mode3-review-patterns.csv", index=False)

    report = build_report(
        prec, cl, au, vocab, unresolved,
        unresolved_samples=unresolved_sample_count(meta, unresolved),
        dial_counts=dial_counts,
        flag_purity=flag_purity_contrast(cl, au, vocab),
        patterns=pat,
        out_dir=out_dir,
    )
    (out / "evidence-report.md").write_text(report)
    print(report)
    print(f"\nwrote {out}/evidence-report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
