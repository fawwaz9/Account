"""Category suggestions, personal layers (Phase 1 item 8).

Cheapest first: your own past choices, then a curated rule, then naive Bayes on
your own history -- and nothing at all below the confidence bar, because a
wrong category erodes trust as fast as a hallucinated syllabus weight.
"""
import datetime
import uuid

import pytest

from app._database.models import SpendCategoryModel, TransactionModel
from app.Finances.schemas.importing import CommitRequest
from app.Finances.services.categorize_service import BAYES, LEARNED, RULE, Categorizer
from app.Finances.services.import_service import commit, detect_mapping, parse_table, preview
from tests.conftest import make_account, make_user

D = datetime.date(2026, 9, 1)


def category(db, user, name, archived=False):
    row = SpendCategoryModel(id=uuid.uuid4(), user_id=user.id, name=name, archived=archived, position=0)
    db.add(row)
    db.commit()
    return row


def spent(db, user, account, description, category_row, amount=-10.0):
    db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
                            amount=amount, description=description, occurred_on=D,
                            category_id=category_row.id if category_row else None))
    db.commit()


@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


def test_your_own_past_choice_beats_the_rule(db, user, chequing):
    coffee = category(db, user, "Coffee")
    category(db, user, "Eating out")  # what the curated rule would say
    spent(db, user, chequing, "TIM HORTONS #123", coffee)
    suggestion = Categorizer(db, user.id).suggest("TIM HORTONS #999")  # same merchant key
    assert (suggestion.category_id, suggestion.source) == (coffee.id, LEARNED)


def test_a_merchant_you_split_is_not_learned(db, user, chequing):
    groceries, home = category(db, user, "Groceries"), category(db, user, "Home")
    for target in (groceries, groceries, home):  # 67%: under the 80% bar
        spent(db, user, chequing, "COSTCO WHOLESALE", target)
    assert Categorizer(db, user.id).suggest("COSTCO WHOLESALE").source != LEARNED


def test_a_curated_rule_uses_your_category_name(db, user, chequing):
    groceries = category(db, user, "Groceries")
    suggestion = Categorizer(db, user.id).suggest("SAFEWAY #4410")
    assert (suggestion.category_id, suggestion.source) == (groceries.id, RULE)


def test_a_rule_with_no_matching_category_suggests_nothing(db, user, chequing):
    category(db, user, "Fun money")
    assert Categorizer(db, user.id).suggest("SAFEWAY #4410").category_id is None


def test_the_more_specific_rule_wins(db, user, chequing):
    eating, transport = category(db, user, "Eating out"), category(db, user, "Transportation")
    c = Categorizer(db, user.id)
    assert c.suggest("UBER EATS 8842").category_id == eating.id
    assert c.suggest("UBER TRIP 8842").category_id == transport.id


def test_naive_bayes_on_your_own_words(db, user, chequing):
    eating, books = category(db, user, "Eating out"), category(db, user, "Books")
    for name in ("PIZZA HUT", "PANAGO PIZZA", "PIZZA GARDEN", "MAGIC PIZZA", "PIZZA PLACE", "DOMINOS PIZZA"):
        spent(db, user, chequing, name, eating)
    for name in ("CHAPTERS BOOKS", "BOOK WAREHOUSE", "PAPERBACK BOOKS", "USED BOOKS"):
        spent(db, user, chequing, name, books)
    suggestion = Categorizer(db, user.id).suggest("NEW PIZZA SPOT")
    assert (suggestion.category_id, suggestion.source) == (eating.id, BAYES)


def test_bayes_stays_quiet_without_enough_history_or_confidence(db, user, chequing):
    eating, books = category(db, user, "Eating out"), category(db, user, "Books")
    for name in ("PIZZA HUT", "PANAGO PIZZA"):
        spent(db, user, chequing, name, eating)
    assert Categorizer(db, user.id).suggest("NEW PIZZA SPOT").category_id is None  # 2 rows < 10

    for n in range(5):
        spent(db, user, chequing, f"CORNER SHOP {n}", eating)
        spent(db, user, chequing, f"CORNER SHOP B{n}", books)
    # "corner shop" is half one, half the other: under the bar.
    assert Categorizer(db, user.id).suggest("CORNER SHOP NEW").category_id is None


def test_an_archived_category_is_never_suggested(db, user, chequing):
    old = category(db, user, "Groceries", archived=True)
    spent(db, user, chequing, "SAFEWAY #1", old)
    assert Categorizer(db, user.id).suggest("SAFEWAY #2").category_id is None


def test_another_users_choices_teach_you_nothing(db, user, chequing):
    other = make_user(db, "other@example.com")
    theirs = make_account(db, other.id, "Theirs")
    their_coffee = category(db, other, "Coffee")
    spent(db, other, theirs, "BLENZ COFFEE", their_coffee)
    category(db, user, "Fun money")
    assert Categorizer(db, user.id).suggest("BLENZ COFFEE").category_id is None


# --- in the import ---------------------------------------------------------

CSV = "Date,Description,Amount\n2026-10-01,SAFEWAY #4410,-62.18\n2026-10-02,PAYROLL,812.40\n"


def mapping():
    return detect_mapping(parse_table(CSV))[0]


def test_the_preview_suggests_for_expenses_only(db, user, chequing):
    groceries = category(db, user, "Groceries")
    text = CSV + "2026-10-03,SAFEWAY REFUND,5.00\n"  # money in, though the rule would match
    rows = preview(db, user.id, chequing.id, text, None).rows
    assert (rows[0].category_id, rows[0].category_source) == (groceries.id, RULE)
    assert rows[1].category_id is None
    assert rows[2].category_id is None


def test_the_commit_applies_only_the_categories_kept(db, user, chequing):
    groceries = category(db, user, "Groceries")
    summary = commit(db, user.id, CommitRequest(
        account_id=chequing.id, csv_text=CSV, mapping=mapping(), lines=[2, 3],
        categories={2: groceries.id, 3: groceries.id},  # an income line's category is ignored
    ))
    rows = {r.description: r for r in db.query(TransactionModel).filter(TransactionModel.import_id == summary.id)}
    assert rows["SAFEWAY #4410"].category_id == groceries.id
    assert rows["PAYROLL"].category_id is None


def test_without_a_kept_category_the_row_is_uncategorised(db, user, chequing):
    category(db, user, "Groceries")
    summary = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=CSV,
                                                mapping=mapping(), lines=[2]))
    [row] = db.query(TransactionModel).filter(TransactionModel.import_id == summary.id).all()
    assert row.category_id is None  # the suggestion is never applied unasked


def test_someone_elses_or_an_archived_category_is_refused(db, user, chequing):
    other = make_user(db, "other@example.com")
    theirs = category(db, other, "Groceries")
    old = category(db, user, "Old", archived=True)
    before = db.query(TransactionModel).count()
    for chosen in (theirs.id, old.id):
        with pytest.raises(ValueError, match="does not exist"):
            commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=CSV, mapping=mapping(),
                                              lines=[2], categories={2: chosen}))
    assert db.query(TransactionModel).count() == before
