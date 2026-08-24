# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.0"]
# ///
"""Column contracts and verdict vocabulary shared by every assay-hygiene stage.

Keeping these in one place is what lets stages B-E be pure functions over
DataFrames with no database access, and what keeps task N+1 from inventing a
column name task N never wrote.
"""
from __future__ import annotations

import re

import pandas as pd

# --- UID validation ----------------------------------------------------------
# Production (main-stable-260811 @ 83b8b99) requires a 3+ letter sample type
# code. Exactly one type in the database is shorter: AB, the antibody type.
# So every AntibodyParent reference is silently discarded before an edge is
# built, and all 874 AB parents have zero incoming DERIVED_FROM.
UID_RE_PROD = re.compile(r"^([AD]\.)?[A-Z]{3,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?$")

# The fix, already on dev-v4-merge. Stage 0 uses this one and reports the delta.
UID_RE_FIXED = re.compile(r"\A([A-Z]\.)?[A-Z]{2,}-\d{6}[A-Z]{2,5}-\d+(-PUB\d*)?\Z")

# --- extract (stage A) -------------------------------------------------------
# `edge_internal_assay_id` holds a dmac `internal_assays`.id, NOT a
# seek_production `assays`.id. The two overlap numerically and share no meaning,
# and MEMBERSHIP_COLUMNS.assay_id below is the OTHER one. Membership is the
# frame stage B joins against, so these names carry `internal` explicitly:
# under a bare `assay_id` the two spaces sit in adjacent frames under one name,
# where choosing wrong is a one-token edit that yields a populated, wrong column
# rather than an error.
EDGE_COLUMNS = [
    "child_id", "parent_id", "child_uuid", "parent_uuid",
    "child_type", "parent_type",
    "edge_internal_assay_id", "edge_internal_assay_title", "edge_protocol_id",
]
MEMBERSHIP_COLUMNS = ["sample_id", "assay_id"]
ASSAY_COLUMNS = [
    "assay_id", "title", "sample_type_id", "study_id",
    "investigation_id", "project_id", "project_title",
    # resolved through dmac.assays_internal_assays; NULL for the 17 records
    # with no junction row, which fall back to (assay_id, title) per
    # neo4j_sync.py:1418-1431 (v4-stable-wt; 944-957 in NExtSEEK/dev-v3-merge)
    "internal_assay_id", "internal_assay_title",
]
SAMPLE_COLUMNS = ["sample_id", "uuid", "json_metadata", "created_at", "project_ids"]
# `sops` had no contract until stage A needed one. The same two names were
# hand-written in three unlinked places (stage0.resolve_properties, the stage 0
# fixture, and a test); this is the constant the extractor's projection and its
# frame are both built from, so the producer can no longer drift from them.
SOP_COLUMNS = ["sop_id", "title"]

# --- stage 0 (lineage backfill) ----------------------------------------------
PARENT_COLUMNS = ["child_uuid", "field", "token"]
CHILDOF_COLUMNS = ["child_uuid", "parent_uuid"]
# the graph's node index: uuid -> (sample_id, sample type). Every child_id and
# parent_id stage 0 writes is resolved through this frame.
NODES_COLUMNS = ["uuid", "sample_id", "type"]

# Mirrors nextseek_api/batch_upload/models.py:457 DerivedFromRelRow exactly.
# That model is extra="forbid", so an invented column is a hard rejection.
EDGE_ROW_COLUMNS = [
    "child_id", "child_uuid", "parent_id", "parent_uuid",
    "protocol_id", "protocol_title", "assay_id",
    "internal_assay_id", "internal_assay_title",
]
# The reporting columns ride BEHIND the payload ones and nowhere else:
# stage0_apply.to_payload slices EDGE_ROW_COLUMNS out of the front and
# apply_edges asserts this whole list, in order. A column inserted anywhere but
# the end shifts the payload slice onto a field DerivedFromRelRow forbids, which
# the server rejects outright.
STAGE0_PLAN_COLUMNS = EDGE_ROW_COLUMNS + [
    "child_type", "parent_type", "field", "n_shared", "assay_source",
    "protocol_source",
]

D_NOT_UID = "not_a_uid"
D_NO_NODE = "parent_not_a_node"
D_SELF_LOOP = "self_loop"
D_ALREADY_EXISTS = "already_has_derived_from"

# --- precedent (stage B) -----------------------------------------------------
RULE_KEY = ["project_id", "child_type", "parent_type", "internal_assay_id"]
# TWO GRAINS, AND EACH SAMPLE COUNT RIDES IMMEDIATELY BEHIND THE EDGE COUNT IT
# CHECKS -- the same placement rule `co_reg_pop` follows behind `co_reg_rate`
# and `n_samples` behind `support`: the check on a number belongs next to the
# number.
#
# `n_both`, `n_child_only` and `n_parent_only` COUNT EDGES and always have.
# `n_child_only` is `propagation_rate`'s denominator and it counts edges whose
# PARENT is, by construction, an ADD_PARENT candidate for that assay -- it is a
# count of the proposals themselves, never of the house declining them. One
# parent fans out over every child it has, so the edge count says how connected
# the graph is where the sample count says how many samples are involved.
# Measured on this extract: 666,939 `n_child_only` edges raise 55,007 distinct
# (parent, internal assay) ADD_PARENT candidates -- 12.1x -- and the largest
# single rule is 303,866 edges over 616 samples, 493x.
#
# THE COLUMN DOES NOT SUM TO THAT CEILING AND IS NOT MEANT TO. Summing
# `n_child_only_samples` over the 961 rules gives 57,946, not 55,007: a rule is
# scoped to one (project, hop), so a parent with children of two types is
# counted once per rule. Each cell is the sample count for ITS rule.
#
# THE TWO NEW COLUMNS ARE DISPLAY AND NOT RANKING. Neither rate is recomputed
# over them and the row order is unchanged -- regraining the RATE moves it
# materially on 8 of the 270 real hops with >= 50 forward edge observations,
# median |delta| 0.000, so the defect was in what reviewers were shown and not
# in what ranked them. See `precedent.mine_precedent` and
# `dossier.build_dossiers`.
PRECEDENT_COLUMNS = RULE_KEY + [
    "internal_assay_title",
    "n_both",
    "n_child_only", "n_child_only_samples",
    "n_parent_only", "n_parent_only_samples",
    "propagation_rate", "reverse_rate",
]

# --- classify (stage C) ------------------------------------------------------
#
# THE GRAIN CHANGED. This list described a per-EDGE finding until 2026-08-17 and
# now describes a per-SAMPLE one: one row per `(sample_id,
# proposed_internal_assay_id)`. Two meanings under one constant name, one frame
# apart, is this branch's signature defect and it has occurred four times, so
# the change was made only after verifying the blast radius: `FINDING_COLUMNS`
# had exactly ONE reference in the whole tree outside this file -- a schema
# test -- and no producer or consumer at all. There was nothing to migrate.
#
# The mitigation for the next reader is structural rather than documentary. The
# two column sets are WHOLLY DISJOINT, so anything written against the per-edge
# shape (`child_id`, `parent_id`, `verdict`, `candidates`, `matched_*`,
# `target_*`) raises a KeyError instead of reading a populated, wrong column.
# tests/test_assay_hygiene_schema.py pins that absence by name.
#
# It read "DISJOINT apart from `project_id`, which means the same thing in both"
# until 2026-08-17, when that one shared name was renamed to `project_ids`. See
# the column note below: it was neither the same thing in both nor singular in
# either, and the exemption is now gone rather than merely documented.
#
# Why per-sample. Mode 1's population is samples registered in NO assay and has
# no edge to hang a row on; Mode 2's proposal is a membership row, which is
# per (sample, assay) however many edges support it; and the writer
# (`smart_merge_assay_assets`) is keyed per sample with a complete assay list.
# An edge-grained finding could express none of those without a second collapse.
#
# Column notes, where the name carries something a reader cannot recover:
#
# `project_ids` is PLURAL, and it was `project_id` until 2026-08-17. Three
#   separate facts forced the rename, and any one of them alone would have:
#
#   1. THE VALUE IS A SET. It carries the SAMPLE's projects, `;`-joined in the
#      convention `registered_internal_assay_ids` one line down already uses.
#      Measured over Mode 1's population, 1,052 of the 6,242 samples hold more
#      than one project id, 34 hold the same id twice (the raw `GROUP_CONCAT`
#      spells it `2,2`), and 193 hold none.
#   2. THE SOURCE IS ALREADY PLURAL. `SAMPLE_COLUMNS.project_ids` above is the
#      frame this is read from, so the singular spelling here was the ONLY place
#      in this module that renamed a plural set on its way through.
#   3. THE SINGULAR NAME IS TAKEN, TWICE, BY SOMETHING THAT REALLY IS SINGULAR.
#      `ASSAY_COLUMNS.project_id` is the one project an assay record belongs to,
#      and `RULE_KEY.project_id` is the one project a precedent rule is scoped
#      to. That is the decisive one: the Mode 2 classifier keys on `RULE_KEY`
#      and emits `FINDING_COLUMNS`, so under the old spelling one name meant
#      "exactly one project" in the key and "a `;`-joined set" in the row, in
#      two frames the same function holds open at once. That is this module's
#      signature defect in its purest form and it has cost this branch four
#      tasks. `test_no_finding_column_collides_with_the_rule_key` now fails on
#      any future recurrence rather than leaving it to a reader.
#
#   The proposed assay's project would not have rescued the singular either: 75
#   of the 137 internal assay ids span more than one project, up to seven. There
#   is no single-valued project anywhere on this row.
#
#   THE DENOMINATOR IS 137 AND NOT 154, corrected 2026-08-18 against the
#   parquet. `assays.parquet` carries 458 records over 137 distinct non-null
#   `internal_assay_id`s plus 17 with none, so `precedent.assay_index`'s map
#   holds 154 -- the 137 plus one fallback per junction-less record. Not one of
#   those 17 fallbacks can span a project, since each stands for exactly one
#   record, so all 75 come out of the 137 and 154 is the wrong denominator for
#   this numerator. 154 IS right wherever the sentence counts what the MAP
#   resolves, which is what it does at `VOCAB_COLUMNS` below and in
#   `mode2.assay_titles`.
#
#   Renamed before the first emitter shipped, which is the same moment
#   `registered_internal_assay_titles` and `co_reg_registered_internal_assay_id`
#   were ADDED and the same argument: `FINDING_COLUMNS` had no producer outside
#   the module being written against it, so this is the cheapest it will ever be.
#   It takes no `_titles` partner and needs none -- a project id is what a
#   curator routes on and this package extracts no project title per sample.
# `registered_internal_assay_ids` is the ANY-membership definition -- a sample
#   with any membership row is registered -- crossed to the internal namespace
#   by `audit.registered_internal`. The MAPPABLE definition is a smaller set,
#   82 samples smaller on the real extract, because 17 assays carry no junction
#   row. The two differ, they have been confused once already in this project,
#   and this column is the ANY one.
# `registered_internal_assay_titles` rides immediately behind its id column and
#   holds the SAME ids decoded, in the SAME positions, both `;`-joined: index i
#   of one names index i of the other. It carries the identical name and meaning
#   as AUDIT_COLUMNS' column of that spelling, deliberately -- one concept, one
#   name, which is the opposite of the adjacency hazard the rest of this module
#   guards. Without it a row reads `registered 115, proposes 24 DNA Extraction`,
#   a bare id on the registered side against a decoded one on the proposed side,
#   and the operator cannot judge the proposal without a lookup they have no
#   artifact for. AUDIT_COLUMNS settled this same asymmetry in increment 1 and
#   the argument carries over unchanged; it is added here for the reason given
#   there, that the moment before the first consumer exists is the one moment a
#   column costs nothing, and no task builds a findings row yet.
#
#   The ids stay. A title is DISPLAY and never IDENTITY: `assay_index` raises on
#   a junction-less assay whose fallback id collides with a genuine internal id,
#   which is what makes ids safe to key on, and nothing makes titles safe -- 458
#   seek assay records collapse to 291 normalised titles. Nothing downstream may
#   key, join or group on this column. Titles come from `precedent.assay_index`,
#   the same funnel that produced the ids, so no second source of truth appears.
# `proposed_*` and not `claimed_*` or `target_*`: under the binding constraint
#   ("nothing decides, everything proposes") the row is a proposal, and the
#   header is where a reader forms their belief about what the pipeline already
#   did. Same reason `proposed_by` is not `decided_by`.
# `proposed_by` names which evidence produced the proposal -- the gated
#   vocabulary claim, precedent, or both. On a hop carrying several candidate
#   assays it is what records that the metadata claim disambiguated.
# `claim_tier` and not `tier`: `CLAIM_COLUMNS` carries a `tier` one join away
#   and `PRECEDENT_COLUMNS` carries rates under bare names, so every borrowed
#   column here is prefixed with the frame it came from. Likewise `vocab_*`
#   for the vocabulary row's support / purity / provenance, and `precedent_*`
#   for stage B's counts.
# `vocab_provenance` holds the same value `CLAIM_COLUMNS.source_provenance`
#   does -- the provenance of the ONE vocabulary row named by `source_field`
#   and `raw_value`, never a rank across sources -- and is spelled `vocab_*`
#   here so it sits with the support and purity it was measured beside.
# `co_reg_pop` is the SUPPORT behind `co_reg_rate`, in samples of this type.
#   It rides immediately behind its rate for the reason `n_samples` rides
#   behind `support` in VOCAB_COLUMNS: a rate of 0.000 over four samples is
#   noise, and the check on a number belongs next to the number.
# `co_reg_registered_internal_assay_id` names WHICH of the sample's existing
#   registrations the rate was measured against, and it COMPLETES the triple
#   above rather than decorating it. A co-registration rate is a statement about
#   an ORDERED PAIR -- across samples of this type registered in R, what share
#   also register X -- while `registered_internal_assay_ids` lists every R the
#   sample holds, up to 7 on the real extract.
#   `compatibility.best_co_registration` picks the R yielding the best rate, so
#   without this column a row reads `registered 56;74;112;133, rate 0.805` and
#   the operator cannot tell which registration produced 0.805, cannot check it,
#   and cannot see that the others were weaker. That makes the finding
#   unexplainable in the artifact whose whole premise is that a human approves it.
#
#   ADDED BEFORE ITS FIRST CONSUMER EXISTS, which is the call
#   `registered_internal_assay_titles` was added under and the same reason:
#   Tasks 5, 6 and 8 would otherwise each decide independently whether to keep
#   the winner `best_co_registration` already returns, and the one that discards
#   it ships the unexplainable row. A divergence between consumers costs more
#   than a column, and this is the cheapest this will ever be.
#
#   AN ID AND NEVER A TITLE, as everywhere in this module: a title is display
#   and never identity, and 124 seek ids collide numerically with genuine
#   internal ids under 122 different titles. It takes no `_title` partner and
#   needs none -- the assay it names is always a member of
#   `registered_internal_assay_ids`, whose `_titles` column already decodes the
#   whole set in position, so the operator can read it without a second lookup.
#
#   EMPTY exactly when no population was measured at all:
#   `best_co_registration` returns `(0.0, 0, None, None, 0)` when no registered
#   assay reaches a co-registration key, and `compat_band` bands that
#   BAND_NO_SUPPORT because it tests support before rate. An id beside a support
#   of 0 would name a population nobody measured.
#
#   AND `co_reg_rate` IS NULL ON EXACTLY THOSE ROWS, which is one column's
#   contract and was living in two files with only one of them updated. That
#   0.0 is safe INSIDE `best_co_registration`, because `compat_band` tests
#   support first; written into `findings.csv` it states a MEASURED rate of
#   zero -- "these never coexist" -- on the one row whose own
#   `evidence_summary` says that is absent evidence and not a rate of zero.
#   `classify.compat_findings` nulls it, and `co_reg_pop` stays 0 beside it:
#   the population WAS read and it is empty, which is what makes the band
#   BAND_NO_SUPPORT rather than BAND_NEVER. Measured 2026-08-18, 0 of the 6,932
#   compatibility rows reach it -- all 45 BAND_NO_SUPPORT rows have a real
#   winner over 4 to 28 samples and a genuinely measured 0.000, and they keep
#   it.
# `co_reg_alt_label_internal_assay_id` and `co_reg_alt_label_pop` carry the
#   COUNTER-EVIDENCE: the assay this sample ALREADY HOLDS that never
#   co-registers with the proposed one, over a population big enough to read,
#   and the size of that population. `compatibility.best_co_registration`
#   returns both.
#
#   They exist because the winning rate is a BEST-OF and a best-of hides its
#   losers. A sample holding R1 and R2, proposed X, with (T,R1,X) = 0.000 over
#   2,000 and (T,R2,X) = 0.9 over 100, reports 0.9 -> BAND_ROUTINE ->
#   CLS_ABSENCE_COMPAT, "the absence is the anomaly, propose X" -- while the
#   well-supported zero saying X is an ALTERNATIVE LABEL for R1, which the
#   sample already carries, never reaches the operator. A well-supported zero is
#   not silence; it is the counter-evidence.
#
#   NOT RARE, which is why they are columns and not a footnote. Measured
#   2026-08-17 over the 7,831 (gated claim, type) rows on a registered sample
#   whose proposed assay it does not hold: 5,839 (74.6%) have a well-supported
#   zero available, and 428 (5.5%) are outright conflicts where the row would
#   otherwise say "propose X" unopposed. 408 of the 428 are the spec's own
#   flagship vocabulary defect -- DNA samples proposed 24 DNA Extraction on the
#   `Type: Illumina Library` mapping at purity 0.707 -- so the counter-evidence
#   points at rows already independently identified as wrong.
#
#   THE POPULATION RIDES WITH THE ID for the reason `co_reg_pop` rides with
#   `co_reg_rate` and `n_samples` rides with `support`: the whole meaning of a
#   zero is its support, which is what `BAND_NO_SUPPORT` exists to say. A bare
#   "never co-registers with 173" with no population repeats the exact error
#   that band was declared to prevent.
#
#   BOTH ARE EMPTY when no registration of this sample carries a well-supported
#   zero against the proposal. When the WINNER is itself a zero the two agree by
#   construction, the row is self-consistent, and the id names the registration
#   the proposal duplicates -- 1,755 rows read "propose 138 CometChip Assay"
#   against a zero on 37 Device Imaging over 8,179, and without the column the
#   operator is told these are alternative labels and never told of what.
#
#   THEY DO NOT RE-CLASSIFY ANYTHING. `compat_band` still bands the WINNER, so a
#   conflicted row still reads CLS_ABSENCE_COMPAT. Whether a populated
#   alt-label id should demote it is a classification ruling and Tasks 5 and 6
#   own classification; this layer owes them the evidence and its measured size,
#   not a fourth bucket named for what someone assumed was in it.
# `type_registrations` counts the samples of THIS row's `sample_type` already
#   registered in the proposed assay, and it carries the same name and the same
#   meaning as `gate.GATE_COLUMNS`' column of that spelling -- one concept, one
#   name, the call `registered_internal_assay_titles` makes against
#   `AUDIT_COLUMNS`. It sits with the `vocab_*` block because both are the
#   GATE's evidence, and it is the only member of that block a row with no claim
#   still carries.
#
#   A COUNT AND NEVER A BOOLEAN, and ZERO IS THE FINDING. A row reading 0 would
#   create a (sample type, assay) pair that exists NOWHERE in the database --
#   measured 2026-08-17 over the emitted Mode 2 rows, 30,496 of 55,007
#   ADD_PARENT rows (55.4%) and 73,195 of 117,331 ADD_CHILD rows (62.4%). A
#   boolean would collapse "joins five existing registrations" with "joins
#   5,000", and a curator triages on the difference.
#
#   IT IS THE SAME CELL `gate.type_registration_index` RULES REACHABILITY ON,
#   and the two rules differ in what they DO with an empty one. A CLAIM resting
#   on an empty cell is blocked `GATE_UNREACHABLE`, because the vocabulary is
#   the only evidence behind it. A MODE 2 row is flagged and still emitted,
#   because its evidence is a neighbour's actual registration, which the gate
#   has no opinion about. Blocking here would silently delete the proposals the
#   design exists to surface.
#
#   NULL means the sample's TYPE could not be resolved, which is a third state
#   and not a zero: `type_reg.get((None, assay))` misses exactly as an empty
#   cell does, so a missing type reported as 0 would assert the strongest
#   negative flag the row can carry about a type nobody knows. 0 rows on the
#   real extract, where every edge endpoint carries a node row.
# `lineage_n_supports` is how many lineage neighbours register the proposed
#   assay, from `lineage.lineage_supports`, and it rides behind
#   `lineage_neighbour_uuid` because it is the check on it: the row NAMES one
#   neighbour and this says how many there were. A `(sample, assay)` pair is ONE
#   membership write however many neighbours support it, so the row is emitted
#   once; without this column a proposal backed by 1,526 neighbours -- the real
#   extract's maximum -- reads exactly like one backed by a single edge. 31,180
#   of the 172,338 emitted rows carry more than one.
#
#   NULL on a mode that never ran the lineage test, which is Mode 1.
# `precedent_direction` says which of stage B's two rates `precedent_rate`
#   holds. They differ -- 0.931 against 0.006 on the hop that justified Mode 2
#   -- so a row carrying a bare rate cannot be audited. Its VALUE is the name of
#   the `PRECEDENT_COLUMNS` column the rate was read from, so a reader can join
#   the row back to `precedent.csv` and check the number without consulting any
#   code. `mode2.ACTION_PRECEDENT_DIRECTION` is the one place the mapping
#   from action to column lives.
# `precedent_n_child_only_samples` / `precedent_n_parent_only_samples` are the
#   SAMPLE-grained halves of the two directional counts, each riding
#   immediately behind the edge count it checks. The edge counts are not
#   refusals: `precedent_n_child_only` counts edges whose PARENT the house has
#   not registered, and that parent is the ADD_PARENT proposal itself, so a
#   large number there is lineage fan-out. The rework's worked case reads 1,300
#   edges over 325 samples on `(2, D.ADCD, TIS, 153)`. Both grains reach an
#   operator through `dossier.build_dossiers`, which rendered only the edge
#   count -- under a reading calling it repeated refusal -- through the 1,012
#   agent adjudications of 2026-08-21. Neither rate is computed over them; see
#   `PRECEDENT_COLUMNS` for why regraining the rate was measured and declined.
# `precedent_supports` is `n_both > 0` -- whether the house has EVER made this
#   co-registration -- and it rides immediately in front of `proposed_by`
#   because it is the check on it. Measured 2026-08-24 over the 170,786 rows of
#   `findings.csv`, 115,087 of the 166,578 `BY_PRECEDENT` rows (69.1%) carry
#   `precedent_n_both == 0` and `precedent_rate == 0.000`: the column naming
#   precedent as the proposer is at its most common on the rows where
#   precedent's own content argues against the proposal. A curator filtering
#   `proposed_by` to find well-supported rows gets, in the majority, the
#   opposite set, and nothing on the row made that filterable in one predicate.
#
#   THE COLUMN'S OWN TOTAL IS 115,104 AND NOT 115,087, and the difference is
#   scoping rather than disagreement. 115,087 counts rows that are BOTH
#   `BY_PRECEDENT` and unsupported, which is the population the paragraph above
#   is about; this column is scoped to the ROW and marks every rule reading
#   zero, including the 17 whose gated claim also names the pair and which
#   therefore read `BY_BOTH`. The mirror is larger and runs the other way: 744
#   of the 52,235 supported rows are `BY_BOTH` and no `proposed_by` filter
#   finds them either. Same measurement, 2026-08-24.
#
#   `proposed_by` IS NOT CHANGED AND IS NOT LYING. It is a PROVENANCE label:
#   `BY_PRECEDENT` means a rule on the hop produced this proposal and no gated
#   claim did, which is true on all 166,578. What it never claimed to say is
#   what the rule CONTAINS, and this column is that, beside it.
#
#   NULLABLE, AND THE NULL IS THE THIRD STATE THE BLOCK ALREADY KEEPS. `None`
#   is "there is no rule on this hop, so nobody measured"; `False` is "there is
#   a rule and it reads never". Collapsing them would repeat the mistake
#   `precedent_rate`'s null exists to prevent -- 0.000 is a rate and absent
#   evidence is not. Mode 1 and the compatibility lane have no hop and so no
#   rule, and both emit `None`.
#
#   DERIVED FROM `precedent_n_both` AND NOT FROM THE RATE. A rate of 0.000 also
#   occurs where `n_both == 0`, but the rate is one of two directions and the
#   count is not, so reading the rate would make the answer depend on
#   `precedent_direction`. Redundant with the count on purpose: the count is
#   the evidence and this is the one predicate a filter can hold.
# `id_namespace` says which id space `proposed_internal_assay_id` speaks, and
#   it is the row's own answer to this package's signature failure. 17 SEEK
#   assay records have no junction row and `precedent.assay_index` falls back
#   to their own `assays.id`, deliberately and documented there -- so a column
#   spelled `proposed_internal_assay_id` holds a raw SEEK id on some rows.
#   Measured 2026-08-24, 1,321 of the 170,786 rows, over 8 of the 17.
#
#   NEITHER JOIN IS SAFE WITHOUT IT, and they fail in opposite directions. A
#   consumer joining the column against `dmac.internal_assays` silently DROPS
#   those 1,321. One joining it against `seek_production.assays` is worse than
#   short: measured 2026-08-24, 162,370 of the other 169,465 rows carry an
#   internal id that numerically collides with some seek `assays.id` -- 87
#   distinct ids do -- so the join SUCCEEDS and returns the wrong assay record,
#   and only the remaining 7,095 fail to match at all. A frame that looks right
#   in both cases, and in the second one it is populated and wrong, which is
#   this package's named failure class exactly.
#
#   IT DESCRIBES THE PROPOSED ID AND NOTHING ELSE ON THE ROW.
#   `registered_internal_assay_ids` is resolved through the same fallback and
#   can carry one too; it is a `;`-joined SET, so one scalar cannot describe it
#   and a second column would be needed to. The proposed id is the one the
#   write path resolves, which is why this one exists first.
#
#   `ID_NAMESPACES` is the vocabulary and `id_namespace` below is the one place
#   the value is chosen. The SET it is chosen against is
#   `precedent.fallback_assay_ids`, the package's single definition of "this
#   record has no junction row", and every lane is HANDED it rather than
#   deriving one -- a lane holding its own opinion about which ids are
#   junction-less is the same class of defect as a second definition of
#   "registered".
FINDING_COLUMNS = [
    "sample_id", "uuid", "sample_type", "project_ids",
    "registered_internal_assay_ids", "registered_internal_assay_titles",
    "proposed_internal_assay_id", "proposed_internal_assay_title",
    "id_namespace",
    "mode", "classification", "gate",
    "claim_tier", "contested", "source_field", "raw_value",
    "vocab_support", "vocab_purity", "vocab_provenance", "type_registrations",
    "lineage", "lineage_neighbour_uuid", "lineage_n_supports",
    "co_reg_rate", "co_reg_pop", "co_reg_registered_internal_assay_id",
    "co_reg_alt_label_internal_assay_id", "co_reg_alt_label_pop",
    "compat_band",
    "precedent_rate", "precedent_direction",
    "precedent_n_both",
    "precedent_n_child_only", "precedent_n_child_only_samples",
    "precedent_n_parent_only", "precedent_n_parent_only_samples",
    "precedent_supports",
    "proposed_by", "evidence_summary", "action",
]

# The two id spaces `proposed_internal_assay_id` can hold, as the values
# `FINDING_COLUMNS.id_namespace` takes. `NS_INTERNAL` is a dmac
# `internal_assays`.id and `NS_SEEK_FALLBACK` is a raw seek_production
# `assays`.id, standing in for one of the 17 records with no junction row.
NS_INTERNAL = "internal"
NS_SEEK_FALLBACK = "seek_fallback"
ID_NAMESPACES = (NS_INTERNAL, NS_SEEK_FALLBACK)


def id_namespace(assay_id, fallback: set[int]) -> str:
    """Which id space `assay_id` speaks. One of `ID_NAMESPACES`.

    THE ONE PLACE THE VALUE IS CHOSEN, and it lives here rather than in each of
    the three emitting lanes because a one-line ternary copied three times is
    how two of them end up disagreeing after an edit -- the same argument
    `precedent.fallback_assay_ids` makes about the predicate it owns, one level
    down.

    `fallback` IS THE CALLER'S AND IS NOT DERIVED HERE. It comes from
    `precedent.fallback_assay_ids`, the package's single definition of "this
    record has no junction row", and this function is deliberately unable to
    build one: a module that could would be a second opinion about which ids
    are junction-less, which is exactly the class of defect the column exists
    to expose. An EMPTY set is therefore a legal answer meaning "every record
    is junctioned", and the lanes take theirs as a required argument so that no
    default can quietly supply one.

    `int()` GUARDS A STRING AND NOT A NUMPY SCALAR. `np.int64(490) in {490}` is
    True and so is `np.float64(490.0) in {490}` -- numpy integers hash equal to
    Python ints -- so the coercion buys nothing there. What it buys is the
    round-trip: an id read back out of `findings.csv` or handed in from a
    hand-built frame can arrive as `"490"`, which matches nothing in the set
    and would report every row `internal` with no error at all.
    """
    return NS_SEEK_FALLBACK if int(assay_id) in fallback else NS_INTERNAL


# --- emit (stage E) ----------------------------------------------------------
# Increment 3's contract, with no consumer anywhere in the tree. `decided_by`
# was renamed to `proposed_by` here at the same time as the FINDING_COLUMNS
# rewrite and for the same reason: two names for one concept, one screen apart,
# is how the wrong one gets shipped, and nothing decides.
RULE_COLUMNS = PRECEDENT_COLUMNS + [
    "verdict", "action", "affected_count", "proposed_by", "rationale",
    "APPROVE", "NOTES",
]

# --- claims (stage B2) -------------------------------------------------------
#
# A sample's own metadata naming the assay it belongs to. Measured 2026-08-14,
# learning the value->assay mapping on half the samples and scoring the held-out
# half against the 360,027 curator-labelled edges (split BY SAMPLE, because a
# sample fans out to many edges and an edge-level split scores memorised
# answers):
#
#   strong fields alone                     65.9% coverage   98.4% accuracy
#   strong then Protocol/DataType           92.3% coverage   90.4% accuracy
#   Type and Protocol predict and agree     35.0% coverage   99.9% accuracy
#
# So the strong fields decide and the weak ones corroborate. Order matters:
# tier assignment walks CLAIM_FIELDS and must see strong fields first.
STRONG_FIELDS = ["Type", "Instrument", "Stimulation", "Software",
                 "SlideStain", "Assay", "Channels", "Stains"]
WEAK_FIELDS = ["Protocol", "DataType"]
CLAIM_FIELDS = STRONG_FIELDS + WEAK_FIELDS

T_CORROBORATED = "corroborated"
T_STRONG = "strong"
T_WEAK = "weak"
# RETIRED as an emitted tier; kept so imports do not break. Tiering is per
# CLAIM, not per sample, and disagreement between a sample's claims is recorded
# in the `contested` COLUMN instead. Measured 2026-08-14: collapsing a
# disagreeing sample to this tier made the Mode 3 audit non-monotone, because
# T_CONFLICT sits below the audit floor -- simulating proposals for the
# unresolved terms suppressed 102 existing flags while adding 13. Adding
# evidence removed coverage. tests/test_assay_hygiene_claims.py asserts
# sample_claims never emits it.
T_CONFLICT = "conflict"
T_NONE = "none"

# `contested` and `source_provenance` ride BEHIND the original seven, which is a
# deliberate ordering and not just an append. `contested` is a policy dial the
# Mode 3 audit reads (Task 7 excludes contested rows by default: admitting them
# raises the flag baseline from 866 to 1,556 AT THE SHIPPED DEFAULTS, and those
# extra rows carry a measured ~30% mapping-error rate). The scope belongs in
# that sentence and this file is where it is declared: the same pair reads
# 879 -> 1,570 with `include_unmappable` on, which is what the figure was before
# Task 7 added that second exclusion, and an unscoped number here is the exact
# hazard the rest of this module documents. `source_provenance` is what makes the
# proposal cap auditable after the fact -- a claim tiered T_WEAK on a `proposed`
# mapping and one tiered T_WEAK on a `learned` weak field are indistinguishable
# without it.
#
# It is `source_provenance` and NOT `provenance` because it is ROW-scoped: it
# describes the one vocabulary row named by `source_field` and `raw_value`, and
# NOT the highest precedence among everything backing the claim. So a claim
# backed by a learned strong field AND a curator weak field reports `learned`,
# naming the strong row the evidence columns actually point at; the curator's
# ruling is what made that claim `corroborated`, and vocabulary.csv stays the
# record of who ruled what. Ranking provenance across sources instead would
# print `curator` beside a `source_field` whose mapping no curator ever touched
# -- the same incoherence claims.py's representative-source rule exists to
# remove. Pinned by test_provenance_names_the_row_the_evidence_columns_name.
#
# The NAME carries that scope because a comment cannot. VOCAB_COLUMNS below has
# its own `provenance`, meaning the provenance of a MAPPING, and the two frames
# sit one join apart: under a bare `provenance` here, two meanings live under one
# name in adjacent frames, where picking wrong is a one-token edit that yields a
# populated, wrong column rather than an error. That is the same hazard
# EDGE_COLUMNS documents for `edge_internal_assay_id`, and it is why this column
# was renamed before its first consumer (Task 7) was written rather than after.
CLAIM_COLUMNS = [
    "sample_id", "uuid", "internal_assay_id", "internal_assay_title",
    "tier", "source_field", "raw_value", "contested", "source_provenance",
]

# --- vocabulary alignment ----------------------------------------------------
#
# provenance records where a mapping came from, because the three are trusted
# differently: `learned` is backed by curator-labelled edges and carries a
# support count, `proposed` is a model's suggestion for a term with no
# empirical anchor, and `curator` is a human decision that outranks both.
P_LEARNED = "learned"
P_PROPOSED = "proposed"
P_CURATOR = "curator"

# Every provenance this package recognises, and the subset carrying empirical
# backing. `claims.py` tests MEMBERSHIP of EVIDENCE_PROVENANCES rather than
# inequality against P_PROPOSED, and that is the whole point of the tuple.
#
# Under `p != P_PROPOSED` this column was read under OPPOSITE defaults by two
# modules: `vocabulary.merge_vocabulary` ranks an unrecognised provenance -1,
# meaning LEAST trusted, while `p != P_PROPOSED` read that same value as
# EVIDENCE-BACKED. So a support=0 guess written as `Proposed`, `PROPOSED`,
# `proposal` or `` defeated the proposal cap and the contest rule together --
# it crossed the Mode 3 audit floor AND could contest a real claim. The
# producer of the column is an LLM writing a csv per
# `commands/curate-assay-vocabulary.md`.
#
# Membership makes the default STRUCTURAL: anything unanticipated is untrusted,
# which is the same direction merge_vocabulary already ranks it. Measured
# 2026-08-14 on the real extract, lifting the cap and nothing else moves the
# audit from 866 flags to 876 at the shipped defaults (879 -> 902 with
# `include_unmappable` on).
#
# The two layers own different halves and both are needed. THIS one is the
# safety invariant and it holds for any frame, including one a caller builds in
# memory. `vocabulary.load_vocabulary` owns the data-quality half at the file
# boundary: it normalises the spelling and REJECTS a value that is still not one
# of these three, so a curator writing `Proposed` gets their row honoured rather
# than silently demoted, and one writing junk is told rather than ignored.
PROVENANCES = (P_LEARNED, P_PROPOSED, P_CURATOR)
EVIDENCE_PROVENANCES = (P_LEARNED, P_CURATOR)

# `n_samples` sits immediately after `support` because it is the check on it.
# `support` counts EDGES and one sample fans out to many, so a term can clear
# min_support off a single curator's single row: measured 2026-08-14 on the real
# extract, 83 of the 736 learned terms rest on fewer than 3 distinct samples and
# 50 rest on exactly ONE -- `Software: matlab` reads as support 132 from one
# sample, `Type: github` as support 73 from one. Edge-weighted support is
# deliberate and stays, because every figure this design rests on was measured
# against it; this column exists so that weakness is visible in the artifact
# rather than hidden behind a reassuring support count.
VOCAB_COLUMNS = [
    "source_field", "raw_value", "internal_assay_id", "internal_assay_title",
    "support", "n_samples", "purity", "provenance",
]

# --- audit (mode 3) ----------------------------------------------------------
#
# `registered_internal_assay_titles` rides immediately behind its id column and
# holds the SAME ids decoded, in the SAME positions, both `;`-joined: index i of
# one names index i of the other. It is not decoration. Mode 3's whole product
# is a list a curator reads and rules on, and without it a row reads
# `registered 115, claims 24 DNA Extraction` -- a bare id on the registered side
# against a decoded one on the claimed side -- so the reader cannot judge the
# contradiction the row asserts without a lookup they have no artifact for. The
# frame was internally inconsistent from the moment it carried both
# `claimed_internal_assay_id` and `claimed_internal_assay_title`.
#
# Titles come from `precedent.assay_index`, the same funnel that produced the
# ids, so no second source of truth appears and no id can decode to a title its
# own registration does not carry. Every id resolves by construction, both
# columns being built from that one map. Measured on the real extract
# 2026-08-14: 0 of the 458 assay records carry an internal id with no title, and
# 0 internal ids resolve to more than one distinct title over the 154 in the
# map, so the decode is total and single-valued on today's data.
#
# Added in Task 7's fix round, deliberately BEFORE the first consumer existed:
# `AUDIT_COLUMNS` had exactly one non-test reference in the tree (audit.py's
# constructor) and Task 8 was unwritten, so this is the one moment a column
# costs nothing. Position is chosen for the same reason STAGE0_PLAN_COLUMNS
# fixes its own: a reader scanning the header meets the two halves of one fact
# side by side.
AUDIT_COLUMNS = [
    "sample_id", "uuid", "sample_type",
    "registered_internal_assay_ids", "registered_internal_assay_titles",
    "claimed_internal_assay_id", "claimed_internal_assay_title",
    "tier", "source_field", "raw_value",
    "verdict",
]


def normalise_value(v) -> str | None:
    """Free text to a comparable key, or None when there is nothing to compare.

    `Liver`, `liver` and `LIVER` appear as three values on the same field in
    production. These are curator-entered fields with no controlled vocabulary,
    so every comparison in this package goes through here.
    """
    if not isinstance(v, str):
        return None
    s = " ".join(v.split()).strip().lower()
    return s or None


# --- vocabulary --------------------------------------------------------------
V_CLEAN = "CLEAN"
V_MODE1_CHILD = "MODE_1_CHILD"
V_MODE1_PARENT = "MODE_1_PARENT"
V_MODE1_BOTH_DARK = "MODE_1_BOTH_DARK"
V_MODE2_PROPAGATE = "MODE_2_PROPAGATE"
V_MODE2_AMBIGUOUS = "MODE_2_AMBIGUOUS"
V_MODE3_FLAG = "MODE_3_FLAG"

A_NONE = "NONE"
A_ADD_PARENT = "ADD_PARENT_TO_ASSAY"
A_ADD_CHILD = "ADD_CHILD_TO_ASSAY"
A_ADD_TO_ASSAY = "ADD_TO_ASSAY"
A_FLAG_ONLY = "FLAG_ONLY"

# --- stage C vocabulary ------------------------------------------------------
#
# Five closed families. Each enumerates itself in a tuple, the way PROVENANCES
# does, because a "closed vocabulary" a consumer cannot enumerate cannot be
# checked for closure by that consumer -- it can only be restated, and a
# restatement is what drifts. The values are prefixed to match their constant
# names so that a value read out of `findings.csv` names its own family; these
# columns are read by an operator, not only by a join.
#
# Distinct from the V_* / A_* / T_* families by test, not by inspection. V_* is
# the per-EDGE verdict vocabulary of the superseded stage C (only V_MODE3_FLAG
# still has a producer, in audit.py), and MODE_1 sitting beside V_MODE1_CHILD is
# exactly the adjacency this module exists to police.

# Which mode proposes a row. Mode 3 is NAMED and never EMITTED: measured
# 2026-08-17 over increment 1's 866 flags, not one is a contradiction -- 576 are
# absences, 31 vocabulary defects, 45 alternative labels, 214 unclassified -- so
# the detector built for "what samples have INCORRECT assays" does not detect
# that. The constant stays because the report has to name the mode in order to
# say it found nothing; a mode the vocabulary cannot spell gets reported as
# ABSENT, and undetected is a different and worse finding than small.
MODE_1 = "MODE_1"
MODE_2 = "MODE_2"
MODE_3 = "MODE_3"
MODES = (MODE_1, MODE_2, MODE_3)
EMITTED_MODES = (MODE_1, MODE_2)

# The vocabulary gate, which runs BEFORE every mode. A claim is only as good as
# the term that produced it, and until 2026-08-17 no stage tested the term:
# lineage precedence fired first, so 24 A.FLOW / A.SPC rows whose claims name
# the measurement assay while the sample is registered in the ANALYSIS assay
# were laundered into Mode 2 write proposals, and one mapping at purity 0.707
# produced 212 of 250 compatibility flags.
GATE_PASS = "GATE_PASS"
GATE_UNREACHABLE = "GATE_UNREACHABLE"      # this TYPE is never in this assay
GATE_INCOHERENT = "GATE_INCOHERENT"        # the term family maps to 2+ assays
GATE_LOW_SUPPORT = "GATE_LOW_SUPPORT"      # under the support OR purity floor
GATE_OUTCOMES = (GATE_PASS, GATE_UNREACHABLE, GATE_INCOHERENT, GATE_LOW_SUPPORT)
# The non-PASS outcomes: every way the gate can find fault with a claim. A
# membership test rather than three inequalities a later edit can forget to
# extend -- the same argument EVIDENCE_PROVENANCES makes against
# `p != P_PROPOSED`.
#
# THIS IS NOT THE SET THAT STOPS A CLAIM, and it said it was until 2026-08-17,
# when it read "the subset that reaches no mode". That is now false, and the
# correction is recorded here rather than quietly applied, because a stale
# comment in the shared contract module is exactly how a consumer ends up with a
# bucket named for what someone assumed was in it. Under the binding constraint
# -- nothing decides, everything proposes -- a THRESHOLD ranks and triages and
# does not grant permission, so GATE_LOW_SUPPORT, which is the outcome of two
# tuned floors, is RECORDED on the row and does not block. GATE_UNREACHABLE and
# GATE_INCOHERENT rest on evidence with no tuned number in them, and they do.
#
# `gate.blocks_mode` is the single place that rule lives and is what every
# consumer calls. Nothing may re-derive blocking from this tuple: measured
# 2026-08-17 on the real extract, doing so stops 30,583 of the 138,007 claims
# where the rule stops 4,609.
GATE_REJECTIONS = (GATE_UNREACHABLE, GATE_INCOHERENT, GATE_LOW_SUPPORT)

# What a gated claim turns out to be. ABSENCE and CONTRADICTION are not the same
# thing and conflating them is the error the operator corrected twice: a sample
# can legitimately hold more than one assay, typically the one that produced it
# and the one that consumed it, so a claim naming an assay the sample lacks is
# an absence until something shows otherwise. CLS_ALT_LABEL is the second
# correction: where a well-supported population NEVER co-registers the pair, the
# two are alternative labels a curator chooses between -- 145 D.IMG samples sit
# in Histopathology and 1,907 never hold it together with Tissue Imaging -- and
# that is not an error either. CLS_UNRESOLVED is reported at its own size rather
# than banded into a mode; silently absorbing what the pipeline cannot classify
# is how a bucket ends up named for what someone assumed was in it.
#
# CLS_UNREACHABLE IS A FIFTH CLASS AND NOT A REFUSAL. `gate.type_registration_index`
# calls a (type, assay) pair absent from it incredible whatever the term's
# support, and `gate.gate_claims` already BLOCKS a claim on one -- but a lineage
# neighbour carries no claim, so until 2026-08-21 nothing put the lineage lane in
# front of that rule. Measured on the 2026-08-21 artifact tree, 99,449 of the
# 167,454 emitted MODE_2 rows read `type_registrations == 0`. They are CLASSED
# here rather than dropped: every one is still emitted, carrying
# GATE_UNREACHABLE, because a proposal that vanishes reads to a curator exactly
# like one that was never generated.
#
# CLS_BOOTSTRAP IS A CUT THROUGH CLS_UNREACHABLE AND NOT A SIXTH POPULATION.
# An unreachable pair is a claim that the house has a systematic gap, and that
# claim is not automatically false: 47 unreachable cohorts were approved by
# agents reading the biology, and the assay-143 name-collision finding turned on
# one of them being right. What separates the two readings is HOW HEAVILY THE
# PROPOSED ASSAY IS USED. Proposing a D.FLOW into Tissue Collection (74) is a
# type error -- 89,263 samples are registered there and not one is a D.FLOW, so
# the absence is the house's answer, and 24,470 of the 99,449 rows are that one
# assay. Proposing a type into an assay holding 12 samples in total is a new
# assay finding its feet. `mode2.BOOTSTRAP_POPULATION_FLOOR` is where the line
# is drawn and why; measured on the 2026-08-21 artifact tree, 8,971 of the
# 99,449 fall under it, over 116 (sample type, assay) pairs and 50 assays.
#
# THE ROW IS UNCHANGED EXCEPT FOR THIS CELL. A bootstrap row still carries
# `GATE_UNREACHABLE`, still carries its direction and its precedent rate, and is
# still emitted -- so every block that reads the gate still holds and the review
# surface splits on the class alone.
CLS_ABSENCE_LINEAGE = "CLS_ABSENCE_LINEAGE"   # a neighbour already carries it
CLS_ABSENCE_COMPAT = "CLS_ABSENCE_COMPAT"     # no neighbour, but the pair coexists
CLS_ALT_LABEL = "CLS_ALT_LABEL"               # the pair never coexists
CLS_UNRESOLVED = "CLS_UNRESOLVED"             # neither test settles it
CLS_UNREACHABLE = "CLS_UNREACHABLE"           # no sample of this type is ever
                                              # registered in this assay
CLS_BOOTSTRAP = "CLS_BOOTSTRAP"               # ...and the assay is barely used
                                              # at all, so the gap may be real
CLASSES = (CLS_ABSENCE_LINEAGE, CLS_ABSENCE_COMPAT, CLS_ALT_LABEL,
           CLS_UNRESOLVED, CLS_UNREACHABLE, CLS_BOOTSTRAP)

# Which lineage neighbour carries the claimed assay, over DERIVED_FROM. Stated
# once and binding: precedent is mined over DERIVED_FROM, so a lineage test run
# over CHILD_OF would ask about a different graph than the one its own evidence
# was measured on -- 52,185 edges apart, about 9% of every Mode 2 figure.
LIN_CHILD = "LIN_CHILD"      # a CHILD registers it -> propose adding the PARENT
LIN_PARENT = "LIN_PARENT"    # a PARENT registers it -> propose adding the CHILD
LIN_NONE = "LIN_NONE"
LINEAGE_RELATIONS = (LIN_CHILD, LIN_PARENT, LIN_NONE)

# How often two assays coexist on samples of one type. BAND_NO_SUPPORT is a
# separate outcome from BAND_NEVER on purpose and the distinction is the whole
# value of the band: a rate of 0.000 over four samples is noise, and reporting
# it as "these never coexist" would manufacture an alternative-label finding out
# of an empty population.
BAND_NEVER = "BAND_NEVER"
BAND_SOMETIMES = "BAND_SOMETIMES"
BAND_ROUTINE = "BAND_ROUTINE"
BAND_NO_SUPPORT = "BAND_NO_SUPPORT"
COMPAT_BANDS = (BAND_NEVER, BAND_SOMETIMES, BAND_ROUTINE, BAND_NO_SUPPORT)

# BOTH NUMBERS BELOW ARE REPORTING BANDS AND NEITHER IS A TUNED THRESHOLD.
# There is no backtest behind either one and neither gates anything. Under the
# binding constraint -- nothing decides, everything proposes -- a threshold
# cannot gate a write because there is no autonomous write to gate: every row in
# all three modes reaches the operator as a proposal they approve or reject.
# These two order what that operator reads first. Task 7 emits the Mode 2
# backtest curves, and a curve sets reading order, not permission; if a later
# reader finds a `>=` on either of these deciding whether a row is PROPOSED
# rather than merely how it is BANDED, that is the defect, not the number.
#
# THE ONE APPROVED READER IS `compatibility.compat_band`, which maps a measured
# rate onto `COMPAT_BANDS` and nothing else. `MIN_CO_REG_SUPPORT` decides only
# whether an unread rate is labelled BAND_NO_SUPPORT instead of BAND_NEVER, and
# `CO_OCCUR_BAND` separates two bands that are BOTH reported. BAND_NEVER, which
# carries the alternative-label finding, rests on a rate of exactly 0.0 and has
# no tuned number in it at all, so no recalibration can create or destroy one.
# `test_the_two_reporting_numbers_gate_nothing` pins the reader by name and
# fails again on a second one.
MIN_CO_REG_SUPPORT = 30     # samples of the type, below which a rate is unread
CO_OCCUR_BAND = 0.5         # the routinely / sometimes boundary


def make_fixture() -> dict[str, pd.DataFrame]:
    """A seven-edge synthetic world for the precedent, gate and classify stages.

    assay 1 "Comet Chip"        project 10, propagating   (D.IMG -> TIS)
    assay 2 "Tissue Collection" project 10, non-propagating
    assay 3 "Patient Visit"     project 10, the producing side of the domain rule

    samples: 100/101 D.IMG children, 200/201 TIS parents,
             300/301 dark children, 400 dark parent, 700 a two-assay PAV parent

    Branches this data DOES reach:
      CLEAN             100 -> 200 and 101 -> 201, both endpoints co-registered
                        in Comet Chip; plus the 203 -> 500 TIS -> MUS hop, whose
                        precedent does not propagate
      MODE_1_CHILD      300 -> 200, child registered nowhere
      MODE_1_BOTH_DARK  301 -> 400, neither endpoint registered
      MODE_2_PROPAGATE  102 -> 202, child in Comet Chip and parent only in
                        Tissue Collection, on a hop whose precedent propagates

    Added 2026-08-17 for the gate and the two Mode 2 directions:

      the domain rule    203 -> 700. A sample can legitimately hold more than
                         one assay, typically the one that PRODUCED it and the
                         one that CONSUMED it: PAV 700 sits in 3 Patient Visit,
                         which produced it, and in 2 Tissue Collection, which
                         consumed it to make TIS 203. Neither registration is
                         wrong and neither excludes the other. Increment 1's
                         code could represent this nowhere, which is why every
                         absence read as a contradiction.
      LIN_PARENT alone   the same hop. Every OTHER Mode-2-eligible hop here
                         reaches both directions at once, so a classifier
                         keying direction off "the edge is disjoint" rather
                         than off the assay was indistinguishable from a
                         correct one. TIS -> PAV reaches A_ADD_CHILD only, and
                         A_ADD_CHILD is the measured-weak direction.
      the gate           `vocabulary` plus four samples, one claim per
                         rejection kind, each arranged so exactly ONE test
                         rejects it -- a claim failing two tests at once cannot
                         show which caught it, which is how 24 vocabulary
                         defects were filed as lineage absences:
                           301 `Type: CometChip`       -> GATE_UNREACHABLE, DNA
                                                          is registered nowhere
                           202 `Software: cometchip`   -> GATE_INCOHERENT
                           203 `Type: rare term`       -> GATE_LOW_SUPPORT, count
                           203 `DataType: illumina library`
                                                       -> GATE_LOW_SUPPORT, purity
                           202 `Instrument: curator call`
                                                       -> GATE_PASS despite
                                                          support 0, because a
                                                          curator ruling outranks
                                                          the data. 202 therefore
                                                          also proves the gate is
                                                          per CLAIM, not per
                                                          sample.
                           700 `Instrument: tissue scope`
                                                       -> GATE_PASS on an assay
                                                          700 already holds, so
                                                          a mode drops it for a
                                                          reason that is not the
                                                          gate.
                         Every claim above names an assay its sample does NOT
                         already hold. Without that the gate cases would be
                         shadowed: a claim naming an assay the sample already
                         holds yields no proposal whether the gate works or not.

    Branches this data does NOT reach:
      MODE_1_PARENT     no edge pairs a registered child with a wholly dark
                        parent. 102 -> 202 is not this case: its parent is
                        registered, just in a different assay, which is mode 2.
      MODE_2_AMBIGUOUS  no CHILD is registered in 2+ assays, so no stage-D
                        tiebreak can fire here. Proving the tiebreak works needs
                        a fixture of its own; a tiebreak that never fires is
                        indistinguishable from a correct one. (700 holds two
                        assays, but only ever as a parent.)
      MODE_3_FLAG       nothing in this world produces it, and Mode 3 has no
                        detector to produce it with.

    The 2026-08-14 rows are frozen and the 2026-08-17 additions were chosen not
    to disturb them: no existing sample, membership row, hop or assay changed,
    and the D.IMG -> TIS / Comet Chip arithmetic every later stage hand-traces
    (n_both=2, n_child_only=1, n_parent_only=0, so propagation_rate=2/3 against
    reverse_rate=1.0) is untouched. Those two rates DIFFER, which is what stops
    a Mode 2 test from passing under a direction swap.
    tests/test_assay_hygiene_schema.py pins all of it, including the branches
    this world does not reach, so the data and this docstring cannot drift.
    """
    edges = pd.DataFrame(
        [
            # both registered in Comet Chip -> establishes propagation precedent
            (100, 200, "D.IMG-1", "TIS-1", "D.IMG", "TIS", 1, "Comet Chip", None),
            (101, 201, "D.IMG-2", "TIS-2", "D.IMG", "TIS", 1, "Comet Chip", None),
            # child in Comet Chip, parent only in Tissue Collection -> dark, mode 2
            (102, 202, "D.IMG-3", "TIS-3", "D.IMG", "TIS", None, None, None),
            # TIS -> MUS where precedent says it does not propagate -> CLEAN
            (203, 500, "TIS-4", "MUS-1", "TIS", "MUS", None, None, None),
            # child registered nowhere -> mode 1 child
            (300, 200, "DNA-1", "TIS-1", "DNA", "TIS", None, None, None),
            # neither endpoint registered -> mode 1 both dark
            (301, 400, "DNA-2", "TIS-9", "DNA", "TIS", None, None, None),
            # the domain rule: 700 produced 203, and holds both assays
            (203, 700, "TIS-4", "PAV-1", "TIS", "PAV", None, None, None),
        ],
        columns=EDGE_COLUMNS,
    )
    membership = pd.DataFrame(
        [
            (100, 1), (200, 1),          # both in Comet Chip
            (101, 1), (201, 1),          # both in Comet Chip
            (102, 1), (202, 2),          # disjoint -> the mode 2 case
            (203, 2), (500, 1),          # disjoint, but hop does not propagate
            (200, 2), (201, 2),          # parents also in Tissue Collection
            (700, 2), (700, 3),          # produced by 3, consumed by 2
        ],
        columns=MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (2, "Tissue Collection", 8, 3, 2, 10, "MIT_SRP", 12, "Tissue Collection"),
            (3, "Patient Visit", 9, 3, 2, 10, "MIT_SRP", 13, "Patient Visit"),
        ],
        columns=ASSAY_COLUMNS,
    )
    # One sample per claim tier, so every branch of claims.sample_claims has a
    # case here. assay 1 is "Comet Chip" (internal 11), assay 2 is
    # "Tissue Collection" (internal 12); tests build an explicit vocabulary
    # rather than learning one, so these raw values map wherever a test says.
    samples = pd.DataFrame(
        [
            # strong AND weak agree -> corroborated
            (100, "D.IMG-1",
             '{"Type": "CometChip", "Protocol": "comet.docx", "Name": "img1"}',
             None, "10"),
            # strong only -> strong
            (101, "D.IMG-2", '{"Type": "CometChip", "Name": "img2"}', None, "10"),
            # weak only -> weak
            (102, "D.IMG-3", '{"Protocol": "comet.docx", "Name": "img3"}', None, "10"),
            # two strong fields naming different assays -> conflict
            (200, "TIS-1",
             '{"Type": "CometChip", "Instrument": "tissue scope"}', None, "10"),
            # nothing that names an assay -> none
            (300, "DNA-1", '{"Protocol": "/sops/9", "Name": "dna1"}', None, "10"),
            # --- one claim per gate rejection, added 2026-08-17 ---
            #
            # EVERY claim below names an assay its sample does NOT already
            # hold, and every one except 301's is REACHABLE for its type. That
            # is deliberate and it is not free: 202 and 203 are the only samples
            # here with room for it, because a claim naming an assay the sample
            # already holds produces no proposal for a reason that has nothing
            # to do with the gate, and a gate regression test written on such a
            # claim passes whether or not the gate works.
            #
            # DNA is registered in NO assay, so any DNA claim is unreachable.
            # `CometChip` is the SAME term that passes for D.IMG, which is what
            # makes this an incredible CLAIM rather than an unknown term. Being
            # registered nowhere, 301 is also Mode 1's population: the gate has
            # to stop this becoming a Mode 1 proposal.
            (301, "DNA-2", '{"Type": "CometChip", "Name": "dna2"}', None, "10"),
            # 202 is a TIS in Tissue Collection only. Both claims name Comet
            # Chip, which TIS samples do hold and 202 does not; one is rejected
            # for its term family and the other must pass on provenance alone,
            # so the gate is forced to be per CLAIM and not per sample.
            (202, "TIS-3",
             '{"Software": "cometchip", "Instrument": "curator call"}',
             None, "10"),
            # 203, likewise, carries the two floor cases: a term with almost no
            # support, and `illumina library`, which is the real one -- purity
            # 0.707 over 2,210 samples, and it produced 212 of the 250 compat
            # flags on its own.
            (203, "TIS-4",
             '{"Type": "rare term", "DataType": "illumina library"}',
             None, "10"),
            # already registered in what it claims: a proposal this sample does
            # not need, and it must be dropped for THAT reason and not by the
            # gate, which passes the claim.
            (700, "PAV-1", '{"Instrument": "tissue scope"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
    # Explicit, not learned. Every value is already normalised, because
    # `normalise_value` is what each lookup goes through and a row spelled
    # `CometChip` would match nothing.
    vocabulary = pd.DataFrame(
        [
            # passes every test, for D.IMG
            ("Type", "cometchip", 11, "Comet Chip", 900, 850, 0.99, P_LEARNED),
            ("Protocol", "comet.docx", 11, "Comet Chip", 400, 380, 0.95, P_LEARNED),
            ("Instrument", "tissue scope", 12, "Tissue Collection",
             50, 50, 1.0, P_LEARNED),
            # an INCOHERENT family: one field, one leading token, two assays.
            # The real one is flowjo -> 30 / 31 / 31 / 153, one product split
            # across four assays with nothing checking that it maps coherently.
            # Both members clear every floor, so only the family can reject them.
            ("Software", "cometchip", 11, "Comet Chip", 120, 40, 0.98, P_LEARNED),
            ("Software", "cometchip v2", 12, "Tissue Collection",
             90, 30, 0.97, P_LEARNED),
            # under the purity floor, and well over the support one
            ("DataType", "illumina library", 11, "Comet Chip",
             2210, 2210, 0.707, P_LEARNED),
            # under the support floor, and at full purity
            ("Type", "rare term", 11, "Comet Chip", 2, 1, 1.0, P_LEARNED),
            # under BOTH floors and gated out by neither: a human decision
            # outranks the data, whatever its support
            ("Instrument", "curator call", 11, "Comet Chip",
             0, 0, 0.0, P_CURATOR),
            # the NEGATIVE case for stem extraction: same field, different
            # products, different assays, sharing a substring but not a leading
            # token. A substring rule collapses these and reports a family that
            # is not one; the incoherent pair above must still collapse.
            ("DataType", "chip seq", 12, "Tissue Collection",
             300, 210, 0.96, P_LEARNED),
            ("DataType", "chipper", 11, "Comet Chip", 250, 180, 0.95, P_LEARNED),
        ],
        columns=VOCAB_COLUMNS,
    )
    return {"edges": edges, "membership": membership, "assays": assays,
            "samples": samples, "vocabulary": vocabulary}


def make_stage0_fixture() -> dict[str, pd.DataFrame]:
    """A synthetic world for stage 0, separate from make_fixture().

    make_fixture()'s rows are frozen because the companion plan hand-traces
    counts off them. Stage 0 needs different shapes (parent tokens, a node
    index, an AB-prefixed token), so it gets its own data rather than growing
    that one.

    parents: six declared tokens off three children, one per outcome
      D.IMG-1 / TIS-1        keeper, both endpoints share assay 1 -> labelled
      D.IMG-1 / AB-1         keeper, AB-prefixed, valid ONLY under the fix
      D.IMG-1 / not-a-uid    dropped, D_NOT_UID
      D.IMG-2 / TIS-9        dropped, D_NO_NODE (no such node)
      D.IMG-2 / D.IMG-2      dropped, D_SELF_LOOP
      D.IMG-3 / TIS-3        dropped, D_ALREADY_EXISTS
    """
    parents = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", "Parent", "TIS-260101ABC-1"),
            ("D.IMG-260101ABC-1", "AntibodyParent", "AB-260101ABC-1"),
            ("D.IMG-260101ABC-1", "Parent", "some free text"),
            ("D.IMG-260101ABC-2", "Parent", "TIS-260101ABC-9"),
            ("D.IMG-260101ABC-2", "Parent", "D.IMG-260101ABC-2"),
            ("D.IMG-260101ABC-3", "Parent", "TIS-260101ABC-3"),
        ],
        columns=PARENT_COLUMNS,
    )
    # the graph's node index: uuid -> (id, type). TIS-...-9 is deliberately absent.
    nodes = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", 100, "D.IMG"),
            ("D.IMG-260101ABC-2", 101, "D.IMG"),
            ("D.IMG-260101ABC-3", 102, "D.IMG"),
            ("TIS-260101ABC-1", 200, "TIS"),
            ("TIS-260101ABC-3", 202, "TIS"),
            ("AB-260101ABC-1", 300, "AB"),
        ],
        columns=NODES_COLUMNS,
    )
    # D.IMG-3 -> TIS-3 already exists, so it must be dropped as ALREADY_EXISTS
    existing = pd.DataFrame(
        [("D.IMG-260101ABC-3", "TIS-260101ABC-3")],
        columns=["child_uuid", "parent_uuid"],
    )
    membership = pd.DataFrame(
        [
            (100, 1), (200, 1),   # D.IMG-1 and TIS-1 share assay 1 -> labelled
            (300, 2),             # AB-1 is in assay 2 only -> disjoint, dark
        ],
        columns=MEMBERSHIP_COLUMNS,
    )
    assays = pd.DataFrame(
        [
            (1, "Comet Chip", 7, 3, 2, 10, "MIT_SRP", 11, "Comet Chip"),
            (2, "Antibody Panel", 8, 3, 2, 10, "MIT_SRP", None, None),
        ],
        columns=ASSAY_COLUMNS,
    )
    samples = pd.DataFrame(
        [
            (100, "D.IMG-260101ABC-1",
             '{"Protocol": "http://x/sops/5", "Parent": "TIS-260101ABC-1"}', None, "10"),
            (101, "D.IMG-260101ABC-2", '{"Protocol": ""}', None, "10"),
            (102, "D.IMG-260101ABC-3", '{"Protocol": "http://x/sops/5"}', None, "10"),
        ],
        columns=SAMPLE_COLUMNS,
    )
    sops = pd.DataFrame([(5, "Comet Chip SOP")], columns=["sop_id", "title"])
    childof = pd.DataFrame(
        [
            ("D.IMG-260101ABC-1", "TIS-260101ABC-1"),
            # declared by nobody: the stale case reconciliation must surface
            ("D.IMG-260101ABC-1", "TIS-260101ABC-77"),
        ],
        columns=CHILDOF_COLUMNS,
    )
    return {
        "parents": parents, "nodes": nodes, "existing": existing,
        "membership": membership, "assays": assays, "samples": samples,
        "sops": sops, "childof": childof,
    }
