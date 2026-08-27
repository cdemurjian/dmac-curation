# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Split a payload into submittable chunks, and verify each against the database.

WHY CHUNKING IS MANDATORY. Gunicorn SIGKILLs at 1200s and this write path has
no transaction, so a crash mid-submission leaves a committed prefix. Chunking
at 2,000 bounds any failure to one chunk. Measured throughput is ~3.4 rows per
second -- the MAX(id)+1 read-then-write cost per row -- so a chunk is roughly
ten minutes.

WHY RECONCILIATION IS A COUNT QUERY. `DBtable.storeOneRecord` sets `status = 1`
and never updates it from the DB call in either write branch, so a failed write
returns success and the feedback workbook prints `successful:` for rows that
never landed. The endpoint's response is a hint. The database is the receipt.

AN OVER-COUNT IS AS BAD AS AN UNDER-COUNT. Primary keys are MAX(id)+1 computed
in Python with no lock; more rows than expected means another writer was active
in the window, and this run's rows may have been overwritten by it.
"""
from __future__ import annotations

import pandas as pd

from .preflight import CHUNK_CAP


class ChunkMismatch(RuntimeError):
    """The database delta is not the number of rows submitted."""


def chunks(sheet: pd.DataFrame, size: int = CHUNK_CAP) -> list[pd.DataFrame]:
    """-> `sheet` split into frames of at most `size` rows."""
    return [sheet.iloc[i:i + size] for i in range(0, len(sheet), size)]


def reconcile(expected: int, before: int, after: int) -> None:
    """Raise unless exactly `expected` rows appeared."""
    actual = after - before
    if actual != expected:
        raise ChunkMismatch(
            f"submitted {expected:,} rows but the database gained "
            f"{actual:,} (MAX(id) {before:,} -> {after:,}). "
            + ("Fewer means rows failed while the endpoint reported success. "
               if actual < expected else
               "More means another writer was active and this run's rows may "
               "have been overwritten. ")
            + "Stop and investigate before the next chunk.")
