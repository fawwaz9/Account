# Next

What is not built yet, roughly in the order it is worth building. The second half
of this file is context rather than work: constraints and measurements that decide
how any of it should be done.

Split out of `whats_next.txt` on 2026-10-02. Anything already deployed lives in
`shipped.md`, which is the file to check before proposing something.

---

## Implementation Plan

Jobs is complete in all three stages, the recurrence engine now has four
consumers and the tokenizer two, and the app is deployed. How each module
actually works, and why, is written down in Ideas/design/ -- start there rather
than here when picking something up.

What was left after that was the longer-horizon work: derivations that need a
term to have closed, the parser everything else had to settle before, and the
things that need new storage or a second person. The Settings, Calendar, Tasks
and Quality of Life items above came later and are mostly small, so they are
not covered by that description -- read the per-module list as the live one and
this section as the reasoning behind the ordering.

### Next, and cheapest
- The rate limiters key on the wrong address (step 12a / D5.5). Behind Cloud Run
  every caller looks like Google's front end, so the limits are one shared
  budget. Production logs show 99 of 99 requests from 169.254.169.126.
  SMALLER THAN THIS ENTRY USED TO CLAIM, checked 2026-09-17: the throttle covers
  only /login and /register at 8 attempts per 15 minutes, and 4 of 5 users sign
  in with Google, which never reaches it. So it is a wide-invite blocker, not a
  today problem. Fix is in client_ip(), api/routes/auth.py:33.
- Request caching on the frontend (audit #35). Every navigation refetches what
  it already has, and every reload() refetches all four endpoints when one row
  changed. This was invisible on localhost and is not from a phone.

### Parked, now that the question is answered
- A dropped course's dollar figure. The open question was whether a refund
  should be attributable to a course at all, given that refunds are income and
  course_id is expense-only. It mostly does not arise: a course dropped late is
  not refunded, and on the rare occasion it is, recording the refund as plain
  income is enough. So this needs no course_id on income, no "dropped" flag
  alongside archived, and no work. Set aside rather than closed -- worth
  reopening only if the refund case turns out to be common in practice.

### Cheap wins, read-only
- The term retrospective. Derived from data already stored: no new tables, no
  writes. It wants a term to have closed first, so it is waiting on the
  calendar rather than on anything in the code.
- The band that shipped is the pattern for the rest of them: project_average in
  grade_service.py shows the shape, including the rule that a projection must
  agree with the live number at the ends or it is a second opinion.
- Read-only offline: cache the shell, stale-while-revalidate the GETs.

### Needs new storage, so later
- Reimbursement state, and who/when for money lent out. No seeded pot to hang
  it on any more -- the "Money Lent" default was removed, so this attaches to
  whichever account the student actually keeps it in.
  DONE 2026-09-17: the Budget heading is back in the per-module list above,
  carrying this and account ordering. The module list no longer reads as though
  Budget has nothing left.
- Grade-to-effort log. Worth noting it now has a precedent: shift_records keys
  on (event_id, on_date) to record what happened on one date of a repeating
  thing, and hours against a grade is the same shape.
- What-if sandbox. Read-only in effect, but it needs the whole term recomputed
  from hypothetical inputs, so it wants the averaging code reachable without a
  session first.

### Syllabus parser
- Deliberately late. It proposes categories, weights and due dates for review,
  which means it depends on due dates, category weights and the course flags all
  being settled -- they are -- and on the tokenizer for dates, which now exists.
- Default path when adding a course, manual behind a button. When editing, manual
  is the default and the parser sits under the grid.


---

## Interface quality, asked for 2026-09-28

> **Status, 2026-10-02.** The third ask is half built: `HelpTip` exists and is in
> use twice. The first two -- confirmations on every destructive action, and a
> visible acknowledgement for every click -- are still open, and so is the rest of
> the (?) sweep. Detail below.
Three standing asks, all of them about the app acknowledging the person using
it. Counted against the code on the day they were written, so the numbers below
are the size of each job rather than an impression of it.

- CONFIRM EVERY DELETE. Four already do, through DeleteConfirmModal: a grade, a
  course, an account, a transaction. NINE DO NOT, and two of those cascade:
    * a task            TasksPage.handleDelete
    * a calendar event  CalendarPage.handleDelete
    * a reminder        ReminderModal.handleDelete
    * a blocked period  BlackoutsModal.handleDelete
    * a job             JobModal.handleDelete      -- cascades to its shifts and cheques
    * a paycheque       PaychequeModal.handleDelete
    * a tuition payment TuitionModal.handleDelete
    * a sinking fund    SinkingFunds              -- cascades to its transfers
    * a standing rule   Repeating.onStop, Recurring.onDelete
  The fund is the sharp one: its own aria-label says "Remove {name} and its
  transfers", so it announces the cascade and then performs it on one click.
  There are also already TWO confirmation idioms -- the modal, and the inline
  "Yes, delete / Keep" pair in CategoriesModal. Pick one before adding nine more
  instances of the wrong one. The modal is the better default; the inline pair
  is better inside a list you are editing, which is why CategoriesModal has it.
    THE TEST, in your words: "every delete button OR INSTANCE that PERMANENTLY
    deletes something". Two useful refinements in that phrasing. "Or instance"
    means the audit is of code paths, not buttons -- so the omnibox, quick
    capture and any keyboard shortcut that can destroy a row count too, and the
    nine above were found by reading delete call sites rather than by clicking
    around. "Permanently" is the line that decides borderline cases: a soft
    delete, an archive or a paused rule is recoverable and does NOT need a
    confirmation, which is why archiving an account is not on this list while
    deleting one is. Anything the user cannot get back by clicking again needs
    the dialog.

- MAKE A CLICK FEEL LIKE A CLICK. 183 buttons in the app, 114 with a disabled
  binding, so ~69 fire with no acknowledgement at all. `:active` appears ZERO
  times in the entire stylesheet -- nothing anywhere shows a pressed state.
  aria-busy is used twice; role="status" nine times. The cheapest large win is
  one `:active` rule on the shared button classes, which is a few lines and
  covers all 183. Then the pending state on anything that makes a request:
  PlannedSpend's scoped aria-busy is the pattern to copy, and it exists because
  removing the only feedback on a month step once made a faster app feel slower.

- EXPLAIN ON DEMAND, NOT EVERYWHERE. 84 `small-text muted` nodes, 36 more plain
  `muted`, 8 loginHint -- 128 sentences of ambient explanation. Each reads as
  thoughtful on its own; together they crowd out the figures the panels exist to
  show.
    THE SPEC, in your words: "Every important or confusing feature should have a
    little clickable white question mark that extends a dialogue box from it
    explaining the feature." Clickable, not hover-only -- which settles a
    question the earlier note left open, because hover alone excludes touch and
    the keyboard.
  There is no such component yet -- aria-describedby is used twice, in
  QuickCapture and Omnibox, and that is the whole of it.
  64 `title=` attributes are NOT the answer, for the same reason: a native
  tooltip never appears on touch and is unreachable from the keyboard.
    Build one shared HelpTip: a real <button> so it is focusable and clickable,
    white as asked, an accessible name of its own, content in a popover that
    extends from the mark rather than a title attribute, and dismissible with
    Escape. Hover MAY also open it, but the click is the contract.
    Then move the muted sentences into it panel by panel rather than in one
    sweep -- some of them must be read BEFORE acting and should stay ambient.
    The rule of thumb: text that answers "what is this?" goes behind the (?),
    text that changes what you are about to do stays on the page.
    First use is already waiting: Ideas/settings-plan.md puts the explanation of
    what the timezone setting affects behind one of these rather than adding a
    129th muted line.


---

## From the front-end review, 2026-09-28
- An outside model walked the live site and filed 23 claims. Nine held; they are
  audit.md #57-#65. Fourteen did not, and are written up there so they are not
  raised again -- including both of its "criticals", which were one observation
  and not a defect.
- Do #58 first. UserPreferences declares seven fields Settings never sends, and
  one of them is timezone. It defaults to America/Regina and timing_service uses
  it to decide whether a task was finished early or late, so every user outside
  that zone gets a figure the module's own docstring calls "a systematic drift
  toward late", with no way to correct it. currency is stored, validated as ISO
  4217, and then ignored by formatMoney, which hardcodes $. The Settings form
  already exists; this is fields, not architecture.
- #57 is the cheapest: "Left to spend" keeps its label when it goes negative, so
  an overspent month reads "-$51,650.99 left to spend". NetWorth already swaps
  its label to "In the red" for the same reason -- copy that.
- A design question, not a finding: should a category be able to declare itself
  not-spending? A student loan recorded as an expense in a "Student Loans"
  category distorts every budget-vs-plan figure downstream, and the app has no
  opinion about it. The settled preference here is options over rules, so if
  this is worth doing it is a flag the user sets, not a warning the app raises.


---

## What is left, by module

### Settings
        BUILT, 2026-10-01 -- every line that was here is done: Account and Password
        side by side, Academic/Calendar/Financial tabs shown one at a time with
        Academic as the default, and the gold rule under the active tab. The
        timezone control and the first (?) marks landed with it. See `shipped.md`,
        "Settings, phases 0-4". Nothing is outstanding for this module except the
        (?) sweep, which is tracked under Interface quality above.

### Calendar
        A line at the exact time of the day it currently is.
          Confirmed missing -- nothing in the calendar draws one today.
          Cheap: WeekView.tsx already lays the grid out from DAY_START with a
          fixed HOUR_HEIGHT (weekLayout.ts), so the line is one absolutely
          positioned div at (nowHour - DAY_START) * HOUR_HEIGHT, inside the
          column for today only. The only real decisions are whether it ticks
          (a minute interval) or is placed once on render, and that it must not
          draw on a week that is not the current one.
        Color customization of different category types of events.
          There are EIGHT kinds, not the five your data happens to use:
          lecture, lab, discussion, midterm, final, deadline, personal, shift.
          Colour is a CSS class per kind today -- EventCard.tsx:24 builds
          `calChip-${kind}` and calendar.css carries a rule for each.
          So customising means storing a colour per kind. UserPreferences is
          the natural home: a JSON column parsed through a Pydantic model,
          where new keys are additive and need no migration.
          ONE THING TO DECIDE FIRST: EventKind's own docstring says these are a
          fixed enum rather than a user table precisely BECAUSE each kind has
          behaviour attached -- a midterm is themed and sorts differently, and
          shifts are excluded from blackouts. Recolouring them is fine; letting
          users ADD kinds is the thing that conflicts with that reasoning.

### Grades
        Term retrospective when a term closes: what moved, what slipped, what you predicted vs got.
        Syllabus paste: drop the text in, get categories, weights and due dates proposed for review.
        Make syllabus parser the main when adding courses but add a button to do it manually.
        When editing courses the manual is the default but syllabus parser will be available under the manual grid.
        Fixed term dates -- DONE 2026-09-17, shipped exactly as asked below.
          Kept only because it records what changed and what is still owed.
          WAS: nothing stored anywhere. term_span() took min(start_date) and
          max(end_date) across a term's courses, so a term could only be
          measured if its courses happened to carry dates -- and 21 of 27 did
          not. That is why every past term had nothing to measure.
          NOW: Grades/utils/terms.py holds TERM_DATES and every reader goes
          through one accessor, term_dates(semester, school_year, first_year):
            Fall    Sep 1  - Dec 31   (the school year's own calendar year)
            Winter  Jan 1  - Apr 30   (+1)
            Spring  May 1  - Jun 30   (+1)   <-- corrected on the way in
            Summer  Jul 1  - Aug 31   (+1)
          The +1 is the whole reason a school year is written 2025-2026; without
          it Winter lands eight months before the Fall it follows.
          THE WIDER SPAN WAS ACCEPTED DELIBERATELY. Your Fall really runs Sep 9
          to Dec 7, so Term Budget now counts a few weeks either side. Fixed
          dates WIN over a course's own -- that was the decision -- with one
          carve-out: the class timetable still uses each course's real dates, or
          it would invent three lectures before term and three after.
          Jobs was reading its own duplicated copy of the old rule and now
          imports the same accessor. That bug is what the duplication cost.
          STILL OWED BEFORE ANY OF IT SHOWS: nobody has set the first-year
          anchor in Settings. It suggests 2024 from your dated courses. One
          click now fixes three things at once -- the Term Budget span, the Jobs
          term, and the heading above them.
        term_label is no longer trusted for the term heading -- DONE 2026-09-17.
          It read "Fall 2025-2026" above a span computed over 2026, because the
          heading came from a free-text field and the dates came from the
          anchor. term_name() now derives the label from the anchor too, so one
          fact feeds both. Winter deliberately keeps the SCHOOL year's calendar
          year, so January 2027 still reads 2026-2027 rather than starting a new
          one -- there is a test for exactly that, and the mutation that used
          the term's own year instead fails it.
          term_label survives only as the fallback for a user with no anchor.
          It has NO EDITOR anywhere in the app, which is why it went stale and
          stayed stale, so it is a column nobody can fix by hand. Worth removing
          once every user has an anchor; nothing else reads it.

        Is it worth it or safe to make not just the dates but the semesters editable due to how integral they are to the structure of the app.
          Safe, but not free, and there are three things to know first.
          1. The DB column is a plain String (models.py:116), so the database
             accepts anything. The GATE is Pydantic: there are TWO Semester
             enums -- Grades/utils/enums.py and Users/schemas/academic_status.py
             -- and both list Fall/Winter/Spring/Summer. They agree today.
             Editable semesters means either keeping both in step or collapsing
             them to one, and two enums for one concept is already a smell.
          2. SEMESTER_ORDER is the part that actually breaks. Declaration order
             is not chronological, so terms sort through an explicit map
             (Fall 0, Winter 1, Spring 2, Summer 3), read by Grades/utils/
             terms.py and course_service.py:190. A custom semester with no entry
             falls through to .get(..., 0) and silently sorts as if it were
             Fall -- wrong order, no error. Any editable scheme needs an order
             per term, not just a name.
          3. Spring is ALREADY in both enums -- it is only absent from your
             data. DONE: the term-date table now exists and carries Spring at
             May 1 - Jun 30, so there is nothing left to add for it.
          Renaming is the risky operation, not adding: courses store the string,
          so a rename orphans every course carrying the old one unless it
          updates them in the same transaction.
          How about the ability to edit the names and dates of the semester but the order must stay intact.
          Suggest ways to accomodate this system also suggest ways to accomodate classes that span multiple semesters.
          ANSWERED, and the answer is the design above: FOUR FIXED SLOTS WITH
            EDITABLE LABELS. The stored value stays "Fall" forever as an id
            nobody sees; only the label is edited. That keeps order intact for
            free -- SEMESTER_ORDER keys on the id, so point 2 above stops being
            a problem -- and it removes the one genuinely dangerous operation, a
            rename that orphans every course carrying the old string, because
            zero course rows are touched by a rename.
            Editable DATES are the same shape: TERM_DATES in Grades/utils/
            terms.py is already behind one accessor, term_dates(semester,
            school_year, first_year), which was built as the seam for exactly
            this. Moving the table into a user-owned column changes one function
            and nothing that calls it.
          MULTI-SEMESTER COURSES were deferred on purpose, to avoid disturbing
            term bucketing while fixed term dates landed. No course in the data
            spans terms today. When it is picked up, the question to settle
            first is which term a two-term course's grades and costs belong to,
            because Term Budget, the Jobs term and cheapest path all bucket by
            a single semester string.


### Jobs
        A fortnightly shift. ShiftMeeting is the same shape as ClassMeeting,
          which now carries an interval and a first week, so it is the same two
          fields again -- left out of that change as scope, not oversight.
        Overtime rules, if a per-shift rate override stops being enough. It was
          offered and declined once already: an override covers the stat holiday
          and the night differential without a provincial rule table.
        Somewhere for cash to live. A cash tip splits by income share like any
          other income, which claims it is in the bank when it is in a pocket.
          A cash account with its own share is the workaround; whether that is
          good enough is worth finding out before building anything.
        Confirmed shifts leave the shifts section after 20 days They are still in db and calendar. 
          Also unconfirmed shifts should be placed at the top of the list sorted by the closest dates.

### Budget
        Reimbursement state, and who and when for money lent out. On whichever
          account you actually keep it in -- there is no seeded pot for it since
          the "Money Lent" default was removed.
        Account ordering is stored (position) but has no editor, so the grid
          order is whatever creation happened to produce. Worth a drag handle
          only if the list gets long.
        (Restored 2026-09-17. These two were listed only in design/finances.md
        and in the "Needs new storage" section below, so the module list read as
        though Budget had nothing left. It does.)

### Grades x Budget (nothing else does this)
        A dollar figure next to a dropped course, since the deadline to drop with a refund is a date on the calendar.
          Parked -- the question behind it has been answered. See below.

### Quality of Life
        Weekly digest on the dashboard: what is due, what moved, what you spent.
        Keyboard shortcuts for the four things you do twenty times a day.
        Offline-capable, because campus wifi. Only read-only offline should be implemented.
        Remove all the dashboard buttons for the modules the sidebar is enough in my opinion.
          Confirmed: Dashboard.tsx lines 149-169, five buttons that only call
          navigate() -- /grades, /calendar, /tasks, /budget, /settings. They
          duplicate the sidebar exactly. Deleting them is deletion only, no
          replacement needed. Check the .action-widget CSS has no other user
          before removing it too.
        Add icons for each module in the sidebar.
          Confirmed missing: Sidebar.tsx renders labels only, zero svg. The nav
          is a plain array of {to, label} at lines 11-17, so this is one icon
          field on that array plus the svg. Seven entries: Dashboard, Grades,
          Calendar, Tasks, Jobs, Budget, Settings.
          Inline the svg rather than adding an icon library -- the CSP on the
          deployed site only admits scripts from cdnjs, and a whole icon
          package for seven glyphs is a lot of bundle for the value.
          Keep the text labels. Icon-only navigation is the accessibility
          regression this codebase has already fixed twice, most recently when
          account kind was a coloured stripe and nothing else.
        Delete confirmations everywhere, and question mark icons instead of muted
          text: both moved to "Interface quality" near the end of this file, where
          they are written up with the counts. Not dropped -- the nine deletes
          that lack a confirmation are named there one by one.

        Light mode????
          Answering the question marks, measured 2026-09-30: this is the largest
          cosmetic job in the app and it is not a settings toggle.
          12 stylesheets. 541 var(--...) uses, which is the good news -- most
          colour already goes through a token. Against that, 36 distinct
          hardcoded hex values and 93 rgba() literals that do not.
          The tokens themselves are named for a dark design: --panel, --bg,
          --deep-border, --muted. A light palette cannot just reassign them,
          because several encode "darker than the page" rather than a role.
          So the work is: tokenise the 36 + 93 stragglers, rename the tokens by
          ROLE rather than by shade, then define a second palette, then look at
          every screen again. The `theme` preference already exists, stores and
          validates -- it is the only part that is done.
          Worth doing as its own project with its own plan. Not worth smuggling
          into another change, and not blocking anything.

### Wild
        Grade-to-effort log: record hours against each grade, then find out whether effort actually correlates with your marks.
        A what-if sandbox: change a weight, a score or a course load and see the whole term rearrange, without saving anything.
        Add functionality for users to work together.
        One user can add a user to a task, assignment, project or just an evemt on the calender.
        This task/calender event will then show up for all users that are added.


---

## Collaboration, by invite
- No shared ownership. The invitee gets their own row; every existing query keeps
  filtering by user_id and nothing else changes. This is how real calendar invites
  work.
- invitations table: source_id, kind (event/task), from_user, to_user, status
  (pending/accepted/declined).
- On accept, copy the event or task into the invitee's own table with an origin_id
  pointing back at the original.
- Organiser edits propagate to accepted copies; organiser deletes mark them cancelled
  rather than vanishing them.
- Address people by email. Return the same response whether or not the address has an
  account, so the endpoint cannot be used to enumerate users.
- An invites inbox, and the only cross-user write in the whole app is one narrow
  insert. Easy to audit.
- Decide once: assigning a task means the other person owns it; sharing means you both
  track it. They are different rows.


---

## A decision owed: the orphaned table, found 2026-09-28
- category_budgets is still in the production database. f0dfede created it for
  whole-budget category limits; 394cb7c removed that feature entirely -- model,
  service, routes, frontend -- and left the table, its four indexes, and TWO
  ROWS: $41,040 against September 2026 and $70 against October. Nothing reads
  it, no foreign key points at it, and nothing has since 2026-09-24.
- So production has 26 tables where python -m app._database.schema builds 25.
  Nothing is broken by that. What is broken is that the schema module is the
  file every other document treats as the description of this database, and it
  has quietly stopped being it.
- THE CHOICE IS YOURS AND IT IS NOT URGENT. Either is fine:
    * DROP IT. Clean, and it destroys those two rows permanently. Back up first
      -- the nightly artifact counts. The $41,040 row is the student-loan figure
      from the feature that was removed, so it is probably not worth keeping,
      but "probably" is not a reason to delete someone's data without asking.
    * KEEP IT, and write here that it is kept deliberately. Costs nothing: it
      is 2 rows in a 13 MB database against a 500 MB cap.
  What is NOT fine is leaving it undecided, because the next person to count
  tables has to work out which of the two numbers is wrong.
- shipping.md step 18 now exists so a removal names its orphaned table at the
  time, rather than being found by counting four days later. Audit #66.


---

## Not built, from the original features.txt sketch
- Notes, Goals and Study Analytics. Listed on day one, never designed, never
  started. Nothing depends on them. Recorded here so the sketch can go.


---

# Context before you start

Not work in itself. These are the constraints, the things that are easy to get
wrong, and the measurements that decide what the work above should look like.

---

## Worth knowing before picking anything up
- Start at Ideas/design/. One note per module plus an overview, and a template
  for the next one. They carry the reasoning behind decisions that had a real
  alternative, which is what stops the next person reversing one for looking
  inconvenient.
- Branch off main, and off main only. Stacking on unmerged work caused phantom
  conflicts twice, and once cost an afternoon to a "the fix is not there" report
  that turned out to be a branch without the fix in it.
- Back up data/app.db before any migration, and test the migration against a
  copy with the new columns genuinely dropped first. A --reload dev server
  applies them on its own, which has already turned one migration check into a
  false pass.
- gh is installed and authenticated, so a PR opens from the terminal. The push
  credential lives in the macOS keychain.
- 904 backend tests. Run the suite with -W error::sqlalchemy.exc.SAWarning:
  that is how a duplicate cascade delete surfaced. Update this number in place
  rather than adding a line -- four stale counts had stacked up here, none of
  them current, and only the last one still joined onto this sentence.
- Mutation-test every guard: revert it and confirm the named test fails. Doing
  that caught three tests this year that asserted something already true by
  construction and would never have failed.
- Repeat rules live in five columns shared by events, standing payments and
  repeating tasks, read and written through Calendar/utils/rule_columns.py.
- Bonus is the one category whose weight is not part of the denominator. Anything
  that sums category_weights wants scoring_weight() from Grades/utils/enums.py
  instead; six sites already special-case Final and route the bonus exclusion
  through is_additive() rather than repeating the check.
- Scores, weights and target grades are floats everywhere. A number input for any
  of them needs step="any" -- without it the browser defaults to step="1" and
  rejects half marks, which is how that went unnoticed for so long.
- accounts.kind drives behaviour in exactly TWO places now: safe-to-spend counts
  only "spending" accounts, and "debt" marks money owed for the net worth figure.
  It is styling everywhere else. That note used to say "exactly one place" and
  advised adding an explicit column rather than loading a third meaning onto
  kind -- which is what counts_toward_net_worth is. Keep following it: the next
  per-account rule wants its own column too.
- counts_toward_net_worth is available on every kind and defaults to on, and is
  deliberately independent of safe-to-spend. Excluding a spending account from
  net worth does not change what you can spend: what you are worth and what you
  can spend before payday are different questions, and one setting quietly
  moving two figures is how a number stops being trusted. There is a test.
- A sinking fund's monthly figure is derived on every read, never stored:
  (target - saved) / months left. A stored schedule goes stale the moment a
  month is missed or the target moves, and the recovery from either is the same
  division. A contribution row exists only once the transfer has happened.
- Safe-to-spend subtracts a fund's contribution only while it is still a
  promise. Once transferred the money sits in a savings account, which
  safe-to-spend already excludes, so counting it in both places would take it
  off twice. Proven against real data: the safe figure is identical either side
  of a contribution.
- Safe-to-spend never counts money that has not arrived. Incoming standing
  instructions inside the window are excluded, and work done but not yet paid
  for is a second figure beside the first rather than part of it.
- A tuition payment writes exactly one ledger row, never one per course. What a
  course cost is a Grades answer -- credits times the term's per-credit rate,
  gross -- and is not meant to tie out against the ledger, which records the net
  of one payment covering a whole term.
- Per-credit rates are additive across a term's payments, so two instalments mean
  entering half the rate twice. credits_counted is stored rather than recomputed
  because it is what the bill was for.
- resolve_course lives in Grades/services/course_lookup.py now, with three
  callers: quick capture, the omnibox, and tagging an expense.
- FastAPI matches routes in declaration order, so any literal path under
  /courses/ must be declared above /courses/{course_id} or it is parsed as an id.
- Only Grades knows when a term runs, and it knows it per course: the term span
  is min(start_date), max(end_date) across the term's courses. Most courses carry
  no dates, so anything built on the span has to say when it is measuring from
  only some of them.
- A term blackout skips only recurring events that belong to a course. The same
  recurrence engine drives recurring payments and repeating tasks, and neither
  cares about reading break -- rent is still due, the bins still need taking out.
  That scoping is one `event.course_id is not None` check, and a test.
- skipped_dates is a JSON column, so dates must be serialised before assignment
  and the list rewritten whole. Assigning date objects into it once broke editing
  any event that had a cancelled date.
- Free blocks, week load and the crunch radar live in one service
  (Calendar/services/load_service.py) because they are one question asked three
  ways, off a single list_occurrences call. Overlapping classes are merged before
  the gaps are walked, or the end of one and the start of the next look like a
  gap that never existed.
- The study window (08:00-22:00, 30-minute floor) lives in UserPreferences, which
  is a JSON column parsed through a Pydantic model -- new keys are additive and
  need no migration.
- The figure beside a category on the course page is computed in Decimal from the
  recorded marks. 11.825 has no binary representation -- the nearest double sits
  below it -- so scaling through a float loses the hundredth before any rounding
  happens. The averaging engine deliberately does not do this: it would move the
  stored course average, and it was measured to change nothing.
- A repeat materialises differently per module, and the differences are the
  point: class times never become rows, payments become rows only once they have
  happened, tasks become rows a little way ahead so each can be ticked off.
- Deleting a shift found a second version of the orphaned-ledger-row fault.
  remove_shift bulk-deleted the ShiftRecordModel directly, which never touched
  the transactions a confirmed cash tip had already written -- the same shape as
  the orphaned tuition payment and paycheque, just one module later. Fixed by
  walking the tip's group_id before the record goes, mutation-tested by
  reverting to the bulk delete.
- A job's shifts come in two shapes and both are events. A one-off has no rule
  and is the default path, because part-time hours are rarely the same twice; a
  weekly pattern is the exception. set_class_schedule-style replacement is
  therefore narrowed to rows with recur_freq set -- otherwise saving a pattern
  silently deleted a fortnight of hand-entered shifts.
- The repeat on the job form is the PAYCHEQUE's, not the shifts'. Unlabelled it
  read as though it governed when you work; it is named and explained now, and
  safe-to-spend is what reads it.
- A shift is the engine's fourth consumer and cost nothing: it is an event with
  a job_id and a rule, exactly as a lecture is an event with a course_id and a
  rule. Free blocks already subtract any timed occurrence, crunch scores an
  unrecognised kind zero, and blackouts only touch course-linked events -- so
  work competes with study, carries no academic weight, and a reading break
  cannot cancel it, with no code that knows what a shift is.
- What an event cannot hold is what happened on one of its dates, because a
  repeating shift is one row expanded on read. shift_records is keyed by
  (event_id, on_date), the same identity EventOccurrence documents, and a row
  exists only once there is something to say about that date.
- An unconfirmed past shift counts at its scheduled hours and is flagged
  `assumed`. Dropping it would make a fortnight nobody did the admin for read as
  a fortnight nobody worked.
- A paycheque is the tuition payment in reverse: gross and named deductions on
  the cheque, only the net in the ledger. It stores a group_id rather than a
  transaction id, because the net splits across accounts and a deposit is
  already several rows tied by that column.
- expected_gross is frozen when the cheque is recorded and never recomputed.
  Re-deriving it would let a shift edited months later overturn a verdict
  already reached -- the same reason a tuition payment stores credits_counted.
- Reconciliation is per job kind. Hourly compares hours times rate, salaried
  compares the period amount and treats hours as context, contract compares
  nothing because you invoiced it. Converting a salary to an implied hourly rate
  would make a long week read as underpayment.
- Cash tips reach the ledger; tips paid through payroll do not, because they
  arrive inside the cheque's gross and a row of their own would count them
  twice. A cash tip with no account taking an income share still records, and
  reports tip_in_ledger false rather than failing -- logging your hours must not
  depend on budget setup.
- db.refresh() reloads a row from the database and discards pending edits. It
  silently undid a corrected gross in update_paycheque; db.flush() is what was
  wanted. The test suite is run with -W error::sqlalchemy.exc.SAWarning, which
  is how the duplicate cascade delete surfaced.
- Earned and paid are reported apart everywhere on the jobs page. Earned comes
  from the shifts and is a prediction; paid comes from cheques that arrived. One
  combined figure would hide a fortnight worked that nobody has paid for, which
  is the thing the page exists to surface.
- The effective hourly rate is measured over the periods cheques actually
  covered, not over every hour worked. Otherwise unpaid hours drag it down and a
  cheque still to come reads as a pay cut.
- WeekLoad now splits booked time into work_minutes and class_minutes.
  booked_minutes still means every timed event, so the split is additive.
- reminders.remind_at is naive LOCAL wall time, deliberately unlike every other
  DateTime in the app, which is naive UTC. "Remind me at 09:00" means nine
  o'clock where the student is and must survive a clock change, so the
  comparison goes through their timezone preference. Comparing against UTC
  would have fired a 20:00 reminder at 17:30 local -- two and a half hours early.
- Reminders have no scheduler and no push. The client asks what is due while it
  is open, and the banner says so, because a notification you half-trust is
  worse than one whose limits you know.
- Snoozing never moves due_date. Moving it would hide the deferral rather than
  record it, and would leave the completion-timing figure measuring against a
  date the student chose instead of the one they were given. The snooze history
  is a table rather than two columns, because the pattern is the point: three
  snoozes citing "waiting on lab partner" is the finding, and a latest-reason
  column cannot say it.
- Any service taking an `on_day` has to thread it into everything it calls.
  window_earnings did not, so whether a shift counted as past was judged against
  the wall clock rather than the day being reported on -- figures that drifted
  with real time and could not be tested at a fixed date.
- CLASS_KINDS does not protect shifts from a course timetable rewrite --
  set_class_schedule matches on course_id as well, and a shift has none. What
  CLASS_KINDS controls is what a ClassMeeting will accept. The first test of
  this was vacuous: adding SHIFT to CLASS_KINDS broke nothing until the test was
  rewritten to assert the rule that actually depends on it.
- That third case is where the editing bug was. materialise only ever adds dates
  that are missing, so edits never reached the 60 days of occurrences already
  written. resync_occurrences now divides on `done` rather than on the date: an
  outstanding occurrence follows the rule even when overdue, a completed one is
  never touched. Nothing marks an occurrence the student hand-edited, so a tweak
  to a future one is overwritten -- the accepted trade against edits appearing to
  do nothing at all.
- materialise takes `since` for the same reason. Its fourteen-day look-back is
  right on a first run, and wrong on an edit: moving a weekly chore from Monday
  to Thursday would otherwise back-fill last Thursday as an overdue task that was
  never assigned.
- completed_at is naive UTC and due_date is a plain local date, so the
  completion-timing figure converts through the student's own timezone before
  subtracting. Comparing them raw is not a rounding error: in UTC-6 anything
  finished after 18:00 local lands on the next UTC day, and evening is when most
  work gets done, so the whole figure would drift toward "late".
- effective_target moved from dash_services to Grades/utils/terms.py. Tasks needs
  it for the at-risk badge, and importing it from a service closed a loop through
  grade_service and grade_schedule back into task_service. The utils modules are
  pure -- no session, no models -- so anything may read them, and that is where a
  rule two modules share belongs.
- Risk bands are 0-5 mild, 5-10 moderate, over 10 severe, in percentage points
  below target, and only for current courses -- the rule collect_attention
  already applies, because a past course below target is history. A course with
  nothing recorded has no standing to be behind, which is why a term that has
  only just started badges nothing at all.
- The exam band needed no endpoint. fetchAgenda already expands repeats over any
  window, so it is that call with a filter on EXAM_KINDS.
- Priority is seeded once, when a grade first raises its task, and never again.
  sync_schedule_for_grade runs on every grade write, so re-deriving it there
  would silently revert the student's own choice each time a score was entered --
  the same failure as a repeating edit being overwritten. CATEGORY_PRIORITY lists
  only the exceptions, so a category added later falls through to the middle of
  the scale rather than arriving with no priority at all.
- A repeating rule carries its own priority and stamps it on each occurrence,
  and resync_occurrences propagates a change to the outstanding ones. Without
  that, a daily chore would need sixty corrections.
- Tasks reach the calendar as chips the client places, not through
  list_occurrences. placeTasks is deliberately separate from place: an event owns
  a span and is drawn with a height, a task is due at a moment and owns none of
  the day, so a deadline is a marker drawn above the blocks rather than a box
  competing with them.
- An ordinary task's due date pre-fills 23:59, because a deadline with no time
  means the end of that day. Clearing the date clears the time, which the API
  rejects on its own ("A time of day needs a date to go with it").
- The frontend has a test runner now: vitest 4.1.11, pinned, `npm test`. Its
  peer range accepts Vite 7, so nothing else had to move. Configured in its own
  vitest.config.ts rather than in vite.config.ts, which is a function that reads
  VITE_API_BASE_URL and builds the CSP plugin -- none of which means anything in
  a test run, and all of which would have to be satisfied for `npm test` to
  start. The suite pins TZ to America/Regina: every date here is a plain local
  date, so a run in UTC would pass while the bug being guarded against -- a date
  read one day early west of Greenwich -- is exactly what cannot happen there.
  Saskatchewan keeps no daylight saving, so the offset is the same all year and
  no test starts failing for half of it.
  IT FOUND A REAL BUG ON THE FIRST RUN, in the file with the quietest failure
  mode in the project. originOf() in securityHeaders.ts returned the *string*
  "null" for an API base with no scheme -- `new URL("localhost:8001/api")`
  parses, reading "localhost:" as the scheme -- so the `=== null` check meant to
  be loud about it never fired, and connect-src shipped a bare `null` token that
  matches no origin. Every API call would then be refused by the browser before
  it was sent, with the API's own logs staying clean. Omitting the scheme is the
  likeliest way to set that variable wrongly and the Pages dashboard is where
  nobody would see it. Fixed by requiring http/https; mutation-tested.
  Production was never affected -- the live connect-src names the Cloud Run URL
  correctly -- so this was a landmine rather than an outage.
  98 tests now, over the eight pure modules: dateUtils, money, securityHeaders,
  weekLayout, timeline, bonus, taskFields and dueTime. The one-off esbuild
  harnesses are retired -- place, placeTasks and timeline.ts are covered for
  real.
  A SECOND BUG CAME OUT OF WRITING THEM, in timeline.ts, and design/calendar.md
  had claimed an assertion covering exactly it. The floor width that keeps a
  one-day course visible and the axis bound are in tension, and the floor won:
  such a course on the last day of a hundred-day term was laid at 99% and
  widened to 1.5%, half a percent past a track nothing clips, reading as a
  course running past the end of term. It is slid back inside now.
  Worth knowing about the coupling the tests found: mutating hasSpecificTime to
  treat 23:59 as a real deadline fails a test in weekLayout as well as its own,
  which is the grid and the all-day band staying exactly complementary. That is
  the property that decides whether a task is drawn twice or not at all, and it
  now has something holding it.
- A ClassMeeting carries its own interval and its own first_on. Interval belongs
  on the meeting rather than the timetable because a weekly lecture beside a
  fortnightly lab is the ordinary case, and it suits what was already there:
  set_class_schedule turns each meeting into its own event row with its own rule
  columns, and Rule.interval was honoured all along.
- The interval was the easy half; the phase was the real gap. Every meeting in a
  timetable shares one starts_on, so without a per-meeting first date every
  fortnightly meeting is pinned to the odd weeks of term -- and labs commonly
  begin in week two, which would leave one a week out all term while looking
  correctly scheduled. first_on must fall on a day the meeting runs, or the
  engine skips to the next day that does and a week is counted wrong, and it is
  bounded by the term in the service rather than the schema, since only the
  service knows those dates. A weekly meeting ignores it: every week is an
  on-week, so there is no phase to choose.
- Monthly classes are not the same size of job. byday is weekly-only -- the
  Recurrence validator rejects it outright for any other frequency -- and monthly
  steps by day of the month through add_months, which yields nothing for a month
  too short for the date. So a class meeting "the second Tuesday" cannot be
  expressed, and a monthly class would land on whatever date it started on. That
  is precisely the BYSETPOS case the recurrence docstring names as the point to
  reach for a library rather than extend the rule. Decide which is meant before
  building: "every 4 weeks" is free today, "the second Tuesday" is not.
- A fixed-size button inherits padding: 7px 14px from the base .container button
  rule, so its glyph sits low and to the right unless the button sets
  display:inline-flex, padding:0 and box-sizing:border-box for itself. That has
  now caught the add-grade button, the weekday picker and the task checkbox.


---

## What the deploy leaves open, in the order it will bite
- The rate limiters key on the peer address, which behind Cloud Run is Google's
  front end, so every limit is one shared budget. Fix before step 39. D5.5.
  NARROWER THAN THIS ENTRY LONG IMPLIED, checked 2026-09-17: the throttle covers
  only /login and /register, at 8 attempts per 15 minutes, and 4 of the 5 users
  sign in with Google, which never touches it. So it bites password sign-ins and
  bursts of sign-ups, not everyday use. Still worth fixing before a wide invite;
  not the emergency it reads as. The fix is to trust Cloud Run's forwarded-for
  header in client_ip() (api/routes/auth.py:33), which deliberately does not
  read it today because an unvalidated X-Forwarded-For is worse than none.
- Backups exist in exactly one place: GitHub Actions artifacts, 90-day
  retention. A second copy in a GCS bucket or B2 was flagged and not done.
- The Dockerfile hardcodes uvicorn on 8000 instead of honouring $PORT, which is
  why --port=8000 is mandatory on every single deploy. One line, never done.
- A second Supabase project, ommqbgaasrusrlizzyzm, holds a full copy of
  everyone's financial data and password hashes from the step 34 restore test.
  Its password has been rotated. Delete it or treat it as production.
- Eight of the ten UptimeRobot monitors are meaningless: the Pages SPA fallback
  returns an identical 200 for every path, including invented ones, so they
  cannot fail. Two are real -- /health and the frontend root.


---

## Things that are easy to get wrong now that it is deployed
- A new table or column does NOT reach Supabase by deploying. The service runs
  with RUN_SCHEMA_ON_STARTUP=0, so run `python -m app._database.schema` against
  it as a deploy step. It is idempotent. Locally nothing changes.
- A push to main deploys the FRONTEND, via Cloudflare Pages. The API does not
  deploy itself; that is a manual gcloud run deploy with --port=8000.
- After any rollback, put traffic back on LATEST. --to-revisions pins the
  service permanently, and every later deploy then reports success and changes
  nothing. This has already happened once.
- SUPABASE_DATABASE_URL in .env is where the cloud string lives. Do NOT set
  DATABASE_URL to it: that is what the app reads, so local dev would point at
  the cloud and the app would come up looking wiped with nothing to say why.
- Local dev is still SQLite at data/app.db, deliberately, and the test suite
  REFUSES a remote TEST_DATABASE_URL unless TEST_DATABASE_ALLOW_REMOTE is set.
  conftest drops every table twice per run.


---

## Will this still be running in three years -- measured 2026-09-17
Asked directly. Capacity is nowhere near binding; what ends it is neglect.

What is fine, with room to spare:
- Database 12 MB of a 500 MB ceiling, at 5 users and 819 rows.
- Requests roughly 36k/month at 20 users, against 2M/month.
- Each nightly backup is 30 KB gzipped. Ninety of them is under 3 MB.
- GitHub Actions about 2 minutes a day, against 2,000 minutes a month.
- Artifact Registry holds 7 images in 95 MB total, not 7 x 85 MB: they share
  every layer but the thin app one, so a deploy costs a few MB, not an image.
- All 10 backend dependencies pinned exactly; the frontend builds from a
  lockfile. Nothing breaks from an upstream release on its own.

What will actually bite, roughly in order:
- SUMMER. Supabase free projects pause after about 7 days of no activity, and
  students stop using a school app in July. The thing quietly preventing it is
  the NIGHTLY BACKUP, which opens a real Postgres connection every day and reads
  as activity. That workflow is therefore load bearing for UPTIME, not just for
  recovery -- do not disable it to tidy up. Worth confirming Supabase's current
  pause-and-delete policy directly, since vendors change it.
- Backups are one copy, one place, 90 days. Corruption noticed in month four has
  nothing clean to go back to. They are 30 KB; a second destination costs
  nothing but the habit.
- The second Supabase project, ommqbgaasrusrlizzyzm, still holds everyone's
  financial data and password hashes. It is both a standing breach surface and
  the occupant of the spare slot on a 2-project free plan.
- Security drift. Pinned dependencies are excellent for reproducibility and
  terrible for patches, because nothing updates them. Over two or three years
  that is real CVE exposure in FastAPI, SQLAlchemy and the JWT library. A
  deliberate bump once a term, run through the suite, handles it.
- Bus factor: deploys are manual and need someone who can follow shipping.md.
  That is now written down, which is most of the fix.

Before more friends join, in order: fix the forwarded-for keying, delete the
second Supabase project, then make the second backup destination a habit.


---

## Housekeeping, learned the hard way 2026-09-17
- Docker on the dev machine reached 7.6 GB, of which 5.5 GB was build cache
  nothing ever clears. `docker builder prune -f` reclaimed 5.1 GB. Deleting a
  LOCAL image tag does not touch the registry copy, so it costs no rollback
  path. Local dev data was never at risk: docker-compose bind-mounts
  ./backend/data, so the SQLite file is on disk, not in a volume.
- README.md's Status block is STALE and contradicts its own opening paragraph:
  it says development is on grades-branch and that Calendar and Tasks return
  hardcoded sample dicts. Both are fully built and the app is in production.
  The first paragraph was rewritten 2026-09-17 to lead with the goal; the block
  under it was left alone and needs the same treatment.


---

## The production database, measured 2026-09-28
- 912 rows, 13 MB against a 500 MB cap, 26 tables, 86 indexes. Five users --
  four active, one soft-deleted on 2026-09-15, which purges 2026-10-15 on the
  first cold start after that date.
- Growth since 2026-09-14: courses 27 -> 30, grades 126 -> 206, accounts
  16 -> 28, transactions 97 -> 143, events 20 -> 51, tasks 11 -> 82. Jobs and
  spend_categories unchanged at 3 and 57.
- account_category_limits holds 11 rows. account_category_month_limits holds
  ZERO -- the per-month override shipped on 2026-09-25 and has not been used
  once. Worth knowing before building anything else on top of it; it may be a
  feature nobody wanted, or one nobody has found.
- The per-user split was not re-measured. Accounts rising by 12 is consistent
  with two more people signing in and having six each seeded on first read.
