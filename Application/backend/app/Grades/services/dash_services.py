import itertools
import uuid
from sqlalchemy.orm import Session
from app._database.models import CourseModel
from app.Grades.utils.enums import GradeCategory, is_additive
from app.Grades.schemas.dashboard import (
    AttentionItem,
    CourseDashboardEntry,
    TermPoint,
    UserGradeDashboard,
    YearSummary,
)
from app.Grades.services.grade_service import (
    calculate_gpa_points,
    calculate_required_final,
    counts_toward_average,
)
from app.Grades.utils.terms import (
    CURRENT,
    FUTURE,
    PAST,
    course_result_grade,
    effective_target,
    year_average,
)
from app.Grades.utils.weights import weight_problems
from app.Grades.services.course_service import get_all_courses
from app.Users.services.user_service import get_preferences, get_user


DEFAULT_TARGET_GRADE = 90.0


def is_graded(course) -> bool:
    """Whether this course has a mark that belongs in an average.

    False only for a transfer credit, which by definition carries credits and no
    score. Left in an average it would count as a zero, which is the whole
    reason the flag exists.
    """
    return not course.transfer_credit


def counts_toward_credits(course) -> bool:
    """Archived courses keep their grade but stop counting toward the degree."""
    return not course.archived


def expects_a_final(course) -> bool:
    """Whether "finished, but no final grade recorded" is worth saying.

    A course with no final exam is finished when the term ends, and a transfer
    credit was never going to be marked. Neither is something to act on.
    """
    return not course.no_final and not course.transfer_credit


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
        # A transfer credit has no grades to summarise, so it contributes
        # credits and stays out of every list on this page.
        if not is_graded(course):
            continue

        weights = course.category_weights
        # Read what the course list and the course page report, so every surface
        # shows one number per course -- including the null that means "nothing
        # marked yet" rather than a zero that means "scored nothing".
        average = course.reported_average
        unfinished_categories = [
            category for category, weight in weights.items()
            # Bonus is optional work, so an empty bonus category is not something
            # left undone. Counted here it would sit in Attention for the whole
            # term as a warning nothing could clear.
            if category != GradeCategory.FINAL.value
            and not is_additive(category)
            and weight > 0
            and not any(
                grade.category == category
                and grade.score is not None
                and counts_toward_average(grade)
                for grade in course.grades
            )
        ]

        needed_final_score = None
        if expects_a_final(course) and weights.get(GradeCategory.FINAL.value, 0.0) > 0:
            try:
                required_final = calculate_required_final(
                    db, user_id, course.id, target_grade, course=course,
                )
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
    required_credits, elective_credits = completed_credits_by_kind(course_list)

    # Only courses with a mark can be the best or the weakest one. An unmarked
    # course used to carry an average of 0.0 and was therefore reported as the
    # weakest course on the page -- a course not started reading as a course
    # being failed, which is the whole reason this figure is nullable.
    scored = [entry for entry in entries if entry.average is not None]
    best_course = max(scored, key=lambda entry: entry.average) if scored else None
    weakest_course = min(scored, key=lambda entry: entry.average) if scored else None
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
        credits_required=required_credits,
        credits_elective=elective_credits,
        credit_target=preferences.credit_target,
        best_course=best_course,
        weakest_course=weakest_course,
        courses_needing_final_score=courses_needing_final_score,
        unfinished_categories_by_course=unfinished_categories_by_course,
        attention=collect_attention(course_list, preferences.default_target_grade),
        term_history=build_term_history(course_list),
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
        if is_graded(course) and final and final > 0 and course.credits > 0:
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
        if not is_graded(course) or not final or final <= 0 or not course.credits:
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
    "in progress" until the whole term rolls over. Archived courses count
    toward neither, which is the point of archiving one.
    """
    completed = 0.0
    in_progress = 0.0

    for course in courses:
        if not counts_toward_credits(course):
            continue

        credits = course.credits or 0.0
        if is_completed(course):
            completed += credits
        elif course.term_bucket == CURRENT:
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


def collect_attention(courses, default_target: float) -> list[AttentionItem]:
    """Things worth acting on, most actionable first.

    Deliberately built from data already loaded -- no extra queries.
    """
    missing: list[AttentionItem] = []
    below: list[AttentionItem] = []
    weights: list[AttentionItem] = []

    for course in courses:
        # Nothing here applies to a credit that was never marked.
        if not is_graded(course):
            continue

        common = {"course_id": course.id, "course_code": course.code}

        # A finished course with no final silently drops out of the cumulative.
        if expects_a_final(course) and course.term_bucket == PAST and not (
            course.final_grade and course.final_grade > 0
        ):
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
                message = f"at {result:g}% against a {target:g}% target"
                on_final = final_needed(course, target)
                if on_final:
                    message += f"; {on_final}"
                below.append(AttentionItem(kind="below_target", **common, message=message))

        for problem in weight_problems(course):
            weights.append(AttentionItem(kind="weight_problem", **common, message=problem))

    return missing + below + weights


def final_needed(course, target: float) -> str | None:
    """What the final must do about a course below target, in words.

    Phase 1 item 2: the figure already existed behind a modal; here it is where
    the shortfall is reported. Nothing when the final is not still ahead -- no
    final, a final already marked -- because then there is nothing it can do.
    Built from the loaded course, like the rest of this function's callers: no
    query of its own.
    """
    if not expects_a_final(course):
        return None
    if not course.category_weights.get(GradeCategory.FINAL.value, 0.0):
        return None
    if any(
        grade.category == GradeCategory.FINAL.value and grade.score is not None
        for grade in course.grades
    ):
        return None
    try:
        answer = calculate_required_final(None, course.user_id, course.id, target, course=course)
    except ValueError:
        return None
    needed = answer.get("needed")
    if needed is None or needed <= 0:
        return None
    if not answer.get("possible"):
        return "out of reach even with 100% on the final"
    return f"needs {needed:g}% on the final"


def completed_credits_by_kind(courses) -> tuple[float, float]:
    """(required, elective) among completed credits.

    The `required` flag has been on the model since the beginning with nothing
    reading it.
    """
    required = elective = 0.0
    for course in courses:
        if not is_completed(course) or not counts_toward_credits(course):
            continue
        if course.required:
            required += course.credits or 0.0
        else:
            elective += course.credits or 0.0

    return required, elective


def is_completed(course) -> bool:
    """Past terms, plus current courses that already carry a final grade.

    A transfer credit is complete the moment it exists: the credit has already
    been granted, and waiting for a term it was never enrolled in to roll over
    would leave it in "in progress" forever.
    """
    if course.transfer_credit:
        return True
    if course.term_bucket == PAST:
        return True
    return course.term_bucket == CURRENT and bool(course.final_grade and course.final_grade > 0)


def build_term_history(courses) -> list[TermPoint]:
    """One point per term, in order, with the running cumulative beside it.

    Relies on get_all_courses returning courses sorted by year then term, so
    consecutive runs are the terms. Terms where nothing is recorded are left
    out rather than plotted as zero, which would drag the line to the floor.
    """
    history: list[TermPoint] = []
    accumulated: list = []

    for (year, semester), group in itertools.groupby(
        courses, key=lambda course: (course.year, course.semester)
    ):
        term_courses = list(group)
        accumulated.extend(term_courses)

        if not any(course_result_grade(course) is not None for course in term_courses):
            continue

        # Cumulative counts finished courses only, so it stays undefined until
        # one exists rather than reporting zero and flooring the chart.
        has_finals = any(
            course.final_grade and course.final_grade > 0 for course in accumulated
        )

        history.append(TermPoint(
            school_year=year,
            semester=semester,
            label=f"Y{year} {semester}",
            term_average=plain_average(term_courses),
            cumulative_average=calculate_cumulative_average(accumulated) if has_finals else None,
        ))

    return history
