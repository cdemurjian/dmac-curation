# The prose-figure census

Task 12 of the Mode 2 generation rework. **The enumeration is the deliverable.**
Two audits and four task reviews all landed on the same recurring finding: not
that the figures in `scripts/assay_hygiene/` are wrong, but that *nobody can
tell which ones are trustworthy*. This file answers that question once.

## What was counted, and how

Every numeric literal appearing in a comment or docstring across
`scripts/assay_hygiene/*.py` (26 modules) and `tests/test_assay_hygiene_*.py`
(23 files) was extracted by AST + `tokenize` — 6,984 occurrences on 3,881 lines.
Most are not figures: dates, thresholds, arities, fixture ids, line
cross-references, id literals. Bucketed:

| bucket | occurrences |
|---|---:|
| bare integer < 10 | 1,684 |
| bare integer 10-99 | 1,530 |
| bare integer 100-999 | 1,321 |
| **thousands-separated integer** | **932** |
| date component | 628 |
| decimal (threshold, rate, ratio) | 566 |
| percentage | 201 |
| bare integer >= 1000 | 122 |

**The census below is the population-scale set**: literals matching
`\d{1,3}(,\d{3})+` — a figure written with thousands separators is, in this
package, always a claim about the corpus. That is **793 occurrences on 585
lines across 44 files, collapsing to 260 distinct values.** Values are the unit
of the table because "is this figure trustworthy" is a question about a value,
not about each site that quotes it.

Percentages and sub-1000 integers were **not** individually re-derived. The
ones this sweep did check are listed under "Figures outside the census" below.

## How the figures were re-derived

A full pipeline run on today's code, into a scratch `out_dir`, over the
read-only baseline extract:

```bash
mkdir -p <scratch>/run12
cp assets/RUN1/04-artifacts/vocabulary-curator.csv <scratch>/run12/
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_evidence assets/RUN1/01-extract <scratch>/run12
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.run_detect   assets/RUN1/01-extract <scratch>/run12
```

`vocabulary.csv`, `claims.parquet`, `mode3-disposition.csv` and
`vocabulary-defects.csv` reproduce the baseline artifacts byte-identically;
`findings.csv` and `precedent.csv` do not, and both differences are this
branch's own work. Everything else was re-derived by calling the package's
own functions against that run rather than by reading a number off a report.

**Nothing reached a database.** No driver was run.

## Verdicts

- **correct** — re-derived this session; the value matches the claim.
- **STALE** — re-derived; the value differs. Fixed in the commit that follows.
- **MEANING-SHIFTED** — the value is right for *some* quantity, and the prose
  attributes it to another.
- **historical** — the prose explicitly scopes it to a superseded run, spec or
  plan ("the spec read", "increment 1 reported", "an earlier revision"). Correct
  as stated and structurally cannot go stale.
- **unmeasurable-here** — measured against a source not in this repository:
  production Neo4j, the SEEK id space, `measure_metadata_accuracy.py`, the
  operator's rulings, the agent adjudications, or a backtest hold-out this
  sweep did not re-run.
- **unverified** — not re-derived this session. **This is the honest residue,
  and it is the answer to the audits' question**: 153 of 260 distinct figures
  carry no evidence from this sweep either way.

### Tally

| verdict | distinct figures | occurrences |
|---|---:|---:|
| correct | 58 | 318 |
| STALE | 15 | 65 |
| MEANING-SHIFTED | 1 | 20 |
| historical | 18 | 74 |
| unmeasurable-here | 15 | 59 |
| unverified | 153 | 257 |
| **total** | **260** | **793** |

Where the unverified mass sits:

| file | unverified occurrences |
|---|---:|
| `tests/test_assay_hygiene_classify.py` | 32 |
| `scripts/assay_hygiene/classify.py` | 22 |
| `scripts/assay_hygiene/backtest.py` | 20 |
| `scripts/assay_hygiene/validation_sample.py` | 18 |
| `scripts/assay_hygiene/mode2.py` | 16 |
| `scripts/assay_hygiene/compatibility.py` | 14 |
| `scripts/assay_hygiene/_schema.py` | 13 |
| `tests/test_assay_hygiene_run_detect.py` | 13 |
| `scripts/assay_hygiene/lineage.py` | 11 |
| `tests/test_assay_hygiene_compatibility.py` | 9 |
| `tests/test_assay_hygiene_validation_sample.py` | 8 |
| `tests/test_assay_hygiene_lineage.py` | 8 |

### The census

| figure | occ | verdict | what it counts / measured value | sites |
|---:|---:|---|---|---|
| `99,449` | 36 | **correct** | PRE_UNREACHABLE keys | scripts/assay_hygiene/baseline.py:8; scripts/assay_hygiene/classify.py:46; scripts/assay_hygiene/classify.py:131; scripts/assay_hygiene/classify.py:137; scripts/assay_hygiene/classify.py:147; scripts/assay_hygiene/classify.py:907 (+30 more) |
| `138,007` | 21 | **STALE** | measures **130,764** (all claims) | scripts/assay_hygiene/audit.py:167; scripts/assay_hygiene/classify.py:304; scripts/assay_hygiene/classify.py:1001; scripts/assay_hygiene/classify.py:1080; scripts/assay_hygiene/gate.py:68; scripts/assay_hygiene/gate.py:120 (+15 more) |
| `55,007` | 20 | **MEANING-SHIFTED** | `lineage.mode2_ceiling`'s add_parent_rows (CORRECT there); WRONG where quoted as the distinct candidates the 666,939 child-only edges raise, which is 55,032 | scripts/assay_hygiene/compatibility.py:169; scripts/assay_hygiene/dossier.py:40; scripts/assay_hygiene/lineage.py:498; scripts/assay_hygiene/lineage.py:504; scripts/assay_hygiene/lineage.py:508; scripts/assay_hygiene/mode2.py:31 (+14 more) |
| `6,242` | 16 | **correct** | Mode 1 population | scripts/assay_hygiene/classify.py:82; scripts/assay_hygiene/classify.py:103; scripts/assay_hygiene/classify.py:298; scripts/assay_hygiene/classify.py:328; scripts/assay_hygiene/mode2.py:496; scripts/assay_hygiene/_schema.py:155 (+10 more) |
| `172,338` | 15 | **correct** | lineage ceiling union_rows | scripts/assay_hygiene/classify.py:152; scripts/assay_hygiene/classify.py:225; scripts/assay_hygiene/classify.py:990; scripts/assay_hygiene/classify.py:1557; scripts/assay_hygiene/lineage.py:504; scripts/assay_hygiene/mode2.py:31 (+9 more) |
| `67,898` | 13 | **correct** | PRE_LINEAGE keys / CLS_ABSENCE_LINEAGE rows | scripts/assay_hygiene/classify.py:30; scripts/assay_hygiene/classify.py:128; scripts/assay_hygiene/classify.py:137; scripts/assay_hygiene/classify.py:147; scripts/assay_hygiene/classify.py:758; scripts/assay_hygiene/classify.py:768 (+7 more) |
| `170,786` | 13 | **correct** | findings.csv rows | scripts/assay_hygiene/classify.py:135; scripts/assay_hygiene/run_detect.py:165; scripts/assay_hygiene/_schema.py:380; scripts/assay_hygiene/_schema.py:419; scripts/assay_hygiene/validation_sample.py:18; tests/test_assay_hygiene_classify.py:4223 (+7 more) |
| `4,242` | 12 | **correct** | rows_with_a_blocked_claim = lineage rows the gate refuses | scripts/assay_hygiene/classify.py:153; scripts/assay_hygiene/classify.py:882; scripts/assay_hygiene/classify.py:1557; scripts/assay_hygiene/run_detect.py:834; tests/test_assay_hygiene_classify.py:2771; tests/test_assay_hygiene_classify.py:4085 (+6 more) |
| `8,971` | 12 | **correct** | CLS_BOOTSTRAP rows | scripts/assay_hygiene/mode2.py:112; scripts/assay_hygiene/mode2.py:302; scripts/assay_hygiene/mode2.py:785; scripts/assay_hygiene/_schema.py:786; scripts/assay_hygiene/validation_sample.py:19; scripts/assay_hygiene/validation_sample.py:30 (+6 more) |
| `167,454` | 12 | **correct** | MODE_2 rows | scripts/assay_hygiene/classify.py:46; scripts/assay_hygiene/classify.py:138; scripts/assay_hygiene/classify.py:1560; scripts/assay_hygiene/mode2.py:778; scripts/assay_hygiene/mode2.py:857; scripts/assay_hygiene/review_mode2.py:37 (+6 more) |
| `1,321` | 11 | **correct** | findings rows on a seek_fallback id | scripts/assay_hygiene/mode2.py:297; scripts/assay_hygiene/mode2.py:299; scripts/assay_hygiene/mode2.py:891; scripts/assay_hygiene/_schema.py:419; scripts/assay_hygiene/_schema.py:423; tests/test_assay_hygiene_classify.py:4253 (+5 more) |
| `19,337` | 11 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:37; scripts/assay_hygiene/backtest.py:71; scripts/assay_hygiene/backtest.py:87; scripts/assay_hygiene/backtest.py:102; scripts/assay_hygiene/backtest.py:467; scripts/assay_hygiene/backtest.py:586 (+5 more) |
| `117,463` | 11 | **correct** | lineage ceiling add_child_rows | scripts/assay_hygiene/compatibility.py:169; scripts/assay_hygiene/lineage.py:498; scripts/assay_hygiene/lineage.py:504; scripts/assay_hygiene/lineage.py:508; scripts/assay_hygiene/mode2.py:31; scripts/assay_hygiene/mode2.py:732 (+5 more) |
| `214,296` | 11 | **correct** | membership rows | scripts/assay_hygiene/backtest.py:60; scripts/assay_hygiene/classify.py:413; scripts/assay_hygiene/classify.py:1361; scripts/assay_hygiene/compatibility.py:180; scripts/assay_hygiene/compatibility.py:529; scripts/assay_hygiene/gate.py:336 (+5 more) |
| `4,151` | 10 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:37; scripts/assay_hygiene/backtest.py:71; scripts/assay_hygiene/backtest.py:86; scripts/assay_hygiene/backtest.py:96; scripts/assay_hygiene/backtest.py:103; scripts/assay_hygiene/backtest.py:467 (+4 more) |
| `90,534` | 10 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/stage0.py:112; scripts/assay_hygiene/stage0.py:119; scripts/assay_hygiene/stage0.py:395; scripts/assay_hygiene/stage0.py:668; scripts/assay_hygiene/stage0.py:700; tests/test_assay_hygiene_stage0_apply.py:385 (+4 more) |
| `1,012` | 8 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/dossier.py:42; scripts/assay_hygiene/precedent.py:216; scripts/assay_hygiene/precedent.py:289; scripts/assay_hygiene/review_verdicts.py:9; scripts/assay_hygiene/_schema.py:375; tests/test_assay_hygiene_dossier.py:3 (+2 more) |
| `89,263` | 8 | **correct** | internal assay 74 (Tissue Collection) population | scripts/assay_hygiene/mode2.py:316; scripts/assay_hygiene/mode2.py:635; scripts/assay_hygiene/mode2.py:643; scripts/assay_hygiene/_schema.py:782; tests/test_assay_hygiene_mode2.py:255; tests/test_assay_hygiene_mode2.py:257 (+2 more) |
| `117,331` | 8 | **correct** | emitted ADD_CHILD lane rows | scripts/assay_hygiene/backtest.py:108; scripts/assay_hygiene/mode2.py:731; scripts/assay_hygiene/mode2.py:1057; scripts/assay_hygiene/_schema.py:333; tests/test_assay_hygiene_backtest.py:977; tests/test_assay_hygiene_classify.py:1779 (+2 more) |
| `1,098` | 7 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/compatibility.py:32; scripts/assay_hygiene/compatibility.py:504; scripts/assay_hygiene/lineage.py:509; scripts/assay_hygiene/mode2.py:491; scripts/assay_hygiene/validation_sample.py:197; tests/test_assay_hygiene_compatibility.py:20 (+1 more) |
| `2,166` | 7 | **STALE** | measures **1,373** (MODE_1 rows) | scripts/assay_hygiene/classify.py:107; scripts/assay_hygiene/review.py:199; scripts/assay_hygiene/review.py:395; tests/test_assay_hygiene_classify.py:2622; tests/test_assay_hygiene_review.py:336; tests/test_assay_hygiene_run_detect.py:459 (+1 more) |
| `7,831` | 7 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/compatibility.py:362; scripts/assay_hygiene/compatibility.py:365; scripts/assay_hygiene/compatibility.py:366; scripts/assay_hygiene/compatibility.py:538; scripts/assay_hygiene/_schema.py:296; tests/test_assay_hygiene_compatibility.py:1044 (+1 more) |
| `25,974` | 7 | **STALE** | measures **18,652** (GATE_LOW_SUPPORT claims) | scripts/assay_hygiene/classify.py:95; scripts/assay_hygiene/gate.py:55; scripts/assay_hygiene/gate.py:68; scripts/assay_hygiene/gate.py:70; scripts/assay_hygiene/gate.py:212; tests/test_assay_hygiene_classify.py:27 (+1 more) |
| `90,478` | 7 | **correct** | CLS_UNREACHABLE rows | scripts/assay_hygiene/validation_sample.py:19; scripts/assay_hygiene/validation_sample.py:29; scripts/assay_hygiene/validation_sample.py:619; scripts/assay_hygiene/validation_sample.py:747; tests/test_assay_hygiene_rulings.py:4; tests/test_assay_hygiene_validation_sample.py:990 (+1 more) |
| `167,347` | 7 | **correct** | neighbour-anchored MODE_2 rows (167,454 - 107 compat) | scripts/assay_hygiene/classify.py:147; scripts/assay_hygiene/classify.py:1558; scripts/assay_hygiene/review_mode2.py:280; scripts/assay_hygiene/review_mode2.py:482; scripts/assay_hygiene/run_detect.py:870; tests/test_assay_hygiene_classify.py:4100 (+1 more) |
| `175,339` | 7 | **correct** | absence keys into the precedence | scripts/assay_hygiene/classify.py:29; scripts/assay_hygiene/classify.py:124; scripts/assay_hygiene/classify.py:748; scripts/assay_hygiene/classify.py:987; tests/test_assay_hygiene_classify.py:3202; tests/test_assay_hygiene_classify.py:4085 (+1 more) |
| `177,392` | 7 | **correct** | node rows | scripts/assay_hygiene/audit.py:166; scripts/assay_hygiene/compatibility.py:138; scripts/assay_hygiene/gate.py:270; scripts/assay_hygiene/gate.py:274; scripts/assay_hygiene/gate.py:290; scripts/assay_hygiene/gate.py:360 (+1 more) |
| `1,052` | 6 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:328; scripts/assay_hygiene/_schema.py:155; tests/test_assay_hygiene_classify.py:180; tests/test_assay_hygiene_classify.py:620; tests/test_assay_hygiene_schema.py:172; tests/test_assay_hygiene_schema.py:209 |
| `1,300` | 6 | **correct** | n_child_only on the worked case (2, D.ADCD, TIS, 153) | scripts/assay_hygiene/precedent.py:204; scripts/assay_hygiene/_schema.py:372; tests/test_assay_hygiene_dossier.py:60; tests/test_assay_hygiene_precedent.py:145; tests/test_assay_hygiene_precedent.py:146; tests/test_assay_hygiene_schema.py:136 |
| `2,210` | 6 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/classify.py:506; scripts/assay_hygiene/gate.py:138; scripts/assay_hygiene/gate.py:187; scripts/assay_hygiene/_schema.py:1013; tests/test_assay_hygiene_gate.py:414; tests/test_assay_hygiene_gate.py:414 |
| `54,780` | 6 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/compatibility.py:169; scripts/assay_hygiene/lineage.py:499; scripts/assay_hygiene/lineage.py:506; scripts/assay_hygiene/run_detect.py:277; tests/test_assay_hygiene_lineage.py:911; tests/test_assay_hygiene_lineage.py:915 |
| `90,000` | 6 | **unverified** | not re-derived this session | scripts/assay_hygiene/stage0_apply.py:287; scripts/assay_hygiene/stage0.py:352; scripts/assay_hygiene/stage0.py:380; tests/test_assay_hygiene_stage0_apply.py:13; tests/test_assay_hygiene_stage0.py:777; tests/test_assay_hygiene_stage0.py:1105 |
| `115,087` | 6 | **correct** | BY_PRECEDENT rows reading precedent_n_both == 0 | scripts/assay_hygiene/mode2.py:948; scripts/assay_hygiene/_schema.py:381; scripts/assay_hygiene/_schema.py:388; scripts/assay_hygiene/_schema.py:389; tests/test_assay_hygiene_mode2.py:522; tests/test_assay_hygiene_schema.py:121 |
| `116,365` | 6 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/compatibility.py:169; scripts/assay_hygiene/lineage.py:499; scripts/assay_hygiene/lineage.py:506; scripts/assay_hygiene/run_detect.py:277; tests/test_assay_hygiene_lineage.py:911; tests/test_assay_hygiene_lineage.py:915 |
| `123,439` | 6 | **STALE** | measures **122,011** (claims naming an assay already held) | scripts/assay_hygiene/classify.py:1001; scripts/assay_hygiene/classify.py:1080; tests/test_assay_hygiene_classify.py:2965; tests/test_assay_hygiene_classify.py:3652; tests/test_assay_hygiene_classify.py:3790; tests/test_assay_hygiene_classify.py:4084 |
| `130,764` | 6 | **correct** | attached claims (claims.parquet rows) | scripts/assay_hygiene/classify.py:121; scripts/assay_hygiene/classify.py:886; tests/test_assay_hygiene_classify.py:4085; tests/test_assay_hygiene_classify.py:4090; tests/test_assay_hygiene_classify.py:4092; tests/test_assay_hygiene_classify.py:4366 |
| `166,578` | 6 | **correct** | BY_PRECEDENT findings rows | scripts/assay_hygiene/mode2.py:949; scripts/assay_hygiene/_schema.py:381; scripts/assay_hygiene/_schema.py:399; tests/test_assay_hygiene_mode2.py:522; tests/test_assay_hygiene_mode2.py:541; tests/test_assay_hygiene_schema.py:122 |
| `666,939` | 6 | **correct** | n_child_only summed over the 961 rules (EDGES) | scripts/assay_hygiene/dossier.py:39; scripts/assay_hygiene/precedent.py:188; scripts/assay_hygiene/_schema.py:98; tests/test_assay_hygiene_precedent.py:115; tests/test_assay_hygiene_schema.py:68; tests/test_assay_hygiene_schema.py:135 |
| `1,071` | 5 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:197; scripts/assay_hygiene/validation_sample.py:197; scripts/assay_hygiene/validation_sample.py:197; scripts/assay_hygiene/validation_sample.py:318; tests/test_assay_hygiene_validation_sample.py:402 |
| `1,373` | 5 | **correct** | MODE_1 rows = keys_mode_1 = claim_rows_proposed | scripts/assay_hygiene/classify.py:126; scripts/assay_hygiene/classify.py:136; tests/test_assay_hygiene_classify.py:2622; tests/test_assay_hygiene_classify.py:2625; tests/test_assay_hygiene_mode2.py:14 |
| `1,526` | 5 | **correct** | largest lineage_n_supports | scripts/assay_hygiene/backtest.py:22; scripts/assay_hygiene/mode2.py:473; scripts/assay_hygiene/_schema.py:355; tests/test_assay_hygiene_backtest.py:13; tests/test_assay_hygiene_schema.py:167 |
| `3,511` | 5 | **STALE** | measures **3,495** (claims failing a blocking test AND a floor) | scripts/assay_hygiene/classify.py:560; scripts/assay_hygiene/gate.py:200; scripts/assay_hygiene/gate.py:625; tests/test_assay_hygiene_classify.py:462; tests/test_assay_hygiene_gate.py:766 |
| `4,255` | 5 | **STALE** | measures **4,242** (rows_with_a_blocked_claim) | scripts/assay_hygiene/mode2.py:179; scripts/assay_hygiene/mode2.py:758; scripts/assay_hygiene/mode2.py:988; tests/test_assay_hygiene_classify.py:2771; tests/test_assay_hygiene_classify.py:4084 |
| `4,553` | 5 | **correct** | keys refused by the gate = GATE_UNREACHABLE claims | scripts/assay_hygiene/classify.py:125; scripts/assay_hygiene/classify.py:878; scripts/assay_hygiene/classify.py:882; tests/test_assay_hygiene_classify.py:4357; tests/test_assay_hygiene_classify.py:4361 |
| `8,806` | 5 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:67; scripts/assay_hygiene/backtest.py:107; scripts/assay_hygiene/backtest.py:584; tests/test_assay_hygiene_backtest.py:712; tests/test_assay_hygiene_backtest.py:977 |
| `18,996` | 5 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:67; scripts/assay_hygiene/backtest.py:107; scripts/assay_hygiene/backtest.py:585; tests/test_assay_hygiene_backtest.py:712; tests/test_assay_hygiene_backtest.py:976 |
| `163,393` | 5 | **correct** | sample records | scripts/assay_hygiene/lineage.py:171; scripts/assay_hygiene/run_evidence.py:870; scripts/assay_hygiene/vocabulary.py:34; tests/test_assay_hygiene_lineage.py:530; tests/test_assay_hygiene_rulings.py:142 |
| `214,124` | 5 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:362; scripts/assay_hygiene/mode2.py:740; scripts/assay_hygiene/precedent.py:85; scripts/assay_hygiene/review.py:348; tests/test_assay_hygiene_classify.py:2234 |
| `333,717` | 5 | **correct** | held-out test edges over all scored terms | scripts/assay_hygiene/gate.py:123; scripts/assay_hygiene/gate.py:132; scripts/assay_hygiene/run_evidence.py:287; tests/test_assay_hygiene_gate.py:430; tests/test_assay_hygiene_run_evidence.py:296 |
| `794,593` | 5 | **correct** | edge_rows | scripts/assay_hygiene/backtest.py:61; scripts/assay_hygiene/backtest.py:667; scripts/assay_hygiene/lineage.py:251; tests/test_assay_hygiene_lineage.py:636; tests/test_assay_hygiene_vocabulary.py:114 |
| `1,122` | 4 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:297; scripts/assay_hygiene/mode2.py:300; tests/test_assay_hygiene_classify.py:4256; tests/test_assay_hygiene_mode2.py:421 |
| `2,066` | 4 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:132; scripts/assay_hygiene/classify.py:1104; scripts/assay_hygiene/classify.py:1117; scripts/assay_hygiene/classify.py:1117 |
| `2,405` | 4 | **correct** | samples_registered_nowhere | scripts/assay_hygiene/mode2.py:496; tests/test_assay_hygiene_classify.py:2015; tests/test_assay_hygiene_classify.py:2719; tests/test_assay_hygiene_classify.py:3743 |
| `2,447` | 4 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/run_detect.py:493; scripts/assay_hygiene/run_detect.py:495; tests/test_assay_hygiene_run_detect.py:952; tests/test_assay_hygiene_run_detect.py:954 |
| `4,143` | 4 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:71; scripts/assay_hygiene/backtest.py:586; tests/test_assay_hygiene_backtest.py:711; tests/test_assay_hygiene_backtest.py:962 |
| `5,839` | 4 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/compatibility.py:365; scripts/assay_hygiene/_schema.py:297; tests/test_assay_hygiene_compatibility.py:1044; tests/test_assay_hygiene_schema.py:334 |
| `6,932` | 4 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:1105; scripts/assay_hygiene/classify.py:1291; scripts/assay_hygiene/_schema.py:277; tests/test_assay_hygiene_classify.py:4585 |
| `19,270` | 4 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:71; scripts/assay_hygiene/backtest.py:586; tests/test_assay_hygiene_backtest.py:710; tests/test_assay_hygiene_backtest.py:962 |
| `54,852` | 4 | **correct** | ADD_PARENT_TO_ASSAY findings rows | scripts/assay_hygiene/review_mode2.py:280; scripts/assay_hygiene/review_mode2.py:482; scripts/assay_hygiene/validation_sample.py:688; tests/test_assay_hygiene_review_mode2.py:384 |
| `85,093` | 4 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/stage0.py:112; scripts/assay_hygiene/stage0.py:669; tests/test_assay_hygiene_stage0.py:539; tests/test_assay_hygiene_stage0.py:1211 |
| `180,995` | 4 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/classify.py:34; scripts/assay_hygiene/classify.py:750; scripts/assay_hygiene/classify.py:992; tests/test_assay_hygiene_classify.py:4083 |
| `360,027` | 4 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/claims.py:11; scripts/assay_hygiene/_schema.py:515; tests/test_assay_hygiene_precedent.py:433; tests/test_assay_hygiene_schema.py:748 |
| `794,592` | 4 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:29; scripts/assay_hygiene/lineage.py:251; tests/test_assay_hygiene_lineage.py:13; tests/test_assay_hygiene_lineage.py:636 |
| `1,340` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:69; scripts/assay_hygiene/classify.py:1360; scripts/assay_hygiene/mode2.py:8 |
| `1,570` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/audit.py:125; scripts/assay_hygiene/_schema.py:550; tests/test_assay_hygiene_rulings.py:22 |
| `1,657` | 3 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/classify.py:107; scripts/assay_hygiene/review.py:438; tests/test_assay_hygiene_review.py:428 |
| `1,755` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:392; scripts/assay_hygiene/_schema.py:313; tests/test_assay_hygiene_compatibility.py:1059 |
| `1,907` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:140; scripts/assay_hygiene/_schema.py:761; tests/test_assay_hygiene_compatibility.py:588 |
| `2,035` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:39; scripts/assay_hygiene/compatibility.py:141; tests/test_assay_hygiene_compatibility.py:590 |
| `2,067` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:1056; tests/test_assay_hygiene_classify.py:2156; tests/test_assay_hygiene_classify.py:2713 |
| `2,912` | 3 | **STALE** | measures **2,119** (Mode 1 claim_rows) | scripts/assay_hygiene/classify.py:105; scripts/assay_hygiene/classify.py:304; tests/test_assay_hygiene_classify.py:2621 |
| `4,415` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:104; scripts/assay_hygiene/classify.py:298; tests/test_assay_hygiene_classify.py:381 |
| `4,750` | 3 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | tests/test_assay_hygiene_gate.py:1048; tests/test_assay_hygiene_gate.py:1056; tests/test_assay_hygiene_vocabulary.py:608 |
| `5,000` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:335; scripts/assay_hygiene/vocabulary.py:252; tests/test_assay_hygiene_vocabulary.py:243 |
| `5,688` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:94; tests/test_assay_hygiene_backtest.py:766; tests/test_assay_hygiene_backtest.py:970 |
| `8,170` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:1056; tests/test_assay_hygiene_classify.py:2155; tests/test_assay_hygiene_classify.py:2712 |
| `8,179` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:393; scripts/assay_hygiene/compatibility.py:442; scripts/assay_hygiene/_schema.py:314 |
| `9,500` | 3 | **unverified** | not re-derived this session | tests/test_assay_hygiene_review_mode2.py:294; tests/test_assay_hygiene_rulings.py:378; tests/test_assay_hygiene_rulings.py:407 |
| `9,878` | 3 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/lineage.py:32; tests/test_assay_hygiene_lineage.py:16; tests/test_assay_hygiene_lineage.py:791 |
| `12,360` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:473; scripts/assay_hygiene/compatibility.py:476; scripts/assay_hygiene/compatibility.py:564 |
| `13,220` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:47; scripts/assay_hygiene/compatibility.py:52; tests/test_assay_hygiene_compatibility.py:590 |
| `52,184` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:30; scripts/assay_hygiene/lineage.py:45; tests/test_assay_hygiene_lineage.py:14 |
| `71,499` | 3 | **unverified** | not re-derived this session | scripts/assay_hygiene/dossier.py:29; scripts/assay_hygiene/dossier.py:31; scripts/assay_hygiene/dossier.py:32 |
| `122,011` | 3 | **correct** | claims naming an assay the sample already holds | scripts/assay_hygiene/classify.py:122; tests/test_assay_hygiene_classify.py:4085; tests/test_assay_hygiene_classify.py:4092 |
| `161,531` | 3 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/lineage.py:32; tests/test_assay_hygiene_lineage.py:16; tests/test_assay_hygiene_lineage.py:791 |
| `169,465` | 3 | **correct** | findings rows on an internal id | scripts/assay_hygiene/_schema.py:424; tests/test_assay_hygiene_mode2.py:598; tests/test_assay_hygiene_schema.py:147 |
| `430,490` | 3 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1168; tests/test_assay_hygiene_classify.py:1202; tests/test_assay_hygiene_classify.py:1273 |
| `1,058` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:880; tests/test_assay_hygiene_classify.py:4359 |
| `1,528` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:23; tests/test_assay_hygiene_backtest.py:14 |
| `1,578` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:360; tests/test_assay_hygiene_validation_sample.py:1186 |
| `1,656` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:596; tests/test_assay_hygiene_classify.py:2769 |
| `1,959` | 2 | **correct** | rows_no_mode | scripts/assay_hygiene/classify.py:139; tests/test_assay_hygiene_mode2.py:14 |
| `2,000` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:289; tests/test_assay_hygiene_schema.py:324 |
| `2,119` | 2 | **correct** | claim_rows; also claims whose term is under the support floor | tests/test_assay_hygiene_classify.py:2621; tests/test_assay_hygiene_classify.py:2625 |
| `3,001` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:988; scripts/assay_hygiene/classify.py:990 |
| `3,495` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:879; tests/test_assay_hygiene_classify.py:4358 |
| `4,054` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:188; tests/test_assay_hygiene_validation_sample.py:1181 |
| `4,609` | 2 | **STALE** | measures **4,553** (BLOCKED claims) | scripts/assay_hygiene/gate.py:69; scripts/assay_hygiene/_schema.py:751 |
| `5,424` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:38; scripts/assay_hygiene/backtest.py:468 |
| `5,437` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:375; tests/test_assay_hygiene_compatibility.py:1047 |
| `6,324` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:82; tests/test_assay_hygiene_classify.py:14 |
| `7,095` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:427; tests/test_assay_hygiene_mode2.py:600 |
| `8,131` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/extract.py:22; tests/test_assay_hygiene_extract.py:373 |
| `9,879` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:35; tests/test_assay_hygiene_lineage.py:796 |
| `10,163` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:94; tests/test_assay_hygiene_backtest.py:773 |
| `10,745` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:60; tests/test_assay_hygiene_validation_sample.py:284 |
| `11,720` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:94; tests/test_assay_hygiene_backtest.py:773 |
| `13,649` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:88; tests/test_assay_hygiene_backtest.py:766 |
| `14,753` | 2 | **correct** | samples carrying an unresolved term | scripts/assay_hygiene/run_evidence.py:453; tests/test_assay_hygiene_run_evidence.py:25 |
| `14,957` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/gate.py:440; tests/test_assay_hygiene_gate.py:325 |
| `19,165` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:38; scripts/assay_hygiene/backtest.py:468 |
| `24,322` | 2 | **correct** | unresolved term occurrences | scripts/assay_hygiene/run_evidence.py:452; tests/test_assay_hygiene_run_evidence.py:25 |
| `24,470` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:783; tests/test_assay_hygiene_mode2.py:256 |
| `27,344` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:1074; tests/test_assay_hygiene_classify.py:2492 |
| `29,763` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/dossier.py:54; scripts/assay_hygiene/review_verdicts.py:23 |
| `30,583` | 2 | **STALE** | measures **22,147** (claims both floors would block) | scripts/assay_hygiene/gate.py:172; scripts/assay_hygiene/_schema.py:750 |
| `31,180` | 2 | **correct** | rows_with_multiple_supports | scripts/assay_hygiene/_schema.py:356; tests/test_assay_hygiene_schema.py:167 |
| `41,282` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:188; tests/test_assay_hygiene_validation_sample.py:1181 |
| `43,604` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:31; tests/test_assay_hygiene_validation_sample.py:1178 |
| `52,185` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:43; scripts/assay_hygiene/_schema.py:807 |
| `52,235` | 2 | **correct** | rows with precedent_supports True | scripts/assay_hygiene/_schema.py:394; tests/test_assay_hygiene_mode2.py:540 |
| `57,946` | 2 | **correct** | n_child_only_samples summed over the 961 rules | scripts/assay_hygiene/precedent.py:196; scripts/assay_hygiene/_schema.py:103 |
| `76,869` | 2 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:150; tests/test_assay_hygiene_run_detect.py:826 |
| `82,663` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/stage0.py:522; tests/test_assay_hygiene_stage0.py:1040 |
| `85,104` | 2 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/stage0.py:112; tests/test_assay_hygiene_stage0.py:1212 |
| `90,470` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:60; scripts/assay_hygiene/validation_sample.py:186 |
| `95,469` | 2 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:151; tests/test_assay_hygiene_run_detect.py:826 |
| `104,440` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/run_detect.py:832; tests/test_assay_hygiene_run_detect.py:779 |
| `112,495` | 2 | **correct** | ADD_CHILD_TO_ASSAY findings rows | scripts/assay_hygiene/review_mode2.py:281; scripts/assay_hygiene/validation_sample.py:687 |
| `115,599` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:506; tests/test_assay_hygiene_lineage.py:923 |
| `115,626` | 2 | **correct** | lineage ceiling union_samples | scripts/assay_hygiene/lineage.py:504; scripts/assay_hygiene/mode2.py:478 |
| `153,309` | 2 | **correct** | test edges where a weak field predicts | scripts/assay_hygiene/run_evidence.py:578; tests/test_assay_hygiene_run_evidence.py:248 |
| `157,839` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/dossier.py:216; tests/test_assay_hygiene_review_mode2.py:294 |
| `162,370` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:424; tests/test_assay_hygiene_mode2.py:598 |
| `163,000` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/extract.py:273; tests/test_assay_hygiene_extract.py:348 |
| `163,379` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/review.py:200; tests/test_assay_hygiene_review.py:337 |
| `166,082` | 2 | **correct** | cascade test edges | scripts/assay_hygiene/run_evidence.py:577; tests/test_assay_hygiene_run_evidence.py:247 |
| `167,330` | 2 | **STALE** | measures **167,347** (neighbour-anchored rows) | scripts/assay_hygiene/classify.py:144; scripts/assay_hygiene/classify.py:149 |
| `171,013` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:506; tests/test_assay_hygiene_lineage.py:923 |
| `176,428` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/run_detect.py:299; scripts/assay_hygiene/run_detect.py:483 |
| `200,000` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/stage0.py:111; scripts/assay_hygiene/stage0.py:111 |
| `303,866` | 2 | **correct** | largest single rule, edges | scripts/assay_hygiene/precedent.py:190; scripts/assay_hygiene/_schema.py:100 |
| `742,534` | 2 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:28; tests/test_assay_hygiene_lineage.py:12 |
| `1,007` | 1 | **correct** | CLS_UNRESOLVED rows | scripts/assay_hygiene/classify.py:139 |
| `1,100` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:11 |
| `1,114` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_rulings.py:280 |
| `1,173` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:197 |
| `1,209` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_compatibility.py:1036 |
| `1,234` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:76 |
| `1,272` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/dossier.py:31 |
| `1,341` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:103 |
| `1,364` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/vocabulary.py:9 |
| `1,510` | 1 | **correct** | rows_proposed_by_both (ceiling grain) | tests/test_assay_hygiene_classify.py:2769 |
| `1,529` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:69 |
| `1,537` | 1 | **correct** | population_with_claim | tests/test_assay_hygiene_classify.py:2626 |
| `1,548` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:70 |
| `1,556` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/_schema.py:547 |
| `1,575` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/precedent.py:191 |
| `1,576` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:460 |
| `1,591` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:459 |
| `1,626` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:70 |
| `1,754` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_vocabulary.py:610 |
| `1,757` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:68 |
| `1,814` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:69 |
| `1,827` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:105 |
| `1,884` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:1093 |
| `2,074` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_backtest.py:193 |
| `2,131` | 1 | **STALE** | measures **2,119** (claims under the support floor) | scripts/assay_hygiene/gate.py:120 |
| `2,271` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/vocabulary_evidence.py:12 |
| `2,390` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:1093 |
| `2,408` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:984 |
| `2,827` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_compatibility.py:1036 |
| `2,869` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:68 |
| `2,906` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/dossier.py:332 |
| `3,392` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:187 |
| `3,487` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:115 |
| `3,571` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:110 |
| `3,574` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_vocabulary.py:609 |
| `3,663` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:2712 |
| `4,478` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:189 |
| `4,554` | 1 | **STALE** | measures **4,553** (GATE_UNREACHABLE claims) | scripts/assay_hygiene/gate.py:69 |
| `4,567` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:1010 |
| `4,628` | 1 | **correct** | Granuloma carriers registered in 74 | tests/test_assay_hygiene_run_evidence.py:482 |
| `4,629` | 1 | **correct** | Granuloma carriers | tests/test_assay_hygiene_run_evidence.py:482 |
| `4,705` | 1 | **correct** | population_no_claim | tests/test_assay_hygiene_classify.py:2626 |
| `4,901` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:190 |
| `4,977` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:111 |
| `4,998` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_vocabulary.py:245 |
| `5,008` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:4275 |
| `5,181` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:1114 |
| `5,214` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_compatibility.py:1056 |
| `5,752` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:988 |
| `6,188` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/run_detect.py:574 |
| `7,195` | 1 | **correct** | Blood-pattern peers | scripts/assay_hygiene/run_evidence.py:372 |
| `7,871` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | tests/test_assay_hygiene_stage0.py:1066 |
| `8,120` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_stage0.py:1020 |
| `8,127` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_stage0.py:1020 |
| `8,442` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/claims.py:162 |
| `8,657` | 1 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/classify.py:992 |
| `8,753` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:989 |
| `9,240` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1226 |
| `10,093` | 1 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/mode2.py:302 |
| `10,497` | 1 | **STALE** | measures **6,677** (claims passing on the representative row while another backing row would be rejected) | scripts/assay_hygiene/gate.py:643 |
| `10,642` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:53 |
| `10,782` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/compatibility.py:52 |
| `12,007` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:114 |
| `13,229` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_compatibility.py:588 |
| `13,560` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:113 |
| `17,625` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:114 |
| `17,720` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:102 |
| `20,000` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_stage0_apply.py:349 |
| `20,683` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:215 |
| `20,737` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:215 |
| `24,050` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_validation_sample.py:618 |
| `30,122` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_validation_sample.py:618 |
| `30,496` | 1 | **correct** | unseen-pair ADD_PARENT rows | scripts/assay_hygiene/_schema.py:332 |
| `32,793` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:60 |
| `33,954` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:115 |
| `34,910` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:187 |
| `36,090` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:61 |
| `40,000` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/vocabulary.py:90 |
| `42,867` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:60 |
| `45,410` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:189 |
| `50,857` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/validation_sample.py:190 |
| `55,057` | 1 | **correct** | the same at the SEEK assay grain | scripts/assay_hygiene/lineage.py:522 |
| `59,182` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/backtest.py:62 |
| `62,957` | 1 | **correct** | test edges where Type and Protocol agree | tests/test_assay_hygiene_run_evidence.py:249 |
| `68,005` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:723 |
| `71,337` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_run_detect.py:667 |
| `73,195` | 1 | **correct** | unseen-pair ADD_CHILD rows | scripts/assay_hygiene/_schema.py:333 |
| `79,488` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:2712 |
| `89,209` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/mode2.py:317 |
| `90,533` | 1 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/stage0.py:119 |
| `107,424` | 1 | **STALE** | measures **107,559** (GATE_PASS claims) | scripts/assay_hygiene/gate.py:68 |
| `115,104` | 1 | **correct** | rows with precedent_supports False | scripts/assay_hygiene/_schema.py:388 |
| `118,141` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:522 |
| `118,493` | 1 | **correct** | test edges where a strong field predicts | tests/test_assay_hygiene_run_evidence.py:246 |
| `133,398` | 1 | **STALE** | measures **126,211** (claims reaching a mode) | scripts/assay_hygiene/gate.py:70 |
| `161,451` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/lineage.py:222 |
| `163,816` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:60 |
| `166,427` | 1 | **historical** | prose scopes it to a superseded run, spec or plan; correct as stated | scripts/assay_hygiene/classify.py:992 |
| `166,586` | 1 | **unverified** | not re-derived this session | scripts/assay_hygiene/classify.py:987 |
| `171,145` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_lineage.py:925 |
| `179,848` | 1 | **correct** | curator-labelled test edges | tests/test_assay_hygiene_run_evidence.py:244 |
| `330,395` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1230 |
| `340,380` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1229 |
| `350,390` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1232 |
| `361,420` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:117 |
| `434,566` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_vocabulary.py:114 |
| `501,600` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1224 |
| `509,875` | 1 | **unmeasurable-here** | measured against a source outside this repo or a hold-out this sweep did not rerun | scripts/assay_hygiene/backtest.py:61 |
| `663,452` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:115 |
| `919,189` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:115 |
| `931,196` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_precedent.py:114 |
| `110,130,501,600` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1262 |
| `290,430,500,610` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1225 |
| `8,100,103,170,260` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1223 |
| `210,310,430,500,610` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1259 |
| `100,103,230,240,250,260,170` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1261 |
| `200,330,340,350,360,380,390` | 1 | **unverified** | not re-derived this session | tests/test_assay_hygiene_classify.py:1258 |

## Figures outside the census that this sweep did check

| site | figure | verdict | measured |
|---|---|---|---|
| `gate.py:68` | `55` GATE_INCOHERENT claims | **STALE** | **0** — `incoherent_families` returns `{}`; no family maps to two assays any more |
| `gate.py:70` | `3.3%` blocked | **STALE** | **3.5%** (4,553 / 130,764) |
| `gate.py:120` | `83` of 736 vocabulary rows under the support floor | **STALE** | **90** |
| `gate.py:132` | held-out accuracy `65.8%` / `88.1%` / `99.9%` by purity band | **STALE** | **68.1%** / **81.4%** / 99.9% (`evidence-report.md`, this run) |
| `gate.py:137` | `Type: Illumina Library` -> 24 at purity `0.707` | **MEANING-SHIFTED** | the term is retired: `internal_assay_id` NaN, support 0, purity 0.0 |
| `gate.py:793` | `flowjo 10.8.1` in a family splitting across 30, 31, 153 | **MEANING-SHIFTED** | all six `flowjo*` rows now carry NaN `internal_assay_id`; the family maps to nothing |
| `classify.py:1001` | `89%` of attached claims | **STALE** | **93%** (122,011 / 130,764) |
| `classify.py:1207` | `mode2_findings` at `eleven` arguments | **STALE** | **twelve** keyword-only, thirteen total |
| `classify.py:278` | `_SHARED_PAYLOAD` "names today's four members" | **correct** | 4 members |
| `mode2.py:699` | "at `thirteen` arguments" | **correct** | 13 total |
| `mode2.py:180` | `2` blocked-claim rows are `BY_LINEAGE_ONLY` | **correct** | 2 of 4,242 |
| `run_detect.py:250` | "Six of the `eleven` keys are counts and five are lists" | **correct** | 11 `INTEGRITY_KEYS`, 6 counts / 5 lists |
| `precedent.py:189` | `12.1x` fan-out ratio | **correct** | 666,939 / 55,032 = 12.1x |
| `precedent.py:191` | largest fan-out `1,575` edges over `3` samples | unverified | — |
| `precedent.py:211` | `8` of `270` hops move materially when regrained | **correct** (denominator) | 270 hops carry >= 50 forward edge observations |
| `gate.py:336` | `194` samples over `210` membership rows | **correct** | 194 / 210 |
| `_schema.py:388` | `115,104` / `744` / `17` | **correct** | all three |

## The single largest finding

`138,007` and `123,439` measure **130,764** and **122,011**. 27 occurrences on
24 lines across 7 files, **all prose** — `grep 138007\|123439` finds nothing
asserted, so no test guarded one of them. `123,439 / 138,007` was quoted as
"89% of attached claims" and is the largest single exclusion in stage C.

The cause is the operator's retirement of four vocabulary terms on 2026-08-21:
the claims frame shrank from 138,007 rows to 130,764, and **every numerator
quoted against it moved too** — which is why fixing only the denominator would
have been worse than leaving it alone. All eight of the gate's census figures
changed, and one of them (`GATE_INCOHERENT`, 55 -> 0) changed to zero, meaning
the gate's coherence test now fires on nothing at all.

## The `866` family — 20 occurrences, and it is a naming problem

`866` is increment 1's contradiction-flag count and every docstring scopes it
that way, correctly. But `classify.mode3_disposition` **re-derives that
population** through `audit.audit_contradictions`, and on this extract it
re-derives at **585**. The consequence is visible inside one artifact:
`detect-report.md` prints "increment 1's 866 flags" in the ceiling section and
"increment 1 raised 585 MODE_3 flags" in the precedence section, one screen
apart. Neither number is wrong; the label "increment 1's" on the 585 is.

**Not changed by this sweep.** It is a labelling decision about an operator-
facing artifact, and every `X of the 866` sub-figure (43 / 225 / 269 / 576 /
598 / 641 / 764 ...) would have to be re-derived against 585 to follow it
through. Recorded here so the next reader does not have to find it again.

## Step 3: should a test re-derive declared figures? No.

**Recommendation: do not build it.**

The reason 27 wrong figures survived is that no test reads them, and the obvious
fix is a test that extracts declared figures from docstrings and re-derives
them. Measured against this census, that fix costs more than the drift:

1. **260 distinct figures would need machine-readable annotation** — 793
   occurrences on 585 lines. Every one needs a marker naming the quantity it
   measures, because the prose form (`3,511 of the 138,007 claims fail a
   blocking test AND a floor`) is not mechanically resolvable to a computation.
2. **Only 58 of the 260 are re-derivable from the extract at all.** 18 are
   deliberately historical, 15 are measured against production Neo4j / the SEEK
   id space / operator rulings / hold-outs, and the rest are one-off readings
   whose defining query exists nowhere in the repo. A guard covering 22% of the
   population, annotated at 100% of the cost, teaches readers that an
   un-annotated figure is *trusted*, which is worse than today's honest
   uncertainty.
3. **The re-derivations are not cheap.** A full `run_evidence` + `run_detect`
   is minutes; several figures here (the representative-row hazard, the
   edge-grain candidate count) needed a bespoke pass over the whole extract.
   A guard doing that on every suite run either becomes a skipped test on any
   machine without the extract — which is where the suite already loses 9 —
   or it dominates the run.
4. **The drift has one dominant cause and it is episodic.** 25 of the 65 stale
   occurrences trace to a single event: four vocabulary terms retired on one
   day. A guard is the wrong instrument for an episodic, attributable shift;
   re-running this census is the right one, and it is one script.

**Instead:** this file is the guard. It is a dated census with a re-derivation
recipe at the top, and re-running it after any change that moves the claims
frame, the vocabulary, or the lineage index costs one pipeline run. The
extractor is 40 lines of `ast` + `tokenize`.

The one cheap mechanical guard worth keeping is the existing derived-integer
convention: figures a report *computes* are bolded and formatted with `:,` by
the writer, so they cannot go stale. Extending that to **prose** is the
proposal being declined; extending it to more *computed* report lines is free
and is where `run_detect.py:693` should have been in the first place.
