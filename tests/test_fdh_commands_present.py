"""The two FDH command files exist, have frontmatter, and reference real paths."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

REFERENCED = [
    "scripts/fdh/submit.py",
    "scripts/fdh/fdh_api.py",
    "scripts/fdh/build_api_index.py",
    "context/fdh_api_index.json",
    "scripts/fdh/generated/REGISTRY.md",
]


def test_command_files_exist_with_frontmatter():
    for name in ("fdh-upload.md", "fdh-api.md"):
        f = COMMANDS / name
        assert f.exists(), f"missing {f}"
        text = f.read_text()
        assert text.startswith("---"), f"{name} missing frontmatter"
        assert "description:" in text.split("---")[1], f"{name} missing description"


def test_referenced_paths_exist():
    # Union of paths referenced across both command files must all resolve.
    blob = (COMMANDS / "fdh-upload.md").read_text() + (COMMANDS / "fdh-api.md").read_text()
    for rel in REFERENCED:
        assert rel in blob, f"expected {rel} to be referenced in the FDH commands"
        assert (REPO / rel).exists(), f"referenced path does not exist: {rel}"
