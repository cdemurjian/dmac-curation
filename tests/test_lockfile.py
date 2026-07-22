"""Lockfile schema v1 and v0 -> v1 migration (toolkit spec section 3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _config  # noqa: E402
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


# ---------------------------------------------------------------------------
# Fix pass: read() is the validation chokepoint. Every malformed-but-parseable
# shape must surface as LockfileError, never a raw TypeError/AttributeError, so
# _config's single `except LockfileError` degrades cleanly instead of crashing
# a curation script with a traceback.
# ---------------------------------------------------------------------------

# name -> a shape that used to escape read() as the WRONG exception type.
MALFORMED_SHAPES = {
    "string_version": {"schema_version": "1", "modes": {}},   # was TypeError
    "bool_version": {"schema_version": True, "modes": {}},     # bool is an int
    "list_modes": {"schema_version": 1, "modes": []},          # was AttributeError
    "string_modes": {"schema_version": 1, "modes": "x"},       # was AttributeError
    "mode_value_not_a_dict": {"schema_version": 1, "modes": {"pipeline": "nope"}},
}


@pytest.mark.parametrize("shape", list(MALFORMED_SHAPES))
def test_read_raises_lockfileerror_not_a_raw_exception(tmp_path, shape):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(MALFORMED_SHAPES[shape]))
    with pytest.raises(_lockfile.LockfileError):
        _lockfile.read(tmp_path)


@pytest.mark.parametrize("shape", list(MALFORMED_SHAPES))
def test_load_config_degrades_on_malformed_lockfile(tmp_path, shape):
    """load_config MUST return an empty ProjectConfig, never raise, on a
    corrupt or hand-edited lockfile — a curation script keeps running."""
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(MALFORMED_SHAPES[shape]))
    cfg = _config.load_config(tmp_path)
    assert isinstance(cfg, _config.ProjectConfig)
    assert cfg.lab is None
    assert cfg.pi is None
    assert cfg.nextseek_project_id is None
    assert cfg.expected_counts == {}


def test_load_config_degrades_on_string_version(tmp_path):
    """The exact review repro: a string schema_version must not TypeError out."""
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"schema_version": "1", "modes": {"pipeline": {"lab": "KAM"}}}))
    cfg = _config.load_config(tmp_path)
    assert cfg.lab is None  # degraded, not read from the corrupt file


def test_load_config_degrades_on_list_modes(tmp_path):
    """The exact review repro: a list `modes` must not AttributeError out."""
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"schema_version": 1, "modes": []}))
    cfg = _config.load_config(tmp_path)
    assert cfg.lab is None


def test_mode_returns_empty_for_a_non_dict_modes():
    """Second-layer defence: mode() never raises on a hand-built bad dict."""
    assert _lockfile.mode({"modes": []}, "pipeline") == {}
    assert _lockfile.mode({"modes": "x"}, "pipeline") == {}
    assert _lockfile.mode({"modes": {"pipeline": "nope"}}, "pipeline") == {}


def test_read_still_degrades_a_future_float_version(tmp_path):
    """Intended case must not regress: a future float version -> LockfileError."""
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"schema_version": 2.0, "modes": {}}))
    with pytest.raises(_lockfile.LockfileError):
        _lockfile.read(tmp_path)


def test_read_still_rejects_a_top_level_array(tmp_path):
    """Intended case must not regress: a top-level JSON array -> LockfileError."""
    (tmp_path / ".dmac-curation.json").write_text(json.dumps([1, 2, 3]))
    with pytest.raises(_lockfile.LockfileError):
        _lockfile.read(tmp_path)


def test_migrate_v0_preserves_a_pre_existing_modes_dict():
    """Finding 2: a hybrid (flat v0 keys + a modes dict) must not lose modes.

    The old loop set out['modes'] from the hybrid's modes mid-loop, then
    unconditionally overwrote it with {'pipeline': ...}, silently dropping the
    report section. Pin that both survive.
    """
    hybrid = {"lab": "KAM", "modes": {"report": {"last_format": "GEO"}}}
    out = _lockfile.migrate_v0(hybrid)
    assert out["modes"]["report"] == {"last_format": "GEO"}      # preserved
    assert out["modes"]["pipeline"]["lab"] == "KAM"              # flat key folded in


def test_read_migrates_a_hybrid_v0_with_modes_on_disk(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"lab": "KAM", "modes": {"report": {"last_format": "GEO"}}}))
    data = _lockfile.read(tmp_path)
    assert data["modes"]["report"] == {"last_format": "GEO"}
    assert data["modes"]["pipeline"]["lab"] == "KAM"
