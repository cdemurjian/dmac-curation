# `docs/`

What is in here, and which of it is still true.

**Only `docs/SECURITY.md` is maintained.** Everything else under `docs/` is dated by
construction: a design spec records what was decided on the day it was written and is
not revised when the code moves past it, an implementation plan is an execution record,
and a finding is a measurement taken against one extract on one day. **A `Status:` line
inside a spec is part of that frozen record, not a claim about the repository today** —
three of them are known to be stale and are marked below.

The living reference documentation is not under `docs/` at all:

| where | what it is |
|---|---|
| `README.md` | layout, modes, commands, quick start |
| `skills/curation/SKILL.md` | the mode table, 8 hard rules, 7 soft rules, 20 pitfalls |
| `skills/curation/{PHASES,FDH,SCHEMA,REPORTS,ASSAY}.md` | one reference doc per mode |
| `commands/*.md` | the authority on what each slash command actually does |
| `context/VINTAGE.json`, `context/PROVENANCE.json` | the vintage of every bundled snapshot |
| `.gitignore` | the exclusion rules, each with the incident that caused it |
| `CONTRIBUTING.md` | what lives in more than one file, and the two guards you will meet |
| `docs/RELEASING.md` | the six places the version lives |
| `tests/README.md` | why a green suite may have measured nothing |

## Start here

New to the repository, in this order:

1. `README.md`
2. `skills/curation/SKILL.md` — the mode table is the one place all five modes are listed
3. `docs/SECURITY.md` — mandatory before touching credentials, `working/`, or any
   curation output
4. `.gitignore` — read the comments. This repository is **public** and has already
   needed two history rewrites
5. `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md` — what a "mode" is,
   and why nothing is registered in `plugin.json`
6. `tests/conftest.py` — why a green suite may have measured nothing

## Living reference

| file | what it is |
|---|---|
| [`SECURITY.md`](SECURITY.md) | Credentials and identifiers. Where each credential comes from and which script consumes it; the three places credentials have actually turned up on disk; the two identifier incidents that cost history rewrites; and how `tests/test_no_plaintext_secrets.py` and `tests/test_identifier_exposure.py` enforce both. **Fix this file when it drifts.** |
| [`RELEASING.md`](RELEASING.md) | The version lives in six places. Change all six in one commit. |

## Design specs — historical

Frozen at their date. Read for *why* a decision was made, never for what the code does.

| file | subject | status as of 2026-08-27 |
|---|---|---|
| [`specs/2026-05-27-dmac-curation-plugin-design.md`](superpowers/specs/2026-05-27-dmac-curation-plugin-design.md) | the original 13-phase pipeline as a plugin | superseded by the 2026-07-21 toolkit design; the pipeline is now 11 numbered phases + 9b |
| [`specs/2026-07-02-fdh-integration-design.md`](superpowers/specs/2026-07-02-fdh-integration-design.md) | FairDomHub as two standalone modules | shipped (0.2.0); still describes `fdh` mode accurately |
| [`specs/2026-07-21-curation-toolkit-design.md`](superpowers/specs/2026-07-21-curation-toolkit-design.md) | **the architecture document: what a "mode" is** | shipped (0.3.0). The closest thing to a living architecture reference; predates `assay` |
| [`specs/2026-07-21-pipeline-rework-review.md`](superpowers/specs/2026-07-21-pipeline-rework-review.md) | review verdict on the pipeline; two steps that do not earn their place | acted on in 0.3.0 |
| [`specs/2026-07-21-report-mode-design.md`](superpowers/specs/2026-07-21-report-mode-design.md) | `report` mode — one declarative mapping spec, O(columns) | shipped (0.3.0); mirrored by `skills/curation/REPORTS.md` |
| [`specs/2026-07-21-schema-mode-design.md`](superpowers/specs/2026-07-21-schema-mode-design.md) | `schema` mode — sample-type authoring, human applies | shipped (0.3.0). **Predates OBI clade + CEDAR grounding**; `skills/curation/SCHEMA.md` is current |
| [`specs/2026-08-04-init-auto-detect-project-lab-design.md`](superpowers/specs/2026-08-04-init-auto-detect-project-lab-design.md) | auto-detect project / lab / PI at `/curate-init` | shipped 2026-08-04. Its status line said "pending implementation plan" until this audit corrected it |
| [`specs/2026-08-12-assay-hygiene-design.md`](superpowers/specs/2026-08-12-assay-hygiene-design.md) | assay hygiene v1: complete the lineage graph, then backfill | **superseded** — corrected 2026-08-27; it had claimed "stage 0 not implemented" and "Not a plugin mode yet", both false |
| [`specs/2026-08-14-assay-hygiene-three-mode-design.md`](superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md) | three equal modes over one evidence layer | **amended twice**, the second superseding the first. Its own header says "Do not plan from the sections below without reading that amendment first" |
| [`specs/2026-08-27-assay-hygiene-mode-design.md`](superpowers/specs/2026-08-27-assay-hygiene-mode-design.md) | assay hygiene as a curation mode — the run model, the ruling store, the write path | **the current assay design.** Shipped the day it was approved. Note it calls `assay` the *fourth* mode; it is the fifth — the spec omits `fdh` |

### The three assay-hygiene specs contradict each other, by design

They are three successive designs, not three views of one. Read only the newest
(`2026-08-27`) for the shape of the mode as it ships, and `skills/curation/ASSAY.md` for
the operator-facing contract. The 2026-08-12 and 2026-08-14 specs survive because the
*arguments* in them — why stage 0 exists, why absence is not contradiction, why Mode 3
has no detector — are not repeated anywhere else.

## Implementation plans — historical

SDD execution records. Several carry figures the work itself later moved; the commit
messages are the authority on what actually landed. **Do not plan from these.**

| file | lines | plan |
|---|---|---|
| [`plans/2026-05-27-dmac-curation-plugin.md`](superpowers/plans/2026-05-27-dmac-curation-plugin.md) | 2,738 | the original 13-phase plugin |
| [`plans/2026-07-02-fdh-integration.md`](superpowers/plans/2026-07-02-fdh-integration.md) | 1,248 | the two FDH modules |
| [`plans/2026-07-21-curation-toolkit.md`](superpowers/plans/2026-07-21-curation-toolkit.md) | 12,503 | pipeline → toolkit; the largest file in the repository |
| [`plans/2026-08-04-init-auto-detect.md`](superpowers/plans/2026-08-04-init-auto-detect.md) | 650 | `detect_context.py` + `nextseek_api.py detect-context` |
| [`plans/2026-08-12-assay-hygiene.md`](superpowers/plans/2026-08-12-assay-hygiene.md) | 1,974 | the six-stage assay pipeline |
| [`plans/2026-08-13-assay-hygiene-stage0.md`](superpowers/plans/2026-08-13-assay-hygiene-stage0.md) | 1,726 | the 90,534-edge `DERIVED_FROM` backfill |
| [`plans/2026-08-14-assay-hygiene-evidence-layer-and-mode-3.md`](superpowers/plans/2026-08-14-assay-hygiene-evidence-layer-and-mode-3.md) | 2,189 | evidence layer + Mode 3 |
| [`plans/2026-08-17-assay-hygiene-mode-1-and-2-detection.md`](superpowers/plans/2026-08-17-assay-hygiene-mode-1-and-2-detection.md) | 640 | vocabulary gate + Modes 1 and 2 |
| [`plans/2026-08-21-assay-hygiene-mode2-generation-rework.md`](superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md) | 738 | stop the 99,449 unreachable proposals without deleting the 2,035 real ones |
| [`plans/2026-08-27-assay-hygiene-prerequisites.md`](superpowers/plans/2026-08-27-assay-hygiene-prerequisites.md) | 794 | four defects that would let run 2 destroy run 1's evidence |
| [`plans/2026-08-27-assay-hygiene-ruling-store.md`](superpowers/plans/2026-08-27-assay-hygiene-ruling-store.md) | 657 | the durable cross-run ruling store |
| [`plans/2026-08-27-assay-hygiene-mode-commands.md`](superpowers/plans/2026-08-27-assay-hygiene-mode-commands.md) | 2,760 | the eight `curate-assay-*` commands |

## Findings — point-in-time measurements

Each is true of the extract and the code at its date. None is maintained.

| file | what it measured |
|---|---|
| [`assay-hygiene-increment-2-deferred-minors.md`](assay-hygiene-increment-2-deferred-minors.md) | 52 review findings judged real and deliberately not fixed, rescued 2026-08-18 from a gitignored SDD ledger before its worktree was torn down |
| [`findings/2026-08-21-assay-143-name-collision.md`](findings/2026-08-21-assay-143-name-collision.md) | internal assay 143 is named for the wrong GPT |
| [`findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md`](findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md) | read-only audit of 170,786 findings rows. **Its `assay-hygiene-bak/` paths do not resolve in a clone**, and it says so |
| [`findings/2026-08-21-mode2-lineage-lane-is-ungated.md`](findings/2026-08-21-mode2-lineage-lane-is-ungated.md) | the root cause of 99,449 impossible proposals. **Fixed** in `c06c2c6` |
| [`findings/2026-08-21-pre-rework-baseline.md`](findings/2026-08-21-pre-rework-baseline.md) | the measured row table the rework's deltas are judged against, derived by a committed script |
| [`findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md`](findings/2026-08-21-track-a-the-write-path-through-the-assay-api.md) | what the chosen NExtSEEK assay write route does, its cost, and the one open question. Source read on a dev box, not in this repo |
| [`findings/2026-08-24-the-operators-rulings-against-the-reworked-detector.md`](findings/2026-08-24-the-operators-rulings-against-the-reworked-detector.md) | the rework is exactly neutral against 111 hand rulings |
| [`findings/2026-08-25-the-prose-figure-census.md`](findings/2026-08-25-the-prose-figure-census.md) | an AST + `tokenize` census of the numeric literals in the comments and docstrings of `scripts/assay_hygiene/` and `tests/test_assay_hygiene_*.py`, answering "which figures are trustworthy" |

## Audits

| directory | what it is |
|---|---|
| [`audit/2026-08-27-docs-audit/`](audit/2026-08-27-docs-audit/) | ground-truth inventories of commands, skills, scripts and repo furniture, plus the drift audits derived from them and the resulting `PROPOSAL.md`. A snapshot at `833e9be`, not a maintained reference |

## Adding a document here

- A **finding** carries its date in the filename and states, in its first paragraph,
  what it measured and against which extract. If it cites a path outside the repository,
  say so — `findings/2026-08-21-audit-of-the-detection-outputs-and-the-code.md` is the
  model.
- A **spec** carries a `Status:` line. When the work ships, amend that line rather than
  the body: the body is the argument, and the argument stays true.
- A **plan** is written once and not maintained.
- Anything a reader needs in order to *use* the plugin belongs in `skills/curation/` or
  `commands/`, not here.
- **No document under `docs/` may carry a real sample or protocol identifier.** See
  `docs/SECURITY.md`.
