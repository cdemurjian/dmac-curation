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

import pandas as pd

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
]
SAMPLE_COLUMNS = ["sample_id", "uuid", "json_metadata", "created_at", "project_ids"]

# --- precedent (stage B) -----------------------------------------------------
RULE_KEY = ["project_id", "child_type", "parent_type", "assay_title"]
PRECEDENT_COLUMNS = RULE_KEY + [
    "n_both", "n_child_only", "n_parent_only",
    "propagation_rate", "reverse_rate",
]

# --- classify (stage C) ------------------------------------------------------
FINDING_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "verdict", "matched_assay_title", "matched_rate",
    "target_assay_id", "project_id",
    # every assay title the child belongs to; stage D's tiebreak needs this and
    # cannot recover it later, because membership is not carried into findings
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
    """A six-edge synthetic world covering every branch of stage C.

    assay 1 "Comet Chip"        project 10, propagating   (D.IMG -> TIS)
    assay 2 "Tissue Collection" project 10, non-propagating

    samples: 100/101 D.IMG children, 200/201 TIS parents,
             300 dark child, 400 dark parent
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
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP"),
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
