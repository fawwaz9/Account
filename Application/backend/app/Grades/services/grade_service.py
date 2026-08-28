import uuid
from sqlalchemy.orm import Session, joinedload
from app._database.models import CourseModel, CourseCategoryWeightModel, GradeModel
from app.Grades.schemas.grade import GradeCreate, GradeUpdate, Grade as GradeSchema
from app.Grades.utils.enums import GradeCategory


def get_user_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    return (
        db.query(CourseModel)
        .options(joinedload(CourseModel.grades), joinedload(CourseModel.category_weight_rows))
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def get_category_weights(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    return course.category_weights


def update_category_weights(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, weights: dict[GradeCategory, float]):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None

    from app.Grades.schemas.course import normalize_category_weights

    merged = normalize_category_weights({
        **{GradeCategory(k) if not isinstance(k, GradeCategory) else k: v for k, v in course.category_weights.items()},
        **weights,
    })

    for category, weight in merged.items():
        category_value = category.value if isinstance(category, GradeCategory) else category
        existing = next((cw for cw in course.category_weight_rows if cw.category == category_value), None)
        if existing:
            existing.weight = weight
        else:
            db.add(CourseCategoryWeightModel(course_id=course.id, category=category_value, weight=weight))

    db.flush()
    db.refresh(course)

    updated_categories = {(c.value if isinstance(c, GradeCategory) else c) for c in weights}
    sync_grade_weights(course, updated_categories)
    course.average = calculate_current_average(course)

    db.commit()
    db.refresh(course)
    return course.category_weights


def sync_grade_weights(course: CourseModel, categories: set[str] | None = None):
    weights = course.category_weights
    for grade in course.grades:
        if categories is None or grade.category in categories:
            grade.weight = weights.get(grade.category, 0.0)


def add_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_data: GradeCreate):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None

    weights = course.category_weights
    category_value = grade_data.category.value if isinstance(grade_data.category, GradeCategory) else grade_data.category

    grade = GradeModel(
        id=uuid.uuid4(),
        course_id=course.id,
        name=grade_data.name,
        category=category_value,
        score=grade_data.score,
        max_score=grade_data.max_score,
        weight=weights.get(category_value, 0.0),
    )
    db.add(grade)
    db.flush()
    db.refresh(course)

    course.average = calculate_current_average(course)
    db.commit()
    db.refresh(grade)
    return grade


def find_course_and_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None, None

    grade = next((g for g in course.grades if g.id == grade_id), None)
    return course, grade


def update_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID, data: GradeUpdate):
    course, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    if grade is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "category" in update_data and update_data["category"] is not None:
        cat = update_data["category"]
        update_data["category"] = cat.value if isinstance(cat, GradeCategory) else cat

    for key, value in update_data.items():
        setattr(grade, key, value)

    if "category" in update_data:
        weights = course.category_weights
        grade.weight = weights.get(grade.category, 0.0)

    course.average = calculate_current_average(course)
    db.commit()
    db.refresh(grade)
    return grade


def delete_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID):
    course, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    if grade is None:
        return None
    
    deleted_grade = GradeSchema.model_validate(grade)

    db.delete(grade)
    db.flush()
    db.refresh(course)

    course.average = calculate_current_average(course)
    db.commit()
    return deleted_grade


def get_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID):
    _, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    return grade


def get_all_grades(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    return course.grades


def record_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID, score: float):
    course, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    if grade is None:
        return None

    if score < 0:
        raise ValueError("score must be a positive value")

    grade.score = score
    course.average = calculate_current_average(course)
    db.commit()
    db.refresh(grade)
    return grade


def calculate_current_average(course: CourseModel) -> float:
    graded = [g for g in course.grades if g.score is not None and g.max_score > 0]
    if not graded:
        return 0.0

    weights = course.category_weights
    categories_present = {g.category for g in graded}

    total_weight = sum(weights.get(category, 0.0) for category in categories_present)
    if total_weight > 100:
        raise ValueError("Total grade weight cannot exceed 100.")

    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        calculate_grade_category_average(course, category) * weights.get(category, 0.0)
        for category in categories_present
    )
    return round(weighted_sum / total_weight, 2)


def calculate_letter_grade(course) -> str:
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


def calculate_required_final(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, target_grade: float):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    weights = course.category_weights
    final_weight = weights.get(GradeCategory.FINAL.value, 0.0)

    earned_categories: dict[str, list[float]] = {}
    for grade in course.grades:
        if grade.category == GradeCategory.FINAL.value or grade.score is None or grade.max_score == 0:
            continue

        earned_categories.setdefault(grade.category, []).append(
            (grade.score / grade.max_score) * 100
        )

    if final_weight == 0:
        raise ValueError("Course has no final exam.")

    earned_weighted_sum = sum(
        (sum(scores) / len(scores)) * weights.get(category, 0.0)
        for category, scores in earned_categories.items()
    )
    graded_weight = sum(weights.get(category, 0.0) for category in earned_categories)

    unfinished_categories = [
        category for category, weight in weights.items()
        if (
            category != GradeCategory.FINAL.value
            and weight > 0
            and category not in earned_categories
        )
    ]
    counted_weight = graded_weight + final_weight
    needed = ((target_grade * counted_weight) - earned_weighted_sum) / final_weight
    return {
        "needed": round(needed, 2),
        "possible": 0 <= needed <= 100,
        "unfinished_categories": unfinished_categories,
    }


def calculate_grade_category_average(course: CourseModel, category: GradeCategory) -> float:
    category_value = category.value if isinstance(category, GradeCategory) else category
    category_grades = [
        g for g in course.grades
        if g.category == category_value and g.score is not None and g.max_score > 0
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