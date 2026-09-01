---
description: Server-side validation of the upload sheets, and triage of any schema gaps (Phase 9b)
---

The user wants Phase 9b — validate the consolidated upload file against the LIVE
NExtSEEK server, before uploading anything.

## How this differs from `/curate-qa`

| | `/curate-qa` (9a) | `/curate-qc` (9b) |
|---|---|---|
| Runs | `qa_flat_sheets.py` | `nextseek_api.py validate` |
| Talks to the server | no | **yes** |
| Needs credentials | no | yes (`.env`) |
| Catches | row counts, dangling parents vs the local master, placeholders, missing required fields | **attribute names the server does not recognise**, CONVERT failures, server-side DAG orphans, name collisions with records already in the DB |

`/curate-qa` cannot know that `Notes` is undefined for `A.TITR` — only the server
knows that. **A clean `/curate-qa` is not evidence the upload will succeed.** Run
both; run this one last.

## Prereqs

- `assay_sheets/<name>.xlsx` exists (a consolidated flat file, from `/curate-consolidate`)
- `.env` holds `NEXTSEEK_USERNAME` + `NEXTSEEK_PASSWORD`
- a project id (lockfile `modes.pipeline.nextseek_project_id`, or ask)

## Steps

1. Run the validator, most thorough setting, dumping the full result:

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py validate \
     --project-id <N> --checks structure,dag,name_check \
     --dump-dir <scratch> assay_sheets/<name>.xlsx
   ```

2. If `valid: true` — report `processed/success/failed` and stop. Ready to upload.

3. If invalid, **classify the errors before proposing anything**. Parse the dump
   rather than eyeballing the truncated console list; the console shows only the
   first 20 of what can be hundreds.

   | Error type | Meaning | Fix |
   |---|---|---|
   | `VALIDATION_ATTRIBUTE_NAME` | field not defined for that sample type | either drop the field, or add it to the type — see below |
   | `CONVERT failed` | the file shape is wrong (e.g. missing the `assay_ids` column) | rebuild the flat file |
   | DAG / orphan | a parent does not resolve server-side | fix parentage, or upload the parent tier first |
   | name collision | a `Name` already exists in the DB | rename, or confirm it is an intentional update |

4. For `VALIDATION_ATTRIBUTE_NAME`, group by sample type and report a table of
   `type -> rejected fields`. Then determine, per field, which of two cases it is:

   - **Our error** — we invented the field, or got its case wrong
     (`Bead_coating_vendor` on D.TITR vs `Bead_coating_Vendor` on D.FCRB), or copied
     a typo out of `sampletypes_db.json` (`QuanitifcationMethod`). **Fix the build
     script.** Do not patch the schema to accommodate our mistake.
   - **A genuine schema gap** — the field is meaningful for that type and simply
     is not defined yet (`Notes` on the A.* tier). **Candidate for a schema patch.**

   Confirm which is which by probing the server (below), not by consulting
   `sampletypes_db.json` — the bundled DB disagrees with the live server in both
   directions.

5. **Discuss with the user before any schema change.** Present the gap list and say
   plainly that sample types are GLOBAL: adding an attribute changes the type for
   every project and every existing record of it across NExtSEEK, not just this
   curation. Get explicit per-type agreement. Never patch as a side effect of QC.

6. Hand off the agreed patches to `/curate-sampletype apply <TYPE> --add <FIELD>`,
   which drives the attributes API. That command owns the write; this one only
   diagnoses. Read the current state first:

   ```bash
   uv run --script <PLUGIN>/scripts/nextseek_api.py sampletype-get <TYPE>
   ```

   If the type already has samples, that is why the `sample_types` PATCH route
   cannot work (see below) — it is not why the write fails, because the attributes
   API is not subject to that constraint.

7. Re-run step 1 to confirm the fix took and nothing else broke.

## Probing what a type actually accepts

The authoritative source is the server, not the bundled catalog. Read one type
directly:

```bash
uv run --script <PLUGIN>/scripts/nextseek_api.py sampletype-get A.TITR   # read-only
uv run --script <PLUGIN>/scripts/nextseek_api.py attributes-list --sample-type A.TITR
```

To test many candidate fields at once, build a throwaway flat file with one row per
sample type carrying every candidate attribute, and validate it with
`--checks structure`. Every rejected name comes back as its own
`VALIDATION_ATTRIBUTE_NAME` error, so one call maps a whole tier. Remember the flat
format requires `uid`, `sampletype`, `assay_ids` and `json_metadata` columns — omit
`assay_ids` and CONVERT fails before any attribute is examined.

Record the result in the project's `context/live_sampletype_attributes.json` so the
next session does not re-probe.

## Behavioral rules

- **Never patch a sample type without explicit user agreement for that specific type.**
  It is a global, shared-schema write.
- **Prefer fixing our own build script over changing the schema.** A schema patch is
  correct only when the field is genuinely missing, not when we mis-named it.
- Report `success`/`failed` counts verbatim from `totals`. Do not describe a run as
  passing when rows failed.
- A `warnings.convert_warnings` entry like `Unknown columns (ignored): ['name',
  'parent', 'notes_summary']` is expected — those are the denormalized review columns
  the consolidator adds and the server ignores. Not an error.
- The `validate` endpoint has no side effects. It is safe to run repeatedly.
- **A schema patch fixes a row only if EVERY field on that row is valid.** A row fails
  if any one of its fields is undefined, so adding one attribute may not move the
  success count at all. Judge progress by the distinct (type, field) rejection list,
  not by `success`/`failed` alone. Adding `Notes` to `A.TITR` removed `Notes` from its
  rejection list while the row still failed on `Lab` and `Name` — that is progress,
  and it should be reported as such rather than as a failed patch.

## Schema changes are visible immediately (fixed 2026-08-31)

**A newly added sample-type attribute is visible to `/curate-qc` and to the upload
straight away. No worker restart is required.** If you have older notes saying
otherwise, they described real behaviour that no longer exists.

The bug: `nextseek_api/batch_upload/prefetch.py::prefetch_sample_type_attributes`
cached `sample_type_id -> {attribute titles}` in a module-level dict with no TTL and
no invalidation on write, and gunicorn runs four workers. The symptom was a rejection
count that **oscillated between runs on an unchanged file** — you were being served
by a different worker each time.

The fix is a database-side generation stamp: `SELECT COUNT(*), MAX(updated_at) FROM
sample_attributes`, compared against a per-process stamp and read **once per batch**
from the single path that `validate` and `upload` share. Every worker reads it from
the one thing they all share, so there is nothing left to go stale.

It is **writer-agnostic** — it equally catches writes made through the attributes API,
through the `/seek/samples/attributes/` web page, or by hand in SQL.

Proven on production against a control: an attribute was created through the API with
no restart, a row using it validated, and a row using a never-created attribute failed
down the same path. Same code path, opposite outcomes.

**If validation still rejects a field you just added**, it is not the cache. Check that
the write actually landed (`sampletype-get <TYPE>`) and that the title matches exactly,
case included.

## Why the `sample_types` PATCH route cannot do this (root-caused 2026-07-31)

**Read this as "why the obvious route fails", not as "no REST route works".** The
attributes API — `POST /nextseek_api/attributes/batch-create/`, used by
`/curate-sampletype apply` — is a different, purpose-built route and it works. This
section explains why the *sample_types proxy* is not that route and never can be.

`PATCH /nextseek_api/sample_types/{id}/` returns `502 {"errors":[{"title":"Invalid
upstream response"}]}` for essentially every real sample type. This is NOT a payload
bug, and no reshaping fixes it.

The chain:

1. The endpoint is a 1:1 pass-through to SEEK (`nextseek_api/services/sample_types.py`,
   `SampleTypeProxyViewSet.partial_update`). It adds request validation and nothing else.
2. SEEK refuses the update:

   ```ruby
   # lib/seek/samples/sample_type_editing_constraints.rb
   def allow_new_attribute?
     !samples?
   end
   ```

   enforced by `validate_against_editing_constraints`. **Any sample type that already
   has samples cannot gain an attribute through Rails.**
3. SEEK returns **422** with a bare error hash.
4. `partial_update` never checks the upstream status code. It tries to model-validate
   the 422 body, that raises, and a bare `except Exception` converts it to the generic
   502. The real message is discarded — which is why this is undiagnosable from outside.

Note the narrowing: that model validation enforces only TWO things, adding an attribute
and removing one that holds data. Edits to EXISTING attributes are likely more permissive
over REST than through the SEEK web form — untested.

**The working route** is the attributes API — `POST /nextseek_api/attributes/batch-create/`,
wrapped by `nextseek_api.py sampletype-add-attribute`. It is a purpose-built endpoint, not a
proxy, so `allow_new_attribute?` never enters into it. See `/curate-sampletype` for the full
procedure, the permission model and the error codes.

Two related NExtSEEK defects worth fixing if you are in that code:

- The 502 masking above, which is the same shape across `services/assays.py`,
  `investigations.py`, `people.py`, `projects.py`, `studies.py`, `samples.py`,
  `data_files.py` — every upstream 4xx/5xx becomes a generic 502.
- `dmac/settings.py` configures no `nextseek_api` logger, so the one surviving
  diagnostic (`log.info('seek_proxy ... status=%d')` in `nextseek_api/helpers.py`) is
  written nowhere. That single line would have revealed the 422 immediately.
