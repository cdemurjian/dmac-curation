---
description: Maintain QUESTIONS_FOR_PI.md (Phase 3)
---

The user is managing the running questions ledger.

Parse `$ARGUMENTS`:
- `add` (or no args): prompt for new question and append
- `list`: print all open + resolved questions
- `resolve <id>`: prompt for answer, move to resolved

## Steps

### `add` flow

1. Read `./QUESTIONS_FOR_PI.md` (or create from template if absent).
2. Determine next ID (one greater than max existing).
3. Use `AskUserQuestion` for topic, body, and originating phase.
4. Append to "Open" section.
5. Save.

### `list` flow

Print the file's contents grouped by Open / Resolved.

### `resolve <id>` flow

1. Find question by ID.
2. Use `AskUserQuestion` for the answer text.
3. Move from "Open" to "Resolved" with the answer.
4. Save.

## Behavioral rules

- ID format: `Q<N>` numeric, monotonic.
- Each question records the phase that surfaced it.
- Resolved questions never deleted — searchable history matters.
