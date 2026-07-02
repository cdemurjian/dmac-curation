"""FDH.md, REGISTRY.md scaffold, and the SKILL.md pointer are present and wired."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_fdh_reference_exists():
    f = REPO / "skills" / "curation" / "FDH.md"
    assert f.exists()
    text = f.read_text()
    for anchor in ("Module 1", "Module 2", "reuse-or-generate", "fdh_api_index.json",
                   "yaml_lines", "dry-run"):
        assert anchor in text, f"FDH.md missing: {anchor}"


def test_registry_scaffold():
    f = REPO / "scripts" / "fdh" / "generated" / "REGISTRY.md"
    assert f.exists()
    text = f.read_text()
    assert "| Script | Purpose |" in text


def test_skill_points_to_fdh():
    text = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert "FDH.md" in text
    assert "/fdh-upload" in text and "/fdh-api" in text
