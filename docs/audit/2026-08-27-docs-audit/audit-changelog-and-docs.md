# Drift audit — `CHANGELOG.md`, `docs/SECURITY.md`, and the `docs/` tree

Worktree `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`, branch
`dev-docs`, HEAD `833e9be`, clean. Every finding below was checked by opening the
source file named and reading the contradicting lines.

**Verdict: SUBSTANTIAL_DRIFT.**

- `CHANGELOG.md` stops at `0.4.0 - 2026-07-31`. **214 commits have landed since**,
  including an entire new curation mode with 8 commands, 39 script modules and the
  first code in the plugin that writes to production. The changelog contains **zero**
  occurrences of `curate-assay`, `assay_hygiene`, `detect-context`, `pull-db`,
  `stamp_guard` or `DMAC_ENV_FILE`.
- `docs/SECURITY.md` was last touched **2026-07-21** (`c25ce6e`), before 0.4.0 shipped.
  Its enforcement section is still accurate line for line; its credential table is not,
  and it is silent on the second exposure class this repository has since discovered
  (sample identifiers) and on the two history rewrites that followed.
- `docs/` holds 31 files and ~34,500 lines with **no index**. One is a maintained
  reference; 30 are frozen specs, plans and findings, three of which carry status lines
  that were falsified by commits landing the same day.

---

# 1. `CHANGELOG.md` — the drafted entry (main deliverable)

## 1.1 What to do with it

Insert the block in §1.2 **verbatim** immediately after line 3 (`All notable changes
to dmac-curation will be documented in this file.`) and above `## 0.4.0 - 2026-07-31`.

It is headed `## Unreleased` deliberately. Promoting it to `## 0.5.0 - <date>` is a
six-file change, not a one-line one, because the version is pinned in code and by test:

| file | field | currently |
|---|---|---|
| `.claude-plugin/plugin.json:3` | `version` | `0.4.0` |
| `.claude-plugin/marketplace.json:15` | `version` | `0.4.0` |
| `scripts/_lockfile.py:29` | `PLUGIN_VERSION` | `0.4.0` |
| `pyproject.toml:3` | `version` | `0.3.0` |
| `README.md:7` | status line | `**Status:** v0.3.0` |
| `tests/test_identity_sync.py:90-96` | literal assertion | `"0.4.0"` |
| `tests/conftest.py:98` | fixture lockfile | `"plugin_version": "0.3.0"` |

Note also that the drafted entry's `### Changed` section deliberately supersedes one
line of the 0.3.0 entry: `CHANGELOG.md:148-150` documents *"Why CEDAR templates are
out of scope"*, and `5115789` (2026-08-27) shipped `scripts/schema/templates.py`, which
reads a pinned CEDAR template over the live CEDAR API with a `CEDAR_API_KEY`. The 0.3.0
reasoning still holds for *emitting* a template; what changed is that one is now read.
A reader scanning the changelog newest-first must not be left with "out of scope" as
the last word on CEDAR.

## 1.2 The entry, in the file's house style

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

---

# 2. `docs/SECURITY.md`

Last modified `c25ce6e`, **2026-07-21** — before 0.4.0 released. Three findings.

## 2.1 What is still correct (checked, not assumed)

Do not "fix" these; they were verified line by line.

- The `_load_dotenv()` resolution order claim: `scripts/fdh/fdh_api.py:159-169` reads
  `Path.cwd()/.env` then `REPO/.env`, `setdefault` only. `scripts/nextseek_api.py:334-349`
  and `scripts/sampletype_attr.py:73-89` mirror it. Nothing requires a plugin-local `.env`.
- The three historical on-disk exposures match `tests/test_no_plaintext_secrets.py:32-36`
  (`FORBIDDEN`) exactly, path for path.
- The three enforcement tests are described correctly:
  `test_known_secret_files_are_gone` (`:126`), `test_no_dotenv_under_working` (`:133`,
  glob `.env*` at `:137`, allowlist `{.env.example, .env.sample, .env.template}` at `:39`),
  `test_no_credential_literals_under_working` (`:143`).
- The detector's stated thresholds are exact: 12+ chars (`:77`), mixed alphabet or
  32+ chars (`:86`), Shannon entropy ≥ 3.0 (`:88`), placeholder-prefix suppression
  (`:60-64`), keys-not-values in the failure message (`:94`).
- "Ten synthetic-fixture tests" — two `@pytest.mark.parametrize` blocks of five each,
  `:162-172` and `:181-191`.
- "Binary files and files over 20 MB are skipped" — `:118`.
- "When `working/` does not exist, tests 2 and 3 `pytest.skip`" — `:135`, `:146`.
- `working/` is gitignored (`.gitignore:93`) and `.env` (`.gitignore:4`), so the
  "never shows in `git status`" note holds.

## 2.2 Finding S1 — the credential table is missing five entries and one consumer

`docs/SECURITY.md`, section *"Where credentials go instead"*. It lists five rows. Live
code reads four more environment variables, and one listed row names the wrong consumer
set.

| what the table omits | read at |
|---|---|
| `NEXTSEEK_TOKEN` | `scripts/nextseek_api.py:357,415,587` (`--token` alternative to Basic auth) |
| `FDH_TOKEN` | `scripts/fdh/fdh_api.py:175-176` — checked *before* `FDH_API`, so it wins |
| `OMERO_USER` / `OMERO_PASSWORD` / `OMERO_SESSIONID` / `OMERO_CSRFTOKEN` | `scripts/omero_pull.py:249,399,408,413` |
| `CEDAR_API_KEY` | `scripts/schema/templates.py:38,121`; documented at `commands/curate-sampletype.md:199` |
| `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD` also feed `scripts/sampletype_attr.py` | `scripts/sampletype_attr.py:478-479` — plus the legacy alias `NEXTSEEK_USER` and `NEXTSEEK_BASE_URL` at `:62,474-478` |

The `sampletype_attr.py` omission is the one that matters: it is the **only script in
the repo that writes to a production database schema**, and a reader of SECURITY.md
would not learn that it takes the same credentials.

### Proposed replacement for the whole table

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

## 2.3 Finding S2 — `$DMAC_ENV_FILE`, the actual bootstrap mechanism, is absent

Since `ad82c51` (2026-08-04), `/curate-init` provisions a project `.env` by copying the
file `$DMAC_ENV_FILE` points at (`commands/curate-init.md:96-112,187`;
`templates/env.example.j2:2-3`). SECURITY.md never names it, so the one document a
person reads about credentials does not describe how credentials actually arrive.

### Proposed insertion, after the credential table

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

## 2.4 Finding S3 — SECURITY.md does not carry the lesson of the history rewrites

This is the significant one. The task named it, and the answer is: **no, it does not.**

`docs/SECURITY.md` is titled *"Credential handling"* and treats credentials as the only
exposure class. Since it was written, this repository has recorded two separate
identifier incidents and grown a second guard for them, none of which SECURITY.md
mentions:

| evidence | says |
|---|---|
| `.gitignore:107-112` | `assay-hygiene-bak/` held 195 MB of real sample metadata matching no pattern, "one `git add -A` away from a PUBLIC repo — and this repo already needed a **history rewrite on 2026-08-21 to strip 1,570 sample identifiers**" |
| `.gitignore:114-122` | `assets/` "carries real sample identifiers — this repository is PUBLIC and already needed a history rewrite on 2026-08-21" |
| `.gitignore:124-144` | `mode2-rulings-backup-2026-08-20.tsv`, a byte-identical copy of the whole ruling file, "was sitting UNTRACKED AND UNIGNORED in the repository root on 2026-08-24". The globs are unanchored *because* a `tests/fixtures/`-scoped rule would have left it there |
| `.gitignore:146-152` | six `.claude/reports/*.json` "were swept into this PUBLIC repository on 2026-08-25 and the branch had to be rewritten" |
| `tests/test_identifier_exposure.py:1-60` | a whole second guard, with a ratchet in both directions, a reserved synthetic band (`19MMDD`), and a written account of two scan holes and why a diff-scoped pre-push scan missed 97 occurrences in 22 files for four days |

Worse, SECURITY.md's *"What it does not catch"* section now reads as more complete than
it is: *"Credentials outside `working/` — nothing else in the checkout is scanned"* was
true of its own guard and is misleading now that a second guard scans the entire tracked
tree (including binaries and zip members) for something else.

SECURITY.md also never states the single fact that governs all of this: **the repository
is public.**

### Proposed additions

Retitle the document and add a scope line at the top:

```markdown
# Security: credentials, and identifiers

**This repository is PUBLIC.** Two classes of thing must never reach it: credentials,
and the real sample and protocol identifiers that curation output carries. They have
different guards, different failure modes, and different remedies. Both are below.

## Credential handling

### Rule
```

…then insert, after the existing *"What it does not catch"* section:

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

---

# 3. `docs/` — the proposed index

## 3.1 Finding D1 — there is no index, and 30 of 31 files are frozen

`docs/` holds 31 markdown files and roughly 34,500 lines. Exactly one — `SECURITY.md` —
is a maintained reference. The other 30 are design specs, SDD plans and dated findings,
and nothing in the tree distinguishes them. A contributor opening
`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` — the newest file, by
date, about the newest subsystem — is told on line 3 that the work is **"Not
implemented"**, seven commits after it shipped.

## 3.2 Findings D2 and D3 — three stale status lines

| file:line | says | reality |
|---|---|---|
| `docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md:3` | `**Status:** design, approved 2026-08-27, all open questions closed. Not implemented.` | Shipped the same day in `d1f4d14` (seven command docs), `64f233d`, `eb8777e` (registered as a mode), `833e9be`. `commands/curate-assay-*.md` ×8 and `skills/curation/ASSAY.md` are on disk |
| same file, §1 line 33 | "Assay hygiene becomes a **fourth** mode alongside `pipeline`, `schema` and `report`" | It is the **fifth**; `fdh` is missing from that list. `skills/curation/SKILL.md:28-34` and `tests/test_mode_table.py:56` both say five |
| `docs/superpowers/specs/2026-08-04-init-auto-detect-project-lab-design.md:3` | `**Status:** Approved (design), pending implementation plan` | The plan exists (`docs/superpowers/plans/2026-08-04-init-auto-detect.md`) and the code shipped: `scripts/detect_context.py`, `nextseek_api.py detect-context` (`:826`), `tests/test_detect_context.py` |
| `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md:3-4` | `stage 0 not implemented, stages A-F partially built (Task 1 only)` … `Not a plugin mode yet.` | `scripts/assay_hygiene/stage0.py`, `stage0_apply.py`, `driver_stage0.py` all exist; stage 0 applied 90,534 edges; and it **is** a plugin mode |

Two ways to fix this. Either amend each status line in place (three one-line edits), or
declare in `docs/README.md` that a spec's status line is frozen at its date and mark the
three known-stale ones there. **Do both.** The status line is what a reader sees first.

Literal replacements, if amending in place:

```markdown
**Status:** design approved 2026-08-27; **SHIPPED the same day** in `d1f4d14`…`833e9be`.
The status line below is preserved as written; see `docs/README.md` for what is current.
**Supersedes:** nothing. **Absorbs:** `commands/curate-assay-vocabulary.md` — absorbed
*into the mode*, not deleted; the command file is live.
```

```markdown
**Status:** Approved (design). **IMPLEMENTED** 2026-08-04 — see
`docs/superpowers/plans/2026-08-04-init-auto-detect.md`, `scripts/detect_context.py`
and `nextseek_api.py detect-context`.
```

```markdown
**Status:** design approved 2026-08-12/13. **SUPERSEDED.** Stage 0 shipped
(`scripts/assay_hygiene/stage0.py`), stages A–F were redesigned as three modes on
2026-08-14, and assay hygiene is now a plugin mode. Read
`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` and
`skills/curation/ASSAY.md` for what is current.
```

## 3.3 The drafted `docs/README.md`

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
| `audit/2026-08-27-docs-audit/` | ground-truth inventories of commands, skills, scripts and repo furniture, plus the drift audits derived from them. A snapshot at `833e9be`, not a maintained reference |

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

# 4. Things checked that turned out fine

Reported so nobody re-derives them.

- `CHANGELOG.md`'s 0.4.0 and 0.3.0 entries are accurate against the code they describe:
  `nextseek_api.py:876-878` still registers `sampletype-add-attribute` as RETIRED with
  the stated 422→502 explanation; `scripts/sampletype_attr.py` requires `--apply` plus
  `--yes-production` on `nextseek.mit.edu` (`:63,290-318,519`); the four rejected
  attribute names and the `QuanitifcationMethod` typo are still recorded in
  `skills/curation/SKILL.md:168-170`; the four deposit scripts default to dry-run and
  require `--write` (`tests/test_deposit_write_safety.py:14-21`).
- `docs/SECURITY.md`'s entire *Enforcement* section is exact — see §2.1.
- `README.md:86` already points at `docs/SECURITY.md`, so an index does not need to
  re-establish that link.
- `scripts/fdh/generated/REGISTRY.md:10`'s `_(none yet)_` row is **correct in this
  worktree** — the directory holds only `__init__.py` and `REGISTRY.md` here. The drift
  is in the main tree and is already fixed uncommitted there.
- The absence of `assay-hygiene/`, `assets/` and `working/` from this worktree is
  correct and is why 51 tests skip.
