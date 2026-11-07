# Account

**One place to run a student life.** Grades, deadlines, classes, money and work
usually live in separate apps that know nothing about each other, which leaves the
student as the glue: entering one assignment as a calendar event, a to-do and a row
in a grade calculator, and still not knowing what next week actually costs.

Account starts from the idea that these aren't five subjects but one life, and that
the answers worth having appear where they meet:
- A dated assignment is both a task and a calendar block.
- A course has a cost and a target grade.
- A shift at work competes with study for the same hours.
- A term has a budget that knows when it starts and ends.

It's built for real daily use, to be relied on for years rather than finished.

> **Status: live, invite-only.** The web app runs at
> [account-2a7.pages.dev](https://account-2a7.pages.dev), with the API on Google
> Cloud Run and the data in Postgres on Supabase. Sign-up is limited to an
> allowlist while it's in private use.

---

## What it does

### Grades
- **Courses with category weights,** and a choice for each category: share its
  weight evenly between items, by points, or by your own weights for each item.
  Marks are entered exactly as the professor gave them (48/52), whatever they're out
  of.
- **The course average,** its letter grade, and CGPA on a switchable scale (UBC's
  4.33 by default).
- **What you need on the final** to reach a target.
- **The band where the course can still finish,** from the best case to the worst.
- **What's worth doing next,** ranked by how much each item can still move the
  grade.
- **Grading schemes** for syllabi with more than one way to count, such as "the
  final replaces the midterm if higher". Dropped marks are supported too.
- **What-if scenarios,** a degree progress page, and a next-term planner.
- **A shared course catalogue** with prerequisites, and course outlines shared
  between students.
- **Grade distributions from past students,** shown only once enough of them have
  shared.

### Money
- **Accounts you define,** each with a share of income. A deposit splits across
  them, and transfers between them are tracked separately.
- **Categories and monthly limits,** recurring payments, sinking funds, and found
  subscriptions.
- **Investment returns, and a net worth figure** that you choose which accounts
  count toward.
- **Bank CSV import** that flags likely duplicates. Undo removes exactly the rows it
  added.
- **A forecast, a year plan, and a spending guard** that watches the weeks around
  exams.
- **Per-course cost:** tuition is priced per credit, so each course shows what it
  cost.

### Calendar and tasks
- **Recurring events** with "ends by" rules, and class times. There's a week view,
  and day and three-day views on a phone.
- **A weekly planner** that places study time in free blocks, up to a daily limit
  you set.
- **Tasks** with due dates, estimates and priorities, plus repeating tasks. A task
  for a course below its target is marked at risk.
- **Shared tasks and events,** focus sessions, reminders, and a daily briefing by
  push notification.
- **Accountability partners,** who see each other's weekly task completion, never
  grades.

### Jobs
- **Jobs with their pay rules** (hourly, or on set days of the month), shifts to
  confirm, and paycheques that split across your accounts. A shift that clashes
  with an exam is flagged on both pages.
- **An application tracker,** with a flow chart of where applications went.
- **Self-employed work:** clients and invoices.
- **A tax packet** that sets a year's pay beside the tuition paid in it.

### Across the app
- **The omnibox:** type `coffee 4.50`, `cosc121 midterm 78/100` or `lab due fri`,
  and it files each in the right place.
- **A Today card,** a "Get started" checklist, keyboard shortcuts, and a phone
  layout with a bottom bar.
- **Bring your own AI:** a read-only MCP server lets a student's own assistant read
  their daily briefing.

---

## Tech stack

| Layer | Choice |
|---|---|
| API | **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, Python 3.12 |
| Database | **Postgres 17** on Supabase in production, **SQLite** locally, on one set of models |
| Web app | **React 19**, **TypeScript**, **Vite 7**, **React Router 7**, **Tailwind v4** |
| Sign-in | Google, or email and password (bcrypt), both issuing the app's own JWT |
| Hosting | API on **Google Cloud Run**, web app on **Cloudflare Pages** |
| CI/CD | **GitHub Actions** |
| Tests | **pytest** on SQLite and Postgres; **Vitest** with Testing Library |

About 270 API routes over 77 tables.

---

## How it's built

### Layout

```
Application/
  backend/
    app/
      <Module>/schemas/    request and response shapes (Pydantic)
      <Module>/services/   the logic; takes a session, returns schemas
      <Module>/utils/      pure functions: no session, no models
      api/routes/          thin: parse, call one service, map errors to status codes
      _database/           models, engine, migrations, row security
      shared/              audit log, money and date helpers, error bodies
    scripts/               admin scripts, run by hand
    tests/
  frontend/
    src/features/<area>/   api.ts, types.ts, components/, hooks/
    src/pages/             one per route, composing features
    src/shared/            components, hooks and utils used across areas
  dev.run.sh               local development
  deploy.run.sh            CI, deploy and checks, from one command
```

The backend modules are Grades, Finances, Calendar, Tasks and Jobs, with Auth and
Users under them. Smaller ones cover syllabus intake, push notifications, the
omnibox, insights and partners.

### A few rules the code keeps

- **The server computes; the client displays.** Every figure is computed in a
  service and sent with the thing it describes, such as a course's average or a
  task's risk. Pages never redo the arithmetic, so two screens can't disagree.
- **One engine per idea.** A single recurrence engine serves class times, shifts,
  recurring payments and repeating tasks. A single averaging function serves every
  grade figure.
- **Only money that moved goes in the ledger.** A bursary or a tax deduction is
  recorded with the thing it belongs to, and only the net reaches an account.
- **Errors mean something.** 422 means the request was malformed, 400 that it was
  well-formed but wrong. 404 means missing *or someone else's*, deliberately the
  same, so the API never confirms which ids exist.

### Keeping each user's data their own

- **Row-level security in Postgres.** The API connects as a restricted role, and
  every request runs as the signed-in user. Even a query that forgot its user
  filter gets only that user's rows.
- **Features that cross between users go through security-definer functions.**
  Shared tasks, the catalogue and grade distributions each have one, and
  each has a SQLite twin that means the same thing.
- **Isolation tests walk every route** as another user, and fail if anything leaks
  or can be changed.
- **Sign-in:**
  - Sign-up is limited to an allowlist.
  - Login is throttled.
  - Changing a password revokes every other session at once.
  - Sign-ins and deletions are written to an audit log, never with a password or
    token in it.

### Shipping

- **CI runs on every push:**
  - the backend suite twice, on SQLite and on Postgres as the restricted role;
  - the frontend suite, type check and build.
- **The API deploys from the `ship` branch:**
  - The workflow authenticates with Workload Identity Federation, so no key file
    exists.
  - It refuses an image that needs a table or column production lacks.
  - It takes a database backup before moving traffic.
- **The web app** builds from `main` on Cloudflare Pages.
- **Schema changes are never applied by a deploy.** A person runs them, after a
  backup, and checks the result with read-back queries before the code that needs
  them goes out.
- **Backups also run on a schedule.**

### Testing

- More than 3,400 backend tests and more than 900 frontend tests.
- Every guard is **mutation-tested**: the fix is reverted, and a named test must
  fail.
- Tests never touch a real database. The backend suite runs on SQLite in memory by
  default, or on a Postgres test database you point it at.

---

## Running it locally

**You need:**
- Python 3.12 and Node.js 20 or later.
- A Google OAuth client ID (web application) with `http://localhost:5173` as an
  authorised JavaScript origin.

**Configure:**
- Copy `Application/.env.example` to `Application/.env`, and set
  `GOOGLE_CLIENT_ID` and a `JWT_SECRET` of at least 32 characters
  (`python3 -c "import secrets; print(secrets.token_hex(32))"`).
- Copy `Application/frontend/.env.example` to `Application/frontend/.env`, and set
  `VITE_GOOGLE_CLIENT_ID` to the same ID.

**Run:**

```bash
cd Application
./dev.run.sh              # API and web app together
./dev.run.sh backend      # API only (uvicorn, port 8001)
./dev.run.sh frontend     # web app only (Vite, port 5173)
./dev.run.sh docker       # the full stack with docker compose
./dev.run.sh install      # install dependencies, then exit
```

The first run creates the Python environment and installs both sets of
dependencies. Locally the database is SQLite at `Application/backend/data/app.db`,
and its tables are created on start-up. Interactive API docs are at `/docs` when
`ENABLE_DOCS` is set.

**Test:**

```bash
cd Application/backend && .venv/bin/python -m pytest -q
# The same suite on Postgres:
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/account_test .venv/bin/python -m pytest -q

cd Application/frontend && npx vitest run
```

---

## License

Not yet specified. This is a personal project.
