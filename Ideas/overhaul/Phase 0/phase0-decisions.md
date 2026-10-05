# Phase 0 — decisions log

Written for: you, reviewing on your return what I decided while you were
away. Each entry gives what I decided, why, and what to say if you want it
changed. Newest at the bottom.

## Ground rules I held myself to

- **No production change of any kind.** No backend deploy, no schema step on
  Supabase, no secret change, no GCP change. Your standing rule is to wait for
  permission before any backend deploy, and you said nothing here should risk
  current data. Everything backend-side is built and tested on the `phase0`
  branch. The production steps are written as a runbook for you to approve.
- **No real data touched.** Nothing ran against `data/app.db` or Supabase. Tests
  used in-memory SQLite and a throwaway Postgres 17 container on 127.0.0.1.
  Mutation runs used scratch copies of the backend with `data/` excluded.
- **Frontend-only changes may ship**, per your standing rule, but only where they
  work against the API that is live today.

---

## D1. Isolation test: enumerate routes, check invariants rather than status codes

`tests/test_isolation.py`.

- **What.** It walks every route from `app.routes`, 313 cases. User B owns one
  row in every table, with a marker string in every text column. After each
  request A makes, three things must hold:
  - A sees nothing of B's.
  - No row of B's changed.
  - No changed row points at B's data.
- **Why invariants, not status codes.** Routes answer foreign ids with 404, 422
  or an empty 200. All three are fine; leaking is not. Checking statuses would
  mean 313 hand-written expectations that test the wrong thing. The one
  exception: a foreign `user_id` in the path must be exactly 403.
- **Why each forged id is also sent alone.** A request with every id forged
  is refused by whichever check runs first, which hides whether the later
  checks exist. Mutation testing proved this: forging all ids at once missed a
  removed account check that forging one at a time caught.
- **Real tokens.** Only `get_db` is overridden, so the whole auth chain is
  under test.
- **The world is dated "today" on the user's clock.** Lists default to the
  current month or week, and a world dated elsewhere let a list with no user
  filter pass. That was caught by mutation.
- **Proof the suite works. Corrected: my first claim here was wrong.** I
  first wrote that all 152 filter removals were caught. They weren't. Every
  one of those runs crashed at startup, because the scratch copies had no
  `Application/.env`, and my script counted an error as a catch. I found this
  when the RLS run showed the same crash.
  - The script now passes dummy settings and counts only a test *failure*.
    An error is reported as invalid, never as a success.
  - Each run starts with a control: an unmutated copy must pass.
  - The four hand mutations, which ran in the real tree and named the failing
    case, were real. The honest 152-filter numbers are in D6.
- **Allowlists stay explicit.**
  - `SKIPPED` holds one route, `/auth/google`, which calls Google over the
    network.
  - `VALIDATION_ONLY` is empty.
  - A route nobody has classified fails the test.

## D2. Fixed: PATCH transaction returned 500 for refusals

**Found by D1.** The service raises `ValueError` for a course or category that
isn't yours, and for an amount edit on a tuition row. The route didn't catch it,
so "Edit this through Pay Tuition" reached a real user as a bare 500.

- **Fix.** The route now catches it and returns 400 with the message, the same as
  the create route. A regression test is in `test_tuition.py`.
- **This is a backend change,** so it waits for a deploy with everything else.

## D3. Row-level security: no bypass anywhere, and switched on by changing the connection

`app/_database/rls.py`, `app/_database/identity.py`, `tests/test_rls.py`.

**Mechanism** (the open question in vision §10). Per-request session claims:
`set_config('app.user_id', <id>, true)` at the start of **every** transaction.
- **Why transaction-local.** Production uses Supabase's transaction pooler,
  where a session-wide setting could carry one request's identity into another
  request on the same server connection.
- **Why every transaction.** Services commit mid-request, so a single set at
  the start isn't enough. A SQLAlchemy `after_begin` listener re-applies it.
- **Why not the other two options.** JWT policies would mean adopting Supabase
  Auth, which the app doesn't use. Per-user database roles are heavy to run
  for 20 or more users.

**Policies**, generated from the models so a new table can't be forgotten:
- `users`: a row is yours if it is you.
- **19 tables** with `user_id`: a row is yours if it carries your id.
- **6 child tables**: a row is yours if its parent is.
- A table that fits none of these makes the generator raise.
- With no identity set, a query returns zero rows. That is the fail-closed
  property, and it's tested on every table.

**No bypass.** The five things that legitimately cross users each became a
narrow `SECURITY DEFINER` function that returns an id or a yes/no, never rows:
- sign-in by email
- Google sign-in
- the "email taken" check on registration
- the "email taken" check on email change
- the list of accounts due for purge

After that lookup, the code acts as that user. Even the 30-day purge deletes
each account while acting as it, so the cascade can only reach that user's
rows.

**Why the owner is never forced through the policies.** Today's API connects
as the table owner. `ENABLE ROW LEVEL SECURITY` without `FORCE` leaves the
owner unaffected, so installing everything changes nothing until the API's
connection is pointed at the new `account_app` role. Pointing it back is the
rollback, and it's instant. `FORCE` would have made today's API see zero rows
the moment it ran.

**What the app role can do.** Data only: SELECT, INSERT, UPDATE and DELETE.
No DDL, no superuser, no BYPASSRLS. Tested. The policies name only that role,
so Supabase's `anon` and `authenticated` roles get no rows from these tables.
That incidentally closes the Supabase Data API off from them.

**Proof** (`tests/test_rls.py`, Postgres 17, as the restricted role):
- Every table has the policy and is not forced.
- No identity: zero rows in every table.
- With an identity: exactly your own rows in every table.
- You can't update, delete, plant or re-own another user's rows, or hang a
  child row under their parent.
- The lookups are exact.
- **The whole 311-case isolation suite passes with the API connected as the
  restricted role.** So the switch breaks nothing the app does.

**A known limit I chose to accept.** A policy checks the row being written,
not the rows it points at. So under RLS alone, A could write a row of A's that
holds the id of B's account. That neither leaks nor damages: B's row stays
invisible to A, and B's totals only count B's rows. The application's
ownership checks stop it today, and the isolation suite tests them. Closing it
in the database would need composite foreign keys on every reference: a large
schema change for a case that can't leak. Say if you want it.

**Deploy gate.** The API now calls those functions to sign anyone in.
`check_schema_conformance.py` therefore refuses a deploy to a database that
lacks them, the same way it refuses a missing column. It also reports how far
RLS is switched on, as information, never as a gate.

**CI.** A new `backend-postgres` job runs the whole suite on a Postgres 17
service container inside the job. A second step fails if the RLS tests were
skipped, so a misconfigured URL can't go green by quietly falling back to
SQLite. The allow-remote variable still appears in no workflow.

## D4. Fixed: email lookups treated `_` and `%` as wildcards (account-takeover path)

Every email lookup used `ILIKE`, where `_` matches any single character and `%`
matches anything.
- **Google sign-in as `john_doe@gmail.com` matched a local account
  `johnxdoe@gmail.com`** and linked the Google identity to it. The Google user
  then owned that person's account.
- **A login with `%@%` matched an arbitrary account.**

Now it's exact, case-insensitive equality (`lower(email) = lower(:email)`) in
every lookup, in both the SQLite path and the Postgres functions, and tested.
The account and category duplicate-name checks have the same `ILIKE` pattern.
There it can only produce a false "already exists" inside your own data, so I
left those alone. Say if you want them changed too.

## D5. Fixed: three deletes failed with a 500 for real users

All three were found by the non-interference test (D6), which deletes from a
world where every table has a row:
- **A job with even one confirmed shift couldn't be deleted.** Its calendar
  blocks were bulk-deleted while shift records still pointed at them.
- **A course couldn't be deleted** once an expense was tagged to it, a
  reminder named it, or a repeating task belonged to it.
- **A spending category couldn't be deleted** once a recurring rule used it.

**Decision: keep what only mentions the thing, and clear the mention.** That's
what the dialogs already promise. A category "removes the label only", ledger
transactions stay, and a repeating task or reminder is a standing decision
that tidying something else shouldn't revoke. Every clear is a literal,
user-scoped UPDATE. Regression tests are in `test_jobs.py` and
`test_delete_references.py`, and pass on SQLite and Postgres. These are
backend changes, so they ship with the deploy.

## D6. Non-interference: B's data must not change A's answers

`tests/test_noninterference.py`. Mutation testing showed the isolation suite
misses a quieter failure: **B's data influencing A's results without appearing
in them.**
- Without its user filter, `blackout_dates` subtracted B's term breaks from
  A's timetable.
- The "last account of its kind" guard counted B's accounts as A's.

Neither put a byte of B's into a response.

**The test.** Every route runs twice from identical starting points, with the
same ids (the world is now deterministic): once with B's world present and
once without. Status, response and A's resulting rows must match. B also gets
"influencer" rows, such as a break over A's lecture day, where leaking would
show.

**It caught a bug in itself first.** My first version overrode the database
with a lambda that had a default argument, so every request in both runs was
the same 500 and every case "agreed". It now refuses any 500, and any
401/403/404 on A's own data. Only one 404 is allowlisted: restoring an account
with no pending deletion, which is a real answer. Both influence bugs are now
caught by name.

## D7. Onboarding: a dashboard checklist derived from what exists — SHIPPED (frontend)

`features/onboarding/GetStarted.tsx`. Five steps:
- set your term
- check your time zone
- add courses
- put something on your week
- record some money

Each step links straight to where it's done.

- **No stored state.** A step is done when the thing exists, however it was
  added, so someone who used the omnibox isn't told to do it again.
- **The time zone step** is done when the saved zone matches the browser's. New
  accounts start on America/Regina, which is wrong for anyone elsewhere, and
  "today" depends on it everywhere.
- **It waits for every data source to answer successfully.** That's your rule
  that an empty state may not show while data is loading.
- **Hide is remembered per user in the browser** (localStorage). It's a
  convenience, not a setting.
- **It shows for anyone with an unfinished step,** including existing friends
  who never recorded money. They can hide it. Say if you'd rather it only
  appear for new accounts.
- **Shipped on its own,** because it uses only endpoints the live API already
  has, per your standing rule that frontend-only work may ship. It was verified
  live: the dashboard chunk and the CSS are identical to a production build.
  The entry differs only by the Google client id, which my scratch build lacked.

## D8. Analytics: per-day counters, aggregate-only report, owner-run

- **`usage_events`.** One row per user, day, kind and module, holding a count,
  the first time and the last time. No paths and no content.
  - **Visits** come from the client, once per room per day per tab. The server
    can't tell which page is open, because the dashboard alone reads three
    modules.
  - **Creates** are recorded by the create routes.
- **Recording never breaks the action it records.** It runs after the action
  has committed, in a savepoint, swallowing its own failures, and skips if
  unsaved work is in the session. Both guards are mutation-tested.
- **`users.created_at`** makes time to first value measurable. Existing
  accounts get NULL, deliberately not backfilled with a guess.
- **`scripts/usage_report.py`** prints the gate numbers:
  - weekly actives
  - the universe test (two or more rooms in a week)
  - retention
  - adoption per room
  - rows per table, which flags zero-row features
  - time to first value

  It prints aggregates only (tested against seeded names, emails and ids), over
  a connection the server makes read-only.
- **A script, not an endpoint.** Totals across users are a cross-user read,
  which the API can't and shouldn't do.
- **It reads production data.** You'd ruled out per-user production reads, so
  running it is your call; the runbook says so.
- **Said out loud:** "Usage counts: On" in Settings → Account, with the details
  behind a (?).
- **No opt-out toggle.** Say if you want one.

## D9. Push notifications: Web Push written out, a scheduler endpoint, owner-only delivery

- **Protocol written here** (`webpush.py`, about 100 lines) instead of
  pywebpush, which would add aiohttp and its tree for a single POST.
  - It reproduces RFC 8291's published example byte for byte.
  - A receiver-side decrypt, written independently, round-trips it.
  - The VAPID JWTs verify, and are scoped to the push service's origin.
- **Delivery.** A secret-protected `POST /api/internal/reminders/dispatch`,
  meant for Cloud Scheduler every 5 minutes. With no secret configured it
  returns 404; with the wrong one, 403. The comparison is constant-time.
- **Isolation.** Finding *which* users have something due is a definer
  function returning ids. Everything after runs acting as that user, so a
  reminder can only reach its owner's own devices. That's tested on SQLite,
  under RLS as the restricted role, and by non-interference, which compares
  which devices received a push.
- **Rules:**
  - `pushed_at` is separate from the app's `fired_at`.
  - A failed send is retried for 12 hours, then dropped as stale.
  - A device the push service calls gone (404 or 410) is deleted.
  - A device with unusable keys is deleted rather than stopping the run for
    everyone after it. Found by the test world.
  - Keys are validated as real P-256 points at subscribe time.
  - Endpoints must be `https://`, because the server POSTs to them.
- **Shared browsers.** When a second person turns notifications on in a
  browser, the subscription moves to them. On sign-out the browser
  unsubscribes itself, offline and instantly, and the server forgets it the
  next time the push service answers 410.
- **No double notifications.** The open app skips its own system notification
  for a reminder already pushed, and both use the same tag.
- **iPhone.** Apple only allows push for a site added to the Home Screen, so
  there's now a manifest, generated icons, and a Settings message saying so in
  place of the button. No native client is needed: the vision's
  "confirm web push first" question is answered yes.
- **The VAPID contact** defaults to the site URL, not your email. Push services
  see it, and your address shouldn't go out unless you configure it.
- **Not live** until the runbook's step 6: keys, the cron secret, and the
  Cloud Scheduler job.

## D10. The tests were tested: every gap mutation found, and what closed it

Each `Model.user_id == user_id` filter in `app/` (164 of them now) was removed
one at a time, in scratch copies, with a control run first. A removal counts
as caught only on a test **failure**; an error counts as invalid.

Six gaps in my own suites surfaced this way, and each is fixed:
1. **Lists defaulted to a window around today, and the seeded world was dated
   elsewhere.** The world is now dated on the user's today.
2. **Every date query parameter got the same day,** so `start=end=today` was an
   empty window, and an unfiltered recurring projection leaked unseen.
   Windows now run from 30 days back to 90 ahead.
3. **Expenses were seeded positive, but the app stores them negative.** So they
   were invisible to every spending sum. The world is now signed like the app.
4. **The limit route was only ever asked to clear a limit,** which writes
   nothing. It is now asked to set one.
5. **Path-object attacks also carried B's ids in the body,** so the body's
   checks refused the request before the path object was looked up. Editing
   B's transaction by id went unseen. The body is now A's own.
6. **B's recurring rule was linked to an existing transaction,** so it was
   never due, and "run due rules" reaching other users had nothing to show.

Two influence bugs (B's data changing A's answers without appearing in them)
led to the non-interference suite (D6), plus "influencer" rows in B's world,
such as names A will try to create.

**What remains uncaught by the SQLite suites is redundant filters.** These are
queries already restricted to an id the user owns (a checked account, course
or category), or whose results are only looked up by the user's own ids:
`course_codes`, the per-account balance and readings maps, the budget summary's
per-account sums, and the clears inside a delete of something already owned.
Removing one changes nothing anyone can observe. They stay as defence in depth,
and under RLS the database enforces the same thing regardless.

**The container incident.** Partway through, the local Postgres container's
checkpointer wedged under eight concurrent test processes, and a gate test's
`DROP DATABASE` hung behind it. I recreated the container, which held only
disposable test databases, and gave the gate test's scratch database a
per-process name so two runs can't collide. CI runs one process on a fresh
container and was never affected.

## D11. Two grant gaps found while checking production, both fixed in code

Checking production after runbook steps 1–2 turned up two ways in that the
local tests had not modelled, because a plain Postgres has none of Supabase's
defaults.

1. **A blanket grant would have exposed a leftover table.** The app role was
   granted `ALL TABLES`, which includes `category_budgets`. That table was left
   by a rollback, no model builds it, so it gets no row policy. Fixed before
   step 2 ran: grants now name the model tables only (`cff08b5`). Production
   confirms `account_app` cannot read `category_budgets`.
2. **Supabase grants every new function to `anon` and `authenticated` by
   name.** `REVOKE ... FROM PUBLIC` doesn't touch a grant made by name. Supabase's
   Data API is on, so anyone holding the project's anon key (public by design)
   could call the email-to-id lookup and the push-endpoint release. Fixed in code
   (`9f1f3cb`): install now revokes each definer function from every grantee but
   its owner and the app role. The test now models Supabase's direct grant, and
   fails without the fix.

**Older, and now mostly closed:** before step 2, Supabase's default grants let
`anon` read every table through the Data API. Row-level security with no anon
policy now refuses it on all 28 model tables. `category_budgets` is the one
still readable until its anon grant is revoked.

## D12. Time-to-first-value is deferred, not failed (your call, 2026-10-05)

Phase 0's last exit criterion stays unchecked on purpose. Your reason: most
onboarding will depend on syllabus parsing and other automations that backfill
a student's data. Timing today's manual setup would measure a path that is
about to stop being the main one.

The measurement is already in place for when it matters. `users.created_at`
is set for every account created since 2026-10-05. Every creation is counted.
`scripts/usage_report.py` prints the median signup-to-first-creation time and
how many accounts created nothing. When the automations exist, run the dry run
and the 3–5 person cohort that were proposed:
- a fresh test account in a private window, timed;
- then real invitees signing up unaided, followed by the report.
