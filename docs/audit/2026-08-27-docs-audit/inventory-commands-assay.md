# Ground-truth inventory — assay-mode slash commands

Scope: the 8 `commands/curate-assay-*.md` files in the `dev-docs` worktree at
`/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`, plus every
module under `scripts/assay_hygiene/` they invoke. Every claim below was read
from the file cited. Paths are worktree-relative unless absolute.

Verified against tip `833e9be` (`fix(assay-hygiene): four defects found reviewing the mode commands`).

---

## 0. Frontmatter — the exact text of all eight

Every one of the eight files has YAML frontmatter containing **`description:` and
nothing else**. There is **no `name:`, no `argument-hint:`, and no
`allowed-tools:` key in any of the eight files.** Verified by printing lines 1–6
of each. `tests/test_assay_hygiene_commands.py:26-30` only asserts `description:`
is present, so nothing enforces the other three keys.

| file | `description` (exact) |
|---|---|
| `commands/curate-assay-init.md:2` | `Open a numbered assay-hygiene run and prove the ruling store survives` |
| `commands/curate-assay-vocabulary.md:2` | `Map unresolved metadata terms onto internal assays (assay hygiene, stage B2)` |
| `commands/curate-assay-detect.md:2` | `Run the evidence and detection passes into this run's own directory` |
| `commands/curate-assay-review.md:2` | `Serve the review surfaces, ingest the operator's rulings, back up` |
| `commands/curate-assay-resolve.md:2` | `Turn approved pairs into SEEK write targets behind the project gate` |
| `commands/curate-assay-write.md:2` | `Write registrations to production, behind eight refusals` |
| `commands/curate-assay-status.md:2` | `Report which assay-hygiene run is open and where it has got to` |
| `commands/curate-assay-backup.md:2` | `Write a dated, verified tarball of the ruling store` |

**No assay command declares or accepts a slash-command argument.** None uses
`$ARGUMENTS`, `$1`, or an `argument-hint`. `curate-assay-detect.md:16` and
`curate-assay-vocabulary.md:10` instruct the operator to set a shell variable
`RUN=assets/RUN2` by hand; that is the only parameterisation in the mode.

**No assay command is invoked via `uv run --script`.** All eight use either
`PYTHONPATH=scripts uv run [--with pandas] [--with pyarrow] python -c "..."` or
`PYTHONPATH=scripts uv run ... python -m assay_hygiene.<module> <extract> <out>`.
This contradicts `skills/curation/SKILL.md:73` hard rule 6 ("Invoke via
`uv run --script <plugin>/scripts/X.py`"). The PEP 723 headers on the modules
(e.g. `scripts/assay_hygiene/rulings.py:1-4`) are inert under `-m`/`-c`, which is
why the docs pass `--with pandas --with pyarrow` explicitly.

---

## 1. `curate-assay-init.md` (86 lines, 3.4 KB)

**What it does.** Opens a numbered assay-hygiene run. It first proves the durable
ruling store still exists and refuses to continue if not; optionally (first run
only) migrates a completed run's rulings into the store; then creates
`assets/RUN<n>/` with its eight tiers, chmods tiers `00`–`06` read-only, and
writes the run lockfile `assets/assay-run.json`. It closes by telling the
operator to consciously decide whether a strict-xfail measurement still applies
to the new extract.

**Invocations** (all `PYTHONPATH=scripts`):

| line | exact command | module reached |
|---|---|---|
| `:13-19` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` | `assay_hygiene.init_run.require_store` (`scripts/assay_hygiene/init_run.py:35`) |
| `:25` | `tar -xzf ~/backups/rulings-<newest>.tar.gz -C assets/` | — (shell) |
| `:32-43` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` | `assay_hygiene.init_run.migrate_into_store` (`init_run.py:76`) → `migrate_rulings.migrate` (`migrate_rulings.py:49`), `migrate_rulings.conflicts` (`:105`), `rulings.load`/`save` (`rulings.py:101`,`:89`), `protect_run.protect` |
| `:60-68` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` | `init_run.next_run_number` (`:51`), `init_run.create_run` (`:62`), `runstate.create` (`runstate.py:49`) |

**Reads.** `assets/rulings/pairs.tsv` (`init_run.py:38`, name from
`rulings.py:43`); `assets/RUN1/01-extract/assays.parquet` (`curate-assay-init.md:36`);
`assets/RUN1/00-rulings/mode2-rulings-2026-08-20.tsv`,
`…/pair-rulings.tsv`, `…/mode1-rulings-COMPLETE.tsv` (`migrate_rulings.py:56,72,87`);
`assets/assay-run.json` (`runstate.py:22,34`).

**Writes.** `assets/rulings/pairs.tsv` (rewritten wholesale by `rulings.save`,
`rulings.py:97`); `assets/RUN<n>/{00-rulings,01-extract,02-agent-runs,03-stage0-applied,04-artifacts,05-review,06-findings,07-process}/`
(`init_run.py:24,71`); mode bits `0o555`/`0o444` on tiers `00`–`06`
(`init_run.py:26,72`; `protect_run.py:21-22,25-38`); `assets/assay-run.json`
(`runstate.py:42-46`).

**Safety gates / refusals.**
- `require_store` raises `MissingRulingStore` (`init_run.py:31,40`) unless
  `<store>/pairs.tsv` exists. The doc's "stop" instruction (`:21-22`) matches.
- `runstate.create` raises `RunLocked` (`runstate.py:26,52-56`) while another run
  is open. The doc states the reason correctly (`:70-73`): MAX(id)+1 primary keys
  with no lock.
- `rulings.save` → `_collapse` raises `ValueError` on an unknown verdict
  (`rulings.py:75`) and `ConflictingRulings` on one key with two verdicts
  (`rulings.py:81`). `migrate_into_store` pre-filters conflicting keys and
  **reports rather than resolves** them (`init_run.py:89-91,107-109`); doc `:46-55`
  is accurate.
- `migrate_into_store` **merges** with the existing store (`init_run.py:87,105`)
  rather than replacing it — the fix from `833e9be`. Doc `:46-50` matches.

**Ordering prerequisites.** None. This is the first command of the mode.

**Defects found.**
1. **`init_run.py:48` advertises a CLI flag that does not exist.** The
   `MissingRulingStore` message tells the operator to run
   `` `curate-assay-init --migrate-from assets/RUN1` ``. `init_run.py` has no
   `argparse`, no `main()`, and no `__main__` block; `curate-assay-init.md` is
   pure prose plus `python -c` snippets. There is no `--migrate-from` anywhere in
   `scripts/` (verified by grep). The doc itself (`:32-43`) does the migration
   with an inline `python -c` instead.
2. **The provenance sidecar is never written.** `migrate` returns provenance
   records (`migrate_rulings.py:54,67,84,100,102`) and `migrate_into_store`
   passes them through under key `"provenance"` (`init_run.py:109`), but the doc's
   snippet (`:38-43`) prints only `store_before`/`written`/`store_total`/`conflicts`
   and **nothing anywhere writes provenance to disk**. `rulings.py:31-33` and
   `carryforward.py:18-24` both describe "a gitignored sidecar" as if it exists.
   This is the root cause of the carry-forward gap in §3.
3. `:80` cites `tests/test_assay_hygiene_rulings.py:332` for the strict-xfail —
   **this citation is correct**; the marker is at that exact line
   (`tests/test_assay_hygiene_rulings.py:332`), `strict=True`, naming 13 rejected
   cohorts.

---

## 2. `curate-assay-vocabulary.md` (313 lines, 15 KB)

**LIVE ENTRY POINT — not a leftover.** Git commit `64f233d`
("absorb curate-assay-vocabulary into the mode") did **not** delete or fold the
file; `git show --stat 64f233d` shows a single file changed, `+32/-11` to
`commands/curate-assay-vocabulary.md`. "Absorb" meant *bring the pre-existing
command into conformance with the new mode*: re-scope every path through `$RUN`
and replace the stale 2026-08-14 headline counts with the command that measures
them. Three independent confirmations that it is live:
- `tests/test_assay_hygiene_commands.py:14-17` lists it in `EXPECTED` and
  parametrises four tests over it.
- `skills/curation/SKILL.md:34` lists it as the second entry point of the `assay`
  mode; `skills/curation/ASSAY.md:35` gives it a row in the command table.
- `scripts/assay_hygiene/gate.py:932` routes unresolved terms to
  `/curate-assay-vocabulary` by name, in a live docstring.

**What it does.** Settles the unresolved tail of the assay vocabulary. Builds an
evidence table joining each unresolved metadata term to what its carrying samples
are actually registered in, has the agent read the underlying sample metadata,
and writes `vocabulary-proposed.csv` with `provenance = proposed`. A term ruled
"not an assay" is written with an **empty** `internal_assay_id` rather than
omitted, so the ruling is durable and the term leaves the queue.

**Invocations.**

| line | exact command |
|---|---|
| `:26-31` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` — reads `$RUN/04-artifacts/vocabulary-unresolved.csv` and prints the tail size by `source_field` |
| `:43-44` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow \`<br>`  python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts` |
| `:71-72` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow \`<br>`  python -m assay_hygiene.vocabulary_evidence $RUN/01-extract $RUN/04-artifacts` |

**Reads.** `$RUN/01-extract/{assays,membership,samples,nodes}.parquet`
(`vocabulary_evidence.py:238-247`; the doc names them at `:55-56`);
`$RUN/04-artifacts/vocabulary-unresolved.csv` (`vocabulary_evidence.py:239`);
`$RUN/04-artifacts/vocabulary-evidence.csv`; `$RUN/04-artifacts/vocabulary.csv`.
Via `run_evidence.main` it additionally reads `edges.parquet`
(`run_evidence.py:895`) and, **from the output directory**,
`vocabulary-proposed.csv` and `vocabulary-curator.csv`
(`run_evidence.py:905-906`).

**Writes.** `$RUN/04-artifacts/vocabulary-evidence.csv`
(`vocabulary_evidence.py:250`) — explicitly declared a working file, not a
contract (`curate-assay-vocabulary.md:298-299`);
`$RUN/04-artifacts/vocabulary-proposed.csv` (the agent's deliverable,
columns fixed at `:268`). Via `run_evidence.main`, also
`vocabulary.csv` (`run_evidence.py:908`), `vocabulary-unresolved.csv` (`:911`),
`precedent.csv` (`:914`), `claims.parquet` (`:917`),
`mode3-contradictions.csv` (`:920`),
`mode3-contradictions-with-contested.csv` (`:932`),
`mode3-review-patterns.csv` (`:950`), `evidence-report.md` (`:963`).

**Output contract** (`:266-279`): columns
`source_field,raw_value,internal_assay_id,internal_assay_title,support,n_samples,purity,provenance`;
`support`/`n_samples`/`purity` **must** be `0`/`0`/`0.0`; `provenance` must be the
literal lowercase `proposed`.

**Safety gates / refusals.**
- `run_evidence.main` calls `_writeguard.assert_writable`
  (`run_evidence.py:888-892`), which raises `SymlinkWriteRefused`
  (`_writeguard.py:22,38`) if `out_dir` or any named artifact under it is a
  symlink.
- `vocabulary_evidence.main` does **not** call `assert_writable` (verified: no
  such call in `scripts/assay_hygiene/vocabulary_evidence.py`), so its
  `vocabulary-evidence.csv` write is unguarded against the symlink hazard. Its
  default `out_dir` is still `"assay-hygiene"` (`vocabulary_evidence.py:235`).
- The vocabulary loader rejects an unrecognised `provenance`
  (`curate-assay-vocabulary.md:277-279`, rule 7 at `:220-226`); the two tiering
  rules test membership of `{learned, curator}` rather than `!= proposed`.
- `merge_vocabulary` raises rather than silently dropping a non-text key
  (`:256-257`), which is why bare-numeric `raw_value`s must be quoted.

**Ordering prerequisites.** Requires an open run from `curate-assay-init`
(`:6-7`). Requires `$RUN/04-artifacts/vocabulary-unresolved.csv` and
`vocabulary.csv`, which only `run_evidence` produces — and this command carries
its own `run_evidence` invocation (`:43-44`) to satisfy that, so it does **not**
require `curate-assay-detect` first.

**Defects found.**
1. **This command cannot run as written on a fresh run.** `create_run` protects
   `04-artifacts` to `0o555` at creation (`init_run.py:26,72`; `protect_run.py:21,36-37`),
   and this file never chmods it writable. Only `curate-assay-detect.md:17`
   carries `chmod -R u+w $RUN/04-artifacts`. Both the `run_evidence` invocation
   (`:43-44`) and the `vocabulary_evidence` invocation (`:71-72`) write into that
   tier and will hit `PermissionError`.
2. `:55` asserts `assays.parquet` holds "137 internal assays" and rule 2 (`:135-136`)
   repeats "137 ids, all in the range 1-188". These are extract-dependent
   constants of exactly the kind `64f233d` removed elsewhere in this same file.
   Rule 6's nine-row measurement/analysis table (`:182-190`) and rule 3's list of
   12 bare-numeric protocol values (`:145-147`) are the same class.
3. `run_evidence`'s `assert_writable` name list (`run_evidence.py:889-892`)
   includes `vocabulary-curator.csv`, `vocabulary-defects.csv` and
   `mode3-disposition.csv`, which `run_evidence` does not write —
   `vocabulary-curator.csv` is an *input* (`:906`) and the other two are
   `run_detect`'s (`run_detect.py:79`).

---

## 3. `curate-assay-detect.md` (88 lines, 3.6 KB)

**What it does.** Generates this run's proposals. Unprotects `04-artifacts`,
copies forward RUN1's `vocabulary-curator.csv`, runs the evidence pass then the
detection pass into the run's own directory, re-protects the tier, then sorts
every cohort three ways against the durable ruling store and records the counts
in the lockfile.

**Invocations.**

| line | exact command |
|---|---|
| `:16` | `RUN=assets/RUN2` |
| `:17` | `chmod -R u+w $RUN/04-artifacts` |
| `:18` | `cp assets/RUN1/04-artifacts/vocabulary-curator.csv $RUN/04-artifacts/ 2>/dev/null \|\| true` |
| `:19-20` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow \`<br>`  python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts` |
| `:21-22` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow \`<br>`  python -m assay_hygiene.run_detect   $RUN/01-extract $RUN/04-artifacts` |
| `:33-38` | `PYTHONPATH=scripts uv run python -c "…"` → `protect_run.protect` / `protect_run.verify` (`protect_run.py:25,41`) |
| `:60-77` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` → `carryforward.split` (`carryforward.py:45`), `rulings.load` |
| `:83-87` | `PYTHONPATH=scripts uv run python -c "…"` → `runstate.update` (`runstate.py:72`) |

**Reads.** `$RUN/01-extract/{edges,membership,assays,samples,nodes}.parquet`
(`run_evidence.py:895-899`); `assets/RUN1/04-artifacts/vocabulary-curator.csv`;
`$RUN/04-artifacts/{vocabulary-proposed,vocabulary-curator}.csv`
(`run_evidence.py:905-906`); `$RUN/04-artifacts/{findings.csv,mode3-disposition.csv,vocabulary-defects.csv}`
read back by `run_detect.main` (`run_detect.py:1096-1098`);
`assets/rulings/pairs.tsv`; `assets/assay-run.json`.

**Writes.** Everything `run_evidence` writes (§2). Plus `run_detect`'s
`ARTIFACTS` (`run_detect.py:79-80`) = `vocabulary-defects.csv`, `findings.csv`,
`mode3-disposition.csv`, `cohorts-to-review.csv` (`COHORTS_NAME`,
`run_detect.py:77`), `mode1-review.html` (`review.REVIEW_NAME`,
`review.py:88`), `detect-report.md` (`REPORT_NAME`, `run_detect.py:72`). Plus
mode bits back to `0o555`/`0o444` on `04-artifacts`. Plus
`assets/assay-run.json` (`step`, `carried_pairs`, `carried_from_run`).

**Safety gates.** `run_evidence.main:888` and `run_detect.main:1088` both call
`_writeguard.assert_writable`, which refuses to write through a symlink
(`_writeguard.py:38`). `run_detect` also fails fast if `gate.main` or
`classify.main` returns non-zero (`run_detect.py:1092-1095`); those two return
exit **2** naming `run_evidence` when `claims.parquet` or `vocabulary.csv` is
missing from `out_dir` (`gate.py:947-954`, `classify.py:1919-1926`) — the doc's
claim at `:26-28` is accurate. `run_detect` does **not** call `run_evidence`
(confirmed: `run_detect.main` calls only `G.main` and `X.main`), so the doc's
"Both are needed, in that order" (`:25`) is correct.

**Ordering prerequisites.** `curate-assay-init` (needs the run directory and the
lockfile; `runstate.update` raises `RunLocked` if no run is open,
`runstate.py:83-84`). `curate-assay-vocabulary` should precede it if the
operator wants proposals merged, because `run_evidence` reads
`vocabulary-proposed.csv` from `out_dir` (`run_evidence.py:905`) and this command
copies forward only `vocabulary-curator.csv` (`:18`), not
`vocabulary-proposed.csv`.

**Carry-forward: documented as non-functional, and it is.** `:70-73` states
plainly that nothing derives `widths` and that carry-forward "currently carries
NOTHING". Confirmed at `carryforward.py:18-24` and by `split`'s logic
(`carryforward.py:54-58`): with `ruled_width == {}`, `was is None`, so every
matched pair falls to `WIDENED`. Root cause is the unwritten provenance sidecar
(§1 defect 2).

**Defects found.**
1. **The carry-forward snippet (`:60-77`) is a non-runnable stub.** `cohorts = []`
   and `widths = {}` are left as comments for the reader to fill in
   (`:65-66`), and nothing in `scripts/` builds a `list[carryforward.Cohort]`
   from `findings.csv` or `cohorts-to-review.csv`. There is no producer of the
   `Cohort` dataclass (`carryforward.py:38-42`) anywhere outside tests.
2. **`:86` contains a literal placeholder inside executable code**:
   `update(Path('assets'), step='detect', carried_pairs=<n>, carried_from_run=1)`.
   `<n>` is a syntax error if pasted.
3. `:10` and `:13` state `assay-hygiene/` is "33 symlinks into `assets/RUN1/`"
   and "27 of 33 artifacts are reachable that way". These are counts of an
   untracked directory outside this worktree; unverifiable here.

---

## 4. `curate-assay-review.md` (68 lines, 2.8 KB)

**What it does.** Describes serving two review surfaces per lane (an HTML page
carrying context and a CSV carrying one row per cohort with a blank `ruling`
column), then ingesting the operator's edited CSV back into the durable ruling
store and backing the store up in the same step.

**Invocations.**

| line | exact command |
|---|---|
| `:23-40` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` → `ingest.ingest` (`ingest.py:36`), `rulings.load`/`save`, `store_backup.back_up` (`store_backup.py:27`) |

Named-but-not-invoked: `assay_hygiene.review_mode2.build_blocks`
(`review_mode2.py:347`), `.to_csv` (`:443`), `.REVIEW_NAME` (`:73`),
`.CSV_NAME` (`:72`), and `assay_hygiene.review.cohort_key` (`review.py:587`) —
`:14-18` tells the agent to use them but gives **no command line** for
`review_mode2.main` (`review_mode2.py:701`).

**Reads.** the operator-edited CSV (path left as a `<placeholder>` at `:31`);
`assets/rulings/pairs.tsv`.
**Writes.** `assets/rulings/pairs.tsv` (rewritten whole, `rulings.py:97`);
`~/backups/rulings-<stamp>.tar.gz` (`store_backup.py:37`).

**Safety gates / refusals.** `ingest.ingest` refuses **whole-file**
(`ingest.py:18-20,32`) on: a missing `cohort_key` **or** `ruling` column
(`:39-44`); a key matching no cohort in this run (`:53-57`); a verdict outside
`APPROVE`/`REJECT`/`WRONG_ASSAY`/`UNSURE` (`rulings.py:44`; `ingest.py:58-61`);
one pair key ruled two ways in the same file (`:63-67`). A blank or `nan` ruling
is skipped, not defaulted (`:51-52`). `back_up` refuses an absent store
(`store_backup.py:30-34`) and re-opens the archive to prove `pairs.tsv` is inside
before returning (`:41-46`). `save` raises `ConflictingRulings` on a cross-file
conflict (`rulings.py:81`); the doc's "do not resolve it" (`:63-68`) matches
`_collapse`'s behaviour.

**Ordering prerequisites.** `curate-assay-detect` (the cohorts must exist).
Precedes `curate-assay-resolve`.

**Defects found — the most serious in the mode.**
1. **The documented ingest cannot join, because no surface emits a `cohort_key`
   column.** `ingest.ingest` requires the literal column `cohort_key`
   (`ingest.py:28,39-44`) and refuses the whole file without it. But:
   - `review_mode2.to_csv` (`review_mode2.py:443-472`) emits
     `band, lab, sample_type, parent_types, assay, field, value, n_rows,
     n_samples, precedent_min, precedent_max, n_contested, neighbour_role,
     neighbours_holding_it, example_neighbours, example_neighbour_types,
     FLAG_analysis_twin, tiers, gates, dates, example_uuids, ruling, note` —
     **no `cohort_key`**. It computes `R.cohort_key(b)` only as a preset lookup
     key (`:470-471`), never as a written column.
   - `run_detect.cohort_table`'s `COHORT_COLUMNS` (`run_detect.py:472-477`) has
     no `cohort_key` and **no `ruling` column at all**.
   - `review.EXPORT_COLUMNS` (`review.py:111`) is `BLOCK_KEY + ("ruling","note")`
     — the six key fields as separate columns, not the joined key.
   The only artifact in the package carrying a literal `cohort_key` column is
   the agent-judging path (`dossier.py:308`, consumed by
   `review_verdicts.py:83,105-113`), which no assay command invokes.
2. **The ingest snippet is a stub**: `cohorts = {}` at `:32` with the comment
   "cohort_key -> pair key, exactly as the review surface emitted". Nothing in
   `scripts/` builds that mapping. `<the file the operator edited>` (`:31`),
   `<today>` (`:34`) and `<stamp>` (`:39`) are literal placeholders inside the
   code block.
3. `:55` says the ingest refuses "a sheet with no `cohort_key` column". It also
   refuses a sheet with no `ruling` column (`ingest.py:39`). Under-stated.
4. `:54` says it refuses "one cohort ruled two different ways". The check is on
   the **pair key**, not the cohort key (`ingest.py:62-67`), so two *different*
   cohorts collapsing to one pair key and ruled differently also refuse — a
   broader and more surprising refusal than documented.
5. `review_mode2.main` defaults `artifacts="assay-hygiene"` (`review_mode2.py:701`)
   — the same default-path clobbering hazard `curate-assay-detect.md:7-14` warns
   about — and it has **no `_writeguard` call**. The review doc gives no
   invocation and therefore no warning.

---

## 5. `curate-assay-resolve.md` (53 lines, 2.2 KB)

**What it does.** Turns approved rulings into a per-project-checked SEEK write
set. Reads the extract's assays and samples plus the approved rows, resolves each
internal assay id to the SEEK `assay_id` belonging to the sample's own project,
and writes a `MANIFEST.csv` of gate-checked targets plus an `EXCLUDED.csv` of
authorised registrations with no correct target.

**Invocations.**

| line | exact command |
|---|---|
| `:12-26` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` → `resolve_targets.resolve` (`resolve_targets.py:39`) |

**Reads.** `assets/RUN2/01-extract/assays.parquet` (`:17`),
`assets/RUN2/01-extract/samples.parquet` (`:18`),
`assets/RUN2/04-artifacts/approved-rows.csv` (`:19`).
**Writes.** `assets/RUN2/04-artifacts/MANIFEST.csv` (`:21`),
`assets/RUN2/04-artifacts/EXCLUDED.csv` (`:22`).

**Safety gate.** `resolve` builds `(internal_assay_id, project_id) -> assay_id`
(`resolve_targets.py:42-44`) and keeps a row only when the sample's own project
set yields exactly one candidate (`:64-78`). `assert_subset`
(`resolve_targets.py:88-98`) raises `CrossProjectTarget` for any sheet row not in
the manifest; `preflight.check` wraps it (`preflight.py:89-92`).

**Ordering prerequisites.** `curate-assay-review` (approved rulings must exist).
Must precede `curate-assay-write` — `MANIFEST.csv` is what preflight checks the
sheet against.

**Defects found.**
1. **`approved-rows.csv` has no producer anywhere in the repository.** Grep over
   `scripts/`, `commands/`, `tests/` returns exactly two hits:
   `commands/curate-assay-resolve.md:19` and
   `docs/superpowers/plans/2026-08-27-assay-hygiene-mode-commands.md:2299` (the
   plan text that generated the doc). Nothing writes it, and the chain from the
   ruling store (`assets/rulings/pairs.tsv`, keyed on
   `(sample_type, internal_assay_id, action)`) to a row-level
   `(sample_id, internal_assay_id)` frame is undocumented and unimplemented.
   **This is the break in the pipeline: review's output and resolve's input do
   not meet.**
2. **The doc lists two exclusion reasons; the code has three.** `:41-46` says
   "Two reasons a row is dropped" and names `NO_PROJECT` and `NO_CANDIDATE`.
   `resolve_targets.py:32` defines a third, `AMBIGUOUS` = "internal assay exists
   in more than one of the sample's projects", excluded at `:71-75`. It was added
   in `833e9be` (which touched `curate-assay-detect.md` and
   `curate-assay-init.md` but **not** `curate-assay-resolve.md`). An operator
   following `:47` ("Report both counts") under-reports the exclusion set.
3. `:44-46` quotes RUN1 figures (374 no-project rows, 45 no-candidate) as if
   current. Extract-dependent.

---

## 6. `curate-assay-write.md` (109 lines, 4.2 KB)

**What it does.** The only command that touches production. It documents the
write mechanism (an `UPDATE_ASSAY` sheet posted to `/seek/sampleupload/` with
both Current columns blank, chosen because it is structurally incapable of
deleting), instructs the operator to capture a `MAX(id)` rollback handle and
verify a database backup, run the eight-refusal preflight, then submit in
2,000-row chunks reconciling each against a `COUNT(*)` query.

**Invocations.**

| line | exact command |
|---|---|
| `:35` | `SELECT MAX(id) FROM seek_production.assay_assets;` (SQL, operator-run) |
| `:39` | `DELETE FROM seek_production.assay_assets WHERE id > <handle>;` (documented undo) |
| `:43-48` | `PYTHONPATH=scripts uv run python -c "…"` → `runstate.read`/`update` |
| `:59-63` | `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "…"` → `preflight.check` (`preflight.py:47`) |
| `:84` | `SELECT COUNT(*) FROM seek_production.assay_assets WHERE id > <handle>;` |
| `:88-92` | `PYTHONPATH=scripts uv run --with pandas python -c "…"` → `chunker.reconcile` (`chunker.py:38`) |

**Reads.** `assets/assay-run.json`; the sheet and `MANIFEST.csv` (both passed as
bare undefined names in the snippet). **Writes.** `assets/assay-run.json`
(`rollback_id`, `chunks_done`); **`seek_production.assay_assets`** rows, via a
manual HTTP post the doc does not script.

**The eight refusals — doc vs. `preflight.py`.** All eight in `:66-69` are real
and implemented, in a different order than listed:

| `preflight.py` | refusal |
|---|---|
| `:52-56` | a sheet named `UPDATE` anywhere in the workbook (`FORBIDDEN_SHEET`, `:35`) |
| `:58-62` | more than `CHUNK_CAP = 2000` rows (`:34`) |
| `:64-70` | a Current pair parsing as two ints (the sole path to the delete branch) |
| `:72-78` | an unparseable New pair |
| `:80-87` | a blank or non-string `uid` |
| `:89-92` | any row absent from the gate-checked manifest |
| `:94-97` | no captured rollback handle |
| `:99-103` | a backup that is absent or unverified (`size` **and** `trailer_ok`) |

`chunker.reconcile` (`chunker.py:38-49`) refuses an over-count as well as a short
write, as `:99-101` states. `chunker.chunks` defaults to `CHUNK_CAP`
(`chunker.py:33`).

**Ordering prerequisites.** `curate-assay-resolve` (the manifest), and a
rollback handle plus verified backup recorded in the lockfile before preflight
will pass.

**Defects found.**
1. **`--confirm` does not exist.** `:8` states "It writes nothing without
   `--confirm`." Grep over `scripts/` returns **zero** occurrences of
   `--confirm`; the only hit in the repository is
   `tests/test_assay_hygiene_commands.py:40`, which asserts the *string appears in
   the doc*. There is no CLI in the assay mode at all, so there is no flag to
   pass — the write is a manual browser/HTTP submission. The test therefore pins
   a promise nothing implements.
2. **Nothing builds the `UPDATE_ASSAY` sheet.** Grep for `UPDATE_ASSAY`,
   `current_pair`, `new_pair`, `sampleupload` across `scripts/`, `commands/`,
   `tests/` finds only `preflight.py:7,65,73` (the consumer) and
   `curate-assay-write.md:12`. No module produces a frame with
   `sample_id, assay_id, uid, current_pair, new_pair`. The central artifact of
   the only production-touching command has no builder.
3. **`registration_payload.py` (144 lines) is orphaned.** It builds the
   `existing UNION additions` complete-list payload for the *other two*
   mechanisms — `PATCH /nextseek_api/assays/{uid}/` and
   `smart_merge_assay_assets` (`registration_payload.py:11-13`) — which
   `curate-assay-write.md:19-22` explicitly rejects in favour of the
   `UPDATE_ASSAY` sheet. No command references it.
4. `:59-63` passes `sheet, manifest, sheet_names, backup, rollback_id` as bare
   undefined names; the snippet is not runnable. `:46` and `:84` embed literal
   `<handle>` placeholders in code.
5. `:17-18` quotes 25,769 rows / 202,016 memberships / 25,912;
   `registration_payload.py:21-24` quotes 26,188 rows / 102 assays / 202,016 /
   24,007 samples / 25,912; `curate-assay-resolve.md:31` and
   `resolve_targets.py:11` quote 26,188. Three different row totals across the
   mode for what appears to be the same set.

---

## 7. `curate-assay-status.md` (48 lines, 1.6 KB)

**What it does.** Reports where the campaign stands. Explicitly writes nothing
(`:5`). Prints the run lockfile's run number, open flag, step, extract sha,
carry-forward counts and write sub-state; then the ruling store's size broken
down by verdict; then the three newest backup tarballs.

**Invocations.**

| line | exact command |
|---|---|
| `:8-21` | `PYTHONPATH=scripts uv run python -c "…"` → `runstate.read` (`runstate.py:34`) |
| `:27-35` | `PYTHONPATH=scripts uv run --with pandas python -c "…"` → `rulings.load` (`rulings.py:101`) |
| `:42` | `ls -lt ~/backups/rulings-*.tar.gz 2>/dev/null \| head -3 \|\| echo "NO BACKUPS"` |

**Reads.** `assets/assay-run.json`; `assets/rulings/pairs.tsv`;
`~/backups/rulings-*.tar.gz`. **Writes.** nothing.
**Refusals.** none. `runstate.read` returns `{}` rather than raising on absence
(`runstate.py:35-38`), which the doc handles (`:11-12`).
**Ordering prerequisites.** none — safe at any point.

**Notes.** The keys it prints (`run`, `open`, `step`, `extract_sha`,
`carried_pairs`, `carried_from_run`, `write.{chunks_done,rollback_id,backup_verified}`)
all exist in `runstate.create`'s payload (`runstate.py:57-69`). `:45-48`'s advice
about `runstate.close` matches `runstate.py:93-99`.

---

## 8. `curate-assay-backup.md` (47 lines, 1.9 KB)

**What it does.** Writes a dated, verified tarball of the ruling store by hand,
for use outside `curate-assay-review`'s automatic per-ingest backup. Documents
the restore command and records the accepted limit that backups live on the same
machine as the store.

**Invocations.**

| line | exact command |
|---|---|
| `:10-16` | `PYTHONPATH=scripts uv run --with pandas python -c "…"` → `store_backup.back_up` (`store_backup.py:27`) |
| `:30` | `tar -xzf ~/backups/rulings-<stamp>.tar.gz -C assets/` |

**Reads.** `assets/rulings/` (whole directory, `store_backup.py:39`).
**Writes.** `~/backups/rulings-<stamp>.tar.gz` (`store_backup.py:37`).
**Refusals.** `BackupUnverified` if `<store>/pairs.tsv` is absent
(`store_backup.py:30-34`) — doc `:24-26` matches; `BackupUnverified` if the
written archive does not contain `pairs.tsv` on read-back
(`store_backup.py:41-46`) — doc `:19-22` matches.
**Ordering prerequisites.** none; requires a store to exist.
**Correct claim verified:** `archive.add(store, arcname=store.name)`
(`store_backup.py:39`) means the archive holds the `rulings/` directory itself,
so `-C assets/` restores to `assets/rulings/` — doc `:33-34` is accurate.

`:35-36`'s claim that `curate-assay-init` "refuses to open a run when the store
is missing and names this command" is **half true**: `require_store` refuses
(`init_run.py:40`) and names the *backup directory* and a `tar -xzf` line
(`init_run.py:45-46`), but does **not** name `curate-assay-backup`. It names the
nonexistent `curate-assay-init --migrate-from` instead (`init_run.py:48`).

---

## 9. The true workflow sequence

```
curate-assay-init                     opens assets/RUN<n>, protects 00-06, proves/creates assets/rulings
   │                                  ── lockfile assets/assay-run.json, open=True
   ├─→ curate-assay-vocabulary        needs 04-artifacts WRITABLE (undocumented chmod)
   │      run_evidence  ──────────────→ vocabulary.csv, vocabulary-unresolved.csv, precedent.csv,
   │      vocabulary_evidence ────────→ claims.parquet, mode3-*.csv, evidence-report.md,
   │      agent writes ───────────────→ vocabulary-evidence.csv, vocabulary-proposed.csv
   │
   ├─→ curate-assay-detect            chmod u+w; cp RUN1 vocabulary-curator.csv
   │      run_evidence (AGAIN) ───────→ re-merges vocabulary-proposed.csv from the step above
   │      run_detect ─────────────────→ findings.csv, cohorts-to-review.csv, mode1-review.html,
   │                                    detect-report.md, vocabulary-defects.csv, mode3-disposition.csv
   │      protect_run.protect         re-locks 04-artifacts
   │      carryforward.split          ⚠ STUB: no producer of `cohorts`; carries nothing by design
   │      runstate.update(step=…)
   │
   ├─→ curate-assay-review            review_mode2 builds the Mode 2 CSV/HTML (no invocation given)
   │      ingest.ingest ─────────────→ assets/rulings/pairs.tsv (merged, whole-file rewrite)
   │      store_backup.back_up ──────→ ~/backups/rulings-<stamp>.tar.gz
   │                                  ⚠ BREAK 1: no surface emits the `cohort_key` column ingest requires
   │
   │      ??? ───────────────────────→ approved-rows.csv
   │                                  ⚠ BREAK 2: no producer exists anywhere in the repo
   │
   ├─→ curate-assay-resolve           resolve_targets.resolve
   │                                 → MANIFEST.csv (project-gated), EXCLUDED.csv (3 reasons, 2 documented)
   │
   └─→ curate-assay-write             ??? builds the UPDATE_ASSAY sheet  ⚠ BREAK 3: no builder
          SQL MAX(id) → runstate.update(rollback_id)
          verified mysqldump → runstate.update(backup_verified)
          preflight.check (8 refusals)
          manual POST /seek/sampleupload/ in 2,000-row chunks
          SQL COUNT(*) → chunker.reconcile per chunk

curate-assay-status    any time, writes nothing
curate-assay-backup    any time, store must exist
```

Hard ordering constraints, from code rather than prose:
1. `init` before everything — `runstate.update` raises `RunLocked` with no open
   run (`runstate.py:83-84`); `create_run` makes the tiers.
2. `run_evidence` before `run_detect` — `gate.main` and `classify.main` return
   exit 2 naming `run_evidence` when `claims.parquet`/`vocabulary.csv` are absent
   (`gate.py:947-954`, `classify.py:1919-1926`).
3. `vocabulary`'s `vocabulary-proposed.csv` must exist before the `run_evidence`
   pass that is to merge it (`run_evidence.py:905`).
4. `resolve` before `write` — `preflight.check` calls `assert_subset` against the
   manifest (`preflight.py:89-92`).
5. `review` before `resolve` — semantically, though **no artifact connects them**
   (Break 2).

---

## 10. Orphans, duplications and contradictions

**Orphaned relative to the eight commands** (present, tested, invoked by nothing):
- `scripts/assay_hygiene/registration_payload.py` — builds the payload for the
  two mechanisms `curate-assay-write.md:19-22` rejects.
- `scripts/assay_hygiene/dossier.py` + `review_verdicts.py` — the only code that
  emits and consumes a literal `cohort_key` column (`dossier.py:308`,
  `review_verdicts.py:83`). This is the 15-agent judging path; no assay command
  mentions either module.
- `scripts/assay_hygiene/validation_sample.py` (1,510 lines),
  `backtest.py` (899), `baseline.py`, `stage0.py`, `stage0_apply.py`,
  `driver_extract.py`, `driver_stage0.py`, `extract.py`, `compatibility.py`,
  `precedent.py` — none is named in any of the eight command files. Only
  `extract.py`'s outputs are referenced, implicitly, as `01-extract/*.parquet`.
- **No command documents how `01-extract/*.parquet` is produced.**
  `curate-assay-init.md:66` asks the operator for "`<sha of the extract you
  pulled>`" without saying what pulls it. `driver_extract.py` and `extract.py`
  exist; no command invokes them.

**Duplication.** `run_evidence` is invoked by two commands into the same output
directory (`curate-assay-vocabulary.md:44`, `curate-assay-detect.md:20`). Only
`curate-assay-detect.md:17` chmods the tier writable first, so the two
invocations are not interchangeable.

**Contradictions with other documentation:**

1. **`skills/curation/SKILL.md:145` still assigns `/curate-assay-vocabulary` to
   `schema` mode** — "→ `schema` mode (`/curate-assay-vocabulary`), the
   assay-hygiene stage B2 judgment step" — while `SKILL.md:34` assigns it to the
   `assay` mode. `eb8777e`'s message says the command "moves from the schema row
   to the assay row"; only the table row moved. Both statements are in the same
   file. `tests/test_mode_table.py` parses only the `## Modes` table
   (`test_mode_table.py:28-41`) and cannot see line 145.
2. **`SKILL.md:42` says "one mode among four"** in the `pipeline` section, after
   `SKILL.md:34` added the fifth.
3. **`SKILL.md:3`, `.claude-plugin/plugin.json:4` and
   `.claude-plugin/marketplace.json` all enumerate exactly four modes** —
   "Modes are pipeline …, fdh …, schema …, report …" — with no `assay`. The
   installed skill description in the running session shows the same four.
   `test_mode_table.py` does not check the frontmatter description.
4. **`README.md:58` lists `/curate-assay-vocabulary` under `schema` mode** and
   describes it reading `assay-hygiene/vocabulary-unresolved.csv` — the default
   path, i.e. the exact clobbering hazard `64f233d` removed from the command
   itself. The README lists **none** of the other seven assay commands and has no
   `assay` mode section (`README.md:20-75`).
5. **`CHANGELOG.md` contains zero occurrences of `curate-assay` or
   `assay-hygiene`.**
6. **`/curate-status` does not know the assay mode exists.**
   `commands/curate-status.md:5` says "all four dmac-curation modes";
   `:26-31` lists pipeline / fdh / schema / report. `scripts/status.py` has no
   assay branch (its only `assay` hits are `assay_sheets/` and
   `/curate-resolve-assays`, `status.py:29-32,46,78-84`). Yet `SKILL.md:38`
   asserts "`/curate-status` reports per mode". The assay mode has its own
   `/curate-assay-status` instead.
7. **`skills/curation/ASSAY.md:35` mis-describes `curate-assay-vocabulary`** as
   "unresolved terms → operator sheet → ingest | ruling store". The command
   writes `vocabulary-proposed.csv` (`curate-assay-vocabulary.md:266`), an
   agent-authored proposal file with `provenance = proposed`; it never touches
   `assets/rulings/` and there is no operator sheet or ingest in it. Only
   `curate-assay-review` and `curate-assay-init` write the ruling store.
8. **`ASSAY.md:9` says tiers "`00`–`06` read-only from creation"** — correct
   (`init_run.py:26`) — but `ASSAY.md` never mentions that `04-artifacts` must be
   chmodded writable for `detect` and `vocabulary` to run, which
   `curate-assay-detect.md:17` does and `curate-assay-vocabulary.md` does not.

**Internal contradiction between two command descriptions.**
`curate-assay-backup.md:5-7` says "`curate-assay-review` does this automatically
on every ingest". `curate-assay-review.md:46-48` agrees ("Backup is part of
ingest, not a separate step"). But the backup is a *third line in a `python -c`
snippet* (`curate-assay-review.md:39`), not a property of `ingest.ingest` —
`ingest.py` neither imports nor calls `store_backup`. Skipping that line skips
the backup silently.

---

## 11. Coverage of these files by tests

`tests/test_assay_hygiene_commands.py` (58 lines) is the only test over the
command docs. It asserts, over the eight names at `:14-17`: the file exists
(`:21`), starts with `---\n` and has `description:` in the frontmatter
(`:26-30`), contains no `--dry-run` (`:34`), that `curate-assay-write.md`
contains the literal strings `--confirm`, `rollback`, `backup`, `manifest`,
`chunk` (`:38-42`), that `curate-assay-init.md` contains `tar` and `backup`
(`:45-47`), and that any line invoking `run_evidence`/`run_detect` also contains
`RUN` or `out` or ends in `\` (`:50-57`).

Nothing tests: that a documented file path has a producer; that a documented
module symbol exists; that a documented flag is implemented; that a documented
exclusion list matches the code; or that the snippets parse as Python.
