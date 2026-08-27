# Drift audit — `README.md`

Target: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs/README.md` (152 lines)
Worktree: branch `dev-docs`, HEAD `833e9bee85c22cb89ca399409187bb2cfcb9faf5` (2026-08-27 16:55:34 -0400)
Auditor: read every source file cited below directly; no finding rests on an inventory alone.

**Verdict: SUBSTANTIAL_DRIFT.**

The README is one release behind and one whole mode behind. It declares v0.3.0 against a
repo that is 0.4.0 in all three authoritative places, and it declares "four modes" against a
repo that registered a fifth (`assay`, 8 commands, a 40-module package, its own reference
doc) in commits `d1f4d14`/`eb8777e`/`64f233d`. Seven of the 26 shipped commands appear
nowhere in the README; the eighth appears filed under the wrong mode with a path that
resolves to a directory the mode's own docs forbid writing to. Two of the three
"What this is not" promises — the load-bearing safety claims — are now false: the plugin
does write to a live NExtSEEK sample type (`/curate-sampletype apply`, shipped in 0.4.0)
and does write registrations into `seek_production` (`/curate-assay-write`).

Everything else checks out. The Quick start sequence runs in a valid order with valid flags
(verified against each command's `$ARGUMENTS` parsing), the fdh and report rows are true,
the Auth section matches `docs/SECURITY.md`, and the git remote in the clone line is the
real one. Only the consolidate artifact name in that sequence is stale.

---

## Findings

### 1. `README.md:7` — the stated version is one release behind — STALE

**Claim:** `**Status:** v0.3.0`

**Reality:** 0.4.0 is the version in all three places anything reads:

- `.claude-plugin/plugin.json:3` — `"version": "0.4.0"`
- `.claude-plugin/marketplace.json:15` — `"version": "0.4.0"`
- `scripts/_lockfile.py:29` — `PLUGIN_VERSION = "0.4.0"`

`tests/test_identity_sync.py:90-97` asserts those three agree and pins the literal
`"0.4.0"`. Nothing asserts the README, which is why it drifted. `CHANGELOG.md:5` opens
with `## 0.4.0 - 2026-07-31`.

This is not cosmetic: `_lockfile.PLUGIN_VERSION` is stamped into every project's
`.dmac-curation.json` at `/curate-init`, so a curator who reads the README front door and
then opens their own lockfile sees two different versions for the same install.

(`pyproject.toml:3` is also stranded at `0.3.0`. Out of scope for this audit, but it is the
same untested-identity gap and should be fixed in the same pass.)

**Fix** — replace line 7:

```markdown
**Status:** v0.4.0
```

---

### 2. `README.md:11`, `:14-24`, `:26-70` — the plugin has five modes; the README knows four — WRONG

**Claim:** `The plugin is organised as four **modes**.` — followed by four bullets
(`pipeline`, `fdh`, `schema`, `report`) and five command tables covering 19 commands.

**Reality:** there are five modes and 26 command files.

- `skills/curation/SKILL.md:28-34` — the mode table has a fifth row (`:34`):
  `| `assay` | /curate-assay-init, /curate-assay-vocabulary, /curate-assay-detect, /curate-assay-review, /curate-assay-resolve, /curate-assay-write, /curate-assay-status, /curate-assay-backup | ASSAY.md | house - one extract, all projects, no PI; run lockfile at assets/ |`
- `skills/curation/ASSAY.md` exists (the mode's reference doc); its command table is at `:32-41`.
- `ls commands/*.md` → 26 files, including all eight `curate-assay-*.md`.
- Commit `d1f4d14` "the seven new mode commands", `eb8777e` "register assay as the fifth
  curation mode".

Seven of those eight commands (`init`, `detect`, `review`, `resolve`, `write`, `status`,
`backup`) are absent from the README entirely. A reader of the front door cannot learn that
the mode exists, that it is house-scoped rather than project-scoped, or that one of its
commands writes to production.

Two second-order consequences worth carrying into the fix:

- The assay mode is **house-scoped**: it runs from the plugin checkout itself, "the
  directory holding `scripts/` and `assets/`" (`commands/curate-assay-init.md:7-8`; the
  same rule, worded "the directory holding `scripts/` and `assay-hygiene/`", at
  `commands/curate-assay-vocabulary.md:36-38`), not from a curation project directory. That
  is a different execution model from every other mode and belongs in the mode bullet.
- `/curate-status` — listed in the README under **Any mode** — does **not** report assay
  mode. `commands/curate-status.md:5-6` still says "across all four dmac-curation modes"
  and its table at `:26-31` has rows for `pipeline` / `fdh` / `schema` / `report` only. The
  assay mode has its own `/curate-assay-status`. The README fix below lists it so a reader
  is not sent to the wrong status command. (The `curate-status.md` text itself is a
  separate defect for whoever owns that file.)

**Fix** — replace line 11 and add a fifth bullet after the `report` bullet (line 24):

```markdown
The plugin is organised as five **modes**. A mode is a convention, not a framework:
entry-point commands, a reference doc loaded on demand, and optionally its own scripts.
```

```markdown
- **`assay`** — assay hygiene: find samples that should be registered against an internal
  assay and are not, put every proposal in front of a human, write the approved ones to
  production. **House-scoped** — one extract, all projects, no PI — so it runs from the
  plugin checkout itself (the directory holding `scripts/` and `assets/`), not from a
  curation project. Reference: [`skills/curation/ASSAY.md`](skills/curation/ASSAY.md).
```

And add a fifth command table, between the `schema` table and the `report` table:

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
| `/curate-assay-write` | **writes to production**, behind eight preflight refusals and `--confirm` |
| `/curate-assay-status` | report which run is open and where it has got to; writes nothing |
| `/curate-assay-backup` | dated, verified tarball of the ruling store |

The ruling store at `assets/rulings/` is human judgement and **nothing regenerates it** —
not compute, not a re-run. It is gitignored; its only protection is the tarball
`/curate-assay-backup` writes.
```

Finally, amend the **Any mode** table so a reader is not sent to the wrong status command:

```markdown
**Any mode**

| command | does |
|---|---|
| `/curate-status` | show toolkit state for `pipeline`, `fdh`, `schema` and `report` (assay mode has its own `/curate-assay-status`) |
```

---

### 3. `README.md:58` — `/curate-assay-vocabulary` is filed under the wrong mode, with a path its own command forbids — WRONG

**Claim** (in the **`schema`** table):

> `/curate-assay-vocabulary` | settle the unresolved tail of the assay vocabulary: reads `assay-hygiene/vocabulary-unresolved.csv` plus the registration evidence from `scripts/assay_hygiene/vocabulary_evidence.py`, writes `vocabulary-proposed.csv` for a curator to overrule. Read-only against the database

**Reality:** three things are wrong.

1. **Wrong mode.** Commit `64f233d` is literally titled "absorb curate-assay-vocabulary
   into the mode". `commands/curate-assay-vocabulary.md:5-7` opens: "This is **stage B2 of
   the assay-hygiene mode**." `skills/curation/SKILL.md:34` lists it under `assay`;
   `skills/curation/ASSAY.md:35` lists it in the assay command table.
2. **Wrong prerequisite.** It is not a standalone command any more. "Run
   `curate-assay-init` first — this command needs an open run"
   (`commands/curate-assay-vocabulary.md:6-7`).
3. **Wrong paths, in the one direction that is dangerous.** The command sets
   `RUN=assets/RUN2 # this run's directory, never the default path`
   (`commands/curate-assay-vocabulary.md:9-11`) and reads
   `$RUN/04-artifacts/vocabulary-unresolved.csv` (`:39`), writing
   `$RUN/04-artifacts/vocabulary-proposed.csv` (`:266`). The README's bare
   `assay-hygiene/` is exactly the default path the mode refuses:
   `skills/curation/ASSAY.md:57-59` — "**Never run a driver on default paths.**
   `run_evidence` and `run_detect` default `out_dir` to `assay-hygiene/`, which is 33
   symlinks into `assets/RUN1/`. `_writeguard` refuses it". A reader following the README
   is aimed at an immutable prior run.

("Read-only against the database" survives — the evidence pass does not write to NExtSEEK;
the rulings it produces land in the local store.)

**Fix:** delete the row from the `schema` table entirely (leaving `/curate-sampletype` as
that table's only row) and let the assay table in finding 2 carry it. If a longer gloss is
wanted there, use:

```markdown
| `/curate-assay-vocabulary` | stage B2 — settle the unresolved tail of the assay vocabulary. Needs an open run: reads `$RUN/04-artifacts/vocabulary-unresolved.csv` plus the registration evidence from `scripts/assay_hygiene/vocabulary_evidence.py`, writes `$RUN/04-artifacts/vocabulary-proposed.csv` for a curator to overrule. Read-only against the database |
```

---

### 4. `README.md:37`, `:64`, `:124` — the consolidate artifact is `Arm{X}-upload.xlsx`, not `Arm{X}.xlsx` — STALE

**Claims:**

- `:37` — "collapse the 4-sheet sheets to flat-format `Arm{X}.xlsx`, plus `Arm{X}_review.xlsx` …"
- `:64` — "GEO / SRA / PRIDE submission artifacts from UIDs, a workbook, an `Arm{X}.xlsx`, or tabular data"
- `:124` — `/curate-consolidate   # → assay_sheets/Arm*.xlsx + Arm*_review.xlsx`

**Reality:** `scripts/consolidate_to_flat.py:490` —
`out_name = f"{arm}.xlsx" if args.all_in_one else f"{arm}-upload.xlsx"`. The bare
`Arm{X}.xlsx` form appears in the codebase only as a **legacy name the script deletes on
re-run** (`scripts/consolidate_to_flat.py:357-359`: "legacy bare-arm outputs (``ArmA.xlsx``)
from before the ``-upload`` suffix"), or as the literal string passed to `--all-in-one NAME`.

`commands/curate-consolidate.md:2,15,22-23` is unambiguous: "Verify per-arm
`Arm{X}-upload.xlsx` files written to `assay_sheets/`. The `-upload` suffix means
retrieve/deposit read them as-is — no rename step." The downstream commands agree —
`commands/curate-qa.md:9` requires `assay_sheets/Arm*-upload.xlsx`.

The `Arm{X}_review.xlsx` half of the claim is correct
(`scripts/consolidate_to_flat.py:253`).

Note for the fixer: `templates/CLAUDE.md.j2:29` carries the same stale name and is rendered
into every scaffolded project. Out of this audit's scope, same one-line fix.

**Fix** — line 37:

```markdown
| `/curate-consolidate` | collapse the 4-sheet sheets to flat-format `Arm{X}-upload.xlsx`, plus `Arm{X}_review.xlsx` (one sheet per sample type, for humans) |
```

line 64:

```markdown
| `/curate-report` | GEO / SRA / PRIDE submission artifacts from UIDs, a workbook, an `Arm{X}-upload.xlsx`, or tabular data |
```

line 124:

```markdown
/curate-consolidate     # → assay_sheets/Arm*-upload.xlsx + Arm*_review.xlsx
```

---

### 5. `README.md:74-77` — two of the three "What this is not" promises are false — WRONG

**Claims:**

> - It does **not** upload to NExtSEEK on its own — it produces upload-ready metadata for a
>   human to submit.
> - It does **not** edit the NExtSEEK sample type catalog — `schema` mode writes a proposal
>   and a rationale; a human applies it.

**Reality:** both were true at 0.3.0 and neither is true now.

*Bullet 1.* `commands/curate-assay-write.md:2-8` — "description: Write registrations to
production, behind eight refusals … **This is the only command that touches production.**
It writes nothing without `--confirm`." It posts an `UPDATE_ASSAY` sheet to
`/seek/sampleupload/` in 2,000-row chunks (`:11-13`, `:75-79`), requires a captured rollback
handle `SELECT MAX(id) FROM seek_production.assay_assets` (`:31-38`) because the undo is
`DELETE FROM seek_production.assay_assets WHERE id > <handle>`, and reconciles each chunk
against a live `COUNT(*)` (`:81-91`). The guardrail is real and elaborate, but the sentence
"does not upload to NExtSEEK on its own" no longer describes it.

*Bullet 2.* The README **contradicts itself four lines earlier**: its own `schema` row at
`:57` says "The explicit `apply` verb can also **write the change to a live server** via
`scripts/sampletype_attr.py`". `CHANGELOG.md:18-23` confirms this shipped in 0.4.0 —
"`scripts/sampletype_attr.py` - add an attribute to a live sample type. Dry-run by default;
`--apply` to write; production additionally requires `--yes-production` … Verified end to
end on dev then production."

The third bullet (no fabricated values) is accurate and matches `SKILL.md` hard rule 8.

**Fix** — replace lines 72-79 wholesale:

```markdown
## What this is not

- It does **not** upload curated project metadata to NExtSEEK — `pipeline` mode produces
  upload-ready sheets for a human to submit. The two exceptions are explicit, opt-in and
  named: `/curate-sampletype apply` (adds one attribute to a live sample type; dry-run by
  default, `--apply` to write, `--yes-production` on top of that for production) and
  `/curate-assay-write` (writes assay registrations to production behind eight preflight
  refusals, `--confirm`, a captured rollback handle and a verified DB backup).
- It does **not** invent sample types — `schema` mode writes a proposal and a rationale for
  a human to review, and only the explicit `apply` verb writes anything.
- It does **not** fabricate values — unknowns are left as greppable
  `*** PLACEHOLDER: ... ***` markers, and ambiguity is surfaced, not guessed.
```

---

### 6. `README.md:88-107` — the repo layout tree omits the two largest additions and the whole test suite — STALE

**Claim:** the tree lists `skills/curation/{SKILL.md, PHASES.md, FDH.md, SCHEMA.md, REPORTS.md}`,
four named scripts plus `fdh/ report/ schema/ deposit/`, then `context/`, `templates/`,
`docs/`.

**Reality** (`git ls-files`, and `ls` of each directory):

| omitted | evidence |
|---|---|
| `skills/curation/ASSAY.md` | the file exists; it is the `assay` mode's reference doc |
| `scripts/assay_hygiene/` | 40 modules — the largest package in `scripts/` by a wide margin (`fdh/` has 4, `report/` 9, `schema/` 7, `deposit/` 1) |
| `tests/` | 92 tracked files (88 `test_*.py`, `conftest.py`, `test_e2e_init.sh`, fixtures) — the single largest tracked directory in the repo |
| `pyproject.toml`, `uv.lock` | both tracked at the root; `.gitignore:52-55` explains uv.lock is deliberately tracked as the reproducibility guarantee |
| `CHANGELOG.md` | tracked at the root |

Per-directory tracked-file counts: `scripts/` 89, `tests/` 92, `docs/` 31, `commands/` 26,
`context/` 17, `templates/` 10, `skills/` 6.

The tree is deliberately illustrative — it does not list all 25 top-level scripts, and that
is fine. But omitting `assay_hygiene/` hides the code behind a whole mode, and omitting
`tests/` misleads a contributor about where the repo's centre of mass is.

**Fix** — replace lines 90-107:

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

---

### 7. `README.md:111-113` and `:141-147` — install and update ignore the marketplace manifest the repo ships — STALE

**Claims:**

```bash
# Install
git clone git@github.com:cdemurjian/dmac-curation.git ~/.claude/plugins/dmac-curation
```

```bash
cd ~/.claude/plugins/dmac-curation && git pull
```

**Reality:** the repo ships `.claude-plugin/marketplace.json`, whose entire purpose is
`/plugin marketplace add` — it declares a marketplace named `dmac` with one plugin
`dmac-curation` at `"source": "./"`. And that is how the plugin is actually installed on
this machine:

- `~/.claude/plugins/known_marketplaces.json` — `"dmac": {"source": {"source": "directory",
  "path": "/home/cdemurjian/code/dmac/curation_skill"}, ...}`
- `~/.claude/plugins/installed_plugins.json` — `"dmac-curation@dmac"` installed to
  `/home/cdemurjian/.claude/plugins/cache/dmac/dmac-curation/0.4.0`, with a
  `gitCommitSha`.

`~/.claude/plugins/` contains `cache/`, `marketplaces/`, `data/`,
`installed_plugins.json` and `known_marketplaces.json` — there is no
`~/.claude/plugins/dmac-curation` and nothing registered at that path. The README documents
neither the marketplace manifest nor the `/plugin` flow, so a new user following it
literally ends up with a checkout in a directory the plugin system does not read from and
does not record in `installed_plugins.json`. (I did not attempt a bare-clone install to
test whether legacy directory discovery still works; the verified point is that the shipped
and actually-used mechanism is the marketplace and the README never mentions it.)

The git remote in the clone line is correct (`git remote -v` → `git@github.com:cdemurjian/dmac-curation.git`).

**Fix** — replace lines 111-113:

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

and replace lines 141-147:

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

---

## Checked and found accurate (not findings)

Recorded so the next auditor does not re-derive them.

| README claim | verified against |
|---|---|
| Every `pipeline` row's command exists and its one-line gloss matches | all 13 `commands/curate-*.md` frontmatter descriptions; phases 1, 2, 3, 5, 6, 7-8, 9, 9b, 10, 11, 12, 13 |
| "12 phases" | `skills/curation/PHASES.md:9` "14 commands drive 12 phases"; matches `plugin.json`'s description |
| `/curate-sample-tree` → `SAMPLE_TREE.md` + `sample_tree.json` + `SAMPLE_TREE.html` | `commands/curate-sample-tree.md:12-13,79,88` |
| `/curate-qa` local, `/curate-qc` server-side and "the last gate before upload" | `commands/curate-qa.md` (drives `qa_flat_sheets.py`, no network); `commands/curate-qc.md:5-6`; `CHANGELOG.md:12-17` |
| `/fdh-upload` → `scripts/fdh/submit.py`; `/fdh-api` over `scripts/fdh/fdh_api.py` | both files exist; `commands/fdh-upload.md:2`, `commands/fdh-api.md:2` |
| `/curate-sampletype apply` writes to a live server via `scripts/sampletype_attr.py` | `CHANGELOG.md:18-23`; the file exists |
| Auth section (per-project `.env`, `FDH_API={"name": "token"}`, never in the plugin) | `docs/SECURITY.md:9-22` |
| Quick start flags: `--lab`/`--pi`, `/curate-build A`, `--project-id 10`, `zenodo` | `curate-init.md:8-11`; `curate-build.md:7`; `curate-resolve-assays.md:7`; `curate-deposit.md:42` |
| Quick start ordering (build → consolidate → resolve-assays → qa → qc → deposit → retrieve → email) | matches the phase numbering in each command's frontmatter |
| `scripts/deposit/` is present in the tree | `README.md:103` — contrary to `inventory-scripts-subpkgs.md:708-712`, which claims it is missing; the inventory is wrong on this point |
| `git@github.com:cdemurjian/dmac-curation.git` | `git remote -v` |

## Considered and rejected

- **The `pipeline` mode bullet (`:14-16`) omits QC** from its prose list of phases. It is a
  summary sentence and the table two sections down documents `/curate-qc` correctly. Worth
  folding "server-side QC" into the bullet when finding 5 is applied, but not a finding.
- **`scripts/deposit/` described as "external deposit builders"** when it holds one GEO
  renderer. Generous, not wrong; the Zenodo/OMERO machinery `/curate-deposit` drives lives
  at the top level of `scripts/`.
- **The Auth section omits `BIOPORTAL_API_KEY`** (`docs/SECURITY.md:17`). The README
  explicitly defers to `docs/SECURITY.md` for the full list, so this is delegation, not drift.
- **`scripts/fdh/generated/REGISTRY.md` says `_(none yet)_`.** Out of scope per the brief,
  and already fixed uncommitted in the main tree.
