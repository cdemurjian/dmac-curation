# dmac-curation

A Claude Code plugin for curating research-project metadata into NExtSEEK / FairDomHub.

**Status:** v0.1.0 — initial release.

## What it does

Drives the 13-phase metadata curation pipeline used by the MIT DMAC team:

1. **Init** — scaffold a project working directory
2. **Inventory** — `FILE_INDEX.md` from PI inputs
3. **Sample tree** — `SAMPLE_TREE.md` mapping manuscript narrative to NExtSEEK sample types
4. **Questions** — running `QUESTIONS_FOR_PI.md`
5. **Build** — per-arm upload sheets (4-sheet xlsx)
6. **Consolidate** — collapse to flat-format batch-upload sheets
7. **Resolve assays** — fetch project assays via NExtSEEK API, cache + curate synonyms
8. **(Synonyms)** — LLM-curated `context/assay_synonyms.json`
9. **QA** — CLEAN / SOFT_FLAG / HARD_REJECT disposition
10. **Deposit** — GEO / Zenodo / OMERO with URL backfill
11. **Retrieve** — emit `RETRIEVE.TXT` for `chat_nextseek` retrieve function
12. **Validate** — round-trip diff vs. downloaded `*_AllMetadata.xlsx`
13. **Email** — draft `EMAIL_TO_PI.md` (skeleton-first, Name-pattern anchors)

Each phase has a corresponding slash command (`/curate-init`, `/curate-inventory`, ...).

## Repo layout

```
dmac-curation/
├── .claude-plugin/plugin.json
├── skills/curation/{SKILL.md, PHASES.md}
├── commands/curate-*.md          # 13 slash commands
├── scripts/                      # PEP 723 inline-deps, uv-runnable
├── context/                      # frozen NExtSEEK schema snapshots
├── templates/                    # .md.j2 + config.j2 rendered into cwd
└── docs/superpowers/{specs,plans}/
```

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

Per-project `.dmac-curation.json` lockfile records the plugin SHA + schema vintage used at init for reproducibility.

## Secrets

All secrets (`.env`, NExtSEEK credentials, MIT SMB credentials, GEO NCFTP tokens) live in **per-project `.env` files**, never in the plugin and never in git. See `.gitignore` for the full exclusion list.

## License

MIT
