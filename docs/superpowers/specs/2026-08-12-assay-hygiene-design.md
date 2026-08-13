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
project_id | child_type | parent_type | assay_title
```

Keyed on **title, not `assay_id`**. Verified 2026-08-12: SEEK holds 458 assay
records under only 291 distinct titles, because the same logical assay is
instantiated once per study. "Tissue Collection - Metadata" exists as 14 records
across 14 studies. Keying on `assay_id` would shatter the evidence into
per-study fragments too thin to judge.

The write target is still a specific `assay_id`, and it is never ambiguous: in
Mode 2 we add the parent to the assay record the child is already in.

Titles also carry suffix conventions (`- Metadata`, `- Data Linked`) layered on
top of the `X` / `X Analysis` split. Whether to normalise these before grouping
is decided in Stage B against the data, not assumed here.

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

## Stage detail

All SQL below was verified against `seek_production` on 2026-08-12.

### A. Extract

One self-contained script run in-container. Four outputs.

`extract/edges.parquet` (704,059 rows), from neo4j:

```cypher
MATCH (c:Sample)-[r:DERIVED_FROM]->(p:Sample)
RETURN c.id AS child_id, p.id AS parent_id,
       c.UID AS child_uuid, p.UID AS parent_uuid,
       c.type AS child_type, p.type AS parent_type,
       r.internal_assay_id AS edge_assay_id,
       r.internal_assay_title AS edge_assay_title,
       r.protocol_id AS edge_protocol_id
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

### B. Mine precedent

For every edge, for every assay either endpoint belongs to:

```python
for child, parent in edges:
    ca, pa = membership[child], membership[parent]
    for a in ca | pa:
        key = (project_of(a), child_type, parent_type, title_of(a))
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
therefore an output of the Stage B distribution plus the backtest, not a number
picked in advance. If the distribution has no clean separation, that is itself a
finding and the deterministic band shrinks in favour of review.

### C. Classify

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

The `CLEAN` branch on low propagation rate is the guard against the failure I
walked into during design: without it every dark edge reads as actionable.

### D. Adjudicate

Order: deterministic thresholds, then the `D.*` / `A.*` tiebreak, then LLM for
what remains.

LLM input contract, one call per ambiguous group rather than per edge:

- child and parent `json_metadata`, restricted to the discriminating keys
  (`Protocol`, `Name`, `Treatment*`, `Notes`, `Type`, `SampleCreationDate`)
- candidate assay titles with their precedent counts
- the project's assay catalog

Returns `{assay_title, confidence, rationale}`. Cached on
`hash(inputs + prompt_version)` so an approved decision cannot drift on re-run.

### E. Emit

`ASSAY_HYGIENE-update.xlsx`, one row per rule:

```
project | child_type | parent_type | assay_title | verdict | action
n_both | n_child_only | n_parent_only | propagation_rate | affected_count
decided_by | rationale | APPROVE | NOTES
```

`APPROVE` and `NOTES` are curator-owned and preserved across regeneration.
`expansion.parquet` carries the row-level edges behind each rule for spot checks.

### F. Apply

```
read approved rules -> join expansion -> group additions by target assay_id
for each assay_id:
    GET  current membership
    PATCH with current + additions        (never a bare overwrite)
    GET  again and verify the delta
    append manifest line
```

Grouping by assay keeps the call count in the hundreds rather than the hundreds
of thousands, and the read-verify bracket is what makes the manifest
trustworthy enough to roll back against.

## Access architecture

MySQL is not reachable from the laptop and no new port may be opened (only
22/80/443 reach the box, and SELinux confines nginx to `http_port_t`).

### What runs where

Only Stage A runs on the box, and nothing is installed there. No Claude, no
`curation_skill` checkout. The extractor is a single self-contained file driven
from the laptop over ssh, exactly as every query in the design session was:

```bash
ssh fairdata 'docker cp /tmp/extract.py nextseek:/tmp/extract.py'
ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < extract.py
ssh fairdata 'docker cp nextseek:/tmp/assay-hygiene-extract .'
scp -r fairdata:/tmp/assay-hygiene-extract ./assay-hygiene/extract
```

Stages B through F run on the laptop against the pulled files. Stage F is the
only other thing that touches production, and it goes over HTTPS to the API, not
to the box.

Running under `manage.py shell` is deliberate: it inherits the configured
`seek` connection and `NEO4J_DATABASE` settings, so no credential ever has to be
read, passed, or stored by these scripts.

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
