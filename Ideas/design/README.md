# The shape of this app

A student life-management app: grades, money, time and work, in one place
because they are one life. The point is not four tools under one login — it is
the questions that only exist where two of them meet. What did this course cost.
Can I afford to drop it. Is the job eating the term. When is there actually room
to study.

- [TEMPLATE.md](TEMPLATE.md) — the design note format, and why each heading is there
- [grades.md](grades.md) · [finances.md](finances.md) · [calendar.md](calendar.md) ·
  [tasks.md](tasks.md) · [jobs.md](jobs.md) · [users-and-auth.md](users-and-auth.md)
- [../jobs-plan.md](../jobs-plan.md) — the worked example, with its build log
- [../whats_next.txt](../whats_next.txt) — what is shipped, what is next, and the
  accumulated notes
- [../session-handoff.md](../session-handoff.md) — where the project is right now
- [../deployment.md](../deployment.md) — how it got on the web, and
  [../ROLLBACK.md](../ROLLBACK.md) for when it breaks

---

## Layout

```
Application/
  backend/
    app/
      <Module>/schemas/     Pydantic: the shape of a request and a response
      <Module>/services/    the logic. Takes a Session, returns schemas
      <Module>/utils/       pure functions. No session, no models
      api/routes/           thin. Parse, call one service, map errors to status
      _database/            models, engine, migrations
      shared/               tokenizer, audit, error bodies, money, dates
    tests/                  911 cases
  frontend/
    src/features/<area>/    api.ts, types.ts, components/, hooks/
    src/pages/              one per route, composing features
    src/shared/             components, utils, hooks used by more than one area
    src/services/           apiClient, endpoints
    src/styles/             one stylesheet per area
```

Twenty-four tables. FastAPI + SQLAlchemy 2.0 + Pydantic v2; React 19 + Vite 7 +
Tailwind v4 + react-router-dom.

**Two databases, one schema.** SQLite is the local default and the working copy
lives at `data/app.db`. Production is Postgres 17 on Supabase, reached through a
transaction-mode pooler. The same models drive both; the two places that differ
are handled in `_database/db.py` and explained in `../plan-a-decisions.md` D2.6.

## The rules that hold it together

### Compute on the server, render on the client

A figure is calculated in a service and attached to the schema the client reads.
The client's job is to display it.

This is not style. The course page once did its own arithmetic and disagreed with
the course average shown on the same screen — two answers to one question with
nothing to say which was right. Anything derived now travels with the thing it
describes: `course.average`, `task.risk`, `shift.counted_minutes`.

### Layers, and which way they point

`routes → services → models`, and `utils` under everything.

Utils are pure: dates in, dates out, no session. That is what lets anything read
them, and it is the fix that resolved a real import cycle — `effective_target`
lived in a service, Tasks needed it, and importing it closed a loop through four
modules. Moving it to `Grades/utils/terms.py` ended that. **A rule two modules
share belongs in utils.**

### One engine per idea, with named consumers

Where two features would do the same thing, one of them owns it and the other
calls it.

The recurrence engine is the clearest case: one rule format in five columns,
four consumers, and the differences between them are the interesting part.

| Consumer | Materialises |
|---|---|
| Class times | never — expanded on read |
| Shifts | never — expanded on read |
| Recurring payments | only once the payment has happened; a balance is the sum of its rows |
| Repeating tasks | a rolling window ahead, so each occurrence can be ticked off |

A repeating thing expanded on read has **no row per occurrence**. Anything that
needs to record something about one date has to key on `(source_id, on_date)` —
that is what `shift_records` does, and what `skipped_dates` works around.

### Only money that moved goes in the ledger

The ledger is a record of what entered or left an account. Nothing else.

Everything else lives with the feature that knows about it. A tuition deduction
(a bursary) and a paycheque deduction (tax) are both real, both affect what you
were charged or earned, and **neither ever entered an account** — so neither is a
transaction. They sit on their own records, and only the net reaches the ledger.

This is why the Grades page can say what a course cost while the ledger shows one
tuition line, and why the Jobs page can show gross pay and an effective hourly
rate that the budget could never compute.

### Errors have meanings

- **422** — a parse-time Pydantic validator. The request was malformed.
- **400** — a service-layer validator. The request was well-formed and wrong.
- **404** — missing, or belongs to another user. Deliberately the same answer, or
  the API confirms which ids are real.
- **403** — the URL's `user_id` is not the token's. A different check, at the path
  rather than the resource, where there is nothing to conceal.

### Cascades go both ways, and are mutation-tested

A record that owns ledger rows must remove them, **and** removing the rows must
remove the record. Only the first half was written for tuition once: deleting the
ledger row left the payment behind, still answering "what did this course cost"
for money that no longer existed, with nothing in the UI able to reach it.

Both halves now have a test, and the test is verified by reverting the fix and
confirming it fails.

## Conventions worth knowing before writing code

**Migrations are additive and idempotent.** `ADDED_COLUMNS` in
`_database/migrations.py`. New tables come from `create_all`. Back up
`data/app.db` first.

> **They no longer run on startup in production.** The deployed service sets
> `RUN_SCHEMA_ON_STARTUP=0`, so **a new table or column does not reach Supabase
> by deploying.** Run it yourself, once, as part of the deploy:
>
> ```sh
> DATABASE_URL="$SUPABASE_DATABASE_URL" python -m app._database.schema
> ```
>
> It is idempotent, so a repeat is harmless. Locally the default is still on and
> nothing changes. This is the single easiest way to ship a change that works on
> your machine and 500s in production.

**Route order is load-bearing.** FastAPI matches in declaration order, so every
literal path goes above its `/{param}` catch-all. `/courses/resolve` below
`/courses/{course_id}` parses as an id and 422s. There is a test asserting the
ordering for `/tasks/timing`.

**JSON columns do not track mutation.** Assign the whole list or dict, and
serialise before assigning — a `date` or a `time` put into one raises at commit,
not at assignment. This has bitten three times: `events.skipped_dates`, a
recurring rule's, and `users.preferences`, the last taking out every Settings
save with a 500.

**`db.refresh()` discards pending edits.** It reloads the row from the database.
It silently undid a corrected paycheque gross. `db.flush()` is almost always what
was wanted.

**Money is float here.** Round to cents at the boundary with `money()` from
`app/shared/money.py`, compare with a tolerance or use `Decimal`, and never
assert float equality. Where a split has to sum to its whole, put the rounding
remainder on the largest share.

> **Do not write a local `money()` or `today()`.** They existed thirteen times
> between them — `money` in four services, `today` in nine — byte-identical
> every time, and a fifth service imported `money` from *another service* rather
> than add a fifth copy, which is a layering rule turning into a suggestion.
> Both now live in `app/shared/`, next to the tokenizer and the audit log. The
> `+ 0.0` inside `money()` is load-bearing and narrower than it looks: it
> normalises an input that is already `-0.0`, so a balance of nothing does not
> read as `-0.00`. It runs before the rounding, so it does *not* catch a small
> negative that rounds away — `money(-0.004)` is still `-0.0`, and there is a
> test pinning both halves so neither gets tidied into the other.

**Fixed-size buttons need their own padding.** The base `.container button` rule
sets `padding: 7px 14px`, so anything with a fixed width and height needs
`display:inline-flex; padding:0; box-sizing:border-box` or its glyph sits low and
right. This has caught five controls.

**Every page is a `lazy()` route.** `src/app/App.tsx` loads the nine signed-in
pages on demand; `LoginPage` and the shell stay eager. A new page added with a
static import silently folds itself back into the first download and nothing
fails to say so. The one `Suspense` lives in `MainLayout` around `<Outlet />`,
so the sidebar stays put while a route arrives.

> **One stylesheet preserves its CONTENTS, not its ORDER.** This is the trap,
> and it shipped a visible regression before it was understood.
> `cssCodeSplit: false` keeps every rule in one file, so the rule *set* is
> identical — which is reassuring and insufficient. The *order* within that file
> follows the module graph, and making the routes lazy changed the module graph.
> `.budgetPage` and `.accountPage` each carried a `max-width: 980px` that had
> never once applied, because `.container` on the same element sets
> `max-width: none` and globals.css happened to be emitted after them. The order
> flipped, the dead rules woke up, and both pages went narrow with no CSS edited.
> **Never let a page class that shares an element with `.container` set its own
> `max-width`** — the two are both unlayered and one class of specificity, so the
> winner is decided by the bundler. Clamp an inner wrapper instead.

> Guarded by `src/styles/pageWidth.test.ts`, which fails if a class used beside
> `container` declares its own `max-width`. Two controls, because the scan
> reports "nothing wrong" and so does a scan that reads nothing: one asserts it
> sees the pages, the other that it can see a `max-width` that *is* there.
> Vitest stubs CSS imports as empty strings, so it reads from disk — a glob
> returns the filenames with no contents and passes while proving nothing.

> **`build.cssCodeSplit` is deliberately `false`.** Vite's default is a
> stylesheet per async chunk, which makes the cascade order depend on the order
> pages were visited — and this app cannot take that, since `main.tsx` loads
> `calendar.css` eagerly for the shared `.calRow`/`.calField`/`.calInput` form
> primitives and the base `.container button` rule has already caught five
> controls. The whole stylesheet is 16.7 KB gzipped against the JavaScript's
> 136 KB, so splitting it would win almost nothing and risk a silent visual
> class of bug. Splitting the routes cut the first download from 136 KB to
> 81 KB gzipped. It did **not** leave the stylesheet unchanged — see above.

**One stylesheet means one namespace.** `cssCodeSplit` is false, so every
`styles/*.css` is concatenated and a bare class selector reaches every page.
Two files defining the same name are in a cascade fight decided by whichever
the bundler emitted last, and the loser is usually a page whose author never
saw the other file. `.categoryList` was the budget's "Where it went" list *and*
the grade-category list on a course page, and the budget rules won: grade rows
were inset from their own border, given a second separator, shrunk a step and
spaced apart. **Scope a page's rules under that page's own container** — the
budget list is `.categorySpend .categoryList` now. `classCollisions.test.ts`
fails on any bare class name defined in two stylesheets.

**Tailwind scans comments too.** It looks for candidate class names in source
files and cannot tell prose from markup, so writing a bare utility word in a
comment adds a real rule to the production stylesheet. One did: a comment in
`chunkErrors.ts` put an unused `text-transform` rule in the CSS.

**Stage explicit paths when committing.** `git add -A` swept in-flight edits into
commits twice.

**Never run a script against the real `data/app.db`.** Copy it to the scratchpad
and point the engine at the copy. And never compute a delete filter — one
`getattr`-based one wiped 218 rows across 27 courses, silently, while the script
printed success.

## Where the modules meet

The joins are the reason the app exists, so they are worth naming.

| Join | How |
|---|---|
| Grades × Finances | a tuition payment prices a term from per-credit rate × credits. One ledger line; what each course cost is a Grades answer, not a row |
| Grades × Calendar | a dated grade becomes either a task that closes when the score lands, or a calendar block — the student chooses, because a deadline and an exam are different things |
| Grades × Tasks | a task from a below-target course carries a risk badge and leads its date group |
| Calendar × Tasks | tasks with due dates draw on the calendar; the week's load counts booked hours against estimated ones |
| Calendar × Jobs | a shift is an event, so work competes with study for the same hours in the free-block finder |
| Jobs × Finances | a paycheque's net splits across accounts by income share, like any other deposit |

## Adding a module

1. Write the design note from [TEMPLATE.md](TEMPLATE.md). Fill in *What already
   exists* first — it usually changes the rest.
2. `app/<Module>/{schemas,services}/`, and `utils/` if two modules will share a
   rule.
3. Tables in `models.py`; new columns into `ADDED_COLUMNS`.
4. `api/routes/<module>.py`, registered in `main.py`. Literal paths above
   catch-alls.
5. `src/features/<module>/` with `api.ts`, `types.ts`, `components/`, `hooks/`;
   a page; a stylesheet; a nav entry.
6. Tests as you go, and mutation-test every guard.
7. Update `whats_next.txt` as part of landing it, not afterwards.
