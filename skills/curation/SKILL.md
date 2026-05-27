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
| 3 | Questions | `/curate-questions [add\|list\|resolve]` | `QUESTIONS_FOR_PI.md` |
| 4 | Task plan | (uses TaskCreate, no command) | TaskList state |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}.xlsx` (flat format) |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` |
| 8 | Synonyms | (LLM-driven in Phase 7) | `context/assay_synonyms.json` |
| 9 | QA | `/curate-qa` | console disposition report |
| 10 | Deposit | `/curate-deposit <geo\|zenodo\|omero>` | external uploads + `Link_PrimaryData` backfilled |
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
