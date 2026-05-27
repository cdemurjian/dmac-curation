#!/usr/bin/env bash
set -euo pipefail

# E2E smoke test: simulate /curate-init in a temp dir and verify scaffold.
# This tests the underlying logic (template rendering, lockfile writing) that
# /curate-init invokes. The actual slash command requires a Claude Code session.

PLUGIN="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap "rm -rf $TMP" EXIT

cd "$TMP"

# Render the templates the same way the /curate-init command does
PLUGIN_PATH="$PLUGIN" uv run --with jinja2 python3 <<PY
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import json, datetime, os, sys

plugin = os.environ["PLUGIN_PATH"]
env = Environment(
    loader=FileSystemLoader(plugin + "/templates"),
    undefined=StrictUndefined,
)
today = datetime.date.today().isoformat()
ctx = {"lab": "KAM", "pi_name": "marie", "init_date": today}

renders = [
    ("CLAUDE.md.j2", "CLAUDE.md", {}),
    ("env.example.j2", ".env.example", {}),
    ("gitignore.j2", ".gitignore", {}),
    ("pyproject.toml.j2", "pyproject.toml", {"project_slug": "marie_curation"}),
]
for tpl, dest, extra in renders:
    template = env.get_template(tpl)
    with open(dest, "w") as f:
        f.write(template.render(**ctx, **extra))

for d in ("files", "manuscript", "previous_metadata", "assay_sheets", "scripts"):
    os.makedirs(d, exist_ok=True)

with open(".dmac-curation.json", "w") as f:
    json.dump({
        "plugin_name": "dmac-curation",
        "plugin_sha": "test-sha",
        "plugin_version": "0.1.0",
        "schema_vintage": json.load(open(plugin + "/context/VINTAGE.json"))["bundled_date"],
        "init_date": today,
        "init_user": os.environ.get("USER", "test"),
        "lab": "KAM",
        "pi": "marie",
        "nextseek_project_id": None,
    }, f, indent=2)

print("init OK")
PY

# Verify scaffold
for f in CLAUDE.md .env.example .gitignore pyproject.toml .dmac-curation.json; do
    test -f "$f" || { echo "FAIL: missing $f"; exit 1; }
done
for d in files manuscript previous_metadata assay_sheets scripts; do
    test -d "$d" || { echo "FAIL: missing dir $d"; exit 1; }
done

# Verify lockfile content
LAB=$(python3 -c "import json; print(json.load(open('.dmac-curation.json'))['lab'])")
test "$LAB" = "KAM" || { echo "FAIL: lockfile lab != KAM (got $LAB)"; exit 1; }

# Verify CLAUDE.md has rendered values
grep -q "Marie" CLAUDE.md || { echo "FAIL: CLAUDE.md missing PI name"; exit 1; }
grep -q "KAM" CLAUDE.md || { echo "FAIL: CLAUDE.md missing lab"; exit 1; }

echo "E2E init smoke test: PASS"
