# Phase 3 — runbook

Written for: you, running Phase 3's production steps in order. Each step says
what it changes, the exact commands, how to verify it with a negative control,
and how to undo it. Follows `Ideas/overhaul/template.md`.

Nothing here has run yet. The first batch, the job application tracker (item
1), is written here once it is built and its facts are settled.

## Done before Phase 3 opened

- **The daily grade recount** (Phase 2 item 13's optional step), created
  2026-10-12: `account-grade-recount`, 09:30 UTC daily. A test run returned
  `200` from `Google-Cloud-Scheduler` in the API's request log. It feeds item
  3. **Undo:** `gcloud scheduler jobs delete account-grade-recount
  --location=us-west1 --project=account-504419` (instant).
