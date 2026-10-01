"""How a list of grades is ordered.

Grades had no ordering at all: they came back in whatever order the database
returned them, which is insertion order in practice, so a course's items sat in
the sequence they happened to be typed in. Adding a quiz you had missed put it
at the bottom, under the final exam.

One rule, in one pure function, because it has to hold on both paths that hand
grades to a client -- the course detail response and the grade list endpoint --
and two sorts that drifted apart would be worse than none.
"""
import re


#: Split on runs of digits, keeping them. "Quiz 10" -> ["quiz ", "10", ""].
_CHUNKS = re.compile(r"(\d+)")


def grade_sort_key(name: str) -> tuple:
    """Alphabetical, case-insensitively, with numbers read as numbers.

    Two deliberate departures from a plain string sort, both earned by the data
    rather than invented:

    **Case-insensitive.** SQLite's default collation is byte order, which puts
    every capital before every lowercase letter -- so "assignments" would sort
    after "Quiz 1" rather than before it. Three of the names in use start
    lowercase, so this is not hypothetical.

    **Numbers compared as numbers.** Strictly, "Quiz 10" *does* precede "Quiz 2"
    alphabetically, and that is the answer nobody wants. A third of the names in
    use are numbered, and a weekly quiz in a thirteen-week term reaches ten, so
    the plain sort would start interleaving the moment it mattered. Comparing the
    digit runs numerically keeps "Quiz 2" before "Quiz 10" while leaving every
    unnumbered name in ordinary alphabetical order.

    The key is a tuple of alternating text and number parts. Text parts are
    lower-cased strings and number parts are ints, and because the split always
    alternates, two keys only ever compare a string against a string and an int
    against an int.
    """
    parts = _CHUNKS.split(name.strip().lower())
    # Odd indices are the digit runs, by construction of the split.
    return tuple(
        int(part) if index % 2 else part
        for index, part in enumerate(parts)
    )


def sorted_grades(grades):
    """The same list, in display order. A new list -- never sorts in place.

    Sorting a SQLAlchemy relationship collection in place would mutate the
    session's idea of the object and risk a flush over something that is purely
    a presentation choice. There is no ordering column behind this and there
    should not be: it is derived from the name every time.
    """
    return sorted(grades, key=lambda grade: grade_sort_key(grade.name))
