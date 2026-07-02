"""Structural checks: the FDH spec is vendored and the package dir exists."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_spec_vendored():
    spec = REPO / "context" / "full-fdh-openapi-spec.yaml"
    assert spec.exists(), "spec must be moved into context/"
    # The vendored file may start with a YAML document marker ("---")
    # before the "openapi:" key, so check the first few lines.
    head = spec.read_text().splitlines()[:5]
    assert any(line.startswith("openapi:") for line in head), (
        f"unexpected head, no 'openapi:' line found: {head!r}"
    )


def test_spec_not_left_in_working():
    assert not (REPO / "working" / "full-fdh-openapi-spec.yaml").exists()


def test_package_scaffold_present():
    assert (REPO / "scripts" / "fdh" / "__init__.py").exists()
    assert (REPO / "scripts" / "fdh" / "generated" / "__init__.py").exists()
