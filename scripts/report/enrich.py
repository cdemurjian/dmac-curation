# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Additive enrichment. Never required, never overwrites.

If a UID happens to resolve in NExtSEEK, fetch and merge it. If it does not,
the run proceeds on whatever the input already carried. Enrichment is a bonus,
not a precondition - which is what lets report mode run on a curated Arm{X}.xlsx
before anything has been uploaded.

Merge rule is LEAF-WINS: a value already present on a sample is never replaced.
The curator's sheet is the truth; the database is the supplement.
"""
from __future__ import annotations

from report.adapters import NormalizedInput, NormalizedSample


def merge_leaf_wins(base: NormalizedInput, extra: NormalizedInput) -> NormalizedInput:
    """Merge `extra` into `base` without overwriting anything `base` has."""
    by_uid: dict[str, NormalizedSample] = {}
    order: list[str] = []
    for sample in base.samples:
        by_uid[sample.uid] = NormalizedSample(
            sample_type=sample.sample_type, uid=sample.uid,
            metadata=dict(sample.metadata), parent=sample.parent)
        order.append(sample.uid)

    for sample in extra.samples:
        existing = by_uid.get(sample.uid)
        if existing is None:
            by_uid[sample.uid] = NormalizedSample(
                sample_type=sample.sample_type, uid=sample.uid,
                metadata=dict(sample.metadata), parent=sample.parent)
            order.append(sample.uid)
            continue
        for key, value in sample.metadata.items():
            if existing.metadata.get(key) in (None, ""):
                existing.metadata[key] = value
        if not existing.parent and sample.parent:
            existing.parent = sample.parent
        if not existing.sample_type and sample.sample_type:
            existing.sample_type = sample.sample_type

    return NormalizedInput(
        samples=[by_uid[u] for u in order],
        source={**base.source, "enriched_from": extra.source or {}},
    )
