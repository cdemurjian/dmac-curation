"""Smoke + unit tests for fdh_api.py (no network, no credentials)."""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fdh" / "fdh_api.py"


def _run(*args):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=90,
    )


def test_help_lists_subcommands():
    r = _run("--help")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    for cmd in ("whoami", "search", "get", "list", "download-blob"):
        assert cmd in out, f"{cmd} missing from --help"


@pytest.mark.parametrize("cmd", ["whoami", "search", "get", "list", "download-blob"])
def test_subcommand_help(cmd):
    r = _run(cmd, "--help")
    assert r.returncode == 0, f"{cmd}: {r.stderr}"


def test_client_requires_token():
    prog = (
        "import sys; sys.path.insert(0, r'{d}')\n"
        "import fdh_api\n"
        "raised = False\n"
        "try:\n"
        "    fdh_api.FairDomHubClient(token=None)\n"
        "except ValueError:\n"
        "    raised = True\n"
        "assert raised, 'expected ValueError for missing token'\n"
        "print('ok')\n"
    ).format(d=str(SCRIPT.parent))
    r = subprocess.run(
        ["uv", "run", "--with", "requests", "python", "-"],
        input=prog, capture_output=True, text=True, timeout=90,
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
