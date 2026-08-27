"""The write protection four files claim, actually applied.

Nothing in this repository performed the `chmod a-w` that `assets/RUN1/README.md`,
`validation_sample.py`, `tests/test_assay_hygiene_rulings.py` and a findings doc
all assert. This makes the claim true and checkable.
"""
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene.protect_run import protect, verify  # noqa: E402


def _run(tmp_path):
    run = tmp_path / "RUN9"
    for tier in ("00-rulings", "04-artifacts"):
        (run / tier).mkdir(parents=True)
        (run / tier / "judgement.tsv").write_text("cohort\tverdict\n")
    return run


def test_protect_makes_a_tier_unwritable(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    mode = (run / "00-rulings").stat().st_mode
    assert not (mode & stat.S_IWUSR), "the directory is still writable"


def test_a_protected_tier_refuses_a_new_file(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    try:
        (run / "00-rulings" / "sneaked-in.csv").write_text("x")
        raised = False
    except PermissionError:
        raised = True
    assert raised, "a protected tier accepted a new file"


def test_verify_reports_an_unprotected_tier(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    unprotected = verify(run, ["00-rulings", "04-artifacts"])
    assert [p.name for p in unprotected] == ["04-artifacts"]


def test_verify_is_empty_once_everything_is_protected(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings", "04-artifacts"])
    assert verify(run, ["00-rulings", "04-artifacts"]) == []


def test_protect_is_idempotent(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    assert protect(run, ["00-rulings"]) == [], "second call re-changed something"
