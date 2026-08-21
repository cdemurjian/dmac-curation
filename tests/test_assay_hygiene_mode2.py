# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The lineage lane's own tests. This file did not exist before this plan.

`mode2.py` is the largest module in the package and generates 167,454 of the
170,786 rows in `findings.csv`, and until now it was exercised only incidentally
through `tests/test_assay_hygiene_classify.py`. Both audits of 2026-08-21 noted
that the one module with no direct test file is where the defects concentrated.

Both figures re-derived 2026-08-21 by counting `mode` over the artifact:
`csv.DictReader(open('assay-hygiene/findings.csv'))` -> 170,786 rows total,
`MODE_2` 167,454, `MODE_1` 1,373, blank 1,959.

NO LINE COUNT HERE ON PURPOSE. The first revision of this docstring said "806
lines", which was already wrong at the commit that introduced it, since that
same commit removed three. Every subsequent edit to `mode2.py` invalidates the
figure again, and no test can check a comment -- which is the stale-figure
defect this package keeps shipping. The sentence means "large" and does not
need a number to say it.
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
    # No `!= BY_BOTH` / `!= BY_LINEAGE_ONLY` here: those follow from the `==`
    # above and would discriminate nothing while wearing this package's
    # "simulate the wrong rule by hand" discipline. The real counterfactual --
    # a row that a widening WOULD have mislabelled, with the row's own null rate
    # and its claim-bearing summary falsifying each alternative -- is in
    # `test_assay_hygiene_classify.py`, in
    # `test_a_claim_with_no_precedent_rule_names_its_own_source` and
    # `test_a_reduced_rule_set_relabels_the_row_rather_than_aborting_the_run`.


def test_the_other_three_combinations_are_unchanged():
    rule = M2.Rule(1, 2, 3, 0.5, 0.25)
    assert M2._proposal_source(rule, _Claim(), 1, 2) == X.BY_BOTH
    assert M2._proposal_source(rule, None, 1, 2) == X.BY_PRECEDENT
    assert M2._proposal_source(None, None, 1, 2) == X.BY_LINEAGE_ONLY
