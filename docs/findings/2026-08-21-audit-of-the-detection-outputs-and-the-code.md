# Audit: the detection outputs, and the code that produced them

**2026-08-21. Read-only.** Nothing in this audit changed the pipeline, the
artifacts or the database. Every figure below was re-derived from
`assay-hygiene-bak/`, which is a local working copy and is **not** in git — so
none of the paths this document cites under `assay-hygiene-bak/` will resolve in
a clone. The scripts that produced the figures were session scratch and were not
preserved; each section states the derivation instead, and the figures in §1 and
§2.1 have since been independently reproduced twice — once by a blind review, and
once by `scripts/assay_hygiene/baseline.py`, which IS in git and re-derives nine
of them on demand. Where a published figure and my measurement disagree, both are
printed.

Population: `assay-hygiene-bak/artifacts/findings.csv`, **170,786 rows, 36
columns** (the brief says 37; it is 36).

---

## 1. The row budget

Buckets are mutually exclusive and applied in the order listed. "Reachable"
means `type_registrations > 0` — at least one sample of this type is registered
in this assay somewhere. "Writable" means at least one SEEK `assays.id` carries
the proposed internal id inside the sample's own project.

| # | bucket | rows | samples | % |
|---|---|---|---|---|
| 1 | proposes nothing by design (`action = NONE`) | 1,959 | 1,959 | 1.1% |
| 2 | **MODE_1 — gated, reachable** | **1,373** | 1,367 | 0.8% |
| 3 | MODE_2 — **UNREACHABLE**, by the gate's own rule | **99,449** | 74,157 | 58.2% |
| 4 | MODE_2 — reachable, no SEEK record in the sample's project | 100 | 100 | 0.1% |
| 6 | MODE_2 — reachable, **ambiguous** SEEK target (≥2 records) | 2,367 | 2,367 | 1.4% |
| 7 | **MODE_2 — reachable, single writable target** | **65,538** | 53,662 | 38.4% |
|   | **total** | **170,786** | | |

**Answer to "how many could a curator plausibly approve": 66,911 (39.2%)** —
buckets 2 and 7. That is the population that survives the pipeline's *own*
stated rules, before anyone reads any biology. It is not a claim that 66,911 are
correct; it is the ceiling on what is worth a curator's attention.

**99,449 rows (58.2%) are removed by one rule the package already defines and
never applies to this lane.** That is the "150k rows that don't actually exist",
measured. It is 58%, not 88% — the remaining gap between 66,911 and 170,786 is
mostly bucket 1 (deliberate no-action reports) and the ambiguity buckets.

Bucket 6 is not junk; it is unresolvable *as emitted*. Those rows name a real
absence and cannot be written because nothing says which SEEK record gets the
row.

### Where the junk concentrates

The 99,449 unreachable rows span **479 distinct (sample_type, assay) pairs**
(the finding doc says 476). The top 15 carry 49,917 of them — **50.2%**:

| sample type → assay | rows |
|---|---|
| TIS → 14 Chemical challenge | 10,745 |
| D.FLOW → 74 Tissue Collection | 7,197 |
| D.IMG → 74 Tissue Collection | 6,276 |
| BAC → 74 Tissue Collection | 3,297 |
| DNA → 88 Bacterial Extraction | 3,024 |
| BAC → 64 Short Read Sequencing | 2,592 |
| TIS → 133 Pathogen Challenge and Antibody Depletion | 2,212 |
| DNA → 74 Tissue Collection | 2,145 |
| D.SEQ → 24 DNA Extraction | 2,126 |
| D.FLOW → 87 Cell Isolation | 1,991 |

Ten pairs, 41,605 rows. A single reachability test removes them all.

### A second budget, from the verdicts rather than the rules

An independent blind review (no access to this document, the finding docs or the
handoff) cut the same population by what a human or agent actually *ruled*,
rather than by what the pipeline's rules permit. It reports:

| | rows |
|---|---|
| plausible — operator-approved ≥0.5 precedent (12,188) + agent-approved and audit-upheld (11,480) | **23,668** |
| indeterminate — audit-WEAK (3,257) + UNSURE (3,090) | 6,347 |
| junk — agent REJECT (132,546) + WRONG_ASSAY (4,016) + overturned (735) + operator reject (142) | **137,439** (82.1% of Mode 2) |

**The two budgets answer different questions and both are right.** Mine
(66,911 / 39.2%) is the ceiling on what survives the pipeline's own stated
rules — what is worth putting in front of a human. The verdict-based one
(23,668 / 14% of Mode 2) is what survived a human or agent actually reading it.
The gap between them, roughly 43,000 rows, is reachable and writable but was
still judged wrong on the biology. That gap is the honest measure of how much
work a reachability gate does *not* do: it is necessary and it is nowhere near
sufficient.

---

## 2. The four known defects

### 1. The lineage lane never reaches the reachability gate — **CONFIRMED, exactly**

Re-measured independently:

| mode | rows | `type_registrations == 0` | carries a gate outcome |
|---|---|---|---|
| MODE_1 | 1,373 | **0** (0.0%) | 1,373 of 1,373 |
| MODE_2 | 167,454 | **99,449** (59.4%) | **868** of 167,454 |
| (no mode) | 1,959 | 0 | 1,959 of 1,959 |

All three published figures reproduce to the row: 99,449 / 167,454 / 59.4%, and
166,586 Mode 2 rows carry no gate outcome. `mode2.py:597` computes
`registrations` and spends it only on the `evidence_summary` string; no branch
tests it. I agree with the diagnosis without reservation.

**One correction to the finding doc.** Its second headline example is wrong:

> `D.IMG -> Organ-on-a-Chip Device Fabrication 7,580 rows | 0 D.IMG ever`

`D.IMG → 84` has `type_registrations == 3`, not 0. Three D.IMG samples *are*
registered there, so all 7,580 of those rows are reachable and would **survive**
the fix the doc proposes. The row count is right; the "0 ever" is not. The other
five headline pairs check out exactly.

The error's provenance is visible: the doc's list is the top of
`detect-report.md`'s "Patterns a lineage neighbour raised" table — which ranks
*all* lineage patterns, not unreachable ones — annotated with "0 ever" without
re-deriving each. This is the bug class the brief names, committed inside the
document that names it.

### 2. `precedent` is partly self-referential — **CONFIRMED as displayed evidence, REFUTED as a rate distortion**

The self-reference is real and it is total, not partial. Measured over the whole
extract:

```
n_child_only observations (EDGES) summed over all hops : 666,515
distinct (parent, assay) ADD_PARENT candidates raised  :  55,007
inflation factor                                       :    12.1x
```

55,007 is exactly the ADD_PARENT ceiling `detect-report.md` publishes, which
corroborates the derivation. **Every edge in the `propagation_rate` denominator
names a parent that is an ADD_PARENT candidate for that assay — that is the
definition of the counter.** So "the house declined this N times" is never a
valid reading of `n_child_only` at any grain, and the number shown to reviewers
is inflated 12.1× on average by child fan-out (worst observed triple: 303,866
edges over 616 proposed samples, ~493×). ANN-6 is right, and its "27 of 126" is
a floor on the problem rather than its size.

**But the extension I proposed to the operator earlier today does not hold, and
I am withdrawing it.** I suggested the self-reference distorts the rate and
explains why 157k rows sat below the 0.50 floor. Measured over the 229 hops with
≥50 forward observations, comparing the shipped edge-grained rate against a
sample-grained rate:

```
rate_edge   >= 0.50 : 100 hops
rate_sample >= 0.50 : 102 hops
median |delta|      : 0.000      max |delta|: 0.622
hops that cross the floor when regrained: 6 of 229
```

The fan-out inflates numerator and denominator together, so the *rate* is
materially unchanged and the floor lands in almost the same place. The defect is
in the **count reviewers were shown**, not in the rate that ranked them. Six
hops flip, led by `(D.IMG, TIS, 69)` at 0.007 → 0.529 and `(CEL, CEL, 24)` at
0.209 → 0.714 — worth re-reading, but not an explanation of the 157k.

### 3. Internal → SEEK resolution is unimplemented — **CONFIRMED**

**85 of 137** internal ids carry more than one SEEK record; the most-split id
carries **23**. No column in any artifact names a SEEK target.

Under the design's own rule ("target the record the registered neighbour is
already in"), over the 167,347 neighbour-anchored rows:

| outcome | rows |
|---|---|
| exactly one SEEK record | 165,453 |
| **two or more — ambiguous** | **573** |
| zero (see caveat) | 1,321 |

The 573 matches `detect-report.md` exactly.

**Correction, 2026-08-21, after an independent review.** I originally wrote that
the 1,321 zeros were "almost certainly a uuid→sample_id resolution artifact".
That was a guess and it was wrong. Measured: all 1,321 carry a
`proposed_internal_assay_id` in `{466, 467, 468, 470, 471, 472, 481, 482}` —
**raw SEEK `assays.id` values**, not internal ids. They are the fallback ids
`precedent.assay_index` mints for the 17 junction-less SEEK records that have no
internal id. My lookup was built from non-null `internal_assay_id` and therefore
found nothing for them.

So those rows are not unwritable — they are the *most* trivially writable rows
in the file, because the id they carry already IS the SEEK target. Corrected
Rule A: **166,774 of 167,347 resolve to exactly one SEEK record, 573 are
ambiguous, none are unresolvable.** That is much closer to `detect-report.md`'s
166,757 (which still does not reconcile exactly; its denominator is 167,330
against the 167,347 rows actually carrying a neighbour uuid, a 17-row gap
neither figure re-derives).

This is a documented design decision, not a bug in itself — but the column is
named `proposed_internal_assay_id` and nothing marks which 1,321 of its values
speak the other namespace. Any consumer joining that column against internal ids
silently drops them; any consumer joining it against SEEK ids silently
mismatches the other 169,465. See defect F.

Under the weaker project-filter rule, over all 170,786 rows: 161,218 resolve to
one, **6,306 are ambiguous**, 2,281 have no record in the sample's project, and
981 have no project recorded. The 6,306 is consistent with ANN-12's cohort-level
sample of 1,455 rows.

### 4. Internal assay 143 is named for the wrong GPT — **CONFIRMED**

265 samples, node types `D.GPT` 145 / `TIS` 80 / `DNA` 40 — matches the finding
doc exactly. Zero occurrences of "aminotransferase" or "transaminase" anywhere
in `samples.parquet`. There is no ALT assay in this database.

**Additional fact the doc does not carry:** internal 143 spans **three** SEEK
records — `26 GPT Assay` (MIT_SRP), and `416` / `420`, both titled
"GPT Assay – Data Attached" and **both in project 13, TestProject_250820**. Two
records for one internal id in one project is defect 3 in miniature, and one of
them is a test project. A rename fixes the label; it does not fix the split.

---

## 3. Defects past the four

Ordered by severity. Confidence is stated.

**A. `PRE_GATE` discards independent lineage evidence.** *High confidence,
consequence unmeasured.* `classify.py:_PRECEDENCE_TESTS` puts `PRE_GATE` first
and `NON_EMITTING_STEPS = (PRE_GATE,)`, so a key whose claim the gate rejected
emits **no row at all** — even when a lineage neighbour independently registers
that assay. For `GATE_UNREACHABLE` that is coherent (both tests fail for the
same reason). For **`GATE_INCOHERENT`** it is not: an incoherent term family is a
defect in the *vocabulary*, which says nothing about whether the neighbour holds
the assay. The lane throws away good evidence because unrelated bad evidence
exists. `detect-report.md` puts 4,255 lineage rows behind the gate but does not
split them by outcome, so I cannot size this without a re-run.

**B. Mode 2 rows carry `gate = NULL`, which reads as "passed".** *Certain.*
166,586 rows carry no gate outcome. A null here is indistinguishable, to any
consumer of `findings.csv`, from a gate that ran and found nothing wrong. This
is the same absence-rendered-as-verdict class, in the product's headline column.

**C. `mode2._proposal_source` raises `ValueError` on a data condition.**
*Certain; currently latent.* The `(gated claim, no precedent rule)` combination
has no `PROPOSAL_SOURCES` member and the function raises rather than inventing
one. Its docstring records that the combination occurs 0 times on the 2026-08-17
extract. That is a property of the data, not of the code: this raise aborts the
whole run, and both the four vocabulary retirements and the proposed
reachability change move exactly the populations that determine it. The
docstring already names the fix (add a fifth member); it should be added
*before* the rework, not after the crash.

**D. `dossier.py` has no test file.** *Certain.* 387 lines, zero direct tests —
verified by grep across `tests/`. It built the review surface that the operator
and 15 agents judged 1,012 cohorts on, and it is where the self-referential
precedent count is rendered (`dossier.py:351`) with the reading "A low rate over
MANY pairs is the house repeatedly declining it" — the exact misreading defect 2
is about. The one module with no tests is the one whose defect reached the
operator's decisions.

**F. `proposed_by = BY_PRECEDENT` on 115,087 rows whose precedent argues
against them.** *Certain. Found by the independent review; verified here.*
`_proposal_source` returns `BY_PRECEDENT` whenever a precedent rule exists,
without regard to what the rule says. Measured: of 166,578 `BY_PRECEDENT` rows,
**115,087 (69.1%) carry `precedent_n_both == 0` and `precedent_rate == 0.000`** —
a rule stating the house has never once co-registered that hop. The provenance
column names precedent as the proposer on two-thirds of the file, in exactly the
rows where precedent's content is "never observed". A reader who filters on
`proposed_by` to find well-supported rows gets the opposite set. Note this is a
*different* population from reachability: `n_both == 0` is 115,104 rows,
`type_registrations == 0` is 99,449, and they are not nested.

**G. Two namespaces in one column, unmarked.** *Certain.* See the correction in
§2.3: 1,321 rows carry a SEEK id in `proposed_internal_assay_id`. The fallback is
deliberate and documented in `precedent.assay_index`; what is missing is any
column or flag distinguishing the two, in a package whose own docstrings name
SEEK/internal confusion as its signature failure.

**E. Figures that do not reproduce.** *Certain, all minor individually.*
479 distinct unreachable pairs vs 476 published; 36 columns vs 37; the
167,330/167,347 mismatch in §2.3; and the `D.IMG → 84` error in §2.1. None
changes a decision on its own. Together they are the reason the brief demands
re-derivation, and they are all in documents written to be trusted.

---

## 4. Recommended rework order

| step | what | rows moved | why here |
|---|---|---|---|
| 0 | add the fifth `PROPOSAL_SOURCES` member (defect C) | 0 | one-line; every later step can otherwise abort the run |
| 1 | **reachability on the lineage lane**, emitted as `GATE_UNREACHABLE` so it BLOCKS visibly, **plus a bootstrap lane** for first-of-a-kind registrations | **−99,449** (58.2%) | largest single cut, uses a rule already written. The independent review puts ~2,035 legitimate first-of-a-kind rows inside that cut — the bootstrap lane is not optional |
| 2 | route reachability-blocked lineage keys to `PRE_COMPAT` instead of dropping them | up to 99,449 reclassified | the co-registration test is exactly "is this pair plausible for this type"; `BAND_NEVER → CLS_ALT_LABEL` is a more useful answer than silence, and it is already built |
| 3 | split `PRE_GATE` by outcome so `GATE_INCOHERENT` does not kill lineage evidence (defect A) | unmeasured, ≤4,255 | cheap, and it recovers rows rather than removing them |
| 4 | report precedent's denominator at sample grain, or beside the edge count | 0 rows, changes what reviewers see | fixes the misleading count without touching the ranking, which measurement says is fine |
| 5 | implement internal→SEEK resolution and emit the target as a column | makes 66,911 writable, isolates 2,367 | nothing can be written until this exists |
| 6 | decide what Mode 3 is | — | genuinely undecided; see below |

Steps 1 and 2 together are the answer to "150k rows that don't actually exist":
they take the reviewable population from 170,786 to **66,911**, and they move the
99,449 into a lane that says *why* rather than deleting them.

**On Mode 3.** `audit.audit_contradictions` produces 585 flags that all
re-dispose elsewhere, and `mode3_findings()` takes no arguments. My view: the
audit machinery is worth **keeping and renaming**, not deleting — it is a
working absence detector wearing a contradiction's name, and its output is
already consumed by `mode3-disposition.csv` as a traceable supersession record.
Deleting it destroys that trail. But it should stop being called Mode 3. The
detector the operator actually wants — registration-side reachability, the
mirror of the claim-side gate, needing no metadata at all — is measurable today
and is not built.

---

## 5. What I could not determine

- **The size of defect A.** Splitting the 4,255 gate-refused lineage rows by
  `GATE_UNREACHABLE` vs `GATE_INCOHERENT` needs a re-run of stage C; the gate
  outcome is not on the emitted rows.
- **Whether the 1,321 "zero SEEK record" rows in §2.3 are real.** They are
  probably uuid-resolution noise. Separating them needs the traversal's own
  `uuid_of`, not a `nodes.parquet` join.
- **Whether the cohort key is the right review unit.** The brief asks; I did not
  get to it. 1,123 cohorts over 167,454 rows, largest 29,763, is on its face a
  unit that hides variation inside the big cohorts, but I have not measured
  within-cohort heterogeneity and will not guess.
- **The 6 floor-crossing hops in §2.2.** Worth a human read; I have not read
  their biology.
- **Anything about the writer.** Out of scope here and still blocked on
  `nextseek_api` source that is not in this repo.

I did not complete a line-by-line audit of `_schema.py`, `claims.py`,
`vocabulary.py`, `compatibility.py`, `backtest.py` or the review modules. What is
above comes from the generation path — `gate.py`, `classify.py`, `mode2.py`,
`lineage.py`, `precedent.py`, `dossier.py` — plus the artifacts.
