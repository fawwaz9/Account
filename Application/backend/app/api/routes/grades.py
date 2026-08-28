from uuid import UUID
from fastapi import APIRouter, Query
from fastapi import HTTPException
from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.course import CategoryWeightsUpdate, CourseCreate, Course, CourseDetail, CourseUpdate
from app.shared.errors import error_course, error_grade, error_user, responses
from app.Grades.services.course_service import (
    create_course,
    delete_course,
    get_all_courses,
    get_course,
    get_course_statistics,
    search_courses,
    update_course,
)
from app.Grades.schemas.dashboard import UserGradeDashboard
from app.Grades.schemas.grade import Grade, GradeCreate, GradeUpdate
from app.Grades.services.grade_service import (
    add_grade,
    calculate_current_average,
    calculate_letter_grade,
    calculate_required_final,
    delete_grade,
    get_all_grades,
    get_category_weights,
    get_grade,
    record_grade,
    update_category_weights,
    update_grade,
)
from app.Grades.services.dash_services import DEFAULT_TARGET_GRADE, get_dashboard

router = APIRouter()

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
        raise HTTPException(status_code=400, detail=str(exc))

    if new_course is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

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
        raise HTTPException(status_code=400, detail=str(exc))

    if updated_course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return updated_course

@router.delete("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def remove_course(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    deleted_course = delete_course(db, user_id, course_id)
    if deleted_course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return deleted_course

@router.get("/{user_id}/courses/{course_id}/statistics", response_model=dict, responses=responses["course_404"])
def get_singlecourse_statistics(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    statistics = get_course_statistics(db, user_id, course_id)
    if statistics is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return statistics

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
        raise HTTPException(status_code=400, detail=str(exc))

    if updated_weights is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return updated_weights

@router.get("/{user_id}/courses/{course_id}/average", responses=responses["course_both"])
def get_course_average(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    course = get_course(db, user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    try:
        course.average = calculate_current_average(course)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"course_id": course.id, "average": course.average}

@router.get("/{user_id}/courses/{course_id}/letter-grade", responses=responses["course_404"])
def get_course_letter_grade(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    course = get_course(db, user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    course.average = calculate_current_average(course)
    return {
        "course_id": course.id,
        "average": course.average,
        "letter_grade": calculate_letter_grade(course),
    }

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
        raise HTTPException(status_code=400, detail=str(exc))

    if new_grade is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return new_grade

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
        raise HTTPException(status_code=400, detail=str(exc))

    if updated_grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return updated_grade

@router.delete("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses={404: {"description": error_grade["not_found"]}})
def remove_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, db: DBSession):
    deleted_grade = delete_grade(db, user_id, course_id, grade_id)
    if deleted_grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return deleted_grade

@router.patch("/{user_id}/courses/{course_id}/grades/{grade_id}/score", response_model=Grade, responses=responses["grade_both"])
def record_single_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, score: float, db: DBSession):
    try:
        grade = record_grade(db, user_id, course_id, grade_id, score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return grade