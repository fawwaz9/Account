# Tasks

## Context

What is outstanding, and increasingly *what is worth doing first*. The module
started as a list ordered by date and has grown two further senses: which work
belongs to a course you are behind on, and whether you actually hit your dates.

**Decisions taken:** the page groups by how soon, because the question it answers
is "what now"; a task with a date is also a calendar item, read through
`list_tasks` rather than a table of its own, so a deadline is one record; risk
leads the date ordering rather than replacing it; priority is shown, not sorted
on.

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `list_tasks` | `services/task_service.py` | the list, filtered and sorted, with course code and risk attached |
| `sort_key` | `services/task_service.py` | risk, then date, then time, then created |
| `course_risk`, `risk_band` | `services/task_service.py` | how far behind a current course is |
| `completion_timing` | `services/timing_service.py` | how early or late work gets finished |
| `run_due`, `materialise`, `resync_occurrences` | `services/recurring_task_service.py` | repeating chores |
| `build_preview`, `capture` | `services/quick_capture_service.py` | a line of text into a task |
| `tokenizer` | `shared/tokenizer.py` | course code, date word, duration, amount, score |

## Data model

`tasks` — title, notes, `due_date`, `due_time`, `estimated_minutes`, `tags`
(JSON), `priority`, `done`, `completed_at`, `archived`, and three links:
`course_id` (school work, whose course code is then its category), `grade_id`
(raised from a dated grade), `recurring_id` (written by a repeat rule).

`recurring_tasks` — the template plus the five shared `recur_*` columns, and its
own `priority` so a chore that repeats sixty times is not corrected sixty times.

Checking a task sets `completed_at` **and archives it**: a checked task's place is
the record of the term, not the list of what is left. Unchecking reverses both,
because the usual reason to uncheck is having checked the wrong row.

## The three senses of order

**Soonest first** is the base, and undated tasks sort after every dated one
(`date.max` rather than None, so the comparison does not raise).

**Risk leads it.** A task from a current course below its target carries a band —
0–5 points below is mild, 5–10 moderate, over 10 severe — and sorts to the top of
whichever date group it was already in. The page's grouping is untouched: it
still answers "what now", and risk only reorders within that. Only current
courses, and only ones with marks recorded: that is the rule `collect_attention`
already applies, because a past course below target is history.

**Priority is shown, not sorted on**, by choice. Coursework is seeded from its
grade category — a final at 5, a midterm or project at 4, everything else at 3 —
and is the student's from then on. Seeded **once, at creation**: `sync_task` runs
on every grade write, so re-deriving it there would silently revert the student's
own choice each time a score was entered.

## Completion timing, and the bug it would have had

`completed_at` minus `due_date`, over a rolling week and the calendar month to
date, bucketed by when work was *finished*.

Two figures, because each hides what the other shows: a signed mean carries
magnitude but lets a fortnight late cancel a fortnight early; an on-time
percentage cannot be skewed by one forgotten task but counts a day late and a
month late alike.

**The trap:** `completed_at` is naive UTC, `due_date` is a plain local date. In
America/Regina (UTC−6) anything finished after 18:00 local is stored on the
following UTC day — so a naive subtraction reports evening work on its due date
as a day late. Evening is when most of it gets done, so the error is not noise,
it is a systematic drift toward "late" that would make the whole figure a lie.
The service converts through the student's own timezone first, and a test covers
exactly that case.

Second gotcha, from the same feature: `set_done` archives on completion, so the
timing query must include done **and** archived rows. `list_tasks` excludes both
by default and cannot be reused.

## Repeating tasks, and the edit bug

A rule writes occurrences for a rolling window — 14 days back, 60 ahead —
idempotent on `(recurring_id, occurrence_date)`, so it is safe to call on every
load and there is no scheduler anywhere.

The bug that shipped with it: `materialise` only ever *adds* dates that are
missing, so editing a rule never reached the sixty days of occurrences already
written. Renaming a daily chore changed the rule and nothing you could see.

`resync_occurrences` divides on **`done`, not on the date**:

- a completed occurrence is a record of work actually done and is never touched
- an outstanding one follows the rule, including an overdue one, which is the
  same chore still waiting

Dates the rule no longer generates are dropped from today forward, so moving a
chore from Monday to Thursday does not leave the Mondays behind. And an edit
passes `since=today` so the 14-day look-back — right on a first run — cannot
back-fill last Thursday as an overdue task that was never assigned.

One accepted loss: nothing marks an occurrence the student hand-edited, so a
tweak to a future one is overwritten when the **rule** is next edited. That beats
every edit appearing to do nothing, and editing the repeat is a reasonable way to
say "change them all".

### Where an occurrence sits, and which occurrence it is

Two columns, because per-occurrence editing made them two facts. `due_date` is
where it currently sits and the student may move it; **`occurrence_date` is the
date the rule produced, and is its identity.**

They were one column until a task became editable, and the collision is worth
recording because both halves of it were silent:

- `written_dates` answers *"which occurrences exist"*. Reading `due_date`, moving
  Monday's chore to Wednesday made Monday look unwritten, so the next page load
  put **a second copy back on Monday**. One edit, two chores.
- the stale sweep in `update_rule` asks *"does the rule still call for this"* and
  deleted outstanding occurrences whose date was not in the pattern — which after
  a move is exactly the ones that had been edited, and nothing else.

So identity has to be something the student cannot edit. `materialise` stamps it
once at creation and nothing writes it again; a `BACKFILLS` entry set it from
`due_date` for every occurrence written before the column existed, which is
correct precisely because there was no way to move one until now.

## Snooze, and why the due date does not move

A task can be pushed out of the list until a date. `due_date` is untouched:
moving it would *hide* the deferral rather than record it, and would leave every
later question about lateness measured against a date the student picked rather
than the one they were given — which is exactly what the completion-timing figure
depends on. A test asserts that a snoozed task finished late still reads as late
against its original date.

The task comes back on its own when the date passes, in the position its own due
date puts it in. Nothing runs to make that happen; the list filter simply stops
excluding it.

`task_snoozes` is a table rather than two columns on the task, because **the
pattern is the point**. Three snoozes citing "waiting on lab partner" says the
task is blocked on a person; a latest-reason column cannot say it, because each
snooze would overwrite the evidence of the one before. The row carries only the
count and the latest reason — a list of tasks does not need a term of history
travelling with it — and the full history is fetched when the modal opens, which
is the one place it changes a decision.

Waking a task early clears `snoozed_until` and keeps the history. Undoing a
snooze does not undo having made it.

## Reminders, and the honest limit

A reminder is not a task: it has no life before or after its moment, being told
is the point, and there is nothing to tick off. Forcing one through a task made
it a chore that never quite closed — the same reason a sat exam is an event
rather than a task.

**`remind_at` is naive local wall time**, deliberately unlike every other
DateTime in the app, which is naive UTC. "Remind me at 09:00" means nine o'clock
where the student is standing, and should still mean that after the clocks change
or after a flight; storing UTC would move an existing reminder by an hour every
spring. So the comparison goes through the timezone preference, and a test pins a
fixed instant to prove it: at 17:30 local (23:30 UTC), a reminder set for 20:00
is *not* due — a UTC comparison would have fired it two and a half hours early.

**There is no scheduler and no push.** The client asks what is due on an interval
while it is open, and that is the whole mechanism. A browser notification is
fired as well where permission was granted, but the in-app banner is the reliable
path and stays until acknowledged.

The banner says the limit out loud. A notification you half-trust is worse than
one whose limits you know, and the alternative — a service worker, VAPID keys and
a process outliving the request — is a large amount of infrastructure for a
locally-run app.

Permission is requested **when the first reminder is saved**, never on page load
and never before the save: a prompt with no context is the one people dismiss
forever, and there is no second chance to ask.

`fired_at` is stamped once and never re-stamped. A reminder surfaced on Monday
and still not dismissed on Wednesday is the same reminder; re-stamping it would
make it read as new on every page load, which is how a notification becomes
something you learn to ignore. Moving the time clears both `fired_at` and
`dismissed_at`, or pushing one to tomorrow would leave it looking already fired
and it would never surface again.

## Quick capture

A line of text into a task, through the shared tokenizer: course code, date word,
duration, amount, score. The omnibox is the same parser with a second front end —
the tokenizer's second consumer, which is what justified extracting it.

## Editing a task

Every row carries an **Edit** button, and it opens the same dialog a task on the
calendar opens. For a long time a task could be ticked, snoozed, re-prioritised
and deleted — and a title typed wrongly could only be deleted and retyped.
`PATCH /tasks/{id}` and `updateTask` both already existed; there was simply no
dialog calling them.

Completing lives **inside** that dialog as a button rather than beside Save,
because it is the one control there that changes something without being a save.
It does not save the fields first: ticking a task off is one decision and editing
it is another, and a Complete button that quietly also wrote a half-finished edit
would be doing two.

### The gradebook closes a task, and never reopens one

A score arriving checks its task off. Nothing in `sync_task` ever unchecks one.

It used to derive the flag both ways — `if task.done != scored` — and that made
the gradebook the authority on whether the work had happened. It is not.
**"I finished the lab" and "the lab has been marked" are different facts**, the
first the student's on Tuesday and the second the TA's three weeks later, and
deriving one from the other loses the first.

The symptom was reported as "entering a grade reopens the task", and it was
actually worse and narrower than that: entering a score was fine, but *any* save
of a grade whose score box was empty ran `set_done(task, False)`, which nulls
`completed_at` and un-archives. Open a grade to fix a typo in its name, save,
and a lab ticked off three weeks ago is back in the list with no record of when
it was done.

**Clearing a score therefore leaves the task closed**, which reverses what this
did before and is the deliberate trade: clearing a score is a statement about
the gradebook — wrong row, wrong number — not about whether the work happened.
Only the student reopens a task, from the task editor.

Two owners take fields back:

- **from a grade** — the title and the deadline are disabled with the reason
  shown, because `sync_task` rewrites them on every grade save. Offering that
  edit would be offering one that silently reverts. Notes, estimate, tags and
  priority stay, which is exactly the set `sync_task` leaves alone.
- **from a repeat** — everything is editable and the change lands on that one
  day, with a line saying that editing the repeat itself will write over it.

`withDueDate` and `parseTags` moved out of `TaskForm` into `taskFields.ts` when
the dialog appeared. Two forms holding the same two rules is how one of them ends
up rejecting a save the other allows.

## The page

Two columns, split by what you do with each side. Left is the work in front of
you: how you have been doing, the one line it takes to add something, what is
late, what has no date, and the record of what is finished. Right is everything
that takes more than a line: the full form, the repeats, and the fortnight they
write into.

Each column is its own flex column rather than one grid placing every row,
because a grid row is as tall as its tallest cell and a short "Overdue" beside a
long fortnight leaves a hole. On a phone the columns dissolve with
`display: contents`, which is what lets `order` interleave them — otherwise one
whole column would have to precede the other and the fortnight's work would sit
below the add form.

The list ends at the fortnight. What lies past it is a count, not a section: a
task three weeks out is not work you can start, but it must not vanish either.

## Notes

- A task with a date is also a calendar item, read through `list_tasks` with a
  window. One record, so the two cannot disagree.
- `date.max` for undated tasks in the sort key, not None.
- Priority is seeded at creation only. Re-deriving it on every grade write would
  revert the student's choice.
- `set_done` archives. Any query over completed work must say so.
- Exams are **not** tasks: nothing to tick off. They are a read-only band above
  the list, on a thirty-day horizon, because revision is what fills the fortnight
  below it.
- A due date pre-fills 23:59, since a deadline with no time means the end of that
  day. Clearing the date clears the time, which the API rejects on its own.

## Still open

Nothing. At-risk-first sorting, priority, completion timing, snooze and reminders
have all landed; what remains on the Tasks side is whatever the next term turns
up.

The one thing worth revisiting is delivery: reminders reach you only while the
app is open. If that proves too weak in practice, the step up is a service
worker and push, and it should be taken deliberately rather than by degrees.
