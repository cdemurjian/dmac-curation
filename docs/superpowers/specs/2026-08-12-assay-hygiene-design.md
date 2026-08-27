# Assay Hygiene: complete the lineage graph, then backfill and audit assay membership

**Date:** 2026-08-12, rewritten 2026-08-13
**Status:** design approved 2026-08-12/13. **SUPERSEDED.** Stage 0 shipped
(`scripts/assay_hygiene/stage0.py`), stages A–F were redesigned as three modes on
2026-08-14, and assay hygiene is now a plugin mode. Read
`docs/superpowers/specs/2026-08-27-assay-hygiene-mode-design.md` and
`skills/curation/ASSAY.md` for what is current.
**Scope:** scripts under `scripts/assay_hygiene/`.

## Revision note

This is a rewrite, not an amendment. The previous draft treated the missing
`DERIVED_FROM` edges as out of scope because closing that gap looked like it
required an export-and-re-upload cycle through `batch_upload/orchestrator.py`,
carrying the membership-deletion hazard. Measurement on 2026-08-13 showed that
reasoning rested on the wrong function.

`upload_all` is orchestrator-only, but nothing needs `upload_all`.
`neo4j_sync.bulk_merge_relationships` (`neo4j_sync.py:157`) is an importable
pure function over `(driver, db_name, rows)` that writes **only to Neo4j**. No
MySQL write, no `smart_merge_assay_assets`, no deletion hazard. A committed
precedent for driving it standalone already exists:
`nextseek_api/batch_upload/scripts/backfill_parent_titles.py` imports
`batch_upload` internals, reads `samples.json_metadata`, and batch-writes Neo4j
from a script run in-container.

Closing the topology gap therefore became the cheapest and most certain work in
the project rather than the most awkward, and it moved to the front as **stage 0**.

## Problem

`chat_nextseek` graph queries of the form "what assay connects sample type A to
sample type B" silently return zero results for most type pairs. There are two
independent defects behind that, at different layers, with different fixes and
very different risk profiles.

### Defect 1 (topology): 89,960 relationships have no `DERIVED_FROM` edge

Measured on production 2026-08-13:

```
CHILD_OF total                742,534
DERIVED_FROM total            704,059
CHILD_OF without DERIVED_FROM  89,960
DERIVED_FROM without CHILD_OF  51,485
```

`CHILD_OF` is the legacy relationship type, superseded by `DERIVED_FROM` in the
2026-03 internal-assays migration. It appears nowhere in current server code and
is created by nothing today. `DERIVED_FROM` is the only edge type that carries
assay and protocol properties, so those 89,960 relationships are structurally
incapable of holding an assay and are invisible to every query this pipeline
builds.

The cause was a pair of exact-key lookups on `"Parent"` where the legacy code
used substring matching. Both halves are now fixed:

- Client side, the migration's exporter stripped every variant field
  (`phase4_sample_export.py:369`, `METADATA_KEEP_KEYS = {"UID","Parent","Protocol"}`).
- Server side, four functions checked only literal `"Parent"`. All four now
  substring-match: `dag.py:38` and `orphan_resolution.py:179` via
  `collect_parent_tokens`, `neo4j_sync.py:580` via the same helper, and
  `uid_gen.py:248` via its own `"parent" not in key.lower()` test.

So the gap is purely historical, from samples ingested before those fixes. The
data to close it is already in `samples.json_metadata` on production.

**Operator ruling (2026-08-13): `*Parent*` as a wildcard SHOULD be included.**
All variant parent fields are intended to become `DERIVED_FROM` edges, matching
the server's `"parent" in key.lower()` behavior. This puts reagent relationships
(`AntibodyParent`, 12,367 references) into the ancestry graph, which is intended.

**Operator ruling (2026-08-14), confirmed against the measured consequence:
`CompensationFCSParent` counts as parentage.** The 2026-08-13 ruling was made in
the abstract. When the dry run was reviewed it turned out that only **7.3%** of
what stage 0 would write is a plain `Parent` field:

| Declaring field | Meaning | Edges | Share |
|---|---|---|---|
| `CompensationFCSParent` | compensation bead control | 66,529 | **73.5%** |
| `AntibodyParent` | staining reagent | 11,934 | 13.2% |
| `Parent` | biological parentage | 6,616 | **7.3%** |
| `Treatment*Parent`, `BacterialParent` | dosing agent | 5,425 | 6.0% |

So nearly three quarters of the write asserts that a flow-cytometry sample
derives from its calibration file, e.g.
`D.FLOW-191202SAS-12 -> D.FCS-191203SAS-47 ("...IL6 APC (Beads).fcs")`. That is
a much larger share than the original ruling implied, and excluding
`CompensationFCSParent` would have been a one-line change dropping stage 0 from
90,534 edges to roughly 24,000. It was put back to the operator with the measured
numbers and confirmed: compensation controls are parents. The write stands at
90,534.

### Defect 2 (annotation): 426,695 `DERIVED_FROM` edges carry no assay

`nextseek_api/batch_upload/neo4j_sync.py:934` writes an assay onto an edge only
when child and parent are **both** members of that assay:

```python
shared = child_assays & parent_assays
```

Measured on production 2026-08-12:

```
704,059   DERIVED_FROM edges total
426,695   (60.6%)  no internal_assay_title / internal_assay_id
 84,070   (11.9%)  bare: only parent_id + child_id
341,808   (48.5%)  protocol present, assay absent
216,114   (30.7%)  full assay + protocol
```

Sampling 5,000 unlabeled edges and classifying each against `seek_production`:

```
4862   97.2%   both endpoints registered, DISJOINT assay sets
  63    1.3%   child in no assay (parent is)
  57    1.1%   neither endpoint in any assay
   9    0.2%   both share an assay      <- genuine sync gap
   9    0.2%   parent in no assay (child is)
```

Control, 5,000 edges that *do* carry an assay: 99.8% both share an assay. The
rule behaves exactly as coded.

#### Why the 97.2% is a defect and not a convention

The dominant pattern is a cross-stage hop where the child sits in the assay that
produced it and the parent sits in the assay that produced *it*:

```
CHILD  D.IMG-190503ENG-430   -> ['Comet Chip']
PARENT TIS-190502ENG-244     -> ['Tissue Collection']
```

That could be read as a deliberate outputs-only curation convention. It is not.
Among edges that *do* share an assay, 4,272 of 4,990 sampled are cross-type,
meaning the assay registers its inputs as well as its outputs:

```
1640  D.TITR -> TIS      -> Titer Assay
 736  TIS -> MUS         -> Tissue Collection
 711  D.FCRB -> TIS      -> FC Receptor Binding Assay
 506  TIS -> PAV         -> Tissue Collection, Patient Visit
```

The same hop under the same assay is curated both ways. `D.TITR -> TIS` is
registered on both sides 1,640 times and left dark 1,057 times. `D.FCRB -> TIS`:
711 registered, 148 dark. `TIS -> PAV`: 506 registered, 31 dark.

Registering the assay's inputs is the house convention. The dark edges are
inconsistent with how the identical hop is curated elsewhere in the same
database. Backfilling membership to precedent therefore makes the existing
intersection rule correct without a code change.

## Why stage 0 comes first, and why it is the cheap half

If the missing edges are created, the **existing, unmodified** intersection rule
labels almost all of them correctly with no inference at all. Measured 2026-08-13
against the exact stage 0 population (90,534 edges, see Source of truth below)
joined to `seek_production.assay_assets`:

| Outcome under the current rule | Edges | Share |
|---|---|---|
| **Both endpoints share an assay, labelled immediately** | **82,663** | **91.3%** |
| Disjoint sets, dark | 4,766 | 5.3% |
| Parent only registered, dark | 1,842 | 2.0% |
| Child only registered, dark | 1,211 | 1.3% |
| Neither registered, dark | 52 | 0.1% |

Stage 0 therefore creates 7,871 dark edges and 82,663 correctly labelled ones.

The gap is highly concentrated. The single hop `D.FLOW -> D.FCS` is 66,529
edges, 73% of the stage 0 population, and it is **100% both-share with zero
exceptions**.

Every one of the top ten gap hops has essentially zero `DERIVED_FROM` edges in
the graph today:

```
gap  66,529  D.FLOW -> D.FCS   existing DERIVED_FROM 0
gap  10,035  D.FLOW -> ABP     existing DERIVED_FROM 0
gap   2,274  MUS -> BAC        existing DERIVED_FROM 0
gap   1,686  D.IMG -> AB       existing DERIVED_FROM 0
gap   1,653  ABP -> AB         existing DERIVED_FROM 0
gap   1,592  MUS -> CHM        existing DERIVED_FROM 2
```

The entire flow-cytometry lineage is absent from the graph. No amount of
membership inference in stages A-F reaches it, because there is no edge to
annotate.

The two halves therefore have opposite risk profiles:

| | Stage 0 | Stages A-F |
|---|---|---|
| Writes to | Neo4j only | `seek_production.assay_assets` |
| Judgment required | none, reproduces declared metadata | inference, thresholds, LLM |
| Precision bar | not applicable | 95% on held-out data |
| Deletion hazard | none, additive MERGE | present, omission deletes |
| Write path proven | yes, `bulk_merge_relationships` | addition unproven, see Task 8 |
| Yield | 82,663 correctly labelled edges | hundreds of thousands of membership rows |
| Reversible by | delete the manifest's edges | manifest replay against a per-sample writer |

Stage 0 is deterministic, additive, graph-only, and independently valuable. It
does not depend on Task 8, on threshold selection, or on the LLM slice.

**Consequence for stages A-F: every statistic in this document below this line
was measured before stage 0 runs, and must be re-measured after it.** Stage 0
adds 90,534 edges of which 7,871 are dark, so the dark-edge count grows slightly
while the *proportion* falls from 60.6% to 54.7%. Computing precedent against the
pre-stage-0 graph would mine a graph that is missing its largest single hop.

## Non-goals

- Changing `neo4j_sync.py`. Stage 0 reuses its writer and its property rules
  verbatim; stages A-F make the intersection rule correct by fixing the data
  underneath it.
- Creating or moving Study or Investigation records.
- Deleting assays.
- **Deleting or modifying `CHILD_OF`.** Operator ruling 2026-08-13: leave it in
  place as a historical record and rollback reference. Stage 0 touches only
  `DERIVED_FROM`. No stage in this spec performs a destructive graph operation.
- Resolving the 2,392 parent tokens that are not UIDs at all (human-readable
  names, or malformed). Stage 0 reports them; resolving them is curation work.
- Deploying the `UID_RE` fix to production. Stage 0 works around it and reports
  it; shipping it is a NExtSEEK change, tracked separately.

## Architecture

| Stage | Nature | Writes | Output |
|---|---|---|---|
| 0. Complete | deterministic | Neo4j `DERIVED_FROM` | `stage0/report.md`, `stage0/manifest.jsonl` |
| A. Extract | deterministic | none | `extract/*.parquet`, `extract/assay_catalog.json` |
| B. Mine precedent | deterministic | none | `precedent.csv` |
| C. Classify | deterministic | none | `findings.csv` |
| D. Adjudicate | threshold + narrow LLM | none | `decisions.csv` |
| E. Emit | deterministic | none | `ASSAY_HYGIENE-update.xlsx`, `expansion.parquet` |
| F. Apply | guarded | `assay_assets` | `applied/<ts>-manifest.jsonl` |

Every stage caches to disk. B through E re-run locally without touching
production. Production is touched exactly three times across the whole pipeline:
stage A's extract (read), stage 0's apply (graph write), and stage F's apply
(membership write).

Stage 0 consumes stage A's extract. Ordering is: A, then 0, then a **second**
run of A to re-extract the enlarged graph, then B through F.

### Artifact layout

```
assay-hygiene/
  extract/                     A, cached, gitignored (contains sample metadata)
  stage0/
    report.md                  0, the reviewable dry-run report
    plan.parquet               0, every edge to be created, with properties
    manifest.jsonl             0, one line per edge actually written
    reconciliation.csv         0, CHILD_OF edges current metadata does not declare
  precedent.csv                B, the reusable map
  findings.csv                 C, every edge with verdict + matched rule
  decisions.csv                D, adds decided_by + rationale
  ASSAY_HYGIENE-update.xlsx    E, rule-level, has APPROVE column
  expansion.parquet            E, row-level drilldown
  applied/                     F, one manifest per apply run
```

## Stage 0: complete the lineage graph

### Source of truth: current metadata, not `CHILD_OF`

Two candidate sources exist and they do not agree. Measured 2026-08-13 by
running the live `collect_parent_tokens` over all 163,393 samples, with the
**corrected** `UID_RE` (see the regex regression below):

```
children declaring a parent                      155,566
declared UID parent refs (deduped)               793,554
tokens invalid under either regex (names etc.)     2,392
declared parents that exist as Sample nodes       73,841 of 73,847
```

Diffed against the graph:

| Source | Edges | |
|---|---|---|
| Promote `CHILD_OF` gap | 89,959 | excludes 1 self-loop |
| **Derive from current metadata** | **90,534** | what a *fixed* pipeline would produce |
| Both agree | 89,834 | 99.9% of the `CHILD_OF` gap |
| Metadata only, `CHILD_OF` never had them | 700 | dominated by `A.IMG -> D.IMG` |
| `CHILD_OF` only, not declared by metadata | 125 | stale, post-migration parent changes |

**Metadata is the authority. `CHILD_OF` is a cross-check.** Three reasons:

1. **It is more complete.** `CHILD_OF` never recorded 700 relationships that
   current metadata declares, dominated by `A.IMG -> D.IMG`, an analysis-to-data
   hop.
2. **It is more conservative.** 125 gap `CHILD_OF` edges are no longer declared
   by the child's metadata, and across the whole `CHILD_OF` set 881 edges are
   undeclared, over 291 distinct children of which 240 declare no parent at all.
   Promotion would resurrect parent references a curator has since changed.
   A worked example: `DNA-190111SES-7` now declares `Parent: TIS-190110SES-1`,
   while `CHILD_OF` still points at six DNA siblings.
3. **It is idempotent against future ingests.** Deriving from metadata makes
   stage 0 produce exactly what a *fixed* pipeline would produce, so a later
   re-upload converges rather than diverging.

### The `UID_RE` production regression, and why stage 0 must not use the live regex

This is the one place where "reuse the server's logic" is wrong, and it was
found only because two probes disagreed on the antibody population.

The production container's UID validator differs from the fixed one in the
development line:

```
production      ^([AD]\.)?[A-Z]{3,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?$
v4-stable-wt    \A([A-Z]\.)?[A-Z]{2,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?\Z
```

`[A-Z]{3,}` requires a sample type code of three or more letters. Exactly one
sample type in the database is shorter: **`AB`**, the antibody type. So
`UID_RE.match("AB-190703FOR-3")` returns `False` on production, every antibody
parent reference is silently discarded before any edge is built, and no
`DERIVED_FROM` edge to an `AB` sample has ever been created. Confirmed: 874
distinct `AB` parents exist as nodes, with **0** incoming `DERIVED_FROM`.

Measured impact across all parent fields:

| Field | Valid on prod | Valid only with the fix | Invalid under both |
|---|---|---|---|
| `Parent` | 703,984 | 5,755 | 1,117 |
| `AntibodyParent` | 10,186 | 1,748 | 1,230 |
| `Treatment2Parent` | 2,102 | 444 | 4 |
| `Treatment1Parent` | 3,925 | 183 | 0 |
| others | 66,715 | 1 | 41 |
| **total** | **786,912** | **8,131** | **2,392** |

Every one of the 8,131 is `AB`-prefixed. They resolve to **8,120 additional
stage 0 edges**, which is why the population is 90,534 and not 82,414.

Three consequences, all binding:

1. **Stage 0 uses `collect_parent_tokens` from the server (key matching and
   semicolon splitting) but applies the CORRECTED `UID_RE`.** The extractor must
   emit each token's raw text plus both verdicts so the delta is visible in
   `report.md` rather than buried.
2. **This is a live product defect, not just a migration artifact.** Until
   production carries the fix, every new upload containing an `AntibodyParent`
   regenerates the gap. File it and deploy the fix; the code already exists on
   `dev-v4-merge`.
3. **The `AB` edges are materially darker than the rest.** Of the 8,120, only
   4,020 (49.5%) get an assay from the intersection rule, against 91.3% overall.
   They will be a disproportionate share of stages A-F's workload.

`CHILD_OF` remains valuable as corroboration. Of the 89,959 non-self-loop gap
edges, **89,834 (99.9%)** are still named by the child's current metadata by UID.
That agreement is what makes stage 0 safe to run behind a light gate.

**Corrected 2026-08-13, measured on the live extract.** The figures below were first computed with
production's broken `UID_RE`, which discards the `AB` references that in fact declare many of these
edges. Filtering the declared set through `UID_RE_PROD` reproduces the old 8,842; with the corrected
regex the real count is **881**, over 291 distinct children, 240 of which declare no parent at all.
A reader working from the superseded figure would read a correct reconciliation as a tenfold failure.

The undeclared `CHILD_OF` edges (125 within the gap, 881 across the whole
`CHILD_OF` set, plus roughly 5,000 from children declaring no parent) go to
`stage0/reconciliation.csv` as a curation report. Nothing acts on them.

### What gets created

Input: `extract/parents.parquet` (see Access architecture), one row per
`(child_uuid, parent_token)` produced by the real server-side
`collect_parent_tokens`.

```
keep tokens matching the CORRECTED UID_RE      -> 793,554 refs
  (of which prod's regex would reject 8,131, all AB-*)
resolve each to an existing Sample node        -> 793,548 refs  (6 dropped, reported)
drop refs that already have a DERIVED_FROM     ->  90,534 to create
drop self-loops (child == parent)              -> reported, expected 1
```

Every dropped ref is counted by reason in `report.md`. Nothing is dropped
silently.

### Edge property contract

Stage 0 writes exactly the fields `DerivedFromRelRow` declares
(`batch_upload/models.py:457`, `extra="forbid"`), computed by the same rules
`_build_derived_from_payloads` uses, so a stage 0 edge is indistinguishable from
a pipeline-produced one:

| Field | Rule |
|---|---|
| `child_id`, `parent_id` | `samples.id` for each uuid |
| `child_uuid`, `parent_uuid` | as declared |
| `protocol_id` | `_SOP_URL_RE` against the child's `json_metadata["Protocol"]` |
| `protocol_title` | `sops.title` for that id |
| `assay_id` | from `shared = child_assays & parent_assays` |
| `internal_assay_id`, `internal_assay_title` | `assays_internal_assays` junction |

### Protocol resolution: the spec was wrong, and the house rule is elsewhere

**Found 2026-08-13 by the whole-branch review, running the dry run against the live extract. This
is a defect in this spec, not in the implementation, and it is unresolved.**

An earlier draft of this section said "Protocol coverage is complete on the population measured:
all 17,538 children carry a `Protocol` key." Carrying the *key* is not carrying a *resolvable id*,
and conflating the two hid the following:

```
existing DERIVED_FROM edges carrying a protocol_id      561,389 of 704,059  (79.7%)
of a 200,000 sample, resolved by sops.title == Protocol 198,209            (99.1%)
of the same, resolved by the /sops/<id> URL this spec specifies   1,779     ( 0.9%)

stage 0 children whose Protocol is a /sops/<id> URL           1
stage 0 children whose Protocol exactly matches a sops.title  14,251
stage 0 children with no Protocol value                        3,233
stage 0 children with a Protocol that resolves neither way       133

sops.title uniqueness                                        553 / 553
```

So the rule this spec mandates would set `protocol_id` on **1 edge out of 90,534**, while 79.7% of
the graph's existing edges carry one, resolvable for 94% of the planned population by a rule the
database demonstrably uses. Production `Protocol` values are overwhelmingly SOP titles
(`P.ABC-190101-V1_BL2-Monocytes-Isolation-Protocol-v1.docx`), not `/sops/<id>` URLs.

The implementation is faithful: `_build_derived_from_payloads` really does use `_SOP_URL_RE`. But
that function is normally fed an upload sheet carrying `sop_id` explicitly, and the URL regex is
only its fallback. A backfill has no sheet, so the fallback is all that remains, and it is nearly
always absent.

**Why this must be decided before the write, not after.** Stage 0 is idempotent by design: once
these pairs exist, `plan_edges` drops them under `already_has_derived_from`, so re-running with a
corrected rule creates and updates nothing. Recovery would mean hand-building a payload from the
archived `plan.parquet` and pushing it through `stage0_apply.apply_manifest`, relying on `MERGE`'s
unconditional `SET` to update in place. That path works and is tested, but it is outside the built
pipeline. This is close to a one-way door.

### RESOLVED by provenance: the house rule already exists, and it is not the URL regex

**Investigated 2026-08-14 at the operator's direction, before choosing.** The question was how the
561,389 existing edges actually got their `protocol_id`. Neither resolution rule in the current
server explains it:

- The **legacy** path (`seek/dbtable_sample.py::getConnectingRelationships`) joins
  `sops.id = SUBSTRING_INDEX(REPLACE(JSON_EXTRACT(json_metadata,'$.Protocol'),'"',''),'/',-1)`.
  On a title-form Protocol that is `sops.id = 'Behar_Flow'`, which MySQL coerces to 0 and matches
  nothing.
- The **modern** path's `_SOP_URL_RE` is `/sops/(\d+)`, which title-form values do not match.

The real source is the **upload sheet's explicit `sop_id` column**, which
`_build_derived_from_payloads` prefers over the regex (`provided_sop_by_uid`, `neo4j_sync.py:908`).
The prior migration's payloads carry it, beside a title-form Protocol:

```
sop_id: 45   Protocol: P.ABC-190101-V1_Bacterial-inoculum-batch-preparation-protocol.docx
```

And that column was computed by `internal-assays-migration/phase4_sample_export.py::resolve_sop_id`,
which handles exactly three formats against a `{sops.title: sops.id}` lookup:

```
1. URL with integer id   https://fairdata.mit.edu/sops/39   -> 39
2. URL with UID          .../uid=P.DEF-190102-V1_...pdf/    -> title lookup
3. Plain UID filename    P.ABC-190101-V1_...docx            -> title lookup
```

Applying that rule verbatim to production:

```
reproduces the stored protocol_id on 200,000 of 200,000 sampled existing edges   100.0%
disagreements                                                                        0
unresolved                                                                           0

on the stage 0 population (90,534 edges):
  fmt3 plain title     85,093   fmt2 uid= URL   10   fmt1 /sops/<id>    1
  no Protocol value     5,248   unresolvable   182
  would gain a VALID protocol_id                              85,104  (94.0%)
  would resolve to a NONEXISTENT sops.id                           0
```

**This settles it.** The three-format rule is not a divergence from the house convention; it *is*
the house convention, proven by exact reproduction on 200,000 edges with zero disagreements. The
server's `_SOP_URL_RE` is only the fallback for when no sheet supplies `sop_id`, and a backfill has
no sheet — so reconstructing what the sheet would have supplied is precisely the faithful act. The
earlier framing of this as "a deliberate divergence" was wrong, and cautious in the wrong direction:
adopting the rule makes stage 0 edges indistinguishable from pipeline-produced ones, while declining
it makes 90,533 of 90,534 anomalous.

**Decision: adopt the three-format rule**, ported from `resolve_sop_id` with the same
`{sops.title: sops.id}` lookup, and validated by a test asserting it reproduces `edge_protocol_id`
on a sample of already-labelled edges. The remaining 5,430 edges (5,248 with no `Protocol` value,
182 unresolvable) keep a null `protocol_id`, which is correct rather than a gap.

Whichever is chosen, stage 0's report must state protocol coverage from the run rather than assume
it, which it now does.

Two server behaviours stage 0 must mirror rather than improve on:

- **Multiple shared assays.** When `|shared| > 1` the server picks the
  **minimum `internal_assay_id`** (`neo4j_sync.py:1064-1078`), which is
  deterministic but arbitrary. Stage 0 reproduces it. Measured 2026-08-13:
  `|shared| > 1` occurs **28 times out of 82,663** labelled edges, so 0.03% of
  assay assignments rest on the tiebreak. `report.md` carries the count and lists
  those 28 edges, so a curator can settle them by hand if they choose.
- **Assays with no junction row.** The server already falls back to
  `(assay_id, assays.title)` (`neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge)`). This resolves the
  question the previous draft left open about the 17 unmapped assays: there is an
  existing documented behaviour and stage 0 adopts it. `report.md` counts how
  many edges took the fallback.

Where `shared` is empty, the assay fields stay `NULL`, the edge is created dark,
and it flows into stages A-F like any other dark edge.

### The residues

Each of these is a reported count in `report.md`, never a silent drop:

| Residue | Count | Disposition |
|---|---|---|
| Tokens invalid under either regex (names etc.) | 2,392 | reported, curation work |
| Tokens valid only with the regex fix | 8,131 | included, and reported as a defect |
| Declared parents with no Sample node | 6 | reported |
| Self-loops | 1 | excluded, reported |
| `CHILD_OF` not declared by metadata | 881 | `reconciliation.csv` |
| Labelled edges resting on the min-id tiebreak | 28 | listed in `report.md` |
| Edges created dark | 7,871 | flow into stages A-F |

### Gate and rollback

**Gate (operator ruling 2026-08-13): dry-run report, then the operator runs the
write.** Not the xlsx approval gate used by stage F. The justification is that
stage 0 reproduces relationships already recorded in the database rather than
making a curation judgment, and 99.9% are independently corroborated by
`CHILD_OF`. A per-row approval sheet at this volume would be rubber-stamped.

Dry run is the default. `--write` is explicit and never inferred.

`manifest.jsonl` records one line per edge actually written, with all properties.
Rollback deletes exactly the `(child_uuid, parent_uuid)` pairs in a manifest.
Stage 0 deliberately does **not** tag created edges with a marker property,
because that would make them distinguishable from pipeline-produced edges and
would leak into every downstream query; the manifest is the record instead.

Acceptance, checked before and after:

```
DERIVED_FROM total              704,059 -> expected 794,593
labelled DERIVED_FROM           277,364 -> expected 360,027
dark DERIVED_FROM               426,695 -> expected 434,566  (60.6% -> 54.7%)
D.FLOW -> D.FCS DERIVED_FROM          0 -> expected 66,529, all labelled
DERIVED_FROM into AB parents          0 -> expected 8,120, of which 4,020 labelled
CHILD_OF total                  742,534 -> unchanged
```

Plus two end-to-end checks, which are the actual point of the work: ask
`chat_nextseek` what assay connects `D.FLOW` to `D.FCS`, and ask it what
antibodies a `D.FLOW` sample derives from. Both return zero rows today.

## Stages A-F: assay membership hygiene

### Taxonomy

The tool must compute this first, because treating every dark edge as
actionable would "correct" hundreds of thousands of correctly curated records.

| Verdict | Meaning | Action |
|---|---|---|
| `CLEAN` | hop has near-zero both-sides precedent | count, do not touch |
| Mode 1 | sample belongs to no assay at all | infer and add |
| Mode 2 | child and parent in disjoint assays, hop normally propagates | add missing membership |
| Mode 3 | sample's assay contradicts strong precedent | flag only, never auto-write |

Mode 3 shares Mode 2's inference engine. Both ask what the neighborhood implies
and compare against what is recorded. Mode 2 finds an absence, Mode 3 finds a
contradiction.

### Rule table

Mode 2 never infers the assay. The child is already in it. Precedent answers one
question: does this hop, under this assay, normally register both sides?

Key:

```
project_id | child_type | parent_type | internal_assay_id
```

**Keyed on `internal_assay_id`, not `assays.title` and not `assays.id`.**
An earlier draft keyed on raw title; that was a worse version of a mapping that
already exists. Measured 2026-08-13:

```
dmac.internal_assays          137 rows / 137 distinct titles   (canonical)
seek_production.assays        458 rows / 291 distinct titles   (raw)
dmac.assays_internal_assays   441 rows: 441 assay_ids -> 137 internal_ids
```

Three reasons the junction wins over string matching:

1. **`assays.id` is too fine.** The same logical assay is instantiated once per
   study, so "Tissue Collection - Metadata" exists as 14 records across 14
   studies, and an id-keyed rule shatters evidence into unjudgeable fragments.
2. **`assays.title` is the wrong vocabulary.** Raw titles carry suffix
   conventions (`- Metadata`, `- Data Linked`) on top of the `X` / `X Analysis`
   split, and collapsing them by string heuristic re-derives, badly, a mapping
   curators already approved.
3. **It is the vocabulary the edge already speaks.** `DERIVED_FROM.internal_assay_title`
   is the canonical name, resolved through this same junction by
   `neo4j_sync._resolve_internal_assays`. Keying on raw title means findings and
   edges cannot be reconciled on assay identity, because the two sides are in
   different namespaces.

Carry `internal_assay_title` alongside the id for human-readable output.

For the 17 assays with no junction row, stage B adopts the same fallback the
server uses: treat `assay_id` as `internal_assay_id` with `assays.title` as the
title, and log the count.

The write target is still a specific `assays.id`, and it is never ambiguous: in
Mode 2 we add the parent to the assay record the child is already in.

Mined columns:

```
n_both_sides       1640    both endpoints registered under this assay
n_child_only       1057    child registered, parent not   <- the dark ones
n_parent_only         3
both_sides_rate   0.608
affected_count     1057    writes this rule would produce
verdict           PROPAGATE | NO_PROPAGATE | AMBIGUOUS | REVIEW
decided_by        deterministic | llm
action            ADD_PARENT_TO_ASSAY | ADD_CHILD_TO_ASSAY | ADD_TO_ASSAY | FLAG_ONLY
```

The assay is part of the key because one hop carries several assays.
`D.IMG -> TIS` resolves to Comet Chip (3,571), Spatial Transcriptomics Analysis
(42) and Tissue Imaging (7); each becomes its own rule judged on its own
evidence.

Project scoping is required: `D.IMG -> CEL` already resolves three ways
(Imaging / Comet Chip / Device Imaging) depending on project.

### Deterministic tiebreak: `D.*` versus `A.*`

Where a child belongs to both `X` and `X Analysis`, the sample type prefix
predicts which belongs on the edge. Every `A.*` child observed resolved to the
Analysis assay (`A.MIGR` to Migration Assay Analysis, `A.FLOW` to Flow Cytometry
Analysis, `A.IMG` to Imaging Analysis, `A.COMC` to Comet Chip Analysis); every
`D.*` child to the measurement assay. This is a named tiebreaker with its own
test, not prompt text. It removes most of the 9.8% ambiguous bucket.

### Where the LLM sits

Deterministic wherever precedent is strong and unambiguous, which the pre-stage-0
dry run said is 87.8% (child has exactly one assay). The LLM handles three narrow
slices:

- **conflicting precedent**, e.g. `BAC -> TIS` at DNA Extraction 30 /
  Bacterial Extraction 30
- **zero precedent**, a hop never observed registered anywhere
- **Mode 3 contradictions**, authoring the rationale a curator reads

Stage D is the only non-reproducible stage. It caches on input hash so an
approved decision does not change on re-run.

### Stage detail

All SQL below was verified against `seek_production` on 2026-08-12.

#### A. Extract

One self-contained package run in-container. Outputs:

`extract/edges.parquet`, from neo4j:

```cypher
MATCH (c:Sample)-[r:DERIVED_FROM]->(p:Sample)
RETURN c.id AS child_id, p.id AS parent_id,
       c.UID AS child_uuid, p.UID AS parent_uuid,
       c.type AS child_type, p.type AS parent_type,
       r.internal_assay_id AS edge_assay_id,
       r.internal_assay_title AS edge_assay_title,
       r.protocol_id AS edge_protocol_id
```

`extract/parents.parquet`, **new for stage 0**, one row per declared parent
reference, produced by calling the real server helper so the laptop never
reimplements it:

```python
from nextseek_api.batch_upload.helpers import UID_RE, collect_parent_tokens
# per sample: [(child_uuid, token, is_uid) for token in collect_parent_tokens(meta)]
```

`extract/membership.parquet` (214,489 rows):

```sql
SELECT asset_id AS sample_id, assay_id
FROM assay_assets WHERE asset_type = 'Sample'
```

`extract/assays.parquet` (458 rows). Note `investigations` has **no**
`project_id`; the link is the `investigations_projects` join table:

```sql
SELECT a.id AS assay_id, a.title, a.sample_type_id, a.study_id,
       i.id AS investigation_id, ip.project_id, p.title AS project_title
FROM assays a
JOIN studies s              ON s.id  = a.study_id
JOIN investigations i       ON i.id  = s.investigation_id
JOIN investigations_projects ip ON ip.investigation_id = i.id
JOIN projects p             ON p.id  = ip.project_id
```

`extract/samples.parquet` (163,393 rows, ~50 MB). `projects_samples` gives
sample-to-project directly (206,533 rows / 162,959 distinct samples), which is
simpler than inferring project through assays:

```sql
SELECT s.id AS sample_id, s.uuid, s.json_metadata, s.created_at,
       GROUP_CONCAT(ps.project_id) AS project_ids
FROM samples s
LEFT JOIN projects_samples ps ON ps.sample_id = s.id
GROUP BY s.id
```

`extract/childof.parquet`, for stage 0's reconciliation report only:

```cypher
MATCH (c:Sample)-[:CHILD_OF]->(p:Sample) RETURN c.uuid AS cu, p.uuid AS pu
```

#### B. Mine precedent

For every edge, for every assay either endpoint belongs to:

```python
for child, parent in edges:
    ca, pa = membership[child], membership[parent]
    for a in ca | pa:
        key = (project_of(a), child_type, parent_type, internal_assay_of(a))
        if   a in ca and a in pa: counts[key].both        += 1
        elif a in ca:             counts[key].child_only  += 1
        else:                     counts[key].parent_only += 1
```

The metric that matters for Mode 2 is **propagation rate**, not a symmetric
share rate:

```
propagation_rate = both / (both + child_only)
```

read as "when the child is in this assay, how often is the parent too". The
reverse direction gets its own `both / (both + parent_only)` for
`ADD_CHILD_TO_ASSAY`.

A global cross-project rollup is emitted alongside, as fallback for projects
with too few observations to judge on their own.

**Open and consequential:** observed rates are moderate, not bimodal.
`D.TITR -> TIS` under Titer Assay is both=1,640 / child_only=1,057, a rate of
0.608. That would not clear a naive 0.80 threshold. Threshold selection is
therefore an output of the stage B distribution plus the backtest, not a number
picked in advance. If the distribution has no clean separation, that is itself a
finding and the deterministic band shrinks in favour of review.

#### C. Classify

Per edge, first match wins:

```
edge already carries an assay          -> CLEAN (labeled)
child_assays and parent_assays empty   -> MODE_1_BOTH_DARK
child_assays empty                     -> MODE_1_CHILD
parent_assays empty                    -> MODE_1_PARENT
sets disjoint                          -> per child assay a, look up rule:
    propagation_rate >= HIGH           -> MODE_2_PROPAGATE
    propagation_rate <= LOW            -> CLEAN (hop legitimately does not propagate)
    otherwise                          -> MODE_2_AMBIGUOUS  (to D)
child assay contradicts a dominant
  precedent with near-zero support     -> MODE_3_FLAG
```

The `CLEAN` branch on low propagation rate is the guard against the failure
walked into during design: without it every dark edge reads as actionable.

#### D. Adjudicate

Order: deterministic thresholds, then the `D.*` / `A.*` tiebreak, then LLM for
what remains.

LLM input contract, one call per ambiguous group rather than per edge:

- child and parent `json_metadata`, restricted to the discriminating keys
  (`Protocol`, `Name`, `Treatment*`, `Notes`, `Type`, `SampleCreationDate`)
- candidate assay titles with their precedent counts
- the project's assay catalog

Returns `{assay_title, confidence, rationale}`. Cached on
`hash(inputs + prompt_version)` so an approved decision cannot drift on re-run.

#### E. Emit

`ASSAY_HYGIENE-update.xlsx`, one row per rule:

```
project | child_type | parent_type | assay_title | verdict | action
n_both | n_child_only | n_parent_only | propagation_rate | affected_count
decided_by | rationale | APPROVE | NOTES
```

Rule-level, one row per `(project, hop, assay, verdict)` with evidence and
affected count, plus a curator-owned `APPROVE` column. Hundreds of reviewable
rows standing in for hundreds of thousands of writes, with `expansion.parquet`
underneath for spot checks. A row-level sheet at this volume would be
rubber-stamped, not reviewed.

`APPROVE` and `NOTES` are curator-owned and preserved across regeneration. Per
plugin hard rule 2, regeneration copies before editing and never clobbers
decisions already made.

`precedent.csv` is independently useful: it is the sample type to assay to
sample type map, mined rather than hand-authored, and it answers "what assay
normally connects D.IMG to TIS in this project" as a lookup.

#### F. Apply

```
read approved rules -> join expansion -> group additions by SAMPLE
for each sample:
    read the sample's CURRENT complete assay set
    union our additions onto it
    PATCH the whole set                    (never a delta, never a partial list)
    read back and verify
    append manifest line
```

See Write safety below for why the axis is per-sample and why a partial list is
destructive.

## Access architecture

MySQL is not reachable from the laptop and no new port may be opened (only
22/80/443 reach the box, and SELinux confines nginx to `http_port_t`).

### What runs where

The split is deliberate and follows one rule: **server logic executes on the
server, judgment executes where it can be tested.**

- **In-container (stage A, read-only):** the extractor, which imports the real
  `collect_parent_tokens` and emits every token it yields. Key matching and
  semicolon splitting are never reimplemented on the laptop, so drift from the
  server's matcher is impossible by construction. This matters because a drifted
  reimplementation would silently create wrong edges, which is the exact class of
  defect this project exists to clean up.

  **One deliberate exception: `UID_RE`.** The extractor emits each token's raw
  text plus both the production verdict and the corrected verdict, and the
  laptop applies the corrected one. Reusing production's regex here would
  reproduce the very bug being fixed and would drop all 8,131 antibody
  references. The exception is narrow, explicit, and reported in `report.md`
  rather than silent, and it is the only place the laptop overrides the server.
  Note that this exception was found by two probes disagreeing, not by reading
  the code: the local checkouts all carry the fixed regex, so reading any of them
  would have confirmed the wrong answer. **Check behaviour against the running
  container, not against a local checkout.**
- **On the laptop (stages 0-plan, B-E):** all judgment. Diffing declared
  references against the graph, computing edge properties, mining precedent,
  classifying, adjudicating, emitting. Covered by the repo's pytest suite.
- **In-container (stage 0 apply):** a parameterised driver over
  `bulk_merge_relationships`, fed an explicit reviewed manifest. It contains no
  logic, only a MERGE.
- **Over HTTPS (stage F apply):** membership writes to the API, not to the box.

Nothing is installed on the box. No Claude, no `curation_skill` checkout. The
extractor is a package copied to `/tmp/scripts` and driven by a short script
piped into `manage.py shell`:

```bash
scp -r ./scripts/assay_hygiene fairdata:/tmp/
ssh fairdata 'docker cp /tmp/assay_hygiene nextseek:/tmp/scripts/assay_hygiene'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < driver.py
ssh fairdata 'docker cp nextseek:/tmp/assay-hygiene-extract .'
scp -r fairdata:/tmp/assay-hygiene-extract ./assay-hygiene/extract
```

The driver does `sys.path.insert(0, "/tmp/scripts")` then
`from assay_hygiene import extract; extract.main()`. Piping `extract.py` itself
fails: it uses a relative import and executes without package context. Nesting
the invocation inside `ssh ... bash -lc "python -c \"...\""` also fails, because
ssh joins its args and the remote shell re-parses them. Both failure modes were
identified before first run and are why the driver script exists.

Running under `manage.py shell` is deliberate: it inherits the configured
`seek` connection and `NEO4J_DATABASE` settings, so no credential is ever read,
passed, or stored by these scripts.

That choice proved load-bearing on 2026-08-13, when two credential facts
surfaced that break hand-rolled connections while leaving the settings path
working. Anyone verifying by hand needs both:

- **Neo4j's password was rotated.** `docker-compose.yml`'s
  `NEO4J_AUTH: "neo4j/demopassword"` is stale; the live value is
  `NEO4J_PASSWORD` in `.env`. `cypher-shell -p demopassword` now fails with an
  access-denied error while the driver keeps working.
- **MySQL `root@localhost` and `root@%` have different passwords.** Socket
  connections from inside `seek-mysql` fail; `-h127.0.0.1` forces TCP and
  succeeds. This is why `docker exec seek-mysql mysqldump -uroot` alone returns
  `Access denied` and the same command with `-h127.0.0.1` does not.

Also note the correct Django alias is `seek` (`seek_production`). The `default`
alias is `dmac`, whose `assay_assets` table exists but is EMPTY, so querying it
yields a confident, entirely wrong answer. This cost real time on 2026-08-13: it
produced a bogus "100% of edges have neither endpoint in any assay" result for
both a test set and its control before being caught. **If a control set and a
test set return identical results, suspect the connection, not the data.**

The container has everything needed, verified 2026-08-12:

```
neo4j driver 6.1.0
NEO4J_DATABASE = {'URI': 'neo4j://neo4j', 'AUTH': ('neo4j', ...)}
pandas 3.0.2, pyarrow 23.0.1
connections['seek'] -> seek_production   (214,489 assay_assets rows)
connections['default'] -> dmac           (assay_assets EMPTY, do not use)
```

`ssh -L` also works without a firewall change but is not the build target. It is
fragile mid-transfer and buys nothing over running in-container.

### Transfer budget

| Data | Rows | Size |
|---|---|---|
| edges | 704,059 | ~10 MB gz |
| parents | 797,435 tokens | ~8 MB gz |
| childof | 742,534 | ~9 MB gz |
| membership | 214,489 | ~1 MB gz |
| samples incl. `json_metadata` | 163,393 | 260 MB raw, ~50 MB parquet+zstd |
| assay catalog, study, investigation, project | thousands | tiny |

`samples.json_metadata` **is** extracted wholesale. Measured 2026-08-12: 260.0 MB
total, 1,669 B average, 25,928 B max. That is one transfer, and on-demand lookup
would mean hundreds of thousands of round trips against production.

It is also load-bearing rather than optional. Sample type alone cannot decide
whether an assay is correct. The discriminating fields live in the metadata, and
a 3,000-sample probe found 479 distinct keys with the relevant ones densely
populated: `Protocol` (2,998/3,000), `Parent` (2,997), `Name` (2,600),
`Treatment` (1,976), `TreatmentType` (1,995), `TreatmentDose` (1,976),
`Notes` (2,866). Those are exactly what separates DNA Extraction from Bacterial
Extraction on a `BAC -> TIS` hop.

Stored as one parquet with `json_metadata` kept as a raw string column and
parsed locally per stage, rather than exploded into 479 sparse columns.

## Validation

### Stage 0

Stage 0 needs no statistical validation because it makes no inference. Its
correctness argument is agreement between two independent records of the same
fact: 99.9% of the edges it creates are attested by both the child's current
metadata and a legacy `CHILD_OF` edge built years earlier by different code.

What it does need is the before/after acceptance table above, run and recorded,
plus a mechanical dry run on the dev box before production.

### Stages A-F

Ground truth already exists: the edges where both sides are registered
(216,114 pre-stage-0, expected to grow by 82,663).

Backtest by hiding the parent's membership on a held-out slice, running
inference cold, and measuring recovery of the assay a curator actually assigned.
This yields precision per hop and per confidence band. The PROPAGATE threshold
is set from that curve.

Thresholds are an **output** of this backtest, not a number chosen in advance.
`D.TITR -> TIS` under Titer Assay has a propagation rate of 0.608, which clears
no threshold anyone would pick by intuition.

**Acceptance bar before any production write:** the deterministic band clears
**95% precision** on held-out data, and the measured number is reported rather
than asserted. 95% is the default and the operator may raise or lower it, but
the run refuses to write when the bar is unmet unless explicitly overridden.

**This is a hard stop.** The precision curve goes to the operator before stage F
proceeds. If no threshold clears 95%, that is a finding, not a reason to lower
the bar: the deterministic band shrinks in favour of human review, and the tool
becomes far more curator-driven than designed.

## Write safety

The two write paths have nothing in common and must not be reasoned about
together.

### Stage 0: graph-only and additive

- Writes `DERIVED_FROM` relationships to Neo4j via `bulk_merge_relationships`.
- Writes nothing to MySQL. Reads `samples`, `sops`, `assay_assets`, `assays`,
  `assays_internal_assays` only.
- `MERGE` is idempotent. Re-running creates nothing new and rewrites the same
  properties.
- Cannot delete. There is no removal path in the code it calls.
- Rollback is a delete over the manifest's exact `(child_uuid, parent_uuid)` pairs.
- Dry run is the default; `--write` is explicit.
- Start with one hop (`MUS -> BAC`, 2,274 edges) rather than the flow-cytometry
  bulk, verify in the UI and in `chat_nextseek`, then widen.

### Stages A-F: per-sample, and omission deletes

An earlier draft assumed writes go through the assays API, one assay at a time
with a full member list. **That is the wrong axis.** The proven production writer
is `nextseek_api/batch_upload/update.py:117 smart_merge_assay_assets`, with the
bulk path at `:429-447`. It is keyed per SAMPLE, one `asset_id` with one complete
assay list, and it does:

```python
to_add    = new_assays - old_assays
to_remove = old_assays - new_assays     # <-- the hazard
```

then bulk-DELETEs and INSERTs against `assay_assets` in direct SQL. Exercised in
production across ~200k rows via `update_existing: true` payloads (verified in
`batch_payload_project_10.json.zip`: 2,843 of 2,844 rows carry `assay_ids`).

Two consequences, both binding:

1. **A sample's assay list must always be COMPLETE.** Sending a partial list
   deletes every membership omitted from it. Stage F must union our additions
   onto the sample's existing assays and send the whole set, never a delta. A
   test must assert the guard refuses to send a partial list.
2. **Removal is already proven; addition is not.** Every id in those production
   payloads was round-tripped out of `assay_assets`, so `to_remove` did the work
   and `to_add` was plausibly always empty. Addition at scale is the unverified
   half, and it is the half stages A-F depend on.

Additional constraints on stages A-F:

- Rule-level approval gates everything. An unapproved rule cannot expand.
- Start with the smallest project, verify in the UI, then widen.
- Manifest per run recording every membership added, so removal targets exactly
  what was created.
- Read by SQL and neo4j. Extraction via API would be slow and would hit the
  documented `page[size]` bug.

## Open risks

1. **Addition at scale is unverified for stages A-F; rollback is not.** An earlier
   draft had this backwards. `smart_merge_assay_assets` demonstrably removes
   memberships at scale in production, so rollback is the *solved* half. What is
   unproven is that a genuine `to_add` lands, because the production payloads only
   ever round-tripped ids that were already present. The dev-box probe must
   therefore test an ADDITION and its reversal, not a deletion. **This does not
   block stage 0**, which never touches `assay_assets`.
2. **Every stages A-F statistic in this document predates stage 0.** The 87.8%
   unambiguous figure, the 97.2% disjoint split, the 216,114 backtest population
   and the precedent distribution were all measured against a graph missing its
   largest single hop. Re-extract and re-measure after stage 0 before selecting
   any threshold.
3. **The proxy masks SEEK 422s as generic 502s.** Stage F failures will be
   uninformative unless the client inspects the upstream body. Precedent for
   working around this exists in `scripts/sampletype_attr.py`.
4. **Write volume in stage F.** `affected_count` summed across PROPAGATE rules
   lands in the hundreds of thousands on sampled evidence. Validation and
   rollback are load-bearing, not optional.
5. **Genuinely unregistered batches exist** and Mode 1 will not always find a
   precedent for them. Several ENG batches are 100% unregistered
   (`190504ENG` 464/464, `190506ENG` 394/394, `190505ENG` 9/9), so both endpoints
   are dark and the hop lookup returns nothing. These fall to the LLM slice or
   to the PI.
6. **The `UID_RE` regression will regenerate the gap until production is
   updated.** Production's `[A-Z]{3,}` rejects the `AB` sample type, so every
   future upload carrying an `AntibodyParent` silently drops it and creates no
   edge. Stage 0 closes the historical 8,120; it does not stop new ones
   appearing. The fix exists on `dev-v4-merge` and needs to ship. Until it does,
   stage 0 is a treatment rather than a cure for this slice, and re-running it
   periodically is the workaround.
7. **`./startup.sh dump-db` cannot be used to take a backup on this host.**
   `dump_mysql.sh:27` passes `--column-statistics=0`, an Oracle MySQL 8 option
   the host's MariaDB 10.11.18 client rejects, and lines 47/50 redirect with
   `| gzip > "$SEED_DIR/..."`, so the shell truncates the destination before
   `mysqldump` runs. A failed run took `startup/seed/dmac.sql.gz` from 3.7 MB to
   20 bytes. Filed as issue #92. Take backups by container-side `mysqldump` plus
   `dump_neo4j.py` instead, and copy `startup/seed/*.gz` first.

## Backup state

A restore-tested production backup predates any write in this spec:
`~/backups/pre-hygiene-2026-08-13/fresh/` on `fairdata`, holding
`seek_production.sql.gz` (95 MB), `dmac.sql.gz` (1.4 MB) and `neo4j.cypher.gz`
(23 MB). Restore into a throwaway `mysql:8.0` container took 606s and every row
count matched live exactly (samples 163,393; assays 458; assay_assets 214,489;
studies 48; investigations 16; projects 12; sops 553; sample_types 115; tables
216/216).

Two gaps: no current filestore backup (only a June copy), and `neo4j.cypher.gz`
was not replay-tested, though its statement counts match live node and
relationship counts exactly. Since stage 0 is a Neo4j write, **replay-testing the
Neo4j dump is a prerequisite for stage 0's production run.**

The June files in that folder are NOT backups of the current stack. They came
from `fairdata.mit.edu`, MariaDB 10.5.22, the legacy pre-container server, eleven
minutes before the containerised stack was created. They are migration source
material. Do not restore any `fresh/*.sql.gz` into a live server: they were taken
with `--databases` so they carry `CREATE DATABASE` and `USE`.

## Evidence appendix

Verified against production 2026-08-12 and 2026-08-13.

Samples in no assay: 5,880 of 163,393 (3.6%). This is *not* the size of the
problem; the dark-edge count is, and the two differ by two orders of magnitude
because a single unregistered sample darkens every incident edge.

Variant parent fields carrying values, whole database:

```
AntibodyParent        12,367
Treatment1Parent       4,108
CompensationFCSParent  3,934
Treatment2Parent       2,512
Treatment3Parent         134
Treatment4Parent          60
AntibodyPanelParent       30
BacterialParent            3
```

Stage 0 population by hop, top 14 of 90,534:

```
66,529  D.FLOW -> D.FCS
10,035  D.FLOW -> ABP
 2,274  MUS -> BAC
 1,845  D.IMG -> AB
 1,653  ABP -> AB
 1,592  MUS -> CHM
 1,542  D.ADNKA -> AB
   652  D.ADNP -> AB
   514  A.IMG -> D.IMG
   476  D.ADMP -> AB
   460  D.ADCD -> AB
   457  MUS -> CEL
   451  PAV -> BAC
   378  D.BSRA -> AB
```

The `-> AB` hops total 8,120 and exist only because stage 0 overrides
production's `UID_RE`. Under production's regex the entire column is absent.

Gap endpoint quality: 0 null uuid, 0 null id, 17,538 distinct children, 2,576
distinct parents, 1 self-loop. Direction is unambiguous: where both `CHILD_OF`
and `DERIVED_FROM` exist, 652,574 agree and 0 disagree.

Worked example, the NDMA cohort. Full lineage present in the graph, zero assay
annotation, only the root chemical registered anywhere:

```
CHM-190501ENG-1  "NDMA-1"                    [assay 12: Chemical Challenge]
  ^-- MUS-190505ENG-1        protocol: -     assay: -
  ^-- MUS-190505ENG-2        protocol: -     assay: -
        ^-- TIS-190505ENG-4  protocol: Med-Term-Collection-at-Necropsy  assay: -
        ^-- TIS-190505ENG-5  protocol: Med-Term-Collection-at-Necropsy  assay: -
              ^-- DNA-190504ENG-214          assay: -
                    ^-- D.SEQ-190504ENG-214  assay: -
```

The TIS edges carry a real protocol title pulled from SEEK's `sops` table, which
proves the sync writes whatever it finds. It found no assay because there was
none to find. This cohort sits in the 1.1% "neither endpoint registered" tail
and is not representative of the bulk problem.

**Caution on generalising from one cohort.** Three conclusions in this project's
history were reversed on measurement, and all three shared a cause: generalising
from the first cohort examined, which turned out to sit in a small tail.

1. The 97.2% disjoint edges were called correctly-curated data to leave alone.
   Wrong: the cross-type precedent (4,272 of 4,990) proves input-registration is
   the house convention.
2. `samples.json_metadata` was called multi-GB and unfetchable. Wrong: 260.0 MB
   total, 1,669 B average.
3. Task 8 was framed as proving rollback. Wrong surface: removal is the solved
   half, addition is the unproven one.

Sample before concluding.

A fourth, from writing this rewrite: the missing `-> AB` edges were nearly
written off as "not declared by metadata" on the strength of an aggregate probe,
which would have silently excluded 8,120 antibody relationships that the operator
had explicitly ruled in. What caught it was two probes disagreeing and the
disagreement being chased to a single pair with raw `repr` output instead of
being averaged away. Two rules follow:

- **When two measurements of the same population disagree, one of them is a bug.
  Find out which before writing either number down.**
- **Verify behaviour against the running container.** Every local checkout
  carries the fixed `UID_RE`; reading any of them would have confirmed the wrong
  answer with complete confidence. Production runs `main-stable-260811 @ 83b8b99`,
  which is not checked out anywhere on the laptop.
