# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Column contracts and verdict vocabulary shared by every assay-hygiene stage.

Keeping these in one place is what lets stages B-E be pure functions over
DataFrames with no database access, and what keeps task N+1 from inventing a
column name task N never wrote.
"""
from __future__ import annotations

import re

import pandas as pd

# --- UID validation ----------------------------------------------------------
# Production (main-stable-260811 @ 83b8b99) requires a 3+ letter sample type
# code. Exactly one type in the database is shorter: AB, the antibody type.
# So every AntibodyParent reference is silently discarded before an edge is
# built, and all 874 AB parents have zero incoming DERIVED_FROM.
UID_RE_PROD = re.compile(r"^([AD]\.)?[A-Z]{3,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?$")

# The fix, already on dev-v4-merge. Stage 0 uses this one and reports the delta.
UID_RE_FIXED = re.compile(r"\A([A-Z]\.)?[A-Z]{2,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?\Z")

# --- extract (stage A) -------------------------------------------------------
EDGE_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "edge_assay_id", "edge_assay_title", "edge_protocol_id",
]
MEMBERSHIP_COLUMNS = ["sample_id", "assay_id"]
ASSAY_COLUMNS = [
    "assay_id", "title", "sample_type_id", "study_id",
    "investigation_id", "project_id", "project_title",
    # resolved through dmac.assays_internal_assays; NULL for the 17 records
    # with no junction row, which fall back to (assay_id, title) per
    # neo4j_sync.py:1011-1021
    "internal_assay_id", "internal_assay_title",
]
SAMPLE_COLUMNS = ["sample_id", "uuid", "json_metadata", "created_at", "project_ids"]
# `sops` had no contract until stage A needed one. The same two names were
# hand-written in three unlinked places (stage0.resolve_properties, the stage 0
# fixture, and a test); this is the constant the extractor's projection and its
# frame are both built from, so the producer can no longer drift from them.
SOP_COLUMNS = ["sop_id", "title"]

# --- stage 0 (lineage backfill) ----------------------------------------------
PARENT_COLUMNS = ["child_uuid", "field", "token"]
CHILDOF_COLUMNS = ["child_uuid", "parent_uuid"]
# the graph's node index: uuid -> (sample_id, sample type). Every child_id and
# parent_id stage 0 writes is resolved through this frame.
NODES_COLUMNS = ["uuid", "sample_id", "type"]

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

# --- emit (stage E) ----------------------------------------------------------
RULE_COLUMNS = PRECEDENT_COLUMNS + [
    "verdict", "action", "affected_count", "decided_by", "rationale",
    "APPROVE", "NOTES",
]

# --- vocabulary --------------------------------------------------------------
V_CLEAN = "CLEAN"
V_MODE1_CHILD = "MODE_1_CHILD"
V_MODE1_PARENT = "MODE_1_PARENT"
V_MODE1_BOTH_DARK = "MODE_1_BOTH_DARK"
V_MODE2_PROPAGATE = "MODE_2_PROPAGATE"
V_MODE2_AMBIGUOUS = "MODE_2_AMBIGUOUS"
V_MODE3_FLAG = "MODE_3_FLAG"

A_NONE = "NONE"
A_ADD_PARENT = "ADD_PARENT_TO_ASSAY"
A_ADD_CHILD = "ADD_CHILD_TO_ASSAY"
A_ADD_TO_ASSAY = "ADD_TO_ASSAY"
A_FLAG_ONLY = "FLAG_ONLY"


def make_fixture() -> dict[str, pd.DataFrame]:
    """A six-edge synthetic world for the precedent and classify stages.

    assay 1 "Comet Chip"        project 10, propagating   (D.IMG -> TIS)
    assay 2 "Tissue Collection" project 10, non-propagating

    samples: 100/101 D.IMG children, 200/201 TIS parents,
             300/301 dark children, 400 dark parent

    Branches this data DOES reach:
      CLEAN             100 -> 200 and 101 -> 201, both endpoints co-registered
                        in Comet Chip; plus the 203 -> 500 TIS -> MUS hop, whose
                        precedent does not propagate
      MODE_1_CHILD      300 -> 200, child registered nowhere
      MODE_1_BOTH_DARK  301 -> 400, neither endpoint registered
      MODE_2_PROPAGATE  102 -> 202, child in Comet Chip and parent only in
                        Tissue Collection, on a hop whose precedent propagates

    Branches this data does NOT reach:
      MODE_1_PARENT     no edge pairs a registered child with a wholly dark
                        parent. 102 -> 202 is not this case: its parent is
                        registered, just in a different assay, which is mode 2.
      MODE_2_AMBIGUOUS  no child is registered in 2+ assays, so ``candidates``
                        is single-element on every row and no tiebreak can fire
                        here. Proving the stage-D tiebreak works needs a fixture
                        of its own; a tiebreak that never fires is
                        indistinguishable from a correct one.
      MODE_3_FLAG       nothing in this world produces it.

    The data is frozen. Later stages hand-trace counts off these exact rows
    (for D.IMG -> TIS under Comet Chip: n_both=2, n_child_only=1, hence
    propagation_rate=2/3), so editing a membership row or a type column
    silently invalidates their arithmetic. tests/test_assay_hygiene_schema.py
    pins this structure, including the two unreached branches above, so the
    data and this docstring cannot drift apart.
    """
    edges = pd.DataFrame(
        [
            # both registered in Comet Chip -> establishes propagation precedent
            (100, 200, "D.IMG-1", "TIS-1", "D.IMG", "TIS", 1, "Comet Chip", None),
            (101, 201, "D.IMG-2", "TIS-2", "D.IMG", "TIS", 1, "Comet Chip", None),
            # child in Comet Chip, parent only in Tissue Collection -> dark, mode 2
            (102, 202, "D.IMG-3", "TIS-3", "D.IMG", "TIS", None, None, None),
            # TIS -> MUS where precedent says it does not propagate -> CLEAN
            (203, 500, "TIS-4", "MUS-1", "TIS", "MUS", None, None, None),
            # child registered nowhere -> mode 1 child
            (300, 200, "DNA-1", "TIS-1", "DNA", "TIS", None, None, None),
            # neither endpoint registered -> mode 1 both dark
            (301, 400, "DNA-2", "TIS-9", "DNA", "TIS", None, None, None),
        ],
        columns=EDGE_COLUMNS,
    )
    membership = pd.DataFrame(
        [
            (100, 1), (200, 1),          # both in Comet Chip
            (101, 1), (201, 1),          # both in Comet Chip
            (102, 1), (202, 2),          # disjoint -> the mode 2 case
            (203, 2), (500, 1),          # disjoint, but hop does not propagate
            (200, 2), (201, 2),          # parents also in Tissue Collection
        ],
        columns=MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
        ],
        columns=ASSAY_COLUMNS,
    )
    samples = pd.DataFrame(
        [
            (100, "D.IMG-1", '{"Protocol": "/sops/5", "Name": "img1"}', None, "10"),
            (300, "DNA-1", '{"Protocol": "/sops/9", "Name": "dna1"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
    return {"edges": edges, "membership": membership,
            "assays": assays, "samples": samples}


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
        columns=NODES_COLUMNS,
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
