"""A category the student is quietly worse at than their own average.

Grades already answers "how is this course doing." This answers the question
nothing else does: pooled across every course, is one *category* -- labs,
quizzes, participation -- where marks are consistently lost, rather than one
course being hard. Derived entirely from what `grades` and
`course_category_weights` already store; nothing new is written.

The comparison is pooled percentages, not course weights: every marked item of
a category, across every graded course, earned over possible -- the same
arithmetic `calculate_grade_category_average` does for one course, done here
across all of them at once. Weighting by category *weight* would answer a
different question (which category costs the most), and this one is about
where marks are actually being lost relative to how the student does
everywhere else.
"""

import uuid
from collections import defaultdict

from sqlalchemy.orm import Session

from app.Grades.schemas.blind_spot import BLIND_SPOT_BANDS, MIN_COURSES, CategoryBlindSpot
from app.Grades.services.course_service import get_all_courses
from app.Grades.services.dash_services import is_graded
from app.Grades.services.grade_service import counts_toward_average
from app.Grades.utils.enums import is_additive
from app.Users.services.user_service import get_user


def is_marked(grade) -> bool:
    return grade.score is not None and grade.max_score > 0 and counts_toward_average(grade)


def severity_for(gap: float) -> str | None:
    for severity, (low, high) in BLIND_SPOT_BANDS.items():
        if low <= gap < high:
            return severity
    return None


def category_blind_spots(db: Session, user_id: uuid.UUID) -> list[CategoryBlindSpot] | None:
    if get_user(db, user_id) is None:
        return None

    courses = [course for course in get_all_courses(db, user_id) if is_graded(course)]

    overall_earned = 0.0
    overall_possible = 0.0
    #: category -> (earned, possible, item_count, {course codes})
    by_category: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0, set()])

    for course in courses:
        for grade in course.grades:
            if not is_marked(grade) or is_additive(grade.category):
                continue

            overall_earned += grade.score
            overall_possible += grade.max_score

            bucket = by_category[grade.category]
            bucket[0] += grade.score
            bucket[1] += grade.max_score
            bucket[2] += 1
            bucket[3].add(course.code)

    if overall_possible == 0:
        return []

    overall_average = overall_earned / overall_possible * 100

    findings = []
    for category, (earned, possible, item_count, codes) in by_category.items():
        if possible == 0 or len(codes) < MIN_COURSES:
            continue

        average = earned / possible * 100
        gap = overall_average - average
        severity = severity_for(gap)
        if severity is None:
            continue

        findings.append(CategoryBlindSpot(
            category=category,
            average=round(average, 2),
            overall_average=round(overall_average, 2),
            gap=round(gap, 2),
            severity=severity,
            course_count=len(codes),
            item_count=item_count,
            course_codes=sorted(codes),
        ))

    findings.sort(key=lambda finding: finding.gap, reverse=True)
    return findings
