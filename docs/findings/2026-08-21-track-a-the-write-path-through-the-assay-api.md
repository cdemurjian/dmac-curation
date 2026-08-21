# Track A: the write path through the assay API

**2026-08-21. Read-only.** Nothing in this investigation wrote to any database.
Source read on `fairdata-dev` at
`/home/service-account/Documents/Programs/NExtSEEK`; spec read at
`~/code/dmac/docker/dev/chat_nextseek/src/chat_nextseek/context/nextseek_api.yaml`;
row figures re-derived from `assay-hygiene-bak/extract/`.

**Decision this supports:** the operator has chosen the NExtSEEK API endpoint
over `batch_upload`'s `smart_merge_assay_assets` for writing assay memberships.
This records what that route actually does, what it costs, and the one question
still open.

---

## 1. The assay PATCH is the only route

`PATCH /nextseek_api/assays/{uid}/`, with `data.relationships.samples`.

All 25 paths in the OpenAPI spec were checked. Samples carry no `assays`
relationship anywhere, and there is no JSON:API `/relationships/samples`
sub-resource. Membership can only be written **from the assay side**. There is
no per-sample write through this API.

The endpoint's own description says "Add additional samples to the flow
cytometry experiment", which hints at additive behaviour. Section 4 explains why
that hint cannot be relied on and why it does not matter.

## 2. NExtSEEK is a thin proxy on both sides

`AssayProxyViewSet.retrieve` (`nextseek_api/services/assays.py:109`) and
`.partial_update` (`:196`) both validate the payload shape, forward to SEEK via
`self.client`, and return the upstream body verbatim. Neither paginates,
merges, reorders or post-processes anything.

**Therefore the replace-vs-append semantics belong to SEEK upstream, not to any
code in this repository.** No amount of reading NExtSEEK will settle them.

## 3. The one NExtSEEK-side hazard is absent

`AssayUpdateRequest.to_seek_payload` (`nextseek_api/models.py:1288`):

```python
if self.data.relationships is not None:
    payload['data']['relationships'] = self.data.relationships.model_dump(exclude_none=True)
```

`exclude_none=True` means an omitted `samples` is **genuinely omitted** from the
forwarded payload rather than serialised as `[]`. A title-only PATCH cannot wipe
membership.

This was worth checking specifically. `AssayPatchRelationships.samples` is
declared `Optional[MultipleReferences] = None`; had the dump not excluded
`None`, every unrelated attribute edit would have emptied the assay's sample
list. It does exclude it. This hazard does not exist.

## 4. No test on the box covers SEEK's behaviour

Every test in `nextseek_api/tests/test_services_assays.py` mocks the client:

```python
with patch.object(AssayProxyViewSet, "client") as mc:
```

They exercise the proxy's plumbing — id injection, id mismatch, 404 fallback,
auth failure, HTML upstream, invalid upstream — and never SEEK's relationship
semantics. Nothing in the repository asserts what a PATCH does to an existing
sample list.

## 5. The blast radius, measured

Under replace semantics the complete-list unit changes, and that is the whole
reason this matters:

| path | complete-list unit | worst case per call |
|---|---|---|
| `smart_merge_assay_assets` (batch upload) | per **sample** | that sample loses its other assays — a handful |
| `PATCH /assays/{uid}/` | per **assay** | that assay loses every other sample |

Measured against the real extract (`assay-hygiene-bak/extract/membership.parquet`):

- 173 SEEK assay records hold members. The largest holds **48,440** samples
  (seek id 8, Tissue Collection in IMPAcTb).
- **Mode 1's already-approved 1,371 rows** would PATCH **16** SEEK records
  holding **156,082** existing memberships between them. The largest single
  payload resends **48,440** sample references in order to add a handful.
- **All 170,786 rows** would PATCH **159** records, putting **213,905**
  existing memberships through a replace.

Top targets by what a truncated read would destroy:

| seek assay_id | current members |
|---|---|
| 8 | 48,440 |
| 9 | 39,008 |
| 17 | 17,625 |
| 16 | 15,127 |
| 19 | 9,188 |
| 56 | 8,834 |
| 22 | 8,300 |
| 18 | 5,600 |

For this particular job the API route carries roughly **100× the blast radius**
of the per-sample batch path — *if* PATCH replaces.

## 6. The reframing: replace-vs-append does not matter

If the writer always sends `existing ∪ additions`, that payload is **correct
under both semantics**:

- under *replace*, the sent set becomes the membership — which is the union, correct;
- under *append*, the sent set is merged into the membership — which is the union, correct.

So the destructive probe is unnecessary and will not be run. The writer is built
to be right either way.

## 7. What actually matters, and it is a pure read

**Does `GET` return the complete `samples` array?**

Under replace semantics a truncated read makes the union short, and the PATCH
silently deletes the difference. That is the entire remaining risk. It is
answerable with one read and no write.

The assays *list* endpoint paginates — the spec's own example shows
`self: /assays?page[number]=1&page[size]=100`. Whether the single-resource GET
truncates its `samples` relationship the same way is not stated anywhere in the
spec, `capabilities.md`, or the enriched endpoint notes, and NExtSEEK passes the
body through without touching it.

The check, from the box (`ssh service-dev`; nginx is on `127.0.0.1:8000`):

```bash
curl -s -u '<seek-user>' http://127.0.0.1:8000/nextseek_api/assays/8/ \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['data']['relationships']['samples']['data']))"
```

- **48440** → GET is complete, and the writer design in §8 is safe.
- **anything smaller, especially a round 100** → it paginates, and read-then-union
  becomes the most dangerous operation in this project. The writer would then
  need SEEK's paginated relationship traversal, or the batch path's smaller
  blast radius becomes preferable despite the operator's preference.

**Not yet run.** Attempting to determine which credential keys existed in the dev
environment files was blocked by the permission classifier — correctly, since it
reads as secret harvesting — and was not worked around. This needs either a
credential the operator is comfortable providing or the operator running the
read.

## 8. Writer design that follows from all of the above

1. **Group additions by target SEEK assay record**, not by sample. One PATCH per
   assay; 16 calls for Mode 1, 159 for the full population.
2. **GET the assay first** and read its current `samples` set. Assert the
   returned count against the extract's known membership count for that record
   before proceeding; **halt on any mismatch**, because a mismatch is either
   pagination or drift and both invalidate the union.
3. **Send `existing ∪ additions`**, always, never additions alone — correct
   under both semantics (§6).
4. **Post-condition on every call**: re-GET and assert the resulting set is a
   superset of the prior set. Halt the entire run on any shrink. The first wrong
   assumption then stops the campaign instead of compounding through 159 assays.
5. **Dry-run mode first**, emitting the exact payload and a per-assay diff
   (`n_before`, `n_after`, `n_added`, `n_lost`) for operator review, with
   `n_lost > 0` anywhere aborting before a single write.
6. **Stage smallest assay first.** Order the campaign ascending by current
   membership so the first real write risks the least.

## 9. Open questions

- **GET completeness** (§7). Blocking. Pure read.
- **Whether SEEK enforces a payload size limit** on a 48,440-reference PATCH.
  Unknown; would surface as a failed write rather than a silent loss, but should
  be probed on the smallest assay first regardless.
- **The 573 rows whose internal id maps to two SEEK records in the sample's own
  project** (from the detection audit). No rule in any artifact chooses between
  them; they must not enter a write campaign until a curator or a rule does.
