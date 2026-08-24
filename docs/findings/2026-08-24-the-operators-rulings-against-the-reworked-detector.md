# The operator's rulings against the reworked detector

Measured 2026-08-24 on `feat/mode2-rework`. The question: does the rework
contradict a judgement the operator already made by hand?

**Short answer: no, and it does not help either. Against the only ground truth
this package owns, the rework is exactly neutral — it costs nothing he approved
and it removes nothing he rejected.**

## What ground truth there is

| file | cohorts | rulings |
|---|---|---|
| `assay-hygiene-bak/rulings/mode2-rulings.tsv` | 111 | 100 APPROVE, 6 REJECT, 5 WRONG_ASSAY |
| `assay-hygiene-bak/rulings/mode1-rulings.tsv` | 17 | 8 APPROVE, 9 WRONG_ASSAY |

128 cohorts, 108 approvals, 20 refusals. Neither file is in this repository and
neither may ever be: they key cohorts on strings from the namespace the
2026-08-21 history rewrite had to strip 1,570 instances of, and this repository
is public. They are copied into `tests/fixtures/` by hand and refused there by
`.gitignore`.

## How it was measured

```bash
mkdir -p <scratch>/out
cp assay-hygiene-bak/artifacts/vocabulary-curator.csv <scratch>/out/
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence assay-hygiene-bak/extract <scratch>/out
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_detect   assay-hygiene-bak/extract <scratch>/out
```

A scratch `out_dir`, because `assay-hygiene-bak/` is read-only on purpose and
`assay-hygiene/` symlinks into it — a default-path run must fail rather than
overwrite the baseline the comparison needs. Nothing reached a database.

**The evidence layer reproduces byte-identically**, so the only thing that
changed between the baseline and this run is the detection layer. md5, scratch
run against `assay-hygiene-bak/artifacts/`:

| artifact | md5 |
|---|---|
| `vocabulary.csv` | `211f91fff3f736ba635f1a2a90b57d35` |
| `precedent.csv` | `37f0add130a79322255bbb892963f58e` |
| `claims.parquet` | `e7810d97704ce336fa258c332d6ba6b3` |

The reworked census, verified rather than quoted — 170,786 rows:

| classification | rows |
|---|---|
| `CLS_ABSENCE_LINEAGE` | 67,898 |
| `CLS_UNREACHABLE` | 90,478 |
| `CLS_BOOTSTRAP` | 8,971 |
| `CLS_ALT_LABEL` | 952 |
| `CLS_UNRESOLVED` | 1,007 |
| `CLS_ABSENCE_COMPAT` | 107 |
| none (MODE_1) | 1,373 |

Pre-rework the first three lines were one line of 167,347 `CLS_ABSENCE_LINEAGE`;
99,449 rows moved.

## What the rework costs: nothing

- All **111** Mode 2 cohorts still resolve. The sheet holds **111 cohorts over
  9,500 rows** both before and after, cohort key for cohort key, and every one
  of them is still `CLS_ABSENCE_LINEAGE`.
- All **100** approvals survive. Not one approved cohort holds even a single
  reclassified row — including rows below the 0.50 sheet floor, where the check
  was made deliberately, because a cohort can survive the floor while part of
  it is gated away.
- The Mode 1 surface holds **37** cohorts before and after, and all **8**
  Mode 1 approvals still resolve.

## What the rework buys: nothing, against these 20

**13 of the 20 cohorts he refused are still on a primary review surface**, and
the reachability gate removed none of them. They will be put in front of him
again carrying a proposal he has already declined.

Eleven on the Mode 2 sheet, all still `CLS_ABSENCE_LINEAGE`, keyed
`lab | sample_type | parent_types | assay | field | value`, worst band first:

```
WRONG_ASSAY  ALT | A.ADNP | D.ADNP | Antibody-Dependent Functional Profiling (ADFP) | (lineage) | ADD_CHILD_TO_ASSAY    2 rows  A_precedent_0.95+
WRONG_ASSAY  ALT | CEL    | TIS    | Flow Cytometry                                 | (lineage) | ADD_CHILD_TO_ASSAY    2 rows  A_precedent_0.95+
WRONG_ASSAY  FOR | A.ADCD | D.ADCD | Antibody-Dependent Functional Profiling (ADFP) | (lineage) | ADD_CHILD_TO_ASSAY    1 row   A_precedent_0.95+
WRONG_ASSAY  SAS | ABP    | AB     | Library Creation                               | (lineage) | ADD_CHILD_TO_ASSAY    1 row   A_precedent_0.95+
WRONG_ASSAY  MEH | NHP    | (none) | Tissue Collection                              | (lineage) | ADD_PARENT_TO_ASSAY  12 rows  B_precedent_0.90+
REJECT       SHA | DNA    | TIS    | DNA Extraction                                 | (lineage) | ADD_CHILD_TO_ASSAY   91 rows  B_precedent_0.90+
REJECT       AGA | D.MSP  | TIS    | Mass Spectrometry                              | (lineage) | ADD_CHILD_TO_ASSAY   16 rows  B_precedent_0.90+
REJECT       SHA | DNA    | TIS    | DNA Extraction                                 | Protocol  | <redacted>            8 rows  B_precedent_0.90+
REJECT       SES | ABP    | AB     | Flow Cytometry                                 | (lineage) | ADD_CHILD_TO_ASSAY    1 row   B_precedent_0.90+
REJECT       ALT | ABP    | AB     | ELISA                                          | (lineage) | ADD_CHILD_TO_ASSAY    4 rows  C_precedent_0.75+
REJECT       BEH | MUS    | (none) | Cell Isolation                                 | (lineage) | ADD_PARENT_TO_ASSAY   4 rows  D_precedent_0.50+
```

142 rows in total — 124 REJECT, 18 WRONG_ASSAY. `(none)` is the literal
`NO_PARENT` the cohort key carries for a sample with no parent.

Two on the Mode 1 surface, both WRONG_ASSAY and both inherited rather than new:

```
WRONG_ASSAY  FLY | TIS | PAV | Short Read Sequencing              | Protocol | <redacted>
WRONG_ASSAY  SES | CEL | CEL | Cell Culture and Organoid Generation | Type   | Macrophages
```

The other seven Mode 1 refusals are gone, discharged by the `tif`/`png`
vocabulary retirements his own rulings caused — a vocabulary fix working, and
already covered by
`test_assay_hygiene_review.py::test_the_real_extract_round_trips_the_operators_seventeen_rulings`.

Two of the fifteen values above are redacted: they are protocol filenames from
the namespace this repository had to rewrite its history to remove. The
unredacted keys are in the failure message the test prints on the machine that
holds the fixtures.

## Why these rulings cannot validate the reachability gate

They can only show it costs nothing. **The two populations cannot intersect.**
An unreachable pair has zero type registrations, so its precedent rate cannot
exceed zero; the sheet the operator ruled on starts at 0.50. Measured: the
99,449 reclassified rows have `max(precedent_rate) == 0.0` and not one of them
sits at or above the floor, while all 9,500 rows on the sheet are
`CLS_ABSENCE_LINEAGE`. Of the 1,114 Mode 2 cohorts that carry a measured
precedent rate, 792 hold a reclassified row and **none of those 792 is one of
the 111 he ruled**.

So the green tests below are evidence that the gate is *harmless to his
judgements*, and are not evidence that the gate is *right*. Nothing in the
128 rulings speaks to the 99,449 rows the rework actually moves. Validating
that population needs its own ground truth.

## Where this lives

`tests/test_assay_hygiene_rulings.py`, eight tests, run against a fresh
`classify.main` over the real extract (~20 s) rather than against a csv on
disk. Seven are green.
`test_the_real_extract_drops_every_cohort_the_operator_rejected` **is red on
purpose** and prints the 13 names above; it goes green when a detector stops
emitting them, and must not be made green any other way. Every test skips on a
clone that does not have the rulings, so the committed suite is green without
them.
