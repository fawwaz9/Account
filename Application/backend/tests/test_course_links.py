"""Where a course lives: Canvas, Piazza, a syllabus.

Two things are worth pinning down, and neither is the happy path.

The first is the scheme check. These render as anchors on the course page, so a
stored `javascript:` URL is script execution on your own page the next time you
click your own link -- and the API is reachable without the client, so the check
has to be here rather than only in the form.

The second is the JSON column. SQLAlchemy does not track a mutation made
*inside* one, so a service that appended to the list would return a
saved-looking response and persist nothing. The same fault has already shipped
twice in this codebase: `skipped_dates` and `users.preferences`.
"""
import uuid

import pytest
from pydantic import ValidationError

from app._database.models import CourseModel
from app.Grades.schemas.course import CourseCreate, CourseLink, CourseUpdate
from app.Grades.services.course_service import create_course, get_course, update_course
from conftest import make_course


def link(title="Canvas", url="https://canvas.ubc.ca"):
    return CourseLink(title=title, url=url)


def course_payload(**overrides):
    fields = {
        "code": "CPSC 221", "name": "Data Structures", "year": 3,
        "semester": "Fall", "credits": 3.0,
    }
    fields.update(overrides)
    return CourseCreate(**fields)


# ------------------------------------------------------- the scheme check --

@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JavaScript:alert(1)",          # the check lowercases, or it is no check
    "data:text/html;base64,PHNjcmlwdD4=",
    "ftp://files.example.com",
    "vbscript:msgbox(1)",
])
def test_a_link_that_is_not_http_is_refused(url):
    with pytest.raises(ValidationError):
        CourseLink(title="Canvas", url=url)


@pytest.mark.parametrize("url", ["https://canvas.ubc.ca", "http://piazza.com/x"])
def test_http_and_https_are_accepted(url):
    assert CourseLink(title="Canvas", url=url).url == url


@pytest.mark.parametrize("url", ["HTTPS://canvas.ubc.ca", "Http://piazza.com/x"])
def test_an_allowed_scheme_is_accepted_whatever_its_case(url):
    """This is what makes the lowercasing load-bearing, and it took a mutation
    to notice. Refusing "JavaScript:" proves nothing about case, because that
    scheme is absent from the allowlist in either case -- drop the .lower() and
    the only thing that breaks is a user who typed HTTPS in capitals.
    """
    assert CourseLink(title="Canvas", url=url).url == url


def test_a_bare_domain_gets_https_rather_than_a_refusal():
    """The likeliest mistake, and the only unambiguous one."""
    assert CourseLink(title="Canvas", url="canvas.ubc.ca").url == "https://canvas.ubc.ca"


def test_a_scheme_is_never_prefixed_onto_something_that_has_one():
    """Otherwise the fix above becomes the hole it was meant to close --
    "https://javascript:alert(1)" would sail past the scheme check."""
    with pytest.raises(ValidationError):
        CourseLink(title="x", url="javascript:alert(1)")


def test_a_link_needs_both_a_name_and_an_address():
    with pytest.raises(ValidationError):
        CourseLink(title="   ", url="https://canvas.ubc.ca")
    with pytest.raises(ValidationError):
        CourseLink(title="Canvas", url="   ")


# ------------------------------------------------------ storing and editing --

def test_a_course_starts_with_no_links(db, user):
    course = create_course(db, user.id, course_payload())
    assert course.links == []


def test_links_given_at_creation_are_kept(db, user):
    course = create_course(db, user.id, course_payload(links=[link()]))

    assert course.links == [{"title": "Canvas", "url": "https://canvas.ubc.ca"}]


def test_links_are_replaced_whole_on_update(db, user):
    course = make_course(db, user.id, "CPSC 221")
    update_course(db, user.id, course.id, CourseUpdate(links=[link()]))

    update_course(db, user.id, course.id, CourseUpdate(
        links=[link("Piazza", "https://piazza.com/ubc")]
    ))

    fresh = get_course(db, user.id, course.id)
    assert fresh.links == [{"title": "Piazza", "url": "https://piazza.com/ubc"}]


def test_an_update_that_does_not_mention_links_leaves_them_alone(db, user):
    """A partial update must not null the column -- the same rule schedule_as
    already follows on a grade."""
    course = make_course(db, user.id, "CPSC 221")
    update_course(db, user.id, course.id, CourseUpdate(links=[link()]))

    update_course(db, user.id, course.id, CourseUpdate(name="Renamed"))

    fresh = get_course(db, user.id, course.id)
    assert fresh.links == [{"title": "Canvas", "url": "https://canvas.ubc.ca"}]
    assert fresh.name == "Renamed"


def test_the_write_survives_a_round_trip_through_the_database(db, user):
    """The silent one. A service that appended to course.links instead of
    reassigning it passes every assertion above -- the object in memory looks
    right -- and persists nothing. Only re-reading the row catches it.
    """
    course = make_course(db, user.id, "CPSC 221")
    update_course(db, user.id, course.id, CourseUpdate(links=[link()]))

    db.expire_all()
    reread = db.query(CourseModel).filter(CourseModel.id == course.id).first()
    assert reread.links == [{"title": "Canvas", "url": "https://canvas.ubc.ca"}]


def test_an_exact_duplicate_is_dropped_but_a_repeated_title_is_not(db, user):
    """Two Canvas links is a real thing for a cross-listed course. The same
    link twice is a double-click."""
    course = create_course(db, user.id, course_payload(links=[
        link(),
        link(),
        link("Canvas", "https://canvas.ubc.ca/courses/2"),
    ]))

    assert [entry["url"] for entry in course.links] == [
        "https://canvas.ubc.ca",
        "https://canvas.ubc.ca/courses/2",
    ]


def test_another_users_course_cannot_have_links_set(db, user):
    from conftest import make_user
    intruder = make_user(db, "someone-else@example.com")
    course = make_course(db, user.id, "CPSC 221")

    assert update_course(db, intruder.id, course.id, CourseUpdate(links=[link()])) is None
