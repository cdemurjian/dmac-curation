import io
import sys
from pathlib import Path

import openpyxl

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


def _make_xlsx(sheets):
    """sheets: list[(sheet_name, [(uid, scientist), ...])]"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        ws.append(["UID", "Scientist"])
        for uid, sci in rows:
            ws.append([uid, sci])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_labs_aggregates_by_lab_code():
    xlsx = _make_xlsx([
        ("CEL", [("CEL-260730WHI-1", "Cameron Flower"),
                 ("CEL-260731WHI-2", "Forest White")]),
        ("D.MSP", [("D.MSP-260729AGA-1", "Nathalie Agar"),
                   ("not-a-uid", "ignored")]),
    ])
    labs = {l.code: l for l in dc.extract_labs(xlsx)}
    assert labs["WHI"].count == 2
    assert labs["WHI"].scientists == ["Cameron Flower", "Forest White"]
    assert labs["WHI"].latest == "260731"
    assert labs["AGA"].count == 1
    assert "AGA" in labs and labs["AGA"].scientists == ["Nathalie Agar"]


def test_rank_labs_author_match_beats_count():
    labs = [dc.LabInfo("AGA", 50, ["Nathalie Agar"], "260701"),
            dc.LabInfo("WHI", 5, ["Cameron Flower", "Forest White"], "260731")]
    ranked = dc.rank_labs(labs, dc.Evidence(author_surnames=["white", "flower"]))
    assert ranked[0].code == "WHI"


def test_rank_labs_recency_tiebreak_when_no_author():
    labs = [dc.LabInfo("AAA", 10, ["X"], "260101"),
            dc.LabInfo("BBB", 10, ["Y"], "260731")]
    ranked = dc.rank_labs(labs, dc.Evidence())
    assert ranked[0].code == "BBB"


def test_guess_pi_prefers_arg():
    assert dc.guess_pi([], dc.Evidence(), "White") == "white"


def test_guess_pi_author_match():
    labs = [dc.LabInfo("WHI", 5, ["Cameron Flower", "Forest White"], "260731")]
    assert dc.guess_pi(labs, dc.Evidence(author_surnames=["white"]), None) == "white"


def test_guess_pi_fallback_first_scientist_surname():
    labs = [dc.LabInfo("WHI", 5, ["Forest White"], "260731")]
    assert dc.guess_pi(labs, dc.Evidence(), None) == "white"
