"""P1: no script may read or write inside the plugin checkout.

Each script is run from a tmpdir curation project. The plugin_sentinel
fixture hashes the whole plugin tree (files *and* directories) before and
after and fails on any change. Scripts that need inputs get them inside the
tmpdir, never in the plugin.

The assertion families:

  test_script_writes_nothing_in_plugin
      Behavioural: run the script, sentinel asserts the checkout is byte- and
      entry-identical afterwards.

  test_script_does_not_reference_plugin_paths_in_output
      Behavioural: a path under the plugin checkout appearing in stdout/stderr
      means the script resolved a PROJECT path against the plugin install dir.
      This is the assertion that catches the *read* half of P1, which the
      sentinel (a write guard) cannot see. It also takes the sentinel, so a
      write during these runs is caught here rather than polluting the next
      test's baseline.

  test_apply_geo_accessions_finds_project_sheets
      Behavioural, single-script: apply_geo_accessions.py prints basenames only,
      so the generic output filter is blind to it. This case puts a real sheet
      in the *project* and asserts the script finds it.

  test_nextseek_fetch_assays_caches_in_the_project_not_the_plugin
      Behavioural, single-script: the assay-id cache is project-scoped state
      that is currently *written* into <plugin>/context/. The output filter
      whitelists /context/ (it cannot tell a read from a write) and the static
      test allows it (plugin context/ is legitimately read from __file__), so
      only a write-specific case can see this one.

  test_no_script_anchors_project_paths_at_the_plugin_dir
      Static: the defect in its source form. Several scripts only reach their
      buggy path resolution when given inputs they do not have here, so the
      behavioural tests alone under-report.

SCOPE OF THE STATIC TEST (it is *not* exhaustive, and must not be described as
such). It is a line-based regex over source text, gated on the identifier
actually being bound from ``__file__`` in that same file. It therefore catches:

  * ``<file-root> / "literal"`` and ``os.path.join(<file-root>, "literal", …)``
    where the literal is not a plugin-owned name, and
  * ``os.path.join(<file-root>, <variable>)``, which rewrites a user-supplied
    relative project path onto the plugin root.

It does NOT catch: joins built with f-strings or ``%``/``.format``; paths
assembled across multiple statements (``p = ROOT; p = p / name``); ``os.chdir``
onto a plugin root; or a root smuggled through a function argument. The
behavioural families exist precisely because this one has holes.

The allowlist is inverted relative to the obvious design: rather than
enumerating *project* directory names (an open-ended list that silently misses
anything unanticipated -- ``new_files_from_lee`` was one such miss), it
enumerates the *plugin-owned* names, which are a closed set verifiable against
the checkout itself. Anything else joined onto a ``__file__`` root is treated as
a project path.

NOTE ON THE ``__file__`` GATE. Matching on the *names* ``ROOT``/``REPO`` alone
failed in both directions. A rename to ``PLUGIN_DIR`` would have turned every
flagged line green with the bug fully intact (``\\bROOT\\b`` does not match
``PLUGIN_DIR``), and the *correct* fix -- ``ROOT = project_root()`` resolved from
cwd -- would have stayed red, pressuring a pointless rename. The gate below asks
whether the identifier in the join is bound from ``__file__`` *in that file*, via
``ast``, so it is insensitive to naming and tracks the actual defect.

NOTE ON ARGV (deviation from the task brief): the brief's argv table passed
``--assay-sheets`` to consolidate_to_flat.py and ``--upload`` to
qa_flat_sheets.py. Neither flag exists -- argparse would exit 2 with a usage
string that contains no plugin path, so both cases would have gone falsely
GREEN and the harness would have licensed a no-op Task 8. The argv below is
the minimum each script accepts to reach its *defaulted* project paths, with
every explicitly-passed input living inside the tmpdir project. In particular
no script is handed a path override for the directory whose default is the
bug.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE_XLSX = REPO / "tests" / "fixtures" / "sample.xlsx"

# A metadata workbook inside the project, so scripts that glob
# <ROOT>/previous_metadata/*All*.xlsx don't bail before reaching the
# path-resolution we are testing. Passed as a cwd-relative path.
PROJECT_META = "previous_metadata/Project_All_Metadata.xlsx"
PROJECT_GSM_CSV = "gsm_roster.txt"

# Every script that resolved paths against the plugin dir before Task 8,
# with an argv that should be a no-op or a dry-run inside the project.
PLUGIN_ANCHORED = [
    ("scripts/consolidate_to_flat.py", []),
    ("scripts/qa_flat_sheets.py", ["assay_sheets/ArmA.xlsx"]),
    ("scripts/stage_zenodo.py", ["--metadata-xlsx", PROJECT_META]),
    ("scripts/apply_zenodo_links.py",
     ["--record-id", "1", "--metadata-xlsx", PROJECT_META]),
    ("scripts/apply_geo_accessions.py",
     ["--gse-bulk", "GSE000000", "--gsm-csv", PROJECT_GSM_CSV]),
    ("scripts/review_metadata_vs_uploads.py",
     ["--metadata-xlsx", PROJECT_META]),
    ("scripts/build_retrieve.py", ["--assay-sheets", "assay_sheets"]),
]

# Scripts that must not compute a *project* path from their own location.
# scripts/fdh/generated/* are excluded: their parent.parent is a sys.path
# insert for the sibling fdh package, not a project path.
#
# MAINTENANCE_SCRIPTS are excluded for a different reason. scripts/refresh_context.py
# is the one plugin-MAINTENANCE script: a maintainer runs it *against* the plugin to
# refresh context/ from a fresh chat_nextseek export, so it legitimately anchors
# at, and writes into, the plugin's own context/ dir -- precisely the pattern
# this static check forbids for *curation* scripts. It never receives a project
# path (its only inputs are --check and an explicit --from-dir), so it has no
# project-path-anchoring defect to catch, and it is deliberately absent from
# PLUGIN_ANCHORED / the plugin_sentinel families because writing the checkout is
# its whole job. Excluding it here removes no protection from any curation
# script. See scripts/refresh_context.py, context/PROVENANCE.json, and Task 18.
#
# The allowlist is pinned to the exact repo-relative *path*, not the basename:
# the glob below is recursive, so matching on p.name alone would silently drop
# any future curation script that happened to be named refresh_context.py in
# some subdir (e.g. scripts/report/refresh_context.py) from the static check.
MAINTENANCE_SCRIPTS = frozenset({"scripts/refresh_context.py"})

PROJECT_SCRIPTS = sorted(
    p for p in REPO.glob("scripts/**/*.py")
    if "generated" not in p.relative_to(REPO).parts
    and str(p.relative_to(REPO)) not in MAINTENANCE_SCRIPTS
)

# Top-level names that belong to the *plugin install* and may legitimately be
# resolved from __file__. This is the plugin's own contents -- a closed set you
# can check against `ls` in the checkout -- which is why the detector inverts
# the allowlist instead of trying to enumerate project directory names.
#
# `context` stays allowed deliberately: consolidate_to_flat.py:86-87 and
# qa_flat_sheets.py:108 only ever open() plugin context/ for READ, which the
# constraint permits. The one context/ *write* (nextseek_api.py) is caught by
# its own behavioural case below, not by broadening this list.
PLUGIN_OWNED_NAMES = frozenset({
    ".env", ".env.example", ".claude-plugin",
    "context", "templates", "commands", "skills", "docs", "scripts", "tests",
    "README.md", "CHANGELOG.md", "LICENSE",
})


def _file_derived_roots(text: str) -> set[str]:
    """Names in this module bound from an expression mentioning ``__file__``.

    ``ROOT = Path(__file__).resolve().parent.parent`` -> {"ROOT"}.
    ``ROOT = project_root()`` (the shape Task 8 moves to) -> set(), so joining a
    project directory onto it is *not* flagged. A rename to ``PLUGIN_DIR``
    keeping the ``__file__`` derivation is still flagged. Uses ast, so multi-line
    and parenthesised bindings are handled.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(n, ast.Name) and n.id == "__file__"
                   for n in ast.walk(value)):
            continue
        for target in targets:
            for n in ast.walk(target):
                if isinstance(n, ast.Name):
                    names.add(n.id)
    return names


def _anchor_hits(script_rel: str, text: str) -> list[str]:
    """Lines joining a project path onto a ``__file__``-derived root."""
    roots = _file_derived_roots(text)
    if not roots:
        return []
    alt = "|".join(re.escape(n) for n in sorted(roots))
    # ROOT / "literal"  and  os.path.join(REPO, "literal", ...)
    join_re = re.compile(
        r"(?<![A-Za-z0-9_])(?:" + alt + r")(?![A-Za-z0-9_])"
        r"\s*(?:/|,)\s*(['\"])(?P<name>[^'\"]*)\1"
    )
    # os.path.join(REPO, upload) -- a user-supplied relative path rewritten
    # onto the plugin root.
    var_re = re.compile(
        r"os\.path\.join\(\s*(?:" + alt + r")\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*\)"
    )
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        flagged = bool(var_re.search(line))
        if not flagged:
            flagged = any(m.group("name") not in PLUGIN_OWNED_NAMES
                          for m in join_re.finditer(line))
        if flagged:
            hits.append(f"{script_rel}:{i}: {line.strip()}")
    return hits


def _prepare(cwd: Path) -> None:
    """Materialise the project-local inputs the argv above refers to."""
    meta = cwd / PROJECT_META
    if not meta.exists():
        meta.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_XLSX, meta)
    gsm = cwd / PROJECT_GSM_CSV
    if not gsm.exists():
        gsm.write_text("GSM0000001 Sample_One_D000001\n")


def _run(script_rel: str, argv: list[str], cwd: Path, env: dict | None = None):
    _prepare(cwd)
    return subprocess.run(
        ["uv", "run", "--script", str(REPO / script_rel), *argv],
        cwd=cwd, capture_output=True, text=True, timeout=600, env=env,
    )


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_writes_nothing_in_plugin(script_rel, argv, curation_project,
                                         plugin_sentinel):
    """The script may fail (missing inputs is fine). It may not touch the plugin."""
    _run(script_rel, argv, curation_project)
    # plugin_sentinel asserts on teardown.


@pytest.mark.parametrize("script_rel,argv", PLUGIN_ANCHORED)
def test_script_does_not_reference_plugin_paths_in_output(script_rel, argv,
                                                          curation_project,
                                                          plugin_sentinel):
    """A path under the plugin checkout appearing in output means the script
    resolved a PROJECT path against the plugin install dir."""
    result = _run(script_rel, argv, curation_project)
    blob = result.stdout + result.stderr
    plugin_str = str(REPO)
    leaked = [
        line for line in blob.splitlines()
        if plugin_str in line
        # The script's own path legitimately appears in tracebacks and usage.
        and script_rel.split("/")[-1] not in line
        and "/context/" not in line          # read-only plugin context is allowed
        and "/templates/" not in line        # read-only plugin templates are allowed
    ]
    assert not leaked, (
        f"{script_rel} resolved a project path against the plugin dir:\n"
        + "\n".join(leaked[:10])
    )


def test_apply_geo_accessions_finds_project_sheets(curation_project,
                                                   plugin_sentinel):
    """apply_geo_accessions.py must look for upload sheets in the PROJECT.

    Its whole stdout is basenames, so the output filter above is structurally
    blind to it, and its only other guard is the static test. This case is the
    one assertion that goes red -> green on a genuine fix: the sheet exists in
    the project, so "not found" can only mean the script looked in
    <plugin>/assay_sheets (scripts/apply_geo_accessions.py:40).

    Placed here rather than in the shared curation_project fixture on purpose:
    dropping a real upload sheet into every case would change what
    consolidate_to_flat.py / qa_flat_sheets.py / apply_zenodo_links.py do once
    Task 8 lands, risking reds for reasons unrelated to path anchoring.
    """
    sheet = curation_project / "assay_sheets" / "D.SEQ-upload-new.xlsx"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_XLSX, sheet)

    r = _run("scripts/apply_geo_accessions.py",
             ["--gse-bulk", "GSE000000", "--gsm-csv", PROJECT_GSM_CSV],
             curation_project)
    blob = r.stdout + r.stderr

    assert "not found — skipping D.SEQ patch" not in blob, (
        "apply_geo_accessions.py reported the project's own "
        "assay_sheets/D.SEQ-upload-new.xlsx as missing, i.e. it resolved "
        "assay_sheets against the plugin install dir:\n" + blob
    )
    assert "=== D.SEQ-upload-new.xlsx ===" in blob, (
        "the sheet was never opened; this case would be vacuous:\n" + blob
    )
    # No --write, so nothing in the project is modified either.
    assert not list((curation_project / "assay_sheets").glob("*.bak"))


class _NExtSEEKStubHandler(BaseHTTPRequestHandler):
    """Minimum JSON:API surface fetch-assays needs, served locally.

    fetch-assays needs credentials and a reachable API, and it returns before
    the write on any HTTP error -- so a bare run against the real host would
    make this case vacuous (green for the wrong reason). This stub lets the
    script reach line 306-317, which is where the defect lives.
    """

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?")[0]
        if path.startswith("/nextseek_api/projects/"):
            body = {"data": {"relationships": {"assays": {"data": [{"id": "1"}]}}}}
        elif path.startswith("/nextseek_api/assays/"):
            body = {"data": [{"id": "1", "attributes": {"title": "RNA Extraction"}}],
                    "links": {"next": None}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):  # silence per-request logging
        pass


@pytest.fixture
def nextseek_stub():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NExtSEEKStubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_nextseek_fetch_assays_caches_in_the_project_not_the_plugin(
        curation_project, nextseek_stub, plugin_sentinel):
    """`/curate-resolve-assays` must cache assay IDs in the PROJECT.

    scripts/nextseek_api.py:49 sets DEFAULT_CACHE_PATH = REPO / "context" /
    "assay_ids_cache.json" and :307/:317 mkdir + write_text it whenever
    --output is omitted, so the command writes project-scoped state into the
    plugin install. This escapes every other family: it has no PLUGIN_ANCHORED
    row, the output filter whitelists "/context/" (it cannot tell a read from a
    write), and the static test deliberately allows plugin context/ because two
    other scripts only *read* it.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEXTSEEK_")}
    r = _run("scripts/nextseek_api.py",
             ["fetch-assays", "--project-id", "42", "--token", "stub",
              "--base-url", nextseek_stub],
             curation_project, env=env)

    # Non-vacuity: the run must actually reach the write. If it did not, this
    # case proves nothing and the failure below is a harness bug, not a P1 fix.
    assert r.returncode == 0, (
        "fetch-assays did not complete against the local stub, so this case "
        f"cannot observe the write:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "wrote 1 assays to" in r.stderr, (
        "fetch-assays never reported a write; case would be vacuous:\n" + r.stderr
    )

    assert (curation_project / "context" / "assay_ids_cache.json").exists(), (
        "fetch-assays wrote its project-scoped assay-id cache outside the "
        "project. Reported destination:\n" + r.stderr
    )
    # plugin_sentinel independently confirms nothing landed in the checkout.


@pytest.mark.parametrize(
    "script_rel",
    [str(p.relative_to(REPO)) for p in PROJECT_SCRIPTS],
)
def test_no_script_anchors_project_paths_at_the_plugin_dir(script_rel):
    """P1 in its source form: a project path joined onto a __file__ root.

    Task 8 replaces these with a cwd-anchored project root (the shape
    build_retrieve.py already uses). Reading plugin-owned assets from
    __file__ stays fine -- only *project* paths are forbidden. See the module
    docstring for what this check does and does not cover.
    """
    text = (REPO / script_rel).read_text()
    hits = _anchor_hits(script_rel, text)
    assert not hits, (
        f"{script_rel} anchors project paths at the plugin install dir:\n"
        + "\n".join(hits)
    )


def test_static_check_tracks_the_defect_not_the_variable_name():
    """The static check must not be defeatable by, or trip on, a rename.

    Two failure modes this guards, both of which the name-based version had:
      * renaming ROOT -> PLUGIN_DIR while keeping the __file__ derivation would
        have turned every flagged line green with the bug intact;
      * the correct fix (ROOT = project_root(), resolved from cwd) would have
        stayed red, pressuring a pointless rename.
    """
    buggy = (
        "from pathlib import Path\n"
        'PLUGIN_DIR = Path(__file__).resolve().parent.parent\n'
        'SHEETS = PLUGIN_DIR / "assay_sheets"\n'
    )
    fixed = (
        "from pathlib import Path\n"
        "ROOT = project_root()\n"
        'SHEETS = ROOT / "assay_sheets"\n'
    )
    plugin_read = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parent.parent\n"
        'DB = ROOT / "context" / "sampletypes_db.json"\n'
    )
    assert _anchor_hits("buggy.py", buggy), "rename defeats the static check"
    assert not _anchor_hits("fixed.py", fixed), "cwd-anchored root falsely flagged"
    assert not _anchor_hits("ok.py", plugin_read), "plugin context/ read flagged"


def test_maintenance_allowlist_is_path_pinned():
    """The maintenance exclusion must match a full repo-relative path, not a
    bare basename.

    The glob feeding PROJECT_SCRIPTS is recursive, so a basename allowlist would
    silently exempt any future curation script named refresh_context.py in a
    subdir. Assert every entry carries a directory component (contains "/") and
    that the real script is still excluded while a same-named sibling would not
    be.
    """
    assert all("/" in entry for entry in MAINTENANCE_SCRIPTS), (
        "MAINTENANCE_SCRIPTS must hold repo-relative paths, not basenames: "
        f"{sorted(MAINTENANCE_SCRIPTS)}"
    )
    assert "scripts/refresh_context.py" in MAINTENANCE_SCRIPTS
    # The genuine maintenance script stays out of the static check...
    project_rels = {str(p.relative_to(REPO)) for p in PROJECT_SCRIPTS}
    assert "scripts/refresh_context.py" not in project_rels
    # ...but a hypothetical same-named curation script in a subdir would not be
    # exempted by a basename match.
    assert "scripts/report/refresh_context.py" not in MAINTENANCE_SCRIPTS


def test_reference_implementations_are_already_clean(curation_project,
                                                     plugin_sentinel):
    """build_retrieve.py and fdh_api.py are the models Task 8 refactors toward."""
    r = _run("scripts/build_retrieve.py",
             ["--assay-sheets", "assay_sheets", "--output", "RETRIEVE.TXT"],
             curation_project)
    assert r.returncode == 0, r.stderr
    assert (curation_project / "RETRIEVE.TXT").exists()
