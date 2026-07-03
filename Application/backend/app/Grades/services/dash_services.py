from uuid import UUID

from app.Grades.utils.enums import GradeCategory
from app.temp_data.store import courses
from app.Grades.schemas.dashboard import CourseDashboardEntry, UserGradeDashboard
from app.Grades.services.grade_service import calculate_current_average, calculate_required_final
from app.Users.services.user_service import get_user


def get_dashboard(user_id: UUID | None = None):
    user = get_user(user_id) if user_id is not None else None
    course_list = user.courses if user is not None else courses

    if user_id is not None and user is None:
        return None

    entries: list[CourseDashboardEntry] = []
    for course in course_list:
        average = calculate_current_average(course)
        unfinished_categories = [
            category.value
            for category, weight in course.category_weights.items()
            if category != GradeCategory.FINAL and weight > 0 and not any(
                grade.category == category and grade.score is not None
                for grade in course.grades
            )
        ]

        needed_final_score = None
        if user_id is not None and course.category_weights.get(GradeCategory.FINAL, 0.0) > 0:
            try:
                required_final = calculate_required_final(user_id, course.id, 90)
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


def calculate_gpa(courses):
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

    gpa = total_quality_points / total_credits
    return round(gpa, 2)

