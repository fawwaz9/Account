import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session, joinedload
from app._database.models import CourseModel, CourseCategoryWeightModel, GradeModel
from app.Grades.schemas.grade import GradeCreate, GradeUpdate, Grade as GradeSchema
from app.Grades.utils.enums import GradeCategory, GradeSchedule, is_additive
from app.Grades.utils.ordering import sorted_grades
from app.Grades.utils.terms import course_result_grade
from app.Grades.services.grade_schedule import (
    forget_block_times,
    sync_schedule_for_grade,
)
# Re-exported: callers import both from here, as they always have.
from app.Grades.utils.marks import MAX_COURSE_PERCENT, counts_toward_average  # noqa: F401
from app.Grades.utils import scheme_math
from app.shared.dates import user_today

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
    course.average = course_grade(course)

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

    before = forecast_before(course)
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
        due_time=grade_data.due_time,
        duration_minutes=grade_data.duration_minutes,
        schedule_as=grade_data.schedule_as.value,
        excluded=grade_data.excluded,
    )
    db.add(grade)
    db.flush()
    db.refresh(course)

    course.average = course_grade(course)
    keep_projection(course, before, user_today(db, user_id))
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

    before = forecast_before(course)
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
                due_time=grade_data.due_time,
                duration_minutes=grade_data.duration_minutes,
                schedule_as=grade_data.schedule_as.value,
                excluded=grade_data.excluded,
            )
            db.add(grade)
            created.append(grade)

        db.flush()
        db.refresh(course)
        course.average = course_grade(course)
        keep_projection(course, before, user_today(db, user_id))
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

    # Read before the merge overwrites it. "The grade had a time and the
    # student took it away" and "the grade never had one" look identical
    # afterwards, and they call for opposite things on the calendar.
    had_time = grade.due_time is not None
    before = forecast_before(course)

    for key, value in update_data.items():
        setattr(grade, key, value)

    if "category" in update_data:
        weights = course.category_weights
        grade.weight = weights.get(grade.category, 0.0)

    # A partial update can raise the score or lower max_score independently, so
    # the pair is only checkable after both have been applied.
    if score_exceeds_limit(grade.score, grade.max_score):
        raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

    # Each clearing cascades to what depends on it. A time of day only refines a
    # deadline and a length only refines a time, so "this has no due date any
    # more" must not leave 14:00 and two hours behind for the next edit to trip
    # over.
    #
    # Keyed on what the request actually *said*, not on the merged state: a
    # blanket "no time, so no length" would swallow the mistake below instead of
    # reporting it, turning a request to set a length on an all-day grade into a
    # silent no-op.
    dropping_date = "due_date" in update_data and update_data["due_date"] is None
    dropping_time = "due_time" in update_data and update_data["due_time"] is None

    if dropping_date:
        grade.due_time = None
    if dropping_date or dropping_time:
        grade.duration_minutes = None
        if had_time:
            # The gradebook had a time and the student took it away, which is
            # not the same as never having had one. Leaving the block at 14:00
            # would leave a start nothing stands behind.
            forget_block_times(db, grade)

    # Sending either one without what it hangs off is still a mistake rather
    # than an instruction, and is refused the way a task refuses an orphan time.
    if grade.due_time is not None and grade.due_date is None:
        raise ValueError("A time of day needs a date to go with it")
    if grade.duration_minutes is not None and grade.due_time is None:
        raise ValueError("A length needs a start time to run from")

    course.average = course_grade(course)
    keep_projection(course, before, user_today(db, user_id))
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

    course.average = course_grade(course)
    db.commit()
    return deleted_grade


def get_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID):
    _, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    return grade


def get_all_grades(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    # Same order as the course detail response, from the same function. A client
    # reading both must not see two different sequences.
    return sorted_grades(course.grades)


def record_grade(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, grade_id: uuid.UUID, score: float):
    course, grade = find_course_and_grade(db, user_id, course_id, grade_id)
    if grade is None:
        return None

    if score < 0:
        raise ValueError("score must be a positive value")
    if score_exceeds_limit(score, grade.max_score):
        raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

    before = forecast_before(course)
    grade.score = score
    course.average = course_grade(course)
    keep_projection(course, before, user_today(db, user_id))
    # The score landing is what closes the task.
    sync_schedule_for_grade(db, course, grade)
    db.commit()
    db.refresh(grade)
    return grade


def bonus_contribution(course: CourseModel) -> float:
    """Percentage points an additive category adds on top of the average.

    Measured against the whole course, never against the graded slice: a bonus
    worth 5% of the course is worth 5 points whenever you earn it, in week two or
    in week twelve. Dividing by the graded weight instead would have made the
    same bonus worth 25 points in a term that was only a fifth marked, which is
    the kind of number that looks like a bug because it is one.
    """
    weights = course.category_weights
    contribution = 0.0

    for category, weight in weights.items():
        if not is_additive(category) or weight <= 0:
            continue
        contribution += calculate_grade_category_average(course, category) * weight / 100.0

    return contribution


def counting_components(course: CourseModel):
    """The components of the scheme picked as this course's grade, or None.

    None when no scheme is picked -- and, defensively, when the id names no
    scheme of this course, so a stale id falls back to the course's own weights
    rather than to nothing.
    """
    scheme_id = getattr(course, "counting_scheme_id", None)
    if scheme_id is None:
        return None
    from app.Grades.schemas.scheme import SchemeComponent

    for scheme in course.grading_schemes:
        if scheme.id == scheme_id:
            return [SchemeComponent.model_validate(c) for c in scheme.components]
    return None


@dataclass(frozen=True)
class Forecast:
    """The course's grade as it stood before a write, and whether it was still a forecast."""
    grade: float | None  # None: nothing marked, so nothing was projected
    ended: bool


def final_is_marked(course: CourseModel) -> bool:
    return any(
        g.category == GradeCategory.FINAL.value and g.score is not None and counts_toward_average(g)
        for g in course.grades
    )


def forecast_ended(course: CourseModel) -> bool:
    """The final is marked or the official result is in: no longer a prediction."""
    return final_is_marked(course) or bool(course.final_grade and course.final_grade > 0)


def forecast_before(course: CourseModel) -> Forecast:
    """Read before a write that might end the forecast (Phase 1 D34)."""
    marked = any(
        g.score is not None and g.max_score > 0 and counts_toward_average(g) and not is_additive(g.category)
        for g in course.grades
    )
    return Forecast(course_grade(course) if marked else None, forecast_ended(course))


def keep_projection(course: CourseModel, before: Forecast, today: date) -> None:
    """Keep the last projection before the final, the first time a write ends the forecast.

    Only the first time: a final re-entered later must not replace the number
    that was a real prediction with one that was not.
    """
    if course.projected_before_final is not None or before.grade is None or before.ended:
        return
    if forecast_ended(course):
        course.projected_before_final = round(before.grade, 2)
        course.projected_on = today


def course_grade(course: CourseModel) -> float:
    """The course's grade: the picked scheme's average, or the course's own.

    The one function every stored average is written through (Phase 1 D25), so
    the dashboard, letter, GPA, cumulative and Attention -- which all read the
    stored figure -- follow a picked scheme without knowing schemes exist.
    """
    components = counting_components(course)
    if components is None:
        return calculate_current_average(course)
    return scheme_math.project(course, components)[0]


def project_course(course: CourseModel, unmarked: float, overrides: dict | None = None) -> float:
    """project_average, through the picked scheme when there is one."""
    components = counting_components(course)
    if components is None:
        return project_average(course, unmarked, overrides)
    return scheme_math.project(course, components, scheme_math.everywhere(components, unmarked), overrides)[0]


def calculate_current_average(course: CourseModel) -> float:
    graded = [
        g for g in course.grades
        if g.score is not None and g.max_score > 0 and counts_toward_average(g)
    ]
    if not graded:
        return 0.0

    weights = course.category_weights
    # Bonus is held out of both sums and added back at the end. Left in, its
    # weight would join the denominator -- so partway through a term, a 5% bonus
    # sitting next to a 20% batch of marked assignments would have been treated
    # as a fifth of the grade rather than as five points on top of it.
    categories_present = {
        g.category for g in graded if not is_additive(g.category)
    }

    total_weight = sum(weights.get(category, 0.0) for category in categories_present)
    earned = 0.0

    if total_weight > 0:
        weighted_sum = sum(
            calculate_grade_category_average(course, category) * weights.get(category, 0.0)
            for category in categories_present
        )
        # Weight past 100 across the scoring categories is bonus by another
        # route: it adds marks without enlarging the denominator, which is how a
        # course marked out of 101% works. Both routes still cap the course at 100.
        denominator = min(total_weight, MAX_COURSE_PERCENT)
        earned = weighted_sum / denominator

    total = earned + bonus_contribution(course)

    # Bonus earned before anything else is marked is real, so a course showing
    # only bonus is not zero -- but it is also not a percentage of nothing, which
    # is why `earned` stays at 0.0 rather than the function returning early.
    return min(round(total, 2), MAX_COURSE_PERCENT)


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


def calculate_letter_grade(course, average: float | None = None) -> str:
    """Letter for the course's result, or "" when nothing is recorded.

    Reads course_result_grade rather than the raw average, so a finished course
    carrying only the professor's final_grade does not read as an F, and an
    untouched course shows no letter at all instead of failing.

    `average` is passed straight through, for a caller holding a freshly
    computed value it has deliberately not written to the row.
    """
    result = course_result_grade(course, average)
    if result is None:
        return ""

    return grade_scale_row(result)[0]


def calculate_gpa_points(average: float | None) -> float:
    """Grade points for a percentage, on the configured scale."""
    return grade_scale_row(average or 0.0)[1]


def category_average_assuming(
    course: CourseModel, category, unmarked: float, overrides: dict | None = None
) -> float | None:
    """A category's average if every unmarked item scored `unmarked` of its max.

    `unmarked` is a fraction: 1.0 for the optimistic case, 0.0 for the grim one.
    Returns None when the category holds nothing at all, which the caller has to
    treat differently -- an empty category is unknown, not zero.

    The granularity matters. An assignment added before it is marked already
    carries its max_score, so a course that has been kept up to date knows
    exactly how much work is outstanding and how much it is worth. Projecting a
    whole category as all-or-nothing would throw that away and give a band so
    wide it says nothing.
    """
    category_value = category.value if isinstance(category, GradeCategory) else category
    items = [
        g for g in course.grades
        if g.category == category_value and g.max_score > 0 and counts_toward_average(g)
    ]
    if not items:
        return None

    possible = sum(g.max_score for g in items)
    if possible == 0:
        return None

    earned = sum(assumed_score(g, unmarked, overrides) for g in items)
    return round(earned / possible * 100, 2)


def assumed_score(grade, unmarked: float, overrides: dict | None) -> float:
    """What one grade is worth under an assumption.

    `overrides` names particular grades by id and wins over everything, which is
    what lets a caller ask "and what if *this* one went full marks" without
    touching the row. It has to be a parameter rather than a temporary write:
    setting grade.score and restoring it would make a read that mutates a mapped
    column, which is one stray commit from a GET that changes data -- the same
    trap course_result_grade's docstring warns about.
    """
    if overrides is not None and grade.id in overrides:
        return overrides[grade.id] * grade.max_score
    if grade.score is not None:
        return grade.score
    return unmarked * grade.max_score


def project_average(
    course: CourseModel, unmarked: float, overrides: dict | None = None
) -> float:
    """The course average if everything still outstanding went `unmarked` way.

    Same shape as calculate_current_average, and deliberately so: a projection
    that did not agree with the live number at the ends -- all marked, or none --
    would be a second opinion about the same course.
    """
    weights = course.category_weights

    scoring = [
        (category, weight) for category, weight in weights.items()
        if weight > 0 and not is_additive(category)
    ]
    total_weight = sum(weight for _, weight in scoring)

    earned = 0.0
    if total_weight > 0:
        weighted_sum = 0.0
        for category, weight in scoring:
            average = category_average_assuming(course, category, unmarked, overrides)
            # A weighted category with nothing in it yet is unknown rather than
            # zero, so it takes the assumption whole: full marks at best, none at
            # worst. That is the honest width of not having entered anything.
            if average is None:
                average = unmarked * 100.0
            weighted_sum += average * weight
        denominator = min(total_weight, MAX_COURSE_PERCENT)
        earned = weighted_sum / denominator

    bonus = 0.0
    for category, weight in weights.items():
        if not is_additive(category) or weight <= 0:
            continue
        average = category_average_assuming(course, category, unmarked, overrides)
        if average is None:
            average = unmarked * 100.0
        bonus += average * weight / 100.0

    return min(round(earned + bonus, 2), MAX_COURSE_PERCENT)


def calculate_grade_band(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Where this course can still finish: best case, worst case, and now.

    The question a running average cannot answer. 78% with everything marked is
    a result; 78% with the final still to come is anywhere between a fail and an
    A, and which one it is decides whether this is the course to spend the
    weekend on.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    best = project_course(course, 1.0)
    worst = project_course(course, 0.0)
    current = course_grade(course)

    outstanding = sum(
        1 for g in course.grades
        if g.score is None and g.max_score > 0 and counts_toward_average(g)
    )
    components = counting_components(course)
    weights = (
        {c.category.value: c.weight for c in components} if components is not None
        else course.category_weights
    )
    empty_categories = [
        category for category, weight in weights.items()
        if weight > 0
        and not is_additive(category)
        and category_average_assuming(course, category, 1.0) is None
    ]

    return {
        "best": best,
        "worst": worst,
        "current": current,
        # Nothing left to mark means the band has closed: best and worst have met
        # and the course simply is what it is.
        "settled": outstanding == 0 and not empty_categories,
        "outstanding_items": outstanding,
        "empty_categories": empty_categories,
    }


def calculate_required_final(
    db: Session,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    target_grade: float,
    course: CourseModel | None = None,
):
    """What the final must score to finish at `target_grade`.

    `course` lets a caller that already holds the row pass it in. The dashboard
    does, and without it this re-fetched a course that was already in the
    identity map once per course -- a third of the N+1 on that page.
    """
    if course is None:
        course = get_user_course(db, user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    components = counting_components(course)
    if components is not None:
        return required_final_under_scheme(course, components, target_grade)

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
        and not is_additive(grade.category)
        and grade.score is not None
        and grade.max_score > 0
        and counts_toward_average(grade)
    }

    if final_weight == 0:
        raise ValueError("Course has no final exam.")

    earned_weighted_sum = sum(
        calculate_grade_category_average(course, category) * weights.get(category, 0.0)
        for category in graded_categories
    )
    graded_weight = sum(weights.get(category, 0.0) for category in graded_categories)

    # Bonus already banked lowers the bar rather than raising the denominator.
    # Counting it on both sides -- as marks earned and as weight to make up --
    # would have cancelled most of its own effect out.
    banked_bonus = bonus_contribution(course)

    unfinished_categories = [
        category for category, weight in weights.items()
        if (
            category != GradeCategory.FINAL.value
            # Bonus is optional by definition, so an empty bonus category is not
            # unfinished work. Left in, it would sit here all term as a warning
            # that no amount of effort could clear.
            and not is_additive(category)
            and weight > 0
            and category not in graded_categories
        )
    ]
    # Capped like calculate_current_average's denominator: weight past 100 is
    # bonus by another route, so it adds marks without enlarging what they are
    # divided by. Uncapped, a course weighted 125% was told it needed 191% on
    # the final when 96.16% brings its shown average to the target (Phase 1 D25,
    # found by the counting-scheme invariant).
    counted_weight = min(graded_weight + final_weight, MAX_COURSE_PERCENT)
    needed = (
        ((target_grade - banked_bonus) * counted_weight) - earned_weighted_sum
    ) / final_weight
    return {
        "needed": round(needed, 2),
        "possible": 0 <= needed <= 100,
        "unfinished_categories": unfinished_categories,
    }


#: How far the search for a required final looks, in percent. Past 100 is
#: reported (as impossible) rather than clipped, as the formula does.
REQUIRED_FINAL_CEILING = 1000.0


def required_final_under_scheme(course: CourseModel, components, target_grade: float) -> dict:
    """calculate_required_final's answer, under a picked scheme.

    A scheme's drops and replacements make the course's average piecewise, so
    instead of the closed formula this searches for the lowest final score that
    reaches the target -- the average never falls as the final rises, which is
    what makes the search sound. Asked the same way as the formula: every final
    item scores the value tried, an empty final takes it whole, and categories
    with nothing marked stay out, reported as unfinished.
    """
    final = GradeCategory.FINAL.value
    final_component = next((c for c in components if c.category.value == final and c.weight > 0), None)
    if final_component is None:
        raise ValueError("Course has no final exam.")

    final_ids = [g.id for g in course.grades if g.category == final and counts_toward_average(g)]

    def average_with_final(percent: float) -> float:
        fraction = percent / 100.0
        return scheme_math.project(
            course, components, {final: fraction}, {grade_id: fraction for grade_id in final_ids}, precise=True,
        )[0]

    if average_with_final(0.0) >= target_grade:
        needed = 0.0
    elif average_with_final(REQUIRED_FINAL_CEILING) < target_grade:
        needed = REQUIRED_FINAL_CEILING
    else:
        low, high = 0.0, REQUIRED_FINAL_CEILING
        for _ in range(60):
            middle = (low + high) / 2
            if average_with_final(middle) >= target_grade:
                high = middle
            else:
                low = middle
        needed = high

    unfinished = [
        c.category.value for c in components
        if c.category.value != final
        and not is_additive(c.category.value)
        and c.weight > 0
        and scheme_math.category_average(course, c.category.value)[0] is None
    ]
    return {
        "needed": round(needed, 2),
        "possible": 0 <= needed <= 100,
        "unfinished_categories": unfinished,
    }


def category_points(course: CourseModel, category) -> float:
    """What a category contributes to the course, in marks out of its weight.

    The figure beside each category on the course page: "11.83/12". Computed here
    rather than in the client, which had the weight and the *rounded* average and
    multiplied them -- rounding twice, so a category worth exactly 11.825 read
    11.82.

    Done in Decimal, which is not fussiness. COSC 111's assignments are 236.5 of
    240 at a weight of 12, exactly 11.825, which should read 11.83. In binary
    floating point 11.825 does not exist: the nearest double is
    11.82499999999999928..., genuinely below the midpoint, so every rounding
    scheme that touches a float -- round(), Decimal(float).quantize, JavaScript's
    Math.round(x * 100) / 100 -- correctly rounds it down and the hundredth is
    already gone before anyone can round it. Converting through str() is what
    keeps it exact: Decimal(str(236.5)) is 236.5, while Decimal(236.5) is the
    binary approximation spelled out in full.

    Deliberately standalone. The averaging engine still scales from the rounded
    category average, because changing that would move the number stored on the
    course and therefore the dashboard, the GPA and the letter grade -- for a
    hundredth that is invisible there. This is the one figure a student reads
    against their own arithmetic on a page of marks, so this is the one that
    earns the ceremony.
    """
    category_value = category.value if isinstance(category, GradeCategory) else category
    weight = course.category_weights.get(category_value, 0.0)

    items = [
        g for g in course.grades
        if g.category == category_value and g.score is not None and g.max_score > 0
        and counts_toward_average(g)
    ]
    if not items or weight == 0:
        return 0.0

    earned = sum(Decimal(str(g.score)) for g in items)
    possible = sum(Decimal(str(g.max_score)) for g in items)
    if possible == 0:
        return 0.0

    points = earned / possible * Decimal(str(weight))
    return float(points.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_grade_category_average(course: CourseModel, category: GradeCategory) -> float:
    category_value = category.value if isinstance(category, GradeCategory) else category
    category_grades = [
        g for g in course.grades
        if g.category == category_value and g.score is not None and g.max_score > 0
        and counts_toward_average(g)
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