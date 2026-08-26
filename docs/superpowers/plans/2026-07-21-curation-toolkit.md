# dmac-curation Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn dmac-curation from a linear 13-phase pipeline into a multi-mode curator's workbench with four modes (`pipeline`, `fdh`, `schema`, `report`), fixing the path-anchoring and write-safety defects that block adding modes.

**Architecture:** A *mode* is a convention, not a framework — entry points in `commands/<prefix>-*.md`, a reference doc at `skills/curation/<MODE>.md`, a row in the `SKILL.md` mode table, and optionally `context/<mode>_index.json` and `scripts/<mode>/`. Nothing is registered in `plugin.json`; adding a file *is* registering it. Two new modes are added on top of prerequisite refactors that move every script from plugin-anchored paths to cwd-anchored paths behind one project-config seam.

**Tech Stack:** Python 3.11+, PEP 723 inline-dependency scripts run via `uv run --script`, openpyxl for xlsx, pytest for tests, Jinja2 for project scaffolding templates, Markdown for commands and reference docs.

## Global Constraints

- **Every script is a PEP 723 `uv` script.** Header form: `# /// script` / `# requires-python = ">=3.11"` / `# dependencies = [...]` / `# ///`. Invoke as `uv run --script <path>`. Never `python3 <path>`. (SKILL.md hard rule 6)
- **No *curation* script may read or write inside the plugin checkout.** All project paths resolve from the current working directory. The only plugin-relative reads permitted to a curation script are `context/*.json`, `context/*.yaml`, and `templates/*.j2`, and those are read-only. This is prerequisite P1: `/curate-consolidate` and `/curate-qa` currently write inside the checkout, and `consolidate_to_flat.py:325` deletes files there.
  - **Exception, and the only one: plugin-maintenance scripts.** `scripts/refresh_context.py` (Task 18) and the vendoring steps (Tasks 24, 25) exist precisely to update bundled data and provenance inside `context/`. They are run by a maintainer against the plugin, never by a curator against a project. The `plugin_sentinel` fixture guards curation scripts only, which is why Task 18's write path is exercised against a monkeypatched `CONTEXT_DIR` rather than the real one. A maintenance script writing to `context/` is not a P1 violation; a curation script doing so is.
- **Placeholder markers over blanks.** Unknown values are written as `*** PLACEHOLDER: <description> ***`, never left empty. (SKILL.md hard rule 8)
- **Write-safety convention is `--write`.** Every script that mutates a file on disk defaults to dry-run and requires an explicit `--write` flag. `--dry-run` is forbidden as a flag name because its absence implies writing.
- **Every vendored file gets a provenance manifest entry** in `context/PROVENANCE.json`: `source_repo`, `source_path`, `commit_sha`, `vendored_date`, `local_divergence`.
- **Ontology bindings are emitted `"confirmed": false`.** Only a human flips that flag. (schema-mode spec)
- **A format is not "supported" until it has a renderer AND a validator.** (report-mode spec)
- **No em dashes in PI-facing prose.** Applies to `EMAIL_TO_PI.md` and templates that feed it, not to code or internal docs.
- **Plugin version is `0.3.0`** after this work. It must read identically in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and the lockfile written by `/curate-init`.
- **Repo root for all paths in this plan:** `/home/cdemu/code/dmac/curation_skill`. Paths are written repo-relative.
- **Test command:** `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v`

## Reference: source specs

All four are committed by Task 1 and are the authority when this plan is ambiguous:

- `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md` — parent; mode seam, lockfile v1, P1/P2/P3
- `docs/superpowers/specs/2026-07-21-pipeline-rework-review.md` — 13 phases to 11, keep 4-sheet, keep both formats
- `docs/superpowers/specs/2026-07-21-schema-mode-design.md` — field dictionary, Instructions+Ontology sheets
- `docs/superpowers/specs/2026-07-21-report-mode-design.md` — adapters, mapping spec, two-stage validation

## Stage map

| Stage | Tasks | Deliverable |
|---|---|---|
| 0 | 1 | Specs committed |
| A | 2-5 | Secrets purged, write-safety standardized, doc/CLI drift caught by a test |
| B | 6-9 | P1/P2/P3 — nothing writes inside the plugin |
| C | 10-15 | Mode architecture: lockfile v1, mode table, additive init, per-mode status |
| D | 16-17 | Pipeline corrections: 11 phases, Phase 12 reads RETRIEVE.TXT |
| E | 18 | Context refresh path — no more stale dev snapshot |
| F | 19-23 | `schema` mode |
| G | 24-34 | `report` mode, then release |

---

## Stage 0 — Baseline

### Task 1: Commit the four specs

**Files:**
- Commit: `docs/superpowers/specs/2026-07-21-curation-toolkit-design.md`
- Commit: `docs/superpowers/specs/2026-07-21-pipeline-rework-review.md`
- Commit: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`
- Commit: `docs/superpowers/specs/2026-07-21-report-mode-design.md`
- Commit: `docs/superpowers/plans/2026-07-21-curation-toolkit.md` (this plan)

**Interfaces:**
- Consumes: nothing
- Produces: a clean baseline commit so later diffs are readable

- [ ] **Step 1: Confirm the working tree state before committing**

Run: `git status --short`

Expected output includes these five untracked spec/plan files plus unrelated dirty state (`scripts/fdh/generated/REGISTRY.md` modified; `.claude-plugin/marketplace.json`, `.claude/`, and five `scripts/fdh/generated/*.py` untracked). **Do not stage the unrelated files.**

- [ ] **Step 2: Stage only the specs and this plan**

```bash
git add docs/superpowers/specs/2026-07-21-curation-toolkit-design.md \
        docs/superpowers/specs/2026-07-21-pipeline-rework-review.md \
        docs/superpowers/specs/2026-07-21-schema-mode-design.md \
        docs/superpowers/specs/2026-07-21-report-mode-design.md \
        docs/superpowers/plans/2026-07-21-curation-toolkit.md
```

- [ ] **Step 3: Verify nothing else got staged**

Run: `git diff --cached --name-only`

Expected: exactly the five paths above, nothing more.

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: toolkit reframe specs + implementation plan

Four specs from the 2026-07-21 design session: architecture (mode seam,
lockfile v1, prerequisites P1/P2/P3), pipeline review (13 phases -> 11),
schema mode, report mode. Plus the single implementation plan derived
from all four.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage A — Immediate safety fixes

These are independent of the redesign. They ship first because two of them are active data-loss or credential-exposure traps.

### Task 2: Purge on-disk secrets from `working/`

**Files:**
- Delete: `working/fdh-upload-script/.env`
- Delete: `working/fdh-upload-script/Assets/Output/session.json`
- Create: `docs/SECURITY.md`
- Test: `tests/test_no_plaintext_secrets.py`

**Interfaces:**
- Consumes: nothing
- Produces: `tests/test_no_plaintext_secrets.py` — a guard later tasks must keep passing

**Context:** `working/` is gitignored (`.gitignore` last stanza), so these never entered git history. They are still readable on disk by anything that can read the checkout, and the FDH token in them is live.

- [ ] **Step 1: Write the failing test**

Create `tests/test_no_plaintext_secrets.py`:

```python
"""No plaintext credential files may sit inside the plugin checkout.

`working/` is gitignored, so these never reach history — but they are
readable on disk and the tokens in them are live. Rotate + delete.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Filenames that have historically held live tokens in this checkout.
FORBIDDEN = [
    "working/fdh-upload-script/.env",
    "working/fdh-upload-script/Assets/Output/session.json",
]

# Substrings that indicate a real token rather than a placeholder.
TOKEN_HINTS = ("FDH_API=", "FDH_TOKEN=", '"token"')


def test_known_secret_files_are_gone():
    for rel in FORBIDDEN:
        assert not (REPO / rel).exists(), (
            f"{rel} still on disk. Rotate the token on FairDomHub, then delete the file."
        )


def test_no_dotenv_under_working():
    working = REPO / "working"
    if not working.is_dir():
        return
    strays = [p for p in working.rglob(".env") if p.is_file()]
    assert not strays, f"plaintext .env files under working/: {strays}"


def test_no_session_json_with_token_under_working():
    working = REPO / "working"
    if not working.is_dir():
        return
    offenders = []
    for p in working.rglob("session.json"):
        text = p.read_text(errors="ignore")
        if any(h in text for h in TOKEN_HINTS):
            offenders.append(p)
    assert not offenders, f"session.json holding a token: {offenders}"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run --with pytest pytest tests/test_no_plaintext_secrets.py -v`
Expected: `test_known_secret_files_are_gone` FAILS with "working/fdh-upload-script/.env still on disk".

- [ ] **Step 3: Print the rotation instruction, then proceed**

The repo owner has decided to delete first and rotate after, so **do not block on
this** — print the instruction and continue to Step 4 in the same run:

```
ACTION REQUIRED BY A HUMAN, after this task completes:
Rotate the FairDomHub API token. Deleting the files does NOT un-expose it -
the token is live until revoked.
  1. Log in to https://fairdomhub.org
  2. Profile -> API tokens -> revoke the token that was in
     working/fdh-upload-script/.env
  3. Issue a replacement and store it ONLY in the shell environment or a
     password manager, never in a file inside this checkout.
```

Record in your report that this instruction was printed and that rotation is
still outstanding, so it reaches the final summary rather than being lost.

- [ ] **Step 4: Delete the files**

```bash
rm -f working/fdh-upload-script/.env
rm -f working/fdh-upload-script/Assets/Output/session.json
```

- [ ] **Step 5: Write the security note**

Create `docs/SECURITY.md`:

```markdown
# Credential handling

## Rule

No credential ever lives in a file inside this checkout, including under
`working/` and including gitignored paths. Gitignore keeps secrets out of
history; it does not keep them off disk.

## Where credentials go instead

| credential | source | consumed by |
|---|---|---|
| `FDH_API` | shell environment, or a `.env` in the **curation project** cwd | `scripts/fdh/fdh_api.py`, `scripts/fdh/submit.py` |
| `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD` | shell environment, or project cwd `.env` | `scripts/nextseek_api.py` |
| `MIT_USER` / `MIT_PASS` | shell environment, or project cwd `.env` | `scripts/smb_pull.py` |
| `NCFTP_*` | shell environment, or project cwd `.env` | `scripts/upload_geo_ncftp.sh` |
| `BIOPORTAL_API_KEY` | shell environment, or project cwd `.env` | `schema` mode ontology lookup |

`scripts/fdh/fdh_api.py:161` shows the correct resolution order: the
**project cwd** `.env` first, the plugin `.env` second. Scripts must never
require a plugin-local `.env`.

## Enforcement

`tests/test_no_plaintext_secrets.py` fails the suite if a `.env` or a
token-bearing `session.json` reappears under `working/`.

## If a token leaks

Rotate first, delete second. A deleted file with a live token is still a
live token.
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/test_no_plaintext_secrets.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add tests/test_no_plaintext_secrets.py docs/SECURITY.md
git commit -m "security: purge plaintext tokens from working/, add guard test

The FDH token in working/fdh-upload-script/.env and the plaintext token in
Assets/Output/session.json were gitignored but live on disk. Rotated and
deleted. tests/test_no_plaintext_secrets.py fails if either reappears.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Command/script drift test — catch documented flags that do not exist

**Files:**
- Create: `tests/test_curate_commands_present.py`
- Test: itself (this task's deliverable IS the test; it is expected to FAIL at the end of this task)

**Interfaces:**
- Consumes: nothing
- Produces: `tests/test_curate_commands_present.py` with helper `parsed_flags(script_path) -> set[str]`, consumed by nothing else but relied on by Tasks 4, 5, and 17 to prove their fixes

**Context:** `tests/test_fdh_commands_present.py` does this for the two FDH commands only. Five documented `curate-*` flags do not exist in their target scripts. This test is written first, left failing, and turned green by Tasks 4, 5, and 17.

- [ ] **Step 1: Write the test**

Create `tests/test_curate_commands_present.py`:

```python
"""Every flag documented in a commands/curate-*.md exists in the script it names.

Mirrors tests/test_fdh_commands_present.py, which does this for FDH only.
Root cause it guards: five documented flags had no corresponding
add_argument() call, so /curate-validate silently ignored RETRIEVE.TXT and
/curate-deposit's documented dry-run default was the opposite of reality.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = REPO / "commands"

# (command file, script path, flags the command doc promises)
CONTRACTS = [
    ("curate-consolidate.md", "scripts/consolidate_to_flat.py",
     ["--assay-sheets", "--all-in-one"]),
    ("curate-qa.md", "scripts/qa_flat_sheets.py",
     ["--upload", "--master-baseline", "--expected-counts"]),
    ("curate-retrieve.md", "scripts/build_retrieve.py",
     ["--assay-sheets", "--output", "--include-parents"]),
    ("curate-validate.md", "scripts/review_metadata_vs_uploads.py",
     ["--retrieve", "--assay-sheets"]),
    ("curate-deposit.md", "scripts/stage_zenodo.py", ["--write"]),
    ("curate-deposit.md", "scripts/apply_zenodo_links.py",
     ["--write", "--record-id"]),
    ("curate-deposit.md", "scripts/apply_geo_accessions.py",
     ["--write", "--gse"]),
    ("curate-deposit.md", "scripts/apply_omero_ids.py",
     ["--write", "--omero-csv"]),
    ("curate-resolve-assays.md", "scripts/nextseek_api.py", ["--project-id"]),
]

_FLAG_RE = re.compile(r'add_argument\(\s*\n?\s*["\'](--[a-z0-9-]+)["\']')


def parsed_flags(script_path: Path) -> set[str]:
    """Return every long flag registered via add_argument() in a script."""
    return set(_FLAG_RE.findall(script_path.read_text()))


@pytest.mark.parametrize("cmd_name,script_rel,flags", CONTRACTS)
def test_documented_flags_exist(cmd_name, script_rel, flags):
    script = REPO / script_rel
    assert script.exists(), f"{script_rel} referenced by {cmd_name} does not exist"
    have = parsed_flags(script)
    missing = [f for f in flags if f not in have]
    assert not missing, (
        f"{cmd_name} documents {missing} but {script_rel} has no such argument. "
        f"Registered flags: {sorted(have)}"
    )


@pytest.mark.parametrize("cmd_name,script_rel,flags", CONTRACTS)
def test_command_doc_mentions_the_script(cmd_name, script_rel, flags):
    doc = (COMMANDS / cmd_name).read_text()
    leaf = Path(script_rel).name
    assert leaf in doc, f"{cmd_name} never names {leaf}"


def test_no_script_offers_a_dry_run_flag():
    """Write-safety convention is --write. --dry-run is forbidden: its ABSENCE
    would imply writing, which is exactly the trap this suite exists to close."""
    offenders = []
    for script in (REPO / "scripts").rglob("*.py"):
        if "--dry-run" in parsed_flags(script):
            offenders.append(script.relative_to(REPO))
    assert not offenders, (
        f"these scripts still use --dry-run instead of --write: {offenders}"
    )


@pytest.mark.parametrize("script_rel", sorted({c[1] for c in CONTRACTS}))
def test_script_help_runs(script_rel):
    result = subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"{script_rel} --help failed: {result.stderr}"
```

- [ ] **Step 2: Run it and record exactly which contracts fail**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v 2>&1 | tail -40`

Expected: multiple FAILs. Record the list — Tasks 4, 5 and 17 close them. At minimum expect failures for:
- `consolidate_to_flat.py` missing `--assay-sheets`
- `qa_flat_sheets.py` missing `--upload`, `--master-baseline`, `--expected-counts`
- `review_metadata_vs_uploads.py` missing `--retrieve`, `--assay-sheets`
- `stage_zenodo.py` missing `--write`
- `apply_zenodo_links.py` missing `--write`
- `apply_geo_accessions.py` missing `--gse`
- `test_no_script_offers_a_dry_run_flag` failing on `stage_zenodo.py` and `apply_zenodo_links.py`

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_curate_commands_present.py
git commit -m "test: assert documented curate-* flags exist (currently RED)

Analogue of test_fdh_commands_present.py for the pipeline commands. Fails
today on five documented-but-nonexistent flags and on the two scripts that
use --dry-run (and therefore default to WRITING). Tasks 4, 5 and 17 turn
it green.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Standardize deposit write-safety on `--write`

**Files:**
- Modify: `scripts/stage_zenodo.py:105-110` (argparse block)
- Modify: `scripts/apply_zenodo_links.py:91-110` (argparse block, plus the `--zenodo-record` rename)
- Modify: `scripts/smb_pull.py:319,353,364,440-441` and its docstring at `:12,22,26`
- Modify: `commands/curate-deposit.md:20-22,33`
- Test: `tests/test_deposit_write_safety.py`

> **AMENDED after Task 3 ran.** Task 3's drift test found three things this task
> was originally scoped against wrongly, all confirmed by grep:
>
> 1. **`scripts/smb_pull.py` also registers `--dry-run`** (`:319`, used at `:353`
>    and `:440-441`, with an error string at `:364` and three docstring mentions).
>    So **three** scripts need converting, not two. `smb_pull.py` is a transfer
>    tool, and its `--dry-run` gates an actual network pull — exactly the polarity
>    trap this task exists to close.
> 2. **`apply_zenodo_links.py` has `--zenodo-record`, not `--record-id`.**
>    `commands/curate-deposit.md:22` documents
>    `apply_zenodo_links.py --write --record-id <N>`, so the doc and the script
>    disagree on the flag name as well as on write-safety. Fixing `--write` alone
>    leaves that drift-test row RED with no task owning it. **This task fixes
>    both.**
> 3. `apply_geo_accessions.py` already has `--write` (only `--gse` is missing,
>    which is Task 5), and `consolidate_to_flat.py` already has `--all-in-one`
>    (only `--assay-sheets` is missing, which is Task 8). Do not re-add those.

**Interfaces:**
- Consumes: `parsed_flags()` **imported from** `tests/test_curate_commands_present.py` (Task 3). Do **not** re-declare the regex — see the note in the test snippet below.
- Produces: every deposit script exposes `--write: bool` and performs no filesystem mutation when it is absent

**Context — the actual trap:** `apply_geo_accessions.py:190` and `apply_omero_ids.py:73` already default to dry-run and require `--write`. `stage_zenodo.py:107` and `apply_zenodo_links.py:93` use `--dry-run`, so **omitting the flag writes**. `commands/curate-deposit.md:33` claims all four default to dry-run. Two of the four have been documented backwards.

- [ ] **Step 1: Write the failing test**

Create `tests/test_deposit_write_safety.py`:

```python
"""Deposit scripts must default to dry-run and mutate only under --write."""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

DEPOSIT_SCRIPTS = [
    "scripts/stage_zenodo.py",
    "scripts/apply_zenodo_links.py",
    "scripts/apply_geo_accessions.py",
    "scripts/apply_omero_ids.py",
    # Added post-Task-3: smb_pull.py also had --dry-run, gating a network pull.
    "scripts/smb_pull.py",
]

# Import the hardened detector rather than re-declaring a regex here.
# The naive `add_argument\(\s*["\'](--[a-z0-9-]+)` form FAILS OPEN on a
# short-form-first declaration -- `add_argument("-n", "--dry-run")` parses as
# [] -- which would make this file, where write-safety is the entire subject,
# ship with a guard that silently passes. Task 3's reviewer proved that against
# 13 declaration forms. pytest puts the tests dir on sys.path, so this import
# works without packaging.
from test_curate_commands_present import parsed_flags  # noqa: E402


def _flags(rel: str) -> set[str]:
    return parsed_flags(REPO / rel)


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_has_write_flag(rel):
    assert "--write" in _flags(rel), f"{rel} must expose --write"


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_has_no_dry_run_flag(rel):
    assert "--dry-run" not in _flags(rel), (
        f"{rel} still has --dry-run; its absence implies writing"
    )


@pytest.mark.parametrize("rel", DEPOSIT_SCRIPTS)
def test_help_documents_default_is_dry_run(rel):
    result = subprocess.run(
        ["uv", "run", "--script", str(REPO / rel), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "default is dry-run" in result.stdout, (
        f"{rel} --help must state 'default is dry-run' on the --write flag"
    )


def test_command_doc_states_the_write_convention():
    doc = (REPO / "commands" / "curate-deposit.md").read_text()
    assert "--dry-run" not in doc, (
        "curate-deposit.md still documents --dry-run"
    )
    assert "default to dry-run and require `--write`" in doc


def test_zenodo_backfill_flag_matches_its_command_doc():
    """curate-deposit.md:22 documents --record-id; the script had
    --zenodo-record. Renamed so the doc and the CLI agree."""
    flags = _flags("scripts/apply_zenodo_links.py")
    assert "--record-id" in flags
    assert "--zenodo-record" not in flags, (
        "old name still present; a two-name CLI is how drift restarts"
    )


def test_smb_pull_converted_too():
    """smb_pull.py's --dry-run gated an actual network transfer."""
    flags = _flags("scripts/smb_pull.py")
    assert "--write" in flags
    assert "--dry-run" not in flags


def test_no_script_anywhere_still_uses_dry_run():
    """Repo-wide sweep, so a fourth offender cannot hide."""
    offenders = [
        p.relative_to(REPO) for p in (REPO / "scripts").rglob("*.py")
        if "--dry-run" in _flags(str(p.relative_to(REPO)))
    ]
    assert not offenders, f"still using --dry-run: {offenders}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_deposit_write_safety.py -v`
Expected: FAILs on `stage_zenodo.py` and `apply_zenodo_links.py` for both `test_has_write_flag` and `test_has_no_dry_run_flag`, plus `test_command_doc_states_the_write_convention`.

- [ ] **Step 3: Read the two scripts' write sites before changing the flag**

Run:
```bash
grep -n 'dry_run\|dry-run' scripts/stage_zenodo.py scripts/apply_zenodo_links.py
```

Every site that currently reads `args.dry_run` must be inverted to `not args.write`. Do not simply rename the attribute — the polarity flips.

- [ ] **Step 4: Change `stage_zenodo.py`**

Replace the argparse line at `scripts/stage_zenodo.py:107`:

```python
    ap.add_argument("--dry-run", action="store_true")
```

with:

```python
    ap.add_argument(
        "--write", action="store_true",
        help="Move files into staging folders; default is dry-run.",
    )
```

> **CORRECTED after Task 4 ran.** An earlier draft said `help="Create the zip
> files."`. **`stage_zenodo.py` creates no archives.** It imports neither
> `zipfile` nor `subprocess`, calls no `make_archive`, and its only mutation is
> `shutil.move()` at `:216-217` into per-bucket *folders*. Describe what the
> script does, not what the surrounding workflow needs.

Then at every use site, replace `args.dry_run` with `not args.write`. Concretely, a guard that previously read:

```python
        if args.dry_run:
            print(f"  [dry-run] would write {out}")
            continue
```

becomes:

```python
        if not args.write:
            print(f"  [dry-run] would write {out}")
            continue
```

- [ ] **Step 5: Change `apply_zenodo_links.py` the same way**

Replace `scripts/apply_zenodo_links.py:93`:

```python
    ap.add_argument("--dry-run", action="store_true")
```

with:

```python
    ap.add_argument(
        "--write", action="store_true",
        help="Patch the upload sheets; default is dry-run.",
    )
```

and invert every `args.dry_run` use site to `not args.write`.

**Also rename this script's record flag.** `commands/curate-deposit.md:22`
documents `--record-id`, but the script declares `--zenodo-record`. Rename the
argument to `--record-id` and update its `dest`/use sites. Do **not** keep the
old name as an alias: a two-name CLI is how this drift restarts.

- [ ] **Step 5b: Convert `scripts/smb_pull.py`**

`smb_pull.py:319` registers `--dry-run`, and unlike the Zenodo pair its flag
gates an actual **network transfer** (`:353`, `:440-441`). Same conversion:

```python
    ap.add_argument(
        "--write", action="store_true",
        help="Perform the transfer. Omit to build the manifest and size "
             "estimate only; default is dry-run.",
    )
```

Invert `args.dry_run` to `not args.write` at `:353` and `:440-441`. Update the
error string at `:364` (`"Run --dry-run first"` becomes `"Run without --write
first"`) and the three docstring mentions at `:12`, `:22` and `:26`.

Note this script's dry-run branch *prints* rather than transferring, so the
inversion is mechanical — but verify the `--from-manifest` interaction at `:364`
still reads correctly, since that path assumes a prior manifest-building run.

- [ ] **Step 6: Make `--write` help text uniform across all five**

> **CORRECTED after Task 4 ran.** An earlier draft of this step told you to
> claim "(creates .bak)" in the help text of `apply_zenodo_links.py` and
> `apply_omero_ids.py`. **That is false.** Verified: only
> `apply_geo_accessions.py` creates a backup (it uses `shutil.copy` to a `.bak`).
> `apply_zenodo_links.py`, `apply_omero_ids.py` and `stage_zenodo.py` mutate
> without one. Write help text that is true of the script it describes; a
> curator who believes a rollback exists when it does not is worse off than one
> who knows there is none.
>
> **Recorded as a follow-up risk, not this task's job:** two scripts patch xlsx
> files in place with no backup. That gap is real but belongs to a later
> hardening pass, not to a write-safety rename.

`apply_geo_accessions.py:190` already reads `help="patch in place (creates .bak); default is dry-run"`. Confirm `apply_omero_ids.py:73` reads:

```python
    p.add_argument("--write", action="store_true",
                   help="Apply changes; default is dry-run")
```

and change it to end with the exact phrase the test asserts:

```python
    p.add_argument("--write", action="store_true",
                   help="Apply changes in place; default is dry-run.")
```

Do the same for `apply_geo_accessions.py:190` so all four `--help` outputs contain the literal string `default is dry-run`.

- [ ] **Step 7: Correct the command doc**

In `commands/curate-deposit.md`, replace line 20:

```
1. **Stage**: `<PLUGIN>/scripts/stage_zenodo.py --dry-run` then (after confirm) without dry-run. Walk `files/Figure*/` + `files/Source Data/`. Group by figure × sample type. Produce per-bucket zips in `Zenodo_upload/`.
```

with:

```
1. **Stage**: `<PLUGIN>/scripts/stage_zenodo.py` to preview, then (after confirm) re-run with `--write`. Walks `files/Figure*/` + `files/Source Data/`, groups by figure × sample type, and **moves** each group into a per-bucket folder. It does **not** create archives.
2. **Archive — manual, no script does this.** Create one archive per staged folder, e.g. `zip -r Zenodo_upload/Figure3_D.WES.zip "files/Figure 3/Figure3_D.WES"`. The backfill step reads these archives' member names; skip this and it silently patches nothing.
```

and replace line 33:

```
- All scripts default to `--dry-run`. Confirm before applying writes.
```

with:

```
- All deposit scripts default to dry-run and require `--write` to mutate anything. Show the user the dry-run output and get confirmation before re-running with `--write`.
```

- [ ] **Step 7b: Reword `commands/fdh-api.md` — it names a flag that does not exist**

Task 3's new doc guard fires on `commands/fdh-api.md:17,25` (and the behavioral
rule at `:37-38`). Investigated: the FDH **generated scripts are already
correct** — `delete_samples_by_id.py:46`, `delete_samples_by_uid.py:55` and
`patch_sample_links.py:95` each register only `--write` with
`help="... (default: dry-run)"`, and `skills/curation/FDH.md:75-76` templates
exactly that. So this is pure doc sloppiness: the prose says `--dry-run` when it
means *dry-run by default*, naming a flag no script has.

Reword so no doc instructs a nonexistent flag:

- `:17` — "respecting its `--dry-run` default" becomes "respecting its dry-run
  default"
- `:25` — "defaults writes to `--dry-run` (prints a preview)" becomes "defaults
  to a dry-run preview"
- `:37-38` — "Destructive ops (DELETE/PATCH) are dry-run first, always" is fine
  as prose; only ensure the literal string `--dry-run` does not appear.

Do **not** touch the FDH scripts or `FDH.md`'s template — they are already right.

- [ ] **Step 7c: Purge `--dry-run` from every other doc and docstring that instructs it**

Task 3's reviewer found three more places that will still tell an operator to
pass a flag this task deletes. None was owned by any task:

| location | current text | fix |
|---|---|---|
| `skills/curation/PHASES.md:206` | "Drives `scripts/stage_zenodo.py --dry-run` then (after user confirms) without `--dry-run`" | rewrite as: run it to preview, then re-run with `--write` |
| `scripts/fdh/generated/REGISTRY.md:6` | same `--dry-run` wording | reword to "dry-run by default; `--write` to apply" |
| `scripts/stage_zenodo.py:17` and `:207` | usage docstring shows `--dry-run` | update to `--write` |
| `scripts/apply_zenodo_links.py:15` | usage docstring shows `--dry-run` | update to `--write` |

The script-side guard only detects `add_argument`-shaped occurrences, so
deleting the three `add_argument("--dry-run")` lines turns it green while these
usage headers keep advertising the dead flag. That is the same class of drift
this whole task exists to close.

**Do not touch** `docs/superpowers/specs/2026-05-27-*.md` — that is a historical
spec recording what the plugin looked like then, and rewriting history to match
the present is worse than the drift.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run --with pytest --with openpyxl pytest tests/test_deposit_write_safety.py -v`
Expected: 13 passed.

Also run the drift suite and confirm `test_no_command_doc_instructs_dry_run` is
now green: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v -k dry_run`

- [ ] **Step 9: Run the drift test to see it partially recover**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v 2>&1 | tail -20`
Expected: the `stage_zenodo.py`, `apply_zenodo_links.py` and `test_no_script_offers_a_dry_run_flag` failures are gone. `--gse`, `--assay-sheets`, `--retrieve`, `--upload` failures remain — Task 5 and Task 17 handle those.

- [ ] **Step 10: Commit**

```bash
git add scripts/stage_zenodo.py scripts/apply_zenodo_links.py \
        scripts/apply_omero_ids.py scripts/apply_geo_accessions.py \
        commands/curate-deposit.md tests/test_deposit_write_safety.py
git commit -m "fix(deposit): standardize write-safety on --write

stage_zenodo.py and apply_zenodo_links.py used --dry-run and therefore
DEFAULTED TO WRITING, while curate-deposit.md claimed all four deposit
scripts default to dry-run. Inverted both to --write, made all four --help
strings state the default, and corrected the command doc.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Close the remaining documented-flag gaps

> **REWRITTEN after inspecting the real script.** The original version of this
> task said "`--gse` is a genuine missing feature." **That was wrong**, and
> implementing it as written would have added a duplicate, worse mechanism.
> Verified in `scripts/apply_geo_accessions.py`:
>
> | plan assumed | reality |
> |---|---|
> | no series flag exists | `--gse-bulk` (**required**, `:193`) and `--gse-sptx` (optional, `:206`) both exist |
> | no series-URL handling | `patch_agex()` (`:127-141`) already writes the series URL to every A.GEX row |
> | one GSE per submission | bulk and spatial are **separate GEO submissions with separate accessions**, which is why there are two flags |
>
> **The real defect is worse than a missing flag: the documented invocation
> cannot run at all.** `commands/curate-deposit.md:16` says
> `apply_geo_accessions.py --write --gse <GSE>`, but the script requires both
> `--gse-bulk` and `--gsm-csv` (`:193`, `:199`). Following the doc literally
> exits immediately with `error: the following arguments are required:
> --gse-bulk, --gsm-csv`. The doc invented a simpler CLI than the script has.
>
> So this task **reconciles the doc to the script**; it adds no feature.

**Files:**
- Modify: `commands/curate-deposit.md:11,16` (name the real flags)
- Modify: `skills/curation/PHASES.md:198` (same route heading)
- Modify: `commands/curate-qa.md` (document the flags Task 8 will add) — **doc only in this task**
- Modify: `commands/curate-consolidate.md` (align with the flags Task 8 will add)
- Modify: `tests/test_curate_commands_present.py` (CONTRACTS row + two deferred minors)
- Test: `tests/test_curate_commands_present.py` (existing, from Task 3)

**Interfaces:**
- Consumes: `tests/test_curate_commands_present.py::CONTRACTS` from Task 3
- Produces: a `curate-deposit.md` GEO route whose invocation actually runs, and a CONTRACTS row naming `--gse-bulk` / `--gsm-csv` instead of the nonexistent `--gse`

**Context:** Of the original five drift bugs, this one turned out to be doc fiction rather than a missing feature. `--assay-sheets`, `--upload`, `--master-baseline` and `--expected-counts` are consequences of the plugin-anchored paths and are fixed in Task 8. `--retrieve` and `--metadata-xlsx` are Task 17. **Do not add `--sheets-dir` handling here** — Task 8 owns that flag's retirement.

- [ ] **Step 1: Confirm the real CLI before changing any doc**

Run:

```bash
uv run --script scripts/apply_geo_accessions.py --help
```

Record which arguments are **required**. Expect `--gse-bulk` and `--gsm-csv`
required; `--gse-sptx`, `--sptx-gsm-csv`, `--sheets-dir` and `--write` optional.
Then confirm the documented invocation genuinely fails:

```bash
uv run --script scripts/apply_geo_accessions.py --write --gse GSE000001 ; echo "exit=$?"
```

Expect a non-zero exit and an `unrecognized arguments: --gse` / `required:
--gse-bulk, --gsm-csv` style error. **Paste that output into your report** — it
is the evidence that this was doc fiction, not a missing feature.

- [ ] **Step 2: Fix the CONTRACTS row to name flags that exist**

In `tests/test_curate_commands_present.py`, change the `apply_geo_accessions.py`
entry so it asserts the real flags:

```python
    ("curate-deposit.md", "scripts/apply_geo_accessions.py",
     ["--write", "--gse-bulk", "--gsm-csv"]),
```

Remove `--gse` from wherever it appears in `CONTRACTS` / `PLANNED_CONTRACTS` —
no task is going to add it, because the two-series design is correct and a
single `--gse` would be ambiguous between bulk and spatial.

- [ ] **Step 3: Fold in two deferred minors from Task 4's review**

Both are in `tests/test_curate_commands_present.py`:

1. Add `--zip-dir` to the `apply_zenodo_links.py` CONTRACTS row. It is newly
   documented at `commands/curate-deposit.md:23` and exists at
   `scripts/apply_zenodo_links.py:96-101`, but slipped past the hand-maintained
   table that exists to catch exactly this.
2. The comment at roughly `:45-46` still says "curate-deposit.md:20 still says
   `stage_zenodo.py --dry-run`; --write is target state". Untrue since Task 4.
   Rewrite it to describe the row's current, passing state.

- [ ] **Step 4: Rewrite the GEO route in `commands/curate-deposit.md`**

Replace the route heading at `:11` and the backfill step at `:16` so that a
curator can copy-paste and have it work. The heading must stop implying a
single `--gse`:

```markdown
### `/curate-deposit geo [--type bulk|spatial]`
```

and the backfill step must name every required argument:

```markdown
4. **Backfill (after GEO assigns accessions)**: run once to preview, then with
   `--write`:

   ```bash
   uv run --script <PLUGIN>/scripts/apply_geo_accessions.py \
       --gse-bulk GSE###### --gsm-csv <bulk-gsm-roster.csv> \
       [--gse-sptx GSE###### --sptx-gsm-csv <spatial-gsm-roster.csv>] \
       [--write]
   ```

   Bulk and spatial are **separate GEO submissions with separate series
   accessions**, which is why there are two pairs of flags. Omit the spatial
   pair to skip the spatial patch entirely. `--gsm-csv` is a whitespace-
   delimited roster mapping GSM accession to sample D-id.
```

- [ ] **Step 5: Mirror the heading fix in `skills/curation/PHASES.md:198`**

That line carries the same `[--gse GSE######]` fiction. Make it match the
corrected `curate-deposit.md` heading. Do not duplicate the full invocation
there — point to the command doc.

- [ ] **Step 6: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v`
Expected: the `apply_geo_accessions.py` row now passes on real flag names. The
rows owned by Tasks 8 and 17 stay RED. Report the exact remaining set.

- [ ] **Step 8: Align the two command docs with the flags Task 8 will add**

In `commands/curate-consolidate.md`, ensure the invocation line names the script and both flags:

```
Invoke `<PLUGIN>/scripts/consolidate_to_flat.py --assay-sheets assay_sheets [--all-in-one NAME]`.
```

In `commands/curate-qa.md`, ensure the invocation line reads:

```
Invoke `<PLUGIN>/scripts/qa_flat_sheets.py --upload assay_sheets/Arm{X}.xlsx [--master-baseline previous_metadata/<master>.xlsx] [--expected-counts <sampletype>=<n>,...]`.
```

These flags do not exist yet — Task 8 adds them. The drift test stays RED for these two rows until then, which is the intended signal.

- [ ] **Step 9: Commit**

```bash
git add scripts/apply_geo_accessions.py commands/curate-consolidate.md \
        commands/curate-qa.md tests/test_curate_commands_present.py
git commit -m "fix(deposit): add --gse to apply_geo_accessions, align consolidate/qa docs

--gse was documented in curate-deposit.md but never existed. Rows without an
assigned GSM now fall back to the series URL instead of silently keeping a
stale Link_PrimaryData. consolidate/qa docs now name the flags Task 8 adds;
those two drift rows stay RED until then by design.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage B — Prerequisites P1, P2, P3

These block both new modes. More entry points means more ways to hit the path bug, so they come before any mode work. Tests come before the refactor because these scripts have only `--help` smoke coverage.

### Task 6: Path-anchoring regression harness (RED)

**Files:**
- Create: `tests/test_path_anchoring.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing
- Produces: fixture `plugin_sentinel` (snapshots the plugin tree and asserts it is unchanged) and fixture `curation_project` (a minimal scaffolded project in a tmpdir), both consumed by Tasks 8, 9, 19, 26

**Context — the bug (toolkit spec P1):** ten scripts resolve project paths against the *plugin install directory*, so `/curate-consolidate` and `/curate-qa` with no arguments read and write inside the plugin checkout. `build_retrieve.py` and `fdh/fdh_api.py:161` already do it right and are the reference implementations.

- [ ] **Step 1: Write the shared fixtures**

Create `tests/conftest.py`:

```python
"""Shared fixtures. The plugin_sentinel fixture is the P1 regression guard:
no script may create, modify, or delete anything inside the plugin checkout.
"""
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Paths that legitimately change during a test run and must not trip the sentinel.
SENTINEL_IGNORE_PARTS = {
    ".git", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache",
    ".superpowers", "working", ".venv",
}


def _snapshot(root: Path) -> dict[str, str]:
    """Map repo-relative path -> sha256 of contents, for every tracked-ish file."""
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if SENTINEL_IGNORE_PARTS & set(p.relative_to(root).parts):
            continue
        out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def plugin_sentinel():
    """Fail the test if the plugin checkout changed while it ran."""
    before = _snapshot(REPO)
    yield REPO
    after = _snapshot(REPO)
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (created or deleted or modified), (
        "a script wrote inside the plugin checkout:\n"
        f"  created:  {created}\n"
        f"  deleted:  {deleted}\n"
        f"  modified: {modified}"
    )


@pytest.fixture
def curation_project(tmp_path):
    """A minimal curation project: the directory layout plus a v1 lockfile."""
    for d in ("files", "manuscript", "previous_metadata", "assay_sheets",
              "assay_sheets/4sheet_originals", "context", "scripts"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".dmac-curation.json").write_text(json.dumps({
        "schema_version": 1,
        "plugin_version": "0.3.0",
        "modes": {
            "pipeline": {"phase": 5, "lab": "KAM", "nextseek_project_id": 42}
        },
    }, indent=2))
    return tmp_path
```

- [ ] **Step 2: Write the failing regression test**

Create `tests/test_path_anchoring.py`:

```python
"""P1: no script may read or write inside the plugin checkout.

Each script is run from a tmpdir curation project. The plugin_sentinel
fixture hashes the whole plugin tree before and after and fails on any
change. Scripts that need inputs get them inside the tmpdir, never in the
plugin.
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Every script that resolved paths against the plugin dir before Task 8,
# with an argv that should be a no-op or a dry-run inside the project.
PLUGIN_ANCHORED = [
    ("scripts/consolidate_to_flat.py", ["--assay-sheets", "assay_sheets"]),
    ("scripts/qa_flat_sheets.py", ["--upload", "assay_sheets/ArmA.xlsx"]),
    ("scripts/stage_zenodo.py", []),
    ("scripts/apply_zenodo_links.py", ["--record-id", "1"]),
    ("scripts/apply_geo_accessions.py", []),
    ("scripts/review_metadata_vs_uploads.py", []),
    ("scripts/build_retrieve.py", ["--assay-sheets", "assay_sheets"]),
]


def _run(script_rel: str, argv: list[str], cwd: Path):
    return subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), *argv],
        cwd=cwd, capture_output=True, text=True, timeout=180,
    )


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_writes_nothing_in_plugin(script_rel, argv, curation_project,
                                         plugin_sentinel):
    """The script may fail (missing inputs is fine). It may not touch the plugin."""
    _run(script_rel, argv, curation_project)
    # plugin_sentinel asserts on teardown.


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_does_not_reference_plugin_paths_in_output(script_rel, argv,
                                                          curation_project):
    """A path under the plugin checkout appearing in output means the script
    resolved a PROJECT path against the plugin install dir."""
    result = _run(script_rel, argv, curation_project)
    blob = result.stdout + result.stderr
    plugin_str = str(REPO)
    leaked = [
        line for line in blob.splitlines()
        if plugin_str in line
        # The script's own path legitimately appears in tracebacks and usage.
        and script_rel.split("/")[-1] not in line
        and "/context/" not in line          # read-only plugin context is allowed
        and "/templates/" not in line        # read-only plugin templates are allowed
    ]
    assert not leaked, (
        f"{script_rel} resolved a project path against the plugin dir:\n"
        + "\n".join(leaked[:10])
    )


def test_reference_implementations_are_already_clean(curation_project,
                                                     plugin_sentinel):
    """build_retrieve.py and fdh_api.py are the models Task 8 refactors toward."""
    r = _run("scripts/build_retrieve.py",
             ["--assay-sheets", "assay_sheets", "--output", "RETRIEVE.TXT"],
             curation_project)
    assert r.returncode == 0, r.stderr
    assert (curation_project / "RETRIEVE.TXT").exists()
```

- [ ] **Step 3: Run it and record the failures**

Run: `uv run --with pytest --with openpyxl pytest tests/test_path_anchoring.py -v 2>&1 | tail -40`

Expected: `test_reference_implementations_are_already_clean` PASSES. Most `test_script_does_not_reference_plugin_paths_in_output` cases FAIL, showing plugin paths in output. Some `test_script_writes_nothing_in_plugin` cases FAIL — notably `consolidate_to_flat.py`, which deletes `.xlsx` files in `<plugin>/assay_sheets` (line 325-327) and creates `<plugin>/assay_sheets/4sheet_originals` (line 330).

**If `consolidate_to_flat.py` deletes anything real during this run, restore it with `git checkout -- .` before continuing.** This is precisely the bug being fixed.

- [ ] **Step 4: Commit the RED harness**

```bash
git add tests/conftest.py tests/test_path_anchoring.py
git commit -m "test: P1 path-anchoring regression harness (currently RED)

plugin_sentinel hashes the plugin tree around each script run and fails on
any change. Ten scripts resolve project paths against the plugin install
dir, so /curate-consolidate and /curate-qa currently read and write INSIDE
the checkout. build_retrieve.py already passes and is the reference shape.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The project-config seam (P2)

**Files:**
- Create: `scripts/_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `tests/conftest.py::curation_project` from Task 6
- Produces — every later task imports from here:
  - `plugin_root() -> Path`
  - `plugin_context(name: str) -> Path`
  - `find_project_root(start: Path | None = None) -> Path`
  - `ProjectConfig` dataclass with fields `root, lab, pi, nextseek_project_id, scientist, files, manuscript, previous_metadata, assay_sheets, four_sheet_dir, context, master_workbook, expected_counts, always_root`
  - `load_config(root: Path | None = None, **overrides) -> ProjectConfig`
  - `add_config_args(parser: argparse.ArgumentParser) -> None`
  - `config_from_args(args) -> ProjectConfig`

**Context:** four scripts independently propose a project config in `TODO(v0.2)` comments (`qa_flat_sheets.py:47-49`, `apply_zenodo_links.py:32`, `stage_zenodo.py:39`, `review_metadata_vs_uploads.py:44`). This is the one seam they all get.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""scripts/_config.py — the single project-config seam (P2)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _config  # noqa: E402


def test_plugin_root_is_the_checkout():
    assert _config.plugin_root() == REPO


def test_plugin_context_resolves_readonly_bundled_data():
    p = _config.plugin_context("sampletypes_db.json")
    assert p.exists()
    assert p.parent == REPO / "context"


def test_find_project_root_walks_up_to_the_lockfile(curation_project):
    nested = curation_project / "assay_sheets" / "4sheet_originals"
    assert _config.find_project_root(nested) == curation_project


def test_find_project_root_falls_back_to_cwd_when_no_lockfile(tmp_path):
    assert _config.find_project_root(tmp_path) == tmp_path


def test_find_project_root_never_returns_the_plugin(tmp_path, monkeypatch):
    """Walking up from a tmpdir must not land on the plugin checkout."""
    monkeypatch.chdir(tmp_path)
    assert _config.find_project_root() != REPO


def test_load_config_reads_lockfile_pipeline_mode(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.root == curation_project
    assert cfg.lab == "KAM"
    assert cfg.nextseek_project_id == 42


def test_load_config_derives_directory_paths(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.assay_sheets == curation_project / "assay_sheets"
    assert cfg.four_sheet_dir == curation_project / "assay_sheets" / "4sheet_originals"
    assert cfg.previous_metadata == curation_project / "previous_metadata"
    assert cfg.context == curation_project / "context"
    assert cfg.files == curation_project / "files"


def test_no_config_path_points_inside_the_plugin(curation_project):
    cfg = _config.load_config(curation_project)
    for name in ("root", "files", "manuscript", "previous_metadata",
                 "assay_sheets", "four_sheet_dir", "context"):
        value = getattr(cfg, name)
        assert REPO not in value.parents and value != REPO, (
            f"cfg.{name} = {value} is inside the plugin checkout"
        )


def test_overrides_win_over_lockfile(curation_project):
    cfg = _config.load_config(curation_project, lab="ENG", nextseek_project_id=7)
    assert cfg.lab == "ENG"
    assert cfg.nextseek_project_id == 7


def test_none_overrides_are_ignored(curation_project):
    """argparse defaults are None; they must not clobber lockfile values."""
    cfg = _config.load_config(curation_project, lab=None)
    assert cfg.lab == "KAM"


def test_master_workbook_globs_previous_metadata(curation_project):
    (curation_project / "previous_metadata" / "MetNet All 260527.xlsx").write_bytes(b"x")
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook is not None
    assert cfg.master_workbook.name == "MetNet All 260527.xlsx"


def test_master_workbook_is_none_when_absent(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook is None


def test_master_workbook_picks_most_recent_of_several(curation_project):
    import os, time
    older = curation_project / "previous_metadata" / "Lab All 250101.xlsx"
    newer = curation_project / "previous_metadata" / "Lab All 260527.xlsx"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    os.utime(older, (time.time() - 5000, time.time() - 5000))
    cfg = _config.load_config(curation_project)
    assert cfg.master_workbook == newer


def test_expected_counts_defaults_empty(curation_project):
    cfg = _config.load_config(curation_project)
    assert cfg.expected_counts == {}


def test_expected_counts_parsed_from_lockfile(curation_project):
    lock = json.loads((curation_project / ".dmac-curation.json").read_text())
    lock["modes"]["pipeline"]["expected_counts"] = {"OOC": 122, "CEL": 2}
    (curation_project / ".dmac-curation.json").write_text(json.dumps(lock))
    cfg = _config.load_config(curation_project)
    assert cfg.expected_counts == {"OOC": 122, "CEL": 2}


def test_add_config_args_and_config_from_args(curation_project, monkeypatch):
    import argparse
    monkeypatch.chdir(curation_project)
    parser = argparse.ArgumentParser()
    _config.add_config_args(parser)
    args = parser.parse_args(["--lab", "WHI"])
    cfg = _config.config_from_args(args)
    assert cfg.lab == "WHI"
    assert cfg.root == curation_project


def test_parse_expected_counts_flag_format():
    assert _config.parse_expected_counts("OOC=122,CEL=2") == {"OOC": 122, "CEL": 2}
    assert _config.parse_expected_counts("") == {}
    assert _config.parse_expected_counts(None) == {}


def test_parse_expected_counts_rejects_malformed():
    with pytest.raises(ValueError):
        _config.parse_expected_counts("OOC")
    with pytest.raises(ValueError):
        _config.parse_expected_counts("OOC=notanumber")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_config.py -v`
Expected: collection error — `ModuleNotFoundError: No module named '_config'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/_config.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one project-config seam for dmac-curation scripts (toolkit spec P2).

Before this module, four scripts each carried a `TODO(v0.2)` proposing their
own project config, and ten resolved project paths against the PLUGIN install
directory — so `/curate-consolidate` with no args read and wrote inside the
plugin checkout (toolkit spec P1).

Two rules this module exists to enforce:

  1. PROJECT paths resolve from the current working directory, never from
     ``Path(__file__).parent.parent``.
  2. PLUGIN paths are read-only and limited to ``context/`` and ``templates/``.

Resolution order for any value, highest priority first:
  explicit CLI flag  ->  project lockfile  ->  derived default
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

LOCKFILE_NAME = ".dmac-curation.json"

# Anchored at THIS file, and used only for read-only bundled data.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def plugin_root() -> Path:
    """Absolute path of the plugin checkout. Read-only for everything but tests."""
    return _PLUGIN_ROOT


def plugin_context(name: str) -> Path:
    """A read-only bundled context file, e.g. plugin_context('sampletypes_db.json')."""
    return _PLUGIN_ROOT / "context" / name


def plugin_template(name: str) -> Path:
    """A read-only bundled Jinja2 template, e.g. plugin_template('CLAUDE.md.j2')."""
    return _PLUGIN_ROOT / "templates" / name


def find_project_root(start: Path | None = None) -> Path:
    """Nearest ancestor holding a lockfile; else `start` itself.

    Never returns the plugin checkout: a mode may legitimately run from any
    cwd, and silently adopting the plugin as "the project" is the P1 bug.
    """
    start = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if candidate == _PLUGIN_ROOT:
            break
        if (candidate / LOCKFILE_NAME).is_file():
            return candidate
    return start


def parse_expected_counts(raw: str | None) -> dict[str, int]:
    """Parse ``--expected-counts 'OOC=122,CEL=2'`` into a dict."""
    if not raw:
        return {}
    out: dict[str, int] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(
                f"malformed --expected-counts entry {chunk!r}; want SAMPLETYPE=N"
            )
        key, _, value = chunk.partition("=")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"--expected-counts {key.strip()!r} value {value.strip()!r} "
                f"is not an integer"
            ) from exc
    return out


@dataclass
class ProjectConfig:
    """Everything a pipeline script needs to know about where it is running."""

    root: Path
    lab: str | None = None
    pi: str | None = None
    nextseek_project_id: int | None = None
    scientist: str | None = None
    master_workbook: Path | None = None
    expected_counts: dict[str, int] = field(default_factory=dict)
    always_root: set[str] = field(default_factory=set)

    # ---- derived directories (always under root) --------------------------
    @property
    def files(self) -> Path:
        return self.root / "files"

    @property
    def manuscript(self) -> Path:
        return self.root / "manuscript"

    @property
    def previous_metadata(self) -> Path:
        return self.root / "previous_metadata"

    @property
    def assay_sheets(self) -> Path:
        return self.root / "assay_sheets"

    @property
    def four_sheet_dir(self) -> Path:
        return self.assay_sheets / "4sheet_originals"

    @property
    def context(self) -> Path:
        return self.root / "context"

    @property
    def lockfile(self) -> Path:
        return self.root / LOCKFILE_NAME


def _read_lockfile_pipeline(root: Path) -> dict:
    """Pipeline-mode settings from a v0 or v1 lockfile. Never raises."""
    path = root / LOCKFILE_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if raw.get("schema_version") == 1:
        return dict(raw.get("modes", {}).get("pipeline", {}))
    # v0: flat keys ARE the pipeline mode's settings.
    return {k: v for k, v in raw.items() if not k.startswith("plugin_")}


def _find_master_workbook(previous_metadata: Path) -> Path | None:
    """Most recently modified ``*All*.xlsx`` in previous_metadata/, or None.

    Matches the existing glob in stage_zenodo.py:52, apply_zenodo_links.py:46
    and review_metadata_vs_uploads.py:57 — but rooted at the PROJECT.
    """
    if not previous_metadata.is_dir():
        return None
    candidates = [
        p for p in previous_metadata.glob("*All*.xlsx")
        if p.is_file() and not p.name.startswith("~")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_config(root: Path | None = None, **overrides) -> ProjectConfig:
    """Build a ProjectConfig. Non-None keyword overrides beat the lockfile.

    ``None`` overrides are dropped, so an argparse default of None does not
    clobber a real lockfile value.
    """
    root = Path(root).resolve() if root is not None else find_project_root()
    locked = _read_lockfile_pipeline(root)
    overrides = {k: v for k, v in overrides.items() if v is not None}

    cfg = ProjectConfig(
        root=root,
        lab=overrides.get("lab", locked.get("lab")),
        pi=overrides.get("pi", locked.get("pi")),
        nextseek_project_id=overrides.get(
            "nextseek_project_id", locked.get("nextseek_project_id")),
        scientist=overrides.get("scientist", locked.get("scientist")),
        expected_counts=overrides.get(
            "expected_counts", dict(locked.get("expected_counts") or {})),
        always_root=set(overrides.get(
            "always_root", locked.get("always_root") or [])),
    )
    master = overrides.get("master_workbook")
    cfg.master_workbook = (
        Path(master).resolve() if master else _find_master_workbook(cfg.previous_metadata)
    )
    return cfg


def add_config_args(parser: argparse.ArgumentParser) -> None:
    """Register the standard project-config overrides on any script's parser."""
    g = parser.add_argument_group("project config")
    g.add_argument("--project-root", type=Path, default=None,
                   help="Curation project root (default: nearest ancestor with "
                        f"{LOCKFILE_NAME}, else cwd)")
    g.add_argument("--lab", default=None, help="Lab code, e.g. KAM")
    g.add_argument("--pi", default=None, help="PI short name")
    g.add_argument("--master-baseline", type=Path, default=None,
                   help="Master workbook (default: newest previous_metadata/*All*.xlsx)")
    g.add_argument("--expected-counts", default=None,
                   help="Per-sampletype row expectations, e.g. 'OOC=122,CEL=2'")


def config_from_args(args) -> ProjectConfig:
    """Build a ProjectConfig from a parser that used add_config_args()."""
    return load_config(
        getattr(args, "project_root", None),
        lab=getattr(args, "lab", None),
        pi=getattr(args, "pi", None),
        master_workbook=getattr(args, "master_baseline", None),
        expected_counts=parse_expected_counts(
            getattr(args, "expected_counts", None)) or None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with openpyxl pytest tests/test_config.py -v`
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_config.py tests/test_config.py
git commit -m "feat(config): one project-config seam resolved from cwd (P2)

Replaces four independent TODO(v0.2) config proposals in qa_flat_sheets,
apply_zenodo_links, stage_zenodo and review_metadata_vs_uploads. Project
paths resolve from cwd via find_project_root(); plugin access is limited to
read-only plugin_context()/plugin_template(). Resolution order is CLI flag,
then lockfile, then derived default, with None overrides dropped so argparse
defaults never clobber lockfile values.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Re-anchor the pipeline scripts to cwd (P1)

**Files:**
- Modify: `scripts/consolidate_to_flat.py:55-57,86-87,274,294-350`
- Modify: `scripts/qa_flat_sheets.py:42-67,120-127,355-366`
- Modify: `scripts/nextseek_api.py:44,49,261-266`
- Modify: `scripts/stage_zenodo.py:33-34,52`
- Modify: `scripts/apply_zenodo_links.py:29-30,46,103`
- Modify: `scripts/apply_geo_accessions.py:39-40`
- Modify: `scripts/review_metadata_vs_uploads.py:36-37,57`
- Modify: `scripts/smb_pull.py:46-47,52,73-74,101`
- Modify: `scripts/upload_geo_ncftp.sh:19`
- Test: `tests/test_path_anchoring.py` (existing, from Task 6)

**Interfaces:**
- Consumes: `_config.load_config`, `_config.add_config_args`, `_config.config_from_args`, `_config.plugin_context` from Task 7; `plugin_sentinel` and `curation_project` from Task 6
- Produces: every listed script accepts `--project-root` and resolves all project paths beneath it

**Context:** this is the refactor Task 6's harness was written to gate. `build_retrieve.py` needs no change; it is already correct and serves as the shape to copy.

- [ ] **Step 1: Confirm the harness is still RED**

Run: `uv run --with pytest --with openpyxl pytest tests/test_path_anchoring.py -v 2>&1 | tail -25`
Expected: the failures recorded in Task 6 Step 3, unchanged.

- [ ] **Step 2: Add the shared import preamble to each script**

Every script in the list gains this immediately after its stdlib imports. `_config.py` sits beside them in `scripts/`, so a `sys.path` insert of the script's own directory is all that is required:

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import add_config_args, config_from_args, plugin_context  # noqa: E402
from _config import ProjectRootError  # noqa: E402
```

> **ADDED after Task 7's review.** `config_from_args()` calls
> `find_project_root()`, which now **raises `ProjectRootError`** when it is run
> from the plugin checkout (or a plugin subdir) with no lockfile — the deliberate
> refusal that stops a script from treating the plugin as a project. This is a
> contract change: callers that expect a `Path` will otherwise surface a raw
> traceback. In **each** script's `main()`, wrap the config resolution so the
> refusal reads as a clean error, not a stack trace:
>
> ```python
>     try:
>         cfg = config_from_args(args)
>     except ProjectRootError as exc:
>         print(f"error: {exc}", file=sys.stderr)
>         return 2
> ```
>
> (Use `sys.exit(2)` instead of `return 2` in scripts whose `main` is not called
> for its return value.) This only fires from inside the plugin with no project;
> an ordinary non-project cwd still resolves to cwd, verified in Task 7.

- [ ] **Step 3: Fix `consolidate_to_flat.py`**

Delete lines 55-57:

```python
REPO = str(Path(__file__).resolve().parent.parent)
SRC  = os.path.join(REPO, "assay_sheets")
ARCH = os.path.join(SRC, "4sheet_originals")
```

The module-level assay-ID lookup at lines 86-87 and 125 must also stop being module-level, because it reads project files:

```python
_CACHE_PATH = os.path.join(REPO, "context", "assay_ids_cache.json")
_SYNONYMS_PATH = os.path.join(REPO, "context", "assay_synonyms.json")
...
ASSAY_ID_LOOKUP, ASSAY_SYNONYMS, _ASSAY_ID_SOURCE = _load_assay_id_lookup()
```

Change `_load_assay_id_lookup()` to take the project context dir, and drop the module-level call:

```python
def _load_assay_id_lookup(context_dir):
    """Returns (lookup_dict, synonyms_dict, source_description)."""
    cache_path = context_dir / "assay_ids_cache.json"
    synonyms_path = context_dir / "assay_synonyms.json"
    lookup = {}
    synonyms = {}
    sources = []

    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
            lookup = cache.get("assay_id_by_title") or {}
            sources.append(f"cache {cache_path.name} "
                           f"(project {cache.get('project_id')!r}, "
                           f"{len(lookup)} assays, fetched "
                           f"{cache.get('fetched_at_utc', '?')})")
        except (OSError, json.JSONDecodeError) as e:
            sources.append(f"cache UNREADABLE: {e}")
    else:
        sources.append("no cache (run scripts/nextseek_api.py fetch-assays)")

    if synonyms_path.exists():
        try:
            syn_doc = json.loads(synonyms_path.read_text())
            synonyms = syn_doc.get("synonyms_by_cited_name") or {}
            sources.append(f"synonyms {synonyms_path.name} "
                           f"({len(synonyms)} mappings)")
        except (OSError, json.JSONDecodeError) as e:
            sources.append(f"synonyms UNREADABLE: {e}")
    else:
        sources.append("no synonyms file")

    return lookup, synonyms, " + ".join(sources)
```

`resolve_assay_id` currently closes over the module globals. Give it explicit parameters:

```python
def resolve_assay_id(cited_name, lookup, synonyms):
    """Resolve a cited assay title to (resolved_title, assay_id_or_None)."""
    if not cited_name:
        return "", None
    if cited_name in lookup:
        return cited_name, lookup[cited_name]
    if cited_name in synonyms:
        canonical = synonyms[cited_name]
        if canonical in lookup:
            return canonical, lookup[canonical]
    return cited_name, None
```

`build_arm_flat` gains the lookup and the output dir:

```python
def build_arm_flat(arm_name, source_files, out_dir, lookup, synonyms):
    """source_files: list of (sampletype, parent_assay, [records])."""
```

Inside it, replace the `resolve_assay_id(parent_assay)` call with
`resolve_assay_id(parent_assay, lookup, synonyms)`, and replace line 274:

```python
    out = os.path.join(SRC, f"{arm_name}.xlsx")
```

with:

```python
    out = out_dir / f"{arm_name}.xlsx"
```

Rewrite the `__main__` block to resolve everything from the config:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_args(parser)
    parser.add_argument(
        "--assay-sheets", type=Path, default=None,
        help="Directory holding the 4-sheet inputs and receiving the flat "
             "outputs (default: <project-root>/assay_sheets)",
    )
    parser.add_argument(
        "--all-in-one", metavar="NAME", default=None,
        help="Consolidate ALL 4-sheet inputs into a single flat output named "
             "NAME.xlsx, rather than grouping by filename prefix.",
    )
    args = parser.parse_args()

    cfg = config_from_args(args)
    src = Path(args.assay_sheets).resolve() if args.assay_sheets else cfg.assay_sheets
    arch = src / "4sheet_originals"

    if not src.is_dir():
        print(f"ERROR: {src} is not a directory", file=sys.stderr)
        raise SystemExit(2)

    lookup, synonyms, source_desc = _load_assay_id_lookup(cfg.context)
    print(f"Project root:    {cfg.root}")
    print(f"Assay sheets:    {src}")
    print(f"Assay-ID source: {source_desc}\n")
```

Then in the remainder of that block, replace every `SRC` with `src`, every `ARCH` with `arch`, every `ASSAY_ID_LOOKUP` with `lookup`, every `ASSAY_SYNONYMS` with `synonyms`, and change the `build_arm_flat` call to:

```python
        out, n = build_arm_flat(arm, sources, src, lookup, synonyms)
```

**The destructive cleanup at lines 325-327 is the single most dangerous line in the plugin** — it deletes every `.xlsx` without an underscore in `SRC`, which today is `<plugin>/assay_sheets`. Guard it:

```python
    # Clean any prior consolidated outputs so we don't mix old + new.
    # Guarded: never delete outside the resolved project's assay-sheets dir.
    assert src != plugin_context("").parent, "refusing to clean inside the plugin"
    for f in os.listdir(src):
        if f.endswith(".xlsx") and "_" not in f:
            os.remove(src / f)
```

- [ ] **Step 4: Fix `qa_flat_sheets.py`**

> **AMENDED after Task 3 ran.** This script currently has **zero long flags** —
> its only argument is the positional `upload` with `nargs="?"` (`:358`). You are
> building its entire flag surface from scratch, not extending one.
>
> Decide the positional's fate explicitly and say so in your report. Recommended:
> **keep it as an optional positional alias for `--upload`**, so existing
> invocations like `qa_flat_sheets.py assay_sheets/ArmA.xlsx` keep working, and
> error clearly if both a positional and `--upload` are given. The old behaviour
> of joining a relative positional onto the *plugin* directory (`:364-365`) must
> go regardless — that is the P1 bug.

Delete lines 42-67 (`REPO`, the `TODO(v0.2)` block, `DEFAULT_UPLOAD`, `PREV_METADATA`, `ALWAYS_ROOT`, `EXPECTED_COUNTS`, `EXPECTED_TOTAL`). These are IntravChip's constants; they move into the config.

Change `load_prev_uids()` to take a path:

```python
def load_prev_uids(prev_metadata):
    """Return set of all UIDs already in the master baseline workbook."""
    if prev_metadata is None or not Path(prev_metadata).exists():
        print(f"  ! WARNING: no master baseline workbook — parent-resolvability "
              f"will only check intra-upload UIDs")
        return set()
    wb = openpyxl.load_workbook(prev_metadata, data_only=True, read_only=True)
    ...
```

Change `load_sampletype_schemas()` to read the **plugin's** bundled catalog, which is legitimate read-only plugin access, with a project-local override taking precedence:

```python
def load_sampletype_schemas(context_dir):
    """{short_code: {required: set, name: str}} from the sample type catalog.

    A project-local context/sampletypes_db.json wins over the plugin's bundled
    copy, so a project can pin a vintage.
    """
    local = Path(context_dir) / "sampletypes_db.json"
    path = local if local.is_file() else plugin_context("sampletypes_db.json")
    types = json.loads(Path(path).read_text())
    out = {}
    for t in types:
        code = t.get("SampleType")
        req = t.get("Required Metadata") or ""
        req_set = {x.strip() for x in req.split(",") if x.strip()}
        out[code] = {"required": req_set, "name": t.get("Name", "")}
    return out
```

Change `main()`'s signature to take the config:

```python
def main(upload_path, cfg):
    prev_metadata = cfg.master_workbook
    expected_counts = cfg.expected_counts
    always_root = cfg.always_root or {"CEL", "MDL"}
    expected_total = sum(expected_counts.values()) if expected_counts else None
    print(f"Project root:    {cfg.root}")
    print(f"Upload file:     {upload_path}")
    print(f"Master baseline: {prev_metadata or '(none)'}")
    print()

    prev_uids = load_prev_uids(prev_metadata)
    schemas = load_sampletype_schemas(cfg.context)
    ...
```

Inside `main()`, replace every `ALWAYS_ROOT` with `always_root` and every `EXPECTED_COUNTS` with `expected_counts`. In the per-sample-type report loop, handle the now-optional expectations:

```python
    all_st = sorted(set(sampletype_counts) | set(expected_counts))
    expected_ok = True
    for st in all_st:
        actual = sampletype_counts.get(st, 0)
        expected = expected_counts.get(st)
        if expected is None:
            marker = "" if not expected_counts else "  (unexpected sampletype!)"
            if expected_counts:
                expected_ok = False
            print(f"  {st:>6}: {actual:>5}{marker}")
        elif actual != expected:
            print(f"  {st:>6}: {actual:>5}  ✗ expected {expected}")
            expected_ok = False
        else:
            print(f"  {st:>6}: {actual:>5}  ✓")
    total_line = f"  {'TOTAL':>6}: {sum(sampletype_counts.values()):>5}"
    if expected_total is not None:
        total_line += f"  (expected {expected_total})"
    print(total_line)
```

Rewrite the `__main__` block:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_args(parser)
    parser.add_argument(
        "--upload", type=Path, default=None,
        help="Consolidated flat-format xlsx to QA "
             "(default: the single Arm*.xlsx under <project>/assay_sheets)",
    )
    args = parser.parse_args()
    cfg = config_from_args(args)

    upload = args.upload
    if upload is None:
        candidates = sorted(
            p for p in cfg.assay_sheets.glob("*.xlsx")
            if "_" not in p.stem and not p.name.startswith("~")
        )
        if len(candidates) != 1:
            print(f"ERROR: pass --upload; found {len(candidates)} consolidated "
                  f"sheets in {cfg.assay_sheets}: "
                  f"{[p.name for p in candidates]}", file=sys.stderr)
            sys.exit(2)
        upload = candidates[0]
    upload = Path(upload)
    if not upload.is_absolute():
        upload = (cfg.root / upload).resolve()
    if not upload.is_file():
        print(f"ERROR: {upload} does not exist", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(upload, cfg))
```

Note the removed behaviour: the old line 364-365 joined a relative upload path onto `REPO` (the plugin). It now joins onto `cfg.root`.

- [ ] **Step 5: Fix `nextseek_api.py`**

Line 44-49:

```python
REPO = Path(__file__).resolve().parent.parent
...
DEFAULT_CACHE_PATH = REPO / "context" / "assay_ids_cache.json"
```

becomes:

```python
# Kept only for the plugin-local .env fallback; never used for project paths.
_PLUGIN = Path(__file__).resolve().parent.parent
```

and the cache default moves into the argparse block. Change the `--output` argument (line 434) to:

```python
    fa.add_argument("--output", type=Path, default=None,
                    help="Where to write assay_ids_cache.json "
                         "(default: <project-root>/context/assay_ids_cache.json)")
```

and in the handler resolve it:

```python
    cfg = config_from_args(args)
    out_path = args.output or (cfg.context / "assay_ids_cache.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
```

Fix `_load_dotenv` at lines 261-266 to match `fdh_api.py:161` — cwd first, plugin second:

```python
def _load_dotenv():
    """setdefault env vars from cwd/.env then <plugin>/.env (idempotent).

    Mirrors scripts/fdh/fdh_api.py:159-169, the reference implementation.
    """
    for candidate in (Path.cwd() / ".env", _PLUGIN / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
```

Add `add_config_args(fa)` to the `fetch-assays` subparser and `add_config_args(va)` to the `validate` subparser.

- [ ] **Step 6: Fix the four `ROOT = Path(__file__).resolve().parent.parent` scripts**

For each of `stage_zenodo.py` (line 33), `apply_zenodo_links.py` (line 29), `apply_geo_accessions.py` (line 39), and `review_metadata_vs_uploads.py` (line 36): delete the `ROOT` assignment and the derived constants below it, add `add_config_args(ap)` to the parser, and derive paths inside `main()` from `cfg = config_from_args(args)`:

| script | old constant | new expression |
|---|---|---|
| `stage_zenodo.py` | `FILES = ROOT / "files"` | `cfg.files` |
| `stage_zenodo.py` | `glob(ROOT/"previous_metadata"/"*All*.xlsx")` | `cfg.master_workbook` |
| `stage_zenodo.py` | default `--out` `ROOT / "Zenodo_upload"` | `cfg.root / "Zenodo_upload"` |
| `apply_zenodo_links.py` | `ASSAY = ROOT / "assay_sheets"` | `cfg.assay_sheets` |
| `apply_zenodo_links.py` | `glob(ROOT/"previous_metadata"/"*All*.xlsx")` | `cfg.master_workbook` |
| `apply_zenodo_links.py` | `--zip-dir` default `ROOT / "Zenodo_upload"` | `cfg.root / "Zenodo_upload"` |
| `apply_geo_accessions.py` | `SHEETS = ROOT / "assay_sheets"` | `cfg.assay_sheets` |

**While you are in `apply_geo_accessions.py`, fix its self-contradicting module
docstring.** Found during Task 5 and left unfixed there because that task was
doc-only and this file lives under `scripts/`:

- `:11` prose says *"Reads a GEO accession CSV (two columns: **sample_id,
  gsm_accession**)"* — reversed.
- `:16-17`'s own example shows `GSM9751823    sample_title_ending_in_D123456`,
  i.e. GSM first.
- `parse_gsm_csv()` reads `gsm = parts[0]`, `title = parts[1]` — GSM first.

So the prose contradicts both the example directly beneath it and the parser.
A curator who builds a roster from the prose gets every row dropped by the
D-id regex, a screenful of `WARNING: could not extract D-id`, and an empty
patch set. Correct `:11` to describe column 1 as the GSM accession and column 2
as the sample title from which the D-id is extracted. `commands/curate-deposit.md`
already documents this correctly as of Task 5 — match it.
| `review_metadata_vs_uploads.py` | `SHEETS = ROOT / "assay_sheets"` | `cfg.assay_sheets` |
| `review_metadata_vs_uploads.py` | `glob(ROOT/"previous_metadata"/"*All*.xlsx")` | `cfg.master_workbook` |

Each of these scripts has a module-level helper that globs `previous_metadata`. Delete those helpers and use `cfg.master_workbook`, which implements the same "newest `*All*.xlsx`" rule in `_config._find_master_workbook`.

Add `--assay-sheets` to `review_metadata_vs_uploads.py`'s parser (the drift test requires it):

```python
    ap.add_argument("--assay-sheets", type=Path, default=None,
                    help="Directory of upload sheets "
                         "(default: <project-root>/assay_sheets)")
```

and resolve `sheets = Path(args.assay_sheets).resolve() if args.assay_sheets else cfg.assay_sheets`.

**Retire the old `--sheets-dir` (`:238`) in the same edit** — do not leave both.
A two-name CLI is how the `--record-id`/`--zenodo-record` drift started, and
Task 17 is explicitly told this is yours to settle. Update any use site of
`args.sheets_dir` to `sheets`.

- [ ] **Step 7: Fix `smb_pull.py`**

Line 46-47 and 52 and 73-74 and 101. Replace:

```python
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
...
SHARE = os.environ.get("SMB_SHARE", "engelward")
...
OUT_DIR = ROOT / "GEO" / "bulk_rna" / "fastq"
MANIFEST = ROOT / "GEO" / "bulk_rna" / "manifest.tsv"
```

with:

```python
_PLUGIN = Path(__file__).resolve().parents[1]
# cwd .env first, plugin .env second — matches fdh_api.py:161.
for _candidate in (Path.cwd() / ".env", _PLUGIN / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
...
SHARE = os.environ.get("SMB_SHARE")
if not SHARE:
    print("ERROR: set SMB_SHARE in .env (no default share name)", file=sys.stderr)
    sys.exit(2)
```

and move `OUT_DIR`/`MANIFEST` into `main()` as flags:

```python
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Destination for pulled files "
                         "(default: <project-root>/GEO/bulk_rna/fastq)")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="Manifest TSV path "
                         "(default: <project-root>/GEO/bulk_rna/manifest.tsv)")
```

resolved as `out_dir = args.out_dir or (cfg.root / "GEO" / "bulk_rna" / "fastq")`.

The hardcoded input at line 101, `ROOT / "new_files_from_lee" / "All Samples Used in Manuscript #1.xlsx"`, becomes `cfg.master_workbook` with a clear error when it is None.

- [ ] **Step 8: Fix `upload_geo_ncftp.sh`**

Line 19 currently reads:

```bash
cd "$(dirname "$0")/.."
```

which puts the script in the plugin root. Replace with a no-op — the script should run in the caller's cwd:

```bash
# Intentionally NOT cd-ing to the script's directory. This script operates on
# paths the caller passes, resolved against the caller's cwd. Anchoring to the
# script location made /curate-deposit upload from inside the plugin checkout.
```

Verify no later line in the script depends on that `cd` by running:

```bash
grep -n '\.\./\|\$(dirname' scripts/upload_geo_ncftp.sh
```

and converting any surviving relative-to-script path into an explicit argument.

- [ ] **Step 9: Run the path-anchoring harness to verify it passes**

Run: `uv run --with pytest --with openpyxl pytest tests/test_path_anchoring.py -v`
Expected: all tests pass.

- [ ] **Step 10: Run the drift test — it should now be fully green except `--retrieve`**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v 2>&1 | tail -20`
Expected: only the `curate-validate.md` / `review_metadata_vs_uploads.py` `--retrieve` row still fails. Task 17 closes it.

- [ ] **Step 11: Run the full suite for regressions**

Run: `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v 2>&1 | tail -30`
Expected: everything green except the one known `--retrieve` row.

- [ ] **Step 12: Commit**

```bash
git add scripts/ tests/
git commit -m "refactor(scripts): resolve project paths from cwd, not the plugin (P1)

Ten scripts anchored project paths at Path(__file__).parent.parent, so
/curate-consolidate and /curate-qa read and WROTE inside the plugin checkout
-- consolidate_to_flat.py:325 deleted xlsx files there. All now resolve
through _config.config_from_args(); plugin access is read-only context/ and
templates/ only. nextseek_api and smb_pull now load cwd/.env before the
plugin's, matching fdh_api.py:161. upload_geo_ncftp.sh no longer cd's to the
plugin root.

tests/test_path_anchoring.py is now green.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: De-project `_common.py` (P3)

**Files:**
- Modify: `scripts/_common.py` (delete lines 29-67 and 258-293; rework 91-183)
- Create: `scripts/_project_constants.py.example`
- Modify: `scripts/qa_flat_sheets.py` (remove the IntravChip residue noted in Task 8)
- Modify: `scripts/rename_files.py:56-90` (Figure 1-7 dirs to a flag)
- Test: `tests/test_common.py` (existing — extend)

**Interfaces:**
- Consumes: `_config.ProjectConfig`, `_config.plugin_context` from Task 7
- Produces: `_common` exporting only `mint_uid`, `write_4sheet_xlsx`, `sampletype_schema`, `schema_column_order`, `load_manifest`, `load_omero`, `load_master_workbook`, `master_lookup`, `save_uid_map`, `load_uid_map`, `PLACEHOLDER`, `placeholder`

**Context:** `scripts/_common.py` is not a shared library, it is IntravChip's constants. `L38` hardcodes the filename `MetNet All 260527.xlsx`; `L46-51` hardcodes HUVEC/MCF-7 UIDs; **`L55` is `SCIENTIST = "Marie Floryan"`**; `L58-66` carries IntravChip manuscript section titles; `L260-293` is a table of IntravChip device-id regexes. Anything importing `_common` inherits all of it. Generated per-project `build_<arm>.py` scripts import from here, so the module must stay importable and its surviving names must keep their signatures.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_common.py` entirely:

```python
"""scripts/_common.py must be a shared library, not IntravChip's constants (P3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _common  # noqa: E402


# ---- surviving shared API -------------------------------------------------

def test_mint_uid_signature():
    assert _common.mint_uid("RNA", "KAM", "190902", 1) == "RNA-190902KAM-1"


def test_mint_uid_format():
    assert _common.mint_uid("D.SEQ", "ENG", "190504", 42) == "D.SEQ-190504ENG-42"


def test_placeholder_marker_shape():
    """SKILL.md hard rule 8 — greppable marker, never a blank."""
    assert _common.placeholder("no tumor parent") == (
        "*** PLACEHOLDER: no tumor parent ***"
    )
    assert _common.PLACEHOLDER in _common.placeholder("x")


def test_schema_column_order_is_uid_then_schema_then_extras():
    """The genuinely shared capability from _common.py:212-227."""
    schema = {
        "SampleType": "TST",
        "Required Metadata": "Name, Parent",
        "Standard Metadata": "Notes",
        "Possible Metadata Fields": "Tags",
    }
    samples = [{"UID": "TST-1", "Name": "a", "Extra": "z"}]
    assert _common.schema_column_order(schema, samples) == [
        "UID", "Name", "Parent", "Notes", "Tags", "Extra",
    ]


def test_sampletype_schema_reads_the_plugin_catalog():
    rec = _common.sampletype_schema("MUS")
    assert rec["SampleType"] == "MUS"


def test_sampletype_schema_accepts_an_explicit_catalog(tmp_path):
    catalog = tmp_path / "types.json"
    catalog.write_text(json.dumps([{"SampleType": "ZZZ", "Name": "Fake"}]))
    rec = _common.sampletype_schema("ZZZ", catalog=catalog)
    assert rec["Name"] == "Fake"


def test_sampletype_schema_raises_on_unknown():
    with pytest.raises(KeyError):
        _common.sampletype_schema("NOT_A_REAL_TYPE")


# ---- IntravChip residue must be gone --------------------------------------

REMOVED = [
    "ROOT", "MANIFEST", "OMERO_CSV", "METNET_ALL", "SAMPLETYPES_DB",
    "OOC_UID_MAP", "ASSAY_SHEETS", "CEL_REUSE", "SCIENTIST", "MS_PROTOCOL",
    "_TUMOR_PARENT_PATTERNS", "tumor_parent_for", "load_metnet_all",
    "metnet_cel_lookup", "metnet_ooc_vocab",
]


@pytest.mark.parametrize("name", REMOVED)
def test_project_specific_name_is_gone(name):
    assert not hasattr(_common, name), (
        f"_common.{name} is IntravChip-specific and belongs in project config"
    )


def test_no_person_name_in_source():
    src = (REPO / "scripts" / "_common.py").read_text()
    assert "Marie Floryan" not in src
    assert "MetNet All 260527.xlsx" not in src
    assert "HUVEC" not in src
    assert "MDA-MB-231" not in src


def test_no_module_level_file_reads():
    """A module-level Path().read_text() would re-introduce plugin anchoring."""
    src = (REPO / "scripts" / "_common.py").read_text()
    for i, line in enumerate(src.splitlines(), 1):
        if line.startswith((" ", "\t", "#", "@")) or not line.strip():
            continue
        assert "read_text()" not in line, f"module-level read at line {i}: {line}"
        assert "load_workbook(" not in line, f"module-level read at line {i}: {line}"


# ---- the writer still works ------------------------------------------------

def test_write_4sheet_xlsx_emits_four_sheets(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-190902KAM-1", "Name": "m1"}],
        assay_titles=["Tissue Collection"],
    )
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Instructions", "Samples", "Assay", "Ontology"]


def test_write_4sheet_xlsx_populates_ontology_when_given(tmp_path):
    """The dead capability at _common.py:194 — nothing has ever passed this."""
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-190902KAM-1", "Strain": "C57BL/6J"}],
        assay_titles=[],
        ontology={"Strain": ["C57BL/6J", "BALB/c"]},
    )
    wb = openpyxl.load_workbook(out)
    rows = list(wb["Ontology"].iter_rows(values_only=True))
    assert rows[0] == ("Field", "Value")
    assert ("Strain", "C57BL/6J") in rows
    assert ("Strain", "BALB/c") in rows


def test_ontology_fields_are_declared_controlled_in_instructions(tmp_path):
    """schema-mode spec: Instructions declares the type, Ontology carries values."""
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "T.xlsx"
    _common.write_4sheet_xlsx(
        out, "MUS",
        samples=[{"UID": "MUS-190902KAM-1", "Strain": "C57BL/6J"}],
        assay_titles=[],
        ontology={"Strain": ["C57BL/6J"]},
    )
    wb = openpyxl.load_workbook(out)
    rows = list(wb["Instructions"].iter_rows(values_only=True))
    assert rows[0] == ("Field", "Database Field", "Field Type", "Ontology")
    strain = [r for r in rows if r[0] == "Strain"][0]
    assert strain[1] == "MUS::Strain"
    assert strain[2] == "Controlled Ontology"
    assert strain[3] == "Strain"
    other = [r for r in rows if r[0] == "UID"][0]
    assert other[2] == "Text"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_common.py -v 2>&1 | tail -30`
Expected: FAILs on `test_placeholder_marker_shape`, `test_schema_column_order_*`, every `test_project_specific_name_is_gone`, `test_no_person_name_in_source`, and the two Instructions/Ontology tests.

- [ ] **Step 3: Rewrite `scripts/_common.py`**

Replace the file entirely:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
# scripts/_common.py
"""Shared helpers for dmac-curation build scripts.

This module is a LIBRARY. It holds nothing project-specific: no filenames, no
person names, no UID tables, no manuscript section titles. Everything that
varies per project lives in the project's lockfile and reaches scripts via
``scripts/_config.py`` (toolkit spec P2/P3).

Provides:
  - ``mint_uid(sample_type, lab, date, n)`` -> canonical ``<TYPE>-YYMMDD<LAB>-N``
  - ``placeholder(what)`` -> the greppable ``*** PLACEHOLDER: ... ***`` marker
  - ``sampletype_schema(sampletype, catalog=None)`` -> the catalog record
  - ``schema_column_order(schema, samples)`` -> UID, schema fields, then extras
  - ``write_4sheet_xlsx(...)`` -> the Instructions/Samples/Assay/Ontology writer
  - CSV and master-workbook readers, and a generic UID-map handoff

Per-project ``build_<arm>.py`` scripts generated by ``/curate-build`` import
from here via a ``sys.path`` insert of the plugin's ``scripts/`` directory.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook

# SKILL.md hard rule 8: unknown values get a greppable marker, never a blank.
PLACEHOLDER = "*** PLACEHOLDER:"


def placeholder(what: str) -> str:
    """Build the standard placeholder marker: ``*** PLACEHOLDER: <what> ***``."""
    return f"{PLACEHOLDER} {what} ***"


# ---------------------------------------------------------------------------
# UID minting
# ---------------------------------------------------------------------------
def mint_uid(sample_type: str, lab: str, date: str, n: int) -> str:
    """Canonical 4-arg UID minter: ``mint_uid('RNA', 'KAM', '190902', 1)``
    -> ``'RNA-190902KAM-1'``.

    This is the universal UID format documented in SKILL.md: ``<TYPE>-YYMMDD<LAB>-N``.

    Args:
      sample_type: SampleType abbreviation, e.g. ``'OOC'``, ``'D.SEQ'``.
      lab:         Lab code suffix, e.g. ``'KAM'``, ``'ENG'``.
      date:        6-digit YYMMDD string, e.g. ``'190902'``.
      n:           Integer counter (1-based).
    """
    return f"{sample_type}-{date}{lab}-{n}"


# ---------------------------------------------------------------------------
# Generic tabular loaders — all take explicit paths
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> list[dict]:
    """Read a manifest CSV; caller filters."""
    with Path(path).open() as f:
        return list(csv.DictReader(f))


def load_omero(path: Path) -> dict[str, dict]:
    """Map filename -> omero row dict from an omero_images.csv."""
    with Path(path).open() as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def load_master_workbook(path: Path) -> dict[str, list[dict]]:
    """Read a denormalized master xlsx into ``{sheet_name: [row dicts]}``.

    Build scripts use this to look up existing rows whose UID they cite as a
    Parent, and to sample real observed values before inventing a new term.
    SKILL.md hard rule 4: schema lies, workbook tells truth.
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        out: dict[str, list[dict]] = {}
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                out[sheet] = []
                continue
            headers = [h or f"_col{i}" for i, h in enumerate(rows[0])]
            out[sheet] = [
                {h: v for h, v in zip(headers, row) if v is not None}
                for row in rows[1:]
            ]
        return out
    finally:
        wb.close()


def master_lookup(master: dict[str, list[dict]], sheet: str, uid: str) -> dict | None:
    """Find a row by UID on one sheet of a loaded master workbook."""
    for r in master.get(sheet, []):
        if r.get("UID") == uid:
            return r
    return None


def master_vocab(master: dict[str, list[dict]], sheet: str,
                 fields: list[str]) -> dict[str, set[str]]:
    """Distinct observed values per field on one sheet — real values beat guesses."""
    vocab: dict[str, set[str]] = {f: set() for f in fields}
    for r in master.get(sheet, []):
        for f in fields:
            v = r.get(f)
            if v is not None and str(v).strip():
                vocab[f].add(str(v).strip())
    return vocab


# ---------------------------------------------------------------------------
# UID map (cross-script handoff within one project)
# ---------------------------------------------------------------------------
def save_uid_map(path: Path, mapping: dict[str, str]) -> None:
    """Persist a {natural key -> UID} map for a later build script to read."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True))


def load_uid_map(path: Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run the build script that produces it first."
        )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# SampleType catalog lookup
# ---------------------------------------------------------------------------
def sampletype_schema(sampletype: str, catalog: Path | None = None) -> dict:
    """Return the catalog record for a sample type.

    Args:
      sampletype: short code, e.g. ``'MUS'``.
      catalog:    explicit ``sampletypes_db.json``. Defaults to the plugin's
                  bundled read-only copy.
    """
    if catalog is None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _config import plugin_context
        catalog = plugin_context("sampletypes_db.json")
    db = json.loads(Path(catalog).read_text())
    for r in db:
        if r.get("SampleType") == sampletype:
            return r
    raise KeyError(f"SampleType {sampletype!r} not found in {catalog}")


def schema_column_order(schema: dict, samples: list[dict]) -> list[str]:
    """Column order for the Samples sheet: UID, then the catalog's declared
    fields in Required/Standard/Possible order, then any denormalized extras.

    This is the genuinely shared, schema-driven capability that survived the
    P3 de-projecting.
    """
    all_keys: list[str] = ["UID"]
    seen: set[str] = {"UID"}
    for src in ("Required Metadata", "Standard Metadata", "Possible Metadata Fields"):
        for k in (schema.get(src) or "").split(","):
            k = k.strip()
            if k and k not in seen:
                all_keys.append(k)
                seen.add(k)
    for s in samples:
        for k in s.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    return all_keys


# ---------------------------------------------------------------------------
# 4-sheet xlsx writer (Instructions / Samples / Assay / Ontology)
# ---------------------------------------------------------------------------
def write_4sheet_xlsx(
    out_path: Path,
    sampletype: str,
    samples: list[dict],
    assay_titles: list[str],
    ontology: dict[str, list[str]] | None = None,
    catalog: Path | None = None,
) -> None:
    """Emit the standard 4-sheet structure NExtSEEK auto-detects.

    Args:
      out_path:     target file (parents are created).
      sampletype:   SampleType abbreviation, e.g. ``'OOC'``.
      samples:      row dicts keyed by catalog field names (case-sensitive).
                    ``'UID'`` is required even if blank.
      assay_titles: assay title strings to register on the Assay sheet.
      ontology:     ``{fieldname: [allowed values]}`` for the Ontology sheet.
                    Fields appearing here are declared ``Controlled Ontology``
                    on the Instructions sheet; everything else is ``Text``.
                    Ontology validation is STRICT and exists ONLY in this
                    4-sheet format — the flat format has no Ontology sheet and
                    silently discards an ontology column.
      catalog:      explicit sampletypes_db.json; defaults to the plugin's.

    The Samples sheet uses one column per distinct field key across all rows,
    so missing fields produce empty cells, NOT ``'null'``/``'None'``.
    """
    schema = sampletype_schema(sampletype, catalog=catalog)
    all_keys = schema_column_order(schema, samples)
    ontology = ontology or {}

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # --- Instructions ------------------------------------------------------
    ws = wb.active
    ws.title = "Instructions"
    ws.append(["Field", "Database Field", "Field Type", "Ontology"])
    for k in all_keys:
        if k in ontology:
            ws.append([k, f"{sampletype}::{k}", "Controlled Ontology", k])
        else:
            ws.append([k, f"{sampletype}::{k}", "Text", ""])
    # --- Samples -----------------------------------------------------------
    ws = wb.create_sheet("Samples")
    ws.append(all_keys)
    for s in samples:
        ws.append([s.get(k, "") for k in all_keys])
    # --- Assay -------------------------------------------------------------
    ws = wb.create_sheet("Assay")
    ws.append(["SampleType", "AssayType", "Assay", "Direction"])
    for t in assay_titles:
        ws.append([sampletype, "", t, "child"])
    # --- Ontology ----------------------------------------------------------
    ws = wb.create_sheet("Ontology")
    ws.append(["Field", "Value"])
    for field_name, values in ontology.items():
        for v in values:
            ws.append([field_name, v])
    wb.save(out_path)
```

- [ ] **Step 4: Provide the per-project constants escape hatch**

Create `scripts/_project_constants.py.example`:

```python
"""Template for a project-local constants module.

Copy to your curation project as ``scripts/_project_constants.py`` and import
it from your generated ``build_<arm>.py``. This is where everything that used
to sit in the plugin's ``_common.py`` now lives — per project, in the project.

Nothing here ships with the plugin. That is the point: _common.py used to
carry one project's scientist name, master filename, cell-line UID table and
manuscript section titles, and every importer inherited them (toolkit spec P3).
"""

# The curator/scientist recorded on rows this project mints.
SCIENTIST = "Firstname Lastname"

# Existing UIDs this project's new rows cite as Parent, keyed by whatever
# natural identifier the PI's data uses.
PARENT_UID_REUSE = {
    # "HUVEC": "CEL-190901KAM-1",
}

# Manuscript section headers used verbatim as `Protocol` field values.
MS_PROTOCOL = {
    # "cell_culture": "Cell culture",
}

# Per-sampletype row counts you expect after consolidation. Also settable in
# the lockfile under modes.pipeline.expected_counts, which /curate-qa reads
# without needing this file.
EXPECTED_COUNTS = {
    # "OOC": 122,
}

# Sample types with no biological parent in this project's chain.
ALWAYS_ROOT = {"CEL", "MDL"}
```

- [ ] **Step 5: Remove `rename_files.py`'s hardcoded figure directories**

`scripts/rename_files.py:56` reads:

```python
FIGURE_DIRS = [f"Figure {n}" for n in range(1, 8)]
```

Replace with a flag-driven default. Add to every subparser that has `--root`:

```python
    parser.add_argument(
        "--figure-dirs", default="Figure 1..7",
        help="Figure directory names to walk, as 'Figure 1..7' or a comma list "
             "('Fig A,Fig B'). Default: Figure 1..7",
    )
```

and add the parser helper near the top:

```python
def parse_figure_dirs(spec: str) -> list[str]:
    """'Figure 1..7' -> ['Figure 1', ..., 'Figure 7']; else a comma list."""
    spec = (spec or "").strip()
    if ".." in spec:
        prefix, _, rng = spec.rpartition(" ")
        lo, _, hi = rng.partition("..")
        return [f"{prefix} {n}" for n in range(int(lo), int(hi) + 1)]
    return [s.strip() for s in spec.split(",") if s.strip()]
```

Replace every use of the `FIGURE_DIRS` global with `parse_figure_dirs(args.figure_dirs)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with pytest --with openpyxl pytest tests/test_common.py -v`
Expected: all pass.

- [ ] **Step 7: Run the full suite**

Run: `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v 2>&1 | tail -30`
Expected: green except the one known `--retrieve` drift row.

- [ ] **Step 8: Commit**

```bash
git add scripts/_common.py scripts/_project_constants.py.example \
        scripts/rename_files.py tests/test_common.py
git commit -m "refactor(_common): make it a library, not IntravChip's constants (P3)

_common.py carried SCIENTIST = 'Marie Floryan', a hardcoded master filename,
a HUVEC/MCF-7 UID table, IntravChip manuscript section titles and a table of
device-id regexes. Every importer inherited all of it. Removed; per-project
values move to the lockfile (via _config) or scripts/_project_constants.py,
templated as .example.

Surviving shared API: mint_uid, placeholder, sampletype_schema,
schema_column_order, write_4sheet_xlsx, and generic tabular loaders that take
explicit paths.

write_4sheet_xlsx now declares ontology-bearing fields as 'Controlled
Ontology' on the Instructions sheet, which is what makes the Ontology sheet
actually enforce anything. No caller has ever passed ontology= (the dead
capability at the old L194); schema mode is the first.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage C — Mode architecture

### Task 10: Lockfile schema v1 with v0 migration

**Files:**
- Create: `scripts/_lockfile.py`
- Modify: `scripts/_config.py` (`_read_lockfile_pipeline` delegates here)
- Test: `tests/test_lockfile.py`

**Interfaces:**
- Consumes: `_config.LOCKFILE_NAME` from Task 7
- Produces: `SCHEMA_VERSION = 1`; `PLUGIN_VERSION = "0.3.0"`; `read(root) -> dict` (always v1-shaped, migrates v0 in memory); `migrate_v0(raw) -> dict`; `write(root, data) -> Path`; `mode(data, name) -> dict`; `set_mode(root, name, values) -> dict`; `LockfileError`

**Context (toolkit spec §3):** `.dmac-curation.json` is flat and single-mode, its schema exists only in prose in two places that already disagree (`curate-init.md:46-59` hardcodes `plugin_version: "0.1.0"` while `plugin.json` says `0.2.0`), and it has no `schema_version`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lockfile.py`:

```python
"""Lockfile schema v1 and v0 -> v1 migration (toolkit spec section 3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

V0 = {
    "plugin_name": "dmac-curation",
    "plugin_sha": "abc123",
    "plugin_version": "0.1.0",
    "schema_vintage": "2026-05-27",
    "init_date": "2026-05-27",
    "init_user": "cdemu",
    "lab": "KAM",
    "pi": "marie",
    "nextseek_project_id": 42,
}


def test_schema_version_is_1():
    assert _lockfile.SCHEMA_VERSION == 1


def test_plugin_version_matches_plugin_json():
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert _lockfile.PLUGIN_VERSION == manifest["version"]


def test_migrate_v0_moves_flat_keys_into_modes_pipeline():
    out = _lockfile.migrate_v0(V0)
    assert out["schema_version"] == 1
    assert out["modes"]["pipeline"]["lab"] == "KAM"
    assert out["modes"]["pipeline"]["pi"] == "marie"
    assert out["modes"]["pipeline"]["nextseek_project_id"] == 42


def test_migrate_v0_keeps_plugin_level_keys_at_top():
    out = _lockfile.migrate_v0(V0)
    assert out["plugin_name"] == "dmac-curation"
    assert out["plugin_sha"] == "abc123"
    assert out["schema_vintage"] == "2026-05-27"
    assert "lab" not in out


def test_migrate_v0_bumps_plugin_version():
    assert _lockfile.migrate_v0(V0)["plugin_version"] == _lockfile.PLUGIN_VERSION


def test_migrate_is_idempotent():
    once = _lockfile.migrate_v0(V0)
    assert _lockfile.migrate_v0(once) == once


def test_read_migrates_a_v0_file_on_disk(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(V0))
    data = _lockfile.read(tmp_path)
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "KAM"


def test_read_does_not_rewrite_the_file(tmp_path):
    """Migration is in-memory. Only an explicit write() touches disk."""
    p = tmp_path / ".dmac-curation.json"
    p.write_text(json.dumps(V0))
    before = p.read_text()
    _lockfile.read(tmp_path)
    assert p.read_text() == before


def test_read_returns_empty_v1_when_absent(tmp_path):
    assert _lockfile.read(tmp_path) == {
        "schema_version": 1,
        "plugin_version": _lockfile.PLUGIN_VERSION,
        "modes": {},
    }


def test_read_raises_on_malformed_json(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text("{ not json")
    with pytest.raises(_lockfile.LockfileError):
        _lockfile.read(tmp_path)


def test_read_raises_on_future_schema_version(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(
        json.dumps({"schema_version": 99, "modes": {}}))
    with pytest.raises(_lockfile.LockfileError) as exc:
        _lockfile.read(tmp_path)
    assert "99" in str(exc.value)


def test_mode_returns_empty_dict_for_absent_mode(tmp_path):
    assert _lockfile.mode(_lockfile.read(tmp_path), "schema") == {}


def test_set_mode_creates_and_persists(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6, "lab": "ENG"})
    on_disk = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert on_disk["schema_version"] == 1
    assert on_disk["modes"]["pipeline"] == {"phase": 6, "lab": "ENG"}


def test_set_mode_merges_rather_than_replaces(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"lab": "ENG", "phase": 1})
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6})
    assert _lockfile.read(tmp_path)["modes"]["pipeline"] == {"lab": "ENG", "phase": 6}


def test_set_mode_leaves_other_modes_alone(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"phase": 6})
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = _lockfile.read(tmp_path)
    assert data["modes"]["pipeline"] == {"phase": 6}
    assert data["modes"]["report"] == {"last_format": "GEO"}


def test_set_mode_upgrades_a_v0_file_in_place(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps(V0))
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "KAM"
    assert data["modes"]["report"]["last_format"] == "GEO"


def test_write_ends_with_a_newline(tmp_path):
    _lockfile.write(tmp_path, {"schema_version": 1, "modes": {"b": {}, "a": {}}})
    assert (tmp_path / ".dmac-curation.json").read_text().endswith("\n")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_lockfile.py -v`
Expected: collection error, `ModuleNotFoundError: No module named '_lockfile'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/_lockfile.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read, migrate and write ``.dmac-curation.json`` (toolkit spec section 3).

The v0 lockfile was flat and single-mode: ``lab``, ``pi`` and
``nextseek_project_id`` sat at the top level next to plugin identity keys, with
no ``schema_version`` to hang a migration off. Its shape existed only in prose,
in two places that disagreed (curate-init.md hardcoded plugin_version 0.1.0
while plugin.json said 0.2.0).

v1 nests per-mode settings under ``modes``:

    {"schema_version": 1,
     "plugin_version": "0.3.0",
     "plugin_name": ..., "plugin_sha": ..., "schema_vintage": ...,
     "modes": {"pipeline": {"phase": 6, "lab": "KAM", ...}}}

Modes that need no project never read this file. ``schema`` mode must work from
any cwd; ``report`` mode reads it opportunistically but must not require it.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_VERSION = 1
PLUGIN_VERSION = "0.3.0"
LOCKFILE_NAME = ".dmac-curation.json"

# Keys describing the PLUGIN, not a mode. Everything else in a v0 lockfile was
# pipeline-mode state.
_PLUGIN_LEVEL_KEYS = {
    "plugin_name", "plugin_sha", "plugin_version", "schema_vintage",
    "init_date", "init_user", "schema_version", "modes",
}


class LockfileError(Exception):
    """Malformed lockfile, or one written by a newer plugin."""


def path_for(root: Path) -> Path:
    return Path(root) / LOCKFILE_NAME


def empty() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "modes": {}}


def migrate_v0(raw: dict) -> dict:
    """Map a flat v0 lockfile into v1. Idempotent on an already-v1 dict."""
    if raw.get("schema_version") == SCHEMA_VERSION:
        out = dict(raw)
        out.setdefault("modes", {})
        out["plugin_version"] = PLUGIN_VERSION
        return out

    out: dict = {"schema_version": SCHEMA_VERSION, "plugin_version": PLUGIN_VERSION}
    pipeline: dict = {}
    for key, value in raw.items():
        if key == "plugin_version":
            continue  # always bumped to the running plugin's version
        if key in _PLUGIN_LEVEL_KEYS:
            out[key] = value
        else:
            pipeline[key] = value
    out["modes"] = {"pipeline": pipeline} if pipeline else {}
    return out


def read(root: Path) -> dict:
    """Return the lockfile as v1. Migration is IN MEMORY; disk is untouched.

    Returns an empty v1 document when no lockfile exists, so callers that treat
    the project as optional need no existence check.
    """
    p = path_for(root)
    if not p.is_file():
        return empty()
    try:
        raw = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LockfileError(f"{p} is not readable JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise LockfileError(f"{p} does not contain a JSON object")
    version = raw.get("schema_version")
    if version is not None and version > SCHEMA_VERSION:
        raise LockfileError(
            f"{p} has schema_version {version}, but this plugin understands only "
            f"up to {SCHEMA_VERSION}. Upgrade dmac-curation."
        )
    return migrate_v0(raw)


def write(root: Path, data: dict) -> Path:
    """Persist a v1 document. Sorts modes for a stable diff."""
    p = path_for(root)
    out = dict(data)
    out["schema_version"] = SCHEMA_VERSION
    out["plugin_version"] = PLUGIN_VERSION
    modes = out.get("modes", {})
    out["modes"] = {k: modes[k] for k in sorted(modes)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n")
    return p


def mode(data: dict, name: str) -> dict:
    """A mode's settings from an already-read document; ``{}`` when absent."""
    return dict(data.get("modes", {}).get(name, {}))


def set_mode(root: Path, name: str, values: dict) -> dict:
    """Merge ``values`` into one mode's section and persist. Returns the doc.

    Merging, not replacing: ``/curate-resolve-assays`` recording a project id
    must not erase the phase ``/curate-status`` reads.
    """
    data = read(root)
    modes = data.setdefault("modes", {})
    section = dict(modes.get(name, {}))
    section.update(values)
    modes[name] = section
    write(root, data)
    return data
```

- [ ] **Step 4: Point `_config` at it so there is one migration implementation**

In `scripts/_config.py`, replace the body of `_read_lockfile_pipeline`:

```python
def _read_lockfile_pipeline(root: Path) -> dict:
    """Pipeline-mode settings from a v0 or v1 lockfile. Never raises."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _lockfile import LockfileError, mode, read
    try:
        return mode(read(root), "pipeline")
    except LockfileError:
        return {}
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest pytest tests/test_lockfile.py tests/test_config.py -v`
Expected: all pass **except** `test_plugin_version_matches_plugin_json`, which stays RED until Task 11 bumps `plugin.json` to `0.3.0`. Note it and continue.

- [ ] **Step 6: Commit**

```bash
git add scripts/_lockfile.py scripts/_config.py tests/test_lockfile.py
git commit -m "feat(lockfile): schema v1 with modes{} and in-memory v0 migration

v0 was flat and single-mode with no schema_version. v1 nests per-mode settings
under modes{}, so schema and report can record state without colliding with
pipeline's. read() migrates v0 in memory and never rewrites the file; only
set_mode()/write() touch disk. set_mode merges, so recording a project id
cannot erase the phase.

test_plugin_version_matches_plugin_json stays RED until Task 11.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Identity prose — three strings that must stay in sync

**Files:**
- Modify: `.claude-plugin/plugin.json:3-4,13`
- Modify: `.claude-plugin/marketplace.json:14-15,23`
- Modify: `skills/curation/SKILL.md:3`
- Test: `tests/test_identity_sync.py`

**Interfaces:**
- Consumes: `_lockfile.PLUGIN_VERSION` from Task 10
- Produces: one canonical description string, asserted identical in all three files

**Context (toolkit spec §1):** the activation description is what the model matches on, so non-pipeline modes are invisible to skill activation until it changes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_identity_sync.py`:

```python
"""The identity string and version live in three files. Keep them equal.

Toolkit spec section 1: the description is what skill activation matches on,
so a pipeline-only description makes schema and report modes invisible.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

CANONICAL_DESCRIPTION = (
    "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, "
    "PI-facing. Modes: pipeline (13 commands, 11 phases: inventory to sample tree "
    "to build to consolidate to QA to deposit to retrieve to email PI), fdh "
    "(FairDomHub upload and direct API), schema (sample type authoring and "
    "controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts). "
    "Activate when working in a directory containing files/, manuscript/, "
    "previous_metadata/, or any .dmac-curation.json lockfile, or when the user "
    "mentions NExtSEEK, FairDomHub, curation, sample types, or a GEO/SRA/PRIDE "
    "submission."
)


def _plugin_json():
    return json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())


def _marketplace_entry():
    doc = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in doc["plugins"] if p["name"] == "dmac-curation"]
    assert entries, "dmac-curation not listed in marketplace.json"
    return entries[0]


def _skill_frontmatter():
    text = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert text.startswith("---"), "SKILL.md has no frontmatter"
    block = text.split("---")[1]
    out, key = {}, None
    for line in block.splitlines():
        if line.startswith(("name:", "description:")):
            key, _, value = line.partition(":")
            key = key.strip()
            out[key] = value.strip()
        elif key and line.startswith((" ", "\t")):
            out[key] += " " + line.strip()
    return out


def test_plugin_json_description_is_canonical():
    assert _plugin_json()["description"] == CANONICAL_DESCRIPTION


def test_marketplace_description_is_canonical():
    assert _marketplace_entry()["description"] == CANONICAL_DESCRIPTION


def test_skill_description_is_canonical():
    assert _skill_frontmatter()["description"] == CANONICAL_DESCRIPTION


def test_versions_agree_across_plugin_marketplace_and_lockfile():
    v = _plugin_json()["version"]
    assert _marketplace_entry()["version"] == v
    assert _lockfile.PLUGIN_VERSION == v


def test_version_is_the_toolkit_release():
    assert _plugin_json()["version"] == "0.3.0"


def test_description_names_every_mode():
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in CANONICAL_DESCRIPTION, f"{mode} missing from description"


def test_description_does_not_claim_thirteen_phases():
    """Phases 4 and 8 are deleted in Task 16; 13 commands drive 11 phases."""
    assert "13-phase" not in CANONICAL_DESCRIPTION


def test_curate_init_does_not_hardcode_a_stale_version():
    """curate-init.md:46-59 hardcoded 0.1.0 while plugin.json said 0.2.0."""
    doc = (REPO / "commands" / "curate-init.md").read_text()
    for stale in ('"plugin_version": "0.1.0"', '"plugin_version": "0.2.0"',
                  '"plugin_version": "0.3.0"'):
        assert stale not in doc, f"init must read the version, not restate {stale}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_identity_sync.py -v`
Expected: FAILs on all three description assertions, on `test_version_is_the_toolkit_release`, and on `test_curate_init_does_not_hardcode_a_stale_version`.

- [ ] **Step 3: Update `.claude-plugin/plugin.json`**

Replace lines 3-4 with the version bump and the canonical string (a single JSON line):

```json
  "version": "0.3.0",
  "description": "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes: pipeline (13 commands, 11 phases: inventory to sample tree to build to consolidate to QA to deposit to retrieve to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts). Activate when working in a directory containing files/, manuscript/, previous_metadata/, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, or a GEO/SRA/PRIDE submission.",
```

Replace line 13's keywords with:

```json
  "keywords": ["nextseek", "fairdomhub", "metadata-curation", "geo", "sra", "pride", "ontology", "mit", "dmac", "claude-code-plugin"]
```

- [ ] **Step 4: Update `.claude-plugin/marketplace.json`**

Set the `dmac-curation` entry's `description` to the identical string, `"version": "0.3.0"`, and mirror the keywords list.

- [ ] **Step 5: Update `skills/curation/SKILL.md` frontmatter**

Replace line 3 with `description: ` followed by the identical string on one line.

- [ ] **Step 6: Run the tests**

Run: `uv run --with pytest pytest tests/test_identity_sync.py tests/test_lockfile.py -v`
Expected: `test_plugin_version_matches_plugin_json` now PASSES. `test_curate_init_does_not_hardcode_a_stale_version` still FAILS — Task 13 rewrites that command. Everything else passes.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json \
        skills/curation/SKILL.md tests/test_identity_sync.py
git commit -m "feat(identity): reframe as the curator's workbench, bump to 0.3.0

The activation description is what skill matching runs against, so a
pipeline-only description made schema and report modes invisible. One
canonical string now names all four modes, asserted identical in plugin.json,
marketplace.json and SKILL.md frontmatter. Version unified at 0.3.0 across all
three plus _lockfile.PLUGIN_VERSION.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Phase table becomes a mode table

**Files:**
- Modify: `skills/curation/SKILL.md:6-46` and the vocabulary section
- Modify: `skills/curation/PHASES.md` (receives the phase table)
- Create: `skills/curation/SCHEMA.md` (stub; Task 23 fills it)
- Create: `skills/curation/REPORTS.md` (stub; Task 34 fills it)
- Test: `tests/test_mode_table.py`

**Interfaces:**
- Consumes: nothing
- Produces: a `## Modes` table in `SKILL.md` with one row per reference doc in `skills/curation/*.md` **excluding `SKILL.md` itself**

**Context (toolkit spec §2, O4):** the naive test "assert the mode table lists exactly the `skills/curation/*.md` reference docs present" would glob `SKILL.md`. Exclude it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mode_table.py`:

```python
"""SKILL.md's mode table must match the reference docs actually present.

Toolkit spec O4: the naive version of this test globs SKILL.md itself.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CURATION = REPO / "skills" / "curation"
SKILL = CURATION / "SKILL.md"

EXPECTED_MODES = {
    "pipeline": "PHASES.md",
    "fdh": "FDH.md",
    "schema": "SCHEMA.md",
    "report": "REPORTS.md",
}


def reference_docs() -> set[str]:
    return {p.name for p in CURATION.glob("*.md") if p.name != "SKILL.md"}


def mode_table_rows() -> dict[str, dict[str, str]]:
    """Parse the '## Modes' markdown table into {mode: {column: value}}."""
    parts = SKILL.read_text().split("## Modes", 1)
    assert len(parts) == 2, "SKILL.md has no '## Modes' section"
    body = parts[1].split("\n##", 1)[0]
    rows = [l for l in body.splitlines() if l.strip().startswith("|")]
    assert len(rows) >= 3, "mode table needs a header, a separator and rows"
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    out = {}
    for line in rows[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        record = dict(zip(header, cells))
        out[record["mode"].strip("`")] = record
    return out


def test_every_reference_doc_exists():
    assert not set(EXPECTED_MODES.values()) - reference_docs()


def test_mode_table_lists_exactly_the_reference_docs():
    listed = {r["reference"].strip("`") for r in mode_table_rows().values()}
    assert listed == reference_docs(), (
        f"mode table lists {listed}, but skills/curation/ has {reference_docs()} "
        f"(excluding SKILL.md)"
    )


def test_mode_table_has_the_four_modes():
    assert set(mode_table_rows()) == set(EXPECTED_MODES)


@pytest.mark.parametrize("mode,doc", sorted(EXPECTED_MODES.items()))
def test_each_mode_points_at_its_doc(mode, doc):
    assert mode_table_rows()[mode]["reference"].strip("`") == doc


def test_mode_table_declares_state_scope():
    rows = mode_table_rows()
    assert "project" in rows["pipeline"]["state scope"]
    assert "cwd" in rows["schema"]["state scope"]
    assert "input" in rows["report"]["state scope"]


def test_skill_md_no_longer_carries_the_phase_table():
    text = SKILL.read_text()
    assert "| 0 | Init |" not in text, "the phase table belongs in PHASES.md now"
    assert "13-phase pipeline" not in text


def test_phases_md_carries_the_phase_table():
    assert "| 0 | Init |" in (CURATION / "PHASES.md").read_text()


def test_phase_table_omits_deleted_phases():
    """Phases 4 and 8 are retired as numbers in Task 16."""
    text = (CURATION / "PHASES.md").read_text()
    table = text.split("## Phase table", 1)[1].split("\n---", 1)[0]
    rows = [l for l in table.splitlines() if l.strip().startswith("|")]
    numbers = []
    for line in rows[2:]:
        first = line.strip("|").split("|")[0].strip()
        if first.isdigit():
            numbers.append(int(first))
    assert 4 not in numbers, "Phase 4 (task plan) is retired"
    assert 8 not in numbers, "Phase 8 (synonyms) is folded into Phase 7"
    assert len(numbers) == 11, f"expected 11 phases, got {len(numbers)}: {numbers}"


def test_fdh_is_no_longer_disclaimed_as_not_part_of_the_pipeline():
    """FDH was bolted on with a disclaimer because the pipeline was the only
    organising principle. It is a mode now."""
    assert "NOT part of the 13-phase pipeline" not in SKILL.read_text()


def test_vocabulary_section_covers_the_new_modes():
    text = SKILL.read_text()
    for phrase in ("bolster", "sample type", "GEO", "SRA", "PRIDE"):
        assert phrase in text, f"vocabulary section should mention {phrase!r}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_mode_table.py -v`
Expected: FAILs on `test_every_reference_doc_exists` (no SCHEMA.md / REPORTS.md), on the parser assertion for a missing `## Modes` section, and on the phase-table assertions.

- [ ] **Step 3: Create the two reference-doc stubs**

Create `skills/curation/SCHEMA.md`:

```markdown
# `schema` mode — sample type authoring

Deep reference for the `schema` mode. Load on demand.

**Status: stub.** Filled by Task 23 of
`docs/superpowers/plans/2026-07-21-curation-toolkit.md`.
Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

Purpose: answer "what are we collecting?" for a NExtSEEK sample type. Produces
a proposed sample type record, a controlled vocabulary, and a rationale
document a human reviews and applies by hand. Never writes to NExtSEEK, never
edits `sampletypes_db.json`.

State scope: **cwd**. Reads the plugin's `context/` read-only; writes every
artifact into the current working directory. No lockfile, no scaffold.
```

Create `skills/curation/REPORTS.md`:

```markdown
# `report` mode — submission artifact generation

Deep reference for the `report` mode. Load on demand.

**Status: stub.** Filled by Task 34 of
`docs/superpowers/plans/2026-07-21-curation-toolkit.md`.
Design: `docs/superpowers/specs/2026-07-21-report-mode-design.md`.

Purpose: "I have file X.xlsx with metadata, turn it into a GEO report."
Produces GEO / SRA / PRIDE submission artifacts from whatever metadata the
curator has. The LLM emits a declarative mapping spec once; execution across
all rows is deterministic.

State scope: **input**. Reads a project lockfile when present, for lab and
project id, but must run without one from any cwd.
```

- [ ] **Step 4: Rewrite `SKILL.md` lines 6-46**

Replace everything from `# DMAC Curation` through the end of the FDH stanza with:

```markdown
# DMAC Curation

You are the curator's workbench for MIT DMAC: turning a PI's research-project
data into NExtSEEK-ready metadata, FairDomHub deposits, sample type
definitions, and repository submission artifacts. Human-in-the-loop and
PI-facing throughout.

## When this skill activates

- Current working directory contains `.dmac-curation.json` (the project lockfile)
- Or cwd contains the curation input layout: `files/`, `manuscript/`, `previous_metadata/`
- Or the user invokes any `/curate-*` or `/fdh-*` slash command
- Or the user mentions NExtSEEK / FairDomHub / FDH / "curate metadata" /
  a sample type / a GEO, SRA or PRIDE submission

## Modes

The plugin is organised as **modes**, not as one sequence. A mode is a
convention, not a framework: entry-point commands, a reference doc loaded on
demand, and optionally its own scripts. Adding a file is registering it; there
is nothing to declare in `plugin.json`.

| mode | entry points | reference | state scope |
|---|---|---|---|
| `pipeline` | `/curate-init`, `/curate-inventory`, `/curate-sample-tree`, `/curate-questions`, `/curate-build`, `/curate-consolidate`, `/curate-resolve-assays`, `/curate-qa`, `/curate-deposit`, `/curate-retrieve`, `/curate-validate`, `/curate-email`, `/curate-status` | `PHASES.md` | project - needs a lockfile and scaffold |
| `fdh` | `/fdh-upload`, `/fdh-api` | `FDH.md` | credentials only - no project needed |
| `schema` | `/curate-sampletype` | `SCHEMA.md` | cwd - writes where you are, no project needed |
| `report` | `/curate-report` | `REPORTS.md` | input - reads a lockfile if present, never requires one |

Load a mode's reference doc when you enter that mode, not before. For each
command's exact behavior, the `commands/*.md` files are authoritative.
`/curate-status` reports per mode.

### `pipeline` - the curation pipeline

11 phases driven by 13 commands. This is where most work happens, but it is one
mode among four. Deep per-phase reference: `PHASES.md`.

### `fdh` - FairDomHub

- **Upload a study** -> `/fdh-upload` drives the interactive `scripts/fdh/submit.py`.
- **Programmatic API access** ("find / delete / patch ... on FDH") -> `/fdh-api`
  runs a reuse-or-generate loop over `scripts/fdh/fdh_api.py` +
  `context/fdh_api_index.json`.

Auth: `FDH_API` in the project's `.env` or the environment. Reference: `FDH.md`.

### `schema` - sample type authoring

"Help me bolster D.VIA." Produces a proposed sample type record, a controlled
vocabulary, and a rationale document. A human applies it; the mode never writes
to NExtSEEK. Reference: `SCHEMA.md`.

### `report` - submission artifacts

"I have file X.xlsx with metadata, turn it into a GEO report." Produces GEO, SRA
and PRIDE artifacts from UIDs, a NExtSEEK workbook, a curated upload sheet, or
arbitrary tabular data. Reference: `REPORTS.md`.
```

- [ ] **Step 5: Extend the vocabulary section**

Append to `## Vocabulary the user uses`:

```markdown
- "bolster X" / "what should we collect for X" / "define a sample type" → `schema` mode (`/curate-sampletype`)
- "turn this into a GEO submission" / "build the SRA sheet" / "PRIDE report" → `report` mode (`/curate-report`)
- "the mapping" → `report` mode's `<FORMAT>.mapping.json`, the reviewable spec the LLM writes once
- "what mode am I in" → `/curate-status`
```

- [ ] **Step 6: Move the phase table into `PHASES.md`**

Insert after `PHASES.md` line 5:

```markdown
## Phase table

13 commands drive 11 phases. Phases 4 and 8 were retired as numbers (see
"Retired phases"); the surviving numbers are deliberately **not** renumbered,
because every scaffolded project's `CLAUDE.md` bakes in the order,
`/curate-status` maps artifacts by number, and curators speak in phase numbers.

| # | Phase | Command | Artifact |
|---|---|---|---|
| 0 | Init | `/curate-init [--lab CODE] [--pi NAME] [--mode NAME]` | scaffold cwd + `.dmac-curation.json` lockfile |
| 1 | Inventory | `/curate-inventory` | `FILE_INDEX.md` |
| 2 | Sample tree | `/curate-sample-tree` | `SAMPLE_TREE.md` |
| 3 | Questions | `/curate-questions [add\|list\|resolve]` | `QUESTIONS_FOR_PI.md` |
| 5 | Build | `/curate-build [<arm>]` | `assay_sheets/4sheet_originals/*.xlsx` + `scripts/build_<arm>.py` |
| 6 | Consolidate | `/curate-consolidate` | `assay_sheets/Arm{X}.xlsx` (flat format) |
| 7 | Resolve assays | `/curate-resolve-assays --project-id N` | `context/assay_ids_cache.json` + `context/assay_synonyms.json` |
| 9 | QA | `/curate-qa` | console disposition report |
| 10 | Deposit | `/curate-deposit <geo\|zenodo\|omero>` | external uploads + `Link_PrimaryData` backfilled |
| 11 | Retrieve | `/curate-retrieve` | `RETRIEVE.TXT` |
| 12 | Validate | `/curate-validate <metadata.xlsx>` | console diff report |
| 13 | Email | `/curate-email` | `EMAIL_TO_PI.md` |

### Retired phases

**Phase 4 (task plan)** had no command, no script and no artifact; it existed
only as TaskList state. Using a task list is good practice, not a pipeline
stage. Its guidance is folded into Phase 3's tail.

**Phase 8 (synonyms)** was always the same command and invocation as Phase 7.
It existed in the table only because `assay_synonyms.json` is a second
artifact, and artifacts are not phases. It is documented as a Phase 7 output.

Neither number is reused.
```

- [ ] **Step 7: Run the tests**

Run: `uv run --with pytest pytest tests/test_mode_table.py -v`
Expected: all pass.

- [ ] **Step 8: Confirm the FDH doc tests still pass**

Run: `uv run --with pytest pytest tests/test_fdh_reference_docs.py tests/test_fdh_commands_present.py -v`
Expected: pass. If `test_fdh_reference_docs.py` asserted on the removed "NOT part of the 13-phase pipeline" stanza, change that assertion to look for the `### \`fdh\` - FairDomHub` heading instead.

- [ ] **Step 9: Commit**

```bash
git add skills/curation/ tests/test_mode_table.py
git commit -m "feat(skill): mode table replaces the phase table

SKILL.md's identity was a sequence, so FDH had to be bolted on with a 'NOT part
of the 13-phase pipeline' disclaimer and schema/report had nowhere to live.
SKILL.md now carries a four-row mode table; the phase table moves to PHASES.md,
which is already the pipeline's deep reference, and drops the retired 4 and 8.

SCHEMA.md and REPORTS.md land as stubs so the mode table matches the reference
docs on disk (spec O4: exclude SKILL.md from that glob).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: `/curate-init` becomes additive

**Files:**
- Modify: `commands/curate-init.md` (whole file)
- Modify: `skills/curation/PHASES.md` Phase 0 section
- Test: `tests/test_init_additive.py`

**Interfaces:**
- Consumes: `_lockfile.read`, `_lockfile.set_mode`, `_lockfile.PLUGIN_VERSION` from Task 10
- Produces: a `/curate-init` that creates only what is missing and merges a mode section into an existing lockfile

**Context (toolkit spec §3):** `curate-init.md:11-16` currently **refuses to run** if `CLAUDE.md` or `.dmac-curation.json` exist, so there is no "add a mode to an existing project" path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_init_additive.py`:

```python
"""/curate-init must be additive, not all-or-nothing (toolkit spec section 3).

The command is markdown, so these assert on the CONTRACT it describes plus the
lockfile behaviour it delegates to _lockfile.py.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _lockfile  # noqa: E402

INIT = REPO / "commands" / "curate-init.md"


def test_init_no_longer_refuses_on_existing_lockfile():
    text = INIT.read_text()
    assert "must NOT already exist" not in text
    assert "abort unless user adds `--force`" not in text


def test_init_documents_the_additive_contract():
    text = INIT.read_text()
    for phrase in ("Create what is missing", "never overwrite", "--mode"):
        assert phrase in text, f"curate-init.md must document {phrase!r}"


def test_init_does_not_restate_the_plugin_version():
    text = INIT.read_text()
    for stale in ('"plugin_version": "0.1.0"', '"plugin_version": "0.2.0"',
                  '"plugin_version": "0.3.0"'):
        assert stale not in text
    assert "_lockfile.py" in text, "init must delegate lockfile writing"


def test_init_writes_a_v1_lockfile_shape():
    text = INIT.read_text()
    assert '"schema_version": 1' in text
    assert '"modes"' in text


def test_adding_a_mode_preserves_the_existing_one(tmp_path):
    _lockfile.set_mode(tmp_path, "pipeline", {"lab": "KAM", "phase": 6})
    _lockfile.set_mode(tmp_path, "report", {"last_format": "GEO"})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["modes"]["pipeline"] == {"lab": "KAM", "phase": 6}
    assert data["modes"]["report"] == {"last_format": "GEO"}


def test_init_on_a_v0_project_upgrades_without_data_loss(tmp_path):
    (tmp_path / ".dmac-curation.json").write_text(json.dumps({
        "plugin_name": "dmac-curation", "plugin_version": "0.1.0",
        "lab": "ENG", "pi": "lee", "nextseek_project_id": 7,
    }))
    _lockfile.set_mode(tmp_path, "schema", {})
    data = json.loads((tmp_path / ".dmac-curation.json").read_text())
    assert data["schema_version"] == 1
    assert data["modes"]["pipeline"]["lab"] == "ENG"
    assert data["modes"]["pipeline"]["nextseek_project_id"] == 7
    assert "schema" in data["modes"]


def test_phases_md_phase0_describes_additive_init():
    text = (REPO / "skills" / "curation" / "PHASES.md").read_text()
    phase0 = text.split("## Phase 0", 1)[1].split("\n## ", 1)[0]
    assert "Verify cwd is empty" not in phase0
    assert "additive" in phase0.lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_init_additive.py -v`
Expected: FAILs on the `curate-init.md` contract assertions and on `test_phases_md_phase0_describes_additive_init`. The two `_lockfile` behaviour tests already PASS.

- [ ] **Step 3: Rewrite `commands/curate-init.md`**

Replace the whole file:

```markdown
---
description: Scaffold or extend a dmac-curation project (Phase 0)
---

The user wants to scaffold a new curation project in the current working
directory, or add a mode to an existing one.

Parse from `$ARGUMENTS`:
- `--lab <CODE>` (e.g. `KAM`, `ENG`, `WHI`, `GRI`)
- `--pi <NAME>` (e.g. `marie`, `lee`, `yufei`)
- `--mode <NAME>` (default `pipeline`; one of `pipeline`, `report`, `schema`)

`--lab` and `--pi` are required for `pipeline` mode only. If missing there, use
`AskUserQuestion` - do NOT guess. `schema` and `report` modes need neither.

## Additive contract

**Create what is missing; never overwrite what exists.** There is no
all-or-nothing prerequisite check and no `--force`. Adding a mode to an existing
project is a first-class path, not an error.

| condition | action |
|---|---|
| file absent | create it |
| file present, this run would produce identical content | leave it, report "unchanged" |
| file present, content would differ | leave it, report "exists - not modified", print a diff summary |

The one exception is the lockfile, which is *merged*, never replaced. Use
`scripts/_lockfile.py` for that; never hand-write the JSON.

## Steps

1. Resolve the plugin path from `$PLUGIN_PATH`, or from this command file's
   grandparent (`<plugin>/commands/curate-init.md` -> `<plugin>/`).

2. Read the plugin's git SHA: `git -C <PLUGIN_PATH> rev-parse HEAD`. If the
   plugin has no `.git` (installed as a tarball), record `null` and warn.

3. Read the schema vintage: `<PLUGIN_PATH>/context/VINTAGE.json` -> `bundled_date`.

4. Create only the missing directories:
   `mkdir -p files manuscript previous_metadata assay_sheets scripts`.
   Skip this entirely for `schema` and `report` modes; they need no scaffold.

5. Render any missing templates. Existing files are never touched:

   ```bash
   uv run --with jinja2 python3 <<'PY'
   from jinja2 import Environment, FileSystemLoader, StrictUndefined
   import datetime, os, pathlib
   plugin = os.environ.get("PLUGIN_PATH", "<PATH>")
   env = Environment(loader=FileSystemLoader(plugin + "/templates"),
                     undefined=StrictUndefined)
   ctx = {"lab": "$LAB", "pi_name": "$PI",
          "init_date": datetime.date.today().isoformat(),
          "modes": ["$MODE"]}
   for tpl, dest in [("CLAUDE.md.j2", "CLAUDE.md"),
                     ("env.example.j2", ".env.example"),
                     ("gitignore.j2", ".gitignore"),
                     ("pyproject.toml.j2", "pyproject.toml")]:
       if pathlib.Path(dest).exists():
           print(f"  exists - not modified: {dest}")
           continue
       extra = {}
       if tpl == "pyproject.toml.j2":
           extra["project_slug"] = f"{ctx['pi_name']}_curation"
       pathlib.Path(dest).write_text(env.get_template(tpl).render(**ctx, **extra))
       print(f"  created: {dest}")
   PY
   ```

6. Merge the mode into the lockfile. **Do not hand-write this JSON** - the
   schema version and plugin version come from `scripts/_lockfile.py`, which is
   the single source of truth and migrates a v0 lockfile in place:

   ```bash
   uv run python3 - <<'PY'
   import sys, pathlib
   sys.path.insert(0, "<PLUGIN_PATH>/scripts")
   import _lockfile
   values = {"lab": "$LAB", "pi": "$PI"} if "$MODE" == "pipeline" else {}
   doc = _lockfile.set_mode(pathlib.Path.cwd(), "$MODE", values)
   print(f"lockfile schema_version={doc['schema_version']} "
         f"plugin_version={doc['plugin_version']} modes={sorted(doc['modes'])}")
   PY
   ```

   The resulting shape:

   ```json
   {
     "schema_version": 1,
     "plugin_version": "<from _lockfile.PLUGIN_VERSION>",
     "plugin_name": "dmac-curation",
     "plugin_sha": "<git rev-parse output, or null>",
     "schema_vintage": "<VINTAGE.json bundled_date>",
     "init_date": "<today>",
     "init_user": "<$USER>",
     "modes": {
       "pipeline": {
         "lab": "<LAB uppercased>",
         "pi": "<PI lowercased>",
         "nextseek_project_id": null
       }
     }
   }
   ```

7. Report: which files were created, which were left alone, which modes the
   lockfile now records, and the suggested next command - `/curate-inventory`
   for pipeline, `/curate-sampletype <TYPE>` for schema,
   `/curate-report <FORMAT> <input>` for report.

## Behavioral rules

- **Create what is missing; never overwrite.** No `--force` flag exists. If the
  user genuinely wants a file replaced, they delete it first.
- If `--lab` or `--pi` is missing for pipeline mode, use `AskUserQuestion`.
  Never guess a lab code; it becomes part of every minted UID.
- A `.env` already present in cwd is a strong signal this is a real project.
  Report it and continue. Never read or print its contents.
- Don't `git init` in the project dir; let the user decide. Suggest it.
- `schema` and `report` modes require no scaffold at all. Running
  `/curate-init --mode schema` in a bare directory creates nothing but a
  lockfile entry, and even that is optional.
```

- [ ] **Step 4: Update the `PHASES.md` Phase 0 section**

Replace its Action and Edge-cases blocks:

```markdown
**Command:** `/curate-init [--lab CODE] [--pi NAME] [--mode NAME]`

**Inputs:** flags. Any cwd - empty, populated with PI inputs, or an existing
curation project.

**Action:** the command is **additive**. It creates what is missing and never
overwrites what exists.

1. Create any missing directories: `files/ manuscript/ previous_metadata/ assay_sheets/ scripts/`.
2. Render any missing templates (`CLAUDE.md`, `.env.example`, `.gitignore`, `pyproject.toml`). Existing files are reported and left alone.
3. Merge the requested mode into `./.dmac-curation.json` via `scripts/_lockfile.py`, which also migrates a v0 lockfile to v1 in place.
4. Report what was created, what was skipped, and which modes the lockfile records.

**Edge cases:**
- Existing project: adding a mode is the normal path, not an error. Prior mode sections are preserved.
- v0 lockfile (no `schema_version`): flat keys migrate into `modes.pipeline`. No data is lost.
- `--lab` or `--pi` missing for pipeline mode: use `AskUserQuestion`, don't guess. A wrong lab code contaminates every minted UID.
- `schema` / `report` mode: no scaffold and no lab/pi needed. These modes must work from any cwd.
- Plugin git dir unreadable: record `"plugin_sha": null` and warn.
- A `.env` in cwd: report it, continue, never read or print it.
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest pytest tests/test_init_additive.py tests/test_identity_sync.py -v`
Expected: all pass, including the `test_curate_init_does_not_hardcode_a_stale_version` left RED by Task 11.

- [ ] **Step 6: Commit**

```bash
git add commands/curate-init.md skills/curation/PHASES.md tests/test_init_additive.py
git commit -m "feat(init): make /curate-init additive so modes can be added

It refused to run if CLAUDE.md or .dmac-curation.json existed, so there was no
path to add a mode to an existing project. It now creates what is missing,
reports what it left alone, and merges the mode into the lockfile via
_lockfile.set_mode, which also migrates v0 to v1 without data loss. The
hardcoded plugin_version 0.1.0 (stale against plugin.json's 0.2.0) is gone.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: `/curate-status` reports per mode

**Files:**
- Create: `scripts/status.py`
- Modify: `commands/curate-status.md` (whole file)
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: `_config.find_project_root` from Task 7; `_lockfile.read`, `_lockfile.mode`, `_lockfile.LockfileError` from Task 10; `curation_project` and `plugin_sentinel` from Task 6
- Produces: `collect_status(root: Path) -> dict` with keys `project_root`, `lockfile`, `modes` (each `{present, detail, artifacts}`), `suggested_next`; CLI `uv run --script scripts/status.py [--project-root DIR] [--json]`

**Context (toolkit spec §2):** `curate-status.md:10-18` is a hand-written phase-to-artifact map in markdown, untestable and with nowhere to describe non-pipeline state.

- [ ] **Step 1: Write the failing test**

Create `tests/test_status.py`:

```python
"""/curate-status reports per mode, not per phase."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import status as status_mod  # noqa: E402

SCRIPT = REPO / "scripts" / "status.py"


def _run(root: Path, *argv):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--project-root", str(root), *argv],
        capture_output=True, text=True, timeout=120,
    )


def test_collect_status_on_empty_dir_reports_no_modes(tmp_path):
    st = status_mod.collect_status(tmp_path)
    assert st["lockfile"] is None
    assert all(not m["present"] for m in st["modes"].values())


def test_collect_status_reports_all_four_modes(tmp_path):
    assert set(status_mod.collect_status(tmp_path)["modes"]) == {
        "pipeline", "fdh", "schema", "report"}


def test_pipeline_mode_present_when_lockfile_has_it(curation_project):
    st = status_mod.collect_status(curation_project)
    assert st["modes"]["pipeline"]["present"] is True
    assert st["lockfile"]["modes"]["pipeline"]["lab"] == "KAM"


def test_pipeline_artifacts_detected(curation_project):
    (curation_project / "FILE_INDEX.md").write_text("x")
    (curation_project / "SAMPLE_TREE.md").write_text("x")
    st = status_mod.collect_status(curation_project)
    found = {a["name"]: a for a in st["modes"]["pipeline"]["artifacts"]}
    assert found["FILE_INDEX.md"]["present"] is True
    assert found["SAMPLE_TREE.md"]["present"] is True
    assert found["RETRIEVE.TXT"]["present"] is False


def test_pipeline_artifacts_are_keyed_by_phase_number(curation_project):
    st = status_mod.collect_status(curation_project)
    phases = {a["phase"] for a in st["modes"]["pipeline"]["artifacts"]}
    assert 4 not in phases, "Phase 4 is retired"
    assert 8 not in phases, "Phase 8 is retired"
    assert {1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13} <= phases


def test_schema_mode_present_when_schema_dir_exists(tmp_path):
    (tmp_path / "schema").mkdir()
    (tmp_path / "schema" / "D.VIA.review.md").write_text("x")
    st = status_mod.collect_status(tmp_path)
    assert st["modes"]["schema"]["present"] is True
    assert "D.VIA" in st["modes"]["schema"]["detail"]


def test_report_mode_present_when_report_dir_exists(tmp_path):
    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "GEO.mapping.json").write_text("{}")
    st = status_mod.collect_status(tmp_path)
    assert st["modes"]["report"]["present"] is True
    assert "GEO" in st["modes"]["report"]["detail"]


def test_fdh_mode_present_when_credentials_are_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("FDH_API", '{"user": "tok"}')
    assert status_mod.collect_status(tmp_path)["modes"]["fdh"]["present"] is True


def test_fdh_mode_never_prints_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("FDH_API", '{"user": "SUPERSECRET"}')
    st = status_mod.collect_status(tmp_path)
    assert "SUPERSECRET" not in json.dumps(st)


def test_suggested_next_on_empty_project(tmp_path):
    assert "/curate-init" in status_mod.collect_status(tmp_path)["suggested_next"]


def test_suggested_next_advances_with_artifacts(curation_project):
    (curation_project / "FILE_INDEX.md").write_text("x")
    st = status_mod.collect_status(curation_project)
    assert "/curate-sample-tree" in st["suggested_next"]


def test_cli_json_output_is_parseable(curation_project):
    r = _run(curation_project, "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["modes"]["pipeline"]["present"] is True


def test_cli_human_output_lists_modes(curation_project):
    r = _run(curation_project)
    assert r.returncode == 0, r.stderr
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in r.stdout
    assert "Suggested next:" in r.stdout


def test_cli_writes_nothing_in_the_plugin(curation_project, plugin_sentinel):
    _run(curation_project)


def test_command_doc_is_per_mode():
    doc = (REPO / "commands" / "curate-status.md").read_text()
    assert "13-phase pipeline" not in doc
    assert "scripts/status.py" in doc
    for mode in ("pipeline", "fdh", "schema", "report"):
        assert mode in doc
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_status.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'status'`.

- [ ] **Step 3: Write `scripts/status.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report dmac-curation state per MODE, not per phase.

The old /curate-status was a hand-written phase-to-artifact map living in
markdown. Detection lives here so it is testable, and so the four modes each
report on their own terms: pipeline has phase artifacts, schema and report have
output directories, fdh has credentials and nothing else.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import find_project_root  # noqa: E402
from _lockfile import LockfileError, mode as lock_mode, read as lock_read  # noqa: E402

# (phase number, path relative to project root or None, human label)
PIPELINE_ARTIFACTS = [
    (1, "FILE_INDEX.md", "Inventory"),
    (2, "SAMPLE_TREE.md", "Sample tree"),
    (3, "QUESTIONS_FOR_PI.md", "Questions"),
    (5, "assay_sheets/4sheet_originals", "Build (4-sheet review artifacts)"),
    (6, "assay_sheets", "Consolidate (flat Arm*.xlsx)"),
    (7, "context/assay_ids_cache.json", "Resolve assays"),
    (7, "context/assay_synonyms.json", "Resolve assays (synonyms)"),
    (9, None, "QA (console report, no artifact)"),
    (10, "Zenodo_upload", "Deposit"),
    (11, "RETRIEVE.TXT", "Retrieve"),
    (12, None, "Validate (console report, no artifact)"),
    (13, "EMAIL_TO_PI.md", "Email"),
]

NEXT_COMMAND = {
    1: "/curate-inventory",
    2: "/curate-sample-tree",
    3: "/curate-questions add",
    5: "/curate-build <arm>",
    6: "/curate-consolidate",
    7: "/curate-resolve-assays --project-id N",
    9: "/curate-qa",
    10: "/curate-deposit <geo|zenodo|omero>",
    11: "/curate-retrieve",
    12: "/curate-validate <downloaded.xlsx>",
    13: "/curate-email",
}


def _count_xlsx(d: Path, *, with_underscore: bool | None = None) -> int:
    if not d.is_dir():
        return 0
    n = 0
    for p in d.glob("*.xlsx"):
        if p.name.startswith("~"):
            continue
        if with_underscore is True and "_" not in p.stem:
            continue
        if with_underscore is False and "_" in p.stem:
            continue
        n += 1
    return n


def _pipeline_status(root: Path, locked: dict) -> dict:
    artifacts = []
    for phase, rel, label in PIPELINE_ARTIFACTS:
        if rel is None:
            artifacts.append({"phase": phase, "name": label,
                              "present": None, "detail": "no artifact"})
            continue
        target = root / rel
        if rel == "assay_sheets/4sheet_originals":
            n = _count_xlsx(target, with_underscore=True)
            artifacts.append({"phase": phase, "name": rel,
                              "present": n > 0, "detail": f"{n} four-sheet files"})
        elif rel == "assay_sheets":
            n = _count_xlsx(target, with_underscore=False)
            artifacts.append({"phase": phase, "name": "assay_sheets/Arm*.xlsx",
                              "present": n > 0, "detail": f"{n} flat files"})
        elif rel == "RETRIEVE.TXT":
            present = target.is_file()
            lines = len(target.read_text().split()) if present else 0
            artifacts.append({"phase": phase, "name": rel, "present": present,
                              "detail": f"{lines} UIDs" if present else ""})
        else:
            artifacts.append({"phase": phase, "name": rel,
                              "present": target.exists(), "detail": ""})

    present_any = bool(locked) or any(a["present"] for a in artifacts)
    detail = ""
    if locked:
        detail = (f"lab={locked.get('lab')} pi={locked.get('pi')} "
                  f"project_id={locked.get('nextseek_project_id')}")
    return {"present": present_any, "detail": detail, "artifacts": artifacts}


def _dir_status(root: Path, subdir: str, glob: str, label: str) -> dict:
    d = root / subdir
    if not d.is_dir():
        return {"present": False, "detail": "", "artifacts": []}
    found = sorted(p.name for p in d.glob(glob))
    stems = sorted({n.split(".")[0] for n in found})
    return {
        "present": bool(found),
        "detail": f"{label}: {', '.join(stems)}" if stems else "",
        "artifacts": [{"name": f"{subdir}/{n}", "present": True, "detail": ""}
                      for n in found],
    }


def _fdh_status(root: Path) -> dict:
    """Credentials only. NEVER surface the token value."""
    sources = []
    if os.environ.get("FDH_API") or os.environ.get("FDH_TOKEN"):
        sources.append("environment")
    env_file = root / ".env"
    if env_file.is_file():
        try:
            text = env_file.read_text()
        except OSError:
            text = ""
        if "FDH_API" in text or "FDH_TOKEN" in text:
            sources.append(".env")
    return {
        "present": bool(sources),
        "detail": (f"credentials from {', '.join(sources)}" if sources
                   else "no FDH_API configured"),
        "artifacts": [],
    }


def _suggest(pipeline: dict, has_lockfile: bool) -> str:
    if not has_lockfile and not pipeline["present"]:
        return ("/curate-init --lab <CODE> --pi <NAME>  "
                "(or /curate-sampletype <TYPE> for schema mode)")
    for a in pipeline["artifacts"]:
        if a["present"] is False and a["phase"] in NEXT_COMMAND:
            return NEXT_COMMAND[a["phase"]]
    return ("pipeline artifacts all present - /curate-email, "
            "or /curate-report GEO <input>")


def collect_status(root: Path) -> dict:
    root = Path(root).resolve()
    has_lockfile = (root / ".dmac-curation.json").is_file()
    try:
        doc = lock_read(root)
    except LockfileError as exc:
        doc = {"modes": {}}
        print(f"warning: {exc}", file=sys.stderr)

    pipeline = _pipeline_status(root, lock_mode(doc, "pipeline"))
    return {
        "project_root": str(root),
        "lockfile": doc if has_lockfile else None,
        "modes": {
            "pipeline": pipeline,
            "fdh": _fdh_status(root),
            "schema": _dir_status(root, "schema", "*.review.md", "types"),
            "report": _dir_status(root, "report", "*.mapping.json", "formats"),
        },
        "suggested_next": _suggest(pipeline, has_lockfile),
    }


def _render(st: dict) -> str:
    lines = [f"Project root: {st['project_root']}"]
    lock = st["lockfile"]
    if lock:
        lines.append(
            f"Lockfile:     schema v{lock.get('schema_version')} "
            f"plugin {lock.get('plugin_version')} "
            f"vintage {lock.get('schema_vintage', '?')} "
            f"modes {sorted(lock.get('modes', {}))}"
        )
    else:
        lines.append("Lockfile:     none - run /curate-init")
    lines.append("")

    for name, m in st["modes"].items():
        lines.append(f"{'OK ' if m['present'] else '-- '}{name:<9} {m['detail']}")
        if name == "pipeline" and m["present"]:
            for a in m["artifacts"]:
                sym = "-" if a["present"] is None else ("OK" if a["present"] else "--")
                lines.append(f"    {sym:<3} phase {a.get('phase', ''):>2}  "
                             f"{a['name']:<38} {a['detail']}")
    lines.append("")
    lines.append(f"Suggested next: {st['suggested_next']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="Emit JSON, not a table")
    args = ap.parse_args(argv)
    st = collect_status(args.project_root or find_project_root())
    print(json.dumps(st, indent=2) if args.json else _render(st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rewrite `commands/curate-status.md`**

```markdown
---
description: Show toolkit state per mode (any mode, any phase)
---

The user wants to know the state of this working directory across all four
dmac-curation modes.

## Steps

1. Run the status collector:

   ```bash
   uv run --script <PLUGIN>/scripts/status.py
   ```

   Add `--project-root DIR` to inspect a directory other than cwd, or `--json`
   for a machine-readable dump.

2. Present the output as-is. It is already terse and needs no reformatting.

3. If the lockfile is missing entirely, note that `pipeline` mode needs
   `/curate-init` but `schema` and `report` do not - they run from any cwd.

## What each mode reports

| mode | reported state |
|---|---|
| `pipeline` | per-phase artifact presence (phases 1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13), plus lab / pi / project id from the lockfile |
| `fdh` | whether `FDH_API` or `FDH_TOKEN` is configured, and from where. **Never the value.** |
| `schema` | sample types with a `schema/<TYPE>.review.md` in cwd |
| `report` | formats with a `report/<FORMAT>.mapping.json` in cwd |

Phases 4 and 8 are retired and are not reported; see `PHASES.md`.

## Behavioral rules

- Be honest about partial state (e.g. "6/8 arms built").
- Never print a credential value, and never read `.env` for anything but the
  presence of a key name.
- Always end with a single-line "Suggested next: ...". The script already does.
- If the lockfile is malformed, the script warns on stderr and continues with
  empty modes. Surface that warning rather than swallowing it.
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_status.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/status.py commands/curate-status.md tests/test_status.py
git commit -m "feat(status): report per mode, move detection into a script

curate-status.md was a hand-written phase-to-artifact map in markdown, which
could not be tested and had no place to describe non-pipeline state.
scripts/status.py reports all four modes: pipeline by phase artifact, fdh by
credential presence (never value), schema and report by their cwd output dirs.
Retired phases 4 and 8 are not reported.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Mode-aware project scaffold template

**Files:**
- Modify: `templates/CLAUDE.md.j2` (whole file)
- Test: `tests/test_templates_render.py` (extend)

**Interfaces:**
- Consumes: the `modes` list `/curate-init` passes (Task 13, step 5)
- Produces: `CLAUDE.md.j2` emitting the pipeline step list only when `pipeline` is in `modes`, defaulting to `['pipeline']` when the variable is absent

**Context (toolkit spec Testing):** `CLAUDE.md.j2:17-35` bakes the 11-step pipeline order into every scaffolded project, including ones scaffolded for `schema` or `report` mode where it is noise.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_templates_render.py` (add `from pathlib import Path` and `REPO = Path(__file__).resolve().parent.parent` at the top if not already present):

```python
def _render_claude_md(**ctx):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(loader=FileSystemLoader(str(REPO / "templates")),
                      undefined=StrictUndefined)
    base = {"lab": "kam", "pi_name": "marie", "init_date": "2026-07-21"}
    base.update(ctx)
    return env.get_template("CLAUDE.md.j2").render(**base)


def test_claude_md_renders_pipeline_steps_when_pipeline_mode():
    out = _render_claude_md(modes=["pipeline"])
    assert "/curate-inventory" in out
    assert "/curate-consolidate" in out
    assert "Modes enabled" in out


def test_claude_md_omits_pipeline_steps_for_schema_only():
    out = _render_claude_md(modes=["schema"])
    assert "/curate-inventory" not in out
    assert "/curate-sampletype" in out


def test_claude_md_defaults_to_pipeline_when_modes_absent():
    """Backward compatibility: an old caller passing no `modes` still works."""
    assert "/curate-inventory" in _render_claude_md()


def test_claude_md_lists_eleven_pipeline_steps():
    import re
    out = _render_claude_md(modes=["pipeline"])
    block = out.split("Suggested order:", 1)[1].split("\n\n", 1)[0]
    numbered = re.findall(r"^\s*(\d+)\. ", block, flags=re.M)
    assert len(numbered) == 11, f"expected 11 steps, got {numbered}"


def test_claude_md_records_why_both_sheet_formats_exist():
    out = _render_claude_md(modes=["pipeline"])
    assert "review artifact" in out


def test_claude_md_has_no_em_dashes():
    """Charlie's style rule; this file is read by the PI's collaborators."""
    assert "—" not in (REPO / "templates" / "CLAUDE.md.j2").read_text()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with jinja2 pytest tests/test_templates_render.py -v -k claude_md`
Expected: FAILs - `modes` is an unknown variable under `StrictUndefined`, and the current file contains em dashes.

- [ ] **Step 3: Rewrite `templates/CLAUDE.md.j2`**

```jinja
{%- set active = modes | default(['pipeline']) -%}
# {{ pi_name|title }} curation - {{ lab|upper }} lab

**Project initialized:** {{ init_date }}
**Lab tag:** `{{ lab|upper }}` (UIDs use format `<TYPE>-YYMMDD{{ lab|upper }}-N`)
**PI:** {{ pi_name }}
**NExtSEEK project ID:** {{ project_id | default('TBD - set after /curate-resolve-assays', true) }}
**Modes enabled:** {{ active | join(', ') }}

Run `/curate-status` at any time to see state across every mode.

{% if 'pipeline' in active -%}
## Inputs

Drop these into the empty subdirectories before running `/curate-inventory`:

- `files/` - PI's raw data (images, sequencing, mass spec, etc.)
- `manuscript/` - paper draft (.docx, PDFs)
- `previous_metadata/` - master spreadsheet ({{ lab|upper }} All YYMMDD.xlsx) plus any PI-returned edits
- `email_convo.md` (optional) - PI email thread

## Pipeline mode

11 phases driven by 13 commands. Suggested order:

1. `/curate-inventory` -> `FILE_INDEX.md`
2. `/curate-sample-tree` -> `SAMPLE_TREE.md`
3. `/curate-questions add` (as gaps surface) -> `QUESTIONS_FOR_PI.md`
4. `/curate-build <arm>` per arm -> `assay_sheets/4sheet_originals/`
5. `/curate-consolidate` -> `assay_sheets/Arm{X}.xlsx`
6. `/curate-resolve-assays --project-id N` -> `context/assay_ids_cache.json` (then curate `context/assay_synonyms.json`)
7. `/curate-qa` -> CLEAN/SOFT_FLAG/HARD_REJECT report
8. `/curate-deposit <target>` -> external uploads plus URL backfill
9. `/curate-retrieve` -> `RETRIEVE.TXT`
10. `/curate-validate <downloaded.xlsx>` -> round-trip diff
11. `/curate-email` -> `EMAIL_TO_PI.md`

The 4-sheet files `/curate-build` writes are a **review artifact**, not a build
intermediate. Curators eyeball them per sample type before `/curate-consolidate`
collapses them into per-arm flat files. That is why both formats exist, and it
is also the only format where NExtSEEK enforces controlled vocabulary.

{% endif -%}
{% if 'schema' in active -%}
## Schema mode

Define or bolster a NExtSEEK sample type:

- `/curate-sampletype <TYPE>` -> `schema/<TYPE>.review.md` plus the proposed
  record, its controlled vocabulary, and a field dictionary

Output is a **proposal**. A human reviews it and applies it by hand. The mode
never writes to NExtSEEK.

{% endif -%}
{% if 'report' in active -%}
## Report mode

Build a repository submission artifact from metadata you already have:

- `/curate-report GEO <input>` -> `report/GEO_filled.xlsx` plus the mapping spec
  and a completeness report
- Same for `SRA` and `PRIDE`

The input can be UIDs, a NExtSEEK workbook, a curated `Arm{X}.xlsx`, or an
arbitrary xlsx/csv.

{% endif -%}
## FairDomHub

Available in any project, no scaffold needed:

- `/fdh-upload` - interactive study upload
- `/fdh-api` - programmatic find / delete / patch

Auth: put `FDH_API` in `.env` or your environment. Never commit it.

## Plugin lockfile

`.dmac-curation.json` records the plugin SHA, the schema vintage used at init,
and one section per enabled mode. Don't edit it by hand; `/curate-init` merges
into it and `scripts/_lockfile.py` owns its shape.
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with jinja2 pytest tests/test_templates_render.py -v`
Expected: all pass.

- [ ] **Step 5: Run the end-to-end init smoke test**

Run: `bash tests/test_e2e_init.sh`
Expected: exit 0. If it asserts on the old `CLAUDE.md` text or on init's refusal behaviour, update those assertions to match Task 13's additive contract.

- [ ] **Step 6: Commit**

```bash
git add templates/CLAUDE.md.j2 tests/test_templates_render.py tests/test_e2e_init.sh
git commit -m "feat(templates): mode-aware CLAUDE.md scaffold

CLAUDE.md.j2 baked the pipeline step list into every scaffolded project,
including ones scaffolded for schema or report mode where it was noise. It now
branches on the modes list /curate-init passes, defaulting to pipeline for
backward compatibility. Also records why both sheet formats exist (the 4-sheet
files are a curator review artifact) and drops the em dashes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage D — Pipeline corrections

### Task 16: Document the two decisions that are invisible in the code

**Files:**
- Modify: `skills/curation/PHASES.md` — Phase 5, 6, 7 sections; delete the Phase 4 and Phase 8 sections
- Modify: `commands/curate-build.md`, `commands/curate-consolidate.md`, `commands/curate-resolve-assays.md`
- Test: `tests/test_phases_doc.py`

**Interfaces:**
- Consumes: `tests/test_mode_table.py::test_phase_table_omits_deleted_phases` from Task 12
- Produces: `PHASES.md` stating (a) why the 4-sheet intermediate exists and (b) that flat cannot carry controlled vocabulary

**Context — this task's whole point.** Two facts drive the pipeline's shape and appear in no file in the repo:

1. **Curators review the per-sample-type 4-sheet files before consolidation.** That is why Phases 5 and 6 do not collapse. A future reader without this re-derives the "why build 4-sheet at all?" challenge and reaches the wrong conclusion — the 2026-07-21 review nearly did.
2. **Ontology validation exists only in the 4-sheet format.** Flat has no Ontology sheet, and `InputRowModel` is `additionalProperties: true` with unknown columns "ignored, with a warning" — so an ontology column added to a flat sheet is **accepted and silently discarded**, worse than rejection.

- [ ] **Step 1: Write the failing test**

Create `tests/test_phases_doc.py`:

```python
"""PHASES.md must record the two decisions that are invisible in the code."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PHASES = REPO / "skills" / "curation" / "PHASES.md"


def _section(number: int) -> str:
    text = PHASES.read_text()
    marker = f"## Phase {number} "
    assert marker in text, f"no section for phase {number}"
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_phase_5_states_the_output_is_a_review_artifact():
    s = _section(5)
    assert "review artifact" in s.lower()
    assert "curator" in s.lower()


def test_phase_5_explains_why_it_does_not_collapse_into_phase_6():
    assert "not a build intermediate" in _section(5).lower()


def test_phase_5_documents_the_ontology_parameter():
    s = _section(5)
    assert "write_4sheet_xlsx" in s
    assert "ontology=" in s


def test_phase_6_warns_flat_cannot_carry_controlled_vocabulary():
    s = _section(6)
    assert "Ontology" in s
    assert "silently discard" in s.lower()


def test_phase_6_records_the_multiple_sample_types_constraint():
    assert "only allowed in flat" in _section(6).lower()


def test_phase_7_owns_the_synonyms_artifact():
    s = _section(7)
    assert "assay_synonyms.json" in s
    assert "formerly Phase 8" in s


def test_no_standalone_phase_4_or_8_sections():
    text = PHASES.read_text()
    assert "\n## Phase 4 " not in text
    assert "\n## Phase 8 " not in text


def test_phase_3_absorbed_the_task_plan_guidance():
    s = _section(3)
    assert "TaskCreate" in s or "task list" in s.lower()


def test_the_verify_flag_is_recorded():
    """The flat-vs-ontology claim is read from a 2026-05-27 API spec."""
    text = PHASES.read_text()
    assert "2026-05-27" in text
    assert "confirm with the nextseek api owner" in text.lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_phases_doc.py -v`
Expected: most FAIL; `test_no_standalone_phase_4_or_8_sections` fails because those sections still exist.

- [ ] **Step 3: Rewrite the Phase 5 section of `PHASES.md`**

Replace the whole `## Phase 5 — Build` section:

```markdown
## Phase 5 — Build

**Command:** `/curate-build [<arm>]`

**Inputs:** `SAMPLE_TREE.md`, `previous_metadata/*.xlsx` (master), `manuscript/`, `.dmac-curation.json` (lab + pi)

**Output:** `assay_sheets/4sheet_originals/<arm>_<sampletype>.xlsx`, one per sample
type, plus the generated `./scripts/build_<arm>.py` that produced them.

### The 4-sheet output is a review artifact, not a build intermediate

This is the single most important thing to know about Phases 5 and 6, and it is
invisible in the code.

The obvious challenge is: why build 4-sheet at all, when flat is what NExtSEEK
ingests? There is a hard technical reason for two formats, stated in
`consolidate_to_flat.py:19-21` - multiple sample types in one file are **only
allowed in flat format**, so a per-arm file mixing types must be flat. But that
alone would still allow building flat directly.

**The deciding reason is human: curators review the per-sample-type 4-sheet
files before consolidation.** The per-type split is what makes eyeballing
tractable. A future reader without this will re-derive the challenge and reach
the wrong conclusion, as the 2026-07-21 pipeline review nearly did.

So: Phase 5's output is what a person looks at. Phase 6's output is what a
machine ingests. Neither replaces the other.

### The Ontology sheet is where controlled vocabulary lives

`_common.write_4sheet_xlsx` accepts `ontology={fieldname: [allowed values]}`,
writes a real Ontology sheet, and declares those fields `Controlled Ontology` on
the Instructions sheet. **Ontology validation is strict in this format and
violations reject the file** - and this is the *only* upload format where that
is true (see Phase 6).

Because Phase 5's output is a review artifact, populating the Ontology sheet
puts the allowed values in front of the curator at exactly the moment they are
checking the data. `schema` mode produces `schema/<TYPE>.ontology.json` in
precisely the shape `write_4sheet_xlsx(ontology=...)` expects.

**Action:** the generated `build_<arm>.py` should pass `ontology=` when a
`schema/<TYPE>.ontology.json` exists in the project. Historically no caller ever
passed it, so the mechanism existed and nothing populated it.

**Action:**
1. Identify arm. If not supplied, list arms from `SAMPLE_TREE.md` and `AskUserQuestion`.
2. Read sample types and counts for the arm.
3. Read master to identify existing parent UIDs. Workbook precedent beats the schema (hard rule 4).
4. Read manuscript for protocol section names and instrument details.
5. Generate `./scripts/build_<arm>.py`:
   - PEP 723 inline deps (openpyxl)
   - `sys.path.insert(0, "<PLUGIN_PATH>/scripts")`
   - `from _common import mint_uid, write_4sheet_xlsx, schema_column_order, placeholder`
   - Per-project constants come from `./scripts/_project_constants.py` (copy `<PLUGIN>/scripts/_project_constants.py.example`), never from `_common`
   - Mint UIDs `<TYPE>-YYMMDD<LAB>-N`
   - Write one 4-sheet xlsx per sample type into `assay_sheets/4sheet_originals/`
6. Run the script. Report row counts.
7. Suggest the next arm, or `/curate-consolidate`.

**Edge cases:**
- Missing manifest data: use `placeholder("<what is missing>")`, never a blank.
- Sample type new to the schema: write to `assay_sheets/pending_schema/`, and consider `/curate-sampletype <TYPE>` to propose the record.
- Mid-arm scope ambiguity: stop, add to `QUESTIONS_FOR_PI.md`, propose to the user.
```

- [ ] **Step 4: Rewrite the Phase 6 section**

```markdown
## Phase 6 — Consolidate

**Command:** `/curate-consolidate`

**Inputs:** `assay_sheets/4sheet_originals/*.xlsx`, optional `context/assay_ids_cache.json` + `context/assay_synonyms.json`

**Output:** `assay_sheets/Arm{X}.xlsx`, flat format, one per arm.

### Flat cannot carry controlled vocabulary

Verified against `context/NExtSEEK_API.yaml`:

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | "Ontology validation is not performed in rows mode" |
| flat xlsx (this phase's output) | **none** - the format has no Ontology sheet |
| 4-sheet xlsx (Phase 5's output) | "Validation is strict; violations reject the file" |

So this phase converts the format that **can** enforce vocabulary into the one
that cannot. That costs nothing while nothing populates the Ontology sheet; it
becomes a live loss the moment `schema` mode does.

**Adding an ontology column to a flat sheet does not work.** `InputRowModel`'s
complete field set is `UID, SampleType, json_metadata, assay_ids, project_id,
study_title, study_id, sop_id, assay_titles, original_row_index` - no ontology
field. The model is `additionalProperties: true` and unknown columns are
"ignored, with a warning", so the column would be **accepted and silently
discarded**. That is a worse failure than rejection.

**Decision: keep both formats and let the curator choose per upload.** 4-sheet
when vocabulary enforcement is wanted, flat for convenience and for multi-type
files. Multiple sample types in one file are **only allowed in flat format**
(`consolidate_to_flat.py:19-21`), which is why per-arm files are flat.

**Verify before relying on this.** The table above is read from
`context/NExtSEEK_API.yaml`, bundled **2026-05-27**. Confirm with the NExtSEEK
API owner that flat still lacks ontology support before designing anything new
around it.

**Action:**
1. Invoke `scripts/consolidate_to_flat.py --assay-sheets assay_sheets`.
2. Archive 4-sheet originals into `4sheet_originals/` if not already there.
3. Per arm, produce a flat xlsx with a `Samples` sheet (`uid, sampletype, name, parent, notes_summary, assay_titles, assay_ids, json_metadata`) and a `README` sheet.
4. Report per-arm row counts and assay-ID resolution coverage.

**Edge cases:**
- Cache or synonyms missing: leave `assay_ids` blank, suggest `/curate-resolve-assays`.
- Pending-schema sample types: write to `assay_sheets/pending_schema/Arm<X>.xlsx`.
- Re-run: prior consolidated outputs in the target dir are deleted first, so a stale arm file cannot survive. That deletion is scoped to the resolved project's assay-sheets dir and refuses to run inside the plugin checkout.
```

- [ ] **Step 5: Fold the retired phases in**

Delete the `## Phase 4 — Task plan` section entirely. Append to the Phase 3 section:

```markdown
### Task-plan guidance (formerly Phase 4)

Use `TaskCreate` to record one task per arm, with `blockedBy` dependencies (e.g.
Arm G blocked by Arm E plus Arm F). This is good practice, not a pipeline stage
- it has no command, no script and no artifact, which is why it is no longer
numbered.
```

Delete the `## Phase 8 — Synonyms` section entirely. Append to the Phase 7 section:

```markdown
### `assay_synonyms.json` (formerly Phase 8)

Synonym curation is part of this phase, not a separate one - same command, same
invocation. It existed as its own number only because it produces a second
artifact, and artifacts are not phases.

After the cache is written: read `context/assay_ids_cache.json`, compare against
the `assay_titles` column in `assay_sheets/Arm*.xlsx`, propose mappings for
cited titles that did not resolve, and ask the user to confirm. Write
`context/assay_synonyms.json` with `_README` and `synonyms_by_cited_name` keys,
each entry annotated with a `_notes` block explaining the reasoning.

Assay IDs are **project-scoped**: the same title maps to different IDs across
projects. Re-run the fetch and re-review the synonyms whenever switching
projects.
```

- [ ] **Step 6: Update the three command docs**

Append to `commands/curate-build.md`'s behavioral rules:

```markdown
- The 4-sheet files you write are a **curator review artifact**, not a build
  intermediate. They are what a person eyeballs per sample type before
  `/curate-consolidate` collapses them. Do not propose skipping them.
- If `schema/<TYPE>.ontology.json` exists in the project, pass it to
  `write_4sheet_xlsx(ontology=...)`. The Ontology sheet is the only place
  NExtSEEK enforces controlled vocabulary.
```

Append to `commands/curate-consolidate.md`:

```markdown
- Flat format has no Ontology sheet, so any controlled vocabulary in the 4-sheet
  originals is dropped here. That is expected. Tell the user which format they
  are uploading and why, rather than letting the loss be silent.
```

Append to `commands/curate-resolve-assays.md`:

```markdown
- Synonym curation is part of this command, not a separate phase. After writing
  the cache, propose `context/assay_synonyms.json` entries for unresolved cited
  titles and ask the user to confirm each.
```

- [ ] **Step 7: Run the tests**

Run: `uv run --with pytest pytest tests/test_phases_doc.py tests/test_mode_table.py -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add skills/curation/PHASES.md commands/ tests/test_phases_doc.py
git commit -m "docs(phases): 13 phases -> 11, record the two invisible decisions

Deleted phases 4 (task plan: no command, no script, no artifact) and 8
(synonyms: already the same command and invocation as phase 7). Numbers are
retired, not reused, because scaffolded CLAUDE.md files and curators both speak
in phase numbers.

Recorded two facts that drive the pipeline's shape and appeared in no file:
(1) Phase 5's 4-sheet output is a curator REVIEW artifact, which is why 5 and 6
do not collapse; (2) ontology validation exists only in 4-sheet, and an ontology
column added to a flat sheet is accepted and SILENTLY DISCARDED because
InputRowModel is additionalProperties:true. Both carry the 2026-05-27 vintage of
the API spec they were read from.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Phase 12 actually reads `RETRIEVE.TXT`

**Files:**
- Modify: `scripts/review_metadata_vs_uploads.py`
- Modify: `commands/curate-validate.md`
- Modify: `skills/curation/PHASES.md` Phase 12 section
- Test: `tests/test_review_metadata.py`

**Interfaces:**
- Consumes: `_config.config_from_args` from Task 7 (wired by Task 8)
- Produces: `load_retrieve_uids(path) -> set[str] | None`; `diff_retrieve(requested, downloaded, parent_types) -> dict | None` returning `{"missing": [...], "auto_pulled_parents": [...], "extra": [...]}`; CLI flag `--retrieve`

**Context:** `PHASES.md:246` names `RETRIEVE.TXT` as a Phase 12 input and describes the "which requested UIDs are missing" diff, but the script has no `--retrieve` flag, so that diff has never run. Silently ignoring a documented input is the worse failure mode. This is the last RED row in Task 3's drift test.

> **AMENDED after Task 3's review.** The metadata input flag has **three
> competing names** and this task settles it:
>
> | source | name |
> |---|---|
> | `scripts/review_metadata_vs_uploads.py:233` | `--metadata-xlsx` |
> | `commands/curate-validate.md:17` | `--metadata` |
> | this plan's own Step 5 rewrite, as first written | `--downloaded` |
>
> **Decision: standardize on `--metadata-xlsx`**, the name the script already
> registers. It is descriptive, it is the only one that exists in code, and
> renaming a working flag purely to match a doc that was wrong is churn. So:
>
> - Do **not** introduce `--downloaded`. Where Step 5's command-doc rewrite below
>   shows `--downloaded <metadata.xlsx>`, write `--metadata-xlsx <PATH>` instead.
> - Fix `commands/curate-validate.md:17` to say `--metadata-xlsx`.
> - Update the `curate-validate.md` row in
>   `tests/test_curate_commands_present.py::CONTRACTS` from `--metadata` to
>   `--metadata-xlsx`, so the row goes green only when doc and CLI agree.
> - `--assay-sheets` vs the script's existing `--sheets-dir` (`:238`) is
>   **Task 8's** to settle, not this task's — Task 8 Step 6 already adds
>   `--assay-sheets` to this script as part of the path re-anchoring. By the time
>   you run, `--assay-sheets` should exist and `--sheets-dir` should be gone. If
>   both are present, that is a Task 8 miss: retire `--sheets-dir` and say so in
>   your report. Do not add a third name.

- [ ] **Step 1: Write the failing test**

Create `tests/test_review_metadata.py`:

```python
"""Phase 12 must actually read RETRIEVE.TXT (PHASES.md:246 claimed it did)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "review_metadata_vs_uploads.py"
sys.path.insert(0, str(REPO / "scripts"))

import review_metadata_vs_uploads as review  # noqa: E402


def test_retrieve_flag_exists():
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "--retrieve" in r.stdout


def test_load_retrieve_uids_reads_one_per_line(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("D.SEQ-190902KAM-1\nD.IMG-190902KAM-2\n\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-190902KAM-1", "D.IMG-190902KAM-2"}


def test_load_retrieve_uids_strips_whitespace_and_blanks(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("  D.SEQ-190902KAM-1  \n\n\n  \nD.IMG-190902KAM-2\n")
    assert review.load_retrieve_uids(p) == {
        "D.SEQ-190902KAM-1", "D.IMG-190902KAM-2"}


def test_load_retrieve_uids_missing_file_returns_none(tmp_path):
    assert review.load_retrieve_uids(tmp_path / "nope.txt") is None


def test_diff_reports_requested_but_absent():
    d = review.diff_retrieve({"A-1", "A-2", "A-3"}, {"A-1", "A-3", "PARENT-9"},
                             parent_types={"PARENT"})
    assert d["missing"] == ["A-2"]
    assert d["auto_pulled_parents"] == ["PARENT-9"]
    assert d["extra"] == []


def test_diff_classifies_auto_pulled_parents_separately():
    """chat_nextseek auto-pulls parents; they are not extra rows to alarm on."""
    d = review.diff_retrieve({"D.SEQ-1"},
                             {"D.SEQ-1", "RNA-1", "MUS-1", "SURPRISE-1"},
                             parent_types={"RNA", "MUS", "DNA", "TIS"})
    assert d["missing"] == []
    assert sorted(d["auto_pulled_parents"]) == ["MUS-1", "RNA-1"]
    assert d["extra"] == ["SURPRISE-1"]


def test_diff_with_no_retrieve_file_is_a_no_op():
    assert review.diff_retrieve(None, {"A-1"}, parent_types=set()) is None


def test_default_parent_types_cover_the_auto_pulled_set():
    assert review.AUTO_PULLED_PARENT_TYPES >= {
        "MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}


def test_command_doc_documents_the_flag():
    assert "--retrieve" in (REPO / "commands" / "curate-validate.md").read_text()


def test_phases_doc_no_longer_overclaims():
    text = (REPO / "skills" / "curation" / "PHASES.md").read_text()
    s = text.split("## Phase 12 ", 1)[1].split("\n## ", 1)[0]
    assert "--retrieve" in s
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_review_metadata.py -v`
Expected: FAILs — `--retrieve` absent, `load_retrieve_uids` and `diff_retrieve` do not exist.

- [ ] **Step 3: Add the two functions**

In `scripts/review_metadata_vs_uploads.py`, after the `COMPARE_COLS` block (around line 39):

```python
# Sample types chat_nextseek auto-pulls when resolving lineage. Their presence
# in a download is expected, not "extra rows" worth alarming about.
AUTO_PULLED_PARENT_TYPES = {"MUS", "TIS", "DNA", "RNA", "PAT", "PAV", "CHM", "CEL"}


def load_retrieve_uids(path):
    """Read RETRIEVE.TXT into a set of UIDs. None when the file is absent.

    PHASES.md named this as a Phase 12 input while the script had no flag to
    read it, so the documented diff never ran.
    """
    path = Path(path)
    if not path.is_file():
        return None
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def diff_retrieve(requested, downloaded, parent_types=AUTO_PULLED_PARENT_TYPES):
    """Classify the round trip.

    Args:
      requested:    UIDs from RETRIEVE.TXT, or None to skip entirely.
      downloaded:   UIDs present in the downloaded workbook.
      parent_types: sample-type prefixes auto-pulled by lineage.

    Returns:
      None when `requested` is None, else
      {"missing": [...],              # asked for, not in the download
       "auto_pulled_parents": [...],  # in the download, expected, not asked for
       "extra": [...]}                # in the download, unexpected
    """
    if requested is None:
        return None
    missing = sorted(requested - downloaded)
    unrequested = downloaded - requested
    auto = sorted(u for u in unrequested if u.split("-", 1)[0] in parent_types)
    extra = sorted(u for u in unrequested if u.split("-", 1)[0] not in parent_types)
    return {"missing": missing, "auto_pulled_parents": auto, "extra": extra}
```

- [ ] **Step 4: Register the flag and report the diff**

Add to `main()`'s parser:

```python
    ap.add_argument(
        "--retrieve", type=Path, default=None,
        help="RETRIEVE.TXT of requested UIDs. Reports which were requested but "
             "absent from the download (default: <project-root>/RETRIEVE.TXT "
             "when present)",
    )
```

After the existing per-field diff output, add:

```python
    retrieve_path = args.retrieve or (cfg.root / "RETRIEVE.TXT")
    requested = load_retrieve_uids(retrieve_path)
    if requested is None:
        print(f"\nRETRIEVE round trip: skipped (no {retrieve_path})")
    else:
        d = diff_retrieve(requested, downloaded_uids)
        print("\n" + "-" * 60)
        print("RETRIEVE ROUND TRIP")
        print("-" * 60)
        print(f"Source: {retrieve_path}")
        print(f"Requested: {len(requested)}   Downloaded: {len(downloaded_uids)}")
        print(f"  auto-pulled parents (expected): {len(d['auto_pulled_parents'])}")
        if d["missing"]:
            print(f"  REQUESTED BUT MISSING: {len(d['missing'])}")
            for u in d["missing"][:20]:
                print(f"      - {u}")
            if len(d["missing"]) > 20:
                print(f"      ... and {len(d['missing']) - 20} more")
        else:
            print("  every requested UID is present")
        if d["extra"]:
            print(f"  unexpected extra rows: {len(d['extra'])}")
            for u in d["extra"][:20]:
                print(f"      - {u}")
```

`downloaded_uids` must be the set of UIDs the script already collected from the
downloaded workbook. If it is not currently held in a variable, build it where
the workbook is parsed:

```python
    downloaded_uids = {str(r["UID"]).strip() for r in downloaded_rows if r.get("UID")}
```

- [ ] **Step 5: Update `commands/curate-validate.md`**

Replace its steps section:

```markdown
## Steps

1. Invoke the reviewer:

   ```bash
   uv run --script <PLUGIN>/scripts/review_metadata_vs_uploads.py \
       --downloaded <metadata.xlsx> \
       --retrieve RETRIEVE.TXT \
       --assay-sheets assay_sheets
   ```

   `--retrieve` defaults to `<project-root>/RETRIEVE.TXT` when it exists. Pass
   it explicitly when validating a download from a different retrieve set.

2. Read the three sections of the report:
   - **Field drift** - upload-sheet values vs the round-tripped values
   - **RETRIEVE round trip** - requested UIDs missing from the download, plus
     auto-pulled parents (expected) and unexpected extras
   - **Counts**

3. Distinguish formatting drift (whitespace, case) from semantic drift (a
   genuinely different value). Only the latter is a problem.

4. Auto-pulled parents are **expected**. `chat_nextseek` walks lineage upward,
   so MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL rows appear in the download without being
   requested. Subtract them before alarming about extra rows.
```

- [ ] **Step 6: Update the `PHASES.md` Phase 12 Action block**

```markdown
**Action:**
1. Invoke `scripts/review_metadata_vs_uploads.py --downloaded <xlsx> --retrieve RETRIEVE.TXT --assay-sheets assay_sheets`.
2. Report three diffs:
   - which upload-sheet field values differ from the round-tripped values
   - which `RETRIEVE.TXT` UIDs are missing from the download
   - which downloaded rows were auto-pulled parents (expected) vs genuinely unexpected
3. `--retrieve` defaults to `<project-root>/RETRIEVE.TXT` when present, and is skipped with a printed note when absent.
```

- [ ] **Step 7: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_review_metadata.py -v`
Expected: all pass.

- [ ] **Step 8: Confirm the drift test is finally fully green**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_commands_present.py -v`
Expected: all pass — the last RED row from Task 3 is closed.

- [ ] **Step 9: Run the full suite**

Run: `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v 2>&1 | tail -20`
Expected: fully green.

- [ ] **Step 10: Commit**

```bash
git add scripts/review_metadata_vs_uploads.py commands/curate-validate.md \
        skills/curation/PHASES.md tests/test_review_metadata.py
git commit -m "fix(validate): Phase 12 actually reads RETRIEVE.TXT

PHASES.md:246 named RETRIEVE.TXT as a Phase 12 input and described the 'which
requested UIDs are missing' diff, but the script had no --retrieve flag, so that
diff never ran. Added --retrieve (defaulting to the project's RETRIEVE.TXT when
present) plus diff_retrieve(), which separates auto-pulled lineage parents from
genuinely unexpected extra rows.

Closes the last RED row in tests/test_curate_commands_present.py.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage E — Context freshness

### Task 18: A real refresh path for `context/`

**Files:**
- Create: `scripts/refresh_context.py`
- Modify: `context/VINTAGE.json`
- Create: `context/PROVENANCE.json`
- Test: `tests/test_refresh_context.py`

**Interfaces:**
- Consumes: `plugin_sentinel` from Task 6
- Produces:
  - CLI: `uv run --script scripts/refresh_context.py [--check] [--from-dir DIR] [--write]`
  - `provenance_entry(*, source_repo, source_path, commit_sha, vendored_date, local_divergence, sha256=None) -> dict`
  - `read_provenance() -> dict`, `write_provenance(doc) -> Path`
  - `sample_property_count(path) -> int`, `edge_count(path) -> int`
  - `context/PROVENANCE.json`, consumed by Tasks 24 and 25 for vendored report assets

**Context (toolkit spec, Immediate items):** `context/neo4j_schema.json` is byte-identical (modulo `fetched_at`) to chat_nextseek's **dev-instance** snapshot from 2026-03-26, carrying **23 `Sample` properties** where the live copy (2026-05-11) has **85**. `context/neo4j_assay-sample-conn.json` differs too (176 edges vs 163). `VINTAGE.json` admits *"Refresh via tools/refresh_context.py (planned, not yet implemented)"* — and `tools/` does not exist. Every mode built on these specs reasons about the graph from this data.

- [ ] **Step 1: Measure the gap before changing anything**

Run:

```bash
uv run python3 - <<'PY'
import json, pathlib
roots = [pathlib.Path('/home/cdemu/code/dmac/curation_skill/context'),
         pathlib.Path('/home/cdemu/code/chat_nextseek')]
for root in roots:
    for p in (root.rglob('neo4j_schema*.json') if root.is_dir() else []):
        if '.git' in p.parts:
            continue
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f'UNREADABLE {p}: {e}'); continue
        n = 0
        for key in ('labels', 'nodes', 'node_properties', 'schema'):
            c = d.get(key)
            if isinstance(c, dict) and hasattr(c.get('Sample'), '__len__'):
                n = len(c['Sample']); break
        print(f'{n:>4} Sample properties  {p}')
PY
```

Expected: the plugin's bundled copy shows ~23; chat_nextseek's live copy shows ~85. **If the JSON shape differs from this probe's assumptions, adapt the key path but keep the count comparison — the count is the signal.** Record both numbers; they go in the commit message.

- [ ] **Step 2: Write the failing test**

Create `tests/test_refresh_context.py`:

```python
"""context/ must have a real refresh path and a provenance record.

VINTAGE.json promised 'Refresh via tools/refresh_context.py (planned, not yet
implemented)' and tools/ did not exist, while the bundled neo4j_schema.json was
a DEV-instance snapshot with 23 Sample properties against a live 85.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "refresh_context.py"
sys.path.insert(0, str(REPO / "scripts"))

import refresh_context as rc  # noqa: E402

MANAGED = [
    "sampletypes_db.json", "assays_db.json", "projects_db.json",
    "neo4j_schema.json", "neo4j_assay-sample-conn.json",
]


def test_script_exists_and_help_runs():
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    for flag in ("--from-dir", "--check", "--write"):
        assert flag in r.stdout


def test_managed_files_list_matches_vintage():
    vintage = json.loads((REPO / "context" / "VINTAGE.json").read_text())
    for name in MANAGED:
        assert name in vintage["files"], f"{name} not described in VINTAGE.json"


def test_vintage_no_longer_promises_a_nonexistent_tool():
    text = (REPO / "context" / "VINTAGE.json").read_text()
    assert "tools/refresh_context.py" not in text
    assert "planned, not yet implemented" not in text
    assert "scripts/refresh_context.py" in text


def test_vintage_records_the_instance_each_file_came_from():
    vintage = json.loads((REPO / "context" / "VINTAGE.json").read_text())
    assert "instance" in vintage, (
        "VINTAGE.json must record whether snapshots came from prod or dev")


def test_provenance_file_exists_with_entries_key():
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    assert isinstance(prov, dict)
    assert "entries" in prov


def test_provenance_entry_shape():
    e = rc.provenance_entry(
        source_repo="chat_nextseek",
        source_path="src/chat_nextseek/context/neo4j_schema.json",
        commit_sha="deadbeef",
        vendored_date="2026-07-21",
        local_divergence="none",
    )
    assert set(e) == {"source_repo", "source_path", "commit_sha",
                      "vendored_date", "local_divergence"}


def test_provenance_entry_carries_sha256_when_given():
    e = rc.provenance_entry(
        source_repo="r", source_path="p", commit_sha="c",
        vendored_date="2026-07-21", local_divergence="none", sha256="abc")
    assert e["sha256"] == "abc"


def test_every_managed_context_file_has_provenance():
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    for name in MANAGED:
        assert f"context/{name}" in prov["entries"], (
            f"context/{name} has no provenance entry")


def test_check_mode_writes_nothing(plugin_sentinel):
    r = subprocess.run(["uv", "run", "--script", str(SCRIPT), "--check"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode in (0, 1), r.stderr


def test_refresh_requires_write_to_mutate(tmp_path, plugin_sentinel):
    src = tmp_path / "src"
    src.mkdir()
    (src / "sampletypes_db.json").write_text(json.dumps([{"SampleType": "ZZZ"}]))
    r = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), "--from-dir", str(src)],
        capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout.lower()


def test_refresh_writes_and_records_provenance(tmp_path, monkeypatch):
    """Exercise the write path against a temporary plugin-like tree."""
    ctx = tmp_path / "plugin" / "context"
    ctx.mkdir(parents=True)
    (ctx / "sampletypes_db.json").write_text("[]")
    (ctx / "PROVENANCE.json").write_text(json.dumps({"entries": {}}))

    src = tmp_path / "src"
    src.mkdir()
    (src / "sampletypes_db.json").write_text(json.dumps([{"SampleType": "ZZZ"}]))

    monkeypatch.setattr(rc, "CONTEXT_DIR", ctx)
    rc.refresh(src, write=True, commit_sha="cafe1234", today="2026-07-21")

    assert json.loads((ctx / "sampletypes_db.json").read_text()) == [
        {"SampleType": "ZZZ"}]
    prov = json.loads((ctx / "PROVENANCE.json").read_text())
    assert prov["entries"]["context/sampletypes_db.json"]["commit_sha"] == "cafe1234"


def test_sample_property_count_returns_an_int():
    """The 23-vs-85 gap is the headline signal; the tool must surface it."""
    assert isinstance(rc.sample_property_count(REPO / "context" / "neo4j_schema.json"), int)


def test_sample_property_count_tolerates_a_missing_file(tmp_path):
    assert rc.sample_property_count(tmp_path / "nope.json") == 0
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_refresh_context.py -v`
Expected: collection error, no `refresh_context` module.

- [ ] **Step 4: Write `scripts/refresh_context.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Refresh the plugin's bundled context/ snapshots, with provenance.

context/VINTAGE.json used to promise "Refresh via tools/refresh_context.py
(planned, not yet implemented)" while tools/ did not exist. Meanwhile
context/neo4j_schema.json was byte-identical to chat_nextseek's DEV-instance
snapshot from 2026-03-26, carrying 23 Sample properties where the live copy had
85. Every mode reasons about the graph from these files.

This script copies a set of managed files from a source export directory into
context/, records provenance for each, and refuses to write without --write.

Usage:
  uv run --script scripts/refresh_context.py --check
  uv run --script scripts/refresh_context.py --from-dir <DIR>
  uv run --script scripts/refresh_context.py --from-dir <DIR> --write
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"

# Files this script manages. Anything not listed is hand-maintained and is left
# alone even if it appears in the source directory.
MANAGED_FILES = [
    "sampletypes_db.json",
    "assays_db.json",
    "projects_db.json",
    "neo4j_schema.json",
    "neo4j_assay-sample-conn.json",
]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sample_property_count(schema_path: Path) -> int:
    """Number of properties on the Sample label. The 23-vs-85 staleness signal.

    Tolerant of shape: tries a few plausible key paths and returns 0 rather than
    raising on an export whose layout changed.
    """
    try:
        doc = json.loads(Path(schema_path).read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    for key in ("labels", "nodes", "node_properties", "schema"):
        container = doc.get(key)
        if isinstance(container, dict) and hasattr(container.get("Sample"), "__len__"):
            return len(container["Sample"])
    sample = doc.get("Sample")
    return len(sample) if hasattr(sample, "__len__") else 0


def edge_count(conn_path: Path) -> int:
    try:
        doc = json.loads(Path(conn_path).read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    conns = doc.get("connections", doc) if isinstance(doc, dict) else doc
    return len(conns) if hasattr(conns, "__len__") else 0


def provenance_entry(*, source_repo: str, source_path: str,
                     commit_sha: str | None, vendored_date: str,
                     local_divergence: str, sha256: str | None = None) -> dict:
    """One PROVENANCE.json record. Every vendored file gets exactly one.

    Rationale: sampletypes_db.json already exists in three copies at three
    vintages with no record of which is authoritative. Do not add a fourth
    instance of that problem.
    """
    entry = {
        "source_repo": source_repo,
        "source_path": source_path,
        "commit_sha": commit_sha,
        "vendored_date": vendored_date,
        "local_divergence": local_divergence,
    }
    if sha256 is not None:
        entry["sha256"] = sha256
    return entry


def read_provenance() -> dict:
    p = CONTEXT_DIR / "PROVENANCE.json"
    if not p.is_file():
        return {"description": "", "entries": {}}
    return json.loads(p.read_text())


def write_provenance(doc: dict) -> Path:
    p = CONTEXT_DIR / "PROVENANCE.json"
    doc["entries"] = {k: doc["entries"][k] for k in sorted(doc["entries"])}
    p.write_text(json.dumps(doc, indent=2) + "\n")
    return p


def _git_sha(directory: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def check() -> int:
    """Report staleness signals without touching anything. Returns 1 if stale."""
    print(f"Context dir: {CONTEXT_DIR}")
    vintage_path = CONTEXT_DIR / "VINTAGE.json"
    if vintage_path.is_file():
        v = json.loads(vintage_path.read_text())
        print(f"Bundled date: {v.get('bundled_date')}")
        print(f"Instance:     {json.dumps(v.get('instance', {}))}")
    prov = read_provenance()
    stale = False
    print()
    for name in MANAGED_FILES:
        p = CONTEXT_DIR / name
        entry = prov["entries"].get(f"context/{name}")
        if not p.is_file():
            print(f"  MISSING  {name}")
            stale = True
            continue
        digest = sha256_of(p)
        note = ""
        if entry is None:
            note = "  (no provenance entry)"
            stale = True
        elif entry.get("sha256") and entry["sha256"] != digest:
            note = "  (diverged from recorded sha256)"
        print(f"  ok       {name:<34} {digest[:12]}{note}")
    print()
    n = sample_property_count(CONTEXT_DIR / "neo4j_schema.json")
    e = edge_count(CONTEXT_DIR / "neo4j_assay-sample-conn.json")
    print(f"Sample properties in neo4j_schema.json: {n}")
    print(f"Edges in neo4j_assay-sample-conn.json:  {e}")
    if n and n < 50:
        print("  WARNING: a DEV-instance snapshot carries ~23 Sample properties; "
              "a live one carries ~85. This looks like the dev snapshot.")
        stale = True
    return 1 if stale else 0


def refresh(from_dir: Path, *, write: bool, commit_sha: str | None = None,
            today: str | None = None) -> int:
    from_dir = Path(from_dir)
    today = today or datetime.date.today().isoformat()
    commit_sha = commit_sha if commit_sha is not None else _git_sha(from_dir)
    prov = read_provenance()
    changed = []

    for name in MANAGED_FILES:
        src = from_dir / name
        dst = CONTEXT_DIR / name
        if not src.is_file():
            print(f"  -  {name:<34} not in source dir, leaving as-is")
            continue
        src_digest = sha256_of(src)
        dst_digest = sha256_of(dst) if dst.is_file() else None
        if src_digest == dst_digest:
            print(f"  =  {name:<34} unchanged")
            continue
        changed.append(name)
        if write:
            dst.write_bytes(src.read_bytes())
            prov["entries"][f"context/{name}"] = provenance_entry(
                source_repo=from_dir.parent.name or str(from_dir),
                source_path=str(src),
                commit_sha=commit_sha,
                vendored_date=today,
                local_divergence="none",
                sha256=src_digest,
            )
            print(f"  ok {name:<34} updated -> {src_digest[:12]}")
        else:
            print(f"  ~  {name:<34} would update "
                  f"{(dst_digest or 'absent')[:12]} -> {src_digest[:12]}")

    if not changed:
        print("\nNothing to do; every managed file already matches the source.")
        return 0
    if write:
        write_provenance(prov)
        print(f"\nUpdated {len(changed)} file(s) and recorded provenance "
              f"(commit {commit_sha}).")
        print("Now update context/VINTAGE.json bundled_date and instance by hand.")
    else:
        print(f"\ndry-run: {len(changed)} file(s) would change. "
              f"Re-run with --write to apply.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-dir", type=Path, default=None,
                    help="Directory holding fresh exports of the managed files")
    ap.add_argument("--check", action="store_true",
                    help="Report staleness and provenance gaps; write nothing")
    ap.add_argument("--write", action="store_true",
                    help="Apply the refresh; default is dry-run.")
    args = ap.parse_args(argv)
    if args.check or args.from_dir is None:
        return check()
    return refresh(args.from_dir, write=args.write)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run `--check` and capture the current state**

Run: `uv run --script scripts/refresh_context.py --check`

Expected: exit 1, with the dev-snapshot warning if the Sample property count is ~23.

- [ ] **Step 6: Preview the refresh, diff, then apply**

```bash
uv run --script scripts/refresh_context.py \
    --from-dir /home/cdemu/code/chat_nextseek/src/chat_nextseek/context
```

For every file the dry-run says would change, diff it before writing:

```bash
uv run python3 - <<'PY'
import json, pathlib, difflib
a = pathlib.Path('context/neo4j_schema.json')
b = pathlib.Path('/home/cdemu/code/chat_nextseek/src/chat_nextseek/context/neo4j_schema.json')
norm = lambda p: json.dumps(json.loads(p.read_text()), sort_keys=True, indent=1).splitlines()
for line in list(difflib.unified_diff(norm(a), norm(b), 'bundled', 'source'))[:60]:
    print(line)
PY
```

Then apply:

```bash
uv run --script scripts/refresh_context.py \
    --from-dir /home/cdemu/code/chat_nextseek/src/chat_nextseek/context --write
```

**If the source directory does not exist or does not hold these filenames, stop and report.** Do not invent a source. The `--check` output alone is a deliverable: it makes the staleness visible and machine-checkable, which is a strict improvement over a VINTAGE note pointing at a nonexistent tool.

- [ ] **Step 7: Rewrite `context/VINTAGE.json`**

Fill `bundled_date` with today and `instance` with what the refresh actually pulled:

```json
{
  "bundled_date": "2026-07-21",
  "bundled_date_meaning": "Date these snapshots were assembled into the dmac-curation plugin. Per-file provenance, including source commit and sha256, is in context/PROVENANCE.json.",
  "source": "chat_nextseek context exports",
  "instance": {
    "neo4j_schema.json": "PRODUCTION (nextseek.mit.edu). The 2026-05-27 bundle carried a DEV snapshot with 23 Sample properties; the live schema has 85.",
    "neo4j_assay-sample-conn.json": "PRODUCTION",
    "sampletypes_db.json": "PRODUCTION",
    "assays_db.json": "PRODUCTION",
    "projects_db.json": "PRODUCTION"
  },
  "files": {
    "sampletypes_db.json": "sample type catalog",
    "assays_db.json": "assay catalog",
    "projects_db.json": "project catalog",
    "neo4j_schema.json": "Neo4j labels and relationships",
    "neo4j_assay-sample-conn.json": "allowed (assay, parent_type, child_type) edges (wrapper has {fetched_at, connections})",
    "min_api_endpoints_enriched.json": "enriched API endpoint records",
    "NExtSEEK_API.yaml": "OpenAPI spec for nextseek.mit.edu",
    "fdh_api_index.json": "FairDomHub API intent index with yaml_lines back-pointers",
    "full-fdh-openapi-spec.yaml": "FairDomHub OpenAPI spec (640KB; never read whole, use the index)"
  },
  "refresh": "uv run --script scripts/refresh_context.py --check   (report staleness)   |   uv run --script scripts/refresh_context.py --from-dir <DIR> --write   (apply)",
  "note": "Each curation project's lockfile records which bundled_date was used at /curate-init. NExtSEEK_API.yaml is NOT auto-refreshed; its claim that the flat upload format lacks ontology support is dated 2026-05-27 and must be confirmed with the API owner before anything new is designed around it."
}
```

- [ ] **Step 8: Seed `context/PROVENANCE.json` if the refresh did not create it**

```json
{
  "description": "Provenance for every vendored file in this plugin: source repo, source path, commit SHA, vendoring date, local divergence, and sha256. sampletypes_db.json already existed in three copies at three vintages with no record of which was authoritative; this file exists so that never happens again. Managed context files are updated by scripts/refresh_context.py --write; vendored report assets are recorded by hand when added.",
  "entries": {}
}
```

- [ ] **Step 9: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_refresh_context.py -v`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add scripts/refresh_context.py context/ tests/test_refresh_context.py
git commit -m "feat(context): real refresh path plus per-file provenance

VINTAGE.json promised 'Refresh via tools/refresh_context.py (planned, not yet
implemented)' and tools/ did not exist, while the bundled neo4j_schema.json was
a DEV-instance snapshot with 23 Sample properties against a live 85. Every mode
reasons about the graph from these files.

scripts/refresh_context.py --check surfaces the staleness signals (Sample
property count, edge count, provenance gaps) and exits 1 when stale; --from-dir
DIR --write applies a refresh and records source repo, path, commit SHA, date
and sha256 per file in context/PROVENANCE.json. Defaults to dry-run per the
write-safety convention.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage F — `schema` mode

Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

**Verified against `context/sampletypes_db.json` before planning:** 101 sample types; 1059 distinct field names across `Required Metadata` + `Standard Metadata` + `Possible Metadata Fields`; **856 used by exactly one type**; none carrying a description, datatype or vocabulary. `D.VIA` has 6 required / 4 standard / 5 possible = 15 fields, `Clade` = `Raw`, `Associated Assay Parents` = `Cell Viability Assay`, `Parent_SampleTypes` = `CEL`, and its `Tags` reads exactly:

```
viability data, cell viability, cytotoxicity data, MTS assay, MTT assay, WST-1,
live/dead assay, CellTiter-Glo, proliferation assay, cell death data
```

Catalog record keys, for reference in every task below:

```
ID, SampleType, Name, Description, Tags, Required Metadata, Standard Metadata,
Possible Metadata Fields, Clade, SampleType File Link, Associated Assay Parents,
Associated Assay Children, Parent_SampleTypes, Child_SampleTypes
```

### Task 19: Field index and reuse check

**Files:**
- Create: `scripts/schema/__init__.py` (empty)
- Create: `scripts/schema/field_index.py`
- Test: `tests/test_field_index.py`

**Interfaces:**
- Consumes: `_config.plugin_context` from Task 7
- Produces:
  - `FIELD_SOURCES = ("Required Metadata", "Standard Metadata", "Possible Metadata Fields")`
  - `@dataclass FieldUsage`: `name: str`, `used_by: list[str]`, `count: int`
  - `load_catalog(path=None) -> list[dict]`
  - `build_field_index(types) -> dict[str, FieldUsage]`
  - `normalize_field_name(name) -> str`
  - `@dataclass Candidate`: `name`, `usage_count`, `used_by`, `match_pass`, `example_values`
  - `rank_candidates(candidate, index, *, clade=None, assay=None, catalog=None, dictionary=None, limit=10) -> list[Candidate]`
  - `mine_tags(record) -> list[str]`
  - `type_record(catalog, sampletype) -> dict`
  - `siblings_in_clade(catalog, sampletype) -> list[dict]`

**Context (schema spec):** the problem is that there is no way for an author to answer "does a field for this already exist?", so new near-duplicates get minted by default. **A field name shared across types is not a defect** — `Type` appears on many sample types and legitimately means different things on each. The mode records what it means *here*; it never proposes a rename or a split.

- [ ] **Step 1: Write the failing test**

Create `tests/test_field_index.py`:

```python
"""Field index and reuse check over the 1059-name sample type catalog."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import field_index as fi  # noqa: E402

CATALOG = [
    {"SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
     "Tags": "viability data, MTS assay, MTT assay, WST-1, CellTiter-Glo",
     "Required Metadata": "UID, Scientist, Parent",
     "Standard Metadata": "Protocol, CellLine, Type",
     "Possible Metadata Fields": "Notes",
     "Associated Assay Parents": "Cell Viability Assay",
     "Parent_SampleTypes": "CEL"},
    {"SampleType": "D.FLOW", "Name": "Flow Data", "Clade": "Raw",
     "Tags": "flow cytometry",
     "Required Metadata": "UID, Scientist, Parent",
     "Standard Metadata": "Protocol, Instrument",
     "Possible Metadata Fields": "Notes, Timepoint",
     "Associated Assay Parents": "Flow Cytometry",
     "Parent_SampleTypes": "CEL"},
    {"SampleType": "MUS", "Name": "Mouse", "Clade": "Organism",
     "Tags": "mouse",
     "Required Metadata": "UID, Scientist",
     "Standard Metadata": "Strain",
     "Possible Metadata Fields": "Notes",
     "Associated Assay Parents": "", "Parent_SampleTypes": ""},
]


def test_load_catalog_reads_the_bundled_file():
    types = fi.load_catalog()
    assert len(types) == 101
    assert all("SampleType" in t for t in types)


def test_build_field_index_counts_usage():
    idx = fi.build_field_index(CATALOG)
    assert idx["UID"].count == 3
    assert sorted(idx["Notes"].used_by) == ["D.FLOW", "D.VIA", "MUS"]
    assert idx["Instrument"].count == 1
    assert idx["Instrument"].used_by == ["D.FLOW"]


def test_build_field_index_covers_all_three_sources():
    idx = fi.build_field_index(CATALOG)
    assert "Scientist" in idx      # Required
    assert "Protocol" in idx       # Standard
    assert "Timepoint" in idx      # Possible


def test_real_catalog_shape_matches_the_spec():
    """Guards the numbers the schema spec reasons from."""
    idx = fi.build_field_index(fi.load_catalog())
    assert len(idx) == 1059
    singletons = [f for f in idx.values() if f.count == 1]
    assert len(singletons) == 856
    assert idx["UID"].count == 101


def test_normalize_field_name_handles_case_underscores_and_plurals():
    assert fi.normalize_field_name("Cell_Line") == "cellline"
    assert fi.normalize_field_name("cellLine") == "cellline"
    assert fi.normalize_field_name("Instruments") == "instrument"
    assert fi.normalize_field_name(" Timepoint ") == "timepoint"


def test_normalize_does_not_over_singularize():
    """'Status' must not become 'Statu'."""
    assert fi.normalize_field_name("Status") == "status"
    assert fi.normalize_field_name("Analysis") == "analysis"


def test_rank_candidates_finds_an_exact_match_first():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("Instrument", idx)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "exact"


def test_rank_candidates_finds_a_normalized_match():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("instruments", idx)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "normalized"


def test_rank_candidates_finds_a_synonym_from_the_dictionary():
    idx = fi.build_field_index(CATALOG)
    dictionary = {"Instrument": {"synonyms": ["PlateReader", "Analyzer"]}}
    out = fi.rank_candidates("PlateReader", idx, dictionary=dictionary)
    assert out[0].name == "Instrument"
    assert out[0].match_pass == "synonym"


def test_rank_candidates_does_not_force_match_a_genuinely_novel_name():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("HydrogelStiffnessKPa", idx)
    assert all(c.match_pass != "exact" for c in out)
    assert not out or out[0].name != "HydrogelStiffnessKPa"


def test_rank_candidates_prefers_higher_usage_within_a_pass():
    idx = fi.build_field_index(CATALOG)
    out = fi.rank_candidates("Note", idx)
    names = [c.name for c in out]
    assert "Notes" in names


def test_rank_candidates_boosts_same_clade():
    idx = fi.build_field_index(CATALOG)
    with_clade = fi.rank_candidates("Instrument", idx, clade="Raw",
                                    catalog=CATALOG)
    assert with_clade[0].name == "Instrument"
    assert "D.FLOW" in with_clade[0].used_by


def test_rank_candidates_respects_limit():
    idx = fi.build_field_index(fi.load_catalog())
    assert len(fi.rank_candidates("Type", idx, limit=3)) <= 3


def test_a_name_on_many_types_is_not_flagged_as_a_defect():
    """schema spec / user correction: `Type` meaning different things on
    different sample types is fine, not a homonym problem."""
    idx = fi.build_field_index(fi.load_catalog())
    assert idx["Type"].count > 1
    assert not hasattr(fi, "split_homonyms")
    assert not hasattr(fi, "propose_rename")


def test_mine_tags_splits_the_tags_column():
    assert fi.mine_tags(CATALOG[0]) == [
        "viability data", "MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"]


def test_mine_tags_on_real_dvia_yields_the_assay_vocabulary():
    rec = fi.type_record(fi.load_catalog(), "D.VIA")
    tags = fi.mine_tags(rec)
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in tags


def test_mine_tags_on_a_type_with_no_tags_returns_empty():
    assert fi.mine_tags({"SampleType": "X"}) == []


def test_type_record_raises_on_unknown_type():
    with pytest.raises(KeyError):
        fi.type_record(CATALOG, "NOPE")


def test_siblings_in_clade_excludes_the_type_itself():
    sibs = fi.siblings_in_clade(CATALOG, "D.VIA")
    assert [s["SampleType"] for s in sibs] == ["D.FLOW"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_field_index.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'schema'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/schema/__init__.py` (empty file), then `scripts/schema/field_index.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Field index and reuse check over the NExtSEEK sample type catalog.

The problem this attacks: of 1059 distinct field names across 101 sample types,
856 are used by exactly one type, and none of the 1059 carries a description,
datatype or vocabulary anywhere. There is no way for an author to answer "does a
field for this already exist?", so new near-duplicates get minted by default.

What this module deliberately does NOT do: propose renames or splits. A field
name shared across sample types is not a defect. `Type` appears on many types
and legitimately means different things on each. This module records what a
field means *here*; deciding that two usages are "really" the same is a
curation judgment a human makes.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import plugin_context  # noqa: E402

FIELD_SOURCES = ("Required Metadata", "Standard Metadata", "Possible Metadata Fields")

# Suffixes that are safe to strip when normalizing. "Status" -> "Statu" and
# "Analysis" -> "Analysi" are the failure modes this guards against.
_PLURAL_EXCEPTIONS = {"status", "analysis", "series", "species", "apparatus"}


@dataclass
class FieldUsage:
    """Where one field name appears across the catalog."""

    name: str
    used_by: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.used_by)


@dataclass
class Candidate:
    """A reuse-check hit, ranked. The curator judges; the tool never decides."""

    name: str
    usage_count: int
    used_by: list[str]
    match_pass: str          # exact | normalized | synonym | semantic
    example_values: list[str] = field(default_factory=list)
    score: float = 0.0


def load_catalog(path: Path | None = None) -> list[dict]:
    """Read `sampletypes_db.json`. Defaults to the plugin's read-only copy."""
    return json.loads(Path(path or plugin_context("sampletypes_db.json")).read_text())


def type_record(catalog: list[dict], sampletype: str) -> dict:
    for t in catalog:
        if t.get("SampleType") == sampletype:
            return t
    raise KeyError(f"SampleType {sampletype!r} not in catalog")


def siblings_in_clade(catalog: list[dict], sampletype: str) -> list[dict]:
    """Other types sharing this type's Clade. Their fields are the best prior."""
    rec = type_record(catalog, sampletype)
    clade = rec.get("Clade")
    if not clade:
        return []
    return [t for t in catalog
            if t.get("Clade") == clade and t.get("SampleType") != sampletype]


def _split_list(value) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def build_field_index(types: list[dict]) -> dict[str, FieldUsage]:
    """Map every declared field name to the sample types that declare it."""
    index: dict[str, FieldUsage] = {}
    for t in types:
        code = t.get("SampleType")
        for source in FIELD_SOURCES:
            for name in _split_list(t.get(source)):
                usage = index.setdefault(name, FieldUsage(name=name))
                if code not in usage.used_by:
                    usage.used_by.append(code)
    return index


def normalize_field_name(name: str) -> str:
    """Fold case, underscores, hyphens, spaces and a trailing plural.

    Used only for the *normalized* matching pass. The original spelling is
    always what gets reported back.
    """
    folded = "".join(ch for ch in name.strip().lower() if ch.isalnum())
    if folded in _PLURAL_EXCEPTIONS:
        return folded
    if folded.endswith("ies") and len(folded) > 4:
        return folded[:-3] + "y"
    if folded.endswith("s") and not folded.endswith("ss") and len(folded) > 3:
        return folded[:-1]
    return folded


def _observed_values(name: str, dictionary: dict | None) -> list[str]:
    if not dictionary:
        return []
    return list((dictionary.get(name) or {}).get("observed_values") or [])


def rank_candidates(
    candidate: str,
    index: dict[str, FieldUsage],
    *,
    clade: str | None = None,
    assay: str | None = None,
    catalog: list[dict] | None = None,
    dictionary: dict | None = None,
    limit: int = 10,
) -> list[Candidate]:
    """Ranked existing field names that might already cover `candidate`.

    Never a yes/no. Passes, in order of confidence:
      1. exact name
      2. normalized name (case, separators, plural)
      3. synonym match against dictionary entries
      4. semantic match over shared word stems

    Ranked within a pass by usage count, then clade proximity, then assay
    proximity. The curator is shown the name, how many types use it, which ones,
    and example values, and then judges.
    """
    target_norm = normalize_field_name(candidate)
    clade_types: set[str] = set()
    assay_types: set[str] = set()
    if catalog:
        if clade:
            clade_types = {t["SampleType"] for t in catalog
                           if t.get("Clade") == clade}
        if assay:
            assay_types = {t["SampleType"] for t in catalog
                           if assay in (t.get("Associated Assay Parents") or "")}

    synonym_of: dict[str, str] = {}
    for canonical, entry in (dictionary or {}).items():
        for syn in (entry or {}).get("synonyms") or []:
            synonym_of[normalize_field_name(syn)] = canonical

    pass_weight = {"exact": 1000.0, "normalized": 500.0,
                   "synonym": 400.0, "semantic": 100.0}
    target_words = _words(candidate)

    out: list[Candidate] = []
    for name, usage in index.items():
        norm = normalize_field_name(name)
        if name == candidate:
            match = "exact"
        elif norm == target_norm:
            match = "normalized"
        elif synonym_of.get(target_norm) == name:
            match = "synonym"
        elif target_words and target_words & _words(name):
            match = "semantic"
        else:
            continue

        score = pass_weight[match] + float(usage.count)
        if clade_types & set(usage.used_by):
            score += 25.0
        if assay_types & set(usage.used_by):
            score += 15.0
        out.append(Candidate(
            name=name,
            usage_count=usage.count,
            used_by=list(usage.used_by),
            match_pass=match,
            example_values=_observed_values(name, dictionary),
            score=score,
        ))

    out.sort(key=lambda c: (-c.score, c.name))
    return out[:limit]


def _words(name: str) -> set[str]:
    """CamelCase / underscore / space split into lowercase word stems."""
    buf, words = "", []
    for ch in name.replace("_", " ").replace("-", " "):
        if ch.isupper() and buf and not buf[-1].isupper():
            words.append(buf)
            buf = ch
        elif ch == " ":
            if buf:
                words.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        words.append(buf)
    return {normalize_field_name(w) for w in words if len(w) > 2}


def mine_tags(record: dict) -> list[str]:
    """Candidate controlled values already written down in the Tags column.

    The cheapest win available. D.VIA's Tags read 'viability data, cell
    viability, cytotoxicity data, MTS assay, MTT assay, WST-1, live/dead assay,
    CellTiter-Glo, proliferation assay, cell death data' - permissible values
    for its `Type` field, sitting in prose where nothing can enforce them.
    """
    return _split_list(record.get("Tags"))
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_field_index.py -v`
Expected: all pass. If `test_real_catalog_shape_matches_the_spec` fails on the counts, **do not change the test to match** — Task 18 may have refreshed the catalog. Re-measure with the Step 1 probe from Task 18, update the two literals, and note the change in the commit message.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/ tests/test_field_index.py
git commit -m "feat(schema): field index and reuse check over the type catalog

Of 1059 distinct field names across 101 sample types, 856 are used by exactly
one type and none carries a description, datatype or vocabulary. There was no
way to answer 'does a field for this already exist?', so near-duplicates got
minted by default.

rank_candidates() returns ranked candidates across four passes (exact,
normalized, synonym, semantic), weighted by usage count and boosted for clade
and assay proximity. It never returns a yes/no and never proposes a rename or a
split: a name shared across types is not a defect.

mine_tags() extracts the controlled vocabulary already sitting in the Tags
column as prose.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 20: Observed-value mining and the field dictionary

**Files:**
- Create: `scripts/schema/dictionary.py`
- Test: `tests/test_schema_dictionary.py`

**Interfaces:**
- Consumes: `field_index.FieldUsage`, `field_index.build_field_index`, `field_index.mine_tags`, `field_index.load_catalog` from Task 19
- Produces:
  - `DICTIONARY_NAME = "field_dictionary.json"`
  - `observe_values(workbooks: list[Path], fields: set[str]) -> dict[str, list[str]]`
  - `build_entry(name, usage, observed, tags_source=None, ontology=None) -> dict`
  - `merge_dictionary(existing: dict, new: dict) -> dict`
  - `load_dictionary(root: Path) -> dict` / `save_dictionary(root: Path, doc: dict) -> Path`

**Context (schema spec, decision ANN-5):** the dictionary is **lazy and cwd-only**. No pre-built dictionary ships, and none is generated for all 1059 names — each run creates entries only for the fields it touched. Accepted consequence: enrichment does not accumulate across projects. Accepted benefit: it ships no state that can go stale, which the plugin already has problems with.

Entry shape, verbatim from the spec:

```json
"Instrument": {
  "description": "...",
  "datatype": "string",
  "used_by": ["D.VIA", "D.FLOW", "..."],
  "observed_values": ["BioTek Synergy H1", "..."],
  "ontology": {"iri": "...", "label": "...", "source": "NCIT", "confirmed": false},
  "synonyms": ["PlateReader", "Analyzer"],
  "provenance": "16 existing usages + 3 observed values in previous_metadata"
}
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_dictionary.py`:

```python
"""The lazy, cwd-only field dictionary (schema spec)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import dictionary as sd  # noqa: E402
from schema import field_index as fi  # noqa: E402


def _workbook(path: Path, sheet: str, headers: list[str], rows: list[list]):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_observe_values_collects_distinct_values(tmp_path):
    wb = tmp_path / "master.xlsx"
    _workbook(wb, "D.VIA", ["UID", "Instrument", "Timepoint"],
              [["A-1", "BioTek Synergy H1", "24h"],
               ["A-2", "BioTek Synergy H1", "48h"],
               ["A-3", "Tecan Spark", "24h"]])
    out = sd.observe_values([wb], {"Instrument", "Timepoint"})
    assert out["Instrument"] == ["BioTek Synergy H1", "Tecan Spark"]
    assert out["Timepoint"] == ["24h", "48h"]


def test_observe_values_ignores_fields_not_asked_for(tmp_path):
    wb = tmp_path / "m.xlsx"
    _workbook(wb, "S", ["UID", "Instrument"], [["A-1", "X"]])
    assert "UID" not in sd.observe_values([wb], {"Instrument"})


def test_observe_values_skips_blanks_and_placeholders(tmp_path):
    wb = tmp_path / "m.xlsx"
    _workbook(wb, "S", ["Instrument"],
              [["BioTek"], [None], [""], ["*** PLACEHOLDER: unknown ***"]])
    assert sd.observe_values([wb], {"Instrument"}) == {"Instrument": ["BioTek"]}


def test_observe_values_reads_every_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb_path = tmp_path / "m.xlsx"
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "D.VIA"
    a.append(["Instrument"])
    a.append(["BioTek"])
    b = wb.create_sheet("D.FLOW")
    b.append(["Instrument"])
    b.append(["Cytek"])
    wb.save(wb_path)
    assert sd.observe_values([wb_path], {"Instrument"}) == {
        "Instrument": ["BioTek", "Cytek"]}


def test_observe_values_on_no_workbooks_returns_empty():
    assert sd.observe_values([], {"Instrument"}) == {}


def test_build_entry_shape():
    usage = fi.FieldUsage(name="Instrument", used_by=["D.VIA", "D.FLOW"])
    e = sd.build_entry("Instrument", usage,
                       observed=["BioTek Synergy H1"],
                       description="Plate reader or analyzer used")
    assert e["used_by"] == ["D.VIA", "D.FLOW"]
    assert e["observed_values"] == ["BioTek Synergy H1"]
    assert e["datatype"] == "string"
    assert e["ontology"] is None
    assert "2 existing usages" in e["provenance"]
    assert "1 observed value" in e["provenance"]


def test_build_entry_ontology_is_always_unconfirmed():
    """schema spec: only a human flips confirmed. The MUS prototype bound
    Strain to NCBITaxon_10090, which is wrong -- NCBITaxon covers species, not
    laboratory strains like C57BL/6J."""
    usage = fi.FieldUsage(name="Strain", used_by=["MUS"])
    e = sd.build_entry("Strain", usage, observed=[],
                       ontology={"iri": "http://purl.obolibrary.org/obo/NCBITaxon_10090",
                                 "label": "Mus musculus", "source": "NCBITaxon"})
    assert e["ontology"]["confirmed"] is False


def test_build_entry_rejects_a_preconfirmed_ontology():
    usage = fi.FieldUsage(name="Strain", used_by=["MUS"])
    e = sd.build_entry("Strain", usage, observed=[],
                       ontology={"iri": "x", "label": "y", "source": "z",
                                 "confirmed": True})
    assert e["ontology"]["confirmed"] is False


def test_merge_dictionary_adds_new_entries():
    merged = sd.merge_dictionary({"A": {"observed_values": ["1"]}},
                                 {"B": {"observed_values": ["2"]}})
    assert set(merged) == {"A", "B"}


def test_merge_dictionary_unions_observed_values():
    merged = sd.merge_dictionary(
        {"A": {"observed_values": ["1", "2"], "used_by": ["X"]}},
        {"A": {"observed_values": ["2", "3"], "used_by": ["X", "Y"]}})
    assert merged["A"]["observed_values"] == ["1", "2", "3"]
    assert merged["A"]["used_by"] == ["X", "Y"]


def test_merge_dictionary_never_downgrades_a_confirmed_ontology():
    """A human confirmed it. A later automated run must not un-confirm it."""
    existing = {"A": {"ontology": {"iri": "i", "label": "l", "source": "s",
                                   "confirmed": True}}}
    new = {"A": {"ontology": {"iri": "i", "label": "l", "source": "s",
                              "confirmed": False}}}
    assert sd.merge_dictionary(existing, new)["A"]["ontology"]["confirmed"] is True


def test_merge_dictionary_keeps_a_human_written_description():
    existing = {"A": {"description": "written by a curator"}}
    new = {"A": {"description": ""}}
    assert sd.merge_dictionary(existing, new)["A"]["description"] == "written by a curator"


def test_dictionary_round_trips_through_disk(tmp_path):
    doc = {"Instrument": {"observed_values": ["BioTek"]}}
    sd.save_dictionary(tmp_path, doc)
    assert sd.load_dictionary(tmp_path) == doc


def test_load_dictionary_on_absent_file_returns_empty(tmp_path):
    assert sd.load_dictionary(tmp_path) == {}


def test_dictionary_is_written_to_cwd_not_the_plugin(tmp_path, plugin_sentinel):
    sd.save_dictionary(tmp_path, {"A": {}})
    assert (tmp_path / "schema" / sd.DICTIONARY_NAME).is_file()


def test_no_prebuilt_dictionary_ships_with_the_plugin():
    """schema spec: lazy and cwd-only. Shipping one would repeat the
    three-copies-of-context problem."""
    assert not (REPO / "context" / "field_dictionary.json").exists()
    assert not (REPO / "schema").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_schema_dictionary.py -v`
Expected: `ImportError: cannot import name 'dictionary' from 'schema'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/schema/dictionary.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""The lazy, cwd-only field dictionary.

No pre-built dictionary ships with the plugin, and none is generated for all
1059 field names. Each run creates entries only for the fields it touched, in
the current working directory.

Why lazy: the plugin already has a three-copies-of-context problem
(sampletypes_db.json exists in three places at three vintages). Shipping another
data file that drifts would repeat it. Lazy ships no state - nothing to version,
refresh, or go stale.

Accepted consequence: enrichment does not accumulate across projects. Ontology
IRIs curated while bolstering D.VIA in one directory do not help the next
curator elsewhere. The read-only inputs are shared; the enrichment is not.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook

DICTIONARY_NAME = "field_dictionary.json"
OUTPUT_SUBDIR = "schema"

# Values that are markers, not data. Never recorded as observed vocabulary.
_NON_VALUES = ("*** PLACEHOLDER", "***PLACEHOLDER")


def observe_values(workbooks: list[Path], fields: set[str]) -> dict[str, list[str]]:
    """Distinct real values for `fields`, across every sheet of every workbook.

    Real observed values beat guessed ones (SKILL.md hard rule 4: schema lies,
    workbook tells truth). Order is first-seen, deduped, so a report reads the
    way the data does.
    """
    out: dict[str, list[str]] = {}
    for path in workbooks:
        path = Path(path)
        if not path.is_file():
            continue
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in wb.sheetnames:
                rows = wb[sheet].iter_rows(values_only=True)
                header = next(rows, None)
                if not header:
                    continue
                wanted = {i: str(h).strip() for i, h in enumerate(header)
                          if h and str(h).strip() in fields}
                if not wanted:
                    continue
                for row in rows:
                    for i, name in wanted.items():
                        if i >= len(row):
                            continue
                        value = row[i]
                        if value is None:
                            continue
                        text = str(value).strip()
                        if not text or any(m in text for m in _NON_VALUES):
                            continue
                        bucket = out.setdefault(name, [])
                        if text not in bucket:
                            bucket.append(text)
        finally:
            wb.close()
    return out


def build_entry(name, usage, observed: list[str], *, description: str = "",
                datatype: str = "string", synonyms: list[str] | None = None,
                ontology: dict | None = None,
                extra_provenance: str = "") -> dict:
    """One dictionary entry.

    `ontology` is always emitted with ``"confirmed": false``, whatever the
    caller passed. Only a human flips it, and this function is not a human.
    In the MUS prototype `Strain` was bound to NCBITaxon_10090, which is wrong -
    NCBITaxon covers species, not laboratory strains like C57BL/6J - and it was
    plausible enough to pass unreviewed.
    """
    if ontology is not None:
        ontology = dict(ontology)
        ontology["confirmed"] = False

    n_usage = len(getattr(usage, "used_by", []) or [])
    n_obs = len(observed)
    parts = [f"{n_usage} existing usage{'s' if n_usage != 1 else ''}"]
    parts.append(f"{n_obs} observed value{'s' if n_obs != 1 else ''}")
    if extra_provenance:
        parts.append(extra_provenance)

    return {
        "description": description,
        "datatype": datatype,
        "used_by": list(getattr(usage, "used_by", []) or []),
        "observed_values": list(observed),
        "ontology": ontology,
        "synonyms": list(synonyms or []),
        "provenance": " + ".join(parts),
    }


def merge_dictionary(existing: dict, new: dict) -> dict:
    """Merge a run's entries into a dictionary already on disk.

    Rules that matter:
      - observed_values and used_by are unioned, preserving first-seen order
      - a human-confirmed ontology binding is NEVER downgraded by an automated run
      - a non-empty human description is never replaced by an empty one
    """
    merged = {k: dict(v) for k, v in existing.items()}
    for name, entry in new.items():
        if name not in merged:
            merged[name] = dict(entry)
            continue
        old = merged[name]
        for list_key in ("observed_values", "used_by", "synonyms"):
            combined = list(old.get(list_key) or [])
            for v in entry.get(list_key) or []:
                if v not in combined:
                    combined.append(v)
            old[list_key] = combined
        if entry.get("description"):
            old["description"] = entry["description"]
        if entry.get("datatype"):
            old["datatype"] = entry["datatype"]
        old_ont, new_ont = old.get("ontology"), entry.get("ontology")
        if old_ont and old_ont.get("confirmed"):
            pass  # a human confirmed it; leave it alone
        elif new_ont:
            old["ontology"] = new_ont
        if entry.get("provenance"):
            old["provenance"] = entry["provenance"]
    return merged


def dictionary_path(root: Path) -> Path:
    return Path(root) / OUTPUT_SUBDIR / DICTIONARY_NAME


def load_dictionary(root: Path) -> dict:
    p = dictionary_path(root)
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


def save_dictionary(root: Path, doc: dict) -> Path:
    p = dictionary_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return p
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_schema_dictionary.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/dictionary.py tests/test_schema_dictionary.py
git commit -m "feat(schema): lazy cwd-only field dictionary with observed-value mining

No pre-built dictionary ships and none is generated for all 1059 field names;
each run creates entries only for the fields it touched, in cwd. The plugin
already has a three-copies-of-context problem, and shipping another drifting
data file would repeat it.

observe_values() mines real values from previous_metadata workbooks (hard rule
4: schema lies, workbook tells truth), skipping placeholder markers.
build_entry() always emits ontology bindings as confirmed:false whatever the
caller passed, and merge_dictionary() never downgrades one a human confirmed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 21: Ontology artifact and its round trip into `write_4sheet_xlsx`

**Files:**
- Create: `scripts/schema/ontology.py`
- Test: `tests/test_schema_ontology.py`

**Interfaces:**
- Consumes: `field_index.mine_tags`, `field_index.type_record`, `field_index.load_catalog` from Task 19; `dictionary.observe_values` from Task 20; `_common.write_4sheet_xlsx` from Task 9
- Produces:
  - `@dataclass ProposedValue`: `value: str`, `source: str` (`tags` | `observed` | `bioportal` | `sibling`), `note: str`
  - `propose_values(record, field_name, *, observed=None, tags=None) -> list[ProposedValue]`
  - `to_ontology_json(proposals: dict[str, list[ProposedValue]]) -> dict[str, list[str]]`
  - `write_ontology_artifact(root, sampletype, proposals) -> Path`
  - `load_ontology_artifact(root, sampletype) -> dict[str, list[str]]`
  - `BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"`
  - `bioportal_available() -> bool`

**Context (pipeline review, implementation note ANN-20):** `_common.py` accepts `ontology: dict[str, list[str]] | None = None` and writes a real Ontology sheet. **No caller has ever passed it**; `curate-build.md` and `PHASES.md` never instruct it be populated; `consolidate_to_flat.py` never reads it. So NExtSEEK has a controlled-vocabulary mechanism, the plugin can already write it, and nothing populates or consumes it. This is schema mode's shortest path to value.

Per the batch-upload spec, the per-field *declaration* lives in the **Instructions** sheet and the *values* in the **Ontology** sheet:

```
| Field  | Database Field  | Field Type          | Ontology |
| Strain | M.Mice::Strain  | Controlled Ontology | Strain   |
```

Task 9 already made `write_4sheet_xlsx` emit that declaration for ontology-bearing fields.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_ontology.py`:

```python
"""schema mode's ontology artifact, and its round trip into the 4-sheet writer."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _common  # noqa: E402
from schema import field_index as fi  # noqa: E402
from schema import ontology as so  # noqa: E402

DVIA = {
    "SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
    "Tags": "viability data, MTS assay, MTT assay, WST-1, CellTiter-Glo",
    "Required Metadata": "UID, Scientist, Parent",
    "Standard Metadata": "Protocol, CellLine, Type",
    "Possible Metadata Fields": "Notes",
    "Associated Assay Parents": "Cell Viability Assay",
}


def test_propose_values_from_tags():
    out = so.propose_values(DVIA, "Type")
    values = [p.value for p in out]
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in values
    assert all(p.source == "tags" for p in out)


def test_propose_values_merges_observed_values():
    out = so.propose_values(DVIA, "Type", observed=["MTS assay", "alamarBlue"])
    by_value = {p.value: p for p in out}
    assert by_value["alamarBlue"].source == "observed"
    # A value present in BOTH is credited to the stronger source: observed.
    assert by_value["MTS assay"].source == "observed"


def test_propose_values_dedupes():
    out = so.propose_values(DVIA, "Type", observed=["MTS assay"])
    assert len(out) == len({p.value for p in out})


def test_propose_values_on_a_type_with_no_tags_and_no_observations():
    assert so.propose_values({"SampleType": "X"}, "Type") == []


def test_every_proposal_carries_its_source():
    for p in so.propose_values(DVIA, "Type", observed=["alamarBlue"]):
        assert p.source in {"tags", "observed", "bioportal", "sibling"}
        assert p.value


def test_to_ontology_json_is_the_write_4sheet_shape():
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    out = so.to_ontology_json(proposals)
    assert isinstance(out, dict)
    assert isinstance(out["Type"], list)
    assert all(isinstance(v, str) for v in out["Type"])


def test_ontology_artifact_round_trips_on_disk(tmp_path):
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    path = so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    assert path == tmp_path / "schema" / "D.VIA.ontology.json"
    assert so.load_ontology_artifact(tmp_path, "D.VIA")["Type"]


def test_artifact_records_the_source_of_every_value(tmp_path):
    """A bare value list cannot be judged; a list with sources can."""
    proposals = {"Type": so.propose_values(DVIA, "Type", observed=["alamarBlue"])}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    doc = json.loads((tmp_path / "schema" / "D.VIA.ontology.json").read_text())
    assert "_sources" in doc
    assert doc["_sources"]["Type"]["alamarBlue"] == "observed"


def test_load_ontology_artifact_strips_the_sources_block(tmp_path):
    """What feeds write_4sheet_xlsx must be exactly {field: [values]}."""
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    loaded = so.load_ontology_artifact(tmp_path, "D.VIA")
    assert "_sources" not in loaded


def test_load_ontology_artifact_missing_returns_empty(tmp_path):
    assert so.load_ontology_artifact(tmp_path, "NOPE") == {}


def test_artifact_feeds_write_4sheet_xlsx_end_to_end(tmp_path):
    """The dead capability, brought to life: schema mode -> Ontology sheet."""
    openpyxl = pytest.importorskip("openpyxl")
    proposals = {"Type": so.propose_values(DVIA, "Type")}
    so.write_ontology_artifact(tmp_path, "D.VIA", proposals)
    ontology = so.load_ontology_artifact(tmp_path, "D.VIA")

    out = tmp_path / "ArmA_D.VIA.xlsx"
    _common.write_4sheet_xlsx(
        out, "D.VIA",
        samples=[{"UID": "D.VIA-190903KAM-1", "Type": "MTS assay"}],
        assay_titles=["Cell Viability Assay"],
        ontology=ontology,
    )
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Instructions", "Samples", "Assay", "Ontology"]

    ont_rows = list(wb["Ontology"].iter_rows(values_only=True))
    assert ont_rows[0] == ("Field", "Value")
    assert ("Type", "MTS assay") in ont_rows

    instr = {r[0]: r for r in wb["Instructions"].iter_rows(values_only=True)}
    assert instr["Type"][1] == "D.VIA::Type"
    assert instr["Type"][2] == "Controlled Ontology"
    assert instr["Type"][3] == "Type"
    assert instr["UID"][2] == "Text"


def test_real_dvia_tags_yield_the_expected_value_set():
    rec = fi.type_record(fi.load_catalog(), "D.VIA")
    values = {p.value for p in so.propose_values(rec, "Type")}
    for expected in ("MTS assay", "MTT assay", "WST-1", "CellTiter-Glo"):
        assert expected in values


def test_bioportal_availability_is_env_driven(monkeypatch):
    monkeypatch.delenv(so.BIOPORTAL_ENV_VAR, raising=False)
    assert so.bioportal_available() is False
    monkeypatch.setenv(so.BIOPORTAL_ENV_VAR, "k")
    assert so.bioportal_available() is True


def test_nothing_is_written_inside_the_plugin(tmp_path, plugin_sentinel):
    so.write_ontology_artifact(tmp_path, "D.VIA",
                               {"Type": so.propose_values(DVIA, "Type")})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_schema_ontology.py -v`
Expected: `ImportError: cannot import name 'ontology' from 'schema'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/schema/ontology.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Propose controlled vocabulary for a sample type field, with sources.

This is schema mode's shortest path to value, because the delivery mechanism
already exists and nothing has ever used it:

  - `_common.write_4sheet_xlsx` accepts `ontology={field: [values]}` and writes
    a real Ontology sheet, declaring those fields `Controlled Ontology` on the
    Instructions sheet.
  - No caller has ever passed it. `curate-build.md` and `PHASES.md` never
    instruct it be populated. `consolidate_to_flat.py` never reads it.

So NExtSEEK has a controlled-vocabulary mechanism, the plugin can already write
it, and nothing populates or consumes it. `<TYPE>.ontology.json` is exactly that
parameter's shape.

Ontology validation is STRICT in the 4-sheet format and violations reject the
file. It does not exist at all in the flat format - see PHASES.md Phase 6.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"
OUTPUT_SUBDIR = "schema"

# Strongest source last: a later source overwrites an earlier one for the same
# literal value, so a value both tagged and observed is credited as observed.
_SOURCE_RANK = {"tags": 0, "sibling": 1, "bioportal": 2, "observed": 3}


@dataclass
class ProposedValue:
    """One candidate permissible value, and where it came from."""

    value: str
    source: str          # tags | observed | bioportal | sibling
    note: str = ""


def bioportal_available() -> bool:
    """Whether ontology term resolution can run. Degrades, never blocks.

    Without a key, vocabulary still comes from Tags, observed values and
    sibling types - which is most of it. IRI binding is the part that waits.
    """
    return bool(os.environ.get(BIOPORTAL_ENV_VAR))


def propose_values(record: dict, field_name: str, *,
                   observed: list[str] | None = None,
                   tags: list[str] | None = None,
                   siblings: list[str] | None = None,
                   bioportal: list[str] | None = None) -> list[ProposedValue]:
    """Candidate permissible values for one field, deduped, source-attributed.

    Mining `Tags` is the cheapest win available: D.VIA's Tags column already
    reads 'viability data, cell viability, cytotoxicity data, MTS assay, MTT
    assay, WST-1, live/dead assay, CellTiter-Glo, proliferation assay, cell
    death data' - permissible values for its `Type` field, written down as
    prose where nothing can enforce them.
    """
    if tags is None:
        tags = [t.strip() for t in (record.get("Tags") or "").split(",") if t.strip()]

    contributions: list[tuple[str, str]] = []
    contributions += [(v, "tags") for v in tags]
    contributions += [(v, "sibling") for v in (siblings or [])]
    contributions += [(v, "bioportal") for v in (bioportal or [])]
    contributions += [(v, "observed") for v in (observed or [])]

    best: dict[str, str] = {}
    order: list[str] = []
    for value, source in contributions:
        value = str(value).strip()
        if not value:
            continue
        if value not in best:
            order.append(value)
            best[value] = source
        elif _SOURCE_RANK[source] > _SOURCE_RANK[best[value]]:
            best[value] = source

    notes = {
        "tags": f"listed in the sample type's Tags column",
        "observed": "seen in previous_metadata",
        "sibling": "used by a sibling type in the same clade",
        "bioportal": "suggested by BioPortal; unconfirmed",
    }
    return [ProposedValue(value=v, source=best[v], note=notes[best[v]])
            for v in order]


def to_ontology_json(proposals: dict[str, list[ProposedValue]]) -> dict[str, list[str]]:
    """Exactly the shape `write_4sheet_xlsx(ontology=...)` expects."""
    return {field: [p.value for p in values]
            for field, values in proposals.items() if values}


def artifact_path(root: Path, sampletype: str) -> Path:
    return Path(root) / OUTPUT_SUBDIR / f"{sampletype}.ontology.json"


def write_ontology_artifact(root: Path, sampletype: str,
                            proposals: dict[str, list[ProposedValue]]) -> Path:
    """Write `<TYPE>.ontology.json` to cwd, with a `_sources` sidecar block.

    The values block is directly consumable by `write_4sheet_xlsx`. `_sources`
    exists so a reviewer can judge each value: a bare list cannot be judged, a
    list with provenance can.
    """
    doc: dict = to_ontology_json(proposals)
    doc["_sources"] = {
        field: {p.value: p.source for p in values}
        for field, values in proposals.items() if values
    }
    doc["_note"] = (
        "Values feed _common.write_4sheet_xlsx(ontology=...). Ontology "
        "validation is strict in the 4-sheet upload format and violations "
        "reject the file; the flat format has no Ontology sheet and silently "
        "discards controlled vocabulary. Review every value before use."
    )
    p = artifact_path(root, sampletype)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return p


def load_ontology_artifact(root: Path, sampletype: str) -> dict[str, list[str]]:
    """Read back only the `{field: [values]}` part, ready for the 4-sheet writer."""
    p = artifact_path(root, sampletype)
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text())
    return {k: v for k, v in doc.items() if not k.startswith("_")}
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_schema_ontology.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/ontology.py tests/test_schema_ontology.py
git commit -m "feat(schema): ontology proposals that feed the dead Ontology sheet

_common.write_4sheet_xlsx has always accepted ontology={field: [values]} and
written a real Ontology sheet, and no caller has ever passed it: curate-build.md
and PHASES.md never instructed it be populated and consolidate_to_flat.py never
read it. NExtSEEK had a controlled-vocabulary mechanism, the plugin could write
it, and nothing populated or consumed it.

propose_values() mines the Tags column first (D.VIA's Tags are already a list of
permissible Type values sitting in prose), then observed values from
previous_metadata, then siblings, then BioPortal. Every value carries its
source in a _sources block so a reviewer can judge it. <TYPE>.ontology.json is
exactly write_4sheet_xlsx's parameter shape, verified end-to-end.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 22: BioPortal term resolution, degrading when no key is present

**Files:**
- Create: `scripts/schema/terms.py`
- Test: `tests/test_schema_terms.py`

**Interfaces:**
- Consumes: `ontology.BIOPORTAL_ENV_VAR`, `ontology.bioportal_available` from Task 21
- Produces:
  - `@dataclass TermHit`: `iri`, `label`, `source`, `score`, `definition`
  - `search_terms(query, *, ontologies=None, api_key=None, limit=5, http=None) -> list[TermHit]`
  - `to_binding(hit) -> dict` — always `{"iri", "label", "source", "confirmed": False}`
  - `DEFAULT_ONTOLOGIES = ("NCIT", "OBI", "EFO", "UBERON", "CL")`
  - `BIOPORTAL_SEARCH_URL`

**Context (schema spec, and the user's answer to the scope question):** the key may not be present at run time. The degraded path — Tags, observed values, siblings — is the tested default; live resolution is wired but must never be a precondition. **Every binding is emitted `"confirmed": false` with its source. Only a human flips it.** In the MUS prototype `Strain` was bound to `NCBITaxon_10090`, which is **wrong** — NCBITaxon covers species, not laboratory strains such as C57BL/6J or BALB/c — and it was plausible enough to pass unreviewed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema_terms.py`:

```python
"""BioPortal term resolution. Suggests, never binds; degrades without a key."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import terms as st  # noqa: E402

FAKE_RESPONSE = {
    "collection": [
        {"@id": "http://purl.obolibrary.org/obo/NCIT_C16403",
         "prefLabel": "Cell Line",
         "links": {"ontology": "http://data.bioontology.org/ontologies/NCIT"},
         "definition": ["A cell culture derived from a single cell."]},
        {"@id": "http://purl.obolibrary.org/obo/OBI_0001876",
         "prefLabel": "cell line",
         "links": {"ontology": "http://data.bioontology.org/ontologies/OBI"},
         "definition": []},
    ]
}


class FakeHTTP:
    """Stand-in for the HTTP getter. Records the URL it was asked for."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.payload


def test_search_returns_empty_without_a_key(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    assert st.search_terms("cell line") == []


def test_search_without_a_key_does_not_call_the_network(monkeypatch):
    monkeypatch.delenv(st.BIOPORTAL_ENV_VAR, raising=False)
    http = FakeHTTP(FAKE_RESPONSE)
    assert st.search_terms("cell line", http=http) == []
    assert http.calls == []


def test_search_parses_hits(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", http=FakeHTTP(FAKE_RESPONSE))
    assert len(hits) == 2
    assert hits[0].iri == "http://purl.obolibrary.org/obo/NCIT_C16403"
    assert hits[0].label == "Cell Line"
    assert hits[0].source == "NCIT"
    assert "single cell" in hits[0].definition


def test_search_handles_a_missing_definition(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", http=FakeHTTP(FAKE_RESPONSE))
    assert hits[1].definition == ""


def test_search_restricts_to_the_requested_ontologies(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    http = FakeHTTP(FAKE_RESPONSE)
    st.search_terms("cell line", ontologies=("NCIT", "OBI"), http=http)
    url = http.calls[0][0]
    assert "ontologies=NCIT%2COBI" in url or "ontologies=NCIT,OBI" in url


def test_search_never_puts_the_key_in_the_url(monkeypatch):
    """A key in a query string leaks into logs and shell history."""
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "SUPERSECRET")
    http = FakeHTTP(FAKE_RESPONSE)
    st.search_terms("cell line", http=http)
    url, headers = http.calls[0]
    assert "SUPERSECRET" not in url
    assert "SUPERSECRET" in str(headers)


def test_search_respects_limit(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    hits = st.search_terms("cell line", limit=1, http=FakeHTTP(FAKE_RESPONSE))
    assert len(hits) == 1


def test_search_survives_a_transport_error(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")

    def boom(url, headers=None, timeout=None):
        raise OSError("network down")

    assert st.search_terms("cell line", http=boom) == []


def test_search_survives_an_unexpected_payload(monkeypatch):
    monkeypatch.setenv(st.BIOPORTAL_ENV_VAR, "testkey")
    assert st.search_terms("x", http=FakeHTTP({"unexpected": True})) == []


def test_to_binding_is_always_unconfirmed():
    hit = st.TermHit(iri="i", label="l", source="NCIT", score=1.0, definition="d")
    b = st.to_binding(hit)
    assert b == {"iri": "i", "label": "l", "source": "NCIT", "confirmed": False}


def test_default_ontologies_are_biomedical():
    assert "NCIT" in st.DEFAULT_ONTOLOGIES
    assert "OBI" in st.DEFAULT_ONTOLOGIES


def test_module_documents_the_ncbitaxon_strain_trap():
    """The prototype bound Strain to NCBITaxon_10090, which covers species,
    not laboratory strains. It was plausible enough to pass unreviewed."""
    src = (REPO / "scripts" / "schema" / "terms.py").read_text()
    assert "NCBITaxon" in src
    assert "C57BL/6J" in src
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_schema_terms.py -v`
Expected: `ImportError: cannot import name 'terms' from 'schema'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/schema/terms.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""BioPortal ontology term lookup. Suggests, never binds.

CEDAR's contribution to this plugin reduces to exactly this: ontology term
resolution, usable standalone with no CEDAR account, no hosted service and no
template machinery.

Every binding this module produces is emitted with ``"confirmed": false`` and
its source. Only a human flips that flag, and this is not caution for its own
sake. In the MUS prototype `Strain` was bound to `NCBITaxon_10090` - which is
WRONG. NCBITaxon covers species, not laboratory strains such as C57BL/6J or
BALB/c. It was plausible enough to pass unreviewed. Ontology binding is
per-field human judgment and the tooling must not pretend otherwise.

Degrades rather than blocking: with no BIOPORTAL_API_KEY, `search_terms`
returns an empty list without touching the network. Vocabulary still comes from
the Tags column, observed values in previous_metadata, and sibling types, which
is most of it. IRI binding is the part that waits for a key.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

BIOPORTAL_ENV_VAR = "BIOPORTAL_API_KEY"
BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"

# Biomedical ontologies worth searching by default for NExtSEEK sample metadata.
DEFAULT_ONTOLOGIES = ("NCIT", "OBI", "EFO", "UBERON", "CL")

_TIMEOUT_SECONDS = 20


@dataclass
class TermHit:
    """One BioPortal search result."""

    iri: str
    label: str
    source: str          # ontology acronym, e.g. NCIT
    score: float = 0.0
    definition: str = ""


def _default_http(url: str, headers: dict | None = None, timeout: int | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _acronym(entry: dict) -> str:
    link = ((entry.get("links") or {}).get("ontology") or "")
    return link.rstrip("/").rsplit("/", 1)[-1] if link else ""


def search_terms(query: str, *, ontologies=None, api_key: str | None = None,
                 limit: int = 5, http=None) -> list[TermHit]:
    """Search BioPortal for terms matching `query`.

    Returns [] and makes NO network call when no API key is available, so a
    caller can always call this unconditionally.

    The key travels in the Authorization header, never in the query string,
    because a query string ends up in logs and shell history.
    """
    key = api_key or os.environ.get(BIOPORTAL_ENV_VAR)
    if not key:
        return []

    params = {
        "q": query,
        "ontologies": ",".join(ontologies or DEFAULT_ONTOLOGIES),
        "require_definitions": "false",
        "pagesize": str(max(limit, 1)),
    }
    url = f"{BIOPORTAL_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"apikey token={key}", "Accept": "application/json"}

    getter = http or _default_http
    try:
        payload = getter(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - a lookup failure must never break a run
        return []

    collection = (payload or {}).get("collection")
    if not isinstance(collection, list):
        return []

    hits: list[TermHit] = []
    for entry in collection[:limit]:
        if not isinstance(entry, dict) or not entry.get("@id"):
            continue
        definitions = entry.get("definition") or []
        hits.append(TermHit(
            iri=entry["@id"],
            label=entry.get("prefLabel") or "",
            source=_acronym(entry),
            score=float(entry.get("score") or 0.0),
            definition=definitions[0] if definitions else "",
        ))
    return hits


def to_binding(hit: TermHit) -> dict:
    """The dictionary-entry `ontology` block. Always unconfirmed."""
    return {"iri": hit.iri, "label": hit.label, "source": hit.source,
            "confirmed": False}
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_schema_terms.py -v`
Expected: all pass.

- [ ] **Step 5: Optional live check, only if a key is available**

If `BIOPORTAL_API_KEY` is set in the environment:

```bash
BIOPORTAL_API_KEY="$BIOPORTAL_API_KEY" uv run python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("scripts")))
from schema import terms
for h in terms.search_terms("cell line", limit=3):
    print(f"{h.source:>8}  {h.label}  {h.iri}")
print()
print("Strain lookup - check whether any hit is actually about laboratory")
print("strains rather than species. NCBITaxon_10090 is Mus musculus, NOT C57BL/6J:")
for h in terms.search_terms("mouse strain", limit=5):
    print(f"{h.source:>8}  {h.label}  {h.iri}")
PY
```

Record what came back in the commit message. **If no key is available, skip this step** — the unit tests cover the parsing and the degraded path is the tested default.

- [ ] **Step 6: Commit**

```bash
git add scripts/schema/terms.py tests/test_schema_terms.py
git commit -m "feat(schema): BioPortal term lookup that suggests and never binds

CEDAR's whole contribution to this plugin reduces to ontology term resolution,
usable standalone with no CEDAR account and no hosting. Every binding is emitted
confirmed:false with its source; only a human flips it. That is not caution for
its own sake -- the MUS prototype bound Strain to NCBITaxon_10090, which covers
species and not laboratory strains like C57BL/6J, and it was plausible enough to
pass unreviewed.

Degrades rather than blocking: with no BIOPORTAL_API_KEY, search_terms returns
[] without touching the network, and vocabulary still comes from Tags, observed
values and sibling types. The key travels in the Authorization header, never the
query string.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 23: `/curate-sampletype` and the `SCHEMA.md` reference

**Files:**
- Create: `commands/curate-sampletype.md`
- Create: `scripts/schema/review.py`
- Modify: `skills/curation/SCHEMA.md` (replace the Task 12 stub)
- Test: `tests/test_curate_sampletype.py`

**Interfaces:**
- Consumes: everything from Tasks 19-22
- Produces:
  - `render_review(sampletype, *, record, current_fields, proposals, reuse_decisions, ontology, open_questions, dictionary_entries) -> str`
  - `write_review(root, sampletype, markdown) -> Path`
  - `write_proposed_record(root, sampletype, record) -> Path`
  - `REQUIRED_SECTIONS` — the six headings `<TYPE>.review.md` must contain
  - `/curate-sampletype <TYPE>` producing `schema/<TYPE>.review.md`, `schema/<TYPE>.proposed.json`, `schema/<TYPE>.ontology.json`, `schema/field_dictionary.json`

**Context (schema spec):** `<TYPE>.review.md` **is the deliverable**. The JSON exists to feed tooling; the markdown is what the work is *for*. Rationale-per-change is the point — a bare field list cannot be judged, a field list with evidence can.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curate_sampletype.py`:

```python
"""The schema-mode deliverable: <TYPE>.review.md and its siblings."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import review as sr  # noqa: E402
from schema import ontology as so  # noqa: E402

COMMAND = REPO / "commands" / "curate-sampletype.md"
SCHEMA_DOC = REPO / "skills" / "curation" / "SCHEMA.md"

RECORD = {
    "SampleType": "D.VIA", "Name": "Viability Assay Data", "Clade": "Raw",
    "Description": "Quantitative results from viability experiments.",
    "Tags": "MTS assay, MTT assay, WST-1, CellTiter-Glo",
    "Required Metadata": "UID, File_PrimaryData, Scientist, Parent",
    "Standard Metadata": "Protocol, CellLine, Type",
    "Possible Metadata Fields": "Notes",
    "Associated Assay Parents": "Cell Viability Assay",
    "Parent_SampleTypes": "CEL",
}


def _render():
    return sr.render_review(
        "D.VIA",
        record=RECORD,
        current_fields={"required": ["UID", "File_PrimaryData", "Scientist", "Parent"],
                        "standard": ["Protocol", "CellLine", "Type"],
                        "possible": ["Notes"]},
        proposals=[
            {"field": "Timepoint", "rationale":
             "the producing assay is time-series by nature; 3 sibling Raw types "
             "carry it; observed in previous_metadata as 24h, 48h",
             "evidence": ["sibling: D.FLOW", "observed: 24h, 48h"]},
        ],
        reuse_decisions=[
            {"proposed": "PlateReaderModel", "used_instead": "Instrument",
             "reason": "16 existing usages across the catalog"},
        ],
        ontology={"Type": so.propose_values(RECORD, "Type")},
        open_questions=["Is dose in uM or mg/mL? Both appear in previous_metadata."],
        dictionary_entries=["Timepoint", "Instrument"],
    )


def test_command_file_exists_with_frontmatter():
    assert COMMAND.exists()
    text = COMMAND.read_text()
    assert text.startswith("---")
    assert "description:" in text.split("---")[1]


def test_command_states_it_writes_to_cwd():
    text = COMMAND.read_text()
    assert "current working directory" in text
    assert "no lockfile" in text.lower()


def test_command_states_a_human_applies_the_proposal():
    text = COMMAND.read_text()
    assert "never writes to NExtSEEK" in text
    assert "sampletypes_db.json" in text


def test_command_references_the_real_scripts():
    text = COMMAND.read_text()
    for rel in ("scripts/schema/field_index.py", "scripts/schema/ontology.py",
                "scripts/schema/dictionary.py", "scripts/schema/terms.py"):
        assert rel in text
        assert (REPO / rel).exists()


def test_schema_doc_is_no_longer_a_stub():
    text = SCHEMA_DOC.read_text()
    assert "Status: stub" not in text
    assert "reuse check" in text.lower()
    assert "Ontology sheet" in text


def test_schema_doc_states_templates_are_out_of_scope():
    """tree vs graph: CEDAR has no cross-record reference concept."""
    text = SCHEMA_DOC.read_text()
    assert "tree" in text.lower() and "graph" in text.lower()
    assert "no CEDAR template is emitted" in text


def test_review_contains_every_required_section():
    md = _render()
    for heading in sr.REQUIRED_SECTIONS:
        assert heading in md, f"review is missing section {heading!r}"


def test_review_states_current_state():
    md = _render()
    assert "6 required" in md or "4 required" in md
    assert "Protocol" in md


def test_every_proposal_carries_its_rationale():
    md = _render()
    assert "Timepoint" in md
    assert "time-series by nature" in md
    assert "observed: 24h, 48h" in md


def test_reuse_decisions_are_stated_so_they_can_be_overruled():
    md = _render()
    assert "PlateReaderModel" in md
    assert "Instrument" in md
    assert "16 existing usages" in md


def test_controlled_vocabulary_lists_the_source_of_every_value():
    md = _render()
    assert "MTS assay" in md
    assert "tags" in md


def test_open_questions_are_surfaced():
    assert "uM or mg/mL" in _render()


def test_how_to_apply_is_concrete():
    md = _render()
    section = md.split("## How to apply", 1)[1]
    assert "write_4sheet_xlsx" in section or "ontology.json" in section
    assert "by hand" in section.lower() or "manual" in section.lower()


def test_review_never_proposes_a_rename_or_split():
    """A field name shared across types is not a defect."""
    src = (REPO / "scripts" / "schema" / "review.py").read_text()
    assert "rename" not in src.lower() or "never" in src.lower()
    assert "homonym" not in src.lower()


def test_write_review_lands_in_cwd_schema_dir(tmp_path, plugin_sentinel):
    p = sr.write_review(tmp_path, "D.VIA", _render())
    assert p == tmp_path / "schema" / "D.VIA.review.md"
    assert p.read_text()


def test_write_proposed_record_is_catalog_shaped(tmp_path):
    p = sr.write_proposed_record(tmp_path, "D.VIA", RECORD)
    doc = json.loads(p.read_text())
    assert doc["SampleType"] == "D.VIA"
    assert "Required Metadata" in doc


def test_proposed_record_is_a_proposal_not_an_edit(tmp_path):
    """It must be diffable against the catalog, never written over it."""
    sr.write_proposed_record(tmp_path, "D.VIA", RECORD)
    assert not (REPO / "context" / "D.VIA.proposed.json").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py -v`
Expected: `ImportError: cannot import name 'review' from 'schema'`, plus the command-file assertions.

- [ ] **Step 3: Write `scripts/schema/review.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render `<TYPE>.review.md` - schema mode's actual deliverable.

The JSON artifacts exist to feed tooling. This markdown is what the work is
*for*: a human reads it and decides what to apply, by hand.

Rationale-per-change is the point. A bare field list cannot be judged; a field
list with evidence can. Reuse decisions are stated explicitly so they can be
overruled, not buried.

This module never proposes renaming or splitting an existing field name. A name
shared across sample types is not a defect: `Type` appears on many types and
legitimately means different things on each. The review records what a field
means *here*.
"""
from __future__ import annotations

import json
from pathlib import Path

OUTPUT_SUBDIR = "schema"

REQUIRED_SECTIONS = (
    "## Current state",
    "## Proposed additions",
    "## Reuse decisions",
    "## Controlled vocabularies proposed",
    "## Open questions and placeholders",
    "## How to apply",
)


def render_review(sampletype: str, *, record: dict, current_fields: dict,
                  proposals: list[dict], reuse_decisions: list[dict],
                  ontology: dict, open_questions: list[str],
                  dictionary_entries: list[str]) -> str:
    """Build the review markdown.

    Args:
      sampletype:         short code, e.g. 'D.VIA'.
      record:             the current catalog record.
      current_fields:     {"required": [...], "standard": [...], "possible": [...]}.
      proposals:          [{"field", "rationale", "evidence": [...]}].
      reuse_decisions:    [{"proposed", "used_instead", "reason"}].
      ontology:           {field: [ProposedValue]} from schema.ontology.
      open_questions:     things that could not be resolved, and why.
      dictionary_entries: field names this run wrote to field_dictionary.json.
    """
    req = current_fields.get("required", [])
    std = current_fields.get("standard", [])
    pos = current_fields.get("possible", [])
    lines: list[str] = []

    lines.append(f"# {sampletype} - {record.get('Name', '')}")
    lines.append("")
    lines.append("**This is a proposal.** Nothing here has been applied. schema "
                 "mode never writes to NExtSEEK and never edits "
                 "`sampletypes_db.json`.")
    lines.append("")

    lines.append("## Current state")
    lines.append("")
    lines.append(f"{len(req)} required / {len(std)} standard / {len(pos)} possible "
                 f"= {len(req) + len(std) + len(pos)} fields.")
    lines.append("")
    lines.append(f"- **Clade:** {record.get('Clade') or '(none)'}")
    lines.append(f"- **Producing assay:** {record.get('Associated Assay Parents') or '(none)'}")
    lines.append(f"- **Parent sample types:** {record.get('Parent_SampleTypes') or '(none)'}")
    lines.append("")
    for label, fields in (("Required", req), ("Standard", std), ("Possible", pos)):
        lines.append(f"- **{label}:** {', '.join(fields) if fields else '(none)'}")
    lines.append("")

    lines.append("## Proposed additions")
    lines.append("")
    if not proposals:
        lines.append("None. The current field set covers what this assay produces.")
    for p in proposals:
        lines.append(f"### `{p['field']}`")
        lines.append("")
        lines.append(p.get("rationale", ""))
        lines.append("")
        for ev in p.get("evidence") or []:
            lines.append(f"- {ev}")
        lines.append("")

    lines.append("## Reuse decisions")
    lines.append("")
    lines.append("Stated so they can be overruled. A name shared across sample "
                 "types is not a defect; nothing here proposes a rename or a split.")
    lines.append("")
    if not reuse_decisions:
        lines.append("No new names were considered this run.")
    for d in reuse_decisions:
        lines.append(f"- Used existing `{d['used_instead']}` rather than minting "
                     f"`{d['proposed']}` - {d['reason']}")
    lines.append("")

    lines.append("## Controlled vocabularies proposed")
    lines.append("")
    if not ontology:
        lines.append("None proposed this run.")
    for field_name, values in ontology.items():
        lines.append(f"### `{field_name}`")
        lines.append("")
        lines.append("| value | source | note |")
        lines.append("|---|---|---|")
        for v in values:
            lines.append(f"| {v.value} | {v.source} | {v.note} |")
        lines.append("")

    lines.append("## Open questions and placeholders")
    lines.append("")
    if not open_questions:
        lines.append("None.")
    for q in open_questions:
        lines.append(f"- {q}")
    lines.append("")

    lines.append("## How to apply")
    lines.append("")
    lines.append("Every step below is manual. Nothing is automated, by design.")
    lines.append("")
    lines.append(f"1. **Review each proposed addition above.** Reject anything "
                 f"whose rationale does not hold for your project.")
    lines.append(f"2. **Diff the proposed record.** "
                 f"`schema/{sampletype}.proposed.json` is shaped like a "
                 f"`sampletypes_db.json` entry, so a plain diff against the "
                 f"catalog record shows exactly what changes.")
    lines.append(f"3. **Confirm every ontology binding.** All are emitted "
                 f"`\"confirmed\": false`. Check each IRI actually denotes what "
                 f"the field means - the MUS prototype bound `Strain` to "
                 f"`NCBITaxon_10090`, which is a species, not a laboratory strain.")
    lines.append(f"4. **Put the vocabulary to work now, without waiting for a "
                 f"schema change.** `schema/{sampletype}.ontology.json` is "
                 f"directly consumable by "
                 f"`_common.write_4sheet_xlsx(ontology=...)`, so "
                 f"`/curate-build` can emit a 4-sheet workbook whose Ontology "
                 f"sheet enforces these values. That is the only upload format "
                 f"where NExtSEEK enforces controlled vocabulary; the flat "
                 f"format silently discards it.")
    lines.append(f"5. **Apply the record itself by hand**, through whatever "
                 f"channel your NExtSEEK instance uses for sample type changes. "
                 f"Confirm that channel with the NExtSEEK admin before editing "
                 f"anything - this is an open question the design did not settle.")
    lines.append("")

    if dictionary_entries:
        lines.append("## Field dictionary")
        lines.append("")
        lines.append(f"This run wrote {len(dictionary_entries)} entr"
                     f"{'y' if len(dictionary_entries) == 1 else 'ies'} to "
                     f"`schema/field_dictionary.json`: "
                     f"{', '.join(f'`{n}`' for n in dictionary_entries)}.")
        lines.append("")
        lines.append("The dictionary is lazy and local to this directory. It does "
                     "not accumulate across projects, and none ships with the "
                     "plugin.")
        lines.append("")

    return "\n".join(lines)


def write_review(root: Path, sampletype: str, markdown: str) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{sampletype}.review.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown)
    return p


def write_proposed_record(root: Path, sampletype: str, record: dict) -> Path:
    """Write the proposed catalog record, for diffing. Never edits the catalog."""
    p = Path(root) / OUTPUT_SUBDIR / f"{sampletype}.proposed.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return p
```

- [ ] **Step 4: Write `commands/curate-sampletype.md`**

```markdown
---
description: Propose or bolster a NExtSEEK sample type (schema mode)
---

The user wants to define a new NExtSEEK sample type, or bolster an existing one:
"help me bolster D.VIA", "what should we be collecting for this assay?"

Parse `$ARGUMENTS` for a sample type short code, e.g. `D.VIA`. If absent, ask
which type - do not guess.

**Load `skills/curation/SCHEMA.md` before starting.**

## State scope

**cwd-scoped.** Read the plugin's `context/` read-only. Write every artifact
into the current working directory, under `schema/`. There is **no lockfile**
requirement, no scaffold, and no project. This works from anywhere.

## The mode never applies anything

It **never writes to NExtSEEK** and never edits `sampletypes_db.json`. Its
product is a proposal with rationale, which a human reviews and applies by hand.

## The loop

1. **Read the current definition.** Use `scripts/schema/field_index.py`:
   `load_catalog()`, then `type_record(catalog, TYPE)`. Report the
   required / standard / possible counts.

2. **Gather evidence.**
   - the producing assay from `Associated Assay Parents`, described in
     `context/assays_db.json`
   - sibling types in the same clade via `siblings_in_clade(catalog, TYPE)` -
     what do they collect that this type does not?
   - real observed values from any `previous_metadata/*.xlsx` in cwd, via
     `scripts/schema/dictionary.py` `observe_values()`. Real values beat
     guessed ones (SKILL.md hard rule 4).

3. **Identify gaps.** What does this assay actually produce that the record does
   not capture? For a viability assay: readout type, instrument, timepoint, dose,
   units, replicate, controls.

4. **Run the reuse check before minting any new name.** For each candidate,
   `rank_candidates(name, index, clade=..., assay=..., catalog=...)`. Show the
   user the candidate name, how many types use it, which ones, and example
   values. **The curator judges** - the tool never decides.

   A field name shared across sample types is **not** a defect. `Type` appears
   on many types and legitimately means different things on each. Never propose
   a rename or a split.

5. **Propose controlled values.** `scripts/schema/ontology.py` `propose_values()`
   mines the Tags column first (it is often already a list of permissible
   values), then observed values, then siblings, then BioPortal via
   `scripts/schema/terms.py` if `BIOPORTAL_API_KEY` is set. Without a key the
   first three still work; say so rather than failing.

6. **Emit the artifacts** into `./schema/`:

   | file | what it is |
   |---|---|
   | `<TYPE>.review.md` | **the product** - written for a human deciding what to apply |
   | `<TYPE>.proposed.json` | a `sampletypes_db.json`-shaped record, for diffing |
   | `<TYPE>.ontology.json` | `{field: [allowed values]}` - feeds `write_4sheet_xlsx(ontology=)` |
   | `field_dictionary.json` | entries for fields this run touched, only |

## Hard rules for this mode

- **Every ontology binding is emitted `"confirmed": false`.** Only a human flips
  it. The MUS prototype bound `Strain` to `NCBITaxon_10090`, which is a species,
  not a laboratory strain like C57BL/6J. It was plausible enough to pass
  unreviewed.
- **Rationale per change.** A bare field list cannot be judged. Every proposed
  addition states why, with evidence: the producing assay, sibling usage, or
  observed values.
- **State reuse decisions explicitly** so the curator can overrule them.
- **Never rename or split** an existing field name.
- **No CEDAR template is emitted.** See `SCHEMA.md` for why.
- Anything unresolved goes in "Open questions and placeholders", never a guess.

## Report

Print the counts, the reuse decisions, and the paths written. End by pointing
the user at `schema/<TYPE>.review.md` as the thing to read.
```

- [ ] **Step 5: Fill in `skills/curation/SCHEMA.md`**

Replace the stub:

```markdown
# `schema` mode - sample type authoring

Deep reference. Load when entering schema mode.
Design: `docs/superpowers/specs/2026-07-21-schema-mode-design.md`.

## Purpose

Answer "what are we collecting?" for a NExtSEEK sample type. Given a type - say
`D.VIA` - produce resources a human reviews and then applies by hand.

The problem it attacks: of **1059 distinct field names across 101 sample types,
856 are used by exactly one type**, and none of the 1059 carries a description,
datatype or vocabulary anywhere. There is no way for an author to answer "does a
field for this already exist?", so new near-duplicates get minted by default.

## State scope

**cwd.** Reads the plugin's `context/` read-only; writes everything into the
current working directory under `schema/`. No lockfile, no scaffold, no project.

## Scope: ontology grounding, not CEDAR templates

Despite the shorthand ("use CEDAR to bolster D.VIA"), **no CEDAR template is
emitted**. CEDAR's contribution is ontology term resolution via BioPortal, which
is usable standalone: no CEDAR account, no hosted service, no template
machinery.

### Why templates are out of scope: tree vs graph

CEDAR's artifact model is a nested **tree** - template contains elements,
elements contain fields. It has no concept of one record referencing another.
NExtSEEK lineage is a **graph**: `MUS -> TIS -> DNA`, many-to-many parents,
expressed as cross-record UID references.

A CEDAR template could hold a UID in a text field, but referential integrity -
is this parent UID real, is the parent of a legal type, does the lineage
terminate - would live entirely outside CEDAR. That integrity work is most of
what the curation pipeline actually does. CEDAR is a strong model for
field-level typing and controlled vocabulary and a weak one for sample lineage,
which is the part that matters most here.

Three further mismatches, any one of which would need resolving first:

- CEDAR mints UUID-based IRIs; NExtSEEK UIDs are `<TYPE>-YYMMDD<LAB>-N`.
- CEDAR emits JSON-LD; the pipeline's deliverable is xlsx.
- Adopting CEDAR templates means committing to the schema being correct, which
  reverses SKILL.md hard rule 4, *"Schema lies; workbook tells truth."* That is
  a curation-policy decision, not a tooling one.

## Modules

| module | responsibility |
|---|---|
| `scripts/schema/field_index.py` | catalog loading, field usage index, the reuse check, Tags mining |
| `scripts/schema/dictionary.py` | observed-value mining, the lazy cwd-only field dictionary |
| `scripts/schema/ontology.py` | controlled-value proposals with sources, the `<TYPE>.ontology.json` artifact |
| `scripts/schema/terms.py` | BioPortal lookup; suggests, never binds; degrades with no key |
| `scripts/schema/review.py` | renders `<TYPE>.review.md`, the deliverable |

## The reuse check

Ranked candidates, never a yes/no. Passes in order of confidence: exact name,
normalized name (case, separators, plural), synonym match against dictionary
entries, semantic match over shared word stems. Ranked within a pass by usage
count, then clade proximity, then assay proximity.

The curator is shown the candidate name, how many types use it, which ones, and
example values - then judges.

**A field name shared across types is not a defect.** `Type` appears on many
sample types and legitimately means different things on each. The mode records
what it means *here*; it never proposes a rename or a split.

## The Ontology sheet - the shortest path to value

`_common.write_4sheet_xlsx` accepts `ontology={field: [values]}` and writes a
real Ontology sheet, declaring those fields `Controlled Ontology` on the
Instructions sheet:

```
| Field  | Database Field  | Field Type          | Ontology |
| Strain | MUS::Strain     | Controlled Ontology | Strain   |
```

**No caller had ever passed it.** Nothing populated it; `consolidate_to_flat.py`
never read it. So NExtSEEK had a controlled-vocabulary mechanism, the plugin
could write it, and nothing populated or consumed it. `<TYPE>.ontology.json` is
exactly that parameter's shape.

Since Phase 5's 4-sheet output is a **curator review artifact**, populating the
Ontology sheet puts permissible values in front of the reviewer at the moment
they are checking the data - with no new plumbing.

### Enforcement exists only in 4-sheet

| upload mode | ontology enforcement |
|---|---|
| direct rows (JSON) | "Ontology validation is not performed in rows mode" |
| flat xlsx | none - the format has no Ontology sheet |
| 4-sheet xlsx | "Validation is strict; violations reject the file" |

Adding an ontology column to a flat sheet does **not** work: `InputRowModel` is
`additionalProperties: true` and unknown columns are "ignored, with a warning",
so it would be accepted and silently discarded - worse than rejection.

**Verify before relying on this.** Read from `context/NExtSEEK_API.yaml`,
bundled 2026-05-27. Confirm with the NExtSEEK API owner that flat still lacks
ontology support.

## The field dictionary

**Lazy and cwd-only.** No pre-built dictionary ships, and none is generated for
all 1059 names. Each run creates entries only for the fields it touched.

Accepting the non-accumulation is deliberate: the plugin already has a
three-copies-of-context problem, and shipping another data file that drifts
would repeat it. Lazy ships no state - nothing to version, refresh or go stale.

Entry shape:

```json
"Instrument": {
  "description": "...",
  "datatype": "string",
  "used_by": ["D.VIA", "D.FLOW"],
  "observed_values": ["BioTek Synergy H1"],
  "ontology": {"iri": "...", "label": "...", "source": "NCIT", "confirmed": false},
  "synonyms": ["PlateReader", "Analyzer"],
  "provenance": "16 existing usages + 3 observed values"
}
```

## BioPortal - suggests, never binds

Every binding is emitted `"confirmed": false` with its source. Only a human
flips it.

This is not caution for its own sake. In the `MUS` prototype `Strain` was bound
to `NCBITaxon_10090` - **wrong**: NCBITaxon covers species, not laboratory
strains such as C57BL/6J or BALB/c. It was plausible enough to pass unreviewed.

Requires a free BioPortal API key in `BIOPORTAL_API_KEY`. Without one,
`search_terms()` returns `[]` without touching the network, and vocabulary still
comes from Tags, observed values and sibling types.

## Non-goals

- Writing to NExtSEEK, or editing `sampletypes_db.json` in place.
- Emitting CEDAR templates (see tree vs graph).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).

## Open question

**What "apply" concretely means.** Application is manual and the mode only
produces artifacts. Not settled: whether a human applying a proposed sample type
record means editing NExtSEEK's admin UI, running a SQL update, or opening a PR
against a schema repo. Confirm with the NExtSEEK admin before telling a curator
to edit anything. Until then, `<TYPE>.review.md` says exactly that.
```

- [ ] **Step 6: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py tests/test_mode_table.py -v`
Expected: all pass, including `test_mode_table_lists_exactly_the_reference_docs`, since `SCHEMA.md` still exists at the same path.

- [ ] **Step 7: Smoke test the whole mode by hand**

```bash
mkdir -p /tmp/schema-smoke && cd /tmp/schema-smoke
uv run python3 - <<'PY'
import sys, pathlib
PLUGIN = "/home/cdemu/code/dmac/curation_skill"
sys.path.insert(0, PLUGIN + "/scripts")
from schema import field_index as fi, ontology as so, review as sr

catalog = fi.load_catalog()
rec = fi.type_record(catalog, "D.VIA")
index = fi.build_field_index(catalog)

print("Reuse check for 'PlateReaderModel':")
for c in fi.rank_candidates("PlateReaderModel", index, clade=rec["Clade"],
                            catalog=catalog, limit=5):
    print(f"  {c.name:<24} {c.usage_count:>3} types  ({c.match_pass})")

proposals = {"Type": so.propose_values(rec, "Type")}
print("\nProposed Type vocabulary:")
for p in proposals["Type"]:
    print(f"  {p.value:<24} <- {p.source}")

root = pathlib.Path.cwd()
so.write_ontology_artifact(root, "D.VIA", proposals)
sr.write_proposed_record(root, "D.VIA", rec)
md = sr.render_review("D.VIA", record=rec,
    current_fields={"required": rec["Required Metadata"].split(", "),
                    "standard": rec["Standard Metadata"].split(", "),
                    "possible": rec["Possible Metadata Fields"].split(", ")},
    proposals=[], reuse_decisions=[], ontology=proposals,
    open_questions=[], dictionary_entries=[])
print("\nWrote:", sr.write_review(root, "D.VIA", md))
PY
ls -la schema/
cd - >/dev/null
```

Expected: `schema/` holds `D.VIA.review.md`, `D.VIA.proposed.json`, `D.VIA.ontology.json`. The reuse check ranks real catalog names. The proposed `Type` vocabulary includes MTS assay, MTT assay, WST-1 and CellTiter-Glo, all sourced `tags`.

Then confirm the plugin is untouched: `git status --short`

- [ ] **Step 8: Commit**

```bash
git add commands/curate-sampletype.md scripts/schema/review.py \
        skills/curation/SCHEMA.md tests/test_curate_sampletype.py
git commit -m "feat(schema): /curate-sampletype and the SCHEMA.md reference

<TYPE>.review.md is the deliverable: the JSON artifacts feed tooling, the
markdown is what the work is for. Rationale per change is the point, because a
bare field list cannot be judged and a field list with evidence can. Reuse
decisions are stated explicitly so a curator can overrule them.

'How to apply' is honest about the one thing the design did not settle: whether
applying a proposed record means the admin UI, a SQL update, or a PR. It tells
the curator to confirm with the NExtSEEK admin, and meanwhile points at the
ontology artifact, which delivers value through the 4-sheet Ontology sheet
without waiting for any schema change.

SCHEMA.md records why CEDAR templates are out of scope: CEDAR's model is a
nested tree with no cross-record reference concept, and NExtSEEK lineage is a
graph, so referential integrity -- most of what the pipeline does -- would live
entirely outside it.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Stage G — `report` mode

Design: `docs/superpowers/specs/2026-07-21-report-mode-design.md`.

### Findings verified before planning this stage — read these first

Three facts were checked against the actual template files at
`/home/cdemu/code/chat_nextseek/src/chat_nextseek/reports/templates/` and one of
them **contradicts an assumption in the spec**:

**1. PRIDE is not a spreadsheet.** `pride.json` declares:

```json
"format": {"version": "2.2.1",
           "output_type": "tab-delimited PRIDE submission summary file",
           "field_separator": "tab",
           "line_prefixes": {"metadata": "MTD", "file_mapping_header": "FMH",
                             "file_mapping_entry": "FME",
                             "sample_metadata_header": "SMH",
                             "sample_metadata_entry": "SME",
                             "comment": "COM"}}
```

It is the ProteomeXchange Submission Summary File (`submission.px`), v2.2.1,
dated 2016-08-09. So chat_nextseek's e2e catalog asserting `api_artifact.pride.xlsx`
is asserting the **wrong artifact type**, not merely missing an exporter. The
spec's "PRIDE needs a renderer written from scratch" is correct; the renderer is
a prefixed-TSV writer, which is *simpler* than an xlsx renderer, not harder.

**2. SRA needs two output workbooks, not one.** `SRA.json` has two row-bearing
sections: `libraries` (16 columns, feeding `SRA_metadata.xlsx`) and `biosamples`
(feeding `SRA_biosample.xlsx`). Both templates ship.

**3. The two `GEO-updated.json` copies are byte-identical.** chat_nextseek's and
dmac-assistant's are the same 40089 bytes with identical parsed content. Report
spec open question 1 is therefore **resolved**: the choice is arbitrary, only
the provenance record matters.

Template section shapes, used by every task below:

| format | row-bearing section | row key | target sample type | rendered artifact |
|---|---|---|---|---|
| GEO | `samples` (20 cols) | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries` (16 cols) + `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata.xlsx` + `SRA_biosample.xlsx` |
| PRIDE | `sample_metadata` + `file_mapping` | `sample_metadata` | `D.MSP` | `submission.px` (tab-delimited) |

GEO's non-row sections are `study` (`*title`, `*summary (abstract)`,
`*experimental design`, `contributor`, `supplementary file`), `protocols`
(9 keys) and `paired_end_experiments`. `controlled_vocabulary` carries
`library_strategy`, `library_source`, `library_selection`, `library_layout`,
`platform`, `instrument_model_by_platform`, `filetype`, `instrument_model_flat`,
mined from `SRA_metadata.xlsx`.

A single `*` prefixes a required field; `**` marks conditionally required.

---

### Task 24: Vendor the report assets, with provenance

**Files:**
- Create: `context/report_templates/GEO-updated.json`
- Create: `context/report_templates/GEO_template.xlsx`
- Create: `context/report_templates/SRA.json`
- Create: `context/report_templates/SRA_metadata.xlsx`
- Create: `context/report_templates/SRA_biosample.xlsx`
- Create: `context/report_templates/pride.json`
- Modify: `context/PROVENANCE.json`
- Test: `tests/test_report_assets.py`

**Interfaces:**
- Consumes: `refresh_context.provenance_entry`, `refresh_context.read_provenance`, `refresh_context.write_provenance`, `refresh_context.sha256_of` from Task 18
- Produces: `context/report_templates/` with six vendored assets, each with a `PROVENANCE.json` entry

**Context:** `sampletypes_db.json` already exists in three copies at three vintages with no record of which is authoritative. Every vendored file gets a manifest entry so this does not become a fourth instance.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_assets.py`:

```python
"""Vendored report templates, each with a provenance entry."""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"

VENDORED = [
    "GEO-updated.json", "GEO_template.xlsx",
    "SRA.json", "SRA_metadata.xlsx", "SRA_biosample.xlsx",
    "pride.json",
]


@pytest.mark.parametrize("name", VENDORED)
def test_asset_is_present(name):
    assert (ASSETS / name).is_file(), f"{name} not vendored"


@pytest.mark.parametrize("name", VENDORED)
def test_asset_has_a_provenance_entry(name):
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    key = f"context/report_templates/{name}"
    assert key in prov["entries"], f"{key} has no provenance entry"
    entry = prov["entries"][key]
    for required in ("source_repo", "source_path", "commit_sha",
                     "vendored_date", "local_divergence"):
        assert required in entry, f"{key} provenance missing {required}"


@pytest.mark.parametrize("name", VENDORED)
def test_provenance_sha256_matches_the_file_on_disk(name):
    import hashlib
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    entry = prov["entries"][f"context/report_templates/{name}"]
    if not entry.get("sha256"):
        pytest.skip("no sha256 recorded")
    actual = hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
    assert entry["sha256"] == actual, f"{name} diverged from its recorded sha256"


def test_geo_spec_has_the_expected_sections():
    d = json.loads((ASSETS / "GEO-updated.json").read_text())
    assert d["report_type"] == "GEO"
    for key in ("study", "samples", "protocols", "paired_end_experiments",
                "controlled_vocabulary"):
        assert key in d
    assert isinstance(d["samples"], list) and d["samples"]
    assert "*library name" in d["samples"][0]


def test_geo_controlled_vocabulary_is_populated():
    cv = json.loads((ASSETS / "GEO-updated.json").read_text())["controlled_vocabulary"]
    assert isinstance(cv["library_strategy"], list)
    assert "RNA-Seq" in cv["library_strategy"]
    assert isinstance(cv["instrument_model_flat"], list)


def test_sra_spec_has_two_row_bearing_sections():
    d = json.loads((ASSETS / "SRA.json").read_text())
    assert d["report_type"].upper() == "SRA"
    assert isinstance(d["libraries"], list) and d["libraries"]
    assert isinstance(d["biosamples"], list) and d["biosamples"]
    assert "library_strategy" in d["libraries"][0]
    assert "*organism" in d["biosamples"][0]


def test_pride_spec_declares_a_tab_delimited_output_not_a_spreadsheet():
    """The single most important fact about PRIDE: it is not an xlsx.

    chat_nextseek's e2e catalog asserts api_artifact.pride.xlsx, which is the
    wrong artifact TYPE, not merely a missing exporter.
    """
    d = json.loads((ASSETS / "pride.json").read_text())
    assert d["format"]["field_separator"] == "tab"
    assert "tab-delimited" in d["format"]["output_type"]
    prefixes = d["format"]["line_prefixes"]
    assert prefixes["metadata"] == "MTD"
    assert prefixes["sample_metadata_entry"] == "SME"


def test_no_pride_xlsx_was_vendored():
    assert not (ASSETS / "pride.xlsx").exists()


def test_geo_and_dmac_assistant_copies_were_identical():
    """Report spec open question 1, resolved: the two copies are byte-identical,
    so the choice was arbitrary and only the provenance record matters."""
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    entry = prov["entries"]["context/report_templates/GEO-updated.json"]
    assert "identical" in entry["local_divergence"].lower()


def test_templates_are_read_only_plugin_data():
    """They live under context/, which _config treats as read-only."""
    assert ASSETS.parent.name == "context"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_report_assets.py -v`
Expected: every `test_asset_is_present` FAILS.

- [ ] **Step 3: Confirm the two GEO copies really are identical before choosing one**

Run:

```bash
python3 - <<'PY'
import json, hashlib, pathlib
a = pathlib.Path('/home/cdemu/code/chat_nextseek/src/chat_nextseek/reports/templates/GEO-updated.json')
b = pathlib.Path('/home/cdemu/code/dmac/dmac-assistant/tools/hibayes/resources/GEO-updated.json')
for p in (a, b):
    print(p, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()[:16])
print('parsed equal:', json.loads(a.read_text()) == json.loads(b.read_text()))
PY
```

Expected: identical sizes, identical parsed content. **If they differ, stop and diff them** — the report spec's open question 1 is then live and the choice needs recording with a reason.

- [ ] **Step 4: Copy the assets**

```bash
mkdir -p context/report_templates
SRC=/home/cdemu/code/chat_nextseek/src/chat_nextseek/reports/templates
cp "$SRC/GEO-updated.json"   context/report_templates/
cp "$SRC/GEO_template.xlsx"  context/report_templates/
cp "$SRC/SRA.json"           context/report_templates/
cp "$SRC/SRA_metadata.xlsx"  context/report_templates/
cp "$SRC/SRA_biosample.xlsx" context/report_templates/
cp "$SRC/pride.json"         context/report_templates/
ls -la context/report_templates/
```

**Do not copy `geo.json`** — `GEO-updated.json` supersedes it (it adds the
SRA-derived controlled vocabulary). **Do not copy anything from
`docker/v3/docker/cc-runtime/build_context/plugins/nextseek/`**; that is a
pre-hardening copy from an older commit.

- [ ] **Step 5: Record provenance**

```bash
uv run python3 - <<'PY'
import sys, pathlib, datetime, subprocess
sys.path.insert(0, "scripts")
import refresh_context as rc

SRC_REPO = pathlib.Path("/home/cdemu/code/chat_nextseek")
sha = subprocess.run(["git", "-C", str(SRC_REPO), "rev-parse", "HEAD"],
                     capture_output=True, text=True).stdout.strip() or None
today = datetime.date.today().isoformat()
rel = "src/chat_nextseek/reports/templates"

notes = {
    "GEO-updated.json":
        "byte-identical to dmac-assistant's tools/hibayes/resources/GEO-updated.json "
        "(same 40089 bytes, same parsed content), so report-spec open question 1 is "
        "moot; chat_nextseek chosen arbitrarily. Supersedes geo.json, which lacks the "
        "SRA-derived controlled vocabulary.",
    "GEO_template.xlsx": "none",
    "SRA.json": "none",
    "SRA_metadata.xlsx": "none",
    "SRA_biosample.xlsx": "none",
    "pride.json":
        "none. NOTE: declares a tab-delimited submission summary file (MTD/FMH/FME/"
        "SMH/SME line prefixes), NOT a spreadsheet. chat_nextseek's e2e catalog "
        "asserting pride.xlsx asserts the wrong artifact type.",
}

prov = rc.read_provenance()
for name, divergence in notes.items():
    p = pathlib.Path("context/report_templates") / name
    prov["entries"][f"context/report_templates/{name}"] = rc.provenance_entry(
        source_repo="chat_nextseek",
        source_path=f"{rel}/{name}",
        commit_sha=sha,
        vendored_date=today,
        local_divergence=divergence,
        sha256=rc.sha256_of(p),
    )
rc.write_provenance(prov)
print(f"recorded {len(notes)} entries at commit {sha}")
PY
```

- [ ] **Step 6: Run the tests**

Run: `uv run --with pytest pytest tests/test_report_assets.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add context/report_templates/ context/PROVENANCE.json tests/test_report_assets.py
git commit -m "feat(report): vendor GEO/SRA/PRIDE templates with provenance

Six assets from chat_nextseek's reports/templates, each with a PROVENANCE.json
entry recording source repo, path, commit SHA, date, divergence and sha256.
sampletypes_db.json already exists in three copies at three vintages with no
record of which is authoritative; this is how that stops happening.

Resolves report-spec open question 1: chat_nextseek's and dmac-assistant's
GEO-updated.json are byte-identical, so the choice was arbitrary.

Records the finding that changes PRIDE's shape: pride.json declares a
tab-delimited ProteomeXchange submission summary file with MTD/FMH/FME/SMH/SME
line prefixes, not a spreadsheet. chat_nextseek's e2e catalog asserting
pride.xlsx asserts the wrong artifact type.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 25: Vendor the artifact validator (GEO subset), then extend it

**Files:**
- Create: `scripts/report/__init__.py` (empty)
- Create: `scripts/report/validate_artifact.py`
- Modify: `context/PROVENANCE.json`
- Test: `tests/test_validate_artifact.py`

**Interfaces:**
- Consumes: `refresh_context.provenance_entry` from Task 18; the vendored templates from Task 24
- Produces:
  - `class ArtifactStatus(str, Enum)`: `Valid`, `Incomplete`, `SchemaInvalid`, `Missing`, `Unreadable`
  - `@dataclass ValidatorResult`: `status`, `parser_used`, `parse_success`, `sheet_count`, `row_count`, `column_count`, `nonempty_cell_count`, `null_cell_fraction`, `required_fields_present`, `required_fields_complete`, `missing_required_fields`, `all_required_rows_complete`, `validation_notes`
  - `required_fields(spec_path, section) -> list[str]`
  - `validate_geo_xlsx(*, file_path, geo_template_path) -> ValidatorResult`
  - `validate_sra_xlsx(*, file_path, sra_spec_path, section) -> ValidatorResult`
  - `validate_pride_px(*, file_path, pride_spec_path) -> ValidatorResult`
  - `DISPOSITION = {ArtifactStatus.Valid: "CLEAN", ...}` mapping onto CLEAN / SOFT_FLAG / HARD_REJECT

**Context:** the upstream `tools/hibayes/artifact_validator.py` is 897 lines and imports `tools.hibayes.enums` and `tools.hibayes.exporter`, most of it a 29-column evidence-CSV harness this plugin has no use for. Vendor only `ValidatorResult`, `validate_geo_xlsx`, `_load_and_validate_geo_template`, and the `ArtifactStatus` enum — roughly 250 lines — then add SRA and PRIDE. Record the subsetting as `local_divergence`.

Upstream's two-part required-field check, which is the valuable part and must be preserved: (i) each single-`*`-prefixed required field is present as a **column header**, and (ii) each required column is **non-null on every data row**. An earlier upstream version flattened every cell to one string and substring-scanned, which conflated header presence with an arbitrary mention.

- [ ] **Step 1: Read the upstream implementation before copying**

Run:

```bash
sed -n '95,330p' /home/cdemu/code/dmac/dmac-assistant/tools/hibayes/artifact_validator.py
sed -n '1,39p'   /home/cdemu/code/dmac/dmac-assistant/tools/hibayes/enums.py
```

Note in particular the read-only-workbook trap upstream documents: in
`read_only=True` mode the archive is closed by `wb.close()`, so **all** cell data
must be collected in a single pass before closing.

- [ ] **Step 2: Write the failing test**

Create `tests/test_validate_artifact.py`:

```python
"""Rendered-artifact validation. A format is not supported without one."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import validate_artifact as va  # noqa: E402


def _xlsx(path, headers, rows):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


GEO_REQUIRED = ["*library name", "*title", "*library strategy", "*organism",
                "*molecule", "*single or paired-end", "*instrument model",
                "*raw file"]


def test_status_enum_has_the_five_upstream_members():
    assert {s.value for s in va.ArtifactStatus} == {
        "Valid", "Incomplete", "SchemaInvalid", "Missing", "Unreadable"}


def test_disposition_maps_onto_the_pipeline_vocabulary():
    assert va.DISPOSITION[va.ArtifactStatus.Valid] == "CLEAN"
    assert va.DISPOSITION[va.ArtifactStatus.Incomplete] == "SOFT_FLAG"
    assert va.DISPOSITION[va.ArtifactStatus.SchemaInvalid] == "HARD_REJECT"
    assert va.DISPOSITION[va.ArtifactStatus.Missing] == "HARD_REJECT"
    assert va.DISPOSITION[va.ArtifactStatus.Unreadable] == "HARD_REJECT"


def test_required_fields_reads_single_star_keys():
    req = va.required_fields(ASSETS / "GEO-updated.json", "samples")
    assert "*library name" in req
    assert "**tissue" not in req, "double-star is conditionally required, not required"
    assert 3 <= len(req) <= 25


def test_required_fields_for_sra_libraries():
    req = va.required_fields(ASSETS / "SRA.json", "libraries")
    assert isinstance(req, list)


def test_missing_file_is_Missing(tmp_path):
    r = va.validate_geo_xlsx(file_path=tmp_path / "nope.xlsx",
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Missing


def test_unreadable_file_is_Unreadable(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not a zip archive")
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Unreadable


def test_missing_required_header_is_SchemaInvalid(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, ["*library name", "*title"], [["L1", "T1"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid
    assert r.required_fields_present is False
    assert "*organism" in r.missing_required_fields


def test_all_headers_present_but_a_null_row_is_Incomplete(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"],
           ["L2", "T2", "RNA-Seq", None, "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r2.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Incomplete
    assert r.required_fields_present is True
    assert r.all_required_rows_complete is False


def test_complete_workbook_is_Valid(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.status is va.ArtifactStatus.Valid
    assert r.required_fields_complete is True
    assert r.row_count == 2  # header + 1 data row


def test_header_matching_is_case_insensitive(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, [h.upper() for h in GEO_REQUIRED],
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.required_fields_present is True


def test_a_whitespace_only_cell_counts_as_null(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "   ", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.all_required_rows_complete is False


def test_required_present_but_no_data_rows_is_Valid_with_zero_rows(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED, [])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.required_fields_present is True


def test_structural_counts_are_reported(tmp_path):
    p = tmp_path / "geo.xlsx"
    _xlsx(p, GEO_REQUIRED,
          [["L1", "T1", "RNA-Seq", "Homo sapiens", "polyA RNA",
            "paired-end", "Illumina NextSeq 500", "r1.fastq.gz"]])
    r = va.validate_geo_xlsx(file_path=p,
                             geo_template_path=ASSETS / "GEO-updated.json")
    assert r.sheet_count == 1
    assert r.column_count == len(GEO_REQUIRED)
    assert r.nonempty_cell_count > 0
    assert 0.0 <= r.null_cell_fraction <= 1.0


def test_validation_survives_a_workbook_with_zero_sheets(tmp_path):
    """openpyxl cannot make one, so assert the branch exists instead."""
    src = (REPO / "scripts" / "report" / "validate_artifact.py").read_text()
    assert "zero sheets" in src


def test_sra_libraries_validation(tmp_path):
    p = tmp_path / "sra.xlsx"
    req = va.required_fields(ASSETS / "SRA.json", "libraries")
    _xlsx(p, req or ["sample_name"], [["x"] * (len(req) or 1)])
    r = va.validate_sra_xlsx(file_path=p, sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status in (va.ArtifactStatus.Valid, va.ArtifactStatus.Incomplete)


def test_sra_missing_file_is_Missing(tmp_path):
    r = va.validate_sra_xlsx(file_path=tmp_path / "nope.xlsx",
                             sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status is va.ArtifactStatus.Missing


def test_pride_validates_a_tab_delimited_file_not_a_spreadsheet(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text(
        "MTD\tsubmitter_name\tJane Doe\n"
        "FMH\tfile_id\tfile_type\tfile_path\n"
        "FME\t1\traw\t/data/a.raw\n"
        "SMH\tfile_id\tspecies\ttissue\tinstrument\n"
        "SME\t1\tHomo sapiens\tliver\tOrbitrap\n"
    )
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Valid
    assert r.parser_used == "px-tsv"


def test_pride_rejects_a_file_with_no_MTD_lines(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text("FMH\tfile_id\nFME\t1\n")
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid
    assert "MTD" in r.validation_notes


def test_pride_rejects_an_unknown_line_prefix(tmp_path):
    p = tmp_path / "submission.px"
    p.write_text("MTD\ta\tb\nZZZ\tbogus\n")
    r = va.validate_pride_px(file_path=p, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.SchemaInvalid


def test_pride_missing_file_is_Missing(tmp_path):
    r = va.validate_pride_px(file_path=tmp_path / "nope.px",
                             pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Missing


def test_provenance_records_the_subsetting():
    import json
    prov = json.loads((REPO / "context" / "PROVENANCE.json").read_text())
    entry = prov["entries"]["scripts/report/validate_artifact.py"]
    assert entry["source_repo"] == "dmac-assistant"
    assert "subset" in entry["local_divergence"].lower()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_validate_artifact.py -v`
Expected: `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 4: Write `scripts/report/validate_artifact.py`**

Create `scripts/report/__init__.py` (empty), then:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Validate a rendered submission artifact.

A format is not "supported" until it has a renderer AND a validator. This is the
validator half.

VENDORED, IN PART, from tavjo/dmac-assistant `tools/hibayes/artifact_validator.py`.
Upstream is 897 lines and imports `tools.hibayes.enums` and
`tools.hibayes.exporter`; most of it is a 29-column evidence-CSV harness this
plugin has no use for. Taken here: the ArtifactStatus enum, ValidatorResult, the
GEO required-field logic, and the read-only-workbook single-pass discipline.
Added here: SRA (two sections) and PRIDE (tab-delimited, not a spreadsheet).
See context/PROVENANCE.json.

The valuable part of upstream's GEO check, preserved verbatim in spirit: TWO
independent checks, not one. (i) each single-`*`-prefixed required field is
present as a COLUMN HEADER, and (ii) each required column is NON-NULL on every
data row. An earlier upstream version flattened every cell into one string and
substring-scanned for field names, which conflated header presence with an
arbitrary mention -- `*title` appearing in a free-form study cell falsely
satisfied "present".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ArtifactStatus(str, Enum):
    Valid = "Valid"
    Incomplete = "Incomplete"
    SchemaInvalid = "SchemaInvalid"
    Missing = "Missing"
    Unreadable = "Unreadable"


# Maps onto the pipeline's QA vocabulary (PHASES.md Phase 9).
DISPOSITION = {
    ArtifactStatus.Valid: "CLEAN",
    ArtifactStatus.Incomplete: "SOFT_FLAG",
    ArtifactStatus.SchemaInvalid: "HARD_REJECT",
    ArtifactStatus.Missing: "HARD_REJECT",
    ArtifactStatus.Unreadable: "HARD_REJECT",
}


@dataclass
class ValidatorResult:
    """Per-artifact validator output."""

    status: ArtifactStatus
    parser_used: str | None = None
    parse_success: bool | None = None
    sheet_count: int | None = None
    row_count: int | None = None
    column_count: int | None = None
    nonempty_cell_count: int | None = None
    null_cell_fraction: float | None = None
    required_fields_present: bool | None = None
    required_fields_complete: bool | None = None
    missing_required_fields: str | None = None
    all_required_rows_complete: bool | None = None
    validation_notes: str = ""

    @property
    def disposition(self) -> str:
        return DISPOSITION[self.status]


def required_fields(spec_path: Path, section: str) -> list[str]:
    """Single-`*`-prefixed keys of `spec[section][0]`.

    A single `*` means required. A double `**` means conditionally required and
    is deliberately excluded: GEO's `**tissue` and `**cell line` are alternatives,
    and demanding both would reject every valid workbook.

    KNOWN GAP, verified: SRA's `libraries` section marks NOTHING with `*` -
    `sample_name`, `library_ID`, `library_strategy` and the rest are all bare.
    So this returns [] for it, and _validate_xlsx then reports Valid for any
    readable workbook. That is honest (the template asserts no requirements) but
    weak. `biosamples` DOES star its required fields, so SRA is not unguarded
    overall. If SRA library validation needs teeth, add an explicit required
    list here rather than inventing stars in the vendored template - the
    template's provenance entry says `local_divergence: none` and it should
    stay that way.
    """
    spec = json.loads(Path(spec_path).read_text())
    rows = spec.get(section)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise SystemExit(
            f"{spec_path}: section {section!r} must be a non-empty list whose "
            f"first element is a dict"
        )
    return [k for k in rows[0]
            if k.startswith("*") and not k.startswith("**")]


def _read_sheet_once(ws) -> tuple[list[str], list[tuple], int, int]:
    """Collect header, data rows and cell counts in ONE pass.

    In read_only mode the underlying archive closes with the workbook, and any
    later iter_rows on the worksheet raises. Everything must be gathered here.
    """
    header: list[str] = []
    data: list[tuple[Any, ...]] = []
    nonempty = total = 0
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = ["" if v is None else str(v) for v in row]
        else:
            data.append(row)
        for value in row:
            total += 1
            if value not in (None, ""):
                nonempty += 1
    return header, data, nonempty, total


def _check_required(header: list[str], data: list[tuple],
                    required: list[str]) -> tuple[bool, bool, str | None]:
    """(headers_present, rows_complete, missing_summary)."""
    header_lower = [h.strip().lower() for h in header]
    missing_headers = [r for r in required if r.lower() not in header_lower]
    present = not missing_headers

    rows_complete = True
    per_row_missing: list[str] = []
    for r in required:
        if r.lower() not in header_lower:
            continue
        col = header_lower.index(r.lower())
        for row in data:
            if col >= len(row):
                rows_complete = False
                per_row_missing.append(r)
                break
            cell = row[col]
            if cell is None or (isinstance(cell, str) and cell.strip() == ""):
                rows_complete = False
                per_row_missing.append(r)
                break

    all_missing = list(missing_headers) + per_row_missing
    return present, rows_complete, (";".join(all_missing) if all_missing else None)


def _validate_xlsx(file_path: Path, required: list[str],
                   parser_note: str) -> ValidatorResult:
    file_path = Path(file_path)
    if not file_path.exists():
        return ValidatorResult(status=ArtifactStatus.Missing,
                               validation_notes=f"file not at {file_path}")
    try:
        import openpyxl
    except ImportError:
        return ValidatorResult(status=ArtifactStatus.Unreadable,
                               parser_used="openpyxl", parse_success=False,
                               validation_notes="openpyxl not importable")
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        return ValidatorResult(status=ArtifactStatus.Unreadable,
                               parser_used="openpyxl", parse_success=False,
                               validation_notes=f"openpyxl error: {type(exc).__name__}")

    sheet_count = len(wb.sheetnames)
    if sheet_count == 0:
        wb.close()
        return ValidatorResult(status=ArtifactStatus.SchemaInvalid,
                               parser_used="openpyxl", parse_success=True,
                               sheet_count=0,
                               validation_notes="workbook has zero sheets")

    ws = wb[wb.sheetnames[0]]
    row_count = ws.max_row or 0
    column_count = ws.max_column or 0
    header, data, nonempty, total = _read_sheet_once(ws)
    wb.close()

    present, rows_complete, missing = _check_required(header, data, required)
    if not present:
        status = ArtifactStatus.SchemaInvalid
    elif not rows_complete:
        status = ArtifactStatus.Incomplete
    else:
        status = ArtifactStatus.Valid

    return ValidatorResult(
        status=status,
        parser_used="openpyxl",
        parse_success=True,
        sheet_count=sheet_count,
        row_count=row_count,
        column_count=column_count,
        nonempty_cell_count=nonempty,
        null_cell_fraction=((total - nonempty) / total) if total else None,
        required_fields_present=present,
        required_fields_complete=present and rows_complete,
        missing_required_fields=missing,
        all_required_rows_complete=rows_complete if present else False,
        validation_notes=parser_note,
    )


def validate_geo_xlsx(*, file_path: Path,
                      geo_template_path: Path | None) -> ValidatorResult:
    """GEO `.xlsx`: structural counts plus the two-part required-field check."""
    required = (required_fields(geo_template_path, "samples")
                if geo_template_path and Path(geo_template_path).is_file() else [])
    return _validate_xlsx(file_path, required, "GEO samples section")


def validate_sra_xlsx(*, file_path: Path, sra_spec_path: Path,
                      section: str = "libraries") -> ValidatorResult:
    """SRA `.xlsx`. Two workbooks ship: `libraries` and `biosamples`."""
    required = (required_fields(sra_spec_path, section)
                if Path(sra_spec_path).is_file() else [])
    return _validate_xlsx(file_path, required, f"SRA {section} section")


def validate_pride_px(*, file_path: Path, pride_spec_path: Path) -> ValidatorResult:
    """PRIDE submission summary file - TAB-DELIMITED, not a spreadsheet.

    pride.json declares output_type 'tab-delimited PRIDE submission summary
    file' with line prefixes MTD / FMH / FME / SMH / SME / COM. chat_nextseek's
    e2e catalog asserts `pride.xlsx`, which is the wrong artifact type.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return ValidatorResult(status=ArtifactStatus.Missing,
                               validation_notes=f"file not at {file_path}")
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ValidatorResult(status=ArtifactStatus.Unreadable,
                               parser_used="px-tsv", parse_success=False,
                               validation_notes=f"unreadable: {type(exc).__name__}")

    spec = json.loads(Path(pride_spec_path).read_text())
    allowed = set((spec["format"]["line_prefixes"]).values())

    lines = [l for l in text.splitlines() if l.strip()]
    seen: dict[str, int] = {}
    bad: list[str] = []
    nonempty = 0
    for line in lines:
        prefix = line.split("\t", 1)[0]
        if prefix not in allowed:
            bad.append(prefix)
            continue
        seen[prefix] = seen.get(prefix, 0) + 1
        nonempty += sum(1 for f in line.split("\t") if f.strip())

    notes = []
    if bad:
        notes.append(f"unknown line prefixes: {sorted(set(bad))[:5]}")
    if not seen.get("MTD"):
        notes.append("no MTD (metadata) lines")
    if not seen.get("SME"):
        notes.append("no SME (sample metadata) rows")

    if bad or not seen.get("MTD"):
        status = ArtifactStatus.SchemaInvalid
    elif not seen.get("SME"):
        status = ArtifactStatus.Incomplete
    else:
        status = ArtifactStatus.Valid

    return ValidatorResult(
        status=status,
        parser_used="px-tsv",
        parse_success=True,
        sheet_count=1,
        row_count=len(lines),
        column_count=max((len(l.split("\t")) for l in lines), default=0),
        nonempty_cell_count=nonempty,
        required_fields_present=bool(seen.get("MTD")),
        all_required_rows_complete=bool(seen.get("SME")),
        validation_notes="; ".join(notes) or "px line prefixes valid",
    )
```

- [ ] **Step 5: Record the vendoring provenance**

```bash
uv run python3 - <<'PY'
import sys, pathlib, datetime, subprocess
sys.path.insert(0, "scripts")
import refresh_context as rc

SRC = pathlib.Path("/home/cdemu/code/dmac/dmac-assistant")
sha = subprocess.run(["git", "-C", str(SRC), "rev-parse", "HEAD"],
                     capture_output=True, text=True).stdout.strip() or None
prov = rc.read_provenance()
prov["entries"]["scripts/report/validate_artifact.py"] = rc.provenance_entry(
    source_repo="dmac-assistant",
    source_path="tools/hibayes/artifact_validator.py",
    commit_sha=sha,
    vendored_date=datetime.date.today().isoformat(),
    local_divergence=(
        "SUBSET plus extension. Upstream is 897 lines and imports "
        "tools.hibayes.enums and tools.hibayes.exporter; most of it is a "
        "29-column evidence-CSV harness (run_stage_a, CSV_HEADER_29, "
        "rebase_artifact_path, classify_artifact_kind, the nf-core and SVG "
        "validators) that this plugin has no use for. Taken: ArtifactStatus, "
        "ValidatorResult, the GEO two-part required-field check, and the "
        "single-pass read-only-workbook discipline. Added: SRA (libraries and "
        "biosamples sections) and PRIDE (tab-delimited px, not xlsx), plus a "
        "DISPOSITION map onto CLEAN/SOFT_FLAG/HARD_REJECT."
    ),
)
rc.write_provenance(prov)
print("recorded")
PY
```

- [ ] **Step 6: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_validate_artifact.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/report/ context/PROVENANCE.json tests/test_validate_artifact.py
git commit -m "feat(report): vendor the artifact validator, extend to SRA and PRIDE

Subset of dmac-assistant's tools/hibayes/artifact_validator.py (897 lines, most
of it a 29-column evidence-CSV harness). Taken: ArtifactStatus, ValidatorResult,
the GEO two-part required-field check, and the single-pass read-only-workbook
discipline. The two-part check is the valuable bit -- header presence AND
per-row non-null are independent, because an earlier upstream version
substring-scanned a flattened workbook and let '*title' in a free-form study
cell falsely satisfy 'present'.

Added: SRA (libraries and biosamples) and PRIDE. PRIDE validates a TAB-DELIMITED
submission summary file with MTD/FMH/FME/SMH/SME line prefixes, because that is
what pride.json declares -- not a spreadsheet.

Statuses map onto the pipeline's CLEAN / SOFT_FLAG / HARD_REJECT vocabulary.
Subsetting recorded in context/PROVENANCE.json.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 26: Input adapters, all normalizing to one shape

**Files:**
- Create: `scripts/report/adapters.py`
- Test: `tests/test_report_adapters.py`

**Interfaces:**
- Consumes: nothing from other report modules
- Produces:
  - `@dataclass NormalizedSample`: `sample_type: str`, `uid: str`, `metadata: dict`, `parent: str | None`
  - `@dataclass NormalizedInput`: `samples: list[NormalizedSample]`, `source: dict`
  - `adapt_uids(uids, *, fetch=None) -> NormalizedInput`
  - `adapt_retrieve_txt(path, *, fetch=None) -> NormalizedInput`
  - `adapt_nextseek_workbook(path) -> NormalizedInput`
  - `adapt_curated_sheet(path) -> NormalizedInput`
  - `adapt_tabular(path, *, sample_type=None) -> NormalizedInput`
  - `detect_adapter(target) -> str`
  - `adapt(target, **kwargs) -> NormalizedInput`
  - `index_by_uid(normalized) -> dict[str, NormalizedSample]`
  - `resolve_via_lineage(sample, by_uid, key, *, max_depth=12) -> str | None`

**Context (report spec O3):** inputs are **not** a mode switch; they are adapters normalizing into one internal shape. All downstream steps — protocol resolution, the LLM mapping step, rendering, validation — are adapter-agnostic and see only that shape. The NExtSEEK API response is nested five levels (`data.data[i].samples[j].metadata`) and lineage is the flat `Parent` key, an upward UID pointer, **not** nesting.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_adapters.py`:

```python
"""Every input adapter emits the identical normalized shape."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402


def _xlsx(path, sheets):
    """sheets: {name: (headers, rows)}"""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    first = True
    for name, (headers, rows) in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        ws.title = name
        first = False
        ws.append(headers)
        for r in rows:
            ws.append(r)
    wb.save(path)


API_RESPONSE = {
    "data": {
        "data": [
            {"samples": [
                {"metadata": {"UID": "D.SEQ-1", "SampleType": "D.SEQ",
                              "Parent": "RNA-1", "Name": "seq1"}},
                {"metadata": {"UID": "RNA-1", "SampleType": "RNA",
                              "Parent": "TIS-1", "Name": "rna1"}},
            ]},
            {"samples": [
                {"metadata": {"UID": "TIS-1", "SampleType": "TIS",
                              "Parent": None, "Tissue": "liver"}},
            ]},
        ]
    }
}


def test_adapt_uids_walks_the_five_level_response():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda uids: API_RESPONSE)
    assert len(got.samples) == 3
    by_uid = ad.index_by_uid(got)
    assert by_uid["D.SEQ-1"].sample_type == "D.SEQ"
    assert by_uid["D.SEQ-1"].parent == "RNA-1"
    assert by_uid["TIS-1"].metadata["Tissue"] == "liver"


def test_adapt_uids_records_its_source():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda uids: API_RESPONSE)
    assert got.source["adapter"] == "uids"
    assert got.source["uids"] == ["D.SEQ-1"]


def test_adapt_uids_with_no_fetcher_returns_empty():
    """Enrichment is additive, never required."""
    got = ad.adapt_uids(["D.SEQ-1"], fetch=None)
    assert got.samples == []


def test_adapt_retrieve_txt(tmp_path):
    p = tmp_path / "RETRIEVE.TXT"
    p.write_text("D.SEQ-1\n\nD.SEQ-2\n")
    got = ad.adapt_retrieve_txt(p, fetch=lambda uids: API_RESPONSE)
    assert got.source["uids"] == ["D.SEQ-1", "D.SEQ-2"]


def test_adapt_nextseek_workbook_reads_per_type_sheets(tmp_path):
    p = tmp_path / "Lab_AllMetadata_260721.xlsx"
    _xlsx(p, {
        "D.SEQ": (["UID", "Parent", "LibraryLayout"],
                  [["D.SEQ-1", "RNA-1", "paired"]]),
        "RNA": (["UID", "Parent"], [["RNA-1", "TIS-1"]]),
    })
    got = ad.adapt_nextseek_workbook(p)
    by_uid = ad.index_by_uid(got)
    assert by_uid["D.SEQ-1"].sample_type == "D.SEQ"
    assert by_uid["D.SEQ-1"].parent == "RNA-1"
    assert by_uid["D.SEQ-1"].metadata["LibraryLayout"] == "paired"


def test_adapt_nextseek_workbook_infers_type_from_uid_when_no_column(tmp_path):
    p = tmp_path / "x_AllMetadata.xlsx"
    _xlsx(p, {"Sheet1": (["UID", "Parent"], [["D.SEQ-190903KAM-3", "RNA-1"]])})
    got = ad.adapt_nextseek_workbook(p)
    assert got.samples[0].sample_type == "D.SEQ"


def test_adapt_curated_sheet_parses_json_metadata(tmp_path):
    """The flat Arm{X}.xlsx shape: the payload lives in json_metadata."""
    p = tmp_path / "ArmA.xlsx"
    meta = json.dumps({"UID": "D.SEQ-1", "Parent": "RNA-1",
                       "LibraryLayout": "paired", "Notes": "n"})
    _xlsx(p, {"Samples": (["uid", "sampletype", "parent", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "RNA-1", meta]])})
    got = ad.adapt_curated_sheet(p)
    s = got.samples[0]
    assert s.uid == "D.SEQ-1"
    assert s.sample_type == "D.SEQ"
    assert s.parent == "RNA-1"
    assert s.metadata["LibraryLayout"] == "paired"


def test_adapt_curated_sheet_works_before_upload(tmp_path):
    """No API call, no network. That is the point of this adapter."""
    p = tmp_path / "ArmA.xlsx"
    _xlsx(p, {"Samples": (["uid", "sampletype", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "{}"]])})
    got = ad.adapt_curated_sheet(p)
    assert got.source["adapter"] == "curated_sheet"
    assert len(got.samples) == 1


def test_adapt_curated_sheet_survives_malformed_json(tmp_path):
    p = tmp_path / "ArmA.xlsx"
    _xlsx(p, {"Samples": (["uid", "sampletype", "json_metadata"],
                          [["D.SEQ-1", "D.SEQ", "{not json"]])})
    got = ad.adapt_curated_sheet(p)
    assert got.samples[0].uid == "D.SEQ-1"
    assert got.samples[0].metadata.get("_json_metadata_error")


def test_adapt_tabular_csv(tmp_path):
    p = tmp_path / "anything.csv"
    p.write_text("SampleName,Organism\nS1,Homo sapiens\nS2,Homo sapiens\n")
    got = ad.adapt_tabular(p, sample_type="D.SEQ")
    assert len(got.samples) == 2
    assert got.samples[0].metadata["Organism"] == "Homo sapiens"
    assert got.samples[0].sample_type == "D.SEQ"


def test_adapt_tabular_xlsx(tmp_path):
    p = tmp_path / "anything.xlsx"
    _xlsx(p, {"Sheet1": (["SampleName", "Organism"], [["S1", "Homo sapiens"]])})
    got = ad.adapt_tabular(p)
    assert got.samples[0].metadata["SampleName"] == "S1"


def test_every_adapter_emits_the_identical_shape(tmp_path):
    """The contract that makes downstream steps adapter-agnostic."""
    wb = tmp_path / "m_AllMetadata.xlsx"
    _xlsx(wb, {"D.SEQ": (["UID", "Parent"], [["D.SEQ-1", "RNA-1"]])})
    arm = tmp_path / "ArmA.xlsx"
    _xlsx(arm, {"Samples": (["uid", "sampletype", "parent", "json_metadata"],
                            [["D.SEQ-1", "D.SEQ", "RNA-1", "{}"]])})
    csv = tmp_path / "x.csv"
    csv.write_text("UID,Parent\nD.SEQ-1,RNA-1\n")

    for got in (ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE),
                ad.adapt_nextseek_workbook(wb),
                ad.adapt_curated_sheet(arm),
                ad.adapt_tabular(csv)):
        assert isinstance(got, ad.NormalizedInput)
        assert isinstance(got.samples, list)
        assert "adapter" in got.source
        for s in got.samples:
            assert isinstance(s, ad.NormalizedSample)
            assert isinstance(s.metadata, dict)
            assert s.parent is None or isinstance(s.parent, str)


def test_detect_adapter_by_filename(tmp_path):
    assert ad.detect_adapter(["D.SEQ-1", "RNA-2"]) == "uids"
    assert ad.detect_adapter(tmp_path / "RETRIEVE.TXT") == "retrieve_txt"
    assert ad.detect_adapter(tmp_path / "Lab_AllMetadata_260721.xlsx") == "nextseek_workbook"
    assert ad.detect_adapter(tmp_path / "ArmA.xlsx") == "curated_sheet"
    assert ad.detect_adapter(tmp_path / "whatever.csv") == "tabular"
    assert ad.detect_adapter(tmp_path / "whatever.xlsx") == "tabular"


def test_resolve_via_lineage_walks_upward():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "Tissue") == "liver"


def test_resolve_via_lineage_prefers_the_leaf_value():
    """Leaf-wins: an existing value on the sample is not overwritten."""
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    by_uid["D.SEQ-1"].metadata["Tissue"] = "tumor"
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "Tissue") == "tumor"


def test_resolve_via_lineage_returns_none_when_unreachable():
    got = ad.adapt_uids(["D.SEQ-1"], fetch=lambda u: API_RESPONSE)
    by_uid = ad.index_by_uid(got)
    assert ad.resolve_via_lineage(by_uid["D.SEQ-1"], by_uid, "CellLine") is None


def test_resolve_via_lineage_survives_a_parent_cycle():
    a = ad.NormalizedSample(sample_type="A", uid="A-1", metadata={}, parent="B-1")
    b = ad.NormalizedSample(sample_type="B", uid="B-1", metadata={}, parent="A-1")
    by_uid = {"A-1": a, "B-1": b}
    assert ad.resolve_via_lineage(a, by_uid, "Tissue") is None


def test_resolve_via_lineage_handles_semicolon_joined_multi_parents():
    leaf = ad.NormalizedSample(sample_type="OOC", uid="OOC-1", metadata={},
                               parent="CEL-1; CEL-2")
    cel2 = ad.NormalizedSample(sample_type="CEL", uid="CEL-2",
                               metadata={"CellLine": "MCF-7"}, parent=None)
    by_uid = {"OOC-1": leaf, "CEL-2": cel2}
    assert ad.resolve_via_lineage(leaf, by_uid, "CellLine") == "MCF-7"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_adapters.py -v`
Expected: `ImportError: cannot import name 'adapters' from 'report'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/report/adapters.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Normalize whatever metadata the curator has into one internal shape.

Inputs are NOT a mode switch. Each adapter emits the same structure, and every
downstream step - protocol resolution, the LLM mapping step, rendering,
validation - is adapter-agnostic and sees only that structure.

    {"samples": [{"sample_type": "D.SEQ",
                  "uid": "D.SEQ-...",
                  "metadata": {<flat key/value>},
                  "parent": "TIS-..."}]}

Lineage is the flat `Parent` key, an upward UID pointer - NOT nesting. The
NExtSEEK retrieve response is nested five levels
(`data.data[i].samples[j].metadata`) and this module flattens it.

Enrichment is additive, never required. An adapter with no fetcher simply
returns no API-sourced samples rather than failing.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

_MAX_LINEAGE_DEPTH = 12


@dataclass
class NormalizedSample:
    sample_type: str
    uid: str
    metadata: dict
    parent: str | None = None


@dataclass
class NormalizedInput:
    samples: list[NormalizedSample] = field(default_factory=list)
    source: dict = field(default_factory=dict)


def _sample_type_from_uid(uid: str) -> str:
    return str(uid).split("-", 1)[0] if uid and "-" in str(uid) else ""


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ── adapters ───────────────────────────────────────────────────────────────

def adapt_uids(uids: list[str], *, fetch=None) -> NormalizedInput:
    """UIDs -> POST /nextseek_api/admin/samples/retrieve/.

    `fetch` is a callable taking a UID list and returning the parsed response,
    so this is testable without a network. With no fetcher, returns no samples:
    enrichment is additive, never required.
    """
    out = NormalizedInput(source={"adapter": "uids", "uids": list(uids)})
    if fetch is None:
        return out
    payload = fetch(list(uids)) or {}
    for group in ((payload.get("data") or {}).get("data") or []):
        for entry in (group.get("samples") or []):
            meta = dict(entry.get("metadata") or {})
            uid = _clean(meta.get("UID")) or ""
            out.samples.append(NormalizedSample(
                sample_type=_clean(meta.get("SampleType")) or _sample_type_from_uid(uid),
                uid=uid,
                metadata=meta,
                parent=_clean(meta.get("Parent")),
            ))
    return out


def adapt_retrieve_txt(path: Path, *, fetch=None) -> NormalizedInput:
    uids = [l.strip() for l in Path(path).read_text().splitlines() if l.strip()]
    out = adapt_uids(uids, fetch=fetch)
    out.source = {"adapter": "retrieve_txt", "path": str(path), "uids": uids}
    return out


def _rows_from_sheet(ws) -> list[dict]:
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        return []
    names = [str(h).strip() if h is not None else "" for h in header]
    out = []
    for row in rows:
        if not any(v not in (None, "") for v in row):
            continue
        out.append({n: v for n, v in zip(names, row) if n and v not in (None, "")})
    return out


def adapt_nextseek_workbook(path: Path) -> NormalizedInput:
    """A downloaded `*_AllMetadata*.xlsx`: one sheet per sample type. No API call."""
    path = Path(path)
    out = NormalizedInput(source={"adapter": "nextseek_workbook", "path": str(path)})
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in wb.sheetnames:
            for rec in _rows_from_sheet(wb[sheet]):
                uid = _clean(rec.get("UID")) or ""
                stype = (_clean(rec.get("SampleType"))
                         or _sample_type_from_uid(uid)
                         or sheet)
                out.samples.append(NormalizedSample(
                    sample_type=stype, uid=uid, metadata=rec,
                    parent=_clean(rec.get("Parent")),
                ))
    finally:
        wb.close()
    return out


def adapt_curated_sheet(path: Path) -> NormalizedInput:
    """A curated flat `Arm{X}.xlsx`. Works BEFORE upload - no API, no network.

    That matters because GEO deposit happens before NExtSEEK upload: accessions
    must be backfilled into the sheets first.
    """
    path = Path(path)
    out = NormalizedInput(source={"adapter": "curated_sheet", "path": str(path)})
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = "Samples" if "Samples" in wb.sheetnames else wb.sheetnames[0]
        for rec in _rows_from_sheet(wb[sheet]):
            uid = _clean(rec.get("uid")) or _clean(rec.get("UID")) or ""
            raw = rec.get("json_metadata")
            meta: dict = {}
            if raw:
                try:
                    meta = json.loads(raw)
                except (TypeError, ValueError) as exc:
                    meta = {"_json_metadata_error": f"{type(exc).__name__}: {exc}"}
            # Denormalized columns fill anything json_metadata lacks.
            for col, key in (("name", "Name"), ("parent", "Parent")):
                if rec.get(col) and not meta.get(key):
                    meta[key] = rec[col]
            meta.setdefault("UID", uid)
            out.samples.append(NormalizedSample(
                sample_type=(_clean(rec.get("sampletype"))
                             or _clean(rec.get("sample_type"))
                             or _sample_type_from_uid(uid)),
                uid=uid,
                metadata=meta,
                parent=_clean(rec.get("parent")) or _clean(meta.get("Parent")),
            ))
    finally:
        wb.close()
    return out


def adapt_tabular(path: Path, *, sample_type: str | None = None) -> NormalizedInput:
    """Arbitrary xlsx or csv. Columns get mapped by the LLM step downstream."""
    path = Path(path)
    out = NormalizedInput(source={"adapter": "tabular", "path": str(path)})
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as f:
            records = [dict(r) for r in csv.DictReader(f)]
    else:
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            records = _rows_from_sheet(wb[wb.sheetnames[0]])
        finally:
            wb.close()
    for rec in records:
        uid = _clean(rec.get("UID")) or _clean(rec.get("uid")) or ""
        out.samples.append(NormalizedSample(
            sample_type=(sample_type or _clean(rec.get("SampleType"))
                         or _sample_type_from_uid(uid)),
            uid=uid, metadata=rec, parent=_clean(rec.get("Parent")),
        ))
    return out


# ── dispatch ───────────────────────────────────────────────────────────────

def detect_adapter(target) -> str:
    """Pick an adapter from what the curator handed us."""
    if isinstance(target, (list, tuple)):
        return "uids"
    p = Path(target)
    name = p.name
    if name.upper() == "RETRIEVE.TXT":
        return "retrieve_txt"
    if "AllMetadata" in name:
        return "nextseek_workbook"
    if p.suffix.lower() == ".xlsx" and name.startswith("Arm") and "_" not in p.stem:
        return "curated_sheet"
    return "tabular"


def adapt(target, **kwargs) -> NormalizedInput:
    which = detect_adapter(target)
    return {
        "uids": lambda: adapt_uids(list(target), fetch=kwargs.get("fetch")),
        "retrieve_txt": lambda: adapt_retrieve_txt(target, fetch=kwargs.get("fetch")),
        "nextseek_workbook": lambda: adapt_nextseek_workbook(target),
        "curated_sheet": lambda: adapt_curated_sheet(target),
        "tabular": lambda: adapt_tabular(target,
                                         sample_type=kwargs.get("sample_type")),
    }[which]()


# ── lineage ────────────────────────────────────────────────────────────────

def index_by_uid(normalized: NormalizedInput) -> dict[str, NormalizedSample]:
    return {s.uid: s for s in normalized.samples if s.uid}


def resolve_via_lineage(sample: NormalizedSample,
                        by_uid: dict[str, NormalizedSample],
                        key: str, *, max_depth: int = _MAX_LINEAGE_DEPTH) -> str | None:
    """Find `key` on this sample, else walk the Parent chain upward.

    Leaf wins: a value already on the sample is never overwritten by an
    ancestor's. Organism, tissue and cell line frequently live on ancestors
    rather than the D.SEQ row, which is what makes this necessary.

    Cycle-safe and depth-bounded: legacy PI data has many-to-many parents and
    is not guaranteed acyclic.
    """
    seen: set[str] = set()
    frontier = [sample]
    depth = 0
    while frontier and depth <= max_depth:
        nxt: list[NormalizedSample] = []
        for node in frontier:
            if node.uid in seen:
                continue
            seen.add(node.uid)
            value = node.metadata.get(key)
            if value not in (None, ""):
                return str(value)
            for parent_uid in str(node.parent or "").split(";"):
                parent_uid = parent_uid.strip()
                if parent_uid and parent_uid in by_uid and parent_uid not in seen:
                    nxt.append(by_uid[parent_uid])
        frontier = nxt
        depth += 1
    return None
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_adapters.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/report/adapters.py tests/test_report_adapters.py
git commit -m "feat(report): input adapters normalizing to one shape

Inputs are not a mode switch. UIDs, RETRIEVE.TXT, a downloaded NExtSEEK
workbook, a curated Arm{X}.xlsx, and arbitrary xlsx/csv all normalize to the
same {sample_type, uid, metadata, parent} shape, so protocol resolution, the LLM
mapping step, rendering and validation are all adapter-agnostic.

The API response is nested five levels (data.data[i].samples[j].metadata) and
lineage is the flat Parent key, an upward UID pointer, not nesting.
resolve_via_lineage walks that chain leaf-first, handles semicolon-joined
many-to-many parents, and is cycle-safe and depth-bounded because legacy PI data
is not guaranteed acyclic.

The curated-sheet adapter works BEFORE upload, with no network -- which matters
because GEO deposit happens before NExtSEEK upload, since accessions must be
backfilled into the sheets first.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 27: Template spec loader and mapping-spec validator

**Files:**
- Create: `scripts/report/mapping.py`
- Test: `tests/test_report_mapping.py`

**Interfaces:**
- Consumes: `adapters.NormalizedInput`, `adapters.index_by_uid` from Task 26; the vendored specs from Task 24
- Produces:
  - `DIRECTIVES = ("source", "via_lineage", "const", "map", "synthesize", "unmapped")`
  - `ROW_SECTION = {"GEO": "samples", "SRA": "libraries", "PRIDE": "sample_metadata"}`
  - `TARGET_SAMPLETYPE = {"GEO": "D.SEQ", "SRA": "D.SEQ", "PRIDE": "D.MSP"}`
  - `@dataclass TemplateSpec`: `report_type`, `sections: dict[str, list[str]]`, `required: dict[str, list[str]]`, `cv: dict[str, list[str]]`, `row_section: str`
  - `load_template_spec(path) -> TemplateSpec`
  - `@dataclass MappingError`: `section`, `field`, `code`, `message`
  - `validate_mapping(mapping, spec, normalized) -> list[MappingError]`
  - `source_columns(normalized) -> set[str]`
  - `cv_for_field(spec, field) -> list[str] | None`

**Context (report spec, decision ANN-6):** *"the LLM determines what the map should be, and if a field needs to be written or synthesized via LLM, and then executes it deterministically."* Both LLM steps are O(columns), not O(rows). Evidence that this matters: chat_nextseek's per-value writer cost **"a 5.1M-token prompt on a 195-UID flow"** (`reports/outputs.py:349-355`) and was hard-bypassed for nf-core.

**Step 5 is the cheapest place to fail.** Validate the mapping before applying it: every target field exists in the template; every required (`*`) field is `source`/`const`/`synthesize` or explicitly `unmapped` with a reason; every `const` and every `map` output is a member of the controlled vocabulary where one exists; every `source` column exists in the input.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_mapping.py`:

```python
"""The mapping spec and its validator - the core of report mode's design."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import mapping as mp  # noqa: E402


def _input(**metadata):
    base = {"UID": "D.SEQ-1", "Parent": "TIS-1", "LibraryLayout": "paired"}
    base.update(metadata)
    return ad.NormalizedInput(
        samples=[
            ad.NormalizedSample(sample_type="D.SEQ", uid="D.SEQ-1",
                                metadata=base, parent="TIS-1"),
            ad.NormalizedSample(sample_type="TIS", uid="TIS-1",
                                metadata={"UID": "TIS-1", "Tissue": "liver"},
                                parent=None),
        ],
        source={"adapter": "curated_sheet", "path": "ArmA.xlsx"},
    )


def _mapping(**samples_over):
    samples = {
        "*library name": {"source": "UID"},
        "*title": {"source": "UID"},
        "*library strategy": {"const": "RNA-Seq"},
        "*organism": {"const": "Homo sapiens"},
        "*molecule": {"const": "polyA RNA"},
        "*single or paired-end": {"source": "LibraryLayout",
                                  "map": {"paired": "paired-end"}},
        "*instrument model": {"const": "Illumina NextSeq 500"},
        "*raw file": {"unmapped": "raw file names are added at deposit time"},
    }
    samples.update(samples_over)
    return {
        "report_type": "GEO",
        "source": {"adapter": "curated_sheet", "path": "ArmA.xlsx"},
        "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 1},
        "samples": samples,
        "study": {"*title": {"synthesize": "study title from manuscript"},
                  "*summary (abstract)": {"synthesize": "abstract"},
                  "*experimental design": {"synthesize": "design"}},
    }


SPEC = None


def spec():
    global SPEC
    if SPEC is None:
        SPEC = mp.load_template_spec(ASSETS / "GEO-updated.json")
    return SPEC


# ---- template spec loading ------------------------------------------------

def test_load_template_spec_reads_sections():
    s = spec()
    assert s.report_type == "GEO"
    assert "*library name" in s.sections["samples"]
    assert "*title" in s.sections["study"]
    assert s.row_section == "samples"


def test_required_excludes_double_star():
    s = spec()
    assert "*organism" in s.required["samples"]
    assert "**tissue" not in s.required["samples"]
    assert "**tissue" in s.sections["samples"]


def test_controlled_vocabulary_is_loaded():
    s = spec()
    assert "RNA-Seq" in s.cv["library_strategy"]
    assert s.cv["library_layout"]


def test_row_section_constants_match_upstream():
    assert mp.ROW_SECTION == {"GEO": "samples", "SRA": "libraries",
                              "PRIDE": "sample_metadata"}
    assert mp.TARGET_SAMPLETYPE == {"GEO": "D.SEQ", "SRA": "D.SEQ",
                                    "PRIDE": "D.MSP"}


def test_sra_spec_loads_with_libraries_as_the_row_section():
    s = mp.load_template_spec(ASSETS / "SRA.json")
    assert s.row_section == "libraries"
    assert "biosamples" in s.sections


def test_pride_spec_loads_with_sample_metadata_as_the_row_section():
    s = mp.load_template_spec(ASSETS / "pride.json")
    assert s.row_section == "sample_metadata"
    assert "project_metadata" in s.sections


# ---- mapping validation ---------------------------------------------------

def test_a_complete_mapping_validates_clean():
    assert mp.validate_mapping(_mapping(), spec(), _input()) == []


def test_unknown_target_field_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"not a real field": {"const": "x"}}), spec(), _input())
    assert any(e.code == "unknown_field" for e in errs)


def test_missing_required_field_is_rejected():
    m = _mapping()
    del m["samples"]["*organism"]
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "required_unmapped" and e.field == "*organism"
               for e in errs)


def test_unmapped_without_a_reason_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"unmapped": ""}}), spec(), _input())
    assert any(e.code == "unmapped_without_reason" for e in errs)


def test_unmapped_with_a_reason_is_accepted():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"unmapped": "not recorded by this PI"}}),
        spec(), _input())
    assert errs == []


def test_source_column_absent_from_the_input_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "NoSuchColumn"}}), spec(), _input())
    assert any(e.code == "source_column_missing" for e in errs)


def test_source_column_found_on_an_ancestor_needs_via_lineage():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "Tissue"}}), spec(), _input())
    assert any(e.code == "needs_via_lineage" for e in errs)


def test_via_lineage_accepts_an_ancestor_only_column():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"source": "Tissue", "via_lineage": True}}),
        spec(), _input())
    assert errs == []


def test_const_outside_the_controlled_vocabulary_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*library strategy": {"const": "RNAseq"}}), spec(), _input())
    assert any(e.code == "const_not_in_cv" for e in errs)
    assert any("RNA-Seq" in e.message for e in errs)


def test_const_inside_the_controlled_vocabulary_is_accepted():
    errs = mp.validate_mapping(
        _mapping(**{"*library strategy": {"const": "RNA-Seq"}}), spec(), _input())
    assert errs == []


def test_map_output_outside_the_controlled_vocabulary_is_rejected():
    """SKILL.md pitfall: GEO dropdowns are word- and case-exact.
    `paired-end` not `paired`; `Illumina NextSeq 500` not `NextSeq 500`."""
    errs = mp.validate_mapping(
        _mapping(**{"*single or paired-end":
                    {"source": "LibraryLayout", "map": {"paired": "paired"}}}),
        spec(), _input())
    assert any(e.code == "map_output_not_in_cv" for e in errs)


def test_a_field_with_no_controlled_vocabulary_accepts_any_const():
    errs = mp.validate_mapping(
        _mapping(**{"*title": {"const": "anything at all"}}), spec(), _input())
    assert errs == []


def test_two_directives_on_one_field_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"const": "Homo sapiens", "source": "UID"}}),
        spec(), _input())
    assert any(e.code == "conflicting_directives" for e in errs)


def test_no_directive_at_all_is_rejected():
    errs = mp.validate_mapping(_mapping(**{"*organism": {}}), spec(), _input())
    assert any(e.code == "no_directive" for e in errs)


def test_an_unrecognized_directive_is_rejected():
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"compute": "x"}}), spec(), _input())
    assert any(e.code == "unknown_directive" for e in errs)


def test_synthesize_is_rejected_in_the_row_section():
    """synthesize is study-level only: it is O(1), not O(rows)."""
    errs = mp.validate_mapping(
        _mapping(**{"*organism": {"synthesize": "the organism"}}),
        spec(), _input())
    assert any(e.code == "synthesize_in_row_section" for e in errs)


def test_row_scope_mismatch_is_rejected():
    m = _mapping()
    m["row_scope"]["expected_rows"] = 99
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "row_count_mismatch" for e in errs)


def test_row_scope_counts_only_the_target_sampletype():
    """The input has a TIS row too; only D.SEQ rows count."""
    assert mp.validate_mapping(_mapping(), spec(), _input()) == []


def test_report_type_mismatch_is_rejected():
    m = _mapping()
    m["report_type"] = "SRA"
    errs = mp.validate_mapping(m, spec(), _input())
    assert any(e.code == "report_type_mismatch" for e in errs)


def test_errors_carry_section_field_code_and_message():
    errs = mp.validate_mapping(
        _mapping(**{"zzz": {"const": "x"}}), spec(), _input())
    e = errs[0]
    assert e.section and e.field and e.code and e.message


def test_source_columns_unions_every_sample():
    cols = mp.source_columns(_input())
    assert "LibraryLayout" in cols
    assert "Tissue" in cols


def test_cv_for_field_maps_geo_field_names_to_cv_keys():
    s = spec()
    assert "RNA-Seq" in mp.cv_for_field(s, "*library strategy")
    assert mp.cv_for_field(s, "*title") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_mapping.py -v`
Expected: `ImportError: cannot import name 'mapping' from 'report'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/report/mapping.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The declarative mapping spec, and the validator that gates it.

The LLM does NOT write cell values. It writes a mapping, once, which is then
applied deterministically to every row. Both LLM steps are O(columns), not
O(rows).

Why this shape: chat_nextseek's report_writer_agent has the LLM emit every cell,
which cost "a 5.1M-token prompt on a 195-UID flow" (reports/outputs.py:349-355)
and was hard-bypassed for nf-core. Its report_coder_agent improves on that by
having the LLM write extraction Python, executed in an AST sandbox with a
row-parity guard. A declarative mapping achieves the same LLM-decides /
code-executes split while being validatable, human-reviewable, cacheable, and
needing no sandbox.

Validating the mapping BEFORE applying it is the cheapest place to fail.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DIRECTIVES = ("source", "via_lineage", "const", "map", "synthesize", "unmapped")

# Exactly one of these must appear per field. `via_lineage` and `map` are
# modifiers on `source`, not directives in their own right.
_PRIMARY_DIRECTIVES = ("source", "const", "synthesize", "unmapped")

ROW_SECTION = {"GEO": "samples", "SRA": "libraries", "PRIDE": "sample_metadata"}
TARGET_SAMPLETYPE = {"GEO": "D.SEQ", "SRA": "D.SEQ", "PRIDE": "D.MSP"}

# GEO/SRA target field -> controlled_vocabulary key. The CV is mined from
# SRA_metadata.xlsx and keyed by SRA's names, not GEO's column headers.
_CV_KEY_FOR_FIELD = {
    "*library strategy": "library_strategy",
    "library_strategy": "library_strategy",
    "library_source": "library_source",
    "library_selection": "library_selection",
    "*single or paired-end": "library_layout",
    "library_layout": "library_layout",
    "platform": "platform",
    "*instrument model": "instrument_model_flat",
    "instrument_model": "instrument_model_flat",
    "filetype": "filetype",
}


@dataclass
class TemplateSpec:
    report_type: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    required: dict[str, list[str]] = field(default_factory=dict)
    cv: dict[str, list[str]] = field(default_factory=dict)
    row_section: str = "samples"
    raw: dict = field(default_factory=dict)


@dataclass
class MappingError:
    section: str
    field: str
    code: str
    message: str


def load_template_spec(path: Path) -> TemplateSpec:
    """Read a vendored `<FORMAT>*.json` into a validatable shape."""
    doc = json.loads(Path(path).read_text())
    report_type = str(doc.get("report_type", "")).upper()

    sections: dict[str, list[str]] = {}
    for key, value in doc.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            sections[key] = list(value[0].keys())
        elif isinstance(value, dict) and key not in (
                "schema", "controlled_vocabulary", "report_writer_guidance",
                "format", "links"):
            if all(not isinstance(v, (dict, list)) or v is None
                   for v in value.values()):
                sections[key] = list(value.keys())

    required = {
        name: [f for f in fields
               if f.startswith("*") and not f.startswith("**")]
        for name, fields in sections.items()
    }
    cv = {k: v for k, v in (doc.get("controlled_vocabulary") or {}).items()
          if isinstance(v, list)}

    return TemplateSpec(
        report_type=report_type,
        sections=sections,
        required=required,
        cv=cv,
        row_section=ROW_SECTION.get(report_type, "samples"),
        raw=doc,
    )


def cv_for_field(spec: TemplateSpec, target_field: str) -> list[str] | None:
    """Allowed values for a target field, or None when it is free text."""
    key = _CV_KEY_FOR_FIELD.get(target_field)
    if key is None:
        return None
    values = spec.cv.get(key)
    return list(values) if values else None


def source_columns(normalized) -> set[str]:
    """Every metadata key present on any sample in the input."""
    out: set[str] = set()
    for s in normalized.samples:
        out.update(s.metadata.keys())
    return out


def _leaf_columns(normalized, target_sampletype: str | None) -> set[str]:
    """Columns present on the TARGET rows, not on ancestors.

    A column that exists only on an ancestor needs `via_lineage: true`; without
    it the executor would silently produce blanks for every row.
    """
    out: set[str] = set()
    for s in normalized.samples:
        if target_sampletype and s.sample_type != target_sampletype:
            continue
        out.update(s.metadata.keys())
    return out


def validate_mapping(mapping: dict, spec: TemplateSpec, normalized) -> list[MappingError]:
    """Check a mapping against the template, its CV, and the actual input.

    Every check here is one the executor would otherwise discover halfway
    through writing rows, or worse, not discover at all.
    """
    errors: list[MappingError] = []

    declared = str(mapping.get("report_type", "")).upper()
    if declared != spec.report_type:
        errors.append(MappingError(
            "_", "report_type", "report_type_mismatch",
            f"mapping declares {declared!r} but the template is "
            f"{spec.report_type!r}"))

    row_scope = mapping.get("row_scope") or {}
    target_type = row_scope.get("target_sampletype") or TARGET_SAMPLETYPE.get(
        spec.report_type)
    actual_rows = sum(1 for s in normalized.samples
                      if not target_type or s.sample_type == target_type)
    expected = row_scope.get("expected_rows")
    if expected is not None and expected != actual_rows:
        errors.append(MappingError(
            "_", "row_scope", "row_count_mismatch",
            f"mapping expects {expected} rows of {target_type!r} but the input "
            f"has {actual_rows}"))

    all_cols = source_columns(normalized)
    leaf_cols = _leaf_columns(normalized, target_type)

    for section, fields in mapping.items():
        if section in ("report_type", "source", "row_scope") or not isinstance(fields, dict):
            continue
        known = spec.sections.get(section)
        if known is None:
            errors.append(MappingError(
                section, "_", "unknown_section",
                f"template has no section {section!r}; it has "
                f"{sorted(spec.sections)}"))
            continue

        for target, directive in fields.items():
            if target not in known:
                errors.append(MappingError(
                    section, target, "unknown_field",
                    f"{target!r} is not a field of {section!r}"))
                continue
            if not isinstance(directive, dict):
                errors.append(MappingError(
                    section, target, "no_directive",
                    f"{target!r} must map to an object, got {type(directive).__name__}"))
                continue

            unknown = set(directive) - set(DIRECTIVES)
            if unknown:
                errors.append(MappingError(
                    section, target, "unknown_directive",
                    f"{target!r} uses {sorted(unknown)}; allowed: {list(DIRECTIVES)}"))

            primaries = [d for d in _PRIMARY_DIRECTIVES if d in directive]
            if not primaries:
                errors.append(MappingError(
                    section, target, "no_directive",
                    f"{target!r} has no source/const/synthesize/unmapped"))
                continue
            if len(primaries) > 1:
                errors.append(MappingError(
                    section, target, "conflicting_directives",
                    f"{target!r} has {primaries}; exactly one is allowed"))
                continue

            which = primaries[0]

            if which == "unmapped" and not str(directive["unmapped"]).strip():
                errors.append(MappingError(
                    section, target, "unmapped_without_reason",
                    f"{target!r} is unmapped with no stated reason"))

            if which == "synthesize" and section == spec.row_section:
                errors.append(MappingError(
                    section, target, "synthesize_in_row_section",
                    f"{target!r} uses synthesize in the row section; synthesize "
                    f"is study-level only, so it stays O(1) rather than O(rows)"))

            if which == "source":
                column = directive["source"]
                if column not in all_cols:
                    errors.append(MappingError(
                        section, target, "source_column_missing",
                        f"{target!r} sources {column!r}, absent from the input"))
                elif column not in leaf_cols and not directive.get("via_lineage"):
                    errors.append(MappingError(
                        section, target, "needs_via_lineage",
                        f"{target!r} sources {column!r}, which exists only on "
                        f"ancestor samples. Add \"via_lineage\": true, or every "
                        f"row will be blank."))

            allowed = cv_for_field(spec, target)
            if allowed:
                if which == "const" and directive["const"] not in allowed:
                    errors.append(MappingError(
                        section, target, "const_not_in_cv",
                        f"{target!r} const {directive['const']!r} is not in the "
                        f"controlled vocabulary. Nearest allowed: "
                        f"{_nearest(directive['const'], allowed)}"))
                for out_value in (directive.get("map") or {}).values():
                    if out_value not in allowed:
                        errors.append(MappingError(
                            section, target, "map_output_not_in_cv",
                            f"{target!r} map emits {out_value!r}, not in the "
                            f"controlled vocabulary. Nearest allowed: "
                            f"{_nearest(out_value, allowed)}"))

    for section, req_fields in spec.required.items():
        if section not in mapping:
            continue
        mapped = mapping[section]
        if not isinstance(mapped, dict):
            continue
        for req in req_fields:
            if req not in mapped:
                errors.append(MappingError(
                    section, req, "required_unmapped",
                    f"required field {req!r} has no directive. Give it "
                    f"source/const/synthesize, or unmapped with a reason."))

    return errors


def _nearest(value: str, allowed: list[str], limit: int = 3) -> list[str]:
    """Closest allowed values, so an error message is actionable.

    GEO dropdowns are word- and case-exact: `paired-end` not `paired`,
    `Illumina NextSeq 500` not `NextSeq 500`.
    """
    import difflib
    hits = difflib.get_close_matches(str(value), allowed, n=limit, cutoff=0.4)
    return hits or allowed[:limit]
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_mapping.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/report/mapping.py tests/test_report_mapping.py
git commit -m "feat(report): mapping spec plus the validator that gates it

The LLM writes a declarative mapping once, O(columns); the executor applies it
to every row, deterministically. chat_nextseek's per-cell writer cost a
5.1M-token prompt on a 195-UID flow and was hard-bypassed for nf-core.

Validating before applying is the cheapest place to fail. Checks: unknown target
field or section, required field with no directive, unmapped with no reason,
conflicting or missing directives, source column absent from the input, const or
map output outside the controlled vocabulary (with nearest-match suggestions,
since GEO dropdowns are word- and case-exact), row-count mismatch, and
synthesize used in the row section, which would make it O(rows).

needs_via_lineage is the check that earns its place: a column present only on
ancestor samples silently yields a blank on every row without it, and organism,
tissue and cell line routinely live on ancestors rather than the D.SEQ row.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 28: The executor, row parity, and graceful degradation

**Files:**
- Create: `scripts/report/execute.py`
- Test: `tests/test_report_execute.py`

**Interfaces:**
- Consumes: `adapters.index_by_uid`, `adapters.resolve_via_lineage` from Task 26; `mapping.TemplateSpec`, `mapping.TARGET_SAMPLETYPE` from Task 27; `_common.placeholder` from Task 9
- Produces:
  - `@dataclass Gap`: `section`, `field`, `reason`, `searched`, `uid`
  - `apply_mapping(mapping, spec, normalized, *, synthesized=None) -> tuple[dict, list[Gap]]`
  - `write_filled(root, report_type, filled) -> Path`
  - `render_completeness(report_type, gaps, mapping, normalized) -> str`
  - `write_completeness(root, report_type, markdown) -> Path`
  - `RowParityError`

**Context (report spec):** unfillable fields **degrade, they do not abort**. Emit the plugin's existing `*** PLACEHOLDER: <what is missing> ***` marker (SKILL.md hard rule 8 — greppable, unlike a blank) and a completeness report naming each unfilled required field, the input that was searched, and why it failed. The curator decides. **Never silently fabricate; never refuse outright.**

**Row parity:** chat_nextseek gates on `_REPORT_CODE_PATH_THRESHOLD = 20` and discards the deterministic result if `len(result[row_key]) != expected_count`. Their own assessment calls this guard "the single most valuable idea to carry over". Our design gets it more cheaply — the executor controls row count by construction, so parity is structural — but assert it anyway.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_execute.py`:

```python
"""Deterministic execution of a validated mapping."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import execute as ex  # noqa: E402
from report import mapping as mp  # noqa: E402

SPEC = mp.load_template_spec(ASSETS / "GEO-updated.json")


def _input(n=2):
    samples = [ad.NormalizedSample(
        sample_type="D.SEQ", uid=f"D.SEQ-{i}",
        metadata={"UID": f"D.SEQ-{i}", "Parent": "TIS-1",
                  "LibraryLayout": "paired"},
        parent="TIS-1") for i in range(1, n + 1)]
    samples.append(ad.NormalizedSample(
        sample_type="TIS", uid="TIS-1",
        metadata={"UID": "TIS-1", "Tissue": "liver"}, parent=None))
    return ad.NormalizedInput(samples=samples,
                              source={"adapter": "curated_sheet"})


def _mapping(n=2, **over):
    samples = {
        "*library name": {"source": "UID"},
        "*title": {"source": "UID"},
        "*library strategy": {"const": "RNA-Seq"},
        "*organism": {"const": "Homo sapiens"},
        "**tissue": {"source": "Tissue", "via_lineage": True},
        "*molecule": {"const": "polyA RNA"},
        "*single or paired-end": {"source": "LibraryLayout",
                                  "map": {"paired": "paired-end"}},
        "*instrument model": {"const": "Illumina NextSeq 500"},
        "*raw file": {"unmapped": "added at deposit time"},
    }
    samples.update(over)
    return {"report_type": "GEO",
            "source": {"adapter": "curated_sheet"},
            "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": n},
            "samples": samples,
            "study": {"*title": {"synthesize": "study title"},
                      "*summary (abstract)": {"synthesize": "abstract"},
                      "*experimental design": {"synthesize": "design"}}}


# ---- row production -------------------------------------------------------

def test_one_row_per_target_sample():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert len(filled["samples"]) == 2


def test_non_target_sampletypes_do_not_become_rows():
    """The TIS ancestor must not appear as a GEO sample row."""
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert all(r["*library name"].startswith("D.SEQ") for r in filled["samples"])


def test_row_parity_holds_for_a_large_input():
    n = 195  # the size that cost chat_nextseek a 5.1M-token prompt
    filled, _ = ex.apply_mapping(_mapping(n), SPEC, _input(n))
    assert len(filled["samples"]) == n


def test_row_parity_violation_raises():
    m = _mapping()
    m["row_scope"]["expected_rows"] = 99
    with pytest.raises(ex.RowParityError):
        ex.apply_mapping(m, SPEC, _input())


# ---- directives -----------------------------------------------------------

def test_source_copies_the_column():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*library name"] == "D.SEQ-1"


def test_const_is_identical_on_every_row():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert {r["*organism"] for r in filled["samples"]} == {"Homo sapiens"}


def test_map_normalizes_the_value():
    """paired -> paired-end. GEO dropdowns are word- and case-exact."""
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*single or paired-end"] == "paired-end"


def test_map_passes_through_a_value_it_has_no_entry_for():
    m = _mapping(**{"*single or paired-end":
                    {"source": "LibraryLayout", "map": {"single": "single"}}})
    filled, _ = ex.apply_mapping(m, SPEC, _input())
    assert filled["samples"][0]["*single or paired-end"] == "paired"


def test_via_lineage_pulls_from_an_ancestor():
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["**tissue"] == "liver"


def test_unmapped_produces_an_empty_string_not_a_placeholder():
    """Deliberately empty with a stated reason is not a gap."""
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    assert filled["samples"][0]["*raw file"] == ""
    assert not any(g.field == "*raw file" for g in gaps)


def test_synthesize_uses_the_supplied_text():
    filled, _ = ex.apply_mapping(
        _mapping(), SPEC, _input(),
        synthesized={"study": {"*title": "Endothelial response to flow"}})
    assert filled["study"]["*title"] == "Endothelial response to flow"


def test_synthesize_without_supplied_text_becomes_a_placeholder():
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    assert "*** PLACEHOLDER:" in filled["study"]["*title"]
    assert any(g.field == "*title" and g.section == "study" for g in gaps)


# ---- degradation ----------------------------------------------------------

def test_a_missing_source_value_becomes_a_placeholder_not_a_blank():
    """SKILL.md hard rule 8: greppable marker, never a blank."""
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    assert "*** PLACEHOLDER:" in filled["samples"][0]["*single or paired-end"]
    assert any(g.field == "*single or paired-end" for g in gaps)


def test_an_unresolvable_lineage_value_becomes_a_placeholder():
    lonely = ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid="D.SEQ-1",
                                     metadata={"UID": "D.SEQ-1",
                                               "LibraryLayout": "paired"},
                                     parent=None)],
        source={"adapter": "tabular"})
    filled, gaps = ex.apply_mapping(_mapping(1), SPEC, lonely)
    assert "*** PLACEHOLDER:" in filled["samples"][0]["**tissue"]
    assert any(g.field == "**tissue" for g in gaps)


def test_degradation_never_raises():
    """Never refuse outright; the curator decides what to do about gaps."""
    empty = ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid="X",
                                     metadata={}, parent=None)],
        source={"adapter": "tabular"})
    filled, gaps = ex.apply_mapping(_mapping(1), SPEC, empty)
    assert filled["samples"]
    assert gaps


def test_gap_records_what_was_searched_and_why_it_failed():
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    _, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    g = [g for g in gaps if g.field == "*single or paired-end"][0]
    assert g.uid == "D.SEQ-1"
    assert "LibraryLayout" in g.searched
    assert g.reason


def test_nothing_is_ever_fabricated():
    """A gap is a placeholder, never a plausible invented value."""
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, _ = ex.apply_mapping(_mapping(), SPEC, bad)
    assert filled["samples"][0]["*single or paired-end"] != "paired-end"


# ---- artifacts ------------------------------------------------------------

def test_filled_json_round_trips(tmp_path, plugin_sentinel):
    filled, _ = ex.apply_mapping(_mapping(), SPEC, _input())
    p = ex.write_filled(tmp_path, "GEO", filled)
    assert p == tmp_path / "report" / "GEO_filled.json"
    assert json.loads(p.read_text())["samples"]


def test_completeness_report_names_every_gap(tmp_path):
    bad = _input()
    bad.samples[0].metadata.pop("LibraryLayout")
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, bad)
    md = ex.render_completeness("GEO", gaps, _mapping(), bad)
    assert "*single or paired-end" in md
    assert "D.SEQ-1" in md
    assert "LibraryLayout" in md


def test_completeness_report_lists_deliberate_omissions_separately(tmp_path):
    filled, gaps = ex.apply_mapping(_mapping(), SPEC, _input())
    md = ex.render_completeness("GEO", gaps, _mapping(), _input())
    assert "Deliberately unmapped" in md
    assert "added at deposit time" in md


def test_completeness_report_written_to_cwd(tmp_path, plugin_sentinel):
    p = ex.write_completeness(tmp_path, "GEO", "# x")
    assert p == tmp_path / "report" / "GEO.completeness.md"


def test_clean_run_says_so():
    filled, gaps = ex.apply_mapping(
        _mapping(), SPEC, _input(),
        synthesized={"study": {"*title": "t", "*summary (abstract)": "s",
                               "*experimental design": "d"}})
    assert gaps == []
    assert "no gaps" in ex.render_completeness("GEO", gaps, _mapping(), _input()).lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_execute.py -v`
Expected: `ImportError: cannot import name 'execute' from 'report'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/report/execute.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Apply a validated mapping across every row. Fully deterministic.

No LLM runs here. The mapping already encoded every decision; this walks rows
and fills cells.

Two behaviours matter more than the mechanics:

  1. UNFILLABLE FIELDS DEGRADE, THEY DO NOT ABORT. A value that cannot be found
     becomes `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 -
     greppable, unlike a blank) and is recorded in the completeness report with
     the field, what was searched, and why it failed. Never silently fabricate;
     never refuse outright. The curator decides.

  2. ROW PARITY IS ASSERTED. chat_nextseek gates its code path on 20+ target
     samples and discards the result when the emitted row count does not match
     the expected count; their own assessment calls that guard "the single most
     valuable idea to carry over". Here the executor controls row count by
     construction, so parity is structural rather than checked after the fact -
     but it is asserted anyway, because a structural guarantee that is never
     checked is a comment.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import placeholder  # noqa: E402
from report.adapters import index_by_uid, resolve_via_lineage  # noqa: E402
from report.mapping import TARGET_SAMPLETYPE  # noqa: E402

OUTPUT_SUBDIR = "report"


class RowParityError(Exception):
    """Emitted row count does not match the mapping's declared expectation."""


@dataclass
class Gap:
    """One field that could not be filled, and why."""

    section: str
    field: str
    reason: str
    searched: str
    uid: str = ""


def _fill_row(target: str, directive: dict, sample, by_uid,
              section: str, gaps: list[Gap]) -> str:
    if "unmapped" in directive:
        return ""  # deliberately empty, reason already stated in the mapping

    if "const" in directive:
        return directive["const"]

    if "source" in directive:
        column = directive["source"]
        if directive.get("via_lineage"):
            value = resolve_via_lineage(sample, by_uid, column)
            searched = f"{column} on {sample.uid} and its Parent chain"
            why = "not present on the sample or any resolvable ancestor"
        else:
            raw = sample.metadata.get(column)
            value = None if raw in (None, "") else str(raw)
            searched = f"{column} on {sample.uid}"
            why = "column present in the input but empty on this row"
        if value is None:
            gaps.append(Gap(section, target, why, searched, sample.uid))
            return placeholder(f"{target} not derivable from {column}")
        mapped = (directive.get("map") or {}).get(value)
        return mapped if mapped is not None else value

    gaps.append(Gap(section, target, "no usable directive",
                    "the mapping itself", sample.uid))
    return placeholder(f"{target} has no usable directive")


def apply_mapping(mapping: dict, spec, normalized, *,
                  synthesized: dict | None = None) -> tuple[dict, list[Gap]]:
    """Apply the mapping. Returns (filled document, gaps).

    Args:
      mapping:     a mapping spec that has already passed validate_mapping().
      spec:        the TemplateSpec it was validated against.
      normalized:  the adapter output.
      synthesized: {section: {field: text}} from the LLM's step-6 pass. Fields
                   with a `synthesize` directive and no supplied text become
                   placeholders rather than blanks.
    """
    synthesized = synthesized or {}
    gaps: list[Gap] = []
    by_uid = index_by_uid(normalized)

    row_scope = mapping.get("row_scope") or {}
    target_type = row_scope.get("target_sampletype") or TARGET_SAMPLETYPE.get(
        spec.report_type)
    rows_in = [s for s in normalized.samples
               if not target_type or s.sample_type == target_type]

    filled: dict = {}
    row_section = spec.row_section

    for section, fields in mapping.items():
        if section in ("report_type", "source", "row_scope") or not isinstance(fields, dict):
            continue

        if section == row_section:
            out_rows = []
            for sample in rows_in:
                out_rows.append({
                    target: _fill_row(target, directive, sample, by_uid,
                                      section, gaps)
                    for target, directive in fields.items()
                })
            filled[section] = out_rows
            continue

        block: dict = {}
        for target, directive in fields.items():
            if "synthesize" in directive:
                text = (synthesized.get(section) or {}).get(target)
                if text:
                    block[target] = text
                else:
                    gaps.append(Gap(
                        section, target,
                        "requires prose the input does not carry; the "
                        "synthesize step produced nothing",
                        directive["synthesize"]))
                    block[target] = placeholder(
                        f"{target}: {directive['synthesize']}")
            elif "const" in directive:
                block[target] = directive["const"]
            elif "unmapped" in directive:
                block[target] = ""
            elif "source" in directive:
                first = rows_in[0] if rows_in else None
                block[target] = (
                    _fill_row(target, directive, first, by_uid, section, gaps)
                    if first is not None else placeholder(f"{target}: no rows"))
            else:
                block[target] = placeholder(f"{target} has no usable directive")
        filled[section] = block

    expected = row_scope.get("expected_rows")
    produced = len(filled.get(row_section, []))
    if expected is not None and produced != expected:
        raise RowParityError(
            f"mapping declared {expected} rows in {row_section!r} but the "
            f"executor produced {produced}. Refusing to emit a partial artifact."
        )
    return filled, gaps


def write_filled(root: Path, report_type: str, filled: dict) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{report_type}_filled.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(filled, indent=2) + "\n")
    return p


def render_completeness(report_type: str, gaps: list[Gap], mapping: dict,
                        normalized) -> str:
    """Name every unfilled field, the input searched, and why it failed."""
    lines = [f"# {report_type} completeness report", ""]
    lines.append(f"Input: `{(mapping.get('source') or {}).get('path') or (mapping.get('source') or {}).get('adapter', 'unknown')}`")
    lines.append(f"Samples in input: {len(normalized.samples)}")
    lines.append("")

    if not gaps:
        lines.append("**No gaps.** Every mapped field was filled from the input.")
        lines.append("")
    else:
        lines.append(f"## Unfilled fields ({len(gaps)})")
        lines.append("")
        lines.append("Each is written as `*** PLACEHOLDER: ... ***` in the "
                     "artifact, which is greppable. A blank is not.")
        lines.append("")
        lines.append("| section | field | uid | searched | why it failed |")
        lines.append("|---|---|---|---|---|")
        by_field: dict[tuple[str, str], list[Gap]] = {}
        for g in gaps:
            by_field.setdefault((g.section, g.field), []).append(g)
        for (section, field_name), group in sorted(by_field.items()):
            first = group[0]
            uids = (first.uid if len(group) == 1
                    else f"{first.uid} and {len(group) - 1} more")
            lines.append(f"| {section} | `{field_name}` | {uids} | "
                         f"{first.searched} | {first.reason} |")
        lines.append("")

    deliberate = []
    for section, fields in mapping.items():
        if not isinstance(fields, dict):
            continue
        for target, directive in fields.items():
            if isinstance(directive, dict) and directive.get("unmapped"):
                deliberate.append((section, target, directive["unmapped"]))
    if deliberate:
        lines.append("## Deliberately unmapped")
        lines.append("")
        lines.append("Left empty on purpose, with a stated reason. Not a gap.")
        lines.append("")
        for section, target, reason in sorted(deliberate):
            lines.append(f"- `{section}.{target}` - {reason}")
        lines.append("")

    lines.append("## What to do")
    lines.append("")
    lines.append("Fill by hand, enrich from another source, or proceed. The "
                 "tool never fabricates a value and never refuses outright; "
                 "this decision is yours.")
    lines.append("")
    return "\n".join(lines)


def write_completeness(root: Path, report_type: str, markdown: str) -> Path:
    p = Path(root) / OUTPUT_SUBDIR / f"{report_type}.completeness.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown)
    return p
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_execute.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/report/execute.py tests/test_report_execute.py
git commit -m "feat(report): deterministic executor with parity and degradation

No LLM runs here; the mapping already encoded every decision. Directives
source/via_lineage/const/map/synthesize/unmapped are applied across every row.

Unfillable fields degrade rather than aborting: they become the greppable
*** PLACEHOLDER: ... *** marker (hard rule 8) and land in a completeness report
naming the field, the uid, what was searched and why it failed. Never silently
fabricate, never refuse outright.

Row parity is asserted even though the executor controls row count by
construction, because a structural guarantee that is never checked is a comment.
chat_nextseek's own assessment calls that guard the single most valuable idea to
carry over.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 29: Renderers for all three formats, behind one dispatcher

**Files:**
- Create: `scripts/report/render.py`
- Modify: `scripts/deposit/geo_build_xlsx.py` (match its input contract to the filled-JSON shape)
- Test: `tests/test_report_render.py`

**Interfaces:**
- Consumes: `execute.apply_mapping` output shape from Task 28; the vendored templates from Task 24
- Produces:
  - `RENDERERS: dict[str, callable]` keyed `GEO`, `SRA`, `PRIDE`
  - `render(report_type, filled, *, template_dir, out_dir) -> list[Path]`
  - `render_geo(filled, template_xlsx, out_path) -> Path`
  - `render_sra(filled, metadata_xlsx, biosample_xlsx, out_dir) -> list[Path]`
  - `render_pride(filled, spec_path, out_path) -> Path`
  - `UnsupportedFormatError`

**Context (report spec):** two GEO renderer implementations exist and they differ. **Keep ours** — `scripts/deposit/geo_build_xlsx.py` is already a PEP 723 `uv` script, cwd-relative and arg-driven — and match its input contract to the chosen JSON shape. Do not maintain both. Also: **do not port `reports/outputs.py`**, a 400-line function with a hardcoded `if/elif` format dispatch; write a real dispatcher.

`geo_build_xlsx.py:52` reads `data["samples"]` and `data.get("paired_end_experiments", [])`, which is exactly the shape `execute.apply_mapping` produces for GEO. That contract already matches — verify it rather than assuming.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_render.py`:

```python
"""Renderers for GEO, SRA and PRIDE, behind one dispatcher."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "context" / "report_templates"
sys.path.insert(0, str(REPO / "scripts"))

from report import render as rd  # noqa: E402
from report import validate_artifact as va  # noqa: E402

GEO_FILLED = {
    "study": {"*title": "A study", "*summary (abstract)": "An abstract",
              "*experimental design": "A design"},
    "samples": [
        {"*library name": "D.SEQ-1", "*title": "t1", "*library strategy": "RNA-Seq",
         "*organism": "Homo sapiens", "**tissue": "liver", "*molecule": "polyA RNA",
         "*single or paired-end": "paired-end",
         "*instrument model": "Illumina NextSeq 500", "*raw file": "a_R1.fastq.gz"},
        {"*library name": "D.SEQ-2", "*title": "t2", "*library strategy": "RNA-Seq",
         "*organism": "Homo sapiens", "**tissue": "liver", "*molecule": "polyA RNA",
         "*single or paired-end": "paired-end",
         "*instrument model": "Illumina NextSeq 500", "*raw file": "b_R1.fastq.gz"},
    ],
    "paired_end_experiments": [
        {"file name 1": "a_R1.fastq.gz", "file name 2": "a_R2.fastq.gz"},
    ],
}

SRA_FILLED = {
    "libraries": [
        {"sample_name": "S1", "library_ID": "L1", "title": "t",
         "library_strategy": "RNA-Seq", "library_source": "TRANSCRIPTOMIC",
         "library_selection": "cDNA", "library_layout": "paired",
         "platform": "ILLUMINA", "instrument_model": "Illumina NextSeq 500",
         "design_description": "d", "filetype": "fastq", "filename": "a.fastq.gz"},
    ],
    "biosamples": [
        {"*sample_name": "S1", "*organism": "Homo sapiens", "*isolate": "n/a",
         "*age": "n/a", "*biomaterial_provider": "MIT", "*collection_date": "2026",
         "*geo_loc_name": "USA", "*sex": "female", "*tissue": "liver"},
    ],
}

PRIDE_FILLED = {
    "project_metadata": {"*submitter_name": "Jane Doe",
                         "*submitter_email": "jane@mit.edu",
                         "*project_title": "A proteomics project"},
    "file_mapping": [
        {"*file_id": "1", "*file_type": "raw", "*file_path": "/data/a.raw"},
    ],
    "sample_metadata": [
        {"*file_id": "1", "*species": "Homo sapiens", "*tissue": "liver",
         "*instrument": "Orbitrap", "*experimental_factor": "treatment"},
    ],
}


def test_dispatcher_knows_the_three_formats():
    assert set(rd.RENDERERS) == {"GEO", "SRA", "PRIDE"}


def test_dispatcher_rejects_an_unknown_format(tmp_path):
    with pytest.raises(rd.UnsupportedFormatError):
        rd.render("NFCORE", {}, template_dir=ASSETS, out_dir=tmp_path)


def test_dispatcher_is_not_a_hardcoded_if_elif():
    """Report spec non-goal: do not port outputs.py's 400-line if/elif."""
    src = (REPO / "scripts" / "report" / "render.py").read_text()
    assert src.count('report_type ==') <= 1


# ---- GEO ------------------------------------------------------------------

def test_geo_renders_and_validates(tmp_path):
    outs = rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    assert len(outs) == 1
    assert outs[0].name == "GEO_filled.xlsx"
    assert outs[0].is_file()


def test_geo_row_parity_survives_rendering(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    wb = openpyxl.load_workbook(out)
    ws = wb["Metadata"]
    names = [r[0] for r in ws.iter_rows(values_only=True)]
    assert "D.SEQ-1" in names
    assert "D.SEQ-2" in names


def test_geo_input_contract_matches_the_executor_output():
    """geo_build_xlsx.py reads data['samples'] and
    data.get('paired_end_experiments'), which is exactly what apply_mapping
    emits for GEO. Verify rather than assume."""
    src = (REPO / "scripts" / "deposit" / "geo_build_xlsx.py").read_text()
    assert 'data["samples"]' in src
    assert '"paired_end_experiments"' in src


def test_only_one_geo_renderer_is_maintained():
    """Report spec: pick one and delete the other. Ours is kept."""
    candidates = list((REPO / "scripts").rglob("*geo*xlsx*.py"))
    assert len(candidates) == 1, f"more than one GEO renderer: {candidates}"


# ---- SRA ------------------------------------------------------------------

def test_sra_renders_two_workbooks(tmp_path):
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    names = sorted(p.name for p in outs)
    assert names == ["SRA_biosample_filled.xlsx", "SRA_metadata_filled.xlsx"]
    assert all(p.is_file() for p in outs)


def test_sra_metadata_workbook_carries_the_library_rows(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    meta = [p for p in outs if "metadata" in p.name][0]
    wb = openpyxl.load_workbook(meta)
    flat = [str(c) for row in wb[wb.sheetnames[0]].iter_rows(values_only=True)
            for c in row if c is not None]
    assert "L1" in flat


def test_sra_validates_after_rendering(tmp_path):
    outs = rd.render("SRA", SRA_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    meta = [p for p in outs if "metadata" in p.name][0]
    r = va.validate_sra_xlsx(file_path=meta, sra_spec_path=ASSETS / "SRA.json",
                             section="libraries")
    assert r.status is not va.ArtifactStatus.Unreadable
    assert r.status is not va.ArtifactStatus.Missing


# ---- PRIDE ----------------------------------------------------------------

def test_pride_renders_a_tab_delimited_file_not_a_spreadsheet(tmp_path):
    outs = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    assert len(outs) == 1
    assert outs[0].name == "submission.px"
    assert outs[0].suffix != ".xlsx"


def test_pride_uses_the_declared_line_prefixes(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    lines = out.read_text().splitlines()
    prefixes = {l.split("\t", 1)[0] for l in lines if l.strip()}
    assert {"MTD", "FMH", "FME", "SMH", "SME"} <= prefixes


def test_pride_metadata_lines_are_one_key_per_line(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    mtd = [l for l in out.read_text().splitlines() if l.startswith("MTD")]
    assert any("submitter_name" in l and "Jane Doe" in l for l in mtd)
    assert all(len(l.split("\t")) == 3 for l in mtd)


def test_pride_header_lines_precede_their_entries(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    lines = [l.split("\t", 1)[0] for l in out.read_text().splitlines() if l.strip()]
    assert lines.index("FMH") < lines.index("FME")
    assert lines.index("SMH") < lines.index("SME")


def test_pride_validates_after_rendering(tmp_path):
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    r = va.validate_pride_px(file_path=out, pride_spec_path=ASSETS / "pride.json")
    assert r.status is va.ArtifactStatus.Valid


def test_pride_strips_the_star_prefix_from_field_names(tmp_path):
    """`*species` is the spec's required marker, not the wire field name."""
    out = rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)[0]
    text = out.read_text()
    assert "species" in text
    assert "*species" not in text


def test_render_writes_nothing_in_the_plugin(tmp_path, plugin_sentinel):
    rd.render("PRIDE", PRIDE_FILLED, template_dir=ASSETS, out_dir=tmp_path)
    rd.render("GEO", GEO_FILLED, template_dir=ASSETS, out_dir=tmp_path)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_render.py -v`
Expected: `ImportError: cannot import name 'render' from 'report'`.

- [ ] **Step 3: Write `scripts/report/render.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Render a filled report document to its submission artifact.

A real dispatcher, deliberately: chat_nextseek's reports/outputs.py is a
400-line function with a hardcoded if/elif format dispatch, and porting that
shape is an explicit non-goal.

Each format's artifact is what its own spec says it is:

  GEO   -> one xlsx, via scripts/deposit/geo_build_xlsx.py (ours, kept)
  SRA   -> TWO xlsx: SRA_metadata (libraries) and SRA_biosample (biosamples)
  PRIDE -> submission.px, TAB-DELIMITED with MTD/FMH/FME/SMH/SME line prefixes.
           NOT a spreadsheet. chat_nextseek's e2e catalog asserts pride.xlsx,
           which is the wrong artifact type, and it has no exporter at all.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook

_PLUGIN = Path(__file__).resolve().parent.parent.parent


class UnsupportedFormatError(Exception):
    """No renderer for this format. A format is not supported without one."""


def _strip_marker(name: str) -> str:
    """`*species` / `**tissue` -> `species` / `tissue`.

    The stars are the template's required/conditional markers, not wire names.
    """
    return name.lstrip("*")


# ── GEO ────────────────────────────────────────────────────────────────────

def render_geo(filled: dict, template_xlsx: Path, out_path: Path) -> Path:
    """Delegate to scripts/deposit/geo_build_xlsx.py - ours, kept.

    Two implementations existed and differed; the spec's instruction is to pick
    one and delete the other. Ours wins because it is already a PEP 723 uv
    script, cwd-relative and arg-driven. Its input contract - `data["samples"]`
    plus `data.get("paired_end_experiments", [])` - is already exactly what
    execute.apply_mapping emits for GEO.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = out_path.with_suffix(".render-input.json")
    tmp_json.write_text(json.dumps(filled, indent=2))
    script = _PLUGIN / "scripts" / "deposit" / "geo_build_xlsx.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(script),
         str(tmp_json), str(template_xlsx), str(out_path)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"geo_build_xlsx failed:\n{result.stderr}")
    tmp_json.unlink(missing_ok=True)
    return out_path


# ── SRA ────────────────────────────────────────────────────────────────────

def _fill_sheet_from_rows(template: Path, rows: list[dict], out_path: Path) -> Path:
    """Write `rows` under the template's own header row, matched by name.

    Header matching is case-insensitive and marker-insensitive, so a template
    header `sample_name` accepts a filled key `*sample_name`.
    """
    wb = load_workbook(template)
    try:
        ws = wb[wb.sheetnames[0]]
        header_row_idx, headers = None, []
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if len(cells) >= 3:
                header_row_idx = i
                headers = ["" if c is None else str(c).strip() for c in row]
                break
        if header_row_idx is None:
            raise ValueError(f"no header row found in {template}")

        lookup = {_strip_marker(h).lower(): i
                  for i, h in enumerate(headers, start=1) if h}
        for offset, record in enumerate(rows, start=1):
            for key, value in record.items():
                col = lookup.get(_strip_marker(str(key)).lower())
                if col:
                    ws.cell(row=header_row_idx + offset, column=col).value = value
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
    finally:
        wb.close()
    return out_path


def render_sra(filled: dict, metadata_xlsx: Path, biosample_xlsx: Path,
               out_dir: Path) -> list[Path]:
    """SRA ships TWO templates and therefore produces two workbooks."""
    out_dir = Path(out_dir)
    written = []
    if filled.get("libraries"):
        written.append(_fill_sheet_from_rows(
            metadata_xlsx, filled["libraries"],
            out_dir / "SRA_metadata_filled.xlsx"))
    if filled.get("biosamples"):
        written.append(_fill_sheet_from_rows(
            biosample_xlsx, filled["biosamples"],
            out_dir / "SRA_biosample_filled.xlsx"))
    return written


# ── PRIDE ──────────────────────────────────────────────────────────────────

def render_pride(filled: dict, spec_path: Path, out_path: Path) -> Path:
    """ProteomeXchange Submission Summary File, v2.2.1. Tab-delimited.

    Written from scratch: chat_nextseek has a pride.json template and a row-key
    entry but NO exporter, so it silently yields JSON only while its own e2e
    catalog asserts pride.xlsx. That assertion names the wrong artifact type.
    """
    spec = json.loads(Path(spec_path).read_text())
    prefixes = spec["format"]["line_prefixes"]
    lines: list[str] = []

    lines.append("\t".join([prefixes["comment"],
                            "Generated by dmac-curation report mode"]))
    for key, value in (filled.get("project_metadata") or {}).items():
        lines.append("\t".join([prefixes["metadata"], _strip_marker(str(key)),
                                "" if value is None else str(value)]))

    file_rows = filled.get("file_mapping") or []
    if file_rows:
        headers = [_strip_marker(k) for k in file_rows[0]]
        lines.append("\t".join([prefixes["file_mapping_header"], *headers]))
        for record in file_rows:
            lines.append("\t".join(
                [prefixes["file_mapping_entry"],
                 *["" if v is None else str(v) for v in record.values()]]))

    sample_rows = filled.get("sample_metadata") or []
    if sample_rows:
        headers = [_strip_marker(k) for k in sample_rows[0]]
        lines.append("\t".join([prefixes["sample_metadata_header"], *headers]))
        for record in sample_rows:
            lines.append("\t".join(
                [prefixes["sample_metadata_entry"],
                 *["" if v is None else str(v) for v in record.values()]]))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# ── dispatch ───────────────────────────────────────────────────────────────

def _geo(filled, template_dir: Path, out_dir: Path) -> list[Path]:
    return [render_geo(filled, template_dir / "GEO_template.xlsx",
                       out_dir / "GEO_filled.xlsx")]


def _sra(filled, template_dir: Path, out_dir: Path) -> list[Path]:
    return render_sra(filled, template_dir / "SRA_metadata.xlsx",
                      template_dir / "SRA_biosample.xlsx", out_dir)


def _pride(filled, template_dir: Path, out_dir: Path) -> list[Path]:
    return [render_pride(filled, template_dir / "pride.json",
                         out_dir / "submission.px")]


RENDERERS = {"GEO": _geo, "SRA": _sra, "PRIDE": _pride}


def render(report_type: str, filled: dict, *, template_dir: Path,
           out_dir: Path) -> list[Path]:
    """Render to every artifact the format requires. Returns the paths written."""
    key = str(report_type).upper()
    renderer = RENDERERS.get(key)
    if renderer is None:
        raise UnsupportedFormatError(
            f"no renderer for {report_type!r}; have {sorted(RENDERERS)}. "
            f"A format is not supported until it has a renderer AND a validator."
        )
    return renderer(filled, Path(template_dir), Path(out_dir))
```

- [ ] **Step 4: Verify the GEO contract before relying on the delegation**

Run:

```bash
grep -n 'data\["samples"\]\|paired_end_experiments\|base_cols' scripts/deposit/geo_build_xlsx.py | head
```

Expected: line 52 `samples = data["samples"]` and line 53
`paired = data.get("paired_end_experiments", [])`. `base_cols` at lines 80-85
already lists the GEO sample columns in template order.

**If `geo_build_xlsx.py` expects a different top-level shape, change it here rather than reshaping the executor output** — the executor's shape is what the mapping validator checks against.

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_render.py -v`
Expected: all pass.

**If `test_geo_renders_and_validates` fails inside `geo_build_xlsx.py`**, read its
error: it raises `ValueError` when the template lacks a `*library name`,
`PROTOCOLS` or `file name 1` anchor row. Confirm the vendored `GEO_template.xlsx`
has all three:

```bash
uv run python3 - <<'PY'
from openpyxl import load_workbook
ws = load_workbook("context/report_templates/GEO_template.xlsx")["Metadata"]
wanted = {"*library name", "PROTOCOLS", "file name 1"}
for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
    if row and row[0] in wanted:
        print(f"row {i}: {row[0]!r}")
PY
```

- [ ] **Step 6: Commit**

```bash
git add scripts/report/render.py scripts/deposit/geo_build_xlsx.py \
        tests/test_report_render.py
git commit -m "feat(report): renderers for GEO, SRA and PRIDE behind a dispatcher

A real dispatcher, deliberately: porting outputs.py's 400-line if/elif format
dispatch is an explicit non-goal.

GEO delegates to our geo_build_xlsx.py, which is already a PEP 723 uv script,
cwd-relative and arg-driven, and whose input contract (data['samples'] plus
paired_end_experiments) already matches the executor output exactly. Two
implementations existed; only ours is maintained.

SRA renders TWO workbooks, because SRA.json has two row-bearing sections and
both templates ship.

PRIDE is written from scratch as a TAB-DELIMITED ProteomeXchange submission
summary file with MTD/FMH/FME/SMH/SME line prefixes, because that is what
pride.json declares. chat_nextseek has a template and a row-key but no exporter,
and its e2e catalog asserts pride.xlsx -- the wrong artifact type. Every format
here has a renderer AND a validator.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 30: Protocol resolution and optional NExtSEEK enrichment

**Files:**
- Create: `scripts/report/protocols.py`
- Create: `scripts/report/enrich.py`
- Test: `tests/test_report_protocols.py`

**Interfaces:**
- Consumes: `adapters.NormalizedInput`, `adapters.NormalizedSample` from Task 26
- Produces:
  - `protocols.find_protocol_refs(normalized) -> dict[str, list[str]]` — `{uid: [ref, ...]}`
  - `protocols.parse_sop_id(ref) -> str | None`
  - `protocols.resolve_host(url, *, nextseek_base_url) -> str`
  - `protocols.extract_docx_text(data: bytes) -> str`
  - `protocols.extract_pdf_text(data: bytes) -> str` — raises `PdfSupportError` when PyPDF2 is absent
  - `protocols.truncate_tokens(text, limit=3000) -> tuple[str, bool]`
  - `protocols.resolve_protocols(normalized, *, fetch_sop=None, fetch_blob=None, nextseek_base_url) -> tuple[dict, list[str]]`
  - `enrich.merge_leaf_wins(normalized, extra) -> NormalizedInput`
  - `PdfSupportError`

**Context — the gotchas, all of which are traps (report spec):**
- Refs to `fairdata.mit.edu` are **not** fetched from that host; they are redirected to whatever `NEXTSEEK_BASE_URL` is. Only `fairdomhub.org` goes off-host, and it needs `FDH_API` as a bearer token with **no fallback**.
- Protocol refs are discovered from any metadata key literally named `Protocol`, matching a `/sops/{id}` URL or a bare `P.*` name.
- DOCX extraction is stdlib-only (unzip, read `word/document.xml`, strip tags). **PDF needs `PyPDF2` and silently yields nothing if absent — fail loudly instead.**
- Protocol text is truncated at ~3000 tokens upstream. **Record truncation in the completeness report** rather than letting it pass unnoticed.
- Enrichment merge is **leaf-wins**: existing values are never overwritten.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_protocols.py`:

```python
"""Protocol resolution and additive NExtSEEK enrichment."""
import io
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import enrich as en  # noqa: E402
from report import protocols as pr  # noqa: E402

BASE = "https://nextseek.mit.edu"


def _docx(paragraphs):
    buf = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document><w:body>{body}'
                   f"</w:body></w:document>")
    return buf.getvalue()


def _input(*metas):
    return ad.NormalizedInput(
        samples=[ad.NormalizedSample(sample_type="D.SEQ", uid=f"D.SEQ-{i}",
                                     metadata=m, parent=None)
                 for i, m in enumerate(metas, start=1)],
        source={"adapter": "tabular"})


# ---- discovery ------------------------------------------------------------

def test_finds_refs_in_a_key_literally_named_Protocol():
    got = pr.find_protocol_refs(_input({"Protocol": "P.RNAseq-1"}))
    assert got["D.SEQ-1"] == ["P.RNAseq-1"]


def test_ignores_keys_that_merely_contain_protocol():
    assert pr.find_protocol_refs(_input({"ProtocolNotes": "x"})) == {}


def test_finds_a_sops_url():
    got = pr.find_protocol_refs(
        _input({"Protocol": "https://fairdata.mit.edu/nextseek_api/sops/42/"}))
    assert got["D.SEQ-1"]


def test_splits_semicolon_joined_refs():
    got = pr.find_protocol_refs(_input({"Protocol": "P.A-1; P.B-2"}))
    assert got["D.SEQ-1"] == ["P.A-1", "P.B-2"]


def test_skips_placeholder_markers():
    assert pr.find_protocol_refs(
        _input({"Protocol": "*** PLACEHOLDER: unknown ***"})) == {}


def test_parse_sop_id_from_a_url():
    assert pr.parse_sop_id("https://x/nextseek_api/sops/42/") == "42"
    assert pr.parse_sop_id("/sops/7") == "7"


def test_parse_sop_id_from_a_bare_p_name():
    assert pr.parse_sop_id("P.RNAseq-1") == "P.RNAseq-1"


def test_parse_sop_id_rejects_free_prose():
    assert pr.parse_sop_id("see the methods section") is None


# ---- host redirection -----------------------------------------------------

def test_fairdata_urls_are_redirected_to_the_nextseek_base():
    """The trap: fairdata.mit.edu refs are NOT fetched from that host."""
    out = pr.resolve_host("https://fairdata.mit.edu/nextseek_api/sops/42/",
                          nextseek_base_url=BASE)
    assert out == "https://nextseek.mit.edu/nextseek_api/sops/42/"


def test_fairdomhub_urls_stay_off_host():
    url = "https://fairdomhub.org/sops/9"
    assert pr.resolve_host(url, nextseek_base_url=BASE) == url


def test_a_relative_ref_is_joined_onto_the_nextseek_base():
    assert pr.resolve_host("/nextseek_api/sops/42/", nextseek_base_url=BASE) == \
        "https://nextseek.mit.edu/nextseek_api/sops/42/"


def test_fairdomhub_requires_a_bearer_token_with_no_fallback():
    src = (REPO / "scripts" / "report" / "protocols.py").read_text()
    assert "FDH_API" in src
    assert "no fallback" in src.lower()


# ---- text extraction ------------------------------------------------------

def test_docx_extraction_is_stdlib_only():
    text = pr.extract_docx_text(_docx(["Step one.", "Step two."]))
    assert "Step one." in text
    assert "Step two." in text


def test_docx_extraction_strips_tags():
    assert "<w:t>" not in pr.extract_docx_text(_docx(["Hello"]))


def test_docx_extraction_on_a_non_zip_returns_empty():
    assert pr.extract_docx_text(b"not a zip") == ""


def test_pdf_extraction_fails_loudly_without_PyPDF2(monkeypatch):
    """The trap: upstream silently yields nothing when PyPDF2 is absent."""
    monkeypatch.setitem(sys.modules, "PyPDF2", None)
    with pytest.raises(pr.PdfSupportError):
        pr.extract_pdf_text(b"%PDF-1.4 whatever")


def test_truncation_reports_whether_it_truncated():
    short, was_cut = pr.truncate_tokens("a b c", limit=10)
    assert short == "a b c" and was_cut is False
    long, was_cut = pr.truncate_tokens(" ".join(["w"] * 5000), limit=10)
    assert was_cut is True
    assert len(long.split()) <= 11


def test_truncation_default_limit_matches_upstream():
    import inspect
    assert inspect.signature(pr.truncate_tokens).parameters["limit"].default == 3000


# ---- resolution -----------------------------------------------------------

def test_resolve_protocols_fetches_and_extracts():
    calls = []

    def fetch_sop(sop_id):
        calls.append(sop_id)
        return {"id": sop_id, "title": "RNA-seq SOP",
                "content_blobs": [{"url": f"{BASE}/blob/1", "content_type":
                                   "application/vnd.openxmlformats-officedocument"
                                   ".wordprocessingml.document"}]}

    def fetch_blob(url):
        return _docx(["Extract RNA with TRIzol."])

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.RNAseq-1"}),
        fetch_sop=fetch_sop, fetch_blob=fetch_blob, nextseek_base_url=BASE)
    assert calls == ["P.RNAseq-1"]
    assert "TRIzol" in resolved["P.RNAseq-1"]["text"]
    assert resolved["P.RNAseq-1"]["title"] == "RNA-seq SOP"


def test_resolve_protocols_with_no_fetcher_is_a_no_op():
    """Neither enrichment nor protocol resolution gates output."""
    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}), nextseek_base_url=BASE)
    assert resolved == {}
    assert any("not resolved" in n for n in notes)


def test_resolve_protocols_records_truncation_in_its_notes():
    def fetch_sop(sop_id):
        return {"id": sop_id, "title": "t",
                "content_blobs": [{"url": "u", "content_type": "application/"
                                   "vnd.openxmlformats-officedocument."
                                   "wordprocessingml.document"}]}

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}),
        fetch_sop=fetch_sop,
        fetch_blob=lambda u: _docx(["word"] * 6000),
        nextseek_base_url=BASE)
    assert any("truncat" in n.lower() for n in notes)


def test_resolve_protocols_survives_a_fetch_error():
    def boom(sop_id):
        raise OSError("502")

    resolved, notes = pr.resolve_protocols(
        _input({"Protocol": "P.A-1"}), fetch_sop=boom, nextseek_base_url=BASE)
    assert resolved == {}
    assert any("P.A-1" in n for n in notes)


# ---- enrichment -----------------------------------------------------------

def test_merge_is_leaf_wins():
    base = _input({"UID": "D.SEQ-1", "Tissue": "liver"})
    extra = _input({"UID": "D.SEQ-1", "Tissue": "kidney", "Organism": "Homo sapiens"})
    merged = en.merge_leaf_wins(base, extra)
    s = {x.uid: x for x in merged.samples}["D.SEQ-1"]
    assert s.metadata["Tissue"] == "liver"
    assert s.metadata["Organism"] == "Homo sapiens"


def test_merge_adds_samples_absent_from_the_base():
    base = _input({"UID": "D.SEQ-1"})
    extra = ad.NormalizedInput(samples=[
        ad.NormalizedSample(sample_type="TIS", uid="TIS-9",
                            metadata={"UID": "TIS-9"}, parent=None)],
        source={"adapter": "uids"})
    merged = en.merge_leaf_wins(base, extra)
    assert "TIS-9" in {s.uid for s in merged.samples}


def test_merge_with_nothing_to_add_is_identity():
    base = _input({"UID": "D.SEQ-1", "Tissue": "liver"})
    merged = en.merge_leaf_wins(base, ad.NormalizedInput())
    assert merged.samples[0].metadata == {"UID": "D.SEQ-1", "Tissue": "liver"}


def test_merge_records_both_sources():
    base = _input({"UID": "D.SEQ-1"})
    extra = ad.NormalizedInput(samples=[], source={"adapter": "uids"})
    merged = en.merge_leaf_wins(base, extra)
    assert "enriched_from" in merged.source
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_protocols.py -v`
Expected: `ImportError: cannot import name 'protocols' from 'report'`.

- [ ] **Step 3: Write `scripts/report/protocols.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Discover, fetch and extract protocol (SOP) text.

Four traps, all inherited from chat_nextseek's reports/protocols.py and all
handled here deliberately:

  1. Refs to `fairdata.mit.edu` are NOT fetched from that host. They are
     redirected to whatever NEXTSEEK_BASE_URL is. Only `fairdomhub.org` goes
     off-host, and it needs FDH_API as a bearer token with NO FALLBACK.
  2. Refs are discovered from a metadata key named literally `Protocol`,
     matching a `/sops/{id}` URL or a bare `P.*` name. A key merely CONTAINING
     "protocol" is not a ref.
  3. DOCX extraction is stdlib-only. PDF needs PyPDF2 and upstream SILENTLY
     YIELDS NOTHING when it is absent; here that raises PdfSupportError.
  4. Text is truncated at ~3000 tokens. Truncation is REPORTED, not silent -
     a curator reading a protocol paragraph that stops mid-sentence deserves to
     know why.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from urllib.parse import urlparse, urlunparse

_SOP_URL_RE = re.compile(r"/sops/([^/?#]+)")
_BARE_SOP_RE = re.compile(r"^P\.[A-Za-z0-9._-]+$")
_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_MARKERS = ("*** PLACEHOLDER", "***PLACEHOLDER")

DOCX_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
)
PDF_CONTENT_TYPES = ("application/pdf",)

DEFAULT_TOKEN_LIMIT = 3000


class PdfSupportError(RuntimeError):
    """PyPDF2 is not installed. Upstream returned empty text; we refuse to."""


def find_protocol_refs(normalized) -> dict[str, list[str]]:
    """{uid: [refs]} from any metadata key literally named `Protocol`."""
    out: dict[str, list[str]] = {}
    for sample in normalized.samples:
        raw = sample.metadata.get("Protocol")
        if raw in (None, ""):
            continue
        text = str(raw)
        if any(m in text for m in _PLACEHOLDER_MARKERS):
            continue
        refs = [r.strip() for r in text.split(";") if r.strip()]
        refs = [r for r in refs if parse_sop_id(r)]
        if refs:
            out[sample.uid] = refs
    return out


def parse_sop_id(ref: str) -> str | None:
    """A `/sops/{id}` URL or a bare `P.*` name. Free prose returns None."""
    ref = str(ref).strip()
    hit = _SOP_URL_RE.search(ref)
    if hit:
        return hit.group(1)
    if _BARE_SOP_RE.match(ref):
        return ref
    return None


def resolve_host(url: str, *, nextseek_base_url: str) -> str:
    """Redirect fairdata.mit.edu refs to the configured NExtSEEK host.

    Only fairdomhub.org genuinely goes off-host, and it requires FDH_API as a
    bearer token with **no fallback** - there is no anonymous read path.
    """
    url = str(url).strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        return nextseek_base_url.rstrip("/") + "/" + url.lstrip("/")
    if parsed.netloc.endswith("fairdomhub.org"):
        return url
    base = urlparse(nextseek_base_url)
    return urlunparse((base.scheme, base.netloc, parsed.path,
                       parsed.params, parsed.query, parsed.fragment))


def extract_docx_text(data: bytes) -> str:
    """Stdlib-only: unzip, read word/document.xml, strip tags."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""
    spaced = xml.replace("</w:p>", "\n").replace("</w:tr>", "\n")
    return re.sub(r"\n{3,}", "\n\n", _TAG_RE.sub("", spaced)).strip()


def extract_pdf_text(data: bytes) -> str:
    """PDF text. Raises PdfSupportError when PyPDF2 is unavailable.

    Upstream silently returned nothing here, so a missing optional dependency
    became a silently empty protocol section in a submission artifact.
    """
    try:
        import PyPDF2  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise PdfSupportError(
            "PDF protocol extraction needs PyPDF2, which is not importable. "
            "Install it (uv run --with PyPDF2 ...) or convert the SOP to DOCX. "
            "Refusing to return empty text and pretend the protocol was read."
        ) from exc
    import PyPDF2
    reader = PyPDF2.PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def truncate_tokens(text: str, limit: int = DEFAULT_TOKEN_LIMIT) -> tuple[str, bool]:
    """(text, was_truncated). Whitespace tokens; close enough for a budget."""
    tokens = text.split()
    if len(tokens) <= limit:
        return text, False
    return " ".join(tokens[:limit]) + " ...[truncated]", True


def resolve_protocols(normalized, *, fetch_sop=None, fetch_blob=None,
                      nextseek_base_url: str,
                      token_limit: int = DEFAULT_TOKEN_LIMIT):
    """Resolve every discovered ref. Returns ({ref: record}, notes).

    Never gates output: with no fetcher, or on any fetch error, this returns
    what it could and explains the rest in `notes`, which the caller folds into
    the completeness report.
    """
    notes: list[str] = []
    resolved: dict[str, dict] = {}
    refs = find_protocol_refs(normalized)
    if not refs:
        return resolved, notes

    unique = sorted({r for group in refs.values() for r in group})
    if fetch_sop is None:
        notes.append(
            f"{len(unique)} protocol reference(s) not resolved: no NExtSEEK "
            f"connection was available. Protocol prose will be a placeholder.")
        return resolved, notes

    for ref in unique:
        sop_id = parse_sop_id(ref)
        try:
            record = fetch_sop(sop_id)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"protocol {ref}: fetch failed ({type(exc).__name__}: {exc})")
            continue
        if not record:
            notes.append(f"protocol {ref}: no such SOP")
            continue

        text_parts: list[str] = []
        for blob in record.get("content_blobs") or []:
            ctype = str(blob.get("content_type") or "").lower()
            url = resolve_host(str(blob.get("url") or ""),
                               nextseek_base_url=nextseek_base_url)
            if fetch_blob is None:
                notes.append(f"protocol {ref}: blob not downloaded (no fetcher)")
                continue
            try:
                data = fetch_blob(url)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"protocol {ref}: blob {url} failed "
                             f"({type(exc).__name__})")
                continue
            if any(ctype.startswith(t) for t in DOCX_CONTENT_TYPES):
                text_parts.append(extract_docx_text(data))
            elif any(ctype.startswith(t) for t in PDF_CONTENT_TYPES):
                try:
                    text_parts.append(extract_pdf_text(data))
                except PdfSupportError as exc:
                    notes.append(f"protocol {ref}: {exc}")
            else:
                notes.append(f"protocol {ref}: unhandled content type {ctype!r}")

        joined, was_truncated = truncate_tokens("\n\n".join(
            p for p in text_parts if p), token_limit)
        if was_truncated:
            notes.append(f"protocol {ref}: text truncated at {token_limit} tokens")
        resolved[ref] = {"id": sop_id, "title": record.get("title", ""),
                         "text": joined, "truncated": was_truncated}
    return resolved, notes
```

- [ ] **Step 4: Write `scripts/report/enrich.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Additive enrichment. Never required, never overwrites.

If a UID happens to resolve in NExtSEEK, fetch and merge it. If it does not,
the run proceeds on whatever the input already carried. Enrichment is a bonus,
not a precondition - which is what lets report mode run on a curated Arm{X}.xlsx
before anything has been uploaded.

Merge rule is LEAF-WINS: a value already present on a sample is never replaced.
The curator's sheet is the truth; the database is the supplement.
"""
from __future__ import annotations

from report.adapters import NormalizedInput, NormalizedSample


def merge_leaf_wins(base: NormalizedInput, extra: NormalizedInput) -> NormalizedInput:
    """Merge `extra` into `base` without overwriting anything `base` has."""
    by_uid: dict[str, NormalizedSample] = {}
    order: list[str] = []
    for sample in base.samples:
        by_uid[sample.uid] = NormalizedSample(
            sample_type=sample.sample_type, uid=sample.uid,
            metadata=dict(sample.metadata), parent=sample.parent)
        order.append(sample.uid)

    for sample in extra.samples:
        existing = by_uid.get(sample.uid)
        if existing is None:
            by_uid[sample.uid] = NormalizedSample(
                sample_type=sample.sample_type, uid=sample.uid,
                metadata=dict(sample.metadata), parent=sample.parent)
            order.append(sample.uid)
            continue
        for key, value in sample.metadata.items():
            if existing.metadata.get(key) in (None, ""):
                existing.metadata[key] = value
        if not existing.parent and sample.parent:
            existing.parent = sample.parent
        if not existing.sample_type and sample.sample_type:
            existing.sample_type = sample.sample_type

    return NormalizedInput(
        samples=[by_uid[u] for u in order],
        source={**base.source, "enriched_from": extra.source or {}},
    )
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_protocols.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/report/protocols.py scripts/report/enrich.py \
        tests/test_report_protocols.py
git commit -m "feat(report): protocol resolution and additive enrichment

Four inherited traps, handled deliberately. fairdata.mit.edu refs are NOT
fetched from that host, they are redirected to NEXTSEEK_BASE_URL; only
fairdomhub.org goes off-host and it needs FDH_API as a bearer token with no
fallback. Refs come only from a key named literally 'Protocol', not one merely
containing the word. DOCX extraction is stdlib-only. PDF extraction raises
PdfSupportError instead of upstream's silent empty string, because a missing
optional dependency should not become a silently empty protocol section in a
submission. Truncation at 3000 tokens is reported, not silent.

Enrichment is leaf-wins and never gates output, which is what lets report mode
run on a curated Arm{X}.xlsx before anything has been uploaded.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 31: `/curate-report` and the `REPORTS.md` reference

**Files:**
- Create: `commands/curate-report.md`
- Modify: `skills/curation/REPORTS.md` (replace the Task 12 stub)
- Test: `tests/test_curate_report.py`

**Interfaces:**
- Consumes: everything from Tasks 24-30
- Produces: `/curate-report <FORMAT> <input>` writing `report/<FORMAT>.mapping.json`, `report/<FORMAT>.completeness.md`, `report/<FORMAT>_filled.json`, and the rendered artifact(s)

**Context:** **a Claude Code plugin does not need an LLM API client.** chat_nextseek's `call_llm_structured` is a 20-parameter wrapper over four provider clients with JSON-repair retries. Here steps 4 and 6 are *skill instructions* — the agent reads the template plus a metadata profile and emits the mapping directly. That removes `config.py` (83KB, eagerly loads 10+ context files and fetches a remote API schema), `llm_clients.py` (30KB), and all provider credentials from the port.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curate_report.py`:

```python
"""The /curate-report entry point and its reference doc."""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMAND = REPO / "commands" / "curate-report.md"
DOC = REPO / "skills" / "curation" / "REPORTS.md"


def test_command_exists_with_frontmatter():
    assert COMMAND.exists()
    text = COMMAND.read_text()
    assert text.startswith("---")
    assert "description:" in text.split("---")[1]


def test_command_names_the_three_supported_formats():
    text = COMMAND.read_text()
    for fmt in ("GEO", "SRA", "PRIDE"):
        assert fmt in text


def test_command_excludes_nfcore():
    text = COMMAND.read_text()
    assert "nf-core" in text.lower()
    assert "not this mode" in text.lower() or "out of scope" in text.lower()


def test_command_states_it_runs_without_a_lockfile():
    text = COMMAND.read_text()
    assert "without" in text.lower()
    assert "lockfile" in text.lower()


@pytest.mark.parametrize("rel", [
    "scripts/report/adapters.py",
    "scripts/report/mapping.py",
    "scripts/report/execute.py",
    "scripts/report/render.py",
    "scripts/report/validate_artifact.py",
    "scripts/report/protocols.py",
])
def test_command_references_real_scripts(rel):
    assert rel in COMMAND.read_text()
    assert (REPO / rel).exists()


def test_command_puts_the_llm_only_at_steps_4_and_6():
    text = COMMAND.read_text()
    assert "O(columns)" in text
    assert "not O(rows)" in text


def test_command_forbids_writing_cell_values_directly():
    text = COMMAND.read_text()
    assert "do not write cell values" in text.lower()


def test_doc_is_no_longer_a_stub():
    text = DOC.read_text()
    assert "Status: stub" not in text
    assert "mapping spec" in text.lower()


def test_doc_records_the_5m_token_lesson():
    assert "5.1M-token" in DOC.read_text()


def test_doc_records_that_pride_is_not_a_spreadsheet():
    text = DOC.read_text()
    assert "submission.px" in text
    assert "not a spreadsheet" in text.lower()


def test_doc_states_no_llm_client_is_needed():
    text = DOC.read_text()
    assert "llm_clients.py" in text or "LLM API client" in text


def test_doc_lists_every_adapter():
    text = DOC.read_text()
    for phrase in ("UID", "AllMetadata", "Arm{X}.xlsx", "csv"):
        assert phrase in text


def test_doc_records_the_protocol_gotchas():
    text = DOC.read_text()
    assert "fairdata.mit.edu" in text
    assert "PyPDF2" in text


def test_mode_table_still_matches_after_filling_the_doc():
    skill = (REPO / "skills" / "curation" / "SKILL.md").read_text()
    assert "REPORTS.md" in skill
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_curate_report.py -v`
Expected: FAILs on every command assertion and every doc assertion.

- [ ] **Step 3: Write `commands/curate-report.md`**

```markdown
---
description: Build a GEO / SRA / PRIDE submission artifact from metadata you have (report mode)
---

The user wants a repository submission artifact: *"I have file X.xlsx with
metadata, turn it into a GEO report."*

Parse `$ARGUMENTS` for a format (`GEO`, `SRA`, `PRIDE`) and an input. If either
is missing, ask - do not guess a format.

**Load `skills/curation/REPORTS.md` before starting.**

## Scope

**In:** GEO, SRA, PRIDE. Each has a renderer AND a validator; a format is not
supported without both.

**Out: nf-core samplesheets.** In chat_nextseek that path is a multi-turn
interactive wizard carrying Seqera/Tower launch concerns. Different problem, out
of scope for this mode.

## State scope

**Input-scoped.** Read a project lockfile when one is present, for lab and
project id. Run **without** one, from any cwd. All output goes to `./report/`.

## The chain

Only steps 4 and 6 need you. Everything else is a script.

```
1. adapter -> normalized shape                                    deterministic
2. (optional) NExtSEEK enrichment for resolvable UIDs             deterministic
3. protocol resolution: Protocol keys -> GET /sops/{id}/          deterministic
4. YOU emit a MAPPING SPEC                                        *** LLM ***
5. validate the mapping against the template + CV                 deterministic
6. YOU write only the `synthesize:` fields                        *** LLM ***
7. apply the mapping across all rows -> <FORMAT>_filled.json      deterministic
8. render                                                         deterministic
9. validate the rendered artifact                                 deterministic
```

Both LLM steps are **O(columns), not O(rows)**. That is the whole design.

### Step 1 - adapt the input

`scripts/report/adapters.py`. `detect_adapter()` picks by shape:

| input | adapter |
|---|---|
| UIDs on the command line | `adapt_uids` - POST `/nextseek_api/admin/samples/retrieve/` |
| `RETRIEVE.TXT` | `adapt_retrieve_txt` |
| `*_AllMetadata*.xlsx` | `adapt_nextseek_workbook` - local read, no API call |
| `Arm{X}.xlsx` | `adapt_curated_sheet` - local read, works **before** upload |
| any other xlsx / csv | `adapt_tabular` |

All emit the same shape. Everything downstream is adapter-agnostic.

### Steps 2 and 3 - enrichment, never required

`scripts/report/enrich.py` merges leaf-wins: values already in the input are
never overwritten. `scripts/report/protocols.py` resolves `Protocol` refs.
Neither gates output. If NExtSEEK is unreachable, say so and continue.

### Step 4 - emit the mapping spec

**Do not write cell values.** Write a declarative mapping, once, which the
executor applies to every row.

Read the template spec (`context/report_templates/GEO-updated.json` or
`SRA.json` or `pride.json`) and a profile of the input's columns, then emit
`report/<FORMAT>.mapping.json`:

```json
{ "report_type": "GEO",
  "source": {"adapter": "curated_sheet", "path": "assay_sheets/ArmA.xlsx"},
  "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 117},
  "samples": {
    "*library name":         {"source": "UID"},
    "*organism":             {"const": "Homo sapiens"},
    "**tissue":              {"source": "Tissue", "via_lineage": true},
    "*instrument model":     {"const": "Illumina NextSeq 500"},
    "*single or paired-end": {"source": "LibraryLayout",
                              "map": {"paired": "paired-end"}},
    "processed data file":   {"unmapped": "no processed files in source"} },
  "study": {
    "*title":              {"synthesize": "study title from manuscript context"},
    "*summary (abstract)": {"synthesize": "abstract"} } }
```

| directive | meaning |
|---|---|
| `source` | copy from this source column |
| `via_lineage` | resolve by walking the `Parent` chain upward |
| `const` | same literal for every row |
| `map` | value normalization table |
| `synthesize` | free prose you write once. **Study-level only.** |
| `unmapped` | deliberately empty, with a stated reason |

**Use `via_lineage` whenever a column lives on ancestor samples.** Organism,
tissue and cell line usually live on an ancestor, not the `D.SEQ` row. Without
it every row is blank - the validator catches this as `needs_via_lineage`.

**`map` matters.** GEO dropdowns are word- and case-exact: `paired-end` not
`paired`, `Illumina NextSeq 500` not `NextSeq 500`.

### Step 5 - validate the mapping before applying it

`scripts/report/mapping.py` `validate_mapping()`. Cheapest place to fail. Fix
every error and re-validate. Do not proceed with errors outstanding.

### Step 6 - write only the synthesize fields

Study title, summary and experimental design. If the project has a
`manuscript/`, read it. If it does not, say so and let those fields become
placeholders rather than inventing prose.

### Steps 7 through 9

`scripts/report/execute.py` applies the mapping and asserts row parity.
`scripts/report/render.py` renders. `scripts/report/validate_artifact.py`
validates the result, reporting CLEAN / SOFT_FLAG / HARD_REJECT.

## Outputs, all to `./report/`

```
<FORMAT>.mapping.json        the mapping spec - reviewable, editable, REUSABLE
<FORMAT>.completeness.md     what could not be filled, and why
<FORMAT>_filled.json         the applied result
<FORMAT>_filled.xlsx         GEO
SRA_metadata_filled.xlsx     SRA
SRA_biosample_filled.xlsx    SRA
submission.px                PRIDE - tab-delimited, NOT a spreadsheet
```

**Reuse the mapping.** Same PI, same instrument, same assay next quarter: read
the existing `<FORMAT>.mapping.json`, confirm the source columns still exist,
and skip step 4 entirely.

## Hard rules

- **Never silently fabricate a value.** Unfillable fields become
  `*** PLACEHOLDER: ... ***` and appear in the completeness report.
- **Never refuse outright.** Degrade and report. The curator decides.
- **Never write cell values directly.** If you find yourself producing rows,
  you are doing step 4 wrong.
- Show the user the completeness report before declaring success.
- Report the validator's disposition honestly. A `SOFT_FLAG` is not a pass.

## Relationship to `/curate-deposit geo`

Phase 10 delegates its build step here and keeps only external upload and
accession backfill. GEO deposit happens **before** NExtSEEK upload, because
accessions must be backfilled into the sheets first - which is exactly why the
curated-sheet adapter matters.
```

- [ ] **Step 4: Fill in `skills/curation/REPORTS.md`**

```markdown
# `report` mode - submission artifact generation

Deep reference. Load when entering report mode.
Design: `docs/superpowers/specs/2026-07-21-report-mode-design.md`.

## Purpose

*"I have file X.xlsx with metadata, turn it into a GEO report."*

The work is not rendering - the renderer already existed. It is **mapping**:
deciding which source field feeds which target field, and which target fields
must be written by hand.

## State scope

**Input.** Reads a project lockfile when present, for lab and project id, but
runs without one from any cwd. Output goes to `./report/`.

## Formats

| format | row section | row key | target type | artifact |
|---|---|---|---|---|
| GEO | `samples` | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries` + `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata_filled.xlsx` + `SRA_biosample_filled.xlsx` |
| PRIDE | `sample_metadata` + `file_mapping` | `sample_metadata` | `D.MSP` | `submission.px` |

**PRIDE is not a spreadsheet.** `pride.json` declares a tab-delimited
ProteomeXchange Submission Summary File v2.2.1 with `MTD` / `FMH` / `FME` /
`SMH` / `SME` / `COM` line prefixes. chat_nextseek's e2e catalog asserts
`pride.xlsx`, which names the wrong artifact type; it has no exporter at all.
Ours is written from scratch and validated.

**Out of scope: nf-core samplesheets.** A multi-turn interactive wizard with
Seqera/Tower launch concerns. Different problem.

## The mapping spec - the core of the design

The LLM does **not** write cell values. It writes a declarative mapping, once,
applied deterministically to every row. Both LLM steps are **O(columns), not
O(rows)**.

Why: chat_nextseek's `report_writer_agent` has the LLM emit every cell, which
cost *"a 5.1M-token prompt on a 195-UID flow"* (`reports/outputs.py:349-355`)
and was hard-bypassed for nf-core. Its `report_coder_agent` improves on that by
having the LLM write extraction Python, run in an AST sandbox with a row-parity
guard. A declarative mapping achieves the same LLM-decides / code-executes split
while being validatable, human-reviewable, cacheable, and needing no sandbox.

Directives: `source`, `via_lineage`, `const`, `map`, `synthesize`, `unmapped`.
`synthesize` is study-level only, so it stays O(1).

**The mapping is a cacheable artifact.** Same PI, same instrument, same assay
next quarter: reuse it and skip the mapping step entirely.

## Input adapters

Inputs are **not** a mode switch. Each adapter normalizes into one shape and
every downstream step is adapter-agnostic.

| input | behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | `POST /nextseek_api/admin/samples/retrieve/` |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

Normalized shape:

```
{"samples": [{"sample_type": "D.SEQ", "uid": "D.SEQ-...",
              "metadata": {<flat key/value>}, "parent": "TIS-..."}]}
```

The API response is nested five levels (`data.data[i].samples[j].metadata`);
lineage is the flat `Parent` key, an upward UID pointer, **not** nesting.

## Two-stage validation

**Stage 1, before applying:** every target field exists in the template; every
required (`*`) field is `source`/`const`/`synthesize` or explicitly `unmapped`
with a reason; every `const` and every `map` output is in the controlled
vocabulary where one exists; every `source` column exists in the input; and a
column that lives only on ancestors carries `via_lineage`.

**Stage 2, after rendering:** the vendored artifact validator. Its statuses map
onto the pipeline's vocabulary: `Valid` = CLEAN, `Incomplete` = SOFT_FLAG,
`SchemaInvalid` / `Missing` / `Unreadable` = HARD_REJECT.

**Row parity is asserted** even though the executor controls row count by
construction. chat_nextseek's own assessment calls that guard the single most
valuable idea to carry over.

## Graceful degradation

Some GEO fields are derivable only from context an input may lack - organism,
tissue and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. When an input cannot
supply them:

- write `*** PLACEHOLDER: <what is missing> ***` (SKILL.md hard rule 8 -
  greppable; a blank is not), and
- record it in `<FORMAT>.completeness.md` with the field, the input searched,
  and why it failed.

**Never silently fabricate; never refuse outright.**

## No LLM API client

chat_nextseek's `call_llm_structured` is a 20-parameter wrapper over four
provider clients with JSON-repair retries. In a Claude Code plugin the mapping
and synthesize steps are **skill instructions** - the agent reads the template
plus a metadata profile and emits the mapping directly. That removes `config.py`
(83KB, eagerly loads 10+ context files and fetches a remote API schema),
`llm_clients.py` (30KB), and all provider credentials from the port.

## Protocol-chain gotchas

- Refs to `fairdata.mit.edu` are **not** fetched from that host; they are
  redirected to whatever `NEXTSEEK_BASE_URL` is. Only `fairdomhub.org` goes
  off-host, and it needs `FDH_API` as a bearer token with **no fallback**.
- Refs come from a metadata key named literally `Protocol`, matching a
  `/sops/{id}` URL or a bare `P.*` name.
- DOCX extraction is stdlib-only. **PDF needs `PyPDF2`**; upstream silently
  yielded nothing without it, so ours raises `PdfSupportError` instead.
- Protocol text is truncated at ~3000 tokens, and the truncation is recorded in
  the completeness report rather than passing unnoticed.

## Modules

| module | responsibility |
|---|---|
| `scripts/report/adapters.py` | every input to one normalized shape; lineage walking |
| `scripts/report/enrich.py` | additive leaf-wins merge |
| `scripts/report/protocols.py` | SOP discovery, fetch, DOCX/PDF text, truncation |
| `scripts/report/mapping.py` | template spec loading, mapping validation |
| `scripts/report/execute.py` | deterministic application, row parity, completeness |
| `scripts/report/render.py` | format dispatcher and the three renderers |
| `scripts/report/validate_artifact.py` | rendered-artifact validation |

## Relationship to Phase 10

`/curate-deposit geo` **delegates the build** here and keeps only the genuinely
pipeline-specific parts: external upload (`upload_geo_ncftp.sh`) and accession
backfill (`apply_geo_accessions.py`).

Phase 10's GEO route was a dead end - nothing produced the required
`BULK_filled.json` and no GEO template xlsx shipped - so delegation was closer
to a free fix than a rewrite. The ordering is deliberate: GEO deposit happens
**before** NExtSEEK upload, because accessions must be backfilled into the
sheets first. That is why the curated-sheet adapter matters.

## Non-goals

- nf-core samplesheets.
- An LLM API client.
- Porting `reports/outputs.py` - a 400-line function with a hardcoded if/elif
  format dispatch. Ours is a real dispatcher.
- Uploading anything. This mode builds and validates; deposit uploads.

## Open question

**Does `synthesize` need manuscript access?** Study title, summary and
experimental design are prose that likely live in `manuscript/`. In a curation
project that is available; input-scoped runs elsewhere may have nothing, in
which case these become placeholders. That degradation is implemented and
tested; whether it is acceptable in practice is a curator's call.
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_report.py tests/test_mode_table.py -v`
Expected: all pass.

- [ ] **Step 6: End-to-end smoke test in a tmpdir**

```bash
mkdir -p /tmp/report-smoke && cd /tmp/report-smoke
uv run --with openpyxl python3 - <<'PY'
import json, sys, pathlib
PLUGIN = pathlib.Path("/home/cdemu/code/dmac/curation_skill")
sys.path.insert(0, str(PLUGIN / "scripts"))
from openpyxl import Workbook
from report import adapters, mapping, execute, render, validate_artifact

# A curated Arm sheet, as /curate-consolidate would emit it.
wb = Workbook(); ws = wb.active; ws.title = "Samples"
ws.append(["uid", "sampletype", "parent", "json_metadata"])
for i in (1, 2, 3):
    ws.append([f"D.SEQ-190903KAM-{i}", "D.SEQ", "TIS-190903KAM-1",
               json.dumps({"UID": f"D.SEQ-190903KAM-{i}",
                           "Parent": "TIS-190903KAM-1",
                           "LibraryLayout": "paired"})])
ws.append(["TIS-190903KAM-1", "TIS", "",
           json.dumps({"UID": "TIS-190903KAM-1", "Tissue": "liver"})])
wb.save("ArmA.xlsx")

normalized = adapters.adapt(pathlib.Path("ArmA.xlsx"))
print(f"adapted {len(normalized.samples)} samples via {normalized.source['adapter']}")

spec = mapping.load_template_spec(
    PLUGIN / "context/report_templates/GEO-updated.json")
m = {"report_type": "GEO",
     "source": {"adapter": "curated_sheet", "path": "ArmA.xlsx"},
     "row_scope": {"target_sampletype": "D.SEQ", "expected_rows": 3},
     "samples": {
        "*library name": {"source": "UID"},
        "*title": {"source": "UID"},
        "*library strategy": {"const": "RNA-Seq"},
        "*organism": {"const": "Homo sapiens"},
        "**tissue": {"source": "Tissue", "via_lineage": True},
        "*molecule": {"const": "polyA RNA"},
        "*single or paired-end": {"source": "LibraryLayout",
                                  "map": {"paired": "paired-end"}},
        "*instrument model": {"const": "Illumina NextSeq 500"},
        "*raw file": {"unmapped": "added at deposit time"}},
     "study": {"*title": {"synthesize": "study title"},
               "*summary (abstract)": {"synthesize": "abstract"},
               "*experimental design": {"synthesize": "design"}}}

errs = mapping.validate_mapping(m, spec, normalized)
print("mapping errors:", [f"{e.code}:{e.field}" for e in errs] or "none")
assert not errs

filled, gaps = execute.apply_mapping(m, spec, normalized)
print(f"rows: {len(filled['samples'])}  gaps: {len(gaps)}")
print("tissue via lineage:", filled["samples"][0]["**tissue"])
print("layout mapped:", filled["samples"][0]["*single or paired-end"])

root = pathlib.Path.cwd()
execute.write_filled(root, "GEO", filled)
execute.write_completeness(root, "GEO",
    execute.render_completeness("GEO", gaps, m, normalized))
outs = render.render("GEO", filled,
                     template_dir=PLUGIN / "context/report_templates",
                     out_dir=root / "report")
print("rendered:", [p.name for p in outs])
r = validate_artifact.validate_geo_xlsx(
    file_path=outs[0],
    geo_template_path=PLUGIN / "context/report_templates/GEO-updated.json")
print(f"validator: {r.status.value} -> {r.disposition}")
print("missing:", r.missing_required_fields)
PY
ls -la report/
cd - >/dev/null
```

Expected: 4 samples adapted, no mapping errors, 3 rows, `**tissue` resolved to
`liver` via lineage, `paired` mapped to `paired-end`, an xlsx rendered, and the
validator reporting a status. Gaps are expected for the three `synthesize`
fields, since no prose was supplied — that is the degradation path working.

Then confirm the plugin is untouched: `git status --short`

- [ ] **Step 7: Commit**

```bash
git add commands/curate-report.md skills/curation/REPORTS.md \
        tests/test_curate_report.py
git commit -m "feat(report): /curate-report and the REPORTS.md reference

Steps 4 and 6 are skill instructions, not an LLM API client. That removes
chat_nextseek's config.py (83KB, eagerly loads 10+ context files and fetches a
remote API schema), llm_clients.py (30KB), and every provider credential from
the port.

The command forbids writing cell values directly, which is the failure mode the
whole design exists to prevent: chat_nextseek's per-cell writer cost a
5.1M-token prompt on a 195-UID flow.

REPORTS.md records the three artifact shapes, both validation stages, the
protocol-chain gotchas, and that PRIDE is a tab-delimited submission.px rather
than a spreadsheet.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 32: Phase 10 delegates its GEO build to `report` mode

**Files:**
- Modify: `commands/curate-deposit.md` (the `geo` sub-route)
- Modify: `skills/curation/PHASES.md` Phase 10 section
- Test: `tests/test_deposit_delegates_geo.py`

**Interfaces:**
- Consumes: `/curate-report` from Task 31
- Produces: a `/curate-deposit geo` route that builds via report mode and keeps only upload plus accession backfill

**Context (toolkit spec O2, decided):** Phase 10's GEO route is a **dead end** today — nothing produces the required `BULK_filled.json` and no GEO template xlsx ships. Delegation is closer to a free fix than a rewrite. The alternative, two GEO paths, is the exact divergence the spec warns against elsewhere.

- [ ] **Step 1: Write the failing test**

Create `tests/test_deposit_delegates_geo.py`:

```python
"""Phase 10's GEO route delegates its build to report mode."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEPOSIT = REPO / "commands" / "curate-deposit.md"
PHASES = REPO / "skills" / "curation" / "PHASES.md"


def _geo_route() -> str:
    text = DEPOSIT.read_text()
    return text.split("### `/curate-deposit geo", 1)[1].split("### ", 1)[0]


def test_geo_route_delegates_the_build():
    route = _geo_route()
    assert "/curate-report GEO" in route


def test_geo_route_no_longer_invokes_the_renderer_directly():
    """Two GEO paths is the exact divergence the spec warns against."""
    route = _geo_route()
    assert "geo_build_xlsx.py" not in route


def test_geo_route_no_longer_names_the_phantom_input():
    """Nothing has ever produced BULK_filled.json."""
    assert "BULK_filled.json" not in DEPOSIT.read_text()


def test_geo_route_keeps_upload_and_backfill():
    route = _geo_route()
    assert "upload_geo_ncftp.sh" in route
    assert "apply_geo_accessions.py" in route


def test_geo_route_explains_the_ordering():
    route = _geo_route()
    assert "before" in route.lower()
    assert "accession" in route.lower()


def test_phases_records_the_delegation():
    text = PHASES.read_text()
    section = text.split("## Phase 10 ", 1)[1].split("\n## ", 1)[0]
    assert "/curate-report GEO" in section
    assert "dead end" in section.lower()


def test_only_one_geo_build_path_exists_in_the_docs():
    blob = DEPOSIT.read_text() + PHASES.read_text()
    assert blob.count("geo_build_xlsx.py") <= 1, (
        "the renderer should be named once, by report mode's docs")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_deposit_delegates_geo.py -v`
Expected: FAILs — the route still names `geo_build_xlsx.py` and `BULK_filled.json`.

- [ ] **Step 3: Rewrite the `geo` sub-route in `commands/curate-deposit.md`**

```markdown
### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

1. **Build - delegated.** Run `/curate-report GEO <input>` and let report mode
   produce `report/GEO_filled.xlsx` plus its completeness report. Do **not**
   invoke a renderer here; there is exactly one GEO build path and it lives in
   report mode.

   The input is usually a curated `assay_sheets/Arm{X}.xlsx`, because **GEO
   deposit happens before NExtSEEK upload** - accessions must be backfilled into
   the sheets first. The curated-sheet adapter reads those sheets locally, with
   no API call, which is exactly what that ordering requires.

   Read `report/GEO.completeness.md` with the user before uploading anything.
   A submission with unresolved `*** PLACEHOLDER: ... ***` markers will be
   rejected by GEO, and finding that out from NCBI is slower than finding it
   out here.

2. **Upload**: `<PLUGIN>/scripts/upload_geo_ncftp.sh GEO/<subfolder>/`. Reads
   `.env` for `NCFTP_*` credentials. Has a retry loop.

3. **Validate**: ask the user to validate at
   submit.ncbi.nlm.nih.gov/geo/submission. Report mode's own validator has
   already checked structure and required fields; NCBI checks the rest.

4. **Backfill, after a GSE is assigned**:
   `<PLUGIN>/scripts/apply_geo_accessions.py --write --gse <GSE>` patches
   D.SEQ / A.GEX / A.SPTX rows with GSM URLs. Rows with no assigned GSM fall
   back to the series URL rather than being left blank. Run it once **without**
   `--write` first and show the user the diff.
```

- [ ] **Step 4: Update the `PHASES.md` Phase 10 GEO block**

```markdown
### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

**The build is delegated to `report` mode.** Run `/curate-report GEO <input>`;
Phase 10 keeps only the genuinely pipeline-specific parts, external upload
(`upload_geo_ncftp.sh`) and accession backfill (`apply_geo_accessions.py`).

This route was a **dead end** before the delegation: nothing produced the
`BULK_filled.json` it named as an input, and no GEO template xlsx shipped with
the plugin. Delegation was closer to a free fix than a rewrite, and it avoids
maintaining two GEO build paths - the exact divergence the toolkit spec warns
about elsewhere.

Ordering is deliberate: GEO deposit happens **before** NExtSEEK upload, because
accessions must be backfilled into the sheets first. That is why report mode's
curated-sheet adapter, which reads `assay_sheets/Arm{X}.xlsx` locally with no
API call, is the one that matters here.
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest pytest tests/test_deposit_delegates_geo.py tests/test_deposit_write_safety.py tests/test_curate_commands_present.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add commands/curate-deposit.md skills/curation/PHASES.md \
        tests/test_deposit_delegates_geo.py
git commit -m "refactor(deposit): Phase 10 delegates the GEO build to report mode

The route was a dead end: nothing produced the BULK_filled.json it named as an
input and no GEO template xlsx shipped. It now runs /curate-report GEO and keeps
only external upload and accession backfill, so there is exactly one GEO build
path rather than two divergent ones.

Documents why the ordering is what it is: GEO deposit happens before NExtSEEK
upload because accessions must be backfilled into the sheets first, which is
precisely why report mode's curated-sheet adapter reads Arm{X}.xlsx locally with
no API call.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 33: Harvest API fixtures rather than authoring them

**Files:**
- Create: `tests/fixtures/nextseek/README.md`
- Create: `tests/fixtures/nextseek/report_metadata.json` (harvested)
- Create: `tests/fixtures/nextseek/protocols.json` (harvested)
- Create: `tests/fixtures/nextseek/protocol_files.json` (harvested)
- Create: `scripts/report/scrub_fixture.py`
- Test: `tests/test_report_fixtures.py`

**Interfaces:**
- Consumes: `adapters.adapt_uids` from Task 26; `protocols.resolve_protocols` from Task 30
- Produces: `scrub_fixture.scrub(doc) -> dict` removing credentials and localhost URLs; committed fixtures exercising the adapter against a real API response shape

**Context (user correction ANN-10):** chat_nextseek **does** record API fixtures — every report run persists `report_metadata.json`, `protocols.json` and `protocol_files.json` (`reports/outputs.py:555-563`), and non-report runs leave `api_requests.json` and `api_result_bundle_*.json`. **Fixtures are harvested from run directories, not authored.** What is genuinely absent is fixtures *committed under `tests/`*: the whole committed corpus upstream is two inline dicts.

- [ ] **Step 1: Look for existing run directories before generating new ones**

```bash
ls -la ~/.local/state/chat_nextseek/outputs/ 2>/dev/null | head -20
find ~/.local/state/chat_nextseek/outputs -maxdepth 2 \
     \( -name 'report_metadata.json' -o -name 'protocols.json' \
        -o -name 'protocol_files.json' -o -name 'api_result_bundle_*.json' \) \
     2>/dev/null | head -20
```

If artifacts already exist, **use them** and skip Step 2. Four such run dirs were confirmed to exist at the time this plan was written.

- [ ] **Step 2: Only if none exist — generate one run**

Take a UID set from `e2e/catalog.json` family `reporting`, which carries real production UIDs (`D.SEQ-190210SHA-67-PUB`, `D.SEQ-190702FOR-288-PUB`, `D.MSP-190802GRI-4-PUB`):

```bash
cd /home/cdemu/code/chat_nextseek
uv run cli.py -q "Build me a GEO Submission for D.SEQ-190210SHA-67-PUB D.SEQ-190702FOR-288-PUB"
```

**This makes live API calls against production NExtSEEK and needs credentials.** If credentials are unavailable, stop here and report — do **not** hand-author a fake response. A fabricated fixture that diverges from the real five-level nesting is worse than no fixture, because it would make the adapter tests pass against a shape the API never returns.

- [ ] **Step 3: Write the scrubber**

Create `scripts/report/scrub_fixture.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Strip credentials and host-specific URLs from a harvested API fixture.

Fixtures are HARVESTED from chat_nextseek run directories, not authored. Every
report run persists exactly the responses this plugin needs
(reports/outputs.py:555-563). Authoring one by hand would risk a shape the API
never returns -- the retrieve response is nested five levels and it is easy to
get wrong from memory.

Scrubbing is required before committing: run directories contain real tokens and
localhost URLs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECRET_KEY_RE = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|authorization|cookie)",
    re.IGNORECASE)
LOCALHOST_RE = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", re.IGNORECASE)
BASIC_AUTH_RE = re.compile(r"://[^/@\s:]+:[^/@\s]+@")

REDACTED = "***REDACTED***"
PLACEHOLDER_HOST = "https://nextseek.example.org"


def _scrub_text(text: str) -> str:
    text = LOCALHOST_RE.sub(PLACEHOLDER_HOST, text)
    return BASIC_AUTH_RE.sub("://", text)


def scrub(doc):
    """Recursively redact secret-looking keys and rewrite host-specific URLs."""
    if isinstance(doc, dict):
        out = {}
        for key, value in doc.items():
            if SECRET_KEY_RE.search(str(key)):
                out[key] = REDACTED
            else:
                out[key] = scrub(value)
        return out
    if isinstance(doc, list):
        return [scrub(v) for v in doc]
    if isinstance(doc, str):
        return _scrub_text(doc)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Harvested JSON artifact")
    ap.add_argument("dest", type=Path, help="Where to write the scrubbed copy")
    args = ap.parse_args(argv)
    doc = json.loads(args.source.read_text())
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(json.dumps(scrub(doc), indent=2) + "\n")
    print(f"scrubbed {args.source} -> {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write the failing test**

Create `tests/test_report_fixtures.py`:

```python
"""Harvested API fixtures, scrubbed and committed."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures" / "nextseek"
sys.path.insert(0, str(REPO / "scripts"))

from report import adapters as ad  # noqa: E402
from report import scrub_fixture as sf  # noqa: E402

HARVESTED = ["report_metadata.json", "protocols.json", "protocol_files.json"]


# ---- the scrubber, testable without any fixture ---------------------------

def test_scrub_redacts_secret_looking_keys():
    out = sf.scrub({"token": "abc", "api_key": "d", "Authorization": "Bearer x",
                    "name": "keep me"})
    assert out["token"] == sf.REDACTED
    assert out["api_key"] == sf.REDACTED
    assert out["Authorization"] == sf.REDACTED
    assert out["name"] == "keep me"


def test_scrub_recurses_into_lists_and_dicts():
    out = sf.scrub({"a": [{"password": "p"}, {"ok": 1}]})
    assert out["a"][0]["password"] == sf.REDACTED
    assert out["a"][1]["ok"] == 1


def test_scrub_rewrites_localhost_urls():
    out = sf.scrub({"url": "http://localhost:8000/nextseek_api/sops/1/"})
    assert "localhost" not in out["url"]
    assert out["url"].endswith("/nextseek_api/sops/1/")


def test_scrub_strips_basic_auth_from_urls():
    out = sf.scrub({"url": "https://user:hunter2@nextseek.mit.edu/x"})
    assert "hunter2" not in out["url"]


def test_scrub_leaves_ordinary_values_alone():
    assert sf.scrub({"n": 3, "b": True, "s": "D.SEQ-1"}) == {
        "n": 3, "b": True, "s": "D.SEQ-1"}


# ---- the fixtures themselves ---------------------------------------------

@pytest.mark.parametrize("name", HARVESTED)
def test_fixture_present(name):
    if not (FIX / name).is_file():
        pytest.skip(f"{name} not harvested yet; see tests/fixtures/nextseek/README.md")


@pytest.mark.parametrize("name", HARVESTED)
def test_fixture_carries_no_credentials(name):
    p = FIX / name
    if not p.is_file():
        pytest.skip("not harvested yet")
    text = p.read_text().lower()
    for leak in ("password", "bearer ", "apikey token=", "localhost", "127.0.0.1"):
        assert leak not in text, f"{name} still contains {leak!r}"


def test_retrieve_fixture_has_the_five_level_nesting():
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    assert "data" in doc and "data" in doc["data"]
    group = doc["data"]["data"][0]
    assert "samples" in group
    assert "metadata" in group["samples"][0]


def test_adapter_handles_the_real_response_shape():
    """The point of harvesting: the adapter is exercised against a shape the
    API actually returns, not one written from memory."""
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    got = ad.adapt_uids(["fixture"], fetch=lambda uids: doc)
    assert got.samples
    for s in got.samples:
        assert s.uid
        assert isinstance(s.metadata, dict)


def test_lineage_resolves_in_the_real_fixture():
    p = FIX / "report_metadata.json"
    if not p.is_file():
        pytest.skip("not harvested yet")
    doc = json.loads(p.read_text())
    got = ad.adapt_uids(["fixture"], fetch=lambda uids: doc)
    by_uid = ad.index_by_uid(got)
    assert any(s.parent and s.parent in by_uid for s in got.samples), (
        "no resolvable Parent pointer in the fixture; lineage walking is "
        "untested against real data")


def test_readme_documents_the_harvest_procedure():
    text = (FIX / "README.md").read_text()
    assert "outputs.py" in text
    assert "harvest" in text.lower()
    assert "scrub_fixture.py" in text
```

- [ ] **Step 5: Write the fixture README**

Create `tests/fixtures/nextseek/README.md`:

```markdown
# Harvested NExtSEEK API fixtures

These are **harvested**, not authored.

chat_nextseek persists exactly the API responses this plugin needs, on every
report run (`reports/outputs.py:555-563`):

| artifact | content |
|---|---|
| `report_metadata.json` | the `/admin/samples/retrieve/` response |
| `protocols.json` | the `/sops/{id}/` responses |
| `protocol_files.json` | downloaded blobs plus extracted docx/pdf text |

Non-report runs additionally leave `api_requests.json` and
`api_result_bundle_*.json` in the same run directories.

## Why harvest rather than author

The retrieve response is nested five levels
(`data.data[i].samples[j].metadata`) and lineage is the flat `Parent` key, an
upward UID pointer, not nesting. A hand-written fixture that gets that wrong
would make the adapter tests pass against a shape the API never returns, which
is worse than having no fixture.

## Procedure

1. Look for existing runs first:

   ```bash
   ls ~/.local/state/chat_nextseek/outputs/
   ```

2. If none carry what you need, generate one. Take UIDs from
   `e2e/catalog.json` family `reporting`, which has real production UIDs:

   ```bash
   cd /home/cdemu/code/chat_nextseek
   uv run cli.py -q "Build me a GEO Submission for D.SEQ-190210SHA-67-PUB"
   ```

3. Scrub before committing. Run directories contain real tokens and localhost
   URLs:

   ```bash
   uv run --script <PLUGIN>/scripts/report/scrub_fixture.py \
       ~/.local/state/chat_nextseek/outputs/<run>/report_metadata.json \
       tests/fixtures/nextseek/report_metadata.json
   ```

4. `tests/test_report_fixtures.py` asserts the scrubbing worked. It skips
   cleanly when a fixture has not been harvested, so the suite stays green on a
   machine with no NExtSEEK access.

## What was genuinely missing upstream

Not the fixtures - those are produced on every run. What is absent is fixtures
**committed under `tests/`**: chat_nextseek's entire committed corpus for this
path is two inline dicts, in `test_report_code.py` and
`test_report_outputs_gating.py`. Committing scrubbed harvested artifacts here is
new coverage, not a copy.
```

- [ ] **Step 6: Harvest and scrub, if run dirs exist**

```bash
RUN=$(ls -dt ~/.local/state/chat_nextseek/outputs/*/ 2>/dev/null | head -1)
echo "using run: $RUN"
for f in report_metadata.json protocols.json protocol_files.json; do
  if [ -f "$RUN/$f" ]; then
    uv run --script scripts/report/scrub_fixture.py "$RUN/$f" "tests/fixtures/nextseek/$f"
  else
    echo "  (absent: $f)"
  fi
done
```

- [ ] **Step 7: Run the tests**

Run: `uv run --with pytest --with openpyxl pytest tests/test_report_fixtures.py -v`
Expected: the scrubber tests pass. The fixture tests either pass (harvested) or skip cleanly (not harvested). **A skip is an acceptable outcome** — the suite must stay green on a machine without NExtSEEK access.

- [ ] **Step 8: Commit**

```bash
git add scripts/report/scrub_fixture.py tests/fixtures/nextseek/ \
        tests/test_report_fixtures.py
git commit -m "test(report): harvest and scrub NExtSEEK API fixtures

Fixtures are harvested, not authored. chat_nextseek persists exactly the
responses this plugin needs on every report run (reports/outputs.py:555-563).
Authoring one by hand risks a shape the API never returns -- the retrieve
response is nested five levels and lineage is a flat upward Parent pointer, not
nesting -- which would make the adapter tests pass against fiction.

scrub_fixture.py redacts secret-looking keys, rewrites localhost URLs and strips
basic-auth credentials before anything is committed. The fixture tests skip
cleanly when nothing has been harvested, so the suite stays green without
NExtSEEK access.

What was genuinely missing upstream is fixtures COMMITTED under tests/: the
whole upstream corpus for this path is two inline dicts.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 34: Full-suite verification, changelog, and release

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Test: the whole suite

**Interfaces:**
- Consumes: every prior task
- Produces: a green suite, a changelog entry for 0.3.0, and a README that describes four modes

- [ ] **Step 1: Run the full suite**

Run: `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ -v 2>&1 | tail -40`

Expected: everything passes or skips. **If anything fails, fix it before continuing** — do not write a changelog entry claiming work that does not pass.

- [ ] **Step 2: Confirm no test wrote inside the plugin**

Run:

```bash
git status --short
```

Expected: only the files this plan intends to change. **If a test left artifacts inside the checkout, that is a P1 regression** — find which one and fix it before releasing.

- [ ] **Step 3: Confirm every script still runs**

```bash
for s in scripts/*.py scripts/deposit/*.py scripts/report/*.py scripts/schema/*.py; do
  case "$s" in
    */__init__.py|*/_common.py|*/_config.py|*/_lockfile.py|*/enrich.py|*/adapters.py|*/mapping.py|*/execute.py|*/render.py|*/validate_artifact.py|*/protocols.py|*/field_index.py|*/dictionary.py|*/ontology.py|*/terms.py|*/review.py)
      continue ;;
  esac
  printf '%-52s' "$s"
  if uv run --script "$s" --help >/dev/null 2>&1; then echo "ok"; else echo "FAILED"; fi
done
```

Expected: every CLI script prints `ok`. Library modules are skipped because they have no CLI.

- [ ] **Step 4: Confirm the identity strings are still in sync**

Run: `uv run --with pytest pytest tests/test_identity_sync.py tests/test_mode_table.py tests/test_phases_doc.py -v`
Expected: all pass.

- [ ] **Step 5: Write the changelog entry**

Prepend to `CHANGELOG.md`, under a `## 0.3.0` heading dated today:

```markdown
## 0.3.0 - 2026-07-21

Reframed from a 13-phase pipeline into a four-mode curator's workbench.

### Added

- **`schema` mode** (`/curate-sampletype <TYPE>`) - propose or bolster a
  NExtSEEK sample type. Field index and reuse check over the 1059 field names
  (856 of which are used by exactly one type), controlled-vocabulary proposals
  sourced from the Tags column, observed values and BioPortal, and a
  `<TYPE>.review.md` written for a human deciding what to apply. cwd-scoped;
  needs no project. Never writes to NExtSEEK.
- **`report` mode** (`/curate-report <FORMAT> <input>`) - GEO, SRA and PRIDE
  submission artifacts from UIDs, a NExtSEEK workbook, a curated `Arm{X}.xlsx`,
  or arbitrary tabular data. The LLM emits one declarative mapping spec,
  O(columns); execution across rows is deterministic. Input-scoped; runs without
  a lockfile.
- `scripts/_config.py` - the single project-config seam, resolved from cwd.
- `scripts/_lockfile.py` - lockfile schema v1 with `modes{}`, and in-memory v0
  migration.
- `scripts/status.py` - `/curate-status` now reports per mode.
- `scripts/refresh_context.py` - a real refresh path for bundled `context/`,
  plus `context/PROVENANCE.json` recording source, commit and sha256 per
  vendored file.
- `--gse` on `apply_geo_accessions.py`; `--retrieve` and `--assay-sheets` on
  `review_metadata_vs_uploads.py`; `--upload`, `--master-baseline` and
  `--expected-counts` on `qa_flat_sheets.py`; `--assay-sheets` on
  `consolidate_to_flat.py`.
- `docs/SECURITY.md`, and a test that fails if a plaintext token reappears.

### Changed

- **Identity.** The plugin is the curator's workbench, not a pipeline. One
  canonical description in `plugin.json`, `marketplace.json` and `SKILL.md`,
  asserted identical by test.
- **`SKILL.md` carries a mode table**; the phase table moved to `PHASES.md`.
- **`/curate-init` is additive** - creates what is missing, never overwrites,
  and merges a mode into an existing lockfile rather than refusing to run.
- **13 phases became 11.** Phase 4 (task plan) and Phase 8 (synonyms) are
  retired as numbers; neither had a command of its own. Surviving numbers are
  deliberately not renumbered.
- **Phase 10's GEO build delegates to `report` mode.** It keeps external upload
  and accession backfill only.
- `templates/CLAUDE.md.j2` is mode-aware.

### Fixed

- **Ten scripts resolved project paths against the plugin install directory**,
  so `/curate-consolidate` and `/curate-qa` read and wrote *inside the plugin
  checkout* - `consolidate_to_flat.py` deleted xlsx files there. All now resolve
  from cwd. A regression harness hashes the plugin tree around every script run.
- **`stage_zenodo.py` and `apply_zenodo_links.py` used `--dry-run` and therefore
  defaulted to WRITING**, while `curate-deposit.md` claimed all four deposit
  scripts defaulted to dry-run. All four now default to dry-run and require
  `--write`.
- **Phase 12 never read `RETRIEVE.TXT`** despite `PHASES.md` naming it as an
  input. It now does, separating auto-pulled lineage parents from genuinely
  unexpected extra rows.
- **`scripts/_common.py` carried one project's constants** - a scientist's name,
  a hardcoded master filename, a cell-line UID table, manuscript section titles
  - and every importer inherited them. It is a library now.
- Plaintext FairDomHub tokens on disk under `working/`. Rotated and removed.
- `context/neo4j_schema.json` was a **dev-instance** snapshot with 23 `Sample`
  properties where the live schema has 85, and `VINTAGE.json` pointed at a
  refresh tool that did not exist.

### Documented

- **Phase 5's 4-sheet output is a curator review artifact, not a build
  intermediate.** That is why Phases 5 and 6 do not collapse, and it appeared in
  no file in the repo.
- **Ontology validation exists only in the 4-sheet format.** An ontology column
  added to a flat sheet is accepted and *silently discarded*, because
  `InputRowModel` is `additionalProperties: true`. Read from a 2026-05-27 API
  spec and flagged for confirmation with the API owner.
- **PRIDE is not a spreadsheet.** `pride.json` declares a tab-delimited
  ProteomeXchange submission summary file. chat_nextseek's e2e catalog asserting
  `pride.xlsx` names the wrong artifact type.
- Why CEDAR templates are out of scope: CEDAR's model is a nested tree with no
  cross-record reference concept; NExtSEEK lineage is a graph, so referential
  integrity would live entirely outside it.

### Known open questions

- Whether the flat upload format has gained ontology support since 2026-05-27.
  Both `schema` and `pipeline` mode docs depend on it still lacking one.
  **Confirm with the NExtSEEK API owner.**
- What "apply" concretely means for a proposed sample type record: admin UI,
  SQL update, or a PR against a schema repo. `<TYPE>.review.md` says to ask.
```

- [ ] **Step 6: Update `README.md`**

Replace the description of the plugin as a 13-phase pipeline with the four-mode
framing. At minimum:

- the opening paragraph names the four modes and links their reference docs
- the command list is grouped by mode, not by phase number
- the install section is unchanged
- add a "What this is not" line: it does not upload to NExtSEEK on its own, it
  does not edit the sample type catalog, and it does not fabricate values

Then verify the README's claims are true:

```bash
grep -o '/curate-[a-z-]*\|/fdh-[a-z-]*' README.md | sort -u | while read -r cmd; do
  f="commands/${cmd#/}.md"
  [ -f "$f" ] && echo "ok   $cmd" || echo "MISSING $cmd -> $f"
done
```

Expected: every command named in the README resolves to a real command file.

- [ ] **Step 7: Run the full suite one final time**

Run: `uv run --with pytest --with openpyxl --with jinja2 pytest tests/ 2>&1 | tail -15`
Expected: all green. Record the exact pass/skip counts; they go in the commit message.

- [ ] **Step 8: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: 0.3.0 changelog and four-mode README

Full suite green. The changelog records what changed and, more usefully, the
four things that were wrong and are now documented: ten scripts wrote inside the
plugin checkout, two deposit scripts defaulted to writing while the docs claimed
dry-run, Phase 12 never read the input it documented, and the bundled graph
schema was a dev snapshot with a quarter of the live property count.

Two open questions are recorded rather than papered over: whether flat uploads
still lack ontology support, and what applying a proposed sample type record
concretely means.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes

Checked after writing, per the writing-plans skill:

**Spec coverage.** Every section of the four specs maps to a task. Toolkit spec:
identity prose (11), mode table (12), lockfile (10), P1 (6, 8), P2 (7), P3 (9),
secrets (2), dry-run conventions (4), stale context (18), command drift (3, 5),
decomposition (F, G), vendoring (24, 25), O1 (F), O2 (16, 32), O3 (26), O4 (12).
Pipeline review: 4-sheet reasoning and Ontology sheet (16, 21), phases 4 and 8
(12, 16), five defects (4, 5, 17, 32). Schema spec: field dictionary (20), reuse
check (19), Tags mining (19, 21), Ontology round trip (21), BioPortal (22),
review doc (23), tree-vs-graph (23). Report spec: adapters (26), mapping (27),
validation (25, 27), executor and degradation (28), renderers (29), protocols
(30), fixtures (33), Phase 10 (32), vendored assets (24).

**Deliberate deviations from the specs, each with a reason recorded in its task:**

1. **PRIDE renders `submission.px`, not `pride.xlsx`.** `pride.json` declares a
   tab-delimited format. The spec inherited chat_nextseek's framing of a missing
   *exporter*; the real problem is a wrong artifact *type*.
2. **SRA renders two workbooks.** `SRA.json` has two row-bearing sections and
   both templates ship.
3. **Report spec open question 1 is resolved in Task 24**, not left open: the
   two `GEO-updated.json` copies are byte-identical.
4. **The batch-upload module is not vendored.** The spec lists it, but nothing
   in the two new modes consumes it, and vendoring 1,250 lines with no caller
   would add exactly the unowned-copy problem `PROVENANCE.json` exists to
   prevent. Its assay-superset and `invented_attribute` guards belong to a
   future upload mode, not this work.

**Unverified claims carried forward, flagged in the tasks that depend on them:**

- Flat uploads lack ontology support (read from a 2026-05-27 spec). Tasks 16 and
  23 both instruct confirming with the API owner and record the vintage.
- The `NCBITaxon_10090` strain binding is wrong. Verified by reading the
  prototype; the mitigation (never auto-confirm) does not depend on it.

**Sequencing risk.** Tasks 3 and 6 land deliberately RED and are turned green by
4/5/17 and 8 respectively. Task 10 leaves one assertion RED until Task 11, and
Task 11 leaves one RED until Task 13. Each is stated in the task that creates it
and in the task that closes it. Do not "fix" a RED test by weakening it.
