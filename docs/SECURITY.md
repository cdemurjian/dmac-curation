# Credential handling

## Rule

No credential ever lives in a file inside this checkout, including under
`working/` and including gitignored paths. Gitignore keeps secrets out of
history; it does not keep them off disk.

## Where credentials go instead

| credential | source | consumed by |
|---|---|---|
| `FDH_API` | shell environment, or a `.env` in the **curation project** cwd | `scripts/fdh/fdh_api.py`, `scripts/fdh/submit.py` |
| `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD` | shell environment, or project cwd `.env` | `scripts/nextseek_api.py` |
| `MIT_USER` / `MIT_PASS` | shell environment, or project cwd `.env` | `scripts/smb_pull.py` |
| `NCFTP_*` | shell environment, or project cwd `.env` | `scripts/upload_geo_ncftp.sh` |
| `BIOPORTAL_API_KEY` | shell environment, or project cwd `.env` | `schema` mode ontology lookup |

`scripts/fdh/fdh_api.py:161` shows the correct resolution order: the
**project cwd** `.env` first, the plugin `.env` second. Scripts must never
require a plugin-local `.env`.

## Enforcement

`tests/test_no_plaintext_secrets.py` fails the suite if a `.env` or a
token-bearing `session.json` reappears under `working/`.

## If a token leaks

Rotate first, delete second. A deleted file with a live token is still a
live token.
