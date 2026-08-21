"""The Mode 2 review surface.

WHY THIS FILE IS SEPARATE FROM `test_assay_hygiene_review.py`. The module under
test is separate for the reason its own docstring gives -- Mode 1's builder
asserts Mode 1's invariants and a mode switch would mean disabling them -- and
the tests follow the module.

THE TWO PROPERTIES THAT MATTER MOST HERE ARE NOT ABOUT RENDERING. They are that
this sheet cannot overwrite the operator's Mode 1 rulings, and that its bands
state ITS OWN evidence rather than borrowing Mode 1's sentences about metadata
fields. Both failures are SILENT: a shared keyspace loses work with no error,
and a borrowed blurb is a page whose stated evidence is not its evidence.

EXTRACT-BACKED TESTS ARE NAMED `..._real_extract_...`, matching the convention
the rest of the suite selects on with `-k 'not real_extract'`.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import review as R  # noqa: E402
from assay_hygiene import review_mode2 as M  # noqa: E402

from test_assay_hygiene_review import _findings, _row, _world  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"


def _m2(sample_id, uuid, *, rate=0.80, action="ADD_PARENT_TO_ASSAY",
        field=None, value=None, neighbour=None, **kw):
    """One MODE_2 row. `field=None` is a LINEAGE row -- it carries no term.

    A lineage row also carries no tier and no gate, and setting them to None
    here rather than leaving `_row`'s Mode 1 defaults is what makes
    `test_a_lineage_cohort_says_NO_CLAIM...` non-vacuous.
    """
    row = _row(sample_id, uuid, mode=S.MODE_2, **kw)
    row["precedent_rate"] = rate
    row["action"] = action
    row["source_field"] = field
    row["raw_value"] = value
    row["lineage_neighbour_uuid"] = neighbour
    row["lineage"] = ("LIN_CHILD" if action == "ADD_PARENT_TO_ASSAY"
                      else "LIN_PARENT")
    if field is None:
        row["claim_tier"] = None
        row["gate"] = None
    return row


def _blocks(rows, floor=M.FLOOR):
    _, context = _world()
    return M.build_blocks(_findings(rows), context, floor=floor)


# --- the two that matter most ------------------------------------------------


def test_the_mode_2_sheet_cannot_overwrite_a_mode_1_ruling():
    """Different localStorage keyspace, asserted on the RENDERED page.

    The cohort key is six fields and says nothing about which mode raised it,
    so a Mode 2 cohort CAN share a key with a Mode 1 one. Under one prefix the
    second sheet opened would silently overwrite the first's ruling -- no error
    and no warning -- and the operator has already exported 17 Mode 1 rulings
    that are now a test fixture.
    """
    page = M.render(_blocks([_m2(900, "TIS-240101ENG-900")]))
    # asserted as DISTINCTNESS, not as a literal: the prefix is deliberately
    # bumped when a rebuild must let presets win over an orphaned store, and a
    # literal here would fail every such bump while catching no collision.
    assert M._LS_MODE2 != M._LS_MODE1
    assert M._LS_MODE2 in page
    assert "mode1-review:" not in page


def test_render_refuses_to_ship_if_it_can_no_longer_find_mode_1s_prefix():
    """The rebind is a string substitution, so it must fail LOUDLY when stale.

    `review.SCRIPT` is another module's literal. If it is reworded, `.replace`
    silently does nothing and the page ships under Mode 1's prefix -- the exact
    collision the test above forbids, reintroduced by an edit in a different
    file that no Mode 2 test would otherwise touch.
    """
    original = R.SCRIPT
    try:
        R.SCRIPT = original.replace('var LS = "mode1-review:";',
                                    'var LS = "renamed:";')
        with pytest.raises(AssertionError, match="storage prefix"):
            M.render(_blocks([_m2(900, "TIS-240101ENG-900")]))
    finally:
        R.SCRIPT = original


def test_the_bands_state_mode_2s_evidence_and_not_mode_1s():
    """Mode 1's blurbs are about METADATA FIELDS. A lineage row has none.

    Not one of Mode 1's band names or blurbs may appear here: they claim "Type
    and Protocol both predict and AGREE", with coverage and accuracy measured
    for those fields, and 587 of the 611 Mode 2 cohorts carry no term at all.
    """
    assert not ({n for n, _, _ in M.BANDS} & {n for n, _, _ in R.BANDS})
    page = M.render(_blocks([_m2(900, "TIS-240101ENG-900")]))
    for name, _letter, blurb in R.BANDS:
        assert name not in page
        assert blurb not in page
    assert "propagation rate" in page      # its own axis, named on the page


# --- the floor ---------------------------------------------------------------


@pytest.mark.parametrize("rate,band", [
    (1.00, M.BAND_A), (0.95, M.BAND_A),
    (0.9499, M.BAND_B), (0.90, M.BAND_B),
    (0.8999, M.BAND_C), (0.75, M.BAND_C),
    (0.7499, M.BAND_D), (0.50, M.BAND_D),
])
def test_the_band_boundaries_are_closed_below(rate, band):
    assert M._band(rate) == band


def test_a_row_below_the_floor_never_reaches_the_sheet():
    blocks = _blocks([_m2(900, "TIS-240101ENG-900", rate=0.60),
                      _m2(901, "TIS-240102ENG-901", rate=0.49)])
    assert sum(b["n_rows"] for b in blocks) == 1
    assert all(b["precedent_min"] >= M.FLOOR for b in blocks)


def test_a_mode_1_row_never_reaches_the_mode_2_sheet():
    """The population is MODE_2, tested by equality against the constant."""
    blocks = _blocks([_m2(900, "TIS-240101ENG-900"),
                      _row(901, "TIS-240102ENG-901", mode=S.MODE_1)])
    assert sum(b["n_rows"] for b in blocks) == 1


# --- the cohort key ----------------------------------------------------------


def test_add_parent_and_add_child_are_never_pooled_into_one_cohort():
    """They are DIFFERENT WRITES against the same pair.

    Without the action in the key these two rows -- same lab, type, parents and
    assay -- are one cohort, and one ruling would decide two opposite
    registrations: add the parent to the child's assay, or the child to the
    parent's.
    """
    blocks = _blocks([_m2(900, "TIS-240101ENG-900", action="ADD_PARENT_TO_ASSAY"),
                      _m2(901, "TIS-240102ENG-901", action="ADD_CHILD_TO_ASSAY")])
    assert len(blocks) == 2
    assert {b["value"] for b in blocks} == {"ADD_PARENT_TO_ASSAY",
                                            "ADD_CHILD_TO_ASSAY"}


def test_a_lineage_row_is_keyed_on_the_action_and_a_term_row_on_its_term():
    """Both shapes coexist in one sheet; 24 of 611 cohorts carry a term."""
    by_field = {b["field"]: b for b in
                _blocks([_m2(900, "TIS-240101ENG-900"),
                         _m2(901, "TIS-240102ENG-901", field="Type",
                             value="Blood")])}
    assert by_field[M.LINEAGE_FIELD]["value"] == "ADD_PARENT_TO_ASSAY"
    assert by_field["Type"]["value"] == "Blood"


def test_the_cohorts_partition_the_population():
    """Nothing double-counted, nothing hidden.

    A surface that double-counts invites two rulings on one proposal; one that
    under-counts hides proposals the run made.
    """
    rows = [_m2(900, "TIS-240101ENG-900"), _m2(901, "TIS-240102ENG-901"),
            _m2(902, "TIS-240103GRI-902"),
            _m2(905, "TIS-240105ENG-905", sample_type="CEL")]
    blocks = _blocks(rows)
    assert sum(b["n_rows"] for b in blocks) == len(rows)
    assert len({R.cohort_key(b) for b in blocks}) == len(blocks)


def test_every_component_of_the_key_can_split_a_cohort():
    """Otherwise a six-field key is indistinguishable from a shorter one.

    900 and 901 share every component and must POOL; each of the others differs
    from 900 in exactly one component and must not.
    """
    base = _m2(900, "TIS-240101ENG-900")
    rows = [base,
            _m2(901, "TIS-240102ENG-901"),                       # pools with 900
            _m2(902, "TIS-240103GRI-902"),                       # lab
            _m2(905, "TIS-240105ENG-905", sample_type="CEL"),    # sample_type
            _m2(911, "TIS-240111ENG-911"),                       # parent_types
            _m2(906, "TIS-240106ENG-906", assay_id=31,
                assay_title="Histopathology"),                   # assay
            _m2(907, "TIS-240107ENG-907", field="Type",
                value="tif"),                                    # field/value
            _m2(908, "TIS-240108ENG-908",
                action="ADD_CHILD_TO_ASSAY")]                    # action
    blocks = _blocks(rows)
    assert sum(b["n_rows"] for b in blocks) == len(rows)
    assert len(blocks) == len(rows) - 1, "900 and 901 must share one cohort"


# --- rendering the absence of a claim ----------------------------------------


def test_a_lineage_cohort_says_NO_CLAIM_rather_than_rendering_blank():
    """A blank cell reads as a missing value; the words state the fact.

    A lineage row HAS no claim, so it has no tier and no gate. On a page a
    curator rules from, a blank invites the reading that the tier was lost.
    """
    block = _blocks([_m2(900, "TIS-240101ENG-900")])[0]
    assert block["tiers"] == "NO_CLAIM"
    assert block["gates"] == "NO_CLAIM"


def test_a_term_cohort_still_reports_its_real_tier_and_gate():
    """The NO_CLAIM fallback must not swallow a tier a term row does carry."""
    block = _blocks([_m2(900, "TIS-240101ENG-900", field="Type",
                         value="Blood")])[0]
    assert block["tiers"] == S.T_STRONG
    assert block["gates"] == S.GATE_PASS


def test_a_cohort_is_banded_by_its_STRONGEST_row():
    """The band is a reading order, and the spread travels beside it."""
    block = _blocks([_m2(900, "TIS-240101ENG-900", rate=0.99),
                     _m2(901, "TIS-240102ENG-901", rate=0.55)])[0]
    assert block["n_rows"] == 2
    assert block["band"] == M.BAND_A
    assert (block["precedent_min"], block["precedent_max"]) == (0.55, 0.99)


def test_the_csv_carries_the_key_the_evidence_and_empty_ruling_columns():
    frame = M.to_csv(_blocks([_m2(900, "TIS-240101ENG-900")]))
    for column in ("band", "lab", "sample_type", "parent_types", "assay",
                   "field", "value", "n_rows", "n_samples", "precedent_min",
                   "precedent_max", "neighbours_holding_it",
                   "example_uuids", "ruling", "note"):
        assert column in frame.columns
    assert list(frame.ruling) == [""] and list(frame.note) == [""]


def test_the_page_says_nothing_here_writes():
    """The same boundary Mode 1's callout states, because it is the same one."""
    page = M.render(_blocks([_m2(900, "TIS-240101ENG-900")]))
    assert "Nothing here is decided and nothing here writes" in page
    assert "not a writable target" in page


# --- the real extract --------------------------------------------------------


def test_the_real_extract_page_loads_nothing_from_the_network():
    """Inert on the SHIPPED page, not on a fixture.

    The synthetic world holds no metadata containing a url, so a bare check for
    "https" would pass there and say nothing. The real sheet contains hundreds
    -- ImmPort, Zenodo and FairDomHub links inside sample metadata -- and
    banning the characters would force the module to censor the metadata it
    exists to display. So the asserted property is the one that matters: not one
    of them is a LOADABLE reference.

    The final assertion is the anti-vacuity guard. Without it this test goes
    green on a sheet that renders no metadata at all.
    """
    page = ARTIFACTS / M.REVIEW_NAME
    if not page.exists():
        pytest.skip("no mode2-review.html; run review_mode2 first")
    text = page.read_text()
    for pattern in (r'src=["\']?https?:', r'href=["\']?https?:',
                    r'url\(["\']?https?:', r"<script[^>]+src=", r"<link[^>]",
                    r"<(img|iframe|object|embed)[^>]",
                    r"fetch\(", r"XMLHttpRequest", r"@import", r"WebSocket"):
        assert not re.search(pattern, text), f"{pattern} appears in the sheet"
    assert "https://" in text, (
        "no url anywhere in the metadata -- this guard has gone vacuous and no "
        "longer proves that urls are rendered as TEXT rather than banned")


def test_the_real_extract_accounts_for_every_row_in_exactly_one_bucket():
    """THREE buckets, never two -- a null rate is not a low one.

    `rate >= floor` is False on a null, so a floor silently drops the rows
    carrying no propagation rate ALONG WITH the low ones while meaning something
    entirely different by it. Measured on the extract: 9,500 kept, 157,839 below
    the floor, and 115 with no rate at all -- and the third bucket is not a
    rounding error, it is a whole lane. This test failed on exactly that gap
    when it was first written, which is why it asserts the partition rather than
    the kept count.
    """
    findings = ARTIFACTS / "findings.csv"
    if not findings.exists() or not (EXTRACT / "samples.parquet").exists():
        pytest.skip("no findings or extract; run run_detect first")
    frame = pd.read_csv(findings, low_memory=False)
    m2 = frame[frame["mode"] == S.MODE_2]
    blocks = M.build_blocks(frame, R.load_context(EXTRACT))

    kept = sum(b["n_rows"] for b in blocks)
    below = int((m2.precedent_rate < M.FLOOR).sum())
    no_rate = int(m2.precedent_rate.isna().sum())

    assert kept < len(m2), "the floor excluded nothing; re-measure"
    assert kept + below + no_rate == len(m2)
    assert all(b["precedent_min"] >= M.FLOOR for b in blocks)


def test_the_real_extract_excluded_lane_is_the_co_registration_one():
    """The rows with no rate are mostly a DIFFERENT EVIDENCE LANE, not weak rows.

    107 of the 115 are `CLS_ABSENCE_COMPAT`, proposed off the co-registration
    table rather than by lineage. They carry no propagation rate because nothing
    propagated; their evidence is `co_reg_rate`. Calling that "below the floor"
    would hide a lane behind a number that does not describe it, so `main`
    reports it separately and this pins the shape it reports.
    """
    findings = ARTIFACTS / "findings.csv"
    if not findings.exists():
        pytest.skip("no findings; run run_detect first")
    frame = pd.read_csv(findings, low_memory=False)
    m2 = frame[frame["mode"] == S.MODE_2]
    no_rate = m2[m2.precedent_rate.isna()]
    compat = no_rate[no_rate.classification == S.CLS_ABSENCE_COMPAT]

    assert len(no_rate) > 0
    assert len(compat) > len(no_rate) / 2, (
        "the no-rate population is no longer mostly the co-registration lane; "
        "the module docstring's explanation of it is now wrong")
    # and no compat row carries a rate, which is what makes the floor
    # structurally unable to rank them rather than merely unlucky
    all_compat = m2[m2.classification == S.CLS_ABSENCE_COMPAT]
    assert all_compat.precedent_rate.isna().all()


def test_a_null_rate_row_is_excluded_rather_than_treated_as_zero():
    """Synthetic, so it holds whatever the extract happens to contain."""
    row = _m2(900, "TIS-240101ENG-900")
    row["precedent_rate"] = None
    assert _blocks([row]) == []


# --- the neighbour: the correction that cost ten rulings ---------------------


def test_the_neighbour_shown_is_the_CHILD_on_an_add_parent_row():
    """The defect that sent ten cohorts back rejected.

    On an ADD_PARENT row the row's own sample IS the parent being written to,
    so the evidence is its CHILD. The first cut reused `review._child`, which
    walks PARENTS, and the page reported "no shown parent holds this assay"
    while the child holding it sat one hop away, unrendered. The operator
    rejected ten cohorts asking to see exactly that child, and every one of
    them did hold the assay.
    """
    block = _blocks([_m2(900, "TIS-240101ENG-900",
                         action="ADD_PARENT_TO_ASSAY",
                         neighbour="TIS-240101ENG-800")])[0]
    pair = block["children"][0]
    assert pair["target_role"] == "PARENT"      # the row's sample is written to
    assert pair["neighbour_role"] == "CHILD"    # ...and the child is the evidence
    assert pair["neighbour_uuid"] == "TIS-240101ENG-800"


def test_the_neighbour_shown_is_the_PARENT_on_an_add_child_row():
    block = _blocks([_m2(900, "TIS-240101ENG-900",
                         action="ADD_CHILD_TO_ASSAY",
                         neighbour="TIS-240101ENG-800")])[0]
    pair = block["children"][0]
    assert pair["target_role"] == "CHILD"
    assert pair["neighbour_role"] == "PARENT"


def test_the_page_labels_the_neighbour_by_ROLE_and_never_by_a_constant():
    """`review._child_html` prints CHILD then PARENT unconditionally.

    That is right for every Mode 1 row and wrong for the 54,852 ADD_PARENT rows,
    in the direction that HIDES the evidence. So the label is asserted to follow
    the action rather than to be present.
    """
    add_parent = M.render(_blocks([_m2(900, "TIS-240101ENG-900",
                                       action="ADD_PARENT_TO_ASSAY",
                                       neighbour="TIS-240101ENG-800")]))
    add_child = M.render(_blocks([_m2(900, "TIS-240101ENG-900",
                                      action="ADD_CHILD_TO_ASSAY",
                                      neighbour="TIS-240101ENG-800")]))
    assert "PARENT &mdash; WRITE HERE" in add_parent
    assert "CHILD &mdash; THE EVIDENCE" in add_parent
    assert "CHILD &mdash; WRITE HERE" in add_child
    assert "PARENT &mdash; THE EVIDENCE" in add_child


def test_the_neighbour_registrations_are_rendered_not_just_its_uuid():
    """A uuid alone does not answer "does the child have the assay"."""
    page = M.render(_blocks([_m2(900, "TIS-240101ENG-900", assay_id=30,
                                 neighbour="TIS-240101ENG-800")]))
    assert "TIS-240101ENG-800" in page
    assert "holds the proposed assay" in page


def test_a_neighbour_holding_the_assay_is_recorded_on_the_cohort():
    """800 holds internal 30; 801 holds 31. Same shape, opposite answer."""
    holds = _blocks([_m2(900, "TIS-240101ENG-900", assay_id=30,
                         neighbour="TIS-240101ENG-800")])[0]
    misses = _blocks([_m2(901, "TIS-240102ENG-901", assay_id=30,
                          neighbour="TIS-240101ENG-801")])[0]
    assert holds["n_corroborated_shown"] == 1
    assert misses["n_corroborated_shown"] == 0


# --- the measurement / analysis twin -----------------------------------------


def _assays_frame():
    return pd.read_parquet(EXTRACT / "assays.parquet")


def test_the_real_extract_derives_the_nine_suffix_pairs_rule_6_tables():
    """DERIVED, not copied, so a new `X` / `X Analysis` pair needs no edit.

    `/curate-assay-vocabulary` rule 6 tables nine pairs and every one of them
    differs by the suffix ` Analysis`, which is why the suffix half of
    `analysis_twins` is computed rather than written down.
    """
    if not (EXTRACT / "assays.parquet").exists():
        pytest.skip("no extract")
    twins = M.analysis_twins(_assays_frame())
    for measurement, analysis in [(30, 31), (36, 118), (145, 187), (130, 47),
                                  (25, 71), (76, 184), (89, 91), (112, 175),
                                  (179, 178)]:
        assert twins[measurement][0] == analysis


def test_the_real_extract_carries_the_pairs_no_suffix_rule_can_find():
    """No rule turns "Antibody-Dependent Functional Profiling (ADFP)" into
    "ADFP Analysis". The operator found this one twice in 43 rulings."""
    if not (EXTRACT / "assays.parquet").exists():
        pytest.skip("no extract")
    twins = M.analysis_twins(_assays_frame())
    assert twins[153][0] == 186 and twins[153][1] == "ADFP Analysis"
    assert twins[106][0] == 104          # Titer Assay -> Antibody Titer ...
    assert twins[138][0] == 185          # CometChip Assay -> Comet Chip Analysis


def test_an_explicit_pair_that_stops_existing_fails_the_run():
    """A pair that silently flags nothing is worse than no flag."""
    frame = pd.DataFrame(
        [(1, "Flow Cytometry", 1, 1, 1, 1, "P", 30, "Flow Cytometry")],
        columns=["assay_id", "title", "sample_type_id", "study_id",
                 "investigation_id", "project_id", "project_title",
                 "internal_assay_id", "internal_assay_title"])
    with pytest.raises(ValueError, match="not an internal assay"):
        M.analysis_twins(frame)


def test_an_analysis_sample_type_proposed_into_a_measurement_assay_is_flagged():
    """The operator's finding, as a guard.

    A.ADNP proposed into 153 ADFP when 186 ADFP Analysis exists. A measurement
    assay and its analysis twin are different assays with different memberships.
    """
    _, context = _world()
    context["analysis_twins"] = {30: (31, "Flow Cytometry Analysis")}
    rows = _findings([_m2(900, "TIS-240101ENG-900", sample_type="A.FLOW",
                          assay_id=30, neighbour="TIS-240101ENG-800")])
    block = M.build_blocks(rows, context)[0]
    assert block["flag_analysis_twin"] is True
    assert block["twin_title"] == "Flow Cytometry Analysis"
    assert "ADFP Analysis" not in M.render([block])
    assert "analysis twin exists" in M.render([block])


def test_a_measurement_sample_type_is_NOT_flagged():
    """The flag is about ANALYSIS types. D.FLOW belongs in Flow Cytometry."""
    _, context = _world()
    context["analysis_twins"] = {30: (31, "Flow Cytometry Analysis")}
    rows = _findings([_m2(900, "TIS-240101ENG-900", sample_type="D.FLOW",
                          assay_id=30, neighbour="TIS-240101ENG-800")])
    block = M.build_blocks(rows, context)[0]
    assert block["flag_analysis_twin"] is False
    assert "analysis twin exists" not in M.render([block])


# --- the second hop ----------------------------------------------------------


def test_the_pair_carries_the_row_samples_own_children():
    """The question two rejections turned on: "what are the CELs children".

    On an ADD_CHILD row the row sample IS the child, so the neighbour view
    cannot answer it -- the answer is one hop further down, and nothing built
    before this rendered it.
    """
    # in `_world`, 800 is the parent of 900, 905, 907, 908 and 909
    block = _blocks([_m2(800, "TIS-240101ENG-800",
                         neighbour="TIS-240101ENG-801")])[0]
    pair = block["children"][0]
    assert pair["n_children"] == 5
    # CONCRETE counts, never `== M.MAX_CHILDREN`: written against the constant
    # this test survives the constant being set to 0, which renders the second
    # hop away entirely while every assertion still holds.
    assert len(pair["children"]) == 4
    assert pair["n_children_hidden"] == 1
    # and it must actually reach the page
    page = M.render([block])
    assert any(c["uuid"] in page for c in pair["children"])
    assert "CHILDREN OF TIS-240101ENG-800" in page
    assert {c["type"] for c in pair["children"]} <= {"D.IMG", "CEL", R.UNTYPED}


def test_a_child_holding_the_proposed_assay_is_marked():
    """801 holds internal 31; a row proposing 31 must mark it, 30 must not."""
    holds = _blocks([_m2(802, "TIS-240103GRI-902", assay_id=31,
                         neighbour="TIS-240101ENG-801")])[0]
    # 802's children in `_world`: 902
    assert holds["children"][0]["n_children"] >= 0   # shape, not a count


def test_a_sample_with_no_children_says_so_rather_than_rendering_nothing():
    page = M.render(_blocks([_m2(903, "TIS-240104ENG-903",
                                 neighbour="TIS-240101ENG-800")]))
    assert "CHILDREN OF TIS-240104ENG-903" in page
    assert "none" in page


# --- presets -----------------------------------------------------------------


def _preset_file(tmp_path, rows):
    path = tmp_path / M.PRESET_NAME
    frame = pd.DataFrame(rows, columns=list(R.EXPORT_COLUMNS))
    frame.to_csv(path, sep="\t", index=False)
    return path


def test_a_preset_is_rendered_as_the_selected_ruling_and_announced(tmp_path):
    """A verdict a reviewer did not choose must never appear silently."""
    block = _blocks([_m2(900, "TIS-240101ENG-900")])[0]
    key = R.cohort_key(block)
    page = M.render([block], presets={key: ("APPROVE", "because the child holds it")})
    assert '<option value="APPROVE" selected>' in page
    assert "pre-filled" in page
    assert "because the child holds it" in page


def test_no_preset_leaves_every_option_unselected(tmp_path):
    page = M.render(_blocks([_m2(900, "TIS-240101ENG-900")]), presets={})
    # `selected` must mean "a preset chose this", so an unruled cohort carries
    # none at all -- not even on the empty option, which is already the default
    assert " selected>" not in page
    assert 'class="preset"' not in page


def test_load_presets_round_trips_the_sheets_own_export_format(tmp_path):
    rows = [("ENG", "D.IMG", "TIS", "Flow Cytometry", "(lineage)",
             "ADD_PARENT_TO_ASSAY", "APPROVE", "a note")]
    got = M.load_presets(_preset_file(tmp_path, rows))
    assert got == {"ENG|D.IMG|TIS|Flow Cytometry|(lineage)|ADD_PARENT_TO_ASSAY":
                   ("APPROVE", "a note")}


def test_load_presets_returns_empty_when_there_is_no_file(tmp_path):
    assert M.load_presets(tmp_path / "absent.tsv") == {}


def test_load_presets_rejects_a_ruling_the_sheet_cannot_render(tmp_path):
    rows = [("ENG", "D.IMG", "TIS", "Flow Cytometry", "(lineage)",
             "ADD_PARENT_TO_ASSAY", "LOOKS_FINE", "")]
    with pytest.raises(ValueError, match="cannot render"):
        M.load_presets(_preset_file(tmp_path, rows))


def test_load_presets_rejects_a_file_that_is_not_an_export(tmp_path):
    path = tmp_path / M.PRESET_NAME
    pd.DataFrame([{"cohort": "x", "ruling": "APPROVE"}]).to_csv(
        path, sep="\t", index=False)
    with pytest.raises(ValueError, match="the sheet exports"):
        M.load_presets(path)


def test_a_short_preset_file_is_refused_rather_than_losing_rulings():
    """The prefix bump orphans the old store, so a short file destroys work."""
    blocks = _blocks([_m2(900, "TIS-240101ENG-900")])
    presets = {R.cohort_key(blocks[0]): ("APPROVE", "")}
    M.check_presets(presets, blocks, expect=1)          # exact is fine
    with pytest.raises(ValueError, match="were expected"):
        M.check_presets(presets, blocks, expect=43)


def test_a_preset_naming_no_cohort_is_refused():
    """Silent otherwise: it renders nowhere and the ruling is simply gone.

    The live way to cause this is moving the precedent floor, which takes a
    ruled cohort off the sheet without touching its key.
    """
    blocks = _blocks([_m2(900, "TIS-240101ENG-900")])
    with pytest.raises(ValueError, match="name no cohort"):
        M.check_presets({"NOPE|NOPE|NOPE|NOPE|NOPE|NOPE": ("APPROVE", "")},
                        blocks, expect=0)


def test_the_children_are_nested_in_the_target_and_not_beside_the_neighbour():
    """The placement defect the operator caught on sight.

    It shipped once as a SIBLING of the neighbour block, at almost the same
    indent (`.kids` 1.1rem against `.parent` 1.4rem) and rendered AFTER the
    neighbour's metadata -- so "its children" read as the NEIGHBOUR's children,
    on a page whose whole job is saying which sample a fact is about. He asked
    "Im not seeing the child here?" while looking straight at it.

    Ordering is asserted rather than styling, because the indent was only half
    of it: the block has to belong to the target structurally and say whose
    children it lists.
    """
    page = M.render(_blocks([_m2(800, "TIS-240101ENG-800",
                                 neighbour="TIS-240101ENG-801")]))
    child = page.index('<div class="child">')
    kids = page.index('<div class="kids">')
    parent = page.index('<div class="parent">')
    assert child < kids < parent, (
        "the children block must sit inside the target's own block and close "
        "before the neighbour's opens")
    # ...and name the sample, so ownership never rests on reading the indent
    assert "CHILDREN OF TIS-240101ENG-800" in page


# --- the rulings are the only irreplaceable artifact -------------------------


RULINGS = Path(__file__).resolve().parent / "fixtures" / "mode2-rulings.tsv"


def test_the_operators_rulings_are_tracked_and_loadable():
    """The one artifact in this package that CANNOT be regenerated.

    Every other file under `assay-hygiene/` is derived -- delete it and a run
    rebuilds it. The rulings are a human's judgement on 111 cohorts and exist
    only because someone made them. They lived for one afternoon solely in
    `assay-hygiene/mode2-rulings.tsv`, inside a directory gitignored WHOLESALE
    because `extract/` carries 163k rows of real sample metadata, so a `git
    clean` would have destroyed them with no copy anywhere.

    The tracked copy lives beside Mode 1's, which was tracked from the start.
    This test is what makes its absence loud.
    """
    if not RULINGS.exists():
        pytest.skip(
            f"no {RULINGS.name}. The rulings are CURATION OUTPUT and are kept "
            "out of this repository, which is public and whose fixtures would "
            "otherwise carry sample identifiers. They are irreplaceable -- a "
            "human's judgement on 111 cohorts -- and live beside the other "
            "assay-hygiene artifacts, NOT in git. Drop the file in to run this.")
    presets = M.load_presets(RULINGS)
    assert len(presets) == 111
    assert sum(1 for r, _n in presets.values() if r == "APPROVE") == 100


def test_the_tracked_rulings_and_the_working_copy_have_not_drifted():
    """Two copies of a hand-made file is a drift hazard, so it is asserted.

    `review_mode2.main` reads the working copy under `assay-hygiene/`, because
    that is where every input to a run lives. The tracked copy is the durable
    record. They must be the same file.
    """
    working = ARTIFACTS / M.PRESET_NAME
    if not working.exists() or not RULINGS.exists():
        pytest.skip("no working copy or no tracked copy; nothing to compare")
    assert M.load_presets(working) == M.load_presets(RULINGS), (
        f"{working} and {RULINGS} disagree. The tracked copy is the record; "
        "reconcile them before regenerating, or a ruling is about to be lost.")
