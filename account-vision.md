# Account — Product Vision

*Last updated: 2026-10-05. Living document — update as decisions are made.*

## 1. Vision

Account is a **student universe**: one place that holds the parts of a student's life
that currently live in Canvas, PrairieLearn, Gradescope, a syllabus PDF, a bank app,
a payslip, a group chat and a rec-league spreadsheet.

**Why a universe rather than a tracker with features bolted on.** Super-apps work in
bounded communities with a shared identity, and a campus is exactly that. A student
does not think of themselves as "a person with grades" or "a person with a budget" —
they think *UBC student*, and an app shaped like the identity rather than the task is
coherent in a way a to-do list is not. The compounding happens at the level of
**attention**: if the app is already where you are several times a day, the next room
costs nothing to enter.

**Three rooms, in the order they currently exist:**

1. **Academic** — courses, grades, deadlines, exams, workload.
2. **Money** — accounts, budgets, savings goals, income from shifts, net worth.
   Already the largest part of the product by route count, and the half a student
   feels weekly rather than at term boundaries.
3. **Body** — physical exertion as a single score, and the sport that feeds it.
   Not started.

**The integration is the moat, not any single room.** Nobody else holds grades, money,
shifts and sport for the same person. Features that need history — velocity, personal
multipliers, cross-room correlations — get better the longer a student stays, and cannot
be copied on day one by anyone who starts today.

**One deliberate limit on that claim.** The financial silo (§13.3) excludes money from
every cross-room correlation and peer comparison, so the correlation half of the moat is
academic-against-body only. What money contributes instead is *attention* — a room the
student is in weekly — and one-way integration *into* money (§13.5), where the calendar
and jobs feed the forecast and nothing financial flows back out. The moat is the shared
academic layer plus attention across rooms, not a correlation engine over everything.

**The test that keeps this honest.** "It all belongs together" can justify building
anything, which is exactly how scope creep disguises itself as strategy (§9.8). So the
thesis is falsifiable: it is **true if one person visits two different rooms in one
week, with at least one visit unprompted** — "two reasons" passes trivially (a grade
check and a task check are two reasons inside one room), and notification-driven
visits don't count, or the metric manufactures itself — and it is a rationalisation
if every room has its own three users and nobody crosses between them. (Tightened
2026-10-02, §13.2.) That is measurable the moment
analytics exist, and it is a better gate than per-feature retention — for a universe
the metric is *rooms visited per week*, not completion rate in one of them.

**On friction.** The aspiration is zero-friction data in, insight out. Today every
byte in the system was typed by a user, and the largest room is hand-entered in a
category with large incumbents. Shared syllabi (§4, Phase 1) is the first feature that
makes the principle literally true rather than aspirational: for every student after
the first in a course, the data genuinely does arrive on its own.

## 2. Current State (measured 2026-10-02)

### Deployment
- **Backend:** Python/FastAPI on Google Cloud Run (`us-west1`), one container image
  per commit, traffic pinned to the latest revision.
- **Frontend:** React + TypeScript + Vite on Cloudflare Pages, built from `main`.
  Ten pages: Dashboard, Login, Budget, Account detail, Calendar, Grades, Course
  detail, Jobs, Tasks, Settings.
- **Database:** Supabase Postgres 17.6 (`us-west-2`). 26 tables in the schema module;
  27 live, the extra being an orphan left by a rollback (§9.10).
- **Ops:** a GitHub Actions database backup, a written rollback runbook with per-image
  notes, an invite-only signup allowlist checked on both the password and Google
  paths, and a deploy order — backup → schema → API → frontend — that is followed
  rather than assumed.

### Scale
- **139 API routes:** Finances 48, Tasks 24, Grades 21, Jobs 17, Calendar 16, Users 7,
  Auth 4, Omnibox 2.
- **1,036 backend tests and 226 frontend tests.** The backend suite passes against
  Postgres as well as SQLite, so the deployment target is exercised rather than
  assumed. Cross-user isolation is checked throughout: 18 test files create a second
  user and assert the first cannot reach their rows.
- **6 user rows, 1 soft-deleted — 5 active.** 5 addresses on the signup allowlist.
  Two of those appear to belong to the builder, so the beta is realistically three
  other people (§12.8).
- **Live data,** read 2026-10-02 and moving daily: 31 courses, 209 grades, 87 tasks,
  54 events, 182 transactions, 11 standing category limits, 11 recurring
  transactions, 4 paycheques.

### Academic
- **Grades (21 routes).** Courses with code, name, term, year, credits, professor,
  required/elective, transfer credit and a no-final flag. Per-course categories with
  weights, a running average, and a target grade. Derived views: **required final**
  ("what you need on the final to hit your target"), **cheapest path**, **grade band**
  and **category blind spots**. Course search and resolution, a grades dashboard, and
  bulk grade entry.
- **Calendar (16 routes).** Events with a kind — lecture, lab, discussion, midterm,
  final, deadline, personal, shift — and a recurrence rule stored as a rule rather
  than materialised rows, with per-occurrence skips. A per-course class schedule, an
  agenda, term blackouts, and a load model: **free blocks** against the student's
  study window, a per-week **week-load** figure and a term **crunch** strip. Deleted
  events can be restored.
- **Tasks (24 routes).** Due date and time, per-task time estimate, priority, tags,
  optional links to a course or a specific grade, recurrence with skip and catch-up,
  snoozing with history, and **completion timing** — how early or late work actually
  gets finished, measured on the student's own clock.
- **Exams** are events of kind `midterm` or `final` rather than a separate module, and
  surface as a countdown strip on the Tasks page.

### Money
- **Finances (48 routes).** Accounts of several kinds with a signed transaction
  ledger; transfers as paired rows that net to zero. Spend categories, a budget
  summary, per-account monthly **budget targets**, and per-account **category limits**
  with per-month overrides. **Sinking funds** with contributions, **safe-to-spend**, a
  **subscription audit** that proposes recurring charges from the ledger for
  confirmation, standing **recurring transactions** with an upcoming view and a
  catch-up run, **income deposits** split across accounts with a preview, **net
  worth**, a **term budget**, **tuition** payments with per-course cost, and monthly
  **investment-return** readings showing what a holding is worth over what was paid in.
- **Jobs (17 routes).** Jobs with a pay schedule expressed as a recurrence rule, shift
  records, **paycheques** with deductions and a preview, and an earnings summary with
  projected next pay.

### Cross-cutting
- **Auth (4 routes).** Google sign-in and password sign-in, registration behind the
  allowlist, and setting a password on an account created through Google.
- **Users (7 routes).** Profile, preferences, academic status (which term you are in,
  which drives past/current/future across the grades page), and account deletion with
  a restore window.
- **Omnibox (2 routes).** A single text field that parses a typed line into a task,
  event or transaction — course code, date, duration, amount and score are all
  recognised — with a preview before it commits.
- **Settings.** Tabbed sections (Academic, Calendar, Financial), a timezone
  preference, blocked periods, income split and category editing.
- **A shared timezone-aware clock.** Every "today" resolves through the student's
  timezone preference rather than the server's, which on Cloud Run is UTC.

### Not built yet
- **Integrations.** No Canvas, PrairieLearn, Gradescope, Google Calendar, bank or
  fitness sync. A course carries links you paste — the schema describes it as *"one
  place a course lives: Canvas, Piazza, a syllabus"* — and nothing is fetched.
- **Push notifications and a scheduler.** Reminders are stored and served when the
  client asks for what is due, so one fires while the app is open and not before.
- **Anything social or shared.** No teams, no leagues, no shared courses, no
  distributions, no accountability partners, no leaderboards.
- **Exertion scoring, syllabus parsing, multiple grading schemes per course, streaks,
  a focus timer.**
- **Shared, multi-user entities.** All 26 tables are single-user: 19 carry `user_id`
  directly, six are children reached through a parent that does — grades through
  courses, snoozes through tasks, contributions through sinking funds, deductions
  through paycheques and tuition payments, category weights through courses — and
  `users` is the root.
- **Database-level isolation.** Enforced in application code today; see §5.6, and
  §4 Phase 0, where closing this is a hard gate.
- **Analytics.** No event capture, no product analytics, no retention measurement.
  Engagement figures are reachable by querying Postgres directly, which is how the
  numbers above were produced.
- **Per-user module toggles.** Features are not individually switchable, so the
  "modular, but measured" principle in §3.6 is currently an intention.

## 3. Strategic Principles

1. **Data safety outranks everything, at any cost.** The app holds grades, full
   financial ledgers and password hashes for real people, and the roadmap adds shared
   data on top. The worst failure is not a wrong figure on a screen but one student
   seeing another's grades or balances. When a plan trades safety for speed, the trade
   gets stated and priced, never taken quietly.
2. **Depth beats breadth.** Deepen the accountability moat before opening a new room.
   A student switches because their current system *can't* do something.
3. **Automatic over manual.** Prefer imports and shared data over typing. Manual
   logging must clear a high bar: an underserved niche plus a sub-30-second
   interaction. Finances does not currently clear it (§12.2).
4. **Deterministic core, LLM at the edges.** Scheduling, projections, risk scores and
   correlations are deterministic algorithms and basic statistics — testable,
   explainable, cheap. LLMs are reserved for unstructured understanding. This is the
   strongest principle here and the one the codebase follows: required final, cheapest
   path, free blocks and earnings projection are all arithmetic.
5. **Switching costs should work for us.** Features that need history get better the
   longer a student stays. None are built, so the moat is still hypothetical (§12.5).
6. **Modular, but measured.** Features should be optional per user, with adoption
   tracked and dead modules killed. Neither half exists yet, and §12.18 shows why it
   matters.
7. **Validate before building.** Interview the beta before any major feature: "what
   would make you delete your current system?" Build what repeats. At three outside
   users this is direction, not evidence (§12.8).

## 4. Feature Roadmap

**Restructured 2026-10-02 around growth rather than dependency.** The previous ordering
grouped features by subject — academic layer, coach, body room — which put the
network-effect features before the network existed and the only acquisition loop last.
Each phase below is named for what it changes about the business, and the arc is
**safe → sticky → spreadable → dense → smart.**

Two hard rules survive intact: nothing that shares data ships before isolation is
enforced by the database, and no phase is declared done on a metric nobody can read.

> **The split that makes this work.** The document-intake pipeline is built once in
> Phase 1 and used for *your own* syllabus — instant term setup, valuable at one user.
> *Inheriting someone else's verified parse* is the network feature, and it switches on
> in Phase 3 when cohorts exist. Same pipeline, two different kinds of value, two
> different moments. Treating them as one feature is what made Phase 1 look like it
> delivered a network effect to five people.

### Phase 0 — Safe and measurable (now)
Nothing ships on top of this until it is done. Neither item below is a feature, and both
are prerequisites for every decision after them.
- **Database-level isolation.** Move the per-user invariant out of application code and
  into the database, so a query that forgets its filter fails closed instead of leaking.
  **Do this now, while every table is still single-user** — it is a migration today and a
  retrofit later. Expect per-request identity to be propagated into the session; the app
  connects as a single role.
- **An enumerated isolation test.** Walk all 139 routes with two users and assert the
  first cannot reach the second's rows. Coverage today is per-feature and depends on
  someone having remembered.
- **Delete surplus copies of production data** (§9.10). One hour, negative liability.
- **Analytics.** Every gate below is a number nobody can currently read. Engagement is
  one SQL query away; retention needs event capture.
- **Push notifications and a scheduler.** Reminders today only fire while the app is
  open, which is a promise the app does not keep. Confirm the web-push path first — if
  this forces a native client the cost changes character (§9.1).
- **Onboarding.** Time-to-first-value in minutes. A new user currently gets empty screens
  and a lot of typing.
- **Confirm every destructive path.** Four deletes go through `DeleteConfirmModal`; **nine
  do not**, and two of those cascade — the sinking fund's own `aria-label` reads "Remove
  {name} and its transfers", so it announces the cascade and then performs it on a single
  click. This is here rather than under polish because losing data a user cannot get back
  falls under §3.1. The audit is of **code paths, not buttons**: the omnibox, quick
  capture and any keyboard shortcut that can destroy a row count too. Recoverable actions
  — archive, soft delete, a paused rule — deliberately do not need the dialog.

### Phase 1 — Worth keeping (single-user depth)
Everything here is valuable at **one user**, needs no cohort and no sharing, and can
therefore be built while the user count is still five. This is the phase that earns the
right to invite anyone.
- **Document-intake pipeline, pointed at your own syllabus** (§13.8, §13.12).
  Unstructured document → JSON → human verification → record. Upload a syllabus and the
  term builds itself: assessments, weights, dated exams, due dates. Finals parse as
  date-TBA at UBC, which is a state rather than a failure. One pipeline later serves
  offer letters, pay stubs and T4s — the best infrastructure ROI in the document.
  - **Verified parses are kept, structured for sharing, and not yet shared.** The
    canonical-course table and `course_lookup.py`'s widening (§5.4) were planned here;
    **moved 2026-10-05 to Phase 2** as the shared course catalogue, so Phase 3 is still
    a switch rather than a migration.
- **Surface the projections that already exist.** Required final and cheapest path are
  built and good, and reached through a modal on a course page. Putting them where a
  student meets them without looking is presentation, not engineering.
- **Workload forecasting:** "14 hours of estimated work due in the next 7 days." The
  inputs exist already — a per-task time estimate and a calendar that computes free
  blocks — so this is aggregation over built parts, and the cheapest real win here.
- **Multiple grading schemes** (§7), sourced from your own verified parse.
- **Degree audit and prerequisite graph** (§13.19). Courses plus programme requirements →
  missing credits, breadth gaps, a cheapest-term path, and a visual unlock map. The
  onboarding wedge for transfer and first-year students, and entirely single-user.
  Transfer mapping is many-to-many with manual override always available. The audit is
  single-user; the prerequisites it reads come from Phase 2's shared catalogue.
- **Rebuild reminders on the new scheduler.** They have zero rows and promise something
  the app cannot do. A broken promise is worse than a missing feature.
- **Money room — the whole single-user core.** No shared-data gate, no density
  requirement, so it runs in parallel with the academic work above rather than behind it.
  - **Capture:** Omnibox AI entry for daily use, CSV import for the onboarding backfill
    and weekly reconciliation, with recurring-transaction detection at import (§13.1,
    §13.9). Preview-before-commit on both; dedupe so a backfill never double-counts.
  - **Auto-categorization** (§13.10), personal layers only at this stage — learned
    merchant map, curated rules, naive Bayes, LLM for unseen merchants. The *shared*
    world-knowledge pool is a Phase 3 unlock, for the same reason as syllabi.
  - **Foresight, which is the room's actual edge** (§13.3): cash-flow forecast, runway,
    merchant run-rate, safe-to-spend-today. "At this pace you go negative in week 9" is
    what no generic budget app models.
  - **Annual planner and hours-to-goal solver** (§13.4). Compose primitives the app
    already holds into one running-balance projection, then solve backwards into required
    work hours as scenarios.
  - **Paycheque verification and vacation pay** (§13.11). Expected versus actual pay with
    BC overtime and stat-holiday rules. Unique, trust-building, and only possible because
    shifts and paycheques live together.
- **Make a click feel like a click.** `:active` appears **zero times** in the entire
  stylesheet, so nothing anywhere shows a pressed state; of 183 buttons, roughly 69 fire
  with no acknowledgement at all. One `:active` rule on the shared button classes is a few
  lines and covers all 183, then a pending state on anything that makes a request. A
  product whose pitch is foresight and trust cannot feel unresponsive at the moment of
  input.
- **Explain on demand, not everywhere.** 128 sentences of ambient muted text crowd out the
  figures the panels exist to show. `HelpTip` exists and is in use twice; the rest is a
  panel-by-panel sweep, moving text that answers "what is this?" behind the mark and
  leaving text that changes what you are about to do on the page.
- **Cut as you go:** sinking funds (zero rows) and the orphan `category_budgets` table
  (§14). A phase that adds without removing accumulates surface a solo builder pays for
  forever.

### Phase 2 — Worth sharing (the growth loop)
The first phase whose purpose is **more users**, not more features. Everything here needs
two people or a team, none of it needs a cohort, and each item makes the next phase land
on a larger base.
- **Shared course catalogue and prerequisites** (added 2026-10-05,
  `Ideas/overhaul/Phase 2/`). Courses know their prerequisites, and both are shared
  world knowledge: one table for everyone, keyed by campus (UBC Vancouver and Okanagan),
  subject and number. Prerequisites are **advisory, never a block**, because exceptions
  are made.
  - **The first table every user reads and no user owns.** The API can read it and
    cannot write it; rows are written only by an owner-run review of users' proposals.
    That is §5.6's "writes are constrained", taken to none from a request.
  - **Sources: users' own syllabi for now.** UBC's terms of use need written consent to
    reproduce the Academic Calendar, so a bulk import waits on UBC's answer
    (`Ideas/overhaul/calender-request.md`). A structured fact is shared once reviewed;
    a syllabus's own wording stays with the person who uploaded it.
  - **Automatic approval later, not yet:** planned at about five different people
    proposing the same rule, counted on verified accounts before open signup.
  - It fits this phase's test, since it needs two people and never a cohort, and it is
    the safe, read-only half of sharing that shared tasks then extend to writes.
- **Shared tasks and events — group coursework.** Add a collaborator to a task,
  assignment, project or calendar event and it appears for everyone added. Group projects
  are the most common form of student collaboration and are currently coordinated in a
  group chat, so this is the gap the three rooms did not cover: the app had sport teams
  and completion stats but nothing for the work students actually share.
  - **It is also the better growth loop for an academic product.** It triggers on
    coursework every student already has, where intramurals require a sport they may not
    play — and inviting a collaborator *is* an invitation to the app.
  - **It changes the data model.** §5.1 lists tasks and events as strictly per-user;
    they become owner-plus-collaborators, and shared **write** access is a larger
    authorization surface than the read-only sharing elsewhere in the plan. The §5.6
    model covers the pattern (a member edits their own team's rows) but it has to be
    built here rather than assumed.
- **Accountability partners — completion, not outcomes.** Share a streak or weekly
  completion percentage with a friend. Needs exactly two users, costs about a week, and
  is the most proven adherence mechanic there is.
- **Team sport and intramurals** (§4 Phase 3 previously). Create a team, invite
  teammates, anyone records a score, everyone sees standings. **This is the acquisition
  loop** — one team is five to ten people, and it works at a single team's scale with no
  density whatsoever. Moving it ahead of the depth features is the central change in this
  restructure: every phase after it lands on more users than it otherwise would.
  - Per-sport stat templates, post-game flow under 30 seconds, **teammate confirmation
    from version one** rather than after the first dispute.
  - Game scores and standings need **no exertion score**, which is why the
    maintenance-heavy fitness integrations wait for Phase 3.
- **Open signup, with affiliation verified later.** Phase 0's isolation is the gate and it
  has already been passed by this point, so what remains is operational: email
  verification, abuse detection and an account-removal path (§6).
  - **Gate, not a line item: the per-client rate limiter is global today.** `client_of()`
    returns the peer address, and behind Cloud Run every caller is the proxy — production
    logs showed 99 of 99 requests from one internal address, so the throttle is one shared
    budget rather than per client. It does not bite now because four of five users sign in
    with Google and never reach it; it bites the moment anyone can register. The fix is
    real work, not configuration: an unvalidated `X-Forwarded-For` is attacker-controlled
    and would hand out unlimited fresh throttle keys, so it means trusting a specific
    forwarded position from Cloud Run. **Open signup does not ship before this does.** Opening
  here rather than last is deliberate — depth built for five people is depth built on a
  guess, and §3.7 says validate before building.
  - **Honest tradeoff:** this enlarges the attack surface earlier, with fewer retention
    features in place and more support load on one person. The safety posture is
    unchanged — isolation still precedes it — but the operational cost arrives sooner.
    This is the item to overrule if the appetite is not there; the rest of the phase
    stands without it.
- **End-of-term flow** (§13.7). One post-grades screen collecting course ratings and
  anonymous grade contributions. The *collection* path ships here so that Phase 3 has
  something to aggregate — a density feature with no intake is a feature with no data.
- **Shift-versus-exam conflict flags** (§13.11) and the **tax packet**. Small builds,
  high gratitude, and the tax packet is seasonal and gets recommended to friends.

### Phase 3 — Density pays (the network features switch on)
Nothing here is new infrastructure; it is the moment the Phase 1 pipelines and the Phase 2
user base meet. Every item was impossible earlier for lack of people, not lack of code.
- **Shared syllabi switched on.** The pipeline exists from Phase 1 and the canonical
  course table (the shared catalogue) from Phase 2; cohorts exist from Phase 2. Now the second student in a course inherits a
  verified parse for free, and each course is *solved once*. Only verified parses publish.
- **Grade distributions, anonymised, with a cohort floor.** "You are at 74%, the class
  median is 81%" — rendering only above a minimum number of contributors, because below
  that an average is a disclosure wearing an aggregate's clothes. Fed by the Phase 2
  end-of-term flow. **Individual grades are never shared** — not between friends, not
  opt-in, not at all.
- **Shared merchant map** (§13.10). The world-knowledge half of auto-categorization, which
  turns a new user's first import from 25% categorized into 80% — the onboarding magic
  moment. Cohort floor of independent confirmations, precomputed, personal override always
  wins.
- **Crowdsourced course intel.** Effort reports → per-course aggregates. The collection
  rode in with the end-of-term flow; this is where enough contributors exist to render.
- **Exertion score and the fitness integrations** (§13.14). Points = duration × MET ×
  corroboration weight, formula versioned and never rewritten. Hybrid inputs weighted
  toward corroboration: Strava or Fitbit if you have them, manual sessions if you do not.
  No native client required. Deferred to here because it is the most maintenance-heavy
  feature proposed and it only matters once there is someone to compete with.
  - **Adaptive goals:** trailing average with progressive overload, dip *proposed* during
    crunch weeks. Always advised, never imposed.
- **Campus and city leaderboards.** Competition widens team → league → campus → city. The
  wedge is *who* you compete with — Apple ships activity competitions one tap away, but
  not against your dorm. Precomputed aggregates, opt-in, disclosure by design.
- **Open league directory and club management.** Browse and filter by sport, level and
  region; dormancy greying, verified-organizer badges, anti-spam gates. Clubs get
  membership, polls, broadcasts and a member-visible calendar. **Never launch the
  directory empty** — nobody joins an empty room.
- **Office-hours radar and co-op salary transparency** (§13.19). Both are aggregate-only
  and both need density: the radar to anonymise check-ins, the salary data to converge
  independent submissions or match a parsed pay stub. Unverified offers never enter the
  aggregate.

### Phase 4 — Smart (history pays)
The coach. Everything here needs *time* rather than people — a term of personal history,
and in several cases data from all three rooms, which only exists once Phase 3 has run.
- **Weekly planner:** constraint-satisfaction scheduling over free blocks. Sort by due
  date and priority, fill greedily, explain the choice ("Thursday, because Friday is
  full"). An LLM would be slower, pricier and occasionally schedule study at 3am.
- **Deadline risk prediction:** personal velocity against required velocity. Division, not
  machine learning. Needs roughly a term of history to mean anything.
- **Focus sessions tagged per course**, and **exam countdown mode**.
- **Proactive briefings** on the Phase 0 scheduler, plus the **BYOAI briefing API**
  (§13.19) — serve the deterministic digest to the student's own assistant at zero AI cost.
- **Cross-room correlations, non-financial only.** The §13.3 silo excludes every
  correlation involving money. What remains is academic against body, which is why this
  could never have run before the exertion score existed.
- **Term simulator** (§13.19), the capstone and the first feature that needs all three
  rooms. Compose each room's deterministic projection over one shared 168-hour week. Work
  hours output **time fit only**; grade bands render solely from directly-set study hours.
- **Grade scenarios, course-drop simulator, next-term planner** (§13.6). The simulator
  pattern on engines that already exist. Course-drop carries real disclaimers — full-time
  status affects loans, housing and immigration standing.
- **Deadline spending guard** (§13.5). Crunch detection → personal spike prediction →
  pre-allocation → report card. Silent until two crunch weeks of history exist.
- **What-if simulator** (money), **self-employed support** (§13.12).
- **Plaid bank sync**, as the paid tier and not before. The money room must prove
  retention on hand-entry and CSV first; buying that liability earlier is pure cost.

### Explicitly not building
- **Individual grade sharing**, in any form. Decided, not deferred.
- **Apple HealthKit and a native client.** The exertion module needs neither. One
  condition would change this: if Phase 0's push notifications force a native client
  anyway, HealthKit becomes nearly free and is worth revisiting then.
- **Sleep and medical-grade health tracking.** The score needs "roughly how much did you
  move", which tolerates noisy inputs. Sleep analysis does not, and Whoop and Apple
  already own it.
- **A workout logger** competing with Strava or Apple Health. Import, don't replicate.
- **Manual TV, film or music logging.** No accountability angle, entrenched competitors,
  pure friction.
- **A general-purpose budgeting app.** The money room earns its place next to term
  structure, tuition and shift income.
- **Stranger discovery of any kind** (§13.19). Account connects you to people you already
  know; it never introduces you to people you do not.
- **Third-party ad SDKs** (§13.15). Maximum trust cost for minimum revenue.

### What moved, and why
| Feature | Was | Now | Reason |
|---|---|---|---|
| Shared syllabi | Phase 1 | Pipeline P1, sharing P3 | A network effect needs a network; the single-user half pays immediately |
| Team sport | Phase 3 | Phase 2 | The only acquisition loop in the document; everything after it should land on more users |
| Open signup | Phase 4 | Phase 2 | Isolation is the gate and it clears in P0; depth built for five users is built on a guess |
| Grade distributions | Phase 1 | Phase 3 | Needs contributors; the intake moved to P2, the aggregate to P3 |
| Crowdsourced intel | Phase 1 intent | Phase 3 | Same — collection early, rendering late |
| Exertion score | Phase 3 (with sport) | Phase 3 (after sport) | Teams need no score; the OAuth maintenance should wait for competitors to exist |
| End-of-term flow | Phase 1 | Phase 2 | It is the intake for P3's aggregates, so it must precede them |
| Shared merchant map | Phase 1 | Phase 3 | Cross-user pool, same density logic as syllabi |
| The coach | Phase 2 | Phase 4 | Needs a term of history, and correlations need body data from P3 |
| Canvas sync | Phase 0 | Deferred, §10 | Neither safety nor sight; shared syllabi may cover the same ground more cheaply |
| Canonical course table, prerequisites | Phase 1 | Phase 2 (2026-10-05) | It is the first shared table, so it belongs with the sharing phase; renamed the shared course catalogue and planned with the overhaul template |

**Pulled in from `Ideas/next.md`, 2026-10-02.** Three things were planned there and absent
here: **shared tasks and events** (Phase 2 — the vision had sport teams and completion
stats but nothing for group coursework), **the three interface-quality asks** (the nine
unconfirmed deletes to Phase 0 under data safety, the click acknowledgement and (?) sweep
to Phase 1), and **the rate limiter**, promoted from a bullet inside open signup to a gate
on it. Deliberately left in `next.md` as backlog rather than vision: keyboard shortcuts,
sidebar icons, duplicate dashboard buttons, event colour customisation, cash tips, shift
list ordering, account drag-ordering, read-only offline, the term retrospective and
reimbursement state.

## 5. Data Architecture

### 5.1 The core transition
Everything today is single-user. The move is to shared domain objects, on one
principle: **separate shared entities from each user's relationship to them.**

**Shared, none of which exists yet:** `courses` as a canonical row (school, code,
name), `grading_schemes`, `scheme_components`, `syllabus_parses`, grade-distribution
aggregates, effort aggregates, `organizations`, `leagues`, `teams`, `games`,
`player_stats`, exertion-leaderboard aggregates.

**Per-user, linked rather than duplicated:** `enrollments` (user → course, term,
target, chosen scheme), plus grades, transactions and exertion entries, each keeping
`user_id` with an optional `course_id` link.

**Owner plus collaborators (new, Phase 2):** tasks and calendar events stop being
strictly per-user once shared coursework ships. The shape is an owner and a collaborator
join table rather than a duplicated row per participant — one task, several people who
can see and complete it. This is the only place in the plan where one user gets **write**
access to another's row, which is why it is called out here rather than folded into the
per-user list.

### 5.2 Key decision: don't share assignment instances
Different sections of the same course have different due dates and weightings. A
single shared "CPSC 304 Assignment 1" row creates an unresolvable conflict over whose
due date wins. Keep assignment rows per-user and share only course-level structure and
aggregates. Network effects without conflict resolution.

### 5.3 Organizations & scope
- `organizations`: id, type (`school` | `city` | `association`), name, region, and a
  self-referential `parent_id`, so USports → Canada West → UBC is a tree. A league or
  a leaderboard attaches at any level.
- **Multi-league teams:** put the league link on a `team_registrations` join table
  rather than a `league_id` column on teams — a UBC team may also play a city league.
  Cheap now, a painful migration later.
- **Discovery:** onboarding asks "where do you study, and where do you play?",
  defaulting to the user's school.
- **Affiliation is self-declared and verified later** (§4, Phase 2), so an
  organization link is a claim until something checks it. Anything consequential —
  a campus leaderboard ranking, a verified-organizer badge — must depend on the
  verified flag rather than the claim.

### 5.4 Identity & dedupe
"CPSC 304", "CPSC304" and "CPSC_V 304" will fragment a shared course table.
**Most of this is solved:** `course_lookup.py` already splits a code into letters and
number, prefix-matches across campus suffixes, and refuses to guess on an ambiguous
prefix because filing against the wrong course is worse than filing against none. What
is missing is scope — it looks at one user's courses. Widening it needs a school-scoped
canonical list, a report-duplicate path, and an admin merge tool that repoints
enrollments.

### 5.5 Migration path (no big-bang rewrite mid-term)
1. **Close the isolation gap first** (§5.6). Everything below increases the cost of
   doing it afterwards.
2. Add shared tables alongside the existing ones; add a nullable `course_id` to the
   per-user tables.
3. Backfill by hand — trivial at 31 courses.
4. Build new features against the shared model from day one.
5. Enforce non-nullable links once the backfill is clean.

### 5.6 Isolation & privacy model
**How it works today.** The API authenticates the caller, resolves a verified user id
through one dependency, and every query filters on `user_id` — or reaches its rows
through a parent that does. It is tested in 18 files. The structural weakness is
that correctness depends on each query remembering its filter, with no database-level
backstop if one forgets.

**Target, and a Phase 0 gate rather than a later improvement:**
- Per-user tables get a database-level predicate, so a forgotten filter fails closed.
- Shared tables are readable by authenticated users; writes are constrained — team
  members edit their own team's games, effort reports are insert-only, organizers
  manage their own leagues.
- **Collaborator write access is the sharpest case** (§5.1). A shared task can be
  completed by anyone on it, so the policy is membership-based rather than ownership-based
  — and membership itself has to be writable only by the owner, or a collaborator could
  add themselves to anything. Model it as an explicit join table with its own policy, not
  as a list column on the task.

**The rule that matters most, because the shortcut is tempting.** A strict per-user
predicate and a shared-aggregate feature are in direct tension: class distributions and
campus leaderboards are cross-user reads, which the policy forbids. **The resolution is
never to relax the policy.** Aggregates are precomputed into their own rows by a job,
and the leaderboard reads a leaderboard table rather than joining across users at
request time. Decide this before the first aggregate feature, because a policy
exception is exactly where this kind of thing fails.

**Disclosure is explicit.** Leaderboards and distributions are public by intent and
opt-in per feature. Private-by-default is the right posture for grades and money and
the wrong description of a leaderboard; the document says which is which rather than
applying one rule to both.

## 6. Governance & Roles

Three problems, not two, once signup opens:
1. **Curating reference data** — course dedupe, organization hierarchy. Platform work:
   fuzzy-match suggestions at creation plus merge tooling.
2. **Moderating community content** — leagues, teams, spam. Distributed rather than
   centralised: league creators are implicitly their organizers.
3. **Policing registration** — new with open signup, and currently handled entirely by
   the allowlist. Needs rate limits, email verification, and a way to remove an abusive
   account that does not involve direct database access.

**Role model to design toward:** platform admin (abuse removal, course merges); org
moderator, scoped to one organization's subtree so UBC's moderator cannot touch
Vancouver city leagues; league organizer; team captain. Store as `user_roles`
(user_id, nullable org_id, role) when volume demands it; until then a `created_by`
check suffices.

## 7. Multiple Grading Schemes

Courses with multiple rubrics — section-dependent weightings, "choose your scheme",
best-of policies — break every generic grade calculator, which makes this a real
differentiator.

**What exists today:** per-course categories with weights, a running average, a target
grade, and required-final and cheapest-path projection against that one scheme.
Multi-scheme does not exist.

- **Model:** `grading_schemes` per course (label, term) → `scheme_components` (name,
  weight, rule fields). `enrollments.grading_scheme_id` records the student's choice.
- **Comparison view:** project the final grade under each scheme side by side
  ("A → 84.5%, B → 87.2%"). Two modes: *choose upfront*, which informs section and
  course selection, and *best-of automatic*, which needs no decision at all.
- **A rule engine, not just weights.** Real rubrics carry conditions: "final replaces
  midterm if higher", "drop the lowest two quizzes", "lab ≥ 50% to pass".
  Deterministic, and where generic calculators die.
- **Sourced from the shared syllabus parse**, which is what makes it affordable —
  extract every scheme a course offers once, for everyone in it.
- **Version schemes.** Professors change rubrics mid-term; keep history, never
  overwrite.
- **Show the work.** "87.2% under Scheme B" is meaningless without an expandable
  breakdown. Trust in the arithmetic *is* the product.

## 8. Analytics & Metrics

None of this is built, which is why it sits in Phase 0 — every gate in §11 is
currently unreadable.

- **The universe test first:** rooms visited per week per person, and whether anyone
  opens the app for two different reasons in one week (§1).
- **Adoption:** users, growth, weekly and daily active, retention.
- **Engagement:** already queryable from Postgres — tasks created, completion rate,
  deadlines tracked, grade entries, most-used features.
- **Reliability:** uptime, response times, error rates.
- **Per-module adoption:** what kills a dead feature with evidence instead of opinion.
- **The switch metrics:** do new users connect Canvas or import a syllabus in their
  first session? Weekly retention? The Sean Ellis test before and after each phase.

**How:** engagement needs aggregate queries, not a pipeline. Product analytics via
something lightweight rather than homegrown. **Privacy rule:** this is friends'
school, money and exertion data — aggregates only, anonymous, and say so out loud.

## 9. Complications, Risks & Open Issues

### 9.1 Open signup versus data safety
These are the two strongest commitments in the document and they pull against each
other. Open registration multiplies the surface over an allowlist of five addresses,
while §3.1 puts data safety above everything at any cost. The plan resolves it one
way only: **the Phase 0 isolation work is a gate, and if it slips, open signup waits.**
Anything else leaves the two commitments in open conflict (§12.1).

### 9.2 Privacy, compliance and trust
Grades, money and exertion data about students, some of whom may be minors in first
year. Needs a real privacy policy, consent per data class rather than one blanket
toggle, export and deletion flows — the delete-and-restore path already exists — and
PIPEDA compliance. A breach, or merely the perception of surveillance, ends this
faster than any competitor. Note the posture differs by room: grades and money are
private by default, leaderboards are public by intent and opt-in.

### 9.3 Integration fragility
Per-user OAuth is the durable path for Canvas; scraping breaks on any UI change and
risks the terms of service. PrairieLearn and Gradescope have little or no public API.
Fitness APIs change faster than anything else here — verify current state before
planning. Rate limits and token refresh have to be designed up front, because that is
where integrations die. Nothing is integrated today, so all of this risk is ahead.

### 9.4 Syllabus parsing accuracy — now higher stakes
An LLM hallucinating one weight produces a wrong grade projection. Shared, that error
**propagates to everyone in the course** rather than one uploader. Mitigations: human
confirmation before a parse is published, anomaly flags (weights not summing to 100%),
a visible provenance trail, and a report-and-correct path so the crowd fixes what the
model got wrong.

### 9.5 Exertion scoring: comparability and gaming — resolved 2026-10-02, see §13.14
Steps are not exertion, and any conversion between activity types is arguable — the
leaderboard's credibility dies the first time someone notices cycling scores badly, or
that shaking a phone scores well. Self-reported entries will be gamed, and campus scale
raises the reward. Hence corroboration weighting and teammate confirmation from version
one, and points weighted toward sessions and games over raw steps, which also fixes the
coverage problem for students without a tracker.

### 9.6 The cold-start problem
Shared syllabi, course intel, distributions and the league directory all need density,
and an empty directory is worse than no directory. Mitigations: seed syllabi by hand for
popular UBC courses, enforce a cohort floor on distributions, launch org-scoped, and gate
the directory behind activity thresholds.

### 9.7 Moderation at open scale
Duplicate leagues, dead leagues, spam accounts, abusive registrations. Trust signals,
activity-recency ranking, dormancy greying, roster minimums and rate limits are designed
— and all an ongoing operational cost that needs budgeted time, which a solo builder in a
heavy term does not obviously have.

### 9.8 Maintenance burden, capacity, and scope creep
Every room is a permanent commitment for one person who is also a full-time CS student.
The roadmap is 12–18 months at a sustainable pace, and the "student universe" framing is
exactly the phrase that makes scope creep sound like strategy. Defences: the falsifiable
universe test (§1), phase gates, and a not-building list that is reviewed quarterly and
has already grown.

### 9.9 Security
With isolation in application code, the highest-severity failure is a query that forgets
its `user_id` filter and returns another student's grades or balances.

**A second, narrower hole, documented and deliberate.** The per-client rate limiter keys
on `request.client.host`, which behind Cloud Run is the proxy — so the throttle on
`/login` and `/register` is one global budget rather than per caller. The code says why it
has not been "fixed": reading an unvalidated `X-Forwarded-For` would let an attacker mint
unlimited throttle keys, which is worse. It is survivable while signup is invite-only and
most users arrive through Google; it is a blocker for open signup (§4, Phase 2). In a solo project
the realistic cause is not an attack but a tired person adding a query at 1am. That is
why the spend goes on a constraint that fails closed and an enumerated two-user route
test, rather than on more review process around a convention.

### 9.10 Known debt, carried deliberately
- **DELETED 2026-10-04.** ~~**A second Supabase project, `ommqbgaasrusrlizzyzm`,** created for a restore drill,
  holding a full copy of every user's financial data and password hashes. Password
  rotated, nothing pointing at it. Under §3.1 this gets deleted, not left dormant — a
  surplus full copy is a breach waiting on an unrelated mistake.~~
- An orphaned table, `category_budgets`, holding two rows from a rolled-back feature, so
  production carries one table more than the schema module builds. Dropping it destroys
  real data, which makes it a decision rather than a tidy-up.
- **Three shipped features with almost no use.** Sinking funds and reminders have zero
  rows in production; the per-account monthly category override, shipped 2026-09-25, has
  two. Either nobody wants them or nobody can find them (§12.18).
- Light mode is unbuilt and priced: 155 hex literals and 93 `rgba()` values across the
  stylesheets (36 and 57 distinct), all outside the token system.
- Reminders cannot fire while the app is closed — a known limit stated in the code.

### 9.11 Monetization and cost — decided 2026-10-02, see §13.15
Supabase, LLM calls for syllabus parsing, push infrastructure, fitness API usage and
open-signup scale all cost money. Free tiers cover a five-person beta and say nothing
about five hundred users. Decided 2026-10-02 (§13.15): freemium at $25/yr annual-only, plus university licensing as a separate B2B track — rec
departments already pay for league-management software, which makes the Phase 2 team
product and Phase 3 directory a plausible commercial wedge.

### 9.12 Competition response
Notion, Todoist and MyStudyLife can copy an academic feature; Apple, Strava and Fitbit
already ship activity competitions. The defences are the flywheel — history-dependent
features cannot be copied on day one — and the bounded community, which is the one thing
a global incumbent structurally cannot replicate. Execution speed matters more than
secrecy.

## 10. Open Questions
- Which isolation mechanism: forwarded-JWT row policies, per-request session claims, or
  per-user database roles? All three satisfy §3.1; they differ in operational cost.
- Monetization model, and when to decide it. — **Decided 2026-10-02:** freemium, $25/yr annual-only (bank sync + unlimited document intake as launch premium); university licensing as a separate B2B track (§13.15).
- Does Canvas sync still earn Phase 0 once shared syllabi exist, or does it become a
  convenience rather than the unlock?
- Data retention: how long is academic, money and exertion history kept?
- What is the cohort floor for grade distributions — and is it a fixed number or a
  proportion of enrollment?
- How is affiliation eventually verified, and what breaks for users who never verify?
- Does the money room stay student-specific, or is it on a path to a general finance app? — **Decided:** student-specific; a general-purpose budgeting app is on the not-building list (§4).
- Should the planner model energy and focus patterns? Needs chronotype data; probably
  overkill for v1.
- **What is the abandon condition?** Every phase has an entry gate and none has an exit
  (§12.20).
- **What rule governs sending personal documents (transcripts, pay stubs, T4s) to an LLM
  provider?** Open — and it blocks transcript parsing, which is deferred out of Phase 1
  until it is decided (§13.20, 2026-10-05). Syllabi are course documents, not personal
  ones, and are unaffected.
- Data residency for LLM processing. — **Decided 2026-10-05:** not pinned during the
  beta; revisit before open signup, alongside the PIPEDA review (§13.21).

## 11. Phase Exit Criteria

Every threshold below is currently unreadable — building the measurement is Phase 0. Each
gate tests the thing its phase was *for*, which is what the restructure in §4 makes
possible: a phase about growth is gated on growth, not on features shipped.

- **Phase 0 → 1 — is it safe and can we see?** Database-level isolation live with the
  enumerated two-user route test passing in CI; surplus data copies deleted; analytics
  reporting; push notifications delivering; time-to-first-value under 5 minutes.
- **Phase 1 → 2 — is it worth keeping?** (The parse itself has a 60-second design goal;
  the gate below includes review.) A syllabus upload builds a term in under five
  minutes; weekly retention ≥40% among the beta; ≥3 users "very disappointed" without it;
  the money room used weekly without prompting. **The universe test can pass here now** —
  academic and money both exist in Phase 1, so "two different rooms in one week with at
  least one visit unprompted" (§13.2) is testable a phase earlier than it used to be.
- **Phase 2 → 3 — did it spread?** ≥5 active teams playing real games with same-day score
  logging; registrations from outside the invited group retaining at week two; an
  accountability partnership surviving a month; moderation load inside a few hours a week.
- **Phase 3 → 4 — did density pay?** At least one course where one student's verified parse
  served another; distributions rendering above the cohort floor in more than one course; a
  leaderboard running a full term without a gaming dispute; the shared merchant map lifting
  first-import categorization above 60%.
- **Phase 4 — ongoing, not a gate.** Planner used for ≥50% of study blocks; risk flags
  acted on rather than dismissed; term-simulator calibration improving across two terms.

## 12. Claude's critic

Twenty concerns, written as if deciding whether to put money in. Ordered roughly by how
much each should change the plan.

1. **The two strongest commitments in this document contradict each other.** Data safety
   at any cost and open signup pull in opposite directions, and the only thing resolving
   them is a Phase 0 gate that has not been built yet.
2. **The largest room contradicts the friction principle.** Finances is 48 of 139 routes,
   entirely hand-entered, in a category owned by YNAB and every bank app — precisely the
   manual logging in an incumbent's space that §3.3 forbids.
3. **The thesis is that data flows in automatically and none does.** Every one of the 209
   grades and 182 transactions was typed by hand, and shared syllabi — the first feature
   that would change that — is one phase away.
4. **The universe thesis is unfalsifiable unless somebody measures it.** The cross-room
   test in §1 is the right gate, and it cannot run until analytics exist, which means the
   central claim is currently untested.
5. **The moat does not exist yet.** Every history-dependent feature is unbuilt, so a
   student switching away today loses nothing, which is the definition of no switching
   cost.
6. **Isolation depends on every query remembering a filter, and the plan now shares
   academic data.** The worst-case bug moves from a wrong figure on screen to one student
   seeing another's grades.
7. **Every success metric is unreadable.** No analytics exist, so the phase gates are
   decoration until Phase 0 lands — including the gate that decides whether Phase 0 is
   done.
8. **Three outside users cannot validate anything, and two of the five allowlisted
   addresses appear to be the builder's.** A beta of three friends will not tell you the
   product is bad, which is the only information worth having at this stage.
9. **The best-built features are the hardest to find.** Required final and cheapest path
   are genuinely good and live behind a modal, which is why a previous revision of this
   document listed them as unbuilt work.
10. **Nobody has asked for the body room.** It is the furthest feature from anything the
    product does today, and the one where "sounds good" and "would actually use" are
    hardest to distinguish — which makes it the first interview question, not the first
    build.
11. **Exertion fairness — answered 2026-10-02, verify in practice (§13.14).** Grounding
    points in METs with a versioned, never-rewritten formula moves this from arguable to
    defensible; the residual risk is whether students accept the standard, which only a
    live leaderboard settles.
12. **Self-reported points will be gamed and campus scale raises the reward.** Teammate
    confirmation is designed, but it has to ship in version one rather than arrive after
    the first dispute.
13. **Grade distributions need a cohort floor before they render at all.** At current
    scale a class average is one person, which is a disclosure wearing an aggregate's
    clothes.
14. **Open signup removes security work the allowlist has been doing silently.** Rate
    limits, email verification, abuse detection and an account-removal path all have to
    exist before registration opens, and none do.
15. **Apple already ships activity competitions one tap away.** The wedge has to be who
    you compete with rather than that you compete — and open signup erodes exactly the
    bounded community that makes that wedge work.
16. **Syllabus parsing is load-bearing and now feeds other students.** §3.4 puts LLMs at
    the edges, but this one sits upstream of grade projection for everyone in a course,
    where one hallucinated weight propagates.
17. **Cost model — answered 2026-10-02 (§15, §13.16–13.18).** The ledger prices build
    weeks, maintenance and liability rather than servers, and lands on the right
    conclusion: labour dwarfs infrastructure roughly 100:1, so time is the binding
    constraint.
18. **Three shipped features have almost no use.** Sinking funds and reminders have zero
    rows and the monthly override has two, and nothing in the roadmap stops that
    recurring — the module-adoption measurement meant to catch it does not exist.
19. **The engineering discipline outruns the product discipline.** 1,036 tests,
    Postgres-verified migrations and a real rollback runbook sit alongside no analytics
    and no user research, which is the signature of building what is satisfying rather
    than what is uncertain.
20. **Nothing here defines failure.** Every phase has an entry gate and none has an
    abandon condition, which is how a solo project runs for two years on sunk cost
    instead of evidence.

## 13. Addendum — 2026-10-02: money capture strategy & universe refinements

### 13.1 Money room data capture, sequenced

**The problem, stated precisely.** Manual expense tracking fails not because typing is
slow but because of forgotten transactions: the budget goes quietly wrong, trust
erodes, usage stops. Every capture strategy below is judged on *completeness*, not
per-transaction speed.

**Layer 1 — AI-assisted entry via the Omnibox (daily capture).** "Spent $12 at Subway"
parses into a categorized transaction. This is the lowest-friction per-transaction path,
handles cash where sync is blind, and categorization is exactly the kind of
unstructured-understanding task a small model does well. Cost is negligible (a
mini-model call on ~200 tokens is a fraction of a cent; even 10k users × 30
transactions/month is tens of dollars). Limitation, stated plainly: it solves typing,
not remembering.

**Layer 2 — CSV import (onboarding backfill + weekly reconciliation).** Every Canadian
bank exports CSV. Two jobs, neither of them daily import:
- (a) **Onboarding:** import 90 days on signup. Instant populated app, the magic
  moment that makes someone stay.
- (b) **Weekly catch-up:** a 2-minute weekly import catching what AI entry missed —
  the safety net that keeps the budget trustworthy.
Implementation requirements: preview-before-commit (consistent with the Omnibox), and
dedupe on amount + date + merchant within a window, so backfills never double-count
hand-entered rows. Zero marginal cost, zero tokens stored, zero new liability.

**Layer 3 — Bank sync via Plaid (later, as a paid tier).** Researched 2026-10-02:
- **Plaid** pay-as-you-go has no minimum spend and a free trial covering 10 production
  connections; Transactions sync bills monthly per connected account (exact rates on
  production application). The only viable provider at this scale.
- **Flinks** has better Canadian-bank reliability but starts at **$500/month on a
  1-year term** — priced out until real revenue.
- Canada has **no operational open banking** (framework still not live in 2026); all
  aggregation is screen-scraping with uneven per-bank reliability. Budget support
  cost, not just API fees.
- The larger cost is **liability**: storing bank access tokens (encrypted at rest,
  never logged), PIPEDA compliance, and a step-change in security posture.
- Market pricing exists: Canadian budget apps charge ~$7.99 CAD/month for sync —
  pass the cost through as the premium tier that funds itself.
- **Trigger:** the money room passes the universe test on Layers 1–2 first. If users
  won't hand-import a CSV, they won't retain on auto-sync either — and then the
  liability was bought for nothing.

**Strategic note.** The money room's differentiated half is the student-specific,
forward-looking features (safe-to-spend, term budgets, tuition-per-course, shift
income — the last already structured and near-automatic). The generic ledger is
commodity competing with every bank app's auto-categorization. Allocate the room's
future budget to deepening the student-specific half; keep the commodity half cheap
(Layers 1–2 above).

### 13.2 Universe thesis refinements

- **Tightened test.** "Two reasons in one week" passes trivially (a grade check and a
  task check are two reasons inside one room). The gate is **two different rooms in
  one week, with at least one visit unprompted** — notification-driven visits don't
  count, or the metric manufactures itself.
- **The split test.** If the app were divided into three separate apps tomorrow, would
  any user's behavior change? If no, it's a bundle, not a universe. The features that
  pass are the cross-room ones (correlations, a planner that sees shifts *and*
  deadlines) — all currently unbuilt (§12.5), so the thesis is 100% future until they
  exist.
- **Rooms are not equal citizens.** The bounded community genuinely advantages exactly
  two things: shared courses (syllabus network effects) and intramural competition
  (the who-you-compete-with wedge). Money and generic fitness gain nothing from
  density. Treat Academic as the network core and Money/Body as retention satellites
  until evidence says otherwise.
- **Bootstrapping paradox, stated.** Integration is the moat, but the moat cannot help
  win rooms — each room needs a standalone 10x wedge first (shared syllabi; team
  competition). Money currently has none; its wedge must come from the
  student-specific half, not the commodity ledger.

### 13.3 Money room: innovative metrics & the financial silo principle (added 2026-10-02)

**Decision: financial data is siloed, not just private.** Money is private by default
(§9.2) *and* excluded from cross-room features and peer comparisons — even
anonymized. Concretely, two otherwise-promising metrics are **rejected**:
- **Work-study tradeoff** (shift hours vs. grades/completion) — correlates financial
  data with academic data across rooms. Out.
- **Peer-relative spending** ("UBC students spend a median of $X on food") — compares
  financial data across users. Out, regardless of cohort floors.
This supersedes the "spend against term week" line in the cross-room
correlations (Phase 4): correlations involving financial data are not built. Grades and
exertion may be aggregated and compared; money may not.

**Metrics to build** (all deterministic, all single-user, all forward-looking —
the money room's edge is student-specific foresight, not another ledger):

- **Term cash-flow forecast.** Project balance forward across the term from tuition
  installments, rent, recurring charges, and *projected* shift income from scheduled
  shifts. Output is a date: "at this pace you go negative in week 9." The money
  equivalent of deadline-risk prediction; no generic budget app models tuition terms
  or shift schedules. Highest priority in the room.
- **Runway.** Burn rate → "your savings last until March 14." Simple, visceral,
  turns abstract overspending into a concrete date.
- **Merchant run-rate.** Top discretionary merchants ranked by projected term cost:
  "at your current pace, DoorDash costs you $612 this term." The latte factor with
  actual math.
- **Safe-to-spend-today.** The existing safe-to-spend made intraday and
  obligation-aware: "you can spend $42 today and still cover rent Friday and your
  tuition installment." The difference between a number and a decision.

**Capture stack, restated with the silo in mind:** Omnibox AI entry for daily capture,
CSV import for onboarding backfill + weekly reconciliation (§13.1), Plaid as a paid
tier later. Nothing in this stack shares financial data outward; the silo holds at
every layer.

**Refinement (2026-10-02):** the silo protects *personal financial facts* (amounts,
merchants visited, spending patterns, peer comparisons, cross-room correlations).
It does not cover *world knowledge*: merchant→category mappings ("Shell = Gas")
reveal nothing about any individual and compound across users like the course
catalog. The principle, sharpened: *personal financial facts never leave the user;
world knowledge compounds.* See §13.10.

### 13.4 Annual planner & hours-to-goal solver (added 2026-10-02)

**Origin.** The builder maintains a yearly spreadsheet (Sept–Apr) laying every known
inflow (carry-over, summer earnings, RESP, federal/provincial grants and loans,
monthly salary) against every known outflow (tuition installments, rent, insurance,
gas, parking, loan repayments, investments, weekly spending) as a hand-maintained
running balance. This is the term financial planner (§13 discussion) already proven
by manual use. The product work is to generate the running-balance column
automatically — and then solve it backwards.

**Annual plan view.** Compose, don't re-enter. Nearly every input already exists as
an app primitive: starting balances (accounts), scheduled one-time inflows (grants,
loans, RESP as dated transactions), salary (jobs pay schedule), tuition (tuition
payments), rent and recurring (recurring transactions), weekly spending (budgets).
The feature assembles them into one chronological running-balance projection for
the academic year. Each fact is entered once, where it lives; the plan builds
itself. This replaces the spreadsheet rather than imitating it.

**Hours-to-goal solver.** The new capability the spreadsheet can't provide. Inputs:
target end balance + date, hourly wage (from the jobs module). The solver works
backwards from the projected shortfall to required work: shortfall ÷ wage = total
hours, spread over available weeks. Present as scenarios, not a single answer —
"8 hrs/wk → ends at $2,100; 12 hrs/wk → ends at $4,800" — because students think in
"what if I pick up more shifts?" Handle seasonal variation explicitly (holiday months
with double hours are real data, not noise); the jobs pay schedule already supports
that shape.

**Plan-vs-actual.** The accountability layer that makes it a coach, not a document.
Actuals (recorded salary, real spending) compare against the plan continuously:
"you're $300 behind plan — 6 fewer hours worked in October than assumed." Drift
flags early, while there's still time to correct.

**Silo check.** All single-user, all forward-looking, no peer comparison, no
cross-room correlation. Passes §13.3.

### 13.5 Connected money features: spending guard & what-if simulator (added 2026-10-02)

**Design rule.** Every module is a sensor for money; money is never a sensor for
anything else. Calendar, tasks, and jobs feed *inward*; financial data never flows
outward — not to academic features, not to peers. Integration into money is
one-directional by construction. This is what makes "connected" compatible with the
financial silo (§13.3).

**Deadline spending guard (calendar → money).** Crunch detection → spike prediction
→ pre-allocation nudge → report card.
- *Crunch detection* from the workload forecast: cluster exams (midterm/final kinds),
  deadlines, and high-priority tasks, weighted by stakes (a 30% final outweighs a 5%
  quiz). A crunch week is forecasted load above the student's personal threshold.
- *Spike prediction* is per-category and strictly personal: the student's own
  crunch-week vs. baseline spending (food delivery ~2× is typical). Surface only
  categories with real lift (>1.5× over ≥3 historical crunch weeks). No generic
  priors, no peer data.
- *The nudge* lands 5–7 days before the crunch, never during: "3 midterms next
  week — you spend 2.1× on food delivery in crunch weeks (~$85 vs $40).
  Pre-allocate $60?" One tap extends the existing per-account category-limit
  primitive to a per-week override.
- *The report card* closes the loop after ("you spent $52 of $60"), building trust
  in the predictions.
- *Cold start:* silent until ≥2 crunch weeks of history exist. A wrong prediction
  early is worse than none.
- *Anti-annoyance:* max one guard per crunch week; three dismissals for a category
  stops suggesting it.
- *Framing caution:* present as pre-allocation, not permission — the guard must not
  normalize overspending.
- *Sequencing:* depends on the workload model (Phase 1) plus ~1 term of categorized
  history, which is why it sits in Phase 4 rather than beside the capture layers.

**What-if simulator (jobs → money).** The annual planner (§13.4) is a deterministic
function, inputs → running-balance curve; the simulator re-runs it with modified
inputs. Free, instant, exact — the deterministic-core principle (§3.4) paying rent;
an LLM approach could not give any of the three.
- *Scenario types:* work ("drop one shift/week," "add Saturdays in November," "no
  shifts during finals"), spending ("cut delivery to $100/mo"), wage ("$22 vs
  $18.50/hr"), one-time ("buy the $800 laptop").
- *Output:* baseline vs. scenario curves overlaid — end balance, go-negative date,
  runway. Saved named scenarios ("Plan A: 12 hrs") with side-by-side comparison.
- *Killer preset — "exam season mode":* zero shifts for the three weeks around
  finals → "not working in December costs you $1,950 of runway." Turns an anxious
  tradeoff into a number.
- *Guardrails:* fixed outflows stay fixed across scenarios; every output lists its
  assumptions ("assumes $18.50/hr, 4.3 weeks/mo"); absurd inputs are capped, not
  silently computed.
- *The line it must not cross:* the simulator stays on the money side. It may output
  "25 hrs/week hits your goal" but must never project academic outcomes from work
  hours — that is the excluded work-study correlation (§13.3) in another form. A
  generic "UBC recommends ≤15 hrs/week in term" disclaimer is acceptable; a
  personalized grade prediction is not.
- *Sharing:* export-only (e.g., PDF for parents who fund the student), explicit
  opt-in per export — never a live share, per the silo.
- *Sequencing:* depends on the annual planner being trustworthy, which depends on
  weekly CSV reconciliation keeping inputs honest (§13.1). The layers stack.

### 13.6 What-if simulator, generalized & professor data (added 2026-10-02)

**The simulator is a pattern, not a money feature.** Model + sliders +
baseline-vs-scenario overlay, built once as a shared component and reused wherever
the app has a deterministic model. Each new deterministic model arrives with its
simulator included — another reason to keep models deterministic (§3.4).

**Grade scenarios.** Generalizes the existing required-final projection: sliders on
each remaining assessment ("what if I get 70% on the final?", "what if I skip
assignment 3?") with a live projected grade. Trivial on the existing grade engine;
high emotional value during finals. Stays on the academic side of the silo.

**Course-drop simulator.** "Drop CPSC 320 → GPA 3.7 → 3.8, credits 15 → 12, tuition
refund $X." The killer detail is the full-time status warning — dropping below the
credit threshold affects student loans, housing eligibility, and immigration status
for international students. High-stakes decisions currently made on gut feel.
Academic → money direction (refund estimate), so the silo holds.

**Next-term planner.** Pick candidate courses → projected weekly workload from
crowdsourced effort hours + grade distributions → "this combo averages 42 hrs/week;
students rate it 2.3/5 difficulty." The academic twin of the term financial
planner: "solve each term once," for time instead of money. Depends on Phase 1
(workload) and Phase 3 (crowdsourced intel), landing in Phase 4 — later, but the
feature that turns course selection from rumor into a decision.

**Professor data: link out, then own, never scrape.** Professor choice moves course
experience as much as workload, and students already check RateMyProfessors — but
RMP has no official public API, scraping violates its ToS, and undocumented
endpoints break without notice (§9.3). RMP data is also self-selection-biased and
unverifiable. Sequencing:
1. *Now:* deep-link from the course planner to the professor's RMP page (URL
   construction — zero integration risk, zero ToS exposure).
2. *Later:* native professor ratings inside the app as part of crowdsourced intel
   (workload, clarity, would-take-again), collected from students verifiably
   enrolled via the app. First-party, compounding with syllabus and effort data —
   strictly better than RMP long-term, because only this app holds enrollment,
   effort, and outcomes together.
3. *Never* bulk-ingest RMP unless a legal path clears.
Professor ratings are public-ish data: no silo or privacy conflict.

**Simulator design rules, carried over.** Every simulator shows its assumptions,
caps absurd inputs instead of silently computing them, and stays on its side of the
financial silo: grade simulators never touch money; money simulators never project
academic outcomes. Frame around agency ("here's what you control"), not anxiety.

### 13.7 End-of-term flow: ratings & anonymous grade contribution (added 2026-10-02)

**The collection mechanism the crowdsourced layer was missing.** Course intel,
professor ratings, effort data, and grade distributions all need a moment when the
student is asked. That moment is the end of term: "you just finished 5 courses —
rate your term."

**Design.**
- *Trigger:* term end date passes plus the local grading lag (UBC posts ~1–2 weeks
  after finals). Ask while the experience is fresh but the stress has faded.
- *One flow, not five interruptions:* a single "rate your term" screen covering all
  completed courses.
- *Ratings (4–5 questions max):* hours/week, difficulty, professor clarity,
  would-take-again. Friction kills response rates; every extra question costs
  completions. Editable for a short window (post-final emotion vs. reflection),
  then locked. Feeds course intel, native professor ratings (§13.6), and the
  next-term planner.
- *Anonymous grade contribution:* "contribute your final grade to the course
  distribution?" — the collection half of the distributions feature, which specified
  the aggregate but never the intake. This flow is Phase 2 precisely so Phase 3 has
  something to aggregate; cohort floor before anything renders (§4, Phase 3). Soft incentive preserving opt-in: contributors unlock the
  distribution view.

**What this is not.** Identifiable grade sharing — with friends, partners, or
anyone — remains excluded per the decided rule (§4, "explicitly not building"):
it is anxiety-producing, asymmetric (the thriving student enables it, the
struggling one feels watched), and it would poison accountability partners, which
are deliberately scoped to *completion, not outcomes*. The end-of-term flow
collects *anonymous contributions to aggregates* and *course ratings*; it never
attaches a name to a grade.

### 13.8 Syllabus schedule parsing: exams, weights & due dates (added 2026-10-02)

**Two linked structures, one extraction pass.** The grading breakdown (Midterm 1 —
20%, Final — 30%, Assignments — 20%) and the dated schedule (Week 5: Midterm 1 on
Oct 6) are separate tables in most syllabi. The parser extracts both and
cross-references them: every weighted assessment ideally resolves to a date, every
dated exam to a weight. Mismatches surface in review ("Final has 30% weight but no
date found") rather than failing silently. Assignment due dates ride the same pass
— the schedule lists them together ("Week 3: Assignment 1 due Sep 26").

**UBC wrinkle: finals aren't in the syllabus.** UBC publishes the exam schedule
mid-term, so finals parse as "date TBA" placeholders with weight attached, and the
app re-checks for the real date later. Model assessments as dated-or-TBA from the
start; a missing date is a state, not a parse failure.

**What one parse powers.** Weights → gradebook categories → grade projection and
required-final. Dated exams → calendar events (midterm/final kinds) → workload
forecast, crunch detection, the deadline spending guard (§13.5), exam countdown
mode. One verified parse feeds four downstream features: the "solve each course
once" thesis working.

**The verification screen is the product.** "I found: Midterm 1 (20%) — Oct 6;
Final (30%) — date TBA..." with edit-before-confirm. Catches hallucinations (§9.4),
and the *verified* parse is what publishes to the next student in the course —
unverified parses never go shared.

**Due dates are initial values, not canonical.** Professors move deadlines via
Piazza/Canvas constantly; the parse seeds the term, sync (or manual edit)
maintains it. Architect dates as overwritable. Recurring items ("quizzes every
Friday") parse to one recurrence rule — the calendar already stores recurrence as
rules, not materialized rows — including per-occurrence skips for reading week.

**Edge cases for the schema.** Drop rules and conditionals ("best 3 of 4 quizzes")
→ the §7 rule-engine fields. Undated components (participation 10%) → weight with
no calendar event; the model must allow it. Week-number schedules → resolve against
term dates. Section variance → structure shared, dates per-section adjustable on
import (§5.2). Mid-term rubric changes → scheme versioning plus a crowd
report-a-change path. Partial parsing is acceptable: weights without dates still
build the gradebook; dates without weights still build the calendar.

### 13.9 CSV import: recurring-transaction detection (added 2026-10-02)

**Detection at import.** Group imported rows by normalized payee + amount; flag
regular intervals (monthly ±3 days, bi-weekly ±2) with three or more occurrences:
"4 monthly charges of $900 — make this recurring?" Variable amounts with the same
payee and interval (utility bills) flag as "amount varies," templated on the most
recent amount. The bar is payee + amount + interval — amount alone is not enough
(weekly manual "$100 spending" logs must not false-positive).

**End date is load-bearing.** The annual planner (§13.4) projects forward; a
recurring rule with no end date projects forever, silently corrupting the cash-flow
forecast and the runway date. The import flow prompts "until when?" — a date or
ongoing. Student life is full of natural end dates (leases, term-length
subscriptions), so the prompt is cheap and the forecast stays honest.

**Two integrations with existing pieces.**
- *Dedupe against existing rules:* if rent is already recurring and the CSV holds
  past rent payments, match the import to the existing rule — fill history, never
  duplicate the rule.
- *Same engine as the subscription audit:* the app already proposes recurring
  charges from the ledger; CSV-time detection is that logic applied at intake. One
  detection engine, two triggers (import + periodic audit).

### 13.10 Auto-categorization: layered, mostly deterministic, shared where safe (added 2026-10-02)

**Yes, without AI for the vast majority.** Spending is habitual — the average person
rotates through ~30 merchants — so a learned lookup covers most volume. Architecture
is cheapest-first, mirroring §3.4 (deterministic core, LLM at the edges):

- **Layer 1 — learned merchant map (per user).** Every confirmation/correction stores
  normalized-merchant → category. Covers the bulk of volume after a few weeks.
- **Layer 2 — curated keyword rules.** Editorial defaults shipped in the app (gas
  brands, known subscriptions, tuition strings). Global, maintained by the
  developer — not derived from users.
- **Layer 3 — naive Bayes on merchant tokens.** Trained on the user's own
  categorized history; runs locally in milliseconds, costs nothing.
- **Layer 4 — LLM, only for never-seen merchants.** Infers the category once; the
  answer is cached into Layer 1 permanently — the fraction of a cent is paid once
  per new merchant, ever.

**Trust rules.** Confidence threshold: below it, ask instead of guessing — wrong
auto-categorization erodes trust like a hallucinated syllabus weight. Run the
pipeline inside the import preview: "we categorized 85% — confirm the rest," so
every confirmation trains Layer 1 and accuracy compounds weekly. Realistic
expectation: 80–90% on real streams from the habitual-merchant effect; the LLM is
a long-tail fallback, and categorization works offline at essentially zero
marginal cost.

**The shared merchant map.** Learned mappings join a global pool, because a new
user's first import categorizing at 80% instead of 25% is the difference between
the onboarding magic moment landing or dying — and it's another bounded-community
network effect (every user improves onboarding for the next, like shared syllabi).
Safeguards:
- *Cohort floor:* a mapping enters the pool only after N distinct users confirm it
  independently (5 is the working floor) — same pattern as grade distributions.
- *Per-user override always wins* over the global mapping.
- *Contested mappings stay out:* a merchant split across categories (e.g., COSTCO
  50/40 Groceries/Household) goes global for no one; those users fall back to
  personal history or Layer 4.
- *Provenance from confirmations only,* never from guesses; contributors are never
  identified — the pool stores mapping + agreement count, nothing else.
This is consistent with the refined silo (§13.3): the pool contains world
knowledge, zero personal financial facts.
- *Built the §5.6 way:* the pool is a **precomputed table** written by a job that counts
  independent confirmations, never a request-time query across users' transactions. Same
  pattern as grade distributions and leaderboards — the isolation rule has no exceptions,
  including for data that is safe to share.

### 13.11 Jobs module improvements (added 2026-10-02)

Current state: jobs with pay schedules as recurrence rules, shift records,
paycheques with deductions + preview, earnings summary with projected next pay.
All improvements below build on those existing primitives.

**Paycheque verification — the standout.** Reconcile expected vs. actual pay:
hours × rate with BC overtime rules (1.5× past 8 hrs/day or 40/week),
stat-holiday eligibility (worked 15 of the last 30 days), and vacation pay
accrual. "Your Oct 15 cheque looks $38 short — Tuesday was 9 hours, overtime may
apply." Hourly student workers are underpaid routinely and never notice; no shift
app builds this for them. Deterministic, trust-building, and only possible
because shifts and paycheques live in the same app.

**Vacation pay tracking.** BC Employment Standards: 4% of gross wages (<5 years),
6% after. Track accrued vs. paid, handling both employer modes (paid out per
cheque vs. held). Verify it appears on the cheque when it should — vacation pay
is one of the most commonly mishandled items for hourly student workers. Folded
into paycheque verification, not a separate feature.

**True hourly wage.** Gross minus deductions over all-in hours, commute included:
"the $18.50/hr gig is really $14/hr after the 40-minute drive each way."
Multi-job ranking falls out — students juggling gigs can compare honestly. Benefit
values convert to $/hr equivalents and fold in here. Feeds the what-if
simulator's wage assumptions (§13.5).

**Benefits record.** Per-job checklist (health, dental, vision, transit pass) +
estimated value per pay period → feeds true compensation. Keep it simple; student
jobs rarely carry rich benefits, but internships sometimes do. (Note: UBC students
already carry the AMS health & dental plan with its opt-outable fee — don't let
the money room double-count it as a job benefit.)

**Tax packet.** Year-end export: total earned, tax/CPP/EI paid, per-employer
breakdown for the T4s, tuition amounts for the credit. Seasonal, and the kind of
feature that gets recommended to friends.

**Earnings-goal progress.** Tie into the hours-to-goal solver (§13.4): "you need
$3,000 by April — at $18.50/hr you're 40% there, 98 hours to go." The goal lives
in the planner; the jobs module shows the progress bar.

**Shift-vs-exam conflicts.** Jobs → calendar (allowed direction): flag shifts
overlapping finals or pre-midterm study blocks at log time, not the night before.
Small build, high gratitude.

**Stock options (light).** Relevant only for startup internships, which is a
minority of student work — keep it minimal. Track grant date, vesting schedule,
and cliff alerts ("1-year cliff hits in 3 months — leaving before then forfeits
X options"). Value as exit *scenarios* only, never a point estimate: private
valuations are opaque and a false-precision number destroys trust. Low priority;
build the hourly-worker features first.

**Priority order:** paycheque verification (+ vacation pay) first — unique,
trust-building, existing data. Then tax packet (seasonal, viral), earnings-goal
progress and conflict detection as natural extensions. Benefits record rides along
with true-wage work. Stock options last, if ever.

### 13.12 Document-intake layer & self-employed support (added 2026-10-02)

**Document-intake layer.** Generalize "syllabus parsing" into a shared pipeline:
unstructured document → structured JSON (mini LLM) → human verification screen →
confirmed record. Four consumers, one extraction engine (a fifth, unofficial transcripts,
was added 2026-10-04 — §13.20):
- Syllabi → courses (assessments, weights, dates) — built first; highest volume,
  shared across users.
- Offer letters → jobs (pay rate, hours, vacation-pay mode, benefits, start/end
  dates, location) — second consumer, nearly free once the pipeline exists. Feeds
  true hourly wage, vacation-pay tracking, benefits record, and the annual
  planner's income curve.
- Pay stubs → paycheque verification (gross, deductions, vacation-pay line,
  reconciled against expected pay).
- T4s → tax packet (employer totals, tax/CPP/EI).
The verification pattern carries over: show what was extracted, confirm-or-edit
before it becomes the record; unverified parses never publish. Anomaly flags
("pay rate missing," "start date in the past"). Amended documents versioned like
grading schemes (§7). Benefits booklets attach as secondary documents to the same
job.

**Self-employed support.** The jobs module assumes an employer (pay schedule,
paycheques, withholding). Self-employment inverts all three:
- *Income model:* invoices and clients instead of paycheques — client, amount,
  date, invoice number, paid/overdue states, with overdue nudges. Model income
  streams with a type field (employment | self-employment); a user can hold both
  (part-time job plus freelance tutoring).
- *No withholding → tax awareness:* track net self-employment income; warn when
  approaching the $3,000 net-tax-owing threshold that triggers quarterly
  installments; surface the CPP double-rate (both halves, unlike employment).
  Installment reminders on the CRA dates (Mar 15, Jun 15, Sep 15, Dec 15).
- *GST/HST threshold:* $30,000 over four consecutive quarters → must register and
  charge. Track cumulative revenue and warn when approaching — a genuine trap for
  freelancers who cross it unknowingly, and almost no consumer app watches it.
- *Deductible expenses:* tag money-room transactions as business expenses (home
  office, mileage, supplies, phone percentage) → feeds the tax packet. This is
  single-user tax computation, not peer sharing or behavioral correlation — inside
  the silo.
- *Variable income vs. the planner:* the hours-to-goal solver (§13.4) can't assume
  wage × hours here. Project from trailing-average income and show a range
  ("typically $400–900/mo"), never a point estimate.
- *Invoicing:* minimal generation with paid/overdue states. Not a full accounting
  product — stop before it becomes one.

**Priority:** document-intake once syllabus parsing proves the pipeline;
self-employment after the core jobs improvements (§13.11). It serves a minority
(tutors, freelancers, gig workers), but the pain is acute where it exists — and
the CRA-threshold warnings are the kind of thing users tell friends about.

### 13.13 Review-pattern catalogue: close every loop (added 2026-10-02)

**Meta-principle.** Every number the app generates that later becomes knowable gets
revisited with the user, and the delta is recorded. That's the learning flywheel
without machine learning — the app gets smarter from the gaps between its
predictions and reality. Features that can't close their loop (no ground truth ever
arrives) need the most caution, because they never self-correct. The no-change
confirmation rate (§15) applies uniformly to all intake verifications.

**Intake verification (parse → confirm).** Syllabus → course structure; offer letter
→ job record; pay stub → parsed totals *before* reconciliation, plus a second
review on the flag itself ("we said $38 short — were we right?"); T4 → tax packet
totals; CSV import → preview-before-commit; recurring-detection confirmations;
bulk grade entry → "here's what will be recorded"; school import → "did we get
your courses right?" at onboarding.

**Prediction review (forecast → actuals).** Task estimates → "you estimated 2h, it
took 3.5h — update your multiplier?" (the personal-multiplier loop made explicit).
Workload forecast → end-of-week actuals. Grade projections → "we projected 84.5%;
you got 82%" — the app grading its own homework, the highest-trust review
shippable. Spending guard → the report card. Risk flags → "were we right?" (tunes
the model). Exertion score → "was this week's score fair?" (tunes the conversion).

**Implicit feedback (dismissal as signal).** Guard dismissals (3× = stop suggesting
that category); briefing thumbs up/down; repeatedly ignored planner suggestions.
Every "don't show me this again" is a labeled training example — log them all.

**Periodic rituals.** Weekly review triage ("8/10 tasks done, 2 dropped — carry
over, reschedule, or drop?"); annual plan review at term start; end-of-term flow
(§13.7).

### 13.14 Exertion score: constant formula, adaptive goals (added 2026-10-02)

**The formula is fixed; the goal is what varies.** This solves the fairness problem
(§9.5, §12.11) structurally: a constant formula means 100 points means the same
thing in September and March, for every competitor. No moving goalposts.

**Ground the conversion in METs.** Points = duration × MET × corroboration weight,
where MET (Metabolic Equivalent of Task) is the exercise-science standard for
comparing activities (running ~9, swimming ~7, cycling ~8). The conversion stops
being arguable and becomes defensible — "we use the sports-science standard" ends
most disputes before they start. Corroboration weighting stands: device-sourced
and teammate-confirmed entries score full; uncorroborated manual entries score
less.

**Version, never rewrite.** If the formula must ever change, it becomes v2 and
history stays v1 — leaderboards are per-version. Retroactively rewriting scores
destroys trust permanently.

**The goal adapts; the formula doesn't.** Personalized weekly/daily targets computed
from trailing history (4-week average × small progressive overload, capped against
spiraling). Contextual: the app *proposes* lowering the goal during exam crunch
weeks (it knows the calendar) and raising it after sustained hits. Always
**advised, never imposed** — the user confirms each change, consistent with the
verification instinct everywhere else. Goal types: streak (hit it N weeks running),
progressive (gradual climb), maintenance (hold through finals). Different
motivations, same ruler underneath.

**Why this works:** fixing the ruler is what makes moving the target meaningful.
If both moved, no one could tell improvement from arithmetic. The "was this week's
score fair?" review (§13.13) tunes the *goal*, never the formula.

### 13.15 Monetization: freemium + B2B (added 2026-10-02) — closes §9.11

**Ads: no.** Third-party ad SDKs contradict data-safety-first (§3.1), and students
are a low-CPM demographic — maximum trust cost for minimum revenue. The
monetizable asset is *trust + student attention at decision moments* (picking
courses, buying textbooks, job hunting); ads liquidate it. Ads go on the
not-building list.

**Model: freemium (student-priced) + B2B licensing.**

*Gating philosophy:* free covers the full core loop plus everything with network
effects — shared syllabi, league participation, accountability partners. Never tax
growth. Premium covers (a) direct marginal-cost pass-through, (b) power-user
depth, (c) convenience. Never gated: core tracking, push notifications, data
export, or any growth loop.

*Premium: annual-only, ~$25 CAD/yr — deliberately below the think-about-it threshold.*
Launch premium is 1–2 features, not a catalogue: **bank sync (Plaid)** — the anchor,
since its per-account cost must be passed through, not absorbed — plus **unlimited
document intake** (syllabi, offer letters, pay stubs, T4s; free tier gets 5
parses/term). Annual-only: one $25 decision a year, no monthly churn to manage,
better cash flow against near-zero marginal cost. The premium tier then grows from
*requested* features, not speculative ones — when customers ask for something with
real cost or depth, that's the next premium candidate. The longer candidate list
(saved scenarios, full history, organizer analytics, AI-polished briefings,
priority support) is a backlog, not a commitment.

*B2B (separate track):* university rec-department licensing for league management
(they already buy this software category); career-services licensing if a
careers/internship module is ever built. Priced per institution.

*Allowed non-subscription revenue:* **league sponsorships** — local businesses
sponsoring standings/leaderboards, the existing rec-league norm, no tracking
involved. **Employer-paid internship postings** — two-sided, needs student density
first. **Textbook price-comparison affiliate** — contextual at course setup,
disclosed, tiny but harmless.

*Sequencing:* monetize only after retention is proven (universe test passing).
Premature paywalls kill the network effects that everything else depends on. Free
while in beta; the paid tier launches with bank sync as its reason to exist.

### 13.16 Investor appendix: addressable market & revenue (added 2026-10-02)

*Rough, labeled estimates — methodology matters more than precision at this stage.*

**Market sizing.**
- **TAM — North American university students:** ~17M (≈1.5M Canada, ~15–16M US
  undergraduates). These are the people living the exact problem: courses, money,
  and body, all unmanaged, in one 4-year window.
- **SAM — reachable in English, product-led:** ~5M. Students at universities where
  a campus-by-campus rollout is feasible without localization or a sales team —
  effectively Canada + US, reached through the team/league distribution wedge.
- **SOM — beachhead:** UBC (~60k students) → Canadian research universities
  (~600k across the U15) → US expansion. Win one campus deeply, prove the density
  metrics (two-room test, league participation), replicate the playbook.

**Why the market is attractive beyond headcount.** Students are a *renewing*
market — ~25% churns every year by graduation, but the same number arrives. A
product that wins a campus keeps winning it. And today's student is tomorrow's
young professional: the relationship compounds beyond graduation (alumni leagues,
early-career money tools).

**Revenue streams, ranked by expected early contribution.**
1. **B2B university licensing** — rec departments already budget for intramural
   management (IMLeagues, TeamSnap territory). Pitch: "your students already use
   us; license the management layer." ~$5–25k/yr per institution by size; 100
   institutions = ~$1M ARR. This is the credible *first substantial* revenue, not
   consumer subscriptions — but note the timing tension: rec departments license a
   league product — Phase 2 under the restructured roadmap — and the campus density that
   makes the pitch credible arrives in Phase 3. Earlier than it used to be, but still
   later than the work it would fund, so it cannot bankroll Phases 0 and 1.
2. **Premium subscriptions** — $25/yr annual-only. Beachhead math, honestly: UBC
   60k × 10% adoption × 5% conversion × $25 ≈ $7.5k/yr. Small per campus — it's a
   long-tail compounder across hundreds of campuses, not the engine.
3. **Employer-paid internship postings** — recruitment revenue once student density
   exists; high value per placement, two-sided.
4. **League sponsorships** — local businesses sponsoring standings; rev-share or
   flat per league. Real-rec-league economics, no tracking.
5. **Textbook affiliate** — small, harmless, disclosed.

**Unit economics.** Near-zero marginal cost per user (deterministic core, no
per-user API spend outside Plaid, which is passed through). CAC near-zero if
distribution is product-led: each intramural team onboarded = ~10 users acquired
for the cost of supporting one organizer. The expensive line items are fixed —
solo/small-team engineering — which is why the cost ledger (§15) prices time, not
servers.

**Campus expansion playbook.** Seed 5–10 intramural teams on a new campus →
~100 users → recruit campus ambassadors from power users → shared course/syllabus
data accumulates → density unlocks distributions, leaderboards, and the directory
→ rec department licensing conversation. Each campus is the same playbook;
marginal cost per campus approaches the ambassador program.

**Comparables.** TeamSnap (team management, charges organizers — closest sports
comp), IMLeagues (university intramural B2B — the licensing comp), Strava
(freemium fitness with the social-competition engine), Notion (free for students
→ institutional/enterprise expansion). Account's differentiation vs. all four: the
three-room integration — none of them owns the student's whole life.

**The pitch in one paragraph.** 17M North American students manage their academic,
financial, and physical lives in disconnected tools or spreadsheets. Account is
the student universe: three rooms, one integration moat, distributed
team-by-team and campus-by-campus at near-zero CAC, monetized through $25/yr
premium, university licensing, and recruitment — on infrastructure whose marginal
cost rounds to zero.

### 13.17 Scaling costs: labor & AI (added 2026-10-02)

**Labor — staged, hired behind traction.**
- *Now → universe test:* solo founder, sweat equity. Burn ≈ $0 + infra (tens of $/mo).
- *Angel stage (post-traction):* first hires — 1 full-stack engineer + fractional
  designer. Canadian market, rough bands: intermediate engineer $100–130k CAD/yr,
  senior $140–180k. Juniors ($70–90k) are cheaper but need mentorship the founder
  can't spare yet — hire intermediate+. Burn ≈ $12–18k/mo all-in.
- *Seed stage:* 3–5 people (2–3 eng, 1 design, founder on product) to ship Phases
  1–3. Burn ≈ $40–60k/mo CAD.
- *Distribution labor stays cheap:* campus ambassadors on stipends ($500–1k/term),
  not salaries — they're the CAC arbitrage, not headcount.
- **Rule: hire only behind proven retention.** Engineers don't fix a failed
  universe test; they multiply a passing one.

**AI costs — sublinear by design, real at scale.**
- The architecture keeps LLMs at the intake edges (document parsing, omnibox,
  categorization fallback) with deterministic cores and aggressive caching — parse
  a syllabus once, serve it to every student in the course. AI cost grows with
  *documents*, not users: sublinear.
- Illustrative math at 100k users (labeled estimate): intake ≈ 100k × 5 docs/term
  × ~$0.01 ≈ $5k/term; premium AI briefings ≈ 10k × daily × ~$0.002 ≈ $600/mo;
  omnibox/categorization ≈ hundreds/mo. Total: low thousands/mo — real,
  budgetable, partly passed through via premium.
- **At 500 users: ~$30–80/mo AI APIs + ~$25/mo infra ≈ $55–105/mo all-in.**
  Syllabi ≈ 200 unique courses × $0.02 ≈ $4 (parsed once, shared); transcripts
  500 × $0.03 ≈ $15 (personal, no sharing); omnibox $15–30/mo at 20% LLM hit
  rate (rules handle the clean entries — the deterministic parser is the cost
  control); categorization fallback ≈ $10 one-time as the merchant pool fills.
  ≈$0.15/user/mo — the $25/yr premium runs at ~95% gross margin before scale.
  *(Added 2026-10-04.)*
  - **Correction (2026-10-05):** the ~95% is per *paying* user ($0.15 of cost against
    ~$2.08/mo of revenue). Across all users it does not hold: at the 5% conversion in
    §13.16, 500 users bring ~25 × $25/yr ≈ $52/mo against ~$55–105/mo of cost, so the
    free tier's AI spend exceeds premium revenue until conversion rises or B2B
    licensing covers it. The per-user cost figures stand.
- Cost controls, in priority order: cache everything parseable; mini models for
  extraction/classification; deterministic-first (simulators and forecasts never
  touch an LLM); per-feature AI budgets with alerts.
- The risk isn't unit cost — it's *unbounded* LLM use (e.g., a general
  conversational assistant on the free tier). Don't build that. Every LLM call
  must be attributable to a feature with a cost model.

**Use of funds (angel-round framing).** ~60% engineering hires, ~15% AI/infra/legal
(PIPEDA review, terms, security audit before open signup), ~15% campus ambassador
program, ~10% buffer. No paid acquisition — if the team wedge doesn't distribute
the product, money won't fix it.

### 13.18 Infrastructure & storage scaling (added 2026-10-02)

**Growth drivers, in order of bite.** (1) *Analytics events* — the silent killer:
10k users × ~100 events/day = 1M rows/day. (2) *Documents* — syllabi, pay stubs,
T4s, offer letters; small per file, unbounded in count. (3) *Core records* —
transactions, grades, tasks; linear in users, cheap per row. (4) *Backups and
egress* — scale with everything above; egress is the classic surprise bill.

**Design decisions that keep it cheap.**
- Raw analytics events roll up to daily aggregates; raws drop after 30–90 days
  (§14 precompute does double duty here — security pattern *and* storage control).
- Never store blobs in Postgres. Original documents live in cheap object storage
  (GCS/Supabase Storage ~$0.02/GB/mo); only extracted JSON touches the database.
  Keep originals — re-parsing when models improve and "show me the source" trust
  both need them.
- Financial records (transactions, paycheques) keep forever — it's the user's
  ledger. Everything else gets a retention policy.
- Cloud Run scales to zero and Cloudflare Pages is generous; neither is the
  concern. Postgres is.

**Illustrative math at 100k users (labeled estimate).** Postgres ~50–100GB →
Supabase Pro + add-ons or early self-managed ≈ $100–400/mo. Documents: 100k × 20
docs × ~200KB ≈ 400GB ≈ ~$10/mo object storage. Backups + egress ≈ low hundreds.
**Total infra ≈ hundreds/mo, not thousands.**

**Known future decision: Supabase → self-managed Postgres.** Supabase's per-GB
pricing is fine to ~6 figures of users; beyond that, self-managed Postgres
(RDS/AlloyDB/GCE) is cheaper per GB but buys ops burden. Migrate on a cost
trigger (e.g., DB bill > $500/mo sustained), not on principle — the founder's
time is worth more than the savings until then.

**The investor takeaway:** infrastructure is the *smallest* scaling cost by two
orders of magnitude — labor dwarfs it ~100:1. This is not an infra-heavy
business; storage growth is linear, predictable, and modelable per user.

### 13.19 Dream features triage (added 2026-10-02)

**Core principle (new): no stranger discovery.** Account connects you to people
you already know; it never introduces you to people you don't. This kills open
study-group matching and constrains any future matching features to existing
connections or explicit opt-in programs. Besides product focus, it avoids the
moderation and safety costs of becoming a social-discovery company — a different
business entirely.

**Degree audit — approved.** Computed from courses + program requirements: missing
credits, breadth gaps, "cheapest-term path" to graduation. Transfer-aware from
day one (maps transfer credits into the audit) — the founder's own UBCO→UBC path
is the design reference. **Transfer mapping is many-to-many** (two courses → one;
one → three; sometimes partial credit) and resolved from three sources in
priority order: (1) official articulation data (e.g., BC Transfer Guide) plus
admin input; (2) learned/cached mappings from other transfer students' confirmed
audits — the shared-data network effect; (3) **manual override, always
available** — the escape hatch when a mapping is too complicated for any
database. Never trap a transfer student in a wrong automatic mapping; the manual
link is part of the feature, not a fallback.

**Prerequisite graph — approved.** Visual degree map: what unlocks what, where
you are, what's at risk if a course is dropped. Doubles as the onboarding wedge
for transfer and first-year students — the moment the app "understands" their
degree.

**Office-hours radar — approved, open questions.** Mechanism: self-reported
check-ins ("I'm going"); only aggregates shared ("~4 people usually go Tuesdays"),
never identities. Two things to resolve: (1) the value exchange must be explicit
— tell users *why* reporting helps them, not just ask for data; (2) the
prof-facing side is undecided (aggregate demand signals like "12 students wanted
Tuesday hours" are possible, but nothing identifiable, and only with consent).

**Co-op salary transparency — approved, with verification.** Anonymous storage
only, explicit consent per submission. Offers enter the aggregate database only
after corroboration: either the user's later payroll records (pay-stub parse)
match the offer, or multiple independent submissions for the same company/role
converge. Unverified offers never touch aggregates. This is the document-intake
pipeline (§13.12) verifying the salary data — the loop closes itself.

**Club dues — phased.** (1) Member-side now: dues as recurring obligations in the
money room (tiny build, real value). (2) Organizer-side with the clubs module:
who-paid tracking + broadcast reminders. (3) Actually processing payments: far
future or never — a different liability universe (money transmission, disputes).

**Club management — approved, scoped.** Membership, votes/polls, member
broadcasts, and a member-visible shared calendar. Event advertising: proceed
aware, not blocked — AMS contracts govern event promotion at UBC, so navigate
the student-society relationship rather than assuming either free rein or a ban.
(Corrected 2026-10-02: awareness, not a hard constraint.)

**Gym buddy matching — opt-in beta, premium candidate.** Tension flagged: open
matching collides with the no-stranger-discovery principle. Survives only scoped
to existing connections (work out with people you know) or explicit opt-in
programs — not algorithmic introduction to strangers.

**Sleep correlations — far future, and gated on a client that does not exist.**
HealthKit sleep → cross-room engine is approved in principle and sequenced after the
three rooms prove themselves. It inherits §4's condition rather than overriding it:
HealthKit and a native client stay on the not-building list unless push notifications
force a native client anyway, at which point sleep data becomes nearly free. Approved
in principle is not approved in sequence.

**Marketplace — far future.** Campus-scoped buy/sell needs density first; it's a
density-class network play, not a feature.

**Term simulator — approved. Implementation:** not a new model — a composition
layer over the three rooms' existing deterministic engines. Each room exposes a
pure projection function (academic: study hours → grade bands + workload fit;
money: work hours + spending → balance curve + runway; body: workouts → exertion
trajectory vs. goal). The unifying constraint is the **168-hour week**: sleep +
classes + study (from the workload model) + work + workouts + overhead = the
budget; any deficit surfaces as "this term doesn't fit," with the overage
attributed per room. Cross-room interactions are explicit rules, not black
boxes: crunch-week detection (calendar density × historical spending spikes),
exam-week exertion dip proposals. Sliders for courses, work h/week,
workouts/week, spending, sleep; one output dashboard (time fit, money curve,
exertion trajectory, crunch flags). Calibration loop per §13.13:
end of term, simulated vs. actual — the simulator learns per user across terms.

**Grade bands are gated, and this is the §13.5 boundary holding under pressure.**
Moving the work slider reports **time fit only** — "this term needs 182 of your 168
hours, 14 short" — and renders no grade band, because work → study → grade is the
excluded work-study inference whether it takes one step or three. Grade bands appear
only when *study hours are set directly*, which is the student stating the input
rather than the app deriving it from their job. The squeeze is shown; the conclusion
is theirs to draw.

**Morning briefing — approved, two paths.** (1) **BYOAI:** expose an MCP/API
surface serving the deterministic briefing digest to the user's *own* AI
(Claude/ChatGPT, which they already pay for) — premium-feeling prose brief at
zero AI cost to us, and a distribution play into the AI-assistant ecosystem.
(2) In-house generation as a premium feature later. Same auth/RLS as the API;
the digest is computed deterministically either way — only the prose layer
moves.

### 13.20 Unofficial transcript parsing (added 2026-10-04)

**Status (2026-10-05): deferred out of Phase 1.** A transcript carries the student's
name, student number and every grade. Parsing it means sending a personal document to
an LLM provider, and the rule for that is undecided (§10). Syllabi, which are course
documents, go ahead without it.

Consumer #5 of the document-intake layer (§13.12): unofficial transcript → courses
+ grades + transfer credits. **Unofficial, not official** — the student downloads it
themselves in about 30 seconds; no registrar request, no fee, no wait. At UBC that is
the Official Documents tool, reached through Workday Student, which replaced the
Student Service Centre (SSC) (verified 2026-10-05). Self-serve is what makes it viable
as an onboarding flow.

**Why it matters.** One upload at signup backfills years of history the user never
typed — the history-dependent features (velocity, multipliers, distributions) are
starving for exactly this. Transcripts also explicitly mark transfer credits,
making this the cleanest source for the degree audit's many-to-many transfer
mapping (§13.19), and they complete the prerequisite graph.

**Design decisions.**
- Parse → verify → commit, same as every intake consumer. Never auto-accept.
- **The PDF is parsed and discarded, not saved.** General principle for the
  intake layer: *personal documents are parsed and discarded; shared documents
  are kept* (syllabi stay, as provenance behind the shared course catalog). This
  narrows §13.18's "keep originals" to shared documents.
- **Merge, don't duplicate.** Transcripts overlap hand-entered courses — match by
  code + term and let the user confirm merges, or ghost duplicates result.
- **Format variance per school.** Don't build regex templates; LLM extraction
  handles it. Start with UBC's unofficial-transcript layout, generalize with
  campus expansion.
- **Personal records only.** Unofficial = self-reported; output touches the
  user's own courses, grades, and audit — never shared aggregates. No new
  row policy is needed (grades are never shared anyway); the open question is
  the provider rule above, not isolation.

**Sequencing:** after syllabi in the intake pipeline — same machinery, new
document type — and only once the personal-document rule is decided.

### 13.21 LLM provider strategy: universal adapter (added 2026-10-04)

**Principle: never married to a price sheet.** All LLM access goes through one
internal interface with task-named methods (`extract_document`, `parse_entry`,
`classify`, `polish_brief`) — never provider-named. Switching providers or models
is changing env vars (`LLM_PROVIDER`, `LLM_MODEL_EXTRACT`, …), not editing call
sites. Each task declares its needs (JSON schema, max latency, max cost per
call); the adapter routes to whatever is configured.

**Why:** model prices move quarterly, new cheap models appear yearly, and
providers have incidents. The adapter turns "migrate providers" from a rewrite
into a config change plus an eval rerun. The eval gate is a fixed set of golden
documents (nasty syllabus, UBC transcript, blurry pay stub) with expected JSON —
run it before any switch; the no-change confirmation rate (§15) keeps watch in
production.

**Provider comparison (Oct 2026, USD per 1M tokens in/out; prices verified
2026-10-05 against provider and third-party pricing pages):**

| Model | In / Out | Notes |
|---|---|---|
| GPT-5 nano | $0.05 / $0.40 | Mature JSON-schema structured outputs; 400K context |
| Gemini 2.5 Flash-Lite | $0.10 / $0.40 | Free tier for dev/test (see the data rule below) |
| GPT-5 mini | $0.25 / $2.00 | Same structured-output maturity; the default extraction pick; 400K context |
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | 1M context |
| Gemini 3.8 Flash | $0.75 / $3.75 | **Intro pricing — doubles to $1.50 / $7.50 on Jan 1 2027**; 1M context; native PDF handling; thinking tokens bill as output |
| Claude Haiku 4.5 | $1 / $5 | Strong instruction-following; cache reads at 10% of input price (extraction prompts are identical every call); 200K context; batch 50% off |
| Claude Sonnet 5.5 | $2 / $10 | Best instruction-following for messy documents; the escalation tier; 1M context at flat pricing; batch 50% off |
| GPT-5 | $1.25 / $10 | Overkill for these workloads |

**Reliability.** JSON-schema structured output is table stakes at all three labs, and
rate limits are a non-issue at 500 users on any provider. *Correction (2026-10-05):*
the original "99.9% SLA tiers exist on all sides" overstated it. OpenAI's 99.9% is a
Scale Tier / Enterprise contract; Anthropic publishes no standard API SLA; Gemini on
Vertex guarantees 99.5%. At this app's scale every provider is a standard tier with no
uptime guarantee — which is one more argument for the adapter: a provider incident is
a config change, not an outage. The differentiators are economic: Anthropic's prompt
caching, batch APIs at 50% off everywhere (use for non-urgent backfills), and
Google's free tier for development.

**Current routing:** omnibox + categorization → nano-class (GPT-5 nano or
Flash-Lite); document extraction → GPT-5 mini or Gemini 3.8 Flash, escalating to
Haiku/Sonnet only on quality issues; dev → Gemini free tier; batch APIs (50%
off) for non-urgent backfills.

**Rules.**
- Start on Gemini's free tier for development, then pick the cheapest paid option per
  workload — the adapter is what makes "per workload" possible. At 500-user scale the
  cheapest-vs-priciest sensible choice is ≈$50/mo: optimize for reliability and
  discount structure (caching, batch), not sticker price.
- **The free tier is for sample documents only (added 2026-10-05).** Google may use
  free-tier inputs to improve its products, including human review; paid tiers don't.
  No user's document — and nothing from a real account — is ever sent to a free tier.
  This follows from §3.1, not from cost.
- Never build on intro pricing without a migration plan. Gemini 3.8 Flash's doubling
  on Jan 1 2027 is the live example; the adapter is the plan.
- **Data residency — decided 2026-10-05: not pinned during the beta**, revisited before
  open signup with the PIPEDA review. If it becomes required: OpenAI charges a 10%
  uplift for regional processing only on models released on or after March 5, 2026 (not
  GPT-5 nano or mini); Anthropic's US-only inference costs 1.1× and works only on Claude
  4.6 and later — Haiku 4.5 cannot be pinned at all. No inexpensive option offers
  Canadian processing.

## 14. Review — cuts & optimizations (2026-10-02)

A periodic review: what to remove, what to streamline. Re-run quarterly; the
module-adoption measurement (§8) turns these from opinion into evidence once it
exists.

### Cut

1. **Surplus Supabase project — immediately.** *(Done: deleted 2026-10-04.)* The restore-drill project
   (`ommqbgaasrusrlizzyzm`) holds a full copy of every user's financial data and
   password hashes. Under §3.1 this is deleted, not left dormant: rotate, verify
   nothing points at it, delete. Cheapest, highest-severity action in the document.
2. **Sinking funds and reminders-as-built.** Zero rows in production. Sinking funds:
   hide behind a flag or delete outright. Reminders are worse than unused — they
   promise something the app cannot do (they don't fire while closed). Rebuild on
   the Phase 0 scheduler + push, or cut. A broken promise is worse than a missing
   feature.
3. **Monthly category override — kept, and extended.** Two rows, shipped 2026-09-25,
   which is thin adoption. The earlier proposal to collapse it is **withdrawn**
   (2026-10-02): the deadline spending guard (§13.5) writes a per-week override on the
   same primitive, so the stack becomes targets → limits → monthly → weekly. Four tiers
   of one concept is a real risk, so the guard is what has to justify the depth — if it
   ships and the weekly overrides go unused, collapse the middle tiers then.
4. **Orphan `category_budgets` table.** Two rows from a rolled-back feature. Export
   the rows, drop the table.
5. **Investment-return readings — question, and it cannot be answered yet.** Monthly
   holding-vs-paid-in readings are a nice-to-have in a student budget app. "Check usage"
   needs the Phase 0 analytics, so this waits on them like every other cut decision —
   which is the meta-cut below, stated as a concrete case.

### Optimize

1. **Precompute aggregates nightly.** Budget summaries, distributions, net worth,
   week-load — batch jobs writing to tables instead of per-request aggregation.
   Serves performance *and* the §5.6 isolation pattern (leaderboard reads a
   leaderboard table, never a cross-user join).
2. **Style token migration.** 155 hex literals and 93 `rgba()` values outside the
   token system. One focused pass: shrinks stylesheets, kills inconsistency bugs,
   unblocks light mode later. No feature work attached.
3. **Route audit on Finances.** 48 of 139 routes in one room — audit for CRUD sprawl
   (summary vs. targets vs. limits vs. overrides) before adding any new finance
   endpoint. The room is already the largest maintenance burden.
4. **Automate the deploy runbook.** Backup → schema → API → frontend becomes a
   GitHub Actions workflow. A solo dev's most expensive failures are deploy-order
   mistakes at midnight.
5. **Per-request identity for RLS.** Phase 0's core: row policies let Postgres
   enforce filtering instead of every query carrying the invariant. Correctness
   first, speed second, same change.

### The meta-cut

**Rule: no new feature ships until module adoption is measurable.** The three
zero-row features happened because nothing could have caught them. Analytics is not
a Phase 0 nice-to-have; it is what makes every future cut decision evidence instead
of opinion. Engineering rigor (1,036 tests, rollback runbooks) must be matched with
product rigor (usage data, user research) — building what's satisfying instead of
what's uncertain is how a solo project drifts.

## 15. Feature cost ledger (2026-10-02)

**Organised by subject, not by phase.** §4 owns the sequence, and the 2026-10-02
restructure moved several features between phases; grouping the ledger by subject means
a resequencing does not invalidate it. Each group names the phases its items land in.

Every proposed feature, costed in point form. Cost types: **Build** (solo-dev time,
part-time student pace — the binding constraint on everything), **Marginal**
(running $/mo at scale), **Maintenance** (ongoing burden), **Liability**
(security/compliance work), **Trust** (cost of the feature being wrong),
**Cold start** (density/data needed before useful), **Opportunity** (what doesn't
get built instead). Estimates are rough; the ordering is the point.

### Foundations — Phase 0

**Database-level RLS isolation**
- Build: 1–2 weeks (policy per table, per-request identity plumbing, migration).
- Marginal: ~$0 (Postgres-native).
- Maintenance: low — declarative; but every new table needs a policy (process tax).
- Liability: *negative* — the highest-ROI security spend in the doc; reduces breach risk.
- Trust: failure mode is a cross-user leak — catastrophic; hence the enumerated test below.
- Opportunity: 1–2 weeks of features — but it's the gate for everything shared, so *not* doing it costs the entire roadmap.

**Enumerated two-user route test**
- Build: 3–5 days (139 routes × 2 users).
- Maintenance: runs in CI; each new route adds cases (small permanent tax).
- Opportunity: low — mostly one-time.

**Analytics (event capture + dashboards)**
- Build: 3–5 days.
- Marginal: $0 on free tiers to hundreds of users.
- Opportunity: none — it's the prerequisite for every future decision; not building it costs *all* cut decisions and *all* phase gates.

**Push notifications**
- Build: 1–2 weeks (scheduler + delivery path).
- Marginal: ~$0 (web push via VAPID free; OneSignal-style free tiers).
- Maintenance: medium — delivery debugging, permission UX, token churn.
- Risk: if this forces a native client, cost explodes (see §9.1) — confirm the web-push path first.
- Opportunity: 2 weeks; unlocks reminders, guards, briefings — high leverage per week.

**Onboarding (<5 min time-to-value)**
- Build: ~1 week (guided setup, empty states).
- Maintenance: revisit with every feature added.
- Opportunity: indirect but large — every point of activation drop wastes all acquisition spend.

**Confirm every destructive path** *(P0)*
- Build: 3–5 days (nine call sites, one chosen idiom, cascade warnings on two).
- Liability: *negative* — removes unrecoverable data loss on a single click.
- Trust: the sinking fund currently announces its own cascade and then performs it; that is the kind of thing a user tells other people about.
- Opportunity: low. Days, not weeks, and it closes a §3.1 exposure.

**Click acknowledgement + the (?) sweep** *(P1)*
- Build: ~1 day for `:active` across the shared button classes (covers all 183); the (?) sweep is panel-by-panel and open-ended.
- Maintenance: low — the sweep reduces surface rather than adding it.
- Trust: a product selling foresight should not feel unresponsive at the moment of input.
- Opportunity: the cheapest perceived-quality win in the document.

**Shared tasks & events (group coursework)** *(P2)*
- Build: 1–2 weeks (collaborator join table, invites, policy, the UI on both task and event).
- Liability: *medium-high* — the only place one user gets **write** access to another's row; membership must be owner-writable only, or a collaborator could add themselves to anything.
- Maintenance: medium (invite abuse, orphaned collaborators on account deletion).
- Opportunity: large, and it buys growth — inviting a collaborator is an invitation to the app, triggered by coursework every student already has.

**Rate limiter fix — forwarded-for keying** *(P2 gate)*
- Build: 2–3 days (trust a specific forwarded position from Cloud Run, plus tests that a spoofed header cannot mint keys).
- Liability: *negative*, and it is a **gate**: the throttle is one global budget today, which is survivable invite-only and not survivable with open registration.
- Opportunity: trivial build, blocking a Very-high-impact feature. Among the best ratios here.

**Canvas sync (per-user OAuth)** *(deferred out of P0 — §10)*
- Build: 1–2 weeks (OAuth flow, sync job, conflict handling).
- Marginal: $0.
- Maintenance: medium — UBC quirks, token refresh, API changes.
- Liability: medium — university-system tokens; keep scopes read-only.
- Opportunity: 2 weeks that could go to shared syllabi, which may cover the same ground more cheaply (§10 open question).

### Academic — pipeline in Phase 1, sharing in Phase 3

**Shared courses & syllabi** *(pipeline P1; sharing switches on P3)*
- Build: 2–3 weeks (canonical table, upload flow, LLM pipeline, verification UI, dedupe).
- Marginal: fractions of a cent per syllabus (mini LLM), cached — tens of $/mo at 10k users.
- Maintenance: medium — parse failures, duplicate merges, admin tooling.
- Trust: *high* — a hallucinated weight propagates to *every* student in the course; the verification UI is mandatory, not polish.
- Cold start: must hand-seed popular UBC courses. *(2026-10-05: seeding from the Academic Calendar needs UBC's written consent under its terms of use; until then courses and prerequisites come from users' own syllabi. See Phase 2, `Ideas/overhaul/Phase 2/`.)*
- Opportunity: 3 weeks — but it's the network-effect foundation; highest-leverage Phase 1 item.

**Grade distributions** *(intake P2, aggregate P3)*
- Build: 3–5 days (aggregate job + cohort floor + display).
- Marginal: $0 (precomputed).
- Liability: medium — the cohort floor *is* a privacy mechanism; mis-set it and an "aggregate" discloses an individual.
- Cold start: renders nothing until N contributors per course — dead weight until density.

**Accountability partners** *(P2)*
- Build: ~1 week (sharing model, streaks, invites).
- Maintenance: low-medium (invite spam/abuse).
- Liability: low — completion data only, never grades (decided).
- Opportunity: 1 week for the most proven adherence mechanic available — good ROI.

**Workload forecasting**
- Build: 3–5 days (aggregation over existing estimates + free blocks).
- Marginal: $0. Maintenance: low.
- Opportunity: ~zero — the doc's "cheapest real win."

**Multiple grading schemes**
- Build: ~1 week (scheme tables, rule engine, comparison UI, versioning).
- Maintenance: low-medium (rule edge cases accumulate).
- Trust: medium — wrong projection misleads; the show-your-work UI is the mitigation.

**Surfacing existing projections**
- Build: days (presentation, not engineering). Opportunity: ~zero — pure win.

### The coach — Phase 4

**Weekly planner (constraint scheduling)**
- Build: 1–2 weeks (algorithm, UI, explanations).
- Marginal: $0 (deterministic — an LLM would be worse *and* pricier).
- Maintenance: low-medium (scheduling edge cases).
- Trust: medium — a visibly dumb schedule kills confidence; explainability ("Thursday because Friday is full") is the mitigation.

**Deadline risk prediction**
- Build: 3–5 days (velocity arithmetic + UI). Marginal: $0.
- Cold start: needs ~1 term of personal history before velocity is meaningful.

**Focus sessions / exam countdown / briefings**
- Build: ~1 week / 3–5 days / ~1 week (briefings need the Phase 0 scheduler).
- Marginal: $0 (templates; optional LLM polish later = pennies).
- Maintenance: low.

**Cross-room correlations, non-financial** *(P4 — needs body data from P3)*
- Build: ~1 week (correlation jobs + UI). Marginal: $0.
- Cold start: longest in the doc — needs weeks of *both* datasets.
- Trust: medium — spurious correlations need sample sizes shown, or "ice cream causes grades" erodes credibility.

### Body room — team sport in Phase 2, exertion in Phase 3

**Exertion score + Strava/Fitbit OAuth** *(P3)*
- Build: 2–3 weeks (two OAuth flows, ingestion jobs, scoring model, leaderboard).
- Marginal: $0–low (free API tiers).
- Maintenance: *high* — fitness APIs change faster than anything else here (§9.3); token refresh; two providers' quirks, forever.
- Liability: medium — health-adjacent data; consent per §9.2.
- Trust: *high* — the activity-conversion model *is* the product; if cyclists feel cheated, the leaderboard dies on day one.
- Opportunity: 3 weeks build + permanent API babysitting — the most maintenance-heavy feature proposed. Price that in.

**Team sport / intramurals** *(P2 — the acquisition loop)*
- Build: 2–3 weeks (teams, leagues, games, stats, invites, standings).
- Maintenance: medium — disputes need the teammate-confirmation flow from v1.
- Cold start: needs 5+ active teams to feel alive.
- Opportunity: large — but it's the distribution wedge (each team = 5–10 users), so the cost buys growth, not just a feature.

**Campus/city leaderboards** *(P3)*
- Build: ~1 week on top of exertion (aggregates + rank UI).
- Liability: medium — opt-in required; disclosure by design.
- Maintenance: gaming disputes scale with competitiveness — budget moderation time.

### Opening up — signup in Phase 2, density features in Phase 3

**Open signup** *(P2)*
- Build: 1–2 weeks (rate limits, email verification, abuse detection, removal path).
- Maintenance: *ongoing and unbounded* — an operational commitment, not a feature.
- Liability: *high* — the allowlist was doing security work silently; open signup multiplies attack surface.
- Opportunity: gates every density-dependent feature — but the cost is permanent ops load on a solo dev. The most underestimated line item in the roadmap.

**Crowdsourced course intel** *(P3)*
- Build: ~1 week. Marginal: $0. Maintenance: low.
- Cold start: needs contributors per course.

**Open league directory** *(P3)*
- Build: 1–2 weeks (browse/search/filter, trust signals, dormancy logic).
- Maintenance: medium — spam, duplicates, dead leagues need ongoing attention.
- Cold start: *do not launch empty* — an empty directory actively harms momentum.

### Money room — single-user core in Phase 1, history-dependent in Phase 4

**Omnibox AI entry**
- Build: 3–5 days. Marginal: fractions of a cent per transaction — tens of $/mo at 10k users.
- Maintenance: low.

**CSV import + recurring detection**
- Build: ~1 week (parser, preview, dedupe, detection).
- Marginal: $0.
- Maintenance: low-medium — bank CSV formats vary and drift.
- Trust: medium — a bad import corrupts the ledger; preview-before-commit is mandatory, not nice.

**Plaid bank sync (paid tier)** *(P4 — after retention proves)*
- Build: 1–2 weeks (Link flow, token storage, sync job, webhooks, normalization).
- Marginal: pay-as-you-go per connected account — passed through as the ~$8/mo paid tier.
- Maintenance: medium — screen-scraping breakage per bank (Canada, §9.3).
- Liability: *high* — token storage (encrypted at rest, KMS, never logged), PIPEDA, breach severity. The largest liability step in the roadmap.
- Opportunity: only after the money room proves retention on Layers 1–2; buying this liability early is pure cost.

**Cash-flow forecast / runway / merchant run-rate / safe-to-spend**
- Build: 1–2 weeks total (all deterministic over existing data). Marginal: $0. Maintenance: low.
- Trust: medium — a wrong forecast misleads real financial decisions; always show assumptions.

**Annual planner + hours-to-goal solver**
- Build: 1–2 weeks (composition UI + solver + scenarios). Marginal: $0. Maintenance: low.

**Deadline spending guard** *(P4 — needs a term of history)*
- Build: ~1 week. Cold start: needs ≥2 crunch weeks of history.
- Trust: medium — framing risk: pre-allocation, not permission; must not normalize overspending.

**What-if simulator (money) + generalized pattern**
- Build: ~1 week for the money version; the shared component amortizes grade/workload/exertion simulators.
- Marginal: $0 (deterministic — the principle paying rent).

**Grade scenarios / course-drop simulator / next-term planner**
- Build: 1–2 weeks total (all on existing engines). Marginal: $0.
- Trust: *high* for course-drop — full-time status, loan, and immigration consequences of a wrong suggestion are severe. Information with disclaimers, never advice.

**End-of-term flow** *(P2 — it is the intake for P3's aggregates)*
- Build: 3–5 days. Maintenance: low.

**Auto-categorization (4 layers + shared map)** *(personal layers P1; shared pool P3)*
- Build: 1–2 weeks. Marginal: ~$0 (LLM only for new merchants, cached forever).
- Maintenance: low-medium (curated rules need upkeep).
- Liability: low — the pool holds world knowledge, zero personal facts (refined silo).

**Jobs improvements (verification, vacation pay, true wage, tax packet, conflicts)**
- Build: 2–3 weeks total. Marginal: $0 (all deterministic).
- Trust: *high* for paycheque verification — cuts both ways (false "you're short" alarms erode trust as fast as missed real ones). Show the math, cite the rule (e.g., BC ESA s.40).

**Document-intake layer**
- Build: 2–3 weeks (pipeline, verification UI, 4 consumers).
- Marginal: fractions of a cent per document.
- Maintenance: medium — format variance across syllabi, offer letters, pay stubs, T4s.
- Trust: high — same hallucination risk as syllabi, now touching pay and tax.
- Opportunity: large build, but amortized across four consumers — the best infrastructure ROI in the doc.

**Self-employed support**
- Build: 1–2 weeks (invoice model, tax awareness, threshold watches).
- Maintenance: low-medium — CRA thresholds and rates change yearly.
- Liability: low-medium — tax *information*, never tax *advice*; disclaimers.

### Cuts — negative cost (§14)

- **Delete surplus Supabase project:** *(done 2026-10-04)* ~1 hour. *Negative* liability — removes breach surface. Do first.
- **Remove sinking funds / reminders-as-built:** ~1 day. Negative maintenance, forever.
- **Drop orphan table:** 1 hour (after exporting 2 rows).
- **Precompute aggregates:** 3–5 days build; negative per-request cost *and* enables the §5.6 security pattern.
- **Style-token migration:** 2–3 days; negative future cost (unblocks light mode, kills inconsistency bugs).
- **Deploy automation:** 2–3 days; negative midnight-deploy-failure risk.

### Reading the ledger

Three patterns worth stating plainly:

1. **Time is the binding constraint, not money.** Almost nothing here has meaningful marginal cost — the deterministic-core principle keeps the API bill near zero at any plausible scale. The costs that matter are solo-dev weeks, permanent maintenance, and liability. Rank features by *weeks-to-build plus years-to-maintain*, not by dollars.
2. **Liability concentrates in three places:** open signup, Plaid token storage, and the RLS/shared-data boundary. Those three deserve disproportionate care relative to their build cost.
3. **Trust cost is the hidden one.** Syllabus parsing, paycheque verification, course-drop simulation, and the cash-flow forecast all share the same failure mode: confidently wrong outputs in high-stakes domains. The mitigations are also the same every time — human confirmation, shown assumptions, disclaimers where consequences are severe. Budget the mitigation as part of the feature, not as polish. **Never auto-accept high-stakes outputs** — the user verifies, and the verification is itself instrumented: every confirmation screen logs accepted-as-is vs. edited, and which fields changed. The **no-change confirmation rate** is the precision proxy — 92% no-change means the extraction is trustworthy; a slide to 70% means something regressed. The edits are the training signal: whichever fields get corrected most get the next round of prompt and rule improvements. This doubles as a feature-health metric for the quarterly review (§14): persistently low no-change rates mark features for rework or cuts.

## 16. Feature Atlas (added 2026-10-02, re-phased with §4)

Every proposed feature in one place, separated by **timeline** (phase), **feasibility**
(High = days–1 week, proven tech; Med = 1–3 weeks or an external dependency; Low =
research-grade or needs density first) and **impact** (Critical = gate or thesis-level;
Very high = growth wedge or jaw-drop demo; High/Med/Low = relative). The last column is
the implementation idea in one line — the mechanism, not the description. Within a phase,
build high-impact × high-feasibility first. Cost detail lives in §15; decisions in §13.

### Phase 0 — safe and measurable

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| DB-level RLS isolation | Med | Critical | Postgres row policies + per-request identity; a forgotten filter fails closed instead of leaking. |
| Enumerated two-user route test | High | High | Walk all 139 routes × 2 users in CI; every new route adds cases. |
| Delete surplus Supabase project | High | Med | **Done 2026-10-04.** Verify nothing points at it, delete; removes breach surface. Negative cost. |
| Analytics | High | Critical | Lightweight event capture; aggregates only, stated out loud. Every gate is unreadable without it. |
| Push notifications + scheduler | Med | High | Web push via VAPID + job scheduler; confirm no native client is forced first. |
| Onboarding (<5 min time-to-value) | High | High | Guided setup; empty states replaced by first value within minutes. |
| Confirm every destructive path | High | High | Nine delete paths have no dialog and two cascade; audit code paths, not buttons. Recoverable actions excluded by design. |

### Phase 1 — worth keeping (valuable at one user)

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| Document-intake pipeline, own syllabus | Med | Critical | Upload → LLM parse → human verification → the term builds itself. The canonical course table moved to Phase 2 as the shared catalogue (2026-10-05); syllabus sharing stays off until P3. |
| Syllabus schedule parsing | Med | High | Same pass extracts exams, weights, due dates; date-TBA finals as placeholders rather than parse failures. |
| Surface existing projections | High | Med | Required-final and cheapest-path moved out of a modal to where students meet them. Presentation, not engineering. |
| Workload forecasting | High | High | Σ(task estimates) vs free blocks from the calendar. Aggregation over built parts — the cheapest real win. |
| Multiple grading schemes | Med | High | Rule engine (drop-lowest, replace-if-higher), versioned, show-your-work UI, from your own verified parse. |
| Degree audit | Med | High | Courses + requirements → missing credits and cheapest-term path. Transfer-aware, many-to-many, manual override always available. |
| Prerequisite graph | Med | High | Visual unlock map from catalog + audit; the transfer and first-year onboarding wedge. |
| Rebuild reminders on the scheduler | High | Med | Zero rows today and they promise what the app cannot do. Rebuild on P0 push, or cut. |
| Omnibox AI entry | High | High | Typed line → parsed transaction → preview → commit. Daily capture layer. |
| CSV import + recurring detection | High | High | Parser + preview-before-commit + dedupe; ≥3 occurrences → recurring candidate; reconcile, never duplicate. |
| Auto-categorization, personal layers | Med | High | Learned merchant map → keyword rules → naive Bayes → LLM for unseen merchants, cached forever. Shared pool waits for P3. |
| Cash-flow forecast / runway / merchant run-rate / safe-to-spend | High | Very high | Deterministic projections over ledger + obligations. Foresight, not another ledger — the room's edge. |
| Annual planner + hours-to-goal solver | Med | High | Compose balances, grants, loans, tuition, salary → running projection; solve backwards into weekly work hours. |
| Paycheque verification + vacation pay | Med | High | Expected vs actual against shifts and BC rules; cite the rule (e.g. BC ESA s.40). |
| Unofficial transcript parsing *(deferred 2026-10-05)* | Med | High | Fifth intake consumer: transcript → courses + grades + transfer credits. Parsed and discarded, never saved; merges against hand-entered courses. Waits on the personal-document provider rule (§13.20). |
| Click acknowledgement (`:active`) | High | Med | One rule on the shared button classes covers all 183 buttons; `:active` appears zero times today. |
| The (?) sweep | High | Med | Move the 128 ambient muted sentences behind `HelpTip`, panel by panel. Text that must be read before acting stays on the page. |

### Phase 2 — worth sharing (the growth loop)

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| Shared tasks & events | Med | Very high | Owner + collaborator join table on tasks and events; group coursework. Triggers on work every student has, and the invite is the growth loop. |
| Team sport / intramurals | Med | Very high | Teams, games, standings; teammate confirmation from v1. **The acquisition loop** — one team ≈ 5–10 users, works at a single team's scale. |
| Rate limiter fix (forwarded-for) | High | High | Gate on open signup: the throttle is one global budget behind Cloud Run. Trust a specific forwarded position; never the raw header. |
| Open signup | Med | Very high | Rate limits, email verification, abuse detection, removal path. P0 isolation is the gate and has already cleared. |
| Accountability partners | High | High | Share streak / weekly completion % with a friend. Needs two users. Completion, never grades. |
| End-of-term flow | High | Med | One post-grades screen: ratings + anonymous grade contribution. The intake P3's aggregates depend on. |
| Shift-vs-exam conflicts | High | Med | Flag shifts overlapping finals or study blocks at log time, not the night before. |
| Tax packet | High | Med | Year-end export: earnings, deductions, per-employer T4 breakdown, tuition amounts. Seasonal and shareable. |

### Phase 3 — density pays (the network features switch on)

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| Shared syllabi switched on | Med | Critical | The P1 pipeline plus P2 cohorts: the second student in a course inherits a verified parse. Only verified parses publish. |
| Grade distributions | High | Med | Precomputed aggregates with a cohort floor; renders only above N contributors, never below. |
| Shared merchant map | Med | High | World-knowledge pool, cohort floor of independent confirmations, precomputed; personal override always wins. Turns a first import from 25% to 80% categorized. |
| Crowdsourced course intel | High | Med | Effort reports → per-course aggregates ("students say 20h"). Collection rode in with P2. |
| Exertion score | Med | High | points = duration × MET × corroboration weight; Strava/Fitbit OAuth; formula versioned, never rewritten. |
| Adaptive exertion goals | High | High | Trailing average × progressive overload, capped; dip proposed for crunch weeks. Always advised, never imposed. |
| Campus / city leaderboards | High | High | Precomputed aggregates; opt-in per feature; disclosure by design. The wedge is *who* you compete with. |
| Open league directory | Med | High | Browse/filter by sport, level, region; dormancy greying, anti-spam. Never launch empty. |
| Club management | Med | High | Membership, votes/polls, broadcasts, member-visible calendar. AMS-aware on advertising, not blocked by it. |
| Office-hours radar | High | Med | Self-reported check-ins → aggregates only; value exchange stated explicitly. |
| Co-op salary transparency | Med | Very high | Anonymous offers, explicit consent, verified by matching payroll records or converging submissions. Unverified never aggregates. |
| Gym buddy (opt-in, scoped) | High | Low-Med | Only within existing connections — no-stranger-discovery rules out open matching. |

### Phase 4 — smart (history pays)

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| Weekly planner | Med | High | Constraint-satisfaction over free blocks; greedy fill, explained choices ("Thursday, because Friday is full"). |
| Deadline risk prediction | High | High | Personal velocity vs required velocity. Division, not machine learning. |
| Proactive briefings | High | High | Deterministic digest on the P0 scheduler; optional LLM polish later. |
| BYOAI briefing API (MCP) | High | Med-High | Serve the deterministic digest to the user's own Claude/ChatGPT. Zero AI cost; a distribution play. |
| Term simulator | Med | Very high | Compose the three rooms' engines over one 168-hour budget. Work hours output **time fit only**; grade bands come solely from directly-set study hours (§13.5, §13.19). |
| Grade scenarios / course-drop / next-term planner | High | High | The simulator pattern on existing engines; course-drop carries full-time-status and immigration disclaimers. |
| Cross-room correlations (non-financial) | High | Med | Exertion vs completion and similar; the §13.3 silo keeps all financial data out. Impossible before P3's exertion data. |
| Deadline spending guard | Med | High | Crunch detection → personal spike prediction → pre-allocate → report card. Silent until 2 crunch weeks exist. |
| What-if simulator (money) | High | High | Sliders on work, spending, wage, one-time buys → baseline vs scenario balance and runway curves. |
| Focus sessions | High | Med | Timer tagged per course → the hours-studied-vs-grade chart. |
| Exam countdown mode | High | Med | Inside 7 days, re-prioritize around the exam. Presentation logic over existing data. |
| Self-employed support | Med | Med | Invoice/client streams, installment awareness, GST/HST threshold watch. Tax information, never advice. |
| Plaid bank sync (premium) | Med | Med | Only after the money room proves retention on hand-entry and CSV. The largest liability step in the roadmap. |

### Deferred and far future

| Feature | Feas. | Impact | Implementation idea |
|---|---|---|---|
| Canvas sync | Med | Med | Per-user OAuth + sync job. Deferred out of P0 — it is neither safety nor sight, and shared syllabi may cover much of the ground more cheaply (§10). |
| Sleep correlations | Med | Low-Med | Inherits §4's condition: only if push forces a native client anyway. |
| Marketplace | Low-Med | High | Campus-scoped buy/sell; needs density plus trust systems. A network play, not a feature. |

### Sequencing logic, in one paragraph

**Safe → sticky → spreadable → dense → smart.** Phase 0 buys safety and sight, and nothing
shared ships without it. Phase 1 makes the app worth keeping for a single user — the
syllabus pipeline pointed at your own term, the money room's foresight, the projections
that already exist but nobody can find — because depth built before anyone arrives is at
least depth that works at one user. Phase 2 exists to grow: teams are the acquisition loop,
open signup removes the ceiling, and accountability partners need exactly two people. Phase
3 is the moment the Phase 1 pipelines meet the Phase 2 population, and every network
feature switches on at once — shared parses, distributions, the merchant map, leaderboards,
the directory. Phase 4 is the coach, which needs a term of history and, for correlations and
the term simulator, all three rooms. The ordering rule throughout: **build the loop before
the depth, and never ship a network feature to an empty network.**
