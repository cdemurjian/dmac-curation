---
description: Draft EMAIL_TO_PI.md iteratively (Phase 13)
---

The user wants Phase 13 — draft an email to the PI summarizing the curation state and asking remaining questions.

## Prereqs

- `SAMPLE_TREE.md`, `QUESTIONS_FOR_PI.md` exist
- `CLAUDE.md` has lab + pi

## Steps

1. Read project state. Identify: arms built, arms deferred, deposit status, open questions.
2. Render `<PLUGIN>/templates/EMAIL_TO_PI.md.j2` into `./EMAIL_TO_PI.md` with skeleton (subject, greeting, summary paragraph, files curated, questions, deposits, asks).
3. **Iterate per-section with the user.** Don't dump full text. Present subject first, get feedback. Then summary paragraph. Then questions. Then asks. User writes the final voice in their own words.
4. Convert any row-number references to Name-pattern anchors (`the 27 rows ending in _phospho`, not `rows 28-54`).
5. Strip em dashes — replace with hyphens or colons.
6. Save final version.

## Behavioral rules

- Skeleton-first. Don't dump full prose.
- Iterate per-section.
- Name-pattern anchors, never row numbers.
- No em dashes (Charlie's style).
- Group questions by intent: structural/files vs metadata-clarifications.
- For multiple PIs: address all in greeting; ask user how to apportion questions.
