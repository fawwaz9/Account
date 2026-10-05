from uuid import UUID
from fastapi import APIRouter, Query
from fastapi import HTTPException
from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.scheme import GradingScheme, SchemeComparison, SchemeWrite
from app.Grades.services import scheme_service
from app.Grades.schemas.course import CategoryWeightsUpdate, CourseCreate, Course, CourseDetail, CourseUpdate
from app.shared.errors import error_course, error_grade, error_user, responses
from app.Grades.services.course_service import (
    create_course,
    delete_course,
    get_all_courses,
    get_course,
    search_courses,
    update_course,
)
from app.Grades.schemas.dashboard import UserGradeDashboard
from app.Grades.schemas.blind_spot import CategoryBlindSpot
from app.Grades.schemas.grade import Grade, GradeCreate, GradeUpdate
from app.Grades.services.grade_service import (
    add_grade,
    add_grades_bulk,
    calculate_grade_band,
    calculate_required_final,
    delete_grade,
    get_all_grades,
    get_category_weights,
    get_grade,
    record_grade,
    update_category_weights,
    update_grade,
)
from app.Grades.services.course_lookup import resolve_course
from app.Grades.schemas.cheapest_path import CheapestPath
from app.Grades.services.cheapest_path import cheapest_path
from app.Grades.services.dash_services import DEFAULT_TARGET_GRADE, get_dashboard
from app.Grades.services.blind_spot_service import category_blind_spots
from app.shared import audit
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

@router.get(
    "/{user_id}/category-blind-spots",
    response_model=list[CategoryBlindSpot],
    responses=responses["user_404"],
)
def get_category_blind_spots(user_id: VerifiedUserId, db: DBSession):
    """A category consistently worse than the student's own average, in more
    than one course -- labs everywhere, not one hard class.

    Read-only, and derived fresh every time from the grades already stored:
    every marked item of a category, pooled across every graded course, against
    the same pooling across every category. Nothing is reported unless it shows
    up in at least two courses -- one course's weak labs is that course's
    problem, not a pattern.
    """
    findings = category_blind_spots(db, user_id)
    if findings is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return findings


@router.get("/{user_id}/grades/dashboard", response_model=UserGradeDashboard, responses=responses["user_404"])
def grade_dashboard(
    user_id: VerifiedUserId,
    db: DBSession,
    target_grade: float = Query(DEFAULT_TARGET_GRADE, ge=0, le=100),
):
    dashboard = get_dashboard(db, user_id, target_grade)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return dashboard

@router.get("/{user_id}/courses", response_model=list[Course], responses=responses["course_404"])
def get_courses(user_id: VerifiedUserId, db: DBSession):
    courses = get_all_courses(db, user_id)
    if courses is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    # An account with no courses yet is an empty collection, not an error --
    # the UI has an empty state for exactly this and never got to show it.
    return courses

@router.post("/{user_id}/courses", response_model=CourseDetail, responses={404: {"description": error_course["not_found"]}, 400: {"description": error_course["already_exists"]}})
def add_course(user_id: VerifiedUserId, course: CourseCreate, db: DBSession):
    try:
        new_course = create_course(db, user_id, course)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if new_course is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, "grades")
    return new_course

@router.get("/{user_id}/courses/search", response_model=list[Course], responses=responses["user_404"])
def search_course_list(
    user_id: VerifiedUserId,
    db: DBSession,
    query: str = Query(..., min_length=1, max_length=100),
):
    courses = search_courses(db, user_id, query)
    if courses is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return courses

@router.get("/{user_id}/courses/resolve", responses=responses["user_404"])
def resolve_course_from_text(
    user_id: VerifiedUserId,
    db: DBSession,
    text: str = Query(..., min_length=1, max_length=200),
):
    """Which course a typed line means, if any.

    Server-side because the matching rules -- letters as a prefix so "cpsc 210"
    finds "CPSC_V 210", and an ambiguous prefix resolving to nothing rather than
    guessing -- must not be reimplemented in TypeScript and allowed to drift
    from the ones quick capture and the omnibox use.
    """
    course = resolve_course(db, user_id, text)
    if course is None:
        return {"course_id": None, "code": None, "name": None}
    return {"course_id": course.id, "code": course.code, "name": course.name}


@router.get("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def get_single_course(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    # get_course recomputes the average, which raises if stored category
    # weights sum past 100. Without this guard that surfaced as a 500, while
    # the sibling /average route already returned 400 for the same cause.
    try:
        course = get_course(db, user_id, course_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return course

@router.patch("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def edit_course(user_id: VerifiedUserId, course_id: UUID, course: CourseUpdate, db: DBSession):
    try:
        updated_course = update_course(db, user_id, course_id, course)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return updated_course

@router.delete("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def remove_course(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    deleted_course = delete_course(db, user_id, course_id)
    if deleted_course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    # A course takes its grades with it, so this is the most destructive mutation
    # in the Grades module.
    audit.deletion(
        "course", user_id=user_id, target_id=course_id, detail=deleted_course.code,
    )
    return deleted_course

@router.get("/{user_id}/courses/{course_id}/category-weights", responses=responses["course_404"])
def get_course_category_weights(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    category_weights = get_category_weights(db, user_id, course_id)
    if category_weights is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return category_weights

@router.patch("/{user_id}/courses/{course_id}/category-weights", responses=responses["course_both"])
def edit_course_category_weights(user_id: VerifiedUserId, course_id: UUID, category_weights: CategoryWeightsUpdate, db: DBSession):
    try:
        updated_weights = update_category_weights(db, user_id, course_id, category_weights.category_weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_weights is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return updated_weights

@router.get("/{user_id}/courses/{course_id}/grade-band", responses=responses["course_both"])
def get_grade_band(
    user_id: VerifiedUserId,
    course_id: UUID,
    db: DBSession,
):
    """Best case, worst case and where the course sits between them."""
    try:
        return calculate_grade_band(db, user_id, course_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)


@router.get(
    "/{user_id}/courses/{course_id}/cheapest-path",
    response_model=CheapestPath,
    responses=responses["course_both"],
)
def get_cheapest_path(
    user_id: VerifiedUserId,
    course_id: UUID,
    db: DBSession,
):
    """What is left in this course, ranked by what it is worth doing."""
    try:
        return cheapest_path(db, user_id, course_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)


@router.get("/{user_id}/courses/{course_id}/required-final", responses=responses["course_both"])
def get_required_final_score(
    user_id: VerifiedUserId,
    course_id: UUID,
    db: DBSession,
    target_grade: float = Query(..., ge=0, le=100),
):
    try:
        return calculate_required_final(db, user_id, course_id, target_grade)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)

@router.get(
    "/{user_id}/courses/{course_id}/schemes",
    response_model=SchemeComparison,
    responses=responses["course_404"],
)
def compare_schemes(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """The course average under its own weights and under each alternative scheme."""
    result = scheme_service.compare(db, user_id, course_id)
    if result is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return result


@router.post(
    "/{user_id}/courses/{course_id}/schemes",
    response_model=GradingScheme,
    responses=responses["course_both"],
)
def add_scheme(user_id: VerifiedUserId, course_id: UUID, scheme: SchemeWrite, db: DBSession):
    result = scheme_service.create_scheme(db, user_id, course_id, scheme)
    if result is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return result


@router.put(
    "/{user_id}/courses/{course_id}/schemes/{scheme_id}",
    response_model=GradingScheme,
    responses=responses["course_both"],
)
def edit_scheme(user_id: VerifiedUserId, course_id: UUID, scheme_id: UUID, scheme: SchemeWrite, db: DBSession):
    result = scheme_service.update_scheme(db, user_id, course_id, scheme_id, scheme)
    if result is None:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return result


@router.delete("/{user_id}/courses/{course_id}/schemes/{scheme_id}", responses=responses["course_404"])
def remove_scheme(user_id: VerifiedUserId, course_id: UUID, scheme_id: UUID, db: DBSession):
    if not scheme_service.delete_scheme(db, user_id, course_id, scheme_id):
        raise HTTPException(status_code=404, detail="Scheme not found")
    return {"deleted": True}


@router.get("/{user_id}/courses/{course_id}/grades", response_model=list[Grade], responses=responses["course_404"])
def list_grades(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    grades = get_all_grades(db, user_id, course_id)
    if grades is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return grades

@router.post("/{user_id}/courses/{course_id}/grades", response_model=Grade, responses={404: {"description": error_course["not_found"]}, 400: {"description": error_grade["invalid_data"]}})
def create_grade(user_id: VerifiedUserId, course_id: UUID, grade: GradeCreate, db: DBSession):
    try:
        new_grade = add_grade(db, user_id, course_id, grade)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if new_grade is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    record_usage(db, user_id, CREATE, "grades")
    return new_grade

@router.post("/{user_id}/courses/{course_id}/grades/bulk", response_model=list[Grade], responses={404: {"description": error_course["not_found"]}, 400: {"description": error_grade["invalid_data"]}})
def create_grades_bulk(user_id: VerifiedUserId, course_id: UUID, grades: list[GradeCreate], db: DBSession):
    """Add several grades at once, all or nothing."""
    try:
        created = add_grades_bulk(db, user_id, course_id, grades)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return created


@router.get("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses={404: {"description": error_grade["not_found"]}})
def get_single_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, db: DBSession):
    grade = get_grade(db, user_id, course_id, grade_id)
    if grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return grade

@router.patch("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses=responses["grade_both"])
def edit_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, grade: GradeUpdate, db: DBSession):
    try:
        updated_grade = update_grade(db, user_id, course_id, grade_id, grade)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return updated_grade

@router.delete("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses={404: {"description": error_grade["not_found"]}})
def remove_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, db: DBSession):
    deleted_grade = delete_grade(db, user_id, course_id, grade_id)
    if deleted_grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    audit.deletion(
        "grade", user_id=user_id, target_id=grade_id,
        detail=f"course={course_id} name={deleted_grade.name}",
    )
    return deleted_grade

@router.patch("/{user_id}/courses/{course_id}/grades/{grade_id}/score", response_model=Grade, responses=responses["grade_both"])
def record_single_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, score: float, db: DBSession):
    try:
        grade = record_grade(db, user_id, course_id, grade_id, score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return grade