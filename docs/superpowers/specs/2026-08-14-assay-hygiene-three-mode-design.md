# Assay Hygiene, stages A-F: three equal modes over one evidence layer

**Date:** 2026-08-14
**Status:** design approved in conversation, not yet planned
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

## Scope

Three modes, equal citizens, over one shared evidence layer.

| Mode | Question | Decided by | Metadata's role | Writes |
|---|---|---|---|---|
| 1 | sample is in no assay; which one? | metadata claim | decides | add sample to assay |
| 2 | parent missing from the child's assay; add it? | precedent on the hop | disambiguates which assay | add parent to assay |
| 3 | registered assay contradicts the evidence | metadata vs registration | decides | nothing, flags only |

Mode 3 is no longer a footnote. A 98.4% predictor of a sample's assay is an
auditor, it runs over all 177,392 samples rather than only those on an edge, and
it writes nothing. It carries none of the deletion hazard and can ship before
the write path is proven.

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
automated. Stage D emits a sample of flagged contradictions for curator review,
and the flag rate is reported. Mode 3 writes nothing, so a wrong flag costs
attention rather than data.

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

Three shippable increments, in this order. Each is useful on its own, and the
riskiest work is last.

**1. Evidence layer plus Mode 3.** Stages A, B, B2, the vocabulary alignment,
and the contradiction audit. Writes nothing to production, needs no proven write
path, and produces `vocabulary.csv` and `precedent.csv`, both independently
useful. If the project stopped here it would still have paid for itself.

**2. Mode 1.** Samples in no assay at all. Metadata decides, validation is the
measurement already run, and the write is small and per-sample. This is where
the write path gets proven, on the smallest population, behind the Task 8
addition probe.

**3. Mode 2.** Precedent-decided, metadata-disambiguated, the largest population
and the only one whose thresholds come out of a backtest curve. Last, because it
depends on both earlier increments being trustworthy.

Splitting this way also means the deletion hazard is faced once, in increment 2,
on hundreds of rows rather than tens of thousands.

## Outputs

- `vocabulary.csv` — the alignment, with provenance and curator corrections
- `precedent.csv` — the mined sample-type-to-assay-to-sample-type map,
  independently useful as a lookup
- `claims.parquet` — per-sample metadata claims with tiers
- `findings.csv` — per-edge and per-sample classification
- `ASSAY_HYGIENE-update.xlsx` — rule-level, one row per (project, hop, assay,
  verdict) with evidence, affected ROW count, and a curator-owned APPROVE column
- `applied/<ts>-manifest.jsonl` — what stage F actually sent

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
  hops with precedent                 213
  rate >= 0.95                    5 rules,     99 child-only edges
  rate 0.60 - 0.80               19 rules, 70,904 child-only edges
  rate exactly 0                269 rules, 564,500 child-only edges
```

The concentration matters: the actionable mid-band is essentially two rules,
`D.TITR -> TIS` under Titer Assay at 0.622 and `D.FCRB -> TIS` under Fc Receptor
Binding at 0.796. Above 0.95 there are 99 child-only edges in the entire
database. A threshold picked by intuition would do nothing.

Reproduce with `scripts/remeasure_post_stage0.py` and
`scripts/measure_metadata_accuracy.py`, both read-only over the extract.
