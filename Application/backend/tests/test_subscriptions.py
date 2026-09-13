"""Finding a subscription nobody told the app about.

Most of what can go wrong here is a false positive: two unrelated charges that
happen to share a description, or a run whose amount or timing only loosely
agrees. Each guard below is mutation-tested by loosening it and confirming a
charge that should be rejected is reported instead.
"""
import datetime
import uuid

import pytest

from app._database.models import TransactionModel
from app.Finances.services.subscription_service import confirm_subscription, find_subscriptions, normalize
from tests.conftest import make_account, make_category


def charge(db, user, account, amount, on, description="Netflix", category=None, recurring_id=None):
    row = TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        kind="expense", amount=-abs(amount), description=description, occurred_on=on,
        category_id=category.id if category else None, recurring_id=recurring_id,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def account(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


def monthly_dates(start, count):
    dates = [start]
    for _ in range(count - 1):
        y, m, d = dates[-1].year, dates[-1].month, dates[-1].day
        m += 1
        if m > 12:
            m = 1
            y += 1
        dates.append(datetime.date(y, m, d))
    return dates


def test_three_monthly_charges_are_found(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on)

    found = find_subscriptions(db, user.id)

    assert len(found) == 1
    assert found[0].cadence == "monthly"
    assert found[0].median_amount == 15.99


def test_two_charges_are_not_found(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 2):
        charge(db, user, account, 15.99, on)

    assert find_subscriptions(db, user.id) == []


def test_wildly_varying_amounts_are_not_found(db, user, account):
    amounts = [10.0, 40.0, 12.0]
    for amount, on in zip(amounts, monthly_dates(datetime.date(2026, 6, 15), 3)):
        charge(db, user, account, amount, on)

    assert find_subscriptions(db, user.id) == []


def test_irregular_gaps_are_not_found(db, user, account):
    dates = [datetime.date(2026, 6, 1), datetime.date(2026, 6, 10), datetime.date(2026, 8, 20)]
    for on in dates:
        charge(db, user, account, 15.99, on)

    assert find_subscriptions(db, user.id) == []


def test_a_charge_with_a_recurring_id_is_never_reported(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on, recurring_id=uuid.uuid4())

    assert find_subscriptions(db, user.id) == []


def test_a_fortnightly_run_is_found(db, user, account):
    start = datetime.date(2026, 6, 1)
    dates = [start, start + datetime.timedelta(days=14), start + datetime.timedelta(days=28)]
    for on in dates:
        charge(db, user, account, 8.5, on, description="Spotify")

    found = find_subscriptions(db, user.id)

    assert len(found) == 1
    assert found[0].cadence == "fortnightly"


def test_a_weekly_run_is_found(db, user, account):
    start = datetime.date(2026, 6, 1)
    dates = [start + datetime.timedelta(days=7 * i) for i in range(3)]
    for on in dates:
        charge(db, user, account, 4.0, on, description="Parking")

    found = find_subscriptions(db, user.id)

    assert len(found) == 1
    assert found[0].cadence == "weekly"


def test_description_matching_ignores_case_and_trailing_reference_numbers(db, user, account):
    dates = monthly_dates(datetime.date(2026, 6, 15), 3)
    descriptions = ["NETFLIX.COM 8842119", "netflix.com #33012", "Netflix.com   551027"]
    for description, on in zip(descriptions, dates):
        charge(db, user, account, 15.99, on, description=description)

    found = find_subscriptions(db, user.id)

    assert len(found) == 1
    assert found[0].description == "Netflix.com   551027"


def test_normalize_strips_case_and_trailing_reference_numbers():
    assert normalize("NETFLIX.COM 8842119") == "netflix.com"
    assert normalize("Spotify Premium #33012") == "spotify premium"
    assert normalize(None) == ""


def test_a_charge_within_ten_percent_still_counts(db, user, account):
    amounts = [15.99, 16.5, 15.75]
    for amount, on in zip(amounts, monthly_dates(datetime.date(2026, 6, 15), 3)):
        charge(db, user, account, amount, on)

    found = find_subscriptions(db, user.id)

    assert len(found) == 1


def test_the_suggested_instruction_is_prefilled_from_the_pattern(db, user, account):
    category = make_category(db, user.id, "Subscriptions")
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on, category=category)

    found = find_subscriptions(db, user.id)[0]

    assert found.suggested.kind == "expense"
    assert found.suggested.amount == 15.99
    assert found.suggested.account_id == account.id
    assert found.suggested.category_id == category.id
    assert found.suggested.starts_on == found.next_expected_on
    assert found.suggested.recurrence.freq == "monthly"
    assert found.suggested.description == "Netflix"


def test_next_expected_on_is_one_month_after_the_last_charge(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on)

    found = find_subscriptions(db, user.id)[0]

    assert found.last_seen == datetime.date(2026, 8, 15)
    assert found.next_expected_on == datetime.date(2026, 9, 15)


def test_two_unrelated_subscriptions_are_both_reported(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on, description="Netflix")
    for on in monthly_dates(datetime.date(2026, 6, 5), 3):
        charge(db, user, account, 8.5, on, description="Spotify")

    found = find_subscriptions(db, user.id)

    assert {candidate.description for candidate in found} == {"Netflix", "Spotify"}


def test_income_and_transfers_are_never_reported(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        db.add(TransactionModel(
            id=uuid.uuid4(), user_id=user.id, account_id=account.id,
            kind="income", amount=15.99, description="Netflix", occurred_on=on,
        ))
    db.commit()

    assert find_subscriptions(db, user.id) == []


def test_unknown_user_returns_none(db):
    assert find_subscriptions(db, uuid.uuid4()) is None


def test_confirming_creates_a_standing_instruction(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on)
    found = find_subscriptions(db, user.id)[0]

    rule = confirm_subscription(
        db, user.id, [o.transaction_id for o in found.occurrences], found.suggested
    )

    assert rule is not None
    assert rule.amount == 15.99
    assert rule.starts_on == found.next_expected_on


def test_confirming_tags_the_history_so_it_is_never_found_again(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on)
    found = find_subscriptions(db, user.id)[0]

    confirm_subscription(db, user.id, [o.transaction_id for o in found.occurrences], found.suggested)

    assert find_subscriptions(db, user.id) == []


def test_the_tagged_transactions_carry_the_new_rules_id(db, user, account):
    for on in monthly_dates(datetime.date(2026, 6, 15), 3):
        charge(db, user, account, 15.99, on)
    found = find_subscriptions(db, user.id)[0]
    ids = [o.transaction_id for o in found.occurrences]

    rule = confirm_subscription(db, user.id, ids, found.suggested)

    tagged = db.query(TransactionModel).filter(TransactionModel.id.in_(ids)).all()
    assert all(row.recurring_id == rule.id for row in tagged)
