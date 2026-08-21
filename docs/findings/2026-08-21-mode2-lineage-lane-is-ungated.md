# Mode 2's lineage lane never sees the reachability gate

**Found 2026-08-21 by the operator, reading a rejected cohort and asking why it
was ever proposed: "why would mode 2 propose that we have patient visit as an
assay for the Tissue? PAV is NHP -> PAV and Tissue collection is PAV -> TIS ...
I think the issue with a lot of these rejects is that these are false rows
identified in the mode 2 code."**

He is right, and the gate that should have stopped them already exists.

## The rule, and where it is enforced

`gate.type_registration_index` maps `(sample_type, internal_assay_id)` to the
number of samples of that type the house holds in that assay. Its own docstring:

> A claim naming a pair absent from this index is naming an assay no sample of
> its type has ever been registered in, anywhere in the database, which makes
> the claim INCREDIBLE whatever the term's support.

For a CLAIM that is `GATE_UNREACHABLE` and it BLOCKS.

    MODE_1  claim-driven,   gated       1,373 rows |     0 with type_registrations == 0
    MODE_2  lineage-driven, NOT gated 167,454 rows | 99,449 with type_registrations == 0  (59.4%)

166,586 of the 167,454 Mode 2 rows carry no gate outcome at all. The lineage
lane raises a proposal from a neighbour's membership, and a lineage-only row has
no claim, so nothing ever puts it in front of the gate.

`mode2.py` COMPUTES `type_registrations` and emits it as a column. It never
tests it. The evidence is gathered, printed, and ignored.

## What that generates

99,449 rows across 476 distinct (type, assay) pairs propose a registration the
house has NEVER made for that sample type. The largest:

    TIS   -> Chemical challenge                     10,745 rows | 0 TIS ever    (assay has    949)
    D.IMG -> Organ-on-a-Chip Device Fabrication      7,580 rows | 0 D.IMG ever  (assay has    722)
    D.FLOW-> Tissue Collection                       7,197 rows | 0 D.FLOW ever (assay has 89,263)
    D.IMG -> Tissue Collection                       6,276 rows | 0 D.IMG ever  (assay has 89,263)
    BAC   -> Tissue Collection                       3,297 rows | 0 BAC ever    (assay has 89,263)
    BAC   -> Short Read Sequencing                   2,592 rows | 0 BAC ever    (assay has 11,250)

Mode 2 proposed registering flow-cytometry data files as "Tissue Collection"
7,197 times, against 89,263 existing Tissue Collection members of which not one
is a D.FLOW.

The operator's own example is the milder version of the same shape: `TIS ->
Patient Visit`, 24,050 rows, where a tissue is proposed for the assay describing
the visit it was collected at. There the house has 178 such rows out of 13,220,
so it is not literally unprecedented -- it is 1.3%, which the gate's floor
machinery is built to judge and never got the chance to.

## What it cost

The 15 agents in the full run did the gate's job by hand. Of the cohorts drawn
from those 99,449 rows they returned:

    REJECT 650 | WRONG_ASSAY 84 | APPROVE 47 | UNSURE 18

650 cohort-level rejections that a one-line reachability test would have
prevented ever being generated, reviewed or rendered.

## The fix, and the one reason not to make it absolute

Apply the reachability test to the lineage lane as the gate already applies it
to claims. That removes 99,449 of 167,454 rows -- 59.4% -- before review.

BUT 47 cohorts at `type_registrations == 0` were APPROVED by agents reading the
biology, and at least one such claim has already proved correct this week: the
`gpt delta` finding turned on a registration the house had never made being
right. So an unreachable pair is not automatically wrong; it is a claim that
the house has a systematic gap.

Recommended shape, matching how the package already treats claims: emit
`GATE_UNREACHABLE` on the lineage lane so it BLOCKS by default and is visible as
a gate outcome rather than a silent absence, and let a curator override it
deliberately. That keeps the 47 reachable by a human decision instead of by
default.

NOT IMPLEMENTED. This is a change to detection, it moves 59% of the Mode 2
population, and every figure in the review artifacts would need re-measuring
after it.
