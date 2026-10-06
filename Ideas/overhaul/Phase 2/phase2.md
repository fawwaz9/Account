# Phase 2 — Worth sharing

Written for: you, deciding the plan before any of it is built.

Taken from `account-vision.md` §4 (Phase 2), §5.1, §5.4–§5.6, §11, §13.19 and
§15. Brought up to date on 2026-10-05 against the code on `phase1` (`26db894`).
Follows `Ideas/overhaul/template.md`.

**What changed in this draft (yours, 2026-10-05).** The shared course
catalogue was first planned on its own. You asked for it to be a phase "for
continuity", so it is now the first part of Phase 2, and the vision says so
(§4). It fits Phase 2's own test: it needs two people, never a cohort. One
reviewed fact helps everyone who takes the course. And its policy shape, a
table everyone reads and nobody owns, is the safe half of the sharing that
Phase 2's shared tasks then extend to writes.

- **Part A, the shared course catalogue,** is planned in full below (items 1–8).
- **Part B, the rest of the vision's Phase 2** (items 9–14), is listed and
  checked against the code, but not yet drafted in detail. It gets the full
  draft before its work starts.

## What Phase 2 is for

The vision: "the first phase whose purpose is **more users**, not more
features. Everything here needs two people or a team, none of it needs a
cohort."

Part A, in your words: **courses should know their prerequisites, and these are
shared between all users, like all courses are.** Prerequisites are **not a
hard limit**, because exceptions are made (D3, D4).

The rules that apply directly:
- **Data safety first.** No request ever writes a shared row, and no request
  reads another user's rows (§5.6). Shared figures are written by a job.
- **World knowledge is shared; personal facts never leave the user** (§13.3).
  "CPSC 221 needs CPSC 210" is world knowledge. "I took CPSC 210" is personal.
- **A wrong shared fact reaches everyone** (§15). So nothing one person enters
  becomes shared without a check.
- **Your own version always wins for you** (§13.19, "manual override, always
  available").
- **Advisory, never blocking.** An unmet prerequisite is a warning, phrased as
  one.

## Exit criteria: Phase 2 → Phase 3

From §11, unchanged:
- [ ] ≥5 active teams playing real games with same-day score logging
- [ ] registrations from outside the invited group retaining at week two
- [ ] an accountability partnership surviving a month
- [ ] moderation load inside a few hours a week

Added for Part A, because a shared table needs its boundary proven before it is
used:
- [ ] **The catalogue policy is proven on Postgres:**
  - every signed-in user can read the catalogue
  - the API's role cannot insert, update or delete it
  - `anon` and `authenticated` get nothing, including through Supabase's
    default grants
  - the generator still refuses any table that is neither per-user nor on the
    shared list
- [ ] **One person's entry cannot reach another person before review.** A test
  walks every route.
- [ ] **Each of your current courses is linked to a catalogue course, or
  deliberately to none.** Linking moves no grade, average or credit.
- [ ] **The course page shows prerequisites as met or not met,** labelled by
  source, with nothing blocked.
- [ ] **UBC has answered the calendar request,** and the answer is recorded.

**Measurable today:** none. The four from §11 need teams, open signup and
partnerships, none of which exist. Part A's are tests and page checks.

## Status at a glance (2026-10-06)

Work is on the `phase2` branch, cut from `main` at `5c2cc43`. **Nothing from
Phase 2 is deployed.**

| # | Item | Status |
|---|---|---|
| **A** | **The shared course catalogue** | **In progress** |
| 1 | The policy for shared, read-only tables | **Built, not deployed** (D9). Proven on Postgres and mutation-checked |
| 2 | Catalogue tables: courses and prerequisites | **Built, not deployed** (D10). Runbook step 1 is written |
| 3 | Linking your courses to the catalogue | **Built, not deployed** (D11). Matched on read; your override stored |
| 4 | Your own prerequisites, and proposals | **Built, not deployed** (D12) |
| 5 | The syllabus reader picks up prerequisites | **Built, not deployed** (D14). Files only what you confirm |
| 6 | Owner review: proposals into the catalogue | **Built, not deployed** (D13). `scripts/catalogue_review.py`. Auto-approval is planned, not built (D5) |
| 7 | Prerequisites on the course page, met or not | **Built, not deployed** (D12). Also warns when adding a future course |
| 8 | UBC's permission, then a bulk import | Request drafted (`Ideas/overhaul/calender-request.md`); waits on UBC |
| **B** | **The rest of the vision's Phase 2** | **Drafted 2026-10-06; waiting on your answers (Q1–Q5)** |
| 9 | Shared tasks and events (group coursework) | Not started. No collaborator tables; tasks and events are per-user |
| 10 | Accountability partners | Not started |
| 11 | Team sport and intramurals | Not started. No team, league or game tables |
| 12 | Open signup, with affiliation verified later | Not started. **Gate:** the rate limiter is still global (`client_of` returns the peer, which is Cloud Run's proxy) |
| 13 | End-of-term flow: ratings and anonymous grade contributions | Not started |
| 14 | Shift-versus-exam conflict flags, and the tax packet | Not started |

## Part A: the shared course catalogue

## Cross-cutting facts to settle before building

**A. The policy for a table nobody owns.** (Decide first; item 1 builds it.)

The generator knows three shapes today:
- `users`
- a table with `user_id`
- a child with exactly one owning parent

Anything else raises, which is good. The plan adds a fourth shape, but only by
name:
- **A short allowlist of shared tables in `rls.py`.** A table outside the
  allowlist with no owner still raises.
- **For those tables, the policy is `FOR SELECT TO account_app USING (true)`,**
  and nothing else. Under row-level security, having no write policy means
  writes are refused.
- **The grant is `SELECT` only,** never the four verbs the other tables get. So
  a write is refused twice: by the grant, and by the policy.
- **Writes happen only as the table's owner,** the role you run the schema step
  as, through an owner-run script. That's the same pattern as the usage
  report. **The API cannot write the catalogue at all.**

**What it costs:** every addition waits for you to run the review (item 6). At
about 20 users that's minutes a week. At open signup it would need an admin
path with its own role, priced then. **The rejected alternative:** an admin
route in the API. That would put write access to shared rows behind
application code, which is the exact class of bug row-level security exists to
remove.

**B. Which school, and how a course is named.** Calendars differ by campus:
UBC Vancouver and UBC Okanagan publish separately, and your own path crosses
both. **Both campuses from the start** (yours, D7). Key: **(campus, subject,
number)**. Codes like `CPSC_V 110` and
`COSC_O 111` already carry the campus, and `course_lookup.code_parts` already
strips the suffix when matching. **Narrowest version:** a `campus` text column
(`UBCV`, `UBCO`), not §5.3's `organizations` tree. That tree can replace it
when leagues need it, which is the "prefer the narrowest design" rule.

**C. Prerequisites change every year.** Each prerequisite row carries the
calendar session it is from (for example `2026W`). The audit reads the session
that applied when you took the course, and the planner reads the current one.

**D. What a prerequisite looks like.** An AND/OR tree in JSON, over course
keys and "one of" groups, with credit thresholds ("6 credits of MATH 100-level").
Anything a tree can't hold stays as a plain note beside it: year standing,
programme restrictions, "or permission of the instructor". Co-requisites are a
separate kind. The source sentence is always kept with the tree, so what the
app shows can be checked.

**E. Where facts may come from.** UBC's terms of use cover the calendar
([ubc.ca/site/legal](https://www.ubc.ca/site/legal.html)):

> "None of the information may be otherwise reproduced, republished or
> re-disseminated in any manner or form without the prior written consent of
> the University of British Columbia."

So until UBC agrees (D2):
- **No bulk copy of the calendar.**
- **The sources are the user's own syllabus, and what the user types.**
- **What becomes shared is the structured fact** ("CPSC 221 requires CPSC 210"),
  never a document's own sentences. The source sentence is shown only to the
  person whose document it came from.

**Decided (yours, D6): syllabus prerequisites are the source for now.** The
structured fact from a syllabus can be shared once reviewed, and the source
sentence stays private. That's my reading of the terms, not legal advice.

**F. How your course links to the catalogue.** A nullable
`courses.catalogue_course_id`, an additive column (§5.5).
- **When it's set:** linked on create, or on applying a syllabus, by matching
  the campus and normalised code.
- **An ambiguous match links nothing,** which is `course_lookup`'s existing
  rule.
- **You can always link or unlink by hand.**

**G. Nothing discloses other users.** No "3 students proposed this", and no
counts. A reviewed fact says "reviewed", not who sent it.

## 1. The policy for shared, read-only tables

**What:** cross-cutting fact A, in `rls.py`.

**Tests, on Postgres:**
- the app role can `SELECT`
- the app role's `INSERT`, `UPDATE` and `DELETE` each fail
- with Supabase's by-name grants to `anon` and `authenticated` modelled (the
  Phase 0 D11 lesson), both get no rows
- a table that is neither per-user nor allowlisted still raises

Mutation-test the allowlist check, the `SELECT`-only grant, and the absence of
a write policy.

**Done when:** all of the above pass in CI's `backend-postgres` job, and each
mutation fails a test.

## 2. Catalogue tables

**What:**
- **`catalogue_courses`:** campus, subject, number, title, credits.
- **`catalogue_prerequisites`:** catalogue course, kind (prerequisite or
  co-requisite), session, rule (JSON), note, source sentence, and source
  (`reviewed-proposal` or `ubc-calendar`).

Both are written only by the owner-run script.

**Facts to settle:** B, C, D.

**Done when:**
- the tables exist under item 1's policy
- the schema gate knows them
- the isolation walk finds no route that writes them

## 3. Linking your courses to the catalogue

**What:**
- The link column (F), auto-linked on create and on applying a syllabus.
- A "Catalogue course" line on the course page, with link and unlink.

The link changes nothing in any grade calculation.

**Done when:**
- the dashboard, averages and credits are identical before and after linking
  (a test, like Phase 1's non-interference walk)
- an ambiguous code links nothing

## 4. Your own prerequisites, and proposals

**What:**
- **A per-user `prerequisite_proposals` table:** your course, rule, note,
  source (`syllabus` or `typed`), and status. It is an ordinary per-user table,
  so the existing generator covers it.
- **It applies to you at once,** which is your own version winning.
- **Others see only reviewed catalogue rows.**

**Done when:**
- one user's proposal changes nothing in any other user's responses (the
  non-interference walk, extended)
- your own proposal shows up for you immediately

## 5. The syllabus reader picks up prerequisites

**What:**
- **The prompt asks for prerequisites and co-requisites.**
- **The check screen shows them, editable.**
- **Confirming files them as your proposals.** It runs through the same adapter
  and the same "nothing becomes a record without confirmation" rule (D16).

**Done when:** a syllabus that lists prerequisites produces proposals you
confirmed, and nothing you didn't.

## 6. Owner review

**What:** an owner-run script, like the usage report.
- **It reads pending proposals as counts per course and rule.** It shows no
  names and no ids.
- **It suggests where independent proposals agree.**
- **On your approval it writes catalogue rows,** and marks the proposals
  accepted or rejected.
- **It runs as the table owner,** from the runbook.

**Not yet: automatic approval (yours, D5).** Every addition goes through you
during the beta. **The plan for later:** a proposal is approved automatically
once about **five different people** have independently proposed the same rule
for the same course. Before that's built, settle:
- **"Different people" means distinct accounts, counted once each.** Two
  uploads by one person count once. Before open signup, when accounts become
  cheap to make, it should mean distinct *verified* accounts (§5.3), or one
  person with five accounts could approve anything.
- **"The same rule" means the same structured tree,** compared after
  normalising codes, not the same wording.
- **Who writes the row.** The API still can't. An automatic approval needs a job
  with its own connection: a role that can write only the catalogue tables and
  read only proposal counts. That's a new role, so it's an owner step in the
  runbook.
- **Every automatic approval is logged and revertible by you,** and you get the
  list in the review script.
- **The threshold is a setting, not a constant,** so five can move once there's
  evidence.

**Done when:**
- an approved proposal appears in every user's catalogue
- a rejected one stays only with its author
- the script refuses to run as the app role

## 7. Prerequisites on the course page

**What:**
- **Each prerequisite shows met or not met** against your passed and transfer
  courses.
- **Each is labelled with its source.**
- **The wording is "not met, and exceptions are sometimes made",** never a
  block.
- **Adding a course to a future term gets the same warning.**

**Done when:**
- your own courses show the right answers, including a transfer credit
- no action anywhere is disabled by an unmet prerequisite

## 8. UBC's permission, then a bulk import

**What:** you ask UBC, using the draft in `Ideas/overhaul/calender-request.md`.
If they agree:
1. **A yearly snapshot** of the calendar's course data.
2. **The prerequisite text parsed into trees** through the intake adapter.
3. **You verify a sample** against the calendar.
4. **The owner-run script writes the rows,** labelled `ubc-calendar`.
5. **Each year's import is a diff you review.**

For scale: an open-source snapshot of the Vancouver calendar holds about 9,500
courses ([ubc-prereq-visualizer](https://github.com/AsarMichil/ubc-prereq-visualizer)).

**Done when:** UBC has answered and the answer is recorded. If yes: your
programme's courses audit correctly against the import.

## Suggested order

Part A first. Its policy is the first shared table, and Part B's shared tasks
build on a proven boundary.
1. **Item 1, the policy.** Nothing shared exists until the boundary is proven.
2. **Item 2, the tables.**
3. **Item 3, linking.** Your own courses get catalogue rows to hang
   prerequisites on.
4. **Item 4, proposals.** The per-user half, useful to you on day one.
5. **Item 7, the course page.** It reads 2 and 4.
6. **Item 5, the syllabus reader.** It fills 4 without typing.
7. **Item 6, owner review.** Sharing switches on.
8. **Item 8, when UBC answers.**

Then Part B, once it is drafted. Item 12's rate-limiter gate stays ahead of open
signup, as the vision says.

Send the calendar request **now**, in parallel. It costs nothing, and the
answer decides how much of 4 to 6 an import later replaces.

**The trade this order makes:** you get your own prerequisites before anyone
shares any, so the network effect comes last. The other order puts shared
writes ahead of the review that makes them safe.

## Part B: the rest of Phase 2 (drafted 2026-10-06, for you to read before any of it is built)

Checked against the code on `phase2` (`b5be61d`). Part A's items 1–7 are
built, and Part A's policy is the base everything below extends. **Nothing in
Part B is built.** The questions at the end decide its order.

### Cross-cutting facts to settle before building Part B

**B1. The first write across users: membership, not ownership.** Items 9, 10
and 11 each let one person's row be seen, and in 9 and 11 changed, by someone
who doesn't own it. §5.6 sets the pattern: an explicit membership table, with
membership writable only by the owner.
- **The generator gets a fifth shape, by name only, like Part A's allowlist.**
  A row is yours if you own it, or if a membership row says you are on it.
  Reads and member-allowed writes use the second test. Changing the
  membership list itself uses only the first.
- **The recursion trap.** A policy on `tasks` that reads `task_members`, whose
  own policy reads `tasks`, makes Postgres fail with "infinite recursion
  detected in policy". The usual fix is a `SECURITY DEFINER` function that
  answers yes or no ("is the caller a member of this task?"), the same pattern
  as the Phase 0 sign-in lookups. It is proven on Postgres, with the Supabase
  grants modelled, as Part A was.
- **What a member may do is listed per table,** not "everything". On a shared
  task, a member may tick it done and edit its text. Only the owner may delete
  it or change who is on it.

**B2. One way for two people to connect: an invite link.** It is shared by 9,
10 and 11.
- **The invite is an unguessable token.** The inviter sends the link
  themselves, by text or group chat. Opening it while signed in asks "join X's
  task?" (or partnership, or team), and accepting creates the membership.
- **Rejected: invite by email address.** It needs an email service the app
  doesn't have. Worse, "no account with that address" tells the inviter who
  uses the app, which is the disclosure §5.6 forbids. A link reveals nothing,
  and works for someone who hasn't signed up yet. That person signs up through
  the link, which is the growth loop.
- **Tokens expire** (7 days), are single-use for a partnership and multi-use
  for a team, and can be revoked by the inviter. They are looked up through a
  definer function that returns only what the invite is for.

**B3. What one member sees of another: a display name, never an email.** Today
`users` is readable only by its own row. Members need each other's names, so
either a definer function returns names for the caller's own memberships
only, or the name is copied onto the membership row when joining. **My
recommendation is the copy:** it's simpler to prove, and a rename updating
everywhere doesn't matter at this scale.

**B4. When a member is deleted.** Their memberships go with them, by purge
cascade. **When the owner is deleted, the shared task goes for everyone.** The
alternative, handing it to a member, is a transfer of ownership nobody asked
for. **This is your call** (question Q3).

**B5. The tests that must grow.**
- **The isolation world gains a shared object between A and B.** The
  invariant becomes "B sees exactly what A shared with B, and changes only what
  a member may".
- **The route walk gains a variant:** a member trying an owner-only action.
- **The non-interference walk** compares A's answers with and without B as a
  member.

### 9. Shared tasks and events (group coursework)

**What** (§4, §5.1, §5.6). Add a collaborator to a task or a calendar event,
and it appears for everyone on it. Anyone on it can tick it done.

**What exists:** tasks and events are strictly per-user (`user_id`, no
collaborators). Recurring tasks materialise per user, and reminders push per
user.

**Facts to settle:**
- **What is shared:** one-off tasks and one-off events only, to start. A
  repeating rule shared across people multiplies every edge case the
  repeating-edits work fixed (Phase 1).
- **"Done" is shared:** one tick closes it for everyone. Per-person done is the
  other choice; one tick fits group work.
- **Whose reminders?** Each member sets their own. A shared task carries no
  reminder of its own.
- **Grades never shared:** a task linked to a graded assessment stays linked
  only for its owner. A member's copy shows the task, never the grade.

**Trust cost:** high. It is the first write by one user to another's row. It
waits for B1's policy, proven on Postgres and mutation-checked, before any
route exists.

**Done when:**
- A member sees and can complete a shared task. A non-member gets nothing: not
  in a list, not by id, not by a guessed id.
- A member cannot delete it or change its members. The route walk proves both,
  on Postgres, as the app role.
- Removing a member removes their access at once.

### 10. Accountability partners (completion, not outcomes)

**What** (§4). Share a weekly completion percentage or a streak with one
friend. Never grades, never money: outcomes are excluded by the vision's own
rule (§13.7, "explicitly not building").

**What exists:** the task completion data, per user. Nothing shared.

**Facts to settle:**
- **The figure:** tasks done on time this week, as a percentage, plus a streak
  of weeks above your own goal. It is computed by a job into a partnership row,
  never read across users at request time (the §5.6 rule).
- **Either partner can end it at any time,** and the other sees only "ended".
- **What is shared is opt-in and listed on the invite.** Nothing more is ever
  added without asking again.

**Trust cost:** low. It is read-only, two people, and figures you chose to
share. **It's the smallest feature that needs B2,** so it's the right place to
prove invites before shared writes depend on them.

**Done when:** a partner sees exactly the agreed figure. Ending it removes the
partner's access at once. The figure comes from the job-written row, which
the route walk shows.

### 11. Team sport and intramurals

**What** (§4, §15). Create a team, invite teammates, and anyone records a game
score. Everyone sees results and standings, and a teammate confirms a score
before it counts.

**What exists:** nothing. There are no team, league, game or organisation
tables.

**Facts to settle:**
- **The narrowest model:**
  - `teams`, plus `team_members` (B1).
  - `games`: team, opponent as text, date, scores, recorded-by, confirmed-by.
  - **No leagues or organisations yet,** the §5.3 tree included. Standings are
    per team, across its own games. Leagues wait until two teams want to play
    each other inside the app.
- **Per-sport stat templates:** none in the first cut, only scores.
- **Confirmation:** a score counts once a second member confirms it. A
  disputed score shows both.
- **Captain:** the creator owns membership (B1). A second captain is a later
  question.

**Trust cost:** medium. It's B1's pattern again, on new tables with no
history to protect.

**Done when:**
- A five-person team records and confirms a game in under 30 seconds on a
  phone.
- A non-member sees nothing of the team.
- The route walk proves members can't change membership.

### 12. Open signup, with affiliation verified later

**What** (§4, §6, §9.1). Anyone can register, not only the invited addresses
in `ALLOWED_SIGNUP_EMAILS`.

**What exists:**
- **Signup is gated** by the allowlist (`signup_policy.py`), on both the
  password path and the Google path.
- **Email verification exists only for Google accounts.** Google vouches for
  the address, and there is no verification email.
- **Account deletion exists,** with a grace period and purge.
- **The rate limiter keys on the peer address.** Behind Cloud Run that is the
  proxy, so the limiter is effectively global (`client_of` in
  `api/routes/auth.py`).

**It splits in two, and the first part is a safety fix worth doing anyway:**
- **12a. The rate limiter keyed per client.** Trust exactly one forwarded
  position: the entry Cloud Run's front end appends, read from the right,
  never a raw `X-Forwarded-For`. **Facts to settle:** which position Google's
  front end guarantees, confirmed against Cloud Run's documentation and a
  logged request. A test sends a forged header and shows it doesn't win.
- **12b. Opening signup:**
  - a verification email for password accounts, which needs an email service:
    a new provider, a secret and a cost
  - a cap on new accounts per client per day
  - your decision to remove the allowlist (an owner step)

**Trust cost:** high, and the vision says so: it opens the attack surface
earlier, with more support load on one person. **This is the item to overrule
if the appetite isn't there.** The rest of the phase stands without it.

**Done when:**
- **12a:** two clients are throttled separately, and a forged header can't
  reset a client's budget. Both are tested, and both are read from production
  logs after the deploy.
- **12b:** a stranger can register, verify and use the app. An unverified
  account can't do anything that reaches another person (invites, teams).

### 13. End-of-term flow: course ratings and anonymous grade contributions

**What** (§13.7). One "rate your term" screen after grades post: 4–5
questions per finished course. Also an opt-in "add my final grade to the
course's distribution".

**What exists:** finished courses and final grades (per user), the catalogue
(Part A) to key ratings on, and the survey table pattern (Phase 1 D12).

**Facts to settle:**
- **Anonymity that holds.** A contribution must not be traceable to its author
  in the stored aggregate. But each person must contribute once per course and
  be able to withdraw.
  - **My proposal:** your own row records that you contributed (per-user,
    private). The aggregate is written by a job into a shared, job-only table
    keyed by catalogue course and term (§5.6), with a cohort floor before
    anything is shown (Phase 3). The job, not a request, does the counting.
  - **Withdrawing** removes your row, and the next job run recounts.
- **When it asks:** the term's end plus about two weeks for grades.
- **Nothing is shown in Phase 2.** Collection only. The distributions are
  Phase 3.

**Trust cost:** medium. Grades are the most sensitive data in the app, and
"anonymous" is a promise that has to be true in the schema, not only on the
screen.

**Done when:**
- A contribution exists only as your private "contributed" mark and a count
  inside the job's table.
- No route returns any aggregate.
- A test shows the job's table can't be traced back to a person, even by
  anyone holding the database.

### 14. Shift-versus-exam conflict flags, and the tax packet

**What** (§13.11, §13.12). Two single-user builds:
- **Conflict flags:** a shift that overlaps or crowds an exam or a final
  (from the calendar) is flagged on both pages.
- **The tax packet:** a year's employment income, deductions and tips,
  gathered from what you've recorded, as one printable page.

**What exists:**
- Shifts, jobs and paycheques with their deductions (Phase 1 D11).
- Exams as calendar events, from grades and the syllabus.
- Nothing that checks one against the other, and no yearly roll-up.

**Facts to settle:**
- **"Crowds":** a shift within N hours before an exam (my default: 12). That
  is a setting, not a constant.
- **The tax packet uses only what you recorded.** Reading a T4 is a personal
  document, so it waits on your rule about sending those to a model.
  Recorded paycheques already carry the figures.
- **It is labelled as a summary for your own records, not tax advice.**

**Trust cost:** low. It's single-user and reads existing data.

**Done when:**
- A shift the night before a final is flagged on the Jobs page and the
  calendar.
- The packet's totals equal the sum of your recorded paycheques for the year
  (a test).

### Suggested order for Part B

1. **12a, the rate limiter.** A known safety gap, small, and needed before
   anything opens up. It's worth doing even if 12b never ships.
2. **14, conflicts and the tax packet.** Single-user, low risk, and useful now.
   It needs nothing from B1 or B2.
3. **10, accountability partners.** It proves invites (B2) on a read-only
   feature.
4. **9, shared tasks.** The first shared write (B1), on proven invites.
5. **11, teams.** B1 again, on fresh tables.
6. **13, end-of-term collection.** It reuses the job-written-table pattern.
   It needs to be live before the first term ends after it ships, so it moves
   earlier if December comes first.
7. **12b, open signup.** Last, once everything a stranger could reach has its
   policy.

**The trade this order makes:** the growth features (11 and 12b) come last,
so more users arrive later. In exchange, every shared write lands on a proven
policy and a proven invite. The vision's order puts teams first because they
are the acquisition loop. That's question Q1.

## Open questions

Part A has none open. Part B's, all yours:
- **Q1. The order.** Mine is above: safety (12a) and single-user (14) first,
  then partners, tasks, teams, collection, and signup last. The vision leads
  with teams as the acquisition loop. Which comes first?
- **Q2. Invites by link (B2) rather than by email address?** Links need no
  email service and reveal nothing about who uses the app.
- **Q3. When the owner of a shared task deletes their account,** does the task
  go for everyone (my default), or pass to a member?
- **Q4. Open signup (12b) at all in Phase 2?** It needs an email provider (a
  new service, secret and cost), and the vision names it the item to overrule.
  12a ships either way.
- **Q5. The tax packet from recorded paycheques only,** until your rule on
  personal documents decides T4s?

## What the vision says that has since moved

- **§4 put the canonical course table in Phase 1.** It is now Phase 2 Part A
  (this draft), and the vision is edited to match.
- **§15 says "must hand-seed popular UBC courses",** and Phase 1 D19 recommended
  reading the calendar. **UBC's terms need written consent for that** (D2).
  Seeding waits on item 8; until then, prerequisites come from syllabi (D6).
- **§5.1 lists `syllabus_parses` and `grading_schemes` as shared.** Phase 1
  built both per-user (D16, D18). Sharing them is Phase 3, and it would reuse
  item 1's policy shape.
- **§5.5 step 3, "backfill by hand — trivial at 31 courses",** becomes an
  automatic link by campus and code (F), with a manual override.
- **§5.6, "shared tables are readable by authenticated users; writes are
  constrained".** Part A constrains writes to none at all from the API, which is
  stricter than the vision.
