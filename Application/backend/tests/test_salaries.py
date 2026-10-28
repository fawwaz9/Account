"""Co-op salary transparency (Phase 3 item 12, D11, D12), on SQLite and Postgres.

The promises: an offer is shared only by its owner's choice and can be taken back;
nothing is copied, so the recount reads the offer as it stands; an offer counts only
once verified (an own job within 5%, or 5 offers agreeing within 10%); only whole
batches of 5, oldest share first; no employer below 5; one offer per person per
employer; and the SQL and Python sides agree.
"""
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main
from app._database import aggregates, recounts, rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import (
    COHORT_FLOOR, ApplicationStepModel, JobApplicationModel, JobModel, SalaryFigureModel, SalaryShareModel, utc_now,
)
from app.Auth.services.session_service import create_access_token
from app.Jobs.services import application_service as service
from conftest import TESTING_SQLITE, make_user


def offer(db, person, company="Shopify", amount=30.0, period="hourly", shared=True, ago=timedelta(0)):
    """An application at offer with its pay, shared `ago` in the past."""
    row = JobApplicationModel(id=uuid.uuid4(), user_id=person.id, company=company, role="Developer intern",
                              applied_on=date(2026, 9, 1), status="offer", offer_amount=amount, offer_period=period)
    db.add(row)
    db.flush()
    db.add(ApplicationStepModel(id=uuid.uuid4(), application_id=row.id, status="applied", on_date=date(2026, 9, 1)))
    if shared:
        db.add(SalaryShareModel(user_id=person.id, application_id=row.id, shared_at=utc_now() - ago))
    db.commit()
    return row


def person(db):
    return make_user(db, f"p-{uuid.uuid4().hex[:8]}@example.com")


def offers(db, amounts, company="Shopify", **kwargs):
    """One person per amount, each sharing an offer; the first shared longest ago."""
    people = []
    for i, amount in enumerate(amounts):
        people.append(person(db))
        offer(db, people[-1], company=company, amount=amount, ago=timedelta(days=len(amounts) - i), **kwargs)
    return people


def figures(db):
    act_as(db, make_user(db, f"reader-{uuid.uuid4().hex[:6]}@example.com").id)
    return aggregates.salary_figures(db)


# --- the rules ---------------------------------------------------------------------------

@pytest.mark.parametrize(("name", "key"), [
    ("Shopify", "shopify"), ("Shopify Inc.", "shopify"), ("  SHOPIFY,  INC ", "shopify"),
    ("Procter & Gamble Co.", "procter and gamble"), ("RBC Royal Bank", "rbc royal bank"),
    ("Acme Corp Ltd", "acme"), ("Company", "company"), ("", ""), (None, ""), ("École Ltée", "cole lt e"),
])
def test_employer_names_are_normalised(db, name, key):
    assert aggregates.employer_key(name) == key
    if not TESTING_SQLITE:
        assert db.execute(text("SELECT account_employer_key(:n)"), {"n": name}).scalar() == key, "SQL twin"


def test_pay_is_compared_per_hour():
    assert aggregates.hourly_equivalent(30.0, "hourly") == 30.0
    assert aggregates.hourly_equivalent(5200.0, "monthly") == pytest.approx(30.0)
    assert aggregates.hourly_equivalent(62400.0, "yearly") == pytest.approx(30.0)


def test_percentiles_interpolate_like_postgres():
    values = [20.0, 25.0, 30.0, 35.0, 40.0]
    assert [aggregates.percentile(values, f) for f in (0.25, 0.5, 0.75)] == [25.0, 30.0, 35.0]
    assert aggregates.percentile([10.0, 20.0], 0.5) == 15.0


def test_the_floor_and_hours_in_the_functions_are_the_models():
    body = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_recount_salaries("):]
    body = body[:body.index("$$;")]
    assert set(re.findall(r">= (\d+)", body)) == {str(COHORT_FLOOR)}
    assert "(total / 5) * 5" in body
    assert set(re.findall(r"/ (\d{4})", body)) == {"2080"}
    read = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_salary_figures("):]
    assert f"f.people >= {COHORT_FLOOR}" in read[:read.index("$$;")]


# --- sharing -------------------------------------------------------------------------------

def test_sharing_is_the_owners_choice_and_can_be_taken_back(db):
    sam = person(db)
    row = offer(db, sam, shared=False)
    act_as(db, sam.id)
    assert service.set_salary_share(db, sam.id, row.id, True).salary_shared is True
    assert service.set_salary_share(db, sam.id, row.id, True).salary_shared is True, "repeating changes nothing"
    assert db.query(SalaryShareModel).count() == 1
    assert service.set_salary_share(db, sam.id, row.id, False).salary_shared is False
    assert db.query(SalaryShareModel).count() == 0


def test_only_an_offer_with_its_pay_can_be_shared(db):
    sam = person(db)
    row = offer(db, sam, shared=False)
    row.offer_amount, row.offer_period = None, None
    db.commit()
    act_as(db, sam.id)
    with pytest.raises(ValueError):
        service.set_salary_share(db, sam.id, row.id, True)


def test_nobody_shares_someone_elses_offer(db):
    sam, alex = person(db), person(db)
    theirs = offer(db, alex, shared=False)
    act_as(db, sam.id)
    assert service.set_salary_share(db, sam.id, theirs.id, True) is None
    assert db.query(SalaryShareModel).count() == 0


def test_deleting_the_application_takes_the_share(db):
    sam = person(db)
    row = offer(db, sam)
    db.delete(row)
    db.commit()
    assert db.query(SalaryShareModel).count() == 0


# --- counting ------------------------------------------------------------------------------

def test_five_agreeing_offers_are_published(db):
    offers(db, [29.0, 29.5, 30.0, 30.5, 31.0])
    assert aggregates.recount_salaries(db) == 1
    [found] = figures(db)
    assert (found.employer, found.people, found.median, found.p25, found.p75) == ("Shopify", 5, 30.0, 29.5, 30.5)


def test_agreeing_means_within_ten_percent_of_each_offer(db):
    """28 and 31 are 3 apart, more than 10% of 28: the 28 isn't agreed with by all
    five, so only four are verified, and four is below the floor."""
    offers(db, [28.0, 29.0, 30.0, 30.5, 31.0])
    assert aggregates.recount_salaries(db) == 0


def test_below_the_floor_nothing_is_published(db):
    offers(db, [30.0] * (COHORT_FLOOR - 1))
    assert aggregates.recount_salaries(db) == 0
    assert figures(db) == []


def test_offers_that_dont_agree_and_have_no_job_behind_them_never_count(db):
    offers(db, [15.0, 22.0, 30.0, 40.0, 55.0])
    assert aggregates.recount_salaries(db) == 0


def test_an_offer_matching_your_own_job_there_is_verified(db):
    people = offers(db, [15.0, 22.0, 30.0, 40.0, 55.0])
    for who, rate in zip(people, [15.5, 21.5, 30.0, 41.0, 54.0]):
        db.add(JobModel(user_id=who.id, name="Co-op", employer="Shopify Inc.", kind="hourly", hourly_rate=rate))
    db.commit()
    assert aggregates.recount_salaries(db) == 1
    assert figures(db)[0].median == 30.0


def test_a_job_more_than_five_percent_off_verifies_nothing(db):
    people = offers(db, [15.0, 22.0, 30.0, 40.0, 55.0])
    for who, rate in zip(people, [16.0, 23.5, 32.0, 42.5, 58.0]):
        db.add(JobModel(user_id=who.id, name="Co-op", employer="Shopify", kind="hourly", hourly_rate=rate))
    db.commit()
    assert aggregates.recount_salaries(db) == 0


def test_only_whole_batches_of_five_count_oldest_share_first(db):
    """Seven agreeing offers: the five shared first are counted, so the newest two
    can't be read off any change until three more arrive."""
    offers(db, [30.0, 30.0, 30.0, 30.0, 30.0, 32.0, 32.0])
    aggregates.recount_salaries(db)
    [found] = figures(db)
    assert (found.people, found.median, found.p75) == (5, 30.0, 30.0)


def test_one_offer_per_person_per_employer_their_latest_share(db):
    repeat = person(db)
    offer(db, repeat, amount=10.0, ago=timedelta(days=30))
    offer(db, repeat, amount=30.0, ago=timedelta(days=20))
    offers(db, [30.0] * (COHORT_FLOOR - 2))
    assert aggregates.recount_salaries(db) == 0, "four people, however many offers"
    offers(db, [30.0])
    aggregates.recount_salaries(db)
    assert figures(db)[0].people == COHORT_FLOOR


def test_monthly_and_yearly_offers_count_per_hour(db):
    offers(db, [30.0, 30.0], period="hourly")
    offers(db, [5200.0, 5200.0], period="monthly")
    offers(db, [62400.0], period="yearly")
    aggregates.recount_salaries(db)
    assert figures(db)[0].median == pytest.approx(30.0)


def test_spellings_of_one_employer_count_together_under_the_commonest(db):
    for company in ("Shopify", "Shopify Inc.", "shopify", "Shopify", "Shopify"):
        offer(db, person(db), company=company)
    aggregates.recount_salaries(db)
    assert [(f.employer, f.people) for f in figures(db)] == [("Shopify", 5)]


def test_taken_back_withdrawn_pay_and_deleted_accounts_are_left_out(db):
    people = offers(db, [30.0] * COHORT_FLOOR)
    people[0].deleted_at = utc_now()
    db.commit()
    assert aggregates.recount_salaries(db) == 0
    people[0].deleted_at = None
    row = db.query(JobApplicationModel).filter(JobApplicationModel.user_id == people[1].id).one()
    row.offer_amount = None
    db.commit()
    assert aggregates.recount_salaries(db) == 0


def test_the_read_checks_the_floor_again_whatever_the_table_holds(db):
    db.add(SalaryFigureModel(employer_key="x", employer="X", people=COHORT_FLOOR - 1, median=1, p25=1, p75=1))
    db.commit()
    assert figures(db) == []


def test_the_daily_recount_runs_it(db):
    offers(db, [30.0] * COHORT_FLOOR)
    assert recounts.run_all(db)["salaries"] == 1


# --- the routes ------------------------------------------------------------------------------

def test_the_routes_share_and_list(db):
    offers(db, [30.0] * COHORT_FLOOR, company="Wealthsimple")
    aggregates.recount_salaries(db)
    sam, alex = person(db), person(db)
    mine, theirs = offer(db, sam, shared=False), offer(db, alex, shared=False)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        shared = client.put(f"/api/jobs/{sam.id}/applications/{mine.id}/salary-share", headers=headers,
                            json={"share": True})
        other = client.put(f"/api/jobs/{sam.id}/applications/{theirs.id}/salary-share", headers=headers,
                           json={"share": True})
        listed = client.get(f"/api/jobs/{sam.id}/applications/salaries", headers=headers)
    finally:
        app.main.app.dependency_overrides.clear()
    assert shared.status_code == 200 and shared.json()["salary_shared"] is True
    assert other.status_code == 404
    assert listed.json() == [{"employer": "Wealthsimple", "people": 5, "median": 30.0, "p25": 30.0, "p75": 30.0}]


def test_two_shared_offers_from_one_person_are_one_voice(db):
    """The same pay offered twice by one employer (a re-offer) is still one person."""
    repeat = person(db)
    offer(db, repeat, amount=30.0, ago=timedelta(days=30))
    offer(db, repeat, amount=30.0, ago=timedelta(days=20))
    offers(db, [30.0] * (COHORT_FLOOR - 2))
    assert aggregates.recount_salaries(db) == 0


def test_a_monthly_offer_is_twelve_months_of_a_2080_hour_year(db):
    offers(db, [5200.0] * COHORT_FLOOR, period="monthly")
    aggregates.recount_salaries(db)
    assert figures(db)[0].median == pytest.approx(30.0)
