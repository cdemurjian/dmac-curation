"""/curate-init must be additive, not all-or-nothing (toolkit spec section 3).

The command is markdown, so these assert on the CONTRACT it describes plus the
lockfile behaviour it delegates to _lockfile.py.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

INIT = REPO / "commands" / "curate-init.md"


def test_init_no_longer_refuses_on_existing_lockfile():
    text = INIT.read_text()
    assert "must NOT already exist" not in text
    assert "abort unless user adds `--force`" not in text


def test_init_documents_the_additive_contract():
    text = INIT.read_text()
    for phrase in ("Create what is missing", "never overwrite", "--mode"):
        assert phrase in text, f"curate-init.md must document {phrase!r}"


def test_init_does_not_restate_the_plugin_version():
    text = INIT.read_text()
    for stale in ('"plugin_version": "0.1.0"', '"plugin_version": "0.2.0"',
                  '"plugin_version": "0.3.0"'):
        assert stale not in text
    assert "_lockfile.py" in text, "init must delegate lockfile writing"


def test_init_writes_a_v1_lockfile_shape():
    text = INIT.read_text()
    assert '"schema_version": 1' in text
    assert '"modes"' in text


def test_scaffold_render_is_tied_to_pipeline_mode():
    """schema/report must not render the pipeline scaffold (Task 13 fix).

    The render step (directories + templates) is gated on pipeline mode so an
    agent executing `--mode schema` in a bare dir writes nothing but a lockfile.
    """
    text = INIT.read_text()
    assert "only in pipeline mode" in text


def test_adding_a_mode_preserves_the_existing_one(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"lab": "KAM", "phase": 6})
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["modes"]["pipeline"] == {"lab": "KAM", "phase": 6}
    assert data["modes"]["report"] == {"last_format": "GEO"}


def test_init_on_a_v0_project_upgrades_without_data_loss(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps({
        "plugin_name": "dmac-curation", "plugin_version": "0.1.0",
        "lab": "ENG", "pi": "lee", "nextseek_project_id": 7,
    }))
    _lockfile.set_mode(tmp_path, "schema", {})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "ENG"
    assert data["modes"]["pipeline"]["nextseek_project_id"] == 7
    assert "schema" in data["modes"]


def test_phases_md_phase0_describes_additive_init():
    text = (REPO / "skills" / "curation" / "PHASES.md").read_text()
    phase0 = text.split("## Phase 0", 1)[1].split("\n## ", 1)[0]
    assert "Verify cwd is empty" not in phase0
    assert "additive" in phase0.lower()
