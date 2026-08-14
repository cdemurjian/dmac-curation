# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage 0: complete the lineage graph.

Creates the DERIVED_FROM relationships that production already records in
samples.json_metadata but has never written to the graph. Writes only Neo4j,
never MySQL, and never deletes.

See docs/superpowers/specs/2026-08-12-assay-hygiene-design.md.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from . import _schema as S


def plan_edges(
    parents: pd.DataFrame,
    nodes: pd.DataFrame,
    existing: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Decide which declared parent references need a DERIVED_FROM edge.

    parents  : child_uuid | field | token   (every token collect_parent_tokens
               yielded, valid or not)
    nodes    : uuid | sample_id | type      (the graph's node index)
    existing : child_uuid | parent_uuid     (DERIVED_FROM edges already present)

    Returns (plan, residues). Nothing is dropped silently: every excluded
    reference is counted under a drop reason, so

        len(plan) + <every drop reason in residues> == len(parents)

    holds for any input. "prod_regex_would_reject" is NOT a drop reason and is
    excluded from that sum -- it is a report-only count that overlaps the
    keepers, recording what the live server would have thrown away.
    """
    residues = {
        S.D_NOT_UID: 0,
        S.D_NO_NODE: 0,
        S.D_SELF_LOOP: 0,
        S.D_ALREADY_EXISTS: 0,
        "duplicate_reference": 0,
        "prod_regex_would_reject": 0,
    }

    node_id = dict(zip(nodes["uuid"], nodes["sample_id"]))
    node_type = dict(zip(nodes["uuid"], nodes["type"]))
    have = set(zip(existing["child_uuid"], existing["parent_uuid"]))

    kept: list[tuple] = []
    seen: set[tuple[str, str]] = set()

    # Selected by name before iterating: itertuples unpacks POSITIONALLY, so a
    # producer emitting these three columns in another order would swap field
    # and token and fail every reference on UID validation. This is a no-op for
    # a correctly-ordered frame and a KeyError for a missing column.
    for child_uuid, field, token in parents[S.PARENT_COLUMNS].itertuples(index=False):
        if not S.UID_RE_FIXED.match(str(token)):
            residues[S.D_NOT_UID] += 1
            continue
        # Report, do not act on, what the live server would have thrown away.
        if not S.UID_RE_PROD.match(str(token)):
            residues["prod_regex_would_reject"] += 1
        if child_uuid == token:
            residues[S.D_SELF_LOOP] += 1
            continue
        if token not in node_id or child_uuid not in node_id:
            residues[S.D_NO_NODE] += 1
            continue
        if (child_uuid, token) in have:
            residues[S.D_ALREADY_EXISTS] += 1
            continue
        if (child_uuid, token) in seen:
            # The same pair declared under two fields is one edge, not two.
            # Counted, not skipped silently: an operator reading the ledger
            # must be able to tell a collapsed duplicate from a lost reference.
            residues["duplicate_reference"] += 1
            continue
        seen.add((child_uuid, token))
        kept.append((
            child_uuid, token,
            node_id[child_uuid], node_id[token],
            node_type[child_uuid], node_type[token],
            field,
        ))

    plan = pd.DataFrame(kept, columns=[
        "child_uuid", "parent_uuid", "child_id", "parent_id",
        "child_type", "parent_type", "field",
    ])
    return plan, residues


# --- protocol resolution -----------------------------------------------------
#
# The house rule, and it is NOT the server's regex alone.
#
# `_build_derived_from_payloads` prefers an upload sheet's explicit `sop_id`
# column over its `_SOP_URL_RE` fallback (neo4j_sync.py:908). Every existing
# labelled edge came in that way, and that column was computed by
# `internal-assays-migration/phase4_sample_export.py::resolve_sop_id`, which
# tries three formats in order against a {sops.title: sops.id} lookup. Measured
# 2026-08-14: applied verbatim to production it reproduces the stored
# protocol_id on 200,000 of 200,000 sampled existing edges with zero
# disagreements, and resolves 85,104 of stage 0's 90,534 planned edges -- 85,093
# of them by format 3 and exactly ONE by the URL regex this stage was originally
# specified against.
#
# So porting the rule is reconstruction, not divergence: a backfill has no
# sheet, and reproducing what the sheet would have supplied is what keeps a
# stage 0 edge indistinguishable from a pipeline-produced one. Resolving 1 edge
# in 90,534 would have made the other 90,533 anomalous instead.

# 1. a SOP URL whose trailing integer IS the sops.id. Identical to _SOP_URL_RE
#    (neo4j_sync.py:42) -- keep the two in step.
SOP_URL_RE = re.compile(r"/sops/(\d+)")
# 2. a URL carrying the SOP's UID filename, which is its sops.title.
SOP_UID_RE = re.compile(r"uid=([^/]+)")

# Which of the three formats resolved an edge, or why none did. Exactly
# analogous to assay_source and, like it, a partition: every planned edge
# carries one of these, so the report's breakdown totals to the edge count.
P_SRC_URL = "sop_url"
P_SRC_UID = "uid_url"
P_SRC_TITLE = "title"
P_SRC_UNRESOLVED = "unresolved"
P_SRC_ABSENT = "none"


def _resolve_protocol(protocol_val, title_to_id: dict) -> tuple:
    """(protocol_id, protocol_source) for one child's Protocol metadata value.

    Ported from resolve_sop_id. Two things it deliberately keeps:

    - **the order, and the early return.** A `uid=` match returns whatever the
      lookup gives, hit or miss; it never retries the whole string as a title.
      Observable whenever a URL's uid half is unknown while the URL itself
      happens to be a sops.title.
    - **str() rather than an isinstance guard.** json_metadata is
      operator-entered, and a Protocol arrives as a number or a list often
      enough that a backfill over 400k rows cannot raise on one.

    The one refinement: a whitespace-only value is reported as ABSENT rather
    than UNRESOLVED. Both resolve to no id -- this decides only which bucket the
    report puts it in, and "a protocol value a curator can go and look at" is
    the wrong description of "  ".
    """
    if not protocol_val:
        return None, P_SRC_ABSENT
    text = str(protocol_val).strip()
    if not text:
        return None, P_SRC_ABSENT
    m = SOP_URL_RE.search(text)
    if m:
        # Taken on trust, and NOT checked against the sops extract: the server
        # does the same and simply leaves the title null when the SOP is unknown
        # (neo4j_sync.py:1055-1062), so validating here would make a stage 0 edge
        # distinguishable from a pipeline one. The report states how many ids
        # were written on that trust alone.
        return int(m.group(1)), P_SRC_URL
    m = SOP_UID_RE.search(text)
    if m:
        # rstrip("/") is the migration's own, and is already unreachable --
        # [^/]+ cannot capture a slash. Kept so the two functions read alike.
        uid = m.group(1).rstrip("/")
        if uid in title_to_id:
            return title_to_id[uid], P_SRC_UID
        return None, P_SRC_UNRESOLVED
    if text in title_to_id:
        return title_to_id[text], P_SRC_TITLE
    return None, P_SRC_UNRESOLVED


def resolve_properties(
    plan: pd.DataFrame,
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    sops: pd.DataFrame,
) -> pd.DataFrame:
    """Compute each new edge's properties exactly as the server would.

    Mirrors nextseek_api/batch_upload/neo4j_sync.py:888-1098. Deliberately does
    not improve on two behaviours, so that an edge stage 0 writes is
    indistinguishable from one the upload pipeline would have written:
      - when several assays are shared, the minimum internal_assay_id wins
      - an assay with no junction row falls back to (assay_id, assays.title)

    Both are arbitrary rather than wrong, so neither is hidden: ``n_shared``
    reports how many assays the tiebreak had to choose between, and
    ``assay_source`` says which of the two id spaces the label came from. An
    edge with n_shared > 1 is a curator's to settle, not this stage's to guess.

    The one server input with no counterpart here is the upload sheet itself:
    the server lets a submitted row override the sop_id and the assay title
    (neo4j_sync.py:903-928). Stage 0 backfills edges for samples uploaded long
    ago, so there is no sheet. For the assay title that means the database wins.
    For the sop_id it means the opposite of leaving it to the regex fallback:
    the sheet's column is where 79.7% of the graph's protocol_ids came from, so
    ``_resolve_protocol`` reconstructs it. ``protocol_source`` records which
    format did, and the report breaks the plan down by it.
    """
    meta_by_id: dict[int, dict] = {}
    # Selected by name before iterating, as in plan_edges: itertuples unpacks
    # POSITIONALLY, and a frame emitting sample_id | json_metadata | uuid would
    # otherwise read the uuid as the metadata blob and silently NULL every
    # protocol instead of failing.
    for sid, _uuid, jmeta, _created, _projects in samples[
        S.SAMPLE_COLUMNS
    ].itertuples(index=False):
        try:
            parsed = json.loads(jmeta) if jmeta else {}
        except (ValueError, TypeError):
            parsed = {}
        # The server would raise AttributeError on a non-dict here; a backfill
        # over 400k rows cannot die on one malformed blob, so treat it as empty.
        meta_by_id[sid] = parsed if isinstance(parsed, dict) else {}

    # Both directions of the sops frame, built in one pass over the DECLARED
    # columns -- selected by name first, as everywhere else here, because a
    # producer emitting title | sop_id would otherwise key the lookup the wrong
    # way round and every title-form Protocol (94% of the population) would come
    # back unresolved with nothing failing.
    #
    #   sop_title   {sops.id: sops.title}, for the title the edge carries
    #   title_to_id {sops.title: sops.id}, the migration's own lookup
    #
    # Two sops sharing a title keep the SMALLEST id, mirroring the assay
    # tiebreak below. Production has 553 titles over 553 sops so this is
    # invisible there; SOPS_SQL carries no ORDER BY, so under a future duplicate
    # a dict built by plain assignment would resolve differently between two
    # extracts of the same database. A null title is skipped: nothing can equal
    # it, and it would put a float in the id comparison.
    sop_title: dict = {}
    title_to_id: dict = {}
    for sop_id, title in sops[S.SOP_COLUMNS].itertuples(index=False):
        sop_title[sop_id] = title
        if pd.isna(sop_id) or pd.isna(title):
            continue
        prev = title_to_id.get(title)
        if prev is None or int(sop_id) < prev:
            title_to_id[title] = int(sop_id)

    assays_by_sample: dict[int, set[int]] = {}
    for sid, aid in membership[S.MEMBERSHIP_COLUMNS].itertuples(index=False):
        assays_by_sample.setdefault(sid, set()).add(aid)

    # assay_id -> (internal_assay_id, internal_assay_title, source)
    #
    # Two passes, mirroring the server's steps 3b-3d (neo4j_sync.py:1003-1027).
    # Pass 1 is the junction table, and an assay mapped to several internal
    # assays keeps the SMALLEST internal_assay_id -- the server's own rule, and
    # its own comment: "Keep smallest internal_assay_id per assay_id
    # (deterministic for 1:N)" (neo4j_sync.py:879-881). Duplicate assay_id rows
    # are normal input, not corruption: the extractor LEFT JOINs the junction
    # table and joins through investigations_projects, so one assay yields one
    # row per (internal assay x project) and their order is not stable across
    # extracts. Last-row-wins would therefore be non-deterministic.
    #
    # Pass 2 is the fallback and only fills assay_ids pass 1 never resolved, so
    # a real junction row beats a fallback for the same assay in any row order.
    # The passes must stay separate: a fallback's id is an assays.id, not an
    # internal_assays.id, so letting it into the minimum above would compare two
    # unrelated id spaces and could hand the edge the wrong internal assay.
    resolved_assay: dict[int, tuple[int, str, str]] = {}
    assay_rows = assays[S.ASSAY_COLUMNS]
    for row in assay_rows.itertuples(index=False):
        if pd.isna(row.internal_assay_id):
            continue
        ia_id = int(row.internal_assay_id)
        prev = resolved_assay.get(row.assay_id)
        if prev is None or ia_id < prev[0]:
            resolved_assay[row.assay_id] = (
                ia_id, row.internal_assay_title, "junction",
            )
    for row in assay_rows.itertuples(index=False):
        if row.assay_id in resolved_assay:
            continue
        # neo4j_sync.py:1021 coerces a NULL assays.title to "" here.
        title = row.title if pd.notna(row.title) else ""
        resolved_assay[row.assay_id] = (row.assay_id, title, "fallback")

    out: list[tuple] = []
    for r in plan.itertuples(index=False):
        meta = meta_by_id.get(r.child_id, {})
        protocol_val = meta.get("Protocol") or meta.get("protocol") or ""
        protocol_id, protocol_source = _resolve_protocol(protocol_val, title_to_id)
        # `if protocol_id` and not `is not None`, mirroring neo4j_sync.py:1060.
        protocol_title = sop_title.get(protocol_id) if protocol_id else None

        shared = (assays_by_sample.get(r.child_id, set())
                  & assays_by_sample.get(r.parent_id, set()))
        assay_id = internal_id = internal_title = None
        source = "none"
        if shared:
            best = None
            for aid in shared:
                if aid not in resolved_assay:
                    continue
                ia_id, ia_title, src = resolved_assay[aid]
                if best is None or ia_id < best[0]:
                    best = (ia_id, ia_title, src, aid)
            # A shared assay the assays frame does not describe stays
            # unresolved and the edge goes out dark with n_shared standing --
            # visibly an extract gap rather than a genuinely dark edge.
            if best is not None:
                internal_id, internal_title, source, assay_id = best

        out.append((
            r.child_id, r.child_uuid, r.parent_id, r.parent_uuid,
            protocol_id, protocol_title, assay_id,
            internal_id, internal_title,
            r.child_type, r.parent_type, r.field, len(shared), source,
            protocol_source,
        ))

    return pd.DataFrame(out, columns=S.STAGE0_PLAN_COLUMNS)


def reconcile_childof(childof: pd.DataFrame, parents: pd.DataFrame) -> pd.DataFrame:
    """CHILD_OF edges the child's CURRENT metadata no longer declares.

    Reported only. Operator ruling 2026-08-13: CHILD_OF is never written,
    modified or deleted by this pipeline, so this frame carries no action
    column by design.

    Covers both populations the spec names: an edge whose child declares some
    other parent, and an edge whose child declares none at all. Neither is
    special-cased -- a pair absent from the declared set is absent for the
    operator to explain, not for this function to classify.
    """
    declared = set(zip(parents["child_uuid"], parents["token"]))
    rows = [
        (c, p, "not_declared_by_metadata")
        for c, p in zip(childof["child_uuid"], childof["parent_uuid"])
        if (c, p) not in declared
    ]
    # Columns are declared even when rows is empty: task 7 writes this straight
    # to reconciliation.csv, and a bare 0x0 frame writes a headerless file.
    return pd.DataFrame(rows, columns=["child_uuid", "parent_uuid", "reason"])


# --- the dry-run report ------------------------------------------------------
#
# The report IS the operator's gate: they read it and then authorise a ~90,000
# relationship write. Anything it fails to state has been dropped silently in
# the only sense that matters operationally.

# Residue keys that count something OVERLAPPING the keepers rather than
# excluding anything, and so must never be summed into the exclusion ledger.
# Mirrors the accounting the planner's docstring states. Every OTHER key is
# treated as a drop reason and rendered by iteration, so a reason added to
# plan_edges later is reported -- with its raw key if nobody labelled it --
# instead of vanishing. A report-only counter added there and forgotten here
# inflates the ledger visibly, which is the safe direction to fail.
REPORT_ONLY_RESIDUES = frozenset({"prod_regex_would_reject"})

# The drop reasons, in the operator's words. D_NO_NODE is the one that cannot
# be read off its own constant: the value is "parent_not_a_node", but the
# branch also fires when the CHILD is missing from the node index. The constant
# is frozen (stages A-F key off it); the label is not, and the label is what
# gets read.
RESIDUE_LABELS = {
    S.D_NOT_UID: "the token is not a sample UID under the corrected pattern",
    S.D_NO_NODE: "an endpoint (the child or the parent) has no Sample node",
    S.D_SELF_LOOP: "the child declares itself as its own parent",
    S.D_ALREADY_EXISTS: "a DERIVED_FROM edge already joins that pair",
    "duplicate_reference": "the same (child, parent) pair declared under two fields",
}

# How many tiebreak edges to list before summarising. The spec expects 28 on
# production; the cap exists so a bad extract cannot bury the rest of the gate
# under 90,000 table rows.
TIEBREAK_LIST_CAP = 50

# Why an edge carries no protocol id. Mutually exclusive and, together with
# "the child has no samples row", exhaustive.
_P_NO_ROW = "the child has no row in the samples extract"
_P_EMPTY = "the child's json_metadata is empty"
_P_UNREADABLE = "the child's json_metadata did not parse as a JSON object"
_P_NO_PROTOCOL = "the child's metadata names no protocol any of the three formats resolves"
_PROTOCOL_CAUSES = [_P_NO_ROW, _P_EMPTY, _P_UNREADABLE, _P_NO_PROTOCOL]

# What each protocol_source means, in the order _resolve_protocol tries them.
# Rendered by iteration over the values the plan actually carries, with these
# five always shown: a source added to _resolve_protocol and forgotten here is
# printed under its raw key rather than vanishing, and a zero against a format
# is itself the finding -- `sop_url` at 1 in 90,534 is why this rule exists.
PROTOCOL_SOURCE_LABELS = {
    P_SRC_URL: "a `/sops/<id>` URL; the id is taken verbatim, unchecked",
    P_SRC_UID: "a URL carrying `uid=<sop title>`, matched against `sops.title`",
    P_SRC_TITLE: "the value is itself a `sops.title`",
    P_SRC_UNRESOLVED: "a `Protocol` value none of the three formats resolves",
    P_SRC_ABSENT: "the child's metadata carries no `Protocol` value",
}


def _pct(n: int, total: int) -> str:
    """A parenthesised percentage, or nothing at all when the total is zero.

    The empty plan is the steady state after a successful run, and the report
    is still the operator's receipt for it, so this cannot divide blindly.
    """
    return f" ({100.0 * n / total:.1f}%)" if total else ""


def _label(value) -> str:
    """A cell as it should print: no bare NaN, and no id turned into a float.

    A Sample node's `type` can be NULL, and any id column holding one null is
    float64 for the whole frame -- so an internal_assay_id arrives here as 11.0
    and the operator cannot paste it into a query. Both are rendering problems
    only; the plan itself keeps its dtypes for the applier to normalise.
    """
    if pd.isna(value):
        return "(none)"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _protocol_causes(resolved: pd.DataFrame, samples: pd.DataFrame) -> dict[str, int]:
    """Split the edges with no protocol id by cause, re-reading the metadata.

    resolve_properties swallows unparseable or non-object json_metadata into
    empty metadata and counts nothing, so a null protocol_id pools a data defect
    with a child that genuinely declares no Protocol. The two are not equally
    actionable, and only the samples frame separates them -- hence the recount
    rather than an inference off the resolved frame.

    Parsing mirrors resolve_properties exactly (json.loads, non-dict treated as
    empty), so these buckets describe the run that produced `resolved` rather
    than a stricter reading of the same data. `samples` is selected by name
    before iterating, for the reason given there.
    """
    cause_by_sample: dict[object, str] = {}
    for sid, _uuid, jmeta, _created, _projects in samples[
        S.SAMPLE_COLUMNS
    ].itertuples(index=False):
        if jmeta is None or (isinstance(jmeta, float) and pd.isna(jmeta)) or jmeta == "":
            cause_by_sample[sid] = _P_EMPTY
            continue
        try:
            parsed = json.loads(jmeta)
        except (ValueError, TypeError):
            cause_by_sample[sid] = _P_UNREADABLE
            continue
        # A document that parses to a list is as unusable as one that does not
        # parse: resolve_properties discards both, and the server would raise.
        cause_by_sample[sid] = _P_NO_PROTOCOL if isinstance(parsed, dict) else _P_UNREADABLE

    counts = dict.fromkeys(_PROTOCOL_CAUSES, 0)
    missing = resolved[resolved["protocol_id"].isna()]
    for child_id in missing["child_id"]:
        counts[cause_by_sample.get(child_id, _P_NO_ROW)] += 1
    return counts


def _prod_rejected_codes(resolved: pd.DataFrame) -> list[tuple[str, int]]:
    """Sample-type codes of the PLANNED edges the live server's UID_RE rejects.

    Derived from the frame this run was handed, so the report describes the
    extract in front of it instead of restating an observation about whichever
    extract happened to be on the bench when the sentence was written. This
    document is regenerated against every future extract.

    Deliberately scoped to the planned edges: `prod_regex_would_reject` is
    counted at validation, and a reference counted there and then excluded as a
    self-loop, a missing node, an existing edge or a duplicate never reaches this
    frame. So this cannot speak for those, and the sentence built from it must
    not either.

    Ordered by descending count then by code, so re-running the same extract
    renders a byte-identical report to diff.
    """
    counts: dict[str, int] = {}
    for token in resolved["parent_uuid"]:
        text = str(token)
        if not S.UID_RE_FIXED.match(text) or S.UID_RE_PROD.match(text):
            continue
        code = text.split("-", 1)[0]
        # Drop the optional dotted prefix: the sample-type code is the part the
        # `[A-Z]{3,}` half of the difference is about, and `A.TIS` is a TIS.
        if len(code) > 2 and code[1] == ".":
            code = code[2:]
        counts[code] = counts.get(code, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def build_report(
    resolved: pd.DataFrame,
    residues: dict[str, int],
    childof_unmatched: pd.DataFrame,
    samples: pd.DataFrame | None = None,
) -> str:
    """The markdown an operator reads before authorising the write.

    `samples` is optional and is used for one thing: recounting WHY an edge
    carries no protocol id. Without it the report still states protocol
    coverage, but says plainly that it cannot separate a child whose metadata
    could not be read from one that declares no protocol. Pass it.
    """
    total = len(resolved)
    labelled_col = resolved["internal_assay_id"].notna()
    labelled = int(labelled_col.sum())
    dark = total - labelled
    shared_col = resolved["n_shared"] > 0
    # An edge with a shared assay that stayed dark is an extract gap, not a dark
    # edge: something the assays frame does not describe was shared by both
    # endpoints. Pooling the two hides a broken extract behind a plausible count.
    dark_unresolved = int((shared_col & ~labelled_col).sum())
    dark_no_share = dark - dark_unresolved
    # n_shared > 1 alone is not a tiebreak: if nothing resolved, nothing was
    # chosen. Restricted to labelled edges, matching the spec's "28 out of
    # 82,663 labelled edges". Still an upper bound -- a shared assay the extract
    # does not describe never entered the comparison.
    tiebreak_col = (resolved["n_shared"] > 1) & labelled_col
    tiebreak = int(tiebreak_col.sum())
    fallback = int((resolved["assay_source"] == "fallback").sum())
    with_protocol = int(resolved["protocol_id"].notna().sum())
    no_protocol = total - with_protocol

    drops = {k: v for k, v in residues.items() if k not in REPORT_ONLY_RESIDUES}
    excluded = sum(int(v) for v in drops.values())

    lines = [
        "# Stage 0 dry run: complete the lineage graph",
        "",
        f"**{total:,} edges to create.** {labelled:,} labelled, {dark:,} dark.",
        "",
        "Stage 0 writes only Neo4j DERIVED_FROM relationships. It does not touch",
        "MySQL, assay_assets, or CHILD_OF, and it cannot delete.",
        "",
        "## Excluded references, by reason",
        "",
        "Every reference the planner read is either created or counted here, so",
        "`references considered` must equal the row count of the parents extract.",
        "A reason with no description is one the planner gained after this report",
        "was written; it is counted all the same.",
        "",
        "| Reason | What it means | References |",
        "|---|---|---|",
    ]
    # Iterated, never enumerated: an unrendered residue is a silent drop.
    for key, count in drops.items():
        meaning = RESIDUE_LABELS.get(key, "(no description here -- see plan_edges)")
        lines.append(f"| `{key}` | {meaning} | {int(count):,} |")
    lines += [
        f"| **excluded, total** |  | **{excluded:,}** |",
        f"| **created** |  | **{total:,}** |",
        f"| **references considered** |  | **{excluded + total:,}** |",
        "",
        "## Production regex override",
        "",
        f"`prod_regex_would_reject`: **{int(residues.get('prod_regex_would_reject', 0)):,}** "
        "references are valid UIDs that the live server's UID_RE rejects. Stage 0",
        "includes them: the counter is taken at validation, before the self-loop,",
        "missing-node, already-exists and duplicate checks, so those of them not",
        "excluded for another reason are created. It is a count of references, not",
        "a promise about edges.",
        "",
        "The two patterns differ in three ways, and this counter separates none of",
        "them:",
        "",
        "| Difference | production `UID_RE_PROD` | corrected `UID_RE_FIXED` |",
        "|---|---|---|",
        r"| sample-type code | `[A-Z]{3,}` | `[A-Z]{2,}` |",
        r"| dotted prefix | `([AD]\.)?` | `([A-Z]\.)?` |",
        r"| anchors | `^ ... $` | `\A ... \Z` |",
        "",
        "Only the first two can put a reference in this count. The sample-type",
        "length is the reason the fix exists: `AB`, the antibody type, is the only",
        "two-letter sample type in the database, so production discards every",
        "`AntibodyParent` reference before an edge is built. The prefix difference",
        "feeds the same count for any dotted prefix other than `A.` or `D.`.",
        "",
    ]

    # Measured off this run's own plan, never asserted about an earlier extract:
    # the report is regenerated against every future one, and a sentence naming
    # a date is a sentence that will be printed against data it never saw.
    rejected = _prod_rejected_codes(resolved)
    if rejected:
        by_code = ", ".join(f"`{code}` ({n:,})" for code, n in rejected)
        lines += [
            "Which of the two is doing the work here is measured, not assumed. Of the",
            "references in this count that became planned edges "
            f"(**{sum(n for _, n in rejected):,}** of them), the",
            f"sample-type codes seen on this run were: {by_code}.",
            "The rest of the counter -- any reference excluded for another reason -- is",
            "not in the plan and is not described by that sentence.",
            "",
        ]
    else:
        lines += [
            "Which of the two is doing the work here is measured, not assumed. On",
            "this run no planned edge carries a reference the live pattern would",
            "have rejected, so anything in the counter above was excluded for",
            "another reason before an edge was planned.",
            "",
        ]

    lines += [
        "The anchor difference runs the other way and cannot add to this count:",
        "`$` matches before a trailing newline and `\\Z` does not, so a token",
        "carrying a trailing newline is accepted by the live server and rejected",
        f"here, under `{S.D_NOT_UID}`.",
        "",
        "Until the fix ships to production, every new upload carrying an",
        "`AntibodyParent` regenerates this gap.",
        "",
        "## Assay resolution",
        "",
        f"- labelled: **{labelled:,}** of **{total:,}** edges{_pct(labelled, total)}",
        f"- dark because no assay is shared by both endpoints: **{dark_no_share:,}**",
        "- dark because the only shared assay is one the assays extract does not"
        f" describe: **{dark_unresolved:,}** (an extract gap, and expected to be 0)",
        f"- edges resting on the min-internal_assay_id tiebreak: **{tiebreak:,}**",
        f"- edges whose assay had no junction row (fallback path): **{fallback:,}**",
        "",
    ]

    # The spec asks for the tiebreak edges themselves, not just the count: the
    # choice among several shared assays is arbitrary-but-deterministic, and a
    # curator can only settle it by hand if the report names the edges.
    lines += ["### Edges resting on the tiebreak", ""]
    if tiebreak == 0:
        lines += ["None.", ""]
    else:
        lines += [
            "The minimum internal_assay_id won. Deterministic, but arbitrary --",
            "settle these by hand if it matters.",
            "",
            "| Child | Parent | Assays shared | internal_assay_id | Title |",
            "|---|---|---|---|---|",
        ]
        listed = resolved[tiebreak_col]
        for r in listed.head(TIEBREAK_LIST_CAP).itertuples(index=False):
            lines.append(
                f"| {r.child_uuid} | {r.parent_uuid} | {int(r.n_shared):,} "
                f"| {_label(r.internal_assay_id)} | {_label(r.internal_assay_title)} |"
            )
        if tiebreak > TIEBREAK_LIST_CAP:
            lines += [
                "",
                f"...and {tiebreak - TIEBREAK_LIST_CAP:,} more, in `plan.parquet` "
                "where `n_shared > 1`.",
            ]
        lines.append("")

    lines += [
        "## Protocol coverage",
        "",
        f"**{with_protocol:,}** of **{total:,}** edges carry a resolvable protocol"
        f" id{_pct(with_protocol, total)}.",
        "",
    ]

    # WHICH rule resolved them, not just how many. The coverage figure alone
    # invites the assumption that the `/sops/<id>` URL did the work; on
    # production it resolves 1 edge in 90,534 and a plain `sops.title` match
    # resolves 85,093. Every source is rendered and the table totals to the edge
    # count, so this is a partition of the plan rather than a selection from it.
    if total:
        counts = resolved["protocol_source"].value_counts(dropna=False).to_dict()
        # Known sources first, in resolution order, then anything else this
        # report was not written for -- by descending count then key, so the
        # same extract renders a byte-identical report to diff.
        extra = sorted(
            (k for k in counts if k not in PROTOCOL_SOURCE_LABELS),
            key=lambda k: (-counts[k], str(k)),
        )
        lines += [
            "Which rule resolved each edge. The three resolving formats are tried",
            "in the order below and the first that matches wins. `unresolved` and",
            "`none` resolve nothing; they are why the coverage figure above is not",
            "the whole plan. Every planned edge is in exactly one row.",
            "",
            "| Source | What it means | Edges |",
            "|---|---|---|",
        ]
        for src in list(PROTOCOL_SOURCE_LABELS) + extra:
            meaning = PROTOCOL_SOURCE_LABELS.get(
                src, "(no description here -- see _resolve_protocol)")
            lines.append(f"| `{_label(src)}` | {meaning} | {counts.get(src, 0):,} |")
        lines += [
            f"| **every planned edge** |  | **{total:,}** |",
            "",
        ]

        # The format-1 decision, stated rather than assumed. A `/sops/<id>` id is
        # the only one taken on trust: formats 2 and 3 read their id OUT of the
        # sops extract, so those cannot dangle. Measured 0 of 90,534 on
        # production; phrased as "resolved no title" because that is exactly what
        # is observable here, and it is also what the graph will show.
        n_url = counts.get(P_SRC_URL, 0)
        if n_url:
            uncorroborated = int(
                ((resolved["protocol_source"] == P_SRC_URL)
                 & resolved["protocol_title"].isna()).sum()
            )
            lines += [
                f"**{uncorroborated:,}** of the **{n_url:,}** edges resolved by a",
                "`/sops/<id>` URL resolved no `protocol_title`. Those are the ids",
                "nothing in the sops extract corroborates: they are what the child's",
                "metadata asserted, and stage 0 writes them unchecked. The server",
                "does the same (neo4j_sync.py:1055-1062), and dropping one would both",
                "make that edge distinguishable from a pipeline-produced one and turn",
                "a traceable id into a null indistinguishable from \"declares none\".",
                "Formats 2 and 3 read their id OUT of the sops extract, so only",
                "format 1 can produce an id the extract has no row for.",
                "",
            ]

    if no_protocol == 0:
        lines += ["Every planned edge resolved one, so there is nothing to explain.", ""]
    elif samples is None:
        lines += [
            f"The other **{no_protocol:,}** pool four causes this run cannot",
            "separate, because the samples frame was not supplied: the child has no",
            "row in the samples extract, its json_metadata is empty, its",
            "json_metadata did not parse as a JSON object, or its metadata names no",
            "protocol any of the three formats resolves. resolve_properties reads an",
            "unreadable blob as empty metadata, so a null protocol id is NOT a claim",
            "that the child declares no protocol -- and neither is the `none` row of",
            "the table above. Pass `samples` to build_report to have this split",
            "recounted.",
            "",
        ]
    else:
        lines += [
            f"The other **{no_protocol:,}**, recounted from the samples extract:",
            "",
            "| Cause | Edges |",
            "|---|---|",
        ]
        causes = _protocol_causes(resolved, samples)
        for cause in _PROTOCOL_CAUSES:
            lines.append(f"| {cause} | {causes[cause]:,} |")
        lines += [
            "",
            # Named, not numbered: "the third row" silently becomes a lie the day
            # someone reorders _PROTOCOL_CAUSES.
            f"`{_P_UNREADABLE}`",
            "is a data defect rather than a missing protocol, and it is invisible",
            "in the plan: resolve_properties reads an unparseable blob as empty",
            "metadata, so those edges are written with a null protocol id exactly",
            "like a child that declares none.",
            "",
        ]

    lines += [
        "## Hops",
        "",
        "| Hop | Edges | Labelled |",
        "|---|---|---|",
    ]
    # Aggregated inside the groupby rather than by re-filtering the frame per
    # group: `x == NaN` is False for every x, so a hop off an untyped node would
    # re-filter to nothing and print 0 labelled beside a non-zero total.
    hops = (
        resolved.assign(_labelled=labelled_col)
        .groupby(["child_type", "parent_type"], dropna=False)["_labelled"]
        .agg(["size", "sum"])
        # stable, so equal-sized hops keep the groupby's own key order and a
        # re-run of the same extract produces a byte-identical report to diff
        .sort_values("size", ascending=False, kind="stable")
    )
    for (child_type, parent_type), row in hops.iterrows():
        lines.append(
            f"| {_label(child_type)} -> {_label(parent_type)} "
            f"| {int(row['size']):,} | {int(row['sum']):,} |"
        )

    lines += [
        "",
        "## CHILD_OF reconciliation",
        "",
        f"**{len(childof_unmatched):,}** CHILD_OF edges are not declared by the",
        "child's current metadata. Reported for curation in `reconciliation.csv`.",
        "Nothing acts on them: stage 0 never writes, modifies or deletes a",
        "CHILD_OF relationship.",
        "",
    ]
    return "\n".join(lines)
