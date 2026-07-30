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
          "label": "Fixed tissue specimen",  required, human-readable
          "display_code": "TIS",             optional, defaults to id
          "clade": "Processed",              optional — derived from assays_db if omitted
          "count": 24,                       optional — instance count, shown as "TIS ×24"
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
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PLUGIN = Path(__file__).resolve().parent.parent
ASSAYS_DB = PLUGIN / "context" / "assays_db.json"
CONN_DB = PLUGIN / "context" / "neo4j_assay-sample-conn.json"
TEMPLATES = PLUGIN / "templates"
VALID_CLADES = {"Source", "Processed", "Raw", "Analyzed"}
# Suffixes that distinguish assay variants without changing the underlying clade pair.
BASE_ASSAY_RE = re.compile(r"\s*-\s*(Metadata|Data Linked)\s*$", re.IGNORECASE)


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


def load_connections() -> list[dict]:
    if not CONN_DB.exists():
        return []
    raw = json.loads(CONN_DB.read_text())
    return raw.get("connections", raw) if isinstance(raw, dict) else raw


def validate_edges(edges: list[dict]) -> list[str]:
    """Check every edge against the Neo4j connection graph.

    This is the guard against the two ways a hand-derived tree goes wrong:

      * inventing an assay that already exists under a different name
        ("gpt Mutant Frequency Assay" when "GPT Assay" is right there), and
      * proposing a parent->child pair as new when the schema already licenses it
        via an assay the author did not think to look for.

    Anything genuinely absent must carry ``match_type: proposed_new`` so it renders
    dashed. Anything present must NOT, or the diagram tells a reviewer to go request
    a vocabulary change that is not needed.
    """
    conns = load_connections()
    if not conns:
        return ["connection graph unavailable — edge legality NOT checked"]

    triples = {(c["parent_type"], c["child_type"], c["assay"]) for c in conns}
    by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_assay: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for c in conns:
        by_pair[(c["parent_type"], c["child_type"])].add(c["assay"])
        by_assay[c["assay"]].add((c["parent_type"], c["child_type"]))
    all_assays = sorted(by_assay)

    warnings: list[str] = []
    for e in edges:
        pair = (e["from"], e["to"])
        proposed = e.get("match_type") == "proposed_new"
        for assay in e.get("assays") or ["(none)"]:
            if (pair[0], pair[1], assay) in triples:
                if proposed:
                    warnings.append(
                        f"edge {pair[0]} -> {pair[1]} ({assay!r}) is marked proposed_new but "
                        f"ALREADY EXISTS in the connection graph — drop the proposal, it renders "
                        f"dashed and sends the curator to the admins for nothing"
                    )
                continue

            # Not licensed as written. Work out the most useful correction.
            hints: list[str] = []
            if by_pair.get(pair):
                hints.append(
                    f"the pair IS licensed by {sorted(by_pair[pair])} — use one of those assay names"
                )
            if assay not in by_assay:
                near = difflib.get_close_matches(assay, all_assays, n=3, cutoff=0.6)
                if near:
                    hints.append(f"no such assay; did you mean {near}?")
                else:
                    hints.append("no such assay in the connection graph")
            else:
                hints.append(
                    f"that assay exists but only connects {sorted(by_assay[assay])[:4]}"
                )
            msg = f"edge {pair[0]} -> {pair[1]} ({assay!r}) is not licensed: " + "; ".join(hints)
            if not proposed:
                msg += ". Mark it proposed_new or correct it"
            warnings.append(msg)

    warnings += suggest_generic_assays(edges, by_pair, by_assay)
    warnings += flag_attribute_candidates(edges)
    return warnings


def suggest_generic_assays(edges: list[dict],
                           by_pair: dict[tuple[str, str], set[str]],
                           by_assay: dict[str, set[tuple[str, str]]]) -> list[str]:
    """Nudge toward the most general assay that covers a step.

    Several assays often license the same parent->child pair: a generic one
    ("Imaging - Data Linked") alongside narrow variants ("Microfluidic Network
    Imaging - Data Linked", "Device Imaging"). Real curated deposits overwhelmingly
    use the generic one, because a narrow variant fragments the same step across
    studies and makes cross-study queries miss rows.

    Generality is measured by how many distinct pairs an assay licenses, but ONLY
    within the same suffix family. "- Data Linked" and "- Metadata" are not cosmetic:
    they record whether the tier carries data files. Recommending bare "Imaging" over
    "Imaging - Data Linked" would silently drop that, so the comparison is confined to
    assays sharing the querying assay's suffix.
    """
    def family(name: str) -> str:
        m = BASE_ASSAY_RE.search(name)
        return m.group(1).lower() if m else ""

    out: list[str] = []
    for e in edges:
        pair = (e["from"], e["to"])
        for assay in e.get("assays") or []:
            alts = {a for a in by_pair.get(pair, set()) if family(a) == family(assay)}
            if assay not in alts or len(alts) < 2:
                continue
            ranked = sorted(alts, key=lambda a: (-len(by_assay[a]), len(a)))
            best = ranked[0]
            if best != assay and len(by_assay[best]) > len(by_assay[assay]):
                out.append(
                    f"edge {pair[0]} -> {pair[1]} uses {assay!r} (licenses "
                    f"{len(by_assay[assay])} pair(s)) but {best!r} also covers it and is more "
                    f"general ({len(by_assay[best])} pairs) — prefer the general assay unless the "
                    f"variant is deliberate"
                )
    return out


def flag_attribute_candidates(edges: list[dict]) -> list[str]:
    """Flag nodes that probably should not be nodes at all.

    A node whose every edge is proposed_new is usually something the schema models as
    an *attribute* rather than a sample: a drug treatment, a culture condition, a
    differentiation state. Proposing a whole node plus its edge for that sends the
    curator to the admins when editing a field would do.
    """
    touching: dict[str, list[bool]] = defaultdict(list)
    for e in edges:
        proposed = e.get("match_type") == "proposed_new"
        touching[e["from"]].append(proposed)
        touching[e["to"]].append(proposed)
    out: list[str] = []
    for node, flags in sorted(touching.items()):
        if flags and all(flags):
            out.append(
                f"node {node} participates ONLY in proposed_new edges — check whether it belongs "
                f"in the schema as an attribute on its neighbour (treatment, dose, condition) "
                f"rather than as a sample node"
            )
    return out


def load_known_assays() -> set[str]:
    """Assay names that appear in the Neo4j connection graph.

    The connection graph and assays_db.json are not fully in sync: some real, in-use
    assays ("RaDR - Data Linked", "Real Time RT-PCR - Data Linked") license edges but
    have no assays_db entry, so no clade can be derived for them. Distinguishing those
    from genuinely proposed assays keeps the warnings honest.
    """
    if not CONN_DB.exists():
        return set()
    raw = json.loads(CONN_DB.read_text())
    conns = raw.get("connections", raw) if isinstance(raw, dict) else raw
    return {c["assay"] for c in conns if c.get("assay")}


def derive_clades(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Fill in missing node clades from assay definitions. Returns warning strings.

    A node's clade describes what it *is*, which is fixed by what produced it. So the
    child role wins: a node that is the target of any edge takes its clade from that
    edge's assay "Child Clade Type". The parent role is consulted only for roots, which
    have nothing upstream to inherit from. Without this precedence a mid-tree node like
    a study visit or a tissue looks ambiguous — Source as a parent, Processed as a child
    — when it is not actually ambiguous at all.

    Every node is guaranteed a clade on return; ambiguity produces a warning and a
    deterministic choice, never a missing key.
    """
    clades = load_assay_clades()
    as_child: dict[str, set[str]] = defaultdict(set)
    as_parent: dict[str, set[str]] = defaultdict(set)
    unknown_assays: set[str] = set()
    warnings: list[str] = []

    for e in edges:
        for assay in e.get("assays") or []:
            entry = clades.get(assay)
            if entry is None:
                # Curated deposits use the suffixed assay variants ("Tissue Collection - Metadata",
                # "Short Read Sequencing - Data Linked"). Those are real, distinct assays in the
                # connection graph, but assays_db.json stores clades under the base name only.
                # Fall back to the base so using the accurate name does not lose the clade.
                base = BASE_ASSAY_RE.sub("", assay).strip()
                entry = clades.get(base)
                if entry is None:
                    unknown_assays.add(assay)
                    continue
            parent, child = entry
            if parent:
                as_parent[e["from"]].add(parent)
            if child:
                as_child[e["to"]].add(child)

    known = load_known_assays()
    for assay in sorted(unknown_assays):
        if assay in known:
            warnings.append(
                f"assay {assay!r} licenses edges in the connection graph but has no "
                f"assays_db.json entry, so no clade could be derived — the two context files "
                f"disagree. Declare 'clade' on its endpoints and report the gap upstream."
            )
        else:
            warnings.append(
                f"assay {assay!r} is in neither context file — expected for a proposed_new "
                f"assay; declare 'clade' on its endpoints"
            )

    for n in nodes:
        nid = n["id"]
        cand = as_child.get(nid) or as_parent.get(nid) or set()
        role = "child" if as_child.get(nid) else "parent"
        declared = n.get("clade")

        if declared:
            if declared not in VALID_CLADES:
                warnings.append(
                    f"node {nid}: clade {declared!r} is not one of {sorted(VALID_CLADES)}")
            elif cand and declared not in cand:
                warnings.append(
                    f"node {nid}: declared clade {declared!r} contradicts the assay "
                    f"definition {sorted(cand)} ({role} role) — check the assay or the override"
                )
            continue

        if len(cand) == 1:
            n["clade"] = next(iter(cand))
        elif len(cand) > 1:
            choice = sorted(cand)[0]
            n["clade"] = choice
            warnings.append(
                f"node {nid}: assays disagree on {role} clade {sorted(cand)} — "
                f"using {choice!r}; declare 'clade' explicitly to silence this"
            )
        else:
            n["clade"] = "Source"
            warnings.append(
                f"node {nid}: no clade declared and none derivable — defaulting to 'Source'")
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
    warnings = validate_edges(edges)
    warnings += derive_clades(nodes, edges)

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

    # Compute the full report before touching disk, so a failure here cannot leave a
    # half-validated artifact behind for someone to review in good faith.
    by_clade: dict[str, int] = defaultdict(int)
    missing = [n["id"] for n in nodes if not n.get("clade")]
    if missing:
        sys.exit(f"internal error: nodes left without a clade: {missing}")
    for n in nodes:
        by_clade[n["clade"]] += 1

    args.output.write_text(html)

    print(f"wrote {args.output}  ({len(html):,} bytes)")
    print(f"  {len(nodes)} nodes, {len(edges)} edges" + (f", {n_rows} rows" if n_rows else ""))
    print("  clades: " + ", ".join(f"{k}={v}" for k, v in sorted(by_clade.items())))
    if warnings:
        print(f"\n  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"    - {w}")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
