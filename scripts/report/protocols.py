# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Discover, fetch and extract protocol (SOP) text.

Four traps, all inherited from chat_nextseek's reports/protocols.py and all
handled here deliberately:

  1. Refs to `fairdata.mit.edu` are NOT fetched from that host. They are
     redirected to whatever NEXTSEEK_BASE_URL is. Only `fairdomhub.org` goes
     off-host, and it needs FDH_API as a bearer token with NO FALLBACK.
  2. Refs are discovered from a metadata key named literally `Protocol`,
     matching a `/sops/{id}` URL or a bare `P.*` name. A key merely CONTAINING
     "protocol" is not a ref.
  3. DOCX extraction is stdlib-only. PDF needs PyPDF2 and upstream SILENTLY
     YIELDS NOTHING when it is absent; here that raises PdfSupportError.
  4. Text is truncated at ~3000 tokens. Truncation is REPORTED, not silent -
     a curator reading a protocol paragraph that stops mid-sentence deserves to
     know why.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from urllib.parse import urlparse, urlunparse

_SOP_URL_RE = re.compile(r"/sops/([^/?#]+)")
_BARE_SOP_RE = re.compile(r"^P\.[A-Za-z0-9._-]+$")
_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_MARKERS = ("*** PLACEHOLDER", "***PLACEHOLDER")

DOCX_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
)
PDF_CONTENT_TYPES = ("application/pdf",)

DEFAULT_TOKEN_LIMIT = 3000


class PdfSupportError(RuntimeError):
    """PyPDF2 is not installed. Upstream returned empty text; we refuse to."""


def find_protocol_refs(normalized) -> dict[str, list[str]]:
    """{uid: [refs]} from any metadata key literally named `Protocol`."""
    out: dict[str, list[str]] = {}
    for sample in normalized.samples:
        raw = sample.metadata.get("Protocol")
        if raw in (None, ""):
            continue
        text = str(raw)
        if any(m in text for m in _PLACEHOLDER_MARKERS):
            continue
        refs = [r.strip() for r in text.split(";") if r.strip()]
        refs = [r for r in refs if parse_sop_id(r)]
        if refs:
            out[sample.uid] = refs
    return out


def parse_sop_id(ref: str) -> str | None:
    """A `/sops/{id}` URL or a bare `P.*` name. Free prose returns None."""
    ref = str(ref).strip()
    hit = _SOP_URL_RE.search(ref)
    if hit:
        return hit.group(1)
    if _BARE_SOP_RE.match(ref):
        return ref
    return None


def resolve_host(url: str, *, nextseek_base_url: str) -> str:
    """Redirect fairdata.mit.edu refs to the configured NExtSEEK host.

    Only fairdomhub.org genuinely goes off-host, and it requires FDH_API as a
    bearer token with **no fallback** - there is no anonymous read path.
    """
    url = str(url).strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        return nextseek_base_url.rstrip("/") + "/" + url.lstrip("/")
    host = (parsed.hostname or "").lower()
    if host == "fairdomhub.org" or host.endswith(".fairdomhub.org"):
        return url
    base = urlparse(nextseek_base_url)
    return urlunparse((base.scheme, base.netloc, parsed.path,
                       parsed.params, parsed.query, parsed.fragment))


def extract_docx_text(data: bytes) -> str:
    """Stdlib-only: unzip, read word/document.xml, strip tags."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""
    spaced = xml.replace("</w:p>", "\n").replace("</w:tr>", "\n")
    return re.sub(r"\n{3,}", "\n\n", _TAG_RE.sub("", spaced)).strip()


def extract_pdf_text(data: bytes) -> str:
    """PDF text. Raises PdfSupportError when PyPDF2 is unavailable.

    Upstream silently returned nothing here, so a missing optional dependency
    became a silently empty protocol section in a submission artifact.
    """
    try:
        import PyPDF2  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise PdfSupportError(
            "PDF protocol extraction needs PyPDF2, which is not importable. "
            "Install it (uv run --with PyPDF2 ...) or convert the SOP to DOCX. "
            "Refusing to return empty text and pretend the protocol was read."
        ) from exc
    import PyPDF2
    reader = PyPDF2.PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def truncate_tokens(text: str, limit: int = DEFAULT_TOKEN_LIMIT) -> tuple[str, bool]:
    """(text, was_truncated). Whitespace tokens; close enough for a budget."""
    tokens = text.split()
    if len(tokens) <= limit:
        return text, False
    return " ".join(tokens[:limit]) + " ...[truncated]", True


def resolve_protocols(normalized, *, fetch_sop=None, fetch_blob=None,
                      nextseek_base_url: str,
                      token_limit: int = DEFAULT_TOKEN_LIMIT):
    """Resolve every discovered ref. Returns ({ref: record}, notes).

    Never gates output: with no fetcher, or on any fetch error, this returns
    what it could and explains the rest in `notes`, which the caller folds into
    the completeness report.
    """
    notes: list[str] = []
    resolved: dict[str, dict] = {}
    refs = find_protocol_refs(normalized)
    if not refs:
        return resolved, notes

    unique = sorted({r for group in refs.values() for r in group})
    if fetch_sop is None:
        notes.append(
            f"{len(unique)} protocol reference(s) not resolved: no NExtSEEK "
            f"connection was available. Protocol prose will be a placeholder.")
        return resolved, notes

    for ref in unique:
        sop_id = parse_sop_id(ref)
        try:
            record = fetch_sop(sop_id)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"protocol {ref}: fetch failed ({type(exc).__name__}: {exc})")
            continue
        if not record:
            notes.append(f"protocol {ref}: no such SOP")
            continue

        text_parts: list[str] = []
        for blob in record.get("content_blobs") or []:
            ctype = str(blob.get("content_type") or "").lower()
            url = resolve_host(str(blob.get("url") or ""),
                               nextseek_base_url=nextseek_base_url)
            if fetch_blob is None:
                notes.append(f"protocol {ref}: blob not downloaded (no fetcher)")
                continue
            try:
                data = fetch_blob(url)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"protocol {ref}: blob {url} failed "
                             f"({type(exc).__name__})")
                continue
            if any(ctype.startswith(t) for t in DOCX_CONTENT_TYPES):
                text_parts.append(extract_docx_text(data))
            elif any(ctype.startswith(t) for t in PDF_CONTENT_TYPES):
                try:
                    text_parts.append(extract_pdf_text(data))
                except PdfSupportError as exc:
                    notes.append(f"protocol {ref}: {exc}")
                except Exception as exc:  # noqa: BLE001 -- malformed PDF, PyPDF2 present; degrade, don't crash
                    notes.append(
                        f"protocol {ref}: PDF extraction failed "
                        f"({type(exc).__name__})")
            else:
                notes.append(f"protocol {ref}: unhandled content type {ctype!r}")

        joined, was_truncated = truncate_tokens("\n\n".join(
            p for p in text_parts if p), token_limit)
        if was_truncated:
            notes.append(f"protocol {ref}: text truncated at {token_limit} tokens")
        resolved[ref] = {"id": sop_id, "title": record.get("title", ""),
                         "text": joined, "truncated": was_truncated}
    return resolved, notes
