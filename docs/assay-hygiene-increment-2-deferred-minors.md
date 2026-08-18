# Increment 2: deferred minors and cross-task carries

Extracted 2026-08-18 from the SDD ledger at
`.superpowers/sdd/2026-08-17-assay-hygiene-mode-1-and-2-detection/progress.md`,
WHICH IS GITIGNORED AND DIES WITH THE WORKTREE. The commit messages carry most
of this branch's rulings; this list survived nowhere else, so it is committed
here before the workspace is torn down.

Every item below was found by a review, judged real, and deliberately NOT fixed
in the task that found it -- because fixing it would have widened a task past
its brief. None is a correctness defect in shipped output; they are test
vacuity, stale prose, naming collisions and unpinned figures. THE FINAL
WHOLE-BRANCH REVIEW IS POINTED AT THIS LIST.

**52 deferred minors. 16 cross-task carries.**

**Status 2026-08-18:** 11 closed by the final review (marked `[x]` with the
commit that closed them). Four were already closed by later tasks and the
ledger never recorded it -- which is itself the argument for extracting this
list rather than trusting the ledger's open/closed state.

## Deferred minors

### Task 1

- [ ] (deferred; ledger:80) per-index pairing loop at test_..._schema.py:227-236 is self-fulfilling; only the length check is load-bearing. Real producer does not exist yet; audit.py:195-196 already ships the ";" join and nothing asserts a title contains no ";".
- [ ] (deferred; ledger:83) test_..._schema.py:823 hardcodes comet = 11 where siblings derive it via _internal().
- [ ] (deferred; ledger:84) grain-change rationale restated in 3 places; restatements drift.
- [ ] (deferred; ledger:85) _string_constants closure compares sets, so two constants in one family sharing a value pass. One-line fix: len(family) == len(set(family.values())).
- [ ] (deferred, new; ledger:93) the Finding-2 reader scan at test_..._schema.py:718-724 passes vacuously if the package path does not resolve (glob on a missing dir yields empty); a module-level import would fail first today, so not silently wrong now. One-line fix: assert (package/"_schema.py").exists().
- [ ] (deferred, new; ledger:96) that same glob("*.py") is non-recursive and skips _schema.py, so a gating comparison inside the declaring module or a future subpackage would not be seen.
- [ ] (deferred, new; ledger:98) test_assay_hygiene_claims.py _fixture_claims() has no pin on its own output row count; now guarded upstream by the samples count pin.

### Task 2

- [ ] (deferred; ledger:134) acceptance test's by_type dict keeps only the last row per type, so per-type assertions check 1 row not 11/13; inert today (populations uniform), blocking assert covers all 24.
- [ ] (deferred; ledger:136) test_reachability_is_evaluated_before... docstring claims 3 failures, asserts only `gate`; gate_failures now makes the full claim one line.
- [x] (deferred, LATENT CRASH, carry to Task 8; ledger:138) three near-copies of the vocabulary index at gate.py:567-571, :706-710, :424 with DISAGREEING null policies — term_families skips null internal_assay_id, the other two do not, so such a row reaching int() at :732 raises ValueError. Unreachable today; the asymmetry is the bug. One _vocab_index() helper with one null policy.
      **RESOLVED 2026-08-18 (7b84d39): one declared policy, `gate._maps_an_assay`, used by all three sites. Csvs byte-identical, so behaviour-preserving on real data (0 of 736 rows carry a null).**
- [ ] (deferred; ledger:142) defect sort documented as total but omits internal_assay_id under unstable quicksort; 0 ties on today's 202 rows.
- [ ] (deferred; ledger:144) GATE_UNREACHABLE rows key internal_assay_id off the claim and title off the vocab row; agree today, would name a different assay if they diverged.
- [ ] (deferred; ledger:146) `blocks_modes` (column) vs `blocks_mode` (function) differ by one character.
- [ ] (deferred; ledger:147) test_a_curator_row_is_never_gated_out_by_the_floors... name now vacuous post-ruling-A.
- [x] (deferred, new; ledger:154) gate.py:876-878 zip(_casts,_argv) truncates, so a 5th CLI arg is now silently discarded where main(*sys.argv[1:]) previously raised TypeError.
      **RESOLVED 2026-08-18 (7b84d39): arity checked before the zip; a 5th argument now exits with a named error instead of being discarded.**
- [ ] (deferred, new; ledger:156) gate.py:63-64 module docstring usage block still shows the bare no-arg invocation; the two new CLI positionals are documented only in main's docstring.

### Task 3

- [ ] (deferred; ledger:200) dup_uuid_rows always equals len(dup_uuid_samples), breaking the module's own stated _rows-vs-sample-list unit convention; and the headline "14 uuids" is in no integrity key.
- [ ] (deferred; ledger:202) report §5 GREEN block stale — shows 20 passed, file has 22. Reviewer ran it: 22 passed, no warnings. Code fine, filed evidence does not match shipped code.
- [ ] (deferred; ledger:204) 3 extract-backed tests re-read 3 parquet files each, 8.0s of the file's 8.24s.
- [ ] (deferred; ledger:205) tests/...:552 raises bare KeyError where every sibling degrades to a named skip.
- [ ] (deferred; ledger:206) LIN_NONE's two-state meaning documented in lineage.py:325-331 but _schema.py:456 declares it bare while both siblings carry comments; _schema.py is where a consumer looks.
- [ ] (deferred; ledger:208) int(raw_child) at lineage.py:205 raises ValueError on a null endpoint, untested, 0 nulls today, fails loud which is the house preference.
- [ ] (deferred; ledger:266) lineage.py:324 uses dict(zip()) over samples, the pattern the docstring two paragraphs above condemns; safe only because samples.sample_id is unique (163,393/163,393, measured), which nothing asserts, and the new extract test rebuilds `own` identically so it would drift the same way and could not catch the drift.
- [ ] (deferred; ledger:270) seen_uuids stores str(child_uuid) while own_uuid stores samples.uuid raw; a null or non-string in samples.uuid would silently disable the preference and revert every ambiguous id to min(), the rule this round overturned. 0 nulls today.
- [ ] (deferred; ledger:273) test P's guard at tests:390 asserts over hard-coded literals, not read off the frame, so editing the fixture leaves it green and vacuous.
- [ ] (deferred, growing; ledger:275) _extract() still uncached, now 4 passes over 794,593 rows, 12.5s -> 17.9s.
- [ ] (deferred, new; ledger:288) test F's guard reads the whole edges.child_uuid column while the rule's min is over seen_uuids[5]; they coincide only because all 3 rows carry child_id==5. Test P's sibling guard uses the faithful .loc filter. Cosmetic.

### Task 4

- [ ] (deferred; ledger:351) two tautological schema assertions at :154/:162 (the real catch is the .index() ValueError at :143).
- [ ] (deferred; ledger:353) fix report cites the wrong covering test for the winner column's emptiness; the property is actually pinned at compatibility:529 and :486.
- [ ] (deferred; ledger:355) band guard evadable — a bare `from ._schema import MIN_CO_REG_SUPPORT` adds 0 to both whole-file counts and passes. Natural spelling is caught.
- [ ] (deferred; ledger:357) BAND_ESTABLISHES exercised for 1 of 4 keys, no closure assertion, ValueError branch untested — though an unmapped band raises rather than returning None.
- [ ] (deferred; ledger:359) no read-only parquet/import guard for compatibility.py where lineage.py has one.
- [ ] (deferred; ledger:360) documented tie-break (larger support, then lowest id) is untested; world B has no tie.
- [ ] (deferred; ledger:361) mode2_ceiling includes some of Mode 1's 6,242 unregistered samples (fixture 300 supplies 2 of 7 ADD_CHILD rows); ruled in the docstring but absent from the printed output and the corrected plan block. Bounded at <=6% of ADD_CHILD samples.
- [x] (deferred, CARRY TO A LATER TASK; ledger:364) measure_absence_vs_contradiction.py is a SECOND implementation of this rule that disagrees — bands on `>` where compat_band uses `>=`, and still labels a zero rate CONTRADICTION, the exact relabelling Task 4 exists to perform. Outside the package and outside the schema test's glob. Should be retired, not re-derived from.
      **RESOLVED 2026-08-18 (7b84d39): the prototype is DELETED. It was a second writer of `mode3-disposition.csv`.**
- [ ] (deferred; ledger:368) gate.py now 939 lines.
- [ ] (deferred; ledger:399) two docstrings still describe the old (0.0,0,None) return shape; stale five-facts narrative at schema:130-134; new tautological assert at schema:218; untested high-rate-thin-support winner carrying a populated alt pair; untested winner-is-itself-a-zero case; 90-char line; no real-extract figure pinned for either new column.
- [ ] (deferred; ledger:424) stale "Three files opened" (now five); false local-import rationale at :539; unfirable KeyError assert at :569 and its test mirror; 93-char line at :659; census test guards on 2 parquet files while reading 5; conflicts_any_band counts a BAND_NO_SUPPORT positive-rate winner.
- [ ] (deferred, new; ledger:492) tests/...:900-901 asserts "rule 4 excludes nothing" while :950-953, untouched, says that is "false at the edge". Both taxonomies are defensible (scope rule 4 to N>=1, or treat rule 5 as its N=0 edge) but the file states P and not-P fifty lines apart. Same shape as Finding 2, one paragraph over. No behaviour, no test impact, one line to close.

### Task 5

- [ ] (deferred; ledger:555) stale _schema.py:137-141 citation at test :445, staled by this task's own commit; at_floor/weak each named for the other's concept; census docstring calls all three identities cross-checks when only the third is; attach_gate's unnamed ValueError on a null id; dead SUMMARY regex and never-observed MISLABELLED branch; hand-listed tier/action families _schema does not declare (a TIERS/ACTIONS tuple would fix it for every consumer); ^def decide_ misses nested defs; classify.py at 553 lines with Tasks 6 and 8 still to extend it.
- [ ] (deferred, new, SIGNATURE SHAPE; ledger:576) tests/...:707-712 and report:627 credit the ATTACHED_COLUMNS literal pin for catching the scheduled widening; the _SHARED_PAYLOAD literal is what fires. A docstring naming the wrong guard, in the same family that cites this defect class elsewhere.
- [ ] (deferred, new; ledger:579) classify.py:123-126 says attach_gate "additionally reads the columns the FRAMES share" — it reads ONLY the frames; _SHARED_PAYLOAD is now a pinned declaration with no runtime reader.
- [ ] (deferred, new; ledger:582) task-5-mutations.py:2 still carries the "lives in the tree" provenance claim that Item 1 corrected everywhere else. Gitignored, ships nowhere.
- [ ] (deferred, new; ledger:584) the harness's restore verification at :269 is a bare assert, a no-op under -O.

### Task 6

- [ ] (deferred; ledger:715) two tautological loop assertions and C5's overclaim; six pooled census keys (deliberate, argued, but rows_without_precedent=10 hides a per-direction fact); 117,331 called a ceiling twice when the ceiling is 117,463; 137-char line; "None" rendered as a literal title; claim_of[pair] takes the last writer with no assertion where precedent_rules RAISES on the analogous duplicate; harness has no n_fail ceiling so a mutation breaking every test still scores CAUGHT; schema test:79 still says 34 columns.
- [ ] (deferred, new; ledger:769) classify.py:1303 carries an unpinned "one keying 42", the ADD_PARENT counterpart of the 170, one layer out from the printed sentence. Correct today; last figure of the family with no test behind it.

### Task 7

- [ ] (deferred, new; ledger:843) backtest.py:100-104's "TOP BAND IS NOT THIN" paragraph carries four figures the reviewer measured exact (17,720 / 117-of-19,337 / 1,341 / 130-of-4,151) that no test pins.
- [ ] (deferred, new; ledger:862) of the four figures carrying "neither top band is one hop", the ADD_CHILD pair is pinned by the extract test while the ADD_PARENT pair (3,534 / 0.9977 / 617 / the shared-triple identity) is pinned by nothing. Two halves of one deliverable sentence on unequal evidence.

### Task 8

- [x] (deferred; ledger:945) 24-flag assertion mixes rows and deduped keys; _world3's six named pairs pinned only by count; to_csv guard misses indented defs; a test naming rates it does not pin; (620,11) covered only transitively; rows_mode_2 pools 744 compat with 167,330 lineage (carry to Task 9); 1,618 vs 1,617.
      **PARTIALLY RESOLVED 2026-08-18 (7b84d39): the 24-vs-25 scoping is now stated wherever the figure is published. The remaining sub-items in this bullet are open.**
- [x] (deferred, new; ledger:1005) the pin is gated behind _real(), which skips without the extract — but its source-scanning half needs no extract, so on a clean checkout the class-guard silently does not run.
      **RESOLVED by Task 8 round 3 (304cb20): same split. The source-scanning half now always runs.**
- [x] (deferred, new; ledger:1007) the POSITIVE needle hard-codes "154" while both negatives are assembled; not live (an earlier assert fails first) but it is the one string not following its own comment's rule.
      **RESOLVED by Task 8 round 3 (304cb20): the positive needle is assembled from `ASSAYS_MAPPED_IDS` like the two negatives.**
- [x] (deferred, new; ledger:1009) tests/test_assay_hygiene_schema.py:43 is a NINTH site, already correct at 137, also unscanned. And mode2.py:217 says "three functions up" where it is one.
      **RESOLVED by Task 8 round 3 (304cb20): the file set is GLOBBED so `test_assay_hygiene_schema.py` is scanned, the needle was loosened to `collaps\w+`, and `mode2.py` now says 'one function up'.**

## Cross-task carries

### Task 2

- [ ] (ledger:158) CARRY TO TASK 4: vocabulary_defects' DEFAULTS leave the floor divergence reachable for every caller except main (gate at 10/0.95, report with args omitted, file says 3/0.75, no error). The finding sanctioned this form, but the alternative — carrying applied floors on the gate frame — makes the mistake unrepresentable. Reconsider when Task 4's sweep is written.

### Task 3

- [x] (ledger:184) CARRY TO TASK 6: dispatch against `neighbours_registering`, not `neighbour_registers`.
      **ALREADY RESOLVED: the module ships `neighbour_registers`; `neighbours_registering` does not exist and the plan does not claim it (verified 2026-08-18).**
- [ ] (ledger:185) CARRY TO TASKS 6 AND 8: `LIN_NONE` means "no absence established" and covers BOTH "no neighbour holds it" AND "the sample already holds it". Two states under one label; consumers must not read it as "no neighbour has it".
- [x] (ledger:246) CARRY TO TASKS 6 AND 8 — PLAN IS STALE: docs/superpowers/plans/2026-08-17-...md:294-297 and task-3-brief.md:10-14 still publish the BRIEFED signatures (lineage_index(edges,samples,membership, assays); neighbour_registers -> 2-tuple). Both now disagree with the module in arity AND return shape. Dispatch 6 and 8 from lineage.py:113 and :370, never from the plan. Ruling: do NOT edit the plan mid-flight (briefs are already extracted and would diverge); carry correct signatures verbatim in the dispatch and let the final review triage whether the plan is corrected. Cost if wrong: a stale plan outlives the session, which the final review can catch.
      **ALREADY RESOLVED before this session: the plan now carries a SUPERSEDED banner and the shipped signatures, which match `lineage.py` exactly (verified 2026-08-18).**

### Task 5

- [x] (ledger:525) CARRY TO TASK 9: 1,591 of the 2,166 proposed rows are CONTESTED and 1,576 are tier `weak`. An unqualified "2,166 Mode 1 proposals" would badly misrepresent the evidence. Report must qualify it.
      **RESOLVED 2026-08-18 (7b84d39): MODE_1's headline now carries contested (1,591), the tier split and the 612 floor failures, ABOVE the prose. Task 9 had shipped it bare.**
- [ ] (ledger:585) CARRY TO TASKS 6 AND 8 — BEHAVIOURAL: attach_gate's widened loop astype(str)-compares ANY column the two frames share. Gate-side numerics (vocab_support, vocab_n_samples, vocab_purity, type_registrations) and claim-side `contested` become eligible the moment a caller PRE-JOINS one, and astype(str) is repr-exact — an int64/float64 split renders "5" vs "5.0" and a last-bit difference on vocab_purity renders unequal, producing a FALSE "describe different runs" raise on frames that agree numerically. Fails safe (names the column, cannot produce a wrong row) but Tasks 6 and 8 pre-join and must know. Also: a caller carrying both X and X_gate makes merge emit two X_gate columns and the guard raises "truth value of a Series is ambiguous" instead of the named error.

### Task 6

- [ ] (ledger:608) BRANCH-LEVEL DOC FIX REQUIRED (spec + plan), not Task 6's to make. Flag for the final review.
- [ ] (ledger:639) BRANCH-LEVEL DOC FIX (spec + plan): all four demotion rows plus the 5/15 scope. Not Task 6's to make.
- [ ] (ledger:683) reverse_rate 1.0 on n_both=2 should recover badly. CARRY TO TASK 7 AS ITS CENTRAL QUESTION.
- [ ] (ledger:732) CARRY TO TASK 7: know the magnitude before leaning on it.
- [x] (ledger:772) CARRY TO TASK 8: item 4's pin sits INSIDE the extract-backed test, which skips without the extract — but its source-text half has NO data dependency and skips with the data anyway. On a machine without the extract, an edit to main's prose passes silently. Split it.
      **RESOLVED by Task 8 round 3 (304cb20): the pin was split into an extract-backed measurement and a source-scan that needs no extract. Verified 2026-08-18.**

### Task 7

- [ ] (ledger:815) CARRY TO TASK 8: _proposal_source's refusal is safe live and unsafe against a smaller rule set (fires 6/4/23 at 20%/seed-7/50% hold-outs) — exactly the configuration that would close the unmeasured-vocabulary concern — and NOTHING in Task 7 pins it. No test asserts the raise fires under a reduced rule set. Task 8 inherits a measured claim with no regression guard.

### Task 8

- [ ] (ledger:904) BRANCH-LEVEL action I take after the review, not Task 8's — I wrote that script and the spec cites
- [ ] (ledger:979) NOT Task 8's, recorded for the final review: tests/test_assay_hygiene_gate.py:196 says "458 records collapsing to 154 internal ids" — 458 collapse to 137; the map holds 154 after the 17 fallbacks.
- [ ] (ledger:981) CARRY TO TASK 9: findings_census's new assertion is CARDINALITY-ONLY (right count, one key swapped, passes — unify_findings catches it, so exposure is the public-caller path); and it makes findings_census unusable on any FILTERED SUBSET of findings.csv, which Task 9's report code meets.

### Task 9

- [ ] (ledger:1092) finding is untouched. Carried to the final review as a wording fix, since the "24" is published in
