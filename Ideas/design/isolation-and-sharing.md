# Isolation and sharing

## Context

Two halves of one question: whose rows can a request reach? Until Phase 0 the
only answer was application code, with every query filtering on `user_id`. A
query that forgot its filter returned everyone's rows. Postgres now refuses to
return them whatever the query says, and every feature that deliberately
crosses between users goes through a narrow door built for it.

**Decisions taken:**
- Isolation is enforced twice: by the service's filter and by a row policy. The
  policy is the backstop, never the plan.
- An unidentified query sees **nothing**, not everything (fail closed).
- Anything that crosses between users is a `SECURITY DEFINER` function. It
  answers with an id, a status word or a few named fields, never with rows.
- Nobody is ever put into something without accepting a link.
- What a sharing feature shows another person is decided per feature, and is
  the minimum. Partners see a completion figure, never a grade, money or a
  task's name.

Phase 0 decisions D1-D11 (`overhaul/Phase 0/`) and Phase 2's D9-D14 and D18-D26
(`overhaul/Phase 2/`) carry the reasoning in full.

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `act_as(db, user_id)` | `_database/identity.py` | records who the session acts for; a listener writes it into `app.user_id` at the start of **every** transaction |
| `get_current_user` | `Auth/dependencies.py` | decodes the token and calls `act_as`, so every authenticated request is identified |
| `account_current_user()` | SQL, `rls.py` | reads `app.user_id`; NULL when unset, which matches no rows |
| `policy_statements`, `grant_statements`, `install` | `_database/rls.py` | generates every policy and grant from the model metadata |
| the 33 definer functions | `rls.FUNCTIONS` | sign-in lookups, the scheduler's queries, and every sharing step |
| SQLite twins | `_database/sharing.py`, `teams.py`, `distributions.py` | the same question as a plain query, for local and the default test run |
| `client_of` | `Auth/services/client_address.py` | the caller's address for the limiters, read from the right of `X-Forwarded-For` |
| `may_sign_up` | `Auth/services/signup_policy.py` | the `ALLOWED_SIGNUP_EMAILS` allowlist; gates creating an account, never signing in |

## Row security

The API connects as `account_app`: no superuser, no BYPASSRLS, owner of no
table. Only that role is named in the policies, so they constrain it and
nothing else. Policies are enabled but **not forced**: the tables' owner, the
role that existed before, is unaffected. That is what made the switch
reversible. Pointing `DATABASE_URL` back at the owner was the rollback, and on
2026-10-05 it wasn't needed.

`set_config(..., is_local => true)` lasts one transaction. Services commit in
the middle of a request, and production runs behind Supabase's transaction
pooler, where consecutive transactions can land on different connections. So
the identity is re-applied at the start of every transaction, never once per
connection.

**Every table is one of five kinds**, decided from the metadata so a new table
cannot be forgotten. `policy_statements` raises on a table that fits none.

| Kind | Rule | Tables |
|---|---|---|
| Root | `users`: a row is yours if it is you | 1 |
| Per-user | carries your `user_id` | most |
| Child | exactly one foreign key to an owned table; yours if its parent is | e.g. `grades`, `task_members`, `games` |
| Shared-read | every identified caller reads it; the app role writes none of it | `catalogue_courses`, `catalogue_prerequisites`, `shared_outlines` |
| Sealed | row security with no policy and no grant, the app role's included | `grade_distributions` and Phase 3's aggregates (below) |

**No-direct-write** is a refinement of the first three, not a sixth kind.
`task_members`, `event_members`, `team_members`, `games`, and Phase 3's
`team_join_requests`, `club_members` and `club_votes` are readable and
deletable by the app role, never insertable or updatable. Their rows come only
from a definer function. That is what makes "nobody is put on anything without
accepting" a property of the database rather than of the routes.

**Grants name model tables, and revoke from everyone else** (Phase 0 D11,
Phase 3 D6). A blanket `GRANT ... ON ALL TABLES` would have handed the role
`category_budgets`, an orphan with no policy (dropped 2026-10-19, but the rule
stands for the next one). Supabase grants every new function
**and table** to `anon`, `authenticated` and `service_role` by name, which
`REVOKE FROM PUBLIC` misses. So `install` takes every privilege on every model
table, and on every function, from every grantee except the owner and
`account_app`, then grants the app role exactly what each table's kind allows.
TRUNCATE ignores row security, which is why "no policy names them" was not
enough.

> **Until 2026-10-13 that held for shared and sealed tables and functions only.**
> Phase 3 batch 1's read-back showed the three roles holding everything on the
> new tables, and so on every per-user table. They were reachable only through
> the Data API, which is off. A future table still arrives granted, because
> Supabase's default privileges are platform settings; the next schema run takes
> the grant back, and read-back B2 checks it.

**Proven three ways, in CI on both databases:**
- `test_isolation.py` builds two users with one of everything (`isolation_world.py`).
  It walks every route as each user and every table, and asserts neither
  reaches the other.
- `test_noninterference.py` checks that one user's writes never move another's
  figures.
- `test_rls.py` checks the policies themselves against a real Postgres, as the
  restricted role.

During Phase 0 each of the 164 `user_id` filters was removed in turn, and every
gap that exposed was closed (D10). The suites found real bugs on the way:
`_` and `%` acting as wildcards in email lookups, an account-takeover path.

## The sharing pattern

Partners, shared tasks, shared events and teams are built the same way. The
pattern is the design, and the next sharing feature should copy it rather than
invent one.

1. **The membership and its link hang under the owned thing.** `task_members`
   and `task_invites` are children of `tasks`, so the ordinary child policy
   makes both the owner's alone. No new policy shape was needed for any of the
   four.
2. **A link carries a token, and only its SHA-256 is stored.** The token
   travels in the URL fragment (`/invite#task:…`, `#event:`, `#team:`, a bare
   fragment for a partner), which browsers never send to a server. Links last
   seven days. Signing in from one returns you to it, and only to a path on
   this site.
3. **Accepting is a definer function, for the caller only.** It writes the
   membership row the app role cannot write itself.
4. **Everything a member does is a definer function** keyed on
   `account_current_user()`: preview, accept, read, the few permitted edits,
   leave. Each checks membership itself.
5. **Names are copied** onto the membership when it is made (`member_name`,
   `owner_name`). A function that read another user's `users` row to show a
   name would be a wider door than the feature needs.
6. **Deleting a user cascades** through `member_id` (`ON DELETE CASCADE`), and
   the user model's relationships to memberships are view-only, so the ORM
   never tries to write them.

Each feature then decides what a member may do:

| Feature | Decision | What a member does | Limits |
|---|---|---|---|
| Partners (item 10) | D22 | sees your week's completion percentage and your streak of good weeks (80%+, capped at 26) | 5 open invites; mutual pair; ending removes both rows |
| Shared tasks (9a) | D23 | sees title, notes and due date; ticks it done for everyone; edits title and notes; leaves | one-off tasks only; 8 members; never the course, grade, timer, priority or tags |
| Shared events (9b) | D24 | sees it on their own calendar, drawn dashed; leaves; changes nothing | one-off events of your own only, not a repeat, shift or grade block; 8 members |
| Teams (11) | D26 | records a game; confirms or disputes someone else's | 30 members; the captain alone renames, removes or deletes |

**Why a task is editable and an event is not:** a task is the group's work,
while an event is a time and place one person set.

**A partner's figure is written by its owner, as its owner.** Opening the
partners panel works out your figure from your own tasks and writes it into your
own row. Your partner reads it through `account_partner_figures`, which answers
only while each of you has a row pointing at the other. No job ever reads across
users.

**A shared thing counts for its owner alone.** A member's week, estimates and
partner figure read only their own tasks. A shared event doesn't reach a
member's free blocks, week load or crunch strip. That is still open, below.

### Teams and games, on the Fitness page

The page was "Teams" until the owner renamed it Fitness (`/fitness`, G then F).
The module stays `Teams`.

- **A score counts once someone other than its recorder confirms it**, the
  captain included. Until then it is shown as unconfirmed and left out of the
  record.
- **A dispute shows both scores** until the recorder corrects theirs, which
  clears it. Confirming your own dispute withdraws it. Nobody may confirm over
  someone else's dispute.
- **The record** (wins, losses, ties, points) comes from confirmed games only
  (`team_service.record_of`).
- **Every game write goes through a definer function, the captain's too**:
  record, confirm, dispute, correct, delete. The recorder may delete while it is
  unconfirmed; the captain may delete any game. `recorded_by` carries no
  foreign key, so a game outlives the member who recorded it, with the name
  copied.

No leagues yet.

## The shared catalogue, and the sealed counts

**`catalogue_courses` and `catalogue_prerequisites` belong to nobody.** Every
identified caller reads them (`account_current_user() IS NOT NULL`, still
fail-closed). The app role can write none of it: refused once by a SELECT-only
grant and again by a policy that covers SELECT alone. Only the owner-run
`scripts/catalogue_review.py` writes, and it refuses to run as the app role.
Proposals reach it as counts of accounts and the rule tree alone, never who
proposed them. How a course links to the catalogue is in [grades.md](grades.md).

**`grade_distributions` is sealed** (D25). The end-of-term review's opt-in
adds your grade to a course's distribution, so the table would answer "what did
this person get" if anything could read it per row. Nothing can.
`account_recount_grade_distributions()` rebuilds it whole, reading grades at
that moment. It writes nothing for a course-term with fewer than 5 contributors
(`COHORT_FLOOR`), and buckets grades by five, with everything under 50 in one
bucket. The review itself holds no copy of the grade. A recount is triggered
through `/api/internal/distributions/recount`, which answers 403 without its
secret. Its daily schedule is the owner's optional step, and nothing displays
the distributions until Phase 3.

## Shared figures above a floor (Phase 3, D11)

A figure everyone reads but nobody can trace to a person: grade distributions,
course intel, office-hour slots, co-op pay, the merchant map and the campus board.
One rule for all of them:
- **A sealed table**, rebuilt whole by its own definer recount, run from the one
  scheduler route (`_database/recounts.py`). Nothing below its floor is written.
- **One definer read per table**, taking a key and checking the floor again, so no
  route can read an aggregate any other way (`_database/aggregates.py` holds the
  SQLite twins).
- **No user id**, and nothing per contribution, in any aggregate table (a test
  checks every sealed table's columns).
- **Floors:** 5 people (`COHORT_FLOOR`), or 3 for a merchant's category
  (`MERCHANT_FLOOR`). The directory and campus board wait for 5 listed teams.
- **Nothing moves in step with one person.** Grades and course answers count only
  after their term's asking window has closed (`COUNTED_AFTER_DAYS`), and pay is
  published only in whole batches of 5.

Adding one means: a sealed model, its recount and read in `rls.FUNCTION_SQL` with
their SQLite twins, an entry in `recounts.RECOUNTS`, a row in
`isolation_world.seed_catalogue`, and the outsider and no-identity proofs in
`test_rls.py`.

## Who gets in

**Signup is by allowlist until open signup** (D19). `ALLOWED_SIGNUP_EMAILS` on
Cloud Run gates creating an account, through both the password and Google
paths. An account that exists keeps working whether or not it is listed.
Removing an address declines a new signup and destroys nothing. `./invite.sh
a@x.com, b@y.com` merges addresses into the list, and it refuses if the current
list is empty or unreadable, since overwriting it would open signup. Unset
means open, so a fresh clone can create its first account.

**Throttling is per caller** (D18). Behind Cloud Run the peer address was the
platform's proxy, which made the limiters one shared budget for everyone.
`client_of` counts `TRUSTED_PROXY_HOPS` entries in from the **right** of
`X-Forwarded-For`, because the left end is whatever the client wrote. With 0
(the default) the header is ignored. Production runs with 1, set after a forged
header was checked and ignored.

## Notes

- **A new table needs its kind** before the schema step can generate policies
  for it. A sealed or shared-read table is named in its list. A table with an
  owner in either list raises.
- **A new route goes into all three walks** in the same change: `PATH_SOURCES`
  and `BODY_PATCHES` in the isolation walk, `DOMAIN_404` for non-interference,
  and the RLS walk.
- **A definer function needs its REVOKE and GRANT**, an entry in `FUNCTIONS` (the
  schema gate checks it exists), a SQLite twin that means the same thing, and a
  Postgres proof in `test_rls.py`.
- **API tests sign in with real tokens.** Overriding `get_current_user` skips
  `act_as`, and on Postgres the test then reads nothing. Item 10's partner test
  passed by accident that way until 9a's caught it.
- **The scheduler is the one cross-user reader**, and it reads ids only.
  `account_users_with_unpushed_reminders` says who has something waiting;
  everything after runs as one user at a time, so a reminder can only be sent to
  its owner's devices.
- **Reading production data is the owner's call**, never a step in a runbook a
  session runs by itself.

## Still open

- A shared event doesn't count in a member's free blocks, week load or crunch
  strip.
- Open signup (12b) waits on D19's conditions; until then every invitee is
  added with `invite.sh`.
- The catalogue is empty until the owner approves proposals. A UBC calendar
  import (item 8) waits on UBC's answer.
- Grade distributions are counted and shown nowhere until Phase 3.
