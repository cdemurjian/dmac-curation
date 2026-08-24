"""Task 9: the wired detection run, and the report an operator judges it by.

THE COUNTS IN THE PROSE MUST EQUAL THE COUNTS IN THE CSV, and that is the
requirement this file exists for. Increment 1 shipped a report quoting a table
it had not computed, and the whole branch has since found nine further
instances of the same class -- a figure inherited from a brief, a neighbouring
quantity, or a previous round, published without being re-measured. So the
assertions below are almost never literals. They recompute the number from the
artifact on disk and compare it to the number in the sentence, which means they
stay true when the extract changes and go red when a figure is remembered
rather than derived.

`test_every_bolded_integer_in_the_prose_is_a_number_the_artifacts_actually_hold`
is the general form of that. It collects every bolded integer in the report and
requires each to be a value re-derived from `findings.csv`,
`mode3-disposition.csv` or `vocabulary-defects.csv`. A hard-coded figure that
was true last week fails it without anyone having to predict which sentence
would go stale.

THE PLAN'S OWN FIGURES FOR THE CORRECTION ARE STALE, AND ARE NOT PINNED HERE.
Requirement 3 of the brief asks the report to say "576 absences, 31 vocabulary
defects, 45 alternative labels, 214 unclassified". Measured off the disposition
Task 8 wrote, the real split is 326 lineage / 247 compat / 205 unresolved / 45
alternative labels / 43 gate. Both sum to 866 and only the 45 agrees. Pinning
the brief's four numbers would have put four wrong figures in the one paragraph
whose whole job is to correct a wrong figure, so the correction is asserted
against `disposition_breakdown` instead -- the same function `classify.main`
prints -- and never against the plan.

THE WORLD IS IMPORTED, NOT REBUILT. `_world` is traced sample by sample in
`test_assay_hygiene_classify`, and a second synthetic world here would be a
second definition of the fixture the way `registered` was once a third
definition of registration. This file adds edges to it and nothing else.
"""
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import claims as C  # noqa: E402
from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import lineage as L  # noqa: E402
from assay_hygiene import mode2 as M2  # noqa: E402
from assay_hygiene import run_detect as RD  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402

from test_assay_hygiene_classify import SEEK_OFFSET, _world  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"


# --- helpers -----------------------------------------------------------------


def _line(md: str, needle: str) -> str:
    """The report line(s) mentioning `needle`, joined.

    Asserting against a whole document lets a number satisfy an assertion from
    an unrelated line, which is how a report can carry a stale figure and stay
    green. Every count below is checked against the line meant to carry it.
    """
    hits = [ln for ln in md.splitlines() if needle in ln]
    assert hits, f"no line mentioning {needle!r} in report:\n{md[:4000]}"
    return " ".join(hits)


def _bolded_ints(md: str) -> list[int]:
    """Every `**1,234**` in the report, as ints. Percentages and rates excluded."""
    return [int(m.replace(",", ""))
            for m in re.findall(r"\*\*([\d,]+)\*\*", md)]


def unreachable_edge(w):
    """One edge over the imported world that emits a `CLS_UNREACHABLE` row.

    THE WORLD'S OWN REACHABILITY CELLS ARE WHAT MAKE IT ONE. 104 is DNA and
    registered nowhere; 6 is TIS and registered in assay 12; NO DNA SAMPLE IN
    THIS WORLD IS REGISTERED ANYWHERE, so `gate.type_registration_index` holds
    0 for (DNA, 12) and the pair the lineage lane offers is one no sample of
    the type has ever held.

    IT MUST BE AN ASSAY 104 DOES NOT CLAIM, which is why the parent is 6 and
    not one of the assay-11 samples. 104's own claim names 11, that claim is
    `GATE_UNREACHABLE`, and a blocked claim is taken by `PRE_GATE` four steps
    before `PRE_UNREACHABLE` is reached -- so an edge to an assay-11 parent
    would produce a gate refusal and no row at all. The real extract shows the
    same fact from the other side: 0 of its 99,449 unreachable keys carry a
    claim.

    THE UUIDS ARE THE NODES' OWN, taken off the world rather than spelled here,
    and that is load-bearing rather than tidy. `mode2.mode2_findings` reads the
    sample's type as `types.get(uuid_of.get(sample_id))` -- uuid first -- and a
    uuid absent from `nodes` yields no type, and so `type_registrations = None`
    rather than 0, and so `CLS_ABSENCE_LINEAGE` rather than `CLS_UNREACHABLE`.
    Written with an invented uuid this edge produced a lineage row and the
    guard below went green against a world that could not exercise it.
    """
    uuid = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    stype = dict(zip(w["nodes"].sample_id.astype(int), w["nodes"].type))
    return (104, 6, uuid[104], uuid[6], stype[104], stype[6], None, None, None)


def bootstrap_edge(w):
    """One edge over the imported world that emits a `CLS_BOOTSTRAP` row.

    THE SIBLING OF `unreachable_edge`, AND THE ONLY DIFFERENCE IS THE ASSAY'S
    OWN SIZE. 104 is DNA and registered nowhere; 9 is TIS and registered in
    assay 13, which holds TWO samples in the whole world -- 9 and 10 -- so the
    pair the lineage lane offers is one no DNA sample has ever held UNDER AN
    ASSAY THE HOUSE HAS BARELY USED. That is `mode2._bootstrap_evidence`'s
    second question, and 2 is under `mode2.BOOTSTRAP_POPULATION_FLOOR`.

    IT MUST BE AN ASSAY 104 DOES NOT CLAIM, for the reason `unreachable_edge`
    gives: 104's own claim names 11, that claim is `GATE_UNREACHABLE`, and
    `PRE_GATE` would take the key four steps before `PRE_UNREACHABLE`. Assay 13
    is named by `Type: zeta`, which 104 does not carry.
    """
    uuid = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    stype = dict(zip(w["nodes"].sample_id.astype(int), w["nodes"].type))
    return (104, 9, uuid[104], uuid[9], stype[104], stype[9], None, None, None)


def both_reachability_classes(w):
    """Both edges, so one world carries `CLS_UNREACHABLE` AND `CLS_BOOTSTRAP`.

    USE IT WITH `over_the_floor`, WHICH IS WHAT MAKES THE FIRST ONE THE FIRST
    ONE. Without the bulk registrations assay 12 holds four samples, so
    `unreachable_edge`'s row is `CLS_BOOTSTRAP` too and the pair collapses into
    one class.
    """
    return [unreachable_edge(w), bootstrap_edge(w)]


# The bulk registration that lifts ONE assay over the floor, and the world it
# is added to has none of its own: every assay in a 30-sample world holds a
# handful, so a report-layer world without this can emit `CLS_BOOTSTRAP` and
# NEVER `CLS_UNREACHABLE`.
#
# THAT GAP WAS NOT ACADEMIC AND IT IS WHY THIS EXISTS. Review round 1 mutated
# `build_report` to drop `CLS_UNREACHABLE` from the term it sums for
# `lineage_derived` and the WHOLE SUITE STAYED GREEN at 1253/12, while the
# real-extract report printed "Mode 2 emitted 76,869 rows a lineage neighbour
# raised ... so 95,469 of the ceiling reached no finding. That difference is
# exactly the rows the vocabulary gate refused plus the rows Mode 1 claimed
# first" -- against a run printing 4,242 and 749. That is the identical false
# arithmetic identity Task 3b existed to remove, shipped past the test written
# to catch it, because the test's counterfactual was a constant zero.
#
# A NEW TYPE AND A NEW ID RANGE, so nothing the base world counts moves. `BLD`
# appears in no cell, no claim and no vocabulary row, and 2001-2100 collide
# with no sample id in `_world`. The uuids follow the world's own
# `<TYPE>-<YYMMDD><LAB>-<serial>` shape, because `assay_hygiene.review` parses
# the lab and the date out of a uuid and REFUSES one it cannot parse.
BULK_TYPE = "BLD"
BULK_ASSAY = 12
BULK_IDS = range(2001, 2101)


def over_the_floor(w):
    """`BULK_IDS` samples registered in `BULK_ASSAY`. -> (nodes, samples, membership).

    Lifts assay 12 from 4 registered samples to 104, over
    `mode2.BOOTSTRAP_POPULATION_FLOOR`, so `unreachable_edge`'s pair reads
    `CLS_UNREACHABLE` -- the house HAS used this assay and has never put a DNA
    in it -- while `bootstrap_edge`'s assay 13 stays at 2 and reads
    `CLS_BOOTSTRAP`.

    THEY ARE REGISTERED, EDGELESS AND CLAIMLESS ON PURPOSE. Registered keeps
    them out of Mode 1's population, edgeless keeps them out of Mode 2's
    ceiling, and `{}` metadata keeps them out of the claims frame -- so they
    move the assay's POPULATION and nothing else that any assertion here reads.
    They carry a `samples` row as well as a `nodes` row, or
    `registered_samples_absent_from_samples` would count all 100 of them.
    """
    nodes, samples, membership = [], [], []
    for sid in BULK_IDS:
        uuid = f"{BULK_TYPE}-2401{sid % 28 + 1:02d}ENG-{sid}"
        nodes.append((uuid, sid, BULK_TYPE))
        samples.append((sid, uuid, "{}", None, "3"))
        membership.append((sid, BULK_ASSAY + SEEK_OFFSET))
    return nodes, samples, membership


def _run(tmp_path, extra_edges=None, extra_registrations=None):
    """A full `main` over the imported world -> (out_dir, report text).

    The two edges are the ones `test_main_writes_exactly_two_artifacts_...`
    adds for the same reason: Mode 1's world carries none of its own, so
    without them Mode 2 emits nothing and every ceiling assertion below would
    be vacuously true against zero.

    `extra_edges` is a callable over the world, so a caller can add a
    population the base world has none of -- see `unreachable_edge` -- without
    forking the world and without spelling a uuid the world derives. It may
    return one edge or a list of them. The default adds nothing, so every
    existing caller runs the same two edges it always did.

    `extra_registrations` is the same idea one frame over, and it runs FIRST so
    an edge builder reads a world the registrations are already in. It returns
    `(nodes, samples, membership)` row lists -- see `over_the_floor`, which is
    what puts an assay over `mode2.BOOTSTRAP_POPULATION_FLOOR` in a world whose
    assays otherwise hold a handful each.
    """
    w = _world()
    if extra_registrations is not None:
        nodes, samples, membership = extra_registrations(w)
        for name, rows, cols in (("nodes", nodes, S.NODES_COLUMNS),
                                 ("samples", samples, S.SAMPLE_COLUMNS),
                                 ("membership", membership,
                                  S.MEMBERSHIP_COLUMNS)):
            w[name] = pd.concat(
                [w[name], pd.DataFrame(rows, columns=cols)], ignore_index=True)
    extra = [] if extra_edges is None else extra_edges(w)
    # one edge or a list of them: the first element of a bare edge tuple is a
    # sample id, and of a list of edges is an edge
    if extra and not isinstance(extra[0], (list, tuple)):
        extra = [extra]
    w["edges"] = pd.DataFrame(
        [(100, 102, "TIS-100", "TIS-102", "TIS", "TIS", None, None, None),
         (100, 101, "TIS-100", "TIS-101", "TIS", "TIS", None, None, None)]
        + list(extra),
        columns=S.EDGE_COLUMNS,
    )
    extract, out = tmp_path / "extract", tmp_path / "out"
    extract.mkdir(), out.mkdir()
    for name in ("samples", "membership", "assays", "nodes", "edges"):
        w[name].to_parquet(extract / f"{name}.parquet", index=False)
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    C.sample_claims(meta, uuids, w["vocabulary"]).to_parquet(
        out / "claims.parquet", index=False)
    V.save_vocabulary(w["vocabulary"], out / "vocabulary.csv")

    assert RD.main(str(extract), str(out)) == 0
    return out, (out / RD.REPORT_NAME).read_text()


# --- the artifacts -----------------------------------------------------------


def test_main_writes_exactly_the_declared_artifacts_and_no_input_byte_changes(
        tmp_path):
    """`ARTIFACTS` names them. This asserts the DIRECTORY, not the tuple.

    Hashed before and after and diffed, rather than checked for four names:
    "it wrote exactly these" is a claim about the tree, and the half that
    matters most is that `claims.parquet`, `vocabulary.csv` and every parquet
    in the extract are byte-identical afterwards. This run reads an extract a
    production writer also reads.
    """
    w = _world()
    w["edges"] = pd.DataFrame(
        [(100, 102, "TIS-100", "TIS-102", "TIS", "TIS", None, None, None),
         (100, 101, "TIS-100", "TIS-101", "TIS", "TIS", None, None, None)],
        columns=S.EDGE_COLUMNS,
    )
    extract, out = tmp_path / "extract", tmp_path / "out"
    extract.mkdir(), out.mkdir()
    for name in ("samples", "membership", "assays", "nodes", "edges"):
        w[name].to_parquet(extract / f"{name}.parquet", index=False)
    meta = V.parse_metadata(w["samples"])
    uuids = dict(zip(w["samples"].sample_id.astype(int), w["samples"].uuid))
    C.sample_claims(meta, uuids, w["vocabulary"]).to_parquet(
        out / "claims.parquet", index=False)
    V.save_vocabulary(w["vocabulary"], out / "vocabulary.csv")

    def _digests():
        return {p.relative_to(tmp_path).as_posix():
                hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(tmp_path.rglob("*")) if p.is_file()}

    before = _digests()
    assert RD.main(str(extract), str(out)) == 0
    after = _digests()

    assert set(after) - set(before) == {f"out/{n}" for n in RD.ARTIFACTS}
    assert {k: v for k, v in after.items() if k in before} == before


def test_the_report_names_every_artifact_this_run_writes(tmp_path):
    """A reader must be able to find the rows the prose summarises.

    Asserted against `ARTIFACTS` rather than against four literals, so adding
    a fifth output and forgetting to mention it is what fails.
    """
    _, md = _run(tmp_path)
    for name in RD.ARTIFACTS:
        assert name in md, f"the report never names {name}"


# --- the two claims that are not counts --------------------------------------


def test_the_no_write_claim_is_made_and_is_scoped_to_this_run_not_the_package(
        tmp_path):
    """Requirement 1, both halves, and the scope is the load-bearing one.

    `scripts/assay_hygiene/` DOES contain a write path: `stage0_apply.py`
    carries `MERGE`/`DELETE` Cypher and `driver_stage0.py` runs it on the box.
    A package-scope "there is no write path in this code" would be false, and a
    reader who found that file afterwards would be right to distrust the rest
    of the report. So the claim must name THIS RUN, and it must say the write
    path exists elsewhere rather than leaving the reader to discover it.
    """
    _, md = _run(tmp_path)
    low = md.lower()
    assert "writes nothing" in low or "nothing was written" in low
    # the three destinations, so "nothing" is not left abstract
    assert "mysql" in low and "neo4j" in low and "api" in low
    # ...and the scope, stated rather than implied
    assert "stage0_apply" in md, (
        "the no-write claim must name the write path it is NOT making, or it "
        "reads as a claim about the package and is false")
    # per mode, not only once at the top
    for mode in (S.MODE_1, S.MODE_2, S.MODE_3):
        section = _section(md, mode)
        assert re.search(r"writes nothing|nothing was written|no row .* written",
                         section.lower()), (
            f"the {mode} section makes no no-write claim; a reader who skims "
            "one section must still meet it")


def test_nothing_is_decided_and_the_claim_is_made_for_all_three_modes(tmp_path):
    """Requirement 2. Every row is a proposal awaiting operator approval.

    There is no APPROVE column, no workbook and no adjudication in this
    increment, so a report that merely lists rows invites them to be read as
    conclusions. Asserted per mode for the same reason as the no-write claim.
    """
    _, md = _run(tmp_path)
    low = md.lower()

    # THE LEAD'S OWN SENTENCE IS PINNED, not merely the word "proposal".
    # Mutation N3 deleted "**Nothing here is decided.**" from the lead and this
    # test SURVIVED IT: the mode sections each say "a proposal awaiting
    # operator approval", so a bare `"proposal" in md` was satisfied by text
    # that was never at issue. The requirement is that the claim is MADE, and
    # a claim has to be looked for where it is supposed to be.
    assert "nothing here is decided" in low, (
        "the report never states that nothing is decided; the per-mode wording "
        "below does not carry that claim for the document")
    heads = [ln for ln in md.splitlines()
             if ln.startswith("#")
             and any(m in ln for m in (S.MODE_1, S.MODE_2, S.MODE_3))]
    assert heads, "the report has no mode headings"
    assert "nothing here is decided" in md[:md.index(heads[0])].lower(), (
        "the no-decision claim is somewhere after the first mode section; a "
        "reader meets the findings before the caveat")

    assert "await" in low or "approval" in low
    for mode in (S.MODE_1, S.MODE_2, S.MODE_3):
        section = _section(md, mode).lower()
        assert "proposal" in section or "proposes nothing" in section or \
            "no detector" in section, (
            f"the {mode} section does not say its rows are proposals")


def _section(md: str, heading_contains: str) -> str:
    """The report text from the heading naming `heading_contains` to the next."""
    lines = md.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("#") and heading_contains in ln:
            start = i
            break
    assert start is not None, f"no heading mentioning {heading_contains!r}"
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if ln.startswith("#"):
            if len(ln) - len(ln.lstrip("#")) <= level:
                return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


# --- the correction ----------------------------------------------------------


def test_the_report_leads_with_the_correction_and_takes_its_split_from_the_csv(
        tmp_path):
    """Requirement 3, asserted against the disposition and NEVER the plan.

    Increment 1 told the operator there were 866 contradictions. The report has
    to say plainly that measurement found none, and it has to lead with that
    rather than bury it: a reader who reviewed the 866 is the reader this
    document is for.

    THE SPLIT IS RE-DERIVED, for the reason in the module docstring: the plan's
    576/31/45/214 is stale against Task 8's measurement and only one of its
    four figures survives. `disposition_breakdown` is the same function
    `classify.main` prints, so the report and the console cannot diverge.
    """
    out, md = _run(tmp_path)
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    split = X.disposition_breakdown(disposition)

    # LEADS with it: the correction appears before the first mode HEADING.
    # Anchored on the heading and not on the first occurrence of the token,
    # so the lead paragraph is free to say "Mode 3" in prose -- which it must,
    # since the correction is about Mode 3 -- without moving its own anchor.
    heads = [ln for ln in md.splitlines()
             if ln.startswith("#")
             and any(m in ln for m in (S.MODE_1, S.MODE_2, S.MODE_3))]
    assert heads, "the report has no mode headings"
    head = md[:md.index(heads[0])].lower()
    assert "contradiction" in head, (
        "the correction is not in the report's lead; a reader who reviewed "
        "the 866 must meet it before any mode")

    # and the split is the measured one, bucket by bucket
    for bucket, n in split.items():
        label = "no bucket" if pd.isna(bucket) else str(bucket)
        assert f"{n:,}" in md, (
            f"the {label} bucket's count {n:,} is in the disposition but not "
            "in the report")
    assert f"{len(disposition):,}" in md

    # THE FIXTURE CANNOT DISCRIMINATE THIS ON ITS OWN, so a second world is
    # built here. `_world` raises exactly ONE Mode 3 flag, so its breakdown has
    # a single bucket and truncating the loop to `[:1]` -- mutation N6 -- is a
    # no-op against it: the test above passed on a report publishing one row of
    # a five-row table. That is the self-certifying shape increment 1 shipped
    # five of, and the fix is a world where the buckets differ, not a stronger
    # sentence about the one that does not.
    #
    # THREE BUCKETS, THREE DISTINCT AND DISTINCTIVE COUNTS. Two buckets holding
    # the same value cannot discriminate a rule that confuses them, and small
    # integers collide with unrelated counts elsewhere in the document.
    synthetic = pd.DataFrame({
        "precedence_step": ([X.PRE_LINEAGE] * 71 + [X.PRE_GATE] * 53
                            + [X.PRE_COMPAT] * 37),
        "classification": ([None] * 71 + [None] * 53
                           + [S.CLS_ABSENCE_COMPAT] * 37),
        "raw_value": ["Illumina Library"] * 161,
    })
    md2 = RD.build_report(
        pd.read_csv(out / "findings.csv", low_memory=False), synthetic,
        pd.read_csv(out / "vocabulary-defects.csv"),
        ceiling=RD._ceiling_from(out.parent / "extract"),
        integrity=dict.fromkeys(L.INTEGRITY_KEYS, 0), out_dir=str(out))
    for n in (71, 53, 37, 161):
        assert str(n) in md2, (
            f"the correction drops the bucket of {n}; every bucket of the "
            "breakdown must reach the operator, not just the largest")


def test_mode_1s_headline_never_ships_without_its_tier_and_contested_split(
        tmp_path):
    """Task 5's carry, which Task 9 shipped without and the final review caught.

    Measured on the real extract: of MODE_1's 2,166 proposals, 1,591 are
    CONTESTED and 1,576 are tier `weak`. An unqualified "2,166 Mode 1
    proposals" states a number three quarters of whose support is a weak field
    the sample contradicts elsewhere, and the review that measured it recorded
    "Report must qualify it" as a carry. The first version of this report
    published the bare count.

    The qualification is asserted as a RELATIONSHIP, not as literals: every
    tier the frame carries appears with its own count, and the contested count
    is the one the frame holds. A future extract changes all four numbers and
    none of these assertions.
    """
    out, md = _run(tmp_path)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    m1 = findings[findings["mode"] == S.MODE_1]
    assert len(m1), "the fixture emitted no MODE_1 rows to qualify"

    section = _section(md, S.MODE_1)
    contested = int(RD._truthy(m1.contested).sum())
    assert f"{contested:,}" in section and "CONTESTED" in section, (
        "the contested count is missing from the MODE_1 section")
    for tier, n in m1.claim_tier.value_counts(dropna=False).items():
        assert f"`{tier}`" in section, f"tier {tier} is not named"
        assert f"{int(n):,}" in section, f"tier {tier}'s count is missing"

    # ...and the qualification is ABOVE the prose, not a footnote below it
    head = section.split("A sample registered in NO assay")[0]
    assert "CONTESTED" in head, (
        "the tier split is below the descriptive prose; a reader takes the "
        "headline count and stops")


def test_mode_3_is_reported_as_undetected_and_never_as_small(tmp_path):
    """Requirement 4. Undetected and small are different findings.

    Mode 3 emits zero rows because no detector exists, not because measurement
    found few contradictions. A report calling the zero "small" would tell an
    operator the problem had been looked for and found rare, which is the
    opposite of true and is exactly the reading increment 1's 866 invited.
    """
    _, md = _run(tmp_path)
    section = _section(md, S.MODE_3)
    low = section.lower()
    assert "no detector" in low, (
        "the Mode 3 section must say a detector does not exist")
    for word in ("small", "rare", "few", "negligible"):
        assert word not in low, (
            f"the Mode 3 section calls its zero {word!r}; undetected and "
            "small are different findings and only one of them is true")


# --- the ceiling -------------------------------------------------------------


def test_every_mode_2_ceiling_figure_is_labelled_a_ceiling(tmp_path):
    """Requirement 5, first half, enforced at EVERY appearance.

    Two published readings of this number disagreed on this branch and a
    ceiling quoted as an expected output is wrong by more than an order of
    magnitude in the weak direction. The word is not decoration.

    THE CEILING IS INJECTED AS SEVEN DISTINCT SENTINELS, and that is what makes
    this test sound. The first version scanned the report for the REAL ceiling
    values and demanded the word on every line carrying one -- and went red on
    the fixture, where the ceiling is 2 and so are the emitted rows, the
    lineage rows and the digit in the title. It was flagging a collision, not a
    defect. Sentinel values no real count can equal remove the coincidence, so
    what is asserted is where these figures appear rather than which lines
    happen to contain a `2`.
    """
    out, _ = _run(tmp_path)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    defects = pd.read_csv(out / "vocabulary-defects.csv")
    ceiling = {k: 900001 + i for i, k in enumerate(L.CEILING_KEYS)}

    md = RD.build_report(findings, disposition, defects, ceiling=ceiling,
                         integrity=dict.fromkeys(L.INTEGRITY_KEYS, 0),
                         out_dir=str(out))
    section = _section(md, "CEILING")
    assert "ceiling" in section.splitlines()[0].lower()

    for key, n in ceiling.items():
        assert f"{n:,}" in section, f"{key} is not published in the section"
        outside = md.replace(section, "")
        assert f"{n:,}" not in outside, (
            f"{key} is published at {f'{n:,}'} OUTSIDE the section whose "
            "heading calls it a ceiling; that is an unlabelled appearance")

    # the table's own column headers carry the word, so a reader scanning the
    # table rather than the prose still meets it
    header = [ln for ln in section.splitlines() if ln.startswith("| direction")]
    assert header and header[0].lower().count("ceiling") >= 2, header


def test_the_two_directions_are_split_and_carry_a_survival_rate(tmp_path):
    """Requirement 5, second half. ADD_PARENT and ADD_CHILD are never pooled.

    They recover identically at equal precedent rate (0.997 vs 0.998 at
    >= 0.95) and differ five-fold in the bulk band, which is the whole reason
    the demotion survives. One pooled number hides that.
    """
    out, md = _run(tmp_path)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    assert "ADD_PARENT" in md and "ADD_CHILD" in md

    lineage = findings[findings.classification == S.CLS_ABSENCE_LINEAGE]
    survival = M2.precedent_survival(lineage)
    assert len(survival), "the fixture emitted no lineage rows to survive"

    # EVERY ROW OF THE CURVE IS IN THE REPORT, keyed on (threshold, action)
    # together. Asserting the pair as a table-row prefix is what makes the
    # split structural: a report that summed the directions could not produce
    # a row naming one of them, and no unrelated line can satisfy this by
    # coincidence the way a bare integer can.
    for r in survival.itertuples(index=False):
        assert f"| {r.threshold} | {r.action} |" in md, (
            f"the curve carries ({r.threshold}, {r.action}) and the report "
            "does not; the two directions must never be pooled")

    # ...and the threshold is explicitly not a permission
    assert "no threshold is chosen" in md.lower()


# --- every row is named ------------------------------------------------------


def _table_counts(section: str) -> dict[str, int]:
    """`| label | **N** | ...` rows of a markdown table -> {label: N}.

    The label's backticks are stripped so the table may quote a class token
    without the test having to know that it does.
    """
    out = {}
    for ln in section.splitlines():
        m = re.match(r"^\|\s*`?([^|`]+?)`?\s*\|\s*\*\*([\d,]+)\*\*\s*\|", ln)
        if m:
            out[m.group(1).strip()] = int(m.group(2).replace(",", ""))
    return out


def _bullet_counts(section: str) -> dict[str, int]:
    """`- **N** `LABEL` -- ...` bullets -> {label: N}."""
    out = {}
    for ln in section.splitlines():
        m = re.match(r"^\s*-\s+\*\*([\d,]+)\*\*\s+`([^`]+)`", ln)
        if m:
            out[m.group(2)] = int(m.group(1).replace(",", ""))
    return out


def _old_rule_coverage(present: pd.Series) -> int:
    """The rows the FOUR pre-2026-08-21 classes plus the null bucket cover.

    The wrong rule, computed by hand, so the tests below assert a DIFFERENCE
    and not merely a number. `CLS_UNREACHABLE` and `CLS_BOOTSTRAP` are
    deliberately not in this tuple: they are the classes the report stopped
    accounting for, and a test that read the class list off `_schema.CLASSES`
    would silently start passing the moment the schema changed, which is the
    failure mode it is guarding. The tuple is FROZEN AT FOUR for that reason --
    it names a historical rule, so it does not grow when the vocabulary does.
    """
    four = (S.CLS_ABSENCE_LINEAGE, S.CLS_ABSENCE_COMPAT, S.CLS_ALT_LABEL,
            S.CLS_UNRESOLVED)
    null = sum(int(n) for cls, n in present.items() if pd.isna(cls))
    return sum(int(present.get(c, 0)) for c in four) + null


def _unaccounted(present: pd.Series) -> int:
    """The rows the four-class rule omits: both reachability classes.

    `CLS_BOOTSTRAP` is a cut through `CLS_UNREACHABLE` and which of the two a
    row gets turns on how heavily the proposed assay is used, so a world whose
    assays all hold a handful emits only the second. That is what the base
    world does and it is why `over_the_floor` exists: a counterfactual naming
    one of the two is a CONSTANT ZERO in such a world, which is how review
    round 1 slipped a report mutation past this file. Both classes are the
    population the pre-2026-08-21 report had no term for.
    """
    return sum(int(present.get(c, 0))
               for c in (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP))


def _both_classes_live(present: pd.Series) -> None:
    """Refuse a world where either reachability class is absent.

    THE GUARD THE ROUND-1 REVIEW SHOWED WAS MISSING. Every counterfactual below
    that names ONE of the two classes is vacuous when that class has no rows,
    and it fails open: `present.get(...)` returns 0 and the inequality against
    a nonzero sibling still holds. So the world is checked rather than the
    arithmetic being trusted, and it is checked in the one place all four
    report closures share.
    """
    for cls in (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP):
        assert int(present.get(cls, 0)), (
            f"this world emitted no {cls} row. Every one-sided counterfactual "
            "below is then a constant zero that still satisfies its own "
            "inequality; run with `extra_registrations=over_the_floor`")


def test_the_reports_class_census_accounts_for_every_finding(tmp_path):
    """THE REPORT'S OWN PER-CLASS COUNTS MUST SUM TO ITS OWN STATED TOTAL.

    This is not "the report mentions `CLS_UNREACHABLE`". Task 3 added a fifth
    classification carrying, on the 2026-08-21 real extract, 99,449 of 170,786
    rows, and every sentence in this report that had grouped on four classes
    went short by that whole population WITHOUT LOOKING WRONG: the MODE_2 line
    still stated a plausible total beside two plausible terms that did not sum
    to it. A curator reading the page met 71,337 rows named and 99,449 not.

    So what is asserted is a CLOSURE property over the rendered document. Every
    row of `findings.csv` must be inside some named term of the report's own
    census, and the census's rows must sum to the total the census itself
    states. A SIXTH class breaks this test without anyone having to predict it:
    if the report ever groups on a fixed list again, the sum falls short by the
    population of whatever the list omits.

    THE WRONG RULE IS SIMULATED BY HAND and asserted to differ. Over this world
    the four-class rule is short by exactly the unreachable population -- the
    same relationship the real extract shows -- so the test discriminates the
    two rules rather than merely recomputing the right one.
    """
    out, md = _run(tmp_path, extra_edges=both_reachability_classes,
                   extra_registrations=over_the_floor)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    present = findings.classification.value_counts(dropna=False)
    _both_classes_live(present)
    n_unreachable = _unaccounted(present)

    # the wrong rule, by hand: short, and short by exactly the new classes
    wrong = _old_rule_coverage(present)
    assert wrong != len(findings), (
        "the four pre-2026-08-21 classes already cover every row, so this "
        "world cannot tell the two rules apart")
    assert len(findings) - wrong == n_unreachable

    # ...and the right answer, read back off the document the operator reads
    section = _section(md, RD.CENSUS_HEADING)
    counted = _table_counts(section)
    assert counted, f"the census section publishes no table:\n{section}"
    assert sum(counted.values()) == len(findings), (
        f"the census names {sum(counted.values()):,} rows and `findings.csv` "
        f"holds {len(findings):,}; {len(findings) - sum(counted.values()):,} "
        "row(s) are in no term on the page")
    assert f"**{len(findings):,}**" in section, (
        "the census never states the total its own rows are supposed to sum to")

    # every class the FRAME carries is named with the count the frame holds
    for cls, n in present.items():
        label = RD.NO_CLASS if pd.isna(cls) else str(cls)
        assert counted.get(label) == int(n), (
            f"the census gives {label} {counted.get(label)!r} where the frame "
            f"holds {int(n)}")
    # ...and every class the VOCABULARY carries is named even at zero, because a
    # class printed only when nonzero reads exactly like one never measured
    for cls in S.CLASSES:
        assert cls in counted, f"{cls} is absent from the census entirely"


def test_the_mode_2_breakdown_sums_to_the_proposal_total_it_states(tmp_path):
    """The site the shortfall shipped on: `- proposals: N -- a and b`.

    Before this task that line read "**167,454** proposals -- **67,898**
    corroborated by a lineage neighbour and **107** by co-registration alone".
    68,005 against a stated 167,454, with no term for the difference. The two
    terms were also taken off the WHOLE frame rather than off MODE_2's own
    rows, so they were a subdivision of a population they had not been measured
    over.

    Both are asserted here: the breakdown is measured on MODE_2's rows, and its
    terms sum to the total the same line states.
    """
    out, md = _run(tmp_path, extra_edges=both_reachability_classes,
                   extra_registrations=over_the_floor)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    m2 = findings[findings["mode"] == S.MODE_2]
    present = m2.classification.value_counts(dropna=False)
    _both_classes_live(present)
    n_unreachable = _unaccounted(present)
    # the wrong rule, by hand, at this site
    assert len(m2) - _old_rule_coverage(present) == n_unreachable

    # THE PREAMBLE ONLY. `_section` stops at the next heading of the SAME level
    # or higher, so the `## MODE_2` section swallows the `###` ceiling and
    # survival subsections and their figures, which are not terms of this
    # total. The rule below is about the headline and its own breakdown.
    head = _section(md, S.MODE_2).split("\n###")[0]
    figures = _bolded_ints(head)
    assert figures, f"the MODE_2 section states no proposal count:\n{head}"
    total, terms = figures[0], figures[1:]
    assert total == len(m2), (
        f"the MODE_2 headline states {total:,} proposals and the frame holds "
        f"{len(m2):,}")
    assert sum(terms) == total, (
        f"the MODE_2 headline states {total:,} proposals and breaks them into "
        f"terms summing to {sum(terms):,}, short by {total - sum(terms):,}; "
        f"MODE_2 carries {n_unreachable:,} {S.CLS_UNREACHABLE} row(s)")

    # ...and each term is ATTRIBUTED to the class it counts, so a reader can
    # tell which population the shortfall would have been in
    named = _bullet_counts(head)
    for cls, n in present.items():
        label = RD.NO_CLASS if pd.isna(cls) else str(cls)
        assert named.get(label) == int(n), (
            f"MODE_2 carries {int(n)} {label} row(s) and the breakdown says "
            f"{named.get(label)!r}")


def test_the_ceiling_gap_paragraph_counts_every_row_the_lineage_lane_raised(tmp_path):
    """The other site the shortfall can ship on, and it is arithmetic.

    "The union above is N rows; Mode 2 emitted M rows a lineage neighbour
    raised ... so N-M of the ceiling reached no finding. That difference is
    exactly the rows the gate refused plus the rows Mode 1 claimed first." That
    sentence is only true if M counts EVERY row the lineage lane produced, and
    the lane produces one class per reachability outcome -- two after Task 3,
    three after Task 4. A term left out does not read as wrong: it makes the
    gap larger, and the gap has a plausible explanation attached to it.

    It went false exactly this way once already. Before the class was added to
    the sum, the paragraph read "104,440 of the ceiling reached no finding"
    against a run printing 4,242 and 749.

    THE POPULATION IS COUNTED BY A SECOND ROUTE. `M` is built off the
    classification census; the assertion is against the rows carrying a
    DIRECTION, which is what "a lineage neighbour raised" means and which only
    a lineage row can carry. So a class dropped from the sum breaks the
    identity rather than shrinking both sides of it.

    THE WRONG RULE IS SIMULATED BY HAND: naming `CLS_UNREACHABLE` alone, the
    shape the sentence had between Tasks 3 and 4. It is short here, and by
    exactly the bootstrap population.
    """
    out, md = _run(tmp_path, extra_edges=both_reachability_classes,
                   extra_registrations=over_the_floor)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    directioned = findings[findings.action.isin((S.A_ADD_PARENT, S.A_ADD_CHILD))]
    present = directioned.classification.value_counts(dropna=False)
    _both_classes_live(present)

    m = re.search(
        r"The union above is ([\d,]+) rows; Mode 2 emitted "
        r"([\d,]+) rows a lineage neighbour raised -- "
        r"([\d,]+) on a pair samples of the type do hold elsewhere and "
        r"([\d,]+) on a pair none of them ever has -- so ([\d,]+) of the "
        r"ceiling reached no finding",
        re.sub(r"\s+", " ", md))
    assert m is not None, (
        "the ceiling-gap sentence changed shape; re-pin it rather than "
        "deleting this test")
    union, raised, reachable, unreachable, gap = [
        int(g.replace(",", "")) for g in m.groups()]

    # the stated total IS the lineage lane's whole output, by the other route
    assert raised == len(directioned)
    # ...and its two terms sum to it, so no class is unaccounted for
    assert reachable + unreachable == raised
    assert reachable == int(present.get(S.CLS_ABSENCE_LINEAGE, 0))
    assert unreachable == _unaccounted(present)

    # THE WRONG RULE, BY HAND, IN BOTH DIRECTIONS. Naming ONE reachability
    # class is short, and it is short whichever one is named -- which is the
    # half review round 1 found missing here. The earlier version asserted only
    # `unreachable != present[CLS_UNREACHABLE]`, and in a world with no
    # `CLS_UNREACHABLE` row that term is 0 and the inequality holds for free:
    # the suite stayed green at 1253/12 under a mutation dropping
    # `CLS_UNREACHABLE` from `build_report`, while the real extract printed
    # "76,869 rows a lineage neighbour raised ... so 95,469 of the ceiling
    # reached no finding" against a run printing 4,242 and 749.
    for dropped in (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP):
        wrong = _unaccounted(present) - int(present.get(dropped, 0))
        assert wrong != unreachable, (
            f"dropping {dropped} from the sum leaves the stated total "
            "unchanged, so this world cannot tell the two rules apart")
        assert raised - (reachable + wrong) == int(present.get(dropped, 0))
    # ...and the gap is the ceiling minus that total and not minus a subset.
    # The union is read out of the same sentence, so the arithmetic checked is
    # the one a reader performs on the page.
    assert gap == union - raised
    assert union >= raised


def test_the_evidenced_classes_are_the_complement_of_the_two_that_propose_nothing():
    """`EVIDENCED` is a hand-written tuple over a CLOSED vocabulary.

    It is the denominator `_term_contrast_note` ranks terms on, so a class
    missing from it makes `lineage_share` a share of less than the population
    the same table calls `rows` -- which is what it was until 2026-08-21, and
    what adding a class without touching it would restore. The tuple is a
    judgement (which classes NAME an evidence source) and stays hand-written;
    what is asserted is that the judgement was MADE for every member of
    `_schema.CLASSES`, by pinning the complement.

    `CLS_ALT_LABEL` and `CLS_UNRESOLVED` are the two out, and both are the
    classes whose gloss ends "PROPOSES NOTHING": one says the term is another
    name for something already registered and the other says no test settled
    the row. Neither names where evidence came from.
    """
    assert set(RD.EVIDENCED) | {S.CLS_ALT_LABEL, S.CLS_UNRESOLVED} == set(
        S.CLASSES), (
        "a class in `_schema.CLASSES` is neither an evidence source nor one of "
        "the two that propose nothing; `EVIDENCED` has not been ruled on")
    assert not set(RD.EVIDENCED) & {S.CLS_ALT_LABEL, S.CLS_UNRESOLVED}
    assert len(set(RD.EVIDENCED)) == len(RD.EVIDENCED)
    # ...and the table that reads it prints a column per member, so a class in
    # the denominator and not in the row would be counted and never shown
    src = (REPO / "scripts" / "assay_hygiene" / "run_detect.py").read_text()
    table = src.split("def _term_contrast_note")[1].split("\ndef ")[0]
    for cls in RD.EVIDENCED:
        name = next(n for n in dir(S) if n.startswith("CLS_")
                    and getattr(S, n) == cls)
        assert table.count(f"S.{name}") >= 2, (
            f"{cls} is in EVIDENCED and the contrast table does not print a "
            "column for it in both rows")


def test_the_survival_table_covers_every_directioned_row_and_says_so(tmp_path):
    """The curve's population is STATED, not left for a reader to assume.

    The table was built over `CLS_ABSENCE_LINEAGE` alone, so after Task 3 it
    described 67,898 of the 167,347 rows a lineage neighbour raised while
    sitting under a heading that names neither number. Unreachable rows are
    lineage-derived -- they carry a direction and a precedent rate -- so they
    belong in it; what was missing was any sentence saying which rows are in.

    Asserted as a relationship: every row carrying one of the two directions is
    in the curve's denominator, and the section names the class rather than
    leaving its inclusion to be inferred from a total.
    """
    out, md = _run(tmp_path, extra_edges=both_reachability_classes,
                   extra_registrations=over_the_floor)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    directioned = findings[findings.action.isin((S.A_ADD_PARENT, S.A_ADD_CHILD))]
    _both_classes_live(directioned.classification.value_counts(dropna=False))

    section = _section(md, "Survival by direction")
    # the denominator column is the whole directioned population, per direction
    for action in (S.A_ADD_PARENT, S.A_ADD_CHILD):
        n = int((directioned.action == action).sum())
        if not n:
            continue
        assert f"| {action} |" in section, f"{action} is not in the curve"
        assert f"| {n:,} |" in section, (
            f"{action} covers {n:,} rows and no row of the table carries that "
            "denominator; the curve is drawn over a subset of the population")
    # ...and the population is named, not assumed -- BOTH reachability classes,
    # since `CLS_BOOTSTRAP` is a cut through `CLS_UNREACHABLE` and a section
    # naming only one of them leaves the other's inclusion to be inferred
    for cls in (S.CLS_UNREACHABLE, S.CLS_BOOTSTRAP):
        assert cls in section, (
            f"the survival section never says whether {cls} rows are in its "
            "curve; a reader who assumes either way has no way to check")
    assert f"**{len(directioned):,}**" in section, (
        "the survival section states no population size")


# --- integrity ---------------------------------------------------------------


def test_a_nonzero_integrity_count_cannot_be_omitted(tmp_path):
    """Requirement 6, and the zero case is the one that needs stating.

    An integrity population printed only when nonzero reads, on a clean run,
    exactly like one that was never measured. Both directions are asserted:
    every key appears when all are zero, and a nonzero value appears with its
    key when one is not.
    """
    out, md = _run(tmp_path)
    for key in L.INTEGRITY_KEYS:
        assert key in md, f"integrity key {key} is not printed"

    # ...and a nonzero count cannot be dropped
    integrity = dict.fromkeys(L.INTEGRITY_KEYS, 0)
    integrity["unresolved_edges"] = 4242
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    defects = pd.read_csv(out / "vocabulary-defects.csv")
    md2 = RD.build_report(findings, disposition, defects,
                          ceiling=RD._ceiling_from(out.parent / "extract"),
                          integrity=integrity, out_dir=str(out))
    assert "4,242" in _line(md2, "unresolved_edges")


# --- the pattern key ---------------------------------------------------------


def test_a_cohort_reports_its_no_mode_rows_rather_than_dropping_them(tmp_path):
    """The review surface, and the regression for how its draft lied.

    THE DRAFT JOINED THE MODE COLUMN WITH `dropna()`. A row in NO mode --
    `CLS_ALT_LABEL`, proposing nothing, because the term is a different name
    for something already registered -- has no label to join, so it vanished
    from the string. Measured on the real extract, `D.IMG` / CometChip Assay /
    `TIF` is 2,447 rows whose overwhelming majority reach no mode, and the
    draft labelled that cohort `MODE_1`. A curator would have read a
    2,447-row registration proposal where the finding is "propose nothing".

    So the three counts are COLUMNS and they are asserted to sum. This is the
    third defect in this package from a null dropped by a default, after
    `disposition_breakdown` and `findings_census`.
    """
    out, _ = _run(tmp_path)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    cohorts = pd.read_csv(out / RD.COHORTS_NAME)

    assert list(cohorts.columns) == RD.COHORT_COLUMNS
    # every finding is in exactly one cohort, and in exactly one mode column
    assert int(cohorts.n_rows.sum()) == len(findings)
    assert (cohorts.n_mode_1 + cohorts.n_mode_2 + cohorts.n_no_mode
            == cohorts.n_rows).all()
    # ...and the per-mode totals equal the frame's own
    for mode, col in ((S.MODE_1, "n_mode_1"), (S.MODE_2, "n_mode_2")):
        assert int(cohorts[col].sum()) == int((findings["mode"] == mode).sum())
    assert int(cohorts.n_no_mode.sum()) == int(findings["mode"].isna().sum())

    # THE NULL STATE IS RENDERED, never blank. A blank cell reads as "not
    # measured"; these rows were measured and reach no mode on purpose.
    if int(cohorts.n_no_mode.sum()):
        assert RD.NO_MODE in " ".join(cohorts.classifications.astype(str))

    # A MIXED COHORT IS THE ONLY ONE THAT CAN CATCH THE DROP, and the fixture
    # has none, so it is built here. `_join` falls back to `NO_MODE` when it
    # renders nothing at all, which means an ALL-null cohort looks identical
    # under both rules -- the mutation that drops nulls survived this test
    # until the case below was added. The real extract's `D.IMG` / CometChip /
    # `TIF` cohort is exactly this shape: 39 rows classified and 2,408 not.
    mixed = pd.DataFrame({
        "sample_type": ["D.IMG", "D.IMG"],
        "proposed_internal_assay_id": [138, 138],
        "proposed_internal_assay_title": ["CometChip Assay"] * 2,
        "raw_value": ["TIF", "TIF"],
        "source_field": ["Type", "Type"],
        "sample_id": [1, 2],
        "mode": [S.MODE_1, None],                  # one in a mode, one not
        "classification": [None, S.CLS_ALT_LABEL],  # ...and the inverse
        "action": ["ADD_TO_ASSAY", "NONE"],
        "claim_tier": [S.T_WEAK, S.T_WEAK], "gate": [S.GATE_PASS] * 2,
        "precedent_rate": [None, None], "co_reg_rate": [None, 0.0],
        "project_ids": ["1", "1"],
    })
    row = RD.cohort_table(mixed).iloc[0]
    assert (row.n_rows, row.n_mode_1, row.n_mode_2, row.n_no_mode) == (2, 1, 0, 1)
    assert row.classifications == f"{S.CLS_ALT_LABEL};{RD.NO_MODE}", (
        "one row of this cohort carries no classification and one carries "
        f"{S.CLS_ALT_LABEL}; dropping the null renders the cohort as though "
        "every row were classified, which is how a 2,408-row 'propose "
        "nothing' finding reads as a registration proposal")


def test_the_cohort_table_refuses_mode_counts_that_do_not_sum(tmp_path):
    """The guard is a raise, not a comment. Verified by feeding it a hole.

    `cohort_table` asserts its own identity at runtime rather than trusting
    the groupby, because the failure it guards against is silent by
    construction: a mode value that matches none of the three buckets simply
    counts nowhere and the row totals still look plausible.
    """
    f = pd.DataFrame({
        "sample_type": ["TIS"], "proposed_internal_assay_id": [11],
        "proposed_internal_assay_title": ["Tissue Collection"],
        "raw_value": ["Blood"], "source_field": ["Type"], "sample_id": [1],
        "mode": ["MODE_UNKNOWN"],           # in none of the three buckets
        "classification": [S.CLS_ABSENCE_COMPAT], "action": ["ADD_TO_ASSAY"],
        "claim_tier": [S.T_STRONG], "gate": [S.GATE_PASS],
        "precedent_rate": [0.9], "co_reg_rate": [0.9], "project_ids": ["1"],
    })
    with pytest.raises(ValueError, match="do not sum"):
        RD.cohort_table(f)


def test_every_pattern_table_is_keyed_on_the_triple_including_raw_value():
    """Requirement 7. The coarser key made two opposite populations invisible.

    Under `(sample_type, proposed_assay)` the PAV `Blood` and `Necropsy` rows
    collapse into one row whose numbers describe neither. The key must carry
    `raw_value`, and this asserts the KEY rather than a symptom of it.
    """
    assert RD.PATTERN_KEY == ["sample_type", "proposed_internal_assay_id",
                             "raw_value"]

    # ...and the rollup actually separates two rows differing only in raw_value
    f = pd.DataFrame({
        "sample_type": ["PAV", "PAV"],
        "proposed_internal_assay_id": [11, 11],
        "proposed_internal_assay_title": ["Tissue Collection"] * 2,
        "raw_value": ["Blood", "Necropsy"],
        "source_field": ["Type", "Type"],
        "sample_id": [1, 2],
        "mode": [S.MODE_2, S.MODE_2],
        "classification": [S.CLS_ABSENCE_COMPAT, S.CLS_ALT_LABEL],
        "action": ["ADD_TO_ASSAY", "NONE"],
        "co_reg_rate": [0.9, 0.0],
    })
    rollup = RD.pattern_rollup(f)
    assert len(rollup) == 2, (
        "two raw values on one (type, assay) collapsed into one pattern; that "
        "is the key that hid the PAV populations")


# --- the vocabulary ----------------------------------------------------------


def test_the_vocabulary_is_named_the_largest_defect_source(tmp_path):
    """Requirement 8. The claim is scoped and the mapping is named.

    A claim is only as good as the term that produced it, and no stage before
    the gate tested the term. The `illumina library` mapping is the single
    largest producer and is named rather than left for a reader to find in a
    202-row csv.
    """
    out, md = _run(tmp_path)
    defects = pd.read_csv(out / "vocabulary-defects.csv")
    assert "vocabulary" in md.lower()
    assert f"{len(defects):,}" in md


def test_the_real_extract_names_the_illumina_mapping_with_its_measured_share():
    """The named mapping, over the real extract, with the share re-measured.

    NAMED, not marked. This suite selects its extract-backed tests with
    `-k 'not real_extract'` against the test NAME -- the mutation harnesses on
    this branch all use that expression -- so a `pytest.mark` here would be an
    unregistered marker that no harness honours and every fast lane would run
    this against an extract it does not have.

    The spec says 212 of 250 `ABSENCE_COMPAT` flags. Measured off the
    disposition Task 8 wrote, the denominator was 247 and the numerator still
    212 -- so the sentence has to carry the measured pair and not the
    remembered one. This asserts the report agrees with the csv, whatever the
    csv says today.

    "WHATEVER THE CSV SAYS" NOW INCLUDES ZERO, and that is this revision. On
    2026-08-20 the operator retired `Type: illumina library` -- a term naming a
    MATERIAL rather than an assay, whose carriers span six assays (Short Read
    Sequencing 2,390 / DNA Extraction 1,884 / cDNA Synthesis 408 / Library
    Creation 394 / Bulk DNA Sequencing 68 / Single Cell Expression 4) -- and the
    mapping left the disposition entirely, taking `ABSENCE_COMPAT` from 247 to
    35. The report correctly stopped naming it.

    The original body asserted the report names the mapping UNCONDITIONALLY,
    which made a retirement indistinguishable from the report silently dropping
    a figure it should still carry. Both directions are now asserted: named with
    the measured pair while the csv holds rows, and NOT named once it holds none
    -- because a sentence quoting a share for a mapping with zero flags is
    exactly the stale-figure defect this test exists to catch.
    """
    d = ARTIFACTS / "mode3-disposition.csv"
    report = ARTIFACTS / RD.REPORT_NAME
    if not d.exists() or not report.exists():
        pytest.skip("no disposition or report; run run_detect.py first")
    disposition = pd.read_csv(d)
    md = report.read_text()
    compat = disposition[disposition.classification == S.CLS_ABSENCE_COMPAT]
    illumina = compat[compat.raw_value.astype(str).str.strip().str.lower()
                      == "illumina library"]

    if len(illumina) == 0:
        # the retired case. Assert the RETIREMENT is why, so this branch cannot
        # go green on a report that simply lost the sentence.
        vocab = V.load_vocabulary(ARTIFACTS / "vocabulary.csv")
        row = vocab[(vocab.source_field == "Type")
                    & (vocab.raw_value == "illumina library")]
        assert len(row) == 1 and pd.isna(row.iloc[0].internal_assay_id), (
            "no illumina flags remain, but the term is not retired either -- "
            "the mapping vanished for some other reason; re-measure")
        assert "illumina library" not in md.lower(), (
            "the report still quotes a share for a mapping that now carries "
            "zero flags")
        return

    assert "illumina library" in md.lower()
    line = _line(md.lower(), "illumina library")
    assert f"{len(illumina):,}" in line and f"{len(compat):,}" in line, (
        f"the report's illumina sentence must carry the MEASURED pair "
        f"{len(illumina)}/{len(compat)}; line was {line!r}")


# --- the general form --------------------------------------------------------


def test_every_bolded_integer_in_the_prose_is_a_number_the_artifacts_hold(
        tmp_path):
    """THE REQUIREMENT, in its general form: prose counts == csv counts.

    Increment 1 shipped a report quoting a table it had not computed. Rather
    than pin each sentence -- which only guards the sentences someone thought
    to pin -- this collects every bolded integer the report publishes and
    requires each to be re-derivable from the three csvs, the ceiling or the
    integrity report. A remembered figure fails without anyone predicting
    which one would go stale.

    Bolding is the report's own convention for "this is a headline count", so
    the population this scans is the one the operator actually reads.

    IT RUNS OVER THE WORLD WITH AN UNREACHABLE ROW IN IT, so the census table
    and the two per-class breakdowns this task added are inside the scan rather
    than beside it. Against the base world those sections render every class at
    zero and the scan cannot tell a derived count from a hard-coded one.
    """
    out, md = _run(tmp_path, extra_edges=both_reachability_classes,
                   extra_registrations=over_the_floor)
    findings = pd.read_csv(out / "findings.csv", low_memory=False)
    disposition = pd.read_csv(out / "mode3-disposition.csv")
    defects = pd.read_csv(out / "vocabulary-defects.csv")
    ceiling = RD._ceiling_from(out.parent / "extract")

    legitimate = set()
    for frame in (findings, disposition, defects):
        legitimate.add(len(frame))
        for col in ("mode", "classification", "action", "gate",
                    "precedence_step", "defect", "lineage", "compat_band"):
            if col in frame.columns:
                legitimate |= set(frame[col].value_counts(dropna=False).tolist())
        for col in ("sample_id", "proposed_internal_assay_id",
                    "claimed_internal_assay_id"):
            if col in frame.columns:
                legitimate.add(int(frame[col].nunique()))
    legitimate |= set(int(v) for v in ceiling.values())
    if len(findings):
        legitimate.add(len(findings) - int((findings.action == "NONE").sum()))
    legitimate |= {0}
    # MODE_1's qualification counts, which are subset counts and so are not
    # reachable from the whole-frame value_counts above
    m1 = findings[findings["mode"] == S.MODE_1]
    if len(m1):
        legitimate.add(int(RD._truthy(m1.contested).sum()))
        legitimate |= set(m1.claim_tier.value_counts(dropna=False).tolist())
        legitimate.add(int((m1.gate != S.GATE_PASS).sum()))
    if "n_claims" in defects.columns and len(defects):
        legitimate.add(int(defects.n_claims.sum()))
        legitimate |= set(defects.groupby("defect").n_claims.sum().tolist())
    # THE THREE PER-CLASS CENSUSES, two of which are SUBSET counts and so are
    # unreachable from the whole-frame value_counts above. Listed rather than
    # left to coincide: on this world every one of them is a single-digit
    # integer that some unrelated count also holds, which is precisely the
    # collision that makes a small fixture certify a wrong figure.
    if len(findings):
        directioned = findings[
            findings.action.isin((S.A_ADD_PARENT, S.A_ADD_CHILD))]
        legitimate.add(len(directioned))
        for frame in (findings, findings[findings["mode"] == S.MODE_2],
                      directioned):
            legitimate |= set(int(n) for n in RD.classification_census(frame))
    # per-pattern sizes and the termed/untermed split, which the two pattern
    # tables and their preamble publish
    if len(findings):
        rollup = RD.pattern_rollup(findings)
        termed = rollup[rollup.raw_value.notna()]
        untermed = rollup[rollup.raw_value.isna()]
        legitimate |= set(rollup.n_rows.tolist())
        legitimate |= {len(rollup), len(termed), len(untermed),
                       int(termed.n_rows.sum()), int(untermed.n_rows.sum())}

    stale = [n for n in _bolded_ints(md) if n not in legitimate]
    assert not stale, (
        f"bolded figure(s) {stale} appear in the prose but are not a count "
        "any artifact holds. A number a reader cannot re-derive is how "
        "increment 1 shipped a table it had not computed.")


def test_the_real_extract_reports_a_correction_matching_the_disposition():
    """The same equality, over the extract the operator will actually read.

    The fixture world is small enough that a coincidence could satisfy the
    scan above. This one runs the identical check against the 866.
    """
    d = ARTIFACTS / "mode3-disposition.csv"
    report = ARTIFACTS / RD.REPORT_NAME
    if not d.exists() or not report.exists():
        pytest.skip("no disposition or report; run run_detect.py first")
    disposition = pd.read_csv(d)
    md = report.read_text()
    split = X.disposition_breakdown(disposition)
    assert f"{len(disposition):,}" in md
    for bucket, n in split.items():
        assert f"{n:,}" in md, f"{bucket} count {n:,} missing from the report"
