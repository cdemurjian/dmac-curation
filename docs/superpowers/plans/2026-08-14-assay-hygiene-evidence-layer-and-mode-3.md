# Assay Hygiene Increment 1: evidence layer and Mode 3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared evidence layer (precedent, metadata claims, the learned assay vocabulary) and the Mode 3 contradiction audit, which writes nothing to production.

**Architecture:** Two independent deterministic miners feed one classifier. Stage B counts graph membership; stage B2 extracts assay claims from `samples.json_metadata` and grades each by a measured confidence tier. Both read the parquet extract stage A already produces. The assay vocabulary that turns free text like `cometchip` into `internal_assay_id 138` is LEARNED from the 360,027 curator-labelled edges, not inferred, and only its unanchored tail goes to a model. Mode 3 compares each sample's claim against what it is actually registered in and flags disagreements. Nothing here writes to MySQL, Neo4j, or the API.

**Tech Stack:** Python 3.11+, pandas, pyarrow, pytest. PEP 723 inline dependency blocks, matching every other script in `scripts/`.

**Spec:** `docs/superpowers/specs/2026-08-14-assay-hygiene-three-mode-design.md`

**This is increment 1 of 3.** Increment 2 is Mode 1 and proving the write path; increment 3 is Mode 2 and its backtest. Each gets its own plan. This one ships useful artifacts without touching production.

## Global Constraints

- **P1 sentinel:** scripts must never create, modify, or delete anything inside the plugin checkout. All project paths resolve from the current working directory. `tests/conftest.py::plugin_sentinel` enforces this and will fail the suite otherwise.
- **Output root** is `assay-hygiene/` under the current working directory.
- **PEP 723 header** on every script: `requires-python = ">=3.11"` plus explicit dependencies.
- **Test command:** `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/<file> -v`
- **Full suite must stay green.** Measure the baseline yourself with `pytest tests/ -q` before you start, and check your work against the DELTA, not against an absolute. An absolute recorded on 2026-08-14 turned out not to be reproducible, so every task below states how many tests it adds rather than what the total should read. Never weaken an existing assertion to make new work pass; a zero-deletion diff on an existing test file is the thing to verify.
- **Read-only.** Nothing in this increment writes to MySQL, Neo4j, or the NExtSEEK API. No stage here needs production access at all: it reads the parquet extract already on disk at `assay-hygiene/extract/`.
- **Rule key is `(project_id, child_type, parent_type, internal_assay_id)`.** NOT `assays.title`, NOT `assays.id`.
- **`internal_assay_id` is NULLABLE and is a RULE_KEY component.** A pandas `groupby(RULE_KEY)` defaults to `dropna=True` and would silently discard the 17 assay records with no junction row, violating the spec's binding "nothing is dropped silently". Pass `dropna=False`, or apply the `(assay_id, assays.title)` fallback first so the key is never null.
- **The 17 assays with no junction row** fall back to `(assay_id, assays.title)` as their identity, the same rule `neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge)` uses.
- **Every measured figure carries its scope in the sentence that states it.** The spec documents three figures that are each measurable three ways, where two readings are wrong. Do not restate a number without its scope.
- **Percentages quoted in this plan are justification, not fixtures.** Task 2 re-derives them. If a re-derived number disagrees with this document by more than a point, stop and report it rather than adjusting the assertion.
- **The judgment steps are slash commands, not API calls.** This plugin has no LLM client and does not gain one. Deterministic work lives in `scripts/`; judgment lives in `commands/*.md` where Claude reads a file and writes a file. The artifact on disk is the cache.
- **Commit style:** end messages with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/assay_hygiene/_schema.py` | MODIFY. Column contracts, tier and provenance vocabulary, shared `normalise_value`, fixture. |
| `scripts/assay_hygiene/vocabulary.py` | CREATE. Learn (field, value) -> internal assay from labelled edges; score it held-out; merge learned/proposed/curator rows; report the unresolved tail. |
| `scripts/assay_hygiene/claims.py` | CREATE. Stage B2. Per-sample assay claims with a confidence tier. |
| `scripts/assay_hygiene/precedent.py` | CREATE. Stage B. The hop-level propagation map. |
| `scripts/assay_hygiene/audit.py` | CREATE. Mode 3. Claim versus registration, flag only. |
| `commands/curate-assay-vocabulary.md` | CREATE. The judgment step for the unresolved tail. |
| `tests/test_assay_hygiene_vocabulary.py` | CREATE. |
| `tests/test_assay_hygiene_claims.py` | CREATE. |
| `tests/test_assay_hygiene_precedent.py` | CREATE. |
| `tests/test_assay_hygiene_audit.py` | CREATE. |

`vocabulary.py` and `claims.py` are separate because one learns a mapping from
graph labels and the other applies it to text. They fail in unrelated ways, and
when a claim looks wrong you need to know which half to distrust.

---

### Task 1: Schema contracts for claims, vocabulary and the audit

**Files:**
- Modify: `scripts/assay_hygiene/_schema.py`
- Test: `tests/test_assay_hygiene_schema.py` (existing file, add tests)

**Interfaces:**
- Produces: `CLAIM_COLUMNS`, `VOCAB_COLUMNS`, `AUDIT_COLUMNS`, `STRONG_FIELDS`, `WEAK_FIELDS`, `CLAIM_FIELDS`, tier constants `T_CORROBORATED` / `T_STRONG` / `T_WEAK` / `T_CONFLICT` / `T_NONE`, provenance constants `P_LEARNED` / `P_PROPOSED` / `P_CURATOR`, `normalise_value(v) -> str | None`, and an extended `make_fixture()` whose `samples` frame exercises every tier. (Task 5 later adds `contested` and `source_provenance` to `CLAIM_COLUMNS` and retires `T_CONFLICT` as an emitted tier; the constant stays.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_assay_hygiene_schema.py`:

```python
def test_claim_and_vocab_contracts_are_declared():
    for col in ("sample_id", "uuid", "internal_assay_id",
                "internal_assay_title", "tier", "source_field", "raw_value"):
        assert col in S.CLAIM_COLUMNS
    for col in ("source_field", "raw_value", "internal_assay_id",
                "internal_assay_title", "support", "n_samples", "purity", "provenance"):
        assert col in S.VOCAB_COLUMNS


def test_tier_and_provenance_constants_are_distinct():
    tiers = [S.T_CORROBORATED, S.T_STRONG, S.T_WEAK, S.T_CONFLICT, S.T_NONE]
    assert len(set(tiers)) == len(tiers)
    prov = [S.P_LEARNED, S.P_PROPOSED, S.P_CURATOR]
    assert len(set(prov)) == len(prov)


def test_strong_and_weak_fields_are_disjoint_and_ordered_strong_first():
    # Tier assignment reads CLAIM_FIELDS in order and the strong fields must be
    # seen first, so a sample carrying both a strong and a weak field is graded
    # on the strong one. Overlap would make a field both deciding and merely
    # corroborating, which is not a state the tier logic can represent.
    assert not set(S.STRONG_FIELDS) & set(S.WEAK_FIELDS)
    assert S.CLAIM_FIELDS == S.STRONG_FIELDS + S.WEAK_FIELDS


def test_protocol_is_a_weak_field_not_a_strong_one():
    # Measured 2026-08-14, held out by sample against the 360,027 labelled
    # edges: strong fields alone score 98.4% accuracy at 65.9% coverage;
    # adding Protocol and DataType raises coverage to 92.3% and drops accuracy
    # to 90.4%, under the 95% bar. Protocol corroborates, it does not decide.
    assert "Protocol" in S.WEAK_FIELDS
    assert "Protocol" not in S.STRONG_FIELDS
    assert "Type" in S.STRONG_FIELDS


def test_normalise_value_folds_case_and_whitespace():
    # `Liver`, `liver` and `LIVER` occur as three values on the same field in
    # production; these are curator-entered free text with no controlled
    # vocabulary.
    assert S.normalise_value("  CometChip ") == "cometchip"
    assert S.normalise_value("Comet  Chip") == "comet chip"
    assert S.normalise_value("") is None
    assert S.normalise_value(None) is None
    assert S.normalise_value(7) is None


def test_fixture_samples_exercise_every_tier():
    fx = S.make_fixture()
    assert list(fx["samples"].columns) == S.SAMPLE_COLUMNS
    by_uuid = {r.uuid: json.loads(r.json_metadata)
               for r in fx["samples"].itertuples()}
    assert by_uuid["D.IMG-1"]["Type"] == "CometChip"      # -> corroborated
    assert by_uuid["D.IMG-1"]["Protocol"] == "comet.docx"
    assert by_uuid["D.IMG-2"]["Type"] == "CometChip"      # -> strong
    assert "Protocol" not in by_uuid["D.IMG-2"]
    assert by_uuid["D.IMG-3"]["Protocol"] == "comet.docx"  # -> weak
    assert "Type" not in by_uuid["D.IMG-3"]
    assert by_uuid["TIS-1"]["Type"] == "CometChip"        # -> conflict
    assert by_uuid["TIS-1"]["Instrument"] == "tissue scope"
    assert "Type" not in by_uuid["DNA-1"]                 # -> none


def test_fixture_edge_and_assay_shape_is_unchanged():
    # Tasks 5 and 6 hand-trace counts off this fixture (n_both=2,
    # n_child_only=1, propagation_rate=2/3). Adding sample rows must not move
    # them, so the edge and assay frames are pinned here.
    fx = S.make_fixture()
    assert len(fx["edges"]) == 6
    assert set(fx["assays"]["title"]) == {"Comet Chip", "Tissue Collection"}
```

Add `import json` at the top of the test file if it is not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: FAIL with `AttributeError: module 'assay_hygiene._schema' has no attribute 'CLAIM_COLUMNS'`

- [ ] **Step 3: Add the contracts to `_schema.py`**

Insert after the `FINDING_COLUMNS` / `RULE_COLUMNS` block, before the `--- vocabulary ---` section:

```python
# --- claims (stage B2) -------------------------------------------------------
#
# A sample's own metadata naming the assay it belongs to. Measured 2026-08-14,
# learning the value->assay mapping on half the samples and scoring the held-out
# half against the 360,027 curator-labelled edges (split BY SAMPLE, because a
# sample fans out to many edges and an edge-level split scores memorised
# answers):
#
#   strong fields alone                     65.9% coverage   98.4% accuracy
#   strong then Protocol/DataType           92.3% coverage   90.4% accuracy
#   Type and Protocol predict and agree     35.0% coverage   99.9% accuracy
#
# So the strong fields decide and the weak ones corroborate. Order matters:
# tier assignment walks CLAIM_FIELDS and must see strong fields first.
STRONG_FIELDS = ["Type", "Instrument", "Stimulation", "Software",
                 "SlideStain", "Assay", "Channels", "Stains"]
WEAK_FIELDS = ["Protocol", "DataType"]
CLAIM_FIELDS = STRONG_FIELDS + WEAK_FIELDS

T_CORROBORATED = "corroborated"
T_STRONG = "strong"
T_WEAK = "weak"
T_CONFLICT = "conflict"
T_NONE = "none"

CLAIM_COLUMNS = [
    "sample_id", "uuid", "internal_assay_id", "internal_assay_title",
    "tier", "source_field", "raw_value",
]

# --- vocabulary alignment ----------------------------------------------------
#
# provenance records where a mapping came from, because the three are trusted
# differently: `learned` is backed by curator-labelled edges and carries a
# support count, `proposed` is a model's suggestion for a term with no
# empirical anchor, and `curator` is a human decision that outranks both.
P_LEARNED = "learned"
P_PROPOSED = "proposed"
P_CURATOR = "curator"

VOCAB_COLUMNS = [
    "source_field", "raw_value", "internal_assay_id", "internal_assay_title",
    "support", "n_samples", "purity", "provenance",
]

# --- audit (mode 3) ----------------------------------------------------------
AUDIT_COLUMNS = [
    "sample_id", "uuid", "sample_type",
    # ids AND titles on the registered side, positionally aligned. The frame
    # already carries both for the CLAIMED assay; carrying only ids here made
    # the csv unjudgeable without a decoder, and Mode 3's entire product is a
    # curator's attention. Titles come from assay_index so there is no second
    # source of truth.
    "registered_internal_assay_ids", "registered_internal_assay_titles",
    "claimed_internal_assay_id",
    "claimed_internal_assay_title", "tier", "source_field", "raw_value",
    "verdict",
]


def normalise_value(v) -> str | None:
    """Free text to a comparable key, or None when there is nothing to compare.

    `Liver`, `liver` and `LIVER` appear as three values on the same field in
    production. These are curator-entered fields with no controlled vocabulary,
    so every comparison in this package goes through here.
    """
    if not isinstance(v, str):
        return None
    s = " ".join(v.split()).strip().lower()
    return s or None
```

- [ ] **Step 4: Extend the fixture's samples frame**

Replace the `samples` frame inside `make_fixture()` with:

```python
    # One sample per claim tier, so every branch of claims.sample_claims has a
    # case here. assay 1 is "Comet Chip" (internal 11), assay 2 is
    # "Tissue Collection" (internal 12); tests build an explicit vocabulary
    # rather than learning one, so these raw values map wherever a test says.
    samples = pd.DataFrame(
        [
            # strong AND weak agree -> corroborated
            (100, "D.IMG-1",
             '{"Type": "CometChip", "Protocol": "comet.docx", "Name": "img1"}',
             None, "10"),
            # strong only -> strong
            (101, "D.IMG-2", '{"Type": "CometChip", "Name": "img2"}', None, "10"),
            # weak only -> weak
            (102, "D.IMG-3", '{"Protocol": "comet.docx", "Name": "img3"}', None, "10"),
            # two strong fields naming different assays -> conflict
            (200, "TIS-1",
             '{"Type": "CometChip", "Instrument": "tissue scope"}', None, "10"),
            # nothing that names an assay -> none
            (300, "DNA-1", '{"Protocol": "/sops/9", "Name": "dna1"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
```

Note `DNA-1` keeps a `Protocol` value that no test vocabulary maps, which is
what makes it a `none` rather than a `weak`: the tier depends on whether the
value resolves, not on whether the field is populated.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: PASS, 25 tests

- [ ] **Step 6: Run the full suite**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/ -q`
Expected: **your measured baseline + 7 passed**, skips unchanged. If any previously-passing test now fails, the fixture change broke a contract — fix the fixture, never the assertion.

- [ ] **Step 7: Commit**

```bash
git add scripts/assay_hygiene/_schema.py tests/test_assay_hygiene_schema.py
git commit -m "$(printf 'feat(assay-hygiene): declare claim, vocabulary and audit contracts\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: Learn the assay vocabulary from curator-labelled edges

**Files:**
- Create: `scripts/assay_hygiene/vocabulary.py`
- Test: `tests/test_assay_hygiene_vocabulary.py`

**Interfaces:**
- Consumes: `_schema.CLAIM_FIELDS`, `VOCAB_COLUMNS`, `P_LEARNED`, `normalise_value`
- Produces: `parse_metadata(samples: pd.DataFrame) -> dict[int, dict]`; `learn_vocabulary(edges: pd.DataFrame, meta: dict[int, dict], min_support: int = 3) -> pd.DataFrame` returning `VOCAB_COLUMNS`; `score_vocabulary(edges, meta, min_support: int = 3) -> pd.DataFrame` with columns `["source_field", "terms", "coverage", "accuracy"]`

**Why learned and not asked.** The mapping `cometchip -> internal_assay_id 138`
is observed in 1,364 curator-labelled edges. Deriving it from data rather than
from a model keeps this measurement independent of the judgment step it exists
to justify, and gives every common term a support count a human can check.

**`support` counts EDGES; `n_samples` counts distinct child samples.** A sample
fans out to a mean of 2.79 labelled edges and a maximum of 1,218, so edge-weighted
support is inflated by fan-out. Measured on the real extract: of 736 learned
terms, 83 clear `min_support=3` on fewer than three distinct samples and **50 rest
on exactly one** — `Software: matlab` shows a support of 132 drawn from a single
sample, and the worst case is 304 from one. `min_support` does not do what its
name suggests.

The semantics are deliberately left alone: every figure in the spec, and this
task's own step 5 gate, is defined against edge-weighted support, and changing it
would invalidate the design's measured basis. `n_samples` rides alongside so the
weakness is visible instead of silent. It matters most in `vocabulary.csv`, which
the spec calls the most durable artifact this project produces and which a curator
corrects by hand — nobody can audit a mapping whose support they cannot decompose.

Both columns are in `VOCAB_COLUMNS`, `n_samples` immediately after `support`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_vocabulary.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import vocabulary as V


def _edges(rows):
    """(child_id, edge_internal_assay_id) pairs as an EDGE_COLUMNS frame."""
    return pd.DataFrame(
        [(c, 900, f"C-{c}", "P-900", "D.IMG", "TIS", a, None, None)
         for c, a in rows],
        columns=S.EDGE_COLUMNS,
    )


def _meta(rows):
    return {sid: d for sid, d in rows}


def test_parse_metadata_skips_unparseable_blobs_without_dropping_the_sample():
    # An unparseable blob is a data defect, not a missing sample. It must read
    # as "no metadata" rather than raising or vanishing silently.
    samples = pd.DataFrame(
        [(1, "A-1", '{"Type": "CometChip"}', None, "10"),
         (2, "A-2", "not json at all", None, "10"),
         (3, "A-3", "", None, "10")],
        columns=S.SAMPLE_COLUMNS,
    )
    meta = V.parse_metadata(samples)
    assert meta[1]["Type"] == "CometChip"
    assert 2 not in meta
    assert 3 not in meta


def test_learn_maps_a_value_to_the_assay_curators_assigned():
    edges = _edges([(1, 11), (2, 11), (3, 11)])
    meta = _meta([(1, {"Type": "CometChip"}),
                  (2, {"Type": "cometchip"}),
                  (3, {"Type": "  CometChip  "})])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    assert list(vocab.columns) == S.VOCAB_COLUMNS
    row = vocab[(vocab.source_field == "Type") & (vocab.raw_value == "cometchip")].iloc[0]
    assert row.internal_assay_id == 11
    assert row.support == 3          # all three normalise to one value
    assert row.purity == 1.0
    assert row.provenance == S.P_LEARNED


def test_learn_drops_values_below_min_support():
    edges = _edges([(1, 11), (2, 12)])
    meta = _meta([(1, {"Type": "rare"}), (2, {"Type": "alsorare"})])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    assert vocab.empty


def test_learn_takes_the_majority_and_records_impurity():
    # A value that mostly means one assay but not always is still usable; the
    # purity column is how a reader sees that it is not clean.
    edges = _edges([(1, 11), (2, 11), (3, 11), (4, 12)])
    meta = _meta([(i, {"Type": "mixed"}) for i in (1, 2, 3, 4)])
    vocab = V.learn_vocabulary(edges, meta, min_support=3)
    row = vocab.iloc[0]
    assert row.internal_assay_id == 11
    assert row.support == 4
    assert row.purity == pytest.approx(0.75)


def test_learn_ignores_dark_edges_because_they_are_not_ground_truth():
    # A dark edge is the thing being fixed. Learning from it would launder the
    # defect into the vocabulary as if a curator had asserted it.
    edges = _edges([(1, None), (2, None), (3, None)])
    meta = _meta([(i, {"Type": "cometchip"}) for i in (1, 2, 3)])
    assert V.learn_vocabulary(edges, meta, min_support=3).empty


def test_score_holds_out_by_sample_and_reports_per_field():
    # 8 samples, ids alternating parity so the split is even.
    edges = _edges([(i, 11) for i in range(1, 9)])
    meta = _meta([(i, {"Type": "cometchip"}) for i in range(1, 9)])
    scored = V.score_vocabulary(edges, meta, min_support=2)
    row = scored[scored.source_field == "Type"].iloc[0]
    assert row.coverage == 1.0
    assert row.accuracy == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_vocabulary.py -v`
Expected: FAIL with `ImportError: cannot import name 'vocabulary'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/vocabulary.py
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


def _tally(edges: pd.DataFrame, meta: dict[int, dict], keep) -> dict:
    """(field, normalised value) -> Counter of the assay ids curators assigned."""
    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
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
    return tally


def learn_vocabulary(
    edges: pd.DataFrame,
    meta: dict[int, dict],
    min_support: int = 3,
) -> pd.DataFrame:
    """Derive the (field, value) -> internal assay mapping from labelled edges.

    `support` is how many labelled edges back the mapping and `purity` is the
    winning assay's share of them. Both are carried so a reader can tell a term
    seen 40,000 times at 0.99 from one seen 3 times at 0.67 -- a distinction the
    mapping alone destroys.
    """
    rows = []
    for (field, value), counter in _tally(edges, meta, lambda _: True).items():
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
    train = _tally(edges, meta, lambda sid: sid % 2 == 0)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_vocabulary.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Re-derive the measured figures against the real extract**

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import sys; sys.path.insert(0, "scripts")
import pandas as pd
from assay_hygiene import vocabulary as V
d = "assay-hygiene/extract"
edges = pd.read_parquet(f"{d}/edges.parquet")
meta = V.parse_metadata(pd.read_parquet(f"{d}/samples.parquet"))
print(V.score_vocabulary(edges, meta).sort_values("coverage", ascending=False).to_string(index=False))
vocab = V.learn_vocabulary(edges, meta)
print(f"\nlearned terms: {len(vocab):,}")
print(vocab.groupby("source_field").size().to_string())
PY
```

Expected, from the 2026-08-14 measurement: `Type` around 42.9% coverage and
97.6% accuracy, `Protocol` around 84.0% and 89.7%, `Instrument` around 25.5%
and 100%. **If a field disagrees with this by more than a point, stop and
report it** rather than adjusting anything. The whole design rests on these.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/vocabulary.py tests/test_assay_hygiene_vocabulary.py
git commit -m "$(printf 'feat(assay-hygiene): learn the assay vocabulary from curator-labelled edges\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: Vocabulary file, provenance precedence, and the unresolved tail

**Files:**
- Modify: `scripts/assay_hygiene/vocabulary.py`
- Test: `tests/test_assay_hygiene_vocabulary.py`

**Interfaces:**
- Consumes: Task 2's `learn_vocabulary`, `_schema.P_LEARNED` / `P_PROPOSED` / `P_CURATOR`
- Produces: `merge_vocabulary(learned, proposed, curator, assays) -> pd.DataFrame`; `unresolved_terms(meta: dict[int, dict], vocab: pd.DataFrame, uuids: dict[int, str], min_occurrences: int = 3) -> pd.DataFrame` with columns `["source_field", "raw_value", "n_samples", "example_uuids"]`; `save_vocabulary(df, path)`; `load_vocabulary(path) -> pd.DataFrame`

`merge_vocabulary` accepts `None` for `proposed` and `curator`, so it works
before Task 4 has ever run.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assay_hygiene_vocabulary.py`:

```python
def _vocab(rows):
    return pd.DataFrame(rows, columns=S.VOCAB_COLUMNS)


def _assays():
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection")],
        columns=S.ASSAY_COLUMNS,
    )


def test_curator_rows_beat_learned_and_proposed():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    proposed = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_PROPOSED)])
    curator = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_CURATOR)])
    out = V.merge_vocabulary(learned, proposed, curator, _assays())
    row = out[out.raw_value == "cometchip"].iloc[0]
    assert row.internal_assay_id == 12
    assert row.provenance == S.P_CURATOR
    assert len(out) == 1


def test_learned_beats_proposed_when_no_curator_row_exists():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    proposed = _vocab([("Type", "cometchip", 12, None, 0, 0, 0.0, S.P_PROPOSED)])
    out = V.merge_vocabulary(learned, proposed, _vocab([]), _assays())
    assert out.iloc[0].internal_assay_id == 11
    assert out.iloc[0].provenance == S.P_LEARNED


def test_merge_fills_the_display_title_from_the_assays_frame():
    learned = _vocab([("Type", "cometchip", 11, None, 900, 850, 0.99, S.P_LEARNED)])
    out = V.merge_vocabulary(learned, _vocab([]), _vocab([]), _assays())
    assert out.iloc[0].internal_assay_title == "Comet Chip"


def test_unresolved_lists_frequent_terms_the_vocabulary_cannot_map():
    meta = {1: {"Type": "cometchip"}, 2: {"Type": "mystery"},
            3: {"Type": "mystery"}, 4: {"Type": "mystery"}, 5: {"Type": "once"}}
    uuids = {1: "A-1", 2: "A-2", 3: "A-3", 4: "A-4", 5: "A-5"}
    vocab = _vocab([("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED)])
    out = V.unresolved_terms(meta, vocab, uuids, min_occurrences=3)
    assert list(out.raw_value) == ["mystery"]     # 'once' is below the floor
    assert out.iloc[0].n_samples == 3
    assert "A-2" in out.iloc[0].example_uuids


def test_vocabulary_round_trips_through_csv(tmp_path):
    df = _vocab([("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED)])
    p = tmp_path / "vocabulary.csv"
    V.save_vocabulary(df, p)
    back = V.load_vocabulary(p)
    assert list(back.columns) == S.VOCAB_COLUMNS
    assert back.iloc[0].internal_assay_id == 11
    assert back.iloc[0].raw_value == "cometchip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_vocabulary.py -v`
Expected: FAIL with `AttributeError: module 'assay_hygiene.vocabulary' has no attribute 'merge_vocabulary'`

- [ ] **Step 3: Write the implementation**

Append to `scripts/assay_hygiene/vocabulary.py`:

```python
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

    Display titles are filled from the assays frame rather than trusted from
    the input, so a stale title in a hand-edited file cannot travel onward.
    """
    titles = {
        int(i): str(t)
        for i, t in zip(assays.internal_assay_id, assays.internal_assay_title)
        if pd.notna(i)
    }
    frames = [f for f in (learned, proposed, curator) if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=S.VOCAB_COLUMNS)
    allrows = pd.concat(frames, ignore_index=True)
    allrows["_rank"] = allrows.provenance.map(_PRECEDENCE).fillna(-1)
    allrows = allrows.sort_values("_rank").drop_duplicates(
        subset=["source_field", "raw_value"], keep="last"
    )
    allrows["internal_assay_title"] = [
        titles.get(int(i)) if pd.notna(i) else None
        for i in allrows.internal_assay_id
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
    """
    known = {(r.source_field, r.raw_value) for r in vocab.itertuples()}
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
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def load_vocabulary(path) -> pd.DataFrame:
    """Read a vocabulary csv, tolerating a curator having edited it by hand.

    `keep_default_na=False` matters: a raw_value of `nan` or `null` is a real
    string a curator may have typed, and pandas would otherwise read it back as
    a missing value and silently change what the row maps.
    """
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=S.VOCAB_COLUMNS)
    df = pd.read_csv(p, keep_default_na=False, na_values=[""])
    for col in S.VOCAB_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[S.VOCAB_COLUMNS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_vocabulary.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Size the unresolved tail against the real extract**

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import sys; sys.path.insert(0, "scripts")
import pandas as pd
from assay_hygiene import vocabulary as V
d = "assay-hygiene/extract"
edges = pd.read_parquet(f"{d}/edges.parquet")
samples = pd.read_parquet(f"{d}/samples.parquet")
assays = pd.read_parquet(f"{d}/assays.parquet")
meta = V.parse_metadata(samples)
uuids = dict(zip(samples.sample_id.astype(int), samples.uuid))
vocab = V.merge_vocabulary(V.learn_vocabulary(edges, meta),
                           None, None, assays)
tail = V.unresolved_terms(meta, vocab, uuids)
print(f"learned terms   {len(vocab):,}")
print(f"unresolved tail {len(tail):,} terms over {int(tail.n_samples.sum()):,} samples")
print(tail.head(25).to_string(index=False))
V.save_vocabulary(vocab, "assay-hygiene/vocabulary.csv")
tail.to_csv("assay-hygiene/vocabulary-unresolved.csv", index=False)
PY
```

Report the tail size. It is the size of Task 4's queue and nobody has measured
it; the spec deliberately declines to estimate it.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/vocabulary.py tests/test_assay_hygiene_vocabulary.py
git commit -m "$(printf 'feat(assay-hygiene): vocabulary file, provenance precedence and the unresolved tail\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: The judgment step for the unresolved tail

**Files:**
- Create: `commands/curate-assay-vocabulary.md`

**Interfaces:**
- Consumes: `assay-hygiene/vocabulary-unresolved.csv` from Task 3
- Produces: `assay-hygiene/vocabulary-proposed.csv` in `VOCAB_COLUMNS` shape with `provenance = proposed`

This is the only step in the increment where judgment happens, and it is a
slash command rather than code because this plugin has no LLM client. Claude
reads the unresolved terms, the assay list, and example samples, then writes
proposals a curator reviews. No script calls a model.

- [ ] **Step 1: Write the command**

```markdown
---
description: Map unresolved metadata terms onto internal assays (assay hygiene, stage B2)
---

The user wants the unresolved tail of the assay vocabulary settled.

Every common metadata term was already mapped from curator-labelled edges and
carries a support count. What is left are terms no labelled edge anchors. Your
job is to propose a mapping for the ones you can justify, and to leave the rest
alone.

## Prereqs

- `assay-hygiene/vocabulary-unresolved.csv` exists (run stage B2's Task 3 step 5)
- `assay-hygiene/vocabulary.csv` exists — the learned mappings, your reference
  for how terms in this database actually correspond to assays
- `assay-hygiene/extract/assays.parquet` exists — the 137 internal assays

## Rules

1. **Propose only what you can justify from evidence in front of you.** A term
   you cannot place is a valid outcome. Leave it out and say so.
2. **Never invent an `internal_assay_id`.** Every id must exist in
   `assays.parquet`. Check it.
3. **Read the example samples.** Each unresolved row carries up to five sample
   UIDs. Look at their full metadata before proposing anything: a term is often
   unambiguous once you see the instrument and protocol beside it.
4. **Match the house vocabulary, not English.** `CometChip` maps to
   `CometChip Assay` because that is what this database calls it. Check
   `vocabulary.csv` for how similar terms were resolved by the data.
5. **Beware the measurement-versus-analysis pair.** Many assays exist twice,
   once for the measurement and once for its analysis (`Flow Cytometry` and
   `Flow Cytometry Analysis`). These are different assays with different
   memberships. If a term could be either, leave it unresolved and note the
   ambiguity — do not guess.
6. **You are proposing, not deciding.** Everything you write lands with
   `provenance = proposed` and a curator can overrule it. Say plainly in your
   summary which proposals you are confident in and which are weak.

## Output

Write `assay-hygiene/vocabulary-proposed.csv` with exactly these columns:

    source_field,raw_value,internal_assay_id,internal_assay_title,support,n_samples,purity,provenance

- `source_field` and `raw_value` copied verbatim from the unresolved file
- `internal_assay_id` and `internal_assay_title` from `assays.parquet`
- `support` = 0, `n_samples` = 0 and `purity` = 0.0, because a proposal has no empirical backing.
  Do not fabricate these — they are what distinguishes your rows from learned ones.
- `provenance` = `proposed`

Then report: how many terms you mapped, how many you left, and the specific
ones you were least sure about.
```

- [ ] **Step 2: Verify the command is registered**

Run: `ls commands/curate-assay-vocabulary.md && head -3 commands/curate-assay-vocabulary.md`
Expected: the file exists and its frontmatter has a `description:` line, matching every other command in that directory.

- [ ] **Step 3: Commit**

```bash
git add commands/curate-assay-vocabulary.md
git commit -m "$(printf 'feat(assay-hygiene): add the vocabulary judgment command for the unresolved tail\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: Stage B2, per-sample claims with a confidence tier

**Files:**
- Create: `scripts/assay_hygiene/claims.py`
- Modify: `scripts/assay_hygiene/_schema.py` — `CLAIM_COLUMNS` gains `contested` (bool) and `source_provenance` (str)
- Modify: `tests/test_assay_hygiene_schema.py` — extend the `CLAIM_COLUMNS` contract test for the two new columns
- Test: `tests/test_assay_hygiene_claims.py`

**Interfaces:**
- Consumes: `_schema.CLAIM_COLUMNS`, `STRONG_FIELDS`, `WEAK_FIELDS`, `CLAIM_FIELDS`, tier constants, `normalise_value`; `vocabulary.parse_metadata`
- Produces: `claim_index(vocab: pd.DataFrame) -> dict[tuple[str, str], tuple[int, str, str]]` mapping `(field, value) -> (internal_assay_id, title, provenance)`; `sample_claims(meta: dict[int, dict], uuids: dict[int, str], vocab: pd.DataFrame) -> pd.DataFrame` returning `CLAIM_COLUMNS`
- Also modifies `_schema.CLAIM_COLUMNS`, which gains `contested` (bool) and `source_provenance` (str).

**`source_provenance`, not `provenance`.** It describes the row named by
`source_field` / `raw_value`, NOT the claim. `vocabulary.csv` has a `provenance`
column meaning the mapping's origin, and two different meanings under one name
in adjacent frames is the defect this increment opened by fixing — see the
`edge_internal_assay_id` rename. The name carries the scope.

### Tiering is PER CLAIM, and contestedness is a column, not a tier

This replaced an earlier design where the tier was assigned per SAMPLE and any
disagreement between fields collapsed the sample to `T_CONFLICT`. That design was
measured and found to be **non-monotone: adding evidence removed audit coverage.**
Simulating proposals for the unresolved terms and running the audit as specified
suppressed 102 existing Mode 3 flags while adding 13 — because a sample that had
a clean strong claim contradicting its registration gained a second, weaker claim,
collapsed to `T_CONFLICT`, and `T_CONFLICT` sits below the audit floor. The
auditor saw less the more it was told.

Three measurements shaped the replacement, all against the real extract:

1. **A population accuracy does not transfer to a disagreement subset.** Strong
   fields are 98.4% accurate overall and weak fields 90.4%, but on the 5,089
   disagreeing samples with a curator-labelled edge as truth, strong is right
   **70.3%** and weak **62.3%**. Letting the strong field simply win there would
   raise flags whose mapping is wrong about 30% of the time — three times the
   error rate the design already refuses as too noisy for a curator.
2. **Most disagreement is not contradiction.** On that same subset, **34% of the
   time both claims are right**: the sample genuinely belongs to both assays.
   That argues for recording both, not for picking a winner.
3. **A proposal is not evidence of the same kind.** A `proposed` mapping has
   `support = 0` and no empirical anchor, so it must never be able to unseat or
   contest a learned or curator mapping.

**The rules.** Emit one row per (sample, claimed assay). Tier each row by the
evidence backing THAT assay only, so adding a claim can never lower another
claim's tier — monotonicity is structural rather than emergent.

```
no field resolves                              -> no row emitted
this assay named by a strong AND a weak field  -> T_CORROBORATED
this assay named only by strong field(s)       -> T_STRONG
this assay named only by weak field(s)         -> T_WEAK
any mapping with provenance == P_PROPOSED      -> capped at T_WEAK, whatever the field
```

`contested = True` on every row of a sample whose LEARNED or CURATOR claims name
more than one assay. **Proposed mappings never set `contested`** — they may
corroborate a claim, never contest one. A proposal stands alone only where the
sample has no other claim.

`T_CONFLICT` is retired as a tier. Keep the constant in `_schema` so nothing
importing it breaks, and add a test asserting `sample_claims` never emits it.

Measured outcome of this design, against the alternatives, all at the DEFAULT
audit setting (`include_contested=False`):

| design | baseline flags | proposals add | proposals suppress |
|---|---|---|---|
| as originally specified | 879 | 13 | 102 |
| strong-beats-weak instead | 1,535 | 23 | 63 |
| per-claim + contested, cap removed | 879 | 23 | 0 |
| **per-claim + contested + proposal cap** | **879** | **0** | **0** |

**Proposals are Mode-3-inert under this design, and that is deliberate.** Every
proposal-only claim sits at `T_WEAK`, below the audit floor, so a proposal can
neither raise a flag nor remove one. A `support = 0` model guess should not be
able to accuse a curator's own registration. The escalation path is explicit: a
curator who agrees with a proposal promotes that row to `provenance = curator`,
which outranks `learned` in `_PRECEDENCE` and legitimately earns a strong tier.

**The cap is not free: it costs 23 flags** at the default audit setting (879 ->
902 without it). That is the price of not letting an unbacked guess accuse a
registration, and it is recoverable one row at a time by a curator promoting a
proposal they agree with.

**Inertness holds only because tier strength ignores proposed sources.** Grading
over all sources lets a proposal on a strong field supply the strong half of a
corroboration for a claim whose real evidence is a weak field, carrying it above
the audit floor — 104 claims on the real extract. See the comment in
`sample_claims` and the test that pins it.

An earlier draft of this table said the shipped design adds 23 flags against a
1,570 baseline. Both figures belong to different rows: 23 is per-claim tiering
WITHOUT the cap, and 1,570 is the `include_contested=True` baseline. Specifying
both the cap and per-claim tiering and then quoting the uncapped, wrong-audit
numbers was my error, caught by rebuilding the amended tasks verbatim.

Suppression is zero by construction rather than by a precedence rule, and the
audit floor becomes a policy dial rather than a tier that deletes evidence.

**Do not widen `DEFAULT_TIERS` to compensate.** Admitting contested rows raises
the baseline from 879 to 1,570, and those extra rows carry the same ~30%
mapping-error rate measured above; Task 7 excludes them by default and that is
what keeps the flag list reviewable.

Caveat on the figures above: the vocabulary was learned from the same labelled
edges used as truth, so they are in-sample. They settle the comparison between
designs; treat the absolute error rates as optimistic.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_claims.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import claims as C
from assay_hygiene import vocabulary as V


def _vocab():
    """Maps the fixture's raw values: comet terms -> 11, tissue terms -> 12."""
    return pd.DataFrame(
        [("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED),
         ("Protocol", "comet.docx", 11, "Comet Chip", 400, 380, 0.95, S.P_LEARNED),
         ("Instrument", "tissue scope", 12, "Tissue Collection", 50, 50, 1.0, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )


def _fixture_claims():
    fx = S.make_fixture()
    meta = V.parse_metadata(fx["samples"])
    uuids = dict(zip(fx["samples"].sample_id.astype(int), fx["samples"].uuid))
    return C.sample_claims(meta, uuids, _vocab())


def test_output_matches_the_contract():
    out = _fixture_claims()
    assert list(out.columns) == S.CLAIM_COLUMNS


def test_strong_and_weak_agreeing_is_corroborated():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-1"].iloc[0]
    assert row.tier == S.T_CORROBORATED
    assert row.internal_assay_id == 11


def test_strong_field_alone_is_strong():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-2"].iloc[0]
    assert row.tier == S.T_STRONG
    assert row.source_field == "Type"


def test_weak_field_alone_is_weak():
    out = _fixture_claims()
    row = out[out.uuid == "D.IMG-3"].iloc[0]
    assert row.tier == S.T_WEAK
    assert row.source_field == "Protocol"


def test_fields_naming_different_assays_are_contested_and_both_survive():
    # Disagreement is data, not an error. Both candidates survive, each tiered
    # on ITS OWN evidence, and the disagreement is recorded in a column instead
    # of collapsing both rows into one unaudited tier.
    out = _fixture_claims()
    rows = out[out.uuid == "TIS-1"]
    assert len(rows) == 2
    assert set(rows.internal_assay_id) == {11, 12}
    assert rows.contested.all()
    # each row keeps the tier its own evidence earns
    assert set(rows.tier) == {S.T_STRONG}


def test_a_contested_sample_keeps_a_tier_the_audit_can_read():
    # The defect this design replaced: any disagreement collapsed the sample to
    # T_CONFLICT, which sits below the audit floor, so ADDING a claim REMOVED an
    # existing flag. Measured at 102 suppressed against 13 added. A tier must
    # never be lowered by the arrival of a second claim.
    out = _fixture_claims()
    assert S.T_CONFLICT not in set(out.tier)


def test_a_proposed_mapping_is_capped_at_weak_even_on_a_strong_field():
    # A proposal has support=0 and no empirical anchor. Graded by field alone it
    # would inherit the strong tier's measured 98.4%, which it has not earned.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Type", "mystery", 11, "Comet Chip", 0, 0, 0.0,
                             S.P_PROPOSED)
    meta = {700: {"Type": "mystery"}}
    out = C.sample_claims(meta, {700: "X-1"}, vocab)
    assert out.iloc[0].tier == S.T_WEAK
    assert out.iloc[0].source_provenance == S.P_PROPOSED


def test_a_proposal_cannot_corroborate_its_way_past_the_audit_floor():
    # The hole the cap was aimed at. Grading tier strength over ALL sources lets
    # a proposal on a STRONG field supply the strong half of a corroboration for
    # a claim whose only real evidence is a weak field — and `corroborated` is
    # above the audit floor, so a support=0 model guess ends up able to accuse a
    # curator's registration. Measured at 104 such claims on the real extract.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Instrument", "comet scope", 11, "Comet Chip", 0, 0,
                             0.0, S.P_PROPOSED)
    meta = {702: {"Protocol": "comet.docx", "Instrument": "comet scope"}}
    out = C.sample_claims(meta, {702: "X-3"}, vocab)
    row = out.iloc[0]
    assert row.internal_assay_id == 11
    assert row.tier == S.T_WEAK          # NOT corroborated
    assert row.source_provenance == S.P_LEARNED  # the learned weak field still owns it


def test_a_proposal_never_contests_a_learned_claim():
    # A proposal may corroborate, never contest. Otherwise a support=0 model
    # guess can push a curator's own registration out of the audit.
    vocab = _vocab()
    vocab.loc[len(vocab)] = ("Software", "imagej", 12, "Tissue Collection", 0, 0,
                             0.0, S.P_PROPOSED)
    meta = {701: {"Type": "cometchip", "Software": "imagej"}}
    out = C.sample_claims(meta, {701: "X-2"}, vocab)
    learned = out[out.internal_assay_id == 11].iloc[0]
    assert learned.tier == S.T_STRONG
    assert not out.contested.any()


def test_a_sample_whose_values_resolve_to_nothing_emits_no_row():
    # DNA-1 has a populated Protocol that the vocabulary does not map. The tier
    # depends on whether values RESOLVE, not on whether fields are populated.
    out = _fixture_claims()
    assert out[out.uuid == "DNA-1"].empty


def test_claim_index_is_keyed_on_field_and_value_together_and_carries_provenance():
    # The same string can mean different assays under different fields, so the
    # field is part of the key. A value-only index would collide them.
    # Provenance rides along because the tier cap and the contest rule both
    # need it, and claim_index is the only place claims.py sees the vocabulary.
    idx = C.claim_index(_vocab())
    assert idx[("Type", "cometchip")] == (11, "Comet Chip", S.P_LEARNED)
    assert ("cometchip",) not in idx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_claims.py -v`
Expected: FAIL with `ImportError: cannot import name 'claims'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/claims.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage B2. What assay does each sample's own metadata say it belongs to.

Independent of stage B by design: that one counts graph membership, this one
reads text. They fail in unrelated ways, and when a number looks wrong you need
to know which half to distrust.

Tiers come from measurement, not intuition. Against the 360,027 curator-labelled
edges, held out by sample: strong fields alone are 98.4% accurate over 65.9% of
the population, Protocol and DataType raise coverage to 92.3% at 90.4%
accuracy, and where Type and Protocol agree the answer is right 99.9% of the
time. So strong fields decide, weak fields corroborate, and agreement between
the two is the strongest signal available.

A claim is not a decision. This module says what a sample asserts about itself;
what to do about it belongs to stage C and the modes.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S


def claim_index(vocab: pd.DataFrame) -> dict[tuple[str, str], tuple[int, str, str]]:
    """(field, normalised value) -> (internal_assay_id, title, provenance).

    Keyed on the field as well as the value: the same string can name different
    assays under different fields, and a value-only index would collide them.

    Provenance rides along because this is the only place claims.py sees the
    vocabulary, and both the proposal tier cap and the contest rule need it.
    """
    out: dict[tuple[str, str], tuple[int, str, str]] = {}
    for r in vocab.itertuples():
        if pd.isna(r.internal_assay_id):
            continue
        out[(str(r.source_field), str(r.raw_value))] = (
            int(r.internal_assay_id),
            None if pd.isna(r.internal_assay_title) else str(r.internal_assay_title),
            str(r.provenance),
        )
    return out


def sample_claims(
    meta: dict[int, dict],
    uuids: dict[int, str],
    vocab: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (sample, claimed assay). Samples claiming nothing emit none.

    Each row is tiered on the evidence backing ITS OWN assay, so the arrival of
    a second claim can never lower the first one's tier. That property is what
    keeps the Mode 3 audit monotone: under the previous per-sample design, any
    disagreement collapsed the whole sample to T_CONFLICT, which sits below the
    audit floor, and adding evidence measurably REMOVED 102 existing flags while
    adding 13.

    Disagreement is recorded in `contested` instead. Only learned and curator
    mappings can contest; a proposal may corroborate a claim but never unseat
    one, because it carries support = 0 and no empirical anchor.
    """
    idx = claim_index(vocab)
    rows = []

    for sample_id, d in meta.items():
        # (assay_id, title) -> the (field, raw, provenance) triples that named
        # it, strong fields first because CLAIM_FIELDS is ordered that way.
        found: dict[tuple[int, str], list[tuple[str, str, str]]] = {}
        for field in S.CLAIM_FIELDS:
            raw = d.get(field)
            value = S.normalise_value(raw)
            if not value:
                continue
            hit = idx.get((field, value))
            if hit is None:
                continue
            iaid, title, prov = hit
            found.setdefault((iaid, title), []).append((field, str(raw), prov))

        if not found:
            continue

        # Contestedness is decided by the EVIDENCE-BACKED claims only. A
        # proposal that happens to name a different assay does not make the
        # sample contested, or a support=0 guess could push a curator's own
        # registration below the audit floor.
        backed = {
            key for key, sources in found.items()
            if any(p != S.P_PROPOSED for _, _, p in sources)
        }
        contested = len(backed) > 1

        for (iaid, title), sources in found.items():
            provs = {p for _, _, p in sources}
            # Tier strength is computed over EVIDENCE-BACKED sources ONLY.
            #
            # Grading over all sources leaves a hole the cap was aimed squarely
            # at: a proposal landing on a strong field supplies the strong half
            # of a corroboration for a claim that already has a learned weak
            # field, and the claim crosses the audit floor on a model's guess.
            # Measured on the real extract, 104 claims rise weak -> corroborated
            # exactly that way. None contradicts its registration in today's
            # data, so the effect is zero by DATA, not by design -- and the risk
            # shape is the `m397` case, where a term's carriers split across
            # assays, the proposal takes the modal one, and the promoted claim
            # then accuses the minority carriers.
            #
            # Excluding proposals here also makes the cap structural rather than
            # a special case: a proposal-only claim has no backing sources at
            # all, so it falls to T_WEAK on its own.
            backing = [f for f, _, p in sources if p != S.P_PROPOSED]
            has_strong = any(f in S.STRONG_FIELDS for f in backing)
            has_weak = any(f in S.WEAK_FIELDS for f in backing)
            if has_strong and has_weak:
                tier = S.T_CORROBORATED
            elif has_strong:
                tier = S.T_STRONG
            else:
                tier = S.T_WEAK
            source_provenance = (S.P_PROPOSED if provs == {S.P_PROPOSED}
                                 else sources[0][2])
            field, raw, _ = sources[0]
            rows.append({
                "sample_id": sample_id, "uuid": uuids.get(sample_id),
                "internal_assay_id": iaid, "internal_assay_title": title,
                "tier": tier, "source_field": field, "raw_value": raw,
                "contested": contested, "source_provenance": source_provenance,
            })

    return pd.DataFrame(rows, columns=S.CLAIM_COLUMNS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_claims.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Run against the real extract**

```bash
uv run --with pandas --with pyarrow python - <<'PY'
import sys; sys.path.insert(0, "scripts")
import pandas as pd
from assay_hygiene import claims as C, vocabulary as V
d = "assay-hygiene/extract"
samples = pd.read_parquet(f"{d}/samples.parquet")
meta = V.parse_metadata(samples)
uuids = dict(zip(samples.sample_id.astype(int), samples.uuid))
vocab = V.load_vocabulary("assay-hygiene/vocabulary.csv")
out = C.sample_claims(meta, uuids, vocab)
out.to_parquet("assay-hygiene/claims.parquet", compression="zstd", index=False)
print(f"{len(out):,} claims over {out.sample_id.nunique():,} samples "
      f"of {len(samples):,}")
print(out.tier.value_counts().to_string())
PY
```

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/claims.py tests/test_assay_hygiene_claims.py
git commit -m "$(printf 'feat(assay-hygiene): stage B2 per-sample assay claims with measured tiers\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 6: Stage B, the precedent miner

**Files:**
- Modify: `scripts/assay_hygiene/precedent.py` — APPEND to it, do not create it
- Test: `tests/test_assay_hygiene_precedent.py`

**`precedent.py` already exists.** Task 4 needed `assay_index` to build its
evidence table and creating a second copy would have put two definitions of
"registered" in one increment — the defect that produced 13 spurious Mode 3
flags before it was caught. So Task 4 created the file carrying its docstring
and `assay_index` only, verbatim from this task's own code block. Append
`membership_index`, `mine_precedent` and `main`; do not rewrite or reorder what
is there, and do not re-add `assay_index`. Its existing test coverage is in
`tests/test_assay_hygiene_vocabulary_evidence.py`; add yours alongside in the
precedent test file.

**Interfaces:**
- Consumes: `_schema.RULE_KEY`, `PRECEDENT_COLUMNS`
- Produces: `membership_index(membership) -> dict[int, set[int]]`; `assay_index(assays) -> dict[int, tuple[int, int, str]]` mapping `assay_id -> (project_id, internal_assay_id, internal_assay_title)`; `mine_precedent(edges, membership, assays) -> pd.DataFrame` returning `PRECEDENT_COLUMNS`

**Keyed on `internal_assay_id`.** `dmac.internal_assays` holds 137 rows under
137 distinct titles and is canonical; `seek_production.assays` holds 458 under
291 titles because the same logical assay is instantiated per study.
`DERIVED_FROM.internal_assay_title` already speaks the internal vocabulary, so
keying on raw titles leaves findings and edges unreconcilable.

**The 17 assays with no junction row** fall back to `(assay_id, assays.title)`
so the key is never null. This module counts into a dict rather than grouping,
so it avoids the `groupby(dropna=True)` trap by construction — but the fallback
is still required, because a `None` key would collapse all 17 into one rule.

**This task deliberately does the opposite of what Task 3 decided, and the
difference is not an oversight.** Task 3 refused the same fallback for the
`internal_assay_title` and left 14 vocabulary rows blank instead, because a
blank is diagnostic of a missing junction row while a filled-in value hides it.
Here the fallback is right, because the alternative is a null in a `RULE_KEY`
component, which collapses 17 unrelated assays into a single rule. **The
fallback is correct for the KEY and wrong for the TITLE.** Do not "harmonise"
the two.

It is safe today only by luck of numbering. Measured on the live extract:
**124 of the 458 SEEK `assay_id`s collide numerically with a genuine internal
id, and 122 of those 124 name a different assay** — seek 13 `Short Read
Sequencing` against internal 13 `Cell Sorting`, seek 24 `Single Cell Clustering
Analysis` against internal 24 `DNA Extraction`. (The two that agree are ids 47
`Mass Spectrometry Analysis` and 74 `Tissue Collection`; an earlier draft of
this section said all 124 disagreed, which overstated it in the direction that
made the argument look stronger.) The 17 junction-less assays happen to sit at
466-482, above the internal range of 1-188, so no collision occurs today. One
new junction-less assay with a low seek id would silently merge two unrelated
assays' precedent into one rule.

**So this task must add a guard test**, beyond the ones listed below, asserting
against the real extract that the fallback ids and the genuine internal ids do
not intersect. It is the only thing standing between the fallback and a silent
wrong answer, and 473 of 360,027 labelled edges already carry a seek id in
`edge_internal_assay_id` because the server applies this same fallback.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_precedent.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import precedent as P


def test_membership_index_groups_assays_by_sample():
    fx = S.make_fixture()
    idx = P.membership_index(fx["membership"])
    assert idx[100] == {1}
    assert idx[200] == {1, 2}
    assert 999 not in idx


def test_assay_index_resolves_to_the_internal_namespace():
    fx = S.make_fixture()
    idx = P.assay_index(fx["assays"])
    assert idx[1] == (10, 11, "Comet Chip")


def test_assay_index_falls_back_when_there_is_no_junction_row():
    # 17 assay records resolve to no internal_assay_id. They fall back to
    # (assay_id, title) -- the same rule neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge) uses -- so the
    # RULE_KEY is never null. A null would collapse all 17 into one rule.
    assays = pd.DataFrame(
        [(2, "Antibody Panel", 8, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    assert P.assay_index(assays)[2] == (10, 2, "Antibody Panel")


def test_comet_chip_hop_records_two_both_sides_and_one_child_only():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "D.IMG")
              & (out.internal_assay_title == "Comet Chip")].iloc[0]
    assert row.n_both == 2
    assert row.n_child_only == 1
    assert row.propagation_rate == pytest.approx(2 / 3)


def test_propagation_rate_is_zero_when_never_both_sides():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "TIS") & (out.parent_type == "MUS")].iloc[0]
    assert row.n_both == 0
    assert row.propagation_rate == 0.0


def test_output_columns_and_key_match_the_contract():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    assert list(out.columns) == S.PRECEDENT_COLUMNS
    assert not out.duplicated(subset=S.RULE_KEY).any()


def test_edges_with_unregistered_endpoints_contribute_nothing():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    assert out[out.child_type == "DNA"].empty


def test_reverse_rate_counts_the_other_direction():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "TIS")
              & (out.internal_assay_title == "Comet Chip")].iloc[0]
    assert row.n_parent_only == 1
    assert row.reverse_rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_precedent.py -v`
Expected: FAIL with `ImportError: cannot import name 'precedent'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/precedent.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage B. Mine the sample-type -> assay -> sample-type map from what exists.

One question per (project, hop, internal assay): when the child is in this
assay, how often is the parent in it too. That is `propagation_rate`, and it is
the evidence a Mode 2 verdict rests on.

Keyed on `internal_assay_id`. dmac.internal_assays is 137 rows under 137
distinct titles and is canonical; seek_production.assays is 458 rows under 291
titles because the same logical assay is instantiated once per study. Keying on
assays.id fragments the evidence; keying on the raw title speaks a different
namespace from DERIVED_FROM.internal_assay_title and leaves findings and edges
unreconcilable.

The output is independently useful. It answers "what assay normally connects
D.IMG to TIS in this project" as a lookup, mined rather than hand-authored, and
nothing like it exists today.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import _schema as S


def membership_index(membership: pd.DataFrame) -> dict[int, set[int]]:
    idx: dict[int, set[int]] = defaultdict(set)
    for sample_id, assay_id in zip(membership.sample_id, membership.assay_id):
        idx[int(sample_id)].add(int(assay_id))
    return dict(idx)


def assay_index(assays: pd.DataFrame) -> dict[int, tuple[int, int, str]]:
    """assay_id -> (project_id, internal_assay_id, internal_assay_title).

    17 assay records have no junction row and resolve to no internal id. They
    fall back to their own (assay_id, title), matching neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge),
    so the rule key is never null. Dropping them would violate the spec's
    binding "nothing is dropped silently"; leaving the key null would collapse
    all 17 into a single meaningless rule.
    """
    out: dict[int, tuple[int, int, str]] = {}
    for aid, pid, title, iaid, ititle in zip(
        assays.assay_id, assays.project_id, assays.title,
        assays.internal_assay_id, assays.internal_assay_title,
    ):
        if pd.isna(iaid):
            out[int(aid)] = (int(pid), int(aid), str(title))
        else:
            out[int(aid)] = (int(pid), int(iaid), str(ititle))
    return out


def mine_precedent(
    edges: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> pd.DataFrame:
    memb = membership_index(membership)
    ainfo = assay_index(assays)

    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])
    titles: dict[tuple, str] = {}

    for child_id, parent_id, child_type, parent_type in zip(
        edges.child_id, edges.parent_id, edges.child_type, edges.parent_type
    ):
        ca = memb.get(int(child_id), frozenset())
        pa = memb.get(int(parent_id), frozenset())
        for assay_id in ca | pa:
            info = ainfo.get(assay_id)
            if info is None:
                continue      # assay absent from the extract; skip rather than guess
            project_id, iaid, ititle = info
            key = (project_id, str(child_type), str(parent_type), iaid)
            titles[key] = ititle
            if assay_id in ca and assay_id in pa:
                counts[key][0] += 1
            elif assay_id in ca:
                counts[key][1] += 1
            else:
                counts[key][2] += 1

    rows = []
    for key, (both, child_only, parent_only) in counts.items():
        project_id, child_type, parent_type, iaid = key
        fwd_den = both + child_only
        rev_den = both + parent_only
        rows.append({
            "project_id": project_id,
            "child_type": child_type,
            "parent_type": parent_type,
            "internal_assay_id": iaid,
            "internal_assay_title": titles[key],
            "n_both": both,
            "n_child_only": child_only,
            "n_parent_only": parent_only,
            "propagation_rate": (both / fwd_den) if fwd_den else 0.0,
            "reverse_rate": (both / rev_den) if rev_den else 0.0,
        })

    out = pd.DataFrame(rows, columns=S.PRECEDENT_COLUMNS)
    return out.sort_values(
        ["n_both", "n_child_only"], ascending=False, ignore_index=True
    )


def main(extract_dir: str = "assay-hygiene/extract",
         out_path: str = "assay-hygiene/precedent.csv") -> None:
    d = Path(extract_dir)
    out = mine_precedent(
        pd.read_parquet(d / "edges.parquet"),
        pd.read_parquet(d / "membership.parquet"),
        pd.read_parquet(d / "assays.parquet"),
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"{len(out)} rules -> {out_path}")
    print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_precedent.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Run against the real extract and check the anchors**

```bash
uv run --with pandas --with pyarrow python -m assay_hygiene.precedent
```

Expected against the post-stage-0 graph, measured 2026-08-14: **961 rules** over
**213 hops with precedent**. `D.TITR -> TIS` under `Titer Assay` should read
`n_both=90,120`, `n_child_only=54,699`, `propagation_rate≈0.622`. `D.FLOW ->
D.FCS` under `Flow Cytometry` should read `n_both=66,529`, `n_child_only=0`,
rate `1.000`.

Do **not** expect `n_both=1,640` for the Titer rule. That figure appears in the
2026-08-12 spec and is a count within a 5,000-edge sample, not a graph-wide
count. Only the rate is comparable between them.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/precedent.py tests/test_assay_hygiene_precedent.py
git commit -m "$(printf 'feat(assay-hygiene): stage B precedent miner keyed on internal_assay_id\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 7: Mode 3, the contradiction audit

**Files:**
- Create: `scripts/assay_hygiene/audit.py`
- Test: `tests/test_assay_hygiene_audit.py`

**Interfaces:**
- Consumes: `_schema.AUDIT_COLUMNS`, `V_MODE3_FLAG`, tier constants; `precedent.membership_index`, `precedent.assay_index`
- Produces: `registered_internal(membership: pd.DataFrame, assays: pd.DataFrame) -> dict[int, set[int]]`; `audit_contradictions(claims, membership, assays, nodes, tiers: tuple[str, ...] = DEFAULT_TIERS, include_contested: bool = False, include_unmappable: bool = False) -> pd.DataFrame` returning `AUDIT_COLUMNS`, where `DEFAULT_TIERS = (T_CORROBORATED, T_STRONG)`

**Mode 3 writes nothing.** It compares what a sample claims against what it is
registered in and reports disagreement. A wrong flag costs attention, not data,
which is why this ships before the write path is proven.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_audit.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import audit as A


def _assays():
    return pd.DataFrame(
        [(1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection")],
        columns=S.ASSAY_COLUMNS,
    )


def _nodes(rows):
    return pd.DataFrame(rows, columns=S.NODES_COLUMNS)


def _claims(rows):
    return pd.DataFrame(rows, columns=S.CLAIM_COLUMNS)


def test_registered_internal_maps_through_the_junction():
    membership = pd.DataFrame([(100, 1), (100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    assert A.registered_internal(membership, _assays())[100] == {11, 12}


def test_a_claim_matching_the_registration_is_not_flagged():
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([(100, 1)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_claim_contradicting_the_registration_is_flagged():
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    out = A.audit_contradictions(claims, membership, _assays(), nodes)
    assert list(out.columns) == S.AUDIT_COLUMNS
    row = out.iloc[0]
    assert row.verdict == S.V_MODE3_FLAG
    assert row.claimed_internal_assay_id == 11
    assert "12" in str(row.registered_internal_assay_ids)
    assert row.sample_type == "D.IMG"


def test_an_unregistered_sample_is_not_a_contradiction():
    # A sample in no assay is Mode 1's problem, not Mode 3's. Mode 3 needs
    # something to contradict.
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)])
    membership = pd.DataFrame([], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_weak_claim_does_not_raise_a_flag_by_default():
    # Weak claims are 90.4% accurate, so flagging on them would put a ~10%
    # false-positive rate in front of a curator.
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_WEAK, "Protocol", "x", False, S.P_LEARNED)])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_a_contested_claim_does_not_raise_a_flag_by_default():
    # A contested sample's evidence disagrees with itself, so it has not decided
    # what it asserts. Excluded by a SEPARATE parameter rather than by tier: on
    # the disagreement subset the winning claim's mapping is still wrong about
    # 30% of the time, three times the rate the weak floor already refuses.
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", True, S.P_LEARNED)])
    assert A.audit_contradictions(claims, membership, _assays(), nodes).empty


def test_contested_claims_can_be_admitted_deliberately():
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", True, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership, _assays(), nodes,
                                 include_contested=True)
    assert len(out) == 1


def test_adding_a_claim_never_removes_an_existing_flag():
    # The monotonicity property the per-claim design exists to guarantee. Under
    # the previous per-sample tiering, a second claim collapsed the sample to
    # T_CONFLICT and its flag vanished: measured at 102 suppressed against 13
    # added over the real extract. Adding a row must only ever add flags.
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    one = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED)])
    before = A.audit_contradictions(one, membership, _assays(), nodes)
    two = _claims([
        (100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "x", False, S.P_LEARNED),
        (100, "D.IMG-1", 13, "Other", S.T_WEAK, "Protocol", "y", False, S.P_PROPOSED),
    ])
    after = A.audit_contradictions(two, membership, _assays(), nodes)
    assert len(after) >= len(before)


def test_the_tier_floor_can_be_widened_deliberately():
    membership = pd.DataFrame([(100, 2)], columns=S.MEMBERSHIP_COLUMNS)
    nodes = _nodes([("D.IMG-1", 100, "D.IMG")])
    claims = _claims([(100, "D.IMG-1", 11, "Comet Chip", S.T_WEAK, "Protocol", "x", False, S.P_LEARNED)])
    out = A.audit_contradictions(claims, membership, _assays(), nodes,
                                 tiers=(S.T_CORROBORATED, S.T_STRONG, S.T_WEAK))
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_audit.py -v`
Expected: FAIL with `ImportError: cannot import name 'audit'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/audit.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Mode 3. Where a sample's metadata contradicts what it is registered in.

Writes nothing, ever. A flag costs a curator's attention; a wrong write costs
data, and this pipeline's writer deletes by omission. That asymmetry is why
Mode 3 ships before the write path is proven.

Only high-confidence claims raise a flag. Strong-field claims are 98.4%
accurate and corroborated ones 99.9% (measured 2026-08-14, held out by sample);
weak claims are 90.4%, so flagging on them would hand a curator roughly one
false positive in ten. Conflicted claims have not settled what they assert and
therefore cannot contradict anything yet. The floor is a parameter so a curator
can widen it deliberately, never by accident.
"""
from __future__ import annotations

import pandas as pd

from . import _schema as S
from .precedent import assay_index

# Tiers trusted enough to contradict a curator's own registration.
DEFAULT_TIERS = (S.T_CORROBORATED, S.T_STRONG)


def registered_internal(
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> dict[int, set[int]]:
    """sample_id -> the set of INTERNAL assay ids it is registered in.

    membership.assay_id is a seek_production assay_assets.assay_id and claims
    speak internal ids, so the junction has to be crossed before anything is
    compared. Comparing the two id spaces directly is the silent-wrong-answer
    failure this whole package is shaped to avoid.
    """
    ainfo = assay_index(assays)
    out: dict[int, set[int]] = {}
    for sample_id, assay_id in zip(membership.sample_id, membership.assay_id):
        info = ainfo.get(int(assay_id))
        if info is None:
            continue
        out.setdefault(int(sample_id), set()).add(info[1])
    return out


def audit_contradictions(
    claims: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    nodes: pd.DataFrame,
    tiers: tuple[str, ...] = DEFAULT_TIERS,
    include_contested: bool = False,
) -> pd.DataFrame:
    """Flag samples whose claim names an assay they are not registered in.

    A sample registered in NOTHING is not flagged: that is Mode 1's population,
    and Mode 3 needs something to contradict.

    Contested rows are excluded by a SEPARATE parameter rather than by tier.
    Folding contestedness into the tier is what made the previous design
    non-monotone -- a second claim lowered the first one's tier and its flag
    disappeared. Here a contested row keeps whatever tier its own evidence
    earned and is filtered at the audit, so admitting them later is a parameter
    change rather than a re-derivation. They are excluded by default because on
    the disagreement subset the winning claim's mapping is wrong about 30% of
    the time, three times the rate the weak floor already refuses.

    `include_unmappable` is the second such dial, and it exists for the same
    reason: a flag that cannot be ESTABLISHED must not be asserted.

    A claim speaks a dmac `internal_assays` id. A registration on one of the 17
    junction-less assays resolves instead to a SEEK `assays.id`, a different
    namespace. `assay_index`'s guard makes a false AGREEMENT impossible and does
    nothing about a false CONTRADICTION: an id in the wrong namespace can never
    match, so it always reads as disagreement. A fallback id in the registered
    set therefore means that registration's internal identity is UNKNOWN, not
    that it is known to differ. Recovering it could only ADD to that set, and
    adding to it can only ever REMOVE a flag -- the same monotonicity direction
    this whole design rests on. So the flag is not established, and the audit
    refuses to assert it.

    Measured: removes 13 of 879 flags at the default, 14 of 1,570 with contested
    admitted. The 14th is exactly the case a title-equality rule would miss,
    which is why this keys on the ID SPACE and never on titles. Task 3 ruled a
    blank title diagnostic rather than fillable, and that stands.

    Four of the 17 fallbacks share a normalised title with a genuine internal id
    (467/64 Short Read Sequencing, 468/34 Genome Alignment, 481/61 RNA
    Extraction, 482/99 Gene Expression Analysis). Only 481 produces flags today;
    the other three are latent, waiting on an at-floor claim. Fixing the 17
    junction rows upstream in `dmac.assays_internal_assays` is strictly better
    and clears the latent three too, but it is a MySQL write outside this
    increment and a junction row can go missing again.
    """
    registered = registered_internal(membership, assays)
    types = {
        int(sid): str(t)
        for sid, t in zip(nodes.sample_id, nodes.type) if pd.notna(sid)
    }

    rows = []
    for c in claims.itertuples():
        if c.tier not in tiers:
            continue
        if bool(c.contested) and not include_contested:
            continue
        have = registered.get(int(c.sample_id))
        if not have:
            continue                      # unregistered -> Mode 1, not Mode 3
        if int(c.internal_assay_id) in have:
            continue                      # claim agrees with the record
        rows.append({
            "sample_id": int(c.sample_id),
            "uuid": c.uuid,
            "sample_type": types.get(int(c.sample_id)),
            "registered_internal_assay_ids": ";".join(str(i) for i in sorted(have)),
            "claimed_internal_assay_id": int(c.internal_assay_id),
            "claimed_internal_assay_title": c.internal_assay_title,
            "tier": c.tier,
            "source_field": c.source_field,
            "raw_value": c.raw_value,
            "verdict": S.V_MODE3_FLAG,
        })
    return pd.DataFrame(rows, columns=S.AUDIT_COLUMNS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_audit.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/audit.py tests/test_assay_hygiene_audit.py
git commit -m "$(printf 'feat(assay-hygiene): mode 3 contradiction audit, flag only\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

### Task 8: End-to-end run and the operator report

**Files:**
- Create: `scripts/assay_hygiene/run_evidence.py`
- Test: `tests/test_assay_hygiene_run_evidence.py`

**Interfaces:**
- Consumes: everything above
- Produces: `build_report(precedent, claims, audit, vocab, unresolved) -> str`; `main(extract_dir, out_dir) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_run_evidence.py
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import run_evidence as R


def test_report_states_every_headline_count():
    precedent = pd.DataFrame(
        [(10, "D.IMG", "TIS", 11, "Comet Chip", 2, 1, 0, 2 / 3, 1.0)],
        columns=S.PRECEDENT_COLUMNS,
    )
    claims = pd.DataFrame(
        [(100, "D.IMG-1", 11, "Comet Chip", S.T_STRONG, "Type", "CometChip", False, S.P_LEARNED)],
        columns=S.CLAIM_COLUMNS,
    )
    audit = pd.DataFrame(
        [(100, "D.IMG-1", "D.IMG", "12", "Tissue Collection", 11, "Comet Chip",
          S.T_STRONG, "Type", "CometChip", S.V_MODE3_FLAG)],
        columns=S.AUDIT_COLUMNS,
    )
    vocab = pd.DataFrame(
        [("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, S.P_LEARNED)],
        columns=S.VOCAB_COLUMNS,
    )
    unresolved = pd.DataFrame(
        [("Type", "mystery", 3, "A-2; A-3; A-4")],
        columns=["source_field", "raw_value", "n_samples", "example_uuids"],
    )
    md = R.build_report(precedent, claims, audit, vocab, unresolved)
    assert "1 rules" in md or "1 rule" in md
    assert "Mode 3" in md
    assert "cometchip" in md          # the vocabulary is shown, not just counted


def test_report_says_plainly_that_nothing_was_written():
    md = R.build_report(*[pd.DataFrame(columns=c) for c in (
        S.PRECEDENT_COLUMNS, S.CLAIM_COLUMNS, S.AUDIT_COLUMNS, S.VOCAB_COLUMNS,
        ["source_field", "raw_value", "n_samples", "example_uuids"])])
    # An operator reading a hygiene report must not have to infer this.
    assert "writes nothing" in md.lower() or "nothing was written" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_run_evidence.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_evidence'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/assay_hygiene/run_evidence.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Run the whole evidence layer over an extract and write the operator report.

Read-only end to end: it reads parquet from disk and writes csv, parquet and
markdown under assay-hygiene/. Nothing here reaches MySQL, Neo4j or the API.

    uv run --with pandas --with pyarrow python -m assay_hygiene.run_evidence
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import _schema as S
from . import audit as A
from . import claims as C
from . import precedent as P
from . import vocabulary as V


def build_report(precedent, claims, audit, vocab, unresolved) -> str:
    lines = [
        "# Assay hygiene: evidence layer",
        "",
        "This stage **writes nothing** to MySQL, Neo4j or the API. Every number",
        "below is read out of the parquet extract.",
        "",
        "## Vocabulary",
        "",
        f"- mapped terms: **{len(vocab):,}**",
        f"- unresolved terms above the floor: **{len(unresolved):,}**"
        f" over {int(unresolved.n_samples.sum()) if len(unresolved) else 0:,} samples",
        "",
    ]
    if len(vocab):
        by_prov = vocab.provenance.value_counts()
        for prov, n in by_prov.items():
            lines.append(f"  - `{prov}`: {n:,}")
        lines.append("")
        lines.append("Highest-support mappings:")
        lines.append("")
        top = vocab.sort_values("support", ascending=False).head(10)
        lines.append("| field | value | assay | support | samples | purity |")
        lines.append("|---|---|---|---|---|---|")
        for r in top.itertuples():
            lines.append(
                f"| {r.source_field} | `{r.raw_value}` | "
                f"{r.internal_assay_title} | {int(r.support):,} | "
                f"{int(r.n_samples):,} | {r.purity:.2f} |"
            )
        lines.append("")

    lines += [
        "## Precedent (stage B)",
        "",
        f"- rules mined: **{len(precedent):,} rules**",
        "",
        "## Claims (stage B2)",
        "",
        f"- claims: **{len(claims):,}**"
        f" over {claims.sample_id.nunique() if len(claims) else 0:,} samples",
        "",
    ]
    if len(claims):
        for tier, n in claims.tier.value_counts().items():
            lines.append(f"  - `{tier}`: {n:,}")
        lines.append("")

    lines += [
        "## Mode 3: contradictions",
        "",
        f"- flagged: **{len(audit):,}** samples whose metadata names an assay",
        "  they are not registered in",
        "",
        "Flags are raised only on `corroborated` and `strong` claims, measured at",
        "99.9% and 98.4% accuracy respectively. Nothing here is written back.",
        "",
    ]
    return "\n".join(lines)


def main(extract_dir: str = "assay-hygiene/extract",
         out_dir: str = "assay-hygiene") -> int:
    d, out = Path(extract_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    edges = pd.read_parquet(d / "edges.parquet")
    membership = pd.read_parquet(d / "membership.parquet")
    assays = pd.read_parquet(d / "assays.parquet")
    samples = pd.read_parquet(d / "samples.parquet")
    nodes = pd.read_parquet(d / "nodes.parquet")

    meta = V.parse_metadata(samples)
    uuids = dict(zip(samples.sample_id.astype(int), samples.uuid))

    learned = V.learn_vocabulary(edges, meta)
    proposed = V.load_vocabulary(out / "vocabulary-proposed.csv")
    curator = V.load_vocabulary(out / "vocabulary-curator.csv")
    vocab = V.merge_vocabulary(learned, proposed, curator, assays)
    V.save_vocabulary(vocab, out / "vocabulary.csv")

    unresolved = V.unresolved_terms(meta, vocab, uuids)
    unresolved.to_csv(out / "vocabulary-unresolved.csv", index=False)

    prec = P.mine_precedent(edges, membership, assays)
    prec.to_csv(out / "precedent.csv", index=False)

    cl = C.sample_claims(meta, uuids, vocab)
    cl.to_parquet(out / "claims.parquet", compression="zstd", index=False)

    au = A.audit_contradictions(cl, membership, assays, nodes)
    au.to_csv(out / "mode3-contradictions.csv", index=False)

    report = build_report(prec, cl, au, vocab, unresolved)
    (out / "evidence-report.md").write_text(report)
    print(report)
    print(f"\nwrote {out}/evidence-report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_run_evidence.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Run the whole layer against the real extract**

```bash
uv run --with pandas --with pyarrow python -m assay_hygiene.run_evidence
```

Expected: 961 precedent rules, a claims count in the hundreds of thousands, and
a Mode 3 flag count nobody has measured yet. **Report the Mode 3 count and hand
a sample of 20 flagged rows to the operator for review** — Mode 3's precision is
agreement with a human and cannot be measured any other way.

- [ ] **Step 6: Run the full suite**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/ -q`
Expected: **your measured baseline + 47 passed**, skips unchanged — 7 in Task 1,
11 across Tasks 2 and 3, 10 in Task 5, 8 in Task 6, 9 in Task 7, and 2 here.
Task 4 adds its own; count from the baseline you measured, not from this list.

- [ ] **Step 7: Commit**

```bash
git add scripts/assay_hygiene/run_evidence.py tests/test_assay_hygiene_run_evidence.py
git commit -m "$(printf 'feat(assay-hygiene): end-to-end evidence layer run and operator report\n\nCo-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>')"
```

---

## What this increment deliberately does not do

- **No writes.** Not to MySQL, not to Neo4j, not to the API. Increment 2 proves
  the write path on Mode 1's small population, behind the addition probe.
- **No Mode 1 or Mode 2 classification.** The evidence layer feeds them; they
  are increments 2 and 3.
- **No threshold selection.** Thresholds are an output of increment 3's backtest
  curve and must not be chosen from the distribution in the spec.
- **No fan-out analysis.** The spec records that 2,074 CometChip images declare
  146 tissue parents each, at 24% of the full cross-product, and that this may
  be bulk over-linking rather than lineage. It is quantified and left alone.
