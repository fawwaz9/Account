"""The in-app question: asked once, of people with an opinion (Phase 1 item 13)."""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import SurveyResponseModel, UsageEventModel
from app.Auth.dependencies import get_current_user
from app.Survey.schemas.survey import Answer, Question
from app.Survey.services.survey_service import ELIGIBLE_DAYS, AlreadyAnswered, pending, respond


def use_on(db, user, days, module="tasks"):
    start = datetime.date(2026, 9, 1)
    for n in range(days):
        db.add(UsageEventModel(id=uuid.uuid4(), user_id=user.id, day=start + datetime.timedelta(days=n),
                               kind="visit", module=module))
    db.commit()


def test_not_asked_before_a_week_of_use(db, user):
    use_on(db, user, ELIGIBLE_DAYS - 1)
    assert pending(db, user.id) is None


def test_asked_after_a_week_of_use(db, user):
    use_on(db, user, ELIGIBLE_DAYS)
    assert pending(db, user.id) == Question.DISAPPOINTMENT


def test_days_not_rows_count(db, user):
    """Seven visits on one day is one day of use, not a week."""
    day = datetime.date(2026, 9, 1)
    for module in ("tasks", "grades", "budget", "jobs", "calendar", "settings", "dashboard"):
        db.add(UsageEventModel(id=uuid.uuid4(), user_id=user.id, day=day, kind="visit", module=module))
    db.commit()
    assert pending(db, user.id) is None


def test_an_answer_is_final(db, user):
    use_on(db, user, ELIGIBLE_DAYS)
    respond(db, user.id, Question.DISAPPOINTMENT, Answer.VERY)
    assert pending(db, user.id) is None
    with pytest.raises(AlreadyAnswered):
        respond(db, user.id, Question.DISAPPOINTMENT, Answer.NOT)
    [row] = db.query(SurveyResponseModel).filter(SurveyResponseModel.user_id == user.id).all()
    assert row.answer == "very"


def test_dont_ask_again_is_an_answer(db, user):
    use_on(db, user, ELIGIBLE_DAYS)
    respond(db, user.id, Question.DISAPPOINTMENT, Answer.DISMISSED)
    assert pending(db, user.id) is None


def test_another_users_use_and_answers_change_nothing(db, user):
    from tests.conftest import make_user

    other = make_user(db, "other@example.com")
    use_on(db, other, ELIGIBLE_DAYS)
    respond(db, other.id, Question.DISAPPOINTMENT, Answer.VERY)
    assert pending(db, user.id) is None          # their week of use is not mine
    use_on(db, user, ELIGIBLE_DAYS)
    assert pending(db, user.id) == Question.DISAPPOINTMENT  # their answer is not mine


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, client):
    assert client.get(f"/api/survey/{user.id}/pending").json() == {"question": None}
    use_on(db, user, ELIGIBLE_DAYS)
    assert client.get(f"/api/survey/{user.id}/pending").json() == {"question": "disappointment"}
    body = {"question": "disappointment", "answer": "somewhat"}
    assert client.post(f"/api/survey/{user.id}/responses", json=body).status_code == 204
    assert client.post(f"/api/survey/{user.id}/responses", json=body).status_code == 409
    assert client.post(f"/api/survey/{user.id}/responses",
                       json={"question": "disappointment", "answer": "meh"}).status_code == 422
    assert client.get(f"/api/survey/{user.id}/pending").json() == {"question": None}
