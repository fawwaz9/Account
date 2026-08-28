import uuid
from sqlalchemy.orm import Session
from app._database.models import CourseModel
from app.Grades.utils.enums import GradeCategory
from app.Grades.schemas.dashboard import CourseDashboardEntry, UserGradeDashboard
from app.Grades.services.grade_service import calculate_required_final
from app.Grades.services.course_service import get_all_courses
from app.Users.services.user_service import get_user


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
            overall_average=0.0,
            cumulative_average=0.0,
            best_course=None,
            weakest_course=None,
            courses_needing_final_score=[],
            unfinished_categories_by_course={},
        )

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
        # Plain mean across courses; cumulative_average weights by credits.
        overall_average=round(sum(entry.average for entry in entries) / len(entries), 2),
        cumulative_average=calculate_cumulative_average(course_list),
        best_course=best_course,
        weakest_course=weakest_course,
        courses_needing_final_score=courses_needing_final_score,
        unfinished_categories_by_course=unfinished_categories_by_course,
    )


def calculate_cumulative_average(courses):
    """Credit-weighted average across courses, so a 6-credit course counts double a 3."""
    total_quality_points = 0.0
    total_credits = 0.0

    for course in courses:
        course_average = course.average
        if course_average is not None and course.credits > 0:
            quality_points = course_average * course.credits
            total_quality_points += quality_points
            total_credits += course.credits

    if total_credits == 0:
        return 0.0

    return round(total_quality_points / total_credits, 2)