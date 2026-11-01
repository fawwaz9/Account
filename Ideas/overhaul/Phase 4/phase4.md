# Phase 4 — Smart (history pays)

Written for: you, reviewing the plan and where each item stands.

Taken from `account-vision.md` §4 (Phase 4), §11, §13.5, §13.6, §13.12, §13.19
and the ledger (§15), brought up to date on 2026-10-31 against the code on
`phase4` (branched from `phase3` at `43d4868`). Follows
`Ideas/overhaul/template.md`.

**Opened while Phase 3 stays open (D1).** Phase 3's items are all built and live;
its exit criteria need contributors, and Strava and Fitbit need your app
registrations. Neither can be built.

**Scope (D2):** everything in the vision's Phase 4 except Plaid.

**Deploys (D3):** frontend freely; backend with no new table or column once
every check passes, through `ship`; anything with a schema change waits for your
schema step.

## What Phase 4 is for

The vision: "The coach. Everything here needs *time* rather than people — a term
of personal history, and in several cases data from all three rooms."

The rules that apply directly:
- **Deterministic first (§3.4).** Every item here is arithmetic over data already
  stored. No item calls an LLM.
- **The financial silo (§13.3, §13.5).** Every module is a sensor for money;
  money is never a sensor for anything else. Correlations exclude money
  entirely. Money simulators never project grades. In the term simulator the work
  slider reports time fit only, and grade bands come only from study hours you set
  directly.
- **Simulators show their assumptions and cap absurd inputs (§13.6).** Frame
  around agency, not anxiety.
- **Cold starts stay silent (§13.5).** A wrong prediction early is worse than
  none: deadline risk and the spending guard say nothing until there is enough
  history, and say what they're waiting for.
- **Course-drop is information with disclaimers, never advice (§15).**
- **Data safety first.** No request reads another user's rows; every new table
  joins the isolation walks.

## Exit criteria

From §11: "Phase 4 — ongoing, not a gate."
- [ ] the planner used for ≥50% of study blocks
- [ ] risk flags acted on rather than dismissed
- [ ] term-simulator calibration improving across two terms

**Which of these can be read today:** none. Each needs a term of use after the
item ships, and the first two need the app to record what came from the planner
and what happened to a flag (see items 2 and 3).

## Status at a glance (2026-10-31)

| # | Item | Schema? | Status |
|---|---|---|---|
| 1 | Cumulative average and CGPA including this term | No | **Deployed 2026-10-31** (`863cfcf`, `account-api-00050-fqt`; D5, D6) |
| 2 | Weekly planner | **Yes** (D7) | Planned |
| 3 | Deadline risk | No | **Built** (D11) |
| 4 | Focus sessions | **Yes** | Planned |
| 5 | Exam countdown | No | Planned |
| 6 | Briefings | No | Planned |
| 7 | BYOAI briefing API and MCP | **Yes** | Planned |
| 8 | Cross-room correlations, non-financial | No | Planned |
| 9 | Term simulator | No | Planned |
| 10 | Grade scenarios | No | **Built** (D10) |
| 11 | Course-drop simulator | No | Planned |
| 12 | Next-term planner | No | Planned |
| 13 | Deadline spending guard | Partly | Planned |
| 14 | Money what-if | No | Planned |
| 15 | Self-employed support | **Yes** | Planned |
| — | Plaid | — | Out of scope (D2) |

---

## Cross-cutting facts to settle before building

1. **One simulator pattern (§13.6).** Model + inputs + baseline-vs-scenario. On
   the server, each simulator is a pure function of the stored data and a
   scenario body, posted and answered, never saved. Saved, named scenarios are
   left for later: they would need a table each, and nothing yet says which
   scenarios people come back to.
2. **The digest is one function.** Briefings (item 6), the BYOAI endpoint and
   the MCP server (item 7) all read the same deterministic digest, so the three
   can never disagree. It carries no money figures unless you decide otherwise
   (question 2 below), because it leaves the app through your own assistant.
3. **What needs a schema step.** The planner's `events.source` (D7), focus
   sessions (a table of sessions), BYOAI (a
   table of hashed tokens), the spending guard's pre-allocation and report card
   (a per-week override), and self-employed support (clients and invoices). Each
   is built and tested on `phase4`, its runbook step written, and it deploys
   after your schema step. Everything else is computed on read.
4. **History windows.** Velocity, correlations and spike prediction read a
   trailing window and say how much history stood behind each figure.

---

## 1. Cumulative average and CGPA including this term

**What** (Phase 4, added by you 2026-10-28). A second, clearly labelled pair
beside the official one, counting each current course at its running average.
**Deployed 2026-10-31** (`863cfcf`, D5, D6). **Done when:** live, which is a D3 deploy. ✓

## 2. Weekly planner

**What** (§4). Constraint scheduling over free blocks: tasks sorted by due date
and priority, filled greedily, each choice explained ("Thursday, because Friday
is full"). **What exists:** `load_service.free_blocks` (gaps clipped to the study
window, longest first), tasks with `estimated_minutes`, `actual_minutes`,
`priority` (1–5), `due_date` and `course_id`, and the estimate ratio
(`estimates_service`). Events have no "study" kind and no field saying where
they came from.

**Facts to settle:**
- A proposal is computed on read; accepting it writes ordinary calendar events
  through the existing event service. Nothing new is stored.
- **Measuring "planner used for ≥50% of study blocks"** needs to know which
  events the planner made: `events.source = 'planner'` (D7, a schema step), so
  the planner lands with the schema items.
- Tasks without an estimate get a default block (the user's minimum free-block
  length), said in the explanation.

**Done when:** a week's plan places every placeable task before its due date,
says why for each, never double-books, never schedules outside the study window,
and lists what didn't fit; accepted blocks appear on the calendar.

## 3. Deadline risk

**What** (§4). Personal velocity against required velocity. Division, not
machine learning. **What exists:** completed tasks with `actual_minutes` and
`completed_at`; open tasks with estimates and due dates; free blocks.

**Facts to settle:**
- **Velocity** = actual minutes completed per day over the last 28 days (falling
  back to estimates done when actuals are missing). **Required** = estimated
  minutes still open before a deadline ÷ days left, scaled by the estimate ratio
  when you've turned it on.
- **Cold start:** silent until 14 days of completed work exist, and it says so.
- **"Acted on rather than dismissed"** can't be read without recording dismissals
  (a schema step). The first version shows the flag and records nothing; the
  criterion stays unreadable until a later step adds it.

**Done when:** each at-risk deadline shows the two rates and the shortfall in
hours, silent under the cold start, with tests on the arithmetic and the floor.

## 4. Focus sessions (schema)

**What** (§4, §16). A timer tagged per course, building the hours-studied-vs-grade
chart. **What exists:** the task timer accumulates into `tasks.actual_minutes`;
there is no record of individual sessions, so neither "per course per week" nor
the chart can be read from it. **Needs a table:** `focus_sessions` (per user:
course, started, ended, minutes). **Trust cost:** none shared.

**Done when:** a session can be started and stopped on a course, the hours per
course per week show, and the hours-vs-grade chart draws from your own courses;
the table is in every isolation walk; live after your schema step.

## 5. Exam countdown

**What** (§4, §16). Inside 7 days of an exam, re-prioritize around it.
Presentation logic over existing data. **What exists:** midterm and final events,
the exam strip on the dashboard, tasks linked to courses.

**Done when:** inside 7 days, the exam's course work rises to the top of Tasks
and the dashboard, with the days left, and nothing changes outside the window.

## 6. Briefings

**What** (§4). A proactive, deterministic digest on the Phase 0 scheduler.
**What exists:** `push_service.dispatch_due_reminders`, called by the scheduler
every 5 minutes at `/api/internal/reminders/dispatch`, acting as each user in
turn; `users.preferences` (JSON).

**Facts to settle:**
- **The digest:** today's events and exams, tasks due today and overdue, at-risk
  deadlines, the week's load, exam countdowns. No money (cross-cutting fact 2).
- **In-app first:** a "Today" card. **Push:** opt-in in Settings, at an hour you
  pick, sent by the existing dispatch run, so no new scheduler job. Stopping a
  second push the same day needs somewhere to remember the day it was sent;
  `users.preferences` can hold it without a schema step.

**Done when:** the card shows the digest; with push on, one briefing arrives per
day at the chosen hour, and none with it off.

## 7. BYOAI briefing API and MCP (schema)

**What** (§13.19). Serve the deterministic digest to your own assistant, at zero
AI cost to us. **Your rules (D4):** off by default; one revocable, read-only
token stored hashed, reading only the digest; a plain API endpoint and a small
MCP server over the same digest.

**Facts to settle:**
- **A table:** `assistant_tokens` (per user: the token's hash, a prefix to
  recognise it by, created, last used). The token is a new kind of credential,
  so this touches the isolation boundary: the endpoint must resolve the token to
  one user and read nothing else.
- **The MCP server** is a route in the API (stateless HTTP, JSON-RPC), so it
  needs no new service to run. It offers one tool, the digest.

**Done when:** a token can be made (shown once), used against the endpoint and
the MCP route to read only the caller's digest, and revoked, after which it is
refused at once; a session token is refused at the token routes and the token at
every other route; mutation-tested; live after your schema step.

## 8. Cross-room correlations, non-financial

**What** (§4). Academic against body; no money in any form. **What exists:**
exertion points per day (`exertion_service._totals`), tasks completed per day,
marks with dates.

**Facts to settle:** weekly pairs (exertion points vs tasks completed, vs marks
earned that week), shown only with at least 8 weeks of both, with the number of
weeks and the correlation in words ("weak", "moderate"), never as cause.

**Done when:** the card shows each pair's strength and sample size above the
floor, nothing below it, and no query in it touches a money table (a test reads
the tables it touches).

## 9. Term simulator

**What** (§13.19). The capstone: the three rooms' projections over one 168-hour
week. **What exists:** the workload model (`week_load`), the year plan
(`plan_service`), the exertion goal.

**The rule that does not bend:** the work slider reports time fit only ("182 of
your 168 hours, 14 short"). Grade bands render only from study hours you set
directly. **Facts to settle:** what each room's projection is, in the simulator's
terms; the calibration loop (§13.13) needs stored simulations, so it waits.

**Done when:** sliders for courses, work, workouts, sleep and study give the
time fit with the overage per room, the money curve from the plan, and the
exertion trajectory; a test proves no grade figure moves with the work slider.

## 10. Grade scenarios

**What** (§13.6). Sliders on each remaining assessment with a live projected
grade. **What exists:** `grade_service.project_course(course, unmarked,
overrides)` and the required-final modal.

**Done when:** each unmarked assessment takes a score, the projected grade
follows, and it matches `project_course` exactly.

## 11. Course-drop simulator

**What** (§13.6). "Drop CPSC 320 → average and credits before and after,
tuition refund estimate", with the full-time warning. **What exists:** the
dashboard figures, `tuition_service.course_cost`. **Settled:** the full-time
warning starts below 9 credits a term, an editable default (D9); the refund is
an estimate only.

**Done when:** before and after figures, the credit change, a refund estimate
with its basis, and the full-time warning with loans, housing and immigration
named; information with disclaimers, never advice.

## 12. Next-term planner

**What** (§13.6). Pick candidate courses → projected weekly hours from past
students' figures above the floor → "this combination averages 42 hours a week".
Deep-link to RateMyProfessors by URL; never scrape. **What exists:**
`aggregates.course_intel` behind the floor (D11 of Phase 3), the catalogue.

**Done when:** a set of catalogue courses shows the summed hours and difficulty
from figures above the floor, says which courses have none, and links out.

## 13. Deadline spending guard (partly schema)

**What** (§13.5). Crunch detection → personal spike prediction → pre-allocation
→ report card. Silent until two crunch weeks of history.

**Facts to settle:** the detection and the prediction are computed on read
(`crunch`, transactions by category). The pre-allocation is "a per-week override
of the category limit", which needs a table, and the report card reads it, so
those two wait for your schema step. Anti-annoyance (one per crunch week; three
dismissals stop a category) needs its dismissals remembered.

**Done when:** before a crunch week with enough history, the money room says
which categories rise and by how much; after your schema step, a pre-allocation
can be set and the report card follows the week.

## 14. Money what-if

**What** (§13.5). The year plan re-run with modified inputs: hours, spending,
wage, one-time purchases, "exam season mode". **What exists:** `plan_service.plan`
and `solve`.

**Done when:** baseline and scenario curves overlaid with end balance, lowest
point and runway, every assumption listed, absurd inputs capped; no academic
figure anywhere in it.

## 15. Self-employed support (schema)

**What** (§13.12). Clients and invoices with paid and overdue states; the $3,000
net-tax installment threshold, the CPP double rate, CRA installment dates, the
$30,000 GST/HST watch; business-expense tags; a trailing-income range for the
planner. Tax information, never advice. **Needs tables:** clients, invoices, and
a way to tag a transaction as a business expense.

**Done when:** invoices move through their states, the thresholds watch real
totals with their sources cited, and the tables are in every isolation walk;
live after your schema step.

---

## Suggested order

1. **CGPA** (built): no schema, no history.
2. **The schema-free coach:** grade scenarios, deadline risk, exam countdown,
   the digest and its Today card. Each one ships under D3.
3. **The schema-free simulators:** course-drop, next-term, money what-if, term
   simulator, correlations, the spending guard's detection.
4. **The schema items, safety first:** BYOAI (a new credential, so it goes first
   and gets the hardest tests), then the planner (D7), focus sessions, the
   guard's pre-allocation, self-employed. All built and tested on `phase4`; one schema step for you; one
   deploy.

The trade: the schema-free items go live as they're done; the schema items wait
for you and land together, so you run one schema step rather than four.

## Open questions

None open. Answered 2026-10-31: the planner's events carry a column (D7), the
digest carries no money (D8), the course-drop warning starts below 9 credits
(D9).

## What the vision says that has since moved

- **Focus sessions** were costed as needing no schema (§15). The task timer keeps
  only a running total, so sessions per course need their own table.
- **The term simulator's calibration loop** needs stored simulations; it waits
  for a term of use and its own table.
- **Plaid** is out of this phase by your call (D2), not merely sequenced last.
