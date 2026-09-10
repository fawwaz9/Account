# Session handoff

Written at the end of a long session so the next one can pick up without
re-deriving anything. Everything below was verified against the running code,
not recalled.

---

## Where things stand

- **Branch:** `grades-branch`. `origin/grades-branch` is at `078e179`;
  **5 commits are unpushed** (`8a01741` through `16d54ff`, the whole Budget module).
- **22 commits** were made this session, starting from `af72c36`.
- `origin/main` sits at `3d0ac95` — a squashed copy of the auth commit. The branch
  has never been merged back.
- **Run it:** `Application/dev.run.sh` (also `backend`, `frontend`, `docker`,
  `install`). It creates the venv, installs both dependency sets, checks the `.env`
  keys and ports, and starts both services. Ctrl+C stops everything.
- Backend port defaults to **8001** (you changed it). `frontend/.env` carries a
  matching `VITE_API_BASE_URL`. Vite inlines that at startup, so **restart Vite
  after changing it**.

---

## What exists now

### Auth — complete
Google OAuth *and* email/password, both issuing the same JWT, so everything
downstream is provider-agnostic. Accounts link: signing in with Google on an
address that already has a password joins them rather than erroring.
`POST /api/auth/password` lets a Google-only account add a password while signed in.

### Grades — complete
Courses, weighted categories, grades, term awareness (past/current/future), letter
grades and GPA, target grades, an Attention panel, a hand-drawn SVG grade trend,
bulk grade entry, credits tracking, and a course search typeahead.

### Budget — complete
User-defined accounts with derived balances, a signed-amount transaction ledger,
double-entry transfers, spending categories, monthly per-account targets with
planned-vs-actual, income distribution by share, and editable ledger rows.

### Not built
**Calendar, Tasks, Notes, Goals, Study Analytics.** Calendar routes still return a
hardcoded sample dict. Tasks too. Recurrence was deliberately deferred to Calendar
so one engine serves both it and Budget's recurring payments.

---

## Decisions that shouldn't be re-litigated

These were argued through and settled. Reversing one needs a reason, not a fresh guess.

| Decision | Why |
|---|---|
| **CGPA exists, on a switchable scale** | Reverses the old README line that UBC has no GPA. Defaults to UBC 4.33, opt-out in Settings. |
| **Accounts and spend categories are rows, not enums** | The fixed `GradeCategory` enum is exactly what forced a real gradebook's ~40 categories into 8 during import. |
| **Balances derived, never stored** | For money, a balance disagreeing with its own ledger is worse than one that costs a query. |
| **Course `average` stored and authoritative** | Opposite of the above, deliberately: it is maintained on every write, and recomputing on read made the list and the detail page disagree. |
| **Cumulative average and CGPA count finished courses only** | A running average is unfinished work, not a result. That is what the semester average is for. |
| **Category weights may exceed 100** | Real courses are marked out of 101% and 104.71%. Weight past 100 is bonus: it adds marks without enlarging the denominator, and the course still caps at 100. |
| **Grades may exceed their category max** | Bonus marks are real. Capped at 2× to still catch a slipped digit. |
| **`below_target` fires only for current courses** | A finished course under target is history, not something to act on. |
| **Transfers are two linked rows** | Sharing a `group_id`; deleting either removes both, editing moves both. |
| **Budget "actual" counts expenses only** | A transfer moves money rather than spending it; income would otherwise offset a target it has nothing to do with. |
| **Recurring deferred to Calendar** | One recurrence engine, written once. |

---

## Conventions this codebase follows

- **Compute server-side, render client-side.** Any figure the UI shows comes from the
  API. Recomputing a formula in React is what produced the worst bug of the session —
  a course page printing `18.00/40` beside an average of `36.00/40`.
- **Attach computed values in the service layer.** `models.py` is imported *by*
  `grade_service`, so a `CourseModel` property calling back into it is a circular
  import. See `attach_course_summary` / `attach_category_averages`.
- **Migrations are additive and idempotent**, in `_database/migrations.py`.
  `create_all` only creates missing *tables*; it never alters an existing one.
  New tables need nothing; new columns on existing tables need an `ADDED_COLUMNS` entry.
- **Status codes:** 422 when a Pydantic validator fires during request parsing,
  400 when a service-layer validator does, 404 missing, 403 cross-user.
- **Native `<button>` for anything clickable** (SonarQube S6848). Where a row both
  selects and deletes, the delete control sits *outside* the row button so one click
  never means two things.
- **Real CSS, not Tailwind** — see the open item below.
- **Back up `data/app.db` before any migration.** Several `app.db.backup-*` files
  exist; they are gitignored.

---

## Gotchas found the hard way

Each of these cost real debugging time. Worth knowing before repeating them.

1. **`StaleDataError` on delete.** Mutating a mapped attribute for display marks the
   row dirty; deleting it in the same session then flushes an UPDATE for a row that is
   gone. Build a detached snapshot instead. (Hit twice — the grades module solved it
   earlier with `model_validate` before commit.)
2. **`create_all` does not alter tables.** A new column silently never reaches an
   existing database.
3. **Preferences were never persisted.** `UserPreferences` was declared and returned
   by `/me`, but `users` had no column, so `setattr` wrote to a non-mapped attribute
   and it vanished on commit. Now a JSON column that merges on partial patch.
4. **Two databases.** `DATABASE_URL` defaulted to `sqlite:///./app.db`, resolved
   against uvicorn's working directory, so local runs and Docker used different files.
   Now an absolute path anchored to the backend directory.
5. **Cumulative at zero flooring a chart.** A term with running averages but no final
   grades reported a cumulative of 0. It is nullable now; the line starts where the
   data does.
6. **A total check cannot catch a swap.** `Final 1%` + `Other 40%` sums to exactly 100
   and passes clean. That is why the weight check also compares the final against the
   largest other category.
7. **`git add -A` swept your in-flight edits into commits twice.** Stage explicit paths.

---

## Your real data

`oganlafawwaz@gmail.com` (Google + password linked), currently **Year 3, Fall**.

- **26 courses**, 126 grades, 208 category-weight rows — a full gradebook imported
  from your spreadsheet, reproducing every stated figure exactly.
- **Cumulative average 88.38, CGPA 4.05.** These match your sheet. If they move
  unexpectedly, something is wrong.
- **6 accounts** (Spending, Savings, Investments, Emergency, School, Money Lent),
  11 transactions, 7 budget targets, 10 categories.
- The import script lives in the scratchpad, deliberately outside the repo since it
  contains personal grades.

**Known data gap:** `MATH 100` is a past course with no final grade — it shows in the
Attention panel and is correctly excluded from the cumulative. Your sheet's
"Final Grade" column looks like a *projection* rather than an awarded grade;
`DATA 101` reads 86 there against a computed 82.53. That column now drives the
cumulative directly, so it is worth confirming.

---

## Open items

**Decisions waiting on you**

- **Tailwind is imported but unwired.** No `vite.config.ts`, so ~31 KB of theme
  variables ship and no utility classes are generated. Registering the plugin also
  enables Preflight, which would reset margins and headings across CSS written for
  browser defaults. Either wire it and accept a restyle, or delete the import and the
  two dependencies. Pending for four sessions.
- **Docker is the last unchecked item in `to_do.txt`.** The files exist and
  `dev.run.sh docker` is wired, but it has never been run end to end.
- **Income share hint reports rather than enforces.** Shares needn't total 100 —
  income divides by ratio. Say if you want it enforced.

**Next feature: Calendar.** Per `core.txt` it is the centre of the whole app —
classes, tasks, daily spend and recurring payments all surfacing on it.
`design.txt` already sketches `events` with `recurrence_rule` and `ends_by`.
Recurrence is the hard part; decide early whether to store an RRULE or something
simpler.

**Cheap win still open:** `shared/components/{Button,Card,Input,Modal}.tsx` and
`shared/utils/*` are all still empty, so every modal is hand-rolled.
`app/layout/` is now filled (sidebar shell exists).
