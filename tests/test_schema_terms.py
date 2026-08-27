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


def _one_item_payload(item):
    """A well-formed-JSON payload whose sole collection entry is `item`."""
    return {"collection": [item]}


def test_search_survives_links_as_a_string(monkeypatch):
    """`links` a str would AttributeError in _acronym (.get on a str)."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    payload = _one_item_payload({
        "@id": "http://purl.obolibrary.org/obo/NCIT_C16403",
        "prefLabel": "Cell Line",
        "links": "not-a-dict",
        "definition": ["A cell culture derived from a single cell."],
    })
    assert st.search_terms("cell line", http=FakeHTTP(payload)) == []


def test_search_survives_a_non_numeric_score(monkeypatch):
    """`score` a non-numeric str would ValueError in float(...)."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    payload = _one_item_payload({
        "@id": "http://purl.obolibrary.org/obo/NCIT_C16403",
        "prefLabel": "Cell Line",
        "links": {"ontology": "http://data.bioontology.org/ontologies/NCIT"},
        "score": "high",
        "definition": ["A cell culture derived from a single cell."],
    })
    assert st.search_terms("cell line", http=FakeHTTP(payload)) == []


def test_search_survives_definition_as_an_int(monkeypatch):
    """`definition` an int would TypeError: 'int' object is not subscriptable."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    payload = _one_item_payload({
        "@id": "http://purl.obolibrary.org/obo/NCIT_C16403",
        "prefLabel": "Cell Line",
        "links": {"ontology": "http://data.bioontology.org/ontologies/NCIT"},
        "definition": 7,
    })
    assert st.search_terms("cell line", http=FakeHTTP(payload)) == []


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


# --- clade neighbours -------------------------------------------------------
#
# The reuse check already mines siblings from the INTERNAL catalog. This walks
# the same shape over a curated external ontology, where the distinguishing
# axis between sibling classes is itself evidence for a missing field: OBI
# splits `cell viability assay` by detection chemistry, which is exactly the
# field D.VIA lacks.

CLASS_HIT = st.TermHit(
    iri="http://purl.obolibrary.org/obo/OBI_0003583",
    label="cell viability assay",
    source="OBI",
    definition="A cytometry assay which measures the number of living cells.",
)

CHILDREN_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/OBI_0003584",
         "prefLabel": "cell viability assay using Annexin V staining",
         "definition": ["A cell viability assay that uses Annexin V staining."]},
        {"@id": "http://purl.obolibrary.org/obo/OBI_0003757",
         "prefLabel": "cell viability assay based on detection of resorufin",
         "definition": []},
    ]
}

# /children is paginated under "collection"; /parents is a BARE LIST.
# Verified against data.bioontology.org - a fake that smooths this over hides
# the only shape bug this function can have.
PARENTS_RESPONSE = [
    {"@id": "http://purl.obolibrary.org/obo/OBI_0001977",
     "prefLabel": "cytometry assay",
     "definition": ["An assay that measures characteristics of cells."]},
]


class RoutedHTTP:
    """Fake getter answering by URL fragment. A clade walk makes several calls."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append(url)
        for fragment, payload in self.routes:
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unrouted URL: {url}")


def _routed():
    return RoutedHTTP([("/children", CHILDREN_RESPONSE),
                       ("/parents", PARENTS_RESPONSE)])


def test_clade_neighbors_returns_empty_without_a_key(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    assert st.clade_neighbors(CLASS_HIT) == []


def test_clade_neighbors_without_a_key_does_not_call_the_network(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    http = _routed()
    assert st.clade_neighbors(CLASS_HIT, http=http) == []
    assert http.calls == []


def test_clade_neighbors_returns_children_with_their_definitions(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    out = st.clade_neighbors(CLASS_HIT, http=_routed())
    children = [n for n in out if n.relation == "child"]
    assert [c.label for c in children] == [
        "cell viability assay using Annexin V staining",
        "cell viability assay based on detection of resorufin",
    ]
    assert "Annexin V staining" in children[0].definition
    assert children[1].definition == ""


def test_clade_neighbors_labels_the_parent_relation(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    out = st.clade_neighbors(CLASS_HIT, http=_routed())
    parents = [n for n in out if n.relation == "parent"]
    assert [p.label for p in parents] == ["cytometry assay"]
    assert parents[0].iri == "http://purl.obolibrary.org/obo/OBI_0001977"


def test_clade_neighbors_requests_the_matched_class_of_its_ontology(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = _routed()
    st.clade_neighbors(CLASS_HIT, http=http)
    assert all("/ontologies/OBI/classes/" in url for url in http.calls)
    # The class IRI must be percent-encoded into the path, not appended raw.
    assert all("http%3A%2F%2Fpurl.obolibrary.org" in url for url in http.calls)


def test_clade_neighbors_caps_the_result_at_limit(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    out = st.clade_neighbors(CLASS_HIT, limit=2, http=_routed())
    assert len(out) == 2


def test_clade_neighbors_survives_a_failing_call(monkeypatch):
    """One dead endpoint must not lose the neighbours the other one returned."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = RoutedHTTP([("/children", CHILDREN_RESPONSE),
                       ("/parents", RuntimeError("boom"))])
    out = st.clade_neighbors(CLASS_HIT, http=http)
    assert [n.relation for n in out] == ["child", "child"]


def test_clade_neighbors_ignores_entries_with_no_id(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = RoutedHTTP([("/children", {"collection": [{"prefLabel": "junk"}]}),
                       ("/parents", {"collection": []})])
    assert st.clade_neighbors(CLASS_HIT, http=http) == []


def test_clade_neighbors_reads_both_bioportal_collection_shapes(monkeypatch):
    """/children paginates under "collection"; /parents returns a bare list."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    out = st.clade_neighbors(CLASS_HIT, http=_routed())
    assert [n.relation for n in out] == ["parent", "child", "child"]


def test_clade_neighbors_ignores_a_payload_that_is_neither_shape(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = RoutedHTTP([("/children", "not json"), ("/parents", 42)])
    assert st.clade_neighbors(CLASS_HIT, http=http) == []
