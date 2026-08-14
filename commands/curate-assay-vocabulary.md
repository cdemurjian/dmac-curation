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

- `assay-hygiene/vocabulary-unresolved.csv` and `assay-hygiene/vocabulary.csv`
  exist. If either is missing or stale, regenerate both with
  `uv run --with pandas --with pyarrow python -m assay_hygiene.run_evidence`,
  or with the snippet in the plan's stage B2 step if that module is not built yet.
- `assay-hygiene/extract/` holds `assays.parquet` (137 internal assays),
  `membership.parquet`, `samples.parquet` and `nodes.parquet`.
- Run everything below from the directory holding `scripts/` and
  `assay-hygiene/`. Unlike the pipeline-mode commands this stage is not
  project-scoped; every path here is relative to that one root.

One thing to not waste time on: `sops.parquet` is `(sop_id, title)` and nothing
else. Matching a Protocol filename against it hands back the same string and no
assay, so it cannot settle a single row here.

## Steps

### 1. Build the evidence table

`vocabulary-unresolved.csv` carries only a count and five example UIDs. The
decisive evidence is somewhere else: what the samples carrying a term are
actually **registered** in. Build that table first, and judge from it.

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import sys, collections; sys.path.insert(0, "scripts")
import pandas as pd
from assay_hygiene import vocabulary as V, _schema as S

d = "assay-hygiene/extract"
samples    = pd.read_parquet(f"{d}/samples.parquet")
assays     = pd.read_parquet(f"{d}/assays.parquet")
membership = pd.read_parquet(f"{d}/membership.parquet")
nodes      = pd.read_parquet(f"{d}/nodes.parquet")
meta = V.parse_metadata(samples)
tail = pd.read_csv("assay-hygiene/vocabulary-unresolved.csv",
                   keep_default_na=False, na_values=[""],
                   dtype={"source_field": str, "raw_value": str})

# sample -> the INTERNAL assay ids it is registered in, plus its sample type.
# membership.assay_id is a seek id and NOT an internal_assay_id; the join
# through assays.parquet is what converts one space into the other.
a2i = {int(r.assay_id): (int(r.internal_assay_id), r.internal_assay_title)
       for r in assays.itertuples() if pd.notna(r.internal_assay_id)}
reg = collections.defaultdict(set)
for sid, aid in zip(membership.sample_id, membership.assay_id):
    hit = a2i.get(int(aid))
    if hit:
        reg[int(sid)].add(hit)
stype = {int(s): t for s, t in zip(nodes.sample_id, nodes.type) if pd.notna(s)}

def winner(counter):
    """Most frequent key, ties broken by the key itself.

    `Counter.most_common` breaks ties by insertion order, and these counters are
    filled by iterating SETS of tuples, whose order is PYTHONHASHSEED-dependent.
    Measured: the same run reported 58, 59 and 61 confounded terms three times
    in a row before this was pinned. Judgment built on a table that changes
    between runs is not reviewable.
    """
    if not counter:
        return (None, None), 0
    return max(counter.items(), key=lambda kv: (kv[1], str(kv[0])))

# base rate: what each sample TYPE is registered in anyway, term ignored
base, seen_type = collections.defaultdict(collections.Counter), collections.Counter()
for sid, t in stype.items():
    if reg.get(sid):
        seen_type[t] += 1
        for x in sorted(reg[sid]):
            base[t][x] += 1

want = {(r.source_field, r.raw_value) for r in tail.itertuples()}
carry = collections.defaultdict(list)
for sid, m in meta.items():
    for f in S.CLAIM_FIELDS:
        v = S.normalise_value(m.get(f))
        if v and (f, v) in want:
            carry[(f, v)].append(sid)

rows = []
for r in tail.itertuples():
    ids = carry[(r.source_field, r.raw_value)]
    c = collections.Counter()
    for sid in ids:
        for x in sorted(reg.get(sid, ())):
            c[x] += 1
    nreg = sum(1 for sid in ids if reg.get(sid))
    types = collections.Counter(stype.get(s) or "?" for s in ids)
    top_t = winner(types)[0]
    (tid, ttl), n = winner(c)
    rows.append({
        "source_field": r.source_field, "raw_value": r.raw_value,
        "n_samples": r.n_samples,
        "sample_types": ";".join(f"{k}:{v}" for k, v in sorted(
            types.items(), key=lambda kv: (-kv[1], str(kv[0])))[:3]),
        "n_registered": nreg, "n_candidate_assays": len(c),
        "cand_id": tid, "cand_title": ttl,
        "share": round(n / nreg, 3) if nreg else 0.0,
        "base_rate": round(base[top_t][(tid, ttl)] / seen_type[top_t], 3)
                     if top_t and seen_type[top_t] and tid else 0.0,
        "example_uuids": r.example_uuids,
    })
ev = pd.DataFrame(rows).sort_values(
    ["n_samples", "source_field", "raw_value"], ascending=[False, True, True])
ev.to_csv("assay-hygiene/vocabulary-evidence.csv", index=False)
print(f"{len(ev)} unresolved terms")
print(f"  {int((ev.n_registered == 0).sum())} with no registered carrier")
print(f"  {int(((ev.n_candidate_assays == 1) & (ev.n_registered > 0)).sum())} "
      "whose registered carriers sit in exactly one internal assay")
print(f"  {int((ev.n_candidate_assays > 1).sum())} with two or more candidates")
print(f"  {int(((ev.share >= 0.9) & (ev.base_rate >= 0.9)).sum())} whose "
      "candidate is just the sample type's base rate")
PY
```

On the 2026-08-14 extract that prints 266 / 89 / 120 / 57 / 59, byte-identical
across runs. So membership is silent for a third of the queue and clean for
under half of it. The last figure is not a fourth group: 59 rows spread across
the other two (48 of the 120, 11 of the 57) only look decisive. Read the columns
this way:

| column | what it tells you |
|---|---|
| `n_registered` | how many carriers are registered anywhere. `0` means membership says nothing at all; you are judging from text alone. |
| `n_candidate_assays` | `1` is a clean signal. `2+` means pick from the evidence or leave it. |
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
   reads `Species: Macaca fascicularis`, `Facility: Flynn Lab`, an NIH grant
   under `Funder`. These are **animal-use (IACUC) protocol numbers**, not bench
   protocols. They name no assay. Leave all 12 unresolved and say why.

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

6. **Beware the measurement-versus-analysis pair.** Ten assay titles are exactly
   `X` and `X Analysis` (25/71 Spectroscopy, 30/31 Flow Cytometry, 36/118
   Imaging, 69/2 Spatial Proteomics, 76/184 Western Blot, 89/91 NMR, 112/175
   PET/CT, 130/47 Mass Spectrometry, 145/187 Histopathology, 179/178 CyTOF), and
   more are near-pairs under different wording (138 `CometChip Assay` against 185
   `Comet Chip Analysis`). These are different assays with different memberships.
   If a term could be either and membership does not separate them, leave it
   unresolved and note the ambiguity. Do not guess.

7. **Know what a weak-field proposal does.** `Protocol` and `DataType` are
   `WEAK_FIELDS`. A weak claim alone lands in tier `weak`, which the Mode 3 audit
   never reads, so it can never raise a flag on its own. Worse, a weak proposal
   that names a *different* assay from a sample's existing strong claim turns
   that sample's tier into `conflict`, which the audit also never reads, and an
   existing flag disappears. Simulated over all 266 terms at once, proposing each
   term's majority-registered assay yields **10 new Mode 3 flags and removes
   190**, net minus 180, spread over 8 terms. So a proposal is not free, and "it
   agreed with membership" is not a defence.

   The corollary is worth saying plainly: a proposal derived from the membership
   of a term's own carriers cannot flag those carriers, because it was built to
   agree with them. Its value is coverage, not detection.

8. **Copy `raw_value` byte for byte.** The values in
   `vocabulary-unresolved.csv` are already normalised (lowercased, whitespace
   collapsed) by `_schema.normalise_value`. The merge keys on that exact string,
   so re-casing or trimming one silently creates a second term that never
   matches anything. Quote every value in the csv, including the bare-numeric
   ones: `merge_vocabulary` now raises rather than silently deleting a key that
   is not text, but the fix is to write text in the first place.

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

`vocabulary-evidence.csv` is a scratch file for this command, not a contract.
Nothing downstream reads it.

Then report:

- how many terms you mapped and how many you left, with the reason for the
  biggest groups you left
- the specific proposals you were least sure about
- the Mode 3 consequence: how many of your proposals sit on weak fields, and
  whether any of them contradicts a strong claim on a sample that is already
  registered somewhere (rule 7). If you cannot tell, say so rather than
  implying the proposals are inert.
