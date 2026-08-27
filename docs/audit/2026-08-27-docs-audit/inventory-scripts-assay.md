# Ground-truth inventory — `scripts/assay_hygiene/`

Worktree: `/home/cdemurjian/code/dmac/curation_skill/.claude/worktrees/docs`, branch `dev-docs`,
tip `833e9be`. All paths below are repo-relative. Every claim was read out of the file cited.

39 files, 17,947 lines (`scripts/assay_hygiene/*.py`). 38 modules plus `__init__.py`, which is a
one-line docstring pointing at `docs/superpowers/specs/2026-08-12-assay-hygiene-design.md`
(`scripts/assay_hygiene/__init__.py:1`).

Package-wide: only **three** modules can reach a live server —
`extract.py` (read-only), `stage0_apply.py` (Neo4j write), `driver_stage0.py` (binds the real
driver). Nothing else imports `neo4j`, a Django connection, `requests`, `urllib` or any HTTP
client; verified by grep over the whole package. There is **no** module that POSTs to
`/seek/sampleupload/`.

---

## 1. Module map by role

### 1.1 Run lifecycle

| module | lines | CLI | purpose |
|---|---|---|---|
| `runstate.py` | 99 | no | the house-scoped run lockfile |
| `init_run.py` | 109 | no | open a run after proving the ruling store exists |
| `protect_run.py` | 48 | no | chmod a run's tiers read-only, and verify |

**`runstate.py`** — one run open at a time, at the *runs root* rather than a project dir
(`runstate.py:6-9`). Lockfile name `assay-run.json` (`runstate.py:22`), `SCHEMA_VERSION = 1`
(`:23`).
Entry points: `read(root)` (`:34`, absent file → `{}`, never raises), `create(root, run, extract_sha)`
(`:49`, raises `RunLocked` (`:26`) while another run is open), `update(root, **fields)` (`:72`,
**merges nested dicts one level** so `write={"rollback_id": n}` cannot drop `backup_verified` —
`:75-81`), `close(root)` (`:93`).
Created state shape (`:57-69`): `schema_version, run, open, pid, extract_sha, step, rulings_ingested,
carried_from_run, carried_pairs, write:{chunks_done, rollback_id, backup_verified}`.
Reads/writes: `<root>/assay-run.json` only. Commands pass `Path('assets')`
(`commands/curate-assay-init.md:66`), so the live path is `assets/assay-run.json`.
The single-run rule is a **safety property, not tidiness**: primary keys on the write path are
`MAX(id)+1` in Python with no lock (`runstate.py:11-14`).

**`init_run.py`** — `TIERS = ("00-rulings","01-extract","02-agent-runs","03-stage0-applied",
"04-artifacts","05-review","06-findings","07-process")` (`:24-25`); `PROTECTED = TIERS[:-1]`
(`:26`), i.e. `07-process` stays writable.
Entry points: `require_store(store, backups)` (`:35`, raises `MissingRulingStore` (`:31`) unless
`<store>/pairs.tsv` exists), `next_run_number(runs_root)` (`:51`, one past the highest `RUN<n>`,
fresh tree → 1), `create_run(runs_root, run)` (`:62`, mkdirs all 8 tiers then `protect` the first 7 —
protection applied **at creation**, `:65-68`), `migrate_into_store(run_dir, assays, store)` (`:76`).
`migrate_into_store` **merges** with what the store already holds (`:93-105`) and **excludes**
conflicting keys rather than resolving them (`:80-85`); returns
`{written, store_total, store_before, conflicts, provenance}` (`:107-108`).

**`protect_run.py`** — `DIR_MODE = 0o555`, `FILE_MODE = 0o444` (`:21-22`).
`protect(run_dir, tiers)` (`:25`) → paths whose mode it actually changed; `verify(run_dir, tiers)`
(`:41`) → the tiers that are **not** protected (empty = all protected). Directories are chmodded,
not just files, because a writable dir accepts a *new* file beside a read-only baseline
(`:11-13`). Docstring records that four source files claimed `chmod a-w` and **no code applied it**
(`:6-9`).

### 1.2 Ruling store, backup, protection

| module | lines | CLI | purpose |
|---|---|---|---|
| `rulings.py` | 110 | no | the durable pair-keyed ruling store |
| `migrate_rulings.py` | 124 | no | RUN1's three ruling shapes → store rows |
| `ingest.py` | 72 | no | operator-edited CSV → rulings |
| `carryforward.py` | 59 | no | sort this run's cohorts against prior rulings |
| `store_backup.py` | 47 | no | dated, verified tarball of the store |
| `_writeguard.py` | 41 | no | refuse to write through a symlink |

**`rulings.py`** — `PAIRS_NAME = "pairs.tsv"` (`:43`);
`VERDICTS = ("APPROVE","REJECT","WRONG_ASSAY","UNSURE")` (`:44`);
`PairKey = tuple[str,str,str]` = `(sample_type, internal_assay_id, action)` (`:46`, `:17`).
`save(store, rulings)` (`:89`) writes `<store>/pairs.tsv` with columns
`sample_type, internal_assay_id, action, verdict, ruled_on, actor` (`:94-96`) and **rewrites the file
wholesale**; `load(store)` (`:101`) returns `{key: Ruling}`, absent store → `{}`.
`normalise_id(value)` (`:61`) strips a trailing `.0` — pandas int columns yield `74.0` and a key
that is sometimes `74` and sometimes `74.0` silently fails to match (`:64-68`).
`_collapse` (`:72`) raises `ValueError` on an unknown verdict and `ConflictingRulings` (`:49`) on one
key with two verdicts — never averaged (`:79-84`).
Why the key changed: RUN1 filed under `lab|sample_type|parent_types|assay_title|field|value`; four
of six fields move with the extract, so 261 rulings became worthless (`:7-13`). The measured cost of
the coarser key: 200 ruled rows → 127 keys, **5 conflicts** (`:19-23`), and the docstring explicitly
corrects an earlier circulated "156 / 114 / 3" figure (`:26-29`).
**Provenance is deliberately NOT stored here** — cohort strings carry lab codes and a protocol
filename containing a person's name, so they go to a gitignored sidecar (`:31-33`).

**`migrate_rulings.py`** — reads three RUN1 files by literal name:
`mode2-rulings-2026-08-20.tsv` (`:56`), `pair-rulings.tsv` (`:72`),
`mode1-rulings-COMPLETE.tsv` (`:87`). `title_index(assays)` (`:34`) raises `AmbiguousTitle` (`:30`)
if two internal assays share a display string. `migrate(run_dir, assays)` (`:49`) →
`(rulings, provenance records)`; `conflicts(rulings)` (`:105`).
`PAIR_VERDICT = {"OVERRIDE": "APPROVE", "CONFIRM_BLOCK": "REJECT"}` (`:27`).
130 of 175 pair rows were UNRULED and are **not** migrated — absence of a ruling is not a ruling
(`:14-15`).

**`ingest.py`** — `ingest(edited, cohorts, ruled_on, actor="operator")` (`:36`) →
`list[Ruling]` or raises `IngestRefused` (`:32`). Requires columns `cohort_key` (`:28`) and
`ruling` (`:29`). Refusals: missing column (`:39-44`), a key matching no cohort in this run
(`:53-57`), a verdict outside `VERDICTS` (`:58-61`), one cohort ruled two ways in the same file
(`:63-67`). A blank/`nan` ruling is **skipped, not defaulted** (`:51-52`); an exact duplicate is a
no-op (`:68-69`). Refusal is **whole-file** (`:18-20`). The cohort key is looked up in the map the
review surface emitted, never reconstructed (`:14-16`).

**`carryforward.py`** — `CARRIED = "already_ruled"`, `WIDENED = "ruled_in_a_narrower_context"`,
`UNSEEN = "never_seen"` (`:33-35`); `Cohort(key, n_rows, cohort_id)` (`:38-42`);
`split(cohorts, store, ruled_width)` (`:45`) → `{bucket: [Cohort]}`.
**Nothing derives `ruled_width` today** (`:18-24`): callers pass `{}`, every matched pair lands in
`WIDENED`, and *carry-forward carries nothing*. That is stated in the module and repeated verbatim
in the command (`commands/curate-assay-detect.md:68-73`). An unknown width counts as widened, not
carried (`:13-16`). The trap it exists for: in RUN1, 2,830 rows shared a cohort key with an approved
cohort but sat below the precedent floor the operator's sheet was built at (`:8-11`).

**`store_backup.py`** — `back_up(store, backups, stamp)` (`:27`) writes
`<backups>/rulings-<stamp>.tar.gz` with `arcname=store.name` (`:39`), then **reopens the archive
and asserts `pairs.tsv` is inside** (`:41-46`), raising `BackupUnverified` (`:23`). Refuses to back
up an absent store (`:30-34`). Motivation is a 2026-08-27 incident: a backup command exited 0 having
written a 0-byte file (`:6-8`). The stamp is a parameter, not read from the clock (`:12-13`).

**`_writeguard.py`** — `assert_writable(out, names)` (`:26`) raises `SymlinkWriteRefused` (`:22`) if
`out` itself is a symlink or if any of `names` under it is. Exists because `run_evidence.main` and
`run_detect.main` default `out_dir="assay-hygiene"`, which is **33 symlinks into `assets/RUN1/`**
(`:6-9`). Called at `run_evidence.py:888-892`, `run_detect.py:1087-1088`, `classify.py:1916-1917`.
Note the coverage is uneven: `gate.main` does **not** call it (`gate.py:944-945` mkdirs directly),
and `classify.main` guards only `("findings.csv",)` (`classify.py:1917`) while it also writes
`mode3-disposition.csv` (`classify.py:2077`).

### 1.3 Extraction and evidence

| module | lines | CLI | purpose |
|---|---|---|---|
| `extract.py` | 360 | `main()`, no `__main__` guard | Stage A read-only extract, runs in the container |
| `driver_extract.py` | 22 | pipeable | pipes `extract.main()` into `manage.py shell` |
| `vocabulary.py` | 511 | no | learn / merge / score the term→assay vocabulary |
| `claims.py` | 198 | no | Stage B2: what a sample's own metadata claims |
| `precedent.py` | 363 | yes | mine per-(project, hop, assay) precedent rates |
| `lineage.py` | 620 | yes | the DERIVED_FROM neighbour index + Mode 2 ceiling |
| `compatibility.py` | 710 | yes | co-registration rates and bands |
| `audit.py` | 221 | no | the increment-1 Mode 3 "contradiction" flags |
| `vocabulary_evidence.py` | 255 | yes | membership evidence for unresolved terms |
| `run_evidence.py` | 970 | yes | the whole evidence layer, one command |

**`extract.py`** — runs **inside the production `nextseek` container** under `manage.py shell`
(`:5-8`). Uses the Django alias `seek` (= `seek_production`); the `default` alias is `dmac`, whose
`assay_assets` table exists but is empty (`:10-11`). `main(outdir="/tmp/assay-hygiene-extract")`
(`:302`) opens a Neo4j driver in `try/finally` (`:321-329`), runs `CYPHER_EXTRACTS` and
`SQL_EXTRACTS`, builds `parents` by delegating to the **server's own** `collect_parent_tokens`
rather than reimplementing it (`:310`, `:339-342`, rationale `:13-18`), and writes each frame to
`<outdir>/<name>.parquet`, zstd (`:346-348`). Raises on duplicate node uuids **after** the writes,
deliberately, so the ~260 MB extract survives for diagnosis (`:350-360`). Deliberate deviation:
production's `UID_RE` is *not* applied here, because it discards ~8,131 two-letter `AB` references
(`:20-25`).
Other entry points: `count_line` (`:187`), `duplicate_uuids` (`:229`), `build_parents` (`:248`).
**Writes to a live server: no. Reads: yes — SQL SELECTs on `seek` and read-only Cypher.**

**`driver_extract.py`** — 22 lines, no logic: `sys.path.insert(0, "/tmp/scripts")` then
`extract.main()` (`:19-22`). Exists because `extract.py` uses a relative import that fails when
piped bare into the shell, and because ssh arg-joining destroys nested quoting (`:3-6`). Carries the
`scp` / `docker cp` / `ssh ... manage.py shell` recipe (`:8-12`).

**`vocabulary.py`** — `parse_metadata(samples)` (`:30`), `learn_vocabulary(edges, meta)` (`:81`),
`score_vocabulary` (`:122`), `merge_vocabulary(learned, proposed, curator, assays)` (`:187`),
`unresolved_terms(meta, vocab, uuids)` (`:341`), `save_vocabulary(df, path)` (`:415`),
`load_vocabulary(path)` (`:438`). Provenance precedence is `learned < proposed < curator`
(`_schema.py:588-590`, `:617`); `EVIDENCE_PROVENANCES = (P_LEARNED, P_CURATOR)`
(`_schema.py:618`) — a `proposed` row is excluded from tiering entirely.

**`claims.py`** — `claim_index(vocab)` (`:28`) keyed on `(field, normalised value)`,
`sample_claims(meta, uuids, vocab)` (`:70`). Tiers come from held-out measurement: strong fields
98.4% over 65.9% of the population, +Protocol/DataType → 92.3% coverage at 90.4%, agreement between
the two 99.9% (`:11-16`). "A claim is not a decision" (`:18-19`).
Field split lives in `_schema.py`: `STRONG_FIELDS = ["Type","Instrument","Stimulation","Software",...]`
(`:527`), `WEAK_FIELDS = ["Protocol","DataType"]` (`:529`); tiers
`T_CORROBORATED/T_STRONG/T_WEAK/T_CONFLICT/T_NONE` (`:532-544`).

**`precedent.py`** — `fallback_assay_ids(assays)` (`:40`), `assay_index(assays)` (`:67`),
`membership_index(membership)` (`:138`), `mine_precedent(edges, membership, assays)` (`:153`).
CLI: `main(extract_dir="assay-hygiene/extract", out_path="assay-hygiene/precedent.csv")` (`:333`) —
**the only module whose second positional arg is a file path, not a directory**. Writes
`precedent.csv`. `RULE_KEY = ["project_id","child_type","parent_type","internal_assay_id"]`
(`_schema.py:86`).

**`lineage.py`** — `lineage_index(edges, samples, membership)` (`:113`) →
`(children_of, parents_of, uuid_of, integrity)`; `lineage_supports` (`:357`),
`neighbour_registers` (`:415`), `mode2_ceiling(children_of, parents_of, registered)` (`:483`).
CLI `main(extract_dir=...)` (`:567`) — **reads four parquet files, writes nothing** (`:571-573`).
Binding rule: the lineage test runs over `DERIVED_FROM`, never `CHILD_OF`, because precedent is
mined over `DERIVED_FROM` — 52,185 edges apart, ~9% of every Mode 2 figure
(`_schema.py:806-809`).

**`compatibility.py`** — `co_registration(membership, assays, nodes)` (`:124`),
`compat_band(rate, support)` (`:236`), `band_establishes(band)` (`:285`),
`best_co_registration` (`:331`), `counter_evidence_census` (`:488`).
CLI `main(extract_dir, out_dir)` (`:608`) — read-only: three parquet files opened, **none written**
(`:612-613`). `out_dir` is used only by `_census` (`:659`) to *read* `claims.parquet` and
`vocabulary.csv`, and it prints a NOTE and returns when they are absent (`:670-676`).
Bands `BAND_NEVER/SOMETIMES/ROUTINE/NO_SUPPORT` (`_schema.py:820-824`);
`MIN_CO_REG_SUPPORT = 30`, `CO_OCCUR_BAND = 0.5` (`_schema.py:844-845`) — both are explicitly
**reporting bands, not gates**, with `compatibility.compat_band` named as the single approved reader
(`_schema.py:826-843`).

**`audit.py`** — `registered_internal(membership, assays)` (`:35`, crosses the seek→internal junction
and **raises** on a membership row naming an unknown assay, `:46-49`),
`audit_contradictions(claims, membership, assays, nodes, ...)` (`:88`).
"Writes nothing, ever" (`:7`). `DEFAULT_TIERS = (T_CORROBORATED, T_STRONG)` (`:32`); the three floors
`tiers`, `include_contested`, `include_unmappable` are parameters so widening is deliberate
(`:20-22`).

**`vocabulary_evidence.py`** — `registered_assays` (`:80`), `carriers` (`:119`),
`build_evidence` (`:138`), `summarise` (`:208`), `load_tail` (`:223`).
CLI `main(extract_dir, out_dir)` (`:234`): reads `samples/membership/assays/nodes.parquet` and
`<out>/vocabulary-unresolved.csv` (`:237-244`), writes `<out>/vocabulary-evidence.csv` (`:247`).
`vocabulary-evidence.csv` is a **working file, not a contract — nothing downstream reads it**
(`commands/curate-assay-vocabulary.md:298-299`).

**`run_evidence.py`** — the evidence-layer driver.
CLI `main(extract_dir="assay-hygiene/extract", out_dir="assay-hygiene")` (`:885`).
Guards with `_writeguard.assert_writable` over eight names (`:888-892`).
Reads `edges, membership, assays, samples, nodes` parquet from `extract_dir` (`:895-899`) plus
`<out>/vocabulary-proposed.csv` and `<out>/vocabulary-curator.csv` (`:905-906`).
Writes, in order: `vocabulary.csv` (`:908`), `vocabulary-unresolved.csv` (`:911`), `precedent.csv`
(`:914`), `claims.parquet` (`:917`), `mode3-contradictions.csv` (`:920`),
`mode3-contradictions-with-contested.csv` (`:932`), `mode3-review-patterns.csv` (`:950`),
`evidence-report.md` (`:963`). It also prices all four audit dial settings in the same run
(`:925-930`).
Non-obvious: it writes `mode3-review-patterns.csv` and both contradiction CSVs but does **not** list
them in its own `assert_writable` call, which names `vocabulary-defects.csv` and
`mode3-disposition.csv` instead — files written by `gate.main` and `classify.main`
(`:889-892` vs `:920`, `:932`, `:950`).

### 1.4 Gating

**`gate.py`** (1,017 lines, CLI). The vocabulary gate runs **before every mode**
(`_schema.py:724-729`).
Entry points: `sample_type_index(nodes)` (`:285`), `sample_type_sets(nodes)` (`:308`),
`untyped_registration_samples` (`:348`), `type_registration_index(membership, assays, nodes)`
(`:368`), `term_stem(value)` (`:452`), `term_families(vocabulary)` (`:526`),
`incoherent_families(vocabulary)` (`:546`), `blocks_mode(outcome)` (`:583`),
`reaches_modes(gated)` (`:601`), `gate_claims(claims, vocabulary, type_reg, types, min_samples,
min_purity)` (`:617`), `vocabulary_defects(gated, vocab, ...)` (`:790`).
Thresholds: `MIN_VOCAB_SAMPLES = 3` (`:145`), `MIN_VOCAB_PURITY = 0.75` (`:197`) — bound once in
`main` and handed to both `gate_claims` and `vocabulary_defects` so a claim's floor and the
curator file's stated floor cannot diverge (`:935-940`).
**Blocking rule, single definition:** `BLOCKING_OUTCOMES = (GATE_UNREACHABLE, GATE_INCOHERENT)`
(`:580`) — a *membership* test, not a `!= GATE_PASS` comparison (`:591-596`).
`GATE_LOW_SUPPORT` is **recorded on the row and does not block**, because it is the outcome of two
tuned floors and a threshold ranks rather than grants permission (`_schema.py:744-748`).
Re-deriving blocking from `GATE_REJECTIONS` instead of calling `blocks_mode` stops 22,147 of 130,764
claims where the rule stops 4,553 (`_schema.py:750-753`).
`reaches_modes` reads `gate_failures` (the complete set), never `gate` (most severe only)
(`:604-607`).
CLI `main(extract_dir, out_dir, min_samples, min_purity)` (`:925`): exits **2** naming
`run_evidence` if `claims.parquet` or `vocabulary.csv` is missing (`:947-954`); writes exactly one
file, `vocabulary-defects.csv` (`:968`), routed to `/curate-assay-vocabulary` and to no mode
(`:931-933`). `__main__` casts argv `(str,str,int,float)` and **checks arity before the zip**,
because `zip` silently discarded a fifth argument and made a typo'd invocation run at default floors
(`:997-1017`).

### 1.5 Detection modes

**`classify.py`** (2,088 lines, CLI) — Mode 1, the compatibility lane, the precedence, the unified
emitter, and the Mode 3 re-disposition.
Entry points: `project_index` (`:327`), `unregistered_samples` (`:377`),
`registered_samples_absent_from_samples` (`:406`), `attach_gate` (`:432`),
`mode1_findings(attached, population, projects, *, fallback_assay_ids)` (`:535`),
`mode1_census` (`:679`), `_registered_columns` (`:718`, shared with `mode2`), `Evidence` (`:820`),
`precedence_step` (`:930`), `absence_keys` (`:981`), `precedence_steps` (`:1073`),
`claims_agreeing_with_a_registration` (`:1078`), `compat_findings` (`:1198`),
`mode3_findings()` (`:1336`), `unify_findings(steps, lanes)` (`:1426`), `findings_census` (`:1611`),
`disposition_breakdown` (`:1752`), `mode3_disposition` (`:1797`), `main` (`:1873`).
`fallback_assay_ids` is required and keyword-only with **no default**, because an empty set is a
legal value and a default would silently report `internal` on every row (`:544-551`).

**`mode2.py`** (1,126 lines, no CLI) — split out of `classify.py`; `mode2` imports `classify` at
module level and `classify` imports `mode2` **lazily inside `main`** to break the cycle
(`mode2.py:16-23`, `classify.py:1911`).
Entry points: `Rule` (`:229`), `assay_titles(assays)` (`:261`), `assay_population` (`:282`),
`registration_projects` (`:347`), `precedent_rules(precedent)` (`:404`),
`mode2_candidates(children_of, parents_of, registered)` (`:466`), `mode2_findings(...)` (`:679`),
`mode2_census` (`:972`), `precedent_survival` (`:1047`).
`BOOTSTRAP_POPULATION_FLOOR = 100` (`:142`) — the cut through `CLS_UNREACHABLE`.
`SURVIVAL_THRESHOLDS = (0.0, 0.5, 0.75, 0.9, 0.95)` (`:149`) is **where `precedent_survival`
reports and nothing else**; `mode2_findings` never sees them (`:144-148`).

`PRECEDENCE` (`classify.py:788-795`), in order:
`PRE_GATE` → `PRE_MODE_1` → `PRE_LINEAGE` → `PRE_UNREACHABLE` → `PRE_COMPAT` → `PRE_MODE_3`.
Lanes wired in `main` (`classify.py:2031-2039`): `PRE_MODE_1 → findings`, `PRE_LINEAGE → m2`,
`PRE_UNREACHABLE → m2` (**the same frame**; `unify_findings` filters each lane by the step that owns
each key), `PRE_COMPAT → compat`, `PRE_MODE_3 → mode3_findings()` (empty).
`PRE_GATE` has **no lane** — a gate-refused key emits nothing (`classify.py:2048-2057`).

### 1.6 Review surfaces

| module | lines | CLI | writes |
|---|---|---|---|
| `review.py` | 1,012 | **no `main` — deliberate** | `mode1-review.html` |
| `review_mode2.py` | 753 | yes | `mode2-cohorts-to-review.csv`, `mode2-review.html` |
| `dossier.py` | 418 | yes | `mode2-dossiers.json` |
| `review_verdicts.py` | 296 | yes | `mode2-verdicts-review.csv/.html` |
| `validation_sample.py` | 1,510 | yes | four validation files |

**`review.py`** — the Mode 1 sheet. `REVIEW_NAME = "mode1-review.html"` (`:88`).
`load_context(extract_dir)` (`:248`) reads five parquet files (`:274-278`);
`build_blocks(findings, context)` (`:455`); `cohort_key(block)` (`:587`) — **the one definition of
the cohort key**, which the review command forbids duplicating
(`commands/curate-assay-review.md:14-18`); `render(blocks)` (`:902`);
`write_review(findings, context, out_dir)` (`:1000`).
**There is deliberately no `main`** (`:1003-1009`): one would need to read the findings frame back off
disk, which is exactly what made the review context and the findings artifact disagree about internal
assay 30 vs 31. `run_detect.main` holds the frame and passes it (`run_detect.py:1109`).
The page "detects and proposes, it does not adjudicate" — the ruling control is a `<select>` of
words that nothing in the package reads (`:14-19`).

**`review_mode2.py`** — `FLOOR = 0.50` (`:67`), `PRESET_NAME = "mode2-rulings.tsv"` (`:69`),
`CSV_NAME = "mode2-cohorts-to-review.csv"` (`:72`), `REVIEW_NAME = "mode2-review.html"` (`:73`).
`analysis_twins(assays)` (`:142`), `load_presets(path)` (`:182`), `check_presets` (`:229`),
`build_blocks(findings, context, floor)` (`:347`), `to_csv(blocks, presets)` (`:443`),
`render(...)` (`:623`), `main(artifacts="assay-hygiene", extract=None, floor=FLOOR,
expect_presets=0)` (`:701`).
`main` reads `<artifacts>/findings.csv` and `<extract>/assays.parquet`; **it raises unless
`kept + below_floor + no_rate == all Mode 2 rows`** — every row accounted for in exactly one bucket
(`:721-727`). Three buckets, never two: a null rate is not a low one.

**`dossier.py`** — `DOSSIER_NAME = "mode2-dossiers.json"` (`:77`).
`sibling_assays` (`:97`), `type_assay_counts` (`:122`), `seek_records` (`:151`),
`build_dossiers(findings, context, assays, membership, nodes)` (`:212`), `main` (`:395`).
Covers **the whole Mode 2 population, no floor** (`:409-410`) — the complement of
`review_mode2`'s floored sheet.

**`review_verdicts.py`** — `SHEET_NAME = "mode2-verdicts-review.html"` (`:45`),
`CSV_NAME = "mode2-verdicts-review.csv"` (`:46`), `VERDICT_GLOB = "full-*-verdicts.tsv"` (`:61`).
`load_verdicts(batch_dir, pattern)` (`:64`), `join_dossiers(verdicts, dossiers)` (`:98`),
`render(frame)` (`:228`), `main(artifacts, batches)` (`:278`) — reads
`<artifacts>/batches/full-*-verdicts.tsv` and `<artifacts>/mode2-dossiers.json`.
This is the agent-verdict roll-up from the 15-agent judging campaign.

**`validation_sample.py`** — `SEED` and the four output names:
`validation-sample.csv` (`:269`), `validation-sample.html` (`:270`),
`validation-sample-key.csv` (`:271`), `validation-sample-power.md` (`:272`).
`certainty_slice` (`:307`), `disagreement_slice` (`:340`), `draw(keys, n, seed, salt)` (`:373`),
`zero_event_bound(population, sample, alpha)` (`:399`), `kish_effective_n` (`:434`),
`power(...)` (`:449`), `agent_convergence` (`:545`), `strata` (`:632`), `cohort_facts` (`:760`),
`build_sample` (`:856`), `to_csv` (`:944`), `to_key` (`:996`), `power_report` (`:1025`),
`render` (`:1368`), `main(artifacts, extract, verdicts, out_dir, seed)` (`:1429`).
`out_dir` defaults to `artifacts` and its docstring says **it should not be left there** — a
default-path run on the symlink tree fails with `Permission denied` rather than destroying the
baseline, and that friction is deliberate (`:1433-1440`). The key file is explicitly *not for the
rater* (`:1483-1484`).

### 1.7 Resolution, registration and the production write path

| module | lines | CLI | purpose |
|---|---|---|---|
| `resolve_targets.py` | 98 | no | internal assay id → the SEEK assay of the sample's own project |
| `preflight.py` | 103 | no | the eight refusals |
| `chunker.py` | 49 | no | split the payload; reconcile each chunk against the DB |
| `registration_payload.py` | 144 | no | complete-list payload for the two *rejected* mechanisms |
| `stage0.py` | 792 | no | plan the DERIVED_FROM backfill |
| `stage0_apply.py` | 320 | no | the Neo4j write itself, driver duck-typed |
| `driver_stage0.py` | 52 | pipeable | binds the real Neo4j driver on the box |

**`resolve_targets.py`** — `TARGET_COLUMN = "write_target_seek_assay_id"` (`:29`).
Exclusion reasons: `NO_PROJECT = "sample belongs to no project"` (`:30`),
`NO_CANDIDATE = "no assay with that internal id in the sample's project"` (`:31`),
`AMBIGUOUS = "internal assay exists in more than one of the sample's projects"` (`:32`).
`resolve(rows, assays, samples)` (`:39`) → `(manifest, excluded)`; manifest columns
`sample_id, internal_assay_id, write_target_seek_assay_id, project_ok` (`:81-82`).
It collects **every** candidate, not the first — a `next()` over `project_ids` made an unrecoverable
write decided by list order (`:59-63`).
`assert_subset(sheet, manifest)` (`:88`) raises `CrossProjectTarget` (`:35`) unless every
`(sample_id, assay_id)` in the sheet is in the manifest.
Stakes: the 2026-08-26 audit found **578 of 26,188 rows** targeting another project's assay;
159 repairable, 419 not, and it is **unrecoverable once written** (`:9-13`).
Note: the module and the command name three exclusion reasons vs two —
`commands/curate-assay-resolve.md:41-47` documents only `NO_PROJECT` and `NO_CANDIDATE` and omits
`AMBIGUOUS`.

**`preflight.py`** — `CHUNK_CAP = 2000` (`:34`), `FORBIDDEN_SHEET = "UPDATE"` (`:35`).
`check(sheet, manifest, sheet_names, backup, rollback_id)` (`:47`) raises `PreflightRefused` (`:38`)
on the first applicable refusal; returns `None` when safe.
Expected sheet columns, read off the checks: `current_pair` (`:65`), `new_pair` (`:73`), `uid`
(`:81-82`), plus `sample_id` and `assay_id` via `assert_subset` (`resolve_targets.py:92`).
`backup` is a dict requiring truthy `size` and `trailer_ok` (`:99`).

**`chunker.py`** — `chunks(sheet, size=CHUNK_CAP)` (`:33`),
`reconcile(expected, before, after)` (`:38`) raising `ChunkMismatch` (`:29`).
Reconciliation is a **count query**, not the endpoint's response: `DBtable.storeOneRecord` sets
`status = 1` and never updates it from the DB call, so the feedback workbook prints `successful:`
for rows that never landed (`:13-16`). An **over-count is refused as well as an under-count** —
more rows than expected means another writer was active (`:18-20`). Measured throughput ~3.4
rows/second, so a 2,000-row chunk is roughly ten minutes (`:7-11`).

**`registration_payload.py`** — `Payloads(per_assay, per_sample, excluded)` (`:44-55`),
`build_payloads(registration, membership)` (`:70`),
`assert_no_membership_lost(per_assay, membership, touched_assays)` (`:103`),
`assert_no_assay_lost(per_sample, membership, touched_samples)` (`:131`).
It builds `existing UNION additions` because **both** candidate mechanisms are complete-list rather
than append — the NExtSEEK API `PATCH /nextseek_api/assays/{uid}/` (per assay) and batch upload's
`smart_merge_assay_assets` (per sample) — so anything absent from the payload is deleted
(`:12-16`). Containment is a separate property: only touched records appear (`:26-29`).
**"This module never talks to a database"** (`:31`).
*Both mechanisms it serves were rejected in favour of the `UPDATE_ASSAY` sheet*
(`commands/curate-assay-write.md:12-23`), which makes this module superseded — see §5.

**`stage0.py`** — `plan_edges(parents, nodes, existing)` (`:23`) → `(plan, residues)` with the
accounting identity `len(plan) + every drop reason == len(parents)` (`:35-42`);
drop reasons `D_NOT_UID/D_NO_NODE/D_SELF_LOOP/D_ALREADY_EXISTS` (`_schema.py:80-83`) plus
`duplicate_reference`, and `prod_regex_would_reject` which is **report-only and excluded from the
sum** (`:40-42`, `:50`). Also `resolve_properties` (`:181`), `reconcile_childof` (`:327`),
`build_report` (`:497`). No `main`. "Writes only Neo4j, never MySQL, and never deletes" (`:8-9`).

**`stage0_apply.py`** — the Neo4j write. `CHUNK_SIZE = 20_000` (`:39`), matching the server's own
default in `neo4j_sync.py:158` (`:37-38`).
`MERGE_CYPHER` (`:41-52`) — `MATCH` both nodes, `MERGE (c)-[r:DERIVED_FROM]->(p)`, `SET` seven
properties. **No removal clause.**
`ROLLBACK_CYPHER` (`:76-81`) — `MATCH ... DELETE r`, keyed on the pair alone.
`to_payload(resolved)` (`:184`), `apply_edges(driver, db_name, resolved, dry_run=True,
chunk_size)` (`:209`), `apply_manifest(driver, db_name, manifest_rows, chunk_size, progress)`
(`:237`), `rollback(driver, db_name, manifest_rows, chunk_size)` (`:275`).
Three properties hold **by construction**, each with a test (`:11-21`): it cannot delete (the only
removal path is `rollback`, targeting exactly the manifest's pairs); it cannot touch `CHILD_OF`
(operator ruling 2026-08-13, neither Cypher string names it); **a dry run is the default** —
`dry_run=False` is the only way to write, and a dry run still produces the full manifest.
`_check_chunk_size` (`:96`) rejects a non-positive chunk size, because `range(0, n, -1)` is empty and
would issue no query while returning a full manifest — indistinguishable from a successful run
(`:98-102`).
Recorded, unmitigated hazard (`:54-75`): if `batch_upload` creates a `DERIVED_FROM` for a *planned*
pair inside the extract→write window, the `MERGE` matches it, the unconditional `SET` overwrites all
seven properties with no record of the old values, and `rollback` then DELETEs an edge stage 0 never
created. **Rollback restores nothing in that case.** The mitigation is procedural only.
There is deliberately **no `driver_stage0_rollback.py`** — the undo is an explicit paste in the
`rollback` docstring (`:286-311`), indented at column 0 so a copied-with-indentation paste dies as an
`IndentationError` rather than running.
The `neo4j` import at `:300` and `:305` is **inside that docstring**, not executable — the module
itself duck-types the driver and is fully unit-testable with a fake (`:7-9`).

**`driver_stage0.py`** — 52 lines, **no logic** (`:3-7`). Reads `/tmp/stage0-manifest.jsonl`
(`:34`), builds the real driver from `settings.NEO4J_DATABASE` (`:41`), calls
`stage0_apply.apply_manifest` in a `try/finally` so a failed write cannot leave a bolt connection
open (`:42-50`). Carries **no undo path and no destructive vocabulary at all, by design**, and a test
asserts it stays that way (`:19-22`; asserted at
`tests/test_assay_hygiene_lineage.py:854`, `tests/test_assay_hygiene_backtest.py:831`,
`tests/test_assay_hygiene_review.py:759`).

### 1.8 Support / measurement

| module | lines | CLI | purpose |
|---|---|---|---|
| `_schema.py` | 1,147 | no | every closed vocabulary, column contract and the fixtures |
| `run_detect.py` | 1,124 | yes | the detection driver + operator report |
| `backtest.py` | 899 | yes | hold-out backtest of Mode 2 |
| `baseline.py` | 59 | yes | re-derive the pre-rework figures |

**`_schema.py`** — imported by 20 other modules in the package. Holds the column lists
(`EDGE_COLUMNS :35`, `ASSAY_COLUMNS :41`, `SAMPLE_COLUMNS :49`, `NODES_COLUMNS :61`,
`STAGE0_PLAN_COLUMNS :75`, `PRECEDENT_COLUMNS :115`, `FINDING_COLUMNS :446`, `RULE_COLUMNS :508`,
`CLAIM_COLUMNS :577`, `VOCAB_COLUMNS :629`, `AUDIT_COLUMNS :660`), every closed vocabulary, and
`make_fixture()` (`:848`) / `make_stage0_fixture()` (`:1067`).
`id_namespace(assay_id, fallback)` (`:475`) with `NS_INTERNAL`/`NS_SEEK_FALLBACK` (`:470-472`) —
the internal-vs-SEEK namespace guard. `normalise_value(v)` (`:669`).
Each family enumerates itself in a tuple so a consumer can *check* closure rather than restate it
(`:699-702`).

**`backtest.py`** — `Split` (`:251`), `Backtest` (`:264`), `sample_universe` (`:281`),
`split_by_sample(universe, fraction, seed)` (`:303`), `check_split` (`:342`),
`blind_membership` (`:391`), `restore_membership` (`:438`), `training_edges` (`:454`),
`held_out_truth` (`:485`), `band_of` (`:546`), `recovery_bands` (`:577`), `backtest(...)` (`:674`),
`main(extract_dir, fraction="0.2", seed="0")` (`:831`).
**Read-only, no file written** (`:834`). Files are named one at a time rather than looped, so every
file the module opens is greppable in its own source (`:848-851`).
"EMPTY is not 0.000"; every precision is a **lower bound**, because a curator's assay set is not
known to be complete (`:889-895`).

**`baseline.py`** — `BASELINE_KEYS` (`:19-25`), `measure(findings_csv, extract_dir)` (`:28`),
`main(findings_csv="assay-hygiene/findings.csv", extract_dir="assay-hygiene/extract")` (`:48`).
"NOT a test and NOT a contract" — a photograph of the output before the reachability rework, so a
`-99,449 rows` claim can be held to it (`:7-11`).

**`run_detect.py`** — see §3. `REPORT_NAME = "detect-report.md"` (`:72`),
`COHORTS_NAME = "cohorts-to-review.csv"` (`:77`),
`ARTIFACTS = ("vocabulary-defects.csv","findings.csv","mode3-disposition.csv",
"cohorts-to-review.csv","mode1-review.html","detect-report.md")` (`:79-80`).
`PATTERN_KEY = ["sample_type","proposed_internal_assay_id","raw_value"]` (`:89`) — the key carries
`raw_value` because under the coarser key the PAV `Blood` and `Necropsy` populations collapsed into
one row that described neither (`:82-88`).
`CLASS_GLOSS` (`:117`) is **asserted complete against `_schema.CLASSES`**: adding a sixth class
without a gloss fails at import. `CLS_UNREACHABLE` was added 2026-08-21 and every sentence grouping
on four classes went short by a whole population without looking wrong (`:106-116`).

---

## 2. Question 1 — the detection modes

`MODE_1`, `MODE_2`, `MODE_3` (`_schema.py:718-720`); `MODES` (`:721`);
**`EMITTED_MODES = (MODE_1, MODE_2)`** (`:722`).

### Mode 1 — the sample is registered in nothing
Detects: an **unregistered** sample (`classify.unregistered_samples`, `classify.py:377`) whose own
metadata makes a gated claim naming an assay. One row per (sample, proposed assay)
(`classify.mode1_findings`, `classify.py:535`).
Gated by: the vocabulary gate, whose passage is `gate.reaches_modes` read off `gate_failures`
(`classify.py:556-560`). A claim failing reachability or coherence reaches no row; a claim under one
of the two tuned floors reaches its row **carrying** `GATE_LOW_SUPPORT` (`classify.py:556-560`,
`gate.py:580`, `_schema.py:744-748`).
Emits rows: **yes**.

### Mode 2 — a lineage neighbour or a peer establishes the absence
Detects: a `DERIVED_FROM` neighbour registers an assay this sample lacks (`mode2.mode2_findings`,
`mode2.py:679`), with precedent on the hop giving the rate at which that gap is closed elsewhere.
Direction is `LIN_CHILD` → propose adding the PARENT, `LIN_PARENT` → propose adding the CHILD
(`_schema.py:810-812`).
Gated by: the same vocabulary gate; then the **precedence** (`classify.py:788-795`) — Mode 1 wins any
key both lanes offer (753 such keys on the real extract, `classify.py:1434-1437`); then the
reachability split, which routes a key whose `(type, assay)` pair the house has never made to
`PRE_UNREACHABLE` rather than `PRE_LINEAGE`.
Emits rows: **yes** — and it is by far the largest population.
The rows are **classified, never dropped**: 99,449 of 167,454 emitted MODE_2 rows read
`type_registrations == 0` and are classed `CLS_UNREACHABLE`, still emitted, still carrying
`GATE_UNREACHABLE`, because "a proposal that vanishes reads to a curator exactly like one that was
never generated" (`_schema.py:768-776`).
`CLS_BOOTSTRAP` is a **cut through** `CLS_UNREACHABLE`, not a sixth population: where the proposed
assay's own population is under `BOOTSTRAP_POPULATION_FLOOR = 100` (`mode2.py:142`, applied
`mode2.py:667`), the gap may be a new assay finding its feet rather than a type error. 8,971 of the
99,449 fall under it, over 116 (type, assay) pairs and 50 assays (`_schema.py:778-789`).

### Mode 3 — no detector exists
Detects: **nothing.** `mode3_findings()` (`classify.py:1336`) takes no argument and returns
`pd.DataFrame(columns=S.FINDING_COLUMNS)` (`:1420`) — an empty frame carrying the full contract.
Emits rows: **none.**
This is the single most important correction in the package and it is asserted repeatedly:
"NOT SMALL. UNDETECTED" (`classify.py:1339`); "REPORT MODE 3 AS UNDETECTED, NEVER AS SMALL. Its zero
is the absence of a detector, not a measurement that contradictions are rare"
(`run_detect.py:53-55`); the constant survives only so the report can *name* the mode in order to say
it found nothing (`_schema.py:711-717`).
Why: increment 1's detector tested `claimed_assay not in registered_assays`, which is an **absence**
test reported under a **contradiction's** name (`classify.py:1340-1342`). Re-disposed under the
precedence, all 866 of its flags land elsewhere: 43 gate rejects, 326 lineage absences, 247
routinely-coexisting pairs, 205 unresolved, 45 alternative labels — "the residue of the subtraction
is EMPTY" (`classify.py:1356-1358`).
The unbuilt candidates are named: registration-side reachability, cross-project registration, and a
removal lane which ships last because of the deletion hazard (`classify.py:1363-1367`).
`audit.audit_contradictions` (`audit.py:88`) still has a producer and still writes
`mode3-contradictions.csv` (`run_evidence.py:920`); `classify.mode3_disposition`
(`classify.py:1797`) re-disposes those flags into `mode3-disposition.csv` (`classify.py:2077`).

### Not modes, but lanes that emit
- `PRE_COMPAT` / `compat_findings` (`classify.py:1198`) — no neighbour, so the co-registration test
  rules. Emits rows carrying `CLS_ABSENCE_COMPAT` (`_schema.py:796`), stamped `MODE_2`.
- `PRE_GATE` (`classify.py:788`) has **no lane** — a gate-refused key emits nothing, ever.

### Gate outcomes, exactly
`GATE_PASS`, `GATE_UNREACHABLE` (this type is never in this assay), `GATE_INCOHERENT` (the term
family maps to 2+ assays), `GATE_LOW_SUPPORT` (under the support **or** purity floor)
(`_schema.py:730-733`). Blocking = `(GATE_UNREACHABLE, GATE_INCOHERENT)` only (`gate.py:580`).

---

## 3. Question 2 — on-disk layout

### 3.1 A run directory

Runs root is `assets/` (`commands/curate-assay-init.md:64-66`). Run directories are
`assets/RUN<n>/` with eight tiers created by `init_run.create_run` (`init_run.py:62-73`) from
`TIERS` (`init_run.py:24-25`):

```
assets/
  assay-run.json                 the run lockfile (runstate.LOCK_NAME, runstate.py:22)
  rulings/                       the DURABLE ruling store, OUTSIDE any run
    pairs.tsv                    rulings.PAIRS_NAME (rulings.py:43)
  RUN<n>/
    00-rulings/                  read-only from creation
    01-extract/                  read-only  -- the parquet extract
    02-agent-runs/               read-only
    03-stage0-applied/           read-only
    04-artifacts/                read-only  -- everything the drivers write
    05-review/                   read-only
    06-findings/                 read-only
    07-process/                  WRITABLE   -- PROTECTED = TIERS[:-1] (init_run.py:26)
```

Tiers `00`–`06` are chmodded `0o555` (dirs) / `0o444` (files) **at creation**, not at the end of a
run (`init_run.py:65-68`, `protect_run.py:21-22`).

`01-extract/` holds the parquet files `extract.main` wrote (`extract.py:346-347`), read by name
throughout: `assays.parquet`, `membership.parquet`, `samples.parquet`, `nodes.parquet`,
`edges.parquet` (e.g. `classify.py:1928-1932`), plus `parents.parquet` and `sops.parquet`
(`extract.py:339`; `_schema.SOP_COLUMNS :54`).

`04-artifacts/` is the `out_dir` for every driver. Files written there, with the module that writes
each:

| file | written by |
|---|---|
| `vocabulary.csv` | `run_evidence.py:908` |
| `vocabulary-unresolved.csv` | `run_evidence.py:911` |
| `precedent.csv` | `run_evidence.py:914`, `precedent.py:342` |
| `claims.parquet` | `run_evidence.py:917` |
| `mode3-contradictions.csv` | `run_evidence.py:920` |
| `mode3-contradictions-with-contested.csv` | `run_evidence.py:932` |
| `mode3-review-patterns.csv` | `run_evidence.py:950` |
| `evidence-report.md` | `run_evidence.py:963` |
| `vocabulary-defects.csv` | `gate.py:968` |
| `findings.csv` | `classify.py:2076` |
| `mode3-disposition.csv` | `classify.py:2077` |
| `cohorts-to-review.csv` | `run_detect.py:1103` |
| `mode1-review.html` | `run_detect.py:1109` → `review.py:1011` |
| `detect-report.md` | `run_detect.py:1113` |
| `vocabulary-evidence.csv` | `vocabulary_evidence.py:247` |
| `mode2-cohorts-to-review.csv`, `mode2-review.html` | `review_mode2.py:730-731` |
| `mode2-dossiers.json` | `dossier.py:404` |
| `mode2-verdicts-review.csv/.html` | `review_verdicts.py:284-285` |
| `validation-sample.csv/.html`, `validation-sample-key.csv`, `validation-sample-power.md` | `validation_sample.py:1463-1466` |

Read but never written by the package (operator/agent inputs):
`vocabulary-proposed.csv` (`run_evidence.py:905`), `vocabulary-curator.csv`
(`run_evidence.py:906`), `mode2-rulings.tsv` (`review_mode2.py:69`, `:727`),
`batches/full-*-verdicts.tsv` (`review_verdicts.py:61`, `:280-282`),
`approved-rows.csv` and the manifest/exclusion CSVs the resolve command writes by hand
(`commands/curate-assay-resolve.md:19-22`).

**Default paths are a hazard, not a convenience.** `run_evidence.main` and `run_detect.main` both
default `out_dir="assay-hygiene"` (`run_evidence.py:886`, `run_detect.py:1072`), and that directory
is 33 symlinks into `assets/RUN1/` — 27 of 33 artifacts reachable through them
(`_writeguard.py:6-9`, `commands/curate-assay-detect.md:9-13`).

### 3.2 The ruling store

`assets/rulings/pairs.tsv` — one file, tab-separated, columns
`sample_type, internal_assay_id, action, verdict, ruled_on, actor` (`rulings.py:94-96`), sorted by
key (`:96`). `save` **rewrites it wholesale**, so a caller must pass the existing rulings alongside
the new ones (`rulings.py:89-98`; stated at `commands/curate-assay-review.md:43-44`).
It sits **outside any run** (`skills/curation/ASSAY.md:15`), because judgement outlives the run that
made it.
Backups: `~/backups/rulings-<stamp>.tar.gz`, archived with `arcname=store.name` so it restores to
`assets/rulings/` with no further moving (`store_backup.py:39`,
`commands/curate-assay-backup.md:29-34`).
Everything under `assets/` is gitignored, so a tarball outside the working tree is the store's only
protection — `git clean -xdf` lists `assets/` for removal
(`commands/curate-assay-review.md:46-48`).

---

## 4. Question 3 — the end-to-end pipeline order

```
0. EXTRACT (on the box, in the nextseek container)
   driver_extract.py  ->  extract.main()                extract.py:302
   writes samples/membership/assays/nodes/edges/parents/sops.parquet   extract.py:346-347
   copied down to  <RUN>/01-extract/

   (optional, one-time) STAGE 0 lineage backfill:
   stage0.plan_edges            stage0.py:23     plan on the laptop
   stage0_apply.apply_edges     stage0_apply.py:209   dry_run=True default -> manifest
   driver_stage0.py -> stage0_apply.apply_manifest  stage0_apply.py:237   WRITES Neo4j
   undo: stage0_apply.rollback  stage0_apply.py:275   (explicit paste only)

1. INIT                                    /curate-assay-init
   init_run.require_store        init_run.py:35    refuse unless pairs.tsv exists
   (first run only) init_run.migrate_into_store   init_run.py:76
   init_run.next_run_number      init_run.py:51
   init_run.create_run           init_run.py:62    mkdir 8 tiers, protect 00-06
   runstate.create               runstate.py:49    step="init"; refuses a second open run

2. EVIDENCE                                /curate-assay-detect (first half)
   run_evidence.main             run_evidence.py:885
     vocabulary.learn/merge/save vocabulary.py:81,187,415  -> vocabulary.csv
     vocabulary.unresolved_terms vocabulary.py:341         -> vocabulary-unresolved.csv
     precedent.mine_precedent    precedent.py:153          -> precedent.csv
     claims.sample_claims        claims.py:70              -> claims.parquet
     audit.audit_contradictions  audit.py:88               -> mode3-contradictions*.csv
                                                           -> mode3-review-patterns.csv
                                                           -> evidence-report.md

2b. VOCABULARY (operator/agent judgement)  /curate-assay-vocabulary
   vocabulary_evidence.main      vocabulary_evidence.py:234 -> vocabulary-evidence.csv
   agent writes vocabulary-proposed.csv ; curator writes vocabulary-curator.csv
   re-run run_evidence to merge them              run_evidence.py:905-908

3. DETECT                                  /curate-assay-detect (second half)
   run_detect.main               run_detect.py:1071
     _writeguard.assert_writable run_detect.py:1088
     gate.main                   gate.py:925   -> vocabulary-defects.csv (exit 2 if inputs missing)
     classify.main               classify.py:1873
        gate.gate_claims         gate.py:617
        classify.attach_gate     classify.py:432
        classify.mode1_findings  classify.py:535
        mode2.mode2_findings     mode2.py:679
        classify.compat_findings classify.py:1198
        classify.mode3_findings  classify.py:1336   (returns an EMPTY frame)
        classify.absence_keys / precedence_steps / unify_findings
                                 classify.py:981, :1073, :1426
        classify.mode3_disposition classify.py:1797
                                 -> findings.csv, mode3-disposition.csv
     run_detect.cohort_table     run_detect.py:480  -> cohorts-to-review.csv
     review.write_review         review.py:1000     -> mode1-review.html
     run_detect.build_report     run_detect.py:555  -> detect-report.md
   protect_run.protect / verify  protect_run.py:25, :41   re-protect 04-artifacts

3b. CARRY-FORWARD SPLIT
   rulings.load                  rulings.py:101
   carryforward.split            carryforward.py:45   (widths == {} today -> carries nothing)
   runstate.update(step="detect", carried_pairs=..., carried_from_run=...)  runstate.py:72

4. REVIEW                                  /curate-assay-review
   review_mode2.build_blocks / to_csv / render   review_mode2.py:347, :443, :623
   review.cohort_key             review.py:587   the ONE cohort-key definition
   (whole-population variants: dossier.main :395 ; review_verdicts.main :278 ;
    validation_sample.main :1429)
   ingest.ingest                 ingest.py:36    operator CSV -> [Ruling]
   rulings.save                  rulings.py:89   existing + new, whole-file rewrite
   store_backup.back_up          store_backup.py:27   backup is PART of ingest

5. RESOLVE                                 /curate-assay-resolve
   resolve_targets.resolve       resolve_targets.py:39  -> MANIFEST.csv, EXCLUDED.csv

6. WRITE                                   /curate-assay-write
   capture rollback handle: SELECT MAX(id) FROM seek_production.assay_assets
   runstate.update(write={"rollback_id": n})            runstate.py:72
   verify the mysqldump: non-zero size AND a "Dump completed" trailer
   preflight.check               preflight.py:47   all eight refusals, before any row
   chunker.chunks                chunker.py:33     2,000 rows per submission
   <<< OPERATOR posts the UPDATE_ASSAY sheet to /seek/sampleupload/ BY HAND >>>
   SELECT COUNT(*) ... WHERE id > handle
   chunker.reconcile             chunker.py:38     per chunk, refusing over- and under-count
   runstate.close                runstate.py:93
```

`run_detect` does **not** call `run_evidence`; both are needed, in that order, and
`gate`/`classify` exit 2 naming what to run first rather than raising `FileNotFoundError`
(`gate.py:947-954`, `classify.py:1919-1926`, `commands/curate-assay-detect.md:25-28`).
`run_detect` **delegates** rather than re-assembling the lanes, because a second assembly is a second
definition of the run and `unify_findings` was verified to silently drop a whole mode when a lane key
is omitted — 8 rows became 4 with no raise (`run_detect.py:13-30`).
The report is built by reading `findings.csv` back off disk, so the counts in the prose and the
counts in the artifact cannot drift (`run_detect.py:1098-1100`, `:1081-1085`).

**Step 6 has no code.** Nothing in `scripts/assay_hygiene/` builds the `UPDATE_ASSAY` workbook and
nothing submits it — see §5.

---

## 5. Question 4 — the safety refusals on the production write path

### 5.1 The eight preflight refusals — `preflight.check`, `preflight.py:47-103`

Checked in **source order** (the docstring numbers them differently, `preflight.py:9-22`; the code
raises on the first that applies, `:23-24`). All eight are independent; none is a subset of another.

| # (code order) | condition | line | why |
|---|---|---|---|
| 1 | any sheet in the workbook is named `UPDATE` | `:52-56` | hijacks dispatch into the metadata-update path, which is tested first (`seek/dbtable_sample.py:1663`) and would rewrite sample metadata |
| 2 | `len(sheet) > 2000` | `:58-62` | gunicorn SIGKILLs at 1200s and this path has **no transaction**, so an over-long submission leaves a committed prefix nobody can bound |
| 3 | any `current_pair` parses as two ints | `:64-70` | the **sole** combination reaching `deleteOneRecord` (`seek/dbtable_assay_assets.py:171`); every Current column must be blank so `id` stays `-1` |
| 4 | any `new_pair` does **not** parse as two ints | `:72-78` | the endpoint drops those registrations silently and still reports success |
| 5 | any `uid` is blank or not a `str` | `:80-87` | `getSampleID` returns `None`, `None > 0` raises, the run 500s mid-chunk leaving a committed prefix |
| 6 | any `(sample_id, assay_id)` absent from the gate-checked manifest | `:89-92` via `resolve_targets.assert_subset:88` | a row not in the manifest was never project-checked; cross-project writes are **unrecoverable** |
| 7 | `rollback_id is None` | `:94-97` | `MAX(id)` was never captured and the run cannot be undone |
| 8 | `not backup["size"] or not backup["trailer_ok"]` | `:99-103` | an unverified backup is not a backup — a `mysqldump` exited 0 having written 0 bytes on 2026-08-27 |

`_pair_is_two_ints` (`:42-44`) splits on `:` and requires exactly two all-digit parts.

### 5.2 Refusals outside preflight, on the same path

- **`chunker.reconcile`** (`chunker.py:38-49`) raises `ChunkMismatch` when the database delta is not
  exactly the rows submitted — **in both directions**. Fewer means rows failed while the endpoint
  reported success; more means another writer was active and this run's rows may have been
  overwritten (`:44-48`). The database is the receipt; the endpoint's response is a hint
  (`:13-16`).
- **`resolve_targets.resolve`** (`resolve_targets.py:39`) excludes rather than guesses: no project
  (`:54-58`), no candidate assay in the sample's project (`:66-70`), and **ambiguity across two of
  the sample's projects** (`:71-75`) — added because `next()` over `project_ids` made an
  unrecoverable write decided by list order (`:59-63`).
- **`runstate.create`** (`runstate.py:49-56`) refuses while another run is open, because two
  concurrent write phases can silently overwrite each other's rows under `MAX(id)+1` with no lock
  (`:11-14`).
- **`init_run.require_store`** (`init_run.py:35-48`) refuses to open a run at all when the ruling
  store is missing — nothing regenerates a human ruling.
- **`store_backup.back_up`** (`store_backup.py:41-46`) refuses to return a path anyone treats as a
  recovery point unless the archive it just wrote actually contains `pairs.tsv`.
- **`rulings.save` / `_collapse`** (`rulings.py:72-98`) refuses an unknown verdict and refuses a
  conflicting key. A conflict is escalated to the operator, never averaged (`:22-24`).
- **`ingest.ingest`** (`ingest.py:36-71`) refuses the **whole file** on an unmatched key, a bad
  verdict, or an internal contradiction.
- **`_writeguard.assert_writable`** (`_writeguard.py:26-40`) refuses to write through a symlink into
  a preserved run. Raises rather than warns, because the caller's next act is a write
  (`:13-15`).
- **`registration_payload.assert_no_membership_lost` / `assert_no_assay_lost`**
  (`registration_payload.py:103`, `:131`) refuse a payload that would delete an existing membership
  nobody ruled on. These guard the two mechanisms the write command rejected, so they are not on the
  live path today.

### 5.3 Structural properties, not runtime checks

- The chosen mechanism is **structurally incapable of deleting**: an `UPDATE_ASSAY` sheet with both
  Current columns blank makes the pair unparseable, `id = -1`, and the delete branch behind `if id>0`
  unreachable (`commands/curate-assay-write.md:12-16`).
- Measured against the alternatives for the same 25,769 rows: the API route put 202,016 existing
  memberships at risk, batch-upload 25,912, this route **zero**
  (`commands/curate-assay-write.md:20-23`).
- Undo for the whole run is one statement:
  `DELETE FROM seek_production.assay_assets WHERE id > <handle>` — no FKs, no triggers, monotonic id
  (`commands/curate-assay-write.md:38-40`).
- Idempotency is **application-level, not a database constraint**: there is no UNIQUE index on
  `(assay_id, asset_id, asset_type)`; `storeOneRecord` reads before writing via
  `__verifyUniqueConstraint` (`commands/curate-assay-write.md:28-30`).
- Stage 0's write path holds three properties by construction with tests attached: it cannot delete,
  it cannot touch `CHILD_OF`, and **a dry run is the default** (`stage0_apply.py:11-21`).

### 5.4 The gap

**No module in `scripts/assay_hygiene/` builds the `UPDATE_ASSAY` sheet, and no module submits it.**
Grep for `UPDATE_ASSAY`, `current_pair` or `new_pair` across `scripts/`, `commands/` and `skills/`
returns exactly two producers: `preflight.py`, which *validates* those columns
(`preflight.py:35`, `:65`, `:73`), and `commands/curate-assay-write.md:12`, which *describes* the
mechanism in prose. There is no HTTP client anywhere in the package.
So the eight refusals are a **library the operator must remember to call** between building the
workbook by hand and posting it by hand. Nothing enforces that `preflight.check` ran before the
submission, and nothing enforces that `chunker.reconcile` ran after it.

---

## 6. Question 5 — dead, superseded and unreferenced modules

Method: for each module, count in-package imports (`from .X import`, `from . import X`), test
imports (`assay_hygiene.X`), and command/skill references, excluding the module's own file.

### Unreferenced by anything — dead
- **`review_verdicts.py`** (296 lines) — **0 in-package imports, 0 test files, 0 commands.** The only
  mentions anywhere in the repo are two rows in
  `docs/findings/2026-08-25-the-prose-figure-census.md:125` and `:223`, citing its docstring figures
  as unverified. It reads `<artifacts>/batches/full-*-verdicts.tsv` (`:61`) — the output of the
  15-agent judging campaign, which was a one-off campaign, not a repeatable stage. It is the only
  module in the package with no test file at all.

### Referenced by tests only — no command, no in-package caller
These run, and are pinned, but are not part of any documented workflow:
- **`backtest.py`** (899) — `tests/test_assay_hygiene_backtest.py` only. Measurement tooling.
- **`baseline.py`** (59) — `tests/test_assay_hygiene_baseline.py` only. Explicitly "not a test and
  not a contract" (`:7`), a photograph of the pre-rework output.
- **`dossier.py`** (418) — `tests/test_assay_hygiene_dossier.py` only.
- **`validation_sample.py`** (1,510) — `tests/test_assay_hygiene_validation_sample.py` only. The
  largest module in this group; the statistical-power apparatus for the agent-judging campaign.
- **`registration_payload.py`** (144) — `tests/test_assay_hygiene_registration_payload.py` only, and
  **superseded**: it builds complete-list payloads for the NExtSEEK API `PATCH` route and for batch
  upload (`:12-14`), and the write command rejected both in favour of the `UPDATE_ASSAY` sheet after
  measuring that they put 202,016 and 25,912 existing memberships at risk respectively
  (`commands/curate-assay-write.md:20-23`).
- **`stage0.py`** (792) — `tests/test_assay_hygiene_stage0.py` only. The stage-0 planner; no command
  drives it, and stage 0 is a one-time backfill.

### Not imported, but not dead — invoked by piping, and test-guarded
- **`driver_extract.py`** — never imported; run by piping into `manage.py shell`
  (`driver_extract.py:8-12`). Its path is asserted in `tests/test_assay_hygiene_extract.py:649`.
- **`driver_stage0.py`** — same shape (`driver_stage0.py:9-15`); path asserted in
  `tests/test_assay_hygiene_stage0_apply.py:28`, and three separate tests assert that *other*
  modules do not name it
  (`tests/test_assay_hygiene_lineage.py:854`, `tests/test_assay_hygiene_backtest.py:831`,
  `tests/test_assay_hygiene_review.py:759`).

### Live and load-bearing
Everything else. Highest in-package fan-in: `_schema.py` (20 importers), `gate.py` (10),
`precedent.py` (9), `review.py` (7), `audit.py` (6), `rulings.py` (6), `vocabulary.py` (5),
`lineage.py` (5).

### Superseded *within* a live module
- `_schema.py:706-709` records that the `V_*` per-edge verdict vocabulary (`V_CLEAN`,
  `V_MODE1_CHILD`, `V_MODE1_PARENT`, `V_MODE1_BOTH_DARK`, `V_MODE2_PROPAGATE`, `V_MODE2_AMBIGUOUS`,
  `V_MODE3_FLAG`, `_schema.py:683-689`) belongs to a **superseded stage C**, and that
  **only `V_MODE3_FLAG` still has a producer, in `audit.py`**.
- `classify.mode3_findings` (`classify.py:1336`) is a live function that is a deliberate stub. It is
  not dead — the report must name the mode in order to say it found nothing
  (`_schema.py:715-717`).

---

## 7. Discrepancies found while inventorying

Recorded as facts about the tree, for whoever applies fixes.

1. **`skills/curation/SKILL.md` frontmatter still describes four modes.** Line 3 lists
   "pipeline ... fdh ... schema ... report" and omits `assay`, while the mode table at
   `skills/curation/SKILL.md:34` lists `assay` with all eight commands and `ASSAY.md`. The
   surrounding prose at `SKILL.md:41` still reads "it is one mode among four".
2. **`skills/curation/SKILL.md:145` routes `/curate-assay-vocabulary` to `schema` mode**, calling it
   "the assay-hygiene stage B2 judgment step". Commit `64f233d` absorbed that command into the
   `assay` mode and `SKILL.md:34` lists it there; line 145 was not updated.
3. **`commands/curate-assay-resolve.md:41-47` documents two exclusion reasons, not three.** It omits
   `resolve_targets.AMBIGUOUS` (`resolve_targets.py:32`), which is a live exclusion path
   (`:71-75`).
4. **`run_evidence.main`'s `assert_writable` list does not match what it writes.** It guards
   `vocabulary-defects.csv` and `mode3-disposition.csv` (`run_evidence.py:891`), which `gate.main`
   and `classify.main` write; it does **not** guard `mode3-contradictions.csv`,
   `mode3-contradictions-with-contested.csv` or `mode3-review-patterns.csv`, which it does write
   (`:920`, `:932`, `:950`).
5. **`classify.main` guards only `findings.csv`** (`classify.py:1917`) while also writing
   `mode3-disposition.csv` (`:2077`). **`gate.main` calls no write guard at all** — it mkdirs and
   writes `vocabulary-defects.csv` directly (`gate.py:944-945`, `:968`).
6. **`precedent.main`'s second argument is a file path, not a directory** (`precedent.py:334`),
   unlike every other CLI in the package, whose second positional is `out_dir`.
7. **`compatibility.main` takes an `out_dir` but writes nothing** — the parameter is used only by
   `_census` to *read* `claims.parquet` and `vocabulary.csv` (`compatibility.py:670-679`).
8. **`extract.py` has a `main()` but no `if __name__ == "__main__"` guard** — it is reachable only
   through `driver_extract.py:22`.
9. **`carryforward` carries nothing today.** Both the module (`carryforward.py:18-24`) and the
   command (`commands/curate-assay-detect.md:68-73`) say so explicitly, and the command's own code
   block hard-codes `widths = {}`. Any doc describing a working carry-forward is describing an
   unbuilt feature.
