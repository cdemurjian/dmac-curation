# Assay Hygiene, stages A-F: three equal modes over one evidence layer

**Date:** 2026-08-14
**Amended:** 2026-08-17, TWICE, the second superseding the first. See "Amendment:
what the three modes actually are". The mode table, the build order, Mode 3's
validation, and the write-authorisation model all changed. Do not plan from the
sections below without reading that amendment first.
**Binding constraint:** nothing writes without per-row operator approval, in all
three modes. Any "decides", "guarded" or "threshold gates the write" phrasing
elsewhere in this document predates that constraint and is superseded by it.
**Status:** increment 1 built and reviewed, and its Mode 3 output is known bad.
Increments 2 and 3 not built. Mode 3 has no working detector.
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

What survives is narrower and better supported. In Mode 2 metadata disambiguates
which assay applies but does not by itself authorise a write. The record is kept
here so a later reader does not find an approved decision silently absent from
the design.

*Superseded 2026-08-17.* This paragraph read "Metadata decides Modes 1 and 3
outright, where the question it answers is the question being asked." Nothing
decides now. See "Nothing decides. Everything proposes."

## Amendment: what the three modes actually are

**2026-08-17, after increment 1 shipped. This supersedes an earlier amendment
made the same day, which was itself wrong.** Both are recorded, because the
error they share is the one this project keeps making.

### What the operator asked for

Verbatim, and this is the canonical statement of what the system is for:

> 1. What samples have no assays and need some
> 2. What samples have assays in one direction but not both and need a second assay
> 3. What samples have INCORRECT assays

Plus a binding constraint on all of it:

> there should be no "auto / guarded: writes" everything should come to me for
> approval for either 3 of the modes.

### Two corrections, one week apart, both from the operator, both the same error

**Correction 1: absence reported as contradiction.** Increment 1's audit tests
`claimed_assay not in registered_assays`, which is an ABSENCE test, and reported
the result as CONTRADICTION. The operator observed that a PAV sample with tissue
collected from it belongs in Patient Visit AND Tissue Collection, one incoming
and one outgoing, so the absence of the second is a missing registration. 86 of
those 97 PAV samples have a TIS child already registered in 74 Tissue
Collection, and the hop runs a propagation rate of 0.931 in project 2. Mode 2
would fire on it confidently.

**Correction 2: the residue is not contradictions either.** Reviewing the 51
flags that survived, the operator observed that they name correct assays. Adding
a third test confirms it: 45 of 51 are ALTERNATIVE LABELS (D.IMG images sit in
127 Tissue Imaging or 145 Histopathology, never both, because a curator picks
one, and 145 D.IMG samples are registered in Histopathology), and 6 are
VOCABULARY DEFECTS, where the claim itself is junk.

**The shared error: a bucket named for what someone assumed was in it, rather
than for what a test proves is in it.** It has now occurred three times. The
third instance was found by adversarial review and is described below. Assume a
fourth exists.

### The third instance, found by review

The 24 flags where a parent carries the claim but the pair never co-occurs are
labelled `ABSENCE_LINEAGE` and routed to Mode 2 as future write candidates. They
are, measured:

| n | type | registered | claims | via |
|---|---|---|---|---|
| 11 | A.FLOW | 31 Flow Cytometry **Analysis** | 30 Flow Cytometry | `Software: FlowJo` |
| 13 | A.SPC | 47 Mass Spectrometry **Analysis** | 130 Mass Spectrometry | `Type: High resolution mass spectra` |

Both are the analysis-versus-measurement pair, the same family as correction 2.
Lineage precedence fires first, nothing tests the vocabulary, and so vocabulary
defects are laundered into membership write proposals.

An earlier version of this section claimed these 24 were "reported as their own
class for a curator". **That was false.** `mode3-disposition.csv` files them
inside the 351.

### The vocabulary is the largest single defect source

Measured over `vocabulary.csv` and the 866 flags:

- One mapping, `Illumina Library` -> 24 DNA Extraction at purity **0.707** over
  2,210 samples, produces **212 of the 250** `ABSENCE_COMPAT` flags. An Illumina
  library is a library; those DNA samples are already correctly registered in
  115 Library Creation.
- One product is split across three assays: `flowjo` -> 30, `flowjo v10.8.1` ->
  31, `flowjo version 10` -> 31, `flowjo 10.3` -> 153. Nothing checks that a
  term family maps coherently.
- 31 of the 866 claims name an assay **no sample of that type has ever been
  registered in**, anywhere in the database.

A claim is only as good as the term that produced it, and no stage tests the
term. This is why the vocabulary gate below runs before every mode.

### The three tests, and what each actually establishes

Deterministic, no model, all over the extract already on disk. Each is named for
what it tests.

| Test | Question | Establishes |
|---|---|---|
| **Reachability** | is this sample TYPE ever registered in the claimed assay, anywhere? | whether the CLAIM is credible at all |
| **Lineage** | does a parent or child already register the claimed assay? | that the claim is an ABSENCE, and which direction |
| **Co-registration** | across samples of this type in R, what share also hold X? | whether R and X coexist, or are alternative labels |

**Order matters and is a contract.** Reachability first, because an incredible
claim must never reach a membership proposal. Then lineage. Then
co-registration. Increment 1's precedence ran lineage first and had no
reachability test at all, which is what produced the third instance above.

Measured over the 866, with reachability applied first:

| Class | n | Routes to |
|---|---|---|
| claim not credible (type never in claimed assay) | 31 | vocabulary curation, NOT a mode |
| claim credible, neighbour carries it | 326 | Mode 2 |
| claim credible, no neighbour, pair coexists | 250 | Mode 2 candidate, unproven |
| claim credible, no neighbour, pair never coexists | 45 | alternative label, no action |
| claim credible, neither test settles it | 214 | judgment |

The 24 FlowJo and mass-spectra rows sit inside the 326 today and must be pulled
out by the vocabulary gate, not by the lineage test.

**The `UNRESOLVED` 214 is mostly one benign pattern.** 204 are RNA samples with
`Type: total RNA` claiming 61 RNA Extraction, and RNA samples ARE registered in
RNA Extraction 1,087 times. That is a credible claim and an ordinary absence.

**Support matters and is reported separately.** A co-registration rate of 0.000
over four samples is noise. A rate is never read as evidence below 30 samples of
the type.

### The domain rule the design lacked

**A sample can legitimately belong to more than one assay, typically one
incoming and one outgoing.** A PAV that had tissue collected from it belongs in
56 Patient Visit, which produced it, and in 74 Tissue Collection, which consumed
it. Neither registration is wrong and neither excludes the other.

Nothing in increment 1's code represents this, which is why every absence read
as a contradiction.

### Nothing decides. Everything proposes.

**Binding, and it overrides every "decided by" phrase elsewhere in this
document.** No mode writes on its own authority. Every proposed change in all
three modes reaches the operator as a row they approve or reject, and an
unapproved row is never sent.

Consequences, each of which contradicts something this spec said before:

1. **Thresholds do not gate writes.** They rank and triage so the operator reads
   the strongest evidence first. A backtest curve sets reading order, not
   permission.
2. **"Metadata decides Modes 1 and 3 outright" is retired.** Metadata proposes.
3. **The approval artifact must carry all three modes.** The rule-level workbook
   is keyed `(project, hop, assay)`, and Mode 1 findings have no hop, so that
   key structurally cannot carry them. A second shape is required.
4. **There is no "unless explicitly overridden".** The validation bar being
   unmet blocks a proposal from being made; it is not a lock the run can pick.

### Mode 3 has no working detector yet

Stated plainly, because the alternative is to ship a mode that reports
alternative labels as errors.

The operator's Mode 3 is "what samples have INCORRECT assays". The detector
built for it finds claims that disagree with registrations, and measurement now
shows that population is alternative labels and vocabulary defects, with
approximately zero genuine mis-registrations. Metadata disagreeing with a
registration is simply not evidence that the registration is wrong.

Candidate detectors that do not depend on the vocabulary, all measurable today
and none built:

- **Registration-side reachability.** A sample registered in an assay its own
  type is otherwise never registered in. This is the mirror of the claim-side
  test and needs no metadata at all.
- **Cross-project registration.** 1,340 membership rows register a sample in an
  assay whose project set is disjoint from the sample's own projects, plus 271
  samples with no project at all.
- **Removal proposals.** Mode 3 implies some assays should come off a sample.
  No mode generates that proposal. The writer's complete-list semantics can
  already express it, and under universal approval a removal is as reviewable as
  an addition, but the deletion hazard means it ships last and separately.

Until one of these is built and validated, Mode 3 reports and proposes nothing.

## Scope

Three modes over one shared evidence layer, behind one vocabulary gate.

| Stage | Question | Evidence | Proposes | Writes |
|---|---|---|---|---|
| **Gate** | is this claim credible? | term-family coherence, mapping support and purity, type reachability | vocabulary corrections | never |
| **1** | sample is in NO assay; which one? | metadata claim | add sample to assay | only on approval |
| **2** | a lineage NEIGHBOUR carries an assay this sample lacks | precedent on the hop, metadata disambiguates | add parent to assay, or add child to assay | only on approval |
| **3** | sample holds an INCORRECT assay | no working detector yet | nothing | never |

The gate is not a mode. It produces no membership change. A claim that fails it
is excluded from Modes 1 and 2 entirely and routed to `/curate-assay-vocabulary`.

**Mode 2's two directions are not equally supported.** `A_ADD_PARENT` is the
direction the operator's domain rule justifies and the evidence backs.
`A_ADD_CHILD` is the mirror, and it is weak:

| | ADD_PARENT | ADD_CHILD |
|---|---|---|
| corroborated by co-registration, over the 866 | **88 / 88, 100%** | 15 / 263, 5.7% |
| edge-weighted rate over `precedent.csv` | 0.351 | 0.280 |
| rules at rate >= 0.95 | 5 | 15 |
| candidate rows surviving rate >= 0.5 | 79,488 | **3,663** of 111,039 |
| rows that would create a (type, assay) pair existing nowhere | 55.6% | **67.6%** |

The mechanism behind the asymmetry: a sample has one producing assay but many
consuming ones, so "the child is in X" pins the parent tightly, while "the
parent is in X" says little about any one child. The cleanest single datum is
one hop carrying both directions: `TIS <- PAV` under 56 Patient Visit runs a
reverse rate of **0.006** while the same hop under 74 Tissue Collection runs a
propagation rate of **0.931**. On the very hop that justified Mode 2, the
parent's assay does not flow down while the child's flows up.

**An earlier version of this section argued for symmetry from volume**, that the
mirror is "the larger of the two, 263 against 88". That reasoning is backwards:
the 263 are precisely the weakly corroborated direction. `A_ADD_CHILD` survives
only where `reverse_rate` earns it, roughly 3% of its ceiling, and the spec must
never quote its unfiltered size without that qualification.

### Which lineage relation, stated once

`CHILD_OF` and `DERIVED_FROM` are different relations and the choice moves every
Mode 2 figure by about 9%.

```
CHILD_OF        742,534 pairs     ceiling  50,508 ADD_PARENT / 111,039 ADD_CHILD
DERIVED_FROM    794,593 edges     ceiling  55,007 ADD_PARENT / 117,463 ADD_CHILD
divergence      52,185 DF-only, 126 CO-only
```

**The DERIVED_FROM ceiling above is CONFIRMED, 2026-08-17.** The companion plan
published 54,780 / 116,365 for the same relation and neither reading had been
root-caused. Both are arithmetically correct: they differ only in the definition
of "registered". ANY membership row, crossed to the internal namespace by
`audit.registered_internal`, gives 55,007 / 117,463; dropping the 17
junction-less assays' registrations gives 54,780 / 116,365. ANY membership row
means registered, so this figure stands and the plan's has been corrected.
`lineage.mode2_ceiling` computes it, so it need never be quoted again. The
CHILD_OF line has NOT been re-measured under the corrected definition and is the
MAPPABLE-only reading; it is quoted here only to show the relation matters, and
Mode 2 uses DERIVED_FROM for both.

Precedent, the decider, is mined over `DERIVED_FROM`. A lineage test run over
`CHILD_OF` therefore asks about a different graph than the one its own evidence
was measured on. **Mode 2 uses `DERIVED_FROM` for both**, and any figure quoted
from the other relation says so. This is the branch's signature defect again,
two meanings one frame apart, and it was introduced by the first version of this
amendment.

### Metadata's role, narrowed again

Metadata decides nothing. It proposes, and only after the gate has accepted the
term that produced it.

In Mode 1 it is the only evidence available, so a Mode 1 proposal is exactly as
good as its vocabulary row. In Mode 2 it disambiguates which assay applies when
a hop carries several, which is the one thing precedent structurally cannot do:
`D.IMG -> TIS` carries 23 assay rules, precedent speaks only about the hop as a
whole, and `Type` / `Protocol` vary per sample.

### What the adjudicator needs in front of it

The operator asked for the logistics folded into the decision. Per proposed row,
all of the following already exist or are one query away:

- the sample's registered assays, with titles, crossed through the internal
  junction (`audit.registered_internal`, `precedent.assay_index`)
- the claim, its tier, whether it is contested, and its vocabulary row with
  support, sample count, purity and provenance
- both precedent rates for every hop touching the sample, with `n_both`,
  `n_child_only`, `n_parent_only`
- lineage neighbours and what they are registered in
- the co-registration rate and support for the assay pair
- the type's base-rate registration distribution
- peer examples: other samples of the type carrying the same term
- protocol and SOP titles, project ids, creation date

Missing and worth building: a `sample_types` extract, so `assays.sample_type_id`
resolves and the DECLARED sample-type-to-assay mapping can be compared against
the OBSERVED one that `precedent.py` mines. Today only the observed direction is
answerable. Also absent from the extract entirely: any record of WHO registered
a sample, so curator identity can never be evidence.

### What currently exists in the database

Measured, and worth stating because "what is already there" is half the
operator's question:

```
sample records                       163,393
membership rows                      214,296   over 157,151 samples
  registered only via a junction-less assay        82 samples
assay records                            458   of which 285 have ZERO samples
distinct internal assay ids used         110
assays with no junction row               17   forcing fallback identity in 4 places
lineage pairs (CHILD_OF)             742,534
DERIVED_FROM edges                   794,593   labelled 360,027, dark 434,566
mined precedent rules                    961   over 213 project/hop triples
learned vocabulary terms                 736   plus 266 unresolved, 0 curator-corrected
```

The 285 empty assays and the 266 unresolved terms are both cheap to report and
neither has been surfaced to a curator.

## Architecture

```
A.  extract      in-container, read-only              -> extract/*.parquet
B.  precedent    deterministic                        -> precedent.csv
B2. claims       deterministic + a cached alignment   -> claims.parquet, vocabulary.csv
C.  classify     deterministic                        -> findings.csv
D.  adjudicate   rule-level LLM over all evidence     -> decisions.csv
E.  emit         deterministic                        -> ASSAY_HYGIENE-update.xlsx
F.  apply        APPROVED ROWS ONLY, over HTTPS       -> applied/<ts>-manifest.jsonl
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
- `conflict` — **RETIRED, and this bullet is wrong.** It describes a tier the
  shipped code does not emit. `_schema.py:137-141` retired it and
  `tests/test_assay_hygiene_claims.py:76` pins `T_CONFLICT not in out.tier`;
  disagreement between fields is carried by the `contested` COLUMN instead, so
  that a contested claim keeps its own tier and the audit's monotonicity
  argument survives. Anything planning against this bullet will fail its own
  test suite. Left in place, corrected, rather than deleted, because the
  2026-08-12 plan and its readers still reference the tier.
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
95% bar is stated per mode and reported rather than asserted.

*Amended 2026-08-17.* This read "the run refuses to write when unmet unless
explicitly overridden". There is no override, because there is no autonomous
write to override. An unmet bar means the pipeline does not PROPOSE the row at
all; it never meant a lock the run could pick. Under universal approval the bar
governs what reaches the operator, and the operator governs what is written.

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

*Amended 2026-08-17, twice.* The first amendment required every flag to survive
both corroboration tests and asserted that the 866 "must reduce to 51". **That
target is now known to be wrong**, because measurement showed the 51 are
alternative labels and vocabulary defects rather than contradictions. Do not
pin 51 as a validation target.

Mode 3 cannot be validated because it has no working detector. See "Mode 3 has
no working detector yet". Its validation is defined when a detector exists, and
the honest interim statement is that the mode reports nothing.

**What is validatable today, and required of the classifier:**

1. **No claim that fails the vocabulary gate reaches any mode.** Testable
   without a human. The 24 FlowJo and mass-spectra rows are the fixture.
2. **No row corroborated by lineage is reported as an error.** This is the
   amendment's central claim and the thing that broke.
3. **Every pattern table is keyed `(sample_type, claimed_assay, raw_value)`**,
   never `(sample_type, claimed_assay)` alone, because the PAV `Blood` and
   `Necropsy` populations behave oppositely under the same tests and were
   merged, and invisible, under the coarser key.
4. **Each class is reported at its own size**, including the ones the pipeline
   cannot classify. Silently banding an unclassifiable row into a mode restates
   the error this amendment exists to fix.

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

**2. The vocabulary gate, plus Mode 1 and Mode 2 detection. Read-only.** The
three tests, the gate that runs before every mode, stage C, and the Mode 2
backtest. No stage D, no workbook, no write path. This increment answers "what
would we propose" and nothing else.

The gate leads the increment rather than trailing it. Measured, the vocabulary
is the largest single defect source in the current output: one mapping produces
212 of 250 `ABSENCE_COMPAT` flags, and lineage-first precedence launders 24 more
vocabulary defects into Mode 2 write candidates. Building detection on an
ungated vocabulary reproduces that by construction.

**3. Adjudication, the approval surface, and the write path.** Stages D, E and
F, behind the addition probe. Two approval shapes are required, because the
rule-level workbook is keyed `(project, hop, assay)` and Mode 1 findings have no
hop. The deletion hazard is faced once, here, and any removal lane ships after
the addition path is proven.

**Not scheduled: a Mode 3 detector.** Mode 3 has none. Building one is its own
increment and it is not increment 3.

### Why detection precedes interpretation

Every Mode-2-shaped gap appears as a Mode 3 flag until Mode 2 fills it. On
today's extract that is 576 of 866 flags, 66.5%, counted as the rows whose claim
is credible and which either carry a lineage neighbour or sit in a coexisting
pair. It was not visible until the three tests were run. Ordering Mode 3 first
optimised for shipping something safe and produced something unreadable.

The corrected order costs nothing in safety. Detection needs no write path:
stages B and C are read-only and only stage F writes.

**Do not ask a curator to review Mode 3's 866 flags as increment 1 emitted
them.** Measured, not one of the classes in that list is a contradiction: 576
are absences, 31 are vocabulary defects, 45 are alternative labels, and 214 are
unclassified. The review would burn the curator's attention and their trust in
the tool.

**And do not read that as "Mode 3 is small".** Mode 3 is not smaller than
believed; it is undetected. The list contained no contradictions at all, which
is a different and worse finding than a short list of real ones.

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
- `vocabulary-defects.csv` — claims rejected by the gate, with the failing test
  named, routed to `/curate-assay-vocabulary` and to no mode
- `mode3-disposition.csv` — the 866 audit flags re-classified, which is how
  increment 1's Mode 3 output is superseded rather than deleted
- `ASSAY_HYGIENE-update.xlsx` — the RULE-level approval surface, one row per
  (project, hop, assay) with evidence, affected ROW count, and an operator-owned
  APPROVE column. Carries Mode 2 only.
- `ASSAY_HYGIENE-mode1.xlsx` — the SECOND approval surface, required because
  Mode 1 findings have no hop and the rule key structurally cannot carry them.
  Grouped by (sample type, term, assay) so the operator judges terms rather than
  6,242 individual samples.
- `applied/<ts>-manifest.jsonl` — what stage F actually sent, and it may contain
  only rows an operator approved

Everything through `mode3-disposition.csv` is increment 2 or earlier and is
read-only. The two workbooks and the manifest are increment 3. **No artifact in
this project authorises a write except an APPROVE cell the operator filled in.**

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
