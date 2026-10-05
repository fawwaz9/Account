"""Which remaining item is worth doing next.

A running average says where a course is. It does not say what to do about it,
and with six things outstanding the useful question is which one moves the
number most -- and, where the student has said how long something will take,
which moves it most per hour.

**Leverage is a spread, not a projection.** Each item is scored by the
difference between the course average with that item at full marks and the same
average with it at zero, every other outstanding item held constant. That
difference is the share of the final average the item controls, and it comes out
the same whatever the other items are assumed to do, because their contribution
appears in both halves and cancels.

**Ranked by rate, then by points, and cut to three.** Points per hour leads,
because the question the panel answers is what to spend the next hour on, and
points break ties beneath it. Hours come from the task a dated grade raised.

An item with no estimate has no rate and is given none: zero would sort it last
as if it paid nothing, infinity first as if it were free, and both are lies. So
rated items rank above unrated, and the unrated fall back to points among
themselves.

That carries a consequence worth stating plainly, because it was a bug here
once. A single estimated item ranks first on its course whatever it is worth,
since nothing else has a rate to beat it -- a lab worth four points can sit
above a final worth forty-five. With one estimate across twenty-three
outstanding items that is the common case, not the corner, which is why the
panel keeps asking for the missing ones. The ranking is worth exactly as much
as the estimates feeding it.

Three rows, because a ranked list of eight is one you read the top of anyway.
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
    """Rate first, then points. Unrated items sort below every rated one.

    Separated out because it is the whole product decision, and burying it in a
    lambda inside a hundred-line function is how it gets changed by accident.

    The first element is deliberately belt-and-braces, and a mutation proved it:
    removing it changes no behaviour and fails no test today, because an item
    only reaches here with leverage above zero and a positive number of minutes,
    so every rated item already has a rate above zero and the `or 0.0` alone
    puts the unrated last. It stays because that is an invariant held by a
    filter fifty lines away -- admit one zero-leverage item and the fallback
    silently starts ranking unrated work among the rated instead of beneath it.
    """
    rated = item.per_hour is not None
    return (0 if rated else 1, -(item.per_hour or 0.0), -item.leverage, item.name)


def item_leverage(course: CourseModel, grade: GradeModel) -> float:
    """How many points of final average this one item still controls."""
    full = project_course(course, BASELINE, {grade.id: 1.0})
    none = project_course(course, BASELINE, {grade.id: 0.0})
    return round(full - none, 2)


def estimates_by_grade(db: Session, course_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Minutes the student put on the task each of this course's grades raised.

    Their own number: `sync_task` seeds a task from a grade but never overwrites
    an estimate, precisely so re-saving a grade cannot revert one.

    Scoped to the course, which it was not at first: the filter named only
    "has a grade and has an estimate", so every course page load read every such
    task in the table. Nothing came back wrong, because a grade id matches one
    grade -- it was a full scan whose result happened to be right, which is the
    kind of thing that stays invisible until the table is large.
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
    """Rank what is left in a course by what it is worth doing."""
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
    """The account default a course with no target of its own falls back to."""
    from app.Grades.services.dash_services import DEFAULT_TARGET_GRADE
    from app.Users.services.user_service import get_preferences, get_user

    user = get_user(db, user_id)
    if user is None:
        return DEFAULT_TARGET_GRADE
    return get_preferences(user).default_target_grade or DEFAULT_TARGET_GRADE
