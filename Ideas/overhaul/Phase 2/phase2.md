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
| 5 | The syllabus reader picks up prerequisites | Not started. The reader exists (Phase 1 D16) |
| 6 | Owner review: proposals into the catalogue | **Built, not deployed** (D13). `scripts/catalogue_review.py`. Auto-approval is planned, not built (D5) |
| 7 | Prerequisites on the course page, met or not | **Built, not deployed** (D12). Also warns when adding a future course |
| 8 | UBC's permission, then a bulk import | Request drafted (`Ideas/overhaul/calender-request.md`); waits on UBC |
| **B** | **The rest of the vision's Phase 2** | **Listed, not drafted** |
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

## Part B: the rest of Phase 2 (listed, to be drafted)

Each needs the full template treatment (facts to settle, "Done when", trust
cost) before its work starts. Their vision text is §4 Phase 2. Noted now,
because it shapes the draft:
- **Item 9 is the sharpest isolation case in the plan** (§5.6): write access to
  another user's row, through a membership table whose membership only the
  owner can change. It reuses nothing from Part A's read-only policy except the
  habit of proving it on Postgres.
- **Item 12 does not ship before the rate limiter is fixed,** which means
  trusting one specific forwarded position from Cloud Run, never a raw
  `X-Forwarded-For`.
- **Item 13's collection path ships here** so Phase 3 has something to
  aggregate. That aggregate is a job-written table, the §5.6 rule.

## Open questions

All five from the first draft are answered (D1, D5–D7, and the calendar
request). None are open for Part A.

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
