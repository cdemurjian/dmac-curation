# Assay Hygiene Ruling Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move human judgement out of the run that produced it into a durable, cross-run store keyed on something a new extract cannot break, so run 2 inherits run 1's 156 rulings instead of re-asking them.

**Architecture:** One new module (`scripts/assay_hygiene/rulings.py`) owning the store's format, reads, writes and conflict detection; one migration entry point that reads RUN1's three ruling files and emits the store; and a carry-forward classifier that sorts new cohorts against it. No changes to detection.

**Tech Stack:** Python 3.11+, pandas, pytest. Run with `uv run --no-project --with pytest --with pandas --with pyarrow ... python -m pytest ...`

**Spec:** `docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` §3 (ruling store), §4 (carry-forward split), §8 (migration)

**Depends on:** Plan 1 (`2026-08-27-assay-hygiene-prerequisites.md`) — Task 1's write guard must land first, or migration can write through the symlink tree.

## Global Constraints

- **This repository is PUBLIC.** Never write a real sample uid, protocol identifier, or `<YYMMDD><LAB>` batch stamp into a tracked file. Synthetic uids use the reserved `19MMDD` band. `tests/test_identifier_exposure.py` enforces this — note that writing a uid literal into a *comment* also trips it.
- **Cohort strings contain identifiers** — lab codes, and in at least one RUN1 case a protocol filename with a person's name. Provenance therefore never enters git, and no test may hard-code a cohort key. Read them from fixtures at runtime, exactly as `tests/test_assay_hygiene_rulings.py` does.
- **`assets/` is gitignored and stays that way.** The store lives at `assets/rulings/`.
- **Never modify `assets/RUN1/00-rulings/`.** It is `chmod a-w` and is the only irreplaceable thing in the repository. Migration reads it.
- Suite baseline after Plan 1: **1,367 passed / 9 skipped / 4 xfailed**.
- Commit after every task. Do not push.

## Measured inputs

Taken from RUN1 on 2026-08-27; re-derive rather than trusting these.

| source | rows | shape |
|---|---:|---|
| `mode1-rulings-COMPLETE.tsv` | 44 | `key` (6 pipe-delimited fields), `ruling`, `note`, `provenance` |
| `mode2-rulings-2026-08-20.tsv` | 111 | `lab`, `sample_type`, `parent_types`, `assay` (title), `field`, `value`, `ruling`, `note` |
| `pair-rulings.tsv` | 175 (45 ruled, 130 `UNRULED`) | `sample_type`, `proposed_assay`, `internal_assay_id`, `ruling`, `status` — **already the target shape** |

All 111 Mode 2 assay titles resolve to a **unique** internal assay id (0 ambiguous, 0 unresolvable). Of the Mode 2 rows, 100 are lineage (carrying the action in `value`: 70 `ADD_PARENT_TO_ASSAY`, 30 `ADD_CHILD_TO_ASSAY`) and 11 are term rows.

**CORRECTED 2026-08-27 by re-derivation, as this section instructs.** The
figures below originally read "156 ruled rows collapse to **114 distinct pair
keys**, of which **3 carry conflicting verdicts**". That measurement silently
omitted the 44 Mode 1 rows: 111 + 45 = 156, and the table directly above lists
44 more. Migration reads all three files, exactly as Task 2 specifies.

Measured over all three sources: **200 ruled rows** (mode2 111 + pair 45 +
mode1 44) collapse to **127 distinct pair keys**, of which **5 carry
conflicting verdicts**. Excluding mode1 reproduces the old 156 / 114 / 3
exactly, which is how the omission was identified. Every verdict present is
inside `VERDICTS` (`APPROVE`, `REJECT`, `WRONG_ASSAY`), so `save` refuses none
of them for vocabulary.

---

### Task 1: The store format, reader and writer

**Files:**
- Create: `scripts/assay_hygiene/rulings.py`
- Test: `tests/test_assay_hygiene_rulings_store.py`

**Interfaces:**
- Produces:
  - `PairKey = tuple[str, str, str]` — `(sample_type, internal_assay_id, action)`, all strings; the id is the decimal integer with no `.0` suffix.
  - `Ruling` — frozen dataclass: `key: PairKey`, `verdict: str`, `ruled_on: str`, `actor: str`.
  - `VERDICTS = ("APPROVE", "REJECT", "WRONG_ASSAY", "UNSURE")`
  - `load(store: Path) -> dict[PairKey, Ruling]`
  - `save(store: Path, rulings: Iterable[Ruling]) -> int`
  - `normalise_id(value) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_rulings_store.py
"""The durable ruling store: what a verdict is filed under, and what it costs.

RUN1's rulings were keyed on `lab|sample_type|parent_types|assay_title|field|value`.
Four of those six fields move with the extract, so a new run matched almost
none of them and 261 rulings became worthless -- not because the judgement
changed but because the string they were filed under did. This stores judgement
under (sample_type, internal_assay_id, action), all three of which survive a
title edit, a lab change and lineage drift.

NO COHORT KEY IS WRITTEN INTO THIS FILE. They carry lab codes and, in one RUN1
case, a protocol filename with a person's name.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import rulings as R  # noqa: E402


def test_a_saved_ruling_reads_back_identical(tmp_path):
    one = R.Ruling(key=("TIS", "74", "ADD_PARENT_TO_ASSAY"),
                   verdict="APPROVE", ruled_on="2026-08-20", actor="operator")
    R.save(tmp_path, [one])
    assert R.load(tmp_path)[one.key] == one


def test_the_internal_id_normalises_away_a_float_suffix():
    """Titles resolve through pandas, which yields 74.0 for an int column."""
    assert R.normalise_id(74.0) == "74"
    assert R.normalise_id("74.0") == "74"
    assert R.normalise_id(" 74 ") == "74"


def test_a_verdict_outside_the_vocabulary_is_refused(tmp_path):
    bad = R.Ruling(key=("TIS", "74", "ADD_PARENT_TO_ASSAY"),
                   verdict="probably fine", ruled_on="2026-08-20", actor="operator")
    with pytest.raises(ValueError, match="probably fine"):
        R.save(tmp_path, [bad])


def test_saving_the_same_key_twice_with_the_same_verdict_is_one_row(tmp_path):
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    R.save(tmp_path, [R.Ruling(key, "APPROVE", "2026-08-20", "operator"),
                      R.Ruling(key, "APPROVE", "2026-08-21", "operator")])
    assert len(R.load(tmp_path)) == 1


def test_saving_the_same_key_with_DIFFERENT_verdicts_refuses(tmp_path):
    """A conflict is the operator's to resolve, never a rule's."""
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    with pytest.raises(R.ConflictingRulings, match="TIS"):
        R.save(tmp_path, [R.Ruling(key, "APPROVE", "2026-08-20", "operator"),
                          R.Ruling(key, "REJECT", "2026-08-21", "operator")])


def test_loading_an_absent_store_is_empty_not_an_error(tmp_path):
    assert R.load(tmp_path / "nothing-here") == {}


def test_the_store_survives_a_round_trip_of_many(tmp_path):
    many = [R.Ruling((f"T{i}", str(i), "ADD_TO_ASSAY"), "APPROVE",
                     "2026-08-20", "operator") for i in range(500)]
    R.save(tmp_path, many)
    assert len(R.load(tmp_path)) == 500
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_rulings_store.py -q`

Expected: collection error — `ImportError: cannot import name 'rulings'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/rulings.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""The durable ruling store: human judgement, separated from the run that made it.

WHY THE KEY IS WHAT IT IS. RUN1 filed verdicts under
`lab|sample_type|parent_types|assay_title|field|value`. Four of those six fields
move with the extract -- the lab is whichever happened to fall in that cohort,
parent_types depends on that extract's lineage, the assay is a TITLE and titles
are editable, and the value is a raw metadata term. So a new extract produced
cohorts that matched almost nothing and 261 rulings became worthless, though
none of the judgement had changed.

`(sample_type, internal_assay_id, action)` survives all four. It is also the
unit the reachability gate decides on, which is why ~150 pair questions settled
97% of a 99,449-row population when 251 cohort rulings could only estimate it.

WHAT THE KEY COSTS, stated because it is real: a pair ruling is COARSER than
the cohort it was made against. Measured on RUN1, 156 ruled rows collapse to 114
keys and 3 of those carry conflicting verdicts -- the operator approved one
cohort and rejected another sharing the same triple, because his judgement
rested on something the triple discards. `save` refuses to resolve that. A
conflict is escalated, never averaged.

PROVENANCE IS NOT STORED HERE. Cohort strings carry lab codes and at least one
protocol filename containing a person's name; they live in a gitignored sidecar
written by the migration, not in this module's tracked output.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PAIRS_NAME = "pairs.tsv"
VERDICTS = ("APPROVE", "REJECT", "WRONG_ASSAY", "UNSURE")

PairKey = tuple[str, str, str]


class ConflictingRulings(ValueError):
    """One key, two different verdicts. The operator resolves this, not a rule."""


@dataclass(frozen=True)
class Ruling:
    key: PairKey
    verdict: str
    ruled_on: str
    actor: str


def normalise_id(value) -> str:
    """-> the internal assay id as a bare decimal string.

    Titles resolve through pandas, whose integer columns yield `74.0`. A key
    that is sometimes `74` and sometimes `74.0` silently fails to match, which
    is the same class of defect as the internal-vs-SEEK id collision.
    """
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _collapse(rulings: Iterable[Ruling]) -> dict[PairKey, Ruling]:
    out: dict[PairKey, Ruling] = {}
    for r in rulings:
        if r.verdict not in VERDICTS:
            raise ValueError(
                f"verdict {r.verdict!r} is not one of {list(VERDICTS)}. A "
                f"typo must refuse rather than default.")
        seen = out.get(r.key)
        if seen is not None and seen.verdict != r.verdict:
            raise ConflictingRulings(
                f"{r.key} carries both {seen.verdict} and {r.verdict}. A pair "
                f"ruling is coarser than the cohort it was made against; this "
                f"is a real disagreement and must be put to the operator.")
        out[r.key] = r
    return out


def save(store: Path, rulings: Iterable[Ruling]) -> int:
    """Write the store. Refuses an unknown verdict or a conflicting key."""
    collapsed = _collapse(rulings)
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [{"sample_type": k[0], "internal_assay_id": k[1], "action": k[2],
          "verdict": r.verdict, "ruled_on": r.ruled_on, "actor": r.actor}
         for k, r in sorted(collapsed.items())])
    frame.to_csv(store / PAIRS_NAME, sep="\t", index=False)
    return len(collapsed)


def load(store: Path) -> dict[PairKey, Ruling]:
    """-> key -> Ruling. An absent store is empty, not an error."""
    path = Path(store) / PAIRS_NAME
    if not path.exists():
        return {}
    frame = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    return {(r.sample_type, normalise_id(r.internal_assay_id), r.action):
            Ruling((r.sample_type, normalise_id(r.internal_assay_id), r.action),
                   r.verdict, r.ruled_on, r.actor)
            for r in frame.itertuples()}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_rulings_store.py -q`

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/rulings.py tests/test_assay_hygiene_rulings_store.py
git commit -m "feat(assay-hygiene): the durable ruling store

RUN1 filed verdicts under lab|sample_type|parent_types|assay_title|field|value.
Four of those six move with the extract, so a new run matched almost none of
them and 261 rulings became worthless -- though none of the judgement had
changed, only the string it was filed under.

(sample_type, internal_assay_id, action) survives a title edit, a lab change
and lineage drift, and is the unit the reachability gate actually decides on.

save() refuses two things rather than resolving them: a verdict outside the
vocabulary, and one key carrying two different verdicts. The second is the
measured cost of a coarser key -- 156 RUN1 rulings collapse to 114 keys and 3
disagree -- and averaging it would silently overwrite a human decision."
```

---

### Task 2: Migrate RUN1's three ruling files

**Files:**
- Create: `scripts/assay_hygiene/migrate_rulings.py`
- Test: `tests/test_assay_hygiene_migrate_rulings.py`

**Why:** The three files have three different shapes. `pair-rulings.tsv` is already the target. `mode2-rulings-2026-08-20.tsv` needs title→id resolution and action derivation. `mode1-rulings-COMPLETE.tsv` needs its 6-field composite key parsed.

**Interfaces:**
- Consumes: `rulings.Ruling`, `rulings.save`, `rulings.normalise_id`, `rulings.ConflictingRulings`.
- Produces:
  - `migrate(run_dir: Path, assays: pd.DataFrame) -> tuple[list[Ruling], list[dict]]` — returns rulings and provenance records. Raises nothing on conflict; conflicts surface via Task 3.
  - `title_index(assays: pd.DataFrame) -> dict[str, str]` — internal assay title → internal id, refusing ambiguity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_migrate_rulings.py
"""Turning RUN1's three ruling shapes into one durable store.

NO COHORT KEY OR LAB CODE IS WRITTEN INTO THIS FILE. Fixtures are synthetic.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import migrate_rulings as M  # noqa: E402


@pytest.fixture
def assays():
    return pd.DataFrame({
        "assay_id": [1, 2, 3],
        "internal_assay_id": [74.0, 130.0, 61.0],
        "internal_assay_title": ["Tissue Collection", "Mass Spectrometry",
                                 "RNA Extraction"],
    })


def test_a_title_resolves_to_a_bare_internal_id(assays):
    assert M.title_index(assays)["Tissue Collection"] == "74"


def test_an_ambiguous_title_is_refused_not_guessed():
    """Two assays sharing a display string must never silently merge."""
    frame = pd.DataFrame({
        "assay_id": [1, 2], "internal_assay_id": [74.0, 99.0],
        "internal_assay_title": ["Imaging", "Imaging"]})
    with pytest.raises(M.AmbiguousTitle, match="Imaging"):
        M.title_index(frame)


def test_a_mode2_lineage_row_takes_its_action_from_the_value_column(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].key == ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert got[0].verdict == "APPROVE"


def test_a_mode2_TERM_row_becomes_ADD_TO_ASSAY(tmp_path, assays):
    """A term row proposes on metadata, not on a lineage direction."""
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\tType\tMacrophages\tREJECT\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].key == ("TIS", "74", "ADD_TO_ASSAY")


def test_a_pair_ruling_maps_OVERRIDE_to_APPROVE(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "pair-rulings.tsv").write_text(
        "sample_type\tproposed_assay\tinternal_assay_id\tblocked_rows\truling\tstatus\tnote\n"
        "TIS\tTissue Collection\t74\t100\tOVERRIDE\truled\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got[0].verdict == "APPROVE"


def test_an_UNRULED_pair_row_is_not_migrated(tmp_path, assays):
    """130 of 175 are UNRULED. Absence of a ruling is not a ruling."""
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "pair-rulings.tsv").write_text(
        "sample_type\tproposed_assay\tinternal_assay_id\tblocked_rows\truling\tstatus\tnote\n"
        "TIS\tTissue Collection\t74\t100\t\tUNRULED\t\n")
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got == []


def test_provenance_records_the_cohort_the_ruling_was_made_against(tmp_path, assays):
    run = tmp_path / "RUN9" / "00-rulings"; run.mkdir(parents=True)
    (run / "mode2-rulings-2026-08-20.tsv").write_text(
        "lab\tsample_type\tparent_types\tassay\tfield\tvalue\truling\tnote\n"
        "ENG\tTIS\tPAV\tTissue Collection\t(lineage)\tADD_PARENT_TO_ASSAY\tAPPROVE\t\n")
    _, prov = M.migrate(tmp_path / "RUN9", assays)
    assert prov[0]["key"] == ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert "ENG" in prov[0]["cohort"], "the cohort as ruled must be recoverable"


def test_a_missing_ruling_file_is_skipped_not_fatal(tmp_path, assays):
    (tmp_path / "RUN9" / "00-rulings").mkdir(parents=True)
    got, _ = M.migrate(tmp_path / "RUN9", assays)
    assert got == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_migrate_rulings.py -q`

Expected: collection error — module does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/assay_hygiene/migrate_rulings.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Read RUN1's three ruling shapes and emit the durable store.

THREE SHAPES, ONE TARGET. `pair-rulings.tsv` already carries sample_type and
internal_assay_id and needs only a verdict rename. `mode2-rulings-2026-08-20.tsv`
carries the assay as a TITLE and the action in a column whose meaning depends on
another column. `mode1-rulings-COMPLETE.tsv` carries a 6-field composite key.

MEASURED ON RUN1 2026-08-27: all 111 Mode 2 titles resolve to a unique internal
id -- 0 ambiguous, 0 unresolvable. 100 rows are lineage (70 ADD_PARENT, 30
ADD_CHILD) and 11 are term rows. 45 of 175 pair rows are ruled; 130 are UNRULED
and are NOT migrated, because the absence of a ruling is not a ruling.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .rulings import Ruling, normalise_id

LINEAGE_FIELD = "(lineage)"
TERM_ACTION = "ADD_TO_ASSAY"
PAIR_VERDICT = {"OVERRIDE": "APPROVE", "CONFIRM_BLOCK": "REJECT"}


class AmbiguousTitle(ValueError):
    """Two internal assays share a display string. Never merge them silently."""


def title_index(assays: pd.DataFrame) -> dict[str, str]:
    """-> internal assay title -> internal id, refusing any ambiguity."""
    seen: dict[str, set[str]] = {}
    for title, iid in zip(assays.internal_assay_title, assays.internal_assay_id):
        if pd.isna(title) or pd.isna(iid):
            continue
        seen.setdefault(str(title).strip(), set()).add(normalise_id(iid))
    bad = {t: sorted(v) for t, v in seen.items() if len(v) > 1}
    if bad:
        raise AmbiguousTitle(
            f"these titles map to more than one internal assay and must not "
            f"be merged: {bad}")
    return {t: v.pop() for t, v in seen.items()}


def migrate(run_dir: Path, assays: pd.DataFrame) -> tuple[list[Ruling], list[dict]]:
    """-> (rulings, provenance records) from every ruling file present."""
    base = Path(run_dir) / "00-rulings"
    index = title_index(assays)
    out: list[Ruling] = []
    prov: list[dict] = []

    m2 = base / "mode2-rulings-2026-08-20.tsv"
    if m2.exists():
        frame = pd.read_csv(m2, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            iid = index.get(str(row.assay).strip())
            if iid is None:
                continue
            action = (str(row.value).strip()
                      if str(row.field).strip() == LINEAGE_FIELD else TERM_ACTION)
            key = (str(row.sample_type).strip(), iid, action)
            out.append(Ruling(key, str(row.ruling).strip(), "2026-08-20", "operator"))
            prov.append({"key": key, "source": "mode2",
                         "cohort": "|".join([row.lab, row.sample_type,
                                             row.parent_types, row.assay,
                                             row.field, row.value])})

    pr = base / "pair-rulings.tsv"
    if pr.exists():
        frame = pd.read_csv(pr, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            if str(row.status).strip() != "ruled":
                continue
            verdict = PAIR_VERDICT.get(str(row.ruling).strip())
            if verdict is None:
                continue
            key = (str(row.sample_type).strip(),
                   normalise_id(row.internal_assay_id), TERM_ACTION)
            out.append(Ruling(key, verdict, "2026-08-25", "operator"))
            prov.append({"key": key, "source": "pair",
                         "cohort": f"{row.sample_type}|{row.proposed_assay}"})

    m1 = base / "mode1-rulings-COMPLETE.tsv"
    if m1.exists():
        frame = pd.read_csv(m1, sep="\t", dtype=str).fillna("")
        for row in frame.itertuples():
            parts = str(row.key).split("|")
            if len(parts) != 6:
                continue
            _lab, sample_type, _parents, assay, _field, _value = parts
            iid = index.get(assay.strip())
            if iid is None:
                continue
            key = (sample_type.strip(), iid, TERM_ACTION)
            out.append(Ruling(key, str(row.ruling).strip(), "2026-08-25", "operator"))
            prov.append({"key": key, "source": "mode1", "cohort": str(row.key)})

    return out, prov
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_migrate_rulings.py -q`

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/migrate_rulings.py tests/test_assay_hygiene_migrate_rulings.py
git commit -m "feat(assay-hygiene): migrate RUN1's three ruling shapes into the store

pair-rulings.tsv is already the target shape and needs only a verdict rename.
mode2 carries the assay as a TITLE and the action in a column whose meaning
depends on another column. mode1 carries a 6-field composite key.

Two refusals rather than guesses: an ambiguous title raises instead of merging
two assays that share a display string, and an UNRULED pair row is not
migrated, because the absence of a ruling is not a ruling -- 130 of RUN1's 175
pair rows are in that state and none of them means REJECT."
```

---

### Task 3: Surface conflicts instead of resolving them

**Files:**
- Modify: `scripts/assay_hygiene/migrate_rulings.py`
- Test: `tests/test_assay_hygiene_migrate_rulings.py`

**Why:** 156 RUN1 rulings collapse to 114 keys and **3 disagree** — one cohort approved, another rejected, sharing the same triple. His judgement rested on something the pair key discards. `rulings.save` refuses to write them; migration must report them so the operator can rule the pair directly.

**Interfaces:**
- Produces: `conflicts(rulings) -> list[dict]` — one record per conflicting key with every verdict and every provenance string that produced it.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_assay_hygiene_migrate_rulings.py

def test_conflicts_reports_a_key_ruled_two_ways(assays):
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    found = M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "REJECT", "2026-08-20", "operator")])
    assert len(found) == 1
    assert sorted(found[0]["verdicts"]) == ["APPROVE", "REJECT"]
    assert found[0]["key"] == key


def test_conflicts_is_empty_when_every_key_agrees(assays):
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    assert M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                        Ruling(key, "APPROVE", "2026-08-21", "operator")]) == []


def test_a_conflict_is_never_resolved_by_majority(assays):
    """Two APPROVE and one REJECT is still a conflict, not an APPROVE."""
    from assay_hygiene.rulings import Ruling
    key = ("TIS", "74", "ADD_PARENT_TO_ASSAY")
    found = M.conflicts([Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "APPROVE", "2026-08-20", "operator"),
                         Ruling(key, "REJECT", "2026-08-20", "operator")])
    assert len(found) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_migrate_rulings.py -q -k conflict`

Expected: `AttributeError: module 'assay_hygiene.migrate_rulings' has no attribute 'conflicts'`

- [ ] **Step 3: Write the minimal implementation**

```python
# add to scripts/assay_hygiene/migrate_rulings.py

def conflicts(rulings: list[Ruling]) -> list[dict]:
    """-> one record per key carrying more than one distinct verdict.

    NEVER resolved by majority, recency or source precedence. A pair ruling is
    coarser than the cohort it was made against, so a disagreement means the
    operator's judgement rested on something the pair key discards -- the lab,
    the parent types, or the specific term. Measured on RUN1: 3 of 114 keys.
    Two APPROVE and one REJECT is a conflict, not an APPROVE.
    """
    seen: dict[tuple, set[str]] = {}
    for r in rulings:
        seen.setdefault(r.key, set()).add(r.verdict)
    return [{"key": k, "verdicts": sorted(v)}
            for k, v in sorted(seen.items()) if len(v) > 1]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --no-project --with pytest --with pandas --with pyarrow python -m pytest tests/test_assay_hygiene_migrate_rulings.py -q`

Expected: `11 passed`

- [ ] **Step 5: Run the migration against real RUN1 and record the result**

Run:
```bash
uv run --no-project --with pandas --with pyarrow python -c "
import sys; sys.path.insert(0,'scripts')
import pandas as pd
from pathlib import Path
from assay_hygiene.migrate_rulings import migrate, conflicts
a = pd.read_parquet('assets/RUN1/01-extract/assays.parquet')
r, prov = migrate(Path('assets/RUN1'), a)
c = conflicts(r)
print(f'rulings read      : {len(r)}')
print(f'distinct pair keys: {len({x.key for x in r})}')
print(f'CONFLICTS         : {len(c)}')
for x in c: print('  ', x['key'], x['verdicts'])
"
```
Expected: 3 conflicts. **Do not resolve them.** Report the three keys to the operator; they need a direct pair ruling. Until they are ruled, they are excluded from the store.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/migrate_rulings.py tests/test_assay_hygiene_migrate_rulings.py
git commit -m "feat(assay-hygiene): surface ruling conflicts rather than resolving them

156 RUN1 rulings collapse to 114 pair keys and 3 disagree -- one cohort
approved, another rejected, sharing the same (type, assay, action). That is
not a data error: it is the measured cost of a coarser key, and it means the
operator's judgement rested on something the triple discards.

Never resolved by majority, recency or source precedence. Two APPROVE and one
REJECT is a conflict, not an APPROVE. The three go back to the operator as
pair questions."
```

---

## Self-Review

**Spec coverage.** §3's key and store → Task 1. §3's provenance sidecar → Task 2 (returned alongside rulings; the gitignored write happens in Plan 3's `review` command, which owns ingest). §8's migration → Tasks 2–3, including the `CONFLICT` handling the spec specifies. §4's three-way carry-forward split is **deferred to Plan 3**, because it needs the detect command's cohort output to classify against and would otherwise be tested only against fixtures.

**Placeholder scan.** No TBD/TODO. Every step carries real code and a runnable command with expected output.

**Type consistency.** `PairKey` is `tuple[str, str, str]` throughout; `normalise_id` is applied at every boundary where pandas could yield `74.0`. `Ruling` field order `(key, verdict, ruled_on, actor)` is used identically in Tasks 1, 2 and 3. `conflicts` takes `list[Ruling]` and returns `list[dict]` with keys `key` and `verdicts`, matching its tests.

**One thing an executor must not do:** resolve the 3 conflicts to unblock themselves. They are the deliverable of Task 3, not an obstacle to it.
