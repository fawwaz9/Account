# Session handoff

Where the project actually is, for a session picking it up cold. Everything here
was checked against the running code, the live deployment or the production
database on **2026-09-14** — not recalled.

**Read this for state. Read [design/](design/) for how and why.** The design
notes carry the reasoning behind every decision that had a real alternative,
which is what stops the next session reversing one for looking inconvenient.

---

## The short version

The app is **built and live**. Five modules ship — Grades, Finances, Calendar,
Tasks and Jobs — on 23 tables and 740 backend tests. It has been deployed to
Cloud Run + Supabase + Cloudflare Pages, and a second person is using it.

| | |
|---|---|
| Branch | `main`, clean, level with `origin/main` |
| Frontend | https://account-2a7.pages.dev — Cloudflare Pages, builds from `main` on push |
| API | https://account-api-210502804146.us-west1.run.app |
| Database | Supabase `kujxxairehpwhxhnkbct`, `us-west-2`, Postgres 17.6 |
| Tests | 740, all green |
| Local dev | `Application/dev.run.sh` — backend on **8001**, SQLite at `data/app.db` |

**Local development still uses SQLite and still points at `data/app.db`.**
Nothing local reads Supabase, deliberately. The cloud string lives in `.env` as
`SUPABASE_DATABASE_URL`, *not* `DATABASE_URL` — setting the latter would point
dev at the cloud and the app would come up looking wiped with nothing on screen
to say why.

---

## What exists

**Grades** — courses, weighted categories, term awareness, letter grades and
CGPA, targets, bonus categories, dropped marks, best/worst projection, credits,
course search.

**Finances** — accounts with derived balances, a signed-amount ledger,
double-entry transfers, categories, monthly targets, income distribution by
share, tuition with per-course cost attribution, safe-to-spend, sinking funds,
subscription detection.

**Calendar** — the recurrence engine and its four consumers, week and month
views, blackout periods, free blocks, week load, the crunch radar.

**Tasks** — due dates and times, priority, repeats, snooze, reminders,
completion timing, at-risk-first ordering, quick capture and the omnibox.

**Jobs** — shifts on the calendar, paycheques with deductions, earned-vs-paid,
effective hourly rate, tips split cash from on-cheque.

**Not built:** Notes, Goals and Study Analytics, from the original `core.txt`
sketch. None has been designed; none is blocking anything.

---

## What is actually left

Three things, in order of how soon they matter:

1. **Step 12a / D5.5 — the rate limiters key on the wrong address.** Behind
   Cloud Run, `request.client.host` is Google's front end: production logs show
   99 of 99 requests from `169.254.169.126`. Every limit is therefore one shared
   budget. Harmless at three users; **must be fixed before the invite list
   opens**, or one person hitting the login limit locks out everyone.
2. **Audit #35 — no request caching.** Redundant round trips on every
   navigation, and every `reload()` refetches all four endpoints when one row
   changed. This cost nothing on localhost and costs real latency from a phone.
3. **Everything in `whats_next.txt`** under *What is left, by module*.

Deployment leftovers, none urgent, all written up in `deployment.md`:
the Dockerfile ignores `$PORT` (hence `--port=8000` on every deploy); backups
exist in one place only, expiring at 90 days; and a **second Supabase project
(`ommqbgaasrusrlizzyzm`) holds a full copy of everyone's data** from the restore
test — its password is rotated, but it should be deleted or treated as
production.

---

## The production data, as of 2026-09-14

Useful as a tripwire: if these move in a way nothing explains, something is wrong.

| | rows |
|---|---|
| users | 4 — three active, one soft-deleted |
| courses | 27 |
| grades | 126 |
| course_category_weights | 223 |
| accounts | 16 |
| transactions | 97 |
| spend_categories | 57 |
| events / tasks / jobs | 20 / 11 / 3 |

The owner holds essentially all of it: 27 courses, 6 accounts, 94 transactions,
3 jobs, 11 tasks. The second person has signed in and their six accounts seeded
on first read; they have entered nothing yet. The soft-deleted account
(`fawz09@student.ubc.ca`, a legacy local-auth row carried over from SQLite)
purges on **2026-10-15**, on the first cold start after that date.

**Cumulative average 88.38, CGPA 4.05** — these matched the source spreadsheet
at import. If they move unexpectedly, that is the signal.

**`MATH 100` is a past course with no final grade**, so it shows in the Attention
panel and is correctly excluded from the cumulative. That is a data gap, not a
bug.

---

## Before you touch anything

- **Branch off `main`, and off `main` only.** Stacking on unmerged work caused
  phantom conflicts twice, and once cost an afternoon to a "the fix is not there"
  report that turned out to be a branch without the fix in it.
- **Never run a script against the real `data/app.db`.** Copy it to the
  scratchpad and point the engine at the copy. And never compute a delete filter
  — one `getattr`-based one wiped 218 rows across 27 courses, silently, while the
  script printed success.
- **Stage explicit paths.** `git add -A` swept in-flight edits into commits twice.
- **A push to `main` deploys the frontend.** Cloudflare Pages builds from it.
  The API does not deploy itself — that is a manual `gcloud run deploy`.
- The rest of the conventions and the hard-won gotchas are in
  [design/README.md](design/README.md), which is where they belong now.
