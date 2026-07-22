# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Apply a validated mapping across every row. Fully deterministic.

No LLM runs here. The mapping already encoded every decision; this walks rows
and fills cells.

Two behaviours matter more than the mechanics:

  1. UNFILLABLE FIELDS DEGRADE, THEY DO NOT ABORT. A value that cannot be found
     becomes `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 -
     greppable, unlike a blank) and is recorded in the completeness report with
     the field, what was searched, and why it failed. Never silently fabricate;
     never refuse outright. The curator decides.

  2. ROW PARITY IS ASSERTED. chat_nextseek gates its code path on 20+ target
     samples and discards the result when the emitted row count does not match
     the expected count; their own assessment calls that guard "the single most
     valuable idea to carry over". Here the executor controls row count by
     construction, so parity is structural rather than checked after the fact -
     but it is asserted anyway, because a structural guarantee that is never
     checked is a comment.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import placeholder  # noqa: E402
from report.adapters import index_by_uid, resolve_via_lineage  # noqa: E402
from report.mapping import TARGET_SAMPLETYPE  # noqa: E402

OUTPUT_SUBDIR = "report"


class RowParityError(Exception):
    """Emitted row count does not match the mapping's declared expectation."""


@dataclass
class Gap:
    """One field that could not be filled, and why."""

    section: str
    field: str
    reason: str
    searched: str
    uid: str = ""


def _fill_row(target: str, directive: dict, sample, by_uid,
              section: str, gaps: list[Gap]) -> str:
    if "unmapped" in directive:
        return ""  # deliberately empty, reason already stated in the mapping

    if "const" in directive:
        return directive["const"]

    if "source" in directive:
        column = directive["source"]
        if directive.get("via_lineage"):
            value = resolve_via_lineage(sample, by_uid, column)
            searched = f"{column} on {sample.uid} and its Parent chain"
            why = "not present on the sample or any resolvable ancestor"
        else:
            raw = sample.metadata.get(column)
            value = None if raw in (None, "") else str(raw)
            searched = f"{column} on {sample.uid}"
            why = "column present in the input but empty on this row"
        if value is None:
            gaps.append(Gap(section, target, why, searched, sample.uid))
            return placeholder(f"{target} not derivable from {column}")
        mapped = (directive.get("map") or {}).get(value)
        return mapped if mapped is not None else value

    gaps.append(Gap(section, target, "no usable directive",
                    "the mapping itself", sample.uid))
    return placeholder(f"{target} has no usable directive")


def apply_mapping(mapping: dict, spec, normalized, *,
                  synthesized: dict | None = None) -> tuple[dict, list[Gap]]:
    """Apply the mapping. Returns (filled document, gaps).

    Args:
      mapping:     a mapping spec that has already passed validate_mapping().
      spec:        the TemplateSpec it was validated against.
      normalized:  the adapter output.
      synthesized: {section: {field: text}} from the LLM's step-6 pass. Fields
                   with a `synthesize` directive and no supplied text become
                   placeholders rather than blanks.
    """
    synthesized = synthesized or {}
    gaps: list[Gap] = []
    by_uid = index_by_uid(normalized)

    row_scope = mapping.get("row_scope") or {}
    target_type = row_scope.get("target_sampletype") or TARGET_SAMPLETYPE.get(
        spec.report_type)
    rows_in = [s for s in normalized.samples
               if not target_type or s.sample_type == target_type]

    filled: dict = {}
    row_section = spec.row_section

    for section, fields in mapping.items():
        if section in ("report_type", "source", "row_scope") or not isinstance(fields, dict):
            continue

        if section == row_section:
            out_rows = []
            for sample in rows_in:
                out_rows.append({
                    target: _fill_row(target, directive, sample, by_uid,
                                      section, gaps)
                    for target, directive in fields.items()
                })
            filled[section] = out_rows
            continue

        block: dict = {}
        for target, directive in fields.items():
            if "synthesize" in directive:
                text = (synthesized.get(section) or {}).get(target)
                if text:
                    block[target] = text
                else:
                    gaps.append(Gap(
                        section, target,
                        "requires prose the input does not carry; the "
                        "synthesize step produced nothing",
                        directive["synthesize"]))
                    block[target] = placeholder(
                        f"{target}: {directive['synthesize']}")
            elif "const" in directive:
                block[target] = directive["const"]
            elif "unmapped" in directive:
                block[target] = ""
            elif "source" in directive:
                first = rows_in[0] if rows_in else None
                block[target] = (
                    _fill_row(target, directive, first, by_uid, section, gaps)
                    if first is not None else placeholder(f"{target}: no rows"))
            else:
                block[target] = placeholder(f"{target} has no usable directive")
        filled[section] = block

    expected = row_scope.get("expected_rows")
    produced = len(filled.get(row_section, []))
    if expected is not None and produced != expected:
        raise RowParityError(
            f"mapping declared {expected} rows in {row_section!r} but the "
            f"executor produced {produced}. Refusing to emit a partial artifact."
        )
    return filled, gaps


def write_filled(root: Path, report_type: str, filled: dict) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{report_type}_filled.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(filled, indent=2) + "\n")
    return p


def render_completeness(report_type: str, gaps: list[Gap], mapping: dict,
                        normalized) -> str:
    """Name every unfilled field, the input searched, and why it failed."""
    lines = [f"# {report_type} completeness report", ""]
    lines.append(f"Input: `{(mapping.get('source') or {}).get('path') or (mapping.get('source') or {}).get('adapter', 'unknown')}`")
    lines.append(f"Samples in input: {len(normalized.samples)}")
    lines.append("")

    if not gaps:
        lines.append("**No gaps.** Every mapped field was filled from the input.")
        lines.append("")
    else:
        lines.append(f"## Unfilled fields ({len(gaps)})")
        lines.append("")
        lines.append("Each is written as `*** PLACEHOLDER: ... ***` in the "
                     "artifact, which is greppable. A blank is not.")
        lines.append("")
        lines.append("| section | field | uid | searched | why it failed |")
        lines.append("|---|---|---|---|---|")
        by_field: dict[tuple[str, str], list[Gap]] = {}
        for g in gaps:
            by_field.setdefault((g.section, g.field), []).append(g)
        for (section, field_name), group in sorted(by_field.items()):
            first = group[0]
            uids = (first.uid if len(group) == 1
                    else f"{first.uid} and {len(group) - 1} more")
            lines.append(f"| {section} | `{field_name}` | {uids} | "
                         f"{first.searched} | {first.reason} |")
        lines.append("")

    deliberate = []
    for section, fields in mapping.items():
        if not isinstance(fields, dict):
            continue
        for target, directive in fields.items():
            if isinstance(directive, dict) and directive.get("unmapped"):
                deliberate.append((section, target, directive["unmapped"]))
    if deliberate:
        lines.append("## Deliberately unmapped")
        lines.append("")
        lines.append("Left empty on purpose, with a stated reason. Not a gap.")
        lines.append("")
        for section, target, reason in sorted(deliberate):
            lines.append(f"- `{section}.{target}` - {reason}")
        lines.append("")

    lines.append("## What to do")
    lines.append("")
    lines.append("Fill by hand, enrich from another source, or proceed. The "
                 "tool never fabricates a value and never refuses outright; "
                 "this decision is yours.")
    lines.append("")
    return "\n".join(lines)


def write_completeness(root: Path, report_type: str, markdown: str) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{report_type}.completeness.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown)
    return p
