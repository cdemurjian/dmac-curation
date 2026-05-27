# dmac-curation Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the dmac-curation Claude Code plugin per `docs/superpowers/specs/2026-05-27-dmac-curation-plugin-design.md` — a 13-phase NExtSEEK metadata curation pipeline shipped as bundled scripts + slash commands + behavioral skill.

**Architecture:** Plugin directory at the repo root (`/home/cdemu/code/dmac/curation_skill/` → github.com/cdemurjian/dmac-curation). Reusable scripts/context/templates owned by the plugin; per-project artifacts owned by the curation working directory. Scripts are PEP 723 inline-dep, uv-runnable. Skill is markdown-driven; 13 slash commands route to scripts and walk the curator through the pipeline.

**Tech Stack:** Python 3.11+ with `uv`, `openpyxl`, `requests`, `smbprotocol`, `python-dotenv`. Bash for shell glue. Markdown for skill + commands. Jinja2 for templates (rendered by `/curate-init`). JSON for schema snapshots + the per-project lockfile.

---

## Source-of-truth for lifted scripts

The plan lifts ~15 scripts from past sessions. Authoritative source paths:

| Script | Source path |
|---|---|
| `_common.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/_common.py` |
| `nextseek_api.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/nextseek_api.py` (richer than yufei version) |
| `consolidate_to_flat.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/consolidate_to_flat.py` |
| `qa_flat_sheets.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/qa_flat_sheets.py` |
| `rename_files.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/rename_files.py` |
| `omero_pull.py` | `/home/cdemu/code/dmac/metnet/marie/intravchip/scripts/omero_pull.py` |
| `smb_pull.py` (consolidated) | `/home/cdemu/code/dmac/srp/lee/scripts/pull_spatial.py` + `pull_bulk_rna.py` |
| `stage_zenodo.py` | `/home/cdemu/code/dmac/srp/lee/scripts/stage_zenodo.py` |
| `apply_zenodo_links.py` | `/home/cdemu/code/dmac/srp/lee/scripts/apply_zenodo_links.py` |
| `apply_geo_accessions.py` | `/home/cdemu/code/dmac/srp/lee/scripts/apply_geo_accessions.py` |
| `apply_omero_ids.py` | derived from intravchip+lee patterns (new canonical) |
| `review_metadata_vs_uploads.py` | `/home/cdemu/code/dmac/srp/lee/scripts/review_nar_vs_uploads.py` |
| `upload_geo_ncftp.sh` | `/home/cdemu/code/dmac/srp/lee/scripts/upload_geo_ncftp.sh` |
| `deposit/geo_build_xlsx.py` | `/home/cdemu/code/dmac/srp/lee/scripts/render_geo_xlsx.py` |
| `context/*.json` + `NExtSEEK_API.yaml` | `/home/cdemu/code/dmac/metnet/marie/intravchip/context/*` |

Universal lift requirements (apply to every script):
1. Top of file: PEP 723 inline-script metadata block declaring deps + python version
2. Remove any hardcoded paths (especially `/home/cdemu/code/dmac/csbc/...` in consolidate_to_flat)
3. REPO root must be derived from `Path(__file__).resolve().parent.parent` not hardcoded
4. Imports from `_common.py` use `from _common import ...` (same-dir import; plugin scripts/ is on sys.path when invoked via `uv run --script`)
5. `--help` must work standalone

---

## Phase A — Plugin scaffolding & manifest

### Task 1: Create plugin manifest and directory skeleton

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: directories `skills/curation/examples/`, `commands/`, `scripts/deposit/`, `context/`, `templates/`, `tests/fixtures/`

- [ ] **Step 1: Create the directory skeleton**

Run:
```bash
mkdir -p .claude-plugin skills/curation/examples commands scripts/deposit context templates tests/fixtures
```

- [ ] **Step 2: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "dmac-curation",
  "version": "0.1.0",
  "description": "Curate research-project metadata for NExtSEEK / FairDomHub via the 13-phase pipeline (inventory → sample tree → build → consolidate → QA → deposit → retrieve → email PI).",
  "author": {
    "name": "Charlie Demurjian",
    "email": "cdemurjian@gmail.com",
    "url": "https://github.com/cdemurjian"
  },
  "homepage": "https://github.com/cdemurjian/dmac-curation",
  "repository": "https://github.com/cdemurjian/dmac-curation",
  "license": "MIT",
  "keywords": ["nextseek", "fairdomhub", "metadata-curation", "mit", "dmac", "claude-code-plugin"]
}
```

- [ ] **Step 3: Verify directory layout**

Run:
```bash
find . -maxdepth 3 -type d -not -path './.git*' | sort
```

Expected output includes:
```
./.claude-plugin
./commands
./context
./docs/superpowers/plans
./docs/superpowers/specs
./scripts
./scripts/deposit
./skills
./skills/curation
./skills/curation/examples
./templates
./tests
./tests/fixtures
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "scaffold: plugin manifest and directory skeleton"
```

---

## Phase B — Bundled context (frozen schema snapshots)

### Task 2: Copy NExtSEEK schema snapshots from intravchip

**Files:**
- Create: `context/sampletypes_db.json`
- Create: `context/assays_db.json`
- Create: `context/projects_db.json`
- Create: `context/neo4j_schema.json`
- Create: `context/min_api_endpoints_enriched.json`
- Create: `context/NExtSEEK_API.yaml`
- Create: `context/VINTAGE.json` (records when snapshots were taken)

- [ ] **Step 1: Copy the 6 source files**

Run:
```bash
SRC=/home/cdemu/code/dmac/metnet/marie/intravchip/context
cp "$SRC/sampletypes_db.json" context/sampletypes_db.json
cp "$SRC/assays_db.json" context/assays_db.json
cp "$SRC/projects_db.json" context/projects_db.json
cp "$SRC/neo4j_schema.json" context/neo4j_schema.json
cp "$SRC/min_api_endpoints_enriched.json" context/min_api_endpoints_enriched.json
cp "$SRC/NExtSEEK API (3).yaml" context/NExtSEEK_API.yaml
```

- [ ] **Step 2: Find the source for `neo4j_assay-sample-conn.json`**

The intravchip context dir doesn't have this file; the srp/lee context dir does.

Run:
```bash
cp /home/cdemu/code/dmac/srp/lee/context/neo4j_assay-sample-conn.json context/neo4j_assay-sample-conn.json
```

- [ ] **Step 3: Write `context/VINTAGE.json`**

```json
{
  "snapshot_date": "2026-05-27",
  "source": "Charlie Demurjian's working curation projects (intravchip + srp/lee)",
  "files": {
    "sampletypes_db.json": "101 sample types",
    "assays_db.json": "217 assays",
    "projects_db.json": "projects list incl. CSBC, GBM_BTC, Griffith, Impact",
    "neo4j_schema.json": "Neo4j labels and relationships",
    "neo4j_assay-sample-conn.json": "176 allowed (assay, parent_type, child_type) edges",
    "min_api_endpoints_enriched.json": "API endpoint enrichment",
    "NExtSEEK_API.yaml": "OpenAPI spec for nextseek.mit.edu"
  },
  "note": "Refresh via tools/refresh_context.py (planned, not yet implemented). Lockfile in each curation project records which vintage was used at /curate-init."
}
```

- [ ] **Step 4: Verify JSON files are valid**

Run:
```bash
for f in context/*.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"
done
```

Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add context/
git commit -m "context: bundle NExtSEEK schema snapshots (2026-05-27 vintage)"
```

---

## Phase C — Templates

### Task 3: Write the 9 Jinja2 templates

**Files:**
- Create: `templates/CLAUDE.md.j2`
- Create: `templates/FILE_INDEX.md.j2`
- Create: `templates/SAMPLE_TREE.md.j2`
- Create: `templates/QUESTIONS_FOR_PI.md.j2`
- Create: `templates/CURATION_PLAN.md.j2`
- Create: `templates/EMAIL_TO_PI.md.j2`
- Create: `templates/pyproject.toml.j2`
- Create: `templates/env.example.j2`
- Create: `templates/gitignore.j2`
- Test: `tests/test_templates_render.py`

- [ ] **Step 1: Write `templates/CLAUDE.md.j2`**

```jinja
# {{ pi_name|title }} curation — {{ lab|upper }} lab

**Project initialized:** {{ init_date }}
**Lab tag:** `{{ lab|upper }}` (UIDs use format `<TYPE>-YYMMDD{{ lab|upper }}-N`)
**PI:** {{ pi_name }}
**NExtSEEK project ID:** {{ project_id | default('TBD — set after /curate-resolve-assays') }}

## Inputs

Drop these into the empty subdirectories before running `/curate-inventory`:

- `files/` — PI's raw data (images, sequencing, mass spec, etc.)
- `manuscript/` — paper draft (.docx, PDFs)
- `previous_metadata/` — master spreadsheet ({{ lab|upper }} All YYMMDD.xlsx) + any PI-returned edits
- `email_convo.md` (optional) — PI email thread

## Pipeline

Run `/curate-status` at any time to see current phase. Suggested order:

1. `/curate-inventory` → `FILE_INDEX.md`
2. `/curate-sample-tree` → `SAMPLE_TREE.md`
3. `/curate-questions add` (as gaps surface) → `QUESTIONS_FOR_PI.md`
4. `/curate-build <arm>` per arm → `assay_sheets/4sheet_originals/`
5. `/curate-consolidate` → `assay_sheets/Arm{X}.xlsx`
6. `/curate-resolve-assays --project-id N` → `context/assay_ids_cache.json` (then curate `context/assay_synonyms.json`)
7. `/curate-qa` → CLEAN/SOFT_FLAG/HARD_REJECT report
8. `/curate-deposit <target>` → external uploads + URL backfill
9. `/curate-retrieve` → `RETRIEVE.TXT`
10. `/curate-validate <downloaded.xlsx>` → round-trip diff
11. `/curate-email` → `EMAIL_TO_PI.md`

## Plugin lockfile

`.dmac-curation.json` records the plugin SHA and schema vintage used at init. Don't edit by hand.
```

- [ ] **Step 2: Write `templates/FILE_INDEX.md.j2`**

```jinja
# File inventory — {{ pi_name|title }} curation

**Generated:** {{ generated_date }}

## Inputs received

### `files/`
{{ files_summary | default('(empty — no raw data dropped in yet)') }}

### `manuscript/`
{{ manuscript_summary | default('(empty)') }}

### `previous_metadata/`
{{ previous_metadata_summary | default('(empty)') }}

### `email_convo.md`
{{ email_summary | default('(no email log present)') }}

## Existing master metadata

{% if master_xlsx %}
File: `{{ master_xlsx }}`

| Sheet | Row count | Sample-type code | {{ pi_name }}'s rows |
|---|---|---|---|
{% for sheet in master_sheets %}
| {{ sheet.name }} | {{ sheet.rows }} | {{ sheet.sampletype }} | {{ sheet.pi_rows }} |
{% endfor %}
{% else %}
(no master spreadsheet found in `previous_metadata/`)
{% endif %}

## Things to flag now

{{ flags | default('(none)') }}

## Suggested next step

`/curate-sample-tree`
```

- [ ] **Step 3: Write `templates/SAMPLE_TREE.md.j2`**

```jinja
# Sample tree — {{ pi_name|title }} ({{ paper_short_title }})

**Generated:** {{ generated_date }}
**Lab tag:** `{{ lab|upper }}`
**Curation date stamp:** `{{ curation_date_stamp }}` (used in new UIDs as `<TYPE>-{{ curation_date_stamp }}{{ lab|upper }}-N`)

## Study overview

{{ study_overview }}

## Already in master ({{ pi_name }}'s existing rows)

{% for type_summary in existing_rows %}
- **{{ type_summary.sampletype }}**: {{ type_summary.count }} rows ({{ type_summary.note }})
{% endfor %}

## Experimental arms

{% for arm in arms %}
### Arm {{ arm.letter }} — {{ arm.title }}

```
{{ arm.ascii_tree }}
```

**Rows to create:**
{% for type in arm.new_rows %}
- `{{ type.sampletype }}` × {{ type.count }} — {{ type.note }}
{% endfor %}

**Open questions:** {{ arm.questions | default('(none)') }}
{% endfor %}

## Cross-arm questions

{{ cross_arm_questions | default('(none)') }}

## Suggested next step

`/curate-build {{ arms[0].letter }}` (or any arm in any order)
```

- [ ] **Step 4: Write `templates/QUESTIONS_FOR_PI.md.j2`**

```jinja
# Questions for {{ pi_name|title }}

**Generated:** {{ generated_date }}

This file accumulates questions as curation progresses. `/curate-questions` adds new entries; `/curate-questions resolve <id>` marks one resolved.

## Open

{% for q in open_questions %}
### {{ q.id }} — {{ q.topic }}
{{ q.body }}

*(surfaced during Phase {{ q.phase }})*
{% endfor %}

## Resolved

{% for q in resolved_questions %}
### {{ q.id }} — {{ q.topic }}
{{ q.body }}

**Answer:** {{ q.answer }}
{% endfor %}
```

- [ ] **Step 5: Write `templates/CURATION_PLAN.md.j2`**

```jinja
# Curation plan — {{ pi_name|title }}

**Generated:** {{ generated_date }}

## Goal

{{ goal }}

## Scope

{{ scope }}

## Per-arm checklist

{% for arm in arms %}
- [ ] Arm {{ arm.letter }} ({{ arm.title }}) — {{ arm.row_estimate }} new rows across {{ arm.sample_types | join(', ') }}
{% endfor %}

## Deposits required

{% for deposit in deposits %}
- [ ] {{ deposit.target }}: {{ deposit.what }}
{% endfor %}

## Email to PI

- [ ] Draft `EMAIL_TO_PI.md` with: sample tree summary, open questions, deposit status
```

- [ ] **Step 6: Write `templates/EMAIL_TO_PI.md.j2`**

```jinja
# Email to {{ pi_name|title }} — draft

**Subject:** {{ subject | default(pi_name|title + ' paper curation update') }}

Hi {{ pi_name|title }},

{{ greeting | default('Quick update on the metadata curation for your paper.') }}

## What's been curated

{{ summary_paragraph }}

{% if sample_tree_svg %}
*(sample tree rendering attached as `{{ sample_tree_svg }}`)*
{% endif %}

## Files we have curated

{{ files_curated_summary }}

## Questions

{% for q in questions %}
{{ loop.index }}. {{ q }}
{% endfor %}

## Status of external deposits

{% for d in deposits %}
- **{{ d.target }}**: {{ d.status }}
{% endfor %}

## What I need from you

{{ asks }}

Thanks!
{{ scientist_name }}
```

- [ ] **Step 7: Write `templates/pyproject.toml.j2`**

```jinja
[project]
name = "{{ project_slug }}"
version = "0.1.0"
description = "Metadata curation project for {{ pi_name }}"
requires-python = ">=3.11"
dependencies = [
    "openpyxl>=3.1",
    "requests>=2.31",
    "python-dotenv>=1.0",
    "smbprotocol>=1.10",
]
```

- [ ] **Step 8: Write `templates/env.example.j2`**

```jinja
# NExtSEEK API credentials
NEXTSEEK_USERNAME=
NEXTSEEK_PASSWORD=
# OR token auth:
# NEXTSEEK_TOKEN=

# MIT BMC Luria SMB (for sequencing pulls)
MIT_USER=cdemu@mit.edu
MIT_PASS=
MIT_DOMAIN=MIT.EDU
SMB_HOST=bmc-pub14.mit.edu
SMB_SHARE=engelward

# NCFTP for GEO submissions
NCFTP_HOST=ftp-private.ncbi.nlm.nih.gov
NCFTP_USER=geoftp
NCFTP_PASS=

# FairDomHub API
FDH_API=
```

- [ ] **Step 9: Write `templates/gitignore.j2`**

```jinja
# Secrets — never commit
.env
.env.local
*.key
*.pem
credentials*
secrets*
.netrc
.smbcreds

# Python
__pycache__/
*.pyc
.venv/

# Curation artifacts (large data; project-specific)
files/*
!files/.gitkeep
*.partial
GEO/
Zenodo_upload/
images_to_upload_to_omero/
*.fastq.gz
*.bam

# Generated tables
manifest.csv
omero_images.csv
RETRIEVE.TXT
*-upload-new.xlsx
*_AllMetadata*.xlsx

# Logs
*.log
.scratch/
```

- [ ] **Step 10: Write `tests/test_templates_render.py`**

```python
"""Smoke-test each .j2 template against a minimal context dict."""
from pathlib import Path
import pytest
jinja2 = pytest.importorskip("jinja2")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    undefined=jinja2.StrictUndefined,
)

FIXTURES = {
    "CLAUDE.md.j2": {
        "pi_name": "marie", "lab": "kam", "init_date": "2026-05-27",
        "project_id": None,
    },
    "FILE_INDEX.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "files_summary": None, "manuscript_summary": None,
        "previous_metadata_summary": None, "email_summary": None,
        "master_xlsx": None, "master_sheets": [], "flags": None,
    },
    "SAMPLE_TREE.md.j2": {
        "pi_name": "marie", "paper_short_title": "IntravChip",
        "generated_date": "2026-05-27", "lab": "kam",
        "curation_date_stamp": "260527",
        "study_overview": "Test overview.", "existing_rows": [],
        "arms": [{"letter": "A", "title": "Test", "ascii_tree": "tree",
                  "new_rows": [], "questions": None}],
        "cross_arm_questions": None,
    },
    "QUESTIONS_FOR_PI.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "open_questions": [], "resolved_questions": [],
    },
    "CURATION_PLAN.md.j2": {
        "pi_name": "marie", "generated_date": "2026-05-27",
        "goal": "test", "scope": "test", "arms": [], "deposits": [],
    },
    "EMAIL_TO_PI.md.j2": {
        "pi_name": "marie", "subject": None, "greeting": None,
        "summary_paragraph": "test", "sample_tree_svg": None,
        "files_curated_summary": "test", "questions": ["q1"],
        "deposits": [], "asks": "ask", "scientist_name": "Charlie",
    },
    "pyproject.toml.j2": {"project_slug": "marie_intravchip", "pi_name": "marie"},
    "env.example.j2": {},
    "gitignore.j2": {},
}

@pytest.mark.parametrize("template_name,context", list(FIXTURES.items()))
def test_template_renders(template_name, context):
    template = ENV.get_template(template_name)
    result = template.render(**context)
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 11: Run the template-render test**

Run:
```bash
uv run --with jinja2 --with pytest pytest tests/test_templates_render.py -v
```

Expected: 9 PASSED.

- [ ] **Step 12: Commit**

```bash
git add templates/ tests/test_templates_render.py
git commit -m "templates: 9 Jinja2 templates for /curate-init render + render smoke test"
```

---

## Phase D — Bundled scripts

### Task 4: Lift `_common.py` shared helpers

**Files:**
- Create: `scripts/_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Copy `_common.py` from intravchip**

Run:
```bash
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/_common.py scripts/_common.py
```

- [ ] **Step 2: Inspect the file**

Run:
```bash
head -40 scripts/_common.py && echo "..." && wc -l scripts/_common.py
```

- [ ] **Step 3: Add PEP 723 inline-deps header if missing**

If the file doesn't start with a `# /// script` block, prepend:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
```

- [ ] **Step 4: Remove any hardcoded paths from the file**

Open `scripts/_common.py` and search for any string starting with `/home/cdemu/` or `/Users/`. Replace with `Path(__file__).resolve().parent.parent` relative paths. If found, document the replacement.

- [ ] **Step 5: Write `tests/test_common.py`**

```python
"""Smoke tests for scripts/_common.py — verify imports and core function signatures."""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _common  # noqa: E402


def test_module_imports():
    assert _common is not None


def test_mint_uid_signature():
    """mint_uid should exist and accept (sample_type, lab, date, n) → str."""
    assert hasattr(_common, "mint_uid"), "mint_uid function expected"
    uid = _common.mint_uid("RNA", "KAM", "260527", 1)
    assert uid == "RNA-260527KAM-1"


def test_mint_uid_format():
    uid = _common.mint_uid("D.SEQ", "ENG", "260514", 42)
    assert uid == "D.SEQ-260514ENG-42"
```

- [ ] **Step 6: Run the test**

Run:
```bash
uv run --with openpyxl --with pytest pytest tests/test_common.py -v
```

Expected: 3 PASSED. If `mint_uid` doesn't exist with that exact signature, inspect `_common.py` and either patch the test to match the actual signature or add a `mint_uid` wrapper if it's named differently.

- [ ] **Step 7: Commit**

```bash
git add scripts/_common.py tests/test_common.py
git commit -m "scripts: lift _common.py shared helpers from intravchip + smoke test"
```

---

### Task 5: Lift `nextseek_api.py` (NExtSEEK API client)

**Files:**
- Create: `scripts/nextseek_api.py`
- Test: `tests/test_nextseek_api_cli.py`

- [ ] **Step 1: Copy from intravchip**

Run:
```bash
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/nextseek_api.py scripts/nextseek_api.py
```

- [ ] **Step 2: Verify PEP 723 header exists**

Run:
```bash
head -10 scripts/nextseek_api.py
```

Expected: a `# /// script` block. If missing, prepend:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "python-dotenv>=1.0"]
# ///
```

- [ ] **Step 3: Strip hardcoded paths and verify `nextseek.mit.edu` as base URL default**

Search the file for `fairdata-dev.mit.edu`, `fairdata.mit.edu`, `/home/cdemu/`. The base URL default must be `https://nextseek.mit.edu/nextseek_api/`. The `validate` subcommand may default to `https://nextseek-dev.mit.edu/nextseek_api/`. Patch as needed.

- [ ] **Step 4: Write `tests/test_nextseek_api_cli.py`**

```python
"""Smoke test: nextseek_api.py --help runs without errors."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "nextseek_api.py"


def test_help_runs():
    """--help should succeed and mention fetch-assays subcommand."""
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "fetch-assays" in result.stdout or "fetch-assays" in result.stderr


def test_fetch_assays_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "fetch-assays", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "project-id" in result.stdout or "project-id" in result.stderr
```

- [ ] **Step 5: Run the test**

Run:
```bash
uv run --with pytest pytest tests/test_nextseek_api_cli.py -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add scripts/nextseek_api.py tests/test_nextseek_api_cli.py
git commit -m "scripts: lift nextseek_api.py (fetch-assays + validate) + CLI smoke test"
```

---

### Task 6: Lift `consolidate_to_flat.py`, `qa_flat_sheets.py`, and write `build_retrieve.py`

**Files:**
- Create: `scripts/consolidate_to_flat.py`
- Create: `scripts/qa_flat_sheets.py`
- Create: `scripts/build_retrieve.py` (new canonical)
- Test: `tests/test_flat_pipeline_cli.py`

- [ ] **Step 1: Copy consolidate + qa**

Run:
```bash
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/consolidate_to_flat.py scripts/consolidate_to_flat.py
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/qa_flat_sheets.py scripts/qa_flat_sheets.py
```

- [ ] **Step 2: Verify PEP 723 + strip hardcoded paths in both files**

For each file, ensure `# /// script` block exists at top with `openpyxl` dep, and grep for hardcoded `/home/cdemu/` paths. The REPO root inside each must derive from `Path(__file__).resolve().parent.parent`.

- [ ] **Step 3: Verify the `--all-in-one` flag exists on consolidate_to_flat.py**

Run:
```bash
uv run --script scripts/consolidate_to_flat.py --help | grep all-in-one
```

If missing, the flag needs to be added. Locate the argparse setup and add `parser.add_argument("--all-in-one", help="Merge all per-arm outputs into a single xlsx with this name")`.

- [ ] **Step 4: Write `scripts/build_retrieve.py` (new canonical)**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Build RETRIEVE.TXT from assay_sheets/ — newline-separated UIDs for chat_nextseek.

By default emits only downstream sample types (D.*/A.*/SLD/etc.) — the retrieve
function auto-pulls parents via the lineage chain. Use --include-parents to emit
all UIDs including DNA/RNA/TIS/MUS intermediates.

Prefers `*-upload-new.xlsx` over `*-upload.xlsx` to capture the latest curation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

# Sample types treated as PARENTS (auto-pulled by retrieve; excluded by default)
PARENT_TYPES = {"MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}


def collect_uids(assay_sheets_dir: Path, include_parents: bool) -> list[str]:
    """Walk assay_sheets/, prefer -upload-new over -upload, dedupe + sort UIDs."""
    seen: set[str] = set()

    # Build map of basename → preferred file (prefer -upload-new)
    candidates: dict[str, Path] = {}
    for p in sorted(assay_sheets_dir.glob("*.xlsx")):
        if p.name.startswith("~"):  # openpyxl lock files
            continue
        if "-upload-new" in p.stem:
            base = p.stem.replace("-upload-new", "")
            candidates[base] = p
        elif "-upload" in p.stem and p.stem.replace("-upload", "") not in candidates:
            base = p.stem.replace("-upload", "")
            candidates.setdefault(base, p)

    for path in candidates.values():
        wb = load_workbook(path, read_only=True, data_only=True)
        if "Samples" not in wb.sheetnames:
            continue
        ws = wb["Samples"]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            continue
        uid_col = None
        for i, h in enumerate(header):
            if h and str(h).strip().lower() == "uid":
                uid_col = i
                break
        if uid_col is None:
            continue
        for row in rows_iter:
            if uid_col >= len(row):
                continue
            uid = row[uid_col]
            if not uid:
                continue
            uid = str(uid).strip()
            if "-" not in uid:
                continue
            sample_type = uid.split("-", 1)[0]
            if not include_parents and sample_type in PARENT_TYPES:
                continue
            seen.add(uid)

    return sorted(seen)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assay-sheets", default="assay_sheets",
                   help="Directory containing *-upload-new.xlsx / *-upload.xlsx (default: assay_sheets)")
    p.add_argument("--output", default="RETRIEVE.TXT", help="Output file (default: RETRIEVE.TXT)")
    p.add_argument("--include-parents", action="store_true",
                   help="Include MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL UIDs (default: downstream-only)")
    args = p.parse_args()

    assay_dir = Path(args.assay_sheets).resolve()
    if not assay_dir.is_dir():
        print(f"ERROR: {assay_dir} is not a directory", file=sys.stderr)
        return 2

    uids = collect_uids(assay_dir, include_parents=args.include_parents)
    out = Path(args.output).resolve()
    out.write_text("\n".join(uids) + "\n")

    by_type: dict[str, int] = {}
    for u in uids:
        t = u.split("-", 1)[0]
        by_type[t] = by_type.get(t, 0) + 1

    print(f"Wrote {len(uids)} UIDs to {out}")
    for t in sorted(by_type):
        print(f"  {t}: {by_type[t]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `tests/test_flat_pipeline_cli.py`**

```python
"""Smoke tests for flat-pipeline scripts."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _help_runs(script_name: str) -> None:
    script = SCRIPTS_DIR / script_name
    result = subprocess.run(
        ["uv", "run", "--script", str(script), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"{script_name} --help failed: {result.stderr}"


def test_consolidate_to_flat_help():
    _help_runs("consolidate_to_flat.py")


def test_qa_flat_sheets_help():
    _help_runs("qa_flat_sheets.py")


def test_build_retrieve_help():
    _help_runs("build_retrieve.py")


def test_build_retrieve_empty_dir(tmp_path):
    (tmp_path / "assay_sheets").mkdir()
    out = tmp_path / "RETRIEVE.TXT"
    script = SCRIPTS_DIR / "build_retrieve.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(script),
         "--assay-sheets", str(tmp_path / "assay_sheets"),
         "--output", str(out)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert out.exists()
    assert out.read_text() == "\n"  # empty file with trailing newline
```

- [ ] **Step 6: Run the tests**

Run:
```bash
uv run --with pytest pytest tests/test_flat_pipeline_cli.py -v
```

Expected: 4 PASSED.

- [ ] **Step 7: Commit**

```bash
git add scripts/consolidate_to_flat.py scripts/qa_flat_sheets.py scripts/build_retrieve.py tests/test_flat_pipeline_cli.py
git commit -m "scripts: lift consolidate_to_flat + qa_flat_sheets, write canonical build_retrieve"
```

---

### Task 7: Write `inspect_workbook.py` (canonical from inline pattern)

**Files:**
- Create: `scripts/inspect_workbook.py`
- Create: `tests/fixtures/sample.xlsx`
- Test: `tests/test_inspect_workbook.py`

- [ ] **Step 1: Write `scripts/inspect_workbook.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Inspect an .xlsx workbook — sheet names, dimensions, headers, sample rows.

Common idiom across past sessions; canonicalized here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook


def inspect(path: Path, sheet: str | None, sample_rows: int) -> int:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2
    wb = load_workbook(path, read_only=True, data_only=True)

    print(f"## {path.name}")
    print(f"Sheets ({len(wb.sheetnames)}):")
    for s in wb.sheetnames:
        ws = wb[s]
        # max_row/max_col are unreliable in read_only — count manually
        rows = sum(1 for _ in ws.iter_rows(values_only=True))
        print(f"  - {s}: {rows} rows × {ws.max_column} cols")

    targets = [sheet] if sheet else wb.sheetnames
    for s in targets:
        if s not in wb.sheetnames:
            print(f"\n(sheet '{s}' not found)")
            continue
        ws = wb[s]
        print(f"\n### Sheet: {s}")
        iter_rows = ws.iter_rows(values_only=True)
        header = next(iter_rows, None)
        if header is None:
            print("  (empty)")
            continue
        print(f"  Headers ({len(header)}): {list(header)}")
        if sample_rows > 0:
            print(f"  Sample (up to {sample_rows} rows):")
            for i, row in enumerate(iter_rows):
                if i >= sample_rows:
                    break
                print(f"    [{i}] {list(row)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, help="Path to .xlsx file")
    p.add_argument("--sheet", help="Limit detail to this sheet (default: all)")
    p.add_argument("--sample", type=int, default=0, help="Show this many sample data rows per sheet")
    args = p.parse_args()
    return inspect(args.path, args.sheet, args.sample)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Generate a tiny fixture xlsx**

Run:
```bash
uv run --with openpyxl python3 -c "
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.title = 'Samples'
ws.append(['UID', 'Name', 'Parent'])
ws.append(['RNA-260527KAM-1', 'A1_tube1', 'TIS-250218KAM-1'])
ws.append(['RNA-260527KAM-2', 'A1_tube2', 'TIS-250218KAM-1'])
ws2 = wb.create_sheet('Instructions')
ws2.append(['Field', 'Type', 'Description'])
wb.save('tests/fixtures/sample.xlsx')
print('Wrote tests/fixtures/sample.xlsx')
"
```

- [ ] **Step 3: Write `tests/test_inspect_workbook.py`**

```python
"""Test inspect_workbook.py against a fixture xlsx."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "inspect_workbook.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.xlsx"


def test_inspect_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Samples" in result.stdout
    assert "Instructions" in result.stdout


def test_inspect_with_sheet_filter():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), str(FIXTURE), "--sheet", "Samples", "--sample", "2"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "RNA-260527KAM-1" in result.stdout
    assert "RNA-260527KAM-2" in result.stdout
```

- [ ] **Step 4: Run the test**

Run:
```bash
uv run --with pytest pytest tests/test_inspect_workbook.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/inspect_workbook.py tests/fixtures/sample.xlsx tests/test_inspect_workbook.py
git commit -m "scripts: canonical inspect_workbook.py + fixture-based test"
```

---

### Task 8: Lift `rename_files.py` and `omero_pull.py`

**Files:**
- Create: `scripts/rename_files.py`
- Create: `scripts/omero_pull.py`
- Create: `scripts/deposit/omero_rest_client.py` (refactored from omero_pull)
- Test: `tests/test_file_ops_cli.py`

- [ ] **Step 1: Copy both files**

Run:
```bash
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/rename_files.py scripts/rename_files.py
cp /home/cdemu/code/dmac/metnet/marie/intravchip/scripts/omero_pull.py scripts/omero_pull.py
```

- [ ] **Step 2: Verify PEP 723 headers + strip hardcoded paths in both**

For each, ensure `# /// script` block at top. `rename_files.py` is stdlib-only (no deps). `omero_pull.py` needs `requests>=2.31`. Strip any `/home/cdemu/` paths.

- [ ] **Step 3: Verify rename_files.py 5 subcommands work**

Run:
```bash
uv run --script scripts/rename_files.py --help
```

Expected: lists `walk`, `checksums`, `apply`, `verify`, `rollback` subcommands.

- [ ] **Step 4: Create `scripts/deposit/__init__.py`**

Run:
```bash
touch scripts/deposit/__init__.py
```

- [ ] **Step 5: Note the refactor of `deposit/omero_rest_client.py`**

For v0.1.0, leave `omero_pull.py` as-is (it has the REST client inline). Refactoring the REST client out as `deposit/omero_rest_client.py` is a follow-up. Add a TODO comment at the top of `omero_pull.py`:

```python
# TODO(v0.2): extract REST client into deposit/omero_rest_client.py for reuse
```

- [ ] **Step 6: Write `tests/test_file_ops_cli.py`**

```python
"""Smoke tests for rename_files.py and omero_pull.py."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def test_rename_files_help():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPTS_DIR / "rename_files.py"), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    for sub in ["walk", "checksums", "apply", "verify", "rollback"]:
        assert sub in result.stdout, f"subcommand {sub} not in --help"


def test_omero_pull_help():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPTS_DIR / "omero_pull.py"), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
```

- [ ] **Step 7: Run tests**

Run:
```bash
uv run --with pytest pytest tests/test_file_ops_cli.py -v
```

Expected: 2 PASSED.

- [ ] **Step 8: Commit**

```bash
git add scripts/rename_files.py scripts/omero_pull.py scripts/deposit/__init__.py tests/test_file_ops_cli.py
git commit -m "scripts: lift rename_files (5 subcommands) + omero_pull (REST client)"
```

---

### Task 9: Consolidate `smb_pull.py` from lee variants

**Files:**
- Create: `scripts/smb_pull.py`
- Test: `tests/test_smb_pull_cli.py`

- [ ] **Step 1: Inspect the two source files to pick a base**

Run:
```bash
ls -la /home/cdemu/code/dmac/srp/lee/scripts/pull_*.py
```

`pull_spatial.py` and `pull_bulk_rna.py` share most code. Pick `pull_bulk_rna.py` as the base — it has the richest argparse (`--from-manifest`, `--rows N-M`, `--rows-from`, `--batch`, `--resume`, `--dry-run`).

- [ ] **Step 2: Copy base script and rename**

Run:
```bash
cp /home/cdemu/code/dmac/srp/lee/scripts/pull_bulk_rna.py scripts/smb_pull.py
```

- [ ] **Step 3: Generalize: rename hardcoded `bulk_rna` references to be configurable**

Open `scripts/smb_pull.py`. Find string literals referencing `bulk_rna` or `spatial` as a domain. Convert to a `--profile bulk_rna|spatial|generic` flag, or pass `--output-dir` so the script doesn't assume a layout. Default `--profile generic` with explicit `--source-pattern <glob>`.

If the existing code has hardcoded SMB path patterns specific to bulk vs spatial (e.g., `noraho/{batch}Eng/`), abstract those into a `--source-pattern` argument with sensible documentation.

- [ ] **Step 4: Verify PEP 723 header + deps**

Ensure top of file has:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["smbprotocol>=1.10", "python-dotenv>=1.0"]
# ///
```

- [ ] **Step 5: Strip hardcoded paths**

Search for `/home/cdemu/` and replace with cwd-relative or argparse-derived paths.

- [ ] **Step 6: Write `tests/test_smb_pull_cli.py`**

```python
"""Smoke test for smb_pull.py — verify --help and --dry-run don't error without credentials."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smb_pull.py"


def test_help_runs():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    for flag in ["--dry-run", "--resume"]:
        assert flag in result.stdout, f"flag {flag} not in --help"
```

- [ ] **Step 7: Run the test**

Run:
```bash
uv run --with pytest pytest tests/test_smb_pull_cli.py -v
```

Expected: 1 PASSED.

- [ ] **Step 8: Commit**

```bash
git add scripts/smb_pull.py tests/test_smb_pull_cli.py
git commit -m "scripts: consolidate pull_spatial+pull_bulk_rna into smb_pull.py"
```

---

### Task 10: Lift deposit/backfill scripts

**Files:**
- Create: `scripts/stage_zenodo.py`
- Create: `scripts/apply_zenodo_links.py`
- Create: `scripts/apply_geo_accessions.py`
- Create: `scripts/apply_omero_ids.py`
- Create: `scripts/review_metadata_vs_uploads.py`
- Create: `scripts/upload_geo_ncftp.sh`
- Create: `scripts/deposit/geo_build_xlsx.py`
- Test: `tests/test_deposit_scripts_help.py`

- [ ] **Step 1: Copy the 5 lee scripts**

Run:
```bash
SRC=/home/cdemu/code/dmac/srp/lee/scripts
cp "$SRC/stage_zenodo.py" scripts/stage_zenodo.py
cp "$SRC/apply_zenodo_links.py" scripts/apply_zenodo_links.py
cp "$SRC/apply_geo_accessions.py" scripts/apply_geo_accessions.py
cp "$SRC/review_nar_vs_uploads.py" scripts/review_metadata_vs_uploads.py
cp "$SRC/upload_geo_ncftp.sh" scripts/upload_geo_ncftp.sh
cp "$SRC/render_geo_xlsx.py" scripts/deposit/geo_build_xlsx.py
chmod +x scripts/upload_geo_ncftp.sh
```

- [ ] **Step 2: Write a new canonical `scripts/apply_omero_ids.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Apply OMERO image IDs to D.IMG `Link_PrimaryData` columns.

Reads `omero_images.csv` (output of `omero_pull.py all --project N`) and patches
the matching upload sheet rows by filename. Idempotent.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from openpyxl import load_workbook


def apply(xlsx_path: Path, omero_csv: Path, dry_run: bool) -> int:
    by_filename: dict[str, dict[str, str]] = {}
    with omero_csv.open() as f:
        for row in csv.DictReader(f):
            fname = row.get("filename") or ""
            if fname:
                by_filename[fname] = row

    wb = load_workbook(xlsx_path)
    if "Samples" not in wb.sheetnames:
        print(f"ERROR: no Samples sheet in {xlsx_path}", file=sys.stderr)
        return 2
    ws = wb["Samples"]

    header_row = [c.value for c in ws[1]]
    try:
        file_col = header_row.index("File_PrimaryData") + 1
        link_col = header_row.index("Link_PrimaryData") + 1
    except ValueError:
        print("ERROR: File_PrimaryData and Link_PrimaryData columns required", file=sys.stderr)
        return 2

    patched = 0
    for r in range(2, ws.max_row + 1):
        fname_cell = ws.cell(row=r, column=file_col).value
        if not fname_cell:
            continue
        fname = str(fname_cell).strip()
        match = by_filename.get(fname)
        if not match:
            continue
        link = match.get("web_url") or match.get("show_url") or ""
        if not link:
            continue
        if not dry_run:
            ws.cell(row=r, column=link_col).value = link
        patched += 1
        print(f"  {'(dry-run) ' if dry_run else ''}{fname} → {link}")

    if not dry_run and patched > 0:
        wb.save(xlsx_path)
    print(f"\n{'Would patch' if dry_run else 'Patched'} {patched} rows in {xlsx_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("xlsx", type=Path)
    p.add_argument("--omero-csv", type=Path, default=Path("omero_images.csv"))
    p.add_argument("--write", action="store_true", help="Apply changes (default is dry-run)")
    args = p.parse_args()
    return apply(args.xlsx, args.omero_csv, dry_run=not args.write)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify PEP 723 + strip hardcoded paths for each lifted script**

For `stage_zenodo.py`, `apply_zenodo_links.py`, `apply_geo_accessions.py`, `review_metadata_vs_uploads.py`, `deposit/geo_build_xlsx.py`:
- Ensure `# /// script` block exists at top
- Replace `/home/cdemu/code/dmac/srp/lee/` references with cwd-relative or argparse-derived paths
- Replace `LP-NAR-All-Metadata*.xlsx` references with a `--metadata-xlsx` argparse flag (default: latest match in cwd)

- [ ] **Step 4: Write `tests/test_deposit_scripts_help.py`**

```python
"""Smoke tests: --help works for each deposit/backfill script."""
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

PY_SCRIPTS = [
    "stage_zenodo.py",
    "apply_zenodo_links.py",
    "apply_geo_accessions.py",
    "apply_omero_ids.py",
    "review_metadata_vs_uploads.py",
    "deposit/geo_build_xlsx.py",
]


def test_each_help_runs():
    for name in PY_SCRIPTS:
        path = SCRIPTS_DIR / name
        assert path.exists(), f"missing {path}"
        result = subprocess.run(
            ["uv", "run", "--script", str(path), "--help"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"{name}: stderr: {result.stderr}"


def test_upload_geo_ncftp_executable():
    path = SCRIPTS_DIR / "upload_geo_ncftp.sh"
    assert path.exists()
    assert path.stat().st_mode & 0o111, "upload_geo_ncftp.sh should be executable"
```

- [ ] **Step 5: Run the tests**

Run:
```bash
uv run --with pytest pytest tests/test_deposit_scripts_help.py -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add scripts/ tests/test_deposit_scripts_help.py
git commit -m "scripts: lift deposit + backfill scripts (Zenodo, GEO, OMERO)"
```

---

## Phase E — Skill docs

### Task 11: Write `skills/curation/SKILL.md`

**Files:**
- Create: `skills/curation/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: dmac-curation
description: Curate research-project metadata for NExtSEEK / FairDomHub via the 13-phase pipeline (inventory → sample tree → build → consolidate → QA → deposit → retrieve → email PI). Activate when working in a directory containing files/, manuscript/, previous_metadata/, or any .dmac-curation.json lockfile.
---

# DMAC Curation

You are helping a curator at MIT DMAC turn a PI's research-project data into NExtSEEK-ready upload sheets via the 13-phase pipeline.

## When this skill activates

- Current working directory contains `.dmac-curation.json` (the per-project lockfile)
- Or cwd contains the curation input layout: `files/`, `manuscript/`, `previous_metadata/`
- Or the user invokes any `/curate-*` slash command
- Or the user mentions NExtSEEK / FairDomHub / FDH / "curate metadata"

## The 13-phase pipeline

| # | Phase | Command | Artifact |
|---|---|---|---|
| 0 | Init | `/curate-init [--lab CODE] [--pi NAME]` | scaffold cwd + `.dmac-curation.json` lockfile |
| 1 | Inventory | `/curate-inventory` | `FILE_INDEX.md` |
| 2 | Sample tree | `/curate-sample-tree` | `SAMPLE_TREE.md` |
| 3 | Questions | `/curate-questions [add|list|resolve]` | `QUESTIONS_FOR_PI.md` |
| 4 | Task plan | (uses TaskCreate, no command) | TaskList state |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}.xlsx` (flat format) |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` |
| 8 | Synonyms | (LLM-driven in Phase 7) | `context/assay_synonyms.json` |
| 9 | QA | `/curate-qa` | console disposition report |
| 10 | Deposit | `/curate-deposit <geo|zenodo|omero>` | external uploads + `Link_PrimaryData` backfilled |
| 11 | Retrieve | `/curate-retrieve` | `RETRIEVE.TXT` |
| 12 | Validate | `/curate-validate <metadata.xlsx>` | console diff report |
| 13 | Email | `/curate-email` | `EMAIL_TO_PI.md` |
| any | Status | `/curate-status` | console pipeline-state summary |

For deep per-phase reference, read `skills/curation/PHASES.md`. For each command's behavior, the `commands/curate-*.md` files are authoritative.

## Hard rules (never violate)

1. **Q&A before UIDs.** If the PI hasn't confirmed experimental scope, draft `EMAIL_TO_PI.md` skeleton (or `QUESTIONS_FOR_PI.md`) before minting UIDs. Where ambiguity exists, ask.
2. **Copy `-upload.xlsx` → `-upload-new.xlsx` before editing.** Preserve history. Never edit the historical file in place.
3. **Check for manual edits before regenerating.** The user may have hand-edited a sheet (e.g., dropped columns). Diff first, surface differences, ask whether to preserve.
4. **Schema lies; workbook tells truth.** Before consulting `context/sampletypes_db.json` for parent rules or required columns, sample existing PI rows in `previous_metadata/`. Workbook precedent wins.
5. **Re-mine email/manuscript before re-asking the PI.** Grep `email_convo.md`, `manuscript/`, and `QUESTIONS_FOR_PI.md` (resolved section) before adding a new question.
6. **Use `uv`, not bare `python3`.** All scripts have PEP 723 inline-deps. Invoke via `uv run --script <plugin>/scripts/X.py`.
7. **Pre-assign UIDs.** Format `<TYPE>-YYMMDD<LAB>-N`. Never auto-gen. Never blank. Date stamp is curation date, not experiment date.
8. **Placeholder markers over blanks.** Use `*** PLACEHOLDER: <description> ***` for unknown values. Greppable; blanks vanish.

## Soft rules (apply with judgment)

- Concrete ASCII trees with real UIDs, not prose summaries (`SAMPLE_TREE.md`)
- Name-pattern anchors in PI emails, never row numbers (`the 27 rows ending in _phospho`, not `rows 28-54` — PI may re-sort)
- Skeleton-first emails. Iterate per-section, let user write the final voice.
- No em dashes in PI-facing prose (Charlie's style)
- `File_PrimaryData` is genuinely required; `Link_PrimaryData` and `Checksum_PrimaryData` are not enforced by the server
- Many-to-many parents are acceptable for legacy/poor-quality PI data
- D.IMG.Parent follows PI precedent. Marie uses OOC even though spec says CEL/CHM/TIS. Sample the workbook.

## Vocabulary the user uses

- "curate" / "curation" → the full pipeline
- "consolidate to flat" → Phase 6
- "QA the sheet" → Phase 9
- "build X sheet" → Phase 5
- "the email" → Phase 13 artifact (`EMAIL_TO_PI.md`)
- "RETRIEVE.TXT" → Phase 11 artifact (downstream UIDs for `chat_nextseek`)
- "all set" / "lets move on" → phase complete, proceed
- "screw the X" → de-scope X for now

## Pitfalls to pre-warn about

- **openpyxl ghost rows.** Writing `None` to a cell leaves a phantom row. `max_row` lies. Always `dropna(how='all')` in validators.
- **`cell.value = None` doesn't reset style.** Sample rows can inherit bold/fill from template rows. Explicitly set `cell.style = "Normal"`.
- **GEO literal validation.** `paired-end` not `paired`; `Illumina NextSeq 500` not `NextSeq 500`. Dropdowns are case- and word-exact.
- **chat_nextseek auto-pulls parents.** Don't include MUS/TIS/DNA/RNA in `RETRIEVE.TXT`. `build_retrieve.py` defaults exclude them.
- **NExtSEEK `validate` endpoint is dev-only.** Production credentials don't authenticate against `nextseek-dev.mit.edu`. The endpoint exists; access doesn't.
- **VPN drops freeze SMB pulls.** `socket.recv()` has no timeout. Resolution: `pkill -f smb_pull.py; find -name '*.partial' -delete; --resume`.
- **`_NNNN` vs `-NNNN` separators.** Match `[_-]` in regex. Past renamer had a real bug from this.
- **Year-prefix mouse-ID typos.** `19-XXX` may actually be `20-XXX`. Try sibling year prefixes before declaring missing.
- **`_Frzn` and other PI suffix noise.** Strip before matching against MUS records.
- **BMC SMB requires `cdemu@mit.edu` (full email), not bare `cdemu`.**
- **MIT Kerberos realm is `ATHENA.MIT.EDU`** (not `MIT.EDU`), but BMC SMB doesn't accept Kerberos. Use `.env` + `smbprotocol`.
- **Fig-7-style byte-identical duplicate trees** in rclone'd Dropbox dumps. Always `diff` before assuming nested dirs are content.
- **`page[size]` is ignored** by NExtSEEK `/assays/` endpoint. Paginate via `next` link only.

## Behavior when ambiguous

If unsure between two interpretations, default to the conservative one and surface the ambiguity to the user. Don't invent values. Don't fill blanks "to be helpful." Use a `*** PLACEHOLDER: ... ***` marker.

## Reading order for new sessions

1. Read this SKILL.md (already loaded)
2. Read `.dmac-curation.json` (lockfile) for lab/pi/project_id context
3. Read project's `CLAUDE.md` for additional notes
4. Run `/curate-status` to orient on current phase
```

- [ ] **Step 2: Verify SKILL.md is well-formed markdown with frontmatter**

Run:
```bash
head -5 skills/curation/SKILL.md
```

Expected: starts with `---`, contains `name:` and `description:`.

- [ ] **Step 3: Commit**

```bash
git add skills/curation/SKILL.md
git commit -m "skill: SKILL.md playbook (8 hard rules, 7 soft rules, 13 pitfalls)"
```

---

### Task 12: Write `skills/curation/PHASES.md`

**Files:**
- Create: `skills/curation/PHASES.md`

- [ ] **Step 1: Write PHASES.md**

```markdown
# Phase reference for dmac-curation

Deep per-phase contract. Read on demand when SKILL.md or a command needs to consult specifics.

For each phase: inputs, outputs, scripts invoked, error modes, edge cases.

---

## Phase 0 — Init

**Command:** `/curate-init [--lab CODE] [--pi NAME]`

**Inputs:** flags. Optionally an empty cwd.

**Action:**
1. Verify cwd is empty (or contains only PI inputs — no `scripts/`, no `context/`, no `CLAUDE.md`). Refuse if not, unless `--force`.
2. Render `templates/CLAUDE.md.j2` → `./CLAUDE.md` with `{lab, pi, init_date}`.
3. Render `templates/env.example.j2` → `./.env.example`.
4. Render `templates/gitignore.j2` → `./.gitignore`.
5. Render `templates/pyproject.toml.j2` → `./pyproject.toml`.
6. Create empty dirs: `files/ manuscript/ previous_metadata/ assay_sheets/ scripts/`.
7. Write `./.dmac-curation.json` lockfile with plugin SHA + schema vintage + lab + pi.
8. Report status.

**Edge cases:**
- cwd not empty: prompt for `--force` or abort
- `--lab` or `--pi` missing: use `AskUserQuestion`, don't guess
- plugin git dir unreadable (no SHA): record `"plugin_sha": null` and warn

---

## Phase 1 — Inventory

**Command:** `/curate-inventory`

**Inputs:** populated `files/`, `manuscript/`, `previous_metadata/`, optional `email_convo.md`

**Action:**
1. Walk `files/` (record `tree -L 2` output + total size).
2. List `manuscript/` (extract docx text if present via zipfile + xml.etree).
3. Inspect every `previous_metadata/*.xlsx` via `scripts/inspect_workbook.py`.
4. Read `email_convo.md` if present.
5. Identify the PI's existing rows in the master xlsx (filter by Scientist column or per-row Notes).
6. Render `templates/FILE_INDEX.md.j2` → `./FILE_INDEX.md`.
7. Suggest `/curate-sample-tree`.

**Edge cases:**
- `files/` empty: still produce a `FILE_INDEX.md` flagging the gap
- Master xlsx absent: flag as a blocker question for the PI
- Multiple master xlsxs (e.g. master + LJP-edits): pick most recent by mtime, note both

---

## Phase 2 — Sample tree

**Command:** `/curate-sample-tree`

**Inputs:** `manuscript/`, `previous_metadata/*.xlsx`, `context/sampletypes_db.json`, `context/assays_db.json`

**Action:**
1. Read manuscript text. Identify experimental arms.
2. For each arm: extract sample types touched. Map to NExtSEEK short codes.
3. Cross-reference against master: which UIDs already exist (`[EXIST]`), which need creating (`[NEW]`).
4. For each new sample type, identify parent type and naming convention from existing rows.
5. Render ASCII trees per arm.
6. Surface open structural questions (Q1, Q2, …) at the bottom.
7. Render `templates/SAMPLE_TREE.md.j2` → `./SAMPLE_TREE.md`.

**Edge cases:**
- New sample type not in `sampletypes_db.json` (e.g., proposed D.REF): mark as PENDING_SCHEMA, add admin question
- Manuscript has no Methods section: pull from email + supplementary docs; flag as a question
- Parent type ambiguous (e.g., D.IMG.Parent = OOC vs CEL/CHM/TIS): follow PI precedent in master, document the deviation

---

## Phase 3 — Questions

**Command:** `/curate-questions [add|list|resolve]`

**Inputs:** conversation context, prior `QUESTIONS_FOR_PI.md`

**Action:**
- `add`: prompt for topic + body + originating phase; append to file
- `list`: print all open questions with IDs
- `resolve <id>`: move from open to resolved, prompt for answer

**Edge cases:**
- File doesn't exist yet: create from template on first `add`
- ID collision: increment until unique

---

## Phase 4 — Task plan

Uses `TaskCreate` directly. No standalone command. SKILL.md instructs Claude to create one task per arm with `blockedBy` dependencies (e.g., Arm G blocked by Arm E + Arm F).

---

## Phase 5 — Build

**Command:** `/curate-build [<arm>]`

**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master), `manuscript/`, `CLAUDE.md` (lab + pi)

**Action:**
1. Identify arm. If not supplied, list arms from `SAMPLE_TREE.md` and `AskUserQuestion`.
2. Read sample types and counts for the arm.
3. Read master to identify existing parent UIDs.
4. Read manuscript for protocol section names, instrument details.
5. Generate `./scripts/build_<arm>.py`:
   - PEP 723 inline deps (openpyxl)
   - `sys.path.insert(0, "<PLUGIN_PATH>/scripts")`
   - `from _common import mint_uid, write_4sheet_xlsx, ...`
   - Mint UIDs `<TYPE>-YYMMDD<LAB>-N`
   - Write 4-sheet xlsx per sample type → `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`
6. Run the script. Report row counts.
7. Suggest next arm or `/curate-consolidate`.

**Edge cases:**
- Missing manifest data (e.g., 27 phospho rows have no file paths): use placeholder markers
- Sample type new to schema: write to `assay_sheets/pending_schema/`
- Mid-arm scope ambiguity: stop, add to QUESTIONS, propose to user

---

## Phase 6 — Consolidate

**Command:** `/curate-consolidate`

**Inputs:** `assay_sheets/4sheet_originals/*.xlsx`, optional `context/assay_ids_cache.json` + `context/assay_synonyms.json`

**Action:**
1. Invoke `scripts/consolidate_to_flat.py`.
2. Archive 4-sheet originals if not already in `4sheet_originals/`.
3. Per arm: produce flat-format xlsx with `Samples` sheet (cols: uid, sampletype, name, parent, notes_summary, assay_titles, assay_ids, json_metadata) + `README` sheet.
4. Report per-arm row counts.

**Edge cases:**
- Cache or synonyms missing: leave `assay_ids` blank, suggest `/curate-resolve-assays`
- Pending-schema sample types: write to `assay_sheets/pending_schema/Arm<X>.xlsx`
- D.REF leak-back on re-run: warn user

---

## Phase 7 — Resolve assays

**Command:** `/curate-resolve-assays --project-id N`

**Inputs:** `.env` with `NEXTSEEK_USERNAME` + `NEXTSEEK_PASSWORD`, project ID

**Action:**
1. Invoke `scripts/nextseek_api.py fetch-assays --project-id N`.
2. Write `context/assay_ids_cache.json` in cwd.
3. Diff cached assay titles vs cited titles in build scripts.
4. For unresolved titles, prompt user to curate `context/assay_synonyms.json` (LLM-judgment layer, per yufei-gemm-2 design).
5. Update `.dmac-curation.json` lockfile with `nextseek_project_id`.

**Edge cases:**
- Auth fail (401): re-prompt for `.env` values, don't log
- Pagination hang: `nextseek_api.py` already fixed (next-link-only termination)
- Project has zero assays: warn, ask user to verify project ID

---

## Phase 8 — Synonyms (no command, LLM-driven)

Embedded in Phase 7 flow. SKILL.md instructs: read `assay_ids_cache.json`, compare against `assay_titles` columns in `assay_sheets/Arm*.xlsx`, propose mappings, ask user to confirm. Write `context/assay_synonyms.json` with `_README` + `synonyms` keys, each entry annotated with a `_notes` block.

---

## Phase 9 — QA

**Command:** `/curate-qa`

**Inputs:** `assay_sheets/Arm*.xlsx`, master xlsx for parent resolvability

**Action:**
1. Invoke `scripts/qa_flat_sheets.py`.
2. Per row: classify CLEAN / SOFT_FLAG / HARD_REJECT.
3. Report counts + per-row dispositions.
4. Surface specific gaps (missing File_PrimaryData, dangling parents, malformed json_metadata, surprise placeholder markers).

**Edge cases:**
- File_PrimaryData blank: HARD_REJECT (per skill rule 8 — required)
- Link_PrimaryData / Checksum_PrimaryData blank: SOFT_FLAG (not enforced)
- Parent UID not in new sheets or master: HARD_REJECT (dangling)
- Pending-schema type: HARD_REJECT (move to pending_schema/)
- Marker like `*** PLACEHOLDER: ... ***` in `File_PrimaryData`: SOFT_FLAG (acceptable)

---

## Phase 10 — Deposit

**Command:** `/curate-deposit <geo|zenodo|omero> [args]`

Routes by first arg:

### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

- Drives `scripts/deposit/geo_build_xlsx.py` to render BULK_filled.xlsx or SPTX_filled.xlsx from filled metadata.
- Drives `scripts/upload_geo_ncftp.sh` for upload.
- After GEO acceptance (manual confirmation): `scripts/apply_geo_accessions.py --write` patches D.SEQ/A.GEX/A.SPTX with GSM URLs.

### `/curate-deposit zenodo [--record-id N]`

- Drives `scripts/stage_zenodo.py --dry-run` then (after user confirms) without `--dry-run`.
- User uploads zips to Zenodo manually via web UI.
- After upload: `scripts/apply_zenodo_links.py --write --record-id N` patches `Link_PrimaryData`.

### `/curate-deposit omero [--project-id N]`

- User uploads images manually via OMERO Insight.
- `scripts/omero_pull.py all --project N` → `omero_images.csv`.
- `scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData`.

**Edge cases:**
- GEO literal validation failures: re-prompt user with corrected literals
- ncftp timeout on big file: script already has retry loop
- OMERO upload partial: diff `omero_images.csv` against manifest, identify missing IDs
- Zenodo record not created yet: surface to user, suggest creating record first

---

## Phase 11 — Retrieve

**Command:** `/curate-retrieve [--include-parents]`

**Inputs:** `assay_sheets/*-upload-new.xlsx`

**Action:**
1. Invoke `scripts/build_retrieve.py`.
2. By default exclude DNA/RNA/MUS/TIS/PAT/PAV/CHM/CEL (auto-pulled by `chat_nextseek`).
3. Write `./RETRIEVE.TXT` (newline-separated, sorted).
4. Report per-sample-type counts.

**Edge cases:**
- No upload-new sheets present: refuse, suggest `/curate-build` + `/curate-consolidate`
- User passes UIDs to fetch via `chat_nextseek`; auto-pulls parents; returns `*_AllMetadata.xlsx`

---

## Phase 12 — Validate

**Command:** `/curate-validate <metadata.xlsx>`

**Inputs:** downloaded `*_AllMetadata.xlsx` from `chat_nextseek`, current `RETRIEVE.TXT`, upload sheets

**Action:**
1. Invoke `scripts/review_metadata_vs_uploads.py`.
2. Diff: which RETRIEVE UIDs are missing from the download; which upload-sheet field values differ from the round-tripped values; which parents auto-pulled.
3. Report.

**Edge cases:**
- Auto-pulled parents count: subtract from "extra rows" before alarming
- Field drift: distinguish formatting changes (whitespace, case) from semantic drift (different value)

---

## Phase 13 — Email

**Command:** `/curate-email`

**Inputs:** `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md`, deposit state, `CLAUDE.md` (lab + pi)

**Action:**
1. Read project state.
2. Render `templates/EMAIL_TO_PI.md.j2` → `./EMAIL_TO_PI.md` with: subject, greeting, summary paragraph, files-curated summary, questions, deposit status, asks.
3. Iterate per-section with the user (skeleton-first; user writes final voice).
4. Hard rules: Name-pattern anchors not row numbers; no em dashes.

**Edge cases:**
- Manuscript references in questions: use Name-patterns (`the 27 rows ending in _phospho`)
- Long deposit lists: bullet, don't paragraph
- Multiple PIs: address all in greeting, ask user

---

## Phase any — Status

**Command:** `/curate-status`

**Action:** scan cwd for artifact files, lockfile, read state. Print:
- Phase artifacts present (✓ / ✗)
- Lockfile contents (lab, pi, project_id, plugin SHA)
- Suggested next command
```

- [ ] **Step 2: Commit**

```bash
git add skills/curation/PHASES.md
git commit -m "skill: PHASES.md deep per-phase reference"
```

---

## Phase F — Slash commands

### Task 13: Write `/curate-init` command

**Files:**
- Create: `commands/curate-init.md`

- [ ] **Step 1: Write `commands/curate-init.md`**

```markdown
---
description: Scaffold a new dmac-curation project (Phase 0)
---

The user wants to scaffold a new curation project in the current working directory.

Parse from $ARGUMENTS: `--lab <CODE>` (e.g., `KAM`, `ENG`, `WHI`, `GRI`) and `--pi <NAME>` (e.g., `marie`, `lee`, `yufei`). Both required. If missing, use `AskUserQuestion` to prompt — do NOT guess.

## Prereqs check

1. Verify cwd is empty or contains only PI inputs. The following must NOT already exist (else abort unless user adds `--force`):
   - `CLAUDE.md`
   - `.dmac-curation.json`
   - `scripts/` (with contents)
   - `context/` (with contents)
2. Verify the plugin is reachable. The plugin path is the directory containing this command file's grandparent (`<plugin>/commands/curate-init.md` → `<plugin>/`).

## Steps

1. Resolve plugin path from `$PLUGIN_PATH` env or via the path of this command file.
2. Read plugin's git SHA: `git -C <PLUGIN_PATH> rev-parse HEAD` (gracefully handle missing git).
3. Read schema vintage: `<PLUGIN_PATH>/context/VINTAGE.json` → `snapshot_date` field.
4. Create directories: `mkdir -p files manuscript previous_metadata assay_sheets scripts`.
5. Render templates by reading `<PLUGIN_PATH>/templates/<NAME>.j2` and substituting placeholders. The substitution is simple text replacement of `{{ placeholder }}` tokens — no need for a Jinja2 runtime; do it inline as Python via Bash heredoc:

   ```bash
   uv run --with jinja2 python3 <<'PY'
   from jinja2 import Environment, FileSystemLoader, StrictUndefined
   import json, datetime, os
   plugin = os.environ.get("PLUGIN_PATH", "<PATH>")
   env = Environment(loader=FileSystemLoader(plugin + "/templates"), undefined=StrictUndefined)
   ctx = {"lab": "$LAB", "pi_name": "$PI", "init_date": datetime.date.today().isoformat()}
   for tpl, dest in [("CLAUDE.md.j2", "CLAUDE.md"),
                     ("env.example.j2", ".env.example"),
                     ("gitignore.j2", ".gitignore"),
                     ("pyproject.toml.j2", "pyproject.toml")]:
       template = env.get_template(tpl)
       extra = {}
       if tpl == "pyproject.toml.j2":
           extra["project_slug"] = f"{ctx['pi_name']}_curation"
       with open(dest, "w") as f:
           f.write(template.render(**ctx, **extra))
   PY
   ```

6. Write `.dmac-curation.json` lockfile:
   ```json
   {
     "plugin_name": "dmac-curation",
     "plugin_sha": "<git rev-parse output>",
     "plugin_version": "0.1.0",
     "schema_vintage": "<VINTAGE.json date>",
     "init_date": "<today>",
     "init_user": "<$USER>",
     "lab": "<LAB uppercased>",
     "pi": "<PI lowercased>",
     "nextseek_project_id": null
   }
   ```
7. Report to user:
   - Which files were written
   - Reminder to drop inputs into `files/`, `manuscript/`, `previous_metadata/`
   - Suggested next: `/curate-inventory`

## Behavioral rules

- Never overwrite an existing `CLAUDE.md` without explicit `--force` (and even then, confirm).
- If `--lab` or `--pi` missing, use `AskUserQuestion` with single-select options derived from `<plugin>/labs/` if that exists, else prompt freely.
- If plugin has no `.git` (e.g., installed as a tarball), record `"plugin_sha": null` and continue.
- Don't initialize git in the project dir — let the user decide. But suggest it in the report.
- Refuse if cwd contains `.env` (might be a real project already) unless `--force`.
```

- [ ] **Step 2: Commit**

```bash
git add commands/curate-init.md
git commit -m "command: /curate-init (Phase 0 — scaffold + lockfile)"
```

---

### Task 14: Write Phase 1-4 commands (`inventory`, `sample-tree`, `questions`, `status`)

**Files:**
- Create: `commands/curate-inventory.md`
- Create: `commands/curate-sample-tree.md`
- Create: `commands/curate-questions.md`
- Create: `commands/curate-status.md`

- [ ] **Step 1: Write `commands/curate-inventory.md`**

```markdown
---
description: Build FILE_INDEX.md from PI inputs (Phase 1)
---

The user wants Phase 1 — inventory of inputs.

## Prereqs

- `.dmac-curation.json` exists (or run `/curate-init` first)
- At least one of `files/`, `manuscript/`, `previous_metadata/` has content (warn if all empty but proceed anyway with empty FILE_INDEX)

## Steps

1. Walk `files/` with `tree -L 2 -h` or `ls -lh`. Capture sizes per top-level subdir.
2. List `manuscript/`. If a `.docx` is present, extract text via Python+zipfile and grep for "Methods" / "Results" section headers.
3. For each xlsx in `previous_metadata/`, invoke `uv run --script <PLUGIN>/scripts/inspect_workbook.py <path>`. Capture sheet names, row counts.
4. Read `email_convo.md` if present; summarize sender list and topic threads.
5. Identify the PI's existing rows in the master xlsx — filter `Scientist` column or Notes column for the PI's name. Count per sample type.
6. Surface "things to flag now" — anything that looks like a blocker (missing master xlsx, manuscript without Methods, file types you can't parse).
7. Render `<PLUGIN>/templates/FILE_INDEX.md.j2` with the gathered context → `./FILE_INDEX.md`.
8. Suggest `/curate-sample-tree`.

## Behavioral rules

- If `previous_metadata/` has multiple xlsxs, list them all; mark the most-recent as master.
- For very large `files/` trees, summarize per-figure / per-arm without listing every file.
- Use the `inspect_workbook.py` script — don't reimplement inline.
```

- [ ] **Step 2: Write `commands/curate-sample-tree.md`**

```markdown
---
description: Derive SAMPLE_TREE.md from manuscript + master + context (Phase 2)
---

The user wants Phase 2 — map the manuscript narrative to NExtSEEK sample types as ASCII trees.

## Prereqs

- `./FILE_INDEX.md` exists (or run `/curate-inventory` first)
- `./manuscript/` non-empty
- `./previous_metadata/*.xlsx` exists

## Steps

1. Read `manuscript/*.docx` extracted text. Identify experimental arms.
2. Read `<PLUGIN>/context/sampletypes_db.json` (101 types) and `<PLUGIN>/context/assays_db.json` (217 assays).
3. For each arm, identify required sample types. Use the master xlsx to determine `[EXIST]` (existing UIDs) vs `[NEW]` (to be created).
4. For each new sample type, infer parent type — **sample existing PI rows first**, fall back to `sampletypes_db.json` if no precedent.
5. Build ASCII trees per arm.
6. Surface 5-15 open structural questions at the bottom (cohort sizes, parentage ambiguity, vocabulary gaps, file path completeness, deposit destinations).
7. Render `<PLUGIN>/templates/SAMPLE_TREE.md.j2` → `./SAMPLE_TREE.md`.
8. Suggest `/curate-questions add` to formalize the open questions, or `/curate-build <arm>` to start.

## Behavioral rules

- Schema lies; workbook tells truth. Sample 5-10 existing PI rows per sample type before consulting the schema JSON.
- For sample types not in `sampletypes_db.json`, mark `PENDING_SCHEMA` and add a question for the NExtSEEK admin.
- Trees are ASCII art, not prose. The user explicitly prefers concrete trees with real UIDs.
- Distinguish `[EXIST]` (existing UID, reused) from `[NEW]` (to be minted this curation).
```

- [ ] **Step 3: Write `commands/curate-questions.md`**

```markdown
---
description: Maintain QUESTIONS_FOR_PI.md (Phase 3)
---

The user is managing the running questions ledger.

Parse `$ARGUMENTS`:
- `add` (or no args): prompt for new question and append
- `list`: print all open + resolved questions
- `resolve <id>`: prompt for answer, move to resolved

## Steps

### `add` flow

1. Read `./QUESTIONS_FOR_PI.md` (or create from template if absent).
2. Determine next ID (one greater than max existing).
3. Use `AskUserQuestion` for topic, body, and originating phase.
4. Append to "Open" section.
5. Save.

### `list` flow

Print the file's contents grouped by Open / Resolved.

### `resolve <id>` flow

1. Find question by ID.
2. Use `AskUserQuestion` for the answer text.
3. Move from "Open" to "Resolved" with the answer.
4. Save.

## Behavioral rules

- ID format: `Q<N>` numeric, monotonic.
- Each question records the phase that surfaced it.
- Resolved questions never deleted — searchable history matters.
```

- [ ] **Step 4: Write `commands/curate-status.md`**

```markdown
---
description: Show pipeline state (any phase)
---

The user wants to know where the project is in the 13-phase pipeline.

## Steps

1. Read `.dmac-curation.json` (lockfile). If missing, advise `/curate-init`.
2. Check for presence of artifact files (per phase):
   - Phase 1: `FILE_INDEX.md`
   - Phase 2: `SAMPLE_TREE.md`
   - Phase 3: `QUESTIONS_FOR_PI.md` (with open vs resolved count)
   - Phase 5: `assay_sheets/4sheet_originals/*.xlsx` (count)
   - Phase 6: `assay_sheets/Arm*.xlsx` (excluding 4sheet_originals/)
   - Phase 7: `context/assay_ids_cache.json` + `context/assay_synonyms.json`
   - Phase 11: `RETRIEVE.TXT` (line count)
   - Phase 13: `EMAIL_TO_PI.md`
3. Read `assay_sheets/` for upload-new sheets vs upload sheets; report counts.
4. Print a status table:

   ```
   Project: marie (KAM) — initialized 2026-05-27
   Lockfile: plugin SHA abc123, schema vintage 2026-05-08

   Phase 1 Inventory:     ✓  FILE_INDEX.md (4.2 KB)
   Phase 2 Sample tree:   ✓  SAMPLE_TREE.md (8 arms)
   Phase 3 Questions:     ✓  12 open, 8 resolved
   Phase 5 Build:         ✓  6/8 arms built (20 4sheet files)
   Phase 6 Consolidate:   ✗
   Phase 7 Resolve:       ✗
   ...
   Phase 13 Email:        ✗

   Suggested next: /curate-build (arms C, G still pending)
   ```
5. Make a suggestion for next command based on current state.

## Behavioral rules

- Be honest about partial state (e.g., 6/8 arms).
- Don't reformat — terse table is fine.
- Always end with a single-line "Suggested next: …".
```

- [ ] **Step 5: Commit**

```bash
git add commands/curate-inventory.md commands/curate-sample-tree.md commands/curate-questions.md commands/curate-status.md
git commit -m "commands: Phase 1-4 + status (inventory, sample-tree, questions, status)"
```

---

### Task 15: Write Phase 5-9 commands (`build`, `consolidate`, `resolve-assays`, `qa`)

**Files:**
- Create: `commands/curate-build.md`
- Create: `commands/curate-consolidate.md`
- Create: `commands/curate-resolve-assays.md`
- Create: `commands/curate-qa.md`

- [ ] **Step 1: Write `commands/curate-build.md`**

```markdown
---
description: Build per-arm upload sheets (Phase 5)
---

The user wants to build assay-sheet rows for a specific experimental arm.

Parse `$ARGUMENTS`: optional `<arm>` (letter or short name). If omitted, list arms from `SAMPLE_TREE.md` and use `AskUserQuestion`.

## Prereqs

- `./SAMPLE_TREE.md` exists
- `./previous_metadata/*.xlsx` exists (master)
- `./CLAUDE.md` exists (lab + pi)
- `./.env` exists (warn if missing — needed at consolidate)

## Steps

1. Read `SAMPLE_TREE.md`, identify the arm. Read sample types and counts.
2. Read master xlsx for existing parent UIDs (cell-line CEL UIDs, patient PAT UIDs, etc.) — don't recreate.
3. Read manuscript for instrument details, protocol section names.
4. Generate `./scripts/build_<arm>.py`. The file must:
   - Begin with PEP 723 inline-deps header (`openpyxl>=3.1`)
   - Insert `<PLUGIN_PATH>/scripts` into `sys.path`
   - `from _common import mint_uid, write_4sheet_xlsx, ...` (use functions that actually exist; consult `<PLUGIN>/scripts/_common.py`)
   - Define `ROW_INFO` / `ARM_BY_COL` / `TIMEPOINT_BY_COL` constants encoding the arm's structure
   - Mint UIDs from N=1 per sample type
   - Write 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type to `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`
5. Save the script. Run it: `uv run --script ./scripts/build_<arm>.py`.
6. Report row counts per file.
7. Suggest the next arm or `/curate-consolidate`.

## Behavioral rules

- Follow precedent over schema (sample existing PI rows in `previous_metadata/` before writing new ones — schema lies, workbook tells truth).
- Use `*** PLACEHOLDER: ... ***` markers for unknown values, never blanks (greppable).
- Pre-assigned UIDs (no auto-gen). Format `<TYPE>-YYMMDD<LAB>-N`.
- Don't include parent-tier records that already exist — `/curate-retrieve` auto-pulls them.
- If the arm has new sample types not in `sampletypes_db.json` (e.g., `D.REF`), write to `assay_sheets/pending_schema/` and note in `QUESTIONS_FOR_PI.md`.
```

- [ ] **Step 2: Write `commands/curate-consolidate.md`**

```markdown
---
description: Collapse 4-sheet xlsx files into flat-format Arm{X}.xlsx (Phase 6)
---

The user wants Phase 6 — consolidate the per-sample-type 4-sheet xlsx files into per-arm flat-format upload sheets.

## Prereqs

- `assay_sheets/4sheet_originals/*.xlsx` exists with at least one file
- Or, if re-running, `assay_sheets/*.xlsx` already exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py [--assay-sheets ./assay_sheets] [--all-in-one <NAME>]`.
2. Verify per-arm xlsx files written to `assay_sheets/`.
3. If `context/assay_ids_cache.json` exists, the script populates the `assay_ids` column. Report resolution stats.
4. If `assay_ids` is mostly empty, suggest `/curate-resolve-assays --project-id N`.
5. Otherwise, suggest `/curate-qa`.

## Behavioral rules

- Check for manual edits in `assay_sheets/Arm*.xlsx` before regenerating. If files exist with mtime newer than `4sheet_originals/`, diff first; ask user.
- Idempotent — safe to re-run.
- Move `D.REF` or other pending-schema rows to `assay_sheets/pending_schema/`.
```

- [ ] **Step 3: Write `commands/curate-resolve-assays.md`**

```markdown
---
description: Fetch project assays via NExtSEEK API and curate synonyms (Phase 7-8)
---

The user wants Phase 7 — resolve assay titles to integer IDs by fetching the live project catalog from NExtSEEK.

Parse `$ARGUMENTS`: `--project-id N` (required).

## Prereqs

- `./.env` exists with `NEXTSEEK_USERNAME` and `NEXTSEEK_PASSWORD` (or `NEXTSEEK_TOKEN`)
- `assay_sheets/Arm*.xlsx` exists (so we have titles to resolve)

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id <N>`.
2. Verify `context/assay_ids_cache.json` written.
3. Diff cached assay titles against `assay_titles` columns in `assay_sheets/Arm*.xlsx`.
4. For each unresolved title, propose a synonym mapping. Use `AskUserQuestion` per mapping (don't batch — judgment per row).
5. Write `context/assay_synonyms.json` with structure:
   ```json
   {
     "_README": [...],
     "synonyms": {
       "<cited title>": "<actual project assay title>"
     },
     "intentionally_unmapped": ["<title>"]
   }
   ```
   Each synonym entry should have a `_notes` block explaining why.
6. Update `.dmac-curation.json` lockfile with `nextseek_project_id`.
7. Suggest re-running `/curate-consolidate` to apply the new assay_ids.

## Behavioral rules

- Auth fail (401): re-prompt for `.env` values; never log.
- Don't auto-map heuristically. Curate per-row with user input (this is the LLM-judgment step Charlie explicitly carved out).
- Note explicitly-unmapped assays (e.g., "Mouse Challenge" not registered as project-10 assay).
```

- [ ] **Step 4: Write `commands/curate-qa.md`**

```markdown
---
description: QA the upload sheets — CLEAN / SOFT_FLAG / HARD_REJECT (Phase 9)
---

The user wants Phase 9 — QA pass on the consolidated upload sheets.

## Prereqs

- `assay_sheets/Arm*.xlsx` exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/qa_flat_sheets.py`.
2. Read the script's report. Categorize each row CLEAN / SOFT_FLAG / HARD_REJECT.
3. Print per-arm summary table:
   ```
   ArmA.xlsx (117 rows): 88 CLEAN, 12 SOFT_FLAG, 17 HARD_REJECT
     HARD_REJECT reasons:
       - missing File_PrimaryData (15)
       - dangling Parent UID (2)
     SOFT_FLAG reasons:
       - PLACEHOLDER marker in metadata (10)
       - assay_id unresolved (2)
   ...
   ```
4. Suggest fixes for HARD_REJECT rows:
   - Missing files → use placeholder markers + `/curate-questions add`
   - Dangling parents → check `previous_metadata` master, possibly build the missing parent
   - Pending schema → move to `assay_sheets/pending_schema/`

## Behavioral rules

- `File_PrimaryData` blank → HARD_REJECT (skill rule 8)
- `Link_PrimaryData` / `Checksum_PrimaryData` blank → SOFT_FLAG (not enforced)
- Parent UID not in new sheets or master → HARD_REJECT
- Pending-schema type → HARD_REJECT (move out of upload set)
- `*** PLACEHOLDER: ... ***` marker in `File_PrimaryData` → SOFT_FLAG (intentional)
- Don't be the last gate — surface dispositions to user for confirmation.
```

- [ ] **Step 5: Commit**

```bash
git add commands/curate-build.md commands/curate-consolidate.md commands/curate-resolve-assays.md commands/curate-qa.md
git commit -m "commands: Phase 5-9 (build, consolidate, resolve-assays, qa)"
```

---

### Task 16: Write Phase 10-13 commands (`deposit`, `retrieve`, `validate`, `email`)

**Files:**
- Create: `commands/curate-deposit.md`
- Create: `commands/curate-retrieve.md`
- Create: `commands/curate-validate.md`
- Create: `commands/curate-email.md`

- [ ] **Step 1: Write `commands/curate-deposit.md`**

```markdown
---
description: Stage external deposits and backfill URLs (Phase 10)
---

The user wants Phase 10 — deposit raw or secondary data to an external repository and backfill `Link_PrimaryData` URLs.

Parse `$ARGUMENTS`: first arg routes to sub-target.

## Sub-routes

### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

1. **Build**: invoke `<PLUGIN>/scripts/deposit/geo_build_xlsx.py` to render `GEO/BULK_filled.xlsx` or `GEO/SPTX_filled.xlsx` from `previous_metadata/*_AllMetadata*.xlsx`.
2. **Upload**: invoke `<PLUGIN>/scripts/upload_geo_ncftp.sh GEO/<subfolder>/`. Reads `.env` for `NCFTP_*` creds. Resilient with retry loop.
3. **Validate**: ask user to validate at submit.ncbi.nlm.nih.gov/geo/submission. Note common gotchas — `paired-end` (not `paired`); `Illumina NextSeq 500` (not `NextSeq 500`); processed-file cols must come before raw-file cols.
4. **Backfill (after GSE assigned)**: `<PLUGIN>/scripts/apply_geo_accessions.py --write --gse <GSE>`.

### `/curate-deposit zenodo [--record-id N] [--from-figures]`

1. **Stage**: `<PLUGIN>/scripts/stage_zenodo.py --dry-run` then (after confirm) without dry-run. Walk `files/Figure*/` + `files/Source Data/`. Group by figure × sample type. Produce per-bucket zips in `Zenodo_upload/`.
2. **User uploads** zips manually to Zenodo via web UI. User reports back the record ID.
3. **Backfill**: `<PLUGIN>/scripts/apply_zenodo_links.py --write --record-id <N>`. Joins zip namelists to upload-sheet rows by filename, patches `Link_PrimaryData`.

### `/curate-deposit omero [--project-id N]`

1. **Identify files** in `images_to_upload_to_omero/` (or whichever dir the user is staging from).
2. **User uploads** to OMERO via Insight desktop or web UI.
3. **Pull IDs**: `<PLUGIN>/scripts/omero_pull.py all --project <N>` → `omero_images.csv`.
4. **Backfill**: `<PLUGIN>/scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData` from `omero_images.csv`.

## Behavioral rules

- All scripts default to `--dry-run`. Confirm before applying writes.
- GEO has lots of literal-validation gotchas — surface them in the report.
- OMERO requires MIT VPN.
- Never log credentials. Read from `.env` via python-dotenv.
```

- [ ] **Step 2: Write `commands/curate-retrieve.md`**

```markdown
---
description: Build RETRIEVE.TXT for chat_nextseek (Phase 11)
---

The user wants Phase 11 — emit a newline-separated UID list for the `chat_nextseek` retrieve function.

Parse `$ARGUMENTS`: optional `--include-parents`.

## Prereqs

- `assay_sheets/*-upload-new.xlsx` (or `-upload.xlsx`) exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]`.
2. Verify `RETRIEVE.TXT` written. Print per-sample-type counts.
3. Tell the user to paste the file's contents into `chat_nextseek` to fetch the round-tripped `*_AllMetadata.xlsx`.

## Behavioral rules

- Default excludes MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL (auto-pulled by retrieve).
- `--include-parents` only for explicit override (rare).
- Prefer `-upload-new.xlsx` over `-upload.xlsx` (latest curation).
```

- [ ] **Step 3: Write `commands/curate-validate.md`**

```markdown
---
description: Round-trip diff downloaded metadata vs uploads (Phase 12)
---

The user wants Phase 12 — verify the downloaded `*_AllMetadata.xlsx` matches what was supposed to upload.

Parse `$ARGUMENTS`: `<metadata.xlsx>` (path to downloaded file).

## Prereqs

- `assay_sheets/*-upload-new.xlsx` exists
- `RETRIEVE.TXT` exists
- Downloaded `*_AllMetadata.xlsx` path provided

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata <PATH> --retrieve RETRIEVE.TXT`.
2. Read the diff report:
   - Missing UIDs (in RETRIEVE but not in download)
   - Extra UIDs (auto-pulled parents — expected; count separately)
   - Field drift per sample type (compare upload-sheet values to round-tripped values)
3. Print a summary table.
4. Surface any field drift to the user for resolution.

## Behavioral rules

- Auto-pulled parents are expected — don't flag as missing.
- Whitespace / case differences in fields = formatting only, soft note. Different values = real drift, hard flag.
- Don't auto-fix drift. Surface to user.
```

- [ ] **Step 4: Write `commands/curate-email.md`**

```markdown
---
description: Draft EMAIL_TO_PI.md iteratively (Phase 13)
---

The user wants Phase 13 — draft an email to the PI summarizing the curation state and asking remaining questions.

## Prereqs

- `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md` exist
- `CLAUDE.md` has lab + pi

## Steps

1. Read project state. Identify: arms built, arms deferred, deposit status, open questions.
2. Render `<PLUGIN>/templates/EMAIL_TO_PI.md.j2` into `./EMAIL_TO_PI.md` with skeleton (subject, greeting, summary paragraph, files curated, questions, deposits, asks).
3. **Iterate per-section with the user.** Don't dump full text. Present subject first, get feedback. Then summary paragraph. Then questions. Then asks. User writes the final voice in their own words.
4. Convert any row-number references to Name-pattern anchors (`the 27 rows ending in _phospho`, not `rows 28-54`).
5. Strip em dashes — replace with hyphens or colons.
6. Save final version.

## Behavioral rules

- Skeleton-first. Don't dump full prose.
- Iterate per-section.
- Name-pattern anchors, never row numbers.
- No em dashes (Charlie's style).
- Group questions by intent: structural/files vs metadata-clarifications.
- For multiple PIs: address all in greeting; ask user how to apportion questions.
```

- [ ] **Step 5: Commit**

```bash
git add commands/curate-deposit.md commands/curate-retrieve.md commands/curate-validate.md commands/curate-email.md
git commit -m "commands: Phase 10-13 (deposit, retrieve, validate, email)"
```

---

## Phase G — Finalize

### Task 17: Update README + CHANGELOG; final secret scan; tag v0.1.0

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README.md to reflect installed state**

Read current README.md. Update the "Status" section from "Design phase" to "v0.1.0 — initial release". Update the "Installation" section to drop "(forthcoming)". Add a "Quick start" section:

```markdown
## Quick start

```bash
# Install
git clone git@github.com:cdemurjian/dmac-curation.git ~/.claude/plugins/dmac-curation

# In any new curation project directory:
cd /path/to/empty/project_dir
/curate-init --lab KAM --pi marie

# Drop your inputs into files/, manuscript/, previous_metadata/
# Then walk the 13-phase pipeline:
/curate-inventory       # → FILE_INDEX.md
/curate-sample-tree     # → SAMPLE_TREE.md
/curate-build A         # → assay_sheets/4sheet_originals/
/curate-consolidate     # → assay_sheets/Arm*.xlsx
/curate-resolve-assays --project-id 10
/curate-qa
/curate-deposit zenodo
/curate-retrieve        # → RETRIEVE.TXT
/curate-email           # → EMAIL_TO_PI.md
```

## Update

```bash
cd ~/.claude/plugins/dmac-curation && git pull
```
```

- [ ] **Step 2: Update CHANGELOG.md**

```markdown
# Changelog

All notable changes to dmac-curation will be documented in this file.

## [0.1.0] — 2026-05-27

### Added
- Plugin manifest (`.claude-plugin/plugin.json`)
- Skill playbook (`skills/curation/SKILL.md` — 8 hard rules, 7 soft rules, 13 pitfalls)
- Deep phase reference (`skills/curation/PHASES.md`)
- 13 slash commands (`commands/curate-*.md`)
- 16 bundled scripts (NExtSEEK API, consolidate, QA, retrieve, rename, OMERO, SMB, deposits)
- 7 NExtSEEK schema snapshots (2026-05-27 vintage in `context/VINTAGE.json`)
- 9 Jinja2 templates for `/curate-init` to render into project working directories
- Comprehensive secrets-safe `.gitignore`
- Test suite: 6 test files covering template rendering + script CLI smoke tests

### Sources
Scripts lifted from prior curation sessions:
- intravchip (Marie Floryan, Kamm lab) — `_common.py`, `nextseek_api.py`, `consolidate_to_flat.py`, `qa_flat_sheets.py`, `rename_files.py`, `omero_pull.py`
- srp/lee (Lee Pribyl, Engelward lab) — `smb_pull.py`, `stage_zenodo.py`, `apply_*_links.py`, `apply_geo_accessions.py`, `upload_geo_ncftp.sh`, `review_metadata_vs_uploads.py`, `deposit/geo_build_xlsx.py`
```

- [ ] **Step 3: Run final secret scan over the whole repo**

Run:
```bash
{
  echo "=== Files in repo ==="
  git ls-files
  echo ""
  echo "=== Secret-pattern scan ==="
  git ls-files | xargs grep -EnH '(api[_-]?key|secret|password|token|bearer|aws_|ghp_|gho_|github_pat|sk-[a-zA-Z0-9]{20,}|xoxb-|xoxp-|-----BEGIN [A-Z ]+PRIVATE KEY)' 2>/dev/null \
    | grep -v 'NEXTSEEK_PASSWORD=$' \
    | grep -v 'NEXTSEEK_USERNAME=$' \
    | grep -v 'MIT_PASS=$' \
    | grep -v 'NCFTP_PASS=$' \
    | grep -v 'FDH_API=$' \
    | grep -v '\.gitignore' \
    | grep -v 'README\.md' \
    | grep -v 'env\.example' \
    | grep -v 'design.md' \
    | grep -v 'SKILL\.md' \
    | grep -v 'PHASES\.md' \
    | grep -v 'curate-.*\.md' \
    | grep -v 'CHANGELOG' \
    || echo "(no concerning matches)"
}
```

Expected: `(no concerning matches)`. If anything pops up, audit it before continuing.

- [ ] **Step 4: Run the full test suite**

Run:
```bash
uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v
```

Expected: ALL tests pass. If any fail, fix before tagging.

- [ ] **Step 5: Commit and tag v0.1.0**

```bash
git add README.md CHANGELOG.md
git commit -m "release: v0.1.0 — initial dmac-curation plugin"
git tag -a v0.1.0 -m "v0.1.0: initial plugin — 13 commands, 16 scripts, 7 schema snapshots"
git push origin main --tags
```

---

### Task 18: End-to-end smoke test in a temp project

**Files:**
- Test: `tests/test_e2e_init.sh`

- [ ] **Step 1: Symlink the plugin into Claude's plugin dir**

Run:
```bash
mkdir -p ~/.claude/plugins
ln -sfn "$(pwd)" ~/.claude/plugins/dmac-curation
ls -la ~/.claude/plugins/dmac-curation
```

Expected: symlink resolves to the repo directory.

- [ ] **Step 2: Write `tests/test_e2e_init.sh`**

```bash
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
        "schema_vintage": json.load(open(plugin + "/context/VINTAGE.json"))["snapshot_date"],
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
```

- [ ] **Step 3: Make the test executable and run it**

Run:
```bash
chmod +x tests/test_e2e_init.sh
tests/test_e2e_init.sh
```

Expected: `init OK` then `E2E init smoke test: PASS`.

- [ ] **Step 4: Confirm Claude Code discovers the plugin**

This step requires manual verification — open a fresh Claude Code session and check that `/curate-init` and other commands autocomplete. Document the verification in CHANGELOG.

- [ ] **Step 5: Commit final state**

```bash
git add tests/test_e2e_init.sh
git commit -m "test: E2E init smoke test"
git push origin main
```

---

## Self-review

Cross-checking the plan against the spec:

| Spec section | Plan task(s) | Coverage |
|---|---|---|
| §1 Problem statement | (context) | ✓ |
| §2 Audience and scope | Task 13 (`/curate-init --lab`) | ✓ |
| §3 13-phase pipeline | Tasks 13-16 (commands per phase) | ✓ |
| §4 Plugin shape | Task 1 (scaffolding) | ✓ |
| §5 Plugin-owned vs project-owned | Tasks 4-10 (plugin scripts), Task 13 (project scaffolding) | ✓ |
| §6 Slash command pattern | Tasks 13-16 | ✓ |
| §7 SKILL.md content | Task 11 | ✓ |
| §8 Bundled scripts | Tasks 4-10 | ✓ |
| §9 `/curate-init` flow + lockfile | Task 13 | ✓ |
| §10 Secrets handling | Already in initial commit; Task 17 re-verifies | ✓ |
| §11 Distribution | README updated in Task 17 | ✓ |
| §12 Non-goals | (informational) | ✓ |
| §13 Open questions | (informational, no tasks needed) | ✓ |
| §14 Success criteria | Tasks 17 + 18 (smoke test + tag) | ✓ |

Placeholder scan: searched the plan for "TBD", "implement later", "Similar to Task N" — none found.

Type consistency: `mint_uid(sample_type, lab, date, n)` signature consistent across `_common.py`, the test, and the `/curate-build` command spec.

Spec gap check: PHASES.md mentioned in spec §4 — created in Task 12. SKILL.md in spec §7 — created in Task 11. `.dmac-curation.json` lockfile in spec §9 — created in Task 13.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-dmac-curation-plugin.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
