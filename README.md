# dmac-curation

A Claude Code plugin for curating research-project metadata into NExtSEEK / FairDomHub.

**Status:** Design phase. The spec lives at [`docs/superpowers/specs/2026-05-27-dmac-curation-plugin-design.md`](docs/superpowers/specs/2026-05-27-dmac-curation-plugin-design.md). Implementation plan and code to follow.

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
├── skills/curation/{SKILL.md, PHASES.md, examples/}
├── commands/curate-*.md          # 13 slash commands
├── scripts/                      # PEP 723 inline-deps, uv-runnable
├── context/                      # frozen NExtSEEK schema snapshots
├── templates/                    # .md.j2 + config.j2 rendered into cwd
└── docs/superpowers/{specs,plans}/
```

## Installation (forthcoming)

```bash
git clone git@github.com:cdemurjian/dmac-curation.git ~/.claude/plugins/dmac-curation
```

Claude Code auto-discovers `.claude-plugin/plugin.json`. Slash commands and the skill become available in any session.

## Updates

```bash
cd ~/.claude/plugins/dmac-curation && git pull
```

Per-project `.dmac-curation.json` lockfile records the plugin SHA + schema vintage used at init.

## Secrets

All secrets (`.env`, NExtSEEK credentials, MIT SMB credentials, GEO NCFTP tokens) live in **per-project `.env` files**, never in the plugin and never in git. See `.gitignore` for the full exclusion list.

## License

MIT
