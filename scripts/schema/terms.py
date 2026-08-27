# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""BioPortal ontology term lookup. Suggests, never binds.

CEDAR's contribution to this plugin reduces to exactly this: ontology term
resolution, usable standalone with no CEDAR account, no hosted service and no
template machinery.

Every binding this module produces is emitted with ``"confirmed": false`` and
its source. Only a human flips that flag, and this is not caution for its own
sake. In the MUS prototype `Strain` was bound to `NCBITaxon_10090` - which is
WRONG. NCBITaxon covers species, not laboratory strains such as C57BL/6J or
BALB/c. It was plausible enough to pass unreviewed. Ontology binding is
per-field human judgment and the tooling must not pretend otherwise.

Degrades rather than blocking: with no BIOPORTAL_API_KEY, `search_terms`
returns an empty list without touching the network. Vocabulary still comes from
the Tags column, observed values in previous_metadata, and sibling types, which
is most of it. IRI binding is the part that waits for a key.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"
BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_CLASS_URL = "https://data.bioontology.org/ontologies/{acronym}/classes/{iri}"

# Biomedical ontologies worth searching by default for NExtSEEK sample metadata.
DEFAULT_ONTOLOGIES = ("NCIT", "OBI", "EFO", "UBERON", "CL")

_TIMEOUT_SECONDS = 20


@dataclass
class TermHit:
    """One BioPortal search result."""

    iri: str
    label: str
    source: str          # ontology acronym, e.g. NCIT
    score: float = 0.0
    definition: str = ""


@dataclass
class CladeNeighbor:
    """One class adjacent to a matched term in an external ontology."""

    label: str
    iri: str
    definition: str = ""
    relation: str = ""   # parent | child


@dataclass
class ClassMatch:
    """A resolved ontology class, and how much to trust the resolution."""

    hit: TermHit
    confidence: str      # exact | normalized | weak


def _default_http(url: str, headers: dict | None = None, timeout: int | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _collection(payload) -> list:
    """Normalise BioPortal's two list shapes.

    `/children` paginates its results under a "collection" key; `/parents`
    returns a bare JSON array. Anything else is treated as empty rather than
    raising, so one odd response cannot break a run.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        entries = payload.get("collection")
        return entries if isinstance(entries, list) else []
    return []


def _acronym(entry: dict) -> str:
    link = ((entry.get("links") or {}).get("ontology") or "")
    return link.rstrip("/").rsplit("/", 1)[-1] if link else ""


def search_terms(query: str, *, ontologies=None, api_key: str | None = None,
                 limit: int = 5, http=None) -> list[TermHit]:
    """Search BioPortal for terms matching `query`.

    Returns [] and makes NO network call when no API key is available, so a
    caller can always call this unconditionally.

    The key travels in the Authorization header, never in the query string,
    because a query string ends up in logs and shell history.
    """
    key = api_key or os.environ.get(BIOPORTAL_ENV_VAR)
    if not key:
        return []

    params = {
        "q": query,
        "ontologies": ",".join(ontologies or DEFAULT_ONTOLOGIES),
        "require_definitions": "false",
        "pagesize": str(max(limit, 1)),
    }
    url = f"{BIOPORTAL_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"apikey token={key}", "Accept": "application/json"}

    getter = http or _default_http
    try:
        payload = getter(url, headers=headers, timeout=_TIMEOUT_SECONDS)

        collection = (payload or {}).get("collection")
        if not isinstance(collection, list):
            return []

        hits: list[TermHit] = []
        for entry in collection[:limit]:
            if not isinstance(entry, dict) or not entry.get("@id"):
                continue
            definitions = entry.get("definition") or []
            hits.append(TermHit(
                iri=entry["@id"],
                label=entry.get("prefLabel") or "",
                source=_acronym(entry),
                score=float(entry.get("score") or 0.0),
                definition=definitions[0] if definitions else "",
            ))
        return hits
    except Exception:  # noqa: BLE001 - a lookup or parse failure must never break a run
        return []


def _normalise_label(text: str) -> str:
    """Fold case, spacing and punctuation for label comparison."""
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def resolve_class(query: str, *, ontologies=None, api_key: str | None = None,
                  limit: int = 10, http=None) -> ClassMatch | None:
    """The class a query names, with the confidence to treat it at.

    `search_terms` returns BioPortal's LEXICAL ranking, and taking hit[0] as
    "the match" is how `Short Read Sequencing` resolved to `linked-read
    sequencing assay` - a 10x-specific technique - while `sequencing assay` sat
    at rank five. Nothing here guesses better than BioPortal does. What it does
    is refuse to present a guess as a match: an exact or normalised label match
    is worth building on, and anything else comes back flagged `weak` so the
    review can say so instead of asserting `Matched X`.

    Returns None when nothing came back at all, including with no API key.
    """
    hits = search_terms(query, ontologies=ontologies, api_key=api_key,
                        limit=limit, http=http)
    if not hits:
        return None

    target = query.casefold().strip()
    for hit in hits:
        if hit.label.casefold().strip() == target:
            return ClassMatch(hit=hit, confidence="exact")

    normalised = _normalise_label(query)
    for hit in hits:
        if _normalise_label(hit.label) == normalised:
            return ClassMatch(hit=hit, confidence="normalized")

    return ClassMatch(hit=hits[0], confidence="weak")


def clade_neighbors(hit: TermHit, *, api_key: str | None = None,
                    limit: int = 10, http=None) -> list[CladeNeighbor]:
    """Parents and children of a matched class, as evidence for missing fields.

    `field_index.siblings_in_clade` mines the same shape from the INTERNAL
    catalog, where the prior is one house's precedent. This mines it from a
    curated external ontology, where the axis that separates sibling classes is
    itself the evidence: OBI splits `cell viability assay` into Annexin V
    staining, ATP bioluminescence and resorufin detection, so detection
    chemistry is a real field D.VIA does not have.

    Definitions are carried because they hold that axis - the label alone is
    often too terse to judge from.

    Returns evidence a curator reads, never a field. Nothing here mints a name;
    inferring the axis from these labels is human (or LLM) work, not extraction.

    Degrades exactly like `search_terms`: no key means no network call and an
    empty list, and one dead endpoint never discards what the other returned.
    """
    key = api_key or os.environ.get(BIOPORTAL_ENV_VAR)
    if not key:
        return []

    base = BIOPORTAL_CLASS_URL.format(
        acronym=hit.source, iri=urllib.parse.quote(hit.iri, safe=""))
    headers = {"Authorization": f"apikey token={key}", "Accept": "application/json"}
    getter = http or _default_http

    found: list[CladeNeighbor] = []
    for relation, path in (("parent", "parents"), ("child", "children")):
        try:
            payload = getter(f"{base}/{path}", headers=headers, timeout=_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - one dead endpoint must not lose the other
            continue

        for entry in _collection(payload):
            if not isinstance(entry, dict) or not entry.get("@id"):
                continue
            definitions = entry.get("definition") or []
            found.append(CladeNeighbor(
                label=entry.get("prefLabel") or "",
                iri=entry["@id"],
                definition=definitions[0] if definitions else "",
                relation=relation,
            ))
    return found[:limit]


def to_binding(hit: TermHit) -> dict:
    """The dictionary-entry `ontology` block. Always unconfirmed."""
    return {"iri": hit.iri, "label": hit.label, "source": hit.source,
            "confirmed": False}
