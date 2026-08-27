# Drift audit — `skills/curation/PHASES.md`

**Target:** `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs/skills/curation/PHASES.md` (506 lines)
**Worktree:** `dev-docs` @ `833e9be`, clean except untracked `docs/audit/`
**Verdict:** SUBSTANTIAL_DRIFT
**Findings:** 9 (2 high / 3 medium-high / 2 medium / 2 low). Every one was verified by opening the cited source file.

---

## Summary

PHASES.md's *structure* is sound: the phase numbering, the retired-4/retired-8 rationale,
the arm definition, the 4-sheet-vs-flat argument and the `synonyms_by_cited_name` key are
all still correct against the code (in the last case PHASES.md is right and
`commands/curate-resolve-assays.md` is the file that is wrong). The drift is concentrated in
the *operational* half of each phase — the "Action" numbered lists, the invocation lines and
the edge cases.

Three things are load-bearing and missing or wrong:

1. **Phase 5 has no `stamp_guard.preflight`.** The single mandatory safety call in the whole
   pipeline — the one guarding against overwriting another curator's records on upload, with
   a named real incident behind it — is in `commands/curate-build.md` and in
   `scripts/stamp_guard.py`, and is absent from the deep reference doc that describes what
   the generated build script must contain.
2. **Phase 6's "no rename needed" promise is false for the GEO deposit route**, which opens
   three hardcoded `<TYPE>-upload-new.xlsx` filenames and silently patches zero rows when it
   finds arm-named sheets instead.
3. **Phase 6 writes a second artifact the doc never names** — `Arm{X}_review.xlsx`, the file
   the flat sheet's own README tells the curator to read.

Then: Phase 7 omits the mandatory back-edge to Phase 6 (nothing else populates `assay_ids`),
Phase 9's invocation line drops the two flags that make QA correct, Phase 10's OMERO line
omits a required positional argument, and Phase 11 carries an edge case that contradicts the
same section's own Inputs line. Finally, every "Invoke `scripts/X.py`" line in the file
violates `SKILL.md` hard rule 6 (`uv run --script`), and the phase table omits 9b, which the
doc itself calls "the last gate before upload".

Non-findings worth recording so nobody re-derives them: PHASES.md:344 (`synonyms_by_cited_name`)
is **correct** — `commands/curate-resolve-assays.md:24` is the outlier. PHASES.md:236-239
(ontology) is now correct; the stale text is the comment at `scripts/schema/ontology.py:13-14`.
PHASES.md:299-302's "bundled 2026-05-27" dating of the NExtSEEK_API.yaml ontology claim is
corroborated by `context/VINTAGE.json`'s closing note. And `pending_schema/` being
agent-only is true of the command files too, so it is not drift specific to this file — see
"Findings considered and rejected" for the hazard it does carry.

---

## F1 — Phase 5 omits `stamp_guard.preflight` and the fresh-DB-pull prerequisite (WRONG, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:199` (Inputs) and `:245-252` (generated-script contract).

The Inputs line names `previous_metadata/*.xlsx` (master) with no freshness constraint, and
the generated-script contract at step 5 lists PEP 723 / `sys.path` / `_common` imports /
project constants / minting / writing — and no `stamp_guard`.

**Reality:**

- `commands/curate-build.md:12-18` makes the fresh pull a hard prereq with the reason spelled
  out ("a stale pull won't show a stamp another curator claimed since it was exported, so the
  check would pass falsely") and gives the `pull-db` line to refresh it.
- `commands/curate-build.md:31-37` makes the call mandatory and non-removable:
  `from stamp_guard import preflight` … `preflight([<types>], LAB, DATE, project_root=".")`.
- `commands/curate-build.md:49-56` records the incident: "Flower_Tyro clobbered 18 Leddy
  immunopeptidomics rows."
- `scripts/stamp_guard.py:169-177` — `preflight(sample_types, lab, date, *, project_root=".",
  master_path=None, max_age_hours=24.0)`; it runs `require_fresh_db_pull` (`:68`) then
  `guard_stamp` (`:134`). `scripts/stamp_guard.py:163` is the `STAMP_GUARD_OVERRIDE=1` escape.

A contributor writing a `build_<arm>.py` from PHASES.md alone produces a script with no
collision guard, and PHASES.md's own "Mint UIDs `<TYPE>-YYMMDD<LAB>-N`" (`:250`) then reads as
an unconditional instruction to mint from N=1 into a stamp nobody proved free.

**Proposed fix.** Replace `PHASES.md:199`:

```markdown
**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master — **must be a fresh DB
pull, under 24 h old**; grab one with `uv run --script <PLUGIN>/scripts/nextseek_api.py
pull-db --project-id N`), `manuscript/`, `.dmac-curation.json` (lab + pi)
```

Replace `PHASES.md:245-251` (step 5 of the Action list):

```markdown
5. Generate `./scripts/build_<arm>.py`:
   - PEP 723 inline deps (openpyxl)
   - `sys.path.insert(0, "<PLUGIN_PATH>/scripts")`
   - `from _common import mint_uid, write_4sheet_xlsx, schema_column_order, placeholder`
   - **`from stamp_guard import preflight`, called BEFORE any UID is minted:**
     `preflight([<sample types this arm mints>], LAB, DATE, project_root=".")`
     (`scripts/stamp_guard.py:169`). This is the root-cause guard against UID-stamp
     collisions: it refuses an absent or >24 h old DB pull (`require_fresh_db_pull`,
     `:68`) and refuses to mint into a `<DATE><LAB>` stamp that already carries rows
     for these sample types, naming the nearest free stamp (`guard_stamp`, `:134`).
     Never delete the call to make a build run.
   - Per-project constants come from `./scripts/_project_constants.py` (copy
     `<PLUGIN>/scripts/_project_constants.py.example`), never from `_common`
   - Mint UIDs `<TYPE>-YYMMDD<LAB>-N` from N=1 — safe **only** because preflight proved
     the stamp free. When several arms share one stamp, offset N per arm (arm A `1..k`,
     arm B `k+1..`); never restart at 1.
   - Write one 4-sheet xlsx (`Instructions / Samples / Assay / Ontology`) per sample type
     into `assay_sheets/4sheet_originals/`
```

Add two edge cases at `PHASES.md:255-259`:

```markdown
- Stale or missing DB pull: `preflight` raises before anything is minted. Re-pull with
  `nextseek_api.py pull-db --project-id N`; do not lower `max_age_hours`.
- Stamp collision: `preflight` raises with a suggested free stamp — re-mint under it.
  `STAMP_GUARD_OVERRIDE=1` downgrades the refusal to a printed warning
  (`scripts/stamp_guard.py:163`) and exists only for a deliberate, eyes-open re-upload
  into an existing stamp, never to silence a real collision.
```

---

## F2 — "the sheet does not need renaming" is false for `/curate-deposit geo` (WRONG, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:269-271`, echoed by Phase 10's GEO route (`:416-418`).

> **Output:** `assay_sheets/Arm{X}-upload.xlsx`, flat format, one per arm. The `-upload`
> suffix is what `/curate-retrieve` and `/curate-deposit` read, so the sheet does not need
> renaming between here and Phase 11.

**Reality.** True for three of four consumers, false for the one that matters most at Phase 10:

| consumer | how it finds sheets | arm-named sheet works? |
|---|---|---|
| `/curate-retrieve` | `build_retrieve.py:31-39` globs `*.xlsx`, prefers `-upload-new` over `-upload` | yes |
| `/curate-validate` | `review_metadata_vs_uploads.py:89` globs `*-upload*.xlsx` | yes |
| `/curate-deposit zenodo` | `apply_zenodo_links.py:64-73` globs `*.xlsx`, same preference | yes |
| **`/curate-deposit geo`** | **`apply_geo_accessions.py:248-250` opens three hardcoded names** | **no** |

`scripts/apply_geo_accessions.py:248-250`:

```python
dseq_path  = sheets / "D.SEQ-upload-new.xlsx"
agex_path  = sheets / "A.GEX-upload-new.xlsx"
asptx_path = sheets / "A.SPTX-upload-new.xlsx"
```

Each is guarded by `if …exists()` / `else: print(f"\nWARNING: {…}.name} not found — skipping …")`
(`:251-265`), and `main()` has no return value or `sys.exit` on that path — so on a project
whose sheets are `ArmA-upload.xlsx`, the GEO backfill prints three warnings, patches zero
rows, and **exits 0**. Following PHASES.md as written, an operator concludes the accessions
landed.

**Proposed fix.** Replace `PHASES.md:269-271`:

```markdown
**Output:** `assay_sheets/Arm{X}-upload.xlsx`, flat format, one per arm — plus the
`Arm{X}_review.xlsx` twin described below.

The `-upload` suffix is what `/curate-retrieve` (`build_retrieve.py:31-39`),
`/curate-validate` (`review_metadata_vs_uploads.py:89`) and `/curate-deposit zenodo`
(`apply_zenodo_links.py:64-73`) read, so no rename is needed for those.

**`/curate-deposit geo` is the exception.** `apply_geo_accessions.py:248-250` opens three
hardcoded per-sample-type filenames in `--sheets-dir` (default `assay_sheets/`):
`D.SEQ-upload-new.xlsx`, `A.GEX-upload-new.xlsx`, `A.SPTX-upload-new.xlsx`. An arm-named
sheet is invisible to it — it prints `WARNING: … not found — skipping`, patches nothing,
and still exits 0. Before Phase 10, split the GEO-bearing types into
`<TYPE>-upload-new.xlsx` working copies (hard rule 2: copy, never rename in place), or
point `--sheets-dir` at a directory that holds them.
```

And append to the Phase 10 GEO bullet at `PHASES.md:418`:

```markdown
  The script reads `D.SEQ-upload-new.xlsx`, `A.GEX-upload-new.xlsx` and
  `A.SPTX-upload-new.xlsx` from `--sheets-dir` (default `assay_sheets/`) and skips, with a
  warning and exit 0, any it cannot find — check the patched-row counts, not the exit code.
```

---

## F3 — Phase 6 never mentions `Arm{X}_review.xlsx` (MISSING, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:269` (Output), `:304-308` (Action), `:66` (arm table row 6).

**Reality.** `scripts/consolidate_to_flat.py:492` calls `build_review_workbook(arm, sources, src)`
unconditionally inside the per-arm loop, writing `out_dir / f"{arm_name}_review.xlsx"`
(`:253`) — one sheet per sample type, every field its own column, frozen panes, tuned widths.

The script's own docstring (`:44-49`) explains why: "The flat file packs each sample into a
single `json_metadata` blob — correct for upload, unreadable for a human — so the review file
is what a curator actually reads before submitting. It is never uploaded." The flat file's
README sheet points at it by name (`:332-336`): "Read that one to review the metadata; upload
THIS one."

This directly undercuts PHASES.md's own centrepiece argument at `:204-222` ("Phase 5's output
is what a person looks at. Phase 6's output is what a machine ingests. Neither replaces the
other."). Phase 6 produces *both*. `templates/CLAUDE.md.j2:43-44` and `README.md:37` already
document the review file; PHASES.md, the deepest reference, does not.

**Proposed fix.** Update the arm table row at `PHASES.md:66`:

```markdown
| 6 | one flat `assay_sheets/Arm{X}-upload.xlsx` + its `Arm{X}_review.xlsx` twin |
```

Insert after the Output block in Phase 6 (i.e. before "### Flat cannot carry controlled
vocabulary" at `:273`):

```markdown
### The review twin

`consolidate_to_flat.py:492` writes `assay_sheets/Arm{X}_review.xlsx` for every arm,
unconditionally — one sheet per sample type, every field in its own column. The flat file
packs each sample into a single `json_metadata` blob, correct for upload and unreadable
for a human, so the twin is what a curator actually reads before submitting
(`consolidate_to_flat.py:44-49`); the flat file's own README sheet says exactly that
(`:332-336`). It is never uploaded.

The underscore in its name is load-bearing: it keeps the twin out of every
consolidated-output glob — `qa_flat_sheets.py`'s `--upload` default (`:420-430`), report
mode's curated-sheet adapter (`scripts/report/adapters.py:203`), and
`is_consolidated_output` (`consolidate_to_flat.py:355-372`), which is why a re-run deletes
the upload sheet but not the twin.

So Phase 5 is not the only review artifact. Phase 5 reviews **what was built**, per sample
type; Phase 6's twin reviews **what will be uploaded**, per arm.
```

And amend Action step 3 (`PHASES.md:307`):

```markdown
3. Per arm, produce a flat xlsx with a `Samples` sheet (`uid, sampletype, name, parent,
   notes_summary, assay_titles, assay_ids, json_metadata`) and a `README` sheet, plus the
   `Arm{X}_review.xlsx` twin.
```

---

## F4 — Phase 7 drops the mandatory re-run of Phase 6 (MISSING, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:322-333` — the Phase 7 Action list ends at step 5,
"Update `.dmac-curation.json` lockfile with `nextseek_project_id`."

**Reality.** `commands/curate-resolve-assays.md:32` has a step 7 that PHASES.md does not:
"Suggest re-running `/curate-consolidate` to apply the new assay_ids."

That step is not cosmetic. `assay_ids` is resolved only while a flat sheet is being written:
`consolidate_to_flat.py:136-151` (`resolve_assay_id`, cache hit → synonym → blank), reached
from `build_arm_flat`. `grep -rn assay_ids scripts/*.py` finds no other writer — `status.py:31`
merely counts the cache file, `nextseek_api.py` only produces it. So a cache or synonym file
written at Phase 7 has **zero effect** until Phase 6 runs again.

The doc also hides the cycle. PHASES.md presents 1→13 as a line, and Phase 6's edge case
(`:311`) says only "Cache or synonyms missing: leave `assay_ids` blank, suggest
`/curate-resolve-assays`" — while Phase 7's own prerequisite is Phase 6's output
(`PHASES.md:343`: "compare against the `assay_titles` column in `assay_sheets/Arm*.xlsx`";
`commands/curate-resolve-assays.md:12`). The true order is 6 → 7 → 6.

**Proposed fix.** Append to the Phase 7 Action list at `PHASES.md:328`:

```markdown
6. **Suggest re-running `/curate-consolidate`.** `assay_ids` is resolved only while a flat
   sheet is being written (`consolidate_to_flat.py:136-151`); nothing backfills the column
   into an existing `Arm{X}-upload.xlsx`. A cache or synonym written now has no effect
   until Phase 6 runs again.
```

Add a note under the Phase 6 heading (`PHASES.md:265`, above "**Inputs:**"):

```markdown
**Phases 6 and 7 are a loop, not a line.** Phase 7 needs Phase 6's output (it diffs the
cached titles against the `assay_titles` column of `assay_sheets/Arm*.xlsx`) and Phase 6
needs Phase 7's output (`context/assay_ids_cache.json` + `context/assay_synonyms.json` are
what populate `assay_ids`). Run 6 → 7 → 6. The second consolidation is not optional if
`assay_ids` came out blank the first time.
```

And sharpen the Phase 6 edge case at `:311`:

```markdown
- Cache or synonyms missing: `assay_ids` is left blank. Run `/curate-resolve-assays
  --project-id N`, **then re-run this phase** — nothing patches the column afterwards.
```

---

## F5 — Phase 9's invocation line drops both flags that make QA correct (WRONG, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:357` (Inputs) and `:360` ("1. Invoke `scripts/qa_flat_sheets.py`.").

**Reality — two separate defects.**

*a) The bare invocation fails on any multi-arm project.* `scripts/qa_flat_sheets.py:420-430`:
with `--upload` absent the script collects the underscore-free `*.xlsx` under
`<project>/assay_sheets` and, `if len(candidates) != 1`, prints `ERROR: pass --upload; found
N consolidated sheets …` and exits 2. `commands/curate-qa.md:13` shows `--upload
assay_sheets/Arm{X}-upload.xlsx` explicitly for that reason.

*b) The most important check is invisible in the doc.* `commands/curate-qa.md:13-16` says
"**Always pass `--master-baseline` with a FRESH DB pull** — it powers the UID-vs-DB collision
net (a new UID that already exists in the pull would overwrite another study on upload).
Without a baseline the net can't run." The check is `qa_flat_sheets.py:165-170`
(`issues["uid_exists_in_db"]`) reported at `:317-334` as a BLOCKER, waivable only by
`QA_ALLOW_DB_UPDATES=1`. PHASES.md names the master xlsx once, "for parent resolvability"
(`:357`), never as a flag, and its five edge cases (`:366-370`) do not include the collision
at all — so a reader takes the doc's word that the master is optional colour.

**Proposed fix.** Replace `PHASES.md:355-364`:

````markdown
**Command:** `/curate-qa`

**Inputs:** `assay_sheets/Arm{X}-upload.xlsx`, one arm at a time; and a **fresh** master DB
pull passed as `--master-baseline`

**Action:**
1. Invoke, per arm:
   ```
   uv run --script <PLUGIN>/scripts/qa_flat_sheets.py \
       --upload assay_sheets/Arm{X}-upload.xlsx \
       --master-baseline previous_metadata/<master>.xlsx \
       [--expected-counts <sampletype>=<n>,...]
   ```
   `--upload` is not optional on a multi-arm project: omitted, the script looks for the
   *single* underscore-free `.xlsx` under `assay_sheets/` and exits 2 listing what it found
   (`qa_flat_sheets.py:420-430`). **Always pass `--master-baseline`, against a pull taken
   just now** — it is what powers the UID-vs-DB collision net below; without it the net
   cannot run and QA will pass a sheet that overwrites another study on upload.
2. Per row: classify CLEAN / SOFT_FLAG / HARD_REJECT (the command interprets the script's
   raw [BLOCKER]/[INFO] findings into these disposition labels).
3. Report counts + per-row dispositions.
4. Surface specific gaps (missing File_PrimaryData, dangling parents, malformed
   json_metadata, surprise placeholder markers).
````

Insert as the first edge case at `PHASES.md:366`:

```markdown
- UID already present in the master baseline: HARD_REJECT. On upload that row UPDATES
  (overwrites) the existing record instead of inserting — the stamp collision Phase 5's
  `preflight` exists to prevent, caught here as the second net (`qa_flat_sheets.py:165-170`,
  `:317-334`). Re-mint under a free stamp. For a deliberate update or restore, and only
  then, re-run with `QA_ALLOW_DB_UPDATES=1`, which downgrades it to
  `INFO — updates acknowledged`.
```

---

## F6 — Phase 10's OMERO backfill omits a required positional argument (WRONG, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:431` — "`scripts/apply_omero_ids.py --write` patches D.IMG
`Link_PrimaryData`."

**Reality.** `scripts/apply_omero_ids.py:72-77` declares `p.add_argument("xlsx", type=Path)`
as the first, required, positional argument. Run as documented, argparse exits 2 with
`the following arguments are required: xlsx` before any work begins. The script does not use
`_config` and does no sheet discovery, so `--omero-csv` (default `omero_images.csv`, `:74`)
also resolves against the cwd. `commands/curate-deposit.md:54` carries the same defect
(inventory D2), so this is not a doc-vs-command disagreement — both need the fix.

**Proposed fix.** Replace `PHASES.md:430-431`:

```markdown
- `uv run --script <PLUGIN>/scripts/omero_pull.py all --project N` → `omero_images.csv`.
- `uv run --script <PLUGIN>/scripts/apply_omero_ids.py assay_sheets/D.IMG-upload-new.xlsx
  [--omero-csv omero_images.csv] --write` patches D.IMG `Link_PrimaryData` by filename
  match. The workbook is a **required positional argument** (`apply_omero_ids.py:73`) — the
  script discovers nothing and does not use `_config`, so both paths resolve against the
  cwd. Dry-run by default; `--write` saves and leaves a `.bak`.
```

---

## F7 — Phase 11's edge case contradicts its own Inputs line (STALE, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:455` — "No upload-new sheets present: refuse, suggest
`/curate-build` + `/curate-consolidate`".

**Reality.** `scripts/build_retrieve.py:31-39` builds its candidate map from `*.xlsx`,
preferring `-upload-new` and **falling back to `-upload`** (`elif "-upload" in p.stem …
candidates.setdefault(base, p)`). `commands/curate-retrieve.md:11` states the same:
"`/curate-consolidate` writes `Arm{X}-upload.xlsx` directly, so a fresh consolidation is
already retrievable with no rename." PHASES.md's own Inputs line at `:446` says exactly that
too — so the edge case contradicts the sentence nine lines above it. It is a leftover from
before `/curate-consolidate` emitted the `-upload` suffix, and following it makes the agent
refuse a phase that would have run.

**Proposed fix.** Replace `PHASES.md:455`:

```markdown
- No `-upload-new` sheets present: **not an error.** `build_retrieve.py:31-39` falls back
  to `*-upload.xlsx`, which is what `/curate-consolidate` writes. Refuse only when neither
  exists — then suggest `/curate-build` + `/curate-consolidate`.
```

---

## F8 — every script invocation line violates the plugin's own hard rule 6 (UNCLEAR, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:126, 156, 305, 324, 381, 417, 418, 422, 425, 449, 467`
(plus `:360` and `:430-431`, fixed under F5/F6).

**Reality.** `skills/curation/SKILL.md:73`, hard rule 6: "**Use `uv`, not bare `python3`.** All
scripts have PEP 723 inline-deps. Invoke via `uv run --script <plugin>/scripts/X.py`." All 24
top-level `scripts/*.py` are mode `-rw-r--r--` and carry PEP 723 headers; the only executable
is `scripts/upload_geo_ncftp.sh`. Every one of the 14 pipeline command files uses
`uv run --script`. PHASES.md — the file those commands defer to for specifics — writes bare
paths throughout, so its lines are neither runnable nor dependency-resolved as printed.

Two of them are additionally under-specified: `:305` omits `--all-in-one NAME`, and `:417`
says "Drives `scripts/upload_geo_ncftp.sh` for upload" without noting that the script takes
`bash`, takes **job names** (`bulk` / `spatial`, `upload_geo_ncftp.sh:116-134`) not a path,
and defaults to running both.

**Proposed fix.** Line-for-line replacements:

| line | current | replacement |
|---|---|---|
| 126 | ``Inspect every `previous_metadata/*.xlsx` via `scripts/inspect_workbook.py`.`` | ``Inspect every `previous_metadata/*.xlsx` via `uv run --script <PLUGIN>/scripts/inspect_workbook.py <path>`.`` |
| 156 | ``Run `scripts/build_sample_tree_html.py` → `./SAMPLE_TREE.html`, the interactive review view.`` | ``Run `uv run --script <PLUGIN>/scripts/build_sample_tree_html.py [--strict]` → `./SAMPLE_TREE.html`, the interactive review view. Both `--input` and `--output` default to cwd-relative paths (`build_sample_tree_html.py:368-369`), so run it from the project root; `--strict` (`:373`) turns a clade warning into exit 1.`` |
| 305 | ``Invoke `scripts/consolidate_to_flat.py --assay-sheets assay_sheets`.`` | ``Invoke `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`.`` |
| 324 | ``Invoke `scripts/nextseek_api.py fetch-assays --project-id N`.`` | ``Invoke `uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id N`.`` |
| 381 | ``` `scripts/nextseek_api.py validate --project-id N --checks structure,dag,name_check --dump-dir <scratch> <file>` ``` | ``` `uv run --script <PLUGIN>/scripts/nextseek_api.py validate --project-id N --checks structure,dag,name_check --dump-dir <scratch> <file>` ``` |
| 417 | ``Drives `scripts/upload_geo_ncftp.sh` for upload.`` | ``Upload with `bash <PLUGIN>/scripts/upload_geo_ncftp.sh [bulk\|spatial]` — the one executable in `scripts/`. Its positional arguments are **job names**, not paths (`upload_geo_ncftp.sh:116-134`); the local source dirs are hardcoded (`GEO/bulk_rna/GEO`, `GEO/spatial`), and a bare invocation runs both jobs. Needs `NCFTP_HOST/USER/PASS/REMOTE_BASE` in `.env`. No dry run — invoking it starts the transfer.`` |
| 418 | ``…: `scripts/apply_geo_accessions.py` patches D.SEQ/A.GEX/A.SPTX…`` | ``…: `uv run --script <PLUGIN>/scripts/apply_geo_accessions.py --gse-bulk GSE###### --gsm-csv <roster> [--gse-sptx GSE###### --sptx-gsm-csv <roster>] [--write]` patches D.SEQ/A.GEX/A.SPTX…`` |
| 422 | ``Drives `scripts/stage_zenodo.py` to preview, then … re-runs it with `--write`.`` | ``Drives `uv run --script <PLUGIN>/scripts/stage_zenodo.py` to preview, then … re-runs it with `--write`.`` |
| 425 | ``` `scripts/apply_zenodo_links.py --write --record-id N` ``` | ``` `uv run --script <PLUGIN>/scripts/apply_zenodo_links.py --write --record-id N` ``` |
| 449 | ``Invoke `scripts/build_retrieve.py`.`` | ``Invoke `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]` **from the project root** — this is the one pipeline script that does not use `_config`/project-root discovery, so `--assay-sheets` and `--output` resolve straight off the cwd (`build_retrieve.py:78-84`).`` |
| 467 | ``Invoke `scripts/review_metadata_vs_uploads.py --metadata-xlsx <xlsx> …`.`` | ``Invoke `uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata-xlsx <xlsx> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`.`` |

---

## F9 — the phase table omits 9b and the header now reads as the whole plugin (STALE, CONFIRMED)

**Doc:** `skills/curation/PHASES.md:9-30`.

**Reality — two things.**

*a) 9b is missing from the table.* The header says the split exists (`:9-10`), and `:374-404`
gives 9b a full section calling it "the last gate before upload" (`:392`) — but the table a
reader scans (`:17-29`) lists 11 rows and no 9b, and neither `/curate-qc` nor `/curate-status`
appears in it, so the "14 commands" of `:9` are 12 in the table. `scripts/status.py:25-38`
confirms 9b is also invisible to `/curate-status`, which is worth saying out loud.

*b) "14 commands drive 12 phases" now under-counts the plugin.* `skills/curation/SKILL.md:30-34`
registers five modes, the fifth (`assay`) adding eight `/curate-assay-*` commands with their
own reference `skills/curation/ASSAY.md` (present on disk). PHASES.md is titled "Phase
reference for dmac-curation" and never says it covers `pipeline` only, so its opening count
reads as the plugin's total. One clause fixes it.

*c)* Minor, same block: the Phase 2 row names only `SAMPLE_TREE.md`, while `:158-160` declares
three co-equal outputs.

**Proposed fix.** Replace `PHASES.md:9-29`:

```markdown
14 pipeline-mode commands drive 12 phases. (The plugin ships 26 commands across five
modes — `pipeline`, `fdh`, `schema`, `report`, `assay`. **This file covers `pipeline`
only**; see `SKILL.md` for the roster and `FDH.md` / `SCHEMA.md` / `REPORTS.md` /
`ASSAY.md` for the rest.)

Phase 9 is split into 9a (`/curate-qa`, local) and 9b (`/curate-qc`, server-side); phases
4 and 8 were retired as numbers (see "Retired phases"); the surviving numbers are
deliberately **not** renumbered, because every scaffolded project's `CLAUDE.md` bakes in
the order, `/curate-status` maps artifacts by number, and curators speak in phase numbers.

The pipeline runs inventory (1) through email (13) — 11 numbers, 12 phases, because 9
splits:

| # | Phase | Command | Artifact |
|---|---|---|---|
| 1 | Inventory | `/curate-inventory` | `FILE_INDEX.md` |
| 2 | Sample tree | `/curate-sample-tree` | `SAMPLE_TREE.md` + `sample_tree.json` + `SAMPLE_TREE.html` |
| 3 | Questions | `/curate-questions [add\|list\|resolve]` | `QUESTIONS_FOR_PI.md` |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}-upload.xlsx` (flat) + `assay_sheets/Arm{X}_review.xlsx` |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` + `context/assay_synonyms.json` |
| 9a | QA (local) | `/curate-qa` | console disposition report |
| 9b | QC (server-side) | `/curate-qc` | console report + `context/live_sampletype_attributes.json` — the last gate before upload |
| 10 | Deposit | `/curate-deposit <geo\|zenodo\|omero>` | external uploads + `Link_PrimaryData` backfilled |
| 11 | Retrieve | `/curate-retrieve` | `RETRIEVE.TXT` |
| 12 | Validate | `/curate-validate <metadata.xlsx>` | console diff report |
| 13 | Email | `/curate-email` | `EMAIL_TO_PI.md` |

`/curate-status` is the fourteenth command and belongs to no phase (see "Phase any").
Note that `/curate-status` does **not** report 9b: `scripts/status.py:25-38` maps
artifacts for phases 1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13 only, so "the last gate ran" is
not recoverable from status output — confirm it from the validator's own report.
```

---

## Findings considered and rejected

- **`synonyms_by_cited_name` (`PHASES.md:344`).** Correct. `consolidate_to_flat.py:125` reads
  exactly that key. `commands/curate-resolve-assays.md:24` says `"synonyms"` and is the file
  that breaks the feature. No PHASES.md change.
- **Ontology (`PHASES.md:230-239`).** Correct and current; `commands/curate-build.md:65-67` now
  instructs `ontology=`. The stale text is `scripts/schema/ontology.py:13-14`, which still
  claims "`curate-build.md` and `PHASES.md` never instruct it be populated".
- **`consolidate_to_flat.py:19-21` citation (`PHASES.md:211`, `:297`).** The quoted claim spans
  `:20-21`; line 19 is blank. Off by one at the start, the range still contains the text.
- **"bundled 2026-05-27" (`PHASES.md:300`).** `context/VINTAGE.json`'s plugin `bundled_date` is
  2026-07-22, but its closing note dates the NExtSEEK_API.yaml ontology claim to 2026-05-27
  and marks the file hand-maintained and never auto-refreshed. The doc is right.
- **`plugin_sha: null` (`PHASES.md:112`).** Matches `commands/curate-init.md:149` and
  `scripts/_lockfile.py:35`.
- **"migrates a v0 lockfile to v1 in place" (`PHASES.md:104`).** `_lockfile.read` migrates in
  memory only, but `/curate-init` reaches it through `set_mode` (`:179`), which calls
  `write` (`:152`) — so the v1 form does land on disk. Accurate as stated.
- **`assay_sheets/pending_schema/` (`PHASES.md:258`, `:312`, `:369`).** Agent-only everywhere:
  `grep -rn pending_schema scripts/` returns nothing, and `commands/curate-build.md:61`,
  `curate-consolidate.md:24` and `curate-qa.md:34` say the same as PHASES.md. Not
  doc-vs-code drift specific to this file. Worth knowing when fixing it globally: a
  pending-schema 4-sheet file left in `assay_sheets/` root carries an underscore and is
  therefore consolidated in as an ordinary source (`consolidate_to_flat.py:443-451`); only
  files already moved into the `pending_schema/` subdirectory are safe, because the glob is
  not recursive. Phase 9's unknown-sampletype HARD_REJECT is the backstop.
- **`/curate-init`'s mode allow-list.** PHASES.md:94 writes `[--mode NAME]` without
  enumerating values, so it is not wrong. The stale allow-list is
  `commands/curate-init.md:11,18-21`.
- **`scripts/fdh/generated/REGISTRY.md`.** Out of scope here and already fixed uncommitted in
  the main tree.
