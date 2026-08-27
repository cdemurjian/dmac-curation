# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render `<TYPE>.review.md` - schema mode's actual deliverable.

The JSON artifacts exist to feed tooling. This markdown is what the work is
*for*: a human reads it and decides what to apply, by hand.

Rationale-per-change is the point. A bare field list cannot be judged; a field
list with evidence can. Reuse decisions are stated explicitly so they can be
overruled, not buried.

This module never proposes renaming or splitting an existing field name. A name
shared across sample types is not a defect: `Type` appears on many types and
legitimately means different things on each. The review records what a field
means *here*.
"""
from __future__ import annotations

import json
from pathlib import Path

OUTPUT_SUBDIR = "schema"

REQUIRED_SECTIONS = (
    "## Current state",
    "## External clade evidence",
    "## Reference template checklist",
    "## Proposed additions",
    "## Reuse decisions",
    "## Controlled vocabularies proposed",
    "## Open questions and placeholders",
    "## How to apply",
)


def render_review(sampletype: str, *, record: dict, current_fields: dict,
                  proposals: list[dict], reuse_decisions: list[dict],
                  ontology: dict, open_questions: list[str],
                  dictionary_entries: list[str],
                  external_clade: dict | None = None,
                  template_checklist: dict | None = None) -> str:
    """Build the review markdown.

    Args:
      sampletype:         short code, e.g. 'D.VIA'.
      record:             the current catalog record.
      current_fields:     {"required": [...], "standard": [...], "possible": [...]}.
      proposals:          [{"field", "rationale", "evidence": [...]}].
      reuse_decisions:    [{"proposed", "used_instead", "reason"}].
      ontology:           {field: [ProposedValue]} from schema.ontology.
      open_questions:     things that could not be resolved, and why.
      dictionary_entries: field names this run wrote to field_dictionary.json.
      external_clade:     {"matched", "source", "neighbors", "reason"} from
                          schema.terms.clade_neighbors, or None if not consulted.
      template_checklist: {"template", "covered", "total", "missing", "reason"}
                          from schema.templates, or None if not consulted.
    """
    req = current_fields.get("required", [])
    std = current_fields.get("standard", [])
    pos = current_fields.get("possible", [])
    lines: list[str] = []

    lines.append(f"# {sampletype} - {record.get('Name', '')}")
    lines.append("")
    lines.append("**This is a proposal.** Nothing here has been applied. schema "
                 "mode never writes to NExtSEEK and never edits "
                 "`sampletypes_db.json`.")
    lines.append("")

    lines.append("## Current state")
    lines.append("")
    lines.append(f"{len(req)} required / {len(std)} standard / {len(pos)} possible "
                 f"= {len(req) + len(std) + len(pos)} fields.")
    lines.append("")
    lines.append(f"- **Clade:** {record.get('Clade') or '(none)'}")
    lines.append(f"- **Producing assay:** {record.get('Associated Assay Parents') or '(none)'}")
    lines.append(f"- **Parent sample types:** {record.get('Parent_SampleTypes') or '(none)'}")
    lines.append("")
    for label, fields in (("Required", req), ("Standard", std), ("Possible", pos)):
        lines.append(f"- **{label}:** {', '.join(fields) if fields else '(none)'}")
    lines.append("")

    lines.append("## External clade evidence")
    lines.append("")
    lines.append("Evidence only - read, not applied. Where an external ontology "
                 "splits one class into several, the axis it splits on is often "
                 "a field this type is missing. Judging that axis is the "
                 "curator's, never the tool's.")
    lines.append("")
    clade = external_clade or {}
    neighbors = clade.get("neighbors") or []
    if not neighbors:
        reason = clade.get("reason") or ""
        lines.append(f"Nothing returned - {reason}." if reason
                     else "Not consulted this run.")
        lines.append("")
    else:
        matched, source = clade.get("matched") or "", clade.get("source") or ""
        confidence = clade.get("confidence") or ""
        if not matched:
            lines.append("Matched an external class.")
        elif confidence == "weak":
            lines.append(
                f"Resolved to `{matched}` in **{source}** - but this is a WEAK "
                "match. No class carries the queried name, so this is BioPortal's "
                "top lexical hit and may be the wrong class entirely. Verify it "
                "before resting anything on what follows.")
        else:
            lines.append(f"Matched `{matched}` in **{source}**.")
        lines.append("")
        for n in neighbors:
            lines.append(f"- **{n.get('relation', '')}** - {n.get('label', '')}")
            if n.get("definition"):
                lines.append(f"  - {n['definition']}")
        lines.append("")

    lines.append("## Reference template checklist")
    lines.append("")
    lines.append("A well-specified reference record for this kind of work, diffed "
                 "against this type. A field listed here is a question - does "
                 "this house collect it, under some other name, or not at all? - "
                 "and not an instruction.")
    lines.append("")
    checklist = template_checklist or {}
    missing = checklist.get("missing") or []
    reason = checklist.get("reason") or ""
    if reason:
        lines.append(f"Nothing returned - {reason}.")
        lines.append("")
    elif not checklist:
        lines.append("Not consulted this run.")
        lines.append("")
    else:
        n_strong, n_weak = checklist.get("strong", 0), checklist.get("weak", 0)
        lines.append(
            f"`{checklist.get('template', '')}` declares "
            f"{checklist.get('total', 0)} fields. Of those, {n_strong} "
            f"{'has' if n_strong == 1 else 'have'} a strong existing match in the "
            f"catalog and {n_weak} {'has' if n_weak == 1 else 'have'} only a weak "
            "one. "
            "Coverage is the reuse check's verdict, not an exact-name diff: the "
            "reference writes prose names (`detection instrument`) and NExtSEEK "
            "writes compact ones (`Sequencer`), so the two conventions almost "
            "never collide and a name-level count means nothing.")
        lines.append("")
        if not missing:
            lines.append("Every field in the reference is already covered.")
            lines.append("")
        for m in missing:
            bits = []
            if m.get("branches"):
                bits.append("vocabulary: " + ", ".join(m["branches"]))
            if m.get("required"):
                bits.append("required in the reference")
            suffix = f" ({'; '.join(bits)})" if bits else ""
            lines.append(f"- **{m.get('name', '')}**{suffix}")
            if m.get("description"):
                lines.append(f"  - {m['description']}")
            if m.get("reuse"):
                lines.append(f"  - reuse check: {m['reuse']}")
        lines.append("")

    lines.append("## Proposed additions")
    lines.append("")
    if not proposals:
        lines.append("None. The current field set covers what this assay produces.")
    for p in proposals:
        lines.append(f"### `{p['field']}`")
        lines.append("")
        lines.append(p.get("rationale", ""))
        lines.append("")
        for ev in p.get("evidence") or []:
            lines.append(f"- {ev}")
        lines.append("")

    lines.append("## Reuse decisions")
    lines.append("")
    lines.append("Stated so they can be overruled. A name shared across sample "
                 "types is not a defect; nothing here proposes a rename or a split.")
    lines.append("")
    if not reuse_decisions:
        lines.append("No new names were considered this run.")
    for d in reuse_decisions:
        lines.append(f"- Used existing `{d['used_instead']}` rather than minting "
                     f"`{d['proposed']}` - {d['reason']}")
    lines.append("")

    lines.append("## Controlled vocabularies proposed")
    lines.append("")
    if not ontology:
        lines.append("None proposed this run.")
    for field_name, values in ontology.items():
        lines.append(f"### `{field_name}`")
        lines.append("")
        lines.append("| value | source | note |")
        lines.append("|---|---|---|")
        for v in values:
            lines.append(f"| {v.value} | {v.source} | {v.note} |")
        lines.append("")

    lines.append("## Open questions and placeholders")
    lines.append("")
    if not open_questions:
        lines.append("None.")
    for q in open_questions:
        lines.append(f"- {q}")
    lines.append("")

    lines.append("## How to apply")
    lines.append("")
    lines.append("Every step below is manual. Nothing is automated, by design.")
    lines.append("")
    lines.append(f"1. **Review each proposed addition above.** Reject anything "
                 f"whose rationale does not hold for your project.")
    lines.append(f"2. **Diff the proposed record.** "
                 f"`schema/{sampletype}.proposed.json` is shaped like a "
                 f"`sampletypes_db.json` entry, so a plain diff against the "
                 f"catalog record shows exactly what changes.")
    lines.append(f"3. **Confirm every ontology binding.** All are emitted "
                 f"`\"confirmed\": false`. Check each IRI actually denotes what "
                 f"the field means - the MUS prototype bound `Strain` to "
                 f"`NCBITaxon_10090`, which is a species, not a laboratory strain.")
    lines.append(f"4. **Put the vocabulary to work now, without waiting for a "
                 f"schema change.** `schema/{sampletype}.ontology.json` is "
                 f"directly consumable by "
                 f"`_common.write_4sheet_xlsx(ontology=...)`, so "
                 f"`/curate-build` can emit a 4-sheet workbook whose Ontology "
                 f"sheet enforces these values. That is the only upload format "
                 f"where NExtSEEK enforces controlled vocabulary; the flat "
                 f"format silently discards it.")
    lines.append(f"5. **Apply the record itself by hand**, through whatever "
                 f"channel your NExtSEEK instance uses for sample type changes. "
                 f"Confirm that channel with the NExtSEEK admin before editing "
                 f"anything - this is an open question the design did not settle.")
    lines.append("")

    if dictionary_entries:
        lines.append("## Field dictionary")
        lines.append("")
        lines.append(f"This run wrote {len(dictionary_entries)} entr"
                     f"{'y' if len(dictionary_entries) == 1 else 'ies'} to "
                     f"`schema/field_dictionary.json`: "
                     f"{', '.join(f'`{n}`' for n in dictionary_entries)}.")
        lines.append("")
        lines.append("The dictionary is lazy and local to this directory. It does "
                     "not accumulate across projects, and none ships with the "
                     "plugin.")
        lines.append("")

    return "\n".join(lines)


def write_review(root: Path, sampletype: str, markdown: str) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{sampletype}.review.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown)
    return p


def write_proposed_record(root: Path, sampletype: str, record: dict) -> Path:
    """Write the proposed catalog record, for diffing. Never edits the catalog."""
    p = Path(root) / OUTPUT_SUBDIR / f"{sampletype}.proposed.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return p
