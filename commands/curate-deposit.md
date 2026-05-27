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

1. **Stage**: `<PLUGIN>/scripts/stage_zenodo.py --dry-run` then (after confirm) without dry-run. Walk `files/Figure*/` + `files/Source Data/`. Group by figure × sample type. Produce per-bucket zips in `Zenodo_upload/`.
2. **User uploads** zips manually to Zenodo via web UI. User reports back the record ID.
3. **Backfill**: `<PLUGIN>/scripts/apply_zenodo_links.py --write --record-id <N>`. Joins zip namelists to upload-sheet rows by filename, patches `Link_PrimaryData`.

### `/curate-deposit omero [--project-id N]`

1. **Identify files** in `images_to_upload_to_omero/` (or whichever dir the user is staging from).
2. **User uploads** to OMERO via Insight desktop or web UI.
3. **Pull IDs**: `<PLUGIN>/scripts/omero_pull.py all --project <N>` → `omero_images.csv`.
4. **Backfill**: `<PLUGIN>/scripts/apply_omero_ids.py --write` patches D.IMG `Link_PrimaryData` from `omero_images.csv`.

## Behavioral rules

- All scripts default to `--dry-run`. Confirm before applying writes.
- GEO has lots of literal-validation gotchas — surface them in the report.
- OMERO requires MIT VPN.
- Never log credentials. Read from `.env` via python-dotenv.
