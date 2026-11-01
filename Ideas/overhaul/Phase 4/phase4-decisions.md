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
