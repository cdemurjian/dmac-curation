---
description: Serve the review surfaces, ingest the operator's rulings, back up
---

The user wants to rule on this run's cohorts.

Two artifacts per surface. The **HTML** carries the context a cell cannot hold —
the neighbour's own registrations, the precedent table, the gate outcome and its
reason. The **CSV** carries one row per cohort with a blank `ruling` column.

The operator edits the CSV and hands it back. Judgement therefore lives in a
diffable, greppable file a later reader can audit.

`assay_hygiene.review_mode2` already builds both for Mode 2 — `build_blocks`,
`to_csv`, and the `REVIEW_NAME` / `CSV_NAME` constants. Use them. Do not write a
second surface builder, and above all do not construct the cohort key locally:
`assay_hygiene.review.cohort_key` is the one definition, and a second one is a
single edit away from disagreeing with the first.

## Ingest

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.ingest import ingest
from assay_hygiene.rulings import load, save
from assay_hygiene.store_backup import back_up

STORE = Path('assets/rulings')
edited  = pd.read_csv('<the file the operator edited>')
cohorts = {}   # cohort_key -> pair key, exactly as the review surface emitted
found = ingest(edited, cohorts, ruled_on='<today>')

existing = load(STORE)
print('new rulings:', len(found))
save(STORE, list(existing.values()) + found)
print('store now  :', len(load(STORE)))
print('backed up  :', back_up(STORE, Path('~/backups').expanduser(), '<stamp>'))
"
```

`save` rewrites the whole store, so pass the existing rulings alongside the new
ones or the file is replaced by just this batch.

**Backup is part of ingest, not a separate step you remember.** The store is
gitignored, so a tarball outside the working tree is its only protection —
`git clean -xdf` lists `assets/` for removal.

## What the ingest refuses, and why it refuses the whole file

- a row matching no cohort in this run
- a verdict outside `APPROVE` / `REJECT` / `WRONG_ASSAY` / `UNSURE`
- one cohort ruled two different ways in the same file
- a sheet with no `cohort_key` column

Refusal is whole-file rather than per-row. A file with one unmatched row was
built against a different cohort set, and ingesting the rows that happen to
match would file a subset of the operator's judgement while reporting success.

A blank `ruling` is skipped, not defaulted: an unruled row is not a rejection.

## Conflicts

If `save` raises `ConflictingRulings`, one pair key carries two different
verdicts. Do not resolve it — not by recency, not by majority, not by source
precedence. Put the pair to the operator with both cohort strings as context and
let them rule it directly.
