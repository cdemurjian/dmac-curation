# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Learn which assay a metadata value names, from what curators actually did.

Free text like `cometchip` has to become `internal_assay_id 138` before any
claim can be compared with a registration. That mapping is not guesswork: it is
observed in 1,364 curator-labelled edges. This module derives it from the
labelled population, scores it on held-out samples, and leaves only the
unanchored tail for a human or a model to settle.

Ground truth here is a labelled edge, meaning one where a curator's own
registration caused `internal_assay_id` to be written. Dark edges are excluded
deliberately: a dark edge is the defect this project exists to fix, and learning
from it would launder that defect into the vocabulary as though someone had
asserted it.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pandas as pd

from . import _schema as S


def parse_metadata(samples: pd.DataFrame) -> dict[int, dict]:
    """sample_id -> its parsed json_metadata, skipping blobs that do not parse.

    An unparseable blob reads as "no metadata" rather than raising: it is a data
    defect on one row and must not stop a run over 163,393 samples. It is not
    silently dropped either -- the sample is simply absent from the index, which
    every caller treats as "claims nothing".
    """
    out: dict[int, dict] = {}
    for sid, blob in zip(samples.sample_id, samples.json_metadata):
        if not blob:
            continue
        try:
            d = json.loads(blob)
        except (ValueError, TypeError):
            continue
        if isinstance(d, dict):
            out[int(sid)] = d
    return out


def _tally(edges: pd.DataFrame, meta: dict[int, dict], keep) -> tuple[dict, dict]:
    """Two views of one walk, both keyed by (field, normalised value).

    The Counter is EDGE-weighted -- how many labelled edges named each assay --
    and is what `support`, `purity` and every measured figure in this design are
    defined against. The set of child sample ids is that same evidence counted
    the other way, and it is the only thing separating a term backed by many
    curators from one backed by a single heavily fanned-out sample.
    """
    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    samples: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    for child_id, iaid in zip(edges.child_id, edges.edge_internal_assay_id):
        if pd.isna(iaid):
            continue                      # dark: not ground truth, see module docstring
        child_id = int(child_id)
        if not keep(child_id):
            continue
        d = meta.get(child_id)
        if not d:
            continue
        for field in S.CLAIM_FIELDS:
            value = S.normalise_value(d.get(field))
            if value:
                tally[(field, value)][int(iaid)] += 1
                samples[(field, value)].add(child_id)
    return tally, samples


def learn_vocabulary(
    edges: pd.DataFrame,
    meta: dict[int, dict],
    min_support: int = 3,
) -> pd.DataFrame:
    """Derive the (field, value) -> internal assay mapping from labelled edges.

    `support` is how many labelled EDGES back the mapping and `purity` is the
    winning assay's share of them. Both are carried so a reader can tell a term
    seen 40,000 times at 0.99 from one seen 3 times at 0.67 -- a distinction the
    mapping alone destroys.

    `n_samples` is the check on `support`, and reading support without it is the
    trap. A sample fans out to many edges, so support cannot distinguish a term
    backed by 132 curator-labelled samples from one backed by a single sample
    with 132 edges; on the real extract 50 of 736 learned terms are the latter,
    `Software: matlab` and `Type: github` among them. `min_support` still counts
    edges on purpose -- every figure this design rests on was measured that way,
    so changing it would invalidate the measurement rather than improve it. The
    column makes the weakness legible without moving a number.
    """
    rows = []
    tally, samples = _tally(edges, meta, lambda _: True)
    for (field, value), counter in tally.items():
        total = sum(counter.values())
        if total < min_support:
            continue
        best, best_n = counter.most_common(1)[0]
        rows.append({
            "source_field": field,
            "raw_value": value,
            "internal_assay_id": best,
            "internal_assay_title": None,   # filled by merge_vocabulary from assays
            "support": total,
            "n_samples": len(samples[(field, value)]),
            "purity": best_n / total,
            "provenance": S.P_LEARNED,
        })
    return pd.DataFrame(rows, columns=S.VOCAB_COLUMNS)


def score_vocabulary(
    edges: pd.DataFrame,
    meta: dict[int, dict],
    min_support: int = 3,
) -> pd.DataFrame:
    """Learn on half the samples, predict the other half, report per field.

    The split is BY SAMPLE (`sample_id % 2`), not by edge. A sample fans out to
    many edges -- 146 parents per child in the largest block -- so an
    edge-level split puts the same sample on both sides and scores memorised
    answers rather than generalisation.

    Metadata VALUES are deliberately shared across the split. Aligning a
    vocabulary once and applying it everywhere is the production behaviour; it
    is specific samples that must not leak.
    """
    train, _ = _tally(edges, meta, lambda sid: sid % 2 == 0)
    mapping = {
        k: c.most_common(1)[0][0]
        for k, c in train.items() if sum(c.values()) >= min_support
    }

    per_field: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for child_id, iaid in zip(edges.child_id, edges.edge_internal_assay_id):
        if pd.isna(iaid):
            continue
        child_id = int(child_id)
        if child_id % 2 == 0:
            continue                       # train side
        d = meta.get(child_id) or {}
        for field in S.CLAIM_FIELDS:
            slot = per_field[field]
            slot[2] += 1                   # every test-side edge counts for coverage
            value = S.normalise_value(d.get(field))
            pred = mapping.get((field, value)) if value else None
            if pred is None:
                continue
            if pred == int(iaid):
                slot[0] += 1
            else:
                slot[1] += 1

    rows = []
    for field, (hit, miss, seen) in per_field.items():
        covered = hit + miss
        terms = sum(1 for f, _ in mapping if f == field)
        rows.append({
            "source_field": field,
            "terms": terms,
            "coverage": covered / seen if seen else 0.0,
            "accuracy": hit / covered if covered else 0.0,
        })
    return pd.DataFrame(rows, columns=["source_field", "terms", "coverage", "accuracy"])


# Precedence, lowest to highest. A curator's decision outranks the data, and
# the data outranks a model's proposal. Encoded as a sort key rather than as
# branching so adding a fourth source later is one line.
_PRECEDENCE = {S.P_PROPOSED: 0, S.P_LEARNED: 1, S.P_CURATOR: 2}


def merge_vocabulary(
    learned: pd.DataFrame,
    proposed: pd.DataFrame,
    curator: pd.DataFrame,
    assays: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (field, value), highest-precedence source winning.

    `proposed` and `curator` accept None, so this works before Task 4 has ever
    run and produced either file.

    `raw_value` is normalised before the dedup key is taken. Without that, a
    curator row spelled `CometChip` and a learned row spelled `cometchip` are
    two different terms: both survive the merge, and every consumer -- which
    looks up the NORMALISED metadata value -- finds the learned row and never
    sees the curator's override. The failure is total and silent, so the
    normalisation belongs here, on the key itself, and not only in the
    consumers that happen to remember to normalise.

    That normalisation can also DESTROY a key -- `normalise_value` returns None
    for a non-str -- so this function RAISES on a raw_value that normalises to
    None rather than deduping it away. See the assertion below for why an
    in-memory frame needs that guard even though `load_vocabulary` pins dtypes.

    Display titles are rebuilt from the assays frame WHERE THAT FRAME HAS ONE,
    so a stale title in a hand-edited file cannot travel onward. Where it has
    none, the row keeps whatever title it already carried. Both halves matter:
    rebuilding is right when there is an authoritative source to rebuild from,
    and wrong when there is not, because vocabulary.csv exists to be
    hand-corrected and an unconditional rebuild silently discards the only
    title those rows will ever have. The evidence columns (`support`,
    `n_samples`, `purity`) travel untouched from whichever row wins: a merge is
    a choice between rows, never a recount.

    A BLANK title is therefore a real finding, not a lookup bug. Measured
    2026-08-14 on the extract, 14 of 736 rows come back untitled, all pointing
    at one of 5 ids (466, 469, 470, 471, 472) that are absent from
    `assays.internal_assay_id` because those assays have no row in
    `dmac.assays_internal_assays`. neo4j_sync.py:1418-1431 (v4-stable-wt;
    944-957 in NExtSEEK/dev-v3-merge) falls back to writing the seek
    `(assay_id, title)` pair into the edge's internal-assay fields for exactly
    those 17 junction-less assays, so `edge_internal_assay_id` -- and therefore
    the learned `internal_assay_id` -- carries a seek assays.id on those rows,
    in a different id space from every other row.

    Titling them off `assays.assay_id` would fill the blanks with the right
    strings and be the wrong call twice over. It would hide the missing junction
    row, which is a hygiene defect of precisely the kind this package exists to
    surface; and it would key a lookup on a column that collides -- 124 of the
    458 seek assay_ids equal a genuine internal_assay_id, and 122 of those 124
    name a DIFFERENT assay (seek 13 `Short Read Sequencing` against internal 13
    `Cell Sorting`, seek 24 `Single Cell Clustering Analysis` against internal 24
    `DNA Extraction`; only ids 47 and 74 happen to agree). Today's junction-less
    block happens to sit at 466-482, above
    the 1-188 internal range, and that accident is the only thing keeping such a
    fallback from returning another assay's title. The fix belongs upstream, in
    the junction table. A test guards this; see
    test_a_junction_less_id_is_never_titled_from_the_seek_assays_frame.

    The sort is explicitly STABLE, which is what makes "the last row for a key
    wins" a real rule rather than an accident. Precedence separates the three
    sources but says nothing about two rows from the SAME source, and one
    source -- the hand-edited curator file -- is exactly where a repeated key
    should be expected: the natural way to correct a csv is to append the new
    row, not to hunt down the old one. pandas' default kind is quicksort and is
    not stable; measured on pandas 3.0.5, 5,000 rows ranked over {0,1,2} had it
    hand drop_duplicates(keep="last") the FIRST row where a stable sort handed
    it the last. So the default does not leave the winner unspecified, it
    usually discards the curator's newest decision, and silently -- the losing
    row leaves no trace in the output to notice.
    """
    # `pd.notna(t)` is not redundant with `pd.notna(i)`. An assays row with a
    # real internal_assay_id but a NULL title would otherwise enter this dict as
    # the literal string "nan" (str(float('nan'))), and since the rebuild below
    # prefers this dict over the row's own value, that string would overwrite a
    # curator's hand-typed title -- the exact case the fallthrough exists to
    # protect. Zero such rows in today's extract, so this is a latent guard.
    titles = {
        int(i): str(t)
        for i, t in zip(assays.internal_assay_id, assays.internal_assay_title)
        if pd.notna(i) and pd.notna(t)
    }
    frames = [f for f in (learned, proposed, curator) if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=S.VOCAB_COLUMNS)
    allrows = pd.concat(frames, ignore_index=True)
    # normalise the key BEFORE deduping, so a curator spelling and a learned
    # spelling of one term are one term. See the docstring.
    before = list(allrows.raw_value)
    allrows["raw_value"] = [S.normalise_value(v) for v in before]
    # A key that normalises to None is a DELETION, not a no-op. Every such row
    # lands on one None key and `drop_duplicates` below keeps exactly one, so
    # n rows in become 1 row out with no error and nothing in the output to
    # notice. `load_vocabulary` pins both key columns to str, which closes the
    # door a csv comes through -- but nothing closes it for a frame a caller
    # BUILDS. The `proposed` frame is the first such caller, and its natural
    # first batch is the 12 bare-numeric Protocol terms in the live unresolved
    # queue: a proposal file written from those, in memory, is the exact input
    # that voided a curator file before the loader was pinned. Loud here beats
    # silent there.
    assert allrows.raw_value.notna().all(), (
        f"raw_value normalises to None on {int(allrows.raw_value.isna().sum())}"
        f" of {len(allrows)} rows, each of which would collapse onto one None"
        " key and all but one be deleted: "
        + "; ".join(
            f"{f}/{v!r} ({p})"
            for f, v, p, n in zip(allrows.source_field, before,
                                  allrows.provenance, allrows.raw_value)
            if pd.isna(n)
        )
        + ". A vocabulary key is text; give it as text."
    )
    # an unrecognised provenance ranks below all three known sources rather
    # than raising: a junk value in a hand-edited file must not be able to
    # outrank a curator, and must not stop the run either.
    allrows["_rank"] = allrows.provenance.map(_PRECEDENCE).fillna(-1)
    allrows = allrows.sort_values("_rank", kind="stable").drop_duplicates(
        subset=["source_field", "raw_value"], keep="last"
    )
    # rebuild from the assays frame where it HAS a title; otherwise keep the
    # one the row carries, which for a junction-less id is the only title it
    # will ever have.
    allrows["internal_assay_title"] = [
        titles.get(int(i), t) if pd.notna(i) else t
        for i, t in zip(allrows.internal_assay_id, allrows.internal_assay_title)
    ]
    return allrows.drop(columns="_rank").reset_index(drop=True)[S.VOCAB_COLUMNS]


def unresolved_terms(
    meta: dict[int, dict],
    vocab: pd.DataFrame,
    uuids: dict[int, str],
    min_occurrences: int = 3,
) -> pd.DataFrame:
    """Frequent metadata values the vocabulary cannot map. The judgment queue.

    Bounded by `min_occurrences` on purpose: a value seen once is far more
    likely to be a typo than a vocabulary gap, and asking a human to rule on
    every singleton buries the terms that matter.

    BOTH sides of the lookup are normalised. learn_vocabulary already emits
    normalised values so a learned-only vocabulary compares equal either way,
    but the other two provenances do not: `proposed` comes from a model and
    `curator` from a hand-edited csv, and a curator typing `CometChip` the way
    it appears in the metadata would otherwise leave every `cometchip` sample
    in this queue -- asking a human to rule again on a question they have
    already answered, in the one artifact whose entire purpose is to be short.
    normalise_value is idempotent, so this costs the learned rows nothing.
    """
    known = {
        (r.source_field, S.normalise_value(r.raw_value))
        for r in vocab.itertuples()
    }
    seen: dict[tuple[str, str], list[int]] = {}
    for sid, d in meta.items():
        for field in S.CLAIM_FIELDS:
            value = S.normalise_value(d.get(field))
            if value and (field, value) not in known:
                seen.setdefault((field, value), []).append(sid)
    rows = [
        {
            "source_field": field,
            "raw_value": value,
            "n_samples": len(ids),
            "example_uuids": "; ".join(
                str(uuids.get(i, i)) for i in sorted(ids)[:5]
            ),
        }
        for (field, value), ids in seen.items() if len(ids) >= min_occurrences
    ]
    out = pd.DataFrame(rows, columns=["source_field", "raw_value",
                                      "n_samples", "example_uuids"])
    return out.sort_values("n_samples", ascending=False, ignore_index=True)


def save_vocabulary(df: pd.DataFrame, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def load_vocabulary(path) -> pd.DataFrame:
    """Read a vocabulary csv, tolerating a curator having edited it by hand.

    A missing file reads as an empty vocabulary rather than raising, because
    `proposed` and `curator` legitimately do not exist until someone has
    produced them.

    `keep_default_na=False` matters: a raw_value of `nan` or `null` is a real
    string a curator may have typed, and pandas would otherwise read it back as
    a missing value and silently change what the row maps.

    The `dtype=` pin on the two KEY columns matters more, and it is not
    hypothetical. read_csv infers per column, so a file whose raw_value column
    happens to be entirely numeric comes back as int64 -- and the merge
    normalises its key through `normalise_value`, which returns None for a
    non-str. Every row in such a file then collapses onto a single None key and
    all but one curator decision is deleted, silently.

    That file is a natural unit of work, not a contrived one: the live
    unresolved queue holds 12 bare-numeric Protocol terms (18032418, 22010444,
    22071552, ...), and a curator ruling on exactly that batch writes a
    wholly-numeric curator.csv. Measured on those 12: 13 rows in, 2 out, 11
    decisions lost. A single-row numeric file is voided the same way.

    The pin is here rather than in `normalise_value` on purpose -- this package
    has ONE normaliser and it stays that way. This is a parsing concern: the
    keys are text, so they are read as text.
    """
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=S.VOCAB_COLUMNS)
    df = pd.read_csv(p, keep_default_na=False, na_values=[""],
                     dtype={"source_field": str, "raw_value": str})
    for col in S.VOCAB_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[S.VOCAB_COLUMNS]
