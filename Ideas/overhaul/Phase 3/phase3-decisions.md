# Phase 3 — decisions

Written for: you, reviewing what was decided for Phase 3 and why. Each entry
says what was decided, what was rejected, and what it costs. Follows
`Ideas/overhaul/template.md`.

## D1. Phase 3 opens before Phase 2 closes, with the tracker (yours, 2026-10-12)

**What I asked:** the tracker is Phase 3 in the vision, and Phase 2's exit
criteria aren't met yet. Open Phase 3 with it, or build it outside the phases?
**Your answer:** open Phase 3 with the tracker.

Why it holds:
- **Phase 2's remaining criteria need use, not code.** Five active teams, a
  partnership surviving a month, outside registrations (deferred, D19), and
  moderation load. No build closes them, so holding Phase 3 until they're met
  would only hold up a feature that needs none of them.
- **The tracker needs no density.** The vision says it "can ship as soon as the
  phase opens".
- **It is large-scale by the template's own test.** It spans backend and
  frontend, adds tables, and you will want its decisions to review.

**What it costs:** two phases open at once. Phase 2 stays open for its usage
criteria, ticked as they happen. The density features of Phase 3 (Part B) still
wait on contributors, so opening the phase early unlocks nothing that needs
people.

**Rejected:** building the tracker outside the phases. It would lose the
decisions log and runbook the template exists for.

## D2. An application's history is kept, step by step, and its statuses include "accepted" (yours, 2026-10-12)

**Your answer:** applied, screening, interview (each round its own step),
offer, **accepted**, rejected, no reply, withdrawn.

Each change is a row in `application_steps` with its date, never an overwrite of
the status. The Sankey and "how long replies take" are both read from the
history, so overwriting would leave neither anything to read. "Accepted"
separates the offers you took from the ones you turned down; turning one down
is "withdrawn" after "offer".

## D3. "No reply" is suggested after 30 quiet days, never set on its own (yours, 2026-10-12)

An application still at applied, screening or interview, with no new step for
30 days, is flagged "no reply yet?" with one tap to mark it. Nothing changes
until you tap. **Rejected:** setting it automatically, because a figure that
moves on its own is one you stop trusting, and a late reply would have to undo
it; and no flag at all, because a forgotten application then sits "applied"
forever and inflates the waiting count.

## D4. Deadlines and follow-ups appear on the calendar, not in Tasks (yours, 2026-10-12)

Both show on the tracker and as all-day items on your calendar, the way a
shared task's due date does. Clicking one points back to the tracker. They are
not tasks: there is nothing to tick off, and the application itself is where
the next step is recorded.

## D5. An offer can carry its pay, privately (yours, 2026-10-12)

An optional amount and period (hourly, monthly or yearly) on an application,
visible only to you. Later it is what you could choose to submit to co-op
salary transparency (item 12), opt-in. Nothing reads it across users, and no
aggregate exists yet.

## D6. No role but the API's keeps a grant on any table (found by batch 1's read-back, 2026-10-12; your call: close it before deploying)

**What the read-back showed:** on `job_applications` and `application_steps`,
Supabase's `anon`, `authenticated` and `service_role` held every privilege,
TRUNCATE included, beside `account_app`'s four. My runbook said to expect
`account_app` alone. It was wrong about why: `rls.py` revoked other grantees on
shared and sealed tables and on functions (Phase 0 D11), **never on ordinary
per-user tables**. Supabase's default privileges grant every new table to those
three roles, so the same grants have sat on every per-user table since each was
made.

**How exposed:** no row-security policy names those roles, so they can read or
change no rows. They are reached only through the Data API, which you switched
off in Phase 0. TRUNCATE ignores row security, so the remaining risk was one
setting away.

**What changed:** the install now revokes every privilege from every grantee
but the table's owner and `account_app`, on every model table, and then
grants the app role exactly what the table's kind allows. A schema run
therefore closes it on all existing tables at once.

**Evidence:** `test_supabase_default_grants_on_every_table_are_taken_away`
grants the three roles and PUBLIC everything on every model table, installs,
and requires them to hold nothing while the app role keeps exactly its kind's
privileges. `test_a_stray_login_cannot_truncate_a_users_table` checks TRUNCATE
from a login role. Removing the new revoke fails both. Removing the line that
spares `account_app` survives: the grants after it restore the app role, in one
transaction. It is kept so the role is never left with nothing, even
mid-install.

**Rejected:** deploying first and closing it later, and leaving it on the Data
API staying off. The fix is one schema run, and data safety comes first.

**Not changed:** Supabase's default privileges themselves (`ALTER DEFAULT
PRIVILEGES`). They are platform settings, so a future table still arrives
granted; the next schema run takes the grant back, and the read-back says so.

## D7. Applications are seen by season: saved, named, month to month (yours, 2026-10-13)

**Your ask:** seasons for applications. You choose when one starts and ends, and
all the data comes from that season (month-year to month-year).

**Your answers:**
- **Saved, with a name**, such as "Summer 2027 co-op", from Sep 2026 to Jan 2027.
  A new per-user table, `application_seasons`, which is an existing row-security
  kind, so the isolation boundary does not move.
- **Membership is by the date applied.** An application belongs to every season
  whose months include the day it was applied for, the whole end month counted.
  Nothing is assigned by hand, so an application can't be filed in the wrong
  season.
- **Seasons may overlap.** A season is a filter by months, not a container.
- **The page opens on the season you're in:** the one including today, or the
  most recent if none does, with "All time" showing everything.

**What a season filters:** the list, the figures and the Sankey, together. A
figure from one season beside a list from another would be the two-totals fault
the app avoids everywhere else. Calendar items are not filtered: a deadline is
a deadline, whichever season you're looking at.

**Rejected:** a picker remembered on one device only (yours to choose; it keeps
nothing between devices), and assigning applications by hand.

## D8. The Sankey is a tree: outcomes at the stage they happened, skipped stages passed through (yours, 2026-10-14)

**Your ask:** the graph intersects. It did, for two reasons: every outcome sat in
the last column, so bands from different stages had to swap order to meet at
one "Rejected"; and the bands at each node stacked in a fixed order that added
crossings of its own.

**Your answers:**
- **Outcomes per stage.** Each stage splits straight into the next stage and the
  ways applications ended there ("Rejected 56" after Applied, "Rejected 11"
  after Interview). A legend under the chart gives each outcome's total across
  stages.
- **A skipped stage counts as passed.** A stage counts everyone who got at least
  that far, so a direct interview is drawn through Screening. Every band then
  moves exactly one column.

With both, every column holds the children of one parent, in the order the
parent's bands leave it, so no two bands can cross. A test checks this
geometrically for every pair of bands. The interview and offer figures above
the chart are unchanged; a HelpTip says how to read the stage counts.

**Rejected:** keeping one node per outcome and only reordering the bands (fewer
crossings, not none); giving skipped paths their own stage nodes (stages would
appear twice); letting skip bands jump a column (accurate, but they cross).

**On a phone** the chart keeps a readable width and scrolls sideways inside its
box. Squeezed to 390px, its labels ran into each other. The page itself stays
phone-width.

## D9. The page lists what needs you; search finds the rest (yours, 2026-10-14)

**Your ask:** replace the lists with a search bar, showing applications only
when asking about "no reply". There's no use rendering hundreds of applications
without the need.

**What I pushed back on, and you took:** speed was never the problem (150 rows
render in milliseconds, and the list is fetched for search anyway); clutter
was. Hiding everything would also have hidden what matters most: an offer can't
go quiet, so a pending offer would never have appeared, nor an interview with
news in the last 30 days. And search needs you to remember a name, while
"what's still going?" has no search term.

**What was built** (`features/jobs/applications/triage.ts`, a pure function):
- **A search bar** over the chosen season: every word typed must appear in the
  company, role, location or source. While you search, the results replace the
  lists, finished ones included. Notes aren't searched.
- **Needs you:** offers, interviews and screenings (in that order, even once
  quiet), and any open application with a deadline in the next 14 days or a
  follow-up due within 7 days or overdue, soonest first.
- **No reply yet?:** the quiet ones (D3), longest silent first, with **"Mark all
  N as no reply"** after a confirm. Marked one at a time; if one fails it stops
  and says "Marked 1 of 3 as no reply, then stopped: …".
- **Waiting** (applied, not quiet, nothing due) and **finished** are hidden
  behind "Show waiting (n)" and "Show finished (n)". "Show waiting" wasn't in
  the agreed list; it was added so "what am I waiting on?" still has an answer
  without a search term.

**Rejected:** search plus the quiet ones only (offers and interviews vanish);
server-side search (the season's list is already on the page); searching notes
(private text turning up in a search result shown on screen).

## D10. Part B is built in one push, by me, item by item; nothing deploys until you say (yours, 2026-10-28)

**Your ask:** carry on with Phase 3 and complete it tonight.

**What "complete" can mean tonight:** every buildable item written, tested and
committed on `phase3`. Not the exit criteria, which need contributors (a parse
serving a second student, distributions above the floor). Not the deploy:
every item adds tables, so each has a schema step, which is yours, and backend
deploys wait for your go-ahead.

**Your answers:**
- **Scope:** all buildable items. Strava and Fitbit wait until you register the
  apps; the exertion score is manual until then.
- **Method:** by myself, one item at a time, each with its tests and decision,
  not a team of agents.

**Rejected:** shared figures only (items 3 and 5); a draft with nothing built.

## D11. The shared-aggregate kind: sealed, rebuilt daily, read through a function, floor of 5 (3 for merchants) (yours and mine, 2026-10-28)

Decided once, for items 3, 4, 5, 8, 11 and 12. The plan's version in
`phase3.md` (Part B) is the rule; this is why.

- **Sealed tables, not shared-read ones.** A shared-read table would rely on
  every route remembering the floor. A sealed table can't be read by the API's
  role at all, so the only way to a figure is a definer function that checks
  the floor itself. It is the Phase 2 D25 rule ("no route returns an aggregate
  is enforced by the database"), extended with exactly one door per figure.
- **Floors (yours):** 5 people for anything about people; 3 for a merchant's
  category. A merchant's category describes the merchant, not the people, and
  the map only ever answers with a category name, never a count.
- **Nothing moves in step with one person (closes the question D25 left).**
  Between two days' counts, a friend who knows you just answered could read
  your band from the one that grew. So:
  - **grades and course answers** count only once their term's asking window
    has closed (180 days after the term ends);
  - **pay** is published only in whole batches of 5;
  - **office hours** are a trailing 120 days of check-ins, where a slot's "busy"
    reading reveals nothing worth protecting.

  **What it costs:** the first distributions appear in mid-2027, from terms
  ending in December 2026. If that's too slow, the alternative is to publish a
  term once and freeze it. That's faster, but a late answer is never counted.
- **The merchant switch is on by default, which is mine to flag.** Grades are
  opt-in because a grade is sensitive. A merchant's category isn't, and an
  opt-in map would never reach 3 people in an invite-only app. Settings has the
  switch, and turning it off removes your votes at the next recount.

**Rejected:** a shared-read aggregate table; per-request recomputation
(D25: a figure must never change because of one request).

## D12. "Verified" means your review, and no document is ever read (yours, 2026-10-28)

- **A shared outline (item 2)** is verified when its student offers it and you
  approve it with `scripts/outline_review.py`. The script runs as the tables'
  owner, lists pending offers by course and term as counts of accounts (never
  who), and copies an approved outline into the shared table. It is the
  catalogue review's shape (Phase 2 D9).
- **A shared salary (item 12)** is verified when it matches the student's own
  recorded job at that employer within 5%, or when 5 or more shares for the
  employer agree within 10%. Unverified shares never count.
- **No pay stub, T4 or other document is read** for either (Phase 2 D20).

**Rejected:** agreement alone for outlines (two students would have to parse
the same syllabus before either is helped).

## D13. Directory and campus board introduce teams, never people (mine, 2026-10-28)

The vision rules out stranger discovery of any kind (§13.19), and puts a league
directory and campus leaderboards in Phase 3. Both are kept on the right side
of that line:
- **They list teams, by their captains' choice.** No member's name appears in
  the directory or on the campus board.
- **The one introduction is asked for.** "Ask to join" shows the captain the
  requester's name, because the requester chose to send it.
- **Individuals appear only on the team board,** to teammates, and only for
  those who opted in.

**Rejected:** individual campus rankings (strangers' names on a list).

## D14. What I decided while building Part B, item by item (mine, 2026-10-28; yours to overturn)

Each is small enough to change in one commit. Listed so nothing is decided
silently.

**Item 3, distributions.** A term shows only after its asking window has closed
(D11), so the first ones appear in mid-2027. The read function checks the floor
again, whatever the sealed table holds. Your own band is your final grade, or
your running average without one.

**Item 5, course intel.** One answer per person per course: their latest
counted term's review. Hours are a median, ratings a mean, both to one decimal;
"would take it again" is a whole percentage.

**Item 11, office hours.**
- Offered only on a course in your current term.
- A second tap within 30 minutes changes the first, so one visit is one answer,
  and Undo removes it.
- A slot is the local weekday and hour of the check-in, counted over the last 120
  days, and reads as the most common answer, the busier one on a tie.

**Item 12, salaries.**
- Pay is compared per hour: monthly × 12 ÷ 2080, yearly ÷ 2080.
- Employer names are normalised ("Shopify Inc." = "shopify") and shown as most
  people wrote them.
- A share holds no amount. If the offer's pay is removed, it stops counting.

**Item 4, merchants.**
- A person's vote is the category holding 80% of their own expenses at that
  merchant, the same bar their personal map uses.
- A merchant needs 75% of the votes as well as 3 people.
- Words like transfer, e-transfer, payment, deposit and ATM mark a description
  that is never a merchant.

**Item 2, outlines.**
- An outline is the categories above 0% and every assessment's name, category and
  due date.
- "Use it" only fills a course with no grades. Exams become calendar blocks and
  the rest tasks, as the syllabus reader does.
- Offering again resets the review. An outline you approved stays shared even if
  its student takes the offer back.

**Item 13, gym buddy.** Names shown are people's current display names, as
invite previews already show. In the isolation tests' paired world, B isn't
looking, so the walks can tell a leak from a share.

**Items 6–7, exertion.**
- Points are hours × MET × weight × 10, rounded.
- The METs are formula version 1, from the Compendium of Physical Activities'
  moderate values. A manual entry weighs 1.0.
- The suggested goal rounds to the nearest 5, never below 5, and needs two weeks
  with any activity.

**Items 8–9, boards and directory.**
- One "list this team on campus" switch covers both the directory and the campus
  board.
- Asking to join is closed until the directory opens (5 listed teams), and a
  declined request can't be sent again.
- The campus board counts the UTC week and is rebuilt daily. A team's board covers
  your own Monday-to-Sunday week.
- `teams.level` is checked by the request schema, not the database: the column
  goes onto a live table, and a check added there would exist only on fresh
  databases.

**Item 10, clubs.**
- The section sits on the Fitness page under teams for now. Say if clubs should
  have a page of their own.
- A club holds up to 200 members. A poll closes at the end of its last day (UTC),
  and members see counts, never who voted for what.
- Club events show on members' calendars read-only, pointing back to the club.

**The branch.** `phase3` was fast-forwarded to `redoc` before Part B began, so
the redocumentation and the new audit ship with Batch 3. That answers "merge
redoc?" from earlier; say if you'd rather keep them apart.

**Evidence, across Part B:**
- Every item has its own test file, and each runs on SQLite and Postgres. That
  adds 377 backend tests (2,606 → 2,983 on SQLite) and 55 frontend ones
  (792 → 847), all passing.
- Every new table is in the isolation, non-interference and RLS walks, and every
  definer function in the outsider and no-identity proofs.
- **Mutation check: 162 of 162 caught.** It removed or loosened rules item by
  item. Twelve survived the first run. Eleven were missing tests, now added. One
  was my local database keeping a grant from an earlier install; a clean
  database, as in CI, catches it.
