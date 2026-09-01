---
description: Write registrations to production, behind eight refusals
---

The user wants this run's registrations written to production.

**This is the only command that touches production.** It writes nothing without
`--confirm`.

## The endpoint that will replace this — NOT YET

`POST /nextseek_api/assay-registrations/` is the purpose-built batch registration
endpoint. It is **additive** — it writes through `batch_insert_assay_assets`, which
contains no DELETE and has a test asserting so — which is the exact property this
sheet was chosen for.

**It is not deployed on production.** Verified 2026-09-01:
`docker exec nextseek ls /app/nextseek_api/assay_registration/` returns 0 there;
production runs a commit predating the merge. The dev box has it.

So **keep using the sheet for production writes.** `assay_hygiene.registration_api`
is the client, built and testable against dev now, and `check_target` refuses a
production base URL outright rather than letting a 404 be misread as "nothing to do".

**Before switching, all four must hold:**

1. production rebuilt and `ls /app/nextseek_api/assay_registration/` non-empty
2. re-verified against production, not just dev
3. the **asynchronous** path built and exercised — at or above 5,000 rows the
   endpoint answers 202 with a durable job. It was verified at 1,000 rows on the
   synchronous path only, and a full ~26,000-row run crosses that threshold
4. rollback reworked: capture the per-row `assay_assets_id` from the response
   (**not** a `MAX(id)` range — a range deletes another writer's rows if one
   interleaves) and treat the graph recompute as step 2, not an afterthought.
   See `rollback_plan` and `/curate-assay-relabel`; those should become one
   procedure

The data gates do **not** move. `registration_api.build_payload` goes through
`update_assay_sheet.build`, so a payload refuses exactly what a sheet refuses —
including a sample whose uid production holds more than once, which is a property
of the data and not of the transport.

The account needs `is_superuser=1`, not merely SEEK admin — the same gate the
attributes API uses.

## The mechanism, and why this one

An `UPDATE_ASSAY` sheet posted to `/seek/sampleupload/`, one row per
`(sample, assay)` edge, **both Current columns blank**. Chosen because it is
structurally incapable of deleting: with the Current pair unparseable, `id = -1`
and the delete branch behind `if id>0` is unreachable.

Measured against the alternatives for the same 25,769 rows: the API route put
202,016 existing memberships at risk, batch-upload 25,912, this route **zero**.
Batch-upload additionally rewrites `samples.title` to the UID string and resets
`policies.access_type` by default.

Every registration writes `direction = 0`. Nothing in `seek/` reads the column,
and our rows assert *membership*; lineage direction is already recorded in the
graph by stage 0, and asserting it again here would be a second copy of a fact,
free to disagree with the first.

Idempotency is application-level, not a database constraint: there is no UNIQUE
index on `(assay_id, asset_id, asset_type)`, and `storeOneRecord` reads before
writing via `__verifyUniqueConstraint`. Worth stating because it would vanish
silently if that code path changed and nothing in the schema would catch it.

## Capture the rollback handle first

```sql
SELECT MAX(id) FROM seek_production.assay_assets;
```

Record it in the lockfile. The row-level undo is
`DELETE FROM seek_production.assay_assets WHERE id > <handle>;` — no FKs, no
triggers, monotonic id.

**That DELETE is only half an undo once `/curate-assay-relabel` has run.** The
relabel rewrites `DERIVED_FROM` labels from post-write `assay_assets` (RUN2:
1,673 edges). Deleting the rows afterwards leaves those labels asserting
memberships that no longer exist, and nothing reports it.

Worse, the relabel command **will not repair it at its defaults**: those edges
become `WOULD_CLEAR`, which `write_set` excludes unless `allow_clear=True`. So a
rollback after a relabel needs a deliberate `allow_clear` pass, ruled on
explicitly. Roll back BEFORE relabelling if you can; if you cannot, treat the
graph repair as a second, ruled step rather than an afterthought.

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.runstate import read, update
w = read(Path('assets'))['write'] | {'rollback_id': <handle>}
update(Path('assets'), write=w)
"
```

## Verify the backup, do not trust its exit code

Non-zero size **and** a `Dump completed` trailer. A `mysqldump` exited 0 having
written a 0-byte file on 2026-08-27; only an `ls` caught it.

## Build the sheet

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow --with openpyxl \
  python -m assay_hygiene.update_assay_sheet
```

`update_assay_sheet.build` takes the run's `MANIFEST.csv` and its extract's
`samples.parquet` and emits the five headers the endpoint requires, with both
Current columns blank and `New Assay Direction` 0. It refuses an ungated row, a
duplicated edge, a non-integer assay target, a sample with no uid, and a sample
whose uid production holds more than once.

**That last one refuses by default and you will hit it.** Both RUN1 and RUN2
carried four. Dropping them is explicit and logged:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow --with openpyxl python -c "
from assay_hygiene.update_assay_sheet import main
main('assets/RUN<n>', drop_ambiguous=True)"
```

It writes `UPDATE_ASSAY.xlsx` and `SUBMIT-MANIFEST.csv` side by side, so the pair
travels to the box together.

**`SUBMIT-MANIFEST.csv` is not `04-artifacts/MANIFEST.csv`.** Two different files:
the submitter's is `uid, assay_id, project_ok` (the workbook carries no sample_id);
`resolve`'s is `sample_id, internal_assay_id, write_target_seek_assay_id,
project_ok` and is what `preflight`'s subset check reads. Passing one where the
other is wanted is a `KeyError` in either direction.

**The New pair is `(New Assay ID, New Assay Direction)` — not `sample:assay`.**
`preflight` checks a pair's shape and never its meaning, so a sheet built to the
wrong reading passes all eight refusals. Read the module docstring.

## The uid-uniqueness gate — the one that cost a chunk

`_retrieveSampleByUID` (`seek/sample/core.py:397-408`) returns a record only when
**exactly one** row matches. A uuid held by two samples resolves to `None`
indistinguishably from a missing one, and `getSampleID`'s `None` then reaches
`if sample_id>0:` and raises `TypeError` — **500ing the whole batch** with every
earlier row already committed and no feedback file written.

That is not hypothetical. It killed RUN1's chunk 06 at row 1221, after 1,220
rows had landed. The preflight that missed it asked *"does this uid exist"* with
a JOIN; the code asks *"does exactly one row have it"*. They agree everywhere
except on duplicates — the only case that hurts.

Production carries duplicate-uuid samples and **`samples.uuid` has no unique
constraint**, so this is standing, not transient. `update_assay_sheet.build`
refuses them at build time; `submit_update_assay` re-checks **live** against the
database before each chunk. Do not disable either.

Registrations for a duplicated sample cannot be written at all until someone
deduplicates those samples — which means choosing which of two identical rows
survives. That is not a decision to fold into a run.

## Prove it on 200 rows first

RUN1 did this and it is the single fact everything else rested on. Pick a slice
covering several assays, submit it, and check the per-assay deltas.

**The canary is an assay that already holds a lot.** RUN1 used one with 48,440
members expected to gain exactly 1: if the endpoint were complete-list rather
than per-edge, that assay would collapse to a single row and you would see it
immediately. It came back 48,441.

```sql
SELECT assay_id, COUNT(*) AS n FROM assay_assets
 WHERE asset_type='Sample' AND assay_id IN (<the assays your slice touches>)
 GROUP BY assay_id ORDER BY assay_id;
```

## Preflight — all eight, before any row

```bash
RUN=assets/RUN<n>
PYTHONPATH=scripts uv run --with pandas --with pyarrow --with openpyxl python -c "
import pandas as pd
from assay_hygiene import update_assay_sheet as U, preflight as P
sheet   = pd.read_excel('assay-hygiene/UPDATE_ASSAY.xlsx', sheet_name=U.SHEET_NAME, dtype=object)
samples = pd.read_parquet('$RUN/01-extract/samples.parquet', columns=['sample_id','uuid'])
sid_of  = dict(zip(samples.uuid.astype(str), samples.sample_id.astype(int)))
manifest = pd.read_csv('$RUN/04-artifacts/MANIFEST.csv')   # resolve's, NOT SUBMIT-MANIFEST
P.check(U.for_preflight(sheet, sid_of), manifest, [U.SHEET_NAME],
        {'size': <backup bytes>, 'trailer_ok': True}, <rollback handle>)
print('preflight clean')
"
```

It refuses: a Current pair of two ints; an unparseable New pair; a blank or
non-string uid; a sheet named `UPDATE` anywhere in the workbook; any row absent
from the gate-checked manifest; no captured rollback handle; a backup that is
absent **or unverified**; a chunk above 2,000 rows.

Each is a live failure mode, not a hypothesis. A blank uid makes `getSampleID`
return `None`, and `None > 0` raises — a 500 mid-chunk, leaving a committed
prefix, because this path has no transaction.

## Submit

`scripts/assay_hygiene/submit_update_assay.py` is the submitter that performed
RUN1's write. **Dry run unless `--confirm`.** It must run ON THE BOX — it posts
to nginx at `127.0.0.1:8000` — so copy it up with the workbook and the manifest.

**Stage into a FRESH directory on the box**, never one holding an earlier run's
sheets — the runner globs `UPDATE_ASSAY-*.xlsx` and will pick up whatever it
finds. A dated directory (`~/ah_write_<YYYYMMDD>/`) is the cheap way.

```bash
scp UPDATE_ASSAY.xlsx SUBMIT-MANIFEST.csv \
    scripts/assay_hygiene/submit_update_assay.py fairdata:~/ah_write_<date>/

uv run --no-project --with requests --with openpyxl python submit_update_assay.py \
    --sheet UPDATE_ASSAY.xlsx --manifest SUBMIT-MANIFEST.csv \
    --username <seek-username> --max-rows <rows+buffer>
                                          # add --confirm to actually send
```

**`--max-rows` defaults to 250 and the example above will refuse without it.**
That is the point of the default: a full sheet cannot be sent by reflex. Raise
it deliberately, per chunk, to just above that chunk's row count.

Password comes from `$NEXTSEEK_PASSWORD` or a prompt — **never argv**, which is
visible in `ps` to every user on the box. Auth is POST-form, not a Django
session: `getSeekLogin` reads username and password straight off the POST.

`--max-rows` defaults to 250 so a full sheet cannot be sent by reflex. Raise it
deliberately per chunk.

## Chunk, submit, count

2,000 rows per submission. Gunicorn SIGKILLs at 1200s and this path has **no
transaction**, so a crash leaves a committed prefix. Measured throughput is
~3.4 rows/second, so roughly ten minutes per chunk.

**Drive it from a loop that halts on the first mismatch**, rather than by hand.
RUN1's runner asserted the database count against a running total after every
chunk and exited on any disagreement. Two properties earned in blood:

- **Assert the starting count before the first submit.** On resume, hold the
  already-written total in a variable and halt if the database disagrees — a
  resumed run that mis-counts its baseline mis-attributes every later chunk.
- **Completed sheets leave the glob** (rename to `DONE-*.bak`). A re-submitted
  chunk is not idempotent at the count level even though it is at the row level.

When a chunk halts, the diagnosis is a fresh 500 in the log:

```bash
docker exec nextseek sh -c 'grep -n "Internal Server Error: /seek/sampleupload" /app/logs/django.log | tail -2'
```

After each chunk:

```sql
SELECT COUNT(*) FROM seek_production.assay_assets WHERE id > <handle>;
```

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
from assay_hygiene.chunker import reconcile
reconcile(expected=<rows submitted>, before=<count before>, after=<count after>)
print('chunk reconciled')
"
```

**The database is the only receipt.** `DBtable.storeOneRecord` sets `status = 1`
and never updates it from the DB call in either write branch, so the feedback
workbook prints `successful:` for rows that never wrote.

`reconcile` refuses an over-count as well as a short write: more rows than
expected means another writer was active and this run's rows may have been
overwritten.

## A quiet window is required

Primary keys are `MAX(id)+1` computed in Python with no lock. A concurrent
insert makes Django's explicit-pk `save()` perform UPDATE-then-INSERT and
silently overwrite the other writer's row, with both callers told they
succeeded. `nextseek_api`'s batch-upload path writes the same table. Confirm no
writes in the preceding window before starting, and do not run two runs at once
— `runstate.create` refuses that for this reason.
