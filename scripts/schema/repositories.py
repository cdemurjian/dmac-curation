# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Repository requirements, read from templates the plugin already vendors.

`context/report_templates/` ships the GEO, SRA and PRIDE templates that `report`
mode writes against. `schema` mode has never opened them, and they are the
strongest evidence available: they say which fields a submission is REJECTED
without, and they carry the exact vocabularies those repositories enforce.

Nothing here calls a network. The files are vendored and versioned with the
plugin, so this source works with no key and no connectivity.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_FILES = {
    "GEO": "GEO-updated.json",
    "SRA": "SRA.json",
    "PRIDE": "pride.json",
}

_CONTEXT_SUBDIR = Path("context") / "report_templates"

# Blocks that describe the template rather than declare fields. Walking them
# would mine prose and guidance keys as if they were submission requirements.
_NON_FIELD_SECTIONS = {
    "schema", "report_writer_guidance", "controlled_vocabulary", "notes",
    "format", "description", "report_type",
}


@dataclass
class RepositoryField:
    """One field a repository asks for."""

    name: str
    section: str
    repository: str
    required: bool = False
    conditional: bool = False


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def load_template(repository: str, root: Path | None = None) -> dict:
    """Read one vendored repository template. Returns {} if absent."""
    filename = REPOSITORY_FILES.get(repository)
    if not filename:
        return {}
    path = (root or _plugin_root()) / _CONTEXT_SUBDIR / filename
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - a missing template must not break a run
        return {}


def _mark(key: str) -> tuple[str, bool, bool]:
    """Split a template key into (name, required, conditional).

    `**` must be tested BEFORE `*`, or every conditionally-required field is
    misread as unconditionally required and the review overstates what a
    submission actually demands.
    """
    if key.startswith("**"):
        return key[2:].strip(), False, True
    if key.startswith("*"):
        return key[1:].strip(), True, False
    return key.strip(), False, False


def _collect(node, section: str, repository: str, out: list[RepositoryField]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                name, required, conditional = _mark(key)
                if required or conditional:
                    out.append(RepositoryField(name=name, section=section,
                                               repository=repository,
                                               required=required,
                                               conditional=conditional))
            _collect(value, section, repository, out)
    elif isinstance(node, list):
        for item in node:
            _collect(item, section, repository, out)


def required_fields(doc: dict, repository: str) -> list[RepositoryField]:
    """Every `*` or `**` marked field, deduplicated, in document order."""
    if not isinstance(doc, dict):
        return []
    found: list[RepositoryField] = []
    for section, node in doc.items():
        if section in _NON_FIELD_SECTIONS:
            continue
        _collect(node, section, repository, found)

    seen: set[str] = set()
    unique: list[RepositoryField] = []
    for f in found:
        if f.name in seen:
            continue
        seen.add(f.name)
        unique.append(f)
    return unique


# Keywords matched against a record's producing assay and Tags. Deliberately
# narrow: a type mapping to no public repository (D.VIA, D.FLOW, D.PRM) must
# come back EMPTY so the review can say the source is thin BY FACT, not by
# failure. Padding this list would put unevidenced fields in front of a curator,
# which is the thing this mode exists to prevent.
REPOSITORY_KEYWORDS = {
    "GEO": ("sequencing", "rna-seq", "rnaseq", "microarray", "chip-seq",
            "atac", "expression profiling"),
    "SRA": ("sequencing", "rna-seq", "rnaseq", "wgs", "wxs", "amplicon",
            "metagenom"),
    "PRIDE": ("proteomic", "mass spectrometry", "mass-spec", "peptide",
              "protein identification"),
}


def controlled_vocabularies(doc: dict) -> dict[str, list[str]]:
    """The value lists a repository enforces, keyed by its own field names.

    Only list-valued entries are vocabularies. The block also carries prose
    (`authority`) and a nested by-platform mapping, neither of which is a flat
    permissible-value list. PRIDE nests the whole block under `schema`.
    """
    if not isinstance(doc, dict):
        return {}
    block = doc.get("controlled_vocabulary")
    if not isinstance(block, dict):
        block = (doc.get("schema") or {}).get("controlled_vocabularies")
    if not isinstance(block, dict):
        return {}
    return {k: v for k, v in block.items() if isinstance(v, list) and v}


def repositories_for(record: dict) -> tuple[str, ...]:
    """Which public repositories cover this sample type's data, if any."""
    haystack = " ".join([
        str((record or {}).get("Associated Assay Parents") or ""),
        str((record or {}).get("Tags") or ""),
    ]).casefold()
    if not haystack.strip():
        return ()
    return tuple(name for name, keywords in REPOSITORY_KEYWORDS.items()
                 if any(k in haystack for k in keywords))
