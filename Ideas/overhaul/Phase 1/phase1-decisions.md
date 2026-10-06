# Phase 1 — decisions

Written for: you, reviewing what was decided for Phase 1 and why. Each entry says
what was decided, what was rejected, and what it costs. Follows
`Ideas/overhaul/template.md`.

---

## D1. The plan's shape: the template, and the suggested order (yours, 2026-10-05)

- **You confirmed the template's working definition of "large scale"**
  (`template.md`, "When to use it"). When something is borderline, I ask you
  before starting.
- **You confirmed `phase1.md`'s suggested order.** It puts the money room's
  deterministic foresight (items 9 and 10) ahead of capture (CSV import and
  categorisation, items 7 and 8). The trade, as written there: forecasts run on a
  hand-kept ledger for a while, in exchange for reaching the room's actual edge
  weeks sooner.

## D2. LLM provider: a universal adapter, not a provider (from the vision's §13.21)

You answered "which provider?" with the vision's new §13.21: never commit to one.

**What:**
- All LLM calls go through one interface with task-named methods
  (`extract_document`, `parse_entry`, `classify`).
- The provider and model are configuration, not code.
- A golden-document eval set gates every switch.

**Starting routes:**
- extraction → GPT-5 mini, or Gemini 3.8 Flash
- the omnibox and categorisation → nano-class
- escalation to Claude Haiku 4.5 or Sonnet 5.5 on quality problems only

**Development uses Gemini's free tier, with sample documents only.** I added this
rule rather than asking, because it follows from data safety. Google may use
free-tier inputs to improve its products, including human review; paid tiers
don't. So no user's document, and nothing from a real account, ever goes to a
free tier.

**It also settles item 6** (the omnibox). The deterministic parser stays first,
and it is the cost control the vision's 500-user figures assume (a 20% LLM hit
rate). The LLM only handles lines the rules can't parse.

**Verified 2026-10-05** (sources in the vision):
- **Every price in §13.21's table matches.**
- **Gemini 3.8 Flash's intro price doubles on Jan 1 2027,** confirmed. That is
  why GPT-5 mini is the safer default, with the adapter as the migration plan.

**Corrected in the vision:**
- **"99.9% SLA on all sides" was overstated.** OpenAI's 99.9% is Scale Tier or
  Enterprise only. Anthropic publishes no standard SLA. Gemini on Vertex
  guarantees 99.5%. At this scale, no provider guarantees uptime.

## D3. Transcript parsing is deferred out of Phase 1 (yours, 2026-10-05)

A transcript carries the student's name, student number and every grade. Parsing
it means sending a personal document to an LLM provider. You chose to defer the
feature rather than pick a rule now. The options you were offered:
- paid tiers only
- paid tiers plus zero data retention
- redacting identifiers before sending

**Effect:**
- Item 14 waits.
- **Syllabi go ahead.** They are course documents, not personal ones.
- **Pay stubs and T4s will need the same rule** when their turn comes.
- The degree audit (item 5) loses its cleanest source of transfer credits until
  then. It falls back to manual entry and articulation data, which it supports
  anyway.

**Verified:** UBC replaced the Student Service Centre with Workday Student.
Unofficial transcripts come free from UBC's Official Documents tool, reached
through Workday. The vision's "UBC SSC" is corrected.

## D4. Syllabus timing: a five-minute gate, a sixty-second goal (yours, 2026-10-05)

- **The exit criterion stays "upload to confirmed term in under five minutes",**
  review included.
- **60 seconds is the design goal for the parse itself.** It came from the
  original vision.
- **Rejected:** making 60 seconds the gate. Reading the verification screen alone
  can take that long, and the screen is the point.

## D5. No data-residency pinning during the beta (yours, 2026-10-05)

LLM calls use each provider's default global routing. Revisit before open signup
(Phase 2), alongside the PIPEDA review already planned there.

**If it becomes required** (verified 2026-10-05):
- **OpenAI** charges a 10% uplift for regional processing only on models released
  on or after March 5, 2026, so not GPT-5 nano or mini.
- **Anthropic's** US-only inference costs 1.1× and only works on Claude 4.6 and
  later. Haiku 4.5 can't be pinned at all.
- **Canada:** no inexpensive option offers Canadian processing.

The vision's wording implied a flat surcharge everywhere, and is corrected.

## D6. How the updated vision was merged (yours, 2026-10-05)

The file you sent (`account-vision (1).md`) used the phase structure from before the
restructure, plus material dated 2026-10-04. Per your choice, the current structure
and decisions stay, and only the new material was added:
- **§13.20,** transcripts. Marked deferred (D3), with UBC's current transcript
  route.
- **§13.21,** the LLM strategy. Prices verified; SLA and residency claims
  corrected; the free-tier rule added.
- **§13.17's "At 500 users" paragraph,** plus the **margin correction** you
  approved. The "~95% gross margin" holds per *paying* user only. At §13.16's 5%
  conversion, 500 users bring about $52 a month against $55–105 of cost.
- **The Phase 1 atlas row** for transcripts, marked deferred.
- **Smaller changes:**
  - a note in §13.12 that transcripts are a fifth intake consumer
  - the 60-second goal in §11
  - two lines in §10: the open personal-document rule, and the residency
    decision

`account-vision.md` isn't in git, so a copy from before this edit was kept in the
session scratchpad. Ask if you want it restored or committed somewhere.

Also corrected in the conversation, though they appeared only in the first file you
sent (the original vision), not this one:
- **"Canvas cross-checking via automated checks" is wrong.** The only Canvas code
  is a saved link per course.
- **The privacy model `auth.uid() = user_id` doesn't apply.** That is for Supabase
  Auth, which this app doesn't use.

---

## Work log, night of 2026-10-05 (you asked me to carry on alone)

Ground rules I held to all night:
- **Frontend-only changes shipped to `main`** after tests, a production build, CI
  and a byte comparison of the live files.
- **Backend changes stay on the `phase1` branch.** Your standing rule is that
  backend deploys need explicit permission, and "start Phase 1 work" isn't that.
- **No production data was read or written.**

## D7. Item 2: required final sits on the course page; the calculator stays (SHIPPED)

- **The vision's premise was half out of date.** Cheapest path was already a card
  on the course page. Only required final was still behind a button and a form.
- **It is now a card beside the grade band, against the target the course already
  has.** That is the course's own target, or the account default when it has
  none: the same rule the grades page's Attention panel uses (`effective_target`).
  Two pages measuring "below target" two ways would contradict each other.
- **It only shows when the final is still ahead:**
  - a current-term course
  - with a weighted final
  - and no mark on it
  - not a transfer credit or a no-final course

  Anything else, or an answer that hasn't arrived or failed, shows nothing. That
  follows your rules: no placeholder while loading, and no line that only states
  an absence.
- **Kept:** the "Required Final Grade" button and its modal, reached from the
  card's "Try another target". It is still the only way to ask about a past
  course, or about a target other than the course's.
- **Not done, and held for the backend batch:** putting "needs X% on the final"
  into the Attention panel's below-target line. That is a backend change.
- **Tests:** 9, and each guard was mutation-tested (5 of 5 caught).
- **Frontend only,** using the existing `required-final` route. Live as
  `a337307`, byte-identical to a production-URL build.

## D8. Item 3: a rolling next-7-days headline, beside the calendar-week glance (SHIPPED)

- **"Next 7 days: 14h of estimated work, 9h free in your study hours."** It is
  built from the existing `week-load` and `free-blocks` routes, for today plus six
  days.
- **Rolling, not Monday to Sunday.** On a Saturday, "this week" has a day and a
  half left, which is the wrong window for "is there time for what's coming". The
  existing glance keeps its calendar week, so it still agrees with the calendar
  view. I considered switching the whole glance to rolling, and rejected it: it
  would quietly change a figure you already read one way.
- **It says how many tasks have no estimate,** because then the figure is a floor.
  That changes how it should be read, so it stays on the page rather than behind
  a (?).
- **It flags estimated work above free time.** Free time is usable gaps only:
  past time is excluded, and gaps shorter than your minimum block are dropped.
  This is what the backend already counts.
- **Silent** when nothing is due, and when either read fails.
- **Cost:** two extra requests per dashboard load. I accepted that rather than add
  a backend route tonight.
- **Not done:** the estimate-versus-actual loop (§13.13). The plan marks it
  "later, and only if cheap".
- **Tests:** 8, with 5 of 5 mutations caught. Live as `974afaf`, byte-identical.

## D9. Item 9: the forecast, runway and run-rates (BUILT; waiting for your go-ahead)

**Safe-to-spend-today already existed.** The Budget page shows "$X a day" to the
next payday, with standing charges and unmoved sinking-fund money subtracted.
That is the obligation-aware daily figure §13.3 asked for. I built the other
three pieces.

**`GET /finances/{user}/forecast`** gives a daily projection to the end of the
current term, or 16 weeks when the term isn't known. What goes in, each piece
counted once:
- **The starting point:** spending-account balances, the same accounts
  safe-to-spend counts.
- **Standing instructions:** as they touch spending accounts.
  - A transfer to savings counts as money leaving.
  - A transfer between two spending accounts nets to nothing.
  - A split deposit counts at the spending accounts' income share. I nearly
    dropped these, because they name no account.
- **Pay:**
  - Each current job's pay dates, from tomorrow. A cheque due today may already
    be recorded, and counting it again would be the optimism this exists to
    avoid.
  - Hourly jobs are paid for scheduled shifts since the pay date before. The
    first cheque also carries work no cheque has covered yet.
  - Salaried jobs pay their period amount. Contract work isn't predicted.
  - Pay is net of the deduction rate your recorded cheques show, at the
    spending accounts' income share.
- **Day-to-day spending:**
  - The pace is the average of recent one-off expenses from spending accounts,
    over the last 8 weeks or however much history exists. Dividing three weeks
    of spending by 56 would understate it by more than half.
  - Recurring rows and tuition are left out of the pace because they are counted
    elsewhere. In the pace too, rent would be charged twice.

**What it returns:**
- **Headline:** the first day below $0, or the lowest point if it never goes
  below.
- **Runway:** spending, savings and emergency balances divided by the recent net
  outflow, with transfers excluded and rent and tuition included. Investments
  and debt are not liquid.
- **Run-rates:** the top one-off merchants at their pace, from every account
  including cards. "Subway #1234" and "SUBWAY 0042" group together.
- **Every assumption, in words.** The card shows them under "How this is worked
  out".

**Not included, and stated in the assumptions:** tuition instalments not yet
recorded. The app has no schedule of future instalments. You could add them as
standing instructions.

**Tests and mutation results:**
- **22 tests, each figure worked out by hand in a comment.**
- **First mutation run: 14 of 22 caught.**
  - Seven `user_id` filters were missed. The cause was my test world: everything
    in it is dated today, and the forecast reads only history before today. The
    same kind of gap as Phase 0's D10.
  - **Fixed two ways.** A direct test builds everything the forecast reads for a
    second user and requires the answer not to move. The shared non-interference
    world now has past-dated rows for both users, which protects every route
    that reads history. All 141 non-interference cases still pass with the other
    user's history present, so no existing route leaks it.
- **After the fix: 19 of 22 caught.** The three missed are redundant, and leak
  nothing if removed:
  - transfers in runway (their two halves always cancel)
  - the tuition-id user filter (it only excludes ids from your own rows)
  - the runway-account user filter (balances come from a per-user map)
- **The card has 8 tests.**

**Where it is:**
- **Backend:** `08dec4a`. **Frontend card:** `e532e63`, on the Budget page under
  safe-to-spend and net worth. Both on `phase1`, **not deployed**.
- **No schema change,** so deploying is just the API, then the frontend.

## D10. Item 10: the year plan and the hours-to-goal solver (BUILT; waiting for your go-ahead)

**`GET /finances/{user}/plan[?target=&until=]`** is the forecast's engine,
pointed at the vision's question (§13.4):
- **All liquid money:** spending, savings and emergency, matching the
  spreadsheet it replaces. A transfer between them nets to nothing. A transfer
  to investments counts as money out.
- **To the end of the school year:** the Winter term's last day. In spring and
  summer that means the next school year, because a plan ending last April would
  be empty. With no school year set, it runs to the next April 30 and says so.
- **Monthly rows:** money in, money out (standing charges plus the day-to-day
  pace) and the end balance. These are the spreadsheet's rows.

**The solver:**
- **The shortfall becomes weekly extra hours** at your main hourly job: the
  first current hourly job in your own order.
- **What one hour adds:** the job's rate, after the deduction rate your cheques
  show, at the liquid accounts' share of your income split.
- **Rounded up to the half hour.** A shift isn't booked to the minute, and
  rounding down would leave the target just out of reach.
- **Shown as 0/4/8/12/16-hour scenarios,** because students think in "what if I
  pick up a shift" (§13.4).
- **Extra hours are on top of shifts already scheduled,** which the base plan
  already counts.

**Not built:** plan versus actual (§13.4's third part). It needs a saved plan to
compare against: a new table, and a decision about when a plan is "set". I would
rather ask you first.

**Found while building, and fixed in the forecast (`f942221`):**
- Card purchases were invisible to the day-to-day pace. Paying a card off is a
  transfer, which the pace never counts, so a student paying by card had almost
  no spending in either figure.
- Card purchases now count as they happen, as money the spending accounts will
  pay. There is a test, and it fails without the fix.

**Tests:**
- **Planner:** 15 tests, hand-computed. 9 of 11 mutations caught; the two missed
  are redundant:
  - the hourly-only job filter (non-hourly jobs carry no hourly rate)
  - the liquid-accounts user filter (balances come from a per-user map)
- **Mutation testing exposed two masked checks.** The April-30 fallback hid both
  the summer rule and a user-lookup filter, so the tests now also check where the
  date came from.
- **Card:** 7 tests.

**Where it is:** backend `f942221`, card `e099325`, on the Budget page under the
forecast. Both on `phase1`, **not deployed**. No schema change.

## D11. Item 11: paycheque verification, BC overtime and vacation pay (BUILT; waiting for your go-ahead)

**The rules, verified against BC's own pages on 2026-10-05:**
- **Overtime (ESA s.40):**
  - time and a half past 8 hours in a day, up to 12
  - double time past 12
  - time and a half past 40 hours in a week. Only the first 8 hours of a day
    count toward the 40, so daily overtime is never counted twice.
  - A week runs Sunday 00:00 to Saturday midnight.
  - Source: [BC overtime pay](https://www2.gov.bc.ca/gov/content/employment-business/employment-standards-advice/employment-standards/hours/overtime-pay).
- **Vacation pay (s.58):**
  - 4% of wages, 6% from the completion of the fifth year.
  - Overtime counts toward it. Tips don't: gratuities are not wages
    ([s.30.3](https://www2.gov.bc.ca/gov/content/employment-business/employment-standards-advice/employment-standards/forms-resources/igm/esa-part-3-section-30-3)).
  - Source: [s.58](https://www2.gov.bc.ca/gov/content/employment-business/employment-standards-advice/employment-standards/forms-resources/igm/esa-part-7-section-58).
- **Not checked:** statutory holiday pay (s.44-45). Its eligibility test reaches
  outside the pay period. A wrong "you're short" costs as much trust as a missed
  one, so the check says plainly that it doesn't check this.

**How the check decides** (`GET /jobs/{user}/paycheques/{id}/check`):
- **Vacation pay both ways.** The app doesn't know whether your employer pays the
  4% on each cheque or holds it. A cheque matching either expectation matches.
  One between the two says "check the vacation-pay line on the stub".
- **Short is measured against the smaller expectation,** vacation pay held, so a
  "short" flag never depends on that guess.
- **Tolerance:** $1, or 0.5% of the expected amount, whichever is larger. Stubs
  round.
- **Every line shows its working:** hours, rate and amount, with the ESA section
  printed under it.
- **Notes:** shifts that weren't confirmed (scheduled hours used), and weeks
  running past the period edges. Counting only the days inside the period can
  only make the expectation smaller; it can never manufacture a shortfall.

**Why on demand rather than stored:**
- The code deliberately stores each cheque's expected amount "so editing a shift
  months later cannot silently rewrite a verdict already reached". The check
  recomputes from the shifts as they are now, so it only appears when you press
  "Check the math".
- New cheques' stored expectation now includes overtime. Old verdicts are left
  as they were, which is that rule.
- **Vacation pay stays out of the stored expectation,** because the employer's
  choice is unknown. So a cheque that does include it still shows "over" in the
  list, as it did before. The check explains why.

**Tests:**
- **22 tests.** The rules are tested alone, and the check against real shifts and
  cheques, including the vision's own example of a 9-hour Tuesday paid straight
  ($9.25 short).
- **13 of 14 mutations caught.** The one missed is the job lookup's user filter,
  which is redundant: the cheque is already found by your user id, and a cheque
  can only reference your own job.
- **The frontend has 5 tests.**

**Where it is:** backend `39df632`, frontend `c65ffff`. Both on `phase1`, **not
deployed**. No schema change.

**Not built:** the second review loop ("we said $38 short — were we right?",
§13.13). It needs somewhere to store the answer; listed for a later decision.

## D12. Item 13: prompted visits and the Sean Ellis question (BUILT; waiting, and needs the schema step)

**Prompted visits:**
- The service worker opens a notification's page with `?from=push`. The app
  strips that from the address bar, and counts the tab's visits as prompted for
  **30 minutes**.
- **Why a window, not the whole tab:** a tab left open for a week isn't a week
  of prompted use. A whole "session" would over-count prompted use, and nothing
  at all would let the metric manufacture itself (§13.2).
- **Prompted is its own usage kind,** `prompted_visit`, not a flag. The per-day
  counter stays one row per kind, and an unprompted visit later the same day
  still counts.
- **The report's strict universe column** counts people with two or more rooms
  in a week and at least one room by an unprompted visit. Creating something
  counts toward the two rooms but isn't proof of "unprompted", since it could
  happen inside a prompted session.

**The question:**
- **"How would you feel if you could no longer use Account?"** Very, somewhat,
  or not disappointed, plus a quiet "Don't ask again", which is recorded as an
  answer and is final.
- **Asked once, after 7 distinct days of use.** In week one the question has no
  answer yet. Days are counted, not rows: seven rooms on one day is one day.
- **A second answer is refused** (409), not merged.
- **Answers are read only by the owner-run report,** as counts.
- **New table `survey_responses`.** It has a `user_id`, so row-level security
  and the grants apply automatically when the schema runs.

**Compatibility:** each half tolerates the other.
- An old API ignores `prompted`, so those visits count as ordinary ones.
- An old frontend never sends it.
- The question card stays hidden if the survey route returns 404.

**Tests:**
- Backend: 8 survey tests (including another user's use and answers changing
  nothing), a prompted-visit test, and the report test extended. The isolation
  world now holds a survey row.
- Frontend: the visit counter and the card, 11 tests.

**Where it is:** backend `84bc4bc`, frontend `b4bbc77`. Both on `phase1`, **not
deployed**. **This one needs the schema step**: see the runbook.

## D13. Item 2, backend half: the Attention line says what the final needs (BUILT; waiting)

- **On the grades page,** "CPSC 221 — at 70% against an 85% target" now
  continues "; needs 100% on the final", or "; out of reach even with 100% on
  the final".
- **It uses the same effective target and the same required-final arithmetic**
  as the course page's card (D7), so the two never disagree.
- **Silent when the final isn't still ahead:** no final, a final already
  marked, or a transfer credit.
- **No new query.** It is built from the course already loaded, as that
  function's docstring requires.
- **Tests:** 3, with 3 of 3 mutations caught. **Commit:** `fd59fbb`, on
  `phase1`, not deployed. No schema change, and no frontend change: the panel
  renders the message as given.

## D14. Item 7: CSV import with preview, duplicates and undo (BUILT; waiting, and needs the schema step)

**Safety rails, because a bad import corrupts real money data (§15):**
- **The preview writes nothing.**
- **The commit re-parses on the server,** from the same text and column mapping,
  and writes only the line numbers you ticked. A client can't describe rows into
  the ledger.
- **An unreadable line is refused,** and then nothing at all is written.
- **Duplicates start unticked:** same amount, within 3 days, and the same
  merchant or the same day.
  - Each existing row matches at most one imported row, so two coffees in one
    file stay two coffees.
  - Importing the same file twice adds nothing, unless duplicates are ticked on
    purpose.
  - Mutation testing found the amount check untested: without it, any purchase
    that day would hide an imported row. There is a test now.
- **Undo removes exactly that import's rows.** It is one literal statement,
  counted before and after, and refused if the counts differ, as your rule for
  cleanups says. In the app it is confirmed first, and the dialog says how many
  rows go. The delete-confirmation guard now covers it.

**Reading real exports:**
- **Formats:** RBC (description split across two columns), TD (no header, debit
  and credit columns), card exports with compact dates, decimal commas,
  parentheses, and CR/DR suffixes.
- **Date order** (day-first or month-first) is read from the dates themselves. A
  file where every date reads both ways is flagged, and you're asked to check.
- **Card accounts start with amounts inverted.** A card's export shows purchases
  as positive, but here a purchase is an expense.
- **Every guess is shown and editable.** Changing a column re-reads the file.

**Recurring detection needed no new code.** Imported expenses are one-off rows to
the existing subscription audit, which finds repeating charges in the ledger: one
engine, two triggers, as §13.9 asks. The import's result says how many
candidates the audit now sees. **Not built:** §13.9's "until when?" end-date
prompt. It belongs in the subscription confirm dialog and needs your call on the
wording.

**Schema:**
- A new `imports` table, plus `transactions.import_id`.
- `group_id` already carries two meanings and the code warns against a third,
  so this is its own column.
- `ADDED_COLUMNS` now takes a per-dialect type: a UUID column is `CHAR(32)` on
  SQLite and `UUID` on Postgres. A `CHAR(32)` on Postgres would be the wrong type
  for every comparison.
- Deleting an account clears its emptied import records, so they can't hold the
  account in place. Account deletion still refuses while any transaction
  remains.
- An existing integrity test caught a missing index on `imports.account_id`.

**Tests:**
- Backend: 29 tests. 16 of 18 mutations caught; the two missed are user filters
  sitting behind ownership checks already made (redundant).
- Frontend: 11 tests for the dialog and the list.

**Where it is:** backend `d33e34e`, frontend `002814d`. Both on `phase1`, **not
deployed**. **This one needs the schema step**: see the runbook.

## D15. Item 8: category suggestions, the personal layers (BUILT; waiting)

**In the import preview, each expense gets a suggestion, cheapest first (§13.10):**
1. **Your own past choice** for that merchant, when at least 80% of your
   choices for it agree. The ledger *is* the merchant map, so every
   categorisation you make anywhere teaches it. There is nothing extra to
   store.
2. **A short curated list of Canadian merchants,** matched to the category names
   you actually use. For example, Safeway goes to "Groceries" if you have it, or
   "Food". With no matching category, it suggests nothing. The most specific
   rule wins ("uber eats" before "uber"). Contested merchants such as Costco are
   left out on purpose.
3. **Naive Bayes on your own merchant words.** Only with at least 10 categorised
   rows to learn from, and only at 75% confidence or more.
4. **Below the bar, nothing.** "Ask, don't guess."

**Rules:**
- **A suggestion is only a starting point.** The commit applies only the
  categories you kept, only to expenses, and refuses a category that is someone
  else's or archived.
- **Not built:**
  - **Layer 4,** an LLM for never-seen merchants, cached into the map. It waits
    for the adapter.
  - **The shared pool,** which is Phase 3.
  - **The omnibox using these suggestions** (item 6), which is a small change
    best made once you've seen the suggestions on real data.

**Tests:**
- Backend: 14 tests. 12 of 13 mutations caught; the one missed is the history
  user filter, which is redundant (another user's rows carry categories that are
  never in your active set). Mutation testing found the income-row case
  untested; it is tested now.
- Frontend: 2 tests.

**Where it is:** backend `ad0c190`, frontend in the following commit. On
`phase1`, **not deployed**. No schema change of its own.

## D16. Item 1: syllabus intake, the critical path (BUILT; waiting for the schema step and a provider key)

**What it does:**
- **"From a syllabus"** sits beside Add Course on the Grades page. It only
  appears once the server can read one, so it isn't a button that always says
  "not set up".
- **You upload a PDF (or text).** The model reads the course code, name,
  professor and every assessment: category, weight, how many, date, or "date
  TBA" for a UBC final.
- **The verification screen is the product (§13.8).** Every field is editable,
  rows can be added and removed, the server's checks sit on top, and the weights'
  total is live. "Create course" waits for 100% and a name on every row.
- **Confirming builds the course:**
  - weights by category
  - a gradebook row per item, with "10 quizzes" expanding to Quiz 1 to 10
  - exams as calendar events, other work as tasks
  - the given dates on the rows
  - "no final" set when there's no Final

**Safety and trust:**
- **Nothing is written by a parse,** except the parse record itself, which the
  daily cap and the no-change measure need.
- **Applying is validated before anything is written.** Weights must sum to
  100% (bonus aside). The course code must be new. A parse builds one course
  only. If the gradebook fails, the course is removed, so no half-built course
  is ever left behind.
- **Deterministic checks on every parse:**
  - weights not summing to 100
  - a weighted item with no date that isn't marked TBA
  - a date outside the term
  - more than one grading scheme (only the first is read; it says so)
- **The no-change measure is recorded** (§15): fields produced, and fields
  changed before confirming. This is the precision proxy.
- **Only the syllabus and the term's dates are sent to the model.** No name,
  email or id; a test checks this. Unusable entries are dropped rather than
  failing the parse, and unknown categories become Other.
- **Cost controls:** 10 parses per person per day (configurable), and an 8 MB
  file cap.

**The adapter (§13.21, D2):**
- `extract_document` is the only door. OpenAI, Gemini and Anthropic are pure
  request builders and readers, each tested for shape.
- The key is a header, never in the URL, where request logs would keep it.
- A provider refusal reports its status, never its body, which can echo the
  request back.
- **Untested against the live APIs,** because there is no key. The first real
  parse should be watched; the shapes are written from the providers'
  documentation.

**Decisions I made:**
- **The file travels as base64 in JSON,** rather than adding a multipart-upload
  dependency.
- **The original file is not kept yet.** §13.20 says shared documents (syllabi)
  are kept as provenance. That needs the storage bucket you haven't chosen
  (Supabase Storage or GCS), so for now only the extracted JSON is stored.
  Adding the bucket later loses nothing going forward.
- **Courses only, for now.** Applying a parse to an existing course, merging
  into its gradebook, is not built. Overwriting a gradebook someone has been
  keeping is the riskiest thing this could do, so it waits for your call.
- **The canonical course table and widening `course_lookup`** (for Phase 3
  sharing) are not built. They need the non-per-user row policy, which is a
  design decision for you (phase1.md, cross-cutting).

**Tests:**
- Backend: 31 tests, and every mutation tried was caught (18). The test suite
  runs against a fake provider everywhere, so nothing in it can reach a real
  model.
- Frontend: 6 tests.

**Where it is:** backend `b40ebcd`, frontend `3060c43`. On `phase1`, **not
deployed**. Needs the schema step (`syllabus_parses`) and the provider setup in
the runbook.

## D17. Item 6: the omnibox suggests a category, shown before filing (BUILT; waiting)

- **The rules-first parser stays.** It is the cost control the vision's 500-user
  figures assume (§13.17).
- **New:** an expense line that names no category gets one from the import's
  categoriser (D15). "$62.18 safeway" previews as "… · Groceries (suggested)".
- **A category named in the line always wins.**
- **Filing rebuilds the same preview,** so only what was on screen is applied.
- **Not built:** the LLM fallback for lines the rules can't read at all. It
  waits until the adapter has had its first live use (D16).
- **Tests:** 4. 2 of 2 mutations caught: removing "named wins", and removing
  the "(suggested)" label. **Commit:** `414d50f`, backend only. No frontend
  change: the omnibox shows the summary as given.

## D18. Item 4: multiple grading schemes, additive (BUILT; waiting, and needs the schema step)

**The decision that shapes it: the course's own weights stay its grade.**
- A scheme is another reading of the same marks, compared beside the course's
  own figure.
- Nothing about the course average, required final, grade band or dashboard
  changes. Grade arithmetic is where trust is easiest to lose, so the feature
  can't move a number you already rely on.
- **Not built, and needs your call:** "choose upfront" (a chosen scheme becoming
  the course's grade) and "best-of automatic". Both would change the main
  figure.

**What a scheme holds:** per-category weights, plus the vision's rules (§7):
- **Drop the N lowest marks in a category.** By percentage, not points, keeping
  at least one. Marks already excluded by hand aren't dropped twice.
- **"Replaced by, if higher".** The final stands in for the midterm when its
  average is higher. This only applies between two categories that both have
  marks.

**The invariant:** a scheme with the course's own weights and no rules gives
exactly `calculate_current_average`. It is tested over 40 generated courses
(bonus, exclusions, partial marking) and a hand-made course weighted past 100%,
because the random courses didn't reliably reach that case. So a scheme can only
ever differ for a reason it shows.

**The working is shown.** Each scheme opens into its categories: the average
after the rules, how many were dropped, and what counted instead. The higher
scheme is marked.

**Storage:** one table, `grading_schemes`, with the components in a JSON column.
A separate components table would have no single owner with a `user_id`, and
the row-security generator refuses that on purpose. As one row owned by one
course, the policy reads the course's owner, and deleting the course takes its
schemes.

**Caught before it shipped:**
- My first editor rebuilt a scheme's rules from the projection's lines. A rule
  that hasn't applied yet ("drop 2" with one mark) reads as nothing there, so
  an edit would have saved it back as "drop 0".
- The comparison now carries each scheme as written, and the editor starts from
  that. There is a test.

**Not built:** versioning, meaning a professor's mid-term rubric change kept as
history. Schemes are edited in place for now.

**Tests:**
- Backend: 17 tests. 10 of 11 mutations caught; the one missed is cosmetic
  (skipping zero-weight categories).
- Frontend: 6 tests.

**Where it is:** backend `81b0778` and `05be778`, frontend `3d82e28`. On
`phase1`, **not deployed**. Needs the schema step (`grading_schemes`).

## D19. Item 5: the degree audit's data spike (RESEARCHED; not built, needs your call)

phase1.md said to settle where requirements come from before committing, because
that decides whether this is two weeks or two months. Findings, 2026-10-05:

- **UBC publishes no structured prerequisite or degree-requirement data.**
  Community projects snapshot the Academic Calendar's JSON:API and parse
  prerequisites out of the description prose into AND/OR trees
  ([ubc-prereq-visualizer](https://github.com/AsarMichil/ubc-prereq-visualizer)).
  Programme requirements are prose and tables on calendar pages
  ([UBC Calendar](https://vancouver.calendar.ubc.ca/)).
- **The BC Transfer Guide has no public API that I could find.** It is a web
  search tool
  ([BC Transfer Guide, UBC](https://www.bctransferguide.ca/transfer-options/bc-transfer-system/institution/university-of-british-columbia-vancouver/)).
  So transfer mapping starts with manual entry, which the vision already makes
  permanent ("manual override, always available", §13.19).

**What I'd recommend,** cheapest first:
1. **An audit against requirements you enter once.** Your programme's required
   courses and credit buckets, with transfer credits mapped by hand,
   many-to-many. It is deterministic and single-user, works for your own
   UBCO→UBC path, and is about 1–2 weeks.
2. **Then read the calendar's programme pages through the intake adapter**
   (D16), the same pattern as a syllabus: parse, verify, record. The verified
   result is world knowledge, and could be shared in Phase 3.
3. **Prerequisites last,** parsed from course descriptions the same way, for the
   unlock graph.

**Before building step 2 or 3:** check the Calendar's terms of use for automated
reading. I haven't, and wouldn't assume.

**Not built tonight,** because which of these you want, and in what order, is a
product choice.

**Correction, 2026-10-05:** steps 2 and 3 assumed the calendar could be read
once its terms were checked. They are now checked, and UBC requires written
consent to reproduce calendar content. Prerequisites and the shared course table
are now Phase 2, Part A (`Ideas/overhaul/Phase 2/`), built on
users' own syllabi and typing until UBC answers (Phase 2 D2, D6).

## D20. Item 12: the cuts, prepared (NOT RUN; your decision, on evidence)

Both cuts depend on production numbers, and reading production data stays your
call (Phase 0). So nothing here has run.
- **Sinking funds:** run the usage report (Phase 0 runbook, step 7) and look at
  `sinking_funds` in "rows per table". At zero, the vision says hide or delete.
  Deleting code is a change I can make once you say which.
- **`category_budgets`:** the leftover from a rolled-back feature, and the one
  table without row-level security. If you decide to drop it, the runbook has
  the steps, export first. It is destructive, so you run it.

## D21. The subscriptions "until when?" prompt (SHIPPED)

- **§13.9: a recurring rule with no end date projects forever,** and quietly
  corrupts the forecast (D9) and the year plan (D10).
- **Each found subscription now has an optional "Until" date.** It can't be
  earlier than the next expected charge, and it reads "ongoing" until one is
  chosen. It is sent as the rule's `recurrence.until`.
- **Frontend only.** The confirm route already took the date and refuses an end
  before the start; that error shows on the card.
- **Tests:** 3. **Live:** `main` at `c5c6238` (a cherry-pick of `phase1`'s
  `a94ad55`). Byte-identical to a production-URL build, 26 of 26 files. The
  first comparison showed 2 differences while the CDN was still propagating;
  re-fetched, they matched.
- **The cherry-pick means `phase1` needs a rebase before its deploy.** The
  runbook says how.

## D22. Courses carry a section, and Attention asks for it on current courses (yours, 2026-10-05; BUILT, waiting)

**Your words:** syllabi and course schedules are only the same for a section.
Add the section, not mandatory, with a missing one called out in Attention, and
only for current courses, since syllabi change every term.

**What was built:**
- **`courses.section`,** an optional text field of up to 20 characters ("101",
  "L2B", "V01"). It is trimmed, and a blank one is stored as none.
- **Attention: "No section"** on a course in the current term that has none.
  It isn't shown on past or future courses, transfer credits or archived
  courses. It is listed last, after everything that moves a grade.
- **Add and edit course forms** have a "Section (optional)" field. The course
  list shows "Section 101 · Professor" when either is set, and nothing when
  neither is.
- **The syllabus reader asks for the section,** and the check screen shows it,
  editable. Filling in a section the syllabus didn't name doesn't count as a
  correction in the no-change measure: many syllabi serve every section, so
  that is adding what the document never had, not fixing a misreading.

**Caught before it shipped:** in pydantic, assigning a field inside a
validator marks it as sent. Trimming the section that way would have cleared it
on every edit that didn't mention it, such as renaming the course. The trim now
runs only when the section was sent, and a test edits the name and checks the
section survives.

**Not built:** matching courses or syllabi across users by code, term and
section. That is the Phase 3 sharing work, and it needs the canonical course
table's row policy.

**Tests:**
- Backend: 17 new tests. All 6 mutations tried were caught.
- Frontend: 5 new tests. All 3 mutations were caught.
- Full suites: SQLite 1,810 passed; Postgres 2,031 passed; frontend 466 passed.

**Schema:** `ALTER TABLE courses ADD COLUMN section VARCHAR`, in the runbook's
step 0. Commit `7513b18` on `phase1`. **Not deployed.**

## D23. `category_budgets` is kept (yours, 2026-10-05)

**Your words:** "dont cut category_budgets, it is useful." The drop is out of
the runbook and nothing about the table changes.

**Where it stands:**
- No model builds it, so the app role has no grant on it and the API cannot
  read it (Phase 0 D11).
- It still has Supabase's default grant to `anon` and `authenticated`, and no
  row policy. With the Data API disabled nothing can use that today. The
  runbook now has an optional, non-destructive `REVOKE` so that re-enabling the
  Data API could never expose it.

**A note for when it is used again:** the table holds per-month overrides for
the whole-budget, per-category limit that was rolled back on 2026-09-24. The
reason for that rollback still applies: a limit covering every account was
judged against one account's share of the spending. If it comes back, it would
be keyed on account and category, and it would get a model, which gives it a
row policy automatically.

## D24. Where kept syllabus files live: Google Cloud Storage (yours, 2026-10-05, after a correction; BUILT, waiting)

You agreed to Supabase Storage on my recommendation. My reason was that "its
per-user access rules work the same way as your tables'." **That was wrong,**
and I checked before building anything:
- **Supabase Storage policies work off Supabase Auth's sign-in token**
  (`auth.jwt()`). This app has its own sign-in, so those policies would never
  see who the user is.
- **A server-side key bypasses the policies entirely.** "S3 access keys provide
  full access to all S3 operations across all buckets and bypass RLS policies";
  the same holds for the service key
  ([S3 auth](https://supabase.com/docs/guides/storage/s3/authentication),
  [access control](https://supabase.com/docs/guides/storage/security/access-control)).

So with either store, who sees a file is decided in app code. The API would
fetch only by a path it reads from the user's own `syllabus_parses` row, which
row-level security does protect. **The real difference is the key:**

| | Supabase Storage | Google Cloud Storage |
|---|---|---|
| Credential | An S3 access key in Secret Manager, valid for every bucket | None: Cloud Run's own identity, granted one bucket |
| If it leaked | Every stored file readable and writable | Nothing to leak |
| Free tier | 1 GB, 50 MB per file | 5 GB-months in us-west1, where the API runs |
| New code | A storage client (boto3, or signing by hand) | None: the existing `google-auth` makes the call |

**Recommendation: Google Cloud Storage,** because there is no key to leak.
**You chose GCS.**

**What was built** (`bdb2ac3`, on `phase1`, not deployed):
- **A file is only ever reached through its row.** The object is named after
  the `syllabus_parses` row, which is read as the user under row-level
  security. Nothing in a request names an object.
- **Uploads never overwrite** (`ifGenerationMatch=0`).
- **Downloads are always attachments,** with `nosniff` and a cleaned-up
  filename.
- **No file outlives its record.** The row is committed before the upload,
  and the object is named after it. The account purge deletes every parse's
  object before the rows, including an upload the row never recorded. If
  storage can't confirm the deletes, that account waits for the next purge.
- **A failed upload costs the parse nothing.**
- **Storage uses the JSON API through the existing `google-auth`,** so no
  library was added.
- **The course page offers "Syllabus · <file>"** when one was kept, and shows
  nothing otherwise.

**Tests:**
- 25 new tests. The suite runs against an in-memory bucket, so nothing reaches
  Google.
- The isolation and non-interference walks now keep a file per world, with the
  marker inside. The first run caught that the fixture's file wasn't kept, so
  the download route had been answering 404 to everyone.
- 13 of 13 mutations caught.
- Full suites: SQLite 1,841, Postgres 2,064, frontend 469 passed.

**Setup:** runbook step 4 (a bucket, one IAM binding, one env var). Optional:
without it nothing is kept.


## D25. You can pick one grading scheme to be a course's grade (yours, 2026-10-05; BUILT, waiting)

**Options offered:** comparison only (my recommendation), you pick one,
best-of automatically, or a per-course mix of all three. **Your choice: you pick
one.**

What it means:
- **Per course, at most one scheme is marked as counting.** When one is,
  every figure built from the course's grade follows it: the course average,
  letter grade, GPA points, cumulative and term averages, the required final,
  Attention, and the grade band.
- **When none is marked, nothing changes.** The course's own weights stay the
  grade, as today.
- **The course page always says which scheme is counting,** and switching back
  to the course's own weights is one click.
- **Best-of automatically is not built.** It was offered and not chosen.

**Trust cost:** this is the first feature that moves a grade figure you already
rely on, so it gets the invariant treatment. A course with no scheme marked must
produce exactly today's numbers (a test over generated courses, like D18's).
And every place that reads "the course's grade" must read it through one
function, so no screen can disagree with another.

## D26. Grading schemes are edited in place; no version history (yours, 2026-10-05)

**Options offered:** edit in place (my recommendation), or keep a history.
**Your choice: edit in place.** An edit replaces the scheme, as built. History
can be added if a real mid-term rubric change makes it worth it.

## D27. A syllabus can add to a course you already have, add-only (yours, 2026-10-05; BUILT, waiting)

**Options offered:** add-only (my recommendation), a full merge with each change
confirmed, or not now. **Your choice: add-only.**

What it means:
- **The syllabus reader can target an existing course.** It proposes the
  assessments that course doesn't have yet, and you confirm each one.
- **It never changes a mark, weight, date or name you entered.** Weights the
  syllabus states that differ from yours are shown for information, not
  applied.
- **Matching an existing assessment** is by category and normalised name, and
  an unclear match counts as existing, so nothing is duplicated by guesswork.

## D28. Sinking funds stay as they are (yours, 2026-10-05)

**Options offered:** run the usage report first (my recommendation), hide now,
keep as is, or delete. **Your choice: keep as is.**

Phase 1 item 12's sinking-funds cut is closed, with no code change. With
`category_budgets` kept (D23), item 12 has nothing left.

## D29. How D25 was built, and a bug it found in the live required final (2026-10-05)

**The design: one function for "the course's grade".**
- **Where the grade lives:** the app stores each course's average and
  recomputes it at six places. Everything else reads that stored figure: the
  dashboard, letter, GPA, term average and Attention.
- **One function:** all six places now write through `course_grade`, which
  uses the picked scheme when there is one. Those screens follow a picked
  scheme without knowing schemes exist.
- **Projections:** the three that work from weights directly (grade band,
  required final, cheapest path) go through the same choice.
- **Shared engine:** the scheme arithmetic is one pure module, `scheme_math`,
  used by both the comparison and the counting grade.
- **The required final under a scheme:** a scheme's drops and replacements make
  the average piecewise, so this searches for the lowest final that reaches the
  target. It searches the unrounded average, so a hundredth's rounding never
  counts as having reached the target.

**The invariant:** picking the course's own weights as a scheme changes no
figure (average, band, cheapest-path projections, required final) across 40
generated courses.

**Correction to the live app (a bug found by that invariant):**
- **The bug:** the existing required-final formula didn't cap its denominator
  at 100% the way the course average does. Weight past 100% is bonus. One
  generated course weighted 125% was told it needed 191% on the final, when
  96.16% brings its shown average to the target.
- **The fix:** capped, with a regression test. It's on `phase1-next` with D25,
  so it goes live with the next batch.

**Rejected:** recomputing figures at read time instead of storing them. That
would have touched every reader rather than six writers, and it's the shape
that lets two screens disagree.

**Tests:**
- 20 for counting, with every path that stores the average tested on a course
  where the scheme and the own weights disagree.
- Mutations: 11 of 11 logic lines caught, and 6 of 6 storage paths caught. The
  storage paths needed new tests first; only adding a mark had been covered.
- Frontend: 4 new tests.

**Where it is:** `0a8107b` (backend), `cf19d17` (frontend), on `phase1-next`.
Needs one column, `courses.counting_scheme_id`.

## D30. How D27 was built (2026-10-05)

**The flow:** "From a Syllabus" on the course page, shown only when syllabus
reading is set up. The server proposes rows and re-checks them when you
confirm.

**Matching:**
- **Same category and the same words,** with case, punctuation and plurals set
  aside. Numbers keep items apart: "Assignment 1" isn't "Assignment 10".
- **Exact matches first,** then a looser one. "Midterm" against "Midterm 1"
  counts as existing, because a duplicate is worse than a row left to add.
- **Each existing row matches at most once,** so "Midterm" covers "Midterm 1"
  and leaves "Midterm 2" new.

**What it writes:** new rows only, plus the section if the course has none and
you tick it. A differing weight is a note; a 0%-weighted category is named. A
syllabus is used once.

**Tests:**
- 17 tests. 10 of 10 mutations caught, after one test was strengthened: the
  first version couldn't tell a loose match stealing an exact one.
- Frontend: 4 tests.

**Where it is:** `da290c6`, on `phase1-next`. No schema change.


## D31. The degree audit is next, from requirements you enter once (yours, 2026-10-05)

**Options offered for what to build next:** the degree audit (my
recommendation), the review loops, Phase 2 Part A, or a pause. **Your choice:
the degree audit.**

**Options offered for where requirements come from:** you enter them once (my
recommendation), wait for UBC, or skip the audit. **Your choice: you enter
them once.** This is D19's option 1:
- **Your requirements:** your programme's required courses and credit buckets,
  typed in from your programme page.
- **Your courses:** transfer credits and cross-campus courses mapped by hand,
  many-to-many.
- **What it shows:** what's met, what's missing, and how many credits each
  bucket still needs.

If UBC agrees to the calendar request (Phase 2 D2), the calendar can fill the
requirements in later. Prerequisites stay in Phase 2.

## D32. The review loops to build, after the audit (yours, 2026-10-05)

**Chosen:**
- **Grade projection against result:** "we projected 84.5%; you got 82%".
- **Task estimate against actual:** "you estimated 2h, it took 3.5h; update
  your multiplier?"
- **The year plan against actual, month by month.**

**Offered, not chosen:** the paycheque flag review ("we said $38 short; were we
right?"). It stays unbuilt.

## D33. The purge reaches every table, and a refusal no longer stops startup (2026-10-05)

**Found** while checking that account deletion removes the degree tables. They
were fine. A new test that purges a user owning a row in *every* table (the
isolation world) found what the old eight-table test could not:

- **Three tables were never purged.** `UserModel` did not cascade to
  `account_category_limits`, `account_category_month_limits` or
  `account_month_values`. Their foreign keys then refused the delete of the
  user's accounts.
- **Twelve foreign keys had no relationship.** SQLAlchemy orders deletes by
  relationships, so those went in whatever order the flush picked. It was right
  by luck for budget targets and wrong for imports.
- **The purge runs in the API's startup**, so one refusal would stop new
  instances starting.

**Done (`4598a82`):**
- The three tables cascade from the user.
- Every foreign key has a relationship. A test reads the metadata and holds
  every key, present and future, to it.
- A refused purge is rolled back whole and logged, and that account waits for
  the next start. The others still go.
- Each of the three protections was mutation-checked: removing it fails a test.

**Production:** not hit yet. The earliest it could happen is about 2026-10-25:
category limits shipped 2026-09-25, plus the 30-day grace period. It needs no
schema step, so it can ship ahead of the batch if the batch waits.

**Why not delete these rows by hand in the purge** instead of with
relationships? A hand-ordered list is what left these tables out in the first
place. Relationships plus a test that reads the metadata can't fall behind a
new table.

## D34. Grade loop: the result against the last projection before the final (yours, 2026-10-06)

**Chosen:** compare the result with the projection as it stood just before
the final was marked. **Offered, not chosen:** the halfway projection as well,
or every projection drawn as a line.

**How it is built:**
- **Saved at the moment it stops being a prediction.** Two columns on
  `courses`: `projected_before_final` and `projected_on`. They are written the
  first time a write would end the forecast:
  - the final exam (category `Final`) gets its first mark, or
  - the course's `final_grade` is first set, for a course with no final or one
    whose final was never entered.

  The value is the course's grade as it stood just before that write: the
  number the course page was showing.
- **First time only.** Editing or re-entering the final later never overwrites
  it, because the first value is the one that was a prediction.
- **Only when something was marked.** With no marks at all there was no
  projection, so nothing is saved.
- **The result** is `final_grade`, the official grade you enter. The course
  says: "Before the final we projected 83.0%. You got 82%."

## D35. Task loop: actual time asked on completion, and a timer (yours, 2026-10-06)

**Chosen:** both. **Offered, not chosen:** the question alone, or the timer
alone.

**How it is built:**
- **Two columns on `tasks`:** `actual_minutes` and `timer_started_at`.
- **The timer is stored on the server,** so it survives a reload or another
  device. Stopping it adds the elapsed minutes to `actual_minutes`, and running
  it twice adds up. A timer left running past 12 hours is not trusted: stopping
  it records nothing and says so.
- **Ticking off a task with an estimate** asks "How long did it take?", with
  quick picks (as estimated, half, 1.5×, 2×, or type it). The timer's total
  fills it in when one ran. Skipping leaves it blank, and a blank counts for
  nothing.

## D36. The estimate ratio: shown, and offered for the workload forecast (yours, 2026-10-06)

**Chosen:** show it and offer to apply it. **Offered, not chosen:** show only,
or apply automatically.

**How it is built:**
- **The ratio** is the total actual time over the total estimated time, across
  completed tasks that have both, from the last 90 days. A total, not an
  average of ratios: a 5-minute task that took 15 should not weigh as much as a
  5-hour one.
- **Shown once at least 5 tasks have both numbers.**
- **"Use it in the workload forecast"** is a preference, off by default. When
  on, the week-load estimate is scaled by the ratio, and the forecast says so.
- **Estimates are never rewritten.** Turning it off undoes it completely.

## D37. Plan loop: a plan counts as set when you save it (yours, 2026-10-06)

**Chosen:** "Save as my plan". **Offered, not chosen:** saved automatically on
the 1st of each month, or both.

**How it is built:**
- **A new table, `saved_plans`.** Each save is a new row and is never
  overwritten, holding the plan's monthly rows as they stood.
- **Each finished month compares with the latest plan saved before it began.**
  A plan saved mid-March starts counting from April. Its March row only covers
  the days after it was saved, so comparing it with all of March would be
  unfair.
- **Actuals come from the ledger, by the plan's own definitions:**
  - Liquid money is spending, savings and emergency accounts. Transfers between
    them net to nothing.
  - Card purchases count when they happen, and paying the card off counts for
    nothing, the same as the forecast's pace.
  - Tuition counts as money out, because it left. The plan leaves tuition out,
    so the month says how much of the difference it explains.

## D38. Every exit number prints from the usage report (2026-10-06)

Item 13's "done when" was that every Phase 1 exit number prints from
`scripts/usage_report.py`. Two did not, and both are now added. Neither needed
a schema change, because the rows already held the data:

- **The money room, unprompted.** A new last column in the weekly table counts
  people who opened Budget that week other than from a notification. A
  `prompted_visit` does not count.
- **Syllabus to term.** A new section reports how many parses were confirmed,
  the median minutes from read to confirmed, and how many took under five
  minutes.
  - It also reports how many were confirmed with nothing changed, plus fields
    changed out of fields shown. That is §15's no-change rate for this confirm
    screen.
  - An add-only merge (D30) is timed but has no field counts, so it is not in
    the no-change rate.

The report stays aggregates only. Its existing test, that nothing printed
identifies anyone, still holds. Three mutations were tried and all three were
caught.

## D39. One switch per account for net worth and every analytic (yours, 2026-10-06)

**Your words:** "let a user pick the accounts he wants to contribute to his
networth and to all analytics."

**Chosen:**
- **One switch per account, for both.** Offered, not chosen: two switches,
  "net worth" and "analytics", set separately.
- **Set from a list in Settings → Financial, and from the account's edit
  dialog.** Offered, not chosen: the Settings list only.

**This reverses an earlier rule.** Until now `counts_toward_net_worth` reached
net worth only, deliberately: "what am I worth" and "what can I spend" were
kept apart, and a test pinned it. That test now says the opposite.
`Ideas/next.md` still describes the old rule; it is your file, so I left it.

**What "unticked" means.** Every figure built from more than one account treats
the account as absent:
- net worth
- safe to spend: spendable balances, committed charges, and sinking-fund
  earmarks paid from it
- the forecast: the spending pace and history window, runway, run-rates
- the year plan, and the plan against actual
- the budget summary, its by-category totals and the Dashboard tiles
- the term budget
- course cost
- the subscription finder
- the standing-instruction totals

What stays as it is:
- **Recording.** Its ledger, its page, deposits into it, and its card,
  which now says "not counted".
- **A transfer between a counted and an unticked account** still counts,
  because the money really left or arrived.
- **The income share.** Pay landing in an unticked account does leave what
  counts.

**How it is built:**
- **No schema change.** The column keeps its name, since renaming a Postgres
  column buys nothing a reader sees.
- **One place reads it:** `Finances/services/counted.py`, as a subquery, so a
  query adds one filter and no extra round trip.

**Tests:**
- **The invariant test** (`tests/test_counted_accounts.py`) adds an unticked
  account with activity of every kind (spending, savings and debt) and requires
  every figure to be unchanged. Ticking it back on must move every figure.
- **Mutation-checked:** 15 of 15 backend filters and 5 of 5 frontend checks.
