"""Warnings about a course's category weights that are worth showing the student.

Separate from the schema validators, which decide what the API accepts and stay
permissive (a course may be marked out of 101%).
"""

from app.Grades.utils.enums import GradeCategory, is_additive, scoring_weight

#: Below this a category is probably missing.
MIN_EXPECTED_TOTAL = 100.0
#: Real bonus runs a few percent, so past this it reads as a typo. The 101% and
#: 104.71% courses in a real gradebook stay silent.
MAX_EXPECTED_TOTAL = 110.0
#: A final worth less than this, next to a category worth at least
#: LARGE_CATEGORY, is almost certainly two weights entered the wrong way round.
LOPSIDED_FINAL = 5.0
LARGE_CATEGORY = 20.0
"""A category at least this heavy, beside a tiny final, suggests two weights swapped."""


def weight_problems(course) -> list[str]:
    """Return readable problems with a course's category weights, or an empty list.

    Flags a scoring total (bonus excluded) below `MIN_EXPECTED_TOTAL` or above
    `MAX_EXPECTED_TOTAL`, and a final under `LOPSIDED_FINAL` beside another category of
    at least `LARGE_CATEGORY`, which looks like two weights swapped. A course with no
    weights, or weights totalling 0, reports nothing.

    Args:
        course: A course row, read through its `category_weights`.

    Returns:
        One sentence per problem; empty when the weights look sound.
    """
    weights = course.category_weights
    if not weights:
        return []

    problems: list[str] = []
    # Bonus sits outside the 100 the course is marked out of, so it must not
    # count here. Summing everything made this check wrong in both directions:
    # 95% of real categories plus a 5% bonus reached 100 and stopped reporting
    # the category that really was missing, while a generous 15% bonus on a
    # correctly built course tripped the "looks like a typo" warning.
    total = round(scoring_weight(weights), 2)

    # A course with nothing entered at all is already reported as such; adding
    # "weights total 0%" on top is noise, not a second problem.
    if total == 0:
        return []

    if total < MIN_EXPECTED_TOTAL:
        problems.append(f"weights total {total:g}%, so a category may be missing")
    elif total > MAX_EXPECTED_TOTAL:
        problems.append(f"weights total {total:g}%, which looks like a typo")

    # A total check alone cannot catch a swap: Final 1% with Other 40% sums to
    # exactly 100 and passes clean, which is how a real course sat wrong for
    # weeks. Compare the final against the largest other category instead.
    final_weight = weights.get(GradeCategory.FINAL.value, 0.0)
    other_weights = [
        weight for category, weight in weights.items()
        if category != GradeCategory.FINAL.value and not is_additive(category)
    ]
    biggest_other = max(other_weights, default=0.0)

    if 0 < final_weight < LOPSIDED_FINAL and biggest_other >= LARGE_CATEGORY:
        problems.append(
            f"the final is only {final_weight:g}% while another category is "
            f"{biggest_other:g}% -- are two weights swapped?"
        )

    return problems
