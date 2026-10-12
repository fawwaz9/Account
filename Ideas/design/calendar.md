# Calendar

## Context

Everything with a date, and the engine that decides what repeats. It is the
module other modules build on rather than the one with the most features: class
times, standing payments, repeating tasks and shifts all resolve through one
recurrence engine, and three of the four store no occurrences at all.

**Decisions taken:**
- A repeat is stored as the rule that generates it, never as its occurrences.
- The rule is a small fixed set of fields, not an RFC 5545 string.
- The time grid is a fixed 24 hours in a scrolling body.
- All-day items live in the header, because pinning them to midnight would say
  something false.
- "Now" and "today" come from the Settings time zone, never the browser's.
- A phone gets one and three days in place of the week.

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
| `event_sharing_service` | `services/event_sharing_service.py` | a one-off event shared through a link (D24) |
| `useCalender` | `frontend/src/features/calender/hooks/useCalender.ts` | the window on screen, its fetches, and the shared items merged in |
| `views.ts` | `frontend/src/features/calender/views.ts` | which views a width offers, each view's dates, step and heading |
| `place`, `placeTasks` | `frontend/src/features/calender/weekLayout.ts` | overlap columns for blocks, and deadlines on the clock |

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

## The views

**Desktop: Week and Month.** The week opens by default, because it has the time
axis that answers "what does today actually look like", and the free blocks and
week load hang off it. The month runs Monday to Sunday over six rows, so the
window it fetches covers the overflow days too.

**A phone gets Day, 3 day and Month** (shipped 2026-10-12). At 720px and below
(`PHONE_QUERY`, the width where the sidebar becomes a top bar) seven columns are
too narrow to read. A phone opens on three days from today.
- **The arrows move a whole page**: a day, three days, a week or a month. A
  three-day window starts at the cursor rather than snapping to a week, so Today
  means today and the two days after it.
- **A sideways swipe does what the arrows do** (`shared/hooks/useSwipe.ts`).
  It counts only if it travels at least 50px and 1.5 times as far sideways as
  vertically. Scrolling through the hours is vertical and never perfectly so,
  and must never step the calendar. Two fingers is a pinch. The listeners are
  passive, so a scroll is never held up.
- **The view is read through `fitView`, not corrected in an effect.** A rotation
  that crosses the breakpoint therefore never renders or fetches a view the width
  doesn't offer. The week becomes three days and back, Month stays Month, and
  the date stays put. The choice is kept too: rotate back and it is still there.

**One time grid for one, three or seven days.** `WeekView` sets `--days` on its
root, and both grids' `grid-template-columns` read it. The header and body are
separate grids, so the dates stay put while the hours scroll, and the shared
variable is the only thing keeping their columns lined up. Headings come from each
date, not its position: a three-day window can start on any weekday. The
minimum width is `gutter + days × 90px`, so seven days scroll sideways on a
narrow screen and one or three fit a phone.

**The free blocks and week load stay a whole week** in the day and three-day
views: the Monday-to-Sunday week the first visible day falls in. A week's load
measured over three days would read as a light week.

## The clock

**The now-line** is a red line at the current minute, in today's column and
nowhere else. So a week that isn't this one draws none, with no branch of its
own. It ticks on the minute boundary, not 60 seconds from mount, ignores the
pointer, and is hidden from screen readers, which would otherwise hear a new
time every minute.

It reads the **Settings time zone** through `nowIn(zone)`, and so does the
highlighted today in every view. The backend's "today" already did, and a line
from a different clock would sit in a different column from every figure the
server sends. `today()` reads a module-level zone that `AuthProvider` sets
while rendering, not in an effect: an effect would open on the browser's day
and then flip. About forty frontend call sites follow it without each threading
a zone through.

## Colours

All eight kinds can be recoloured in Settings → Calendar, stored in
`preferences.event_colors` only for the kinds changed. "Default" removes the key,
so a retuned default reaches everyone who never touched it. Kinds stay a fixed
enum: recolouring only.

The stylesheet holds one `--kind-color` per kind, with the bar and tint derived
by `color-mix`, and a chosen colour arrives as an inline custom property. An
exam keeps its heavier bar in any colour. A test keeps `kindColors.ts`'s
defaults in step with the stylesheet's.

## Shared events, and shifts near exams

**A one-off event of your own can be shared through a link** (D24). Members see
it on their own calendar, drawn dashed, with the owner's name and the other
members'. They can leave and change nothing: an event is a time and place one
person set. If the owner later makes it repeat, it drops off members' calendars.
A shared *task* reaches members' calendars on its due date as an all-day item.
Both are merged into the window in `useCalender`, and a failed shared read leaves
your own calendar as it was. The mechanism is in
[isolation-and-sharing.md](isolation-and-sharing.md).

**A shift that collides with an exam is flagged here and on Jobs** (D21): it
overlaps, or ends within the "Keep clear before an exam" buffer. The rule lives
in Jobs (`conflict_service.py`), reading the calendar's own occurrences, so it
agrees with what this page shows. See [jobs.md](jobs.md).

## Notes

- **`skipped_dates` is a JSON column.** Serialise dates before assigning and
  rewrite the list whole. Assigning `date` objects into it broke editing any
  event with a cancelled date. Same class of bug as `users.preferences`.
- Adding an `EventKind` touches: the enum, `EVENT_KIND_LABELS` here and in the
  frontend, and a `--kind-color` in `calendar.css` with its twin in
  `kindColors.ts` (a test fails until both exist). The Settings colour list
  reads `EVENT_KIND_LABELS`, so it follows. It must **not** join `CLASS_KINDS` unless a
  course timetable should be able to be made of it.
- `features/calender/` is misspelled across its files. It is a known follow-up,
  deliberately not bundled into any feature change.
- What protects a shift from a timetable rewrite is the `course_id` match in
  `set_class_schedule`, **not** `CLASS_KINDS`. A test asserting otherwise was
  vacuous and had to be rewritten.
- A repeat's `count` is measured from the event's own start, not from the window,
  so paging forward cannot hand you occurrences seven and eight of a five-week
  series. A skipped date consumes one of `count`.
- The week view's overlap maths and `placeTasks` are covered by
  `weekLayout.test.ts` now, under `vitest`. They were each checked with a
  one-off esbuild harness before, which is to say checked once, by whoever
  remembered.
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
like a design choice rather than a bug.

Both are covered by `vitest` now -- `timeline.test.ts` and `weekLayout.test.ts`
-- where before they had only one-off esbuild harnesses that ran when someone
remembered to write one.

> **This paragraph used to claim fourteen assertions covering, among other
> things, "that no bar can be laid outside the axis". Writing them found that
> one was not true.** The floor width and the axis bound are in direct tension
> and the floor won: a one-day course on the last day of a hundred-day term was
> laid at 99% and then widened to 1.5%, painting half a percent past a track
> that has `position: relative` and nothing to clip it -- so it read as a course
> running past the end of term. `buildTimeline` now slides such a bar back
> inside the axis instead, which is the lesser distortion, since a bar at the
> floor is already wider than the day it stands for. Both guarantees hold
> together now, and the test that says so fails if the clamp is removed.

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

- A shared event doesn't count in a member's free blocks, week load or crunch
  strip.
- `ShiftMeeting` is the same shape as `ClassMeeting` and could take the same two
  fields whenever a fortnightly shift comes up. It was left out as scope, not as
  an oversight.
