"""Sanity checks on a course's category weights.

Kept separate from the schema validators: those decide what the API will
*accept*, which has to stay permissive because a course marked out of 101% is
legitimate. These decide what is worth pointing out to the student.
"""

from app.Grades.utils.enums import GradeCategory

#: Below this a category is probably missing.
MIN_EXPECTED_TOTAL = 100.0
#: Real bonus runs a few percent, so past this it reads as a typo. The 101% and
#: 104.71% courses in a real gradebook stay silent.
MAX_EXPECTED_TOTAL = 110.0
#: A final worth less than this, next to a category worth at least
#: LARGE_CATEGORY, is almost certainly two weights entered the wrong way round.
LOPSIDED_FINAL = 5.0
LARGE_CATEGORY = 20.0


def weight_problems(course) -> list[str]:
    """Human-readable problems with a course's weights, or an empty list."""
    weights = course.category_weights
    if not weights:
        return []

    problems: list[str] = []
    total = round(sum(weights.values()), 2)

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
        if category != GradeCategory.FINAL.value
    ]
    biggest_other = max(other_weights, default=0.0)

    if 0 < final_weight < LOPSIDED_FINAL and biggest_other >= LARGE_CATEGORY:
        problems.append(
            f"the final is only {final_weight:g}% while another category is "
            f"{biggest_other:g}% -- are two weights swapped?"
        )

    return problems
