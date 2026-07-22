# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The declarative mapping spec, and the validator that gates it.

The LLM does NOT write cell values. It writes a mapping, once, which is then
applied deterministically to every row. Both LLM steps are O(columns), not
O(rows).

Why this shape: chat_nextseek's report_writer_agent has the LLM emit every cell,
which cost "a 5.1M-token prompt on a 195-UID flow" (reports/outputs.py:349-355)
and was hard-bypassed for nf-core. Its report_coder_agent improves on that by
having the LLM write extraction Python, executed in an AST sandbox with a
row-parity guard. A declarative mapping achieves the same LLM-decides /
code-executes split while being validatable, human-reviewable, cacheable, and
needing no sandbox.

Validating the mapping BEFORE applying it is the cheapest place to fail.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DIRECTIVES = ("source", "via_lineage", "const", "map", "synthesize", "unmapped")

# Exactly one of these must appear per field. `via_lineage` and `map` are
# modifiers on `source`, not directives in their own right.
_PRIMARY_DIRECTIVES = ("source", "const", "synthesize", "unmapped")

ROW_SECTION = {"GEO": "samples", "SRA": "libraries", "PRIDE": "sample_metadata"}
TARGET_SAMPLETYPE = {"GEO": "D.SEQ", "SRA": "D.SEQ", "PRIDE": "D.MSP"}

# GEO's `*single or paired-end` dropdown requires the word `paired-end`, but the
# vendored controlled_vocabulary.library_layout was mined from SRA/ENA and holds
# ['single', 'paired'] - there is no `paired-end`. The read-only template is not
# edited; the GEO-specific layout CV lives here in code instead.
_GEO_LAYOUT_CV = ["single", "paired-end"]   # GEO dropdown values, not SRA's

# GEO/SRA target field -> controlled_vocabulary key. The CV is mined from
# SRA_metadata.xlsx and keyed by SRA's names, not GEO's column headers.
_CV_KEY_FOR_FIELD = {
    "*library strategy": "library_strategy",
    "library_strategy": "library_strategy",
    "library_source": "library_source",
    "library_selection": "library_selection",
    "library_layout": "library_layout",
    "platform": "platform",
    # GEO's `*instrument model` dropdown uses `Illumina NextSeq 500`-style
    # names, but the vendored `instrument_model_flat` was mined from SRA and
    # holds the unprefixed `NextSeq 500` (an upstream naming inconsistency), so
    # exact-match CV enforcement would wrongly reject valid GEO values. GEO
    # instrument model is therefore left as free text (cv_for_field -> None),
    # which is the repo owner's stated intent. SRA's `instrument_model` keeps
    # the flat CV: for SRA the mined names match, and no test relies on it.
    "instrument_model": "instrument_model_flat",
    "filetype": "filetype",
}


@dataclass
class TemplateSpec:
    report_type: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    required: dict[str, list[str]] = field(default_factory=dict)
    cv: dict[str, list[str]] = field(default_factory=dict)
    row_section: str = "samples"
    raw: dict = field(default_factory=dict)


@dataclass
class MappingError:
    section: str
    field: str
    code: str
    message: str


def load_template_spec(path: Path) -> TemplateSpec:
    """Read a vendored `<FORMAT>*.json` into a validatable shape.

    Section NAMES come from the template's own `schema.sections` declaration.
    Each section's FIELD KEYS come from the top-level `doc[name]` object (a list
    section like GEO `paired_end_experiments` is a list-of-rows, so its keys are
    the first row's keys). Reading field keys from `schema.sections[name]` would
    KeyError on PRIDE's `sample_metadata`, which has no `"fields"` subkey.
    """
    doc = json.loads(Path(path).read_text())
    report_type = str(doc.get("report_type", "")).upper()

    section_names = list((doc.get("schema") or {}).get("sections") or {})
    sections: dict[str, list[str]] = {}
    if section_names:
        for name in section_names:
            val = doc.get(name)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                sections[name] = list(val[0].keys())
            elif isinstance(val, dict):
                sections[name] = list(val.keys())
    else:
        # Defensive fallback for a future spec with no schema.sections: keep the
        # brief's doc.items() heuristic. All three shipped templates declare
        # schema.sections, so this branch is not exercised by them.
        for key, value in doc.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                sections[key] = list(value[0].keys())
            elif isinstance(value, dict) and key not in (
                    "schema", "controlled_vocabulary", "report_writer_guidance",
                    "format", "links"):
                if all(not isinstance(v, (dict, list)) or v is None
                       for v in value.values()):
                    sections[key] = list(value.keys())

    required = {
        name: [f for f in fields
               if f.startswith("*") and not f.startswith("**")]
        for name, fields in sections.items()
    }
    cv = {k: v for k, v in (doc.get("controlled_vocabulary") or {}).items()
          if isinstance(v, list)}

    return TemplateSpec(
        report_type=report_type,
        sections=sections,
        required=required,
        cv=cv,
        row_section=ROW_SECTION.get(report_type, "samples"),
        raw=doc,
    )


def cv_for_field(spec: TemplateSpec, target_field: str) -> list[str] | None:
    """Allowed values for a target field, or None when it is free text."""
    if target_field == "*single or paired-end":
        return list(_GEO_LAYOUT_CV)
    key = _CV_KEY_FOR_FIELD.get(target_field)
    if key is None:
        return None
    values = spec.cv.get(key)
    return list(values) if values else None


def source_columns(normalized) -> set[str]:
    """Every metadata key present on any sample in the input."""
    out: set[str] = set()
    for s in normalized.samples:
        out.update(s.metadata.keys())
    return out


def _leaf_columns(normalized, target_sampletype: str | None) -> set[str]:
    """Columns present on the TARGET rows, not on ancestors.

    A column that exists only on an ancestor needs `via_lineage: true`; without
    it the executor would silently produce blanks for every row.
    """
    out: set[str] = set()
    for s in normalized.samples:
        if target_sampletype and s.sample_type != target_sampletype:
            continue
        out.update(s.metadata.keys())
    return out


def validate_mapping(mapping: dict, spec: TemplateSpec, normalized) -> list[MappingError]:
    """Check a mapping against the template, its CV, and the actual input.

    Every check here is one the executor would otherwise discover halfway
    through writing rows, or worse, not discover at all.
    """
    errors: list[MappingError] = []

    declared = str(mapping.get("report_type", "")).upper()
    if declared != spec.report_type:
        errors.append(MappingError(
            "_", "report_type", "report_type_mismatch",
            f"mapping declares {declared!r} but the template is "
            f"{spec.report_type!r}"))

    row_scope = mapping.get("row_scope") or {}
    target_type = row_scope.get("target_sampletype") or TARGET_SAMPLETYPE.get(
        spec.report_type)
    actual_rows = sum(1 for s in normalized.samples
                      if not target_type or s.sample_type == target_type)
    expected = row_scope.get("expected_rows")
    if expected is not None and expected != actual_rows:
        errors.append(MappingError(
            "_", "row_scope", "row_count_mismatch",
            f"mapping expects {expected} rows of {target_type!r} but the input "
            f"has {actual_rows}"))

    all_cols = source_columns(normalized)
    leaf_cols = _leaf_columns(normalized, target_type)

    for section, fields in mapping.items():
        if section in ("report_type", "source", "row_scope") or not isinstance(fields, dict):
            continue
        known = spec.sections.get(section)
        if known is None:
            errors.append(MappingError(
                section, "_", "unknown_section",
                f"template has no section {section!r}; it has "
                f"{sorted(spec.sections)}"))
            continue

        for target, directive in fields.items():
            if target not in known:
                errors.append(MappingError(
                    section, target, "unknown_field",
                    f"{target!r} is not a field of {section!r}"))
                continue
            if not isinstance(directive, dict):
                errors.append(MappingError(
                    section, target, "no_directive",
                    f"{target!r} must map to an object, got {type(directive).__name__}"))
                continue

            unknown = set(directive) - set(DIRECTIVES)
            if unknown:
                errors.append(MappingError(
                    section, target, "unknown_directive",
                    f"{target!r} uses {sorted(unknown)}; allowed: {list(DIRECTIVES)}"))

            primaries = [d for d in _PRIMARY_DIRECTIVES if d in directive]
            if not primaries:
                errors.append(MappingError(
                    section, target, "no_directive",
                    f"{target!r} has no source/const/synthesize/unmapped"))
                continue
            if len(primaries) > 1:
                errors.append(MappingError(
                    section, target, "conflicting_directives",
                    f"{target!r} has {primaries}; exactly one is allowed"))
                continue

            which = primaries[0]

            if which == "unmapped" and not str(directive["unmapped"]).strip():
                errors.append(MappingError(
                    section, target, "unmapped_without_reason",
                    f"{target!r} is unmapped with no stated reason"))

            if which == "synthesize" and section == spec.row_section:
                errors.append(MappingError(
                    section, target, "synthesize_in_row_section",
                    f"{target!r} uses synthesize in the row section; synthesize "
                    f"is study-level only, so it stays O(1) rather than O(rows)"))

            if which == "source":
                column = directive["source"]
                if column not in all_cols:
                    errors.append(MappingError(
                        section, target, "source_column_missing",
                        f"{target!r} sources {column!r}, absent from the input"))
                elif column not in leaf_cols and not directive.get("via_lineage"):
                    errors.append(MappingError(
                        section, target, "needs_via_lineage",
                        f"{target!r} sources {column!r}, which exists only on "
                        f"ancestor samples. Add \"via_lineage\": true, or every "
                        f"row will be blank."))

            allowed = cv_for_field(spec, target)
            if allowed:
                if which == "const" and directive["const"] not in allowed:
                    errors.append(MappingError(
                        section, target, "const_not_in_cv",
                        f"{target!r} const {directive['const']!r} is not in the "
                        f"controlled vocabulary. Nearest allowed: "
                        f"{_nearest(directive['const'], allowed)}"))
                for out_value in (directive.get("map") or {}).values():
                    if out_value not in allowed:
                        errors.append(MappingError(
                            section, target, "map_output_not_in_cv",
                            f"{target!r} map emits {out_value!r}, not in the "
                            f"controlled vocabulary. Nearest allowed: "
                            f"{_nearest(out_value, allowed)}"))

    for section, req_fields in spec.required.items():
        if section not in mapping:
            continue
        mapped = mapping[section]
        if not isinstance(mapped, dict):
            continue
        for req in req_fields:
            if req not in mapped:
                errors.append(MappingError(
                    section, req, "required_unmapped",
                    f"required field {req!r} has no directive. Give it "
                    f"source/const/synthesize, or unmapped with a reason."))

    return errors


def _nearest(value: str, allowed: list[str], limit: int = 3) -> list[str]:
    """Closest allowed values, so an error message is actionable.

    GEO dropdowns are word- and case-exact: `paired-end` not `paired`,
    `Illumina NextSeq 500` not `NextSeq 500`.
    """
    import difflib
    hits = difflib.get_close_matches(str(value), allowed, n=limit, cutoff=0.4)
    return hits or allowed[:limit]
