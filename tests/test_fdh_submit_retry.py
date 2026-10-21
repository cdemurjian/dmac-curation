"""Retry policy of submit.py's write helpers (no network: requests is faked).

A POST whose response times out may still have been applied server-side; re-sending
it created six identical assays on 2026-10-07. submit.py had its own copy of the
retry loop fixed in fdh_api.py, which also retried 4xx because raise_for_status()
sat inside the `except RequestException`. Writes now retry 429 only.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
import requests

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fdh" / "submit.py"


def _stub_missing_deps():
    """submit.py is a uv --script with deps the test env lacks; stub only those."""
    def missing(name):
        try:
            importlib.import_module(name)
            return False
        except ImportError:
            return True

    if missing("questionary"):
        sys.modules["questionary"] = types.ModuleType("questionary")
    if missing("rapidfuzz"):
        rf = types.ModuleType("rapidfuzz")
        rf.process = types.SimpleNamespace()
        sys.modules["rapidfuzz"] = rf
    if missing("rich"):
        class _Console:
            def print(self, *a, **k):
                pass

            def rule(self, *a, **k):
                pass

        rich = types.ModuleType("rich")
        console = types.ModuleType("rich.console")
        console.Console = _Console
        table = types.ModuleType("rich.table")
        table.Table = object
        sys.modules.update({"rich": rich, "rich.console": console, "rich.table": table})



_stub_missing_deps()
_spec = importlib.util.spec_from_file_location("fdh_submit", SCRIPT)
submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(submit)


class _Resp:
    def __init__(self, status, body=None):
        body = body if body is not None else {"data": {"id": "1", "attributes": {"title": "t"}}}
        self.status_code, self.text = status, json.dumps(body)
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class _Requests:
    """Stands in for the `requests` module inside submit.py. Plays back a script of
    outcomes per call: an exception instance, a status code, or a _Resp."""

    exceptions = requests.exceptions

    def __init__(self, outcomes, gets=()):
        self.outcomes, self.gets, self.calls = list(outcomes), list(gets), []

    def _next(self, queue):
        out = queue.pop(0)
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, _Resp) else _Resp(out)

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw["timeout"]))
        return self._next(self.outcomes)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw["timeout"]))
        return self._next(self.gets)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(submit.time, "sleep", lambda s: None)

    def install(outcomes, gets=()):
        r = _Requests(outcomes, gets)
        monkeypatch.setattr(submit, "requests", r)
        return r
    return install


def _writes(r):
    return [c for c in r.calls if c[0] != "GET"]


@pytest.mark.parametrize("exc", [requests.ReadTimeout("slow"), requests.ConnectionError("x")])
def test_post_is_not_resent_after_network_error(fake, exc):
    r = fake([exc, 201])
    with pytest.raises(type(exc)):
        submit._post_jsonapi("https://fdh.invalid", "/assays", "t", {"data": {}})
    assert len(r.calls) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 422, 404])
def test_post_is_not_resent_after_error_status(fake, status):
    r = fake([status, 201])
    with pytest.raises(requests.HTTPError):
        submit._post_jsonapi("https://fdh.invalid", "/assays", "t", {"data": {}})
    assert len(r.calls) == 1


def test_patch_is_not_resent_after_timeout(fake):
    r = fake([requests.ReadTimeout("slow"), 200])
    with pytest.raises(requests.ReadTimeout):
        submit._patch_jsonapi("https://fdh.invalid/assays/1", "t", {"data": {}})
    assert r.calls == [("PATCH", "https://fdh.invalid/assays/1", 60)]


def test_patch_is_not_resent_after_422(fake):
    r = fake([422, 200])
    with pytest.raises(requests.HTTPError):
        submit._patch_jsonapi("https://fdh.invalid/assays/1", "t", {"data": {}})
    assert len(r.calls) == 1


def test_post_retries_429(fake):
    r = fake([429, 429, 201])
    assert submit._post_jsonapi("https://fdh.invalid", "/assays", "t", {})["data"]["id"] == "1"
    assert len(r.calls) == 3


def test_post_gives_up_on_429_after_max_retries(fake):
    r = fake([429] * 3)
    with pytest.raises(requests.HTTPError):
        submit._post_jsonapi("https://fdh.invalid", "/assays", "t", {}, max_retries=2)
    assert len(r.calls) == 3


@pytest.mark.parametrize("fn", ["create_sample", "create_sample_type"])
def test_sample_creates_are_not_resent_after_timeout(fake, fn):
    r = fake([requests.ReadTimeout("slow"), 201])
    with pytest.raises(requests.ReadTimeout):
        getattr(submit, fn)("https://fdh.invalid", "t", {"data": {}})
    assert len(r.calls) == 1 and r.calls[0][2] == 120


def _study(*assays):
    return _Resp(200, {"data": [{"id": i, "attributes": {"title": t}} for i, t in assays]})


def test_bulk_assays_rereads_study_instead_of_resending(fake):
    # Study starts with an older "A" (id 5). POST for "A" times out, but it landed as 9.
    r = fake([requests.ReadTimeout("slow")],
             gets=[_study(("5", "A")), _study(("5", "A")), _study(("5", "A"), ("9", "A"))])
    df = submit.bulk_create_assays_df("https://fdh.invalid", "t", "42", ["A"])
    assert len(_writes(r)) == 1
    assert df.to_dict("records") == [{"assay_title": "A", "assay_id": "9"}]


def test_bulk_assays_stops_when_unknown_post_never_lands(fake):
    r = fake([201, requests.ReadTimeout("slow"), 201],
             gets=[_study()] + [_study(("1", "t"))] * 6)
    with pytest.raises(RuntimeError, match="did not appear"):
        submit.bulk_create_assays_df("https://fdh.invalid", "t", "42", ["t", "B", "C"])
    assert len(_writes(r)) == 2  # "C" is never attempted


def test_bulk_assays_does_not_reread_on_422(fake):
    r = fake([422], gets=[_study()])
    with pytest.raises(requests.HTTPError):
        submit.bulk_create_assays_df("https://fdh.invalid", "t", "42", ["A"])
    assert [c[0] for c in r.calls] == ["GET", "POST"]
