# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The lineage lane's own tests. This file did not exist before this plan.

`mode2.py` is 806 lines and generates 167,454 of the 170,786 findings rows, and
until now it was exercised only incidentally through
`tests/test_assay_hygiene_classify.py`. Both audits of 2026-08-21 noted that the
one module with no direct test file is where the defects concentrated.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import mode2 as M2  # noqa: E402


class _Claim:
    """The duck-typed shape `_proposal_source` reads. It touches no attribute."""


def test_a_gated_claim_with_no_precedent_rule_names_its_own_source():
    """The combination the function used to raise on.

    It occurs 0 times on the 2026-08-17 extract, which is a fact about that
    extract. The reachability rework moves the populations that determine it,
    so the run must not abort the first time one appears.
    """
    got = M2._proposal_source(None, _Claim(), sample_id=1, assay_id=2)
    assert got == X.BY_CLAIM_NO_RULE
    assert got in X.PROPOSAL_SOURCES
    # ...and the wrong answers, simulated by hand, DIFFER. BY_BOTH would assert
    # a precedent that is not there; BY_LINEAGE_ONLY would hide the claim.
    assert got != X.BY_BOTH
    assert got != X.BY_LINEAGE_ONLY


def test_the_other_three_combinations_are_unchanged():
    rule = M2.Rule(1, 2, 3, 0.5, 0.25)
    assert M2._proposal_source(rule, _Claim(), 1, 2) == X.BY_BOTH
    assert M2._proposal_source(rule, None, 1, 2) == X.BY_PRECEDENT
    assert M2._proposal_source(None, None, 1, 2) == X.BY_LINEAGE_ONLY
