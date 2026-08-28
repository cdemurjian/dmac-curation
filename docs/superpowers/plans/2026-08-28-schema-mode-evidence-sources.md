# Schema Mode Evidence Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/curate-sampletype` propose attributes from four evidence sources — repository requirements, type-specific CEDAR templates, BioPortal ontologies, and stated research knowledge — instead of one pinned generic CEDAR template.

**Architecture:** A new `scripts/schema/repositories.py` reads the GEO/SRA/PRIDE templates already vendored in `context/report_templates/` and yields required fields plus the vocabularies those repositories enforce. `scripts/schema/templates.py` gains per-type CEDAR template selection, demoting `common assay template` to an explicit fallback. `scripts/schema/ontology.py` gains two source ranks. `scripts/schema/review.py` gains one section and changes one. No module writes to NExtSEEK; every artifact stays a proposal.

**Tech Stack:** Python 3.11+, stdlib only (`urllib.request`, `json`, `dataclasses`). PEP 723 inline deps. pytest with injected-HTTP fakes. Run everything via `uv run`.

**Spec:** `docs/superpowers/specs/2026-08-28-schema-mode-evidence-sources-design.md`

## Global Constraints

- **Never write to NExtSEEK, never edit `context/sampletypes_db.json`.** Every output is a proposal a human applies by hand.
- **Every ontology binding is emitted `"confirmed": false`.** Only a human flips it.
- **Never rename or split an existing field name.** A name shared across sample types is not a defect.
- **Nothing mints a field.** Every source produces evidence; the curator judges.
- **Every review section is always rendered, and states WHY when empty.** Silence cannot distinguish "checked, found nothing" from "never checked".
- **Degrade, never raise.** No API key or a failed call yields an empty result and a note, never an exception.
- **No network in unit tests.** Inject an HTTP fake; model shapes verified against the live service.
- **Live smoke run required** against each external service before any task is called done — both defects found so far (`/parents` returns a bare array; CEDAR nests elements) passed unit tests first.
- **Full-suite baseline diff before committing.** Run with all deps: `uv run --with pytest --with openpyxl --with pandas --with requests --with pyarrow pytest tests/ -q`. Baseline is **1568 passed, 9 skipped, 4 xfailed, 0 failed** (measured 2026-08-28 on dev@7e2c432; re-measure, the tree is shared).
- **Never write `schema/` into the plugin repo root.** `tests/test_schema_dictionary.py::test_no_prebuilt_dictionary_ships_with_the_plugin` asserts it does not exist. Run demos in a scratch directory.

## File Structure

| file | responsibility |
|---|---|
| `scripts/schema/repositories.py` | **new.** Read vendored GEO/SRA/PRIDE templates; required fields, enforced vocabularies, which repositories apply to a type |
| `scripts/schema/templates.py` | **modify.** Add per-type CEDAR search, ranking, and fallback selection |
| `scripts/schema/ontology.py` | **modify.** Add `repository` and `cedar_branch` to `_SOURCE_RANK` |
| `scripts/schema/review.py` | **modify.** Add `## Repository requirements`; make the checklist declare a fallback |
| `scripts/schema/terms.py` | **unchanged.** `field_vocabulary` already built (Task 1 only documents it) |
| `tests/test_schema_repositories.py` | **new.** Repository reader tests |
| `tests/test_schema_templates.py` | **modify.** Selection and ranking tests |
| `tests/test_curate_sampletype.py` | **modify.** New/changed review sections |
| `commands/curate-sampletype.md` | **modify.** The loop gains sources 1 and 2 |
| `skills/curation/SCHEMA.md` | **modify.** Reference for all four sources |

---

### Task 1: Land the existing `field_vocabulary` work

`terms.field_vocabulary` and the obsolete-class filter are implemented and green
but **uncommitted and undocumented** — their doc updates were interrupted. Land
them before building on top, so the tree is clean.

**Files:**
- Modify: `commands/curate-sampletype.md` (step 5 of The loop)
- Modify: `skills/curation/SCHEMA.md` (new section before `## BioPortal - suggests, never binds`)
- Test: `tests/test_schema_terms.py` (already green, 42 tests — do not change)

**Interfaces:**
- Consumes: nothing.
- Produces: `terms.field_vocabulary(field, concept=None, *, ontologies=None, api_key=None, limit=40, http=None) -> VocabularyProposal` where `VocabularyProposal` has `.field: str`, `.concept: str`, `.values: list[str]`, `.confidence: str`, `.ontologies: tuple[str, ...]`, `.note: str`. Later tasks call this.

- [ ] **Step 1: Confirm the existing tests are green before touching anything**

Run: `uv run --with pytest pytest tests/test_schema_terms.py -q`
Expected: `42 passed`

- [ ] **Step 2: Replace step 5 of The loop in `commands/curate-sampletype.md`**

Find the block beginning `5. **Propose controlled values.**` and replace it entirely with:

```markdown
5. **Propose controlled values.** `scripts/schema/ontology.py` `propose_values()`
   merges Tags, observed values, siblings, CEDAR branches, repository
   vocabularies and BioPortal, ranking observed highest (hard rule 4).

   **`propose_values` does NOT call BioPortal.** It accepts `bioportal=[...]`
   and you must produce that list, or every value comes from Tags no matter
   what key is set. Use `terms.field_vocabulary(field, concept, ontologies=...)`,
   which returns the CHILDREN of the concept a field names. Two ways in:

   - **a current attribute** - compose the concept from the field AND the
     producing assay. A bare field name is not its concept: `Type` resolves
     EXACT to a generic class called "Type" and `Protocol` to
     kinds-of-protocol. Nothing distinguishes that from `Sequencer` ->
     `sequencer`, which is correct, so the values come back for you to read.
   - **a CEDAR-proposed attribute** - pass that field's declared branch as
     `ontologies`. The templates are authored against BAO, so `assay footprint`
     inside BAO yields array, microplate, vial, cuvette. Unbranched,
     `assay title` returns "Performed Patient Note Title".

   Read `_sources` in the artifact before trusting any of it.
```

- [ ] **Step 3: Add the reference section to `skills/curation/SCHEMA.md`**

Insert immediately before the line `## BioPortal - suggests, never binds`:

```markdown
## Field vocabulary - the middle of the chain

`propose_values` has always accepted `bioportal=[...]` and until this was added
nothing produced that list. Every `ontology.json` the plugin had written came
entirely from the Tags column, whatever key was set.

`terms.field_vocabulary(field, concept, ontologies=...)` fills it. The candidate
values for a field are the **children** of the concept that field names; a
parent is broader than the field and is never a permissible value for it.

**The concept is composed by the caller, not taken from the field name.** A bare
field name resolves confidently to the wrong thing: `Type` is an EXACT match for
a generic class called "Type". Nothing distinguishes that by shape from
`Sequencer` -> `sequencer`, which is right, so nothing tries.

For a CEDAR field, pass its declared branch. `assay footprint` inside BAO
resolves exactly and yields array, microplate, vial, cuvette.

**Obsolete classes are filtered in `search_terms` on two signals.** OBO marks
deprecation in the LABEL (`obsolete biological process`) while BioPortal reports
`obsolete: false` for that very class. Neither signal suffices alone.
```

- [ ] **Step 4: Run the full suite**

Run: `uv run --with pytest --with openpyxl --with pandas --with requests --with pyarrow pytest tests/ -q`
Expected: `1568 passed, 9 skipped, 4 xfailed` — unchanged from baseline (docs-only change plus already-green tests).

- [ ] **Step 5: Commit**

```bash
git add commands/curate-sampletype.md skills/curation/SCHEMA.md scripts/schema/terms.py tests/test_schema_terms.py
git commit -m "feat(schema): close the BioPortal value chain with field_vocabulary"
```

---

### Task 2: Repository template reader — required fields

**Files:**
- Create: `scripts/schema/repositories.py`
- Test: `tests/test_schema_repositories.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `REPOSITORY_FILES: dict[str, str]` mapping `"GEO"|"SRA"|"PRIDE"` to a filename under `context/report_templates/`
  - `@dataclass RepositoryField` with `.name: str`, `.section: str`, `.repository: str`, `.required: bool`, `.conditional: bool`
  - `load_template(repository: str, root: Path | None = None) -> dict`
  - `required_fields(doc: dict, repository: str) -> list[RepositoryField]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_repositories.py`:

```python
"""GEO / SRA / PRIDE requirements, read from the templates report mode vendors.

These files already ship in context/report_templates/ and schema mode has never
opened them. They are the only source that says which fields a submission is
REJECTED without, and they carry the vocabularies those repositories enforce.

A leading `*` marks required; `**` marks conditionally required (GEO uses it for
`**tissue`, `**cell line`, `**cell type`; PRIDE for `**file_mapping`).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from schema import repositories as sr  # noqa: E402

GEO_DOC = {
    "study": {"*title": None, "contributor": []},
    "samples": [{"*library strategy": None, "*organism": None,
                 "**tissue": None, "genotype": None}],
    "protocols": {"*extract protocol": None, "growth protocol": None},
}


def test_every_known_repository_has_a_file():
    assert set(sr.REPOSITORY_FILES) == {"GEO", "SRA", "PRIDE"}


def test_each_repository_file_actually_exists():
    for name in sr.REPOSITORY_FILES:
        assert sr.load_template(name)


def test_required_fields_collects_star_prefixed_keys():
    out = sr.required_fields(GEO_DOC, "GEO")
    assert {f.name for f in out} == {
        "title", "library strategy", "organism", "tissue", "extract protocol"}


def test_required_fields_strips_the_marker_from_the_name():
    out = sr.required_fields(GEO_DOC, "GEO")
    assert not any(f.name.startswith("*") for f in out)


def test_a_double_star_field_is_conditional_not_required():
    out = {f.name: f for f in sr.required_fields(GEO_DOC, "GEO")}
    assert out["tissue"].conditional is True
    assert out["tissue"].required is False
    assert out["organism"].required is True
    assert out["organism"].conditional is False


def test_required_fields_records_the_section_it_came_from():
    out = {f.name: f for f in sr.required_fields(GEO_DOC, "GEO")}
    assert out["title"].section == "study"
    assert out["library strategy"].section == "samples"
    assert out["extract protocol"].section == "protocols"


def test_unmarked_fields_are_not_returned():
    names = {f.name for f in sr.required_fields(GEO_DOC, "GEO")}
    assert "contributor" not in names and "genotype" not in names


def test_required_fields_tags_the_repository():
    assert all(f.repository == "GEO" for f in sr.required_fields(GEO_DOC, "GEO"))


def test_the_real_geo_template_declares_its_known_required_fields():
    out = {f.name for f in sr.required_fields(sr.load_template("GEO"), "GEO")}
    assert {"library strategy", "organism", "genome build/assembly"} <= out


def test_the_real_sra_template_declares_its_known_required_fields():
    out = {f.name for f in sr.required_fields(sr.load_template("SRA"), "SRA")}
    assert {"sample_name", "organism", "collection_date"} <= out


def test_a_malformed_document_yields_nothing_rather_than_raising():
    assert sr.required_fields({"study": "not a dict"}, "GEO") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --with pytest pytest tests/test_schema_repositories.py -q`
Expected: FAIL — `ImportError: cannot import name 'repositories' from 'schema'`

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/schema/repositories.py`:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Repository requirements, read from templates the plugin already vendors.

`context/report_templates/` ships the GEO, SRA and PRIDE templates that `report`
mode writes against. `schema` mode has never opened them, and they are the
strongest evidence available: they say which fields a submission is REJECTED
without, and they carry the exact vocabularies those repositories enforce.

Nothing here calls a network. The files are vendored and versioned with the
plugin, so this source works with no key and no connectivity.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_FILES = {
    "GEO": "GEO-updated.json",
    "SRA": "SRA.json",
    "PRIDE": "pride.json",
}

_CONTEXT_SUBDIR = Path("context") / "report_templates"


@dataclass
class RepositoryField:
    """One field a repository asks for."""

    name: str
    section: str
    repository: str
    required: bool = False
    conditional: bool = False


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def load_template(repository: str, root: Path | None = None) -> dict:
    """Read one vendored repository template. Returns {} if absent."""
    filename = REPOSITORY_FILES.get(repository)
    if not filename:
        return {}
    path = (root or _plugin_root()) / _CONTEXT_SUBDIR / filename
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - a missing template must not break a run
        return {}


def _mark(key: str) -> tuple[str, bool, bool]:
    """Split a template key into (name, required, conditional).

    `**` marks conditionally required and must be tested BEFORE `*`, or every
    conditional field is misread as unconditionally required.
    """
    if key.startswith("**"):
        return key[2:].strip(), False, True
    if key.startswith("*"):
        return key[1:].strip(), True, False
    return key.strip(), False, False


def _collect(node, section: str, repository: str, out: list[RepositoryField]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                name, required, conditional = _mark(key)
                if required or conditional:
                    out.append(RepositoryField(name=name, section=section,
                                               repository=repository,
                                               required=required,
                                               conditional=conditional))
            _collect(value, section, repository, out)
    elif isinstance(node, list):
        for item in node:
            _collect(item, section, repository, out)


def required_fields(doc: dict, repository: str) -> list[RepositoryField]:
    """Every `*` or `**` marked field, deduplicated, in document order."""
    if not isinstance(doc, dict):
        return []
    found: list[RepositoryField] = []
    for section, node in doc.items():
        if section in ("schema", "report_writer_guidance", "controlled_vocabulary",
                       "notes", "format", "description", "report_type"):
            continue
        _collect(node, section, repository, found)

    seen: set[str] = set()
    unique: list[RepositoryField] = []
    for f in found:
        if f.name in seen:
            continue
        seen.add(f.name)
        unique.append(f)
    return unique
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --with pytest pytest tests/test_schema_repositories.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/repositories.py tests/test_schema_repositories.py
git commit -m "feat(schema): read required fields from the vendored GEO/SRA/PRIDE templates"
```

---

### Task 3: Repository vocabularies and type-to-repository mapping

**Files:**
- Modify: `scripts/schema/repositories.py`
- Test: `tests/test_schema_repositories.py`

**Interfaces:**
- Consumes: `load_template` from Task 2.
- Produces:
  - `controlled_vocabularies(doc: dict) -> dict[str, list[str]]`
  - `repositories_for(record: dict) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_schema_repositories.py`:

```python
# --- vocabularies and applicability ----------------------------------------

D_SEQ = {"SampleType": "D.SEQ",
         "Associated Assay Parents": "Short Read Sequencing",
         "Tags": "sequencing data, FASTQ, raw reads, NGS data"}
D_MSP = {"SampleType": "D.MSP",
         "Associated Assay Parents": "Mass Spectrometry Proteomics",
         "Tags": "mass spectrometry data, proteomics data"}
D_VIA = {"SampleType": "D.VIA",
         "Associated Assay Parents": "Cell Viability Assay",
         "Tags": "viability data, cell viability, cytotoxicity data"}


def test_controlled_vocabularies_reads_the_top_level_block():
    doc = {"controlled_vocabulary": {"library_strategy": ["WGS", "RNA-Seq"],
                                     "authority": "a prose note"}}
    assert sr.controlled_vocabularies(doc) == {"library_strategy": ["WGS", "RNA-Seq"]}


def test_controlled_vocabularies_drops_non_list_entries():
    """`authority` is a prose string, not a vocabulary."""
    doc = {"controlled_vocabulary": {"authority": "mined from the template"}}
    assert sr.controlled_vocabularies(doc) == {}


def test_controlled_vocabularies_falls_back_to_the_schema_block():
    """PRIDE nests its vocabularies under `schema`, not at the top level."""
    doc = {"schema": {"controlled_vocabularies": {"modification": ["Oxidation"]}}}
    assert sr.controlled_vocabularies(doc) == {"modification": ["Oxidation"]}


def test_controlled_vocabularies_of_a_document_with_none():
    assert sr.controlled_vocabularies({"study": {}}) == {}


def test_the_real_geo_template_carries_its_enforced_vocabularies():
    cv = sr.controlled_vocabularies(sr.load_template("GEO"))
    assert len(cv["library_strategy"]) == 41
    assert len(cv["instrument_model_flat"]) == 82
    assert "RNA-Seq" in cv["library_strategy"]


def test_a_sequencing_type_maps_to_geo_and_sra():
    assert sr.repositories_for(D_SEQ) == ("GEO", "SRA")


def test_a_proteomics_type_maps_to_pride():
    assert sr.repositories_for(D_MSP) == ("PRIDE",)


def test_a_type_no_public_repository_covers_maps_to_nothing():
    """D.VIA is thin by fact, not by failure. The review must be able to say so."""
    assert sr.repositories_for(D_VIA) == ()


def test_matching_is_case_insensitive():
    assert sr.repositories_for({"Associated Assay Parents": "SHORT READ SEQUENCING",
                                "Tags": ""}) == ("GEO", "SRA")


def test_a_record_missing_both_fields_maps_to_nothing():
    assert sr.repositories_for({}) == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --with pytest pytest tests/test_schema_repositories.py -q`
Expected: FAIL — `AttributeError: module 'schema.repositories' has no attribute 'controlled_vocabularies'`

- [ ] **Step 3: Write the minimal implementation**

Append to `scripts/schema/repositories.py`:

```python
# Keywords matched against a record's producing assay and Tags. Deliberately
# narrow: a type mapping to no public repository (D.VIA, D.FLOW, D.PRM) must
# come back empty so the review can say the source is thin BY FACT, not by
# failure. Padding this list would put unevidenced fields in front of a curator.
REPOSITORY_KEYWORDS = {
    "GEO": ("sequencing", "rna-seq", "rnaseq", "microarray", "chip-seq",
            "atac", "expression profiling"),
    "SRA": ("sequencing", "rna-seq", "rnaseq", "wgs", "wxs", "amplicon",
            "metagenom"),
    "PRIDE": ("proteomic", "mass spectrometry", "mass-spec", "peptide",
              "protein identification"),
}


def controlled_vocabularies(doc: dict) -> dict[str, list[str]]:
    """The value lists a repository enforces, keyed by its own field names.

    Only list-valued entries are vocabularies. The block also carries prose
    (`authority`) and a nested by-platform mapping, neither of which is a flat
    permissible-value list.
    """
    if not isinstance(doc, dict):
        return {}
    block = doc.get("controlled_vocabulary")
    if not isinstance(block, dict):
        block = (doc.get("schema") or {}).get("controlled_vocabularies")
    if not isinstance(block, dict):
        return {}
    return {k: v for k, v in block.items() if isinstance(v, list) and v}


def repositories_for(record: dict) -> tuple[str, ...]:
    """Which public repositories cover this sample type's data, if any."""
    haystack = " ".join([
        str((record or {}).get("Associated Assay Parents") or ""),
        str((record or {}).get("Tags") or ""),
    ]).casefold()
    if not haystack.strip():
        return ()
    return tuple(name for name, keywords in REPOSITORY_KEYWORDS.items()
                 if any(k in haystack for k in keywords))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --with pytest pytest tests/test_schema_repositories.py -q`
Expected: `20 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/repositories.py tests/test_schema_repositories.py
git commit -m "feat(schema): map a sample type to the repositories that cover it"
```

---

### Task 4: `## Repository requirements` section in the review

**Files:**
- Modify: `scripts/schema/review.py` (`REQUIRED_SECTIONS` tuple; `render_review` signature and body)
- Test: `tests/test_curate_sampletype.py`

**Interfaces:**
- Consumes: `RepositoryField` from Task 2, `repositories_for` from Task 3.
- Produces: `render_review(..., repository_requirements: dict | None = None)` where the dict is `{"repositories": list[str], "fields": list[dict], "vocabularies": dict[str, int], "reason": str}` and each field dict is `{"name", "section", "repository", "required", "conditional", "held"}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curate_sampletype.py`:

```python
# --- repository requirements ------------------------------------------------

REPO_REQS = {
    "repositories": ["GEO", "SRA"],
    "fields": [
        {"name": "library strategy", "section": "samples", "repository": "GEO",
         "required": True, "conditional": False, "held": "LibraryStrategy"},
        {"name": "genome build/assembly", "section": "protocols",
         "repository": "GEO", "required": True, "conditional": False,
         "held": ""},
        {"name": "tissue", "section": "samples", "repository": "GEO",
         "required": False, "conditional": True, "held": ""},
    ],
    "vocabularies": {"library_strategy": 41, "instrument_model_flat": 82},
    "reason": "",
}


def _render_with_repos(reqs):
    return sr.render_review(
        "D.SEQ", record=RECORD,
        current_fields={"required": [], "standard": [], "possible": []},
        proposals=[], reuse_decisions=[], ontology={},
        open_questions=[], dictionary_entries=[],
        repository_requirements=reqs)


def test_repository_requirements_is_a_required_section():
    assert "## Repository requirements" in sr.REQUIRED_SECTIONS


def test_repository_requirements_precedes_the_other_evidence():
    """The strongest source is read first."""
    text = _render()
    assert text.index("## Current state") \
        < text.index("## Repository requirements") \
        < text.index("## External clade evidence")


def test_repository_requirements_names_the_repositories_consulted():
    text = _render_with_repos(REPO_REQS)
    assert "GEO" in text and "SRA" in text


def test_repository_requirements_marks_a_field_this_type_already_holds():
    text = _render_with_repos(REPO_REQS)
    section = text.split("## Repository requirements")[1].split("## External")[0]
    assert "LibraryStrategy" in section


def test_repository_requirements_distinguishes_conditional_from_required():
    text = _render_with_repos(REPO_REQS)
    section = text.split("## Repository requirements")[1].split("## External")[0]
    assert "conditional" in section.lower()


def test_repository_requirements_reports_the_enforced_vocabularies():
    text = _render_with_repos(REPO_REQS)
    assert "library_strategy" in text and "82" in text


def test_repository_requirements_says_when_no_repository_covers_the_type():
    """D.VIA is thin by fact. Never let that read as a failed lookup."""
    text = _render_with_repos({"repositories": [], "fields": [], "vocabularies": {},
                               "reason": "no public repository covers this data type"})
    assert "no public repository covers this data type" in text


def test_repository_requirements_defaults_to_not_consulted():
    text = _render_with_repos(None)
    section = text.split("## Repository requirements")[1].split("##")[0]
    assert "not consulted" in section.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py -q`
Expected: FAIL — `TypeError: render_review() got an unexpected keyword argument 'repository_requirements'`

- [ ] **Step 3: Write the minimal implementation**

In `scripts/schema/review.py`, add to `REQUIRED_SECTIONS` between `"## Current state"` and `"## External clade evidence"`:

```python
    "## Repository requirements",
```

Add the keyword argument to `render_review`, after `template_checklist`:

```python
                  repository_requirements: dict | None = None) -> str:
```

Insert this block immediately before `lines.append("## External clade evidence")`:

```python
    lines.append("## Repository requirements")
    lines.append("")
    lines.append("The strongest evidence available, and the only source that is "
                 "enforced: a submission is REJECTED without these. Read from the "
                 "GEO, SRA and PRIDE templates vendored in "
                 "`context/report_templates/` - no network, no key.")
    lines.append("")
    reqs = repository_requirements or {}
    reason = reqs.get("reason") or ""
    fields = reqs.get("fields") or []
    if reason:
        lines.append(f"Nothing returned - {reason}.")
        lines.append("")
    elif not repository_requirements:
        lines.append("Not consulted this run.")
        lines.append("")
    else:
        repos = ", ".join(reqs.get("repositories") or []) or "(none)"
        lines.append(f"Consulted: **{repos}**.")
        lines.append("")
        for f in fields:
            kind = "conditional" if f.get("conditional") else "required"
            held = f.get("held") or ""
            status = f"already held as `{held}`" if held else "**NOT HELD**"
            lines.append(f"- `{f.get('name', '')}` - {kind} in "
                         f"{f.get('repository', '')} ({f.get('section', '')}) - {status}")
        lines.append("")
        vocabs = reqs.get("vocabularies") or {}
        if vocabs:
            lines.append("Vocabularies these repositories enforce, usable directly "
                         "as permissible values:")
            lines.append("")
            for name, count in vocabs.items():
                lines.append(f"- `{name}` - {count} values")
            lines.append("")

    lines.append("## External clade evidence")
```

Then delete the now-duplicated original `lines.append("## External clade evidence")` line that followed.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py -q`
Expected: all pass, including the 8 new tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/review.py tests/test_curate_sampletype.py
git commit -m "feat(schema): surface repository requirements as the first evidence section"
```

---

### Task 5: CEDAR template selection as an agent step — REDESIGNED, DONE

**Superseded the original deterministic `select_template`.** The live gate
caught it choosing wrongly in both directions, and the cause is not fixable by a
better query or a better score.

CEDAR matches **token prefixes against template NAMES**. So:

| query | hits | meaning |
|---|---|---|
| `sequencing` | 0 | a BAD QUERY — templates are named `seq`, never `sequencing` |
| `*seq*` | 18 | RNA-Seq, ATAC-Seq, DBiT-seq, Seq-Scope, Pixel-seq, MiAIRR |
| `*viab*` | 0 | a REAL ABSENCE — nothing viability-specific exists |
| `Cell Viability Assay` | 8 | all generic, matched on the stopword `assay` |

A function cannot tell row 1 from row 3 — both are zero. A reader comparing them
can. And a score-based picker ranks `Pistoia Alliance assay template` (63
fields) top for D.VIA and calls it type-specific, which is the exact defect this
plan exists to remove.

**What shipped:**
- `search_templates(query, ...)` stays the primitive — tested, unchanged.
- `select_template` is **deleted**, with a test asserting it stays deleted.
- `fallback_template()` supplies the pinned generic once the agent has concluded
  nothing fits.
- `commands/curate-sampletype.md` carries the search loop: query, inspect the
  names, strip stopwords, wildcard the distinctive stem, try abbreviation and
  expansion, try Tags terms, then JUDGE — and report which queries ran.

**Verified live.** D.SEQ: `Short Read Sequencing` → 0, `*seq*` → 8 real
candidates (Seq-Scope 26 fields/26 described/10 bound). D.VIA: absence confirmed
across `*viab*`, `*cytotox*`, `*cytom*`, `*flow*`, `*facs*` — all 0 — so its
fallback is earned rather than assumed.

### Task 6: Checklist section declares a fallback

**Files:**
- Modify: `scripts/schema/review.py` (the `## Reference template checklist` block)
- Test: `tests/test_curate_sampletype.py`

**Interfaces:**
- Consumes: `select_template` from Task 5.
- Produces: `template_checklist` dict gains an `is_fallback: bool` key. Existing keys (`template`, `total`, `strong`, `weak`, `missing`, `reason`) are unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curate_sampletype.py`:

```python
def test_checklist_declares_when_it_fell_back_to_the_generic_template():
    """A generic checklist read as type-specific is the defect this replaces."""
    text = _render_with_checklist({**CHECKLIST, "is_fallback": True})
    section = text.split("## Reference template checklist")[1].split("## Proposed")[0]
    assert "no type-specific" in section.lower() or "generic" in section.lower()


def test_checklist_does_not_hedge_a_domain_specific_template():
    text = _render_with_checklist(
        {**CHECKLIST, "template": "RNA-Seq Metadata", "is_fallback": False})
    section = text.split("## Reference template checklist")[1].split("## Proposed")[0]
    assert "generic" not in section.lower()
    assert "RNA-Seq Metadata" in section
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py -k checklist -q`
Expected: FAIL on `test_checklist_declares_when_it_fell_back_to_the_generic_template` — the word is absent.

- [ ] **Step 3: Write the minimal implementation**

In `scripts/schema/review.py`, inside the checklist `else:` branch, immediately after the `n_strong, n_weak = ...` line and its `lines.append(...)` block, add:

```python
        if checklist.get("is_fallback"):
            lines.append("")
            lines.append("**No type-specific template matched this assay, so this "
                         "is the GENERIC fallback.** Read every row as a question "
                         "about assays in general, not about this one.")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --with pytest --with openpyxl pytest tests/test_curate_sampletype.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/review.py tests/test_curate_sampletype.py
git commit -m "feat(schema): say when the template checklist is the generic fallback"
```

---

### Task 7: Value precedence — repository and CEDAR branch sources

**Files:**
- Modify: `scripts/schema/ontology.py` (`_SOURCE_RANK`, `propose_values`, the notes dict)
- Test: `tests/test_schema_ontology.py`

**Interfaces:**
- Consumes: `controlled_vocabularies` from Task 3, `field_vocabulary` from Task 1.
- Produces: `propose_values(record, field_name, *, observed=None, tags=None, siblings=None, bioportal=None, cedar_branch=None, repository=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_schema_ontology.py`:

```python
# --- precedence -------------------------------------------------------------
#
# A submission is literally rejected against a repository vocabulary, so it
# outranks everything except a real observed workbook value (hard rule 4).
# Tags drops to the floor: it is a per-sample-type prose list, not a per-field
# vocabulary, and binding it to one field is an unverifiable assertion.

RECORD_WITH_TAGS = {"SampleType": "D.SEQ", "Tags": "RNA-Seq, FASTQ"}


def test_repository_outranks_bioportal_for_the_same_value():
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            bioportal=["RNA-Seq"], repository=["RNA-Seq"])
    assert [p.source for p in out if p.value == "RNA-Seq"] == ["repository"]


def test_observed_still_outranks_repository():
    """Hard rule 4: the workbook beats every declared schema."""
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            repository=["RNA-Seq"], observed=["RNA-Seq"])
    assert [p.source for p in out if p.value == "RNA-Seq"] == ["observed"]


def test_bioportal_outranks_a_cedar_branch_value():
    out = so.propose_values({}, "assay footprint", tags=[],
                            cedar_branch=["microplate"], bioportal=["microplate"])
    assert [p.source for p in out if p.value == "microplate"] == ["bioportal"]


def test_cedar_branch_outranks_a_tag():
    out = so.propose_values({}, "x", tags=["microplate"], cedar_branch=["microplate"])
    assert [p.source for p in out if p.value == "microplate"] == ["cedar_branch"]


def test_a_repository_value_carries_an_explanatory_note():
    out = so.propose_values({}, "LibraryStrategy", tags=[], repository=["WGS"])
    assert "reject" in out[0].note.lower()


def test_every_source_still_contributes_its_unique_values():
    out = so.propose_values(RECORD_WITH_TAGS, "LibraryStrategy",
                            repository=["WGS"], bioportal=["exome sequencing"])
    assert {p.value for p in out} == {"RNA-Seq", "FASTQ", "WGS", "exome sequencing"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --with pytest pytest tests/test_schema_ontology.py -q`
Expected: FAIL — `TypeError: propose_values() got an unexpected keyword argument 'repository'`

- [ ] **Step 3: Write the minimal implementation**

In `scripts/schema/ontology.py`, replace `_SOURCE_RANK` with:

```python
# Strongest source LAST: a later source overwrites an earlier one for the same
# literal value. `observed` stays top per hard rule 4 - the workbook outranks
# the schema. `repository` sits directly beneath it because a submission is
# literally rejected against those lists. `tags` is the floor: it is a
# per-sample-type prose list, not a per-field vocabulary.
_SOURCE_RANK = {"tags": 0, "sibling": 1, "cedar_branch": 2, "bioportal": 3,
                "repository": 4, "observed": 5}
```

Replace the `propose_values` signature with:

```python
def propose_values(record: dict, field_name: str, *,
                   observed: list[str] | None = None,
                   tags: list[str] | None = None,
                   siblings: list[str] | None = None,
                   bioportal: list[str] | None = None,
                   cedar_branch: list[str] | None = None,
                   repository: list[str] | None = None) -> list[ProposedValue]:
```

Replace the `contributions` block with:

```python
    contributions: list[tuple[str, str]] = []
    contributions += [(v, "tags") for v in tags]
    contributions += [(v, "sibling") for v in (siblings or [])]
    contributions += [(v, "cedar_branch") for v in (cedar_branch or [])]
    contributions += [(v, "bioportal") for v in (bioportal or [])]
    contributions += [(v, "repository") for v in (repository or [])]
    contributions += [(v, "observed") for v in (observed or [])]
```

Add these two entries to the `notes` dict:

```python
        "cedar_branch": "from the ontology branch a CEDAR template binds this field to",
        "repository": "enforced by the target repository; a submission is REJECTED without an exact match",
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --with pytest pytest tests/test_schema_ontology.py -q`
Expected: all pass, including the 6 new tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/schema/ontology.py tests/test_schema_ontology.py
git commit -m "feat(schema): rank repository vocabularies above ontology suggestions"
```

---

### Task 8: Wire all four sources into the command loop and reference

**Files:**
- Modify: `commands/curate-sampletype.md` (steps 2 and 3 of The loop)
- Modify: `skills/curation/SCHEMA.md`

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: nothing in code.

- [ ] **Step 1: Replace the evidence bullets in `commands/curate-sampletype.md`**

In step 2 of The loop, insert these two bullets BEFORE the existing
`- **external clade evidence**` bullet:

```markdown
   - **repository requirements** via `scripts/schema/repositories.py` - the
     strongest source, and local. `repositories_for(record)` says which of
     GEO / SRA / PRIDE cover this data type; `required_fields(load_template(r), r)`
     gives the fields a submission is REJECTED without, and
     `controlled_vocabularies(load_template(r))` gives the value lists those
     repositories enforce (GEO alone ships 41 library strategies and 82
     instrument models). No key, no network. A type no repository covers comes
     back EMPTY - that is a fact about the type, not a failed lookup, and the
     review must say so.
   - **a type-specific CEDAR template** via `templates.select_template(record)`,
     which searches on the producing assay and returns
     `(candidate, is_fallback)`. Pinning one generic template gave D.VIA and
     D.SEQ an identical 28-row checklist; `RNA-Seq` returns 8 templates and
     `ATAC` 2, while `viability`, `cytometry` and `flow` return 0. When
     `is_fallback` is True you are reading a GENERIC assay checklist - pass the
     flag through so the review says so.
```

- [ ] **Step 2: Replace step 3 of The loop**

```markdown
3. **Identify gaps.** What does this assay produce that the record does not
   capture? Weigh the four sources by what each can actually establish:

   - a **repository-required** field this type lacks is the strongest signal
     available - a submission fails without it
   - a **type-specific CEDAR** field is a community convention; a **fallback**
     CEDAR field is a question about assays in general
   - **OBI clade** evidence suggests an AXIS to think about, never a field. Read
     the sibling definitions and name the axis yourself
   - your own **research knowledge** is what explains why any of it applies
     here, and it belongs in the rationale for every proposal

   None of them is an instruction. A field required by GEO and absent here is
   still a question for the curator.
```

- [ ] **Step 3: Add the reference section to `skills/curation/SCHEMA.md`**

Insert immediately before `## The reference template checklist`:

```markdown
## Repository requirements - the strongest source, and already local

`context/report_templates/` ships the GEO, SRA and PRIDE templates `report` mode
writes against, and `schema` mode never opened them. They carry two things no
other source has: the fields a submission is REJECTED without (`*` required,
`**` conditionally required), and the vocabularies those repositories enforce -
`library_strategy` (41), `instrument_model_flat` (82), `library_selection` (33),
`platform` (17).

This outranks BioPortal for any type deposited publicly. D.SEQ's `Sequencer`
should validate against GEO's 82 instrument models - the list a submission is
actually rejected against - not the 6 OBI classes a search returns. SKILL.md
already records the cost of getting this wrong: `paired-end` not `paired`,
`Illumina NextSeq 500` not `NextSeq 500`.

`repositories_for(record)` matches the producing assay and Tags against narrow
keyword sets. It is deliberately narrow: D.VIA, D.FLOW and D.PRM come back
EMPTY, and that emptiness is a fact about those types, not a failure. Padding
the keyword list would put unevidenced fields in front of a curator, which is
what this mode exists to prevent.
```

- [ ] **Step 4: Run the full suite**

Run: `uv run --with pytest --with openpyxl --with pandas --with requests --with pyarrow pytest tests/ -q`
Expected: `0 failed`, and total passed = 1568 baseline + every test added in Tasks 2-7.

- [ ] **Step 5: End-to-end demo run — REQUIRED**

Run in a scratch directory, NEVER in the plugin root (`schema/` there fails
`test_no_prebuilt_dictionary_ships_with_the_plugin`):

```bash
mkdir -p /tmp/curate-demo && cd /tmp/curate-demo
```

Generate `D.SEQ` and `D.VIA` reviews through all four sources and confirm by eye:
D.SEQ shows GEO+SRA requirements and a non-fallback template; D.VIA shows an
empty repository section stating no public repository covers it, and a checklist
declaring itself the generic fallback. **The two reviews must no longer be
substantially identical** — that identity is the defect this plan exists to fix.

- [ ] **Step 6: Commit**

```bash
git add commands/curate-sampletype.md skills/curation/SCHEMA.md
git commit -m "docs(schema): document all four evidence sources and how they rank"
```

---

## Self-Review

**Spec coverage.** Source 1 → Tasks 2, 3, 4. Source 2 → Tasks 5, 6. Source 3 →
Task 1 (already built). Source 4 → Task 8 step 2, as rationale guidance. Value
precedence → Task 7. Review structure → Tasks 4, 6. The resolved open question
(thin reviews for uncovered types stay thin) → Task 3's narrow keyword sets and
Task 4's "says when no repository covers the type" test.

**Placeholders.** None. Every code step carries the literal code; every test
step carries the literal test.

**Type consistency.** `RepositoryField` (Task 2) is consumed by Task 4's dict
shape. `TemplateCandidate` (Task 5) is consumed by Task 6's `is_fallback` key.
`propose_values` keyword names `cedar_branch` and `repository` (Task 7) match
`_SOURCE_RANK` keys and the `notes` dict keys exactly. `field_vocabulary`'s
signature (Task 1) is used unchanged in Task 8's documentation.

**Not covered, deliberately.** Wiring the sources into a single runner script is
out of scope: the mode is agent-driven from `commands/curate-sampletype.md`, and
Task 8 documents the calls rather than adding a CLI that nothing else in this
mode has.
