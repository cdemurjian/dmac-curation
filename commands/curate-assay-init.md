---
description: Open a numbered assay-hygiene run and prove the ruling store survives
---

The user wants a new assay-hygiene run.

This mode is **house-scoped**: one extract, all projects, no PI. Every path
below is relative to the directory holding `scripts/` and `assets/`.

## Before anything else: the ruling store

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from pathlib import Path
from assay_hygiene.init_run import require_store
require_store(Path('assets/rulings'), Path('~/backups').expanduser())
print('ruling store present')
"
```

If that raises `MissingRulingStore`, **stop**. Nothing regenerates a human
ruling — not compute, not a re-run. Restore the newest tarball it names:

```bash
tar -xzf ~/backups/rulings-<newest>.tar.gz -C assets/
```

Only if this is genuinely the first run, create the store by migrating a
completed run:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.init_run import migrate_into_store
a = pd.read_parquet('assets/RUN1/01-extract/assays.parquet')
got = migrate_into_store(Path('assets/RUN1'), a, Path('assets/rulings'))
print('store before:', got['store_before'])
print('keys added  :', got['written'])
print('store total :', got['store_total'])
print('conflicts   :', len(got['conflicts']))
for c in got['conflicts']: print('  ', c['key'], c['verdicts'])
"
```

Migration **merges into** the store; it does not replace it. If `store_before`
is non-zero you are adding to existing judgement, and anything already there
that this run does not re-derive -- the operator's resolutions of earlier
conflicts, above all -- is preserved. If a migrated verdict contradicts one
already stored, `save` raises `ConflictingRulings` rather than picking a side.

**Conflicting keys are excluded and reported, never resolved.** A key ruled two
ways means the operator's judgement rested on something the pair key discards —
the lab, the parent types, or the specific term. Put those pairs back to the
operator; do not pick a verdict by recency, majority or source precedence.

## Open the run

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from pathlib import Path
from assay_hygiene.init_run import create_run, next_run_number
from assay_hygiene.runstate import create
n = next_run_number(Path('assets'))
run = create_run(Path('assets'), n)
create(Path('assets'), run=n, extract_sha='<sha of the extract you pulled>')
print('opened', run)
"
```

`create` refuses while another run is open. That is a safety property: two
concurrent write phases can silently overwrite each other's rows, because
primary keys are `MAX(id)+1` computed in Python with no lock.

Tiers `00`–`06` are made read-only at creation. `07-process` stays writable
because it holds the workspace a later run appends to.

## One decision this run must make consciously

`tests/test_assay_hygiene_rulings.py:332` is `xfail(strict=True)` and names 13
cohorts the operator rejected that a primary surface still proposes. If the new
extract no longer contains them the assertion passes, strict mode reports XPASS
and the suite goes red for a reason unrelated to any fix. Decide whether that
measurement still applies to this run, and record the decision in
`07-process/`. Do not silently flip the marker.
