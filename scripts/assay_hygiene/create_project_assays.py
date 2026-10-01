# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "requests>=2.31", "openpyxl>=3.1", "pyarrow>=14.0"]
# ///
"""Create reviewed, project-scoped assays and rebuild the gated upload sheet.

This is deliberately a two-phase operation.  The operator first writes and
reviews ``ASSAY-CREATION-PLAN.csv``.  Only ``--confirm`` sends a POST, and an
on-disk in-progress marker makes a timeout or partial response non-retryable.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

from .update_assay_sheet import main as build_sheet

PLAN_COLUMNS = ("sample_id", "project_id", "title", "study_id", "procedure_type", "assay_type", "rationale")
RESULT_COLUMNS = (*PLAN_COLUMNS, "created_seek_assay_id")


class AssayCreationRefused(ValueError):
    pass


def validate_plan(plan: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in PLAN_COLUMNS if column not in plan.columns]
    if missing:
        raise AssayCreationRefused(f"creation plan is missing {missing}")
    plan = plan.loc[:, PLAN_COLUMNS].copy()
    for column in ("sample_id", "project_id", "study_id"):
        if plan[column].isna().any() or not plan[column].astype(str).str.fullmatch(r"[0-9]+").all():
            raise AssayCreationRefused(f"{column} must be a completed integer for every proposed assay")
    for column in ("title", "procedure_type", "assay_type", "rationale"):
        if plan[column].isna().any() or not plan[column].astype(str).str.strip().ne("").all():
            raise AssayCreationRefused(f"{column} must be explicitly completed; do not invent assay metadata")
    if plan.duplicated(["sample_id", "project_id", "title"]).any():
        raise AssayCreationRefused("creation plan repeats a sample/project/title target")
    return plan


def _created_id(body: object) -> int:
    try:
        value = body["data"]["id"]
        return int(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise AssayCreationRefused("assay creation response lacks data.id; reconcile before retrying") from exc


def create(run: Path, base_url: str, *, confirm: bool) -> pd.DataFrame:
    artifacts, process = run / "04-artifacts", run / "07-process"
    plan_path = artifacts / "ASSAY-CREATION-PLAN.csv"
    if not plan_path.exists():
        raise AssayCreationRefused("write and review 04-artifacts/ASSAY-CREATION-PLAN.csv before creation")
    plan = validate_plan(pd.read_csv(plan_path, dtype=object))
    result_path, marker = process / "CREATED-ASSAYS.csv", process / "ASSAY-CREATION-IN-PROGRESS.csv"
    if result_path.exists() or marker.exists():
        raise AssayCreationRefused("a creation receipt or in-progress marker exists; reconcile the server instead of retrying")
    if not confirm:
        return plan
    process.mkdir(parents=True, exist_ok=True)
    marker.write_text(plan.to_csv(index=False), encoding="utf-8")
    auth = (os.getenv("NEXTSEEK_USERNAME"), os.getenv("NEXTSEEK_PASSWORD"))
    if not all(auth):
        raise AssayCreationRefused("NEXTSEEK_USERNAME and NEXTSEEK_PASSWORD are required")
    endpoint = urljoin(base_url.rstrip("/") + "/", "nextseek_api/assays/")
    created = []
    for row in plan.itertuples(index=False):
        payload = {"data": {"type": "assays", "attributes": {"title": row.title, "assay_type": row.assay_type, "assay_class": row.procedure_type}, "relationships": {"study": {"data": {"type": "studies", "id": str(row.study_id)}}}}}
        response = requests.post(endpoint, json=payload, auth=auth, timeout=30)
        response.raise_for_status()
        created.append({**row._asdict(), "created_seek_assay_id": _created_id(response.json())})
        pd.DataFrame(created, columns=RESULT_COLUMNS).to_csv(result_path, index=False)
    created_frame = pd.DataFrame(created, columns=RESULT_COLUMNS)
    manifest_path = artifacts / "MANIFEST.csv"
    manifest = pd.read_csv(manifest_path)
    additions = created_frame.rename(columns={"created_seek_assay_id": "write_target_seek_assay_id"})[["sample_id", "write_target_seek_assay_id"]]
    additions["internal_assay_id"] = "created"
    additions["project_ok"] = True
    augmented = pd.concat([manifest, additions[manifest.columns]], ignore_index=True)
    augmented_path = artifacts / "MANIFEST-WITH-CREATED-ASSAYS.csv"
    augmented.to_csv(augmented_path, index=False)
    build_sheet(run, manifest_path=augmented_path)
    marker.unlink()
    return created_frame


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--base-url", default=os.getenv("NEXTSEEK_BASE_URL"))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    if not args.base_url:
        raise AssayCreationRefused("NEXTSEEK_BASE_URL or --base-url is required")
    result = create(args.run, args.base_url, confirm=args.confirm)
    print(f"{'created' if args.confirm else 'validated'} {len(result):,} assay plan row(s)")


if __name__ == "__main__":
    main()
