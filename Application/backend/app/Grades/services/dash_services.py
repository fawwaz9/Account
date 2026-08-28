import uuid
from sqlalchemy.orm import Session
from app._database.models import CourseModel
from app.Grades.utils.enums import GradeCategory
from app.Grades.schemas.dashboard import CourseDashboardEntry, UserGradeDashboard
from app.Grades.services.grade_service import calculate_current_average, calculate_required_final
from app.Grades.services.course_service import get_all_courses
from app.Users.services.user_service import get_user


def get_dashboard(db: Session, user_id: uuid.UUID):
    user = get_user(db, user_id)
    if user is None:
        return None

    course_list = get_all_courses(db, user_id)

    entries: list[CourseDashboardEntry] = []
    for course in course_list:
        weights = course.category_weights
        average = calculate_current_average(course)
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
                required_final = calculate_required_final(db, user_id, course.id, 90)
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
        overall_average=round(sum(entry.average for entry in entries) / len(entries), 2),
        best_course=best_course,
        weakest_course=weakest_course,
        courses_needing_final_score=courses_needing_final_score,
        unfinished_categories_by_course=unfinished_categories_by_course,
    )


def calculate_cumulative_average(courses):
    total_quality_points = 0.0
    total_credits = 0.0

    for course in courses:
        course_average = calculate_current_average(course)
        if course_average is not None and course.credits > 0:
            quality_points = course_average * course.credits
            total_quality_points += quality_points
            total_credits += course.credits

    if total_credits == 0:
        return 0.0

    return round(total_quality_points / total_credits, 2)