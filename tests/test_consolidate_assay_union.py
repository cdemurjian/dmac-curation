"""A row's assay_ids is its own assay plus every assay it is a parent to (issue #8).

NExtSEEK can only label a DERIVED_FROM edge when parent and child are both
members of that assay. The 4-sheet schema carries one assay per file and cannot
say this; the flat format carries assay_ids per row, which is why these passes
exist.

The keying case is the one that regressed once already: a record is addressable
by UID *or* by Name — NExtSEEK resolves a physical parent by Name — but it is
emitted under `uid or name`. Accumulating against the raw parent token drops the
pushed-up assay whenever a row that has a UID is referenced by Name.

UIDs here use the reserved 19MMDD synthetic band (see docs/SECURITY.md).
"""
import sys
from pathlib import Path

import openpyxl
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import consolidate_to_flat as C  # noqa: E402

LOOKUP = {"Tissue Collection": 10, "DNA Extraction": 41, "Sequencing": 77}

TIS_UID = "TIS-190101ABC-1"
DNA_UID = "DNA-190101ABC-1"
SEQ_UID = "D.SEQ-190101ABC-1"


def _build(tmp_path, source_files):
    C.build_arm_flat("T", source_files, tmp_path, LOOKUP, {}, "T-upload.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "T-upload.xlsx")["Samples"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    out = {}
    for r in rows[1:]:
        d = dict(zip(hdr, r))
        ids = {t.strip() for t in str(d["assay_ids"] or "").split(",") if t.strip()}
        out[d["uid"] or d["name"]] = ids
    return out


def _tissue(parent=""):
    return ("TIS", "Tissue Collection",
            [{"UID": TIS_UID, "Name": "tissue-A", "Parent": parent}])


def _dna(parent):
    return ("DNA", "DNA Extraction",
            [{"UID": DNA_UID, "Name": "dna-A", "Parent": parent}])


@pytest.mark.parametrize("token,label", [
    (TIS_UID, "by UID"),
    ("tissue-A", "by Name"),
])
def test_parent_joins_its_childs_assay_however_it_is_referenced(
        tmp_path, token, label):
    """The regression: a Name-referenced parent kept only its own assay."""
    got = _build(tmp_path, [_tissue(), _dna(token)])
    assert got[TIS_UID] == {"10", "41"}, (
        f"parent referenced {label} should carry its own assay (10) and the "
        f"assay it feeds (41), got {got[TIS_UID]}")
    assert got[DNA_UID] == {"41"}


def test_a_row_feeding_two_assays_carries_both(tmp_path):
    tis = ("TIS", "Tissue Collection",
           [{"UID": TIS_UID, "Name": "tissue-A", "Parent": ""}])
    dna = ("DNA", "DNA Extraction",
           [{"UID": DNA_UID, "Name": "dna-A", "Parent": "tissue-A"}])
    seq = ("D.SEQ", "Sequencing",
           [{"UID": SEQ_UID, "Name": "seq-A", "Parent": TIS_UID}])
    got = _build(tmp_path, [tis, dna, seq])
    assert got[TIS_UID] == {"10", "41", "77"}


def test_a_parent_outside_the_workbook_is_left_alone(tmp_path):
    """The documented residue: `assay` mode owns parents this build cannot see."""
    got = _build(tmp_path, [_dna("TIS-190101ABC-9")])
    assert got[DNA_UID] == {"41"}
    assert "TIS-190101ABC-9" not in got


def test_multi_parent_tokens_are_split_on_semicolons(tmp_path):
    other = "TIS-190101ABC-2"
    tis = ("TIS", "Tissue Collection", [
        {"UID": TIS_UID, "Name": "tissue-A", "Parent": ""},
        {"UID": other, "Name": "tissue-B", "Parent": ""},
    ])
    dna = ("DNA", "DNA Extraction",
           [{"UID": DNA_UID, "Name": "dna-A", "Parent": f"tissue-A; {other}"}])
    got = _build(tmp_path, [tis, dna])
    assert got[TIS_UID] == {"10", "41"}
    assert got[other] == {"10", "41"}


def test_a_row_with_no_resolvable_assay_title_is_not_invented(tmp_path):
    """An unresolvable assay title must not put a bare id on anyone's row."""
    tis = ("TIS", "Nothing In The Cache",
           [{"UID": TIS_UID, "Name": "tissue-A", "Parent": ""}])
    got = _build(tmp_path, [tis, _dna(TIS_UID)])
    assert got[TIS_UID] == {"41"}, "keeps the assay it feeds, invents nothing"
