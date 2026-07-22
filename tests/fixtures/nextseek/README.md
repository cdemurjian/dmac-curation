# Harvested NExtSEEK API fixtures

These are **harvested**, not authored.

chat_nextseek persists exactly the API responses this plugin needs, on every
report run (`reports/outputs.py:555-563`):

| artifact | content |
|---|---|
| `report_metadata.json` | the `/admin/samples/retrieve/` response |
| `protocols.json` | the `/sops/{id}/` responses |
| `protocol_files.json` | downloaded blobs plus extracted docx/pdf text |

Non-report runs additionally leave `api_requests.json` and
`api_result_bundle_*.json` in the same run directories.

## Why harvest rather than author

The retrieve response is nested five levels
(`data.data[i].samples[j].metadata`) and lineage is the flat `Parent` key, an
upward UID pointer, not nesting. A hand-written fixture that gets that wrong
would make the adapter tests pass against a shape the API never returns, which
is worse than having no fixture.

## Procedure

1. Look for existing runs first:

   ```bash
   ls ~/.local/state/chat_nextseek/outputs/
   ```

2. If none carry what you need, generate one. Take UIDs from
   `e2e/catalog.json` family `reporting`, which has real production UIDs:

   ```bash
   cd /home/cdemu/code/chat_nextseek
   uv run cli.py -q "Build me a GEO Submission for D.SEQ-221031SHA-67-PUB"
   ```

3. Scrub before committing. Run directories contain real tokens and localhost
   URLs:

   ```bash
   uv run --script <PLUGIN>/scripts/report/scrub_fixture.py \
       ~/.local/state/chat_nextseek/outputs/<run>/report_metadata.json \
       tests/fixtures/nextseek/report_metadata.json
   ```

4. `tests/test_report_fixtures.py` asserts the scrubbing worked. It skips
   cleanly when a fixture has not been harvested, so the suite stays green on a
   machine with no NExtSEEK access.

### Sharp edge for the harvester

`test_fixture_carries_no_credentials` rejects a fixture whose text contains the
substrings `"password"`, `"localhost"`, `"127.0.0.1"` or `"bearer "`.
`scrub_fixture.py` redacts secret-looking *values* but keeps the *key*, so a
literal `"password"` key (or a value that happens to contain one of those
substrings) would survive scrubbing and fail that test. If it fires, inspect the
scrubbed output and rename or drop the offending key by hand before committing;
do not weaken the test.

## What was genuinely missing upstream

Not the fixtures - those are produced on every run. What is absent is fixtures
**committed under `tests/`**: chat_nextseek's entire committed corpus for this
path is two inline dicts, in `test_report_code.py` and
`test_report_outputs_gating.py`. Committing scrubbed harvested artifacts here is
new coverage, not a copy.
