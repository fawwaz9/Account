# Phase 3 — Density pays

Written for: you, deciding the plan before any of it is built.

Taken from `account-vision.md` §4 (Phase 3), the Phase 3 roadmap table, and §11.
Brought up to date on 2026-10-12 against the code on `main` (`d638bcf`).
Follows `Ideas/overhaul/template.md`.

**Opened early, by your call (D1).** Phase 2's exit criteria need real use:
five active teams, a partnership that lasts a month. They can't be met by
building. You chose to open Phase 3 with the one item that needs no other
users, the job application tracker, and leave Phase 2 open for its usage
criteria.

- **Part A, the job application tracker,** is planned in full below (item 1).
- **Part B, the density features** (items 2–13), was drafted and built on
  2026-10-28 (D10–D13), **not yet deployed**: Batch 3 in the runbook. Most of
  it shows nothing until enough people contribute, by design.

## What Phase 3 is for

The vision: "Nothing here is new infrastructure; it is the moment the Phase 1
pipelines and the Phase 2 user base meet. Every item was impossible earlier for
lack of people, not lack of code."

The tracker is the exception, and the vision says so: **private and
single-user**, so it needs no density and "can ship as soon as the phase
opens".

The rules that apply directly:
- **Data safety first.** No request reads another user's rows (§5.6). Shared
  figures are written by a job, never by a request.
- **Below a cohort floor, an aggregate is a disclosure.** Nothing renders under
  it (§4: "an average is a disclosure wearing an aggregate's clothes").
- **Individual grades are never shared,** not between friends, not opt-in, not
  at all.
- **Your own version always wins for you** (§13.19).
- **Never launch a directory empty** (§4).

## Exit criteria: Phase 3 → Phase 4

From §11, unchanged:
- [ ] at least one course where one student's verified parse served another
- [ ] distributions rendering above the cohort floor in more than one course
- [ ] a leaderboard running a full term without a gaming dispute
- [ ] the shared merchant map lifting first-import categorization above 60%

**Which of these can be read today:** none. Each needs contributors. The
tracker is not on the list: it is a single-user feature riding in this phase
because the vision put it here, and it has its own "Done when".

## Status at a glance (2026-10-28)

Every item is built. Items 2–13 wait on Batch 3's schema step and deploy, and
then on contributors (D11's floors).

| # | Item | Status |
|---|---|---|
| 1 | Job application tracker | **Deployed 2026-10-13** (`72bb9f2`), with D2–D6; seasons (D7) 2026-10-14 (`e5d5eb6`) |
| 2 | Shared syllabi | **Built** (`e24b42b`): offered outlines, your review script, "Use it" on an empty course |
| 3 | Grade distributions shown | **Built** (`c501b90`): closed terms above the floor on the course page |
| 4 | Shared merchant map | **Built** (`b100c82`): a layer after your own history, 3 people agreeing |
| 5 | Crowdsourced course intel | **Built** (`79d0c91`): hours, difficulty, clarity and "take again" per figure above the floor |
| 6 | Exertion score | **Built** (`1584637`), manual entries. Strava and Fitbit wait on your app registrations |
| 7 | Adaptive exertion goals | **Built** (`1584637`): last 4 weeks plus 10%, eased in exam weeks |
| 8 | Campus leaderboards | **Built** (`294301a`): team board (opt-in), campus board of listed teams. A city board waits for a second campus |
| 9 | Open league directory | **Built** (`294301a`): opens at 5 listed teams; ask to join |
| 10 | Club management | **Built** (`06c6726`): members by link, posts, polls, calendar events |
| 11 | Office-hours radar | **Built** (`4acc31e`): three taps, slots above the floor |
| 12 | Co-op salary transparency | **Built** (`a479d50`): verified, published in batches of 5 |
| 13 | Gym buddy, scoped | **Built** (`c16c14a`): partners and teammates only |

---

## Part A: the job application tracker

### 1. Job application tracker

**What** (Phase 3 roadmap table, added by you 2026-10-11). Under Jobs. Every
application you send: the company, the role, when you applied and where you
found it. Its status as it moves from applied to screening, interview rounds,
then offer, rejection, no reply or withdrawn, with deadlines and follow-ups.
Dashboards of your own progress:
- how many get a reply
- how long replies take
- the applications → interviews → offers flow, drawn as a Sankey diagram, the
  chart students share at the end of a recruiting season

**Where** (yours, 2026-10-12): its own page under Jobs. An "Applications" tab
on the Jobs page opens it; the Jobs page itself is unchanged.

**What exists.**
- Nothing for applications. The Jobs module is about jobs you have.
- Charts are hand-drawn SVG (`features/budget/components/*Chart*`); there is no
  chart library, and none is needed for one Sankey.
- Row security classifies new tables from the metadata. A per-user table and a
  child of it are both existing kinds, so **the isolation boundary does not
  move**.
- The isolation, non-interference and RLS walks take new routes through
  `PATH_SOURCES`, `BODY_PATCHES` and `DOMAIN_404`.

**The shape I'd build** (for you to change):
- `job_applications` (per-user): company, role, applied on, source (where you
  found it), link, location, notes, current status, deadline, follow-up date,
  created and updated times.
- `application_steps` (child of an application): each status change with its
  date. **The history is the point.** The Sankey and "how long replies take"
  are both read from it, so a status is never just overwritten.
- Statuses: applied, screening, interview (each round a step), offer, accepted,
  rejected, no reply, withdrawn.
- Figures computed on the server (`compute on the server, render on the
  client`): counts per stage, reply rate, median days to first reply, and the
  Sankey's flows.

**Facts to settle** (yours; asked alongside this draft):
1. Is the status list right, and is "accepted" its own step after "offer"?
2. Is "no reply" something you mark, or shown automatically after a quiet
   stretch?
3. Do deadlines and follow-ups reach the calendar or Tasks, or stay on the
   tracker's page?
4. Is a pay figure on an offer worth recording now? Private to you, and later the
   opt-in way into co-op salary transparency (item 12).

**Trust cost:** none shared. It is single-user, and nothing leaves your rows.

**Done when:**
- you can add an application, move it through its statuses, and see its history
- the page shows the counts, reply rate and days to reply from your own data,
  and the Sankey drawn from the history
- both tables are in the isolation, non-interference and RLS walks, on SQLite
  and Postgres
- it is live, with the schema step yours

---

## Part B: the density features (drafted 2026-10-28, D10–D13)

You asked for every buildable item in one push (D10). Each is built on
`phase3` with its tests and a decision entry, and **nothing is deployed** until
you say so: every item has a schema step, which is yours. What no build can do:
the exit criteria need real contributors, and Strava and Fitbit need app
registrations only you can make.

### The shared-aggregate kind (D11), decided once for items 3, 4, 5, 8, 11 and 12

Phase 2 has tables everyone reads (the catalogue) and a table nobody reads
(grade counts). Phase 3 needs **figures everyone reads, but only above a
floor**. The rule:

- **Written by the daily recount, never by a request.** Each aggregate is a
  sealed table (the existing kind), rebuilt whole by a definer function that
  the one scheduler route runs. Nothing below its floor is written at all.
- **Read only through a definer function** that takes a key (a course, an
  employer) and re-checks the floor. No route can read the table itself.
- **No user id, and nothing per contribution,** in any aggregate. A test
  checks every aggregate table's columns.
- **Floors (yours):** 5 people for anything about people (grades, course
  answers, office hours, pay, campus standings); 3 people for a merchant's
  category, which says nothing about anyone.
- **A figure never moves in step with one person's answer.** Grades and course
  answers count only once their term's asking window has closed (180 days after
  the term ends), and pay is published only in whole batches of 5. Phase 2 D25
  left this question open.
- **Below the floor, the page says what it's waiting for** ("Shown once 5
  students have shared"), never a partial figure.

### 2. Shared syllabi
**What:** the second student in a course inherits a reviewed outline: its
categories, weights and assessments, with due dates, and no scores, notes or
syllabus wording.
**Verified (D12, yours):** the student offers their course's outline from the
course page, and you approve it with `scripts/outline_review.py`, the way
catalogue proposals are approved. An approved outline is world knowledge in a
shared-read table, keyed by course and term. The next student adding that
course is offered "Use the reviewed outline", and can change anything after.
**Done when:** an offered outline you approve fills a second student's empty
course; an unapproved one reaches nobody; the walks cover the new tables.

### 3. Grade distributions, shown
**What:** on the course page, "How past classes did": each closed term's
5-point bands, its median band, and where your own grade sits.
**Exists:** collection and the sealed counts (Phase 2 D25).
**New:** a read function, `account_grade_distribution(course key)`, answering
only terms at or above the floor whose asking window has closed.
**Done when:** a course-term above the floor renders; below it, nothing but
the waiting line; no route returns another course's counts.

### 4. Shared merchant map
**What:** a new user's first import comes back categorised: "STARBUCKS →
Coffee", because enough others filed it there.
**How:** each person's most-used category name for a merchant is one vote. A
merchant enters the map when 3 or more people agree, and that name holds at
least 75% of the votes, so contested merchants (Costco) stay out. Transfers,
e-transfers and payments are never merchants. It sits after your own history
and before the curated list: **your own version always wins.** It only
suggests a category you have, by name.
**Your switch:** Settings → Finances, "Help categorise others' imports", on by
default (D11 explains why; yours to flip).

### 5. Crowdsourced course intel
**What:** "Students say about 9 hours a week · difficulty 3.6/5 · clarity
4.1/5 · 70% would take it again," on the course page, from term reviews.
**How:** pooled across a course's closed terms. Each figure shows only when 5
or more people answered that question, so a rating 2 people gave is never
shown.

### 6–7. Exertion score and adaptive goals
**What:** log an activity (kind, minutes) and it earns points = hours × MET ×
corroboration weight, with the formula version stored on each row and never
rewritten. A manual entry weighs 1.0 today; device sources get their weights
when Strava or Fitbit are connected (left for your app registrations).
**Goal:** a suggested weekly target from your last 4 weeks plus 10%, with a
dip to 70% in a week holding exams, always shown as advice beside the goal
you set, never imposed.

### 8. Leaderboards
**Team board:** this week's points for teammates who opted in, seen only by
teammates who opted in too. **Campus board:** teams ranked by their opted-in
members' points, for teams whose captain listed them, shown only once 5 teams
are on it. Individuals never appear on the campus board, only team names, so
it introduces nobody to anybody. A city board waits for a second campus.

### 9. Open league directory
**What:** captains can list their team (sport, level, area, "looking for
players", a line about it). Listed teams are browsable and filterable, and
greyed after 30 days without a game. "Ask to join" sends the captain your name
and a short message; they accept or decline.
**Never launch empty:** the directory shows nothing until 5 teams are listed.
**Anti-spam:** one pending request per team, five pending at most, 200
characters.

### 10. Club management
**What:** a club with members (joined by link, like teams), polls with one vote
each, announcements, and club events that appear on every member's calendar.
Only the club's owner posts, runs polls and adds events. Members see names,
never other members' ids.

### 11. Office-hours radar
**What:** "At office hours now? How's the line?" on the course page: three
taps (no line, short, long). Each course shows its busy slots: "Tue 2pm:
usually a long line". The value exchange is stated beside the buttons.
**How:** a slot (weekday and hour) shows once 5 people have checked in there in
the last 120 days.

### 12. Co-op salary transparency
**What:** on an offer in the tracker, "Share this offer's pay anonymously",
off unless you turn it on. Jobs → Applications shows each employer's typical
hourly pay (median and middle half) once 5 verified people have shared.
**Verified (D12):** the offer matches a job you have recorded at that employer,
within 5%; or 5 or more shares for the employer agree within 10%. Unverified
shares never count. **No pay stub or T4 is read.** Published only in whole
batches of 5, so one new share can't be picked out of the change.

### 13. Gym buddy
**What:** "I'm looking for someone to train with", with times and a note.
You see which of your partners and teammates are also looking, and only while
you're visible yourself. No stranger is ever shown.

## Suggested order (as built, D10)

Safety first, then the figures, then the people features:
1. **D11's kind**, proven with item 3 on the counts already being collected.
2. **Items 5, 11, 12 and 4**, the other aggregates.
3. **Item 2**, the shared outlines and your review script.
4. **Item 13, then 6–8,** on connections that already exist.
5. **Items 9–10**, the directory and clubs.

## Open questions

- Strava and Fitbit: which first, once you register the apps.
- The merchant switch's default (on, D11).

## What the vision says that has since moved

- The tracker was added to Phase 3 by you on 2026-10-11 (`next.md`), and the
  vision already says so.
- Grade distribution **collection** moved to Phase 2 and is live. Only the
  **display** is Phase 3's.
- The daily recount job, listed as optional in Phase 2's runbook, has been live
  since 2026-10-12.
