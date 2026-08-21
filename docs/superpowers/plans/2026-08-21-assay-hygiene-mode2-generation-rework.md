# Mode 2 Generation Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Mode 2 emitting ~99,449 proposals that name a (sample type, assay) pair the house has never made, without deleting the ~2,035 legitimate first-of-a-kind registrations hidden inside them, and hand the operator a review artifact whose every row carries a writable target.

**Architecture:** The reachability rule already exists in `gate.type_registration_index` and already blocks metadata claims. The lineage lane never meets it because a lineage-only key carries no claim. The fix threads reachability into `classify.Evidence` — the four-boolean input to the precedence — as a fifth boolean, adds one new precedence step (`PRE_UNREACHABLE`) that claims unreachable lineage keys so they are emitted, classified and visible rather than silently dropped, and adds a bootstrap lane so a genuinely-new (type, assay) pair is a distinguishable finding rather than noise. Nothing is deleted; 99,449 rows move off the primary review surface onto a separate one.

**Tech Stack:** Python 3.11+, pandas 3.0.5, pyarrow, pytest. Run everything through `uv`. The package is `scripts/assay_hygiene/`, imported as `assay_hygiene` with `PYTHONPATH=scripts`.

**Spec:** `docs/findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md` (this session's audit, with measured row impacts) and `assay-hygiene-bak/findings/2026-08-21-independent-blind-review.md` (an independent blind review that corroborated it). Both travel with this plan; executors read both.

## Global Constraints

- **Nothing writes.** No task in this plan touches MySQL, Neo4j or the NExtSEEK API. Do not run `driver_extract.py`, `driver_stage0.py` or `stage0_apply.py`.
- **Nothing is deleted.** Every row the rework removes from the primary surface must still be emitted, classified and counted. A row that vanishes reads, to a curator, exactly like a row that was never generated — and this package has already shipped that defect once.
- **An absence is never a verdict.** Where a value could not be measured, the answer is "not measured", never a measured negative. This is the recurring bug class both audits name. `type_registrations is None` (a typeless sample) must NOT block; only `== 0` blocks.
- **Every figure is re-derived, never quoted.** Any count written into a docstring, report or commit message must come from a command run in that task. The two audits found stale figures in documents whose subject was stale figures.
- **The suite baseline is 1220 passed / 12 skipped**, measured 2026-08-21 after Task 1. It is NOT the 1196/16 quoted in earlier documents: commit `1477277` moved the working directory out of the repo, so 21 tests skipped for a missing `assay-hygiene/` and more for absent test deps. Both are fixed — `assay-hygiene/` is now a tree of symlinks into `assay-hygiene-bak/` (128K, no duplication), and the pytest invocation below carries `jinja2` and `pyyaml`. Some remaining skips are the rulings fixtures, which Task 9 restores.
- Run tests: `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests --with jinja2 --with pyyaml pytest tests/ -q`
- **The suite count rises by exactly 1 for every new `.py` file added anywhere under `scripts/`.** `tests/test_path_anchoring.py:135-139` globs `scripts/**/*.py`, excluding any path containing a `generated` part and `scripts/refresh_context.py`. So a task that adds a module — in `assay_hygiene/` or elsewhere under `scripts/` — reports one extra PASS, and that is not breakage. Task 2 added `baseline.py` and took the count to **1221 passed / 12 skipped**. State your own expected count in your report and say which files you added.
- **Test discipline, from `tests/test_assay_hygiene_classify.py`'s own header:** every guard reads its expected value off the frame AND simulates the wrong rule by hand, asserting the two DIFFER. A test that asserts a count proves only that the code produced that count.
- **Artifacts live at `assay-hygiene-bak/`,** not `assay-hygiene/`. The working directory was removed; read the extract from `assay-hygiene-bak/extract/` and the products from `assay-hygiene-bak/artifacts/`.
- Run scripts: `PYTHONPATH=scripts uv run --with pandas --with pyarrow python <script>`
- Run tests: `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests pytest tests/ -q`

---

## File Structure

| file | responsibility | change |
|---|---|---|
| `scripts/assay_hygiene/_schema.py` | constants: classes, gate outcomes, column contracts | add `CLS_UNREACHABLE`, `CLS_BOOTSTRAP` to `CLASSES`; add `reachable`/`precedent_supports`/`proposed_seek_assay_id` to `FINDING_COLUMNS` |
| `scripts/assay_hygiene/classify.py` | shared frame, precedence, Mode 1, compat lane, unify | `Evidence` gains a 5th boolean; `PRE_UNREACHABLE` step; `absence_keys` computes reachability; `BY_LINEAGE_AGAINST_PRECEDENT` proposal source |
| `scripts/assay_hygiene/mode2.py` | the lineage lane | test `registrations`; emit gate outcome and classification; fifth proposal source; sample-grained precedent |
| `scripts/assay_hygiene/precedent.py` | precedent mining | emit sample-grained denominators beside edge-grained |
| `tests/test_assay_hygiene_classify.py` | precedence + Mode 1 + compat + unify | new tests per task |
| `tests/test_assay_hygiene_mode2.py` | **CREATE** — the lineage lane has no direct test file today | new |
| `tests/test_assay_hygiene_rulings.py` | **CREATE** — the operator's rulings as a regression suite | new |

---

### Task 1: The fifth proposal source, before anything moves

`mode2._proposal_source` raises `ValueError` on the `(gated claim, no precedent rule)` combination. Its own docstring records that the combination occurs 0 times on the 2026-08-17 extract — a property of the data, not of the logic. Every later task in this plan moves exactly the populations that determine it, and the raise aborts the entire run. It goes first.

**Files:**
- Modify: `scripts/assay_hygiene/classify.py:169-183` (the `BY_*` family and `PROPOSAL_SOURCES`)
- Modify: `scripts/assay_hygiene/mode2.py:415-454` (`_proposal_source`)
- Test: `tests/test_assay_hygiene_mode2.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `classify.BY_CLAIM_NO_RULE = "BY_CLAIM_NO_RULE"`, added to `classify.PROPOSAL_SOURCES`. `mode2._proposal_source(rule, claim, sample_id, assay_id) -> str` no longer raises.

- [ ] **Step 1: Write the failing test**

Create `tests/test_assay_hygiene_mode2.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The lineage lane's own tests. This file did not exist before this plan.

`mode2.py` is 806 lines and generates 167,454 of the 170,786 findings rows, and
until now it was exercised only incidentally through
`tests/test_assay_hygiene_classify.py`. Both audits of 2026-08-21 noted that the
one module with no direct test file is where the defects concentrated.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import classify as X  # noqa: E402
from assay_hygiene import mode2 as M2  # noqa: E402


class _Claim:
    """The duck-typed shape `_proposal_source` reads. It touches no attribute."""


def test_a_gated_claim_with_no_precedent_rule_names_its_own_source():
    """The combination the function used to raise on.

    It occurs 0 times on the 2026-08-17 extract, which is a fact about that
    extract. The reachability rework moves the populations that determine it,
    so the run must not abort the first time one appears.
    """
    got = M2._proposal_source(None, _Claim(), sample_id=1, assay_id=2)
    assert got == X.BY_CLAIM_NO_RULE
    assert got in X.PROPOSAL_SOURCES
    # ...and the wrong answers, simulated by hand, DIFFER. BY_BOTH would assert
    # a precedent that is not there; BY_LINEAGE_ONLY would hide the claim.
    assert got != X.BY_BOTH
    assert got != X.BY_LINEAGE_ONLY


def test_the_other_three_combinations_are_unchanged():
    rule = M2.Rule(1, 2, 3, 0.5, 0.25)
    assert M2._proposal_source(rule, _Claim(), 1, 2) == X.BY_BOTH
    assert M2._proposal_source(rule, None, 1, 2) == X.BY_PRECEDENT
    assert M2._proposal_source(None, None, 1, 2) == X.BY_LINEAGE_ONLY
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow pytest tests/test_assay_hygiene_mode2.py -q`
Expected: FAIL — `AttributeError: module 'assay_hygiene.classify' has no attribute 'BY_CLAIM_NO_RULE'`

- [ ] **Step 3: Add the constant**

In `scripts/assay_hygiene/classify.py`, after `BY_LINEAGE_ONLY` (line 182):

```python
# The fourth combination of (precedent rule, gated claim), which `mode2.
# _proposal_source` raised on until 2026-08-21. Its absence was a property of
# the 2026-08-17 extract and not of the logic, and the reachability rework moves
# exactly the populations that determine it. Named for what it IS -- a claim
# with no measured hop -- rather than widened out of `BY_BOTH`, which means
# "precedent proposed, the claim disambiguated" and would assert a rate that is
# not there.
BY_CLAIM_NO_RULE = "BY_CLAIM_NO_RULE"
PROPOSAL_SOURCES = (BY_CLAIM, BY_PRECEDENT, BY_BOTH, BY_LINEAGE_ONLY,
                    BY_CLAIM_NO_RULE)
```

- [ ] **Step 4: Replace the raise**

In `scripts/assay_hygiene/mode2.py`, import `BY_CLAIM_NO_RULE` alongside the other `BY_*` names, then replace the `raise ValueError(...)` block at the end of `_proposal_source` with:

```python
    return BY_CLAIM_NO_RULE
```

Update the docstring's "RAISES ON THE FOURTH" paragraph to record that the fourth combination is now named, that it occurred 0 times on the 2026-08-17 extract, and that this plan's reachability change is why it stopped being safe to raise.

- [ ] **Step 5: Run the new tests and the full suite**

Run: `uv run --with pytest --with pandas --with pyarrow pytest tests/test_assay_hygiene_mode2.py -q`
Expected: PASS (2 tests)

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests pytest tests/ -q`
Expected: 1198 passed / 16 skipped (baseline 1196 + 2 new). Any other delta means something else broke — stop and diagnose.

- [ ] **Step 6: Commit**

```bash
git add tests/test_assay_hygiene_mode2.py scripts/assay_hygiene/classify.py scripts/assay_hygiene/mode2.py
git commit -m "fix(assay-hygiene): name the fourth proposal source instead of aborting the run"
```

---

### Task 2: Pin the current output as a measured baseline

Every later task claims a row delta. Those claims must be checked against something. This task writes the current figures down, derived rather than quoted, so each subsequent task can prove its own impact instead of asserting it.

**Files:**
- Create: `scripts/assay_hygiene/baseline.py`
- Create: `docs/findings/2026-08-21-pre-rework-baseline.md` (generated, committed)

**Interfaces:**
- Consumes: nothing.
- Produces: `baseline.measure(findings_csv: str, extract_dir: str) -> dict[str, int]` and `baseline.main(...) -> int`, printing a markdown table.

- [ ] **Step 1: Write the measurement script**

Create `scripts/assay_hygiene/baseline.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The pre-rework figures, DERIVED, so every later delta can be checked.

NOT A TEST AND NOT A CONTRACT. This is a photograph of the output as it stood
before the reachability rework, taken so that a task claiming "-99,449 rows" can
be held to it. Both audits of 2026-08-21 found stale figures in documents whose
subject was stale figures; the defence is to re-derive, never to quote.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASELINE_KEYS = (
    "rows", "rows_mode_1", "rows_mode_2", "rows_no_mode",
    "mode2_unreachable", "mode2_reachable",
    "mode2_without_a_gate_outcome",
    "by_precedent_with_no_coregistration",
    "rows_with_a_fallback_namespace_id",
)


def measure(findings_csv: str, extract_dir: str) -> dict[str, int]:
    f = pd.read_csv(findings_csv, low_memory=False)
    assays = pd.read_parquet(Path(extract_dir) / "assays.parquet")
    genuine = {int(x) for x in assays.internal_assay_id.dropna()}
    m2 = f[f["mode"] == "MODE_2"]
    return {
        "rows": len(f),
        "rows_mode_1": int((f["mode"] == "MODE_1").sum()),
        "rows_mode_2": len(m2),
        "rows_no_mode": int(f["mode"].isna().sum()),
        "mode2_unreachable": int((m2.type_registrations == 0).sum()),
        "mode2_reachable": int((m2.type_registrations > 0).sum()),
        "mode2_without_a_gate_outcome": int(m2.gate.isna().sum()),
        "by_precedent_with_no_coregistration": int(
            ((f.proposed_by == "BY_PRECEDENT") & (f.precedent_n_both == 0)).sum()),
        "rows_with_a_fallback_namespace_id": int(
            (~f.proposed_internal_assay_id.astype(int).isin(genuine)).sum()),
    }


def main(findings_csv="assay-hygiene-bak/artifacts/findings.csv",
         extract_dir="assay-hygiene-bak/extract") -> int:
    got = measure(findings_csv, extract_dir)
    print("| key | rows |")
    print("|---|---|")
    for k in BASELINE_KEYS:
        print(f"| `{k}` | {got[k]:,} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
```

- [ ] **Step 2: Run it and capture the output**

Run:
```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.baseline > /tmp/baseline.md && cat /tmp/baseline.md
```

Expected, from this session's audit — **verify each, and if any differs, stop and reconcile before proceeding**:

| key | rows |
|---|---|
| `rows` | 170,786 |
| `rows_mode_1` | 1,373 |
| `rows_mode_2` | 167,454 |
| `rows_no_mode` | 1,959 |
| `mode2_unreachable` | 99,449 |
| `mode2_without_a_gate_outcome` | 166,586 |
| `by_precedent_with_no_coregistration` | 115,087 |
| `rows_with_a_fallback_namespace_id` | 1,321 |

- [ ] **Step 3: Write the baseline document**

Create `docs/findings/2026-08-21-pre-rework-baseline.md` containing the generated table, the exact command that produced it, the extract date, and one sentence: "Every row-impact claim in `docs/superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md` is measured against this table."

- [ ] **Step 4: Commit**

```bash
git add scripts/assay_hygiene/baseline.py docs/findings/2026-08-21-pre-rework-baseline.md
git commit -m "chore(assay-hygiene): pin the pre-rework figures, derived not quoted"
```

---

### Task 3: Reachability reaches the lineage lane

The core change. `gate.type_registration_index` already holds the rule and `gate.gate_claims` already blocks a *claim* on it. A lineage-only key carries no claim, so nothing puts it in front of the gate. This threads the same measurement into the precedence as a fifth `Evidence` boolean and gives unreachable lineage keys their own step, so they are emitted, classified and counted rather than dropped.

**Why a new step and not a filter:** `PRE_LINEAGE` becoming `e.lineage and e.reachable` would send an unreachable lineage-only key (no claim) falling through `PRE_COMPAT` — which tests `e.claim` — to `PRE_MODE_3`, which claims nothing, and `precedence_step` would raise. A dedicated step keeps the "exactly one step claims each key" contract and makes the population visible in the census.

**Files:**
- Modify: `scripts/assay_hygiene/_schema.py:619-623` (`CLASSES`)
- Modify: `scripts/assay_hygiene/classify.py:690-696` (`PRECEDENCE`), `:735-744` (`Evidence`), `:760-781` (`_PRECEDENCE_TESTS`), `:814-875` (`absence_keys`)
- Modify: `scripts/assay_hygiene/mode2.py:586-624` (emit the outcome)
- Test: `tests/test_assay_hygiene_classify.py`, `tests/test_assay_hygiene_mode2.py`

**Interfaces:**
- Consumes: `classify.BY_CLAIM_NO_RULE` (Task 1).
- Produces:
  - `_schema.CLS_UNREACHABLE = "CLS_UNREACHABLE"`, appended to `CLASSES`
  - `classify.PRE_UNREACHABLE = "PRE_UNREACHABLE"`, in `PRECEDENCE` between `PRE_LINEAGE` and `PRE_COMPAT`
  - `classify.Evidence(claim, claim_reaches, unregistered, lineage, reachable)` — five booleans
  - `classify.absence_keys(attached, *, population, registered, candidates, type_reg, types, uuid_of)` — three new keyword-only arguments
  - `mode2.mode2_findings` unchanged in signature; rows now carry `gate = S.GATE_UNREACHABLE` and `classification = S.CLS_UNREACHABLE` where unreachable

- [ ] **Step 1: Write the failing precedence tests**

Append to `tests/test_assay_hygiene_classify.py`:

```python
def test_an_unreachable_lineage_key_is_claimed_by_its_own_step_not_dropped():
    """The defect this rework exists to fix.

    A lineage neighbour holds an assay no sample of this type has ever been
    registered in. Before this change the key went to PRE_LINEAGE and was
    emitted as an ordinary proposal; 99,449 of 167,454 Mode 2 rows on the
    2026-08-17 extract were of this shape.
    """
    e = X.Evidence(claim=False, claim_reaches=False, unregistered=False,
                   lineage=True, reachable=False)
    assert X.precedence_step(e) == X.PRE_UNREACHABLE
    # ...and the OLD rule, simulated by hand, gives a different answer. Without
    # this the test cannot tell the new contract from the old one.
    old = (X.PRE_GATE, X.PRE_MODE_1, X.PRE_LINEAGE, X.PRE_COMPAT, X.PRE_MODE_3)
    assert X.precedence_step(e, order=old) == X.PRE_LINEAGE


def test_a_reachable_lineage_key_is_unaffected():
    e = X.Evidence(claim=False, claim_reaches=False, unregistered=False,
                   lineage=True, reachable=True)
    assert X.precedence_step(e) == X.PRE_LINEAGE


def test_a_sample_with_no_resolvable_type_is_not_blocked():
    """AN ABSENCE IS NOT A VERDICT -- the bug class both audits name.

    `type_registration_index` has no cell for a sample carrying no type, so
    nothing was measured. Reading that as 'never registered' would block a
    proposal on evidence nobody gathered. `absence_keys` maps unknown to
    reachable=True for exactly this reason.
    """
    e = X.Evidence(claim=False, claim_reaches=False, unregistered=False,
                   lineage=True, reachable=True)   # unknown -> True
    assert X.precedence_step(e) == X.PRE_LINEAGE


def test_every_evidence_tuple_is_still_claimed_by_exactly_one_step():
    """Exhaustive over all 32 combinations. No key may fall through."""
    import itertools
    for bits in itertools.product([False, True], repeat=5):
        e = X.Evidence(*bits)
        if e.claim_reaches and not e.claim:
            continue                      # constructible by hand, refused by design
        step = X.precedence_step(e)
        assert step in X.PRECEDENCE
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --with pytest --with pandas --with pyarrow pytest tests/test_assay_hygiene_classify.py -q -k "unreachable or no_resolvable_type or exactly_one_step"`
Expected: FAIL — `TypeError: Evidence.__new__() missing 1 required positional argument: 'reachable'`

- [ ] **Step 3: Add the class constant**

In `scripts/assay_hygiene/_schema.py`, after `CLS_UNRESOLVED` (line 622):

```python
CLS_UNREACHABLE = "CLS_UNREACHABLE"           # no sample of this type is ever
                                              # registered in this assay
CLASSES = (CLS_ABSENCE_LINEAGE, CLS_ABSENCE_COMPAT, CLS_ALT_LABEL,
           CLS_UNRESOLVED, CLS_UNREACHABLE)
```

- [ ] **Step 4: Extend `Evidence` and the precedence**

In `scripts/assay_hygiene/classify.py`, add the field at line 744:

```python
    reachable: bool         # a sample of this TYPE is registered in this assay
                            # SOMEWHERE -- or no type could be resolved, which is
                            # not the same as a measured zero and does not block
```

Add the step constant beside the others (near line 695) and insert it into `PRECEDENCE`:

```python
PRE_UNREACHABLE = "PRE_UNREACHABLE"   # a neighbour carries it, but no sample of
                                      # this type ever has
PRECEDENCE = (PRE_GATE, PRE_MODE_1, PRE_LINEAGE, PRE_UNREACHABLE, PRE_COMPAT,
              PRE_MODE_3)
```

Amend the two lineage tests in `_PRECEDENCE_TESTS`:

```python
    # 3. lineage. A neighbour holds it AND the house has made this (type, assay)
    #    registration before. The second half is new: `gate.
    #    type_registration_index` calls a pair absent from it "INCREDIBLE
    #    whatever the term's support" and BLOCKS a claim on it, and until
    #    2026-08-21 this lane never met that rule.
    PRE_LINEAGE: lambda e: e.lineage and e.reachable,
    # 4. a neighbour holds it and NO sample of this type ever has. Its own step
    #    and its own lane: the row is still emitted, carrying GATE_UNREACHABLE,
    #    so a curator can override it. Dropping it here would delete 99,449
    #    proposals with nothing in any artifact saying they existed.
    PRE_UNREACHABLE: lambda e: e.lineage,
```

`PRE_UNREACHABLE` needs no `not e.reachable`: it sits after `PRE_LINEAGE`, which already took every reachable lineage key. Restating the predecessor's condition would make the ORDER unobservable — the cascade rule this dict's own comment states.

- [ ] **Step 5: Compute reachability in `absence_keys`**

Add three keyword-only parameters and the derivation. In both loops, replace the `Evidence(...)` construction so `reachable` is computed once:

```python
def _reachable(sample_id, assay_id, type_reg, types, uuid_of) -> bool:
    """Is a sample of this TYPE registered in this assay anywhere?

    THREE STATES COLLAPSED TO TWO, AND THE DIRECTION IS DELIBERATE. A missing
    (type, assay) CELL is a measured zero -- `type_registration_index` holds a
    cell for every pair that occurs. A missing TYPE is not measured at all, and
    that answer is True: the gate refuses to assert what was not established,
    which is the same direction `audit.audit_contradictions` refuses a
    contradiction it cannot resolve.
    """
    stype = types.get(uuid_of.get(sample_id))
    if stype is None:
        return True
    return type_reg.get((stype, assay_id), 0) > 0
```

Thread it into both `Evidence(...)` calls in `absence_keys`, and document the three new arguments in the docstring with the same "PASSED IN rather than re-derived" argument the function already makes for `population` and `candidates` — a second opinion here about which pairs are reachable would put the precedence and the gate on two different worlds.

- [ ] **Step 6: Run the precedence tests**

Run: `uv run --with pytest --with pandas --with pyarrow pytest tests/test_assay_hygiene_classify.py -q -k "unreachable or no_resolvable_type or exactly_one_step"`
Expected: PASS (4 tests). Other tests in the file will now fail on the `Evidence` arity and on `absence_keys`' signature — that is expected and Step 7 fixes them.

- [ ] **Step 7: Update every caller**

Find them: `grep -rn "Evidence(\|absence_keys(" scripts/ tests/`. Update each construction to pass `reachable`, and each `absence_keys` call to pass `type_reg`, `types`, `uuid_of`. In `classify.main` and `run_detect.py` those three are already in scope — they are built for `gate_claims` and `mode2_findings`. Pass the same objects; do not build second copies.

- [ ] **Step 8: Emit the outcome on the row**

In `scripts/assay_hygiene/mode2.py`, after `registrations` is computed (line 590), derive the two columns and use them in the row dict:

```python
        # THE GATE'S OWN RULE, APPLIED TO THIS LANE AT LAST. `registrations == 0`
        # is what `gate.gate_claims` calls GATE_UNREACHABLE and BLOCKS a claim
        # on. `None` is a sample with no resolvable type -- nobody measured, so
        # nothing is asserted and the row passes.
        unreachable = registrations == 0
        row_gate = (S.GATE_UNREACHABLE if unreachable
                    else (claim.gate if claim is not None else None))
        row_class = (S.CLS_UNREACHABLE if unreachable else S.CLS_ABSENCE_LINEAGE)
```

Replace `"gate": claim.gate if claim is not None else None,` with `"gate": row_gate,` and `"classification": S.CLS_ABSENCE_LINEAGE,` with `"classification": row_class,`.

- [ ] **Step 9: Wire the new lane into `unify_findings`**

**In `classify.main` ONLY.** `run_detect.py` does NOT build a `lanes` dict and does not call `unify_findings` — its module docstring (lines 16-24) records that re-assembling the lanes there was the obvious shape, was tried, and was rejected because `unify_findings` silently drops a whole mode when a lane is omitted. It reads the files `classify.main` wrote instead. Do not touch it.

Add the Mode 2 frame under the new step as well:

```python
    lanes = {
        X.PRE_MODE_1: mode1,
        X.PRE_LINEAGE: mode2,
        X.PRE_UNREACHABLE: mode2,   # the SAME frame; `unify_findings` filters
                                    # each lane by the step that owns each key,
                                    # so every row lands in exactly one
        X.PRE_COMPAT: compat,
        X.PRE_MODE_3: mode3,
    }
```

- [ ] **Step 10: Write the end-to-end test**

Append to `tests/test_assay_hygiene_mode2.py` a test that builds a small world where one lineage pair is reachable and one is not, runs the full `mode2_findings` → `unify_findings` path, and asserts: both rows are emitted; the unreachable one carries `gate == S.GATE_UNREACHABLE` and `classification == S.CLS_UNREACHABLE`; the reachable one carries `CLS_ABSENCE_LINEAGE`; and **the total row count is unchanged from before the rework** — nothing was deleted, only reclassified.

Use **`_pipeline2(w=None)` at `tests/test_assay_hygiene_classify.py:1473`**, not `_pipeline`. `_pipeline2` is the Mode 2 world and returns `(w, bundle, findings)` where `bundle` is the keyword-argument dict `mode2_findings` takes — so a test needing to perturb one index does it by name rather than by rebuilding the call. `_pipeline` at `:271` is the Mode 1 world and returns six values.

- [ ] **Step 11: Extend the census, then run the full suite**

The census will break, and that is it doing its job. Extend it deliberately rather than routing around it:

- `FINDINGS_CENSUS_KEYS` (`classify.py:1352-1356`) gains **`keys_unreachable`**, produced in `findings_census` (`:1427`) as `counts[PRE_UNREACHABLE]` alongside its siblings.
- The first stated identity (`classify.py:1318-1319`) becomes:
  `input_keys = keys_refused_by_the_gate + keys_mode_1 + keys_lineage + keys_unreachable + keys_compat + keys_mode_3`
- `FINDINGS_CENSUS_KEYS` also gains **`rows_cls_unreachable`**, and the fourth identity becomes the **five** `rows_cls_*` keys plus `rows_without_a_classification`.
- **Do NOT add `PRE_UNREACHABLE` to `NON_EMITTING_STEPS`.** It has a lane and it emits; the second identity (`rows = input_keys − keys claimed by NON_EMITTING_STEPS`) must keep subtracting `PRE_GATE` alone. Adding it there would restore exactly the silent-drop the tuple exists to prevent.

Then run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests --with jinja2 --with pyyaml pytest tests/ -q`
Expected: all green, at the baseline count (this task adds no new `.py` file to the package).

- [ ] **Step 12: Measure the real impact**

Re-run detection over the real extract, then re-run `baseline.measure` against the new `findings.csv` and diff it against Task 2's table. Record the actual numbers in the commit message.

Expected: `rows` unchanged at 170,786; `rows` carrying `CLS_UNREACHABLE` ≈ 99,449; `mode2_without_a_gate_outcome` falls by the same amount. **If `rows` changed at all, something was dropped — stop.**

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "feat(assay-hygiene): the lineage lane finally meets the reachability gate"
```

---

### Task 4: The bootstrap lane

The independent review puts ~2,035 legitimate first-of-a-kind registrations inside the 99,449. The assay-143 finding turned on exactly such a case being right, and 47 unreachable cohorts were approved by agents reading the biology. An unreachable pair is not automatically wrong — it is a claim that the house has a systematic gap, and that is a different review question deserving a different sheet.

**Files:**
- Modify: `scripts/assay_hygiene/_schema.py` (`CLS_BOOTSTRAP`)
- Modify: `scripts/assay_hygiene/mode2.py`
- Test: `tests/test_assay_hygiene_mode2.py`

**Interfaces:**
- Consumes: Task 3's `CLS_UNREACHABLE` and `row_class`.
- Produces: `_schema.CLS_BOOTSTRAP = "CLS_BOOTSTRAP"`; `mode2._bootstrap_evidence(assay_id, sample_type, type_reg, titles) -> tuple[bool, str]`.

- [ ] **Step 1: Define the discriminator, and measure it before coding it**

A `CLS_UNREACHABLE` row is a **bootstrap candidate** when the proposed assay is itself sparsely populated — the house has barely used it — rather than well-populated with other types. Proposing `D.FLOW → Tissue Collection` against 89,263 existing members of which zero are D.FLOW is a type error; proposing a type into an assay holding 3 samples total is a new assay finding its feet.

Run this first and record the split:

```python
# scratch: how many of the 99,449 sit under a sparsely-populated assay?
import pandas as pd
f = pd.read_csv("assay-hygiene-bak/artifacts/findings.csv", low_memory=False)
m = pd.read_parquet("assay-hygiene-bak/extract/membership.parquet")
a = pd.read_parquet("assay-hygiene-bak/extract/assays.parquet")
ai = {int(r.assay_id): r.internal_assay_id for r in a.itertuples() if pd.notna(r.internal_assay_id)}
pop = pd.Series([ai[int(x)] for x in m.assay_id if int(x) in ai]).value_counts()
un = f[(f["mode"] == "MODE_2") & (f.type_registrations == 0)]
size = un.proposed_internal_assay_id.map(pop).fillna(0)
for t in (10, 50, 100, 500):
    print(f"assay holds < {t:>4} samples: {(size < t).sum():>7,} rows")
```

Choose the threshold from what this prints, not from this document. Record the chosen number and its justification in the docstring.

- [ ] **Step 2: Write the failing test**

```python
def test_an_unreachable_pair_under_a_barely_used_assay_is_a_bootstrap_candidate():
    """The assay-143 case, generalised.

    47 unreachable cohorts were approved by agents reading the biology, and the
    gpt delta finding turned on one of them being right. A blanket block would
    have deleted every one; this lane keeps them reviewable and apart.
    """
    ...  # build a world where assay 9 holds 2 samples total, none of type TIS


def test_an_unreachable_pair_under_a_heavily_used_assay_is_not():
    """D.FLOW -> Tissue Collection: 89,263 members, not one a D.FLOW.

    That is a type error, not a gap, and it must not reach the bootstrap sheet.
    """
    ...
```

- [ ] **Step 3: Implement, run, commit** — same TDD cycle as Task 3. The row keeps `gate = GATE_UNREACHABLE`; only `classification` differs, so the block still holds and the review surface can split on class.

---

### Task 5: `proposed_by` stops asserting support it does not have

115,087 rows (69.1% of all `BY_PRECEDENT` rows) carry `precedent_n_both == 0` and `precedent_rate == 0.000` — a rule stating the house has never once made that co-registration. The provenance column names precedent as the proposer in exactly the rows where precedent's content argues against.

**Files:** `scripts/assay_hygiene/classify.py`, `scripts/assay_hygiene/mode2.py`, `scripts/assay_hygiene/_schema.py` (`FINDING_COLUMNS`), `tests/test_assay_hygiene_mode2.py`

**Interfaces:** produces `_schema.FINDING_COLUMNS` gaining `precedent_supports` (nullable bool: `None` where no rule, `True` where `n_both > 0`, `False` where `n_both == 0`).

- [ ] **Step 1:** Write a test asserting that a row with a rule at `n_both == 0` carries `precedent_supports is False` while still carrying `proposed_by == BY_PRECEDENT`, and that a reader filtering `precedent_supports == True` gets a strictly smaller set than filtering `proposed_by == BY_PRECEDENT`. Assert the two counts DIFFER.
- [ ] **Step 2:** Run to verify it fails.
- [ ] **Step 3:** Add the column to `FINDING_COLUMNS` and emit it from `mode2_findings` (`None if rule is None else rule.n_both > 0`). Emit `None` from the Mode 1 and compat lanes, which have no hop.
- [ ] **Step 4:** Run tests; re-measure against the real extract and confirm 115,087 rows carry `precedent_supports == False`.
- [ ] **Step 5:** Commit.

---

### Task 6: Precedent reports a denominator a reader can interpret

`propagation_rate = n_both / (n_both + n_child_only)`, and `n_child_only` counts **edges** whose parent is, by construction, an ADD_PARENT candidate for that assay. Measured this session: 666,515 such edges raise 55,007 distinct candidates — a 12.1× fan-out inflation, worst case ~493×. `dossier.py:351` renders that number to reviewers under the reading "A low rate over MANY pairs is the house repeatedly declining it", which is never a valid reading of it.

**Note the scope, measured:** regraining the *rate* from edges to samples moves it materially on only 6 of 229 hops (median |delta| 0.000). This task fixes **what reviewers are shown**, not the ranking. Do not expect the row order to change.

**Files:** `scripts/assay_hygiene/precedent.py`, `scripts/assay_hygiene/dossier.py`, `tests/test_assay_hygiene_precedent.py`, `tests/test_assay_hygiene_dossier.py` (create — `dossier.py` has no test file)

- [ ] **Step 1:** Write a test over a hand-built world with one parent and four children, all four children registered and the parent not: assert `n_child_only == 4` (edges) while the new `parents_only == 1` (samples), and assert the two DIFFER. This is the `ALT|TIS|ADFP` case from the handoff — 1,300 apparent declines that are 325 samples × 4 children.
- [ ] **Step 2:** Run to verify it fails.
- [ ] **Step 3:** Add `n_child_only_samples` and `n_parent_only_samples` to `PRECEDENT_COLUMNS` and to `mine_precedent`'s counters (a `set` per key beside each integer).
- [ ] **Step 4:** In `dossier.py`, render both, and rewrite the `reading` string. It must no longer say a low rate over many pairs is the house declining; it must say the count is of edges belonging to the samples being proposed.
- [ ] **Step 5:** Run tests, re-measure, commit.

---

### Task 7: `GATE_INCOHERENT` stops killing independent lineage evidence

`PRE_GATE` is first in the precedence and is the only non-emitting step, so a key whose claim the gate rejected produces no row at all — even when a lineage neighbour independently registers that assay. For `GATE_UNREACHABLE` that is coherent: both tests fail for the same reason. For `GATE_INCOHERENT` it is not — an incoherent term family is a defect in the *vocabulary*, which says nothing about whether the neighbour holds the assay.

**Unmeasured:** `detect-report.md` puts 4,255 lineage rows behind the gate without splitting them by outcome. **Step 1 of this task is to measure the split**, and if `GATE_INCOHERENT` accounts for a negligible share, close the task as won't-fix and record the number.

- [ ] **Step 1:** Measure. Re-run stage C with the gate outcome retained on refused keys; report `GATE_UNREACHABLE` vs `GATE_INCOHERENT` counts.
- [ ] **Step 2:** If material, split `PRE_GATE` into `PRE_GATE_UNREACHABLE` (non-emitting) and let incoherent-only keys fall through to the lineage test. Write the test first, exhaustively over the evidence tuples as in Task 3.
- [ ] **Step 3:** Run, measure, commit — or commit the measurement and a docstring recording why no change was made.

---

### Task 8: The two namespaces are marked

1,321 rows carry a raw SEEK `assays.id` in `proposed_internal_assay_id` — the fallback ids `precedent.assay_index` mints for the 17 junction-less records. The fallback is deliberate and documented; what is missing is any flag distinguishing the two, in a package whose own docstrings name SEEK/internal confusion as its signature failure. A consumer joining that column against internal ids silently drops these; joining against SEEK ids silently mismatches the other 169,465.

- [ ] **Step 1:** Write a test asserting every findings row carries `id_namespace` in `("internal", "seek_fallback")`, that exactly the junction-less ids are marked `seek_fallback`, and that a hand-simulated join against internal ids alone loses precisely the marked rows.
- [ ] **Step 2:** Run to verify it fails.
- [ ] **Step 3:** Add `id_namespace` to `FINDING_COLUMNS`; derive it in each lane from `precedent.fallback_assay_ids(assays)`, which already exists.
- [ ] **Step 4:** Run, re-measure (expect 1,321), commit.

---

### Task 9: The operator's rulings become a regression suite

This is what converts "smaller" into "trustworthy". The operator ruled 111 Mode 2 cohorts and 17 Mode 1 cohorts. The reworked detector must reproduce those judgements: if it drops a cohort he approved, or still proposes one he rejected as `WRONG_ASSAY`, the rework is wrong — and we find out before he reviews anything.

**Files:** Create `tests/test_assay_hygiene_rulings.py`; restore `assay-hygiene-bak/rulings/*.tsv` into `tests/fixtures/`.

- [ ] **Step 1:** Copy the rulings fixtures in and confirm the three currently-skipped tests run: `uv run ... pytest tests/ -q` should report 16 → 13 skips.
- [ ] **Step 2:** Write a test that, for every cohort the operator ruled `APPROVE`, asserts the reworked pipeline still emits it and does NOT classify it `CLS_UNREACHABLE`. Any that are must be listed by name in the failure message — these are the false negatives the reachability gate introduces, and the operator has to see each one.
- [ ] **Step 3:** Write the mirror: for every cohort ruled `WRONG_ASSAY` or `REJECT`, assert it is now either absent, `CLS_UNREACHABLE`, or `CLS_ALT_LABEL`. Report any still on the primary surface.
- [ ] **Step 4:** Run. **Expect failures, and treat the list as the deliverable** — it is the measured cost and benefit of the rework against ground truth. Record it.
- [ ] **Step 5:** Commit both the tests and a findings document naming every cohort that moved the wrong way.

---

### Task 10: Bound the reject-side error

132,546 agent `REJECT` verdicts were never audited in that direction; only the approve side was. At the measured ~5% false-approve floor, roughly 6–7k plausible rows may be buried there — real missing registrations that would stay missing.

- [ ] **Step 1:** Draw a random sample of 200 cohorts from the REJECT bucket with a fixed, recorded seed. `Math.random`-style irreproducibility is not acceptable here; the sample must be re-drawable.
- [ ] **Step 2:** Build a review sheet for the sample in the operator's stated format — CSV first, HTML second, cohort-level, with a punt option.
- [ ] **Step 3:** **Operator checkpoint.** He rules the 200.
- [ ] **Step 4:** Compute the false-reject rate with a confidence interval and extrapolate to the 132,546. Write it up.
- [ ] **Step 5:** If the rate is material, the REJECT bucket cannot be used as a filter and Task 11's surface must include a re-judged slice. Record the decision either way.

---

### Task 11: The review artifact

**Files:** `scripts/assay_hygiene/review_mode2.py`, `scripts/assay_hygiene/dossier.py`

- [ ] **Step 1:** Regenerate findings, cohorts and dossiers over the reworked population.
- [ ] **Step 2:** Split the output into four sheets, each with its own count printed: **primary** (reachable, singly-writable, precedent-supported), **bootstrap** (Task 4), **ambiguous target** (the 573 + 2,367 that resolve to two or more SEEK records), and **blocked** (`CLS_UNREACHABLE` non-bootstrap, present so nothing is invisible).
- [ ] **Step 3:** Every row on every sheet carries: `write_target_seek_assay_id` (from the Track A resolution stage — **this task is blocked until that lands**), gate outcome, `reachable`, `precedent_supports`, both precedent grains, `id_namespace`, and the evidence sentence.
- [ ] **Step 4:** Print a row budget at the top of the report, derived, in the shape of Task 2's baseline table so the two are diffable.
- [ ] **Step 5:** **Operator checkpoint.** Hand it over.

---

## Self-Review

**Spec coverage.** Audit defect 1 → Tasks 3, 4. Defect 2 (precedent self-reference) → Task 6. Defect 3 (internal→SEEK) → **not in this plan** — it is Track A, and Task 11 Step 3 declares the dependency. Defect 4 (assay 143) → **not in this plan**; it is a rename in `dmac.assays_internal_assays`, a table not in this repo, and the operator's call. Defect A (`PRE_GATE`) → Task 7. Defect B (null gate) → Task 3 Step 8. Defect C (crash) → Task 1. Defect D (no dossier tests) → Task 6 Step 1. Defects E/F/G → Tasks 2, 5, 8. Independent review's reject-side gap → Task 10; bootstrap → Task 4.

**Two known gaps, stated rather than papered over.** Task 11 cannot complete without Track A's resolution stage. And the cohort-key question — whether 1,123 cohorts averaging 149 rows and topping out at 29,763 is the right review unit — is unanswered by either audit and has no task here; it should be measured before Task 11 fixes a grouping in place.

**Placeholder scan.** Tasks 4, 6, 7, 8, 10 and 11 carry step-level detail rather than full code bodies. That is deliberate for Task 7 (whose first step is a measurement that may close it) and Task 10 (which is a human review loop), but Tasks 4, 6 and 8 should have their test bodies written out before execution if a subagent is to implement them cold.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session with checkpoints for review.
