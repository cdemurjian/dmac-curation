# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Field index and reuse check over the NExtSEEK sample type catalog.

The problem this attacks: of 1059 distinct field names across 101 sample types,
857 are used by exactly one type, and none of the 1059 carries a description,
datatype or vocabulary anywhere. There is no way for an author to answer "does a
field for this already exist?", so new near-duplicates get minted by default.

What this module deliberately does NOT do: propose renames or splits. A field
name shared across sample types is not a defect. `Type` appears on many types
and legitimately means different things on each. This module records what a
field means *here*; deciding that two usages are "really" the same is a
curation judgment a human makes.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import plugin_context  # noqa: E402

FIELD_SOURCES = ("Required Metadata", "Standard Metadata", "Possible Metadata Fields")

# Suffixes that are safe to strip when normalizing. "Status" -> "Statu" and
# "Analysis" -> "Analysi" are the failure modes this guards against.
_PLURAL_EXCEPTIONS = {"status", "analysis", "series", "species", "apparatus"}


@dataclass
class FieldUsage:
    """Where one field name appears across the catalog."""

    name: str
    used_by: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.used_by)


@dataclass
class Candidate:
    """A reuse-check hit, ranked. The curator judges; the tool never decides."""

    name: str
    usage_count: int
    used_by: list[str]
    match_pass: str          # exact | normalized | synonym | semantic
    example_values: list[str] = field(default_factory=list)
    score: float = 0.0


def load_catalog(path: Path | None = None) -> list[dict]:
    """Read `sampletypes_db.json`. Defaults to the plugin's read-only copy."""
    return json.loads(Path(path or plugin_context("sampletypes_db.json")).read_text())


def type_record(catalog: list[dict], sampletype: str) -> dict:
    for t in catalog:
        if t.get("SampleType") == sampletype:
            return t
    raise KeyError(f"SampleType {sampletype!r} not in catalog")


def siblings_in_clade(catalog: list[dict], sampletype: str) -> list[dict]:
    """Other types sharing this type's Clade. Their fields are the best prior."""
    rec = type_record(catalog, sampletype)
    clade = rec.get("Clade")
    if not clade:
        return []
    return [t for t in catalog
            if t.get("Clade") == clade and t.get("SampleType") != sampletype]


def _split_list(value) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def build_field_index(types: list[dict]) -> dict[str, FieldUsage]:
    """Map every declared field name to the sample types that declare it."""
    index: dict[str, FieldUsage] = {}
    for t in types:
        code = t.get("SampleType")
        for source in FIELD_SOURCES:
            for name in _split_list(t.get(source)):
                usage = index.setdefault(name, FieldUsage(name=name))
                if code not in usage.used_by:
                    usage.used_by.append(code)
    return index


def normalize_field_name(name: str) -> str:
    """Fold case, underscores, hyphens, spaces and a trailing plural.

    Used only for the *normalized* matching pass. The original spelling is
    always what gets reported back.
    """
    folded = "".join(ch for ch in name.strip().lower() if ch.isalnum())
    if folded in _PLURAL_EXCEPTIONS:
        return folded
    if folded.endswith("ies") and len(folded) > 4:
        return folded[:-3] + "y"
    if folded.endswith("s") and not folded.endswith("ss") and len(folded) > 3:
        return folded[:-1]
    return folded


def _observed_values(name: str, dictionary: dict | None) -> list[str]:
    if not dictionary:
        return []
    return list((dictionary.get(name) or {}).get("observed_values") or [])


def rank_candidates(
    candidate: str,
    index: dict[str, FieldUsage],
    *,
    clade: str | None = None,
    assay: str | None = None,
    catalog: list[dict] | None = None,
    dictionary: dict | None = None,
    limit: int = 10,
) -> list[Candidate]:
    """Ranked existing field names that might already cover `candidate`.

    Never a yes/no. Passes, in order of confidence:
      1. exact name
      2. normalized name (case, separators, plural)
      3. synonym match against dictionary entries
      4. semantic match over shared word stems

    Ranked within a pass by usage count, then clade proximity, then assay
    proximity. The curator is shown the name, how many types use it, which ones,
    and example values, and then judges.
    """
    target_norm = normalize_field_name(candidate)
    clade_types: set[str] = set()
    assay_types: set[str] = set()
    if catalog:
        if clade:
            clade_types = {t["SampleType"] for t in catalog
                           if t.get("Clade") == clade}
        if assay:
            assay_types = {t["SampleType"] for t in catalog
                           if assay in (t.get("Associated Assay Parents") or "")}

    synonym_of: dict[str, str] = {}
    for canonical, entry in (dictionary or {}).items():
        for syn in (entry or {}).get("synonyms") or []:
            synonym_of[normalize_field_name(syn)] = canonical

    pass_weight = {"exact": 1000.0, "normalized": 500.0,
                   "synonym": 400.0, "semantic": 100.0}
    target_words = _words(candidate)

    out: list[Candidate] = []
    for name, usage in index.items():
        norm = normalize_field_name(name)
        if name == candidate:
            match = "exact"
        elif norm == target_norm:
            match = "normalized"
        elif synonym_of.get(target_norm) == name:
            match = "synonym"
        elif target_words and target_words & _words(name):
            match = "semantic"
        else:
            continue

        score = pass_weight[match] + float(usage.count)
        if clade_types & set(usage.used_by):
            score += 25.0
        if assay_types & set(usage.used_by):
            score += 15.0
        out.append(Candidate(
            name=name,
            usage_count=usage.count,
            used_by=list(usage.used_by),
            match_pass=match,
            example_values=_observed_values(name, dictionary),
            score=score,
        ))

    out.sort(key=lambda c: (-c.score, c.name))
    return out[:limit]


def _words(name: str) -> set[str]:
    """CamelCase / underscore / space split into lowercase word stems.

    An uppercase RUN is split before the character that begins the next word,
    so `QCPlatform` yields qc + platform rather than one opaque token. Without
    that, a `Platform` query could not see `QCPlatform` on D.SEQ - the very type
    that owns it - and the semantic pass is the last thing standing between a
    curator and a duplicate name.

    Two-letter stems are kept. The old `len(w) > 2` filter deleted `bp`, which
    left `F_bp` and `R_bp` with an EMPTY word set, so they could never match
    anything at all.
    """
    chars = name.replace("_", " ").replace("-", " ")
    buf, words = "", []
    for i, ch in enumerate(chars):
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch == " ":
            if buf:
                words.append(buf)
            buf = ""
            continue
        if ch.isupper() and buf and (not buf[-1].isupper() or nxt.islower()):
            words.append(buf)
            buf = ch
            continue
        buf += ch
    if buf:
        words.append(buf)
    return {normalize_field_name(w) for w in words if len(w) >= 2}


def mine_tags(record: dict) -> list[str]:
    """Candidate controlled values already written down in the Tags column.

    The cheapest win available. D.VIA's Tags read 'viability data, cell
    viability, cytotoxicity data, MTS assay, MTT assay, WST-1, live/dead assay,
    CellTiter-Glo, proliferation assay, cell death data' - permissible values
    for its `Type` field, sitting in prose where nothing can enforce them.
    """
    return _split_list(record.get("Tags"))
