# Contributing to dmac-curation

## Things that live in more than one file

- **The canonical description** — `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `skills/curation/SKILL.md` frontmatter, and
  `tests/test_identity_sync.py::CANONICAL_DESCRIPTION`. All four must match byte for
  byte; the first three are asserted equal to the fourth. It is unquoted YAML
  frontmatter, so it must contain no `": "` — a colon-space makes the skill stop
  loading altogether. It is also what skill activation matches on, so every mode
  needs a cue in it (`test_description_carries_an_activation_cue_for_every_mode`).
- **The version** — six places. See `docs/RELEASING.md`.
- **The mode table** — `SKILL.md` is the source; `tests/test_mode_table.py` asserts it
  against `commands/` and against the reference docs.

## Adding a command

1. `commands/<name>.md` with frontmatter `description`.
2. A row in the right mode's table in `skills/curation/SKILL.md`.
3. A row in the right table in `README.md`.
4. If the command is the first of a new mode, everything in "Adding a mode" below.

## Adding a mode

A mode is a convention, not a framework: entry-point commands, a reference doc loaded on
demand, and optionally its own scripts. Nothing is registered in `plugin.json`. What must
change: the mode table in `SKILL.md`, a `### <mode>` subsection in `SKILL.md`, a new
`skills/curation/<MODE>.md`, the mode bullet and command table in `README.md`, the
canonical description in all four places above **including an activation cue**,
`scripts/status.py` if `/curate-status` should report it, and a `CHANGELOG.md` entry.

The `assay` mode is the cautionary tale: it shipped complete, with 8 commands and 39
modules, and stayed invisible to skill activation for a release because the description
was not among the files that changed.

## Invocation forms — they are not interchangeable

- Standalone `scripts/*.py` — PEP 723 inline deps, run with `uv run --script`.
- `scripts/assay_hygiene/` — a package; relative imports mean `uv run --script` raises
  `ImportError: attempted relative import with no known parent package`. Drive it with
  `PYTHONPATH=scripts uv run --with pandas --with pyarrow python -c ...`.
- `scripts/schema/`, `scripts/report/` — libraries, no `main()`. Import them.

## Two guards you will meet

- `tests/test_no_plaintext_secrets.py` — credentials.
- `tests/test_identifier_exposure.py` — a ratchet on identifier-shaped strings in tracked
  files. It goes red when the count grows *and* when it shrinks. New fixtures use the
  reserved `19MMDD` synthetic band. This repository is **public**; read `docs/SECURITY.md`
  before adding any fixture — or any prose — derived from real data. A real
  `<YYMMDD><LAB>` batch stamp quoted in a changelog entry is an exposure exactly like one
  in a fixture, and the test that catches it only runs where the extract is present.

## Documentation is not optional

`commands/*.md` is the authority on what a command does; `skills/curation/*.md` is the
authority on how a mode works. A behaviour change that lands without the matching doc
edit is an incomplete change. Nothing tests prose against code — that is why the
2026-08-27 audit (`docs/audit/2026-08-27-docs-audit/`) found 55 drift findings.
