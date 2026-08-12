# Assay Hygiene: backfill and audit assay membership across SEEK production

**Date:** 2026-08-12
**Status:** design approved, not yet implemented
**Scope:** scripts under `scripts/assay_hygiene/`. Not a plugin mode yet.

## Problem

`chat_nextseek` graph queries of the form "what assay connects sample type A to
sample type B" silently return zero results for most type pairs. The Cypher is
correct and the graph topology is correct. The assay annotation on the
`DERIVED_FROM` edge is missing.

Measured on production neo4j (2026-08-12):

```
704,059   DERIVED_FROM edges total
426,695   (60.6%)  no internal_assay_title / internal_assay_id
 84,070   (11.9%)  bare: only parent_id + child_id
341,808   (48.5%)  protocol present, assay absent
216,114   (30.7%)  full assay + protocol
```

### Root cause

`nextseek_api/batch_upload/neo4j_sync.py:934` writes an assay onto an edge only
when child and parent are **both** members of that assay:

```python
shared = child_assays & parent_assays
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

### Why the 97.2% is a defect and not a convention

The dominant pattern is a cross-stage hop where the child sits in the assay that
produced it and the parent sits in the assay that produced *it*:

```
CHILD  D.IMG-230913ENG-430   -> ['Comet Chip']
PARENT TIS-230830ENG-244     -> ['Tissue Collection']
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

## Non-goals

- Changing `neo4j_sync.py`. If membership is backfilled to precedent, the
  intersection rule starts working on its own.
- Creating or moving Study or Investigation records.
- Deleting assays.
- Touching sample lineage. Topology is correct and is not in scope.

## Taxonomy

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

## Rule table

Mode 2 never infers the assay. The child is already in it. Precedent answers one
question: does this hop, under this assay, normally register both sides?

Key:

```
project_id | child_type | parent_type | assay_id | assay_title
```

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

Deterministic wherever precedent is strong and unambiguous, which the dry run
says is 87.8% (child has exactly one assay). The LLM handles three narrow slices:

- **conflicting precedent**, e.g. `BAC -> TIS` at DNA Extraction 30 /
  Bacterial Extraction 30
- **zero precedent**, a hop never observed registered anywhere
- **Mode 3 contradictions**, authoring the rationale a curator reads

Stage D is the only non-reproducible stage. It caches on input hash so an
approved decision does not change on re-run.

## Pipeline

| Stage | Nature | Output |
|---|---|---|
| A. Extract | deterministic | `extract/edges.parquet`, `extract/membership.parquet`, `extract/assay_catalog.json` |
| B. Mine precedent | deterministic | `precedent.csv` |
| C. Classify | deterministic | `findings.csv` |
| D. Adjudicate | threshold + narrow LLM | `decisions.csv` |
| E. Emit | deterministic | `ASSAY_HYGIENE-update.xlsx`, `expansion.parquet` |
| F. Apply | guarded | `applied/<ts>-manifest.jsonl` |

Every stage caches to disk. B through E re-run locally without touching
production.

`precedent.csv` is independently useful: it is the sample type to assay to
sample type map, mined rather than hand-authored, and it answers "what assay
normally connects D.IMG to TIS in this project" as a lookup.

### Update sheet grain

Rule-level, one row per `(project, hop, assay, verdict)` with evidence and
affected count, plus a curator-owned `APPROVE` column. Hundreds of reviewable
rows standing in for hundreds of thousands of writes, with `expansion.parquet`
underneath for spot checks. A row-level sheet at this volume would be
rubber-stamped, not reviewed.

Per plugin hard rule 2, regeneration copies before editing and never clobbers
decisions already made.

### Artifact layout

```
assay-hygiene/
  extract/                     A, cached, gitignored (contains sample metadata)
  precedent.csv                B, the reusable map
  findings.csv                 C, every edge with verdict + matched rule
  decisions.csv                D, adds decided_by + rationale
  ASSAY_HYGIENE-update.xlsx    E, rule-level, has APPROVE column
  expansion.parquet            E, row-level drilldown
  applied/                     F, one manifest per apply run
```

## Access architecture

MySQL is not reachable from the laptop and no new port may be opened (only
22/80/443 reach the box, and SELinux confines nginx to `http_port_t`).

Extraction runs **inside the `nextseek` container**, which already has
everything needed, verified 2026-08-12:

```
neo4j driver 6.1.0
NEO4J_DATABASE = {'URI': 'neo4j://neo4j', 'AUTH': ('neo4j', ...)}
pandas 3.0.2, pyarrow 23.0.1
connections['seek'] -> seek_production   (214,489 assay_assets rows)
connections['default'] -> dmac           (assay_assets EMPTY, do not use)
```

One script writes parquet to `/tmp`, then `docker cp` to the host and `scp` to
the laptop. Production is touched exactly twice: extract, and apply.

`ssh -L` also works without a firewall change but is not the build target. It is
fragile mid-transfer and buys nothing over running in-container.

### Transfer budget

| Data | Rows | Size |
|---|---|---|
| edges | 704,059 | ~10 MB gz |
| membership | 214,489 | ~1 MB gz |
| assay catalog, study, investigation, project | thousands | tiny |

`samples.json_metadata` is deliberately **not** extracted wholesale. 163k JSON
blobs are needed only for the narrow LLM slice and are fetched on demand for
those samples.

## Validation

Ground truth already exists: the 216,114 edges where both sides are registered.

Backtest by hiding the parent's membership on a held-out slice, running
inference cold, and measuring recovery of the assay a curator actually assigned.
This yields precision per hop and per confidence band. The PROPAGATE threshold
is set from that curve.

**Acceptance bar before any production write:** the deterministic band clears
**95% precision** on held-out data, and the measured number is reported rather
than asserted. 95% is the default and the operator may raise or lower it, but
the run refuses to write when the bar is unmet unless explicitly overridden.

## Write safety

- Dry run is the default. `--write` is explicit and never inferred.
- Rule-level approval gates everything. An unapproved rule cannot expand.
- Start with the smallest project, verify in the UI, then widen.
- Manifest per run recording every membership added, so removal targets exactly
  what was created.
- Read by SQL and neo4j, write by API. The API is for writes only, where
  validation and auth matter. Extraction via API would be slow and would hit the
  documented `page[size]` bug.

## Open risks

1. **Rollback is unverified.** `AssayProxyViewSet` exposes `list`, `retrieve`,
   `create`, `partial_update` and no delete. Removal likely means PATCHing the
   assay with its membership list minus our additions. This must be proven on
   the dev box against a throwaway assay before any production write. If
   rollback does not work cleanly, batching must become more conservative.
2. **The proxy masks SEEK 422s as generic 502s.** Apply-stage failures will be
   uninformative unless the client inspects the upstream body. Precedent for
   working around this exists in `scripts/sampletype_attr.py`.
3. **Write volume.** `affected_count` summed across PROPAGATE rules lands in the
   hundreds of thousands on sampled evidence. Validation and rollback are
   load-bearing, not optional.
4. **Genuinely unregistered batches exist** and Mode 1 will not always find a
   precedent for them. Several ENG batches are 100% unregistered
   (`260514ENG` 464/464, `260505ENG` 394/394, `260519ENG` 9/9), so both endpoints
   are dark and the hop lookup returns nothing. These fall to the LLM slice or
   to the PI.

## Evidence appendix

Verified against production 2026-08-12. Samples in no assay: 5,880 of 163,393
(3.6%). This is *not* the size of the problem; the dark-edge count is, and the
two differ by two orders of magnitude because a single unregistered sample
darkens every incident edge.

Worked example, the NDMA cohort. Full lineage present in the graph, zero assay
annotation, only the root chemical registered anywhere:

```
CHM-230509ENG-1  "NDMA-1"                    [assay 12: Chemical Challenge]
  ^-- MUS-260519ENG-1        protocol: -     assay: -
  ^-- MUS-260519ENG-2        protocol: -     assay: -
        ^-- TIS-260519ENG-4  protocol: Med-Term-Collection-at-Necropsy  assay: -
        ^-- TIS-260519ENG-5  protocol: Med-Term-Collection-at-Necropsy  assay: -
              ^-- DNA-260514ENG-214          assay: -
                    ^-- D.SEQ-260514ENG-214  assay: -
```

The TIS edges carry a real protocol title pulled from SEEK's `sops` table, which
proves the sync writes whatever it finds. It found no assay because there was
none to find. This cohort sits in the 1.1% "neither endpoint registered" tail
and is not representative of the bulk problem.
