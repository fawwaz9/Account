# Calendar

## Context

Everything with a date, and the engine that decides what repeats. It is the
module other modules build on rather than the one with the most features: class
times, standing payments, repeating tasks and shifts all resolve through one
recurrence engine, and three of the four store no occurrences at all.

**Decisions taken:** a repeat is stored as the rule that generates it, never as
its occurrences; the rule is a small fixed set of fields rather than an RFC 5545
string; the week grid is a fixed 24 hours in a scrolling body; all-day items live
in the header, because pinning them to midnight would say something false.

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `occurrences(rule, starts_on, from, to, skipped)` | `utils/recurrence.py` | the whole engine. Dates in, dates out, no session |
| `Rule`, `parse_byday`, `format_byday`, `add_months` | `utils/recurrence.py` | the rule, and its stored form |
| `recurrence_of` / `apply_recurrence` / `rule_of` | `utils/rule_columns.py` | the five columns four tables share |
| `list_occurrences` | `services/event_service.py` | every dated thing in a window, already expanded |
| `set_class_schedule` | `services/class_schedule_service.py` | a course timetable, replacing rather than appending |
| `free_blocks`, `week_load`, `crunch` | `services/load_service.py` | three readings of one window |
| `blackout_dates` | `services/blackout_service.py` | a reading break, subtracted from course events only |

## The engine

One module, pure, no session. The rule is frequency, interval, weekdays, and an
end expressed as either a last date or a count — deliberately not a full RRULE
string. A timetable, a monthly payment and a weekly chore are all expressible in
it, it survives being read in a database browser, and it needs no parser. If
something genuinely needs `BYSETPOS`, that is the point to reach for a library.

Three behaviours worth knowing:

- **Weekly is anchored to the Monday of the starting week**, and steps whole
  weeks by the interval. So "every other week on Mon/Wed/Fri" keeps all three
  days in the same on-week rather than drifting apart.
- **Monthly steps by day of month** through `add_months`, which yields *nothing*
  for a month too short — the 31st does not occur in February, and inventing the
  28th would silently move a rent day.
- **`byday` is weekly-only**, enforced by the validator. So "the second Tuesday"
  is not expressible. That is the known limit, and it is why non-weekly class
  times split into an easy half and a hard one.

### Four consumers, and their differences are the point

| Consumer | Materialises | Why |
|---|---|---|
| Class times | never | nothing hangs off an individual lecture |
| Shifts | never | same |
| Recurring payments | only once it has happened | a balance is the sum of its rows, and a future payment in that sum is money wrongly gone |
| Repeating tasks | a rolling window ahead | each occurrence is ticked off separately and may be edited on its own, and a virtual one has nowhere to keep either |

A thing expanded on read has **no row per occurrence**. Anything recording
something about one date must key on `(event_id, on_date)` — the identity
`EventOccurrence` documents, and what `shift_records` uses.

## Data model

`events` — title, `kind`, `starts_on`, `start_time`/`end_time` (both null means
all-day), the five `recur_*` columns, `skipped_dates` (JSON), and three links
saying what the block belongs to: `course_id`, `job_id`, `grade_id`.

`EventKind` is a closed enum, not a table, because each value has behaviour
attached — a midterm is themed and sorted differently from a lecture, so a
user-defined one would have nothing to do. `CLASS_KINDS` is what a course
timetable is built from *and* the only kinds a `ClassMeeting` accepts;
`EXAM_KINDS` gets the exam card; `shift` is neither.

`term_blackouts` — a reading break, entered once and subtracted from every
recurring event **that belongs to a course**. That scoping is one
`event.course_id is not None` check and a test: the same engine drives rent and
the bins, and neither cares about reading break. It also means a shift is
correctly unaffected, with no code that knows what a shift is.

## The load service: one window, three readings

`free_blocks`, `week_load` and `crunch` are one question asked three ways off a
single `list_occurrences` call.

- **Free blocks** — the gaps between commitments inside a study window you set in
  Settings (08:00–22:00, 30-minute floor). Overlapping classes are merged before
  the gaps are walked, or the end of one and the start of the next look like a
  gap that never existed. Time already gone is not offered.
- **Week load** — booked and estimated kept apart, because booked time is not
  optional and estimated time is a guess you wrote down. Split further into
  `work_minutes` and `class_minutes`, additively: `booked_minutes` still means
  every timed event.
- **Crunch radar** — per ISO week, weighted by kind: final 5, midterm 3, deadline
  1, everything else 0. A kind the dict does not know scores zero and drops out,
  which is how a shift stayed correctly absent from a measure of academic
  pressure without anyone writing a rule for it.

## Notes

- **`skipped_dates` is a JSON column.** Serialise dates before assigning and
  rewrite the list whole. Assigning `date` objects into it broke editing any
  event with a cancelled date. Same class of bug as `users.preferences`.
- Adding an `EventKind` touches: the enum, `EVENT_KIND_LABELS` here and in the
  frontend, and a chip colour in `calendar.css`. It must **not** join
  `CLASS_KINDS` unless a course timetable should be able to be made of it.
- What protects a shift from a timetable rewrite is the `course_id` match in
  `set_class_schedule`, **not** `CLASS_KINDS`. A test asserting otherwise was
  vacuous and had to be rewritten.
- A repeat's `count` is measured from the event's own start, not from the window,
  so paging forward cannot hand you occurrences seven and eight of a five-week
  series. A skipped date consumes one of `count`.
- The week view's overlap maths and `placeTasks` were each checked with a one-off
  esbuild harness. There is still no frontend test runner.
- Tasks reach the calendar as chips the client merges in, not through
  `list_occurrences`. A task due at a specific time is placed on the clock; one
  due at end of day stays in the all-day band, since that is what a bare due date
  means.
- **A task chip opens the task editor** — the task page's, not a second one.
  It used to tick the task off instead, which meant the calendar could do exactly
  one thing to a task and a click meant to *look* at one finished it. Completing
  moved inside the editor, where it is a button that says what it does. The cost
  is one-click ticking from the calendar, which was deliberate and is now two
  clicks; the ✓/○ glyph stays as state, with `aria-hidden` since it is no longer
  the control.
- **The event popup carries its own Close.** `Modal` has no × and does not close
  on a backdrop click, so every dialog relies on its form's Cancel — and this one
  is read-only. Its grade branch rendered an explanatory sentence and *no buttons
  at all*: a dialog dismissable only by a keystroke nothing mentioned. The other
  branch was worse in its way, since the nearest thing to a dismiss was "Cancel
  this one", which cancels the lecture. Close is first in the row, away from
  Delete.

## The term timeline

Every current course on one axis. Deliberately **no backend**: the page already
holds each course with its dates and its `term_bucket`, so the span is two lines
of arithmetic over data already fetched, and an endpoint would only be a second
place for the same answer to live.

That is not a hole in "compute on the server". The rule exists because a derived
*figure* computed twice can disagree — an average, a total. A bar's position is
layout over server-supplied facts, and the facts here (the dates, and which term
a course is in) are still computed server-side.

`timeline.ts` is kept out of the component for the same reason `weekLayout.ts`
is: position arithmetic goes wrong silently, because a bar an inch off looks
like a design choice rather than a bug. Fourteen assertions cover it, including
that no bar can be laid outside the axis and that a one-day course keeps a floor
width rather than vanishing into a hairline.

Courses with no dates are **named underneath, not dropped**. Most courses in this
app carry none, so a chart showing three of six would under-report the term while
looking complete.

## Class times that are not weekly

A `ClassMeeting` carries its own `interval` and its own `first_on`, because a
course routinely mixes them — a weekly lecture beside a fortnightly lab is the
ordinary case, not an edge one. That suits what was already there:
`set_class_schedule` turns each meeting into its own event row with its own rule
columns, and `Rule.interval` was honoured all along.

**Two halves, and the second is easy to miss.** The interval says *how often*;
`first_on` says *which week the cycle starts on*. The whole timetable shares one
`starts_on`, so without a per-meeting anchor every fortnightly meeting is pinned
to the odd weeks of term — and labs commonly begin in week two, which would leave
one a week out for the whole term while looking perfectly scheduled.

`first_on` must fall on a day the meeting actually runs. Anchoring to any other
day leaves the first cycle short, because the engine skips forward to the next
day that does run and a week is counted wrong. It is also bounded by the term, in
the service rather than the schema — only the service knows those dates, since
they come from the course when the form omits them.

A weekly meeting ignores `first_on` entirely: every week is an on-week, so there
is no phase to choose, and the form hides the field rather than asking a question
with no meaning.

**Monthly is still unreachable.** `byday` is weekly-only, so "the second Tuesday"
cannot be expressed, and a monthly repeat lands on the day of the month it
started on. That is the `BYSETPOS` case the engine's docstring names as the point
to reach for a library rather than extend the rule.

## Still open

Nothing on the Calendar side. `ShiftMeeting` is the same shape and could take the
same two fields whenever a fortnightly shift comes up; it was left out here as
scope rather than as an oversight.
