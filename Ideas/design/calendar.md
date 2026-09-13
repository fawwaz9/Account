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
| Repeating tasks | a rolling window ahead | each occurrence is ticked off separately, and a virtual one has nowhere to keep that |

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

## Still open

A term timeline — every course's span on one horizontal chart. Non-weekly class
times, per meeting: biweekly is nearly free, but the meetings share one
`starts_on`, so it needs a per-meeting first date or every biweekly lab lands on
the odd weeks of term. Monthly needs `BYSETPOS` and is a separate decision.
