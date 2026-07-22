"""Lockfile schema v1 and v0 -> v1 migration (toolkit spec section 3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

V0 = {
    "plugin_name": "dmac-curation",
    "plugin_sha": "abc123",
    "plugin_version": "0.1.0",
    "schema_vintage": "2026-05-27",
    "init_date": "2026-05-27",
    "init_user": "cdemu",
    "lab": "KAM",
    "pi": "marie",
    "nextseek_project_id": 42,
}


def test_schema_version_is_1():
    assert _lockfile.SCHEMA_VERSION == 1


def test_plugin_version_matches_plugin_json():
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert _lockfile.PLUGIN_VERSION == manifest["version"]


def test_migrate_v0_moves_flat_keys_into_modes_pipeline():
    out = _lockfile.migrate_v0(V0)
    assert out["schema_version"] == 1
    assert out["modes"]["pipeline"]["lab"] == "KAM"
    assert out["modes"]["pipeline"]["pi"] == "marie"
    assert out["modes"]["pipeline"]["nextseek_project_id"] == 42


def test_migrate_v0_keeps_plugin_level_keys_at_top():
    out = _lockfile.migrate_v0(V0)
    assert out["plugin_name"] == "dmac-curation"
    assert out["plugin_sha"] == "abc123"
    assert out["schema_vintage"] == "2026-05-27"
    assert "lab" not in out


def test_migrate_v0_bumps_plugin_version():
    assert _lockfile.migrate_v0(V0)["plugin_version"] == _lockfile.PLUGIN_VERSION


def test_migrate_is_idempotent():
    once = _lockfile.migrate_v0(V0)
    assert _lockfile.migrate_v0(once) == once


def test_read_migrates_a_v0_file_on_disk(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(V0))
    data = _lockfile.read(tmp_path)
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "KAM"


def test_read_does_not_rewrite_the_file(tmp_path):
    """Migration is in-memory. Only an explicit write() touches disk."""
    p = tmp_path / ".dmac-curation.json"
    p.write_text(json.dumps(V0))
    before = p.read_text()
    _lockfile.read(tmp_path)
    assert p.read_text() == before


def test_read_returns_empty_v1_when_absent(tmp_path):
    assert _lockfile.read(tmp_path) == {
        "schema_version": 1,
        "plugin_version": _lockfile.PLUGIN_VERSION,
        "modes": {},
    }


def test_read_raises_on_malformed_json(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text("{ not json")
    with pytest.raises(_lockfile.LockfileError):
        _lockfile.read(tmp_path)


def test_read_raises_on_future_schema_version(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"schema_version": 99, "modes": {}}))
    with pytest.raises(_lockfile.LockfileError) as exc:
        _lockfile.read(tmp_path)
    assert "99" in str(exc.value)


def test_mode_returns_empty_dict_for_absent_mode(tmp_path):
    assert _lockfile.mode(_lockfile.read(tmp_path), "schema") == {}


def test_set_mode_creates_and_persists(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6, "lab": "ENG"})
    on_disk = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert on_disk["schema_version"] == 1
    assert on_disk["modes"]["pipeline"] == {"phase": 6, "lab": "ENG"}


def test_set_mode_merges_rather_than_replaces(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"lab": "ENG", "phase": 1})
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6})
    assert _lockfile.read(tmp_path)["modes"]["pipeline"] == {"lab": "ENG", "phase": 6}


def test_set_mode_leaves_other_modes_alone(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6})
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = _lockfile.read(tmp_path)
    assert data["modes"]["pipeline"] == {"phase": 6}
    assert data["modes"]["report"] == {"last_format": "GEO"}


def test_set_mode_upgrades_a_v0_file_in_place(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(V0))
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "KAM"
    assert data["modes"]["report"]["last_format"] == "GEO"


def test_write_ends_with_a_newline(tmp_path):
    _lockfile.write(tmp_path, {"schema_version": 1, "modes": {"b": {}, "a": {}}})
    assert (tmp_path / ".dmac-curation.json").read_text().endswith("\n")
