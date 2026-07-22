"""The identity string and version live in three files. Keep them equal.

Toolkit spec section 1: the description is what skill activation matches on,
so a pipeline-only description makes schema and report modes invisible.
"""
import json
import pytest
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

CANONICAL_DESCRIPTION = (
    "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, "
    "PI-facing. Modes are pipeline (13 commands, 11 phases from inventory through "
    "sample tree, build, consolidate, QA, deposit, retrieve, to email PI), fdh "
    "(FairDomHub upload and direct API), schema (sample type authoring and "
    "controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts). "
    "Activate when working in a directory containing files/, manuscript/, "
    "previous_metadata/, or any .dmac-curation.json lockfile, or when the user "
    "mentions NExtSEEK, FairDomHub, curation, sample types, or a GEO/SRA/PRIDE "
    "submission."
)


def _plugin_json():
    return json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())


def _marketplace_entry():
    doc = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in doc["plugins"] if p["name"] == "dmac-curation"]
    assert entries, "dmac-curation not listed in marketplace.json"
    return entries[0]


def _skill_frontmatter():
    text = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert text.startswith("---"), "SKILL.md has no frontmatter"
    block = text.split("---")[1]
    out, key = {}, None
    for line in block.splitlines():
        if line.startswith(("name:", "description:")):
            key, _, value = line.partition(":")
            key = key.strip()
            out[key] = value.strip()
        elif key and line.startswith((" ", "\t")):
            out[key] += " " + line.strip()
    return out


def test_plugin_json_description_is_canonical():
    assert _plugin_json()["description"] == CANONICAL_DESCRIPTION


def test_marketplace_description_is_canonical():
    assert _marketplace_entry()["description"] == CANONICAL_DESCRIPTION


def test_skill_description_is_canonical():
    assert _skill_frontmatter()["description"] == CANONICAL_DESCRIPTION


def test_description_is_yaml_safe_frontmatter():
    """The SKILL.md description lives in unquoted YAML frontmatter, which the
    skill loader parses. A mid-string ': ' (colon-space) is read by YAML as a
    mapping and makes the whole frontmatter fail to load -- the skill then does
    not activate at all. The hand-rolled parser in _skill_frontmatter() splits
    on the first colon and so CANNOT catch this; an earlier canonical string
    ('Modes: pipeline', '11 phases: inventory') passed every other test here
    while being YAML-invalid. This guards that exact regression.
    """
    assert ": " not in CANONICAL_DESCRIPTION, (
        "canonical description contains a colon-space; unquoted YAML frontmatter "
        "would read it as a mapping and fail to load"
    )
    yaml = pytest.importorskip("yaml")
    fm = (REPO / "skills" / "curation" / "SKILL.md").read_text().split("---")[1]
    loaded = yaml.safe_load(fm)
    assert loaded["description"] == CANONICAL_DESCRIPTION, (
        "strict yaml.safe_load did not recover the canonical description from "
        "SKILL.md frontmatter"
    )


def test_versions_agree_across_plugin_marketplace_and_lockfile():
    v = _plugin_json()["version"]
    assert _marketplace_entry()["version"] == v
    assert _lockfile.PLUGIN_VERSION == v


def test_version_is_the_toolkit_release():
    assert _plugin_json()["version"] == "0.3.0"


def test_description_names_every_mode():
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in CANONICAL_DESCRIPTION, f"{mode} missing from description"


def test_description_does_not_claim_thirteen_phases():
    """Phases 4 and 8 are deleted in Task 16; 13 commands drive 11 phases."""
    assert "13-phase" not in CANONICAL_DESCRIPTION


def test_curate_init_does_not_hardcode_a_stale_version():
    """curate-init.md:46-59 hardcoded 0.1.0 while plugin.json said 0.2.0."""
    doc = (REPO / "commands" / "curate-init.md").read_text()
    for stale in ('"plugin_version": "0.1.0"', '"plugin_version": "0.2.0"',
                  '"plugin_version": "0.3.0"'):
        assert stale not in doc, f"init must read the version, not restate {stale}"
