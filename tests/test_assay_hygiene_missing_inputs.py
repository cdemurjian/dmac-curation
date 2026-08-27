"""A missing prerequisite must name itself and the command that makes it.

`assets/RUN1/README.md` documents `run_detect <extract> /tmp/out` as the
reproduction command. run_detect never calls run_evidence, so gate and classify
read claims.parquet out of an empty directory and die with a bare traceback.
`compatibility.py:670-676` already handles this correctly; these two did not.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import gate as G, classify as X  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"


def test_gate_names_the_missing_input_rather_than_raising(tmp_path, capsys):
    rc = G.main(str(EXTRACT), str(tmp_path))
    assert rc == 2
    out = capsys.readouterr().out
    assert "claims.parquet" in out
    assert "run_evidence" in out, "the message must say what to run first"


def test_classify_names_the_missing_input_rather_than_raising(tmp_path, capsys):
    rc = X.main(str(EXTRACT), str(tmp_path))
    assert rc == 2
    out = capsys.readouterr().out
    assert "claims.parquet" in out or "vocabulary.csv" in out
    assert "run_evidence" in out
