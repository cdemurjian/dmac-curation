---
description: Author the protocol .docx set from the manuscript Methods and register it as SOPs (Phase 3b)
---

The user wants Phase 3b: turn the manuscript's Materials and Methods into the
protocol documents that the sample tree's assays reference, and register them on
NExtSEEK as SOP records.

Runs **after `/curate-sample-tree`**, because the tree is what tells you which
assays need documenting, and **before `/curate-build`**, because the `Protocol`
column of every upload row carries a SOP title that has to exist first.

Parse `$ARGUMENTS`: optional `--project-id N` (needed only to register), optional
`--only <topic>` to rebuild a single protocol.

## Prereqs

- `./sample_tree.json` and `./SAMPLE_TREE.md` exist (run `/curate-sample-tree` first)
- `./manuscript/` non-empty
- `./.env` with `NEXTSEEK_USERNAME` / `NEXTSEEK_PASSWORD` (only needed for registration)

## Stop here if the study has no Methods text

**An in-prep study with no written Methods gets no protocol files.** Do not
write placeholder documents. A `*** PLACEHOLDER ***` marker is right in a
spreadsheet cell, where QA greps for it and a curator fills it in; it is wrong in
a SOP, which gets registered on a shared server, cited by row after row, and
emailed to a PI as if it described a real procedure. A stub protocol is worse
than a missing one because it looks answered.

So when `manuscript/` carries no Methods section and the PI has supplied no
protocol documents:

1. Run the coverage half anyway. `build_protocols.py --coverage-only` with no
   manifest is not possible, so instead list each edge in `sample_tree.json` and
   the assay that licenses it, and report which have no protocol. That list is
   the deliverable.
2. Add one question per uncovered assay to `QUESTIONS_FOR_PI.md` via
   `/curate-questions add`, naming the assay and the edge it licenses.
3. Tell the user the phase is deferred, and that re-running it once Methods text
   or PI-supplied protocol documents land will pick up where it stopped.
4. Do **not** create `protocols/`. Phase 5 can proceed with a blank `Protocol`
   column; a directory of empty documents helps nobody.

## Steps

1. **Read the whole Methods**, main text AND supplement, end to end. Same rule
   as Phase 2: detailed Materials and Methods often sit at the END of a main text
   or only in the SI. Manuscript may be `.pdf` or `.docx`; extract accordingly.

2. **Write `protocols/_methods.json`**, the verbatim excerpts: one entry per
   manuscript section heading, in document order:

   ```json
   [{"heading": "Analysis of confocal microscopy images",
     "paras": ["Using 3D images of actin, CT-FIRE was used to…", "…"]}]
   ```

   This file is a **transcription, not a summary**. Copy the paragraphs; change
   nothing. If a PDF extraction leaves artifacts (line-break hyphens, the
   journal's `MFP- 3D` mid-line compound style, floated display equations that
   land inside the wrong paragraph), repair them and say so. Write a small
   extraction script next to the project's other `scripts/` so the transcription
   is reproducible rather than hand-typed. Mark any entry that is genuinely not a
   byte-for-byte copy with `"verbatim": false`; transcribed equations are the
   usual case, and the build's verbatim check exempts exactly those.

3. **Write `protocols/_manifest.json`**, the mapping, and the only file where
   judgment lives. Group the sections into topics, and name the assay each topic
   documents:

   ```json
   {"lab": "SHE", "stamp": "260807", "version": 1,
    "study": "Oak et al., Sci. Adv. 11, eadq0638 (2025)",
    "doi": "10.1126/sciadv.adq0638",
    "protocols": [
      {"topic": "ConfocalImageAnalysis",
       "headings": ["Analysis of confocal microscopy images"],
       "assays": ["Imaging Analysis"],
       "note": "Describes D.IMG→A.IMG, the tier documented at count=0."}
    ]}
   ```

   - `lab` and `stamp` come from the lockfile and the batch you are curating:
     the same `<LAB>` and `YYMMDD` the UIDs use.
   - `assays` must be the **exact** assay titles used on the tree's edges,
     `- Metadata` and `- Data Linked` suffixes included. They are how the
     coverage tables join protocols to edges; a near-miss silently reports the
     edge as uncovered.
   - `note` is per-protocol prose carried into Table A. Use it for the scope
     decisions a reviewer would otherwise have to reconstruct.

4. **Render:**

   ```bash
   uv run --script <PLUGIN>/scripts/build_protocols.py
   ```

   Writes one `P.<LAB>-<STAMP>-V<n>_<Topic>.docx` per manifest entry plus
   `protocols/COVERAGE.md`. Read every line of its output. It fails loudly on a
   heading the manifest wants but the methods file lacks, on a section consumed
   more or fewer times than it occurs, and on any body paragraph that did not
   round-trip verbatim. Fix the JSON and re-run rather than editing a document by
   hand. Add `--force` to rewrite documents that already exist, `--only <topic>`
   for one, `--coverage-only` to refresh the tables alone.

5. **Write `protocols/README.md`** from `<PLUGIN>/templates/PROTOCOLS.md.j2`.
   This is the narrative half: naming convention, provenance, how the extraction is
   reproduced, and the open items the coverage tables surfaced. Link to
   `COVERAGE.md` rather than restating it.

6. **Register the SOPs (needs `--project-id`, and needs the user to say yes).**
   Registration is a separate decision from authoring. Do it in three steps, in
   this order, and never collapse them:

   a. **Preview.** The command writes nothing without `--write`:

      ```bash
      uv run --script <PLUGIN>/scripts/upload_sops.py --project-id N
      ```

   b. **Ask.** Show the user the preview output, then put the decision to them
      with `AskUserQuestion`: name the **server** it will write to, the
      **project id**, and **how many records** would be created. Offer at least
      "register all N", "register none, keep the files local", and let them pick
      a subset with `--only`. Wait for a clear answer. Silence, "sounds good" to
      a different question, or a general "run phase 3b" is **not** approval to
      upload.

   c. **Write, only after a yes:**

      ```bash
      uv run --script <PLUGIN>/scripts/upload_sops.py --project-id N --write --confirmed
      ```

   `--write` alone is REFUSED by the script before it makes any network call.
   `--confirmed` is your assertion that a human saw the preview and approved it,
   so pass it only when that actually happened in this conversation.

7. **Refresh the tables** so Table A carries the new SOP ids:
   `build_protocols.py --coverage-only`.

8. Suggest `/curate-build <arm>`, and remind the user that the `Protocol` column
   takes the **SOP title verbatim**, which is the filename, e.g.
   `P.SHE-260807-V1_AFM.docx`. A SOP has no separate `uid` attribute.

## Behavioral rules

- **A protocol is an excerpt, not a document you write.** The body is the
  manuscript's own Methods prose. No metadata block, no curation notes, no
  "Prepared by", no commentary. Everything you want to say about the protocol
  goes in `COVERAGE.md` or `protocols/README.md`. A PI who opens the `.docx`
  should see their own words and nothing else.
- **Never overwrite a protocol that has already been handed over.** The build
  skips existing files by default and needs `--force` to rewrite one. Before
  passing `--force`, check whether the file was already registered
  (`protocols/_sops.json`) or emailed. If it was, mint a new version by bumping
  `version` in the manifest to `V2`, instead of rewriting `V1` underneath the
  record that cites it.
- **Always author fresh for this batch.** Do not go looking for an existing SOP
  on the server to cite instead. Every curation batch writes its own
  `P.<LAB>-<STAMP>-V<n>_*.docx` set, and `upload_sops.py` skipping a filename it
  already sees is idempotency for re-runs, not reuse of someone else's record.
- **Ask the user before uploading anything to NExtSEEK. Every time.** SOP records
  land in a catalog every curator on the project shares, they are cited by row
  after row, and there is no clean undo. Authoring the documents is safe and
  local; registering them is not, so approval to run this phase is never
  approval to upload. Preview, ask with `AskUserQuestion`, wait for a clear yes,
  and only then pass `--write --confirmed`. The script refuses a bare `--write`
  before it opens a connection, so the gate holds even if this rule is skimmed,
  but do not lean on it: `--confirmed` is a statement about what the human said,
  and asserting it falsely is the failure the flag exists to make visible.
- **A re-run is still an upload.** Resuming a half-finished batch, or registering
  one more protocol with `--only`, needs its own yes. Approval for the first
  batch does not carry to the next one.
- **Two NExtSEEK bugs are already handled; don't "fix" them again.**
  `POST /nextseek_api/sops/` can return HTTP 500 with an HTML body *while
  creating the record*, and it rewrites the submitted title with a
  `<YYMMDD>-V<n>_` prefix. The script verifies against the server rather than the
  response, then `PATCH`es the canonical title. Reported upstream as
  [BioMicroCenter/NExtSEEK#109](https://github.com/BioMicroCenter/NExtSEEK/issues/109).
  If a run looks like it failed, re-run it. The skip list is built from the
  server, so a half-finished batch resumes cleanly.
- **A protocol with no edge is not automatically a mistake.** Study-wide
  statistics and analysis methods for an out-of-scope tier are real methods that
  legitimately match no row. Keep them registered so the record is complete, and
  say why in the `note`.
- **An edge with no protocol IS a gap.** Every assay on the tree should be
  documented by something. Table B is the checklist; work it to zero or explain
  each remainder in `protocols/README.md`.
- `COVERAGE.md` is a build artifact. Never hand-edit it. Change
  `_manifest.json` or `sample_tree.json` and re-run.
