"""A ratchet on the identifiers this PUBLIC repository already exposes.

WHAT THIS IS NOT. It is not a claim that the exposure is acceptable. 35 real
sample identifiers and 18 protocol identifiers are in tracked files right now,
and removing them means rewriting published history on a shared branch --
an operator decision this suite cannot make. What a test CAN do is guarantee
the number never goes up while that decision is pending, which is the part that
has repeatedly failed here by accident rather than by choice.

WHY A RATCHET AND NOT A BAN. A test asserting zero would be red on arrival and
would be disabled within a day. A ratchet is green today, goes red the moment a
36th identifier lands, and goes red AGAIN when the exposure shrinks so the
baseline gets tightened rather than silently left stale. Both directions matter:
a ratchet that only catches growth quietly stops protecting anything once the
cleanup happens.

HOW THIS WAS MISSED FOR FOUR DAYS. The 2026-08-25 pre-push scan checked the
DIFF of one push -- "0 protocol identifiers in added lines, 5 sample uids all
verified synthetic" -- and reported clean, correctly. It never scanned the whole
tracked tree, so 97 occurrences already sitting in 22 files were invisible to
it. Scanning a diff answers "am I adding one"; only scanning the tree answers
"is one there". This file asks the second question.

THE TWO TIERS, AND WHY THE WEAKER ONE IS THE IMPORTANT ONE. Deciding whether a
uid is REAL needs `assets/RUN1/01-extract/`, which is absent on CI and on every
fresh clone -- exactly where an accidental commit is most likely. So the
pattern-only tier runs everywhere and ratchets on the raw hit count, real or
synthetic; the verified tier runs only where the extract exists and names the
smaller true number. A synthetic fixture that trips the pattern tier is a
five-second baseline bump. A real identifier that trips it is a history rewrite.
Erring toward the false positive is the whole point.

NO IDENTIFIER IS WRITTEN INTO THIS FILE. The baselines are counts. The
identifiers are read out of the tree at runtime and named only in a failure
message, which is the same rule `tests/test_assay_hygiene_rulings.py` follows
for cohort keys.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

EXTRACT = REPO / "assay-hygiene" / "extract"

# `P.LAB-YYMMDD-V#`. One of the 18 embeds a person's name in the filename that
# follows it, which is why this is tracked separately from sample uids.
PROTOCOL_RE = re.compile(r"P\.[A-Z]{3}-[0-9]{6}-V[0-9]")

# The production uid grammar, from `_schema.UID_RE_FIXED`. Deliberately the
# permissive form: this scan should over-report, not under-report.
UID_RE = re.compile(r"\b([AD]\.)?[A-Z]{2,}-[0-9]{6}[A-Z]{2,5}-[0-9]+")

# --- the baselines -----------------------------------------------------------
# Measured 2026-08-25 on feat/mode2-followups. LOWER THESE when the cleanup
# lands; the test tells you what to lower them to.
PROTOCOL_OCCURRENCES = 21          # 18 distinct, across 4 files
UID_PATTERN_OCCURRENCES = 439      # real AND synthetic; the CI-safe number
UID_REAL_DISTINCT = 35             # verified against the extract, across 22 files


def _tracked_matches(pattern: re.Pattern) -> list[tuple[str, str]]:
    """-> (path, identifier) for every match in every TRACKED file."""
    out = subprocess.run(
        ["git", "grep", "-InE", pattern.pattern],
        cwd=REPO, capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        for m in pattern.finditer(parts[2]):
            found.append((parts[0], m.group(0)))
    return found


def _ratchet(actual: int, baseline: int, what: str, detail: str = "") -> None:
    """Fail on growth, and fail on an un-tightened win."""
    assert actual <= baseline, (
        f"{what} GREW from {baseline} to {actual}. This repository is PUBLIC. "
        f"Do not lower the bar to make this pass -- remove the identifier."
        + detail)
    assert actual == baseline, (
        f"{what} shrank from {baseline} to {actual}. Lower the baseline in "
        f"tests/test_identifier_exposure.py to {actual} to lock the win in, "
        f"or the ratchet quietly stops protecting the difference.")


def test_the_protocol_identifier_count_never_grows():
    hits = _tracked_matches(PROTOCOL_RE)
    files = sorted({p for p, _ in hits})
    _ratchet(len(hits), PROTOCOL_OCCURRENCES, "protocol identifiers in tracked files",
             detail=f" Files: {files}")


def test_the_sample_uid_pattern_count_never_grows():
    """The CI-safe tier: counts pattern hits without deciding if they are real.

    This is the one that runs where the extract does not exist, which is where
    an accidental commit is most likely to happen.
    """
    hits = _tracked_matches(UID_RE)
    _ratchet(len(hits), UID_PATTERN_OCCURRENCES,
             "sample-uid-shaped strings in tracked files",
             detail=" If yours is a synthetic fixture, bump the baseline and "
                    "say so; if it is real, it must come out.")


def test_the_real_extract_confirms_which_exposed_uids_are_genuine():
    """The verified tier. Names the true number, and only runs where it can.

    A pattern hit is not an exposure -- most of this repo's are synthetic
    fixtures. This one joins against the production extract and ratchets on
    what is actually a person's sample.
    """
    if not (EXTRACT / "nodes.parquet").exists():
        pytest.skip("no extract; the pattern-only tier still ran")
    import pandas as pd

    universe: set[str] = set()
    for name in ("nodes.parquet", "samples.parquet"):
        frame = pd.read_parquet(EXTRACT / name)
        for column in frame.columns:
            if "uuid" in column.lower() or "uid" in column.lower():
                universe |= set(frame[column].dropna().astype(str))
    assert universe, "the extract yielded no uids; this test would be vacuous"

    real = {u for _, u in _tracked_matches(UID_RE) if u in universe}
    _ratchet(len(real), UID_REAL_DISTINCT,
             "REAL sample identifiers in tracked files",
             detail=f" Newly exposed: {sorted(real)[:5]}")
