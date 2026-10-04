# Session handoff

Where the project actually is, for a session picking it up cold. Everything here
was checked against the running code, the live deployment or the production
database on **2026-09-28** — not recalled. Where a figure was carried over from
an earlier pass rather than re-measured, it says so.

**Read this for state. Read [design/](design/) for how and why.** The design
notes carry the reasoning behind every decision that had a real alternative,
which is what stops the next session reversing one for looking inconvenient.

---

## The short version

The app is **built and live**. Five modules ship — Grades, Finances, Calendar,
Tasks and Jobs — on 25 tables, 940 backend tests and 142 frontend tests. It has
been deployed to Cloud Run + Supabase + Cloudflare Pages, and a second person is
using it.

| | |
|---|---|
| Branch | `main`, clean, level with `origin/main` |
| Frontend | https://account-2a7.pages.dev — Cloudflare Pages, builds from `main` on push |
| API | https://account-api-210502804146.us-west1.run.app |
| Database | Supabase `kujxxairehpwhxhnkbct`, `us-west-2`, Postgres 17.6 |
| Tests | 940 backend + 142 frontend, all green |
| API image | `backend:8f73dca` — revision `account-api-00018-2zp` |
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
subscription detection, and per-`(account, category)` spending limits with a
per-month override and a Planned-spend target derived from them.

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
   navigation, and every `reload()` refetches — **eight** endpoints, not the
   four this finding originally said. Cost nothing on localhost; costs real
   latency from a phone.
3. **Audit #57–#65**, from the front-end review of 2026-09-28. #58 first: seven
   stored preferences have no control in Settings, and `timezone` is one of
   them, so the completion-timing figures are computed against the wrong day
   boundary for anyone outside `America/Regina`.
4. **The three interface-quality asks** in `next.md` — confirm every
   delete (nine do not), make a click feel like a click (`:active` appears zero
   times in the whole stylesheet), and move ambient muted explanations behind a
   `(?)` affordance.
5. **Everything in `next.md`** under *What is left, by module*.

Deployment leftovers, none urgent, all written up in `deployment.md`:
the Dockerfile ignores `$PORT` (hence `--port=8000` on every deploy); backups
exist in one place only, expiring at 90 days. (The second Supabase project
from the restore test, `ommqbgaasrusrlizzyzm`, was deleted 2026-10-04.)

---

## The production data, as of 2026-09-28

**Queried, not recalled** — a read-only census against Supabase on 2026-09-28,
run inside a `READ ONLY` transaction, selecting no email address and no password
hash. Useful as a tripwire: if these move in a way nothing explains, something is
wrong.

| | rows | was, 2026-09-14 |
|---|---|---|
| users | **5** — 4 active, 1 soft-deleted | 4 |
| courses | 30 | 27 |
| grades | 206 | 126 |
| course_category_weights | 250 | 223 |
| accounts | 28 | 16 |
| transactions | 143 | 97 |
| spend_categories | 57 | 57 |
| events / tasks / jobs | 51 / 82 / 3 | 20 / 11 / 3 |
| account_category_limits | 11 | — (feature is newer) |
| account_category_month_limits | 0 | — (shipped, unused) |
| `category_budgets` | **2 — orphaned, see below** | — |

**912 rows, 13 MB, 26 tables, 86 indexes.** The cap is 500 MB, so size is not a
question yet. The 86 is what Postgres actually holds, primary-key and
unique-constraint indexes included; the schema module declares 55 through
SQLAlchemy's inspector, and the two numbers are not counting the same thing.

> ### 26 tables in production, 25 in the schema
>
> **`category_budgets` should not exist.** It was created by `f0dfede` for
> whole-budget category limits, and `394cb7c` took that feature back out — model,
> service, routes, the lot. The **rollback removed the code and left the table**,
> with its four indexes and **two rows of real data**: $41,040 against September
> 2026 and $70 against October. Nothing references it, no foreign key points at
> it, and nothing has selected from it since 2026-09-24.
>
> It is harmless, and it is not nothing: production's schema disagrees with what
> `python -m app._database.schema` builds, which is the file everyone trusts to
> describe this database. **Dropping it destroys two rows**, so it is a decision
> rather than a tidy-up — recorded in `next.md`.

The **per-user split was not re-measured** — that query was refused as a
production read, so the 2026-09-14 reading stands: the owner held essentially all
of it. Accounts rising 16 → 28 is consistent with two more people signing in and
having six each seeded on first read. The soft-deleted account, a legacy
local-auth row carried over from SQLite, has `deleted_at = 2026-09-15`, so it
purges on **2026-10-15**, on the first cold start after that date — confirmed by
this census.

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
