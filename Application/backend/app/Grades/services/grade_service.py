from uuid import UUID, uuid4

from app.Grades.schemas.grade import Grade, GradeCreate, GradeUpdate
from app.Grades.utils.enums import GradeCategory
from app.Grades.schemas.course import normalize_category_weights
from app.Users.services.user_service import get_user

def sync_grade_weights(course, categories: set[GradeCategory] | None = None):
    for grade in course.grades:
        if categories is None or grade.category in categories:
            grade.weight = course.category_weights.get(grade.category, 0.0)

def get_user_course(user_id: UUID, course_id: UUID):
    user = get_user(user_id)
    if user is None:
        return None

    for course in user.courses:
        if course.id == course_id:
            return course

    return None

def get_category_weights(user_id: UUID, course_id: UUID):
    course = get_user_course(user_id, course_id)
    if course is None:
        return None

    return course.category_weights

def update_category_weights(user_id: UUID, course_id: UUID, weights: dict[GradeCategory, float]):
    course = get_user_course(user_id, course_id)
    if course is None:
        return None

    updated_categories = set(weights)
    course.category_weights = normalize_category_weights({
        **course.category_weights,
        **weights,
    })
    sync_grade_weights(course, updated_categories)
    course.average = calculate_current_average(course)
    return course.category_weights

def add_grade(user_id: UUID, course_id: UUID, grade_data: GradeCreate):
    course = get_user_course(user_id, course_id)
    if course is None:
        return None

    grade = Grade(
        id=uuid4(),
        weight=course.category_weights.get(grade_data.category, 0.0),
        **grade_data.model_dump()
    )
    course.grades.append(grade)
    course.average = calculate_current_average(course)
    return grade

def find_course_and_grade(user_id: UUID, course_id: UUID, grade_id: UUID):
    course = get_user_course(user_id, course_id)
    if course is None:
        return None, None

    for grade in course.grades:
        if grade.id == grade_id:
            return course, grade

    return None, None

def update_grade(user_id: UUID, course_id: UUID, grade_id: UUID, data: GradeUpdate):
    course, grade = find_course_and_grade(user_id, course_id, grade_id)
    if grade is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(grade, key, value)

    if "category" in update_data:
        grade.weight = course.category_weights.get(grade.category, 0.0)

    course.average = calculate_current_average(course)
    return grade

def delete_grade(user_id: UUID, course_id: UUID, grade_id: UUID):
    course, grade = find_course_and_grade(user_id, course_id, grade_id)
    if grade is None:
        return None

    course.grades.remove(grade)
    course.average = calculate_current_average(course)
    return grade

def get_grade(user_id: UUID, course_id: UUID, grade_id: UUID):
    _, grade = find_course_and_grade(user_id, course_id, grade_id)
    if grade is None:
        return None
    return grade

def get_all_grades(user_id: UUID, course_id: UUID):
    course = get_user_course(user_id, course_id)
    if course is None:
        return None

    return course.grades

def record_grade(user_id: UUID, course_id: UUID, grade_id: UUID, score: float) -> Grade | None:
    course, grade = find_course_and_grade(user_id, course_id, grade_id)
    if grade is None:
        return None

    if score < 0:
        raise ValueError("score must be a positive value")

    grade.score = score
    course.average = calculate_current_average(course)
    return grade

def calculate_current_average(course) -> float: 
    graded = [
        g for g in course.grades
        if g.score is not None and g.max_score > 0
    ]
    if not graded:
        return 0.0

    category_averages: dict[GradeCategory, list[float]] = {}
    for grade in graded:
        category_averages.setdefault(grade.category, []).append(
            (grade.score / grade.max_score) * 100
        )

    total_weight = sum(
        course.category_weights.get(category, 0.0)
        for category in category_averages
    )
    if total_weight > 100:
        raise ValueError("Total grade weight cannot exceed 100.")
    
    if total_weight == 0:
        return 0.0
    
    weighted_sum = sum(
        (sum(scores) / len(scores)) * course.category_weights.get(category, 0.0)
        for category, scores in category_averages.items()
    )
    return round(weighted_sum / total_weight, 2)

def calculate_letter_grade(course): # — convert the numeric average to a letter grade according to your grading scale.
    if course.average >= 90:
        return "A+"
    elif course.average >= 85:
        return "A"
    elif course.average >= 80:
        return "A-"
    elif course.average >= 76:
        return "B+"
    elif course.average >= 72:
        return "B"
    elif course.average >= 68:
        return "B-"
    elif course.average >= 64:
        return "C+"
    elif course.average >= 60:
        return "C"
    elif course.average >= 55:
        return "C-"
    elif course.average >= 50:
        return "D"
    else:
        return "F"

def calculate_required_final(user_id: UUID, course_id: UUID, target_grade: float):
    course = get_user_course(user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    final_weight = course.category_weights.get(GradeCategory.FINAL, 0.0)

    earned_categories: dict[GradeCategory, list[float]] = {}
    for grade in course.grades:
        if grade.category == GradeCategory.FINAL or grade.score is None or grade.max_score == 0:
            continue

        earned_categories.setdefault(grade.category, []).append(
            (grade.score / grade.max_score) * 100
        )

    if final_weight == 0:
        raise ValueError("Course has no final exam.")

    earned_weighted_sum = sum(
        (sum(scores) / len(scores)) * course.category_weights.get(category, 0.0)
        for category, scores in earned_categories.items()
    )
    graded_weight = sum(
        course.category_weights.get(category, 0.0)
        for category in earned_categories
    )

    unfinished_categories = [
        category for category, weight in course.category_weights.items()
        if (
            category != GradeCategory.FINAL
            and weight > 0
            and category not in earned_categories
        )
    ]
    counted_weight = graded_weight + final_weight
    needed = ((target_grade * counted_weight) - earned_weighted_sum) / final_weight
    return {
        "needed": round(needed, 2),
        "possible": 0 <= needed <= 100,
        "unfinished_categories": unfinished_categories
    }

def calculate_grade_category_average(course, category: GradeCategory) -> float:
    category_grades = [
        g for g in course.grades
        if g.category == category and g.score is not None and g.max_score > 0
    ]
    if not category_grades:
        return 0.0

    total_weight = sum(g.max_score for g in category_grades)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        (g.score / g.max_score) * 100 * g.max_score
        for g in category_grades
    )
    return round(weighted_sum / total_weight, 2)