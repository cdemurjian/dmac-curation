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
