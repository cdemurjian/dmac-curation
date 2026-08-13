"""Piped into `manage.py shell` on the box to perform the stage 0 write.

Reads a manifest the laptop produced and the operator reviewed. Contains no
logic: every decision was made, reported and approved before this runs, and the
chunking plus the per-row validation live in stage0_apply where tests cover
them. Nothing here recomputes a plan, so what goes into the graph is exactly
what the dry-run report described.

    scp -r ./scripts/assay_hygiene fairdata:/tmp/
    scp <run>/manifest.jsonl fairdata:/tmp/stage0-manifest.jsonl
    ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
    ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
    ssh fairdata 'docker cp /tmp/stage0-manifest.jsonl nextseek:/tmp/'
    ssh fairdata 'docker exec -i nextseek uv run manage.py shell' \
        < scripts/assay_hygiene/driver_stage0.py

Writes Neo4j DERIVED_FROM relationships and nothing else: not MySQL, not
assay_assets, not the legacy relationship type stage 0 was ruled out of on
2026-08-13. It carries no undo path, and no destructive vocabulary at all, by
design: the undo lives in stage0_apply as a documented paste rather than as a
second pipeable file, precisely so it cannot be run by accident. A test asserts
this file stays that way.
"""
import json
import sys

sys.path.insert(0, "/tmp/scripts")

from django.conf import settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from assay_hygiene import stage0_apply  # noqa: E402

MANIFEST = "/tmp/stage0-manifest.jsonl"

with open(MANIFEST) as fh:
    rows = [json.loads(line) for line in fh if line.strip()]
print(f"manifest: {len(rows):,} edges")

nd = settings.NEO4J_DATABASE
driver = GraphDatabase.driver(nd["URI"], auth=nd["AUTH"])
try:
    # try/finally, not a trailing close(): a failed write on a production box
    # must not leave a bolt connection open in the container.
    sent = stage0_apply.apply_manifest(
        driver, nd.get("NAME") or "neo4j", rows,
        progress=lambda done, total: print(f"  {done:,}/{total:,}", flush=True),
    )
finally:
    driver.close()

print(f"done: {sent:,} rows sent")
