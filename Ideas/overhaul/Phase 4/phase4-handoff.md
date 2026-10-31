# Phase 4 handoff

Written for: the next Claude session, likely in the cloud, starting cold. Written
2026-10-31. Read this, then `Ideas/overhaul/template.md`, which is the pipeline to
follow, and `account-vision.md` (Phase 4 at about line 403, and §13.5, §13.6, §13.12,
§13.19).

## The owner's instruction

"Check if phase 3 is complete, if not complete it, then run all checks, then move on
to phase 4 independently. Ask any clarifying questions." The owner is at work and
answers questions by phone.

## The owner's answers (2026-10-31): record these as Phase 4 decisions

- **Scope:** all of Phase 4 except Plaid. That is: CGPA including this term, weekly
  planner, deadline risk, focus sessions, exam countdown, briefings, BYOAI, non-financial
  correlations, term simulator, grade scenarios, course-drop, next-term planner, deadline
  spending guard, money what-if, self-employed.
- **Deploys:** once all checks pass, backend changes that add **no tables or columns**
  may deploy without asking again; verify and record them. Frontend is free to deploy.
  **Anything with a schema change waits for the owner's schema step.**
- **BYOAI:** off by default; a revocable, read-only token stored hashed, which reads only
  the digest. A plain API endpoint plus a small MCP server over the same digest.
- **CGPA including this term:** a current course counts at its running average, the
  figure the Semester Average uses, not a projected finish (settled 2026-10-28; details
  in `Ideas/next.md`, Grades).

## Where things stand

- **Phase 3:** all 13 items are built and live, except Strava and Fitbit, which wait on
  the owner's app registrations. Its exit criteria need real contributors, so no build
  can meet them. Open Phase 4 the way Phase 2 was left (Phase 3 D1): Phase 3 stays open
  for those criteria. Record that as a decision.
- **Live:** API `account-api-00049-smp` at `9b5a4bd`; Pages at `abeb498`. Production was
  healthy on 2026-10-31: no errors since the deploy, and the recount answers 200 daily.
- **Not deployed yet:** `5baad80`, frontend only, from walking every Phase 3 screen in a
  browser. Rounded course figures, ranks on the campus board, no hole on the Fitness page,
  no overflow on a phone. Deploy it once CI passes on the branch tip, then record it in
  `Ideas/shipped.md` and `Ideas/ROLLBACK.md`. `bddc556` is formatter output only.
- **Checks on `5baad80`:** frontend 850 passed, tsc and build clean, backend on SQLite
  2,983 passed. The local Postgres run had not finished at handoff, so read CI's
  `backend-postgres` job on this push instead.
- **Phase 4 itself:** nothing built, and no `phase4.md` yet. Next: branch `phase4` from
  `phase3`, and draft `phase4.md` and `phase4-decisions.md` from the template. Build CGPA
  first: it needs no schema and no history (`Grades/services/dash_services.py`,
  `SemesterSummary.tsx`).

## What already exists for Phase 4

- `Calendar/services/load_service.py`: `free_blocks`, `week_load`, `crunch`.
- Task timer and estimate ratio: `Tasks/services/estimates_service.py`.
- `Finances/services/plan_service.py`: the year plan and its hours scenarios.
- `Finances/services/tuition_service.py`, for the course-drop refund.
- `RequiredFinalModal.tsx`, the grade engine, for grade scenarios.
- `Notifications/services/push_service.py`, and the scheduler's `/api/internal/*` routes.
- `_database/aggregates.py` `course_intel`, for the next-term planner.
- Category limits: `AccountCategoryLimitModel`, `AccountCategoryMonthLimitModel`.

## Rules that do not bend

- Data safety is the highest priority. No request reads another user's rows.
- The schema step is the owner's. `deploy.run.sh` never applies schema.
- Use `./Application/deploy.run.sh` for deploys. Never run anything against
  `data/app.db` or production to "check"; use a throwaway database.
- **The financial silo (§13.3, §13.5):** nothing correlates money with academics. Money
  simulators never project grades. In the term simulator, the work slider gives time fit
  only, and grade bands come only from directly set study hours.
- Reading production data is the owner's call. Don't send the owner's email to unrelated
  services. Personal documents never go to an LLM. A permission denial is not to be worked
  around. `TEST_DATABASE_ALLOW_REMOTE` must never appear in workflows.
- Stage explicit paths. Commit messages end with the attribution line the session gives.
- **Tests:** enumerate routes rather than list them, and add every new table to the
  isolation walks (`tests/isolation_world.py`, `test_isolation.py`,
  `test_noninterference.py`, `test_rls.py`). Mutation-test the safety lines.
- **Look at new screens in a browser with seeded data.** The owner's team and club
  fields had no visible box, and every test passed. Walking Phase 3 found four more.

## If this session lacks what the laptop had

`gcloud`, production secrets and `Application/.env` are not in the repo. If deploying or
reading logs needs credentials this environment doesn't have, keep building and testing on
`phase4`, and leave the deploy for the owner's laptop. Don't look for other ways in.
