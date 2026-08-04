# Init Auto-Detect (project + lab code) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `/curate-init` auto-detect the NExtSEEK project, lab code, and PI from the API plus local evidence, presented as one confirmation, instead of hand-typed `--lab`/`--pi`/`--project-id`.

**Architecture:** A new network-free module `scripts/detect_context.py` holds pure ranking logic (evidence → project rank → lab extraction/rank → PI guess). A new `nextseek_api.py detect-context` subcommand wires it to the API (`/projects/` + `export_project`) and prints JSON. `curate-init.md` orchestrates: run it, show one `AskUserQuestion` confirm, write `lab`/`pi`/`nextseek_project_id` to the lockfile. The export pull doubles as the build guard's fresh DB pull in `previous_metadata/`.

**Tech Stack:** Python 3.11+, `openpyxl` (xlsx parsing), `requests` (API, existing), pytest. PEP 723 inline-deps scripts.

## Global Constraints

- Branch: `feat/init-auto-detect` (off `origin/main`). Commit per task.
- `detect_context.py` is **network-free** — stdlib + `openpyxl` only; no `requests`, no `_config` import. This keeps Tasks 1–4 unit-testable offline.
- UID grammar: `<TYPE>-<YYMMDD><LAB>-N`, regex `^(?P<type>.+)-(?P<date>\d{6})(?P<lab>[A-Z]{3})-(?P<n>\d+)$`.
- Lab code is **always confirmed** in init, never auto-applied silently (collision guardrail).
- Test import pattern (match existing tests): `REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO / "scripts"))`.
- v1 evidence is filename-based (cwd path parts + `manuscript/` filenames + `previous_metadata/` xlsx names); PDF/DOCX text extraction is out of scope.

---

### Task 1: `detect_context.py` — tokenize, Evidence, gather_evidence

**Files:**
- Create: `scripts/detect_context.py`
- Test: `tests/test_detect_context.py`

**Interfaces:**
- Produces: `tokenize(text: str) -> list[str]`; `@dataclass Evidence(path_tokens, author_surnames, doi, master_tokens)` with `.all_tokens() -> set[str]`; `gather_evidence(project_root: Path) -> Evidence`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_detect_context.py
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import detect_context as dc  # noqa: E402


def test_tokenize_lowercases_and_drops_short():
    assert dc.tokenize("Cancer of the CSBC-2026") == ["cancer", "the", "csbc", "2026"]


def test_gather_evidence_reads_path_manuscript_master(tmp_path):
    proj = tmp_path / "csbc-publications" / "flower-curation-tyrosine"
    (proj / "manuscript").mkdir(parents=True)
    (proj / "manuscript" / "flower-white-2026-tyrosine.pdf").write_text("x")
    (proj / "previous_metadata").mkdir()
    (proj / "previous_metadata" / "CSBC All 260731.xlsx").write_text("x")
    ev = dc.gather_evidence(proj)
    assert "csbc" in ev.all_tokens()          # from path + master filename
    assert "flower" in ev.author_surnames     # manuscript filename token
    assert "white" in ev.author_surnames
    assert "csbc" in ev.master_tokens
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jps/.claude/plugins/dmac-curation && uv run --with openpyxl pytest tests/test_detect_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detect_context'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/detect_context.py
"""Network-free logic for /curate-init project + lab auto-detection.

nextseek_api.py's `detect-context` subcommand wires these to the API; keeping
them here (stdlib + openpyxl only) makes them unit-testable offline.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

UID_RE = re.compile(r"^(?P<type>.+)-(?P<date>\d{6})(?P<lab>[A-Z]{3})-(?P<n>\d+)$")
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens of length >= 3 (drops noise like 'of')."""
    return [t for t in _WORD.findall((text or "").lower()) if len(t) >= 3]


@dataclass
class Evidence:
    path_tokens: list[str] = field(default_factory=list)
    author_surnames: list[str] = field(default_factory=list)
    doi: "str | None" = None
    master_tokens: list[str] = field(default_factory=list)

    def all_tokens(self) -> set:
        return set(self.path_tokens) | set(self.master_tokens)


def gather_evidence(project_root) -> Evidence:
    root = Path(project_root)
    path_tokens: list[str] = []
    for part in root.resolve().parts:
        path_tokens.extend(tokenize(part))

    author_surnames: list[str] = []
    man = root / "manuscript"
    if man.is_dir():
        for f in sorted(man.iterdir()):
            if f.is_file():
                toks = tokenize(f.stem)
                path_tokens.extend(toks)
                author_surnames.extend(toks)  # filenames often encode authors

    master_tokens: list[str] = []
    pm = root / "previous_metadata"
    if pm.is_dir():
        for f in sorted(pm.glob("*.xlsx")):
            master_tokens.extend(tokenize(f.stem))

    return Evidence(path_tokens=path_tokens, author_surnames=author_surnames,
                    doi=None, master_tokens=master_tokens)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jps/.claude/plugins/dmac-curation && uv run --with openpyxl pytest tests/test_detect_context.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/jps/.claude/plugins/dmac-curation
git add scripts/detect_context.py tests/test_detect_context.py
git commit -m "feat(detect): evidence gathering + tokenize for init auto-detect"
```

---

### Task 2: `rank_projects`

**Files:**
- Modify: `scripts/detect_context.py`
- Test: `tests/test_detect_context.py`

**Interfaces:**
- Consumes: `Evidence`, `tokenize`.
- Produces: `rank_projects(projects: list[dict], evidence: Evidence) -> list[dict]` — each input `{"id", "title"}` gets a `"score"` (count of evidence tokens matching title tokens); sorted by score desc, then title.

- [ ] **Step 1: Write the failing test**

```python
def test_rank_projects_scores_and_sorts():
    projects = [{"id": 4, "title": "MetNet"},
                {"id": 10, "title": "Cancer_Systems_Biology_Consortium(CSBC)"}]
    ev = dc.Evidence(path_tokens=["csbc", "flower", "tyrosine"])
    ranked = dc.rank_projects(projects, ev)
    assert ranked[0]["id"] == 10
    assert ranked[0]["score"] >= 1
    assert ranked[-1]["id"] == 4 and ranked[-1]["score"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py::test_rank_projects_scores_and_sorts -q`
Expected: FAIL — `AttributeError: module 'detect_context' has no attribute 'rank_projects'`.

- [ ] **Step 3: Write the implementation** (append to `detect_context.py`)

```python
def rank_projects(projects: list, evidence: Evidence) -> list:
    """Score each project by evidence-token overlap with its title; sort desc."""
    ev = evidence.all_tokens() | set(evidence.author_surnames)
    out = []
    for p in projects:
        title_toks = set(tokenize(p.get("title", "")))
        out.append({**p, "score": len(ev & title_toks)})
    out.sort(key=lambda p: (-p["score"], str(p.get("title", ""))))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/detect_context.py tests/test_detect_context.py
git commit -m "feat(detect): rank projects by evidence overlap"
```

---

### Task 3: `extract_labs`

**Files:**
- Modify: `scripts/detect_context.py`
- Test: `tests/test_detect_context.py`

**Interfaces:**
- Produces: `@dataclass LabInfo(code, count, scientists, latest, score=0.0)`; `extract_labs(xlsx_bytes: bytes) -> list[LabInfo]` — parses UIDs across every sheet with a `uid` header column, aggregating per `<LAB>`: `count`, distinct sorted `scientists` (from a `scientist` column if present), and `latest` (max `YYMMDD`).

- [ ] **Step 1: Write the failing test**

```python
import io
import openpyxl


def _make_xlsx(sheets):
    """sheets: list[(sheet_name, [(uid, scientist), ...])]"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        ws.append(["UID", "Scientist"])
        for uid, sci in rows:
            ws.append([uid, sci])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_labs_aggregates_by_lab_code():
    xlsx = _make_xlsx([
        ("CEL", [("CEL-260730WHI-1", "Cameron Flower"),
                 ("CEL-260731WHI-2", "Forest White")]),
        ("D.MSP", [("D.MSP-260729AGA-1", "Nathalie Agar"),
                   ("not-a-uid", "ignored")]),
    ])
    labs = {l.code: l for l in dc.extract_labs(xlsx)}
    assert labs["WHI"].count == 2
    assert labs["WHI"].scientists == ["Cameron Flower", "Forest White"]
    assert labs["WHI"].latest == "260731"
    assert labs["AGA"].count == 1
    assert "AGA" in labs and labs["AGA"].scientists == ["Nathalie Agar"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py::test_extract_labs_aggregates_by_lab_code -q`
Expected: FAIL — `AttributeError: ... has no attribute 'extract_labs'`.

- [ ] **Step 3: Write the implementation** (append to `detect_context.py`)

```python
@dataclass
class LabInfo:
    code: str
    count: int
    scientists: list
    latest: str
    score: float = 0.0


def extract_labs(xlsx_bytes: bytes) -> list:
    """Aggregate UIDs across all sheets of a project export into per-lab records."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    agg: dict = {}
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            hdr = [str(h).strip().lower() if h is not None else "" for h in next(rows)]
        except StopIteration:
            continue
        if "uid" not in hdr:
            continue
        ui = hdr.index("uid")
        si = hdr.index("scientist") if "scientist" in hdr else None
        for r in rows:
            if ui >= len(r) or not r[ui]:
                continue
            m = UID_RE.match(str(r[ui]).strip())
            if not m:
                continue
            a = agg.setdefault(m.group("lab"),
                               {"count": 0, "scientists": set(), "latest": ""})
            a["count"] += 1
            a["latest"] = max(a["latest"], m.group("date"))
            if si is not None and si < len(r) and r[si]:
                a["scientists"].add(str(r[si]).strip())
    wb.close()
    return [LabInfo(code=code, count=v["count"],
                    scientists=sorted(v["scientists"]), latest=v["latest"])
            for code, v in agg.items()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/detect_context.py tests/test_detect_context.py
git commit -m "feat(detect): extract per-lab-code aggregates from a project export"
```

---

### Task 4: `rank_labs` + `guess_pi`

**Files:**
- Modify: `scripts/detect_context.py`
- Test: `tests/test_detect_context.py`

**Interfaces:**
- Consumes: `LabInfo`, `Evidence`.
- Produces: `rank_labs(labs, evidence) -> list[LabInfo]` — sets `score=100.0` when any `evidence.author_surnames` token is a substring of a lab's joined scientist names, else `0.0`; sorts by `(-score, -count, -int(latest))`. `guess_pi(labs, evidence, pi_arg) -> str | None` — returns `pi_arg.lower()` if given; else the author surname matching the top lab's scientists; else the last-name of the top lab's first scientist; `None` if no labs.

- [ ] **Step 1: Write the failing tests**

```python
def test_rank_labs_author_match_beats_count():
    labs = [dc.LabInfo("AGA", 50, ["Nathalie Agar"], "260701"),
            dc.LabInfo("WHI", 5, ["Cameron Flower", "Forest White"], "260731")]
    ranked = dc.rank_labs(labs, dc.Evidence(author_surnames=["white", "flower"]))
    assert ranked[0].code == "WHI"


def test_rank_labs_recency_tiebreak_when_no_author():
    labs = [dc.LabInfo("AAA", 10, ["X"], "260101"),
            dc.LabInfo("BBB", 10, ["Y"], "260731")]
    ranked = dc.rank_labs(labs, dc.Evidence())
    assert ranked[0].code == "BBB"


def test_guess_pi_prefers_arg():
    assert dc.guess_pi([], dc.Evidence(), "White") == "white"


def test_guess_pi_author_match():
    labs = [dc.LabInfo("WHI", 5, ["Cameron Flower", "Forest White"], "260731")]
    assert dc.guess_pi(labs, dc.Evidence(author_surnames=["white"]), None) == "white"


def test_guess_pi_fallback_first_scientist_surname():
    labs = [dc.LabInfo("WHI", 5, ["Forest White"], "260731")]
    assert dc.guess_pi(labs, dc.Evidence(), None) == "white"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py -q -k "rank_labs or guess_pi"`
Expected: FAIL — `AttributeError: ... has no attribute 'rank_labs'`.

- [ ] **Step 3: Write the implementation** (append to `detect_context.py`)

```python
def _latest_int(s: str) -> int:
    return int(s) if s.isdigit() else 0


def rank_labs(labs: list, evidence: Evidence) -> list:
    """Author-surname match wins; then higher count; then newer latest date."""
    surnames = [s for s in evidence.author_surnames if len(s) >= 3]
    for lab in labs:
        joined = " ".join(lab.scientists).lower()
        lab.score = 100.0 if any(s in joined for s in surnames) else 0.0
    labs.sort(key=lambda l: (-l.score, -l.count, -_latest_int(l.latest)))
    return labs


def guess_pi(labs: list, evidence: Evidence, pi_arg):
    if pi_arg:
        return pi_arg.lower()
    if not labs:
        return None
    top = labs[0]
    surnames = [s for s in evidence.author_surnames if len(s) >= 3]
    for sci in top.scientists:
        low = sci.lower()
        for sn in surnames:
            if sn in low:
                return sn
    if top.scientists:
        return top.scientists[0].split()[-1].lower()
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with openpyxl pytest tests/test_detect_context.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/detect_context.py tests/test_detect_context.py
git commit -m "feat(detect): rank labs (author boost) + guess PI"
```

---

### Task 5: `detect-context` subcommand in `nextseek_api.py`

**Files:**
- Modify: `scripts/nextseek_api.py` (add `list_projects` client method near `get_project` ~line 135; add `cmd_detect_context` before `def main`; register subparser after the `pull-db` block)
- Test: `tests/test_nextseek_api_detect.py`

**Interfaces:**
- Consumes: `detect_context.{gather_evidence,rank_projects,extract_labs,rank_labs,guess_pi}`; existing `NExtSEEKClient.export_project`, `_client_from_args`, `config_from_args`, `_load_dotenv`, `NExtSEEKError`, `ProjectRootError`, `DEFAULT_BASE_URL`.
- Produces: `NExtSEEKClient.list_projects() -> list[dict]` (`[{"id": int, "title": str}, ...]`); `cmd_detect_context(args) -> int` printing a JSON object with keys `projects, chosen_project, labs, pi_guess, export_path, evidence, warnings`.

- [ ] **Step 1: Write the failing test** (isolated file so it needs `requests`, unlike Tasks 1–4)

```python
# tests/test_nextseek_api_detect.py
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import nextseek_api as na  # noqa: E402


def test_list_projects_normalizes(monkeypatch):
    c = na.NExtSEEKClient(username="u", password="p")
    monkeypatch.setattr(c, "_get", lambda path, params=None: {
        "data": [
            {"id": "10", "type": "projects", "attributes": {"title": "CSBC"}},
            {"id": "4", "attributes": {"title": "MetNet"}},
        ]})
    ps = c.list_projects()
    assert {"id": 10, "title": "CSBC"} in ps
    assert {"id": 4, "title": "MetNet"} in ps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with requests --with openpyxl pytest tests/test_nextseek_api_detect.py -q`
Expected: FAIL — `AttributeError: 'NExtSEEKClient' object has no attribute 'list_projects'`.

- [ ] **Step 3a: Add the `list_projects` method** (in `nextseek_api.py`, right after `get_project`)

```python
    def list_projects(self) -> list:
        """GET /projects/ → [{'id': int, 'title': str}, ...] (JSON:API normalized)."""
        doc = self._get("/projects/")
        data = doc.get("data", doc) if isinstance(doc, dict) else doc
        out = []
        for r in (data or []):
            attrs = r.get("attributes", r) if isinstance(r, dict) else {}
            pid = r.get("id")
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                pass
            out.append({"id": pid, "title": attrs.get("title") or attrs.get("name") or ""})
        return out
```

- [ ] **Step 3b: Add `cmd_detect_context`** (immediately before `def main(argv=None) -> int:`)

```python
def cmd_detect_context(args: argparse.Namespace) -> int:
    """Suggest project + lab + pi for /curate-init as JSON (API + local evidence)."""
    import json as _json
    _load_dotenv()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import detect_context as dc

    client = _client_from_args(args)  # exits(2) if no creds
    try:
        cfg = config_from_args(args)
        root, prev_dir = cfg.root, cfg.previous_metadata
    except ProjectRootError:
        root = Path(".").resolve()
        prev_dir = root / "previous_metadata"

    warnings = []
    evidence = dc.gather_evidence(root)
    try:
        projects = client.list_projects()
    except NExtSEEKError as e:
        print(f"error: could not list projects: HTTP {e.status}", file=sys.stderr)
        return 1
    ranked = dc.rank_projects(projects, evidence)

    if getattr(args, "project_id", None):
        chosen = next((p for p in ranked if str(p["id"]) == str(args.project_id)),
                      {"id": args.project_id, "title": ""})
    else:
        chosen = ranked[0] if ranked else None

    labs, export_path = [], None
    if chosen:
        try:
            content, fname = client.export_project(chosen["id"], "xlsx")
            prev_dir.mkdir(parents=True, exist_ok=True)
            (prev_dir / fname).write_bytes(content)
            export_path = str(prev_dir / fname)
            labs = dc.rank_labs(dc.extract_labs(content), evidence)
        except NExtSEEKError as e:
            warnings.append(f"export pull failed (HTTP {e.status}); labs unavailable")

    out = {
        "projects": ranked,
        "chosen_project": chosen,
        "labs": [vars(l) for l in labs],
        "pi_guess": dc.guess_pi(labs, evidence, getattr(args, "pi", None)),
        "export_path": export_path,
        "evidence": {
            "path_tokens": evidence.path_tokens[:20],
            "author_surnames": evidence.author_surnames[:20],
            "master_tokens": evidence.master_tokens[:20],
        },
        "warnings": warnings,
    }
    print(_json.dumps(out, indent=2))
    return 0
```

- [ ] **Step 3c: Register the subparser** (after the `pull-db` block, before the `# ── validate ──` block)

```python
    # ── detect-context ──────────────────────────────────────────────────────
    dctx = sub.add_parser(
        "detect-context",
        help="Suggest project + lab code + pi for /curate-init (JSON) from the "
             "API and local evidence.")
    dctx.add_argument("--project-id", default=None,
                      help="Force a project id instead of auto-ranking.")
    dctx.add_argument("--pi", default=None, help="Known PI (skips PI guessing).")
    dctx.add_argument("--username", default=None)
    dctx.add_argument("--password", default=None)
    dctx.add_argument("--token", default=None)
    dctx.add_argument("--base-url", default=DEFAULT_BASE_URL)
    add_config_args(dctx)
    dctx.set_defaults(func=cmd_detect_context)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with requests --with openpyxl pytest tests/test_nextseek_api_detect.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Verify the CLI wires up (no network)**

Run: `uv run --script scripts/nextseek_api.py detect-context --help`
Expected: help text lists `--project-id`, `--pi`, `--base-url`. Exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/nextseek_api.py tests/test_nextseek_api_detect.py
git commit -m "feat(api): detect-context subcommand + list_projects"
```

---

### Task 6: Wire auto-detect into `curate-init.md`

**Files:**
- Modify: `commands/curate-init.md` (Steps + Behavioral rules)

**Interfaces:**
- Consumes: `nextseek_api.py detect-context` JSON output.

- [ ] **Step 1: Update the arg-handling rule** — replace the current "If `--lab` or `--pi` is missing … use `AskUserQuestion`. Never guess a lab code" behavioral rule with:

```markdown
- If `--lab`/`--pi`/`--project-id` are missing in pipeline mode, AUTO-DETECT
  before asking: run
  `uv run --script <PLUGIN>/scripts/nextseek_api.py detect-context` (requires the
  copied `.env`). It returns JSON with a ranked `projects`, a `chosen_project`,
  ranked `labs` (code + count + scientists + latest), and `pi_guess`, and it
  drops the project export into `previous_metadata/` (also the build guard's
  fresh pull). Present ONE `AskUserQuestion` confirm of
  `chosen_project` + top `labs[0].code` + `pi_guess`; on accept use them, on
  change offer the ranked `projects`/`labs` lists (lab code may be free-typed
  for a brand-new lab). **Never apply a lab code without this confirm** — a wrong
  lab code silently overwrites another lab on upload. If detect-context fails
  (no creds/network), fall back to `AskUserQuestion` for lab/pi as before.
```

- [ ] **Step 2: Record the project id in the lockfile** — in the Step 6 lockfile snippet's `values`, add `nextseek_project_id` when known. Replace the `values = (...)` line with:

```python
   values = ({"lab": "$LAB".upper(), "pi": "$PI".lower(),
              "nextseek_project_id": $PROJECT_ID}   # int from detect-context, else None
             if "$MODE" == "pipeline" else {})
```

- [ ] **Step 3: Add a prereq note** — under `## Prereqs`, after the `.env` bullet, add:

```markdown
- Auto-detect needs the copied `.env` (NExtSEEK creds). Without it, init still
  works but falls back to asking for lab/pi.
```

- [ ] **Step 4: Verify the command references detect-context**

Run: `grep -n "detect-context" /Users/jps/.claude/plugins/dmac-curation/commands/curate-init.md`
Expected: at least one match in the behavioral rules.

- [ ] **Step 5: Confirm the command-presence test still passes**

Run: `uv run --with pyyaml pytest tests/test_curate_commands_present.py -q`
Expected: PASS (unchanged — this only edits prose).

- [ ] **Step 6: Commit**

```bash
git add commands/curate-init.md
git commit -m "feat(init): auto-detect project/lab/pi via detect-context (one-tap confirm)"
```

---

### Task 7: Full suite + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the detect tests together**

Run: `uv run --with requests --with openpyxl pytest tests/test_detect_context.py tests/test_nextseek_api_detect.py -q`
Expected: all PASS (10 passed).

- [ ] **Step 2: Live smoke (needs `.env` with NExtSEEK creds; from a project dir)**

Run (from a dir with a `.env`): `uv run --script <PLUGIN>/scripts/nextseek_api.py detect-context --project-id 10`
Expected: JSON with `chosen_project.id == 10`, `labs` containing `WHI`/`AGA`/… with plausible counts, and an `export_path` under `previous_metadata/`. If offline/no creds, skip — covered by unit tests.

- [ ] **Step 3: Push the branch**

```bash
cd /Users/jps/.claude/plugins/dmac-curation
git push -u fork feat/init-auto-detect   # or open a PR to origin/main per your flow
```

---

## Self-Review

**Spec coverage:** goal (auto-detect project/lab/pi, one confirm) → Tasks 5–6; `detect-context` data-flow steps 1–7 → Tasks 1–5; reuse `export_project` + fresh-pull side effect → Task 5 (writes to `previous_metadata/`); sets `nextseek_project_id` → Task 6 Step 2; lab-always-confirmed safety → Task 6 Step 1; error/fallback table → Task 5 (`warnings`, projects-only on export fail) + Task 6 Step 1 (no creds/network fallback); testing (offline unit + live smoke) → Tasks 1–5 + Task 7. No gaps.

**Placeholder scan:** no TBD/TODO; every code and test step has complete code; commands have expected output. Clear.

**Type consistency:** `Evidence`, `LabInfo`, `tokenize`, `gather_evidence`, `rank_projects`, `extract_labs`, `rank_labs`, `guess_pi`, `list_projects`, `cmd_detect_context` names/signatures match across Tasks 1–6. `rank_labs` mutates+returns the same list; `guess_pi` reads `labs[0]` after ranking — consistent with Task 5 call order (`rank_labs(...)` then `guess_pi(labs, ...)`).

**Known v1 simplification (vs spec):** author surnames come from `manuscript/` **filenames**, not PDF/DOCX text — captured in Global Constraints and acceptable for v1 (the real manuscript filename `flower-white-2026-…` already encodes authors). Deeper extraction is a future enhancement.
