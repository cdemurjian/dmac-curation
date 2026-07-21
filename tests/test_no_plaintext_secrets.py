"""No plaintext credential files may sit inside the plugin checkout.

`working/` is gitignored, so these never reach history — but they are
readable on disk and the tokens in them are live. Rotate + delete.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Filenames that have historically held live tokens in this checkout.
FORBIDDEN = [
    "working/fdh-upload-script/.env",
    "working/fdh-upload-script/Assets/Output/session.json",
]

# Substrings that indicate a real token rather than a placeholder.
TOKEN_HINTS = ("FDH_API=", "FDH_TOKEN=", '"token"')


def test_known_secret_files_are_gone():
    for rel in FORBIDDEN:
        assert not (REPO / rel).exists(), (
            f"{rel} still on disk. Rotate the token on FairDomHub, then delete the file."
        )


def test_no_dotenv_under_working():
    working = REPO / "working"
    if not working.is_dir():
        return
    strays = [p for p in working.rglob(".env") if p.is_file()]
    assert not strays, f"plaintext .env files under working/: {strays}"


def test_no_session_json_with_token_under_working():
    working = REPO / "working"
    if not working.is_dir():
        return
    offenders = []
    for p in working.rglob("session.json"):
        text = p.read_text(errors="ignore")
        if any(h in text for h in TOKEN_HINTS):
            offenders.append(p)
    assert not offenders, f"session.json holding a token: {offenders}"
