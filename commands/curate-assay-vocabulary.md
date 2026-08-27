---
description: Map unresolved metadata terms onto internal assays (assay hygiene, stage B2)
---

This is **stage B2 of the assay-hygiene mode**. It is house-scoped: one
extract, all projects, no PI. Run `curate-assay-init` first — this command
needs an open run, and every path below is relative to it. Set `RUN` once:

```bash
RUN=assets/RUN2      # this run's directory, never the default path
```

The user wants the unresolved tail of the assay vocabulary settled.

Every common metadata term was already mapped from curator-labelled edges and
carries a support count. What is left are terms no labelled edge anchors. Your
job is to propose a mapping for the ones you can justify, and to leave the rest
alone.

The size of the unresolved tail moves with the extract, so it is not quoted
here. Quoting a figure and then telling the reader to re-measure it is how the
wrong number gets copied forward -- this file previously carried 2026-08-14
counts under exactly that instruction. Measure yours before starting:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "
import pandas as pd
u = pd.read_csv('$RUN/04-artifacts/vocabulary-unresolved.csv')
print(f'{len(u):,} unresolved terms')
print(u.groupby('source_field').size().sort_values(ascending=False).to_string())
"
```

## Prereqs

- Run everything below from the directory holding `scripts/` and
  `assay-hygiene/`. Unlike the pipeline-mode commands this stage is not
  project-scoped; every path here is relative to that one root.
- `$RUN/04-artifacts/vocabulary-unresolved.csv` and `$RUN/04-artifacts/vocabulary.csv`
  exist. If either is missing or stale, regenerate both with:

  ```bash
  PYTHONPATH=scripts uv run --with pandas --with pyarrow \
    python -m assay_hygiene.run_evidence $RUN/01-extract $RUN/04-artifacts
  ```

  `PYTHONPATH=scripts` is not optional. Without it the package is not importable
  from this directory and the run dies with `ModuleNotFoundError: No module
  named 'assay_hygiene'`.

  That command is the end-to-end driver: it rebuilds the vocabulary, the
  unresolved queue, the precedent table, the claims, the Mode 3 flags and
  `evidence-report.md` in one read-only pass. Run it again after you write your
  proposals to see them merged.
- `$RUN/01-extract/` holds `assays.parquet` (137 internal assays),
  `membership.parquet`, `samples.parquet` and `nodes.parquet`.

One thing to not waste time on: `sops.parquet` is `(sop_id, title)` and nothing
else. Matching a Protocol filename against it hands back the same string and no
assay, so it cannot settle a single row here.

## Steps

### 1. Build the evidence table

`vocabulary-unresolved.csv` carries only a count and five example UIDs. The
decisive evidence is somewhere else: what the samples carrying a term are
actually **registered** in.

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow \
  python -m assay_hygiene.vocabulary_evidence $RUN/01-extract $RUN/04-artifacts
```

That writes `$RUN/04-artifacts/vocabulary-evidence.csv` and prints a summary.

The block below is a WORKED EXAMPLE from the 2026-08-14 extract, kept because
the shape of the answer is what matters here and the ratios are what you learn
to read. **These are not your run's numbers.** Compare against your own output,
never against these:

```
266 unresolved terms
  86 with no registered carrier
  120 whose registered carriers sit in exactly one internal assay
  60 with two or more candidate assays
  58 whose candidate is just the sample type's base rate
```

The last figure is not a fourth group; those 58 sit inside the two above it. So
membership is silent for a third of the queue, clean for 120 terms, and a chunk
of the confident-looking rows are confounded. Read the columns this way:

| column | what it tells you |
|---|---|
| `n_registered` | how many carriers are registered anywhere. `0` means membership says nothing at all; you are judging from text alone. |
| `n_candidate_assays` | `1` is a clean signal. `2+` means leave it unless something else separates them. |
| `share` | the candidate's share of registered carriers. |
| `base_rate` | the same assay's share among **all** registered samples of that sample type. |

`base_rate` is the one that stops you, and it means *membership is not evidence
here*, not *the answer is wrong*. Two rows sit at `share` 1.00 with a high
`base_rate` and resolve in opposite directions:

- `Protocol: 18032418`, 35 NHP samples, candidate 56 `Patient Visit`,
  `base_rate` 0.875. Rule 3 below: the answer is no assay at all.
- `Protocol: p.pqr-190110-v1_nx_sop_v1.zip;`, 799 TIS samples, candidate
  74 `Tissue Collection`, `base_rate` 0.998. But the same filename **without**
  the trailing `;` is already in `vocabulary.csv` at support 15,919 mapping to
  74. A stray delimiter split one term in two, and that, not membership, is
  what settles it.

So when `base_rate` is high, go find other evidence. Do not treat it as a
verdict either way.

### 2. Read the samples behind anything you intend to propose

`example_uuids` carries up to five UIDs per row. Pull their full
`json_metadata` out of `samples.parquet` and read it. A term is often
unambiguous once you see the instrument, the study and the protocol beside it,
and occasionally the metadata says outright that the term is not an assay at
all.

### 3. Write the proposals, then report

Per the Output section below. Write the file even if it holds two rows; an
honest short file is the deliverable, a padded long one is not.

## Rules

1. **Propose only what you can justify from evidence in front of you.** A term
   you cannot place is a valid outcome. Leave it out and say so.

2. **Never invent an `internal_assay_id`.** Every id must exist in
   `assays.internal_assay_id`. Check it. Today that column holds 137 ids, all in
   the range 1-188. `vocabulary.csv` also contains 14 rows carrying ids 466, 469,
   470, 471 and 472 with a **blank title**: those are not internal assay ids at
   all, they are seek `assays.id` values leaking through a missing junction row.
   A blank title is the tell. Never propose one.

3. **Ask whether the term or the sample type is doing the work.** Check
   `base_rate` before believing `share`. The live worked example: the 12
   bare-numeric Protocol values (18032418, 22010444, 22071552, 23012317,
   21048970, 17050656, 17029987, 15066174, 19014206, 24095281, 18052927,
   25036254) all sit at `share` 1.00 on internal assay 56 `Patient Visit`, which
   looks decisive. It is not. All 198 carrying samples are of type NHP, 87.5% of
   registered NHP samples are in `Patient Visit` regardless, and their metadata
   carries an NIH grant under `Funder` and a macaque under `Species` (149
   *M. fascicularis*, 49 *M. mulatta*). These are **animal-use (IACUC) protocol
   numbers**, not bench protocols. They name no assay.

   Record that as a ruling rather than as a silence: write all 12 with an
   **empty `internal_assay_id`**, per the "ruled: not an assay" note in the
   Output section. Omitting them instead leaves no record that anyone ever
   looked, and every future run puts the same 12 terms back in the queue.

   Do not over-read the batch as one lab's numbering: 174 of the 198 carriers
   are `Facility: Flynn Lab` and 24 are the NIH Vaccine Research Center, and
   term `23012317` is *entirely* VRC, 24 of 24. The conclusion holds for all 12,
   the single-institution inference does not.

4. **Match the house vocabulary, not English.** `cometchip` maps to `CometChip
   Assay` (id 138) because that is what this database calls it. Check
   `vocabulary.csv` for how similar terms were resolved by the data.

5. **String similarity is not evidence.** These two Protocol values are one day
   and one lab apart:

   | value | status | assay |
   |---|---|---|
   | `p.mno-190108-v1_in-vivo-comet-assay-protocol.docx` | unresolved, 2,271 samples | carriers unanimously registered in 138 `CometChip Assay` |
   | `p.mno-190109-v1_in-vivo-comet-chip---mus.docx` | already learned, support 31 | 14 `Chemical challenge` |

   Nearly identical strings, different assays. Let membership decide, never the
   filename.

6. **Beware the measurement-versus-analysis pair.** Nine assay titles are exactly
   `X` and `X Analysis`:

   | measurement | analysis |
   |---|---|
   | 25 Spectroscopy | 71 Spectroscopy Analysis |
   | 30 Flow Cytometry | 31 Flow Cytometry Analysis |
   | 36 Imaging | 118 Imaging Analysis |
   | 76 Western Blot | 184 Western Blot Analysis |
   | 89 Nuclear Magnetic Resonance Spectroscopy | 91 Nuclear Magnetic Resonance Spectroscopy Analysis |
   | 112 PET/CT Scan | 175 PET/CT Scan Analysis |
   | 130 Mass Spectrometry | 47 Mass Spectrometry Analysis |
   | 145 Histopathology | 187 Histopathology Analysis |
   | 179 CyTOF | 178 CyTOF Analysis |

   More carry the same distinction under different wording, so an `X Analysis`
   suffix search will miss them: 138 `CometChip Assay` against 185 `Comet Chip
   Analysis`, and 69 `Spatial Proteomics` against 2 `Analyzed Spatial
   Proteomics`, where the qualifier is a prefix rather than a suffix. These are
   different assays with different memberships. If a term
   could be either and membership does not separate them, leave it unresolved
   and note the ambiguity. Do not guess.

7. **A proposal cannot make Mode 3 see less, and will rarely make it see more.**
   Both halves are design, not luck. The design is the claims and audit sections
   of the assay-hygiene evidence-layer plan under `docs/superpowers/plans/`, as
   amended in `bc0bbe0`. Read it there rather than trusting a summary here.

   Two properties of that design govern what your file can do:

   - **Suppression is impossible by construction.** Each claim is tiered on the
     evidence backing its own assay, and disagreement is recorded in a
     `contested` column instead of a tier that swallows both claims. Adding a
     claim therefore cannot lower another claim's tier. An earlier design did
     collapse disagreeing samples below the audit floor, and adding proposals
     measurably removed 102 existing flags while adding 13; that is why this one
     exists. Nothing you write can delete a flag.
   - **A proposal is excluded from tiering entirely**, whatever field carried
     it, and the audit floor is `corroborated` / `strong`. So a proposal cannot
     raise ANY claim to the floor -- not a proposal-only one, and not one that
     agrees with existing evidence. `Type` being a strong field does not buy
     your guess the strong tier.

   Both properties rest on your `provenance` column being read correctly, and
   until 2026-08-15 it was not: the two rules tested `!= proposed`, so writing
   `Proposed`, `PROPOSED` or anything else unrecognised made your row count as
   evidence -- crossing the audit floor and contesting real claims, which
   *would* have deleted flags. They now test membership of `{learned, curator}`
   and the loader rejects a provenance it does not recognise. Rule 9 still
   applies: write `proposed`, exactly.

   Measured on the 2026-08-14 extract, adding proposals for all 180 terms that
   have a candidate: **0 flags added, 0 removed**, at all four audit settings
   (866 at the shipped defaults, 1,556 admitting contested rows, 879 admitting
   unmappable registrations, 1,570 admitting both). The 180 proposals add 8,442
   new `weak` claims and change **no existing claim's tier at all**, so the
   0 / 0 is structural rather than a lucky selection: any subset of them gives
   the same answer, because `weak` is below the floor and a proposal can never
   enter the contest.

   That cap is the only thing buying the zero. Lift it and nothing else, leaving
   the contest rule and the audit floor exactly as they are, and the same 180
   proposals raise **10 flags** at the shipped defaults (866 -> 876). The
   often-quoted "+23" is the same experiment read at `include_unmappable=True`
   (879 -> 902), which was the default before Task 7 added that exclusion; 13 of
   those 23 are the unmappable rows the audit now refuses on identity grounds.
   Either way, grading a guess by the field that carried it buys false
   positives and nothing else.

   So the corollary is the whole of it: **a proposal derived from the membership
   of a term's own carriers cannot flag those carriers, because it was built to
   agree with them. Its value is coverage, not detection.** Judge your file on
   whether the mappings are right, never on what Mode 3 does afterwards.

8. **Copy `raw_value` byte for byte.** The values in
   `vocabulary-unresolved.csv` are already normalised (lowercased, whitespace
   collapsed) by `_schema.normalise_value`. The merge keys on that exact string,
   so re-casing or trimming one silently creates a second term that never
   matches anything. Quote every value in the csv, including the bare-numeric
   ones: `merge_vocabulary` raises rather than silently deleting a key that is
   not text, but the fix is to write text in the first place.

9. **You are proposing, not deciding.** Everything you write lands with
   `provenance = proposed`, below `learned` and `curator` in precedence, and a
   curator can overrule it. Say plainly in your summary which proposals you are
   confident in and which are weak.

## Output

Write `$RUN/04-artifacts/vocabulary-proposed.csv` with exactly these columns:

    source_field,raw_value,internal_assay_id,internal_assay_title,support,n_samples,purity,provenance

- `source_field` and `raw_value` copied verbatim from the unresolved file
- `internal_assay_id` and `internal_assay_title` from `assays.parquet`
- `support` = 0, `n_samples` = 0 and `purity` = 0.0. These are **defined against
  curator-labelled edges** and a proposal has none, so writing a membership count
  into them would make the column mean two things in one file. Do not fabricate
  them; the zeros are what distinguishes your rows from learned ones.
- `provenance` = `proposed`, spelled exactly that way. The loader normalises
  case and surrounding whitespace and **rejects** anything it still does not
  recognise, so a typo stops the run with a message naming the row rather than
  quietly changing how far your row is trusted.

### Ruling that a term is not an assay

Leave `internal_assay_id` and `internal_assay_title` **empty** and write the row
anyway. That is a real, supported state, and it is the only way to record the
ruling:

- the row survives the merge and stays in `vocabulary.csv`, so the decision is
  durable and visible;
- it produces no claim, so nothing can be flagged off it;
- and the term leaves `vocabulary-unresolved.csv`, so nobody is asked to rule on
  it again.

Omitting the term instead does none of these: it comes back in every future
queue, indistinguishable from a term nobody has looked at yet. Rule 3's 12 IACUC
protocol numbers are the live case. Pinned by
`test_a_null_id_row_is_a_working_ruled_not_an_assay_state`.

`vocabulary-evidence.csv` is a working file for this command, not a contract.
Nothing downstream reads it.

Then report:

- how many terms you mapped and how many you left, with the reason for the
  biggest groups you left
- the specific proposals you were least sure about
- how many of your proposals sit on terms the evidence table reports with two or
  more candidate assays. Rule 6 says leave those; if you proposed any anyway,
  say which and why. Mode 3 will not catch it for you (rule 7).
