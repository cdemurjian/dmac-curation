"""The UPDATE_ASSAY sheet, the one artifact that reaches production.

WHY THIS FILE EXISTS AT ALL. `/curate-assay-write` documents posting an
`UPDATE_ASSAY` sheet and `preflight.check` takes that sheet as its first
argument, but nothing built one -- so the write stage terminated in a frame no
module produced. Every RUN so far bridged it by hand.

THE TRAP THIS SUITE IS MOSTLY ABOUT. `preflight._pair_is_two_ints` checks a
pair's SHAPE and never its meaning, and the planning fixture that seeded this
work read

    {"sample_id": [10], "assay_id": [501], "new_pair": ["10:501"]}

which reads exactly as if the New pair were `sample_id:assay_id`. It is not.
Read off `seek/dbtable_assay_assets.py:109-166`, the endpoint takes the sample
from `getSampleID(dici['Sample UID'])` -- a separate argument, never a sheet
pair -- and the New pair is

    (dici['New Assay ID'], dici['New Assay Direction'])

A sheet built to the fixture's reading would put a sample id where the assay id
goes and pass all eight refusals doing it, because `10:501` and `501:0` are both
two ints. Nothing downstream would catch it: `storeOneRecord` reports success
for rows that never wrote, so the receipt would say 744 and the graph would
carry 744 registrations against whatever assays happen to have those ids.
`test_the_new_pair_is_the_assay_and_the_direction` is the guard.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import chunker as C  # noqa: E402
from assay_hygiene import preflight as P  # noqa: E402
from assay_hygiene import update_assay_sheet as U  # noqa: E402

RUN2 = REPO / "assets" / "RUN2"
GOOD_BACKUP = {"size": 17_000_000, "trailer_ok": True}

# Synthetic, and in the reserved 19MMDD band that is provably absent from
# production. DEFINED ONCE AND REFERRED TO THEREAFTER, which is what keeps
# `test_identifier_exposure`'s ratchet counting this module as two occurrences
# rather than one per use.
UID_A = "TIS-190101ENG-901"
UID_B = "TIS-190101ENG-902"
UID_C = "TIS-190101ENG-903"


def _manifest(**over):
    base = {"sample_id": [10, 11],
            "internal_assay_id": [24, 24],
            "write_target_seek_assay_id": [501, 502],
            "project_ok": [True, True]}
    base.update(over)
    return pd.DataFrame(base)


def _uids():
    return {10: UID_A, 11: UID_B}


# --- the endpoint's contract -------------------------------------------------


def test_the_sheet_carries_exactly_the_headers_the_endpoint_requires():
    """`_batchUpdateSampleAssociation` refuses the file for a missing header.

    Read off `seek/sample/upload.py:818`. It is an exact list and the check is
    per-header presence, so a rename on either side fails the whole submission
    with error 701 rather than a row.
    """
    sheet = U.build(_manifest(), _uids())
    assert tuple(sheet.columns) == U.REQUIRED_HEADERS
    assert U.REQUIRED_HEADERS == (
        "Sample UID", "Current Assay ID", "Current Assay Direction",
        "New Assay ID", "New Assay Direction")


def test_both_current_columns_are_blank_so_the_delete_branch_is_unreachable():
    """The entire safety argument for choosing this mechanism.

    `updateSample_assay_asset` sets `id = -1` when EITHER Current column fails
    `int()`, and `deleteOneRecord` sits behind `if id>0`. Blank in both is what
    makes the sheet structurally incapable of deleting.
    """
    sheet = U.build(_manifest(), _uids())
    for column in ("Current Assay ID", "Current Assay Direction"):
        assert list(sheet[column]) == ["", ""]
        for value in sheet[column]:
            with pytest.raises((ValueError, TypeError)):
                int(value)


def test_the_new_pair_is_the_assay_and_the_direction():
    """THE TRAP. See the module docstring.

    `New Assay ID` is the SEEK assay this row registers into -- the manifest's
    gate-checked `write_target_seek_assay_id`, never the sample. The sample
    travels as `Sample UID` and nowhere else.
    """
    sheet = U.build(_manifest(), _uids())
    assert list(sheet["New Assay ID"]) == [501, 502]
    assert list(sheet["New Assay Direction"]) == [0, 0]
    assert list(sheet["Sample UID"]) == [UID_A, UID_B]
    # the sample ids must appear NOWHERE in the posted sheet
    flat = sheet.astype(str).to_numpy().ravel().tolist()
    assert "10" not in flat and "11" not in flat


def test_every_row_writes_direction_zero():
    """One fact, recorded once. Lineage direction is already in the graph from
    stage 0, and asserting it again here would be a second copy free to
    disagree with the first."""
    assert U.DIRECTION == 0
    sheet = U.build(_manifest(), _uids())
    assert set(sheet["New Assay Direction"]) == {0}


# --- what build refuses ------------------------------------------------------


def test_a_sample_with_no_uid_is_refused():
    """`getSampleID` returns None, `None > 0` raises, the run 500s mid-chunk
    and leaves a committed prefix -- this path has no transaction."""
    with pytest.raises(U.SheetRefused, match="uid"):
        U.build(_manifest(), {10: UID_A})


def test_a_blank_uid_is_refused_as_loudly_as_a_missing_one():
    with pytest.raises(U.SheetRefused, match="uid"):
        U.build(_manifest(), _uids() | {11: "   "})


def test_a_row_the_project_gate_did_not_pass_is_refused():
    """`project_ok` False is a row with no correct target, not a row to write.

    The cross-project write is the unrecoverable one: it registers a sample
    into another project's assay, and nothing in SEEK undoes that by itself.
    """
    with pytest.raises(U.SheetRefused, match="project"):
        U.build(_manifest(project_ok=[True, False]), _uids())


def test_a_duplicated_edge_is_refused_because_it_breaks_the_count():
    """Submitting one edge twice is harmless in the database and fatal to the
    receipt. `storeOneRecord` dedupes on `(assay_id, asset_id, asset_type)`, so
    the second row writes nothing -- and `chunker.reconcile` then sees a short
    write it cannot distinguish from rows that genuinely failed."""
    dup = pd.DataFrame({"sample_id": [10, 10],
                        "internal_assay_id": [24, 24],
                        "write_target_seek_assay_id": [501, 501],
                        "project_ok": [True, True]})
    with pytest.raises(U.SheetRefused, match="twice|duplicate"):
        U.build(dup, _uids())


def test_a_non_integer_assay_target_is_refused():
    """`int(dici['New Assay ID'])` failing sets `addnew = False`, and the row
    is then dropped silently while the workbook reports success."""
    bad = _manifest()
    bad["write_target_seek_assay_id"] = ["", 502]
    with pytest.raises(U.SheetRefused, match="assay"):
        U.build(bad, _uids())


def test_a_uid_that_is_not_UNIQUE_in_the_extract_is_refused():
    """THIS IS WHAT KILLED CHUNK 06 OF RUN1, and it is not a hypothesis.

    `_retrieveSampleByUID` (`seek/sample/core.py:397-408`) returns a record only
    when `len(records)==1`. A uuid held by two samples therefore resolves to
    None exactly as a missing one does, and `upload.py`'s `if sample_id>0`
    raises TypeError on it -- 500ing the submission mid-chunk with rows already
    committed.

    RUN1's preflight asked "does this uid exist" with a JOIN and a COUNT
    DISTINCT. The code asks "does exactly ONE row have this uid". Those two
    agree everywhere except on duplicates, which is the only case that can
    hurt, and four of them took chunk 06 down. Production carries duplicate
    uuids and `samples.uuid` has no unique constraint, so this is a live
    property of the data and not a transient.

    The duplicate is detectable from `uid_of` alone: two sample ids mapping to
    one uid IS the ambiguity, so no second source has to be consulted.
    """
    doubled = _uids() | {12: UID_A}       # sample 12 shares sample 10's uid
    with pytest.raises(U.SheetRefused, match="more than one sample"):
        U.build(_manifest(), doubled)


def test_a_duplicate_uid_elsewhere_in_the_extract_does_not_block_us():
    """The refusal is about uids this sheet WRITES, not the whole database.

    Production holds duplicate uuids that no run touches. Refusing on those
    would make every sheet unbuildable for a defect in unrelated rows.
    """
    unrelated = _uids() | {900: UID_C, 901: UID_C}
    sheet = U.build(_manifest(), unrelated)
    assert len(sheet) == 2


# --- the join back to preflight ----------------------------------------------


def test_the_preflight_frame_is_derived_from_the_posted_sheet():
    """Preflight must check what will ACTUALLY be posted.

    Deriving its frame from the manifest instead would check the input twice
    and the artifact never -- exactly the gap that lets a build bug through.
    """
    manifest = _manifest()
    sheet = U.build(manifest, _uids())
    frame = U.for_preflight(sheet, {v: k for k, v in _uids().items()})
    assert list(frame.sample_id) == [10, 11]
    assert list(frame.assay_id) == [501, 502]
    assert list(frame.new_pair) == ["501:0", "502:0"]
    assert list(frame.current_pair) == ["", ""]


def test_a_clean_sheet_passes_all_eight_refusals():
    manifest = _manifest()
    sheet = U.build(manifest, _uids())
    frame = U.for_preflight(sheet, {v: k for k, v in _uids().items()})
    P.check(frame, manifest, [U.SHEET_NAME], GOOD_BACKUP, 414935)


def test_a_sheet_row_outside_the_manifest_is_refused_by_preflight():
    """The subset property, checked on the real artifact rather than asserted."""
    manifest = _manifest()
    sheet = U.build(manifest, _uids())
    sheet.loc[0, "New Assay ID"] = 999
    frame = U.for_preflight(sheet, {v: k for k, v in _uids().items()})
    with pytest.raises(P.PreflightRefused, match="manifest check failed"):
        P.check(frame, manifest, [U.SHEET_NAME], GOOD_BACKUP, 414935)


def test_the_workbook_never_carries_a_sheet_named_UPDATE(tmp_path):
    """`UPDATE` is tested BEFORE the assay path in dispatch and would send the
    file into `_batchUpdateSample`, rewriting sample metadata."""
    path = tmp_path / "run2.xlsx"
    names = U.write_workbook(U.build(_manifest(), _uids()), path)
    assert names == [U.SHEET_NAME]
    assert P.FORBIDDEN_SHEET not in names
    back = pd.read_excel(path, sheet_name=U.SHEET_NAME, dtype=object)
    assert tuple(back.columns) == U.REQUIRED_HEADERS


def test_the_workbook_round_trips_the_current_columns_as_unparseable(tmp_path):
    """A blank that survives xlsx as a blank. If openpyxl were to write a 0
    there, `int()` would succeed, `id` would stop being -1, and the delete
    branch this mechanism was chosen to make unreachable would reopen."""
    path = tmp_path / "run2.xlsx"
    U.write_workbook(U.build(_manifest(), _uids()), path)
    back = pd.read_excel(path, sheet_name=U.SHEET_NAME, dtype=object)
    for column in ("Current Assay ID", "Current Assay Direction"):
        for value in back[column]:
            with pytest.raises((ValueError, TypeError)):
                int(value)


# --- the real run ------------------------------------------------------------


def test_the_real_run2_manifest_builds_one_chunk():
    """744 gate-checked rows, and the cap is 2,000 -- so one submission."""
    manifest_path = RUN2 / "04-artifacts" / "MANIFEST.csv"
    samples_path = RUN2 / "01-extract" / "samples.parquet"
    if not manifest_path.exists() or not samples_path.exists():
        pytest.skip("RUN2 artifacts are curation output and are not in git")
    manifest = pd.read_csv(manifest_path)
    samples = pd.read_parquet(samples_path, columns=["sample_id", "uuid"])
    uid_of = dict(zip(samples.sample_id.astype(int), samples.uuid.astype(str)))
    assert len(manifest) == 744

    # THE RESOLVED MANIFEST IS REFUSED, and that is the correct outcome. Four
    # of its samples carry a uid production holds twice -- the same class of
    # row that killed RUN1's chunk 06. RUN2 is a SINGLE chunk, so submitting it
    # unfiltered would not cost one chunk, it would cost the run.
    with pytest.raises(U.SheetRefused, match="more than one sample"):
        U.build(manifest, uid_of)

    counts = pd.Series(list(uid_of.values())).value_counts()
    doubled = {u for u, n in counts.items() if n > 1}
    writable = manifest[~manifest.sample_id.map(uid_of).isin(doubled)]
    assert len(writable) == 740, "4 rows are blocked by duplicate uuids"

    sheet = U.build(writable, uid_of)
    assert len(sheet) == 740 and len(C.chunks(sheet)) == 1
    frame = U.for_preflight(sheet, {v: k for k, v in uid_of.items()})
    P.check(frame, writable, [U.SHEET_NAME], GOOD_BACKUP, 414935)
