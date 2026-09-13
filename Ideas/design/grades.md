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
| `calculate_current_average` | `services/grade_service.py:287` | the course average, from marked work only |
| `bonus_contribution` | `services/grade_service.py:267` | marks banked on top of the 100 |
| `project_average` | `services/grade_service.py:403` | the same arithmetic with unmarked work at an assumed score |
| `calculate_grade_band` | `services/grade_service.py:444` | best and worst finish, per unmarked item |
| `calculate_required_final` | `services/grade_service.py:483` | what the final has to be |
| `category_points` | `services/grade_service.py:544` | marks out of a category's weight, in `Decimal` |
| `term_bucket`, `course_result_grade`, `effective_target` | `utils/terms.py` | placing a course in time, and judging it |
| `weight_problems` | `utils/weights.py` | weights that do not add up |
| `resolve_course` | `services/course_lookup.py` | a course from a typed code; three callers |
| `sync_schedule_for_grade` | `services/grade_schedule.py` | a dated grade's task or calendar block |

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

## Still open

Category blind spots across courses; a term retrospective once a term closes;
the syllabus parser, deliberately late because it depends on due dates, category
weights and the tokenizer all being settled — they now are.
