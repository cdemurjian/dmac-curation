#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests>=2.31",
#   "pandas>=2.0",
#   "openpyxl>=3.1",
#   "xlsxwriter>=3.1",
#   "rapidfuzz>=3.0",
#   "questionary>=2.0",
#   "rich>=13.0",
#   "python-dotenv>=1.0",
# ]
# ///
"""
submit.py — FairDOMHub Study Submission Tool
============================================
Run with:
    uv run submit.py

Walks you interactively through uploading a study to FairDOMHub:

  Step 0 — Config          : choose API user, study ID, project(s), workbook, suffix
  Step 1 — Assays          : review existing assays or create new ones
  Step 2 — Protocols       : fuzzy-match files → metadata names, assign assays, upload SOPs
  Step 3 — Metadata rewrite: replace protocol names with SOP links in workbook
  Step 4 — Sample types    : create from workbook sheets, assign assays interactively
  Step 5 — Samples         : bulk-create from workbook rows
  Done   — summary + next steps

Prerequisites before running:
  1. Create the Study manually via the FairDOMHub web UI and note its numeric ID.
  2. Populate Assets/Protocols/ with all protocol files (.pdf, .docx, etc.).
  3. Place your metadata workbook (.xlsx) in Assets/.
     - Each sheet = one Sample Type; each column = one attribute.
     - A column named "UID" is required — it becomes the record title.
  4. Create a .env file in this directory (copy .env.example and fill in your tokens).

After the script finishes:
  - All outputs are saved to Assets/Output/ as CSVs for your records.
  - Review the data on FairDOMHub, then publish manually via the web UI.
"""

# ── Standard library ──────────────────────────────────────────────────────────
import argparse
import ast
import concurrent.futures
import json
import mimetypes
import os
import re
import sys
import time
import typing as t
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# ── Third-party ───────────────────────────────────────────────────────────────
import pandas as pd
import questionary
import requests
from dotenv import load_dotenv
from rapidfuzz import process as fuzz_process
from rich.console import Console
from rich.table import Table

console = Console()

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://fairdomhub.org/"

# All known FairDOMHub projects for this lab. Add new entries here as needed.
# Keys are the numeric project ID strings used by the API.
PROJECT_MAPPING: Dict[str, str] = {
    "222": "Impact",
    "221": "SRP",
    "340": "MetNet",
    "343": "Endo-Griffith",
    "441": "CSBC",
}

OUTPUT_DIR = "Assets/Output"
SESSION_FILE = "Assets/Output/session.json"


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP UTILITIES
#
# These are the low-level building blocks for every API call.
# FairDOMHub uses the JSON:API spec (https://jsonapi.org/).
# Do not modify without testing against the live API.
# ═══════════════════════════════════════════════════════════════════════════════

def _headers(api_token: str) -> Dict:
    """Standard headers for JSON:API requests."""
    return {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _json_headers(api_token: str) -> Dict:
    """Alias for _headers; used where the distinction matters for clarity."""
    return {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _bin_headers(api_token: str) -> Dict:
    """Headers for binary file upload (Step 2 of the two-step SOP upload)."""
    return {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/octet-stream",
        "Accept": "application/json",
    }


def _post_jsonapi(
    base_url: str,
    path: str,
    api_token: str,
    payload: dict,
    max_retries: int = 5,
    backoff_factor: float = 2.0,
) -> dict:
    """
    POST to a JSON:API endpoint with exponential backoff for transient errors.

    Retries automatically on:
      429 — Too Many Requests (rate limit)
      502 — Bad Gateway
      503 — Service Unavailable

    Any other 4xx or 5xx is raised immediately without retry (e.g. 422
    Unprocessable Entity means your payload has a validation error — retrying
    won't help).
    """
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    attempt = 0
    while True:
        try:
            r = requests.post(url, json=payload, headers=_headers(api_token), timeout=60)
            if r.status_code >= 400:
                if r.status_code in (429, 502, 503) and attempt < max_retries:
                    wait = backoff_factor ** attempt
                    console.print(f"[yellow]⚠  Server busy ({r.status_code}). Retrying in {wait:.0f}s...[/yellow]")
                    time.sleep(wait)
                    attempt += 1
                    continue
                try:
                    console.print(f"[red]ERROR BODY:[/red] {r.json()}")
                except Exception:
                    console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
                r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = backoff_factor ** attempt
                console.print(f"[yellow]⚠  Request failed ({e}). Retrying in {wait:.0f}s...[/yellow]")
                time.sleep(wait)
                attempt += 1
            else:
                raise


def _patch_jsonapi(
    url: str,
    api_token: str,
    payload: dict,
    max_retries: int = 5,
    backoff_factor: float = 2.0,
) -> dict:
    """
    PATCH a JSON:API endpoint with exponential backoff for transient errors.
    url must be the full absolute URL.
    """
    attempt = 0
    while True:
        try:
            r = requests.patch(url, json=payload, headers=_headers(api_token), timeout=60)
            if r.status_code >= 400:
                if r.status_code in (429, 502, 503) and attempt < max_retries:
                    wait = backoff_factor ** attempt
                    console.print(f"[yellow]⚠  Server busy ({r.status_code}). Retrying in {wait:.0f}s...[/yellow]")
                    time.sleep(wait)
                    attempt += 1
                    continue
                try:
                    console.print(f"[red]ERROR BODY:[/red] {r.json()}")
                except Exception:
                    console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
                r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = backoff_factor ** attempt
                console.print(f"[yellow]⚠  Request failed ({e}). Retrying in {wait:.0f}s...[/yellow]")
                time.sleep(wait)
                attempt += 1
            else:
                raise


def _page_through(base_url: str, url: str, api_token: str) -> List[dict]:
    """
    Follow JSON:API pagination (links.next) and return all data items.
    Handles relative next-page URLs by resolving against base_url.
    """
    def _abs(u: str) -> str:
        return urljoin(base_url.rstrip("/") + "/", u) if not urlparse(u).scheme else u

    url = _abs(url)
    items: List[dict] = []
    while True:
        r = requests.get(url, headers=_headers(api_token), timeout=60)
        if r.status_code >= 400:
            try:
                console.print(f"[red]ERROR BODY:[/red] {r.json()}")
            except Exception:
                console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
            r.raise_for_status()
        payload = r.json()
        items.extend(payload.get("data") or [])
        nxt = (payload.get("links") or {}).get("next")
        if not nxt:
            break
        url = _abs(nxt)
    return items


# ═══════════════════════════════════════════════════════════════════════════════
# ASSAY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def create_assay(
    base_url: str,
    api_token: str,
    *,
    title: str,
    study_id: str,
    assay_class_key: str = "EXP",          # "EXP" = experimental, "MOD" = modelling
    assay_type_uri: Optional[str] = None,
    technology_type_uri: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Create a single assay inside a study.

    assay_class_key options:
      "EXP" — Experimental assay (default)
      "MOD" — Modelling analysis

    Returns the raw API response dict (use response["data"]["id"] for the assay ID).
    """
    attributes: dict = {
        "title": title,
        "assay_class": {"key": assay_class_key},
    }
    if description:
        attributes["description"] = description
    if assay_type_uri:
        attributes["assay_type"] = {"uri": assay_type_uri}
    if technology_type_uri:
        attributes["technology_type"] = {"uri": technology_type_uri}

    payload = {
        "data": {
            "type": "assays",
            "attributes": attributes,
            "relationships": {
                "study": {"data": {"id": str(study_id), "type": "studies"}}
            },
        }
    }
    return _post_jsonapi(base_url, "/assays", api_token, payload)


def bulk_create_assays_df(
    base_url: str,
    api_token: str,
    study_id: str,
    assay_names: List[str],
    return_responses: bool = False,
) -> Union[pd.DataFrame, Tuple[pd.DataFrame, List[Dict]]]:
    """
    Create multiple assays from a list of names.

    Returns a DataFrame with columns: assay_title, assay_id.
    If return_responses=True, also returns the raw API response list.
    """
    records, responses = [], []
    for name in assay_names:
        console.print(f"  Creating assay: [cyan]{name}[/cyan]")
        r = create_assay(base_url, api_token, title=name, study_id=study_id)
        records.append({
            "assay_title": r["data"]["attributes"]["title"],
            "assay_id": r["data"]["id"],
        })
        responses.append(r)
    df = pd.DataFrame(records)
    return (df, responses) if return_responses else df


def get_assays_for_study(base_url: str, api_token: str, study_id: str) -> pd.DataFrame:
    """
    Fetch all assays already linked to a study from the API.

    Returns a DataFrame with columns: assay_title, assay_id.
    Useful to review what already exists before creating new assays.
    """
    url = f"{base_url.rstrip('/')}/studies/{study_id}/assays"
    r = requests.get(url, headers=_headers(api_token), timeout=60)
    if r.status_code >= 400:
        try:
            console.print(f"[red]ERROR BODY:[/red] {r.json()}")
        except Exception:
            console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
        r.raise_for_status()
    records = [
        {"assay_title": item["attributes"].get("title", ""), "assay_id": item["id"]}
        for item in r.json().get("data", [])
    ]
    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════════════════════════
# PROTOCOL / SOP FUNCTIONS
#
# FairDOMHub uses a two-step upload for file assets (SOPs, data files, etc.):
#   Step 1: POST metadata to reserve a "content blob" slot → receive upload_link
#   Step 2: PUT the raw file bytes to that upload_link
# ═══════════════════════════════════════════════════════════════════════════════

def build_protocols_dataframe(base_dir: str = "Assets/Protocols") -> pd.DataFrame:
    """
    Scan the Protocols folder and return a DataFrame of files to upload.

    Columns: file_path | file_name (no extension) | assay_ids (empty list)

    assay_ids is populated interactively in the submission workflow before upload.
    """
    if not os.path.exists(base_dir):
        raise FileNotFoundError(f"Protocols folder not found: {base_dir}")
    records = []
    for fname in os.listdir(base_dir):
        fpath = os.path.join(base_dir, fname)
        if os.path.isfile(fpath):
            records.append({
                "file_path": fpath,
                "file_name": os.path.splitext(fname)[0],
                "assay_ids": [],
            })
    return pd.DataFrame(records)


def extract_unique_protocols(metadata_path: str) -> List[str]:
    """
    Parse every sheet in the metadata workbook, find any column named "Protocol",
    and collect all unique protocol name strings (split on ";" for multi-value cells).

    These names are what appear in the metadata and are what will be replaced with
    SOP links after upload.

    Uses a context manager to ensure the file handle is released immediately after
    reading, which is important on Windows where open handles block later writes.
    """
    with pd.ExcelFile(metadata_path) as xl:
        all_protocols: set = set()
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            if "Protocol" in df.columns:
                for val in df["Protocol"].dropna().unique():
                    for part in str(val).split(";"):
                        stripped = part.strip()
                        if stripped:
                            all_protocols.add(stripped)
    return sorted(all_protocols)


def fuzzy_match_protocols(
    protocols_df: pd.DataFrame,
    metadata_protocols: List[str],
    score_cutoff: int = 70,
) -> pd.DataFrame:
    """
    Match each file_name in protocols_df to the closest name in metadata_protocols
    using fuzzy string matching (rapidfuzz WRatio scorer via process.extractOne).

    WRatio is a weighted combination of several ratio strategies, making it
    robust to prefixes, suffixes, and word reordering — well-suited for matching
    bare filenames against protocol names that often include version prefixes.

    Adds columns:
      matched_protocol — the best metadata name match (or original filename if no match)
      match_score      — similarity score 0–100 (None if no match exceeded score_cutoff)

    Entries with score < 90 are surfaced as correction prompts in step_protocols.
    The score_cutoff parameter controls the minimum score to accept any match at all.
    """
    updated_names, match_scores = [], []
    for fname in protocols_df["file_name"]:
        result = fuzz_process.extractOne(fname, metadata_protocols, score_cutoff=score_cutoff)
        if result is not None:
            match, score, _ = result
            updated_names.append(match)
            match_scores.append(score)
        else:
            updated_names.append(fname)
            match_scores.append(None)
            console.print(f"[yellow]⚠  No good match found for:[/yellow] {fname}")
    df = protocols_df.copy()
    df["matched_protocol"] = updated_names
    df["match_score"] = match_scores
    return df


def create_sop_with_placeholder(
    base_url: str,
    api_token: str,
    *,
    title: str,
    project_ids: List[str],
    assay_ids: List[str],
    file_path: str,
    description: Optional[str] = None,
) -> Tuple[str, str, str, dict]:
    """
    Step 1 of 2-step SOP upload: POST metadata to /sops to reserve a blob slot.

    FairDOMHub creates the SOP record and returns an upload_link (a pre-signed
    PUT URL) where you must send the actual file bytes.

    Returns: (sop_id, upload_link, blob_id, full_response_dict)
    """
    fname = os.path.basename(file_path)
    ctype, _ = mimetypes.guess_type(fname)
    ctype = ctype or "application/octet-stream"

    attributes: dict = {
        "title": title,
        "content_blobs": [{"original_filename": fname, "content_type": ctype}],
    }
    if description:
        attributes["description"] = description

    relationships: dict = {
        "projects": {"data": [{"id": str(pid), "type": "projects"} for pid in project_ids]}
    }
    if assay_ids:
        relationships["assays"] = {
            "data": [{"id": str(aid), "type": "assays"} for aid in assay_ids]
        }

    payload = {"data": {"type": "sops", "attributes": attributes, "relationships": relationships}}

    r = requests.post(
        f"{base_url.rstrip('/')}/sops",
        headers=_json_headers(api_token),
        json=payload,
        timeout=120,
    )
    if r.status_code >= 400:
        try:
            console.print(f"[red]ERROR BODY:[/red] {r.json()}")
        except Exception:
            console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
        r.raise_for_status()

    resp = r.json()
    sop_id = resp["data"]["id"]
    blob_info = resp["data"]["attributes"]["content_blobs"][0]
    upload_link = blob_info.get("link", "")
    parsed = urlparse(upload_link)
    blob_id = parsed.path.rstrip("/").split("/")[-1]

    # Ensure upload_link is absolute (API sometimes returns a relative path)
    if not parsed.scheme:
        upload_link = urljoin(base_url.rstrip("/") + "/", upload_link.lstrip("/"))

    return sop_id, upload_link, blob_id, resp


def upload_sop_binary_with_retry(
    upload_url: str,
    api_token: str,
    file_path: str,
    max_retries: int = 5,
    backoff: int = 10,
) -> dict:
    """
    Step 2 of 2-step SOP upload: PUT the raw file bytes to the blob URL.

    Uses exponential backoff: wait = backoff * 2^attempt seconds between retries.
    Raises RuntimeError after max_retries exhausted.
    """
    for attempt in range(max_retries):
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            r = requests.put(upload_url, headers=_bin_headers(api_token), data=data, timeout=300)
            if r.status_code >= 400:
                try:
                    console.print(f"[red]ERROR BODY:[/red] {r.json()}")
                except Exception:
                    console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
                r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = backoff * (2 ** attempt)
            console.print(
                f"[yellow]⚠  Upload failed (attempt {attempt + 1}/{max_retries}): {e}. "
                f"Retrying in {wait}s...[/yellow]"
            )
            time.sleep(wait)
    raise RuntimeError(f"Failed to upload {file_path} after {max_retries} retries.")


def upload_protocols_df(
    base_url: str,
    api_token: str,
    project_ids: List[str],
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Iterate over a protocols DataFrame and upload each file as an SOP.

    Adds columns to the DataFrame: sop_id, sop_link, blob_id.
    Failed uploads are logged but do not halt the loop — check for null sop_id rows.
    """
    df = df.copy()
    df["sop_id"] = None
    df["sop_link"] = None
    df["blob_id"] = None

    for idx, row in df.iterrows():
        file_path = row["file_path"]
        title = row["matched_protocol"]
        assay_ids = row["assay_ids"] if isinstance(row["assay_ids"], list) else []

        console.print(f"  ⬆  [cyan]{title}[/cyan]  ({os.path.basename(file_path)})")
        try:
            sop_id, upload_url, blob_id, _ = create_sop_with_placeholder(
                base_url, api_token,
                title=title,
                project_ids=project_ids,
                assay_ids=assay_ids,
                file_path=file_path,
            )
            upload_sop_binary_with_retry(upload_url, api_token, file_path)
            df.at[idx, "sop_id"] = sop_id
            df.at[idx, "sop_link"] = f"{base_url.rstrip('/')}/sops/{sop_id}"
            df.at[idx, "blob_id"] = blob_id
            console.print(f"  [green]✓ SOP {sop_id}[/green] → {df.at[idx, 'sop_link']}")
        except Exception as e:
            console.print(f"  [red]✗ Failed for {file_path}: {e}[/red]")

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# METADATA REWRITE
# ═══════════════════════════════════════════════════════════════════════════════

def replace_anywhere_in_metadata(
    metadata_path: str,
    uploaded_protocols_csv: str,
    output_path: str,
) -> None:
    """
    Globally replace protocol name strings with their SOP URLs across all cells
    in all sheets of the metadata workbook.

    Safe to use with output_path == metadata_path (in-place update). The read
    phase uses a context manager so the openpyxl file handle is fully released
    before xlsxwriter opens the same path for writing — on Windows, an open
    handle on the source file causes a "file cannot be saved" / PermissionError.

    The replacement uses a single compiled regex that matches all protocol names
    at once (longest match wins), so partial overlaps are handled correctly.
    Only string-typed cells are touched; numbers, dates, and NaN are left alone.
    """
    uploaded_df = pd.read_csv(uploaded_protocols_csv)
    uploaded_df = uploaded_df.dropna(subset=["matched_protocol", "sop_link"]).copy()
    uploaded_df["matched_protocol"] = uploaded_df["matched_protocol"].astype(str)
    uploaded_df["sop_link"] = uploaded_df["sop_link"].astype(str)
    mapping = dict(zip(uploaded_df["matched_protocol"], uploaded_df["sop_link"]))

    if not mapping:
        console.print("[yellow]⚠  No replacements found (mapping is empty). Skipping.[/yellow]")
        return

    # Sort by length descending so longer keys are matched first
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))

    def repl(match: re.Match) -> str:
        """Return the SOP link that corresponds to the matched protocol name."""
        return mapping[match.group(0)]

    # ── Read phase: close the file handle before writing ─────────────────────
    # Using `with` here is critical on Windows: pd.ExcelFile holds a file lock
    # and xlsxwriter cannot overwrite the same path while it is open.
    sheets_out = {}
    with pd.ExcelFile(metadata_path, engine="openpyxl") as xls:
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df = df.map(lambda v: pattern.sub(repl, v) if isinstance(v, str) else v)
            sheets_out[sheet] = df
    # xls handle is now fully closed — safe to write to the same path

    # ── Write phase ──────────────────────────────────────────────────────────
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        for sheet, df in sheets_out.items():
            df.to_excel(writer, sheet_name=sheet, index=False)

    console.print(f"[green]✓ Replacements written to:[/green] {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLE TYPE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Regex to detect URLs and DOIs — used to auto-classify columns as URI vs Text
_URL_RX = re.compile(r"(https?://|ftp://|doi:)", re.IGNORECASE)


def column_is_all_links(series: pd.Series) -> bool:
    """
    Return True only if every non-null, non-empty cell in the Series is a
    single valid URL or DOI. Used to decide whether a sample attribute should
    be typed "URI" or "Text" on FairDOMHub.

    Returns False if:
      - Any cell is blank or NaN
      - Any cell contains a non-URL value
      - Any cell is a mix of URL and non-URL text

    Raises ValueError if a cell contains multiple semicolon-separated URLs —
    the FairDOMHub API does not accept multi-value URI attributes.
    """
    values = series.astype(str).str.strip()
    if values.isna().any() or any(v == "" for v in values):
        return False
    for v in values:
        if ";" in v:
            parts = [p.strip() for p in v.split(";") if p.strip()]
            if len(parts) > 1 and all(_URL_RX.search(p) for p in parts):
                raise ValueError(f"Multiple semicolon-separated links in one cell: '{v}'")
            return False
        if not _URL_RX.search(v):
            return False
    return True


def get_sample_attribute_type_ids(
    base_url: str,
    api_token: str,
    wanted: tuple = ("Text", "URI"),
) -> Dict[str, str]:
    """
    Fetch attribute type IDs from the API (e.g. "Text" → "7", "URI" → "14").

    Falls back to known spec defaults if the request fails, so this is safe
    to call without a network connection.
    """
    url = f"{base_url.rstrip('/')}/sample_attribute_types?page[size]=1000"
    title_to_id: Dict[str, str] = {}
    try:
        r = requests.get(url, headers=_headers(api_token), timeout=60)
        r.raise_for_status()
        for item in r.json().get("data", []):
            title = item.get("attributes", {}).get("title")
            _id = item.get("id")
            if title in wanted and _id:
                title_to_id[title] = str(_id)
    except Exception:
        pass
    title_to_id.setdefault("Text", "7")
    title_to_id.setdefault("URI", "14")
    return title_to_id


def build_sample_type_payload(
    sheet_name: str,
    title_suffix: str,
    df: pd.DataFrame,
    project_ids: List[str],
    attr_type_ids: Dict[str, str],
) -> dict:
    """
    Build the JSON:API payload for creating a SampleType from one workbook sheet.

    Each DataFrame column becomes a sample attribute. Column-level rules:
      - "UID" column → required=True, is_title=True (the record's display name)
      - Columns where every non-null cell is a URL/DOI → type "URI"
      - All other columns → type "Text"

    The SampleType title is "<sheet_name> - <title_suffix>".

    Raises ValueError (propagated from column_is_all_links) if any cell in a
    URI-candidate column contains multiple semicolon-separated URLs — the API
    does not support multi-value URI attributes.
    """
    sample_attributes = []
    for i, col in enumerate(df.columns, start=1):
        attr_title = str(col)
        is_uri = column_is_all_links(df[col])
        type_title = "URI" if is_uri else "Text"
        type_id = attr_type_ids.get(type_title)
        is_uid = attr_title.strip().lower() == "uid"
        sample_attributes.append({
            "title": attr_title,
            "sample_attribute_type": (
                {"id": str(type_id)} if type_id else {"title": type_title}
            ),
            "required": bool(is_uid),
            "pos": i,
            "is_title": bool(is_uid),
        })

    st_title = f"{sheet_name} - {title_suffix}".strip(" -")
    return {
        "data": {
            "type": "sample_types",
            "attributes": {
                "title": st_title,
                "sample_attributes": sample_attributes,
            },
            "relationships": {
                "projects": {
                    "data": [{"id": str(pid), "type": "projects"} for pid in project_ids]
                }
            },
        }
    }


def create_sample_type(
    base_url: str,
    api_token: str,
    payload: dict,
    max_retries: int = 5,
    backoff_seconds: int = 5,
) -> dict:
    """POST /sample_types with exponential backoff for transient errors."""
    url = f"{base_url.rstrip('/')}/sample_types"
    attempt = 0
    while True:
        try:
            r = requests.post(url, headers=_json_headers(api_token), json=payload, timeout=120)
            if r.status_code >= 400:
                try:
                    console.print(f"[red]ERROR BODY:[/red] {r.json()}")
                except Exception:
                    console.print(f"[red]ERROR BODY (text):[/red] {r.text}")
                if r.status_code in (429, 500, 502, 503) and attempt < max_retries:
                    wait = backoff_seconds * (2 ** attempt)
                    console.print(f"[yellow]⚠  Server {r.status_code}. Retrying in {wait}s...[/yellow]")
                    time.sleep(wait)
                    attempt += 1
                    continue
                r.raise_for_status()
            resp = r.json()
            st_id = resp["data"]["id"]
            st_title = resp["data"]["attributes"]["title"]
            console.print(f"  [green]✓ SampleType {st_id}[/green]: {st_title}")
            return resp
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = backoff_seconds * (2 ** attempt)
                console.print(f"[yellow]⚠  Network error: {e}. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
                attempt += 1
            else:
                raise


def create_sample_types_from_workbook(
    base_url: str,
    api_token: str,
    project_ids: List[str],
    xlsx_path: str,
    title_suffix: str,
) -> pd.DataFrame:
    """
    Read each sheet in the workbook and create a SampleType for it.

    Returns a DataFrame with columns:
      sheet_name | sample_type_id | title | link | assay_ids (empty list)

    The assay_ids column starts empty — it is populated in the interactive
    assignment step that follows (step_sample_types).

    Uses a context manager on pd.ExcelFile to release the file handle before
    any downstream writes, preventing Windows file lock errors.
    """
    type_ids = get_sample_attribute_type_ids(base_url, api_token)
    with pd.ExcelFile(xlsx_path) as xls:
        sheet_names = xls.sheet_names
    rows = []
    for sheet in sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
        if df.shape[1] == 0:
            console.print(f"[yellow]⚠  Sheet '{sheet}' has no columns; skipping.[/yellow]")
            continue
        console.print(f"\n  Sheet [cyan]{sheet}[/cyan]")
        payload = build_sample_type_payload(sheet, title_suffix, df, project_ids, type_ids)
        resp = create_sample_type(base_url, api_token, payload)
        st_id = resp["data"]["id"]
        rows.append({
            "sheet_name": sheet,
            "sample_type_id": st_id,
            "title": resp["data"]["attributes"]["title"],
            "link": f"{base_url.rstrip('/')}/sample_types/{st_id}",
            "assay_ids": [],
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_cell(val) -> Optional[str]:
    """Return a trimmed string, or None if the cell is empty/NaN."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def build_sample_payload(
    row: pd.Series,
    sample_type_id: str,
    project_ids: List[str],
    assay_ids: Optional[List[str]] = None,
) -> dict:
    """
    Build the JSON:API payload for a single Sample row.

    Title is taken from the "UID" column if present; falls back to the first
    non-null value, then "Sample_<row_index>".

    Known URI fields (Link_PrimaryData, Protocol) are silently dropped if their
    value does not start with "http" — the API returns a 422 for non-URL values
    in URI-typed attributes.

    All empty/NaN cells are excluded from attribute_map.
    """
    attr_map: Dict[str, str] = {}
    for col, val in row.items():
        key = str(col).strip()
        cleaned = _clean_cell(val)
        if cleaned is None:
            continue
        # URI-typed fields must be valid URLs; skip non-URLs silently
        if key in ("Link_PrimaryData", "Protocol") and not cleaned.lower().startswith("http"):
            continue
        attr_map[key] = cleaned

    # Determine the sample's display title
    title_val: Optional[str] = None
    if "UID" in row.index:
        title_val = _clean_cell(row["UID"])
    if title_val is None:
        for v in row.values:
            title_val = _clean_cell(v)
            if title_val:
                break
    if title_val is None:
        title_val = f"Sample_{row.name}"

    payload: dict = {
        "data": {
            "type": "samples",
            "attributes": {"title": title_val, "attribute_map": attr_map},
            "relationships": {
                "sample_type": {"data": {"id": str(sample_type_id), "type": "sample_types"}},
                "projects": {
                    "data": [{"id": str(pid), "type": "projects"} for pid in project_ids]
                },
            },
        }
    }
    if assay_ids:
        payload["data"]["relationships"]["assays"] = {
            "data": [
                {"id": str(aid).strip(), "type": "assays"}
                for aid in assay_ids
                if str(aid).strip()
            ]
        }
    return payload


def create_sample(
    base_url: str,
    api_token: str,
    payload: dict,
    max_retries: int = 5,
    backoff_seconds: int = 5,
) -> dict:
    """
    POST /samples with retries for transient server errors.

    422 Unprocessable Entity is raised immediately — it means the attribute_map
    contains invalid data (wrong type, missing required field, etc.).
    Check the ERROR BODY printed above the exception for details.
    """
    url = f"{base_url.rstrip('/')}/samples"
    attempt = 0
    while True:
        try:
            r = requests.post(url, headers=_json_headers(api_token), json=payload, timeout=120)
            if r.status_code >= 400:
                try:
                    console.print(f"[red]ERROR BODY:[/red] {r.json()}")
                except Exception:
                    console.print(f"[red]ERROR BODY (text):[/red] {r.text[:2000]}")
                if r.status_code in (429, 500, 502, 503) and attempt < max_retries:
                    wait = backoff_seconds * (2 ** attempt)
                    console.print(f"[yellow]⚠  Server {r.status_code}. Retrying in {wait}s...[/yellow]")
                    time.sleep(wait)
                    attempt += 1
                    continue
                r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = backoff_seconds * (2 ** attempt)
                console.print(f"[yellow]⚠  Network error: {e}. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
                attempt += 1
            else:
                raise


def create_samples_from_workbook(
    base_url: str,
    api_token: str,
    project_ids: List[str],
    xlsx_path: str,
    summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create one Sample per data row across all sheets in the workbook.

    Uses summary_df (produced by create_sample_types_from_workbook) to look up
    the sample_type_id and assay_ids for each sheet.

    Returns a DataFrame with columns: sheet | uid | sample_id | link.
    Sheets not present in summary_df are skipped with a warning.

    Uses a context manager on pd.ExcelFile to release the file handle immediately
    after reading the sheet list, preventing Windows file lock errors on subsequent
    per-sheet reads.
    """
    with pd.ExcelFile(xlsx_path) as xls:
        sheet_names = xls.sheet_names
    rows = []
    for sheet in sheet_names:
        if sheet not in summary_df["sheet_name"].values:
            console.print(f"[yellow]⚠  Sheet '{sheet}' not in summary; skipping.[/yellow]")
            continue

        st_row = summary_df.loc[summary_df["sheet_name"] == sheet].iloc[0]
        st_id = str(st_row["sample_type_id"])

        # Parse assay_ids from whatever format they were stored in (list, CSV repr, etc.)
        assay_ids: List[str] = (
            _parse_assay_ids(st_row["assay_ids"])
            if "assay_ids" in summary_df.columns
            else []
        )

        df = pd.read_excel(xlsx_path, sheet_name=sheet).dropna(how="all")
        console.print(
            f"\n  Sheet [cyan]{sheet}[/cyan] → {len(df)} samples "
            f"(SampleType {st_id}, assays={assay_ids})"
        )

        for _, row in df.iterrows():
            if row.isna().all():
                continue
            payload = build_sample_payload(row, st_id, project_ids, assay_ids)
            title_val = payload["data"]["attributes"]["title"]
            console.print(f"    ⬆  {title_val}")
            resp = create_sample(base_url, api_token, payload)
            sample_id = resp["data"]["id"]
            rows.append({
                "sheet": sheet,
                "uid": title_val,
                "sample_id": sample_id,
                "link": f"{base_url.rstrip('/')}/samples/{sample_id}",
            })
            console.print(f"    [green]✓ {sample_id}[/green]")

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLISH / PERMISSIONS
#
# Step 6: batch-set policy on all assets in a study so they become publicly
# visible on FairDOMHub.  Uses PATCH /{resource_type}/{id} with a policy block.
#
# Access levels accepted by the API:
#   "view"     — public can see metadata only
#   "download" — public can also download files
#
# The study itself is NOT published here — do that manually via the web UI
# after reviewing, as noted in the workflow summary.
# ═══════════════════════════════════════════════════════════════════════════════

# Resource types we attempt to publish.  "sample_types" are included because
# this tool creates them; the notebook did not need them.
_PUBLISHABLE_TYPES = ["assays", "sops", "sample_types", "samples", "data_files",
                      "models", "presentations", "publications"]


def collect_study_assets(
    base_url: str,
    api_token: str,
    study_id: str,
) -> Dict[str, List[str]]:
    """
    Discover all asset IDs linked to a study.

    Strategy (mirrors the notebook approach):
      1. Fetch study relationships and try links.related for each asset type.
      2. Fall back to inline relationships.data arrays.
      3. Recurse into each assay to pick up nested data_files and samples
         (these often only appear at the assay level, not the study level).

    Returns a dict mapping resource_type → list of ID strings.
    """
    study_url = f"{base_url.rstrip('/')}/studies/{study_id}"
    r = requests.get(study_url, headers=_headers(api_token), timeout=60)
    r.raise_for_status()
    study = r.json()

    data = study.get("data") or {}
    rels = data.get("relationships") or {}

    targets: Dict[str, List[str]] = {t: [] for t in _PUBLISHABLE_TYPES}

    # Pass 1 — links.related (paginated)
    for typ in targets:
        rel = rels.get(typ) or {}
        related = (rel.get("links") or {}).get("related")
        if related:
            ids = [x["id"] for x in _page_through(base_url, related, api_token)]
            targets[typ] = ids
            if ids:
                console.print(f"  [dim]{typ}:[/dim] {len(ids)} via links.related")

    # Pass 2 — inline relationships.data
    for typ in targets:
        if not targets[typ]:
            rel = rels.get(typ) or {}
            rel_data = rel.get("data")
            if isinstance(rel_data, dict):
                targets[typ] = [rel_data["id"]]
            elif isinstance(rel_data, list):
                targets[typ] = [x["id"] for x in rel_data if isinstance(x, dict)]
            if targets[typ]:
                console.print(f"  [dim]{typ}:[/dim] {len(targets[typ])} via relationships.data")

    # Pass 3 — recurse into assays for nested data_files + samples
    nested_files: List[str] = []
    nested_samples: List[str] = []
    for a_id in targets.get("assays", []):
        a_url = f"{base_url.rstrip('/')}/assays/{a_id}"
        ar = requests.get(a_url, headers=_headers(api_token), timeout=60)
        if ar.status_code >= 400:
            continue
        a_rels = (ar.json().get("data") or {}).get("relationships") or {}

        df_related = ((a_rels.get("data_files") or {}).get("links") or {}).get("related")
        if df_related:
            nested_files.extend(x["id"] for x in _page_through(base_url, df_related, api_token))

        s_related = ((a_rels.get("samples") or {}).get("links") or {}).get("related")
        if s_related:
            nested_samples.extend(x["id"] for x in _page_through(base_url, s_related, api_token))

        # Also check inline arrays
        for key, bucket in (("data_files", nested_files), ("samples", nested_samples)):
            rel_data = (a_rels.get(key) or {}).get("data")
            if isinstance(rel_data, list):
                bucket.extend(x["id"] for x in rel_data if isinstance(x, dict))

    if nested_files:
        targets["data_files"] = sorted(set(targets["data_files"] + nested_files))
    if nested_samples:
        targets["samples"] = sorted(set(targets["samples"] + nested_samples))

    return targets


def publish_resource(
    base_url: str,
    api_token: str,
    resource_type: str,
    rid: str,
    project_id: str,
    access_level: str = "view",
) -> dict:
    """
    PATCH a single resource to set its policy to public.

    policy.access controls public visibility:
      "view"     — public can read metadata
      "download" — public can also download attached files

    The project permission entry keeps project owners' manage access intact.
    """
    url = f"{base_url.rstrip('/')}/{resource_type}/{rid}"
    payload = {
        "data": {
            "type": resource_type,
            "id": str(rid),
            "attributes": {
                "policy": {
                    "access": access_level,
                    "permissions": [
                        {
                            "resource": {"id": str(project_id), "type": "projects"},
                            "access": "manage",
                        }
                    ],
                }
            },
        }
    }
    return _patch_jsonapi(url, api_token, payload)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _print_table(df: pd.DataFrame, title: str = "") -> None:
    """Render a DataFrame as a Rich table in the terminal."""
    table = Table(title=title, show_lines=True)
    for col in df.columns:
        table.add_column(str(col))
    for _, row in df.iterrows():
        table.add_row(*[str(v) for v in row.values])
    console.print(table)


def _pick_assays(
    prompt: str,
    df_assays: pd.DataFrame,
    preselected=None,
) -> List[str]:
    """
    Show a checkbox prompt listing all available assays.
    Returns a list of the selected assay_id strings (may be empty).

    preselected: assay_ids to pre-check (any format accepted by _parse_assay_ids).
    Used when re-assigning assays to sample types that already have some — so a
    re-run starts from the current selection instead of a blank slate.
    """
    if df_assays.empty:
        return []
    pre = set(_parse_assay_ids(preselected)) if preselected is not None else set()
    choices = [
        questionary.Choice(
            title=f"{row.assay_id} – {row.assay_title}",
            value=str(row.assay_id),
            checked=str(row.assay_id) in pre,
        )
        for _, row in df_assays.iterrows()
    ]
    selected = questionary.checkbox(prompt, choices=choices).ask()
    return selected or []


def _parse_assay_ids(val) -> List[str]:
    """
    Parse an assay_ids value into a flat list of ID strings, regardless of source.

    Handles all formats that can appear across the workflow:
      - Python list (in-memory):         ['2809', '2810']  →  ['2809', '2810']
      - Python list repr from CSV:       "['2809', '2810']" →  ['2809', '2810']
      - Plain comma-separated from CSV:  "2809, 2810"       →  ['2809', '2810']
      - Single value:                    "2816"             →  ['2816']
      - Empty / NaN:                     ""  or  NaN        →  []

    This normalises the inconsistency between how pandas serialises Python lists
    to CSV (with brackets and quotes) vs how manually-edited CSVs look (plain
    comma-separated). Always use this function when reading assay_ids from a CSV.
    """
    if isinstance(val, list):
        return [str(a).strip() for a in val if str(a).strip()]
    if pd.isna(val) or str(val).strip() in ("", "nan", "[]"):
        return []
    s = str(val).strip()
    # Handle Python list repr: "['2809', '2810']" or "[2809, 2810]"
    if s.startswith("["):
        try:
            parsed = ast.literal_eval(s)
            return [str(a).strip() for a in parsed if str(a).strip()]
        except (ValueError, SyntaxError):
            pass
    # Plain comma-separated: "2809, 2810" or single "2816"
    return [x.strip() for x in s.split(",") if x.strip()]


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION PERSISTENCE
#
# Saves config + last completed step so --resume can pick up where you left off.
# The token is stored in plain text — session.json should not be committed.
# ═══════════════════════════════════════════════════════════════════════════════

def _save_session(cfg: dict, last_completed_step: int) -> None:
    """Write cfg and last_completed_step to SESSION_FILE."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = {**cfg, "last_completed_step": last_completed_step}
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _load_session() -> Tuple[dict, int]:
    """
    Load a saved session from SESSION_FILE.

    Returns (cfg, start_step) where start_step = last_completed_step + 1.
    Exits with a clear error if no session file exists.
    """
    if not os.path.exists(SESSION_FILE):
        console.print(
            f"[red]No session file found at {SESSION_FILE}.\n"
            f"Run without --resume first to create one.[/red]"
        )
        sys.exit(1)
    with open(SESSION_FILE) as f:
        data = json.load(f)
    last = data.pop("last_completed_step", 0)
    cfg = data
    start_step = last + 1
    console.print(
        f"[dim]Loaded session from {SESSION_FILE} "
        f"(last completed: step {last} → resuming from step {start_step})[/dim]"
    )
    return cfg, start_step


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW STEPS
# ═══════════════════════════════════════════════════════════════════════════════

def step_config() -> dict:
    """
    Step 0: Collect all per-run configuration interactively.

    Reads FDH_API from .env — a JSON object mapping username strings to API
    token strings, e.g.:
        FDH_API={"alice": "token_aaa", "bob": "token_bbb"}

    Returns a config dict:
        api_token  — the selected user's token
        study_id   — FairDOMHub study ID string
        project_id — list of project ID strings
        workbook   — path to the .xlsx metadata file
        suffix     — sample type name suffix
    """
    console.rule("[bold blue]Step 0: Configuration[/bold blue]")

    # ── Load .env and parse FDH_API ───────────────────────────────────────────
    load_dotenv()
    fdh_api_raw = os.environ.get("FDH_API", "")
    if not fdh_api_raw:
        console.print("[red]FDH_API not set in .env — see .env.example for the format.[/red]")
        sys.exit(1)
    try:
        user_tokens: Dict[str, str] = json.loads(fdh_api_raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]FDH_API is not valid JSON: {e}[/red]")
        sys.exit(1)
    if not user_tokens:
        console.print("[red]FDH_API JSON is empty.[/red]")
        sys.exit(1)

    # ── Select which user's token to use ──────────────────────────────────────
    username = questionary.select(
        "Select API user:",
        choices=list(user_tokens.keys()),
    ).ask()
    api_token = user_tokens[username]
    console.print(f"  Authenticated as [bold]{username}[/bold]")

    # ── Study ID ──────────────────────────────────────────────────────────────
    study_id = questionary.text("Study ID (numeric, from the FairDOMHub URL):").ask().strip()

    # ── Project(s) ────────────────────────────────────────────────────────────
    manual_project_choice = "__manual_project_id__"
    project_choices = [
        questionary.Choice(title=f"{pid} – {name}", value=pid)
        for pid, name in PROJECT_MAPPING.items()
    ]
    project_choices.append(
        questionary.Choice(title="Enter project ID manually", value=manual_project_choice)
    )
    project_id: List[str] = (
        questionary.checkbox("Select project(s):", choices=project_choices).ask() or []
    )
    if manual_project_choice in project_id:
        project_id.remove(manual_project_choice)
        while True:
            manual_project_id = (
                questionary.text("Enter project ID (numeric):").ask() or ""
            ).strip()
            if manual_project_id.isdigit():
                if manual_project_id not in project_id:
                    project_id.append(manual_project_id)
                break
            console.print("[red]Project ID must be numeric.[/red]")

    if not project_id:
        console.print("[red]No projects selected. Exiting.[/red]")
        sys.exit(1)

    # ── Metadata workbook ─────────────────────────────────────────────────────
    workbook = questionary.path(
        "Path to metadata workbook (.xlsx):",
        default="Assets/",
    ).ask().strip()
    if not os.path.exists(workbook):
        console.print(f"[red]Workbook not found: {workbook}[/red]")
        sys.exit(1)

    # ── Sample type suffix ────────────────────────────────────────────────────
    suffix = questionary.text(
        "Sample type suffix (appended to each sheet name, e.g. 'MM'):",
    ).ask().strip()

    cfg = {
        "api_token": api_token,
        "study_id": study_id,
        "project_id": project_id,
        "workbook": workbook,
        "suffix": suffix,
    }

    console.print("\n[bold]Config summary:[/bold]")
    for k, v in cfg.items():
        display = "[dim]**********[/dim]" if k == "api_token" else f"[cyan]{v}[/cyan]"
        console.print(f"  {k}: {display}")

    _save_session(cfg, 0)
    return cfg


def step_assays(cfg: dict) -> pd.DataFrame:
    """
    Step 1: Review existing assays for the study and optionally create new ones.

    Always fetches the current list from the API so you see the live state.
    New assays are entered one per line in a multiline prompt.

    Returns the final assay DataFrame (assay_title, assay_id).
    """
    console.rule("[bold blue]Step 1: Assays[/bold blue]")

    df_assays = get_assays_for_study(BASE_URL, cfg["api_token"], cfg["study_id"])
    if not df_assays.empty:
        _print_table(df_assays, title=f"Existing assays in study {cfg['study_id']}")
    else:
        console.print("  No assays found in this study yet.")

    if questionary.confirm("Create new assays?", default=False).ask():
        raw = questionary.text(
            "Enter assay names — one per line. Leave blank and press Enter when done:",
            multiline=True,
        ).ask()
        names = [n.strip() for n in (raw or "").splitlines() if n.strip()]
        if names:
            console.print(f"\nCreating {len(names)} assay(s)...")
            new_df = bulk_create_assays_df(BASE_URL, cfg["api_token"], cfg["study_id"], names)
            df_assays = pd.concat([df_assays, new_df], ignore_index=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "assays_from_study.csv")
    df_assays.to_csv(out_path, index=False)
    console.print(f"\n[green]✓ Saved:[/green] {out_path}")
    return df_assays


def step_protocols(cfg: dict, df_assays: pd.DataFrame) -> pd.DataFrame:
    """
    Step 2: Upload protocol files as SOPs.

    Workflow:
      1. Scan Assets/Protocols/ for files.
      2. Extract protocol names from the metadata workbook's "Protocol" columns.
      3. Fuzzy-match filenames → metadata names (show results table).
      4. Prompt to correct any low-confidence matches (score < 90).
      5. For each protocol, select which assays it belongs to.
      6. Upload all SOPs (two-step: reserve blob → PUT bytes).

    Saves two CSVs:
      protocols_preupload.csv  — after matching/assignment, before upload
      protocols_uploaded.csv   — after upload (includes sop_id, sop_link)
    """
    console.rule("[bold blue]Step 2: Protocols[/bold blue]")

    protocols_df = build_protocols_dataframe("Assets/Protocols")
    metadata_protocols = extract_unique_protocols(cfg["workbook"])

    console.print(
        f"\nFound [cyan]{len(protocols_df)}[/cyan] protocol files  |  "
        f"[cyan]{len(metadata_protocols)}[/cyan] unique protocol names in workbook."
    )

    protocols_df = fuzzy_match_protocols(protocols_df, metadata_protocols, score_cutoff=75)
    _print_table(
        protocols_df[["file_name", "matched_protocol", "match_score"]],
        title="Fuzzy match results (review before confirming)",
    )

    # Allow correction of low-confidence or unmatched entries
    for idx, row in protocols_df.iterrows():
        score = row["match_score"]
        if score is None or score < 90:
            keep = questionary.confirm(
                f"  '{row['file_name']}'\n"
                f"  matched to: '{row['matched_protocol']}' (score={score})\n"
                f"  Keep this match?",
                default=True,
            ).ask()
            if not keep:
                new_name = questionary.text(
                    "  Enter the correct protocol name:",
                    default=row["matched_protocol"],
                ).ask()
                protocols_df.at[idx, "matched_protocol"] = new_name.strip()

    # Interactively assign assays
    console.print("\n[bold]Assign assays to each protocol[/bold]  (space = select, enter = confirm)\n")
    for idx, row in protocols_df.iterrows():
        selected_ids = _pick_assays(
            f"Assays for  '{row['matched_protocol']}':",
            df_assays,
        )
        protocols_df.at[idx, "assay_ids"] = selected_ids

    # Save pre-upload snapshot
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pre_path = os.path.join(OUTPUT_DIR, "protocols_preupload.csv")
    protocols_df.to_csv(pre_path, index=False)
    console.print(f"\n[green]✓ Pre-upload snapshot saved:[/green] {pre_path}")

    if not questionary.confirm("\nUpload protocols to FairDOMHub now?", default=True).ask():
        console.print("[yellow]Protocol upload skipped.[/yellow]")
        return protocols_df

    uploaded_df = upload_protocols_df(BASE_URL, cfg["api_token"], cfg["project_id"], protocols_df)
    post_path = os.path.join(OUTPUT_DIR, "protocols_uploaded.csv")
    uploaded_df.to_csv(post_path, index=False)
    console.print(f"\n[green]✓ Uploaded protocols saved:[/green] {post_path}")
    return uploaded_df


def step_metadata_rewrite(cfg: dict) -> None:
    """
    Step 3: Replace protocol name strings in the workbook with SOP URLs.

    Reads the mapping from Assets/Output/protocols_uploaded.csv and overwrites
    cfg["workbook"] in-place. Run this after protocols are uploaded.
    """
    console.rule("[bold blue]Step 3: Metadata Rewrite[/bold blue]")

    uploaded_csv = os.path.join(OUTPUT_DIR, "protocols_uploaded.csv")
    if not os.path.exists(uploaded_csv):
        console.print(f"[yellow]⚠  {uploaded_csv} not found. Skipping metadata rewrite.[/yellow]")
        return

    if not questionary.confirm(
        f"Replace protocol names with SOP links in '{cfg['workbook']}'?",
        default=True,
    ).ask():
        console.print("[yellow]Skipped.[/yellow]")
        return

    replace_anywhere_in_metadata(cfg["workbook"], uploaded_csv, cfg["workbook"])


def _reuse_existing_sample_types(cfg: dict) -> Optional[pd.DataFrame]:
    """
    Offer to reuse sample types recorded in a previous Step 4 run instead of
    creating them again.

    Returns the loaded summary DataFrame if the user opts to reuse, else None
    (meaning the caller should create sample types fresh).

    Only offers reuse when Assets/Output/sample_types_created.csv exists AND its
    sheet_name set is a subset of the current workbook's sheets — i.e. the CSV
    describes THIS workbook, not a different one from the "process another
    workbook" loop. This prevents duplicate SampleType resources when a run is
    resumed after the assay-assignment step was cancelled.
    """
    path = os.path.join(OUTPUT_DIR, "sample_types_created.csv")
    if not os.path.exists(path):
        return None
    try:
        existing = _load_summary_from_csv()
    except Exception:
        return None
    if existing.empty or "sheet_name" not in existing.columns:
        return None

    with pd.ExcelFile(cfg["workbook"]) as xls:
        wb_sheets = set(xls.sheet_names)
    csv_sheets = set(existing["sheet_name"].astype(str))
    if not csv_sheets or not csv_sheets <= wb_sheets:
        # CSV describes a different workbook — don't offer to reuse it.
        return None

    console.print(
        f"\n[yellow]Found {len(existing)} existing sample types for this workbook "
        f"in {path}:[/yellow]"
    )
    for _, r in existing.iterrows():
        assays = _parse_assay_ids(r.get("assay_ids"))
        assay_note = f"assays={assays}" if assays else "[dim]no assays assigned[/dim]"
        console.print(f"  [cyan]{r['sheet_name']}[/cyan] → SampleType {r['sample_type_id']}  {assay_note}")

    if questionary.confirm(
        "Reuse these existing sample types (skip creation) and only (re)assign assays?",
        default=True,
    ).ask():
        console.print("[green]Reusing existing sample types — no new ones will be created.[/green]")
        return existing

    console.print("[yellow]Not reusing — new sample types will be created (may duplicate on FairDOMHub).[/yellow]")
    return None


def step_sample_types(cfg: dict, df_assays: pd.DataFrame) -> pd.DataFrame:
    """
    Step 4: Create SampleTypes from workbook sheets, then assign assays.

    One SampleType is created per sheet. After creation, you assign which
    assays each SampleType belongs to (used when creating samples in Step 5).

    If Assets/Output/sample_types_created.csv already holds sample types for this
    same workbook (e.g. a previous run created them but the assay assignment was
    interrupted/cancelled), you are offered the choice to reuse those existing
    sample types and only (re)assign assays — avoiding duplicate SampleType
    resources on FairDOMHub.

    Saves Assets/Output/sample_types_created.csv.
    Returns the summary DataFrame (includes assay_ids column).
    """
    console.rule("[bold blue]Step 4: Sample Types[/bold blue]")

    summary_df = _reuse_existing_sample_types(cfg)
    if summary_df is None:
        summary_df = create_sample_types_from_workbook(
            BASE_URL, cfg["api_token"], cfg["project_id"], cfg["workbook"], cfg["suffix"]
        )

    console.print("\n[bold]Assign assays to each Sample Type[/bold]  (space = select, enter = confirm)\n")
    for idx, row in summary_df.iterrows():
        selected_ids = _pick_assays(
            f"Assays for  '{row['title']}':",
            df_assays,
            preselected=row.get("assay_ids"),
        )
        summary_df.at[idx, "assay_ids"] = selected_ids

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "sample_types_created.csv")
    summary_df.to_csv(out_path, index=False)
    console.print(f"\n[green]✓ Saved:[/green] {out_path}")
    return summary_df


def step_samples(cfg: dict, summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    Step 5: Bulk-create Samples from every data row in the workbook.

    Shows a per-sheet row count before starting so you know what to expect,
    then confirms before submitting anything. Each row becomes one Sample record
    linked to the SampleType and assays assigned in Step 4.

    Saves Assets/Output/samples_created.csv with columns: sheet, uid, sample_id, link.

    If sample creation is skipped at the prompt, returns an empty DataFrame without
    saving a CSV (the existing one from a previous run is left untouched).
    """
    console.rule("[bold blue]Step 5: Samples[/bold blue]")

    with pd.ExcelFile(cfg["workbook"]) as xls:
        sheet_names = xls.sheet_names
    total = 0
    for sheet in sheet_names:
        df = pd.read_excel(cfg["workbook"], sheet_name=sheet).dropna(how="all")
        count = len(df)
        total += count
        console.print(f"  [cyan]{sheet}[/cyan]: {count} rows")
    console.print(f"\n  Total samples to create: [bold]{total}[/bold]")

    if not questionary.confirm("Create all samples now?", default=True).ask():
        console.print("[yellow]Sample creation skipped.[/yellow]")
        return pd.DataFrame()

    samples_df = create_samples_from_workbook(
        BASE_URL, cfg["api_token"], cfg["project_id"], cfg["workbook"], summary_df
    )
    out_path = os.path.join(OUTPUT_DIR, "samples_created.csv")
    samples_df.to_csv(out_path, index=False)
    console.print(f"\n[green]✓ Saved:[/green] {out_path}")
    return samples_df


def step_publish(cfg: dict) -> None:
    """
    Step 6: Batch-set policy on all study assets so they become publicly visible.

    Discovers every asset linked to the study (assays, SOPs, sample types,
    samples, data files) via the API, shows a summary table, then confirms
    before PATCHing each one.  Samples are published in parallel (5 workers)
    to keep the operation fast.

    The study itself is NOT published here — do that manually via the web UI
    after reviewing the data, as noted in the workflow summary.

    Saves Assets/Output/published_assets.csv with columns:
      resource_type | id | status (ok / error) | message
    """
    console.rule("[bold blue]Step 6: Publish Assets[/bold blue]")

    # ── Access level ─────────────────────────────────────────────────────────
    access_level = questionary.select(
        "Public access level:",
        choices=[
            questionary.Choice("view     — public can see metadata only", value="view"),
            questionary.Choice("download — public can see metadata and download files", value="download"),
        ],
    ).ask()

    # Use the first project ID for the policy permission entry
    project_id = cfg["project_id"][0] if cfg["project_id"] else ""

    # ── Collect assets ────────────────────────────────────────────────────────
    console.print(f"\nScanning study [cyan]{cfg['study_id']}[/cyan] for assets...")
    assets = collect_study_assets(BASE_URL, cfg["api_token"], cfg["study_id"])

    total = sum(len(v) for v in assets.values())
    if total == 0:
        console.print("[yellow]⚠  No publishable assets found for this study.[/yellow]")
        return

    # ── Summary table ─────────────────────────────────────────────────────────
    table = Table(title=f"Assets to publish (access={access_level})", show_lines=True)
    table.add_column("Resource type")
    table.add_column("Count", justify="right")
    for rtype, ids in assets.items():
        if ids:
            table.add_row(rtype, str(len(ids)))
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total}[/bold]")
    console.print(table)

    if not questionary.confirm(
        f"\nPublish {total} assets (policy='{access_level}', project={project_id})?",
        default=False,
    ).ask():
        console.print("[yellow]Publish skipped.[/yellow]")
        return

    # ── Publish ───────────────────────────────────────────────────────────────
    results: List[Dict] = []

    def _publish_one(resource_type: str, rid: str) -> Dict:
        try:
            publish_resource(BASE_URL, cfg["api_token"], resource_type, rid, project_id, access_level)
            return {"resource_type": resource_type, "id": rid, "status": "ok", "message": ""}
        except Exception as e:
            return {"resource_type": resource_type, "id": rid, "status": "error", "message": str(e)}

    for rtype, ids in assets.items():
        if not ids:
            continue
        console.print(f"\n  Publishing [cyan]{rtype}[/cyan] ({len(ids)} items)...")

        if rtype == "samples" and len(ids) > 5:
            # Parallel for large sample sets — 5 workers, ~1 req/s per worker
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(_publish_one, rtype, rid): rid for rid in ids}
                for fut in concurrent.futures.as_completed(futs):
                    rec = fut.result()
                    results.append(rec)
                    icon = "[green]✓[/green]" if rec["status"] == "ok" else "[red]✗[/red]"
                    console.print(f"    {icon} {rec['id']}")
        else:
            for rid in ids:
                rec = _publish_one(rtype, rid)
                results.append(rec)
                icon = "[green]✓[/green]" if rec["status"] == "ok" else "[red]✗[/red]"
                console.print(f"    {icon} {rtype[:-1] if rtype.endswith('s') else rtype} {rid}")

    # ── Save results ──────────────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "published_assets.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    console.print(
        f"\n[green]✓ {ok} published[/green]"
        + (f"  [red]✗ {err} errors[/red]" if err else "")
        + f"  — saved: {out_path}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RESUME HELPERS
#
# Used when --step N skips earlier steps and loads their saved outputs instead.
# ═══════════════════════════════════════════════════════════════════════════════

def _load_assays_from_csv() -> pd.DataFrame:
    """
    Load the assay list saved by a previous Step 1 run.

    Reads Assets/Output/assays_from_study.csv and returns a DataFrame with
    columns assay_title and assay_id. Exits with a clear error if the file is
    missing — run Step 1 first or remove --step to start from the beginning.
    """
    path = os.path.join(OUTPUT_DIR, "assays_from_study.csv")
    if not os.path.exists(path):
        console.print(
            f"[red]Cannot resume: {path} not found.\n"
            f"Run without --step (or with --step 1) to generate it first.[/red]"
        )
        sys.exit(1)
    df = pd.read_csv(path)
    console.print(f"[dim]Loaded {len(df)} assays from {path}[/dim]")
    return df


def _load_summary_from_csv() -> pd.DataFrame:
    """
    Load the sample-type summary saved by a previous Step 4 run.

    Reads Assets/Output/sample_types_created.csv, parses the assay_ids column
    using _parse_assay_ids so it handles any storage format (plain CSV string,
    Python list repr, etc.), and returns the ready-to-use summary DataFrame.

    Exits with a clear error if the file is missing.
    """
    path = os.path.join(OUTPUT_DIR, "sample_types_created.csv")
    if not os.path.exists(path):
        console.print(
            f"[red]Cannot resume: {path} not found.\n"
            f"Run --step 4 (or earlier) to generate it first.[/red]"
        )
        sys.exit(1)
    df = pd.read_csv(path)
    df["assay_ids"] = df["assay_ids"].apply(_parse_assay_ids)
    console.print(f"[dim]Loaded {len(df)} sample types from {path}[/dim]")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ARGUMENT PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Examples
    --------
    Run the full workflow (default):
        uv run submit.py

    Start from Step 4, re-entering config manually:
        uv run submit.py --step 4

    Resume from where a previous run left off (loads saved session):
        uv run submit.py --resume
    """
    parser = argparse.ArgumentParser(
        prog="uv run submit.py",
        description=(
            "FairDOMHub Study Submission Tool\n\n"
            "Interactively uploads a study to FairDOMHub step by step.\n"
            "Each step saves its output to Assets/Output/ so you can resume\n"
            "from any point without re-running earlier steps.\n\n"
            "Steps:\n"
            "  1  Assays         — review or create assays for the study\n"
            "  2  Protocols      — fuzzy-match, assign assays, upload SOPs\n"
            "  3  Metadata rewrite — replace protocol names with SOP links\n"
            "  4  Sample types   — create from workbook sheets, assign assays\n"
            "  5  Samples        — bulk-create from workbook rows\n"
            "  6  Publish        — batch-set policy to public on all assets\n\n"
            "Config (Step 0) runs unless --resume is used.\n\n"
            "Prerequisite files:\n"
            "  .env                  — FDH_API token (see .env.example)\n"
            "  Assets/<workbook>.xlsx — metadata workbook\n"
            "  Assets/Protocols/     — protocol files to upload as SOPs\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--step",
        type=int,
        choices=[1, 2, 3, 4, 5, 6],
        default=None,
        metavar="N",
        help=(
            "Step to start from (1–6). Runs Step 0 (config) first.\n"
            "  1 = Assays (full run)\n"
            "  2 = Protocols (loads assays_from_study.csv)\n"
            "  3 = Metadata rewrite (loads assays_from_study.csv)\n"
            "  4 = Sample types (loads assays_from_study.csv; offers to reuse\n"
            "      existing sample_types_created.csv instead of recreating)\n"
            "  5 = Samples only (loads assays + sample_types_created.csv)\n"
            "  6 = Publish only"
        ),
    )
    group.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume from where the last run stopped. Loads config and\n"
            "last completed step from Assets/Output/session.json — no\n"
            "Step 0 prompts needed."
        ),
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """
    Entry point.

    --resume   loads session.json and resumes from last_completed_step + 1.
    --step N   re-runs Step 0 (config) then starts from step N.
    (default)  runs all steps from the beginning.
    """
    args = parse_args()

    console.rule("[bold green]FairDOMHub Study Submission Tool[/bold green]")

    if args.resume:
        cfg, start_step = _load_session()
        console.print(
            f"\n[dim]Resuming from Step {start_step}. "
            f"Earlier outputs will be loaded from {OUTPUT_DIR}/.[/dim]\n"
        )
    else:
        start_step = args.step if args.step is not None else 1
        if start_step > 1:
            console.print(
                f"\n[dim]Starting from Step {start_step}. "
                f"Earlier outputs will be loaded from {OUTPUT_DIR}/.[/dim]\n"
            )
        else:
            console.print(
                "\n[dim]Steps: Config → Assays → Protocols → Metadata Rewrite → "
                "Sample Types → Samples → Publish\nOutputs saved to Assets/Output/ after each step.\n[/dim]"
            )
        cfg = step_config()  # also saves session at step 0

    # Step 1: Assays
    if start_step <= 1:
        df_assays = step_assays(cfg)
        _save_session(cfg, 1)
    elif start_step <= 5:
        console.print("[dim]Skipping Step 1 — loading assays from CSV.[/dim]")
        df_assays = _load_assays_from_csv()
    else:
        df_assays = pd.DataFrame()  # not needed for publish-only run

    # Step 2: Protocols
    if start_step <= 2:
        step_protocols(cfg, df_assays)
        _save_session(cfg, 2)
    elif start_step <= 5:
        console.print("[dim]Skipping Step 2 (protocols already uploaded).[/dim]")

    # Step 3: Metadata rewrite
    if start_step <= 3:
        step_metadata_rewrite(cfg)
        _save_session(cfg, 3)
    elif start_step <= 5:
        console.print("[dim]Skipping Step 3 (metadata rewrite already done).[/dim]")

    # Step 4: Sample types
    if start_step <= 4:
        summary_df = step_sample_types(cfg, df_assays)
        _save_session(cfg, 4)
    elif start_step <= 5:
        console.print("[dim]Skipping Step 4 — loading sample types from CSV.[/dim]")
        summary_df = _load_summary_from_csv()
    else:
        summary_df = pd.DataFrame()  # not needed for publish-only run

    # Step 5: Samples
    if start_step <= 5:
        step_samples(cfg, summary_df)
        _save_session(cfg, 5)

        # ── Optional: additional workbooks (sample types + samples only) ──────
        # Mirrors the "second run" pattern from the original notebook where a
        # second metadata file added extra sample types to the same study.
        while questionary.confirm(
            "\nProcess another workbook for this study (sample types + samples only)?",
            default=False,
        ).ask():
            new_workbook = questionary.path("Path to additional workbook:", default="Assets/").ask().strip()
            if not os.path.exists(new_workbook):
                console.print(f"[red]File not found: {new_workbook}[/red]")
                break
            workbook_cfg = {**cfg, "workbook": new_workbook}
            extra_summary = step_sample_types(workbook_cfg, df_assays)
            step_samples(workbook_cfg, extra_summary)
    else:
        console.print("[dim]Skipping Step 5 (samples already created).[/dim]")

    # Step 6: Publish
    step_publish(cfg)
    _save_session(cfg, 6)

    # ── Done ──────────────────────────────────────────────────────────────────
    console.rule("[bold green]Done[/bold green]")
    console.print(
        f"\n[bold]Next step:[/bold] Review the data on FairDOMHub, "
        f"then publish the [italic]study itself[/italic] via the web UI.\n"
        f"All outputs: [cyan]{OUTPUT_DIR}/[/cyan]\n"
    )


if __name__ == "__main__":
    main()
