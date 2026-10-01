---
description: Review and explicitly create missing project-scoped assays before writing memberships
---

Use this after `/curate-assay-resolve` only when an approved sample/project pair has no
matching assay. Create `04-artifacts/ASSAY-CREATION-PLAN.csv` with the required fields:
`sample_id, project_id, title, study_id, procedure_type, assay_type, rationale`.

Review the plan. The command validates it without side effects unless `--confirm` is present:

```bash
PYTHONPATH=scripts uv run python -m assay_hygiene.create_project_assays assets/RUN<n>
PYTHONPATH=scripts uv run python -m assay_hygiene.create_project_assays assets/RUN<n> --confirm
```

With confirmation it posts each reviewed definition to `POST /nextseek_api/assays/`, records
returned IDs in `07-process/CREATED-ASSAYS.csv`, and rebuilds `UPDATE_ASSAY.xlsx` using those
project-scoped IDs. An in-progress marker blocks retries after a timeout or partial result;
reconcile the server manually rather than risk duplicate assays.
