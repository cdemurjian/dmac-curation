"""Piped into `manage.py shell` on the box. Kept short on purpose.

extract.py uses a relative import, so piping IT into the shell executes it
without package context and the import raises. And nesting the invocation
inside `ssh ... bash -lc "python -c \\"...\\""` will not survive ssh's arg
joining plus the remote shell's re-parse. Copy the package, pipe this.

    scp -r ./scripts/assay_hygiene fairdata:/tmp/
    ssh fairdata 'docker exec nextseek mkdir -p /tmp/scripts'
    ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
    ssh fairdata 'docker exec -i nextseek uv run manage.py shell' \
        < scripts/assay_hygiene/driver_extract.py

Read-only: it runs SELECTs and read-only Cypher and writes parquet to
/tmp inside the container. Nothing here touches MySQL, Neo4j or the API.
"""
import sys

sys.path.insert(0, "/tmp/scripts")
from assay_hygiene import extract  # noqa: E402

extract.main()
