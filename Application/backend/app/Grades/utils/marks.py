"""The two facts every grade calculation shares: the course ceiling and what counts.

Kept apart from `grade_service` so `scheme_math` can use them without an import
cycle through the service.
"""

MAX_COURSE_PERCENT = 100.0
"""The most a course average can reach, in percent, however much bonus there is."""


def counts_toward_average(grade) -> bool:
    """Return whether a grade takes part in any average; a dropped grade does not.

    Args:
        grade: A grade row, or anything with an `excluded` attribute.

    Returns:
        False for a dropped (`excluded`) grade, True otherwise.
    """
    return not getattr(grade, "excluded", False)
