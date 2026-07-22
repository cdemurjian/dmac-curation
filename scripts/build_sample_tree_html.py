#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2>=3.1"]
# ///
"""Render a project's sample_tree.json into an interactive SAMPLE_TREE.html.

Usage (from a curation project root):

    uv run --script <PLUGIN>/scripts/build_sample_tree_html.py
    uv run --script <PLUGIN>/scripts/build_sample_tree_html.py --input sample_tree.json \
        --output SAMPLE_TREE.html --title "..." --subtitle "..."

Input schema — sample_tree.json:

    {
      "title":    "...",                     optional, overridden by --title
      "subtitle": "...",                     optional
      "footer":   "...",                     optional
      "nodes": [
        {
          "id": "TIS",                       required, unique
          "label": "Wasp head specimen",     required, human-readable
          "display_code": "TIS",             optional, defaults to id
          "clade": "Processed",              optional — derived from assays_db if omitted
          "count": 39,                       optional — instance count, shown as "TIS ×39"
          "match_type": "existing_nextseek", optional — "proposed_new" draws a dashed border
          "type_status": "existing",         optional — "created" counts in the stats bar
          "evidence_strength": "strong",     optional
          "sources": ["..."],                optional
          "quotes":  ["..."],                optional — verbatim manuscript support
          "rationale": "...",                optional — string or list; text containing
                                             "NOTE FOR CURATOR" / "FLAG FOR CURATOR" is
                                             surfaced as a highlighted flag
          "sample_type_id": 12               optional
        }
      ],
      "edges": [
        {
          "from": "TIS", "to": "D.IMG",      required, must reference declared nodes
          "assays": ["Imaging"],             optional, drives the edge label + clade lookup
          "assay_id": 29,                    optional
          "assay_status": "reused",          optional
          "match_type": "existing_nextseek", optional
          ... same optional evidence fields as nodes
        }
      ]
    }

Only `id`/`label` on nodes and `from`/`to` on edges are required. Everything else
renders when present, so a tree can be published early and enriched as curation
proceeds.

Clade derivation: when a node omits "clade", it is looked up from the bundled
context/assays_db.json via the assay on its edges — an assay declares
"Parent Clade Type" and "Child Clade Type", which fix the clades of the two
endpoints it connects. Conflicts and gaps are reported, never silently guessed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PLUGIN = Path(__file__).resolve().parent.parent
ASSAYS_DB = PLUGIN / "context" / "assays_db.json"
TEMPLATES = PLUGIN / "templates"
VALID_CLADES = {"Source", "Processed", "Raw", "Analyzed"}


def load_assay_clades() -> dict[str, tuple[str | None, str | None]]:
    """Map assay name -> (parent clade, child clade) from the bundled context DB."""
    if not ASSAYS_DB.exists():
        return {}
    raw = json.loads(ASSAYS_DB.read_text())
    recs = raw if isinstance(raw, list) else next(iter(raw.values()))
    out: dict[str, tuple[str | None, str | None]] = {}
    for r in recs:
        name = r.get("Name")
        if not name:
            continue
        p, c = r.get("Parent Clade Type"), r.get("Child Clade Type")
        # Several assay names appear twice; keep the first record that carries clades.
        if name in out and out[name] != (None, None):
            continue
        out[name] = (p, c)
    return out


def derive_clades(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Fill in missing node clades from assay definitions. Returns warning strings."""
    clades = load_assay_clades()
    proposed: dict[str, set[str]] = defaultdict(set)
    warnings: list[str] = []

    for e in edges:
        for assay in e.get("assays") or []:
            if assay not in clades:
                warnings.append(f"assay {assay!r} not in assays_db.json — no clade derived")
                continue
            parent, child = clades[assay]
            if parent:
                proposed[e["from"]].add(parent)
            if child:
                proposed[e["to"]].add(child)

    for n in nodes:
        declared = n.get("clade")
        cand = proposed.get(n["id"], set())
        if declared:
            if declared not in VALID_CLADES:
                warnings.append(f"node {n['id']}: clade {declared!r} is not one of {sorted(VALID_CLADES)}")
            elif cand and declared not in cand:
                warnings.append(
                    f"node {n['id']}: declared clade {declared!r} contradicts assay "
                    f"definition {sorted(cand)} — check the assay or the override"
                )
            continue
        if len(cand) == 1:
            n["clade"] = cand.pop()
        elif len(cand) > 1:
            warnings.append(
                f"node {n['id']}: assays disagree on clade {sorted(cand)} — set it explicitly"
            )
        else:
            warnings.append(f"node {n['id']}: no clade declared and none derivable — defaulting to Source")
            n["clade"] = "Source"
    return warnings


def validate(data: dict) -> list[str]:
    errs: list[str] = []
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        errs.append("'nodes' must be a non-empty list")
        return errs
    if not isinstance(edges, list):
        errs.append("'edges' must be a list")
        return errs

    seen: set[str] = set()
    for i, n in enumerate(nodes):
        if not n.get("id"):
            errs.append(f"nodes[{i}] missing 'id'")
            continue
        if n["id"] in seen:
            errs.append(f"duplicate node id {n['id']!r}")
        seen.add(n["id"])
        if not n.get("label"):
            errs.append(f"node {n['id']}: missing 'label'")
    for i, e in enumerate(edges):
        for k in ("from", "to"):
            if not e.get(k):
                errs.append(f"edges[{i}] missing {k!r}")
            elif e[k] not in seen:
                errs.append(f"edges[{i}] {k}={e[k]!r} references an undeclared node")
    return errs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="sample_tree.json", type=Path)
    ap.add_argument("--output", default="SAMPLE_TREE.html", type=Path)
    ap.add_argument("--title")
    ap.add_argument("--subtitle")
    ap.add_argument("--footer")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any clade warning is raised")
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"no such file: {args.input}\nWrite a sample_tree.json first — see the module docstring for the schema.")
    try:
        data = json.loads(args.input.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{args.input} is not valid JSON: {exc}")

    errs = validate(data)
    if errs:
        sys.exit("invalid sample_tree.json:\n  " + "\n  ".join(errs))

    nodes, edges = data["nodes"], data["edges"]
    warnings = derive_clades(nodes, edges)

    title = args.title or data.get("title") or "Sample tree"
    n_rows = sum(n.get("count") or 0 for n in nodes)
    default_sub = f"{len(nodes)} sample types, {len(edges)} assay connections"
    if n_rows:
        default_sub += f", {n_rows} rows"
    subtitle = args.subtitle or data.get("subtitle") or default_sub
    footer = args.footer or data.get("footer") or "Draft sample tree for NExtSEEK — generated for scientific review"

    graph_json = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)
    # Keep the payload from terminating the <script> block it lives in.
    graph_json = graph_json.replace("</", "<\\/")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined,
                      autoescape=False)
    html = env.get_template("SAMPLE_TREE.html.j2").render(
        title=title, subtitle=subtitle, footer=footer, graph_json=graph_json)

    if "{{" in html:
        sys.exit("render left unresolved '{{' in the output — a literal '{{' has crept into "
                 "SAMPLE_TREE.html.j2; see the editor note at the top of that template")

    args.output.write_text(html)

    print(f"wrote {args.output}  ({len(html):,} bytes)")
    print(f"  {len(nodes)} nodes, {len(edges)} edges" + (f", {n_rows} rows" if n_rows else ""))
    by_clade: dict[str, int] = defaultdict(int)
    for n in nodes:
        by_clade[n["clade"]] += 1
    print("  clades: " + ", ".join(f"{k}={v}" for k, v in sorted(by_clade.items())))
    if warnings:
        print(f"\n  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"    - {w}")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
