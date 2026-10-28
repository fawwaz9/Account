"""Grading-scheme arithmetic: a course and a list of components in, an average out.

One engine answers every scheme question: the live average from marked work, an
assumed average with unmarked work at a given score (the band and cheapest path),
and a what-if with chosen grades forced by id (the required final). With the
course's own weights and no rules it reproduces the course's own figures. Pure: no
session, and no import of the services that read it.
"""

from dataclasses import dataclass

from app.Grades.utils.enums import is_additive
from app.Grades.utils.marks import MAX_COURSE_PERCENT, counts_toward_average


def _value(category) -> str:
    """Return an enum's string value, or the argument if it is already a string."""
    return category.value if hasattr(category, "value") else category


def category_average(
    course, category: str, drop_lowest: int = 0, fill: float | None = None, overrides: dict | None = None,
) -> tuple[float | None, int]:
    """Return a category's point-weighted average and how many items were dropped.

    Dropped (`excluded`) grades and items with no maximum never count. Each counted
    item scores, in order of precedence: its override, its mark, or `fill` of its
    maximum when unmarked. The lowest `drop_lowest` by percentage are then dropped,
    always keeping at least one.

    Args:
        course: Course row whose `grades` are read.
        category: Category name.
        drop_lowest: How many of the lowest-scoring items to drop.
        fill: Fraction (0-1) of its maximum an unmarked item is assumed to score; None
            counts marked items only (the live average).
        overrides: Grade id to a forced fraction (0-1) of its maximum.

    Returns:
        (average percentage rounded to 2 places, number dropped); the average is None
        when nothing in the category counts.
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
    """The working for one component of a scheme projection.

    Attributes:
        category: The component's category.
        weight: Its weight in percent.
        average: The category's average after drops and replacement; None when unknown.
        dropped: How many lowest items were dropped.
        replaced_by: The category whose higher average replaced this one, or None.
    """
    category: object
    weight: float
    average: float | None
    dropped: int
    replaced_by: object | None


def project(
    course, components, fill: dict | None = None, overrides: dict | None = None, precise: bool = False,
) -> tuple[float, list[Line]]:
    """Return the course average under a scheme's components, and the working.

    A category missing from `fill` is live; one in `fill` scores its unmarked items at
    that fraction, and when it has nothing at all it takes the fraction whole. A
    `replace_with` swaps in the other category's average when that is higher. Scoring
    weights divide by at most `MAX_COURSE_PERCENT`; bonus categories add on top; the
    result is capped at 100.

    Args:
        course: Course row whose `grades` are read.
        components: Anything with `category`, `weight`, `drop_lowest` and
            `replace_with`.
        fill: Category to an assumed fraction (0-1); `{}` gives the live average and 1.0
            everywhere the best case.
        overrides: Grade id to a forced fraction (0-1) of its maximum.
        precise: True skips the final rounding, so a search cannot mistake rounding for
            reaching its target.

    Returns:
        (average percentage, one `Line` per component); the average is 0.0 when no
        category has anything to count.
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
    """Return a `fill` assuming the same fraction in every category the components name.

    Args:
        components: The scheme's components.
        fraction: Assumed share (0-1) of each maximum.

    Returns:
        Category name to `fraction`.
    """
    return {_value(c.category): fraction for c in components}
