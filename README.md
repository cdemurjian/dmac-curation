# dmac-curation

A Claude Code plugin for curating research-project metadata into NExtSEEK / FairDomHub.
It is a curator's workbench, not a single pipeline: human-in-the-loop and PI-facing
throughout.

**Status:** v0.5.0

## What it does

The plugin is organised as five **modes**. A mode is a convention, not a framework:
entry-point commands, a reference doc loaded on demand, and optionally its own scripts.

- **`pipeline`** — the metadata curation pipeline: 12 phases from inventory through
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
- **`assay`** — assay hygiene: find samples that should be registered against an internal
  assay and are not, put every proposal in front of a human, write the approved ones to
  production. **House-scoped** — one extract, all projects, no PI — so it runs from the
  plugin checkout itself (the directory holding `scripts/` and `assets/`), not from a
  curation project. Reference: [`skills/curation/ASSAY.md`](skills/curation/ASSAY.md).

## Commands, grouped by mode

**`pipeline`** (reference: `PHASES.md`)

| command | does |
|---|---|
| `/curate-init` | scaffold or extend a project working directory (additive) |
| `/curate-inventory` | `FILE_INDEX.md` from PI inputs |
| `/curate-sample-tree` | `SAMPLE_TREE.md` + `sample_tree.json` + interactive `SAMPLE_TREE.html`, mapping manuscript narrative to NExtSEEK sample types |
| `/curate-questions` | running `QUESTIONS_FOR_PI.md` |
| `/curate-build` | per-arm upload sheets (4-sheet xlsx review artifact) |
| `/curate-consolidate` | collapse the 4-sheet sheets to flat-format `Arm{X}-upload.xlsx`, plus `Arm{X}_review.xlsx` (one sheet per sample type, for humans) |
| `/curate-resolve-assays` | fetch project assays via NExtSEEK API, cache + curate synonyms |
| `/curate-qa` | CLEAN / SOFT_FLAG / HARD_REJECT disposition of the upload sheets (local, offline) |
| `/curate-qc` | validate against the **live** NExtSEEK server; triage schema gaps. The last gate before upload |
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
| `/curate-sampletype` | propose or bolster a NExtSEEK sample type; writes a `<TYPE>.review.md` for a human to apply. The explicit `apply` verb can also **write the change to a live server** via `scripts/sampletype_attr.py` |

**`assay`** (reference: `ASSAY.md`)

Run in order. Every path is relative to the plugin checkout; runs are numbered and
immutable at `assets/RUN<n>/`, and one run is open at a time.

| command | does |
|---|---|
| `/curate-assay-init` | open a numbered run, prove the ruling store survives, freeze the run's tiers |
| `/curate-assay-vocabulary` | stage B2 — map the unresolved tail of metadata terms onto internal assays |
| `/curate-assay-detect` | evidence + detection passes into this run's own directory |
| `/curate-assay-review` | serve the review surfaces, ingest the operator's rulings, auto-backup the store |
| `/curate-assay-resolve` | turn approved pairs into per-project SEEK write targets, behind the project gate |
| `/curate-assay-write` | **writes to production**, behind eight preflight refusals |
| `/curate-assay-status` | report which run is open and where it has got to; writes nothing |
| `/curate-assay-backup` | dated, verified tarball of the ruling store |

The ruling store at `assets/rulings/` is human judgement and **nothing regenerates it** —
not compute, not a re-run. It is gitignored; its only protection is the tarball
`/curate-assay-backup` writes.

**`report`** (reference: `REPORTS.md`)

| command | does |
|---|---|
| `/curate-report` | GEO / SRA / PRIDE submission artifacts from UIDs, a workbook, an `Arm{X}-upload.xlsx`, or tabular data |

**Any mode**

| command | does |
|---|---|
| `/curate-status` | show toolkit state for `pipeline`, `fdh`, `schema` and `report` (assay mode has its own `/curate-assay-status`) |

## What this is not

- It does **not** upload curated project metadata to NExtSEEK — `pipeline` mode produces
  upload-ready sheets for a human to submit. The two exceptions are explicit, opt-in and
  named: `/curate-sampletype apply` (adds one attribute to a live sample type; dry-run by
  default, `--apply` to write, `--yes-production` on top of that for production) and
  `/curate-assay-write` (writes assay registrations to production behind eight preflight
  refusals, a captured rollback handle and a verified DB backup).
- It does **not** invent sample types — `schema` mode writes a proposal and a rationale for
  a human to review, and only the explicit `apply` verb writes anything.
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
├── skills/curation/{SKILL.md, PHASES.md, FDH.md, SCHEMA.md, REPORTS.md, ASSAY.md}
├── commands/{curate-*.md, fdh-*.md}   # 26 slash commands, grouped by mode
├── scripts/                           # PEP 723 inline-deps, uv-runnable
│   ├── nextseek_api.py                # assay-id cache, server-side validate, sample-type reads
│   ├── sampletype_attr.py             # add attributes to a live sample type (native editor)
│   ├── consolidate_to_flat.py         # 4-sheet -> flat upload file + _review.xlsx
│   ├── build_sample_tree_html.py      # sample_tree.json -> interactive SAMPLE_TREE.html
│   ├── assay_hygiene/                 # assay mode: extract, detect, rule, resolve, write
│   ├── fdh/                           # FairDomHub upload + API
│   ├── report/                        # report-mode adapters, mapping, render, validate
│   ├── schema/                        # schema-mode field index + vocabulary
│   └── deposit/                       # external deposit builders
├── context/                           # frozen NExtSEEK schema snapshots + provenance
├── templates/                         # .md.j2 + config.j2 rendered into cwd
├── tests/                             # pytest suite + fixtures
├── docs/                              # SECURITY.md, findings, specs and plans
├── pyproject.toml, uv.lock            # uv.lock is tracked on purpose (reproducibility)
└── CHANGELOG.md
```

Run output — `assets/`, `assay-hygiene/`, `working/` — is gitignored and never committed;
`assets/` in particular holds real sample identifiers and this repository is public.
See `.gitignore`.

## Quick start

```bash
# Install (the repo ships .claude-plugin/marketplace.json — a marketplace named `dmac`)
git clone git@github.com:cdemurjian/dmac-curation.git ~/code/dmac-curation
```

Then in Claude Code:

```
/plugin marketplace add ~/code/dmac-curation
/plugin install dmac-curation@dmac
```

```bash
# In any new curation project directory:
cd /path/to/empty/project_dir
/curate-init --lab KAM --pi marie

# Drop your inputs into files/, manuscript/, previous_metadata/
# Then walk the pipeline mode:
/curate-inventory       # → FILE_INDEX.md
/curate-sample-tree     # → SAMPLE_TREE.md + sample_tree.json + SAMPLE_TREE.html
/curate-build A         # → assay_sheets/4sheet_originals/
/curate-consolidate     # → assay_sheets/Arm*-upload.xlsx + Arm*_review.xlsx
/curate-resolve-assays --project-id 10
/curate-qa              # local checks
/curate-qc              # server-side validation - last gate before upload
/curate-deposit zenodo
/curate-retrieve        # → RETRIEVE.TXT
/curate-email           # → EMAIL_TO_PI.md
```

The other four modes need no curation project. `fdh`, `schema` and `report` run wherever
you are; `assay` runs from the plugin checkout itself:

```bash
/curate-sampletype D.VIA          # schema mode — writes D.VIA.review.md in cwd
/curate-report GEO my_metadata.xlsx   # report mode — builds a GEO submission artifact
/fdh-upload                       # fdh mode — interactive FairDomHub study upload
/curate-assay-status              # assay mode — which run is open, and where it got to
```

## Update

```bash
cd ~/code/dmac-curation && git pull
```

then in Claude Code:

```
/plugin marketplace update dmac
```

Per-project `.dmac-curation.json` lockfile records the plugin SHA + version + schema
vintage used at init for reproducibility.

## License

MIT
