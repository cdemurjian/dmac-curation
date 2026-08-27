# Assay hygiene as a curation mode — design

**Status:** design, approved in outline 2026-08-27. Not implemented.
**Supersedes:** nothing. **Absorbs:** `commands/curate-assay-vocabulary.md`.

## Why this exists

RUN1 completed on 2026-08-25: a full assay-hygiene pass over the production
extract producing 26,193 human-ruled registrations, of which 25,769 survived a
project-consistency audit and are being written now. It took roughly six
sessions.

Re-running it in three or six months currently scores **2 out of 5** on
"guided, re-runnable workflow". The compute is trivial — 47 seconds regenerates
every proposal, and the pipeline is verified deterministic across a pandas major
version. What does not survive is everything that made those proposals
*actionable*: 261 cohort rulings, 175 pair rulings, 1,012 agent verdicts and 16
calibration rounds, all keyed to RUN1's cohort strings. `REGISTRATION-ROWS.csv`
is produced by no committed code.

This design makes run 2 a guided workflow rather than a reconstruction, and
makes RUN1's judgement carry forward.

## What this is not

Not a rewrite of the detection pipeline. `scripts/assay_hygiene/` stays as it
is; its 26 modules are sound, deterministic and well tested at the unit level.
This adds the *workflow* layer that has only ever existed in session
transcripts.

## 1. Mode, not plugin

Assay hygiene becomes a fourth mode alongside `pipeline`, `schema` and
`report`, with commands named `curate-assay-*` to match the flat family already
in `commands/`.

It is **house-scoped, not project-scoped**. One extract, all projects, no PI.
`commands/curate-assay-vocabulary.md` already establishes this ("unlike the
pipeline-mode commands this stage is not project-scoped"), and
`scripts/_lockfile.py` already anticipates modes that never read a project
lockfile.

That existing command is absorbed and fixed on the way in. It currently carries
both defects this design exists to remove: it instructs `run_evidence` with **no
`out_dir`** — the clobbering hazard of §6 — and quotes figures from the
2026-08-14 extract while telling the reader to re-measure them.

## 2. The run model

**Runs are numbered and immutable.** `/curate-assay-init` creates `assets/RUN<n>/`
and applies `chmod a-w` to the evidence tiers **in code**. Today four separate
files assert this protection and nothing performs it; resolved through the
symlink tree, 27 of 33 artifacts are clobberable by a default-path run.

**State is a lockfile**, following the `.dmac-curation.json` pattern:

```json
{ "run": 2, "extract_sha": "...", "extract_pulled": "2026-09-14",
  "schema_pinned": "...", "step": "review",
  "rulings_ingested": {"vocabulary": 736, "pairs": 312, "mode1": 44},
  "carried_from_run": 1, "carried_pairs": 479,
  "write": {"chunks_done": 0, "rollback_id": null, "backup_verified": false} }
```

**One run at a time.** The lockfile carries a pid and refuses a second `init`
while one is open. Beyond removing "which run am I in" confusion, two concurrent
write phases could silently overwrite each other's rows — see §5.

## 3. The ruling store

**Rulings live outside runs and outlive them**, at `assets/rulings/`. This is
the structural change that makes reuse possible: today rulings live *inside* the
run that produced them, which is why they do not transfer.

**Keyed on the pair, with provenance alongside.**

```
pairs.tsv       (sample_type, internal_assay_id, action) -> verdict, date, actor
provenance/     the cohort string as ruled, extract id, reviewer notes
```

The pair is the unit the reachability gate actually decides on — the operator's
own 2026-08-25 correction made this point, and it is why ~150 questions settled
97% of a 99,449-row population. The key survives lab changes, assay-title edits
and parent-type drift, all of which break a cohort string.

Provenance is kept because a pair ruling is coarser than the cohort it was made
against. Without it, "the operator approved this pair" cannot be distinguished
from "the operator approved a narrow slice and we widened it".

**Everything under `assets/` stays gitignored.** The repository is PUBLIC and
this session alone found 35 real sample identifiers, 18 protocol identifiers and
a whole class of bare `<YYMMDD><LAB>` batch stamps in tracked files. Nothing
identifying goes to git.

**Backup is automatic on ingest, not a command you remember.** The one weakness
of keeping rulings out of git is that protection depends on discipline;
`/curate-assay-review` therefore writes a dated tarball outside the working tree
every time it ingests judgement. `/curate-assay-backup` exists for manual use.
Note that `git clean -xdf` currently lists `assets/` and `.claude/` for removal.

## 4. Commands

| command | does | writes |
|---|---|---|
| `curate-assay-init` | pull extract, verify schema projection, create run, chmod tiers, open lockfile | run dir |
| `curate-assay-vocabulary` | unresolved terms → operator sheet → ingest verdicts | ruling store |
| `curate-assay-detect` | `run_evidence` + `run_detect` into the run's own out_dir; emit surfaces | run artifacts |
| `curate-assay-review` | serve Mode 1 / Mode 2 / pair sheets, ingest rulings, auto-backup | ruling store |
| `curate-assay-resolve` | internal → SEEK targets, **project gate**, emit sheet + manifest | run artifacts |
| `curate-assay-write` | preflight, chunk, submit, reconcile against the database | **production** |
| `curate-assay-status` | read lockfile, report position | nothing |
| `curate-assay-backup` | dated tarball of the ruling store | backup dir |

### The carry-forward split

On `detect`, every cohort is sorted three ways against the ruling store:

- **already ruled** — the pair matches and the new cohort is no wider than the
  one ruled against. Carried, with provenance available.
- **ruled in a narrower context** — the pair matches but the new cohort covers
  rows the original did not. **Surfaced for re-confirmation, never auto-applied.**
- **never seen** — goes to the operator.

The middle bucket is RUN1's trap made visible. 2,830 rows shared a cohort key
with an approved cohort but sat below the precedent floor the operator's sheet
was built at; he never saw them. A naive carry-forward registers them silently.

## 5. `curate-assay-write`

The only command that touches production. It refuses:

| refusal | why |
|---|---|
| any row whose Current pair parses as two ints | the sole combination reaching `deleteOneRecord` (`seek/dbtable_assay_assets.py:171`) |
| any row with an unparseable New pair | silently drops the registration and reports success |
| any UID blank, non-string or whitespace-only | `getSampleID` returns `None`; `None > 0` raises; **500s mid-run leaving a committed prefix** |
| a sheet named `UPDATE` anywhere in the workbook | hijacks dispatch into the metadata-update path (`seek/dbtable_sample.py:1663` is tested first) |
| any row absent from the gate-checked manifest | project consistency unproven — see below |
| no captured rollback handle | `MAX(id)` must be recorded before the first chunk |
| backup absent **or unverified** | non-zero size *and* a `Dump completed` trailer |
| a chunk above the row cap | 20-minute gunicorn SIGKILL, and this path has no transaction |

**Project consistency is a hard gate.** SEEK assay ids are per-project. A
registration must land on the assay belonging to the *sample's own* project, not
merely one with the right title or internal id. The 2026-08-26 audit found 578
of 26,188 rows targeting another project's assay, every one produced by the
design's "neighbour's own SEEK record" rule where the lineage neighbour lived
elsewhere. 159 were repairable, 419 were not and were excluded. This is
unrecoverable once written — the sample joins a project it does not belong to.

The check cannot be made from the workbook alone; it needs each sample's project
set and each assay's project. `resolve` therefore emits a manifest gate-checked
at build time, and `write` asserts the sheet is a subset of it.

### Two principles, stated because habit was not enough

**Verify the artifact, never the exit code.** Three separate things reported
success while failing on 2026-08-27: `mysqldump` exited 0 having written 0
bytes; `DBtable.storeOneRecord` (`dmac/dbtable.py:109`) sets `status = 1` and
never updates it in either write branch, so a DB failure returns success; and a
runner sailed past an empty variable because bash evaluates `""` as 0 in
arithmetic. Every step asserts on the thing produced.

**The database is the only receipt.** Verification after each chunk is a count
query. The endpoint's response and its feedback workbook are hints — the
workbook prints `successful:` for rows that never wrote.

### Write mechanism

`UPDATE_ASSAY` sheet → `POST /seek/sampleupload/`, one row per `(sample, assay)`
edge, both Current columns blank. Chosen over the two alternatives because it is
**structurally incapable of deleting**: with the Current pair unparseable,
`id = -1` and the delete branch behind `if id>0` is unreachable. It also needs no
read-back, so no complete-list union is required.

Measured against the alternatives for the same 25,769 rows: the API route put
202,016 existing memberships at risk, batch-upload 25,912, this route **zero**.
Batch-upload additionally rewrites `samples.title` to the UID string and resets
`policies.access_type` by default.

Idempotency is application-level, not a database constraint: no UNIQUE index
exists on `(assay_id, asset_id, asset_type)`; `storeOneRecord` reads before
writing via `__verifyUniqueConstraint`. This is worth stating because it would
vanish silently if that code path changed, and nothing in the schema would catch
it.

**Chunking is mandatory** — 2,000 rows per submission. Gunicorn SIGKILLs at
1200s with no transaction, and per-chunk verification bounds a failure to one
chunk. Measured throughput is ~3.4 rows/second (the `MAX(id)+1` read-then-write
cost per row), so ~10 minutes per chunk.

**Quiet window required.** Primary keys are `MAX(id)+1` computed in Python with
no lock. A concurrent insert makes Django's explicit-pk `save()` perform
UPDATE-then-INSERT and *silently overwrite the other writer's row*, with both
callers told they succeeded. `nextseek_api`'s batch-upload path writes the same
table.

## 6. Prerequisites

Each is a live defect, fixed as part of this work rather than tracked separately.

1. **`chmod a-w` applied by code.** Asserted in four files, performed by none.
2. **`out_dir` required** on `run_evidence` / `run_detect` / `classify` /
   `validation_sample`, or a guard refusing to write through a symlink. This is
   what makes a default-path run destructive.
3. **Existence guards** for `claims.parquet` and `vocabulary.csv` in
   `gate.main` and `classify.main`, matching `compatibility.py:670-676`. The one
   documented reproduction command in `assets/RUN1/README.md` currently dies
   with a bare `FileNotFoundError`.
4. **Dependency pinning.** PEP-723 headers are lower-bound only; there is no
   lockfile. The pipeline works on pandas 3 today by luck, not design.

## 7. Testing

The suite tests units well and encodes the workflow nowhere. This adds tests
that assert the *sequence*:

- a fresh run refuses to write before rulings are ingested
- a carried ruling applied to a wider cohort is surfaced, not auto-applied
- the write preflight refuses each of the eight conditions in §5
- the project gate refuses a cross-project row (proven by injection)

Plus two fixes to existing tests:

- **`tests/conftest.py:127`** matches `_real_extract_` with a trailing
  underscore. Two tests end `..._on_the_real_extract` and eleven more use
  `skipif` without the convention, so the banner whose job is to say "this run
  measured nothing" under-reports by a third — 40 skips, 13 invisible.
- **Two landmines, both worth defusing deliberately rather than discovering.**

  `test_assay_hygiene_rulings.py:230` is a *vacuity guard*, and it is correct as
  written: it requires the reworked frame to carry both new classes AND the
  baseline to carry neither, because otherwise the four "nothing was lost" tests
  below it compare a frame with itself and assert that a change which never
  happened cost nothing. It fires only if the RUN1 baseline is regenerated in
  place — which is precisely what prerequisite §6.2 prevents. Fixing `out_dir`
  defuses it; RUN2 writing into its own run directory does not trip it.

  `test_assay_hygiene_rulings.py:332` is `xfail(strict=True)` and names 13
  cohorts the operator rejected that a primary surface still proposes. If a new
  extract simply no longer contains them, the assertion passes, strict mode
  reports XPASS, and the suite goes red for a reason unrelated to any fix. The
  marker that protects the deliverable is also a tripwire on new data, and RUN2
  must decide consciously whether that measurement still applies.

## 8. Migrating RUN1

One-time, in `init`: read RUN1's cohort rulings, derive the pair key for each,
write `pairs.tsv` with the original cohort string as provenance. Where several
cohort rulings collapse to one pair and **disagree**, the pair is written as
`CONFLICT` and surfaced to the operator rather than resolved by a rule.

Expected yield: 261 cohort rulings and 175 pair rulings over ~479 distinct
pairs. The 1,012 agent verdicts migrate the same way but stay marked as agent
judgement — they were measured at ~80% agreement with the operator and a ~5%
false-approve floor consensus did not reduce.

## 9. Open questions

- **Review surface format.** RUN1 used a mix of TSV, CSV and HTML. Unresolved
  whether `review` serves a local page or emits files.
- **Where `assets/rulings/` lives** if the working tree is ever cloned fresh.
  It is gitignored by design, so a new clone has no judgement until a backup is
  restored. The restore path is undesigned.
- **Whether `direction` should ever be non-zero.** RUN1 wrote `0` throughout
  (house neutral). Production is 60/40 between 0 and 1, and the registration
  rows carry a per-row `action` that maps plausibly onto SEEK's
  none/incoming/outgoing convention. Deferred deliberately.
