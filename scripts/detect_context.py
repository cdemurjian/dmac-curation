"""Network-free logic for /curate-init project + lab auto-detection.

nextseek_api.py's `detect-context` subcommand wires these to the API; keeping
them here (stdlib + openpyxl only) makes them unit-testable offline.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

UID_RE = re.compile(r"^(?P<type>.+)-(?P<date>\d{6})(?P<lab>[A-Z]{3})-(?P<n>\d+)$")
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens of length >= 3 (drops noise like 'of')."""
    return [t for t in _WORD.findall((text or "").lower()) if len(t) >= 3]


@dataclass
class Evidence:
    path_tokens: list[str] = field(default_factory=list)
    author_surnames: list[str] = field(default_factory=list)
    doi: "str | None" = None
    master_tokens: list[str] = field(default_factory=list)

    def all_tokens(self) -> set:
        return set(self.path_tokens) | set(self.master_tokens)


def gather_evidence(project_root) -> Evidence:
    root = Path(project_root)
    path_tokens: list[str] = []
    for part in root.resolve().parts:
        path_tokens.extend(tokenize(part))

    author_surnames: list[str] = []
    man = root / "manuscript"
    if man.is_dir():
        for f in sorted(man.iterdir()):
            if f.is_file():
                toks = tokenize(f.stem)
                path_tokens.extend(toks)
                author_surnames.extend(toks)  # filenames often encode authors

    master_tokens: list[str] = []
    pm = root / "previous_metadata"
    if pm.is_dir():
        for f in sorted(pm.glob("*.xlsx")):
            master_tokens.extend(tokenize(f.stem))

    return Evidence(path_tokens=path_tokens, author_surnames=author_surnames,
                    doi=None, master_tokens=master_tokens)


def rank_projects(projects: list, evidence: Evidence) -> list:
    """Score each project by evidence-token overlap with its title; sort desc."""
    ev = evidence.all_tokens() | set(evidence.author_surnames)
    out = []
    for p in projects:
        title_toks = set(tokenize(p.get("title", "")))
        out.append({**p, "score": len(ev & title_toks)})
    out.sort(key=lambda p: (-p["score"], str(p.get("title", ""))))
    return out


@dataclass
class LabInfo:
    code: str
    count: int
    scientists: list
    latest: str
    score: float = 0.0


def extract_labs(xlsx_bytes: bytes) -> list:
    """Aggregate UIDs across all sheets of a project export into per-lab records."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    agg: dict = {}
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            hdr = [str(h).strip().lower() if h is not None else "" for h in next(rows)]
        except StopIteration:
            continue
        if "uid" not in hdr:
            continue
        ui = hdr.index("uid")
        si = hdr.index("scientist") if "scientist" in hdr else None
        for r in rows:
            if ui >= len(r) or not r[ui]:
                continue
            m = UID_RE.match(str(r[ui]).strip())
            if not m:
                continue
            a = agg.setdefault(m.group("lab"),
                               {"count": 0, "scientists": set(), "latest": ""})
            a["count"] += 1
            a["latest"] = max(a["latest"], m.group("date"))
            if si is not None and si < len(r) and r[si]:
                a["scientists"].add(str(r[si]).strip())
    wb.close()
    return [LabInfo(code=code, count=v["count"],
                    scientists=sorted(v["scientists"]), latest=v["latest"])
            for code, v in agg.items()]
