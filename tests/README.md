# tests/

## Running

`uv run pytest`. Read the banner `conftest.py` prints at the end: it names every test
skipped for a missing extract.

**A green suite is not evidence the assay pipeline was measured.** The assay fixtures
depend on a production extract that is gitignored and not present in a fresh clone or in
CI, so a large block of tests skips by default. The banner exists because that block was
read as healthy for days.

This cuts both ways for the identifier guard: the tests that compare tracked strings
against *real* production identifiers are in that skipped block. Where the extract is
absent, only the pattern-count ratchet runs.

## What guards what

| file | guards |
|---|---|
| `test_identity_sync.py` | the description and version across `plugin.json`, `marketplace.json`, `SKILL.md` — the YAML-safety of the frontmatter string, and an activation cue per mode |
| `test_mode_table.py` | `SKILL.md`'s mode table against `commands/` and the reference docs; the PHASES.md phase table, including the 9a/9b split |
| `test_no_plaintext_secrets.py` | credentials under `working/` |
| `test_identifier_exposure.py` | a two-directional ratchet on identifier-shaped strings in tracked files, including binaries and zip members |
| `test_dependency_pinning.py` | `pyproject.toml` pins, and its version against `plugin.json` |
| `test_deposit_write_safety.py` | every deposit script defaults to dry-run |

## Fixtures with identifiers

Use the reserved synthetic band `19MMDD` for UID batch stamps and the reserved lab codes
for protocol titles. See `docs/SECURITY.md`.
