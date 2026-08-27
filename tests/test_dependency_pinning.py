"""The suite's dependencies must be pinned, not merely lower-bounded.

The pipeline reproduced byte-identically across a pandas major version. That is
luck: every PEP-723 header in scripts/assay_hygiene/ says `pandas>=2.0` and
nothing holds an upper bound or records what was actually resolved.
"""
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_a_pyproject_exists():
    assert (REPO / "pyproject.toml").is_file()


def test_a_lockfile_exists():
    assert (REPO / "uv.lock").is_file(), "run `uv lock`"


def test_the_pinned_deps_cover_what_the_scripts_import():
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    declared = " ".join(data["project"]["dependencies"])
    for package in ("pandas", "pyarrow", "openpyxl", "jinja2", "requests"):
        assert package in declared, f"{package} is imported but not declared"


def test_the_lockfile_records_a_resolved_pandas():
    text = (REPO / "uv.lock").read_text()
    assert 'name = "pandas"' in text, "pandas is not resolved in the lockfile"


def test_pyproject_version_matches_plugin_json():
    """The fourth copy of the version, and the only one nothing asserted.

    test_identity_sync.py pins plugin.json, marketplace.json and _lockfile.py to
    each other; pyproject.toml sat outside that net and drifted two releases
    behind (0.3.0 against 0.4.0) without a single test going red.
    """
    import json
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert data["project"]["version"] == manifest["version"]
