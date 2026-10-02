"""What an investment is worth, and the arithmetic that must not drift.

The feature records a **level** -- how far above or below its ledger balance a
holding sits -- and derives every figure on screen from it. The first test here is
the loss case, deliberately: a percentage that can only ever render positive is
the bug this kind of feature always ships with.
"""
from datetime import date

from app.Finances.utils.returns import latest_reading, month_gain, return_percent


def m(year: int, month: int) -> date:
    """A month key, always the first, as every month column in this app stores it."""
    return date(year, month, 1)


# ------------------------------------------------------ a holding that is down --

def test_a_holding_worth_less_than_you_put_in_reads_as_a_loss():
    """Written first, and on purpose.

    A feature that shows a return is always shipped with a percentage that cannot
    go negative -- an `abs()` somewhere, or a formatter that only knows how to
    print a plus. $9,187.60 held against $10,000 put in is down 8.1%, and it has
    to say so.
    """
    assert return_percent(-812.40, 10_000.0) == -8.1


def test_a_loss_is_the_latest_reading_too():
    """The level can go down as well as up, and the newest one still wins."""
    readings = [(m(2026, 7), 500.0), (m(2026, 8), -300.0)]

    assert latest_reading(readings) == (m(2026, 8), -300.0)


def test_a_month_in_which_the_holding_fell_reports_a_negative_gain():
    readings = [(m(2026, 7), 500.0), (m(2026, 8), 150.0)]

    assert month_gain(readings, m(2026, 8)) == -350.0


# --------------------------------------------- the readings are levels, not flows --

def test_all_time_gain_is_the_latest_reading_not_the_total_of_them():
    """The mistake that makes every figure wrong at once.

    Three readings of +100, +200, +300 describe a holding that is +300 up. Summing
    them reports +600, and the error grows with every month recorded. Mutating
    `latest_reading` to return a sum must fail here.
    """
    readings = [(m(2026, 6), 100.0), (m(2026, 7), 200.0), (m(2026, 8), 300.0)]

    assert latest_reading(readings) == (m(2026, 8), 300.0)


def test_the_order_the_readings_arrive_in_does_not_decide_the_latest():
    """It is handed rows from a query. Relying on the database's order would make
    this correct only for as long as nobody added an ORDER BY or removed one."""
    readings = [(m(2026, 8), 300.0), (m(2026, 6), 100.0), (m(2026, 7), 200.0)]

    assert latest_reading(readings) == (m(2026, 8), 300.0)


def test_no_readings_at_all_is_none_rather_than_zero():
    """An account nobody has recorded a value for has an unknown return, not a
    return of nothing. Zero would render as "flat", which is a claim."""
    assert latest_reading([]) is None


# ----------------------------------------------------------- carrying forward --

def test_a_month_with_no_reading_shows_the_last_one_taken():
    """An investment you have not checked has not lost its value."""
    readings = [(m(2026, 7), 500.0)]

    assert latest_reading(readings, on_or_before=m(2026, 9)) == (m(2026, 7), 500.0)


def test_a_reading_is_never_carried_backwards():
    """The asymmetry that keeps carry-forward honest.

    Viewing July when the only reading is September's must show nothing. A figure
    from the future is not a stale figure, it is a wrong one -- it would state
    July's position using information that did not exist until September.
    """
    readings = [(m(2026, 9), 500.0)]

    assert latest_reading(readings, on_or_before=m(2026, 7)) is None


def test_carrying_forward_stops_at_the_month_asked_for():
    """With readings either side, the one at or before the month wins -- not the
    newest overall, which is what an unfiltered max would return."""
    readings = [(m(2026, 6), 100.0), (m(2026, 7), 200.0), (m(2026, 9), 900.0)]

    assert latest_reading(readings, on_or_before=m(2026, 8)) == (m(2026, 7), 200.0)


def test_a_reading_in_the_month_asked_for_is_included():
    """`on_or_before` is inclusive. Off by one here would hide the figure in the
    very month it was recorded, which is the month anyone looks at first."""
    readings = [(m(2026, 8), 400.0)]

    assert latest_reading(readings, on_or_before=m(2026, 8)) == (m(2026, 8), 400.0)


# ----------------------------------------------------------- a month's movement --

def test_a_months_gain_is_the_difference_between_two_levels():
    readings = [(m(2026, 7), 500.0), (m(2026, 8), 625.0)]

    assert month_gain(readings, m(2026, 8)) == 125.0


def test_a_months_gain_uses_the_previous_reading_not_the_previous_calendar_month():
    """Skip a month and the gain spans the gap, which is the only honest answer --
    the movement happened, it just was not cut in two."""
    readings = [(m(2026, 5), 100.0), (m(2026, 8), 400.0)]

    assert month_gain(readings, m(2026, 8)) == 300.0


def test_a_carried_forward_month_has_no_gain_rather_than_a_gain_of_zero():
    """Carrying the level forward keeps the all-time figure honest. Reporting the
    month's movement as 0 would assert the holding was flat, which nobody
    recorded -- the difference between "unknown" and "unchanged"."""
    readings = [(m(2026, 7), 500.0)]

    assert month_gain(readings, m(2026, 9)) is None


def test_the_first_reading_ever_taken_has_no_month_gain():
    """Nothing to subtract from. Its level is the whole story and the caller shows
    that instead; subtracting from an implicit zero would report the entire gain
    to date as having happened in that one month."""
    readings = [(m(2026, 7), 500.0)]

    assert month_gain(readings, m(2026, 7)) is None


def test_a_months_gain_is_rounded_to_cents():
    readings = [(m(2026, 7), 0.1), (m(2026, 8), 0.3)]

    assert month_gain(readings, m(2026, 8)) == 0.2


# ------------------------------------------------------- the percentage guards --

def test_a_zero_balance_has_no_percentage():
    """Division by zero. An account with nothing in it and a recorded gain is
    possible -- withdraw everything after a reading -- and the dollar figure is
    still worth showing, so the caller needs None rather than an exception."""
    assert return_percent(500.0, 0.0) is None


def test_a_negative_balance_has_no_percentage():
    """The guard nobody thinks to check.

    Dividing a positive gain by a negative balance yields a negative percentage,
    so a holding that had gained would render as a loss. Refusing to answer is the
    only safe response -- the question "what percent of a negative is this" has no
    useful answer to print beside a balance.
    """
    assert return_percent(500.0, -2_000.0) is None


def test_a_percentage_is_measured_against_what_you_put_in():
    assert return_percent(543.21, 10_000.0) == 5.4


def test_adding_money_lowers_the_percentage_without_touching_the_gain():
    """Not a rounding artefact -- the truth.

    The same $500 gain against $20,000 put in is 2.5%, not 5%: you hold $20,500 on
    $20,000 of cost. The percentage falls because the money you added has not
    gained yet, and a reader checking 500/20000 against the balance printed beside
    it gets the same answer.
    """
    assert return_percent(500.0, 10_000.0) == 5.0
    assert return_percent(500.0, 20_000.0) == 2.5


def test_a_percentage_is_rounded_to_one_decimal():
    """Rounded here so the client renders rather than recomputes. Two opinions on
    the same division disagree at the boundary."""
    assert return_percent(333.0, 10_000.0) == 3.3


# ---------------------------------------------------------- through the services --

import uuid
from datetime import timedelta

import pytest

from app._database.models import AccountMonthValueModel, TransactionModel
from app.Finances.schemas.account import AccountMonthValueUpsert
from app.Finances.services.account_service import (
    clear_month_value,
    delete_account,
    get_account,
    get_accounts,
    measured_on,
    net_worth,
    set_month_value,
)
from app.Finances.services.activity_service import get_account_activity
from tests.conftest import make_account, make_user

#: A month safely in the past, so `measured_on` is its last day whenever the
#: suite happens to run. A test anchored to "this month" would measure against
#: today and quietly change behaviour on the 1st.
MARCH = date(2026, 3, 1)
APRIL = date(2026, 4, 1)
MAY = date(2026, 5, 1)


def invested(db, user, name="Investments", **overrides):
    account = make_account(db, user.id, name, kind="investment")
    for key, value in overrides.items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return account


def deposit(db, user, account, amount, on_date=date(2026, 1, 15)):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="income",
        amount=amount, description="Contribution", occurred_on=on_date,
    ))
    db.commit()


def record(db, user, account, month, **figure):
    return set_month_value(
        db, user.id, account.id, AccountMonthValueUpsert(month=month, **figure)
    )


def readings_in(db, account):
    return (
        db.query(AccountMonthValueModel)
        .filter(AccountMonthValueModel.account_id == account.id)
        .count()
    )


# --- typing what it is worth, storing the level -------------------------------

def test_typing_what_it_is_worth_stores_how_far_above_the_ledger_that_is(db, user):
    """The subtraction is the app's job. $10,543.21 held against $10,000 put in is
    a level of +$543.21, and that level is what persists."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    updated = record(db, user, account, MARCH, market_value=10_543.21)

    assert updated.investment_return.difference_amount == 543.21
    assert updated.investment_return.return_percent == 5.4
    assert updated.investment_return.market_value == 10_543.21
    assert updated.investment_return.ledger_balance == 10_000.0


def test_a_holding_worth_less_than_the_ledger_stores_a_negative_level(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    updated = record(db, user, account, MARCH, market_value=9_187.60)

    assert updated.investment_return.difference_amount == -812.40
    assert updated.investment_return.return_percent == -8.1


def test_a_recorded_level_survives_a_later_deposit(db, user):
    """Contribution-neutrality, which is the whole reason the level is stored.

    Had the market value been stored and the difference derived, the $10,000
    deposit below would make the month-end ledger $20,000 against a recorded
    $10,500 and report this gain as a $9,500 LOSS.
    """
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, market_value=10_500.0)

    deposit(db, user, account, 10_000.0, on_date=date(2026, 2, 10))

    after = get_account(db, user.id, account.id)
    assert after.investment_return.difference_amount == 500.0, "the level moved"
    # The percentage falls, and that is correct: $20,500 held on $20,000 of cost.
    assert after.investment_return.return_percent == 2.5


def test_the_difference_can_be_set_directly(db, user):
    """The path that needs no ledger lookup -- correcting an old month, or a
    restore. No market value is invented to go with it."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    updated = record(db, user, account, MARCH, difference_amount=750.0)

    assert updated.investment_return.difference_amount == 750.0
    assert updated.investment_return.market_value is None


def test_sending_both_figures_or_neither_is_refused():
    """Two answers to one question, where whichever the service preferred would
    silently discard the other."""
    for payload in ({}, {"market_value": 1.0, "difference_amount": 2.0}):
        with pytest.raises(ValueError):
            AccountMonthValueUpsert(month=MARCH, **payload)


def test_any_day_of_the_month_is_stored_as_the_first(db, user):
    """Or September is stored twenty-eight ways and no two readings ever match."""
    account = invested(db, user)
    deposit(db, user, account, 1_000.0)

    record(db, user, account, date(2026, 3, 14), market_value=1_100.0)

    stored = db.query(AccountMonthValueModel).filter(
        AccountMonthValueModel.account_id == account.id
    ).one()
    assert stored.month == MARCH


def test_recording_the_same_month_twice_corrects_it_rather_than_duplicating(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    record(db, user, account, MARCH, market_value=10_500.0)
    updated = record(db, user, account, MARCH, market_value=10_900.0)

    assert readings_in(db, account) == 1
    assert updated.investment_return.difference_amount == 900.0


def test_a_non_investment_account_is_refused(db, user):
    """Every read path gates on kind, so storing a reading here would be a write
    that silently does nothing -- the worst kind of accepted request."""
    savings = make_account(db, user.id, "Savings", kind="savings")

    with pytest.raises(ValueError, match="not an investment account"):
        record(db, user, savings, MARCH, market_value=500.0)

    assert readings_in(db, savings) == 0


def test_an_unknown_account_is_not_found_rather_than_an_error(db, user):
    assert set_month_value(
        db, user.id, uuid.uuid4(), AccountMonthValueUpsert(month=MARCH, market_value=1.0)
    ) is None


# --- what the month is measured against --------------------------------------

def test_a_past_month_is_measured_against_its_own_last_day():
    assert measured_on(MARCH, today=date(2026, 10, 2)) == date(2026, 3, 31)


def test_an_unfinished_month_is_measured_against_today():
    """You cannot measure a month against its 31st on the 14th, and reaching for
    the end of an unfinished month would count deposits that have not happened."""
    assert measured_on(date(2026, 10, 1), today=date(2026, 10, 14)) == date(2026, 10, 14)


def test_the_day_is_passed_in_rather_than_read_from_the_server_clock():
    """It used to call `date.today()`, which is UTC in production -- so between
    six in the evening and midnight in Regina a reading for the current month was
    measured against a ledger holding one more day than the student had lived.

    Passing the day is what makes that the caller's problem, and the callers
    resolve it through the timezone preference.
    """
    # The student's 1st, while UTC has already rolled to the 2nd.
    assert measured_on(date(2026, 10, 1), today=date(2026, 10, 1)) == date(2026, 10, 1)
    assert measured_on(date(2026, 10, 1), today=date(2026, 10, 2)) == date(2026, 10, 2)


def test_a_past_month_ignores_deposits_made_after_it(db, user):
    """The reason the dated balance exists at all.

    $10,000 was in by March, and $5,000 more arrived in April. Subtracting the
    all-time balance instead would make March's level `10_500 - 15_000`, i.e.
    **-$4,500**: a $500 gain recorded as a four-and-a-half-thousand dollar loss.
    """
    account = invested(db, user)
    deposit(db, user, account, 10_000.0, on_date=date(2026, 1, 15))
    deposit(db, user, account, 5_000.0, on_date=date(2026, 4, 20))

    record(db, user, account, MARCH, market_value=10_500.0)

    stored = db.query(AccountMonthValueModel).filter(
        AccountMonthValueModel.account_id == account.id
    ).one()
    assert stored.difference_amount == 500.0


def test_the_card_divides_by_the_all_time_balance_not_the_months(db, user):
    """Two denominators, deliberately, and this is the one that is easy to mix up.

    The *level* is fixed against the month it was recorded for. The *percentage on
    the card* divides by the balance standing today, because that is the number
    printed next to it and a reader doing the arithmetic has to get the same
    answer. So the same $500 level reads 5.0% in March and 3.3% once another
    $5,000 has gone in -- and 3.3% is the truth about what you now hold.
    """
    account = invested(db, user)
    deposit(db, user, account, 10_000.0, on_date=date(2026, 1, 15))
    record(db, user, account, MARCH, market_value=10_500.0)

    assert get_account(db, user.id, account.id).investment_return.return_percent == 5.0

    deposit(db, user, account, 5_000.0, on_date=date(2026, 4, 20))

    card = get_account(db, user.id, account.id)
    assert card.investment_return.ledger_balance == 15_000.0
    assert card.investment_return.difference_amount == 500.0
    assert card.investment_return.return_percent == 3.3


# --- the account card --------------------------------------------------------

def test_the_card_shows_the_latest_reading_overall(db, user):
    """Not scoped to a month, so the newest reading wins regardless of which
    month anyone was last looking at."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)
    record(db, user, account, MAY, difference_amount=300.0)

    card = get_account(db, user.id, account.id)

    assert card.investment_return.difference_amount == 300.0
    assert card.investment_return.as_of == MAY
    assert card.investment_return.is_carried_forward is False


def test_an_investment_account_with_no_readings_has_no_figure(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    assert get_account(db, user.id, account.id).investment_return is None


def test_a_spending_account_never_carries_a_figure(db, user):
    spending = make_account(db, user.id, "Chequing")

    assert get_account(db, user.id, spending.id).investment_return is None


def test_an_account_that_stops_being_an_investment_stops_reporting_a_return(db, user):
    """Its rows are deliberately kept, so the kind check is the only thing
    stopping a re-kinded account reporting a stale return."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    account.kind = "savings"
    db.commit()

    assert get_account(db, user.id, account.id).investment_return is None
    assert readings_in(db, account) == 1, "the readings should be kept, not deleted"


def test_a_zero_balance_leaves_the_dollar_figure_but_drops_the_percentage(db, user):
    """Withdraw everything after a reading and the division has no answer. The
    level is still worth showing."""
    account = invested(db, user)
    record(db, user, account, MARCH, difference_amount=500.0)

    card = get_account(db, user.id, account.id)

    assert card.investment_return.difference_amount == 500.0
    assert card.investment_return.return_percent is None


# --- the account page, month by month ----------------------------------------

def test_the_account_page_carries_a_reading_forward_and_dates_it(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    activity = get_account_activity(db, user.id, account.id, MAY)

    assert activity.investment_return.difference_amount == 500.0
    assert activity.investment_return.as_of == MARCH
    assert activity.investment_return.is_carried_forward is True


def test_the_month_a_reading_was_taken_for_is_not_flagged_as_carried(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    activity = get_account_activity(db, user.id, account.id, MARCH)

    assert activity.investment_return.is_carried_forward is False


def test_a_month_before_the_first_reading_shows_nothing(db, user):
    """No carrying backwards: February cannot be stated using March's figure."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    activity = get_account_activity(db, user.id, account.id, date(2026, 2, 1))

    assert activity.investment_return is None


def test_the_account_page_carries_the_kind_so_it_can_tell_the_pots_apart(db, user):
    """It could not before, which is why every account showed the same tiles."""
    account = invested(db, user)
    spending = make_account(db, user.id, "Chequing")

    assert get_account_activity(db, user.id, account.id, MARCH).kind == "investment"
    assert get_account_activity(db, user.id, spending.id, MARCH).kind == "spending"


def test_the_page_sends_the_months_own_ledger_balance_not_the_all_time_one(db, user):
    """What the entry form subtracts a typed market value from. Using the
    all-time balance for a past month would subtract deposits made since."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0, on_date=date(2026, 1, 15))
    deposit(db, user, account, 5_000.0, on_date=date(2026, 4, 20))

    march = get_account_activity(db, user.id, account.id, MARCH)

    assert march.balance == 15_000.0, "all-time balance"
    assert march.ledger_balance_at_month == 10_000.0, "March's balance"


def test_a_spending_account_page_computes_no_investment_figures(db, user):
    spending = make_account(db, user.id, "Chequing")
    deposit(db, user, spending, 500.0)

    activity = get_account_activity(db, user.id, spending.id, MARCH)

    assert activity.investment_return is None
    assert activity.ledger_balance_at_month == 0.0


# --- net worth ---------------------------------------------------------------

def test_net_worth_includes_the_latest_recorded_gain(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    figure = net_worth(db, user.id)

    assert figure.investment_gain == 500.0
    assert figure.net_worth == 10_500.0


def test_net_worth_takes_the_latest_gain_and_not_the_sum_of_the_readings(db, user):
    """Three readings describe a holding up $300, not up $600."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)
    record(db, user, account, APRIL, difference_amount=200.0)
    record(db, user, account, MAY, difference_amount=300.0)

    assert net_worth(db, user.id).investment_gain == 300.0


def test_a_loss_lowers_net_worth(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=-800.0)

    figure = net_worth(db, user.id)

    assert figure.investment_gain == -800.0
    assert figure.net_worth == 9_200.0


def test_an_account_excluded_from_net_worth_cannot_smuggle_its_gain_in(db, user):
    """Money someone else is holding is neither an asset nor a debt, and its gain
    is neither either."""
    account = invested(db, user, counts_toward_net_worth=False)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    figure = net_worth(db, user.id)

    assert figure.investment_gain == 0.0
    assert figure.net_worth == 0.0


def test_an_archived_accounts_gain_is_left_out(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    account.archived = True
    db.commit()

    assert net_worth(db, user.id).investment_gain == 0.0


def test_net_worth_without_any_readings_reports_no_gain(db, user):
    """The control. `investment_gain` of 0.0 has to mean nothing was recorded, not
    that the field was forgotten."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    figure = net_worth(db, user.id)

    assert figure.investment_gain == 0.0
    assert figure.net_worth == 10_000.0


# --- clearing, and the blast radius of a delete -------------------------------

def test_clearing_a_month_removes_only_that_month(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)
    record(db, user, account, APRIL, difference_amount=200.0)

    before = readings_in(db, account)
    updated = clear_month_value(db, user.id, account.id, APRIL)

    assert before == 2
    assert readings_in(db, account) == 1
    assert updated.investment_return.as_of == MARCH


def test_clearing_a_month_that_holds_nothing_is_not_an_error(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)

    assert clear_month_value(db, user.id, account.id, MARCH) is not None
    assert readings_in(db, account) == 0


def test_clearing_accepts_any_day_of_the_month(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)

    clear_month_value(db, user.id, account.id, date(2026, 3, 28))

    assert readings_in(db, account) == 0


def test_deleting_an_account_removes_its_readings_and_nobody_elses(db, user):
    """Counted before and after, both accounts.

    The readings are a foreign key, so without the explicit delete this is an
    integrity error rather than untidiness -- and a delete whose filter was
    computed rather than written once emptied a whole table here.
    """
    kept = invested(db, user, name="TFSA")
    doomed = invested(db, user, name="RRSP")
    deposit(db, user, kept, 1_000.0)
    record(db, user, kept, MARCH, difference_amount=50.0)
    record(db, user, doomed, MARCH, difference_amount=90.0)
    record(db, user, doomed, APRIL, difference_amount=120.0)

    assert (readings_in(db, kept), readings_in(db, doomed)) == (1, 2)

    delete_account(db, user.id, doomed.id)

    assert readings_in(db, doomed) == 0, "the deleted account's readings remain"
    assert readings_in(db, kept) == 1, "another account's readings were taken too"


def test_one_users_readings_are_invisible_to_another(db, user):
    """Both figures are keyed on the owner, not only on the account."""
    other = make_user(db, "someone.else@example.com")
    mine = invested(db, user)
    deposit(db, user, mine, 10_000.0)
    record(db, user, mine, MARCH, difference_amount=500.0)

    assert net_worth(db, other.id).investment_gain == 0.0
    assert get_account(db, other.id, mine.id) is None


# --- the month's movement, as the page receives it ----------------------------

def test_the_page_reports_what_the_holding_did_during_the_month(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)
    record(db, user, account, APRIL, difference_amount=625.0)

    assert get_account_activity(db, user.id, account.id, APRIL).investment_return.month_gain == 125.0


def test_a_month_that_lost_value_reports_a_negative_movement(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)
    record(db, user, account, APRIL, difference_amount=150.0)

    assert get_account_activity(db, user.id, account.id, APRIL).investment_return.month_gain == -350.0


def test_a_carried_forward_month_reports_no_movement_rather_than_none_happening(db, user):
    """The distinction the tile has to render differently: unknown, not flat."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    figure = get_account_activity(db, user.id, account.id, MAY).investment_return
    assert figure.is_carried_forward is True
    assert figure.month_gain is None


def test_the_first_reading_has_a_level_but_no_movement(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)

    figure = get_account_activity(db, user.id, account.id, MARCH).investment_return
    assert figure.difference_amount == 500.0
    assert figure.month_gain is None, "nothing to subtract from"


def test_the_card_reports_no_month_movement_because_it_asked_for_no_month(db, user):
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=500.0)
    record(db, user, account, APRIL, difference_amount=625.0)

    assert get_account(db, user.id, account.id).investment_return.month_gain is None


# --- the all-time figure the page header shows -------------------------------

def test_the_page_carries_an_all_time_figure_matching_the_card(db, user):
    """The header is an all-time number, so it needs the latest reading against
    the all-time balance -- exactly what the card computes."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)
    record(db, user, account, MAY, difference_amount=500.0)

    activity = get_account_activity(db, user.id, account.id, MAY)
    card = get_account(db, user.id, account.id)

    assert activity.all_time_return.difference_amount == card.investment_return.difference_amount
    assert activity.all_time_return.return_percent == card.investment_return.return_percent
    assert activity.all_time_return.as_of == card.investment_return.as_of


def test_the_all_time_figure_does_not_move_with_the_month_picker(db, user):
    """The bug this field exists to prevent.

    Browsing back to March must not restate what the holding is worth today. The
    month-scoped figure changes; the all-time one does not.
    """
    account = invested(db, user)
    deposit(db, user, account, 10_000.0)
    record(db, user, account, MARCH, difference_amount=100.0)
    record(db, user, account, MAY, difference_amount=500.0)

    march = get_account_activity(db, user.id, account.id, MARCH)
    may = get_account_activity(db, user.id, account.id, MAY)

    assert march.investment_return.difference_amount == 100.0, "March's own reading"
    assert may.investment_return.difference_amount == 500.0, "May's own reading"
    # The all-time figure is the same from either month.
    assert march.all_time_return.difference_amount == 500.0
    assert may.all_time_return.difference_amount == 500.0


def test_the_all_time_figure_uses_the_all_time_balance(db, user):
    """Not the month's. $15,000 is in by today, so the percentage is 500/15000."""
    account = invested(db, user)
    deposit(db, user, account, 10_000.0, on_date=date(2026, 1, 15))
    deposit(db, user, account, 5_000.0, on_date=date(2026, 4, 20))
    record(db, user, account, MARCH, difference_amount=500.0)

    activity = get_account_activity(db, user.id, account.id, MARCH)

    assert activity.ledger_balance_at_month == 10_000.0, "the form's denominator"
    assert activity.all_time_return.ledger_balance == 15_000.0, "the header's denominator"
    assert activity.all_time_return.return_percent == 3.3


def test_market_value_is_the_balance_plus_the_all_time_level(db, user):
    """What the card and the header now print as the headline figure. Stated as a
    test because the client adds these two, and if they ever stopped being
    addable the cards would silently stop summing to net worth."""
    account = invested(db, user)
    deposit(db, user, account, 6_893.93)
    record(db, user, account, MARCH, market_value=7_268.27)

    activity = get_account_activity(db, user.id, account.id, MARCH)
    worth = activity.balance + activity.all_time_return.difference_amount

    assert round(worth, 2) == 7_268.27


def test_a_non_investment_account_has_no_all_time_figure(db, user):
    spending = make_account(db, user.id, "Chequing")
    deposit(db, user, spending, 500.0)

    assert get_account_activity(db, user.id, spending.id, MARCH).all_time_return is None


def test_the_sum_of_what_the_cards_show_equals_net_worth(db, user):
    """The incoherence this whole change exists to close.

    Net worth adds each investment account's latest gain, so the cards have to
    show market value or the headline can never be reached by adding up what is
    on screen -- and `Sectors` carries a comment warning about exactly that.
    """
    tfsa = invested(db, user, name="TFSA")
    rrsp = invested(db, user, name="RRSP")
    chequing = make_account(db, user.id, "Chequing")
    deposit(db, user, tfsa, 6_000.0)
    deposit(db, user, rrsp, 4_000.0)
    deposit(db, user, chequing, 1_200.0)
    record(db, user, tfsa, MARCH, difference_amount=400.0)
    record(db, user, rrsp, MARCH, difference_amount=-150.0)

    cards = get_accounts(db, user.id)
    on_screen = sum(
        card.balance + (card.investment_return.difference_amount
                        if card.investment_return else 0.0)
        for card in cards
        if card.counts_toward_net_worth
    )

    assert round(on_screen, 2) == net_worth(db, user.id).net_worth
