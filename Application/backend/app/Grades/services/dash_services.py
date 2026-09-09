import uuid
from sqlalchemy.orm import Session
from app._database.models import CourseModel
from app.Grades.utils.enums import GradeCategory
from app.Grades.schemas.dashboard import (
    AttentionItem,
    CourseDashboardEntry,
    UserGradeDashboard,
    YearSummary,
)
from app.Grades.services.grade_service import calculate_gpa_points, calculate_required_final
from app.Grades.utils.terms import CURRENT, FUTURE, PAST, course_result_grade, year_average
from app.Grades.utils.weights import weight_problems
from app.Grades.services.course_service import get_all_courses
from app.Users.services.user_service import get_preferences, get_user


DEFAULT_TARGET_GRADE = 90.0


def get_dashboard(db: Session, user_id: uuid.UUID, target_grade: float = DEFAULT_TARGET_GRADE):
    """Roll every course up into one view.

    `target_grade` drives the "what do I need on the final" figures. It used to
    be hard-coded at 90, so every course was measured against an A+ regardless
    of what the student was actually aiming for.
    """
    user = get_user(db, user_id)
    if user is None:
        return None

    course_list = get_all_courses(db, user_id)

    entries: list[CourseDashboardEntry] = []
    for course in course_list:
        weights = course.category_weights
        # Read the stored column, same as the course list and course page, so
        # every surface reports one number per course.
        average = course.average
        unfinished_categories = [
            category for category, weight in weights.items()
            if category != GradeCategory.FINAL.value and weight > 0 and not any(
                grade.category == category and grade.score is not None
                for grade in course.grades
            )
        ]

        needed_final_score = None
        if weights.get(GradeCategory.FINAL.value, 0.0) > 0:
            try:
                required_final = calculate_required_final(db, user_id, course.id, target_grade)
                needed_final_score = required_final.get("needed")
            except ValueError:
                needed_final_score = None

        entries.append(
            CourseDashboardEntry(
                course_id=course.id,
                course_code=course.code,
                course_name=course.name,
                average=average,
                needed_final_score=needed_final_score,
                unfinished_categories=unfinished_categories,
            )
        )

    if not entries:
        return UserGradeDashboard(
            total_courses=0,
            cumulative_average=0.0,
            semester_average=0.0,
            cgpa=None,
            credits_completed=0.0,
            credits_in_progress=0.0,
            credit_target=get_preferences(user).credit_target,
            best_course=None,
            weakest_course=None,
            courses_needing_final_score=[],
            unfinished_categories_by_course={},
        )

    preferences = get_preferences(user)
    current_courses = [c for c in course_list if c.term_bucket == CURRENT]
    completed_credits, in_progress_credits = credits_by_state(course_list)

    best_course = max(entries, key=lambda entry: entry.average)
    weakest_course = min(entries, key=lambda entry: entry.average)
    courses_needing_final_score = [
        entry for entry in entries if entry.needed_final_score is not None and entry.needed_final_score > 0
    ]
    unfinished_categories_by_course = {
        f"{entry.course_code} - {entry.course_name}": entry.unfinished_categories
        for entry in entries
        if entry.unfinished_categories
    }

    return UserGradeDashboard(
        total_courses=len(entries),
        cumulative_average=calculate_cumulative_average(course_list),
        semester_average=plain_average(current_courses),
        cgpa=calculate_cgpa(course_list) if preferences.gpa_scale_enabled else None,
        credits_completed=completed_credits,
        credits_in_progress=in_progress_credits,
        credit_target=preferences.credit_target,
        best_course=best_course,
        weakest_course=weakest_course,
        courses_needing_final_score=courses_needing_final_score,
        unfinished_categories_by_course=unfinished_categories_by_course,
        attention=collect_attention(course_list, preferences.default_target_grade),
        past_years=summarize_years(course_list, PAST),
        future_years=summarize_years(course_list, FUTURE),
    )


def plain_average(courses) -> float:
    """Unweighted mean over courses that have a result, skipping the rest."""
    results = [g for g in (course_result_grade(c) for c in courses) if g is not None]
    if not results:
        return 0.0

    return round(sum(results) / len(results), 2)


def calculate_cumulative_average(courses):
    """Credit-weighted average over courses with a final grade recorded.

    Only finished courses count. A running average is a snapshot of work in
    progress, not a result, so a term you are partway through does not move
    your cumulative figure -- that is what the semester average is for.
    Credit-weighted, so a 6-credit course counts double a 3.
    """
    total_quality_points = 0.0
    total_credits = 0.0

    for course in courses:
        final = course.final_grade
        if final and final > 0 and course.credits > 0:
            total_quality_points += final * course.credits
            total_credits += course.credits

    if total_credits == 0:
        return 0.0

    return round(total_quality_points / total_credits, 2)


def calculate_cgpa(courses) -> float | None:
    """Credit-weighted grade points over courses with a final grade recorded.

    Deliberately the same set as calculate_cumulative_average: the two are the
    same measure on different scales, and letting one count in-progress work
    while the other did not would put contradictory figures side by side.
    """
    total_points = 0.0
    total_credits = 0.0

    for course in courses:
        final = course.final_grade
        if not final or final <= 0 or not course.credits:
            continue
        total_points += calculate_gpa_points(final) * course.credits
        total_credits += course.credits

    if total_credits == 0:
        return None

    return round(total_points / total_credits, 2)


def credits_by_state(courses) -> tuple[float, float]:
    """(completed, in progress).

    Completed is every past-term credit plus current-term courses that already
    have a final grade recorded -- a course finished mid-year should not sit in
    "in progress" until the whole term rolls over.
    """
    completed = 0.0
    in_progress = 0.0

    for course in courses:
        credits = course.credits or 0.0
        if course.term_bucket == PAST:
            completed += credits
        elif course.term_bucket == CURRENT:
            if course.final_grade and course.final_grade > 0:
                completed += credits
            else:
                in_progress += credits

    return completed, in_progress


def summarize_years(courses, bucket: str) -> list[YearSummary]:
    """Group one bucket's courses by school year, newest year first for past.

    Uses year_average, so a course that was never filled in is skipped rather
    than pulling its year toward zero.
    """
    by_year: dict[int, list] = {}
    for course in courses:
        if course.term_bucket != bucket:
            continue
        by_year.setdefault(course.year, []).append(course)

    summaries = [
        YearSummary(
            school_year=year,
            average=year_average(year_courses),
            course_count=len(year_courses),
        )
        for year, year_courses in by_year.items()
    ]
    return sorted(summaries, key=lambda entry: entry.school_year)


def effective_target(course, default_target: float) -> float:
    """The course's own target, or the account default when it has none."""
    return course.target_grade if course.target_grade is not None else default_target


def collect_attention(courses, default_target: float) -> list[AttentionItem]:
    """Things worth acting on, most actionable first.

    Deliberately built from data already loaded -- no extra queries.
    """
    missing: list[AttentionItem] = []
    below: list[AttentionItem] = []
    weights: list[AttentionItem] = []

    for course in courses:
        common = {"course_id": course.id, "course_code": course.code}

        # A finished course with no final silently drops out of the cumulative.
        if course.term_bucket == PAST and not (course.final_grade and course.final_grade > 0):
            missing.append(AttentionItem(
                kind="missing_final", **common,
                message="finished, but no final grade recorded",
            ))

        # Only current courses: a past course under target is history, not
        # something you can still do anything about.
        if course.term_bucket == CURRENT:
            result = course_result_grade(course)
            target = effective_target(course, default_target)
            if result is not None and result < target:
                below.append(AttentionItem(
                    kind="below_target", **common,
                    message=f"at {result:g}% against a {target:g}% target",
                ))

        for problem in weight_problems(course):
            weights.append(AttentionItem(kind="weight_problem", **common, message=problem))

    return missing + below + weights
