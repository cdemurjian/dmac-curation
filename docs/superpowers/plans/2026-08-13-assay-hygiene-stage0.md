# Assay Hygiene Stage 0: Lineage Graph Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the 90,534 `DERIVED_FROM` relationships that production records in `samples.json_metadata` but has never written to the graph, of which 82,663 get a correct assay from the existing intersection rule with no inference.

**Architecture:** A read-only extractor runs inside the production `nextseek` container and emits parquet. Every judgment (which references lack an edge, what properties each edge carries, what to report) is a pure function on the laptop under pytest. A thin in-container driver replays an explicit, reviewed manifest through `neo4j_sync.bulk_merge_relationships`. Neo4j is the only thing written; MySQL is read-only throughout.

**Tech Stack:** Python 3.11+, pandas, pyarrow, pytest. PEP 723 inline dependency blocks, matching every other script in `scripts/`.

**Spec:** `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md`

**Companion plan:** `docs/superpowers/plans/2026-08-12-assay-hygiene.md` (stages A-F, the membership-inference half). That plan depends on this one having run, because every statistic in it was measured against a graph missing its largest single hop.

## Global Constraints

- **P1 sentinel:** scripts must never create, modify, or delete anything inside the plugin checkout. All project paths resolve from the current working directory. `tests/conftest.py::plugin_sentinel` enforces this and will fail the suite otherwise.
- **Output root** is `assay-hygiene/` under the current working directory.
- **PEP 723 header** on every script: `requires-python = ">=3.11"` plus explicit dependencies.
- **Test command:** `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/<file> -v`
- **Dry run is the default.** `--write` must be explicit and never inferred.
- **Stage 0 writes ONLY Neo4j `DERIVED_FROM`.** It never writes MySQL, never touches `assay_assets`, and never deletes anything. It must not call `smart_merge_assay_assets` or the assays API.
- **`CHILD_OF` is never written, modified, or deleted.** Operator ruling 2026-08-13. It is read for reconciliation only.
- **Use the CORRECTED `UID_RE`, not production's.** Production runs `^([AD]\.)?[A-Z]{3,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?$`, whose `{3,}` rejects the two-letter `AB` sample type and silently discards all 8,131 antibody parent references. Stage 0 uses `\A([A-Z]\.)?[A-Z]{2,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?\Z` and reports the delta. This is the only place stage 0 overrides server behaviour.
- **Everything else comes from the server.** Key matching and semicolon splitting use the real `collect_parent_tokens`; edge properties follow `_build_derived_from_payloads` exactly, including the minimum-`internal_assay_id` tiebreak and the `(assay_id, assays.title)` fallback for assays with no junction row.
- **Nothing is dropped silently.** Every reference excluded for any reason is counted by reason in `report.md`.
- **Correct Django DB alias is `seek`** (`seek_production`). The `default` alias is `dmac` and its `assay_assets` table is empty; querying it returns a confident, entirely wrong answer.
- **Verify behaviour against the running container, not a local checkout.** Production runs `main-stable-260811 @ 83b8b99`, checked out nowhere on this box, and every local checkout carries the *fixed* `UID_RE`.

---

### Task 1: Amend the schema for the corrected rule key and stage 0 contracts

The existing `_schema.py` pins `RULE_KEY` to `assay_title`, which the spec has since inverted to `internal_assay_id`. This task makes that change and adds the stage 0 column contracts.

**Do NOT edit the existing `make_fixture()` data rows.** Tasks in the companion plan hand-trace counts off those exact rows (`n_both=2`, `n_child_only=1`, `propagation_rate=2/3`). Adding a *column* to the `assays` frame is safe because it changes no count. Stage 0 gets its own separate fixture.

**Files:**
- Modify: `scripts/assay_hygiene/_schema.py`
- Modify: `tests/test_assay_hygiene_schema.py`

**Interfaces:**
- Consumes: nothing
- Produces: `UID_RE_FIXED`, `UID_RE_PROD` (both `re.Pattern`); `PARENT_COLUMNS`, `CHILDOF_COLUMNS`, `EDGE_ROW_COLUMNS`, `STAGE0_PLAN_COLUMNS` (all `list[str]`); `RULE_KEY` changed to `["project_id", "child_type", "parent_type", "internal_assay_id"]`; `ASSAY_COLUMNS` gains `internal_assay_id` and `internal_assay_title`; drop-reason constants `D_NOT_UID`, `D_NO_NODE`, `D_SELF_LOOP`, `D_ALREADY_EXISTS` (all `str`); `make_stage0_fixture() -> dict[str, pandas.DataFrame]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_assay_hygiene_schema.py: REPLACE test_rule_key_is_title_not_assay_id
# with the two tests below, and APPEND the rest.

def test_rule_key_is_internal_assay_id():
    # 458 assay records collapse to 137 curated internal assays via
    # dmac.assays_internal_assays. assays.id is too fine (the same logical
    # assay is instantiated per study); assays.title is a different namespace
    # from DERIVED_FROM.internal_assay_title, so findings and edges would not
    # reconcile.
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type", "internal_assay_id"]
    assert "assay_title" not in S.RULE_KEY


def test_precedent_carries_internal_assay_title_for_display():
    assert "internal_assay_title" in S.PRECEDENT_COLUMNS


def test_prod_uid_regex_rejects_the_two_letter_antibody_type():
    # This is the production defect stage 0 works around. If this test ever
    # goes green-by-passing, production has been fixed and the override can go.
    assert S.UID_RE_PROD.match("AB-190703FOR-3") is None
    assert S.UID_RE_FIXED.match("AB-190703FOR-3") is not None


def test_both_regexes_agree_on_three_letter_types():
    for uid in ("TIS-190110SES-1", "D.ADNKA-190704FOR-98", "MUS-191201SAS-125"):
        assert S.UID_RE_PROD.match(uid) is not None
        assert S.UID_RE_FIXED.match(uid) is not None


def test_edge_row_columns_mirror_the_server_model():
    # nextseek_api/batch_upload/models.py:457 DerivedFromRelRow, extra="forbid".
    # A column stage 0 invents here is a field bulk_merge_relationships rejects.
    assert S.EDGE_ROW_COLUMNS == [
        "child_id", "child_uuid", "parent_id", "parent_uuid",
        "protocol_id", "protocol_title", "assay_id",
        "internal_assay_id", "internal_assay_title",
    ]


def test_drop_reasons_are_distinct():
    reasons = [S.D_NOT_UID, S.D_NO_NODE, S.D_SELF_LOOP, S.D_ALREADY_EXISTS]
    assert len(set(reasons)) == len(reasons)


def test_original_fixture_still_matches_the_widened_assay_contract():
    # ASSAY_COLUMNS grew by two; make_fixture() builds against that constant and
    # would raise if its rows were not widened to match.
    fx = S.make_fixture()
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS
    assert fx["assays"].iloc[0]["internal_assay_id"] == 11


def test_frozen_fixture_arithmetic_is_unaffected_by_the_new_column():
    # The companion plan hand-traces n_both=2 / n_child_only=1 off these rows.
    # Adding a column to `assays` must not disturb edges or membership.
    fx = S.make_fixture()
    assert len(fx["edges"]) == 6
    assert len(fx["membership"]) == 10


def test_stage0_fixture_covers_every_drop_reason_and_one_keeper():
    fx = S.make_stage0_fixture()
    parents = fx["parents"]
    # one token per drop reason, plus two that survive to be created
    assert len(parents) == 6
    assert set(parents.columns) == set(S.PARENT_COLUMNS)
    # exactly one token is AB-*, valid only under the corrected regex
    ab = [t for t in parents["token"] if t.startswith("AB-")]
    assert len(ab) == 1
    assert S.UID_RE_PROD.match(ab[0]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: FAIL. `test_rule_key_is_internal_assay_id` fails on the old value; the rest fail with `AttributeError: module 'assay_hygiene._schema' has no attribute 'UID_RE_PROD'`.

- [ ] **Step 3: Amend the schema**

```python
# scripts/assay_hygiene/_schema.py
# Add near the top, after `import pandas as pd`:
import re

# --- UID validation ----------------------------------------------------------
# Production (main-stable-260811 @ 83b8b99) requires a 3+ letter sample type
# code. Exactly one type in the database is shorter: AB, the antibody type.
# So every AntibodyParent reference is silently discarded before an edge is
# built, and all 874 AB parents have zero incoming DERIVED_FROM.
UID_RE_PROD = re.compile(r"^([AD]\.)?[A-Z]{3,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?$")

# The fix, already on dev-v4-merge. Stage 0 uses this one and reports the delta.
UID_RE_FIXED = re.compile(r"\A([A-Z]\.)?[A-Z]{2,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?\Z")
```

```python
# scripts/assay_hygiene/_schema.py
# REPLACE the ASSAY_COLUMNS / RULE_KEY / PRECEDENT_COLUMNS / FINDING_COLUMNS
# blocks with these. Everything else in the file is unchanged.

ASSAY_COLUMNS = [
    "assay_id", "title", "sample_type_id", "study_id",
    "investigation_id", "project_id", "project_title",
    # resolved through dmac.assays_internal_assays; NULL for the 17 records
    # with no junction row, which fall back to (assay_id, title) per
    # neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge)
    "internal_assay_id", "internal_assay_title",
]

# --- stage 0 (lineage backfill) ----------------------------------------------
PARENT_COLUMNS = ["child_uuid", "field", "token"]
CHILDOF_COLUMNS = ["child_uuid", "parent_uuid"]

# Mirrors nextseek_api/batch_upload/models.py:457 DerivedFromRelRow exactly.
# That model is extra="forbid", so an invented column is a hard rejection.
EDGE_ROW_COLUMNS = [
    "child_id", "child_uuid", "parent_id", "parent_uuid",
    "protocol_id", "protocol_title", "assay_id",
    "internal_assay_id", "internal_assay_title",
]
STAGE0_PLAN_COLUMNS = EDGE_ROW_COLUMNS + [
    "child_type", "parent_type", "field", "n_shared", "assay_source",
]

D_NOT_UID = "not_a_uid"
D_NO_NODE = "parent_not_a_node"
D_SELF_LOOP = "self_loop"
D_ALREADY_EXISTS = "already_has_derived_from"

# --- precedent (stage B) -----------------------------------------------------
RULE_KEY = ["project_id", "child_type", "parent_type", "internal_assay_id"]
PRECEDENT_COLUMNS = RULE_KEY + [
    "internal_assay_title",
    "n_both", "n_child_only", "n_parent_only",
    "propagation_rate", "reverse_rate",
]

# --- classify (stage C) ------------------------------------------------------
FINDING_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "verdict", "matched_internal_assay_id", "matched_internal_assay_title",
    "matched_rate", "target_assay_id", "project_id",
    # every internal_assay_id the child belongs to; stage D's tiebreak needs
    # this and cannot recover it later, because membership is not carried
    # into findings
    "candidates",
]
```

```python
# scripts/assay_hygiene/_schema.py
# REQUIRED: make_fixture() builds its assays frame with seven values against
# ASSAY_COLUMNS, which now has nine, so it raises unless this is updated too.
# Adding a COLUMN is safe under the fixture freeze; the companion plan's
# hand-traced counts (n_both=2, n_child_only=1, propagation_rate=2/3) all come
# from the edges and membership frames, which are untouched.
#
# REPLACE the assays frame inside make_fixture() with:
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
        ],
        columns=ASSAY_COLUMNS,
    )
```

```python
# scripts/assay_hygiene/_schema.py: APPEND at the end of the file.

def make_stage0_fixture() -> dict[str, pd.DataFrame]:
    """A synthetic world for stage 0, separate from make_fixture().

    make_fixture()'s rows are frozen because the companion plan hand-traces
    counts off them. Stage 0 needs different shapes (parent tokens, a node
    index, an AB-prefixed token), so it gets its own data rather than growing
    that one.

    parents: six declared tokens off three children, one per outcome
      D.IMG-1 / TIS-1        keeper, both endpoints share assay 1 -> labelled
      D.IMG-1 / AB-1         keeper, AB-prefixed, valid ONLY under the fix
      D.IMG-1 / not-a-uid    dropped, D_NOT_UID
      D.IMG-2 / TIS-9        dropped, D_NO_NODE (no such node)
      D.IMG-2 / D.IMG-2      dropped, D_SELF_LOOP
      D.IMG-3 / TIS-3        dropped, D_ALREADY_EXISTS
    """
    parents = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", "Parent", "TIS-260101ABC-1"),
            ("D.IMG-260101ABC-1", "AntibodyParent", "AB-260101ABC-1"),
            ("D.IMG-260101ABC-1", "Parent", "some free text"),
            ("D.IMG-260101ABC-2", "Parent", "TIS-260101ABC-9"),
            ("D.IMG-260101ABC-2", "Parent", "D.IMG-260101ABC-2"),
            ("D.IMG-260101ABC-3", "Parent", "TIS-260101ABC-3"),
        ],
        columns=PARENT_COLUMNS,
    )
    # the graph's node index: uuid -> (id, type). TIS-...-9 is deliberately absent.
    nodes = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", 100, "D.IMG"),
            ("D.IMG-260101ABC-2", 101, "D.IMG"),
            ("D.IMG-260101ABC-3", 102, "D.IMG"),
            ("TIS-260101ABC-1", 200, "TIS"),
            ("TIS-260101ABC-3", 202, "TIS"),
            ("AB-260101ABC-1", 300, "AB"),
        ],
        columns=["uuid", "sample_id", "type"],
    )
    # D.IMG-3 -> TIS-3 already exists, so it must be dropped as ALREADY_EXISTS
    existing = pd.DataFrame(
        [("D.IMG-260101ABC-3", "TIS-260101ABC-3")],
        columns=["child_uuid", "parent_uuid"],
    )
    membership = pd.DataFrame(
        [
            (100, 1), (200, 1),   # D.IMG-1 and TIS-1 share assay 1 -> labelled
            (300, 2),             # AB-1 is in assay 2 only -> disjoint, dark
        ],
        columns=MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (2, "Antibody Panel", 8, 3, 2, 10, "MIT_SRP", None, None),
        ],
        columns=ASSAY_COLUMNS,
    )
    samples = pd.DataFrame(
        [
            (100, "D.IMG-260101ABC-1",
             '{"Protocol": "http://x/sops/5", "Parent": "TIS-260101ABC-1"}', None, "10"),
            (101, "D.IMG-260101ABC-2", '{"Protocol": ""}', None, "10"),
            (102, "D.IMG-260101ABC-3", '{"Protocol": "http://x/sops/5"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
    sops = pd.DataFrame([(5, "Comet Chip SOP")], columns=["sop_id", "title"])
    childof = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
            # declared by nobody: the stale case reconciliation must surface
            ("D.IMG-260101ABC-1", "TIS-260101ABC-77"),
        ],
        columns=CHILDOF_COLUMNS,
    )
    return {
        "parents": parents, "nodes": nodes, "existing": existing,
        "membership": membership, "assays": assays, "samples": samples,
        "sops": sops, "childof": childof,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/ -q`
Expected: PASS. Baseline was 609 passed / 12 skipped. This task adds 9 tests and replaces 1, so expect **617 passed / 12 skipped**. If the count differs, stop and reconcile before continuing rather than adjusting the expectation to match.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/_schema.py tests/test_assay_hygiene_schema.py
git commit -m "feat(assay-hygiene): internal_assay_id rule key + stage 0 contracts"
```

---

### Task 2: Stage 0 planner, deciding which references become edges

Pure function. No database, no properties yet: this task only answers "which declared parent references need an edge, and why was each of the others excluded".

**Files:**
- Create: `scripts/assay_hygiene/stage0.py`
- Test: `tests/test_assay_hygiene_stage0.py`

**Interfaces:**
- Consumes: `_schema.PARENT_COLUMNS`, `_schema.UID_RE_FIXED`, `_schema.UID_RE_PROD`, `_schema.D_NOT_UID`, `_schema.D_NO_NODE`, `_schema.D_SELF_LOOP`, `_schema.D_ALREADY_EXISTS`, `_schema.make_stage0_fixture`
- Produces: `plan_edges(parents, nodes, existing) -> tuple[pandas.DataFrame, dict[str, int]]`. The DataFrame has columns `["child_uuid", "parent_uuid", "child_id", "parent_id", "child_type", "parent_type", "field"]`, one row per edge to create. The dict maps each drop-reason constant to a count, plus the key `"prod_regex_would_reject"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_stage0.py
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import stage0


def test_planner_keeps_only_creatable_references():
    fx = S.make_stage0_fixture()
    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    pairs = set(zip(plan["child_uuid"], plan["parent_uuid"]))
    assert pairs == {
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
        ("D.IMG-260101ABC-1", "AB-260101ABC-1"),
    }


def test_planner_counts_every_exclusion_by_reason():
    fx = S.make_stage0_fixture()
    _, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert residues[S.D_NOT_UID] == 1
    assert residues[S.D_NO_NODE] == 1
    assert residues[S.D_SELF_LOOP] == 1
    assert residues[S.D_ALREADY_EXISTS] == 1


def test_planner_reports_what_the_production_regex_would_have_dropped():
    # The whole point of the override: without it the AB edge never exists.
    fx = S.make_stage0_fixture()
    _, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    assert residues["prod_regex_would_reject"] == 1


def test_planner_resolves_ids_and_types_from_the_node_index():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    row = plan[plan["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert row["child_id"] == 100
    assert row["parent_id"] == 300
    assert row["child_type"] == "D.IMG"
    assert row["parent_type"] == "AB"
    assert row["field"] == "AntibodyParent"


def test_planner_is_idempotent_against_its_own_output():
    # Re-running after a successful write must plan nothing.
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    import pandas as pd
    now_existing = pd.concat([
        fx["existing"],
        plan[["child_uuid", "parent_uuid"]],
    ], ignore_index=True)
    plan2, residues2 = stage0.plan_edges(fx["parents"], fx["nodes"], now_existing)
    assert len(plan2) == 0
    assert residues2[S.D_ALREADY_EXISTS] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: FAIL with `ImportError: cannot import name 'stage0'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/stage0.py
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

    Returns (plan, residues). Every excluded reference is counted in residues,
    so the row count of `parents` is fully accounted for.
    """
    residues = {
        S.D_NOT_UID: 0,
        S.D_NO_NODE: 0,
        S.D_SELF_LOOP: 0,
        S.D_ALREADY_EXISTS: 0,
        "prod_regex_would_reject": 0,
    }

    node_id = dict(zip(nodes["uuid"], nodes["sample_id"]))
    node_type = dict(zip(nodes["uuid"], nodes["type"]))
    have = set(zip(existing["child_uuid"], existing["parent_uuid"]))

    kept: list[tuple] = []
    seen: set[tuple[str, str]] = set()

    for child_uuid, field, token in parents.itertuples(index=False):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/stage0.py tests/test_assay_hygiene_stage0.py
git commit -m "feat(assay-hygiene): stage 0 planner with per-reason drop accounting"
```

---

### Task 3: Stage 0 edge properties, mirroring the server exactly

Computes what each new edge carries. This must reproduce `_build_derived_from_payloads` (`neo4j_sync.py:888-1098`) rather than improve on it, so a stage 0 edge is indistinguishable from a pipeline-produced one.

**Files:**
- Modify: `scripts/assay_hygiene/stage0.py`
- Modify: `tests/test_assay_hygiene_stage0.py`

**Interfaces:**
- Consumes: `plan_edges` output; `_schema.EDGE_ROW_COLUMNS`, `_schema.STAGE0_PLAN_COLUMNS`
- Produces: `resolve_properties(plan, samples, membership, assays, sops) -> pandas.DataFrame` with columns `_schema.STAGE0_PLAN_COLUMNS`. `SOP_URL_RE` (a `re.Pattern`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_stage0.py: APPEND

def _resolved():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    return stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )


def test_shared_assay_is_stamped_when_both_endpoints_are_registered():
    out = _resolved()
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["assay_id"] == 1
    assert row["internal_assay_id"] == 11
    assert row["internal_assay_title"] == "Comet Chip"
    assert row["n_shared"] == 1
    assert row["assay_source"] == "junction"


def test_disjoint_endpoints_produce_a_dark_edge_rather_than_a_guess():
    # The AB parent is in assay 2, the child in assay 1. Stage 0 infers nothing;
    # the edge is created dark and stages A-F deal with it.
    out = _resolved()
    row = out[out["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert pd.isna(row["assay_id"])
    assert pd.isna(row["internal_assay_id"])
    assert row["n_shared"] == 0
    assert row["assay_source"] == "none"


def test_protocol_is_extracted_from_the_child_and_titled_from_sops():
    out = _resolved()
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["protocol_id"] == 5
    assert row["protocol_title"] == "Comet Chip SOP"


def test_output_carries_exactly_the_server_model_fields_plus_reporting_columns():
    out = _resolved()
    assert list(out.columns) == S.STAGE0_PLAN_COLUMNS
    # the first nine must match DerivedFromRelRow in order, because the applier
    # slices them straight into the payload
    assert list(out.columns)[:9] == S.EDGE_ROW_COLUMNS


def test_assay_with_no_junction_row_falls_back_to_assay_id_and_title():
    # neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge). 17 of 458 production assays have no junction row;
    # the server does NOT skip them, it uses (assay_id, assays.title).
    fx = S.make_stage0_fixture()
    # put BOTH endpoints of the AB edge in assay 2, which has no junction row
    membership = pd.concat([
        fx["membership"],
        pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS),
    ], ignore_index=True)
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan, fx["samples"], membership, fx["assays"], fx["sops"]
    )
    row = out[out["parent_uuid"] == "AB-260101ABC-1"].iloc[0]
    assert row["assay_id"] == 2
    assert row["internal_assay_id"] == 2
    assert row["internal_assay_title"] == "Antibody Panel"
    assert row["assay_source"] == "fallback"


def test_multiple_shared_assays_pick_the_minimum_internal_assay_id():
    # neo4j_sync.py:1064-1078. Arbitrary but deterministic; stage 0 reproduces
    # it and reports the count so a curator can settle those edges by hand.
    fx = S.make_stage0_fixture()
    assays = pd.concat([
        fx["assays"],
        pd.DataFrame([(3, "Other", 9, 3, 2, 10, "MIT_SRP", 4, "Other")],
                     columns=S.ASSAY_COLUMNS),
    ], ignore_index=True)
    membership = pd.concat([
        fx["membership"],
        pd.DataFrame([(100, 3), (200, 3)], columns=S.MEMBERSHIP_COLUMNS),
    ], ignore_index=True)
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    out = stage0.resolve_properties(
        plan, fx["samples"], membership, assays, fx["sops"]
    )
    row = out[out["parent_uuid"] == "TIS-260101ABC-1"].iloc[0]
    assert row["n_shared"] == 2
    assert row["internal_assay_id"] == 4      # min(11, 4)
    assert row["assay_id"] == 3               # the assay that carried it
```

Add `import pandas as pd` to the top of the test file if it is not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: FAIL with `AttributeError: module 'assay_hygiene.stage0' has no attribute 'resolve_properties'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/stage0.py: APPEND (and add `import re` at the top)

# Matches the server's protocol extraction: the Protocol metadata value is a
# SOP URL and the trailing integer is the sops.id.
SOP_URL_RE = re.compile(r"/sops/(\d+)")


def resolve_properties(
    plan: pd.DataFrame,
    samples: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    sops: pd.DataFrame,
) -> pd.DataFrame:
    """Compute each new edge's properties exactly as the server would.

    Mirrors nextseek_api/batch_upload/neo4j_sync.py:888-1098. Deliberately does
    not improve on two behaviours:
      - when several assays are shared, the minimum internal_assay_id wins
      - an assay with no junction row falls back to (assay_id, assays.title)
    """
    import json

    meta_by_id: dict[int, dict] = {}
    for sid, _uuid, jmeta, _created, _projects in samples.itertuples(index=False):
        try:
            parsed = json.loads(jmeta) if jmeta else {}
        except (ValueError, TypeError):
            parsed = {}
        meta_by_id[sid] = parsed if isinstance(parsed, dict) else {}

    sop_title = dict(zip(sops["sop_id"], sops["title"]))

    assays_by_sample: dict[int, set[int]] = {}
    for sid, aid in membership.itertuples(index=False):
        assays_by_sample.setdefault(sid, set()).add(aid)

    # assay_id -> (internal_assay_id, internal_assay_title, source)
    resolved_assay: dict[int, tuple[int, str, str]] = {}
    for row in assays.itertuples(index=False):
        if pd.notna(row.internal_assay_id):
            resolved_assay[row.assay_id] = (
                int(row.internal_assay_id), row.internal_assay_title, "junction",
            )
        else:
            resolved_assay[row.assay_id] = (row.assay_id, row.title, "fallback")

    out: list[tuple] = []
    for r in plan.itertuples(index=False):
        meta = meta_by_id.get(r.child_id, {})
        protocol_val = meta.get("Protocol") or meta.get("protocol") or ""
        m = SOP_URL_RE.search(str(protocol_val))
        protocol_id = int(m.group(1)) if m else None
        protocol_title = sop_title.get(protocol_id) if protocol_id else None

        shared = assays_by_sample.get(r.child_id, set()) & assays_by_sample.get(r.parent_id, set())
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
            if best is not None:
                internal_id, internal_title, source, assay_id = best

        out.append((
            r.child_id, r.child_uuid, r.parent_id, r.parent_uuid,
            protocol_id, protocol_title, assay_id,
            internal_id, internal_title,
            r.child_type, r.parent_type, r.field, len(shared), source,
        ))

    return pd.DataFrame(out, columns=S.STAGE0_PLAN_COLUMNS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/stage0.py tests/test_assay_hygiene_stage0.py
git commit -m "feat(assay-hygiene): stage 0 edge properties mirroring the server rules"
```

---

### Task 4: The dry-run report and the CHILD_OF reconciliation

The report is the gate. The operator reads it and then runs the write, so anything not in it is invisible.

**Files:**
- Modify: `scripts/assay_hygiene/stage0.py`
- Modify: `tests/test_assay_hygiene_stage0.py`

**Interfaces:**
- Consumes: `resolve_properties` output, `plan_edges` residues
- Produces: `build_report(resolved, residues, childof_unmatched) -> str` (markdown); `reconcile_childof(childof, parents) -> pandas.DataFrame` with columns `["child_uuid", "parent_uuid", "reason"]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_stage0.py: APPEND

def test_reconciliation_surfaces_childof_edges_metadata_no_longer_declares():
    fx = S.make_stage0_fixture()
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    pairs = set(zip(recon["child_uuid"], recon["parent_uuid"]))
    assert pairs == {("D.IMG-260101ABC-1", "TIS-260101ABC-77")}
    assert recon.iloc[0]["reason"] == "not_declared_by_metadata"


def test_reconciliation_never_proposes_an_action():
    # Operator ruling 2026-08-13: CHILD_OF is left alone. This file is a report.
    fx = S.make_stage0_fixture()
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    assert list(recon.columns) == ["child_uuid", "parent_uuid", "reason"]


def test_report_states_every_residue_and_the_regex_override():
    fx = S.make_stage0_fixture()
    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    resolved = stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    report = stage0.build_report(resolved, residues, recon)

    assert "2 edges to create" in report
    # per-reason accounting, so nothing is dropped silently
    for reason in (S.D_NOT_UID, S.D_NO_NODE, S.D_SELF_LOOP, S.D_ALREADY_EXISTS):
        assert reason in report
    # the override must be stated, not buried
    assert "prod_regex_would_reject" in report or "production regex" in report.lower()
    # labelled vs dark split
    assert "1 labelled" in report and "1 dark" in report
    # the tiebreak count is a standing regression guard
    assert "min-internal_assay_id tiebreak" in report
    # reconciliation is reported but not actioned
    assert "1" in report and "CHILD_OF" in report


def test_report_lists_hops_so_a_reviewer_can_spot_an_unexpected_one():
    fx = S.make_stage0_fixture()
    plan, residues = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    resolved = stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )
    recon = stage0.reconcile_childof(fx["childof"], fx["parents"])
    report = stage0.build_report(resolved, residues, recon)
    assert "D.IMG -> TIS" in report
    assert "D.IMG -> AB" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: FAIL with `AttributeError: module 'assay_hygiene.stage0' has no attribute 'reconcile_childof'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/stage0.py: APPEND

def reconcile_childof(childof: pd.DataFrame, parents: pd.DataFrame) -> pd.DataFrame:
    """CHILD_OF edges the child's CURRENT metadata no longer declares.

    Reported only. Operator ruling 2026-08-13: CHILD_OF is never written,
    modified or deleted by this pipeline, so this frame carries no action
    column by design.
    """
    declared = set(zip(parents["child_uuid"], parents["token"]))
    rows = [
        (c, p, "not_declared_by_metadata")
        for c, p in zip(childof["child_uuid"], childof["parent_uuid"])
        if (c, p) not in declared
    ]
    return pd.DataFrame(rows, columns=["child_uuid", "parent_uuid", "reason"])


def build_report(
    resolved: pd.DataFrame,
    residues: dict[str, int],
    childof_unmatched: pd.DataFrame,
) -> str:
    """The markdown an operator reads before authorising the write."""
    total = len(resolved)
    labelled = int(resolved["internal_assay_id"].notna().sum())
    dark = total - labelled
    tiebreak = int((resolved["n_shared"] > 1).sum())
    fallback = int((resolved["assay_source"] == "fallback").sum())
    no_protocol = int(resolved["protocol_id"].isna().sum())

    lines = [
        "# Stage 0 dry run: complete the lineage graph",
        "",
        f"**{total} edges to create.** {labelled} labelled, {dark} dark.",
        "",
        "Stage 0 writes only Neo4j DERIVED_FROM relationships. It does not touch",
        "MySQL, assay_assets, or CHILD_OF, and it cannot delete.",
        "",
        "## Excluded references, by reason",
        "",
        "| Reason | Count |",
        "|---|---|",
    ]
    for key in (S.D_NOT_UID, S.D_NO_NODE, S.D_SELF_LOOP, S.D_ALREADY_EXISTS):
        lines.append(f"| `{key}` | {residues.get(key, 0):,} |")
    lines += [
        "",
        "## Production regex override",
        "",
        f"`prod_regex_would_reject`: **{residues.get('prod_regex_would_reject', 0):,}** "
        "references are valid UIDs that the live server's UID_RE rejects, because",
        "its `[A-Z]{3,}` excludes the two-letter `AB` sample type. Stage 0 includes",
        "them. Until the fix ships to production, every new upload regenerates",
        "this gap.",
        "",
        "## Assay resolution",
        "",
        f"- edges resting on the min-internal_assay_id tiebreak: **{tiebreak:,}**",
        f"- edges whose assay had no junction row (fallback path): **{fallback:,}**",
        f"- edges whose child carries no resolvable Protocol: **{no_protocol:,}**",
        "",
        "## Hops",
        "",
        "| Hop | Edges | Labelled |",
        "|---|---|---|",
    ]
    grouped = resolved.groupby(["child_type", "parent_type"], dropna=False)
    counts = grouped.size().sort_values(ascending=False)
    for (ct, pt), n in counts.items():
        sub = resolved[(resolved["child_type"] == ct) & (resolved["parent_type"] == pt)]
        lines.append(f"| {ct} -> {pt} | {n:,} | {int(sub['internal_assay_id'].notna().sum()):,} |")

    lines += [
        "",
        "## CHILD_OF reconciliation",
        "",
        f"**{len(childof_unmatched):,}** CHILD_OF edges are not declared by the",
        "child's current metadata. Reported for curation. Nothing acts on them.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0.py -v`
Expected: PASS, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/stage0.py tests/test_assay_hygiene_stage0.py
git commit -m "feat(assay-hygiene): stage 0 dry-run report and CHILD_OF reconciliation"
```

---

### Task 5: Stage A extractor, run read-only inside the production container

**Files:**
- Create: `scripts/assay_hygiene/extract.py`
- Create: `scripts/assay_hygiene/driver_extract.py`
- Test: `tests/test_assay_hygiene_extract.py`

**Interfaces:**
- Consumes: `_schema` column contracts
- Produces: `EDGES_CYPHER`, `CHILDOF_CYPHER`, `NODES_CYPHER` (all `str`); `MEMBERSHIP_SQL`, `ASSAYS_SQL`, `SAMPLES_SQL`, `SOPS_SQL` (all `str`); `build_parents(samples_rows, collect_fn) -> pandas.DataFrame`; `main(outdir="/tmp/assay-hygiene-extract") -> None`

This task cannot run its own live extraction as part of the test cycle. The tests assert the query text and the pure `build_parents` transform; the live run is step 6 and is verified by row counts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_extract.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import extract


def test_assays_sql_joins_project_through_the_junction_table():
    # `investigations` has NO project_id column; the link is
    # investigations_projects. Getting this wrong yields an empty frame.
    assert "investigations_projects" in extract.ASSAYS_SQL
    assert "i.project_id" not in extract.ASSAYS_SQL


def test_assays_sql_resolves_internal_assay_via_the_dmac_junction():
    # The rule key is internal_assay_id, so the extract must carry it.
    assert "assays_internal_assays" in extract.ASSAYS_SQL
    assert "internal_assays" in extract.ASSAYS_SQL
    assert "LEFT JOIN" in extract.ASSAYS_SQL.upper()  # 17 assays have no row


def test_membership_sql_reads_the_seek_schema_not_dmac():
    assert "assay_assets" in extract.MEMBERSHIP_SQL
    assert "asset_type" in extract.MEMBERSHIP_SQL


def test_childof_cypher_reads_but_never_writes():
    for forbidden in ("MERGE", "CREATE", "DELETE", "SET "):
        assert forbidden not in extract.CHILDOF_CYPHER.upper()


def test_build_parents_uses_the_injected_server_helper():
    # The point of injection: key matching and semicolon splitting are the
    # server's, never reimplemented here.
    calls = []

    def fake_collect(meta):
        calls.append(meta)
        return ["TIS-260101ABC-1", "AB-260101ABC-1"]

    rows = [("D.IMG-260101ABC-1", '{"Parent": "TIS-260101ABC-1"}')]
    out = extract.build_parents(rows, fake_collect)
    assert calls == [{"Parent": "TIS-260101ABC-1"}]
    assert list(out.columns) == S.PARENT_COLUMNS
    assert set(out["token"]) == {"TIS-260101ABC-1", "AB-260101ABC-1"}


def test_build_parents_records_which_field_each_token_came_from():
    def fake_collect(meta):
        return ["TIS-260101ABC-1", "AB-260101ABC-1"]

    rows = [(
        "D.IMG-260101ABC-1",
        '{"Parent": "TIS-260101ABC-1", "AntibodyParent": "AB-260101ABC-1"}',
    )]
    out = extract.build_parents(rows, fake_collect)
    got = dict(zip(out["token"], out["field"]))
    assert got["TIS-260101ABC-1"] == "Parent"
    assert got["AB-260101ABC-1"] == "AntibodyParent"


def test_build_parents_survives_unparseable_metadata():
    def fake_collect(meta):
        return []

    out = extract.build_parents([("X-260101ABC-1", "not json")], fake_collect)
    assert len(out) == 0
    assert list(out.columns) == S.PARENT_COLUMNS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_extract.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract'`.

- [ ] **Step 3: Write the extractor**

```python
# scripts/assay_hygiene/extract.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=15"]
# ///
"""Stage A: read-only extract, run INSIDE the production nextseek container.

Runs under `manage.py shell` so it inherits the configured `seek` connection
and NEO4J_DATABASE settings. No credential is ever read, passed or stored here.

The correct Django alias is `seek` (seek_production). The `default` alias is
`dmac`, whose assay_assets table EXISTS but is EMPTY.
"""
from __future__ import annotations

import json

import pandas as pd

from . import _schema as S

EDGES_CYPHER = """
MATCH (c:Sample)-[r:DERIVED_FROM]->(p:Sample)
RETURN c.id AS child_id, p.id AS parent_id,
       c.uuid AS child_uuid, p.uuid AS parent_uuid,
       c.type AS child_type, p.type AS parent_type,
       r.internal_assay_id AS edge_assay_id,
       r.internal_assay_title AS edge_assay_title,
       r.protocol_id AS edge_protocol_id
"""

CHILDOF_CYPHER = """
MATCH (c:Sample)-[:CHILD_OF]->(p:Sample)
RETURN c.uuid AS child_uuid, p.uuid AS parent_uuid
"""

NODES_CYPHER = """
MATCH (s:Sample)
RETURN s.uuid AS uuid, s.id AS sample_id, s.type AS type
"""

MEMBERSHIP_SQL = """
SELECT asset_id AS sample_id, assay_id
FROM assay_assets WHERE asset_type = 'Sample'
"""

# `investigations` has no project_id; the link is investigations_projects.
# internal_assay_id is LEFT JOINed because 17 of 458 assays have no junction row.
ASSAYS_SQL = """
SELECT a.id AS assay_id, a.title, a.sample_type_id, a.study_id,
       i.id AS investigation_id, ip.project_id, p.title AS project_title,
       ia.id AS internal_assay_id, ia.internal_assay_title
FROM assays a
JOIN studies s              ON s.id  = a.study_id
JOIN investigations i       ON i.id  = s.investigation_id
JOIN investigations_projects ip ON ip.investigation_id = i.id
JOIN projects p             ON p.id  = ip.project_id
LEFT JOIN {dmac}.assays_internal_assays aia ON aia.assay_id = a.id
LEFT JOIN {dmac}.internal_assays ia         ON ia.id = aia.internal_assay_id
"""

SAMPLES_SQL = """
SELECT s.id AS sample_id, s.uuid, s.json_metadata, s.created_at,
       GROUP_CONCAT(ps.project_id) AS project_ids
FROM samples s
LEFT JOIN projects_samples ps ON ps.sample_id = s.id
GROUP BY s.id
"""

SOPS_SQL = "SELECT id AS sop_id, title FROM sops"


def build_parents(samples_rows, collect_fn) -> pd.DataFrame:
    """One row per declared parent token.

    `collect_fn` is the SERVER's collect_parent_tokens, injected rather than
    reimplemented, so key matching and semicolon splitting cannot drift.
    UID validation is deliberately NOT done here: stage 0 applies the corrected
    regex on the laptop, and the raw token must survive to be reported.
    """
    out: list[tuple[str, str, str]] = []
    for child_uuid, jmeta in samples_rows:
        try:
            meta = json.loads(jmeta) if jmeta else {}
        except (ValueError, TypeError):
            continue
        if not isinstance(meta, dict):
            continue
        tokens = collect_fn(meta)
        if not tokens:
            continue
        # attribute each token back to the field that produced it
        origin: dict[str, str] = {}
        for key, value in meta.items():
            if "parent" not in key.lower() or not isinstance(value, str):
                continue
            for part in value.split(";"):
                part = part.strip()
                if part and part not in origin:
                    origin[part] = key
        for token in tokens:
            out.append((child_uuid, origin.get(token, "Parent"), token))
    return pd.DataFrame(out, columns=S.PARENT_COLUMNS)


def main(outdir: str = "/tmp/assay-hygiene-extract") -> None:
    """Write every extract to `outdir` as parquet. Read-only against production."""
    import pathlib

    from django.conf import settings
    from django.db import connections
    from neo4j import GraphDatabase

    from nextseek_api.batch_upload.helpers import collect_parent_tokens

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    dmac = settings.DATABASES[settings.NEXTSEEK_DATABASE]["NAME"]
    nd = settings.NEO4J_DATABASE
    db = nd.get("NAME") or "neo4j"
    driver = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])

    def cypher(q):
        recs, _, _ = driver.execute_query(q, {}, database_=db)
        return pd.DataFrame([dict(r) for r in recs])

    def sql(q):
        with connections["seek"].cursor() as cur:
            cur.execute(q)
            cols = [c[0] for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)

    frames = {
        "edges": cypher(EDGES_CYPHER),
        "childof": cypher(CHILDOF_CYPHER),
        "nodes": cypher(NODES_CYPHER),
        "membership": sql(MEMBERSHIP_SQL),
        "assays": sql(ASSAYS_SQL.format(dmac=dmac)),
        "samples": sql(SAMPLES_SQL),
        "sops": sql(SOPS_SQL),
    }
    frames["parents"] = build_parents(
        list(zip(frames["samples"]["uuid"], frames["samples"]["json_metadata"])),
        collect_parent_tokens,
    )
    driver.close()

    for name, df in frames.items():
        df.to_parquet(out / f"{name}.parquet", compression="zstd", index=False)
        print(f"{name:<12} {len(df):>10,} rows")
```

```python
# scripts/assay_hygiene/driver_extract.py
"""Piped into `manage.py shell` on the box. Kept short on purpose.

extract.py uses a relative import, so piping IT into the shell executes it
without package context and the import raises. And nesting the invocation
inside `ssh ... bash -lc "python -c \\"...\\""` will not survive ssh's arg
joining plus the remote shell's re-parse. Copy the package, pipe this.
"""
import sys

sys.path.insert(0, "/tmp/scripts")
from assay_hygiene import extract  # noqa: E402

extract.main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_extract.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/extract.py scripts/assay_hygiene/driver_extract.py tests/test_assay_hygiene_extract.py
git commit -m "feat(assay-hygiene): stage A extractor with server-injected parent tokens"
```

- [ ] **Step 6: Run the live extraction (read-only) and check the row counts**

```bash
scp -r ./scripts/assay_hygiene fairdata:/tmp/
ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < scripts/assay_hygiene/driver_extract.py
ssh fairdata 'docker cp nextseek:/tmp/assay-hygiene-extract /tmp/assay-hygiene-extract'
mkdir -p assay-hygiene && scp -r fairdata:/tmp/assay-hygiene-extract assay-hygiene/extract
```

Expected row counts, measured on production 2026-08-13. Any material deviation means stop and investigate rather than proceed:

```
edges          704,059
childof        742,534
nodes          163,393   (approximately; every Sample node)
membership     214,489
assays             458   (rows may exceed 458 if an assay maps to several projects)
samples        163,393
sops               553
parents        797,435   tokens
```

- [ ] **Step 7: Commit nothing, and confirm the extract is gitignored**

```bash
git status --short
```
Expected: `assay-hygiene/` does not appear. It holds `json_metadata` for every sample and must never be committed. If it appears, add it to `.gitignore` and commit only that change.

---

### Task 6: Stage 0 applier, manifest, and rollback

The applier is deliberately duck-typed over a `driver` object so the whole write path is unit-testable with a fake. The real Neo4j driver is bound only in the thin in-container script.

**Files:**
- Create: `scripts/assay_hygiene/stage0_apply.py`
- Create: `scripts/assay_hygiene/driver_stage0.py`
- Test: `tests/test_assay_hygiene_stage0_apply.py`

**Interfaces:**
- Consumes: `resolve_properties` output (columns `_schema.STAGE0_PLAN_COLUMNS`)
- Produces: `MERGE_CYPHER`, `ROLLBACK_CYPHER` (both `str`); `to_payload(resolved) -> list[dict]`; `apply_edges(driver, db_name, resolved, dry_run=True, chunk_size=20_000) -> list[dict]`; `rollback(driver, db_name, manifest_rows, chunk_size=20_000) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_stage0_apply.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import stage0, stage0_apply


class FakeDriver:
    """Records every call instead of touching a database."""

    def __init__(self):
        self.calls = []

    def execute_query(self, cypher, params=None, database_=None):
        self.calls.append((cypher, params, database_))
        return None


def _resolved():
    fx = S.make_stage0_fixture()
    plan, _ = stage0.plan_edges(fx["parents"], fx["nodes"], fx["existing"])
    return stage0.resolve_properties(
        plan, fx["samples"], fx["membership"], fx["assays"], fx["sops"]
    )


def test_dry_run_is_the_default_and_issues_no_query():
    driver = FakeDriver()
    manifest = stage0_apply.apply_edges(driver, "neo4j", _resolved())
    assert driver.calls == []
    assert len(manifest) == 2   # the manifest is still produced for review


def test_write_requires_an_explicit_flag():
    driver = FakeDriver()
    stage0_apply.apply_edges(driver, "neo4j", _resolved(), dry_run=False)
    assert len(driver.calls) == 1


def test_payload_carries_only_the_server_model_fields():
    # DerivedFromRelRow is extra="forbid"; a reporting column leaking into the
    # payload is a hard rejection at the server.
    payload = stage0_apply.to_payload(_resolved())
    assert set(payload[0].keys()) == set(S.EDGE_ROW_COLUMNS)
    for extra in ("child_type", "parent_type", "field", "n_shared", "assay_source"):
        assert extra not in payload[0]


def test_dark_edges_carry_python_None_not_nan():
    # A dark edge's assay fields make those columns float64, so a naive
    # `.where(notna, None)` leaves NaN behind and the driver writes a float
    # rather than a null.
    payload = stage0_apply.to_payload(_resolved())
    dark = [r for r in payload if r["parent_uuid"] == "AB-260101ABC-1"][0]
    assert dark["assay_id"] is None
    assert dark["internal_assay_id"] is None
    assert dark["internal_assay_title"] is None


def test_the_write_is_a_merge_and_can_never_delete():
    for forbidden in ("DELETE", "DETACH", "REMOVE"):
        assert forbidden not in stage0_apply.MERGE_CYPHER.upper()
    assert "MERGE" in stage0_apply.MERGE_CYPHER.upper()


def test_the_write_never_touches_child_of():
    # Operator ruling 2026-08-13.
    assert "CHILD_OF" not in stage0_apply.MERGE_CYPHER.upper()
    assert "CHILD_OF" not in stage0_apply.ROLLBACK_CYPHER.upper()


def test_created_edges_carry_no_marker_property():
    # A marker would make stage 0 edges distinguishable from pipeline-produced
    # ones and would leak into every downstream query. The manifest is the record.
    payload = stage0_apply.to_payload(_resolved())
    for key in payload[0]:
        assert "backfill" not in key.lower()
        assert "stage0" not in key.lower()


def test_manifest_records_one_line_per_edge_with_full_properties():
    manifest = stage0_apply.apply_edges(FakeDriver(), "neo4j", _resolved(), dry_run=False)
    assert len(manifest) == 2
    for row in manifest:
        assert set(S.EDGE_ROW_COLUMNS) <= set(row.keys())


def test_rollback_targets_exactly_the_manifest_pairs():
    driver = FakeDriver()
    manifest = stage0_apply.apply_edges(FakeDriver(), "neo4j", _resolved(), dry_run=False)
    n = stage0_apply.rollback(driver, "neo4j", manifest)
    assert n == 2
    _cypher, params, _db = driver.calls[0]
    pairs = {(r["child_uuid"], r["parent_uuid"]) for r in params["rows"]}
    assert pairs == {
        ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
        ("D.IMG-260101ABC-1", "AB-260101ABC-1"),
    }


def test_rollback_deletes_only_derived_from():
    assert "DERIVED_FROM" in stage0_apply.ROLLBACK_CYPHER
    assert "DELETE" in stage0_apply.ROLLBACK_CYPHER.upper()


def test_apply_refuses_a_frame_with_unexpected_columns():
    bad = _resolved().drop(columns=["assay_source"])
    with pytest.raises(ValueError, match="columns"):
        stage0_apply.apply_edges(FakeDriver(), "neo4j", bad, dry_run=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0_apply.py -v`
Expected: FAIL with `ImportError: cannot import name 'stage0_apply'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/stage0_apply.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage 0 write path: MERGE DERIVED_FROM, record a manifest, support rollback.

Mirrors neo4j_sync.bulk_merge_relationships (neo4j_sync.py:157). The driver is
duck-typed so the whole path is unit-testable with a fake; the real Neo4j
driver is bound only in driver_stage0.py.

This module cannot delete anything except via `rollback`, which targets exactly
the pairs in a manifest produced by a prior run.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S

MERGE_CYPHER = """
UNWIND $rows AS row
MATCH (c:Sample {uuid: row.child_uuid})
MATCH (p:Sample {uuid: row.parent_uuid})
MERGE (c)-[r:DERIVED_FROM]->(p)
SET r.protocol_id = row.protocol_id, r.protocol_title = row.protocol_title,
    r.assay_id = row.assay_id,
    r.internal_assay_id = row.internal_assay_id,
    r.internal_assay_title = row.internal_assay_title,
    r.child_id = row.child_id, r.parent_id = row.parent_id
RETURN count(r) AS processed
"""

ROLLBACK_CYPHER = """
UNWIND $rows AS row
MATCH (c:Sample {uuid: row.child_uuid})-[r:DERIVED_FROM]->(p:Sample {uuid: row.parent_uuid})
DELETE r
RETURN count(*) AS removed
"""


def to_payload(resolved: pd.DataFrame) -> list[dict]:
    """Slice the plan down to exactly DerivedFromRelRow's fields.

    That model is extra="forbid", so a reporting column reaching the server is
    a hard rejection.
    """
    frame = resolved[S.EDGE_ROW_COLUMNS]
    # astype(object) first: on a float column `.where(..., None)` leaves NaN in
    # place, and a NaN reaching the Neo4j driver is not the same as a null
    # property. Every optional field here (protocol_id, assay_id,
    # internal_assay_id) is float64 the moment one row is dark.
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def apply_edges(
    driver,
    db_name: str,
    resolved: pd.DataFrame,
    dry_run: bool = True,
    chunk_size: int = 20_000,
) -> list[dict]:
    """MERGE every planned edge. Dry run by default; `dry_run=False` is explicit.

    Returns the manifest: one dict per edge, written whether or not the run
    touched the database, so a dry run is reviewable.
    """
    if list(resolved.columns) != S.STAGE0_PLAN_COLUMNS:
        raise ValueError(
            f"unexpected columns: {list(resolved.columns)} != {S.STAGE0_PLAN_COLUMNS}"
        )
    payload = to_payload(resolved)
    if dry_run:
        return payload
    for i in range(0, len(payload), chunk_size):
        driver.execute_query(
            MERGE_CYPHER, {"rows": payload[i : i + chunk_size]}, database_=db_name
        )
    return payload


def rollback(driver, db_name: str, manifest_rows: list[dict], chunk_size: int = 20_000) -> int:
    """Delete exactly the DERIVED_FROM edges a manifest records creating."""
    pairs = [
        {"child_uuid": r["child_uuid"], "parent_uuid": r["parent_uuid"]}
        for r in manifest_rows
    ]
    for i in range(0, len(pairs), chunk_size):
        driver.execute_query(
            ROLLBACK_CYPHER, {"rows": pairs[i : i + chunk_size]}, database_=db_name
        )
    return len(pairs)
```

```python
# scripts/assay_hygiene/driver_stage0.py
"""Piped into `manage.py shell` on the box to perform the stage 0 write.

Reads a manifest written by the laptop. Contains no logic: every decision was
made and reviewed before this runs.

    ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < driver_stage0.py
"""
import json
import sys

sys.path.insert(0, "/tmp/scripts")

from django.conf import settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from assay_hygiene import stage0_apply  # noqa: E402

MANIFEST = "/tmp/stage0-manifest.jsonl"

with open(MANIFEST) as fh:
    rows = [json.loads(line) for line in fh if line.strip()]
print(f"manifest: {len(rows):,} edges")

nd = settings.NEO4J_DATABASE
db = nd.get("NAME") or "neo4j"
driver = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
for i in range(0, len(rows), 20_000):
    driver.execute_query(
        stage0_apply.MERGE_CYPHER, {"rows": rows[i : i + 20_000]}, database_=db
    )
    print(f"  merged {min(i + 20_000, len(rows)):,}/{len(rows):,}")
driver.close()
print("done")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_stage0_apply.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Run the full suite**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/ -q`
Expected: PASS, no failures. Record the count in the SDD ledger.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/stage0_apply.py scripts/assay_hygiene/driver_stage0.py tests/test_assay_hygiene_stage0_apply.py
git commit -m "feat(assay-hygiene): stage 0 applier, manifest, and manifest-scoped rollback"
```

---

### Task 7: HARD STOP. Dry run against real data, report to the operator

No code. This task produces the report the operator reads before authorising any write, and it stops.

**Files:**
- Create: `assay-hygiene/stage0/report.md` (gitignored output, not committed)
- Create: `assay-hygiene/stage0/manifest.jsonl` (gitignored output, not committed)
- Create: `assay-hygiene/stage0/reconciliation.csv` (gitignored output, not committed)

- [ ] **Step 1: Run the pipeline end to end in dry-run mode**

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "scripts")
import pandas as pd
from assay_hygiene import stage0, stage0_apply

ex = pathlib.Path("assay-hygiene/extract")
f = {n: pd.read_parquet(ex / f"{n}.parquet")
     for n in ("parents", "nodes", "edges", "membership", "assays", "samples", "sops", "childof")}
existing = f["edges"][["child_uuid", "parent_uuid"]]

plan, residues = stage0.plan_edges(f["parents"], f["nodes"], existing)
resolved = stage0.resolve_properties(plan, f["samples"], f["membership"], f["assays"], f["sops"])
recon = stage0.reconcile_childof(f["childof"], f["parents"])
manifest = stage0_apply.apply_edges(None, "neo4j", resolved)     # dry run

out = pathlib.Path("assay-hygiene/stage0"); out.mkdir(parents=True, exist_ok=True)
# `samples` is REQUIRED here, not optional. Without it build_report cannot tell a
# json_metadata parse failure from a genuinely absent Protocol key, and degrades to
# a pooled figure. The report is the operator's gate, so the distinction has to reach it.
(out / "report.md").write_text(stage0.build_report(resolved, residues, recon, f["samples"]))
recon.to_csv(out / "reconciliation.csv", index=False)
resolved.to_parquet(out / "plan.parquet", compression="zstd", index=False)
with open(out / "manifest.jsonl", "w") as fh:
    for row in manifest:
        fh.write(json.dumps(row, default=str) + "\n")
print(f"{len(resolved):,} edges planned")
PY
```

- [ ] **Step 2: Check the headline numbers against the spec**

Open `assay-hygiene/stage0/report.md` and confirm, against the spec's measured values:

```
edges to create                  90,534
labelled                         82,663   (91.3%)
dark                              7,871
prod_regex_would_reject           8,127   (all AB-*)
not_a_uid                         2,119
duplicate_reference                   7
parent_not_a_node                     6
self_loop                             1
min-internal_assay_id tiebreak       28
top hop  D.FLOW -> D.FCS         66,529   (100% labelled)
AB-parent edges                   8,120   (of which 4,020 labelled)
```

A material deviation means the extract or the planner is wrong. Stop and diagnose rather than proceeding.

**Corrected 2026-08-13.** Two of these were first written from a probe that counted RAW parent
tokens, while the extractor emits the token list `collect_parent_tokens` produces, which
deduplicates across keys. `prod_regex_would_reject` was 8,131 and `not_a_uid` was 2,392 against
795,687 raw tokens; the deduplicated figures are the ones above. Left uncorrected, this gate fired
on a correct run.

The exclusion ledger must also balance exactly:
`len(plan) + every drop reason == len(parents)`, i.e. `90,534 + 705,153 == 795,687`.
`prod_regex_would_reject` is NOT part of that sum: it is a report-only counter that overlaps
whichever bucket the reference lands in.

- [ ] **Step 3: Replay-test the Neo4j backup**

The existing backup at `~/backups/pre-hygiene-2026-08-13/fresh/` has a verified MySQL restore but `neo4j.cypher.gz` was **never replay-tested**. Stage 0 is a Neo4j write, so this is a prerequisite, not a nicety. Replay it into a throwaway Neo4j container and confirm node and relationship counts match live.

- [ ] **Step 4: Hand the report to the operator and STOP**

Report: the headline counts, the regex override and its 8,131 antibody references, the 28 tiebreak edges, and the reconciliation count. Ask whether to write, and whether to start with the smallest hop (`MUS -> BAC`, 2,274 edges) before the flow-cytometry bulk.

**Do not proceed to Task 8 without an explicit go.**

---

### Task 8: The production write, staged

Runs only after Task 7's approval.

- [ ] **Step 0: Re-extract `existing` and reconcile, immediately before writing**

The plan was computed against an extract taken earlier, on a live system that accepts uploads. If
`batch_upload` creates a `DERIVED_FROM` for a pair stage 0 has already planned, inside that window,
then the `MERGE` **matches instead of creating**, the unconditional `SET` overwrites all seven of
that edge's properties with no record of the previous values, and a later rollback deletes an edge
stage 0 never created. Rollback restores nothing in that case. See `stage0_apply.py`'s rollback
caveat.

Re-run the `edges` Cypher only, and reconcile:

```bash
cat > /tmp/recheck.py <<'PY'
import sys
sys.path.insert(0, "/tmp/scripts")
from django.conf import settings
from neo4j import GraphDatabase
from assay_hygiene import extract
nd = settings.NEO4J_DATABASE
drv = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
recs, _, _ = drv.execute_query(extract.EDGES_CYPHER, {}, database_=nd.get("NAME") or "neo4j")
print(f"DERIVED_FROM now: {len(recs):,}")
drv.close()
PY
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < /tmp/recheck.py
```

Expected: **704,059**, unchanged from the extract. If it has moved, do not write. Re-extract
`edges.parquet`, re-run the Task 7 dry run, and drop any planned pair that now appears in
`existing` from the manifest — do not merge over it. Alternatively quiesce `batch_upload` for the
write window.

- [ ] **Step 1: Write one hop first**

Filter the manifest to `MUS -> BAC` (2,274 edges) and write only those.

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "scripts")
import pandas as pd
plan = pd.read_parquet("assay-hygiene/stage0/plan.parquet")
sub = plan[(plan["child_type"] == "MUS") & (plan["parent_type"] == "BAC")]
from assay_hygiene import stage0_apply
rows = stage0_apply.to_payload(sub)
with open("/tmp/stage0-manifest.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r, default=str) + "\n")
print(f"{len(rows):,} edges staged")
PY
scp /tmp/stage0-manifest.jsonl fairdata:/tmp/stage0-manifest.jsonl
ssh fairdata 'docker cp /tmp/stage0-manifest.jsonl nextseek:/tmp/stage0-manifest.jsonl'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < scripts/assay_hygiene/driver_stage0.py
```

- [ ] **Step 2: Verify that hop in the graph and in the UI**

```bash
cat > /tmp/verify.py <<'PY'
from django.conf import settings
from neo4j import GraphDatabase
nd = settings.NEO4J_DATABASE
drv = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
r, _, _ = drv.execute_query(
    "MATCH (c:Sample {type:'MUS'})-[r:DERIVED_FROM]->(p:Sample {type:'BAC'}) "
    "RETURN count(r) AS n, count(r.internal_assay_id) AS labelled",
    {}, database_=nd.get("NAME") or "neo4j")
print(dict(r[0]))
drv.close()
PY
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < /tmp/verify.py
```

Expected: `n` = 2,274. Then open one of those samples in the NExtSEEK UI and confirm the lineage renders.

- [ ] **Step 3: Write the remaining hops**

Repeat step 1 with the full manifest.

- [ ] **Step 4: Run the full acceptance table**

```
DERIVED_FROM total              704,059 -> 794,593
labelled DERIVED_FROM           277,364 -> 360,027
dark DERIVED_FROM               426,695 -> 434,566
D.FLOW -> D.FCS DERIVED_FROM          0 -> 66,529, all labelled
DERIVED_FROM into AB parents          0 -> 8,120, of which 4,020 labelled
CHILD_OF total                  742,534 -> unchanged
```

`CHILD_OF total` changing at all means something wrote to it, which nothing in this plan does. Roll back and investigate.

- [ ] **Step 5: The end-to-end check that is the point of the work**

In `chat_nextseek`, ask both:

1. "what assay connects D.FLOW to D.FCS"
2. "what antibodies does a D.FLOW sample derive from"

Both return zero rows today. Both must now answer.

- [ ] **Step 6: Archive the manifest**

```bash
mkdir -p assay-hygiene/stage0/applied
cp /tmp/stage0-manifest.jsonl "assay-hygiene/stage0/applied/$(date +%Y%m%dT%H%M%S)-manifest.jsonl"
```

The manifest is the only rollback record. Losing it means losing the ability to target exactly what was created.

- [ ] **Step 7: Re-run stage A against the enlarged graph**

The companion plan mines precedent from `extract/edges.parquet`, which is now 90,534 edges short. Re-run Task 5 step 6 and confirm `edges.parquet` comes back at 794,593 rows.

Until this is done, every statistic in the companion plan is measured against a graph missing its largest hop. This is the handoff point between the two plans.

---

### Task 9: File the `UID_RE` production defect

Stage 0 closes the historical 8,120 antibody edges. It does not stop new ones from being dropped, because production still runs the regex that rejects them.

**Files:**
- Create: a GitHub issue on `BioMicroCenter/NExtSEEK`

- [ ] **Step 1: Draft the issue per the repo conventions**

Follow `docs/ISSUE-CONVENTIONS.md` in the NExtSEEK repo and validate with `scripts/validate_issue.py`. Content:

- **Title:** `UID_RE rejects the two-letter AB sample type, silently dropping every antibody parent reference`
- **Body:** production (`main-stable-260811 @ 83b8b99`) runs `^([AD]\.)?[A-Z]{3,}-...`; `[A-Z]{2,}` is required. `AB` is the only sample type in the database shorter than three characters. Consequence: 8,131 parent references are discarded before an edge is built, and all 874 `AB` parents have zero incoming `DERIVED_FROM`. The fix is already on `dev-v4-merge` (`nextseek_api/batch_upload/helpers.py`), so this is a deploy, not a code change. Include the reproduction: `UID_RE.match("AB-190703FOR-3")` returns `None` in the running container.

- [ ] **Step 2: Ask the operator before filing**

Per the NExtSEEK CLAUDE.md convention, deferred work becomes an issue, but filing is confirmed with the user first.

---

## Deferred, deliberately

- **Deploying the `UID_RE` fix.** Task 9 files it; shipping it is a NExtSEEK change on a different repo and release cadence.
- **Resolving the 2,392 non-UID parent tokens.** Human-readable names and malformed values. Stage 0 reports them; turning them into UIDs is curation work with a PI in the loop.
- **Acting on the CHILD_OF reconciliation.** Operator ruling 2026-08-13: `CHILD_OF` is left alone. The 3,829 undeclared edges are a report.
- **A CLI wrapper.** Tasks 7 and 8 drive the stages from inline scripts. A `stage0.py --write` entry point is worth adding once the shape has survived one real run, not before.
