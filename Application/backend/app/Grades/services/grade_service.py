import uuid
from sqlalchemy.orm import Session, joinedload
from app._database.models import CourseModel, CourseCategoryWeightModel, GradeModel
from app.Grades.schemas.grade import GradeCreate, GradeUpdate, Grade as GradeSchema
from app.Grades.utils.enums import GradeCategory, GradeSchedule
from app.Grades.utils.terms import course_result_grade
from app.Grades.services.grade_schedule import sync_schedule_for_grade


MAX_COURSE_PERCENT = 100.0

#: A grade may exceed its max -- bonus marks are real -- but not absurdly, so a
#: slipped digit (150 out of 10) is still caught.
MAX_SCORE_MULTIPLE = 2.0


def score_exceeds_limit(score: float | None, max_score: float) -> bool:
    return score is not None and score > max_score * MAX_SCORE_MULTIPLE


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
        due_date=grade_data.due_date,
        schedule_as=grade_data.schedule_as.value,
    )
    db.add(grade)
    db.flush()
    db.refresh(course)

    course.average = calculate_current_average(course)
    # Inside this transaction, so a grade that fails to save leaves no task
    # behind for work that was never recorded.
    sync_schedule_for_grade(db, course, grade)
    db.commit()
    db.refresh(grade)
    return grade


def add_grades_bulk(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grades: list[GradeCreate]):
    """Create several grades in one transaction.

    Entering a course's categories one modal at a time meant eleven sequential
    requests, any of which could fail and leave the course half-populated. This
    commits once: either every row lands or none does.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None

    weights = course.category_weights
    created: list[GradeModel] = []

    try:
        for grade_data in grades:
            category_value = (
                grade_data.category.value
                if isinstance(grade_data.category, GradeCategory)
                else grade_data.category
            )
            grade = GradeModel(
                id=uuid.uuid4(),
                course_id=course.id,
                name=grade_data.name,
                category=category_value,
                score=grade_data.score,
                max_score=grade_data.max_score,
                weight=weights.get(category_value, 0.0),
                due_date=grade_data.due_date,
                schedule_as=grade_data.schedule_as.value,
            )
            db.add(grade)
            created.append(grade)

        db.flush()
        db.refresh(course)
        course.average = calculate_current_average(course)
        for grade in created:
            sync_schedule_for_grade(db, course, grade)
        db.commit()
    except Exception:
        db.rollback()
        raise

    for grade in created:
        db.refresh(grade)
    return created


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

    if update_data.get("schedule_as") is not None:
        schedule = update_data["schedule_as"]
        update_data["schedule_as"] = (
            schedule.value if isinstance(schedule, GradeSchedule) else schedule
        )
    else:
        # A partial update that does not mention it must not null the column.
        update_data.pop("schedule_as", None)

    for key, value in update_data.items():
        setattr(grade, key, value)

    if "category" in update_data:
        weights = course.category_weights
        grade.weight = weights.get(grade.category, 0.0)

    # A partial update can raise the score or lower max_score independently, so
    # the pair is only checkable after both have been applied.
    if score_exceeds_limit(grade.score, grade.max_score):
        raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

    course.average = calculate_current_average(course)
    # Covers all four of the ways an edit moves the task: a renamed grade, a
    # moved deadline, a deadline removed, and a score arriving by edit rather
    # than through record_grade.
    sync_schedule_for_grade(db, course, grade)
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
    if score_exceeds_limit(score, grade.max_score):
        raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

    grade.score = score
    course.average = calculate_current_average(course)
    # The score landing is what closes the task.
    sync_schedule_for_grade(db, course, grade)
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
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        calculate_grade_category_average(course, category) * weights.get(category, 0.0)
        for category in categories_present
    )

    # Weight past 100 is bonus: it adds marks without enlarging the denominator,
    # which is how a course marked out of 101% works. Earning beyond a
    # category's weight (bonus marks on an assignment) is allowed to offset
    # losses elsewhere, but the course itself still caps at 100.
    denominator = min(total_weight, MAX_COURSE_PERCENT)
    return min(round(weighted_sum / denominator, 2), MAX_COURSE_PERCENT)


# (minimum percentage, letter, grade points) on UBC's published 4.33 scale.
# One table so the letter and the GPA can never disagree about a boundary --
# they were separate ladders waiting to drift apart.
GRADE_SCALE: list[tuple[float, str, float]] = [
    (90, "A+", 4.33),
    (85, "A", 4.00),
    (80, "A-", 3.67),
    (76, "B+", 3.30),
    (72, "B", 3.00),
    (68, "B-", 2.67),
    (64, "C+", 2.33),
    (60, "C", 2.00),
    (55, "C-", 1.67),
    (50, "D", 1.00),
    (0, "F", 0.00),
]


def grade_scale_row(average: float) -> tuple[str, float]:
    for minimum, letter, points in GRADE_SCALE:
        if average >= minimum:
            return letter, points

    return "F", 0.0


def calculate_letter_grade(course) -> str:
    """Letter for the course's result, or "" when nothing is recorded.

    Reads course_result_grade rather than the raw average, so a finished course
    carrying only the professor's final_grade does not read as an F, and an
    untouched course shows no letter at all instead of failing.
    """
    result = course_result_grade(course)
    if result is None:
        return ""

    return grade_scale_row(result)[0]


def calculate_gpa_points(average: float | None) -> float:
    """Grade points for a percentage, on the configured scale."""
    return grade_scale_row(average or 0.0)[1]


def calculate_required_final(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, target_grade: float):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    weights = course.category_weights
    final_weight = weights.get(GradeCategory.FINAL.value, 0.0)

    # Which non-final categories have at least one marked grade. The averages
    # themselves come from calculate_grade_category_average so this prediction
    # agrees with the average shown on the course; computing a plain mean of
    # percentages here made the two disagree whenever a category mixed
    # assignments of different sizes (5/10 and 90/100 gave 70% here but 86.36%
    # on the course page).
    graded_categories = {
        grade.category
        for grade in course.grades
        if grade.category != GradeCategory.FINAL.value
        and grade.score is not None
        and grade.max_score > 0
    }

    if final_weight == 0:
        raise ValueError("Course has no final exam.")

    earned_weighted_sum = sum(
        calculate_grade_category_average(course, category) * weights.get(category, 0.0)
        for category in graded_categories
    )
    graded_weight = sum(weights.get(category, 0.0) for category in graded_categories)

    unfinished_categories = [
        category for category, weight in weights.items()
        if (
            category != GradeCategory.FINAL.value
            and weight > 0
            and category not in graded_categories
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