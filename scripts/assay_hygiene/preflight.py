# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""The eight refusals, checked before a single row reaches production.

EVERY ONE IS A LIVE FAILURE MODE of /seek/sampleupload/, not a hypothesis:

  1. a Current pair of two ints is the SOLE combination reaching
     deleteOneRecord (seek/dbtable_assay_assets.py:171)
  2. an unparseable New pair silently drops the registration and reports success
  3. a blank UID makes getSampleID return None, and `None > 0` raises -- a 500
     mid-run, leaving a committed prefix, because this path has no transaction
  4. a sheet named UPDATE hijacks dispatch into the metadata-update path
     (seek/dbtable_sample.py:1663 is tested first)
  5. a row absent from the gate-checked manifest was never project-checked
  6. no rollback handle means MAX(id) was never captured and the run cannot
     be undone
  7. an unverified backup is not a backup -- non-zero size AND a trailer,
     because a mysqldump exited 0 having written 0 bytes
  8. a chunk above the cap meets gunicorn's 1200s SIGKILL with no transaction

ORDER MATTERS ONLY IN THAT THE FIRST FAILURE IS REPORTED. All eight are
independent; none is a subset of another.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .resolve_targets import CrossProjectTarget, assert_subset

CHUNK_CAP = 2000
FORBIDDEN_SHEET = "UPDATE"


class PreflightRefused(RuntimeError):
    """A condition that would corrupt or silently drop production data."""


def _pair_is_two_ints(value) -> bool:
    parts = str(value).split(":")
    return len(parts) == 2 and all(p.strip().isdigit() for p in parts)


def check(sheet: pd.DataFrame, manifest: pd.DataFrame,
          sheet_names: Iterable[str], backup: dict,
          rollback_id: int | None) -> None:
    """Raise on the first refusal that applies. Returns None when safe."""
    names = list(sheet_names)
    if any(n.strip() == FORBIDDEN_SHEET for n in names):
        raise PreflightRefused(
            f"a sheet named {FORBIDDEN_SHEET!r} is present in {names}. It "
            f"hijacks dispatch into the metadata-update path, which is tested "
            f"before the assay path and would rewrite sample metadata.")

    if len(sheet) > CHUNK_CAP:
        raise PreflightRefused(
            f"{len(sheet):,} rows exceeds the {CHUNK_CAP} cap. Gunicorn "
            f"SIGKILLs at 1200s and this path has no transaction, so an "
            f"over-long submission leaves a committed prefix nobody can bound.")

    bad_current = [r for r in sheet.itertuples()
                   if _pair_is_two_ints(getattr(r, "current_pair", ""))]
    if bad_current:
        raise PreflightRefused(
            f"{len(bad_current)} row(s) carry a Current pair that parses as "
            f"two ints. That is the sole combination reaching the delete "
            f"branch; every Current column must be blank so id stays -1.")

    bad_new = [r for r in sheet.itertuples()
               if not _pair_is_two_ints(getattr(r, "new_pair", ""))]
    if bad_new:
        raise PreflightRefused(
            f"{len(bad_new)} row(s) carry an unparseable New pair. The "
            f"endpoint drops those registrations silently and still reports "
            f"success.")

    bad_uid = [r for r in sheet.itertuples()
               if not isinstance(getattr(r, "uid", None), str)
               or not str(getattr(r, "uid")).strip()]
    if bad_uid:
        raise PreflightRefused(
            f"{len(bad_uid)} row(s) carry a blank or non-string uid. "
            f"getSampleID returns None, `None > 0` raises, and the run 500s "
            f"mid-chunk leaving a committed prefix.")

    try:
        assert_subset(sheet, manifest)
    except CrossProjectTarget as exc:
        raise PreflightRefused(f"manifest check failed: {exc}") from exc

    if rollback_id is None:
        raise PreflightRefused(
            "no rollback handle captured. MAX(id) must be recorded before the "
            "first chunk, or the run cannot be undone.")

    if not backup.get("size") or not backup.get("trailer_ok"):
        raise PreflightRefused(
            f"backup unverified: size={backup.get('size')!r} "
            f"trailer_ok={backup.get('trailer_ok')!r}. Both are required -- a "
            f"mysqldump exited 0 having written 0 bytes on 2026-08-27.")
