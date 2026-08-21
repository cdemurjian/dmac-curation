# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "pyarrow>=14"]
# ///
"""The pre-rework figures, DERIVED, so every later delta can be checked.

NOT A TEST AND NOT A CONTRACT. This is a photograph of the output as it stood
before the reachability rework, taken so that a task claiming "-99,449 rows" can
be held to it. Both audits of 2026-08-21 found stale figures in documents whose
subject was stale figures; the defence is to re-derive, never to quote.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASELINE_KEYS = (
    "rows", "rows_mode_1", "rows_mode_2", "rows_no_mode",
    "mode2_unreachable", "mode2_reachable",
    "mode2_without_a_gate_outcome",
    "by_precedent_with_no_coregistration",
    "rows_with_a_fallback_namespace_id",
)


def measure(findings_csv: str, extract_dir: str) -> dict[str, int]:
    f = pd.read_csv(findings_csv, low_memory=False)
    assays = pd.read_parquet(Path(extract_dir) / "assays.parquet")
    genuine = {int(x) for x in assays.internal_assay_id.dropna()}
    m2 = f[f["mode"] == "MODE_2"]
    return {
        "rows": len(f),
        "rows_mode_1": int((f["mode"] == "MODE_1").sum()),
        "rows_mode_2": len(m2),
        "rows_no_mode": int(f["mode"].isna().sum()),
        "mode2_unreachable": int((m2.type_registrations == 0).sum()),
        "mode2_reachable": int((m2.type_registrations > 0).sum()),
        "mode2_without_a_gate_outcome": int(m2.gate.isna().sum()),
        "by_precedent_with_no_coregistration": int(
            ((f.proposed_by == "BY_PRECEDENT") & (f.precedent_n_both == 0)).sum()),
        "rows_with_a_fallback_namespace_id": int(
            (~f.proposed_internal_assay_id.astype(int).isin(genuine)).sum()),
    }


def main(findings_csv="assay-hygiene-bak/artifacts/findings.csv",
         extract_dir="assay-hygiene-bak/extract") -> int:
    got = measure(findings_csv, extract_dir)
    print("| key | rows |")
    print("|---|---|")
    for k in BASELINE_KEYS:
        print(f"| `{k}` | {got[k]:,} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
