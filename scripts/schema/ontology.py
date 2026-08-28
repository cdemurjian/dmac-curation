# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Propose controlled vocabulary for a sample type field, with sources.

This is schema mode's shortest path to value, because the delivery mechanism
already exists and nothing has ever used it:

  - `_common.write_4sheet_xlsx` accepts `ontology={field: [values]}` and writes
    a real Ontology sheet, declaring those fields `Controlled Ontology` on the
    Instructions sheet.
  - No caller has ever passed it. `curate-build.md` and `PHASES.md` never
    instruct it be populated. `consolidate_to_flat.py` never reads it.

So NExtSEEK has a controlled-vocabulary mechanism, the plugin can already write
it, and nothing populates or consumes it. `<TYPE>.ontology.json` is exactly that
parameter's shape.

Ontology validation is STRICT in the 4-sheet format and violations reject the
file. It does not exist at all in the flat format - see PHASES.md Phase 6.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"
OUTPUT_SUBDIR = "schema"

# Strongest source last: a later source overwrites an earlier one for the same
# literal value, so a value both tagged and observed is credited as observed.
# Strongest source LAST: a later source overwrites an earlier one for the same
# literal value. `observed` stays top per hard rule 4 - the workbook outranks the
# schema. `repository` sits directly beneath it because a submission is literally
# REJECTED against those lists. `tags` is the floor: it is a per-sample-type
# prose list, not a per-field vocabulary, and binding it to one field is an
# assertion nothing can check.
_SOURCE_RANK = {"tags": 0, "sibling": 1, "cedar_branch": 2, "bioportal": 3,
                "repository": 4, "observed": 5}


@dataclass
class ProposedValue:
    """One candidate permissible value, and where it came from."""

    value: str
    source: str          # tags | observed | bioportal | sibling
    note: str = ""


def bioportal_available() -> bool:
    """Whether ontology term resolution can run. Degrades, never blocks.

    Without a key, vocabulary still comes from Tags, observed values and
    sibling types - which is most of it. IRI binding is the part that waits.
    """
    return bool(os.environ.get(BIOPORTAL_ENV_VAR))


def propose_values(record: dict, field_name: str, *,
                   observed: list[str] | None = None,
                   tags: list[str] | None = None,
                   siblings: list[str] | None = None,
                   bioportal: list[str] | None = None,
                   cedar_branch: list[str] | None = None,
                   repository: list[str] | None = None) -> list[ProposedValue]:
    """Candidate permissible values for one field, deduped, source-attributed.

    Mining `Tags` is the cheapest win available WHERE IT APPLIES: D.VIA's Tags
    column already reads 'viability data, cell viability, cytotoxicity data, MTS
    assay, MTT assay, WST-1, live/dead assay, CellTiter-Glo, proliferation
    assay, cell death data' - plausibly permissible values for its `Type` field,
    written down as prose where nothing can enforce them.

    But that is a claim about ONE field of ONE type, and it is the curator's to
    make. Pass `tags=field_index.mine_tags(record)` once you have judged the
    Tags to be a vocabulary for this field. Nothing is mined automatically.
    """
    # Tags are NOT mined by default. The Tags column describes the SAMPLE TYPE,
    # not any one field, so defaulting it here put assay chemistries into every
    # field asked for - `Scientist` returned MTS assay and CellTiter-Glo, into a
    # validator that rejects the whole file on one violation.
    tags = tags or []

    contributions: list[tuple[str, str]] = []
    contributions += [(v, "tags") for v in tags]
    contributions += [(v, "sibling") for v in (siblings or [])]
    contributions += [(v, "cedar_branch") for v in (cedar_branch or [])]
    contributions += [(v, "bioportal") for v in (bioportal or [])]
    contributions += [(v, "repository") for v in (repository or [])]
    contributions += [(v, "observed") for v in (observed or [])]

    best: dict[str, str] = {}
    order: list[str] = []
    for value, source in contributions:
        value = str(value).strip()
        if not value:
            continue
        if value not in best:
            order.append(value)
            best[value] = source
        elif _SOURCE_RANK[source] > _SOURCE_RANK[best[value]]:
            best[value] = source

    notes = {
        "tags": f"listed in the sample type's Tags column",
        "observed": "seen in previous_metadata",
        "sibling": "used by a sibling type in the same clade",
        "bioportal": "suggested by BioPortal; unconfirmed",
        "cedar_branch": "from the ontology branch a CEDAR template binds this field to",
        "repository": ("enforced by the target repository; a submission is "
                       "REJECTED without an exact match"),
    }
    return [ProposedValue(value=v, source=best[v], note=notes[best[v]])
            for v in order]


def to_ontology_json(proposals: dict[str, list[ProposedValue]]) -> dict[str, list[str]]:
    """Exactly the shape `write_4sheet_xlsx(ontology=...)` expects."""
    return {field: [p.value for p in values]
            for field, values in proposals.items() if values}


def artifact_path(root: Path, sampletype: str) -> Path:
    return Path(root) / OUTPUT_SUBDIR / f"{sampletype}.ontology.json"


def write_ontology_artifact(root: Path, sampletype: str,
                            proposals: dict[str, list[ProposedValue]]) -> Path:
    """Write `<TYPE>.ontology.json` to cwd, with a `_sources` sidecar block.

    The values block is directly consumable by `write_4sheet_xlsx`. `_sources`
    exists so a reviewer can judge each value: a bare list cannot be judged, a
    list with provenance can.
    """
    doc: dict = to_ontology_json(proposals)
    doc["_sources"] = {
        field: {p.value: p.source for p in values}
        for field, values in proposals.items() if values
    }
    doc["_note"] = (
        "Values feed _common.write_4sheet_xlsx(ontology=...). Ontology "
        "validation is strict in the 4-sheet upload format and violations "
        "reject the file; the flat format has no Ontology sheet and silently "
        "discards controlled vocabulary. Review every value before use."
    )
    p = artifact_path(root, sampletype)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return p


def load_ontology_artifact(root: Path, sampletype: str) -> dict[str, list[str]]:
    """Read back only the `{field: [values]}` part, ready for the 4-sheet writer."""
    p = artifact_path(root, sampletype)
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text())
    return {k: v for k, v in doc.items() if not k.startswith("_")}
