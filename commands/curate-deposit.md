---
description: Stage external deposits and backfill URLs (Phase 10)
---

The user wants Phase 10 — deposit raw or secondary data to an external repository and backfill `Link_PrimaryData` URLs.

Parse `$ARGUMENTS`: first arg routes to sub-target.

## Sub-routes

### `/curate-deposit geo [--type bulk|spatial] [--gse GSE######]`

1. **Build**: invoke `<PLUGIN>/scripts/deposit/geo_build_xlsx.py` to render `GEO/BULK_filled.xlsx` or `GEO/SPTX_filled.xlsx` from `previous_metadata/*_AllMetadata*.xlsx`.
2. **Upload**: invoke `<PLUGIN>/scripts/upload_geo_ncftp.sh GEO/<subfolder>/`. Reads `.env` for `NCFTP_*` creds. Resilient with retry loop.
3. **Validate**: ask user to validate at submit.ncbi.nlm.nih.gov/geo/submission. Note common gotchas — `paired-end` (not `paired`); `Illumina NextSeq 500` (not `NextSeq 500`); processed-file cols must come before raw-file cols.
4. **Backfill (after GSE assigned)**: `<PLUGIN>/scripts/apply_geo_accessions.py --write --gse <GSE>`.

### `/curate-deposit zenodo [--record-id N] [--from-figures]`

1. **Stage**: `<PLUGIN>/scripts/stage_zenodo.py` to preview, then (after confirm) re-run with `--write`. Walks `files/Figure*/` + `files/Source Data/`, groups by figure × sample type, and **moves** each curated non-image file into a per-bucket *folder* `files/Figure {N}/Figure{N}_{SampleType}/`. It moves files only — it does **not** create archives.
2. **Archive — manual, no script does this.** The curator creates one archive per bucket folder (e.g. `zip -r Zenodo_upload/Figure3_D.WES.zip "files/Figure 3/Figure3_D.WES"`) and puts the `.zip` files in `Zenodo_upload/`. Tell the user this step is theirs; do not claim staging produced zips.
3. **User uploads** those zips manually to Zenodo via web UI. User reports back the record ID.
4. **Backfill**: `<PLUGIN>/scripts/apply_zenodo_links.py --write --record-id <N>`. Reads each `.zip` in `Zenodo_upload/` (override with `--zip-dir`), joins its namelist to upload-sheet rows by filename, patches `Link_PrimaryData`. If step 2 was skipped there are no archives to read and the backfill patches nothing.

### `/curate-deposit omero [--project-id N]`

1. **Identify files** in `images_to_upload_to_omero/` (or whichever dir the user is staging from).
2. **User uploads** to OMERO via Insight desktop or web UI.
3. **Pull IDs**: `<PLUGIN>/scripts/omero_pull.py all --project <N>` → `omero_images.csv`.
4. **Backfill**: `<PLUGIN>/scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData` from `omero_images.csv`.

## Behavioral rules

- All deposit scripts default to dry-run and require `--write` to mutate anything. Show the user the dry-run output and get confirmation before re-running with `--write`.
- GEO has lots of literal-validation gotchas — surface them in the report.
- OMERO requires MIT VPN.
- Never log credentials. Read from `.env` via python-dotenv.
