"""`baseline.measure` is the anchor every row-delta claim in the mode 2
generation rework is checked against, so a wrong figure here mis-anchors the
whole plan and nothing downstream can catch it -- downstream compares against
this table.

Two failure modes are silent and both are covered below.

A key ADDED to the returned dict but missing from `BASELINE_KEYS` never prints:
`main` iterates the constant, not the dict. That drift is not hypothetical --
the brief specifying this module tabulated eight of the nine keys, omitting
`mode2_reachable`. `test_measure_returns_exactly_the_keys_it_prints` closes it
in both directions.

Swapping the `== 0` / `> 0` expressions for `mode2_unreachable` and
`mode2_reachable` prints two entirely plausible numbers. The fixture below is
built so those two counts DIFFER (4 and 2), which is what makes the swap show up
as a red instead of passing unnoticed.

Everything here is synthetic and written to `tmp_path`, so this file cannot skip
for a missing artifact. The real 106 MB `findings.csv` is deliberately outside
git; a test that reached for it would be green-by-absence, which is the failure
mode the baseline exists to defend against.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S
from assay_hygiene import baseline as B

# The genuine internal namespace in the fixture extract. An id outside it is a
# fallback -- a seek `assays.id` standing in for a record with no junction row.
GENUINE = (11, 12)

FINDINGS_COLUMNS = [
    "mode", "type_registrations", "gate",
    "proposed_by", "precedent_n_both", "proposed_internal_assay_id",
]

# (mode, type_registrations, gate, proposed_by, precedent_n_both, proposed_internal_assay_id)
FINDINGS_ROWS = [
    # -- MODE_1: 2 rows, both gated, both reachable ------------------------
    ("MODE_1", 5, "GATE_OK", "BY_PRECEDENT", 3, 11),
    ("MODE_1", 7, "GATE_OK", "BY_CLAIM", 0, 12),
    # -- MODE_2: 6 rows; 4 unreachable / 2 reachable, 5 with no gate -------
    ("MODE_2", 0, None, "BY_LINEAGE_ONLY", 0, 11),
    ("MODE_2", 0, None, "BY_PRECEDENT", 0, 11),
    ("MODE_2", 0, None, "BY_PRECEDENT", 0, 12),
    ("MODE_2", 0, "GATE_UNREACHABLE", "BY_PRECEDENT", 4, 12),
    ("MODE_2", 3, None, "BY_PRECEDENT", 0, 11),
    ("MODE_2", 9, None, "BY_LINEAGE_ONLY", 2, 12),
    # -- no mode: 3 rows, one carrying a fallback-namespace id -------------
    (None, 0, None, "BY_PRECEDENT", 5, 11),
    (None, 1, None, "BY_CLAIM", 0, 2),
    (None, 0, None, "BY_LINEAGE_ONLY", 1, 12),
]

# Hand-counted off FINDINGS_ROWS above, not read back out of `measure`.
#
#   rows                                 11 rows in the list
#   rows_mode_1                           2 rows 1-2
#   rows_mode_2                           6 rows 3-8
#   rows_no_mode                          3 rows 9-11
#   mode2_unreachable                     4 rows 3,4,5,6   (type_registrations == 0)
#   mode2_reachable                       2 rows 7,8       (type_registrations > 0)
#   mode2_without_a_gate_outcome          5 rows 3,4,5,7,8 (row 6 has a gate)
#   by_precedent_with_no_coregistration   3 rows 4,5,7     (BY_PRECEDENT and n_both == 0;
#                                                           rows 1,6,9 are BY_PRECEDENT
#                                                           with 3, 4 and 5)
#   rows_with_a_fallback_namespace_id     1 row 10         (id 2, outside GENUINE)
#
# The three mode buckets are 2 / 6 / 3 rather than 2 / 6 / 2 so that swapping
# the MODE_1 test for the isna() test is also a red.
EXPECTED = {
    "rows": 11,
    "rows_mode_1": 2,
    "rows_mode_2": 6,
    "rows_no_mode": 3,
    "mode2_unreachable": 4,
    "mode2_reachable": 2,
    "mode2_without_a_gate_outcome": 5,
    "by_precedent_with_no_coregistration": 3,
    "rows_with_a_fallback_namespace_id": 1,
}


@pytest.fixture
def artifacts(tmp_path):
    """A findings csv and an extract dir, written the way the real ones are.

    The csv goes through `to_csv`/`read_csv` rather than being handed over as a
    frame, because that round trip is where `mode` and `gate` acquire the NaNs
    that `isna()` counts, and `measure` is only ever called on a re-read file.
    """
    findings = tmp_path / "findings.csv"
    pd.DataFrame(FINDINGS_ROWS, columns=FINDINGS_COLUMNS).to_csv(findings, index=False)

    extract = tmp_path / "extract"
    extract.mkdir()
    assays = pd.DataFrame(
        [(1, "Comet Chip", None, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
         (2, "Tissue Collection", None, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
         # no junction row, so no internal id: dropna() must drop it, leaving
         # {11, 12} genuine and making a proposal of `2` a fallback.
         (3, "Patient Visit", None, 3, 2, 10, "MIT_SRP", None, None)],
        columns=S.ASSAY_COLUMNS,
    )
    assays.to_parquet(extract / "assays.parquet", index=False)
    return str(findings), str(extract)


def test_measure_returns_exactly_the_keys_it_prints(artifacts):
    """A key `measure` gains but `BASELINE_KEYS` does not is never printed.

    `main` iterates `BASELINE_KEYS`, so the missing direction raises `KeyError`
    on its own. This is the other direction, which is silent.
    """
    assert set(B.measure(*artifacts)) == set(B.BASELINE_KEYS)


def test_baseline_keys_has_no_duplicates():
    assert len(B.BASELINE_KEYS) == len(set(B.BASELINE_KEYS))


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_every_key_counts_what_it_names(artifacts, key):
    assert B.measure(*artifacts)[key] == EXPECTED[key]


def test_the_mode_buckets_partition_the_frame(artifacts):
    """The identity the baseline document tells a re-runner to re-check."""
    got = B.measure(*artifacts)
    assert got["rows_mode_1"] + got["rows_mode_2"] + got["rows_no_mode"] == got["rows"]


def test_the_reachability_buckets_partition_mode_2(artifacts):
    """The second documented identity -- and the one the `== 0` / `> 0` swap
    leaves intact, which is exactly why the per-key assertions above carry
    different expected values for the two halves."""
    got = B.measure(*artifacts)
    assert got["mode2_unreachable"] + got["mode2_reachable"] == got["rows_mode_2"]


def test_the_two_reachability_counts_differ_so_a_swap_is_detectable(artifacts):
    """Guards the fixture, not the module.

    If someone rebalances FINDINGS_ROWS until these two are equal, swapping the
    two expressions in `measure` becomes undetectable and the per-key tests go
    quietly toothless. This fails first and says why.
    """
    assert EXPECTED["mode2_unreachable"] != EXPECTED["mode2_reachable"]
    got = B.measure(*artifacts)
    assert got["mode2_unreachable"] != got["mode2_reachable"]


def test_main_prints_every_key_and_returns_zero(artifacts, capsys):
    findings, extract = artifacts
    assert B.main(findings, extract) == 0
    out = capsys.readouterr().out
    for key in B.BASELINE_KEYS:
        assert f"`{key}`" in out
    assert out.startswith("| key | rows |\n|---|---|\n")
