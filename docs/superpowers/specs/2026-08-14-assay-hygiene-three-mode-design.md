# Assay Hygiene, stages A-F: three equal modes over one evidence layer

**Date:** 2026-08-14
**Amended:** 2026-08-17. See "Amendment: absence is not contradiction". The mode
table, the build order, and Mode 3's validation all changed. Do not plan from the
sections below without reading that amendment first.
**Status:** increment 1 built and reviewed. Increments 2 and 3 not built.
**Supersedes:** the stages A-F half of `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md`,
and the whole of `docs/superpowers/plans/2026-08-12-assay-hygiene.md`.
**Carries forward unchanged:** that spec's stage 0, its write-safety analysis, its
access architecture, and its credential traps.

## Why this rewrite exists

The 2026-08-12 design was built on measurements taken against a graph that was
missing 90,534 relationships, and it argued from three figures whose scope was
never pinned. Stage 0 shipped to production on 2026-08-14 and closed the
topology gap. Re-measuring afterwards, and then testing the metadata for the
first time, changed three things that the design rests on.

**1. The statistics survived, but only under scopes the old spec never stated.**

| Figure | Old | Re-measured 2026-08-14 | Scope that makes it true |
|---|---|---|---|
| backtest population | 216,114 | 299,076 | edges carrying assay AND protocol |
| unambiguous | 87.8% | 87.1% | per edge, scoped to DARK edges |
| disjoint split | 97.2% | 96.0% | share of dark edges |
| `D.TITR -> TIS` rate | 0.608 | 0.622 | graph-wide, not the 5,000-edge sample |

Two of those are measurable three different ways and two of the three readings
are wrong. "Both endpoints registered" reads 778,324, not 299,076. Per-hop
unambiguity reads 87.8%, matching the old number exactly, by coincidence. Every
figure in this document therefore carries its scope in the sentence that states
it.

**2. Sample metadata predicts curator-assigned assays, and it is tiered.**

Measured 2026-08-14 on the 360,027 curator-labelled edges, learning the
value-to-assay mapping on half the samples and scoring the held-out half.
The split is by sample, not by edge, because a sample fans out to many edges
and an edge-level split scores memorised answers.

| Signal | Coverage | Accuracy |
|---|---|---|
| strong fields: `Type`, `Instrument`, `Stimulation`, `Software`, `SlideStain`, `Assay`, `Channels`, `Stains` | 65.9% | **98.4%** |
| strong, then `Protocol` / `DataType` | 92.3% | 90.4% |
| `Type` and `Protocol` both predict and agree | 35.0% | **99.9%** |

All eight strong fields are 100% accurate on held-out data except `Type`
(97.6%) and `Software` (99.8%), but the last two are thin: `Channels` is
supported by 66 held-out edges and `Stains` by 13, against 77,212 for `Type`,
so their contribution is real but rests on very few observations and should not
be leaned on alone. The headline row is 65.9% / 98.4% with or without them.

Strong fields clear the 95% bar on their own. `Protocol` buys 26 points of
coverage and costs the bar, which makes it a corroborating signal rather than a
deciding one.

These three rows are reproduced by `scripts/measure_metadata_accuracy.py`, which
reads its field lists and its cascade order from
`scripts/assay_hygiene/_schema.py` (`STRONG_FIELDS` / `WEAK_FIELDS` /
`CLAIM_FIELDS`) so the measurement and the contract cannot diverge.

**3. Metadata answers a different question than Mode 2 asks.**

The design's flagship case was `D.IMG -> TIS` under CometChip Assay: 303,866
dark edges whose metadata names the assay on both sides, with a propagation rate
of exactly zero. It read as the largest reachable block in the database. Two
measurements killed that reading.

*The same children are registered in that assay on a different hop.* 1,364
`D.IMG -> CEL` edges carry `internal_assay_id 138` with both endpoints
registered. The convention exists and looks deliberate: register the immediate
input the image was taken from, not the upstream tissue those cells came from.
A rate of zero was evidence of a boundary, not an absence of evidence.

*Metadata describes the child, and Mode 2 asks about the parent.* `Type:
CometChip` on the child says what the child is. It says nothing about whether
the tissue belongs in the assay. Treating a claim about one endpoint as a
decision about the other is the error this rewrite is here to avoid.

**Edges are not writes.** That block is 2,074 children against 616 parents,
averaging 146 parents per child. Membership is written per sample and assay, so
backfilling it is **616 rows**, not 303,866. Every child-only edge count in the
old spec overstates write volume the same way. This document counts rows.

### A decision that was made and then revised

Mid-design the operator ruled that metadata evidence alone could carry a rule to
`MODE_2_PROPAGATE`, with the curator's APPROVE column as the gate, on the
strength of the CometChip block appearing to be 46% of all child-only volume.

That ruling was made before the two measurements above existed. Both undercut
its premise: the block is 616 rows rather than 303,866, and the metadata
supporting it describes the child while Mode 2 asks about the parent. The
operator revised it once the measurements were presented.

What survives is narrower and better supported. Metadata decides Modes 1 and 3
outright, where the question it answers is the question being asked. In Mode 2
it disambiguates which assay applies but does not by itself authorise a write.
The record is kept here so a later reader does not find an approved decision
silently absent from the design.

## Amendment: absence is not contradiction

**2026-08-17, after increment 1 shipped.**

**The operator found this.** Reviewing Mode 3's flagship pattern, 97 PAV samples
registered in 56 Patient Visit whose metadata carries `Type=Blood`, they
observed: a PAV that had tissue collected from it should be in Patient Visit AND
Tissue Collection, one incoming assay and one outgoing. So the flag is not a
contradiction. It is a missing parent registration, which is exactly what Mode 2
finds. And they added that this might make Mode 3 dependent on Mode 2 entirely.

Both halves held up under measurement. 86 of those 97 PAV samples have a TIS
child ALREADY registered in 74 Tissue Collection, and the precedent for that hop
is strong: `TIS child <- PAV parent` under assay 74 runs a propagation rate of
0.931 in project 2, against 27,161 both-registered and 2,009 child-only, plus
0.960, 0.808, 1.000 and 1.000 in four other projects. Mode 2 would fire on it
confidently.

**Mode 3 is also a lossy detector of the same thing.** The 2,009 child-only
figure is the real size of that gap on that one hop. Mode 3 surfaced 97, because
it only sees samples whose metadata happens to carry a term the vocabulary maps.

### Why it happened

The mode table said Mode 2 finds an ABSENCE and Mode 3 finds a CONTRADICTION,
and left the distinction in prose. What increment 1 built tests
`claimed_assay not in registered_assays`, which is an absence test. It never
distinguished "should be in both" from "cannot be both", because nothing in the
code knew a sample could legitimately hold two assays at once.

A prose distinction between two modes, with no operational test separating them,
becomes whichever one the code happens to implement. The fix is not a better
sentence in the table. It is the two tests defined under Scope, both of which
run over data already on disk.

### What changed in this document

1. The mode table: Mode 2 runs in both directions, Mode 3 is scoped to the
   residue after corroboration.
2. A new domain rule, that a sample can hold an incoming and an outgoing assay.
3. Two operational tests, with the measured disposition of all 866 flags.
4. The build order: Mode 2 detection moves ahead of Mode 3 interpretation, and
   every write moves to increment 3.
5. Mode 3's validation gains an automatable precondition.

### Provenance of the figures in this amendment

The 88 / 263 / 515 lineage split and the whole disposition table are re-derived
by `scripts/measure_absence_vs_contradiction.py`, committed alongside this
amendment and read-only.

An earlier ad hoc version of that split, quoted in the 2026-08-17 handoff report
as 88 / 279 / 499, is WRONG in two of its three cells. The child figure was
right; the parent and neither figures were not. The difference is the handling
of 14 duplicate uuids and 755 `childof` rows that do not resolve to a sample on
both ends. Anyone carrying numbers forward from that report should take them
from the script instead.

The 86-of-97 PAV figure and the 0.931 propagation rate were both correct and are
confirmed here.

## Scope

Three modes, equal citizens, over one shared evidence layer.

**Amended 2026-08-17.** This is the corrected table. The original is preserved in
the amendment section below, because increment 1 was built against it.

| Mode | Question | Decided by | Metadata's role | Writes |
|---|---|---|---|---|
| 1 | sample is in NO assay at all; which one? | metadata claim | decides | add sample to assay |
| 2 | a lineage NEIGHBOUR carries an assay this sample lacks; add it? | precedent on the hop | disambiguates which assay | add parent to assay, or add child to assay |
| 3 | metadata claims an assay that NEITHER the registration NOR the lineage NOR type precedent supports | metadata vs registration vs co-registration | decides | nothing, flags only |

Three changes from the original table, all forced by measurement.

**Mode 2 runs in both directions.** The original scoped it to "parent missing
from the child's assay". The mirror case, a child missing from the parent's
assay, is the larger of the two: over the 866 Mode 3 flags it is 263 against 88.
`_schema.py` already carries `A_ADD_PARENT` and `A_ADD_CHILD` as separate
actions, so the code anticipated this and only the spec was narrow.

**Mode 3 is scoped to what it can actually establish.** It does not detect
contradiction by testing `claimed not in registered`, because that is an absence
test and a sample can legitimately hold more than one assay. It detects a claim
that survives both corroboration tests defined below.

**The three modes are ordered by evidence, not by population.** Mode 1 needs no
neighbour. Mode 2 needs a neighbour that carries the claim. Mode 3 is the
residue after both. A flag can only be Mode 3 if Modes 1 and 2 have already
declined it, which is why Mode 2's detection must run before Mode 3's output is
read.

Mode 3 remains an auditor that writes nothing, runs over all 177,392 samples
rather than only those on an edge, and carries none of the deletion hazard. What
changed is its size, not its safety: scoped correctly it flags 51 samples on
today's extract rather than 866.

### The domain rule the design lacked

**A sample can legitimately belong to more than one assay, typically one
incoming and one outgoing.** A PAV that had tissue collected from it belongs in
56 Patient Visit, which produced it, and in 74 Tissue Collection, which consumed
it. Neither registration is wrong and neither excludes the other.

Nothing in increment 1's code represents this. `audit_contradictions` tests
`claimed_internal_assay_id not in registered_internal(sample)`, so every
legitimate second assay reads as a contradicted first one. This rule is the
whole distinction between Mode 2 and Mode 3 and it must be encoded, not assumed.

### Absence and contradiction, made operational

Two deterministic tests. Neither needs a model. They are independent: the first
asks the graph about this sample's neighbours, the second asks the graph about
this sample TYPE's habits.

**Test 1, lineage.** Does a parent or child of this sample already register the
claimed assay? If so, the sample's own lineage corroborates the claim and what
is missing is a registration. This is Mode 2 by definition, and the direction of
the neighbour selects `A_ADD_PARENT` or `A_ADD_CHILD`.

**Test 2, compatibility.** Across every sample of this type registered in R,
what share ALSO register the claimed X? Call it the co-registration rate.

- A high rate means R and X routinely coexist on this type, so the absence is
  the anomaly and the claim is an absence.
- A rate of exactly zero on a well supported population means they never
  coexist. This is the only evidence in the pipeline that supports the word
  contradiction.
- A middling rate establishes neither and must be reported as unresolved rather
  than resolved by a threshold nobody has backtested.

Support matters and is reported separately. A rate of 0.000 over four samples is
noise, not a finding, and must never be called a contradiction.

**Measured over the 866 flags** in `assay-hygiene/mode3-contradictions.csv` as
increment 1 produced them, at its default tiers. Reproduce with
`scripts/measure_absence_vs_contradiction.py`, read-only, which prints every row
here and writes `assay-hygiene/mode3-disposition.csv`.

| | never co-occurs | no support | routinely co-occurs | sometimes |
|---|---|---|---|---|
| **child registers it** | 0 | 0 | 88 | 0 |
| **parent registers it** | 24 | 13 | 15 | 211 |
| **neither** | 51 | 0 | 250 | 214 |

Reading that table as dispositions:

| Disposition | Flags | Share | Mode |
|---|---|---|---|
| `ABSENCE_LINEAGE` a neighbour already carries the claim | 351 | 40.5% | 2 |
| `ABSENCE_COMPAT` no neighbour, but the two assays routinely coexist | 250 | 28.9% | 2 candidate, unproven |
| `UNRESOLVED` neither test settles it | 214 | 24.7% | needs judgment |
| `CONTRADICTION` no neighbour, and the two assays never coexist | 51 | 5.9% | 3 |

**94.1% of what increment 1 called a contradiction is not one.** The two tests
agree perfectly where lineage is strongest: all 88 child-registered flags also
sit in the routinely-coexists band, which is a consistency check the design did
not ask for and passed.

They disagree on 24 flags where a parent carries the claim but the type never
co-registers the pair. That disagreement is real and is not resolved here. It is
reported as its own class for a curator, because a sample whose parent is in an
assay its type never shares is either a genuine contradiction or a mislabelled
parent, and the pipeline cannot tell which.

**The flagship case, split.** The 122 PAV samples claiming 74 Tissue Collection
are two populations, not one:

| raw value | flags | explained by lineage |
|---|---|---|
| `Blood` | 97 | 86 (88.7%) |
| `Necropsy` | 25 | 2 (8.0%) |

The 86 of 97 confirms the operator's reading exactly. The `Necropsy` variant
behaves oppositely under the same test and was invisible while both were quoted
as one 122-row pattern. Grouping by `(sample_type, claimed_assay)` without
`raw_value` merges populations that behave differently, and any pattern table
must key on the raw value.

**The residue that survives both tests** is 51 flags over 5 patterns, dominated
by one: 44 `D.IMG` samples claiming 145 Histopathology, whose registered assay
127 never co-registers 145 across 1,907 samples of that type. That single
pattern is the real Mode 3 finding in this database, and it was 5% of a list of
866 nobody could read.

### What this costs and what it does not

The two tests are read-only, deterministic, and run over the extract already on
disk. Neither needs the write path, an LLM, or production access. `precedent.py`
already carries the propagation rates; the lineage test is a lookup against
`childof.parquet` and `membership.parquet`.

The compatibility test is NOT a substitute for the Mode 2 backtest. It says two
assays coexist on a type; it does not say this sample should be added, and it
carries no measured precision. Everything it produces is a candidate for Mode
2's precedent-decided path, never an authorised write.

Mode 2 keeps precedent as its decider. What metadata adds is discrimination:
`D.IMG -> TIS` carries 23 assay rules, precedent can only speak about the hop as
a whole, and `Type` / `Protocol` vary per sample. That is the one thing
precedent structurally cannot do.

## Architecture

```
A.  extract      in-container, read-only              -> extract/*.parquet
B.  precedent    deterministic                        -> precedent.csv
B2. claims       deterministic + a cached alignment   -> claims.parquet, vocabulary.csv
C.  classify     deterministic                        -> findings.csv
D.  adjudicate   rule-level LLM over all evidence     -> decisions.csv
E.  emit         deterministic                        -> ASSAY_HYGIENE-update.xlsx
F.  apply        guarded, over HTTPS                  -> applied/<ts>-manifest.jsonl
```

Production is touched twice: A reads, F writes. B through E re-run locally
without touching it.

B and B2 are separate stages on purpose. One counts graph membership, the other
extracts text from JSON blobs. They fail in unrelated ways, and when a number
looks wrong you need to know which half to distrust. Neither knows about modes;
the mode vocabulary lives entirely in C.

### Stage B2: claims

For every sample, what assay does its own metadata say it belongs to.

Output one row per (sample, claimed internal_assay_id, tier, source field,
raw value). A sample may claim more than once; disagreement between fields is
data, not an error, and stage C decides what to do with it.

Tiers, from the measurement above:

- `strong` — a strong field predicts. 98.4%.
- `corroborated` — `Type` and `Protocol` both predict and agree. 99.9%.
- `weak` — only `Protocol` or `DataType` predicts. 90.4%.
- `conflict` — populated fields predict different assays. 3.1% of the labelled
  population. Goes to stage D.
- `none` — nothing predicts.

Tier is assigned by rule, not by model. The percentages above are the
justification for the tiers and must be re-derived by Task 2, not copied.

### The vocabulary alignment

Something must map `cometchip` onto `internal_assay_id 138`. That mapping is
**observed in 1,364 curator-labelled edges**, so it is learned, not inferred.

1. Learn (field, normalised value) -> internal_assay_id from the labelled edges
   by majority vote, with a minimum support threshold, holding out a split to
   score it.
2. Hand the LLM only the terms with no empirical anchor.
3. Write the union to `vocabulary.csv` with, per term: the mapping, its support
   count, its purity, and whether it came from data or from the model.
4. A curator may correct any row. Corrections win over both sources and survive
   re-runs.

This inverts the trust story in the useful direction. Common terms are backed by
what curators actually did, at a measured rate. The model handles the tail, and
its proposals land in a file a human can read and correct rather than
disappearing into hundreds of thousands of individual inferences.

`vocabulary.csv` is the most durable artifact this project produces after the
graph itself: the first written-down mapping between how people label samples
and how the assay vocabulary is structured. It is independently useful, and it
should be committed and reviewed even if no write ever ships.

Sizing the model's share of the tail is Task 2's first measurement. It is not
estimated here.

### Stage D: the LLM judge

The LLM judges **rules, not rows**: one call per (project, hop, assay) candidate
with all evidence in front of it, not one call per edge. Hundreds of calls, not
hundreds of thousands. The curator sheet stays rule-level and reviewable, and a
row-level sheet at this volume would be rubber-stamped rather than read.

Each call sees: the precedent numbers, the metadata claim distribution and its
tiers, the `D.*` / `A.*` sample-type tiebreak, the affected row count, and a
handful of example UIDs with their raw metadata. It returns a verdict, a
confidence, and the rationale a curator reads.

Order inside D is deterministic-first: thresholds, then the tiebreak, then the
model. Anything the deterministic layers settle never reaches the model.

**Reproducibility.** D is the only non-reproducible stage. It caches on a hash
of its full input, so an approved decision cannot drift when the pipeline is
re-run. A cache miss is visible in the output, never silent.

## Validation

Each mode is validated separately, because each infers a different thing. The
95% bar is stated per mode, reported rather than asserted, and the run refuses
to write when unmet unless explicitly overridden.

**Mode 1.** Hide the membership of samples that have one, predict from metadata
alone, measure recovery. This is exactly the measurement already run: 98.4% on
strong-field coverage. It must be re-derived inside the harness rather than
inherited from this document.

**Mode 2.** The precedent backtest carried forward from the old spec. Hide the
parent's membership on a held-out slice of the edges where both sides are
registered, run inference cold, measure recovery of the assay a curator
assigned. Thresholds are an output of that curve, never chosen in advance.

**Mode 3.** Precision here is agreement with a human, and it cannot be
automated. Mode 3 writes nothing, so a wrong flag costs attention rather than
data.

*Amended 2026-08-17.* Increment 1 shipped this validation as "emit a sample for
curator review" and that is not enough, because it cannot distinguish a wrong
flag from a correctly detected absence. Mode 3 now has one automatable
precondition before any human sees a flag:

**Every flag must survive both corroboration tests.** A flag whose claim is
carried by a lineage neighbour, or whose assay pair routinely coexists on its
sample type, is not a Mode 3 finding and must be routed to Mode 2 instead of
shown to a curator. This is a property of the classifier and is testable
without a human: on the current extract the audit's 866 must reduce to 51.

Only the residue goes to a curator, keyed by `(sample_type, claimed_assay,
raw_value)` and never by `(sample_type, claimed_assay)` alone, because the PAV
`Blood` and `Necropsy` populations behave oppositely under the same tests and
were merged by the coarser key.

The `UNRESOLVED` class is reported as its own population with its size stated.
It is not folded into either mode. Reporting 214 flags the pipeline cannot
classify is the honest output; silently banding them into Mode 3 would restate
the same error this amendment exists to fix.

### What cannot be validated, stated plainly

A backtest measures recovery of known-good labels. Where a hop and assay have no
labelled examples anywhere, there is no ground truth and precision is
unmeasurable **by construction**. No threshold, sample size, or model choice
fixes this.

For those cases the honest basis is transferred evidence: metadata's measured
accuracy on the population where ground truth does exist, applied where it does
not, and labelled as such on the sheet. A rule resting on transferred evidence
must say so in its rationale, and must never be presented as carrying a measured
precision it does not have.

## Write safety

Carried forward unchanged from the 2026-08-12 spec, and binding.

The proven writer is `smart_merge_assay_assets`
(`nextseek_api/batch_upload/update.py:117`, bulk path `:429-447`). It is keyed
per sample with a COMPLETE assay list, computes `to_remove = old - new`, and
bulk-deletes. Consequences:

1. **A sample's assay list must always be complete.** Stage F unions additions
   onto the sample's existing assays and sends the whole set, never a delta. A
   test must assert the guard refuses to send a partial list.
2. **Addition at scale is unproven.** That writer has been exercised across
   ~200k production rows, but every id in those payloads was round-tripped out
   of `assay_assets`, so `to_remove` did the work and `to_add` was plausibly
   always empty. The dev-box probe must test an ADDITION and its reversal, not a
   deletion, and it is a hard stop before F runs anywhere.

## Build order

**Amended 2026-08-17.** The original order is preserved at the end of this
section. It split the increments on WRITE RISK, which was right about safety and
backwards about interpretability.

Three shippable increments. The first two write nothing at all; every write in
the project lands in the third.

**1. Evidence layer plus Mode 3 detection. BUILT.** Stages A, B, B2, the
vocabulary alignment, and the audit. Produces `vocabulary.csv` and
`precedent.csv`, both independently useful. 65 commits, reviewed whole. Its Mode
3 output is mis-scoped as described in the amendment above and is superseded by
increment 2, but the evidence layer under it stands.

**2. Mode 1 and Mode 2 detection, read-only.** Stage C for all three modes, plus
the two corroboration tests, plus the Mode 2 backtest. No stage D, no curator
workbook, no write path. This increment answers "what would we change" and
nothing else. It also re-scopes Mode 3 by subtraction, which is the reason it
comes before anyone reviews Mode 3's flags.

**3. Adjudication, the curator workbook, and the write path.** Stages D, E and
F, behind the addition probe. The deletion hazard is faced once, here.

### Why detection precedes interpretation

Every Mode-2-shaped gap appears as a Mode 3 flag until Mode 2 fills it. On
today's extract that is 601 of 866 flags, 69.4%, and it was not visible until
the two tests above were run. Mode 3's numbers cannot be read before Mode 2 has
run, so ordering Mode 3 first optimised for shipping something safe and produced
something unreadable.

The corrected order costs nothing in safety. Mode 2's DETECTION needs no write
path: stages B and C are read-only and only stage F writes.

**Do not ask a curator to review Mode 3's 866 flags as increment 1 emitted
them.** 94.1% of that list is absence reported as contradiction, and the review
would burn the curator's attention and their trust in the tool.

### Original build order, superseded

Kept because increment 1 was built against it. It read: (1) evidence layer plus
Mode 3, (2) Mode 1, where the write path gets proven on the smallest population
behind the Task 8 addition probe, (3) Mode 2, last because it depends on both
earlier increments being trustworthy. The reasoning was that the deletion hazard
should be faced once, on hundreds of rows rather than tens of thousands. That
reasoning survives and now applies to increment 3.

## Outputs

- `vocabulary.csv` — the alignment, with provenance and curator corrections
- `precedent.csv` — the mined sample-type-to-assay-to-sample-type map,
  independently useful as a lookup
- `claims.parquet` — per-sample metadata claims with tiers
- `findings.csv` — per-sample classification, one row per (sample, claimed
  assay), carrying the mode, the disposition, and both corroboration tests
- `mode3-disposition.csv` — the 866 audit flags re-scoped by both tests, which
  is how increment 1's Mode 3 output is superseded rather than deleted
- `ASSAY_HYGIENE-update.xlsx` — rule-level, one row per (project, hop, assay,
  verdict) with evidence, affected ROW count, and a curator-owned APPROVE column
- `applied/<ts>-manifest.jsonl` — what stage F actually sent

The first four are increment 2 and earlier, and are read-only. The last two are
increment 3 and are the only artifacts in the project that imply a write.

## Findings this design does not address

**Bulk over-linking.** 2,074 CometChip images declare 146 tissue parents each,
at 24% of the full cross-product. That is not per-sample lineage; it looks like
every image in an experiment linked to every tissue in it. If so, the defect in
those 303,866 edges is the edges themselves and no membership backfill is the
right fix. Stage 0 created edges from what the metadata declared, correctly. The
question of whether the metadata should have declared them is upstream of this
pipeline and belongs with the PI.

This is reported, quantified, and not acted on. It should be measured across all
hops, since the fan-out ratio is cheap to compute and nobody has looked.

**Workstream B residue**, unchanged from the stage 0 report: 2,392 parent tokens
that are not UIDs, 6 declared parents with no Sample node, 881 CHILD_OF edges
current metadata no longer declares, and 5,248 stage 0 children with no protocol
value.

**The legacy update path writes no lineage at all.** `__batchUpdateSample`
contains zero calls to `storeSampleNeo4j`, and the only live write is gated on
`if newSample:`. That may be a larger contributor to the historical gap than
anything here, and it is unquantified against the extract.

## Measured figures, 2026-08-14, post-stage-0

All against `assay-hygiene/extract/` taken after the stage 0 write.

```
DERIVED_FROM total                794,593
  labelled                        360,027   45.3%
  dark                            434,566   54.7%

dark, by cause
  both registered, DISJOINT       417,399   96.0%   -> Mode 2
  child in no assay                 7,924    1.8%   -> Mode 1
  neither registered                5,935    1.4%   -> Mode 1
  parent in no assay                1,935    0.4%   -> Mode 1
  share an assay yet dark           1,373    0.3%   -> genuine sync gap

precedent
  rules mined                         961
  project/hop pairs with precedent    213

  band                rules   of those, with   child-only edges
                              child-only > 0   in the band
  rate >= 0.95          175                5                 99
  rate 0.60 - 0.80       19               19             70,904
  rate exactly 0        709              269            564,500
```

BOTH rule columns are given because the earlier version of this table silently
mixed them. It read `rate >= 0.95 -> 5 rules, 99 child-only edges`: the rule
count scoped to rules that carry child-only volume, beside the edge count taken
over the whole band. Unscoped the band holds **175** rules, and `rate exactly 0`
holds **709**, of which 440 sit at (`n_both` 0, `n_child_only` 0) -- parent-only
observations with nothing to propagate -- leaving the 269 the old row quoted.
The middle row was correct unscoped and is unchanged.

"project/hop pairs" and not "hops": the unit is the triple (`project_id`,
`child_type`, `parent_type`). This extract happens to hold exactly 213 distinct
(`child_type`, `parent_type`) pairs as well, so the bare word read as "every hop
in the graph has precedent" against a coincidence. The true type-pair figure is
**153 of 208** appearing on a rule row (213 appear on an edge).

The concentration matters: the actionable mid-band is essentially two rules,
`D.TITR -> TIS` under Titer Assay at 0.622 and `D.FCRB -> TIS` under Fc Receptor
Binding at 0.796. Above 0.95 there are 99 child-only edges in the entire
database, spread over the 5 of those 175 rules that have any. A threshold picked
by intuition would do nothing.

Reproduce with `scripts/remeasure_post_stage0.py` and
`scripts/measure_metadata_accuracy.py`, both read-only over the extract. The
first prints every row above, including all three bands at both scopes; it did
not print any of the three when this table was written, which is how the scope
mix survived.
