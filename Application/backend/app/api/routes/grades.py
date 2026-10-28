"""Grades routes under `/api/grades`: courses, grades, weights, schemes, figures.

Also the catalogue link, prerequisites, the dashboard and blind spots. Literal paths
are declared above the `/courses/{course_id}` routes, since FastAPI matches in
order.
"""

from uuid import UUID
from fastapi import APIRouter, Query
from fastapi import HTTPException
from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.scheme import CountingScheme, GradingScheme, SchemeComparison, SchemeWrite
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
from app.Grades.schemas.catalogue import CatalogueChoice, CatalogueCourse, CatalogueLink
from app.Grades.services import catalogue_service, prerequisite_service
from app.Grades.schemas.prerequisite import Kind, PrerequisitePreview, Prerequisites, RuleChecked, RuleText, RuleWrite
from app.Grades.utils.enums import Semester
from app.Grades.utils.prerequisites import RuleError, parse_text, render
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
    """List the grade categories the student does worse in than their own average.

    Only categories that trail in at least two courses are listed, worst gap first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The blind spots; empty when there are none.

    Raises:
        HTTPException: 404 when the user does not exist.
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
    """Return the grades dashboard: averages, credits, trend and Attention.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        target_grade: Target, 0-100, for every course's needed-final figure; 90 by
            default.

    Returns:
        The dashboard.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    dashboard = get_dashboard(db, user_id, target_grade)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return dashboard

@router.get("/{user_id}/courses", response_model=list[Course], responses=responses["course_404"])
def get_courses(user_id: VerifiedUserId, db: DBSession):
    """List the student's courses in term order, with their figures.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Every course; empty when there are none.
    """
    courses = get_all_courses(db, user_id)
    if courses is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    # An account with no courses yet is an empty collection, not an error --
    # the UI has an empty state for exactly this and never got to show it.
    return courses

@router.post("/{user_id}/courses", response_model=CourseDetail, responses={404: {"description": error_course["not_found"]}, 400: {"description": error_course["already_exists"]}})
def add_course(user_id: VerifiedUserId, course: CourseCreate, db: DBSession):
    """Add a course, and count it as a create in Grades.

    Args:
        user_id: The verified caller's id.
        course: The new course.
        db: Request-scoped database session.

    Returns:
        The new course in full.

    Raises:
        HTTPException: 400 when the user already has a course with this code; 404 when
            the user does not exist.
    """
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
    """Find the student's courses whose code or name contains the query, in any term.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        query: Text to find, 1-100 characters; `%` and `_` match literally.

    Returns:
        The matching courses.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
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
    """Return which of the student's courses a typed code means, if any.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        text: The typed line, 1-200 characters.

    Returns:
        `course_id`, `code` and `name`, all null when nothing (or more than one course)
        matches.
    """
    course = resolve_course(db, user_id, text)
    if course is None:
        return {"course_id": None, "code": None, "name": None}
    return {"course_id": course.id, "code": course.code, "name": course.name}


# The shared catalogue (Phase 2 item 3). Read-only from here: the API's role
# cannot write it, and the routes sit under your own path like every other, so
# the isolation walk covers them.
@router.get("/{user_id}/catalogue", response_model=list[CatalogueCourse], responses=responses["user_404"])
def search_catalogue(user_id: VerifiedUserId, db: DBSession, q: str = Query(default="", max_length=20)):
    """Search the shared catalogue by code prefix, such as "cpsc 2".

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        q: The typed prefix, at most 20 characters.

    Returns:
        Up to 20 catalogue courses; empty for anything that is not a code prefix.
    """
    return catalogue_service.search(db, q)


@router.get("/{user_id}/courses/{course_id}/catalogue", response_model=CatalogueLink,
            responses=responses["course_404"])
def get_catalogue_link(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Return a course's catalogue link and how it was decided.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The link.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    link = catalogue_service.get_link(db, user_id, course_id)
    if link is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return link


@router.put("/{user_id}/courses/{course_id}/catalogue", response_model=CatalogueLink,
            responses=responses["course_404"])
def set_catalogue_link(user_id: VerifiedUserId, course_id: UUID, choice: CatalogueChoice, db: DBSession):
    """Set a course's catalogue link: automatic, a chosen catalogue course, or none.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        choice: The mode, and the catalogue course for "chosen".
        db: Request-scoped database session.

    Returns:
        The resulting link.

    Raises:
        HTTPException: 404 when the course is missing or another user's, or the chosen
            catalogue course does not exist.
    """
    try:
        link = catalogue_service.set_link(db, user_id, course_id, choice)
    except catalogue_service.CatalogueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return link


# Prerequisites (Phase 2 items 4 and 7): yours, the shared one, met or not.
# Advisory -- nothing anywhere is refused because one is unmet (D3).
@router.post("/{user_id}/prerequisites/check", response_model=RuleChecked, responses=responses["user_404"])
def check_prerequisite_text(user_id: VerifiedUserId, body: RuleText):
    """Read a typed prerequisite rule back, so the page can show what would be saved.

    Args:
        user_id: The verified caller's id.
        body: The typed rule.

    Returns:
        The rule tree and its normalised text.

    Raises:
        HTTPException: 400 when the text is not a valid rule.
    """
    try:
        rule = parse_text(body.text)
    except RuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuleChecked(rule=rule, text=render(rule))


@router.get("/{user_id}/prerequisites/preview", response_model=PrerequisitePreview, responses=responses["user_404"])
def preview_prerequisites(user_id: VerifiedUserId, db: DBSession, code: str = Query(..., max_length=20),
                          year: int = Query(..., ge=1, le=10), semester: Semester = Query(...)):
    """Return the shared prerequisite warning for a course about to be added.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        code: The code being added, at most 20 characters.
        year: Its school year, 1-10.
        semester: Its term.

    Returns:
        The matching catalogue course and its rules with verdicts; empty for a past term
        or an unmatched code.
    """
    return prerequisite_service.preview(db, user_id, code, year, semester.value)


@router.get("/{user_id}/courses/{course_id}/prerequisites", response_model=Prerequisites,
            responses=responses["course_404"])
def get_prerequisites(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Return a course's prerequisite rules, both versions, with verdicts.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The rules per kind and the catalogue link.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    found = prerequisite_service.prerequisites(db, user_id, course_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return found


@router.put("/{user_id}/courses/{course_id}/prerequisites", response_model=Prerequisites,
            responses=responses["course_404"])
def set_own_prerequisite(user_id: VerifiedUserId, course_id: UUID, body: RuleWrite, db: DBSession):
    """Save the student's own rule of one kind for a course, replacing any they had.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        body: The rule, typed or as a tree.
        db: Request-scoped database session.

    Returns:
        The course's rules after the change.

    Raises:
        HTTPException: 400 when the rule cannot be read; 404 when the course is missing
            or another user's.
    """
    try:
        found = prerequisite_service.set_own(db, user_id, course_id, body)
    except RuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return found


@router.delete("/{user_id}/courses/{course_id}/prerequisites", response_model=Prerequisites,
               responses=responses["course_404"])
def delete_own_prerequisite(user_id: VerifiedUserId, course_id: UUID, db: DBSession,
                            kind: Kind = Query(default="prerequisite")):
    """Delete the student's own rule of one kind for a course.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.
        kind: "prerequisite" (the default) or "corequisite".

    Returns:
        The course's rules after the change.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    found = prerequisite_service.delete_own(db, user_id, course_id, kind)
    if found is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])
    return found


@router.get("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def get_single_course(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Return one course in full: grades in display order and per-category figures.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The course, its stored average as is.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
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
    """Edit a course; sent weights are checked before anything is saved.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        course: The fields to change; omitted ones stay.
        db: Request-scoped database session.

    Returns:
        The updated course in full.

    Raises:
        HTTPException: 400 when the weights are out of range; 404 when the course is
            missing or another user's.
    """
    try:
        updated_course = update_course(db, user_id, course_id, course)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_course is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return updated_course

@router.delete("/{user_id}/courses/{course_id}", response_model=CourseDetail, responses=responses["course_404"])
def remove_course(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Delete a course with its grades, timetable and tasks; audit-logged.

    Expenses, reminders and repeating tasks that mention it are kept, without the
    mention.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The deleted course.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
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
    """Return a course's category weights.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        Category name to weight percentage.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    category_weights = get_category_weights(db, user_id, course_id)
    if category_weights is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return category_weights

@router.patch("/{user_id}/courses/{course_id}/category-weights", responses=responses["course_both"])
def edit_course_category_weights(user_id: VerifiedUserId, course_id: UUID, category_weights: CategoryWeightsUpdate, db: DBSession):
    """Change some of a course's category weights and recompute its average.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        category_weights: The categories to change and their weights.
        db: Request-scoped database session.

    Returns:
        The full weight map after the change.

    Raises:
        HTTPException: 400 when a weight or the merged total is out of range;
            404 when the course is missing or another user's.
    """
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
    """Return where a course can still finish: best case, worst case and now.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        "best", "worst", "current", "settled", "outstanding_items" and
        "empty_categories".

    Raises:
        HTTPException: 404 when the course is missing or another user's; 400 for any
            other error.
    """
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
    """Return the three unmarked items in a course most worth doing next.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The ranked items, with the target, current and best averages.

    Raises:
        HTTPException: 404 when the course is missing or another user's; 400 for any
            other error.
    """
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
    """Return what the final must score for a course to finish at a target.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.
        target_grade: Target percentage, 0-100; required.

    Returns:
        "needed", "possible" and "unfinished_categories".

    Raises:
        HTTPException: 404 when the course is missing or another user's; 400 when it has
            no weighted final.
    """
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
    """Return the course average under its own weights and under each scheme.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The comparison, with the best and the picked scheme.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
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
    """Add an alternative grading scheme to a course.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        scheme: The label and components.
        db: Request-scoped database session.

    Returns:
        The new scheme.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
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
    """Replace a scheme's label and components, regrading the course if picked.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        scheme_id: The scheme.
        scheme: The new label and components.
        db: Request-scoped database session.

    Returns:
        The updated scheme.

    Raises:
        HTTPException: 404 when the course or scheme is missing or another user's.
    """
    result = scheme_service.update_scheme(db, user_id, course_id, scheme_id, scheme)
    if result is None:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return result


@router.put(
    "/{user_id}/courses/{course_id}/counting-scheme",
    response_model=SchemeComparison,
    responses=responses["course_404"],
)
def set_counting_scheme(user_id: VerifiedUserId, course_id: UUID, choice: CountingScheme, db: DBSession):
    """Pick the scheme that is the course's grade, or null for the course's own weights.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        choice: The scheme to count, or null.
        db: Request-scoped database session.

    Returns:
        The comparison after the change.

    Raises:
        HTTPException: 404 when the course is not the caller's or the scheme is not this
            course's.
    """
    result = scheme_service.set_counting(db, user_id, course_id, choice.scheme_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Course or scheme not found")
    return result


@router.delete("/{user_id}/courses/{course_id}/schemes/{scheme_id}", responses=responses["course_404"])
def remove_scheme(user_id: VerifiedUserId, course_id: UUID, scheme_id: UUID, db: DBSession):
    """Delete a scheme; if it was the picked one, the course's own weights count again.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        scheme_id: The scheme.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the course or scheme is missing or another user's.
    """
    if not scheme_service.delete_scheme(db, user_id, course_id, scheme_id):
        raise HTTPException(status_code=404, detail="Scheme not found")
    return {"deleted": True}


@router.get("/{user_id}/courses/{course_id}/grades", response_model=list[Grade], responses=responses["course_404"])
def list_grades(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """List a course's grades in display order.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The grades.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    grades = get_all_grades(db, user_id, course_id)
    if grades is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return grades

@router.post("/{user_id}/courses/{course_id}/grades", response_model=Grade, responses={404: {"description": error_course["not_found"]}, 400: {"description": error_grade["invalid_data"]}})
def create_grade(user_id: VerifiedUserId, course_id: UUID, grade: GradeCreate, db: DBSession):
    """Add a grade to a course, raising its task or calendar block if dated.

    Counted as a create in Grades.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grade: The new grade.
        db: Request-scoped database session.

    Returns:
        The new grade.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
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
    """Add several grades to a course at once, all or nothing.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grades: The new grades.
        db: Request-scoped database session.

    Returns:
        The new grades.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    try:
        created = add_grades_bulk(db, user_id, course_id, grades)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return created


@router.get("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses={404: {"description": error_grade["not_found"]}})
def get_single_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, db: DBSession):
    """Return one of a course's grades.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grade_id: The grade.
        db: Request-scoped database session.

    Returns:
        The grade.

    Raises:
        HTTPException: 404 when the course or grade is missing or another user's.
    """
    grade = get_grade(db, user_id, course_id, grade_id)
    if grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return grade

@router.patch("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses=responses["grade_both"])
def edit_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, grade: GradeUpdate, db: DBSession):
    """Edit a grade; its task or calendar block follows.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grade_id: The grade.
        grade: The fields to change; omitted ones stay.
        db: Request-scoped database session.

    Returns:
        The updated grade.

    Raises:
        HTTPException: 400 when the edited grade breaks a rule (score over twice the
            maximum, a time without a date, a length without a time); 404 when the
            course or grade is missing or another user's.
    """
    try:
        updated_grade = update_grade(db, user_id, course_id, grade_id, grade)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return updated_grade

@router.delete("/{user_id}/courses/{course_id}/grades/{grade_id}", response_model=Grade, responses={404: {"description": error_grade["not_found"]}})
def remove_grade(user_id: VerifiedUserId, course_id: UUID, grade_id: UUID, db: DBSession):
    """Delete a grade, with the task or block it raised, and record it in the audit log.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grade_id: The grade.
        db: Request-scoped database session.

    Returns:
        The deleted grade.

    Raises:
        HTTPException: 404 when the course or grade is missing or another user's.
    """
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
    """Record a grade's score; a task it raised is checked off.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        grade_id: The grade.
        score: Points earned, as a query parameter; 0 to twice the maximum.
        db: Request-scoped database session.

    Returns:
        The marked grade.

    Raises:
        HTTPException: 400 when the score is negative or over the limit; 404 when the
            course or grade is missing or another user's.
    """
    try:
        grade = record_grade(db, user_id, course_id, grade_id, score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if grade is None:
        raise HTTPException(status_code=404, detail=error_grade["not_found"])

    return grade
