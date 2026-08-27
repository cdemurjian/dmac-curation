---
description: Write registrations to production, behind eight refusals
---

The user wants this run's registrations written to production.

**This is the only command that touches production.** It writes nothing without
`--confirm`.

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

Record it in the lockfile. Undo for the whole run is
`DELETE FROM seek_production.assay_assets WHERE id > <handle>;` — no FKs, no
triggers, monotonic id.

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

## Preflight — all eight, before any row

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from assay_hygiene.preflight import check
check(sheet, manifest, sheet_names, backup, rollback_id)
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

## Chunk, submit, count

2,000 rows per submission. Gunicorn SIGKILLs at 1200s and this path has **no
transaction**, so a crash leaves a committed prefix. Measured throughput is
~3.4 rows/second, so roughly ten minutes per chunk.

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
