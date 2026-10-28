"""One row in every table, all belonging to one user.

The isolation suite needs a victim who owns *something* everywhere: a route can
only be shown not to leak a kind of row if a row of that kind exists to leak.
Built straight through the ORM rather than through the API, so the world does
not depend on the routes it is about to be used to test.

Every free-text column carries ``marker``, so "did anything of B's reach A" is a
substring check on the response, whatever shape the route returns.
"""
import hashlib
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app._database.rls import SEALED_TABLES, SHARED_READ_TABLES
from app._database.models import (
    AccountCategoryLimitModel,
    AccountCategoryMonthLimitModel,
    AccountModel,
    AccountMonthValueModel,
    Base,
    BudgetTargetModel,
    CatalogueCourseModel,
    CataloguePrerequisiteModel,
    CourseCategoryWeightModel,
    CourseModel,
    EventModel,
    InviteModel,
    GradeModel,
    JobModel,
    PaychequeDeductionModel,
    PaychequeModel,
    PartnershipModel,
    PrerequisiteProposalModel,
    RecurringTaskModel,
    RecurringTransactionModel,
    ReminderModel,
    ShiftRecordModel,
    SinkingContributionModel,
    SinkingFundModel,
    SpendCategoryModel,
    TaskModel,
    TaskSnoozeModel,
    TermBlackoutModel,
    TransactionModel,
    TuitionDeductionModel,
    PushSubscriptionModel,
    ImportModel,
    CourseEquivalenceModel,
    SavedPlanModel,
    DegreeRequirementModel,
    GradingSchemeModel,
    SurveyResponseModel,
    SyllabusParseModel,
    TuitionPaymentModel,
    UsageEventModel,
    TaskInviteModel,
    TaskMemberModel,
    UserModel,
    EventInviteModel,
    EventMemberModel,
    GradeDistributionModel,
    CourseIntelModel,
    MerchantCategoryModel,
    SalaryFigureModel,
    SalaryShareModel,
    OfficeHourCheckinModel,
    OfficeHourSlotModel,
    TermReviewModel,
    GameModel,
    JobApplicationModel,
    ApplicationSeasonModel,
    ApplicationStepModel,
    TeamInviteModel,
    TeamMemberModel,
    TeamModel,
)

from app.Intake.services import storage  # noqa: E402

BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def seed_world(db, user_id: uuid.UUID, marker: str, day: date) -> dict[str, uuid.UUID]:
    """Give ``user_id`` one row in every table. Returns ``{table name: row id}``.

    Everything happens on ``day`` -- pass the user's today. Lists default to a
    window around now (this month's transactions, this week's events), and a
    world dated anywhere else is invisible to them, so a list that leaked every
    user's rows would still pass.
    """
    WORLD_DAY = day
    WORLD_MONTH = day.replace(day=1)
    ids: dict[str, uuid.UUID] = {}

    def add(row):
        db.add(row)
        db.flush()
        ids[row.__tablename__] = row.id
        return row

    # Deterministic per marker: the same world built twice has the same ids,
    # which is what lets test_noninterference compare a database holding B's
    # world against one that does not, row for row and response for response.
    counter = iter(range(1, 1000))

    def new_id():
        return uuid.uuid5(uuid.NAMESPACE_URL, f"account-isolation-world/{marker}/{next(counter)}")

    account = add(AccountModel(
        id=new_id(), user_id=user_id, name=f"{marker} chequing", kind="spending",
        income_share=100.0, archived=False, position=0,
    ))
    savings = AccountModel(
        id=new_id(), user_id=user_id, name=f"{marker} savings", kind="savings",
        income_share=0.0, archived=False, position=1,
    )
    db.add(savings)
    db.flush()
    ids["accounts_second"] = savings.id

    category = add(SpendCategoryModel(
        id=new_id(), user_id=user_id, name=f"{marker} groceries", archived=False, position=0,
    ))
    course = add(CourseModel(
        id=new_id(), user_id=user_id, code=f"{marker.upper()}101", name=f"{marker} course",
        semester="Fall", year=3, credits=3.0, required=True, professor=f"{marker} prof",
        final_grade=0.0, average=0.0, no_final=False, transfer_credit=False, archived=False,
        links=[{"title": f"{marker} link", "url": f"https://example.com/{marker}"}],
        start_date=day - timedelta(days=14), end_date=day + timedelta(days=60),
    ))
    # The one table with an integer key, so the database assigns it.
    add(CourseCategoryWeightModel(course_id=course.id, category="Assignment", weight=100.0))
    grade = add(GradeModel(
        id=new_id(), course_id=course.id, name=f"{marker} assignment", category="Assignment",
        score=80.0, max_score=100.0, excluded=False, due_date=WORLD_DAY,
    ))
    job = add(JobModel(
        id=new_id(), user_id=user_id, name=f"{marker} job", employer=f"{marker} employer",
        kind="hourly", hourly_rate=20.0, started_on=day - timedelta(days=30), archived=False, position=0,
    ))
    add(TermBlackoutModel(
        id=new_id(), user_id=user_id, label=f"{marker} break",
        starts_on=day + timedelta(days=30), ends_on=day + timedelta(days=34),
    ))
    add(AccountCategoryLimitModel(
        id=new_id(), user_id=user_id, account_id=account.id, category_id=category.id, limit_amount=200.0,
    ))
    add(AccountCategoryMonthLimitModel(
        id=new_id(), user_id=user_id, account_id=account.id, category_id=category.id,
        month=WORLD_MONTH, limit_amount=150.0,
    ))
    add(AccountMonthValueModel(
        id=new_id(), user_id=user_id, account_id=account.id, month=WORLD_MONTH,
        difference_amount=12.5, market_value=1012.5,
    ))
    add(BudgetTargetModel(
        id=new_id(), user_id=user_id, account_id=account.id, month=WORLD_MONTH, planned_amount=300.0,
    ))
    paycheque = add(PaychequeModel(
        id=new_id(), user_id=user_id, job_id=job.id, occurred_on=WORLD_DAY, gross_amount=400.0,
        notes=f"{marker} cheque",
    ))
    add(PaychequeDeductionModel(id=new_id(), paycheque_id=paycheque.id, description=f"{marker} tax", amount=40.0))
    recurring_task = add(RecurringTaskModel(
        id=new_id(), user_id=user_id, course_id=course.id, title=f"{marker} weekly reading",
        notes=f"{marker} notes", starts_on=WORLD_DAY, recur_freq="weekly", recur_interval=1,
        recur_byday=BYDAY[day.weekday()], active=True,
    ))
    recurring_money = add(RecurringTransactionModel(
        id=new_id(), user_id=user_id, kind="expense", account_id=account.id, amount=15.0,
        description=f"{marker} subscription", category_id=category.id, starts_on=WORLD_DAY,
        recur_freq="monthly", recur_interval=1, active=True,
    ))
    add(ReminderModel(
        id=new_id(), user_id=user_id, title=f"{marker} reminder", notes=f"{marker} notes",
        remind_at=datetime.combine(day, time(9, 0), tzinfo=timezone.utc), course_id=course.id,
    ))
    fund = add(SinkingFundModel(
        id=new_id(), user_id=user_id, name=f"{marker} fund", target_amount=500.0,
        due_on=day + timedelta(days=180), from_account_id=account.id, to_account_id=savings.id, archived=False,
    ))
    add(SinkingContributionModel(id=new_id(), fund_id=fund.id, for_month=WORLD_MONTH, amount=50.0))
    event = add(EventModel(
        id=new_id(), user_id=user_id, course_id=course.id, title=f"{marker} lecture", kind="lecture",
        location=f"{marker} hall", notes=f"{marker} notes", starts_on=WORLD_DAY,
        start_time=time(10, 0), end_time=time(11, 0), recur_freq="weekly", recur_interval=1,
        recur_byday=BYDAY[day.weekday()],
    ))
    shift_event = EventModel(
        id=new_id(), user_id=user_id, job_id=job.id, title=f"{marker} shift", kind="shift",
        starts_on=WORLD_DAY, start_time=time(17, 0), end_time=time(21, 0),
    )
    db.add(shift_event)
    db.flush()
    ids["events_shift"] = shift_event.id
    # Phase 2 item 9b: a one-off personal event, the kind that can be shared --
    # the lecture above repeats, and the shift is a shift. Its own key, so
    # ids["events"] stays the lecture the walk already uses.
    personal_event = EventModel(
        id=new_id(), user_id=user_id, title=f"{marker} study group", kind="personal",
        location=f"{marker} library", notes=f"{marker} bring notes", starts_on=WORLD_DAY,
        start_time=time(14, 0), end_time=time(15, 0),
    )
    db.add(personal_event)
    db.flush()
    ids["events_personal"] = personal_event.id
    task = add(TaskModel(
        id=new_id(), user_id=user_id, course_id=course.id, grade_id=grade.id, title=f"{marker} task",
        notes=f"{marker} notes", due_date=WORLD_DAY, done=False, archived=False,
    ))
    transaction = add(TransactionModel(
        # Signed as the app stores it: an expense is negative. Stored positive,
        # it was invisible to every sum of spending, so a summary that leaked
        # every user's transactions still added up the same.
        id=new_id(), user_id=user_id, account_id=account.id, kind="expense", amount=-25.0,
        description=f"{marker} coffee", occurred_on=WORLD_DAY, category_id=category.id,
        # Not linked to the recurring rule: a linked row reads as today's
        # occurrence already written, so the rule was never due, and a "run the
        # due rules" that reached another user's rules had nothing to show.
    ))
    add(ShiftRecordModel(
        id=new_id(), user_id=user_id, event_id=shift_event.id, job_id=job.id, on_date=WORLD_DAY,
        confirmed=True, tip_amount=10.0, tip_is_cash=True, notes=f"{marker} shift notes",
    ))
    add(TaskSnoozeModel(id=new_id(), task_id=task.id, until=day + timedelta(days=6), reason=f"{marker} reason"))
    tuition_txn = TransactionModel(
        id=new_id(), user_id=user_id, account_id=account.id, kind="expense", amount=-3000.0,
        description=f"{marker} tuition", occurred_on=WORLD_DAY, course_id=course.id,
    )
    db.add(tuition_txn)
    db.flush()
    ids["transactions_tuition"] = tuition_txn.id
    payment = add(TuitionPaymentModel(
        id=new_id(), user_id=user_id, transaction_id=tuition_txn.id, school_year=3, semester="Fall",
        cost_per_credit=1000.0, fees=0.0, credits_counted=3.0, occurred_on=WORLD_DAY,
    ))
    add(TuitionDeductionModel(
        id=new_id(), tuition_payment_id=payment.id, description=f"{marker} bursary", amount=100.0,
    ))
    add(UsageEventModel(id=new_id(), user_id=user_id, day=WORLD_DAY, kind="visit", module="grades"))
    add(PushSubscriptionModel(
        id=new_id(), user_id=user_id, endpoint=f"https://push.invalid/{marker}/device",
        # A real P-256 point (RFC 8291's example), so it can be encrypted to.
        p256dh="BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
        auth="BTBZMqHH6r4Tts7J_aSIgg",
    ))
    # A CSV import with one row of its own, so undoing someone else's import
    # has something of theirs to wrongly remove. Added directly, not through
    # add(), which would overwrite the world's one "transactions" id.
    imported = add(ImportModel(id=new_id(), user_id=user_id, account_id=account.id,
                               filename=f"{marker}.csv", row_count=1))
    imported_row = TransactionModel(
        id=new_id(), user_id=user_id, account_id=account.id, kind="expense", amount=-4.5,
        description=f"{marker} imported coffee", occurred_on=WORLD_DAY, import_id=imported.id,
    )
    db.add(imported_row)
    ids["transactions_imported"] = imported_row.id
    # An alternative scheme on the world's course, so reading or editing
    # someone else's is something to refuse.
    add(GradingSchemeModel(id=new_id(), course_id=course.id, label=f"{marker} scheme",
                           components=[{"category": "Final", "weight": 100.0, "drop_lowest": 0,
                                        "replace_with": None}]))
    # An unapplied parse, so applying someone else's is an attempt to build a
    # course from their syllabus.
    # Behind the world's course, with its file kept in the suite's fake bucket
    # and the marker inside it, so a download that served the wrong person's
    # file would carry the other world's marker into the response.
    parse = add(SyllabusParseModel(id=new_id(), user_id=user_id, course_id=course.id, filename=f"{marker}.pdf",
                                   provider="openai", model="suite-model", media_type="application/pdf",
                                   file_kept=True, result={"course_code": f"{marker[:8]} 1",
                                                           "course_name": f"{marker} syllabus",
                                                           "assessments": []}))
    # Deleted first: test_noninterference builds the same world, same ids,
    # twice in one run, and storage.put rightly refuses to overwrite.
    storage.delete(parse.object_name)
    storage.put(parse.object_name, f"%PDF-1.4 {marker} syllabus".encode(), "application/pdf")
    # Degree audit (Phase 1 D31): a requirement the world's course meets, and
    # a mapping from it, so the audit's read reaches both tables.
    add(DegreeRequirementModel(id=new_id(), user_id=user_id, name=f"{marker} requirement", kind="credits",
                               items=["CPSC"], credits_needed=3.0, shares=False, position=0))
    add(CourseEquivalenceModel(id=new_id(), user_id=user_id, from_codes=[course.code],
                               counts_as=["CPSC 110"], note=f"{marker} mapping"))
    # A question of the world's own, so the real one is still unanswered and
    # A's request to answer it reaches the write path instead of a 409.
    add(SurveyResponseModel(id=new_id(), user_id=user_id, question=f"{marker} question", answer="very"))
    # A saved year plan (Phase 1 D37) with a month already finished, so the
    # review reads it -- and with the marker in a field the review never shows,
    # so a leak would be found by its number instead.
    add(SavedPlanModel(id=new_id(), user_id=user_id, saved_on=day - timedelta(days=90),
                       starts_on=day - timedelta(days=90), ends_on=day + timedelta(days=200),
                       starting_balance=4242.42,
                       months=[{"month": (day - timedelta(days=60)).replace(day=1).isoformat(),
                                "money_in": 4242.42, "money_out": 4242.42, "end_balance": 4242.42}]))
    # Phase 2 item 10: an open invite of this user's, whose token is
    # "<marker> invite token" -- so the walk can preview and accept A's own.
    add(InviteModel(id=new_id(), user_id=user_id, kind="partner",
                    token_hash=hashlib.sha256(f"{marker} invite token".encode()).hexdigest(),
                    expires_at=datetime.combine(day + timedelta(days=5), time(12, 0))))
    # Phase 2 item 9a: a live link on the world's task, whose token is
    # "<marker> task invite token" -- so the walk can preview and accept A's own.
    add(TaskInviteModel(id=new_id(), task_id=task.id,
                        token_hash=hashlib.sha256(f"{marker} task invite token".encode()).hexdigest(),
                        expires_at=datetime.combine(day + timedelta(days=5), time(12, 0))))
    # Phase 2 item 9b: a live link on the world's personal event, token
    # "<marker> event invite token".
    add(EventInviteModel(id=new_id(), event_id=personal_event.id,
                         token_hash=hashlib.sha256(f"{marker} event invite token".encode()).hexdigest(),
                         expires_at=datetime.combine(day + timedelta(days=5), time(12, 0))))
    # Phase 2 item 13: an end-of-term review of the world's course, opted in to
    # the grade count, with the marker in the snapshot key a leak would carry.
    add(TermReviewModel(id=new_id(), user_id=user_id, course_id=course.id, course_key=f"{marker} key",
                        term_code="2025W1", hours_per_week=9, difficulty=4, clarity=2, would_take_again=False,
                        contribute_grade=True))
    # Phase 2 item 11: a team this user captains, a game they recorded on it
    # (unconfirmed, so correcting and deleting it reach the write), and a live
    # link whose token is "<marker> team invite token".
    team = add(TeamModel(id=new_id(), user_id=user_id, name=f"{marker} team", sport=f"{marker} ultimate"))
    add(GameModel(id=new_id(), team_id=team.id, played_on=WORLD_DAY, opponent=f"{marker} opponent",
                  our_score=7, their_score=5, recorded_by=user_id, recorded_by_name=f"{marker} recorder"))
    add(TeamInviteModel(id=new_id(), team_id=team.id,
                        token_hash=hashlib.sha256(f"{marker} team invite token".encode()).hexdigest(),
                        expires_at=datetime.combine(day + timedelta(days=5), time(12, 0))))
    # Phase 2 item 4: an own prerequisite rule on the world's course, with the
    # marker in the private syllabus sentence a leak would carry.
    add(PrerequisiteProposalModel(id=new_id(), user_id=user_id, course_id=course.id, kind="prerequisite",
                                  rule={"course": "CPSC 110"}, note=f"{marker} note", source="syllabus",
                                  source_text=f"{marker} syllabus sentence", session="2026W"))
    # Phase 3 item 1: an application at interview, with the marker in the notes
    # and the private offer figure a leak would carry, and a second step.
    application = add(JobApplicationModel(
        id=new_id(), user_id=user_id, company=f"{marker} company", role=f"{marker} role", applied_on=WORLD_DAY,
        source=f"{marker} source", notes=f"{marker} application notes", status="interview",
        deadline=WORLD_DAY, follow_up_on=WORLD_DAY, offer_amount=31.5, offer_period="hourly"))
    first_step = add(ApplicationStepModel(id=new_id(), application_id=application.id, status="applied",
                                          on_date=WORLD_DAY))
    # Its own key, so the interview step below stays "application_steps" (the
    # one a path names) and this row still counts as this user's.
    ids["application_steps_applied"] = first_step.id
    add(ApplicationStepModel(id=new_id(), application_id=application.id, status="interview", on_date=WORLD_DAY,
                             note=f"{marker} step note"))
    # Phase 3 item 12: the application's offer pay, shared.
    add(SalaryShareModel(id=new_id(), user_id=user_id, application_id=application.id))
    # Phase 3 D7: a season covering the world's month, named with the marker.
    add(ApplicationSeasonModel(id=new_id(), user_id=user_id, name=f"{marker} season",
                               starts_month=WORLD_MONTH, ends_month=WORLD_MONTH))
    # Phase 3 item 11: a check-in at the world's course's office hours, with the
    # marker in the snapshot key a leak would carry.
    add(OfficeHourCheckinModel(id=new_id(), user_id=user_id, course_id=course.id, course_key=f"{marker} key",
                               weekday=day.weekday(), hour=14, wait="long",
                               checked_at=datetime.combine(day, time(21, 0))))
    _ = (event, transaction, recurring_task)

    db.commit()

    missing = ({t.name for t in Base.metadata.sorted_tables} - set(ids) - {"users"} - SHARED_READ_TABLES
               - SEALED_TABLES - PAIRED_TABLES)
    assert not missing, f"the world has nothing in: {sorted(missing)}"
    return ids


#: Tables whose rows need two people, seeded by seed_pair rather than by one
#: user's world (Phase 2 items 10, 9a, 9b and 11).
PAIRED_TABLES = frozenset({"partnerships", "task_members", "event_members", "team_members"})


def seed_pair(db, a_id, b_id, mark_a: str, mark_b: str) -> tuple[dict, dict]:
    """A partnership between A and B: one row each, as the accept function
    writes them. Each row's partner_name carries its owner's marker, because
    that is the one field the other person must never be shown -- what they
    may see of each other is the figure, through the definer function.

    Returns (A's ids, B's ids), to merge into each world.
    """
    a_row = PartnershipModel(id=uuid.uuid4(), user_id=a_id, partner_id=b_id, partner_name=f"{mark_a} partner",
                             week_percent=50.0, streak_weeks=1, figure_on=date(2026, 9, 14))
    b_row = PartnershipModel(id=uuid.uuid4(), user_id=b_id, partner_id=a_id, partner_name=f"{mark_b} partner",
                             week_percent=75.0, streak_weeks=2, figure_on=date(2026, 9, 14))
    db.add_all([a_row, b_row])
    # Shared tasks (Phase 2 item 9a), one way only. A has shared A's task with
    # B, so B's membership is a row of A's -- under A's task -- and in the walk
    # (A attacking B) A holds no rights over anything of B's. B's own task is
    # shared with a third person, so B too has a membership row for A to fail
    # to reach. Names carry each row owner's marker, as partner_name does.
    a_task = db.query(TaskModel).filter_by(user_id=a_id, title=f"{mark_a} task").one()
    b_task = db.query(TaskModel).filter_by(user_id=b_id, title=f"{mark_b} task").one()
    third = UserModel(id=uuid.uuid5(uuid.NAMESPACE_URL, f"account-isolation-world/{mark_b}/third"),
                      name="third member", email=f"{mark_b}-third@example.com", google_id=f"g-{mark_b}-third",
                      email_verified=True)
    db.add(third)
    db.flush()
    a_member = TaskMemberModel(id=uuid.uuid4(), task_id=a_task.id, member_id=b_id,
                               member_name=f"{mark_a} member", owner_name=f"{mark_a} owner")
    b_member = TaskMemberModel(id=uuid.uuid4(), task_id=b_task.id, member_id=third.id,
                               member_name=f"{mark_b} member", owner_name=f"{mark_b} owner")
    db.add_all([a_member, b_member])
    # Shared events (Phase 2 item 9b), the same way round: A's study group has
    # B on it, and B's has the third person.
    a_event = db.query(EventModel).filter_by(user_id=a_id, title=f"{mark_a} study group").one()
    b_event = db.query(EventModel).filter_by(user_id=b_id, title=f"{mark_b} study group").one()
    a_attendee = EventMemberModel(id=uuid.uuid4(), event_id=a_event.id, member_id=b_id,
                                  member_name=f"{mark_a} attendee", owner_name=f"{mark_a} owner")
    b_attendee = EventMemberModel(id=uuid.uuid4(), event_id=b_event.id, member_id=third.id,
                                  member_name=f"{mark_b} attendee", owner_name=f"{mark_b} owner")
    db.add_all([a_attendee, b_attendee])
    # Teams (Phase 2 item 11), the same way round: B plays on A's team, and the
    # third person on B's.
    a_team = db.query(TeamModel).filter_by(user_id=a_id, name=f"{mark_a} team").one()
    b_team = db.query(TeamModel).filter_by(user_id=b_id, name=f"{mark_b} team").one()
    a_player = TeamMemberModel(id=uuid.uuid4(), team_id=a_team.id, member_id=b_id,
                               member_name=f"{mark_a} player", owner_name=f"{mark_a} owner")
    b_player = TeamMemberModel(id=uuid.uuid4(), team_id=b_team.id, member_id=third.id,
                               member_name=f"{mark_b} player", owner_name=f"{mark_b} owner")
    db.add_all([a_player, b_player])
    db.flush()
    ids = ({"partnerships": a_row.id, "task_members": a_member.id, "event_members": a_attendee.id,
            "team_members": a_player.id},
           {"partnerships": b_row.id, "task_members": b_member.id, "event_members": b_attendee.id,
            "team_members": b_player.id})
    db.commit()
    return ids


#: Fixed, so two databases built for the same case hold the same shared rows
#: (the non-interference walk), and so the walk can name one in a body.
CATALOGUE_IDS = {
    "catalogue_courses": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/catalogue_courses"),
    "catalogue_prerequisites": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/catalogue_prerequisites"),
    "grade_distributions": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/grade_distributions"),
    "course_intel": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/course_intel"),
    "office_hour_slots": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/office_hour_slots"),
    "salary_figures": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/salary_figures"),
    "merchant_categories": uuid.uuid5(uuid.NAMESPACE_URL, "account-test/merchant_categories"),
}


def seed_catalogue(db) -> dict[str, uuid.UUID]:
    """One row in every shared table, and in every sealed one, belonging to
    nobody (Phase 2 items 1 and 13).

    Not part of a user's world: shared rows have no owner, so they are seeded
    once beside both worlds. Present so a route that changed or deleted one is
    caught, and so a read of them is a read of something.
    """
    course = CatalogueCourseModel(id=CATALOGUE_IDS["catalogue_courses"], campus="UBCV", subject="CPSC", number="221",
                                  title="Basic Algorithms and Data Structures", credits=4.0)
    db.add(course)
    db.flush()
    rule = CataloguePrerequisiteModel(id=CATALOGUE_IDS["catalogue_prerequisites"], catalogue_course_id=course.id,
                                      kind="prerequisite", session="2026W",
                                      rule={"all": [{"course": "UBCV CPSC 210"}]},
                                      source="reviewed-proposal")
    db.add(rule)
    # Phase 2 item 13: one row in the sealed table too -- nobody's, like the
    # catalogue, and readable by no request at all -- so a route that changed
    # or leaked it would be caught.
    sealed = GradeDistributionModel(id=CATALOGUE_IDS["grade_distributions"], course_key="UBCV CPSC 221",
                                    term_code="2025W1", bucket=80, contributors=7)
    db.add(sealed)
    # Phase 3 item 5: what reviews say about the same course, sealed the same way.
    intel = CourseIntelModel(id=CATALOGUE_IDS["course_intel"], course_key="UBCV CPSC 221", hours_answers=6,
                             hours_median=9.0, difficulty_answers=6, difficulty_mean=3.5, clarity_answers=6,
                             clarity_mean=4.0, again_answers=6, again_share=50.0)
    db.add(intel)
    # Phase 3 item 11: a busy office-hours slot for the same course.
    slot = OfficeHourSlotModel(id=CATALOGUE_IDS["office_hour_slots"], course_key="UBCV CPSC 221", weekday=1, hour=14,
                               people=6, none_votes=1, short_votes=1, long_votes=4)
    db.add(slot)
    # Phase 3 item 12: an employer's typical pay.
    pay = SalaryFigureModel(id=CATALOGUE_IDS["salary_figures"], employer_key="shopify", employer="Shopify", people=5,
                            median=30.0, p25=28.0, p75=32.0)
    db.add(pay)
    # Phase 3 item 4: a merchant most people file as coffee.
    merchant = MerchantCategoryModel(id=CATALOGUE_IDS["merchant_categories"], merchant_key="blenz",
                                     category_name="coffee", people=3)
    db.add(merchant)
    # Read before the commit: after it, touching an attribute refreshes the row
    # and leaves a transaction open holding a lock that blocks rls.install.
    ids = {"catalogue_courses": course.id, "catalogue_prerequisites": rule.id, "grade_distributions": sealed.id,
           "course_intel": intel.id, "office_hour_slots": slot.id, "salary_figures": pay.id,
           "merchant_categories": merchant.id}
    db.commit()
    missing = (SHARED_READ_TABLES | SEALED_TABLES) - set(ids)
    assert not missing, f"the catalogue seed has nothing in: {sorted(missing)}"
    return ids


def snapshot(db) -> dict[str, dict]:
    """Every row of every table, keyed by table and primary key.

    Read through the session's connection so it sees what the routes committed,
    not what the session happens to have cached.
    """
    db.expire_all()
    out = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        out[table.name] = {row["id"]: dict(row) for row in rows}
    return out
