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


def test_find_project_root_refuses_when_cwd_is_the_plugin_root(monkeypatch):
    """Standing in the plugin checkout with no lockfile must refuse loudly.

    This is the P1 bug in its purest form: start == _PLUGIN_ROOT would fall
    through to `return start` and hand back the plugin as "the project".
    """
    monkeypatch.chdir(_config.plugin_root())
    with pytest.raises(_config.ProjectRootError):
        _config.find_project_root()


def test_find_project_root_refuses_inside_a_plugin_subdir(monkeypatch):
    """A plugin subdir with no lockfile above it must also refuse."""
    subdir = _config.plugin_root() / "scripts" / "fdh"
    assert subdir.is_dir(), "fixture assumes scripts/fdh exists in the checkout"
    monkeypatch.chdir(subdir)
    with pytest.raises(_config.ProjectRootError):
        _config.find_project_root()


def test_find_project_root_honours_explicit_start_from_the_plugin(
        curation_project, monkeypatch):
    """Even standing in the plugin, an explicit start with a lockfile resolves."""
    monkeypatch.chdir(_config.plugin_root())
    nested = curation_project / "assay_sheets" / "4sheet_originals"
    assert _config.find_project_root(nested) == curation_project


def test_find_project_root_honours_a_lockfile_inside_a_plugin_subtree(
        tmp_path, monkeypatch):
    """The pathological edge: a real lockfile inside the plugin subtree is honoured.

    _PLUGIN_ROOT is monkeypatched onto a tmp tree so the real checkout is never
    touched. A lockfile placed *inside* that fake plugin, with cwd a subdir of
    it, must resolve to the lockfile dir rather than raise — someone
    deliberately made a project there.
    """
    monkeypatch.setattr(_config, "_PLUGIN_ROOT", tmp_path)
    (tmp_path / _config.LOCKFILE_NAME).write_text("{}")
    subdir = tmp_path / "scripts" / "fdh"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    assert _config.find_project_root() == tmp_path


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


def test_master_workbook_embedded_date_beats_mtime(curation_project):
    """Selection is by embedded YYMMDD date, NOT mtime, when names carry dates.

    Fixture deliberately crosses the two signals: the file with the OLDER
    embedded date (250101) is given the NEWER mtime, and the file with the
    NEWER embedded date (260527) is given the OLDER mtime. A pure-mtime strategy
    would pick 250101; the assertion pins that 260527 (newest date) wins.
    """
    import os, time
    pm = curation_project / "previous_metadata"
    date_old = pm / "Lab All 250101.xlsx"   # older date, newer mtime
    date_new = pm / "Lab All 260527.xlsx"   # newer date, older mtime
    date_old.write_bytes(b"x")
    date_new.write_bytes(b"x")
    now = time.time()
    os.utime(date_old, (now, now))                 # newest mtime
    os.utime(date_new, (now - 9000, now - 9000))   # oldest mtime
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook == date_new


def test_master_workbook_falls_back_to_mtime_for_undated_names(curation_project):
    """Version-named masters have no parseable date, so newest mtime decides."""
    import os, time
    pm = curation_project / "previous_metadata"
    older = pm / "YufeiCui_AllMetadata_v1.xlsx"
    newer = pm / "IntravChip_AllMetadata_v1.xlsx"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    now = time.time()
    os.utime(older, (now - 9000, now - 9000))
    os.utime(newer, (now, now))
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook == newer


def test_master_workbook_warns_on_multiple_candidates(curation_project, capsys):
    """More than one candidate must surface a stderr warning, not silently pick.

    Mirrors the real srp/lee hazard: four LP-NAR-All-Metadata* masters in one
    dir. The warning must name every candidate and the one selected.
    """
    pm = curation_project / "previous_metadata"
    names = [
        "LP-NAR-All-Metadata-v1.xlsx",
        "LP-NAR-All-Metadata-v2.xlsx",
        "LP-NAR-All-Metadata-v3.xlsx",
        "LP-NAR-All-Metadata-vFinal.xlsx",
    ]
    for n in names:
        (pm / n).write_bytes(b"x")
    cfg = _config.load_config(curation_project)
    err = capsys.readouterr().err
    assert "master workbooks" in err
    for n in names:
        assert n in err, f"warning omitted candidate {n}:\n{err}"
    assert "selected" in err
    assert cfg.master_workbook is not None
    assert cfg.master_workbook.name in names


def test_master_workbook_single_candidate_is_silent(curation_project, capsys):
    """A lone candidate must NOT emit the ambiguity warning."""
    (curation_project / "previous_metadata" / "MetNet All 260527.xlsx").write_bytes(b"x")
    _config.load_config(curation_project)
    assert "master workbooks" not in capsys.readouterr().err


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
