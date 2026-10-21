"""Retry policy of FairDomHubClient._request (no network: the session is faked).

A POST whose response times out may still have been applied server-side; re-sending
it created six identical assays on 2026-10-07. Creates must never be auto-retried
on an unknown outcome; reads still are.
"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "fdh"))
import fdh_api  # noqa: E402


class _Resp:
    def __init__(self, status, body=b'{"data": {"id": "1"}}'):
        self.status_code, self.content, self.url = status, body, "u"
        self.text = body.decode()

    def json(self):
        import json
        return json.loads(self.content)


class _Session:
    """Plays back a script of outcomes: an exception instance or a status code."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def request(self, method, url, **kw):
        self.calls.append((method, kw["timeout"]))
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return _Resp(out)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(fdh_api.time, "sleep", lambda s: None)
    c = fdh_api.FairDomHubClient(token="t", base_url="https://fdh.invalid")
    return c


def _fake(client, outcomes):
    client.session = _Session(outcomes)
    return client.session


@pytest.mark.parametrize("exc", [requests.ReadTimeout("slow"), requests.ConnectionError("x")])
def test_post_is_not_resent_after_network_error(client, exc):
    s = _fake(client, [exc, 201])
    with pytest.raises(type(exc)):
        client.post("assays", {"data": {}})
    assert len(s.calls) == 1


@pytest.mark.parametrize("status", [502, 503])
def test_post_is_not_resent_after_gateway_error(client, status):
    s = _fake(client, [status, 201])
    with pytest.raises(fdh_api.FDHError):
        client.post("assays", {"data": {}})
    assert len(s.calls) == 1


def test_patch_is_not_resent_after_timeout(client):
    s = _fake(client, [requests.ReadTimeout("slow"), 200])
    with pytest.raises(requests.ReadTimeout):
        client.patch("assays", 1, {"data": {}})
    assert len(s.calls) == 1


def test_post_with_explicit_retries_still_skips_timeouts(client):
    s = _fake(client, [requests.ReadTimeout("slow"), 201])
    with pytest.raises(requests.ReadTimeout):
        client._request("POST", "/assays", json_body={}, max_retries=3)
    assert len(s.calls) == 1


def test_post_retries_429_only_when_asked(client):
    s = _fake(client, [429, 201])
    assert client._request("POST", "/assays", json_body={}, max_retries=1).status_code == 201
    assert len(s.calls) == 2


def test_get_still_retries_transient_failures(client):
    s = _fake(client, [requests.ReadTimeout("slow"), 503, 200])
    assert client.get("assays", 1) == {"data": {"id": "1"}}
    assert len(s.calls) == 3


def test_get_gives_up_after_max_retries(client):
    s = _fake(client, [requests.ReadTimeout("slow")] * 6)
    with pytest.raises(requests.ReadTimeout):
        client.get("assays", 1)
    assert len(s.calls) == 6


def test_post_timeout_override(client):
    s = _fake(client, [201])
    client.post("assays", {"data": {}}, timeout=300)
    assert s.calls == [("POST", 300)]
    client.session.outcomes = [200]
    client.get("assays", 1)
    assert s.calls[-1] == ("GET", 60.0)
