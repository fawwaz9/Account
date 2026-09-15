"""What you have, less what you owe.

The page used to show `Total: $X` -- a plain sum of every balance, which counted
a credit card as though it were savings and money someone else was holding as
though it were in your pocket.

The interesting property is that **debt needs no arithmetic of its own**. A debt
account's balance is the ordinary signed sum of its rows, so it is already
negative and a plain sum subtracts it. The tests below exist largely to catch
someone "fixing" that by subtracting it a second time.
"""
import datetime
import uuid

import pytest

from app._database.models import TransactionModel
from app.Finances.schemas.account import AccountCreate, AccountKind, AccountUpdate
from app.Finances.services.account_service import (
    create_account,
    net_worth,
    update_account,
)
from tests.conftest import make_account

ANCHOR = datetime.date(2026, 10, 14)
CENT = 0.011


def put(db, user, account, amount):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        kind="income", amount=amount, description="Opening", occurred_on=ANCHOR,
    ))
    db.commit()


@pytest.fixture
def savings(db, user):
    account = make_account(db, user.id, "Savings", kind="savings")
    put(db, user, account, 1500.00)
    return account


@pytest.fixture
def card(db, user):
    """A credit card carrying 1,000 owed, recorded the way the app records it:
    purchases are expenses on the account, so the balance runs negative."""
    account = make_account(db, user.id, "Visa", kind="debt")
    put(db, user, account, -1000.00)
    return account


# ------------------------------------------------------------------- debt --

def test_debt_lowers_net_worth_by_its_magnitude(db, user, savings, card):
    figure = net_worth(db, user.id)

    assert figure.net_worth == pytest.approx(500.00, abs=CENT)


def test_debt_is_reported_as_a_positive_magnitude(db, user, savings, card):
    """"Debt -1,000" reads as a double negative, so the line carries the size."""
    figure = net_worth(db, user.id)

    assert figure.debt_total == pytest.approx(1000.00, abs=CENT)


def test_debt_is_not_subtracted_twice(db, user, savings, card):
    """The failure this whole design is shaped to avoid.

    A debt balance is already negative. Subtracting `debt_total` from
    `net_worth` as well would report 1,500 - 1,000 - 1,000 = -500 on a person
    who is 500 in the black.
    """
    figure = net_worth(db, user.id)

    assert figure.net_worth == pytest.approx(
        1500.00 - 1000.00, abs=CENT
    ), "net_worth should already include the negative balance, not subtract it again"
    assert figure.net_worth > 0


def test_no_debt_accounts_means_a_zero_debt_line(db, user, savings):
    assert net_worth(db, user.id).debt_total == 0.0


# -------------------------------------------------------- the opt-out flag --

def test_an_other_account_counts_by_default(db, user, savings):
    lent = make_account(db, user.id, "Money Lent", kind="other")
    put(db, user, lent, 250.00)

    assert net_worth(db, user.id).net_worth == pytest.approx(1750.00, abs=CENT)


def test_toggling_an_other_account_off_removes_it_silently(db, user, savings):
    lent = make_account(db, user.id, "Money Lent", kind="other")
    put(db, user, lent, 250.00)

    update_account(db, user.id, lent.id, AccountUpdate(counts_toward_net_worth=False))
    figure = net_worth(db, user.id)

    assert figure.net_worth == pytest.approx(1500.00, abs=CENT)
    # It is excluded, not reclassified: money owed to you is not money you owe.
    assert figure.debt_total == 0.0


def test_a_created_account_counts_without_the_client_saying_so(db, user, savings):
    created = create_account(db, user.id, AccountCreate(name="Travel", kind=AccountKind.SAVINGS))

    assert created.counts_toward_net_worth is True


@pytest.mark.parametrize("kind", ["spending", "savings", "investment", "emergency", "other", "debt"])
def test_any_kind_of_account_can_be_taken_out_of_the_total(db, user, savings, kind):
    """No kind is privileged here.

    This was once restricted to "other" accounts, on the reasoning that Money
    Lent was the only real case and that hiding a savings account would let the
    headline be quietly falsified. That trades a rule the student has to be
    told about for a judgement they are better placed to make -- a joint
    account, or one held for somebody else, is just as real and no rule here
    could have anticipated it.
    """
    account = make_account(db, user.id, f"Pot ({kind})", kind=kind)
    put(db, user, account, 300.00)
    before = net_worth(db, user.id).net_worth

    update_account(db, user.id, account.id, AccountUpdate(counts_toward_net_worth=False))

    assert net_worth(db, user.id).net_worth == pytest.approx(before - 300.00, abs=CENT)


def test_a_debt_account_can_be_hidden_and_leaves_the_debt_line_too(db, user, savings, card):
    """Excluded means excluded from both figures, not moved between them."""
    update_account(db, user.id, card.id, AccountUpdate(counts_toward_net_worth=False))

    figure = net_worth(db, user.id)
    assert figure.net_worth == pytest.approx(1500.00, abs=CENT)
    assert figure.debt_total == 0.0


def test_an_account_can_be_created_already_excluded(db, user, savings):
    created = create_account(db, user.id, AccountCreate(
        name="Held for a friend", kind=AccountKind.SAVINGS, counts_toward_net_worth=False))

    assert created.counts_toward_net_worth is False


def test_excluding_a_spending_account_does_not_change_what_is_safe_to_spend(db, user):
    """Two different questions, and they must not be coupled.

    "What am I worth" and "what can I spend before payday" have different
    answers, so a pot left out of the first is still cash in hand for the
    second. Wiring net worth into safe-to-spend would make one setting quietly
    change two figures.
    """
    import datetime
    from app.Finances.services.safe_service import safe_to_spend

    spending = make_account(db, user.id, "Chequing", kind="spending")
    put(db, user, spending, 900.00)
    before = safe_to_spend(db, user.id, on_day=datetime.date(2026, 10, 14)).safe_now

    update_account(db, user.id, spending.id, AccountUpdate(counts_toward_net_worth=False))

    after = safe_to_spend(db, user.id, on_day=datetime.date(2026, 10, 14)).safe_now
    assert after == pytest.approx(before, abs=CENT)
    assert after == pytest.approx(900.00, abs=CENT)


# ------------------------------------------------------------------ edges --

def test_archiving_removes_an_account_from_net_worth(db, user, savings):
    """Matching what the accounts list already does, so the two agree."""
    other = make_account(db, user.id, "Old ISA", kind="savings")
    put(db, user, other, 400.00)
    assert net_worth(db, user.id).net_worth == pytest.approx(1900.00, abs=CENT)

    update_account(db, user.id, other.id, AccountUpdate(archived=True))

    assert net_worth(db, user.id).net_worth == pytest.approx(1500.00, abs=CENT)


def test_a_transfer_between_counting_accounts_leaves_net_worth_alone(db, user, savings):
    """Moving money is not earning it. The two halves cancel, which is the
    whole reason a transfer is two signed rows rather than a special record."""
    spending = make_account(db, user.id, "Chequing", kind="spending")
    before = net_worth(db, user.id).net_worth

    group = uuid.uuid4()
    for account, amount in ((savings, -200.00), (spending, 200.00)):
        db.add(TransactionModel(
            id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="transfer",
            amount=amount, description="Move", occurred_on=ANCHOR, group_id=group,
        ))
    db.commit()

    assert net_worth(db, user.id).net_worth == pytest.approx(before, abs=CENT)


def test_paying_down_the_card_raises_net_worth_by_nothing(db, user, savings, card):
    """A payment moves money from one pot to another; it does not create any.

    Worth asserting because it is counter-intuitive: the debt line falls, which
    feels like progress, and net worth correctly does not move.
    """
    before = net_worth(db, user.id)

    group = uuid.uuid4()
    for account, amount in ((savings, -300.00), (card, 300.00)):
        db.add(TransactionModel(
            id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="transfer",
            amount=amount, description="Card payment", occurred_on=ANCHOR, group_id=group,
        ))
    db.commit()

    after = net_worth(db, user.id)
    assert after.net_worth == pytest.approx(before.net_worth, abs=CENT)
    assert after.debt_total == pytest.approx(700.00, abs=CENT)
