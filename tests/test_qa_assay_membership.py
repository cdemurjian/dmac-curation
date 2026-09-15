"""Check 8: an edge whose parent and child share no assay uploads unlabelled.

NExtSEEK can only put an assay label on a DERIVED_FROM edge when parent and
child are BOTH members of that assay (issue #8). These assert the QA pass
catches that at phase 9A, and — just as important — that it says so when it
cannot run instead of passing vacuously.

UIDs here use the reserved 19MMDD synthetic band (see docs/SECURITY.md).
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import qa_flat_sheets  # noqa: E402

HEADERS = ["uid", "sampletype", "name", "parent", "notes_summary",
           "assay_titles", "assay_ids", "json_metadata"]

TISSUE = "TIS-190101ABC-1"
DNA = "DNA-190101ABC-1"


def _row(uid, sampletype, parent, assay_ids):
    meta = {"UID": uid, "Name": uid}
    if parent:
        meta["Parent"] = parent
    return [uid, sampletype, uid, parent, "", "", assay_ids,
            json.dumps(meta, separators=(",", ":"))]


def _workbook(tmp_path, rows, headers=HEADERS):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Samples"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    path = tmp_path / "Arm-upload.xlsx"
    wb.save(path)
    return path


def _cfg(tmp_path):
    context = tmp_path / "context"
    context.mkdir(exist_ok=True)
    (context / "sampletypes_db.json").write_text(json.dumps([
        {"SampleType": "TIS", "Name": "Tissue", "Required Metadata": ""},
        {"SampleType": "DNA", "Name": "DNA", "Required Metadata": ""},
    ]))
    # expected_counts={} not None: main() tolerates None at its first use and
    # then crashes on `set(expected_counts)` in the report. Separate bug; not
    # what these tests are about.
    return SimpleNamespace(root=tmp_path, context=context,
                           master_workbook=None, expected_counts={},
                           always_root={"TIS"})


def _run(tmp_path, rows, capsys, headers=HEADERS):
    path = _workbook(tmp_path, rows, headers)
    try:
        qa_flat_sheets.main(path, _cfg(tmp_path))
    except SystemExit:
        pass
    return capsys.readouterr().out


def test_a_parent_outside_the_childs_assay_is_a_blocker(tmp_path, capsys):
    """The defect: the assay holds only what it produced."""
    out = _run(tmp_path, [
        _row(TISSUE, "TIS", "", ""),          # parent, in no assay
        _row(DNA, "DNA", TISSUE, "41"),       # child, sole member of assay 41
    ], capsys)
    assert "assay_membership_gap" in out
    assert TISSUE in out
    assert "1 parent-child edge(s) checked" in out


def test_no_blocker_once_the_parent_joins_the_childs_assay(tmp_path, capsys):
    """The fix: the parent is a member of the assay it feeds."""
    out = _run(tmp_path, [
        _row(TISSUE, "TIS", "", "41"),
        _row(DNA, "DNA", TISSUE, "41"),
    ], capsys)
    assert "assay_membership_gap" not in out
    assert "1 parent-child edge(s) checked" in out


def test_a_row_with_no_assay_is_reported_once_not_once_per_parent(tmp_path, capsys):
    """Two parents, one missing assay set on the child: one finding, not two."""
    other = "TIS-190101ABC-2"
    out = _run(tmp_path, [
        _row(TISSUE, "TIS", "", "41"),
        _row(other, "TIS", "", "41"),
        _row(DNA, "DNA", f"{TISSUE};{other}", ""),
    ], capsys)
    assert out.count("has no assay_ids") == 1
    assert "2 parent-child edge(s) checked" in out


def test_a_parent_outside_this_sheet_is_not_judged(tmp_path, capsys):
    """`assay` mode owns parents this workbook cannot speak for."""
    out = _run(tmp_path, [
        _row(DNA, "DNA", "TIS-190101ABC-9", "41"),
    ], capsys)
    assert "assay_membership_gap" not in out
    assert "0 parent-child edge(s) checked" in out


def test_a_sheet_without_the_column_says_it_skipped(tmp_path, capsys):
    headers = [h for h in HEADERS if h != "assay_ids"]
    rows = [[c for h, c in zip(HEADERS, _row(TISSUE, "TIS", "", ""))
             if h != "assay_ids"],
            [c for h, c in zip(HEADERS, _row(DNA, "DNA", TISSUE, ""))
             if h != "assay_ids"]]
    out = _run(tmp_path, rows, capsys, headers=headers)
    assert "[SKIP] assay-membership check: sheet has no 'assay_ids' column" in out


def test_a_sheet_with_blank_uids_says_it_skipped(tmp_path, capsys):
    """Blank UIDs mean nothing to key parent tokens on. Say so; do not pass."""
    out = _run(tmp_path, [
        _row("", "TIS", "", "41"),
        _row("", "DNA", "some tissue", "41"),
    ], capsys)
    assert "[SKIP] assay-membership check: no row carries a UID" in out
    assert "assay_membership_gap" not in out
