"""Courses: create, read, edit, delete and search, with each response's figures.

Responses read the stored average and attach the derived fields (letter, grade
points, term bucket, reported average) onto the row under their own names, never
writing to a mapped column during a read.
"""

import uuid
from sqlalchemy.orm import Session, selectinload
from app._database.models import (
    SyllabusParseModel,
    CourseCategoryWeightModel,
    CourseModel,
    GradeModel,
    RecurringTaskModel,
    ReminderModel,
    TransactionModel,
    UserModel,
)
from app.Grades.schemas.course import CourseCreate, CourseUpdate, clean_links
from app.Grades.services.grade_service import (
    calculate_gpa_points,
    calculate_grade_category_average,
    category_points,
    calculate_letter_grade,
    forecast_before,
    keep_projection,
    update_category_weights as apply_category_weights,
)
from app.Grades.utils.enums import SEMESTER_ORDER
from app.Grades.utils.terms import course_result_grade, term_bucket
from app.shared.dates import user_today


def courses_with_marks(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Return the ids of a user's courses that have at least one counted mark.

    One grouped query for a whole list; dropped grades do not count.

    Args:
        db: Open database session.
        user_id: Whose courses to check.

    Returns:
        The ids of courses with a scored, non-dropped grade.
    """
    rows = (
        db.query(GradeModel.course_id)
        .join(CourseModel, CourseModel.id == GradeModel.course_id)
        .filter(
            CourseModel.user_id == user_id,
            GradeModel.score.isnot(None),
            GradeModel.excluded.is_(False),
        )
        .distinct()
        .all()
    )
    return {course_id for (course_id,) in rows}


def course_has_marks(db: Session, course_id: uuid.UUID) -> bool:
    """Return whether one course has at least one counted mark.

    Args:
        db: Open database session.
        course_id: The course to check; the caller has already checked ownership.

    Returns:
        True when a non-excluded grade has a score.
    """
    return (
        db.query(GradeModel.id)
        .filter(
            GradeModel.course_id == course_id,
            GradeModel.score.isnot(None),
            GradeModel.excluded.is_(False),
        )
        .first()
        is not None
    )


def attach_course_summary(
    course: CourseModel,
    current_school_year: int | None = None,
    current_semester: str | None = None,
    has_marks: bool = True,
) -> CourseModel:
    """Attach the derived fields every course response carries, from loaded columns.

    Sets `letter_grade`, `grade_points`, `term_bucket` and `reported_average` on the
    row; safe to map over a list, since it never touches `course.grades`.

    Args:
        course: The course row; only attributes are set, nothing is written.
        current_school_year: The student's school year now.
        current_semester: The student's term now.
        has_marks: Whether the course has a counted mark; False reports the average
            as None.

    Returns:
        The same course.
    """
    course.letter_grade = calculate_letter_grade(course)
    course.grade_points = calculate_gpa_points(course_result_grade(course))
    course.term_bucket = term_bucket(course, current_school_year, current_semester)
    # Attached under its own name, never assigned onto `course.average`: that
    # column is mapped, and writing to it during a read is how a GET starts
    # changing data.
    course.reported_average = course.average if has_marks else None
    return course


def attach_category_averages(course: CourseModel) -> CourseModel:
    """Attach per-category averages and points for the course detail response.

    Reads `course.grades`, so use it for single-course reads only.

    Args:
        course: The course row; only attributes are set.

    Returns:
        The same course, with `category_averages` and `category_points`.
    """
    course.category_averages = {
        category: calculate_grade_category_average(course, category)
        for category in course.category_weights
    }
    # What each category contributes, in marks out of its weight. Sent rather
    # than derived, because deriving it meant multiplying the rounded average
    # above by the weight -- a second rounding, which showed 11.82 for a figure
    # that is exactly 11.825.
    course.category_points = {
        category: category_points(course, category)
        for category in course.category_weights
    }
    return course


def current_term_of(db: Session, user_id: uuid.UUID) -> tuple[int | None, str | None]:
    """Return the user's current (school year, semester), or (None, None) if unknown.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        (school year, semester) from the user's academic status; either may be None.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None, None
    return user.current_school_year, user.current_semester


def create_course(db: Session, user_id: uuid.UUID, course_data: CourseCreate):
    """Create a course with its category weights and links.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_data: The validated new course.

    Returns:
        The new course with every derived field attached, or None when the user does
        not exist.

    Raises:
        ValueError: If the user already has a course with exactly this code.

    Note:
        Commits. The duplicate check is check-then-insert; the unique index on
        (user_id, code) is what finally holds.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    existing = db.query(CourseModel).filter(
        CourseModel.user_id == user_id, CourseModel.code == course_data.code
    ).first()
    if existing:
        raise ValueError("course code already exists")

    course = CourseModel(
        id=uuid.uuid4(),
        user_id=user_id,
        code=course_data.code,
        name=course_data.name,
        semester=course_data.semester,
        year=course_data.year,
        credits=course_data.credits,
        required=course_data.required,
        professor=course_data.professor,
        section=course_data.section,
        final_grade=course_data.final_grade,
        target_grade=course_data.target_grade,
        start_date=course_data.start_date,
        end_date=course_data.end_date,
        no_final=course_data.no_final,
        transfer_credit=course_data.transfer_credit,
        archived=course_data.archived,
        links=clean_links(course_data.links),
    )
    db.add(course)
    db.flush()  # gets course.id available before commit if needed

    for category, weight in course_data.category_weights.items():
        db.add(CourseCategoryWeightModel(course_id=course.id, category=category.value, weight=weight))

    db.commit()
    db.refresh(course)
    year, semester = current_term_of(db, user_id)
    return attach_category_averages(
        attach_course_summary(course, year, semester, course_has_marks(db, course.id))
    )


def get_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Return one course with its derived fields and per-category figures.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The course, or None when it is missing or another user's. The stored average
        is returned as is, never recomputed.
    """
    course = db.query(CourseModel).filter(
        CourseModel.id == course_id, CourseModel.user_id == user_id
    ).first()
    if course is None:
        return None

    # The stored `average` column is authoritative: every write path
    # (add_grade, update_grade, delete_grade, record_grade,
    # update_category_weights) recomputes and commits it. Recomputing here too
    # meant this route and the course list could return different numbers for
    # the same course, since get_all_courses reads the stored value.
    year, semester = current_term_of(db, user_id)
    return attach_category_averages(
        attach_course_summary(course, year, semester, course_has_marks(db, course.id))
    )


def get_all_courses(db: Session, user_id: uuid.UUID):
    """Return all of a user's courses, sorted by school year, term and code.

    Grades and weights are loaded in two extra queries for the whole list.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        Every course with its summary fields attached; empty when there are none.
    """
    # Grades and weights are loaded with the courses, in two extra queries for
    # the whole list rather than two per course. Every caller here reads both --
    # attach_course_summary and the dashboard rollup do -- so lazy loading was
    # a guaranteed N+1, not a possible one. selectinload rather than joinedload
    # because these are collections: a join would multiply each course row by
    # its grades and make the sort and the summary work on duplicates.
    courses = (
        db.query(CourseModel)
        .options(
            selectinload(CourseModel.grades),
            selectinload(CourseModel.category_weight_rows),
        )
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    # One lookup for the whole list, not one per course.
    year, semester = current_term_of(db, user_id)

    # Sorted here so term order lives in one place. The client groups consecutive
    # runs rather than carrying its own idea of what follows Fall.
    courses.sort(key=lambda c: (c.year, SEMESTER_ORDER.get(c.semester, 0), c.code))
    marked = courses_with_marks(db, user_id)
    return [
        attach_course_summary(course, year, semester, course.id in marked)
        for course in courses
    ]


def update_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: CourseUpdate):
    """Apply a partial edit to a course, with any weight change, in one transaction.

    Links are replaced whole. Field changes stay pending until the weights, if sent,
    have been checked, so a rejected weight change leaves the course untouched.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        data: The fields to change; omitted ones stay.

    Returns:
        The updated course with every derived field attached, or None when it is
        missing or another user's.

    Raises:
        ValueError: If the merged weights are out of range.

    Note:
        Commits. The merged course is not re-validated against the create rules, and a
        code already used by another of the user's courses fails at commit.
    """
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    update_data = data.model_dump(exclude_unset=True)
    category_weights = update_data.pop("category_weights", None)
    # Taken off the dict and applied from the typed models below. model_dump
    # would hand back plain dicts, which cannot be deduplicated by title and
    # url without re-reading their keys.
    update_data.pop("links", None)

    before = forecast_before(course)
    for key, value in update_data.items():
        setattr(course, key, value)
    keep_projection(course, before, user_today(db, user_id))

    if data.links is not None:
        # Assigned whole, and that is the point rather than a style choice.
        # SQLAlchemy does not see a mutation made *inside* a JSON column, so
        # appending to course.links would return a saved-looking response and
        # persist nothing.
        course.links = clean_links(data.links)

    if category_weights is not None:
        # Left pending above and committed here, in one transaction with the
        # weights. The field changes used to be committed *first*, so a weight
        # the validator rejects returned a 400 that had already changed the
        # record -- the caller saw a failure and the row moved anyway.
        apply_category_weights(db, user_id, course_id, category_weights)
    else:
        db.commit()

    db.refresh(course)

    # db.refresh expires the instance, so recompute after the last one rather
    # than relying on what get_course attached before the writes.
    year, semester = current_term_of(db, user_id)
    return attach_category_averages(
        attach_course_summary(course, year, semester, course_has_marks(db, course.id))
    )


def delete_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Delete a course with its grades, weights, events, tasks and other children.

    Expenses, reminders, repeating tasks and syllabus parses that only mention the
    course are kept, with the mention cleared.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The deleted course row, or None when it is missing or another user's.

    Note:
        Commits.
    """
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    # What only *mentions* the course is kept, with the mention cleared: money
    # tagged to it happened, a reminder is still a reminder, and a repeating
    # task is a standing decision. Its grades, timetable and tasks are the
    # course itself and go with it (the ORM cascades). Without these three,
    # deleting any course with a tagged expense, a reminder or a repeating task
    # failed the foreign key, as a 500. Found by test_noninterference.py.
    db.query(TransactionModel).filter(
        TransactionModel.user_id == user_id, TransactionModel.course_id == course_id,
    ).update({TransactionModel.course_id: None}, synchronize_session=False)
    db.query(ReminderModel).filter(
        ReminderModel.user_id == user_id, ReminderModel.course_id == course_id,
    ).update({ReminderModel.course_id: None}, synchronize_session=False)
    db.query(RecurringTaskModel).filter(
        RecurringTaskModel.user_id == user_id, RecurringTaskModel.course_id == course_id,
    ).update({RecurringTaskModel.course_id: None}, synchronize_session=False)
    db.query(SyllabusParseModel).filter(
        SyllabusParseModel.user_id == user_id, SyllabusParseModel.course_id == course_id,
    ).update({SyllabusParseModel.course_id: None}, synchronize_session=False)
    db.delete(course)
    db.commit()
    return course



def search_courses(db: Session, user_id: uuid.UUID, query: str):
    """Return the user's courses whose code or name contains the query, ignoring case.

    `%` and `_` in the query match literally.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        query: Text to find.

    Returns:
        Matching courses from any term with their summary fields, or None when the user
        does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    # `%` and `_` are wildcards to LIKE, so without escaping them a search for
    # "_" matches every course and "100%" matches nothing it should. Not an
    # injection -- the value is parameterised either way -- just a search that
    # quietly does something other than what was typed.
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_query = f"%{escaped}%"
    matches = (
        db.query(CourseModel)
        .filter(
            CourseModel.user_id == user_id,
            (CourseModel.code.ilike(like_query, escape="\\"))
            | (CourseModel.name.ilike(like_query, escape="\\")),
        )
        .all()
    )
    # Search reaches every term, so results need their bucket to be labelled.
    marked = courses_with_marks(db, user_id)
    return [
        attach_course_summary(
            course, user.current_school_year, user.current_semester, course.id in marked
        )
        for course in matches
    ]
