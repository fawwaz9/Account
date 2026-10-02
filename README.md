# Account — The Ultimate Student App

**One place to run a student life.** Grades, deadlines, classes and money normally live in four apps that know nothing about each other, which leaves the student as the integration layer — entering the same assignment as a calendar event, a to-do and a row in a grade calculator, and still not knowing what next week actually costs. Account is built on the premise that these are not four subjects but one life, and that the answers worth having only appear where they meet: a dated assignment is a task *and* a calendar block, a course carries a cost and a target, a term has a budget that knows when it begins and ends.

The aim is a tool good enough to live in every day, not one to demonstrate — built for real use first, and meant to be worked on and relied on for years rather than finished.

**Repository:** [github.com/fawwaz9/Account](https://github.com/fawwaz9/Account)

> **Status: live in production**, and a second person is using it. The frontend is
> on [account-2a7.pages.dev](https://account-2a7.pages.dev), the API on Cloud Run in
> `us-west1`, and the data in Supabase Postgres 17.6. Development is on **`main`**,
> and a push to it rebuilds the frontend.
>
> **Five modules ship** — Grades, Finances/Budget, Calendar, Tasks and Jobs — over 23
> tables and 904 backend tests, with Auth, Users and Settings underneath them. Only
> the last three boxes of the tree below are unbuilt: Notes, Goals and Study
> Analytics have never been started, and nothing depends on them.
>
> **`Ideas/` is the live record, and it is what to read rather than this file.**
> [`Ideas/design/`](Ideas/design/README.md) carries how each module works and *why*,
> which is what stops a settled decision being reversed for looking inconvenient;
> [`shipped.md`](Ideas/shipped.md) holds what has shipped and [`next.md`](Ideas/next.md) what is next;
> [`shipping.md`](Ideas/shipping.md) is the loop for building and deploying a change;
> [`ROLLBACK.md`](Ideas/ROLLBACK.md) is for when something is broken; and
> [`audit.md`](Ideas/audit.md) is the defect record — 56 findings, one still open.
>
> **Sections further down still describe the app as it was before any of that
> shipped** — they name Calendar and Tasks as stubs, list closed security findings as
> open, and point at files since deleted. They are being brought current; until they
> are, trust `Ideas/` over anything below this line.

---

## The Goal

From `Ideas/core.txt` — the app is meant to become a single place that holds:

- A **heavily modifiable calendar** with recurring events and "ends by" rules, showing classes, tasks/reminders, money spent per day, and recurring payments/transfers all on the same surface.
- A **grade calculator and class schedule**, with predictions and analytics.
- A **budget system built on accounts you create** — Spending, Savings, Investments, Emergency Savings and School are seeded as a starting point, and any account you add beyond them takes a name, a kind and a share of income like the rest. Income is distributed across them and movements between them are tracked separately.
- **Tasks with checkboxes and progress bars** for long-running goals (saving money, gym consistency, study hours).

Target feature tree, as first sketched:

```
Dashboard
├── Grades      (calculator, assignment tracker, predictions, analytics)
├── Calendar    (classes, exams, deadlines, study planner)
├── Finances    (budget, expenses, income, savings)
├── Tasks       (homework, personal, recurring)
├── Notes
├── Goals
├── Study Analytics
└── Settings
```

The project is built around UBC-specific context. `calculate_letter_grade` maps
percentages onto UBC's letter scale. An earlier version of this file said there was
deliberately no GPA scale; that has since been reversed — **CGPA exists on a
switchable scale**, defaulting to UBC's 4.33 and turned off in Settings for anyone
who does not want it.

---

## Tech Stack

### Backend
| Piece | Choice |
|---|---|
| Framework | **FastAPI** 0.135 |
| ORM | **SQLAlchemy** 2.0 |
| Database | **SQLite** (`Application/backend/data/app.db`) |
| Validation | **Pydantic v2** + `pydantic-settings` |
| Auth | **Google OAuth** (`google-auth`) and email + password (**bcrypt**), both issuing **PyJWT** bearer tokens |
| Server | **uvicorn** |

### Frontend
| Piece | Choice |
|---|---|
| UI | **React 19** + **TypeScript** |
| Build | **Vite 7** |
| Routing | **React Router 7** |
| HTTP | Hand-rolled `fetch` wrapper (`services/apiClient.ts`) |
| Styling | Plain CSS with CSS custom properties (`styles/globals.css`) |

### Infrastructure
- **Docker** — multi-stage production builds for both services (backend runs as a non-root `appuser`)
- **docker-compose** — orchestration, backend bound to `127.0.0.1:8000` only
- **nginx** — serves the built frontend with SPA fallback so `/grades` survives a hard refresh

### Tooling
- **SonarQube / SonarLint** — static analysis, treated as actionable and fixed inline rather than deferred

---

## Architecture

### Backend layout

```
Application/backend/
├── Dockerfile
├── requirements.txt
├── data/app.db                        # SQLite file, bind-mounted for host visibility
└── app/
    ├── main.py                        # FastAPI app, CORS, router registration
    ├── config.py                      # pydantic-settings: GOOGLE_CLIENT_ID, JWT_SECRET, ...
    ├── Auth/
    │   ├── dependencies.py            # bearer scheme → get_current_user_id / CurrentUser
    │   ├── schemas/token.py           # GoogleAuthRequest, TokenResponse, TokenPayload
    │   └── services/
    │       ├── access.py              # VerifiedUserId — path-level user authorization
    │       ├── google_auth_service.py # verifies the Google ID token
    │       └── session_service.py     # create/decode our own JWT
    ├── Users/
    │   ├── schemas/user.py            # User, UserCreate/Update, UserPreferences
    │   ├── schemas/academic_status.py # school year / semester (not yet persisted)
    │   └── services/user_service.py
    ├── Grades/
    │   ├── schemas/                   # course.py, grade.py, dashboard.py
    │   ├── services/                  # course_service.py, grade_service.py, dash_services.py
    │   └── utils/enums.py             # Semester, GradeCategory
    ├── api/routes/                    # auth, users, grades, calender, tasks, finances
    ├── shared/errors.py               # error dicts + reusable OpenAPI `responses`
    └── _database/
        ├── db.py, models.py, dependencies.py
        ├── design.txt                 # target schema, including tables not yet built
        └── check_state.py             # diagnostic script for inspecting live DB state
```

### Data model (`_database/models.py`)

```
users ──< courses ──< grades
      │        └────< course_category_weights
      ├──< accounts ──< transactions >── spend_categories
      └──< budget_targets
```

Eight tables, not the four this section used to list: the Budget module added
`accounts`, `transactions`, `spend_categories` and `budget_targets`.

| Table | Notes |
|---|---|
| `users` | UUID PK, unique `email` and `google_id`, `auth_provider` (how it was created), `password_hash` (bcrypt; NULL until one is set), `email_verified` |
| `courses` | UUID PK, `code`, `name`, `semester`, `year`, `credits`, `required`, `professor`, `final_grade`, `average`, optional `start_date`/`end_date` |
| `course_category_weights` | One row per (course, category) — the normalized form of the `category_weights` dict |
| `grades` | `name`, `category`, `score` (nullable), `max_score`, `weight` copied from the course's category weight |

All child relationships use `cascade = "all, delete-orphan"` — deleting a user hard-deletes their courses and grades. There are no soft deletes or audit trail yet (see [Security backlog](#security-backlog)).

`CourseModel.category_weights` is a `@property` that flattens the `category_weight_rows` relationship into a clean `dict[str, float]` for Pydantic, keeping ORM internals out of the API-facing shape.

### API surface

Every router is mounted under `/api`, and every route except `POST /api/auth/google` and `GET /api/users/me` is scoped by `{user_id}` and guarded by the `VerifiedUserId` dependency, which 403s if the JWT subject doesn't match the path.

| Router | Base path | State |
|---|---|---|
| Auth | `/api/auth` | `POST /google`, `POST /register`, `POST /login`, `POST /password` — all return the same 7-day app JWT |
| Users | `/api/users` | `GET /me`, `GET/PATCH/DELETE /{user_id}`, academic status |
| Grades | `/api/grades` | Full CRUD — see below |
| Finances | `/api/finances` | **Complete** — accounts, transactions, transfers, deposits, spend categories, budget targets, per-account activity |
| Calendar | `/api/calendar` | `GET /{user_id}/events` — **still returns a hardcoded sample event** |
| Tasks | `/api/tasks` | `GET /{user_id}/tasks` — **still returns a hardcoded sample task** |

Grades endpoints (all prefixed `/api/grades/{user_id}`):

```
GET    /grades/dashboard                            aggregated cross-course rollup
GET    /courses                                     list
POST   /courses                                     create
GET    /courses/search?query=                       server-side ilike search
GET    /courses/{course_id}                         detail (with grades)
PATCH  /courses/{course_id}                         update
DELETE /courses/{course_id}
GET    /courses/{course_id}/statistics
GET    /courses/{course_id}/category-weights
PATCH  /courses/{course_id}/category-weights
GET    /courses/{course_id}/average
GET    /courses/{course_id}/letter-grade
GET    /courses/{course_id}/required-final?target_grade=
GET    /courses/{course_id}/grades                  list grades
POST   /courses/{course_id}/grades                  create grade
GET    /courses/{course_id}/grades/{grade_id}
PATCH  /courses/{course_id}/grades/{grade_id}
DELETE /courses/{course_id}/grades/{grade_id}
PATCH  /courses/{course_id}/grades/{grade_id}/score?score=
```

Direct user creation/listing endpoints were deliberately **removed** — Google OAuth is the only supported path for creating or identifying a user, since exposing raw user CRUD was a security risk.

### Authentication

Two providers, one session format. Both routes return the same `TokenResponse`,
so everything downstream — `get_current_user_id`, `VerifiedUserId`, the
frontend's bearer header — is provider-agnostic.

| Route | Auth | Body | Success |
|---|---|---|---|
| `POST /api/auth/google` | — | `{ id_token }` | 200 + JWT |
| `POST /api/auth/register` | — | `{ name, email, password }` | 201 + JWT |
| `POST /api/auth/login` | — | `{ email, password }` | 200 + JWT |
| `POST /api/auth/password` | bearer | `{ new_password, current_password? }` | 200 + **replacement JWT** |

**One account, both sign-in methods.** Signing in with Google on an address that
already has a local account links the two rather than erroring — same user id,
same courses. `/me` reports `has_password` and `has_google` so the UI can show
what the account can actually use; `auth_provider` records only how it was
first created.

To go the other direction, a Google-only account adds a password through
`POST /api/auth/password` **while signed in**. Registration onto an address
that already belongs to a Google account is refused, because letting an
unauthenticated caller attach a password to an existing account is account
takeover by anyone who knows the address.

- **Linking drops an unproven password.** Local signup cannot verify an address
  (there is no verification email yet), so a password on an unverified account
  proves nothing about who owns the mailbox — someone could register
  `victim@example.com` before the real owner ever signs in with Google and keep
  access afterwards. This is account pre-hijacking. Google's assertion settles
  ownership, so on link the unverified account's password is cleared and
  `email_verified` is set; the owner sets a new one from account settings.
  An already-verified account keeps its password.
- **Changing a password requires the current one**, so a stolen session cannot
  silently lock the owner out. An account with no password yet can set its
  first without that step.
- Passwords are hashed with **bcrypt** (`Auth/services/password_service.py`).
  bcrypt rejects anything over 72 bytes outright rather than truncating, so
  that limit is enforced in the schema as a 422 instead of surfacing as a 500.
  Minimum length is 8 characters.
- `password_hash` is NULL for Google users. A Google-only account attempting a
  password login is rejected exactly like a wrong password.
- **Login never reveals whether an address is registered.** A missing account,
  a Google-only account, and a wrong password all return the same
  `401 Invalid email or password`, and the no-account path still spends a
  bcrypt verification so the responses take comparable time.
- Emails are normalized (trimmed, lower-cased, format-checked) on the way in,
  so casing cannot produce two accounts for one address.
- `GET /api/users/me` declares `response_model=User`. This is load-bearing —
  without it FastAPI serializes the raw ORM row, which now includes
  `password_hash`.

### Frontend layout

```
Application/frontend/
├── Dockerfile, nginx.conf, index.html   # index.html loads Google Identity Services
└── src/
    ├── main.tsx
    ├── app/
    │   ├── App.tsx                      # AuthProvider + BrowserRouter + all routes
    │   ├── auth/AuthContext.tsx         # token, user, isAuthenticated, isLoading, login, logout
    │   ├── auth/ProtectedRoute.tsx
    │   └── layout/                      # MainLayout, Sidebar, Topbar — all populated
    ├── services/
    │   ├── apiClient.ts                 # fetch wrapper: base URL, bearer header, 401 handling
    │   ├── authClient.ts                # loginWithGoogle
    │   ├── currentUserClient.ts         # getCurrentUser
    │   └── endpoints.ts                 # centralized path builders
    ├── features/
    │   ├── grades/                      # api.ts, types.ts, hooks, ~19 components
    │   ├── budget/                      # api.ts, types.ts, hooks, ~12 components
    │   ├── calender/                    # api.ts + types.ts only; components are EMPTY STUBS
    │   └── tasks/                       # api.ts + types.ts only; components are EMPTY STUBS
    ├── pages/                           # Dashboard, LoginPage, Calendar, Tasks, Budget,
    │   └── grades/                      #   GradesPage, CourseDetailPage
    ├── shared/                          # components/Modal.tsx is real; the rest are EMPTY STUBS
    └── styles/                          # globals.css, dashboard.css, grades/*.css
```

**Auth flow:** `index.html` loads the Google Identity Services script → `LoginPage` renders the Google button and polls up to ~10s for the script → the Google credential is POSTed to `/api/auth/google` → the returned app JWT goes into `AuthContext` and `sessionStorage` → the effect fetches `/api/users/me` to populate `user`. `isLoading` exists specifically so `ProtectedRoute` doesn't bounce to `/login` before auth state has resolved on first load.

**API client:** `apiClient.ts` is a hand-written `fetch` wrapper — `axios` has been
removed from `package.json`. It reads `VITE_API_BASE_URL`, attaches the bearer token
from `sessionStorage`, unpacks FastAPI's 422 `detail` arrays into readable messages,
and on a 401 clears the token and redirects to `/login`.

Its fallback is `http://localhost:8000/api`, which does **not** match the backend's
default port of 8001 — so `dev.run.sh` derives `VITE_API_BASE_URL` from `BACKEND_PORT`
and exports it, and the two cannot disagree. That fallback is now only reached by
running Vite by hand with no `.env`.

---

## Core Feature: Grade Tracking

The one fully-built module. Supports:

- **Courses** with configurable **category weights** drawn from the `GradeCategory` enum (`Assignment`, `Lab`, `Quiz`, `Midterm`, `Final`, `Participation`, `Project`, `Other`) and a `Semester` enum (`Fall`, `Winter`, `Spring`, `Summer`).
- **Grades** recorded per category, each with `score`, `max_score`, and a `weight` inherited from the course's category weight at time of grading. `sync_grade_weights` re-propagates weights to existing grades when a category weight changes.
- **Point-weighted category averages** — `calculate_grade_category_average` weights each grade within a category by its `max_score`, so a 20-point assignment counts more than a 5-point quiz (equivalent to total points earned ÷ total points possible).
- **Course-level weighted average** — `calculate_current_average` combines each *graded* category's average weighted by its `category_weight`, normalizing over only the categories that have grades, with a guard against weights summing over 100.
- **"What do I need on the final"** — `calculate_required_final` back-solves for the final score needed to hit a target, and reports which categories are still ungraded so the answer can be read with the right caveat.
- **Dashboard aggregation** — `get_dashboard` rolls all courses into best/weakest course, overall average, courses still needing a final score, and unfinished categories per course.
- **Modal-driven CRUD UI** — `AddCourseModal`, `EditCourseModal`, `AddGradeModal`, `EditGradeModal`, `DeleteConfirmModal`, with `GradeCategoryColumn`s derived dynamically from each course's active (non-zero-weight) categories.

### Data flow pattern (the house style)

```
Modal owns form state (useState)
  → Form component is presentational only (form, updateField, onSubmit, error props)
    → handleSubmit builds a typed payload
      → typed API function (features/<domain>/api.ts)
        → apiClient (get/post/patch/del) + endpoints.ts path builder
          → FastAPI route (VerifiedUserId + DBSession)
            → service-layer function (course_service.py / grade_service.py)
              → SQLAlchemy model mutation + commit
```

Every new resource — budgets, tasks, calendar events — is expected to follow this same five-layer pattern.

---

## Key Design Decisions & Learnings

### Data integrity: category weight normalization
`update_course` once bypassed `normalize_category_weights`, letting weights summing over 100% reach the database. Fixed by routing all weight updates through `apply_category_weights` (the alias `course_service` uses for `grade_service.update_category_weights`), adding sum-check `@model_validator`s to `CourseUpdate` and `CategoryWeightsUpdate`, and building `check_state.py` to inspect live DB state and flag any course whose weights still sum over 100.

### Pydantic ↔ SQLAlchemy boundary
The relationship is `category_weight_rows`; the `@property category_weights` converts it to `dict[str, float]` for serialization. `DetachedInstanceError` on deletes is avoided by snapshotting via `GradeSchema.model_validate(grade)` **before** committing the delete.

### HTTP status code conventions
- **422** — a Pydantic validator fires during FastAPI's request parsing (bypasses the route's own `try/except`)
- **400** — a validator fires inside service-layer code (caught by the route's exception handler)

Used consistently across the grades module.

### Form state typing
`CourseCreate` (not `CourseUpdate`) is used for form state, because `CourseUpdate`'s nullable fields break controlled React inputs.

### React hooks discipline
`useAuth()` is always called at the top level of a component — never inside a handler or conditional. All consumer files were migrated off an earlier `getOrCreateUserId` pattern to `useAuth()`, which also fixed a Rules-of-Hooks violation in `AddCourseModal`.

### CSS specificity
When a global rule like `.container button` overrides component styles, the fix is a more specific component selector (`.courses .courseBox`) rather than `!important`. `all: unset` is avoided as a reset — it also resets `display` and breaks flex/grid; targeted resets (`background`, `border`, `padding`, `font`, `appearance`) are used instead.

### Accessibility (SonarQube-driven)
- **S6848 / S6819** — clickable `<div>`s and `role="button"` are replaced with native `<button>` elements, which get focus, keyboard activation, and touch support for free.
- **S6470** — Docker `COPY` scope is tightened rather than copying broad directories.
- Super-linear regex backtracking patterns identified and fixed.
- Dependencies use the SonarQube-recommended `Annotated[Session, Depends(get_db)]`, aliased as `DBSession`.

---

## Getting Started

### Prerequisites
- Python 3.12
- Node.js 20+
- Docker & Docker Compose (optional)
- A Google Cloud OAuth **Web application** client ID with `http://localhost:5173` as an authorized JavaScript origin

### Environment variables

`Application/.env` (read by docker-compose):
```
GOOGLE_CLIENT_ID=<your-google-oauth-client-id>
JWT_SECRET=<a-long-random-string>
```

`Application/backend/.env`:
```
GOOGLE_CLIENT_ID=<same-client-id>
JWT_SECRET=<same-secret>
```

`Application/frontend/.env`:
```
VITE_GOOGLE_CLIENT_ID=<same-client-id>
```

Each of those three directories carries a committed **`.env.example`** — copy it and
fill it in. `JWT_SECRET` must be at least 32 characters or the backend refuses to start;
generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`.

Optional overrides: `JWT_EXPIRE_MINUTES` (default 7 days), `DATABASE_URL` (default
`backend/data/app.db`, an absolute path anchored to the backend directory),
`ALLOWED_ORIGINS` (default `http://localhost:5173`), `LOG_LEVEL` (default `INFO`).

`JWT_ALGORITHM` is **no longer configurable** — it is a module constant. Read from the
environment it could be set to `none`, which PyJWT accepts as the unsigned algorithm,
and every token would then verify.

`VITE_API_BASE_URL` is derived by `dev.run.sh` from `BACKEND_PORT` and exported, so the
frontend cannot end up pointing at a port the backend is not on. Set it yourself only to
reach a backend the script did not start; an explicit value in your environment wins.

All `.env` files are gitignored and must be created locally.

### Quick start

`Application/dev.run.sh` handles everything — it creates the backend virtualenv,
installs both dependency sets on first run, checks that the required `.env` keys
are present and the ports are free, then starts both services with prefixed,
colour-coded output. Ctrl+C stops everything it started.

```bash
cd Application
./dev.run.sh              # backend + frontend
./dev.run.sh backend      # uvicorn only
./dev.run.sh frontend     # vite only
./dev.run.sh docker       # full stack via docker compose
./dev.run.sh install      # install dependencies, then exit
```

Each service prints its URL on startup. Dependency installs are skipped on later
runs unless `requirements.txt` or `package-lock.json` changes. Override a port
with `BACKEND_PORT=8005 ./dev.run.sh`.

The manual equivalents are below, if you'd rather drive the services yourself.

### Running with Docker Compose
```bash
cd Application
docker-compose up --build
```
Frontend on `http://localhost:5173`, backend on `http://localhost:8000` (bound to loopback only). The SQLite file is bind-mounted at `backend/data/app.db` so it survives rebuilds and stays visible from the host.

Note that Vite inlines `VITE_*` values at build time, so changing `VITE_API_BASE_URL` or `VITE_GOOGLE_CLIENT_ID` requires a rebuild, not just a restart.

### Running locally (without Docker)

**Backend:**
```bash
cd Application/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Tables are created on startup via `Base.metadata.create_all`. Interactive API docs at `http://localhost:8000/docs`.

**Frontend:**
```bash
cd Application/frontend
npm install
npm run dev
```

### Inspecting the database
```bash
cd Application/backend
python3 -m app._database.check_state
```
Prints every user with their course count, and every course with its per-category
weights, flagging any whose weights sum over 100.

Note it does this **at import time**, and prints every user's id, name and email — so
importing it for any other reason also dumps that to stdout.

**Back up `data/app.db` before any migration.** Several `app.db.backup-*` files exist and
are gitignored.

---

## Testing

The project had no automated tests of any kind, which is the single fact that best
explained the shape of `Ideas/audit.md`: nearly every defect in it is one a test would
have pinned down, and several were re-runs of bugs already fixed once elsewhere.

```bash
cd Application/backend
.venv/bin/python -m pytest tests/ -q
```

Coverage is deliberately narrow and aimed at the defects most likely to be
reintroduced by a later refactor — the money-integrity and account-takeover paths, and
the session/throttle mechanisms:

| File | Covers |
|---|---|
| `tests/test_money_integrity.py` | Deposit and transfer group semantics |
| `tests/test_auth_integrity.py` | The email-change takeover chain |
| `tests/test_session_integrity.py` | Revocation, required token claims, login throttling |

`tests/conftest.py` gives every test a fresh in-memory database and deliberately does
**not** import `app._database.db`, whose engine is bound to the real `data/app.db`. A
test that can reach the live ledger is worse than no test.

---

## Known Gaps

### Not yet built
- **Calendar and Tasks** have no database models, schemas, or service layers — their
  routes return hardcoded sample dicts. The target schema for `events`, `tasks`, `goals`
  and `classes` is sketched in `app/_database/design.txt` (which is Postgres DDL for a
  SQLite app, so read it as intent rather than as something to run), including
  recurrence rules and "ends by" dates. Recurrence was deliberately deferred to
  Calendar so **one engine** serves it, repeating tasks and recurring payments alike.
- **Notes, Goals and Study Analytics** are not started.
- **Shared UI kit** — `shared/components/Modal.tsx` is now real and all ten dialogs use
  it. `{Button,Card,Checkbox,Input}.tsx`, `shared/hooks/{useDebounce,useLocalStorage}.ts`
  and `shared/utils/{dateUtils,formatters,mathUtils}.ts` are still empty, so everything
  other than the dialog shell is still hand-rolled.
- `SchedulePage.tsx`, `app/router.tsx` and `features/grades/hooks/UseAssignments.ts` are
  empty; routing lives inline in `App.tsx`. `features/calender/` is **misspelled**, and
  Calendar is the next module to build — worth renaming before imports exist.
- Roughly 21 zero-byte files remain across the frontend. They read as existing
  scaffolding when nothing is there.

### Wired but incomplete
- **Tailwind is now wired.** `vite.config.ts` registers `@tailwindcss/vite` and
  `@vitejs/plugin-react`, so utility classes are generated and Fast Refresh works.
  For four sessions this section claimed the decision was being deferred because
  registering the plugin *would* switch on Preflight. That premise was false:
  Preflight was already shipping and already active, because Vite resolved the bare
  `@import "tailwindcss"` and inlined the package's raw CSS verbatim. The app's
  appearance already incorporated the reset, so the option described as "safe" —
  deleting the import — was the one that would have changed how it looked.

  Registering the plugin turned 332 previously-inert utility classes live, and fixed
  a real bug for free: `max-h-[70vh] overflow-y-auto` on the Add/Edit Course forms was
  the only scroll container those dialogs had, and it did not exist, so on a
  1366×768 laptop the submit button sat off-screen and could not be clicked.
- `features/grades/api.ts` now has `updateCategoryWeights`, `recordGrade`,
  `searchCourses` and `fetchDashboard`; the dashboard endpoint is wired and
  `CourseSearch` uses the server-side `/courses/search` typeahead.
- There is **no email verification flow**, so a local account's `email_verified`
  only ever becomes true by linking Google. A real verification email would let
  local accounts stand on their own and would remove the password-drop on link.
- There is no password *reset* (forgot-password) flow.
- **Session revocation exists now**, but only in one direction: changing a password
  invalidates every token outstanding at that moment. There is still no refresh
  mechanism and no per-device session list, so the expiry remains 7 days. See
  *Sessions and revocation* below.
- `axios` has been removed. `requirements.txt` is still a full `pip freeze` and carries
  `firebase_admin`, `openai`, `google-cloud-storage`, `google-cloud-firestore` and
  `grpcio` — none of which appear anywhere in the code, and which add hundreds of MB to
  every virtualenv and image.
- `app/temp_data/store.py` and the empty `Grades/utils/errors.py`, `Users/utils/errors.py`, and `api/api.txt` are leftovers from before the database existed.

### Data integrity
Grade `score` is nullable, so an assignment can be added before it is marked;
every averaging function already skipped `None` scores. A score above its
`max_score` is rejected on create, on partial update, and on the
`/score` shortcut — the update paths check after applying changes, since a
partial update can raise the score or lower `max_score` independently.

### Schema migrations
There is no Alembic. `Base.metadata.create_all` only creates missing *tables* —
it never alters an existing one — so columns added later are applied by
`app/_database/migrations.py`, which runs on startup and is idempotent. Anything
beyond adding a nullable column (renames, type changes, backfills) will need a
real migration tool.

Note also that `DATABASE_URL` now defaults to an absolute path anchored to the
backend directory (`backend/data/app.db`). It previously defaulted to
`sqlite:///./app.db`, which resolved against whatever directory uvicorn was
started from, so a local run and `docker-compose` (which bind-mounts
`backend/data`) silently used two different database files.

### Repository hygiene
**Fixed.** The repo tracks **156 files**: no `node_modules`, no `__pycache__`, no
`.pyc`, no `dist/`. An earlier version of this section said 1150 of 1278 tracked files
were dependencies and told you to run `git rm -r --cached` — following that now would
do damage, so it has been removed.

`.gitignore` needs **both** `*.db` and `*.db.backup*`; do not "simplify" that away, as
a backup filename does not end in `.db`. `backend/.dockerignore` needs the same care
and previously lacked it, which baked nine real database backups into the image.

A stray `npm create vite` scaffold at the repository root — `package.json`,
`package-lock.json` and a 51 MB `node_modules`, with no `index.html` and no `src/` —
has been removed. It declared `typescript@6.0.3` against the frontend's `5.9.3`, and
because Node resolution walks upward, a pruned `frontend/node_modules` would have
silently resolved a different TypeScript major.

---

## Security

`Ideas/audit.md` is the current, verified list; `Ideas/fix.txt` was an earlier pass and
has been folded into it (including seven findings that did not survive re-checking).

### Closed

| Issue | What it was |
|---|---|
| Account takeover via email change | `update_user` wrote `email` through a blanket `setattr` loop and never cleared `email_verified`, so the Google-link guard was bypassable. Changing the address now clears the flag. |
| Empty `JWT_SECRET` accepted | Compose substitutes `""` for an unset variable and Pydantic accepted it for a required `str`, so the server booted and signed every token with a zero-length HMAC key. Now `Field(min_length=32)`, and the algorithm is a module constant rather than an env-overridable setting — `JWT_ALGORITHM=none` was otherwise reachable. |
| Deposit corruption (two bugs) | `group_id` meant both "transfer pair" and "deposit split". Deleting one leg of a split deposit deleted all of them; editing one negated a sibling into an impossible negative-income row that vanished from every view while still moving the balance. Both paths now branch on `kind`. |
| Cross-tenant category write | `create`/`update_transaction` trusted the client's `category_id`, and `delete_category`'s `UPDATE` had no `user_id` filter — so deleting your category rewrote someone else's row. Ownership is checked on write and the delete is scoped. |
| Transfer halves desynchronising | The date/description carry-over sat inside `if new_amount is not None`, so editing only a transfer's date moved one leg and left the other in a different month. |
| No rate limiting on `/login` | One bcrypt verification per request, unbounded. Now throttled — see below. |
| No session revocation | See *Sessions and revocation* below. |
| No logging of any kind | Authentication attempts and deletions are now recorded — see below. |
| Real data baked into the Docker image | `.dockerignore` matched `*.db` but not `app.db.backup-*`, so nine backups of real financial data landed in an image layer, invisible behind the runtime bind mount. |

### Sessions and revocation

Each token carries the **session epoch** it was minted under, and the account carries
its current epoch. A mismatch is refused. Changing a password bumps the epoch, which
invalidates every token outstanding at that moment, and returns a replacement token for
the caller — so a stolen token elsewhere dies immediately while the person who just
proved they know the old password is not thrown out of the page they are standing on.

A counter rather than a timestamp, deliberately. Comparing a token's `iat` against a
revocation *time* cannot distinguish a token minted just before the revocation from one
minted just after, because `iat` has whole-second granularity — signing straight back in
could be refused. This was not theoretical: it is what the first implementation did, and
its own regression test caught it. Integer equality has no such window, no timezone
handling, and nothing to prune. A `jti` denylist was the other option; it buys
per-token revocation, which is worth nothing without a per-device session list to
revoke from.

The check lives in `get_current_user`, where the user row is already loaded — every
authenticated route reaches it through `CurrentUser` or `VerifiedUserId` — so
revocation costs no extra query.

Tokens minted before the epoch claim existed read as epoch 0, which is every account's
starting epoch, so they stay valid until something actually revokes them.

### Login throttling

A sliding window per `(address, client)` and a looser one per client alone, checked
*before* the password is verified so a blocked caller costs no bcrypt work. Eight
failures per address per 15 minutes; a success clears that address's history, so one
forgotten password followed by the right one does not leave the account half-locked.
Returns 429 with `Retry-After`. Knobs are at the top of
`Auth/services/login_throttle.py`.

Hand-rolled rather than adding a dependency, and its limits are worth stating: the state
is in this process's memory, so it resets on restart and is not shared between workers.
More than one worker, or several instances, needs a shared store instead.

Note the trade-off: while an address is throttled, **the correct password is also
refused**. That is what makes guessing expensive, and it is what lockout means, but it
can lock you out of your own app for up to 15 minutes after eight fat-fingered attempts.

### Logging

`app/shared/audit.py`. Two kinds of event are recorded: every authentication attempt
(successes at INFO, failures at WARNING) and every deletion of a course, grade, account,
transaction, category or user. Never a password, a hash, or a token. Emails *are*
recorded on authentication, because an auth log that cannot say which account was
attacked is not much use — so the log deserves the same care as the database.

### Still open

| Issue | Severity | Impact |
|---|---|---|
| JWT in `sessionStorage` | Medium | Any XSS steals a token. There is no XSS vector today — no `dangerouslySetInnerHTML`, no `innerHTML`, no `eval` anywhere in `src/` — but this is the payload if one appears. Moving it to an httpOnly cookie is what would *introduce* a CSRF requirement, which is why it has not been done casually. |
| 7-day expiry, no refresh | Medium | Shortening it without a refresh mechanism just means signing in more often. Needs a deliberate decision about session length. |
| Cascading hard deletes, no soft delete | High | Deleting an account wipes every course and grade immediately. The cascades are also *incomplete* — `spend_categories` and `budget_targets` are orphaned rather than removed, and SQLite does not enforce foreign keys without `PRAGMA foreign_keys=ON`. Both halves want fixing together. |
| `allow_methods=["*"]` / `allow_headers=["*"]` with `allow_credentials=True` | Medium | Authentication is a bearer header and no cookie is ever set, so the flag grants nothing and only widens what a misconfigured `ALLOWED_ORIGINS` would expose. |
| No HTTPS/HSTS in `nginx.conf` | Medium | Listens on 80 with no redirect. Tokens cross the network in plaintext, which makes the 7-day lifetime considerably worse anywhere but localhost. |
| No indexes, no unique constraints | Medium | Every hot query is a full scan. `(user_id, code)`, `(user_id, name)` and `(user_id, account_id, month)` are enforced only by check-then-insert in Python, so all of them race. |
| SQLite unconfigured for concurrency | Medium | No WAL, no busy timeout, against a 40-thread threadpool. Two simultaneous writes surface as `database is locked` → an uncaught 500. |
| No rate limiting on `/register` or `/google` | Low | `/google` is bounded by Google verifying the token; `/register` is account-spam rather than credential guessing. |

## Repository & Branches

```
origin  https://github.com/fawwaz9/Account.git
```

- **`main`** — the integration branch, and now the only one that matters. Work
  merged back and development happens here.
- Branch off `main`, and off `main` only. Stacking on unmerged work caused
  phantom conflicts twice, and once cost an afternoon to a "the fix is not there"
  report that turned out to be a branch without the fix in it.

**A push to `main` deploys the frontend**, because Cloudflare Pages builds from
it. The API does not deploy itself — that is a manual `gcloud run deploy`. See
`Ideas/deployment.md`.

### Where the planning lives
**[`Ideas/README.md`](Ideas/README.md) indexes all of it.** `Ideas/to_do.txt`,
`Ideas/fix.txt` and `Ideas/features.txt` have been folded into the files below
and deleted:

| File | Holds |
|---|---|
| `Ideas/design/` | **Start here.** One note per module plus an overview: how each works and why |
| `Ideas/session-handoff.md` | Where the project is right now — branch, live URLs, data, what is left |
| `Ideas/next.md` | The feature backlog per module, and the order to build it in |
| `Ideas/shipped.md` | What is already built and deployed — check before proposing anything |
| `Ideas/audit.md` | Every known defect, tiered by severity, with what was verified how |
| `Ideas/deployment.md` | The 39-step deploy runbook, all of it done bar the last two |
| `Ideas/plan-a-decisions.md` | Why each deployment choice was made, and what would change its mind |
| `Ideas/ROLLBACK.md` | What to do when it is broken. Commands first |
| `Ideas/jobs-plan.md` | The worked example: a module planned, built and logged |
| `Ideas/core.txt` | The original goal, in the author's own words |

Docker has since been run end to end — that was Phase 0 of the deployment, and
it found a real defect nothing else would have (local builds are `linux/arm64`;
Cloud Run needs `amd64`).

---

## License

Not yet specified — personal project.
