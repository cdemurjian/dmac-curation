# Assay Hygiene Mode Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn assay hygiene from a pile of scripts into the toolkit's fourth curation mode — eight `curate-assay-*` commands over a numbered, immutable run model and a ruling store that outlives runs.

**Architecture:** Seven new modules under `scripts/assay_hygiene/`, each owning one responsibility (run state, carry-forward, ingest, backup, target resolution, write preflight, chunking), plus seven new command documents and one absorbed existing one. No detection logic changes: `run_evidence`, `run_detect`, `classify` and `gate` are called, not rewritten. The write path is additive-only and refuses on eight conditions before touching production.

**Tech Stack:** Python 3.11+, pandas, pytest. Run with `uv run --group dev python -m pytest ...` (the lockfile from prerequisites Task 5), or the ad-hoc form `uv run --no-project --with pytest --with pandas --with pyarrow --with numpy --with openpyxl --with jinja2 --with pyyaml --with requests --with python-dotenv --with smbprotocol python -m pytest ...`

**Spec:** `docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md`

**Depends on:**
- `2026-08-27-assay-hygiene-prerequisites.md` — **landed.** Provides `_writeguard.assert_writable` / `SymlinkWriteRefused` and `protect_run.protect` / `verify`, both consumed here.
- `2026-08-27-assay-hygiene-ruling-store.md` — **landed.** Provides `rulings.Ruling` / `PairKey` / `VERDICTS` / `ConflictingRulings` / `load` / `save` / `normalise_id`, and `migrate_rulings.migrate` / `title_index` / `conflicts` / `AmbiguousTitle`.

## Global Constraints

- **This repository is PUBLIC.** Never write a real sample uid, protocol identifier, or `<YYMMDD><LAB>` batch stamp into a tracked file — including into a comment. `tests/test_identifier_exposure.py` enforces this. Synthetic uids must use the reserved `19MMDD` date band (e.g. `TIS-190101ENG-901`), which is provably absent from production.
- **Cohort strings carry identifiers** — lab codes, and in at least one RUN1 case a protocol filename with a person's name. No test may hard-code a cohort key; read them from fixtures at runtime, as `tests/test_assay_hygiene_rulings.py` does. Provenance never enters git.
- **`assets/` is gitignored and stays that way.** Runs live at `assets/RUN<n>/`, the ruling store at `assets/rulings/`. Nothing under `assets/` is ever committed.
- **Never modify `assets/RUN1/`.** Every tier `00`–`06` is now `0o555`/`0o444` (prerequisites Task 2). Migration reads it. `07-process` is deliberately writable.
- **No script may register a `--dry-run` flag, and no command doc may instruct an operator to pass one.** `tests/test_curate_commands_present.py` asserts both halves. Writing is opt-in via `--confirm`; its absence is the safe default.
- **Suite baseline: measure yours before Task 1 and use that number.** On `feat/assay-hygiene-ruling-store` @ `8c90490` it is **1,426 passed / 11 skipped / 4 xfailed**.

  **Full-suite arithmetic:** expected total = baseline + tests you added + **one per new file under `scripts/`**. `tests/test_path_anchoring.py` parametrizes over every script, so each new module contributes one passing case nobody wrote. Both prior plans tripped on this. Per-file counts below are exact; derive the full-suite number with that rule rather than trusting a hard-coded total.
- The 4 xfails are intentional deliverables. Never "fix" an xfail to make it pass.
- **The invariant that matters in any checkout:** no `_real_extract_` test skips. If the skipped-measurement banner fires, the extract is unreachable and nothing below is being measured.
- Commit after every task. Do not push.

## Measured inputs

Re-derive rather than trusting these; the prior plan's headline figure was wrong because it was not re-derived.

| fact | value |
|---|---|
| RUN1 ruling rows migrated | **200** (mode2 111 + pair 45 + mode1 44) |
| distinct pair keys | **127** |
| conflicting keys | **5** |
| verdicts present | `APPROVE`, `REJECT`, `WRONG_ASSAY` — all inside `VERDICTS` |
| RUN1 tiers | `00-rulings` … `07-process`; `00`–`06` read-only |

The spec §8 predicts "261 cohort rulings and 175 pair rulings over ~479 distinct pairs". That was written before migration existed and does not match what migration actually reads. **The measured figures above supersede it.**

## File structure

| file | responsibility |
|---|---|
| `scripts/assay_hygiene/runstate.py` | the run lockfile: create, read, update, one-run-at-a-time |
| `scripts/assay_hygiene/store_backup.py` | dated tarball of the ruling store, verified by content |
| `scripts/assay_hygiene/carryforward.py` | sort cohorts three ways against the ruling store |
| `scripts/assay_hygiene/ingest.py` | join an operator-edited CSV back onto cohorts |
| `scripts/assay_hygiene/resolve_targets.py` | internal id → SEEK assay, project gate, manifest |
| `scripts/assay_hygiene/preflight.py` | the eight refusals, before any production write |
| `scripts/assay_hygiene/chunker.py` | split a payload into chunks; reconcile against the database |
| `commands/curate-assay-{init,detect,review,resolve,write,status,backup}.md` | the seven new command docs |
| `commands/curate-assay-vocabulary.md` | absorbed and fixed |
| `skills/curation/ASSAY.md` | the mode's reference doc |

---

### Task 1: The run lockfile

**Files:**
- Create: `scripts/assay_hygiene/runstate.py`
- Test: `tests/test_assay_hygiene_runstate.py`

**Why:** The mode needs to know which run is open, what step it is on, and whether another process already holds one. `scripts/_lockfile.py` establishes the `.dmac-curation.json` pattern for project-scoped modes; this mode is house-scoped and needs its own file at the runs root, not a project lockfile.

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LOCK_NAME = "assay-run.json"`
  - `RunLocked` — a `RuntimeError` subclass raised when a second run is opened.
  - `create(root: Path, run: int, extract_sha: str) -> dict` — writes the lockfile, returns it. Raises `RunLocked` if one is already open.
  - `read(root: Path) -> dict` — `{}` when absent.
  - `update(root: Path, **fields) -> dict` — merges fields into the open lockfile and rewrites it.
  - `close(root: Path) -> None` — marks the run closed so a new one may open.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_runstate.py
"""One run at a time, and a file that says which.

Two concurrent write phases could silently overwrite each other's rows: primary
keys are MAX(id)+1 computed in Python with no lock, so a second writer makes
Django's explicit-pk save() do UPDATE-then-INSERT and overwrite the first
writer's row, with both callers told they succeeded.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import runstate as S  # noqa: E402


def test_reading_an_absent_lockfile_is_empty_not_an_error(tmp_path):
    assert S.read(tmp_path) == {}


def test_create_writes_a_readable_lockfile(tmp_path):
    made = S.create(tmp_path, run=2, extract_sha="abc123")
    assert made["run"] == 2
    assert made["extract_sha"] == "abc123"
    assert S.read(tmp_path)["run"] == 2


def test_a_second_run_is_refused_while_one_is_open(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    with pytest.raises(S.RunLocked, match="2"):
        S.create(tmp_path, run=3, extract_sha="def456")


def test_a_new_run_opens_once_the_previous_is_closed(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.close(tmp_path)
    assert S.create(tmp_path, run=3, extract_sha="def456")["run"] == 3


def test_update_merges_without_dropping_existing_fields(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc123")
    S.update(tmp_path, step="review", carried_pairs=479)
    got = S.read(tmp_path)
    assert got["step"] == "review"
    assert got["carried_pairs"] == 479
    assert got["extract_sha"] == "abc123", "update must not clobber"


def test_update_on_no_open_run_refuses(tmp_path):
    with pytest.raises(S.RunLocked):
        S.update(tmp_path, step="review")


def test_a_fresh_run_records_that_nothing_is_written_yet(tmp_path):
    made = S.create(tmp_path, run=2, extract_sha="abc123")
    assert made["write"]["chunks_done"] == 0
    assert made["write"]["rollback_id"] is None
    assert made["write"]["backup_verified"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_runstate.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'assay_hygiene.runstate'`

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/runstate.py
# /// script
# requires-python = ">=3.11"
# ///
"""Which run is open, what step it is on, and whether anyone else holds one.

WHY A SECOND FILE RATHER THAN `scripts/_lockfile.py`. That one is keyed to a
project directory and its `mode()` helper assumes a project lockfile. Assay
hygiene is house-scoped -- one extract, all projects, no PI -- so its state
lives at the runs root instead.

ONE RUN AT A TIME IS A SAFETY PROPERTY, NOT TIDINESS. Primary keys in the write
path are MAX(id)+1 computed in Python with no lock. A concurrent insert makes
Django's explicit-pk save() perform UPDATE-then-INSERT and silently overwrite
the other writer's row, with both callers told they succeeded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

LOCK_NAME = "assay-run.json"
SCHEMA_VERSION = 1


class RunLocked(RuntimeError):
    """A run is already open, or none is and one was expected."""


def _path(root: Path) -> Path:
    return Path(root) / LOCK_NAME


def read(root: Path) -> dict:
    """-> the lockfile, or {} when absent. Never raises on absence."""
    path = _path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write(root: Path, data: dict) -> dict:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def create(root: Path, run: int, extract_sha: str) -> dict:
    """Open a run. Refuses while another is open."""
    current = read(root)
    if current and current.get("open"):
        raise RunLocked(
            f"run {current['run']} is still open (pid {current.get('pid')}). "
            f"Close it before opening run {run}: two concurrent write phases "
            f"can silently overwrite each other's rows.")
    return _write(root, {
        "schema_version": SCHEMA_VERSION,
        "run": run,
        "open": True,
        "pid": os.getpid(),
        "extract_sha": extract_sha,
        "step": "init",
        "rulings_ingested": {},
        "carried_from_run": None,
        "carried_pairs": 0,
        "write": {"chunks_done": 0, "rollback_id": None,
                  "backup_verified": False},
    })


def update(root: Path, **fields) -> dict:
    """Merge `fields` into the open run. Refuses when none is open."""
    current = read(root)
    if not current or not current.get("open"):
        raise RunLocked("no run is open; `curate-assay-init` opens one.")
    current.update(fields)
    return _write(root, current)


def close(root: Path) -> None:
    """Mark the run closed so another may open."""
    current = read(root)
    if not current:
        return
    current["open"] = False
    _write(root, current)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_runstate.py -q`

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/runstate.py tests/test_assay_hygiene_runstate.py
git commit -m "feat(assay-hygiene): the run lockfile

House-scoped, so it does not reuse scripts/_lockfile.py, whose mode() helper
assumes a project lockfile. One run at a time is a safety property rather than
tidiness: write-path primary keys are MAX(id)+1 computed in Python with no
lock, so a second concurrent writer makes Django's explicit-pk save() perform
UPDATE-then-INSERT and silently overwrite the first writer's row -- with both
callers told they succeeded."
```

---

### Task 2: `init` refuses to proceed without a ruling store

**Files:**
- Create: `scripts/assay_hygiene/init_run.py`
- Test: `tests/test_assay_hygiene_init_run.py`

**Why:** Spec §9: the auto-backup tarball is the recovery path, and it is only load-bearing if something checks. `init` finding no ruling store must stop with the restore command and a statement of what is at stake — no amount of compute regenerates a human ruling. Silently starting a fresh run is how a campaign's judgement gets quietly discarded.

**Interfaces:**
- Consumes: `runstate.create`, `runstate.RunLocked`.
- Produces:
  - `MissingRulingStore` — a `RuntimeError` subclass whose message names the restore command.
  - `require_store(store: Path, backups: Path) -> None` — raises unless the store exists and holds `pairs.tsv`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_init_run.py
"""A fresh run must not silently discard a campaign's judgement.

No amount of compute regenerates a human ruling. `init` finding no ruling store
stops and names the restore command; it never starts an empty run quietly.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import init_run as I  # noqa: E402


def test_an_absent_store_refuses_and_names_the_restore_path(tmp_path):
    with pytest.raises(I.MissingRulingStore) as excinfo:
        I.require_store(tmp_path / "rulings", tmp_path / "backups")
    message = str(excinfo.value)
    assert "backups" in message, "the message must say where backups live"
    assert "tar" in message, "the message must carry a runnable restore command"


def test_a_store_directory_without_pairs_is_still_missing(tmp_path):
    """An empty directory is the shape a half-finished restore leaves."""
    (tmp_path / "rulings").mkdir()
    with pytest.raises(I.MissingRulingStore):
        I.require_store(tmp_path / "rulings", tmp_path / "backups")


def test_a_populated_store_passes(tmp_path):
    store = tmp_path / "rulings"; store.mkdir()
    (store / "pairs.tsv").write_text(
        "sample_type\tinternal_assay_id\taction\tverdict\truled_on\tactor\n")
    I.require_store(store, tmp_path / "backups")   # must not raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/init_run.py
# /// script
# requires-python = ">=3.11"
# ///
"""Open a run, having first proved the campaign's judgement still exists.

WHY THIS REFUSES RATHER THAN WARNS. Keeping rulings out of a PUBLIC repository
means their only protection is a backup on one machine. That is a real,
recorded limit -- a lost machine is a lost curation campaign -- and the one
thing that makes the backup load-bearing rather than decorative is that
something checks for it before a run starts. A warning above a fresh empty run
is a warning nobody reads.
"""
from __future__ import annotations

from pathlib import Path

from .rulings import PAIRS_NAME


class MissingRulingStore(RuntimeError):
    """No ruling store. Restore it before starting a run."""


def require_store(store: Path, backups: Path) -> None:
    """Raise unless `store` holds a pairs file."""
    store, backups = Path(store), Path(backups)
    if (store / PAIRS_NAME).exists():
        return
    raise MissingRulingStore(
        f"no ruling store at {store}/{PAIRS_NAME}.\n"
        f"NOTHING REGENERATES A HUMAN RULING -- not compute, not a re-run. If "
        f"this is not the very first run, judgement is missing and the run "
        f"must not start.\n"
        f"Restore the most recent backup from {backups}:\n"
        f"  tar -xzf {backups}/<newest>.tar.gz -C {store.parent}\n"
        f"If this genuinely IS the first run, create the store by migrating an "
        f"existing run: `curate-assay-init --migrate-from assets/RUN1`.")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/init_run.py tests/test_assay_hygiene_init_run.py
git commit -m "feat(assay-hygiene): init refuses to start without a ruling store

Keeping rulings out of a public repository means their only protection is a
backup on one machine. The backup is load-bearing only if something checks, so
init stops and names the restore command rather than starting an empty run.
A warning printed above a fresh run is a warning nobody reads."
```

---

### Task 3: Create the run directory and protect its tiers

**Files:**
- Modify: `scripts/assay_hygiene/init_run.py`
- Test: `tests/test_assay_hygiene_init_run.py`

**Why:** Spec §2: runs are numbered and immutable, and `chmod a-w` is applied **in code**. Prerequisites Task 2 built `protect_run.protect`; this is the caller that makes new runs protected by construction rather than by someone remembering.

**Interfaces:**
- Consumes: `protect_run.protect`, `protect_run.verify`, `runstate.create`.
- Produces:
  - `TIERS = ("00-rulings", "01-extract", "02-agent-runs", "03-stage0-applied", "04-artifacts", "05-review", "06-findings", "07-process")`
  - `PROTECTED = TIERS[:-1]` — everything but `07-process`.
  - `next_run_number(runs_root: Path) -> int`
  - `create_run(runs_root: Path, run: int) -> Path` — makes the tier tree, returns the run directory.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_assay_hygiene_init_run.py

def test_the_next_run_number_follows_the_highest_present(tmp_path):
    (tmp_path / "RUN1").mkdir()
    (tmp_path / "RUN2").mkdir()
    assert I.next_run_number(tmp_path) == 3


def test_the_first_run_is_number_one(tmp_path):
    assert I.next_run_number(tmp_path) == 1


def test_a_stray_directory_does_not_confuse_the_numbering(tmp_path):
    (tmp_path / "RUN1").mkdir()
    (tmp_path / "rulings").mkdir()
    (tmp_path / "RUNaway").mkdir()
    assert I.next_run_number(tmp_path) == 2


def test_create_run_makes_every_tier(tmp_path):
    run = I.create_run(tmp_path, 2)
    assert run.name == "RUN2"
    for tier in I.TIERS:
        assert (run / tier).is_dir(), f"{tier} missing"


def test_a_created_run_is_protected_except_the_process_tier(tmp_path):
    """07-process holds the workspace a later run appends to."""
    from assay_hygiene.protect_run import verify
    run = I.create_run(tmp_path, 2)
    assert verify(run, I.PROTECTED) == []
    assert verify(run, ["07-process"]) == [run / "07-process"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: `5 failed` — `AttributeError: module 'assay_hygiene.init_run' has no attribute 'next_run_number'` and the same for `create_run` / `TIERS` / `PROTECTED`.

- [ ] **Step 3: Write the minimal implementation**

Add to `scripts/assay_hygiene/init_run.py`:

```python
import re

from .protect_run import protect

TIERS = ("00-rulings", "01-extract", "02-agent-runs", "03-stage0-applied",
         "04-artifacts", "05-review", "06-findings", "07-process")
PROTECTED = TIERS[:-1]

_RUN_DIR = re.compile(r"^RUN(\d+)$")


def next_run_number(runs_root: Path) -> int:
    """-> one past the highest RUN<n> present. A fresh tree starts at 1."""
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return 1
    found = [int(m.group(1)) for m in
             (_RUN_DIR.match(p.name) for p in runs_root.iterdir() if p.is_dir())
             if m]
    return max(found, default=0) + 1


def create_run(runs_root: Path, run: int) -> Path:
    """Make RUN<n> with every tier, then protect all but `07-process`.

    PROTECTION IS APPLIED AT CREATION, not at the end of a run. A tier that is
    writable for the duration of the run is a tier the run can destroy, and the
    artifacts most worth protecting are written early.
    """
    base = Path(runs_root) / f"RUN{run}"
    for tier in TIERS:
        (base / tier).mkdir(parents=True, exist_ok=True)
    protect(base, PROTECTED)
    return base
```

**Note on ordering:** `protect` is applied immediately, so anything the run writes into `01-extract` or `04-artifacts` must be written *before* `create_run` protects them, or written through an explicit unprotect/reprotect. Task 4 does the former: it stages content and protects afterwards. If a later command needs to add to a protected tier it must call `protect_run.protect` again after writing, never leave the tier writable.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/init_run.py tests/test_assay_hygiene_init_run.py
git commit -m "feat(assay-hygiene): create numbered runs with protected tiers

Spec section 2: runs are numbered and immutable and the chmod is applied in
code. Four files asserted that protection and none performed it; protect_run
made it real and this is the caller that makes new runs protected by
construction rather than by someone remembering.

Applied at creation rather than at the end of a run: a tier writable for the
duration is a tier the run can destroy, and the artifacts most worth
protecting are written early. 07-process stays writable by design."
```

---

### Task 4: Migrate RUN1 into the store on first init

**Files:**
- Modify: `scripts/assay_hygiene/init_run.py`
- Test: `tests/test_assay_hygiene_init_run.py`

**Why:** Spec §8. The store is empty until RUN1's judgement is moved into it, and that migration is one-time. Plan 2 built `migrate` and `conflicts`; this wires them to `rulings.save` and decides what happens to the 5 conflicting keys — they are **excluded from the store and reported**, never resolved.

**Interfaces:**
- Consumes: `migrate_rulings.migrate`, `migrate_rulings.conflicts`, `rulings.save`, `rulings.Ruling`.
- Produces:
  - `migrate_into_store(run_dir: Path, assays: pd.DataFrame, store: Path) -> dict` — returns `{"written": int, "conflicts": list[dict], "provenance": list[dict]}`. Writes only non-conflicting keys.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_assay_hygiene_init_run.py
#
# NOTE: this test needs pandas. The file's existing tests do not; that is fine,
# the import is module-level and the whole file runs under the pandas env.

import pandas as pd  # add to the imports at the top of the file


def _assays():
    return pd.DataFrame({
        "assay_id": [1, 2],
        "internal_assay_id": [74.0, 130.0],
        "internal_assay_title": ["Tissue Collection", "Mass Spectrometry"],
    })


def _run_with(tmp_path, rows):
    run = tmp_path / "RUN1" / "00-rulings"
    run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        + rows)
    return tmp_path / "RUN1"


def test_a_clean_migration_writes_every_key(tmp_path):
    run = _run_with(tmp_path,
                    "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 1
    assert got["conflicts"] == []


def test_a_conflicting_key_is_EXCLUDED_and_reported(tmp_path):
    """The store must not contain a key the operator ruled two ways."""
    run = _run_with(
        tmp_path,
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n"
        "OTH\tTIS\tXXX\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tREJECT\t\n")
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 0, "a conflicting key must not be written"
    assert len(got["conflicts"]) == 1
    assert got["conflicts"][0]["key"] == ("TIS", "74", "ADD_PARENT_TO_ASSAY")


def test_a_conflict_does_not_block_the_keys_that_agree(tmp_path):
    run = _run_with(
        tmp_path,
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n"
        "OTH\tTIS\tXXX\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tREJECT\t\n"
        "ENG\tMUS\tPAV\tMass Spectrometry\t(lineage)\tADD_CHILD_TO_ASSAY\tAPPROVE\t\n")
    got = I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    assert got["written"] == 1, "the agreeing key must still land"
    assert len(got["conflicts"]) == 1


def test_the_written_store_reads_back_through_rulings_load(tmp_path):
    from assay_hygiene.rulings import load
    run = _run_with(tmp_path,
                    "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    I.migrate_into_store(run, _assays(), tmp_path / "rulings")
    store = load(tmp_path / "rulings")
    assert store[("TIS", "74", "ADD_PARENT_TO_ASSAY")].verdict == "APPROVE"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: `4 failed` — `AttributeError: ... has no attribute 'migrate_into_store'`

- [ ] **Step 3: Write the minimal implementation**

Add to `scripts/assay_hygiene/init_run.py`:

```python
import pandas as pd

from .migrate_rulings import conflicts, migrate
from .rulings import save


def migrate_into_store(run_dir: Path, assays: pd.DataFrame,
                       store: Path) -> dict:
    """Move a completed run's judgement into the durable store.

    CONFLICTING KEYS ARE EXCLUDED, NOT RESOLVED. Measured on RUN1, 200 ruled
    rows collapse to 127 pair keys and 5 disagree. `rulings.save` refuses the
    whole batch if a conflict reaches it, so they are filtered here and
    returned for the operator to rule directly. Writing one of the two verdicts
    -- by recency, by majority, by source precedence -- silently overwrites a
    human decision with a guess.
    """
    found, prov = migrate(run_dir, assays)
    clashing = conflicts(found)
    blocked = {record["key"] for record in clashing}
    clean = [r for r in found if r.key not in blocked]
    written = save(store, clean) if clean else 0
    return {"written": written, "conflicts": clashing, "provenance": prov}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_init_run.py -q`

Expected: `12 passed`

- [ ] **Step 5: Migrate the real RUN1 and record the result**

Run:
```bash
uv run --no-project --with pandas --with pyarrow python -c "
import sys; sys.path.insert(0,'scripts')
import pandas as pd
from pathlib import Path
from assay_hygiene.init_run import migrate_into_store
a = pd.read_parquet('assets/RUN1/01-extract/assays.parquet')
got = migrate_into_store(Path('assets/RUN1'), a, Path('assets/rulings'))
print('written  :', got['written'])
print('conflicts:', len(got['conflicts']))
for c in got['conflicts']: print('  ', c['key'], c['verdicts'])
"
```
Expected: `written: 122`, `conflicts: 5` (127 keys less the 5 excluded). **Do not resolve the conflicts.** Report the five keys to the operator; each needs a direct pair ruling. If the numbers differ, re-derive before proceeding — do not adjust a test to match.

This writes `assets/rulings/pairs.tsv`, which is gitignored.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/init_run.py tests/test_assay_hygiene_init_run.py
git commit -m "feat(assay-hygiene): migrate a completed run's judgement into the store

Spec section 8, one-time. Plan 2 built migrate() and conflicts(); this wires
them to rulings.save and decides what a conflicting key does: it is EXCLUDED
from the store and reported, never resolved.

save() refuses the whole batch if a conflict reaches it, so conflicts are
filtered here rather than allowed to block the 122 keys that agree. Choosing
one of two verdicts by recency, majority or source precedence would silently
overwrite a human decision with a guess."
```

---

### Task 5: Back the ruling store up, and verify the tarball

**Files:**
- Create: `scripts/assay_hygiene/store_backup.py`
- Test: `tests/test_assay_hygiene_store_backup.py`

**Why:** Spec §3: backup is automatic on ingest, not a command someone remembers. And spec §5's first principle — verify the artifact, never the exit code — applies directly: `mysqldump` exited 0 having written 0 bytes on 2026-08-27, caught only by an `ls`. A backup function that returns a path without reading it back is the same defect.

**Interfaces:**
- Consumes: `rulings.PAIRS_NAME`.
- Produces:
  - `BackupUnverified` — a `RuntimeError` subclass.
  - `back_up(store: Path, backups: Path, stamp: str) -> Path` — writes `<backups>/rulings-<stamp>.tar.gz`, verifies it lists the store's files, returns the path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_store_backup.py
"""A backup that is not read back is not a backup.

On 2026-08-27 a mysqldump exited 0 having written 0 bytes; only an `ls` caught
it. `back_up` therefore opens the archive it just wrote and asserts the store's
files are inside, rather than trusting that tar returned cleanly.
"""
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import store_backup as B  # noqa: E402


def _store(tmp_path):
    store = tmp_path / "rulings"
    (store / "provenance").mkdir(parents=True)
    (store / "pairs.tsv").write_text(
        "sample_type\tinternal_assay_id\taction\tverdict\truled_on\tactor\n"
        "TIS\t74\tADD_TO_ASSAY\tAPPROVE\t2026-08-20\toperator\n")
    (store / "provenance" / "run1.jsonl").write_text('{"key": "x"}\n')
    return store


def test_a_backup_is_written_where_asked(tmp_path):
    made = B.back_up(_store(tmp_path), tmp_path / "backups", "20260827-1200")
    assert made.exists()
    assert made.name == "rulings-20260827-1200.tar.gz"


def test_the_backup_actually_contains_the_pairs_file(tmp_path):
    made = B.back_up(_store(tmp_path), tmp_path / "backups", "20260827-1200")
    with tarfile.open(made) as archive:
        names = archive.getnames()
    assert any(n.endswith("pairs.tsv") for n in names), names


def test_the_backup_round_trips_byte_identical(tmp_path):
    store = _store(tmp_path)
    original = (store / "pairs.tsv").read_bytes()
    made = B.back_up(store, tmp_path / "backups", "20260827-1200")
    out = tmp_path / "restored"; out.mkdir()
    with tarfile.open(made) as archive:
        archive.extractall(out, filter="data")
    restored = next(out.rglob("pairs.tsv"))
    assert restored.read_bytes() == original


def test_backing_up_an_absent_store_refuses(tmp_path):
    """An empty archive that reports success is the failure mode being stopped."""
    with pytest.raises(B.BackupUnverified, match="nothing to back up"):
        B.back_up(tmp_path / "gone", tmp_path / "backups", "20260827-1200")


def test_two_backups_on_the_same_day_do_not_collide(tmp_path):
    store = _store(tmp_path)
    a = B.back_up(store, tmp_path / "backups", "20260827-1200")
    b = B.back_up(store, tmp_path / "backups", "20260827-1830")
    assert a != b and a.exists() and b.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_store_backup.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/store_backup.py
# /// script
# requires-python = ">=3.11"
# ///
"""A dated tarball of the ruling store, verified by reading it back.

WHY VERIFICATION IS PART OF THE FUNCTION. On 2026-08-27 a backup command exited
0 having written a 0-byte file, and only a sanity `ls` caught it. An exit code
describes the call; the archive describes the backup. This opens what it wrote
and asserts the store's files are inside before returning a path anyone treats
as a recovery point.

The stamp is passed in rather than read from the clock so the caller controls
naming and the function stays testable.
"""
from __future__ import annotations

import tarfile
from pathlib import Path

from .rulings import PAIRS_NAME


class BackupUnverified(RuntimeError):
    """The archive does not contain what it was supposed to preserve."""


def back_up(store: Path, backups: Path, stamp: str) -> Path:
    """Write `<backups>/rulings-<stamp>.tar.gz` and prove it holds the store."""
    store, backups = Path(store), Path(backups)
    if not (store / PAIRS_NAME).exists():
        raise BackupUnverified(
            f"nothing to back up: {store / PAIRS_NAME} does not exist. An "
            f"archive of an absent store is an empty file that reports "
            f"success, which is worse than no backup at all.")

    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"rulings-{stamp}.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        archive.add(store, arcname=store.name)

    with tarfile.open(target) as archive:
        names = archive.getnames()
    if not any(n.endswith(PAIRS_NAME) for n in names):
        raise BackupUnverified(
            f"{target} was written but does not contain {PAIRS_NAME}; "
            f"it holds {names}")
    return target
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_store_backup.py -q`

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/store_backup.py tests/test_assay_hygiene_store_backup.py
git commit -m "feat(assay-hygiene): back the ruling store up, and read the archive back

Spec section 3: backup is automatic on ingest, not a command someone
remembers. Verification is part of the function because an exit code describes
the call and the archive describes the backup -- on 2026-08-27 a backup
command exited 0 having written a 0-byte file, caught only by a sanity ls.

Backing up an absent store refuses rather than producing an empty archive that
reports success."
```

---

### Task 6: The carry-forward three-way split

**Files:**
- Create: `scripts/assay_hygiene/carryforward.py`
- Test: `tests/test_assay_hygiene_carryforward.py`

**Why:** Spec §4. This is the deferred heart of the design and the one place a naive implementation silently registers rows nobody approved. In RUN1, 2,830 rows shared a cohort key with an approved cohort but sat below the precedent floor the operator's sheet was built at — he never saw them. A carry-forward that matches on the pair alone registers all of them.

**Interfaces:**
- Consumes: `rulings.load`, `rulings.Ruling`, `rulings.PairKey`, `rulings.normalise_id`.
- Produces:
  - `CARRIED`, `WIDENED`, `UNSEEN` — the three bucket names as string constants.
  - `Cohort` — frozen dataclass: `key: PairKey`, `n_rows: int`, `cohort_id: str`.
  - `split(cohorts: Iterable[Cohort], store: dict[PairKey, Ruling], ruled_width: dict[PairKey, int]) -> dict[str, list[Cohort]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_carryforward.py
"""Three buckets, and why the middle one exists.

A pair ruling carries forward only while the new cohort is no wider than the
one it was made against. In RUN1, 2,830 rows shared a cohort key with an
approved cohort but sat below the precedent floor the operator's sheet was
built at, so he never saw them. Matching on the pair alone registers all of
them silently; that is what this splits apart.

NO REAL COHORT KEY APPEARS HERE. Keys are synthetic.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import carryforward as C  # noqa: E402
from assay_hygiene.rulings import Ruling  # noqa: E402

KEY = ("TIS", "74", "ADD_TO_ASSAY")
OTHER = ("MUS", "87", "ADD_PARENT_TO_ASSAY")


def _store(*keys):
    return {k: Ruling(k, "APPROVE", "2026-08-20", "operator") for k in keys}


def test_a_pair_never_ruled_is_unseen():
    got = C.split([C.Cohort(KEY, 10, "c1")], {}, {})
    assert [c.cohort_id for c in got[C.UNSEEN]] == ["c1"]
    assert got[C.CARRIED] == [] and got[C.WIDENED] == []


def test_a_pair_ruled_at_the_same_width_is_carried():
    got = C.split([C.Cohort(KEY, 10, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.CARRIED]] == ["c1"]


def test_a_pair_ruled_against_MORE_rows_is_carried():
    """Narrower than what was ruled is covered by that ruling."""
    got = C.split([C.Cohort(KEY, 4, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.CARRIED]] == ["c1"]


def test_a_pair_ruled_against_FEWER_rows_is_widened_not_carried():
    """RUN1's trap: the ruling exists but never covered these rows."""
    got = C.split([C.Cohort(KEY, 900, "c1")], _store(KEY), {KEY: 10})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["c1"]
    assert got[C.CARRIED] == [], "a widened cohort must never auto-apply"


def test_a_widened_cohort_with_no_recorded_width_is_widened_not_carried():
    """An unknown width is not evidence of coverage."""
    got = C.split([C.Cohort(KEY, 900, "c1")], _store(KEY), {})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["c1"]


def test_every_cohort_lands_in_exactly_one_bucket():
    cohorts = [C.Cohort(KEY, 4, "carried"),
               C.Cohort(OTHER, 900, "widened"),
               C.Cohort(("X", "1", "ADD_TO_ASSAY"), 5, "unseen")]
    got = C.split(cohorts, _store(KEY, OTHER), {KEY: 10, OTHER: 10})
    landed = [c.cohort_id for bucket in got.values() for c in bucket]
    assert sorted(landed) == ["carried", "unseen", "widened"]
    assert len(landed) == len(set(landed)), "a cohort was double-counted"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_carryforward.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/carryforward.py
# /// script
# requires-python = ">=3.11"
# ///
"""Sort this run's cohorts against the rulings of every run before it.

THE MIDDLE BUCKET IS THE WHOLE POINT. A pair ruling is coarser than the cohort
it was made against, so "the operator approved this pair" and "the operator
approved a narrow slice of this pair and we widened it" are different facts. In
RUN1, 2,830 rows shared a cohort key with an approved cohort but sat below the
precedent floor the operator's sheet was built at; he never saw them. A
carry-forward matching on the pair alone registers every one of them silently.

AN UNKNOWN RULED WIDTH IS TREATED AS WIDENED, NOT CARRIED. Absence of evidence
that the ruling covered these rows is not evidence that it did, and the cost of
the two mistakes is not symmetric: a needless re-confirmation costs the
operator a line, an unearned carry-forward writes to production.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .rulings import PairKey, Ruling

CARRIED = "already_ruled"
WIDENED = "ruled_in_a_narrower_context"
UNSEEN = "never_seen"


@dataclass(frozen=True)
class Cohort:
    key: PairKey
    n_rows: int
    cohort_id: str


def split(cohorts: Iterable[Cohort],
          store: dict[PairKey, Ruling],
          ruled_width: dict[PairKey, int]) -> dict[str, list[Cohort]]:
    """-> {bucket: cohorts}. Every cohort lands in exactly one bucket."""
    out: dict[str, list[Cohort]] = {CARRIED: [], WIDENED: [], UNSEEN: []}
    for cohort in cohorts:
        if cohort.key not in store:
            out[UNSEEN].append(cohort)
            continue
        was = ruled_width.get(cohort.key)
        if was is not None and cohort.n_rows <= was:
            out[CARRIED].append(cohort)
        else:
            out[WIDENED].append(cohort)
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_carryforward.py -q`

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/carryforward.py tests/test_assay_hygiene_carryforward.py
git commit -m "feat(assay-hygiene): the carry-forward three-way split

Spec section 4. A pair ruling carries forward only while the new cohort is no
wider than the one it was made against. In RUN1, 2,830 rows shared a cohort key
with an approved cohort but sat below the precedent floor the operator's sheet
was built at, so he never saw them -- a carry-forward matching on the pair
alone registers every one silently.

An unknown ruled width counts as widened, not carried. Absence of evidence that
a ruling covered these rows is not evidence that it did, and the two mistakes
do not cost the same: a needless re-confirmation costs a line, an unearned
carry-forward writes to production."
```

---

### Task 7: The ingest join

**Files:**
- Create: `scripts/assay_hygiene/ingest.py`
- Test: `tests/test_assay_hygiene_ingest.py`

**Why:** Spec §9 names this "the one place RUN1 was hand-assembled, and it is where a mistake registers rows nobody approved". It specifies four properties, each of which is a test below.

**Interfaces:**
- Consumes: `rulings.VERDICTS`, `rulings.Ruling`, `rulings.PairKey`.
- Produces:
  - `IngestRefused` — a `ValueError` subclass.
  - `ingest(edited: pd.DataFrame, cohorts: dict[str, PairKey], ruled_on: str, actor: str = "operator") -> list[Ruling]` — `edited` carries `cohort_key` and `ruling` columns; `cohorts` maps the emitted cohort key to its pair key.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_ingest.py
"""Joining an operator-edited CSV back onto the cohorts it was built from.

Spec section 9's four required properties, one test each. This is the one place
RUN1 was hand-assembled and it is where a mistake registers rows nobody
approved.

NO REAL COHORT KEY APPEARS HERE. Keys are synthetic.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import ingest as G  # noqa: E402

COHORTS = {"cohort-a": ("TIS", "74", "ADD_TO_ASSAY"),
           "cohort-b": ("MUS", "87", "ADD_PARENT_TO_ASSAY")}


def _edited(rows):
    return pd.DataFrame(rows, columns=["cohort_key", "ruling"])


def test_a_ruled_row_becomes_a_ruling():
    got = G.ingest(_edited([["cohort-a", "APPROVE"]]), COHORTS, "2026-09-01")
    assert len(got) == 1
    assert got[0].key == ("TIS", "74", "ADD_TO_ASSAY")
    assert got[0].verdict == "APPROVE"
    assert got[0].ruled_on == "2026-09-01"


def test_a_blank_ruling_is_skipped_not_defaulted():
    """An unruled row is not a rejection."""
    assert G.ingest(_edited([["cohort-a", ""]]), COHORTS, "2026-09-01") == []


def test_a_row_matching_NO_cohort_refuses_the_whole_file():
    """Property 1: a partial match is never resolved by a rule."""
    with pytest.raises(G.IngestRefused, match="cohort-zzz"):
        G.ingest(_edited([["cohort-a", "APPROVE"],
                          ["cohort-zzz", "APPROVE"]]), COHORTS, "2026-09-01")


def test_a_verdict_outside_the_vocabulary_refuses():
    """Property 2: refuse rather than default."""
    with pytest.raises(G.IngestRefused, match="probably fine"):
        G.ingest(_edited([["cohort-a", "probably fine"]]), COHORTS, "2026-09-01")


def test_ingesting_the_same_file_twice_is_a_no_op():
    """Property 3: idempotent, not a duplicate ruling."""
    edited = _edited([["cohort-a", "APPROVE"]])
    once = G.ingest(edited, COHORTS, "2026-09-01")
    twice = G.ingest(edited, COHORTS, "2026-09-01")
    assert once == twice
    assert len({r.key for r in once + twice}) == 1


def test_the_same_cohort_ruled_twice_in_ONE_file_refuses_if_it_disagrees():
    with pytest.raises(G.IngestRefused, match="cohort-a"):
        G.ingest(_edited([["cohort-a", "APPROVE"],
                          ["cohort-a", "REJECT"]]), COHORTS, "2026-09-01")


def test_a_missing_cohort_key_column_refuses():
    """Property 4: the key is the one the surface emitted, never rebuilt."""
    with pytest.raises(G.IngestRefused, match="cohort_key"):
        G.ingest(pd.DataFrame([{"key": "cohort-a", "ruling": "APPROVE"}]),
                 COHORTS, "2026-09-01")


def test_whitespace_around_a_verdict_does_not_defeat_the_vocabulary():
    got = G.ingest(_edited([["cohort-a", " APPROVE "]]), COHORTS, "2026-09-01")
    assert got[0].verdict == "APPROVE"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_ingest.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/ingest.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Join an operator-edited CSV back onto the cohorts it was built from.

THIS IS THE ONE PLACE RUN1 WAS HAND-ASSEMBLED, and it is where a mistake
registers rows nobody approved. Four properties, all from spec section 9:

  1. every ingested row matches exactly one cohort, or the ingest REFUSES --
     a partial match is never resolved by a rule
  2. a verdict outside the vocabulary refuses rather than defaults
  3. ingesting the same file twice is a no-op, not a duplicate ruling
  4. the cohort key is the one the review surface EMITTED, looked up in the
     map it emitted -- never reconstructed here, because a second definition
     of the key is one edit away from disagreeing with the first

REFUSAL IS WHOLE-FILE, NOT PER-ROW. A file with one unmatched row is a file
built against different cohorts, and ingesting the rows that happen to match
would file a subset of the operator's judgement while reporting success.
"""
from __future__ import annotations

import pandas as pd

from .rulings import PairKey, Ruling, VERDICTS

KEY_COLUMN = "cohort_key"
RULING_COLUMN = "ruling"


class IngestRefused(ValueError):
    """The edited sheet does not join cleanly onto the cohorts it came from."""


def ingest(edited: pd.DataFrame, cohorts: dict[str, PairKey],
           ruled_on: str, actor: str = "operator") -> list[Ruling]:
    """-> the rulings this sheet carries, or raise."""
    for column in (KEY_COLUMN, RULING_COLUMN):
        if column not in edited.columns:
            raise IngestRefused(
                f"the sheet has no {column!r} column; it carries "
                f"{list(edited.columns)}. This must be the file the review "
                f"surface emitted, not one rebuilt by hand.")

    seen: dict[PairKey, str] = {}
    out: list[Ruling] = []
    for row in edited.itertuples():
        key = str(getattr(row, KEY_COLUMN)).strip()
        verdict = str(getattr(row, RULING_COLUMN)).strip()
        if not verdict or verdict.lower() == "nan":
            continue
        if key not in cohorts:
            raise IngestRefused(
                f"{key!r} matches no cohort in this run. The sheet was built "
                f"against a different set; ingesting only the rows that match "
                f"would file part of your judgement and report success.")
        if verdict not in VERDICTS:
            raise IngestRefused(
                f"verdict {verdict!r} on {key!r} is not one of "
                f"{list(VERDICTS)}. A typo must refuse rather than default.")
        pair = cohorts[key]
        if pair in seen and seen[pair] != verdict:
            raise IngestRefused(
                f"{key!r} is ruled both {seen[pair]} and {verdict} in this "
                f"one file. That is a disagreement to settle before ingest, "
                f"not something to resolve by row order.")
        if pair in seen:
            continue
        seen[pair] = verdict
        out.append(Ruling(pair, verdict, ruled_on, actor))
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_ingest.py -q`

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/ingest.py tests/test_assay_hygiene_ingest.py
git commit -m "feat(assay-hygiene): the tested ingest join

Spec section 9's four properties, one test each. This is the one place RUN1 was
hand-assembled and it is where a mistake registers rows nobody approved.

Refusal is whole-file rather than per-row: a file with one unmatched row was
built against different cohorts, and ingesting the rows that happen to match
would file a subset of the operator's judgement while reporting success. The
cohort key is looked up in the map the review surface emitted, never rebuilt
here -- a second definition of the key is one edit from disagreeing with the
first."
```

---

### Task 8: Resolve SEEK targets behind a project gate

**Files:**
- Create: `scripts/assay_hygiene/resolve_targets.py`
- Test: `tests/test_assay_hygiene_resolve_targets.py`

**Why:** Spec §5: "Project consistency is a hard gate." SEEK assay ids are per-project; a registration must land on the assay belonging to the *sample's own* project. The 2026-08-26 audit found 578 of 26,188 rows targeting another project's assay — 159 repairable, 419 not. This is unrecoverable once written: the sample joins a project it does not belong to.

**Interfaces:**
- Consumes: `rulings.normalise_id`.
- Produces:
  - `CrossProjectTarget` — a `ValueError` subclass.
  - `resolve(rows: pd.DataFrame, assays: pd.DataFrame, samples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]` — returns `(manifest, excluded)`. `rows` carries `sample_id` and `internal_assay_id`; `assays` carries `assay_id`, `internal_assay_id`, `project_id`; `samples` carries `sample_id` and `project_ids` (a list). The manifest gains `write_target_seek_assay_id` and `project_ok`, and **every manifest row has `project_ok` true**.
  - `assert_subset(sheet: pd.DataFrame, manifest: pd.DataFrame) -> None` — raises `CrossProjectTarget` if the sheet carries a `(sample_id, assay_id)` pair the manifest does not.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_resolve_targets.py
"""SEEK assay ids are per-project, and a wrong one is unrecoverable.

The 2026-08-26 audit found 578 of 26,188 rows targeting an assay in a different
project than the sample. Once written, the sample joins a project it does not
belong to and nothing undoes that from the outside.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import resolve_targets as T  # noqa: E402


@pytest.fixture
def assays():
    # internal assay 74 exists in project 1 (as seek 501) and project 2 (as 502)
    return pd.DataFrame({
        "assay_id": [501, 502, 503],
        "internal_assay_id": [74.0, 74.0, 99.0],
        "project_id": [1, 2, 1],
    })


@pytest.fixture
def samples():
    return pd.DataFrame({
        "sample_id": [10, 20, 30],
        "project_ids": [[1], [2], []],
    })


def test_a_sample_resolves_to_its_OWN_projects_assay(assays, samples):
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501]
    assert excluded.empty


def test_the_same_internal_id_resolves_DIFFERENTLY_per_project(assays, samples):
    rows = pd.DataFrame({"sample_id": [10, 20], "internal_assay_id": [74, 74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501, 502]


def test_a_sample_with_no_project_is_excluded_not_guessed(assays, samples):
    """374 RUN1 rows were in this state. No correct target exists."""
    rows = pd.DataFrame({"sample_id": [30], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.empty
    assert excluded.reason.tolist() == ["sample belongs to no project"]


def test_a_project_with_no_such_assay_is_excluded(assays, samples):
    """45 RUN1 rows were in this state."""
    rows = pd.DataFrame({"sample_id": [20], "internal_assay_id": [99]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert manifest.empty
    assert excluded.reason.tolist() == ["no assay with that internal id in the sample's project"]


def test_every_manifest_row_is_project_ok(assays, samples):
    rows = pd.DataFrame({"sample_id": [10, 20, 30], "internal_assay_id": [74, 74, 74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.project_ok.all()


def test_assert_subset_passes_for_a_sheet_built_from_the_manifest(assays, samples):
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    sheet = manifest[["sample_id", "write_target_seek_assay_id"]].rename(
        columns={"write_target_seek_assay_id": "assay_id"})
    T.assert_subset(sheet, manifest)          # must not raise


def test_assert_subset_refuses_an_INJECTED_cross_project_row(assays, samples):
    """Proven by injection, as the spec requires."""
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [502]})   # other project
    with pytest.raises(T.CrossProjectTarget, match="502"):
        T.assert_subset(sheet, manifest)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_resolve_targets.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/resolve_targets.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Turn an internal assay id into the SEEK assay of the sample's own project.

WHY THIS IS A HARD GATE. SEEK assay ids are per-project: the same internal
assay exists as a different `assay_id` in every project that runs it. A
registration that lands on another project's assay puts the sample into a
project it does not belong to, and nothing undoes that from the outside. The
2026-08-26 audit found 578 of 26,188 rows in exactly that state, every one
produced by a rule that resolved through a lineage neighbour without checking
the neighbour lived in the same project. 159 were repairable, 419 were not.

THE CHECK CANNOT BE MADE FROM THE WORKBOOK. It needs each sample's project set
and each assay's project, so `resolve` emits a manifest gate-checked at build
time and `assert_subset` is what `write` uses to prove the sheet never grew a
row the gate did not see.

EXCLUSION IS NOT REJECTION. A dropped row is an authorised registration with no
correct target, and it is reported as such rather than silently discarded.
"""
from __future__ import annotations

import pandas as pd

from .rulings import normalise_id

TARGET_COLUMN = "write_target_seek_assay_id"
NO_PROJECT = "sample belongs to no project"
NO_CANDIDATE = "no assay with that internal id in the sample's project"


class CrossProjectTarget(ValueError):
    """A row targets an assay outside the sample's own project."""


def resolve(rows: pd.DataFrame, assays: pd.DataFrame,
            samples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (manifest, excluded). Every manifest row is project-consistent."""
    by_project: dict[tuple[str, int], int] = {}
    for a in assays.itertuples():
        by_project[(normalise_id(a.internal_assay_id), int(a.project_id))] = int(a.assay_id)

    projects = {int(s.sample_id): list(s.project_ids)
                for s in samples.itertuples()}

    kept, dropped = [], []
    for row in rows.itertuples():
        sample_id = int(row.sample_id)
        internal = normalise_id(row.internal_assay_id)
        owned = projects.get(sample_id) or []
        if not owned:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_PROJECT})
            continue
        target = next((by_project[(internal, int(p))] for p in owned
                       if (internal, int(p)) in by_project), None)
        if target is None:
            dropped.append({"sample_id": sample_id,
                            "internal_assay_id": internal,
                            "reason": NO_CANDIDATE})
            continue
        kept.append({"sample_id": sample_id, "internal_assay_id": internal,
                     TARGET_COLUMN: target, "project_ok": True})

    manifest = pd.DataFrame(
        kept, columns=["sample_id", "internal_assay_id", TARGET_COLUMN,
                       "project_ok"])
    excluded = pd.DataFrame(
        dropped, columns=["sample_id", "internal_assay_id", "reason"])
    return manifest, excluded


def assert_subset(sheet: pd.DataFrame, manifest: pd.DataFrame) -> None:
    """Raise unless every (sample, assay) pair in `sheet` is in `manifest`."""
    allowed = {(int(r.sample_id), int(getattr(r, TARGET_COLUMN)))
               for r in manifest.itertuples()}
    strays = [(int(r.sample_id), int(r.assay_id)) for r in sheet.itertuples()
              if (int(r.sample_id), int(r.assay_id)) not in allowed]
    if strays:
        raise CrossProjectTarget(
            f"{len(strays)} row(s) target an assay the project gate never "
            f"approved, e.g. {strays[:5]}. The sheet must be a subset of the "
            f"manifest; a row that is not was never project-checked.")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_resolve_targets.py -q`

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/resolve_targets.py tests/test_assay_hygiene_resolve_targets.py
git commit -m "feat(assay-hygiene): resolve SEEK targets behind a hard project gate

SEEK assay ids are per-project: the same internal assay is a different assay_id
in every project that runs it. A registration landing on another project's
assay puts the sample into a project it does not belong to, and nothing undoes
that from the outside. The 2026-08-26 audit found 578 of 26,188 rows in exactly
that state; 159 were repairable, 419 were not.

The check cannot be made from the workbook, so resolve emits a manifest
gate-checked at build time and assert_subset proves the sheet never grew a row
the gate did not see. Exclusion is reported, not silent: a dropped row is an
authorised registration with no correct target."
```

---

### Task 9: The eight write refusals

**Files:**
- Create: `scripts/assay_hygiene/preflight.py`
- Test: `tests/test_assay_hygiene_preflight.py`

**Why:** Spec §5's table, one refusal per row. Each is a live failure mode of the SEEK upload endpoint, not a hypothetical. This runs before a single row reaches production.

**Interfaces:**
- Consumes: `resolve_targets.assert_subset`, `resolve_targets.CrossProjectTarget`.
- Produces:
  - `PreflightRefused` — a `RuntimeError` subclass.
  - `CHUNK_CAP = 2000`
  - `check(sheet: pd.DataFrame, manifest: pd.DataFrame, sheet_names: Iterable[str], backup: dict, rollback_id: int | None) -> None` — raises on the first condition that fails, naming it. `backup` is `{"size": int, "trailer_ok": bool}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_preflight.py
"""The eight refusals from spec section 5, one test each.

Every one is a live failure mode of /seek/sampleupload/, not a hypothesis.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import preflight as P  # noqa: E402

GOOD_BACKUP = {"size": 17_000_000, "trailer_ok": True}


def _sheet(**over):
    base = {"sample_id": [10], "assay_id": [501],
            "uid": ["TIS-190101ENG-901"],
            "current_pair": [""], "new_pair": ["10:501"]}
    base.update(over)
    return pd.DataFrame(base)


def _manifest():
    return pd.DataFrame({"sample_id": [10],
                         "write_target_seek_assay_id": [501],
                         "project_ok": [True]})


def test_a_clean_sheet_passes():
    P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_current_pair_of_two_ints_is_refused():
    """The sole combination that reaches deleteOneRecord."""
    with pytest.raises(P.PreflightRefused, match="delete"):
        P.check(_sheet(current_pair=["10:501"]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_an_unparseable_new_pair_is_refused():
    """Silently drops the registration and reports success."""
    with pytest.raises(P.PreflightRefused, match="New pair"):
        P.check(_sheet(new_pair=["not-a-pair"]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_blank_uid_is_refused():
    """getSampleID returns None; None > 0 raises; 500s mid-run."""
    with pytest.raises(P.PreflightRefused, match="uid"):
        P.check(_sheet(uid=["   "]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_a_sheet_named_UPDATE_anywhere_is_refused():
    """Hijacks dispatch into the metadata-update path, tested first."""
    with pytest.raises(P.PreflightRefused, match="UPDATE"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY", "UPDATE"],
                GOOD_BACKUP, 414935)


def test_a_row_absent_from_the_manifest_is_refused():
    with pytest.raises(P.PreflightRefused, match="manifest"):
        P.check(_sheet(assay_id=[999]), _manifest(),
                ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)


def test_no_rollback_handle_is_refused():
    with pytest.raises(P.PreflightRefused, match="rollback"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"], GOOD_BACKUP, None)


def test_an_unverified_backup_is_refused():
    """Non-zero size AND a Dump completed trailer. A 0-byte file exited 0."""
    with pytest.raises(P.PreflightRefused, match="backup"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"],
                {"size": 0, "trailer_ok": False}, 414935)


def test_a_backup_with_size_but_no_trailer_is_still_refused():
    with pytest.raises(P.PreflightRefused, match="backup"):
        P.check(_sheet(), _manifest(), ["UPDATE_ASSAY"],
                {"size": 17_000_000, "trailer_ok": False}, 414935)


def test_a_chunk_above_the_cap_is_refused():
    """20-minute gunicorn SIGKILL, and this path has no transaction."""
    big = pd.DataFrame({
        "sample_id": range(P.CHUNK_CAP + 1),
        "assay_id": [501] * (P.CHUNK_CAP + 1),
        "uid": ["TIS-190101ENG-901"] * (P.CHUNK_CAP + 1),
        "current_pair": [""] * (P.CHUNK_CAP + 1),
        "new_pair": ["10:501"] * (P.CHUNK_CAP + 1)})
    manifest = pd.DataFrame({
        "sample_id": range(P.CHUNK_CAP + 1),
        "write_target_seek_assay_id": [501] * (P.CHUNK_CAP + 1),
        "project_ok": [True] * (P.CHUNK_CAP + 1)})
    with pytest.raises(P.PreflightRefused, match="2000"):
        P.check(big, manifest, ["UPDATE_ASSAY"], GOOD_BACKUP, 414935)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_preflight.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/preflight.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_preflight.py -q`

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/preflight.py tests/test_assay_hygiene_preflight.py
git commit -m "feat(assay-hygiene): the eight write refusals

Spec section 5's table, one refusal per row, each a live failure mode of
/seek/sampleupload/ rather than a hypothesis. A Current pair of two ints is the
only combination that reaches deleteOneRecord; an unparseable New pair drops
the registration and reports success; a blank uid 500s mid-chunk leaving a
committed prefix; a sheet named UPDATE hijacks dispatch into the
metadata-update path.

Backup verification requires size AND trailer because a mysqldump exited 0
having written 0 bytes."
```

---

### Task 10: Chunking and database reconciliation

**Files:**
- Create: `scripts/assay_hygiene/chunker.py`
- Test: `tests/test_assay_hygiene_chunker.py`

**Why:** Spec §5: chunking is mandatory at 2,000 rows, and "the database is the only receipt". The endpoint's feedback workbook prints `successful:` for rows that never wrote, because `DBtable.storeOneRecord` sets `status = 1` and never updates it from the DB call.

**Interfaces:**
- Consumes: `preflight.CHUNK_CAP`.
- Produces:
  - `ChunkMismatch` — a `RuntimeError` subclass.
  - `chunks(sheet: pd.DataFrame, size: int = CHUNK_CAP) -> list[pd.DataFrame]`
  - `reconcile(expected: int, before: int, after: int) -> None` — raises unless `after - before == expected`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_chunker.py
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
    with pytest.raises(K.ChunkMismatch, match="1999"):
        K.reconcile(expected=2000, before=414935, after=416934)


def test_reconcile_refuses_MORE_rows_than_expected():
    """An over-count means another writer was active; the window was not quiet."""
    with pytest.raises(K.ChunkMismatch, match="2001"):
        K.reconcile(expected=2000, before=414935, after=416936)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_chunker.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/chunker.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_chunker.py -q`

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/chunker.py tests/test_assay_hygiene_chunker.py
git commit -m "feat(assay-hygiene): chunk the payload and reconcile against the database

Gunicorn SIGKILLs at 1200s and this path has no transaction, so a crash
mid-submission leaves a committed prefix; chunking at 2,000 bounds a failure to
one chunk. Reconciliation is a count query because storeOneRecord sets
status = 1 and never updates it from the DB call, so the feedback workbook
prints successful: for rows that never landed.

An over-count refuses too: primary keys are MAX(id)+1 with no lock, so more
rows than expected means another writer was active and this run's rows may have
been overwritten."
```

---

### Task 11: Workflow sequence tests

**Files:**
- Create: `tests/test_assay_hygiene_workflow.py`

**Why:** Spec §7: "The suite tests units well and encodes the workflow nowhere." Every module above is correct in isolation; these assert the *order* — that a run cannot write before it has judgement, and that a widened cohort never reaches production without being seen.

**Interfaces:**
- Consumes: `runstate`, `init_run`, `carryforward`, `preflight`, `resolve_targets`, `rulings`.
- Produces: nothing. This task adds tests only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_workflow.py
"""The sequence, not the units.

Each module is already tested in isolation. These assert the order they must
run in -- the property that a correct set of parts can still get wrong.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import carryforward as C  # noqa: E402
from assay_hygiene import init_run as I  # noqa: E402
from assay_hygiene import preflight as P  # noqa: E402
from assay_hygiene import resolve_targets as T  # noqa: E402
from assay_hygiene import runstate as S  # noqa: E402
from assay_hygiene.rulings import Ruling  # noqa: E402


def test_a_fresh_run_refuses_to_write_before_rulings_are_ingested(tmp_path):
    """No rollback handle and no backup: the write path is closed by default."""
    S.create(tmp_path, run=2, extract_sha="abc")
    state = S.read(tmp_path)
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [501],
                          "uid": ["TIS-190101ENG-901"],
                          "current_pair": [""], "new_pair": ["10:501"]})
    manifest = pd.DataFrame({"sample_id": [10],
                             "write_target_seek_assay_id": [501],
                             "project_ok": [True]})
    with pytest.raises(P.PreflightRefused):
        P.check(sheet, manifest, ["UPDATE_ASSAY"],
                {"size": 0, "trailer_ok": False},
                state["write"]["rollback_id"])


def test_a_carried_ruling_applied_to_a_wider_cohort_is_surfaced_not_applied():
    """The RUN1 trap, asserted end to end."""
    key = ("TIS", "74", "ADD_TO_ASSAY")
    store = {key: Ruling(key, "APPROVE", "2026-08-20", "operator")}
    got = C.split([C.Cohort(key, 2830, "wide")], store, {key: 12})
    assert [c.cohort_id for c in got[C.WIDENED]] == ["wide"]
    assert got[C.CARRIED] == [], "a widened cohort must not reach the write set"


def test_the_project_gate_refuses_a_cross_project_row_by_injection():
    """Spec section 7 requires this be proven by injection, not by argument."""
    assays = pd.DataFrame({"assay_id": [501, 502],
                           "internal_assay_id": [74.0, 74.0],
                           "project_id": [1, 2]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, _ = T.resolve(rows, assays, samples)
    assert manifest.write_target_seek_assay_id.tolist() == [501]

    injected = pd.DataFrame({"sample_id": [10], "assay_id": [502]})
    with pytest.raises(P.PreflightRefused, match="manifest"):
        P.check(injected, manifest, ["UPDATE_ASSAY"],
                {"size": 17_000_000, "trailer_ok": True}, 414935)


def test_a_run_cannot_be_opened_twice(tmp_path):
    S.create(tmp_path, run=2, extract_sha="abc")
    with pytest.raises(S.RunLocked):
        S.create(tmp_path, run=3, extract_sha="def")


def test_init_refuses_a_run_when_the_store_is_gone(tmp_path):
    with pytest.raises(I.MissingRulingStore):
        I.require_store(tmp_path / "rulings", tmp_path / "backups")


def test_the_happy_path_reaches_preflight_clean(tmp_path):
    """The same sequence, with every precondition met, must NOT raise."""
    S.create(tmp_path, run=2, extract_sha="abc")
    S.update(tmp_path, write={"chunks_done": 0, "rollback_id": 414935,
                              "backup_verified": True})
    assays = pd.DataFrame({"assay_id": [501], "internal_assay_id": [74.0],
                           "project_id": [1]})
    samples = pd.DataFrame({"sample_id": [10], "project_ids": [[1]]})
    rows = pd.DataFrame({"sample_id": [10], "internal_assay_id": [74]})
    manifest, excluded = T.resolve(rows, assays, samples)
    assert excluded.empty
    sheet = pd.DataFrame({"sample_id": [10], "assay_id": [501],
                          "uid": ["TIS-190101ENG-901"],
                          "current_pair": [""], "new_pair": ["10:501"]})
    P.check(sheet, manifest, ["UPDATE_ASSAY"],
            {"size": 17_000_000, "trailer_ok": True},
            S.read(tmp_path)["write"]["rollback_id"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_workflow.py -q`

Expected: all 6 fail or error on import until Tasks 1–10 have landed. If Tasks 1–10 are already committed, this step's expected result is `6 passed` immediately — in that case, confirm the tests are genuinely exercising the sequence by temporarily reverting `carryforward.split`'s widened branch and seeing `test_a_carried_ruling_applied_to_a_wider_cohort...` fail, then restore it.

- [ ] **Step 3: No implementation**

This task adds no production code. Its deliverable is the sequence assertions themselves.

- [ ] **Step 4: Run the full suite**

Run: `uv run --group dev python -m pytest tests/ -q`

Expected: baseline + every test added in Tasks 1–11 + one per new module under `scripts/`. That is **8 modules**: `runstate`, `init_run`, `store_backup`, `carryforward`, `ingest`, `resolve_targets`, `preflight`, `chunker`. Derive the number; do not adjust a test to reach it.

- [ ] **Step 5: Commit**

```bash
git add tests/test_assay_hygiene_workflow.py
git commit -m "test(assay-hygiene): assert the workflow sequence, not just the units

Spec section 7: the suite tests units well and encodes the workflow nowhere.
Every module above is correct in isolation; these assert the order -- a fresh
run cannot write before rulings are ingested, a carried ruling applied to a
wider cohort is surfaced rather than applied, and the project gate refuses a
cross-project row proven by injection rather than by argument.

The happy path is asserted too, so the refusals cannot pass by refusing
everything."
```

---

### Task 12: The seven new command documents

**Files:**
- Create: `commands/curate-assay-init.md`, `curate-assay-detect.md`, `curate-assay-review.md`, `curate-assay-resolve.md`, `curate-assay-write.md`, `curate-assay-status.md`, `curate-assay-backup.md`
- Test: `tests/test_assay_hygiene_commands.py`

**Why:** The modules are unreachable without commands. `commands/curate-assay-vocabulary.md` establishes the house style: YAML frontmatter with a `description`, then prose addressed to the agent, with runnable blocks.

**Interfaces:**
- Consumes: every module above.
- Produces: seven command documents. No Python.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_commands.py
"""Every assay-mode command exists, is addressed, and never writes by default.

Mirrors tests/test_curate_commands_present.py's write-safety direction: no
command doc may instruct an operator to pass --dry-run, because its absence
would imply writing.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

EXPECTED = ["curate-assay-init.md", "curate-assay-vocabulary.md",
            "curate-assay-detect.md", "curate-assay-review.md",
            "curate-assay-resolve.md", "curate-assay-write.md",
            "curate-assay-status.md", "curate-assay-backup.md"]


@pytest.mark.parametrize("name", EXPECTED)
def test_the_command_exists(name):
    assert (COMMANDS / name).is_file()


@pytest.mark.parametrize("name", EXPECTED)
def test_the_command_has_a_description(name):
    text = (COMMANDS / name).read_text()
    assert text.startswith("---\n"), "needs YAML frontmatter"
    front = text.split("---", 2)[1]
    assert "description:" in front


@pytest.mark.parametrize("name", EXPECTED)
def test_no_command_instructs_a_dry_run_flag(name):
    assert "--dry-run" not in (COMMANDS / name).read_text()


def test_the_write_command_names_confirm_and_every_refusal():
    text = (COMMANDS / "curate-assay-write.md").read_text()
    assert "--confirm" in text, "writing must be opt-in"
    for phrase in ("rollback", "backup", "manifest", "chunk"):
        assert phrase in text.lower(), f"write doc does not mention {phrase}"


def test_the_init_command_names_the_restore_path():
    text = (COMMANDS / "curate-assay-init.md").read_text()
    assert "tar" in text and "backup" in text.lower()


def test_no_assay_command_tells_the_operator_to_omit_out_dir():
    """The clobbering hazard: run_evidence with no out_dir writes through
    the symlink tree into the preserved baseline."""
    for name in EXPECTED:
        text = (COMMANDS / name).read_text()
        for line in text.splitlines():
            if "assay_hygiene.run_evidence" in line or "assay_hygiene.run_detect" in line:
                assert "RUN" in line or "out" in line or line.rstrip().endswith("\\"), (
                    f"{name} invokes a driver with no output directory: {line!r}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_commands.py -q`

Expected: **24 failures/errors** — seven missing files across three parametrized tests (21), plus the three specific tests that read a file that does not exist yet. `test_the_command_exists[curate-assay-vocabulary.md]` passes, because that one file already exists.

- [ ] **Step 3: Write the command documents**

Each follows the frontmatter-then-prose shape of `curate-assay-vocabulary.md`. Write them with this content:

`commands/curate-assay-init.md`:
```markdown
---
description: Open a numbered assay-hygiene run and prove the ruling store survives
---

The user wants a new assay-hygiene run.

This mode is **house-scoped**: one extract, all projects, no PI. Every path
below is relative to the directory holding `scripts/` and `assets/`.

## Before anything else: the ruling store

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from pathlib import Path
from assay_hygiene.init_run import require_store
require_store(Path('assets/rulings'), Path('~/backups').expanduser())
print('ruling store present')
"
```

If that raises `MissingRulingStore`, **stop**. Nothing regenerates a human
ruling — not compute, not a re-run. Restore the newest tarball it names:

```bash
tar -xzf ~/backups/rulings-<newest>.tar.gz -C assets/
```

Only if this is genuinely the first run, create the store by migrating RUN1.

## Open the run

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
from pathlib import Path
from assay_hygiene.init_run import create_run, next_run_number
from assay_hygiene.runstate import create
n = next_run_number(Path('assets'))
run = create_run(Path('assets'), n)
create(Path('assets'), run=n, extract_sha='<sha of the extract you pulled>')
print('opened', run)
"
```

`create` refuses while another run is open. That is a safety property: two
concurrent write phases can silently overwrite each other's rows, because
primary keys are `MAX(id)+1` computed in Python with no lock.

Tiers `00`–`06` are made read-only at creation. `07-process` stays writable.

## One decision this run must make consciously

`tests/test_assay_hygiene_rulings.py:332` is `xfail(strict=True)` and names 13
cohorts the operator rejected that a primary surface still proposes. If the new
extract no longer contains them the assertion passes, strict mode reports XPASS
and the suite goes red for a reason unrelated to any fix. Decide whether that
measurement still applies to this run, and record the decision in
`07-process/`. Do not silently flip the marker.
```

`commands/curate-assay-detect.md`:
```markdown
---
description: Run the evidence and detection passes into this run's own directory
---

The user wants this run's proposals generated.

## Never write to the default paths

`run_evidence` and `run_detect` default `out_dir` to `assay-hygiene/`, which is
33 symlinks into `assets/RUN1/`. A default-path run overwrites the baseline
every measurement is compared against. `assay_hygiene._writeguard` now refuses
it outright, but pass the run's own directory rather than relying on the
refusal:

```bash
RUN=assets/RUN2
cp assets/RUN1/04-artifacts/vocabulary-curator.csv $RUN/04-artifacts/ 2>/dev/null || true
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_detect   $RUN/01-extract $RUN/04-artifacts
```

`run_detect` does **not** call `run_evidence`. Both are needed, in that order;
`gate` and `classify` read `claims.parquet` and `vocabulary.csv` from the output
directory and now exit 2 naming what to run first rather than raising.

`04-artifacts` is read-only from creation, so unprotect it for the run and
re-protect afterwards:

```bash
chmod -R u+w $RUN/04-artifacts       # before
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.protect_run import protect
protect(Path('$RUN'), ['04-artifacts'])"   # after
```

## Sort the cohorts against previous judgement

Every cohort goes into exactly one of three buckets:

- **already ruled** — the pair matches and this cohort is no wider than the one
  ruled against. Carried.
- **ruled in a narrower context** — the pair matches but this cohort covers
  rows the original did not. **Surfaced for re-confirmation, never applied.**
- **never seen** — goes to the operator.

The middle bucket is the trap this mode exists to close. In RUN1, 2,830 rows
shared a cohort key with an approved cohort but sat below the precedent floor
the operator's sheet was built at, so he never saw them.

Report the three counts and record them in the lockfile via
`runstate.update(carried_pairs=...)`.
```

`commands/curate-assay-review.md`:
```markdown
---
description: Serve the review surfaces, ingest the operator's rulings, back up
---

The user wants to rule on this run's cohorts.

Two artifacts per surface. The **HTML** carries the context a cell cannot hold —
the neighbour's own registrations, the precedent table, the gate outcome and its
reason. The **CSV** carries one row per cohort with a blank `ruling` column.

The operator edits the CSV and hands it back. Judgement therefore lives in a
diffable, greppable file a later reader can audit.

## Ingest

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.ingest import ingest
from assay_hygiene.rulings import save
from assay_hygiene.store_backup import back_up
edited = pd.read_csv('<the file the operator edited>')
cohorts = {}   # cohort_key -> pair key, as emitted by the review surface
found = ingest(edited, cohorts, ruled_on='<today>')
save(Path('assets/rulings'), found)
print('backed up to', back_up(Path('assets/rulings'),
                              Path('~/backups').expanduser(), '<stamp>'))
"
```

**Backup is part of ingest, not a separate step you remember.** The store is
gitignored, so a tarball outside the working tree is its only protection —
`git clean -xdf` lists `assets/` for removal.

The ingest **refuses the whole file** rather than part of it if any row matches
no cohort, if a verdict is outside the vocabulary, or if one cohort is ruled two
ways. A partial ingest files a subset of the operator's judgement and reports
success.

The `cohort_key` must be the one the review surface emitted — use
`assay_hygiene.review.cohort_key`, never rebuild it here. A second definition of
the key is one edit away from disagreeing with the first.
```

`commands/curate-assay-resolve.md`:
```markdown
---
description: Turn approved pairs into SEEK write targets behind the project gate
---

The user wants the approved rulings turned into a write set.

SEEK assay ids are **per-project**. The same internal assay is a different
`assay_id` in every project that runs it, so a registration must land on the
assay belonging to the *sample's own* project.

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from pathlib import Path
from assay_hygiene.resolve_targets import resolve
RUN = Path('assets/RUN2')
assays  = pd.read_parquet(RUN/'01-extract'/'assays.parquet')
samples = pd.read_parquet(RUN/'01-extract'/'samples.parquet')
rows    = pd.read_csv(RUN/'04-artifacts'/'approved-rows.csv')
manifest, excluded = resolve(rows, assays, samples)
manifest.to_csv(RUN/'04-artifacts'/'MANIFEST.csv', index=False)
excluded.to_csv(RUN/'04-artifacts'/'EXCLUDED.csv', index=False)
print(f'{len(manifest):,} targets, {len(excluded):,} excluded')
print(excluded.reason.value_counts().to_string() if len(excluded) else '')
"
```

The 2026-08-26 audit found 578 of 26,188 rows targeting another project's
assay. 159 were repairable, 419 were not. **This is unrecoverable once
written** — the sample joins a project it does not belong to.

Excluded rows are authorised registrations with no correct target, not
rejections. Report both counts to the operator; a large `sample belongs to no
project` count is an upstream data problem worth raising separately.

`MANIFEST.csv` is what `curate-assay-write` checks the sheet against. Do not
hand-edit it.
```

`commands/curate-assay-write.md`:
```markdown
---
description: Write registrations to production, behind eight refusals
---

The user wants this run's registrations written to production.

**This is the only command that touches production.** It writes nothing without
`--confirm`.

## The mechanism, and why this one

An `UPDATE_ASSAY` sheet posted to `/seek/sampleupload/`, one row per
`(sample, assay)` edge, **both Current columns blank**. Chosen because it is
structurally incapable of deleting: with the Current pair unparseable, `id = -1`
and the delete branch behind `if id>0` is unreachable.

Measured against the alternatives for the same 25,769 rows: the API route put
202,016 existing memberships at risk, batch-upload 25,912, this route **zero**.

Every registration writes `direction = 0`. Nothing in `seek/` reads the column,
and our rows assert membership; lineage direction is already recorded in the
graph by stage 0.

## Preflight — all eight, before any row

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
from assay_hygiene.preflight import check
check(sheet, manifest, sheet_names, backup, rollback_id)
print('preflight clean')
"
```

It refuses: a Current pair of two ints; an unparseable New pair; a blank or
non-string uid; a sheet named `UPDATE` anywhere in the workbook; any row absent
from the gate-checked manifest; no captured rollback handle; a backup that is
absent **or unverified**; a chunk above 2,000 rows.

## Capture the rollback handle first

```sql
SELECT MAX(id) FROM seek_production.assay_assets;
```

Record it in the lockfile. Undo for the whole run is
`DELETE FROM seek_production.assay_assets WHERE id > <handle>;` — no FKs, no
triggers, monotonic id.

## Verify the backup, do not trust its exit code

Non-zero size **and** a `Dump completed` trailer. A `mysqldump` exited 0 having
written a 0-byte file on 2026-08-27; only an `ls` caught it.

## Chunk, submit, count

2,000 rows per submission. Gunicorn SIGKILLs at 1200s and this path has **no
transaction**, so a crash leaves a committed prefix. After each chunk:

```sql
SELECT COUNT(*) FROM seek_production.assay_assets WHERE id > <handle>;
```

**The database is the only receipt.** `DBtable.storeOneRecord` sets `status = 1`
and never updates it from the DB call, so the feedback workbook prints
`successful:` for rows that never wrote. `reconcile()` refuses an over-count
too: more rows than expected means another writer was active and this run's rows
may have been overwritten.

A quiet window is required. `nextseek_api`'s batch-upload path writes the same
table, and primary keys are `MAX(id)+1` computed in Python with no lock.
```

`commands/curate-assay-status.md`:
```markdown
---
description: Report which assay-hygiene run is open and where it has got to
---

The user wants to know where this campaign stands. This command writes nothing.

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.runstate import read
state = read(Path('assets'))
if not state:
    print('no run has been opened')
else:
    print(f\"run {state['run']}  open={state['open']}  step={state['step']}\")
    print(f\"  extract      {state['extract_sha']}\")
    print(f\"  carried      {state['carried_pairs']} pairs from run {state['carried_from_run']}\")
    w = state['write']
    print(f\"  write        chunks_done={w['chunks_done']} rollback={w['rollback_id']} backup_verified={w['backup_verified']}\")
"
```

Also report the ruling store's size, since it is the thing that outlives runs:

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
from pathlib import Path
from assay_hygiene.rulings import load
print(f'{len(load(Path(\"assets/rulings\"))):,} rulings in the store')
"
```
```

`commands/curate-assay-backup.md`:
```markdown
---
description: Write a dated, verified tarball of the ruling store
---

The user wants the ruling store backed up by hand. `curate-assay-review` does
this automatically on every ingest; this command exists for use outside that.

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
from pathlib import Path
from assay_hygiene.store_backup import back_up
made = back_up(Path('assets/rulings'), Path('~/backups').expanduser(),
               '<YYYYMMDD-HHMM>')
print('wrote', made)
"
```

`back_up` opens the archive it just wrote and asserts the store's files are
inside before returning. An exit code describes the call; the archive describes
the backup.

Backing up an absent store **refuses** rather than producing an empty archive
that reports success.

This accepts a real limit, recorded rather than smoothed over: backups live on
the same machine, so a lost machine is a lost curation campaign. That is the
cost of keeping identifiers out of a public repository.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_commands.py -q`

Expected: `28 passed` (three parametrized tests over 8 files, plus 4 specific tests).

- [ ] **Step 5: Commit**

```bash
git add commands/curate-assay-*.md tests/test_assay_hygiene_commands.py
git commit -m "feat(assay-hygiene): the seven new mode commands

init, detect, review, resolve, write, status and backup, in the
frontmatter-then-prose shape curate-assay-vocabulary.md established.

Every driver invocation names an explicit output directory, asserted by a test:
run_evidence with no out_dir writes through the symlink tree into the preserved
baseline, which is the hazard the write guard exists to catch and which no doc
should be teaching. No doc instructs --dry-run; writing is opt-in via --confirm."
```

---

### Task 13: Absorb and fix `curate-assay-vocabulary.md`

**Files:**
- Modify: `commands/curate-assay-vocabulary.md`

**Why:** Spec §1: "That existing command is absorbed and fixed on the way in. It currently carries both defects this design exists to remove." It instructs `run_evidence` with **no `out_dir`** (the clobbering hazard), and quotes 2026-08-14 figures while telling the reader to re-measure them. Task 12's `test_no_assay_command_tells_the_operator_to_omit_out_dir` already covers this file, and is red until this task lands.

**Interfaces:**
- Consumes: nothing.
- Produces: no new interface.

- [ ] **Step 1: Confirm the test is red for this file**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_commands.py -q -k out_dir`

Expected: FAIL naming `curate-assay-vocabulary.md` and the bare
`python -m assay_hygiene.run_evidence` line.

- [ ] **Step 2: Fix the invocation**

In `commands/curate-assay-vocabulary.md`, replace both bare driver invocations
with run-scoped ones. The block currently reading:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence
```

becomes:

```bash
RUN=assets/RUN2      # this run's directory, never the default path
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts
```

Do the same for the `vocabulary_evidence` invocation further down, and replace
every remaining `assay-hygiene/<file>` path in the document with
`$RUN/04-artifacts/<file>` or `$RUN/01-extract/<file>` as appropriate.

- [ ] **Step 3: Replace the stale figures with an instruction to measure**

Delete the paragraph beginning "Measured on the 2026-08-14 extract: **266
unresolved terms over 14,753 distinct samples**…" and the per-field breakdown.
Quoting a figure and then telling the reader to re-measure it is how the wrong
number gets copied forward. Replace with:

```markdown
The size of the unresolved tail moves with the extract, so it is not quoted
here. Measure it for this run before starting:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
u = pd.read_csv('$RUN/04-artifacts/vocabulary-unresolved.csv')
print(f'{len(u):,} unresolved terms')
print(u.groupby('field').size().sort_values(ascending=False).to_string())
"
```
```

- [ ] **Step 4: Add the mode header**

Add immediately after the frontmatter, matching the other seven:

```markdown
This is **stage B2 of the assay-hygiene mode**. It is house-scoped: one
extract, all projects, no PI. Run `curate-assay-init` first — this command
needs an open run, and every path below is relative to it.
```

- [ ] **Step 5: Run the tests**

Run: `uv run --no-project --with pytest python -m pytest tests/test_assay_hygiene_commands.py -q`

Expected: `28 passed`

- [ ] **Step 6: Commit**

```bash
git add commands/curate-assay-vocabulary.md
git commit -m "fix(assay-hygiene): absorb curate-assay-vocabulary into the mode

It carried both defects this design exists to remove. It instructed
run_evidence with no out_dir -- the clobbering hazard, which resolves through
the symlink tree onto the preserved baseline -- and it quoted 2026-08-14
figures while telling the reader to re-measure them, which is exactly how a
stale number gets copied forward.

Both fixed: every path is now run-scoped, and the figures are replaced by the
command that measures them."
```

---

### Task 14: Register `assay` as the fifth mode

**Files:**
- Create: `skills/curation/ASSAY.md`
- Modify: `skills/curation/SKILL.md`, `tests/test_mode_table.py`
- Test: `tests/test_mode_table.py`

**Why:** `tests/test_mode_table.py` pins exactly four modes and asserts the SKILL.md table lists exactly the reference docs present. Adding a fifth mode without updating all three goes red. The test function is literally named `test_mode_table_has_the_four_modes`.

**Interfaces:**
- Consumes: nothing.
- Produces: no Python interface.

- [ ] **Step 1: Write the failing test**

In `tests/test_mode_table.py`, add `assay` to `EXPECTED_MODES` and rename the
count test:

```python
EXPECTED_MODES = {
    "pipeline": "PHASES.md",
    "fdh": "FDH.md",
    "schema": "SCHEMA.md",
    "report": "REPORTS.md",
    "assay": "ASSAY.md",
}
```

and rename `test_mode_table_has_the_four_modes` to
`test_mode_table_has_every_mode`, leaving its body unchanged:

```python
def test_mode_table_has_every_mode():
    assert set(mode_table_rows()) == set(EXPECTED_MODES)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest python -m pytest tests/test_mode_table.py -q`

Expected: `3 failed` — `test_every_reference_doc_exists` (no `ASSAY.md`),
`test_mode_table_lists_exactly_the_reference_docs`, and
`test_mode_table_has_every_mode`.

- [ ] **Step 3: Write the reference doc**

Create `skills/curation/ASSAY.md`:

```markdown
# Assay hygiene mode

House-scoped, not project-scoped: one extract, all projects, no PI. It finds
samples that should be registered against an internal assay and are not, puts
every proposal in front of a human, and writes the approved ones to production.

## The run model

Runs are numbered and immutable at `assets/RUN<n>/`, tiers `00`–`06` read-only
from creation. State is `assets/assay-run.json`; one run may be open at a time,
because two concurrent write phases can silently overwrite each other's rows.

## The ruling store

Judgement lives at `assets/rulings/`, **outside** any run, keyed on
`(sample_type, internal_assay_id, action)` with the cohort string kept
alongside as provenance.

This is the structural change that makes reuse possible. RUN1 filed verdicts
under `lab|sample_type|parent_types|assay_title|field|value`; four of those six
move with the extract, so a new run matched almost none of them and 261 rulings
became worthless without any judgement having changed.

A pair ruling is **coarser** than the cohort it was made against. Measured on
RUN1, 200 ruled rows collapse to 127 keys and 5 disagree. Those 5 are excluded
from the store and put back to the operator, never resolved by a rule.

## Commands

| command | does | writes |
|---|---|---|
| `curate-assay-init` | open a run, prove the store survives, chmod tiers | run dir |
| `curate-assay-vocabulary` | unresolved terms → operator sheet → ingest | ruling store |
| `curate-assay-detect` | evidence + detection into the run's own out_dir | run artifacts |
| `curate-assay-review` | serve surfaces, ingest rulings, auto-backup | ruling store |
| `curate-assay-resolve` | internal → SEEK targets behind the project gate | run artifacts |
| `curate-assay-write` | preflight, chunk, submit, reconcile | **production** |
| `curate-assay-status` | read the lockfile, report position | nothing |
| `curate-assay-backup` | dated, verified tarball of the store | backup dir |

## Three things that will bite

**Never run a driver on default paths.** `run_evidence` and `run_detect`
default `out_dir` to `assay-hygiene/`, which is 33 symlinks into
`assets/RUN1/`. `_writeguard` refuses it, but pass the run directory anyway.

**Nothing regenerates a human ruling.** The store is gitignored and its only
protection is a tarball on one machine. `git clean -xdf` lists `assets/` for
removal. A lost machine is a lost campaign — that is the accepted cost of
keeping identifiers out of a public repository.

**The database is the only receipt.** `storeOneRecord` sets `status = 1` and
never updates it, so the endpoint's feedback workbook reports success for rows
that never wrote.
```

- [ ] **Step 4: Add the row to SKILL.md**

In `skills/curation/SKILL.md`'s `## Modes` table, add a row matching the
existing column shape. Read the header row first and fill every column — the
parser in `test_mode_table.py` skips any row whose cell count does not match
the header, so a short row fails as "mode missing" rather than as a bad row:

```markdown
| `assay` | assay hygiene: register samples against internal assays, house-scoped | `ASSAY.md` |
```

- [ ] **Step 5: Run the tests**

Run: `uv run --no-project --with pytest python -m pytest tests/test_mode_table.py -q`

Expected: all pass, with one more parametrized case than before
(`test_each_mode_points_at_its_doc[assay-ASSAY.md]`).

- [ ] **Step 6: Run the full suite**

Run: `uv run --group dev python -m pytest tests/ -q`

Expected: derive it — baseline plus every test added across Tasks 1–14 plus one
per new module under `scripts/`. If a count disagrees, diff collected node ids
against a pristine tree rather than adjusting a test.

- [ ] **Step 7: Commit**

```bash
git add skills/curation/ASSAY.md skills/curation/SKILL.md tests/test_mode_table.py
git commit -m "feat(assay-hygiene): register assay as the fifth curation mode

test_mode_table.py pins the mode set, the reference docs present and the
SKILL.md table against each other, so all three move together or the suite goes
red. The count test is renamed off 'four' so it does not lie the next time a
mode is added.

ASSAY.md records the three things that bite: never run a driver on default
paths, nothing regenerates a human ruling, and the database is the only
receipt."
```

---

## Self-Review

**Spec coverage.**

| spec section | task |
|---|---|
| §1 mode not plugin; absorb `curate-assay-vocabulary` | 13, 14 |
| §2 run model, numbered runs, chmod in code, one run at a time | 1, 3 |
| §3 ruling store location, pair key, provenance, automatic backup | 4, 5, 7 (store itself landed in Plan 2) |
| §4 the eight commands | 12, 13 |
| §4 carry-forward three-way split | 6 |
| §5 the eight write refusals | 9 |
| §5 project consistency hard gate + manifest | 8 |
| §5 verify the artifact not the exit code | 5, 9, 10 |
| §5 the database is the only receipt | 10 |
| §5 chunking mandatory at 2,000 | 9, 10 |
| §6 prerequisites | **landed in the prerequisites plan** — all four |
| §7 workflow sequence tests | 11 |
| §7 conftest banner fix | **landed in the prerequisites plan** (Task 4) |
| §7 the two landmines | vacuity guard defused by the write guard; the strict-xfail is a conscious RUN2 decision, surfaced in `curate-assay-init.md` (Task 12) rather than pre-decided here |
| §8 migrating RUN1 | 4 |
| §9 review surfaces HTML + CSV | 12 |
| §9 the tested ingest join, four properties | 7 |
| §9 ruling recovery, init refuses silently | 2 |
| §9 direction is always 0 | 12 (`curate-assay-write.md`) |

**Deliberately not built here.** The HTML review surface is *documented* in Task 12 but not implemented, because `review_mode2.py` already builds Mode 2's HTML and CSV (`build_blocks`, `to_csv`, `REVIEW_NAME`, `CSV_NAME`) and rewriting it would be duplication, not progress. Task 7's `ingest` is the piece that was genuinely missing — the join *back*. An executor finding a surface Mode 1 or the pair queue needs and `review_mode2` cannot give should raise it rather than inventing a second key definition.

**Placeholder scan.** No TBD/TODO. Every code step carries runnable code; every test step names the command and the expected count. The one deliberate blank is `cohorts = {}` in `curate-assay-review.md`, which is a prose command doc showing shape, not executable plan code — Task 7's tests pin the real contract.

**Type consistency.** `PairKey` is `tuple[str, str, str]` everywhere and comes from `rulings`, never redefined. `Ruling(key, verdict, ruled_on, actor)` field order matches Plan 2 and is used identically in Tasks 4, 6, 7, 11. `Cohort(key, n_rows, cohort_id)` is used identically in Tasks 6 and 11. `TARGET_COLUMN = "write_target_seek_assay_id"` is defined once in `resolve_targets` and consumed by `assert_subset` and `preflight.check`; note `registration_payload.py` already defines the same string independently — that duplication predates this plan and is left alone rather than refactored mid-flight, but an executor touching both should collapse them. `CHUNK_CAP` is defined in `preflight` and imported by `chunker`, so the cap has one definition.

**Two things an executor must not do.** Resolve the 5 conflicting keys to unblock themselves — they are Task 4's deliverable, not an obstacle. And adjust a test to reach an expected suite count: both prior plans mispredicted totals for benign reasons, and the correct response is to diff collected node ids against a pristine tree.
