# Security: credentials, and identifiers

**This repository is PUBLIC.** Two classes of thing must never reach it: credentials,
and the real sample and protocol identifiers that curation output carries. They have
different guards, different failure modes, and different remedies. Both are below.

## Credential handling

### Rule

No credential ever lives in a file inside this checkout, including under
`working/` and including gitignored paths. Gitignore keeps secrets out of
history; it does not keep them off disk.

### Where credentials go instead

| credential | source | consumed by |
|---|---|---|
| `FDH_API` (`{"user": "token"}`) or `FDH_TOKEN` | shell environment, or a `.env` in the **curation project** cwd | `scripts/fdh/fdh_api.py`, `scripts/fdh/submit.py`. `FDH_TOKEN` is checked first and wins |
| `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD`, or `NEXTSEEK_TOKEN` | shell environment, or project cwd `.env` | `scripts/nextseek_api.py` — **the one script that writes a production sample-type schema**, through the attributes API. Mutations additionally require the SEEK login's Django user to have `is_superuser=1`; a SEEK admin who is not one is refused with 403. |
| `MIT_USER` / `MIT_PASS` | shell environment, or project cwd `.env` | `scripts/smb_pull.py` |
| `OMERO_USER` / `OMERO_PASSWORD`, or `OMERO_SESSIONID` / `OMERO_CSRFTOKEN` | shell environment; the password is prompted for if unset | `scripts/omero_pull.py` |
| `NCFTP_*` | shell environment, or project cwd `.env` | `scripts/upload_geo_ncftp.sh` |
| `BIOPORTAL_API_KEY` | shell environment, or project cwd `.env` | `schema` mode ontology lookup (`scripts/schema/terms.py`, `scripts/schema/ontology.py`) |
| `CEDAR_API_KEY` | shell environment, or project cwd `.env` | `schema` mode reference-template checklist (`scripts/schema/templates.py`). Absent, it makes no network call and renders an empty section |

The `_load_dotenv()` function in `scripts/fdh/fdh_api.py` shows the correct
resolution order: the **project cwd** `.env` first, the plugin `.env` second.
Scripts must never require a plugin-local `.env`.

### How a project gets its `.env`

Keep one filled credentials file **outside every git repository** and point
`$DMAC_ENV_FILE` at it from your shell profile:

    export DMAC_ENV_FILE="$HOME/.config/dmac/.env"

`/curate-init` copies that file to `./.env` in the curation project and `chmod 600`s
the copy. It never reads the values, and it never writes one into the plugin checkout.
With `$DMAC_ENV_FILE` unset or missing, init falls back to rendering `.env.example` and
says so.

The copy lives in the *project*, not here — which is why the rule above is scoped to
this checkout. A project `.env` is still a plaintext credential on disk: it inherits
the project's own `.gitignore` (rendered from `templates/gitignore.j2`), and rotating a
token means rotating it at the provider, not deleting the copies.

### Where credentials have actually turned up on disk

These are the concrete exposures found in this checkout. Check all of them
before assuming a directory is clean.

| location | shape | why it is easy to miss |
|---|---|---|
| `working/fdh-upload-script/.env` | `FDH_API={"name": "<token>"}` | gitignored, so it never shows in `git status` |
| `working/**/Assets/Output/session.json` | `"api_token": "<token>"` — the key `scripts/fdh/submit.py` writes | generated at runtime; regenerated every session |
| `working/**/.ipynb_checkpoints/*-checkpoint.ipynb` | `API_TOKEN = "<token>"` in a cell | **Jupyter mirrors every notebook into a sibling `.ipynb_checkpoints/` directory. Deleting the notebook does not delete the checkpoint.** A token pasted into a cell survives there indefinitely, in a dot-directory most tooling hides. |

Whenever a notebook that touched a credential is removed, remove its
`.ipynb_checkpoints/` sibling in the same breath.

### Enforcement

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

#### What it does not catch

- Credentials outside `working/` — nothing else in the checkout is scanned *by this
  guard*. The identifier guard below scans the entire tracked tree, including
  binaries and zip members.
- Binary files (`.xlsx`, `.docx`) and files over 20 MB are skipped.
- A token stored under a key name that does not read as credential-ish, or a
  short/low-entropy token.
- Anything already in git history. This is a disk-hygiene guard, not a
  history scrubber.

When `working/` does not exist, tests 2 and 3 `pytest.skip` rather than pass,
so a green run on a fresh clone is not mistaken for a verified-clean tree.

### If a token leaks

Rotate first, delete second. A deleted file with a live token is still a
live token. Deleting the file removes the on-disk copy; only revoking the
credential at the provider closes the exposure.

---

## Identifiers

Credentials are not the only exposure. Curation output — the production extract, the
rulings, the agent verdicts, the review surfaces, the handoff reports — carries real
sample UIDs and protocol titles, and one of those titles carries a person's name.

**This has gone wrong twice, and both times cost a history rewrite.**

- **2026-08-21.** `assay-hygiene-bak/` held 195 MB of real sample metadata while
  matching no `.gitignore` pattern. The rewrite stripped **1,570 sample identifiers**
  from history.
- **2026-08-25.** Six `.claude/reports/*.json` handoff reports, which quote protocol and
  sample identifiers verbatim, were committed and the branch had to be rewritten.
- **2026-08-24**, caught before it landed: `mode2-rulings-backup-2026-08-20.tsv`, a
  byte-identical copy of the whole ruling file, sat untracked and unignored in the
  repository root.

### What that bought

`.gitignore` now excludes by **name and prefix**, not by location, precisely because
each of those escaped a location-scoped rule: `assay-hygiene/` **and** `assay-hygiene-*/`;
`assets/`; unanchored `*rulings*.tsv` and `*verdicts*.csv`; `.claude/`;
`scripts/fdh/generated/*.py`. Every one of those lines has its incident written above
it. **Read the comments before editing that file**, and when you add an exclusion, add
the reason.

### The guard

`tests/test_identifier_exposure.py` is a **ratchet on identifier-shaped strings in
tracked files**, not a ban — a test suite about UID grammar needs well-formed UIDs. It
goes red when the count grows and red again when it shrinks, so a cleanup tightens the
baseline instead of leaving it stale.

Two tiers: a pattern-only tier that runs everywhere (including CI and a fresh clone,
which is exactly where an accidental commit is most likely), and a verified tier that
runs only where the extract exists and names the smaller true number. The verified
baselines are **0**.

Two holes it had, each of which hid a real identifier, both now closed:

1. **Case.** Four real protocol titles were written lowercase; an `[A-Z]{3}` pattern
   cannot see them. The pattern is case-tolerant by character class rather than by a
   flag, so `git grep -E` and Python agree.
2. **Binaries.** `git grep -I` skips them by design, and `tests/fixtures/sample.xlsx`
   carried three UIDs inside its zipped sheet XML. One test opens tracked bytes and zip
   members instead of grepping.

**Scanning a diff answers "am I adding one". Only scanning the whole tracked tree
answers "is one there".** A 2026-08-25 pre-push scan checked one push's diff, reported
clean, and was correct — while 97 occurrences already sat in 22 tracked files.

### Writing a fixture that needs an identifier

Do not invent a free-form one, and do not restore a real one. The 2026-08-25 cleanup
*replaced* every real identifier rather than deleting it, by moving its `<YYMMDD><LAB>`
batch stamp into a **reserved synthetic band, `19MMDD`**: no uuid in the extract carries
a 19xx date for any lab, so a UID stamped `19MMDD` is provably not a person's sample,
while the type prefix, lab code and serial are preserved so every documented
relationship still reads. Protocol titles moved the same way, under lab codes absent
from all 553 SOP titles. **Keep new fixtures in those bands.**

### If an identifier lands in history

Unlike a credential, there is nothing to rotate. The only remedy is a history rewrite
plus a force-push, and every clone and every open branch has to be re-based onto it.
That asymmetry is the reason the `.gitignore` rules are deliberately over-broad.
