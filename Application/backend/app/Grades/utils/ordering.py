"""Display order of a course's grades: by name, ignoring case, numbers as numbers.

Both the course detail response and the grade list use this one rule, so the two
always agree.
"""
import re


#: Split on runs of digits, keeping them. "Quiz 10" -> ["quiz ", "10", ""].
_CHUNKS = re.compile(r"(\d+)")


def grade_sort_key(name: str) -> tuple:
    """Return a sort key ordering names alphabetically, digit runs read as numbers.

    "Quiz 2" sorts before "Quiz 10", and case is ignored.

    Args:
        name: A grade's name.

    Returns:
        A tuple alternating lower-cased text parts and integer digit runs, so two keys
        only ever compare text with text and numbers with numbers.
    """
    parts = _CHUNKS.split(name.strip().lower())
    # Odd indices are the digit runs, by construction of the split.
    return tuple(
        int(part) if index % 2 else part
        for index, part in enumerate(parts)
    )


def sorted_grades(grades):
    """Return the grades in display order as a new list, never sorting in place.

    Args:
        grades: Grade rows, such as a course's `grades` relationship.

    Returns:
        A new list ordered by `grade_sort_key` of each name.

    Note:
        Sorting a relationship collection in place would mutate the session's view of
        the course and could be flushed; the order is derived on every read.
    """
    return sorted(grades, key=lambda grade: grade_sort_key(grade.name))
