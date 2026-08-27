"""The banner must see every extract-backed skip, not the ones named one way.

It exists to stop a run that measured nothing from reading as green. Matching
`_real_extract_` with a trailing underscore misses tests ending
`..._on_the_real_extract` and every `skipif` that does not follow the naming
convention -- 13 of 40 skips on a fresh clone.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))

from conftest import _MEASUREMENT_CONVENTION as PATTERN  # noqa: E402


def _matches(nodeid: str) -> bool:
    return bool(re.search(PATTERN, nodeid))


def test_it_matches_the_underscore_delimited_form():
    assert _matches("tests/t.py::test_the_real_extract_drops_every_cohort")


def test_it_matches_a_name_ENDING_in_real_extract():
    """Two real tests end this way and were invisible to the banner."""
    assert _matches("tests/t.py::test_the_gate_is_coherent_on_the_real_extract")


def test_it_does_not_match_an_unrelated_test():
    assert not _matches("tests/t.py::test_the_csv_carries_the_key")


def test_every_extract_backed_test_in_the_tree_is_visible_to_it():
    """Measured against the actual suite, not a fixture."""
    names = []
    for path in (REPO / "tests").glob("test_*.py"):
        for line in path.read_text().splitlines():
            if line.startswith("def test_") and "real_extract" in line:
                names.append(line.split("(")[0].removeprefix("def "))
    assert names, "no extract-backed tests found; this test would be vacuous"
    invisible = [n for n in names if not _matches(f"tests/x.py::{n}")]
    assert not invisible, f"invisible to the banner: {invisible}"
