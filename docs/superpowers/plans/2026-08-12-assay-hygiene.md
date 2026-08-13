# Assay Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a six-stage pipeline that mines assay-membership precedent from SEEK production, classifies every `DERIVED_FROM` edge as clean or defective, and emits a curator-approvable rule sheet that expands into guarded API writes.

**Architecture:** Stage A runs inside the production `nextseek` container and writes parquet; stages B through E are pure local transforms over those files; stage F writes back over HTTPS. Every stage is a standalone `uv run --script` CLI plus an importable pure function, so the transforms are unit-testable without any database.

**Tech Stack:** Python 3.11+, pandas, pyarrow, openpyxl, pytest. PEP 723 inline dependency blocks, matching every other script in `scripts/`.

**Spec:** `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md`

## Global Constraints

- **P1 sentinel:** scripts must never create, modify, or delete anything inside the plugin checkout. All project paths resolve from the current working directory. `tests/conftest.py::plugin_sentinel` enforces this and will fail the suite otherwise.
- **Output root** is `assay-hygiene/` under the current working directory.
- **PEP 723 header** on every script: `requires-python = ">=3.11"` plus explicit dependencies.
- **Test command:** `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/<file> -v`
- **Read by SQL and neo4j, write by API.** Never write to MySQL or neo4j directly.
- **Dry run is the default.** `--write` must be explicit and never inferred.
- **Rule key is `(project_id, child_type, parent_type, assay_title)`.** Title, not `assay_id`: 458 assay records share 291 titles.
- **Propagation metric:** `propagation_rate = n_both / (n_both + n_child_only)`.
- **Verified SQL join path:** `assays -> studies -> investigations -> investigations_projects -> projects`. The `investigations` table has no `project_id` column.
- **Correct Django DB alias is `seek`** (`seek_production`). The `default` alias is `dmac` and its `assay_assets` table is empty.

---

### Task 1: Column contracts and test fixtures

**Files:**
- Create: `scripts/assay_hygiene/__init__.py`
- Create: `scripts/assay_hygiene/_schema.py`
- Test: `tests/test_assay_hygiene_schema.py`

**Interfaces:**
- Consumes: nothing
- Produces: `EDGE_COLUMNS`, `MEMBERSHIP_COLUMNS`, `ASSAY_COLUMNS`, `SAMPLE_COLUMNS`, `PRECEDENT_COLUMNS`, `FINDING_COLUMNS`, `RULE_COLUMNS` (all `list[str]`); verdict constants `V_CLEAN`, `V_MODE1_CHILD`, `V_MODE1_PARENT`, `V_MODE1_BOTH_DARK`, `V_MODE2_PROPAGATE`, `V_MODE2_AMBIGUOUS`, `V_MODE3_FLAG` (all `str`); action constants `A_NONE`, `A_ADD_PARENT`, `A_ADD_CHILD`, `A_ADD_TO_ASSAY`, `A_FLAG_ONLY` (all `str`); `make_fixture() -> dict[str, pandas.DataFrame]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_schema.py
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S


def test_verdict_constants_are_distinct():
    verdicts = [S.V_CLEAN, S.V_MODE1_CHILD, S.V_MODE1_PARENT,
                S.V_MODE1_BOTH_DARK, S.V_MODE2_PROPAGATE,
                S.V_MODE2_AMBIGUOUS, S.V_MODE3_FLAG]
    assert len(set(verdicts)) == len(verdicts)


def test_rule_key_is_title_not_assay_id():
    # 458 assay records share 291 titles; keying on id shatters precedent
    assert S.RULE_KEY == ["project_id", "child_type", "parent_type", "assay_title"]
    assert "assay_id" not in S.RULE_KEY


def test_precedent_columns_carry_both_directions():
    for col in ("n_both", "n_child_only", "n_parent_only",
                "propagation_rate", "reverse_rate"):
        assert col in S.PRECEDENT_COLUMNS


def test_fixture_shapes_match_declared_columns():
    fx = S.make_fixture()
    assert list(fx["edges"].columns) == S.EDGE_COLUMNS
    assert list(fx["membership"].columns) == S.MEMBERSHIP_COLUMNS
    assert list(fx["assays"].columns) == S.ASSAY_COLUMNS


def test_fixture_encodes_the_four_canonical_situations():
    fx = S.make_fixture()
    # 1 propagating hop, 1 non-propagating hop, 1 dark child, 1 dark pair
    assert len(fx["edges"]) == 6
    assert set(fx["assays"]["title"]) == {"Comet Chip", "Tissue Collection"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'assay_hygiene'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/__init__.py
"""Assay hygiene pipeline. See docs/superpowers/specs/2026-08-12-assay-hygiene-design.md"""
```

```python
# scripts/assay_hygiene/_schema.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Column contracts and verdict vocabulary shared by every assay-hygiene stage.

Keeping these in one place is what lets stages B-E be pure functions over
DataFrames with no database access, and what keeps task N+1 from inventing a
column name task N never wrote.
"""
from __future__ import annotations

import pandas as pd

# --- extract (stage A) -------------------------------------------------------
EDGE_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "edge_assay_id", "edge_assay_title", "edge_protocol_id",
]
MEMBERSHIP_COLUMNS = ["sample_id", "assay_id"]
ASSAY_COLUMNS = [
    "assay_id", "title", "sample_type_id", "study_id",
    "investigation_id", "project_id", "project_title",
]
SAMPLE_COLUMNS = ["sample_id", "uuid", "json_metadata", "created_at", "project_ids"]

# --- precedent (stage B) -----------------------------------------------------
RULE_KEY = ["project_id", "child_type", "parent_type", "assay_title"]
PRECEDENT_COLUMNS = RULE_KEY + [
    "n_both", "n_child_only", "n_parent_only",
    "propagation_rate", "reverse_rate",
]

# --- classify (stage C) ------------------------------------------------------
FINDING_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "verdict", "matched_assay_title", "matched_rate",
    "target_assay_id", "project_id",
    # every assay title the child belongs to; stage D's tiebreak needs this and
    # cannot recover it later, because membership is not carried into findings
    "candidates",
]

# --- emit (stage E) ----------------------------------------------------------
RULE_COLUMNS = PRECEDENT_COLUMNS + [
    "verdict", "action", "affected_count", "decided_by", "rationale",
    "APPROVE", "NOTES",
]

# --- vocabulary --------------------------------------------------------------
V_CLEAN = "CLEAN"
V_MODE1_CHILD = "MODE_1_CHILD"
V_MODE1_PARENT = "MODE_1_PARENT"
V_MODE1_BOTH_DARK = "MODE_1_BOTH_DARK"
V_MODE2_PROPAGATE = "MODE_2_PROPAGATE"
V_MODE2_AMBIGUOUS = "MODE_2_AMBIGUOUS"
V_MODE3_FLAG = "MODE_3_FLAG"

A_NONE = "NONE"
A_ADD_PARENT = "ADD_PARENT_TO_ASSAY"
A_ADD_CHILD = "ADD_CHILD_TO_ASSAY"
A_ADD_TO_ASSAY = "ADD_TO_ASSAY"
A_FLAG_ONLY = "FLAG_ONLY"


def make_fixture() -> dict[str, pd.DataFrame]:
    """A six-edge synthetic world covering every branch of stage C.

    assay 1 "Comet Chip"        project 10, propagating   (D.IMG -> TIS)
    assay 2 "Tissue Collection" project 10, non-propagating

    samples: 100/101 D.IMG children, 200/201 TIS parents,
             300 dark child, 400 dark parent
    """
    edges = pd.DataFrame(
        [
            # both registered in Comet Chip -> establishes propagation precedent
            (100, 200, "D.IMG-1", "TIS-1", "D.IMG", "TIS", 1, "Comet Chip", None),
            (101, 201, "D.IMG-2", "TIS-2", "D.IMG", "TIS", 1, "Comet Chip", None),
            # child in Comet Chip, parent only in Tissue Collection -> dark, mode 2
            (102, 202, "D.IMG-3", "TIS-3", "D.IMG", "TIS", None, None, None),
            # TIS -> MUS where precedent says it does not propagate -> CLEAN
            (203, 500, "TIS-4", "MUS-1", "TIS", "MUS", None, None, None),
            # child registered nowhere -> mode 1 child
            (300, 200, "DNA-1", "TIS-1", "DNA", "TIS", None, None, None),
            # neither endpoint registered -> mode 1 both dark
            (301, 400, "DNA-2", "TIS-9", "DNA", "TIS", None, None, None),
        ],
        columns=EDGE_COLUMNS,
    )
    membership = pd.DataFrame(
        [
            (100, 1), (200, 1),          # both in Comet Chip
            (101, 1), (201, 1),          # both in Comet Chip
            (102, 1), (202, 2),          # disjoint -> the mode 2 case
            (203, 2), (500, 1),          # disjoint, but hop does not propagate
            (200, 2), (201, 2),          # parents also in Tissue Collection
        ],
        columns=MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP"),
        ],
        columns=ASSAY_COLUMNS,
    )
    samples = pd.DataFrame(
        [
            (100, "D.IMG-1", '{"Protocol": "/sops/5", "Name": "img1"}', None, "10"),
            (300, "DNA-1", '{"Protocol": "/sops/9", "Name": "dna1"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
    return {"edges": edges, "membership": membership,
            "assays": assays, "samples": samples}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_schema.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/__init__.py scripts/assay_hygiene/_schema.py tests/test_assay_hygiene_schema.py
git commit -m "feat(assay-hygiene): column contracts, verdict vocabulary, synthetic fixture"
```

---

### Task 2: Stage A extractor

**Files:**
- Create: `scripts/assay_hygiene/extract.py`
- Test: `tests/test_assay_hygiene_extract.py`

**Interfaces:**
- Consumes: `_schema.EDGE_COLUMNS`, `MEMBERSHIP_COLUMNS`, `ASSAY_COLUMNS`, `SAMPLE_COLUMNS`
- Produces: `EDGES_CYPHER: str`, `MEMBERSHIP_SQL: str`, `ASSAYS_SQL: str`, `SAMPLES_SQL: str`, `write_outputs(outdir: pathlib.Path, frames: dict[str, pandas.DataFrame]) -> list[pathlib.Path]`

This script is the only one that runs in-container. It cannot be unit tested against a live database, so the tests pin the query text (which is where the two schema bugs found during design would have bitten) and exercise the writer against the fixture.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_extract.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import extract as E


def test_assays_sql_uses_the_join_table_not_a_project_id_column():
    # investigations has NO project_id; verified against seek_production 2026-08-12
    sql = E.ASSAYS_SQL
    assert "investigations_projects" in sql
    assert "i.project_id" not in sql


def test_membership_sql_filters_to_sample_assets():
    assert "asset_type = 'Sample'" in E.MEMBERSHIP_SQL


def test_samples_sql_pulls_json_metadata_and_project_scope():
    assert "json_metadata" in E.SAMPLES_SQL
    assert "projects_samples" in E.SAMPLES_SQL


def test_edges_cypher_returns_every_declared_edge_column():
    for col in S.EDGE_COLUMNS:
        assert col in E.EDGES_CYPHER


def test_write_outputs_emits_one_parquet_per_frame(tmp_path):
    frames = S.make_fixture()
    written = E.write_outputs(tmp_path, frames)
    assert len(written) == 4
    for p in written:
        assert p.exists()
        assert p.suffix == ".parquet"
    back = pd.read_parquet(tmp_path / "edges.parquet")
    assert list(back.columns) == S.EDGE_COLUMNS
    assert len(back) == 6


def test_write_outputs_creates_the_directory(tmp_path):
    target = tmp_path / "nested" / "extract"
    E.write_outputs(target, S.make_fixture())
    assert (target / "assays.parquet").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_extract.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/extract.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage A. Extract edges, membership, assays and samples to parquet.

Runs INSIDE the nextseek container so it inherits the configured `seek`
connection and NEO4J_DATABASE settings. No credential is read or stored here.

    ssh fairdata 'docker exec -i nextseek uv run manage.py shell' < extract.py

Then copy assay-hygiene-extract/ out with docker cp + scp.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import _schema as S

EDGES_CYPHER = """
MATCH (c:Sample)-[r:DERIVED_FROM]->(p:Sample)
RETURN c.id   AS child_id,   p.id   AS parent_id,
       c.UID  AS child_uuid, p.UID  AS parent_uuid,
       c.type AS child_type, p.type AS parent_type,
       r.internal_assay_id    AS edge_assay_id,
       r.internal_assay_title AS edge_assay_title,
       r.protocol_id          AS edge_protocol_id
"""

MEMBERSHIP_SQL = """
SELECT asset_id AS sample_id, assay_id
FROM assay_assets
WHERE asset_type = 'Sample'
"""

# investigations has no project_id: the link is the investigations_projects
# join table. Getting this wrong silently drops every row.
ASSAYS_SQL = """
SELECT a.id AS assay_id, a.title, a.sample_type_id, a.study_id,
       i.id AS investigation_id, ip.project_id, p.title AS project_title
FROM assays a
JOIN studies s                  ON s.id  = a.study_id
JOIN investigations i           ON i.id  = s.investigation_id
JOIN investigations_projects ip ON ip.investigation_id = i.id
JOIN projects p                 ON p.id  = ip.project_id
"""

SAMPLES_SQL = """
SELECT s.id AS sample_id, s.uuid, s.json_metadata, s.created_at,
       GROUP_CONCAT(ps.project_id) AS project_ids
FROM samples s
LEFT JOIN projects_samples ps ON ps.sample_id = s.id
GROUP BY s.id
"""

_FRAME_ORDER = [
    ("edges", S.EDGE_COLUMNS),
    ("membership", S.MEMBERSHIP_COLUMNS),
    ("assays", S.ASSAY_COLUMNS),
    ("samples", S.SAMPLE_COLUMNS),
]


def write_outputs(outdir: Path, frames: dict[str, pd.DataFrame]) -> list[Path]:
    """Write one parquet per frame, column order pinned to the schema."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, cols in _FRAME_ORDER:
        df = frames[name][cols]
        path = outdir / f"{name}.parquet"
        df.to_parquet(path, index=False, compression="zstd")
        written.append(path)
    return written


def _sql(alias: str, query: str, columns: list[str]) -> pd.DataFrame:
    from django.db import connections
    with connections[alias].cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def _cypher(query: str, columns: list[str]) -> pd.DataFrame:
    from django.conf import settings
    from neo4j import GraphDatabase
    cfg = settings.NEO4J_DATABASE
    driver = GraphDatabase.driver(cfg["URI"], auth=cfg["AUTH"])
    try:
        with driver.session(database=cfg["NAME"]) as sess:
            rows = [tuple(rec[c] for c in columns) for rec in sess.run(query)]
    finally:
        driver.close()
    return pd.DataFrame(rows, columns=columns)


def main(outdir: str = "/tmp/assay-hygiene-extract") -> None:
    frames = {
        "edges": _cypher(EDGES_CYPHER, S.EDGE_COLUMNS),
        "membership": _sql("seek", MEMBERSHIP_SQL, S.MEMBERSHIP_COLUMNS),
        "assays": _sql("seek", ASSAYS_SQL, S.ASSAY_COLUMNS),
        "samples": _sql("seek", SAMPLES_SQL, S.SAMPLE_COLUMNS),
    }
    for name, df in frames.items():
        print(f"{name}: {len(df)} rows")
    for path in write_outputs(Path(outdir), frames):
        print("wrote", path)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/assay-hygiene-extract")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_extract.py -v`
Expected: 6 passed

- [ ] **Step 5: Live smoke run against production (read-only)**

```bash
cd /home/cdemurjian/code/dmac/curation_skill
tar cf - scripts/assay_hygiene | ssh fairdata 'cat > /tmp/ah.tar'
ssh fairdata 'docker cp /tmp/ah.tar nextseek:/tmp/ah.tar'
ssh fairdata 'docker exec -i nextseek bash -lc "cd /tmp && tar xf ah.tar && uv run python -c \"
import django, os
os.environ.setdefault(\\\"DJANGO_SETTINGS_MODULE\\\",\\\"dmac.settings\\\")
django.setup()
import sys; sys.path.insert(0,\\\"/tmp/scripts\\\")
from assay_hygiene import extract; extract.main()
\""'
```

Expected row counts, which double as the assertion that the SQL is right:
`edges: 704059`, `membership: 214489`, `assays: 458`, `samples: 163393`.
If `assays` returns 0, the `investigations_projects` join is broken.

- [ ] **Step 6: Pull the artifacts down**

```bash
ssh fairdata 'docker cp nextseek:/tmp/assay-hygiene-extract /tmp/assay-hygiene-extract'
mkdir -p assay-hygiene
scp -r fairdata:/tmp/assay-hygiene-extract assay-hygiene/extract
du -sh assay-hygiene/extract   # expect roughly 60-70 MB
```

- [ ] **Step 7: Commit**

```bash
git add scripts/assay_hygiene/extract.py tests/test_assay_hygiene_extract.py
git commit -m "feat(assay-hygiene): stage A extractor with verified SQL and Cypher"
```

---

### Task 3: Stage B precedent miner

**Files:**
- Create: `scripts/assay_hygiene/precedent.py`
- Test: `tests/test_assay_hygiene_precedent.py`

**Interfaces:**
- Consumes: `_schema.RULE_KEY`, `PRECEDENT_COLUMNS`
- Produces: `mine_precedent(edges: pandas.DataFrame, membership: pandas.DataFrame, assays: pandas.DataFrame) -> pandas.DataFrame` returning `PRECEDENT_COLUMNS`; `membership_index(membership) -> dict[int, set[int]]`; `assay_index(assays) -> dict[int, tuple[int, str]]`

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


def test_comet_chip_hop_records_two_both_sides_and_one_child_only():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "D.IMG") & (out.assay_title == "Comet Chip")].iloc[0]
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
    # DNA children (300, 301) are in no assay, so no DNA rule exists
    assert out[out.child_type == "DNA"].empty


def test_reverse_rate_counts_the_other_direction():
    fx = S.make_fixture()
    out = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    row = out[(out.child_type == "TIS") & (out.assay_title == "Comet Chip")].iloc[0]
    # sample 500 (MUS parent) is in Comet Chip but child 203 is not
    assert row.n_parent_only == 1
    assert row.reverse_rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_precedent.py -v`
Expected: FAIL with `ImportError: cannot import name 'precedent'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/precedent.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage B. Mine the sample-type -> assay -> sample-type map from what exists.

The output answers one question per (project, hop, assay title): when the child
is in this assay, how often is the parent in it too? That is `propagation_rate`,
and it is the evidence a Mode 2 verdict rests on.

Keyed on assay TITLE because SEEK holds 458 assay records under 291 titles, one
per study. Keying on assay_id fragments the evidence into unjudgeable pieces.
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


def assay_index(assays: pd.DataFrame) -> dict[int, tuple[int, str]]:
    return {
        int(a): (int(p), str(t))
        for a, p, t in zip(assays.assay_id, assays.project_id, assays.title)
    }


def mine_precedent(
    edges: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
) -> pd.DataFrame:
    memb = membership_index(membership)
    ainfo = assay_index(assays)

    counts: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])  # both, child, parent

    for child_id, parent_id, child_type, parent_type in zip(
        edges.child_id, edges.parent_id, edges.child_type, edges.parent_type
    ):
        ca = memb.get(int(child_id), frozenset())
        pa = memb.get(int(parent_id), frozenset())
        for assay_id in ca | pa:
            info = ainfo.get(assay_id)
            if info is None:
                continue  # assay not resolvable to a project; skip rather than guess
            project_id, title = info
            key = (project_id, str(child_type), str(parent_type), title)
            if assay_id in ca and assay_id in pa:
                counts[key][0] += 1
            elif assay_id in ca:
                counts[key][1] += 1
            else:
                counts[key][2] += 1

    rows = []
    for (project_id, child_type, parent_type, title), (both, child_only, parent_only) in counts.items():
        fwd_den = both + child_only
        rev_den = both + parent_only
        rows.append({
            "project_id": project_id,
            "child_type": child_type,
            "parent_type": parent_type,
            "assay_title": title,
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
Expected: 6 passed

- [ ] **Step 5: Run against the real extract and eyeball the distribution**

```bash
uv run --with pandas --with pyarrow python -m assay_hygiene.precedent
```

Sanity anchors from the design session: a `D.TITR -> TIS` / `Titer Assay` rule should show roughly `n_both=1640, n_child_only=1057, propagation_rate≈0.61`, and `D.IMG -> TIS` / `Comet Chip` should be one of the largest rules.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/precedent.py tests/test_assay_hygiene_precedent.py
git commit -m "feat(assay-hygiene): stage B precedent miner keyed on assay title"
```

---

### Task 4: Stage C classifier

**Files:**
- Create: `scripts/assay_hygiene/classify.py`
- Test: `tests/test_assay_hygiene_classify.py`

**Interfaces:**
- Consumes: `_schema` verdict constants, `precedent.membership_index`, `precedent.assay_index`
- Produces: `classify_one(child_assays: set[int], parent_assays: set[int], child_type: str, parent_type: str, edge_has_assay: bool, lookup, high: float, low: float) -> tuple[str, dict]`; `classify_edges(edges, membership, assays, precedent, high=0.80, low=0.10) -> pandas.DataFrame` returning `FINDING_COLUMNS`

`lookup` is a callable `(project_id, child_type, parent_type, assay_title) -> float | None` returning the propagation rate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_classify.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import classify as C
from assay_hygiene import precedent as P


def _lookup_factory(rate_by_title):
    def lookup(project_id, child_type, parent_type, assay_title):
        return rate_by_title.get(assay_title)
    return lookup


def test_edge_that_already_carries_an_assay_is_clean():
    v, _ = C.classify_one({1}, {1}, "D.IMG", "TIS", True,
                          _lookup_factory({}), 0.8, 0.1)
    assert v == S.V_CLEAN


def test_both_endpoints_unregistered_is_mode_1_both_dark():
    v, _ = C.classify_one(set(), set(), "DNA", "TIS", False,
                          _lookup_factory({}), 0.8, 0.1)
    assert v == S.V_MODE1_BOTH_DARK


def test_child_unregistered_is_mode_1_child():
    v, _ = C.classify_one(set(), {1}, "DNA", "TIS", False,
                          _lookup_factory({}), 0.8, 0.1)
    assert v == S.V_MODE1_CHILD


def test_parent_unregistered_is_mode_1_parent():
    v, _ = C.classify_one({1}, set(), "D.IMG", "TIS", False,
                          _lookup_factory({}), 0.8, 0.1)
    assert v == S.V_MODE1_PARENT


def test_disjoint_with_strong_precedent_propagates():
    lookup = _lookup_factory({"Comet Chip": 0.95})
    v, meta = C.classify_one({1}, {2}, "D.IMG", "TIS", False, lookup, 0.8, 0.1,
                             titles={1: "Comet Chip", 2: "Tissue Collection"},
                             projects={1: 10, 2: 10})
    assert v == S.V_MODE2_PROPAGATE
    assert meta["matched_assay_title"] == "Comet Chip"
    assert meta["target_assay_id"] == 1


def test_disjoint_with_weak_precedent_is_clean_not_a_finding():
    # THE guard: without this every dark edge reads as actionable
    lookup = _lookup_factory({"Comet Chip": 0.02})
    v, _ = C.classify_one({1}, {2}, "D.IMG", "TIS", False, lookup, 0.8, 0.1,
                          titles={1: "Comet Chip", 2: "Tissue Collection"},
                          projects={1: 10, 2: 10})
    assert v == S.V_CLEAN


def test_disjoint_with_middling_precedent_is_ambiguous():
    lookup = _lookup_factory({"Comet Chip": 0.61})
    v, _ = C.classify_one({1}, {2}, "D.IMG", "TIS", False, lookup, 0.8, 0.1,
                          titles={1: "Comet Chip", 2: "Tissue Collection"},
                          projects={1: 10, 2: 10})
    assert v == S.V_MODE2_AMBIGUOUS


def test_unknown_hop_with_no_precedent_is_ambiguous():
    v, _ = C.classify_one({1}, {2}, "X", "Y", False, _lookup_factory({}), 0.8, 0.1,
                          titles={1: "Comet Chip", 2: "Tissue Collection"},
                          projects={1: 10, 2: 10})
    assert v == S.V_MODE2_AMBIGUOUS


def test_classify_edges_returns_the_finding_contract():
    fx = S.make_fixture()
    prec = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    out = C.classify_edges(fx["edges"], fx["membership"], fx["assays"], prec)
    assert list(out.columns) == S.FINDING_COLUMNS
    assert len(out) == len(fx["edges"])
    assert set(out.verdict) <= {
        S.V_CLEAN, S.V_MODE1_CHILD, S.V_MODE1_PARENT, S.V_MODE1_BOTH_DARK,
        S.V_MODE2_PROPAGATE, S.V_MODE2_AMBIGUOUS, S.V_MODE3_FLAG,
    }


def test_classify_edges_carries_candidates_for_stage_d():
    # stage D's tiebreak cannot recover membership later, so findings must carry it
    fx = S.make_fixture()
    prec = P.mine_precedent(fx["edges"], fx["membership"], fx["assays"])
    out = C.classify_edges(fx["edges"], fx["membership"], fx["assays"], prec)
    row = out[out.child_uuid == "D.IMG-3"].iloc[0]
    assert row.candidates == ["Comet Chip"]
    dark = out[out.child_uuid == "DNA-1"].iloc[0]
    assert dark.candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_classify.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/classify.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Stage C. Assign every edge a verdict.

The CLEAN branch on low propagation rate is the load-bearing guard. Without it
every dark edge reads as actionable and the tool would propose "correcting"
hundreds of thousands of correctly curated records.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import _schema as S
from .precedent import assay_index, membership_index

HIGH_DEFAULT = 0.80
LOW_DEFAULT = 0.10


def classify_one(
    child_assays: set[int],
    parent_assays: set[int],
    child_type: str,
    parent_type: str,
    edge_has_assay: bool,
    lookup,
    high: float = HIGH_DEFAULT,
    low: float = LOW_DEFAULT,
    titles: dict[int, str] | None = None,
    projects: dict[int, int] | None = None,
) -> tuple[str, dict]:
    """Return (verdict, metadata). First match wins."""
    blank = {"matched_assay_title": None, "matched_rate": None,
             "target_assay_id": None, "project_id": None}

    if edge_has_assay:
        return S.V_CLEAN, blank
    if not child_assays and not parent_assays:
        return S.V_MODE1_BOTH_DARK, blank
    if not child_assays:
        return S.V_MODE1_CHILD, blank
    if not parent_assays:
        return S.V_MODE1_PARENT, blank
    if child_assays & parent_assays:
        return S.V_CLEAN, blank  # sync gap, not a curation defect

    titles = titles or {}
    projects = projects or {}

    best: tuple[float, int, str, int] | None = None
    saw_unknown = False
    for assay_id in sorted(child_assays):
        title = titles.get(assay_id)
        project_id = projects.get(assay_id)
        if title is None or project_id is None:
            saw_unknown = True
            continue
        rate = lookup(project_id, child_type, parent_type, title)
        if rate is None:
            saw_unknown = True
            continue
        if best is None or rate > best[0]:
            best = (rate, assay_id, title, project_id)

    if best is None:
        return S.V_MODE2_AMBIGUOUS, blank

    rate, assay_id, title, project_id = best
    meta = {"matched_assay_title": title, "matched_rate": rate,
            "target_assay_id": assay_id, "project_id": project_id}

    if rate >= high:
        return S.V_MODE2_PROPAGATE, meta
    if rate <= low and not saw_unknown:
        return S.V_CLEAN, meta
    return S.V_MODE2_AMBIGUOUS, meta


def classify_edges(
    edges: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    precedent: pd.DataFrame,
    high: float = HIGH_DEFAULT,
    low: float = LOW_DEFAULT,
) -> pd.DataFrame:
    memb = membership_index(membership)
    ainfo = assay_index(assays)
    titles = {a: t for a, (_, t) in ainfo.items()}
    projects = {a: p for a, (p, _) in ainfo.items()}

    rates = {
        (int(r.project_id), r.child_type, r.parent_type, r.assay_title): float(r.propagation_rate)
        for r in precedent.itertuples()
    }

    def lookup(project_id, child_type, parent_type, assay_title):
        return rates.get((int(project_id), child_type, parent_type, assay_title))

    rows = []
    for e in edges.itertuples():
        child_assays = memb.get(int(e.child_id), set())
        verdict, meta = classify_one(
            child_assays,
            memb.get(int(e.parent_id), set()),
            str(e.child_type), str(e.parent_type),
            bool(pd.notna(e.edge_assay_id)),
            lookup, high, low, titles, projects,
        )
        rows.append({
            "child_id": e.child_id, "parent_id": e.parent_id,
            "child_uuid": e.child_uuid, "parent_uuid": e.parent_uuid,
            "child_type": e.child_type, "parent_type": e.parent_type,
            "verdict": verdict, **meta,
            "candidates": sorted(
                titles[a] for a in child_assays if a in titles
            ),
        })
    return pd.DataFrame(rows, columns=S.FINDING_COLUMNS)


def main(extract_dir: str = "assay-hygiene/extract",
         precedent_path: str = "assay-hygiene/precedent.csv",
         out_path: str = "assay-hygiene/findings.csv") -> None:
    d = Path(extract_dir)
    out = classify_edges(
        pd.read_parquet(d / "edges.parquet"),
        pd.read_parquet(d / "membership.parquet"),
        pd.read_parquet(d / "assays.parquet"),
        pd.read_csv(precedent_path),
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(out.verdict.value_counts().to_string())


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_classify.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/classify.py tests/test_assay_hygiene_classify.py
git commit -m "feat(assay-hygiene): stage C classifier with the CLEAN low-precedent guard"
```

---

### Task 5: Backtest harness

**Files:**
- Create: `scripts/assay_hygiene/backtest.py`
- Test: `tests/test_assay_hygiene_backtest.py`

**Interfaces:**
- Consumes: `precedent.mine_precedent`, `classify.classify_one`
- Produces: `holdout_split(membership, edges, frac=0.2, seed=0) -> tuple[pandas.DataFrame, list[tuple[int,int,int]]]`; `score_thresholds(edges, membership, assays, thresholds: list[float], frac=0.2, seed=0) -> pandas.DataFrame` with columns `["threshold", "n_predicted", "n_correct", "precision", "recall"]`

This is the gate on every production write. It hides the parent's membership on edges that are currently correct, re-mines precedent without them, and measures how often the pipeline recovers the assay a curator actually assigned.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_backtest.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import backtest as B


def test_holdout_removes_only_parent_memberships_it_reports():
    fx = S.make_fixture()
    reduced, held = B.holdout_split(fx["membership"], fx["edges"], frac=1.0, seed=0)
    assert len(held) > 0
    for child_id, parent_id, assay_id in held:
        match = reduced[(reduced.sample_id == parent_id) & (reduced.assay_id == assay_id)]
        assert match.empty, "held-out membership must be absent from the reduced set"


def test_holdout_is_deterministic_for_a_given_seed():
    fx = S.make_fixture()
    a = B.holdout_split(fx["membership"], fx["edges"], frac=0.5, seed=7)[1]
    b = B.holdout_split(fx["membership"], fx["edges"], frac=0.5, seed=7)[1]
    assert a == b


def test_holdout_never_removes_child_memberships():
    fx = S.make_fixture()
    reduced, held = B.holdout_split(fx["membership"], fx["edges"], frac=1.0, seed=0)
    for child_id, parent_id, assay_id in held:
        kept = reduced[(reduced.sample_id == child_id) & (reduced.assay_id == assay_id)]
        assert not kept.empty, "child side must survive so the hop stays inferable"


def test_score_thresholds_returns_one_row_per_threshold():
    fx = S.make_fixture()
    out = B.score_thresholds(fx["edges"], fx["membership"], fx["assays"],
                             thresholds=[0.5, 0.8], frac=1.0, seed=0)
    assert list(out.columns) == ["threshold", "n_predicted", "n_correct", "precision", "recall"]
    assert len(out) == 2


def test_precision_is_bounded_and_defined_when_nothing_predicted():
    fx = S.make_fixture()
    out = B.score_thresholds(fx["edges"], fx["membership"], fx["assays"],
                             thresholds=[1.01], frac=1.0, seed=0)
    row = out.iloc[0]
    assert row.n_predicted == 0
    assert row.precision == 0.0  # defined, not NaN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_backtest.py -v`
Expected: FAIL with `ImportError: cannot import name 'backtest'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/backtest.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""Validation gate. Hide known-good parent memberships, then try to recover them.

Ground truth is the set of edges where both endpoints are already registered in
the same assay. Those are curator decisions. If the pipeline cannot recover them
it has no business writing new ones.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from . import _schema as S
from .classify import classify_one
from .precedent import assay_index, membership_index, mine_precedent


def holdout_split(
    membership: pd.DataFrame,
    edges: pd.DataFrame,
    frac: float = 0.2,
    seed: int = 0,
) -> tuple[pd.DataFrame, list[tuple[int, int, int]]]:
    """Remove the PARENT side of a fraction of both-sides edges.

    Returns (reduced_membership, [(child_id, parent_id, assay_id), ...]).
    The child side is deliberately preserved: the pipeline must still be able to
    see which assay the child is in, because that is what it propagates.
    """
    memb = membership_index(membership)
    candidates: list[tuple[int, int, int]] = []
    for child_id, parent_id in zip(edges.child_id, edges.parent_id):
        shared = memb.get(int(child_id), set()) & memb.get(int(parent_id), set())
        for assay_id in sorted(shared):
            candidates.append((int(child_id), int(parent_id), assay_id))

    candidates.sort()
    rng = random.Random(seed)
    k = int(len(candidates) * frac)
    held = sorted(rng.sample(candidates, k)) if k else []

    drop = {(p, a) for _, p, a in held}
    mask = [
        (int(s), int(a)) not in drop
        for s, a in zip(membership.sample_id, membership.assay_id)
    ]
    return membership[mask].reset_index(drop=True), held


def score_thresholds(
    edges: pd.DataFrame,
    membership: pd.DataFrame,
    assays: pd.DataFrame,
    thresholds: list[float],
    frac: float = 0.2,
    seed: int = 0,
) -> pd.DataFrame:
    reduced, held = holdout_split(membership, edges, frac=frac, seed=seed)
    prec = mine_precedent(edges, reduced, assays)
    memb = membership_index(reduced)
    ainfo = assay_index(assays)
    titles = {a: t for a, (_, t) in ainfo.items()}
    projects = {a: p for a, (p, _) in ainfo.items()}

    rates = {
        (int(r.project_id), r.child_type, r.parent_type, r.assay_title): float(r.propagation_rate)
        for r in prec.itertuples()
    }

    def lookup(project_id, child_type, parent_type, assay_title):
        return rates.get((int(project_id), child_type, parent_type, assay_title))

    types = {int(c): str(t) for c, t in zip(edges.child_id, edges.child_type)}
    types.update({int(p): str(t) for p, t in zip(edges.parent_id, edges.parent_type)})

    rows = []
    for thr in thresholds:
        predicted = correct = 0
        for child_id, parent_id, truth_assay in held:
            verdict, meta = classify_one(
                memb.get(child_id, set()), memb.get(parent_id, set()),
                types.get(child_id, "?"), types.get(parent_id, "?"),
                False, lookup, thr, 0.0, titles, projects,
            )
            if verdict != S.V_MODE2_PROPAGATE:
                continue
            predicted += 1
            if meta["target_assay_id"] == truth_assay:
                correct += 1
        rows.append({
            "threshold": thr,
            "n_predicted": predicted,
            "n_correct": correct,
            "precision": (correct / predicted) if predicted else 0.0,
            "recall": (correct / len(held)) if held else 0.0,
        })
    return pd.DataFrame(rows, columns=["threshold", "n_predicted", "n_correct", "precision", "recall"])


def main(extract_dir: str = "assay-hygiene/extract",
         out_path: str = "assay-hygiene/backtest.csv") -> None:
    d = Path(extract_dir)
    out = score_thresholds(
        pd.read_parquet(d / "edges.parquet"),
        pd.read_parquet(d / "membership.parquet"),
        pd.read_parquet(d / "assays.parquet"),
        thresholds=[0.50, 0.60, 0.70, 0.80, 0.90, 0.95],
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(out.to_string(index=False))
    print("\nAcceptance bar is 95% precision. Pick the lowest threshold that clears it.")


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_backtest.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the real backtest and record the chosen threshold**

```bash
uv run --with pandas --with pyarrow python -m assay_hygiene.backtest
```

STOP and report the table to the user before continuing. If no threshold clears
95% precision, that is a finding: the deterministic band shrinks and more volume
routes to review. Do not silently lower the bar.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/backtest.py tests/test_assay_hygiene_backtest.py
git commit -m "feat(assay-hygiene): backtest harness gating writes on held-out precision"
```

---

### Task 6: Stage D deterministic adjudication

**Files:**
- Create: `scripts/assay_hygiene/adjudicate.py`
- Test: `tests/test_assay_hygiene_adjudicate.py`

**Interfaces:**
- Consumes: `_schema` constants
- Produces: `analysis_tiebreak(child_type: str, candidates: list[str]) -> str | None`; `Adjudicator` protocol with `decide(case: dict) -> dict`; `NullAdjudicator`; `adjudicate(findings: pandas.DataFrame, adjudicator: Adjudicator) -> pandas.DataFrame` adding columns `decided_by` and `rationale`

The `D.*` / `A.*` tiebreak is a named, tested rule rather than prompt text, because the dry run showed it resolves most of the ambiguous bucket deterministically.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_adjudicate.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import adjudicate as A


def test_analysis_prefix_picks_the_analysis_assay():
    assert A.analysis_tiebreak("A.FLOW", ["Flow Cytometry", "Flow Cytometry Analysis"]) \
        == "Flow Cytometry Analysis"


def test_data_prefix_picks_the_measurement_assay():
    assert A.analysis_tiebreak("D.TITR", ["Titer Assay", "Titer Assay Analysis"]) \
        == "Titer Assay"


def test_tiebreak_declines_when_no_analysis_variant_exists():
    assert A.analysis_tiebreak("D.IMG", ["Comet Chip", "Tissue Imaging"]) is None


def test_tiebreak_declines_for_non_prefixed_sample_types():
    assert A.analysis_tiebreak("TIS", ["Tissue Collection", "Tissue Collection Analysis"]) is None


def test_null_adjudicator_marks_everything_for_review():
    out = A.NullAdjudicator().decide({"candidates": ["a", "b"]})
    assert out["assay_title"] is None
    assert out["decided_by"] == "review"


def test_adjudicate_leaves_non_ambiguous_verdicts_untouched():
    findings = pd.DataFrame([{
        "child_type": "D.IMG", "verdict": S.V_MODE2_PROPAGATE,
        "matched_assay_title": "Comet Chip", "candidates": ["Comet Chip"],
    }])
    out = A.adjudicate(findings, A.NullAdjudicator())
    assert out.iloc[0].decided_by == "deterministic"
    assert out.iloc[0].matched_assay_title == "Comet Chip"


def test_adjudicate_resolves_ambiguous_rows_via_the_tiebreak_before_the_llm():
    findings = pd.DataFrame([{
        "child_type": "A.FLOW", "verdict": S.V_MODE2_AMBIGUOUS,
        "matched_assay_title": None,
        "candidates": ["Flow Cytometry", "Flow Cytometry Analysis"],
    }])
    out = A.adjudicate(findings, A.NullAdjudicator())
    assert out.iloc[0].matched_assay_title == "Flow Cytometry Analysis"
    assert out.iloc[0].decided_by == "tiebreak"


def test_adjudicate_falls_through_to_the_adjudicator_when_tiebreak_declines():
    findings = pd.DataFrame([{
        "child_type": "BAC", "verdict": S.V_MODE2_AMBIGUOUS,
        "matched_assay_title": None,
        "candidates": ["DNA Extraction", "Bacterial Extraction"],
    }])
    out = A.adjudicate(findings, A.NullAdjudicator())
    assert out.iloc[0].decided_by == "review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_adjudicate.py -v`
Expected: FAIL with `ImportError: cannot import name 'adjudicate'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/adjudicate.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Stage D. Resolve ambiguous findings: tiebreak first, model only if needed.

Observed in the design dry run: every A.* child resolved to the "... Analysis"
assay and every D.* child to the measurement assay. That is encoded here as a
tested rule, not buried in a prompt, so it is falsifiable and free.
"""
from __future__ import annotations

from typing import Protocol

import pandas as pd

from . import _schema as S

_ANALYSIS = " Analysis"


def analysis_tiebreak(child_type: str, candidates: list[str]) -> str | None:
    """Pick between "X" and "X Analysis" using the sample-type prefix.

    Returns None when the rule does not apply, so the caller falls through.
    """
    if not (child_type.startswith("A.") or child_type.startswith("D.")):
        return None
    analysis = [c for c in candidates if c.endswith(_ANALYSIS)]
    measurement = [c for c in candidates if not c.endswith(_ANALYSIS)]
    if not analysis or not measurement:
        return None
    wanted = analysis if child_type.startswith("A.") else measurement
    return wanted[0] if len(wanted) == 1 else None


class Adjudicator(Protocol):
    def decide(self, case: dict) -> dict:
        """Return {"assay_title": str | None, "decided_by": str, "rationale": str}."""


class NullAdjudicator:
    """Decides nothing. Everything it sees becomes a human review item."""

    def decide(self, case: dict) -> dict:
        return {"assay_title": None, "decided_by": "review",
                "rationale": "no deterministic rule matched; needs curator review"}


def adjudicate(findings: pd.DataFrame, adjudicator: Adjudicator) -> pd.DataFrame:
    out = findings.copy()
    decided_by: list[str] = []
    rationale: list[str] = []
    titles: list[str | None] = []

    for row in out.itertuples():
        if row.verdict != S.V_MODE2_AMBIGUOUS:
            decided_by.append("deterministic")
            rationale.append("")
            titles.append(row.matched_assay_title)
            continue

        candidates = list(getattr(row, "candidates", []) or [])
        picked = analysis_tiebreak(str(row.child_type), candidates)
        if picked is not None:
            decided_by.append("tiebreak")
            rationale.append(f"{row.child_type} prefix selects '{picked}'")
            titles.append(picked)
            continue

        verdict = adjudicator.decide({"child_type": row.child_type,
                                      "candidates": candidates})
        decided_by.append(verdict["decided_by"])
        rationale.append(verdict["rationale"])
        titles.append(verdict["assay_title"])

    out["matched_assay_title"] = titles
    out["decided_by"] = decided_by
    out["rationale"] = rationale
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_adjudicate.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/adjudicate.py tests/test_assay_hygiene_adjudicate.py
git commit -m "feat(assay-hygiene): stage D tiebreak and adjudicator protocol"
```

---

### Task 7: Stage E rule sheet emitter

**Files:**
- Create: `scripts/assay_hygiene/emit.py`
- Test: `tests/test_assay_hygiene_emit.py`

**Interfaces:**
- Consumes: `_schema.RULE_COLUMNS`, `RULE_KEY`
- Produces: `build_rules(findings: pandas.DataFrame, precedent: pandas.DataFrame) -> pandas.DataFrame` returning `RULE_COLUMNS`; `build_expansion(findings: pandas.DataFrame) -> pandas.DataFrame` with columns `RULE_KEY + ["target_assay_id", "child_id", "parent_id", "child_uuid", "parent_uuid"]`; `read_approvals(path) -> dict[tuple, tuple[str, str]]`; `write_sheet(path, rules: pandas.DataFrame) -> None`

`build_expansion` is what Task 9 joins approved rules against. Without it the
apply stage has no way to turn a rule back into the specific samples it covers.

Curator decisions in `APPROVE` and `NOTES` must survive regeneration, per plugin hard rule 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_emit.py
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import emit as E


def _findings():
    return pd.DataFrame([
        {"child_id": 100, "parent_id": 200, "child_uuid": "D.IMG-1", "parent_uuid": "TIS-1",
         "project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
         "matched_assay_title": "Comet Chip", "verdict": S.V_MODE2_PROPAGATE,
         "decided_by": "deterministic", "rationale": "", "target_assay_id": 1},
        {"child_id": 101, "parent_id": 201, "child_uuid": "D.IMG-2", "parent_uuid": "TIS-2",
         "project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
         "matched_assay_title": "Comet Chip", "verdict": S.V_MODE2_PROPAGATE,
         "decided_by": "deterministic", "rationale": "", "target_assay_id": 1},
        {"child_id": 203, "parent_id": 500, "child_uuid": "TIS-4", "parent_uuid": "MUS-1",
         "project_id": 10, "child_type": "TIS", "parent_type": "MUS",
         "matched_assay_title": "Tissue Collection", "verdict": S.V_CLEAN,
         "decided_by": "deterministic", "rationale": "", "target_assay_id": 2},
    ])


def _precedent():
    return pd.DataFrame([
        {"project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
         "assay_title": "Comet Chip", "n_both": 9, "n_child_only": 2,
         "n_parent_only": 0, "propagation_rate": 0.818, "reverse_rate": 1.0},
    ])


def test_clean_findings_never_become_rules():
    rules = E.build_rules(_findings(), _precedent())
    assert (rules.verdict != S.V_CLEAN).all()


def test_rules_aggregate_findings_into_affected_count():
    rules = E.build_rules(_findings(), _precedent())
    row = rules.iloc[0]
    assert row.affected_count == 2
    assert row.assay_title == "Comet Chip"


def test_rules_carry_the_precedent_evidence():
    rules = E.build_rules(_findings(), _precedent())
    row = rules.iloc[0]
    assert row.n_both == 9
    assert row.propagation_rate == pytest.approx(0.818)


def test_sheet_has_the_declared_columns(tmp_path):
    path = tmp_path / "ASSAY_HYGIENE-update.xlsx"
    E.write_sheet(path, E.build_rules(_findings(), _precedent()))
    import openpyxl
    ws = openpyxl.load_workbook(path)["Rules"]
    header = [c.value for c in ws[1]]
    assert header == S.RULE_COLUMNS


def test_expansion_keeps_one_row_per_actionable_finding():
    exp = E.build_expansion(_findings())
    assert len(exp) == 2  # the CLEAN row is excluded
    assert set(exp.columns) == set(
        S.RULE_KEY + ["target_assay_id", "child_id", "parent_id",
                     "child_uuid", "parent_uuid"]
    )


def test_expansion_joins_back_to_rules_on_the_rule_key():
    rules = E.build_rules(_findings(), _precedent())
    exp = E.build_expansion(_findings())
    merged = exp.merge(rules[S.RULE_KEY], on=S.RULE_KEY, how="inner")
    assert len(merged) == 2, "every expansion row must match a rule"


def test_curator_approvals_survive_regeneration(tmp_path):
    path = tmp_path / "ASSAY_HYGIENE-update.xlsx"
    rules = E.build_rules(_findings(), _precedent())
    E.write_sheet(path, rules)

    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb["Rules"]
    ws.cell(row=2, column=S.RULE_COLUMNS.index("APPROVE") + 1, value="YES")
    ws.cell(row=2, column=S.RULE_COLUMNS.index("NOTES") + 1, value="checked by hand")
    wb.save(path)

    merged = E.build_rules(_findings(), _precedent())
    for key, (approve, notes) in E.read_approvals(path).items():
        mask = True
        for col, val in zip(S.RULE_KEY, key):
            mask = mask & (merged[col] == val)
        merged.loc[mask, "APPROVE"] = approve
        merged.loc[mask, "NOTES"] = notes
    E.write_sheet(path, merged)

    ws2 = openpyxl.load_workbook(path)["Rules"]
    assert ws2.cell(row=2, column=S.RULE_COLUMNS.index("APPROVE") + 1).value == "YES"
    assert ws2.cell(row=2, column=S.RULE_COLUMNS.index("NOTES") + 1).value == "checked by hand"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_emit.py -v`
Expected: FAIL with `ImportError: cannot import name 'emit'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/emit.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "openpyxl>=3.1", "pyarrow>=14"]
# ///
"""Stage E. Collapse findings into a rule sheet a curator can actually read.

Rule-level, not row-level: 400k proposed writes would be rubber-stamped, a few
hundred rules can be judged. APPROVE and NOTES are curator-owned and are merged
forward on every regeneration (plugin hard rule 3).
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd

from . import _schema as S

_ACTION_BY_VERDICT = {
    S.V_MODE2_PROPAGATE: S.A_ADD_PARENT,
    S.V_MODE2_AMBIGUOUS: S.A_ADD_PARENT,
    S.V_MODE1_CHILD: S.A_ADD_TO_ASSAY,
    S.V_MODE1_PARENT: S.A_ADD_TO_ASSAY,
    S.V_MODE1_BOTH_DARK: S.A_FLAG_ONLY,
    S.V_MODE3_FLAG: S.A_FLAG_ONLY,
}


def build_rules(findings: pd.DataFrame, precedent: pd.DataFrame) -> pd.DataFrame:
    actionable = findings[findings.verdict != S.V_CLEAN].copy()
    if actionable.empty:
        return pd.DataFrame(columns=S.RULE_COLUMNS)

    actionable = actionable.rename(columns={"matched_assay_title": "assay_title"})
    grouped = (
        actionable
        .groupby(S.RULE_KEY + ["verdict", "decided_by"], dropna=False)
        .agg(affected_count=("child_type", "size"),
             rationale=("rationale", "first"))
        .reset_index()
    )
    merged = grouped.merge(precedent, on=S.RULE_KEY, how="left")
    merged["action"] = merged.verdict.map(_ACTION_BY_VERDICT).fillna(S.A_FLAG_ONLY)
    for col in ("n_both", "n_child_only", "n_parent_only"):
        merged[col] = merged[col].fillna(0).astype(int)
    for col in ("propagation_rate", "reverse_rate"):
        merged[col] = merged[col].fillna(0.0)
    merged["APPROVE"] = ""
    merged["NOTES"] = ""
    return merged[S.RULE_COLUMNS].sort_values(
        "affected_count", ascending=False, ignore_index=True
    )


def build_expansion(findings: pd.DataFrame) -> pd.DataFrame:
    """Row-level backing for each rule: the exact edges a rule would act on.

    Stage F joins approved rules against this to recover concrete sample ids.
    """
    cols = S.RULE_KEY + ["target_assay_id", "child_id", "parent_id",
                         "child_uuid", "parent_uuid"]
    actionable = findings[findings.verdict != S.V_CLEAN].copy()
    if actionable.empty:
        return pd.DataFrame(columns=cols)
    actionable = actionable.rename(columns={"matched_assay_title": "assay_title"})
    return actionable[cols].reset_index(drop=True)


def read_approvals(path) -> dict[tuple, tuple[str, str]]:
    """Recover curator-owned APPROVE/NOTES keyed by RULE_KEY."""
    path = Path(path)
    if not path.exists():
        return {}
    ws = openpyxl.load_workbook(path)["Rules"]
    header = [c.value for c in ws[1]]
    key_idx = [header.index(k) for k in S.RULE_KEY]
    a_idx, n_idx = header.index("APPROVE"), header.index("NOTES")
    out: dict[tuple, tuple[str, str]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        approve = row[a_idx] or ""
        notes = row[n_idx] or ""
        if not approve and not notes:
            continue
        out[tuple(row[i] for i in key_idx)] = (approve, notes)
    return out


def write_sheet(path, rules: pd.DataFrame) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rules"
    ws.append(S.RULE_COLUMNS)
    for row in rules[S.RULE_COLUMNS].itertuples(index=False):
        ws.append(list(row))
    wb.save(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_emit.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/assay_hygiene/emit.py tests/test_assay_hygiene_emit.py
git commit -m "feat(assay-hygiene): stage E rule sheet and row-level expansion"
```

---

### Task 8: Prove the rollback path on the dev box

**Files:**
- Create: `scripts/assay_hygiene/ROLLBACK_PROBE.md`

No production writes may happen until this task produces a documented answer. The
assays API exposes `list`, `retrieve`, `create`, `partial_update` and no delete,
so removal is unproven. This task is exploratory and has no unit test; its
deliverable is a written finding.

- [ ] **Step 1: Create a throwaway assay on nextseek-dev**

Work against `fairdata-dev`, never production. Use the `nextseek` container there.
Create an assay under a test study, then add two samples to it via
`PATCH /nextseek_api/assays/<id>/`.

- [ ] **Step 2: Attempt removal by PATCHing the membership minus one sample**

Record the exact request body, the HTTP status, and the response body. Per the
plugin's documented pitfall the proxy converts SEEK's 422 into a generic 502, so
capture the upstream body if the proxy exposes it.

- [ ] **Step 3: Verify by re-reading the assay**

Confirm whether the sample was actually detached or whether the PATCH was a
no-op that reported success.

- [ ] **Step 4: Write the finding**

Create `scripts/assay_hygiene/ROLLBACK_PROBE.md` recording: the request shape
that worked or failed, the observed status codes, whether removal is possible,
and if not, what the fallback is (direct SQL delete run by the operator, or
`sampletype_attr.py`-style native-endpoint driving).

- [ ] **Step 5: Report to the user and stop**

If rollback does not work, say so plainly and do not proceed to Task 9 without a
decision. Batching strategy depends entirely on this answer.

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/ROLLBACK_PROBE.md
git commit -m "docs(assay-hygiene): record rollback probe findings from dev box"
```

---

### Task 9: Stage F guarded apply

**Files:**
- Create: `scripts/assay_hygiene/apply.py`
- Test: `tests/test_assay_hygiene_apply.py`

**Interfaces:**
- Consumes: `_schema.RULE_KEY`, `emit.read_approvals`
- Produces: `plan_writes(rules: pandas.DataFrame, expansion: pandas.DataFrame) -> dict[int, set[int]]`; `apply_writes(plan, client, manifest_path, write: bool = False) -> dict`

`client` is any object with `get_members(assay_id) -> set[int]` and
`set_members(assay_id, members: set[int]) -> None`, so tests use a fake and no
network is touched.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assay_hygiene_apply.py
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import apply as AP


class FakeClient:
    def __init__(self, members=None):
        self.members = members or {1: {10, 11}}
        self.calls = []

    def get_members(self, assay_id):
        return set(self.members.get(assay_id, set()))

    def set_members(self, assay_id, members):
        self.calls.append((assay_id, set(members)))
        self.members[assay_id] = set(members)


def _rules(approve="YES"):
    return pd.DataFrame([{
        "project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
        "assay_title": "Comet Chip", "APPROVE": approve,
    }])


def _expansion():
    return pd.DataFrame([
        {"project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
         "assay_title": "Comet Chip", "target_assay_id": 1, "parent_id": 12},
        {"project_id": 10, "child_type": "D.IMG", "parent_type": "TIS",
         "assay_title": "Comet Chip", "target_assay_id": 1, "parent_id": 13},
    ])


def test_unapproved_rules_produce_no_writes():
    assert AP.plan_writes(_rules(approve=""), _expansion()) == {}


def test_approved_rule_expands_to_its_parent_samples():
    assert AP.plan_writes(_rules(), _expansion()) == {1: {12, 13}}


def test_only_yes_counts_as_approval():
    assert AP.plan_writes(_rules(approve="maybe"), _expansion()) == {}


def test_dry_run_makes_no_client_calls(tmp_path):
    client = FakeClient()
    result = AP.apply_writes({1: {12, 13}}, client, tmp_path / "m.jsonl", write=False)
    assert client.calls == []
    assert result["would_add"] == 2
    assert not (tmp_path / "m.jsonl").exists()


def test_write_unions_rather_than_overwriting(tmp_path):
    client = FakeClient(members={1: {10, 11}})
    AP.apply_writes({1: {12}}, client, tmp_path / "m.jsonl", write=True)
    assay_id, members = client.calls[0]
    assert members == {10, 11, 12}, "existing membership must be preserved"


def test_manifest_records_only_the_additions(tmp_path):
    manifest = tmp_path / "m.jsonl"
    client = FakeClient(members={1: {10, 11}})
    AP.apply_writes({1: {11, 12}}, client, manifest, write=True)
    entry = json.loads(manifest.read_text().strip())
    assert entry["assay_id"] == 1
    assert entry["added"] == [12], "11 was already a member and is not an addition"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_apply.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/assay_hygiene/apply.py
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14", "requests>=2.31"]
# ///
"""Stage F. Expand approved rules into guarded API writes.

Dry run is the default and --write must be explicit. Writes union onto existing
membership and never overwrite, and the manifest records only true additions so
a rollback targets exactly what this run created.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import _schema as S

APPROVED = "YES"


def plan_writes(rules: pd.DataFrame, expansion: pd.DataFrame) -> dict[int, set[int]]:
    approved = rules[rules.APPROVE.astype(str).str.strip().str.upper() == APPROVED]
    if approved.empty:
        return {}
    joined = expansion.merge(approved[S.RULE_KEY], on=S.RULE_KEY, how="inner")
    plan: dict[int, set[int]] = {}
    for assay_id, parent_id in zip(joined.target_assay_id, joined.parent_id):
        plan.setdefault(int(assay_id), set()).add(int(parent_id))
    return plan


def apply_writes(plan: dict[int, set[int]], client, manifest_path,
                 write: bool = False) -> dict:
    total_would = sum(len(v) for v in plan.values())
    if not write:
        return {"would_add": total_would, "assays": len(plan), "written": 0}

    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with manifest_path.open("a") as fh:
        for assay_id, proposed in sorted(plan.items()):
            current = client.get_members(assay_id)
            additions = sorted(proposed - current)
            if not additions:
                continue
            client.set_members(assay_id, current | set(additions))
            verified = client.get_members(assay_id)
            fh.write(json.dumps({
                "assay_id": assay_id,
                "added": additions,
                "verified": sorted(set(additions) & verified) == additions,
            }) + "\n")
            written += len(additions)
    return {"would_add": total_would, "assays": len(plan), "written": written}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/test_assay_hygiene_apply.py -v`
Expected: 6 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run --with pytest --with pandas --with pyarrow --with openpyxl pytest tests/ -q`
Expected: all pass, including `plugin_sentinel` (nothing written inside the checkout)

- [ ] **Step 6: Commit**

```bash
git add scripts/assay_hygiene/apply.py tests/test_assay_hygiene_apply.py
git commit -m "feat(assay-hygiene): stage F guarded apply, dry-run default, union writes"
```

---

## Deferred, deliberately

- **Live LLM adjudicator.** Task 6 ships the `Adjudicator` protocol and a working
  `NullAdjudicator` that routes everything to review. Binding a real Claude client
  is a separate task, and whoever picks it up must load the `claude-api` skill
  first rather than guessing a model id.
- **Plugin mode registration.** No `commands/*.md`, no `HYGIENE.md`, no
  `plugin.json` wiring. The user explicitly scoped this to scripts for now.
- **Mode 3 detection depth.** `V_MODE3_FLAG` exists in the vocabulary and flows
  through emit, but Task 4 does not implement contradiction detection. It needs
  the Stage B distribution to define "dominant precedent with near-zero support",
  which does not exist until Task 3 runs on real data.
