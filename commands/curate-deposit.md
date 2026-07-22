---
description: Stage external deposits and backfill URLs (Phase 10)
---

The user wants Phase 10 — deposit raw or secondary data to an external repository and backfill `Link_PrimaryData` URLs.

Parse `$ARGUMENTS`: first arg routes to sub-target.

## Sub-routes

### `/curate-deposit geo [--type bulk|spatial]`

1. **Build — delegated to report mode.** Run `/curate-report GEO <input>` and let report mode produce `report/GEO_filled.xlsx` plus its completeness report. Do **not** invoke a renderer here: there is exactly one GEO build path and it lives in report mode.

   The input is usually a curated `assay_sheets/Arm{X}.xlsx`, because **GEO deposit happens before NExtSEEK upload** — the accessions GEO assigns must be backfilled into the sheets first. Report mode's curated-sheet adapter reads those sheets locally, with no API call, which is exactly what that ordering requires.

   Read `report/GEO.completeness.md` with the user before uploading anything. A submission still carrying `*** PLACEHOLDER: ... ***` markers would be rejected by GEO, and hearing that from NCBI is slower than catching it here.
2. **Upload**: invoke `<PLUGIN>/scripts/upload_geo_ncftp.sh GEO/<subfolder>/`. Reads `.env` for `NCFTP_*` creds. Resilient with retry loop.
3. **Validate**: ask user to validate at submit.ncbi.nlm.nih.gov/geo/submission. Note common gotchas — `paired-end` (not `paired`); `Illumina NextSeq 500` (not `NextSeq 500`); processed-file cols must come before raw-file cols.
4. **Backfill (after GEO assigns accessions)**: run once to preview, then again with `--write`:

   ```bash
   uv run --script <PLUGIN>/scripts/apply_geo_accessions.py \
       --gse-bulk GSE###### --gsm-csv <bulk-gsm-roster.txt> \
       [--gse-sptx GSE###### --sptx-gsm-csv <spatial-gsm-roster.txt>] \
       [--write]
   ```

   Bulk and spatial are **separate GEO submissions with separate series accessions**, which is why there are two pairs of flags. `--gse-bulk` and `--gsm-csv` are both required. Omitting `--gse-sptx` skips the A.SPTX patch entirely; `--sptx-gsm-csv` is optional even when `--gse-sptx` is given, in which case the bulk roster is reused and filtered to `D##-####` tokens.

   The roster passed to `--gsm-csv` is **whitespace-delimited with no header** (despite the `csv` in the flag name): column 1 is the GSM accession, column 2 is the sample title. The sample D-id is *extracted from the title*, not given as its own column — bulk matches a trailing `_D######`, spatial matches a bracketed `(D##-####)`. Blank lines and `#` comments are skipped; a title with no D-token is warned about and dropped.

   ```
   GSM9751823    P12_tumor_RNA_D123456
   GSM9751824    P12_normal_RNA_D123457
   ```

   Patches applied: D.SEQ gets `Accession` = GSM and `Link_PrimaryData` = the per-sample GSM URL; A.GEX gets `Link_PrimaryData` = the bulk **series** URL on every row; A.SPTX gets per-sample GSM URLs. Each patched sheet gets a `.bak` alongside it.

   **D.SEQ is all-or-nothing:** if any D.SEQ row's D-id is missing from the roster the script prints the unmapped rows and refuses to save that sheet even under `--write`. Fix the roster and re-run rather than patching by hand.

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
