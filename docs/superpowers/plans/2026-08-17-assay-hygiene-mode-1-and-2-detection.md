# Assay Hygiene Increment 2: Mode 1 and Mode 2 detection, read-only

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build stage C, the classifier, for all three modes. Decide what WOULD
change and why, write it to `findings.csv`, and re-scope increment 1's Mode 3
output by subtraction. Nothing in this increment writes to production, and no
curator workbook is produced.

**Architecture:** Two new deterministic corroboration tests join the evidence
layer increment 1 already shipped. The LINEAGE test asks whether a parent or
child already registers a claimed assay; the COMPATIBILITY test asks whether two
assays routinely coexist on a sample type. Stage C runs Mode 1 (no registration
at all, metadata decides), Mode 2 (a neighbour carries an assay this sample
lacks, precedent decides, in both directions), and Mode 3 (the residue after
both tests). A backtest produces Mode 2's threshold curve rather than a
threshold being chosen in advance.

**Tech Stack:** Python 3.11+, pandas, pyarrow, pytest. PEP 723 inline dependency
blocks, matching every other script in `scripts/`.

**Spec:** `docs/superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md`,
**as amended 2026-08-17**. Read the section "Amendment: absence is not
contradiction" before Task 1. The unamended mode table is the artifact that
produced the defect this increment exists to fix.

**This is increment 2 of 3.** Increment 1 built the evidence layer and a
mis-scoped Mode 3. Increment 3 is stages D, E and F: adjudication, the curator
workbook, and the write path behind the addition probe. **This increment writes
nothing to production and produces no APPROVE column,** because an APPROVE
column exists to gate a write and there is no write here to gate.

## Global Constraints

- **P1 sentinel:** scripts must never create, modify, or delete anything inside the plugin checkout. All project paths resolve from the current working directory. `tests/conftest.py::plugin_sentinel` enforces this and will fail the suite otherwise.
- **Output root** is `assay-hygiene/` under the current working directory.
- **PEP 723 header** on every script: `requires-python = ">=3.11"` plus explicit dependencies.
- **Test command:** `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests pytest tests/<file> -v`

  **`--with requests` is required and increment 1's plan omitted it.** Without it the suite does not run at all: `tests/test_nextseek_api_detect.py` imports `scripts/nextseek_api.py`, which imports `requests`, and collection dies with `ModuleNotFoundError` before a single test executes. Verified 2026-08-17.
- **Full suite must stay green, measured as a DELTA.** Run the full suite yourself before you start and record the number. Increment 1 recorded an absolute that turned out not to be reproducible. Every task below states how many tests it adds. Never weaken an existing assertion; a zero-deletion diff on an existing test file is the thing to verify.

  For reference only, the reading on 2026-08-17 at `8a7376b` plus this plan's two documents and the reproducer script was **901 passed, 13 skipped**. Treat that as a sanity check on your environment, not as a target: if you measure something wildly different, your environment differs from the one this plan was written against and that is worth resolving first.
- **Stale bytecode silently invalidates mutation testing on this machine.** `PYTHONPYCACHEPREFIX` is set to a shared cache. If you verify a test by breaking the implementation and the test still passes, suspect the cache before you conclude the test is weak.
- **Read-only, and harder than last time.** Increment 1 could say "no write path in this increment". This one classifies things that WILL be written in increment 3, so the temptation to "just add the writer while I'm here" is real. There is no writer in this increment. `stage0_apply.py` and `driver_stage0.py` exist in this package and carry live Cypher; nothing you build may import them.
- **Rule key is `(project_id, child_type, parent_type, internal_assay_id)`.** NOT `assays.title`, NOT `assays.id`.
- **`internal_assay_id` is NULLABLE and is a RULE_KEY component.** A pandas `groupby(RULE_KEY)` defaults to `dropna=True` and silently discards the 17 assay records with no junction row. Pass `dropna=False`, or apply the `(assay_id, assays.title)` fallback first.
- **Count ROWS, not edges.** A write is one `(sample, assay)` pair. Every population figure in this plan is a row count or a sample count and says which. An edge count overstates write volume by up to 146x on this data.
- **Every measured figure carries its scope in the sentence that states it.**
- **Percentages and counts quoted in this plan are justification, not fixtures.** Re-derive any figure before you assert it in a test or a report. If a re-derived number disagrees with this document by more than a point, STOP and report it rather than adjusting the assertion. This happened on every task of increment 1 and the implementers were right every time.
- **Commit style:** end messages with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

### A note on this plan's code blocks

Increment 1's retrospective was blunt about it: every one of its 8 tasks had at
least one defect in a code block the planner wrote, five planner-written tests
certified properties in their own titles without testing them, one failed
against the planner's own implementation, and one planner fix created a
data-loss bug.

So this plan deliberately specifies **interfaces, contracts, invariants and the
cases that must be tested**, and does not supply implementation bodies. Write
the code test-first. Where this plan does show code it is a signature or a data
shape, not a body to paste.

If you disagree with something here, measure it and say so. Every implementer on
increment 1 disagreed with something in their brief, proved it by measurement,
and was right.

## Measured starting state

All against `assay-hygiene/extract/`, taken after the stage 0 production write,
and `assay-hygiene/claims.parquet` as increment 1 produced it. Reproduce the
disposition figures with `scripts/measure_absence_vs_contradiction.py`.

```
samples in extract                       163,393
  registered in >=1 internal assay       157,069
  registered in NOTHING                    6,324   <- Mode 1 population

MODE 1, unregistered samples that carry a metadata claim
  samples                                  1,883
  (sample, assay) rows                     2,977
  at strong/corroborated tier only    719 samples / 723 rows

MODE 2 ceiling, unfiltered by precedent, both directions
  ADD_PARENT rows (child has it, parent does not)    50,508 over  39,773 samples
  ADD_CHILD  rows (parent has it, child does not)   111,039 over  97,635 samples
  union, distinct (sample, assay)                   161,420 over 110,170 samples

MODE 3, increment 1's 866 flags re-scoped by both tests
  ABSENCE_LINEAGE   351   40.5%
  ABSENCE_COMPAT    250   28.9%
  UNRESOLVED        214   24.7%
  CONTRADICTION      51    5.9%   <- what stays Mode 3
```

The Mode 2 ceiling is **unfiltered**: it is every candidate before precedent
says anything, and it is the largest number this project will ever print. It is
not a plan to write 161,420 rows. Precedent thresholds cut it down and Task 6
produces the curve that decides by how much. State it this way in the report;
an unqualified 161,420 will read as an intent to write.

### Four extract defects you must handle explicitly

Increment 1's rule is that nothing is dropped silently. All four of these are
silent drops in the natural pandas spelling.

| Defect | Size | Where it bites |
|---|---|---|
| `sample_id` in `membership` but absent from `samples.parquet` | **362** samples, all registered | any `samples`-driven loop that assumes membership resolves |
| duplicate `uuid` across `sample_id`s | 14 uuids, 28 rows | `set_index("uuid")` raises `InvalidIndexError`; `.map()` fans out |
| `childof` rows not resolvable to a sample on both ends | 755 of 742,534 | the lineage index |
| `membership` rows whose assay has no junction row | 279 | the internal-id crossing, already handled by `assay_index` |

The 362 are new and were found while writing this plan. They are registered in
an internal assay but have no row in the samples extract, so they cannot carry a
claim, cannot be typed from a uuid, and will not appear in any Mode 1 or Mode 3
population. They CAN appear as a neighbour in the lineage test. Decide
deliberately whether a neighbour you cannot type is usable evidence, document
the decision, and count them in the report either way.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/assay_hygiene/_schema.py` | MODIFY. Stage C column contracts, mode and disposition vocabulary, corroboration bands, fixture extension. |
| `scripts/assay_hygiene/lineage.py` | CREATE. Test 1. Parent/child indexes and `neighbour_registers`, with the integrity guards. |
| `scripts/assay_hygiene/compatibility.py` | CREATE. Test 2. Co-registration rate per `(sample_type, registered, claimed)` with support. |
| `scripts/assay_hygiene/classify.py` | CREATE. Stage C. Modes 1, 2 and 3 over one pass, emitting `FINDING_COLUMNS`. |
| `scripts/assay_hygiene/backtest.py` | CREATE. Mode 2's held-out recovery curve. |
| `scripts/assay_hygiene/run_detect.py` | CREATE. The wired read-only run and the operator report. |
| `scripts/measure_absence_vs_contradiction.py` | EXISTS. The spec's reproducer. Task 7 must agree with it. |
| `tests/test_assay_hygiene_lineage.py` | CREATE. |
| `tests/test_assay_hygiene_compatibility.py` | CREATE. |
| `tests/test_assay_hygiene_classify.py` | CREATE. |
| `tests/test_assay_hygiene_backtest.py` | CREATE. |

`lineage.py` and `compatibility.py` are separate modules on purpose, for the
same reason `precedent.py` and `claims.py` are: they answer different questions
against different populations and fail in unrelated ways. When a disposition
looks wrong you need to know which test to distrust. Neither imports the other.

---

### Task 1: Stage C schema contracts

**Files:**
- Modify: `scripts/assay_hygiene/_schema.py`
- Test: extend `tests/test_assay_hygiene_schema.py` (or the existing schema test file; find it, do not create a second)

**Adds ~6 tests.**

`FINDING_COLUMNS` currently describes a per-EDGE finding, left over from the
2026-08-12 design. Stage C emits one row per `(sample, claimed_assay)`, because
that is the unit of a write. Replacing it is a contract change: grep for every
reader before you touch it.

**This is the branch's signature defect, so read this twice.** Increment 1
shipped the same bug four times: a column keeps its name while its meaning
changes one frame away, and the fourth instance was caught only by a
whole-branch review. `FINDING_COLUMNS` changing from per-edge to per-sample is
exactly that shape. Either rename it, or verify every existing reference and say
in the commit message what you checked.

- [ ] **Step 1: Write the failing tests** covering: every new constant is
  distinct from every existing one; the disposition vocabulary is closed;
  `FINDING_COLUMNS` has no duplicate names; the fixture round-trips through the
  new columns.
- [ ] **Step 2: Add the vocabulary.**

Required constants, values are yours to choose but must not collide with the
existing `V_*` / `A_*` / `T_*` families:

```
MODE_1, MODE_2, MODE_3                  which mode claimed this row
DISP_ABSENCE_LINEAGE                    a neighbour already registers the claim
DISP_ABSENCE_COMPAT                     no neighbour, but the pair coexists
DISP_UNRESOLVED                         neither test settles it
DISP_CONTRADICTION                      no neighbour, and the pair never coexists
LIN_CHILD, LIN_PARENT, LIN_NONE         lineage test outcome
BAND_NEVER, BAND_SOMETIMES, BAND_ROUTINE, BAND_NO_SUPPORT
MIN_CO_REG_SUPPORT = 30                 reporting floor, NOT a tuned threshold
CO_OCCUR_BAND = 0.5                     reporting band, NOT a tuned threshold
```

Both numbers carry a comment saying they are reporting bands with no backtest
behind them, and that the spec's position is that thresholds are an OUTPUT of a
curve. Do not let a later reader mistake them for validated cutoffs.

- [ ] **Step 3: Redefine `FINDING_COLUMNS`**, one row per `(sample, claimed
  assay)`, carrying at minimum: `sample_id`, `uuid`, `sample_type`, `project_id`,
  `registered_internal_assay_ids`, `claimed_internal_assay_id`,
  `claimed_internal_assay_title`, `mode`, `disposition`, `claim_tier`,
  `source_field`, `raw_value`, `lineage`, `lineage_neighbour_uuid`,
  `co_reg_rate`, `co_reg_pop`, `compat_band`, `precedent_rate`,
  `precedent_n_both`, `precedent_n_child_only`, `decided_by`, `action`.
- [ ] **Step 4: Extend `make_fixture()`** so it can produce all four
  dispositions and both Mode 2 directions. The existing fixture cannot express a
  sample legitimately holding two assays, which is the domain rule this whole
  increment encodes, so it cannot currently express the case that matters.
- [ ] **Step 5: Run the full suite. Report the delta.**

---

### Task 2: The lineage test, and the extract integrity guards

**Files:**
- Create: `scripts/assay_hygiene/lineage.py`
- Test: `tests/test_assay_hygiene_lineage.py`

**Adds ~12 tests.**

**Interfaces:**

```python
def lineage_index(childof, samples) -> tuple[dict[int, list[int]], dict[int, list[int]], dict]
    """-> (children_of, parents_of, integrity) keyed by sample_id."""

def neighbour_registers(sample_id, claimed_assay, children_of, parents_of, registered) -> tuple[str, int | None]
    """-> (LIN_CHILD | LIN_PARENT | LIN_NONE, the neighbour's sample_id or None)."""
```

`registered` is `audit.registered_internal(membership, assays)`. Do not build a
third grouping of the membership frame; that function already crosses the
junction and raises on an unknown assay.

**Contracts that must be tested:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a child registers the claim, the parent does not, so the parent's finding is `LIN_CHILD`
  - the mirror: a parent registers it, the child does not, so the child's finding is `LIN_PARENT`
  - both register it, so no finding is produced at all (there is nothing absent)
  - neither registers it, so `LIN_NONE`
  - a sample with no neighbours at all returns `LIN_NONE` and does not raise
  - **duplicate uuid:** two `sample_id`s sharing a uuid resolve deterministically to the lowest, and the count is reported. A `set_index("uuid")` here raises `InvalidIndexError` on the real extract; a test that never sees a duplicate will not catch it.
  - **unresolvable `childof`:** a row naming a uuid with no sample is counted into `integrity`, not dropped silently and not crashed on
  - **the 362:** a neighbour `sample_id` present in `membership` but absent from `samples` is handled per your documented decision, and the test asserts that decision explicitly rather than asserting whatever the code happens to do
  - `LIN_CHILD` takes precedence over `LIN_PARENT` when both hold, and the test names why the tie is broken that way
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3:** `integrity` must carry, by name and count: `dup_uuid_rows`,
  `unresolved_childof`, `membership_without_sample`. The report prints them. A
  silently clean run on a dirty extract is the failure mode.
- [ ] **Step 4: Verify against the real extract.** `lineage_index` over
  `assay-hygiene/extract/` must report 28 duplicate-uuid rows across 14 uuids,
  755 unresolvable `childof` rows, and 362 membership-without-sample. If your
  numbers differ, STOP: either the extract changed or one of us is wrong, and
  both are worth knowing before you build on it.
- [ ] **Step 5: Run the full suite. Report the delta.**

---

### Task 3: The compatibility test

**Files:**
- Create: `scripts/assay_hygiene/compatibility.py`
- Test: `tests/test_assay_hygiene_compatibility.py`

**Adds ~10 tests.**

**Interface:**

```python
def co_registration(membership, assays, samples) -> dict[tuple[str, int, int], tuple[float, int]]
    """(sample_type, registered_assay, claimed_assay) -> (rate, support)."""

def compat_band(rate: float | None, support: int) -> str
    """-> BAND_NEVER | BAND_SOMETIMES | BAND_ROUTINE | BAND_NO_SUPPORT."""
```

Rate is: of all samples of `sample_type` registered in `registered_assay`, the
share that are ALSO registered in `claimed_assay`. Support is the size of the
denominator, **in samples of that type**, and it is not an edge count.

**Contracts that must be tested:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a pair that always coexists rates 1.0
  - a pair that never coexists rates 0.0
  - **support below the floor is `BAND_NO_SUPPORT` and is NEVER `BAND_NEVER`,** even at rate 0.0. This is the test that stops the pipeline calling four samples a contradiction.
  - the rate is directional: `rate(T, R, X)` and `rate(T, X, R)` differ when the populations differ, and the test asserts a case where they do
  - sample type comes from the uuid prefix and a sample whose uuid does not parse is counted, not dropped
  - a sample registered in three assays yields the BEST rate over its registered set, and the test pins which one won
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify against the real extract** on the pattern the spec names:
  `(D.IMG, 127, 145)` must read rate 0.000 over a support of 1,907, and
  `(PAV, 56, 74)` must read approximately 0.805 over 13,229. Re-derive rather
  than trusting these; if they disagree, report before proceeding.
- [ ] **Step 4: Run the full suite. Report the delta.**

---

### Task 4: Mode 1, samples registered in nothing

**Files:**
- Create the Mode 1 half of `scripts/assay_hygiene/classify.py`
- Test: `tests/test_assay_hygiene_classify.py`

**Adds ~10 tests.**

Mode 1's population is the 6,324 samples with no internal-assay registration at
all. Metadata decides, because the question metadata answers ("what is this
sample") is exactly the question being asked.

**Contracts:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a sample registered in NOTHING with a strong claim yields a Mode 1 finding with `action = A_ADD_TO_ASSAY`
  - a sample registered in SOMETHING is never Mode 1, whatever it claims. That is Mode 2 or 3.
  - a sample registered in nothing with NO claim yields no finding, and is counted in the report as unreachable rather than omitted
  - a sample with two conflicting claims produces the `T_CONFLICT` tier and is NOT silently resolved to one of them
  - tier is carried onto the finding, so a `weak` Mode 1 row is distinguishable downstream from a `strong` one
  - a sample whose only registration is an UNMAPPABLE id is NOT Mode 1: its internal identity is unknown, not known to be absent. `audit_contradictions` already reasons this way; match it and cite it.
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify against the real extract.** Expect approximately 1,883
  samples and 2,977 `(sample, assay)` rows at all tiers, and 719 samples / 723
  rows at strong plus corroborated. Re-derive; report disagreement.
- [ ] **Step 4: Run the full suite. Report the delta.**

---

### Task 5: Mode 2, both directions, precedent-decided

**Files:**
- Extend `scripts/assay_hygiene/classify.py`
- Test: extend `tests/test_assay_hygiene_classify.py`

**Adds ~14 tests.**

**This is the task the increment exists for.** Mode 2 fires when a lineage
neighbour registers an assay this sample lacks. Precedent on the hop decides
whether to propose it; metadata disambiguates WHICH assay when the hop carries
several; neither authorises a write, because there is no write here.

Both directions, and they are not symmetric:

| Direction | Trigger | Action | Precedent column |
|---|---|---|---|
| child has it, parent lacks it | `LIN_CHILD` | `A_ADD_PARENT` | `propagation_rate` |
| parent has it, child lacks it | `LIN_PARENT` | `A_ADD_CHILD` | `reverse_rate` |

`mine_precedent` already computes both rates and its docstring defines them:
`propagation_rate = n_both / (n_both + n_child_only)` asks "given the child is
in this assay, how often is the parent". **Using `propagation_rate` for the
`A_ADD_CHILD` direction is a wrong-column bug that produces plausible numbers
and no error.** Assert the pairing in a test.

**Contracts:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - `A_ADD_PARENT` is keyed on `propagation_rate`; `A_ADD_CHILD` on `reverse_rate`. Two separate tests, each failing if the columns are swapped. Build the fixture so the two rates DIFFER, otherwise the test passes under the bug.
  - a hop with no precedent row yields a finding marked as having no measured basis, and does NOT default to rate 0.0. Absent evidence and evidence of absence are different, and the spec is explicit that they are unmeasurable by construction.
  - a hop carrying several candidate assays uses the metadata claim to pick, and the finding records `decided_by` as the disambiguator
  - a sample already registered in the assay produces NO finding
  - the rule key is the full `(project_id, child_type, parent_type, internal_assay_id)` and a match on three of four does not count
  - a `(sample, assay)` pair reachable from two different neighbours is emitted ONCE, because it is one write, and the finding records that it had multiple supports
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify against the real extract.** The unfiltered ceiling should
  land near 50,508 `A_ADD_PARENT` rows over 39,773 samples and 111,039
  `A_ADD_CHILD` rows over 97,635 samples, union 161,420 over 110,170. These are
  pre-precedent candidates. Report them as a ceiling with that word attached.
- [ ] **Step 4: Run the full suite. Report the delta.**

---

### Task 6: Mode 2's backtest and the threshold curve

**Files:**
- Create: `scripts/assay_hygiene/backtest.py`
- Test: `tests/test_assay_hygiene_backtest.py`

**Adds ~9 tests.**

Hide the membership of one endpoint on a held-out slice of edges where BOTH are
registered, run Mode 2 cold, and measure how often it recovers the assay a
curator actually assigned.

**Split by SAMPLE, never by edge.** A sample fans out to many edges and an
edge-level split scores memorised answers. Increment 1's metadata measurement
made this mistake explicit and the spec records it; do not reintroduce it.

**Thresholds are an OUTPUT.** Emit the full precision-versus-rate curve. Do not
pick a cutoff, do not put a default in the code, and do not let the report imply
one has been validated.

**Contracts:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a sample appearing on both sides of the split fails the test, so the guard is real
  - hiding a membership and restoring it leaves the input frames byte-identical, so the backtest cannot leak into the live classification
  - recovery is measured against the CURATOR's assay, not against whether any assay was proposed
  - the curve reports support per band, and a band with no observations is reported as empty rather than as 0.0 precision
  - both directions are backtested separately and reported separately
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Run it over the real extract** and record the curve in the
  report. Expect the actionable middle band to be thin: the spec's post-stage-0
  table shows 175 rules at rate >= 0.95 carrying only 99 child-only edges in the
  entire database, while the mid band 0.60 to 0.80 is essentially two rules,
  `D.TITR -> TIS` at 0.622 and `D.FCRB -> TIS` at 0.796.
- [ ] **Step 4:** If the curve shows no band clearing the spec's 95% bar, SAY SO
  as the finding. A backtest that fails to find a safe threshold is a successful
  backtest and a blocked increment 3, and reporting it that way is the whole
  point of doing detection before writing.
- [ ] **Step 5: Run the full suite. Report the delta.**

---

### Task 7: Stage C unification, and Mode 3 by subtraction

**Files:**
- Extend `scripts/assay_hygiene/classify.py`
- Test: extend `tests/test_assay_hygiene_classify.py`

**Adds ~11 tests.**

One pass emits `findings.csv` for all three modes, and Mode 3 becomes what
survives after Modes 1 and 2 have declined a row.

**The ordering is the contract.** A row is Mode 3 only if it is not Mode 1 and
not Mode 2. Encode that as an explicit precedence, not as the order of `if`
branches that a later edit can reorder without failing a test.

**Contracts:**

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a row that qualifies for Mode 1 and Mode 3 is Mode 1, and the test states why
  - a row corroborated by lineage is Mode 2 and NEVER Mode 3, which is the amendment's central claim
  - a row in `BAND_ROUTINE` with no lineage is `DISP_ABSENCE_COMPAT` and is reported as a Mode 2 CANDIDATE carrying no measured precision, not as a Mode 2 finding
  - `DISP_UNRESOLVED` is its own output class and is not folded into any mode
  - the four dispositions partition the input: every row gets exactly one, none gets two, and the counts sum to the input size. Assert the sum.
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Reconcile with the spec's reproducer.** Run
  `scripts/measure_absence_vs_contradiction.py` and your classifier over the same
  866 flags. They must agree: 351 / 250 / 214 / 51. **If they disagree, one of
  them is wrong and you must find out which before continuing.** Do not adjust
  either until you know. The reproducer was written by hand during planning and
  has no tests; your classifier has tests and no independent check. That is the
  point of running both.
- [ ] **Step 4: Emit `assay-hygiene/mode3-disposition.csv`** carrying all 866
  original flags with their new disposition, so increment 1's output is
  superseded traceably rather than deleted.
- [ ] **Step 5: Run the full suite. Report the delta.**

---

### Task 8: The wired run and the operator report

**Files:**
- Create: `scripts/assay_hygiene/run_detect.py`
- No new test file; assert the report's invariants inside the existing suite.

**Adds ~7 tests.**

**Interface:** `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -m assay_hygiene.run_detect`

Follow `run_evidence.py`'s shape. It is the model for this and its docstring
explains why the report says what it says.

**The report is the deliverable, not the counts.** It must do six things a
count cannot:

1. **State that nothing was written**, in the first paragraph and again per
   mode. Say it at the scope of THIS run, not of the package: `stage0_apply.py`
   carries live Cypher and a package-wide "there is no write path here" is false
   and would rightly destroy a reader's trust in the rest.
2. **Lead with the correction.** Increment 1's report told the operator there
   were 866 contradictions. This one must say plainly that 94.1% of those were
   absence reported as contradiction, that the real Mode 3 residue is 51, and
   that the operator found the error.
3. **Print the four integrity counts** from Task 2 whether or not they are zero.
4. **Label the Mode 2 ceiling as a ceiling** every time the number appears.
5. **Report `UNRESOLVED` as its own population with its size.** Do not bury it.
6. **Key every pattern table on `(sample_type, claimed_assay, raw_value)`.** The
   PAV `Blood` and `Necropsy` populations behave oppositely under the same tests
   and were merged, and invisible, under the coarser key.

- [ ] **Step 1: Write the failing tests:** the report names every artifact it
  writes; the no-write claim appears and is scoped; a nonzero integrity count
  cannot be omitted; the disposition counts in the prose equal the counts in the
  csv. That last one is a real risk, since increment 1 shipped a report quoting
  a purity table it had not computed.
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Run end to end over the real extract.**
- [ ] **Step 4: Read the report as the operator would.** Does it lead with the
  correction? Is the ceiling unmistakably a ceiling? Would someone who reviewed
  the 866 last week understand what changed and why?
- [ ] **Step 5: Run the full suite. Report the delta.**

---

## Definition of done

- [ ] Full suite green, reported as a delta against the baseline you measured.
- [ ] `findings.csv`, `mode3-disposition.csv` and the report written under `assay-hygiene/`.
- [ ] The classifier and `measure_absence_vs_contradiction.py` agree on all four disposition counts over the 866.
- [ ] Mode 2's backtest curve exists, with support per band, and no threshold is chosen in code.
- [ ] Nothing imports `stage0_apply.py` or `driver_stage0.py`. Verify by grep.
- [ ] No `ASSAY_HYGIENE-update.xlsx`, no APPROVE column, no write path. Those are increment 3.
- [ ] The four extract-integrity counts are printed by the run.

## What this increment deliberately does not do

- **No stage D.** No LLM adjudication. The rule-level judge belongs with the curator workbook it feeds.
- **No stage E or F.** No workbook, no writer, no addition probe.
- **No threshold decision.** Task 6 produces the curve; choosing the cutoff is increment 3's opening move and is the operator's call.
- **No re-review of the 866.** The operator should not be asked to look at those flags again until Task 7 has re-scoped them.
- **No fix for the 17 missing junction rows** in `dmac.assays_internal_assays`. That is a MySQL fix outside every increment of this project, it would clear four separate workarounds at once, and it is tracked as an open question rather than done here.
