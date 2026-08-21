# The pre-rework baseline: the output as it stood on 2026-08-21

Every row-impact claim in `docs/superpowers/plans/2026-08-21-assay-hygiene-mode2-generation-rework.md`
is measured against this table.

Both audits of 2026-08-21 found stale figures inside documents whose subject was
stale figures. This table is the defence: it is derived by a script that is
committed beside it, so a later task claiming a row delta can be held to a
number that was measured rather than quoted.

## The table

| key | rows |
|---|---|
| `rows` | 170,786 |
| `rows_mode_1` | 1,373 |
| `rows_mode_2` | 167,454 |
| `rows_no_mode` | 1,959 |
| `mode2_unreachable` | 99,449 |
| `mode2_reachable` | 68,005 |
| `mode2_without_a_gate_outcome` | 166,586 |
| `by_precedent_with_no_coregistration` | 115,087 |
| `rows_with_a_fallback_namespace_id` | 1,321 |

## The command that produced it

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -m assay_hygiene.baseline
```

Run from the repository root on 2026-08-21, against the defaults compiled into
`baseline.main`: `assay-hygiene-bak/artifacts/findings.csv` and
`assay-hygiene-bak/extract`. `assay-hygiene/` is a tree of symlinks into
`assay-hygiene-bak/`, so `assay-hygiene/findings.csv` and `assay-hygiene/extract`
reach the same bytes.

## What was measured, and when

`findings.csv` is 106,206,399 bytes and 170,786 rows. The extract is the eight
parquet frames in `assay-hygiene-bak/extract/`; `samples.parquet` holds 163,393
rows and `assays.parquet` 458, naming 137 distinct genuine `internal_assay_id`
values.

**The extract's own run date is not recorded anywhere in the artifact tree.**
Two things about it can be derived, and neither is that date:

- the newest sample it contains was created `2026-08-06 16:00:02`
  (`samples.created_at.max()`), so the extract was taken no earlier than that;
- every file in `assay-hygiene-bak/extract/` carries mtime
  `2026-08-21 12:34:12`, to the same fraction of a second across all eight —
  that is when the tree was copied into the backup, not when the extract ran.

## Three identities that hold at this baseline

None of the three is asserted by `baseline.py` against the real frame, and all
three were checked by hand when the table was taken. They are recorded because
each can fail SILENTLY — the table would still print nine plausible rows while
quietly not accounting for part of the frame — and because the rework changes
exactly the population they cover:

- `rows_mode_1 + rows_mode_2 + rows_no_mode == rows` (1,373 + 167,454 + 1,959 =
  170,786). The `mode` column holds exactly three values here: `MODE_2`,
  `MODE_1`, and null. A fourth value would vanish from all three buckets.
- `mode2_unreachable + mode2_reachable == rows_mode_2` (99,449 + 68,005 =
  167,454). No Mode 2 row has a null `type_registrations`; one that did would be
  counted as neither reachable nor unreachable.
- **`by_precedent_with_no_coregistration` counts only rows whose
  `precedent_n_both` is actually zero, never rows where it is null.** The
  expression is `(f.proposed_by == "BY_PRECEDENT") & (f.precedent_n_both == 0)`,
  and `NaN == 0` is `False`, so a `BY_PRECEDENT` row carrying a blank
  `precedent_n_both` is excluded rather than counted. **Today that exclusion
  removes 0 rows**, so the figure of 115,087 is unaffected. But the column is
  `float64` and 3,447 of the 170,786 rows already carry a blank
  `precedent_n_both` — none of them `BY_PRECEDENT`, which is the only reason the
  exclusion is empty. The rework can produce such rows, and if it does this
  count will quietly under-report.

Whoever re-runs `baseline.py` against post-rework output should re-check all
three before comparing tables — for the third, compare
`(proposed_by == "BY_PRECEDENT") & precedent_n_both.isna()` against 0.
`baseline.py` deliberately does not abort on any of them, because the rework may
legitimately change what these columns contain and an abort would break the very
comparison the script exists to enable. The computation is left as it is: it
counts what it names, and it is this document that was incomplete.

`tests/test_assay_hygiene_baseline.py` asserts the first two identities, and a
hand-computed value for each of the nine keys, against a synthetic fixture. That
guards the arithmetic in `measure` — a swap of the `== 0` and `> 0` expressions
is a red — but it says nothing about any real frame, which is why the hand
checks above are recorded here as figures rather than delegated to the suite.

## What this is not

Not a test and not a contract. It is a photograph. Nothing here authorises a
write, and no figure in it is a threshold.
