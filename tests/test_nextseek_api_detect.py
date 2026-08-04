import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import nextseek_api as na  # noqa: E402


def test_list_projects_normalizes(monkeypatch):
    c = na.NExtSEEKClient(username="u", password="p")
    monkeypatch.setattr(c, "_get", lambda path, params=None: {
        "data": [
            {"id": "10", "type": "projects", "attributes": {"title": "CSBC"}},
            {"id": "4", "attributes": {"title": "MetNet"}},
        ]})
    ps = c.list_projects()
    assert {"id": 10, "title": "CSBC"} in ps
    assert {"id": 4, "title": "MetNet"} in ps
