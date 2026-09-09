import uuid
from sqlalchemy.orm import Session
from app._database.models import CourseModel, CourseCategoryWeightModel, UserModel
from app.Grades.schemas.course import CourseCreate, CourseUpdate
from app.Grades.services.grade_service import (
    calculate_grade_category_average,
    calculate_letter_grade,
    update_category_weights as apply_category_weights,
)
from app.Grades.utils.enums import SEMESTER_ORDER
from app.Grades.utils.terms import term_bucket


def attach_course_summary(
    course: CourseModel,
    current_school_year: int | None = None,
    current_semester: str | None = None,
) -> CourseModel:
    """Attach the fields every course carries, cheaply.

    Reads only columns already loaded, so it is safe to map over a whole list
    without lazy-loading each course's grades.
    """
    course.letter_grade = calculate_letter_grade(course)
    course.term_bucket = term_bucket(course, current_school_year, current_semester)
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
        final_grade=course_data.final_grade,
        start_date=course_data.start_date,
        end_date=course_data.end_date,
    )
    db.add(course)
    db.flush()  # gets course.id available before commit if needed

    for category, weight in course_data.category_weights.items():
        db.add(CourseCategoryWeightModel(course_id=course.id, category=category.value, weight=weight))

    db.commit()
    db.refresh(course)
    year, semester = current_term_of(db, user_id)
    return attach_category_averages(attach_course_summary(course, year, semester))


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
    return attach_category_averages(attach_course_summary(course, year, semester))


def get_all_courses(db: Session, user_id: uuid.UUID):
    courses = db.query(CourseModel).filter(CourseModel.user_id == user_id).all()
    # One lookup for the whole list, not one per course.
    year, semester = current_term_of(db, user_id)

    # Sorted here so term order lives in one place. The client groups consecutive
    # runs rather than carrying its own idea of what follows Fall.
    courses.sort(key=lambda c: (c.year, SEMESTER_ORDER.get(c.semester, 0), c.code))
    return [attach_course_summary(course, year, semester) for course in courses]


def update_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: CourseUpdate):
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    update_data = data.model_dump(exclude_unset=True)
    category_weights = update_data.pop("category_weights", None)

    for key, value in update_data.items():
        setattr(course, key, value)

    db.commit()
    db.refresh(course)

    if category_weights is not None:
        apply_category_weights(db, user_id, course_id, category_weights)
        db.refresh(course)

    # db.refresh expires the instance, so recompute after the last one rather
    # than relying on what get_course attached before the writes.
    year, semester = current_term_of(db, user_id)
    return attach_category_averages(attach_course_summary(course, year, semester))


def delete_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    db.delete(course)
    db.commit()
    return course


def get_course_statistics(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    course = get_course(db, user_id, course_id)
    if not course:
        return None

    return {
        "course_id": course.id,
        "course_code": course.code,
        # Named `average` like every other route; this was the lone
        # `current_grade` for the same value.
        "average": course.average,
    }


def search_courses(db: Session, user_id: uuid.UUID, query: str):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    like_query = f"%{query}%"
    matches = (
        db.query(CourseModel)
        .filter(
            CourseModel.user_id == user_id,
            (CourseModel.code.ilike(like_query)) | (CourseModel.name.ilike(like_query)),
        )
        .all()
    )
    # Search reaches every term, so results need their bucket to be labelled.
    return [
        attach_course_summary(course, user.current_school_year, user.current_semester)
        for course in matches
    ]