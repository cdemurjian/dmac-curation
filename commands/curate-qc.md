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

6. Hand off the agreed patches to `/curate-sampletype apply <TYPE> --add <FIELD>`.
   That command owns the write; this one only diagnoses.

7. Re-run step 1 to confirm the fix took and nothing else broke.

## Probing what a type actually accepts

The authoritative source is the server, not the bundled catalog. Read one type
directly:

```bash
uv run --script <PLUGIN>/scripts/nextseek_api.py sampletype-get A.TITR
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

## Known server-side blocker (as of 2026-07-30)

`PATCH /nextseek_api/sample_types/{id}/` returns **`502 {"errors":[{"title":"Invalid
upstream response"}]}`** on nextseek.mit.edu, so `/curate-sampletype apply` cannot
currently complete. Verified twice against `A.TITR` (id 99) with payloads conforming
to `SampleTypePatchData` / `SampleTypeSampleAttributePatch`, using both the title-ref
and id-ref forms of `sample_attribute_type`.

Evidence it is not the payload:
- `GET` on the same resource succeeds, so auth, path and resource id are all correct.
- The error body is NExtSEEK's proxy reporting that UPSTREAM SEEK returned something
  it could not interpret — a gateway failure, not a validation rejection (a bad
  payload returns a 400 with field-level detail).
- The sample type was re-read after each attempt and was **byte-identical both times**,
  so the write never partially applied.

**Do not keep retrying.** Two attempts is enough to establish it. Report it to the
NExtSEEK administrators, and in the meantime either drop the offending field from the
build script or have an admin add the attribute through the web UI.

Re-test with the dry run (`sampletype-add-attribute <TYPE> --name <FIELD>`, no
`--apply`) plus one `--apply` after the admins confirm a fix.
