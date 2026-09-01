# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0", "openpyxl>=3.1", "pyarrow>=14.0"]
# ///
"""The UPDATE_ASSAY workbook — the only artifact this mode posts to production.

WHAT WAS MISSING. `/curate-assay-write` documents posting an `UPDATE_ASSAY`
sheet and `preflight.check` takes that sheet as its FIRST argument, but nothing
built one. The write stage terminated in a frame no module produced, so every
run bridged it by hand. This module is that joint.

THE CONTRACT IS READ OFF THE ENDPOINT, NOT INFERRED. Verified against
NExtSEEK on 2026-08-31:

  seek/sample/upload.py:818   headers_required = ["Sample UID",
                              "Current Assay ID", "Current Assay Direction",
                              "New Assay ID", "New Assay Direction"]
  seek/sample/upload.py:975   dispatch on 'UPDATE_ASSAY' in sheetnames
  seek/sample/upload.py:852   sample_id = self.getSampleID(dici['Sample UID'])
  seek/dbtable_assay_assets.py:109-166  updateSample_assay_asset

A missing header fails the WHOLE file with error 701, not a row, so the five
names are exact and ordered here.

THE PAIRS ARE COLUMN PAIRS, AND NEITHER OF THEM IS THE SAMPLE. This is the
trap this module exists to close. `preflight._pair_is_two_ints` checks a pair's
SHAPE and never its meaning, and the planning fixture that seeded this work read
`{"sample_id": [10], "assay_id": [501], "new_pair": ["10:501"]}` — which reads
exactly as though the New pair were `sample_id:assay_id`. It is not:

    Current pair = (Current Assay ID, Current Assay Direction)
    New pair     = (New Assay ID,     New Assay Direction)

The sample never appears in a pair at all. It reaches the endpoint through
`getSampleID(dici['Sample UID'])` and nowhere else. A sheet built to the
fixture's reading would put a sample id where an assay id belongs, pass all
eight refusals doing it — `10:501` and `501:0` are both two ints — and register
744 rows against whatever assays happen to carry those ids. Nothing downstream
catches it: `storeOneRecord` sets `status = 1` without consulting the database,
so the feedback workbook would print `successful:` for every one.

WHY BOTH CURRENT COLUMNS ARE BLANK. `updateSample_assay_asset` sets `id = -1`
the moment EITHER Current column fails `int()`, and `deleteOneRecord` sits
behind `if id>0`. Blank in both is the entire safety argument for choosing this
mechanism over the API and batch-upload routes: it is structurally incapable of
deleting. Measured for the same 25,769 rows, those two put 202,016 and 25,912
existing memberships at risk; this route puts zero.

WHY DIRECTION IS ALWAYS 0. Our rows assert MEMBERSHIP. Lineage direction is
already recorded in the graph by stage 0, and asserting it again here would be
a second copy of a fact, free to disagree with the first. Note that `direction`
is NOT in `uniqueFields` (`['assay_id', 'asset_id', 'asset_type']`), so it does
not participate in the read-before-write that makes a re-submission idempotent.

WHY THIS REFUSES RATHER THAN FILTERS. Every refusal below is a row that would
otherwise reach production silently wrong. Dropping such a row and continuing
would submit a sheet whose size no longer matches the manifest the operator
approved, and `chunker.reconcile` would then read the gap as a failed write.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

SHEET_NAME = "UPDATE_ASSAY"

# EXACT AND ORDERED. `_batchUpdateSampleAssociation` checks presence per header
# and fails the whole submission with error 701 for any one missing.
REQUIRED_HEADERS = ("Sample UID", "Current Assay ID", "Current Assay Direction",
                    "New Assay ID", "New Assay Direction")

# The manifest column carrying the gate-checked SEEK assay. It is NOT
# `internal_assay_id`: the internal id is this house's own numbering and the
# endpoint writes `assay_assets.assay_id`, which is SEEK's.
TARGET_COLUMN = "write_target_seek_assay_id"

DIRECTION = 0
BLANK = ""


class SheetRefused(ValueError):
    """A row that would reach production silently wrong."""


def _is_true(value) -> bool:
    """Tolerant of bool, numpy.bool_ and the string a CSV round-trip leaves."""
    return str(value).strip().lower() == "true"


def _pair(first, second) -> str:
    """The two columns as preflight reads them, or "" when they are blank.

    JOINED ONLY WHEN BOTH CARRY SOMETHING. Rendering two blanks as ':' would
    invent a separator the sheet does not contain, and a reader checking "is
    this two ints" against a fabricated string is checking the wrong artifact.
    """
    a, b = str(first).strip(), str(second).strip()
    return f"{a}:{b}" if a and b else BLANK


def build(manifest: pd.DataFrame, uid_of: dict[int, str]) -> pd.DataFrame:
    """-> the UPDATE_ASSAY sheet for `manifest`, or raise.

    `uid_of` maps sample_id to the sample's UID string, from the extract's
    `samples.parquet`. It is passed in rather than read here because this
    module never touches a database or an extract: it takes frames and returns
    frames, so the artifact can be reviewed before anything is posted.
    """
    if TARGET_COLUMN not in manifest.columns:
        raise SheetRefused(
            f"the manifest carries {list(manifest.columns)} and not "
            f"{TARGET_COLUMN!r}. The sheet registers into SEEK's assay id; a "
            "manifest without one has not been through the project gate.")

    ungated = [int(r.sample_id) for r in manifest.itertuples()
               if not _is_true(r.project_ok)]
    if ungated:
        raise SheetRefused(
            f"{len(ungated)} row(s) carry project_ok other than True, e.g. "
            f"sample(s) {ungated[:5]}. A row the project gate did not pass has "
            "no correct target, and registering a sample into another "
            "project's assay is the one write nothing here can undo.")

    edges = [(int(r.sample_id), r) for r in manifest.itertuples()]
    seen: dict[tuple, int] = {}
    for i, (sid, row) in enumerate(edges):
        key = (sid, str(getattr(row, TARGET_COLUMN)).strip())
        if key in seen:
            raise SheetRefused(
                f"the manifest names sample {sid} into assay {key[1]} twice "
                f"(rows {seen[key]} and {i}). The second is a duplicate that "
                "writes nothing -- `storeOneRecord` dedupes on (assay_id, "
                "asset_id, asset_type) -- so the database would gain one row "
                "where two were submitted, and `chunker.reconcile` cannot tell "
                "that from a row that genuinely failed.")
        seen[key] = i

    targets, bad_assay = [], []
    for sid, row in edges:
        try:
            targets.append(int(getattr(row, TARGET_COLUMN)))
        except (TypeError, ValueError):
            bad_assay.append((sid, getattr(row, TARGET_COLUMN)))
    if bad_assay:
        raise SheetRefused(
            f"{len(bad_assay)} row(s) carry a {TARGET_COLUMN} that is not an "
            f"integer, e.g. {bad_assay[:5]}. `int(dici['New Assay ID'])` "
            "failing sets addnew = False, and the endpoint then drops the "
            "registration while still reporting success.")

    uids, bad_uid = [], []
    for sid, _row in edges:
        uid = uid_of.get(sid)
        if not isinstance(uid, str) or not uid.strip():
            bad_uid.append(sid)
        else:
            uids.append(uid)
    if bad_uid:
        raise SheetRefused(
            f"{len(bad_uid)} sample(s) have no uid in the extract, e.g. "
            f"{bad_uid[:5]}. `getSampleID` returns None for a blank uid, "
            "`None > 0` raises, and the submission 500s mid-chunk leaving a "
            "committed prefix -- this path has no transaction.")

    # THE CHUNK-06 GATE. `_retrieveSampleByUID` returns a record only when
    # `len(records)==1`, so a uuid held by TWO samples resolves to None exactly
    # as a missing one does -- and `upload.py`'s `if sample_id>0` raises on
    # None, 500ing the submission mid-chunk with rows already committed. Four
    # such uids took RUN1's chunk 06 down.
    #
    # ASKED AS "IS IT UNIQUE", NOT "DOES IT EXIST". RUN1's preflight used a
    # JOIN and a COUNT DISTINCT, which answers the second question; the two
    # agree everywhere except on duplicates, which is the only case that hurts.
    # `samples.uuid` carries no unique constraint, so this is a standing
    # property of the data rather than a transient to retry past.
    #
    # SCOPED TO THE UIDS THIS SHEET WRITES. Production holds duplicate uuids no
    # run touches; refusing on those would make every sheet unbuildable.
    counts = Counter(uid_of.values())
    ambiguous = sorted({u for u in uids if counts[u] > 1})
    if ambiguous:
        raise SheetRefused(
            f"{len(ambiguous)} uid(s) on this sheet name more than one sample "
            f"in the extract, e.g. {len(ambiguous[:5])} of them. "
            "`_retrieveSampleByUID` requires exactly one match and returns "
            "None otherwise, which 500s the whole submission mid-chunk. Those "
            "samples must be deduplicated in production before their "
            "registrations can be written; drop them from the manifest to "
            "write the rest.")

    n = len(edges)
    return pd.DataFrame({
        "Sample UID": uids,
        # BLANK, and this is the safety property. See the module docstring.
        "Current Assay ID": [BLANK] * n,
        "Current Assay Direction": [BLANK] * n,
        "New Assay ID": targets,
        "New Assay Direction": [DIRECTION] * n,
    }, columns=list(REQUIRED_HEADERS))


def for_preflight(sheet: pd.DataFrame,
                  sample_id_of: dict[str, int]) -> pd.DataFrame:
    """-> the frame `preflight.check` reads, DERIVED FROM THE POSTED SHEET.

    Derived from the sheet and not rebuilt from the manifest on purpose: the
    manifest is the input and the sheet is the artifact, and a preflight that
    re-checks the input has verified nothing about what will actually be sent.
    That is precisely the gap a build defect would travel through.
    """
    uids = [str(u) for u in sheet["Sample UID"]]
    unknown = sorted({u for u in uids if u not in sample_id_of})
    if unknown:
        raise SheetRefused(
            f"{len(unknown)} uid(s) on the sheet resolve to no sample in the "
            f"extract, e.g. {unknown[:5]}. Without a sample id the row cannot "
            "be checked against the gate-approved manifest at all.")

    return pd.DataFrame({
        "sample_id": [int(sample_id_of[u]) for u in uids],
        "assay_id": [int(a) for a in sheet["New Assay ID"]],
        "uid": uids,
        "current_pair": [_pair(c, d) for c, d
                         in zip(sheet["Current Assay ID"],
                                sheet["Current Assay Direction"])],
        "new_pair": [_pair(a, d) for a, d
                     in zip(sheet["New Assay ID"],
                            sheet["New Assay Direction"])],
    })


def write_workbook(sheet: pd.DataFrame, path) -> list[str]:
    """Write the workbook and -> its sheet names.

    ONE SHEET, NAMED UPDATE_ASSAY. Dispatch tests for a sheet called `UPDATE`
    BEFORE the assay path (`seek/sample/upload.py`), so a workbook carrying one
    is routed into `_batchUpdateSample` and rewrites sample metadata instead.
    """
    path = Path(path)
    if tuple(sheet.columns) != REQUIRED_HEADERS:
        raise SheetRefused(
            f"the sheet carries {list(sheet.columns)}; the endpoint requires "
            f"{list(REQUIRED_HEADERS)} and fails the whole file for any one "
            "missing. Build it with `build`, do not assemble it here.")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        sheet.to_excel(writer, sheet_name=SHEET_NAME, index=False)
        return list(writer.book.sheetnames)


def ambiguous_samples(manifest: pd.DataFrame,
                      uid_of: dict[int, str]) -> list[int]:
    """-> the manifest's sample ids whose uid names more than one sample."""
    counts = Counter(uid_of.values())
    return sorted({int(r.sample_id) for r in manifest.itertuples()
                   if counts.get(uid_of.get(int(r.sample_id)), 0) > 1})


def main(run_dir=None, out=None, artifacts="assay-hygiene",
         drop_ambiguous=False) -> int:
    """Build the workbook for a run from its manifest and its own extract.

    IT DOES NOT DEFAULT INTO THE RUN'S OWN TIERS. `04-artifacts` is chmod 0o555
    from the moment the run is created -- a tier writable for the duration of a
    run is a tier the run can destroy -- so the workbook lands in the working
    directory, as every other `main` in this package does. Copy it into the run
    deliberately, or pass `out`.
    """
    # REQUIRED, AND IT USED TO DEFAULT TO "assets/RUN2". The write command
    # documents running this module bare, so on RUN3 the default would have
    # silently rebuilt a workbook from RUN2's manifest and RUN2's extract --
    # rows already in production. `assert_subset` would pass (they ARE a subset
    # of RUN2's own manifest) and preflight would pass; the first thing to
    # notice would be `chunker.reconcile`, after up to 2,000 rows had been
    # re-submitted.
    if not run_dir:
        raise SheetRefused(
            "run_dir is required. It previously defaulted to a specific run, "
            "which meant a later run rebuilt the earlier one's workbook from "
            "the earlier one's extract -- rows already written to production, "
            "and nothing before `reconcile` would have caught it. Pass the "
            "run you are building, e.g. main('assets/RUN3').")
    run = Path(run_dir)
    manifest = pd.read_csv(run / "04-artifacts" / "MANIFEST.csv")
    samples = pd.read_parquet(run / "01-extract" / "samples.parquet",
                              columns=["sample_id", "uuid"])
    uid_of = dict(zip(samples.sample_id.astype(int), samples.uuid.astype(str)))

    # REFUSES BY DEFAULT, and dropping is explicit and logged. These are
    # authorised registrations with no writable target, not rows to discard
    # quietly -- they stay unwritten until someone deduplicates the samples.
    blocked = ambiguous_samples(manifest, uid_of)
    if blocked:
        print(f"  {len(blocked)} sample(s) carry a uid production holds more "
              f"than once: {blocked}")
        if not drop_ambiguous:
            print("  REFUSING. Re-run with drop_ambiguous=True to write the "
                  "rest, or deduplicate those samples first.")
        else:
            manifest = manifest[~manifest.sample_id.isin(blocked)]
            print(f"  DROPPED them; {len(manifest):,} row(s) remain writable")

    sheet = build(manifest, uid_of)
    target = Path(out) if out else Path(artifacts) / "UPDATE_ASSAY.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    names = write_workbook(sheet, target)

    # The companion manifest `submit_update_assay --manifest` reads. ITS SHAPE
    # IS THE SHIM'S, NOT resolve_targets': the shim joins (uid, New Assay ID)
    # because those are the only two identifying columns the workbook carries.
    # Written beside the workbook so the pair travels together to the box.
    # NAMED DISTINCTLY ON PURPOSE. `resolve_targets` already writes a
    # MANIFEST.csv -- `sample_id, internal_assay_id, write_target_seek_assay_id,
    # project_ok` -- which is what `preflight.assert_subset` reads. THIS one is
    # the submitter's, keyed on `uid, assay_id, project_ok`, because the
    # workbook carries no sample_id. Two different files under one name, feeding
    # two gates in the same command, is a swap waiting to happen.
    companion = target.with_name("SUBMIT-MANIFEST.csv")
    pd.DataFrame({"uid": sheet["Sample UID"],
                  "assay_id": sheet["New Assay ID"],
                  "project_ok": True}).to_csv(companion, index=False)
    print(f"wrote {companion}  ({len(sheet):,} row(s), the shim's project gate)")
    print(f"wrote {target}  sheets={names}  rows={len(sheet):,}")
    print(f"  every Current column blank; every New Assay Direction "
          f"{DIRECTION}; {sheet['New Assay ID'].nunique()} distinct assay(s)")
    print("  NOT YET PREFLIGHTED -- run preflight.check on for_preflight(...) "
          "with the rollback handle and the verified backup before posting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
