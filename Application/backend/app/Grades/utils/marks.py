"""The two facts every grade calculation shares, with no service attached.

Here rather than in grade_service so the scheme arithmetic (scheme_math) can
use them without importing the service that, in turn, uses it.
"""

MAX_COURSE_PERCENT = 100.0


def counts_toward_average(grade) -> bool:
    """Whether a grade is part of the arithmetic at all.

    A dropped mark -- the two lowest quizzes, say -- stays on the course so it
    can be seen and un-dropped later, but must not reach any average. One
    predicate rather than `not g.excluded` scattered across six call sites,
    because a single place that forgets it is a wrong grade shown confidently.
    """
    return not getattr(grade, "excluded", False)
