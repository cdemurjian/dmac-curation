# Auto-detect project + lab code in `curate-init` — Design

**Date:** 2026-08-04
**Status:** Approved (design), pending implementation plan
**Component:** `dmac-curation` plugin — `scripts/nextseek_api.py` + `commands/curate-init.md`

## Goal

Stop making the curator hand-type `--lab`, `--pi`, and (later) the NExtSEEK
project id at `/curate-init`. Instead, use the API plus whatever local evidence
exists to **auto-detect and pre-fill** the project, lab code, and PI, presented
as a single one-tap confirmation. Reduce typing without reintroducing the
UID-stamp collision risk (a wrong lab code silently overwrites another lab's
records on upload).

## Non-goals

- Not building a fuzzy-match library — simple token-overlap ranking is enough.
- Not adding a new "labs" API endpoint — lab codes are read from the project
  export we already pull.
- Detection fills only `lab` / `pi` / `nextseek_project_id`. Everything else in
  init (dirs, templates, `.env` copy, lockfile merge) is unchanged.
- Not fully autonomous: the lab code is **always** confirmed, never applied
  silently.

## Approach (chosen: A — evidence-ranked auto-detect + one-tap confirm)

Auto-detect and pre-fill from the API + local evidence, then require a single
confirmation. When the guess is right it is one keystroke; a wrong lab code
cannot pass without the curator seeing it. Rejected alternatives: fully
autonomous zero-input (re-creates the collision bug), and always-interactive
pickers (more typing, less automation).

## Architecture

- **`nextseek_api.py detect-context`** (new subcommand) does all API + evidence
  work and prints a JSON suggestion to stdout. Pure/testable; matches the
  existing "API logic in nextseek_api.py, orchestration in the command" split.
- **`curate-init.md`** orchestrates: in pipeline mode, when `--lab`/`--pi`/
  `--project-id` are omitted, call `detect-context`, present the top candidate
  via `AskUserQuestion`, then write the confirmed values into the lockfile.
- **Reuses `NExtSEEKClient.export_project`** (the `pull-db` plumbing). The export
  pulled to read lab codes is written into `previous_metadata/`, so it doubles
  as the fresh DB pull the build stamp-guard requires.
- init now also sets `modes.pipeline.nextseek_project_id`, retiring that manual
  step at `/curate-resolve-assays`.

## `detect-context` — data flow

1. `GET /projects/` → 12 `{id, title}`.
2. Gather local evidence (best-effort, whatever exists):
   - cwd path tokens (e.g. `csbc-publications/flower-curation-tyrosine` →
     `csbc`, `flower`, `tyrosine`);
   - `manuscript/` filenames + light text extract → author surnames, DOI;
   - any `previous_metadata/` master filename (e.g. `CSBC All …`).
3. **Rank projects** by token overlap of evidence vs. project titles.
4. Pull the top project's export (`export_project`, xlsx) → also saved to
   `previous_metadata/`.
5. Extract per **lab code** from the export UIDs (`<TYPE>-<YYMMDD><LAB>-N`):
   sample count, distinct `Scientist`s, latest date-stamp.
6. **Rank lab codes**: a manuscript-author surname matching a `Scientist` wins;
   else by count, then recency.
7. Guess **PI**: `--pi` if given; else the top lab's dominant `Scientist`
   (or manuscript corresponding author).

### Output JSON (stdout)

```json
{
  "projects": [{"id": 10, "title": "Cancer_Systems_Biology_Consortium(CSBC)", "score": 3}, ...],
  "chosen_project": {"id": 10, "title": "..."},
  "labs": [{"code": "WHI", "count": 111, "scientists": ["Cameron Flower", "Forest White"], "latest": "190221"}, ...],
  "pi_guess": "white",
  "export_path": "previous_metadata/project-10-...CSBC.xlsx",
  "evidence": ["path:csbc", "manuscript-author:White", ...],
  "warnings": ["..."]
}
```

## init flow changes

- Pipeline mode, args omitted → run `detect-context`; present one combined
  confirm: *"Project **CSBC (10)**, lab **WHI** (White; 111 samples, latest
  190221), PI **white** — accept / change?"* One keystroke to accept; override
  chooses from the ranked project / lab lists (or free-text a new lab code).
- `detect-context` pulls the **top-ranked** project's export so the lab list is
  ready for the single confirm. If the curator overrides the **project** at the
  confirm, init re-invokes `detect-context --project-id <new>` (which pulls that
  project's export and its labs) and re-presents — the common case (guess right)
  stays one pull + one confirm; a project override costs one extra pull.
- Confirmed values → lockfile (`lab`, `pi`, `nextseek_project_id`). The export
  already sits in `previous_metadata/` for the guard.
- Explicit `--lab`/`--pi`/`--project-id` skip detection but still validate the
  project id against the API and still pull its export.

## Safety

The **lab code is always confirmed**, never auto-applied. This is the guardrail
against re-creating the UID-stamp collision (minting into another lab's stamp).
The confirm is one keystroke when the guess is right.

## Error handling / fallbacks (each degrades, never blocks)

| Condition | Behavior |
|---|---|
| No creds / no network | Fall back to current behavior (`AskUserQuestion` for lab/pi); note detection skipped. |
| No confident project match | Present the full ranked project list to pick. |
| New/empty project, no lab codes yet | Curator types the lab code (free text). |
| Bare init (empty `manuscript/`) | Rank on folder name + lab recency/count; weaker default, still a confirm. |
| Export pull fails | Detection returns projects-only suggestion; lab picked from a later pull or typed. |

## Testing

- **Unit (offline, no network):** pure ranking functions against fixtures — fake
  `/projects/` list + a small synthetic export → assert project rank and lab
  rank, including the manuscript-author-match boost and the recency/count
  tiebreak. Evidence-gathering tested against a temp dir tree.
- **Live smoke:** `detect-context` against project 10 → expects CSBC chosen and
  WHI/AGA/… present in `labs` with plausible counts.
