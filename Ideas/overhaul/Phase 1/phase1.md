# Phase 1 — Worth keeping (single-user depth)

Taken from `account-vision.md`:
- §4 Phase 1
- §5.4
- §7
- §9.4
- §11
- §13.1, §13.3, §13.4, §13.8–§13.13, §13.17, §13.19–§13.21
- §14
- §15 "Academic" and "Money room"
- §16 Phase 1

Brought up to date on 2026-10-05, against the code as it stands after Phase 0, and
revised the same day with the vision's §13.20–§13.21. Decisions are in
`phase1-decisions.md`.
The vision was written on 2026-10-02, and four of its Phase 1 items have since
shipped or largely exist. Section numbers below point back into the vision.

Follows `Ideas/overhaul/template.md`.

---

## What Phase 1 is for

Phase 1 is the phase that **earns the right to invite anyone** (§4). Everything in
it is valuable at one user. It needs no cohort and no sharing, so it can be built
while the user count is still small.

Two rooms carry it, and they run in parallel rather than one behind the other:

- **Academic.** Upload a syllabus and the term builds itself, then the projections
  that already exist get put where a student meets them. This is also where
  Phase 0's deferred onboarding measurement lands (Phase 0 D12): onboarding is
  meant to come from parsing and backfill, not from typing.
- **Money.** The single-user core: capture that doesn't depend on remembering
  (CSV import, categorisation), then the foresight no generic budget app has (a
  cash-flow forecast, runway, an hours-to-goal plan, paycheque verification).

Three rules from the vision apply here directly:

1. **Never auto-accept high-stakes outputs** (§15 "Reading the ledger"). Every
   parse, import and categorisation goes through a confirm-or-edit screen, and
   that screen is instrumented: accepted as-is versus edited, and which fields
   changed. The **no-change rate** is the precision measure.
2. **The financial silo** (§13.3). Personal financial facts never leave the user.
   Money is never compared across users or correlated with grades, even
   anonymised. World knowledge, such as merchant to category, may compound, but
   not until Phase 3.
3. **Verified parses are kept, structured for sharing, and not yet shared**
   (§4). The canonical course table is built here so Phase 3 is a switch, not a
   migration. Sharing stays off. **Moved, 2026-10-05:** the canonical table is
   now Phase 2, Part A (the shared course catalogue, `Ideas/overhaul/Phase 2/`).

---

## Exit criteria: Phase 1 → Phase 2

From §11. All must hold:

- [ ] A syllabus upload builds a term in under five minutes, review included.
      The parse itself has a 60-second design goal (D4). *(This replaces Phase 0's
      deferred time-to-first-value; see Phase 0 D12.)*
- [ ] Weekly retention is at least 40% among the beta.
- [ ] At least 3 users would be "very disappointed" without it.
- [ ] The money room is used weekly without prompting.
- [ ] *(Testable from this phase, per §11)* The universe test: two different
      rooms in one week, with at least one visit unprompted.

**All of them can now be read** from `scripts/usage_report.py` (D38), which
the owner runs read-only against production:

| Criterion | Where in the report |
|---|---|
| Syllabus to term in under five minutes | **SYLLABUS TO TERM**: the median time from read to confirmed, and how many were under five minutes. The read itself, with its 60-second goal, happens before the clock starts. |
| Weekly retention of at least 40% | **WEEKLY**, "back from last week" |
| At least 3 "very disappointed" | **WOULD YOU BE DISAPPOINTED** |
| The money room used weekly without prompting | **WEEKLY**, "money room, unprompted" |
| The universe test | **WEEKLY**, "2+ rooms, one unprompted" |

The same section also shows the no-change rate on the syllabus confirm screen
(§15).

None of these can pass until real people use the app. That is the beta's job,
not code's.

---

## Status at a glance (end of 2026-10-05)

**Live:** both earlier batches, the first since 2026-10-05 (`26db894`) and the
second since 2026-10-06 (`81d099c`), and the review loops since 2026-10-06
(`aaf93c4`, `account-api-00037-9p8`). Decision numbers point to `phase1-decisions.md`.

| # | Item | Status |
|---|---|---|
| 1 | Document-intake pipeline, own syllabus | **Built** (D16). Needs the schema step and a provider key. Courses now carry a section (D22). Keeping the original file is built, in GCS (D24). Adding to an existing course, add-only: **live** (D27, D30). The canonical course table moved to Phase 2, Part A |
| 2 | Surface existing projections | **Shipped** on the course page (D7). The Attention line's "needs X% on the final" is **built** (D13) |
| 3 | Workload forecasting | **Shipped** (D8). The estimate-versus-actual loop: **live** (D35, D36) |
| 4 | Multiple grading schemes | **Built**, additive (D18). Picking a scheme as the grade: **live** (D25, D29). Versioning: not wanted (D26). Projection against result: **live** (D34) |
| 5 | Degree audit and prerequisite graph | **Spike done** (D19). Prerequisites and the shared course table moved to Phase 2, Part A (`Ideas/overhaul/Phase 2/`, planned 2026-10-05); the audit itself, from requirements you enter, is **live** (D31) |
| 6 | Omnibox entry | **Built** (D17): suggests a category. The LLM fallback waits for the adapter's first live use |
| 7 | CSV import and recurring detection | **Built** (D14). Needs the schema step. The "until when?" prompt is **shipped** (D21) |
| 8 | Auto-categorisation, personal layers | **Built** (D15), in the import and the omnibox |
| 9 | Foresight: forecast, runway, run-rate | **Built** (D9). Safe-to-spend-today already existed |
| 10 | Annual planner and hours-to-goal solver | **Live** (D10). Plan versus actual: **live** (D37) |
| 11 | Paycheque verification and vacation pay | **Live** (D11). The second review loop ("were we right?"): offered, not chosen (D32) |
| 12 | Cuts | **Closed:** `category_budgets` kept (D23), then **dropped 2026-10-19** (D23, superseded); sinking funds kept as they are (D28) |
| 13 | Measurement for this phase's gate | **Live** (D12). Every exit number now prints from the usage report (D38) |
| 14 | Unofficial transcript parsing | **Deferred** (D3) |
| — | Click acknowledgement, the (?) sweep, reminders on the scheduler | **Done** before Phase 1 |

---|---|---|
| 1 | Document-intake pipeline, own syllabus (incl. schedule parsing) | Not started. **Critical**, and the largest item |
| 2 | Surface existing projections (required final, cheapest path) | Built, reached through a modal on the course page. Presentation work only |
| 3 | Workload forecasting | **Largely built.** `week-load` already splits booked from estimated minutes, and the dashboard shows it. Remaining: the headline and free-hours comparison |
| 4 | Multiple grading schemes | Not started. Best sourced from item 1 |
| 5 | Degree audit and prerequisite graph | Not started. Needs a programme-requirements data source |
| 6 | Omnibox entry | **Built, deterministically.** Stays rules-first; an LLM handles only what the rules can't parse (D2) |
| 7 | CSV import and recurring detection | Not started. The subscription audit is the same detection engine, applied at intake |
| 8 | Auto-categorisation, personal layers | Not started |
| 9 | Foresight: cash-flow forecast, runway, merchant run-rate, safe-to-spend-today | Safe-to-spend exists (until next pay). The other three are not started |
| 10 | Annual planner and hours-to-goal solver | Not started. Every input already exists as a primitive |
| 11 | Paycheque verification and vacation pay | Not started. Shifts, paycheques and deductions exist |
| 12 | Cuts: sinking funds, `category_budgets` | Not started |
| 13 | Measurement for this phase's gate | Not started |
| 14 | Unofficial transcript parsing | **Deferred** (your call, 2026-10-05) until the personal-document rule is decided (D3) |
| — | Click acknowledgement (`:active`) | **Done** 2026-10-03 |
| — | Explain on demand (the (?) sweep) | **Done** 2026-10-03. "128 sentences" was an overcount; about 20 were real |
| — | Rebuild reminders on the scheduler | **Done in Phase 0**, 2026-10-05: they push with the app closed |

---

## Cross-cutting facts to settle before building

These apply to several items at once, and each is cheaper to decide once than per
feature.

- **The first LLM in the codebase — decided: the universal adapter (§13.21, D2).**
  There is no LLM dependency today. Items 1, 6 and 8 all use one interface with
  task-named methods (`extract_document`, `parse_entry`, `classify`):
  - **Provider and model come from configuration** (`LLM_PROVIDER`,
    `LLM_MODEL_EXTRACT`, …), never from call sites.
  - **Starting routes:**
    - extraction → GPT-5 mini, or Gemini 3.8 Flash (its price doubles on Jan 1 2027)
    - the omnibox and categorisation → nano-class
    - escalation to Claude Haiku 4.5 or Sonnet 5.5 only on quality problems
  - **A golden-document eval set** gates every switch.
  - **Development uses Gemini's free tier, with sample documents only.** Free-tier
    inputs may be used by Google. No user's document ever goes to a free tier.
  - Still to build: each key as a Cloud Run secret, and a per-user rate limit plus
    a monthly spending cap per feature.
  - **What may be sent:** syllabi, which are course documents. For
    categorisation, a never-seen merchant name only (Layer 4). Amounts, balances
    and anything that identifies the user are never sent: data safety and the
    silo both say so. **Personal documents (transcripts, pay stubs, T4s) are not
    sent at all until their rule is decided (D3).**
  - **Region: not pinned during the beta** (D5). Revisit before open signup.
- **Uploaded documents — decided (§13.20): shared documents are kept, personal
  ones are discarded.** A syllabus is kept as provenance behind the parse (§9.4).
  Cloud Run's disk doesn't persist, so that means **object storage**, never blobs
  in Postgres (§13.18). This is new infrastructure: settle the bucket (Supabase
  Storage or GCS), who can read it, and its retention. Syllabi hold no personal
  data, but the bucket still gets the same deliberate access as everything else.
- **The first table that isn't per-user** (moved to Phase 2, Part A, on
  2026-10-05; its policy is planned there). The canonical course table (item 1,
  §5.4) is world knowledge: it holds no `user_id` and no single owner.
  `rls.owner_predicate` **refuses such a table on purpose**, so it can't land by
  accident. It needs a deliberate policy before it exists:
  - who may read it (likely every signed-in user)
  - who may write it (a job, or an admin path; never a request reading other
    users' rows)
  - how a user's course links to it (a nullable `canonical_course_id` on
    courses, per §5.5)

  This is the same isolation boundary §15 lists among the three liability
  hotspots, so it deserves the Phase 0 treatment: a test that proves the
  boundary.
- **Verification instrumentation** (§13.13, §15). Each confirm screen records, per
  confirmation: the feature, accepted as-is or edited, and which fields changed.
  It reports the no-change rate as an aggregate. This is analytics, so it follows
  Phase 0's privacy rule: per-user rows, read only by the owner-run report.
- **Overwritable dates** (§13.8). Parsed dates seed the term; edits and later
  re-checks own it after that. A finals date of "TBA" is a state, not a failure.
- **Every new table goes through row-level security automatically.** `rls.py`
  generates policies from the models, so a new per-user table needs a `user_id` or
  exactly one owning parent. The isolation suite enumerates every new route.
  Neither needs remembering, but both will fail CI if skipped, which is the point.

---

## 1. Document-intake pipeline, pointed at your own syllabus

**What** (§13.8, §13.12). Unstructured document to structured JSON, then human
verification, then a record. Upload a syllabus and the term builds itself:
- assessments and their weights
- dated exams, including finals as date-TBA at UBC
- assignment due dates
- recurring items as one recurrence rule ("quizzes every Friday", with a skip
  for reading week)

The same pipeline later serves offer letters, pay stubs and T4s, which is why the
vision calls it the best infrastructure return in the document.

**The verification screen is the product.** "I found Midterm 1 (20%) on Oct 6,
and Final (30%) with the date TBA…", with edit before confirm. Mismatches surface
in review rather than failing silently:
- "Final has 30% weight but no date found"
- weights that don't sum to 100%

**What one confirmed parse powers:**
- weights → gradebook categories → projection and required final
- dated exams → calendar events → workload, crunch and exam countdown

**Schema edge cases** (§13.8):
- drop rules ("best 3 of 4") use item 4's rule fields
- undated components (participation) get a weight with no event
- week-number schedules resolve against term dates
- partial parses are acceptable

**Built here, switched on in Phase 3:**
- the canonical course table
- `course_lookup.py` widened from one user's courses to a school-scoped list

**Trust cost** (§9.4, §15). A hallucinated weight produces a wrong projection.
Once shared, it would reach everyone in the course, which is why verification is
mandatory, not polish.

**Done when:**
- A real syllabus (start with one of your own) goes from upload to a confirmed
  term in under five minutes.
- The parse itself takes about 60 seconds or less, which is the design goal (D4).
- Nothing becomes a record without confirmation.
- The no-change rate is recorded.
- The syllabus file is kept in object storage as provenance; nothing personal is
  stored.

---

## 2. Surface the projections that already exist

**What** (§4). Required final and cheapest path are built and good, but reached
through `RequiredFinalModal` and `CheapestPath` on the course detail page. Move
them to where a student meets them without looking: the course card, the grades
dashboard, and possibly the dashboard's crunch strip.

**Done when** both numbers are visible without opening anything, and a course
with no final or no target says nothing rather than rendering an empty figure
(your rule: omit a line that only states an absence).

---

## 3. Workload forecasting

**What exists.** `GET /calendar/{user}/week-load` returns booked minutes, split
into work and class, and estimated minutes from task estimates. Dashboard and
`TimeInsights` show it. The vision's "14 hours of estimated work due in the next
7 days" is mostly this.

**What's left:**
- The headline comparison: estimated work against **free** hours (`free-blocks`
  already computes them) — "14 hours due, 9 free hours before then."
- Saying plainly how much of it rests on missing estimates. The schema already
  separates booked from estimated time for exactly this reason.
- The review loop (§13.13): "you estimated 2h, it took 3.5h". Later, and only if
  cheap.

**Done when** the next-seven-days comparison is on the dashboard and says how
much of it is estimated.

---

## 4. Multiple grading schemes

**What** (§7):
- `grading_schemes` per course, and `scheme_components` with rule fields, such as
  "final replaces midterm if higher" or "drop the lowest two quizzes".
- The student's choice is recorded.
- A side-by-side projection under each scheme, with **show the work**.
- Schemes are versioned, because professors change rubrics mid-term.

**Depends on item 1** for affordability: extract every scheme a course offers in
the same parse. It can be built against hand entry first, but the vision prices it
as "from your own verified parse".

**Done when** a course with two schemes shows both projections with an
expandable breakdown, and the existing single-scheme projections still agree
with today's numbers.

---

## 5. Degree audit and prerequisite graph

**What** (§13.19):
- Courses plus programme requirements give missing credits, breadth gaps and a
  cheapest-term path.
- It is transfer-aware from day one, with your own UBCO→UBC path as the design
  reference. Transfer mapping is many-to-many, with manual override always
  available.
- The graph is a visual unlock map: what unlocks what, and what's at risk if a
  course is dropped.

**The unknown that sizes it: requirements data.** Where do programme
requirements and prerequisites come from — the UBC calendar, BC Transfer Guide
articulation data, or manual entry? That decides whether this is two weeks or two
months. Settle it with a spike before committing.

**Done when** your own degree audits correctly against your real transcript,
including the transfer credits.

---

## 6. Omnibox entry

**What exists.** `app/Omnibox` is deterministic. Its tokenizer and a small,
ordered routing rule file a line as a grade, money or a task, through each
module's own service. The vision (§13.1 Layer 1) asks for AI entry: "Spent $12 at
Subway" parsed into a **categorised** transaction.

**Resolved by the vision's cost model** (§13.17, §13.21; D2). The deterministic
parser stays first, and it is the cost control. A nano-class model handles only
the lines the rules can't parse, priced on a 20% hit rate. The category comes
from item 8. So this item is two small changes:
- an LLM fallback behind the adapter for unparsed lines
- the omnibox calling item 8 for the category

Both go behind the same preview-before-commit.

---

## 7. CSV import and recurring-transaction detection

**What** (§13.1 Layer 2, §13.9):
- **Two jobs.** Onboarding backfill (90 days, the magic moment) and a two-minute
  weekly catch-up for what entry missed.
- **Preview before commit, and dedupe.** Match on amount, date and merchant within
  a window, so a backfill never double-counts a hand-entered row.
- **Recurring detection at import.** Payee plus amount plus interval, with three
  or more occurrences. "Amount varies" for utilities.
- **"Until when?"** A recurring rule with no end date projects forever and
  corrupts the forecast (item 9).
- **One detection engine, two triggers.** The existing subscription audit
  already proposes recurring charges from the ledger. Import is the same logic
  at intake.
- **Dedupe against existing rules.** Fill in history, never duplicate a rule.

**Trust cost** (§15). A bad import corrupts the ledger, which is real money data.
Preview before commit is mandatory, and an import must be undoable as one unit.

**Done when:**
- A real CSV from your own bank imports with a preview.
- Re-importing the same file adds nothing.
- An import can be undone completely.
- Recurring candidates are proposed with an end-date prompt.

---

## 8. Auto-categorisation, personal layers

**What** (§13.10), cheapest first:
1. **A learned merchant map, per user.** Every confirmation teaches it.
2. **Curated keyword rules,** global and maintained by you.
3. **Naive Bayes** on the user's own history.
4. **An LLM, only for a merchant never seen before.** The answer is cached into
   layer 1 for good.

**Rules:**
- Below a confidence threshold, ask rather than guess.
- It runs inside the import preview: "85% categorised, confirm the rest."
- **The shared pool is Phase 3.** Nothing in this item reads across users.

**Done when** a re-import of a categorised month categorises most rows without
asking, and every confirmation lands in the user's own map.

---

## 9. Foresight: the money room's edge

**What** (§13.3), all deterministic and single-user:
- **Term cash-flow forecast.** Balance projected across the term from tuition
  instalments, rent, recurring charges and projected shift income. The output is
  a date: "at this pace you go negative in week 9". The highest priority in the
  room.
- **Runway.** "Your savings last until March 14."
- **Merchant run-rate.** "At your current pace, DoorDash costs you $612 this
  term."
- **Safe-to-spend-today.** The existing safe-to-spend, which runs until next pay,
  made daily and obligation-aware: "$42 today, and rent is still covered Friday."

**Trust cost** (§15). A wrong forecast misleads real decisions, so always show
the assumptions behind the number.

**Done when** each figure shows its assumptions, and a test pins each one
against a hand-computed ledger.

---

## 10. Annual planner and hours-to-goal solver

**What** (§13.4). Your own September–April spreadsheet, generated:
- **The running balance builds itself** from primitives that already exist:
  accounts, dated inflows, the jobs pay schedule, tuition payments, recurring
  transactions and budgets. Each fact is entered once, where it lives.
- **Hours-to-goal solver.** It works backwards from the shortfall to weekly
  hours, as scenarios: "8 hrs/wk ends at $2,100; 12 hrs/wk at $4,800."
- **Plan versus actual.** "You're $300 behind plan."

**Done when** it reproduces your spreadsheet's running balance from data already
in the app, and the solver's scenarios agree with a hand calculation.

---

## 11. Paycheque verification and vacation pay

**What** (§13.11):
- **Expected versus actual pay.** It applies BC overtime (1.5× past 8 hours a day
  or 40 a week), stat-holiday eligibility, and vacation pay at 4%, or 6% after
  five years, whether paid per cheque or held.
- **Show the math and cite the rule** (for example, BC ESA s.40): "Your Oct 15
  cheque looks $38 short. Tuesday was 9 hours."

**Trust cost** (§15). It cuts both ways. A false "you're short" erodes trust as
fast as a missed real one. Second review loop: "we said $38 short — were we
right?"

**Done when** it agrees with a hand calculation for your real shifts and cheques,
and every flag names the rule it applied.

---

## 12. Cuts

**Sinking funds** (§14 Cut #2). Zero rows when the vision was written. Re-check
with the usage report's rows-per-table, then hide them behind a flag or delete
them. It is your call, made on the number.

**`category_budgets`** (§14 Cut #4, `next.md`). This is the leftover from a
rolled-back feature. It holds two rows ($41,040 against September 2026 and $70
against October), and nothing reads it. **It is also the one production table
without row-level security.** Phase 0 kept it away from the restricted role and
asked for its anon grant to be revoked.

Dropping it is destructive, so it goes through the runbook:
1. Export its two rows into the decisions log.
2. Take a backup.
3. You run the `DROP`.
4. The schema gate's "no model builds: category_budgets" note then goes away.

**Done when** both are decided on evidence, and production's table count
matches the models.

---

## 13. Measurement for this phase's gate

- **Unprompted visits.** A notification opens the app with a marker, and the
  visit counter records it as prompted. Everything else counts as unprompted.
- **"Very disappointed."** A one-question, in-app, dismissible survey ("How would
  you feel if you could no longer use Account?"), shown once to active users
  after a few weeks. Its results go into the owner-run report as counts only.
- **The no-change rate** per confirm screen (cross-cutting, above).
- **Syllabus to term.** Time from upload to confirmed parse.

**Done when** every Phase 1 exit number prints from the usage report.

---

## 14. Unofficial transcript parsing — DEFERRED (2026-10-05)

**What** (§13.20). This is the intake layer's fifth consumer: an unofficial
transcript becomes courses, grades and transfer credits. One upload backfills
years of history, and it is the cleanest source for the degree audit's transfer
mapping (item 5). At UBC it comes free from the Official Documents tool, through
Workday Student, which replaced the SSC.

**Why it's deferred.** A transcript carries the student's name, student number
and every grade. Parsing it sends a personal document to an LLM provider, and the
rule for that is undecided (D3). The options you were offered:
- paid tiers only
- paid tiers plus zero data retention
- redacting identifiers before sending

**When it comes back.** It is the same machinery as item 1, with a new document
type. The design is already in §13.20: parse, verify, commit; discard the PDF;
merge against hand-entered courses rather than duplicating.

---

## Suggested order

1. **Quick wins and cuts:** item 2 (presentation), item 3's headline, and item
   12's decisions. A few days, and they make the app better immediately.
2. **The remaining cross-cutting work:**
   - the LLM adapter and its golden-document eval set (the provider is decided,
     D2)
   - the object-storage bucket for syllabi
   - the canonical-table policy

   Items 1, 6 and 8 all wait on these.
3. **Item 1, the document-intake pipeline.** This is the phase's critical path
   and its exit criterion, plus item 13's syllabus timing. The academic room
   continues with item 4 off the same parse.
4. **In parallel, the money room's deterministic edge: item 9, then item 10.**
   No LLM, no new data, high impact, and they prove the room's thesis before
   capture gets cheaper.
5. **Capture: item 7, then item 8,** and item 6 resolved by item 8's design.
6. **Item 11**, paycheque verification.
7. **Item 5**, the degree audit and prerequisite graph, after its data spike. It
   is last because its size is unknown, not because it matters less.
8. **Item 13's measurement**, built early enough that the gate can be read when
   the features land. In practice, alongside step 3.

**The trade in this order.** It puts foresight (item 9) ahead of capture (items
7–8), though forecasts are only as good as the ledger behind them. The ledger is
hand-kept today, and forecasting from it is still useful. Building capture first
would delay the room's actual edge by weeks.

---

## Open questions

- **The rule for sending personal documents to an LLM provider** (D3). It
  blocks item 14, and later pay stubs and T4s.
- **The syllabus bucket:** Supabase Storage or GCS, access, and retention
  (cross-cutting, above).
- **Where degree requirements come from** (item 5).
- **The abandon condition** (§10, §12.20). This is still open from Phase 0.
  Every phase has an entry gate and none has an exit.
- **Self-employed support** (§13.12). The vision's priority puts it "after the
  core jobs improvements", and §16 doesn't list it in Phase 1. Treated here as
  out of Phase 1 unless you say otherwise.

## What the vision says that has since moved

- **§4 Phase 1 lists three items that are now done:** reminders on the
  scheduler (Phase 0), click acknowledgement and the (?) sweep (both
  2026-10-03).
- **"128 ambient sentences"** (§4, §16) was an overcount; about 20 were real.
- **"139 routes"** (§14 Optimize #3) is now 146: Phase 0 added push and usage.
- **Workload forecasting** is priced at 3–5 days to build in §15. Most of it
  exists as `week-load`.
