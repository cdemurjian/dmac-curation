"""scripts/_config.py — the single project-config seam (P2)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _config  # noqa: E402


def test_plugin_root_is_the_checkout():
    assert _config.plugin_root() == REPO


def test_plugin_context_resolves_readonly_bundled_data():
    p = _config.plugin_context("sampletypes_db.json")
    assert p.exists()
    assert p.parent == REPO / "context"


def test_find_project_root_walks_up_to_the_lockfile(curation_project):
    nested = curation_project / "assay_sheets" / "4sheet_originals"
    assert _config.find_project_root(nested) == curation_project


def test_find_project_root_falls_back_to_cwd_when_no_lockfile(tmp_path):
    assert _config.find_project_root(tmp_path) == tmp_path


def test_find_project_root_never_returns_the_plugin(tmp_path, monkeypatch):
    """Walking up from a tmpdir must not land on the plugin checkout."""
    monkeypatch.chdir(tmp_path)
    assert _config.find_project_root() != REPO


def test_load_config_reads_lockfile_pipeline_mode(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.root == curation_project
    assert cfg.lab == "KAM"
    assert cfg.nextseek_project_id == 42


def test_load_config_derives_directory_paths(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.assay_sheets == curation_project / "assay_sheets"
    assert cfg.four_sheet_dir == curation_project / "assay_sheets" / "4sheet_originals"
    assert cfg.previous_metadata == curation_project / "previous_metadata"
    assert cfg.context == curation_project / "context"
    assert cfg.files == curation_project / "files"


def test_no_config_path_points_inside_the_plugin(curation_project):
    cfg = _config.load_config(curation_project)
    for name in ("root", "files", "manuscript", "previous_metadata",
                 "assay_sheets", "four_sheet_dir", "context"):
        value = getattr(cfg, name)
        assert REPO not in value.parents and value != REPO, (
            f"cfg.{name} = {value} is inside the plugin checkout"
        )


def test_overrides_win_over_lockfile(curation_project):
    cfg = _config.load_config(curation_project, lab="ENG", nextseek_project_id=7)
    assert cfg.lab == "ENG"
    assert cfg.nextseek_project_id == 7


def test_none_overrides_are_ignored(curation_project):
    """argparse defaults are None; they must not clobber lockfile values."""
    cfg = _config.load_config(curation_project, lab=None)
    assert cfg.lab == "KAM"


def test_master_workbook_globs_previous_metadata(curation_project):
    (curation_project / "previous_metadata" / "MetNet All 260527.xlsx").write_bytes(b"x")
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook is not None
    assert cfg.master_workbook.name == "MetNet All 260527.xlsx"


def test_master_workbook_is_none_when_absent(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook is None


def test_master_workbook_picks_most_recent_of_several(curation_project):
    import os, time
    older = curation_project / "previous_metadata" / "Lab All 250101.xlsx"
    newer = curation_project / "previous_metadata" / "Lab All 260527.xlsx"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    os.utime(older, (time.time() - 5000, time.time() - 5000))
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook == newer


def test_expected_counts_defaults_empty(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.expected_counts == {}


def test_expected_counts_parsed_from_lockfile(curation_project):
    lock = json.loads((curation_project / ".dmac-curation.json").read_text())
    lock["modes"]["pipeline"]["expected_counts"] = {"OOC": 122, "CEL": 2}
    (curation_project / ".dmac-curation.json").write_text(json.dumps(lock))
    cfg = _config.load_config(curation_project)
    assert cfg.expected_counts == {"OOC": 122, "CEL": 2}


def test_add_config_args_and_config_from_args(curation_project, monkeypatch):
    import argparse
    monkeypatch.chdir(curation_project)
    parser = argparse.ArgumentParser()
    _config.add_config_args(parser)
    args = parser.parse_args(["--lab", "WHI"])
    cfg = _config.config_from_args(args)
    assert cfg.lab == "WHI"
    assert cfg.root == curation_project


def test_parse_expected_counts_flag_format():
    assert _config.parse_expected_counts("OOC=122,CEL=2") == {"OOC": 122, "CEL": 2}
    assert _config.parse_expected_counts("") == {}
    assert _config.parse_expected_counts(None) == {}


def test_parse_expected_counts_rejects_malformed():
    with pytest.raises(ValueError):
        _config.parse_expected_counts("OOC")
    with pytest.raises(ValueError):
        _config.parse_expected_counts("OOC=notanumber")
