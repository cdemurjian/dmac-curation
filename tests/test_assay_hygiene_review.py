"""Task 10: the Mode 1 review sheet, and the defects it has already shipped.

A TEST OVER GENERATED HTML IS WHERE A VACUOUS ASSERTION HIDES. `assert "note"
in html` passes on a document whose notes field is unreachable, whose buttons
have no handlers and whose storage listener threw at load. That is not
hypothetical: it is exactly what shipped, and the whole first half of this file
exists to make each of those states RED rather than green.

THE DEFECT THAT MOTIVATES `test_no_class_token_is_shared_by_a_structural_and_an
_interactive_element`. The prototype styled a band blurb as `<p class="note">`
and the per-cohort notes field as `<textarea class="note">`. The script then
ran `document.querySelectorAll(".dec, .note")`, which swept up the paragraphs;
`el.closest(".notes")` returned `null` on the FIRST paragraph; `paint(null)`
threw; and the throw aborted the `forEach` before a single storage listener or
either button handler was attached. The page still looked right, still accepted
typing into every textarea, and saved nothing while both buttons did nothing.
A substring test for "Export notes" was green through all of it.

So the class-token check is structural rather than textual: it parses the
rendered document, collects the tags each class token appears on, and refuses
any token that is worn by both a form control and a non-control. That fails on
the shipped bug without anyone having to remember it was the word "note".

THE SECOND DEFECT is a sandboxed viewer. `window.localStorage` THROWS
`SecurityError` rather than returning null when the page is opened from a
sandboxed frame or with site data blocked, and an unguarded throw at load time
aborts the rest of the script -- the same silent-dead-form outcome by a
different route. `test_every_storage_call_is_guarded...` brace-matches the
script and requires every storage access to sit inside a `try` body, and
requires the page to SAY so when storage is unavailable rather than pretending
the notes are safe.

THE THIRD is the reason the builder takes a frame and not a path. An earlier
form of this sheet was three scripts reading each other's csv, and it went
inconsistent twice -- once emitting assay 31 "Flow Cytometry Analysis" in the
review context where `findings.csv` said assay 30 "Flow Cytometry".
`test_the_sheet_is_built_from_the_frame_and_never_from_a_file_this_run_wrote`
plants exactly that disagreement on disk and requires the frame to win.

EXTRACT-BACKED TESTS ARE NAMED `..._real_extract_...`, matching the convention
in `test_assay_hygiene_run_detect.py`: this suite selects its fast lane with
`-k 'not real_extract'` against the test NAME, so a `pytest.mark` would be an
unregistered marker no mutation harness honours.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from assay_hygiene import _schema as S  # noqa: E402
from assay_hygiene import review as R  # noqa: E402
from assay_hygiene import run_detect as RD  # noqa: E402
from assay_hygiene import vocabulary as V  # noqa: E402

EXTRACT = REPO / "assay-hygiene" / "extract"
ARTIFACTS = REPO / "assay-hygiene"
RULINGS = Path(__file__).resolve().parent / "fixtures" / "mode1-rulings.tsv"

# Form controls. The distinction this file polices is between an element a
# curator TYPES INTO and one that merely renders, because the shipped defect
# was one class token worn by both.
CONTROLS = {"select", "textarea", "input", "button", "option"}


# --- a tiny world ------------------------------------------------------------
#
# HAND-BUILT HERE RATHER THAN IMPORTED. `test_assay_hygiene_classify._world` is
# a census fixture whose every count is traced in its docstring; it carries two
# Mode 1 labs and no lineage of its own, so a cohort test built on it would be
# asserting against one group. This world exists to make the COHORT KEY
# discriminate -- two labs, two sample types, two parent shapes, two terms --
# and it holds no counts anyone else depends on.


def _findings(rows) -> pd.DataFrame:
    """A findings frame with every `FINDING_COLUMNS` name present.

    The real frame arrives off `findings.csv` with all 37 columns, and a
    builder that happens to work on a 9-column frame and raises `KeyError` on
    the real one is a test passing for the wrong reason.
    """
    frame = pd.DataFrame(rows)
    for col in S.FINDING_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    return frame[S.FINDING_COLUMNS]


def _row(sample_id, uuid, *, sample_type="D.IMG", assay_id=30,
         assay_title="Flow Cytometry", field="Type", value="tif",
         tier=S.T_STRONG, contested=False, gate=S.GATE_PASS,
         mode=S.MODE_1, projects="3", purity=1.0, type_regs=12):
    return {
        "sample_id": sample_id, "uuid": uuid, "sample_type": sample_type,
        "project_ids": projects, "proposed_internal_assay_id": assay_id,
        "proposed_internal_assay_title": assay_title, "mode": mode,
        "classification": S.CLS_ABSENCE_COMPAT, "gate": gate,
        "claim_tier": tier, "contested": contested, "source_field": field,
        "raw_value": value, "vocab_purity": purity,
        "type_registrations": type_regs, "action": "ADD_REGISTRATION",
    }


def _world():
    """-> (findings, context). NINE Mode 1 rows over EIGHT cohorts.

    EVERY ONE OF THE SIX KEY COMPONENTS SEPARATES A PAIR HERE, which is what
    makes `test_dropping_any_component_of_the_key_collapses_a_cohort` able to
    say anything: a world where one component never varies cannot tell a
    six-field key from a five-field one.

        sid  uuid                 lab  type   parents     assay          field/value
        900  TIS-240101ENG-900    ENG  D.IMG  800 TIS     30 Flow Cyt.   Type/tif
        901  TIS-240102ENG-901    ENG  D.IMG  801 TIS     30 Flow Cyt.   Type/tif
        902  TIS-240103GRI-902    GRI  D.IMG  802 TIS     30 Flow Cyt.   Type/tif
        903  TIS-240104ENG-903    ENG  D.IMG  none        30 Flow Cyt.   Type/tif
        905  TIS-240105ENG-905    ENG  CEL    800 TIS     30 Flow Cyt.   Type/tif
        906  TIS-240106ENG-906    ENG  D.IMG  801 TIS     31 Histopath.  Type/tif
        907  TIS-240107ENG-907    ENG  D.IMG  800 TIS     30 Flow Cyt.   DataType/tif
        908  TIS-240108ENG-908    ENG  D.IMG  800 TIS     30 Flow Cyt.   Type/png
        911  TIS-240111ENG-911    ENG  D.IMG  803 AB,     30 Flow Cyt.   Type/tif
                                             804 TIS
        909  TIS-240109ENG-909    MODE_2, and must never reach the sheet

    900 and 901 SHARE a cohort -- they differ only in which parent they hang
    off, which is not a key component -- so the world exercises a multi-row
    cohort as well as eight single-row ones. Nine rows, eight cohorts.

    THE CORROBORATION CASES ARE CHOSEN TO BREAK A TITLE-KEYED CHECK.
        900  proposes 30, parent 800 holds internal 30        -> corroborated
        901  proposes 30, parent 801 holds internal 31        -> not
        902  proposes 30, parent 802 holds internal 32 WHOSE TITLE IS ALSO
             "Flow Cytometry"                                 -> not
    902 is the discriminator. Two assays sharing a display string is the exact
    hazard `merge_vocabulary` and `audit_contradictions` both refuse a title
    key for, and a flag comparing titles rather than ids would light 902 green
    and tell a curator a neighbour corroborates a proposal it does not.
    """
    findings = _findings([
        _row(900, "TIS-240101ENG-900"),
        _row(901, "TIS-240102ENG-901"),
        _row(902, "TIS-240103GRI-902"),
        _row(903, "TIS-240104ENG-903"),
        _row(905, "TIS-240105ENG-905", sample_type="CEL"),
        _row(906, "TIS-240106ENG-906", assay_id=31, assay_title="Histopathology"),
        _row(907, "TIS-240107ENG-907", field="DataType", tier=S.T_WEAK),
        _row(908, "TIS-240108ENG-908", value="png"),
        _row(911, "TIS-240111ENG-911"),
        _row(909, "TIS-240109ENG-909", mode=S.MODE_2),
    ])
    parents_of = {900: frozenset({800}), 901: frozenset({801}),
                  902: frozenset({802}), 905: frozenset({800}),
                  906: frozenset({801}), 907: frozenset({800}),
                  908: frozenset({800}), 909: frozenset({800}),
                  911: frozenset({803, 804})}
    uuid_of = {800: "TIS-240101ENG-800", 801: "TIS-240101ENG-801",
               802: "TIS-240101ENG-802", 803: "AB-240101ENG-803",
               804: "TIS-240101ENG-804"}
    types = {"TIS-240101ENG-800": "TIS", "TIS-240101ENG-801": "TIS",
             "TIS-240101ENG-802": "TIS", "AB-240101ENG-803": "AB",
             "TIS-240101ENG-804": "TIS"}
    context = {
        "parents_of": parents_of,
        "uuid_of": uuid_of,
        "types": types,
        "registrations": {
            800: [(1030, 30, "Flow Cytometry")],
            801: [(1031, 31, "Histopathology")],
            802: [(1032, 32, "Flow Cytometry")],
        },
        "metadata": {
            900: {"Type": "tif", "DataType": "png", "Notes": "",
                  "Tissue": "liver"},
            800: {"Type": "tif", "Tissue": "liver"},
        },
    }
    return findings, context


def _html(findings=None, context=None) -> str:
    f, c = _world()
    return R.render(R.build_blocks(findings if findings is not None else f,
                                   context if context is not None else c))


# --- an HTML reader ----------------------------------------------------------


class _Doc(HTMLParser):
    """Tags, their class tokens and their ancestry. No third-party parser.

    `beautifulsoup4` is not a dependency of this repo and adding one so a test
    can read its own output would put the assertion behind an install that CI
    may not have. `html.parser` is stdlib and reads enough: every start tag,
    the class tokens on it, and the stack it sits in.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str]]] = []
        self.elements: list[tuple[str, frozenset[str], tuple]] = []
        self.by_token: dict[str, set[str]] = {}
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str, str]] = []   # (tag, name, value)
        self.text: list[str] = []       # rendered text, outside style/script
        self.raw: list[str] = []        # the style and script bodies
        self._raw_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._raw_tag = tag
        d = dict(attrs)
        tokens = frozenset((d.get("class") or "").split())
        self.elements.append((tag, tokens, tuple(self.stack)))
        self.tags.append(tag)
        for name, value in attrs:
            self.attrs.append((tag, name, value or ""))
        for t in tokens:
            self.by_token.setdefault(t, set()).add(tag)
        if tag not in ("br", "hr", "img", "input", "meta", "link"):
            self.stack.append((tag, tokens))

    def handle_data(self, data):
        """Style and script bodies are kept APART from the rendered text.

        `html.parser` reports both through `handle_data`, so pooling them would
        let a URL inside a stylesheet satisfy a check meant to say "the only
        URLs here are inert page text". They are the two places a URL is NOT
        inert, so they get their own bucket.
        """
        (self.raw if self._raw_tag else self.text).append(data)

    def handle_endtag(self, tag):
        if tag == self._raw_tag:
            self._raw_tag = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def with_token(self, token):
        return [e for e in self.elements if token in e[1]]


def _doc(html_text: str) -> _Doc:
    p = _Doc()
    p.feed(html_text)
    return p


def _script(html_text: str) -> str:
    """The page's script bodies, joined. Fails rather than returning ""."""
    bodies = re.findall(r"<script[^>]*>(.*?)</script>", html_text, re.S)
    assert bodies, "the sheet carries no script; every handler below is absent"
    return "\n".join(bodies)


def _try_spans(js: str) -> list[tuple[int, int]]:
    """Index spans of every `try { ... }` BODY, string literals skipped.

    Brace-matched rather than regex-matched: a regex for a try block cannot
    know where the block ends, and "the call is somewhere after the word try"
    is satisfied by a call after the block closes -- which is precisely the
    unguarded case. String literals are skipped so a brace inside a message
    cannot unbalance the scan.
    """
    spans, i, n = [], 0, len(js)
    while True:
        m = re.compile(r"\btry\s*\{").search(js, i)
        if not m:
            return spans
        start = m.end() - 1
        depth, j, quote = 0, start, None
        while j < n:
            ch = js[j]
            if quote:
                if ch == "\\":
                    j += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        assert depth == 0, "unbalanced braces after a `try` in the sheet script"
        spans.append((start, j))
        i = j + 1


# --- the UID parse, which is not a modelled field ----------------------------


def test_the_uid_parse_recovers_the_lab_and_the_date_from_the_house_shape():
    """`<TYPE>-<YYMMDD><LAB>-<serial>`, split at the digit/letter boundary.

    THE LAB IS NOT A COLUMN ANYWHERE. Neither `samples` nor `nodes` nor
    `findings` carries it; it exists only inside the uuid, by convention, and
    the sheet groups on it because a curator rules lab by lab. Everything a
    convention-derived field touches has to be guarded, which is what the two
    tests below are for.
    """
    got = R.parse_uid("D.IMG-240910LAU-68")
    assert got["lab"] == "LAU" and got["date"] == "240910"
    assert got["type"] == "D.IMG" and got["serial"] == "68"


@pytest.mark.parametrize("bad", [
    "TIS-100",                       # the shape a synthetic fixture uses
    "2720-Group 01-G181_TMZ_IC_PD",  # a real extract uuid, measured below
    "MUS-240910LAU-68\xa0",          # a real one, with a trailing NBSP
    "D.IMG-24091LAU-68",             # five date digits
    "D.IMG-240910-68",               # no lab
    "",
])
def test_a_uid_that_does_not_match_the_house_shape_fails_loudly(bad):
    """It RAISES. It does not return None, blank or NaN.

    `str.extract` -- the spelling the prototype used -- yields NaN on a
    non-match, and `groupby(dropna=False)` then puts every unparseable uuid in
    ONE cohort keyed `lab = nan`. Rows from different labs would be presented
    to a curator as one population and ruled on together. Silence here is worse
    than a crash, so it is a crash.

    Measured on the 2026-08-14 extract: 0 of the 2,166 MODE_1 uuids fail this
    parse, and 2 of the 163,379 sample uuids do -- `2720-Group 01-...`, which
    is not a UID at all, and `MUS-240910LAU-68` carrying a trailing NON-BREAKING
    SPACE. The second is the one that argues for the raise: it is one invisible
    character from valid, and `.strip()`ing it would be this module quietly
    repairing someone else's data defect.
    """
    with pytest.raises(ValueError) as e:
        R.parse_uid(bad)
    assert repr(bad)[1:-1].split("\\x")[0][:8] in str(e.value) or bad == "", \
        "the raise must name the uuid it refused"


def test_a_findings_frame_with_one_unparseable_uuid_refuses_the_whole_sheet():
    """One bad uuid stops the sheet and names itself. It is not skipped.

    Skipping it would drop a curator's row from a review surface silently,
    which is the same failure as mis-grouping it with a different lab and is
    harder to notice.
    """
    findings, context = _world()
    findings.loc[0, "uuid"] = "TIS-900"
    with pytest.raises(ValueError) as e:
        R.build_blocks(findings, context)
    assert "TIS-900" in str(e.value)


# --- the cohorts -------------------------------------------------------------


def test_every_mode_1_finding_lands_in_exactly_one_cohort_and_the_counts_sum():
    """Requirement 5, both halves, and the SUM is the half that catches drift.

    A cohort table whose rows overlap presents the same proposal twice and
    invites two rulings on it; one whose rows do not cover presents fewer
    proposals than the run found and hides the rest. Asserted against the frame
    rather than a literal, so it stays true when the world changes.
    """
    findings, context = _world()
    blocks = R.build_blocks(findings, context)
    m1 = findings[findings["mode"] == S.MODE_1]

    assert sum(b["n_rows"] for b in blocks) == len(m1) == 9
    assert len({R.cohort_key(b) for b in blocks}) == len(blocks) == 8
    # ...and the MODE_2 row leaked into none of them
    assert "909" not in str(blocks)


def test_dropping_any_component_of_the_key_collapses_a_cohort():
    """The key is SIX fields and each one separates a pair in this world.

    A test that only counts cohorts cannot tell a six-field key from a
    five-field one unless the fixture makes every field load-bearing. This
    re-derives the count with one component removed at a time and requires the
    count to FALL each time -- so a key that quietly loses `source_field` or
    `parent_types` is red here rather than in production, where it would merge
    two populations a curator rules on differently.
    """
    findings, context = _world()
    full = R.build_blocks(findings, context)
    keys = {tuple(b[c] for c in R.BLOCK_KEY) for b in full}
    assert len(keys) == len(full)
    for i, component in enumerate(R.BLOCK_KEY):
        collapsed = {k[:i] + k[i + 1:] for k in keys}
        assert len(collapsed) < len(keys), (
            f"dropping {component!r} from the cohort key changes nothing in "
            "this world, so no test here can tell whether it is in the key")


def test_a_cohort_shows_at_most_five_examples_and_says_what_it_is_holding_back():
    """NO SILENT TRUNCATION, which is the same rule the report's `_more` keeps.

    A cohort of 400 rows showing 5 without saying so reads as a cohort of 5.
    """
    findings, context = _world()
    # eight more rows with no parent, joining 903's cohort: 1 + 8 = 9
    extra = _findings([_row(920 + i, f"TIS-240101ENG-{920 + i}")
                       for i in range(8)])
    blocks = R.build_blocks(pd.concat([findings, extra], ignore_index=True),
                            context)
    big = max(blocks, key=lambda b: b["n_rows"])
    assert big["parent_types"] == R.NO_PARENT
    assert big["n_rows"] == 9 and big["shown"] == R.MAX_EXAMPLES == 5
    html_text = R.render(blocks)
    assert "showing 5 of 9" in html_text


def test_a_mode_1_child_that_carries_its_own_registration_is_refused():
    """MODE 1 IS "registered in nothing". A child holding a registration is
    not a Mode 1 row, and rendering one would put a proposal in front of a
    curator for a sample that already has the answer.

    Measured on the 2026-08-14 extract, 0 of the 1,657 Mode 1 samples carry any
    membership row, so this guard costs nothing today and is the one that goes
    red if the precedence between the modes is ever reordered.
    """
    findings, context = _world()
    context["registrations"][900] = [(1030, 30, "Flow Cytometry")]
    with pytest.raises(ValueError) as e:
        R.build_blocks(findings, context)
    assert "900" in str(e.value) and "MODE_1" in str(e.value)


def test_a_parent_already_holding_the_proposed_assay_is_flagged():
    """The strongest corroboration a Mode 1 row can have, and it EXISTS.

    Mode 1 outranks the lineage step in this package's precedence, so a sample
    registered in nothing is claimed by Mode 1 even where a DERIVED_FROM
    neighbour already carries the proposed pair. Where that happens the
    neighbour is independent evidence for the proposal, and it is the only
    evidence a Mode 1 row can have beyond its own metadata.

    900's parent holds internal 30, which IS the proposal. 901's parent holds
    31, which is not -- and the pair is deliberately near-identical in title so
    a flag keyed on the TITLE rather than the id would light up on both.
    """
    findings, context = _world()
    blocks = {R.cohort_key(b): b for b in R.build_blocks(findings, context)}
    by_uuid = {c["uuid"]: c for b in blocks.values() for c in b["children"]}

    assert by_uuid["TIS-240101ENG-900"]["parent_has_proposed"] is True
    assert by_uuid["TIS-240102ENG-901"]["parent_has_proposed"] is False
    assert by_uuid["TIS-240104ENG-903"]["parent_has_proposed"] is False
    assert by_uuid["TIS-240103GRI-902"]["parent_has_proposed"] is False, (
        "902's parent holds internal 32, whose TITLE is also 'Flow Cytometry'. "
        "A flag keyed on the title rather than the assay id reads that as "
        "corroboration and tells a curator a neighbour agrees when it does not")
    assert "ALREADY in this assay" in R.render(list(blocks.values()))


def test_a_child_with_no_parent_is_keyed_no_parent_and_says_so():
    """A missing parent is a POPULATION, not a blank.

    The operator ruled on three `NO_PARENT` cohorts in the fixture rulings, so
    this is a group they read as a group -- an empty string in the key would
    sort it beside whatever else was empty.
    """
    findings, context = _world()
    blocks = R.build_blocks(findings, context)
    orphan = [b for b in blocks if b["parent_types"] == R.NO_PARENT]
    assert len(orphan) == 1 and orphan[0]["children"][0]["uuid"].endswith("903")
    assert "no DERIVED_FROM parent" in R.render(blocks)


def test_a_cohort_header_carries_the_stats_a_curator_sorts_on():
    """rows, samples, contested, tiers, date range and the review band."""
    findings, context = _world()
    findings.loc[findings.sample_id == 902, "contested"] = True
    blocks = {b["lab"]: b for b in R.build_blocks(findings, context)}
    gri = blocks["GRI"]
    assert gri["n_rows"] == 1 and gri["n_samples"] == 1
    assert gri["n_contested"] == 1
    assert gri["tiers"] == S.T_STRONG
    assert gri["dates"] == "240103"
    assert gri["band"] == R.BAND_CONTESTED

    html_text = R.render(list(blocks.values()))
    assert "1 contested" in html_text and R.BAND_CONTESTED in html_text


def test_a_cohort_spanning_two_dates_reports_a_range_not_one_of_them():
    findings, context = _world()
    findings.loc[findings.sample_id == 901, "uuid"] = "TIS-240930ENG-901"
    findings.loc[findings.sample_id == 901, "sample_id"] = 900
    blocks = R.build_blocks(findings, context)
    span = [b for b in blocks if b["n_rows"] == 2]
    assert span and span[0]["dates"] == "240101-240930"


# --- the metadata panel ------------------------------------------------------


def test_the_source_field_of_the_proposal_is_marked_apart_from_other_claims():
    """Requirement: claim-bearing fields marked, the SOURCE field DISTINCTLY.

    900's metadata carries both `Type` (the source of this proposal) and
    `DataType` (claim-bearing, but not what raised this row). On a contested
    row the entire question is which of several fields to believe, so a panel
    that marks them identically answers nothing.
    """
    doc = _doc(_html())
    claims = doc.with_token("claim")
    assert claims, "no claim-bearing metadata field is marked at all"
    sources = doc.with_token("src")
    assert sources, "the field that produced the proposal is not marked"
    for _tag, tokens, _stack in sources:
        assert "claim" in tokens, "the source marker must refine the claim one"
    assert len(sources) < len(claims), (
        "every marked claim field is also marked as the source, so the two "
        "markings do not distinguish anything")


def test_blank_metadata_is_dropped_and_counted_rather_than_rendered():
    """The D.IMG sheet carries 60+ columns and a typical row fills six.

    Rendering the blanks buries the six that matter; dropping them without
    saying how many were dropped hides that the record is mostly empty, which
    is itself evidence about the claim.
    """
    findings, context = _world()
    html_text = R.render(R.build_blocks(findings, context))
    assert ">Notes<" not in html_text, (
        "900's blank `Notes` field was rendered; the blanks bury the six "
        "fields that carry the claim")
    assert "1 blank" in html_text, (
        "the blanks were dropped without saying how many, so a mostly-empty "
        "record reads exactly like a full one")


def test_a_parent_registration_renders_the_seek_id_and_the_internal_id():
    """`seek -> internal`, because they are different id spaces.

    One internal id spans up to 23 SEEK records. A sheet that showed only the
    internal id would let a reader believe a single row names a single writable
    record, which is the claim `run_detect`'s report exists to deny.
    """
    html_text = _html()
    assert "seek 1030" in html_text and "internal 30" in html_text


# --- the interactive layer, which is where the defects shipped ---------------


def test_no_class_token_is_shared_by_a_structural_and_an_interactive_element():
    """THE SHIPPED DEFECT, in its general form. See this module's docstring.

    `<p class="note">` beside `<textarea class="note">` made
    `querySelectorAll(".dec, .note")` return paragraphs, `closest(".notes")`
    return null on the first of them, and the resulting throw aborted the loop
    that attaches EVERY storage listener and BOTH button handlers -- while the
    form still accepted typing. Nothing in the rendered text changed.

    So this is asserted over the parsed document rather than over its text: for
    every class token, the set of tags wearing it must be entirely form
    controls or entirely not.
    """
    doc = _doc(_html())
    for token, tags in sorted(doc.by_token.items()):
        control = tags & CONTROLS
        structural = tags - CONTROLS
        assert not (control and structural), (
            f"class token {token!r} is worn by form control(s) "
            f"{sorted(control)} AND by {sorted(structural)}. A selector for "
            "one will collect the other, and one throw inside that loop "
            "silently kills every handler on the page.")


def test_the_two_selectors_the_script_uses_resolve_to_exactly_their_controls():
    """`.dec` is only ever a `<select>` and `.note` only ever a `<textarea>`.

    The general check above would also pass if `.note` were worn by two DIFFERENT
    controls. The script reads `.value` off both and writes one storage key per
    element, so two kinds of control under one token would collide their keys.
    """
    doc = _doc(_html())
    assert {t for t, _c, _s in doc.with_token("dec")} == {"select"}
    assert {t for t, _c, _s in doc.with_token("note")} == {"textarea"}
    assert doc.by_token["notes"] & CONTROLS == set()


def test_every_ruling_control_sits_inside_a_notes_container():
    """Requirement 2. `closest('.notes')` must never return null.

    That call is made inside the loop that attaches every listener on the page,
    and a null return there is not a missing highlight: it is an exception that
    ends the loop and leaves the rest of the document inert.
    """
    doc = _doc(_html())
    controls = doc.with_token("dec") + doc.with_token("note")
    assert len(controls) >= 2, "the sheet renders no ruling controls at all"
    for tag, _tokens, stack in controls:
        assert any("notes" in tokens for _t, tokens in stack), (
            f"a <{tag}> ruling control has no .notes ancestor")


def test_every_storage_call_is_guarded_and_the_page_says_when_it_is_not():
    """Requirement 3, both halves.

    A sandboxed viewer -- an iframe with a restrictive sandbox, or a browser
    with site data blocked -- makes `window.localStorage` THROW `SecurityError`
    on access rather than return null. An unguarded access at load time aborts
    the script, and this page's script is one `forEach` that attaches every
    listener and both button handlers: an abort inside it leaves a form that
    accepts typing and saves nothing, with dead buttons.

    Guarding is not enough on its own. If storage silently does not work, a
    curator loses an afternoon of rulings on reload, so the page has to SAY it
    and the count line is where they will be looking.
    """
    js = _script(_html())
    spans = _try_spans(js)
    assert spans, "the script contains no try block; nothing is guarded"
    for m in re.finditer(r"localStorage|\.getItem|\.setItem|\.removeItem", js):
        assert any(a < m.start() < b for a, b in spans), (
            f"storage access {m.group(0)!r} at offset {m.start()} is outside "
            "every try block; one SecurityError there kills every handler")
    assert "NOT saved in this browser" in js, (
        "the page never tells a curator their rulings are not being kept")


def test_the_export_contract_is_the_eight_columns_and_the_script_emits_them():
    """Requirement 6's second half, pinned on BOTH sides.

    The header the script writes and the tuple this module publishes have to be
    the same eight names in the same order, or a ruling file exported from the
    page cannot be read back by anything that trusts `EXPORT_COLUMNS`.
    """
    assert R.EXPORT_COLUMNS == ("lab", "sample_type", "parent_types", "assay",
                                "field", "value", "ruling", "note")
    js = _script(_html())
    header = re.search(r'var rows = \[\[(.*?)\]\.join', js, re.S)
    assert header, "the export builder does not start from a header row"
    names = re.findall(r'"([a-z_]+)"', header.group(1))
    assert tuple(names) == R.EXPORT_COLUMNS


def test_a_ruling_key_round_trips_to_exactly_one_emitted_cohort():
    """The key a curator exports resolves back to the cohort it was ruled on.

    Six fields joined by `|`, which only works while no field CONTAINS one --
    so the builder refuses a key component carrying the delimiter rather than
    emitting a key that splits into seven.
    """
    findings, context = _world()
    blocks = R.build_blocks(findings, context)
    by_key = {R.cohort_key(b): b for b in blocks}
    for key, block in by_key.items():
        parts = key.split("|")
        assert len(parts) == len(R.BLOCK_KEY) == 6
        assert tuple(parts) == tuple(str(block[c]) for c in R.BLOCK_KEY)


def test_a_key_component_carrying_the_delimiter_is_refused():
    """A `|` in a term would split the exported key into seven fields."""
    findings, context = _world()
    findings.loc[0, "raw_value"] = "a|b"
    with pytest.raises(ValueError) as e:
        R.build_blocks(findings, context)
    assert "a|b" in str(e.value)


@pytest.mark.parametrize("column", ["raw_value", "source_field",
                                    "proposed_internal_assay_title"])
def test_a_null_claim_field_is_refused_rather_than_keyed_as_nan(column):
    """The unparseable-UID defect one column over, and it is easy to miss.

    `astype(str)` renders a null as the STRING "nan", so a cohort key built
    over nulls does not fail -- it succeeds, and produces a cohort labelled
    `nan` pooling rows from unrelated claims for one ruling. That is the same
    outcome a null lab would have and it has to be refused the same way.

    Parametrized over all three claim-derived components, so a guard that
    covers the term and forgets the field is red rather than half-green.

    WHAT THIS TEST DOES NOT PROVE, stated because a mutation measured it: the
    guard reads the SOURCE column rather than the `astype(str)` derived one,
    and swapping the two survives this suite. Under pandas 3.0.5 with
    `future.infer_string` on, `astype(str)` preserves the null for every dtype,
    so both spellings behave identically here; under the pandas 2 the package
    also declares, the derived spelling is silently vacuous. No test in this
    file can tell those apart on this interpreter, and pretending otherwise
    would be the vacuous assertion this file exists to prevent.
    """
    findings, context = _world()
    findings.loc[0, column] = None
    with pytest.raises(ValueError) as e:
        R.build_blocks(findings, context)
    assert column in str(e.value) and "nan" in str(e.value)


# --- the frame is the run ----------------------------------------------------


def test_the_sheet_is_built_from_the_frame_and_never_from_a_file_this_run_wrote(
        tmp_path):
    """Requirement 4. ONE definition of the run, and it is in memory.

    The prototype's earlier form was separate scripts reading each other's csv,
    and it went inconsistent twice -- once emitting assay 31 "Flow Cytometry
    Analysis" into the review context where `findings.csv` said assay 30 "Flow
    Cytometry". This plants exactly that disagreement: a decoy `findings.csv`
    and a decoy `cohorts-to-review.csv` in the output directory naming assay
    31, against an in-memory frame naming 30. The frame must win, and the decoy
    string must not appear anywhere in the sheet.
    """
    findings, context = _world()
    decoy = findings.copy()
    decoy["proposed_internal_assay_id"] = 31
    decoy["proposed_internal_assay_title"] = "Flow Cytometry Analysis"
    decoy.to_csv(tmp_path / "findings.csv", index=False)
    decoy.to_csv(tmp_path / RD.COHORTS_NAME, index=False)

    path = R.write_review(findings, context, tmp_path)
    text = path.read_text()

    assert "Flow Cytometry Analysis" not in text, (
        "the sheet quotes a file the run wrote rather than the frame the run "
        "is; that is the assay 30/31 divergence, reproduced")
    assert "Flow Cytometry" in text
    assert path.name == R.REVIEW_NAME


def test_this_module_reads_no_csv_at_all():
    """The structural half of the same requirement.

    `run_detect` reads `findings.csv` back on purpose, once, and hands the
    frame on. If this module could read a csv it could read that one a second
    time, and two reads of one file at two moments is how the two artifacts
    disagreed. It takes a frame; it has no reason to know the filename.
    """
    src = (REPO / "scripts" / "assay_hygiene" / "review.py").read_text()
    assert "read_csv" not in src
    assert "findings.csv" not in src


def test_the_sheet_has_no_approval_surface_and_imports_no_write_path():
    """The increment's hard boundary: it detects and proposes, and stops.

    A ruling captured as text a human exports is fine. Anything that INGESTS a
    ruling is out of scope, and the two modules that can write to the graph are
    named here so an import of either is red rather than merely reviewed.
    """
    src = (REPO / "scripts" / "assay_hygiene" / "review.py").read_text()
    assert "stage0_apply" not in src and "driver_stage0" not in src
    for banned in ("MERGE", "DELETE", "APPROVE ="):
        assert banned not in src, f"the review module mentions {banned!r}"
    text = _html()
    # APPROVE exists as a RULING a curator may record, never as a column.
    assert "APPROVE" in text
    assert "<th" not in text, "the sheet renders no table, so it has no columns"


# --- the page itself ---------------------------------------------------------


def _assert_self_contained(text: str) -> None:
    """Nothing in `text` can cause an external request.

    THIS IS NOT `"https://" not in text`, AND THE FIRST VERSION OF IT WAS.
    That version passed on the fixture world and would have FAILED on the
    shipped artifact: the real extract carries a `Link_OrganWeight` metadata
    field holding a Zenodo URL, which appears 275 times in the 45-cohort sheet
    as ESCAPED TEXT INSIDE A SPAN. It is data a curator has to see, it is
    inert, and a test banning those characters would have forced this module to
    censor the metadata it exists to display. It is also the exact shape of a
    vacuous assertion: green only because no fixture value happened to contain
    a URL.

    So this asserts the property that matters -- the page issues no request --
    and then pins WHERE a scheme is allowed to appear rather than whether it
    appears at all. Two places are inert and both occur in the real sheet: a
    text node (275 times, the Zenodo link) and an escaped non-fetching
    attribute (4 times, in `data-k`, because two cohorts have a `Protocol` term
    that IS a URL and the cohort key carries the term). Everywhere else is
    refused: any fetching tag, any fetching attribute, and anything at all
    inside the stylesheet or the script, which are the two bodies where a URL
    is not inert.
    """
    doc = _doc(text)

    fetching_tags = {"link", "img", "iframe", "object", "embed", "video",
                     "audio", "source", "track", "portal", "frame", "applet"}
    present = {t for t in doc.tags if t in fetching_tags}
    assert not present, f"the sheet renders tag(s) that fetch: {sorted(present)}"

    fetching_attrs = {"src", "href", "action", "poster", "srcset", "data",
                      "background", "formaction", "cite", "manifest", "ping"}
    bad = [(tag, name, value[:60]) for tag, name, value in doc.attrs
           if name in fetching_attrs]
    assert not bad, f"the sheet carries fetching attribute(s): {bad[:3]}"

    for construct in ("@import", "fetch(", "XMLHttpRequest", "WebSocket",
                      "importScripts", "sendBeacon", "url(http", "url('http",
                      'url("http', "//cdn"):
        assert construct not in text, f"the sheet reaches out: {construct!r}"

    # THE STYLESHEET AND THE SCRIPT CARRY NO SCHEME AT ALL. They are the two
    # bodies where a URL is a request rather than a string.
    inert_attr = "\n".join(
        value for tag, name, value in doc.attrs if name not in fetching_attrs)
    rendered = "".join(doc.text)
    for scheme in ("http://", "https://", "//fonts.", "data:font", "://"):
        assert scheme not in "".join(doc.raw), (
            f"{scheme!r} appears inside the stylesheet or the script, where a "
            "URL is a request and not a string")
        # ...and every other occurrence is accounted for as rendered text or
        # as an escaped value on an attribute that cannot fetch. A scheme loose
        # in the markup is neither, and fails here.
        accounted = rendered.count(scheme) + inert_attr.count(scheme)
        assert text.count(scheme) <= accounted, (
            f"{text.count(scheme) - accounted} occurrence(s) of {scheme!r} are "
            "neither rendered text nor an escaped non-fetching attribute")


def test_a_metadata_value_carrying_markup_is_escaped_and_creates_no_element():
    """Every string on this page came out of a database a curator can edit.

    The same requirement as self-containment, approached from the side an
    attacker would: a `json_metadata` value is free text, and a value reading
    `<script src=...>` that reached the document as markup would BOTH execute
    and fetch, defeating the checks above without tripping any of them -- they
    inspect the rendered tree, and injected markup becomes part of that tree.

    The term and the metadata are planted because they take two different
    routes onto the page: an escaped `data-k` attribute and a metadata cell.

    ASSERTED AS "THE TAG MULTISET DOES NOT MOVE", against a benign render of
    the same shape. Checking for the absence of a particular tag does not work
    -- the sheet uses `<b>` for every field name, so `"b" not in tags` is false
    on a perfectly safe page, and the first version of this test asserted
    exactly that and failed. What injection means is that a VALUE became an
    ELEMENT, and the way to say that is to count the elements twice.
    """
    findings, context = _world()
    benign = {"Type": "plain value", "Notes": "another plain value"}
    context["metadata"][900] = benign
    findings.loc[0, "raw_value"] = "harmless"
    clean = _doc(R.render(R.build_blocks(findings, context)))

    findings.loc[0, "raw_value"] = '"><script src=x>bad</script>'
    context["metadata"][900] = {"Type": '<img src=x onerror=bad()>',
                                "Notes": "</textarea><b>injected</b>"}
    text = R.render(R.build_blocks(findings, context))
    doc = _doc(text)

    _assert_self_contained(text)
    assert sorted(doc.tags) == sorted(clean.tags), (
        "a metadata value or a term became an element: the injected render "
        "has a different tag multiset from the benign one")
    assert "&lt;img src=x" in text and "<img src=x" not in text
    assert "&lt;script" in text and "<script src" not in text


def test_the_sheet_is_self_contained_and_fetches_nothing():
    """Requirement 7. It is opened off a laptop, frequently offline.

    A CDN font or script would make the review surface depend on a network the
    reviewer may not have, and would tell a third party which cohorts a curator
    opened and when.
    """
    _assert_self_contained(_html())


def test_the_sheet_carries_both_themes_and_cannot_scroll_the_page_sideways():
    """Requirement 8. The viewer's theme is not knowable at render time.

    Three states, not two: an explicit choice sets `data-theme`, and the
    default sets nothing at all and leaves only `prefers-color-scheme`. So the
    light palette is defined on bare `:root`, the dark one under the media
    query, and again under `[data-theme=dark]` so an explicit choice wins in
    both directions.

    The horizontal-scroll half is asserted structurally: the free-text this
    page renders -- uuids, protocol filenames, metadata values -- has no spaces
    to break at, so any container holding it needs `overflow-wrap` or it sets
    the page width. There is no headless browser in this suite, so this checks
    the properties that prevent it rather than the absence of the scrollbar.
    """
    text = _html()
    css = re.search(r"<style>(.*?)</style>", text, re.S)
    assert css, "the sheet carries no stylesheet"
    css = css.group(1)
    assert "prefers-color-scheme:dark" in css.replace(" ", "")
    assert "[data-theme=dark]" in css.replace('"', "").replace("'", "")
    assert "[data-theme=light]" in css.replace('"', "").replace("'", "")
    assert re.search(r"body\s*\{[^}]*background:var\(--bg\)",
                     css.replace(" ", "")), "body has no token background"
    assert "box-sizing:border-box" in css.replace(" ", "")
    assert css.replace(" ", "").count("overflow-wrap:anywhere") >= 3
    assert not re.search(r":\s*\d{3,}px", css), (
        "a fixed pixel width wider than a phone will scroll the page sideways")


def test_the_sheet_says_the_proposed_assay_is_not_a_writable_target():
    """Consistent with the report, which makes the same statement.

    `proposed_internal_assay_id` is a harmonisation key this package derives;
    membership keys on a SEEK `assays.id`, and one internal id spans up to 23
    SEEK records. A review sheet that lists rows next to an APPROVE control
    invites them to be read as directly actionable, and for Mode 1 there is not
    even a neighbour rule to resolve one.
    """
    text = _html().lower()
    assert "internal" in text and "not a writable target" in text
    assert "seek" in text


def test_the_sheet_states_what_makes_a_row_mode_1():
    """A reader has to know the child holds NO registration, or the panel
    showing `registered in nothing` reads as missing data rather than as the
    definition of the population."""
    text = _html()
    assert "registered in nothing" in text
    assert "no registration" in text.lower()


# --- the wiring --------------------------------------------------------------


def test_run_detect_declares_the_review_sheet_as_one_of_its_artifacts():
    """Named once, in `ARTIFACTS`.

    `test_main_writes_exactly_the_declared_artifacts_and_no_input_byte_changes`
    diffs the output directory against this tuple and
    `test_the_report_names_every_artifact_this_run_writes` requires the prose to
    mention each, so this one assertion recruits both.
    """
    assert R.REVIEW_NAME in RD.ARTIFACTS


# --- the real extract --------------------------------------------------------


def test_the_real_extract_round_trips_the_operators_seventeen_rulings():
    """Requirement 6, against a REAL ruling file a real curator exported.

    A key that resolves to no cohort means the sheet regenerated with a
    different grouping and every ruling in that file is orphaned -- the silent
    outcome this whole increment is built to avoid.

    A RETIREMENT IS THE ONE LEGITIMATE WAY TO LOSE A KEY, and telling the two
    apart is what this revision adds. On 2026-08-20 the operator retired
    `DataType: tif` and `DataType: png`, and 7 of his 9 WRONG_ASSAY cohorts --
    every tif and png one -- stopped being emitted because the mapping that
    raised them is gone. That is the vocabulary fix WORKING: the ruling was
    "this proposal is wrong", and the proposal no longer exists. Failing on it
    would mean the suite goes red every time a curator's own ruling is acted on.

    So the two outcomes are separated rather than merged:

      * EVERY `APPROVE` key must still resolve, with no exception. Those are the
        write candidates; losing one silently is the failure that matters most,
        and a retirement must never take one. Measured after the retirement: all
        8 still resolve.
      * A `WRONG_ASSAY` key may resolve to nothing ONLY IF its term is now
        retired in the vocabulary -- asserted against `vocabulary.csv`, not
        assumed. Measured: 7 gone (5 tif, 2 png), 2 still emitted (the SeqWell
        protocol and the Macrophages cohort), because no vocabulary ruling
        reaches those two and they still need an answer.

    Anything else is still the orphaning this test was written to catch.
    """
    if not (EXTRACT / "samples.parquet").exists() or \
            not (ARTIFACTS / "findings.csv").exists():
        pytest.skip("no extract or findings; run run_detect.py first")
    if not RULINGS.exists():
        pytest.skip(
            f"no {RULINGS.name}. The rulings are CURATION OUTPUT and are kept "
            "out of this repository, which is public and whose fixtures would "
            "otherwise carry sample identifiers. They live beside the other "
            "assay-hygiene artifacts; drop the file in to run this test.")
    findings = pd.read_csv(ARTIFACTS / "findings.csv", low_memory=False)
    context = R.load_context(EXTRACT)
    blocks = R.build_blocks(findings, context)
    emitted = {R.cohort_key(b) for b in blocks}

    rulings = pd.read_csv(RULINGS, sep="\t")
    assert list(rulings.columns) == ["key", "ruling", "note"]
    assert len(rulings) == 17
    for key in rulings.key:
        assert len(key.split("|")) == len(R.BLOCK_KEY)

    vocab = V.load_vocabulary(ARTIFACTS / "vocabulary.csv")
    retired = {(str(r.source_field), str(r.raw_value))
               for r in vocab.itertuples(index=False)
               if pd.isna(r.internal_assay_id)}

    orphaned = []
    for key, ruling in zip(rulings.key, rulings.ruling):
        if key in emitted:
            continue
        field, value = key.split("|")[4], key.split("|")[5]
        term = (field, S.normalise_value(value))
        if ruling == "WRONG_ASSAY" and term in retired:
            continue          # discharged by a retirement -- the fix working
        orphaned.append(f"{key} [{ruling}]")
    assert not orphaned, (
        f"{len(orphaned)} of {len(rulings)} rulings resolve to no cohort and "
        f"were NOT discharged by a retirement: {orphaned[:3]}")

    # the strong half, stated separately so it cannot be weakened by the
    # exemption above: no APPROVE key may go missing for any reason at all.
    lost = [k for k, r in zip(rulings.key, rulings.ruling)
            if r == "APPROVE" and k not in emitted]
    assert not lost, f"a retirement took {len(lost)} APPROVE cohort(s): {lost}"


def test_the_real_extract_renders_a_sheet_that_is_still_inert(tmp_path):
    """The structural guards, over data that CONTAINS URLs and odd characters.

    THE FIXTURE WORLD CANNOT PROVE ANY OF THIS. Every value in it is a short
    tame string, so the class partition, the storage guard and above all the
    self-containment check are being asserted against markup no real metadata
    ever touched. The real extract is where a `Link_OrganWeight` field holds a
    Zenodo URL 275 times over -- the case that showed the first version of the
    self-containment test was green only by fixture. Whatever else the data
    does, it must not escape into markup.
    """
    if not (EXTRACT / "samples.parquet").exists() or \
            not (ARTIFACTS / "findings.csv").exists():
        pytest.skip("no extract or findings; run run_detect.py first")
    findings = pd.read_csv(ARTIFACTS / "findings.csv", low_memory=False)
    text = R.render(R.build_blocks(findings, R.load_context(EXTRACT)))

    _assert_self_contained(text)

    doc = _doc(text)
    for token, tags in sorted(doc.by_token.items()):
        assert not ((tags & CONTROLS) and (tags - CONTROLS)), (
            f"class token {token!r} is worn by a control and a non-control")
    controls = doc.with_token("dec") + doc.with_token("note")
    assert len(controls) >= 2
    for tag, _tokens, stack in controls:
        assert any("notes" in tokens for _t, tokens in stack), (
            f"a <{tag}> ruling control has no .notes ancestor")

    js = _script(text)
    spans = _try_spans(js)
    for m in re.finditer(r"localStorage|\.getItem|\.setItem|\.removeItem", js):
        assert any(a < m.start() < b for a, b in spans)


def test_the_real_extract_partitions_every_mode_1_row_into_a_cohort():
    """The sum, over the whole population rather than a seven-row world."""
    if not (EXTRACT / "samples.parquet").exists() or \
            not (ARTIFACTS / "findings.csv").exists():
        pytest.skip("no extract or findings; run run_detect.py first")
    findings = pd.read_csv(ARTIFACTS / "findings.csv", low_memory=False)
    blocks = R.build_blocks(findings, R.load_context(EXTRACT))
    m1 = findings[findings["mode"] == S.MODE_1]
    assert sum(b["n_rows"] for b in blocks) == len(m1)
    assert len({R.cohort_key(b) for b in blocks}) == len(blocks)
