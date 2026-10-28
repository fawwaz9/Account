"""Reads of the sealed aggregates, each through its floor (Phase 3, D11).

Shared figures live in sealed tables that the API's role cannot read; on Postgres
every read here calls the one `SECURITY DEFINER` function that answers for its
table, and that function applies the floor itself. SQLite has no row security, so
there each read is a plain query applying the same rules; the tests run both.
"""
import re
import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    COHORT_FLOOR, COUNTED_AFTER_DAYS, OFFICE_HOUR_WINDOW_DAYS, WORK_HOURS_PER_YEAR, CourseIntelModel,
    DIRECTORY_FLOOR, ActivityModel, CampusBoardModel, GradeDistributionModel, JobApplicationModel, JobModel,
    MERCHANT_FLOOR, MerchantCategoryModel, TeamMemberModel, TeamModel,
    OfficeHourCheckinModel, OfficeHourSlotModel, SalaryFigureModel, SalaryShareModel, SpendCategoryModel,
    TermReviewModel, TransactionModel, UserModel, utc_now,
)

#: Month and day each term code's term ends, and the years to add to the code's
#: year: "2025W2" (Winter) ends on Apr 30, 2026.
TERM_ENDS = {"W1": (12, 31, 0), "W2": (4, 30, 1), "S1": (6, 30, 0), "S2": (8, 31, 0)}


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


def term_code_end(code: str | None) -> date | None:
    """Return the last day of the term a code such as "2025W1" names.

    Args:
        code: A term code: four digits of year, then W1, W2, S1 or S2.

    Returns:
        The term's last day; None for a code of any other shape.
    """
    if not code or len(code) != 6 or not code[:4].isdigit() or code[4:] not in TERM_ENDS:
        return None
    month, day, years = TERM_ENDS[code[4:]]
    return date(int(code[:4]) + years, month, day)


def term_closed(code: str | None, today: date) -> bool:
    """Return whether a term's answers may reach a shown figure today.

    Args:
        code: The term code.
        today: The day to judge by (UTC on Postgres, so the same here).

    Returns:
        True once `COUNTED_AFTER_DAYS` have passed since the term ended; False for an
        unreadable code.
    """
    ends = term_code_end(code)
    return ends is not None and ends + timedelta(days=COUNTED_AFTER_DAYS) < today


@dataclass(frozen=True)
class Band:
    """One band of one term's grade counts, as the read function answers it.

    Attributes:
        term_code: The term, such as "2025W1".
        bucket: The band's lower bound: 0 for below 50, then 50, 55 ... 95.
        contributors: Grades counted in the band.
    """
    term_code: str
    bucket: int
    contributors: int


def grade_distribution(db: Session, course_key: str, today: date) -> list[Band]:
    """Return a course's grade bands for every closed term at or above the floor.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".
        today: Today in UTC, used on SQLite only; Postgres reads its own clock.

    Returns:
        Bands, newest term first, lowest band first within a term; empty when no term
        qualifies.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_grade_distribution(:k)"), {"k": course_key}).all()
        return [Band(r.term_code, r.bucket, r.contributors) for r in rows]
    by_term: dict[str, list[GradeDistributionModel]] = defaultdict(list)
    for row in db.query(GradeDistributionModel).filter(GradeDistributionModel.course_key == course_key):
        by_term[row.term_code].append(row)
    out = []
    for term in sorted(by_term, reverse=True):
        rows = by_term[term]
        if sum(r.contributors for r in rows) < COHORT_FLOOR or not term_closed(term, today):
            continue
        out += [Band(term, r.bucket, r.contributors) for r in sorted(rows, key=lambda r: r.bucket)]
    return out


def _utc_today() -> date:
    """Return today's date in UTC, the clock the Postgres functions read."""
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class CourseIntel:
    """What term reviews say about a course; each figure None below the floor.

    Attributes:
        hours_answers: People who gave weekly hours.
        hours_median: Their median weekly hours.
        difficulty_answers: People who rated difficulty.
        difficulty_mean: Mean difficulty, 1-5.
        clarity_answers: People who rated instructor clarity.
        clarity_mean: Mean clarity, 1-5.
        again_answers: People who said whether they'd take it again.
        again_share: Percentage of them who said yes.
    """
    hours_answers: int | None
    hours_median: float | None
    difficulty_answers: int | None
    difficulty_mean: float | None
    clarity_answers: int | None
    clarity_mean: float | None
    again_answers: int | None
    again_share: float | None


def _at_floor(answers: int | None, value):
    """Return `value` when `answers` reaches the floor, else None."""
    return value if answers is not None and answers >= COHORT_FLOOR else None


def recount_course_intel(db: Session, today: date | None = None) -> int:
    """Rebuild the course figures from scratch from every counted term review.

    One answer per person per course (their latest counted term's), from live
    accounts and reviews not skipped; a figure below the floor is written as null, and
    a course with none at the floor gets no row.

    Args:
        db: Open session; needs no acting user.
        today: Day to judge counted terms by, on SQLite only; None means today in UTC.

    Returns:
        The number of course rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_course_intel()")).scalar()
        db.commit()
        return int(written or 0)
    today = today or _utc_today()
    db.query(CourseIntelModel).delete(synchronize_session=False)
    latest: dict[tuple[uuid.UUID, str], TermReviewModel] = {}
    rows = (
        db.query(TermReviewModel)
        .join(UserModel, UserModel.id == TermReviewModel.user_id)
        .filter(TermReviewModel.skipped.is_(False), UserModel.deleted_at.is_(None),
                TermReviewModel.course_key.isnot(None))
        .all()
    )
    for review in rows:
        if not term_closed(review.term_code, today):
            continue
        key = (review.user_id, review.course_key)
        if key not in latest or review.term_code > latest[key].term_code:
            latest[key] = review
    by_course: dict[str, list[TermReviewModel]] = defaultdict(list)
    for (_, course_key), review in latest.items():
        by_course[course_key].append(review)
    written = 0
    now = utc_now()
    for course_key, reviews in by_course.items():
        hours = [r.hours_per_week for r in reviews if r.hours_per_week is not None]
        difficulty = [r.difficulty for r in reviews if r.difficulty is not None]
        clarity = [r.clarity for r in reviews if r.clarity is not None]
        again = [r.would_take_again for r in reviews if r.would_take_again is not None]
        if max(len(hours), len(difficulty), len(clarity), len(again)) < COHORT_FLOOR:
            continue
        db.add(CourseIntelModel(
            course_key=course_key,
            hours_answers=_at_floor(len(hours), len(hours)),
            hours_median=_at_floor(len(hours), float(statistics.median(hours)) if hours else None),
            difficulty_answers=_at_floor(len(difficulty), len(difficulty)),
            difficulty_mean=_at_floor(len(difficulty), statistics.fmean(difficulty) if difficulty else None),
            clarity_answers=_at_floor(len(clarity), len(clarity)),
            clarity_mean=_at_floor(len(clarity), statistics.fmean(clarity) if clarity else None),
            again_answers=_at_floor(len(again), len(again)),
            again_share=_at_floor(len(again), 100.0 * sum(again) / len(again) if again else None),
            computed_at=now,
        ))
        written += 1
    db.commit()
    return written


def course_intel(db: Session, course_key: str) -> CourseIntel | None:
    """Return what term reviews say about a course, each figure through the floor.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".

    Returns:
        The figures, or None when the course has no row.
    """
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_course_intel(:k)"), {"k": course_key}).first()
        return None if row is None else CourseIntel(*row)
    row = db.query(CourseIntelModel).filter(CourseIntelModel.course_key == course_key).first()
    if row is None:
        return None
    return CourseIntel(
        _at_floor(row.hours_answers, row.hours_answers), _at_floor(row.hours_answers, row.hours_median),
        _at_floor(row.difficulty_answers, row.difficulty_answers),
        _at_floor(row.difficulty_answers, row.difficulty_mean),
        _at_floor(row.clarity_answers, row.clarity_answers), _at_floor(row.clarity_answers, row.clarity_mean),
        _at_floor(row.again_answers, row.again_answers), _at_floor(row.again_answers, row.again_share),
    )


@dataclass(frozen=True)
class Slot:
    """How busy one weekday-and-hour of a course's office hours usually is.

    Attributes:
        weekday: Local weekday, 0 Monday to 6 Sunday.
        hour: Local hour, 0-23.
        people: Distinct people whose check-in counted.
        none_votes: How many found no line.
        short_votes: How many found a short line.
        long_votes: How many found a long line.
    """
    weekday: int
    hour: int
    people: int
    none_votes: int
    short_votes: int
    long_votes: int


def recount_office_hours(db: Session, now: datetime | None = None) -> int:
    """Rebuild the office-hour slots from scratch from recent check-ins.

    Each person's latest check-in per course, weekday and hour in the last
    `OFFICE_HOUR_WINDOW_DAYS` counts once; live accounts only; no slot below the floor.

    Args:
        db: Open session; needs no acting user.
        now: The moment to measure the window from, on SQLite only (naive UTC).

    Returns:
        The number of slot rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_office_hours()")).scalar()
        db.commit()
        return int(written or 0)
    since = (now or utc_now()) - timedelta(days=OFFICE_HOUR_WINDOW_DAYS)
    db.query(OfficeHourSlotModel).delete(synchronize_session=False)
    latest: dict[tuple, OfficeHourCheckinModel] = {}
    rows = (
        db.query(OfficeHourCheckinModel)
        .join(UserModel, UserModel.id == OfficeHourCheckinModel.user_id)
        .filter(UserModel.deleted_at.is_(None), OfficeHourCheckinModel.checked_at > since)
        .all()
    )
    for row in rows:
        key = (row.user_id, row.course_key, row.weekday, row.hour)
        if key not in latest or row.checked_at > latest[key].checked_at:
            latest[key] = row
    slots: dict[tuple, list[str]] = defaultdict(list)
    for (_, course_key, weekday, hour), row in latest.items():
        slots[(course_key, weekday, hour)].append(row.wait)
    written = 0
    stamp = utc_now()
    for (course_key, weekday, hour), waits in slots.items():
        if len(waits) < COHORT_FLOOR:
            continue
        db.add(OfficeHourSlotModel(course_key=course_key, weekday=weekday, hour=hour, people=len(waits),
                                   none_votes=waits.count("none"), short_votes=waits.count("short"),
                                   long_votes=waits.count("long"), computed_at=stamp))
        written += 1
    db.commit()
    return written


def office_hours(db: Session, course_key: str) -> list[Slot]:
    """Return a course's office-hour slots at the floor, by weekday then hour.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".

    Returns:
        The slots; empty when none has reached the floor.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_office_hours(:k)"), {"k": course_key}).all()
        return [Slot(*row) for row in rows]
    rows = (
        db.query(OfficeHourSlotModel)
        .filter(OfficeHourSlotModel.course_key == course_key, OfficeHourSlotModel.people >= COHORT_FLOOR)
        .order_by(OfficeHourSlotModel.weekday, OfficeHourSlotModel.hour)
        .all()
    )
    return [Slot(r.weekday, r.hour, r.people, r.none_votes, r.short_votes, r.long_votes) for r in rows]


#: Company-form words dropped from the end of an employer's name.
_EMPLOYER_SUFFIX = re.compile(r"( (inc|ltd|llc|corp|corporation|co|company|limited))+$")
#: An offer is verified by an own job within this fraction of its pay.
OWN_JOB_TOLERANCE = 0.05
#: Offers within this fraction of each other agree.
AGREEMENT_TOLERANCE = 0.10


def employer_key(name: str | None) -> str:
    """Return an employer's name normalised, so "Shopify Inc." and "shopify" match.

    The twin of the SQL `account_employer_key`.

    Args:
        name: The name as typed.

    Returns:
        Lower case, "&" as "and", other punctuation as spaces, single spaces, and a
        trailing company form (Inc, Ltd, Corp ...) dropped; "" for no name.
    """
    text_ = (name or "").lower().replace("&", " and ")
    text_ = re.sub(r"[^a-z0-9 ]", " ", text_)
    text_ = re.sub(r" +", " ", text_).strip()
    return _EMPLOYER_SUFFIX.sub("", text_)


def hourly_equivalent(amount: float, period: str) -> float:
    """Return an offer's pay per hour: monthly as 12 months, yearly over 2080 hours.

    Args:
        amount: The offer in dollars.
        period: "hourly", "monthly" or "yearly".

    Returns:
        Dollars per hour.
    """
    if period == "hourly":
        return amount
    if period == "monthly":
        return amount * 12 / WORK_HOURS_PER_YEAR
    return amount / WORK_HOURS_PER_YEAR


def percentile(values: list[float], fraction: float) -> float:
    """Return a percentile by linear interpolation, as Postgres's percentile_cont does.

    Args:
        values: At least one value.
        fraction: 0 to 1.

    Returns:
        The value `fraction` of the way through the sorted values.
    """
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass(frozen=True)
class SalaryFigure:
    """Typical hourly pay at one employer, from verified shared offers.

    Attributes:
        employer: The name as most people wrote it.
        people: Offers counted, a multiple of 5.
        median: Median dollars per hour.
        p25: Bottom of the middle half.
        p75: Top of the middle half.
    """
    employer: str
    people: int
    median: float
    p25: float
    p75: float


def recount_salaries(db: Session) -> int:
    """Rebuild the salary figures from scratch from every shared offer.

    Each person's latest shared offer per employer, live accounts only, read from the
    application now. An offer counts only once verified (an own hourly job there
    within 5%, or 5 people's offers within 10% of it), and only whole batches of 5
    verified offers, oldest share first.

    Args:
        db: Open session; needs no acting user.

    Returns:
        The number of employer rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_salaries()")).scalar()
        db.commit()
        return int(written or 0)
    db.query(SalaryFigureModel).delete(synchronize_session=False)
    rows = (
        db.query(SalaryShareModel, JobApplicationModel)
        .join(JobApplicationModel, (JobApplicationModel.id == SalaryShareModel.application_id)
              & (JobApplicationModel.user_id == SalaryShareModel.user_id))
        .join(UserModel, UserModel.id == SalaryShareModel.user_id)
        .filter(UserModel.deleted_at.is_(None), JobApplicationModel.offer_amount > 0,
                JobApplicationModel.offer_period.isnot(None))
        .all()
    )
    latest: dict[tuple, tuple] = {}
    for share, application in rows:
        key = employer_key(application.company)
        if not key:
            continue
        found = latest.get((share.user_id, key))
        if found is None or share.shared_at > found[0].shared_at:
            latest[(share.user_id, key)] = (share, application)
    shared = [
        {"user_id": user_id, "key": key, "employer": application.company.strip(), "shared_at": share.shared_at,
         "hourly": hourly_equivalent(application.offer_amount, application.offer_period)}
        for (user_id, key), (share, application) in latest.items()
    ]
    by_employer: dict[str, list[dict]] = defaultdict(list)
    for offer in shared:
        by_employer[offer["key"]].append(offer)
    written = 0
    now = utc_now()
    for key, offers in by_employer.items():
        verified = []
        for offer in offers:
            agreeing = sum(1 for other in offers
                           if abs(other["hourly"] - offer["hourly"]) <= AGREEMENT_TOLERANCE * offer["hourly"])
            if agreeing >= COHORT_FLOOR or _own_job_matches(db, offer):
                verified.append(offer)
        verified.sort(key=lambda o: (o["shared_at"], o["hourly"]))
        batch = verified[: len(verified) // COHORT_FLOOR * COHORT_FLOOR]
        if len(batch) < COHORT_FLOOR:
            continue
        hourly = [o["hourly"] for o in batch]
        names = Counter(o["employer"] for o in batch)
        most = max(names.values())
        db.add(SalaryFigureModel(
            employer_key=key, employer=min(name for name, n in names.items() if n == most), people=len(batch),
            median=percentile(hourly, 0.5), p25=percentile(hourly, 0.25), p75=percentile(hourly, 0.75),
            computed_at=now,
        ))
        written += 1
    db.commit()
    return written


def _own_job_matches(db: Session, offer: dict) -> bool:
    """Return whether the offer's owner has an hourly job there paying within 5% of it."""
    for job in db.query(JobModel).filter(JobModel.user_id == offer["user_id"], JobModel.kind == "hourly"):
        if (employer_key(job.employer) == offer["key"] and job.hourly_rate is not None
                and abs(job.hourly_rate - offer["hourly"]) <= OWN_JOB_TOLERANCE * offer["hourly"]):
            return True
    return False


def salary_figures(db: Session) -> list[SalaryFigure]:
    """Return every employer's salary figures at the floor, by name.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.

    Returns:
        The figures; empty while no employer has reached the floor.
    """
    if _is_postgres(db):
        return [SalaryFigure(*row) for row in db.execute(text("SELECT * FROM account_salary_figures()")).all()]
    rows = db.query(SalaryFigureModel).filter(SalaryFigureModel.people >= COHORT_FLOOR).all()
    return [SalaryFigure(r.employer, r.people, r.median, r.p25, r.p75)
            for r in sorted(rows, key=lambda r: r.employer.lower())]


#: Words that make a description a transfer or a payment, never a merchant.
NOT_MERCHANTS = re.compile(
    r"\b(transfer|etransfer|interac|payment|deposit|withdrawal|atm|cheque|refund|payroll|paypal|venmo)\b")
#: A person's vote for a merchant is the category holding this share of their
#: expenses there (categorize_service.MAP_AGREEMENT; a test holds them together).
PERSONAL_AGREEMENT = 0.8
#: A merchant is shared only when its category holds this share of the votes.
SHARED_AGREEMENT = 0.75


def recount_merchant_categories(db: Session) -> int:
    """Rebuild the shared merchant map from scratch from everyone's categorised expenses.

    One vote per person per merchant: the unarchived category name holding 80% of
    their expenses there, from live accounts that haven't switched sharing off.
    Transfers and payments are never merchants, nor keys under 3 letters. A merchant
    is written at `MERCHANT_FLOOR` people holding 75% of the votes.

    Args:
        db: Open session; needs no acting user.

    Returns:
        The number of merchant rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_merchant_categories()")).scalar()
        db.commit()
        return int(written or 0)
    # The normaliser lives with the forecast, which every other reader uses;
    # imported here, not above, to keep this module free of service imports.
    from app.Finances.services.forecast_service import merchant_key

    db.query(MerchantCategoryModel).delete(synchronize_session=False)
    rows = (
        db.query(TransactionModel.user_id, TransactionModel.description, SpendCategoryModel.name, UserModel.preferences)
        .join(SpendCategoryModel, (SpendCategoryModel.id == TransactionModel.category_id)
              & (SpendCategoryModel.user_id == TransactionModel.user_id))
        .join(UserModel, UserModel.id == TransactionModel.user_id)
        .filter(TransactionModel.kind == "expense", SpendCategoryModel.archived.is_(False),
                UserModel.deleted_at.is_(None))
        .all()
    )
    chosen: dict[tuple, Counter] = defaultdict(Counter)
    for user_id, description, category, preferences in rows:
        if (preferences or {}).get("share_merchant_categories") is False:
            continue
        key = merchant_key(description)
        if len(key) < 3 or NOT_MERCHANTS.search(key):
            continue
        chosen[(user_id, key)][category.lower()] += 1
    votes: dict[str, Counter] = defaultdict(Counter)
    for (_, key), counts in chosen.items():
        top = max(counts.values())
        name = min(name for name, n in counts.items() if n == top)
        if top >= PERSONAL_AGREEMENT * sum(counts.values()):
            votes[key][name] += 1
    written = 0
    now = utc_now()
    for key, tally in votes.items():
        voters = sum(tally.values())
        for name, people in tally.items():
            if people >= MERCHANT_FLOOR and people >= SHARED_AGREEMENT * voters:
                db.add(MerchantCategoryModel(merchant_key=key, category_name=name, people=people, computed_at=now))
                written += 1
    db.commit()
    return written


def merchant_categories(db: Session, keys: list[str]) -> dict[str, str]:
    """Return the agreed category name for each merchant key asked about, at the floor.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        keys: Merchant keys, as `forecast_service.merchant_key` gives them.

    Returns:
        Merchant key to lower-case category name, for the keys the map holds.
    """
    wanted = sorted({key for key in keys if key})
    if not wanted:
        return {}
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_merchant_categories(:keys)"), {"keys": wanted}).all()
        return {row.merchant_key: row.category_name for row in rows}
    rows = (
        db.query(MerchantCategoryModel)
        .filter(MerchantCategoryModel.merchant_key.in_(wanted), MerchantCategoryModel.people >= MERCHANT_FLOOR)
        .all()
    )
    return {row.merchant_key: row.category_name for row in rows}


@dataclass(frozen=True)
class BoardTeam:
    """A listed team on this week's campus board.

    Attributes:
        week_start: The week's Monday (UTC).
        team_name: The team's name.
        sport: Its sport, or None.
        points: Its opted-in players' points that week.
    """
    week_start: date
    team_name: str
    sport: str | None
    points: int


def recount_campus_board(db: Session, today: date | None = None) -> int:
    """Rebuild this week's campus board: listed teams by opted-in players' points.

    Nothing is written until `DIRECTORY_FLOOR` teams with live captains are listed.

    Args:
        db: Open session; needs no acting user.
        today: The day whose Monday-to-Sunday week to count, on SQLite only; None means
            today in UTC.

    Returns:
        The number of team rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_campus_board()")).scalar()
        db.commit()
        return int(written or 0)
    today = today or _utc_today()
    week = today - timedelta(days=today.weekday())
    db.query(CampusBoardModel).delete(synchronize_session=False)
    listed = []
    for team in db.query(TeamModel).filter(TeamModel.listed.is_(True)):
        captain = db.get(UserModel, team.user_id)
        if captain is not None and captain.deleted_at is None:
            listed.append(team)
    if len(listed) < DIRECTORY_FLOOR:
        db.commit()
        return 0
    now = utc_now()
    for team in listed:
        people = {team.user_id} | {m.member_id for m in db.query(TeamMemberModel).filter_by(team_id=team.id)}
        points = 0
        for person in people:
            user = db.get(UserModel, person)
            opted = user is not None and (user.preferences or {}).get("leaderboard_opt_in") is True
            if not opted or user.deleted_at is not None:
                continue
            points += sum(a.points for a in db.query(ActivityModel).filter(
                ActivityModel.user_id == person, ActivityModel.on_date >= week,
                ActivityModel.on_date <= week + timedelta(days=6)))
        db.add(CampusBoardModel(week_start=week, team_name=team.name, sport=team.sport, points=points,
                                computed_at=now))
    db.commit()
    return len(listed)


def campus_board(db: Session) -> list[BoardTeam]:
    """Return the campus board, only once it holds `DIRECTORY_FLOOR` teams.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.

    Returns:
        Teams by points, most first; empty below the floor.
    """
    if _is_postgres(db):
        return [BoardTeam(*row) for row in db.execute(text("SELECT * FROM account_campus_board()")).all()]
    rows = db.query(CampusBoardModel).all()
    if len(rows) < DIRECTORY_FLOOR:
        return []
    return [BoardTeam(r.week_start, r.team_name, r.sport, r.points)
            for r in sorted(rows, key=lambda r: (-r.points, r.team_name))]
