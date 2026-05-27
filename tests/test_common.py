"""Smoke tests for scripts/_common.py — verify imports and core function signatures."""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _common  # noqa: E402


def test_module_imports():
    assert _common is not None


def test_mint_uid_signature():
    """mint_uid should exist and accept (sample_type, lab, date, n) → str."""
    assert hasattr(_common, "mint_uid"), "mint_uid function expected"
    uid = _common.mint_uid("RNA", "KAM", "260527", 1)
    assert uid == "RNA-260527KAM-1"


def test_mint_uid_format():
    uid = _common.mint_uid("D.SEQ", "ENG", "260514", 42)
    assert uid == "D.SEQ-260514ENG-42"
