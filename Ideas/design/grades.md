# Grades

## Context

The oldest module, and the one the rest borrow their vocabulary from: a course, a
term, a category weight. Its job is to answer *where does this course stand* and
*where can it still finish*, and to be the single place that knows when a term
runs — a fact Finances, Calendar and Jobs all need and none of them own.

**Decisions taken:** a course is marked out of 100 and bonus sits outside that;
an unmarked item is not a zero; a projection must agree with the live number at
its ends or it is a second opinion; flags (`no_final`, `transfer_credit`,
`archived`) change the rules rather than hiding the row.

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `calculate_current_average` | `services/grade_service.py` | the course average, from marked work only |
| `bonus_contribution` | `services/grade_service.py` | marks banked on top of the 100 |
| `project_average` | `services/grade_service.py` | the same arithmetic with unmarked work at an assumed score |
| `calculate_grade_band` | `services/grade_service.py` | best and worst finish, per unmarked item |
| `calculate_required_final` | `services/grade_service.py` | what the final has to be |
| `category_points` | `services/grade_service.py` | marks out of a category's weight, in `Decimal` |
| `term_bucket`, `course_result_grade`, `effective_target` | `utils/terms.py` | placing a course in time, and judging it |
| `weight_problems` | `utils/weights.py` | weights that do not add up |
| `sorted_grades`, `grade_sort_key` | `utils/ordering.py` | the one order grades reach a client in: case ignored, numbers compared as numbers |
| `resolve_course` | `services/course_lookup.py` | a course from a typed code; three callers |
| `sync_schedule_for_grade` | `services/grade_schedule.py` | a dated grade's task or calendar block |
| `compare`, `set_counting` | `services/scheme_service.py` | alternative grading schemes beside the course's own (D18, D25) |
| `audit` | `services/degree_service.py` | requirements against courses, computed on every read (D31) |
| `link_of`, `match` | `services/catalogue_service.py` | a course's place in the shared catalogue, matched when read |
| `prerequisites`, `evaluate` | `services/prerequisite_service.py`, `utils/prerequisites.py` | met, on track or not met, advisory only |
| `overview`, `save` | `services/term_review_service.py` | the end-of-term review (D25) |
| `parse`, `apply`, `add_to_course` | `Intake/services/syllabus_service.py` | a syllabus in, a course out, checked by a person (D16, D27) |

## Data model

`courses` — code, name, year, semester, credits, `target_grade` (null falls back
to the account default), `average` (stored, and authoritative: every write path
recomputes it, so a hundred readers do not each redo the arithmetic), plus three
flags that change rules rather than visibility:

- `no_final` — no final exam, so "finished with no final grade" is not a problem
  to raise
- `transfer_credit` — counts credits, carries no grade, stays out of every average
- `archived` — still searchable and still in the credit-weighted average, but out
  of credits completed

And since Phase 1 and 2:

- `section` — "101", "L1A". A current course without one is listed in Attention
  (D22), since the catalogue and a syllabus both need to know which section
- `final_grade` — the result the professor submitted. Once entered it is the
  grade a finished course is represented by (`course_result_grade`), ahead of
  the running average
- `projected_before_final`, `projected_on` — the projection kept from the moment
  before the final was marked or the result entered (D34). Stored, because the
  point is what was true *then*
- `counting_scheme_id` — the grading scheme that counts as the course's grade, or
  null for the course's own weights (D29)
- `catalogue_course_id`, `catalogue_unlinked` — only what *you* decided about the
  catalogue link: a course picked by hand, or "none". With neither, the link is
  matched by campus and code on every read

`course_category_weights` — category → weight, one row each. A table rather than
a JSON blob because it is queried and summed.

`grades` — name, `score` (**nullable**, and the nullability is the point: null is
"not marked yet", zero is "marked zero", and collapsing them makes a course you
are doing well in read as a failure), `max_score`, category, `due_date`,
`schedule_as`, `excluded`.

### The two rules that shape everything

**An unmarked item is not a zero.** Only marked work enters the average, which is
why a course with one 90% assignment shows 90 rather than 9. Everything about
projection exists because that running average cannot answer "where will this
finish" — 78% with the final still to come is anywhere between a fail and an A.

**Bonus sits outside the 100.** `ADDITIVE_CATEGORIES` in `utils/enums.py` names
it, and `scoring_weight()` is what anything summing weights must use instead of
reading them raw. A course weighted 100 + 5 bonus is still marked out of 100, and
the 5 is protection against a slip elsewhere. Six sites already special-case
`Final`; routing the bonus exclusion through `is_additive()` is what stops the
two drifting apart.

`excluded` is the dropped-mark flag: the grade stays on the course, visible, and
leaves every average. For a professor who drops the two lowest quizzes.

Newer tables, each the user's own:
- `grading_schemes`: alternative rubrics.
- `degree_requirements` and `course_equivalences`: the audit's inputs.
- `syllabus_parses`: a parse and, if kept, where its file is.
- `prerequisite_proposals`: your own prerequisite rules.
- `term_reviews`: the end-of-term answers.

`catalogue_courses` and `catalogue_prerequisites` belong to nobody, and
`grade_distributions` is sealed. All three are in
[isolation-and-sharing.md](isolation-and-sharing.md).

## What was built, and what it cost

| Feature | Note |
|---|---|
| Category weights, letter grades, GPA | GPA is opt-out: UBC does not publish one |
| Required-final calculator | reports which categories are empty, because the figure ignores them |
| Best/worst band | projected **per unmarked item**, not per category — per-category rounded twice |
| Bonus as a real category | the weight outside the 100; a gold row when a score exceeds its own max |
| Course flags | each changes a rule; none hides the row |
| Dropped marks | `excluded`, kept and visible |
| Dated grades | task or calendar block, the student's choice |
| Fractional scores | the columns always allowed it; the inputs defaulted to `step="1"` |

### The rounding decision, which is deliberate

`category_points` computes in `Decimal` from the recorded marks. `11.825` has no
binary representation — the nearest double sits *below* it — so scaling a rounded
average by a weight loses the hundredth before any rounding happens, and showed
`11.82` for a figure that is exactly `11.825`.

The averaging engine deliberately does **not** do this. Changing it would move
stored course averages, and it was measured: 0 of 27 course averages moved, 0
letter grades moved. So the fix is confined to the one figure that was visibly
wrong, and the engine was left alone.

## Notes

- `average` is a stored column and authoritative. Do not recompute it in a reader.
- Only Grades knows when a term runs, and it knows it **per course**: the span is
  `min(start_date), max(end_date)` across the term's courses. Most courses carry
  no dates, so anything built on the span has to say it is measuring from only
  some of them.
- Anything summing `category_weights` wants `scoring_weight()`, not the raw value.
- Scores, weights and targets are floats. A number input for any of them needs
  `step="any"`.
- `effective_target` lives in `utils/terms.py`, not in `dash_services`. Tasks
  needs it, and importing it from a service closed a cycle through four modules.
- A literal path under `/courses/` must be declared above `/courses/{course_id}`.
  `/courses/resolve` was not, and 422'd.

## Printing a term

No dependency: a print stylesheet and `window.print()`, which already opens a
save-as-PDF dialog on every platform that matters here. The button only
appears on a specific past or future year, never on "Current Courses" -- a
term that has stopped moving is a record worth keeping; the current term is
still changing under you, so printing it today freezes something that will be
wrong by next week.

Everything that is screen furniture rather than the record opts out with
`.no-print` (the print button itself, the archived toggle) or is hidden by
`layout.css`'s own print rule (the sidebar, the topbar) -- no page needs to
know about another page's chrome. `.courses` and `.termGroup` both get
`break-inside: avoid`, the one thing a printed list must not do: split a
course's code and grade across a page boundary.
## Category blind spots

Read-only, no tables: pools every marked, non-bonus item of one category --
labs, quizzes, midterms -- across every graded course, and compares that pooled
percentage to the same pooling done across every category. A category is
reported only once it sits **2 or more points below** the student's own
overall average **in at least two different courses** -- the second guard is
the whole point of the feature. One course's weak labs is that course's
problem; the pattern this looks for only exists once courses are compared, and
a single-course dip is what "not in one class" in the original ask was
excluding.

Severity uses the same three bands as the tasks page's risk badge (0-5 mild,
5-10 moderate, over 10 severe) rather than a new scale, so a student who
already reads one badge does not have to learn a second.

**Weighted by marks, not by category weight.** The comparison is earned over
possible, pooled across every item -- the same arithmetic
`calculate_grade_category_average` already does for one course, just not reset
between courses. Weighting by each course's *category weight* instead would
answer "which category costs the most," a different question from "where are
marks actually being lost relative to everywhere else."

Bonus is excluded by construction (`is_additive`), a dropped mark by
`counts_toward_average`, and an unmarked item by `is_marked` -- three existing
predicates, no new ones needed. A transfer-credit course contributes nothing,
since `is_graded` already says it carries no marks at all.

**Found and fixed on the way in:** `add_grade` and `add_grades_bulk` built their
`GradeModel` row field by field and never read `grade_data.excluded`, so a
grade created already dropped came back counting toward the average anyway.
Never caught before because every existing dropped-mark test writes the model
row directly rather than going through the create path -- this one only
surfaced because the blind-spot tests call `add_grade` itself. Fixed in both
functions, mutation-tested.

Verified against the real gradebook: Midterm and Final both come back moderate
(9.4 and 5.4 points below the coursework average, respectively) across every
current course -- a real, plausible pattern, not a false positive from the
detector.

## A date, a time, and how long it runs

A grade's date can carry a **time** (`grades.due_time`), and a calendar-bound one
a **length** (`grades.duration_minutes`). The time reaches a task as its due time
and a block as its start; the length becomes the block's end.

**A length, not an end time**, and that is the whole reason this shape was
chosen. "The midterm is two hours" is what a student actually knows, and an end
*derived* from a start cannot contradict it — where a second stored column can,
and would need a rule saying so. `end <= start` is unrepresentable rather than
validated.

Each field only refines the one above it, so each clearing cascades: no date
means no time, and no time means no length. The cascade keys on **what the
request said**, not on the merged state — a blanket "no time, so no length" would
swallow *"set a length on an all-day grade"* into a silent no-op instead of
refusing it.

### The one case the sync cannot see

`sync_event` gets the grade's final state, where **"never had a time"** and
**"just lost one"** are identical — and they call for opposite things. Never
having one leaves a start the student typed on the calendar alone, because the
gradebook saying nothing is not the gradebook saying all-day. Taking one away
means the block should go back to all-day.

So `update_grade` reads `due_time` *before* the merge and calls
`forget_block_times` only when a time that existed was removed. Both directions
have a test named for them.

Where the grade has a time and no length, `move_start` moves the start and
**carries the existing end with it**: an exam marked 09:00–11:00 on the calendar
and re-timed to 14:00 on the grade would otherwise end three hours before it
began — a pair the API refuses, leaving a row nothing could edit afterwards. An
end that would run past midnight is dropped rather than wrapped, since an event
has one date.

## Which item is worth doing next

The average says where a course is; it does not say what to do about it.
`cheapest_path` ranks what is left by **leverage** — the course average with an
item at full marks minus the same average with it at zero, every other
outstanding item held constant. That difference is the share of the final
average the item controls, and it is the same whatever the others are assumed to
do, because their contribution appears in both halves and cancels.

It reuses `project_average` through a new pure `overrides` parameter rather than
by setting `grade.score` and putting it back. That matters more than it looks:
mutate-and-restore passes every value-based test, including one that re-reads
every score from the database, because the value is back before anybody looks.
What it cannot hide is `db.dirty` — setting a mapped attribute flags the row
whether or not the value ends up where it started, so the GET carries a pending
UPDATE that the next commit anywhere would flush. The test asserts on the
session, and it took a mutation to work that out.

### Ranked by rate, then by points — top three only

Hours come from the task a dated grade raised. The list is ordered by **points
per hour**, with points breaking ties beneath it, and cut to three.

An item with no estimate has no rate and is not given one: zero would sort it
last as though it paid nothing, infinity first as though it were free. Rated
items rank above unrated, and the unrated fall back to points among themselves.

> **This was ranked on points alone first, and the reason still stands.**
> Ranking on rate means an item with an estimate outranks every item without
> one, because nothing unrated has a rate to beat. Over the real courses that
> puts STAT_V 201's Lab 3 — 4.3 points, the only estimated item — above its
> Final Exam at 45. The rate ranking was asked for deliberately in full view of
> that, and the trade is recorded here rather than left to be rediscovered as a
> bug. It is why the panel keeps asking for the missing estimates: with one
> estimate across 23 outstanding items, the prompt is the feature.

The cut happens **after** the sort, and there is a test whose fixture creates
the heaviest item last so that cutting first would drop exactly the row that
should lead. Both the ranking and the cut are server-side, so the rule is one
thing in one place with tests on it rather than a slice in the component.

Bonus categories are excluded: they add on top of the average rather than
composing it, so chasing one is how you spend a weekend moving a number that was
never going to reach. Zero-leverage items are excluded too — offering work that
changes nothing is worse than offering none.

## What the final needs, and what it was projected to be

**The required final is a card beside the grade band** (D7). It is measured
against the course's own target, or the account default (`effective_target`). It
shows only while the final is still ahead: a current term, a weighted final,
unmarked, and not a transfer or a no-final course. The free calculator stays,
as "Try another target". The Attention panel says what the final needs too
(D13).

**Before the final, we projected 83.0%. You got 82%** (D34). When a final is
marked or a result entered, the projection from just before is kept on the
course. It is the review loop the grade band was always missing: whether
these projections are any good is only knowable afterwards.

## Grading schemes

Some courses publish more than one rubric: "the better of 40/60 or 20/80".
`scheme_service` projects each scheme beside the course's own grade, with the
working shown (D18). A scheme has its own weights, and two rules:
`drop_lowest` leaves out a category's N lowest marks, and `replace_with` lets a
higher category average stand in for another ("the final replaces the midterm
if higher").

**A scheme with the course's own weights and no rules must give exactly the
course's average.** That is tested, so a scheme can only ever differ for a
reason it can show.

**A scheme can count as the grade** (D25, D29). `counting_scheme_id` makes it the
figure the course reports. The stored average is recomputed in the same
commit, so every screen moves together. That fixed a real overshoot: a course weighted over 100 was told
its final needed 191% when 96.16% would do.

## From a syllabus

**Upload a syllabus and the term builds itself** (D16): assessments, weights,
dated exams and due dates. Three rules carry it:
- **Nothing becomes a record without confirmation.** The parse is shown with
  every field editable, and only what is confirmed is written. A hallucinated
  weight in a grade projection is exactly the failure this exists to avoid.
- **Checks are deterministic and run on every parse,** so the screen can point
  at what to look at: weights not summing to 100, a weighted assessment with no
  date that isn't marked TBA, a date outside the term.
- **A syllabus can add to a course you already have, and only add** (D27, D30).
  Matching rows are left alone and nothing is changed or removed, so a second
  upload can't undo a correction you made.

**What is sent to a model is narrow on purpose.** `Intake/services/llm.py` is the
one door, provider-agnostic and named by task (`extract_document`). Only
syllabi go through it: course documents, with nothing identifying a user in the
request. Personal documents are not sent (Phase 1 D3), and that is why T4 upload
was scrapped (Phase 2 D20). Original files are kept in a bucket when one is
configured (D24), and the account purge deletes them first.

Parses are capped per day (`LLM_PARSES_PER_DAY`, default 10). **The cap once
compared a UTC date with the student's local one**, so every evening it counted
nothing. CI caught it by running the same commit after midnight UTC. Tests in
UTC-12 and UTC+14 now fail at any hour if it returns. The feature hides itself
until a key is set.

The reader also picks up **prerequisites**, filed only once you confirm them.
The syllabus's own sentence stays with you and never reaches the catalogue.

## The degree audit

Grades → Degree audit (D31). You enter the requirements and how your courses map
onto them once, and it shows what is done, in progress and missing. It is
computed on every read and never stored, so it can't drift from the courses
it describes.

**An equivalence replaces its sources.** It applies when every source course is
on your record, takes the least-finished one's status, and stands in for them.
So a course is never counted both as itself and as what it maps to.

## Prerequisites, and the shared catalogue

**Each course is matched to the catalogue by campus and code when it is read**,
so it links itself as soon as the catalogue gains it, and the catalogue starts
empty. What is stored is only your own decision: a course picked by hand, or
"none". **Linking moves no grade, average or credit**; it is a pointer for
prerequisites.

**Your prerequisites are typed, and apply to you at once.** "CPSC 210 and one of
MATH 200, MATH 217", "6 credits of MATH 1xx", "CPSC 210 with 64%". They parse into
a small JSON tree (`utils/prerequisites.py`): a course with an optional minimum
grade, a number of credits by subject and level, or `all` and `any`. Codes are
stored without the campus suffix. Anything a tree can't hold, such as year
standing or "permission of the instructor", goes in the note beside it.

**Met, on track, or not met, per part, labelled by source.** Yours wins for you
when you have one, and both are shown. "Not met" always adds "exceptions are
sometimes made", and **nothing anywhere is refused** because of it (D3).
Adding a future course previews the shared rule.

Your rule is also a proposal. The owner reviews proposals as counts of accounts
with the rule tree alone, and only approved rules reach the shared catalogue.

## Rate your term

**End-of-term reviews** (D25), on the Grades page from 14 to 180 days after a
term ends. There are four questions per finished course: hours a week (0-80),
difficulty and clarity (1-5), and whether you would take it again. Answers lock
after 14 days. A course can be skipped.

**The opt-in adds your grade to the course's distribution**, and never locks. The
review holds no copy of the grade. The count is rebuilt whole by a definer
function, reading grades at that moment, into a table nothing can read, and
nothing is written for a course-term under 5 contributors. **Nothing is shown
yet:** distributions are Phase 3's.

## Still open

- A term retrospective when a term closes: what moved, what slipped, what you
  predicted against what you got. The kept projection (D34) is its first input.
- Pasting syllabus text rather than uploading a file; making the syllabus the
  default way to add a course, with manual entry a button away.
- Dropping `users.term_label` once every user has a first-year anchor.
- Whether semesters themselves should be editable. Safe, but there are two
  `Semester` enums to keep in step or collapse, and `SEMESTER_ORDER` is the
  part that would break. The working is in `next.md`.
