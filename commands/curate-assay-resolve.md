---
description: Turn approved pairs into SEEK write targets behind the project gate
---

The user wants the approved rulings turned into a write set.

SEEK assay ids are **per-project**. The same internal assay exists as a
different `assay_id` in every project that runs it, so a registration must land
on the assay belonging to the *sample's own* project.

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.resolve_targets import resolve
RUN = Path('assets/RUN2')
assays  = pd.read_parquet(RUN/'01-extract'/'assays.parquet')
samples = pd.read_parquet(RUN/'01-extract'/'samples.parquet')
rows    = pd.read_csv(RUN/'04-artifacts'/'approved-rows.csv')
manifest, excluded = resolve(rows, assays, samples)
manifest.to_csv(RUN/'04-artifacts'/'MANIFEST.csv', index=False)
excluded.to_csv(RUN/'04-artifacts'/'EXCLUDED.csv', index=False)
print(f'{len(manifest):,} targets, {len(excluded):,} excluded')
if len(excluded):
    print(excluded.reason.value_counts().to_string())
"
```

## Why this is a hard gate

The 2026-08-26 audit found 578 of 26,188 rows targeting another project's
assay — every one produced by a rule that resolved through a lineage neighbour
without checking the neighbour lived in the same project. 159 were repairable,
419 were not.

**This is unrecoverable once written.** The sample joins a project it does not
belong to, and nothing undoes that from the outside.

## Excluded rows are not rejections

Two reasons a row is dropped, and both are authorised registrations with no
correct target rather than judgements against them:

- **sample belongs to no project** — no correct target exists. 374 RUN1 rows.
- **no assay with that internal id in the sample's project** — 45 RUN1 rows.

Report both counts to the operator. A large no-project count is an upstream
data problem worth raising separately, not something to fix here.

`MANIFEST.csv` is what `curate-assay-write` checks the sheet against, and every
row in it is project-checked at build time. Do not hand-edit it: a row that is
in the sheet but not the manifest was never gate-checked, and `write` refuses
the whole submission when it finds one.
