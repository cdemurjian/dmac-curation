# Drift audit — `skills/curation/SCHEMA.md` and `skills/curation/REPORTS.md`

Audit root: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs` (branch `dev-docs`).
Targets: `skills/curation/SCHEMA.md` (230 lines), `skills/curation/REPORTS.md` (174 lines).
Every finding below was verified by opening the named source file and reading the
contradicting lines. Line numbers are worktree state at audit time.

**Verdict: SUBSTANTIAL_DRIFT.** Eight findings — four per doc. The two headline
defects are that SCHEMA.md flatly denies the existence of the mode's live
production-write path, and that REPORTS.md's PRIDE row omits the one section
whose absence makes every rendered `submission.px` fail stage-2 validation.

---

## Answer to the directed question: `/curate-assay-vocabulary`

**SCHEMA.md never claims it. No finding against this file.**

`grep -n -i 'vocabulary' skills/curation/SCHEMA.md` returns 8 hits
(`:13, :39, :76, :86, :87, :213, :226, :227`) and **not one of them names
`/curate-assay-vocabulary`**. SCHEMA.md's "controlled vocabulary" is entirely
about `<TYPE>.ontology.json` / `write_4sheet_xlsx(ontology=)` / BioPortal — a
different concern from the assay-hygiene stage-B2 mapping of unresolved metadata
terms onto internal assays. SCHEMA.md names no `/curate-*` command at all.

The misrouting the git history implies is real but lives elsewhere:

- `skills/curation/SKILL.md:145` — "…'the assay vocabulary' → `schema` mode
  (`/curate-assay-vocabulary`), the assay-hygiene stage B2 judgment step".
- Contradicted three lines' worth of the same file away by `SKILL.md:34`, which
  lists `/curate-assay-vocabulary` under the `assay` mode row.
- `commands/curate-assay-vocabulary.md:5` calls itself "stage B2 of the
  **assay-hygiene mode**"; `skills/curation/ASSAY.md:35` lists it under assay.

That belongs to whoever audits SKILL.md (it is `C5` in
`inventory-skills-refs.md`). Flagged here only so it is not lost.

---

## SCHEMA.md

### S1 — `## Non-goals` denies a live production-write path that exists (WRONG)

**Location:** `skills/curation/SCHEMA.md:218` (bullet 1 of `## Non-goals`,
`:216-222`), with a companion edit at `:16-19` (`## State scope`).

**Claim:**

> - Writing to NExtSEEK, or editing `sampletypes_db.json` in place.

and

> **cwd.** Reads the plugin's `context/` read-only; writes everything into the
> current working directory under `schema/`. No lockfile, no scaffold, no project.

**Reality.** Schema mode has a live-write path and it targets **production by
default**:

- `commands/curate-sampletype.md:11` — "**Load `skills/curation/SCHEMA.md`
  before starting.**" SCHEMA.md is what an operator reads first.
- `commands/curate-sampletype.md:28-31` — "The one exception is the explicit
  `apply` verb below… **This is a GLOBAL, SHARED-SCHEMA WRITE.**"
- `commands/curate-sampletype.md:33-84` — the full `/curate-sampletype apply
  <TYPE> --add <FIELD>` procedure driving `scripts/sampletype_attr.py`.
- `scripts/sampletype_attr.py:62` — `DEFAULT_BASE_URL =
  os.environ.get("NEXTSEEK_BASE_URL", "https://nextseek.mit.edu")`.
- `scripts/sampletype_attr.py:242` — the write: `self.session.get(
  f"{self.base_url}{SAVE_PATH}", …)` with `SAVE_PATH = "/seek/attribute/save/"`
  (`:64`).
- `commands/curate-sampletype.md:152-165` — a verified-on-production record
  table dated 2026-07-31.

A reader who loads only SCHEMA.md is told the opposite of the truth about the
one command in this mode that can damage a shared schema for every project in
NExtSEEK.

**Proposed fix.** Two edits.

Replace `skills/curation/SCHEMA.md:16-19`:

```markdown
## State scope

**cwd.** Reads the plugin's `context/` read-only; writes everything into the
current working directory under `schema/`. No lockfile, no scaffold, no project.

The single exception is `/curate-sampletype apply`, which writes to a **live
NExtSEEK server** and defaults to production. See
[Applying: the one live-write path](#applying-the-one-live-write-path).
```

Replace `skills/curation/SCHEMA.md:216-222`:

```markdown
## Non-goals

- Writing to NExtSEEK *from the proposal path*, or editing `sampletypes_db.json`
  in place. The one exception is the explicit `apply` verb — see
  [Applying: the one live-write path](#applying-the-one-live-write-path).
- Emitting CEDAR templates (see tree vs graph).
- Migrating the 101 existing sample types.
- Renaming or splitting field names shared across types.
- A shared, accumulating field dictionary (deliberately deferred).
```

---

### S2 — `## Open question` treats "what apply means" as unsettled; it is settled and shipped (STALE)

**Location:** `skills/curation/SCHEMA.md:224-230`.

**Claim:**

> **What "apply" concretely means.** Application is manual and the mode only
> produces artifacts. Not settled: whether a human applying a proposed sample type
> record means editing NExtSEEK's admin UI, running a SQL update, or opening a PR
> against a schema repo. Confirm with the NExtSEEK admin before telling a curator
> to edit anything. Until then, `<TYPE>.review.md` says exactly that.

**Reality.** For the case that actually occurs — adding an attribute to an
existing type, the `/curate-qc` handoff — this was answered, tooled and verified
end to end on production:

- `scripts/sampletype_attr.py:6-25` — the answer is "drive NExtSEEK's own native
  editor": `GET /seek/attribute/save/` → Django ORM → `sample_attributes`,
  because `PATCH /nextseek_api/sample_types/{id}/` proxies to SEEK and SEEK's
  `allow_new_attribute?` returns false for any type that has samples.
- `commands/curate-sampletype.md:152-165` — "**Verified end to end
  (2026-07-31)**": `Notes` added to `A.TITR` on dev (id 35) then production
  (id 99), 10 → 11 attributes, existing samples reconciled.
- The guards are real and specific, not hypothetical: `_validate`
  (`scripts/sampletype_attr.py:180-206`), dry-run-by-default (`--apply`
  required; `:374, :411, :446`), and `_confirm_production`
  (`:290-317`) refusing `--apply` against `PRODUCTION_HOSTS = ("nextseek.mit.edu",)`
  (`:63`) without `--yes-production`.

The genuinely open part is narrower: applying a *whole proposed sample type
record*, and the fact that `sampletype_attr.py` is a declared stopgap.

**Proposed fix.** Replace `skills/curation/SCHEMA.md:224-230` with a new section
plus a narrowed open question:

````markdown
## Applying: the one live-write path

Everything above produces artifacts a human applies by hand. `/curate-sampletype
apply <TYPE> --add <FIELD>` is the one exception: it adds an attribute to a live
sample type through `scripts/sampletype_attr.py`, normally as the handoff from
`/curate-qc` after the server rejected a field that genuinely ought to exist.
`commands/curate-sampletype.md` is the authority; this is what a reader of
SCHEMA.md needs to know before they get there.

**Why a bespoke tool.** `PATCH /nextseek_api/sample_types/{id}/` is a 1:1
pass-through to SEEK, and SEEK's `allow_new_attribute?` refuses any sample type
that already has samples — nearly all of them — surfacing through NExtSEEK's
proxy as a generic `502 "Invalid upstream response"`. `sampletype_attr.py`
instead drives NExtSEEK's own native editor (`GET /seek/attribute/save/` → Django
ORM → `sample_attributes`) and calls `updateSampleType` to reconcile existing
samples' `json_metadata`.

**This is a GLOBAL, SHARED-SCHEMA WRITE.** Sample types are not project-scoped:
adding `Notes` to `A.TITR` changes that type for every project and every existing
`A.TITR` record across NExtSEEK.

**The guards, exactly.** The ORM path bypasses Rails, and therefore bypasses every
SEEK model validation. Four things stand in:

1. `sampletype_attr.py::_validate` (`scripts/sampletype_attr.py:180-206`)
   re-implements the three validations that matter —
   `validate_attribute_title_unique`, `validate_attribute_accessor_names_unique`,
   `validate_one_title_attribute_present`. These are the ONLY protection on this
   path; the `/seek/samples/attributes/` web page offers none of them.
2. **Dry run is the default.** `add`, `remove` and `selftest` print the exact
   record and send nothing unless `--apply` is passed.
3. **Production needs a second flag.** `_confirm_production`
   (`scripts/sampletype_attr.py:290-317`) refuses `--apply` against
   `nextseek.mit.edu` (`PRODUCTION_HOSTS`, `:63`) unless `--yes-production` is
   given too. `--yes-production` is stripped from `argv` before parsing, so it may
   appear anywhere on the command line.
4. **Rehearse on dev.** `--base-url https://nextseek-dev.mit.edu` (or
   `NEXTSEEK_BASE_URL`) targets dev, where the same types exist in the same shape.
   `DEFAULT_BASE_URL` is production (`:62`).

```bash
uv run --script <PLUGIN>/scripts/sampletype_attr.py list <TYPE>
uv run --script <PLUGIN>/scripts/sampletype_attr.py add <TYPE> --title <FIELD> --type Text
uv run --script <PLUGIN>/scripts/sampletype_attr.py --base-url https://nextseek-dev.mit.edu \
    add <TYPE> --title <FIELD> --type Text --apply
uv run --script <PLUGIN>/scripts/sampletype_attr.py \
    add <TYPE> --title <FIELD> --type Text --apply --yes-production
```

**Two things that will bite.** A change is invisible to `/curate-qc` and to batch
upload until the NExtSEEK app workers restart —
`prefetch_sample_type_attributes` caches sample_type_id → attribute titles in a
module-level dict with no TTL and no invalidation on write, so the web page shows
your attribute while validation still denies it. And the ORM path skips the Rails
callbacks that trigger Solr reindexing, so a new attribute may not be searchable
in SEEK until a reindex (unverified).

**When NOT to apply.** If the server rejected a field because *we* got it wrong —
invented it, mis-cased it, or copied a typo out of `sampletypes_db.json` — fix the
build script instead. Patching a shared schema to accommodate our own error
pollutes a shared vocabulary.

## Open question

**What "apply" means beyond adding an attribute.** Adding an attribute to an
existing type is settled, tooled and verified end to end (`Notes` on `A.TITR`,
dev then production, 2026-07-31). Still unsettled: how a human applies a *whole
proposed sample type record* — NExtSEEK's admin UI, a SQL update, or a PR against
a schema repo. Confirm with the NExtSEEK admin before telling a curator to create
a type; `<TYPE>.review.md` says exactly that. `sampletype_attr.py` is itself a
declared stopgap — superuser-only, a GET with JSON in query params — expected to
be superseded by a proper `nextseek_api` REST write endpoint wrapping
`DBtable_sampleattribute` + `DBtable_sample.updateSampleType`.
````

---

### S3 — the headline statistic is off by one: 856 vs 857 (WRONG)

**Location:** `skills/curation/SCHEMA.md:11-14` (`## Purpose`).

**Claim:**

> The problem it attacks: of **1059 distinct field names across 101 sample types,
> 856 are used by exactly one type**…

**Reality: 857.** Computed directly from the shipped catalog using the module's
own function:

```
$ python3 -c "import sys; sys.path.insert(0,'scripts');
from schema import field_index as fi
cat=fi.load_catalog(); idx=fi.build_field_index(cat)
print(len(cat), len(idx), sum(1 for u in idx.values() if u.count==1))"
101 1059 857
```

Two other sources agree with 857 and disagree with SCHEMA.md:

- `scripts/schema/field_index.py:7-8` — "of 1059 distinct field names across 101
  sample types, 857 are used by exactly one type".
- `docs/superpowers/specs/2026-07-21-schema-mode-design.md:17` — "857 (81%)".

**Proposed fix.** In `skills/curation/SCHEMA.md:11-12`, change `856` to `857`:

```markdown
The problem it attacks: of **1059 distinct field names across 101 sample types,
857 are used by exactly one type**, and none of the 1059 carries a description,
```

---

### S4 — the `## Modules` table omits `templates.py`, the mode's only field-naming source (MISSING)

**Location:** `skills/curation/SCHEMA.md:52-58`.

**Reality.** `scripts/schema/` holds six real modules; the table lists five.
The missing one is `scripts/schema/templates.py` (139 lines) — and it is not a
minor helper:

- SCHEMA.md devotes forty lines to it (`## The reference template checklist`,
  `:138-178`) and calls it "the **only** source in the mode that names fields
  rather than values" (`:143`).
- It is the only consumer of `CEDAR_API_KEY` (`scripts/schema/templates.py:38`).
- It is the only module in the mode reaching `resource.metadatacenter.org`
  (`:39`).

A contributor scanning the table for the mode's surface would miss it entirely.

Two smaller inaccuracies in the same table:

- The `review.py` row names only `<TYPE>.review.md`. `review.py:245-250` also
  defines `write_proposed_record` → `<cwd>/schema/<TYPE>.proposed.json`, which
  `commands/curate-sampletype.md:234` lists as one of the mode's three artifacts.
  `<TYPE>.proposed.json` is never named anywhere in SCHEMA.md.
- Nothing tells the reader these are **not** CLIs.
  `grep -rn 'if __name__\|argparse\|def main' scripts/schema/` returns nothing,
  yet SKILL.md hard rule 6 says "All scripts have PEP 723 inline-deps. Invoke via
  `uv run --script <plugin>/scripts/X.py`". `uv run --script
  scripts/schema/field_index.py` exits 0 having done nothing.

**Proposed fix.** Replace `skills/curation/SCHEMA.md:52-58`:

```markdown
| module | responsibility |
|---|---|
| `scripts/schema/field_index.py` | catalog loading, field usage index, the reuse check, Tags mining |
| `scripts/schema/dictionary.py` | observed-value mining, the lazy cwd-only field dictionary |
| `scripts/schema/ontology.py` | controlled-value proposals with sources, the `<TYPE>.ontology.json` artifact |
| `scripts/schema/terms.py` | BioPortal lookup; suggests, never binds; degrades with no key |
| `scripts/schema/templates.py` | CEDAR reference-template checklist — the only source that names *fields*; the only consumer of `CEDAR_API_KEY`; degrades to an empty section without one |
| `scripts/schema/review.py` | renders `<TYPE>.review.md` (the deliverable) and `<TYPE>.proposed.json` (a catalog-shaped record, for diffing) |

**None of these is a CLI.** There is no `main()`, no `argparse` and no
`if __name__` anywhere in `scripts/schema/`, so SKILL.md hard rule 6
(`uv run --script …`) does not apply here. The contract is
`sys.path.insert(0, "<PLUGIN>/scripts")` then `from schema import field_index`.
```

---

### S5 — the pinned-template field counts contradict the code and cannot both be right (UNCLEAR)

**Location:** `skills/curation/SCHEMA.md:152-154`.

**Claim:**

> `common assay template` carries 28 fields, 27 described and 22 BAO-bound, while
> the Pistoia Alliance template carries 7 with no descriptions and no bindings.

**Reality.** `scripts/schema/templates.py:17-18` says something different for the
same template: "`common assay template` carries 25 fields, 24 of them described
and 20 bound to a BioAssay Ontology branch."
`commands/curate-sampletype.md:187-188` sides with SCHEMA.md ("returns 28 fields,
27 described and 22 bound"). Which is correct is **not determinable offline**:
`REFERENCE_TEMPLATES` (`templates.py:52-55`) pins one third-party
`bibo:draft` v0.0.1 template fetched live from `resource.metadatacenter.org`, and
the module's own docstring (`:49-51`) says it is deliberately never vendored
precisely so it can change upstream. Quoting a count in three places guarantees at
least two of them are wrong at any moment.

Refuted while checking: SCHEMA.md's plural "templates are pinned by `@id`"
(`:151`) is *not* a defect — the sentence names Pistoia explicitly as the example
of one **not** worth pinning, which is consistent with `REFERENCE_TEMPLATES`
holding exactly one entry.

**Proposed fix.** Replace `skills/curation/SCHEMA.md:149-154`:

```markdown
**A checklist, not a lookup.** The shared library cannot be selected by assay
name - `viability`, `flow cytometry`, `sequencing` and `metabolomics` all return
zero hits - so templates are pinned by `@id` and diffed against the type.
Quality varies enormously and only well-specified templates are worth pinning:
`REFERENCE_TEMPLATES` (`scripts/schema/templates.py:52-55`) holds exactly one,
`common assay template`, while the Pistoia Alliance template carries 7 fields
with no descriptions and no bindings and is deliberately left out. **Field counts
are not quoted here on purpose:** the pinned template is a third-party
`bibo:draft` at v0.0.1, fetched live and never vendored, so any number goes stale
without warning. Run `template_fields(REFERENCE_TEMPLATES["common assay
template"])` and report what actually comes back.
```

---

## REPORTS.md

### R1 — the PRIDE row omits `project_metadata`; a mapping written from this table renders a HARD_REJECT artifact (WRONG)

**Location:** `skills/curation/REPORTS.md:25` (PRIDE row of the `## Formats`
table, `:21-25`).

**Claim:**

> | PRIDE | `sample_metadata` + `file_mapping` | `sample_metadata` | `D.MSP` | `submission.px` |

**Reality.** `pride.json` declares **three** sections, not two —
`['project_metadata', 'file_mapping', 'sample_metadata']` (read from
`context/report_templates/pride.json`, `schema.sections`). The omitted one is
load-bearing:

- `scripts/report/render.py:161-163` — `render_pride` writes one `MTD` line per
  key of `filled.get("project_metadata")`. No section → no `MTD` lines.
- `scripts/report/validate_artifact.py:308-309` — `validate_pride_px` sets
  `status = ArtifactStatus.SchemaInvalid` when `not seen.get("MTD")`.
- `scripts/report/validate_artifact.py:44-50` — `SchemaInvalid` → `HARD_REJECT`.

REPORTS.md's Formats table is the only place in the repo that enumerates PRIDE's
sections: `commands/curate-report.md` never names any of them
(`grep -n 'project_metadata\|sample_metadata\|file_mapping'` returns nothing).
So a curator following the documentation writes a two-section PRIDE mapping,
renders a `.px` with no `MTD` lines, and gets HARD_REJECT at stage 2 with no
explanation of what they left out.

**Proposed fix.** Replace `skills/curation/REPORTS.md:21-25` and append a note:

```markdown
| format | sections to map | row section | target type | artifact |
|---|---|---|---|---|
| GEO | `samples` (the spec also declares `study`, `protocols`, `paired_end_experiments`, `checksums`) | `samples` | `D.SEQ` | `GEO_filled.xlsx` |
| SRA | `libraries`, `biosamples` | `libraries` | `D.SEQ` | `SRA_metadata_filled.xlsx` + `SRA_biosample_filled.xlsx` |
| PRIDE | `project_metadata`, `file_mapping`, `sample_metadata` | `sample_metadata` | `D.MSP` | `submission.px` |

**`project_metadata` is not optional for PRIDE.** `render_pride` writes one `MTD`
line per `project_metadata` key (`scripts/report/render.py:161-163`), and
`validate_pride_px` returns `SchemaInvalid` — HARD_REJECT — for a `.px` carrying
no `MTD` lines (`scripts/report/validate_artifact.py:308-309`). A PRIDE mapping
that omits the section renders a file that fails stage 2 every time.
```

---

### R2 — synthesized GEO study prose never reaches `GEO_filled.xlsx` (WRONG)

**Location:** `skills/curation/REPORTS.md:49-51` (`## The mapping spec`);
the same assumption drives `## Open question` at `:168-174`.

**Claim:**

> Directives: `source`, `via_lineage`, `const`, `map`, `synthesize`, `unmapped`.
> `synthesize` is study-level only, so it stays O(1).

and, at `:170-172`:

> **Does `synthesize` need manuscript access?** Study title, summary and
> experimental design are prose that likely live in `manuscript/`.

**Reality.** For GEO — the only format for which `synthesize` is documented and
exemplified — the synthesized text is written to `report/GEO_filled.json` and
then **discarded at render time**:

- `scripts/report/render.py:42-64` — `render_geo` does not render. It writes
  `filled` to a temp JSON and shells out:
  `subprocess.run(["uv", "run", "--script", <plugin>/scripts/deposit/geo_build_xlsx.py,
  tmp_json, template_xlsx, out_path], timeout=300)`.
- `scripts/deposit/geo_build_xlsx.py:52-53` — the child reads exactly two keys:
  `samples = data["samples"]` and
  `paired = data.get("paired_end_experiments", [])`.
- `scripts/deposit/geo_build_xlsx.py:23` — "STUDY rows and the PROTOCOLS/PE block
  itself are **preserved verbatim** (just shifted)." Confirmed by
  `grep -n 'study\|STUDY' scripts/deposit/geo_build_xlsx.py`: every hit is about
  preserving or shifting template rows; none writes a value from the JSON.

`commands/curate-report.md:86-88` shows the documented mapping example carrying
exactly this:

```json
  "study": {
    "*title":              {"synthesize": "study title from manuscript context"},
    "*summary (abstract)": {"synthesize": "abstract"} }
```

A curator does the manuscript harvest, writes the prose, sees it in
`GEO_filled.json` and `GEO.completeness.md`, and ships a `GEO_filled.xlsx` whose
STUDY block still holds the blank template rows. SRA and PRIDE have no such gap —
`render_sra` (`render.py:130-143`) and `render_pride` (`:148-186`) write every
mapped section.

**Proposed fix.** Replace `skills/curation/REPORTS.md:49-50` (keep `:51-53` as
they are):

```markdown
Directives: `source`, `via_lineage`, `const`, `map`, `synthesize`, `unmapped`.
`synthesize` is study-level only, so it stays O(1).

**Caveat for GEO: synthesized study prose does not reach the xlsx.** `render_geo`
does not render — it writes `filled` to a temp JSON and shells out to
`scripts/deposit/geo_build_xlsx.py` (`scripts/report/render.py:55-62`, needs `uv`
on PATH, 300s timeout). That script reads only `data["samples"]` and
`data.get("paired_end_experiments", [])` and re-pastes the template's STUDY and
PROTOCOLS rows verbatim (`scripts/deposit/geo_build_xlsx.py:52-53, :23`). A
`study` block in a GEO mapping reaches `report/GEO_filled.json` and
`GEO.completeness.md` but **nothing transfers it into `GEO_filled.xlsx`** — the
curator still fills the STUDY block by hand before submitting, and should be told
so. SRA and PRIDE write every mapped section.
```

And replace `## Open question` (`skills/curation/REPORTS.md:170-174`) with:

```markdown
**Does `synthesize` need manuscript access?** Study title, summary and
experimental design are prose that likely live in `manuscript/`. In a curation
project that is available; input-scoped runs elsewhere may have nothing, in
which case these become placeholders. That degradation is implemented and
tested; whether it is acceptable in practice is a curator's call. Note the GEO
caveat above before spending effort here: for GEO the answer currently lands only
in `GEO_filled.json` and `GEO.completeness.md`, never in `GEO_filled.xlsx`.
```

---

### R3 — the UID / `RETRIEVE.TXT` adapter has no shipped HTTP client and returns zero samples in silence (WRONG)

**Location:** `skills/curation/REPORTS.md:62` (row 1 of the `## Input adapters`
table, `:60-65`).

**Claim:**

> | NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | `POST /nextseek_api/admin/samples/retrieve/` |

Presented as behaviour, in a column headed "behaviour", alongside three rows that
genuinely describe what the code does ("local read, no API call").

**Reality.** `scripts/report/adapters.py:62-84`:

```python
def adapt_uids(uids: list[str], *, fetch=None) -> NormalizedInput:
    """UIDs -> POST /nextseek_api/admin/samples/retrieve/.
    ...
    out = NormalizedInput(source={"adapter": "uids", "uids": list(uids)})
    if fetch is None:
        return out
```

The endpoint appears only in that docstring. The module imports no HTTP client;
`fetch` is an injected callable. **With `fetch=None` the adapter returns an empty
sample list and no error** (`:70-71`), and `adapt_retrieve_txt` delegates to it
(`:86-90`), as does the `adapt()` façade via `kwargs.get("fetch")` (`:211-212`).

Nothing in the repo supplies that callable outside tests:
`grep -rn 'fetch=' --include=*.py .` returns 12 hits — 9 in `tests/`, 3 in
`adapters.py` itself. `scripts/nextseek_api.py` has no `retrieve` at all
(`grep -n retrieve` → no output). The only other mentions of the endpoint are the
two doc lines (`commands/curate-report.md:51`, `REPORTS.md:62`).

Failure scenario: a curator runs `/curate-report GEO RETRIEVE.TXT`. The adapter
returns zero samples; `apply_mapping` produces zero rows; if the mapping omits
`row_scope.expected_rows` (see R4) nothing objects, and `GEO_filled.xlsx` is
emitted with an empty SAMPLES block.

**Proposed fix.** Replace `skills/curation/REPORTS.md:60-65`:

```markdown
| input | behaviour |
|---|---|
| NExtSEEK UIDs (args, or `RETRIEVE.TXT`) | needs an injected `fetch` callable — see below |
| NExtSEEK workbook (`*_AllMetadata*.xlsx`) | local read, no API call |
| curated upload sheet (`Arm{X}-upload.xlsx`) | local read; works **before** upload |
| arbitrary xlsx / csv | local read; columns mapped by the LLM step |

**The UID adapters ship no HTTP client.** `adapt_uids` / `adapt_retrieve_txt`
take a `fetch=` callable and unnest whatever it returns; the shape they expect is
the five-level `POST /nextseek_api/admin/samples/retrieve/` response
(`scripts/report/adapters.py:62-84`). **With `fetch=None` they return zero samples
silently** (`:70-71`) — not an error. Nothing in `scripts/` supplies that callable
today; only the tests do. So either wire the call yourself against
`scripts/nextseek_api.py`, or use one of the three local-read adapters. Prefer
the local ones — the curated sheet is the documented GEO input anyway, because GEO
deposit happens *before* NExtSEEK upload.
```

---

### R4 — `## Two-stage validation` overstates every one of its three guarantees (MISSING)

**Location:** `skills/curation/REPORTS.md:77-91`.

Three separate overstatements, all in one section, all verified:

**(a) SRA `libraries` validation has no teeth.**
`scripts/report/validate_artifact.py:83-91` records it as a verified known gap:

> KNOWN GAP, verified: SRA's `libraries` section marks NOTHING with `*` -
> `sample_name`, `library_ID`, `library_strategy` and the rest are all bare.
> So this returns [] for it, and `_validate_xlsx` then reports Valid for any
> readable workbook.

`validate_sra_xlsx` defaults to `section="libraries"` (`:259`), and with an empty
`required` list `_check_required` finds nothing missing, so `status =
ArtifactStatus.Valid` → `CLEAN` (`:227-232`, `:44-50`). REPORTS.md tells the
reader `Valid = CLEAN` and stops. A curator reasonably reads a CLEAN on
`SRA_metadata_filled.xlsx` as "complete".

**(b) CV checking covers nine fields, and none of PRIDE's.**
`scripts/report/mapping.py:44-60` is an explicit 8-entry allowlist
(`_CV_KEY_FOR_FIELD`), plus one special case in `cv_for_field`
(`:132-140`) for GEO's `*single or paired-end` using the in-code
`_GEO_LAYOUT_CV` (`:40`). Any other target field returns `None` — free text — even
if the template declares a vocabulary. GEO's `*instrument model` is deliberately
excluded (`:51-57`). And `context/report_templates/pride.json` declares **no
`controlled_vocabulary` key at all** (verified by reading the file: its top-level
keys are `description, file_mapping, format, notes, project_metadata,
report_type, sample_metadata, schema`), so `const`/`map` outputs are never
CV-checked for PRIDE.

**(c) Row parity is conditional, not structural.**
REPORTS.md:90 — "**Row parity is asserted** even though the executor controls row
count by construction." `scripts/report/execute.py:153-159`:

```python
expected = row_scope.get("expected_rows")
produced = len(filled.get(row_section, []))
if expected is not None and produced != expected:
    raise RowParityError(...)
```

Stage 1 has the same `expected is not None` gate
(`scripts/report/mapping.py:189-194`). Omit `row_scope.expected_rows` from the
mapping and **neither** check runs. Combined with R3 this is how an empty
artifact ships without complaint.

**Proposed fix.** Replace `skills/curation/REPORTS.md:77-91`:

```markdown
## Two-stage validation

**Stage 1, before applying:** every target field exists in the template; every
required (`*`) field is `source`/`const`/`synthesize` or explicitly `unmapped`
with a reason; every `source` column exists in the input; and a column that lives
only on ancestors carries `via_lineage`.

**CV checking is narrower than it sounds.** `const` and `map` outputs are checked
only for the nine fields `cv_for_field` recognises
(`scripts/report/mapping.py:44-60, :132-140`): eight SRA-keyed names plus GEO's
`*single or paired-end`, which uses a GEO-specific list held in code because the
vendored CV was mined from SRA and holds `paired`, not `paired-end`. GEO's
`*instrument model` is deliberately free text. **PRIDE has no controlled
vocabulary at all** — `pride.json` declares no `controlled_vocabulary` key — so
nothing in a PRIDE mapping is ever CV-checked.

**Stage 2, after rendering:** the vendored artifact validator. Its statuses map
onto the pipeline's vocabulary: `Valid` = CLEAN, `Incomplete` = SOFT_FLAG,
`SchemaInvalid` / `Missing` / `Unreadable` = HARD_REJECT.

**Known gap, verified: SRA `libraries` validation has no teeth.** `SRA.json`'s
`libraries` section stars nothing — `sample_name`, `library_ID`,
`library_strategy` and the rest are all bare — so `required_fields` returns `[]`
and any readable `SRA_metadata_filled.xlsx` reports `Valid` / CLEAN
(`scripts/report/validate_artifact.py:83-91`). `biosamples` does star its fields,
so SRA is not unguarded overall, but never read CLEAN on the metadata workbook as
evidence it is complete. Read `SRA.completeness.md` instead.

**Row parity is asserted only when the mapping declares it.** `RowParityError`
fires when `row_scope.expected_rows` is set and the produced row count differs
(`scripts/report/execute.py:153-159`); stage 1 checks the same number against the
input (`scripts/report/mapping.py:189-194`). Omit `expected_rows` and neither
check runs — which is how an adapter that silently returned zero samples ends up
as an empty artifact. **Always set it.** chat_nextseek's own assessment calls that
guard the single most valuable idea to carry over.
```

---

### R5 — the Published-paper harvest is five sources; REPORTS.md lists four and drops the most important one for this mode (WRONG)

**Location:** `skills/curation/REPORTS.md:96-101` (`## Graceful degradation`).

**Claim:**

> First run the Published-paper harvest (SKILL.md): the manuscript Methods,
> Supplemental Methods and Data Availability statement, plus the master NExtSEEK
> sheet (`previous_metadata/*.xlsx`), usually supply exactly these. Only when all
> four come up empty does the field degrade

**Reality.** `skills/curation/SKILL.md:84-101` defines the harvest as **five**
sources — "harvest these five sources in order and stop at the first real hit" —
and REPORTS.md omits source 4:

> 4. The **named deposit itself** — when a Data Availability statement gives an
>    accession, FETCH the deposit and enumerate its files… This manifest is
>    **ground truth for the data tier**: the number and identity of raw/processed
>    files fixes the D.* node counts, filenames, and checksums. Do NOT infer
>    data-tier structure from precedent when a deposit exists.

That is the single most valuable source for *this* mode. GEO, SRA and PRIDE
artifacts are, to a first approximation, a file manifest with checksums —
`GEO_template.xlsx` carries an MD5 Checksums sheet, `SRA.json` has a `filetype`
CV, `pride.json` has a whole `file_mapping` section. REPORTS.md sends a curator
straight past the one source that answers those columns and on to a placeholder.

(`commands/curate-report.md:114-118` carries the same four-source omission; that
file is another auditor's target, but the fix is the same edit.)

**Proposed fix.** Replace `skills/curation/REPORTS.md:95-101`:

```markdown
Some GEO fields are derivable only from context an input may lack - organism,
tissue and cell line frequently live on **ancestor** samples rather than the
`D.SEQ` row, and protocol prose needs a resolvable SOP id. First run the
Published-paper harvest (SKILL.md), all **five** sources in order: the manuscript
Methods, Supplemental Methods and Data Availability statement, then **the named
deposit itself**, then the master NExtSEEK sheet (`previous_metadata/*.xlsx`).
The deposit matters most here — for a report-mode run it is ground truth for the
data tier (file counts, filenames, checksums), which is precisely the tier GEO,
SRA and PRIDE ask about. Only when all five come up empty does the field degrade:
```

---

## Checked and refuted — deliberately not reported

Recorded so a later reader does not re-derive them.

| checked | verdict |
|---|---|
| SCHEMA.md `## Modules` claiming `templates.py` is pinned to multiple templates (`:151` "templates are pinned") | Not a defect. The sentence names Pistoia as an example of one *not* worth pinning, consistent with `REFERENCE_TEMPLATES` holding one entry. |
| SCHEMA.md `:98-100` quoting the API spec on ontology enforcement | Exact. `context/NExtSEEK_API.yaml:472` "Ontology validation is not performed in rows mode"; `:506` "Validation is strict; violations reject the file"; `:511` "Unknown extra columns are ignored, with a warning". |
| SCHEMA.md `:85-87` "No caller had ever passed it… `consolidate_to_flat.py` never read it" | Still true. `grep -rn 'ontology=' scripts/` finds no caller passing it to `write_4sheet_xlsx`; `grep -ni ontology scripts/consolidate_to_flat.py` returns one line (`:19`), a sheet-name presence check only. |
| SCHEMA.md `:75-83` `write_4sheet_xlsx(ontology={field: [values]})` | Exact. `scripts/_common.py:188-195`, parameter at `:193`, semantics at `:204-209`. |
| SCHEMA.md `:81-83` example row uses `MUS::Strain` where the API spec uses `M.Mice::Strain` | Illustrative; not worth an edit. |
| SCHEMA.md `:203-214` BioPortal "suggests, never binds" | Exact. `scripts/schema/terms.py:185-188` `to_binding` always emits `{"confirmed": False}`; `dictionary.py:87-89` force-overrides any caller value; `terms.py:98-100` returns `[]` with no network call absent `BIOPORTAL_API_KEY`. |
| SCHEMA.md `:180-187` "lazy and cwd-only" dictionary | Exact. `scripts/schema/dictionary.py:7-8, :16-18, :154-158`. |
| REPORTS.md `:15-17` "Reads a project lockfile when present… Output goes to `./report/`" | Fine. No lockfile read exists in `scripts/report/` — it is an agent-level instruction matching `commands/curate-report.md:24`. `execute.py:38` `OUTPUT_SUBDIR = "report"`. |
| REPORTS.md `:124-134` protocol-chain gotchas | All four exact against `scripts/report/protocols.py` — `resolve_host` `:75-90`, the literal `Protocol` key `:52`, `PdfSupportError` `:43, :104-120`, `truncate_tokens(limit=3000)` `:40, :123-128`. |
| REPORTS.md `:148-158` "Relationship to Phase 10" | True as a claim about the *command*. `commands/curate-deposit.md:13` delegates the build and keeps upload + backfill. (That `scripts/deposit/geo_build_xlsx.py` is the actual GEO writer is covered in R2, not here.) |
| REPORTS.md `:23-25` artifact column omits `<FORMAT>_filled.json` | Intermediate, not a deliverable; `commands/curate-report.md:133` lists it. Not misdirecting. |
| REPORTS.md `:138-146` module table omits `scrub_fixture.py` | Test-fixture utility, documented in `tests/fixtures/nextseek/README.md`. Not worth a row. |
| REPORTS.md `:103` cites "SKILL.md hard rule 8" | Correct — rule 8 is at `SKILL.md:75`. (`SCHEMA.md:47` "hard rule 4" is likewise correct.) |
| REPORTS.md `:44`, `:164` citing `reports/outputs.py:349-355` | External repo (chat_nextseek); unverifiable from here. Left alone. |
