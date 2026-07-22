"""/curate-status reports per mode, not per phase."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import status as status_mod  # noqa: E402

SCRIPT = REPO / "scripts" / "status.py"


def _run(root: Path, *argv):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--project-root", str(root), *argv],
        capture_output=True, text=True, timeout=120,
    )


def test_collect_status_on_empty_dir_reports_no_modes(tmp_path):
    st = status_mod.collect_status(tmp_path)
    assert st["lockfile"] is None
    assert all(not m["present"] for m in st["modes"].values())


def test_collect_status_reports_all_four_modes(tmp_path):
    assert set(status_mod.collect_status(tmp_path)["modes"]) == {
        "pipeline", "fdh", "schema", "report"}


def test_pipeline_mode_present_when_lockfile_has_it(curation_project):
    st = status_mod.collect_status(curation_project)
    assert st["modes"]["pipeline"]["present"] is True
    assert st["lockfile"]["modes"]["pipeline"]["lab"] == "KAM"


def test_pipeline_artifacts_detected(curation_project):
    (curation_project / "FILE_INDEX.md").write_text("x")
    (curation_project / "SAMPLE_TREE.md").write_text("x")
    st = status_mod.collect_status(curation_project)
    found = {a["name"]: a for a in st["modes"]["pipeline"]["artifacts"]}
    assert found["FILE_INDEX.md"]["present"] is True
    assert found["SAMPLE_TREE.md"]["present"] is True
    assert found["RETRIEVE.TXT"]["present"] is False


def test_pipeline_artifacts_are_keyed_by_phase_number(curation_project):
    st = status_mod.collect_status(curation_project)
    phases = {a["phase"] for a in st["modes"]["pipeline"]["artifacts"]}
    assert 4 not in phases, "Phase 4 is retired"
    assert 8 not in phases, "Phase 8 is retired"
    assert {1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13} <= phases


def test_schema_mode_present_when_schema_dir_exists(tmp_path):
    (tmp_path / "schema").mkdir()
    (tmp_path / "schema" / "D.VIA.review.md").write_text("x")
    st = status_mod.collect_status(tmp_path)
    assert st["modes"]["schema"]["present"] is True
    assert "D.VIA" in st["modes"]["schema"]["detail"]


def test_report_mode_present_when_report_dir_exists(tmp_path):
    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "GEO.mapping.json").write_text("{}")
    st = status_mod.collect_status(tmp_path)
    assert st["modes"]["report"]["present"] is True
    assert "GEO" in st["modes"]["report"]["detail"]


def test_fdh_mode_present_when_credentials_are_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("FDH_API", '{"user": "tok"}')
    assert status_mod.collect_status(tmp_path)["modes"]["fdh"]["present"] is True


def test_fdh_mode_never_prints_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("FDH_API", '{"user": "SUPERSECRET"}')
    st = status_mod.collect_status(tmp_path)
    assert "SUPERSECRET" not in json.dumps(st)


def test_suggested_next_on_empty_project(tmp_path):
    assert "/curate-init" in status_mod.collect_status(tmp_path)["suggested_next"]


def test_suggested_next_advances_with_artifacts(curation_project):
    (curation_project / "FILE_INDEX.md").write_text("x")
    st = status_mod.collect_status(curation_project)
    assert "/curate-sample-tree" in st["suggested_next"]


def test_cli_json_output_is_parseable(curation_project):
    r = _run(curation_project, "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["modes"]["pipeline"]["present"] is True


def test_cli_human_output_lists_modes(curation_project):
    r = _run(curation_project)
    assert r.returncode == 0, r.stderr
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in r.stdout
    assert "Suggested next:" in r.stdout


def test_cli_writes_nothing_in_the_plugin(curation_project, plugin_sentinel):
    _run(curation_project)


def test_command_doc_is_per_mode():
    doc = (REPO / "commands" / "curate-status.md").read_text()
    assert "13-phase pipeline" not in doc
    assert "scripts/status.py" in doc
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in doc
