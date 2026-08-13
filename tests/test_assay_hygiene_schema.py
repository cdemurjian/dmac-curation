import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S


def test_verdict_constants_are_distinct():
    verdicts = [S.V_CLEAN, S.V_MODE1_CHILD, S.V_MODE1_PARENT,
                S.V_MODE1_BOTH_DARK, S.V_MODE2_PROPAGATE,
                S.V_MODE2_AMBIGUOUS, S.V_MODE3_FLAG]
    assert len(set(verdicts)) == len(verdicts)


def test_rule_key_is_title_not_assay_id():
    # 458 assay records share 291 titles; keying on id shatters precedent
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type", "assay_title"]
    assert "assay_id" not in S.RULE_KEY


def test_precedent_columns_carry_both_directions():
    for col in ("n_both", "n_child_only", "n_parent_only",
                "propagation_rate", "reverse_rate"):
        assert col in S.PRECEDENT_COLUMNS


def test_fixture_shapes_match_declared_columns():
    fx = S.make_fixture()
    assert list(fx["edges"].columns) == S.EDGE_COLUMNS
    assert list(fx["membership"].columns) == S.MEMBERSHIP_COLUMNS
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS


def test_fixture_encodes_the_four_canonical_situations():
    fx = S.make_fixture()
    # 1 propagating hop, 1 non-propagating hop, 1 dark child, 1 dark pair
    assert len(fx["edges"]) == 6
    assert set(fx["assays"]["title"]) == {"Comet Chip", "Tissue Collection"}
