"""P1: no script may read or write inside the plugin checkout.

Each script is run from a tmpdir curation project. The plugin_sentinel
fixture hashes the whole plugin tree (files *and* directories) before and
after and fails on any change. Scripts that need inputs get them inside the
tmpdir, never in the plugin.

The three assertion families:

  test_script_writes_nothing_in_plugin
      Behavioural: run the script, sentinel asserts the checkout is byte- and
      entry-identical afterwards.

  test_script_does_not_reference_plugin_paths_in_output
      Behavioural: a path under the plugin checkout appearing in stdout/stderr
      means the script resolved a PROJECT path against the plugin install dir.
      This is the assertion that catches the *read* half of P1, which the
      sentinel (a write guard) cannot see.

  test_no_script_anchors_project_paths_at_the_plugin_dir
      Static: the defect itself. Several scripts only reach their buggy path
      resolution when given inputs they do not have here, so the behavioural
      tests alone under-report. This one is deterministic and exhaustive.

NOTE ON ARGV (deviation from the task brief): the brief's argv table passed
``--assay-sheets`` to consolidate_to_flat.py and ``--upload`` to
qa_flat_sheets.py. Neither flag exists -- argparse would exit 2 with a usage
string that contains no plugin path, so both cases would have gone falsely
GREEN and the harness would have licensed a no-op Task 8. The argv below is
the minimum each script accepts to reach its *defaulted* project paths, with
every explicitly-passed input living inside the tmpdir project. In particular
no script is handed a path override for the directory whose default is the
bug.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE_XLSX = REPO / "tests" / "fixtures" / "sample.xlsx"

# A metadata workbook inside the project, so scripts that glob
# <ROOT>/previous_metadata/*All*.xlsx don't bail before reaching the
# path-resolution we are testing. Passed as a cwd-relative path.
PROJECT_META = "previous_metadata/Project_All_Metadata.xlsx"
PROJECT_GSM_CSV = "gsm_roster.txt"

# Every script that resolved paths against the plugin dir before Task 8,
# with an argv that should be a no-op or a dry-run inside the project.
PLUGIN_ANCHORED = [
    ("scripts/consolidate_to_flat.py", []),
    ("scripts/qa_flat_sheets.py", ["assay_sheets/ArmA.xlsx"]),
    ("scripts/stage_zenodo.py", ["--metadata-xlsx", PROJECT_META]),
    ("scripts/apply_zenodo_links.py",
     ["--record-id", "1", "--metadata-xlsx", PROJECT_META]),
    ("scripts/apply_geo_accessions.py",
     ["--gse-bulk", "GSE000000", "--gsm-csv", PROJECT_GSM_CSV]),
    ("scripts/review_metadata_vs_uploads.py",
     ["--metadata-xlsx", PROJECT_META]),
    ("scripts/build_retrieve.py", ["--assay-sheets", "assay_sheets"]),
]

# Scripts that must not compute a *project* path from their own location.
# scripts/fdh/generated/* are excluded: their parent.parent is a sys.path
# insert for the sibling fdh package, not a project path.
PROJECT_SCRIPTS = sorted(
    p for p in REPO.glob("scripts/**/*.py")
    if "generated" not in p.relative_to(REPO).parts
)

# Directories/files that belong to the *curation project*, never to the plugin
# install. context/ and templates/ are deliberately absent: those are
# plugin-owned read-only assets and may legitimately be resolved from __file__.
PROJECT_DIR_NAMES = (
    "assay_sheets", "previous_metadata", "files", "GEO", "Zenodo_upload",
    "manuscript", "Assets", "images_to_upload_to_omero", "omero_images.csv",
    "RETRIEVE.TXT", "manifest.csv", "FILE_INDEX.md", "SAMPLE_TREE.md",
)

# A module-level ROOT/REPO derived from __file__ joined to a project path.
_ANCHOR_JOIN = re.compile(
    r"\b(?:ROOT|REPO)\b\s*(?:/|,)\s*[\"'](?:" +
    "|".join(re.escape(n) for n in PROJECT_DIR_NAMES) + r")"
)
# ...or joined to a *variable*, e.g. os.path.join(REPO, upload), which turns a
# user-supplied relative project path into a plugin path.
_ANCHOR_VAR_JOIN = re.compile(
    r"os\.path\.join\(\s*(?:ROOT|REPO)\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*\)"
)


def _prepare(cwd: Path) -> None:
    """Materialise the project-local inputs the argv above refers to."""
    meta = cwd / PROJECT_META
    if not meta.exists():
        meta.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_XLSX, meta)
    gsm = cwd / PROJECT_GSM_CSV
    if not gsm.exists():
        gsm.write_text("GSM0000001 Sample_One_D000001\n")


def _run(script_rel: str, argv: list[str], cwd: Path):
    _prepare(cwd)
    return subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), *argv],
        cwd=cwd, capture_output=True, text=True, timeout=600,
    )


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_writes_nothing_in_plugin(script_rel, argv, curation_project,
                                         plugin_sentinel):
    """The script may fail (missing inputs is fine). It may not touch the plugin."""
    _run(script_rel, argv, curation_project)
    # plugin_sentinel asserts on teardown.


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_does_not_reference_plugin_paths_in_output(script_rel, argv,
                                                          curation_project):
    """A path under the plugin checkout appearing in output means the script
    resolved a PROJECT path against the plugin install dir."""
    result = _run(script_rel, argv, curation_project)
    blob = result.stdout + result.stderr
    plugin_str = str(REPO)
    leaked = [
        line for line in blob.splitlines()
        if plugin_str in line
        # The script's own path legitimately appears in tracebacks and usage.
        and script_rel.split("/")[-1] not in line
        and "/context/" not in line          # read-only plugin context is allowed
        and "/templates/" not in line        # read-only plugin templates are allowed
    ]
    assert not leaked, (
        f"{script_rel} resolved a project path against the plugin dir:\n"
        + "\n".join(leaked[:10])
    )


@pytest.mark.parametrize(
    "script_rel",
    [str(p.relative_to(REPO)) for p in PROJECT_SCRIPTS],
)
def test_no_script_anchors_project_paths_at_the_plugin_dir(script_rel):
    """P1 in its source form: a project directory joined onto a __file__ root.

    Task 8 replaces these with a cwd-anchored project root (the shape
    build_retrieve.py already uses). Reading plugin-owned assets from
    __file__ stays fine -- only *project* paths are forbidden.
    """
    text = (REPO / script_rel).read_text()
    hits = [
        f"{script_rel}:{i}: {line.strip()}"
        for i, line in enumerate(text.splitlines(), 1)
        if _ANCHOR_JOIN.search(line) or _ANCHOR_VAR_JOIN.search(line)
    ]
    assert not hits, (
        f"{script_rel} anchors project paths at the plugin install dir:\n"
        + "\n".join(hits)
    )


def test_reference_implementations_are_already_clean(curation_project,
                                                     plugin_sentinel):
    """build_retrieve.py and fdh_api.py are the models Task 8 refactors toward."""
    r = _run("scripts/build_retrieve.py",
             ["--assay-sheets", "assay_sheets", "--output", "RETRIEVE.TXT"],
             curation_project)
    assert r.returncode == 0, r.stderr
    assert (curation_project / "RETRIEVE.TXT").exists()
