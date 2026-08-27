"""A ratchet on the identifiers this PUBLIC repository already exposes.

WHAT THIS IS NOT. It is not a claim that the exposure is acceptable. It once
read "35 real sample identifiers and 18 protocol identifiers are in tracked
files right now"; on 2026-08-25 they came out and the verified baselines are
both 0. What the pattern tiers still guarantee is that the count of
identifier-SHAPED strings never grows unnoticed, which is the part that had
repeatedly failed here by accident rather than by choice.

WHY A RATCHET AND NOT A BAN. A ban on the SHAPE would be wrong: a test suite
about uid grammar needs well-formed uids, and 439 of them are legitimate
synthetic fixtures. A ban on the REALITY is what the verified tiers are, and
they now assert 0. The pattern tiers stay a ratchet: they go red the moment a
440th uid-shaped string lands, and red AGAIN when the count shrinks so the
baseline gets tightened rather than silently left stale. Both directions
matter: a ratchet that only catches growth quietly stops protecting anything
once the cleanup happens.

WHAT THE 2026-08-25 CLEANUP ACTUALLY DID, so the next person does not "restore"
it. Every real uid was replaced, not deleted -- the surrounding assertions and
prose need a well-formed identifier -- by moving its `<YYMMDD><LAB>` batch stamp
into a RESERVED SYNTHETIC BAND: `19MMDD`. Zero of the extract's 177,392 uuids
carry a 19xx date, for any lab, so any uid stamped 19MMDD is provably not a
person's sample, and the type prefix, lab code and serial are all preserved so
every documented relationship (siblings, shared serials, parent/child hops)
still reads. Protocol titles moved the same way: to `19MMDD` dates under lab
codes absent from all 553 sops titles. Keep new fixtures in those bands.

TWO HOLES THIS FILE HAD, both of which hid a REAL identifier. (1) CASE. Four
real sops titles were written lowercase (`p.mno-190105-v1_...docx`) and an
`[A-Z]{3}` pattern cannot see them; PROTOCOL_RE is now case-tolerant in its
character classes rather than by a flag, so `git grep -E` and `re` agree. (2)
BINARIES. `git grep -I` skips them by design, and `tests/fixtures/sample.xlsx`
carried three uids inside its zipped sheet XML. The third test below opens
tracked bytes and zip members instead of grepping.

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
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

EXTRACT = REPO / "assay-hygiene" / "extract"

# `P.LAB-YYMMDD-V#`. CASE-TOLERANT BY CHARACTER CLASS, never by re.IGNORECASE:
# `_tracked_matches` shells out to `git grep -E` with `pattern.pattern`, and a
# Python-side flag would not reach git. Four real sops titles were written
# lowercase and an `[A-Z]{3}` pattern could not see them.
PROTOCOL_RE = re.compile(r"[Pp]\.[A-Za-z]{3}-[0-9]{6}-[Vv][0-9]")

# The production uid grammar, from `_schema.UID_RE_FIXED`. Deliberately the
# permissive form: this scan should over-report, not under-report.
UID_RE = re.compile(r"\b([AD]\.)?[A-Z]{2,}-[0-9]{6}[A-Z]{2,5}-[0-9]+")

# The `<YYMMDD><LAB>` batch stamp ALONE, with no type prefix and no serial.
# This is the class both earlier scans missed: `190220WHI` names a real lab's
# real batch on a real date, and it is identifying even though it is not a
# whole uid, so no uid-shaped pattern will ever match it.
STAMP_RE = re.compile(r"[0-9]{6}[A-Z]{2,5}")

# --- the baselines -----------------------------------------------------------
# Measured 2026-08-26 on feat/mode2-followups, AFTER the cleanup. These two are
# ratchets on SHAPE: a suite about uid grammar legitimately needs well-formed
# uids, and every one of these is now synthetic. The REALITY tiers below are
# not ratchets -- they assert zero.
PROTOCOL_OCCURRENCES = 26          # case-tolerant; the case-sensitive count is 21
UID_PATTERN_OCCURRENCES = 440      # all synthetic
# 439 -> 440 on 2026-08-27: the prerequisites plan under docs/superpowers/plans/
# cites one 19MMDD-band uid as the example new fixtures must follow. Verified
# absent from all 177,393 production uids, and no 19xx-band uid is real for any
# lab. The literal is NOT repeated here -- writing it would itself bump the
# count, which is how this comment reached 441 on its first draft.


def _tracked_matches(pattern: re.Pattern) -> list[tuple[str, str]]:
    """-> (path, identifier) for every match in every TRACKED TEXT file."""
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


def _tracked_binaries() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO,
                         capture_output=True, text=True).stdout.split()
    return [REPO / f for f in out
            if f.lower().endswith((".xlsx", ".xls", ".zip", ".docx", ".pdf"))]


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


@pytest.fixture(scope="module")
def production():
    """-> (real uids, real `<YYMMDD><LAB>` stamps, real sops titles lowercased).

    Skips where the extract is absent, which is CI and every fresh clone. The
    two SHAPE ratchets above still run there; only the REALITY tiers need this.
    """
    if not (EXTRACT / "nodes.parquet").exists():
        pytest.skip("no extract; the pattern-only tiers still ran")
    import pandas as pd

    uids: set[str] = set()
    for name in ("nodes.parquet", "samples.parquet"):
        frame = pd.read_parquet(EXTRACT / name)
        for column in frame.columns:
            if "uuid" in column.lower() or "uid" in column.lower():
                uids |= set(frame[column].dropna().astype(str))
    assert uids, "the extract yielded no uids; these tests would be vacuous"

    stamps = {m.group(0) for u in uids
              for m in re.finditer(r"[0-9]{6}[A-Z]{2,5}(?=-)", u)}
    sops = pd.read_parquet(EXTRACT / "sops.parquet")
    titles = {str(v).lower() for c in sops.columns if "title" in c.lower()
              for v in sops[c].dropna()}
    return uids, stamps, titles


# --- SHAPE: ratchets, and they run everywhere --------------------------------


def test_the_protocol_identifier_count_never_grows():
    hits = _tracked_matches(PROTOCOL_RE)
    _ratchet(len(hits), PROTOCOL_OCCURRENCES,
             "protocol identifiers in tracked files",
             detail=f" Files: {sorted({p for p, _ in hits})}")


def test_the_sample_uid_pattern_count_never_grows():
    """The CI-safe tier: counts pattern hits without deciding if they are real.

    This is the one that runs where the extract does not exist, which is where
    an accidental commit is most likely to happen.
    """
    _ratchet(len(_tracked_matches(UID_RE)), UID_PATTERN_OCCURRENCES,
             "sample-uid-shaped strings in tracked files",
             detail=" If yours is a synthetic fixture, bump the baseline and "
                    "say so; if it is real, it must come out.")


# --- REALITY: not ratchets. Zero, or the repository is leaking. --------------


def test_the_real_extract_finds_no_genuine_sample_identifier(production):
    uids, _, _ = production
    real = sorted({u for _, u in _tracked_matches(UID_RE) if u in uids})
    assert not real, (
        f"{len(real)} REAL sample identifier(s) are in tracked files of a "
        f"PUBLIC repository. Replace each one, keeping its grammar, by moving "
        f"its date stamp into the reserved 19MMDD synthetic band: {real[:5]}")


def test_the_real_extract_finds_no_genuine_batch_stamp(production):
    """The class two earlier scans missed: a stamp with no uid around it.

    `190220WHI` is not a uid and no uid-shaped pattern matches it, but it names
    a real lab's real batch on a real date.
    """
    _, stamps, _ = production
    real = sorted({s for _, s in _tracked_matches(STAMP_RE) if s in stamps})
    assert not real, (
        f"{len(real)} REAL `<YYMMDD><LAB>` batch stamp(s) are in tracked "
        f"files: {real[:5]}")


def test_the_real_extract_finds_no_genuine_protocol_title(production):
    """Joined against sops titles, and case-insensitively on both sides."""
    _, _, titles = production
    hits = {h.lower() for _, h in _tracked_matches(PROTOCOL_RE)}
    real = sorted({h for h in hits if any(h in t for t in titles)})
    assert not real, (
        f"{len(real)} REAL protocol identifier(s) are in tracked files; one "
        f"such filename embeds a person's name: {real[:5]}")


def test_no_real_identifier_hides_inside_a_tracked_binary(production):
    """`git grep -I` skips binaries by design, and that hole hid three uids.

    `tests/fixtures/sample.xlsx` is a zip; its sheet XML is text nothing above
    can see. This opens tracked bytes and zip members instead of grepping.
    """
    uids, stamps, _ = production
    leaked: dict[str, list[str]] = {}
    for path in _tracked_binaries():
        blobs = []
        try:
            with zipfile.ZipFile(path) as archive:
                blobs = [archive.read(n) for n in archive.namelist()]
        except (zipfile.BadZipFile, OSError):
            blobs = [path.read_bytes()]
        found: set[str] = set()
        for blob in blobs:
            text = blob.decode("utf-8", "ignore")
            found |= {m.group(0) for m in UID_RE.finditer(text) if m.group(0) in uids}
            found |= {m.group(0) for m in STAMP_RE.finditer(text) if m.group(0) in stamps}
        if found:
            leaked[str(path.relative_to(REPO))] = sorted(found)
    assert not leaked, (
        f"real identifiers are hidden inside tracked binary files, where "
        f"`git grep` cannot see them: {leaked}")
