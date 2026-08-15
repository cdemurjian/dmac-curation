---
description: Map unresolved metadata terms onto internal assays (assay hygiene, stage B2)
---

The user wants the unresolved tail of the assay vocabulary settled.

Every common metadata term was already mapped from curator-labelled edges and
carries a support count. What is left are terms no labelled edge anchors. Your
job is to propose a mapping for the ones you can justify, and to leave the rest
alone.

Measured on the 2026-08-14 extract: **266 unresolved terms over 14,753 distinct
samples**, 9.0% of 163,393. By field: Protocol 103, Type 83, Instrument 24,
Software 23, DataType 11, SlideStain 8, Stimulation 7, Channels 6, Assay 1.
Re-measure rather than quoting those; they move with the extract.

## Prereqs

- Run everything below from the directory holding `scripts/` and
  `assay-hygiene/`. Unlike the pipeline-mode commands this stage is not
  project-scoped; every path here is relative to that one root.
- `assay-hygiene/vocabulary-unresolved.csv` and `assay-hygiene/vocabulary.csv`
  exist. If either is missing or stale, regenerate both with:

  ```bash
  PYTHONPATH=scripts uv run --with pandas --with pyarrow \
    python -m assay_hygiene.run_evidence
  ```

  `PYTHONPATH=scripts` is not optional. Without it the package is not importable
  from this directory and the run dies with `ModuleNotFoundError: No module
  named 'assay_hygiene'`. A failure naming `assay_hygiene.run_evidence`
  specifically is a different thing: that module is the end-to-end driver and
  arrives with Task 8, so until then regenerate with the stage B2 snippet in
  the plan instead.
- `assay-hygiene/extract/` holds `assays.parquet` (137 internal assays),
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
  python -m assay_hygiene.vocabulary_evidence
```

That writes `assay-hygiene/vocabulary-evidence.csv` and prints a summary. On the
2026-08-14 extract:

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
- `Protocol: p.fly-240924-v1_nx_flynn_sop_v1.zip;`, 799 TIS samples, candidate
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
   numbers**, not bench protocols. They name no assay. Leave all 12 unresolved
   and say why.

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
   | `p.eng-230912-v1_in-vivo-comet-assay-protocol.docx` | unresolved, 2,271 samples | carriers unanimously registered in 138 `CometChip Assay` |
   | `p.eng-230913-v1_in-vivo-comet-chip---mus.docx` | already learned, support 31 | 14 `Chemical challenge` |

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
   - **A proposal-only claim is capped at `weak` whatever field carried it**,
     and the audit floor is `corroborated` / `strong`. So a term you propose
     that no other evidence names cannot raise a flag either. `Type` being a
     strong field does not buy your guess the strong tier.

   Measured on the 2026-08-14 extract, rebuilding the amended Tasks 5 and 7 and
   adding proposals for all 180 terms that have a candidate: **0 flags added, 0
   removed**, at both audit settings (879 excluding contested rows, 1,570
   including them). Every proposal-selection variant in rule 6's range gives the
   same 0 / 0.

   The one way a proposal reaches the audit at all: if it names the **same**
   assay as an existing evidence-backed claim, it is no longer proposal-only, so
   the cap lifts and the claim can rise from `weak` to `corroborated` and cross
   the floor. 100 claims move that way here, and none of them contradicts its
   sample's registration, so the measured effect is still zero. That is a
   measurement, not a guarantee.

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

Write `assay-hygiene/vocabulary-proposed.csv` with exactly these columns:

    source_field,raw_value,internal_assay_id,internal_assay_title,support,n_samples,purity,provenance

- `source_field` and `raw_value` copied verbatim from the unresolved file
- `internal_assay_id` and `internal_assay_title` from `assays.parquet`
- `support` = 0, `n_samples` = 0 and `purity` = 0.0. These are **defined against
  curator-labelled edges** and a proposal has none, so writing a membership count
  into them would make the column mean two things in one file. Do not fabricate
  them; the zeros are what distinguishes your rows from learned ones.
- `provenance` = `proposed`

`vocabulary-evidence.csv` is a working file for this command, not a contract.
Nothing downstream reads it.

Then report:

- how many terms you mapped and how many you left, with the reason for the
  biggest groups you left
- the specific proposals you were least sure about
- how many of your proposals sit on terms the evidence table reports with two or
  more candidate assays. Rule 6 says leave those; if you proposed any anyway,
  say which and why. Mode 3 will not catch it for you (rule 7).
