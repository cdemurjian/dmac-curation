# Assay hygiene mode

House-scoped, not project-scoped: one extract, all projects, no PI. It finds
samples that should be registered against an internal assay and are not, puts
every proposal in front of a human, and writes the approved ones to production.

## The run model

Runs are numbered at `assets/RUN<n>/` and hold eight protected tiers, plus two
the relabel stage adds:

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
    07-process/           WRITABLE    -- the only ORIGINAL tier not chmodded
    08-extract-post-write/ WRITABLE   -- the post-write extract relabel plans from
    09-relabel/           WRITABLE    -- relabel's backup, manifest and row file

`08` and `09` exist because `00`-`06` are chmod 0o555 from run creation and the
relabel stage runs AFTER them. Its inputs and outputs are not part of the
immutable baseline the run was detected from, and writing them into
`03-stage0-applied` — which an earlier draft of the command did — fails outright.
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

## The ruling store

Judgement lives at `assets/rulings/`, **outside** any run, keyed on
`(sample_type, internal_assay_id, action)` with the cohort string kept
alongside as provenance.

This is the structural change that makes reuse possible. RUN1 filed verdicts
under `lab|sample_type|parent_types|assay_title|field|value`; four of those six
move with the extract, so a new run matched almost none of them and 261 rulings
became worthless without any judgement having changed.

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

## Commands

| command | does | writes |
|---|---|---|
| `curate-assay-init` | open a run, prove the store survives, chmod tiers | run dir |
| `curate-assay-vocabulary` | unresolved terms → evidence → agent proposals | `vocabulary-proposed.csv` |
| `curate-assay-detect` | evidence + detection into the run's own out_dir | run artifacts |
| `curate-assay-review` | serve surfaces, ingest rulings, auto-backup | ruling store |
| `curate-assay-resolve` | internal → SEEK targets behind the project gate | run artifacts |
| `curate-assay-write` | build the sheet, preflight (8 refusals), submit, reconcile against the DB | **production** |
| `curate-assay-relabel` | repair the DERIVED_FROM labels the write invalidated | **the graph** |
| `curate-assay-status` | read the lockfile, report position | nothing |
| `curate-assay-backup` | dated, verified tarball of the store | backup dir |

**`relabel` is the closing stage of a run, not an optional extra.** A
`DERIVED_FROM` edge's assay label is `parent_assays ∩ child_assays` computed over
`assay_assets`, and it is a STORED PROPERTY, not a view. Every successful write
therefore invalidates the edges touching the written samples and nothing
notices. A run that stops at `write` leaves the graph disagreeing with the
database it was derived from. Measured on RUN2: the 740-row write left 1,641
edges dark that should not have been.

## What is not built yet

The command table is a design, not a closed loop. **One joint has no code**;
the other two are closed as of 2026-08-31, when RUN2 ran the whole chain
end to end for the first time. Check this list before planning a run.

**Review → the ruling store — HALF CLOSED.** The sheet now emits the column
`ingest` joins on. `review.EXPORT_COLUMNS` leads with `cohort_key`
(`review.py:130`), the page's export writes it from the `data-k` it already
carries, and `review_mode2.to_csv` emits it as column 1 (`review_mode2.py:485`)
— all from `review.cohort_key` (`review.py:606`), the one definition. A sheet
straight out of `main` ingests with no hand edit, and `load_presets` still reads
a sheet exported before the column existed.

What is still yours to build is `ingest`'s **second** argument: the
`{cohort_key: pair_key}` map, `cohort_key → (sample_type, internal_assay_id,
action)`. Resolve the assay title through `migrate_rulings.title_index`, which
refuses an ambiguous title rather than picking. Never re-derive the key itself.

**Review → resolve.** `curate-assay-resolve` reads
`$RUN/04-artifacts/approved-rows.csv` (`commands/curate-assay-resolve.md:19`).
**Nothing writes it.** Expanding the pair-keyed store into a row-level
`(sample_id, internal_assay_id)` frame is manual work today.

**Resolve → write — HALF CLOSED.** `update_assay_sheet` now builds the workbook
from a run's `MANIFEST.csv` and its own extract:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow --with openpyxl \
  python -m assay_hygiene.update_assay_sheet
```

**Read that module's docstring before touching the sheet.** The five headers are
exact (`seek/sample/upload.py:818`) and a missing one fails the whole file with
error 701, not a row. And the Current/New "pairs" `preflight` names are COLUMN
pairs — `(Assay ID, Assay Direction)` — not `sample:assay`. The sample reaches
the endpoint only through `getSampleID(dici['Sample UID'])`. A sheet built to the
other reading passes all eight refusals and registers every row against the
wrong assay.

**Resolve → write, the submitter — CLOSED.** `submit_update_assay.py` is the
submitter that performed RUN1's 25,765-row write, recovered from that session
and vendored unchanged in logic. Dry run unless `--confirm`; runs on the box;
carries its own delete-safety, project-consistency and **live uid-uniqueness**
gates. `--confirm` is real here, whatever `curate-assay-write.md` says about the
mode's other commands.

Still open: `preflight.check` and `chunker.reconcile` remain a library the
operator must call on either side of a submission; nothing enforces that either
ran, and there is no CLI for the mode as a whole.

## Resuming a run that was closed early

`close` releases the lock, and `create` allocates a NEW run number and refuses
while anything is open — so for a while there was no way back into a run that
had been closed before it finished, and resuming meant editing the lockfile by
hand. `runstate.reopen(root, run)` is that path:

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.runstate import reopen
print(reopen(Path('assets'), run=2))"
```

It takes the run number as an argument rather than reopening whatever the
lockfile holds — reopening a run you have misidentified re-submits its rows. It
re-stamps the pid, does not touch `step`, refuses while a different run is open,
and is a no-op on a run already open.

## Production defects this mode has hit, and has not fixed

**`samples.uuid` has no unique constraint, and duplicate-uuid samples exist.**
Created by an upload that inserted each row twice. A duplicated uuid resolves to
`None` in `_retrieveSampleByUID` exactly as a missing one does, which 500s a
whole submission mid-write. RUN1 lost chunk 06 to four of them; RUN2's manifest
carries four as well. Registrations for those samples are unwritable until
someone deduplicates them, which means choosing which of two identical rows
survives — not a decision to fold into a run.

**The same missing-constraint pattern** is why `assay_assets` idempotency rests
on `storeOneRecord`'s application-level read-before-write rather than on the
database: there is no unique index on `(assay_id, asset_id, asset_type)` either.

**A sample in no project has no correct registration target.** 242 of RUN2's
1,043 approved rows (23%) belong to no project at all, against RUN1's 1.4%. That
is an upstream data problem; `resolve` excludes them rather than papering over
it.

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

## Four things that will bite

**Never run a driver on default paths.** `run_evidence` and `run_detect`
default `out_dir` to `assay-hygiene/`, which is 33 symlinks into
`assets/RUN1/`. `_writeguard` refuses it, but pass the run directory anyway.

**Nothing regenerates a human ruling.** The store is gitignored and its only
protection is a verified tarball outside the working tree. `git clean -xdf` lists
`assets/` for removal. A lost machine is a lost campaign — the accepted cost of
keeping identifiers out of a public repository.

**The database is the only receipt.** `storeOneRecord` sets `status = 1` and
never updates it from the DB call, so the endpoint's feedback workbook reports
success for rows that never wrote. Verification is a count query.

**SEEK assay ids are per-project.** A registration landing on another project's
assay puts the sample into a project it does not belong to, and nothing undoes
that. The 2026-08-26 audit found 578 of 26,188 rows in that state.

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
