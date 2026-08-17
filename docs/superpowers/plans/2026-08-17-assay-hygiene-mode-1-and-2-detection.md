# Assay Hygiene Increment 2: the vocabulary gate, Mode 1 and Mode 2 detection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate every metadata claim on whether the term that produced it is
credible, then decide what the pipeline would PROPOSE for Modes 1 and 2, and
write it to `findings.csv`. Nothing writes to production. Nothing is decided;
everything is proposed for the operator to approve later.

**Architecture:** A vocabulary gate runs before any mode and rejects claims
whose term is incoherent, unsupported, or names an assay the sample's type has
never been registered in. Surviving claims meet three deterministic tests
(reachability, lineage, co-registration) whose ORDER is a contract. Mode 1
proposes an assay for samples registered in nothing. Mode 2 proposes adding a
sample to an assay a lineage neighbour already holds, in two directions of very
unequal strength. Mode 3 proposes nothing, because it has no working detector.

**Tech Stack:** Python 3.11+, pandas, pyarrow, pytest. PEP 723 inline dependency
blocks, matching every other script in `scripts/`.

**Spec:** `docs/superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md`,
**as amended 2026-08-17 (the SECOND amendment, "what the three modes actually
are")**. Read it before Task 1. An earlier amendment the same day is superseded
and planning from it reproduces a known defect.

**This is increment 2 of 3.** Increment 1 built the evidence layer and a Mode 3
whose output is known bad. Increment 3 is adjudication, the two approval
surfaces, and the write path.

## The binding constraint

**Nothing decides. Everything proposes.** No mode writes on its own authority,
in any mode, ever. Thresholds rank and triage so the operator reads the
strongest evidence first; they do not grant permission. If you find yourself
writing a code path where a number authorises a change, you have misread the
spec.

In this increment nothing writes at all, so the constraint shows up as
vocabulary: `decided_by` is a provenance field naming which evidence produced a
PROPOSAL, and no function is named `decide_*`.

## Global Constraints

- **P1 sentinel:** scripts must never create, modify, or delete anything inside the plugin checkout. All project paths resolve from the current working directory. `tests/conftest.py::plugin_sentinel` enforces this.
- **Output root** is `assay-hygiene/` under the current working directory.
- **PEP 723 header** on every script: `requires-python = ">=3.11"` plus explicit dependencies.
- **Test command:** `uv run --with pytest --with pandas --with pyarrow --with openpyxl --with requests pytest tests/<file> -v`

  **`--with requests` is required and increment 1's plan omitted it.** Without it collection dies on `tests/test_nextseek_api_detect.py` before a single test runs. Verified 2026-08-17.
- **Full suite must stay green, measured as a DELTA.** Measure the baseline yourself first. Reading on 2026-08-17: **901 passed, 13 skipped**. Treat it as an environment sanity check, not a target.
- **Stale bytecode silently invalidates mutation testing here.** `PYTHONPYCACHEPREFIX` points at a shared cache. If you break an implementation and its test still passes, suspect the cache before concluding the test is weak.
- **Read-only.** Nothing here touches MySQL, Neo4j, or the API. `stage0_apply.py` and `driver_stage0.py` carry live Cypher; nothing you build may import them. Verify by grep before you finish.
- **Rule key is `(project_id, child_type, parent_type, internal_assay_id)`.**
- **`internal_assay_id` is NULLABLE and is a RULE_KEY component.** `groupby(RULE_KEY)` defaults to `dropna=True` and silently discards the 17 junction-less assays.
- **Count ROWS, not edges.** A write is one `(sample, assay)` pair.
- **Every measured figure carries its scope in the sentence that states it.**
- **Re-derive every figure in this plan before asserting it in a test.** If a re-derived number disagrees by more than a point, STOP and report. This plan already shipped one set of wrong numbers; see below.
- **Commit style:** end messages with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

### Two definitions of "registered", and the one you must use

**This plan's first draft got this wrong and its verification targets certified
the bug.** There are two populations and they differ by 82 samples:

```
samples with ANY membership row              157,151   -> 6,242 unregistered
samples with a MAPPABLE membership row       157,069   -> 6,324 unregistered
registered ONLY via a junction-less assay         82
```

**Use the ANY-membership definition. Mode 1's population is 6,242.** A sample
registered only under one of the 17 junction-less assays IS registered; its
assay's internal identity is merely unknown. Calling it unregistered proposes a
first assay for a sample that already has one. `audit.py`'s docstring argues
exactly this for the audit and Task 5 below inherits it.

This is the branch's signature defect in its purest form: one word, two
meanings, one frame apart.

### A note on this plan's code blocks

Increment 1's retrospective: a defect in a planner-written code block in every
one of its 8 tasks, five planner-written tests that certified properties in
their own titles without testing them, one planner fix that created a data-loss
bug. This plan therefore specifies **interfaces, contracts, invariants and the
cases that must be tested**, and supplies no implementation bodies.

Adversarial review of this plan's first draft found six further defects in it,
including the population error above. Assume more remain. Measure, disagree, and
say so; every implementer on increment 1 who disagreed with their brief was
right.

## Measured starting state

Against `assay-hygiene/extract/` post-stage-0, and `claims.parquet` /
`vocabulary.csv` as increment 1 produced them.

```
samples                                  163,393
  registered (ANY membership row)        157,151
  registered in NOTHING                    6,242   <- Mode 1 population

MODE 1
  unregistered samples carrying a claim    1,827
  (sample, assay) rows                     2,912
  at strong+corroborated tier                671 samples / 671 rows

MODE 2 CEILING, unfiltered by precedent, over DERIVED_FROM
  ADD_PARENT      55,007 rows over  42,654 samples
  ADD_CHILD      117,463 rows over 102,582 samples
  union          172,338 rows over 115,626 samples  (132 pairs reach both ways)

VOCABULARY, the largest single defect source
  learned terms                                736  (0 curator-corrected, ever)
  unresolved tail                              266
  claims whose assay is unreachable for the type, of 866 flags     31
  ABSENCE_COMPAT flags from ONE mapping     212 of 250
```

**The Mode 2 numbers are a CEILING** and the word must accompany them
everywhere. Precedent cuts them down hard: at `rate >= 0.5`, ADD_CHILD survives
at **3,663 of 117,463, about 3%**.

**RECONCILED 2026-08-17 by Task 4, and the figures above are the corrected
ones.** Two independent computations disagreed: this plan read 54,780 / 116,365
and an independent review read 55,007 / 117,463 over the same relation. Both are
arithmetically correct and they differ by ONE thing -- the definition of
"registered". ANY membership row, crossed to the internal namespace by
`audit.registered_internal`, gives 55,007 / 117,463; dropping the 17
junction-less assays' registrations gives 54,780 / 116,365. **ANY membership row
means registered, so the larger pair is right and this plan understated the
ceiling by 227 and 1,098.**

The proof that the whole block was computed under the wrong definition, rather
than one figure being mistyped: this plan's own union line read 171,013 rows over
115,599 samples, which is exactly what the MAPPABLE-only reading produces, while
its own two components sum to 171,145. Self-loops, duplicate edge pairs and the
seek/internal id crossing were each measured and ruled out. `lineage.mode2_ceiling`
now computes it and `lineage.main` prints it, so it can be re-derived in one
command instead of quoted.

### Which lineage relation

**Use `DERIVED_FROM` (`edges.parquet`), not `CHILD_OF` (`childof.parquet`).**

```
CHILD_OF        742,534 pairs    ceiling  50,508 / 111,039  (MAPPABLE-only)
DERIVED_FROM    794,592 pairs    ceiling  55,007 / 117,463
divergence      52,185 DF-only, 126 CO-only
```

Precedent, the decider, is mined over `DERIVED_FROM`. A lineage test over
`CHILD_OF` asks about a different graph than its own evidence was measured on.
The first draft of this plan used `CHILD_OF` without saying so, which moved
every Mode 2 figure by roughly 9%.

### Four extract defects, each a silent drop in the natural pandas spelling

| Defect | Size | Where it bites |
|---|---|---|
| `sample_id` in `membership` but absent from `samples.parquet` | **362**, all registered | any `samples`-driven loop |
| duplicate `uuid` across `sample_id`s | 14 uuids, 28 rows | `set_index("uuid")` RAISES; `.map()` fans out |
| edge rows not resolvable to a sample on both ends | 755 over CHILD_OF | the lineage index |
| `membership` rows whose assay has no junction row | 279 over 17 assays | the internal-id crossing |

## File Structure

| File | Responsibility |
|---|---|
| `scripts/assay_hygiene/_schema.py` | MODIFY. Stage C contracts, mode/class vocabulary, gate outcomes, bands. |
| `scripts/assay_hygiene/gate.py` | CREATE. The vocabulary gate. Runs before every mode. |
| `scripts/assay_hygiene/lineage.py` | CREATE. Neighbour indexes over DERIVED_FROM, with integrity guards. |
| `scripts/assay_hygiene/compatibility.py` | CREATE. Co-registration rate and support. |
| `scripts/assay_hygiene/classify.py` | CREATE. Stage C. Modes 1 and 2, one pass. |
| `scripts/assay_hygiene/backtest.py` | CREATE. Mode 2's recovery curve, both directions. |
| `scripts/assay_hygiene/run_detect.py` | CREATE. The wired read-only run and the operator report. |
| `scripts/measure_absence_vs_contradiction.py` | EXISTS, and is TEST-LESS. Treat as a cross-check, never as an oracle. |
| `tests/test_assay_hygiene_gate.py` | CREATE. |
| `tests/test_assay_hygiene_lineage.py` | CREATE. |
| `tests/test_assay_hygiene_compatibility.py` | CREATE. |
| `tests/test_assay_hygiene_classify.py` | CREATE. |
| `tests/test_assay_hygiene_backtest.py` | CREATE. |

---

### Task 1: Stage C schema contracts

**Files:** modify `scripts/assay_hygiene/_schema.py`; extend the existing schema test file (find it; do not create a second).

**Adds ~7 tests.**

`FINDING_COLUMNS` currently describes a per-EDGE finding and **has no consumer
anywhere in the package**. Neither do `A_ADD_PARENT`, `A_ADD_CHILD`,
`A_ADD_TO_ASSAY`, `A_FLAG_ONLY`, `A_NONE`, or `RULE_COLUMNS`. They are dead
vocabulary, not anticipation. You are their first consumer, so you may reshape
them freely, but say in the commit message which you checked.

- [ ] **Step 1: Write the failing tests.** New constants distinct from existing
  `V_*` / `A_*` / `T_*` families; the class vocabulary is closed; no duplicate
  column names; the fixture round-trips.
- [ ] **Step 2: Add the vocabulary.**

```
MODE_1, MODE_2                      which mode proposes this row
MODE_3 exists but is never emitted  no detector; assert this in a test
GATE_PASS, GATE_UNREACHABLE, GATE_INCOHERENT, GATE_LOW_SUPPORT
CLS_ABSENCE_LINEAGE, CLS_ABSENCE_COMPAT, CLS_ALT_LABEL, CLS_UNRESOLVED
LIN_CHILD, LIN_PARENT, LIN_NONE
BAND_NEVER, BAND_SOMETIMES, BAND_ROUTINE, BAND_NO_SUPPORT
MIN_CO_REG_SUPPORT = 30             reporting floor, NOT a tuned threshold
CO_OCCUR_BAND = 0.5                 reporting band, NOT a tuned threshold
```

Both numbers carry a comment saying they are reporting bands with no backtest
behind them and that they gate nothing.

- [ ] **Step 3: Redefine `FINDING_COLUMNS`**, one row per `(sample, proposed
  assay)`: `sample_id`, `uuid`, `sample_type`, `project_id`,
  `registered_internal_assay_ids`, `proposed_internal_assay_id`,
  `proposed_internal_assay_title`, `mode`, `classification`, `gate`,
  `claim_tier`, `contested`, `source_field`, `raw_value`, `vocab_support`,
  `vocab_purity`, `vocab_provenance`, `lineage`, `lineage_neighbour_uuid`,
  `co_reg_rate`, `co_reg_pop`, `compat_band`, `precedent_rate`,
  `precedent_direction`, `precedent_n_both`, `precedent_n_child_only`,
  `precedent_n_parent_only`, `evidence_summary`, `action`.

  Name the assay column `proposed_*`, not `claimed_*` or `target_*`. Under the
  binding constraint the row is a proposal, and the column name should make a
  later reader unable to mistake it for a decision.
- [ ] **Step 4: Extend `make_fixture()`** to express: a sample legitimately in
  two assays; both Mode 2 directions; a gate rejection of each kind; a hop whose
  `propagation_rate` and `reverse_rate` DIFFER.
- [ ] **Step 5: Full suite. Report the delta.**

---

### Task 2: The vocabulary gate

**Files:** create `scripts/assay_hygiene/gate.py`, `tests/test_assay_hygiene_gate.py`

**Adds ~14 tests.**

**This task exists because of a measured failure.** Lineage-first precedence
launders vocabulary defects into membership write proposals. On today's data
that is at least 24 rows mislabelled `ABSENCE_LINEAGE` (11 A.FLOW registered in
31 Flow Cytometry **Analysis** claiming 30 Flow Cytometry via `Software:
FlowJo`; 13 A.SPC registered in 47 claiming 130 Mass Spectrometry via `Type:
High resolution mass spectra`), plus 212 of 250 `ABSENCE_COMPAT` rows arising
from one mapping.

**Interface:**

```python
def type_registration_index(membership, assays, samples) -> dict[tuple[str, int], int]
    """(sample_type, internal_assay_id) -> how many samples of that type are registered there."""

def gate_claims(claims, vocabulary, type_reg, min_support, min_purity) -> pd.DataFrame
    """One row per claim with a GATE_* outcome and the reason."""
```

Three rejection tests:

1. **Unreachable.** The claimed assay has ZERO registered samples of this
   sample type, anywhere. The claim is not credible. 31 of the 866 fail this.
2. **Incoherent term family.** Normalised terms sharing a stem map to different
   assays: `flowjo` -> 30, `flowjo v10.8.1` -> 31, `flowjo version 10` -> 31,
   `flowjo 10.3` -> 153. Report the family; do not auto-resolve it.
3. **Low support or purity.** Below thresholds you REPORT rather than choose.
   `illumina library` -> 24 sits at purity 0.707 over 2,210 samples and drives
   212 flags, so purity alone is discriminating here.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a claim whose type is never registered in the claimed assay is `GATE_UNREACHABLE` and reaches NO mode
  - a claim whose type IS registered there passes reachability even when this particular sample's registered assay never co-occurs with it
  - a term family mapping to two assays is `GATE_INCOHERENT`, and the test asserts the whole family is reported, not just the minority member
  - stem extraction does not collapse genuinely different products; include a negative case
  - a curator-provenance vocabulary row is NEVER gated out, whatever its support. A human decision outranks the data.
  - gate outcomes are computed per CLAIM, not per sample; a sample with one good and one bad claim keeps the good one
  - the gate never mutates `claims.parquet` or `vocabulary.csv`
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify against the real extract.** Report how many of the 138,007
  claims fail each test, and confirm the 24 FlowJo/mass-spectra rows and the 31
  unreachable rows are among the rejects. **If the FlowJo rows still pass the
  gate, the gate does not work**, whatever the aggregate numbers say.
- [ ] **Step 4: OPTIONAL, high value.** Extend stage A with a `sample_types`
  extract (id -> code, title) so `assays.sample_type_id` resolves. Today only
  the OBSERVED type-to-assay mapping is knowable, from precedent; the DECLARED
  one is not. If you do this, the gate can compare them, which is strictly
  better evidence than reachability alone. One SQL query. Do it in its own
  commit so it can be reverted independently.
- [ ] **Step 5: Emit `assay-hygiene/vocabulary-defects.csv`**, routed to
  `/curate-assay-vocabulary`, never to a mode.
- [ ] **Step 6: Full suite. Report the delta.**

---

### Task 3: The lineage test

**Files:** create `scripts/assay_hygiene/lineage.py`, `tests/test_assay_hygiene_lineage.py`

**Adds ~12 tests.**

**Interfaces:**

**SUPERSEDED. These are the BRIEFED signatures and not the ones that shipped;
`scripts/assay_hygiene/lineage.py` is the source of truth.** What shipped:**

```python
INTEGRITY_KEYS: tuple[str, ...]     # 11 keys

def lineage_index(edges, samples, membership) -> tuple[dict, dict, dict, dict]
    """-> (children_of, parents_of, uuid_of, integrity), keyed by sample_id."""

def lineage_supports(sample_id, assay_id, children_of, parents_of, registered) -> tuple[list[int], list[int]]
    """-> (children registering it, parents registering it), each sorted."""

def neighbour_registers(sample_id, assay_id, children_of, parents_of, uuid_of, registered) -> tuple[str, int | None, str | None]
    """-> (LIN_CHILD | LIN_PARENT | LIN_NONE, neighbour sample_id, neighbour uuid)."""
```

`assays` was dropped: the function never reads an assay id, and taking the frame
would advertise a validation it does not perform. `uuid_of` was added because
`FINDING_COLUMNS.lineage_neighbour_uuid` is otherwise recovered by a `samples`
join that is blank for the 243 unresolved endpoints, 182 of which are registered
and can therefore BE the named neighbour. The two lookup functions were given
DIFFERENT arities and return shapes on purpose, so a call swapped between them
raises `TypeError` rather than binding a `list` to a relation.

The briefed signatures, for the record:

```python
def lineage_index(edges, samples, membership, assays) -> tuple[dict, dict, dict]
def neighbour_registers(sample_id, assay_id, children_of, parents_of, registered) -> tuple[str, int | None]
```

`lineage_index` **takes `membership` and `assays`**, which the first draft's
signature omitted while requiring it to report `membership_without_sample`. It
cannot count what it cannot see.

`registered` comes from `audit.registered_internal`. Do not build a third
grouping of the membership frame.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - child registers it, parent does not -> parent's row is `LIN_CHILD`
  - parent registers it, child does not -> child's row is `LIN_PARENT`
  - both register it -> NO row at all, nothing is absent
  - neither -> `LIN_NONE`
  - a sample with no neighbours returns `LIN_NONE` and does not raise
  - **duplicate uuid:** two `sample_id`s on one uuid resolve to the lowest, deterministically, and the count is reported. `set_index("uuid")` RAISES on the real extract; a fixture without a duplicate will not catch it.
  - **unresolvable edge rows** are counted into `integrity`, not dropped and not crashed on
  - **the 362:** a neighbour in `membership` but absent from `samples` is handled per your documented decision, and the test asserts THAT decision rather than whatever the code does
  - `LIN_CHILD` wins ties over `LIN_PARENT`, and the test names why
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3:** `integrity` carries `dup_uuid_rows`, `unresolved_edges`,
  `membership_without_sample` by name. The report prints them even at zero.
- [ ] **Step 4: Verify against the real extract:** 28 duplicate-uuid rows over
  14 uuids, 362 membership-without-sample. If your numbers differ, STOP.
- [ ] **Step 5: Full suite. Report the delta.**

---

### Task 4: The co-registration test

**Files:** create `scripts/assay_hygiene/compatibility.py`, `tests/test_assay_hygiene_compatibility.py`

**Adds ~10 tests.**

**SUPERSEDED. What shipped, in `scripts/assay_hygiene/compatibility.py`:**

```python
BAND_ESTABLISHES: dict[str, str]    # band -> class, reported, never enforced

def co_registration(membership, assays, nodes) -> dict[tuple[str, int, int], tuple[float, int]]
    """(sample_type, registered assay, proposed assay) -> (rate, support in SAMPLES of that type)."""

def compat_band(rate, support) -> str
def band_establishes(band) -> str
def best_co_registration(sample_type, registered_assay_ids, proposed_assay_id, table) -> tuple[float, int, int | None]
    """-> (rate, support, the registered assay that produced them)."""
```

The third argument is `nodes` and not `samples`, the same departure
`gate.type_registration_index` made: `SAMPLE_COLUMNS` carries no type column and
the uuid prefix is wrong on 5 of the 177,392 nodes. `best_co_registration`
collapses a sample's several registered assays to one rate and NAMES the winner,
because `FINDING_COLUMNS` carries one rate per row and two consumers each
inventing a collapse is how this branch produced three wrong figures.

**What this test does and does not establish.** A high rate means the two assays
coexist on this type, so absence is the anomaly. A zero rate on a well-supported
population means they do not coexist, which after the gate means **alternative
labels**, not contradiction: D.IMG images sit in 127 Tissue Imaging or 145
Histopathology, never both, and 145 D.IMG samples are registered in
Histopathology. The first draft of this plan called that a contradiction.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - always coexists -> 1.0; never -> 0.0
  - **support below the floor is `BAND_NO_SUPPORT`, never `BAND_NEVER`,** even at rate 0.0
  - the rate is directional; assert a case where `(T,R,X)` and `(T,X,R)` differ
  - a sample registered in three assays yields the BEST rate, and the test pins which won
  - a uuid that does not parse into a type is counted, not dropped
  - **a zero rate on a reachable pair classifies `CLS_ALT_LABEL`, never an error.** This is the regression test for the second design error.
- [ ] **Step 2: Implement to green.**
- [x] **Step 3: Verify.** MEASURED 2026-08-17: `(D.IMG, 127, 145)` = 0.000 over
  **2,035**; `(PAV, 56, 74)` = 0.805 over **13,220**. The rates hold; the
  populations quoted here (1,907 / 13,229) type samples by the uuid prefix in
  `samples.parquet`, and this package types them off `nodes.type`. The gap
  decomposes exactly: 132 samples registered in 127 and typed D.IMG by the graph
  have no `samples.parquet` row at all, and 4 (D.IMG) / 9 (PAV) have a mysql row
  but no node row, so they carry no type here and are reported by
  `gate.untyped_registration_samples`.
- [x] **Step 4: RECONCILE THE MODE 2 CEILING.** DONE. The two readings are one
  number under two definitions of "registered": ANY membership row gives
  **55,007 / 117,463** and dropping the 17 junction-less assays gives 54,780 /
  116,365. ANY membership row means registered, so the former is right. See
  `lineage.mode2_ceiling` and the corrected block under "Measured starting
  state".
- [ ] **Step 5: Full suite. Report the delta.**

---

### Task 5: Mode 1

**Files:** extend `scripts/assay_hygiene/classify.py`, `tests/test_assay_hygiene_classify.py`

**Adds ~10 tests.**

Population is the **6,242** samples with NO membership row. Metadata proposes,
after the gate.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - registered in nothing, gate-passing strong claim -> Mode 1 row, `action = A_ADD_TO_ASSAY`
  - **registered ONLY via a junction-less assay -> NOT Mode 1.** The 82-sample case. Its assay's identity is unknown, not absent.
  - registered in something -> never Mode 1
  - registered in nothing with no claim -> no row, counted in the report as unreachable rather than omitted
  - a gate-rejected claim produces no Mode 1 row even when the sample is registered in nothing
  - two claims disagreeing: the `contested` COLUMN carries it and BOTH rows are emitted. **Do not require or emit `T_CONFLICT`** — it is retired (`_schema.py:137-141`) and `tests/test_assay_hygiene_claims.py:76` pins its absence. The first draft of this plan mandated it and would have forced an implementer to break that test.
  - tier is carried onto the row, so a weak proposal is distinguishable from a strong one
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify:** approximately 1,827 samples / 2,912 rows at all tiers,
  671 / 671 at strong plus corroborated, BEFORE the gate. Report the after-gate
  numbers too; nobody has measured those.
- [ ] **Step 4: Full suite. Report the delta.**

---

### Task 6: Mode 2, two directions of unequal strength

**Files:** extend `classify.py` and its test.

**Adds ~15 tests.**

| Direction | Trigger | Action | Precedent column |
|---|---|---|---|
| child has it, parent lacks it | `LIN_CHILD` | `A_ADD_PARENT` | `propagation_rate` |
| parent has it, child lacks it | `LIN_PARENT` | `A_ADD_CHILD` | `reverse_rate` |

**`A_ADD_CHILD` is the weak direction and the plan must not treat the two as
peers.** Measured:

| | ADD_PARENT | ADD_CHILD |
|---|---|---|
| corroborated by co-registration over the 866 | **88/88, 100%** | 15/263, 5.7% |
| rules at rate >= 0.95 | 5 | 15 |
| candidate rows surviving rate >= 0.5 | 79,488 | **3,663** of 117,463 |
| rows creating a (type, assay) pair existing nowhere | 55.6% | **67.6%** |

The single cleanest datum: `TIS <- PAV` under 56 Patient Visit runs a reverse
rate of **0.006**, while the same hop under 74 Tissue Collection runs a
propagation rate of **0.931**. On the hop that justified Mode 2, the parent's
assay does not flow down while the child's flows up.

An earlier draft argued for symmetry from volume ("263 against 88"). That is
backwards: the 263 are the weakly corroborated direction.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - `A_ADD_PARENT` keys on `propagation_rate`; `A_ADD_CHILD` on `reverse_rate`. **Build the fixture so the two rates DIFFER**, or the test passes under the swap it exists to catch.
  - a hop with no precedent row yields a row marked as having no measured basis, and does NOT default to 0.0. Absent evidence and evidence of absence differ.
  - a hop carrying several candidate assays uses the gated metadata claim to disambiguate, and `decided_by` records that
  - a sample already registered in the assay yields no row
  - the rule key is all four components; three of four does not match
  - a `(sample, assay)` pair reachable from two neighbours is emitted ONCE, because it is one write, and records that it had multiple supports
  - **an ADD_CHILD row creating a (type, assay) pair existing nowhere in the database is flagged as such on the row.** 67.6% of them do.
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Verify the ceiling** as reconciled in Task 4, and report ADD_PARENT
  and ADD_CHILD separately at every threshold. Never print a combined figure.
- [ ] **Step 4: Full suite. Report the delta.**

---

### Task 7: Mode 2's backtest

**Files:** create `scripts/assay_hygiene/backtest.py` and its test.

**Adds ~10 tests.**

Hide one endpoint's membership on a held-out slice where both are registered,
run cold, measure recovery of the curator's assay.

**Split by SAMPLE, never by edge.** A sample fans out to many edges; an
edge-level split scores memorised answers.

**Thresholds are an OUTPUT.** Emit the full curve. Under the binding constraint
they set the operator's reading order, not permission, so there is no cutoff to
choose in code at all.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - a sample on both sides of the split fails the test, so the guard is real
  - hiding and restoring leaves the input frames byte-identical
  - recovery is measured against the CURATOR's assay, not against whether any proposal was made
  - the curve reports support per band; an empty band reports empty, not 0.0 precision
  - **the two directions are backtested and reported separately**, never pooled
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Run over the real extract and record both curves.**
- [ ] **Step 4:** If no band clears the spec's 95% bar, SAY SO as the finding. A
  backtest that finds no safe threshold is a successful backtest.

---

### Task 8: Stage C unification

**Files:** extend `classify.py` and its test.

**Adds ~12 tests.**

One pass emits `findings.csv`. **The precedence is the contract:**

```
1. GATE      a rejected claim reaches no mode, ever
2. MODE 1    registered in nothing (ANY-membership definition)
3. LINEAGE   a neighbour carries it -> Mode 2
4. COMPAT    routinely coexists -> Mode 2 candidate, unproven
             never coexists     -> CLS_ALT_LABEL, no action
             otherwise          -> CLS_UNRESOLVED
5. MODE 3    emits nothing; no detector exists
```

Encode it as explicit precedence, not as `if` branch order a later edit can
reorder without failing a test.

- [ ] **Step 1: Write the failing tests.** Required cases:
  - **a gate-rejected claim is never Mode 2 even when a neighbour carries it.** This is the regression test for the third design error; the 24 FlowJo/mass-spectra rows are the fixture.
  - a row corroborated by lineage is Mode 2 and never an error
  - a zero-co-registration row on a reachable pair is `CLS_ALT_LABEL` and proposes nothing
  - `CLS_UNRESOLVED` is its own class, folded into no mode
  - **Mode 3 emits zero rows**, and the test says why: no detector exists
  - the classes partition the input; assert the counts sum, and define "the input" explicitly in the test name
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Cross-check against `measure_absence_vs_contradiction.py`,
  and do NOT pin its numbers.** That script has no tests and encodes the OLD
  precedence (lineage before any vocabulary check), so its 351/250/214/51 split
  is known to launder the 24. Your classifier SHOULD disagree with it. Report
  the differences and explain each one. The first draft of this plan required
  agreement with those four numbers, which would have pinned the bug in as
  correct.
- [ ] **Step 4: Emit `mode3-disposition.csv`** carrying all 866 original flags
  with their new classification, so increment 1's output is superseded
  traceably rather than deleted.
- [ ] **Step 5: Full suite. Report the delta.**

---

### Task 9: The wired run and the operator report

**Files:** create `scripts/assay_hygiene/run_detect.py`. Assert report invariants in the existing suite.

**Adds ~8 tests.**

Follow `run_evidence.py`'s shape.

The report must:

1. **State that nothing was written**, first paragraph and per mode, scoped to
   THIS run and not to the package. `stage0_apply.py` carries live Cypher and a
   package-wide claim would be false.
2. **State that nothing is decided.** Every row is a proposal awaiting operator
   approval, in all three modes.
3. **Lead with the correction.** Increment 1 told the operator there were 866
   contradictions. Say plainly that measurement found none: 576 absences, 31
   vocabulary defects, 45 alternative labels, 214 unclassified. Say the operator
   found both errors.
4. **Report Mode 3 as having no detector**, and never as "small". Undetected and
   small are different findings.
5. **Label the Mode 2 ceiling a ceiling** at every appearance, and split
   ADD_PARENT from ADD_CHILD with the survival rate at threshold.
6. **Print the integrity counts** whether or not they are zero.
7. **Key every pattern table on `(sample_type, proposed_assay, raw_value)`.** The
   PAV `Blood` and `Necropsy` populations behave oppositely and were invisible
   under the coarser key.
8. **Report the vocabulary as the largest defect source**, with the
   `illumina library` mapping named.

- [ ] **Step 1: Write the failing tests:** the report names every artifact it
  writes; the no-write and no-decision claims appear and are scoped; a nonzero
  integrity count cannot be omitted; **the counts in the prose equal the counts
  in the csv** (increment 1 shipped a report quoting a table it had not
  computed).
- [ ] **Step 2: Implement to green.**
- [ ] **Step 3: Run end to end.**
- [ ] **Step 4: Read it as the operator would.** Does it lead with the
  correction? Is the ceiling unmistakably a ceiling? Would someone who reviewed
  the 866 understand what changed and why?
- [ ] **Step 5: Full suite. Report the delta.**

---

## Definition of done

- [ ] Full suite green, reported as a delta against your measured baseline.
- [ ] `findings.csv`, `vocabulary-defects.csv`, `mode3-disposition.csv`, and the report written under `assay-hygiene/`.
- [ ] The 24 FlowJo and mass-spectra rows are gate rejects, not Mode 2 proposals.
- [ ] Mode 3 emits zero rows and the report says why.
- [ ] Both backtest curves exist with per-band support, and no threshold is chosen in code.
- [ ] The Mode 2 ceiling discrepancy is root-caused and reported.
- [ ] Nothing imports `stage0_apply.py` or `driver_stage0.py`. Verify by grep.
- [ ] No workbook, no APPROVE column, no write path.
- [ ] No function named `decide_*`; nothing in the codebase authorises a change.

## What this increment deliberately does not do

- **No stage D, E or F.** No adjudication, no workbook, no writer, no addition probe.
- **No threshold decision.** Task 7 produces the curves; under universal approval there is no cutoff to choose.
- **No Mode 3 detector.** Building one is its own increment. Candidates, none built: registration-side reachability (a sample in an assay its type otherwise never holds); cross-project registration (1,340 membership rows register a sample in an assay whose projects are disjoint from the sample's own, plus 271 samples with no project); a removal lane.
- **No re-review of the 866.** Not until Task 8 has reclassified them.
- **No fix for the 17 junction-less assays** in `dmac.assays_internal_assays`. A MySQL fix outside every increment here; it would clear four workarounds at once.
- **No curator-identity evidence.** The extract records who registered nothing; it cannot.
