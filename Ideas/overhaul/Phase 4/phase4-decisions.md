# Phase 4 — decisions

Written for: you, reviewing what was decided for Phase 4 and why. Each entry
says what was decided, what was rejected, and what it costs. Follows
`Ideas/overhaul/template.md`.

## D1. Phase 4 opens while Phase 3 stays open for its criteria (yours, 2026-10-31)

**What you asked:** check whether Phase 3 is complete, finish it if not, run
every check, then move on to Phase 4.

**What I found:** all 13 Phase 3 items are built and live (Batch 3, `9b5a4bd`,
and the walkthrough fixes, `5baad80`, deployed 2026-10-31). Two things remain,
and no build can close either:
- **The exit criteria need contributors.** A verified parse serving another
  student, distributions above the floor in two courses, a leaderboard running a
  full term, the merchant map lifting first-import categorization above 60%.
- **Strava and Fitbit wait on your app registrations.**

So Phase 3 is complete as far as building goes. It stays open for those
criteria, ticked as they happen, the way Phase 2 was left when Phase 3 opened
(Phase 3 D1).

**What it costs:** three phases open at once (2, 3 and 4), each waiting on use
rather than code. Nothing in Phase 4 needs Phase 3's criteria met: it needs a
term of personal history, which accrues either way.

**Checks before opening:** CI green on all three jobs (backend, backend on
Postgres 17, frontend) at `83f4bc0`, the Phase 3 tip.

## D2. Phase 4 is everything in the vision except Plaid (yours, 2026-10-31)

In scope: CGPA including this term, the weekly planner, deadline risk, focus
sessions, exam countdown, briefings, BYOAI, non-financial correlations, the term
simulator, grade scenarios, course-drop, the next-term planner, the deadline
spending guard, the money what-if, and self-employed support.

**Out:** Plaid bank sync. The vision already gates it on the money room proving
retention on hand entry and CSV (§4, §15: "the largest liability step in the
roadmap"), and nothing has measured that yet.

## D3. What may deploy without asking again (yours, 2026-10-31)

- **Frontend:** free to deploy once its checks pass.
- **Backend that adds no tables and no columns:** may deploy without asking
  again, once every check passes (SQLite, Postgres, frontend, tsc, build).
  Each deploy is verified and recorded in `shipped.md` and `ROLLBACK.md`.
- **Anything with a schema change waits for your schema step.** The deploy
  script never applies schema; the deploy workflow's schema gate refuses a
  deploy whose tables or columns are missing, which is the backstop.

**How, from a cloud session (yours, 2026-10-31).** This session has no `gcloud`
login and no production secrets, and you chose to keep it that way. It doesn't
need them: pushing `ship` runs `deploy-api.yml` in GitHub Actions, which has its
own keyless identity and does the backup, schema gate, smoke test, digest check,
health and CORS. You said yes to deploying no-schema backend changes that way.
**What this session can't do:** read Cloud Run logs, or reach
`account-2a7.pages.dev` (the network policy denies it). So each deploy is
verified by the workflow's own checks and Cloudflare's check on the commit, and
the log read and file-by-file Pages comparison are listed as not done.

*Correction, in place:* I first asked you whether API deploys should wait for
your laptop, because I wrongly said they needed `gcloud`. You answered on that
wrong premise; the question above replaced it.

## D4. BYOAI: off by default, one revocable read-only token, the digest only (yours, 2026-10-31)

- **Off until you turn it on.** No token exists until you make one.
- **The token is stored hashed.** It is shown once, when made, and never again.
  Revoking it deletes the hash, so it stops working at once.
- **Read-only, and it reads only the digest.** It cannot read a course, a
  transaction or anything else by itself; it is not a session token.
- **Two ways in, over the same digest:** a plain API endpoint, and a small MCP
  server that serves the same digest to your own assistant.

## D5. "CGPA including this term" counts a current course at its running average (yours, 2026-10-28)

The official cumulative average and CGPA count only courses with a final grade,
so marks entered during a term never move them, which reads as broken. A second
pair, clearly labelled, sits beside the official one and also counts each
current course **at its running average, the figure the Semester Average already
uses**, with its credits. Not a projected finish. The official pair is
unchanged.

## D6. How "including this term" was built (mine, 2026-10-31; yours to overturn)

- **Exactly the Semester Average's figure.** A current course without a final
  counts at `course_result_grade`, the function the Semester Average already
  calls, so the two can never disagree about a course. A current course that
  already has a final counts once, at the final.
- **The same exclusions as the official pair, and two more.** Transfer credit
  and courses without credits stay out, as now. A past course with no final stays
  out (it already sits in Attention as "no final"), and so does a future course.
  An archived current course counts, because the official average counts archived
  courses too; only credits completed leave them out.
- **Absent rather than repeated.** When no current course has a mark, both
  fields are null and the panel shows nothing extra. It never prints a second
  copy of the official figures under a different label.
- **On the grades page only.** The home dashboard keeps the official pair alone.
  Adding the second pair there is a few lines if you want it.
- **Quieter than the official pair.** Under its own "Including this term"
  heading with a dashed rule above it, in the body colour rather than gold, with
  a "?" that says what it counts.
- **Computed on read.** No table, no column, so it is a D3 deploy.

Evidence: `tests/test_including_this_term.py`, 16 tests, including one that a
mark entered this term moves the new pair and not the official one, and one that
another user's courses never reach it. Five mutations of the rule, each caught:
counting any term without a final, dropping the repeat gate, ignoring the
GPA-scale setting, counting transfer credit, preferring the running average over
a final. `SemesterSummary.test.tsx`, 5 tests, including an older API that sends
neither field. Seen in a browser with seeded data at 1280px and 390px, with the
"?" open; the repo's guard that HelpTip is styled only from `globals.css` caught
my first layout, and the second uses the global `labelWithTip` pattern.

## D7. The planner's events say where they came from, in a new column (yours, 2026-10-31)

**What I asked:** to read "planner used for ≥50% of study blocks", the app has to
know which events the planner made. A marker in the event's notes (no schema),
or a column? **Your answer:** a column, `events.source`, set to `planner` on the
events it makes.

**What it costs:** the planner's "add to calendar" writes that column, so the
planner deploys with the other schema items after your schema step, not under
D3. **Rejected:** a marker in notes, which you'd see on every event it made and
which an edit could erase.

## D8. The digest carries no money (yours, 2026-10-31)

The Today card, the push briefing, the BYOAI endpoint and the MCP route all read
one digest: events, exams, tasks due and overdue, deadline risk, the week's load,
exam countdowns. **No money figure,** so nothing financial leaves the app through
your own assistant, and the money room stays the only place money is shown.
**Rejected:** today's safe-to-spend at the end of the digest.

## D9. The course-drop warning starts below 9 credits a term, as an editable default (yours, 2026-10-31)

Below 9 credits in a term, the course-drop simulator warns that full-time status
may be lost, naming student loans, housing and study permits, and says to check
your own rules. 9 is shown as a default you can change in the simulator, not as
a fact about your situation. **Rejected:** 12, which some loans and awards use;
the warning names that some use a higher figure.

## D10. How grade scenarios were built (mine, 2026-11-01; yours to overturn)

- **The server's engine, never a copy.** The dialog posts the scores and the
  server answers with `project_course`, the function behind the grade band and
  the cheapest path, so a scenario can't disagree with either. A test over 30
  generated courses (random weights, marks, drops, overrides) checks equality.
- **Where:** a "What if…" button on the course page's "Can still finish" band,
  which only shows while something is left to mark.
- **What can be set:** only unmarked, counted assessments. Marked work stays as
  marked ("what if I'd got 90 on the midterm" is a different question, and it
  would blur what the figure means). Dropped work stays out.
- **"Everything else"** starts at the course's grade now, rounded, and covers
  every assessment not set, plus any weighted category with nothing entered yet
  (which the dialog names), exactly as the band counts it.
- **Absurd inputs are refused, not clamped** (§13.6): a score outside 0–100, or
  an assessment that isn't this course's unmarked work, is a 422.
- **Nothing is saved** and the call keeps the page's GET cache, since it writes
  nothing.

Evidence: `tests/test_grade_scenarios.py`, 19 tests; five mutations caught
(accepting any grade id, dropping the percent-to-fraction step, listing dropped
work, ignoring the overrides, letting scores past 100). The first run had one
survivor, listing dropped work, because the fixture's dropped item was also
marked; an unmarked dropped item now catches it. `GradeScenarioModal.test.tsx`,
5 tests, including that only the newest answer lands (mutation caught). Walked
in a browser at 1280px and 390px; the projection matched the hand figure.

## D11. How deadline risk was built (mine, 2026-11-01; yours to overturn)

- **Velocity** is the minutes of work you finished per day over the last 28
  days: each finished task's timed or reported minutes, else its estimate; a
  task with neither counts nothing. A younger history divides by its own length,
  so a new account isn't read as slow.
- **Required velocity** for a due date is the estimated minutes still open on
  everything due by then, overdue work included, over the days left (today
  counted). The estimate ratio scales it only when you've turned it on, as the
  workload forecast does.
- **At risk** means the required pace is above yours **and the day adds
  estimated work of its own.** A day that adds none (an unestimated "Email TA")
  shows no new risk; its shortfall was already named at the earlier deadline. The
  card says "with what's due before it" when earlier work makes up part of one.
- **Cold start** (§13.5): nothing is said until 14 days of history and 5
  finished tasks with a time. Before then the card says how close it is; with no
  finished work at all it says nothing.
- **Horizon:** the next 21 days. **Where:** the Tasks page, under the exam strip.
- **Completion days are the user's own.** `completed_at` is naive UTC; it is
  read in your time zone (the existing `local_completion_date`), so an evening's
  work isn't counted as tomorrow's. Found while walking it.
- **"Risk flags acted on rather than dismissed"** (§11) stays unreadable: the
  card has no dismiss, and recording one would need a table.

Evidence: `tests/test_deadline_risk.py`, 17 tests with hand-worked figures;
eleven mutations caught (both cold-start floors, overdue work, the days-left
count, the ratio only when asked, archived tasks, both user filters, actual
before estimate, the UTC date, flagging days that add nothing).
`DeadlineRiskCard.test.tsx`, 6 tests. Walked in a browser at 1280px and 390px
with 28 days of seeded history.

## D12. How exam countdown was built (mine, 2026-11-01; yours to overturn)

- **Inside 7 days, today included,** of a midterm or final on the calendar, a
  card under the exam strip names it and lists its course's open work: due by
  the exam's day or undated, dated soonest first, then the most important. Up to
  five are listed; the count and the estimated time cover all of them.
- **Work due after the exam stays out.** Walking it showed the course's
  assignment due a fortnight later and the final itself listed under a midterm,
  which isn't exam-week work. It stays in the list below.
- **The main list's order is unchanged.** The countdown sits above it rather
  than re-sorting it, so nothing you've learned about where things are moves.
- **An exam over today has left**, by the exam strip's own rule (past its end,
  else its start; an untimed exam stays the day).
- **Computed on the server**, so the briefing digest (item 6) reads the same
  rule rather than a copy.

Evidence: `tests/test_exam_countdown.py`, 12 tests; seven mutations caught (over
exams kept, any kind an exam, finished work, the user filter, the window a day
short, undated first, work after the exam). The user filter first survived,
because a stranger's task always sits on the stranger's course; a test now puts
a stray row on my course to prove the filter itself. `ExamCountdownCard.test.tsx`,
5 tests. Walked in a browser at both widths.

## D13. The digest and the Today card, and why the push waits (mine, 2026-11-01; yours to overturn)

- **One digest, composed from the services that already answer each part:**
  today's calendar (shifts included as times, never pay), tasks due today, overdue
  work (three named, all counted), the exam countdown (D12), deadline risk once
  it knows your pace (D11), the week's load and today's free time. It renders to
  plain sentences, one line per part, and leaves out any part with nothing in it.
  The same data gives the same words.
- **No money, proved on the queries (D8).** A test captures every SQL statement
  the digest runs and fails if any reads one of the 24 tables that hold money or
  pay; slipping a transactions query into the digest makes it fail.
- **The Today card shows the digest's own lines,** so it can never say something
  the briefing doesn't. It sits at the top of the desktop dashboard. **The phone
  dashboard is unchanged:** your sketch for it was three cards and no greeting,
  and I didn't want to overrule that without asking. One line adds it there.
- **The push briefing waits for the schema step.** The reminder dispatcher finds
  its users on Postgres through a security-definer function, because it runs as
  no one; finding users who asked for a briefing needs one more function of that
  kind, and functions are installed by your schema step. So the opt-in setting
  and the push land with BYOAI, which needs the same kind of function to turn a
  token into a user.

Evidence: `tests/test_digest.py`, 11 tests; five mutations caught (a money query,
both user filters, finished tasks, listing every overdue task). The course-code
lookup first survived, for the same reason as D12's; a stray-row test now holds
it. `TodayCard.test.tsx`, 3 tests. Seen in a browser on the dashboard.

## D14. How the course-drop simulator was built (mine, 2026-11-01; yours to overturn)

- **The grades page's own functions, run twice:** once on your courses, once
  without the one you'd drop. A test checks that "now" equals the grades page.
  Shown: credits this term, the semester average, the official cumulative and
  CGPA, and the pair including this term; rows with nothing on either side are
  left out.
- **Only a course in the current term** has "If I drop it…" (beside Edit Course);
  the route refuses any other with a 422.
- **The full-time line is 9 credits, editable in the dialog (D9).** Under it, the
  first note names student loans and grants, residence and housing,
  scholarships and a study permit's conditions, and says to check each; a second
  says some use 12 credits or 60% of a full load.
- **The refund is a ceiling, not a promise:** the course's gross tuition (its
  credits times the term's recorded rate), with "before the refund deadline
  usually most of it, after it often nothing". With no rate recorded it says no
  refund can be estimated rather than showing $0. Academic to money only, so the
  silo holds (§13.6).
- **The W:** a note that a withdrawal after the deadline can stay on a
  transcript.
- **Information, not advice,** said in the dialog. Nothing is written.
- **Found while walking it:** the full-time field had no visible box, the same
  fault as the team fields in Phase 3. It now draws one.

Evidence: `tests/test_drop_preview.py`, 12 tests; six mutations caught (past
courses allowed, the course kept in "after", the full-time comparison, archived
credits, the 12-credit note, a refund claimed with no rate). The archived-credits
guard first survived because no archived course was in the fixture; one is now.
`DropPreviewModal.test.tsx`, 5 tests. Walked in a browser at both widths.

## D15. How the next-term planner was built (mine, 2026-11-01; yours to overturn)

- **Its own page,** "Plan next term", beside "Degree audit" on the grades page.
  Courses are picked from the shared catalogue (the existing search), up to eight.
- **Figures through the floor, exactly as the course page reads them** (Phase 3
  D11): hours, difficulty, clarity and "take again", each only once five people
  answered. The campus is part of the key, so UBCO's CPSC 221 never borrows
  UBCV's figures.
- **The headline is the median weekly hours summed** over the courses that have
  them ("about 20.5 hours a week across 2 of 3 courses"). A course with no figure
  yet is named and left out of the sum, never counted as zero. Mean difficulty
  and total credits sit under it.
- **Professor ratings are a link out, never a fetch** (§13.6): type an
  instructor's name and a RateMyProfessors search link appears. Nothing is sent
  anywhere by the app.
- **Grade distributions aren't in it.** The vision mentions them; a
  distribution per course doesn't add up across a combination the way hours do,
  and each course page already shows its own. Easy to add per row if you want.
- **Nothing is stored;** the plan is gone when you leave the page.

Evidence: `tests/test_next_term.py`, 9 tests (the floor, the campus key, the sum
leaving out what's missing, catalogue-only, no repeats, one to eight).
`NextTermPage.test.tsx`, 3 tests. Walked in a browser at both widths with seeded
catalogue courses and figures.

## D16. How the money what-if was built (mine, 2026-11-01; yours to overturn)

- **The year plan's own inputs, shared rather than copied.** The part of `plan`
  that gathers balances, spending, standing instructions and pay is now
  `plan_inputs`, and the solver's "main hourly job and its deduction rate" is
  `main_hourly_job`; the plan, the solver and the what-if all call them. The
  plan's 46 existing tests pass unchanged, and a test checks that a scenario with
  nothing changed is the plan to the cent.
- **The changes:** hours a week more or fewer at the main job (in a date window
  or the whole plan); a stretch with no shifts at all; a different hourly rate;
  day-to-day spending a month more or less; up to ten one-off purchases. Under
  "What if…" below the year plan; nothing is saved.
- **"Exam season" is offered, not assumed:** the three weeks up to the last final
  on your calendar, as a button that fills the no-shifts stretch. The calendar
  feeds money here; nothing flows back.
- **Caps, said rather than silent** (§13.5): hours can only come off shifts that
  are on the schedule, week by week; spending can't go below $0 a day; dates
  outside the plan, inverted windows, a stretch with one end, and out-of-range
  figures are refused.
- **Where the money lands:** lost shifts come off the cheque each would have been
  on; changed hours land at each week's end (said in the assumptions); a new
  wage scales the main job's upcoming cheques only.
- **The silo, proved:** a test captures every query the what-if runs and fails
  if it reads grades, tasks or any academic table.

Evidence: `tests/test_whatif.py`, 27 tests with hand-worked figures (four lost
shifts cost $370, or $296 after 20% deductions; a $20 wage on $2,590 of cheques
adds $210); eight mutations, six caught. The two that survive are equivalent:
copying the events before changing them (the baseline is already projected), and
skipping salaried shifts (they earn $0 from hours anyway). `WhatIfPanel.test.tsx`,
4 tests. Walked in a browser: exam season plus $100 a month less came to −$70.93,
which is nine $92.50 shifts at the 80% of pay that lands in liquid accounts
against $595 saved.

**Correction, in place (D15):** the next-term page first set its own
`max-width` on an element it shares with `.container`; the repo's page-width
guard caught it after the commit was pushed. The width now sits on an inner
wrapper. I had run only that page's tests before committing; the full suite
runs before every commit from here.

## D17. How the non-financial correlations were built (mine, 2026-11-01; yours to overturn)

- **Two pairs, week by week over the last six months:** exertion points against
  tasks finished, and against minutes of work finished (timed or reported, else
  the estimate, as deadline risk counts them). Both are things the app already
  records with a date; marks have no "earned on" date, so they aren't paired.
- **Silent until eight weeks hold both rooms,** counted from when the later of
  the two began; only complete weeks count, so this week's half-logged figures
  never move it. Before eight, the card says how many weeks so far; with nothing
  in either room it says nothing.
- **Pearson's r, in words:** under 0.2 "no clear link", then weak, moderate,
  strong, always with the number of weeks. A side that never changes reads as no
  clear link rather than dividing by zero.
- **Never a cause.** The sentence says what tended to go together, and the card
  ends with "weeks that move together aren't proof that one causes the other".
- **No money, proved on the queries** (§13.3), the same capture test as the
  digest's.
- **Where:** the Fitness page, beside the activity card it reads, with a small
  scatter of the weeks.

Evidence: `tests/test_correlations.py`, 20 tests (r by hand on known series, the
strength bands at their edges, the eight-week floor, one room alone, the later
start, this week left out, a flat side, the money capture, a stranger's weeks);
six mutations, all caught. `CorrelationsCard.test.tsx`, 3 tests. Walked in a
browser with twelve seeded weeks.

## D18. How the term simulator was built, and what "grade bands" became (mine, 2026-11-01; yours to overturn)

- **A composition, not a model** (§13.19). Sliders for sleep, classes, study,
  work, workouts (how many, how long), everything else a day, and spending. They
  start from your own figures: classes, tasks' estimates and scheduled shifts over
  the next four weeks, workouts over the last four, 8 hours' sleep and 3 hours of
  everything else.
- **The 168-hour week,** per room: classes and study, work, workouts, sleep and
  everything else. "Fits, with 58.5 hours spare" or "Needs 179 of your 168 hours:
  11 short", with a bar and each room's hours.
- **Money** is the what-if (D16) with the work slider's change from your
  scheduled hours and the spending slider, so the two can't disagree.
- **Exertion** prices the workouts at the effort of what you've logged lately
  (a moderate effort with nothing logged), against your weekly goal.
- **The boundary** (§13.5, §13.19): the work slider moves time and money only.
  Nothing academic shows until you tick "Set my study hours", and nothing in that
  part reads the work hours. A test moves work from 0 to 60 hours and checks the
  academic part is identical; a mutation that leaks work into it is caught.
- **What "grade bands from study hours" became.** No honest deterministic model
  turns hours into a grade, and inventing one (say, sliding from the worst to the
  best case by hours) would be a made-up prediction in a confident font. So the
  study part says **what your hours cover**: "6 hours covers 75% of the 8 your
  tasks are estimated at: about 2 hours short each week", beside each current
  course's band as it stands ("CPSC 310: 40–90, now 80"), which the simulator
  never moves. **This is the decision most worth your review**: if you want an
  actual projected band, it needs a rule you're willing to stand behind, and the
  calibration loop (§13.13) to check it against real terms.
- **Not built:** saved simulations and the calibration loop (simulated against
  actual at term's end). Both need a table, and a term of use first.
- **Where:** "Plan the term" at the top of the calendar (which is in the phone
  navigation), at `/term`.
- **Found while walking it:** the 168-hour bar didn't draw, because the app
  already had a global `.termBar` from the term budget. Every class on the page
  is now prefixed `termSim`.

Evidence: `tests/test_term_simulator.py`, 16 tests (the boundary across four
work values, nothing academic unset, the 168 by room by hand, a week that doesn't
fit, defaults from the weeks ahead, coverage both ways, bands unmoved, exertion
at your effort and at the default, spending touching only money); six mutations,
all caught. `TermPage.test.tsx`, 3 tests. Walked in a browser at both widths.

**Correction, in place (D15):** the next-term route's "foreign references" case
in the isolation walk never got past validation, because it sent a made-up
catalogue id; the walk now names the shared catalogue row, as the catalogue-link
route's case does. CI on `8b14236` will show the failure; this commit fixes it.

## D19. The spending guard's detection half, and its threshold (mine, 2026-11-01; yours to overturn)

- **Built now, without a schema step:** crunch detection, your own spikes, and
  the timing. **Waiting for the schema step:** the one-tap pre-allocation (a
  per-week override of a category limit), the report card that reads it, and
  "three dismissals stop a category", which needs the dismissals remembered.
- **A week's load** uses the workload model's own weights (final 5, midterm 3,
  deadline 1, task due 1), counting tasks due **whether done or not**, so a past
  week reads as heavy as it was rather than as light as its finished list.
- **A crunch week** carries at least 5 and at least twice your median week.
  *Correction, in place:* I first used twice the median of your **busy** weeks;
  a test showed that a student whose only busy weeks are exam weeks then never
  gets a crunch week at all. The median now runs over every week.
- **A spike** is your own crunch-week average above 1.5 times your other weeks'
  average, over at least 3 crunch weeks, and at least $5 more (§13.5's rule plus
  a floor so $8 against $3 isn't news). Uncounted accounts are left out, as in
  every money figure.
- **Silent until two crunch weeks** are in the history (§13.5); before three,
  it can speak but names no category, so in practice it says nothing until the
  third.
- **When:** the week before a crunch week (one to seven days ahead), never
  during it. The vision says 5–7 days for a push; on the page it shows the whole
  week before, so it isn't missed by not opening the app on those three days.
- **Where and how it reads:** the Budget page, under safe-to-spend: "A heavy week
  from Mon, Nov 2. 2 exams and 5 tasks. In weeks like that, you've spent more on:
  Delivery, about $85 a week against $38 usually (2.2× over 3 crunch weeks)",
  with "a heads-up, not a licence". Calendar into money only.

Evidence: `tests/test_spending_guard.py`, 15 tests; eight mutations, seven caught.
The survivor is equivalent: the seven-day lead check, since only next week is
ever examined. The other-user filter first survived because a stranger's
spending sits in their own categories; a stray row naming my category now holds
it. `SpendingGuardCard.test.tsx`, 5 tests. Walked in a browser with twelve
seeded weeks.

## D20. How BYOAI was built (mine, under your D4; 2026-11-01; yours to overturn)

- **A table and a definer function, so a schema step.** `assistant_tokens`
  (per user, one row at most: the token's SHA-256, a 12-character prefix to
  recognise it by, when it was made and last used) and
  `account_assistant_token_user(text)`, which finds a token's owner by its hash
  before anyone is identified and answers with nothing else. Row security
  classifies the table as per-user from its metadata; the function is granted to
  the API's role only, and a test proves another role (Supabase's `anon` grant
  modelled) is refused.
- **Your rules (D4), as built:** off until made ("Let my assistant read my
  briefing" in Settings, under notifications); the token is shown once with a
  Copy button and where to point an assistant; only its hash is stored; making a
  new one replaces the old; "Turn off" deletes the row, so the token stops at
  once; a deleted account's token is dead.
- **It reads the digest and nothing else.** Two doors over the same digest:
  `GET /api/assistant/digest`, and `POST /api/assistant/mcp`, a small stateless
  MCP server (JSON-RPC: `initialize`, `ping`, `tools/list`, and one tool,
  `get_briefing`). A GET there is answered 405, as the MCP transport expects of a
  server with no stream.
- **The boundaries, each tested:** the token is refused at **every** other route
  in the app (enumerated: every route, every method, the owner's id in the path);
  a session token is refused at the assistant routes; anything that isn't
  `Bearer acct_…` of a sane length is refused **before** the database is asked;
  a browser page from an origin the API doesn't serve is refused (the MCP
  transport's guard against a page acting on someone's behalf); 30 failures from
  one address in the window are throttled.
- **The walks:** the table is in the isolation world; the assistant routes are
  walked as own-reads with A's assistant token (a new `ASSISTANT` set beside
  `PUBLIC` and `SELF`), including the MCP tool call; the noninterference walk
  masks the random prefix, as it already masked random tokens.

Evidence: `tests/test_assistant.py`, 31 tests; fourteen mutations, all caught
after three pre-lookup filters first survived (the lookup would have refused
those values anyway; the tests now prove garbage never reaches it). On a local
Postgres 16: the RLS suite and these tests pass, 826. Walked in a browser: a
token made in Settings, then read the digest directly and over MCP with curl; a
session token was refused there and the assistant token refused at a grades
route.

## D21. The briefing push, and why it adds a column (mine, 2026-11-01; yours to overturn)

- **At an hour you pick, once a day, on devices with notifications on.**
  "Daily briefing" in Settings: Off, or 5am to noon, or 5pm to 9pm. The push is
  the Today card's lines: the date as the title, the first three lines as the
  body, opening the dashboard.
- **No new scheduler job.** It runs inside the existing reminder dispatch, every
  five minutes, and the run's result now counts briefings.
- **Once a day needs remembering,** so `users.briefing_sent_on` (a nullable
  date, written only by the dispatcher). I chose a column over a key in your
  preferences because the preferences are yours to edit, and a server-written
  date there could be overwritten by a settings save.
- **Who to brief** comes from a second definer function,
  `account_users_with_briefing()`, because the dispatcher runs as no one; each
  user's hour is checked on their own clock.
- **Grace:** a missed run still sends within three hours of the chosen hour;
  after that the day's briefing is skipped as stale. A failed delivery isn't
  marked sent, so the next run tries again.
- **The hour has its own route,** `PUT /api/briefing/{user_id}/schedule`,
  because the preferences patch treats null as "no opinion" and could never turn
  it off (the same reason as the exertion goal).

Evidence: `tests/test_briefing_push.py`, 12 tests (the hour, once a day, grace
and staleness, off, no device, a failed delivery retried, push not set up, two
people due at once each getting only their own day, the lookup itself, the
route); five mutations, all caught after the lookup's filter first survived (the
dispatcher re-checks it; a direct test now holds it).

## D22. How the weekly planner was built (mine, under your D7; 2026-11-01; yours to overturn)

- **Two columns on `events`, so a schema step:** `source` ("planner" on the
  blocks it makes, D7) and `planned_task_id`, the task a block is for, with no
  foreign key, because the block is your calendar's and stays if the task goes.
  The second column is mine: without it a second plan would plan the same task
  again in the time left over.
- **"Plan my week" on the Tasks page.** Tasks due in the next seven days, and any
  overdue, sorted by due date and then priority, placed greedily into the free
  blocks the calendar already finds (inside your study window, never over an
  event). Each block says why: "The first free time before it's due Wednesday",
  "Tomorrow, because the free time before it went to work due sooner", "It's
  overdue, so the first free time". What doesn't fit is listed with the
  shortfall, never squeezed in.
- **The sizes:** a task gets its estimate (scaled by the estimate ratio if you
  turned it on) less time already logged; no estimate gets 60 minutes; a task
  within 15 minutes of done isn't planned. No block runs over two hours, a
  15-minute break separates two blocks of the same task, and no block is shorter
  than your minimum free block (a 10-minute remainder rounds up). Time you've
  already accepted counts toward each task.
- **Accepting re-checks everything:** each block must still be inside free time
  as the calendar stands, inside the week, for one of your open tasks, and not
  overlap another; anything else is refused. Another person's task reads as not
  found (404), as every other route does.
- **Found while building it:** the first version moved to the next free stretch
  after one two-hour chunk instead of filling the rest of the same stretch, so a
  long task due today was reported as not fitting; and the first walk showed a
  ten-minute block. Both fixed, both pinned by tests.

Evidence: `tests/test_planner.py`, 21 tests; twelve mutations, all caught after
the priority one first survived (my test's titles sorted the same way by
alphabet; they now disagree). The isolation walk drives the accept route with
each variant's own task (B's under foreign-refs, now refused as not found);
`_patched` learned list indices for that. `PlannerModal.test.tsx`, 4 tests.
Walked in a browser at both widths.

## D23. How focus sessions were built (mine, 2026-11-01; yours to overturn)

- **A table, so a schema step:** `focus_sessions` (per user: an optional course,
  start, end, minutes). The task timer keeps only a running total, so neither
  hours per course per week nor hours against grades could be read from it (the
  correction already noted in `phase4.md`). Focus time on a deleted course goes
  with the course; deleting the account takes every session.
- **The timer's rules are the task timer's:** one session at a time, so starting
  another stops the first; a session left running past 12 hours was forgotten,
  and stopping it records nothing; only your own courses, else not found.
- **Where:** a Focus card on the Tasks page: pick a course (or none), Start,
  Stop; this week's minutes per course; and once two courses have both focus
  hours and a grade, a small chart of hours this term against each course's
  grade now. Your own courses only; nothing is compared with anyone.

Evidence: `tests/test_focus.py`, 10 tests (also green on Postgres); five
mutations, all caught. The table is in the isolation world, and the walks cover
the three routes. `FocusCard.test.tsx`, 4 tests. The repo's class-collision
guard caught chart classes I'd reused from the Fitness page; they're renamed.
Seen in a browser with a session running.

## D24. Setting money aside for a crunch week, and the report card (mine, 2026-11-01; yours to overturn)

- **A table, so a schema step:** `crunch_allocations` (per user: a category, a
  week's Monday, an amount or nothing, and whether it was waved off). One row per
  category per week; a second tap replaces the first. Deleting a category takes
  its rows; deleting the account takes them all.
- **A mark, not an edit to your plan:** D19 called this "a per-week override of
  a category limit", but your limits are monthly and per account, so a week's
  override has nowhere honest to land. Setting money aside records the amount
  for that week and nothing else; your monthly limits and safe-to-spend don't
  move. A nudge that quietly rewrote your budget would be worse than one that
  doesn't. If you'd rather it moved money, that's a change to the limits model
  and I'd want your say on it first.
- **The buttons:** under each category the guard names, "Set aside $85" (the
  crunch-week average, rounded) and "Not this time". Only your own categories,
  else not found; only this week or next, from its Monday, else refused. The
  amount runs 0 to $10,000.
- **Three weeks of "not this time"** for a category and the guard stops naming
  it (§13.5). Changing your mind within a week replaces that week's tap, so a
  tap then a "Set aside" counts as setting aside.
- **The report card** reads the last finished week you set money aside for:
  "Last crunch week: $85.00 of $90.00 on Delivery, inside what you set aside".
  Spending on accounts you don't count is left out, as in every money figure. A
  week still under way has no card yet. It shows even with no crunch ahead.

Evidence: `tests/test_spending_guard.py`, 21 tests (also green on Postgres);
the new mutations all caught, after one survived until a test pinned that a week
not yet over has no card. The table is in the isolation world, and the walks
drive both new routes with each variant's own category. `SpendingGuardCard.test.tsx`
covers both buttons and the card. Walked in a browser at both widths, before and
after a tap.

## D25. How self-employed support was built (mine, 2026-11-01; yours to overturn)

- **Two tables and a column, so a schema step:** `clients` (a name, archived or
  not) and `invoices` (client, number, what it was for, issued, due, amount,
  paid on); `transactions.business_percent` for business expenses. A client is
  only a name: the app isn't an accounting product, and a client's own details
  are theirs. A client with invoices can be archived, not deleted.
- **Where:** a third tab under Jobs, "Self-employed". Overdue invoices first,
  then the year's figures, the invoices (paid ones behind a button), the CRA
  rules, business expenses, and clients. The tax packet gains a
  self-employment section.
- **Invoices move through their states by their dates:** outstanding, overdue
  once unpaid past due (30 days after issue unless you name a date), paid once
  marked. Numbers are unique per user; the next one is suggested.
- **Marking one paid** asks where the money went: into one account, split by
  income share (as a paycheque is), or nowhere new because it's already in your
  ledger (imported from the bank, say), so nothing is counted twice. The
  deposit is tied to the invoice the way a paycheque's is; marking it unpaid or
  deleting it removes the deposit, and a new amount moves it. Only your own
  accounts, else not found, with nothing changed.
- **Revenue counts by the day you invoiced,** for the year and for the GST/HST
  watch; what was paid that year shows beside it.
- **Business expenses:** an expense's business share, 1 to 100 (a phone used
  for work 40% of the time is 40). Tagged from the Self-employed page, from the
  last 90 days' expenses; income can't be tagged. Counted from every account,
  unlike spending figures, because a business expense is one whichever card
  paid it.
- **CPP:** both halves, 11.9% on net self-employment income above the $3,500
  exemption up to the year's ceiling, then CPP2 at 8% to the second ceiling.
  The gross pay recorded from your jobs that year uses the exemption and the
  ceilings first (its own CPP came off the cheques). Figures for 2024 to 2026
  from the CRA's page; a later year uses 2026's and says so. Part years aren't
  prorated.
- **Instalments: the rule and the dates, no income-tax estimate.** The page
  states the $3,000 rule (this year and either of the two before; $1,800 in
  Quebec) and the four dates, with the next one. It doesn't estimate your income
  tax: that takes your whole return (other income, province, credits), and a
  wrong figure presented as yours is worse than none. *Correction, before
  shipping:* I first meant to show "CPP alone: $X of the $3,000". The CRA's
  test counts tax, not CPP, so that line would have been wrong; it's gone. If
  you want an estimate, it needs a province and a model of the return, and your
  say.
- **GST/HST:** invoiced revenue over the last four calendar quarters, the
  current one to date, against $30,000. Over when the four quarters pass it or
  any one quarter does; approaching from 80% ($24,000). The page notes that
  exempt services (some tutoring) don't count and that ride-share and taxi
  drivers register from the first dollar.
- **The typical month is a range,** never one number: the lower and upper
  quartile of up to six finished months since your first invoice, an empty
  month counting as $0, shown once there are three. It isn't drawn into the
  year plan: a range doesn't fit the plan's one curve, so it sits on the
  Self-employed page for now (`next.md`).
- **Sources cited in the app:** the CRA's CPP rates page, "Who has to pay
  instalments" and "When to register for and start charging the GST/HST".
  This session's network can't reach canada.ca, so I checked the figures
  (2026 ceiling $74,600, second ceiling $85,000; 2025 $71,300 and $81,200) and
  the rules through search results quoting those pages, not by reading them.
  Worth a look against the pages themselves.
- **Not built:** a printable invoice (it would need your address and the
  client's, which the app doesn't keep), and an overdue push (it would need a
  sent-on date per invoice). Both in `next.md`.

- **GST/HST, one test for both of CRA's:** one quarter over $30,000 is always
  the four quarters over it too, since amounts are positive. A mutation showed
  my separate single-quarter check could never change the answer, so it's gone;
  the two rules differ only in when registration takes effect.

Evidence: `tests/test_self_employed.py`, 52 tests (CPP cases worked by hand in
the test's comments), also green on Postgres. 27 mutations of the safety lines
and rules: 21 caught at first; five user filters and the year filter on
payments survived until a test wrote rows past the routes (another user's
invoice on my client, my invoice on theirs, their ledger row in my deposit's
group) and another's paycheque; now all caught, and the sixth survivor is the
GST check above. Both tables, the deposit row and a tagged expense are in the isolation
world, and the walks drive all eleven routes with each variant's own client,
invoice and account. `SelfEmployedPage.test.tsx`, 7 tests. The repo's delete
guard caught a client delete with no confirm dialog; it has one now. Walked in a
browser at both widths, marking an invoice paid into an account.

## D26. What walking every feature found, 2026-11-01 (mine; yours to overturn)

Every Phase 4 item, driven in a browser against a real local API with twelve weeks of
seeded history, at desktop and phone width, and the new doors probed directly. No server
error, no leak. Fixed in this commit, which waits for Batch 4 to go live:
- **Tasks on a phone:** the title sat under Edit, and Delete ran 36px off the screen. This
  predates Phase 4, so it is live today.
- **The term simulator's "Spending a month: 0"** is a change, not your spending. It now
  reads "Change in spending a month: no change", with a sign and a dollar.
- **Correlations:** "finish less tasks" reads "fewer".
- **The digest's at-risk line** said a one-hour reading was "5h 43m short". The shortfall
  counts earlier work, and the line now says so, as the Tasks card does.

Left for you, not changed:
- **The planner has no daily cap.** With 11 hours of work due, it proposed 9.5 hours on one
  Sunday, 12:28pm to 10pm, with two 15-minute breaks. The vision warns a visibly dumb
  schedule kills trust. It also books nothing for an exam itself: it only places tasks.
- **"Set aside $90" moves no money (D24),** yet it sits above a "Set aside" section saying
  "Nothing reserved yet", and its footnote says the week "stays inside your plan".

Not walked end to end: a real push on a phone (needs VAPID keys and a device; tests only).

## D27. Transfers carry a category, 2026-11-03 (yours)

Asked for: "Transfers must have a category too as they are money leaving an account."
Your three answers:
- **Optional, like an expense's.** The picker defaults to "Uncategorised". Older transfers
  stay uncategorised until edited, and repeating and fund transfers still work without one.
- **It counts.** A categorised transfer's outgoing leg counts in that category's spending
  and against an account's limit for it, on the account page and the budget page. The
  receiving leg never counts: it is money arriving.
- **It ships with Batch 4,** built on `phase4`. There's no schema change:
  `transactions.category_id` and `recurring_transactions.category_id` already exist.

Mine, yours to overturn:
- **Both legs hold the category,** kept in step the way the description is, so either row
  shows it and editing either moves both.
- **An uncategorised transfer is in no category row.** Otherwise every top-up from before
  this would pile into "Uncategorised". A categorised one now makes an account's breakdown
  add up to its money out.
- **Left expense-only:**
  - The spending guard, because moving money is not a crunch-week spike.
  - The categoriser's learning and the shared merchant map, so "Chequing to Savings"
    neither trains nor votes.
  - The term budget and the plan review, which already treat transfers as not spending.
  - Sinking-fund contributions, which stay uncategorised.
- **Paying a card from chequing,** if categorised, shows in that category beside the card's
  purchases. The budget page's account totals already count it twice the same way.

Evidence:
- `tests/test_transfer_categories.py`, 18 tests, and a guard test in
  `test_spending_guard.py`.
- `TransferCategory.test.tsx`, 4 tests, covering the record, edit and standing-instruction
  dialogs.
- 13 mutations, all caught. Seven are backend: the partner sync, writing the category on
  create, `amount < 0` and the category guard in both the Python and SQL rules, and the
  recurring hand-off. Six are frontend: each dialog's picker and what it sends.
- Walked in a browser at both widths:
  - A $200 Chequing→Savings transfer as "Savings goal" showed on Chequing's "Where it
    went", which then added up to its money out. It showed on the budget page once and not
    on Savings.
  - Editing the Savings-side leg to Groceries moved both legs.
