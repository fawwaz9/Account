# Application audit

- **Last updated:** 2026-10-28
- **Status:** 0 completed / 0 in progress / 110 left

A staff-level review for an invite-only release (under 100 users) with a few
contributors joining. Integrity and reliability come first, readability and
maintainability second, scalability last. When work starts on an issue it moves
from its priority section to **In progress**; when it is done it moves to
**Completed**, its checklist box is ticked, and the timeline records when, where
and anything the fix did that nobody expected. The previous audit (68 findings,
2026-09-10 to 2026-10-19) is archived in `audit-archive.md`.

---

## Checklist

### Critical (1)

- [ ] **C1** The standing-instruction catch-up knows a payment was written only by finding its row, so editing a rule's dates back-fills up to 120 days of duplicate payments and a deleted payment is written again.

### High (9)

- [ ] **H1** Update paths validate a PATCH as a fragment, never the merged row, so one edit can store a row its own response model refuses, after which every read of that list returns 500 until the row is repaired by hand.
- [ ] **H2** Editing any field of a paycheque, even its notes, deletes its ledger rows and re-splits the net by today's income shares, silently moving past money between accounts.
- [ ] **H3** Once any date of a weekly shift pattern is confirmed, the pattern can no longer be re-saved or deleted: both paths fail on the shift_records foreign key and return 500.
- [ ] **H4** Safe to spend subtracts every outgoing standing instruction and sinking-fund contribution from any counted account, including bills paid from savings and transfers into spending, from the spending balance.
- [ ] **H5** Deleting one allocation of a paycheque's deposit (scope=row) deletes the whole cheque but leaves its other income rows in the ledger with nothing explaining them.
- [ ] **H6** Panels refetch only when a hand-bumped nonce changes, and some saves never bump it: after a grade is saved the course page's band, 'Worth doing next', required-final and schemes keep their old figures, and after an event is saved the calendar's free blocks, week load and shift conflicts do.
- [ ] **H7** A wrong password on sign-in is treated as an expired session: the login page reloads and the real error is never shown.
- [ ] **H8** The dashboard shows balances, net worth and this month's spending before due standing payments are written, so it is wrong until the Budget page is opened.
- [ ] **H9** Tapping × on a transaction deletes it, or both halves of a transfer, at once: no confirmation and no undo.

### Medium (28)

- [ ] **M1** Errors are mapped to status codes by hand in each route, with no app-wide handler, so ordinary mistakes return 500 (an uninvited Google sign-up, renaming a category onto a used name, a one-sided shift-conflict window) and some routes choose 404 or 400 by searching the message text.
- [ ] **M2** Data loading is hand-rolled in about sixty hooks and components, in three drifting patterns, so the out-of-order and stale-cache guards the last audit added are missing from some.
- [ ] **M3** Standing payments, repeating-task occurrences and sinking-fund contributions are de-duplicated by a read-then-insert with no unique index, both catch-ups run on every page load, and a standing payment is committed before it is stamped as written.
- [ ] **M4** Saving a course timetable replaces it wholesale: every cancelled class date comes back on each save, and a slow or failed load lets the blank form replace the whole timetable.
- [ ] **M5** Services commit inside themselves, so operations that must be all-or-nothing span several transactions: recording or deleting tuition, applying a syllabus and confirming a subscription can each be left half-done.
- [ ] **M6** Nothing checks code style or static types beyond `tsc`: no Python linter, formatter or type checker anywhere, no ESLint or formatter for the frontend despite `eslint-disable` directives in its source, and the frontend type-check skips two build files.
- [ ] **M7** Configuration is read two ways and fully validated by neither: half the backend settings are raw `os.getenv` reads that never see Application/.env and are not checked at startup, LLM settings are checked only when a parse runs, and a frontend build without VITE_API_BASE_URL silently targets localhost.
- [ ] **M8** Production problems are hard to see: frontend crashes stay in the visitor's console, the API has no exception handler, request id or structured log fields, and audit lines go to two differently named loggers with no record of each purged account.
- [ ] **M9** Deleting a cash tip's ledger row from the ledger fails on the shift_records foreign key and returns 500.
- [ ] **M10** Term blackouts hide one-off course events too, so a midterm, deadline or grade block dated inside a reading break disappears from the calendar and every figure built on it.
- [ ] **M11** Row policies check only a row's own owner column, so a foreign key to another user's row passes WITH CHECK.
- [ ] **M12** Each definer function must be listed by hand in four places, and a missed REVOKE FROM PUBLIC is not caught by the lockdown loop.
- [ ] **M13** A model answer that breaks the "lenient" extract schema's limits fails the parse after the paid model call, uncounted by the daily cap, with a raw Pydantic dump as the message.
- [ ] **M14** Course codes are parsed by five separate regular expressions with different rules.
- [ ] **M15** The add and edit forms for courses and for grades are each written twice: `AddCourseForm`/`EditCourseForm` differ only in ids, a notice and Reset, and `AddGradeForm`/`EditGradeForm` only in the dropped toggle.
- [ ] **M16** The headline cumulative and semester averages report 0% when nothing has been recorded yet, so every new student's grades page and dashboard read as failing.
- [ ] **M17** Any background refetch anywhere in the app makes the course page swap itself for 'Loading...', unmounting open dialogs and discarding whatever the student had typed in them.
- [ ] **M18** 'Stop' on a repeating task deletes every unticked occurrence, overdue and edited ones included, but its confirmation only says the ticked-off ones stay.
- [ ] **M19** A non-JSON error body (a gateway 502/503/504 page) makes every API call fail with a JSON parser message and loses the HTTP status.
- [ ] **M20** Any failure loading the user at startup (offline, a 5xx during a deploy) discards the session token and signs the student out.
- [ ] **M21** Every frontend API type is hand-copied from a Pydantic schema, with no generation or contract test, and the copies have already drifted.
- [ ] **M22** An account's month lists at most its newest 100 transactions, silently, while the totals beside it count every row.
- [ ] **M23** The 'Remove this fund?' dialog promises the money stays where it was moved, but removing a fund deletes its transfers, which moves the money back.
- [ ] **M24** Editing a tuition payment cannot be saved without re-picking 'Paid from', and saving then moves its ledger row to the picked account and resets its description.
- [ ] **M25** Saving a shift pattern applies it from the job's start date, rewriting every past unconfirmed week, from an editor that never shows the current pattern.
- [ ] **M26** The omnibox can file a line before its module badge has caught up, so the 'shown before you commit' safeguard fails on quick typing and Enter.
- [ ] **M27** The tests are strong on single operations but miss the sequences where this audit's worst bugs live, the Google sign-in route is never called, several guards are regular expressions over source text, and nothing measures coverage or drives the app end to end.
- [ ] **M28** A new contributor has no current entry point: the root README tells readers to trust Ideas/ over itself and still gives 23 tables, 904 tests and a backend/.env that nothing reads, while the conventions live in about 11,800 lines of narrative notes with no CONTRIBUTING guide or PR checklist.

### Low (65)

- [ ] **L1** Invite-link handling (token minting, SHA-256 hashing, one live link, cancel, remove member) is copied across four services that must stay in step with the definer functions.
- [ ] **L2** App-wide frontend code lives inside feature folders: `getErrorMessage` (exported from the Add Course dialog) and `DeleteConfirmModal` in grades, the `ValidationError` type the shared API client imports from grades/types, and `formatMoney` in budget.
- [ ] **L3** Date helpers are re-implemented privately in budget and jobs components instead of using shared/utils/dateUtils, including three different `monthLabel`s.
- [ ] **L4** Naive-UTC timestamps are shown as dates by slicing the string or `new Date()`, so link expiries, snooze history and import dates read a day late every evening west of Greenwich.
- [ ] **L5** Failed loads render as empty states: the grades page's Attention panel says 'Nothing needs attention', and budget and partner panels vanish when their request fails.
- [ ] **L6** The add-task form and the game form clear themselves even when the save fails, losing what was typed.
- [ ] **L7** Calendar information is carried only by position, bar height and hover `title`: week-view blocks have no time in their accessible name and the crunch strip has no text per week.
- [ ] **L8** The term budget's 'cannot measure' message blames course dates when the cause is a missing first-year anchor.
- [ ] **L9** The category and account duplicate-name checks pass the raw name to ILIKE, so `%` and `_` act as wildcards and untrimmed names slip past them.
- [ ] **L10** Paycheque allocations are checked with the float tolerance audit #50 removed from deposits, and not checked at all when a cheque is corrected.
- [ ] **L11** The user-exists, owned-course and course-code lookups are copied into five services, and Finances, Jobs and Calendar import `user_exists` from the Tasks service.
- [ ] **L12** The week-load and crunch figures read tasks through list_tasks' list defaults, so a snoozed task's hours vanish from the week it is due and finished work drops out of past weeks.
- [ ] **L13** Skipping a repeating task's occurrence, and its 'next due' date, still match occurrences by due_date, so a moved occurrence survives being cancelled and can be reported as next due after it is done.
- [ ] **L14** Completion timing loads every task the user has ever completed on each Tasks page load, then discards all but the last month in Python.
- [ ] **L15** The effective hourly rate expands the whole calendar once per cheque, and the Jobs and Budget pages each call it alongside several other full expansions.
- [ ] **L16** The tax packet's 'tuition paid' is the ledger amount (after scholarships, with fees), which never matches the eligible tuition on a T2202 when a bill had either.
- [ ] **L17** Unticking 'counts' on the last spending account silently empties safe-to-spend, the exact outcome the last-of-a-kind guard exists to prevent for archiving.
- [ ] **L18** A category limit of 0 with spending against it reports 0% used, and the client's progress bar then announces 'No target set'.
- [ ] **L19** Quick capture and the omnibox each read a line into a task with their own copy of the same rules (course matching, unmatched-code handling, duration clamping).
- [ ] **L20** POST /recurring/run accepts any `through` date, so one request can write future standing-instruction payments into the ledger as if they had happened.
- [ ] **L21** course_category_weights has no unique (course_id, category), so a category can hold two weight rows.
- [ ] **L22** Enumerated and ranged columns on the older tables have no CHECK constraints, unlike the Phase 2 and 3 tables.
- [ ] **L23** ADDED_COLUMNS mixes Postgres-safe DDL with SQLite-only DDL, so ensure_schema fails on any Postgres database older than the current models.
- [ ] **L24** The grade-distribution cohort floor counts contributions, not distinct contributors.
- [ ] **L25** A second player's dispute silently overwrites the first, because a game holds a single dispute slot.
- [ ] **L26** Audit log lines interpolate caller-supplied text unescaped, so a login attempt can forge audit entries, and deleted titles land in the logs.
- [ ] **L27** The Semester enum is defined twice, in Grades/utils/enums.py and Users/schemas/academic_status.py.
- [ ] **L28** Nineteen schema modules use Pydantic v1 `class Config`, deprecated in Pydantic 2 and removed in 3, while the rest use `model_config`.
- [ ] **L29** Push endpoints are any https URL a signed-in user submits, so the scheduler POSTs (and follows redirects) to arbitrary hosts.
- [ ] **L30** Every Google sign-in fetches Google's signing keys afresh, with the library's 120-second default timeout.
- [ ] **L31** A syllabus parse holds a database connection and an open transaction for the whole provider call, up to 90 seconds.
- [ ] **L32** The dashboard computes a required final for every course against a fixed 90% target, and no client reads the result.
- [ ] **L33** Reminders that went stale unpushed keep their owners in the scheduler's candidate list on every run, indefinitely.
- [ ] **L34** Every Settings save returns the full UserDetail, lazily loading and re-validating every course and grade, with placeholder course figures.
- [ ] **L35** A database error during the startup purge stops the instance from starting, instead of letting /health report 503.
- [ ] **L36** The schema gate checks definer functions by name only, so a changed function body or signature deploys without the schema step.
- [ ] **L37** Date labels mix a hard-coded English weekday with a month name in the browser's locale.
- [ ] **L38** Fitness page visits are never counted in usage analytics: the room list is hand-copied on both sides and both copies miss it.
- [ ] **L39** A course's final grade uses 0 as 'none recorded', so every reader must repeat a `> 0` check and a real 0 cannot be stored.
- [ ] **L40** Cancelling one date of a series and deleting the whole series share one DELETE URL, told apart only by an optional query parameter.
- [ ] **L41** The calendar re-declares which job-application statuses are still open instead of importing the jobs feature's `OPEN_STATUSES`.
- [ ] **L42** Bulk grade entry silently drops a half-filled row, so a grade typed without its 'Out of' value is never saved and nothing says so.
- [ ] **L43** The course-links editor promises that addresses without http:// are assumed https, but its `type="url"` inputs make the browser refuse such addresses before the form submits.
- [ ] **L44** The credits bar reports aria-valuenow above aria-valuemax once a student passes the credit target, the fault the budget ProgressBar already had fixed.
- [ ] **L45** Two editors key removable rows by array index, the bug audit #36 fixed in BulkGradesModal: the syllabus check table and the class-timetable meetings.
- [ ] **L46** The reminder screens tell students reminders only fire while the app is open, but a scheduler now pushes them to devices, so the help text steers people away from a feature that works.
- [ ] **L47** The Repeats header adds one occurrence of every active rule into a single 'each time round' figure, whatever each rule's frequency or number of weekdays.
- [ ] **L48** The task forms copy their shared constants: the 2400-minute estimate cap is a bare literal in four places, `PRIORITY_STEPS` is defined four times, and the repeating-task dialog re-implements the tag parsing `taskFields` exists to share.
- [ ] **L49** API errors are thrown as bare `Error(message)`, so callers cannot tell not-found from invalid input, a server fault or a network failure.
- [ ] **L50** No request has a timeout or can be cancelled, so a stalled connection leaves a page loading with no error.
- [ ] **L51** Preference saves are untyped on the frontend, so a misspelt or unknown key compiles and is silently dropped by the server.
- [ ] **L52** The user fetch in AuthProvider has no stale-response guard, so a slow answer can restore a user after sign-out or a token swap.
- [ ] **L53** `formatMoney` and `formatPercent` choose the minus sign before rounding, so a value that rounds to zero can read as −$0.00 or −0.0%.
- [ ] **L54** A browser keeps receiving a student's reminders after their session ends any way other than Sign out (tab closed, token expired, 401).
- [ ] **L55** The 'permanent deletes ask first' test cannot see eleven destructive api functions, because it only matches `export async function delete|clear…`.
- [ ] **L56** API modules follow three different conventions for paths, declarations and types, with no rule saying which is current.
- [ ] **L57** 'Balance over time' spaces its points evenly by index, not by date, so long quiet stretches and busy weeks look the same width.
- [ ] **L58** A deposit can be submitted with the split computed for a previous amount, which the server then rejects with a validation error.
- [ ] **L59** Saving a planned-spend target or category limit, or stopping a standing instruction, fails silently when the server refuses: no message, only an unhandled rejection.
- [ ] **L60** Four budget dialogs re-seed their form whenever the parent's accounts or categories array is rebuilt, wiping half-typed input: the AddMoneyModal fix was not applied to its siblings.
- [ ] **L61** Many panels still refetch on the whole `user` object, so every Settings save (which rebuilds `user`) reloads them, the fix of old audit #34 applied only to the main hooks.
- [ ] **L62** Saving any one Settings tab re-seeds every field from the server, silently discarding unsaved edits on the other tabs.
- [ ] **L63** SettingsPage is a ~1,000-line single component with 38 state variables, a duplicated data load and a two-request save reported as one.
- [ ] **L64** Names and layout disagree with the modules they hold: `features/calender`, `paycheck_service.py` beside `paycheque_service.py`, route files named for URLs rather than modules, the Teams module behind the Fitness page, and the Finances module behind the Budget page.
- [ ] **L65** Backend dependencies are only half pinned: transitive versions float on every image build, `cryptography` and `requests` are imported directly but undeclared, test tools ship in the production image, and nothing watches for updates.

### Cosmetic (7)

- [ ] **CO1** Dead declarations read as live API: unused schema classes (TokenPayload, three academic-status models), four uncalled frontend API wrappers, and five unused interfaces in grades/types.ts.
- [ ] **CO2** Money helpers the design notes say must live only in app/shared are copied: a private `_money` in the tax packet, and `money_text` twice.
- [ ] **CO3** errors.py carries unused entries and a key named for 409 that documents a 400.
- [ ] **CO4** `calender/api.ts` declares a module-level function named `window`, shadowing the browser global throughout the module.
- [ ] **CO5** Task sharing and event sharing are two hand-kept copies of one client: duplicate owner-view types, accept-status unions, invite-link builders and preview/accept calls.
- [ ] **CO6** `JobCard`'s `hours` prop and JobsPage's `hoursByJob` carry minutes, converted only inside the card.
- [ ] **CO7** Doc comments inside function bodies sit above the wrong code, so they describe a neighbour.

---

## Critical

### C1. The standing-instruction catch-up knows a payment was written only by finding its row, so editing a rule's dates back-fills up to 120 days of duplicate payments and a deleted payment is written again.

*Integrity · verified*

`run_due` recomputes every due date of an instruction (up to 120 days back) and writes each one that has no ledger row with that `recurring_id` and date. Nothing records which dates were already handled, so two ordinary actions corrupt the ledger. Moving a rule's start date or repeat (rent from the 1st to the 5th, weekly to fortnightly) makes every past date of the new pattern 'unwritten', and the next Budget page load writes them all as real expenses dated in the past; deleting a generated payment removes the only evidence it was written, so the next load writes it back. Both reproduced in review on the current code: a $900 monthly rent caught up to 4 rows becomes 8 (the 1st and the 5th of each month) after the edit, and a deleted gym payment returns. Balances, safe-to-spend, the forecast and the budget are wrong by the amount, and the student's own repair (deleting the phantom rows) does not stick. The repeating-task service met the same case and passes `since=today` on edit; the payment service does not.

**Files affected:**
- `backend/app/Finances/services -> [recurring_service.py, transaction_service.py]`
- `backend/app/api/routes -> [recurring.py]`

**Evidence:** Finances/services/recurring_service.py:316 -- update_rule applies starts_on and the recurrence with setattr / apply_recurrence and nothing else; due_dates (:391-404) then takes every occurrence of the edited rule from `max(instruction.starts_on, through - 120 days)` to today and returns those not in written_dates. Reproduced on the SQLite fixtures: a $900 monthly 'Rent' from 2026-06-01, caught up to 2026-10-26 (4 rows, Jul-Oct 1st), then update_rule(starts_on=2026-06-05) and run_due again: 8 rows, 07-01, 07-05, 08-01, 08-05, 09-01, 09-05, 10-01, 10-05. Also: Finances/services/recurring_service.py:85-98 -- written_dates is read from the surviving TransactionModel rows with that recurring_id, so once delete_transaction removes a row its date is no longer 'written', and due_dates (:391-404) returns it again within the 120-day catch-up. Reproduced on the SQLite fixtures: a monthly 'Gym' instruction writes its 2026-10-01 row; delete_transaction on that row, then run_due -> one row again.

**Suggested fix:** Give each instruction a record of handled dates: on `update_rule`, set a catch-up floor (a `catchup_from` column set to today, or equivalent) so dates before the edit are never written for the edited rule; when `delete_transaction` removes a row with a `recurring_id`, add its date to the instruction's `skipped_dates` in the same commit (and say so in the confirm dialog). Add regression tests for both sequences, and clamp `run_due`'s `through` to the user's today while there (see the related low finding).

**What the fix could break:** Production may already hold back-filled duplicates from earlier edits; find them (rows of one rule spaced closer than its interval) and let the owner decide case by case before or with the fix. A student who edited a rule to back-fill missed payments would now enter them by hand; deleting a generated row to have it regenerated would instead skip it.

---

## High

### H1. Update paths validate a PATCH as a fragment, never the merged row, so one edit can store a row its own response model refuses, after which every read of that list returns 500 until the row is repaired by hand.

*Integrity · verified*

Across tasks, events, reminders, repeating tasks, jobs, spending categories, accounts, sinking funds, term blackouts (on create too), courses and grades, the create schemas carry the non-blank and cross-field rules and the response models inherit them, but each update service applies `setattr` for every sent field and commits. A one-space title, a 31-character tag, clearing an event's start time, ticking transfer credit on a course with a final grade, an end date before the stored start, or an explicit null on a field with no null meaning is committed; the PATCH itself answers 500 although the write landed, and every endpoint that lists the row then fails response validation for that user, so the page that would let them undo it no longer loads (the whole Budget page for a blank account name). Explicit nulls on NOT NULL columns and a duplicate course code on rename escape as IntegrityErrors, also 500s. Reproduced in review on the current code for tasks, reminders, events and blackouts, and confirmed by reading for courses and grades.

**Files affected:**
- `backend/app/Tasks/services -> [task_service.py, reminder_service.py, recurring_task_service.py]`
- `backend/app/Calendar/services -> [event_service.py, blackout_service.py]`
- `backend/app/Jobs/services -> [job_service.py]`
- `backend/app/Tasks/schemas -> [task.py, reminder.py, recurring_task.py]`
- `backend/app/Calendar/schemas -> [event.py, blackout.py]`
- `backend/app/Jobs/schemas -> [job.py]`
- `backend/app/Finances/services -> [budget_service.py, account_service.py, sinking_service.py]`
- `backend/app/Finances/schemas -> [budget.py, account.py, sinking.py]`
- `backend/app/Grades/schemas -> [course.py, grade.py]`
- `backend/app/Grades/services -> [course_service.py, grade_service.py]`
- `backend/app/api/routes -> [grades.py]`
- `backend/app/_database -> [models.py]`
- `frontend/src/features/grades -> [types.ts]`

**Evidence:** Tasks/services/task_service.py:371-374 -- update_task strips the title and then runs `setattr(task, key, value)` for every sent field, with no blank-title or tag check; TaskBase.validate_task (Tasks/schemas/task.py:56) refuses `self.title.strip() == ""` and tags over 30 characters, and runs again when the `Task` response model serialises the stored row. Same shape in event_service.update_event:148 (EventBase.validate_event, Calendar/schemas/event.py:150, refuses an end_time without a start_time), reminder_service.update_reminder:169 (no strip, and no `remind_at.tzinfo` check, which ReminderBase.validate_reminder applies at Tasks/schemas/reminder.py:47), recurring_task_service.update_rule:206 and job_service.update_job:206 (JobBase.validate_job: blank name; a pay schedule with pay_starts_on cleared). Reproduced on the SQLite test fixtures: update_task(TaskUpdate(title=' ')) stores '' and Task.model_validate of the listed row then fails 'String should have at least 1 character'; TaskUpdate(tags=['x'*31]) is stored and the read fails 'A tag cannot be longer than 30 characters'; ReminderUpdate(title='  ') commits, its own response fails, and every later list_reminders raises; EventUpdate(start_time=None) on a 07:00-08:00 event stores (None, 08:00) and Event.model_validate fails 'An event with an end time needs a start time'; ReminderUpdate(remind_at=15:00+00:00) is stored as 15:00 local wall time. Also Finances/services/budget_service.py:207 -- update_category runs `setattr(category, key, value)` after only a case-insensitive clash check, so SpendCategoryUpdate(name=' ') is stored and SpendCategoryBase.validate_category (Finances/schemas/budget.py:40) then fails every SpendCategory response, including GET categories. And Finances/services/account_service.py:664 -- update_account's `setattr(account, key, value)` stores AccountUpdate(name=' '), which AccountBase.validate_account (Finances/schemas/account.py:89) then refuses on every Account response, GET accounts included (the whole budget page). And Finances/services/sinking_service.py:284 -- update_fund's `setattr(fund, key, value)` stores SinkingFundUpdate(name=' ') unstripped, which SinkingFundBase.validate_fund (Finances/schemas/sinking.py:40) then refuses on every SinkingFund response, the fund list included. The same holds on create for term blackouts: Calendar/services/blackout_service.py:120 stores `label=data.label.strip()` (and :165 on update), so TermBlackoutCreate(label='   ') passes `min_length=1` and stores ''; as_schema then fails `TermBlackout.label` min_length after the commit, and every later list_blackouts raises 'String should have at least 1 character' (reproduced on the SQLite fixtures). Also: Application/backend/app/Grades/schemas/course.py -- `class Course(CourseBase)` inherits `validate_course_logic` ("A transfer credit carries credits, not a grade", "end date cannot be before start date", blank code/name), but `CourseUpdate.validate_course_update` checks only the section, weights and a start/end pair sent together, and `course_service.update_course` applies `setattr(course, key, value)` and commits without re-checking the merged row. Likewise `Grade(GradeBase)` refuses a blank name while `GradeUpdate.name` (min_length=1) accepts "   ". Verified with pydantic: `CourseUpdate(transfer_credit=True, final_grade=80)` validates, and `Course.model_validate` of that stored state raises ValidationError. Also: Application/backend/app/Grades/services/course_service.py:315 -- `update_data = data.model_dump(exclude_unset=True)` then `setattr(course, key, value)` for every key; `CourseUpdate` declares `credits`, `required`, `final_grade`, `no_final`, `transfer_credit`, `archived` (and `code`, `name`, `year`, `semester`) as `X | None = None`, while `Course` serialises `credits: float`, `final_grade: float` etc. and models.py:265-288 leaves `credits`, `required`, `final_grade`, `average` nullable. Also: Application/backend/app/Grades/services/course_service.py -- `create_course` checks `CourseModel.code == course_data.code` before inserting, but `update_course` only does `setattr(course, key, value)` and `db.commit()`, so renaming to an existing code hits `uq_courses_user_code` as an IntegrityError; no route or app-wide handler catches IntegrityError. `CourseUpdate.code`, `GradeUpdate.name`, `GradeUpdate.category`, `GradeUpdate.max_score` and the boolean flags are `X | None = None`, so an explicit null is applied to NOT NULL columns.

**Suggested fix:** In every update service, validate the merged state before committing with the same rule functions the create schemas use (build the base schema from row plus patch, or factor the validators into plain functions both paths call) and map failures to 400; reject explicit null for fields without a null meaning (a validator over `model_fields_set`); check the unique course code on update; serialise stored rows without re-running request validators (as `degree.py` already does). Add one PATCH-then-list regression test per module, and run a one-off production check for rows already in a bad state.

**What the fix could break:** Some PATCHes that succeed today (clearing `pay_starts_on`, a one-space title) will return 400 and the frontend must show the message; rows already stored in a bad state must be found and repaired with the fix; re-validation must not re-run mutating validators (tag cleaning) in a way that rewrites stored data; adding NOT NULL needs a check that no row holds NULL.

### H2. Editing any field of a paycheque, even its notes, deletes its ledger rows and re-splits the net by today's income shares, silently moving past money between accounts.

*Integrity · verified*

`update_paycheque` always clears the cheque's deposit rows and rewrites them, and the client always sends `allocations: []` (the `Paycheque` response carries no allocations, so it could not send the original split back), so the net is re-split by the shares in force today rather than those that applied when the money arrived. Students change their income split during a term, so correcting a September cheque's notes, period or date in November moves September's money between Spending, Savings and the rest, changing balances, the running-balance chart, past months' figures and the plan review with nothing on screen to say why; an account archived since loses its share. Reproduced in review: a $1,000 cheque split 500/200/200/100 lands entirely in Savings after a notes-only edit once the shares change. Totals still add up, which is what makes it hard to notice.

**Files affected:**
- `backend/app/Jobs/services -> [paycheque_service.py]`
- `backend/app/Jobs/schemas -> [paycheque.py]`
- `backend/app/api/routes -> [jobs.py]`
- `frontend/src/features/jobs/components -> [PaychequeModal.tsx]`
- `frontend/src/features/jobs -> [types.ts]`

**Evidence:** Jobs/services/paycheque_service.py:428-433 -- update_paycheque always runs `clear_deposit(db, user_id, cheque.group_id)` and writes new rows with `data.allocations if allocations is not None else None`, so with no allocations deposit_rows (:215) uses `split_income(net, accounts)` over `active_accounts` (current shares, archived accounts excluded). The frontend's PaychequeModal always sends `allocations: []`. Reproduced on the SQLite test fixtures: a $1,000 cheque recorded on 2026-09-15 under the seeded 50/20/20/10 shares lands as Spending 500, Savings 200, Investments 200, Emergency 100; after the shares change to Savings 100%, `update_paycheque(PaychequeUpdate(notes='typo fixed'))` leaves Savings 1000 and every other account 0 for that cheque. Also: Application/frontend/src/features/jobs/components/PaychequeModal.tsx:42 -- `formFor` always sets `allocations: []`, and the edit path sends it (`const { job_id: _ignored, ...rest } = payload; await updatePaycheque(user.id, paycheque.id, rest);`); paycheque_service.update_paycheque then does `clear_deposit(db, user_id, cheque.group_id)` and rebuilds with `deposit_rows(..., data.allocations if allocations is not None else None, ...)`, where `split = allocations or split_income(net, accounts)` uses the current shares.

**Suggested fix:** Rewrite the deposit only when the net changes, and then keep the existing rows' proportions (or a stored allocation); leave the ledger alone for notes, period and date changes (moving `occurred_on` on the existing rows when the date changes). Return the cheque's allocations so the form can show and keep them; re-split by today's shares only when the student asks.

**What the fix could break:** Cheques already edited have been re-split and cannot be recovered from the database; the fix only stops further drift. Keeping the old rows changes which transaction ids survive an edit (nothing references them today). Tests pin the current rewrite-on-update behaviour.

### H3. Once any date of a weekly shift pattern is confirmed, the pattern can no longer be re-saved or deleted: both paths fail on the shift_records foreign key and return 500.

*Reliability · verified*

A shift pattern is one event row, and each confirmed date is a shift_records row pointing at it. remove_shift deletes the records first and unpicks their cash-tip ledger rows, but the two other delete paths do not: re-saving the weekly pattern on the Jobs page (the documented way to change one's hours) and deleting the series from the calendar both delete the event directly. With foreign keys enforced (SQLite runs with foreign_keys=ON, Postgres always) the flush fails and the request returns 500. Students confirm past shifts as a matter of routine, so any job with one confirmed shift has a pattern that can be neither changed nor removed; the only path that works is deleting the whole job, which also deletes its paycheques. Were enforcement ever off, the same code would orphan the records and leave their cash-tip ledger rows explaining nothing.

**Files affected:**
- `backend/app/Jobs/services -> [job_service.py]`
- `backend/app/Calendar/services -> [event_service.py]`
- `backend/app/_database -> [models.py]`
- `backend/app/api/routes -> [jobs.py, calendar.py]`

**Evidence:** Jobs/services/job_service.py:406-421 -- set_shift_schedule loads the job's repeating shift events and calls `db.delete(event)` then `db.flush()`; shift_records.event_id is `Column(Uuid, ForeignKey("events.id"), nullable=False)` with no ondelete (_database/models.py:1337) and the only relationship is the many-to-one ShiftRecordModel.event (models.py:1360), so the flush issues DELETE on events that confirmed records still reference. Calendar/services/event_service.py:278 -- delete_event (DELETE /calendar/{user_id}/events/{event_id}) deletes any event, shifts included, the same way. Reproduced on the SQLite test fixtures: confirm one Tuesday of a weekly pattern, then call set_shift_schedule with a new pattern -> sqlite3.IntegrityError FOREIGN KEY constraint failed; delete_event on that shift event -> the same error. Repro scripts in the backend_a scratchpad (ba_work/repro/test_shift_schedule_resave.py, test_delete_confirmed_shift_event.py).

**Suggested fix:** Decide what a pattern change means for dates already recorded, and implement it in one helper that set_shift_schedule and delete_event (for a shift) both call. Either end the old series instead of deleting it (set recur_until to the day before the change and start the new pattern from the change, so past records stay attached to their event), or delete the records explicitly first, unpicking cash tips exactly as remove_shift does, behind a confirmation. Add tests that confirm a shift and then re-save the pattern and delete the series.

**What the fix could break:** Ending the old series rather than deleting it keeps the old times visible on past weeks of the calendar, which is correct history but a visible change. Deleting records removes confirmed hours and cash-tip income rows from the ledger, so it needs an explicit confirmation in the UI. Earnings and the tax packet read records by date, so whichever option is chosen must keep past figures stable.

### H4. Safe to spend subtracts every outgoing standing instruction and sinking-fund contribution from any counted account, including bills paid from savings and transfers into spending, from the spending balance.

*Integrity · verified*

Safe to spend is the headline of the Budget page and is meant to be spending balances less what will leave them before the next cheque. Because commitments are selected by sign and counted-ness alone, money that never touches the spending accounts is subtracted from them: a bill paid from Savings, a transfer between two other accounts, a sinking fund funded from Savings, and worst of all a standing transfer from Savings into Spending, which adds money but is subtracted as if it left. A student who tops up their spending account from savings every month sees their safe figure understated by twice nothing, and one who pays insurance from savings is told they cannot afford what they can. The forecast on the same page makes the right distinction, so the two figures disagree.

**Files affected:**
- `backend/app/Finances/services -> [safe_service.py, sinking_service.py, recurring_service.py]`
- `backend/app/Finances/schemas -> [safe.py]`

**Evidence:** Finances/services/safe_service.py:158-162 -- `leaving = [charge for charge in charges if charge.signed_amount < 0 and charge.account_id not in uncounted]`, and recurring_service.upcoming:426-432 signs every expense and transfer negative by its source (`leaving = instruction.kind in (EXPENSE, TRANSFER)`), so the only test is 'counted', never 'drawn from a spending account'. sinking_service.unfunded_total:356 filters funds only by `from_account_id.notin_(uncounted_accounts(user_id))`. The forecast gets this right (forecast_service.recurring_events:275-279 checks `charge.account_id in spendable_ids` and adds a transfer's incoming leg). Reproduced on the SQLite test fixtures: Spending holds $1,000 and Savings $5,000; adding a monthly $400 Savings-to-Spending 'Allowance' transfer due on the 20th and a $250 'Insurance' expense paid from Savings on the 25th moves safe_now on the 10th from $1,000.00 to $350.00, with both listed as commitments.

**Suggested fix:** Select commitments by the accounts they draw on, the way forecast_service.recurring_events does: an expense counts when its account is one of `spendable_accounts`; a transfer counts by its net effect on the spending set (out minus in); a deposit is never a commitment. Filter sinking funds to those whose from_account is a spending account. Share one helper between safe_service and forecast_service so they cannot diverge again, and add tests for a savings-paid bill and a savings-to-spending transfer.

**What the fix could break:** Safe-to-spend will rise for students with standing instructions on non-spending accounts, which is the correct figure but a visible change on the headline; tests that pin today's numbers may need updating.

### H5. Deleting one allocation of a paycheque's deposit (scope=row) deletes the whole cheque but leaves its other income rows in the ledger with nothing explaining them.

*Integrity · verified*

A paycheque's net is a deposit: several income rows sharing a group_id, owned by the cheque. The delete path treats 'row' scope as 'drop one allocation of a deposit' (the deliberate #3 fix), and separately treats any grouped row as a reason to delete its cheque. Combined, removing one allocation from the account page deletes the cheque, its deductions and its expected-pay verdict from Jobs, while 75% of the net stays in the ledger as anonymous 'Cafe pay' income. The Jobs page then reports less paid than the ledger received, the tax packet loses the cheque's gross and deductions, and nothing in the UI can reach the stranded rows as a cheque again. This is the orphaned-record fault the design notes say cascades must prevent in both directions.

**Files affected:**
- `backend/app/Finances/services -> [transaction_service.py]`
- `backend/app/api/routes -> [finances.py]`

**Evidence:** Finances/services/transaction_service.py:520-529 -- whenever the row has a group_id, delete_transaction deletes every PaychequeModel whose group_id matches (`for cheque in doomed_cheques: db.delete(cheque)`), but the ledger delete at :539-545 removes the whole group only `if ... (is_transfer or scope == "group")`, else just `db.delete(transaction)`. Reproduced on the SQLite test fixtures: a $1,000 cheque split over the four seeded accounts, then delete_transaction(first_row, scope='row') -> 3 income rows left, 0 paycheques.

**Suggested fix:** For a row owned by a paycheque, either refuse scope=row (a cheque's split is changed by editing the cheque), or delete the whole group whenever a cheque owns it. The same check belongs in front of any other record that owns a group (sinking contributions are transfers, so they are already removed whole).

**What the fix could break:** A client offering 'just this allocation' for cheque rows would get a 400 or a larger delete than before, so the account-page dialog should say the cheque goes with it. Production may already hold stranded cheque rows; a query for income rows whose group_id matches no paycheque or deposit sibling would find them.

### H6. Panels refetch only when a hand-bumped nonce changes, and some saves never bump it: after a grade is saved the course page's band, 'Worth doing next', required-final and schemes keep their old figures, and after an event is saved the calendar's free blocks, week load and shift conflicts do.

*Integrity · verified*

The course average and grade columns update after a save, but 'Can still finish 62 - 94', 'Worth doing next', 'On the final: You need 71%' and the scheme comparison are computed by separate endpoints and only refetch when their nonce changes, which a grade save does not do. A student who enters a midterm mark sees the new average beside a band, a needed-final figure and a ranking that still describe the course before the mark, and nothing on screen says they are stale; they only correct after leaving and returning to the page. Every write also empties the GET cache, so no background refresh rescues it. These are exactly the figures students use to decide where to spend effort.

**Files affected:**
- `frontend/src/pages/grades -> [CourseDetailPage.tsx]`
- `frontend/src/features/grades/components -> [GradeBand.tsx, CheapestPath.tsx, RequiredFinalPanel.tsx, GradingSchemes.tsx, CourseCost.tsx]`
- `frontend/src/pages -> [CalendarPage.tsx]`
- `frontend/src/features/calender/components -> [TimeInsights.tsx]`

**Evidence:** Application/frontend/src/pages/grades/CourseDetailPage.tsx:204 -- `refreshCourse` only does `setCourse(await fetchCourseDetail(...))`; it is what `onGradeAdded`, `onGradeUpdated`, `onGradeDeleted`, the bulk-add and the delete-grade confirm call (line 443 and below). The panels refetch on `nonce={reloadNonce}` (line 320 onward), and `setReloadNonce` is only called by the links dialog, the counting-scheme switch and 'Try again'. Each panel documents its `nonce` prop as 'Bumped by the page whenever a grade changes, to refetch.' CalendarPage.tsx:324 -- `EventModal ... onSaved={reload}` refreshes the grid but not `insightNonce`, which TimeInsights and ShiftConflictsPanel refetch on; every other calendar action (skip, delete, task save, blackouts) bumps it.

**Suggested fix:** Have `refreshCourse` bump `reloadNonce` and the EventModal save bump `insightNonce` (or derive the panels' refetch key from the data they depend on rather than a manual counter), and add tests that saving a grade refetches the band and that adding an event refetches the free blocks.

**What the fix could break:** Each grade save then issues the four or five panel requests again, which is the intended behaviour; panels briefly show their previous figures until the answers land.

### H7. A wrong password on sign-in is treated as an expired session: the login page reloads and the real error is never shown.

*Reliability · verified*

`send` assumes any 401 means the stored session died, but the sign-in endpoints use 401 for a refused credential. `loginWithEmail` and `loginWithGoogle` go through `post`, so a mistyped password makes LoginPage set the error to "Session expired" and the browser immediately navigates to /login, reloading the page it is already on: the typed email is cleared and the server's "invalid credentials" detail is never displayed. Every invited user who mistypes a password sees the sign-in page silently reset, which reads as the app being broken, and a rejected Google account looks the same. No test covers a 401 from an auth route (apiClient.test.tsx only covers caching).

**Files affected:**
- `frontend/src/services -> [apiClient.ts, authClient.ts]`
- `frontend/src/pages -> [LoginPage.tsx]`
- `backend/app/api/routes -> [auth.py]`

**Evidence:** Application/frontend/src/services/apiClient.ts:101-105 -- `if (response.status === 401) { sessionStorage.removeItem("access_token"); clearApiCache(); window.location.href = "/login"; throw new Error("Session expired"); }` runs for every request, while auth.py login_with_email raises `HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_auth["invalid_credentials"])` and the Google route raises 401 on a rejected ID token. `getBlob` (apiClient.ts:151-154) repeats the same branch.

**Suggested fix:** Treat a 401 as session expiry only when the request carried a bearer token (or exclude `auth/*` paths), and otherwise throw the server's detail like any other error; share one 401 handler between `send` and `getBlob`. Add a test that a 401 from `auth/login` surfaces its detail without navigating.

**What the fix could break:** Expired-session handling must keep redirecting for authenticated calls; the set-password flow (which revokes other sessions) and any page that relies on the redirect should be re-tested. Users will start seeing the server's sign-in messages, so their wording becomes user-facing.

### H8. The dashboard shows balances, net worth and this month's spending before due standing payments are written, so it is wrong until the Budget page is opened.

*Integrity · verified*

Standing instructions are written to the ledger only when a client asks, and useBudget's own comment explains why it asks first: otherwise the balances are out of date and safe-to-spend counts a paid bill as cash in hand. The dashboard is the landing page and skips that step, so on the morning rent or a subscription falls due the home screen's net worth, account balances and 'spent this month' omit it. A student who checks only the dashboard sees money they no longer have; the figures jump when they next open Budget, which reads as the app being inconsistent.

**Files affected:**
- `frontend/src/features/budget/hooks -> [useBudgetGlance.ts, useBudget.ts]`
- `frontend/src/pages -> [Dashboard.tsx]`
- `backend/app/api/routes -> [recurring.py]`

**Evidence:** Application/frontend/src/features/budget/hooks/useBudgetGlance.ts:30-34 -- `Promise.all([fetchAccounts(userId), fetchBudgetSummary(userId, firstOfMonth(today())), fetchNetWorth(userId)])` with no `runRecurring`; the only caller of the catch-up is useBudget.ts:171 (`await runRecurring(userId).catch(() => undefined);`), and the only server path to `run_due` is POST /recurring/run (recurring.py:112), whose docstring says there is no scheduler.

**Suggested fix:** Run the catch-up once per session or page load before any money read, in one place (for example a shared `ensureRecurringCaughtUp(userId)` awaited by both hooks, or in AuthProvider after sign-in), or have the server run `run_due` inside the balance-reading endpoints.

**What the fix could break:** Another POST on the dashboard's first load (it already keeps the cache when nothing was written); running it server-side on reads turns GETs into writes, which conflicts with the GET cache's assumptions and row-security write paths.

### H9. Tapping × on a transaction deletes it, or both halves of a transfer, at once: no confirmation and no undo.

*Integrity · verified*

The project's rule is that every permanent delete asks first (deleteConfirmations.test.ts), and Ideas/audit.md lists 'Deletes confirm ... Transactions' as verified healthy, but an ordinary expense, an income row or a transfer is removed by a single click or tap on a small × beside the amount, with no dialog and no way back. On a phone the × sits next to the row's edit target, so a mis-tap silently changes balances, the month's spending and safe-to-spend. The test misses it because the delete call lives in a hook it exempts (`PROVIDES_CONFIRM_STATE`) and the consumers render a modal for the split case, which satisfies 'renders a confirmation'. This contradicts the archived audit's 'Verified healthy' entry 'Deletes confirm' (Transactions included). That entry was too broad when written: at its commit (d0bcd1b) `useTransactionDelete` already deleted single rows and transfers on one click, and `deleteConfirmations.test.ts` exempts the hook (`PROVIDES_CONFIRM_STATE`) on the assumption that it supplies the confirmation, which it does only for multi-row deposits.

**Files affected:**
- `frontend/src/features/budget/hooks -> [useTransactionDelete.ts]`
- `frontend/src/features/budget/components -> [Transactions.tsx, BudgetView.tsx]`
- `frontend/src/pages/budget -> [AccountDetailPage.tsx]`
- `frontend/src/features -> [deleteConfirmations.test.ts]`

**Evidence:** Application/frontend/src/features/budget/hooks/useTransactionDelete.ts:33-40 -- `requestDelete` sets `pending` only when `transaction.kind !== "transfer" && transaction.group_size > 1`, otherwise `void run(transaction, "group")`; Transactions.tsx:96 wires the row's × button as `onClick={() => onDelete(transaction)}`, and BudgetView.tsx:205 / AccountDetailPage.tsx:243 pass `onDelete={remove.requestDelete}`. The only DeleteConfirmModal tied to it opens on `remove.pending`, i.e. split deposits.

**Suggested fix:** Route every `requestDelete` through a confirmation: one DeleteConfirmModal for a plain row (naming the description and amount, and 'both sides' for a transfer) and the existing scope dialog for split deposits; or add an undo toast that restores the row. Tighten the test so a hook-provided delete must be reachable only through a rendered confirm.

**What the fix could break:** One more click for every deletion on the budget and account pages; the coordinator should check whether the archive's 'verified healthy' entry meant only the split-deposit case before treating this as a regression.

---

## Medium

### M1. Errors are mapped to status codes by hand in each route, with no app-wide handler, so ordinary mistakes return 500 (an uninvited Google sign-up, renaming a category onto a used name, a one-sided shift-conflict window) and some routes choose 404 or 400 by searching the message text.

*Reliability · verified*

The design README gives each status a meaning (422 malformed, 400 valid but wrong, 404 missing or not yours, 403 path user, 429 throttled), but every route re-implements it: a `try/except ValueError` around some service calls and not others, `if result is None` for 404, and in grades.py `404 if "not found" in message.lower() else 400`. `main.py` registers no exception handler, so whatever a route forgets (a ValueError, an IntegrityError on a unique index) becomes an unexplained 500 and a stack trace in the logs. For an invite-only release the first instance matters most: anyone not on the allowlist who uses Google sign-in gets a 500 rather than the 'invitation only' message, because `get_or_create_user_by_google_id` runs outside the route's try (confirmed in review; the route is never called by a test). Renaming a category onto an existing name was reproduced returning 500. With contributors joining, each new route copies whichever neighbour it starts from.

**Files affected:**
- `backend/app/api/routes -> [jobs.py, finances.py, auth.py, grades.py]`
- `backend/app/Jobs/services -> [conflict_service.py]`
- `backend/app/Finances/services -> [budget_service.py]`
- `backend/app/Users/services -> [user_service.py]`
- `backend/app/Grades/services -> [grade_service.py, cheapest_path.py]`

**Evidence:** api/routes/jobs.py:92-96 -- the 400 checks run `if start and end and ...`; with `start` omitted, conflict_service.shift_conflicts defaults it to today and calls list_occurrences(start - 1 day, end), which raises ValueError ('The window ends before it starts' or 'cannot be longer than 400 days') that nothing catches. Also: api/routes/finances.py:1120-1126 -- edit_category calls `update_category(db, user_id, category_id, category)` with no try/except, while update_category raises ValueError('A category with that name already exists') (budget_service.py:203-204) and every sibling handler maps ValueError to 400. tests/test_categories_and_split.py:153 ('renaming_to_an_exact_duplicate_is_a_refusal_not_a_500') tests the service only. Reproduced through the API with TestClient on the SQLite fixtures: PATCH /api/finances/{user}/categories/{id} {"name": <another category's name>} -> 500 Internal Server Error. Also: Application/backend/app/api/routes/auth.py -- in `login_with_google` only `verify_google_token(...)` is inside the try; `user = user_service.get_or_create_user_by_google_id(db, user_data)` follows it unguarded, and that function raises `ValueError(error_auth["not_invited"])` for an address off the allowlist (and `create_user` raises ValueError when the address was taken meanwhile). main.py registers no exception handler, and the route is never called in tests (test_isolation.py skips it because it verifies over the network). Also: Application/backend/app/api/routes/grades.py -- `get_grade_band`, `get_cheapest_path` and `get_required_final_score` each do `status_code = 404 if "not found" in message.lower() else 400` on a ValueError, because the services raise `ValueError("Course not found.")` for a missing course and ValueError for bad requests alike.

**Suggested fix:** Raise typed domain errors from services (NotFound, Invalid, Conflict) and register one handler in `main.py` that maps them, plus IntegrityError on known unique indexes, to 404/400/409 with the message; delete the per-route string matching; fix the four instances listed; add a route test for the uninvited Google path with a stubbed verifier.

**What the fix could break:** Some failure responses change status (500 to 400/409); the frontend shows messages by text, so it is mostly unaffected. The handler must keep 'missing' and 'another user's' indistinguishable (both 404).

### M2. Data loading is hand-rolled in about sixty hooks and components, in three drifting patterns, so the out-of-order and stale-cache guards the last audit added are missing from some.

*Maintainability · plausible*

Each hook copies the same dozen lines (userId from auth, loading/error state, a load callback, `useApiRefresh`, a mount effect) and each copy has drifted. Audit #12 (out-of-order responses showing the wrong data) and #34 (hooks re-fetching on every `refreshUser()` because they depend on the user object) were fixed hook by hook, so the fixes are present in some and absent in others: a grades hook whose initial load resolves after a post-save reload will put the pre-save list back on screen, and a Settings save re-runs the blind-spots fetch. With more contributors, the next hook will be copied from whichever neighbour is nearest, guard or no guard.

**Files affected:**
- `frontend/src/features/grades/hooks -> [useCourses.ts, useDashboard.ts, useBlindSpots.ts]`
- `frontend/src/features/calender/hooks -> [useCalender.ts, useTimeGlance.ts, useWorkloadForecast.ts]`
- `frontend/src/features/tasks/hooks -> [useTasks.ts, useReminders.ts]`
- `frontend/src/features/budget/hooks -> [useBudget.ts, useAccountActivity.ts, useBudgetGlance.ts]`
- `frontend/src/features/jobs/hooks -> [useJobs.ts]`
- `frontend/src/features/budget/components -> [CashFlowForecast.tsx, YearPlan.tsx, TermBudget.tsx]`
- `frontend/src/pages -> [ApplicationsPage.tsx]`

**Evidence:** useCalender.ts:76 and useTasks.ts:43 use a `latestRequest` ticket so only the newest answer is applied; useTimeGlance.ts:53 and useWorkloadForecast.ts:39 use a `cancelled` flag plus `useApiRefreshCount`; useCourses.ts, useDashboard.ts and useBlindSpots.ts apply whatever resolves last with no guard; useBlindSpots.ts:27 still depends on `[user]` rather than `user?.id` (`}, [user]);`), and swallows failures into `setSpots([])`. Also: Application/frontend/src/features/jobs/hooks/useJobs.ts:30-68 -- `const latestRequest = useRef(0); ... const ticket = ++latestRequest.current; ... if (ticket !== latestRequest.current) return; ... useApiRefresh(load);` repeated in 21 files (grep `latestRequest`/`++latest`), a `let cancelled = false` variant in 38 more, and the same four-line 'The id, not the object' comment copied into 11 hooks.

**Suggested fix:** Extract one `useApiResource(key, fetcher)` hook (or adopt a small query library) that owns the ticket guard, `user?.id` dependency, loading/stale/error state and the `useApiRefresh` subscription, and move these hooks onto it one at a time.

**What the fix could break:** Hook return shapes differ (`summary`, `spots`, `forecast`, `stale`), so callers change unless thin wrappers keep the old names; tests that count requests (useBudget.test.ts style) would catch behaviour changes.

### M3. Standing payments, repeating-task occurrences and sinking-fund contributions are de-duplicated by a read-then-insert with no unique index, both catch-ups run on every page load, and a standing payment is committed before it is stamped as written.

*Integrity · verified*

All three rules ('one payment per instruction per date', 'one occurrence per repeating task per date', 'one contribution per fund per month') are enforced only by reading first. Two requests that overlap both see nothing written and both insert: the Budget page runs the standing-instruction catch-up on every load (useBudget calls runRecurring), the Tasks page runs the repeating-task catch-up on every load, and a double-tapped 'set aside' fires two contributions. For standing payments there is a second path to a duplicate without any concurrency: the payment commits before the recurring_id stamp, so a failure between the two commits leaves an unstamped rent payment that the next catch-up writes again. A duplicated rent payment or fund transfer is real money counted twice in a balance and in safe-to-spend, and nothing on screen marks it as a duplicate.

**Files affected:**
- `backend/app/Finances/services -> [recurring_service.py, sinking_service.py]`
- `backend/app/Tasks/services -> [recurring_task_service.py]`
- `backend/app/_database -> [models.py]`
- `frontend/src/features/tasks/hooks -> [useTasks.ts]`
- `frontend/src/features/tasks -> [api.ts]`

**Evidence:** Finances/services/recurring_service.py:391-404 -- due_dates reads written_dates (`TransactionModel.recurring_id == recurring_id`, :85) and returns every occurrence not in it; write_occurrence (:419-466) calls create_transaction / create_transfer / record_deposit, each of which commits its rows itself (transaction_service.py:275, :316; deposit_service.py:143), and only then runs a second UPDATE setting recurring_id and commits again (:341-344). Tasks/services/recurring_task_service.py:501-505 -- materialise skips dates in `already = written_dates(db, rule.id)` and inserts the rest. Finances/services/sinking_service.py:370-378 -- contribute checks `already` for (fund_id, for_month) then inserts. _database/models.py has no unique index on transactions(recurring_id, occurred_on), tasks(recurring_id, occurrence_date) or sinking_contributions(fund_id, for_month), although the column comments call each pair the dedup key. Also: Application/backend/app/Tasks/services/recurring_task_service.py:103 -- `written_dates` reads existing `occurrence_date`s and `materialise` inserts the rest; models.py has only the non-unique `Index("ix_tasks_recurring_id", TaskModel.recurring_id)`. Frontend: useTasks.ts:59 `await runRepeating(userId).catch(() => undefined);` runs at the start of every `load()`, which re-runs on each filter toggle and every `reload()` after a save.

**Suggested fix:** Add unique indexes on transactions(recurring_id, occurred_on) (only one row per transfer leg needs it, so key on account_id too, or make it partial where the dialect allows), tasks(recurring_id, occurrence_date) and sinking_contributions(fund_id, for_month), and treat an IntegrityError in the catch-ups as 'already written'. Make write_occurrence build its rows with recurring_id set and commit once, using unsaved row builders (as deposit_rows and transfer_rows already do for paycheques and funds).

**What the fix could break:** Building the indexes fails if production already holds duplicates, so check first and clean up by hand. A transfer writes two rows with the same recurring_id and date, and a deposit several, so the payment index must include account_id. The catch-ups must handle the constraint error without aborting the other rules' payments.

### M4. Saving a course timetable replaces it wholesale: every cancelled class date comes back on each save, and a slow or failed load lets the blank form replace the whole timetable.

*Integrity · verified*

Cancelling one lecture is stored as a skipped date on the series. The timetable form is the place a student fixes a room or a time, and saving it replaces the series wholesale, so every cancellation made since (a professor's sick day, a lab that did not run) reappears on the calendar and in free-time and week-load figures, with nothing to say they were ever cancelled. Members and invite links on a class event would go the same way, though class events are rarely shared.

**Files affected:**
- `backend/app/Calendar/services -> [class_schedule_service.py]`
- `frontend/src/features/calender/components -> [ClassScheduleModal.tsx]`

**Evidence:** Calendar/services/class_schedule_service.py:167-168 -- set_class_schedule runs `db.delete(event)` for every lecture, lab and discussion of the course, then writes new events with `skipped_dates=[]` (:203). Also: Application/frontend/src/features/calender/components/ClassScheduleModal.tsx:320 -- the save button is `disabled={saving || !hasTermDates}`, not while `loading` or after the load's `.catch` set an error, and the form starts as `[blankMeeting()]`; class_schedule_service.py:121 `set_class_schedule` deletes every lecture/lab/discussion event and writes new ones, its Note saying 'dates cancelled on them (`skipped_dates`) ... are not carried over'.

**Suggested fix:** Carry each old series' skipped dates (those still inside the new term) onto the replacement that matches it by kind and weekday, or update matching events in place instead of delete-and-insert.

**What the fix could break:** Matching old to new meetings is a heuristic when the timetable changes shape; a skipped date that no longer falls on a meeting day is harmless but should be dropped.

### M5. Services commit inside themselves, so operations that must be all-or-nothing span several transactions: recording or deleting tuition, applying a syllabus and confirming a subscription can each be left half-done.

*Integrity · verified*

`create_transaction`, `record_deposit`, `create_rule`, `create_course`, `add_grades_bulk` and others commit before returning, which the design notes already warn about for deposits. Any operation built from two of them crosses a commit between its halves: `record_tuition` commits the expense, then the payment and its deductions; `delete_tuition` commits the payment's removal, then the row's; syllabus `apply` commits the course, the grades, each rule and the applied stamp separately, with a compensating delete for only one of the gaps; `confirm_subscription` commits the new rule, then tags its charges. A dropped pooler connection, a constraint error or a Cloud Run instance recycled between commits leaves a ledger row with no tuition record (unreachable from the tuition editor), money gone from Grades but still in the ledger, a half-built course that blocks the retry, or a second standing instruction that doubles a subscription. The standing-payment catch-up has the same shape (payment committed before its `recurring_id` stamp), covered in the de-duplication finding.

**Files affected:**
- `backend/app/Finances/services -> [tuition_service.py, transaction_service.py, subscription_service.py, recurring_service.py]`
- `backend/app/Intake/services -> [syllabus_service.py]`
- `backend/app/Grades/services -> [course_service.py, grade_service.py]`

**Evidence:** Finances/services/tuition_service.py:240-276 -- record_tuition calls create_transaction, which adds and commits the expense row on its own (transaction_service.py:274-275), and only then adds the TuitionPaymentModel and its deductions and commits again. delete_tuition (:522-531) deletes the payment and commits, then calls delete_transaction for the ledger row, which commits separately. Also: Application/backend/app/Intake/services/syllabus_service.py -- `apply` calls `create_course` (commits), then `add_grades_bulk` (commits) inside `try: ... except Exception: db.rollback(); delete_course(...)`, then `file_rules` (each `set_own` commits), then sets `row.applied_at` and commits; the duplicate check `You already have a course {code}` runs before any of it. Also: Finances/services/subscription_service.py:250-259 -- confirm_subscription calls create_rule (which commits the new instruction) and then tags the charges with a separate UPDATE and commit; nothing checks whether the given transaction_ids already carry a recurring_id.

**Suggested fix:** Give the shared write functions an unsaved or flush-only form (as `deposit_rows` and `transfer_rows` already are for paycheques and funds) and have each composite operation commit once; make `confirm_subscription` refuse charges that already carry a `recurring_id`.

**What the fix could break:** Adding a no-commit path to shared functions invites misuse by other callers; keep the default unchanged and test each composite path for atomicity.

### M6. Nothing checks code style or static types beyond `tsc`: no Python linter, formatter or type checker anywhere, no ESLint or formatter for the frontend despite `eslint-disable` directives in its source, and the frontend type-check skips two build files.

*Contributor · verified*

CI deliberately blocks nothing (its header says so, and that is the owner's decision), but it also checks nothing beyond the tests and `tsc`. The Python side has no linter, formatter or type checker at all, which is how a missing `Raises`-path, an unused import or a None passed where a date is expected reaches review; nineteen schema modules still use the Pydantic v1 `class Config`, which a linter would flag. The frontend has no ESLint even though React's hook rules are exactly what its hand-written data hooks keep getting subtly wrong, and seven `eslint-disable` directives show someone expected them to run. `tsconfig.json` lists root files by hand, so `apiPreconnect.ts` (which decides the deployed preconnect hint) is never type-checked. With contributors joining, there is also no shared formatting, so diffs will fill with whitespace churn.

**Files affected:**
- `frontend -> [package.json, tsconfig.json, vite.config.ts, apiPreconnect.ts, apiPreconnect.test.ts]`
- `.github/workflows -> [ci.yml]`
- `frontend/src/features/budget/components -> [CoursePicker.tsx]`
- `frontend/src/features/partners -> [PartnersPanel.tsx]`
- `frontend/src/shared/components -> [SharingSection.tsx]`
- `backend -> [requirements.txt]`

**Evidence:** Application/frontend/package.json -- scripts are dev/build/preview/typecheck/test only, no eslint, prettier or biome in devDependencies or node_modules/.bin, no config file; yet CoursePicker.tsx carries `// eslint-disable-next-line react-hooks/exhaustive-deps` (and 6 more directives across 7 files). ci.yml's frontend job runs `npm test` and `npm run build` only. Also: Application/frontend/tsconfig.json -- `"include": ["src", "vitest.config.ts", "securityHeaders.ts", "securityHeaders.test.ts"]`; `tsc --noEmit --listFilesOnly` lists vitest.config.ts, securityHeaders.ts and securityHeaders.test.ts as the only root .ts files, so apiPreconnect.ts (imported only by vite.config.ts) is never checked. Also: .github/workflows/ci.yml:67 and :114 -- the backend jobs run only `python -m pytest tests/ -q -W error::sqlalchemy.exc.SAWarning`; :146 and :155 -- the frontend job runs only `npm test` and `npm run build`. Application/backend/requirements.txt lists no ruff, flake8, black, mypy or pyright, and no config for any exists in the repository.

**Suggested fix:** Add ruff (lint and format) and a type checker (mypy or pyright, starting lenient) for the backend, ESLint (typescript-eslint, react-hooks, jsx-a11y basics) and Prettier or Biome for the frontend, each as a CI step that reports like the tests do; include all root `*.ts` files in the type-check (or a tsconfig.node.json).

**What the fix could break:** The first runs will report many findings; start with a small rule set (rules-of-hooks, exhaustive-deps, unused imports, pyflakes) as errors and the rest as warnings, and format in one dedicated commit to keep blame readable.

### M7. Configuration is read two ways and fully validated by neither: half the backend settings are raw `os.getenv` reads that never see Application/.env and are not checked at startup, LLM settings are checked only when a parse runs, and a frontend build without VITE_API_BASE_URL silently targets localhost.

*Reliability · verified*

`app/config.py`'s `Settings` reads `Application/.env` and refuses to start without a valid `JWT_SECRET` or `GOOGLE_CLIENT_ID`, which is the right shape. But `ALLOWED_ORIGINS`, `ENABLE_DOCS`, `RUN_SCHEMA_ON_STARTUP`, `LOG_LEVEL`, `ALLOWED_SIGNUP_EMAILS` and `DATABASE_URL` are read with `os.getenv` in main.py, signup_policy.py and db.py, so values set in the `.env` the example file tells contributors to fill in are silently ignored unless the shell exports them, and a typo in any of them is never reported. `LLM_PROVIDER` is accepted at startup whatever it says, so a misspelt provider reads as available and every parse then fails. On the frontend, a production build with no `VITE_API_BASE_URL` ships a site whose CSP and API calls point at localhost, and the only warning fires for an unparsable URL. Each is a configuration mistake that surfaces only as a confusing failure in use.

**Files affected:**
- `backend/app -> [config.py, main.py]`
- `backend/app/Auth/services -> [signup_policy.py]`
- `backend/app/_database -> [db.py]`
- `backend/app/Intake/services -> [llm.py]`
- `frontend -> [securityHeaders.ts, apiPreconnect.ts, vite.config.ts]`
- `frontend/src/services -> [apiClient.ts, apiBase.ts]`

**Evidence:** Application/backend/app/main.py:101 -- `DOCS_ENABLED = _truthy("ENABLE_DOCS")`, :140 `os.getenv("ALLOWED_ORIGINS", ...)`, :58 `RUN_SCHEMA_ON_STARTUP`, :30 `LOG_LEVEL`; signup_policy.py:22 `os.getenv("ALLOWED_SIGNUP_EMAILS", "")`; db.py:48 `DATABASE_URL`. Only `Settings` has `env_file=ENV_FILE`, yet Application/.env.example sets `ALLOWED_ORIGINS` and `ENABLE_DOCS=1`, and dev.run.sh:188 starts uvicorn without `--env-file`. Also: Application/backend/app/Intake/services/llm.py -- `configured()` returns `bool(settings.LLM_PROVIDER and settings.LLM_MODEL_EXTRACT and settings.LLM_API_KEY)` without checking `LLM_PROVIDER in PROVIDERS`, which only `extract_document` does (raising NotConfigured, a 503); `http_post` calls `response.json()` outside the try, so a non-JSON 2xx body escapes as a ValueError the route reports as a 400 with the decoder's message. Also: Application/frontend/securityHeaders.ts:119 -- `const base = (apiBaseUrl ?? DEFAULT_API_BASE_URL).trim();` and src/services/apiClient.ts:16 -- `(import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).trim()`; the only build warning fires when `originOf(base) === null`, which `http://localhost:8000` never is.

**Suggested fix:** Move every setting into `Settings` (so all are read from the environment and the one `.env` and validated together at startup), validate `LLM_PROVIDER` against the known providers there, and make the Vite config fail a production build when `VITE_API_BASE_URL` is unset or local.

**What the fix could break:** Values that were silently ignored will start taking effect (an `ALLOWED_ORIGINS` or `ENABLE_DOCS` line in a local `.env`); a production deploy with a bad value would now fail at startup instead of at use, which is the point but needs a check of Cloud Run's variables first.

### M8. Production problems are hard to see: frontend crashes stay in the visitor's console, the API has no exception handler, request id or structured log fields, and audit lines go to two differently named loggers with no record of each purged account.

*Reliability · verified*

With an invite-only group the owner learns about most failures from a message, so the logs have to answer 'what happened to this person at that time'. Today an unhandled backend error is logged only by uvicorn's default traceback, with no request id, user id or route to tie it to a report; plain-text lines give Cloud Logging nothing to filter on beyond the text. Frontend render errors and unhandled promise rejections are written only to the visitor's own console, so a broken page in production is invisible until someone complains. Account purges, the one irreversible automated action, log only a count, and purge deferrals and failures go to a logger named `audit` while every other audit line uses `app.audit`, so a filter on one misses the other.

**Files affected:**
- `frontend/src/shared/components -> [ErrorBoundary.tsx]`
- `backend/app/Users/services -> [user_service.py]`
- `backend/app -> [main.py]`

**Evidence:** Application/frontend/src/shared/components/ErrorBoundary.tsx:68 -- `console.error("Unhandled render error:", error, info.componentStack);` is the only record; there is no `window.onerror`/`unhandledrejection` handler and no client-error endpoint anywhere in frontend/src or backend/app. Also: Application/backend/app/main.py -- the lifespan logs only `logging.getLogger("audit").info("purged %s expired account(s)", purged)`; user_service.purge_expired_users logs deferrals and failures to `logging.getLogger("audit")` and successes not at all, while shared/audit.py writes to `app.audit` and routes/users.py audits the deletion request and restore with `audit.deletion("user", ...)`. Also: Application/backend/app/main.py:29 -- `logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format=...)` is the whole logging setup; no `add_middleware` other than CORS and no `exception_handler` is registered. Loggers in use: `app.audit`, `app.health`, `app.push`, `app.rls`, `app.schema`, `app.signup`, `app.usage`, and `audit` three times.

**Suggested fix:** Add a small middleware that assigns a request id, logs method, route, status, duration and user id per request, and returns the id in a header; register an exception handler that logs the traceback with that id; emit JSON log lines (or at least a severity field) for Cloud Logging. Add a `window.onerror`/`unhandledrejection` hook and an error-boundary report to a tiny authenticated endpoint (rate-limited, no payloads beyond message and stack). Log each purged account id to `app.audit` and rename the stray `audit` loggers.

**What the fix could break:** More log volume (small at this scale); the client-error endpoint must not become a way to fill the logs, so cap it per user. Never log request bodies, which carry grades and money.

### M9. Deleting a cash tip's ledger row from the ledger fails on the shift_records foreign key and returns 500.

*Reliability · verified*

A filed cash tip is an ordinary-looking income row on the account page, and deleting it there is the obvious way to remove a tip recorded by mistake. The delete fails at flush because the shift record still points at the row, and the client gets a 500 with no explanation. The two other owners of ledger rows (tuition and paycheques) were given the cascade the design notes require in both directions; cash tips were not. If the delete did succeed (were enforcement ever off), the shift would keep claiming tip_in_ledger with no row behind it.

**Files affected:**
- `backend/app/Finances/services -> [transaction_service.py]`
- `backend/app/Jobs/services -> [job_service.py]`
- `backend/app/_database -> [models.py]`

**Evidence:** _database/models.py:1352 -- `tip_transaction_id = Column(Uuid, ForeignKey("transactions.id"), nullable=True)` with no ondelete; delete_transaction (Finances/services/transaction_service.py) clears tuition payments, paycheques and sinking contributions that own a row, but nothing touches ShiftRecordModel.tip_transaction_id. Reproduced on the SQLite test fixtures: confirm a shift with a $20 cash tip filed to the cash-tip account, then delete_transaction on that income row -> sqlite3.IntegrityError FOREIGN KEY constraint failed.

**Suggested fix:** In delete_transaction, find shift records pointing at the row (or at any row of its group, for older split tips) and either refuse with a 400 that says to edit the shift's tip, or clear the record's tip and tip_transaction_id in the same commit. Add a test next to the tuition and paycheque cascade tests.

**What the fix could break:** Clearing the tip on the shift changes the Jobs page's tip figures and the tax packet's cash tips for that date, which is the intended effect but should be stated in the confirm dialog.

### M10. Term blackouts hide one-off course events too, so a midterm, deadline or grade block dated inside a reading break disappears from the calendar and every figure built on it.

*Integrity · verified*

A blackout exists to cancel class meetings over a reading break or a holiday. Because the filter is 'belongs to a course' rather than 'is a repeating class', it also removes any one-off event of that course in the range: a midterm or final the student added by hand, a lab deadline, and every block a dated grade produced with schedule_as='event'. Deadlines due in reading week are common. The event vanishes from the calendar, from the crunch strip's exam count, from free-time blocking and from the shift-versus-exam conflict check, with nothing on screen to say why, which is how a student misses an exam.

**Files affected:**
- `backend/app/Calendar/services -> [event_service.py, load_service.py]`
- `backend/app/Jobs/services -> [conflict_service.py]`

**Evidence:** Calendar/services/event_service.py:398-405 -- list_occurrences merges the blackout dates into `skipped` for any event with `event.course_id is not None`, with no check that the event repeats or is a class kind; the design notes (Ideas/design/calendar.md, 'subtracted from every recurring event that belongs to a course') and the TermBlackoutModel docstring both say recurring. tests/test_blackouts.py covers classes, personal events and payments, not one-off course events. Reproduced on the SQLite fixtures: a one-off 'CPSC 221 midterm' (kind midterm, course set) on 2026-10-14 is listed for 12-18 Oct until a blackout covering 12-16 Oct is added, after which the window returns nothing.

**Suggested fix:** Apply blackouts only to occurrences of a repeating rule in CLASS_KINDS (or, at least, only when `rule.repeats`), matching the documented scope, and add a test with a one-off course exam inside a blackout.

**What the fix could break:** A course's one-off events inside a blackout will reappear; if a student relied on a blackout to hide a one-off they meant to cancel, it comes back (they can delete it). No data changes.

### M11. Row policies check only a row's own owner column, so a foreign key to another user's row passes WITH CHECK.

*Security · plausible*

Isolation is meant to be enforced twice, by the service filter and by the policy. For references between a user's own rows it is enforced once: if a service forgets to check that a submitted account, category, course or job id is the caller's (the bug audit #7 found for categories), the row policy accepts a row owned by the caller that points at another user's row, because the foreign key is checked by the database without row security. The visible results are cross-user links that neither side can see, and a victim who later cannot delete their own category or account because a hidden foreign key in someone else's row blocks it, with a 500 they cannot diagnose. The isolation suite tests the routes that exist today, not this property of the database.

**Files affected:** `backend/app/_database -> [rls.py, models.py]`

**Evidence:** Application/backend/app/_database/rls.py:833 -- `CREATE POLICY ... FOR ALL TO {APP_ROLE} USING ({predicate}) WITH CHECK ({predicate})`, where `owner_predicate` for a per-user table is only `user_id = account_current_user()`. Secondary keys such as transactions.account_id / category_id / course_id, events.course_id / job_id, tasks.course_id, budget_targets.account_id and account_category_limits.category_id are never examined, and Postgres foreign-key checks bypass row security.

**Suggested fix:** Make cross-tenant references impossible in the schema: add a unique (user_id, id) index on each owned parent and turn each secondary foreign key into a composite one, FOREIGN KEY (user_id, account_id) REFERENCES accounts (user_id, id). Alternatively extend the generated WITH CHECK to require every non-null owned foreign key to resolve to a row with the same user_id.

**What the fix could break:** A schema migration on most per-user tables, which must first confirm no existing row already crosses users (the census says none do); composite keys on SQLite need table rebuilds; WITH CHECK subqueries add a lookup to every insert and update.

### M12. Each definer function must be listed by hand in four places, and a missed REVOKE FROM PUBLIC is not caught by the lockdown loop.

*Maintainability · plausible*

Adding a sharing feature means touching four lists in step. Forgetting the GRANT breaks the feature loudly, but forgetting the REVOKE FROM PUBLIC fails silently: the generic loop only strips named roles, so the new SECURITY DEFINER function, which runs with the owner's rights and crosses users, stays executable by every role that can connect, and the outsider test only exercises the functions already written into its own list. With contributors about to join and sharing features still being added, this is the most likely way a cross-user door is left open.

**Files affected:**
- `backend/app/_database -> [rls.py]`
- `backend/tests -> [test_rls.py]`

**Evidence:** Application/backend/app/_database/rls.py:50 -- `FUNCTIONS = (...)`; lines 595-626 repeat each signature as `REVOKE ALL ON FUNCTION ... FROM PUBLIC`; lines 883-915 repeat it again as `GRANT EXECUTE ...`; tests/test_rls.py keeps its own `DEFINER_SIGNATURES` and call list. The loop at 632 joins `pg_roles g ON g.oid = a.grantee`, which never matches the PUBLIC grantee (oid 0), and hard-codes `g.rolname <> 'account_app'` instead of `APP_ROLE`.

**Suggested fix:** Keep one tuple of full signatures and generate the REVOKE FROM PUBLIC and GRANT EXECUTE statements (and the `FUNCTIONS` name list) from it; make the outsider test enumerate `pg_proc` for every `prosecdef` function named `account_%` rather than keep its own list; use `APP_ROLE` in the loop.

**What the fix could break:** Generated statements must match the existing signatures exactly, including argument types, or the REVOKE/GRANT fails at install; the change is otherwise behaviour-neutral and verifiable by diffing `render_sql()` before and after.

### M13. A model answer that breaks the "lenient" extract schema's limits fails the parse after the paid model call, uncounted by the daily cap, with a raw Pydantic dump as the message.

*Reliability · plausible*

The schema promises that whatever the model gets wrong the student fixes on the check screen, but a 301-character note, a 110% weight, 80 participation days or a long multi-instructor professor field makes the whole parse fail. Because validation runs after the provider has been paid and before the parse row exists, a syllabus that reliably produces such an answer can be retried without limit, each attempt costing money and none counting toward LLM_PARSES_PER_DAY, which exists exactly to stop a retry loop costing much. The student meanwhile sees Pydantic's internal error text (field paths, input values, an errors.pydantic.dev link).

**Files affected:**
- `backend/app/Intake/schemas -> [syllabus.py]`
- `backend/app/Intake/services -> [syllabus_service.py]`
- `backend/app/api/routes -> [intake.py]`

**Evidence:** Application/backend/app/Intake/schemas/syllabus.py -- `ExtractedRule._trim` cuts to `value[:500]` but `note` has `max_length=300`; `ExtractedAssessment.name` max 100, `weight` le=100, `count` le=60 and `SyllabusExtract.course_code` max 20 are hard limits. syllabus_service.parse calls `llm.extract_document(...)` and then `SyllabusExtract.model_validate(_clean(raw))` before the SyllabusParseModel row the cap counts is written; routes/intake.py maps any ValueError (ValidationError included) to `HTTPException(400, detail=str(exc))`.

**Suggested fix:** Make the extract models clamp rather than refuse: truncate strings to their limits in before-validators (note to 300), clamp weight and count, drop unreadable assessments; record the parse row (or count the attempt) before calling the provider so failures are capped; and map a validation failure to a 502 with a plain message.

**What the fix could break:** Clamped values may hide a genuinely odd syllabus, though the check screen and warnings still show them; counting failed attempts toward the cap means a student can hit the limit on provider errors.

### M14. Course codes are parsed by five separate regular expressions with different rules.

*Maintainability · plausible*

The same student-typed code is read one way by quick capture and the omnibox, another by the catalogue link, the term-review key, prerequisites and the degree audit. "CPSC-210" resolves in quick capture but is not a code to a prerequisite rule; "MATH 1000" resolves as a course but never matches a catalogue row; a letter-suffixed code counts as one course in a prerequisite check and as its base course in the audit. Each rule was tuned locally, the design notes ask for one engine per idea, and the docstrings already show two of them meant to stay in step by hand.

**Files affected:**
- `backend/app/Grades/services -> [course_lookup.py, catalogue_service.py]`
- `backend/app/Grades/utils -> [prerequisites.py]`
- `backend/app/Grades/schemas -> [degree.py]`
- `backend/app/shared -> [tokenizer.py]`

**Evidence:** Application/backend/app/Grades/services/course_lookup.py -- `CODE_PARTS = re.compile(r"^([A-Za-z_]+)\s*(\d+[A-Za-z]?)$")` (any letters, any digit count); catalogue_service.CODE `^([A-Za-z]{2,5})(?:_([A-Za-z]))?\s*(\d{3}[A-Za-z]?)$` (keeps the suffix as a campus); prerequisites.CODE keeps a letter suffix in the number while `code_key` drops it; degree.CODE drops it in `parse_code`; tokenizer.COURSE_PATTERN also accepts hyphens (`[\s\-_]*`). prerequisites.code_key's docstring says it must read codes "the same" as degree.parse_code.

**Suggested fix:** Put one course-code parser in Grades/utils (returning subject, optional campus, number, optional suffix) and derive each consumer's key from it, with a table-driven test of the spellings each must accept or refuse.

**What the fix could break:** Unifying changes which strings each feature accepts: some codes that resolve today may stop resolving (or start) in one feature, and the catalogue/term-review keys of existing rows could change, so stored `term_reviews.course_key` values should be checked.

### M15. The add and edit forms for courses and for grades are each written twice: `AddCourseForm`/`EditCourseForm` differ only in ids, a notice and Reset, and `AddGradeForm`/`EditGradeForm` only in the dropped toggle.

*Maintainability · plausible*

Every field (code, name, semester, year, credits, professor, section, final grade, target, required, dates) and its validation attributes is written twice. The project already extracted `CategoryWeights` and `CourseFlags` precisely because the two forms 'differed only in class names' and could disagree, but stopped there; a new course field, a changed limit (the backend caps section at 20 and credits at 0.5-10) or the final-grade null fix has to be made in both or the add and edit paths silently diverge, which is how `required`-on-a-div and the placeholder-label sweep each had to be fixed twice.

**Files affected:** `frontend/src/features/grades/components -> [AddCourseForm.tsx, EditCourseForm.tsx, AddGradeForm.tsx, EditGradeForm.tsx]`

**Evidence:** Application/frontend/src/features/grades/components/EditCourseForm.tsx:36 -- `{/* Paired into rows, matching AddCourseForm. */}`; a diff of the two files with `add`/`edit` normalised shows only element ids, the CategoryWeights class names, the `notice` slot, the Reset button and the submit label differ. AddGradeForm.tsx and EditGradeForm.tsx repeat the same name, score, max-score, BonusNote and ScheduleChoice markup (including the identical four-field `onChange` comment), EditGradeForm adding only the `excluded` checkbox.

**Suggested fix:** Merge each pair into one form component (`CourseForm` with `idPrefix`, optional `notice`, optional `onReset`, `submitLabel`; `GradeForm` with an optional dropped toggle), keeping the Add and Edit modals as callers.

**What the fix could break:** Element ids are used by tests and labels; keep the existing ids via the prefix. Visual styling differs slightly (`edit_category_grid` classes), so the class names need to be passed through or unified with CSS checks.

### M16. The headline cumulative and semester averages report 0% when nothing has been recorded yet, so every new student's grades page and dashboard read as failing.

*Integrity · verified*

The project's settled rule is that 'not marked yet' is not zero: course averages (#31), year summaries and the trend chart's cumulative points are all nullable, and `calculate_cgpa` returns None in exactly the case where `calculate_cumulative_average` returns 0.0. The headline figures were left on the old convention. A first-year student has no final grades until their first term ends, so from sign-up until December the grades page says 'Cumulative Average 0%', and the semester average says 0% until something is marked. At an invite-only launch every user is in that state, and it is the first number they see. Rated medium in review rather than high: the figure is a misleading empty state for a student with nothing recorded yet, not a wrong number computed from real data.

**Files affected:**
- `backend/app/Grades/services -> [dash_services.py]`
- `backend/app/Grades/schemas -> [dashboard.py]`
- `frontend/src/features/grades -> [types.ts]`
- `frontend/src/features/grades/components -> [SemesterSummary.tsx]`
- `frontend/src/pages -> [Dashboard.tsx]`

**Evidence:** Application/backend/app/Grades/services/dash_services.py:222 -- `calculate_cumulative_average` returns `0.0` when `total_credits == 0`, and `plain_average` (line 206) returns `0.0` when no current course has a result; dashboard.py:115 declares `cumulative_average: float = 0.0`. SemesterSummary.tsx:14/19 render `{summary.semester_average}%` and `{summary.cumulative_average}%`; Dashboard.tsx:80/83/140 show the same figures.

**Suggested fix:** Make `cumulative_average` and `semester_average` `float | None` in `UserGradeDashboard` (returning None when nothing counts, as `calculate_cgpa` does), type them `number | null` on the frontend, and render a dash or 'no finals yet' in SemesterSummary and the dashboard.

**What the fix could break:** Any consumer that does arithmetic on these figures (the dashboard tiles, tests asserting 0.0) must handle null; the API contract changes for both fields.

### M17. Any background refetch anywhere in the app makes the course page swap itself for 'Loading...', unmounting open dialogs and discarding whatever the student had typed in them.

*Reliability · plausible*

The refresh notice is global, not per resource, and this page treats every reload as a first load. When a background refetch of anything returns a different answer while the student is on a course page, the page blanks to 'Loading...', the scroll position is lost, and every open dialog (Edit Course, Add/Edit Grade, Add Several, Class Times, the syllabus check screen) unmounts; when the page returns, the dialogs remount from their initial state, so a half-typed bulk entry or edit is gone. It is most likely just after arriving from a cached visit, which is exactly when someone opens a dialog to add the mark they came for. Other modals reset their forms from `[source, open]` effects for the same reason (EditGradeModal, CourseLinksModal, EditCourseModal, RepeatingModal, EventModal), so a reload that replaces the source object also wipes edits there.

**Files affected:**
- `frontend/src/pages/grades -> [CourseDetailPage.tsx]`
- `frontend/src/shared/hooks -> [useApiRefresh.ts]`
- `frontend/src/services -> [apiCache.ts]`

**Evidence:** Application/frontend/src/pages/grades/CourseDetailPage.tsx:108 -- the load effect depends on `refreshed` from `useApiRefreshCount()` and calls `setLoading(true)`; line 210 -- `if (loading) return <div className="p-4">Loading...</div>;` returns before any dialog is rendered. apiCache.ts `notify` fires every listener when any cached GET's background refetch comes back changed.

**Suggested fix:** Show 'Loading...' only before the first course arrives (keep rendering the existing course during a reload, as useTasks' `stale` flag does), and seed modal forms once per opening (on the `open` transition or the source's id), not on every new object identity.

**What the fix could break:** Dialogs would then keep the values from when they opened even if the course changed in the background, which is the expected behaviour for an edit in progress; a save could overwrite a concurrent change, as it already can.

### M18. 'Stop' on a repeating task deletes every unticked occurrence, overdue and edited ones included, but its confirmation only says the ticked-off ones stay.

*Integrity · plausible*

Materialising writes occurrences up to 60 days ahead and keeps overdue ones, and students edit occurrences individually (notes, a moved date, a snooze, a running timer). Stopping the repeat silently removes all of those along with the future ones; the confirmation describes only what survives, so a student who expects their current overdue reading (with notes) to remain loses it with no undo. The pause control in the edit dialog ('Active: uncheck to stop new ones without losing what is done') is the non-destructive option, but the Stop dialog does not mention it. The backend's bulk delete also bypasses ORM cascades, so any child rows of those tasks (snooze history, for instance) depend on database-level ON DELETE rules, which is worth confirming.

**Files affected:**
- `frontend/src/pages -> [TasksPage.tsx]`
- `frontend/src/features/tasks -> [api.ts]`
- `backend/app/Tasks/services -> [recurring_task_service.py]`

**Evidence:** Application/frontend/src/pages/TasksPage.tsx:237 -- `deleteRepeating(user.id, rule.id)` uses the default `dropPending = true`; recurring_task_service.py:414 then bulk-deletes `TaskModel.recurring_id == rule.id, TaskModel.done.is_(False)` with `synchronize_session=False`. The dialog text (line 463) reads: '... will stop repeating and the rule will be deleted. Occurrences you have already ticked off stay where they are'.

**Suggested fix:** State the cascade in the dialog ('N open occurrences, including M overdue, will be deleted') and offer 'Keep open ones' (send `dropPending=false`) or point to pausing; check that task children are removed by FK cascade or delete them explicitly.

**What the fix could break:** None for stored data; the dialog gains a count (one extra read or a field on the rule) and a choice.

### M19. A non-JSON error body (a gateway 502/503/504 page) makes every API call fail with a JSON parser message and loses the HTTP status.

*Reliability · plausible*

Errors that do not come from FastAPI -- a Cloud Run cold-start timeout, a 503 while a revision rolls out, a Cloudflare or load-balancer error page -- arrive as HTML or plain text. `JSON.parse` then throws a SyntaxError such as "Unexpected token '<'", which every page shows verbatim as its error message, and the status code that would explain the failure is gone, so neither the user nor a bug report can tell an outage from a client bug. This is the most likely failure mode during a deploy or a backend incident, exactly when clear messages matter.

**Files affected:** `frontend/src/services -> [apiClient.ts]`

**Evidence:** Application/frontend/src/services/apiClient.ts:108-109 -- `const text = await response.text(); const json = text ? JSON.parse(text) : null;` runs before `if (!response.ok)`, unguarded; `getBlob` at line 159 already wraps the same parse in `try { ... } catch { json = null; }`.

**Suggested fix:** Parse the body inside try/catch (as `getBlob` does) and fall back to `response.statusText` or `Request failed with status N` when it is not JSON; consider throwing an error type that carries `status`.

**What the fix could break:** Low: only the text of error messages on non-JSON responses changes. A success response with a non-JSON body would now need an explicit decision (throw or return null).

### M20. Any failure loading the user at startup (offline, a 5xx during a deploy) discards the session token and signs the student out.

*Reliability · plausible*

The catch is meant for an expired token, but it fires for every rejection: no network on a phone, a Cloud Run cold start or 503 while a revision rolls out, a CORS misconfiguration, a non-JSON gateway page. Each of those throws away a perfectly valid token, so the student lands on the sign-in page and must sign in again (with Google or a password) for what was a transient blip. With sessionStorage-scoped tokens this also loses the session for that tab entirely. It will hit real users on flaky mobile connections and during every deploy window.

**Files affected:** `frontend/src/app/auth -> [AuthContext.tsx, ProtectedRoute.tsx]`

**Evidence:** Application/frontend/src/app/auth/AuthContext.tsx:42-49 -- `getCurrentUser().then(setUser).catch(() => { sessionStorage.removeItem("access_token"); setToken(null); setUser(null); })`, with the comment `// token invalid/expired — clear everything`; a real 401 never reaches this catch as a recoverable case because apiClient's `send` already removes the token and navigates to /login.

**Suggested fix:** Only treat an authentication failure as sign-out (apiClient already handles 401); for other errors keep the token and expose an error state with a retry, which ProtectedRoute renders instead of redirecting. This needs the client error to carry a status.

**What the fix could break:** ProtectedRoute currently treats `isAuthenticated === false` as 'go to /login'; it would need a third state so a failed load does not loop or spin forever.

### M21. Every frontend API type is hand-copied from a Pydantic schema, with no generation or contract test, and the copies have already drifted.

*Maintainability · plausible*

The backend is the source of truth for about 230 routes' shapes, and FastAPI already publishes them as OpenAPI, but the client re-declares each one by hand and nothing checks that the two agree. A renamed or newly nullable field compiles fine on the frontend and fails at runtime, typically as `undefined` rendered as blank or `NaN` money. Loose `string` where the server has an enum also lets an impossible value through the type checker. As contributors join, the backend and frontend will change in separate PRs and this is where they will silently disagree.

**Files affected:**
- `frontend/src/features/budget -> [types.ts]`
- `frontend/src/features/jobs -> [types.ts]`
- `frontend/src/features/jobs/applications -> [types.ts]`
- `frontend/src/features/omnibox -> [types.ts]`
- `frontend/src/features/partners -> [types.ts]`
- `frontend/src/services -> [currentUserClient.ts]`

**Evidence:** Application/frontend/src/features/budget/types.ts:410 -- `/** Mirrors app/Finances/schemas/safe.py. */` (likewise jobs/types.ts:159 and 225, omnibox/types.ts:1, applications/types.ts:1); drift: `CurrentUser.preferences` (currentUserClient.ts) lacks seven `UserPreferences` fields, `JobEarnings.kind: string` and `ShiftConflict.exam_kind: string` (jobs/types.ts:232, 341) are enums on the server, and `ShiftMeeting.days: string[]` (jobs/types.ts:80) is `Weekday[]` everywhere else.

**Suggested fix:** Generate types from the API's OpenAPI document (for example openapi-typescript in a `npm run gen:api` step, checked in CI against the running schema), then re-export or alias them from the feature `types.ts` files; at minimum add a CI test that diffs field names between the OpenAPI schema and the hand-written interfaces.

**What the fix could break:** Generated names and nullability will differ from the hand-written ones (optional vs nullable, enums as unions), so adoption touches many imports; do it module by module. Fields the server sends but the client never declared become visible and may expose existing mismatches.

### M22. An account's month lists at most its newest 100 transactions, silently, while the totals beside it count every row.

*Integrity · plausible*

The account page reads its figures (totals, daily flow, categories) from `accounts/{id}/activity`, which covers every row, and its list from `/transactions`, which returns only the newest 100 in the window. A busy spending account, especially after a CSV import of a bank statement, can pass 100 rows in a month; the oldest rows then vanish from the list with nothing on screen saying so, while the totals above still include them. A student reconciling against their bank will find transactions 'missing' and cannot reach them to edit or delete.

**Files affected:**
- `frontend/src/features/budget -> [api.ts]`
- `frontend/src/features/budget/hooks -> [useAccountActivity.ts]`
- `frontend/src/features/budget/components -> [Transactions.tsx]`
- `backend/app/api/routes -> [finances.py]`

**Evidence:** Application/backend/app/api/routes/finances.py:892 -- `limit: int = Query(100, ge=1, le=500)` on GET /transactions; frontend/src/features/budget/api.ts `fetchTransactions` never sends `limit`, and useAccountActivity.ts:49 calls `fetchTransactions(userId, { accountId, start: month, end: lastOfMonth(month) })`. Transactions.tsx has no 'showing N of M' or load-more state. The old comment on `fetchTransactions` claimed a cap of 500.

**Suggested fix:** Return a total count (or a `has_more` flag) with the page and show 'showing 100 of N' with a load-more or paging control; or pass an explicit `limit` up to the server's 500 and tell the user when it is hit.

**What the fix could break:** Raising the limit increases payload size and render cost for large months; paging changes the hook's state shape and the delete/edit refresh logic.

### M23. The 'Remove this fund?' dialog promises the money stays where it was moved, but removing a fund deletes its transfers, which moves the money back.

*Integrity · plausible*

Balances are the sum of ledger rows, so deleting the contributions' transfers undoes them: the savings account drops by everything set aside and the spending account rises by the same. The confirmation says the opposite, so a student who removes a finished fund expecting the money to stay in savings will see their savings balance fall and safe-to-spend jump, which looks like money appearing from nowhere and invites them to spend it. The test only pins the phrase 'every transfer recorded against it', not the false sentence after it.

**Files affected:**
- `frontend/src/features/budget/components -> [SinkingFunds.tsx]`
- `backend/app/Finances/services -> [sinking_service.py]`

**Evidence:** Application/frontend/src/features/budget/components/SinkingFunds.tsx:163-165 -- message `"...and every transfer recorded against it will be removed. The money itself stays in the account it was moved to; what goes is the goal and its history."`; sinking_service.py:492-493 `for contribution in list(fund.contributions or []): clear_transfer(db, user_id, contribution.group_id)`.

**Suggested fix:** Decide which behaviour is wanted. If the money should stay, delete the fund and contributions but keep (or re-describe) the transfers; if removal should reverse it, change the message to say the set-aside money goes back to the account it came from, and point to Archive for keeping it.

**What the fix could break:** Keeping the transfers changes the documented cascade and the backend tests that pin it; changing only the text is safe.

### M24. Editing a tuition payment cannot be saved without re-picking 'Paid from', and saving then moves its ledger row to the picked account and resets its description.

*Integrity · verified*

The 'Paid from' select shows the first account (the browser's display for a value that matches no option) while the state is empty, so Save is disabled with no reason given. To save a simple fee correction the student must change the select, and whatever they pick becomes the account the tuition is recorded against: a multi-thousand-dollar row can silently move from the account that really paid it, shifting two balances, safe-to-spend and net worth splits. Any custom description on the ledger row is also replaced by the default. No test covers the edit path. Rated medium in review: the account change needs an explicit pick in a visible field; the silent part is the description reset and the risk of picking a different account than the original.

**Files affected:**
- `frontend/src/features/budget/components -> [TuitionModal.tsx]`
- `frontend/src/features/budget -> [types.ts]`
- `backend/app/Finances/schemas -> [tuition.py]`
- `backend/app/Finances/services -> [tuition_service.py]`
- `frontend/src/pages/budget -> [AccountDetailPage.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/TuitionModal.tsx:89-96 -- the edit branch loads `occurred_on`, `cost_per_credit`, `fees`, `deductions` and `credits_counted` but never calls `setAccountId` or `setDescription` (the TuitionPayment schema carries neither); the edit instance in BudgetView/AccountDetailPage starts with `accountId` "", so `disabled={submitting || blocked || !accountId}` (line 418) blocks Save; the payload sends `account_id: accountId, description: description || null`, and tuition_service.update_tuition does `transaction.account_id = data.account_id` and `transaction.description = data.description or f"Tuition {term_name(...)}"`.

**Suggested fix:** Return `account_id` and `description` with TuitionPayment (from its ledger row) and seed both in the edit branch; until then, omit them from the update payload and let the server keep the row's current values.

**What the fix could break:** Schema change on the tuition endpoint (additive); the server must accept an update without account_id if the client stops sending it.

### M25. Saving a shift pattern applies it from the job's start date, rewriting every past unconfirmed week, from an editor that never shows the current pattern.

*Integrity · plausible*

Shifts are expanded on read, so a pattern's past occurrences count as worked (assumed) hours in earnings, the cheque preview and the hours-against-classes figure. When a student's rota changes this week and they save the new pattern, the client backdates it to the day the job started: every past week now shows the new days, earned-to-date figures change, and past unconfirmed shifts on the old days vanish. Because the editor starts blank, they must also re-enter the whole pattern from memory. (That the save fails outright once any patterned shift was confirmed is backend_a's foreign-key finding on set_shift_schedule; this one is the client's effective date and editor.)

**Files affected:**
- `frontend/src/features/jobs/components -> [ShiftScheduleModal.tsx]`
- `backend/app/Jobs/services -> [job_service.py]`

**Evidence:** Application/frontend/src/features/jobs/components/ShiftScheduleModal.tsx:110-114 -- `setShiftSchedule(user.id, job.id, { meetings: filled, starts_on: job.started_on, ends_on: job.ended_on })`, with `meetings` initialised to `[blankMeeting()]` on every open (no days, 09:00-17:00) rather than the job's existing blocks; job_service.set_shift_schedule deletes all the job's repeating shift events and writes new weekly events over that window.

**Suggested fix:** Load the current pattern into the editor, and save a new pattern from a chosen effective date (default today): end the old events the day before (set their `until`) instead of deleting them, so history and confirmed records stay attached.

**What the fix could break:** Ending rather than deleting old events changes how many event rows a job accumulates and how the calendar expands them; backend tests around replace-the-pattern semantics would need updating.

### M26. The omnibox can file a line before its module badge has caught up, so the 'shown before you commit' safeguard fails on quick typing and Enter.

*Integrity · plausible*

The component's own doc says the badge naming the destination module before commit 'is the whole reason this is safe': a mark filed as an expense is a mistake found weeks later. But Enter within the 200 ms debounce plus the preview round trip files whatever the server reads from the new text while the badge still shows the previous line's module, or no badge at all. The `can_create === false` guard is also stale, so a line the server would refuse can be submitted (it fails server-side) and a fixable one can be blocked. Fast typists using Ctrl+K and Enter are exactly the users this box is for.

**Files affected:** `frontend/src/features/omnibox -> [Omnibox.tsx]`

**Evidence:** Application/frontend/src/features/omnibox/Omnibox.tsx:34 -- `const debounced = useDebounce(text, 200);` drives `previewLine`, but `handleSubmit` (line 76) checks only `if (!user || text.trim() === "" || preview?.can_create === false) return;` and then files the live `text` with `fileLine(user.id, text)`; nothing compares the preview's `text` with what is being filed, and a null preview (still loading, or failed) does not block filing.

**Suggested fix:** Only enable File when `preview?.text === text.trim()` (the server echoes the text) and the preview allows it; on Enter with a stale or missing preview, fetch the preview first and show it, or send the previewed kind with the file request and have the server refuse a mismatch.

**What the fix could break:** A short delay before Enter works after typing; tests that type and submit immediately would need to wait for the preview.

### M27. The tests are strong on single operations but miss the sequences where this audit's worst bugs live, the Google sign-in route is never called, several guards are regular expressions over source text, and nothing measures coverage or drives the app end to end.

*Reliability · verified*

3,228 backend cases and 792 frontend cases cover a great deal, and the isolation, non-interference and RLS walks are unusually good. But the defects this audit found cluster where single-operation tests cannot see them: an edit followed by the catch-up, a PATCH followed by a read, a delete when dependent rows exist, a save followed by a panel refresh. The one route that admits new users by Google is skipped by every walk, which is how its uninvited-user 500 went unnoticed. Several guards (delete confirmations, page widths, shared styles, the TasksPage loading wiring) are regexes over source text: they miss shapes they were not written for (eleven destructive functions are invisible to the confirmation sweep) and a comment can satisfy or break them, which this documentation pass had to work around. Without coverage numbers or a single end-to-end flow, nobody can see which paths are untested, and a contributor changing a hook has no test that signs in and clicks through.

**Files affected:**
- `backend/tests -> [test_isolation.py]`
- `frontend/src/features -> [deleteConfirmations.test.ts]`
- `.github/workflows -> [ci.yml]`
- `frontend -> [package.json]`

**Evidence:** Application/backend/tests/test_isolation.py:94 -- `("POST", "/api/auth/google"): "verifies a Google credential over the network; "` skips the route, and no other test calls it (the service is tested in test_signup_policy.py). Application/frontend/src/features/deleteConfirmations.test.ts:71 -- `readFileSync(f, "utf8").match(/export async function (delete|clear)[A-Za-z]+/g)`; 11 frontend test files read source or CSS with `readFileSync`. .github/workflows/ci.yml has no coverage step; Application/frontend/package.json has no browser test runner. The critical and high backend findings were each reproduced in review with a four-to-ten-line test the suite does not have (edit a rule then catch up; PATCH then list; confirm a shift then re-save the pattern; delete a deposit allocation).

**Suggested fix:** Add sequence tests per write path (edit-then-catch-up, PATCH-then-list, delete-with-dependents) alongside each fix in this audit; test `/auth/google` with a stubbed verifier; publish a coverage report from CI (reporting, not gating, to match the CI policy); add one Playwright smoke run (sign in with a wrong then right password, add a course and a grade, record a spend) against a local build; move the source-text guards onto the TypeScript compiler API or runtime checks where practical.

**What the fix could break:** More CI time (minutes); browser tests are slower and can be flaky, so keep the smoke run small and non-blocking at first.

### M28. A new contributor has no current entry point: the root README tells readers to trust Ideas/ over itself and still gives 23 tables, 904 tests and a backend/.env that nothing reads, while the conventions live in about 11,800 lines of narrative notes with no CONTRIBUTING guide or PR checklist.

*Contributor · verified*

The owner's notes are unusually thorough about why things are the way they are, and that is valuable. But they are written as a history, and the rules a contributor must not break are spread through it: a first pull request will break one of them (a table with no row-security kind, a literal route below its catch-all, a mutated JSON column) because nothing short of reading thousands of lines says so. The root README is the page GitHub shows first, and it is knowingly out of date, including a setup step that silently does nothing. Contributors joining at release time will meet all of this at once.

**Files affected:**
- `. -> [README.md]`
- `backend -> [.env.example]`
- `backend/app -> [config.py]`
- `Ideas/design -> [README.md]`

**Evidence:** README.md:15 -- 'tables and 904 backend tests' (the suite now has 3,228 cases over 53 models); README.md:27 -- 'Sections further down still describe the app as it was before any of that shipped'; README.md:363 -- tells contributors to create `Application/backend/.env`, while Application/backend/.env.example says 'There is no backend/.env any more' and Application/backend/app/config.py:30 reads only `ENV_FILE = APPLICATION_DIR / ".env"`. `wc -l Ideas/*.md Ideas/design/*.md` is 11,838 lines; the rules a contributor must follow (row-security kind per table, route order, JSON columns reassigned whole, `money()`/`user_today()`, cache rules, lazy routes) sit in prose in Ideas/design/README.md. The repository has no CONTRIBUTING.md and .github holds only workflows.

**Suggested fix:** Replace the root README with a short current page (what the app is, setup in a handful of commands, how to run both test suites and the Postgres job locally, where decisions live); move the contributor rules into a CONTRIBUTING.md checklist and a pull-request template (new table: kind in rls.py and the three walks; new route: literal paths first, isolation walk; JSON columns; money and today helpers; data hooks use useApiRefresh); keep Ideas/ as the decision record, linked from both.

**What the fix could break:** Documentation only. The checklist must stay short and current or it repeats the README's problem; link to the design notes for the reasons rather than copying them.

---

## Low

### L1. Invite-link handling (token minting, SHA-256 hashing, one live link, cancel, remove member) is copied across four services that must stay in step with the definer functions.

*Maintainability · verified*

The token is the credential that lets someone into another person's task, event, team or partnership, and the rule 'store only its SHA-256, 24 random bytes, seven days, one live link' lives in four places. A change to any part (a pepper on the hash, a longer token, a shorter expiry, rate-limiting accepts) has to be made four times and in the SQL definer functions that compare the hashes; missing one silently breaks that feature's links or leaves it weaker than the others. It is also four times the test surface for a security-relevant path.

**Files affected:**
- `backend/app/Calendar/services -> [event_sharing_service.py]`
- `backend/app/Tasks/services -> [task_sharing_service.py]`
- `backend/app/Partners/services -> [partner_service.py]`
- `backend/app/Teams/services -> [team_service.py]`

**Evidence:** `def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()` appears at Tasks/services/task_sharing_service.py:30, Calendar/services/event_sharing_service.py:26, Partners/services/partner_service.py:35 and Teams/services/team_service.py:24; task_sharing_service and event_sharing_service also carry line-for-line copies of NotShareable, _live_links, new_link (`secrets.token_urlsafe(24)`, INVITE_DAYS expiry, revoke the old link), cancel_link and remove_member, differing only in the model class. Also: Application/backend/app/Teams/services/team_service.py -- `def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()` and `token = secrets.token_urlsafe(24)`; the same function and call appear in partner_service.py, task_sharing_service.py and event_sharing_service.py, each with its own "revoke the live link, mint a new one" loop.

**Suggested fix:** Move token creation and hashing into one shared helper (for example app/shared/invites.py) and, for tasks and events, one small generic for the owner-side link operations parameterised by the invite and member models.

**What the fix could break:** Low; behaviour is identical today. Any change to hashing must be made in rls.py's definer SQL at the same time, or existing links stop working.

### L2. App-wide frontend code lives inside feature folders: `getErrorMessage` (exported from the Add Course dialog) and `DeleteConfirmModal` in grades, the `ValidationError` type the shared API client imports from grades/types, and `formatMoney` in budget.

*Maintainability · verified*

The design README puts code used by more than one area in `src/shared/`, but the app's error-message helper, its one destructive-action dialog, the API error shape and its money formatter each live in a feature folder: 24 files outside grades import `DeleteConfirmModal` or `getErrorMessage`, `services/apiClient.ts` (the layer every feature builds on) imports from `features/grades/types` with a leftover 'adjust path' note, and seven files outside budget import `budget/money`. Every money, jobs and calendar dialog therefore depends on the grades components folder, which also creates an import cycle (AddCourseModal, PrerequisiteWarning, PrerequisitesPanel all reach each other, found while ordering files for this pass); reworking AddCourseModal can break eight budget modals, and a contributor looking in `shared/` for the confirm dialog, the error helper or the money formatter will not find them and may write another. Meanwhile 53 other sites inline their own error message.

**Files affected:**
- `frontend/src/features/grades/components -> [AddCourseModal.tsx, DeleteConfirmModal.tsx, CourseCost.tsx]`
- `frontend/src/features/budget/components -> [AddMoneyModal.tsx, CategoriesModal.tsx, AccountImports.tsx, BudgetView.tsx]`
- `frontend/src/features/calender/components -> [BlackoutsModal.tsx]`
- `frontend/src/pages/grades -> [CourseDetailPage.tsx]`
- `frontend/src/features/tasks/components -> [ReminderModal.tsx]`
- `frontend/src/features/jobs/components -> [JobModal.tsx, PayCheckPanel.tsx, JobCard.tsx, Earnings.tsx, TaxPacketPanel.tsx, PaychequeList.tsx, PaychequeModal.tsx]`
- `frontend/src/features/jobs/applications -> [ApplicationModal.tsx]`
- `frontend/src/services -> [apiClient.ts]`
- `frontend/src/features/grades -> [types.ts]`
- `frontend/src/features/budget -> [money.ts]`
- `frontend/src/features/omnibox -> [Omnibox.tsx]`
- `frontend/src/pages -> [Dashboard.tsx]`

**Evidence:** Application/frontend/src/features/grades/components/AddCourseModal.tsx:117 -- `export function getErrorMessage(apiError: unknown): string`, imported as `../../grades/components/AddCourseModal` by eight budget modals and BlackoutsModal, and as `./AddCourseModal` by eight grades files; meanwhile `err instanceof Error ? err.message : "..."` appears 53 times elsewhere. `import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal"` appears in 17 files outside grades, including BlackoutsModal.tsx:8, ReminderModal, JobModal, SinkingFunds and five pages. Also: Application/frontend/src/features/budget/components/CategoriesModal.tsx:4 -- `import { getErrorMessage } from "../../grades/components/AddCourseModal";` (a helper exported from a course dialog), and AccountImports.tsx:2 `import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";`; 24 files outside features/grades import one of the two (grep). Also: Application/frontend/src/services/apiClient.ts:1 -- `import { ValidationError } from "../features/grades/types"; // adjust path to wherever these live` Also: Application/frontend/src/features/grades/components/CourseCost.tsx:4 -- `import { formatMoney } from "../../budget/money";`; the same import appears in seven files outside features/budget (grep `budget/money`).

**Suggested fix:** Move `DeleteConfirmModal` to `shared/components/`, `getErrorMessage` and `ValidationError` to `services/` beside apiClient, and `money.ts` to `shared/utils/`; leave re-exports for a release if needed and use the helper at the inline sites.

**What the fix could break:** Import churn only; the deleteConfirmations test matches the `DeleteConfirmModal` tag, not its path. Some inline fallbacks would change to the helper's text unless it takes a fallback.

### L3. Date helpers are re-implemented privately in budget and jobs components instead of using shared/utils/dateUtils, including three different `monthLabel`s.

*Maintainability · plausible*

The shared module exists so that every date is parsed and formatted one way (local midnight, never UTC). The budget feature carries four private copies, two of them duplicated verbatim across files, each with its own parsing idiom (`T00:00:00` string parsing rather than `fromIso`). They are correct today, but a fix to one (for example pinning a display locale) will not reach the others, and the old dateUtils header even pointed readers at a `features/budget/dates.ts` that no longer exists.

**Files affected:**
- `frontend/src/shared/utils -> [dateUtils.ts]`
- `frontend/src/features/budget/components -> [YearPlan.tsx, PlanVsActual.tsx, CashFlowForecast.tsx]`
- `frontend/src/features/budget/hooks -> [useAccountActivity.ts]`
- `frontend/src/pages/budget -> [AccountDetailPage.tsx]`
- `frontend/src/features/jobs/applications -> [seasons.ts]`
- `frontend/src/features/jobs/components -> [Earnings.tsx, PaychequeModal.tsx, ShiftList.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/YearPlan.tsx:199 and PlanVsActual.tsx:122 -- identical private `monthName`/`longDate` built on `new Date(`${value}T00:00:00`).toLocaleDateString(...)`; PlanVsActual.tsx:111 `nextMonth` and useAccountActivity.ts:83 `lastOfMonth` re-implement `addMonths`/`lastOfMonth` from dateUtils.ts. Also: Application/frontend/src/features/budget/hooks/useAccountActivity.ts:81 -- a private `function lastOfMonth(month: string)` built on `new Date(year, index, 0)`, beside the exported `lastOfMonth` in shared/utils/dateUtils.ts:85; AccountDetailPage.tsx:359 has a private `monthLabel` duplicating dateUtils `monthLabel` ("September 2026"), and seasons.ts exports another `monthLabel` that returns "Sep 2026" from a YYYY-MM string. Also: private `shortDate`/`weeksFrom` in CashFlowForecast.tsx, `nextMonth`/`monthName`/`longDate` in PlanVsActual.tsx and YearPlan.tsx (each its own copy), and an identical `hours(minutes)` formatter in Earnings.tsx, PaychequeModal.tsx and ShiftList.tsx.

**Suggested fix:** Move `longDate` and a month-and-year label into `shared/utils/dateUtils.ts`, and replace the private copies with imports of `monthLabel`/`lastOfMonth`/`addMonths`.

**What the fix could break:** Output format could change slightly (`monthLabel` is long-month, the budget copies are short-month with year), so the shared helper needs a short variant; budget component tests that match exact strings would need checking.

### L4. Naive-UTC timestamps are shown as dates by slicing the string or `new Date()`, so link expiries, snooze history and import dates read a day late every evening west of Greenwich.

*Integrity · plausible*

The team convention is that 'today' is the Settings zone and dates are never derived from UTC, but these three places take the first ten characters of a UTC timestamp. For a student in Vancouver or Regina, a link made after 4-6pm says it is open until a day later than it really is in local terms, and a snooze made in the evening is listed under tomorrow's date. SnoozeModal also prints the raw YYYY-MM-DD where every other date in the app goes through `shortDate`. Small, but it is the exact off-by-one the date utilities were written to prevent, and it will be copied.

**Files affected:**
- `frontend/src/shared/components -> [SharingSection.tsx]`
- `frontend/src/features/tasks/components -> [SnoozeModal.tsx]`
- `frontend/src/features/partners -> [PartnersPanel.tsx]`
- `frontend/src/features/budget/components -> [AccountImports.tsx]`

**Evidence:** Application/frontend/src/shared/components/SharingSection.tsx:138 -- `shortDate(sharing.link.expires_at.slice(0, 10))`; SnoozeModal.tsx:129 -- `{entry.snoozed_at.slice(0, 10)}`; PartnersPanel.tsx:129 -- `shortDate(open.expires_at.slice(0, 10))`. The backend stores both as naive UTC (`expires_at=now + timedelta(days=INVITE_DAYS)` with `utc_now`; `snoozed_at` default `utc_now`), unlike `remind_at`, which is local wall time and is sliced correctly. Also: Application/frontend/src/features/budget/components/AccountImports.tsx:64 -- `new Date(entry.created_at).toLocaleDateString()` where `created_at` is naive UTC with no `Z`, which the browser parses as local time; PartnersPanel.tsx:129 `shortDate(open.expires_at.slice(0, 10))`, SharingSection.tsx:138 `sharing.link.expires_at.slice(0, 10)` and SnoozeModal.tsx:129 `entry.snoozed_at.slice(0, 10)` take the UTC calendar date.

**Suggested fix:** Add a `localDateOf(utcTimestamp, zone)` helper beside `nowIn` in shared/utils (parse as UTC, format in the Settings zone) and use it for these fields; format the snooze date with `shortDate`.

**What the fix could break:** Displayed dates shift by a day for evening events; nothing stored changes.

### L5. Failed loads render as empty states: the grades page's Attention panel says 'Nothing needs attention', and budget and partner panels vanish when their request fails.

*Reliability · plausible*

Attention is where a missing final grade or a course below target is flagged; when the dashboard request fails, the page asserts there is nothing to act on rather than saying it could not check, the same fault audit #54 fixed on the Dashboard page. Separately, because the hook has no 'stale' notion (useTasks has one), any background refresh or post-save reload swaps the whole course list for 'Loading courses...' and back, a flicker the Tasks page was specifically fixed to avoid (#59).

**Files affected:**
- `frontend/src/pages/grades -> [GradesPage.tsx]`
- `frontend/src/features/grades/hooks -> [useCourses.ts, useDashboard.ts]`
- `frontend/src/features/budget/components -> [CashFlowForecast.tsx, YearPlan.tsx, TermBudget.tsx, PlanVsActual.tsx, Subscriptions.tsx, SinkingFunds.tsx, AccountImports.tsx]`
- `frontend/src/features/partners -> [PartnersPanel.tsx]`

**Evidence:** Application/frontend/src/pages/grades/GradesPage.tsx:34 -- `const { summary, reload: reloadSummary } = useDashboard();` drops `error`; the panels then render `items={summary?.attention ?? []}` (AttentionPanel says 'Nothing needs attention.') and `years={summary?.past_years ?? []}` ('Courses from earlier terms will appear here.'). The course list is drawn only under `!loading && !error`, and useCourses sets `loading` true on every reload, including the ones `useApiRefresh` triggers. Also: Application/frontend/src/features/budget/components/CashFlowForecast.tsx:32-34 -- `.catch(() => { if (!cancelled && ticket === latestRequest.current) setForecast(null); })` followed by `if (!forecast || isEmpty(forecast)) return null;`; the same catch-to-empty pattern in YearPlan (setPlanned(null)), TermBudget (setTerm(null)), PlanVsActual (setReview(null)), Subscriptions and AccountImports (render nothing on an empty list) and SinkingFunds (shows 'Nothing reserved yet.'). PartnersPanel's `load` does `catch { setData(null); }` and the panel returns null, taking the invite button with it.

**Suggested fix:** Take `error` from `useDashboard` and show one line in the right column when it is set (leaving Attention unrendered); give `useCourses` the `stale` pattern from `useTasks` so rows already on screen stay during a reload.

**What the fix could break:** None for data; the page gains an error line and stops flickering.

### L6. The add-task form and the game form clear themselves even when the save fails, losing what was typed.

*Reliability · plausible*

Because the page swallows the failure, the form always believes the save worked and resets: the error banner appears while the title, course, date, time, priority, estimate and tags the student just entered are wiped. The quick-capture box beside it gets this right (it clears only after `captureTask` succeeds), so the two add paths on the same page behave differently on failure.

**Files affected:**
- `frontend/src/features/tasks/components -> [TaskForm.tsx]`
- `frontend/src/pages -> [TasksPage.tsx, FitnessPage.tsx]`

**Evidence:** Application/frontend/src/features/tasks/components/TaskForm.tsx:58 -- after `await onSubmit({...})`, `setForm(blankTask()); setTagText("");` run unconditionally; TasksPage's `handleAdd` wraps the create in `withBusy` (line 133), which catches the error into `actionError` and resolves normally. Also: Application/frontend/src/pages/FitnessPage.tsx:183 -- `onSubmit={(game) => act(() => recordGame(userId, teamId, game))}`, where `act` catches every error and resolves (lines 145-157); GameForm's `submit` then runs `if (!initial) { setOpponent(""); setOurs(""); setTheirs(""); }` whether or not the save worked.

**Suggested fix:** Have `onSubmit` report success (return a boolean, or rethrow from `handleAdd`) and reset the form only on success.

**What the fix could break:** None; failed saves would keep the typed values.

### L7. Calendar information is carried only by position, bar height and hover `title`: week-view blocks have no time in their accessible name and the crunch strip has no text per week.

*Accessibility · plausible*

The strip exists to show which coming week holds the exams and deadlines, but the exams/deadlines/tasks breakdown is reachable only by hovering with a mouse: `title` is not shown on touch screens and is announced inconsistently (often not at all) on list items. A screen-reader user hears a list of empty items, and a phone user, the app's main audience, cannot read any week's contents. The project's own HelpTip doc already rejects `title` as an answer for this reason.

**Files affected:** `frontend/src/features/calender/components -> [TimeInsights.tsx, WeekView.tsx, EventCard.tsx]`

**Evidence:** Application/frontend/src/features/calender/components/TimeInsights.tsx:179 -- each week is an `li` holding an empty `span className="crunchBar"` sized by `style={{ height }}`, with the counts only in `title={`Week of ${week.starts_on} — ...`}`; the only text is the legend 'N weeks · heaviest carries P'. Also: Application/frontend/src/features/calender/components/WeekView.tsx:146 -- the block button's only text is `occurrence.title` (plus the location when tall enough); its time is placed by `top` and given only in `title={[title, clockTime(start_time), location]...}`, whereas the due-task markers beside them set `aria-label={`Edit ${title}, due ${clockTime(due_time)}`}`. EventChip in EventCard.tsx likewise shows the start time visually but relies on `title` for the rest.

**Suggested fix:** Give each item visually hidden text ("Week of 14 Oct: 2 exams, 1 deadline") via an `srOnly` span or `aria-label`, and mark the current week with `aria-current`; optionally make bars focusable buttons that reveal the breakdown.

**What the fix could break:** None visible; screen-reader output gains a sentence per week.

### L8. The term budget's 'cannot measure' message blames course dates when the cause is a missing first-year anchor.

*Readability · verified*

The term budget no longer measures from courses' own dates; it measures from the term's fixed dates via the first-year anchor. The first sentence of the user-facing reason still says the cause is course dates, which sends a student to edit courses that will not help. (The four stale `#:` field comments beside it in Finances/schemas/budget.py, and the stale `accounts.kind` comment in models.py, were corrected in this review.)

**Files affected:**
- `backend/app/Finances/services -> [tuition_service.py]`
- `backend/app/Finances/schemas -> [budget.py]`

**Evidence:** Application/backend/app/Finances/services/tuition_service.py:546 -- `"No course in this term has start and end dates, so there is no term "` `"to measure. Set the year your first year began, in Settings."`, returned when `term_span` (which derives the span from the first-year anchor and the term's fixed dates, not from course dates) gives None.

**Suggested fix:** Reword the reason to name the anchor: 'This term has no dates yet: set the year your first year began, in Settings.'

**What the fix could break:** A test may assert the old wording; grep the suite before changing it.

### L9. The category and account duplicate-name checks pass the raw name to ILIKE, so `%` and `_` act as wildcards and untrimmed names slip past them.

*Integrity · plausible*

ILIKE treats `%` and `_` in the pattern as wildcards, so a category named 'Food_Drink' is refused when 'FoodXDrink' exists, and a category whose name contains `%` collides with almost anything the user already has. In the other direction, 'Groceries ' (trailing space) passes both the check and the case-sensitive unique index beside 'Groceries', giving two categories that read the same. This is the residual audit #52 recorded and closed for course search, one module over. Low impact: it needs an unusual name, and the failure is a refusal or a near-duplicate rather than lost money.

**Files affected:** `backend/app/Finances/services -> [budget_service.py, account_service.py]`

**Evidence:** Finances/services/budget_service.py:135 -- create_category: `SpendCategoryModel.name.ilike(data.name)`, and :199 the same in update_category; the name is stored unstripped (`name=data.name`, :144). The same pattern in account_service.create_account:462 (`AccountModel.name.ilike(data.name)`, stored unstripped at :471) and update_account:520.

**Suggested fix:** Strip the name in the schema, and compare with `func.lower(SpendCategoryModel.name) == name.lower()` (or escape the pattern) instead of ILIKE; consider a unique index on lower(name) per user.

**What the fix could break:** A functional unique index on lower(name) would fail to build if a user already has case-variant duplicates; check production first. Stripping changes stored names only for new writes.

### L10. Paycheque allocations are checked with the float tolerance audit #50 removed from deposits, and not checked at all when a cheque is corrected.

*Integrity · plausible*

On create, allocations a cent away from the net can pass the float tolerance, writing ledger rows that sum to a cent more or less than the cheque says it paid: the 'cent that never existed' audit #50 fixed one module over. On update there is no check at all, so a PATCH with allocations totalling anything, or naming one account twice, writes that money to the ledger while the cheque still reports the old net. Today's frontend never sends allocations (it always sends an empty list), which keeps this low, but the API is the contract and the next client or script will.

**Files affected:**
- `backend/app/Jobs/schemas -> [paycheque.py]`
- `backend/app/Jobs/services -> [paycheque_service.py]`
- `backend/app/Finances/schemas -> [deposit.py]`

**Evidence:** Jobs/schemas/paycheque.py:118 -- PaychequeCreate.validate_allocations uses `if abs(total - net) > 0.01:`, the comparison DepositCreate.validate_allocations (Finances/schemas/deposit.py:66) replaced with whole-cent equality to close audit #50. PaychequeUpdate.allocations (paycheque.py:152) has no validator, and update_paycheque passes it straight to deposit_rows, which neither sums nor de-duplicates it.

**Suggested fix:** Share one allocation validator between DepositCreate, PaychequeCreate and the update path: whole-cent equality with the net and one entry per account; in update_paycheque, validate against the net computed after the patch.

**What the fix could break:** A client sending allocations rounded differently from the server's net (for example from a stale preview) will start getting a 400. None for the current frontend.

### L11. The user-exists, owned-course and course-code lookups are copied into five services, and Finances, Jobs and Calendar import `user_exists` from the Tasks service.

*Maintainability · plausible*

The ownership check (`CourseModel.id == course_id, CourseModel.user_id == user_id`) is the app-level half of tenant isolation that audit #7 was about, and it lives in five copies that each have to keep the user filter. The cross-module imports also run against the layering rule in Ideas/design/README.md (a rule two modules share belongs in utils or shared): money and jobs code depending on the Tasks service for a one-line lookup ties unrelated modules together and invites import cycles, which is the failure that moved effective_target into Grades/utils.

**Files affected:**
- `backend/app/Tasks/services -> [task_service.py, recurring_task_service.py, reminder_service.py]`
- `backend/app/Calendar/services -> [event_service.py, blackout_service.py]`
- `backend/app/Finances/services -> [recurring_service.py, transaction_service.py, safe_service.py, sinking_service.py, subscription_service.py]`
- `backend/app/Jobs/services -> [job_service.py, paycheque_service.py]`

**Evidence:** `def user_exists` at Tasks/services/task_service.py:49, Tasks/services/recurring_task_service.py:42, Calendar/services/event_service.py:66 and Finances/services/recurring_service.py:157 (reminder_service has `owned_user`, shared/dates.py has `user_for`); `def owned_course` at task_service.py:62, recurring_task_service.py:55, reminder_service.py:152, event_service.py:79 and Finances/services/transaction_service.py:72; `def course_codes` in task_service, recurring_task_service, reminder_service and event_service. safe_service, sinking_service, subscription_service, job_service, paycheque_service and blackout_service all do `from app.Tasks.services.task_service import user_exists`.

**Suggested fix:** Move `user_exists`/`user_for`, `owned_course` and `course_codes` into one shared module (shared/dates.py already holds `user_for`) and import them from there everywhere.

**What the fix could break:** Mechanical; the risk is an import cycle if the new home imports services, so keep it dependent on models only.

### L12. The week-load and crunch figures read tasks through list_tasks' list defaults, so a snoozed task's hours vanish from the week it is due and finished work drops out of past weeks.

*Integrity · plausible*

A snooze hides a task from the list but leaves its due date alone on purpose, so the work is still due that week. Because the load figures reuse the list's filters, snoozing Friday's essay until Thursday removes its estimate from this week's 'estimated' hours and its weight from the crunch strip, making an over-committed week look lighter exactly when the student is putting things off; the same week_load feeds the Jobs page's hours-against-classes. Excluding done tasks also means a past week's crunch weight shrinks as its tasks are ticked off, so the strip describes what is left rather than how heavy the week was, which may or may not be intended.

**Files affected:**
- `backend/app/Calendar/services -> [load_service.py]`
- `backend/app/Tasks/services -> [task_service.py]`
- `backend/app/Jobs/services -> [earnings_service.py]`

**Evidence:** Calendar/services/load_service.py:233 (week_load) and :319 (crunch) call `list_tasks(db, user_id, start=window_start, end=window_end)` with the defaults include_done=False, include_archived=False, include_snoozed=False, which task_service.list_tasks applies for the to-do list (a snooze hides a task until its date).

**Suggested fix:** Pass include_snoozed=True from week_load and crunch, and decide explicitly whether done tasks count (they probably should for crunch, which describes a week's weight, and not for week_load's remaining estimate); add a test with a snoozed task.

**What the fix could break:** Weekly estimates and crunch weights rise for students who snooze; tests pinning current counts change.

### L13. Skipping a repeating task's occurrence, and its 'next due' date, still match occurrences by due_date, so a moved occurrence survives being cancelled and can be reported as next due after it is done.

*Integrity · verified*

The occurrence_date column was added precisely because matching on due_date deleted or duplicated moved occurrences (the comments in resync_occurrences describe that bug). Two paths were not converted. Cancelling a week's occurrence after moving it leaves the moved task on the list as live work for a week that was cancelled, and cancelling a different date that a moved occurrence happens to sit on deletes the wrong task. next_due ignores a moved occurrence that was completed, so the rule can show a date as next due when that occurrence is already done.

**Files affected:** `backend/app/Tasks/services -> [recurring_task_service.py]`

**Evidence:** Tasks/services/recurring_task_service.py:456 -- skip_occurrence deletes outstanding tasks with `TaskModel.due_date == on_date`; next_due (:158-162) builds its done set from `TaskModel.due_date`. The module docstring and written_dates/resync_occurrences key on occurrence_date because the student may move due_date. Reproduced on the SQLite fixtures: a weekly Monday rule, Monday's occurrence moved to Wednesday, then skip_occurrence(Monday) -> the moved task is still there, due Wednesday.

**Suggested fix:** Match on `TaskModel.occurrence_date == on_date` in skip_occurrence and build next_due's done set from occurrence_date, with tests that move an occurrence first.

**What the fix could break:** None beyond the corrected behaviour; rows written before occurrence_date existed may have it null and need the same backfill the column's introduction used.

### L14. Completion timing loads every task the user has ever completed on each Tasks page load, then discards all but the last month in Python.

*Scalability · plausible*

Repeating tasks write a row per occurrence (a daily chore is about 365 completed rows a year), so a student's completed-task history grows by hundreds to thousands of rows a year, and every Tasks page load pulls all of them as ORM objects to keep roughly a month. At around 100 users this is not an outage, but it is the one Tasks read whose cost grows without bound, and it is cheap to bound now.

**Files affected:** `backend/app/Tasks/services -> [timing_service.py]`

**Evidence:** Tasks/services/timing_service.py:101-109 -- completion_timing queries `TaskModel.user_id == user_id, TaskModel.done.is_(True), TaskModel.completed_at.isnot(None)` with no date bound, then skips rows with `finished_on < earliest`.

**Suggested fix:** Filter in SQL on `completed_at >= (start of the earliest window in the user's zone, converted to UTC) - 1 day`, using shared/dates.local_day_in_utc, and keep the exact local-day check in Python.

**What the fix could break:** An off-by-one at the window's edge if the UTC bound is computed without the zone; keep a margin of a day and the Python filter.

### L15. The effective hourly rate expands the whole calendar once per cheque, and the Jobs and Budget pages each call it alongside several other full expansions.

*Scalability · plausible*

With biweekly pay, a student has about 26 cheques with periods by December, so one Jobs page load runs roughly 30 full calendar expansions, and a Budget page load (safe-to-spend, forecast, year plan) runs another dozen or more. Each is cheap alone, but they grow with the number of cheques and events and all run on the request thread. At around 100 users this is latency rather than an outage; it is cheap to head off by expanding once.

**Files affected:**
- `backend/app/Jobs/services -> [earnings_service.py]`
- `backend/app/Finances/services -> [forecast_service.py, plan_service.py, safe_service.py]`

**Evidence:** Jobs/services/earnings_service.py:239-243 -- effective_rate loops `for cheque in cheques:` and calls `list_shifts(db, user_id, cheque.period_start, cheque.period_end, on_day=anchor)` for each; list_shifts runs list_occurrences (every event, the blackouts and the course codes) plus a jobs and a records query. earnings_summary also calls list_shifts three times through window_earnings and once per current job through upcoming_pay; forecast_service.pay_events and plan_service.solve call effective_rate again over 180 days, and safe_service calls upcoming_pay.

**Suggested fix:** Expand the user's shifts once for the widest window needed (the year to date, or the 180-day look-back) and bucket them by cheque period in memory; share that expansion between the figures built in one request.

**What the fix could break:** The per-period `assumed` flag depends on the anchor day only, so one expansion gives the same answer; tests pin the figures and would catch a regression.

### L16. The tax packet's 'tuition paid' is the ledger amount (after scholarships, with fees), which never matches the eligible tuition on a T2202 when a bill had either.

*Integrity · plausible*

The tax packet exists to sit beside the student's slips at tax time. The tuition credit is claimed on eligible tuition as the school reports it, which is before scholarships and excludes many mandatory fees, while this figure is what left the bank: net of bursaries and including fees such as a transit pass. A student with any deduction or fee will see a number that cannot match their T2202, and nothing on the packet says which definition it uses. The payment record already holds rate, credits, fees and deductions, so both figures are available.

**Files affected:**
- `backend/app/Jobs/services -> [tax_packet_service.py]`
- `backend/app/Jobs/schemas -> [tax_packet.py]`

**Evidence:** Jobs/services/tax_packet_service.py:119-132 -- `tuition_paid=_money(sum(abs(amount or 0.0) for (amount,) in tuition))` over `TransactionModel.amount` joined to each TuitionPaymentModel dated in the year; that row is credits x rate + fees - deductions (tuition_service.record_tuition).

**Suggested fix:** Report gross tuition (credits_counted x cost_per_credit, summed per payment) as the tuition figure, with fees and deductions shown separately, or label the current figure 'tuition paid from your accounts' and add the gross beside it.

**What the fix could break:** Changes a figure on the tax packet; tests pinning tuition_paid need updating.

### L17. Unticking 'counts' on the last spending account silently empties safe-to-spend, the exact outcome the last-of-a-kind guard exists to prevent for archiving.

*Integrity · plausible*

Ideas/design/finances.md explains the guard: archiving the last spending account makes safe-to-spend report $0.00 'with nothing on screen to say why, which is a wrong answer that looks exactly like a right one'. Since D39 made the counts switch remove an account from every analytic, unticking it on the only spending account produces the same silent zero (or a negative figure, once commitments are subtracted), but neither the guard nor safe-to-spend notices. D39 deliberately lets any account be unticked, so the gap is in what the figure says rather than in allowing the change.

**Files affected:** `backend/app/Finances/services -> [account_service.py, safe_service.py]`

**Evidence:** Finances/services/account_service.py:90-120 -- would_orphan_role counts surviving accounts by kind and `archived` only, and update_account calls it only when the kind changes or `archived` becomes True; safe_service.spendable_accounts (:94-115) reads spending accounts with `counts_toward_net_worth.is_(True)`.

**Suggested fix:** Either extend the role check to `counts_toward_net_worth` (refusing, with the same message, to untick the last counted spending account), or have safe-to-spend return an explicit 'no counted spending account' state that the page explains.

**What the fix could break:** Refusing would contradict D39's 'any account may be unticked'; the explicit state is the less intrusive option.

### L18. A category limit of 0 with spending against it reports 0% used, and the client's progress bar then announces 'No target set'.

*Accessibility · plausible*

The design treats a limit of 0 as a real instruction ('nothing is meant to go here'), and the server documents that it reports 0% for it and relies on `remaining` to show the overspend. The visible note does say '$X over', but the bar beside it is empty and uncoloured, and a screen reader is told there is no target at all, which is the opposite of the truth for the one limit whose whole meaning is 'any spending is over'.

**Files affected:**
- `backend/app/Finances/services -> [activity_service.py]`
- `frontend/src/features/budget/components -> [ProgressBar.tsx, WhereItWent.tsx]`

**Evidence:** Finances/services/activity_service.py:226 -- `used_percent=round(actual / limit * 100, 1) if limit else 0.0`; ProgressBar.tsx computes `hasTarget = max > 0`, so for max=0 it sets state 'none', width 0 and `aria-valuetext` 'No target set', although WhereItWent renders the row only when `entry.limit !== null` and its note says '$X over'.

**Suggested fix:** Have ProgressBar treat a defined limit of 0 as a target (state 'over' when value > 0, full width, valuetext '$X over a $0 limit'), or have the server send an explicit over flag the bar can use.

**What the fix could break:** Visual change on rows with a zero limit only.

### L19. Quick capture and the omnibox each read a line into a task with their own copy of the same rules (course matching, unmatched-code handling, duration clamping).

*Maintainability · plausible*

Two inputs that file tasks from typed text have to agree on how a line is read, or a student gets a different task depending on which box they typed into. Today they agree by being written twice; the next rule (a due time, a priority word) will land in one and not the other.

**Files affected:**
- `backend/app/Tasks/services -> [quick_capture_service.py]`
- `backend/app/Omnibox/services -> [omnibox_service.py]`

**Evidence:** Tasks/services/quick_capture_service.py:19-54 (build_preview) and Omnibox/services/omnibox_service.py:133-165 plus _task_preview (:277-298) both call parse(text, user_today(...)), resolve_course on parsed.course_code, put an unmatched code back into the title, and drop a duration outside 1..MAX_ESTIMATED_MINUTES; each then builds its own preview schema.

**Suggested fix:** Have the omnibox's task path call quick_capture_service.build_preview (or extract the shared reading into one function both use) and map its result.

**What the fix could break:** Low; the two previews have different response shapes, so only the reading should be shared.

### L20. POST /recurring/run accepts any `through` date, so one request can write future standing-instruction payments into the ledger as if they had happened.

*Integrity · plausible*

The module's central rule is that a payment becomes a row only once it has happened, because a future payment in a balance reports money as gone while it is still in the account. The catch-up endpoint lets the client choose the cut-off, so `?through=2027-06-01` writes up to eight months of rent and subscriptions as real expenses, and they then sit in the ledger with dates in the future. Today's client never sends `through`, which keeps this low, but it is a one-parameter way for a script or a future client bug to corrupt balances, and the parameter appears to exist only for tests.

**Files affected:**
- `backend/app/api/routes -> [recurring.py]`
- `backend/app/Finances/services -> [recurring_service.py]`

**Evidence:** api/routes/recurring.py:94 -- `through: date | None = Query(default=None, description="Defaults to today")` is passed straight to run_due (:112), whose due_dates writes every unwritten occurrence up to `through` with no check that it is not after the user's today.

**Suggested fix:** Clamp `through` to the user's today in run_due (or drop the parameter from the route and keep it for tests at the service level).

**What the fix could break:** None for the current client.

### L21. course_category_weights has no unique (course_id, category), so a category can hold two weight rows.

*Integrity · plausible*

Weights are written by check-then-insert in the services. Two concurrent weight edits on one course, or any script that inserts without checking, can leave two rows for one category. The dict in `category_weights` then keeps whichever row loads last, so the course average, `sync_grade_weights` and the weight total can silently disagree with what the course page shows, and deleting the category may remove only one of the rows. The Uniqueness block exists precisely to close check-then-insert races, and this table was left out of it.

**Files affected:**
- `backend/app/_database -> [models.py]`
- `backend/app/Grades/services -> [grade_service.py]`

**Evidence:** Application/backend/app/_database/models.py:342 -- CourseCategoryWeightModel declares only `course_id`, `category`, `weight`; the Uniqueness block (line 1530 on) covers courses, accounts, categories, targets and limits but not this table, and `CourseModel.category_weights` builds `{cw.category: cw.weight for cw in self.category_weight_rows}`.

**Suggested fix:** Add `Index("uq_course_category_weights_course_category", CourseCategoryWeightModel.course_id, CourseCategoryWeightModel.category, unique=True)` to the Uniqueness block, after a one-off query that finds and merges any existing duplicates.

**What the fix could break:** The index creation fails on a database that already holds duplicates, so production must be checked (and cleaned) first; services that insert a duplicate would then get an IntegrityError (a 500) instead of a silent second row.

### L22. Enumerated and ranged columns on the older tables have no CHECK constraints, unlike the Phase 2 and 3 tables.

*Integrity · plausible*

Every allowed value of these columns lives only in Pydantic enums. A script, a migration, a definer function or a future code path that writes an unexpected value ("Expense", priority 9, a semester typo) is stored silently, and the readers that branch on the value then mis-file it: a transaction whose kind matches nothing drops out of every income and spending figure, and an unknown semester has no term dates. The newer tables show the project already prefers database-enforced vocabularies, so the two halves of the schema now follow different rules.

**Files affected:** `backend/app/_database -> [models.py]`

**Evidence:** Application/backend/app/_database/models.py:504 -- `kind = Column(String, nullable=False)` on transactions ("income | expense | transfer" only in a comment); likewise accounts.kind (449), events.kind (725), grades.schedule_as (413), courses.semester (264), jobs.kind (1268), recur_freq on four tables, tasks.priority 1-5 (831). Newer tables do check theirs, e.g. `CheckConstraint("status IN (...)", name="ck_application_status")` at 2497.

**Suggested fix:** Add named CHECK constraints for the enumerated columns (and `priority BETWEEN 1 AND 5`) on Postgres through the schema step, generated from the same tuples the schemas use, after a query confirms production holds only valid values. SQLite can keep application-level checks, as it already does for constraints it cannot add.

**What the fix could break:** A constraint fails to install if any existing row violates it, so data must be audited first; a later code path writing a new value must extend the constraint in the same change, or its writes start failing with IntegrityError.

### L23. ADDED_COLUMNS mixes Postgres-safe DDL with SQLite-only DDL, so ensure_schema fails on any Postgres database older than the current models.

*Reliability · plausible*

The module works on production only because Supabase's tables were created whole by create_all from the current models, so none of the older entries has ever run there. A Postgres database built from an earlier commit (a staging copy, a restored backup, a contributor's local Postgres) would hit `default expression is of type integer` or `type "datetime" does not exist` partway through the schema step, or silently gain CHAR(32) id columns that never compare equal to the UUIDs the models write. Nothing marks which entries are safe, and the next contributor copying an old line repeats the trap the accounts comment describes.

**Files affected:** `backend/app/_database -> [migrations.py]`

**Evidence:** Application/backend/app/_database/migrations.py:27 -- `"email_verified": "BOOLEAN NOT NULL DEFAULT 0"` and `"deleted_at": "DATETIME"` sit beside entries the comments call out as Postgres-safe (`"BOOLEAN NOT NULL DEFAULT true"`, `{"sqlite": "CHAR(32)", "postgresql": "UUID"}`); UUID foreign-key columns such as `events.grade_id` are plain `"CHAR(32)"`.

**Suggested fix:** Convert every entry to dialect-neutral DDL (`DEFAULT false`, `TIMESTAMP`) or a per-dialect dict as the newer entries do, and add a test that renders each entry for Postgres and checks it parses there.

**What the fix could break:** Changing the strings affects only databases that still lack a column; SQLite accepts `false` and `TIMESTAMP`, so existing local databases are unaffected.

### L24. The grade-distribution cohort floor counts contributions, not distinct contributors.

*Security · plausible*

The floor exists so that no course-term group is small enough to point at a person. One student holding two course rows that resolve to the same course key in the same term (a case-variant duplicate code, a retake entered twice, two rows linked to one catalogue course) contributes two grades, so a published band can rest on four people, or fewer with more duplicates. Nothing reads the sealed table until Phase 3, so there is no exposure today, but the guarantee in the docs is stronger than the SQL.

**Files affected:**
- `backend/app/_database -> [rls.py, distributions.py]`
- `backend/app/Grades/services -> [term_review_service.py]`

**Evidence:** Application/backend/app/_database/rls.py:412 -- `SELECT course_key, term_code FROM counted GROUP BY course_key, term_code HAVING count(*) >= 5`, where `counted` has one row per term_reviews row; term_reviews is unique only per (user_id, course_id), and `course_key_of` maps differently spelled codes (or two courses hand-linked to one catalogue course) to the same key.

**Suggested fix:** Carry `r.user_id` through the CTEs, keep one grade per (user, course_key, term_code), and require `count(DISTINCT user_id) >= 5`; mirror it in the SQLite twin in distributions.py and add a test with one user contributing twice.

**What the fix could break:** Some course-terms currently at the floor would drop below it and disappear from the table; the counts in a band change for any student with duplicates.

### L25. A second player's dispute silently overwrites the first, because a game holds a single dispute slot.

*Integrity · plausible*

Confirming is refused over someone else's dispute, but disputing is not. If two teammates dispute the same game with different scores, the second write replaces the first player's name and scores with no trace, so the recorder only ever sees one of the objections, and the first player's dispute appears to have been withdrawn. The rules in isolation-and-sharing.md (a dispute shows both scores until the recorder corrects) assume one dispute at a time without enforcing it.

**Files affected:** `backend/app/_database -> [rls.py, teams.py]`

**Evidence:** Application/backend/app/_database/rls.py:547 -- account_dispute_team_game updates `WHERE g.id = p_game AND account_on_team(g.team_id) AND g.recorded_by <> account_current_user() AND g.confirmed_by IS NULL AND ...` with no `g.disputed_by IS NULL OR g.disputed_by = account_current_user()` guard; teams.py:dispute_game mirrors it.

**Suggested fix:** Refuse a dispute while another player's is open (add the same `disputed_by IS NULL OR disputed_by = caller` condition the confirm function uses, in both twins), or move disputes to a child table if several should be shown.

**What the fix could break:** A player who wants to dispute an already-disputed game is refused instead of overwriting; the client should say why. Changing the function needs the schema step to run.

### L26. Audit log lines interpolate caller-supplied text unescaped, so a login attempt can forge audit entries, and deleted titles land in the logs.

*Security · plausible*

Cloud Run splits stdout on newlines, so an unauthenticated login attempt with an email such as "x\nauth.login outcome=success email=victim@x.com" writes a second, fabricated audit line, and any signed-in user can do the same through a task or reminder title they then delete. The audit log exists to be trusted after a breach; forged success lines or noise in it undermine exactly that use, and the deletion lines also copy free-text personal content (task and reminder titles) into logs that are otherwise kept to identifiers.

**Files affected:**
- `backend/app/shared -> [audit.py]`
- `backend/app/api/routes -> [auth.py, tasks.py, grades.py]`
- `backend/app/Auth/schemas -> [credentials.py]`

**Evidence:** Application/backend/app/shared/audit.py:37 -- `parts.append(f"email={email}")` and `log(" ".join(parts))` with no escaping; routes/auth.py:165 logs `email=payload.email` on a failed login, and `LoginRequest.check_email` only strips and lower-cases (deliberately lenient), so the value may contain a newline; routes/tasks.py:830 passes `detail=deleted.title`.

**Suggested fix:** Escape or quote every interpolated value (for example `repr()` or replacing control characters), or emit structured JSON log records with fields instead of a joined string; log ids rather than titles for deletions.

**What the fix could break:** Log lines change shape, so any saved log query or alert matching the current format must be updated; losing titles makes a deletion line less readable to a human scanning logs.

### L27. The Semester enum is defined twice, in Grades/utils/enums.py and Users/schemas/academic_status.py.

*Maintainability · plausible*

The user's current term and every course's term are compared against each other to decide past, current and future, so the two vocabularies must stay identical. A term added or renamed in one enum (a "Full year" option, say) would validate on courses and be refused, or silently never match, on the academic status, and the OpenAPI schema already advertises two different enum types with the same name.

**Files affected:**
- `backend/app/Grades/utils -> [enums.py]`
- `backend/app/Users/schemas -> [academic_status.py]`

**Evidence:** Application/backend/app/Users/schemas/academic_status.py:14 -- `class Semester(str, Enum): FALL = "Fall" ...` repeats `app.Grades.utils.enums.Semester` with the members in a different order; the courses schema, syllabus intake and the grades routes import the Grades one, the user's academic status uses its own.

**Suggested fix:** Delete the copy in academic_status.py and import `Semester` from `app.Grades.utils.enums` (utils is the shared layer both modules may import).

**What the fix could break:** The OpenAPI component for the academic status changes name or order, which a generated client could notice; behaviour is otherwise identical.

### L28. Nineteen schema modules use Pydantic v1 `class Config`, deprecated in Pydantic 2 and removed in 3, while the rest use `model_config`.

*Maintainability · plausible*

Pydantic 2 emits a PydanticDeprecatedSince20 warning for every class-based Config and Pydantic 3 drops it, so an eventual upgrade breaks every one of these models at import. Two spellings of the same setting across modules also make it unclear to a new contributor which to copy.

**Files affected:**
- `backend/app/Grades/schemas -> [course.py, grade.py, degree.py]`
- `backend/app/Users/schemas -> [user.py, academic_status.py]`
- `backend/app/Calendar/schemas -> [blackout.py, event.py]`
- `backend/app/Finances/schemas -> [account.py, budget.py, plan.py, recurring.py, sinking.py, transaction.py, tuition.py]`
- `backend/app/Jobs/schemas -> [job.py, paycheque.py]`
- `backend/app/Tasks/schemas -> [recurring_task.py, reminder.py, task.py]`

**Evidence:** Application/backend/app/Grades/schemas/course.py -- `class Config: from_attributes = True; populate_by_name = True` inside `Course`; `grep -rln "class Config:" app` lists 19 files, while app/Grades/schemas/catalogue.py uses `model_config = ConfigDict(from_attributes=True)`. requirements.txt pins pydantic==2.12.5.

**Suggested fix:** Replace each `class Config` with `model_config = ConfigDict(...)` in one mechanical change, and add a test or lint rule that fails on `class Config:` in app/.

**What the fix could break:** Low: the settings carry over one to one and configs are still inherited from base models; the deprecation warnings disappear from test output.

### L29. Push endpoints are any https URL a signed-in user submits, so the scheduler POSTs (and follows redirects) to arbitrary hosts.

*Security · plausible*

A user can register an endpoint on any host, including internal or third-party https services, and the API then sends authenticated-looking POSTs there from its own egress address on every reminder and test, following any redirect (as a GET after 301/302) to wherever it points, including plain http. The response body is not returned, so the exposure is small, but the status code decides whether the subscription is kept or removed, and the server becomes a request relay the invite list is the only gate on.

**Files affected:**
- `backend/app/Notifications/schemas -> [push.py]`
- `backend/app/Notifications/services -> [push_service.py]`

**Evidence:** Application/backend/app/Notifications/schemas/push.py -- `SubscriptionCreate.https_only` checks only `value.startswith("https://")`; push_service.py:56 sends with `requests.post(endpoint, headers=headers, data=body, timeout=10)`, which follows redirects by default.

**Suggested fix:** Accept only the browser push services' hosts (fcm.googleapis.com, updates.push.services.mozilla.com, *.notify.windows.com, web.push.apple.com and the like) at subscribe time, and send with `allow_redirects=False`.

**What the fix could break:** A browser whose push service is not on the list cannot subscribe until it is added; existing subscriptions on other hosts should be revalidated or dropped.

### L30. Every Google sign-in fetches Google's signing keys afresh, with the library's 120-second default timeout.

*Reliability · plausible*

Each Google sign-in makes an outbound HTTPS request for Google's certificates before it can answer, adding latency to every sign-in and making it depend on that fetch. If Google's endpoint is slow rather than down, the request thread waits up to two minutes before GoogleUnavailable is raised, holding one of the request pool's threads and a database session (the route's DBSession is already open) the whole time; a handful of such sign-ins at once would exhaust the five pooled connections.

**Files affected:** `backend/app/Auth/services -> [google_auth_service.py]`

**Evidence:** Application/backend/app/Auth/services/google_auth_service.py -- `id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)` builds a new uncached transport per call; google/auth/transport/requests.py sets `_DEFAULT_TIMEOUT = 120`.

**Suggested fix:** Reuse one transport with certificate caching (a module-level `google.auth.transport.requests.Request` over a `CacheControl`-wrapped session, or cache the certs for their max-age) and pass a short timeout (a few seconds) to the fetch.

**What the fix could break:** Cached keys must honour Google's rotation (respect Cache-Control max-age); a short timeout turns a slow Google into a quicker 503 instead of a slow success.

### L31. A syllabus parse holds a database connection and an open transaction for the whole provider call, up to 90 seconds.

*Scalability · plausible*

Reading a PDF syllabus routinely takes tens of seconds, and during all of it the request keeps its pooled connection checked out. Five students uploading syllabi on one instance in the first week of term (the moment this feature exists for) would take every connection that instance has, and every other request there would wait ten seconds for one and then fail with a 500. Through Supabase's transaction pooler an idle-in-transaction connection is also held server-side for the duration. Rated low in review: parses are capped per user per day, so overlapping 90-second calls are unlikely at under 100 users; worth fixing before the cap or the user count grows.

**Files affected:**
- `backend/app/Intake/services -> [syllabus_service.py, llm.py]`
- `backend/app/_database -> [db.py]`

**Evidence:** Application/backend/app/Intake/services/syllabus_service.py -- `parse` queries the user and `used_today` (opening the session's transaction) and then calls `llm.extract_document(...)`, whose `http_post` waits `timeout=TIMEOUT_SECONDS` (90); db.py sizes the pool at `POOL_SIZE = 3`, `MAX_OVERFLOW = 2`, `POOL_TIMEOUT_SECONDS = 10` per instance.

**Suggested fix:** End the transaction before the provider call (read and check the cap, then `db.commit()` or `db.close()`), make the call with no session work in flight, and reopen for the insert; or move parsing to a background job the client polls.

**What the fix could break:** The cap check and the insert are no longer atomic, so two simultaneous uploads may both pass a cap of one remaining (acceptable, or reserve the slot first); the code path gains a second transaction.

### L32. The dashboard computes a required final for every course against a fixed 90% target, and no client reads the result.

*Maintainability · plausible*

The response carries a per-course "needed on the final" figure measured against 90% for every course, while the Attention list on the same response measures each course against its own target or the account default (85% by default), so two fields of one payload answer the same question differently. Nothing displays the 90% figures today, but they are computed on every dashboard load and documented in the API, so the next screen built on them would show the A+ target the old docstring says was removed.

**Files affected:**
- `backend/app/Grades/services -> [dash_services.py]`
- `backend/app/api/routes -> [grades.py]`
- `backend/app/Grades/schemas -> [dashboard.py]`

**Evidence:** Application/backend/app/Grades/services/dash_services.py -- `DEFAULT_TARGET_GRADE = 90.0`, and `get_dashboard` calls `calculate_required_final(db, user_id, course.id, target_grade, course=course)` per course with that one target; routes/grades.py declares `target_grade: float = Query(DEFAULT_TARGET_GRADE, ...)` and features/grades/hooks/useDashboard.ts calls `fetchDashboard(userId)` with no target. `needed_final_score`, `courses_needing_final_score` and `unfinished_categories_by_course` appear in the frontend only in types.ts.

**Suggested fix:** Drop `needed_final_score`, `courses_needing_final_score` and `unfinished_categories_by_course` (and the query parameter) if no screen needs them, or compute them with `effective_target(course, preferences.default_target_grade)` as Attention does.

**What the fix could break:** Removing fields changes the API contract; check no client (or test) reads them first.

### L33. Reminders that went stale unpushed keep their owners in the scheduler's candidate list on every run, indefinitely.

*Scalability · plausible*

Any reminder that was never pushed and never dismissed (one created before the user turned notifications on, or one whose every delivery failed) stays a candidate for ever, so that user is acted as, loaded and queried on every scheduler run, every few minutes, for nothing. The candidate list only grows; at 100 users it is cheap, but it is unbounded work that also makes the scheduler's logs and counts harder to read.

**Files affected:**
- `backend/app/Notifications/services -> [push_service.py]`
- `backend/app/_database -> [rls.py, identity.py]`

**Evidence:** Application/backend/app/_database/rls.py -- `account_users_with_unpushed_reminders` selects users with `r.dismissed_at IS NULL AND r.pushed_at IS NULL AND r.remind_at <= p_horizon` and a device, with no lower bound; push_service.dispatch_due_reminders then skips anything `remind_at <= now - STALE_AFTER` without marking it.

**Suggested fix:** Give the candidate query a lower bound (`remind_at > p_horizon - (STALE_AFTER + WIDEST_ZONE)` or similar) in both the definer function and its SQLite twin, or mark stale reminders (a `pushed_at` sentinel or a `push_skipped_at` column) when the dispatch passes over them.

**What the fix could break:** Changing the definer function needs the schema step to run; the bound must stay wide enough for every time zone or due reminders are missed.

### L34. Every Settings save returns the full UserDetail, lazily loading and re-validating every course and grade, with placeholder course figures.

*Scalability · plausible*

Saving a timezone triggers one lazy query per course for its grades (plus its weights), and runs every course and grade through the CourseBase and GradeBase validators, so the single bad row described in the response-validation finding also makes Settings fail to save with a 500. The course payload it builds is never used and would mislead anyone who did use it: every course reports no average, no letter and the current term.

**Files affected:**
- `backend/app/api/routes -> [users.py]`
- `backend/app/Users/schemas -> [user.py]`

**Evidence:** Application/backend/app/api/routes/users.py -- `@router.patch("/{user_id}", response_model=UserDetail, ...)`, where `UserDetail.courses: list[CourseDetail]`; frontend services/currentUserClient.ts sends every preferences save to this route and reads only the user fields. Nothing attaches `reported_average`, `letter_grade` or `term_bucket` to these course rows, so each serialises with the schema defaults.

**Suggested fix:** Return `User` (or a small preferences payload) from the PATCH and GET-by-id routes, and drop `UserDetail` unless a caller needs courses, in which case build them through course_service so they carry real figures.

**What the fix could break:** A client reading `courses` from these responses would lose them; the shipped frontend does not.

### L35. A database error during the startup purge stops the instance from starting, instead of letting /health report 503.

*Reliability · plausible*

On a scale-to-zero service every cold start runs this query. If the database is momentarily unreachable (Supabase waking from a pause, a pooler hiccup), the exception escapes the lifespan, uvicorn aborts startup, and Cloud Run sees a crashed container rather than a running one whose /health answers 503 as it was designed to. The purge is optional work at that moment, yet it turns a transient database blip into a failed instance start and a confusing crash loop in the logs.

**Files affected:**
- `backend/app -> [main.py]`
- `backend/app/Users/services -> [user_service.py]`

**Evidence:** Application/backend/app/main.py -- the lifespan runs `with SessionLocal() as session: purged = purge_expired_users(session)` with no try; purge_expired_users guards each account's delete (`except SQLAlchemyError`) and storage errors, but not its first query, `expired_user_ids(db, cutoff)`.

**Suggested fix:** Wrap the purge call in the lifespan in a try/except that logs the failure (to `app.audit`) and continues, so the purge simply runs on the next start.

**What the fix could break:** A persistently failing purge could go unnoticed unless the log line is alerted on; accounts past their grace period wait for a later start.

### L36. The schema gate checks definer functions by name only, so a changed function body or signature deploys without the schema step.

*Reliability · plausible*

The gate exists so that new code never runs against an older database. Columns and new functions are covered, but most changes to the sharing features are edits to an existing definer function (a new limit, a fixed condition, an added parameter) or to a policy or grant in rls.py. Such a change passes the gate whether or not the schema step ran, and the API then calls the old SQL: a fix that silently is not live, or, for a changed signature, every call to that function failing with a 500.

**Files affected:**
- `backend/scripts -> [check_schema_conformance.py]`
- `backend/app/_database -> [rls.py]`

**Evidence:** Application/backend/scripts/check_schema_conformance.py -- `missing.extend(f"function {name}()" for name in rls.FUNCTIONS if name not in state["functions"])`, where `state["functions"]` is the set of `pg_proc.proname` in `public`; argument types, bodies, policies and grants are not compared.

**Suggested fix:** Have the gate compare more than names: for example store a hash of `rls.render_sql()` in a small metadata table when `install` runs and fail the gate when it differs from the deploying code's hash, or compare `pg_get_functiondef` for each function.

**What the fix could break:** A hash comparison fails on any whitespace-only change to the SQL, forcing a schema step that is harmless but must be run; the metadata table needs its own row-security kind.

### L37. Date labels mix a hard-coded English weekday with a month name in the browser's locale.

*Maintainability · plausible*

`shortDate`, `rangeLabel`, `weekLabel` and `monthLabel` take the month from the browser's locale but `shortDate` takes the weekday from an English table, so a browser set to French renders "Tue 8 sept." and a German one "Tue 8 Sept.". Every other string in the app is English, so the locale-dependent half is the odd one out. It is cosmetic for most users but it also makes the output of these helpers depend on the test machine's locale, which is a trap for snapshot-style tests and for contributors in other locales.

**Files affected:** `frontend/src/shared/utils -> [dateUtils.ts]`

**Evidence:** Application/frontend/src/shared/utils/dateUtils.ts:6 -- `const WEEKDAY_LABELS = ["Mon", "Tue", ...]` is fixed English, while `monthName` (line 129) returns `fromIso(value).toLocaleString(undefined, { month: ... })`; `shortDate` (line 122) joins the two.

**Suggested fix:** Pick one rule: pass an explicit locale ("en-CA" or "en-GB") to `toLocaleString` in `monthName`, or derive the weekday from `Intl.DateTimeFormat` with the same locale. One shared constant for the display locale keeps the date helpers consistent.

**What the fix could break:** Users with a non-English browser locale would see month names change to English; any test that asserted a locale-specific month would need updating.

### L38. Fitness page visits are never counted in usage analytics: the room list is hand-copied on both sides and both copies miss it.

*Maintainability · plausible*

The usage report exists to test the vision's 'two rooms in a week, one unprompted' thesis, but visits to the Fitness room (added in Phase 2) return null from `moduleFor` and are silently dropped, so every Fitness visit reads as no use at all. The list of rooms lives in three places (the route table, `moduleFor`, and the backend enum) with nothing tying them together, so the next room added will be missed the same way. Adding "fitness" only on the frontend would make the backend answer 422 to every Fitness visit, which `.catch(() => {})` would also swallow.

**Files affected:**
- `frontend/src/shared/hooks -> [useVisitCounter.ts]`
- `backend/app/Usage/schemas -> [usage.py]`
- `frontend/src/app -> [App.tsx]`

**Evidence:** Application/frontend/src/shared/hooks/useVisitCounter.ts:13 -- `return ["grades", "calendar", "tasks", "jobs", "budget", "settings"].includes(first) ? first : null;`; the backend `Module` enum in Usage/schemas/usage.py lists the same seven rooms, while App.tsx:71 routes `/fitness` to `FitnessPage` and the sidebar links it.

**Suggested fix:** Add `FITNESS = "fitness"` to the backend `Module` enum and "fitness" to `moduleFor`, and add a frontend test that every sidebar route maps to a module (or derive the list from the sidebar's own items).

**What the fix could break:** None for users; historical usage data simply starts including Fitness from the deploy date, which matters when comparing weeks across it.

### L39. A course's final grade uses 0 as 'none recorded', so every reader must repeat a `> 0` check and a real 0 cannot be stored.

*Maintainability · plausible*

The project already fixed this exact zero-versus-null confusion for `average` (audit #31) and for grade scores, but the course result still encodes 'not recorded' as 0. Eleven sites across both tiers must each remember the sentinel; one that forgets treats an unfinished course as a 0% result (an F in degree progress, a 0 in a distribution). A student cannot clear a final grade except by typing 0, and a genuine 0% result is indistinguishable from none.

**Files affected:**
- `frontend/src/features/grades -> [types.ts]`
- `frontend/src/features/grades/components -> [CourseList.tsx, ProjectionReview.tsx]`
- `backend/app/_database -> [models.py, distributions.py, rls.py]`
- `backend/app/Grades/schemas -> [course.py]`
- `backend/app/Grades/utils -> [terms.py]`
- `backend/app/Grades/services -> [dash_services.py, grade_service.py, degree_service.py]`

**Evidence:** Application/backend/app/_database/models.py:288 -- `final_grade = Column(Float, default=0.0)` documented as '0 means none recorded'; the same `final_grade > 0` test is repeated in CourseList.tsx:18, ProjectionReview.tsx:10, terms.py:177, dash_services.py:359/461/491, grade_service.py:572, degree_service.py:85, distributions.py:35 and rls.py:400, while course.py:220 uses plain truthiness.

**Suggested fix:** Make `final_grade` nullable end to end (column, schemas, TypeScript `number | null`), migrate existing 0.0 values to NULL, and replace the `> 0` checks with `is not None` through one helper such as `course_result_grade`.

**What the fix could break:** Needs a data migration in Postgres and SQLite; every reader and the RLS SQL function must change together, and the course forms must send null for an empty field instead of `Number("")`, which is 0.

### L40. Cancelling one date of a series and deleting the whole series share one DELETE URL, told apart only by an optional query parameter.

*Integrity · plausible*

A recoverable action (skip a date, undone by `restoreOccurrence`) and an irreversible one (delete a series with all its skipped dates and sharing) are the same request minus a query string. Anything that drops the query (a refactor that builds the URL through a helper that discards it, a retry layer, a proxy rewriting URLs) silently turns 'no lecture on Monday' into 'delete every lecture', and the delete-confirmation sweep in `deleteConfirmations.test.ts` does not look at `skipOccurrence` because its name is not delete-prefixed. The restore path is already a separate POST route, so the API is asymmetric as well.

**Files affected:**
- `frontend/src/features/calender -> [api.ts]`
- `backend/app/api/routes -> [calendar.py]`

**Evidence:** Application/frontend/src/features/calender/api.ts:39 -- `skipOccurrence` sends `del(`${endpoints.calendar.event(userId, eventId)}?on_date=${onDate}`)` to the same path `deleteEvent` uses (line 34); routes/calendar.py:195 `remove_event` skips one date when `on_date` is present and otherwise deletes the series.

**Suggested fix:** Give skipping its own route, mirroring restore: `POST /events/{id}/occurrences/{on_date}/skip` (or `DELETE /events/{id}/occurrences/{on_date}`), and make `DELETE /events/{id}` reject an `on_date` parameter.

**What the fix could break:** A route change needs the frontend and backend deployed together (or the old form kept for a release); the OpenAPI docs and any tests calling `?on_date=` change.

### L41. The calendar re-declares which job-application statuses are still open instead of importing the jobs feature's `OPEN_STATUSES`.

*Maintainability · plausible*

The calendar decides which applications still put a deadline or follow-up on the calendar using a private, untyped copy of the jobs feature's rule. If the jobs module adds a status (an 'assessment' stage, say) or reclassifies one, the tracker and triage change and the calendar silently keeps the old list, so follow-ups either vanish from the calendar or linger for closed applications. The literal set is also typed as `Set<string>`, so a misspelt status would compile.

**Files affected:**
- `frontend/src/features/calender/hooks -> [useCalender.ts]`
- `frontend/src/features/jobs/applications -> [types.ts]`

**Evidence:** Application/frontend/src/features/calender/hooks/useCalender.ts:201 -- `const open = new Set(["applied", "screening", "interview", "offer"]);` while jobs/applications/types.ts:28 exports `OPEN_STATUSES: ApplicationStatus[] = ["applied", "screening", "interview", "offer"]`, which `triage.ts` already imports.

**Suggested fix:** Import `OPEN_STATUSES` from `jobs/applications/types` in `applicationOccurrences` (the file already imports `Application` from there).

**What the fix could break:** None; same values today.

### L42. Bulk grade entry silently drops a half-filled row, so a grade typed without its 'Out of' value is never saved and nothing says so.

*Integrity · plausible*

The intent ('a blank row is just an unused slot') is right for an empty row, but the filter also discards a row with a name and a score and no maximum, or a maximum and no name. The save succeeds for the other rows, the dialog closes, and the student believes every mark they typed was recorded; the missing one only shows up later as a gap in the average. The on-screen hint says 'Blank rows are ignored', which a half-filled row is not.

**Files affected:** `frontend/src/features/grades/components -> [BulkGradesModal.tsx]`

**Evidence:** Application/frontend/src/features/grades/components/BulkGradesModal.tsx:64 -- `const filled = rows.filter((row) => row.name.trim() !== "" && row.max_score !== "");` and only `filled` is sent; the dialog then closes on success.

**Suggested fix:** Treat a row as blank only when every field is empty; for a partly filled row, refuse the submit and mark the row ("Row 3 needs a name and an Out of"), or make name and max_score `required` once any field in the row has a value.

**What the fix could break:** Students who relied on leaving a placeholder name in a spare row would now be asked to clear it.

### L43. The course-links editor promises that addresses without http:// are assumed https, but its `type="url"` inputs make the browser refuse such addresses before the form submits.

*Reliability · plausible*

Browser constraint validation requires an absolute URL in a url input, so typing `canvas.ubc.ca` blocks Save with the browser's 'Please enter a URL' bubble. The backend's bare-domain handling, and the help text describing it, can therefore never be reached from the only form that sends links. Students pasting from an address bar usually get the scheme, but anyone typing a domain by hand is told one thing and shown another.

**Files affected:**
- `frontend/src/features/grades/components -> [CourseLinksModal.tsx]`
- `backend/app/Grades/schemas -> [course.py]`

**Evidence:** Application/frontend/src/features/grades/components/CourseLinksModal.tsx:126 -- the address input is `type="url"` inside a validating `form` (no `noValidate`), while the note above it says 'Addresses without http:// are assumed to be https.'; Grades/schemas/course.py:66 does prepend `https://` to a bare domain.

**Suggested fix:** Either use `type="text"` with `inputMode="url"` (keeping the server-side check as the authority) or add `noValidate` to the form; keep the note only if bare domains really are accepted.

**What the fix could break:** Losing the browser's URL check means obviously wrong text reaches the API, which already rejects non-http(s) schemes with a 422 message the dialog shows.

### L44. The credits bar reports aria-valuenow above aria-valuemax once a student passes the credit target, the fault the budget ProgressBar already had fixed.

*Accessibility · plausible*

Finishing a degree with a few credits over the target is common (123 of 120), and then the progressbar's current value exceeds its maximum, which ARIA forbids and screen readers announce inconsistently. The previous audit closed this exact defect for the budget bar only, so the rule was fixed per component rather than in one place. The stale 'Quarter marks' comment inside the function misdescribes the ticks.

**Files affected:** `frontend/src/features/grades/components -> [CreditsBar.tsx]`

**Evidence:** Application/frontend/src/features/grades/components/CreditsBar.tsx:39 -- `aria-valuenow={Math.round(completed)}` beside `aria-valuemax={target}` with no clamp (budget/components/ProgressBar.tsx:31 uses `Math.min(Math.round(value), rounded)`); a target of 0 also yields `aria-valuemax={0}` although the widths use `safeTarget`. The comment above the ticks says 'Quarter marks' while the code draws ticks at `[0.5, 0.8]`.

**Suggested fix:** Clamp `aria-valuenow` to the maximum (and use `safeTarget` for `aria-valuemax`), keeping the true figure in `aria-valuetext`/`aria-label`; correct the tick comment.

**What the fix could break:** None visible; screen-reader output changes only past the target.

### L45. Two editors key removable rows by array index, the bug audit #36 fixed in BulkGradesModal: the syllabus check table and the class-timetable meetings.

*Reliability · plausible*

Removing a row shifts every later row's data into the DOM nodes of the row before it. The inputs are controlled, so the values end up right, but focus stays on the same node, so a student who deletes a misread row while a later row's field has focus (or with a keystroke in flight) types into the wrong assessment. The check screen is described as 'the product' because people edit many rows on it, which is where this bites. The fix was made once in one modal and not carried to the other editable tables.

**Files affected:**
- `frontend/src/features/intake -> [SyllabusModal.tsx]`
- `frontend/src/features/calender/components -> [ClassScheduleModal.tsx]`

**Evidence:** Application/frontend/src/features/intake/SyllabusModal.tsx:160 -- `<tr key={index}>` for rows that each carry a remove button (`setRows(rows.filter((_, at) => at !== index))`); BulkGradesModal gave its rows a stable `id` for exactly this reason. ClassScheduleModal.tsx:167 -- `<fieldset key={index} className="calRecurrence">` for meetings that each have a Remove button.

**Suggested fix:** Give each row a client id when it is created or loaded (as BulkGradesModal's `emptyRow` does) and key on it, in both editors.

**What the fix could break:** None; the id is never sent.

### L46. The reminder screens tell students reminders only fire while the app is open, but a scheduler now pushes them to devices, so the help text steers people away from a feature that works.

*Reliability · plausible*

Push delivery was added after these explanations were written, and the user-facing copy was not updated with it (the code comments in useReminders and fetchDueReminders said the same until this pass). A student who reads the (?) learns not to rely on reminders and may never enable notifications, which is exactly the behaviour push was built to change; the usage metric for prompted visits depends on it. Copy that misdescribes the product is also the first thing a new contributor will trust.

**Files affected:**
- `frontend/src/features/tasks/components -> [ReminderBanner.tsx, ReminderModal.tsx]`
- `backend/app/Notifications/services -> [push_service.py]`

**Evidence:** Application/frontend/src/features/tasks/components/ReminderBanner.tsx:22 -- HelpTip text 'Only while the app is open. There is no background delivery...'; ReminderModal.tsx:101 -- 'It only fires while the app is open'. Meanwhile push_service.py `dispatch_due_reminders` pushes due reminders and stamps `pushed_at`, `useReminders` skips the local notification when `row.pushed_at` is set, and public/sw.js plus features/notifications/push.ts handle the subscription.

**Suggested fix:** Reword both HelpTips to describe the real paths: pushed to devices where notifications are enabled, shown in the app's banner either way, and link to the Settings control that enables push.

**What the fix could break:** None; copy only. Tests asserting the old sentences would need updating.

### L47. The Repeats header adds one occurrence of every active rule into a single 'each time round' figure, whatever each rule's frequency or number of weekdays.

*Readability · plausible*

The variable is called `weekly` but the sum ignores `freq`, `interval` and `byday`: a daily 30-minute chore, a Mon/Wed/Fri reading of an hour and a monthly 2-hour task add up to '3h 30m each time round', a figure that is not any real period's load (the true weekly cost is 3h 30m + 3h + about 30m). Students use this header to judge how much standing work they have, so a confident but meaningless number misleads, while the week-load figures elsewhere are computed properly by the server.

**Files affected:** `frontend/src/features/tasks/components -> [Repeating.tsx]`

**Evidence:** Application/frontend/src/features/tasks/components/Repeating.tsx:38 -- `const weekly = rules.filter((rule) => rule.active && rule.estimated_minutes).reduce((total, rule) => total + (rule.estimated_minutes ?? 0), 0);` rendered as `{duration(weekly)} each time round`.

**Suggested fix:** Compute a per-week figure from each rule (occurrences per week x estimate) and label it 'about Xh a week', or drop the header figure and rely on the server's week load.

**What the fix could break:** The figure changes for anyone with non-weekly or multi-day rules; none of the data changes.

### L48. The task forms copy their shared constants: the 2400-minute estimate cap is a bare literal in four places, `PRIORITY_STEPS` is defined four times, and the repeating-task dialog re-implements the tag parsing `taskFields` exists to share.

*Maintainability · plausible*

`taskFields.ts` was created because the task forms 'fail silently when they drift', yet the repeating-task dialog was left with its own copy of the tag rules, and the backend's estimate cap is copied as an unnamed number into four inputs. If the backend raises or lowers `MAX_ESTIMATED_MINUTES`, three inputs keep the old limit (the browser blocks valid values, or lets through values the API answers with a 422), and a change to how tags are split (say, de-duplicating) reaches tasks but not repeats.

**Files affected:**
- `frontend/src/features/tasks/components -> [RepeatingModal.tsx, EditTaskModal.tsx, TaskForm.tsx, HowLongPrompt.tsx, TaskItem.tsx]`
- `frontend/src/features/tasks -> [taskFields.ts]`

**Evidence:** Application/frontend/src/features/tasks/components/RepeatingModal.tsx:163, EditTaskModal.tsx:246 and TaskForm.tsx:119 -- `max={2400}`; HowLongPrompt.tsx:6 -- `const MAX_MINUTES = 2400;` ('Mirrors MAX_ESTIMATED_MINUTES in app/Tasks/schemas/task.py'). RepeatingModal.tsx:105 -- `tags: tagText.split(",").map((tag) => tag.trim()).filter(Boolean)` and :82 `rule?.tags.join(", ")`, the same rules as `parseTags`/`tagText` in taskFields.ts. `const PRIORITY_STEPS = Array.from(...)` is declared identically in TaskItem.tsx:18, EditTaskModal.tsx:17, TaskForm.tsx:6 and RepeatingModal.tsx:15.

**Suggested fix:** Export `MAX_ESTIMATED_MINUTES` and `PRIORITY_STEPS` from `tasks/types.ts` beside the priority bounds and use them everywhere; use `parseTags`/`tagText` in RepeatingModal.

**What the fix could break:** None; same values today.

### L49. API errors are thrown as bare `Error(message)`, so callers cannot tell not-found from invalid input, a server fault or a network failure.

*Maintainability · plausible*

The backend gives statuses meanings (400 wrong, 404 missing or not yours, 429 throttled), but the client flattens them into a message string. Any page that wants different behaviour for 404 (show "not found") versus a transient failure (offer retry) has nothing to branch on except message text, which is the root of the earlier "any failure reports Course not found" class of bug. It also makes 429 `Retry-After` and offline handling impossible to add centrally.

**Files affected:**
- `frontend/src/services -> [apiClient.ts]`
- `frontend/src/pages -> [InvitePage.tsx]`

**Evidence:** Application/frontend/src/services/apiClient.ts:116 -- `throw new Error(message);` after `extractErrorMessage(json, ...)`; the response status is discarded, and `fetch` rejections (offline, CORS, DNS) surface as the browser's own TypeError text. Consumer: InvitePage.tsx `look.catch(() => { if (!cancelled) setProblem(invalid); })` tells the user the link 'has expired, been used, or been cancelled' for any preview failure, including a network error, a 429 or a 5xx, because it cannot tell them apart.

**Suggested fix:** Throw an `ApiError extends Error` carrying `status`, the parsed `detail` and `retryAfter`, and map network failures to a distinct `kind`; migrate callers gradually since `message` stays the same.

**What the fix could break:** None for existing callers if `message` is unchanged; code using `instanceof Error` keeps working.

### L50. No request has a timeout or can be cancelled, so a stalled connection leaves a page loading with no error.

*Reliability · plausible*

A request that hangs (a mobile network switching, a Cloud Run instance stuck starting) keeps its page in the loading state until the browser's own limit, often minutes, and the user gets no message or retry. Because nothing can be aborted, hooks also cannot cancel a superseded request when the user changes month or week, which is why each hook has to guard against out-of-order answers itself.

**Files affected:** `frontend/src/services -> [apiClient.ts]`

**Evidence:** Application/frontend/src/services/apiClient.ts:91 and 150 -- `await fetch(buildUrl(path), { ...init, headers: {...}, body })` with no `signal`; `RequestOptions` accepts `RequestInit` but no caller passes an AbortSignal and `get`, `post`, `patch`, `put` and `del` do not expose one.

**Suggested fix:** Give `send` a default `AbortSignal.timeout(...)` (longer for imports and uploads) combined with an optional caller signal, and let `get` accept a signal so data hooks can abort on unmount or when their inputs change.

**What the fix could break:** Too short a timeout would fail slow but valid requests (CSV imports, tax packet); the GET cache shares one in-flight promise per path, so aborting must not cancel a request another caller is waiting on.

### L51. Preference saves are untyped on the frontend, so a misspelt or unknown key compiles and is silently dropped by the server.

*Maintainability · plausible*

The preference payload is the one write in the app with no TypeScript shape: callers in SettingsPage and TasksPage pass object literals that the compiler cannot check. Pydantic's default is to ignore unknown fields, so a typo such as `exam_bufer_hours` returns 200, the page reports success, and nothing is stored. The read type has also drifted from the backend model, so values like `use_estimate_ratio` are read through the index signature as `unknown`.

**Files affected:**
- `frontend/src/services -> [currentUserClient.ts]`
- `frontend/src/pages -> [SettingsPage.tsx, TasksPage.tsx]`
- `backend/app/Users/schemas -> [user.py]`

**Evidence:** Application/frontend/src/services/currentUserClient.ts:67 -- `export function updatePreferences(userId: string, preferences: Record<string, unknown>)`; `CurrentUser.preferences` declares 11 fields plus `[key: string]: unknown`, while backend `UserPreferences` has 17 (currency, week_start, theme, date_format, time_format, default_reminder_minutes_before, use_estimate_ratio are missing) and `UserPreferencesPatch` declares no `extra="forbid"`.

**Suggested fix:** Declare a `PreferencesPatch` type mirroring `UserPreferencesPatch` (all optional) and use it for `updatePreferences`; declare the missing read fields and drop the index signature; optionally set `extra="forbid"` on the patch model so unknown keys 422.

**What the fix could break:** Forbidding extras on the server would reject any client still sending a removed or misspelt key; check every caller first.

### L52. The user fetch in AuthProvider has no stale-response guard, so a slow answer can restore a user after sign-out or a token swap.

*Integrity · plausible*

If the token changes while `users/me` is in flight (sign out right after opening the app, or `login` with the replacement token from a password change), the earlier request still resolves and calls `setUser` with the previous answer. After a sign-out that leaves `user` populated with `token` null: `isAuthenticated` stays false, but `setClockZone` keeps the previous user's zone and anything reading `user` directly sees the old account until the next change. Rare, but it is the shared-computer case the logout comment worries about.

**Files affected:** `frontend/src/app/auth -> [AuthContext.tsx]`

**Evidence:** Application/frontend/src/app/auth/AuthContext.tsx:54-62 -- the `[token]` effect calls `getCurrentUser().then(setUser)` with no cleanup or `cancelled` flag; `logout` sets token and user to null while that request may still be pending.

**Suggested fix:** Return a cleanup from the effect that sets a `cancelled` flag (or compare the token captured at request time with the current one) and skip `setUser`/`setToken` when stale.

**What the fix could break:** None expected; behaviour only changes for superseded requests.

### L53. `formatMoney` and `formatPercent` choose the minus sign before rounding, so a value that rounds to zero can read as −$0.00 or −0.0%.

*Integrity · plausible*

Any amount in (-0.005, 0) prints as "−$0.00" and any percent in (-0.05, 0) as "−0.0%". Server figures are already rounded to cents, but the client subtracts and sums them (left to spend, allocation totals, chart nets), and float residue such as -1e-15 then shows a minus sign in front of nothing. The backend's `money()` guards exactly this case for -0.0, and the `whole` branch here already rounds before choosing the sign, so the two paths disagree.

**Files affected:**
- `frontend/src/features/budget -> [money.ts]`
- `frontend/src/pages -> [Dashboard.tsx]`
- `frontend/src/features/budget/components -> [AddMoneyModal.tsx]`

**Evidence:** Application/frontend/src/features/budget/money.ts:23-24 -- `return `${amount < 0 ? "−" : ""}$${formatted}`` where `formatted` is `Math.abs(amount).toLocaleString(... maximumFractionDigits: 2)`; only the `whole` option rounds first (`if (options.whole) amount = Math.round(amount)`). formatPercent does the same with `toFixed(1)`. Callers format client-side arithmetic such as `budget.total_planned - budget.total_actual` (Dashboard.tsx:182).

**Suggested fix:** Round to the displayed precision first (cents, or one decimal for percents) and choose the sign from the rounded value, for every option, not only `whole`.

**What the fix could break:** Display only; snapshot or text-matching tests that expect the current output for tiny negatives would change.

### L54. A browser keeps receiving a student's reminders after their session ends any way other than Sign out (tab closed, token expired, 401).

*Security · plausible*

The logout comment states the goal: a shared computer must stop receiving a person's reminders when they sign out. But on a shared or lab computer the usual way a session ends is closing the tab or the 7-day token expiring, and neither unsubscribes, so the OS keeps showing that student's reminder titles to whoever uses the machine next, until they sign in elsewhere and turn it off, or the next user enables push (the server then releases the endpoint). On a personal phone this persistence is the feature, which is why the fix is a design choice rather than one line.

**Files affected:**
- `frontend/src/features/notifications -> [push.ts]`
- `frontend/src/app/auth -> [AuthContext.tsx]`
- `frontend/src/services -> [apiClient.ts]`
- `backend/app/Notifications/services -> [push_service.py]`

**Evidence:** Application/frontend/src/features/notifications/push.ts:98 -- `forgetThisDevice` (the local unsubscribe) is called only from AuthContext `logout` (AuthContext.tsx:65); apiClient's 401 branch (apiClient.ts:101-105) and AuthContext's failed-load branch clear the token without it. The token lives in sessionStorage, so closing the tab also ends the session silently. push_service `_payload` sends `"title": reminder.title, "body": course_code or "Reminder"`.

**Suggested fix:** Say next to the toggle that this device keeps receiving reminders until Sign out; on sign-in, if the browser holds a subscription the server says belongs to another account, unsubscribe it (or offer to take it over); consider unsubscribing in the 401 handler when the token was not merely expired.

**What the fix could break:** Clearing on every session end would stop push on personal devices after each tab close or weekly token expiry, defeating the feature; any change needs to separate the shared-device case from the personal one.

### L55. The 'permanent deletes ask first' test cannot see eleven destructive api functions, because it only matches `export async function delete|clear…`.

*Maintainability · plausible*

The sweep exists because ten delete paths once shipped with no confirmation, and it is the only guard against that regressing. It silently ignores any destructive call declared without `async`, as an arrow const, or named remove/end/leave/revoke, which covers the whole of Applications, Partners and Teams. Every one of those sites does confirm today (DeleteConfirmModal in ApplicationModal and SeasonsModal, the inline 'Yes, delete / Keep' and 'End it?' pairs in FitnessPage and PartnersPanel), but a new or refactored site there would pass the test while deleting on one click.

**Files affected:**
- `frontend/src/features -> [deleteConfirmations.test.ts]`
- `frontend/src/features/jobs/applications -> [api.ts]`
- `frontend/src/features/partners -> [api.ts]`
- `frontend/src/features/teams -> [api.ts]`

**Evidence:** Application/frontend/src/features/deleteConfirmations.test.ts -- `.match(/export async function (delete|clear)[A-Za-z]+/g)`; jobs/applications/api.ts declares `export function deleteSeason`, `deleteApplication`, `deleteStep` (no `async`); partners/api.ts `export function revokeInvite`, `endPartnership`; teams/api.ts `export const removeTeam = ...`, `removeGame`, `removeTeamMember`, `leaveTeam`, `cancelTeamLink`.

**Suggested fix:** Derive the destructive list from what the function does (any export whose body calls `del`) rather than from its declaration form and name, or adopt one declaration convention for api modules and assert it; add a control asserting `deleteSeason` and `removeGame` are in the list.

**What the fix could break:** Widening the list will flag sites whose confirmation the test cannot recognise (e.g. revoking an invite, which is deliberately one click); those need an explicit RECOVERABLE entry.

### L56. API modules follow three different conventions for paths, declarations and types, with no rule saying which is current.

*Maintainability · plausible*

`services/endpoints.ts` was meant to be the one map of API paths, and Ideas/design/README.md describes `features/<area>/api.ts, types.ts`, but newer modules skip both. A path changed on the server must now be hunted in two styles, a reader cannot tell which convention to copy, and the declaration style matters to tooling: the delete-confirmation test only recognises `export async function`. Small today, but it compounds with every contributor who copies the nearest file.

**Files affected:**
- `frontend/src/services -> [endpoints.ts]`
- `frontend/src/features/jobs -> [api.ts]`
- `frontend/src/features/jobs/applications -> [api.ts]`
- `frontend/src/features/partners -> [api.ts]`
- `frontend/src/features/teams -> [api.ts]`

**Evidence:** Application/frontend/src/features/teams/api.ts:66 -- `export const fetchTeams = (userId: string) => get<TeamSummary[]>(`teams/${userId}`);` with its interfaces declared in api.ts; partners/api.ts and applications/api.ts build paths inline with plain `export function`; jobs/api.ts uses `endpoints.jobs.*` except `fetchShiftConflicts` (`jobs/${userId}/shift-conflicts`) and `fetchTaxPacket`; budget/api.ts is `export async function` over `endpoints.finances.*`. endpoints.ts also has one PascalCase key, `grades.CategoryWeights`.

**Suggested fix:** Pick one convention (paths in endpoints.ts, `export async function`, types in types.ts), move teams' types to features/teams/types.ts, convert the inline paths, and note the rule in Ideas/design/README.md or a lint rule.

**What the fix could break:** Mechanical but touches imports across Fitness, Applications, Partners and Invite pages; behaviour should not change.

### L57. 'Balance over time' spaces its points evenly by index, not by date, so long quiet stretches and busy weeks look the same width.

*Readability · plausible*

The chart is labelled as a time series and its axis prints the first and last dates, but the horizontal position is the point's ordinal. Ten transactions in one week and a three-month gap before them take the same space, so the slope a reader sees is not a rate over time and a long period without movement (a savings account left alone) is invisible. It also means the chart's shape changes when an unrelated small transaction is added.

**Files affected:** `frontend/src/features/budget/components -> [AccountBalanceChart.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/AccountBalanceChart.tsx:49-50 -- `const x = (index: number) => PAD.left + (points.length === 1 ? INNER_W / 2 : (index / (points.length - 1)) * INNER_W);` over `balance_history`, which has one point per day with movement only.

**Suggested fix:** Position points by day (days since the first point over the total span), and draw the balance as a step line since it only changes on movement days.

**What the fix could break:** Dense months will crowd; the per-point dots may need thinning for long histories.

### L58. A deposit can be submitted with the split computed for a previous amount, which the server then rejects with a validation error.

*Reliability · plausible*

Typing a new amount and pressing Enter within the 300 ms debounce, or before the preview answers, sends the new amount with the old split. DepositCreate's validator requires the allocations to total the amount to the cent, so the user gets a 422 phrased in terms of allocations they never touched. Nothing is written, so no money is corrupted, but it is a confusing failure on the most common money entry for a student with several accounts.

**Files affected:** `frontend/src/features/budget/components -> [AddMoneyModal.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/AddMoneyModal.tsx:119-124 -- `recordDeposit(user.id, { amount: Number(amount), ..., allocations })` where `allocations` comes from `previewDeposit` on `useDebounce(amount, 300)`; the Record button is disabled only while `submitting`, never while the preview is stale, in flight, or hand-edited so that 'Allocated X of Y' does not match.

**Suggested fix:** Disable Record (or recompute synchronously) while the debounced amount differs from the typed one or a preview is pending, and when the hand-edited allocations do not sum to the amount, show the difference and block submission; alternatively send no allocations unless the user edited them.

**What the fix could break:** Slightly slower submit after typing; must not block deposits when the preview call itself fails (empty allocations already mean 'split by share').

### L59. Saving a planned-spend target or category limit, or stopping a standing instruction, fails silently when the server refuses: no message, only an unhandled rejection.

*Reliability · plausible*

Any failure (offline, a 400 from validation, a 5xx) leaves the input open with no explanation; the error surfaces only as an unhandled promise rejection in the console. A student who presses Enter and looks away will believe the target was saved until they notice the figure never changed. The same component's siblings (CategoriesModal, IncomeSplitModal) all show the server's message.

**Files affected:** `frontend/src/features/budget/components -> [PlannedSpend.tsx, BudgetView.tsx, WhereItWent.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/PlannedSpend.tsx:32-39 -- `async function commit(accountId) { setSaving(true); try { await onSetTarget(...); setEditing(null); } finally { setSaving(false); } }`, called as `onKeyDown={... if (event.key === "Enter") commit(entry.account_id); }` and `onClick={() => commit(entry.account_id)}` with no catch; BudgetView's `handleSetTarget` rethrows whatever `setBudgetTarget` throws. WhereItWent.tsx's `commit` (limits on an account's page) has the same try/finally with no catch, called as `if (event.key === "Enter") commit(id!)`. BudgetView.tsx `handleStopRule` (try/finally, no catch) is called as `void handleStopRule(stoppingRule)` from the confirm dialog, so a failed stop closes the dialog and says nothing.

**Suggested fix:** Catch in `commit`, keep the field open and show the message beside it (as the other budget editors do with `getErrorMessage`).

**What the fix could break:** None; display only.

### L60. Four budget dialogs re-seed their form whenever the parent's accounts or categories array is rebuilt, wiping half-typed input: the AddMoneyModal fix was not applied to its siblings.

*Reliability · plausible*

`useBudget` rebuilds its arrays on every reload, and reloads happen in the background: `useApiRefresh` re-reads after any cache refresh notice, and other panels' writes reload the page. Each of these dialogs then resets to the server's values or to a blank form while the student is typing, with nothing on screen saying why. The bug was found and fixed once (old audit #37) in AddMoneyModal, but the four look-alike dialogs kept the old dependency list.

**Files affected:** `frontend/src/features/budget/components -> [RecurringModal.tsx, SinkingFundModal.tsx, IncomeSplitModal.tsx, CategoriesModal.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/RecurringModal.tsx:93 -- `useEffect(() => { setForm(formFor(rule, accounts)); setError(null); }, [rule, accounts, open]);`; SinkingFundModal.tsx:52 `}, [open, accounts]);` resetting to `blank(accounts)`; IncomeSplitModal.tsx:38 and CategoriesModal.tsx:40 likewise on `accounts` / `categories`. AddMoneyModal.tsx and RecordSpendModal.tsx carry comments explaining that exactly this dependency 'wiped whatever was half-typed' and now depend on `open` alone.

**Suggested fix:** Seed on open (and on a change of the edited record's id) only, as AddMoneyModal does; derive defaults that need the account list inside the open transition or with functional updates that keep existing choices.

**What the fix could break:** A dialog left open across a genuine change (an account deleted elsewhere) would keep a stale selection; the server already rejects unknown ids.

### L61. Many panels still refetch on the whole `user` object, so every Settings save (which rebuilds `user`) reloads them, the fix of old audit #34 applied only to the main hooks.

*Scalability · plausible*

AuthContext's `refreshUser` replaces `user` after any profile or preference change, so every effect keyed on the object re-runs its fetch even though the id is unchanged. On Settings that is three reloads per save, and anywhere these panels are mounted alongside, the same. Harmless at today's scale but it multiplies requests per user action, and it reintroduces the out-of-order-answer window the tickets were written for.

**Files affected:**
- `frontend/src/features/budget/components -> [SinkingFunds.tsx, Subscriptions.tsx, TermBudget.tsx]`
- `frontend/src/features/jobs/components -> [PaychequeModal.tsx]`
- `frontend/src/features/omnibox -> [Omnibox.tsx]`
- `frontend/src/pages -> [SettingsPage.tsx, FitnessPage.tsx, CalendarPage.tsx, TasksPage.tsx]`
- `frontend/src/pages/budget -> [AccountDetailPage.tsx]`

**Evidence:** Application/frontend/src/features/budget/components/TermBudget.tsx:36 -- `}, [user, nonce]);` (also SinkingFunds.tsx:48, Subscriptions.tsx:47, SettingsPage.tsx:180/203/220, FitnessPage.tsx:41, CalendarPage.tsx:72, TasksPage.tsx:93/106/119, pages/budget/AccountDetailPage.tsx:43, PaychequeModal.tsx:99, Omnibox.tsx:80), while useBudget, useJobs and useAccountActivity carry the comment 'The id, not the object. `refreshUser()` builds a fresh `user` every time'.

**Suggested fix:** Depend on `user?.id` (and on the specific preference read, where one matters) as the main hooks already do; a lint rule or the shared data hook would stop it recurring.

**What the fix could break:** An effect that genuinely needs a fresh preference (e.g. timezone) must list that field explicitly or it will stop updating.

### L62. Saving any one Settings tab re-seeds every field from the server, silently discarding unsaved edits on the other tabs.

*Reliability · plausible*

Fields live at page level precisely so that switching tabs keeps unsaved typing, and a test pins that. But the re-seed effect runs on every new `user` object, so changing the study window on Calendar, switching to Academic and saving there (or picking a cash-tip account on Financial, or changing the password) resets the Calendar fields to their stored values with no message. The student believes their study window was kept until they notice the free blocks did not change.

**Files affected:**
- `frontend/src/pages -> [SettingsPage.tsx]`
- `frontend/src/app/auth -> [AuthContext.tsx]`

**Evidence:** Application/frontend/src/pages/SettingsPage.tsx:166-184 -- `useEffect(() => { if (!user) return; setSchoolYear(...); ... setStudyStart(...); ... setZone(...); setColors(...); setTipAccount(...); }, [user]);` while each save ends with `await refreshUser();` (lines 256, 294, 346), which replaces `user`; the tab doc says unsaved typing 'survives a tab switch for free -- which is the agreed behaviour'.

**Suggested fix:** Seed once when the user first arrives (key on `user?.id`), and after a save update only the fields that tab owns; or track dirty fields and skip them when re-seeding.

**What the fix could break:** Fields must still pick up values changed elsewhere (another device) on a fresh visit; seeding on id change keeps that.

### L63. SettingsPage is a ~1,000-line single component with 38 state variables, a duplicated data load and a two-request save reported as one.

*Maintainability · plausible*

Three tabs, the password form, notifications, tips and account counting all share one component's state and one render function, so any change risks the cross-tab reset above and makes the page hard to test in parts. The two-step academic save is not atomic but presents itself as one saved state; a partial failure tells the student nothing was saved when the term was.

**Files affected:** `frontend/src/pages -> [SettingsPage.tsx]`

**Evidence:** Application/frontend/src/pages/SettingsPage.tsx -- 996 lines, 38 `useState` calls in one function; `loadMoneyBits` (line 154) and the effect at line 189 each fetch accounts and categories with the same `Promise.all`; `handleAcademicSubmit` awaits `updateAcademicStatus` then `updatePreferences`, so a failure of the second leaves the first saved while the page says 'Could not save your settings'.

**Suggested fix:** Split each tab into its own component owning its fields and save handler; reuse `loadMoneyBits` in the effect; report a partial academic save precisely (or add one endpoint that saves term and targets together).

**What the fix could break:** The tab-switch behaviour test depends on state living above the tabs; lifting per-tab state into children needs keep-mounted tabs or a shared store to preserve it.

### L64. Names and layout disagree with the modules they hold: `features/calender`, `paycheck_service.py` beside `paycheque_service.py`, route files named for URLs rather than modules, the Teams module behind the Fitness page, and the Finances module behind the Budget page.

*Maintainability · verified*

Each mismatch is small and documented somewhere in Ideas/, but together they make the codebase harder to navigate than its clean layering deserves: a new contributor grepping for 'calendar' misses the frontend feature, opens the wrong one of two near-identical paycheque files, and cannot find a module's routes by its name. This pass had to carry a glossary entry for each. The cost of renaming grows with every branch and contributor added, so the cheapest time is now.

**Files affected:**
- `frontend/src/features/calender -> [api.ts]`
- `backend/app/Jobs/services -> [paycheck_service.py, paycheque_service.py]`
- `backend/app/api/routes -> [applications.py, recurring.py, push.py, shared_tasks.py, shared_events.py]`
- `backend/app/Grades/services -> [dash_services.py]`
- `frontend/src/pages -> [FitnessPage.tsx]`

**Evidence:** Application/frontend/src/features/calender/ -- 26 files under the misspelt folder (Ideas/design/calendar.md: 'a known follow-up'); Application/backend/app/Jobs/services/paycheck_service.py (the cheque check) beside paycheque_service.py (the records); Application/backend/app/api/routes/applications.py serves Jobs, recurring.py serves Finances, push.py serves Notifications, shared_tasks.py and shared_events.py serve Tasks and Calendar; Application/frontend/src/pages/FitnessPage.tsx is the page for app/Teams; Application/backend/app/Grades/services/dash_services.py is the only plural service module.

**Suggested fix:** In one dedicated commit with nothing else in it: rename `features/calender` to `features/calendar`, `paycheck_service.py` to something like `cheque_check.py`, and `dash_services.py` to `dashboard_service.py`; either rename route files to their module (`jobs_applications.py`, `finances_recurring.py`) or add a route-to-module table to the design README; note the page-to-module names (Budget/Finances, Fitness/Teams) in the same table.

**What the fix could break:** Import and path churn across many files; open branches will conflict; tests that read files by path (styles tests, kindColors) need their paths updated in the same commit.

### L65. Backend dependencies are only half pinned: transitive versions float on every image build, `cryptography` and `requests` are imported directly but undeclared, test tools ship in the production image, and nothing watches for updates.

*Maintainability · verified*

Pinning direct dependencies was a real improvement over the old `pip freeze`, but every Docker build still resolves the transitive set fresh, so two deploys of the same commit can run different starlette, pydantic-core or cryptography versions, and a breaking release upstream surfaces as a production failure with no code change to blame. Web-push encryption depends on `cryptography` only because google-auth happens to require it today. Test tools in the production image are dead weight and attack surface. With nothing proposing updates, security fixes in these packages arrive only when someone remembers.

**Files affected:**
- `backend -> [requirements.txt, Dockerfile]`
- `backend/app/Notifications/services -> [webpush.py, push_service.py]`
- `frontend -> [package.json]`

**Evidence:** Application/backend/requirements.txt -- 'Only direct dependencies are listed. pip resolves the rest', and pytest==9.1.1 and httpx==0.28.1 sit in the same file; Application/backend/Dockerfile:10 -- `RUN pip install --no-cache-dir -r requirements.txt`; Application/backend/app/Notifications/services/webpush.py:20-22 import `cryptography` and push_service.py:53 `import requests`, neither declared (they arrive through google-auth); no .github/dependabot.yml. Application/frontend/package.json uses ranges such as `"react": "^19.x"`, held in place only by package-lock.json.

**Suggested fix:** Keep a `requirements.in` of direct dependencies and compile a hashed lock (pip-tools or uv) that the Dockerfile installs; declare `cryptography` and `requests`; move pytest and httpx to `requirements-dev.txt` used by CI and dev.run.sh; enable Dependabot for pip, npm and GitHub Actions.

**What the fix could break:** The first lock freezes today's resolved versions (no behaviour change); dev.run.sh and CI must install the dev file; Dependabot will open PRs that need the owner's review rhythm.

---

## Cosmetic

### CO1. Dead declarations read as live API: unused schema classes (TokenPayload, three academic-status models), four uncalled frontend API wrappers, and five unused interfaces in grades/types.ts.

*Maintainability · plausible*

Unused code that looks authoritative misleads a contributor: `TokenPayload` suggests a token shape the app does not decode, `AcademicStatus` describes a stored record when the status lives on the users row, `UserDetail` in grades/types.ts describes an endpoint the app no longer has, and `recordGrade`, `fetchCourseCategoryWeights`, `updateCategoryWeights` and `skipRepeating` wrap routes the client no longer calls. Nothing detects dead code today (see the CI finding). The API-client import of `ValidationError` from grades/types is covered by the app-wide-code finding.

**Files affected:**
- `backend/app/Auth/schemas -> [token.py]`
- `backend/app/Users/schemas -> [academic_status.py]`
- `frontend/src/features/grades -> [api.ts, types.ts]`
- `frontend/src/features/tasks -> [api.ts]`
- `frontend/src/services -> [apiClient.ts]`

**Evidence:** Application/backend/app/Auth/schemas/token.py -- `class TokenPayload(BaseModel)` has no reference in app/, scripts/ or tests/ (session_service decodes tokens into its own TokenClaims); in academic_status.py only `AcademicStatusUpdate` is imported anywhere, leaving `AcademicStatusBase`, `AcademicStatusCreate` and `AcademicStatus` (with a v1 `class Config` and a uuid4 default id for a record that does not exist) unused. Also: Application/frontend/src/features/grades/api.ts:48 `fetchCourseCategoryWeights`, :55 `updateCategoryWeights`, :98 `recordGrade`; Application/frontend/src/features/tasks/api.ts:180 `skipRepeating` -- `grep -rlw` finds each name only in its own file. Also: Application/frontend/src/features/grades/types.ts:289-329 -- `HTTPValidationError`, `User`, `UserCreate`, `UserDetail` and `UserUpdate` have no importer anywhere in src; services/apiClient.ts:1 -- `import { ValidationError } from "../features/grades/types"; // adjust path to wherever these live`.

**Suggested fix:** Delete the unused backend models and the five frontend interfaces and four wrappers; consider retiring the backend routes the wrappers covered if nothing else calls them.

**What the fix could break:** None at runtime; removing backend routes would break any external script that uses them.

### CO2. Money helpers the design notes say must live only in app/shared are copied: a private `_money` in the tax packet, and `money_text` twice.

*Maintainability · plausible*

Ideas/design/README.md records that money() and today() once existed thirteen times and says 'Do not write a local money()'. The tax packet's copy will drift the moment the shared one changes (its own docstring mentions a planned change to where `+ 0.0` sits), and the two money_text copies are the start of the same pattern for formatting.

**Files affected:**
- `backend/app/Jobs/services -> [tax_packet_service.py, paycheck_service.py]`
- `backend/app/Finances/services -> [forecast_service.py]`

**Evidence:** Jobs/services/tax_packet_service.py:43 -- `def _money(value): return round(value + 0.0, 2)`, byte-identical to shared/money.money; `def money_text(amount): return f"${amount:,.2f}"` at Jobs/services/paycheck_service.py:210 and Finances/services/forecast_service.py:691 (plan_service imports forecast's copy).

**Suggested fix:** Import money from app/shared/money.py in the tax packet, and move money_text there too.

**What the fix could break:** None.

### CO3. errors.py carries unused entries and a key named for 409 that documents a 400.

*Readability · plausible*

The module is the single source of client-visible messages, so dead keys and a misleading key name invite a contributor to document the wrong status or to keep an unused message in step with code it no longer describes.

**Files affected:** `backend/app/shared -> [errors.py]`

**Evidence:** Application/backend/app/shared/errors.py:66 -- `"auth_409": {400: {...error_user["already_exists"]}}`; `responses["course_400"]`, `responses["grade_404"]`, `responses["grade_400"]` and `error_course["invalid_average"]` are referenced nowhere in app/.

**Suggested fix:** Delete the unused entries and rename `auth_409` to `auth_400` (or `register_400`) together with its one caller in routes/auth.py.

**What the fix could break:** None at runtime; the rename touches one route decorator.

### CO4. `calender/api.ts` declares a module-level function named `window`, shadowing the browser global throughout the module.

*Readability · plausible*

Inside this module `window` is a query-string helper, so any later code here that reaches for `window.location` or `window.setTimeout` gets a TypeScript error at best and a confusing one; the sibling sharing modules build invite links from `window.location.origin`, so the pattern is one paste away. The same query is also spelled out inline in `fetchAgenda` two functions earlier.

**Files affected:** `frontend/src/features/calender -> [api.ts]`

**Evidence:** Application/frontend/src/features/calender/api.ts:66 -- `function window(start: string, end: string) { return `?start=${start}&end=${end}`; }`

**Suggested fix:** Rename it to `windowQuery` (or `rangeQuery`) and use it in `fetchAgenda` too.

**What the fix could break:** None; module-private.

### CO5. Task sharing and event sharing are two hand-kept copies of one client: duplicate owner-view types, accept-status unions, invite-link builders and preview/accept calls.

*Maintainability · plausible*

The shared panel was extracted, but the API layer under it was copied per feature, so the two halves already differ (one reuses `Sharing`, the other redeclares it). A change to the owner view (say, adding `link.created_at`) or to the invite-link format has to be made in both modules and in the invite page that parses the prefixes, with the compiler unable to point out the second copy because the types are structurally separate.

**Files affected:**
- `frontend/src/features/tasks -> [sharing.ts]`
- `frontend/src/features/calender -> [sharing.ts]`
- `frontend/src/shared/components -> [SharingSection.tsx]`

**Evidence:** Application/frontend/src/features/tasks/sharing.ts:10 -- `TaskSharing` restates `Sharing` from shared/components/SharingSection.tsx field for field (calender/sharing.ts imports `Sharing` instead); `TaskAcceptStatus` and `EventAcceptStatus` are the same union; `taskInviteLink` and `eventInviteLink` differ only in the `task:`/`event:` prefix the invite page parses.

**Suggested fix:** Have tasks/sharing.ts use `Sharing` from the shared component, and build both modules' link and accept helpers from one small factory keyed by the path segment and link prefix.

**What the fix could break:** None for users; type-level change plus a small helper.

### CO6. `JobCard`'s `hours` prop and JobsPage's `hoursByJob` carry minutes, converted only inside the card.

*Readability · plausible*

The value is minutes end to end but is named hours at both the call site and the prop. Anyone reusing the prop, or adding a 'more than 20 hours' warning, will compare minutes against hours and be off by sixty.

**Files affected:**
- `frontend/src/features/jobs/components -> [JobCard.tsx]`
- `frontend/src/pages -> [JobsPage.tsx]`

**Evidence:** Application/frontend/src/pages/JobsPage.tsx:81 -- `const hoursByJob = useMemo(() => upcomingMinutesByJob(shifts, today()), [shifts]);` passed as `hours={hoursByJob.get(job.id) ?? 0}`; JobCard renders `trimHours(hours)` where `function trimHours(minutes: number)` divides by 60.

**Suggested fix:** Rename to `minutes` / `minutesByJob`.

**What the fix could break:** None; rename only.

### CO7. Doc comments inside function bodies sit above the wrong code, so they describe a neighbour.

*Readability · plausible*

Editors attach a JSDoc to the next declaration, so hovering `handleCounted` shows the tip-account text and `handleTipAccount` shows nothing; readers of useBudget meet a description of refs where a refresh subscription is. These were left alone by the documentation pass because they are inside function bodies.

**Files affected:**
- `frontend/src/pages -> [SettingsPage.tsx]`
- `frontend/src/features/budget/hooks -> [useBudget.ts]`

**Evidence:** Application/frontend/src/pages/SettingsPage.tsx:310-314 -- the JSDoc 'Choose where cash tips go. Saves on change...' is immediately followed by a second JSDoc and `async function handleCounted`, while `handleTipAccount` has none; useBudget.ts:175-178 -- the comment 'Which month the summary currently holds, and which user has had its first load. Both are refs...' sits above `useApiRefresh(load);`, with the refs it describes two lines further down.

**Suggested fix:** Move each comment above the code it describes.

**What the fix could break:** None.

---

## Timeline

**2026-10-28:** audit opened alongside the total redocumentation of the backend and
frontend (branch `redoc`): every module, class and function rewritten in the new
docstring format, checked to change documentation only.

| Issue | Found | Started | Fixed | Main file of the fix | Unexpected consequences |
|---|---|---|---|---|---|
| C1 | 2026-10-28 | — | — | — | — |
| H1 | 2026-10-28 | — | — | — | — |
| H2 | 2026-10-28 | — | — | — | — |
| H3 | 2026-10-28 | — | — | — | — |
| H4 | 2026-10-28 | — | — | — | — |
| H5 | 2026-10-28 | — | — | — | — |
| H6 | 2026-10-28 | — | — | — | — |
| H7 | 2026-10-28 | — | — | — | — |
| H8 | 2026-10-28 | — | — | — | — |
| H9 | 2026-10-28 | — | — | — | — |
| M1 | 2026-10-28 | — | — | — | — |
| M2 | 2026-10-28 | — | — | — | — |
| M3 | 2026-10-28 | — | — | — | — |
| M4 | 2026-10-28 | — | — | — | — |
| M5 | 2026-10-28 | — | — | — | — |
| M6 | 2026-10-28 | — | — | — | — |
| M7 | 2026-10-28 | — | — | — | — |
| M8 | 2026-10-28 | — | — | — | — |
| M9 | 2026-10-28 | — | — | — | — |
| M10 | 2026-10-28 | — | — | — | — |
| M11 | 2026-10-28 | — | — | — | — |
| M12 | 2026-10-28 | — | — | — | — |
| M13 | 2026-10-28 | — | — | — | — |
| M14 | 2026-10-28 | — | — | — | — |
| M15 | 2026-10-28 | — | — | — | — |
| M16 | 2026-10-28 | — | — | — | — |
| M17 | 2026-10-28 | — | — | — | — |
| M18 | 2026-10-28 | — | — | — | — |
| M19 | 2026-10-28 | — | — | — | — |
| M20 | 2026-10-28 | — | — | — | — |
| M21 | 2026-10-28 | — | — | — | — |
| M22 | 2026-10-28 | — | — | — | — |
| M23 | 2026-10-28 | — | — | — | — |
| M24 | 2026-10-28 | — | — | — | — |
| M25 | 2026-10-28 | — | — | — | — |
| M26 | 2026-10-28 | — | — | — | — |
| M27 | 2026-10-28 | — | — | — | — |
| M28 | 2026-10-28 | — | — | — | — |
| L1 | 2026-10-28 | — | — | — | — |
| L2 | 2026-10-28 | — | — | — | — |
| L3 | 2026-10-28 | — | — | — | — |
| L4 | 2026-10-28 | — | — | — | — |
| L5 | 2026-10-28 | — | — | — | — |
| L6 | 2026-10-28 | — | — | — | — |
| L7 | 2026-10-28 | — | — | — | — |
| L8 | 2026-10-28 | — | — | — | — |
| L9 | 2026-10-28 | — | — | — | — |
| L10 | 2026-10-28 | — | — | — | — |
| L11 | 2026-10-28 | — | — | — | — |
| L12 | 2026-10-28 | — | — | — | — |
| L13 | 2026-10-28 | — | — | — | — |
| L14 | 2026-10-28 | — | — | — | — |
| L15 | 2026-10-28 | — | — | — | — |
| L16 | 2026-10-28 | — | — | — | — |
| L17 | 2026-10-28 | — | — | — | — |
| L18 | 2026-10-28 | — | — | — | — |
| L19 | 2026-10-28 | — | — | — | — |
| L20 | 2026-10-28 | — | — | — | — |
| L21 | 2026-10-28 | — | — | — | — |
| L22 | 2026-10-28 | — | — | — | — |
| L23 | 2026-10-28 | — | — | — | — |
| L24 | 2026-10-28 | — | — | — | — |
| L25 | 2026-10-28 | — | — | — | — |
| L26 | 2026-10-28 | — | — | — | — |
| L27 | 2026-10-28 | — | — | — | — |
| L28 | 2026-10-28 | — | — | — | — |
| L29 | 2026-10-28 | — | — | — | — |
| L30 | 2026-10-28 | — | — | — | — |
| L31 | 2026-10-28 | — | — | — | — |
| L32 | 2026-10-28 | — | — | — | — |
| L33 | 2026-10-28 | — | — | — | — |
| L34 | 2026-10-28 | — | — | — | — |
| L35 | 2026-10-28 | — | — | — | — |
| L36 | 2026-10-28 | — | — | — | — |
| L37 | 2026-10-28 | — | — | — | — |
| L38 | 2026-10-28 | — | — | — | — |
| L39 | 2026-10-28 | — | — | — | — |
| L40 | 2026-10-28 | — | — | — | — |
| L41 | 2026-10-28 | — | — | — | — |
| L42 | 2026-10-28 | — | — | — | — |
| L43 | 2026-10-28 | — | — | — | — |
| L44 | 2026-10-28 | — | — | — | — |
| L45 | 2026-10-28 | — | — | — | — |
| L46 | 2026-10-28 | — | — | — | — |
| L47 | 2026-10-28 | — | — | — | — |
| L48 | 2026-10-28 | — | — | — | — |
| L49 | 2026-10-28 | — | — | — | — |
| L50 | 2026-10-28 | — | — | — | — |
| L51 | 2026-10-28 | — | — | — | — |
| L52 | 2026-10-28 | — | — | — | — |
| L53 | 2026-10-28 | — | — | — | — |
| L54 | 2026-10-28 | — | — | — | — |
| L55 | 2026-10-28 | — | — | — | — |
| L56 | 2026-10-28 | — | — | — | — |
| L57 | 2026-10-28 | — | — | — | — |
| L58 | 2026-10-28 | — | — | — | — |
| L59 | 2026-10-28 | — | — | — | — |
| L60 | 2026-10-28 | — | — | — | — |
| L61 | 2026-10-28 | — | — | — | — |
| L62 | 2026-10-28 | — | — | — | — |
| L63 | 2026-10-28 | — | — | — | — |
| L64 | 2026-10-28 | — | — | — | — |
| L65 | 2026-10-28 | — | — | — | — |
| CO1 | 2026-10-28 | — | — | — | — |
| CO2 | 2026-10-28 | — | — | — | — |
| CO3 | 2026-10-28 | — | — | — | — |
| CO4 | 2026-10-28 | — | — | — | — |
| CO5 | 2026-10-28 | — | — | — | — |
| CO6 | 2026-10-28 | — | — | — | — |
| CO7 | 2026-10-28 | — | — | — | — |

---

## In progress

### Critical

_None._

### High

_None._

### Medium

_None._

### Low

_None._

### Cosmetic

_None._

---

## Completed

### Critical

_None._

### High

_None._

### Medium

_None._

### Low

_None._

### Cosmetic

_None._
