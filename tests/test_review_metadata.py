"""Phase 12 must actually read RETRIEVE.TXT (PHASES.md:246 claimed it did)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "review_metadata_vs_uploads.py"
sys.path.insert(0, str(REPO / "scripts"))

import review_metadata_vs_uploads as review  # noqa: E402


def test_retrieve_flag_exists():
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "--retrieve" in r.stdout


def test_load_retrieve_uids_reads_one_per_line(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("D.SEQ-190902KAM-1\nD.IMG-190902KAM-2\n\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-190902KAM-1", "D.IMG-190902KAM-2"}


def test_load_retrieve_uids_strips_whitespace_and_blanks(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("  D.SEQ-190902KAM-1  \n\n\n  \nD.IMG-190902KAM-2\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-190902KAM-1", "D.IMG-190902KAM-2"}


def test_load_retrieve_uids_missing_file_returns_none(tmp_path):
    assert review.load_retrieve_uids(tmp_path / "nope.txt") is None


def test_diff_reports_requested_but_absent():
    d = review.diff_retrieve({"A-1", "A-2", "A-3"}, {"A-1", "A-3", "PARENT-9"},
                             parent_types={"PARENT"})
    assert d["missing"] == ["A-2"]
    assert d["auto_pulled_parents"] == ["PARENT-9"]
    assert d["extra"] == []


def test_diff_classifies_auto_pulled_parents_separately():
    """chat_nextseek auto-pulls parents; they are not extra rows to alarm on."""
    d = review.diff_retrieve({"D.SEQ-1"},
                             {"D.SEQ-1", "RNA-1", "MUS-1", "SURPRISE-1"},
                             parent_types={"RNA", "MUS", "DNA", "TIS"})
    assert d["missing"] == []
    assert sorted(d["auto_pulled_parents"]) == ["MUS-1", "RNA-1"]
    assert d["extra"] == ["SURPRISE-1"]


def test_diff_with_no_retrieve_file_is_a_no_op():
    assert review.diff_retrieve(None, {"A-1"}, parent_types=set()) is None


def test_default_parent_types_cover_the_auto_pulled_set():
    assert review.AUTO_PULLED_PARENT_TYPES >= {
        "MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}


def test_command_doc_documents_the_flag():
    assert "--retrieve" in (REPO / "commands" / "curate-validate.md").read_text()


def test_phases_doc_no_longer_overclaims():
    text = (REPO / "skills" / "curation" / "PHASES.md").read_text()
    s = text.split("## Phase 12 ", 1)[1].split("\n## ", 1)[0]
    assert "--retrieve" in s
