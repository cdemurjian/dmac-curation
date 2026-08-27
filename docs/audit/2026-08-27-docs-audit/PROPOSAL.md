# Documentation update proposal — dmac-curation

**Scope:** every documentation file in the plugin.
**Basis:** eight ground-truth inventories and six drift audits in this directory, all taken
against worktree `.../.claude/worktrees/docs`, branch `dev-docs`, HEAD `833e9be`.
**Author's verification:** every claim below is traceable to a `file:line` or to a named
audit finding. Where two auditors disagreed I read the source myself and say so inline.

---

## 1. Verdict

The documentation is one release and one whole mode behind, and the gap is not evenly
spread: the *design* prose is broadly still true while the *operational* prose — what to
run, with which flags, and what it will write — has decayed almost everywhere. Six of six
audits returned SUBSTANTIAL_DRIFT, 55 findings in total.

The single structural reason is that **nothing tests the documentation against the code,
and the one thing that is tested is tested in the wrong direction.**
`tests/test_identity_sync.py` pins the plugin's description and version byte-for-byte
across `plugin.json`, `marketplace.json` and `SKILL.md` — so those three can never disagree
— but it asserts nothing about `README.md`, `pyproject.toml`, or any reference doc. The
result is a set of four artefacts locked together at a value that is now wrong (four modes)
and a fringe of files that drifted freely. Everything else follows from that: the fifth
mode, `assay`, registered in `d1f4d14`/`eb8777e`/`64f233d`, is invisible to the plugin's own
activation string, absent from the README, absent from the changelog, and absent from
`/curate-status`, while the reference docs for the four older modes quietly fell behind
their commands.

The consequence that matters most is not staleness but **inverted safety claims**. Three
separate documents now assert the plugin cannot do something it demonstrably does:
`README.md:74-77` promises it never uploads to NExtSEEK and never edits the sample type
catalog; `SCHEMA.md:218` lists "writing to NExtSEEK" as a non-goal while being the mandatory
pre-read for the command that writes to it; and `FDH.md:7` promises a host override that
does not exist for the uploader, which hardcodes production at `scripts/fdh/submit.py:73`.
A reader who trusts any of the three will take an action believing it to be reversible.

---

## 2. The drift, ranked

Ordered by how badly the item would misdirect a reader. Duplicates reported by more than one
auditor are merged into a single row and the merge is named.

### Tier 1 — a reader acting on this does damage, or believes work happened that did not

| # | file | severity | what's wrong | fix |
|---|---|---|---|---|
| 1 | `README.md:74-77` | CRITICAL | Two of three "What this is not" promises are false. `/curate-sampletype apply` writes to a live sample type (`CHANGELOG.md:18-23`) and `/curate-assay-write` writes registrations into `seek_production` (`commands/curate-assay-write.md:2-8`). The README contradicts itself: its own `:57` already says `apply` writes to a live server. | Replace the section — §3.1 F5 |
| 2 | `skills/curation/SCHEMA.md:218` | CRITICAL | `## Non-goals` bullet 1 denies the live production-write path. `commands/curate-sampletype.md:11` orders the operator to read SCHEMA.md *first*; `scripts/sampletype_attr.py:62` defaults to `https://nextseek.mit.edu` and `:242` performs the write. | Rewrite Non-goals + add `## Applying: the one live-write path` — §3.8 S1/S2 |
| 3 | `skills/curation/FDH.md:7` | CRITICAL | The shared preamble promises `FDH_BASE_URL` / `--base-url` over **both** modules. `scripts/fdh/submit.py:73` hardcodes `BASE_URL = "https://fairdomhub.org/"`; its only flags are `--step` and `--resume` (`:1780-1841`); `FDH_BASE_URL` appears nowhere in the file (verified). Every `/fdh-upload` run writes to production. | Split the bullet per module — §3.7 F1 |
| 4 | `skills/curation/SKILL.md:40-64` | CRITICAL | No `### assay` subsection at all, so the always-loaded layer never says that a command writes to production, that rulings are unregenerable, or that SEEK assay ids are per-project. `ASSAY.md` carries all three but is loaded only *after* you already know to enter the mode (`SKILL.md:36-37`). | Insert the subsection — §3.3 F7 |
| 5 | `skills/curation/PHASES.md:199,245-252` | HIGH | Phase 5 omits `stamp_guard.preflight` — the one mandatory safety call in the pipeline, with the Flower_Tyro/18-row incident behind it (`commands/curate-build.md:49-56`) — and its fresh-DB-pull prerequisite. A build script written from PHASES.md alone has no collision guard. | Replace Inputs + step 5, add two edge cases — §3.4 F1 |
| 6 | `skills/curation/ASSAY.md:30-41` | HIGH | The command table reads as a working chain; **three joints have no code.** No review surface emits `ingest`'s required `cohort_key` (`ingest.py:28,39-44` vs `review_mode2.py:443-472`); nothing writes `approved-rows.csv`; nothing builds or posts the `UPDATE_ASSAY` sheet, and `--confirm` (`curate-assay-write.md:8`) does not exist — there is no CLI in the mode. | Add `## What is not built yet` — §3.6 A5 |
| 7 | `skills/curation/ASSAY.md:43-53` | HIGH | The carry-forward split is described as operational. `carryforward.py:18-24` says nothing derives `ruled_width`, callers pass `{}`, and the CARRIED branch is unreachable (`:52-58`). ASSAY.md is the only doc that describes it as working. | Replace the section — §3.6 A1 |
| 8 | `skills/curation/ASSAY.md` (whole) | HIGH | Never explains Modes 1/2/3, so an operator reading `Mode 3: 0` in `detect-report.md` reads "we checked, contradictions are rare". `classify.py:1336,1420` and `run_detect.py:53-55` both say the zero is **UNDETECTED, never SMALL**. | Add `## The three modes` — §3.6 A6 |
| 9 | `skills/curation/REPORTS.md:25` | HIGH | The PRIDE row omits `project_metadata`. Without it `render_pride` emits no `MTD` lines (`render.py:161-163`) and `validate_pride_px` returns `SchemaInvalid` → HARD_REJECT (`validate_artifact.py:308-309,44-50`). REPORTS.md is the **only** place in the repo enumerating PRIDE's sections. | Replace the Formats table + note — §3.9 R1 |
| 10 | `skills/curation/REPORTS.md:62` | HIGH | The UID / `RETRIEVE.TXT` adapter is documented as a `POST` in a column headed "behaviour". `adapters.py:62-84` takes an injected `fetch`; with `fetch=None` it returns **zero samples and no error** (`:70-71`). Nothing outside tests supplies the callable. | Replace the adapter table + note — §3.9 R3 |
| 11 | `skills/curation/REPORTS.md:77-91` | HIGH | All three validation guarantees overstated: SRA `libraries` stars nothing so any readable workbook reports CLEAN (`validate_artifact.py:83-91`); CV checking covers nine fields and none of PRIDE's (`mapping.py:44-60,132-140`; `pride.json` has no `controlled_vocabulary` key); row parity fires only if the mapping sets `expected_rows` (`execute.py:153-159`). | Replace the section — §3.9 R4 |
| 12 | `skills/curation/PHASES.md:269-271`, `:416-418` | HIGH | "the sheet does not need renaming" is false for `/curate-deposit geo`. `apply_geo_accessions.py:248-250` opens three hardcoded `<TYPE>-upload-new.xlsx` names, warns, patches zero rows and **exits 0**. | Replace Output block + amend the Phase 10 bullet — §3.4 F2 |
| 13 | `skills/curation/PHASES.md:357,360` | HIGH | Phase 9's bare invocation drops both flags that make QA correct: without `--upload` it exits 2 on any multi-arm project (`qa_flat_sheets.py:420-430`), and without `--master-baseline` the UID-vs-DB collision net cannot run (`:165-170`, `:317-334`). | Replace the Action block, add an edge case — §3.4 F5 |
| 14 | `skills/curation/ASSAY.md:9-11` | HIGH | The run model omits the eighth tier (`07-process`) and, critically, that `04-artifacts` is `0o555` from creation — every driver needs `chmod -R u+w` first. `commands/curate-assay-vocabulary.md` omits it too, so that step fails with `PermissionError` as documented. | Replace the run model — §3.6 A3 |
| 15 | `skills/curation/ASSAY.md` (whole) | HIGH | Never says how `01-extract/` is produced. `grep` over `commands/ skills/` returns zero hits for `driver_extract`; the recipe exists only in `driver_extract.py:8-12`. The mode has no documented step zero. | Add `## Before run 1` — §3.6 A4 |
| 16 | `skills/curation/FDH.md:17` | HIGH | The Module 1 flow line hides three hazards: step 3 overwrites the curator's workbook in place through a `read_excel`→`ExcelWriter` round trip (`submit.py:1495,570-622`); step 4 POSTs sample types to production with **no** confirmation (`:1568-1573`); step 6 publishes every study asset and runs unconditionally, outside every start-step guard (`:1940`). | Replace with a per-step gate table — §3.7 F6 |

### Tier 2 — the plugin's own identity, and the record of what it does

| # | file | severity | what's wrong | fix |
|---|---|---|---|---|
| 17 | `plugin.json:4`, `marketplace.json:14`, `SKILL.md:3`, `tests/test_identity_sync.py:16` | HIGH | The canonical description (byte-identical across four files, verified) names only pipeline/fdh/schema/report. `assay` is house-scoped — no `files/`, no `manuscript/`, no lockfile — so **not one activation cue fires for it**, which is the exact failure `test_identity_sync.py:3-4` warns about. | New 845-char YAML-safe string, all four files + widen `test_description_names_every_mode` — §3.3 F1 |
| 18 | `README.md:11,14-24,26-70` | HIGH | "four modes"; 7 of 8 assay commands absent entirely. A reader of the front door cannot learn the mode exists, that it is house-scoped, or that one command writes to production. | Fifth bullet + fifth command table + amended Any-mode row — §3.1 F2 |
| 19 | `CHANGELOG.md` | HIGH | Stops at `0.4.0 - 2026-07-31`; **214 commits since**. Zero occurrences of `curate-assay`, `assay_hygiene`, `pull-db`, `stamp_guard`, `DMAC_ENV_FILE` (verified). | Full drafted `## Unreleased` entry — §3.2 |
| 20 | `docs/SECURITY.md` | HIGH | Silent on the second exposure class. Never says the repository is **public**; never mentions sample identifiers, the two history rewrites (`.gitignore:107-112`, `:146-152`), or `tests/test_identifier_exposure.py`. Its "What it does not catch" now reads as more complete than it is. | Retitle + `## Identifiers` section — §3.11 S3 |
| 21 | `docs/SECURITY.md` credential table | MEDIUM | Omits `NEXTSEEK_TOKEN`, `FDH_TOKEN` (which *wins* over `FDH_API`), the four `OMERO_*`, `CEDAR_API_KEY`, and the fact that `sampletype_attr.py` — the only script that writes a production schema — takes the NExtSEEK credentials. | Replace the table — §3.11 S1 |
| 22 | `docs/SECURITY.md` | MEDIUM | `$DMAC_ENV_FILE`, the actual bootstrap mechanism since `ad82c51`, is absent — the one document about credentials does not say how credentials arrive. | Insert `## How a project gets its .env` — §3.11 S2 |
| 23 | `docs/` (31 files, ~34,500 lines) | MEDIUM | No index; 30 of 31 files frozen with nothing marking them so. Three spec status lines are falsified by shipped code, one of them by commits landing the same day. | New `docs/README.md` + three status-line amendments — §3.10 |

### Tier 3 — wrong routing, wrong invocation, wrong counts

| # | file | severity | what's wrong | fix |
|---|---|---|---|---|
| 24 | `README.md:58` **and** `SKILL.md:145` (merged: README F3 + SKILL F3; SCHEMA auditor confirms SCHEMA.md is *not* at fault) | HIGH | `/curate-assay-vocabulary` filed under `schema` mode in both. It is an `assay` command (`64f233d`, `curate-assay-vocabulary.md:5`, `ASSAY.md:35`, `SKILL.md:34`) that **refuses to run without an open run**. The README also gives `assay-hygiene/` as its path — the default path `_writeguard` refuses, 33 symlinks into `assets/RUN1/` (`ASSAY.md:57-59`). | Delete the schema row; two replacement lines in SKILL.md — §3.1 F3, §3.3 F3 |
| 25 | `SKILL.md:73` + `PHASES.md` (12 lines) + `SCHEMA.md:52-58` (merged: SKILL F4 + PHASES F8 + SCHEMA S4) | HIGH | Hard rule 6 prescribes `uv run --script` universally. **Reproduced:** it raises `ImportError: attempted relative import with no known parent package` on every `assay_hygiene` module. Meanwhile every PHASES.md invocation line is a bare path (violating the rule), and no `scripts/schema/` module is a CLI at all (no `main`, no `argparse`). One rule, three different truths. | Rewrite rule 6 with both forms; 11 line-for-line PHASES replacements; a "none of these is a CLI" note in SCHEMA.md — §3.3 F4, §3.4 F8, §3.8 S4 |
| 26 | `SKILL.md:75,112` + `PHASES.md:244,257` + `REPORTS.md:100` (merged: SKILL F6 + REPORTS R5) | MEDIUM | "all four sources" against a harvest `SKILL.md:85-86` defines as **five**. The omitted source 4 is *the named deposit itself*, which `SKILL.md:101-104` calls "ground truth for the data tier" — the single most valuable source for report mode. An off-by-one on a rule labelled "never violate". | Change the count in all five places; REPORTS.md gets a rewritten paragraph — §3.3 F6, §3.4, §3.9 R5 |
| 27 | `README.md:7`, `pyproject.toml:3` (merged: README F1 + SKILL F8) | MEDIUM | README says v0.3.0, `pyproject.toml` says 0.3.0, three tested artefacts say 0.4.0 — and 0.4.0 itself predates the whole assay mode. `pyproject.toml` is covered by no test (`test_dependency_pinning.py` reads it but checks only pins). | Bump per §5 Q1, add a pyproject-version test — §3.1 F1, §3.3 F8 |
| 28 | `PHASES.md:322-333` | MEDIUM | Phase 7 drops the mandatory re-run of Phase 6. `assay_ids` is resolved only while a flat sheet is written (`consolidate_to_flat.py:136-151`); no other writer exists. The real order is 6 → 7 → 6, and the doc presents 1→13 as a line. | Append step 6 + a loop note + sharpen the Phase 6 edge case — §3.4 F4 |
| 29 | `PHASES.md:66,269,304-308` | MEDIUM | Phase 6 never names `Arm{X}_review.xlsx`, written unconditionally at `consolidate_to_flat.py:492` — the file the flat sheet's own README tells the curator to read (`:332-336`). This undercuts PHASES.md's own "Phase 5 is what a person looks at" argument. | Add `### The review twin` + amend the table row and step 3 — §3.4 F3 |
| 30 | `README.md:37,64,124` | MEDIUM | The consolidate artifact is `Arm{X}-upload.xlsx`, not `Arm{X}.xlsx` (`consolidate_to_flat.py:490`). The bare form exists in the code only as a **legacy name the script deletes on re-run** (`:357-359`). `templates/CLAUDE.md.j2:29` carries the same stale name into every scaffolded project. | Three one-line edits + the template — §3.1 F4 |
| 31 | `PHASES.md:431` | MEDIUM | The OMERO backfill line omits a required positional. `apply_omero_ids.py:72-77` declares `xlsx` as argument 1; run as documented, argparse exits 2 before any work. `commands/curate-deposit.md:54` has the same defect. | Replace the two lines — §3.4 F6 |
| 32 | `PHASES.md:455` | MEDIUM | Phase 11's edge case ("No upload-new sheets present: refuse") contradicts its own Inputs line nine lines above and `build_retrieve.py:31-39`, which falls back to `-upload`. Following it makes the agent refuse a phase that would have run. | Replace the edge case — §3.4 F7 |
| 33 | `PHASES.md:9-29` | MEDIUM | The phase table omits 9b — which the doc itself calls "the last gate before upload" (`:392`) — and "14 commands drive 12 phases" now reads as the whole plugin's count when the plugin ships 26 across five modes. | Replace the header + table — §3.4 F9 |
| 34 | `SKILL.md:42-43`, `:38` (merged: SKILL F2 + F5) | MEDIUM | "one mode among four"; and "`/curate-status` reports per mode" when `scripts/status.py:182-188` builds exactly four keys and has no `assay` branch. `commands/curate-status.md:5` carries the same stale phrasing. | Two line edits — §3.3 F2, F5 |
| 35 | `ASSAY.md:35` | MEDIUM | The `curate-assay-vocabulary` row claims an operator sheet, an ingest, and a **ruling-store** write. The command writes only `$RUN/04-artifacts/vocabulary-proposed.csv` at `provenance = proposed`, the lowest precedence, excluded from tiering (`_schema.py:618`). | Replace the row — §3.6 A2 |
| 36 | `ASSAY.md:26-28` | MEDIUM | "Lab was the discriminator in three of the five … 3.9%" has no in-repo source. `migrate_rulings.py:115-119` splits those five by **source lane**, not lab; and 3.9% is 5/127 attached to a 3-of-5 subclaim. | Replace the paragraph — §3.6 A7 |
| 37 | `ASSAY.md:61-64` | MEDIUM | No backup path, no restore line, no resume story — for a mode whose store is gitignored and unregenerable. `init_run.py:48`'s own refusal message advertises `--migrate-from`, **a flag that does not exist**. | Add `## Backup, restore, and resuming` — §3.6 A9 |
| 38 | `SCHEMA.md:11-14` | LOW | Says 856 single-use field names. **I re-ran `field_index` myself: 857** (`101 1059 857`). `field_index.py:7-8` and the 2026-07-21 spec both say 857. | One-character fix — §3.8 S3 |
| 39 | `SCHEMA.md:52-58` | MEDIUM | The module table omits `templates.py` — 139 lines, the mode's **only** field-naming source (`SCHEMA.md:143` says so itself), the only consumer of `CEDAR_API_KEY`. The `review.py` row omits `<TYPE>.proposed.json`, which is never named anywhere in SCHEMA.md. | Replace the table + the not-a-CLI note — §3.8 S4 |
| 40 | `SCHEMA.md:224-230` | MEDIUM | `## Open question` treats "what apply means" as unsettled. It was answered, tooled and verified end to end on production 2026-07-31 (`commands/curate-sampletype.md:152-165`). | Narrow the question, add the live-write section — §3.8 S2 |
| 41 | `SCHEMA.md:152-154` | LOW | Pinned-template field counts (28/27/22) contradict `templates.py:17-18` (25/24/20). Not determinable offline — the template is a third-party `bibo:draft` fetched live and deliberately never vendored. Quoting it in three places guarantees two are wrong. | Remove the numbers — §3.8 S5 |
| 42 | `REPORTS.md:49-51`, `:168-174` | MEDIUM | Synthesized GEO study prose never reaches `GEO_filled.xlsx`. `render_geo` shells out to `geo_build_xlsx.py`, which reads only `samples` and `paired_end_experiments` and re-pastes STUDY rows verbatim (`:52-53`, `:23`). The curator sees the prose in the JSON and ships a blank STUDY block. | Add the caveat + rewrite the open question — §3.9 R2 |
| 43 | `FDH.md:4` | LOW | "the 13-phase NExtSEEK pipeline" — `PHASES.md:9` says 12 phases across 11 numbers. `tests/test_mode_table.py:73` bans the phrase in SKILL.md **only**, which is why it survived here and at `commands/fdh-upload.md:7`. | Replace the paragraph, widen the test — §3.7 F2 |
| 44 | `FDH.md:28,35` | MEDIUM | The reuse-or-generate loop's library can never populate. `.gitignore:154-156` ignores `scripts/fdh/generated/*.py` (verified with `git check-ignore`), so step 1 finds an empty library on every installed copy **forever**, and step 5 cannot commit what it wrote. The `--write` guard it promises has no lint, no test and no helper. | Replace the loop — §3.7 F3 |
| 45 | `FDH.md:39-48` | MEDIUM | Omits `fdh_api.py`'s own five-verb read CLI (`:234-274`). "What samples are linked to assay 123?" is one `list assays 123 samples` call; the doc sends the agent to generate a script instead. | Insert `### The read-only CLI` — §3.7 F4 |
| 46 | `FDH.md:8-9` | MEDIUM | Auth omits `FDH_TOKEN` (checked *first*, so it wins), `--token`, `--user`, and the bare `sys.exit(2)` when `FDH_API` holds two or more entries with no `--user` (`fdh_api.py:172-195`) — the shape the doc's own example implies is normal. | Extend the auth bullet — §3.7 F5 |
| 47 | `README.md:88-107` | MEDIUM | The repo-layout tree omits `ASSAY.md`, `scripts/assay_hygiene/` (40 modules, the largest package by far), `tests/` (92 files, the largest tracked directory), `pyproject.toml`/`uv.lock`, and `CHANGELOG.md`. | Replace the tree — §3.1 F6 |
| 48 | `README.md:111-113,141-147` | MEDIUM | Install and update bypass the `marketplace.json` the repo ships and the machine actually uses (`~/.claude/plugins/known_marketplaces.json` registers `dmac` → this checkout; `installed_plugins.json` records `dmac-curation@dmac`). A new user following the README ends up with a checkout the plugin system does not read. | Replace both blocks — §3.1 F7 |
| 49 | `README.md:133` | LOW | "The other three modes need no project" — there are four others, and `assay` needs no *curation project* but does need the plugin checkout as cwd. **My own finding**, not in any audit. | One-line edit — §3.1 F8 |

**Nitpicks dropped: nine.** README's pipeline bullet omitting QC (a summary sentence; the
table below it is correct); `scripts/deposit/` glossed as "builders" for one renderer
(generous, not wrong); README's Auth omitting `BIOPORTAL_API_KEY` (it explicitly delegates
to `docs/SECURITY.md`); REPORTS.md's module table omitting `scrub_fixture.py` (a test
fixture utility); REPORTS.md's artifact column omitting `<FORMAT>_filled.json` (an
intermediate); SCHEMA.md's `MUS::Strain` example diverging from the API spec's
`M.Mice::Strain` (illustrative); PHASES.md's `consolidate_to_flat.py:19-21` citation being
off by one at the start (the range still contains the text); `assay_sheets/pending_schema/`
being agent-only (true of the command files too, so not drift specific to any one doc); and
`scripts/fdh/generated/REGISTRY.md`'s `_(none yet)_` row, which **is correct in this
worktree** — see §3.12.

**Auditor disagreement resolved.** `inventory-scripts-subpkgs.md:708-712` claims
`scripts/deposit/` is missing from the README tree; the README auditor says it is present. I
read `README.md:103` — `│   └── deposit/  # external deposit builders`. **The inventory is
wrong; the README is right.** No finding.

---

## 3. Per-file change plan

### 3.1 `README.md`

Seven audit findings plus one of mine. The README is the front door and carries the two
false safety promises, so it should be fixed first after the version decision (§5 Q1).

**F1 — replace line 7:**

```markdown
**Status:** v0.5.0
```

(Or `v0.4.0` if the operator declines the bump — see §5 Q1. The point is that it must match
`plugin.json`, `marketplace.json` and `scripts/_lockfile.py:29`, which
`tests/test_identity_sync.py:90-97` already pins together. `_lockfile.PLUGIN_VERSION` is
stamped into every project's `.dmac-curation.json` at `/curate-init`, so a curator reading
the README and then their own lockfile currently sees two versions for one install.)

**F2 — replace line 11:**

```markdown
The plugin is organised as five **modes**. A mode is a convention, not a framework:
entry-point commands, a reference doc loaded on demand, and optionally its own scripts.
```

**F2 — add a fifth bullet after line 24:**

```markdown
- **`assay`** — assay hygiene: find samples that should be registered against an internal
  assay and are not, put every proposal in front of a human, write the approved ones to
  production. **House-scoped** — one extract, all projects, no PI — so it runs from the
  plugin checkout itself (the directory holding `scripts/` and `assets/`), not from a
  curation project. Reference: [`skills/curation/ASSAY.md`](skills/curation/ASSAY.md).
```

**F2 — add a fifth command table between the `schema` and `report` tables:**

```markdown
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
```

> Note on the original draft: the README auditor's version of the `/curate-assay-write` row
> ended "and `--confirm`". The ASSAY/FDH auditor established that `--confirm` **does not
> exist** — `grep` finds it only in `commands/curate-assay-write.md:8` and in
> `tests/test_assay_hygiene_commands.py:40`, which merely asserts the string appears in the
> doc. I have dropped it from the row above rather than propagate a flag that is not real.
> The command file's own claim is a separate defect for whoever owns `commands/`.

**F2 — amend the Any-mode table (lines 66-70):**

```markdown
**Any mode**

| command | does |
|---|---|
| `/curate-status` | show toolkit state for `pipeline`, `fdh`, `schema` and `report` (assay mode has its own `/curate-assay-status`) |
```

**F3 — delete line 58 entirely** (the `/curate-assay-vocabulary` row in the `schema` table),
leaving `/curate-sampletype` as that table's only row. The assay table above carries it. Its
three defects were: wrong mode (`64f233d` is titled "absorb curate-assay-vocabulary into the
mode"), wrong prerequisite (it needs an open run), and a path — `assay-hygiene/` — that is
the default `_writeguard` refuses, resolving to 33 symlinks into the immutable `assets/RUN1/`.

**F4 — three one-line edits.** Line 37:

```markdown
| `/curate-consolidate` | collapse the 4-sheet sheets to flat-format `Arm{X}-upload.xlsx`, plus `Arm{X}_review.xlsx` (one sheet per sample type, for humans) |
```

Line 64:

```markdown
| `/curate-report` | GEO / SRA / PRIDE submission artifacts from UIDs, a workbook, an `Arm{X}-upload.xlsx`, or tabular data |
```

Line 124:

```markdown
/curate-consolidate     # → assay_sheets/Arm*-upload.xlsx + Arm*_review.xlsx
```

(and the same name at `templates/CLAUDE.md.j2:29`, which is rendered into every scaffolded
project — out of this audit's file scope, same one-line fix).

**F5 — replace lines 72-79 wholesale:**

```markdown
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
```

**F6 — replace lines 90-107:**

````markdown
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
````

**F7 — replace lines 111-113:**

````markdown
```bash
# Install (the repo ships .claude-plugin/marketplace.json — a marketplace named `dmac`)
git clone git@github.com:cdemurjian/dmac-curation.git ~/code/dmac-curation
```

Then in Claude Code:

```
/plugin marketplace add ~/code/dmac-curation
/plugin install dmac-curation@dmac
```
````

**F7 — replace lines 141-147:**

````markdown
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
````

**F8 (mine) — replace line 133:**

```markdown
The other four modes need no curation project. `fdh`, `schema` and `report` run wherever
you are; `assay` runs from the plugin checkout itself:
```

---

### 3.2 `CHANGELOG.md`

**What changes and why.** The file stops at `0.4.0 - 2026-07-31` and 214 commits have landed
since, including the fifth mode, the plugin's first production write path, `/curate-init`
auto-detection, the UID-stamp collision guard, `pull-db`, `$DMAC_ENV_FILE` provisioning, OBI
and CEDAR grounding in schema mode, and the fix that reclassified 99,449 impossible Mode 2
proposals. A reader scanning newest-first is currently told that CEDAR is out of scope
(`CHANGELOG.md:148-150`) as the last word, when `5115789` shipped a module that reads a
pinned CEDAR template over the live API — the drafted `### Changed` section supersedes that
line deliberately.

**Insert verbatim after line 3** (`All notable changes to dmac-curation will be documented
in this file.`) and above `## 0.4.0 - 2026-07-31`. Headed `## Unreleased`; promote to
`## 0.5.0 - <date>` only together with the version bump in §5 Q1.

```markdown
## Unreleased

A fifth mode. `assay` is house-scoped assay hygiene — one production extract, all
projects, no PI — and it is the first thing in this plugin that writes to production.
Alongside it: `/curate-init` learned to guess the project, the lab and the PI;
`/curate-build` gained a UID-stamp collision guard; and `schema` mode gained two
external grounding sources.

### Added

- **`assay` mode - 8 commands, `skills/curation/ASSAY.md`, 39 modules under
  `scripts/assay_hygiene/`.** It finds NExtSEEK samples that should be registered
  against an internal assay and are not, puts every proposal in front of a human, and
  writes the approved ones to production. The order is `/curate-assay-init` →
  `-vocabulary` → `-detect` → `-review` → `-resolve` → `-write`, with `-status` and
  `-backup` safe at any point. **House-scoped, not project-scoped:** one extract, all
  projects, no lockfile, no PI. 44 test modules cover it.
- **Numbered immutable runs.** `/curate-assay-init` creates `assets/RUN<n>/` with eight
  tiers and chmods `00-rulings` through `06-findings` read-only **at creation**, not at
  the end - a tier that is writable for the duration of a run is a tier the run can
  destroy, and the artifacts most worth protecting are written first. State is
  `assets/assay-run.json`; a second `init` refuses while one is open, because two
  concurrent write phases assign `MAX(id)+1` primary keys with no lock.
- **A durable ruling store that outlives the runs** - `assets/rulings/pairs.tsv`, keyed
  on `(sample_type, internal_assay_id, action)`. RUN1 filed verdicts under
  `lab|sample_type|parent_types|assay_title|field|value`; four of those six fields move
  with the extract, so a new extract matched almost none of them and **261 rulings
  became worthless without a single judgement having changed**. The pair key survives
  all four. It is also *coarser* than the cohort it was ruled against: measured on
  RUN1, 200 ruled rows collapse to 127 keys and 5 of those carry conflicting verdicts.
  **A conflict is escalated, never averaged** - `rulings.save` raises rather than
  picking a winner, and `/curate-assay-init` reports conflicting keys instead of
  merging them.
- **`/curate-assay-write`, behind eight refusals** (`scripts/assay_hygiene/preflight.py`).
  Every one is a live failure mode of `/seek/sampleupload/`, not a hypothesis: a Current
  pair of two ints is the sole combination that reaches `deleteOneRecord`; an
  unparseable New pair drops the registration and reports success; a blank UID raises
  mid-run on a path with no transaction, leaving a committed prefix; a sheet named
  `UPDATE` hijacks dispatch into the metadata-update path; a row absent from the
  gate-checked manifest was never project-checked; no rollback handle means `MAX(id)`
  was never captured and the run cannot be undone; a backup without both non-zero size
  and a verified trailer is not a backup (a `mysqldump` once exited 0 having written 0
  bytes); and a chunk above 2,000 rows meets gunicorn's 1200 s SIGKILL. Rows go up in
  2,000-row chunks, each reconciled against a `COUNT(*)` - `chunker.reconcile` refuses
  an over-count as well as a short write.
- **A hard project gate on SEEK assay ids** (`scripts/assay_hygiene/resolve_targets.py`).
  SEEK assay ids are per-project: the same internal assay is a different `assay_id` in
  every project that runs it, and a registration landing on the wrong one puts the
  sample into a project it does not belong to, which nothing undoes from outside. The
  2026-08-26 audit found **578 of 26,188 rows** in exactly that state - 159 repairable,
  419 not. `resolve` now emits a manifest gate-checked at build time, and
  `assert_subset` is what `write` uses to prove the submitted sheet never grew a row the
  gate did not see. An excluded row is an authorised registration with no correct
  target, and is reported as such rather than silently dropped.
- **Backups that are read back before they are believed.** `store_backup.back_up`
  re-opens the tarball it just wrote and refuses unless `pairs.tsv` is inside.
  `/curate-assay-review` backs up on every ingest; `/curate-assay-backup` does it on
  demand. `/curate-assay-init` refuses to open a run at all when the store is missing,
  because **nothing regenerates a human ruling** - not compute, not a re-run.
- **`/curate-init` auto-detects project, lab and PI.** `scripts/detect_context.py` ranks
  projects by token overlap with your inputs, aggregates UIDs per lab code across a
  project export, boosts the lab whose author surname matches, then guesses the PI.
  Surfaced as `nextseek_api.py detect-context` and confirmed with one tap. The ranking
  logic is network-free so it is unit-testable offline.
- **`nextseek_api.py pull-db`** - download a project's full DB export into
  `previous_metadata/` and print sheet and row counts. This is the fresh pull the stamp
  guard requires.
- **`scripts/stamp_guard.py` - the UID-stamp collision guard.** Minting from N=1 into a
  `<YYMMDD><LAB>` stamp another curation batch already owns **silently overwrites that
  study on upload** (the 260730WHI / 260729WHI incidents). `preflight()` refuses a build
  unless a DB pull under 24 hours old is present and the intended stamp is unused, and
  names the nearest free stamp when it refuses. `/curate-qa` carries the matching net: a
  new UID already in the master baseline is a HARD_REJECT. Both carry environment-only
  escape hatches - `STAMP_GUARD_OVERRIDE=1` and `QA_ALLOW_DB_UPDATES=1` - which leave no
  trace on the command line.
- **`.env` provisioning from `$DMAC_ENV_FILE`.** `/curate-init` copies the file that
  variable points at to `./.env` and `chmod 600`s the copy; it never reads the values.
  Keep the filled credentials file outside every git repo and export the variable from
  your shell profile.
- **`schema` mode grounds attribute proposals in OBI and CEDAR.** BioPortal can say
  which *values* a field may take but not which *fields* a sample type should carry -
  its REST API exposes only a class's annotation properties, never the OWL restrictions
  describing an assay's inputs and outputs. Two sources now fill that gap and **neither
  mints a field**: `terms.clade_neighbors` walks a matched class's parents and children
  (OBI splits `cell viability assay` by detection chemistry - Annexin V, ATP
  bioluminescence, resorufin - which D.VIA does not capture), and
  `templates.template_fields` reads one pinned CEDAR template as a **checklist**. The
  shared library cannot be selected by assay name, so `common assay template` is pinned
  by `@id` and diffed against the type. Nothing is vendored; both degrade to an empty
  section that states its reason when `BIOPORTAL_API_KEY` / `CEDAR_API_KEY` is absent.
- **`tests/test_identifier_exposure.py`** - a ratchet on the identifier-shaped strings
  this **public** repository exposes, beside the existing credential guard. It goes red
  when the count grows *and* when it shrinks, so a cleanup tightens the baseline rather
  than leaving it stale. The two holes it started with each hid a real identifier: case
  (four protocol titles were written lowercase and an `[A-Z]{3}` pattern cannot see
  them) and binaries (`git grep -I` skips them by design, and `tests/fixtures/sample.xlsx`
  carried three UIDs inside its zipped sheet XML).

### Changed

- **The plugin has five modes, not four.** `skills/curation/SKILL.md`'s mode table now
  lists all 26 commands across `pipeline` / `fdh` / `schema` / `report` / `assay`, and
  `/curate-assay-vocabulary` moved from the `schema` row to the `assay` row.
- **CEDAR is no longer wholly out of scope.** 0.3.0 recorded why CEDAR *templates* are
  not adopted as an artifact model; that reasoning stands and nothing emits a CEDAR
  template. What changed is that a pinned CEDAR template is now *read*, over the live
  API, as a field checklist in `schema` mode.
- **The test suite now reports what it did not measure.** `tests/conftest.py` prints a
  banner naming every test skipped for a missing extract. Those fixtures carry real
  sample identifiers and this repository is public, so a fresh clone and CI always skip
  them - and a `1196 passed / 16 skipped` baseline was read as healthy for days while 21
  tests silently skipped. **A green suite is not evidence the assay pipeline was
  measured.**
- **Dependencies are declared once, in `pyproject.toml` plus a tracked `uv.lock`.** The
  bounds in `pyproject.toml` are floors - the same ones the PEP 723 headers already
  declared - and `uv.lock` is the reproducibility guarantee, which is why it is
  deliberately committed.
- **`.gitignore` gained seven exclusion classes**, each with the incident that caused it
  written above it: `assay-hygiene/` and the prefix glob `assay-hygiene-*/`; `assets/`;
  unanchored `*rulings*.tsv` and `*verdicts*.csv`; `.claude/`; and
  `scripts/fdh/generated/*.py`. Read the comments before editing it - they are the
  incident record, not decoration.

### Fixed

- **Mode 2's lineage lane never met the reachability gate.**
  `gate.type_registration_index` calls a (sample type, assay) pair absent from it
  incredible whatever the term's support, and the gate has always blocked a metadata
  claim on such a pair - but a lineage neighbour carries no claim, so nothing ever put
  the lineage lane in front of that rule. Measured on the 2026-08-21 extract, **99,449
  of 167,454 emitted Mode 2 rows - 59.4% - proposed a (type, assay) pair the house has
  never once made**, and every one reached the operator with a blank `gate`. `Evidence`
  gains a `reachable` boolean derived from the same index the gate already holds.
  **Nothing was deleted**: the rows are reclassified into their own step and still
  emitted, and the before/after `findings.csv` differ only in `classification` and
  `gate`, on exactly those 99,449 rows.
- **Internal assay 143 was named for the wrong GPT** - "Alanine Aminotransferase
  (ALT/GPT) Activity Assay", while SEEK assay 26 that it maps is the gpt delta mutation
  assay. Found by two independent agent readings during Mode 2 calibration and confirmed
  against the extract.
- **The write protection that four files claimed existed was never applied.** Resolved
  through the symlink tree, 27 of 33 artifacts were clobberable by a run left on default
  paths. `/curate-assay-init` now performs the chmod in code, and
  `_writeguard.assert_writable` refuses to write through a symlink into a preserved run.
- **A missing prerequisite is named instead of raising a bare traceback**, and the
  under-reporting in the unmeasured-work banner itself was closed.
- **Every real sample and protocol identifier is out of the tracked tree.** Each was
  *replaced*, not deleted - the surrounding assertions and prose need a well-formed
  identifier - by moving its `<YYMMDD><LAB>` batch stamp into a reserved synthetic band,
  `19MMDD`, which no uuid in the extract carries for any lab. Keep new fixtures in that
  band.

### Known issues

- **The plugin's own identity still says four modes.** The canonical description in
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `SKILL.md`
  frontmatter names `pipeline`, `fdh`, `schema` and `report` and omits `assay` - and
  skill activation matches on that string, so nothing in the activation surface mentions
  assay hygiene. `/curate-status` has no `assay` branch and `commands/curate-status.md`
  still says "all four dmac-curation modes"; the mode carries its own
  `/curate-assay-status` instead. `README.md` and `pyproject.toml` remain at 0.3.0.
- **Carry-forward carries nothing.** `carryforward.split` sorts every cohort three ways -
  already ruled, ruled in a narrower context, never seen - but nothing derives
  `ruled_width`, so callers pass `{}`, every matched pair lands in *widened*, and
  `/curate-assay-detect` re-asks everything. The split is real; the carry-forward is not
  the finished feature. Root cause is the provenance sidecar that `rulings.py` and
  `carryforward.py` both describe and nothing writes.
- **Three artifacts in the assay workflow have no producer.** `ingest.ingest` refuses a
  sheet without a literal `cohort_key` column and no review surface emits one;
  `/curate-assay-resolve` reads `approved-rows.csv`, which nothing writes; and nothing
  builds the `UPDATE_ASSAY` sheet `/curate-assay-write` submits. Until those close,
  review → resolve → write is driven by hand.
- **Two documented flags do not exist.** `curate-assay-write.md` says "It writes nothing
  without `--confirm`", and `init_run.py`'s refusal message names
  `curate-assay-init --migrate-from`. There is no CLI in the assay mode at all - every
  command is `python -c` / `python -m` snippets and the production write is a manual
  submission - so there is no flag to pass.
- **The assay commands do not follow hard rule 6.** They invoke
  `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -m assay_hygiene.<module>`
  rather than `uv run --script`, because the PEP 723 headers on those modules are inert
  under `-m` and `-c`, which is why the dependencies are passed explicitly.
- **A lost machine is a lost campaign.** The ruling store is gitignored and its only
  protection is a tarball on the same machine - the accepted cost of keeping identifiers
  out of a public repository. `git clean -xdf` lists `assets/` for removal.
```

> If the version bump in §5 Q1 is taken, delete the last sentence of the first
> "Known issues" bullet (`README.md` and `pyproject.toml` remain at 0.3.0) and the first
> bullet's opening clause, since §3.1 F1 and §3.3 F1/F8 close both.

---

### 3.3 `skills/curation/SKILL.md` (+ `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`)

**What changes and why.** The mode table at `SKILL.md:28-34` is *already correct* — the
auditor diffed its 26 command names against `ls commands/*.md` in both directions and the
sets are identical. Everything around the table still describes the four-mode plugin. The
description string is the highest-impact item because it is what skill activation matches
on, and the `assay` mode's cues (`scripts/` + `assets/`, no `files/`, no lockfile) appear
nowhere in it.

**Before applying: the description lives in FOUR files.**

```
.claude-plugin/plugin.json          "description"
.claude-plugin/marketplace.json     plugins[0].description
skills/curation/SKILL.md            frontmatter description:
tests/test_identity_sync.py         CANONICAL_DESCRIPTION
```

`test_identity_sync.py:57,61,65` asserts the first three equal `CANONICAL_DESCRIPTION` byte
for byte, so changing three of four turns the suite red. The string also lives in **unquoted
YAML frontmatter**: a mid-string `": "` makes it parse as a mapping and the skill stops
loading — `test_description_is_yaml_safe_frontmatter` (`:77`) guards exactly that. The
replacement below was round-tripped through `yaml.safe_load` by the auditor and contains no
colon-space.

**F1 — the new canonical string (845 chars, YAML-safe):**

```
Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.
```

`assets/assay-run.json` is a real, checkable cue: `runstate.py:22` sets
`LOCK_NAME = "assay-run.json"`, `:32` resolves it as `root / LOCK_NAME`,
`commands/curate-assay-status.md:9-10` calls `read(Path('assets'))`, and `ASSAY.md:11` names
it.

Apply to `SKILL.md:3` (single unquoted frontmatter line):

```yaml
description: Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.
```

Apply to `.claude-plugin/plugin.json:4`:

```json
  "description": "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.",
```

Apply to `.claude-plugin/marketplace.json:14`:

```json
      "description": "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.",
```

Apply to `tests/test_identity_sync.py:16-27` (**required** — the suite goes red otherwise):

```python
CANONICAL_DESCRIPTION = (
    "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, "
    "PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through "
    "sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to "
    "email PI), fdh (FairDomHub upload and direct API), schema (sample type "
    "authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission "
    "artifacts), assay (house-scoped assay hygiene - 8 commands that find "
    "unregistered sample-assay pairs, put every proposal in front of a human, and "
    "write the approved ones to production). Activate when working in a directory "
    "containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or "
    "any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, "
    "FairDomHub, curation, sample types, assay hygiene, assay registration, or a "
    "GEO/SRA/PRIDE submission."
)
```

and widen `tests/test_identity_sync.py:99-101`:

```python
def test_description_names_every_mode():
    for mode in ("pipeline", "fdh", "schema", "report", "assay"):
        assert mode in CANONICAL_DESCRIPTION, f"{mode} missing from description"
```

**F2 — replace `SKILL.md:42-43`:**

```markdown
12 phases driven by 14 commands. This is where most work happens, but it is one
mode among five. Deep per-phase reference: `PHASES.md`.
```

**F3 — replace `SKILL.md:145` with two lines:**

```markdown
- "unresolved terms" / "which assay does this metadata value mean" / "the assay vocabulary" → `assay` mode (`/curate-assay-vocabulary`), stage B2 — needs an open run
- "assay hygiene" / "register these samples against an assay" / "which run is open" / "rule the cohorts" → `assay` mode (`/curate-assay-status` to orient, `/curate-assay-init` to open a run)
```

**F4 — replace `SKILL.md:73` (hard rule 6).** The current form was *reproduced* failing:
`uv run --script scripts/assay_hygiene/run_detect.py --help` →
`ImportError: attempted relative import with no known parent package`.

```markdown
6. **Use `uv`, not bare `python3`.** Two invocation forms, and they are not interchangeable. Standalone scripts under `scripts/` carry PEP 723 inline-deps — run them as `uv run --script <plugin>/scripts/X.py`. `scripts/assay_hygiene/` is a **package**, not a script directory: its modules import each other relatively, so `uv run --script` on one fails with `ImportError: attempted relative import with no known parent package`. Drive it as `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "from assay_hygiene.<mod> import <fn>; ..."`, exactly as every `/curate-assay-*` command does. `scripts/schema/` is a library too — no `main()`, no `argparse` anywhere in it — so import it, do not run it.
```

**F5 — replace `SKILL.md:38`:**

```markdown
`/curate-status` reports on the `pipeline`, `fdh`, `schema` and `report` modes.
`assay` is house-scoped and has its own reporter, `/curate-assay-status`.
```

**F6 — replace `SKILL.md:75` (hard rule 8), changing "four" to "five":**

```markdown
8. **Harvest before you placeholder; for published work, flag don't placeholder.** For an **in-prep** study, use `*** PLACEHOLDER: <description> ***` for unknown values (greppable; blanks vanish). For a **published or submitted** study the metadata almost always exists — run the [Published-paper harvest](#published-paper-harvest) before writing any value, and if it is genuinely absent from all five sources, leave the cell **blank** and log the gap in `QUESTIONS_FOR_PI.md`. Never a placeholder in that case.
```

**F6 — replace `SKILL.md:112-114`:**

```markdown
- **Genuinely absent from all five** → leave the cell **blank** and add a
  name-pattern-anchored question to `QUESTIONS_FOR_PI.md`. Do **not** write a
  `*** PLACEHOLDER ***`. QA surfaces the blank; the PI fills it.
```

**F7 — insert after `SKILL.md:64` (end of the `### report` subsection):**

```markdown
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
```

> Deviation from the drafted text: the auditor's version said "It writes nothing without
> `--confirm`". `--confirm` does not exist (see §3.1 F2 note). Replaced with the true
> property — the submission is manual — which is a stronger warning, not a weaker one.

**F8 — version, if §5 Q1 is taken.** `.claude-plugin/plugin.json:3`,
`.claude-plugin/marketplace.json:15`, `scripts/_lockfile.py:29`, `pyproject.toml:3` all to
`0.5.0`; `tests/test_identity_sync.py:96-97`:

```python
def test_version_is_the_toolkit_release():
    assert _plugin_json()["version"] == "0.5.0"
```

and close the untested fourth copy by adding to `tests/test_dependency_pinning.py`:

```python
def test_pyproject_version_matches_plugin_json():
    import json
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert data["project"]["version"] == manifest["version"]
```

---

### 3.4 `skills/curation/PHASES.md`

**What changes and why.** The structure is sound and should not be touched: phase numbering,
the retired-4/8 rationale, the arm definition, the 4-sheet-vs-flat argument and the
`synonyms_by_cited_name` key are all still correct (on that last one PHASES.md is right and
`commands/curate-resolve-assays.md:24` is the file that breaks the feature). Nine findings,
all in the operational half.

**F9 — replace `PHASES.md:9-29` (header + phase table):**

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

**F1 — replace `PHASES.md:199` (Phase 5 Inputs):**

```markdown
**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master — **must be a fresh DB
pull, under 24 h old**; grab one with `uv run --script <PLUGIN>/scripts/nextseek_api.py
pull-db --project-id N`), `manuscript/`, `.dmac-curation.json` (lab + pi)
```

**F1 — replace `PHASES.md:245-251` (step 5 of the Action list):**

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

**F1 — add two edge cases at `PHASES.md:255-259`:**

```markdown
- Stale or missing DB pull: `preflight` raises before anything is minted. Re-pull with
  `nextseek_api.py pull-db --project-id N`; do not lower `max_age_hours`.
- Stamp collision: `preflight` raises with a suggested free stamp — re-mint under it.
  `STAMP_GUARD_OVERRIDE=1` downgrades the refusal to a printed warning
  (`scripts/stamp_guard.py:163`) and exists only for a deliberate, eyes-open re-upload
  into an existing stamp, never to silence a real collision.
```

**F4 — insert a note under the Phase 6 heading (`PHASES.md:265`, above `**Inputs:**`):**

```markdown
**Phases 6 and 7 are a loop, not a line.** Phase 7 needs Phase 6's output (it diffs the
cached titles against the `assay_titles` column of `assay_sheets/Arm*.xlsx`) and Phase 6
needs Phase 7's output (`context/assay_ids_cache.json` + `context/assay_synonyms.json` are
what populate `assay_ids`). Run 6 → 7 → 6. The second consolidation is not optional if
`assay_ids` came out blank the first time.
```

**F2 + F3 — replace `PHASES.md:269-271` (Phase 6 Output):**

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

**F3 — insert before `### Flat cannot carry controlled vocabulary` (`PHASES.md:273`):**

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

**F3 — amend the arm table row at `PHASES.md:66`:**

```markdown
| 6 | one flat `assay_sheets/Arm{X}-upload.xlsx` + its `Arm{X}_review.xlsx` twin |
```

**F3 — amend Action step 3 (`PHASES.md:307`):**

```markdown
3. Per arm, produce a flat xlsx with a `Samples` sheet (`uid, sampletype, name, parent,
   notes_summary, assay_titles, assay_ids, json_metadata`) and a `README` sheet, plus the
   `Arm{X}_review.xlsx` twin.
```

**F4 — sharpen the Phase 6 edge case at `PHASES.md:311`:**

```markdown
- Cache or synonyms missing: `assay_ids` is left blank. Run `/curate-resolve-assays
  --project-id N`, **then re-run this phase** — nothing patches the column afterwards.
```

**F4 — append to the Phase 7 Action list at `PHASES.md:328`:**

```markdown
6. **Suggest re-running `/curate-consolidate`.** `assay_ids` is resolved only while a flat
   sheet is being written (`consolidate_to_flat.py:136-151`); nothing backfills the column
   into an existing `Arm{X}-upload.xlsx`. A cache or synonym written now has no effect
   until Phase 6 runs again.
```

**F5 — replace `PHASES.md:355-364` (Phase 9):**

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

**F5 — insert as the first edge case at `PHASES.md:366`:**

```markdown
- UID already present in the master baseline: HARD_REJECT. On upload that row UPDATES
  (overwrites) the existing record instead of inserting — the stamp collision Phase 5's
  `preflight` exists to prevent, caught here as the second net (`qa_flat_sheets.py:165-170`,
  `:317-334`). Re-mint under a free stamp. For a deliberate update or restore, and only
  then, re-run with `QA_ALLOW_DB_UPDATES=1`, which downgrades it to
  `INFO — updates acknowledged`.
```

**F6 — replace `PHASES.md:430-431` (Phase 10, OMERO):**

```markdown
- `uv run --script <PLUGIN>/scripts/omero_pull.py all --project N` → `omero_images.csv`.
- `uv run --script <PLUGIN>/scripts/apply_omero_ids.py assay_sheets/D.IMG-upload-new.xlsx
  [--omero-csv omero_images.csv] --write` patches D.IMG `Link_PrimaryData` by filename
  match. The workbook is a **required positional argument** (`apply_omero_ids.py:73`) — the
  script discovers nothing and does not use `_config`, so both paths resolve against the
  cwd. Dry-run by default; `--write` saves and leaves a `.bak`.
```

**F2 — append to the Phase 10 GEO bullet at `PHASES.md:418`:**

```markdown
  The script reads `D.SEQ-upload-new.xlsx`, `A.GEX-upload-new.xlsx` and
  `A.SPTX-upload-new.xlsx` from `--sheets-dir` (default `assay_sheets/`) and skips, with a
  warning and exit 0, any it cannot find — check the patched-row counts, not the exit code.
```

**F7 — replace `PHASES.md:455` (Phase 11 edge case):**

```markdown
- No `-upload-new` sheets present: **not an error.** `build_retrieve.py:31-39` falls back
  to `*-upload.xlsx`, which is what `/curate-consolidate` writes. Refuse only when neither
  exists — then suggest `/curate-build` + `/curate-consolidate`.
```

**F8 — eleven line-for-line invocation replacements** (hard rule 6). Every top-level
`scripts/*.py` is mode `-rw-r--r--` with a PEP 723 header; the only executable is
`upload_geo_ncftp.sh`. As printed, none of these lines is runnable or dependency-resolved.

| line | replacement |
|---|---|
| 126 | ``Inspect every `previous_metadata/*.xlsx` via `uv run --script <PLUGIN>/scripts/inspect_workbook.py <path>`.`` |
| 156 | ``Run `uv run --script <PLUGIN>/scripts/build_sample_tree_html.py [--strict]` → `./SAMPLE_TREE.html`, the interactive review view. Both `--input` and `--output` default to cwd-relative paths (`build_sample_tree_html.py:368-369`), so run it from the project root; `--strict` (`:373`) turns a clade warning into exit 1.`` |
| 305 | ``Invoke `uv run --script <PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`.`` |
| 324 | ``Invoke `uv run --script <PLUGIN>/scripts/nextseek_api.py fetch-assays --project-id N`.`` |
| 381 | ``` `uv run --script <PLUGIN>/scripts/nextseek_api.py validate --project-id N --checks structure,dag,name_check --dump-dir <scratch> <file>` ``` |
| 417 | ``Upload with `bash <PLUGIN>/scripts/upload_geo_ncftp.sh [bulk\|spatial]` — the one executable in `scripts/`. Its positional arguments are **job names**, not paths (`upload_geo_ncftp.sh:116-134`); the local source dirs are hardcoded (`GEO/bulk_rna/GEO`, `GEO/spatial`), and a bare invocation runs both jobs. Needs `NCFTP_HOST/USER/PASS/REMOTE_BASE` in `.env`. No dry run — invoking it starts the transfer.`` |
| 418 | ``…: `uv run --script <PLUGIN>/scripts/apply_geo_accessions.py --gse-bulk GSE###### --gsm-csv <roster> [--gse-sptx GSE###### --sptx-gsm-csv <roster>] [--write]` patches D.SEQ/A.GEX/A.SPTX…`` |
| 422 | ``Drives `uv run --script <PLUGIN>/scripts/stage_zenodo.py` to preview, then … re-runs it with `--write`.`` |
| 425 | ``` `uv run --script <PLUGIN>/scripts/apply_zenodo_links.py --write --record-id N` ``` |
| 449 | ``Invoke `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]` **from the project root** — this is the one pipeline script that does not use `_config`/project-root discovery, so `--assay-sheets` and `--output` resolve straight off the cwd (`build_retrieve.py:78-84`).`` |
| 467 | ``Invoke `uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py --metadata-xlsx <xlsx> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`.`` |

**Merged finding 26 — the harvest is five sources.** Replace `PHASES.md:244`:

```markdown
4. Gather field values. For a **published/submitted** study run the Published-paper harvest (SKILL.md), all **five** sources in order: the manuscript **Methods**, **Supplemental Methods**, and **Data Availability statement**, then **the named deposit itself** (fetch it and enumerate its files — it is ground truth for the data tier), then the **master NExtSEEK sheet** (`previous_metadata/*.xlsx`). A value genuinely absent from all five is left blank and logged to `QUESTIONS_FOR_PI.md`, never placeholdered.
```

and `PHASES.md:257`:

```markdown
- Missing manifest data, **published/submitted study**: run the Published-paper harvest first (SKILL.md) — all five sources, including the named deposit. If still absent, leave blank and add a question to `QUESTIONS_FOR_PI.md` — no placeholder.
```

---

### 3.5 (reserved — no file)

---

### 3.6 `skills/curation/ASSAY.md`

**What changes and why.** 72 lines covering 8 commands, 39 modules and 40 test files, against
`PHASES.md`'s 506 lines for 14 commands and `SCHEMA.md`'s 230 for one. The problem is not
depth: four things a run cannot start or finish without are simply absent, and three
statements are actively false. This is the doc that needs the most new text.

**A3 — replace `ASSAY.md:7-11` (the run model):**

`````markdown
## The run model

Runs are numbered at `assets/RUN<n>/` and hold eight tiers:

```
assets/
  assay-run.json          the run lockfile (one run open at a time)
  rulings/pairs.tsv       the durable ruling store, OUTSIDE any run
  RUN<n>/
    00-rulings/           read-only from creation
    01-extract/           read-only   -- the parquet extract (see "Before run 1")
    02-agent-runs/        read-only
    03-stage0-applied/    read-only
    04-artifacts/         read-only   -- everything the drivers write
    05-review/            read-only
    06-findings/          read-only
    07-process/           WRITABLE    -- the only tier that is not chmodded
```

Tiers `00`–`06` are chmodded `0o555`/`0o444` **at creation**, not at the end of a
run: a tier that is writable for the duration of a run is a tier the run can
destroy (`scripts/assay_hygiene/init_run.py:24-26`, `:62-73`).

**Consequence: a driver cannot write until you unprotect its tier.** `detect` and
`vocabulary` both write into `04-artifacts`, so both need

```bash
chmod -R u+w $RUN/04-artifacts     # before
# ... run the drivers ...
PYTHONPATH=scripts uv run python -c \
  "from assay_hygiene.protect_run import protect, verify; \
   from pathlib import Path; r=Path('$RUN'); protect(r, ('04-artifacts',)); \
   print('unprotected:', verify(r, ('04-artifacts',)))"    # after
```

`commands/curate-assay-detect.md:17,33-38` carries this;
`commands/curate-assay-vocabulary.md` does not, and will fail without it.

State is `assets/assay-run.json`; one run may be open at a time, because two
concurrent write phases can silently overwrite each other's rows under
`MAX(id)+1` primary keys with no lock (`scripts/assay_hygiene/runstate.py:11-14`,
`:49-56`).
`````

**A4 — insert a new section after the run model:**

`````markdown
## Before run 1: pulling the extract

`01-extract/` is not produced by any slash command. It comes off the box, from
inside the production `nextseek` container, and nothing in the mode will run
without it.

```bash
scp -r ./scripts/assay_hygiene fairdata:/tmp/
ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' \
    < scripts/assay_hygiene/driver_extract.py
```

Read-only: SELECTs on the `seek` alias (= `seek_production`) and read-only
Cypher, writing parquet to `/tmp` inside the container
(`scripts/assay_hygiene/driver_extract.py:1-16`, `extract.py:5-11`). Copy the
result down into `assets/RUN<n>/01-extract/` before `curate-assay-init`, and
record its sha in the lockfile.

Seven files land there: `assays`, `membership`, `samples`, `nodes`, `edges`,
`parents`, `sops` (`extract.py:339`, `:346-348`). `extract.py` has a `main()`
but no `__main__` guard — `driver_extract.py` is the only way in, because
`extract.py`'s relative import fails when piped bare into the shell.

Duplicate node uuids raise **after** the writes, deliberately, so the ~260 MB
extract survives for diagnosis (`extract.py:350-360`).
`````

**A6 — insert `## The three modes` after the run model:**

```markdown
## The three modes

| mode | detects | emits |
|---|---|---|
| **Mode 1** | an unregistered sample whose own metadata makes a gated claim naming an assay | yes |
| **Mode 2** | a `DERIVED_FROM` neighbour registers an assay this sample lacks, with precedent on the hop | yes — the largest population |
| **Mode 3** | *nothing — there is no detector* | none, ever |

**Mode 3's zero is UNDETECTED, never SMALL.** `classify.mode3_findings()` takes
no argument and returns an empty frame carrying the full column contract
(`scripts/assay_hygiene/classify.py:1336`, `:1420`). The constant survives only
so the report can name the mode in order to say it found nothing
(`_schema.py:711-717`, `run_detect.py:53-55`). Increment 1's "866 contradictions"
were an absence test reported under a contradiction's name; re-disposed under
the precedence, all 866 land elsewhere and the residue is empty
(`classify.py:1340-1358`).

**Mode 2 classifies, it never drops.** 99,449 of 167,454 emitted Mode 2 rows
propose a `(sample_type, assay)` pair the house has never made. They are still
emitted, classed `CLS_UNREACHABLE` and carrying `GATE_UNREACHABLE`, because a
proposal that vanishes reads to a curator exactly like one that was never
generated (`_schema.py:768-776`). 8,971 of those fall under `CLS_BOOTSTRAP` — a
cut through the same population where the proposed assay's own population is
under 100 rows, so the gap may be a new assay finding its feet rather than a
type error (`mode2.py:142`, `_schema.py:778-789`).

The vocabulary gate runs before every mode. Only `GATE_UNREACHABLE` and
`GATE_INCOHERENT` block; `GATE_LOW_SUPPORT` is recorded on the row and does not
(`gate.py:580`, `_schema.py:744-748`). A gate-refused key emits nothing at all —
`PRE_GATE` has no lane (`classify.py:788`, `:2048-2057`).
```

**A7 — replace `ASSAY.md:24-28`:**

```markdown
A pair ruling is **coarser** than the cohort it was made against. Measured on
RUN1 over all three ruling files, 200 ruled rows collapse to 127 keys and 5 of
those carry conflicting verdicts — the operator approved one cohort and rejected
another sharing the same triple, because his judgement rested on something the
triple discards (`scripts/assay_hygiene/rulings.py:19-24`). Those 5 were excluded
from the store and put back to the operator, never resolved by a rule. Three of
the five are Mode 2 disagreeing with itself; the other two involve Mode 1, one
against itself and one against Mode 2 — the only cross-source disagreement in the
set (`migrate_rulings.py:115-119`). The measured cost of the coarser key is
therefore 5 of 127 keys, **3.9%**.

(An earlier "156 rows / 114 keys / 3 conflicts" figure circulated in the plan and
a handoff. It omitted the 44 Mode 1 rows; 5 of 127 is the true cost.)
```

**A2 — replace the `ASSAY.md:35` row:**

```markdown
| `curate-assay-vocabulary` | unresolved terms → evidence → agent proposals | `vocabulary-proposed.csv` |
```

**A5 — amend the `ASSAY.md:39` write row:**

```markdown
| `curate-assay-write` | preflight (8 refusals), chunk, **operator posts by hand**, reconcile | **production** |
```

**A5 — insert `## What is not built yet` before `## Four things that will bite`:**

```markdown
## What is not built yet

The command table is a design, not a closed loop. Three joints have no code, and
a run has to bridge each of them by hand. Check this list before planning a run.

**Review → the ruling store.** `ingest.ingest` requires a literal `cohort_key`
column and refuses the whole file without it (`scripts/assay_hygiene/ingest.py:28`,
`:39-44`), but no review surface emits that column: `review_mode2.to_csv` writes
the six key fields separately (`review_mode2.py:443-472`) and uses `cohort_key`
only as a preset lookup. You must build the `{cohort_key: pair_key}` map the
ingest snippet takes as `cohorts` yourself, from `review.cohort_key`
(`review.py:587`) — the one definition, never re-derive it.

**Review → resolve.** `curate-assay-resolve` reads
`$RUN/04-artifacts/approved-rows.csv` (`commands/curate-assay-resolve.md:19`).
**Nothing writes it.** Expanding the pair-keyed store into a row-level
`(sample_id, internal_assay_id)` frame is manual work today.

**Resolve → write.** No module builds the `UPDATE_ASSAY` sheet
(`sample_id, assay_id, uid, current_pair, new_pair`), and there is no HTTP client
anywhere in `scripts/assay_hygiene/`. `preflight.check` and `chunker.reconcile`
are a library the operator must remember to call on either side of a submission
made by hand; nothing enforces that either ran. `curate-assay-write.md:8` mentions
a `--confirm` flag — it does not exist; there is no CLI in this mode at all.
```

**A1 — replace `ASSAY.md:43-53` (the carry-forward split):**

```markdown
## The carry-forward split — designed, not yet operational

On `detect`, every cohort is sorted three ways against the store: **already
ruled** (carried), **ruled in a narrower context** (surfaced, never applied),
and **never seen** (goes to the operator).

**Today the first bucket is always empty.** Deciding that a cohort was already
ruled requires knowing how wide the original ruling was — the row count it was
made against — and that number lives in a provenance sidecar that
`init_run.migrate_into_store` computes and nothing writes to disk. Callers pass
`ruled_width = {}`, so `carryforward.split` sends every matched pair to
`ruled_in_a_narrower_context` and the run re-asks everything
(`scripts/assay_hygiene/carryforward.py:18-24`, `:52-58`). That is the safe
direction, deliberately: an unearned carry-forward writes to production, a
needless re-confirmation costs the operator a line. It is not the finished
feature. Do not plan a run on the assumption that prior rulings will be skipped.

The middle bucket is what the design is for. In RUN1, 2,830 rows shared a cohort
key with an approved cohort but sat below the precedent floor the operator's
sheet was built at, so he never saw them
(`scripts/assay_hygiene/carryforward.py:8-11`). An unknown ruled width counts as
widened, not carried — absence of evidence that a ruling covered these rows is
not evidence that it did.
```

**A9 — replace the "Nothing regenerates a human ruling" bullet at `ASSAY.md:61-64` and add a
section:**

````markdown
**Nothing regenerates a human ruling.** The store is gitignored and its only
protection is a verified tarball outside the working tree. `git clean -xdf` lists
`assets/` for removal. A lost machine is a lost campaign — the accepted cost of
keeping identifiers out of a public repository.

## Backup, restore, and resuming an interrupted run

**Backup** is part of `curate-assay-review`'s ingest, not a separate step — but
it is a third line in that command's `python -c` snippet
(`commands/curate-assay-review.md:39`), *not* a property of `ingest.ingest`,
which neither imports nor calls `store_backup`. Skip that line and the backup is
skipped silently. `/curate-assay-backup` runs it on demand.

Archives land at `~/backups/rulings-<stamp>.tar.gz`. `back_up` re-opens the
archive it just wrote and refuses to return a path unless `pairs.tsv` is really
inside (`scripts/assay_hygiene/store_backup.py:41-46`) — written after a backup
command exited 0 having produced a 0-byte file.

**Restore** is one line, because the archive holds the `rulings/` directory
itself (`arcname=store.name`, `store_backup.py:39`):

```bash
tar -xzf ~/backups/rulings-<stamp>.tar.gz -C assets/
```

`curate-assay-init` refuses to open a run when `assets/rulings/pairs.tsv` is
absent and prints that restore line (`init_run.py:35-46`). Ignore the last
sentence of its message: `curate-assay-init --migrate-from` is **not a real
flag** — there is no CLI in this mode. Migration is the inline `python -c` at
`commands/curate-assay-init.md:32-43`.

**Resuming.** `/curate-assay-status` writes nothing and reads
`assets/assay-run.json` for `run`, `open`, `step`, `extract_sha`, `carried_pairs`,
`carried_from_run` and `write.{chunks_done, rollback_id, backup_verified}`
(`runstate.py:57-69`). `step` is where the run stopped; re-run that command's
step from the top — every driver is idempotent over its own `out_dir` (unprotect
the tier first, see the run model). `runstate.update` merges the nested `write`
dict one level, so recording a rollback id cannot drop `backup_verified`
(`runstate.py:72-81`). Close a finished run with `runstate.close` before opening
the next; `runstate.create` refuses while one is open.
````

**Checked and correct — do not "fix".** `ASSAY.md:22`'s "261 rulings became worthless"
(`rulings.py:12`), `:25`'s "200 rows → 127 keys, 5 disagreed" (`rulings.py:20-21`), `:49-51`'s
"2,830 rows" (`carryforward.py:9-10`), `:58-59`'s "33 symlinks into `assets/RUN1/`"
(`_writeguard.py:7-8`), `:72`'s "578 of 26,188" (`resolve_targets.py:11`) — all exact.

---

### 3.7 `skills/curation/FDH.md`

**What changes and why.** Six findings. The auth story is wrong in the one place that
determines which server gets written to, and the self-extending-toolkit loop describes an
outcome the `.gitignore` makes impossible.

**F1 + F5 — replace `FDH.md:7-9` (one contiguous block):**

```markdown
- **Module 2 (`/fdh-api`)** — host `https://fairdomhub.org` by default; override
  with `--base-url` or `.env` `FDH_BASE_URL` (`scripts/fdh/fdh_api.py:198-201`).
- **Module 1 (`/fdh-upload`) is production-only.** `submit.py` hardcodes
  `BASE_URL = "https://fairdomhub.org/"` (`scripts/fdh/submit.py:73`) and reads no
  host from the environment; its only flags are `--step N` and `--resume`
  (`:1780-1841`). There is no staging mode. Every run writes to fairdomhub.org.
- Auth: `.env` `FDH_API` = JSON `{ "<name>": "<token>" }`. Token from
  fairdomhub.org → Profile → Actions → API Token. Never log tokens.
  - Module 2 resolves in order `--token` → `$FDH_TOKEN` → `$FDH_API`
    (`scripts/fdh/fdh_api.py:172-195`). Inside `FDH_API`: `--user NAME` selects;
    a one-entry map auto-selects; **two or more entries with no `--user` exits 2.**
  - `.env` is read from the current directory first, then the plugin checkout,
    with `setdefault` semantics — an exported shell variable wins over both
    (`fdh_api.py:159-169`).
  - Module 1 reads only `FDH_API` and picks the user through an interactive
    prompt (`submit.py:1281`, `:1295-1301`); it honours neither `FDH_TOKEN` nor
    `--token`.
```

**F2 — replace `FDH.md:3-5`:**

```markdown
Load on demand when the user wants to **upload to FairDomHub** or **access the FDH API**.
These are two independent, standalone capabilities — NOT part of the NExtSEEK curation
pipeline (12 phases across 11 numbers, `PHASES.md`); they do not consume
`assay_sheets/` / flat sheets.
```

Also fix `commands/fdh-upload.md:7` and widen `tests/test_mode_table.py:73` past SKILL.md —
the test is why the phrase survived in these two files.

**F6 — replace `FDH.md:11-21` (Module 1):**

```markdown
## Module 1 — Upload a study (`/fdh-upload`)

Interactive, human-run tool: `scripts/fdh/submit.py`. Claude checks prereqs and
hands off; it cannot answer the tool's prompts. See `commands/fdh-upload.md`.
**Production-only** — see the host note above.

Workbook format: each sheet = one Sample Type; each column = one attribute; a
`UID` column is required (it becomes the record title,
`scripts/fdh/submit.py:700`, `:869-870`). Columns whose every non-empty cell is a
URL/DOI are auto-typed URI (`column_is_all_links`, `:630-633`). Known project IDs
live in `PROJECT_MAPPING` (`:77-83`); a manual numeric id can also be entered.

Resumable via `--resume` / `--step N` (mutually exclusive; the only two flags).
Most steps write a CSV to `Assets/Output/` — step 3 does not.

| step | what it does | gate |
|---|---|---|
| 0 Config | pick user, study id, project(s), workbook | — |
| 1 Assays | `POST /assays` | confirm, default **no** |
| 2 Protocols | `POST /sops` then `PUT` the bytes | confirm, default yes |
| 3 Metadata rewrite | **overwrites your workbook in place** | confirm, default yes |
| 4 Sample types | `POST /sample_types`, one per sheet | **none** |
| 5 Samples | `POST /samples` | confirm, default yes |
| 6 Publish | PATCHes every study asset to public | confirm, default **no** |

Three of those deserve saying out loud before a run:

- **Step 3 destroys workbook formatting.** It rewrites `cfg["workbook"]` to its own
  path through a `read_excel` → `ExcelWriter` round trip (`:1495`, `:570-622`):
  cell formatting, data validation, merged cells and formulas do not survive.
  Take a copy of the workbook first — the tool keeps no backup.
- **Step 4 has no confirmation.** If `Assets/Output/sample_types_created.csv` is
  absent or does not cover the workbook's sheets, one SampleType is created on
  fairdomhub.org per sheet with no prompt (`:1568-1573`, reuse offer `:1512-1547`).
- **Step 6 always runs.** `step_publish(cfg)` is called unconditionally at `:1940`,
  outside every start-step guard, so even `--step 5` reaches it. It sets
  `policy.access` to `view` or `download` on every discovered asset — assays, SOPs,
  sample types, samples, data files, models, presentations, publications — plus a
  `manage` permission for the **first** selected project only (`:1023-1024`, `:1654`,
  `:1107-1146`). Its deny-by-default confirm is the only thing stopping it. The
  study record itself is not published.
```

**F3 — replace `FDH.md:25-37` (the reuse-or-generate loop):**

```markdown
A self-extending toolkit — but the extension is **local to your checkout**.
`scripts/fdh/generated/*.py` is gitignored (`.gitignore:154-156`: the scripts are
written against live project ids, frequently carry sample uids, and several are
destructive), so generated scripts never ship with the plugin and a fresh install
always starts with an empty library.

When the user asks for an API operation ("find all samples for assay X and delete
them"), follow the reuse-or-generate loop:

1. **Try the read CLI first** — see "The read-only CLI" below. Many tasks
   ("what is linked to assay 123?") need no script at all.
2. **Check the local library** — read `scripts/fdh/generated/REGISTRY.md`. Reuse a
   script if one fits. Expect it to be empty on a fresh checkout; that is normal.
3. **Consult the index** — `context/fdh_api_index.json`, a list of enriched
   endpoint entries: `path, method, operation_id, summary, category,
   primary_entities, intent_patterns, llm_hint, yaml_lines`. Match on
   `intent_patterns` / `category` / `llm_hint`. Every DELETE entry's `llm_hint` is
   prefixed "DESTRUCTIVE — irreversible on the live repo"
   (`scripts/fdh/build_api_index.py:129`).
4. **Pull only the relevant YAML** — `Read` `context/full-fdh-openapi-spec.yaml` at
   each chosen entry's `yaml_lines` `[start, end]`. Never load the whole 640 KB file.
5. **Generate + run** — write a script under `scripts/fdh/generated/` (template below).
6. **Record it** — add a `REGISTRY.md` row and show the diff. `REGISTRY.md` is
   tracked and the script is not, so committing the row alone would ship a pointer
   to a file nobody else has: commit the row only if the user wants the *description*
   shared, and say plainly that the script itself stays local.

Nothing enforces the dry-run/`--write` convention — no lint, no test, no shared
helper. It holds only because the generating agent follows the template.

Regenerate the index after an API bump: `uv run --script scripts/fdh/build_api_index.py`.
It rewrites `context/fdh_api_index.json` **inside the plugin checkout**
(`build_api_index.py:22-24`, `:177`); show the diff.
```

**F4 — insert before `### The shared client`:**

`````markdown
### The read-only CLI — try this before generating anything

`fdh_api.py` is also a CLI with five read verbs
(`scripts/fdh/fdh_api.py:234-274`). Every subcommand takes `--token`, `--user`
and `--base-url`.

```bash
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py whoami
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py search "<query>" [--type samples]
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py get assays 123
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py list assays 123 samples
uv run --script <PLUGIN>/scripts/fdh/fdh_api.py download-blob <url> --out <path>
```

**There is no write verb, by design.** `post` / `patch` / `delete` exist on the
client but are wired to no subcommand — "used by generated scripts, never by this
read CLI" (`fdh_api.py:146`). Every FDH write goes through a per-task generated
script carrying its own `--write` gate. Transient `429/502/503` are retried up to
5 times with exponential backoff (`fdh_api.py:35`, `:69-89`); anything else `>=400`
raises `FDHError`.
`````

**Checked and correct — do not "fix".** `FDH.md:19-21`'s workbook-format claims,
`:41-48`'s ten client methods, `:32`'s "640 KB" (640,626 bytes), and `:105-107`'s
`Assets/Output/session.json` plaintext-token warning (`submit.py:1225-1230`) are all exact.

---

### 3.8 `skills/curation/SCHEMA.md`

**S1 — replace `SCHEMA.md:16-19` (State scope):**

```markdown
## State scope

**cwd.** Reads the plugin's `context/` read-only; writes everything into the
current working directory under `schema/`. No lockfile, no scaffold, no project.

The single exception is `/curate-sampletype apply`, which writes to a **live
NExtSEEK server** and defaults to production. See
[Applying: the one live-write path](#applying-the-one-live-write-path).
```

**S1 — replace `SCHEMA.md:216-222` (Non-goals):**

```markdown
## Non-goals

- Writing to NExtSEEK *from the proposal path*, or editing `sampletypes_db.json`
  in place. The one exception is the explicit `apply` verb — see
  [Applying: the one live-write path](#applying-the-one-live-write-path).
- Emitting CEDAR templates (see tree vs graph).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).
```

**S3 — replace `SCHEMA.md:11-12`.** I re-ran the module's own functions:
`load_catalog`/`build_field_index` returns `101 1059 857`. `field_index.py:7-8` and
`docs/superpowers/specs/2026-07-21-schema-mode-design.md:17` both say 857; SCHEMA.md is the
lone outlier.

```markdown
The problem it attacks: of **1059 distinct field names across 101 sample types,
857 are used by exactly one type**, and none of the 1059 carries a description,
```

**S4 — replace `SCHEMA.md:52-58` (the Modules table):**

```markdown
| module | responsibility |
|---|---|
| `scripts/schema/field_index.py` | catalog loading, field usage index, the reuse check, Tags mining |
| `scripts/schema/dictionary.py` | observed-value mining, the lazy cwd-only field dictionary |
| `scripts/schema/ontology.py` | controlled-value proposals with sources, the `<TYPE>.ontology.json` artifact |
| `scripts/schema/terms.py` | BioPortal lookup; suggests, never binds; degrades with no key |
| `scripts/schema/templates.py` | CEDAR reference-template checklist — the only source that names *fields*; the only consumer of `CEDAR_API_KEY`; degrades to an empty section without one |
| `scripts/schema/review.py` | renders `<TYPE>.review.md` (the deliverable) and `<TYPE>.proposed.json` (a catalog-shaped record, for diffing) |

**None of these is a CLI.** There is no `main()`, no `argparse` and no
`if __name__` anywhere in `scripts/schema/`, so SKILL.md hard rule 6
(`uv run --script …`) does not apply here. The contract is
`sys.path.insert(0, "<PLUGIN>/scripts")` then `from schema import field_index`.
```

**S5 — replace `SCHEMA.md:149-154`.** The counts cannot be settled offline: the pinned
template is a third-party `bibo:draft` v0.0.1 fetched live and deliberately never vendored
(`templates.py:49-51`), and three files quote three different numbers.

```markdown
**A checklist, not a lookup.** The shared library cannot be selected by assay
name - `viability`, `flow cytometry`, `sequencing` and `metabolomics` all return
zero hits - so templates are pinned by `@id` and diffed against the type.
Quality varies enormously and only well-specified templates are worth pinning:
`REFERENCE_TEMPLATES` (`scripts/schema/templates.py:52-55`) holds exactly one,
`common assay template`, while the Pistoia Alliance template carries 7 fields
with no descriptions and no bindings and is deliberately left out. **Field counts
are not quoted here on purpose:** the pinned template is a third-party
`bibo:draft` at v0.0.1, fetched live and never vendored, so any number goes stale
without warning. Run `template_fields(REFERENCE_TEMPLATES["common assay
template"])` and report what actually comes back.
```

**S2 — replace `SCHEMA.md:224-230` with a new section plus a narrowed open question:**

`````markdown
## Applying: the one live-write path

Everything above produces artifacts a human applies by hand. `/curate-sampletype
apply <TYPE> --add <FIELD>` is the one exception: it adds an attribute to a live
sample type through `scripts/sampletype_attr.py`, normally as the handoff from
`/curate-qc` after the server rejected a field that genuinely ought to exist.
`commands/curate-sampletype.md` is the authority; this is what a reader of
SCHEMA.md needs to know before they get there.

**Why a bespoke tool.** `PATCH /nextseek_api/sample_types/{id}/` is a 1:1
pass-through to SEEK, and SEEK's `allow_new_attribute?` refuses any sample type
that already has samples — nearly all of them — surfacing through NExtSEEK's
proxy as a generic `502 "Invalid upstream response"`. `sampletype_attr.py`
instead drives NExtSEEK's own native editor (`GET /seek/attribute/save/` → Django
ORM → `sample_attributes`) and calls `updateSampleType` to reconcile existing
samples' `json_metadata`.

**This is a GLOBAL, SHARED-SCHEMA WRITE.** Sample types are not project-scoped:
adding `Notes` to `A.TITR` changes that type for every project and every existing
`A.TITR` record across NExtSEEK.

**The guards, exactly.** The ORM path bypasses Rails, and therefore bypasses every
SEEK model validation. Four things stand in:

1. `sampletype_attr.py::_validate` (`scripts/sampletype_attr.py:180-206`)
   re-implements the three validations that matter —
   `validate_attribute_title_unique`, `validate_attribute_accessor_names_unique`,
   `validate_one_title_attribute_present`. These are the ONLY protection on this
   path; the `/seek/samples/attributes/` web page offers none of them.
2. **Dry run is the default.** `add`, `remove` and `selftest` print the exact
   record and send nothing unless `--apply` is passed.
3. **Production needs a second flag.** `_confirm_production`
   (`scripts/sampletype_attr.py:290-317`) refuses `--apply` against
   `nextseek.mit.edu` (`PRODUCTION_HOSTS`, `:63`) unless `--yes-production` is
   given too. `--yes-production` is stripped from `argv` before parsing, so it may
   appear anywhere on the command line.
4. **Rehearse on dev.** `--base-url https://nextseek-dev.mit.edu` (or
   `NEXTSEEK_BASE_URL`) targets dev, where the same types exist in the same shape.
   `DEFAULT_BASE_URL` is production (`:62`).

```bash
uv run --script <PLUGIN>/scripts/sampletype_attr.py list <TYPE>
uv run --script <PLUGIN>/scripts/sampletype_attr.py add <TYPE> --title <FIELD> --type Text
uv run --script <PLUGIN>/scripts/sampletype_attr.py --base-url https://nextseek-dev.mit.edu \
    add <TYPE> --title <FIELD> --type Text --apply
uv run --script <PLUGIN>/scripts/sampletype_attr.py \
    add <TYPE> --title <FIELD> --type Text --apply --yes-production
```

**Two things that will bite.** A change is invisible to `/curate-qc` and to batch
upload until the NExtSEEK app workers restart —
`prefetch_sample_type_attributes` caches sample_type_id → attribute titles in a
module-level dict with no TTL and no invalidation on write, so the web page shows
your attribute while validation still denies it. And the ORM path skips the Rails
callbacks that trigger Solr reindexing, so a new attribute may not be searchable
in SEEK until a reindex (unverified).

**When NOT to apply.** If the server rejected a field because *we* got it wrong —
invented it, mis-cased it, or copied a typo out of `sampletypes_db.json` — fix the
build script instead. Patching a shared schema to accommodate our own error
pollutes a shared vocabulary.

## Open question

**What "apply" means beyond adding an attribute.** Adding an attribute to an
existing type is settled, tooled and verified end to end (`Notes` on `A.TITR`,
dev then production, 2026-07-31). Still unsettled: how a human applies a *whole
proposed sample type record* — NExtSEEK's admin UI, a SQL update, or a PR against
a schema repo. Confirm with the NExtSEEK admin before telling a curator to create
a type; `<TYPE>.review.md` says exactly that. `sampletype_attr.py` is itself a
declared stopgap — superuser-only, a GET with JSON in query params — expected to
be superseded by a proper `nextseek_api` REST write endpoint wrapping
`DBtable_sampleattribute` + `DBtable_sample.updateSampleType`.
`````

**Answered directed question.** SCHEMA.md never claims `/curate-assay-vocabulary` —
`grep -n -i vocabulary` returns 8 hits and none names the command. The misrouting is at
`SKILL.md:145` and `README.md:58` (finding 24).

---

### 3.9 `skills/curation/REPORTS.md`

**R1 — replace `REPORTS.md:21-25` (the Formats table) and append a note:**

```markdown
| format | sections to map | row section | target type | artifact |
|---|---|---|---|---|
| GEO | `samples` (the spec also declares `study`, `protocols`, `paired_end_experiments`, `checksums`) | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries`, `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata_filled.xlsx` + `SRA_biosample_filled.xlsx` |
| PRIDE | `project_metadata`, `file_mapping`, `sample_metadata` | `sample_metadata` | `D.MSP` | `submission.px` |

**`project_metadata` is not optional for PRIDE.** `render_pride` writes one `MTD`
line per `project_metadata` key (`scripts/report/render.py:161-163`), and
`validate_pride_px` returns `SchemaInvalid` — HARD_REJECT — for a `.px` carrying
no `MTD` lines (`scripts/report/validate_artifact.py:308-309`). A PRIDE mapping
that omits the section renders a file that fails stage 2 every time.
```

**R2 — replace `REPORTS.md:49-50` (keep `:51-53`):**

```markdown
Directives: `source`, `via_lineage`, `const`, `map`, `synthesize`, `unmapped`.
`synthesize` is study-level only, so it stays O(1).

**Caveat for GEO: synthesized study prose does not reach the xlsx.** `render_geo`
does not render — it writes `filled` to a temp JSON and shells out to
`scripts/deposit/geo_build_xlsx.py` (`scripts/report/render.py:55-62`, needs `uv`
on PATH, 300s timeout). That script reads only `data["samples"]` and
`data.get("paired_end_experiments", [])` and re-pastes the template's STUDY and
PROTOCOLS rows verbatim (`scripts/deposit/geo_build_xlsx.py:52-53, :23`). A
`study` block in a GEO mapping reaches `report/GEO_filled.json` and
`GEO.completeness.md` but **nothing transfers it into `GEO_filled.xlsx`** — the
curator still fills the STUDY block by hand before submitting, and should be told
so. SRA and PRIDE write every mapped section.
```

**R3 — replace `REPORTS.md:60-65` (the input-adapter table):**

```markdown
| input | behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | needs an injected `fetch` callable — see below |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}-upload.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

**The UID adapters ship no HTTP client.** `adapt_uids` / `adapt_retrieve_txt`
take a `fetch=` callable and unnest whatever it returns; the shape they expect is
the five-level `POST /nextseek_api/admin/samples/retrieve/` response
(`scripts/report/adapters.py:62-84`). **With `fetch=None` they return zero samples
silently** (`:70-71`) — not an error. Nothing in `scripts/` supplies that callable
today; only the tests do. So either wire the call yourself against
`scripts/nextseek_api.py`, or use one of the three local-read adapters. Prefer
the local ones — the curated sheet is the documented GEO input anyway, because GEO
deposit happens *before* NExtSEEK upload.
```

**R4 — replace `REPORTS.md:77-91` (Two-stage validation):**

```markdown
## Two-stage validation

**Stage 1, before applying:** every target field exists in the template; every
required (`*`) field is `source`/`const`/`synthesize` or explicitly `unmapped`
with a reason; every `source` column exists in the input; and a column that lives
only on ancestors carries `via_lineage`.

**CV checking is narrower than it sounds.** `const` and `map` outputs are checked
only for the nine fields `cv_for_field` recognises
(`scripts/report/mapping.py:44-60, :132-140`): eight SRA-keyed names plus GEO's
`*single or paired-end`, which uses a GEO-specific list held in code because the
vendored CV was mined from SRA and holds `paired`, not `paired-end`. GEO's
`*instrument model` is deliberately free text. **PRIDE has no controlled
vocabulary at all** — `pride.json` declares no `controlled_vocabulary` key — so
nothing in a PRIDE mapping is ever CV-checked.

**Stage 2, after rendering:** the vendored artifact validator. Its statuses map
onto the pipeline's vocabulary: `Valid` = CLEAN, `Incomplete` = SOFT_FLAG,
`SchemaInvalid` / `Missing` / `Unreadable` = HARD_REJECT.

**Known gap, verified: SRA `libraries` validation has no teeth.** `SRA.json`'s
`libraries` section stars nothing — `sample_name`, `library_ID`,
`library_strategy` and the rest are all bare — so `required_fields` returns `[]`
and any readable `SRA_metadata_filled.xlsx` reports `Valid` / CLEAN
(`scripts/report/validate_artifact.py:83-91`). `biosamples` does star its fields,
so SRA is not unguarded overall, but never read CLEAN on the metadata workbook as
evidence it is complete. Read `SRA.completeness.md` instead.

**Row parity is asserted only when the mapping declares it.** `RowParityError`
fires when `row_scope.expected_rows` is set and the produced row count differs
(`scripts/report/execute.py:153-159`); stage 1 checks the same number against the
input (`scripts/report/mapping.py:189-194`). Omit `expected_rows` and neither
check runs — which is how an adapter that silently returned zero samples ends up
as an empty artifact. **Always set it.** chat_nextseek's own assessment calls that
guard the single most valuable idea to carry over.
```

**R5 (merged finding 26) — replace `REPORTS.md:95-101`:**

```markdown
Some GEO fields are derivable only from context an input may lack - organism,
tissue and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. First run the
Published-paper harvest (SKILL.md), all **five** sources in order: the manuscript
Methods, Supplemental Methods and Data Availability statement, then **the named
deposit itself**, then the master NExtSEEK sheet (`previous_metadata/*.xlsx`).
The deposit matters most here — for a report-mode run it is ground truth for the
data tier (file counts, filenames, checksums), which is precisely the tier GEO,
SRA and PRIDE ask about. Only when all five come up empty does the field degrade:
```

**R2 — replace `## Open question` (`REPORTS.md:170-174`):**

```markdown
**Does `synthesize` need manuscript access?** Study title, summary and
experimental design are prose that likely live in `manuscript/`. In a curation
project that is available; input-scoped runs elsewhere may have nothing, in
which case these become placeholders. That degradation is implemented and
tested; whether it is acceptable in practice is a curator's call. Note the GEO
caveat above before spending effort here: for GEO the answer currently lands only
in `GEO_filled.json` and `GEO.completeness.md`, never in `GEO_filled.xlsx`.
```

---

### 3.10 `docs/README.md` (new file) and three spec status lines

**Why.** 31 files, ~34,500 lines, no index. Exactly one file (`SECURITY.md`) is maintained;
30 are frozen. A contributor opening the newest spec about the newest subsystem is told on
line 3 that the work is "Not implemented", seven commits after it shipped.

**Three status-line amendments, in place.**

`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md:3`:

```markdown
**Status:** design approved 2026-08-27; **SHIPPED the same day** in `d1f4d14`…`833e9be`.
The status line below is preserved as written; see `docs/README.md` for what is current.
**Supersedes:** nothing. **Absorbs:** `commands/curate-assay-vocabulary.md` — absorbed
*into the mode*, not deleted; the command file is live.
```

(Its §1 line 33 also calls `assay` the *fourth* mode alongside `pipeline`, `schema` and
`report`, omitting `fdh`. It is the fifth.)

`docs/superpowers/specs/2026-08-04-init-auto-detect-project-lab-design.md:3`:

```markdown
**Status:** Approved (design). **IMPLEMENTED** 2026-08-04 — see
`docs/superpowers/plans/2026-08-04-init-auto-detect.md`, `scripts/detect_context.py`
and `nextseek_api.py detect-context`.
```

`docs/superpowers/specs/2026-08-12-assay-hygiene-design.md:3-4`:

```markdown
**Status:** design approved 2026-08-12/13. **SUPERSEDED.** Stage 0 shipped
(`scripts/assay_hygiene/stage0.py`), stages A–F were redesigned as three modes on
2026-08-14, and assay hygiene is now a plugin mode. Read
`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` and
`skills/curation/ASSAY.md` for what is current.
```

**The new `docs/README.md`, in full:**

```markdown
# `docs/`

What is in here, and which of it is still true.

**Only `docs/SECURITY.md` is maintained.** Everything else under `docs/` is dated by
construction: a design spec records what was decided on the day it was written and is
not revised when the code moves past it, an implementation plan is an execution record,
and a finding is a measurement taken against one extract on one day. **A `Status:` line
inside a spec is part of that frozen record, not a claim about the repository today** —
three of them are known to be stale and are marked below.

The living reference documentation is not under `docs/` at all:

| where | what it is |
|---|---|
| `README.md` | layout, modes, commands, quick start |
| `skills/curation/SKILL.md` | the mode table, 8 hard rules, 7 soft rules, 20 pitfalls |
| `skills/curation/{PHASES,FDH,SCHEMA,REPORTS,ASSAY}.md` | one reference doc per mode |
| `commands/*.md` | the authority on what each slash command actually does |
| `context/VINTAGE.json`, `context/PROVENANCE.json` | the vintage of every bundled snapshot |
| `.gitignore` | the exclusion rules, each with the incident that caused it |

## Start here

New to the repository, in this order:

1. `README.md`
2. `skills/curation/SKILL.md` — the mode table is the one place all five modes are listed
3. `docs/SECURITY.md` — mandatory before touching credentials, `working/`, or any
   curation output
4. `.gitignore` — read the comments. This repository is **public** and has already
   needed two history rewrites
5. `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md` — what a "mode" is,
   and why nothing is registered in `plugin.json`
6. `tests/conftest.py` — why a green suite may have measured nothing

## Living reference

| file | what it is |
|---|---|
| [`SECURITY.md`](SECURITY.md) | Credentials and identifiers. Where each credential comes from and which script consumes it; the three places credentials have actually turned up on disk; the two identifier incidents that cost history rewrites; and how `tests/test_no_plaintext_secrets.py` and `tests/test_identifier_exposure.py` enforce both. **Fix this file when it drifts.** |

## Design specs — historical

Frozen at their date. Read for *why* a decision was made, never for what the code does.

| file | subject | status as of 2026-08-27 |
|---|---|---|
| [`specs/2026-05-27-dmac-curation-plugin-design.md`](superpowers/specs/2026-05-27-dmac-curation-plugin-design.md) | the original 13-phase pipeline as a plugin | superseded by the 2026-07-21 toolkit design; the pipeline is now 11 numbered phases + 9b |
| [`specs/2026-07-02-fdh-integration-design.md`](superpowers/specs/2026-07-02-fdh-integration-design.md) | FairDomHub as two standalone modules | shipped (0.2.0); still describes `fdh` mode accurately |
| [`specs/2026-07-21-curation-toolkit-design.md`](superpowers/specs/2026-07-21-curation-toolkit-design.md) | **the architecture document: what a "mode" is** | shipped (0.3.0). The closest thing to a living architecture reference; predates `assay` |
| [`specs/2026-07-21-pipeline-rework-review.md`](superpowers/specs/2026-07-21-pipeline-rework-review.md) | review verdict on the pipeline; two steps that do not earn their place | acted on in 0.3.0 |
| [`specs/2026-07-21-report-mode-design.md`](superpowers/specs/2026-07-21-report-mode-design.md) | `report` mode — one declarative mapping spec, O(columns) | shipped (0.3.0); mirrored by `skills/curation/REPORTS.md` |
| [`specs/2026-07-21-schema-mode-design.md`](superpowers/specs/2026-07-21-schema-mode-design.md) | `schema` mode — sample-type authoring, human applies | shipped (0.3.0). **Predates OBI clade + CEDAR grounding** (2026-08-27); `skills/curation/SCHEMA.md` is current |
| [`specs/2026-08-04-init-auto-detect-project-lab-design.md`](superpowers/specs/2026-08-04-init-auto-detect-project-lab-design.md) | auto-detect project / lab / PI at `/curate-init` | **its status line is STALE** — it says "pending implementation plan"; the plan exists and the code shipped 2026-08-04 |
| [`specs/2026-08-12-assay-hygiene-design.md`](superpowers/specs/2026-08-12-assay-hygiene-design.md) | assay hygiene v1: complete the lineage graph, then backfill | **STALE and superseded** — its status line says "stage 0 not implemented" and "Not a plugin mode yet"; both are false |
| [`specs/2026-08-14-assay-hygiene-three-mode-design.md`](superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md) | three equal modes over one evidence layer | **amended twice**, the second superseding the first. Its own header says "Do not plan from the sections below without reading that amendment first" |
| [`specs/2026-08-27-assay-hygiene-mode-design.md`](superpowers/specs/2026-08-27-assay-hygiene-mode-design.md) | assay hygiene as a curation mode — the run model, the ruling store, the write path | **the current assay design.** Its status line is STALE: it says "Not implemented" and it shipped the same day. It also calls `assay` the *fourth* mode; it is the fifth |

### The three assay-hygiene specs contradict each other, by design

They are three successive designs, not three views of one. Read only the newest
(`2026-08-27`) for the shape of the mode as it ships, and `skills/curation/ASSAY.md` for
the operator-facing contract. The 2026-08-12 and 2026-08-14 specs survive because the
*arguments* in them — why stage 0 exists, why absence is not contradiction, why Mode 3
has no detector — are not repeated anywhere else.

## Implementation plans — historical

SDD execution records. Several carry figures the work itself later moved; the commit
messages are the authority on what actually landed. **Do not plan from these.**

| file | lines | plan |
|---|---|---|
| [`plans/2026-05-27-dmac-curation-plugin.md`](superpowers/plans/2026-05-27-dmac-curation-plugin.md) | 2,738 | the original 13-phase plugin |
| [`plans/2026-07-02-fdh-integration.md`](superpowers/plans/2026-07-02-fdh-integration.md) | 1,248 | the two FDH modules |
| [`plans/2026-07-21-curation-toolkit.md`](superpowers/plans/2026-07-21-curation-toolkit.md) | 12,503 | pipeline → toolkit; the largest file in the repository |
| [`plans/2026-08-04-init-auto-detect.md`](superpowers/plans/2026-08-04-init-auto-detect.md) | 650 | `detect_context.py` + `nextseek_api.py detect-context` |
| [`plans/2026-08-12-assay-hygiene.md`](superpowers/plans/2026-08-12-assay-hygiene.md) | 1,974 | the six-stage assay pipeline |
| [`plans/2026-08-13-assay-hygiene-stage0.md`](superpowers/plans/2026-08-13-assay-hygiene-stage0.md) | 1,726 | the 90,534-edge `DERIVED_FROM` backfill |
| [`plans/2026-08-14-assay-hygiene-evidence-layer-and-mode-3.md`](superpowers/plans/2026-08-14-assay-hygiene-evidence-layer-and-mode-3.md) | 2,189 | evidence layer + Mode 3 |
| [`plans/2026-08-17-assay-hygiene-mode-1-and-2-detection.md`](superpowers/plans/2026-08-17-assay-hygiene-mode-1-and-2-detection.md) | 640 | vocabulary gate + Modes 1 and 2 |
| [`plans/2026-08-21-assay-hygiene-mode2-generation-rework.md`](superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md) | 738 | stop the 99,449 unreachable proposals without deleting the 2,035 real ones |
| [`plans/2026-08-27-assay-hygiene-prerequisites.md`](superpowers/plans/2026-08-27-assay-hygiene-prerequisites.md) | 794 | four defects that would let run 2 destroy run 1's evidence |
| [`plans/2026-08-27-assay-hygiene-ruling-store.md`](superpowers/plans/2026-08-27-assay-hygiene-ruling-store.md) | 657 | the durable cross-run ruling store |
| [`plans/2026-08-27-assay-hygiene-mode-commands.md`](superpowers/plans/2026-08-27-assay-hygiene-mode-commands.md) | 2,760 | the eight `curate-assay-*` commands |

## Findings — point-in-time measurements

Each is true of the extract and the code at its date. None is maintained.

| file | what it measured |
|---|---|
| [`assay-hygiene-increment-2-deferred-minors.md`](assay-hygiene-increment-2-deferred-minors.md) | 52 review findings judged real and deliberately not fixed, rescued 2026-08-18 from a gitignored SDD ledger before its worktree was torn down |
| [`findings/2026-08-21-assay-143-name-collision.md`](findings/2026-08-21-assay-143-name-collision.md) | internal assay 143 is named for the wrong GPT |
| [`findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md`](findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md) | read-only audit of 170,786 findings rows. **Its `assay-hygiene-bak/` paths do not resolve in a clone**, and it says so |
| [`findings/2026-08-21-mode2-lineage-lane-is-ungated.md`](findings/2026-08-21-mode2-lineage-lane-is-ungated.md) | the root cause of 99,449 impossible proposals. **Fixed** in `c06c2c6` |
| [`findings/2026-08-21-pre-rework-baseline.md`](findings/2026-08-21-pre-rework-baseline.md) | the measured row table the rework's deltas are judged against, derived by a committed script |
| [`findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md`](findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md) | what the chosen NExtSEEK assay write route does, its cost, and the one open question. Source read on a dev box, not in this repo |
| [`findings/2026-08-24-the-operators-rulings-against-the-reworked-detector.md`](findings/2026-08-24-the-operators-rulings-against-the-reworked-detector.md) | the rework is exactly neutral against 111 hand rulings |
| [`findings/2026-08-25-the-prose-figure-census.md`](findings/2026-08-25-the-prose-figure-census.md) | an AST + `tokenize` census of the 6,984 numeric literals in the comments and docstrings of `scripts/assay_hygiene/` (26 modules) and `tests/test_assay_hygiene_*.py` (23 files), answering "which figures are trustworthy" |

## Audits

| directory | what it is |
|---|---|
| `audit/2026-08-27-docs-audit/` | ground-truth inventories of commands, skills, scripts and repo furniture, plus the drift audits derived from them and the resulting `PROPOSAL.md`. A snapshot at `833e9be`, not a maintained reference |

## Adding a document here

- A **finding** carries its date in the filename and states, in its first paragraph,
  what it measured and against which extract. If it cites a path outside the repository,
  say so — `findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md` is the
  model.
- A **spec** carries a `Status:` line. When the work ships, amend that line rather than
  the body: the body is the argument, and the argument stays true.
- A **plan** is written once and not maintained.
- Anything a reader needs in order to *use* the plugin belongs in `skills/curation/` or
  `commands/`, not here.
- **No document under `docs/` may carry a real sample or protocol identifier.** See
  `docs/SECURITY.md`.
```

---

### 3.11 `docs/SECURITY.md`

**What changes and why.** Last touched 2026-07-21, before 0.4.0 released. Its entire
*Enforcement* section was verified line for line and must not be touched. Three findings.

**S3 — retitle and add a scope line at the top:**

```markdown
# Security: credentials, and identifiers

**This repository is PUBLIC.** Two classes of thing must never reach it: credentials,
and the real sample and protocol identifiers that curation output carries. They have
different guards, different failure modes, and different remedies. Both are below.

## Credential handling

### Rule
```

**S1 — replace the whole credential table under *"Where credentials go instead"*:**

```markdown
| credential | source | consumed by |
|---|---|---|
| `FDH_API` (`{"user": "token"}`) or `FDH_TOKEN` | shell environment, or a `.env` in the **curation project** cwd | `scripts/fdh/fdh_api.py`, `scripts/fdh/submit.py`. `FDH_TOKEN` is checked first and wins |
| `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD`, or `NEXTSEEK_TOKEN` | shell environment, or project cwd `.env` | `scripts/nextseek_api.py`, and `scripts/sampletype_attr.py` — **the one script that writes a production sample-type schema**. `sampletype_attr.py` also honours the legacy name `NEXTSEEK_USER` and `NEXTSEEK_BASE_URL` |
| `MIT_USER` / `MIT_PASS` | shell environment, or project cwd `.env` | `scripts/smb_pull.py` |
| `OMERO_USER` / `OMERO_PASSWORD`, or `OMERO_SESSIONID` / `OMERO_CSRFTOKEN` | shell environment; the password is prompted for if unset | `scripts/omero_pull.py` |
| `NCFTP_*` | shell environment, or project cwd `.env` | `scripts/upload_geo_ncftp.sh` |
| `BIOPORTAL_API_KEY` | shell environment, or project cwd `.env` | `schema` mode ontology lookup (`scripts/schema/terms.py`, `scripts/schema/ontology.py`) |
| `CEDAR_API_KEY` | shell environment, or project cwd `.env` | `schema` mode reference-template checklist (`scripts/schema/templates.py`). Absent, it makes no network call and renders an empty section |
```

**S2 — insert after the credential table:**

```markdown
## How a project gets its `.env`

Keep one filled credentials file **outside every git repository** and point
`$DMAC_ENV_FILE` at it from your shell profile:

    export DMAC_ENV_FILE="$HOME/.config/dmac/.env"

`/curate-init` copies that file to `./.env` in the curation project and `chmod 600`s
the copy. It never reads the values, and it never writes one into the plugin checkout.
With `$DMAC_ENV_FILE` unset or missing, init falls back to rendering `.env.example` and
says so.

The copy lives in the *project*, not here — which is why the rule above is scoped to
this checkout. A project `.env` is still a plaintext credential on disk: it inherits
the project's own `.gitignore` (rendered from `templates/gitignore.j2`), and rotating a
token means rotating it at the provider, not deleting the copies.
```

**S3 — insert after the existing *"What it does not catch"* section:**

```markdown
---

## Identifiers

Credentials are not the only exposure. Curation output — the production extract, the
rulings, the agent verdicts, the review surfaces, the handoff reports — carries real
sample UIDs and protocol titles, and one of those titles carries a person's name.

**This has gone wrong twice, and both times cost a history rewrite.**

- **2026-08-21.** `assay-hygiene-bak/` held 195 MB of real sample metadata while
  matching no `.gitignore` pattern. The rewrite stripped **1,570 sample identifiers**
  from history.
- **2026-08-25.** Six `.claude/reports/*.json` handoff reports, which quote protocol and
  sample identifiers verbatim, were committed and the branch had to be rewritten.
- **2026-08-24**, caught before it landed: `mode2-rulings-backup-2026-08-20.tsv`, a
  byte-identical copy of the whole ruling file, sat untracked and unignored in the
  repository root.

### What that bought

`.gitignore` now excludes by **name and prefix**, not by location, precisely because
each of those escaped a location-scoped rule: `assay-hygiene/` **and** `assay-hygiene-*/`;
`assets/`; unanchored `*rulings*.tsv` and `*verdicts*.csv`; `.claude/`;
`scripts/fdh/generated/*.py`. Every one of those lines has its incident written above
it. **Read the comments before editing that file**, and when you add an exclusion, add
the reason.

### The guard

`tests/test_identifier_exposure.py` is a **ratchet on identifier-shaped strings in
tracked files**, not a ban — a test suite about UID grammar needs well-formed UIDs. It
goes red when the count grows and red again when it shrinks, so a cleanup tightens the
baseline instead of leaving it stale.

Two tiers: a pattern-only tier that runs everywhere (including CI and a fresh clone,
which is exactly where an accidental commit is most likely), and a verified tier that
runs only where the extract exists and names the smaller true number. The verified
baselines are **0**.

Two holes it had, each of which hid a real identifier, both now closed:

1. **Case.** Four real protocol titles were written lowercase; an `[A-Z]{3}` pattern
   cannot see them. The pattern is case-tolerant by character class rather than by a
   flag, so `git grep -E` and Python agree.
2. **Binaries.** `git grep -I` skips them by design, and `tests/fixtures/sample.xlsx`
   carried three UIDs inside its zipped sheet XML. One test opens tracked bytes and zip
   members instead of grepping.

**Scanning a diff answers "am I adding one". Only scanning the whole tracked tree
answers "is one there".** A 2026-08-25 pre-push scan checked one push's diff, reported
clean, and was correct — while 97 occurrences already sat in 22 tracked files.

### Writing a fixture that needs an identifier

Do not invent a free-form one, and do not restore a real one. The 2026-08-25 cleanup
*replaced* every real identifier rather than deleting it, by moving its `<YYMMDD><LAB>`
batch stamp into a **reserved synthetic band, `19MMDD`**: no uuid in the extract carries
a 19xx date for any lab, so a UID stamped `19MMDD` is provably not a person's sample,
while the type prefix, lab code and serial are preserved so every documented
relationship still reads. Protocol titles moved the same way, under lab codes absent
from all 553 SOP titles. **Keep new fixtures in those bands.**

### If an identifier lands in history

Unlike a credential, there is nothing to rotate. The only remedy is a history rewrite
plus a force-push, and every clone and every open branch has to be re-based onto it.
That asymmetry is the reason the `.gitignore` rules are deliberately over-broad.
```

Also amend the existing *"What it does not catch"* line "Credentials outside `working/` —
nothing else in the checkout is scanned" to say it is true of *this* guard, and point at
the identifier guard, which scans the entire tracked tree including binaries and zip members.

---

### 3.12 `scripts/fdh/generated/REGISTRY.md`

**No change in this worktree.** I verified it: `ls -a scripts/fdh/generated/` returns
`__init__.py` and `REGISTRY.md` only, so the `_(none yet)_` row at `:10` is **correct here**.
Two independent auditors reached the same conclusion. The drift named in the session brief
is in the main tree and is already fixed uncommitted there.

The structural point belongs in `FDH.md` instead (§3.7 F3): `.gitignore:154-156` ignores
`scripts/fdh/generated/*.py` (confirmed by `git check-ignore -v`), so this registry is
permanently empty on every installed copy of the plugin, and a committed row would ship a
pointer to a file nobody else has. If the operator wants that stated where a reader will
meet it, add one line under the existing preamble:

```markdown
Generated scripts are gitignored (`.gitignore:154-156`) — they are written against live
project ids and several are destructive. This registry is therefore **local to your
checkout** and starts empty on a fresh install. A committed row without its script is a
pointer to a file nobody else has; commit one only when the *description* is worth
sharing.
```

---

## 4. New documentation that should exist but does not

Three, each justified by a defect above that has no home in any existing file.

### 4.1 `CONTRIBUTING.md` (repo root)

*Justification:* the plugin's identity string lives in **four** files locked together by a
test, and nothing tells a contributor that. That is the mechanism behind findings 17 and 27,
the two most systemic items in this report.

```markdown
# Contributing to dmac-curation

## Things that live in more than one file

- **The canonical description** — `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `skills/curation/SKILL.md` frontmatter, and
  `tests/test_identity_sync.py::CANONICAL_DESCRIPTION`. All four must match byte for
  byte; the first three are asserted equal to the fourth. It is unquoted YAML
  frontmatter, so it must contain no `": "` — a colon-space makes the skill stop
  loading altogether.
- **The version** — `plugin.json`, `marketplace.json`, `scripts/_lockfile.py`,
  `pyproject.toml`, `README.md`, `tests/test_identity_sync.py`, `tests/conftest.py`.
  See `docs/RELEASING.md`.
- **The mode table** — `SKILL.md` is the source; `tests/test_mode_table.py` asserts it
  against `commands/` and against the reference docs.

## Adding a command

1. `commands/<name>.md` with frontmatter `description`.
2. A row in the right mode's table in `skills/curation/SKILL.md`.
3. A row in the right table in `README.md`.
4. If the command is the first of a new mode, everything in "Adding a mode" below.

## Adding a mode

A mode is a convention, not a framework: entry-point commands, a reference doc loaded on
demand, and optionally its own scripts. Nothing is registered in `plugin.json`. What must
change: the mode table in `SKILL.md`, a `### <mode>` subsection in `SKILL.md`, a new
`skills/curation/<MODE>.md`, the mode bullet and command table in `README.md`, the
canonical description in all four places above, `scripts/status.py` if `/curate-status`
should report it, and a `CHANGELOG.md` entry.

## Invocation forms — they are not interchangeable

- Standalone `scripts/*.py` — PEP 723 inline deps, run with `uv run --script`.
- `scripts/assay_hygiene/` — a package; relative imports mean `uv run --script` raises
  `ImportError`. Drive it with `PYTHONPATH=scripts uv run --with pandas --with pyarrow
  python -c ...`.
- `scripts/schema/`, `scripts/report/` — libraries, no `main()`. Import them.

## Two guards you will meet

- `tests/test_no_plaintext_secrets.py` — credentials.
- `tests/test_identifier_exposure.py` — a ratchet on identifier-shaped strings in tracked
  files. It goes red when the count grows *and* when it shrinks. New fixtures use the
  reserved `19MMDD` synthetic band. This repository is **public**; read `docs/SECURITY.md`
  before adding any fixture derived from real data.

## Documentation is not optional

`commands/*.md` is the authority on what a command does; `skills/curation/*.md` is the
authority on how a mode works. A behaviour change that lands without the matching doc
edit is an incomplete change. Nothing tests prose against code — that is why the
2026-08-27 audit found 55 drift findings.
```

### 4.2 `docs/RELEASING.md`

*Justification:* the version is stranded in two of four places and 0.4.0 predates an entire
mode, because the release procedure is unwritten. Finding 27.

```markdown
# Releasing

The version lives in seven places. Change all seven in one commit.

| file | field |
|---|---|
| `.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` | `version` |
| `scripts/_lockfile.py` | `PLUGIN_VERSION` — stamped into every project's `.dmac-curation.json` at `/curate-init` |
| `pyproject.toml` | `version` |
| `README.md` | the `**Status:**` line |
| `tests/test_identity_sync.py` | the literal in `test_version_is_the_toolkit_release` |
| `tests/conftest.py` | the fixture lockfile's `plugin_version` |

## Procedure

1. Promote `## Unreleased` in `CHANGELOG.md` to `## X.Y.Z - <date>`; move anything not
   actually shipping back under a fresh `## Unreleased`.
2. Change the seven fields above.
3. `uv run pytest tests/test_identity_sync.py tests/test_lockfile.py
   tests/test_dependency_pinning.py tests/test_mode_table.py`
4. `uv run pytest` — and read the skip banner `tests/conftest.py` prints. A green suite
   with the extract absent has not measured the assay pipeline.
5. Reinstall from the marketplace and confirm the version the plugin reports.

## What earns a minor bump

A new mode, a new command, or a new write path. A doc-only pass does not.
```

### 4.3 `tests/README.md`

*Justification:* 92 tracked files, the largest directory in the repo, absent from the README
tree (finding 47); and the changelog records that a `1196 passed / 16 skipped` baseline was
read as healthy for days while 21 assay tests silently skipped.

```markdown
# tests/

## Running

`uv run pytest`. Read the banner `conftest.py` prints at the end: it names every test
skipped for a missing extract.

**A green suite is not evidence the assay pipeline was measured.** The assay fixtures
depend on a production extract that is gitignored and not present in a fresh clone or in
CI, so a large block of tests skips by default. The banner exists because that block was
read as healthy for days.

## What guards what

| file | guards |
|---|---|
| `test_identity_sync.py` | the description and version across `plugin.json`, `marketplace.json`, `SKILL.md` — and the YAML-safety of the frontmatter string |
| `test_mode_table.py` | `SKILL.md`'s mode table against `commands/` and the reference docs |
| `test_no_plaintext_secrets.py` | credentials under `working/` |
| `test_identifier_exposure.py` | a two-directional ratchet on identifier-shaped strings in tracked files, including binaries and zip members |
| `test_dependency_pinning.py` | `pyproject.toml` pins |
| `test_deposit_write_safety.py` | every deposit script defaults to dry-run |

## Fixtures with identifiers

Use the reserved synthetic band `19MMDD` for UID batch stamps and the reserved lab codes
for protocol titles. See `docs/SECURITY.md`.
```

---

## 5. Open questions for the operator

**Q1 — version: bump to 0.5.0, or ship the changelog as `## Unreleased`?** The two audits
disagree. The skill/manifest auditor says bump all four places to 0.5.0; the changelog
auditor drafted `## Unreleased` because promoting it is a seven-file change. **My reading:
bump.** 0.4.0 is dated 2026-07-31 and its changelog entry cannot account for a fifth mode, 8
of 26 commands, 39 script modules, or the plugin's first production write path — a reader of
the manifest currently sees a version whose release notes describe a different product. But
the decision is yours, and everything in §3 works either way: only §3.1 F1 and §3.3 F8 change.

**Q2 — is `--confirm` a missing flag or a stale doc?** `commands/curate-assay-write.md:8`
promises it; there is no CLI in the assay mode at all, and the only other occurrence in the
repo is a test asserting the string appears in the doc. Same question for
`curate-assay-init --migrate-from`, advertised by `init_run.py:48`'s own refusal message.
I have documented both as not existing. If they are meant to exist, that is code work and
the doc text above changes.

**Q3 — the three unbuilt joints: document or build?** `cohort_key` on a review surface,
`approved-rows.csv`, and the `UPDATE_ASSAY` sheet builder each have no producer, so
review → resolve → write is manual. §3.6 A5 documents that honestly. If they are close to
shipping, the honest text is a liability the day they land; if they are not, a reader
planning a run needs it today.

**Q4 — should `docs/` historical material be archived rather than indexed?** §3.10 proposes
an index that marks 30 of 31 files frozen. The alternative is moving specs, plans and
findings under `docs/archive/` so the tree itself says so. The index is cheaper and
reversible; the move is clearer and breaks every existing link. I recommend the index now
and the move only if `docs/` keeps growing.

**Q5 — is the bare-clone install still supported?** §3.1 F7 documents the marketplace flow,
which is what this machine actually uses. I did not test whether cloning into
`~/.claude/plugins/dmac-curation` still works via legacy directory discovery. If it does,
both paths should be documented; if it does not, the README has been wrong for some time.

**Q6 — the CEDAR template field count (28 vs 25).** `SCHEMA.md:152`,
`commands/curate-sampletype.md:187` and `templates.py:17` disagree, and the template is
fetched live from a third party so no offline check settles it. §3.8 S5 removes the number
from SCHEMA.md. If you would rather keep a number, someone must make the live call — and
then the same number needs removing from the other two files anyway.

---

## 6. Application order

Grouped so each step is independently verifiable and nothing depends on a later step.

**Step 0 — decide Q1 (version).** Everything else is written to work either way.

**Step 1 — identity, in one commit.** The new canonical description in all four files
(§3.3 F1), the `test_description_names_every_mode` widening, and — if Q1 is *bump* — the
version in `plugin.json`, `marketplace.json`, `_lockfile.py`, `pyproject.toml`,
`test_identity_sync.py`, `conftest.py`, plus the new `pyproject` version test (§3.3 F8).
*Verify:* `uv run pytest tests/test_identity_sync.py tests/test_mode_table.py
tests/test_lockfile.py tests/test_dependency_pinning.py` — green. Then reload the skill and
confirm it still activates (a stray `": "` in the frontmatter silently disables it).

**Step 2 — `SKILL.md`.** F2, F3, F4, F5, F6, F7 (§3.3). This is the always-loaded layer and
every other doc defers to it, so its hard rules must be right before the reference docs cite
them. *Verify:* `uv run pytest tests/test_mode_table.py`; grep `SKILL.md` for `four` and
confirm every survivor is deliberate; re-read hard rule 6 against one assay command file.

**Step 3 — `README.md`.** All eight edits (§3.1), plus the `Arm{X}-upload.xlsx` name at
`templates/CLAUDE.md.j2:29`. *Verify:* every command named in the README exists in
`commands/` and vice versa (26 = 26); the version matches step 1; no occurrence of
`Arm{X}.xlsx` without the `-upload` suffix remains.

**Step 4 — `CHANGELOG.md`.** Insert the drafted entry (§3.2), adjusted per Q1. *Verify:*
`grep -c 'curate-assay' CHANGELOG.md` is no longer 0; if Q1 was *bump*, the heading date and
the manifest version agree.

**Step 5 — the five mode reference docs, in this order.** `ASSAY.md` first (§3.6 — the
largest gap and the most dangerous mode), then `PHASES.md` (§3.4 — the most findings),
then `FDH.md` (§3.7), `SCHEMA.md` (§3.8), `REPORTS.md` (§3.9). *Verify after each:* every
`file:line` citation the new text introduces still resolves at HEAD; every command line in
a fenced block parses against the script's `argparse` (read it, do not run anything that
touches a server); `uv run pytest tests/test_fdh_reference_docs.py tests/test_mode_table.py`.

**Step 6 — the "all four sources" family, as one sweep.** `SKILL.md:75`, `:112` (done in
step 2), `PHASES.md:244`, `:257`, `REPORTS.md:100`. *Verify:* `grep -rn "all four"
skills/ commands/` returns nothing that refers to the harvest.

**Step 7 — `docs/`.** New `docs/README.md`, the three spec status-line amendments, and
`docs/SECURITY.md` (§3.10, §3.11). *Verify:* every relative link in `docs/README.md`
resolves; `docs/SECURITY.md`'s Enforcement section is byte-identical to what it was — it was
verified correct and must not move.

**Step 8 — the three new files** (§4): `CONTRIBUTING.md`, `docs/RELEASING.md`,
`tests/README.md`. *Verify:* `docs/RELEASING.md`'s seven-file table matches what step 1
actually changed.

**Step 9 — full suite and a real activation check.** `uv run pytest`, and **read the skip
banner** — a green run with the extract absent has not measured the assay pipeline. Then
reinstall from the marketplace and confirm the plugin reports the intended version and that
a prompt mentioning "assay hygiene" activates the skill.

**Out of scope for this proposal, but surfaced by it** — someone owns these:
`commands/curate-status.md:5,26-31` ("all four modes"), `commands/curate-deposit.md:54`
(missing OMERO positional), `commands/curate-resolve-assays.md:24` (`"synonyms"` vs
`synonyms_by_cited_name`, which breaks the feature), `commands/curate-assay-vocabulary.md`
(no `chmod` before writing to `04-artifacts`), `commands/fdh-upload.md:7` ("13-phase"),
`commands/curate-report.md:114-118` (four sources), `scripts/schema/ontology.py:13-14` (a
stale comment about PHASES.md), and `scripts/status.py:8,182-188` (no `assay` branch).
