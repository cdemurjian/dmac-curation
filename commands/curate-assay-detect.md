---
description: Run the evidence and detection passes into this run's own directory
---

The user wants this run's proposals generated.

## Never write to the default paths

`run_evidence` and `run_detect` default `out_dir` to `assay-hygiene/`, which is
33 symlinks into `assets/RUN1/`. A default-path run follows those links and
overwrites the baseline every measurement is compared against — 27 of 33
artifacts are reachable that way. `assay_hygiene._writeguard` now refuses it
outright, but pass the run's own directory rather than relying on the refusal:

```bash
RUN=assets/RUN2
chmod -R u+w $RUN/04-artifacts
cp assets/RUN1/04-artifacts/vocabulary-curator.csv $RUN/04-artifacts/ 2>/dev/null || true
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_detect   $RUN/01-extract $RUN/04-artifacts
```

`run_detect` does **not** call `run_evidence`. Both are needed, in that order;
`gate` and `classify` read `claims.parquet` and `vocabulary.csv` from the output
directory and exit 2 naming what to run first rather than raising a bare
`FileNotFoundError`.

Re-protect the tier when the run finishes writing to it:

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.protect_run import protect, verify
protect(Path('$RUN'), ['04-artifacts'])
print('unprotected:', verify(Path('$RUN'), ['04-artifacts']))
"
```

## Sort the cohorts against previous judgement

Every cohort goes into exactly one of three buckets:

- **already ruled** — the pair matches and this cohort is no wider than the one
  ruled against. Carried.
- **ruled in a narrower context** — the pair matches but this cohort covers
  rows the original did not. **Surfaced for re-confirmation, never applied.**
- **never seen** — goes to the operator.

The middle bucket is the trap this mode exists to close. In RUN1, 2,830 rows
shared a cohort key with an approved cohort but sat below the precedent floor
the operator's sheet was built at, so he never saw them. A carry-forward
matching on the pair alone registers every one of them silently.

An unknown ruled width counts as **widened**, not carried: absence of evidence
that a ruling covered these rows is not evidence that it did.

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from pathlib import Path
from assay_hygiene.carryforward import split, CARRIED, WIDENED, UNSEEN
from assay_hygiene.rulings import load
store = load(Path('assets/rulings'))
cohorts = []      # build from this run's detect output
widths  = {}      # pair key -> rows the ruling was made against
got = split(cohorts, store, widths)
for bucket in (CARRIED, WIDENED, UNSEEN):
    print(f'{bucket:32} {len(got[bucket]):>6,}')
"
```

Report the three counts and record them in the lockfile:

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.runstate import update
update(Path('assets'), step='detect', carried_pairs=<n>, carried_from_run=1)
"
```
