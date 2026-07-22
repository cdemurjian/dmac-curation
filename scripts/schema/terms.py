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


def _default_http(url: str, headers: dict | None = None, timeout: int | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    except Exception:  # noqa: BLE001 - a lookup failure must never break a run
        return []

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


def to_binding(hit: TermHit) -> dict:
    """The dictionary-entry `ontology` block. Always unconfirmed."""
    return {"iri": hit.iri, "label": hit.label, "source": hit.source,
            "confirmed": False}
