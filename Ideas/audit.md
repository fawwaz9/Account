# Application audit

Written 2026-09-10 against the working tree at `ca2884f` plus the uncommitted
account-activity work, and kept current as findings close -- most recently by the
front-end review pass of 2026-09-28. **The tiers below are a record, not a to-do
list.** Read the status passes for what is actually open.

Everything here was reproduced — by probing the running API, querying the live
database, building the frontend and reading the shipped artefact, or reading the
code path end to end. Where a claim rests on reading
alone rather than a reproduction, it says so.

**Two outside reviews have been folded in**, on the same terms: findings
re-checked against the current code rather than copied, the real ones placed in the
tiers below, and the ones that did not survive verification recorded near the end so
they are not raised again. `Ideas/fix.txt` (3 Aug, a source read) contributed two
findings and seven failed claims. `account-app-review.md` (27 Sep, a browser
walkthrough of the live site by a model with no access to this code) contributed
nine findings, #57-#65, and fourteen failed claims. Neither list is quoted; both
were re-derived.

**The project had no automated tests of any kind when this was written.** No pytest,
no vitest, no conftest. That is the single fact that best explains the shape of this
list: every defect below is one a test would have pinned down, and several are re-runs
of bugs the project has already fixed once elsewhere.

There is now a `backend/tests/` suite -- **940 cases**, grown from the 31 that were
written alongside the critical fixes, and a frontend suite of **142 cases in 17
files** where there were none. **This finding is closed.** The sentence that stood
here until 2026-09-28 -- "still nothing on the frontend, which is the one part of
this finding that has not moved" -- is no longer true; the frontend tests arrived
with the CSS cascade faults of the September deployment work, which is fitting,
since those were the defects no amount of backend testing could have caught.

---

## Status as of the high-tier pass

**All 5 critical and all 16 high findings are closed.** The tiers below are kept as
written, as the record of what was wrong and how it was verified -- they are *not* a
live to-do list any more. What follows is.

Closed in an earlier pass: #1 #2 #3 #4 #5 #7 #8 #18.
Closed in the high-tier pass: #6 #9 #10 #11 #12 #13 #14 #15 #16 #17 #19 #20 #21,
plus #47 (a token missing `sub` or `exp` 500'd) which fell out of #21 for free.

Three of those were fixed differently from what this document recommended, and the
reasons are worth keeping:

- **#3/#4** were fixed by branching on `kind == TRANSFER` with a `scope` parameter,
  *not* by adding the `group_kind` column suggested below. `kind` already carried the
  distinction; a new column would have been a second source of truth for it.
- **#21** uses a **session-epoch counter** on `users`, not the `jti` denylist suggested
  below. Comparing a token's `iat` against a revocation *timestamp* cannot distinguish a
  token minted just before the revocation from one minted just after, because `iat` has
  whole-second granularity -- the first implementation did exactly that and its own
  regression test caught it refusing a legitimate sign-in. A `jti` denylist buys
  per-token revocation, which is worth nothing without a per-device session list to
  revoke from. Changing a password now also returns a replacement token, so other
  sessions die while the caller stays put.
- **#6** is hand-rolled rather than a throttling library, since `requirements.txt`
  already carries ~30 packages the app does not use. Its limits are documented in
  `login_throttle.py`: in-process state, so it resets on restart and does not span
  workers.

**This paragraph is kept as it read at the time, and is no longer true.** It said:
*"Still open: the medium tier (#22-#42) and low tier (#43-#56), minus #47,"* naming
#24/#25, #28+#40 and #29 as the highest-value remaining. All of those have since
closed in the passes below. **See the deployment pass at the end for what is
actually still open — it is one item.**

## Status as of the second dead-code pass

**Closes the `_database/design.txt` item from the "Also medium" tail**, by
deleting it: 95 lines of Postgres DDL that nothing referenced, describing tables
that have since been built differently, in a project that now runs real Postgres
in production -- so it had stopped being a harmless sketch and become a file
someone could mistake for the schema.

Four other things went with it, each verified unreferenced first rather than
deleted for looking unused: `get_all_users`, an unfiltered query over every user
row left behind when the user-listing endpoints were removed; `weekday_code` in
the recurrence engine; `app/temp_data/`, by then holding nothing but a stale
`.pyc` of a module deleted in the first pass; and the five dashboard buttons that
only called `navigate()` somewhere the sidebar already links -- which did not
even list Jobs, so they had been both redundant *and* incomplete for a while.
Removing those orphaned `.grid`, the whole `.widget` family and `.widget-link`,
which had been dead since the first commit in July: 54 of the 113 lines of
`dashboard.css`.

**And it added a dependency rather than removing one.** Three test files use
Starlette's `TestClient`, which needs `httpx`, and `httpx` ships only under
`fastapi[standard]` / `starlette[full]` while `requirements.txt` pins plain
`fastapi` -- so it was present in the working venv by accident and absent from a
fresh clone. Exactly the gap the first pass found with pytest, and the
verification that would have caught it (a throwaway virtualenv built from the
file alone) predates the tests that introduced it. Verified both ways this time:
a fresh venv from `requirements.txt` alone runs all 40 of those tests, and
uninstalling `httpx` from that same venv fails all three files at collection.

## Status as of the dead-code pass

**Closed: #56**, plus the `pip freeze` requirements file from the "Also medium" tail.

Sixteen files removed, every one verified unreferenced first rather than deleted on
the strength of being empty: eleven zero-byte frontend modules, two zero-byte
`errors.py`, `temp_data/store.py`, `api/api.txt`, and `_database/check_state.py` --
which really did print every user's id, name and email to stdout at import.

`requirements.txt` went from a 58-line `pip freeze` to 9 direct dependencies, which
is 66 installed packages down to 42. **pytest was never declared at all**, so a fresh
clone following the README could not run a single test. Verified by building a
throwaway virtualenv from the pruned file alone and running the whole suite against
it: 562 passed, and the app still imports with all 137 routes.

`package.json` needed nothing -- the `axios` dependency this document names is already
gone from it.

## Status as of the database-integrity pass

**Closed: #24, #25, #26, #28, #29, #38, #39.** Every foreign key and filter column is
now indexed (49 indexes, 0 before), all four unique constraints exist as unique
indexes, SQLite runs with WAL, a 5s busy timeout and `foreign_keys=ON`, backfills are
keyed by `(table, column)`, and DDL runs in a lifespan hook rather than at import.

Three things are worth keeping from how it went:

- **Turning on foreign keys is what found the bugs, not the indexes.** The test suite
  went from 562 green to two failures the moment enforcement was on, and both were
  real: `remove_shift` deleted a cash tip's ledger rows while `shift_records.
  tip_transaction_id` still pointed at them, and `delete_account` would now 500 rather
  than silently orphan a standing instruction. The suite had passed for weeks against
  a database where every `ForeignKey` was a comment.
- **#28 was bigger than "two missing cascades".** `UserModel` declared exactly two --
  courses and accounts -- so *fourteen* other tables were orphaned on delete, not the
  two this document names. They are declared now, and a test asserts nothing survives
  a delete rather than trusting the declaration.
- **`delete_account` now refuses rather than cascades** for standing instructions and
  sinking funds, and cascades only budget targets. A rent instruction deleted as a
  side effect of tidying an account stops paying rent; a budget target is a planning
  number scoped to that account and means nothing without it.

Verified against a copy of the real database: 0 foreign-key violations before or after,
row counts unchanged, and the hot queries now report `SEARCH ... USING INDEX` where
they previously reported `SCAN`.

## Status as of the service-correctness pass

**Closed: #27, #41, #43, #44, #45, #46, #49, #51, #52**, plus the unstripped
`ALLOWED_ORIGINS` split from the low-tier tail.

The theme is the same in every one: the server answered confidently and wrongly.

- **#27** is worse than "commits twice". The schema validator sums only the weights
  *submitted*, while the service merges them over the ones the course already has and
  checks that total -- so a patch that is fine alone and only breaks the ceiling once
  merged is the one that reaches the half-applied commit. The first test written for
  this was vacuous for exactly that reason: `CourseUpdate` rejected the payload before
  the service ever ran, and the mutation test is what exposed it.
- **#49** had the same shape. A test that registers the same address twice never
  reaches the insert -- the pre-check catches it, and the pre-check is precisely the
  path that does not race. It only tests anything once the check is neutralised.
- **#46** was two bugs. `payload["name"]` 500s on a token granted without the profile
  scope, and a transport failure reaching Google's JWKS endpoint arrives as
  `GoogleAuthError`, not `ValueError`, so it escaped the handler entirely. A network
  failure is now a 503 rather than a 401: "we could not tell" is not "your token is
  bad", and logging it as a rejected sign-in would make a Google outage read as a
  burst of failed logins.
- **#43/#44** returned `200 []`, which on a money page is the one answer that is
  certainly wrong -- it reads as a fact rather than a failure.
- **#45** was not one route. Fourteen `raise HTTPException` sites across four routers
  were missing `from exc`.

## Status as of the performance pass

**Closed: #22, #23, #50.**

The dashboard went from **81 queries to 5** on the real gradebook's 27 courses. Two
causes, both named correctly here: lazy `grades` and `category_weights` per course
(now one `selectinload` each for the whole list), and `calculate_required_final`
re-fetching a course already in the identity map (now takes the row the caller
holds). Verified byte-identical: the whole dashboard payload and every account
balance, dumped before and after against a copy of the real database, `diff` clean.

`get_account` no longer groups the entire ledger to answer about one account.

**#50 is real but its example is not.** The rule was `abs(difference) > 0.01`, and
for 100.00 against 100.01 the float difference lands at 0.010000000000005 -- just
*above* the tolerance, so that exact case was rejected by accident. The first test
written for it passed against the unfixed code for precisely that reason. Sweeping
every amount from 0.01 to 600.00 finds **tens of thousands** of pairs where the
difference lands at or below 0.01 and a one-cent error really was accepted, so the
finding stands; it just needed a value that demonstrates it. Comparison is now in
whole cents, which needs no tolerance at all.

## Status as of the nullable-average pass

**Closed: #31**, and it exposed a live bug on the dashboard while doing it.

An unmarked course reported `average: 0.0`, and `get_dashboard` picked its weakest
course with a plain `min` over that figure -- so **the weakest course on the page was
whichever course you had not started**. On the real gradebook, 7 of 27 courses were
in that state, and the weakest course moves from one of them to MATH 220 at 77.5,
which is a real course with real marks.

Two decisions worth keeping:

- **Null means "nothing marked", not "averages zero".** A course whose marks really
  do average zero still reports `0.0`. That distinction is the whole point, so the
  flag comes from whether any counting grade exists, not from testing the average
  against zero -- and a dropped mark does not count, for the same reason it stays out
  of every average.
- **The mapped column is never written.** The service attaches `reported_average` and
  the schema reads it through a `validation_alias`, so deciding what to report never
  means assigning to `course.average` -- which would be #51 all over again. A test
  asserts the column still reads 0.0 while the API reports null.

The flag is computed in one grouped query for a list and an EXISTS for a single
course, so it does not depend on grades being eager-loaded and does not reintroduce
the N+1 closed at #22.

## Status as of the frontend pass

**Closed: #32, #33, #34, #36, #37, #53, #54**, plus `aria-valuenow` exceeding
`aria-valuemax` from the low-tier tail. **#55 was already fixed** -- `TaskList` takes
an `emptyMessage` and every caller passes one; what remained was the unexplained
disabled button, which now says why on the page as well as on hover.

- **#34 was twenty sites, not a handful.** Ten of them are the always-mounted data
  hooks, which is where the cost lands: `refreshUser()` builds a fresh object, so one
  Settings save re-ran every one of them. All ten use `user` for nothing but its id,
  so they now depend on `user?.id` -- a primitive that does not change. The remaining
  ten are transient components (modals, the omnibox) and are left for now.
- **#32's disagreement is real and narrow.** The server rounds `used_percent` to 1dp
  and the client did not, so at the `close` boundary 89.96 became 90.0 on one side
  and stayed 0.8996 on the other. The server's figure is now passed in, with the
  derivation kept only as a fallback for callers that have none.
- **#33 was a comment, not a bug.** The type said "expenses only -- transfers move
  money rather than spending it"; `budget_service` deliberately includes the outgoing
  leg of a transfer and carries a comment saying the two must not diverge. The numbers
  were right, so the comment moved to match them.
- **#36** needed row identity, not a different key expression: rows carry an `id` now.

## Status as of the soft-delete pass

**Closed: #40**, which needed #28's completed cascades underneath it and so waited
for that to land rather than being built on a deletion that still leaked.

Deletion is a request now. `delete_user` marks `deleted_at`, revokes every session
in the same moment, and removes nothing; `purge_expired_users` does the removing
once the thirty-day window has passed, and runs at startup for the same reason due
payments are written on read -- idempotent work, done when something is already
happening. A machine left off for a month catches up when it starts, which is
correct: the deadline passed whether or not the server was running.

Three decisions worth keeping:

- **Signing in still works while deletion is pending.** There is no email system
  here, so blocking sign-in would make an account that nobody could ever restore --
  the grace period would be decoration. The client reads `deletes_on` and offers to
  undo it.
- **Asking twice does not move the deadline.** Otherwise repeating the request
  quietly buys another thirty days, and the account never goes.
- **The purge deletes one row at a time through the ORM, not in bulk.** A bulk
  statement bypasses the cascades, and the mutation test for it fails with a foreign
  key violation rather than silently orphaning -- which is #28 and #29 doing their
  job on a fault introduced a fortnight later.

Worth knowing: **there is no UI for account deletion at all**, and never was. The
DELETE endpoint has no caller in the frontend, so restore needs none either; the API
is the whole surface today.

## Status as of the accessibility pass

Closes three of the "Also medium" items: the `h1 -> h3` heading jump on the course
page, account kind conveyed by colour alone, and `CourseSearch` claiming
`role="combobox"` without the parts that make one work.

The combobox is the interesting one. It had the role, `aria-expanded`,
`aria-controls` and `aria-autocomplete` -- everything except the two things that
carry the actual state. Arrow keys moved a purely visual highlight: nothing set
`aria-activedescendant`, and the results were list items rather than options, so a
screen-reader user was told a list existed and then never told which row they were
on. Declaring the role without those is arguably worse than not declaring it, since
it promises behaviour that is not there.

Account kind was a 3px coloured stripe and nothing else, across five kinds. The
stripe stays as decoration and is now `aria-hidden`, with the kind written out
beside the name -- the same treatment the Jobs page already gives hourly, salaried
and contract.

Still open from that tail: inputs labelled by placeholder only, which is a wider
sweep across a dozen forms.

One correction to #17 found while fixing it: this document calls the unconfirmed
account delete "permanent", but the server refuses to delete an account that still
holds transactions and says to archive instead. The exposure was empty accounts only.
It now has a two-stage confirm regardless.


## Status as of the deployment pass

**Closes #42, and confirms #30 and #48 were closed earlier without being recorded
here.** Written 2026-09-14, after the app went live on Cloud Run + Supabase +
Cloudflare Pages.

- **#42 — no HTTPS enforcement — is closed, by the deployment not using nginx.**
  The finding called this *"not urgent while this runs on your own machine; a
  blocker before it runs anywhere else"*, and it now runs somewhere else. In
  production the browser talks to Cloudflare Pages and Pages talks to Cloud Run,
  and neither serves plaintext. Verified:

  ```
  curl -sI https://account-2a7.pages.dev
    strict-transport-security: max-age=31536000; includeSubDomains
  curl -sI http://account-api-...run.app/health
    HTTP/1.1 302 Found -> https://...
  ```

  `frontend/nginx.conf` still listens on 80 with no redirect, and that is now
  correct rather than a defect: it serves the local docker stack only, where the
  origin is `localhost` and there is no certificate to redirect to. **The finding
  moved from "open" to "does not apply" without a line of code changing**, which
  is worth noticing — it was a deployment finding filed against application code.

- **#30 — the transfer-partner lookup with no `user_id` filter — is closed.**
  Every `group_id` lookup in `transaction_service` now carries `user_id`
  alongside it. One deliberate exception remains: the sinking-contribution
  cleanup matches on `group_id` alone, which is safe because `group_id` is a
  `Uuid` and cross-user collision is not a real event.

- **#48 — nothing invalidates a JWT — is closed**, as a consequence of #21. The
  session-epoch counter on `users` is compared on every authenticated request,
  and `set_password` bumps it, so changing a password really does end every
  other session. Deleting an account bumps it too.

**Still open, and it is one item plus a sweep:**

- **#35 — no request caching. Still open, and both halves of it are.**
  Dashboard → Budget → Dashboard still issues redundant round trips, and every
  `reload()` still refetches everything when one row changed. This mattered
  less on localhost than it does now: the same page from a phone on mobile data
  pays real latency for each of them.

  > **A third case, larger than either of these, was found while scoping the
  > fix and is now closed — but it is not one this finding ever described, so
  > #35 does not shrink.** Stepping the month picker re-ran the whole load:
  > eight reads and a write, where only `fetchBudgetSummary` takes a month at
  > all. The other seven are the same figure whichever month is on screen, and
  > the write had nothing to record because no time passes between two clicks.
  > A month step is now one request, and it no longer blanks the page while it
  > runs. `useBudget.test.ts` counts the requests, since nothing on screen
  > looks different either way.
  >
  > The count in this finding is also stale: it says "all four endpoints".
  > `reload()` refetched **eight**, from 18 call sites on the budget page.
- **Inputs labelled by placeholder only**, from the accessibility tail — a sweep
  across a dozen forms, not a single fix.

**What the deployment added that this audit never covered**, all of it in
`Ideas/deployment.md` rather than here: an invite gate on registration, a
registration throttle, the docs endpoints off by default, a configurable
`ALLOWED_ORIGINS`, six security headers, a React error boundary, a service
account with two grants and no project roles, nightly backups that have been
restored once for real, and uptime monitoring. Two known weaknesses were carried
in deliberately and are written up there: the rate limiters key on Google's front
end rather than the caller (D5.5), and backups exist in one place only.

## Status as of the front-end review pass

Written 2026-09-28, folding in `account-app-review.md` -- a read-only walkthrough of
the live site at `https://account-2a7.pages.dev` done from the browser by another
model, which saw the running app and none of this code. **Twenty-three claims. Nine
survived, fourteen did not**, and the nine are #57-#65 below.

It is worth saying why that ratio is not a criticism of the review. A reviewer with
only the front end can see that a figure looks wrong; it cannot see whether the
figure is wrong, whether the rule behind it is deliberate, or whether the string it
read is the string the page renders. Every claim here was checked against the code
path that produces it, the same standard the rest of this document holds to, and
the fourteen are recorded in their own section so they are not raised a third time.

**The single most useful thing it found, it found sideways.** It reported "no
timezone anywhere on deadlines/events" as an accessibility nit. The real defect is
larger and is now #58: `UserPreferences` declares seven fields the Settings page
never sends, and `timezone` is one of them. It defaults to `America/Regina`, and
`timing_service.local_completion_date` uses it to decide whether a task was
finished early or late -- the one figure the module's own docstring warns is
"a bias in one direction across most of the sample" if the zone is wrong. Anyone
outside Saskatchewan gets that figure computed against the wrong day boundary and
has no way to say so. A stored preference with no control is not a gap in the
form; it is a setting that silently cannot be right.

**And one whole class of its findings was an artefact of how it read the page,
which is worth recording because the fingerprint is exact.** It reported "text
spacing glitches" on four pages -- `17tasks· 40m`, `$628.84gross,$157.21deducted`,
`4completedtasks have no due date` -- and concluded "screen readers hear garbled
strings". They do not. `TaskList` renders:

```jsx
{tasks.length} {tasks.length === 1 ? "task" : "tasks"}
{load && ` · ${load}`}
```

The space between `17` and `tasks` is a whitespace-only JSX text node. The space
after `·` is *inside* a template literal, so it is part of a larger text node.
Accessible-name computation trims each node and concatenates -- the first space is
lost, the second survives. That is precisely the string the review quoted, down to
which of the two spaces lived. `CompletionTiming` reproduces it exactly under the
same rule. **The rendered text is correctly spaced and so is what a screen reader
announces; what was read was the accessible-name tree, which is not the page.**
The same mechanism explains "course name shown twice on cards" (a button's computed
name beside its own children) and "Hours Hours" in Settings (the browser's names for
the internal segments of `<input type="time">`).

**Its two CRITICALs were one observation, and it is not a defect.** It reported that
net worth excludes debt, and separately that a $41,040 student loan is recorded as
spending. The first is false: `net_worth` sums balances where
`counts_toward_net_worth`, a debt balance is already negative, and
`account_service.py:183` carries a comment saying that subtracting it a second time
is the bug the comment exists to prevent. `NetWorth.tsx` draws a Debt line beside
the headline. The reason no debt appears is the second observation -- the loan is a
*category* named "Student Loans", not a debt *account*, so there is no negative
balance for net worth to include. The proof offered, that $27,886.34 − $41,040
equals the term summary's −$13,153.66, matches a **stock** against a **flow**; they
agree only because the same $41,040 is in both, meaning different things.

That leaves the real question underneath, which is a design question and not a
finding: should the app refuse, or warn about, a transaction categorised in a way
that breaks budget-vs-plan? **The settled preference on this project is options over
rules** -- so the answer is probably a way to mark a category as not-spending, which
the user chooses, rather than a warning the app decides to show. Recorded here
rather than as a defect because the ledger did what it was told.

**Nothing in the review touched security, and nothing in it changed a tier above
Low.** The nine that survived are one wording bug, one missing settings surface,
and seven small UI and accessibility faults. Read against the fourteen that did not,
that is the useful summary: the parts of this app that handle money and auth were
looked at hard by something with fresh eyes and no access to the source, and it
found nothing there.

**What is open, as of this pass.** The deployment pass above says "one item plus a
sweep", which was true when it was written and is superseded here:

- **#35 — no request caching**, both halves. Unchanged since 2026-09-14.
- **Inputs labelled by placeholder only**, the sweep across a dozen forms.
- **#57-#65**, from this pass. #58 is the one worth doing first: it is the only
  item on the list that makes a figure wrong rather than making a page awkward,
  and the form it needs already exists.
- **#66**, from the production census run the same day. It is the only finding in
  this document that is a fact about the *database* rather than the code, and the
  only one a reader cannot verify from the repository alone.

Everything else in this document is closed.

---

## Summary

| # | Severity | Area | Issue |
|---|---|---|---|
| 1 | **Critical** | Auth | Account takeover: changing your email does not clear `email_verified` |
| 2 | **Critical** | Config | An unset `JWT_SECRET` becomes `""` and the server starts anyway |
| 3 | **Critical** | Money | Deleting one leg of a deposit deletes the whole deposit |
| 4 | **Critical** | Money | Editing a deposit's amount corrupts a sibling allocation |
| 5 | **Critical** | CSS | Tailwind is unwired; tall modals have no scroll container and their submit buttons are unreachable |
| 6 | High | Auth | No rate limiting on `POST /api/auth/login` |
| 7 | High | Data | Cross-tenant category attach, and a cross-tenant `UPDATE` that follows from it |
| 8 | High | Money | Editing a transfer's date desynchronises its two halves |
| 9 | High | Docker | Eight backups of real financial data are baked into the backend image |
| 10 | High | Tooling | `dev.run.sh` installs its signal traps too late and orphans the backend |
| 11 | High | Tooling | `dev.run.sh` never checks `VITE_API_BASE_URL`; a fresh clone is silently broken |
| 12 | High | React | Out-of-order fetches can show one month's figures under another month's label |
| 13 | High | UX | Any network failure on a course page reports "Course not found" |
| 14 | High | A11y | Ten hand-rolled modals: no focus trap, no Escape, no `role="dialog"` |
| 15 | High | A11y | `required` is inert on four forms — they are `<div>`s, not `<form>`s |
| 16 | High | A11y | Eight category-weight inputs have no accessible name |
| 17 | High | UX | Destructive buttons render identically to Cancel; account delete has no confirmation |
| 18 | High | Types | `CourseCreate` is missing `target_grade` — the `category_id` bug waiting to happen |
| 19 | High | Docs | `READMe.md` has eleven wrong claims, two of which cause damage if acted on |
| 20 | High | Repo | A stray committed Vite scaffold at the repo root, with a different TypeScript major |
| 21 | High | Auth | A stolen token cannot be revoked, and nothing records that it was used |
| 22–46 | Medium | — | see below |
| 47–56 | Low | — | see below |
| 57 | Medium | UX | "Left to spend" keeps its label when it goes negative |
| 58 | Medium | Settings | Seven stored preferences have no control; `timezone` skews the timing figures |
| 59 | Medium | React | Every list renders its empty state while its own refetch is in flight |
| 60 | Low | UX | An overdrawn spending account is conveyed by the minus sign alone |
| 61 | Low | A11y | Week view renders all events then all due markers, so reading order is not time order |
| 62 | Low | UX | A course card shows an average with no sign of how few items it rests on |
| 63 | Low | UX | The grade trend axis can label 105 |
| 64 | Low | A11y | Two priority selects can carry the same accessible name |
| 65 | Low | A11y | The study-hours start input is labelled "Study hours", the end one "Study hours end" |
| 66 | Medium | Database | A rolled-back feature left `category_budgets`, and two rows, in production |
| 67 | Low | CSS | Two dead Tailwind utility rules are emitted from English in code comments |

Nothing in this list is a style opinion. Items I checked and found **healthy** are
recorded at the end so we don't re-audit them.

---

## Critical

### 1. Account takeover — changing your email does not clear `email_verified`

`backend/app/Users/services/user_service.py` — `update_user`, and `link_google_to_account`

`link_google_to_account` carries a careful twelve-line docstring about account
pre-hijacking, and drops an unproven password when linking:

```python
user.google_id = google_id
if not user.email_verified:
    user.password_hash = None
user.email_verified = True
```

But `update_user` writes `email` through a blanket loop and never touches
`email_verified`:

```python
for key, value in update_data.items():
    setattr(user, key, value)          # 'email' is just another key
```

So the guard is bypassable. Verified chain:

1. Attacker signs in with Google — `create_user` sets `email_verified=True`.
2. Attacker calls `POST /api/auth/password`. No `current_password` is required
   because `has_password` is False.
3. Attacker `PATCH /api/users/{own_id}` with the victim's email. The only check is
   that no *existing* row holds it. `email_verified` stays `True`.
4. The victim later signs in with Google. No row matches their `google_id`, so the
   lookup falls through to email — finding the attacker's row — and
   `link_google_to_account` runs. Because `email_verified` is already `True`, the
   attacker's password **survives**.
5. The victim now uses the attacker's account. The attacker signs in with
   email + password and reads everything, and can lock the victim out.

The attack needs the Google-first route specifically — a local attacker has
`email_verified=False` and would lose their password at step 4. That precision is
what makes it real rather than theoretical.

**Fix:** set `email_verified = False` whenever `email` changes. Better, make email
immutable without a re-verification flow.

### 2. An unset `JWT_SECRET` becomes `""` and the server starts

`backend/app/config.py` and `docker-compose.yml`

```python
class Settings(BaseSettings):
    GOOGLE_CLIENT_ID: str
    JWT_SECRET: str            # no min_length, no non-empty check
```

Compose does `JWT_SECRET: ${JWT_SECRET}`, and Docker Compose substitutes an **empty
string** with only a warning when the variable is undefined. There is **no
`.env.example` in the repo** — `.gitignore` even carries a `!.env.example`
negation for a file nobody ever created — so a fresh clone has nothing to populate
it from. `.dockerignore` excludes `.env`, so `env_file=".env"` finds nothing inside
the container either.

Pydantic accepts `""` for a required `str`, and PyJWT's `HMACAlgorithm.prepare_key`
rejects only PEM/SSH-shaped keys, not empty ones. **The backend boots normally and
signs every session token with a zero-length HMAC key.** Anyone can mint a token
for any user id. The only signal is a compose warning that scrolls past during a
multi-minute image build.

`dev.run.sh` guards this — but only for `./dev.run.sh docker`, not for the raw
`docker compose up --build` that `READMe.md` tells you to run.

Related: `JWT_ALGORITHM` is env-overridable, and PyJWT's `NoneAlgorithm` treats
`""` as `None` — so `JWT_ALGORITHM=none` plus the empty secret yields entirely
unsigned tokens.

**Fix:** `JWT_SECRET: str = Field(min_length=32)`, make the algorithm a module
constant rather than a setting, and commit a `.env.example`.

### 3. Deleting one leg of a deposit deletes the whole deposit

`backend/app/Finances/services/transaction_service.py` — `delete_transaction`

```python
if transaction.group_id is not None:
    db.query(TransactionModel).filter(
        TransactionModel.group_id == transaction.group_id,
        TransactionModel.user_id == user_id,
    ).delete(synchronize_session=False)
```

The docstring — "Deletes both halves of a transfer, half a transfer is not a
thing" — is right about transfers. But `deposit_service.record_deposit` **also**
assigns one shared `group_id` across every account a deposit was split into.
`group_id` means two different things, and this code only knows about one of them.

Record a 5,500 paycheque split four ways, then delete the Spending row because you
mistyped it: all four rows vanish and four balances move. The UI tooltip says
"Deleting a transfer removes both sides", which is wrong on both counts.

Not yet triggered in your data — all three existing deposit groups happen to hold
one row. It fires the first time you use the deposit tab with more than one account
carrying a share.

**Fix:** stop overloading `group_id`. Add a `group_kind` column (`transfer` |
`deposit`) and branch on it: delete the group for a transfer, delete one row for a
deposit.

### 4. Editing a deposit's amount corrupts a sibling allocation

Same file, `update_transaction`:

```python
partner = (... .filter(group_id == ..., id != transaction.id).first())
if partner is not None:
    partner.amount = -transaction.amount
```

Correct for a transfer, where the legs mirror. For a deposit every leg is
**positive income** — negating one produces an income row with a negative amount, a
state the codebase assumes cannot exist because `signed()` enforces the sign on
write.

The downstream behaviour is what makes this nasty. A negative income row is
classified as neither money-in nor money-out by `activity_service`, and it is not
an expense, so `get_budget_summary` skips it too. **It disappears from every chart,
tile and progress bar while still dragging the balance down.**

With three or more legs it is also arbitrary — `.first()` has no `order_by`, so one
unpredictable sibling is corrupted and the rest keep their old value.

### 5. Tailwind is unwired, and tall modals become unreachable

`frontend/src/styles/globals.css:1` is `@import "tailwindcss";` and **there is no
`vite.config.ts` anywhere in the project**, so `@tailwindcss/vite` is installed but
never registered. Vite resolves the bare import to the package's raw CSS and inlines
it verbatim.

Measured directly from the built artefact `dist/assets/index-C3gP0ENc.css`:

| Probe | Result |
|---|---|
| `.rounded-lg` and every other utility | **0 occurrences** |
| `--tw-*` custom properties | **0 occurrences** |
| `@layer base{...}` (Preflight) | **present and live** |
| raw `@tailwind utilities` at-rule | **present** — proof no processor ever ran |
| `@theme default` block | present, and discarded unparsed by the browser |

**332 utility-class usages across ten component files are inert.** The worst
consequence: `AddCourseForm` and `EditCourseForm` wrap their body in

```jsx
<div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1 text-center">
```

`max-h-[70vh] overflow-y-auto` is the *only* scroll container, and it does not
exist. The hand-written CSS gives it nothing to fall back on — `.popup` is
`position: fixed` with `align-items: center` and no `overflow`, and
`.addCoursePopup` has no `max-height`. The Add Course form is roughly 800px tall
(eleven fields plus an 8-cell weight grid plus three buttons). On a 1366×768 laptop
it overflows both ends of a fixed-position container that cannot scroll, so
**"Add Course" is off-screen and unclickable.** Same for Edit Course, and for
`BulkGradesModal` past about six rows.

**Correction to the README and the handoff.** Both say the Tailwind decision is
being deferred because *"registering the plugin would also switch on Preflight,
which would reset margins and headings across CSS written for browser defaults."*
That premise is false — **Preflight is already shipping and already active.** The
`@layer base` reset is in the bundle right now. `globals.css` re-sets `h1`–`h3`
after the import so headings survive, but `ul`, `ol`, `p` and `fieldset` are
currently getting Preflight's `margin:0; padding:0; border:0 solid`, not browser
defaults. The app's present appearance already incorporates the reset.

So the option described as "safe" — deleting the `@import` — is actually the one
that would change how the app looks. This has been blocking a decision for four
sessions on a reason that does not hold.

**Fix:** add a `vite.config.ts` registering `@tailwindcss/vite` (and
`@vitejs/plugin-react`, which is also absent — there is no Fast Refresh today, and
every save does a full page reload). That turns 332 dead classes live and fixes the
modal scrolling for free.

---

## High

### 6. No rate limiting on login
`backend/app/api/routes/auth.py`. No throttling library in `requirements.txt`, no
lockout, no CAPTCHA. One bcrypt verification per request, unbounded. The careful
timing-equalisation in `password_service.py` is defending a far smaller hole than
this one leaves open against an 8-character minimum password.

### 7. Cross-tenant category attach, and the cross-tenant write it enables
`transaction_service.create_transaction` trusts the client's `category_id` with no
ownership check, and `update_transaction` does the same through its `setattr` loop.
On its own that is a modest IDOR — the category name is never echoed back. The
damage is the pairing with `budget_service.delete_category`, which nulls by
`category_id` with **no `user_id` filter**:

```python
db.query(TransactionModel).filter(TransactionModel.category_id == category_id).update(
    {TransactionModel.category_id: None}, synchronize_session=False
)
```

User A posts an expense carrying user B's `category_id`; when B deletes that
category, the UPDATE crosses the tenancy boundary and rewrites A's row. **Fix both
ends:** validate ownership on write, and scope the delete by `user_id`.

### 8. Editing a transfer's date desynchronises its halves
`update_transaction` again. The `occurred_on`/`description` carry-over is nested
*inside* `if new_amount is not None:`, so changing only a transfer's date moves one
leg and not the other. The two halves then sit in different months — the account
page shows the outgoing leg in September and the incoming leg in October, and both
months' totals are wrong. Trivial to hit through the edit modal.

### 9. Real personal data is baked into the Docker image
`backend/.dockerignore` lists `*.db`, which excludes `data/app.db` — but **not**
`app.db.backup-20260910-002503`, because that filename does not end in `.db`.
`Dockerfile` then does `COPY . .`, so all eight backups (741 KB of your courses,
grades, accounts and transactions) land in an image layer. They are invisible at
runtime because the bind mount shadows them, so this would never be noticed by
running the stack — but they are permanently in the image and would ship with it.

Note `.gitignore` gets this right with a separate `*.db.backup*` rule.
`.dockerignore` never got the same treatment.

### 10. `dev.run.sh` installs its traps too late and orphans the backend
The traps live inside `supervise`, but `main` calls `start_backend`, then
`start_frontend`, then `supervise`. Between the first two there is **no trap
installed at all** — and `start_frontend` may spend minutes in `npm ci`. A port
clash, a missing `node`, a failed install, or **Ctrl+C during `npm ci`** all exit
with uvicorn already running and unreaped. The next run then dies with
`Port 8001 is already in use`, and you have to hunt down a process the script
itself leaked. **Fix:** move both `trap` lines to the top of `main`.

### 11. `dev.run.sh` never checks `VITE_API_BASE_URL`
`check_frontend_env` checks `VITE_GOOGLE_CLIENT_ID` and warns; it does not check
`VITE_API_BASE_URL` at all, and does not `die` the way `check_backend_env` does.
`frontend/.env` is gitignored, so on a fresh clone it does not exist —
`apiClient.ts` then falls back to `http://localhost:8000/api` while the script just
started the backend on **8001**. The app loads, renders its shell, and every fetch
fails, with the only diagnostic being a warning about Google sign-in.

The same trap fires for `BACKEND_PORT=8005 ./dev.run.sh`, which the README
recommends: the override never reaches the frontend. **Fix:** have `start_frontend`
export `VITE_API_BASE_URL="http://localhost:$BACKEND_PORT/api"` so the two cannot
disagree.

### 12. Out-of-order fetches show the wrong month's money
`useBudget` and `useAccountActivity` both `await Promise.all([...])` then `setState`
with **no cancellation guard** — unlike `useBudgetGlance` and `CourseSearch`, which
both get it right. Hold down the month picker's stepper and several `load()`s race.
If September resolves after October, the page shows September's figures while the
picker reads October, and the stale `setLoading(false)` clears the spinner so
nothing signals the mismatch. On a money page that is a silent wrong-number bug.
**Fix:** the `cancelled` flag the sibling hooks already use.

### 13. Any network failure on a course page reports "Course not found"
`CourseDetailPage` catches its load error into `console.error` — the only
`console.error` in the codebase — and has no `error` state. The render then falls
to `if (!course) return <div>Course not found</div>`. So an API outage, a 500 or a
dropped connection all tell the user their course **has been deleted**: a
permanent, factual-sounding claim, with no retry and no message. Every other page
surfaces `err.message`.

### 14. Ten modals with no keyboard or screen-reader contract
`AddCourseModal`, `EditCourseModal`, `AddGradeModal`, `EditGradeModal`,
`DeleteConfirmModal`, `RequiredFinalModal`, `BulkGradesModal`, `AddMoneyModal`,
`EditTransactionModal`, `EditAccountModal`. None traps focus, restores focus on
close, closes on Escape, or carries `role="dialog"` / `aria-modal` /
`aria-labelledby`. A keyboard user tabs through the entire page *behind* the
overlay; a screen-reader user is never told a dialog opened.

`shared/components/Modal.tsx` exists as a 0-byte file. Writing it once fixes all
ten.

### 15. `required` is inert on four forms
`AddCourseForm`, `EditCourseForm`, `AddGradeForm`, `EditGradeForm` mark inputs
`required`, but their root is a `<div>`, not a `<form>`, and submit is
`<button type="button" onClick={...}>`. **No constraint validation ever runs**, and
Enter-to-submit is dead. Submitting blank sends `{code: "", name: ""}` and relies on
the backend to reject it — the error then renders at the bottom of a modal that may
be scrolled off-screen (see #5).

`AddGradeForm` is self-contradictory on top of that: `required` on an input whose
placeholder reads "Score (blank = not graded yet)". Wrapping it in a real `<form>`
would break the documented feature.

### 16. Eight category-weight inputs have no accessible name
`AddCourseForm` renders the 4×2 weight grid with `placeholder={category}` and no
`id`, no label, no `aria-label`. The placeholder vanishes on the first keystroke,
leaving eight identical boxes with no indication of which is which. A screen reader
announces eight bare spin buttons.

`EditCourseForm` does this correctly with `<label htmlFor=...>`. The Add form simply
never received the fix.

### 17. Destructive buttons look exactly like Cancel
`DeleteConfirmModal` and `EditAccountModal` style their confirm buttons
`!bg-red-600 !text-white` — inert classes (#5). The only matching rule is
`.addCoursePopup button`, so in "This will permanently delete all grades in this
course" the Delete and Cancel buttons render as the same gold-on-navy pill.

`EditAccountModal` is worse: `Delete` is the **first** button in the row and calls
`deleteAccount` immediately with **no confirmation at all**, unlike every other
delete in the app. And since `createAccount` has no UI anywhere, a misclick is
permanent.

### 18. `CourseCreate` is missing `target_grade`
The proper type-check reports 11 real errors; 7 are this one omission.
`features/grades/types.ts` declares `CourseCreate` without `target_grade` while four
components set and read it. `Course` and `CourseUpdate` both have it; only
`CourseCreate` does not.

It works today by luck — the payload carries the field as an excess property and
the backend assigns it. But the natural response to `TS2339: Property
'target_grade' does not exist` is to delete the line, at which point every course
silently gets the account default and the "Target Grade" field becomes a no-op that
still looks like it works. **This is the `category_id` bug, one keystroke away from
happening again.** Fix the type, not the call sites.

### 19. `READMe.md` has eleven wrong claims, two of them damaging
It was accurate when written and has not kept up. The two that cause harm if acted
on:

- It says the repo tracks 1150 dependency files, `__pycache__` and `dist/`, and
  tells you to run `git rm -r --cached`. **All of that is fixed** — 158 tracked
  files, none in `node_modules`, no `.pyc`, no `dist/`. Following the instruction
  would do damage.
- It says `origin/grades-branch` was deleted and suggests `git remote prune
  origin`. The branch is **live** at `078e179` with your 6 unpushed commits ahead
  of it.

The other nine, briefly: it says Finances is a hardcoded stub (it is a complete
module with four tables and five services); it says `MainLayout`/`Sidebar`/`Topbar`
are empty files (all three are populated and in use); it says the budget components
are empty stubs (there are ten-plus); it says four functions are missing from
`grades/api.ts` (all four exist); it says `AcademicStatus` has no route (there are
two); it says there is no GPA scale by design (CGPA now exists on a switchable
scale); it documents four database tables (there are eight); it says `axios` is a
dependency (it is not, though it is still installed); and the Preflight claim in #5.

Also: the filename is `READMe.md` with a lowercase `e`, so every `cat README.md`
and every tab-completion misses it.

### 20. A stray committed Vite scaffold at the repo root
`/package.json`, `/package-lock.json` and a 51 MB `/node_modules` sit at the repo
root with no `index.html` and no `src/`. Provenance: `npm create vite` run in the
wrong directory on Jun 24, committed in the initial architecture commit, never
cleaned up. The lockfile is tracked.

It declares **`typescript@6.0.3`** where the frontend uses `5.9.3`, and has no
`tailwindcss` and no `react-router-dom`. Because Node resolution walks upward, if
`Application/frontend/node_modules` is ever pruned, Vite and `tsc` will silently
resolve from the root — a different TypeScript major, no error. That is exactly the
"works on my machine" class of bug.

### 21. A stolen token is valid for seven days and nothing records its use

Three separate gaps compound, and `fix.txt` was right to group them:

- The token lives in `sessionStorage` (`AuthContext.tsx`), so any XSS reads it.
  There is no XSS vector today — see the "did not hold up" section — but this is
  the payload if one ever appears.
- There is **no revocation of any kind**: `JWT_EXPIRE_MINUTES` is 7 days, tokens
  carry no `jti`, there is no denylist, and `set_password` does not invalidate
  outstanding sessions. A user who changes their password *because* they think
  they were compromised stays compromised for a week.
- There is **no logging at all** — no access log, no failed-authentication log, no
  record of who deleted which course. So a breach leaves no trace to find
  afterwards, and there is nothing to alert on.

Individually each is a common trade-off. Together they mean a single stolen token
grants a week of undetectable, unrevocable access to academic and financial
records. **Fix, in order of value:** shorten the expiry and add a refresh
mechanism; add a `jti` plus a denylist so `set_password` can revoke; log
authentication events and destructive mutations.

---

## Medium

22. **`get_dashboard` is an N+1**, ~3 queries per course (lazy weights, lazy grades,
    plus a redundant `get_user_course` inside `calculate_required_final` for a
    course already in the identity map). 40 courses ≈ 125 queries for one page.
23. **`get_account` sums the entire ledger to answer one account** — it calls
    `balances_by_account` for all accounts and discards all but one. Same in
    `update_account`.
24. **No indexes on any foreign key or filter column.** Every hot query is a full
    scan: `transactions.user_id/account_id/occurred_on`, `courses.user_id`,
    `grades.course_id`, `budget_targets.(user_id, account_id, month)`.
    `running_balance` scans the full history on every account-page load.
25. **No unique constraints** on `(user_id, code)` for courses, `(user_id, name)`
    for accounts and categories, or `(user_id, account_id, month)` for targets. All
    four are enforced only by check-then-insert in Python, so all four race.
26. **Seeding-on-read races.** `get_accounts` and `get_categories` check-then-insert
    with no lock, so two concurrent `GET`s on a fresh user seed twice — 12 accounts
    or 26 categories. A `GET` that writes is also not idempotent.
27. **`update_course` commits twice**, so a weight rejection leaves a half-applied
    patch: the code change is committed before `apply_category_weights` runs and
    can raise. The caller sees a 400 and the record changed anyway.
28. **No `PRAGMA foreign_keys=ON`, and `delete_user` orphans data.** `UserModel`
    declares cascades for courses and accounts but not for `spend_categories` or
    `budget_targets`, and SQLite does not enforce FKs by default. "Delete my
    account" silently leaves financial rows behind.
29. **SQLite concurrency is unconfigured** — no WAL, no explicit `timeout`, against
    a 40-thread threadpool. Two simultaneous writes surface as
    `database is locked` → uncaught → 500.
30. **The transfer-partner lookup has no `user_id` filter** — the one write path in
    the module that could touch another user's row.
31. **A course with no grades reports `average: 0.0`** and `letter_grade: ""`. Zero
    is a real grade; "no grades yet" is not. This is the same bug already fixed for
    the cumulative average, which was made nullable for exactly this reason.
32. **`used_percent` is computed server-side and thrown away.** `ProgressBar`
    recomputes `value / max` instead — a direct violation of the project's
    "compute server-side, render client-side" rule. They agree today only by
    coincidence; the server rounds to 1 dp and the client does not, so the
    `>= 0.9` "close" threshold can disagree at the boundary.
33. **`AccountBudget.actual`'s doc comment contradicts the backend.** The type says
    "Expenses only — transfers move money rather than spending it"; the backend
    deliberately includes outgoing transfers and carries a comment warning that the
    two must not diverge. The numbers are right; the comment is a trap for whoever
    reads it next.
34. **Every hook depends on the whole `user` object**, not `user.id`. `refreshUser()`
    creates a new object, so one Settings save re-runs every mounted hook's full
    fetch.
35. **No request caching.** Dashboard → Budget → Dashboard issues 7 round trips,
    about 4 of them redundant. Every `reload()` refetches all four endpoints even
    when one row changed.
36. **`BulkGradesModal` keys rows by array index** while rows are removable —
    removing row 1 while editing row 3 reuses the focused DOM node for different
    data and loses the keystroke.
37. **`AddMoneyModal` resets in-progress input** whenever the parent reloads,
    because its effect depends on the `accounts` array identity.
38. **`BACKFILLS` is keyed by bare column name**, not `(table, column)` — and
    `archived`, `position`, `name`, `user_id` and `kind` all exist on multiple
    tables. Safe today only because there is exactly one entry.
39. **`create_all` and `ensure_schema` run at module import**, so any `import
    app.main` — a test collector, a reload worker, an IDE indexer — issues DDL.

40. **Deleting a user is immediate and unrecoverable.** `cascade = "all, delete-orphan"`
    wipes every course and grade the moment `DELETE /api/users/{id}` lands — no soft
    delete, no archive, no confirmation step beyond the request itself. Combined
    with #21 (a stolen token cannot be revoked), a compromised account means
    permanent loss of an entire academic record. Note this sits alongside the
    *opposite* defect at #28: the cascades that do exist are incomplete, so
    categories and budget targets are orphaned rather than removed. Both halves
    want fixing together — complete the cascade, and make deletion recoverable.

41. **CORS is wider than it needs to be.** `main.py` sets `allow_methods=["*"]` and
    `allow_headers=["*"]`, which permits methods the API never serves. It also sets
    `allow_credentials=True` while authentication is a Bearer header and no cookie
    is ever set — so the flag grants nothing and only widens what a future
    misconfigured `ALLOWED_ORIGINS` would expose. Narrow both lists to what is
    actually used and drop `allow_credentials` until something needs it.

42. **No HTTPS enforcement in the deployed stack.** `frontend/nginx.conf` listens on
    80 with no redirect and no HSTS header. Bearer tokens then cross the network in
    plaintext, which makes the seven-day lifetime in #21 considerably worse in any
    deployment beyond localhost. Not urgent while this runs on your own machine;
    a blocker before it runs anywhere else.

Also medium: `requirements.txt` is a raw `pip freeze` with ~30 unused packages
(`openai`, `firebase_admin`, three `google-cloud-*`, `grpcio`) adding hundreds of MB
to every venv and image; the frontend lockfile still declares `axios` and 27 dead
packages are installed; the frontend Dockerfile inlines `localhost:8000` at build
time and nginx never proxies `/api`, so the image is host-locked; the backend
Dockerfile's `chown /app/data` is shadowed by the runtime bind mount and fails off
Docker Desktop; `dev.run.sh`'s staleness check ignores `package.json`; account kind
is conveyed by colour alone in `Sectors`; `CourseSearch` claims `role="combobox"`
but never sets `aria-activedescendant` or `role="option"`; heading levels jump
`h1 → h3` on the course detail page; seven inputs are labelled by placeholder only;
`_database/design.txt` is Postgres DDL for a SQLite app whose weight `CHECK`
contradicts a settled decision; and errors render as muted grey text with no
`role="alert"`.

---

## Low

43. Inverted date ranges (`start > end`) return `200 []` instead of a 400.
44. An unknown `account_id` filter returns `200 []` instead of 404.
45. `required-final` re-raises without `from exc`, against an otherwise consistent
    codebase.
46. `verify_google_token` 500s instead of 401 on a token with no `name` claim, or on
    a network failure reaching Google's JWKS endpoint.
47. `decode_access_token` 500s on a token with no `sub`, and `exp` is not required.
48. Nothing invalidates a JWT — 7-day tokens, no `jti`, no denylist, no logout, and
    `set_password` does not revoke existing sessions.
49. Concurrent registration of the same email returns 500 (`IntegrityError` escapes
    the `ValueError` handler).
50. Deposit allocation tolerance is `> 0.01`, so allocations summing to `100.01`
    against a `100.00` deposit are accepted — a cent that never existed.
51. `GET /average` and `/letter-grade` mutate the session (assigning to a mapped
    column inside a read); harmless today because nothing commits, but a landmine.
52. `search_courses` does not escape `%` and `_`, so they act as live wildcards.
53. `ProtectedRoute` renders `null` during auth bootstrap — a blank white page on
    cold load, with `// or a spinner` in the code conceding the point.
54. `Dashboard` renders "Welcome, " with a trailing comma while `/users/me` is in
    flight, and discards `useBudgetGlance`'s `error` entirely, so a failed budget
    fetch renders as no budget section at all.
55. Tasks and Calendar pages render an empty `<ul>` with no empty state; "Record
    Money" is disabled with no explanation when there are no accounts.
56. **21 zero-byte files** and a dead fixture. `shared/components/*` (all five),
    `shared/utils/*`, `shared/hooks/useLocalStorage.ts`, `app/router.tsx`,
    `pages/SchedulePage.tsx`, and the whole `features/tasks/` and
    `features/calender/` component trees. They read as existing scaffolding when
    nothing is there. `testData/courses.ts` is a stale fixture nothing imports,
    accounting for the other 4 type errors. Dead on the backend too:
    `temp_data/store.py`, two 0-byte `errors.py`, `api/api.txt`, and
    `_database/check_state.py` — which **prints every user's id, name and email to
    stdout at import time**.

Also low: `features/calender/` is misspelled, and Calendar is the next feature to
build — rename it now, before imports exist. `ALLOWED_ORIGINS` is split without
stripping whitespace, so `"a.com, b.com"` yields a value that can never match.
`aria-valuenow` can exceed `aria-valuemax` when overspent. Nine exported API
functions have zero call sites. `Ideas/to_do.txt` has gained no entry since auth
landed, despite Grades and all of Budget shipping.

---

## From the front-end review

The nine claims in `account-app-review.md` that survived being checked against the
code, renumbered into this document's sequence. Each was reproduced by reading the
path that produces the behaviour; none needed a live probe, because all nine are
decided in the client or in a schema. Severity is Low unless it says otherwise.

57. **Medium. "Left to spend" goes negative and the label stops being English.**
    `Dashboard.tsx` renders `total_planned - total_actual` under the fixed label
    "Left to spend". The block is gated on `total_planned > 0` but not on the sign
    of the difference, so a month that overspends its plan reads
    `-$51,650.99 Left to spend` -- a sentence with no meaning. The figure is right;
    the word for it changes when it crosses zero. "Over by $51,650.99" is the same
    number said truthfully, and the page already has the pattern: `NetWorth` swaps
    its own label to "In the red" for exactly this reason.

58. **Medium. Seven stored preferences have no control anywhere, and one of them
    changes a figure.** `UserPreferences` declares `timezone`, `currency`,
    `week_start`, `theme`, `date_format`, `time_format` and
    `default_reminder_minutes_before`. `SettingsPage` sends none of them -- it
    covers `credit_target`, `gpa_scale_enabled`, `default_target_grade`, the study
    window and `min_free_block_minutes`, and nothing else. The API validates all
    seven, `timezone` against real IANA data, so the surface exists and only the
    form is missing.

    `timezone` is the one that matters, and it is not cosmetic.
    `timing_service.local_completion_date` converts `completed_at` into the
    student's own zone before comparing it to a due date, and its docstring says
    why in terms this finding cannot improve on: in UTC−6 anything finished after
    18:00 local is stored on the next UTC day, "so an evening's work on its due
    date reads as a day late. Evening is when most of it gets done, so the error is
    not noise -- it is a systematic drift toward 'late'." The default is
    `America/Regina`. Every user outside it gets that drift and no way to stop it.

    `currency` is validated as ISO 4217 and then ignored: `money.ts` hardcodes `$`.
    Either wire it up or drop the field, but a validated preference nothing reads
    is a promise the app does not keep.

    > **CLOSED 2026-10-01, and the count in the heading was the wrong way to read
    > it.** "Seven preferences have no control" sounds like seven controls to
    > build. It was one bug, one control, and five things that were never built.
    >
    > - **The bug.** Worse than this finding said: Settings was not merely failing
    >   to set `timezone`, it was *resetting* it on every save, because
    >   `UserUpdate.preferences` was typed as the full `UserPreferences` and every
    >   field of that has a default. Fixed in `b140088` with a real patch type;
    >   proved against a throwaway database first.
    > - **The control.** `timezone` is now a `<select>` in the Calendar tab, seeded
    >   from the stored value and never from the browser's guess — the guess is
    >   offered by a button, the way the first-year field offers one. A `(?)` says
    >   what it affects.
    > - **The five.** `currency`, `week_start`, `theme`, `date_format` and
    >   `time_format` are read by nothing, and `default_reminder_minutes_before` by
    >   nothing either. **They stay unexposed, and that is the finding's answer
    >   rather than work outstanding.** A control that changes nothing is worse
    >   than an absent one: it invites someone to set it and then quietly disagrees
    >   with the app. Each needs its consumer built first, and three of them —
    >   `week_start`, `date_format`, `time_format` — mean changing shared date
    >   utilities the recurrence engine depends on. `theme` needs a light palette
    >   that does not exist; see `whats_next.txt` for what that actually costs.
    >
    > So nothing here is pending. If one of those five is wanted, it is a feature
    > with a consumer to build, not a field to add to a form.

59. **Medium. Every list renders its empty state while its own refetch is in
    flight.** `TaskList` shows `emptyMessage` whenever `tasks.length === 0`, with no
    notion of loading. Ticking "Show completed" flips both `includeDone` and
    `includeArchived`, which changes `useTasks`'s callback identity and starts a new
    fetch; until it lands, `tasks` is the previous array and the Done group renders
    "Nothing finished yet." beside a stats block saying 18 tasks were finished this
    month. That is the contradiction the review reported, and it is a loading state,
    not a disagreement between two figures -- both are right, one is a frame behind.

    `TasksPage` does render `Loading…` with `role="status"`, but it is one line at
    the top of the page and says nothing about which of the five groups is stale.
    The narrow fix is for `TaskList` to take the flag it is already next to.

60. **A spending account in overdraft is conveyed by the minus sign alone.**
    `Sectors` gives a debt account `sectorCard--debt` and gives an overdrawn
    spending account nothing -- `-$188.66` renders in the same weight and colour as
    a healthy balance. This is the same fault the accessibility pass closed for
    account *kind*, one field over: the card was taught to stop conveying kind by
    colour alone and was never taught anything about sign. `SafeToSpend` does say
    over-committed, but that is an aggregate a scroll away from the card.

    **Still open, and now with company on the same card.** Investment returns
    (2026-10-01) added a second signed figure beside the balance, `(+3.2%)` /
    `(−8.1%)`. It was deliberately given **no** sign-dependent colour -- the sign
    lives in the text and `.sectorReturn` is muted in both directions -- precisely
    so this finding is not deepened while it is open. Fixing #60 should therefore
    treat the two together: whatever marks an overdrawn balance should be the thing
    that marks a loss, rather than a third convention.

61. **Reading order in the week view is two sorted sequences, not one.** `place()`
    sorts events by start minute and `placeTasks()` sorts due markers by theirs, so
    the review's claim that events are not time-ordered is wrong. The residual is
    real though: `WeekView` renders *all* of a day's event blocks and *then* all of
    its task markers, so an 11pm lecture precedes a 9am deadline in the DOM. Both
    sequences are sorted; their concatenation is not. The comment above the markers
    explains the render order as a painting decision -- drawn after the blocks so a
    deadline inside a lecture is not hidden -- which is correct for the canvas and
    happens to also decide reading order, which it should not.

62. **A course card states an average with no indication of how little it rests
    on.** `GradeBand` exists precisely for this: "Can still finish 12 – 100" with
    "17 items left to mark" under it. It renders only on the course detail page.
    `CourseCard`, in the list, shows a `100` in the average circle and an `A+`
    beside it from one marked item of eighteen, with nothing qualifying either. The
    reviewer read that as final, which is what it looks like. The band's own
    `outstanding_items` is the figure the card is missing.

63. **The grade trend axis can label a grade that cannot exist.**
    `GradeTrendChart` pads the observed maximum by 2 and rounds up to a multiple of
    5, so a term at 100 draws a top tick of **105**. The review called the axis
    "0–105"; the floor is data-driven too (`Math.floor((rawMin - 2) / 5) * 5`), so a
    record from 77.5 to 100 actually draws 75–105. The ceiling half stands: the
    chart should clamp at 100, where the scale ends.

64. **Two priority selects can carry the same accessible name.** `TaskItem` labels
    its select `Priority of ${task.title}`. A recurring task with two materialised
    occurrences in the same list produces two controls a screen reader cannot tell
    apart. Almost certainly the origin of the review's `dup=1/2` annotation, which
    was otherwise unreproducible. The due date is already on the row and would
    separate them.

65. **The study-hours inputs are labelled asymmetrically.** `study-start` is
    labelled "Study hours" by its `<label htmlFor>`; `study-end` carries
    `aria-label="Study hours end"`. The first should say "start". One word.

---

## From the production census

One finding, from a read-only census of the Supabase database on 2026-09-28. It
is here rather than above because nothing in the code could have shown it: the
defect is a difference between what the schema builds and what production holds,
and you only see it by counting both.

66. **Medium. A rolled-back feature left its table, and its data, in production.**
    `category_budgets` was created by `f0dfede` for whole-budget category limits.
    `394cb7c` removed that feature — model, service, routes, frontend, every
    reference. **The table is still there**, with its four indexes and **two rows**:
    $41,040 against September 2026 and $70 against October. No foreign key points
    at it and nothing has read it since 2026-09-24.

    Production therefore has **one table more than `python -m app._database.schema`
    builds** -- 26 against 25 when this was found, and 27 against 26 once
    `account_month_values` shipped on 2026-10-01 -- and that drift is the part worth
    fixing. The schema module is the file
    every other document treats as the description of this database; once it is
    not, the next person to compare the two has to work out which of them is
    wrong, with no record saying a rollback is the reason.

    **This is a gap in the removal procedure, not a one-off.** `ROLLBACK.md`
    already says a rollback cannot undo a table, and it is right — dropping one
    destroys data that rolling code back does not. What is missing is the step
    after: a removal should record the table it orphaned, so the decision to keep
    or drop it is taken deliberately rather than discovered a week later by
    counting. `shipping.md` step 17 is where that belongs.

    Dropping it destroys two rows of real data, so it is the owner's call.

67. **Low. Two dead utility rules are shipped in the stylesheet, written by prose.**
    The built sheet contains `.visible{visibility:visible}` and
    `.contents{display:contents}`. Neither class is used by any element in the app.
    They exist because **Tailwind scans comments for class candidates**, so an
    ordinary English sentence in a `.ts` or `.tsx` comment that happens to contain
    a bare utility word emits a real rule for it.

    Found by the selector-order diff while shipping investment returns, which
    caught two *more* of them arriving the same way -- `.collapse` from "must not
    collapse into one" and `.table` from "the table this feature copied" -- both
    reworded before the change was committed. These two are older and were already
    in production.

    Harmless in weight, perhaps forty bytes. Worth recording for two reasons: it is
    the third time this mechanism has produced a dead rule here, and a sheet with
    unexplained selectors in it makes the order diff noisier, which is the check
    that catches real cascade regressions. The fix is to reword the comments that
    feed them, found by diffing emitted selectors against classes actually used.

---

## Claims from `fix.txt` that did not hold up

Recorded so they are not raised a third time. Each was checked against the current
code, not dismissed on reading.

**"Horizontal privilege escalation — `verify_user_access` is not used
consistently."** It is. Every route taking a `user_id` path parameter is guarded by
`VerifiedUserId`; there is no unguarded `user_id: UUID` in the codebase. The
specific example given, `/api/users/me`, takes no `user_id` at all — it returns the
caller's own record from the token, which is the correct design. I also probed for
IDOR directly: passing your own `user_id` with another user's account id returns
404, not their data.

**"Stored XSS via grade names and course titles."** No. There is no
`dangerouslySetInnerHTML`, no `innerHTML` assignment and no `eval` anywhere in
`frontend/src` — React escapes interpolated text by default, so
`{course.name}` renders a `<img src=x onerror=...>` string as literal text. The
original note conceded this itself, describing a "hypothetical vulnerable component
(not shown, but likely exists)". It does not exist.

**"No bounds check on category weights."** There is, in two layers.
`normalize_category_weights` rejects any individual weight outside 0–100
(`raise ValueError(weight_error["invalid_weight_value"])`) and rejects a total above
`MAX_TOTAL_WEIGHT = 200.0`. Note the ceiling is deliberately 200 rather than 100 —
weight above 100 is bonus marks, a settled decision. *(There is a real adjacent bug,
but it is a different one: see #27, where `update_course` commits before the weight
check runs.)*

**"DOS via an unbounded search query."** No. The route declares
`query: str = Query(..., min_length=1, max_length=100)`. It is bounded at the edge.

**"Frontend redirects on 401 without cleaning up stale auth state."** It cleans up.
`apiClient.ts` removes the token on any 401, and `AuthContext` clears it in two more
places.

**"No CSRF protection on state-changing endpoints."** Not applicable. CSRF depends
on the browser attaching credentials automatically, which is what cookies do.
Authentication here is a Bearer token read from `sessionStorage` and set explicitly
on each request — a cross-site form post carries no `Authorization` header. Moving
the token to an httpOnly cookie, as `fix.txt` recommends, is the change that *would*
introduce a CSRF requirement.

**"SQL injection via `ilike()`."** The note answers itself — the value is
parameterised. The real residual is smaller and is recorded at #52: `%` and `_` in a
search term act as live wildcards because they are not escaped.

Two further `fix.txt` items were right in substance and are folded in above rather
than repeated here: no rate limiting on authentication (#6) and SQLite running
without WAL or a busy timeout (#29).

---

## Claims from the front-end review that did not hold up

Fourteen, recorded so they are not raised again. Each was checked against the code
path that produces the behaviour, not dismissed on reading. Several are good
observations of the wrong thing, and those say what the right thing was.

**"Budget net worth excludes debt (CRITICAL)."** It does not. `net_worth` sums the
balances of every non-archived account with `counts_toward_net_worth` set, and a
debt account's balance is already negative, so it is included by arithmetic rather
than by special case. `account_service.py` carries a comment at `DEBT_KINDS` saying
that set exists to *report* the debt line and not to subtract it, "the bug this
comment is here to prevent". `NetWorth`'s docstring says the same again, and
`NetWorth.tsx` draws a Debt row under the headline whenever `debt_total > 0`. See
the status pass above for why the supporting arithmetic -- $27,886.34 − $41,040
matching the term summary -- proves nothing: it sets a stock against a flow.

**"Loan disbursement counted as spending (CRITICAL)."** Not a code defect. A
$41,040 expense in a category named "Student Loans" is what the ledger was told to
record, and every figure downstream of it is correctly derived from it. The design
question underneath -- whether a category should be able to declare itself
not-spending -- is in the status pass. The app accepting it "without warning" is
the settled preference on this project, not an oversight.

**"Recurring text-concatenation artifacts across Dashboard, Tasks, Jobs and
Budget," and "screen readers hear garbled strings."** No. This is
accessible-name computation trimming whitespace-only text nodes, not the DOM. The
fingerprint is exact and is worked through in the status pass: in `17tasks· 40m`
the lost space and the surviving space are two different kinds of JSX node. The
rendered page and the announced text are both correctly spaced.

**"Don't show course name twice on cards."** The same artefact. `CourseCard`'s
button has one `<span>` with the code in it; the button's *computed name* is that
span's text, so an accessibility-tree dump prints the string once as the button's
name and once as its child. There is one code on screen.

**"Fix awkward accessible names on study-hours inputs ('Hours Hours', 'Minutes
Minutes', 'AM/PM AM/PM')."** Nothing in the app emits those. Both controls are
`<input type="time">`, whose three internal segments are named by the browser. The
real nit is one word and is #65.

**"Give 'Set aside funds' a clear entry point -- section is empty with no way to
add one."** `SinkingFunds` has a **New fund** button in its section heading, beside
the `<h2>`, and an empty state that explains what a fund is for. The button is
there when the list is empty; that is the case it was written for.

**"Destructive actions without confirmed safeguards."** Grades, courses, accounts
and transactions all route through `DeleteConfirmModal` -- `EditGradeModal`,
`CourseDetailPage` (twice), `BudgetView` and `AccountDetailPage`, the last with a
"Whole deposit" confirm label that is the visible half of the #3 fix. This was #17,
closed in the accessibility pass. The review declined to test it, which is correct
under a read-only brief, but the answer is yes.

**"Don't mix unconfirmed 'Estimated' earnings into totals."** They are not mixed.
`Earnings` splits by source, not by window, and its docstring argues the point at
length: the cards carry money that arrived, everything the shifts merely predict
lives under `Estimates`, "and the two are not a sum and a remainder". A window with
work in it and no cheque yet says "Nothing paid yet" rather than a confident $0.00.

**"Explain the 25% deduction -- tax withholding? fee? Users can't verify
correctness."** The premise is wrong: it is not a rate the app applies.
`deduction_percent` is `deducted / gross * 100` over the deduction lines the
student entered on their own cheques. It is a measurement of their pay, not an
assumption about it, so it is already as verifiable as the cheques behind it. The
quoted "if it's not right, edit the job" does not appear in the codebase.

**"Fix Priority combobox accessible names ('P1 dup=1/2')."** Not reproducible.
The options read `1 · Lowest` through `5 · Highest` and the select is labelled
`Priority of {title}`; no "P" prefix exists anywhere. The duplicate-name residual
is real and is #64.

**"Fix time-axis labels skipping 2am and 2pm."** Not reproducible. `WeekView` maps
over all 24 `HOURS` with no conditional, and `hourLabel` returns `2am` and `2pm`
for hours 2 and 14. Every hour is in the DOM.

**"Ensure calendar events are time-ordered in the accessibility tree."** They are:
`place()` sorts on `startMinutes` before anything is rendered. The true residual --
events and due markers being two separately sorted runs -- is #61.

**"Deduplicate recurring tasks."** Deliberate, with the reasoning in `Repeating`'s
own docstring: the rule and its occurrence are different objects answering
different questions, and "showing a rule inline among its own occurrences would
make it look like a seventh thing to tick off." A rule in Repeats and a task in the
fortnight are not a duplicate.

**"Fix typo: 'Software Contruction'."** Not in the codebase -- `contruction`
appears nowhere in any source file. It is the course name as typed into the app,
and it is fixable from the course editor.

Two more were right to ask and turned out healthy, so they are in the section below
rather than here: the "Worth doing next" ranking, and whether the dashboard's budget
figures trace to their source.

---

## Verified healthy — do not re-audit

- **Auth holds.** No token → 401. Malformed → 401. Expired → 401. Forged
  `alg=none` → 401. Another user's data → 403 on every module. Algorithm is pinned
  to a single-element list. Google's ID token is genuinely verified server-side with
  the audience pinned and `email_verified` enforced.
- **No IDOR.** Your own `user_id` in the path with another user's object id returns
  404, not their data — ownership is filtered in the services, not just the
  dependency. Every route taking a `user_id` path parameter is guarded by
  `VerifiedUserId` — there is not one unguarded `user_id: UUID` in the codebase.
- **Login does not leak.** All three failure modes return an identical message, and
  the no-account path burns a real bcrypt verification to equalise timing.
- **No password hash is ever serialised.** `/me` and every user route use response
  models that do not declare it.
- **No secrets have ever been committed**, on any branch — I searched history by
  content, not just by filename. No `.env`, no `.db`, no key material. `.gitignore`
  correctly needs both `*.db` and `*.db.backup*`; do not "simplify" that away.
- **Migrations are complete.** Every model column is either in an original CREATE or
  in `ADDED_COLUMNS` — verified by replaying the logic against all nine SQLite files
  in `data/`, spanning 2026-08-28 to today. Every column reaches every historical
  database.
- **`DATABASE_URL` anchoring is correct** and consistent between local and Docker.
- **Ledger data is sound.** Zero sign violations, zero zero-amount rows, zero
  cross-user transactions, zero dangling category references, zero future-dated
  rows. Every two-row transfer group nets to exactly zero.
- **No 500s** across 26 courses × 6 per-course endpoints, plus dashboard and search.
  The 422s on `required-final` and `search` are correct — both have required params.
- **Grades above their category max** (6) and **weights over 100** (4 courses, up to
  104.71) are deliberate per the settled decisions. Not bugs.
- **Ctrl+C does kill both services** once `supervise` is reached — `set -m` plus
  process-group signalling is correct. The bug is only that it may never be reached.
- **`npm ci` does not fail** on the lockfile desync; npm 10 prunes and exits 0.
- **No click handlers on non-interactive elements.** The S6848 convention is
  genuinely upheld, and every icon-only button carries an `aria-label`.
- **No SQL injection.** Everything goes through the ORM; the single raw `text()`
  interpolates only from a module-level literal.
- **Docker hygiene is otherwise good:** multi-stage build, non-root user, `.git` and
  `.env` excluded.
- **"Worth doing next" handles weights and dropped grades.** `cheapest_path` filters
  on `counts_toward_average`, so a dropped quiz cannot be offered as work; skips
  `is_additive` categories, because bonus marks add on top of an average rather than
  composing it and so are not a route to a target; scores leverage through
  `project_average`, which carries the weights; and drops any item whose leverage is
  zero, which is how a weightless category stays off the list. Covered by
  `test_cheapest_path.py`.
- **The dashboard's budget figures trace to their source.** `total_actual` and
  `total_planned` come from `budget_service`, the same call the budget page reads,
  and `Biggest this month` is `by_category[0]` from that response. The figures a
  front-end reviewer found implausible are the ones the data produces; the only
  defect in that block is the wording of one label (#57).
- **Net worth includes debt.** Verified by reading the arithmetic rather than the
  screen: negative balances enter the sum unchanged, and `debt_total` reports the
  same money as a positive magnitude for display.
- **Deletes confirm.** Every destructive control in Grades, Courses, Accounts and
  Transactions opens `DeleteConfirmModal` first.

---

## Suggested order

1. **The two deposit bugs (#3, #4)** — they silently corrupt money, and #4 hides its
   own damage from every view that would show it.
2. **The email-change takeover (#1)** — an active account-takeover path.
3. **`JWT_SECRET` minimum length (#2)** and a committed `.env.example`.
4. **Category ownership (#7)** and the transfer date desync (#8).
5. **`vite.config.ts` and `tsconfig.json` (#5, #18)** — one config file turns 332
   classes live and fixes the unreachable modal buttons; the other makes
   `npm run build` actually type-check. Together they would have caught the
   `category_id` bug on the day it was written, and #18 before it ships.
6. **`dev.run.sh` traps and `VITE_API_BASE_URL` (#10, #11)** — both bite on a fresh
   clone.
7. **`.dockerignore` (#9)** before the image is ever pushed anywhere.
8. Indexes and unique constraints (#24, #25), which also close the seeding races.
9. The a11y tier — a single shared `Modal` (#14) closes ten instances at once.

Given there are no tests, #1, #3, #4, #7 and #8 are the ones most likely to be
reintroduced by a later refactor. Each deserves a regression test written as part of
its fix — which would also be this project's first test.
