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


# --- class resolution -------------------------------------------------------
#
# search_terms returns BioPortal's LEXICAL ranking. Taking hit[0] as "the match"
# is how `Short Read Sequencing` resolved to `linked-read sequencing assay` - a
# 10x-specific technique - while `sequencing assay` sat at rank 5. The fix is
# not to guess better; it is to stop presenting a guess as a match.

RANKED_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/OBI_0003412",
         "prefLabel": "linked-read sequencing assay",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
        {"@id": "http://purl.obolibrary.org/obo/OBI_0600047",
         "prefLabel": "sequencing assay",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
    ]
}

EXACT_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/OBI_0003412",
         "prefLabel": "linked-read sequencing assay",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
        {"@id": "http://purl.obolibrary.org/obo/OBI_0003583",
         "prefLabel": "cell viability assay",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
    ]
}


def test_resolve_returns_none_without_a_key(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    assert st.resolve_class("cell viability assay") is None


def test_resolve_prefers_an_exact_label_over_bioportals_top_hit(monkeypatch):
    """BioPortal ranks linked-read first; the exact label is what we want."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    m = st.resolve_class("Cell Viability Assay", http=FakeHTTP(EXACT_RESPONSE))
    assert m.hit.label == "cell viability assay"
    assert m.confidence == "exact"


def test_resolve_flags_a_lexical_top_hit_as_weak(monkeypatch):
    """No OBI class is named `Short Read Sequencing`. Say so, do not pretend."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    m = st.resolve_class("Short Read Sequencing", http=FakeHTTP(RANKED_RESPONSE))
    assert m.hit.label == "linked-read sequencing assay"
    assert m.confidence == "weak"


def test_resolve_matches_ignoring_case_and_separators(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    m = st.resolve_class("cell-viability assay", http=FakeHTTP(EXACT_RESPONSE))
    assert m.confidence == "normalized"
    assert m.hit.label == "cell viability assay"


def test_resolve_returns_none_when_nothing_comes_back(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    assert st.resolve_class("nonsense", http=FakeHTTP({"collection": []})) is None


# --- field vocabulary -------------------------------------------------------
#
# The missing middle: propose_values accepts bioportal=[...] and nothing ever
# produced that list, so every ontology.json this plugin has written came
# entirely from the Tags column.
#
# The value list for a field is the CHILDREN of the concept the field names.
# A bare field name is not that concept - `Type` resolves EXACT to a generic
# ontology class named "Type" - so the concept is composed by the caller, and
# for a CEDAR field its declared branch (BAO, DOID) narrows the search.

VOCAB_SEARCH = {
    "collection": [
        {"@id": "http://www.bioassayontology.org/bao#BAO_0000248",
         "prefLabel": "assay footprint",
         "links": {"ontology": "http://data.bioontology.org/ontologies/BAO"},
         "definition": []},
    ]
}

VOCAB_CHILDREN = {
    "collection": [
        {"@id": "http://x#1", "prefLabel": "microplate", "definition": ["A plate."]},
        {"@id": "http://x#2", "prefLabel": "cuvette", "definition": []},
    ]
}

VOCAB_PARENTS = [
    {"@id": "http://x#0", "prefLabel": "assay format", "definition": []},
]


def _vocab_http():
    return RoutedHTTP([("/children", VOCAB_CHILDREN),
                       ("/parents", VOCAB_PARENTS),
                       ("search", VOCAB_SEARCH)])


def test_field_vocabulary_is_empty_without_a_key(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    v = st.field_vocabulary("assay footprint")
    assert v.values == []
    assert v.note


def test_field_vocabulary_returns_the_child_labels(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    v = st.field_vocabulary("assay footprint", http=_vocab_http())
    assert v.values == ["microplate", "cuvette"]


def test_field_vocabulary_excludes_the_parent(monkeypatch):
    """A parent is broader than the field. It is not a permissible value."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    v = st.field_vocabulary("assay footprint", http=_vocab_http())
    assert "assay format" not in v.values


def test_field_vocabulary_records_the_resolution_confidence(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    v = st.field_vocabulary("assay footprint", http=_vocab_http())
    assert v.confidence == "exact"
    assert v.concept == "assay footprint"


def test_field_vocabulary_takes_a_composed_concept_distinct_from_the_field(monkeypatch):
    """`Type` alone resolves to a generic class; the concept carries the context."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    v = st.field_vocabulary("Type", concept="assay footprint", http=_vocab_http())
    assert v.field == "Type"
    assert v.concept == "assay footprint"
    assert v.values == ["microplate", "cuvette"]


def test_field_vocabulary_searches_the_ontologies_it_is_given(monkeypatch):
    """A CEDAR field declares its branch; that is a better search than a guess."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = _vocab_http()
    st.field_vocabulary("assay footprint", ontologies=("BAO",), http=http)
    search_urls = [u for u in http.calls if "search" in u]
    assert search_urls and "ontologies=BAO" in search_urls[0]


def test_field_vocabulary_notes_why_it_found_nothing(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = RoutedHTTP([("search", {"collection": []})])
    v = st.field_vocabulary("nonsense", http=http)
    assert v.values == []
    assert "no class" in v.note.lower()


def test_field_vocabulary_notes_a_class_that_has_no_children(monkeypatch):
    """A leaf class yields no vocabulary. Say so rather than returning silence."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = RoutedHTTP([("/children", {"collection": []}),
                       ("/parents", []), ("search", VOCAB_SEARCH)])
    v = st.field_vocabulary("assay footprint", http=http)
    assert v.values == []
    assert "no narrower" in v.note.lower()


# --- obsolete classes -------------------------------------------------------
#
# `biological process` searched in GO returns `obsolete biological process` as
# its top hit, and BioPortal reports obsolete=False for it - OBO marks
# deprecation by prefixing the LABEL, and the structured flag does not follow.
# Trusting either alone proposes a retired class as live vocabulary.

OBSOLETE_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/GO_0008150x",
         "prefLabel": "obsolete biological process",
         "obsolete": False,          # BioPortal really does say False here
         "links": {"ontology": "http://data.bioontology.org/ontologies/GO"},
         "definition": []},
        {"@id": "http://purl.obolibrary.org/obo/GO_0065007",
         "prefLabel": "biological regulation",
         "obsolete": False,
         "links": {"ontology": "http://data.bioontology.org/ontologies/GO"},
         "definition": []},
        {"@id": "http://purl.obolibrary.org/obo/GO_flagged",
         "prefLabel": "a properly flagged retired term",
         "obsolete": True,
         "links": {"ontology": "http://data.bioontology.org/ontologies/GO"},
         "definition": []},
    ]
}


def test_search_drops_a_label_prefixed_obsolete(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("biological process", http=FakeHTTP(OBSOLETE_RESPONSE))
    assert "obsolete biological process" not in [h.label for h in hits]


def test_search_drops_a_flagged_obsolete_class(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("biological process", http=FakeHTTP(OBSOLETE_RESPONSE))
    assert "a properly flagged retired term" not in [h.label for h in hits]


def test_search_keeps_the_live_class_behind_an_obsolete_one(monkeypatch):
    """Dropping the retired top hit must promote the real one, not lose it."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("biological process", http=FakeHTTP(OBSOLETE_RESPONSE))
    assert [h.label for h in hits] == ["biological regulation"]


def test_obsolete_filtering_survives_into_resolution(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    m = st.resolve_class("biological process", http=FakeHTTP(OBSOLETE_RESPONSE))
    assert m.hit.label == "biological regulation"
