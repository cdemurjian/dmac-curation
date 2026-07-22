# dmac-curation

A Claude Code plugin for curating research-project metadata into NExtSEEK / FairDomHub.
It is a curator's workbench, not a single pipeline: human-in-the-loop and PI-facing
throughout.

**Status:** v0.3.0

## What it does

The plugin is organised as four **modes**. A mode is a convention, not a framework:
entry-point commands, a reference doc loaded on demand, and optionally its own scripts.

- **`pipeline`** — the metadata curation pipeline: 11 phases from inventory through
  sample tree, build, consolidate, QA, deposit, retrieve, to emailing the PI. Needs a
  project (a lockfile and scaffold). Reference: [`skills/curation/PHASES.md`](skills/curation/PHASES.md).
- **`fdh`** — FairDomHub: interactive study upload and direct programmatic API access.
  Needs credentials only, no project. Reference: [`skills/curation/FDH.md`](skills/curation/FDH.md).
- **`schema`** — sample type authoring: propose or bolster a NExtSEEK sample type with a
  reuse check over the field index and controlled-vocabulary proposals. Writes where you
  are, no project needed. Reference: [`skills/curation/SCHEMA.md`](skills/curation/SCHEMA.md).
- **`report`** — repository submission artifacts: GEO, SRA and PRIDE reports from UIDs, a
  NExtSEEK workbook, a curated upload sheet, or arbitrary tabular data. Reads a lockfile
  if present, never requires one. Reference: [`skills/curation/REPORTS.md`](skills/curation/REPORTS.md).

## Commands, grouped by mode

**`pipeline`** (reference: `PHASES.md`)

| command | does |
|---|---|
| `/curate-init` | scaffold or extend a project working directory (additive) |
| `/curate-inventory` | `FILE_INDEX.md` from PI inputs |
| `/curate-sample-tree` | `SAMPLE_TREE.md` mapping manuscript narrative to NExtSEEK sample types |
| `/curate-questions` | running `QUESTIONS_FOR_PI.md` |
| `/curate-build` | per-arm upload sheets (4-sheet xlsx review artifact) |
| `/curate-consolidate` | collapse the 4-sheet sheets to flat-format `Arm{X}.xlsx` |
| `/curate-resolve-assays` | fetch project assays via NExtSEEK API, cache + curate synonyms |
| `/curate-qa` | CLEAN / SOFT_FLAG / HARD_REJECT disposition of the upload sheets |
| `/curate-deposit` | stage external deposits (Zenodo / OMERO / GEO) and backfill URLs |
| `/curate-retrieve` | emit `RETRIEVE.TXT` for the `chat_nextseek` retrieve function |
| `/curate-validate` | round-trip diff downloaded metadata vs uploads |
| `/curate-email` | draft `EMAIL_TO_PI.md` (skeleton-first, Name-pattern anchors) |

**`fdh`** (reference: `FDH.md`)

| command | does |
|---|---|
| `/fdh-upload` | launch the interactive study-upload tool (`scripts/fdh/submit.py`) |
| `/fdh-api` | programmatic API access — reuse or generate a script over `scripts/fdh/fdh_api.py` |

**`schema`** (reference: `SCHEMA.md`)

| command | does |
|---|---|
| `/curate-sampletype` | propose or bolster a NExtSEEK sample type; writes a `<TYPE>.review.md` for a human to apply |

**`report`** (reference: `REPORTS.md`)

| command | does |
|---|---|
| `/curate-report` | GEO / SRA / PRIDE submission artifacts from UIDs, a workbook, an `Arm{X}.xlsx`, or tabular data |

**Any mode**

| command | does |
|---|---|
| `/curate-status` | show toolkit state per mode |

## What this is not

- It does **not** upload to NExtSEEK on its own — it produces upload-ready metadata for a
  human to submit.
- It does **not** edit the NExtSEEK sample type catalog — `schema` mode writes a proposal
  and a rationale; a human applies it.
- It does **not** fabricate values — unknowns are left as greppable
  `*** PLACEHOLDER: ... ***` markers, and ambiguity is surfaced, not guessed.

## Auth

- **NExtSEEK / SMB / GEO** — per-project `.env` files, never in the plugin, never in git.
- **FairDomHub** — per-project `.env` `FDH_API={"name": "token"}`.

See `.gitignore` for the full exclusion list, and `docs/SECURITY.md`.

## Repo layout

```
dmac-curation/
├── .claude-plugin/{plugin.json, marketplace.json}
├── skills/curation/{SKILL.md, PHASES.md, FDH.md, SCHEMA.md, REPORTS.md}
├── commands/{curate-*.md, fdh-*.md}   # slash commands, grouped by mode
├── scripts/                           # PEP 723 inline-deps, uv-runnable
│   ├── fdh/                           # FairDomHub upload + API
│   ├── report/                        # report-mode adapters, mapping, render, validate
│   ├── schema/                        # schema-mode field index + vocabulary
│   └── deposit/                       # external deposit builders
├── context/                           # frozen NExtSEEK schema snapshots + provenance
├── templates/                         # .md.j2 + config.j2 rendered into cwd
└── docs/
```

## Quick start

```bash
# Install
git clone git@github.com:cdemurjian/dmac-curation.git ~/.claude/plugins/dmac-curation

# In any new curation project directory:
cd /path/to/empty/project_dir
/curate-init --lab KAM --pi marie

# Drop your inputs into files/, manuscript/, previous_metadata/
# Then walk the pipeline mode:
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

The other three modes need no project:

```bash
/curate-sampletype D.VIA          # schema mode — writes D.VIA.review.md in cwd
/curate-report GEO my_metadata.xlsx   # report mode — builds a GEO submission artifact
/fdh-upload                       # fdh mode — interactive FairDomHub study upload
```

## Update

```bash
cd ~/.claude/plugins/dmac-curation && git pull
```

Per-project `.dmac-curation.json` lockfile records the plugin SHA + schema vintage used at init for reproducibility.

## License

MIT
