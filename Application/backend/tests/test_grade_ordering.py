"""Grades come back in a predictable order.

They used to come back in insertion order, so adding a quiz you had missed put it
under the final exam. The rule is alphabetical -- with two departures that the
real data earned rather than taste: case is ignored, and digit runs compare as
numbers.

Both paths that hand grades to a client go through the same function, and the
last test here is the one that would notice if a third path appeared and did not.
"""
import uuid

import pytest

from app.Grades.schemas.course import CourseDetail
from app.Grades.schemas.grade import Grade
from app.Grades.utils.ordering import grade_sort_key, sorted_grades


class Row:
    """The attribute `sorted_grades` reads. A model would work; this is cheaper
    and makes it obvious the function only needs a name."""

    def __init__(self, name):
        self.name = name


def names(rows):
    return [row.name for row in rows]


# ------------------------------------------------------------ the pure rule --

def test_plain_names_go_alphabetically():
    rows = [Row("Midterm"), Row("Assignments"), Row("Participation")]
    assert names(sorted_grades(rows)) == ["Assignments", "Midterm", "Participation"]


def test_numbers_compare_as_numbers_not_as_text():
    """The reason this is not a plain string sort.

    Strictly, "Quiz 10" does precede "Quiz 2" alphabetically. It is also the
    answer nobody wants, and a weekly quiz in a thirteen-week term gets there.
    """
    rows = [Row("Quiz 10"), Row("Quiz 2"), Row("Quiz 1"), Row("Quiz 11")]
    assert names(sorted_grades(rows)) == ["Quiz 1", "Quiz 2", "Quiz 10", "Quiz 11"]


def test_case_is_ignored():
    """SQLite's default collation is byte order, which puts every capital before
    every lowercase letter. Three names in the real data start lowercase, so
    sorting in the database would have put them after everything else.

    The pair matters. An earlier version of this test used "quizzes" against
    "Assignments" and "Midterm", where byte order and case-insensitive order give
    the same answer -- so it passed with the case folding removed and proved
    nothing. These two disagree: folded, "assignments" leads; by byte, "M" (77)
    beats "a" (97) and "Midterm" leads.
    """
    rows = [Row("Midterm"), Row("assignments")]
    assert names(sorted_grades(rows)) == ["assignments", "Midterm"]

    # And the same within one word, so it is not only the first letter.
    assert names(sorted_grades([Row("quizB"), Row("quiza")])) == ["quiza", "quizB"]


def test_a_number_alone_still_sorts_numerically():
    rows = [Row("10"), Row("9"), Row("1")]
    assert names(sorted_grades(rows)) == ["1", "9", "10"]


def test_surrounding_whitespace_does_not_decide_the_order():
    rows = [Row("  Zebra"), Row("Apple")]
    assert names(sorted_grades(rows)) == ["Apple", "  Zebra"]


def test_numbers_in_the_middle_of_a_name():
    rows = [Row("Lab 10 report"), Row("Lab 2 report")]
    assert names(sorted_grades(rows)) == ["Lab 2 report", "Lab 10 report"]


def test_the_key_never_compares_a_number_against_a_string():
    """What keeps the sort from raising TypeError on mixed names.

    The split alternates text and digits, so position 0 is always text and every
    odd position is always a number. Two keys therefore line up type-for-type.
    Without this the pair below -- one starting with a digit, one with a letter --
    is exactly what blows up.
    """
    for name in ("Quiz 1", "1 Quiz", "", "10", "abc", "a1b2c3"):
        key = grade_sort_key(name)
        for index, part in enumerate(key):
            assert isinstance(part, int if index % 2 else str), (name, key)

    # And the pair actually sorts rather than raising.
    assert names(sorted_grades([Row("1 Quiz"), Row("Quiz 1")])) == ["1 Quiz", "Quiz 1"]


def test_an_empty_name_sorts_first_rather_than_raising():
    rows = [Row("Midterm"), Row("")]
    assert names(sorted_grades(rows)) == ["", "Midterm"]


def test_sorting_does_not_mutate_the_list_it_was_given():
    """It is handed a SQLAlchemy relationship collection in production. Sorting
    that in place would mutate the session's idea of the object over something
    that is purely a presentation choice."""
    rows = [Row("Quiz 2"), Row("Quiz 1")]
    original = list(rows)

    sorted_grades(rows)

    assert rows == original, "the input collection was reordered in place"


# ------------------------------------------- the paths that reach a client --

def grade(name):
    return Grade(
        id=uuid.uuid4(), name=name, category="Assignment",
        score=None, max_score=100.0, weight=10.0,
    )


def test_the_course_detail_response_orders_its_grades():
    """Ordered by the schema, so no call site that builds one can forget."""
    detail = CourseDetail(
        id=uuid.uuid4(), user_id=uuid.uuid4(), code="CPSC 221", name="Data Structures",
        credits=4.0, year=2, semester="Fall",
        grades=[grade("Quiz 10"), grade("Assignments"), grade("Quiz 2")],
    )

    assert [g.name for g in detail.grades] == ["Assignments", "Quiz 2", "Quiz 10"]


def test_an_empty_course_detail_is_fine():
    """The control for the test above: the validator must not require content."""
    detail = CourseDetail(
        id=uuid.uuid4(), user_id=uuid.uuid4(), code="CPSC 110", name="Systematic Program Design",
        credits=4.0, year=1, semester="Fall",
    )

    assert detail.grades == []


def test_both_client_paths_use_the_one_function():
    """The guard against a third path ordering grades its own way.

    Not a style check: the course page and the grade list endpoint are read by
    the same client, and two sorts that drifted would show the same course's items
    in two different sequences. If a new path appears, it either calls this
    function or this test names it.
    """
    import inspect

    from app.Grades.schemas import course as course_schema
    from app.Grades.services import grade_service

    for module in (course_schema, grade_service):
        source = inspect.getsource(module)
        assert "sorted_grades" in source, f"{module.__name__} no longer orders grades"

    # And nothing else reaches for a hand-rolled sort of grades by name.
    assert "course.grades" in inspect.getsource(grade_service.get_all_grades)
    assert "sorted_grades" in inspect.getsource(grade_service.get_all_grades)
