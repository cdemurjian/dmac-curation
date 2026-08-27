# Ground-truth inventory — `skills/curation/` reference docs

Scope: the 6 files in `skills/curation/`. Worktree
`/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`, branch `dev-docs`,
HEAD `833e9be`. Every assertion below was read out of the file or the code cited. Line
numbers are 1-indexed and were taken from this worktree at this SHA.

Paths in this document are repo-relative to the worktree root unless prefixed.

---

## 0. Size and shape

| file | lines | bytes | covers |
|---|---|---|---|
| `skills/curation/SKILL.md` | 196 | 14016 | plugin entry point; mode table; hard/soft rules; pitfalls |
| `skills/curation/PHASES.md` | 506 | 25854 | `pipeline` mode, per-phase contract |
| `skills/curation/FDH.md` | 107 | 4733 | `fdh` mode, two modules |
| `skills/curation/SCHEMA.md` | 230 | 11034 | `schema` mode |
| `skills/curation/REPORTS.md` | 174 | 7933 | `report` mode |
| `skills/curation/ASSAY.md` | 72 | 3597 | `assay` mode |

`SKILL.md` is the only one with YAML frontmatter (`SKILL.md:1-4`).

---

## 1. Ground truth: the command set

`ls commands/*.md` = **26 files**, exact set (basenames, `.md` stripped):

```
curate-assay-backup    curate-assay-detect    curate-assay-init      curate-assay-resolve
curate-assay-review    curate-assay-status    curate-assay-vocabulary curate-assay-write
curate-build           curate-consolidate     curate-deposit         curate-email
curate-init            curate-inventory       curate-qa              curate-qc
curate-questions       curate-report          curate-resolve-assays  curate-retrieve
curate-sample-tree     curate-sampletype      curate-status          curate-validate
fdh-api                fdh-upload
```

Breakdown: 14 pipeline + 2 fdh + 1 schema + 1 report + 8 assay = 26.

**SKILL.md's mode table (`SKILL.md:28-34`) matches this set exactly — all 26 commands,
no extras, no missing.** Verified name by name. The mode table is the one part of SKILL.md
that is current with the `assay` mode.

Manifest version: `0.4.0` (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`).

---

## 2. Mode ↔ reference doc coverage

| mode | reference doc | doc exists | entry points listed at |
|---|---|---|---|
| `pipeline` | `PHASES.md` | yes | `SKILL.md:30` (14 commands) |
| `fdh` | `FDH.md` | yes | `SKILL.md:31` (2) |
| `schema` | `SCHEMA.md` | yes | `SKILL.md:32` (1) |
| `report` | `REPORTS.md` | yes | `SKILL.md:33` (1) |
| `assay` | `ASSAY.md` | yes | `SKILL.md:34` (8) |

**Every mode has a reference doc.** `skills/curation/` contains exactly these 5 + SKILL.md;
no orphan doc, no missing doc. Enforced by `tests/test_mode_table.py:44-62`
(`EXPECTED_MODES` at `tests/test_mode_table.py:13-19` already names `assay: ASSAY.md`).

Design-doc backlinks: `SCHEMA.md:4` → `docs/superpowers/specs/2026-07-21-schema-mode-design.md`
(exists); `REPORTS.md:4` → `docs/superpowers/specs/2026-07-21-report-mode-design.md` (exists).
`ASSAY.md` has **no** design-doc backlink although
`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` exists. `PHASES.md` and
`FDH.md` have none either.

---

## 3. Section outlines

### SKILL.md
```
6   # DMAC Curation
13  ## When this skill activates
21  ## Modes            (table at 28-34)
40  ### `pipeline` - the curation pipeline
45  ### `fdh` - FairDomHub
54  ### `schema` - sample type authoring
60  ### `report` - submission artifacts        <-- NO `### assay` subsection
66  ## Hard rules (never violate)              (8 numbered rules, 68-75)
77  ## Published-paper harvest
122 ## Soft rules (apply with judgment)
132 ## Vocabulary the user uses
150 ## Pitfalls to pre-warn about
187 ## Behavior when ambiguous
191 ## Reading order for new sessions
```

### PHASES.md
```
1   # Phase reference for dmac-curation
7   ## Phase table        (11 numbered rows at 19-29; Phase 0 table at 36-38)
40  ### Retired phases
54  ## What an "arm" is
78  ### When to split into separate arms
92  ## Phase 0 — Init
117 ## Phase 1 — Inventory
139 ## Phase 2 — Sample tree
171 ## Phase 3 — Questions
186 ### Task-plan guidance (formerly Phase 4)
195 ## Phase 5 — Build
204 ### The 4-sheet output is a review artifact, not a build intermediate
223 ### The Ontology sheet is where controlled vocabulary lives
263 ## Phase 6 — Consolidate
273 ### Flat cannot carry controlled vocabulary
317 ## Phase 7 — Resolve assays
335 ### `assay_synonyms.json` (formerly Phase 8)
353 ## Phase 9 — QA
374 ## Phase 9b — QC (server-side validation)
408 ## Phase 10 — Deposit
414 ### `/curate-deposit geo [--type bulk|spatial]`
420 ### `/curate-deposit zenodo [--record-id N]`
427 ### `/curate-deposit omero [--project-id N]`
442 ## Phase 11 — Retrieve
460 ## Phase 12 — Validate
480 ## Phase 13 — Email
499 ## Phase any — Status
```

### FDH.md
```
1   # FairDomHub (FDH) integration — reference
11  ## Module 1 — Upload a study (`/fdh-upload`)
23  ## Module 2 — Programmatic API access (`/fdh-api`)
39  ### The shared client
50  ### Generated-script template (dry-run first, always)
99  ## Safety (hard rules)      (3 bullets, 101-107)
```
(Headings at FDH.md:53-56 are `#` comment lines inside the fenced PEP 723 block, not sections.)

### SCHEMA.md
```
1   # `schema` mode - sample type authoring
6   ## Purpose
16  ## State scope
21  ## Scope: ontology grounding, not CEDAR templates
28  ### Why templates are out of scope: tree vs graph
50  ## Modules            (5-row table at 52-58)
60  ## The reuse check
74  ## The Ontology sheet - the shortest path to value
94  ### Enforcement exists only in 4-sheet
110 ## External clade evidence
138 ## The reference template checklist
180 ## The field dictionary
203 ## BioPortal - suggests, never binds
216 ## Non-goals            (5 bullets)
224 ## Open question
```

### REPORTS.md
```
1   # `report` mode - submission artifact generation
6   ## Purpose
14  ## State scope
19  ## Formats            (3-row table at 21-25)
36  ## The mapping spec - the core of the design
55  ## Input adapters     (4-row table at 60-65)
77  ## Two-stage validation
93  ## Graceful degradation
115 ## No LLM API client
124 ## Protocol-chain gotchas
136 ## Modules            (7-row table at 138-146)
148 ## Relationship to Phase 10
160 ## Non-goals
168 ## Open question
```

### ASSAY.md
```
1   # Assay hygiene mode
7   ## The run model
13  ## The ruling store
30  ## Commands           (8-row table at 32-41)
43  ## The carry-forward split
55  ## Four things that will bite
```

---

## 4. Numbered rules and invariants

### SKILL.md hard rules — 8, `SKILL.md:68-75`
1. `:68` Q&A before UIDs — draft `EMAIL_TO_PI.md` / `QUESTIONS_FOR_PI.md` before minting.
2. `:69` Copy `-upload.xlsx` → `-upload-new.xlsx` before editing.
3. `:70` Check for manual edits before regenerating; diff first.
4. `:71` "Schema lies; workbook tells truth" — `previous_metadata/` beats `context/sampletypes_db.json`.
5. `:72` Re-mine email/manuscript before re-asking the PI.
6. `:73` Use `uv`, not bare `python3`; all scripts PEP 723; `uv run --script <plugin>/scripts/X.py`.
7. `:74` Pre-assign UIDs, format `<TYPE>-YYMMDD<LAB>-N`; never auto-gen, never blank; date = curation date.
8. `:75` Harvest before you placeholder; published work → blank + question, not placeholder.

Cross-references to rule numbers elsewhere: `PHASES.md:243` ("hard rule 4"),
`PHASES.md:313` ("hard rule 2"), `PHASES.md:366` ("skill rule 8"), `SCHEMA.md:47`
("hard rule 4"), `REPORTS.md:103` ("hard rule 8"). All five point at the rule that is
actually at that number.

### SKILL.md soft rules — 7 bullets, `SKILL.md:124-130`
Includes `:128` "`File_PrimaryData` is genuinely required; `Link_PrimaryData` and
`Checksum_PrimaryData` are not enforced by the server" and `:130` "D.IMG.Parent follows PI
precedent."

### SKILL.md pitfalls — 20 bullets, `SKILL.md:152-185`
Numerically/structurally checkable ones: `:155` `build_retrieve.py` default excludes parents;
`:157` `smb_pull.py` is dry-run by default; `:164` `page[size]` ignored by `/assays/`;
`:168-170` bundled DB lists fields the server rejects (`Notes` on nine of eleven A./D. types),
one typo (`QuanitifcationMethod` on D.PCR), case distinctions (`Bead_coating_vendor` on D.TITR
vs `Bead_coating_Vendor` on D.FCRB); `:171-175` `PATCH /nextseek_api/sample_types/{id}/` cannot
add an attribute to a type with samples (422 → surfaced as 502).

### Published-paper harvest — `SKILL.md:77-120`
`SKILL.md:86` says **five** sources; the numbered list `SKILL.md:88-107` has 5 entries
(Methods / Supplemental / Data Availability / the named deposit / master NExtSEEK sheet).

### FDH.md safety hard rules — 3, `FDH.md:101-107`
Dry-run default + `--write` + interactive confirm; review-then-commit for generated scripts;
credentials from `.env` only, `Assets/Output/session.json` holds a plaintext token.

### PHASES.md invariants
- `PHASES.md:9-13` "14 commands drive 12 phases"; 9 splits into 9a/9b; 4 and 8 retired as
  numbers; **surviving numbers deliberately not renumbered** (three stated reasons).
- `PHASES.md:15` "The 11 pipeline phases run inventory (1) through email (13)."
- `PHASES.md:50` "Neither number is reused."
- `PHASES.md:33-34` Phase 0 is the init step, not one of the 11.
- `PHASES.md:204-221` the 4-sheet output is a review artifact, not a build intermediate.
- `PHASES.md:273-302` flat format cannot carry controlled vocabulary; the "verify before
  relying on this" flag names the bundle date **2026-05-27** (`PHASES.md:300`).
- `PHASES.md:348-350` assay IDs are project-scoped.
- `PHASES.md:404` "A sample-type patch is a GLOBAL write."

### ASSAY.md invariants
- `:9-11` runs numbered and immutable at `assets/RUN<n>/`, tiers `00`–`06` read-only from
  creation; state `assets/assay-run.json`; one run open at a time.
- `:15-17` ruling store at `assets/rulings/`, keyed `(sample_type, internal_assay_id, action)`.
- `:19-22` RUN1 key was `lab|sample_type|parent_types|assay_title|field|value`; four of six
  move with the extract; 261 rulings became worthless.
- `:24-28` 200 ruled rows → 127 keys, 5 disagreed; excluded, not resolved; "Lab was the
  discriminator in three of the five, which is the measured cost of dropping it from the
  key: 3.9%."
- `:45-47` three-way carry-forward split: carried / widened / never seen.
- `:49-53` RUN1: 2,830 rows below the precedent floor; unknown ruled width counts as widened.
- `:57-72` four hazards (default paths / nothing regenerates a ruling / the DB is the only
  receipt / SEEK assay ids are per-project).

---

## 5. Command mentions, by doc and line

| doc | commands named (line) |
|---|---|
| SKILL.md | `:17` glob `/curate-*`, `/fdh-*`; `:30` all 14 pipeline; `:31` `/fdh-api`, `/fdh-upload`; `:32` `/curate-sampletype`; `:33` `/curate-report`; `:34` all 8 `/curate-assay-*`; `:38` `/curate-status`; `:47` `/fdh-upload`; `:48` `/fdh-api`; `:142-148` vocabulary mappings; `:170` `/curate-qc`; `:176` `/curate-qc`; `:196` `/curate-status` |
| PHASES.md | `:9` `/curate-qa`; `:10` `/curate-qc`; `:13,:70,:501` `/curate-status`; `:19-29` table; `:33,:38,:94` `/curate-init`; `:69` `/curate-build <arm>`; `:119` `/curate-inventory`; `:141` `/curate-sample-tree`; `:173` `/curate-questions`; `:197` `/curate-build`; `:265` `/curate-consolidate`; `:311` `/curate-resolve-assays`; `:319` `/curate-resolve-assays --project-id N`; `:355` `/curate-qa`; `:376` `/curate-qc`; `:387` `/curate-sampletype apply <TYPE> --add <FIELD>`; `:410,:414,:420,:427` `/curate-deposit`; `:416` `/curate-report GEO <input>`; `:444` `/curate-retrieve [--include-parents]`; `:455` `/curate-build`+`/curate-consolidate`; `:462` `/curate-validate <metadata.xlsx>`; `:482` `/curate-email` |
| FDH.md | `:11` `/fdh-upload`; `:23` `/fdh-api` |
| SCHEMA.md | **none** — the doc never names `/curate-sampletype` |
| REPORTS.md | `:150` `/curate-deposit geo`. Never names `/curate-report`. |
| ASSAY.md | `:34-41` all 8, written **without** the leading slash (`curate-assay-init`, …) |

`/curate-sampletype apply <TYPE> --add <FIELD>` (`PHASES.md:387`) is the only invocation
naming a `curate-sampletype` subcommand; `commands/curate-sampletype.md` is the authority.

---

## 6. Script / context / template paths named, and whether they exist

### SKILL.md
| line | path | exists |
|---|---|---|
| 47 | `scripts/fdh/submit.py` | yes (82357 B) |
| 49 | `scripts/fdh/fdh_api.py` | yes |
| 50 | `context/fdh_api_index.json` | yes |
| 71 | `context/sampletypes_db.json` | yes |
| 73 | `<plugin>/scripts/X.py` (pattern) | n/a |
| 174 | `scripts/sampletype_attr.py` | yes |

### PHASES.md
| line | path | exists |
|---|---|---|
| 22 | `scripts/build_<arm>.py` | project-local, generated; not in plugin |
| 24 | `context/assay_ids_cache.json`, `context/assay_synonyms.json` | project-local outputs |
| 102 | `files/ manuscript/ previous_metadata/ assay_sheets/ scripts/` | scaffold targets |
| 104 | `scripts/_lockfile.py` | yes |
| 126 | `scripts/inspect_workbook.py` | yes |
| 129 | `templates/FILE_INDEX.md.j2` | yes |
| 143 | `context/sampletypes_db.json`, `context/assays_db.json` | both yes |
| 152 | `templates/SAMPLE_TREE.md.j2` | yes |
| 156 | `scripts/build_sample_tree_html.py` | yes |
| 249 | `scripts/_project_constants.py.example` | yes |
| 275, 300 | `context/NExtSEEK_API.yaml` | yes (278299 B) |
| 305 | `scripts/consolidate_to_flat.py` | yes |
| 324, 381 | `scripts/nextseek_api.py` | yes |
| 360 | `scripts/qa_flat_sheets.py` | yes |
| 403 | `context/live_sampletype_attributes.json` | project-local output; **not** in plugin `context/` |
| 417 | `scripts/upload_geo_ncftp.sh` | yes |
| 418 | `scripts/apply_geo_accessions.py` | yes |
| 422 | `scripts/stage_zenodo.py` | yes |
| 425 | `scripts/apply_zenodo_links.py` | yes |
| 430 | `scripts/omero_pull.py` | yes |
| 431 | `scripts/apply_omero_ids.py` | yes |
| 449 | `scripts/build_retrieve.py` | yes |
| 467 | `scripts/review_metadata_vs_uploads.py` | yes |
| 488 | `templates/EMAIL_TO_PI.md.j2` | yes |
| 296, 418 | `commands/curate-deposit.md` | yes |

Phase-0 template renders named at `PHASES.md:103` (`CLAUDE.md`, `.env.example`, `.gitignore`,
`pyproject.toml`) map to `templates/CLAUDE.md.j2`, `templates/env.example.j2`,
`templates/gitignore.j2`, `templates/pyproject.toml.j2` — all present.

### FDH.md
| line | path | exists |
|---|---|---|
| 13 | `scripts/fdh/submit.py` | yes |
| 14 | `commands/fdh-upload.md` | yes |
| 28, 34 | `scripts/fdh/generated/REGISTRY.md`, `scripts/fdh/generated/` | yes |
| 29 | `context/fdh_api_index.json` | yes (50198 B) |
| 32 | `context/full-fdh-openapi-spec.yaml` ("640 KB") | yes, 640626 B |
| 37 | `scripts/fdh/build_api_index.py` | yes |
| 41 | `scripts/fdh/` (sys.path) | yes |

### SCHEMA.md
| line | path | exists |
|---|---|---|
| 4 | `docs/superpowers/specs/2026-07-21-schema-mode-design.md` | yes |
| 18 | `context/` (read-only) | yes |
| 54 | `scripts/schema/field_index.py` | yes |
| 55 | `scripts/schema/dictionary.py` | yes |
| 56 | `scripts/schema/ontology.py` | yes |
| 57 | `scripts/schema/terms.py` | yes |
| 58 | `scripts/schema/review.py` | yes |
| 106 | `context/NExtSEEK_API.yaml` | yes |

`scripts/schema/` also contains `templates.py` (5478 B), **absent from the module table**
though its API is discussed at `SCHEMA.md:138-178`.

### REPORTS.md
All 7 rows of the module table (`REPORTS.md:140-146`) exist: `adapters.py`, `enrich.py`,
`protocols.py`, `mapping.py`, `execute.py`, `render.py`, `validate_artifact.py`.
`scripts/report/scrub_fixture.py` exists and is not listed (test-fixture utility).
`REPORTS.md:44` cites `reports/outputs.py:349-355` — that is **chat_nextseek**, an external
repo; unverifiable from here. Same for `REPORTS.md:164`.

### ASSAY.md
**Names zero file paths.** It refers to code by bare identifier only: `run_evidence`,
`run_detect` (`:57`), `_writeguard` (`:59`), `storeOneRecord` (`:66`). All three modules
live at `scripts/assay_hygiene/run_evidence.py`, `run_detect.py`, `_writeguard.py`;
`storeOneRecord` is NExtSEEK server-side and not in this repo.

---

## 7. Artifact filenames named, by doc

| artifact | named at |
|---|---|
| `FILE_INDEX.md` | SKILL n/a; `PHASES.md:19,:129,:134` |
| `SAMPLE_TREE.md` | `SKILL.md:124`; `PHASES.md:20,:152,:158,:199,:241,:484` |
| `sample_tree.json` | `PHASES.md:153,:158` |
| `SAMPLE_TREE.html` | `PHASES.md:156,:159` |
| `QUESTIONS_FOR_PI.md` | `SKILL.md:68,:72,:113,:189`; `PHASES.md:21,:174,:244,:257,:259,:484` |
| `EMAIL_TO_PI.md` | `SKILL.md:68,:138`; `PHASES.md:29,:488` |
| `assay_sheets/4sheet_originals/*.xlsx` | `PHASES.md:22,:65,:201,:251,:267` |
| `assay_sheets/Arm{X}-upload.xlsx` | `PHASES.md:23,:66,:269,:313`; `REPORTS.md:64` |
| `assay_sheets/pending_schema/Arm<X>.xlsx` | `PHASES.md:258,:312` |
| `*-upload-new.xlsx` | `SKILL.md:69`; `PHASES.md:313,:446,:455` |
| `context/assay_ids_cache.json` | `PHASES.md:24,:325,:342` |
| `context/assay_synonyms.json` | `PHASES.md:24,:267,:327,:335,:344` |
| `RETRIEVE.TXT` | `SKILL.md:139,:155`; `PHASES.md:27,:451,:464,:467,:472`; `REPORTS.md:62` |
| `.dmac-curation.json` | `SKILL.md:15,:194`; `PHASES.md:38,:104,:199,:328` |
| `omero_images.csv` | `PHASES.md:430,:436` |
| `Zenodo_upload/` `.zip` | `PHASES.md:423,:425,:438` |
| `context/live_sampletype_attributes.json` | `PHASES.md:403` |
| `Assets/Output/`, `Assets/Output/session.json` | `FDH.md:17,:104,:105` |
| `<TYPE>.review.md` | `SCHEMA.md:58,:230` |
| `<TYPE>.ontology.json` | `SCHEMA.md:56,:88`; `PHASES.md:233,:236` |
| `field_dictionary.json` (entry shape only, unnamed) | `SCHEMA.md:189-201` |
| `GEO_filled.xlsx` / `SRA_metadata_filled.xlsx` / `SRA_biosample_filled.xlsx` / `submission.px` | `REPORTS.md:23-25` |
| `<FORMAT>.mapping.json` | `SKILL.md:147`; `REPORTS.md` (prose, `:52`) |
| `<FORMAT>.completeness.md` | `SKILL.md:119`; `REPORTS.md:106,:111` |
| `pride.json` | `REPORTS.md:27` |
| `assets/RUN<n>/`, `assets/assay-run.json`, `assets/rulings/` | `ASSAY.md:9,:10,:15` |

Cross-check against `commands/curate-sampletype.md:229-235`: that command emits **three**
artifacts — `<TYPE>.review.md`, `<TYPE>.proposed.json`, `<TYPE>.ontology.json`.
`SCHEMA.md` never names `<TYPE>.proposed.json`, although `scripts/schema/review.py:245`
defines `write_proposed_record`.

Cross-check against `commands/curate-report.md:130-139`: the outputs are
`<FORMAT>.mapping.json`, `<FORMAT>.completeness.md`, `<FORMAT>_filled.json`,
`<FORMAT>_filled.xlsx`, `SRA_metadata_filled.xlsx`, `SRA_biosample_filled.xlsx`,
`submission.px`. `REPORTS.md:21-25` omits `<FORMAT>_filled.json`.

`context/report_templates/` holds `GEO_template.xlsx`, `GEO-updated.json`, `pride.json`,
`SRA.json`, `SRA_biosample.xlsx`, `SRA_metadata.xlsx` — `REPORTS.md` names only `pride.json`.

---

## 8. Claim → citation lookup table (checkable claims only)

Legend: **OK** = verified true against code at this SHA. **WRONG** = contradicted.
**STALE** = was true, now contradicted by the `assay` mode landing. **UNSOURCED** = no
in-repo evidence found. **PARTIAL** = true as written but materially incomplete.

### 8.1 Mode / command structure

| # | claim | doc:line | ground truth | verdict |
|---|---|---|---|---|
| C1 | frontmatter: "Modes are pipeline …, fdh …, schema …, report …" | `SKILL.md:3` | five modes exist; `assay` is the fifth (`SKILL.md:34`, `commands/curate-assay-*.md` ×8) | **STALE** |
| C2 | "it is one mode among four" | `SKILL.md:43` | five modes | **STALE** |
| C3 | mode table lists 26 commands across 5 modes | `SKILL.md:28-34` | `commands/` holds exactly those 26 | **OK** |
| C4 | "`/curate-status` reports per mode" | `SKILL.md:38` | `scripts/status.py:183-188` reports `pipeline`, `fdh`, `schema`, `report` only — no `assay` key; `scripts/status.py:8` says "the four modes" | **STALE** |
| C5 | `/curate-assay-vocabulary` belongs to `schema` mode, "the assay-hygiene stage B2 judgment step" | `SKILL.md:145` | `SKILL.md:34` puts it in `assay` mode; `commands/curate-assay-vocabulary.md:5` says "stage B2 of the **assay-hygiene mode**"; `ASSAY.md:35` lists it under assay | **WRONG** (self-contradiction inside SKILL.md) |
| C6 | there is a `### assay` mode subsection | — | `SKILL.md:40,45,54,60` give `pipeline`/`fdh`/`schema`/`report` prose subsections; `assay` has none | **PARTIAL** (table row only) |
| C7 | `/curate-status` reference doc: "all four dmac-curation modes" | `commands/curate-status.md:5` | five | **STALE** (command file, cross-ref) |
| C8 | 14 pipeline commands | `SKILL.md:3,:42`; `PHASES.md:9` | counted 14 at `SKILL.md:30` | **OK** |

### 8.2 Phase numbering

| # | claim | doc:line | ground truth | verdict |
|---|---|---|---|---|
| C9 | "14 commands drive 12 phases" | `PHASES.md:9` | 11 numbered rows (`PHASES.md:19-29`) + 9b = 12 | **OK** |
| C10 | "The 11 pipeline phases run inventory (1) through email (13)" | `PHASES.md:15` | table rows = 1,2,3,5,6,7,9,10,11,12,13 = 11 | **OK**; asserted by `tests/test_mode_table.py:94` |
| C11 | phases 4 and 8 retired, numbers not reused | `PHASES.md:9-13,:40-50` | `tests/test_mode_table.py:82-94`, `tests/test_phases_doc.py:47-50` enforce | **OK** |
| C12 | "NOT part of the **13-phase** NExtSEEK pipeline" | `FDH.md:4` | the pipeline is 12 phases / 11 numbered (`PHASES.md:9,:15`). `tests/test_mode_table.py:100` bans this phrase in SKILL.md but **not** in FDH.md, so it survived | **STALE** |
| C13 | "13-phase NExtSEEK artifacts" | `commands/fdh-upload.md:7` | same | **STALE** (cross-ref) |
| C14 | phases reported by `/curate-status`: 1,2,3,5,6,7,9,10,11,12,13 | `commands/curate-status.md:28` | `scripts/status.py:29-36` matches | **OK** |

### 8.3 Script paths, flags, invocations

| # | claim | doc:line | ground truth | verdict |
|---|---|---|---|---|
| C15 | `scripts/consolidate_to_flat.py --assay-sheets assay_sheets` | `PHASES.md:305` | `scripts/consolidate_to_flat.py:396-399` defines `--assay-sheets` | **OK** |
| C16 | "multiple sample types in one file are only allowed in flat format (`consolidate_to_flat.py:19-21`)" | `PHASES.md:212-213,:296-297` | `scripts/consolidate_to_flat.py:19-21` says exactly that | **OK** — line citation is exact |
| C17 | `scripts/nextseek_api.py fetch-assays --project-id N` | `PHASES.md:324` | `scripts/nextseek_api.py:781-783,:784` | **OK** |
| C18 | `nextseek_api.py validate --project-id N --checks structure,dag,name_check --dump-dir <scratch> <file>` | `PHASES.md:381` | `scripts/nextseek_api.py:845-858` — all four flags exist, `files` is `nargs="+"` | **OK** |
| C19 | `/curate-retrieve [--include-parents]` excludes DNA/RNA/MUS/TIS/PAT/PAV/CHM/CEL by default | `PHASES.md:444,:450`; `SKILL.md:155` | `scripts/build_retrieve.py:22` `PARENT_TYPES = {"MUS","TIS","DNA","RNA","PAT","PAV","CHM","CEL"}`; `:82-84` `--include-parents` | **OK** |
| C20 | retrieve prefers `*-upload-new.xlsx` over `*-upload.xlsx` | `PHASES.md:446` | `scripts/build_retrieve.py:11,:26,:34-38` | **OK** |
| C21 | `review_metadata_vs_uploads.py --metadata-xlsx <xlsx> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`; `--retrieve` defaults to `<project-root>/RETRIEVE.TXT` | `PHASES.md:467,:472` | `scripts/review_metadata_vs_uploads.py:258-275` — all three flags, default documented at `:271-274` | **OK** |
| C22 | `_common.write_4sheet_xlsx` accepts `ontology={field: [values]}` | `PHASES.md:224`; `SCHEMA.md:75` | `scripts/_common.py:188-195`, param at `:193` | **OK** |
| C23 | build script imports `mint_uid, write_4sheet_xlsx, schema_column_order, placeholder` from `_common` | `PHASES.md:248` | `scripts/_common.py:44,:188,:162,:36` — all four exist | **OK** |
| C24 | `sampletype_attr.py` is the way to add an attribute; `nextseek_api` PATCH cannot | `SKILL.md:171-175`; `PHASES.md:387` | `scripts/sampletype_attr.py` exists; `scripts/nextseek_api.py:876-878` help = "RETIRED - cannot work. Use scripts/sampletype_attr.py instead." | **OK** |
| C25 | FDH client methods `get, search, page_through, list_related, whoami, post, patch, delete, download_blob`, plus `make_client` | `FDH.md:114-116,:138` | `scripts/fdh/fdh_api.py:101,104,110,121,135,147,150,153,138`; `make_client` at `:198` | **OK** — all 10 |
| C26 | submit.py writes CSVs to `Assets/Output/`; `PROJECT_MAPPING` holds project IDs; `--resume`/`--step N` | `FDH.md:17,:21` | `scripts/fdh/submit.py:85` `OUTPUT_DIR = "Assets/Output"`, `:86` `SESSION_FILE`, `:77` `PROJECT_MAPPING`, `:1221,:1730` resume/step | **OK** |
| C27 | "read `scripts/fdh/generated/REGISTRY.md` … reuse a script if one fits" | `FDH.md:28` | `scripts/fdh/generated/REGISTRY.md:10` = `\| _(none yet)_ \|` while 0 generated scripts exist beside it in this worktree (only `__init__.py`). Registry and directory agree **here**; the drift the task brief describes is in the main tree, not this one | **OK in this worktree** |
| C28 | `terms.clade_neighbors(hit)` | `SCHEMA.md:112` | `scripts/schema/terms.py:136` | **OK** |
| C29 | `templates.template_fields(id)` | `SCHEMA.md:140` | `scripts/schema/templates.py:114` | **OK** |
| C30 | `field_index.rank_candidates()` | `SCHEMA.md:165` | `scripts/schema/field_index.py:120` | **OK** |
| C31 | schema mode has 5 modules | `SCHEMA.md:52-58` | `scripts/schema/` holds 6 non-`__init__` modules; `templates.py` missing from the table but described at `SCHEMA.md:138-178` | **PARTIAL** |
| C32 | report mode has 7 modules | `REPORTS.md:138-146` | all 7 exist; `scripts/report/scrub_fixture.py` unlisted | **OK** (unlisted file is a test util) |

### 8.4 Counts and measured figures

| # | claim | doc:line | ground truth | verdict |
|---|---|---|---|---|
| C33 | "of **1059** distinct field names across **101** sample types, **856** are used by exactly one type" | `SCHEMA.md:11-13` | `scripts/schema/field_index.py:7-8`: "1059 distinct field names across 101 sample types, **857** are used by exactly one type"; `docs/superpowers/specs/2026-07-21-schema-mode-design.md:17`: "**857 (81%)**" | **WRONG** — 856 vs 857, off by one against two sources |
| C34 | "none is generated for all 1059 names" | `SCHEMA.md:182-183` | `scripts/schema/dictionary.py:8` | **OK** |
| C35 | "200 ruled rows collapse to 127 keys and 5 disagreed" | `ASSAY.md:25` | `scripts/assay_hygiene/rulings.py:20-21`; `scripts/assay_hygiene/migrate_rulings.py:112` "5 of 127 keys" | **OK** |
| C36 | "261 rulings became worthless" | `ASSAY.md:22` | `scripts/assay_hygiene/rulings.py:12` | **OK** |
| C37 | "Lab was the discriminator in three of the five, which is the measured cost of dropping it from the key: **3.9%**" | `ASSAY.md:27-28` | no in-repo source for "lab was the discriminator in three of the five" (grep over `scripts/assay_hygiene/`, the mode spec and the ruling-store plan). 3.9% = 5/127; 3/127 = 2.4%. The sentence attaches the 5-of-127 percentage to a 3-of-5 subclaim | **UNSOURCED** + arithmetically mismatched |
| C38 | "In RUN1, 2,830 rows shared a cohort key with an approved cohort but sat below the precedent floor" | `ASSAY.md:49-51` | `scripts/assay_hygiene/carryforward.py:9-10` verbatim | **OK** |
| C39 | "`assay-hygiene/` … is 33 symlinks into `assets/RUN1/`" | `ASSAY.md:58-59` | `scripts/assay_hygiene/_writeguard.py:7-8` "33 symlinks into `assets/RUN1/`"; `commands/curate-assay-detect.md:9-11` adds "27 of 33 artifacts are reachable that way" | **OK** |
| C40 | "The 2026-08-26 audit found 578 of 26,188 rows in that state" | `ASSAY.md:72` | `scripts/assay_hygiene/resolve_targets.py:11` verbatim; `scripts/assay_hygiene/registration_payload.py:21` "26,188 resolved rows" | **OK** (note: project `CLAUDE.md` quotes 26,193 for a different set — REGISTRATION-ROWS.csv rows) |
| C41 | harvest "these **five** sources" | `SKILL.md:86` | numbered list `SKILL.md:88-107` has 5 entries | **OK** |
| C42 | "genuinely absent from **all four** sources" (×2) | `SKILL.md:75`, `SKILL.md:112` | the list is five (`SKILL.md:86`) | **WRONG** — same defect propagated to `PHASES.md:244`, `PHASES.md:257` ("all four"), `REPORTS.md:100` ("Only when all four come up empty") |
| C43 | `context/full-fdh-openapi-spec.yaml` is 640 KB | `FDH.md:32` | 640626 bytes | **OK** |
| C44 | `context/NExtSEEK_API.yaml` bundled 2026-05-27 | `PHASES.md:300`; `SCHEMA.md:107` | asserted by `tests/test_phases_doc.py:58-62`; not independently re-derivable from the file | **OK as a self-consistent flag** |

### 8.5 `assay` mode behaviour

| # | claim | doc:line | ground truth | verdict |
|---|---|---|---|---|
| C45 | tiers `00`–`06` read-only from creation | `ASSAY.md:9-10` | `scripts/assay_hygiene/init_run.py:24-26`: `TIERS` has **8** entries `00-rulings … 07-process`; `PROTECTED = TIERS[:-1]` = 00–06. `create_run` (`:62-73`) protects at creation | **PARTIAL** — the 00–06 half is exact; the doc never mentions that `07-process` exists and is writable |
| C46 | state at `assets/assay-run.json`, one run open at a time | `ASSAY.md:10-11` | `scripts/assay_hygiene/runstate.py:22` `LOCK_NAME = "assay-run.json"`; `create` refuses while open (`:49-56`); commands read `Path('assets')` (`commands/curate-assay-status.md:10`) | **OK** |
| C47 | ruling store at `assets/rulings/`, key `(sample_type, internal_assay_id, action)` | `ASSAY.md:15-17` | `scripts/assay_hygiene/rulings.py:15,:46,:94`; `commands/curate-assay-init.md:16` uses `assets/rulings` | **OK** |
| C48 | conflicts "excluded from the store and put back to the operator, never resolved by a rule" | `ASSAY.md:25-26` | `scripts/assay_hygiene/rulings.py:80-85` raises `ConflictingRulings`; `init_run.py:88-91` filters and returns them | **OK** |
| C49 | "On `detect`, every cohort is sorted three ways against the store: **already ruled** (carried), **ruled in a narrower context** (surfaced, never applied), and **never seen**" | `ASSAY.md:45-47` | `scripts/assay_hygiene/carryforward.py:33-35` defines the three buckets, but `:18-24` states: "NOTHING DERIVES `ruled_width` YET … Callers therefore pass `{}`, every matched pair lands in WIDENED, and the practical effect is that carry-forward carries nothing and re-asks everything … it is not the finished feature, and a reader should not mistake a working split for a working carry-forward." The CARRIED branch (`:55-56`) is unreachable in production today | **PARTIAL / materially misleading** — ASSAY.md describes the split as operational and never records that the carried bucket is always empty |
| C50 | `curate-assay-init` "chmod tiers" | `ASSAY.md:34` | `scripts/assay_hygiene/init_run.py:72` `protect(base, PROTECTED)`; `scripts/assay_hygiene/protect_run.py` | **OK** |
| C51 | `curate-assay-review` "auto-backup" on ingest | `ASSAY.md:37` | `commands/curate-assay-backup.md:5-7` confirms review backs up on every ingest; `scripts/assay_hygiene/store_backup.py:27-47` verifies the tarball by reading it back | **OK** |
| C52 | `curate-assay-status` "writes nothing" | `ASSAY.md:40` | `commands/curate-assay-status.md:5` "This command writes nothing." | **OK** |
| C53 | "`storeOneRecord` sets `status = 1` and never updates it from the DB call" | `ASSAY.md:66-67` | server-side NExtSEEK code, not in this repo; corroborated only by `docs/findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md` | **UNVERIFIABLE HERE** |
| C54 | `curate-assay-write` "writes to **production**" and is the only command that does | `ASSAY.md:39` | `commands/curate-assay-write.md:7-8` "This is the only command that touches production. It writes nothing without `--confirm`." Command description says "behind eight refusals"; ASSAY.md's table cell says only "preflight, chunk, submit, reconcile" | **OK**, understated |

### 8.6 Doc-lint tests already in place (what is guaranteed vs. not)

`tests/test_mode_table.py` — parses `## Modes` and asserts: every reference doc exists
(`:44`); the table lists exactly the `.md` files in `skills/curation/` minus SKILL.md
(`:48`); the mode set equals `{pipeline, fdh, schema, report, assay}` (`:56`); each mode
points at its own doc (`:60`); state-scope strings for pipeline/schema/report (`:65`);
SKILL.md carries no phase table (`:72`); PHASES.md does (`:78`); the phase table omits 4
and 8 and has exactly 11 rows (`:82`); the string `"NOT part of the 13-phase pipeline"` is
absent **from SKILL.md** (`:97-100`); the vocabulary section mentions bolster / sample type
/ GEO / SRA / PRIDE (`:103`).

`tests/test_phases_doc.py` — asserts phase 5 says "review artifact" + "curator" + "not a
build intermediate" + `write_4sheet_xlsx` + `ontology=`; phase 6 says "Ontology" +
"silently discard" + "only allowed in flat"; phase 7 owns `assay_synonyms.json` +
"formerly Phase 8"; no standalone phase 4/8 sections; phase 3 mentions TaskCreate; the
2026-05-27 verify flag is present.

`tests/test_fdh_reference_docs.py` — FDH.md exists with anchors; REGISTRY.md has the table
header; SKILL.md points at FDH.md and names both fdh commands.

**Not covered by any test:** the frontmatter mode list (C1), "one mode among four" (C2),
`/curate-status` mode coverage (C4), the schema-vs-assay vocabulary line (C5), the
"13-phase" string in FDH.md (C12) or `commands/fdh-upload.md` (C13), the 856/857 count
(C33), the "all four / five sources" mismatch (C42), and the carry-forward status (C49).

---

## 9. Facts a later agent should not re-derive

- `SKILL.md` is the only doc with frontmatter, and that frontmatter is duplicated verbatim
  in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. A fix to C1 must
  touch all three or they diverge.
- `README.md:11` says "four modes" and `README.md:14` "12 phases"; `README.md:58` documents
  `/curate-assay-vocabulary` as reading `assay-hygiene/vocabulary-unresolved.csv`. README is
  outside this inventory's scope but shares C1/C2's defect.
- `scripts/status.py` has no `assay` branch; adding one is a code change, not a doc change.
  Until then, `ASSAY.md:40` correctly routes assay status to `curate-assay-status`, which
  reads `assets/assay-run.json` directly.
- `ASSAY.md` is the shortest reference doc (72 lines) covering the mode with the most
  commands (8) and the only mode that writes to production.
- Untracked run output (`assay-hygiene/`, `assets/`, `working/`) is gitignored and lives in
  the main tree, not here. Its absence is expected; no ASSAY.md path claim can be checked
  against a live store from this worktree.
