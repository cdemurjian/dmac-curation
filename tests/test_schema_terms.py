"""BioPortal term resolution. Suggests, never binds; degrades without a key."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import terms as st  # noqa: E402

FAKE_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/NCIT_C16403",
         "prefLabel": "Cell Line",
         "links": {"ontology": "http://data.bioontology.org/ontologies/NCIT"},
         "definition": ["A cell culture derived from a single cell."]},
        {"@id": "http://purl.obolibrary.org/obo/OBI_0001876",
         "prefLabel": "cell line",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
    ]
}


class FakeHTTP:
    """Stand-in for the HTTP getter. Records the URL it was asked for."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.payload


def test_search_returns_empty_without_a_key(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    assert st.search_terms("cell line") == []


def test_search_without_a_key_does_not_call_the_network(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    http = FakeHTTP(FAKE_RESPONSE)
    assert st.search_terms("cell line", http=http) == []
    assert http.calls == []


def test_search_parses_hits(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", http=FakeHTTP(FAKE_RESPONSE))
    assert len(hits) == 2
    assert hits[0].iri == "http://purl.obolibrary.org/obo/NCIT_C16403"
    assert hits[0].label == "Cell Line"
    assert hits[0].source == "NCIT"
    assert "single cell" in hits[0].definition


def test_search_handles_a_missing_definition(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", http=FakeHTTP(FAKE_RESPONSE))
    assert hits[1].definition == ""


def test_search_restricts_to_the_requested_ontologies(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = FakeHTTP(FAKE_RESPONSE)
    st.search_terms("cell line", ontologies=("NCIT", "OBI"), http=http)
    url = http.calls[0][0]
    assert "ontologies=NCIT%2COBI" in url or "ontologies=NCIT,OBI" in url


def test_search_never_puts_the_key_in_the_url(monkeypatch):
    """A key in a query string leaks into logs and shell history."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "SUPERSECRET")
    http = FakeHTTP(FAKE_RESPONSE)
    st.search_terms("cell line", http=http)
    url, headers = http.calls[0]
    assert "SUPERSECRET" not in url
    assert "SUPERSECRET" in str(headers)


def test_search_respects_limit(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", limit=1, http=FakeHTTP(FAKE_RESPONSE))
    assert len(hits) == 1


def test_search_survives_a_transport_error(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")

    def boom(url, headers=None, timeout=None):
        raise OSError("network down")

    assert st.search_terms("cell line", http=boom) == []


def test_search_survives_an_unexpected_payload(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    assert st.search_terms("x", http=FakeHTTP({"unexpected": True})) == []


def test_to_binding_is_always_unconfirmed():
    hit = st.TermHit(iri="i", label="l", source="NCIT", score=1.0, definition="d")
    b = st.to_binding(hit)
    assert b == {"iri": "i", "label": "l", "source": "NCIT", "confirmed": False}


def test_default_ontologies_are_biomedical():
    assert "NCIT" in st.DEFAULT_ONTOLOGIES
    assert "OBI" in st.DEFAULT_ONTOLOGIES


def test_module_documents_the_ncbitaxon_strain_trap():
    """The prototype bound Strain to NCBITaxon_10090, which covers species,
    not laboratory strains. It was plausible enough to pass unreviewed."""
    src = (REPO / "scripts" / "schema" / "terms.py").read_text()
    assert "NCBITaxon" in src
    assert "C57BL/6J" in src
