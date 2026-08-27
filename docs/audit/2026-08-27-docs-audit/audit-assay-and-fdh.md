# Drift audit — `skills/curation/ASSAY.md` and `skills/curation/FDH.md`

Worktree: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`, branch
`dev-docs`, tip `833e9be`. Every finding below was verified by opening the cited source
file and reading the contradicting lines in this worktree. Nothing was executed against a
network or a live server.

| doc | lines | verdict |
|---|---|---|
| `skills/curation/ASSAY.md` | 72 | **SUBSTANTIAL_DRIFT** — three false statements, and five omissions that stop an operator running the mode |
| `skills/curation/FDH.md` | 107 | **SUBSTANTIAL_DRIFT** — one false safety-relevant claim, one unachievable workflow, three material omissions |

---

# Part 1 — `ASSAY.md`

## Adequacy verdict

72 lines does **not** let an operator run the mode end to end, and the gap is not one of
depth — it is that four things a run cannot start or finish without are simply absent.
For scale: `ASSAY.md` covers 8 commands, 39 modules (`scripts/assay_hygiene/*.py`) and 40
test files in 72 lines. `PHASES.md` covers 14 commands in 506. `SCHEMA.md` covers **one**
command in 230.

A reader who follows `ASSAY.md` alone:

- cannot produce `01-extract/` (A4) — the mode has no first step;
- hits `PermissionError` on the first driver invocation (A3);
- believes already-ruled cohorts are being carried forward when nothing is (A1);
- believes `curate-assay-vocabulary` writes rulings (A2);
- believes `init → … → write` is a connected chain when three joints have no code (A5);
- meets `Mode 3: 0 rows` in `detect-report.md` with no way to read it correctly (A6);
- has no restore procedure and no way to tell where an interrupted run stopped (A9).

---

## A1 — WRONG: the carry-forward split is described as operational; the CARRIED bucket is unreachable

**Doc** — `ASSAY.md:43-53`, the whole `## The carry-forward split` section, opening:

> On `detect`, every cohort is sorted three ways against the store: **already
> ruled** (carried), **ruled in a narrower context** (surfaced, never applied),
> and **never seen** (goes to the operator).

**Reality** — `scripts/assay_hygiene/carryforward.py:18-24`:

> NOTHING DERIVES `ruled_width` YET. It is the number of rows the ORIGINAL ruling
> was made against, which lives in the provenance sidecar rather than in the pair
> store, and no code assembles it today. Callers therefore pass `{}`, every
> matched pair lands in WIDENED, and the practical effect is that carry-forward
> carries nothing and re-asks everything. [...] it is not the finished feature,
> and a reader should not mistake a working split for a working carry-forward.

Confirmed in `split` itself (`carryforward.py:52-58`): with `ruled_width == {}`,
`was is None`, so the `CARRIED` branch is never taken. `commands/curate-assay-detect.md:60-77`
hard-codes `widths = {}` in its own snippet and states the same thing. The root cause is
that the provenance sidecar `rulings.py:31-33` and `carryforward.py:20` both refer to is
never written — `init_run.migrate_into_store` returns provenance records under key
`"provenance"` (`init_run.py:107-109`) and nothing persists them.

`ASSAY.md` is the only document in the set that describes the split as working.

**Proposed fix** — replace `ASSAY.md:43-53` entirely:

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

---

## A2 — WRONG: the `curate-assay-vocabulary` row misstates both what the command does and what it writes

**Doc** — `ASSAY.md:35`:

```
| `curate-assay-vocabulary` | unresolved terms → operator sheet → ingest | ruling store |
```

**Reality** — the command produces an **agent-authored proposal file**, not an operator
sheet, and never touches `assets/rulings/`:

- `commands/curate-assay-vocabulary.md:266` — "Write `$RUN/04-artifacts/vocabulary-proposed.csv`
  with exactly these columns: `source_field,raw_value,internal_assay_id,internal_assay_title,support,n_samples,purity,provenance`".
- `:276` — "`provenance` = `proposed`, spelled exactly that way", which sits *below*
  `learned` and `curator` in precedence (`:260`) and is excluded from tiering entirely
  (`scripts/assay_hygiene/_schema.py:618`).
- `grep -n "rulings\|ingest\|pairs.tsv" commands/curate-assay-vocabulary.md` returns no
  write to the ruling store. Only `curate-assay-review` (via `ingest.ingest` + `rulings.save`)
  and `curate-assay-init` (via `migrate_into_store`) write `assets/rulings/pairs.tsv`.

The word "ingest" in that cell points the reader at the wrong command's mechanism, and the
"ruling store" write target is the load-bearing error: it implies `curate-assay-vocabulary`
produces durable human judgement subject to the store's conflict refusal, when it produces
a low-precedence proposal a curator can overrule.

**Proposed fix** — replace the `ASSAY.md:35` row:

```markdown
| `curate-assay-vocabulary` | unresolved terms → evidence → agent proposals | `vocabulary-proposed.csv` |
```

---

## A3 — MISSING: the run model never says how anything writes into a run

**Doc** — `ASSAY.md:9-11`:

> Runs are numbered and immutable at `assets/RUN<n>/`, tiers `00`–`06` read-only
> from creation.

**Reality.** True as far as it goes (`init_run.py:24-26`, `:62-73`; `protect_run.py:21-22`),
but three facts a run cannot proceed without are absent:

1. There are **eight** tiers, not seven. `TIERS = ("00-rulings", "01-extract",
   "02-agent-runs", "03-stage0-applied", "04-artifacts", "05-review", "06-findings",
   "07-process")` and `PROTECTED = TIERS[:-1]` (`init_run.py:24-26`) — `07-process` is
   the writable one, and the doc never mentions it exists.
2. `04-artifacts` — the `out_dir` every driver writes to — is `0o555` from creation, so
   `detect` and `vocabulary` must `chmod -R u+w` it first and re-protect afterwards.
   `commands/curate-assay-detect.md:17` does this; `commands/curate-assay-vocabulary.md`
   **does not**, and both its `run_evidence` (`:43-44`) and `vocabulary_evidence`
   (`:71-72`) invocations write into that tier. Following either the command file or
   `ASSAY.md`, the vocabulary step fails with `PermissionError`.
3. Re-protection is a separate explicit step (`commands/curate-assay-detect.md:33-38` →
   `protect_run.protect` / `verify`, `protect_run.py:25`, `:41`), not automatic.

**Proposed fix** — replace `ASSAY.md:7-11` with:

```markdown
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
```

---

## A4 — MISSING: nothing says how `01-extract/` is produced, so the mode has no first step

**Doc** — `ASSAY.md` never names the extract at all. `curate-assay-init.md:66` asks the
operator to record "`<sha of the extract you pulled>`" without saying what pulls it.
`grep -rn "driver_extract\|extract.py\|manage.py shell" commands/ skills/` returns **zero
hits** — every reference to `01-extract` in the command set is a *read*.

**Reality.** `scripts/assay_hygiene/extract.py:302` (`main`) runs **inside the production
`nextseek` container** under `manage.py shell`, using the Django alias `seek`
(= `seek_production`), and writes seven parquet files to `<outdir>`
(`extract.py:346-348`). It is reachable only through `scripts/assay_hygiene/driver_extract.py:22`
— `extract.py` has a `main()` but no `if __name__ == "__main__"` guard. The recipe lives
in `driver_extract.py:8-12` and nowhere else in the repo.

This is the mode's step zero and it is undocumented outside a module docstring.

**Proposed fix** — insert a new section after the run model:

```markdown
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
```

---

## A5 — MISSING: three joints in the documented pipeline have no code, and the doc presents an unbroken chain

**Doc** — `ASSAY.md:30-41`, the command table, reads as a working sequence from `init`
through `write`.

**Reality.** Three artifacts the chain depends on have no producer anywhere in the
repository. Each was verified by grep over `scripts/`, `commands/`, `tests/` in this
worktree:

1. **No review surface emits the `cohort_key` column `ingest` requires.**
   `ingest.py:28` sets `KEY_COLUMN = "cohort_key"` and refuses the **whole file**
   without it (`ingest.py:39-44`). But `review_mode2.to_csv` (`review_mode2.py:443-472`)
   emits `band, lab, sample_type, parent_types, assay, field, value, n_rows, n_samples,
   precedent_min, precedent_max, n_contested, neighbour_role, neighbours_holding_it,
   example_neighbours, example_neighbour_types, FLAG_analysis_twin, tiers, gates, dates,
   example_uuids, ruling, note` — no `cohort_key`; it calls `R.cohort_key(b)` only as a
   preset lookup (`:470-471`). `review.EXPORT_COLUMNS` (`review.py:111`) emits the six key
   fields as separate columns. `run_detect.COHORT_COLUMNS` (`run_detect.py:472-477`) has
   neither `cohort_key` nor `ruling`. The only artifact in the package carrying a literal
   `cohort_key` column is `dossier.py:308`, on the agent-judging path that no command invokes.
2. **`approved-rows.csv` has no producer.** `grep -rn "approved-rows" scripts/ commands/ tests/`
   returns exactly one hit: `commands/curate-assay-resolve.md:19`, which reads it. Nothing
   converts the pair-keyed store (`sample_type, internal_assay_id, action`) into the
   row-level `(sample_id, internal_assay_id)` frame `resolve_targets.resolve` expects.
3. **Nothing builds or submits the `UPDATE_ASSAY` sheet.** `grep -rn "UPDATE_ASSAY|current_pair|new_pair" scripts/ commands/ skills/`
   finds `preflight.py` (which *validates* those columns) and `commands/curate-assay-write.md:12`
   (which *describes* the mechanism in prose). `grep -rln "import requests|import urllib|import httpx|sampleupload" scripts/assay_hygiene/`
   matches only `preflight.py` — there is **no HTTP client in the package**. The submission
   is a manual browser/HTTP post; `--confirm`, which `commands/curate-assay-write.md:8`
   promises, does not exist in `scripts/` at all (the only hit in the repo is
   `tests/test_assay_hygiene_commands.py:40`, asserting the string appears in the doc).

**Proposed fix** — insert before `## Four things that will bite`:

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

Also amend the `ASSAY.md:39` write row so "submit" does not read as something the
package does:

```markdown
| `curate-assay-write` | preflight (8 refusals), chunk, **operator posts by hand**, reconcile | **production** |
```

---

## A6 — MISSING: the mode never explains its own modes, including that Mode 3 has no detector

**Doc** — `ASSAY.md` never uses the words "Mode 1", "Mode 2" or "Mode 3", yet the mode's
central artifact (`detect-report.md`) and its two review surfaces are organised by them.

**Reality.**

- `_schema.py:718-722`: `MODES = (MODE_1, MODE_2, MODE_3)`, `EMITTED_MODES = (MODE_1, MODE_2)`.
- `classify.mode3_findings()` (`classify.py:1336`) takes no argument and returns
  `pd.DataFrame(columns=S.FINDING_COLUMNS)` (`:1420`) — an empty frame carrying the full
  contract. Its docstring opens: *"There are none, and there is no detector to produce
  any. NOT SMALL. UNDETECTED."*
- `run_detect.py:53-55`: *"REPORT MODE 3 AS UNDETECTED, NEVER AS SMALL. Its zero is the
  absence of a detector, not a measurement that contradictions are rare. Those are
  different findings and only one of them is true."*
- Mode 2's largest class is emitted-but-unreachable: 99,449 of 167,454 rows read
  `type_registrations == 0` and carry `CLS_UNREACHABLE` / `GATE_UNREACHABLE`, still
  emitted, *"because a proposal that vanishes reads to a curator exactly like one that was
  never generated"* (`_schema.py:768-776`).

An operator handed `detect-report.md` with `Mode 3: 0` and no reference doc will read it
as "we checked and there are almost no wrong assays". That is the exact misreading the
code goes out of its way to prevent, and the mode's reference doc does not carry the
correction.

**Proposed fix** — insert after the run model:

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

---

## A7 — WRONG: the "3.9%" sentence is unsourced and attaches the wrong number to the wrong claim

**Doc** — `ASSAY.md:26-28`:

> Those 5 were excluded from the store and put back to the operator, never
> resolved by a rule. Lab was the discriminator in three of the five, which is
> the measured cost of dropping it from the key: 3.9%.

**Reality** — `scripts/assay_hygiene/migrate_rulings.py:115-119`, the only in-repo
breakdown of those five conflicts:

> Three of the five are Mode 2 disagreeing with itself. The other two involve Mode
> 1, which the plan's original 156/114/3 measurement omitted: one is Mode 1
> against itself (APPROVE vs WRONG_ASSAY) and one is Mode 1 APPROVE against Mode 2
> REJECT -- the only cross-source disagreement in the set.

The three-of-five split is by **source lane**, not by lab. `grep -rn "discriminator" scripts/ docs/ commands/ skills/`
returns the word only in `mode2.py:288`, `run_evidence.py:370` and `review_mode2.py:286`
(all unrelated) — and in `ASSAY.md:27` itself. There is no source anywhere for "lab was
the discriminator in three of the five".

The arithmetic is also mismatched: 3.9% is 5/127, the whole conflict rate; 3/127 is 2.4%.
The sentence attaches the five-key percentage to a three-key subclaim.

`rulings.py:19-24` says only that the operator's judgement *"rested on something the triple
discards"* — it does not name the discarded field.

**Proposed fix** — replace `ASSAY.md:24-28`:

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

---

## A9 — MISSING: no backup path, no restore, no way to resume

**Doc** — `ASSAY.md:61-64` says only that the store's "only protection is a tarball on one
machine". No path, no command, no restore line, no resume story.

**Reality.**

- Backups live at `~/backups/rulings-<stamp>.tar.gz`, written with `arcname=store.name`
  so `-C assets/` restores straight to `assets/rulings/` (`store_backup.py:37`, `:39`;
  `commands/curate-assay-backup.md:29-34`).
- `back_up` re-opens the archive and asserts `pairs.tsv` is inside, raising
  `BackupUnverified` otherwise (`store_backup.py:41-46`) — written after a 2026-08-27
  incident where a backup command exited 0 having produced a 0-byte file (`:6-8`).
- `init_run.require_store` refuses to open a run at all when `pairs.tsv` is absent, and
  its message names the backup directory and a `tar -xzf` line (`init_run.py:35-46`).
  Note: that same message ends by advising `curate-assay-init --migrate-from assets/RUN1`
  (`init_run.py:48`) — **a flag that does not exist**; `init_run.py` has no `argparse`, no
  `main()` and no `__main__` block, and the doc does the migration with an inline
  `python -c` (`commands/curate-assay-init.md:32-43`).
- The lockfile carries `step`, so `/curate-assay-status` tells you where a run stopped;
  `runstate.update` merges nested dicts one level so `write={"rollback_id": n}` cannot
  drop `backup_verified` (`runstate.py:57-69`, `:72-81`); `runstate.close` ends the run
  (`:93-99`).

**Proposed fix** — replace the "Nothing regenerates a human ruling" bullet at
`ASSAY.md:61-64` and add a section:

```markdown
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
```

---

# Part 2 — `FDH.md`

## F1 — WRONG: the base-URL override does not exist for Module 1, and the claim sits in the shared preamble

**Doc** — `FDH.md:7`, in the header block that introduces **both** modules:

> - Host: `https://fairdomhub.org` (default). Override via `.env` `FDH_BASE_URL` or `--base-url`.

**Reality.** True of `fdh_api.py` (`make_client`, `fdh_api.py:198-201`: `args.base_url or
os.environ.get("FDH_BASE_URL") or DEFAULT_BASE_URL`). **False of `submit.py`**:

- `scripts/fdh/submit.py:73` — `BASE_URL = "https://fairdomhub.org/"`, a module constant.
- All seven live call sites pass that constant directly: `:1375`, `:1389`, `:1467`,
  `:1570`, `:1619`, `:1658`, `:1687`.
- `parse_args` (`submit.py:1780-1841`) defines exactly two flags, `--step` and `--resume`,
  mutually exclusive. There is no `--base-url`.
- The only environment read in the whole file is `os.environ.get("FDH_API", "")` at
  `:1281`. `FDH_BASE_URL` appears nowhere.

Every run of `/fdh-upload` writes to fairdomhub.org. A reader who believes this line will
try to point the uploader at a staging host and will silently create real assays,
protocols and samples on production instead. This is the highest-consequence error in
either doc.

**Proposed fix** — replace `FDH.md:7-9`:

```markdown
- **Module 2 (`/fdh-api`)** — host `https://fairdomhub.org` by default; override
  with `--base-url` or `.env` `FDH_BASE_URL` (`scripts/fdh/fdh_api.py:198-201`).
- **Module 1 (`/fdh-upload`) is production-only.** `submit.py` hardcodes
  `BASE_URL = "https://fairdomhub.org/"` (`scripts/fdh/submit.py:73`) and reads no
  host from the environment; its only flags are `--step N` and `--resume`
  (`:1780-1841`). There is no staging mode. Every run writes to fairdomhub.org.
- Auth: `.env` `FDH_API` = JSON `{ "<name>": "<token>" }`. Token from
  fairdomhub.org → Profile → Actions → API Token. Never log tokens.
```

---

## F2 — STALE: "the 13-phase NExtSEEK pipeline"

**Doc** — `FDH.md:4`:

> These are two independent, standalone capabilities — NOT part of the 13-phase NExtSEEK
> pipeline (they do not consume `assay_sheets/` / flat sheets).

**Reality** — `skills/curation/PHASES.md:9`: "14 commands drive 12 phases. Phase 9 is split
into 9a … 9b; phases 4 and 8 were retired as numbers"; `PHASES.md:15`: "The 11 pipeline
phases run inventory (1) through email (13)." The highest phase *number* is 13; the
pipeline is not 13 phases.

`tests/test_mode_table.py:73` asserts `"13-phase pipeline" not in` **SKILL.md** only, which
is why the phrase survived here and in `commands/fdh-upload.md:7`.

**Proposed fix** — replace `FDH.md:3-5`:

```markdown
Load on demand when the user wants to **upload to FairDomHub** or **access the FDH API**.
These are two independent, standalone capabilities — NOT part of the NExtSEEK curation
pipeline (12 phases across 11 numbers, `PHASES.md`); they do not consume
`assay_sheets/` / flat sheets.
```

(The same phrase should be fixed at `commands/fdh-upload.md:7`, and the ban in
`tests/test_mode_table.py:73` widened past SKILL.md.)

---

## F3 — WRONG: the reuse-or-generate loop's library can never be populated for anyone but the author

**Doc** — `FDH.md:28` and `:35`:

> 1. **Check the library first** — read `scripts/fdh/generated/REGISTRY.md`. Reuse a script if one fits.
> …
> 5. **Contribute back** — add a `REGISTRY.md` row, show the diff, commit on approval.

**Reality** — `.gitignore:154-156`:

```
# Generated FairDomHub task scripts. Written per-task against live project ids
# and frequently carry sample uids; several are destructive (delete_samples_*).
scripts/fdh/generated/*.py
```

Confirmed with `git check-ignore -v scripts/fdh/generated/foo.py` →
`.gitignore:156:scripts/fdh/generated/*.py`. In this worktree
`ls -a scripts/fdh/generated/` returns `__init__.py` and `REGISTRY.md` only.

Three consequences the doc does not state:

- Step 1 ("check the library first") finds an **empty library on every installed copy of
  the plugin**, permanently. This is a design property of the ignore rule, not a stale
  file.
- Step 5's "commit on approval" cannot commit the script — the path is ignored. Only the
  `REGISTRY.md` row is committable, so a populated registry ships pointing at files nobody
  else has.
- The `--write` guard the loop promises (`FDH.md:101-102`) exists **only as prose plus the
  template at `FDH.md:50-97`**. There is no lint, no test, and no shared helper; nothing in
  the codebase enforces it. `tests/test_fdh_reference_docs.py:16-20` checks only that the
  registry's table header string is present.

**Proposed fix** — replace `FDH.md:25-37`:

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

---

## F4 — MISSING: `fdh_api.py`'s own five-verb read CLI is never mentioned

**Doc** — `FDH.md:39-48` presents the client purely as a Python library to import from a
generated script.

**Reality** — `scripts/fdh/fdh_api.py:234-274` builds a full argparse CLI with five
read-only subcommands, each accepting `--token`, `--user` and `--base-url`:

```
whoami | search QUERY [--type TYPE] | get TYPE ID | list TYPE ID RELATIONSHIP | download-blob URL --out PATH
```

`post` / `patch` / `delete` exist as library methods but are deliberately wired to no
subcommand — `fdh_api.py:146`: *"used by generated scripts, never by this read CLI"*. That
is the mechanism by which every FDH write goes through a per-task script with its own
`--write` gate, and the doc never says so.

Practical cost: a question like "what samples are linked to assay 123?" is one
`list assays 123 samples` call. `FDH.md` sends the agent to generate, review and run a new
script instead.

**Proposed fix** — insert before "### The shared client":

```markdown
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
```

---

## F5 — MISSING: the auth story omits `FDH_TOKEN`, `--token`, `--user`, and a hard `exit(2)`

**Doc** — `FDH.md:8-9` gives one mechanism: `.env` `FDH_API` = JSON `{ "<name>": "<token>" }`.

**Reality** — `_resolve_token` (`fdh_api.py:172-195`) resolves in this order: `--token` →
`$FDH_TOKEN` → `$FDH_API` JSON. Within the JSON: `--user` selects; a single-entry map
auto-selects; **two or more entries with no `--user` is `sys.exit(2)`** with
`"error: multiple users in FDH_API [...]; pass --user NAME"`. `_load_dotenv`
(`:159-169`) reads `cwd/.env` **then** `<plugin>/.env`, with `setdefault` semantics — so a
plugin-level `.env` cannot override a project-level one, and an already-exported shell var
beats both.

`submit.py` behaves differently: it reads only `FDH_API` (`:1281`) and picks the user
through an interactive prompt (`:1295-1301`).

A lab with two tokens in `FDH_API` — the shape the doc's own example implies is normal —
hits a bare exit 2 with nothing in the reference doc to explain it.

**Proposed fix** — extend the auth bullet:

```markdown
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

---

## F6 — MISSING: the Module 1 flow line hides an in-place workbook overwrite, an unprompted production write, and an unconditional publish

**Doc** — `FDH.md:17`:

> Flow: Config → Assays → Protocols (SOPs) → Metadata rewrite → Sample types →
> Samples → Publish. Resumable via `--resume` / `--step N`; each step writes a CSV to
> `Assets/Output/`.

**Reality**, all read out of `scripts/fdh/submit.py`:

1. **"Metadata rewrite" overwrites the curator's workbook in place, with no backup.**
   `step_metadata_rewrite` (`:1474-1495`) calls
   `replace_anywhere_in_metadata(cfg["workbook"], uploaded_csv, cfg["workbook"])` — input
   path == output path. The implementation reads every sheet with `pd.read_excel` and
   re-emits through `pd.ExcelWriter(engine="xlsxwriter")` (`:617-620`); cell formatting,
   data validation, merged cells, formulas and sheet metadata do not survive that round
   trip. Its confirm defaults **True** (`:1487-1490`). It also writes **no CSV**, so the
   doc's "each step writes a CSV" is false for it.
2. **"Sample types" POSTs to production with no confirmation.** `step_sample_types`
   (`:1549`) calls `_reuse_existing_sample_types(cfg)` and, if that returns `None`, calls
   `create_sample_types_from_workbook(...)` immediately (`:1568-1573`) — one
   `POST /sample_types` per workbook sheet, unprompted. The only prompt on that path is
   the *reuse* offer, shown only when `Assets/Output/sample_types_created.csv` already
   exists and its `sheet_name` set is a subset of the current workbook's sheets
   (`:1512-1547`). A first run, or a run after that CSV is deleted, has no gate.
3. **"Publish" is a batch policy change to public over every study asset, and it runs
   unconditionally.** `step_publish(cfg)` sits at `submit.py:1940`, **outside every
   `if start_step <= N` guard** — a `--step 5` resume reaches it too. It discovers every
   asset linked to the study across `assays, sops, sample_types, samples, data_files,
   models, presentations, publications` (`:1023-1024`) in three passes (`collect_study_assets`,
   `:1027`), then PATCHes each with `policy.access` = `view` or `download` plus a `manage`
   permission for `cfg["project_id"][0]` — **the first selected project only** (`:1654`,
   `publish_resource` `:1107-1146`). Samples go through a 5-worker `ThreadPoolExecutor`
   above 5 items (`:1697-1704`). Its confirm defaults **False** (`:1675-1679`) — the only
   deny-by-default prompt in the tool, and the only thing between a routine run and
   publishing the whole study. The study record itself is deliberately not published
   (`:1636-1637`).

**Proposed fix** — replace `FDH.md:11-21`:

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

---

## Not findings (checked and refuted)

- `FDH.md:19-21`'s workbook-format claims (sheet = Sample Type, column = attribute, `UID`
  required and becomes the title, all-URL columns typed URI, `PROJECT_MAPPING`) — all
  verified true at `submit.py:34-36`, `:700`, `:716`, `:869-870`, `:630-633`, `:77-83`.
- `FDH.md:41-48`'s client method list — all ten verified present
  (`fdh_api.py:101,104,110,121,135,138,147,150,153`; `make_client` `:198`).
- `FDH.md:32`'s "640 KB" for `context/full-fdh-openapi-spec.yaml` — 640,626 bytes.
- `FDH.md:105-107`'s `Assets/Output/session.json` plaintext-token warning — true
  (`submit.py:1225-1230`).
- `ASSAY.md:22`'s "261 rulings became worthless" (`rulings.py:12`), `:25`'s
  "200 ruled rows collapse to 127 keys and 5 disagreed" (`rulings.py:20-21`), `:49-51`'s
  "2,830 rows" (`carryforward.py:9-10`), `:58-59`'s "33 symlinks into `assets/RUN1/`"
  (`_writeguard.py:7-8`), `:72`'s "578 of 26,188" (`resolve_targets.py:11`) — all exact.
- `ASSAY.md:66-67`'s `storeOneRecord` claim is server-side NExtSEEK code, not in this
  repo; corroborated only by `docs/findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md`.
  Not reported — unverifiable here, and the doc's use of it is a hazard warning, which is
  the right register.
- `scripts/fdh/generated/REGISTRY.md` saying `_(none yet)_`: in **this worktree** the
  registry and the directory agree (only `__init__.py` beside it). The drift named in the
  session brief is in the main tree and already fixed there. Reported only as the
  structural consequence of the ignore rule (F3), not as a stale row.
