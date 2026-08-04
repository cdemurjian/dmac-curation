import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import detect_context as dc  # noqa: E402


def test_tokenize_lowercases_and_drops_short():
    assert dc.tokenize("Cancer of the CSBC-2026") == ["cancer", "the", "csbc", "2026"]


def test_gather_evidence_reads_path_manuscript_master(tmp_path):
    proj = tmp_path / "csbc-publications" / "flower-curation-tyrosine"
    (proj / "manuscript").mkdir(parents=True)
    (proj / "manuscript" / "flower-white-2026-tyrosine.pdf").write_text("x")
    (proj / "previous_metadata").mkdir()
    (proj / "previous_metadata" / "CSBC All 260731.xlsx").write_text("x")
    ev = dc.gather_evidence(proj)
    assert "csbc" in ev.all_tokens()          # from path + master filename
    assert "flower" in ev.author_surnames     # manuscript filename token
    assert "white" in ev.author_surnames
    assert "csbc" in ev.master_tokens


def test_rank_projects_scores_and_sorts():
    projects = [{"id": 4, "title": "MetNet"},
                {"id": 10, "title": "Cancer_Systems_Biology_Consortium(CSBC)"}]
    ev = dc.Evidence(path_tokens=["csbc", "flower", "tyrosine"])
    ranked = dc.rank_projects(projects, ev)
    assert ranked[0]["id"] == 10
    assert ranked[0]["score"] >= 1
    assert ranked[-1]["id"] == 4 and ranked[-1]["score"] == 0
