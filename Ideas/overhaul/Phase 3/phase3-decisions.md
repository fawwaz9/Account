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
