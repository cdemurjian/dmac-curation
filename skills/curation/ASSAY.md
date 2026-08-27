# Assay hygiene mode

House-scoped, not project-scoped: one extract, all projects, no PI. It finds
samples that should be registered against an internal assay and are not, puts
every proposal in front of a human, and writes the approved ones to production.

## The run model

Runs are numbered and immutable at `assets/RUN<n>/`, tiers `00`–`06` read-only
from creation. State is `assets/assay-run.json`; one run may be open at a time,
because two concurrent write phases can silently overwrite each other's rows.

## The ruling store

Judgement lives at `assets/rulings/`, **outside** any run, keyed on
`(sample_type, internal_assay_id, action)` with the cohort string kept
alongside as provenance.

This is the structural change that makes reuse possible. RUN1 filed verdicts
under `lab|sample_type|parent_types|assay_title|field|value`; four of those six
move with the extract, so a new run matched almost none of them and 261 rulings
became worthless without any judgement having changed.

A pair ruling is **coarser** than the cohort it was made against. Measured on
RUN1, 200 ruled rows collapse to 127 keys and 5 disagreed. Those 5 were
excluded from the store and put back to the operator, never resolved by a rule.
Lab was the discriminator in three of the five, which is the measured cost of
dropping it from the key: 3.9%.

## Commands

| command | does | writes |
|---|---|---|
| `curate-assay-init` | open a run, prove the store survives, chmod tiers | run dir |
| `curate-assay-vocabulary` | unresolved terms → operator sheet → ingest | ruling store |
| `curate-assay-detect` | evidence + detection into the run's own out_dir | run artifacts |
| `curate-assay-review` | serve surfaces, ingest rulings, auto-backup | ruling store |
| `curate-assay-resolve` | internal → SEEK targets behind the project gate | run artifacts |
| `curate-assay-write` | preflight, chunk, submit, reconcile | **production** |
| `curate-assay-status` | read the lockfile, report position | nothing |
| `curate-assay-backup` | dated, verified tarball of the store | backup dir |

## The carry-forward split

On `detect`, every cohort is sorted three ways against the store: **already
ruled** (carried), **ruled in a narrower context** (surfaced, never applied),
and **never seen** (goes to the operator).

The middle bucket is the trap. In RUN1, 2,830 rows shared a cohort key with an
approved cohort but sat below the precedent floor the operator's sheet was
built at, so he never saw them. An unknown ruled width counts as widened, not
carried — absence of evidence that a ruling covered these rows is not evidence
that it did.

## Four things that will bite

**Never run a driver on default paths.** `run_evidence` and `run_detect`
default `out_dir` to `assay-hygiene/`, which is 33 symlinks into
`assets/RUN1/`. `_writeguard` refuses it, but pass the run directory anyway.

**Nothing regenerates a human ruling.** The store is gitignored and its only
protection is a tarball on one machine. `git clean -xdf` lists `assets/` for
removal. A lost machine is a lost campaign — the accepted cost of keeping
identifiers out of a public repository.

**The database is the only receipt.** `storeOneRecord` sets `status = 1` and
never updates it from the DB call, so the endpoint's feedback workbook reports
success for rows that never wrote. Verification is a count query.

**SEEK assay ids are per-project.** A registration landing on another project's
assay puts the sample into a project it does not belong to, and nothing undoes
that. The 2026-08-26 audit found 578 of 26,188 rows in that state.
