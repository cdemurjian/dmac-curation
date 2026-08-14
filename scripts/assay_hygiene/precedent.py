# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage B. Mine the sample-type -> assay -> sample-type map from what exists.

One question per (project, hop, internal assay): when the child is in this
assay, how often is the parent in it too. That is `propagation_rate`, and it is
the evidence a Mode 2 verdict rests on.

Keyed on `internal_assay_id`. dmac.internal_assays is 137 rows under 137
distinct titles and is canonical; seek_production.assays is 458 rows under 291
titles because the same logical assay is instantiated once per study. Keying on
assays.id fragments the evidence; keying on the raw title speaks a different
namespace from DERIVED_FROM.internal_assay_title and leaves findings and edges
unreconcilable.

ONLY `assay_index` lives here so far. `mine_precedent` and its helpers are the
rest of stage B and are still to be written; this module was created early
because `assay_index` is the single definition of "which internal assay is this
seek assay", and a second copy of that definition is a silent-wrong-answer bug
rather than a duplication nit. See vocabulary_evidence.py, which was the second
caller and the reason this file exists now.
"""
from __future__ import annotations

import pandas as pd


def assay_index(assays: pd.DataFrame) -> dict[int, tuple[int, int, str]]:
    """assay_id -> (project_id, internal_assay_id, internal_assay_title).

    17 assay records have no junction row and resolve to no internal id. They
    fall back to their own (assay_id, title), matching neo4j_sync.py:1418-1431
    (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge), so the rule key is never
    null. Dropping them would violate the spec's binding "nothing is dropped
    silently"; leaving the key null would collapse all 17 into a single
    meaningless rule.

    The fallback means the returned internal id is NOT always a
    dmac.internal_assays id: on those 17 it is a seek assays.id, in a different
    id space. That is deliberate and it is what the graph itself does. Every
    consumer must use THIS function rather than filtering on
    `internal_assay_id.notna()`, or two parts of one run will disagree about
    which samples are registered.

    Measured on the real extract 2026-08-14, filtering instead of falling back
    loses 279 of 214,124 sample-assay registrations across 239 samples, and
    drops 82 samples out of the registered population entirely. That is 0.13%
    and it is not harmless. It made `Type: m397` read as 79 of 79 carriers
    registered in one assay at share 1.00, when 13 of them are registered under
    fallback assay 481 and nowhere else. A proposal built on that reading
    contradicts the registration of those 13 samples, and Mode 3 flags all 13.
    Under this function the same term reads 2 candidate assays at share 0.835,
    which is a term you leave alone. See vocabulary_evidence.build_evidence.
    """
    out: dict[int, tuple[int, int, str]] = {}
    for aid, pid, title, iaid, ititle in zip(
        assays.assay_id, assays.project_id, assays.title,
        assays.internal_assay_id, assays.internal_assay_title,
    ):
        if pd.isna(iaid):
            out[int(aid)] = (int(pid), int(aid), str(title))
        else:
            out[int(aid)] = (int(pid), int(iaid), str(ititle))
    return out
