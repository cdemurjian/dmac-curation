"""CEDAR reference-template fields. A checklist, never a lookup.

Search cannot select a template by assay name - `viability`, `flow cytometry`,
`sequencing` and `metabolomics` all return zero hits against the shared
library. So a small set of pinned reference templates is diffed against the
sample type as a completeness checklist.

Every fixture here mirrors a shape verified against resource.metadatacenter.org.
A fake that smooths over the real structure hides the only bugs this code can
have - CEDAR nests fields inside TemplateElements, and a flat reader reports
ATACseq Metadata as ONE field when it carries fourteen.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import templates as tp  # noqa: E402

FIELD = "https://schema.metadatacenter.org/core/TemplateField"
ELEMENT = "https://schema.metadatacenter.org/core/TemplateElement"


def _field(desc="", branches=(), required=False):
    return {
        "@type": FIELD,
        "schema:description": desc,
        "_valueConstraints": {
            "requiredValue": required,
            "branches": [{"acronym": a, "name": "x", "uri": "http://x"} for a in branches],
        },
    }


# Scaffolding really does sit in `properties`; `_ui.order` is what excludes it.
SCAFFOLDING = {"@context": {}, "@id": {}, "schema:name": {}, "pav:createdOn": {}}

FLAT_TEMPLATE = {
    "_ui": {"order": ["assay title", "bioassay type", "detection instrument"]},
    "properties": {
        "assay title": _field("A short summary description of the assay."),
        "bioassay type": _field("Categorization of bioassays.", ("BAO",)),
        "detection instrument": _field("Equipment used for readout.", ("BAO",), True),
        **SCAFFOLDING,
    },
}

NESTED_TEMPLATE = {
    "_ui": {"order": ["aTACseqAssayMetadata"]},
    "properties": {
        "aTACseqAssayMetadata": {
            "@type": ELEMENT,
            "_ui": {"order": ["aTACseq_Instrument", "aTACseq_Read_Length"]},
            "properties": {
                "aTACseq_Instrument": _field("Instrument used."),
                "aTACseq_Read_Length": _field("Read length."),
            },
        },
        **SCAFFOLDING,
    },
}

# Multi-cardinality fields arrive wrapped in an array under `items`.
ARRAY_TEMPLATE = {
    "_ui": {"order": ["related assays"]},
    "properties": {
        "related assays": {"type": "array",
                           "items": _field("Assays belonging to the same project.")},
    },
}

TEMPLATE_ID = "https://repo.metadatacenter.org/templates/303429bb-b7a8-4cbe-b4e2-8c3be6b95f5c"


class FakeHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_returns_empty_without_a_key(monkeypatch):
    monkeypatch.delenv(tp.CEDAR_ENV_VAR, raising=False)
    assert tp.template_fields(TEMPLATE_ID) == []


def test_without_a_key_does_not_call_the_network(monkeypatch):
    monkeypatch.delenv(tp.CEDAR_ENV_VAR, raising=False)
    http = FakeHTTP(FLAT_TEMPLATE)
    assert tp.template_fields(TEMPLATE_ID, http=http) == []
    assert http.calls == []


def test_extracts_flat_fields_in_declared_order(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(FLAT_TEMPLATE))
    assert [f.name for f in out] == ["assay title", "bioassay type", "detection instrument"]
    assert out[0].description == "A short summary description of the assay."


def test_skips_jsonld_scaffolding(monkeypatch):
    """`properties` holds @context and schema:name; `_ui.order` is the authority."""
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(FLAT_TEMPLATE))
    assert not any(f.name.startswith("@") or ":" in f.name for f in out)


def test_carries_ontology_branch_acronyms(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(FLAT_TEMPLATE))
    by = {f.name: f for f in out}
    assert by["bioassay type"].branches == ("BAO",)
    assert by["assay title"].branches == ()


def test_marks_required_fields(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(FLAT_TEMPLATE))
    by = {f.name: f for f in out}
    assert by["detection instrument"].required is True
    assert by["assay title"].required is False


def test_recurses_into_template_elements(monkeypatch):
    """A flat reader reports ATACseq Metadata as one field. It carries fourteen."""
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(NESTED_TEMPLATE))
    assert [f.name for f in out] == ["aTACseq_Instrument", "aTACseq_Read_Length"]


def test_a_nested_field_records_the_element_it_came_from(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(NESTED_TEMPLATE))
    assert all(f.path == "aTACseqAssayMetadata" for f in out)


def test_a_flat_field_has_no_element_path(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(FLAT_TEMPLATE))
    assert all(f.path == "" for f in out)


def test_unwraps_multi_cardinality_array_fields(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(ARRAY_TEMPLATE))
    assert [f.name for f in out] == ["related assays"]
    assert out[0].description == "Assays belonging to the same project."


def test_percent_encodes_the_template_id_into_the_path(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    http = FakeHTTP(FLAT_TEMPLATE)
    tp.template_fields(TEMPLATE_ID, http=http)
    url, headers = http.calls[0]
    assert "https%3A%2F%2Frepo.metadatacenter.org" in url
    assert headers["Authorization"] == "apiKey testkey"


def test_returns_empty_on_a_malformed_payload(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    assert tp.template_fields(TEMPLATE_ID, http=FakeHTTP("not a template")) == []


def test_survives_a_failed_fetch(monkeypatch):
    """An owner can unshare a template. That must degrade, never raise."""
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    assert tp.template_fields(TEMPLATE_ID, http=FakeHTTP(RuntimeError("403"))) == []


def test_a_reference_template_is_pinned():
    assert tp.REFERENCE_TEMPLATES
    assert all(v.startswith("https://repo.metadatacenter.org/templates/")
               for v in tp.REFERENCE_TEMPLATES.values())


DEEP_TEMPLATE = {
    "_ui": {"order": ["outer"]},
    "properties": {
        "outer": {
            "@type": ELEMENT,
            "_ui": {"order": ["inner"]},
            "properties": {
                "inner": {
                    "@type": ELEMENT,
                    "_ui": {"order": ["depth_2_field"]},
                    "properties": {"depth_2_field": _field("Nested two deep.")},
                }
            },
        }
    },
}


def test_a_twice_nested_field_records_its_full_element_path(monkeypatch):
    monkeypatch.setenv(tp.CEDAR_ENV_VAR, "testkey")
    out = tp.template_fields(TEMPLATE_ID, http=FakeHTTP(DEEP_TEMPLATE))
    assert [f.name for f in out] == ["depth_2_field"]
    assert out[0].path == "outer.inner"


# --- coverage ---------------------------------------------------------------
#
# `covered: 0 of 28` was reported for D.SEQ, which carries 84 fields. Exact-name
# coverage between CEDAR prose names (`detection instrument`) and NExtSEEK
# compact ones (`Sequencer`) can essentially never match, so the count was a
# naming-convention artifact that read as a finding. Coverage is decided by the
# reuse check's STRONG passes instead.

FIELDS = [
    tp.TemplateField(name="detection instrument"),
    tp.TemplateField(name="assay design method"),
    tp.TemplateField(name="bioassay type"),
    tp.TemplateField(name="threshold"),
]


def _resolver(mapping):
    return lambda name: mapping.get(name)


def test_coverage_counts_only_strong_reuse_matches():
    strong, weak, uncovered = tp.coverage(FIELDS, _resolver({
        "detection instrument": "normalized",
        "assay design method": "exact",
        "bioassay type": "semantic",
    }))
    assert [f.name for f in strong] == ["detection instrument", "assay design method"]


def test_coverage_separates_weak_matches_from_real_ones():
    strong, weak, uncovered = tp.coverage(FIELDS, _resolver({"bioassay type": "semantic"}))
    assert [f.name for f in weak] == ["bioassay type"]


def test_coverage_reports_fields_with_no_candidate_at_all():
    strong, weak, uncovered = tp.coverage(FIELDS, _resolver({}))
    assert len(uncovered) == 4


def test_coverage_counts_a_synonym_as_strong():
    strong, _, _ = tp.coverage(FIELDS, _resolver({"threshold": "synonym"}))
    assert [f.name for f in strong] == ["threshold"]


def test_coverage_partitions_every_field_exactly_once():
    strong, weak, uncovered = tp.coverage(FIELDS, _resolver({
        "detection instrument": "exact", "bioassay type": "semantic"}))
    assert len(strong) + len(weak) + len(uncovered) == len(FIELDS)
