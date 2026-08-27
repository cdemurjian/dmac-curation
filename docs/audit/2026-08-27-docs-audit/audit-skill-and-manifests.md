# Drift audit — `skills/curation/SKILL.md` + the two plugin manifests

**Target files**

- `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs/skills/curation/SKILL.md`
- `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs/.claude-plugin/plugin.json`
- `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs/.claude-plugin/marketplace.json`

**Worktree** `.../.claude/worktrees/docs`, branch `dev-docs`, HEAD `833e9be`.
Every claim below was read out of the cited file at this SHA, and the executable
claim (F4) was reproduced by running the command.

**Verdict: SUBSTANTIAL_DRIFT.**

---

## The shape of the drift, in one paragraph

The **mode table** (`SKILL.md:28-34`) is fully current: I diffed its 26 command
names against `ls commands/*.md` and the two sets are identical, with `assay`
present and pointing at a real `ASSAY.md`. Everything *around* the table still
describes the four-mode plugin that existed before commit `eb8777e`
("register assay as the fifth curation mode"). The single highest-impact
instance is the **canonical description string**, which is byte-identical across
`plugin.json`, `marketplace.json`, `SKILL.md` frontmatter *and*
`tests/test_identity_sync.py`, and which names only pipeline / fdh / schema /
report. That string is what skill activation matches on — the test file's own
docstring says so — so the fifth mode is invisible to activation. Three smaller
items are internal self-contradictions inside SKILL.md (`assay-vocabulary`
filed under `schema`, "one mode among four", "all four sources" against a
five-item list), one is an instruction that is now executably wrong (hard rule
6's `uv run --script` does not work for any `assay_hygiene` module), and one is
a version-metadata mismatch.

---

## A note before applying anything

**The description string lives in FOUR files, not three.**

```
.claude-plugin/plugin.json          "description"
.claude-plugin/marketplace.json     plugins[0].description
skills/curation/SKILL.md            frontmatter description:
tests/test_identity_sync.py         CANONICAL_DESCRIPTION
```

`tests/test_identity_sync.py` asserts all three files equal
`CANONICAL_DESCRIPTION` byte for byte, so changing three of the four turns the
suite red. Two further tests in that file need touching as well
(`test_description_names_every_mode`, `test_version_is_the_toolkit_release`).
Full patch in F1 and F8 below.

The description also lives in **unquoted YAML frontmatter**. A mid-string
colon-space (`": "`) makes the frontmatter parse as a mapping and the skill
then does not load at all — `test_description_is_yaml_safe_frontmatter` guards
exactly this regression. **The replacement string below was round-tripped
through `yaml.safe_load` and contains no colon-space.**

---

## F1 — WRONG — the canonical description names four modes; there are five

**Where:** `SKILL.md:3` (frontmatter), `.claude-plugin/plugin.json:4`,
`.claude-plugin/marketplace.json:14`. All three are byte-identical, 613 chars.

**Claim:**

> "Modes are pipeline (14 commands, 12 phases …), fdh (FairDomHub upload and
> direct API), schema (sample type authoring and controlled vocabulary), report
> (GEO / SRA / PRIDE submission artifacts). Activate when working in a directory
> containing files/, manuscript/, previous_metadata/, or any
> .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub,
> curation, sample types, or a GEO/SRA/PRIDE submission."

**Reality:** five modes. `SKILL.md:34` carries the `assay` row; `commands/`
holds 8 `curate-assay-*.md` files; `skills/curation/ASSAY.md` exists;
`tests/test_mode_table.py:13-19` already lists `"assay": "ASSAY.md"` in
`EXPECTED_MODES`. The description is the only identity artefact that never got
the update.

**Why it matters, concretely.** The `assay` mode is house-scoped — it runs
against `scripts/` + `assets/`, with no `files/`, no `manuscript/`, no
`previous_metadata/` and no `.dmac-curation.json`. **Not one activation cue in
the current string fires for it**, and none of its vocabulary ("assay hygiene",
"register these samples") appears either. `tests/test_identity_sync.py:3-4`
states the failure mode itself: *"the description is what skill activation
matches on, so a pipeline-only description makes schema and report modes
invisible."* The same sentence now applies to `assay`.

### Replacement string (845 chars, YAML-verified, no colon-space)

```
Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.
```

`assets/assay-run.json` is a real, checkable cue:
`scripts/assay_hygiene/runstate.py:22` sets `LOCK_NAME = "assay-run.json"` and
`:32` resolves it as `root / LOCK_NAME`; `commands/curate-assay-status.md:9-10`
calls `read(Path('assets'))`; `ASSAY.md:11` says "State is
`assets/assay-run.json`".

### Apply to `SKILL.md:3` (frontmatter, single unquoted line)

```yaml
description: Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.
```

### Apply to `.claude-plugin/plugin.json:4`

```json
  "description": "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.",
```

### Apply to `.claude-plugin/marketplace.json:14`

```json
      "description": "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to email PI), fdh (FairDomHub upload and direct API), schema (sample type authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission artifacts), assay (house-scoped assay hygiene - 8 commands that find unregistered sample-assay pairs, put every proposal in front of a human, and write the approved ones to production). Activate when working in a directory containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, FairDomHub, curation, sample types, assay hygiene, assay registration, or a GEO/SRA/PRIDE submission.",
```

### Apply to `tests/test_identity_sync.py:16-27` (required — the suite goes red otherwise)

```python
CANONICAL_DESCRIPTION = (
    "Curator's workbench for NExtSEEK / FairDomHub metadata. Human-in-the-loop, "
    "PI-facing. Modes are pipeline (14 commands, 12 phases from inventory through "
    "sample tree, build, consolidate, QA, server-side QC, deposit, retrieve, to "
    "email PI), fdh (FairDomHub upload and direct API), schema (sample type "
    "authoring and controlled vocabulary), report (GEO / SRA / PRIDE submission "
    "artifacts), assay (house-scoped assay hygiene - 8 commands that find "
    "unregistered sample-assay pairs, put every proposal in front of a human, and "
    "write the approved ones to production). Activate when working in a directory "
    "containing files/, manuscript/, previous_metadata/, assets/assay-run.json, or "
    "any .dmac-curation.json lockfile, or when the user mentions NExtSEEK, "
    "FairDomHub, curation, sample types, assay hygiene, assay registration, or a "
    "GEO/SRA/PRIDE submission."
)
```

and widen the mode-coverage assertion at `tests/test_identity_sync.py:99-101`:

```python
def test_description_names_every_mode():
    for mode in ("pipeline", "fdh", "schema", "report", "assay"):
        assert mode in CANONICAL_DESCRIPTION, f"{mode} missing from description"
```

---

## F2 — STALE — "it is one mode among four"

**Where:** `SKILL.md:42-43`, the `### pipeline` subsection.

**Claim:**

> "12 phases driven by 14 commands. This is where most work happens, but it is
> one mode among four. Deep per-phase reference: `PHASES.md`."

**Reality:** five. The mode table two dozen lines above it (`SKILL.md:28-34`)
lists five rows, and I confirmed the 26-command set matches `commands/` exactly.
("12 phases driven by 14 commands" is *correct* and agrees with `PHASES.md:9`;
only the mode count is wrong.)

**Fix — replace `SKILL.md:42-43`:**

```markdown
12 phases driven by 14 commands. This is where most work happens, but it is one
mode among five. Deep per-phase reference: `PHASES.md`.
```

---

## F3 — WRONG — `/curate-assay-vocabulary` is filed under `schema` mode, contradicting SKILL.md's own mode table

**Where:** `SKILL.md:145`, "Vocabulary the user uses".

**Claim:**

> `- "unresolved terms" / "which assay does this metadata value mean" / "the assay vocabulary" → `schema` mode (`/curate-assay-vocabulary`), the assay-hygiene stage B2 judgment step`

**Reality:** it is an `assay`-mode command, and three other sources say so —
including SKILL.md itself:

- `SKILL.md:34` lists `/curate-assay-vocabulary` in the **`assay`** row.
- `commands/curate-assay-vocabulary.md:5` — "This is **stage B2 of the
  assay-hygiene mode**. It is house-scoped: one extract, all projects, no PI.
  Run `curate-assay-init` first — this command needs an open run".
- `ASSAY.md:35` lists it in the assay command table.
- Commit `64f233d`, "fix(assay-hygiene): absorb curate-assay-vocabulary into
  the mode".

**Why it matters:** this is not cosmetic. `schema` mode is cwd-scoped and needs
no project; the command actually **refuses to run without an open assay-hygiene
run**. A reader routed to "schema mode" will invoke it with no `RUN` set and no
lockfile and get a failure with no obvious cause. It is also the only line in
SKILL.md that flatly contradicts SKILL.md's own mode table.

Secondary gap in the same section: `assay` has **no** vocabulary entries beyond
this mis-filed one, so none of the phrases an operator actually uses route
anywhere.

**Fix — replace `SKILL.md:145` with two lines:**

```markdown
- "unresolved terms" / "which assay does this metadata value mean" / "the assay vocabulary" → `assay` mode (`/curate-assay-vocabulary`), stage B2 — needs an open run
- "assay hygiene" / "register these samples against an assay" / "which run is open" / "rule the cohorts" → `assay` mode (`/curate-assay-status` to orient, `/curate-assay-init` to open a run)
```

---

## F4 — WRONG — hard rule 6's invocation form does not work for any `assay_hygiene` module

**Where:** `SKILL.md:73`, Hard rules (never violate).

**Claim:**

> "6. **Use `uv`, not bare `python3`.** All scripts have PEP 723 inline-deps.
> Invoke via `uv run --script <plugin>/scripts/X.py`."

**Reality — reproduced, not inferred.** `scripts/assay_hygiene/` is a Python
**package**, not a set of standalone scripts. Its modules carry PEP 723 headers
(`scripts/assay_hygiene/run_detect.py:1-4`) but import each other relatively
(`run_detect.py:64-70`: `from . import _schema as S`, `from . import audit as A`,
…). Running the documented form in this worktree:

```
$ uv run --script scripts/assay_hygiene/run_detect.py --help
Installed 5 packages in 29ms
Traceback (most recent call last):
  File ".../scripts/assay_hygiene/run_detect.py", line 64, in <module>
    from . import _schema as S
ImportError: attempted relative import with no known parent package
```

All eight `/curate-assay-*` commands use a different form, e.g.
`commands/curate-assay-init.md:12` and `commands/curate-assay-status.md:7`:

```bash
PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "..."
```

So a "never violate" hard rule prescribes the one invocation that fails for
8 of the 26 commands, and the rule's supporting claim ("All scripts have PEP 723
inline-deps", true) actively encourages the wrong conclusion.

**Fix — replace `SKILL.md:73`:**

```markdown
6. **Use `uv`, not bare `python3`.** Two invocation forms, and they are not interchangeable. Standalone scripts under `scripts/` carry PEP 723 inline-deps — run them as `uv run --script <plugin>/scripts/X.py`. `scripts/assay_hygiene/` is a **package**, not a script directory: its modules import each other relatively, so `uv run --script` on one fails with `ImportError: attempted relative import with no known parent package`. Drive it as `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c "from assay_hygiene.<mod> import <fn>; ..."`, exactly as every `/curate-assay-*` command does.
```

---

## F5 — STALE — "`/curate-status` reports per mode" (it reports on four of five)

**Where:** `SKILL.md:38`.

**Claim:** "`/curate-status` reports per mode."

**Reality:** `scripts/status.py:182-188` builds the modes dict with exactly four
keys — `pipeline`, `fdh`, `schema`, `report`. No `assay` key. The module
docstring at `scripts/status.py:8` still says "the four modes each report on
their own terms". The `assay` mode has its own reporter,
`/curate-assay-status`, which reads `assets/assay-run.json` directly.
(`commands/curate-status.md:5` carries the same stale "all four dmac-curation
modes" phrasing — that file is outside this audit's scope but should move in
the same commit.)

**Fix — replace `SKILL.md:38`:**

```markdown
`/curate-status` reports on the `pipeline`, `fdh`, `schema` and `report` modes.
`assay` is house-scoped and has its own reporter, `/curate-assay-status`.
```

---

## F6 — WRONG — "all four sources" against a five-item list, stated twice

**Where:** `SKILL.md:75` (Hard rule 8) and `SKILL.md:112` (Published-paper
harvest, "Then:").

**Claim:**

- `:75` — "…and if it is genuinely absent from **all four** sources, leave the
  cell **blank**…"
- `:112` — "- **Genuinely absent from all four** → leave the cell **blank**…"

**Reality:** `SKILL.md:85-86` says "harvest these **five** sources in order and
stop at the first real hit", and the numbered list at `:88-107` has five
entries: Methods, Supplementary Methods, Data Availability, **the named deposit
itself**, and the master NExtSEEK sheet. Source 4 was added later and is the
one the doc most emphasises — `:101-104` calls the deposit manifest "**ground
truth for the data tier**". A curator counting to four has an off-by-one
against a rule labelled "never violate", on the exact step that determines
whether a cell gets a real value, a blank, or a forbidden placeholder.

Same defect propagated to `PHASES.md:244`, `PHASES.md:257` and `REPORTS.md:100`
("Only when all four come up empty") — outside this audit's target files, worth
fixing in the same pass.

**Fix — `SKILL.md:75`, change the one phrase:**

```markdown
8. **Harvest before you placeholder; for published work, flag don't placeholder.** For an **in-prep** study, use `*** PLACEHOLDER: <description> ***` for unknown values (greppable; blanks vanish). For a **published or submitted** study the metadata almost always exists — run the [Published-paper harvest](#published-paper-harvest) before writing any value, and if it is genuinely absent from all five sources, leave the cell **blank** and log the gap in `QUESTIONS_FOR_PI.md`. Never a placeholder in that case.
```

**Fix — `SKILL.md:112-114`:**

```markdown
- **Genuinely absent from all five** → leave the cell **blank** and add a
  name-pattern-anchored question to `QUESTIONS_FOR_PI.md`. Do **not** write a
  `*** PLACEHOLDER ***`. QA surfaces the blank; the PI fills it.
```

---

## F7 — MISSING — no `### assay` subsection, and nothing in SKILL.md says one command writes to production

**Where:** `SKILL.md:40-64`. `pipeline` (`:40`), `fdh` (`:45`), `schema` (`:54`)
and `report` (`:60`) each get a prose subsection under `## Modes`. `assay` gets
a table row and nothing else — the `## Hard rules` heading follows at `:66`.

**Reality:** the mode this omits is the only one that writes to production.
`commands/curate-assay-write.md:6-8`: *"The user wants this run's registrations
written to production. **This is the only command that touches production.** It
writes nothing without `--confirm`."* SKILL.md — whose stated job includes
"Hard rules (never violate)" and "Pitfalls to pre-warn about" — never mentions
this anywhere. Nor does it mention the two irreversibility properties `ASSAY.md`
leads with: `ASSAY.md:59-63`, "Nothing regenerates a human ruling. The store is
gitignored and its only protection is a tarball on one machine… A lost machine
is a lost campaign"; and `ASSAY.md:70-72`, "SEEK assay ids are per-project. A
registration landing on another project's assay puts the sample into a project
it does not belong to, and **nothing undoes that**."

This is not "the doc is allowed to summarise". SKILL.md is always loaded;
`ASSAY.md` is loaded *only* once a reader already knows to enter assay mode
(`SKILL.md:36-37`, "Load a mode's reference doc when you enter that mode, not
before"). A destructive, unrecoverable capability that is invisible until you
have already entered the mode is a gap in the always-loaded layer.

**Fix — insert after `SKILL.md:64` (end of the `### report` subsection):**

```markdown
### `assay` - assay hygiene

House-scoped, not project-scoped: one extract, all projects, no PI. Finds
samples that should be registered against an internal assay and are not, puts
every proposal in front of a human, and writes the approved ones to production.
Runs are numbered and immutable at `assets/RUN<n>/`; the run lockfile is
`assets/assay-run.json` and exactly one run may be open at a time, because two
concurrent write phases can silently overwrite each other's rows. Judgement
lives in the ruling store at `assets/rulings/`, outside any run.

Three things this mode can do that no other mode can:

- **`/curate-assay-write` is the only command in the plugin that touches
  production.** It writes nothing without `--confirm` and sits behind eight
  preflight refusals. Capture the `MAX(id)` rollback handle first.
- **Nothing regenerates a human ruling.** The store is gitignored and its only
  protection is a tarball on one machine; `git clean -xdf` would list `assets/`
  for removal. Run `/curate-assay-backup` after any session that ruled a lot.
- **SEEK assay ids are per-project.** A registration landing on another
  project's assay puts the sample into a project it does not belong to, and
  nothing undoes that.

Reference: `ASSAY.md`.
```

---

## F8 — STALE — `pyproject.toml` says 0.3.0 while both manifests say 0.4.0, and 0.4.0 predates the whole `assay` mode

**Where:** `.claude-plugin/plugin.json:3` and `.claude-plugin/marketplace.json:15`
both `"version": "0.4.0"`; `pyproject.toml:3` `version = "0.3.0"`.

**Reality, two parts.**

1. **Unambiguous mismatch.** `scripts/_lockfile.py:29` `PLUGIN_VERSION = "0.4.0"`
   and `tests/test_identity_sync.py:93-97` asserts plugin.json ==
   marketplace.json == `_lockfile.PLUGIN_VERSION`. **`pyproject.toml` is not
   covered by any test** — `tests/test_dependency_pinning.py:13-22` reads the
   file but only checks dependency pins, never `version`. So three artefacts
   agree at 0.4.0 and a fourth silently disagrees at 0.3.0.
2. **0.4.0 is stale on its face.** `CHANGELOG.md:5` dates 0.4.0 to 2026-07-31
   and describes `/curate-qc`, `sampletype_attr.py` and `Arm{X}_review.xlsx`.
   `grep -c 'assay-hygiene\|curate-assay' CHANGELOG.md` returns **0**. A whole
   fifth mode — 8 commands, ~38 modules under `scripts/assay_hygiene/`, and the
   plugin's only production writer — landed after that release
   (`d1f4d14`, `eb8777e`, `833e9be`) with no version bump. Anyone reading the
   manifest sees a version whose changelog entry cannot account for a third of
   the command surface.

**Fix.** Bump to `0.5.0` in **all four** places, in one commit:

- `.claude-plugin/plugin.json:3` → `"version": "0.5.0",`
- `.claude-plugin/marketplace.json:15` → `"version": "0.5.0",`
- `scripts/_lockfile.py:29` → `PLUGIN_VERSION = "0.5.0"`
- `pyproject.toml:3` → `version = "0.5.0"`

and update the pin at `tests/test_identity_sync.py:96-97`:

```python
def test_version_is_the_toolkit_release():
    assert _plugin_json()["version"] == "0.5.0"
```

Also add `tests/test_dependency_pinning.py` coverage so the fourth copy stops
drifting silently:

```python
def test_pyproject_version_matches_plugin_json():
    import json
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert data["project"]["version"] == manifest["version"]
```

(The matching `## 0.5.0` CHANGELOG entry is the repo-furniture audit's business,
not this one's, but the bump and the entry belong in the same commit.)

---

## Checked and found ACCURATE — not findings

Recorded so a later reader does not re-derive them.

| checked | result |
|---|---|
| Mode table command set (`SKILL.md:28-34`) vs `ls commands/*.md` | **exact match**, 26 = 26, diffed both directions, no extras, no omissions |
| Mode → reference doc mapping, all five | every doc exists in `skills/curation/`; `tests/test_mode_table.py:13-19` already names `assay: ASSAY.md` |
| `assay` state scope "run lockfile at assets/" | correct — `runstate.py:22,32`, `ASSAY.md:11` |
| "12 phases driven by 14 commands" (`SKILL.md:42`, and in the description) | agrees with `PHASES.md:9`; 11 numbered phases + 9b = 12, and 11 table commands + qc + init + status = 14 |
| Every path named in SKILL.md | all present: `context/sampletypes_db.json`, `context/fdh_api_index.json`, `scripts/fdh/submit.py`, `scripts/fdh/fdh_api.py`, `scripts/sampletype_attr.py`, `scripts/build_retrieve.py`, `scripts/smb_pull.py` |
| Hard rule 7 UID format `<TYPE>-YYMMDD<LAB>-N` | matches `commands/curate-build.md:59` and the design docs |
| Hard rules 1, 2, 3, 5 | no contradicting source found |
| Hard rule 4 ("schema lies; workbook tells truth") vs the pitfall at `:165` ("the live server is a third authority, and it outranks both") | **deliberate and reconciled** — the pitfall names rule 4 explicitly and qualifies it. Not drift. |
| The three descriptions byte-identical to each other | yes, verified programmatically, 613 chars, YAML-safe |

---

## Suggested application order

1. F1 + F8 together (they touch the same four/five files and the same test module).
2. F2, F3, F5, F6 — one-line edits inside SKILL.md.
3. F4 — hard rule 6 rewrite.
4. F7 — insert the `### assay` subsection.
5. Run `uv run pytest tests/test_identity_sync.py tests/test_mode_table.py tests/test_lockfile.py tests/test_dependency_pinning.py`.
