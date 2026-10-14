"""The job application tracker (Phase 3 item 1, D2-D5).

The history is the point (D2): each status change is a step with its date, and
replies, days to a reply and the Sankey are all read from it. "No reply" is
suggested after 30 quiet days and never set on its own (D3). An offer's pay is
private (D5); that nobody else reads it is the isolation walks' job.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main
from app._database.db import get_db
from app.Auth.services.session_service import create_access_token
from app.Jobs.schemas.application import ApplicationIn, ApplicationUpdate, OfferPeriod, SeasonIn, StepIn
from app.Jobs.services import application_service as service
from app.shared.dates import user_today


def apply(db, user, company="Shopify", role="Backend intern", days_ago=40, **over):
    today = user_today(db, user.id)
    return service.create(db, user.id, ApplicationIn(
        company=company, role=role, applied_on=today - timedelta(days=days_ago), **over))


def step(db, user, application, status, days_ago, note=None):
    today = user_today(db, user.id)
    return service.add_step(db, user.id, application.id,
                            StepIn(status=status, on_date=today - timedelta(days=days_ago), note=note))


# --- the history -------------------------------------------------------------

def test_an_application_starts_with_its_applied_step(db, user):
    made = apply(db, user)
    assert made.status == "applied"
    assert [(s.status, s.on_date) for s in made.steps] == [("applied", made.applied_on)]


def test_each_change_is_a_step_and_the_latest_is_the_status(db, user):
    made = apply(db, user)
    step(db, user, made, "screening", 35)
    step(db, user, made, "interview", 30)
    latest = step(db, user, made, "interview", 25, note="second round")
    assert latest.status == "interview"
    assert [s.status for s in latest.steps] == ["applied", "screening", "interview", "interview"]
    assert latest.steps[-1].note == "second round"


def test_a_step_entered_out_of_order_still_sorts_by_its_date(db, user):
    made = apply(db, user)
    step(db, user, made, "interview", 20)
    back = step(db, user, made, "screening", 30)
    assert [s.status for s in back.steps] == ["applied", "screening", "interview"]
    assert back.status == "interview"


def test_a_step_before_applying_is_refused(db, user):
    made = apply(db, user, days_ago=10)
    with pytest.raises(ValueError):
        step(db, user, made, "screening", 11)


def test_applied_is_only_ever_the_first_step():
    with pytest.raises(ValidationError):
        StepIn(status="applied", on_date="2026-10-01")


def test_a_mistaken_step_can_be_taken_back(db, user):
    made = apply(db, user)
    wrong = step(db, user, made, "rejected", 20)
    undone = service.delete_step(db, user.id, made.id, wrong.steps[-1].id)
    assert undone.status == "applied" and len(undone.steps) == 1


def test_the_first_step_goes_only_with_the_application(db, user):
    made = apply(db, user)
    with pytest.raises(ValueError):
        service.delete_step(db, user.id, made.id, made.steps[0].id)


def test_moving_the_applied_date_moves_the_first_step(db, user):
    made = apply(db, user, days_ago=40)
    moved = service.update(db, user.id, made.id, ApplicationUpdate(applied_on=made.applied_on - timedelta(days=5)))
    assert moved.steps[0].on_date == moved.applied_on


def test_the_applied_date_cannot_move_past_what_already_happened(db, user):
    made = apply(db, user, days_ago=40)
    step(db, user, made, "screening", 30)
    with pytest.raises(ValueError):
        service.update(db, user.id, made.id, ApplicationUpdate(applied_on=made.applied_on + timedelta(days=15)))


def test_deleting_an_application_takes_its_history(db, user):
    made = apply(db, user)
    step(db, user, made, "screening", 30)
    assert service.delete(db, user.id, made.id) is True
    assert service.list_applications(db, user.id) == []


# --- the offer's pay (D5) ----------------------------------------------------

def test_an_offer_carries_its_pay_with_both_halves(db, user):
    made = apply(db, user, offer_amount=32.5, offer_period=OfferPeriod.HOURLY)
    assert (made.offer_amount, made.offer_period) == (32.5, OfferPeriod.HOURLY)


def test_half_an_offer_is_refused_on_create_and_on_edit(db, user):
    with pytest.raises(ValidationError):
        ApplicationIn(company="A", role="B", applied_on="2026-10-01", offer_amount=30)
    made = apply(db, user)
    with pytest.raises(ValueError):
        service.update(db, user.id, made.id, ApplicationUpdate(offer_amount=30))


def test_clearing_both_halves_clears_the_offer(db, user):
    made = apply(db, user, offer_amount=60000, offer_period=OfferPeriod.YEARLY)
    cleared = service.update(db, user.id, made.id, ApplicationUpdate(offer_amount=None, offer_period=None))
    assert cleared.offer_amount is None and cleared.offer_period is None


# --- "no reply yet?" (D3) ----------------------------------------------------

def test_thirty_quiet_days_while_waiting_asks_no_reply_yet(db, user):
    assert apply(db, user, company="Quiet", days_ago=30).quiet is True
    assert apply(db, user, company="Recent", days_ago=29).quiet is False


def test_the_quiet_count_runs_from_the_latest_step(db, user):
    made = apply(db, user, days_ago=60)
    assert step(db, user, made, "interview", 10).quiet is False


def test_an_offer_or_a_closed_application_is_never_asked(db, user):
    for status in ("offer", "accepted", "rejected", "no_reply", "withdrawn"):
        made = apply(db, user, company=status, days_ago=90)
        assert step(db, user, made, status, 60).quiet is False, status


def test_nothing_changes_until_you_mark_it(db, user):
    made = apply(db, user, days_ago=90)
    assert made.quiet is True and made.status == "applied"
    marked = step(db, user, made, "no_reply", 0)
    assert marked.status == "no_reply" and marked.quiet is False


# --- the figures -------------------------------------------------------------

def test_the_figures_are_read_from_the_history(db, user):
    a = apply(db, user, company="A", days_ago=40)
    step(db, user, a, "screening", 36)          # replied in 4 days
    step(db, user, a, "interview", 30)
    step(db, user, a, "interview", 25)          # a second round
    step(db, user, a, "offer", 20)
    step(db, user, a, "accepted", 18)
    b = apply(db, user, company="B", days_ago=40)
    step(db, user, b, "rejected", 30)           # replied in 10 days
    apply(db, user, company="C", days_ago=5)    # still waiting
    d = apply(db, user, company="D", days_ago=60)
    step(db, user, d, "no_reply", 10)           # no answer

    stats = service.stats(db, user.id)
    assert stats.total == 4
    assert stats.open == 1
    assert stats.replied == 2
    assert stats.reply_rate == 0.5
    assert stats.median_days_to_reply == 7.0
    assert (stats.interviews, stats.offers, stats.accepted) == (1, 1, 1)
    assert stats.by_status == {"accepted": 1, "rejected": 1, "applied": 1, "no_reply": 1}


def test_the_sankey_follows_each_path_with_interview_rounds_as_one_stage(db, user):
    a = apply(db, user, company="A", days_ago=40)
    for status, ago in (("screening", 36), ("interview", 30), ("interview", 25), ("offer", 20), ("accepted", 18)):
        step(db, user, a, status, ago)
    b = apply(db, user, company="B", days_ago=40)
    step(db, user, b, "rejected", 30)
    apply(db, user, company="C", days_ago=5)

    flows = {(f.source, f.target): f.count for f in service.stats(db, user.id).flows}
    assert flows == {
        ("applied", "screening"): 1, ("screening", "interview"): 1, ("interview", "offer"): 1,
        ("offer", "accepted"): 1, ("applied", "rejected"): 1, ("applied", "waiting"): 1,
    }


def test_a_late_reply_undoes_no_reply_in_the_sankey(db, user):
    a = apply(db, user, days_ago=60)
    step(db, user, a, "no_reply", 20)
    step(db, user, a, "interview", 5)
    flows = {(f.source, f.target) for f in service.stats(db, user.id).flows}
    assert flows == {("applied", "interview"), ("interview", "waiting")}


def test_no_applications_reads_as_nothing_rather_than_zero_percent(db, user):
    stats = service.stats(db, user.id)
    assert stats.total == 0 and stats.reply_rate is None and stats.median_days_to_reply is None


# --- through the API ---------------------------------------------------------

def test_the_api_round_trip(db, user):
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        base = f"/api/jobs/{user.id}/applications"
        made = client.post(base, headers=headers, json={
            "company": "Shopify", "role": "Backend intern", "applied_on": "2026-09-01",
        })
        assert made.status_code == 200, made.text
        application = made.json()

        moved = client.post(f"{base}/{application['id']}/steps", headers=headers,
                            json={"status": "interview", "on_date": "2026-09-10"})
        assert moved.json()["status"] == "interview"

        # Declared above /{application_id}, so it is the figures, not an id.
        stats = client.get(f"{base}/stats", headers=headers)
        assert stats.status_code == 200 and stats.json()["interviews"] == 1

        assert client.post(f"{base}/{application['id']}/steps", headers=headers,
                           json={"status": "screening", "on_date": "2026-08-01"}).status_code == 400
        assert client.delete(f"{base}/{application['id']}", headers=headers).json() == {"deleted": True}
        assert client.get(base, headers=headers).json() == []
    finally:
        app.main.app.dependency_overrides.pop(get_db, None)


def test_an_accepted_offer_counts_as_an_offer_even_with_the_offer_step_skipped(db, user):
    """Recording "accepted" straight after the interview still means there was an offer."""
    made = apply(db, user, days_ago=40)
    step(db, user, made, "interview", 30)
    step(db, user, made, "accepted", 20)
    stats = service.stats(db, user.id)
    assert (stats.offers, stats.accepted) == (1, 1)


# --- seasons (D7) ------------------------------------------------------------

def applied_on(db, user, company, day):
    return service.create(db, user.id, ApplicationIn(company=company, role="Intern", applied_on=day))


def season(db, user, name, starts, ends):
    return service.create_season(db, user.id, SeasonIn(name=name, starts=starts, ends=ends))


def test_a_season_holds_what_was_applied_for_within_its_months_end_month_whole(db, user):
    for company, day in [("Before", date(2026, 8, 31)), ("First day", date(2026, 9, 1)),
                         ("Last day", date(2026, 12, 31)), ("After", date(2027, 1, 1))]:
        applied_on(db, user, company, day)
    fall = season(db, user, "Fall 2026 co-op", "2026-09", "2026-12")
    inside = {a.company for a in service.list_applications(db, user.id, fall.id)}
    assert inside == {"First day", "Last day"}


def test_the_figures_come_from_the_season_alone(db, user):
    early = applied_on(db, user, "Early", date(2026, 5, 10))
    step(db, user, early, "rejected", 100)
    applied_on(db, user, "Fall", date(2026, 9, 15))
    fall = season(db, user, "Fall", "2026-09", "2026-12")

    in_season = service.stats(db, user.id, fall.id)
    assert in_season.total == 1 and in_season.replied == 0
    assert {(f.source, f.target) for f in in_season.flows} == {("applied", "waiting")}
    assert service.stats(db, user.id).total == 2


def test_seasons_may_overlap(db, user):
    applied_on(db, user, "October", date(2026, 10, 5))
    winter = season(db, user, "Winter co-op", "2026-09", "2026-11")
    year = season(db, user, "All of 2026", "2026-01", "2026-12")
    for s in (winter, year):
        assert [a.company for a in service.list_applications(db, user.id, s.id)] == ["October"]


def test_a_season_across_new_year(db, user):
    applied_on(db, user, "December", date(2026, 12, 20))
    applied_on(db, user, "January", date(2027, 1, 10))
    applied_on(db, user, "February", date(2027, 2, 1))
    winter = season(db, user, "Winter", "2026-12", "2027-01")
    assert {a.company for a in service.list_applications(db, user.id, winter.id)} == {"December", "January"}


@pytest.mark.parametrize("bad", [
    dict(name="Backwards", starts="2026-12", ends="2026-09"),
    dict(name="Too long", starts="2026-01", ends="2028-01"),
    dict(name="Not a month", starts="2026-13", ends="2027-01"),
    dict(name="Not a month", starts="Sep 2026", ends="2027-01"),
    dict(name="   ", starts="2026-09", ends="2026-12"),
])
def test_a_season_that_cannot_be_is_refused(bad):
    with pytest.raises(ValidationError):
        SeasonIn(**bad)


def test_a_single_month_and_two_years_are_both_seasons():
    SeasonIn(name="One month", starts="2026-09", ends="2026-09")
    SeasonIn(name="Two years", starts="2026-01", ends="2027-12")


def test_deleting_a_season_deletes_no_application(db, user):
    applied_on(db, user, "Kept", date(2026, 10, 1))
    fall = season(db, user, "Fall", "2026-09", "2026-12")
    assert service.delete_season(db, user.id, fall.id) is True
    assert service.list_seasons(db, user.id) == []
    assert [a.company for a in service.list_applications(db, user.id)] == ["Kept"]


def test_editing_a_season_moves_what_it_holds(db, user):
    applied_on(db, user, "October", date(2026, 10, 1))
    fall = season(db, user, "Fall", "2026-11", "2026-12")
    assert service.list_applications(db, user.id, fall.id) == []
    service.update_season(db, user.id, fall.id, SeasonIn(name="Fall", starts="2026-09", ends="2026-12"))
    assert len(service.list_applications(db, user.id, fall.id)) == 1


def test_seasons_list_newest_first(db, user):
    season(db, user, "Summer", "2026-05", "2026-08")
    season(db, user, "Fall", "2026-09", "2026-12")
    assert [s.name for s in service.list_seasons(db, user.id)] == ["Fall", "Summer"]


def test_the_api_filters_by_season_and_refuses_an_unknown_one(db, user):
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        base = f"/api/jobs/{user.id}/applications"
        client.post(base, headers=headers, json={"company": "In", "role": "R", "applied_on": "2026-10-01"})
        client.post(base, headers=headers, json={"company": "Out", "role": "R", "applied_on": "2026-06-01"})
        made = client.post(f"{base}/seasons", headers=headers, json={"name": "Fall", "starts": "2026-09", "ends": "2026-12"})
        assert made.status_code == 200, made.text
        assert made.json()["starts"] == "2026-09"
        season_id = made.json()["id"]
        assert [a["company"] for a in client.get(base, headers=headers, params={"season_id": season_id}).json()] == ["In"]
        assert client.get(f"{base}/stats", headers=headers, params={"season_id": season_id}).json()["total"] == 1
        unknown = "00000000-0000-0000-0000-000000000009"
        assert client.get(base, headers=headers, params={"season_id": unknown}).status_code == 404
        assert client.get(f"{base}/stats", headers=headers, params={"season_id": unknown}).status_code == 404
    finally:
        app.main.app.dependency_overrides.pop(get_db, None)
