"""context/ must have a real refresh path and a provenance record.

VINTAGE.json promised 'Refresh via tools/refresh_context.py (planned, not yet
implemented)' and tools/ did not exist, while the bundled neo4j_schema.json was
a DEV-instance snapshot with 23 Sample properties against a live 85.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "refresh_context.py"
sys.path.insert(0, str(REPO / "scripts"))

import refresh_context as rc  # noqa: E402

MANAGED = [
    "sampletypes_db.json", "assays_db.json", "projects_db.json",
    "neo4j_schema.json", "neo4j_assay-sample-conn.json",
]


def test_script_exists_and_help_runs():
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    for flag in ("--from-dir", "--check", "--write"):
        assert flag in r.stdout


def test_managed_files_list_matches_vintage():
    vintage = json.loads((REPO / "context" / "VINTAGE.json").read_text())
    for name in MANAGED:
        assert name in vintage["files"], f"{name} not described in VINTAGE.json"


def test_vintage_no_longer_promises_a_nonexistent_tool():
    text = (REPO / "context" / "VINTAGE.json").read_text()
    assert "tools/refresh_context.py" not in text
    assert "planned, not yet implemented" not in text
    assert "scripts/refresh_context.py" in text


def test_vintage_records_the_instance_each_file_came_from():
    vintage = json.loads((REPO / "context" / "VINTAGE.json").read_text())
    assert "instance" in vintage, (
        "VINTAGE.json must record whether snapshots came from prod or dev")


def test_provenance_file_exists_with_entries_key():
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    assert isinstance(prov, dict)
    assert "entries" in prov


def test_provenance_entry_shape():
    e = rc.provenance_entry(
        source_repo="chat_nextseek",
        source_path="src/chat_nextseek/context/neo4j_schema.json",
        commit_sha="deadbeef",
        vendored_date="2026-07-21",
        local_divergence="none",
    )
    assert set(e) == {"source_repo", "source_path", "commit_sha",
                      "vendored_date", "local_divergence"}


def test_provenance_entry_carries_sha256_when_given():
    e = rc.provenance_entry(
        source_repo="r", source_path="p", commit_sha="c",
        vendored_date="2026-07-21", local_divergence="none", sha256="abc")
    assert e["sha256"] == "abc"


def test_every_managed_context_file_has_provenance():
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    for name in MANAGED:
        assert f"context/{name}" in prov["entries"], (
            f"context/{name} has no provenance entry")


def test_check_mode_writes_nothing(plugin_sentinel):
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--check"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode in (0, 1), r.stderr


def test_refresh_requires_write_to_mutate(tmp_path, plugin_sentinel):
    src = tmp_path / "src"
    src.mkdir()
    (src / "sampletypes_db.json").write_text(json.dumps([{"SampleType": "ZZZ"}]))
    r = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--from-dir", str(src)],
        capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout.lower()


def test_refresh_writes_and_records_provenance(tmp_path, monkeypatch):
    """Exercise the write path against a temporary plugin-like tree."""
    ctx = tmp_path / "plugin" / "context"
    ctx.mkdir(parents=True)
    (ctx / "sampletypes_db.json").write_text("[]")
    (ctx / "PROVENANCE.json").write_text(json.dumps({"entries": {}}))

    src = tmp_path / "src"
    src.mkdir()
    (src / "sampletypes_db.json").write_text(json.dumps([{"SampleType": "ZZZ"}]))

    monkeypatch.setattr(rc, "CONTEXT_DIR", ctx)
    rc.refresh(src, write=True, commit_sha="cafe1234", today="2026-07-21")

    assert json.loads((ctx / "sampletypes_db.json").read_text()) == [
        {"SampleType": "ZZZ"}]
    prov = json.loads((ctx / "PROVENANCE.json").read_text())
    assert prov["entries"]["context/sampletypes_db.json"]["commit_sha"] == "cafe1234"


def test_sample_property_count_returns_an_int():
    """The 23-vs-85 gap is the headline signal; the tool must surface it."""
    assert isinstance(rc.sample_property_count(REPO / "context" / "neo4j_schema.json"), int)


def test_sample_property_count_tolerates_a_missing_file(tmp_path):
    assert rc.sample_property_count(tmp_path / "nope.json") == 0
