---
description: Build RETRIEVE.TXT for chat_nextseek (Phase 11)
---

The user wants Phase 11 — emit a newline-separated UID list for the `chat_nextseek` retrieve function.

Parse `$ARGUMENTS`: optional `--include-parents`.

## Prereqs

- `assay_sheets/*-upload-new.xlsx` (or `-upload.xlsx`) exists

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]`.
2. Verify `RETRIEVE.TXT` written. Print per-sample-type counts.
3. Tell the user to paste the file's contents into `chat_nextseek` to fetch the round-tripped `*_AllMetadata.xlsx`.

## Behavioral rules

- Default excludes MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL (auto-pulled by retrieve).
- `--include-parents` only for explicit override (rare).
- Prefer `-upload-new.xlsx` over `-upload.xlsx` (latest curation).
