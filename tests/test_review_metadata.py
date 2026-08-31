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
    p.write_text("D.SEQ-260527KAM-1\nD.IMG-260527KAM-2\n\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-260527KAM-1", "D.IMG-260527KAM-2"}


def test_load_retrieve_uids_strips_whitespace_and_blanks(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("  D.SEQ-260527KAM-1  \n\n\n  \nD.IMG-260527KAM-2\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-260527KAM-1", "D.IMG-260527KAM-2"}


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


def test_normalize_collapses_whitespace_around_semicolons():
    """NExtSEEK stores multi-parent lists as "A;B"; builds may emit "A; B".

    Without collapsing, every multi-parent row reads as a diff on a clean round
    trip. Observed live: a 101-row upload reported 10 false Parent diffs and
    nothing else.
    """
    from review_metadata_vs_uploads import normalize

    assert normalize("A; B") == normalize("A;B") == "A;B"
    assert normalize("A ;  B ;C") == "A;B;C"
    assert normalize("MUS-260807SHE-1; MUS-260807SHE-2") == "MUS-260807SHE-1;MUS-260807SHE-2"
    # single values and blanks are untouched
    assert normalize("CEL-260807SHE-9") == "CEL-260807SHE-9"
    assert normalize(None) == ""
    assert normalize("  padded  ") == "padded"
    # a genuine difference still shows up
    assert normalize("A;B") != normalize("A;C")


def test_join_uids_emits_the_canonical_separator():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    from _common import join_uids

    assert join_uids(["A", "B"]) == "A;B"
    assert join_uids(["A"]) == "A"
    assert join_uids([]) == ""
    # blanks dropped, order preserved, stray spacing stripped
    assert join_uids([" A ", None, "", "B"]) == "A;B"
