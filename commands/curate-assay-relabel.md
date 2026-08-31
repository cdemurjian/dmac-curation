---
description: Repair DERIVED_FROM assay labels the write invalidated (assay hygiene, final stage)
---

The user wants the graph's edge labels brought back into agreement with
`assay_assets` after a registration write.

## Why this runs at all

A `DERIVED_FROM` edge's assay label is `parent_assays ∩ child_assays`, computed
over `assay_assets`. `/curate-assay-write` adds rows to `assay_assets`. The
labels are **stored properties, not a view**, so every successful write
invalidates the edges touching the written samples and nothing notices.

Measured on production 2026-08-28, after ~25,765 registrations landed:
**416,355 of 802,231 edges were dark that should not have been**, and coverage
was 46%. After the repair, 98%. It took 30 seconds.

This is the closing stage of a run, not an optional extra.

## Step 1 is the backup. There is no step 0.

```bash
RUN=assets/RUN2
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.relabel import back_up_edges
edges = pd.read_parquet(f'$RUN/01-extract/edges.parquet')
print('backed up ->', back_up_edges(edges, Path('$RUN/03-stage0-applied/relabel-before.csv.gz')))
"
```

It writes **every** edge's current label, not just the ones about to change, then
re-reads the file and refuses unless the row count matches. A backup of the
write set alone cannot restore an edge some other writer changed inside the
window, and taking the whole graph costs one pass over a frame already in
memory — about 2.5MB compressed.

`BackupUnverified` means stop. Nothing has been written to the graph.

## Plan, and report the five buckets

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd, json
from pathlib import Path
from assay_hygiene.relabel import plan_relabel, write_set, census, to_rows
RUN = Path('$RUN')
read = lambda n: pd.read_parquet(RUN/'01-extract'/f'{n}.parquet')
plan = plan_relabel(read('edges'), read('samples'), read('membership'),
                    read('assays'), read('sops'))
for bucket, n in census(plan).items():
    print(f'  {bucket:<14} {n:>9,}')
rows = to_rows(write_set(plan), half='after')
out = RUN/'03-stage0-applied'/'relabel-rows.jsonl'
out.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
plan.to_csv(RUN/'03-stage0-applied'/'relabel-manifest.csv.gz', index=False,
            compression='gzip')
print(f'\n  {len(rows):,} rows queued -> {out}')
"
```

Every edge appears in the plan, including the ones nothing will be done to —
`UNCHANGED` and `NO_SHARED` were 385,581 of 802,231 rows on production, and a
plan listing only the writes would report them as absences.

**`WOULD_CLEAR` is reported and never written.** Those are edges that HAVE a
label their endpoints no longer share (82 on production). Blanking them is the
one destructive thing this stage could do, so it is opt-in via
`write_set(plan, allow_clear=True)` and never a consequence of running the
repair. Report the count; do not act on it without a ruling.

## Write

```bash
scp -r ./scripts/assay_hygiene fairdata:/tmp/
scp $RUN/03-stage0-applied/relabel-rows.jsonl fairdata:/tmp/relabel-rows.jsonl
ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
ssh fairdata 'docker cp /tmp/relabel-rows.jsonl nextseek:/tmp/'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' \
    < scripts/assay_hygiene/driver_relabel.py
```

**No credential is read, passed or stored.** The driver runs under
`manage.py shell` and inherits the container's configured `NEO4J_DATABASE`
settings. That is also why the Neo4j HTTP Query API is not used here — it needs
the password on a command line. Never put it in the repo, a script, or a shell
history; if a route ever needs it, it comes from the box's own `.env`.

`cypher-shell` is not an option: its `:param name => value` evaluates the
argument as a Cypher expression, where map keys must be bare identifiers, so
JSON cannot be handed to it. A 44MB param file failed on exactly this.

## Undo — a SET-back, never a DELETE

`stage0_apply.rollback` does `DELETE r`. That is correct for stage 0, where
every manifest row was a newly created edge. **Applied here it would destroy
416,568 relationships that already existed.** Do not reach for it.

The manifest carries the `before_` half for exactly this:

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
import pandas as pd, json
from pathlib import Path
from assay_hygiene.relabel import to_rows
plan = pd.read_csv('$RUN/03-stage0-applied/relabel-manifest.csv.gz')
written = plan[plan.disposition.isin(['GAIN','CHANGE'])]
rows = to_rows(written, half='before')
Path('/tmp/relabel-undo.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
print(f'{len(rows):,} undo rows -> /tmp/relabel-undo.jsonl')
"
```

Then pipe it with the same driver after pointing `ROWS` at the undo file. It is
a documented paste rather than a second pipeable script, deliberately, so it
cannot be run by accident.

## Verify

```bash
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' <<'PY'
from django.conf import settings
from neo4j import GraphDatabase
nd = settings.NEO4J_DATABASE
d = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
try:
    recs, _, _ = d.execute_query(
        "MATCH ()-[r:DERIVED_FROM]->() RETURN count(r) AS edges, "
        "count(r.internal_assay_id) AS with_assay", {},
        database_=nd.get("NAME") or "neo4j")
    print(dict(recs[0]))
finally:
    d.close()
PY
```

Edge count must be **unchanged** — this stage sets properties and creates
nothing. `with_assay` should have risen by exactly the `GAIN` count.

## Known limitation, carried forward deliberately

Only one assay survives per edge: where the endpoints share several, the
minimum `internal_assay_id` wins and the rest are discarded. `n_shared` in the
manifest says which edges had a tiebreak. This reproduces the upload path's own
rule (`neo4j_sync.py`) rather than fixing it — a relabel that disagreed with the
uploader would be a second source of truth. Filed as
BioMicroCenter/NExtSEEK#118.
