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
- **Part B, the density features** (items 2–13), is listed and checked against
  the code, but not drafted in detail. Each needs contributors before it can
  show anything, and gets the full draft before its work starts.

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

## Status at a glance (2026-10-12)

| # | Item | Status |
|---|---|---|
| 1 | Job application tracker | **Planned below.** Facts to settle are yours |
| 2 | Shared syllabi | Pipeline built (Phase 1 D16); catalogue built (Phase 2 Part A). Waits on cohorts |
| 3 | Grade distributions shown | Collection live (Phase 2 item 13), recount job live since 2026-10-12. Waits on 5+ contributors per course-term |
| 4 | Shared merchant map | Personal categorizer built (Phase 1 D17). Shared layer not started |
| 5 | Crowdsourced course intel | Collection live (term reviews' hours, difficulty, clarity). Display not started |
| 6 | Exertion score and fitness integrations | Not started. Teams live under Fitness |
| 7 | Adaptive exertion goals | Not started; needs item 6 |
| 8 | Campus and city leaderboards | Not started |
| 9 | Open league directory | Not started; never launch empty |
| 10 | Club management | Not started |
| 11 | Office-hours radar | Not started |
| 12 | Co-op salary transparency | Not started; item 1's offers are its natural way in |
| 13 | Gym buddy, scoped | Not started |

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

## Part B: the density features (listed, not yet drafted)

Each of these waits on contributors. The shared ones also move the isolation
boundary in a new way: Phase 2 has tables everyone reads (the catalogue) and a
table nobody reads (grade counts). Phase 3 needs **aggregates everyone reads,
but only above a floor**. That is a new kind, to be settled once for items 2–5,
8 and 11–12:

- **A shared aggregate is written by a job, read through a definer function, and
  answers nothing below its floor.** The sealed `grade_distributions` table and
  its daily recount are the start. Its read path, a function returning a
  course-term's buckets only at 5 or more contributors, is item 3's first step.
- **Each floor is a decision, per feature,** with the re-identification risk
  named. Five contributors is the grade floor today (`COHORT_FLOOR`).

### 2. Shared syllabi switched on
The second student in a course inherits a verified parse. **Exists:** the
syllabus pipeline (Phase 1 D16, D27), the catalogue (Phase 2 Part A).
**To settle:** what "verified" means, and who verifies.

### 3. Grade distributions, shown
"You are at 74%, the class median is 81%", above the floor only. **Exists:**
collection (Phase 2 item 13, D25), the sealed table, and the daily recount (live
2026-10-12). **To settle:** the read function, and how the floor is shown when
it isn't met.

### 4. Shared merchant map
The world-knowledge half of categorization: a new user's first import from 25%
to 80% categorized. **Exists:** the personal three-layer categorizer (Phase 1
D17). **To settle:** a confirmation floor, and that a merchant name never
carries a person with it.

### 5. Crowdsourced course intel
"Students say 20 hours a week." **Exists:** the term reviews collect hours,
difficulty, clarity and would-take-again. **To settle:** the floor, and which
figures to show.

### 6–7. Exertion score, fitness integrations, adaptive goals
Points = duration × MET × corroboration weight, the formula versioned and never
rewritten. Strava or Fitbit, else manual. **To settle:** the OAuth providers,
token storage, and that this is the most maintenance-heavy item in the vision.

### 8. Campus and city leaderboards
Team → league → campus → city. Opt-in, precomputed. **Waits on** item 6.

### 9–10. Open league directory, club management
**Never launch empty.** **Waits on** enough teams (Phase 2's criterion).

### 11. Office-hours radar
Self-reported check-ins, aggregates only.

### 12. Co-op salary transparency
Anonymous offers with explicit consent, verified by matching a payroll record or
converging submissions. Unverified offers never aggregate. **Item 1 is its way
in:** an offer recorded in the tracker is the one a student can choose to
submit.

### 13. Gym buddy
Only within existing connections. No stranger discovery.

---

## Suggested order

1. **The tracker (item 1).** No density needed, so it can ship now. Its offers
   feed item 12 later.
2. **The shared-aggregate kind**, decided once, with item 3's read function as
   its first use. It's the smallest step that proves the new boundary, on data
   already being collected.
3. **Items 3 and 5**, rendering as soon as any course-term clears the floor.
4. **Items 2 and 4**, once cohorts exist. Each lifts a new user's first week.
5. **Items 6–13**, once Phase 2's teams exist. They need people to compete
   with.

## Open questions

- The tracker's four facts above.
- Whether Part B is drafted in full now, or item by item as each one's
  contributors appear. I'd go item by item.

## What the vision says that has since moved

- The tracker was added to Phase 3 by you on 2026-10-11 (`next.md`), and the
  vision already says so.
- Grade distribution **collection** moved to Phase 2 and is live. Only the
  **display** is Phase 3's.
- The daily recount job, listed as optional in Phase 2's runbook, has been live
  since 2026-10-12.
