"""Harvested API fixtures, scrubbed and committed."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures" / "nextseek"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import scrub_fixture as sf  # noqa: E402

HARVESTED = ["report_metadata.json", "protocols.json", "protocol_files.json"]


# ---- the scrubber, testable without any fixture ---------------------------

def test_scrub_redacts_secret_looking_keys():
    out = sf.scrub({"token": "abc", "api_key": "d", "Authorization": "Bearer x",
                    "name": "keep me"})
    assert out["token"] == sf.REDACTED
    assert out["api_key"] == sf.REDACTED
    assert out["Authorization"] == sf.REDACTED
    assert out["name"] == "keep me"


def test_scrub_recurses_into_lists_and_dicts():
    out = sf.scrub({"a": [{"password": "p"}, {"ok": 1}]})
    assert out["a"][0]["password"] == sf.REDACTED
    assert out["a"][1]["ok"] == 1


def test_scrub_rewrites_localhost_urls():
    out = sf.scrub({"url": "http://localhost:8000/nextseek_api/sops/1/"})
    assert "localhost" not in out["url"]
    assert out["url"].endswith("/nextseek_api/sops/1/")


def test_scrub_strips_basic_auth_from_urls():
    out = sf.scrub({"url": "https://user:hunter2@nextseek.mit.edu/x"})
    assert "hunter2" not in out["url"]


def test_scrub_leaves_ordinary_values_alone():
    assert sf.scrub({"n": 3, "b": True, "s": "D.SEQ-1"}) == {
        "n": 3, "b": True, "s": "D.SEQ-1"}


# ---- the fixtures themselves ---------------------------------------------

@pytest.mark.parametrize("name", HARVESTED)
def test_fixture_present(name):
    if not (FIX / name).is_file():
        pytest.skip(f"{name} not harvested yet; see tests/fixtures/nextseek/README.md")


@pytest.mark.parametrize("name", HARVESTED)
def test_fixture_carries_no_credentials(name):
    p = FIX / name
    if not p.is_file():
        pytest.skip("not harvested yet")
    text = p.read_text().lower()
    for leak in ("password", "bearer ", "apikey token=", "localhost", "127.0.0.1"):
        assert leak not in text, f"{name} still contains {leak!r}"


def test_retrieve_fixture_has_the_five_level_nesting():
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    assert "data" in doc and "data" in doc["data"]
    group = doc["data"]["data"][0]
    assert "samples" in group
    assert "metadata" in group["samples"][0]


def test_adapter_handles_the_real_response_shape():
    """The point of harvesting: the adapter is exercised against a shape the
    API actually returns, not one written from memory."""
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    got = ad.adapt_uids(["fixture"], fetch=lambda uids: doc)
    assert got.samples
    for s in got.samples:
        assert s.uid
        assert isinstance(s.metadata, dict)


def test_lineage_resolves_in_the_real_fixture():
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    got = ad.adapt_uids(["fixture"], fetch=lambda uids: doc)
    by_uid = ad.index_by_uid(got)
    assert any(s.parent and s.parent in by_uid for s in got.samples), (
        "no resolvable Parent pointer in the fixture; lineage walking is "
        "untested against real data")


def test_readme_documents_the_harvest_procedure():
    text = (FIX / "README.md").read_text()
    assert "outputs.py" in text
    assert "harvest" in text.lower()
    assert "scrub_fixture.py" in text
