"""Chunk, then count. The database is the only receipt.

DBtable.storeOneRecord sets status = 1 and never updates it from the DB call in
either write branch, so the feedback workbook prints `successful:` for rows
that never wrote. Verification is a count query or it is nothing.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import chunker as K  # noqa: E402


def _sheet(n):
    return pd.DataFrame({"sample_id": range(n), "assay_id": [501] * n})


def test_a_small_sheet_is_one_chunk():
    assert len(K.chunks(_sheet(10))) == 1


def test_chunks_never_exceed_the_cap():
    for part in K.chunks(_sheet(4500)):
        assert len(part) <= K.CHUNK_CAP


def test_chunking_loses_no_rows():
    got = K.chunks(_sheet(4500))
    assert sum(len(p) for p in got) == 4500


def test_chunking_preserves_every_row_exactly_once():
    got = pd.concat(K.chunks(_sheet(4500)))
    assert sorted(got.sample_id.tolist()) == list(range(4500))


def test_an_empty_sheet_produces_no_chunks():
    assert K.chunks(_sheet(0)) == []


def test_reconcile_accepts_an_exact_delta():
    K.reconcile(expected=2000, before=414935, after=416935)


def test_reconcile_refuses_a_short_write():
    with pytest.raises(K.ChunkMismatch, match="1,999"):
        K.reconcile(expected=2000, before=414935, after=416934)


def test_reconcile_refuses_MORE_rows_than_expected():
    """An over-count means another writer was active; the window was not quiet."""
    with pytest.raises(K.ChunkMismatch, match="2,001"):
        K.reconcile(expected=2000, before=414935, after=416936)
