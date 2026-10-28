"""The shared merchant map (Phase 3 item 4, D11), on SQLite and Postgres.

The promises: one vote per person per merchant, their confident choice; never a
transfer or payment; written at 3 people holding 75% of the votes; switching
sharing off takes your votes out; the map only ever suggests a category you have,
by name, after your own history and before the curated list; and the SQL and Python
sides agree, the merchant key included.
"""
import re
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app._database import aggregates, recounts, rls
from app._database.identity import act_as
from app._database.models import (
    MERCHANT_FLOOR, AccountModel, MerchantCategoryModel, SpendCategoryModel, TransactionModel, utc_now,
)
from app.Finances.services import categorize_service
from app.Finances.services.categorize_service import Categorizer
from app.Finances.services.forecast_service import merchant_key
from conftest import TESTING_SQLITE, make_user


def spender(db, *categories):
    """A person with an account and the named categories; returns (user, {name: category})."""
    user = make_user(db, f"s-{uuid.uuid4().hex[:8]}@example.com")
    account = AccountModel(id=uuid.uuid4(), user_id=user.id, name="Chequing", kind="spending", income_share=100.0)
    db.add(account)
    made = {}
    for name in categories:
        made[name] = SpendCategoryModel(id=uuid.uuid4(), user_id=user.id, name=name)
        db.add(made[name])
    db.commit()
    user.account_id = account.id
    return user, made


def spend(db, user, category, description, times=1):
    for _ in range(times):
        db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=user.account_id, kind="expense",
                                amount=-5.0, description=description, occurred_on=date(2026, 10, 1),
                                category_id=category.id))
    db.commit()


def voters(db, n, description="BLENZ COFFEE #1234", category="Coffee", times=1):
    people = []
    for _ in range(n):
        user, made = spender(db, category)
        spend(db, user, made[category], description, times)
        people.append(user)
    return people


def shared(db, *keys):
    act_as(db, make_user(db, f"reader-{uuid.uuid4().hex[:6]}@example.com").id)
    return aggregates.merchant_categories(db, list(keys))


# --- the rules -----------------------------------------------------------------------------

@pytest.mark.parametrize("description", [
    "BLENZ COFFEE #1234", "Subway 0042", "  UBER *EATS  ", "Tim Hortons - #88,", None, "", "Café 7",
    "STARBUCKS\tSTORE  12", "*** 123 ***",
])
def test_the_sql_merchant_key_is_the_forecasts(db, description):
    if TESTING_SQLITE:
        pytest.skip("the SQL twin is Postgres-only")
    assert db.execute(text("SELECT account_merchant_key(:d)"), {"d": description}).scalar() == merchant_key(description)


def test_the_floor_and_shares_in_the_functions_are_the_models():
    body = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_recount_merchant_categories("):]
    body = body[:body.index("$$;")]
    assert f"people >= {MERCHANT_FLOOR}" in body
    assert f"n >= {aggregates.PERSONAL_AGREEMENT} * total" in body
    assert f"people >= {aggregates.SHARED_AGREEMENT} * voters" in body
    assert aggregates.PERSONAL_AGREEMENT == categorize_service.MAP_AGREEMENT
    words = re.search(r"\[\[:<:\]\]\((.*?)\)\[\[:>:\]\]", body).group(1)
    assert words == aggregates.NOT_MERCHANTS.pattern.split("(")[1].split(")")[0]
    read = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_merchant_categories("):]
    assert f"m.people >= {MERCHANT_FLOOR}" in read[:read.index("$$;")]


# --- counting --------------------------------------------------------------------------------

def test_three_people_agreeing_put_a_merchant_on_the_map(db):
    voters(db, MERCHANT_FLOOR)
    assert aggregates.recount_merchant_categories(db) == 1
    assert shared(db, "blenz coffee") == {"blenz coffee": "coffee"}


def test_below_the_floor_nothing_is_written(db):
    voters(db, MERCHANT_FLOOR - 1)
    assert aggregates.recount_merchant_categories(db) == 0


def test_one_vote_per_person_however_many_times_they_went(db):
    voters(db, MERCHANT_FLOOR - 1, times=20)
    assert aggregates.recount_merchant_categories(db) == 0


def test_a_contested_merchant_stays_out(db):
    """Three say groceries, two say household: 60% isn't 75%."""
    voters(db, 3, description="COSTCO WHOLESALE", category="Groceries")
    voters(db, 2, description="COSTCO WHOLESALE", category="Household")
    assert aggregates.recount_merchant_categories(db) == 0
    voters(db, 4, description="COSTCO WHOLESALE", category="Groceries")
    assert aggregates.recount_merchant_categories(db) == 1, "7 of 9 is past 75%"


def test_a_person_split_between_categories_gives_no_vote(db):
    for _ in range(MERCHANT_FLOOR - 1):
        voters(db, 1)
    torn, made = spender(db, "Coffee", "Snacks")
    spend(db, torn, made["Coffee"], "BLENZ COFFEE", times=3)
    spend(db, torn, made["Snacks"], "BLENZ COFFEE", times=2)
    assert aggregates.recount_merchant_categories(db) == 0
    spend(db, torn, made["Coffee"], "BLENZ COFFEE", times=5)
    assert aggregates.recount_merchant_categories(db) == 1, "8 of 10 is a confident choice"


def test_category_names_are_matched_without_case(db):
    voters(db, 1, category="Coffee")
    voters(db, 1, category="coffee")
    voters(db, 1, category="COFFEE")
    aggregates.recount_merchant_categories(db)
    assert shared(db, "blenz coffee") == {"blenz coffee": "coffee"}


@pytest.mark.parametrize("description", [
    "INTERAC E-TRANSFER TO JOHN SMITH", "E-TRANSFER 1234", "ONLINE PAYMENT - VISA", "ATM WITHDRAWAL",
    "PAYROLL DEPOSIT", "PAYPAL *JOHNSMITH", "VENMO", "AB",
])
def test_transfers_payments_and_tiny_keys_are_never_merchants(db, description):
    voters(db, MERCHANT_FLOOR + 2, description=description, category="Rent")
    assert aggregates.recount_merchant_categories(db) == 0


def test_switching_sharing_off_takes_your_vote_out(db):
    people = voters(db, MERCHANT_FLOOR)
    people[0].preferences = {"share_merchant_categories": False}
    db.commit()
    assert aggregates.recount_merchant_categories(db) == 0


def test_deleted_accounts_and_archived_categories_dont_vote(db):
    people = voters(db, MERCHANT_FLOOR)
    people[0].deleted_at = utc_now()
    db.commit()
    assert aggregates.recount_merchant_categories(db) == 0
    people[0].deleted_at = None
    db.query(SpendCategoryModel).filter(SpendCategoryModel.user_id == people[1].id).update({"archived": True})
    db.commit()
    assert aggregates.recount_merchant_categories(db) == 0


def test_the_read_checks_the_floor_again_and_answers_only_whats_asked(db):
    db.add(MerchantCategoryModel(merchant_key="thin", category_name="coffee", people=MERCHANT_FLOOR - 1))
    db.add(MerchantCategoryModel(merchant_key="blenz", category_name="coffee", people=MERCHANT_FLOOR))
    db.add(MerchantCategoryModel(merchant_key="other", category_name="food", people=9))
    db.commit()
    assert shared(db, "thin", "blenz", "missing", "") == {"blenz": "coffee"}
    assert shared(db) == {}


def test_the_daily_recount_runs_it(db):
    voters(db, MERCHANT_FLOOR)
    assert recounts.run_all(db)["merchant_categories"] == 1


# --- suggesting --------------------------------------------------------------------------------

def map_holds(db, key="blenz coffee", name="coffee"):
    db.add(MerchantCategoryModel(merchant_key=key, category_name=name, people=MERCHANT_FLOOR))
    db.commit()


def test_a_new_user_gets_the_shared_category_when_they_have_one_by_that_name(db):
    map_holds(db)
    newcomer, made = spender(db, "Coffee", "Groceries")
    act_as(db, newcomer.id)
    suggestion = Categorizer(db, newcomer.id).suggest("BLENZ COFFEE #9")
    assert (suggestion.category_id, suggestion.source) == (made["Coffee"].id, categorize_service.SHARED)


def test_the_map_never_suggests_a_category_you_dont_have(db):
    map_holds(db)
    newcomer, _ = spender(db, "Groceries")
    act_as(db, newcomer.id)
    assert Categorizer(db, newcomer.id).suggest("BLENZ COFFEE").category_id is None


def test_your_own_history_always_wins(db):
    map_holds(db)
    regular, made = spender(db, "Coffee", "Treats")
    spend(db, regular, made["Treats"], "BLENZ COFFEE", times=3)
    act_as(db, regular.id)
    suggestion = Categorizer(db, regular.id).suggest("BLENZ COFFEE")
    assert (suggestion.category_id, suggestion.source) == (made["Treats"].id, categorize_service.LEARNED)


def test_the_map_comes_before_the_curated_list(db):
    """Starbucks is on the curated list as Eating out first; the crowd says Coffee."""
    map_holds(db, key="starbucks", name="coffee")
    newcomer, made = spender(db, "Coffee", "Eating out")
    act_as(db, newcomer.id)
    assert Categorizer(db, newcomer.id).suggest("STARBUCKS").category_id == made["Coffee"].id


def test_prefetch_reads_the_map_once_for_many_rows(db, monkeypatch):
    map_holds(db)
    newcomer, made = spender(db, "Coffee")
    act_as(db, newcomer.id)
    calls = []
    real = aggregates.merchant_categories
    monkeypatch.setattr(aggregates, "merchant_categories", lambda db, keys: calls.append(keys) or real(db, keys))
    categorizer = Categorizer(db, newcomer.id)
    categorizer.prefetch(["BLENZ COFFEE #1", "BLENZ COFFEE #2", "SAFEWAY 12"])
    assert [categorizer.suggest(d).category_id for d in ("BLENZ COFFEE #1", "BLENZ COFFEE #2")] == \
        [made["Coffee"].id] * 2
    assert len(calls) == 1
