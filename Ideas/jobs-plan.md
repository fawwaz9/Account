# Jobs: what you work, what it earns, and what actually arrives

## Context

A new module beside Grades, Finances, Calendar and Tasks, for students working
one or several jobs. It answers three questions the app cannot answer today:
*when am I working*, *what am I earning*, and *did the cheque match the hours*.

It is deliberately two-faced. **Time** goes to the Calendar, so a shift competes
with lectures for the same hours and the existing free-block and week-load
machinery sees it. **Money** goes to the Budget, but only at the point a
paycheque arrives — every earnings figure, rate and analysis lives on the Jobs
page, and the ledger stays a record of money that actually moved.

**Decisions taken:** shifts are scheduled then confirmed, with an unconfirmed
past shift counting at its scheduled hours and marked as assumed; a job is
hourly, salaried or contract, each with its own expected-pay rule; a paycheque
records gross and named deductions and sends only the net to the ledger, split
across accounts by income share; shifts are a new `EventKind` on the existing
events table; a paycheque covers a pay period and is reconciled against the
shifts in it; tips are marked cash or on-cheque and only cash may reach the
ledger; delivered in three stages.

---

## What already exists, and is being reused rather than rebuilt

| Existing | Where | Used for |
|---|---|---|
| The recurrence engine and `recur_*` columns | `Calendar/utils/recurrence.py`, `rule_columns.py` | a repeating shift, at **no cost** — events already carry the rule |
| `list_occurrences` | `Calendar/services/event_service.py` | shifts expand on read like every other event |
| `free_blocks` | `Calendar/services/load_service.py` | already subtracts any timed occurrence, so shifts reduce study time with no change |
| `CRUNCH_WEIGHTS.get(kind, 0)` + `if weight == 0: continue` | `load_service.py:214` | a shift scores 0 and drops out of the crunch radar **automatically** — correct, it is commitment, not academic pressure |
| Blackout scoping (`event.course_id is not None`) | `blackout_service.py` | reading break already cannot touch a shift |
| `split_income` / `DepositCreate` | `Finances/services/deposit_service.py` | the net paycheque splitting across accounts |
| `tuition_payments` + `tuition_deductions` | `_database/models.py`, `tuition_service.py` | **the structural precedent**: own table, named deductions, only the net reaches the ledger |
| `term_span(courses)` | `Finances/services/tuition_service.py` | "earned this term" measured over the term's own dates |
| `week_load` | `load_service.py` | hours against class time |
| `trimNumber`, `formatMoney`, `duration()` | `shared/utils/`, `budget/money.ts` | every figure on the page |

---

## Data model

Four new tables, one new column, one new enum member.

### `jobs`
`id`, `user_id`, `name`, `employer`, `kind` (`hourly` | `salaried` | `contract`),
`hourly_rate` (hourly only), `period_amount` (salaried only), `started_on`,
`ended_on` (null while current), `archived`, `position`.

Pay timing reuses the engine rather than inventing a schedule: `pay_starts_on`
plus the same `recur_*` columns, so "every second Friday" is the rule that
already drives class times and standing payments. That is what makes "next
cheque, and when" a read rather than a new mechanism.

### `events` — one new column
`job_id` (nullable FK), exactly beside the existing `course_id`, plus
`EventKind.SHIFT`. A shift is genuinely a timed block; giving it its own table
would mean teaching the calendar, free blocks and week load about a second
source, the way tasks already have to be merged in.

### `shift_records` — what actually happened on one date
`id`, `user_id`, `event_id`, `on_date`, `worked_start`, `worked_end`,
`confirmed`, `tip_amount`, `tip_is_cash`, `tip_transaction_id` (nullable),
`rate_override` (nullable), `notes`.

Keyed by **`(event_id, on_date)`**, which is the identity the codebase already
documents for an occurrence (`EventOccurrence` has no id of its own). A
recurring shift is one row expanded on read, so this is the only place a single
Friday can be confirmed. A record exists only once there is something to say
about that date — an unconfirmed shift has no row at all.

### `paycheques`
`id`, `user_id`, `job_id`, `group_id`, `occurred_on`, `gross_amount`,
`period_start`, `period_end`, `expected_gross`, `notes`.

`group_id` rather than a single `transaction_id`, because the net **splits**
across accounts and a deposit is already several rows tied by that column. The
service attaches a computed `paycheque_id` onto transactions for display, the
way `tuition_payment_id` is attached today rather than stored.

`expected_gross` is **stored**, for the same reason `credits_counted` is: it is
what the cheque was checked against at the time, and recomputing it later would
silently rewrite the verdict when a shift is edited months afterwards.

### `paycheque_deductions`
`id`, `paycheque_id`, `description`, `amount` (positive; the sign is in the
name). A direct mirror of `tuition_deductions`.

---

## PR 1 — Jobs, and shifts on the calendar

Migration: the four tables via `create_all`, and `events.job_id` +
`recurring`-style columns on `jobs` through `ADDED_COLUMNS`.

- `app/Jobs/` — `schemas/job.py`, `services/job_service.py`, mirroring the
  Grades/Finances module shape.
- `EventKind.SHIFT` added. Touch points the enum forces, each small:
  `EVENT_KIND_LABELS` and the `CLASS_KINDS`/`EXAM_KINDS` tuples in
  `Calendar/schemas/event.py` and `frontend/features/calender/types.ts`; a
  `.calChip-shift` and `.weekBlock.calChip-shift` colour in `calendar.css`.
  `CLASS_KIND_VALUES` in `class_schedule_service.py` must **not** gain it, or
  replacing a course timetable would delete shifts.
- Shift scheduling reuses `ClassScheduleModal`'s shape — a job's weekly pattern
  is the same form as a course's, and per-meeting interval work is already
  planned for that component.
- `shift_records`: confirm worked hours for one date, with the scheduled times
  pre-filled so confirming an ordinary shift is one click.

**Tests** (`tests/test_jobs.py`, `tests/test_shifts.py`): a shift appears in
`list_occurrences`; a shift reduces `free_blocks`; a shift scores zero in
`crunch`; a term blackout does **not** skip a shift; replacing a course
timetable leaves shifts intact; confirming writes one record per date and is
idempotent; an unconfirmed past shift reports as assumed, not missing.

## PR 2 — Paycheques, deductions, and the ledger

- `paycheque_service.py`: `record_paycheque`, `update_paycheque`,
  `delete_paycheque`, each writing or unwinding the deposit through
  `deposit_service.split_income` so the net behaves exactly like any other
  income.
- **Cascade both ways**, tested by mutation: deleting the deposit rows removes
  the paycheque, and deleting the paycheque removes its rows. The orphaned
  tuition payment came from exactly this gap.
- Cash tips write their own income row when recorded; on-cheque tips do not,
  because they are already inside the gross. One `tip_is_cash` flag decides, and
  a test asserts an on-cheque tip is counted once rather than twice.

**Tests** (`tests/test_paycheques.py`): net = gross − deductions; the net splits
by income share and the parts sum to the whole; a deduction never appears as
income; deleting either side removes both; a cash tip reaches the ledger and an
on-cheque tip does not.

## PR 3 — Earnings, and did the cheque match

`app/Jobs/services/earnings_service.py`, one service answering all four figures
over one window, following `load_service.py`'s "one question asked several ways"
shape:

- **Earned this week / month / term**, per job and total, hours beside money.
  Term dates come from `term_span`.
- **Effective hourly rate**: net ÷ hours worked, beside the advertised rate.
  Only computable because gross and deductions are both recorded.
- **Hours against class time**: `WeekLoad` currently sums every timed occurrence
  into one `booked_minutes`. It gains a `work_minutes` split by kind — additive,
  and the existing field keeps its meaning.
- **Upcoming pay**: unpaid confirmed hours, plus the next date the job's pay rule
  produces.

Reconciliation, per job type: **hourly** compares hours × rate (honouring
`rate_override`); **salaried** compares the period amount and reports hours as
context rather than as pay; **contract** compares what was invoiced against what
arrived. The rule lives in one dict beside the function, like `CRUNCH_WEIGHTS`.

An unconfirmed past shift contributes at its scheduled hours and is counted
separately, so every total can say how much of itself is assumed.

---

## Verification

1. `.venv/bin/python -m pytest tests/ -q` — **396 must still pass** at every
   stage. Everything here is additive.
2. `npx tsc --noEmit && npm run build`, with every new CSS class confirmed
   present in the built bundle.
3. Back up `data/app.db` before each stage's first run.
4. Migrations tested against a **copy** with the new columns genuinely dropped
   first — a `--reload` dev server applies them on its own, which already turned
   one migration check into a false pass.
5. Mutation-test each cascade and each reconciliation rule: revert it, confirm
   the named test fails.
6. Money assertions use a tolerance or `Decimal`, never float equality.

## Notes

- Branch each PR off `main` once the previous has merged. Stacking on unmerged
  work caused phantom conflicts twice, and cost an afternoon to the "the fix is
  not there" report.
- Stage explicit paths when committing, never `git add -A`.
- 422 from a parse-time Pydantic validator, 400 from a service-layer one.
- Any literal route under `/jobs/` must be declared above `/jobs/{job_id}`.
- A fixed-size button needs `display:inline-flex; padding:0;
  box-sizing:border-box` or it inherits `padding: 7px 14px` from the base rule.
- Never run a verification script against the real `data/app.db`, and never
  compute a delete filter.
- Update `Ideas/whats_next.txt` as part of landing each stage.

---

# Progress

## Stage 1 — done

Jobs, shifts on the calendar, and confirming worked hours. Branch
`jobs-and-shifts`. 422 backend tests pass (396 + 26 new).

Built as planned, with four things worth recording that the plan did not
anticipate:

- **`EventOccurrence` gained `job_id`.** Without it, reading a window of shifts
  meant a query per occurrence to find out which job each belonged to. It sits
  beside `course_id` and is populated the same way.
- **`ShiftOccurrence` gained `worked_start` / `worked_end`.** Caught by `tsc`:
  re-opening an already-confirmed shift would otherwise have shown the schedule
  again rather than what was actually entered.
- **The `CLASS_KINDS` claim in the plan was wrong.** Keeping `SHIFT` out of it
  does *not* protect shifts from a course timetable rewrite —
  `set_class_schedule` also matches on `course_id`, and a shift has none. The
  first test written for it was vacuous: adding `SHIFT` to `CLASS_KINDS` broke
  nothing. It was rewritten to assert what `CLASS_KINDS` really controls, which
  is that a `ClassMeeting` refuses to be a shift, and now fails under that
  mutation.
- **`JobUpdate` cannot enforce the cross-field pay rules.** A patch changing only
  `kind` cannot see the rate already stored, so the check lives in the service
  (`check_pay_fields`) and clears whichever field the new kind does not use.

Verified beyond the suite:

- Both guards mutation-tested. Widening blackout scoping to every event fails
  `test_a_reading_break_does_not_cancel_a_shift`; adding `SHIFT` to
  `CLASS_KINDS` fails `test_a_class_meeting_refuses_to_be_a_shift`.
- Migration run against a **copy** with all four tables dropped and
  `events.job_id` removed first — a `--reload` dev server applies them on its
  own, which has already turned one migration check into a false pass. 10 events
  and 89 transactions unchanged, titles identical, no existing event given a
  `job_id`, idempotent over three runs.
- End-to-end on a copy of the real database: a Tue/Thu 09:00–14:00 shift took
  exactly 300 of the 600 free minutes on 6 October; confirming Tuesday as
  09:00–15:30 moved it to 390 minutes and left Thursday at 300 and still
  assumed; transaction count unchanged at 89, since no money moves until
  stage 2.

## Stage 2 — done

Paycheques, deductions, the net reaching the ledger, and cash tips. Branch
`job-paycheques`. 447 backend tests pass (422 + 25 new).

Built as planned. Five things the plan did not anticipate:

- **`db.refresh()` silently discarded a correction.** `update_paycheque` set the
  new gross, then called `db.refresh(cheque)` to reload the deductions — which
  reloads the row from the database and threw the edit away, so correcting a
  gross kept the old one and rewrote the ledger at the old net. Replaced with
  `db.flush()` plus a query for the deductions. Caught by a test, not by review.
- **A cash tip is several ledger rows, not one.** It splits across accounts like
  any other income, but `shift_records` holds a single `tip_transaction_id`.
  Deleting only that row orphaned the rest. The record now points at one row and
  the *group* finds them all, and a changed tip rewrites the group rather than
  patching it.
- **A cash tip with nowhere to go no longer fails.** The first version raised
  when no account had an income share — which blocks logging your hours over an
  unrelated budget setting. It now records the tip and reports
  `tip_in_ledger: false`, so the gap is visible rather than silent or fatal.
- **The manual deduction delete duplicated the ORM cascade**, leaving SQLAlchemy
  expecting to remove rows already gone and warning on every commit. The
  relationship's `delete-orphan` handles it. The suite is now also run with
  `-W error::sqlalchemy.exc.SAWarning` to catch the next one.
- **`record_deposit` commits on its own**, so it could not be reused: the rows
  and the cheque have to land in one transaction. `deposit_rows` builds them
  unsaved from the same `split_income`, and the caller commits once.

Verified beyond the suite:

- Reverse cascade mutation-tested: removing it fails
  `test_deleting_the_ledger_rows_takes_the_cheque`.
- End-to-end on a **copy** of the real database, against the real income shares
  (Spending 50, Savings 20, Investments 20, Money Lent 0): a $170 cheque against
  an expected $185 was flagged $15 short; deductions of $23.21 stayed off the
  ledger; the net of $146.79 split into three rows of $81.55 / $32.62 / $32.62
  summing exactly to the net; deleting the cheque returned the transaction count
  to where it started, with no paycheque left behind.

## Stage 3 — not started

Reconciliation and the earnings page.
