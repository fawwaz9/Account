""""Worth doing next": a course's unmarked items ranked by what they are worth.

Each item's leverage is the spread between the projected average with it at full
marks and at zero, everything else outstanding held at `BASELINE`. Items rank by
points per hour where the student estimated the task, then by points, and the top
`TOP_N` are returned; an item without an estimate is never given a rate.
"""
import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel, GradeModel, TaskModel
from app.Grades.schemas.cheapest_path import CheapestPath, RemainingItem
from app.Grades.services.grade_service import (
    counts_toward_average,
    get_user_course,
    project_course,
)
from app.Grades.utils.enums import is_additive
from app.Grades.utils.terms import effective_target

#: Held constant while one item is varied. Zero rather than anything else
#: because the projection clamps at 100: with the other outstanding items
#: assumed grim, the full-marks half of the spread has the most room before it
#: meets the ceiling and starts understating the item.
BASELINE = 0.0

#: How many rows the panel shows. The rest are ranked and then dropped, rather
#: than never ranked: the cut has to come after the ordering or "top three"
#: means "first three found".
TOP_N = 3


def rank_key(item: RemainingItem) -> tuple[int, float, float, str]:
    """Return the sort key: rated items first, by points per hour, then points.

    Args:
        item: One outstanding item.

    Returns:
        A tuple that sorts ascending into the display order; the name breaks ties.
    """
    rated = item.per_hour is not None
    return (0 if rated else 1, -(item.per_hour or 0.0), -item.leverage, item.name)


def item_leverage(course: CourseModel, grade: GradeModel) -> float:
    """Return the points of final average one unmarked item still controls.

    Args:
        course: The course the item belongs to.
        grade: The unmarked item.

    Returns:
        Projected average at full marks minus at zero, rounded to 2 places.
    """
    full = project_course(course, BASELINE, {grade.id: 1.0})
    none = project_course(course, BASELINE, {grade.id: 0.0})
    return round(full - none, 2)


def estimates_by_grade(db: Session, course_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Return the student's minute estimates from the tasks this course's grades raised.

    Args:
        db: Open database session.
        course_id: The course.

    Returns:
        Grade id to estimated minutes, for tasks that carry an estimate.
    """
    rows = (
        db.query(TaskModel.grade_id, TaskModel.estimated_minutes)
        .join(GradeModel, GradeModel.id == TaskModel.grade_id)
        .filter(
            GradeModel.course_id == course_id,
            TaskModel.estimated_minutes.isnot(None),
        )
        .all()
    )
    return {row.grade_id: row.estimated_minutes for row in rows}


def cheapest_path(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CheapestPath:
    """Return the three unmarked items in a course most worth doing next.

    Dropped, bonus and zero-leverage items are left out.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The target, the stored current average, the best case, whether the target is
        reachable, and the ranked items with counts.

    Raises:
        ValueError: If the course is missing or another user's.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        raise ValueError("Course not found.")

    target = effective_target(course, default_target(db, user_id))
    estimates = estimates_by_grade(db, course.id)

    items: list[RemainingItem] = []
    for grade in course.grades:
        if grade.score is not None or grade.max_score <= 0:
            continue
        if not counts_toward_average(grade):
            continue
        # A bonus category adds on top of the average rather than composing it,
        # so it is not a route to a target -- chasing one is how you spend a
        # weekend moving a number that was never going to reach.
        if is_additive(grade.category):
            continue

        leverage = item_leverage(course, grade)
        if leverage <= 0:
            # A category carrying no weight cannot move anything. Listing it
            # would be offering work that changes nothing.
            continue

        minutes = estimates.get(grade.id)
        items.append(RemainingItem(
            grade_id=grade.id,
            name=grade.name,
            category=grade.category,
            max_score=grade.max_score,
            due_date=grade.due_date,
            leverage=leverage,
            estimated_minutes=minutes,
            per_hour=round(leverage / (minutes / 60), 2) if minutes else None,
        ))

    items.sort(key=rank_key)
    shown = items[:TOP_N]

    # Counted over what is shown rather than over everything outstanding: these
    # two feed a line that says "these" beside three visible rows, and a count
    # taken from the whole set would be describing items nobody can see.
    estimated = [item for item in shown if item.per_hour is not None]

    best = project_course(course, 1.0)
    return CheapestPath(
        target=target,
        # The stored column, not a fresh calculation. Every write path
        # recomputes and commits it, and the course header on the same page
        # renders that value -- recomputing here is how one screen ends up
        # showing two different averages for one course.
        current=round(course.average or 0.0, 2),
        best=best,
        # Says whether the target is still arithmetically available, so the
        # ranking is not read as a plan that gets you there when nothing can.
        reachable=best >= target,
        items=shown,
        # What the cut hid, so the panel can say "top 3 of 8" rather than
        # implying eight outstanding items are three.
        remaining_count=len(items),
        estimated_count=len(estimated),
        unestimated_count=len(shown) - len(estimated),
    )


def default_target(db: Session, user_id: uuid.UUID) -> float:
    """Return the account's default target, or `DEFAULT_TARGET_GRADE` without one.

    A default of 0 also falls back to `DEFAULT_TARGET_GRADE`.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        The target as a percentage.
    """
    from app.Grades.services.dash_services import DEFAULT_TARGET_GRADE
    from app.Users.services.user_service import get_preferences, get_user

    user = get_user(db, user_id)
    if user is None:
        return DEFAULT_TARGET_GRADE
    return get_preferences(user).default_target_grade or DEFAULT_TARGET_GRADE
