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
    update_category_weights as apply_category_weights,
)
from app.Grades.utils.enums import SEMESTER_ORDER
from app.Grades.utils.terms import course_result_grade, term_bucket


def courses_with_marks(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Which of a user's courses have at least one mark that counts.

    One grouped query for the whole list rather than reading `course.grades`
    per course, so this can be used from the list endpoints without turning
    them into an N+1 -- and without depending on grades being eager-loaded.

    A dropped grade does not count, for the same reason it stays out of every
    average: it is on the course to be seen, not to be scored.
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
    """The single-course form of `courses_with_marks`, as an EXISTS."""
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
    """Attach the fields every course carries, cheaply.

    Reads only columns already loaded, so it is safe to map over a whole list
    without lazy-loading each course's grades. `has_marks` is passed in for the
    same reason -- working it out here would mean touching `course.grades`.
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
    """Compute the per-category averages CourseDetail exposes.

    Touches course.grades, so this is for single-course reads only -- mapping it
    over a list would lazy-load grades once per course.

    Set on the instance rather than defined as a CourseModel property because
    models.py is imported *by* grade_service -- a property calling back into it
    would be a circular import. This mirrors how `course.average` is attached.
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
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None, None
    return user.current_school_year, user.current_semester


def create_course(db: Session, user_id: uuid.UUID, course_data: CourseCreate):
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
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    update_data = data.model_dump(exclude_unset=True)
    category_weights = update_data.pop("category_weights", None)
    # Taken off the dict and applied from the typed models below. model_dump
    # would hand back plain dicts, which cannot be deduplicated by title and
    # url without re-reading their keys.
    update_data.pop("links", None)

    for key, value in update_data.items():
        setattr(course, key, value)

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