# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""A stratified, reproducible validation sample of the rework's own decisions.

    SEED = 20260824

Read-only end to end: it reads `findings.csv`, the extract parquets and the
agent verdict csv, and writes a csv, an html sheet, a key file and a power
statement under `out_dir`. Nothing here reaches MySQL, Neo4j or the API and
nothing it writes is a decision.

    PYTHONPATH=scripts uv run --with pandas --with pyarrow \
        python -m assay_hygiene.validation_sample <artifacts> <extract> \
        <verdicts.csv> <out_dir>

WHY THIS EXISTS. The 2026-08-21 rework reclassified 99,449 of 170,786
proposals as `CLS_UNREACHABLE` (90,478) or `CLS_BOOTSTRAP` (8,971). The only
ground truth this package owns is the operator's 128 hand rulings, and
`tests/test_assay_hygiene_rulings.py` proves those CANNOT validate the
reachability gate: an unreachable pair has zero type registrations so its
precedent rate is structurally 0.0, the sheet he ruled on starts at 0.50, and
the two populations cannot intersect. The central change of the rework has no
human validation at all. This module draws the sample that closes that.

THREE STRATA, ONE QUESTION EACH, ONE SITTING:

    A  CLS_UNREACHABLE, non-bootstrap  90,478 rows   is the gate right?
    B  CLS_BOOTSTRAP                    8,971 rows   real gaps, or noise?
    C  agent-REJECT, still primary     43,604 rows   is the reject side sound?

THE DRAW IS A HASH ORDER AND NOT AN RNG, and that is the whole integrity of the
exercise. `random.sample` and `numpy.random.default_rng` are both reproducible
in principle, but re-deriving their stream needs the same library, the same
version and the same call sequence; a reader who wants to satisfy themselves
that a sample was not chosen AFTER someone saw the answers cannot check either
one by hand. A cohort is drawn iff `sha256("<seed>|draw|<cohort key>")` sorts
in the first n of its stratum, so the selection is a pure function of the seed
and the key, checkable in any language with three lines and no dependency on
this file. `_digest` is the one place it is computed.

TIES AND INPUT ORDER, STATED HONESTLY. The ranking sorts on `(digest, key)`
rather than on the digest alone, which makes the order total -- but a sha256
collision over a few hundred cohort keys is unobservable, so NO TEST IN THIS
REPOSITORY CAN MAKE THAT TIEBREAK MATTER, and it is written for the reader
rather than for a guard. What IS testable, and is tested, is the property it
belongs to: the sample must not depend on the order the cohorts arrive in.
`build_blocks` returns them sorted on band and row count, and a draw that
preserved that order would be a draw weighted by cohort size wearing a hash's
clothes. `test_the_draw_does_not_depend_on_the_order_the_cohorts_arrive_in`
fails when the sort is removed and passes when only the tiebreak is -- which is
the accurate description of what it covers.

THE SAMPLE IS DRAWN AT COHORT LEVEL BECAUSE THE OPERATOR RULES COHORTS. A
row-level draw would ask him the same question hundreds of times and weight the
answer by cohort size, which is exactly the bias a per-cohort rate is meant to
avoid. Every cohort therefore carries `n_rows`, so Step 6 can report the rate
both ways -- and they will differ, because the largest stratum-A cohort holds
10,745 of its 90,470 rows and the median holds 9.

THE RATER MUST BE ABLE TO PUNT. `UNSURE` is a first-class verdict on the sheet
and in the html select. Forcing a binary is how a false-approve floor gets
manufactured, and this project has measured one: the 2026-08-21 calibration put
15 agents at ~80% agreement with a ~5% false-approve floor. The verdict
vocabulary is the FOUR the agent verdict file already uses -- APPROVE, REJECT,
WRONG_ASSAY, UNSURE -- so a human ruling and an agent verdict pool without a
translation table, and `check_verdict_vocabulary` refuses a verdict file
carrying a fifth rather than dropping it.

WHAT THE SHEET WITHHOLDS, ON PURPOSE, AND WHAT IT CANNOT. Stratum C exists to
ask whether the agent REJECT bucket is sound. A sheet that printed the agent's
verdict and its ARGUMENT beside the cohort would be measuring how often a human
agrees with reasoning they were handed, which is a different and much easier
question. So `verdict`, `confidence` and `reason` live in
`validation-sample-key.csv` and never in the sheet, and
`test_the_sheet_carries_no_agent_verdict` asserts the separation.

THE BLINDING IS PARTIAL AND THE LIMIT IS STATED RATHER THAN PAPERED OVER. The
stratum label is off the sheet, but `classification` is ON it because it is
real evidence a rater needs -- and it recovers the stratum: every
`CLS_UNREACHABLE` cohort here is A, every `CLS_BOOTSTRAP` is B, and because
stratum C is drawn ENTIRELY from agent-REJECT cohorts, a rater who has read
this file can infer that a `CLS_ABSENCE_LINEAGE` cohort on the sheet was
rejected by an agent. Closing that would need a control slice of non-rejected
primary cohorts, which is a bigger sitting than the operator agreed to. What is
protected is the agent's reasoning; what is not is the bare fact of membership.

THE SHEET IS ORDERED BY A SECOND, SEPARATELY SALTED DIGEST so the three strata
interleave. A sheet in stratum blocks would let a rater notice, halfway down,
that the questions have changed shape.

BOTH PRECEDENT GRAINS, AND WHAT THAT PHRASE COULD NOT MEAN HERE. The plan's
Task 6 was to add SAMPLE-grained counts beside the edge-grained ones; it is not
in this tree -- `_schema.PRECEDENT_COLUMNS` still holds only `n_both`,
`n_child_only`, `n_parent_only` and the two rates over them. So the two grains
the sheet can honestly carry are the two DIRECTIONS, `propagation_rate` and
`reverse_rate`, both recomputed here from the row's own three counts rather
than read from `precedent_rate`, which holds only the one direction
`precedent_direction` names. `check_rates_reproduce_the_row` asserts the
recomputation reproduces `precedent_rate` in that direction, so the arithmetic
cannot drift from `precedent.mine_precedent`'s.

WHAT IS EXACT AND WHAT IS THE EXAMPLES'. `type_registrations`, the proposed
assay's population and `id_namespace` are functions of `(sample_type, assay
id)` or of the assay id alone, so they are computed HERE from the package's own
indexes -- `gate.type_registration_index`, `mode2.assay_population`,
`precedent.fallback_assay_ids` -- and then checked against the values the rows
carry. Everything else on the row varies by project within one cohort, so it is
reported over the shown examples with its denominator (`n_examples_shown` of
`n_rows`), following the rule the rest of this package keeps about caps.

THE COHORT KEY IS NEVER RECONSTRUCTED HERE. `review_mode2.build_blocks` is the
one definition, called with `floor=0.0`; a local `lab|type|parents|assay|field|
value` join would be a second one, which is a defect class this package has
already recorded three times. The cost is that `build_blocks` keys on
`precedent_rate >= floor`, which is False on a null, so the 8 `CLS_UNREACHABLE`
rows carrying NO precedent rate reach no cohort and are not on this sheet.
`check_row_accounting` states that as an equation rather than letting it be a
silent shortfall.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import gate as G
from . import mode2 as M2
from . import precedent as P
from . import review as R
from . import review_mode2 as M

# THE SEED. Recorded in the module docstring above, in every output file and in
# the key file, and pinned by `test_the_docstring_records_the_seed`. It is the
# date the sample was designed; nothing about the value is special and
# everything about its being FIXED and PUBLISHED is.
SEED = 20260824

STRATUM_A = "A_unreachable"
STRATUM_B = "B_bootstrap"
STRATUM_C = "C_agent_reject"
STRATA = (STRATUM_A, STRATUM_B, STRATUM_C)

TARGET = {STRATUM_A: 100, STRATUM_B: 50, STRATUM_C: 50}

QUESTION = {
    STRATUM_A: "Is the reachability gate right? The house has never put this "
               "sample type in this assay. Is that its settled answer, or a "
               "gap that should be filled?",
    STRATUM_B: "Did the population floor find a real gap? The assay is barely "
               "used, so its empty cells may be inexperience rather than a "
               "type error.",
    STRATUM_C: "Is the reject sound? This proposal is still on a primary "
               "review surface after the rework.",
}

# The three classes that route a proposal AWAY from the primary review surface.
# Named exactly as `tests/test_assay_hygiene_rulings.py` names them, so the two
# files cannot drift into two opinions about what "still on the surface" means.
#
# `CLS_ALT_LABEL` IS INERT HERE TODAY AND IS LISTED ANYWAY. Measured 2026-08-24
# on the real extract: all 952 alt-label rows carry a null `mode`, so
# `build_blocks` -- which selects `mode == MODE_2` -- returns 0 cohorts for
# them, and removing this member changes stratum C by nothing (verified by
# mutation; the real-extract test stays green). It stays because the tuple's
# job is to state the RULE the sibling test states, not to hold only the
# members that currently bite; a lane that starts emitting a mode would
# otherwise walk onto this sheet silently.
OFF_PRIMARY = (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP, S.CLS_ALT_LABEL)

# The verdict a rater may record, and the ONE that makes the sheet honest.
PUNT = "UNSURE"
VERDICT_OPTIONS = (
    ("", "-- not ruled --"),
    ("APPROVE", "APPROVE -- the pair is right, the house should hold it"),
    ("REJECT", "REJECT -- the pair is wrong, do not register it"),
    ("WRONG_ASSAY", "WRONG ASSAY -- a different assay is the right one"),
    (PUNT, "I CANNOT TELL -- there is not enough here to judge"),
)
VERDICTS = tuple(v for v, _label in VERDICT_OPTIONS if v)

# What the rater fills in. Two fields and not three: the html's export script
# is `review.SCRIPT`, which carries exactly one select and one textarea per
# cohort, and forking it to add a confidence column would fork the localStorage
# and export logic the operator already trusts. The punt carries the
# uncertainty a confidence column would have carried.
FILL_IN = ("verdict", "reason")

CSV_NAME = "validation-sample.csv"
HTML_NAME = "validation-sample.html"
KEY_NAME = "validation-sample-key.csv"
POWER_NAME = "validation-sample-power.md"

# The storage prefix, bumped away from BOTH shipped sheets. `review_mode2`
# records why at length: the sheets share `review.SCRIPT`, so two sheets on one
# prefix share a keyspace and a ruling on one silently overwrites a ruling on
# the other wherever the six-field keys collide -- and stratum C's cohorts are
# Mode 2 cohorts, so a collision here is not hypothetical.
_LS_MODE1 = 'var LS = "mode1-review:";'
_LS_VALIDATION = 'var LS = "validation-sample-v1:";'

# `review.SCRIPT` hard-codes the export header. Substituted rather than
# re-declared, and asserted, for the same reason the prefix is: a rename in
# `review.py` must fail loudly here rather than exporting a column named
# `ruling` out of a sheet whose column is `verdict`.
_HDR_MODE1 = '"ruling","note"'
_HDR_VALIDATION = '"verdict","reason"'

MAX_META_FIELDS = 4


# --- the draw ----------------------------------------------------------------


def _digest(seed: int, salt: str, key: str) -> str:
    """The one place a cohort's hash rank is computed. sha256, hex.

    `salt` separates the two independent orders this module needs -- which
    cohorts are DRAWN, and what order they are PRESENTED in -- so that the
    presentation order carries no information about how close a cohort was to
    missing the cut.
    """
    return hashlib.sha256(
        f"{seed}|{salt}|{key}".encode("utf-8")).hexdigest()


def draw(keys, n: int, seed: int = SEED, salt: str = "draw") -> list[str]:
    """-> the `n` keys whose digest sorts first. A pure function of its inputs.

    RAISES on a duplicate key. A cohort key is a review unit; two of them
    would mean one cohort could be drawn twice and ruled twice, and
    `build_blocks` already refuses to emit a duplicate, so a duplicate reaching
    here means something upstream stopped being the cohort key.

    `n` LARGER THAN THE POPULATION RETURNS THE POPULATION, which is a census
    and is reported as one -- `power` gives a census a zero-event bound of
    exactly 0, because there is nothing left unseen to bound.
    """
    keys = list(keys)
    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})[:3]
        raise ValueError(
            f"{len(keys) - len(set(keys))} duplicate cohort key(s) reached the "
            f"draw, e.g. {dupes}. One cohort is one review unit; a duplicate "
            "would be drawn and ruled twice.")
    ranked = sorted(keys, key=lambda k: (_digest(seed, salt, k), k))
    return ranked[:max(0, int(n))]


# --- the power, stated before anyone rules -----------------------------------


def zero_event_bound(population: int, sample: int, alpha: float = 0.05) -> int:
    """-> the most bad cohorts a 0-event sample leaves consistent, at 1-alpha.

    THE EXACT HYPERGEOMETRIC BOUND AND NOT THE RULE OF THREE. Sampling is
    without replacement from a finite, often small population -- 50 of stratum
    B's 137 cohorts is 36% of it -- and the binomial approximation ignores
    that, so it overstates what a clean sample leaves possible. The answer is
    the largest K with

        P(none of K bad appear) = C(N-K, n) / C(N, n) > alpha

    computed as a running product so no factorial is formed.

    A CENSUS BOUNDS AT ZERO and that is not a degenerate case to guard away:
    when `sample >= population` every cohort was looked at, so a 0-event
    outcome means there are none, exactly. Reporting a positive bound there
    would understate what the sitting achieved.
    """
    population, sample = int(population), int(sample)
    if sample >= population:
        return 0
    if sample <= 0:
        return population
    best = 0
    for k in range(1, population - sample + 1):
        p = 1.0
        for i in range(sample):
            p *= (population - k - i) / (population - i)
        if p > alpha:
            best = k
        else:
            break
    return best


def kish_effective_n(weights) -> float:
    """(sum w)^2 / sum(w^2) -- how many EQUAL cohorts a skewed sample is worth.

    The row-weighted rate is a ratio estimator over cohorts of wildly unequal
    size, and its variance is set by that inequality rather than by the count
    of cohorts. Kish's effective n is the standard way to say so in one number:
    a sample of 100 cohorts one of which holds a third of the rows is worth
    about three equal ones for any row-weighted statement.
    """
    w = [float(x) for x in weights]
    total = sum(w)
    squares = sum(x * x for x in w)
    return (total * total / squares) if squares else 0.0


def power(stratum: str, population_cohorts: int, population_rows: int,
          sampled_rows, alpha: float = 0.05) -> dict:
    """Every figure Step 4 owes the operator, for one stratum.

    IT REPORTS TWO BOUNDS BECAUSE THE SAMPLE SUPPORTS TWO CLAIMS OF VERY
    DIFFERENT STRENGTH, and printing only the flattering one is how a sample
    comes to imply a precision it does not have.

    PER COHORT the draw is uniform and the bound is exact and useful.

    PER ROW it is neither. A cohort-level draw says nothing about the rows in
    cohorts it did not draw, so with zero events the row rate is bounded only
    by the rows NOT covered: `row_bound_worst_case = 1 - covered/population`.
    On a population whose largest cohort is 12% of its rows and whose median
    cohort is 9, that bound is close to 1 and the honest report says so.
    `kish_n_eff` is the second half of the same statement -- what the sample is
    worth for a row-weighted estimate if one is attempted anyway.
    """
    sampled_rows = [int(x) for x in sampled_rows]
    n = len(sampled_rows)
    covered = sum(sampled_rows)
    bound_k = zero_event_bound(population_cohorts, n, alpha)
    return {
        "stratum": stratum,
        "question": QUESTION[stratum],
        "population_cohorts": int(population_cohorts),
        "population_rows": int(population_rows),
        "sampled_cohorts": n,
        "sampled_rows": covered,
        "row_coverage": (covered / population_rows) if population_rows else 0.0,
        "cohort_bound_k": bound_k,
        "cohort_bound_rate": (bound_k / population_cohorts
                              if population_cohorts else 0.0),
        "largest_sampled_cohort": max(sampled_rows) if sampled_rows else 0,
        "kish_n_eff": kish_effective_n(sampled_rows),
        "row_bound_worst_case": (1.0 - covered / population_rows
                                 if population_rows else 1.0),
        "census": n >= population_cohorts,
    }


# --- the populations ---------------------------------------------------------


def check_verdict_vocabulary(verdicts: pd.DataFrame) -> None:
    """The sheet's options must cover every verdict the agent file uses.

    A verdict this sheet cannot render is a verdict Step 6 cannot pool with the
    human rulings, and the failure is silent in the direction that matters: the
    stratum C population would simply be built from a smaller REJECT set, and
    nothing on the sheet would say so.
    """
    unknown = sorted(set(verdicts.verdict.dropna().astype(str)) - set(VERDICTS))
    if unknown:
        raise ValueError(
            f"the verdict file carries {unknown}, which this sheet cannot "
            f"render; VERDICT_OPTIONS is {sorted(VERDICTS)}. A verdict the "
            "sheet cannot render is a verdict the analysis cannot pool.")
    if PUNT not in VERDICTS:
        raise ValueError(
            f"{PUNT!r} is not in VERDICT_OPTIONS. A rater who cannot answer "
            "'I cannot tell' is forced to a yes or a no, which is how a "
            "false-approve floor is manufactured.")


def check_row_accounting(name: str, blocks: list[dict], population: int,
                         unrated: int) -> None:
    """Cohort rows + rows with no precedent rate == the class's rows. Or raise.

    `build_blocks` selects on `precedent_rate >= floor` and that predicate is
    False on a null, so a row carrying no rate silently reaches no cohort. On
    the 2026-08-24 run that is 8 of stratum A's 90,478 and 0 of stratum B's
    8,971. Eight rows is small and a silent shortfall is not, so it is stated
    as an equation that fails rather than as a comment that ages.
    """
    got = sum(int(b["n_rows"]) for b in blocks)
    if got + int(unrated) != int(population):
        raise ValueError(
            f"{name}: {got:,} row(s) in cohorts + {unrated:,} with no "
            f"precedent rate != the {population:,} row(s) in the class. Every "
            "row must be accounted for in exactly one bucket, or this sample "
            "is drawn from a population it cannot describe.")


def strata(findings: pd.DataFrame, verdicts: pd.DataFrame,
           context: dict) -> dict[str, dict]:
    """-> {stratum: {"blocks": [...], "population_rows": int, "unrated": int}}.

    THE THREE POPULATIONS ARE ASSERTED DISJOINT rather than assumed. A and B
    are cuts of one classification column and C is the complement of both, so
    disjointness looks structural -- but the cohort key holds the assay TITLE
    and four titles on this extract resolve to two internal ids each, so one
    key CAN in principle straddle two classes. A cohort in two strata would be
    ruled once and counted twice, in two rates, with two different
    denominators.
    """
    out: dict[str, dict] = {}
    for name, cls in ((STRATUM_A, S.CLS_UNREACHABLE),
                      (STRATUM_B, S.CLS_BOOTSTRAP)):
        rows = findings[findings.classification == cls]
        blocks = M.build_blocks(rows, context, floor=0.0)
        unrated = int(rows.precedent_rate.isna().sum())
        check_row_accounting(name, blocks, len(rows), unrated)
        out[name] = {"blocks": blocks, "population_rows": int(len(rows)),
                     "unrated": unrated}

    primary = findings[(findings["mode"] == S.MODE_2)
                       & (~findings.classification.isin(OFF_PRIMARY))]
    rejected = set(verdicts.loc[verdicts.verdict == "REJECT", "cohort_key"])
    blocks = [b for b in M.build_blocks(primary, context, floor=0.0)
              if R.cohort_key(b) in rejected]
    out[STRATUM_C] = {
        "blocks": blocks,
        "population_rows": sum(int(b["n_rows"]) for b in blocks),
        "unrated": 0,
    }

    seen: dict[str, str] = {}
    for name, part in out.items():
        for block in part["blocks"]:
            key = R.cohort_key(block)
            if key in seen:
                raise ValueError(
                    f"cohort {key!r} is in both {seen[key]} and {name}. One "
                    "cohort would be ruled once and counted in two rates.")
            seen[key] = name
    return out


# --- the per-cohort facts ----------------------------------------------------


def _rates(row) -> tuple[float | None, float | None]:
    """(propagation, reverse) from the row's own three counts.

    `precedent.mine_precedent` defines both: propagation is both / (both +
    child_only) and reverse is both / (both + parent_only), each 0.0 on an
    empty denominator. Recomputed rather than read because the row carries only
    ONE rate and `precedent_direction` says which -- a sheet printing that bare
    number beside a cohort would show the reverse rate on 112,495 of the rows
    and the forward rate on 54,852 with nothing to tell them apart.
    """
    both, child, parent = (row.get("precedent_n_both"),
                           row.get("precedent_n_child_only"),
                           row.get("precedent_n_parent_only"))
    if any(pd.isna(v) for v in (both, child, parent)):
        return None, None
    both, child, parent = float(both), float(child), float(parent)
    fwd, rev = both + child, both + parent
    return (both / fwd if fwd else 0.0), (both / rev if rev else 0.0)


def check_rates_reproduce_the_row(rows: pd.DataFrame) -> None:
    """The recomputed rate in the row's own direction must BE `precedent_rate`.

    Without this the sheet carries two numbers computed here and one computed
    in `precedent.py`, and nothing anywhere says they agree. The tolerance is
    1e-9 because both sides are float divisions of the same two integers.
    """
    for row in rows.to_dict("records"):
        stated = row.get("precedent_rate")
        direction = row.get("precedent_direction")
        if pd.isna(stated) or not isinstance(direction, str):
            continue
        fwd, rev = _rates(row)
        mine = fwd if direction == "propagation_rate" else rev
        if mine is None or abs(mine - float(stated)) > 1e-9:
            raise ValueError(
                f"row {row.get('uuid')} states {direction} "
                f"{float(stated):.6f} and its own counts give {mine}. The two "
                "precedent grains on this sheet do not reproduce the column "
                "the detector wrote.")


def _distinct(values) -> str:
    """Sorted distinct non-null values, `;`-joined. The sheet's one collapse.

    A cohort spans projects, so a row-level column can hold more than one value
    inside it. Printing the first would be a fact about an example presented as
    a fact about the cohort; printing them all is longer and true.
    """
    out = sorted({str(v) for v in values
                  if v is not None and not (isinstance(v, float) and pd.isna(v))
                  and str(v) not in ("", "nan")})
    return ";".join(out)


def _num(value) -> str:
    """An int that survived a csv round trip as a float, printed as an int."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return f"{int(float(value)):,}"


def _example_rows(block: dict, rows: pd.DataFrame) -> pd.DataFrame:
    """The findings rows behind the examples the sheet shows.

    `(sample_id, proposed_internal_assay_title, action)` is unique inside a
    classification on this extract -- verified 2026-08-24, 0 duplicate groups
    over all 90,478 / 8,971 / 67,898 rows of the three classes -- so this is a
    join and not a heuristic. It is scoped to the cohort's own action for the
    same reason `build_blocks` puts the action in the key: ADD_PARENT and
    ADD_CHILD are two different writes against one pair.
    """
    ids = [c["sample_id"] for c in block["children"]]
    hit = rows[(rows.sample_id.isin(ids))
               & (rows.proposed_internal_assay_title == block["assay"])]
    if block["field"] == M.LINEAGE_FIELD:
        hit = hit[hit.action == block["value"]]
    return hit


def cohort_facts(block: dict, rows: pd.DataFrame, *, type_reg: dict,
                 assay_pop: dict, fallback: set[int]) -> dict:
    """One cohort's evidence, exact where it can be and denominated where not.

    THE THREE INDEX-DERIVED FACTS ARE CHECKED AGAINST THE ROWS. Reading
    `type_registrations` off the row would be simpler and would also make this
    sheet unable to notice a detector that wrote the wrong one; computing it
    from `gate.type_registration_index` and then asserting the row agrees makes
    the sheet a second measurement rather than a second rendering. The same
    holds for `id_namespace` against `_schema.id_namespace` over
    `precedent.fallback_assay_ids`. `assay_population` has no column at all --
    the number the bootstrap split turned on appears only inside
    `evidence_summary` -- so this is the first surface to carry it as data.
    """
    hit = _example_rows(block, rows)
    if hit.empty:
        raise ValueError(
            f"cohort {R.cohort_key(block)!r} shows {len(block['children'])} "
            "example(s) and none of them joins back to a findings row. The "
            "sheet would carry a cohort whose evidence cannot be shown.")

    ids = sorted({int(a) for a in hit.proposed_internal_assay_id.dropna()})
    if len(ids) != 1:
        raise ValueError(
            f"cohort {R.cohort_key(block)!r} names assay ids {ids}. The key "
            "holds the assay TITLE and four titles on this extract resolve to "
            "two internal ids, so a cohort spanning two is a cohort whose "
            "population and namespace are two different answers.")
    assay_id = ids[0]

    sample_type = block["sample_type"]
    registrations = int(type_reg.get((sample_type, assay_id), 0))
    stated = sorted({int(v) for v in hit.type_registrations.dropna()})
    if stated != [registrations]:
        raise ValueError(
            f"cohort {R.cohort_key(block)!r}: gate.type_registration_index "
            f"says {sample_type} has {registrations} registration(s) in "
            f"{assay_id} and the rows say {stated}.")

    namespace = S.id_namespace(assay_id, fallback)
    stated_ns = _distinct(hit.id_namespace)
    if stated_ns and stated_ns != namespace:
        raise ValueError(
            f"cohort {R.cohort_key(block)!r}: _schema.id_namespace says "
            f"{namespace} for assay {assay_id} and the rows say {stated_ns}.")

    check_rates_reproduce_the_row(hit)
    grains = [_rates(r) for r in hit.to_dict("records")]
    evidence = [str(e) for e in hit.evidence_summary.dropna()]

    return {
        "proposed_internal_assay_id": assay_id,
        "type_registrations": registrations,
        "assay_population": int(assay_pop.get(assay_id, 0)),
        "id_namespace": namespace,
        "classification": _distinct(hit.classification),
        "gate": _distinct(hit.gate) or "NO_GATE",
        "action": _distinct(hit.action),
        "precedent_supports": _distinct(hit.precedent_supports) or "no rule",
        "precedent_direction": _distinct(hit.precedent_direction),
        "precedent_rate_propagation": _distinct(
            f"{f:.3f}" for f, _r in grains if f is not None),
        "precedent_rate_reverse": _distinct(
            f"{r:.3f}" for _f, r in grains if r is not None),
        "precedent_n_both": _distinct(_num(v) for v in hit.precedent_n_both),
        "precedent_n_child_only": _distinct(
            _num(v) for v in hit.precedent_n_child_only),
        "precedent_n_parent_only": _distinct(
            _num(v) for v in hit.precedent_n_parent_only),
        "lineage_n_supports": _distinct(
            _num(v) for v in hit.lineage_n_supports),
        "n_examples_joined": int(len(hit)),
        "evidence": evidence[0] if evidence else "",
        "n_evidence_variants": len(set(evidence)),
    }


def _metadata_cell(block: dict) -> str:
    """The examples' claim-bearing metadata, flattened for a csv cell.

    Claim fields only, and capped. The html carries every field of every
    example expanded; this is the triage pass, and a cell holding sixty columns
    of a D.IMG sheet is a cell nobody reads.
    """
    parts = []
    for child in block["children"]:
        meta = child["meta"]
        items = (meta["claim"] + meta["rest"])[:MAX_META_FIELDS]
        rendered = ", ".join(f"{k}={v}" for k, v in items) or "(no metadata)"
        parts.append(f'{child["uuid"]}: {rendered}')
    return " || ".join(parts)


# --- the sheet ---------------------------------------------------------------


def build_sample(findings: pd.DataFrame, verdicts: pd.DataFrame,
                 context: dict, *, type_reg: dict, assay_pop: dict,
                 fallback: set[int], seed: int = SEED,
                 target: dict | None = None) -> tuple[list[dict], list[dict]]:
    """-> (the drawn cohorts, in sheet order; the power statement per stratum).

    Each drawn cohort carries its own `block` and `facts` so the csv, the html
    and the key file are three renderings of ONE selection rather than three
    selections that agree today.
    """
    target = dict(TARGET if target is None else target)
    check_verdict_vocabulary(verdicts)
    parts = strata(findings, verdicts, context)

    by_class = {S.CLS_UNREACHABLE: findings[
                    findings.classification == S.CLS_UNREACHABLE],
                S.CLS_BOOTSTRAP: findings[
                    findings.classification == S.CLS_BOOTSTRAP]}
    primary = findings[(findings["mode"] == S.MODE_2)
                       & (~findings.classification.isin(OFF_PRIMARY))]
    source = {STRATUM_A: by_class[S.CLS_UNREACHABLE],
              STRATUM_B: by_class[S.CLS_BOOTSTRAP],
              STRATUM_C: primary}

    drawn: list[dict] = []
    stats: list[dict] = []
    for name in STRATA:
        blocks = {R.cohort_key(b): b for b in parts[name]["blocks"]}
        picked = draw(list(blocks), target[name], seed)
        for key in picked:
            block = blocks[key]
            drawn.append({
                "stratum": name,
                "cohort_key": key,
                "block": block,
                "facts": cohort_facts(block, source[name], type_reg=type_reg,
                                      assay_pop=assay_pop, fallback=fallback),
                "draw_digest": _digest(seed, "draw", key),
            })
        stats.append(power(name, len(blocks), parts[name]["population_rows"],
                           [blocks[k]["n_rows"] for k in picked]))

    drawn.sort(key=lambda d: (_digest(seed, "order", d["cohort_key"]),
                              d["cohort_key"]))
    for i, entry in enumerate(drawn, start=1):
        entry["cohort_id"] = f"V{i:03d}"
    return drawn, stats


def to_csv(drawn: list[dict], seed: int = SEED) -> pd.DataFrame:
    """The sheet the operator reads FIRST. One row per cohort, blind to stratum.

    `seed` rides on every row rather than in a header comment because a csv has
    no header comment a spreadsheet will keep, and a sheet that cannot say
    which draw produced it cannot be re-derived.
    """
    out = []
    for entry in drawn:
        b, f = entry["block"], entry["facts"]
        out.append({
            "cohort_id": entry["cohort_id"],
            "lab": b["lab"], "sample_type": b["sample_type"],
            "parent_types": b["parent_types"], "assay": b["assay"],
            "field": b["field"], "value": b["value"],
            "cohort_key": entry["cohort_key"],
            "n_rows": b["n_rows"], "n_samples": b["n_samples"],
            "n_examples_shown": b["shown"],
            "classification": f["classification"], "gate": f["gate"],
            "action": f["action"],
            "type_registrations": f["type_registrations"],
            "assay_population": f["assay_population"],
            "proposed_internal_assay_id": f["proposed_internal_assay_id"],
            "id_namespace": f["id_namespace"],
            "precedent_supports": f["precedent_supports"],
            "precedent_direction": f["precedent_direction"],
            "precedent_rate_propagation": f["precedent_rate_propagation"],
            "precedent_rate_reverse": f["precedent_rate_reverse"],
            "precedent_n_both": f["precedent_n_both"],
            "precedent_n_child_only": f["precedent_n_child_only"],
            "precedent_n_parent_only": f["precedent_n_parent_only"],
            "lineage_n_supports": f["lineage_n_supports"],
            "neighbour_role": b["children"][0]["neighbour_role"],
            "neighbours_holding_it":
                f'{b["n_corroborated_shown"]}/{b["shown"]}',
            "example_uuids": ";".join(c["uuid"] for c in b["children"]),
            "example_neighbours": ";".join(
                str(c["neighbour_uuid"]) for c in b["children"]),
            "example_neighbour_types": ";".join(
                str(c["neighbour_type"]) for c in b["children"]),
            "example_metadata": _metadata_cell(b),
            "FLAG_analysis_twin": (b["twin_title"] if b["flag_analysis_twin"]
                                   else ""),
            "evidence": f["evidence"],
            "n_evidence_variants": f["n_evidence_variants"],
            "seed": seed,
            "verdict": "",
            "reason": "",
        })
    return pd.DataFrame(out)


def to_key(drawn: list[dict], verdicts: pd.DataFrame,
           seed: int = SEED) -> pd.DataFrame:
    """The stratum assignment and the agent verdict. NOT for the rater.

    This is the half of the sample that would anchor a rater if it sat on the
    sheet, and the half Step 6 cannot compute a stratified rate without. Kept
    in a separate file so that handing over the sheet cannot hand over the
    answer key by accident.
    """
    prior = {row["cohort_key"]: row for row in verdicts.to_dict("records")}
    return pd.DataFrame([{
        "cohort_id": entry["cohort_id"],
        "stratum": entry["stratum"],
        "cohort_key": entry["cohort_key"],
        "n_rows": entry["block"]["n_rows"],
        "n_samples": entry["block"]["n_samples"],
        "agent_verdict": prior.get(entry["cohort_key"], {}).get("verdict", ""),
        "agent_confidence": prior.get(entry["cohort_key"], {}).get(
            "confidence", ""),
        "agent_reason": prior.get(entry["cohort_key"], {}).get("reason", ""),
        "seed": seed,
        "draw_digest": entry["draw_digest"],
    } for entry in drawn])


def power_report(stats: list[dict], seed: int = SEED,
                 alpha: float = 0.05) -> str:
    """Step 4, in the operator's hands BEFORE he rules. Markdown.

    IT LEADS WITH WHAT THE SAMPLE CANNOT DO. The per-cohort bound is the strong
    result and the row-weighted one is close to worthless at these coverages;
    printing them in that order, with the weak one explained rather than
    omitted, is the difference between a power statement and an advertisement.
    """
    conf = f"{(1 - alpha) * 100:.0f}%"
    lines = [
        "# Validation sample -- what it can and cannot bound",
        "",
        f"Seed **{seed}**. A cohort is drawn iff "
        "`sha256(\"<seed>|draw|<cohort key>\")` sorts in the first n of its "
        "stratum; the sheet's order is the same hash with the salt `order`. "
        "No RNG is involved, so the draw can be re-derived in any language "
        "and checked against this file.",
        "",
        "**Nothing here is decided and nothing here writes.** Every cohort is "
        "a proposal awaiting a ruling, and `" + PUNT + "` is a first-class "
        "answer.",
        "",
        "## Per cohort -- the claim this sample supports",
        "",
        "| stratum | cohorts | drawn | if NOTHING is found, the true rate is "
        f"at most ({conf}) |",
        "|---|---|---|---|",
    ]
    for s in stats:
        claim = ("**0 of {n}** -- this is a CENSUS, every cohort was looked at"
                 .format(n=s["population_cohorts"]) if s["census"] else
                 f'{s["cohort_bound_k"]} of {s["population_cohorts"]} cohorts '
                 f'({s["cohort_bound_rate"]:.1%})')
        lines.append(f'| {s["stratum"]} | {s["population_cohorts"]:,} | '
                     f'{s["sampled_cohorts"]:,} | {claim} |')
    lines += [
        "",
        "Exact hypergeometric, one-sided: the largest K for which "
        "`C(N-K,n)/C(N,n) > " f"{alpha}" "`. It is not the rule of three -- "
        "sampling is without replacement from a small population, and the "
        "finite-population correction is worth having when n is a third of N.",
        "",
        "## Per row -- the claim it does NOT support",
        "",
        "| stratum | rows | rows drawn | coverage | biggest drawn cohort | "
        "Kish n_eff | 0-event row bound |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in stats:
        lines.append(
            f'| {s["stratum"]} | {s["population_rows"]:,} | '
            f'{s["sampled_rows"]:,} | {s["row_coverage"]:.1%} | '
            f'{s["largest_sampled_cohort"]:,} | {s["kish_n_eff"]:.1f} | '
            f'<= {s["row_bound_worst_case"]:.1%} |')
    lines += [
        "",
        "**Read the last column as a refusal, not a result.** A cohort-level "
        "draw says nothing whatever about the rows in cohorts it did not "
        "draw, so with zero events the row-weighted rate is bounded only by "
        "the share of rows the sample never covered. At these coverages that "
        "bound is close to 1 and no row-weighted conclusion should be drawn "
        "from a clean sitting.",
        "",
        "**Kish n_eff is what a row-weighted estimate is actually worth.** "
        "`(sum w)^2 / sum(w^2)` over the drawn cohorts' row counts. Where it "
        "is far below the cohort count, one or two large cohorts carry the "
        "estimate and its confidence interval will be far wider than the "
        "cohort count suggests.",
        "",
        "## The questions",
        "",
    ]
    for s in stats:
        lines.append(f'- **{s["stratum"]}** -- {s["question"]}')
    lines.append("")
    return "\n".join(lines)


_CSS_EXTRA = """
.facts{margin:.4rem 0;padding:.35rem .6rem;font-size:.83rem;color:var(--mut);
 line-height:1.8;background:var(--code);border-radius:4px}
.facts b{color:var(--fg)}
.cid{font-family:ui-monospace,monospace;font-size:.8rem;color:var(--mut);
 margin-right:.5rem}
.ev{margin:.4rem 0;font-size:.85rem;line-height:1.6}
.punt{color:var(--warn);font-weight:600}
"""

_CALLOUT = (
    '<div class="callout">'
    "<b>Nothing here is decided and nothing here writes.</b> Every cohort "
    "below is a PROPOSAL the detector made and nobody has ever judged. A "
    "verdict you record is text you export and hand on; no stage in this "
    "package reads it back, and none of it reaches MySQL, Neo4j or the API."
    "<br><br>"
    "<b>&ldquo;I cannot tell&rdquo; is a real answer and you are asked to use "
    "it.</b> This sitting exists to measure how often the detector is wrong. "
    "A guess recorded as a yes or a no does not measure that &mdash; it adds "
    "noise to the measurement in the one direction that is hardest to detect "
    "afterwards. If the evidence on the page is not enough, say "
    f"<span class=\"punt\">{PUNT}</span> and say why in the note."
    "<br><br>"
    "<b>Where a cohort has been judged before, you are not shown that "
    "judgement.</b> Some of these have a prior verdict and an argument behind "
    "it, recorded elsewhere and deliberately kept off this page: showing it "
    "would measure how often you agree with reasoning you were handed, which "
    "is not the question. Judge each cohort on what is printed here."
    "<br><br>"
    "<b>The proposed assay is an INTERNAL id, and that is not a writable "
    "target.</b> Every registration below is rendered <code>seek &rarr; "
    "internal</code>; a membership row keys on the SEEK id and one internal id "
    "spans up to 23 SEEK records."
    "</div>")


def _facts_html(entry: dict) -> str:
    f, b = entry["facts"], entry["block"]
    return (
        '<div class="facts">'
        f'<b>{f["classification"]}</b> &middot; gate {R._e(f["gate"])} '
        f'&middot; {b["n_rows"]:,} row(s), {b["n_samples"]:,} sample(s), '
        f'showing {b["shown"]}<br>'
        f'<b>{R._e(b["sample_type"])} in this assay, anywhere:</b> '
        f'{f["type_registrations"]:,} sample(s) &middot; '
        f'<b>the assay holds</b> {f["assay_population"]:,} sample(s) of any '
        f'type (bootstrap floor {M2.BOOTSTRAP_POPULATION_FLOOR})<br>'
        f'<b>precedent</b> propagation {R._e(f["precedent_rate_propagation"])} '
        f'&middot; reverse {R._e(f["precedent_rate_reverse"])} &middot; '
        f'n_both {R._e(f["precedent_n_both"])}, n_child_only '
        f'{R._e(f["precedent_n_child_only"])}, n_parent_only '
        f'{R._e(f["precedent_n_parent_only"])} &middot; the row reads '
        f'{R._e(f["precedent_direction"])} &middot; ever co-registered: '
        f'{R._e(f["precedent_supports"])}<br>'
        f'<b>proposed assay</b> {f["proposed_internal_assay_id"]} in the '
        f'<code>{R._e(f["id_namespace"])}</code> id space &middot; lineage '
        f'support(s) {R._e(f["lineage_n_supports"])}'
        "</div>")


def _notes_html(entry: dict) -> str:
    options = "".join(
        f'<option value="{R._e(value)}">{R._e(label)}</option>'
        for value, label in VERDICT_OPTIONS)
    return (
        '<div class="notes">'
        f'<label>verdict <select class="dec" '
        f'data-k="{R._e(entry["cohort_key"])}">{options}</select></label>'
        f'<textarea class="note" data-k="{R._e(entry["cohort_key"])}" '
        'rows="2" placeholder="Why. If you cannot tell, what would you need '
        'to see?"></textarea></div>')


def _cohort_html(entry: dict) -> list[str]:
    b, f = entry["block"], entry["facts"]
    out = [
        '<section class="cohort">'
        f'<h3><span class="cid">{entry["cohort_id"]}</span>'
        f'{R._e(b["lab"])} &middot; {R._e(b["sample_type"])} '
        f'<span class="arrow">&larr;</span> parent '
        f'{R._e(b["parent_types"])}</h3>'
        f'<div class="propose">propose <b>{R._e(b["assay"])}</b>'
        f'<span class="ids">from {R._e(b["field"])} = '
        f'&ldquo;{R._clip(b["value"])}&rdquo;</span></div>',
        _facts_html(entry),
        f'<div class="ev"><span class="lbl">THE DETECTOR&rsquo;S OWN SENTENCE, '
        f'FOR {R._e(b["children"][0]["uuid"])}</span> {R._e(f["evidence"])}'
        + ("" if f["n_evidence_variants"] <= 1 else
           f' <span class="ids">The other {f["n_evidence_variants"] - 1} '
           "shown example(s) carry their own sentence, naming their own "
           "lineage neighbour; each is rendered with its pair below.</span>")
        + "</div>",
    ]
    if b["flag_analysis_twin"]:
        out.append(
            '<div class="callout"><b>Check the assay, not just the pair.</b> '
            f'This is an <code>{R._e(b["sample_type"])}</code> sample &mdash; '
            "an ANALYSIS type &mdash; proposed into a MEASUREMENT assay whose "
            f'analysis twin exists: <b>{R._e(b["twin_title"])}</b> '
            f'(internal {b["twin_id"]}).</div>')
    for pair in b["children"]:
        out += M._pair_html(pair)
    out.append(_notes_html(entry))
    out.append("</section>")
    return out


def render(drawn: list[dict], stats: list[dict], seed: int = SEED) -> str:
    """The whole page: one file, no network, both themes. See `review.render`."""
    assert _LS_MODE1 in R.SCRIPT, (
        "review.SCRIPT no longer declares the Mode 1 storage prefix verbatim, "
        "so this module cannot rebind it and this sheet would SHARE a "
        "keyspace with Mode 1 -- and with Mode 2, whose cohorts stratum C is "
        "drawn from. Re-pin it.")
    assert _HDR_MODE1 in R.SCRIPT, (
        "review.SCRIPT no longer declares the export header verbatim, so this "
        "sheet would export a column named `ruling` while its csv calls it "
        "`verdict`. Re-pin it.")
    script = R.SCRIPT.replace(_LS_MODE1, _LS_VALIDATION).replace(
        _HDR_MODE1, _HDR_VALIDATION)

    total = sum(e["block"]["n_rows"] for e in drawn)
    bounds = " &middot; ".join(
        f'{s["sampled_cohorts"]} drawn of {s["population_cohorts"]:,} '
        f'(0 found bounds the rate at {s["cohort_bound_rate"]:.1%})'
        for s in stats)
    parts = []
    for entry in drawn:
        parts += _cohort_html(entry)
    return (f"<title>Validation sample, {len(drawn)} cohorts</title>"
            f"<style>{R.CSS}{M._CSS_EXTRA}{_CSS_EXTRA}</style>"
            f'<h1>Validation sample &mdash; {len(drawn):,} cohort(s), '
            f"{total:,} proposal(s)</h1>"
            f'<p class="lede">A stratified sample of proposals the detector '
            "made and <b>no human has ever judged</b>, drawn at seed "
            f"<b>{seed}</b> by sha256 hash order so it can be re-derived "
            "exactly. Three strata, interleaved on purpose. "
            f"{R._e(bounds)}. Up to {R.MAX_EXAMPLES} examples per cohort.</p>"
            f"{_CALLOUT}{''.join(parts)}{R.BAR}{script}\n")


def main(artifacts="assay-hygiene", extract=None, verdicts=None, out_dir=None,
         seed: int = SEED) -> int:
    """Draw the sample, write the four files, print the power statement.

    `out_dir` DEFAULTS TO `artifacts` AND SHOULD NOT BE LEFT THERE on this
    tree: `assay-hygiene/` is a directory of symlinks into a read-only
    `assay-hygiene-bak/`, so a default-path run fails with Permission denied
    rather than writing through the links and destroying the baseline. That
    friction is deliberate; pass a scratch directory.
    """
    a = Path(artifacts)
    e = Path(extract) if extract else a / "extract"
    v = Path(verdicts) if verdicts else a / "mode2-verdicts-review.csv"
    out = Path(out_dir) if out_dir else a
    out.mkdir(parents=True, exist_ok=True)

    findings = pd.read_csv(a / "findings.csv", low_memory=False)
    verdict_frame = pd.read_csv(v)
    membership = pd.read_parquet(e / "membership.parquet")
    assays = pd.read_parquet(e / "assays.parquet")
    nodes = pd.read_parquet(e / "nodes.parquet")

    context = R.load_context(e)
    context["analysis_twins"] = M.analysis_twins(assays)

    drawn, stats = build_sample(
        findings, verdict_frame, context,
        type_reg=G.type_registration_index(membership, assays, nodes),
        assay_pop=M2.assay_population(membership, assays),
        fallback=P.fallback_assay_ids(assays), seed=seed)

    to_csv(drawn, seed).to_csv(out / CSV_NAME, index=False)
    to_key(drawn, verdict_frame, seed).to_csv(out / KEY_NAME, index=False)
    (out / HTML_NAME).write_text(render(drawn, stats, seed))
    (out / POWER_NAME).write_text(power_report(stats, seed))

    print(f"wrote {out / CSV_NAME} -- the sheet, {len(drawn)} cohort(s)")
    print(f"wrote {out / HTML_NAME} -- the same cohorts, expanded")
    print(f"wrote {out / KEY_NAME} -- stratum and agent verdict. NOT for the "
          "rater: it is the anchor the sheet withholds")
    print(f"wrote {out / POWER_NAME} -- what this sample can and cannot bound")
    print(f"  seed {seed}; a cohort is drawn iff sha256('{seed}|draw|<key>') "
          "sorts in the first n of its stratum")
    for s in stats:
        print(f"  {s['stratum']:16s} {s['sampled_cohorts']:>4} of "
              f"{s['population_cohorts']:>5,} cohort(s), "
              f"{s['sampled_rows']:>7,} of {s['population_rows']:>7,} row(s) "
              f"({s['row_coverage']:.1%}); 0 found bounds the COHORT rate at "
              f"{s['cohort_bound_rate']:.1%}, the ROW rate at only "
              f"{s['row_bound_worst_case']:.1%}")
    print("  the row-weighted bound is a refusal, not a result: a "
          "cohort-level draw cannot speak for rows it never covered")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
