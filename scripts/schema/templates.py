# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""CEDAR reference-template fields. A checklist, never a lookup.

BioPortal can say which *values* a field may take; it cannot say which *fields*
an assay record should carry - a class fetched from its REST API exposes only
annotation properties (definition, editor, curation status, subClassOf), never
the OWL restrictions that would describe an assay's inputs and outputs. CEDAR
templates are the opposite: a literal list of fields, each with a description
and an ontology branch to draw values from. That is why this module exists.

It is a CHECKLIST, not a lookup. CEDAR's shared library cannot be selected by
assay name - `viability`, `flow cytometry`, `sequencing` and `metabolomics` all
return zero hits - so a small set of pinned, general, well-specified templates
is diffed against the sample type instead. `common assay template` carries 25
fields, 24 of them described and 20 bound to a BioAssay Ontology branch.

Nothing here mints a field. The review renders the uncovered ones as a
checklist with their descriptions, and the existing reuse check
(`field_index.rank_candidates`) decides whether the type already covers each.
The curator judges, exactly as everywhere else in this mode.

Degrades like `terms.py`: without CEDAR_API_KEY there is no network call and an
empty list. The pinned templates are third-party and shared rather than public,
so an owner CAN revoke access; that path degrades to an empty section which
states its reason rather than going silent.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

CEDAR_ENV_VAR = "CEDAR_API_KEY"
CEDAR_TEMPLATE_URL = "https://resource.metadatacenter.org/templates/{id}"

FIELD_TYPE = "https://schema.metadatacenter.org/core/TemplateField"
ELEMENT_TYPE = "https://schema.metadatacenter.org/core/TemplateElement"

# Pinned by @id because search cannot select by assay name. `common assay
# template` is the only general template in the reachable library that is
# well-specified: the Pistoia Alliance one carries 7 fields with no
# descriptions and no ontology bindings at all.
#
# NOTE: this is bibo:draft at v0.0.1 and owned by a third party. It is read at
# runtime and never vendored, so a change upstream shows up as a changed
# checklist rather than as silently stale shipped state.
REFERENCE_TEMPLATES = {
    "common assay template":
        "https://repo.metadatacenter.org/templates/303429bb-b7a8-4cbe-b4e2-8c3be6b95f5c",
}

_TIMEOUT_SECONDS = 30


@dataclass
class TemplateField:
    """One field declared by a reference template."""

    name: str
    description: str = ""
    branches: tuple[str, ...] = ()
    required: bool = False
    path: str = ""      # dotted element path; "" for a top-level field


def _default_http(url: str, headers: dict | None = None, timeout: int | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _walk(node: dict, path: str, out: list[TemplateField]) -> None:
    """Collect fields depth-first, driven by `_ui.order`.

    `_ui.order` is the authority on what is a real field: `properties` also
    holds JSON-LD scaffolding (@context, @id, schema:name, pav:createdOn) which
    must never be reported. Multi-cardinality fields arrive wrapped as
    {"type": "array", "items": {...}}, and elements nest arbitrarily deep -
    ATACseq Metadata declares ONE top-level property holding fourteen fields.
    """
    order = (node.get("_ui") or {}).get("order") or []
    properties = node.get("properties") or {}

    for name in order:
        spec = properties.get(name)
        if not isinstance(spec, dict):
            continue
        if isinstance(spec.get("items"), dict):
            spec = spec["items"]

        if spec.get("@type") == ELEMENT_TYPE:
            _walk(spec, f"{path}.{name}" if path else name, out)
            continue

        constraints = spec.get("_valueConstraints") or {}
        branches = tuple(
            b.get("acronym", "") for b in (constraints.get("branches") or [])
            if isinstance(b, dict) and b.get("acronym")
        )
        out.append(TemplateField(
            name=name,
            description=spec.get("schema:description") or "",
            branches=branches,
            required=bool(constraints.get("requiredValue")),
            path=path,
        ))


def template_fields(template_id: str, *, api_key: str | None = None,
                    http=None) -> list[TemplateField]:
    """Every field a reference template declares, elements flattened.

    Returns [] and makes NO network call without a key, so a caller can always
    call this unconditionally.
    """
    key = api_key or os.environ.get(CEDAR_ENV_VAR)
    if not key:
        return []

    url = CEDAR_TEMPLATE_URL.format(id=urllib.parse.quote(template_id, safe=""))
    headers = {"Authorization": f"apiKey {key}", "Accept": "application/json"}
    getter = http or _default_http

    try:
        payload = getter(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - an unshared template must degrade, not raise
        return []

    if not isinstance(payload, dict):
        return []

    found: list[TemplateField] = []
    _walk(payload, "", found)
    return found
