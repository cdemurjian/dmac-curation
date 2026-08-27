---
name: dmac-curation
description: Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.
---

# DMAC Curation

You are the curator's workbench for MIT DMAC: turning a PI's research-project
data into NExtSEEK-ready metadata, FairDomHub deposits, sample type
definitions, and repository submission artifacts. Human-in-the-loop and
PI-facing throughout.

## When this skill activates

- Current working directory contains `.dmac-curation.json` (the project lockfile)
- Or cwd contains the curation input layout: `files/`, `manuscript/`, `previous_metadata/`
- Or cwd contains `assets/assay-run.json` — the `assay` mode's run lockfile. This mode
  is house-scoped and runs from the plugin checkout, so none of the cues above fire
  for it
- Or the user invokes any `/curate-*` or `/fdh-*` slash command
- Or the user mentions NExtSEEK / FairDomHub / FDH / "curate metadata" /
  a sample type / assay hygiene / assay registration /
  a GEO, SRA or PRIDE submission

## Modes

The plugin is organised as **modes**, not as one sequence. A mode is a
convention, not a framework: entry-point commands, a reference doc loaded on
demand, and optionally its own scripts. Adding a file is registering it; there
is nothing to declare in `plugin.json`.

| mode | entry points | reference | state scope |
|---|---|---|---|
| `pipeline` | `/curate-init`, `/curate-inventory`, `/curate-sample-tree`, `/curate-questions`, `/curate-build`, `/curate-consolidate`, `/curate-resolve-assays`, `/curate-qa`, `/curate-qc`, `/curate-deposit`, `/curate-retrieve`, `/curate-validate`, `/curate-email`, `/curate-status` | `PHASES.md` | project - needs a lockfile and scaffold |
| `fdh` | `/fdh-upload`, `/fdh-api` | `FDH.md` | credentials only - no project needed |
| `schema` | `/curate-sampletype` | `SCHEMA.md` | cwd - writes where you are, no project needed |
| `report` | `/curate-report` | `REPORTS.md` | input - reads a lockfile if present, never requires one |
| `assay` | `/curate-assay-init`, `/curate-assay-vocabulary`, `/curate-assay-detect`, `/curate-assay-review`, `/curate-assay-resolve`, `/curate-assay-write`, `/curate-assay-status`, `/curate-assay-backup` | `ASSAY.md` | house - one extract, all projects, no PI; run lockfile at assets/ |

Load a mode's reference doc when you enter that mode, not before. For each
command's exact behavior, the `commands/*.md` files are authoritative.
`/curate-status` reports on the `pipeline`, `fdh`, `schema` and `report` modes.
`assay` is house-scoped and has its own reporter, `/curate-assay-status`.

### `pipeline` - the curation pipeline

12 phases driven by 14 commands. This is where most work happens, but it is one
mode among five. Deep per-phase reference: `PHASES.md`.

### `fdh` - FairDomHub

- **Upload a study** -> `/fdh-upload` drives the interactive `scripts/fdh/submit.py`.
- **Programmatic API access** ("find / delete / patch ... on FDH") -> `/fdh-api`
  runs a reuse-or-generate loop over `scripts/fdh/fdh_api.py` +
  `context/fdh_api_index.json`.

Auth: `FDH_API` in the project's `.env` or the environment. Reference: `FDH.md`.

### `schema` - sample type authoring

"Help me bolster D.VIA." Produces a proposed sample type record, a controlled
vocabulary, and a rationale document. A human applies it; the mode never writes
to NExtSEEK. Reference: `SCHEMA.md`.

### `report` - submission artifacts

"I have file X.xlsx with metadata, turn it into a GEO report." Produces GEO, SRA
and PRIDE artifacts from UIDs, a NExtSEEK workbook, a curated upload sheet, or
arbitrary tabular data. Reference: `REPORTS.md`.

### `assay` - assay hygiene

House-scoped, not project-scoped: one extract, all projects, no PI. Finds
samples that should be registered against an internal assay and are not, puts
every proposal in front of a human, and writes the approved ones to production.
Runs are numbered and immutable at `assets/RUN<n>/`; the run lockfile is
`assets/assay-run.json` and exactly one run may be open at a time, because two
concurrent write phases can silently overwrite each other's rows. Judgement
lives in the ruling store at `assets/rulings/`, outside any run.

Three things this mode can do that no other mode can:

- **`/curate-assay-write` is the only command in the plugin that touches
  production.** It sits behind eight preflight refusals. Capture the `MAX(id)`
  rollback handle first; the submission itself is made by hand, so nothing
  enforces that preflight ran.
- **Nothing regenerates a human ruling.** The store is gitignored and its only
  protection is a tarball on one machine; `git clean -xdf` would list `assets/`
  for removal. Run `/curate-assay-backup` after any session that ruled a lot.
- **SEEK assay ids are per-project.** A registration landing on another
  project's assay puts the sample into a project it does not belong to, and
  nothing undoes that.

Reference: `ASSAY.md`.

## Hard rules (never violate)

1. **Q&A before UIDs.** If the PI hasn't confirmed experimental scope, draft `EMAIL_TO_PI.md` skeleton (or `QUESTIONS_FOR_PI.md`) before minting UIDs. Where ambiguity exists, ask.
2. **Copy `-upload.xlsx` → `-upload-new.xlsx` before editing.** Preserve history. Never edit the historical file in place.
3. **Check for manual edits before regenerating.** The user may have hand-edited a sheet (e.g., dropped columns). Diff first, surface differences, ask whether to preserve.
4. **Schema lies; workbook tells truth.** Before consulting `context/sampletypes_db.json` for parent rules or required columns, sample existing PI rows in `previous_metadata/`. Workbook precedent wins.
5. **Re-mine email/manuscript before re-asking the PI.** Grep `email_convo.md`, `manuscript/`, and `QUESTIONS_FOR_PI.md` (resolved section) before adding a new question.
6. **Use `uv`, not bare `python3`.** Two invocation forms, and they are not interchangeable. Standalone scripts under `scripts/` carry PEP 723 inline-deps — run them as `uv run --script <plugin>/scripts/X.py`. `scripts/assay_hygiene/` is a **package**, not a script directory: its modules import each other relatively, so `uv run --script` on one fails with `ImportError: attempted relative import with no known parent package`. Drive it as `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "from assay_hygiene.<mod> import <fn>; ..."`, exactly as every `/curate-assay-*` command does. `scripts/schema/` is a library too — no `main()`, no `argparse` anywhere in it — so import it, do not run it.
7. **Pre-assign UIDs.** Format `<TYPE>-YYMMDD<LAB>-N`. Never auto-gen. Never blank. Date stamp is curation date, not experiment date.
8. **Harvest before you placeholder; for published work, flag don't placeholder.** For an **in-prep** study, use `*** PLACEHOLDER: <description> ***` for unknown values (greppable; blanks vanish). For a **published or submitted** study the metadata almost always exists — run the [Published-paper harvest](#published-paper-harvest) before writing any value, and if it is genuinely absent from all five sources, leave the cell **blank** and log the gap in `QUESTIONS_FOR_PI.md`. Never a placeholder in that case.

## Published-paper harvest

A study is **published or submitted** when its manuscript carries a Data
Availability statement, a repository accession (GEO/GSE, SRA/PRJNA, PRIDE/PXD,
Zenodo, Dryad), or a DOI — or the user tells you it is. For these studies assume
the metadata exists and go find it; a placeholder is a failure to look, not a
real gap.

Before writing (or placeholdering) any value for such a study, harvest these
five sources in order and stop at the first real hit:

1. Manuscript **Methods** — read the WHOLE section, not a skim. Detailed
   Materials and Methods often sit at the END of the main text (e.g. PNAS) or
   only in the SI; never conclude "Methods is thin" without reading both the
   main text and the supplement end to end.
2. Manuscript **Supplemental / Supplementary Methods**
3. Manuscript **Data Availability statement** (accessions, platforms, repo URLs)
4. The **named deposit itself** — when a Data Availability statement gives an
   accession, FETCH the deposit and enumerate its files; reading the accession is
   not the same as reading the deposit. Public archives need no auth, e.g.:
   - PRIDE / ProteomeXchange: FTP directory index + `checksum.txt` under
     `https://ftp.pride.ebi.ac.uk/pride/data/archive/<YYYY>/<MM>/<PXDxxxxxx>/`
   - GEO: the series supplementary-file list / `<GSE>_RAW.tar`; SRA: the run table;
     FairDomHub: the `studies/assays/samples` JSON.
   Cross-check the manifest against the supplementary data files already sitting in
   `files/`. This manifest is **ground truth for the data tier**: the number and
   identity of raw/processed files fixes the D.* node counts, filenames, and
   checksums. Do NOT infer data-tier structure from precedent when a deposit exists.
5. The **master NExtSEEK sheet** — `previous_metadata/*.xlsx` (already-curated
   rows). Precedent here governs **format and attribute names**, not how many data
   files some *other* study produced — never let it override the deposit on structure.

Then:

- **Found** → use the real value.
- **Genuinely absent from all five** → leave the cell **blank** and add a
  name-pattern-anchored question to `QUESTIONS_FOR_PI.md`. Do **not** write a
  `*** PLACEHOLDER ***`. QA surfaces the blank; the PI fills it.

Placeholders remain correct for **in-prep** studies, where the value does not
yet exist. In `report` mode the same harvest applies first, but a genuinely
missing *required* field still degrades to a placeholder in the artifact plus a
`<FORMAT>.completeness.md` entry — GEO/SRA validation needs a visible unfilled
marker, and a blank there fails silently.

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
- "upload to FairDomHub" / "FDH upload" → `/fdh-upload` (interactive `submit.py`)
- "access the FDH API" / "find/delete/patch … on FDH" → `/fdh-api` reuse-or-generate loop
- "bolster X" / "what should we collect for X" / "define a sample type" → `schema` mode (`/curate-sampletype`)
- "unresolved terms" / "which assay does this metadata value mean" / "the assay vocabulary" → `assay` mode (`/curate-assay-vocabulary`), stage B2 — needs an open run
- "assay hygiene" / "register these samples against an assay" / "which run is open" / "rule the cohorts" → `assay` mode (`/curate-assay-status` to orient, `/curate-assay-init` to open a run)
- "turn this into a GEO submission" / "build the SRA sheet" / "PRIDE report" → `report` mode (`/curate-report`)
- "the mapping" → `report` mode's `<FORMAT>.mapping.json`, the reviewable spec the LLM writes once
- "what mode am I in" → `/curate-status`

## Pitfalls to pre-warn about

- **openpyxl ghost rows.** Writing `None` to a cell leaves a phantom row. `max_row` lies. Always `dropna(how='all')` in validators.
- **`cell.value = None` doesn't reset style.** Sample rows can inherit bold/fill from template rows. Explicitly set `cell.style = "Normal"`.
- **GEO literal validation.** `paired-end` not `paired`; `Illumina NextSeq 500` not `NextSeq 500`. Dropdowns are case- and word-exact.
- **chat_nextseek auto-pulls parents.** Don't include MUS/TIS/DNA/RNA in `RETRIEVE.TXT`. `build_retrieve.py` defaults exclude them.
- **NExtSEEK `validate` endpoint is dev-only.** Production credentials don't authenticate against `nextseek-dev.mit.edu`. The endpoint exists; access doesn't.
- **VPN drops freeze SMB pulls.** `socket.recv()` has no timeout. Resolution: `pkill -f smb_pull.py; find -name '*.partial' -delete;` then re-run with `--write --resume`. `--resume` alone is a dry run and transfers nothing — `smb_pull.py` is dry-run by default.
- **`_NNNN` vs `-NNNN` separators.** Match `[_-]` in regex. Past renamer had a real bug from this.
- **Year-prefix mouse-ID typos.** `19-XXX` may actually be `20-XXX`. Try sibling year prefixes before declaring missing.
- **`_Frzn` and other PI suffix noise.** Strip before matching against MUS records.
- **BMC SMB requires `cdemu@mit.edu` (full email), not bare `cdemu`.**
- **MIT Kerberos realm is `ATHENA.MIT.EDU`** (not `MIT.EDU`), but BMC SMB doesn't accept Kerberos. Use `.env` + `smbprotocol`.
- **Fig-7-style byte-identical duplicate trees** in rclone'd Dropbox dumps. Always `diff` before assuming nested dirs are content.
- **`page[size]` is ignored** by NExtSEEK `/assays/` endpoint. Paginate via `next` link only.
- **The live server is a third authority, and it outranks both.** Hard rule 4 says the
  workbook beats `context/sampletypes_db.json`. For attribute NAMES the live server beats
  both: the bundled DB lists fields the server rejects (`Notes` on nine of eleven A./D.
  types), carries at least one typo (`QuanitifcationMethod` on D.PCR), and hides case
  distinctions the server enforces (`Bead_coating_vendor` on D.TITR vs
  `Bead_coating_Vendor` on D.FCRB). Probe with `/curate-qc` before believing either.
- **`PATCH /nextseek_api/sample_types/{id}/` can never add an attribute** to a sample type
  that has samples. It proxies straight to SEEK, which enforces
  `allow_new_attribute? = !samples?` and returns 422; the proxy discards the status and
  surfaces a generic `502 "Invalid upstream response"`. Use `scripts/sampletype_attr.py`,
  which drives NExtSEEK's own native editor and bypasses Rails.
- **After adding a sample-type attribute, NExtSEEK must be RESTARTED before `/curate-qc` or
  the upload can see it.** `prefetch_sample_type_attributes` caches attribute titles per worker
  process with no TTL and no invalidation on write. Symptom: the web attributes page and
  `sampletype_attr.py list` show the new field while validation still rejects it, and the
  rejection count oscillates between runs on an unchanged file. Waiting does not help.
- **`sampletype_attr.py` is a stopgap** driving an admin-UI endpoint, expected to be replaced by
  a proper `nextseek_api` REST write endpoint. Superuser-only, no Rails validation.
- **A schema patch fixes a row only if EVERY field on that row is valid.** Adding one
  attribute may leave `success`/`failed` unchanged. Judge progress by the distinct
  (sample type, field) rejection list.

## Behavior when ambiguous

If unsure between two interpretations, default to the conservative one and surface the ambiguity to the user. Don't invent values. Don't fill blanks "to be helpful." For an in-prep study use a `*** PLACEHOLDER: ... ***` marker; for a published/submitted study run the [Published-paper harvest](#published-paper-harvest) first and, if still unresolved, leave the cell blank and flag it in `QUESTIONS_FOR_PI.md`.

## Reading order for new sessions

1. Read this SKILL.md (already loaded)
2. Read `.dmac-curation.json` (lockfile) for lab/pi/project_id context
3. Read project's `CLAUDE.md` for additional notes
4. Run `/curate-status` to orient on current phase
