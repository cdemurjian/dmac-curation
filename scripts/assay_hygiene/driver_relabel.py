"""Piped into `manage.py shell` on the box to perform the relabel write.

Reads a row file the laptop produced and the operator reviewed. NOT from
`03-stage0-applied`, which is 0o555 from run creation and is stage 0's record --
this stage writes to `09-relabel`, and the extract it plans from must be a
POST-WRITE one, never the run's own `01-extract`. Contains no
logic: the plan, the diff and the five bucket counts were computed, reported and
approved before this runs, and the chunking lives in `relabel.apply_rows` where
tests cover it. Nothing here recomputes a label, so what reaches the graph is
exactly what the dry-run report described.

    scp -r ./scripts/assay_hygiene fairdata:/tmp/
    scp <run>/09-relabel/relabel-rows.jsonl fairdata:/tmp/relabel-rows.jsonl
    ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
    ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
    ssh fairdata 'docker cp /tmp/relabel-rows.jsonl nextseek:/tmp/'
    ssh fairdata 'docker exec -i nextseek uv run manage.py shell' \
        < scripts/assay_hygiene/driver_relabel.py

NO CREDENTIAL IS READ, PASSED OR STORED HERE. It runs under `manage.py shell`,
so it inherits the configured NEO4J_DATABASE settings from the environment the
container already has. That is also why the HTTP Query API is not used: that
route needs the password on a command line.

Writes three properties on existing Neo4j DERIVED_FROM relationships and nothing
else: not MySQL, not assay_assets, not the node set. It carries no undo path and
no destructive vocabulary at all, by design -- the undo lives in `relabel` as a
documented paste rather than as a second pipeable file, precisely so it cannot
be run by accident. A test asserts this file stays that way.
"""
import json
import sys

sys.path.insert(0, "/tmp/scripts")

from django.conf import settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from assay_hygiene import relabel  # noqa: E402

ROWS = "/tmp/relabel-rows.jsonl"

with open(ROWS) as fh:
    rows = [json.loads(line) for line in fh if line.strip()]
print(f"rows: {len(rows):,} edges to relabel")

nd = settings.NEO4J_DATABASE
driver = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
try:
    # try/finally, not a trailing close(): a failed write on a production box
    # must not leave a bolt connection open in the container.
    sent = relabel.apply_rows(
        driver, nd.get("NAME") or "neo4j", rows,
        progress=lambda done, total: print(f"  {done:,}/{total:,}", flush=True),
    )
finally:
    driver.close()

print(f"done: {sent:,} rows sent")
