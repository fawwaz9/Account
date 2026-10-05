"""Grading-scheme arithmetic, pure: a course and a list of components in, a figure out.

One engine for every question a scheme answers (Phase 1 D18, D25):

* **live** -- the average from what is marked, the way the course's own average
  is computed (categories with nothing marked stay out of the denominator);
* **assumed** -- every unmarked item scored `fill` of its max, and an empty
  weighted category taken whole at `fill`, the way the grade band and the
  cheapest path project the course's own weights;
* **what-if** -- particular grades forced to a value by id, which is how the
  required final asks "what if the final went this way".

With the course's own weights and no rules it gives exactly the course's own
figures in each mode; the tests hold it to that, so a scheme can only ever
differ for a reason it can show.

Components are anything with `category`, `weight`, `drop_lowest` and
`replace_with` -- SchemeComponent, in practice. No session, no service import:
grade_service and scheme_service both read it.
"""

from dataclasses import dataclass

from app.Grades.utils.enums import is_additive
from app.Grades.utils.marks import MAX_COURSE_PERCENT, counts_toward_average


def _value(category) -> str:
    return category.value if hasattr(category, "value") else category


def category_average(
    course, category: str, drop_lowest: int = 0, fill: float | None = None, overrides: dict | None = None,
) -> tuple[float | None, int]:
    """(average, how many dropped), point-weighted like the course's own.

    `fill` None is live: only marked items count, and nothing marked is None.
    `fill` a fraction scores every unmarked item at that share of its max. An
    override by grade id beats both. Drops are by percentage, keeping at least
    one, over whatever is being counted.
    """
    overrides = overrides or {}
    items = [
        g for g in course.grades
        if g.category == category and g.max_score > 0 and counts_toward_average(g)
    ]
    scored: list[tuple[float, float]] = []  # (score, max)
    for g in items:
        if g.id in overrides:
            scored.append((overrides[g.id] * g.max_score, g.max_score))
        elif g.score is not None:
            scored.append((g.score, g.max_score))
        elif fill is not None:
            scored.append((fill * g.max_score, g.max_score))
    if not scored:
        return None, 0
    dropped = min(drop_lowest, len(scored) - 1)
    if dropped:
        scored = sorted(scored, key=lambda pair: pair[0] / pair[1])[dropped:]
    total = sum(maximum for _, maximum in scored)
    weighted = sum((score / maximum) * 100 * maximum for score, maximum in scored)
    return round(weighted / total, 2), dropped


@dataclass
class Line:
    category: object
    weight: float
    average: float | None
    dropped: int
    replaced_by: object | None


def project(
    course, components, fill: dict | None = None, overrides: dict | None = None, precise: bool = False,
) -> tuple[float, list[Line]]:
    """(the course average under these components, the working per category).

    `fill` maps a category to the fraction its unmarked items -- and, when it
    has none at all, the category itself -- are assumed to score. A category
    missing from `fill` is live. So `{c: 1.0 for every c}` is the best case,
    `{}` is the live average. `precise` skips the last rounding, for a search
    that must not mistake a hundredth's rounding for having reached its target.
    """
    fill = fill or {}
    averages: dict[str, float | None] = {}
    drops: dict[str, int] = {}
    for c in components:
        key = _value(c.category)
        averages[key], drops[key] = category_average(course, key, c.drop_lowest, fill.get(key), overrides)
        if averages[key] is None and key in fill:
            # A weighted category with nothing in it yet is unknown, not zero, so
            # under an assumption it takes the assumption whole -- the grade
            # band's rule for the course's own weights.
            averages[key] = round(fill[key] * 100.0, 2)

    lines: list[Line] = []
    counted: dict[str, float | None] = {}
    for c in components:
        key = _value(c.category)
        value = averages[key]
        replaced_by = None
        if c.replace_with is not None and value is not None:
            other_key = _value(c.replace_with)
            other = averages.get(other_key)
            if other is None and other_key not in averages:
                other, _ = category_average(course, other_key, 0, fill.get(other_key), overrides)
            if other is not None and other > value:
                value, replaced_by = other, c.replace_with
        counted[key] = value
        lines.append(Line(c.category, c.weight, value, drops[key], replaced_by))

    scoring = [c for c in components if not is_additive(_value(c.category)) and counted[_value(c.category)] is not None]
    total_weight = sum(c.weight for c in scoring)
    earned = 0.0
    if total_weight > 0:
        weighted = sum(counted[_value(c.category)] * c.weight for c in scoring)
        earned = weighted / min(total_weight, MAX_COURSE_PERCENT)
    bonus = sum(
        (counted[_value(c.category)] or 0.0) * c.weight / 100.0
        for c in components if is_additive(_value(c.category)) and c.weight > 0
    )
    if not any(value is not None for value in counted.values()):
        return 0.0, lines
    total = earned + bonus if precise else round(earned + bonus, 2)
    return min(total, MAX_COURSE_PERCENT), lines


def everywhere(components, fraction: float) -> dict:
    """A `fill` that assumes `fraction` in every category the components name."""
    return {_value(c.category): fraction for c in components}
