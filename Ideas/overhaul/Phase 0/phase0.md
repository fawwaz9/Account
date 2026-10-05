# Phase 0 — Safe and measurable

Taken from `account-vision.md` (§4 Phase 0, §5.6, §8, §9.1, §9.9, §9.10, §10, §11,
§14, §15 Foundations, §16 Phase 0) and brought up to date on 2026-10-04. The vision
was written on 2026-10-02, and two things have moved since. Section numbers below
point back into the vision.

---

## What Phase 0 is for

Nothing ships on top of Phase 0 until it is done. None of its items is a feature
in the usual sense. Each is a prerequisite for the decisions after it:

- **Safe.** Grades, full ledgers and password hashes for real people are in this
  database, and the roadmap adds shared data on top. The worst failure is one
  student seeing another student's grades or balances, not a wrong number on a
  screen (§3.1).
- **Measurable.** Every later phase gate is a number nobody can read today
  (§11). Without measurement, the gate that decides whether Phase 0 is done is
  also unreadable (§12.7).

Two rules from the vision apply here directly:

1. Nothing that shares data ships before isolation is enforced by the database.
2. No phase is declared done on a metric nobody can read.

**This is the gate on open signup.** If Phase 0's isolation slips, open signup
waits (§9.1).

## Exit criteria: Phase 0 → Phase 1

From §11. All five must hold:

- [x] Database-level isolation is live, and the enumerated two-user route test
      passes in CI. *(2026-10-05: the API connects as `account_app`)*
- [x] The surplus copies of production data are deleted. *(2026-10-04)*
- [x] Analytics are reporting. *(2026-10-05: counters recording in production;
      `scripts/usage_report.py` is run when you choose to)*
- [x] Push notifications are delivering. *(2026-10-05: test notifications
      received on laptop and phone; scheduler running every 5 minutes)*
- [ ] Time-to-first-value is under 5 minutes. **Deferred by you, 2026-10-05:**
      most onboarding will come from syllabus parsing and other automations
      that backfill data, so measuring today's manual setup would time the wrong
      thing. Measure it once those exist. See D12.

---

## Status at a glance (updated 2026-10-05)

**All of Phase 0 is live in production.** The one exit criterion left open,
time-to-first-value, was deferred on purpose (D12). Production steps are in
`phase0-runbook.md`. Every decision is in `phase0-decisions.md`.

| # | Item | Status |
|---|---|---|
| 1 | Delete the surplus Supabase project | **Done**, by you, 2026-10-04 |
| 2 | Database-level isolation (RLS) | **Live** 2026-10-05: the API connects as `account_app` |
| 3 | Enumerated two-user route test | **Done.** 313 cases, plus non-interference; runs in CI on SQLite and Postgres |
| 4 | Analytics | **Live** 2026-10-05; report via `scripts/usage_report.py` |
| 5 | Push notifications and a scheduler | **Live** 2026-10-05. No native client needed |
| 6 | Onboarding | **Shipped** (frontend), 2026-10-04. The 5-minute measurement is deferred (D12) |
| 7 | Confirm every destructive path | **Done** 2026-10-03 |

Found and fixed along the way, all live:
- the email-wildcard account-takeover path
- three deletes that returned 500
- PATCH transaction returning 500

---

## 1. Delete the surplus Supabase project — DONE 2026-10-04

The owner deleted it ("Account_backup") on 2026-10-04. A repo-wide search found
nothing but documentation referring to it; those docs now say it is gone.
One of the five exit criteria is met.

**What.** Project `ommqbgaasrusrlizzyzm` was created for a restore drill. It holds
a full copy of every user's financial data and password hashes. Its password is
rotated and nothing points at it (§9.10).

**Why it's first.** It is the cheapest, highest-severity action in the vision
(§14 Cut #1). Under §3.1, a surplus copy gets deleted rather than left dormant: it
is a breach waiting on an unrelated mistake. It costs nothing to remove (§15).

**Steps:**
1. Confirm nothing references it. Search the repo, the GitHub secrets, the Cloud
   Run environment, and `.env` files for `ommqbgaasrusrlizzyzm`.
2. Confirm the production project's own backups are current. The `backup.yml`
   workflow runs before every API deploy.
3. Delete the project in the Supabase dashboard. Only the owner can do this step.

**Done when** the project no longer appears in the Supabase organization.

---

## 2. Database-level isolation

**What it is today** (§5.6). The API authenticates the caller and resolves a
verified user id through one dependency. Every query then filters on `user_id`,
or reaches its rows through a parent that does. Correctness depends on each query
remembering its filter. Nothing in the database catches one that forgets.

**Target.** Per-user tables get a database-level predicate, so a forgotten filter
fails closed (returns nothing) instead of leaking. **Do it now, while every table
is single-user.** Today it is a migration; once tables are shared it becomes a
retrofit (§4).

**The tables** (§2, current state). There are 26:
- **19** carry `user_id` directly.
- **6** are children reached through a parent:
  - grades and category weights, through courses
  - snoozes, through tasks
  - contributions, through sinking funds
  - deductions, through paycheques and tuition payments
- **`users`** is the root.

The 19 get a simple policy. The 6 children need either a policy that checks the
parent row, or a denormalized `user_id`. Choosing between those is part of the
design work.

**Open question carried from §10: the mechanism.** All three options satisfy §3.1.
They differ in operational cost:
- **Per-request session claims.** Something like `SET LOCAL app.user_id = …` at
  the start of each transaction, and policies that read it. This fits how the app
  works now, with one connection role and a SQLAlchemy session per request (§4
  expects exactly this).
- **Forwarded-JWT row policies.** This is the Supabase-native pattern, but the
  app issues its own JWTs rather than using Supabase Auth.
- **Per-user database roles.** The strongest separation, and the heaviest to run
  at 20 or more users.

**Facts to settle before building:**
- **The role the API connects as.** In Postgres, a table's owner and any superuser
  bypass row-level security unless the table uses `FORCE ROW LEVEL SECURITY`. If
  the API connects as the owner of these tables, enabling policies alone changes
  nothing. Expect a dedicated, non-owner application role. Creating it means a
  schema step and a new production secret, so it goes through the usual
  backend-deploy permission.
- **The pooler.** The app uses Supabase's pooler. With transaction pooling, a
  claim must be `SET LOCAL` inside the transaction; a session-level `SET` could
  carry over to another request on the same connection. Check which pooler mode
  the API's URL uses.
- **Local and CI databases are SQLite, which has no row-level security.** The
  test suite and CI run on SQLite by default (`tests/conftest.py`). Policies can
  only be proven on Postgres, so CI needs a Postgres service container (free on
  GitHub Actions) for at least the isolation suite.
  `TEST_DATABASE_ALLOW_REMOTE` must still never appear in a workflow. This means
  a disposable Postgres inside the CI job, never Supabase.
- **Background work.** The backup workflow, the schema-conformance gate (the
  `ci_reader` role) and any future scheduler (item 5) need their own deliberate
  access, rather than inheriting a bypass by accident.

**Design rules carried forward from §5.6.** These are not built in Phase 0, but
the policy design must not block them:
- **Shared aggregates never relax the policy.** Class distributions and
  leaderboards are precomputed into their own rows by a job. No request-time query
  joins across users.
- **Collaborator write access** (shared tasks, Phase 2) is membership-based,
  through an explicit join table. Only the owner can write membership, or a
  collaborator could add themselves to anything.
- **Disclosure is explicit and opt-in per feature.** Private by default suits
  grades and money; it is the wrong description of a leaderboard.

**Done when:**
- Every per-user table has a policy and is forced.
- The API connects as a non-owner role.
- A query with its `user_id` filter deliberately removed returns zero rows on
  Postgres, and a test proves it.

---

## 3. Enumerated two-user route test

**What.** Walk every route with two users and assert that the first cannot read
or change the second's rows (§4, §15). Coverage today is per feature, and depends
on someone having remembered.

**Scale today.** 140 route decorators under `app/api/routes` as of 2026-10-04.
The vision counted 139; the cash-tip endpoint is the addition.

**Approach worth reusing.** Use the shape of `deleteConfirmations.test.ts` from
2026-10-03. It **enumerates** the routes from the app itself (`app.routes`) and
fails if any route has no isolation case, with an explicit allowlist for routes
that hold no per-user data (health, login, register). A hand count missed one
delete in ten; an enumeration can't. Each new route then adds a case, which is the
small permanent cost §15 names.

**What each case checks.** User B's id in the path, or B's row id in the body,
gets the route's existing "not yours or not there" answer, usually 404. Nothing
of B's is returned or changed, and B's row counts are compared before and after.

**Relationship to item 2.** Run the suite twice:
- **On SQLite**, it proves the application-code filters.
- **On CI's Postgres with policies on**, it proves the database backstop.

The strongest form of the backstop test removes a filter on purpose and still
sees zero rows.

**Done when** the suite covers every enumerated route, runs in CI on both
databases, and a deliberately removed filter makes it fail.

---

## 4. Analytics

**Why it's in Phase 0** (§8, §14 meta-cut). Every gate in §11 is unreadable
without it. The rule the vision states is: **no new feature ships until module
adoption is measurable.** The three zero-row features (sinking funds, reminders,
and the monthly category override with two rows) happened because nothing could
have caught them.

**What to measure first:**
- **The universe test.** Rooms visited per week per person, and whether anyone
  opens the app for two different reasons in one week (§1, §13.2).
- **Adoption.** Users, weekly and daily active users, and retention.
- **Per-module adoption.** This is what lets a dead feature be killed on evidence
  instead of opinion. Investment-return readings are already waiting on it (§14
  Cut #5).
- **Engagement.** Tasks created, completion rate, grade entries. This is already
  one SQL query away in Postgres, so it needs no pipeline.
- **Reliability.** Uptime, response times, error rates.

**How** (§8). Engagement comes from aggregate queries. Product events (page and
module visits) come from something lightweight rather than homegrown, and retention
needs that event capture.

**Privacy rule.** This is friends' school and money data. Analytics are
aggregates only and anonymous, and the app says so out loud. Under item 2's rule,
aggregates are computed by a job, never by a request reading across users.

**Done when** the universe test, weekly active users and per-module adoption are
readable without writing a query by hand.

---

## 5. Push notifications and a scheduler

**Why.** Reminders are stored and served when the client asks, so one fires only
while the app is open (§2, §9.10). That is a promise the app doesn't keep. It
also unlocks the later reminders, spending guards and briefings (§15).

**Confirm the web-push path first** (§4, §15). If push forces a native client,
the cost changes character entirely. A fact to check early: on iOS, web push works
only for a site added to the Home Screen, which means a web app manifest and the
install step.

**Pieces:**
- **Delivery.** Web push with VAPID keys, which is free.
- **Scheduler.** Cloud Run scales to zero, so nothing in the API runs on a timer.
  Something external has to call it on a schedule: Cloud Scheduler, or a GitHub
  Actions cron. Its access needs the same deliberate scoping as item 2.
- **Permission UX and token churn.** §15 calls this the medium, ongoing
  maintenance cost.

**Decision attached** (§14 Cut #2). Reminders as built have zero rows in
production. Rebuild them on this scheduler, or cut them. A broken promise is worse
than a missing feature.

**Done when** a reminder arrives on a phone with the app closed, on both iOS and
Android or desktop.

---

## 6. Onboarding (under 5 minutes to value)

**Why.** A new user gets empty screens and a lot of typing (§4). Every point of
activation lost wastes whatever brought them in (§15). Open signup in Phase 2
makes this matter much more.

**What.** A guided setup, with empty states replaced by first value within
minutes. Revisit it with every feature added (§15).

**Measuring it** depends on item 4: time from registration to the first course,
transaction or task.

**Done when** the measured time-to-first-value is under 5 minutes.

---

## 7. Confirm every destructive path — DONE 2026-10-03

Shipped as "The three interface quality asks" (`Ideas/shipped.md`):
- There were **ten** unconfirmed delete paths, not nine.
- All ten now go through `DeleteConfirmModal`.
- The two that cascade (the sinking fund with its transfers, and the job with its
  shifts and cheques) say so, and say what survives.

`deleteConfirmations.test.ts` checks the **wiring** (a confirmation is rendered,
not merely imported), so a new delete without a dialog fails CI. Recoverable
actions (archive, soft delete, a paused rule) are exempt by an explicit allowlist.

One loose end: `Ideas/next.md`'s Quality of Life section still mentions "the nine
deletes".

---

## Suggested order

1. ~~**Delete the surplus project.**~~ Done 2026-10-04.
2. **The enumerated route test, against today's application-code filters.** It
   becomes the harness item 2 is proven with, and it may find a real leak before
   any policy exists.
3. **Database-level isolation**, with the Postgres CI service, proven by the test
   from step 2.
4. **Analytics.** Engagement queries can start any time in parallel. Event
   capture comes after isolation, so the aggregate job is built under the
   policies.
5. **Push and the scheduler**, after the iOS web-push check.
6. **Onboarding**, measured with step 4's numbers.

Steps 2 and 3 put safety ahead of measurement. §16 says to build high-impact,
high-feasibility first, which would put analytics earlier. The trade is a few days
of not being able to see usage, in exchange for closing the one failure §3.1 ranks
above everything.

---

## Open questions still standing

- **The isolation mechanism** (§10). Session claims, JWT policies or per-user roles.
- **The abandon condition** (§10, §12.20). Every phase has an entry gate and none
  has an exit.
- **Canvas sync** is out of Phase 0 and deferred (§4 "What moved"). Revisit
  only if shared syllabi don't cover the same ground.

## Inconsistency in the vision to fix

§16's Phase 2 row for open signup says "P0 isolation is the gate and **has already
cleared**." It has not cleared. §4's "What moved" table says it "clears in P0",
which is the accurate wording.
