# Assay Hygiene Prerequisites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a second assay-hygiene run safe to start, by fixing four live defects that would let it destroy the evidence RUN1's judgement rests on.

**Architecture:** Four independent, small changes to `scripts/assay_hygiene/` and `tests/conftest.py`, each pinned by a test that fails before the fix. No new modules, no behaviour change to the detection pipeline. The largest is a write-guard helper that refuses to write through a symlink.

**Tech Stack:** Python 3.11+, pandas, pytest. Run everything with `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest ...`

**Spec:** `docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` §6 (Prerequisites) and §7 (Testing)

## Global Constraints

- **This repository is PUBLIC.** Never write a real sample uid, protocol identifier, or `<YYMMDD><LAB>` batch stamp into a tracked file. `tests/test_identifier_exposure.py` enforces this and will fail the build. Synthetic uids must use the reserved `19MMDD` date band (e.g. `TIS-190101ENG-901`), which is provably absent from production.
- **Suite baseline depends on where you run it. Measure yours before Task 1 and use that number.**
  - Main checkout: **1,347 passed / 9 skipped / 4 xfailed**
  - Worktree `.claude/worktrees/prereqs`: **1,345 passed / 11 skipped / 4 xfailed**

  The 2-test difference is `tests/test_no_plaintext_secrets.py`, which skips
  without a `working/` directory — gitignored, so absent from a fresh worktree.
  It is unrelated to this plan. What matters is that **no `_real_extract_` test
  skips in either place**: every extract-backed measurement runs, and the
  skipped-work banner stays silent. If it fires, stop — the extract is not
  reachable and nothing below is being measured.

  A worktree also needs two hand-copied fixtures that `.gitignore` refuses
  (`*rulings*.tsv` at any depth): copy `tests/fixtures/mode1-rulings.tsv` and
  `mode2-rulings.tsv` from the main checkout, or 9 tests skip and the
  intentional xfail silently becomes a skip.

  Expected counts below are written against the **worktree** baseline of 1,345.
  Add 2 if running in the main checkout.
- The 4 xfails are intentional deliverables. Never "fix" an xfail to make it pass.
- **Never write to `assets/RUN1/`.** Tiers `00`–`03` are read-only on disk; `04`–`07` are not, and that is exactly the defect Task 1 fixes.
- **`assay-hygiene/` is a symlink tree into `assets/RUN1/`**, not a directory of real files.
- Commit after every task. Do not push.

---

### Task 1: Refuse to write through a symlink

**Files:**
- Create: `scripts/assay_hygiene/_writeguard.py`
- Modify: `scripts/assay_hygiene/run_evidence.py:885-887`, `scripts/assay_hygiene/run_detect.py:1071-1086`, `scripts/assay_hygiene/classify.py:1873`
- Test: `tests/test_assay_hygiene_writeguard.py`

**Why:** `run_evidence.main` and `run_detect.main` both default `out_dir="assay-hygiene"`. That directory is 33 symlinks into `assets/RUN1/`; `assay-hygiene/findings.csv` resolves to `assets/RUN1/04-artifacts/findings.csv`. A default-path run therefore overwrites the baseline every measurement is compared against. 27 of 33 artifacts are reachable this way. The read-only tiers (`00`–`03`) resist by permission; `04-artifacts` does not.

**Interfaces:**
- Produces: `assert_writable(out: Path, names: Iterable[str]) -> None` — raises `SymlinkWriteRefused` (a `RuntimeError` subclass) naming every offending path. Called by `run_evidence.main`, `run_detect.main`, `classify.main` before any write.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_writeguard.py
"""A run must never write through a symlink into the preserved baseline.

`assay-hygiene/` is 33 symlinks into `assets/RUN1/`. Writing `findings.csv`
there does not create a file -- it follows the link and overwrites the RUN1
artifact that every before/after measurement is compared against. The tiers
that hold rulings are chmod a-w and resist; `04-artifacts` is writable and does
not.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene._writeguard import assert_writable, SymlinkWriteRefused  # noqa: E402


def test_a_plain_directory_is_writable(tmp_path):
    assert_writable(tmp_path, ["findings.csv"])          # must not raise


def test_a_symlinked_target_is_refused(tmp_path):
    real = tmp_path / "baseline"; real.mkdir()
    (real / "findings.csv").write_text("the RUN1 baseline")
    out = tmp_path / "out"; out.mkdir()
    (out / "findings.csv").symlink_to(real / "findings.csv")

    with pytest.raises(SymlinkWriteRefused, match="findings.csv"):
        assert_writable(out, ["findings.csv"])


def test_the_refusal_names_every_offender_not_just_the_first(tmp_path):
    real = tmp_path / "baseline"; real.mkdir()
    out = tmp_path / "out"; out.mkdir()
    for name in ("findings.csv", "claims.parquet"):
        (real / name).write_text("x")
        (out / name).symlink_to(real / name)

    with pytest.raises(SymlinkWriteRefused) as excinfo:
        assert_writable(out, ["findings.csv", "claims.parquet"])
    assert "findings.csv" in str(excinfo.value)
    assert "claims.parquet" in str(excinfo.value)


def test_a_missing_name_is_fine(tmp_path):
    """A file that does not exist yet is the normal case, not an error."""
    assert_writable(tmp_path, ["not-created-yet.csv"])


def test_a_symlinked_OUT_DIR_is_refused(tmp_path):
    """The whole directory being a link is the same hazard one level up."""
    real = tmp_path / "baseline"; real.mkdir()
    out = tmp_path / "out"
    out.symlink_to(real, target_is_directory=True)

    with pytest.raises(SymlinkWriteRefused):
        assert_writable(out, ["findings.csv"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_writeguard.py -q`

Expected: collection error — `ImportError: cannot import name '_writeguard'`. That is the correct first failure; the module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/_writeguard.py
# /// script
# requires-python = ">=3.11"
# ///
"""Refuse to write through a symlink into a preserved run.

WHY THIS EXISTS. `run_evidence.main` and `run_detect.main` default
`out_dir="assay-hygiene"`, and that directory is 33 symlinks into
`assets/RUN1/`. Writing `findings.csv` there follows the link and destroys the
baseline every before/after measurement in this package is compared against.
Four separate files claimed `chmod a-w` protected this; nothing applied it, and
the tiers that ARE read-only are the ones the pipeline never writes to.

This raises rather than warns because the caller's next act is a write, and a
warning attached to a destroyed baseline is not a warning.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class SymlinkWriteRefused(RuntimeError):
    """A write would have followed a symlink out of `out_dir`."""


def assert_writable(out: Path, names: Iterable[str]) -> None:
    """Raise unless every `name` under `out` can be written without following a link."""
    out = Path(out)
    offenders: list[str] = []
    if out.is_symlink():
        offenders.append(f"{out}/ (the output directory itself) -> {out.readlink()}")
    else:
        for name in names:
            target = out / name
            if target.is_symlink():
                offenders.append(f"{target} -> {target.readlink()}")
    if offenders:
        raise SymlinkWriteRefused(
            "refusing to write through a symlink; this would overwrite a "
            "preserved artifact rather than create a file. Pass an out_dir "
            "that is a real directory:\n  " + "\n  ".join(offenders))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_writeguard.py -q`

Expected: `5 passed`

- [ ] **Step 5: Wire it into the three entry points**

In `scripts/assay_hygiene/run_detect.py`, inside `main` immediately after `d, out = Path(extract_dir), Path(out_dir)` (currently line 1086):

```python
    from ._writeguard import assert_writable
    assert_writable(out, ARTIFACTS)
```

In `scripts/assay_hygiene/run_evidence.py`, inside `main` immediately after `d, out = Path(extract_dir), Path(out_dir)` (currently line 887):

```python
    from ._writeguard import assert_writable
    assert_writable(out, ("vocabulary.csv", "claims.parquet", "precedent.csv",
                          "vocabulary-unresolved.csv", "vocabulary-curator.csv",
                          "vocabulary-defects.csv", "mode3-disposition.csv",
                          "evidence-report.md"))
```

In `scripts/assay_hygiene/classify.py`, inside `main` after its `out` is resolved (near line 1873):

```python
    from ._writeguard import assert_writable
    assert_writable(out, ("findings.csv",))
```

- [ ] **Step 6: Prove the guard fires on the real tree**

Run:
```bash
uv run --no-project --with pandas --with pyarrow python -c "
import sys; sys.path.insert(0,'scripts')
from assay_hygiene.run_detect import main
main('assets/RUN1/01-extract', 'assay-hygiene')
"
```
Expected: `SymlinkWriteRefused` naming `assay-hygiene/findings.csv -> ../assets/RUN1/04-artifacts/findings.csv`. Before this task the same command silently destroyed the baseline.

- [ ] **Step 7: Run the full suite**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest tests/ -q`

Expected: `1350 passed, 11 skipped, 4 xfailed` (baseline 1,347 + 5 new). If any previously-passing test now errors with `SymlinkWriteRefused`, that test was writing through the symlink tree — fix the test to use `tmp_path`, do not weaken the guard.

- [ ] **Step 8: Commit**

```bash
git add scripts/assay_hygiene/_writeguard.py tests/test_assay_hygiene_writeguard.py \
        scripts/assay_hygiene/run_detect.py scripts/assay_hygiene/run_evidence.py \
        scripts/assay_hygiene/classify.py
git commit -m "fix(assay-hygiene): refuse to write through a symlink into a preserved run

run_evidence and run_detect both default out_dir to assay-hygiene/, which is 33
symlinks into assets/RUN1/. A default-path run followed those links and
overwrote the baseline every before/after measurement is compared against -- 27
of 33 artifacts were reachable that way. Four files claimed chmod a-w prevented
this; nothing applied it, and the tiers that are read-only are the ones the
pipeline never writes to.

Raises rather than warns: the caller's next act is a write, and a warning
attached to a destroyed baseline is not a warning."
```

---

### Task 2: Apply the write protection the docs claim exists

**Files:**
- Create: `scripts/assay_hygiene/protect_run.py`
- Test: `tests/test_assay_hygiene_protect_run.py`
- Modify: `assets/RUN1/README.md` (untracked — edit but do not commit)

**Why:** `assets/RUN1/README.md`, `validation_sample.py:1435`, `tests/test_assay_hygiene_rulings.py:141` and a findings doc all state the first four tiers are `chmod a-w`. A repo-wide grep for `chmod a-w` finds only those claims — no script performs it. Tiers `00`–`03` happen to be read-only because someone did it by hand once; `04`–`07` are not, and `05-review` holds `contested-ALL.csv` and `unruled-queue.csv`, which are inputs to `REGISTRATION-ROWS.csv` and are human judgement.

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `protect(run_dir: Path, tiers: Iterable[str]) -> list[Path]` — sets mode `0o555` on each tier directory and `0o444` on its files, returning what it changed. `verify(run_dir, tiers) -> list[Path]` returns tiers that are NOT protected.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_protect_run.py
"""The write protection four files claim, actually applied.

Nothing in this repository performed the `chmod a-w` that `assets/RUN1/README.md`,
`validation_sample.py`, `tests/test_assay_hygiene_rulings.py` and a findings doc
all assert. This makes the claim true and checkable.
"""
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene.protect_run import protect, verify  # noqa: E402


def _run(tmp_path):
    run = tmp_path / "RUN9"
    for tier in ("00-rulings", "04-artifacts"):
        (run / tier).mkdir(parents=True)
        (run / tier / "judgement.tsv").write_text("cohort\tverdict\n")
    return run


def test_protect_makes_a_tier_unwritable(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    mode = (run / "00-rulings").stat().st_mode
    assert not (mode & stat.S_IWUSR), "the directory is still writable"


def test_a_protected_tier_refuses_a_new_file(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    try:
        (run / "00-rulings" / "sneaked-in.csv").write_text("x")
        raised = False
    except PermissionError:
        raised = True
    assert raised, "a protected tier accepted a new file"


def test_verify_reports_an_unprotected_tier(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    unprotected = verify(run, ["00-rulings", "04-artifacts"])
    assert [p.name for p in unprotected] == ["04-artifacts"]


def test_verify_is_empty_once_everything_is_protected(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings", "04-artifacts"])
    assert verify(run, ["00-rulings", "04-artifacts"]) == []


def test_protect_is_idempotent(tmp_path):
    run = _run(tmp_path)
    protect(run, ["00-rulings"])
    assert protect(run, ["00-rulings"]) == [], "second call re-changed something"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_protect_run.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'assay_hygiene.protect_run'`

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/protect_run.py
# /// script
# requires-python = ">=3.11"
# ///
"""Make a completed run read-only, and check that it is.

WHY. `assets/RUN1/README.md` and three source files state that the first four
tiers of a run are `chmod a-w`. No code applied it. The tiers that are in fact
read-only are the ones the pipeline never writes to, so the protection that
exists protects nothing and the protection that matters was never there.

Directories are set to 0o555 rather than files alone, because a writable
directory accepts a NEW file even when every existing file is read-only -- and
an artifact appearing beside the baseline is the symptom this is meant to stop.
"""
from __future__ import annotations

import stat
from collections.abc import Iterable
from pathlib import Path

DIR_MODE = 0o555
FILE_MODE = 0o444


def protect(run_dir: Path, tiers: Iterable[str]) -> list[Path]:
    """-> the paths whose mode this call actually changed."""
    changed: list[Path] = []
    for tier in tiers:
        base = Path(run_dir) / tier
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*"), reverse=True):
            want = DIR_MODE if path.is_dir() else FILE_MODE
            if stat.S_IMODE(path.stat().st_mode) != want:
                path.chmod(want); changed.append(path)
        if stat.S_IMODE(base.stat().st_mode) != DIR_MODE:
            base.chmod(DIR_MODE); changed.append(base)
    return changed


def verify(run_dir: Path, tiers: Iterable[str]) -> list[Path]:
    """-> the tiers that are NOT protected. Empty means every tier is."""
    bad: list[Path] = []
    for tier in tiers:
        base = Path(run_dir) / tier
        if base.is_dir() and (stat.S_IMODE(base.stat().st_mode) & stat.S_IWUSR):
            bad.append(base)
    return bad
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_protect_run.py -q`

Expected: `5 passed`

- [ ] **Step 5: Apply it to RUN1's unprotected tiers**

Run:
```bash
uv run --no-project python -c "
import sys; sys.path.insert(0,'scripts')
from pathlib import Path
from assay_hygiene.protect_run import protect, verify
print('changed:', len(protect(Path('assets/RUN1'), ['04-artifacts','05-review','06-findings'])))
print('still unprotected:', verify(Path('assets/RUN1'), ['00-rulings','01-extract','02-agent-runs','03-stage0-applied','04-artifacts','05-review','06-findings']))
"
```
Expected: a non-zero change count, then `still unprotected: []`.

`07-process` is deliberately left writable — it holds the SDD workspace a future run appends to.

- [ ] **Step 6: Correct the false claim in the RUN1 README**

`assets/RUN1/` is gitignored, so this is a local edit with nothing to commit. Replace the sentence asserting the first four tiers are `chmod a-w` with an accurate one naming which tiers are protected and that `scripts/assay_hygiene/protect_run.py` is what applies it.

- [ ] **Step 7: Run the full suite**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest tests/ -q`

Expected: `1355 passed, 11 skipped, 4 xfailed`. If a test now fails with `PermissionError` under `assets/RUN1/`, it was writing into a preserved tier — that is the defect being fixed, so redirect the test to `tmp_path`.

- [ ] **Step 8: Commit**

```bash
git add scripts/assay_hygiene/protect_run.py tests/test_assay_hygiene_protect_run.py
git commit -m "feat(assay-hygiene): apply the write protection four files claim exists

assets/RUN1/README.md, validation_sample.py, test_assay_hygiene_rulings.py and
a findings doc all state the first four tiers of a run are chmod a-w. A
repo-wide grep for that string finds only the claims -- no code performs it.
The tiers that happen to be read-only are the ones the pipeline never writes
to, so the protection that existed protected nothing.

Directories go to 0o555, not just files to 0o444: a writable directory accepts
a NEW file even when every existing file is read-only, and an artifact
appearing beside the baseline is the symptom this stops. verify() makes the
claim checkable instead of asserted."
```

---

### Task 3: Fail with a named error, not a bare traceback

**Files:**
- Modify: `scripts/assay_hygiene/gate.py:950-955`, `scripts/assay_hygiene/classify.py:1918-1926`
- Test: `tests/test_assay_hygiene_missing_inputs.py`

**Why:** `assets/RUN1/README.md` documents `run_detect <extract> /tmp/out` as the way to reproduce a run. It does not work: `run_detect.main` never calls `run_evidence`, and `gate.py` and `classify.py` read `claims.parquet` and `vocabulary.csv` from `out_dir` with no existence check, so the single documented command dies with `FileNotFoundError` and no indication of what to run first. `compatibility.py:670-676` already does this correctly.

**Interfaces:**
- Consumes: nothing.
- Produces: both `main` functions return exit code `2` and print a message naming the missing file and the command that creates it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_missing_inputs.py
"""A missing prerequisite must name itself and the command that makes it.

`assets/RUN1/README.md` documents `run_detect <extract> /tmp/out` as the
reproduction command. run_detect never calls run_evidence, so gate and classify
read claims.parquet out of an empty directory and die with a bare traceback.
`compatibility.py:670-676` already handles this correctly; these two did not.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import gate as G, classify as X  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"


def test_gate_names_the_missing_input_rather_than_raising(tmp_path, capsys):
    rc = G.main(str(EXTRACT), str(tmp_path))
    assert rc == 2
    out = capsys.readouterr().out
    assert "claims.parquet" in out
    assert "run_evidence" in out, "the message must say what to run first"


def test_classify_names_the_missing_input_rather_than_raising(tmp_path, capsys):
    rc = X.main(str(EXTRACT), str(tmp_path))
    assert rc == 2
    out = capsys.readouterr().out
    assert "claims.parquet" in out or "vocabulary.csv" in out
    assert "run_evidence" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_missing_inputs.py -q`

Expected: FAIL with `FileNotFoundError: .../claims.parquet` — the bare traceback this task removes. (If `assay-hygiene/extract` is absent the tests error on the fixture instead; that is the CI state and is acceptable — they run where the extract exists.)

- [ ] **Step 3: Write the minimal implementation**

In `scripts/assay_hygiene/gate.py`, in `main`, immediately before the first read of `claims.parquet` (currently near line 950):

```python
    missing = [f for f in ("claims.parquet", "vocabulary.csv")
               if not (out / f).exists()]
    if missing:
        print(f"ERROR: {missing} not found under {out}. This stage reads what "
              f"`run_evidence` writes; run it first:\n"
              f"  PYTHONPATH=scripts uv run --with pandas --with pyarrow \\\n"
              f"      python -m assay_hygiene.run_evidence {extract_dir} {out}")
        return 2
```

Apply the identical block in `scripts/assay_hygiene/classify.py`, in `main`, before its first read (currently near line 1918).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_missing_inputs.py -q`

Expected: `2 passed`

- [ ] **Step 5: Fix the command the RUN1 README documents**

`assets/RUN1/` is gitignored, so this is a local edit. Replace the single-command reproduction block with the working two-command form, including the `vocabulary-curator.csv` copy that `run_evidence` needs:

```bash
mkdir -p /tmp/run2 && cp assets/RUN1/04-artifacts/vocabulary-curator.csv /tmp/run2/
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence assets/RUN1/01-extract /tmp/run2
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_detect   assets/RUN1/01-extract /tmp/run2
```

- [ ] **Step 6: Run the full suite**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest tests/ -q`

Expected: `1357 passed, 11 skipped, 4 xfailed`

- [ ] **Step 7: Commit**

```bash
git add scripts/assay_hygiene/gate.py scripts/assay_hygiene/classify.py \
        tests/test_assay_hygiene_missing_inputs.py
git commit -m "fix(assay-hygiene): name the missing prerequisite instead of a bare traceback

The one reproduction command assets/RUN1/README.md gives the next operator does
not work. run_detect never calls run_evidence, and gate and classify read
claims.parquet and vocabulary.csv out of out_dir with no existence check, so it
dies with FileNotFoundError and no indication of what to run first.

compatibility.py:670-676 already had the right pattern; this copies it. Returns
2 and prints the command that creates the missing file."
```

---

### Task 4: Make the skipped-measurement banner see every skip

**Files:**
- Modify: `tests/conftest.py:127`
- Test: `tests/test_conftest_banner.py`

**Why:** The banner exists to stop a run in which nothing was measured from reading as a green suite. It matches `"_real_extract_"` **with a trailing underscore**. Two tests end `..._on_the_real_extract` and eleven more skip via `skipif` without the naming convention, so 13 of 40 skips are invisible to it — the guard whose entire job is to report unmeasured work under-reports by a third. `test_assay_hygiene_rulings.py:57` documents the fast lane as `-k 'not real_extract'`, without the underscore, so the two conventions already disagree.

**Interfaces:**
- Consumes: nothing.
- Produces: `_MEASUREMENT_CONVENTION` becomes a compiled pattern matching `real_extract` anywhere in a nodeid.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_conftest_banner.py
"""The banner must see every extract-backed skip, not the ones named one way.

It exists to stop a run that measured nothing from reading as green. Matching
`_real_extract_` with a trailing underscore misses tests ending
`..._on_the_real_extract` and every `skipif` that does not follow the naming
convention -- 13 of 40 skips on a fresh clone.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))

from conftest import _MEASUREMENT_CONVENTION as PATTERN  # noqa: E402


def _matches(nodeid: str) -> bool:
    return bool(re.search(PATTERN, nodeid))


def test_it_matches_the_underscore_delimited_form():
    assert _matches("tests/t.py::test_the_real_extract_drops_every_cohort")


def test_it_matches_a_name_ENDING_in_real_extract():
    """Two real tests end this way and were invisible to the banner."""
    assert _matches("tests/t.py::test_the_gate_is_coherent_on_the_real_extract")


def test_it_does_not_match_an_unrelated_test():
    assert not _matches("tests/t.py::test_the_csv_carries_the_key")


def test_every_extract_backed_test_in_the_tree_is_visible_to_it():
    """Measured against the actual suite, not a fixture."""
    names = []
    for path in (REPO / "tests").glob("test_*.py"):
        for line in path.read_text().splitlines():
            if line.startswith("def test_") and "real_extract" in line:
                names.append(line.split("(")[0].removeprefix("def "))
    assert names, "no extract-backed tests found; this test would be vacuous"
    invisible = [n for n in names if not _matches(f"tests/x.py::{n}")]
    assert not invisible, f"invisible to the banner: {invisible}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_conftest_banner.py -q`

Expected: 2 failures — `test_it_matches_a_name_ENDING_in_real_extract` and `test_every_extract_backed_test_in_the_tree_is_visible_to_it`, the latter naming the two `..._on_the_real_extract` tests.

- [ ] **Step 3: Write the minimal implementation**

In `tests/conftest.py`, replace the constant at line 127:

```python
# Matches `real_extract` ANYWHERE in a nodeid. The earlier `_real_extract_`
# required delimiting underscores on both sides and so could not see the two
# tests ending `..._on_the_real_extract`, nor any `skipif` that does not follow
# the naming convention -- 13 of 40 skips on a fresh clone. A guard whose job
# is to report unmeasured work must not itself under-report.
_MEASUREMENT_CONVENTION = "real_extract"
```

No change is needed at the call site: `pytest_terminal_summary` already does a substring test, and `"real_extract" in nodeid` is exactly the wanted semantics.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_conftest_banner.py -q`

Expected: `4 passed`

- [ ] **Step 5: Verify the banner now counts more on a simulated fresh clone**

Run:
```bash
cat > tests/test_zz_probe_on_the_real_extract.py <<'PY'
import pytest
def test_the_gate_is_coherent_on_the_real_extract():
    pytest.skip("simulating a fresh clone")
PY
uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_zz_probe_on_the_real_extract.py -q
rm -f tests/test_zz_probe_on_the_real_extract.py
```
Expected: the `MEASUREMENTS THAT DID NOT RUN` banner names the probe. Before this task it stayed silent. Confirm the probe file is deleted afterwards.

- [ ] **Step 6: Run the full suite**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest tests/ -q`

Expected: `1361 passed, 11 skipped, 4 xfailed`

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_conftest_banner.py
git commit -m "fix(tests): the unmeasured-work banner was itself under-reporting

It matched _real_extract_ with delimiting underscores, so it could not see the
two tests ending ..._on_the_real_extract nor any skipif that does not follow
the naming convention -- 13 of 40 skips on a fresh clone. A guard whose entire
job is to say 'this run measured nothing' must not under-report by a third.

test_assay_hygiene_rulings.py:57 already documents the fast lane as
-k 'not real_extract' without the underscore, so the two conventions disagreed."
```

---

### Task 5: Pin the dependencies

**Files:**
- Create: `pyproject.toml`, `uv.lock`
- Test: `tests/test_dependency_pinning.py`

**Why:** Every module carries a PEP-723 header with lower bounds only (`pandas>=2.0`), and there is no `pyproject.toml`, `uv.lock` or `requirements.txt` anywhere. The pipeline was verified byte-identical across a pandas major version — that is luck, not design, and the next major bump has nothing holding it.

**Interfaces:**
- Consumes: nothing.
- Produces: a lockfile every command in the mode can resolve against.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dependency_pinning.py
"""The suite's dependencies must be pinned, not merely lower-bounded.

The pipeline reproduced byte-identically across a pandas major version. That is
luck: every PEP-723 header in scripts/assay_hygiene/ says `pandas>=2.0` and
nothing holds an upper bound or records what was actually resolved.
"""
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_a_pyproject_exists():
    assert (REPO / "pyproject.toml").is_file()


def test_a_lockfile_exists():
    assert (REPO / "uv.lock").is_file(), "run `uv lock`"


def test_the_pinned_deps_cover_what_the_scripts_import():
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    declared = " ".join(data["project"]["dependencies"])
    for package in ("pandas", "pyarrow", "openpyxl", "jinja2", "requests"):
        assert package in declared, f"{package} is imported but not declared"


def test_the_lockfile_records_a_resolved_pandas():
    text = (REPO / "uv.lock").read_text()
    assert 'name = "pandas"' in text, "pandas is not resolved in the lockfile"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_dependency_pinning.py -q`

Expected: `4 failed` — no `pyproject.toml`, no `uv.lock`.

- [ ] **Step 3: Write the minimal implementation**

```toml
# pyproject.toml
[project]
name = "dmac-curation"
version = "0.3.0"
requires-python = ">=3.11"
# Floors are what the PEP-723 headers already declared; uv.lock records what
# was actually resolved. The pipeline is verified deterministic on pandas 3,
# so the lock is the reproducibility guarantee, not these bounds.
dependencies = [
    "pandas>=2.0",
    "pyarrow>=14.0",
    "openpyxl>=3.1",
    "jinja2>=3.1",
    "requests>=2.31",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "smbprotocol>=1.10",
]

[dependency-groups]
dev = ["pytest>=8.0", "numpy>=1.26"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Generate the lockfile and run the test**

Run:
```bash
uv lock
uv run --no-project --with pytest python -m pytest tests/test_dependency_pinning.py -q
```
Expected: `4 passed`

- [ ] **Step 5: Confirm the suite still passes under the locked resolution**

Run: `uv run --group dev python -m pytest tests/ -q`

Expected: `1365 passed, 11 skipped, 4 xfailed`. If the locked resolution changes any count, stop and report the difference rather than adjusting a test — a count that moves with a dependency version is a finding.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/test_dependency_pinning.py
git commit -m "build: pin dependencies instead of lower-bounding them

Every PEP-723 header says pandas>=2.0 and nothing recorded what was actually
resolved. The pipeline reproduced byte-identically across a pandas major
version, which is luck rather than design -- the next bump has nothing holding
it. The lockfile is the reproducibility guarantee; the floors merely restate
what the headers already said."
```

---

## Self-Review

**Spec coverage.** §6.1 `chmod` by code → Task 2. §6.2 `out_dir` guard → Task 1 (the guard variant, chosen over required-`out_dir` because 20+ existing callers rely on the default and the guard catches the hazard precisely). §6.3 existence guards → Task 3. §6.4 dependency pinning → Task 5. §7's conftest banner fix → Task 4. §7's two landmines are **deliberately not in this plan**: the vacuity guard at `test_assay_hygiene_rulings.py:230` is defused by Task 1 (it only fires when the baseline is regenerated in place, which the write guard now prevents), and the strict-xfail at `:332` is a RUN2 decision about whether that measurement still applies, not a defect to fix now. §§1–5 and §8 belong to Plans 2 and 3.

**Placeholder scan.** No TBD/TODO. Every code step carries real code; every test step names the command and the expected output.

**Type consistency.** `assert_writable(out, names)` and `SymlinkWriteRefused` are used in Task 1 exactly as defined. `protect(run_dir, tiers)` / `verify(run_dir, tiers)` are used in Task 2 exactly as defined. `_MEASUREMENT_CONVENTION` stays a plain string in Task 4, matching the existing substring call site — no call-site change is implied anywhere.

**Expected suite counts** rise 1,345 → 1,350 → 1,355 → 1,357 → 1,361 → 1,365 across the five tasks, against the worktree baseline (add 2 in the main checkout). An executor seeing a different number should stop rather than adjust.
