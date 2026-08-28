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

It is a CHECKLIST, not a lookup, and choosing WHICH template is a judgement the
agent makes - see `curate-sampletype.md`. CEDAR matches token prefixes against
template NAMES, so an assay's own name is often the wrong query: `sequencing`
returns 0 while `*seq*` returns 18. A zero is therefore ambiguous - a bad query
or a real absence - and only a reader comparing several queries can say which.

No field count is quoted here, deliberately, matching SCHEMA.md. The pinned
template is an unvendored third-party draft and its counts move: an earlier
docstring here claimed 25/24/20 and another claimed 28/27/22 for the same
template, and a justification for excluding the Pistoia template on "7 fields
with no descriptions" survived long after it grew to 63 fields with 56
described. Measure it at runtime; do not cite it from memory.

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

# The GENERIC fallback, pinned by @id, used only once the agent has concluded no
# type-specific template fits. It is not "the best template" and no longer
# claims to be: the justification here used to cite the Pistoia Alliance
# template as carrying "7 fields with no descriptions", which was measured once
# and never rechecked - it now carries 63 fields with 56 described and 31 bound,
# and OUTSCORES this one. Measure at runtime; see the module docstring.
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


# Reuse-check passes strong enough to call a reference field "already covered".
# The semantic pass matches on shared word stems and is not one of them.
STRONG_PASSES = ("exact", "normalized", "synonym")


def coverage(fields, resolver):
    """Partition reference fields by how well this house already covers them.

    Exact-NAME coverage is meaningless here and reporting it was actively
    misleading: it put D.SEQ, a type carrying 84 fields, at "0 of 28". CEDAR
    writes prose names (`detection instrument`), NExtSEEK writes compact ones
    (`Sequencer`), so the two conventions essentially never collide. Coverage is
    the reuse check's verdict instead.

    `resolver` maps a field name to a `Candidate.match_pass` or None, so this
    stays free of any dependency on the catalog.

    Returns (strong, weak, uncovered); every field lands in exactly one.
    """
    strong, weak, uncovered = [], [], []
    for f in fields:
        match_pass = resolver(f.name)
        if match_pass in STRONG_PASSES:
            strong.append(f)
        elif match_pass:
            weak.append(f)
        else:
            uncovered.append(f)
    return strong, weak, uncovered


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


CEDAR_SEARCH_URL = "https://resource.metadatacenter.org/search"


@dataclass
class TemplateCandidate:
    """One CEDAR template considered for a sample type."""

    name: str
    template_id: str
    field_count: int = 0
    described: int = 0
    bound: int = 0
    score: float = 0.0


def search_templates(query: str, *, api_key: str | None = None,
                     limit: int = 20, http=None) -> list[TemplateCandidate]:
    """Templates matching a query, scored by how well specified they are.

    Quality varies enormously and an unusable template is worse than none, so
    score on what a curator can actually read: field count, how many carry a
    description, and how many bind to an ontology branch.

    The score RANKS candidates; it does not choose one. It cannot tell that
    `MiAIRR V1.1.0` (81 fields) is immune-repertoire-specific and wrong for a
    general sequencing type, nor that `Pistoia Alliance assay template` matched
    only on the stopword `assay`. Both outscore the right answer. The caller
    reads the names and decides.
    """
    key = api_key or os.environ.get(CEDAR_ENV_VAR)
    if not key:
        return []

    params = urllib.parse.urlencode({"q": query, "resource_types": "template",
                                     "limit": str(max(limit, 1))})
    headers = {"Authorization": f"apiKey {key}", "Accept": "application/json"}
    getter = http or _default_http

    try:
        payload = getter(f"{CEDAR_SEARCH_URL}?{params}", headers=headers,
                         timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - a failed search must degrade, not raise
        return []
    if not isinstance(payload, dict):
        return []

    out: list[TemplateCandidate] = []
    for entry in payload.get("resources") or []:
        if not isinstance(entry, dict) or not entry.get("@id"):
            continue
        fields = template_fields(entry["@id"], api_key=key, http=http)
        described = sum(1 for f in fields if f.description)
        bound = sum(1 for f in fields if f.branches)
        out.append(TemplateCandidate(
            name=entry.get("schema:name") or "",
            template_id=entry["@id"],
            field_count=len(fields), described=described, bound=bound,
            score=len(fields) + 2.0 * described + 3.0 * bound))
    return out


def fallback_template(*, api_key: str | None = None,
                      http=None) -> TemplateCandidate | None:
    """The pinned generic template, for when no domain template fits.

    There is deliberately NO `select_template`. Choosing a template is a
    judgement call that a fixed query cannot make: searching `sequencing`
    returns 0 while `*seq*` returns 18, and searching `*viab*` returns 0 because
    the library genuinely holds nothing for viability. Those look identical to a
    function and completely different to a reader. Worse, CEDAR matches token
    prefixes against template NAMES, so the stopword "assay" pulls
    `Pistoia Alliance assay template` into the results for any assay type and a
    score-based picker will happily call it type-specific.

    `search_templates` is the primitive; `curate-sampletype.md` drives the
    search, adapts the query, and judges. This function only supplies the
    fallback once that judgement concludes nothing fits.
    """
    key = api_key or os.environ.get(CEDAR_ENV_VAR)
    if not key:
        return None
    template_id = REFERENCE_TEMPLATES["common assay template"]
    fields = template_fields(template_id, api_key=key, http=http)
    return TemplateCandidate(
        name="common assay template", template_id=template_id,
        field_count=len(fields),
        described=sum(1 for f in fields if f.description),
        bound=sum(1 for f in fields if f.branches))
