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

The `_load_dotenv()` function in `scripts/fdh/fdh_api.py` shows the correct
resolution order: the **project cwd** `.env` first, the plugin `.env` second.
Scripts must never require a plugin-local `.env`.

## Where credentials have actually turned up on disk

These are the concrete exposures found in this checkout. Check all of them
before assuming a directory is clean.

| location | shape | why it is easy to miss |
|---|---|---|
| `working/fdh-upload-script/.env` | `FDH_API={"name": "<token>"}` | gitignored, so it never shows in `git status` |
| `working/**/Assets/Output/session.json` | `"api_token": "<token>"` — the key `scripts/fdh/submit.py` writes | generated at runtime; regenerated every session |
| `working/**/.ipynb_checkpoints/*-checkpoint.ipynb` | `API_TOKEN = "<token>"` in a cell | **Jupyter mirrors every notebook into a sibling `.ipynb_checkpoints/` directory. Deleting the notebook does not delete the checkpoint.** A token pasted into a cell survives there indefinitely, in a dot-directory most tooling hides. |

Whenever a notebook that touched a credential is removed, remove its
`.ipynb_checkpoints/` sibling in the same breath.

## Enforcement

`tests/test_no_plaintext_secrets.py` fails the suite when any of the following
is true. It scans on-disk state under `working/`, not git history — gitignored
files are exactly the ones it is looking for.

1. **`test_known_secret_files_are_gone`** — any path in its `FORBIDDEN` list
   exists. That list is the three exposures tabled above, by exact path.
2. **`test_no_dotenv_under_working`** — any file matching `.env*` exists under
   `working/`, other than `.env.example` / `.env.sample` / `.env.template`.
   The glob is `.env*`, so `.env.local` and `.env.prod.local` are caught too.
3. **`test_no_credential_literals_under_working`** — *content* scan of every
   text file under `working/` (any name, any extension, including notebooks
   and checkpoints). It flags a file when a credential-ish key
   (`token`, `api_key` / `apikey`, `password`, `secret`, `authorization`,
   `fdh_api`) is followed by an assignment whose value looks like a real
   credential: 12+ characters, mixed alphabet or 32+ chars, Shannon entropy
   at or above 3.0 bits/char, and not a `your_…` / `changeme` / `example…`
   placeholder. Failure messages name the file and the offending **key only**
   — never the value.

The detector itself is covered by ten synthetic-fixture tests in the same
file, which assert it fires on planted `session.json` / `.env` / notebook /
YAML / Python credentials and stays quiet on `.env.example` placeholders,
prose mentions of `api_token`, and ordinary source that passes `api_token`
as a parameter.

### What it does not catch

- Credentials outside `working/` — nothing else in the checkout is scanned.
- Binary files (`.xlsx`, `.docx`) and files over 20 MB are skipped.
- A token stored under a key name that does not read as credential-ish, or a
  short/low-entropy token.
- Anything already in git history. This is a disk-hygiene guard, not a
  history scrubber.

When `working/` does not exist, tests 2 and 3 `pytest.skip` rather than pass,
so a green run on a fresh clone is not mistaken for a verified-clean tree.

## If a token leaks

Rotate first, delete second. A deleted file with a live token is still a
live token. Deleting the file removes the on-disk copy; only revoking the
credential at the provider closes the exposure.
