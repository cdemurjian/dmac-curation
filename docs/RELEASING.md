# Releasing

The version lives in six places. Change all six in one commit.

| file | field |
|---|---|
| `.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` | `plugins[0].version` |
| `scripts/_lockfile.py` | `PLUGIN_VERSION` — stamped into every project's `.dmac-curation.json` at `/curate-init` |
| `pyproject.toml` | `version` |
| `README.md` | the `**Status:**` line |
| `tests/test_identity_sync.py` | the literal in `test_version_is_the_toolkit_release` |

Three of those are asserted equal to each other by
`test_versions_agree_across_plugin_marketplace_and_lockfile`, and `pyproject.toml` is
asserted equal to `plugin.json` by `test_pyproject_version_matches_plugin_json`. `README.md`
is the one copy no test covers — check it by eye.

**Not a version copy:** the `"plugin_version": "0.3.0"` literals in
`scripts/_lockfile.py`'s docstring and in `tests/conftest.py`'s `curation_project` fixture.
Those are deliberately *old* — the fixture exercises reading a lockfile written by an
earlier plugin. Leave them alone. Do add the version you are leaving behind to the stale
list in `test_curate_init_does_not_hardcode_a_stale_version`.

## Procedure

1. Promote `## Unreleased` in `CHANGELOG.md` to `## X.Y.Z - <date>`; move anything not
   actually shipping back under a fresh `## Unreleased`.
2. Change the six fields above.
3. `uv run pytest tests/test_identity_sync.py tests/test_lockfile.py
   tests/test_dependency_pinning.py tests/test_mode_table.py`
4. `uv run pytest` — and read the skip banner `tests/conftest.py` prints. A green suite
   with the extract absent has not measured the assay pipeline.
5. Reinstall from the marketplace and confirm the version the plugin reports.

## What earns a minor bump

A new mode, a new command, or a new write path. A doc-only pass does not.
