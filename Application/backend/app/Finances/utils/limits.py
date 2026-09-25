"""What a category is allowed to spend in a given month.

Pure: numbers in, a number out, no session. Here rather than in the service
because the rule is read from two directions -- the budget summary computing a
month, and the writer deciding whether an override is still needed -- and the
layering rule in the design notes says a rule two callers share belongs in
`utils`.

Shaped on `effective_target` in `Grades/utils/terms.py`, which answers the same
question for a course's target grade: the specific value if there is one, the
standing default otherwise.
"""


def effective_limit(standing: float | None, override: float | None) -> float | None:
    """The limit in force: the month's own, else the category's standing one.

    **Tests for None, not for truthiness, and that is the whole function.** An
    override of `0` is a real instruction -- "nothing is meant to go here this
    month" -- under which any spending at all is over budget. A falsy check
    would read that as "no override", fall through to the standing limit, and
    report a month you had deliberately closed as if it were merely unbudgeted:
    the exact inversion of what was asked for, on the month someone cared enough
    about to set to zero.

    The same distinction runs through the column itself. `monthly_limit` is
    nullable so that "no limit" and "a limit of nothing" stay separable, and
    returning None here means the caller must not draw a bar rather than draw an
    empty one.
    """
    if override is not None:
        return override
    return standing
