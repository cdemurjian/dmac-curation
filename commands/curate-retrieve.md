---
description: Build RETRIEVE.TXT for chat_nextseek (Phase 11)
---

The user wants Phase 11 — emit a newline-separated UID list for the `chat_nextseek` retrieve function.

Parse `$ARGUMENTS`: optional `--include-parents`.

## Prereqs

- A consolidated workbook exists in `assay_sheets/`. `/curate-consolidate` writes `Arm{X}-upload.xlsx` per arm, and `--all-in-one NAME` writes exactly `NAME.xlsx`; both are picked up with no rename. The `*_review.xlsx` companion is skipped — it is never uploaded, so it is never retrieved from.

## Steps

1. Invoke `uv run --script <PLUGIN>/scripts/build_retrieve.py [--include-parents]`.
2. Verify `RETRIEVE.TXT` written. Print per-sample-type counts.
3. Tell the user to paste the file's contents into `chat_nextseek` to fetch the round-tripped `*_AllMetadata.xlsx`.

## Behavioral rules

- Default excludes a MUS/TIS/DNA/RNA/PAT/PAV/CHM/CEL row **only when something
  derives from it** — those are auto-pulled by retrieve's lineage walk. A row of
  one of those types with no child is a leaf and is always emitted: it is the
  only handle on its branch. Branches that dead-end in a parent type are real
  (`PAT -> PAV -> TIS` for a tissue microarray core with no assay downstream),
  and excluding by type alone loses them silently.
- `--include-parents` only for explicit override (rare).
- File preference per basename: `-upload-new.xlsx` > `-upload.xlsx` > bare `.xlsx`.

## Verifying the round trip

Reconcile the returned UIDs against the workbook before `/curate-validate`. Any
uploaded UID that does not come back is a gap in `RETRIEVE.TXT`, not a gap on the
server — group the missing ones by sample type, because a whole missing branch
points at the leaf rule above.
