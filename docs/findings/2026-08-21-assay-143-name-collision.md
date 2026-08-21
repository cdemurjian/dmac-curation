# Internal assay 143 is mislabelled: "GPT" was read as the wrong GPT

**Found 2026-08-20 by two independent agent readings during Mode 2 calibration,
confirmed against the extract 2026-08-21.**

## The defect

    seek assay_id 26  title "GPT Assay"            (project 3, MIT_SRP)
      -> internal 143 title "Alanine Aminotransferase (ALT/GPT) Activity Assay"

Someone mapped a SEEK assay named *GPT Assay* onto an internal assay named for
alanine aminotransferase, reading GPT as glutamate-pyruvate transaminase -- the
old clinical name for ALT.

In this lab "GPT" means the ***gpt delta* transgenic rodent mutation assay**, a
genotoxicity assay in which the *gpt* transgene is rescued from genomic DNA and
sequenced. The two share three letters and nothing else.

## The evidence, measured

265 samples are registered under internal 143 (seek 26, 416, 420).

    sample types      D.GPT 145 | TIS 80 | DNA 40
    Type field        "GPT Library"
    Protocol          P.ENG-251216-V1_gpt_delta_assay_LinVo-Dec2025.pdf
                      P.ESS-201123-V1_gpt-NextGen-Protocol-.pdf
                      P.ESS-230308-V2_Duplex-sequencing.docx
    Name field        19-1060_liver_GPTassay, 19-1148_liver_GPTassay, ...

    clearly gpt-delta evidence   185 of 265
    ALT-enzyme evidence only       0 of 265
    neither                       80 of 265  (liver TIS named *_liver_RaDR --
                                              the source tissues whose gDNA went
                                              into the assay)

    samples ANYWHERE in the 163,393-sample extract mentioning
    "aminotransferase" or "transaminase":  0

An ALT activity assay measures an enzyme in SERUM. It does not produce a
sequencing library, does not consume genomic DNA, and does not use a duplex
sequencing protocol. Every signal here is the mutation assay.

## What is NOT wrong

THE MEMBERSHIPS ARE CORRECT AND THE VOCABULARY IS CORRECT. Both learned terms
pointing at 143 are gpt protocol filenames at purity 1.00 over 80 and 40
samples. The system correctly grouped these samples; only the NAME on the group
is wrong. So the fix is a RENAME, not a re-registration, and it moves no
membership row.

## Blast radius

    265  samples already registered under the wrong name
    226  proposed Mode 2 finding rows naming 143
      2  vocabulary terms (both correct mappings)
      3  operator rulings decided partly on the strength of the wrong name

## It reverses three calibration verdicts, in the OPERATOR's favour

Both agent rounds rejected `ENG|DNA|TIS|...ALT/GPT...` and
`ESS|DNA|TIS|...ALT/GPT...` with HIGH confidence, reasoning that an Illumina
library cannot participate in a serum enzyme activity assay. That reasoning is
correct GIVEN THE LABEL and wrong given the assay: the gpt delta assay is
performed ON genomic DNA, so a DNA library is precisely what participates.

The operator approved those cohorts. He was right. The agents were defeated by
the same bad label that misled everything else -- which is the strongest
argument in this document for fixing the name before any further review.

## The fix

Rename internal assay 143 in `dmac.assays_internal_assays`. Nothing else moves.

The name is the house's to choose; the protocol calls it the *gpt delta assay*
and the standard nomenclature is "gpt delta transgenic rodent mutation assay".

NOT DONE HERE. That table is not in this repo and renaming an assay 265 samples
point at is an operator decision, not an agent's.

## Afterwards

Re-run the chain, then re-check the three affected rulings and the 226 proposed
rows against the corrected name.
