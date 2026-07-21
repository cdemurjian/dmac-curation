"""No plaintext credential may sit inside the plugin checkout.

`working/` is gitignored, so nothing under it reaches git history — but the
files are readable on disk by anything that can read the checkout, and a token
stays live until it is rotated at the provider. Rotate first, delete second.

Historical exposures this guard exists to catch:

* ``working/fdh-upload-script/.env``                    — ``FDH_API=<token>``
* ``working/.../Assets/Output/session.json``            — ``"api_token": "<token>"``
  (that is the key ``scripts/fdh/submit.py`` actually writes)
* ``working/.../.ipynb_checkpoints/*-checkpoint.ipynb`` — ``API_TOKEN = "<token>"``

The notebook case is why this module scans file *content* and not just file
names: Jupyter mirrors every notebook into a sibling ``.ipynb_checkpoints/``
directory, so deleting a notebook that had a token pasted into a cell leaves a
full copy of the token behind in the checkpoint.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKING = REPO / "working"

# Exact paths that have historically held live tokens in this checkout.
FORBIDDEN = [
    "working/fdh-upload-script/.env",
    "working/fdh-upload-script/Assets/Output/session.json",
    "working/fdh-upload-script/.ipynb_checkpoints/Upload to FDH-checkpoint.ipynb",
]

# Dotenv-shaped names that are allowed to exist because they hold no values.
DOTENV_ALLOWLIST = {".env.example", ".env.sample", ".env.template"}

# A credential-ish key immediately followed by an assignment separator.
# Matches ``api_token":``, ``API_TOKEN =``, ``apiKey:``, ``FDH_TOKEN=``,
# ``Authorization:``, ``client_secret":`` — in .env, JSON and notebook-escaped
# JSON alike (hence the optional backslash before the closing quote of a key).
CRED_KEY_RE = re.compile(
    r"[\w.\-]*"
    r"(?:token|api[_\-]?key|apikey|passwd|password|secret|authorization|fdh_api)"
    r"[\w.\-]*"
    r"\\?[\"']?\s*[:=]\s*",
    re.IGNORECASE,
)

# How much text after the separator counts as "the value".
VALUE_WINDOW = 120

# A token-shaped literal: long, from a urlsafe/base64 alphabet.
CANDIDATE_RE = re.compile(r"[A-Za-z0-9_\-+=]{12,200}")

# Values that are obviously documentation stand-ins, not credentials.
PLACEHOLDER_PREFIXES = (
    "your", "my", "example", "sample", "changeme", "change_me", "replace",
    "insert", "paste", "put", "xxx", "abc", "todo", "dummy", "fake",
    "placeholder", "redacted", "none", "null", "test_", "some",
)


def _shannon(value: str) -> float:
    """Shannon entropy in bits/char. Random tokens land well above 3.0."""
    if not value:
        return 0.0
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in Counter(value).values())


def looks_like_secret(value: str) -> bool:
    """True when `value` reads as a real credential rather than a placeholder."""
    if len(value) < 12:
        return False
    if value.lower().startswith(PLACEHOLDER_PREFIXES):
        return False
    classes = sum(
        bool(re.search(pattern, value))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    # Mixed-alphabet tokens, or long single-alphabet ones (e.g. 40-char hex).
    if classes < 3 and len(value) < 32:
        return False
    return _shannon(value) >= 3.0


def find_credential_literals(text: str) -> list[str]:
    """Return the credential-ish KEYS in `text` that are assigned a real-looking value.

    Only key names are returned — never the value — so that a failure message
    can name the offending file and key without echoing the secret.
    """
    hits = []
    for match in CRED_KEY_RE.finditer(text):
        window = text[match.end():match.end() + VALUE_WINDOW]
        if any(looks_like_secret(c) for c in CANDIDATE_RE.findall(window)):
            hits.append(match.group(0).strip().rstrip(":=").strip().strip("\"'\\"))
    return hits


def _is_probably_text(path: Path) -> bool:
    try:
        return b"\0" not in path.open("rb").read(8192)
    except OSError:
        return False


def scan_tree(root: Path) -> dict[Path, list[str]]:
    """Map every text file under `root` to the credential keys it exposes."""
    offenders: dict[Path, list[str]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size > 20_000_000 or not _is_probably_text(path):
            continue
        hits = find_credential_literals(path.read_text(errors="ignore"))
        if hits:
            offenders[path] = sorted(set(hits))
    return offenders


def test_known_secret_files_are_gone():
    for rel in FORBIDDEN:
        assert not (REPO / rel).exists(), (
            f"{rel} still on disk. Rotate the token on FairDomHub, then delete the file."
        )


def test_no_dotenv_under_working():
    if not WORKING.is_dir():
        pytest.skip("no working/ directory")
    strays = [
        p for p in WORKING.rglob(".env*")
        if p.is_file() and p.name not in DOTENV_ALLOWLIST
    ]
    assert not strays, f"plaintext .env files under working/: {strays}"


def test_no_credential_literals_under_working():
    """Any file under working/ that assigns a real-looking token fails the suite."""
    if not WORKING.is_dir():
        pytest.skip("no working/ directory")
    offenders = scan_tree(WORKING)
    assert not offenders, (
        "credential literals under working/ "
        f"(file -> offending keys, values withheld): "
        f"{ {str(p.relative_to(REPO)): k for p, k in offenders.items()} }"
    )


# --- the detector's own tests, on synthetic data only ------------------------
# These prove the guard above can actually fail. Every value here is invented
# for the test; none is or ever was a real credential.

SYNTHETIC_TOKEN = "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY"  # not a real token


@pytest.mark.parametrize(
    "name,body",
    [
        ("session.json", '{\n  "base_url": "https://x",\n  "api_token": "%s"\n}' % SYNTHETIC_TOKEN),
        (".env", "FDH_TOKEN=%s\n" % SYNTHETIC_TOKEN),
        ("nb-checkpoint.ipynb", '{"source": ["API_TOKEN = \\"%s\\"\\n"]}' % SYNTHETIC_TOKEN),
        ("cfg.yaml", "apiKey: %s\n" % SYNTHETIC_TOKEN),
        ("headers.py", 'HEADERS = {"Authorization": "%s"}' % SYNTHETIC_TOKEN),
    ],
    ids=["session.json", ".env", "ipynb-checkpoint", "yaml", "python"],
)
def test_scanner_flags_synthetic_credentials(tmp_path, name, body):
    (tmp_path / name).write_text(body)
    offenders = scan_tree(tmp_path)
    assert list(offenders) == [tmp_path / name], f"{name} was not flagged"
    # The failure report names keys, never values.
    assert SYNTHETIC_TOKEN not in str(offenders)


@pytest.mark.parametrize(
    "name,body",
    [
        (".env.example", 'FDH_API={"alice": "your_token", "bob": "bobs_token"}\n'),
        ("README.md", 'FDH_API={"your_name": "your_api_token"}\n'),
        ("CLAUDE.md", "The script caches the `api_token` for the session.\n"),
        ("submit.py", 'def _headers(api_token: str):\n    return {"Authorization": f"Token {api_token}"}\n'),
        ("notes.md", "Set the api_token in your shell environment, never in a file.\n"),
    ],
    ids=[".env.example", "README.md", "CLAUDE.md", "source-code", "prose"],
)
def test_scanner_ignores_placeholders_and_prose(tmp_path, name, body):
    (tmp_path / name).write_text(body)
    assert scan_tree(tmp_path) == {}, f"{name} false-positived"
