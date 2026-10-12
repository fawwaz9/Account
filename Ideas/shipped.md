# Shipped

Everything below is built, deployed and verified. **Do not re-propose anything in
this file** -- that is what it is for. Entries keep the reasoning that produced
them, including the alternatives rejected and the traps found, because the "why"
is what stops a later change undoing a decision without knowing it was one.

Newest work is at the bottom of each group. Split out of `whats_next.txt` on
2026-10-02; open work moved to `next.md`.

---

## Features and fixes, oldest first
        Category limits can now differ for one month.
          The standing figure still carries into every month; a single month can
          be given its own, and says "this month only" on the row. The editor
          has a "This month only" tick that opens ALREADY TICKED on a row that
          is showing an override, so editing an overridden month does not
          silently rewrite the standing figure behind it.
          TWO TABLES, NOT A NULLABLE MONTH COLUMN. A unique index cannot enforce
          "at most one standing row" when the distinguishing column is NULL --
          Postgres and SQLite both treat NULLs as distinct, so the constraint
          would accept two standing limits for the same pair. Partial indexes
          could express it but are dialect-specific, and ensure_indexes walks
          the metadata generically.
          effective_category_limit tests `override is not None`, not truthiness:
          an override of 0 means "nothing this month" and a falsy check would
          fall through to the standing figure. Mutation-tested.
          Exercised against a VACUUM INTO copy of data/app.db: standing applies
          to both months, one month overridden leaves its neighbour alone,
          moving the standing figure moves the non-overridden month only, and
          clearing deletes the row rather than freezing today's value.
        LIVE as of 2026-09-25: API image da6ac93 on revision
          account-api-00017-kwt, frontend index-DKAVzYQ6.js, schema applied.
          Verified with controls: the new route answers 401 while a route that
          does not exist answers 404; five new strings found across five chunks
          (the bundle is split, so they are NOT all in one -- the endpoint is in
          the entry, limit_amount in the api chunk, "Record spending" in
          AccountDetailPage); a bogus control string found in none. No
          UndefinedColumn in the logs; CORS returns the Pages origin.
          NOT ROLLBACK-SAFE ON THE API ALONE -- an older API omits
          planned_is_derived and the limit fields, and `undefined === null` is
          false, so every category row would render $NaN. Both halves together.
        Record spending on the account page, and category limits keyed to it.
          Two changes to the account detail page. A Record spending button with
          NO ACCOUNT PICKER -- on an account's own page the account is not a
          question, and a picker there can only be answered wrongly. Expense
          only; income, transfers and the income-split deposit stay on the
          budget page where more than one account is in view.
          And category limits keyed on (account, category), which is the fix for
          what got the first attempt removed: a whole-budget limit was judged
          against one account's share of the spending, so a category split
          across two accounts always looked under budget.
          THE ACCOUNT'S TARGET IS NOW THE SUM OF ITS CATEGORY LIMITS, but only
          when it has any. Savings ($9,000) and Money Lent ($1,200) carry real
          targets and would never be itemised by category; deriving
          unconditionally would report both as budgeting nothing. One pure
          function, planned_for_account, read by both the account page and the
          budget summary so they cannot disagree. It keys on the list being
          EMPTY, not on its sum being falsy -- a single limit of 0 is a budget
          of nothing, and a test fails on the falsy version.
          The budget page shows derived targets read-only and no category limits
          at all. Both absences are load-bearing: one number with two places to
          set it is where the last edit quietly wins, and a per-account limit has
          nothing to be judged against on a page spanning every account.
          THE ROW LAYOUT BROKE THE SAME WAY TWICE and is now pinned by
          categoryRow.test.ts. Adding a bar gives a row a third child, and
          justify-content on the li only works while a row is exactly two spans.
          jsdom has no layout engine, so no test that renders the component can
          see this -- it reads the stylesheet from disk instead.
          Mutation testing found a real integrity bug: without clearing
          account_category_limits first, deleting a category fails with FOREIGN
          KEY constraint failed. Both deletes clear it now, both tested.
          Exercised end to end against a VACUUM INTO copy of data/app.db over
          the real 18 accounts, 44 categories and 8 targets -- derive, agree
          across both screens, clear, revert -- with every row count identical.
        Category spending limits were built, shipped, and ROLLED BACK.
          A standing monthly_limit per category with a per-month override, and
          red/amber/green colouring of "Where it went" against it. Deployed on
          2026-09-24 and removed the same day: the user judged that limits
          belong in the spending-account section only, where Planned spend
          already sets a per-account target and draws the same bar. DO NOT
          RE-PROPOSE per-category budgets, caps or category colour coding.
          "Where it went" is a record of where money went; "was that more than I
          meant to spend" is answered one level up, against the account.
          THE SUPABASE COLUMN AND TABLE WERE DELIBERATELY LEFT IN PLACE.
          spend_categories.monthly_limit is nullable and every row is NULL;
          category_budgets exists and is empty. Neither is referenced by any
          code now. Dropping a column and a table in production is irreversible
          and buys nothing measurable, so they stay -- documented here so the
          next person reading the schema does not mistake them for something in
          use. The same is true of the local data/app.db, which the dev server
          migrated on reload.
          WORTH KEEPING FROM IT: the row layout fix. "Where it went" had
          justify-content on the li itself, which only works while a row is
          exactly two spans; the padding increase from that work is kept, the
          rest reverted with the feature.
        Budget and Account pages went narrow, and the cause was my own claim.
          .budgetPage and .accountPage each carried max-width:980px that had
          NEVER APPLIED in production: .container on the same element sets
          max-width:none (to defeat Tailwind's container utility), both rules
          are unlayered and one class of specificity, so the winner was decided
          purely by which file the bundler emitted last -- globals.css. Making
          the routes lazy changed the module graph, the order flipped, the dead
          rules woke up, and both pages clamped to 980px.
          CORRECTION TO THE ENTRY BELOW: it says the stylesheet was unchanged
          and that the ordering differences were inert. The first half is true
          and the second half is false. cssCodeSplit:false keeps one FILE, which
          preserves the rule set, NOT the order within it -- and order is what
          breaks a tie between two unlayered rules of equal specificity. An
          identical rule multiset was the evidence I leaned on, and it cannot
          see this class of bug at all.
          Fixed by deleting both dead max-width declarations rather than by
          restoring the order, because an appearance that depends on bundler
          emission order is not a fixed appearance -- it is the same bug waiting
          for the next import to move. .accountPage keeps position:relative,
          which is load-bearing.
          GUARDED: pageWidth.test.ts fails if any class used beside "container"
          declares its own max-width, with a control asserting the scan really
          sees budgetPage and accountPage so it cannot pass by reading nothing.
        LIVE as of 2026-09-24: frontend 972fff5, entry index-BTL-dvNy.js,
          stylesheet style-H5jp_U0I.css. Frontend only -- no schema step, no
          image, no Cloud Run deploy, because nothing outside
          Application/frontend/ changed.
          Verified on the deployed site, not locally: entry 253,589 raw /
          81,200 gzipped against 486,867 / 135,705 before; "Loading your
          accounts" absent from the entry and present in BudgetPage-DZe6-Pmd.js;
          all 20 referenced chunks served; the preconnect origin and the
          connect-src origin identical; 6 of 6 headers; / /budget /calendar all
          200. THE DEPLOYED STYLESHEET IS 90,773 BYTES WITH AN IDENTICAL RULE
          MULTISET to the pre-split one -- the cssCodeSplit decision holding up
          in production and not just in the local build.
          A CHECK THAT COULD NOT FAIL, caught by its control: Pages serves
          index.html for any unmatched path, so a MISSING chunk returns 200 with
          content-type text/html rather than 404. Asserting status 200 on a
          chunk therefore proves nothing -- a deleted chunk passes. Compare
          content-type instead; a real chunk is application/javascript. Written
          up in ROLLBACK.md, because it also means a 200 in a log is no evidence
          a chunk exists.
          NOT VERIFIED FROM HERE, and worth a look in a browser: the exact error
          string a stale chunk produces. The server side is confirmed (200,
          text/html, nosniff, so the module is refused and the import rejects),
          and the four phrasings matched in chunkErrors.ts are the documented
          ones, but no browser was driven to check.
        The first download is 40% smaller, and the API handshake starts earlier.
          The app had no code splitting at all: App.tsx statically imported all
          ten pages, so the login screen downloaded Grades, Calendar, Tasks,
          Jobs, Budget and Settings before it could draw a password field, and
          paid it again on every cache miss. The nine signed-in pages are now
          lazy() routes behind one Suspense in MainLayout; LoginPage and the
          shell stay eager, because an unauthenticated visitor needs nothing
          else and deferring them would only add a round trip.
          MEASURED, not estimated: entry chunk 486,867 -> 253,561 raw and
          135,705 -> 81,199 gzipped, across 22 files instead of 1. Proved with
          controls rather than by reading the build log -- "Loading your
          accounts" (from BudgetView) is absent from the entry and present in
          BudgetPage's chunk, so the grep that says so is known to work.
          THE STYLESHEET IS UNCHANGED, and that was the point of setting
          build.cssCodeSplit: false. Vite would otherwise emit a stylesheet per
          chunk, loaded in whatever order pages were visited, and this app
          cannot take that -- see design/README.md. Verified as identical size
          and identical rule multiset; the only difference is ordering, and both
          moves are provably inert (Tailwind's rules are all inside @layer,
          which ranks below unlayered CSS whatever the source order, and every
          dashboard.css selector is defined exactly once in the whole file).
          index.html now carries a preconnect to the API origin, so DNS, TCP and
          TLS happen alongside the bundle download instead of after it. It comes
          from originOf() in securityHeaders.ts -- the same function connect-src
          uses -- so the origin the browser warms and the origin it is allowed
          to call cannot drift. crossorigin is on it deliberately: the calls
          carry an Authorization header, and an anonymous connection cannot be
          reused for a credentialled one.
          THE ONE NEW FAILURE MODE, named because it did not exist before: a tab
          open across a deploy holds chunk names the new release does not serve.
          It reloads itself once, guarded by a timestamp rather than a
          "did it work" flag -- a flag needs a success signal and a missed
          signal is an unescapable reload loop. A second failure inside ten
          seconds falls through to a crash screen that says the app was updated
          rather than that the page broke.
          A COMMENT CHANGED THE CSS. Tailwind scans source files for candidate
          class names and cannot tell prose from markup, so a bare utility word
          written in a comment in chunkErrors.ts added a real, unused
          text-transform rule to the production stylesheet. Caught only because
          the stylesheet was being compared byte for byte.
          NOT DONE, and deliberately: narrowing what each mutation invalidates,
          and a request cache. Both can show a stale number that looks like a
          fresh one, and safe_to_spend reads Jobs as well as Finances, so the
          invalidation map crosses a module boundary the budget hook cannot see.
          The runRecurring-before-reads waterfall in useBudget is also still
          there -- free to fix, but it edits the ordering rule safe-to-spend
          correctness depends on.
        LIVE as of 2026-09-22: image ca86a3e, revision account-api-00012-xfk.
          One deploy, carrying the two jobs paid-vs-earned commits (25e42fd,
          49c129e) that had been sitting on main undeployed since 2026-09-17,
          plus ca86a3e itself. NO SCHEMA STEP: nothing under app/_database/
          changed, checked with the step 11 diff rather than assumed.
          Safe to roll back on its own in both directions -- the reasoning is
          written out in ROLLBACK.md rather than here.
          Verified end to end on a COPY of data/app.db before deploying: over
          the real three jobs, every per-job breakdown sums to its window
          headline -- $795.25 gross, $177.82 deducted, $617.43 net -- which is
          precisely the bug 49c129e fixed, so the check would have caught its
          reintroduction.
          NOTE: "This month" and "This term" still read identically, because
          Fall began Sep 1. Known coincidence, not a fault; it stops on Oct 1.
        A test that was only passing on what the last run left behind.
          test_ensure_indexes_is_safe_to_run_twice wrote its indexes on the test
          session's connection and then asserted through the APPLICATION engine,
          which conftest deliberately binds to a throwaway file so the suite can
          never reach the live ledger. Two different databases: it passed on
          indexes an earlier run had left in that file, and failed the moment
          the file was deleted -- which is how it surfaced, as a one-off red on
          an otherwise green suite. Now asserts through the same connection it
          wrote on, which is also the only bind that is safe against Postgres:
          reading through the engine opens a second connection outside the
          test's transaction, the deadlock the test above it warns about.
        Jobs leads with what was PAID, not what was earned. The window cards are
          money that arrived -- net paid as the headline, "X gross, Y deducted"
          under it, and a per-job breakdown of pay. Everything the shifts only
          predict moved into Estimates, which is the old "Not paid yet" block
          renamed and widened rather than a third section beside it.
          The Past week card is gone: pay does not arrive weekly. The week
          window is still computed and still on the wire because
          test_earnings.py makes 13 assertions through it -- a fixed 7 days
          keeps the expected shift counts obvious -- it is just not drawn.
          JobEarnings gained gross_paid/deducted/net_paid. The window always had
          a paid total but no way to say which job it came from, so a per-job
          breakdown could only ever show earned.
          A BUG FOUND WHILE DOING IT: the per-job loop skipped any job with no
          shifts and nothing earned, so a job paid in the window for work done
          before it opened -- the normal case -- was dropped from the breakdown
          while the window total still counted its money. The rows disagreed
          with the headline above them and every existing test stayed green.
          NOTE: "This month" and "This term" read identically until Oct 1,
          because Fall began Sep 1. That is the same coincidence behind the
          original "term is the same as past week" report, and is not a fault.
        A ticked-off task stays ticked off. The gradebook used to derive a
          task's done flag from its grade in BOTH directions, so any save of a
          grade with an empty score box ran set_done(task, False) -- which nulls
          completed_at and un-archives. Opening a grade to fix a typo in its
          name put a lab you ticked off three weeks ago back in the list, with
          no record of when it was done. A score still checks a task off;
          nothing unchecks one now. Clearing a score leaves the task closed,
          which reverses the old behaviour on purpose: clearing a score is about
          the gradebook, not about whether you did the work.
        LIVE as of 2026-09-17: image e494729, revision account-api-00010-ktd.
          Three deploys that day: 18e3376 (links, term dates, cheapest path --
          the only one needing a schema step, for courses.links and
          users.first_year_calendar_year), 89a7c22 (the pts/h ranking) and
          e494729 (the task-reopen fix, API only).
          STILL TRUE AND WORTH DOING: nobody has set the first-year anchor, so
          Term Budget and the Jobs term stay quiet until Settings gets one. It
          suggests 2024 from your dated courses. That is designed behaviour, not
          a fault -- an unanchored term must not silently become year 1.
        Course resource links. Canvas, Piazza, PrairieLearn and anything else,
          as chips above the insights row with one muted underlined control.
          Stored as JSON on the course and reassigned whole, because SQLAlchemy
          does not see a mutation inside a JSON column. http/https only, checked
          on the server: these render as anchors, and a stored javascript: URL
          is script execution on your own page.
        Fixed term dates, anchored to one setting. courses.year is the SCHOOL
          year, 1 to 10, so "Fall starts Sep 1" had no calendar year to attach
          to. Settings now takes the year first year began and every term
          derives from it. Term Budget measures the term rather than assembling
          a span from whichever courses happened to carry dates -- which is why
          21 of 27 courses could not be measured before. The class timetable is
          carved out and still uses each course's real dates, or it would invent
          three lectures before term and three after.
          NOTE: your term_label reads "2025-2026" while your year-3 Fall courses
          run September 2026. The label is a year stale, so the anchor is
          suggested from the dated courses instead -- it offers 2024, which is
          right. Worth fixing the label too.
        The term heading comes from the anchor too (1ceb30f). It read "Fall
          2025-2026" above a span computed over 2026, because the heading came
          from the free-text term_label and the dates from the anchor. term_name()
          now derives both from one fact. Winter keeps the school year's calendar
          year, so January 2027 still reads 2026-2027 -- tested, and the mutation
          using the term's own year fails it. term_label survives only as the
          fallback for a user with no anchor.
        Cheapest path to a target. Ranks what is left in a course by how much of
          the final average each item still controls, with a per-hour rate where
          the task carries an estimate. Top three only, ranked by points per
          hour and then by points -- asked for directly, and it replaced an
          earlier rule that ranked on points alone.
          NOTE: that earlier rule existed for a reason, and the reason has not
          gone away. An item with no estimate has no rate, so it ranks below
          every item that has one. With 1 estimate across 23 outstanding items
          that means STAT_V 201 now shows Lab 3 (4.3 pts, estimated) above the
          Final Exam (45 pts, not estimated). The other six courses have no
          estimates at all, so they rank on points exactly as before. Add
          estimates and the ranking becomes what it claims to be; leave them off
          and the rate has nothing to rank.
        The browser tab says Account rather than App.
        Editing a task at all. Every row has an Edit button and a task on the
          calendar opens the same dialog, which also carries the Complete
          button. Before this a task could be ticked, snoozed, re-prioritised
          and deleted -- and a title typed wrongly could only be deleted and
          retyped. PATCH /tasks/{id} and updateTask both already existed; there
          was no dialog calling them.
          The dialog is deliberately tighter than the other fifteen: it holds
          eight fields where most hold three, so the compact spacing is scoped
          to it rather than loosened from .calForm. The fields a grade owns are
          drawn as muted text with no border or fill -- a disabled input still
          looks like an input, which reads as broken rather than as belonging
          to something else.
        A calendar task chip opens that editor instead of ticking the task off.
          The calendar could previously do exactly one thing to a task, so a
          click meant to look at one finished it. One-click ticking from the
          calendar is the cost; it is two clicks through the editor now.
        Editing ONE occurrence of a repeat, which needed a new column to be
          safe. Occurrences were identified by their due date, so moving
          Monday's chore to Wednesday made Monday look unwritten and the next
          page load put a second copy back on it -- and the stale sweep deleted
          the moved one. tasks.occurrence_date is the date the rule produced and
          nothing but the rule writes it; due_date is where it currently sits.
          Editing the RULE still rewrites outstanding occurrences, which is what
          a repeat is for, and the dialog says so.
        A time on a grade's date, and a length for one on the calendar. A lab
          due at noon and a 14:00 midterm running two hours are each entered
          once in the gradebook. A length rather than an end time: "two hours"
          is what you know, and an end derived from a start cannot end before
          it. Both are optional and blank by default -- a guessed 09:00 reads
          on the calendar as a fact.
        A Close button on the event popup. It had none: Modal has no x and does
          not close on a backdrop click, and the grade branch rendered an
          explanatory sentence and no buttons at all. The nearest thing to a
          dismiss on the other branch was "Cancel this one", which cancels the
          lecture.
        An income split editor and a category manager, side by side under Where
          it went. The split shows every account at once with what each share
          comes to as a percentage of income -- these are ratios, so a single
          field in isolation cannot tell you what it means. Categories can be
          added, renamed, archived and deleted; all four endpoints had existed
          since categories were built and nothing had ever called three of them.
        Where it went now always renders. It used to appear only when there was
          spending to show, which hid both of those controls in exactly the
          month you are most likely to be setting categories up.
        Net worth, replacing the plain Total that summed every balance -- which
          counted a credit card as savings and money someone else was holding
          as money in your pocket. Sits beside safe-to-spend at the top of the
          page, with a Debt line under it when there is debt. Computed on the
          server, because the dashboard shows the same figure and a rule about
          which accounts count is the kind that drifts when written twice.
        counts_toward_net_worth, available on every account kind and on by
          default. Money lent out, a joint account or anything held for someone
          else can be taken out of the total. Deliberately independent of
          safe-to-spend: excluding a spending account from net worth does not
          change what you can spend, because those are different questions.
        Creating, editing and deleting accounts, with the two roles the app
          cannot do without protected: the last non-archived spending account
          and the last savings one refuse to be deleted, archived, or have
          their kind changed away. Protection reads the kind, not the name, so
          renaming Spending to Chequing keeps it and holding three spending
          accounts lets any two go.
        A debt account kind, for money owed. Its balance is the ordinary signed
          sum of its rows, so it reads negative and a total that adds every
          balance subtracts debt without a special case. Shown in red, with the
          kind still written out beside it.
        The recurrence engine, and class times as its first consumer.
        events and tasks tables. Anything dated renders on the calendar.
        Due dates on grades, and the choice of what a date means: a task that
          closes when the score lands, or a calendar block with nothing to tick off.
        Midterm and final event kinds, themed as exams rather than class blocks.
        Course flags: no_final, transfer_credit, archived, with the credit and
          average rules each flag changes.
        Recurring transactions in all four kinds, on the same engine as class times.
        Repeating tasks -- the engine's third consumer, so all three now run on it.
        Estimated minutes, tags, course-code categorisation, check-to-archive.
        One tokenizer: course code, date word, duration, amount, score/max.
        Quick capture on the Tasks page, and the omnibox on top of the same parser.
        A week view on the calendar: 24 hours, overlapping classes side by side.
        The account page in two columns, with the target bar dividing them.
        Bonus as a real category: its weight sits outside the 100 the course is
          marked out of, and its marks are added on top, banked against the whole
          course rather than the graded slice.
        Bonus on screen: the course badge, "+2.50" in the strip rather than a
          fraction, a gold row for a grade above its own max, and forms that stay
          silent until a score actually goes over.
        Best/worst band: where a course can still finish, projected per unmarked
          item rather than per category, hidden once nothing is outstanding.
        Archived courses marked and hideable, the flag finally read.
        A final's card distinct from a midterm's.
        Fractional scores and weights, which the columns always allowed -- the
          inputs defaulted to step="1" and refused anything else.
        course_id on transactions, so a textbook can say which course it was for.
          Tagged by dropdown, by the description, or through the omnibox.
        Pay Tuition: a rate times the term's credits, plus fees belonging to no
          course, less deductions that never touched the account. One ledger
          line for what left; the gross is what the course pages report.
        What a course cost, on the course page: its gross tuition share plus
          anything bought for it.
        Correcting and removing a tuition payment, its ledger row moving with it.
        Dropped marks: a grade kept on a course but left out of every average,
          for when a professor drops the two lowest.
        Term budget: what a term has cost, measured over the term's own dates
          rather than a calendar month.
        Free blocks, week load and the crunch radar: three readings of one
          window, with a study-hours window you set in Settings. The calendar
          opens on the week, and time already gone is not offered as free.
        Blocked periods: a reading break entered once and skipped by every
          class, plus per-event dates blocked while setting a repeat up.
        Editing a repeating task reaching the occurrences it already wrote.
          Outstanding ones follow the rule, completed ones stay as the record
          of what was done, and an edit no longer back-fills the past.
        Due times on the calendar: placed on the clock in the week view, shown
          on the chip in the month view, and enterable on an ordinary task --
          a due date now pre-fills the end of that day.
        Exams coming up, above the work: a read-only thirty-day band on the
          tasks page, since revision is what fills the fortnight below it.
        At-risk first: tasks from courses below target lead their own date
          group, badged by how far behind the course is.
        How early or late work actually gets finished, over a rolling week and
          the month to date, with the signed average and the on-time share
          side by side because each hides what the other shows.
        Priority, 1 to 5. Coursework is seeded from its grade category -- a
          final at 5, a midterm or project at 4, everything else at 3 -- and is
          the student's to change from there. Repeating chores carry one on the
          rule, so sixty occurrences are not corrected one at a time.
        The list ends at the fortnight. What lies past it is a count rather than
          a standing section: a task three weeks out is not work you can start.
        The tasks page in two columns, split by what you do with each side: the
          work in front of you on the left, the things that take more than a
          line to set up on the right. One column on a phone, ordered by
          urgency rather than by which column it came from.
        Jobs, first stage: a job with the kind of pay it actually has, shifts
          as events on the calendar, and confirming what was really worked.
        Jobs, second stage: paycheques. Gross and named deductions stay on the
          cheque, only the net reaches the ledger and splits by income share,
          and what the hours said it should be is checked against what arrived.
          Cash tips reach the budget; tips paid on the cheque are already in it.
        Jobs, third stage: earnings. Week, month and term in hours and money,
          the effective rate once tax comes off, work hours beside class hours,
          and what has been worked but not yet paid for.
        Snooze with a reason. A task leaves the list until a date and comes back
          in its own place, because the due date never moves -- and every snooze
          is kept, so three citing the same thing reads as a blocked task.
        Reminders, as opposed to tasks: something that notifies rather than
          waits. A banner while the app is open, plus a browser notification
          where permission was given, and the limit said out loud rather than
          hidden.
        Term timeline: every current course on one axis, with today marked and
          the ones carrying no dates named rather than quietly left out.
        Class times that are not weekly, per meeting: a weekly lecture beside a
          fortnightly lab, each with its own first week -- without which every
          fortnightly meeting would be stuck on the odd weeks of term.
        Safe to spend: what is in a spending account, less what is committed,
          over the window that ends at your next cheque. Work done but not yet
          paid for is shown beside it, never inside it.
        Sinking funds: what something costs and when it is due, with the monthly
          figure derived rather than stored, so a missed month raises the rest
          instead of moving the date. Setting aside writes a real transfer.
        Subscription audit: expenses with no standing instruction behind them,
          grouped by description, flagged once the amount and the gap between
          charges both agree on a rhythm, each with a standing instruction
          already filled in to confirm.
        Shifts entered one at a time, which is how part-time work arrives. The
          weekly pattern is still there for jobs that repeat, and saving one no
          longer deletes the shifts you typed in by hand.
        Removing a one-off shift, for a mistake or one never confirmed. Takes
          any cash tip already in the ledger with it, and asks first only when
          something was actually confirmed.
        Deleting an account is a request rather than an execution: the row
          is marked, every session ends at once, and nothing is removed until
          thirty days have passed. Signing in still works until then, because
          with no email system a blocked sign-in is an account nobody could
          ever restore.
        The database enforcing its own rules: every foreign key and filter
          column indexed, the four unique constraints that were only ever
          Python checks, WAL and a busy timeout, and foreign keys actually on.
          Turning enforcement on is what found the two real bugs behind it.
        Sixteen dead files gone, each checked for references first rather
          than deleted for being empty -- including one that printed every
          user's name and email to stdout at import. requirements.txt cut from
          a 58-line pip freeze to 9 direct dependencies, and pytest, which the
          suite has always needed, declared for the first time.

        Nine audit findings where the server answered confidently and wrongly:
          a rejected edit that had already been applied, a search where "_"
          matched every course, a GET that queued a write, and an empty list
          standing in for both an impossible date range and an unknown account.

        The grades dashboard from 81 queries to 5, with the payload verified
          byte-identical before and after. Deposit allocations compared in
          whole cents, so a split can no longer be a cent more than the money
          that actually arrived.

        A course with nothing marked reports no average rather than zero,
          which also stopped the dashboard naming a course you had not started
          as your weakest one. A course that genuinely averages zero still
          says zero -- that distinction is the whole point.

        Eight frontend audit findings: a blank white page on every cold load,
          a greeting addressed to nobody, a swallowed budget error, half-typed
          input wiped by a background refresh, a bulk-grade row losing a
          keystroke when another row was removed, and the client second-
          guessing a percentage the server had already rounded.
        The task priority badge shows just the number, centred. The select's own
          text is transparent and an overlay span carries the digit, so the
          closed badge is not left to whatever a fixed-width overflow:hidden
          happened to clip "3 · Normal" down to -- the open dropdown still
          spells out what each step means.
        Standing instructions beside what is coming up, rather than stacked --
          equal columns, so the near-term reason to change a rule sits next to
          the rule instead of below the whole list of them.
        Printing a term: a print stylesheet and window.print(), so a past or
          future year -- never the current, still-moving one -- can be saved
          as a PDF worth keeping.
        Category blind spots: a category -- labs, quizzes, midterms -- pooled
          across every graded course and compared to the student's own overall
          average, reported only once it is 2+ points behind in two or more
          courses, so one hard class cannot trigger it alone.


---

## Dead code removed, second pass 2026-09-23. 102 lines out, 5 in.
        Each verified unreferenced before deletion, not deleted for looking
        unused -- and one candidate survived the check: `.space-between` looked
        dead in a first sweep that was itself broken, and a second sweep found
        it genuinely unused as a class while every other hit was the CSS value
        of the same name.
        Gone: get_all_users (an unfiltered query over every user row, left when
        the user-listing endpoints were removed -- the route went, the service
        did not); weekday_code in the recurrence engine; app/temp_data/, holding
        only a stale .pyc of a module deleted in the first pass;
        _database/design.txt, 95 lines of Postgres DDL nothing referenced and
        which a reader could now mistake for the real schema; and the five
        dashboard buttons that only called navigate() somewhere the sidebar
        already links. Those buttons had gone stale as well as redundant -- they
        never listed Jobs. Removing them orphaned .grid, the whole .widget
        family and .widget-link, dead since the first commit in July: 54 of the
        113 lines of dashboard.css.
        ADDED: httpx==0.28.1. Three test files use Starlette's TestClient, which
        needs it, and it ships only under fastapi[standard] -- so it was in the
        working venv by accident and missing from a fresh clone. The same gap as
        the undeclared pytest, and the check that would have caught it predates
        the tests that introduced it. A fresh venv from requirements.txt alone
        now runs all 40 of them; uninstalling httpx from that venv fails all
        three files at collection.


---

## Duplicate helpers consolidated, 2026-09-23.
        money() existed in four services and today() in nine, byte-identical
        every time, and earnings_service imported money from paycheque_service
        rather than write a fifth copy -- a service importing from another
        service, which is the layering rule becoming a suggestion. Both now
        live in app/shared/ beside the tokenizer and the audit log, and
        earnings_service reads the shared one.
        Mutation-tested, and this is what makes it a consolidation rather than
        a tidy-up: changing the shared money() ONCE fails 20 tests spread
        across Jobs (earnings, paycheques) and Finances (safe-to-spend, sinking
        funds, subscriptions). Changing today() fails tests in Tasks. Both
        module families genuinely read the one function now.
        FOUND WHILE DOCUMENTING IT: the `+ 0.0` in money() does less than it
        looks. It normalises an input that is already -0.0 -- which is what
        stops a balance of nothing reading as "-0.00" -- but it runs BEFORE the
        rounding, so a small negative that rounds away keeps its sign:
        money(-0.004) is -0.0. Moving the addition after the round would close
        that and would change no other value, but it is a behaviour change
        rather than a move, so it was deliberately left out of this commit.
        tests/test_shared_helpers.py pins both halves.
        On the frontend, features/budget/dates.ts is gone: pad, isoDate and
        firstOfMonth were byte-identical to shared/utils/dateUtils, localToday
        was today under another name, and dateUtils' own header already said
        the two matched rather than removing one. Six importers moved. The
        equivalence was proven by a throwaway vitest file asserting each pair
        agreed while both modules still existed, then deleted with the module.
        Also routed SinkingFundModal and AddMoneyModal through formatMoney --
        both rendered money with a raw toFixed(2), so a four-figure amount read
        "1234.50" where the rest of the app says "$1,234.50", in a file whose
        own docstring calls itself the one place that decides how money reads.


---

## Three dead endpoints removed, 2026-09-23. 137 routes, was 140.
        GET /courses/{id}/statistics, /average and /letter-grade had no caller
        in the frontend -- no builder for any of them in endpoints.ts, which is
        the one place a path is constructed -- and no test anywhere. /statistics
        took its service function with it: get_course_statistics existed only
        for that route and returned {course_id, course_code, average}, a strict
        subset of what GET /courses/{id} already answers.
        CHECKED BEFORE REMOVING, because the real risk of deleting an endpoint
        is making data unreachable rather than breaking a caller: the Course
        schema carries both `average` and `letter_grade`, and the frontend
        already reads course.letter_grade straight off the course in
        CourseList. calculate_letter_grade and calculate_current_average keep
        their callers -- 2 and 8 respectively -- so only the routes went, not
        the arithmetic.
        Audit #51 was about two of these: GET /average and /letter-grade
        mutating the session by assigning to a mapped column inside a read. The
        finding was fixed long ago; the endpoints it was about are now gone
        entirely.


---

## A month step costs one request, 2026-09-24.
        The budget page loaded eight things and wrote one, and re-ran the lot
        every time the month picker moved -- where only fetchBudgetSummary takes
        a month at all. The other seven are the same figure whichever month is
        on screen: two are windowed on today() and five take no date. The write
        is runRecurring, which is what makes "open the app and last month's rent
        is already there" work without a scheduler -- genuinely needed on the
        first load, and pointless between two clicks, because no time passes.
        A BONUS THAT WAS NOT THE POINT: `loading` gates the whole page body, so
        stepping the month used to hide the accounts, the ledger and the charts
        to fetch one figure. The summary now keeps its previous value while the
        new one arrives.
        Mutations are deliberately untouched -- reload() still catches up and
        refetches all eight from all 18 call sites. Narrowing that is where the
        staleness risk is: today's full reload is crude but correct, and a
        stale balance on a money page is the wrong answer that looks exactly
        like a right one.
        VERIFIED BY COUNTING, because nothing on screen looks different either
        way. useBudget.test.ts asserts a month step calls fetchBudgetSummary
        once and the other seven not at all, and that reload() still calls
        everything. Mutation-tested against the old hook: the two tests about
        the change fail and the two about unchanged behaviour pass, which is
        what says they measure this and nothing else.
        This needed jsdom and @testing-library/react, the first hook test in
        the project. Per-file via a `// @vitest-environment jsdom` docblock, so
        the eight pure modules stay on node. NOTE: installing under
        --legacy-peer-deps (the npm arborist workaround) does not install peers,
        so @testing-library/dom had to be added by hand afterwards -- expect
        that for anything else installed that way.
        AUDIT #35 IS STILL OPEN. It describes two different cases -- refetching
        across pages, and reload() after a mutation -- and this fixed neither.
        AND IT SHIPPED FEELING SLOWER, which is the lesson. `loading` was the
        only feedback on that page, and the month step deliberately stopped
        setting it -- so a click changed nothing on screen until the figure
        landed, where before the page visibly flashed. Eight requests down to
        one is not something anyone can feel; the missing flash is. Reported as
        "if anything it feels slower" and it was right.
        Fixed by reporting on the two panels a month actually changes --
        PlannedSpend, which owns the picker, and WhereItWent -- rather than on
        the page. They keep their previous figures and dim while the new ones
        arrive. Keyed on aria-busy rather than a class, so the attribute that
        tells a screen reader the region is updating is the same one that dims
        it, and there is one state rather than two that can disagree.
        THE GENERAL RULE, worth having before the next optimisation: removing
        work can still read as slower if it also removes the only sign that a
        click registered. Feedback is not what the page was waiting on -- it is
        what the person was.


---

## Deployment -- DONE. The app is live.
- https://account-2a7.pages.dev, talking to Cloud Run in us-west1, talking to
  Supabase Postgres 17.6 in us-west-2. A second person is using it.
- Steps 1-37 of Ideas/deployment.md are done. Only 38 (watch it for a week) and
  39 (invite the rest) remain, and both are time passing rather than work.
- Read Ideas/shipping.md to BUILD AND SHIP a change. It is the loop -- build,
  verify, deploy, record -- in the order the steps have to happen, and every
  rule in it names the day it cost something. Written 2026-09-17 and used for
  real on the deploy the same day.
- Read Ideas/ROLLBACK.md if something is broken. It is written to be read while
  stressed: commands first, reasoning second.
- Read Ideas/deployment.md for how it got there, and Ideas/plan-a-decisions.md
  for why each choice was made and what would change its mind.


---

## Settings, phases 0-4 LIVE 2026-10-01
- API image 147d08b, revision account-api-00019-lcb. Frontend from the same
  commit. 946 backend tests, 157 frontend.
- Phase 0 fixed a live bug: every Settings save was resetting the preferences it
  did not mention, timezone included, because UserUpdate.preferences was typed as
  the full UserPreferences and every field of that has a default. It now takes a
  UserPreferencesPatch and the merge dumps exclude_unset. Audit #58's first half
  is closed; the six preferences nothing reads are still unexposed on purpose.
- Phase 1 put Account and Password side by side, and gave the three cards an
  actual card -- `.card` had been in that markup since the first commit and never
  existed in any stylesheet.
- Phase 2 grouped the rest into Academic, Calendar and Financial tabs. First real
  tablist in the app. The study window moved to Calendar; Financial holds Income
  split and Edit categories, which the Budget page still offers too.
- Phases 3 and 4 followed the same day. The timezone control is in the Calendar
  tab: a <select> off Intl.supportedValuesOf with a short Canadian fallback,
  seeded from the STORED zone and never from the browser's guess -- the guess is
  offered by a button instead, so opening Settings in another city cannot
  silently repoint every reminder on the next save. Blocked periods got its
  entry point there too.
- AUDIT #58 IS CLOSED, and the way it was worded was misleading. "Seven
  preferences have no control" reads as seven controls to build. It was one bug
  (fixed), one control (built), and five things nothing reads -- currency,
  week_start, theme, date_format, time_format, default_reminder_minutes_before.
  Those stay unexposed deliberately. A control that changes nothing is worse
  than an absent one.
- The (?) exists now: shared/components/HelpTip.tsx, nine tests. Clickable, not
  hover-only; the panel is inline in normal flow so it cannot overflow a narrow
  screen; Escape closes it and is stopped from reaching a dialog around it. Two
  in use so far, on the timezone field and on Blocked periods. THE REST OF THE
  SWEEP IS STILL TO DO -- 128 ambient muted sentences were counted and two have
  moved. Do it panel by panel, and leave anything that must be read BEFORE
  acting where it is.


---

## Grades are sorted now, 2026-10-01
- They used to come back in insertion order, so a quiz added late sat under the
  final exam. One rule in Grades/utils/ordering.py, applied on both paths that
  hand grades to a client -- the CourseDetail schema and the list endpoint -- so
  a new path either calls it or fails the test that names both.
- Alphabetical, with two departures the real data earned rather than taste.
  CASE IS IGNORED: SQLite's default collation is byte order, which puts every
  capital before every lowercase letter, and three names in use start lowercase.
  NUMBERS COMPARE AS NUMBERS: strictly "Quiz 10" does precede "Quiz 2"
  alphabetically, and that is the answer nobody wants; a third of the names in
  use are numbered and a weekly quiz reaches ten.
- No frontend change was needed: the category grouping uses reduce/push, which
  preserves the order the server sent.


---

## Investment returns, asked for 2026-09-30 -- SHIPPED 2026-10-01
Built as designed below, with three decisions taken at the start of the build and
one scope cut. WHAT WAS BUILT: a new table `account_month_values`, one row per
(user, account, month), holding `difference_amount` (the level) and `market_value`
(what was typed, for showing back only). The rule is a pure function in
`Finances/utils/returns.py`. The card carries `(+3.2%)` beside the balance via
`Account.investment_return`; the account page replaces Movements with a return
tile and gains a "What it is worth" section that is where a reading is typed.

THE THREE DECISIONS, all asked and answered before building:
- YOU TYPE WHAT IT IS WORTH, not the difference. The market value is the figure on
  a statement; the subtraction is the app's job. The stored figure is still the
  difference, so none of the arithmetic below changes. Note the design note below
  overstates its case: storing the market value would need a dated ledger query,
  not time-weighting -- but it is still wrong, because a deposit made after a
  reading would make a derived difference report a gain as a loss. The level is
  stored because it is the only form that survives a later deposit.
- A MONTH WITH NO READING CARRIES THE LAST ONE FORWARD, dated on screen. It is
  never carried backwards: viewing July when only September is recorded shows
  nothing, because a figure from the future is not stale, it is wrong.
- THE GAIN COUNTS TOWARD NET WORTH, which was not in the original ask. `net_worth`
  adds each counting, non-archived investment account's latest difference, and
  `NetWorth.tsx` discloses it on its own line -- a headline that moves because
  someone remembered to record a reading has to say so on its face.

AMENDED SAME DAY, and the reason is worth keeping. As first shipped, the card's
headline stayed the LEDGER balance and the gain appeared only as the (+3.2%). The
owner spotted within the hour that net worth had moved but the card had not --
which meant adding up the cards could no longer reach the headline above them. That
is precisely the fault `Sectors` already carried a comment warning about: "two
totals on one page would sooner or later disagree in front of you". Mine did.

So the headline is now what the holding is WORTH (`balance + difference_amount`),
with a `.sectorPaidIn` line under it giving the ledger figure -- which is also what
keeps the percentage checkable, since it divides by exactly that. The account page
header matches, built from a new `AccountActivity.all_time_return` rather than the
month-scoped reading: using the month's would have added March's gain to today's
balance the moment anyone stepped the month picker back. A backend test now asserts
the sum of what the cards show equals net worth.

This also closed a flaw found while diagnosing it: the card had gated the whole
figure on `return_percent`, so an account with nothing paid in showed a recorded
gain of +$320 as NOTHING AT ALL -- the percentage being uncomputable took the
dollar figure down with it. The headline now carries it and only the percentage is
absent.

CUT, deliberately, and easy to add: THE MONTH'S PERCENTAGE. The tile shows the
month's gain in dollars only. A month percentage needs a second dated-balance
query and a denominator the reader cannot check against anything on screen,
whereas the card's percentage divides by the balance printed next to it.

TWO DENOMINATORS EXIST and mixing them up is the easiest mistake here. The level
is fixed against the ledger at the end of the month it was recorded for. The
percentage on the card divides by the balance standing TODAY, so the same $500
level reads 5.0% at $10,000 in and 3.3% once $15,000 is in -- and 3.3% is the
truth about what is now held. There is a test named after this.

VERIFIED: 1016 backend tests pass against Postgres as well as SQLite; nine
mutations of the guards were each confirmed to fail a test. The migration was
rehearsed on a throwaway Postgres by dropping the table and reapplying. Against a
VACUUM INTO copy of real data, recording a reading on the real Investments
account moved net worth by exactly the gain and left all 145 transactions alone.

The original design note follows, kept because its reasoning is still the reason
the feature is this small.

## Investment returns, as designed 2026-09-30
An investment account's balance is the sum of its ledger -- what you put in. It
says nothing about what the holding is now worth, so an account that has doubled
and one that has halved read identically. This closes that.

THE ASK, as given:
- On an investment account, record each month the DOLLAR AMOUNT the investment
  is higher or lower than its plain value -- plain value being the balance the
  ledger already derives.
- Total return is then computed, not typed.
- The account card carries the all-time figure beside the balance, very small,
  e.g. (+3.2%).
- The monthly figure REPLACES the Movements tile in the investment account's
  own page.

WHY THE SHAPE WORKS, and it is worth writing down because it is the whole
reason this is a small feature rather than a portfolio tracker:
- What gets typed is a LEVEL, not a flow. "$500 higher than plain value" is a
  snapshot of market minus cost, so the readings DO NOT SUM. All-time gain is
  the LATEST reading, not the total of them. Getting this backwards is the one
  way to make every figure wrong, so the rule wants a pure function and a test.
- The difference is CONTRIBUTION-NEUTRAL, which is the happy accident that
  makes the monthly figure easy. Put $1,000 in: plain value rises $1,000 and
  market value rises $1,000, so the difference does not move. Gain $50: market
  moves, plain does not, difference moves $50. So the difference IS cumulative
  gain, and a month's gain is just difference(m) - difference(m-1) -- no
  time-weighting, no adjusting for deposits. A design that stored market value
  instead would need all of that.
- All-time % = latest difference / balance. Month % = that month's gain over
  the previous month's balance.

WHERE IT TOUCHES:
- Sectors.tsx, the .sectorBalance span -- the (+3.2%) goes beside it. Keep the
  sign IN THE TEXT, not in the colour alone: audit #60 is already open against
  this component for conveying an overdraft by the minus sign and nothing else,
  and adding a second colour-only meaning to the same card makes that worse.
- AccountDetailPage.tsx:136 -- the `Movements` tile, currently
  activity.transaction_count. That is the one being replaced, for investment
  accounts only.
- AccountActivity DOES NOT CARRY `kind`. Both this and the older idea of gating
  Record spending to spending accounts need it; one field on the schema serves
  both, which is a reason to do it once rather than twice.
- Storage: one row per (user, account, month), the shape
  account_category_month_limits already uses. New table, so it arrives via
  create_all -- and per shipping.md that makes the schema step MANDATORY, since
  production runs RUN_SCHEMA_ON_STARTUP=0.

QUESTIONS WORTH ANSWERING BEFORE BUILDING, not while:
- A month with no reading: carry the last one forward and say when it was
  taken, or show nothing? Carrying forward is the honest default -- an
  investment you have not checked has not lost its value -- but it must be
  dated on screen or a stale figure reads as current.
- Investment accounts only, as asked. Savings accounts earn interest and would
  take the same mechanism; the narrower thing ships first and the wider one is
  a kind check, not a redesign.
- A holding worth LESS than you put in gives a negative difference and a
  (-8.1%). Make sure the first test written is that one, because a percentage
  that only ever renders positive is the bug this kind of feature always has.


---

## Subscriptions found: "until when?" -- SHIPPED 2026-10-05
Vision §13.9, Phase 1 decision D21. A recurring rule with no end date projects
forever and corrupts any forecast, while leases and term-length subscriptions
have natural ends.
- Each found subscription has an optional Until date, no earlier than the next
  expected charge. It reads "ongoing" until set, and is sent as the rule's
  recurrence.until.
- Frontend only: the confirm route already accepted the date and refuses an end
  before the start.

LIVE: c5c6238, all 26 changed files byte-identical to a production-URL build.

---

## Phase 1, items 2 and 3: required final on the course page, a 7-day workload line -- SHIPPED 2026-10-05
Phase 1 of Ideas/overhaul (Ideas/overhaul/Phase 1/). Decisions D7 and D8 in
phase1-decisions.md. Both are frontend-only, over routes already live.

- **Required final is a card beside the grade band** (item 2). It is measured
  against the course's own target, or the account default (the Attention panel's
  `effective_target` rule). It shows only when the final is still ahead: current
  term, a weighted final, unmarked, not a transfer or no-final course. The old
  calculator stays, as "Try another target". Cheapest path was already inline,
  so the vision's "both behind a modal" was half out of date.
- **"Next 7 days: Xh of estimated work, Yh free in your study hours"** on the
  dashboard (item 3). A rolling window, today plus six, so it is the right
  question on a Saturday; the Monday-to-Sunday glance below it is unchanged. It
  says how many tasks have no estimate, and flags work above free time.

Both say nothing while loading, on a failed read, or when there is nothing to
say. Every guard is mutation-tested.

LIVE: a337307 (item 2), then 974afaf (item 3). Each verified byte-identical to a
production-URL build: 26 of 26 files.

---

## Phone redesign from the owner's sketch, with gold icons -- SHIPPED 2026-10-12
From the owner's sketch ("Add Course.pdf") and nine icons in
`frontend/src/assets/icons/`. Frontend only. The owner chose a phone-only
redesign plus gold icons on the desktop sidebar, the profile icon opening
Settings, the checklist and survey kept, and "exams" counting midterms and
finals.
- **The bottom icon bar** (`app/layout/BottomNav.tsx`) replaces the sidebar at
  720px and below. It is fixed, scrolls sideways, and shows five icons and a
  sliver of the sixth (Home, Grades, Tasks, Budget, Calendar, then Fitness and
  Jobs). The current page is in a gold ring, drawn from `aria-current`. Its
  entries are picked out of `NAV` by route, so the two bars can't drift.
  Settings isn't in it.
- **The header** is "Account" and the profile icon, which opens Settings.
  Sign out lives at the foot of Settings' Account card on a phone. The omnibox
  shows on home only, with its how-to behind a gold "?" instead of the line of
  text under it.
- **The phone dashboard** has no greeting. It shows three cards:
  - grades: average, CGPA, courses, this term's average under "Year 3 Fall",
    and credits completed
  - money in whole dollars (`formatMoney(..., { whole: true })`)
  - this week: booked, tasks due, exams, shifts and free time
  Exams and shifts are counted off this week's agenda (`countWeek`). A failed
  read hides those two figures only. The checklist and survey stay while they
  apply. The workload line, strongest and weakest course, biggest category and
  estimated work are desktop only.
- **Every icon is gold.** The PNGs are CSS masks filled with `--gold`
  (`shared/components/Icon.tsx`), so the files stay as drawn and the colour is
  one token. The site's `img-src` allows `'self'` and `data:`, which covers
  both the hashed files and the one small enough to inline.
- **Fixed on the way:** the phone calendar's header ran 45px past a 390px
  screen once it had three view tabs. The page widened, the phone zoomed out,
  and the fixed bar fell out of view. Found from a headless-Chrome screenshot,
  not a test. The header now wraps, with a stylesheet test.
- `viewport-fit=cover`, so the bar clears an iPhone's home indicator.

Checked by screenshotting the phone and desktop layouts in headless Chrome
against a mock API with sample figures (no real data). 667 frontend tests, 40
new. The mutation check caught 15 of 16; the 16th, dropping `end` on the home
link, is equivalent, because React Router never marks `to="/"` active on a
sub-page.

LIVE: `main` at `4103e3c`, matching a production build file by file (35 files).

---

## Phone calendar: one day and three days in place of the week -- SHIPPED 2026-10-12
next.md, Calendar. On a phone the week's seven columns were too narrow to read,
and the grid's 680px minimum made it scroll sideways.
- **Which views where.** At 720px and below (the width where the sidebar
  already becomes a top bar) the switch offers Day, 3 day and Month, opening
  on three days from today. The desktop keeps Week and Month, unchanged: the
  owner's choice, phones only.
- **A page at a time.** The arrows move one day, three days, a week or a
  month. Three days starts at the cursor rather than snapping to a week, so
  Today shows today and the next two. A sideways swipe on a phone does what
  the arrows do. Only a clearly sideways swipe counts: at least 50px, and 1.5
  times its vertical travel. So scrolling through the hours never steps the
  calendar, and two fingers (a pinch) don't either.
- **Rotation.** The view is read through `fitView`, not corrected in an
  effect. A width change that crosses the breakpoint therefore never renders
  or fetches a view the width doesn't offer. Week becomes three days and
  back, Month stays Month, and the date is kept.
- **One grid.** WeekView draws any number of days. The column count is a
  `--days` variable that both grids' template reads, so their columns can't
  drift apart. Headings come from each date, not its position, since a
  three-day window can start on any weekday. The hour gutter narrows to 40px
  on a phone.
- **The free blocks and week load stay a whole week** in the day and
  three-day views: the week the first visible day falls in. A week's load
  measured over three days would read as a light week.
- The helpers are in `features/calender/views.ts`; `rangeLabel` was split out
  of `weekLabel`.

627 frontend tests, 23 of them new. The mutation check caught 11 of 11
mutants: wrong step size, no `fitView`, a week offered on a phone, the wrong
default, headings by position, no `--days`, swipe on a desktop, no
verticality check, swipe direction reversed, no listener for width changes,
and a fixed 7 in the CSS. Frontend only: no route, no schema.

LIVE: `main` at `6500761`, matching a production build file by file (37
files).

---

## Phase 2 items 13 and 11: end-of-term reviews, and teams (under Fitness) -- SHIPPED 2026-10-11
The last two buildable Phase 2 items, in one deploy (`Ideas/overhaul/Phase 2/`, D25, D26).

**Item 13, end-of-term reviews (D25).** "Rate your term" on the Grades page:
four questions per recently finished course, and an opt-in to add your grade
to the course's distribution. Asked from 14 to 180 days after a term ends;
answers lock after 14 days; the opt-in never does. **Nothing is shown:** the
distributions are Phase 3's.
- Your review holds no copy of your grade. The counts live in
  `grade_distributions`, a new **sealed** kind of table: row security with
  no policy and no grant, so the API itself can't read it.
- `account_recount_grade_distributions()` rebuilds it whole, reading grades
  at that moment, and writes nothing for a course-term under 5
  contributors. Its daily schedule is the owner's optional step.

**Item 11, teams (D26), on the page the owner renamed Fitness.** Make a team,
send the link, and anyone on it records a game. A score counts once someone
other than its recorder confirms it, the captain included; a disputed score
shows both until the recorder corrects it. The record: wins, losses, ties and
points from confirmed games. No leagues yet.
- `team_members` and `games` are read-and-delete for the API's role: every
  write goes through one of eleven definer functions, the captain's too.

Proven on SQLite and Postgres. Mutation checks: 28 of 28 (13) and 40 of 41
(11), the 41st a redundant guard. Both found real test gaps on the first run,
now closed.

LIVE: API `account-api-00045-hp9` (digest-verified `2de81a8`, sha256
`6265a8bd...`) since 2026-10-11 18:26 UTC. The schema step was the owner's.
All read-backs matched. Item 13's check C was re-run on 2026-10-12, its first
results pane having shown the previous query's output: the recount is callable
by `postgres` and `account_app` only. The gate reports row-level security on
for 50 of 50 tables. Health ok. The new routes answer 401 against two 404
controls; the recount door 403 without its secret. No errors in the new
revision's logs. Settings carried over. Frontend `main` at `2de81a8`, matching
a production build file by file (37 files).

---

## Phase 2 item 9b: shared events, through event links -- SHIPPED 2026-10-11
The second half of item 9 (`Ideas/overhaul/Phase 2/`, D24), on 9a's pattern.
- **A member sees and leaves, and changes nothing.** A shared event appears
  on their own calendar with its title, kind, time, place and notes, the
  owner's name and the other members'. Drawn dashed. Never the course. A task
  is the group's work, so members edit it; an event is a time and place one
  person set, so they don't.
- **Only a one-off event of your own can be shared:** not a repeat, a shift
  or a grade's block. If the owner makes it repeat later, it drops off
  members' calendars.
- **The same structure as 9a:** `event_members` and `event_invites` hang under
  the event; `event_members` is read-and-delete for the app role, written
  only by `account_accept_event_invite`. Four definer functions, none of
  which writes an event.
- **Shared tasks reach the calendar too:** a member sees a shared task's due
  date there, with a card pointing to the Tasks page to tick or edit it.
- **One share section** now serves tasks and events.

Proven on SQLite and Postgres: 23 shared-event tests, 4 new row-security
proofs, and all 8 routes in the walks, including under row-level security.
27 of 27 guard mutations caught on the first run.

**Not yet:** a shared event doesn't count in the member's free time, week
load or crunch strip.

LIVE: API `account-api-00044-vn2` (digest-verified `f884f69`, sha256
`cf9d49ca...`) since 2026-10-11 09:58 UTC. The schema step was the owner's;
the three read-backs matched (`event_members`: SELECT and DELETE only). The
gate reports row-level security on for 44 of 44 tables. Health ok. The 8 new
routes answer 401 against two 404 controls. No errors in the new revision's
logs. `TRUSTED_PROXY_HOPS=1` and the signup list carried over. Frontend
`main` at `f884f69`, matching a production build file by file (34 files).

---

## Phase 2 item 9a: shared tasks, through task links -- SHIPPED 2026-10-10
The first feature where one person changes another's row (`Ideas/overhaul/Phase 2/`, D23).
- **What a member does:** sees the title, notes and due date, ticks it done
  for everyone, edits the title and notes, and leaves. Never the course,
  grade, timer, priority or tags. Only the owner changes the date, deletes
  it, or changes who is on it. One-off tasks only.
- **No new policy shape.** `task_members` and `task_invites` hang under the
  task, so the existing child policy makes both the owner's alone. The
  `tasks` policy is untouched.
- **Nobody is put on a task without accepting.** The app role has SELECT and
  DELETE on `task_members`, never INSERT or UPDATE; only
  `account_accept_task_invite` writes a membership, for the caller.
- **Six definer functions** reach the owner's task for a member, each keyed
  on `account_current_user()` and revoked from everyone but `account_app`.
- **Links:** one live per task, usable by several people, 7 days, at most 8
  members. Only the token's hash is stored; the token rides in the fragment
  (`/invite#task:...`).
- **A shared task counts for its owner alone:** a member's week, estimates
  and partner figure read only their own tasks.

Proven on SQLite and Postgres: 24 shared-task tests, 5 new row-security
proofs, and all 9 routes in the isolation, non-interference and RLS walks.
36 of 36 guard mutations caught, after two test gaps were closed. CI's
Postgres job also caught a test that overrode `get_current_user`, which
skips setting the database identity; item 10's partner API test had the same
shortcut and passed by accident. Both now sign in with real tokens.

**Not in it:** shared events (9b), and a shared task on a member's calendar.

LIVE: API `account-api-00043-s9h` (digest-verified `97a3858`, sha256
`2cbe2e6f...`) since 2026-10-10 19:07 UTC. The schema step was the owner's;
the three read-backs matched (`task_members`: SELECT and DELETE only). The
gate reports row-level security on for 42 of 42 tables. Health ok. The 9 new
routes answer 401 against two 404 controls. No errors in the new revision's
logs. Frontend `main` at `97a3858`, matching a production build file by file
(33 files).

---

## Phase 2 items 12a, 14 and 10: throttling per caller, shifts near exams, the tax packet, accountability partners -- SHIPPED 2026-10-08
Three Part B items in one deploy (`Ideas/overhaul/Phase 2/`, D18, D20-D22).
- **12a, the rate limiter per caller (D18).** `client_address.client_of` reads
  one position of `X-Forwarded-For`, counted from the right, and checks it is an
  IP address. Anything doubtful falls back to the peer. It is behind
  `TRUSTED_PROXY_HOPS`, which defaults to 0: the header is ignored, so
  throttling behaves exactly as before. The position is confirmed against
  production logs before the switch goes on (runbook, 12a step 2).
- **14, shifts near exams (D21).** A shift that overlaps an exam, or ends
  within the "Keep clear before an exam" buffer (Settings -> Calendar, default
  12 hours, 0-48), is flagged on Jobs and Calendar. An untimed exam counts as
  starting at 08:00.
- **14, the tax packet (D20, D21).** For a calendar year: recorded pay per job,
  and tuition paid, by the date it was paid. Built only from what you recorded;
  T4s are scrapped, and no personal document is read.
- **10, accountability partners (D22).** An invite link that lasts 7 days, with
  at most 5 open. Only the token's sha256 is stored, and the token travels in
  the URL fragment (`/invite#...`), which browsers never send to a server.
  Accepting makes a mutual pair. Each person's figure (this week's percentage
  and a streak of good weeks, 80% or more, capped at 26) lives in their own
  row. A definer function returns figures only across a mutual pair, and one
  other is the only writer across users. Ending a partnership removes both
  rows. Signing in from an invite link returns you to it, and only to a path
  on this site.

Proven on SQLite and Postgres: 20 partner tests, 5 new RLS tests, and every
new route in the isolation, non-interference and RLS walks. Mutations found
three vacuous partner tests (a raw token passed where its hash belonged, and
two tests that deleted the wrong side of a pair). All three were fixed, and
the mutations are now caught.

**Not on yet:** `TRUSTED_PROXY_HOPS`, the owner's switch. Until open signup
(D19), an invitee must be on `ALLOWED_SIGNUP_EMAILS` to sign in.

LIVE: API `account-api-00040-w6n` (digest-verified `867938d`, sha256
`089c4a2a...`; corrected 2026-10-10, see below) since 2026-10-08 05:04 UTC. The schema step was the owner's;
the read-backs matched. The gate reports row-level security on for 40 of 40
tables. Health ok. The 8 new routes answer 401 against two 404 controls. No
errors in the new revision's logs. A forged `X-Forwarded-For` was ignored
(`client=169.254...`). Frontend `main` at `867938d`, matching a production
build file by file (32 files).

**The switch, on since 2026-10-08:** the owner set `TRUSTED_PROXY_HOPS=1`
(revision `00041-r88`). Checked on 2026-10-10 with a forged
`X-Forwarded-For: 203.0.113.7`: the audit line's `client=` equalled Cloud
Run's own `remoteIp` for the request, the caller's real address. It was
neither the forged value nor the platform's `169.254...` proxy, so throttling
is now per caller.

**Correction, 2026-10-10:** this entry first gave the image's digest as
`b0f9560a...`. That was the backup job's own `pg_dump` image, which logs a
`Digest:` line earlier in the same workflow; a grep for "Digest" found it
first. The deployed image is `089c4a2a...`, as Cloud Run's revision records.
The deploy's own check compared the right digest at the time.

---

## Phase 2 Part A: the shared course catalogue and prerequisites -- SHIPPED 2026-10-07
The first table every user reads and nobody owns (`Ideas/overhaul/Phase 2/`, D9-D14).
- **The policy:** `rls.SHARED_READ_TABLES` gets a SELECT-only policy that still
  needs an identity, and a SELECT-only grant. Every other grantee is revoked,
  including Supabase's anon and authenticated, because TRUNCATE ignores
  row-level security. The API cannot write the catalogue at all.
- **The catalogue:** `catalogue_courses` and `catalogue_prerequisites`. Only a
  `ubc-calendar` row may carry source wording, held by a check constraint.
- **Linking:** each course is matched to the catalogue by campus and code when
  read. Your override, a course or "none", is stored in two new columns on
  `courses`. Linking moves no grade, average or credit.
- **Your prerequisites:** typed (`CPSC 210 and one of MATH 200, MATH 217`, `6
  credits of MATH 1xx`, `CPSC 210 with 64%`), stored per-user in
  `prerequisite_proposals`, and applying to you at once.
- **Met or not:** a panel on the course page says met, on track or not met
  per part, labelled by source. "Not met" always adds "exceptions are
  sometimes made"; nothing is ever blocked. Adding a future course previews
  the shared rule.
- **From a syllabus:** the reader picks up prerequisites. Only what you confirm
  is filed, and the syllabus's sentence stays with you.
- **The owner review:** `scripts/catalogue_review.py` lists proposals as counts
  of accounts and shares the rule tree alone. It runs only as the tables'
  owner and refuses the app role.

Proven on Postgres. 49 guard mutations were caught, and one gap they found
gained a test. The isolation, non-interference and RLS walks cover the 7 new
routes.

**Not live:** nothing is in the shared catalogue until the owner approves
something with the review script. Item 8, a UBC calendar import, waits on
UBC's answer.

LIVE: API `account-api-00039-vmr` (digest-verified `11925ac`) since 2026-10-07
04:58 UTC. The schema step was the owner's. The gate reports row-level
security on for 38 of 38 tables. Health ok, the 6 new routes 401 against a 404
control, no errors in the new revision's logs. Frontend `main` at `11925ac`,
matching a production build file by file (29 files).

---

## Counted accounts: one switch for net worth and every analytic -- SHIPPED 2026-10-06
The owner's call (D39). Settings -> Financial lists every account with a
checkbox, and the account's edit dialog says the same thing. An unticked
account is treated as absent by every figure built from more than one account:
- net worth and safe to spend
- the forecast, runway and run-rates
- the year plan and the plan against actual
- the budget summary and the Dashboard
- the term budget and course cost
- the subscription finder and the standing-instruction totals

Its card says "not counted", and its ledger stays. This reverses the earlier
rule that net worth and safe to spend were kept apart. No schema change: the
existing column is read in more places, through Finances/services/counted.py.
The invariant test adds an unticked account of every kind and requires every
figure to stay the same. 15 of 15 backend and 5 of 5 frontend mutations were
caught.

LIVE: API `account-api-00038-mzd` (digest-verified `abf61d9`) since 2026-10-06
09:40 UTC. Health ok, routes 401 against a 404 control, no errors in the logs.
Frontend `main` at `abf61d9`, matching a production build file by file
(29 files).

---

## Phase 1, the review loops -- SHIPPED 2026-10-06
Decisions D34-D38 in phase1-decisions.md, steps in phase1-runbook.md ("The
review loops"). The owner backed up and applied the schema (four nullable
columns, one new table), then ran `deploy.run.sh all`.

- **The projection against the result** (D34). When a course's final is marked
  or its result entered, the grade from just before is kept. The course page
  then says "before the final, we projected 83.0%. You got 82%".
- **How long it actually took** (D35). Every open task has a server-side timer.
  Ticking off a task with an estimate asks the question, with the timer's total
  offered first. A timer left running past 12 hours records nothing.
- **The estimate ratio** (D36). It is the total actual time over the total
  estimated, shown from 5 tasks. A switch lets the workload forecast use it, and
  everywhere the forecast shows its estimate, it says when it is scaled.
- **The plan against each month** (D37). "Save as my plan" keeps a copy, never
  overwritten. Each finished month is compared with the plan saved before it
  began, with tuition named.
- **Every Phase 1 exit number prints from the usage report** (D38). The new ones
  are the money room unprompted and syllabus to term, with its no-change rate.

LIVE: API `account-api-00037-9p8` (digest-verified `aaf93c4`) since 2026-10-06 06:56 UTC.
The four new routes answer 401 against a 404 control, health is ok, and the logs
show no errors. Frontend `main` at `aaf93c4`, matching a production build file
by file (29 files).

Then, the owner's call: Budget's forecast and year plan moved to the foot of
the page, side by side (`ff0b4f8`). Live at `2081f1a`, matching a build file
by file; the live stylesheet carries the grid.

---

## Phase 1, the second batch -- SHIPPED 2026-10-05
Phase 1 of Ideas/overhaul. Decisions D25-D33 in phase1-decisions.md, steps in
phase1-runbook.md ("Next batch"). The owner backed up and applied the schema
(one nullable column, `courses.counting_scheme_id`; two new tables,
`degree_requirements` and `course_equivalences`), then ran
`deploy.run.sh api`.

- **A grading scheme can count as the course's grade** (D25, D29), or the
  course's own weights. The required-final figure no longer goes past 100% on
  courses weighted over 100: one test course was told 191% when 96.16% would do.
- **A syllabus can add to a course you already have** (D27, D30). It only adds,
  and never changes or removes anything already there.
- **The degree audit** (D31), at Grades → Degree audit. You enter the
  requirements and course mappings once, and it shows what is done, in
  progress, and missing.
- **The purge reaches every table** (D33). It never deleted category limits or
  month values, so their foreign keys would have refused the purge. The purge
  runs at startup, so an API instance could not have started. That would have
  been possible from about 2026-10-25. A refused purge now rolls back and
  waits instead.
- **`deploy.run.sh`** pushes the branch itself so CI runs, and a docs-only
  commit uses the CI run of its code.

CI CAUGHT A REAL BUG BY THE CLOCK: the same commit passed CI at 23:24 UTC and
failed at 03:04, after midnight UTC but still evening in Vancouver. The
syllabus daily cap compared a UTC date with the student's local one, so every
evening it counted nothing. It is fixed in `606a11a`, with tests in UTC-12 and
UTC+14 that fail at any hour if it comes back. The frontend went out with it.
The API half followed at 03:21 UTC as `account-api-00036-qbx` (`81d099c`).

LIVE: API `account-api-00035-cvz` (digest-verified `d81dfea`). The new routes
answer 401 against a 404 control, health is ok, and the logs show no errors.
Frontend `main` at `606a11a`, matching a production build file by file
(29 files).

---

## Phase 1, the backend batch -- SHIPPED 2026-10-05
Phase 1 of Ideas/overhaul (Ideas/overhaul/Phase 1/). Every decision is in
phase1-decisions.md (D9-D24), the steps in phase1-runbook.md. Deployed in one
batch: the owner applied the schema (four new tables, two nullable columns),
then `ship` and `main` went out at `26db894`.

- **Budget: "Where this is heading"** (D9). It shows the first day spending
  accounts would cross $0, the runway at the recent pace, and the fastest
  one-off categories, with every assumption listed. Card purchases count as
  they happen.
- **The year plan, and hours a week to a savings target** (D10).
- **Paycheque check** (D11). It recomputes a cheque from your shifts, with BC
  overtime and vacation pay, shows the arithmetic, and cites the rule.
- **Bank CSV import** (D14, D15). Preview before writing, duplicates unticked,
  category suggestions, and undo of the whole import.
- **A course from its syllabus** (D16). The parse is checked and edited before
  anything is created. Original files are kept in GCS when a bucket is set (D24).
- **Alternative grading schemes,** compared beside the course's own grade (D18).
- **The course section** (D22). A current course without one is in Attention.
- **The omnibox suggests a category** (D17). Attention says what the final needs
  (D13).
- **Measurement for the phase gate** (D12). Visits that start from a push
  notification are counted apart, and the "very disappointed" question is asked
  once, after a week.

THE DEPLOY WAITED OUT A GITHUB OUTAGE: two attempts were cancelled before a
runner picked them up ("not acquired by Runner of type hosted"). The third, after
Actions recovered, passed backup, schema gate, smoke test, digest check, health
and CORS. The frontend went out through `Application/deploy.run.sh web`, its first
real push.

Not live yet: syllabus reading needs the AI key (runbook step 3), and keeping
files needs the bucket (step 4). Until then the feature hides itself, and nothing
breaks.

LIVE: API `account-api-00034-54q` (digest-verified `26db894`); new routes answer
401 against a 404 control; health ok; no errors or 5xx in its logs. Frontend
`main` at `26db894`, matching a production build file by file (28 files).

---

## Phase 0: isolation in the database, usage counts, push -- SHIPPED 2026-10-05
Phase 0 of Ideas/overhaul (Ideas/overhaul/Phase 0/). Every decision, with its
reasoning, is in phase0-decisions.md (D1-D11); the production steps are in
phase0-runbook.md.

- **Row-level security on all 28 model tables.** Each table's policy names
  `account_app` only, and none is forced, so the API -- still connecting as the
  owner -- is unaffected until the connection switch (runbook step 5). Sign-in and
  scheduler lookups go through seven `account_*` definer functions, callable by
  nobody but the owner and `account_app`.
- **An enumerated two-user isolation suite, plus non-interference tests.** These
  run in CI on SQLite and Postgres, the Postgres run as the restricted role. Each
  of the 164 `user_id` filters was removed in turn; every gap that exposed in the
  suites was closed (D10).
- **Bugs the suites found:** email lookups treated `_` and `%` as wildcards (an
  account-takeover path); deleting a job with a confirmed shift, a course with
  linked rows, and a category used by a recurring rule each returned 500; PATCH on
  a tuition transaction returned 500.
- **Usage counts.** One row per user, day, kind and room; the report script prints
  totals only.
- **Push notifications** with a service worker and manifest (iPhone: from the Home
  Screen). They stay dormant until the VAPID key, cron secret and scheduler exist
  (runbook step 6).

GRANT GAPS FOUND ON PRODUCTION (D11). A blanket `GRANT ... ON ALL TABLES` would
have handed the restricted role `category_budgets`, a leftover with no policy;
grants now name model tables. Supabase grants every new function to anon by
name, which `REVOKE FROM PUBLIC` misses; install now revokes from everyone but
the owner and the app role. The owner switched off Supabase's Data API, which
the app never used. Before this, anon could read every table through it.

LIVE: 9f1f3cb on revision account-api-00029-29h (backup, schema gate 28/28, digest,
health and CORS checked by the workflow); new routes answer 401 against a 404
control. Frontend index-k4a8swTz.js; all 32 files byte-identical to a
production-URL build.
ISOLATION ON 2026-10-05: the owner switched DATABASE_URL to `database-url-app`
(revision account-api-00030-xmq, same image). In the first 206 requests as
`account_app` -- password sign-in, every finance read, grades, jobs, calendar,
account reorders, recurring runs and visit counts -- there was no failure but a
favicon 404, and no permission or row-security error in the logs.
PUSH ON 2026-10-05: the owner added the VAPID key, cron secret and the 5-minute
Cloud Scheduler job. Every push request then returned 500: the runbook stored the
key from `print()`, trailing newline and all, and base64 refused it. Settings sat
on "Checking..." because the failed-check path never set the device flag (and
would have claimed "not set up"). Both are fixed (eb41226 frontend, 238c122
`.strip()` on the key, each with a test that fails without it); the runbook
command now prints without the newline. LIVE: revision account-api-00032-vxd. The
scheduler's call returns 200; a call with no secret, or a wrong one, returns 403.
SEND A TEST, ONE DEVICE (d081828, revision account-api-00033-8sx): pressed on the
laptop it arrived on the phone too, because the test went to every device. The
frontend now names its own endpoint, and the server sends there if it belongs to
the caller (aiming at another user's device sends nothing; tested). With no
endpoint it still sends to all, so either half could deploy first. Reminders
still go to every device. The notification buttons were also made row-sized.

---

## Cash tips go to one chosen account -- SHIPPED 2026-10-04

A cash tip used to split across accounts by income share like a paycheque, which
claimed it was in the bank when it was in a pocket. Settings -> Financial now has
"Cash tips go to": one account, and the whole tip lands there as one row.

**Decided with the owner, and the default changed:** with no account chosen -- or
the chosen one archived or deleted -- a cash tip is HELD: recorded on the shift,
kept out of the budget. A red "!" beside the confirmed shift in Jobs says so and
links to Settings -> Financial (Settings now opens on ?tab=). Choosing an account
files every held tip into it. Changing the account affects tips from now on --
tips already in the budget, including old split ones, stay where they landed.

Choosing has its own endpoint (PUT /jobs/{user_id}/cash-tip-account) rather than
riding on the preferences save: it writes to the ledger and needs an ownership
check, so both happen in one transaction, and the generic save cannot set it.
`tip_in_ledger` had been sent by the API all along and shown nowhere, so a tip
with nowhere to go was invisible until now.

Guarded by 16 tests that count every account's rows before and after, plus four
existing tests updated to choose an account (one had started passing vacuously).
Seven mutations each fail by name. The copy-of-local-data check ran but proved
little: local data has no shift tips.

LIVE: be4f1d7, revision account-api-00028-jwz; frontend verified byte-for-byte
against a production-URL build.

---

## "Get started" checklist on the dashboard -- SHIPPED 2026-10-04
Phase 0 item 6, onboarding (Ideas/overhaul/phase0.md). Frontend only.

Five steps, each a link straight to where it is done:
- tell it your term
- check your time zone
- add courses
- put something on your week
- record some money

Each is derived from data the dashboard already loads, so a step ticks itself
off however the thing was added (the omnibox counts). Nothing about the list
is stored.

SHOWN ONLY ONCE EVERY SOURCE HAS ANSWERED SUCCESSFULLY. The steps are claims
about what exists, so a slow or failed read must not tell someone to add the
courses they have. This is the owner's no-empty-state-while-loading rule;
removing the guard fails two tests.

The time zone step is done when the saved zone matches the browser's: new
accounts start on America/Regina, and "today" comes from it everywhere. Hide
is remembered per user in localStorage, guarded, since this Node's jsdom has
no localStorage and a private window may refuse it.

It shows for anyone with an unfinished step, existing accounts included.

LIVE: commit b1ceac5. The dashboard chunk and style-BS-dNUlC.css are identical
to a production-URL build of that commit. The entry differs only by the Google
client id, which the scratch build had no .env for.

## Keyboard shortcuts, and accounts you can reorder -- SHIPPED 2026-10-03
Frontend only. No endpoint, no schema, no deploy gate.

KEYBOARD SHORTCUTS. G then a letter goes to a module (D G C T J B S, read from
the Sidebar's own NAV array so the two cannot drift). ? opens the list -- the
only place shortcuts are shown, by the owner's choice. N adds on the current
page: new event, focus the task quick-add, new job, Add Course, Record Money.
On the calendar, the arrows step and T goes to today. Every one calls the same
handler as the visible button it stands in for. N on Grades is off while a past
year is shown (no Add Course there) and on Budget while there are no accounts
(Record Money is disabled then).
  "NOTHING FIRES WHILE TYPING" is one function, isTypingContext in
  shared/hooks/useShortcut.ts: inputs, textareas, selects, contenteditable,
  any modifier (Cmd-K stays the omnibox's), IME composition, an already
  handled event, and ANY OPEN aria-modal DIALOG -- so N pressed on a form's
  Save button cannot open a second form behind it.
  G sequences listen on the CAPTURE phase so the key after G is consumed
  before any page hears it; otherwise G T on the calendar would also jump to
  today. Tested, and mutation-tested along with each guard above.

ACCOUNT ORDERING. A drag handle on each account card, beside the pencil and
outside the card's Link (a handle inside it would open the account on every
drag). Pointer Events with pointer capture, not HTML5 drag-and-drop, which
never fires on touch; touch-action: none on the handle. The card under the
finger is found by elementFromPoint and its index in the grid, so the wrapping
grid needs no layout maths. The focused handle also moves by arrow keys, one
place per press. Escape mid-drag puts it back.
  SAVED AS ONE PATCH PER ACCOUNT THAT MOVED, through the existing
  ownership-checked account route. Not atomic: a failure midway leaves a mixed
  order. Accepted on purpose -- it costs nothing but order, dragging again fixes
  it, and a batch endpoint would have needed a backend deploy. Either way the
  grid reloads to what the server holds and says so on failure.
  Every index is written, not nudged: accounts made before ordering existed can
  share position 0, and only distinct positions make the order mean anything.
  New accounts were already created at position = count, so they land last.

NOT VERIFIED IN A REAL BROWSER by me: the pointer path is tested in jsdom with
elementFromPoint stubbed, so actual hit-testing on a phone was not exercised.

Also removed from next.md: "remove the dashboard buttons", which had shipped in
0224d31 (see the dead-code pass above) but was still listed as to-do.

## Every frontend "today" on the Settings time zone -- SHIPPED 2026-10-03

The follow-up the now-line left open. The week view had moved onto the Settings
zone; the month view's today, and every other frontend `today()` -- about forty
call sites across tasks, budget, jobs and the calendar -- still read the browser
clock, so while travelling the month could mark a different day from the week.

Fixed at the source rather than at forty call sites: `today()` reads a module-level
zone that `AuthProvider` sets from the signed-in user, falling back to the browser
when nobody is signed in or the zone is unusable. Set during the provider's render,
not in an effect, so a page's first `today()` is already on the student's clock --
an effect would open on the browser's day and flip. Two places that read
`new Date()` directly (the dashboard's "this week", a sinking fund's months-to-go)
now go through `today()` too.

Guarded at each link: the clock, the provider actually setting it, and the month
view marking the right cell. Three mutations each fail by name -- the provider
never setting the zone, `today()` ignoring it, and the call moved into an effect.
Frontend only.

---

## A now-line on the week, and event colours you choose -- SHIPPED 2026-10-03

**The now-line.** A red line at the current minute, in today's column of the week
view and nowhere else -- so a week that is not this one draws none, with no branch
of its own. It ticks on the minute boundary, not 60s from mount, so it moves when
the clock does. It ignores the pointer and is hidden from screen readers.

It reads the **Settings time zone**, not the browser's: the backend's "today"
already does, and a line from a different clock would sit in a different column
from every server figure. The week's highlighted "today" column moved onto the
same clock, so the two always agree. `nowIn(zone)` in `shared/utils/zonedNow.ts`
uses Intl with `hourCycle: "h23"` (midnight is minute 0, not 24:00) and falls back
to the browser clock for an unusable zone, as the backend falls back to UTC. The
month view still uses the browser clock -- left for a later slice, in next.md.

**Event colours.** All eight kinds, in Settings -> Calendar, each beside a sample
drawn with the calendar's own classes, so an exam keeps its heavier bar in any
colour. Stored as `preferences.event_colors`, only for kinds changed: "Default"
removes the key rather than storing a copy, so a retuned default reaches everyone
who never touched it. Validated as `#rrggbb` on BOTH `UserPreferences` and
`UserPreferencesPatch` -- dropping it from the patch model fails five tests. Kinds
stay a fixed enum; recolouring only.

The stylesheet moved from sixteen hardcoded colour pairs to one `--kind-color` per
kind, with bar and tint derived by `color-mix`; a chosen colour arrives as an
inline custom property. Proven identical for an unchanged calendar by resolving
what each kind actually paints, before and after, in both views -- all sixteen
match, including personal's lighter grey and both exam grounds. A test keeps
`kindColors.ts`'s defaults in step with the stylesheet's.

No migration (a JSON key). API rollback is safe alone: older code's
`UserPreferences` ignores the unknown key.

---

## CI, and the API deploys itself from `ship` -- SHIPPED 2026-10-03

Asked for because deploying by hand took too long. `shipping.md` steps 10-15 were
a dozen commands typed in order from a laptop, each with a trap someone had
already fallen into.

**CI** (`ci.yml`) runs the three green lights on every push: backend pytest and
frontend test + build, in parallel, ~90s. Docs-only commits skip it. It reports
and blocks nothing, keeping the rule that a red test cannot block a hotfix.
Proven by breaking it on purpose -- no `JWT_SECRET` failed the backend at
collection, a type error only `tsc` can see failed the build with the tests
green, and a docs-only push started no run.

**The deploy** (`deploy-api.yml`): `git push origin HEAD:ship` runs the backup
(`backup.yml`, now callable, its plausibility gate a precondition), builds amd64,
smoke-tests the container, checks the image carries this commit's source, pushes,
deploys with `--port=8000`, then verifies that the revision taking 100% of traffic
runs the digest just pushed, `/health`, and CORS against a stranger's origin as
well as ours. A separate branch because pushing `main` IS the frontend deploy:
anything triggered by it would deploy the API after the frontend.

**The schema is never applied by the workflow.** `check_schema_conformance.py`
compares the models with production's catalogue and refuses the deploy when a
table or column is missing, printing the fix. It replaces the git-diff gate, which
fired on a deleted design note and could not see a column missing from
`ADDED_COLUMNS`. It runs as `ci_reader`, a CONNECT-only role refused every row of
data -- proven on a throwaway Postgres 17 that such a role still sees the schema.

**No key exists.** Workload Identity Federation: GCP mints tokens only for
`refs/heads/ship` of this repo. A probe proved it three ways before any role was
granted -- `ship` got a token, that token was refused the registry, and another
branch was refused a token outright. The deployer then got three roles, each on
one resource, none project-wide.

Three things the first runs caught, all fixed:
- The gate's first credential failure crashed with exit 1 -- the code meaning
  "apply the schema". A bad password must not send anyone to run a migration; it
  now exits 2 and says it could not connect.
- The first real deploy SUCCEEDED and then failed its own check: Cloud Run records
  a revision's image by digest, never by the tag deployed. It now resolves what
  `:SHA` is in the registry and compares digests -- which a moved tag cannot fool.
- CI's first evening run failed two tests that compared against `date.today()`.
  The test user lives in America/Regina and the runner in UTC, so from 6pm they
  disagree by a day. Both now expect `user_today`; the suite passes on UTC, local
  and UTC+14 clocks.

Two deploys (00025, 00026) changed no app code -- they proved the pipeline.

---

## "Show completed" flashed "Nothing finished yet." -- FIXED 2026-10-03

Reported from the screen: turning the toggle on showed the empty message first and
the finished tasks a moment later.

The toggle changes `includeDone`, which refetches -- but `tasks` still holds the
rows fetched WITHOUT the done ones, so the Done group rendered with zero rows and
said "Nothing finished yet.". The message was never wrong about the data in state;
it was a true statement about the previous answer being read as the new one. An
empty message is a claim about the data, and no group may make it before the data
arrives.

`useTasks` now returns `stale` alongside `loading`: loading AND the rows in state
were fetched under a different filter. `loading` alone could not drive this, because
it is also true during a plain reload, when the rows already on screen are still
right -- wiring the lists to it would flicker every empty group every time a task
was added. `TaskList` takes `loading` and, only when it has no rows, shows
"Loading..." in place of the empty message and withholds the count as well, since
"0 tasks" beside "Loading..." is the same false claim in fewer words. All four
lists are wired, so the fortnight and Overdue stop asserting emptiness on first
load too. No CSS: the built stylesheet is byte-identical.

The guard covers all three links, because this morning proved the leaf being right
is not the question: seven component tests, three hook tests for `stale`, and a
source test that every `<TaskList>` in `TasksPage` is actually passed
`loading={stale}` -- the "written correctly, never wired" failure mode. Five
mutations were each confirmed to fail a test by name, including dropping the prop
from the Done list and wiring it to plain `loading`.

269 frontend tests across 28 files. Frontend only: no image, no schema, no API
revision.

---

## The three interface quality asks -- SHIPPED 2026-10-03

Asked for 2026-09-28; all three closed together. The counts in `next.md` were the
size of each job as measured then, and two of the three turned out to be wrong in
ways worth recording.

**CONFIRM EVERY DELETE -- and it was ten, not nine.** The hand audit listed nine
unconfirmed delete paths. Enumerating every call site against the api layer instead
found a tenth, `deleteShift` in JobsPage. Every destructive call site now goes
through `DeleteConfirmModal`, and the two that cascade say so: the sinking fund
previously announced "Remove {name} and its transfers" in its own aria-label and then
performed it on one click, and removing a job takes its shifts and paycheques.

Each message names what SURVIVES rather than only what goes -- the fund's money stays
in the account, the job's ledger transactions stay, a recorded paycheque outlives its
shift -- because that is the part that settles whether to click.

Two of the seven were not what their labels said: `Repeating.onStop` and
`Recurring.onDelete` both call a delete, so "Stop" was deleting the rule. The dialogs
say so, and say that occurrences already ticked off and payments already made stay.
A calendar event looked like it might be exempt under the recoverable rule, but
`restoreOccurrence` un-skips one occurrence of a repeat -- there is no undelete for an
event, so it is permanent and asks.

`deleteConfirmations.test.ts` is the part that lasts: it reads the api layer for every
`delete*`/`clear*` export, finds every call site, and fails if one has no
confirmation, with a RECOVERABLE allowlist so the exemption is explicit rather than
implied. A hand count missed one in ten; the enumeration cannot.

**AND THEN SIX OF THE TEN SHIPPED HALF-APPLIED.** The paragraph above was written
before the work was verified, and it was wrong about the part that mattered. The
edits were made with bare `str.replace()`, which returns the string unchanged when
its anchor does not match and reports nothing, so a script printed success over
six sites it had not touched. Post-deploy verification across all 25 served chunks
found two dialog messages missing, traced them to source rather than to a stale
deploy, and the audit that followed found the rest.

Three of them still deleted on ONE CLICK, and all three were the ones that cascade
or cannot be undone: the sinking fund with its transfers, the job with its shifts
and cheques, and a tuition payment. They rendered a dialog nothing could open --
which is why the guard passed, because it searched for the identifier
`DeleteConfirmModal` and the `import` line satisfies that. Three more had the
trigger rewired with no dialog rendered, so the delete silently did nothing: the
task, the repeat rule and the calendar event. Those were live for the hour between
the two pushes.

The guard now checks WIRING, in three parts: a confirmation is rendered and not
merely imported; no handler prop (`onClick`, `onDelete`, `onRemove`, `onStop`) is
wired to a delete-performing function or calls a delete api inline; and every
`open={state}` has something able to set that state, counting a setter passed by
reference. It reads each component's body by brace matching rather than a character
window, so a dialog far below its trigger is still found. All three real shipped
bugs were replayed against it and each now fails by name and file.

THE LESSON WORTH KEEPING: the verification was the weak link, not the change. An
edit applied by a script needs an assertion that it applied, and a guard that
matches an identifier proves an import, not a behaviour -- mutate it against the
real bug or it is not a guard. Fixed in `92804bc`.

**MAKE A CLICK FEEL LIKE A CLICK.** `:active` appeared zero times in the stylesheet,
across 192 buttons, so the only feedback a press ever had was `:hover` -- which touch
does not have. The spec's "one rule on the shared button classes covers all 183" was
not achievable: `.buttons` carries 19 of the 192 and `.calButton` 64. It needed a bare
`button:not(:disabled):active` baseline plus per-class rules, because
`.class:hover` is (0,2,0) against `button:active`'s (0,1,1) and you are always
hovering while pressing. Press lands where hover lifted from; reduced motion keeps the
brightness change and drops the movement. A stylesheet test asserts it cannot regress
to zero and that no disabled button presses.

**EXPLAIN ON DEMAND -- and "128 ambient sentences" was an overcount.** All 133
muted nodes were dumped and read. Most are figures, labels, status lines, errors and
empty states, which is what `muted` is for; hiding a figure behind a question mark
makes the app worse. The genuine "what is this?" prose was about 20 nodes, and 20
moved: 31 HelpTips across 12 files, up from 2 in 1, with the node count going
133 -> 118 because the remainder are doing real work.

The rule held: text that changes what you are about to do stayed on the page
("Deleting a category removes the label only", "Replaces any pattern already set"),
and the two chart lines stayed because the panel is a heading and that sentence --
behind a mark it would be an empty box explaining nothing.

Two fixes beyond the sweep. The account toggles' explanations were INSIDE `<label>`,
so the checkbox was announced with the whole sentence appended; moving them out fixed
the accessible name. And `Loading`'s bootstrap spinner was styled in `layout.css`,
which only MainLayout imports, while ProtectedRoute renders it before MainLayout
mounts -- unstyled in development for the one case it exists for.

A correction worth keeping: HelpTip's styles moved to `globals.css` for organisation,
NOT because they were unreachable. The first claim was that they rendered unstyled
outside /settings in dev; that was wrong, because `main.tsx` imports login.css,
grades.css, courseDetail.css and calendar.css directly. The code comment and the test
docstring were corrected rather than left confidently wrong.

**Also shipped with it: the task tick is now visible.** Checking a task used to await
the server, reload, and regroup in the same frame, so the tick never rendered -- the
row simply vanished from the fortnight. It is optimistic now, held crossed out for
300ms in the group it was already in, with the linger running alongside the request so
a slow network adds no delay on top of the pause. The grouping rule moved to
`features/tasks/horizon.ts` with 17 tests; four mutations each fail, including the one
that matters -- letting a lingering row fall through to done breaks five.

256 frontend tests across 26 files. Frontend only: no image, no schema, no API
revision. Moving CSS between files was verified by comparing every selector's
declarations across the old and new builds -- no pre-existing selector lost one, the
only differences being two minifier normalisations.

---

## "Today" meant UTC, not the student's day -- FIXED 2026-10-02
The owner noticed free time was wrong and named the cause: "I think it is using
utc". It was. `free_blocks` used `datetime.now()` and `crunch` used
`date.today()`, and the Cloud Run container sets no TZ -- confirmed by running the
deployed image, where datetime.now() == utcnow().

For America/Regina (UTC-6) that meant: at 14:00 local the server thought 20:00 and
clipped the afternoon off; from 18:00 local UTC was already tomorrow, so the day
the client asked about was skipped as past and there was NO free time after six in
the evening, ever. The study window's hours came from preferences the whole time,
which is why it looked inconsistent rather than broken.

The scan found 25 naive clocks, not 2 -- `shared/dates.today()` and its nineteen
callers across Tasks, Finances and Jobs, the omnibox, the quick-capture parser,
tuition, two finance route defaults, and `measured_on` from the day before. All
converted. `shared/dates` is now the single timezone-aware clock and the naive
`today()` was DELETED rather than deprecated, so the mistake is not one import
away. Its own docstring had said "anything that starts needing a timezone comes
through here", which turned out to be the right place all along.

Five call sites held no user, so they are told the day as an argument -- the idiom
the module already described. `measured_on`, `next_pay_on`, the tokenizer's
`parse`, and the two rule-scoped ones read `rule.user_id`.

THE LESSON WORTH KEEPING: every test in test_week_load.py injects `now=`, so the
injected path was well covered and the DEFAULT -- the broken line -- had no test
at all. A seam added for testability is why the production path went unexercised.
There are now tests that call the default and assert it goes through the
preference. Audit #68.
