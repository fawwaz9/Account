"""The omnibox: one line in, filed into the right module.

The routing rule is three ordered cases, and the tests that matter are the ones
where a line could plausibly go two ways. A wrong guess here is worse than no
omnibox, so each boundary gets pinned.
"""
from datetime import date

import pytest

from app._database.models import GradeModel, TaskModel, TransactionModel
from app.Omnibox.schemas.omnibox import OmniboxKind
from app.Omnibox.services.omnibox_service import build_preview, file_it
from app.Finances.services.transaction_service import list_transactions
from conftest import make_account, make_category, make_course, make_user


def setup_account(db, user):
    """A spending account and a savings one, so "which pot" is a real question."""
    spending = make_account(db, user.id, "Spending")
    spending.kind = "spending"
    savings = make_account(db, user.id, "Savings")
    savings.kind = "savings"
    db.commit()
    return spending, savings


# ----------------------------------------------------------------- routing --

def test_a_score_goes_to_grades(db, user):
    make_course(db, user.id, "COSC 121")
    assert build_preview(db, user.id, "cosc121 midterm 78/100").kind == OmniboxKind.GRADE


def test_an_amount_goes_to_money(db, user):
    setup_account(db, user)
    assert build_preview(db, user.id, "coffee 4.50").kind == OmniboxKind.EXPENSE


def test_everything_else_is_a_task(db, user):
    assert build_preview(db, user.id, "buy milk").kind == OmniboxKind.TASK


def test_a_course_number_does_not_make_it_money(db, user):
    """The reason a bare integer is never an amount."""
    make_course(db, user.id, "COSC 121")
    assert build_preview(db, user.id, "cosc121 lab due fri").kind == OmniboxKind.TASK


def test_a_score_wins_over_an_amount(db, user):
    """"78/100" is a mark even with money-looking digits beside it."""
    make_course(db, user.id, "COSC 121")
    setup_account(db, user)

    preview = build_preview(db, user.id, "cosc121 midterm 78/100")

    assert preview.kind == OmniboxKind.GRADE
    assert preview.amount is None


# ------------------------------------------------------------------ grades --

def test_a_grade_reads_course_name_and_mark(db, user):
    make_course(db, user.id, "COSC 121")
    preview = build_preview(db, user.id, "cosc121 midterm 78/100")

    assert preview.course_code == "COSC 121"
    assert (preview.score, preview.max_score) == (78.0, 100.0)
    assert preview.title == "midterm"
    assert preview.can_create is True


def test_the_category_is_read_from_the_name(db, user):
    make_course(db, user.id, "COSC 121")

    assert build_preview(db, user.id, "cosc121 midterm 78/100").grade_category == "Midterm"
    assert build_preview(db, user.id, "cosc121 lab 3 18/20").grade_category == "Lab"
    assert build_preview(db, user.id, "cosc121 quiz 9/10").grade_category == "Quiz"


def test_an_unrecognised_name_falls_back_to_other(db, user):
    make_course(db, user.id, "COSC 121")
    assert build_preview(db, user.id, "cosc121 essay 40/50").grade_category == "Other"


def test_a_mark_with_no_course_cannot_be_filed(db, user):
    """It has to go somewhere, and guessing the course would be worse."""
    preview = build_preview(db, user.id, "midterm 78/100")

    assert preview.can_create is False
    assert "course code" in preview.reason


def test_a_mark_naming_an_unknown_course_says_which(db, user):
    make_course(db, user.id, "COSC 121")
    preview = build_preview(db, user.id, "cs221 midterm 78/100")

    assert preview.can_create is False
    assert "CS 221" in preview.reason


def test_filing_a_grade_writes_it_to_the_course(db, user):
    course = make_course(db, user.id, "COSC 121")
    result = file_it(db, user.id, "cosc121 midterm 78/100")

    assert result.kind == OmniboxKind.GRADE
    assert result.course_id == course.id
    [grade] = db.query(GradeModel).all()
    assert (grade.name, grade.category, grade.score, grade.max_score) == (
        "midterm", "Midterm", 78.0, 100.0,
    )


# ------------------------------------------------------------------- money --

def test_an_expense_lands_in_the_spending_account_by_default(db, user):
    setup_account(db, user)
    preview = build_preview(db, user.id, "coffee 4.50")

    assert preview.account_name == "Spending"
    assert preview.amount == 4.50
    assert preview.title == "coffee"


def test_naming_an_account_overrides_the_default(db, user):
    setup_account(db, user)
    preview = build_preview(db, user.id, "transfer fee 2.50 savings")

    assert preview.account_name == "Savings"
    # The account name is understood, so it does not also stay in the description.
    assert "savings" not in preview.title.lower()


def test_a_category_is_matched_and_taken_out_of_the_description(db, user):
    setup_account(db, user)
    make_category(db, user.id, "Groceries")
    preview = build_preview(db, user.id, "groceries 42.10 market run")

    assert preview.category_name == "Groceries"
    assert preview.title == "market run"


def test_a_line_that_is_only_a_category_still_gets_a_description(db, user):
    setup_account(db, user)
    make_category(db, user.id, "Groceries")
    preview = build_preview(db, user.id, "groceries 42.10")

    assert preview.title == "Groceries"
    assert preview.can_create is True


def test_a_name_only_matches_on_a_word_boundary(db, user):
    """"Art" must not match inside "started"."""
    setup_account(db, user)
    make_category(db, user.id, "Art")
    preview = build_preview(db, user.id, "started early 9.99")

    assert preview.category_name is None


def test_an_expense_with_a_date_uses_it(db, user):
    setup_account(db, user)
    preview = build_preview(db, user.id, "coffee 4.50 2026-09-20")

    assert preview.on_date == date(2026, 9, 20)


def test_an_expense_with_no_date_is_today(db, user):
    setup_account(db, user)
    assert build_preview(db, user.id, "coffee 4.50").on_date == date.today()


def test_money_with_nowhere_to_put_it_cannot_be_filed(db, user):
    preview = build_preview(db, user.id, "coffee 4.50")

    assert preview.can_create is False
    assert "account" in preview.reason.lower()


def test_filing_an_expense_leaves_the_account(db, user):
    """Signing goes through the ordinary money path, so it cannot drift."""
    spending, _ = setup_account(db, user)
    file_it(db, user.id, "coffee 4.50")

    [row] = list_transactions(db, user.id)
    assert row.signed_amount == -4.50
    assert row.account_id == spending.id


# ------------------------------------------------------------------- tasks --

def test_a_task_reads_course_date_and_duration(db, user):
    course = make_course(db, user.id, "COSC 121")
    preview = build_preview(db, user.id, "cosc121 lab report due fri 90m")

    assert preview.course_id == course.id
    assert preview.title == "lab report"
    assert preview.estimated_minutes == 90
    assert preview.on_date is not None


def test_filing_a_task_writes_an_ordinary_task(db, user):
    make_course(db, user.id, "COSC 121")
    result = file_it(db, user.id, "cosc121 lab due fri")

    assert result.kind == OmniboxKind.TASK
    [task] = db.query(TaskModel).all()
    assert task.title == "lab"
    assert task.done is False


def test_a_line_with_no_words_cannot_be_filed(db, user):
    preview = build_preview(db, user.id, "fri")

    assert preview.can_create is False
    assert "what it is" in preview.reason


# ------------------------------------------------------------ safety rails --

def test_previewing_never_writes(db, user):
    make_course(db, user.id, "COSC 121")
    setup_account(db, user)

    for line in ("cosc121 midterm 78/100", "coffee 4.50", "cosc121 lab due fri"):
        build_preview(db, user.id, line)

    assert db.query(GradeModel).count() == 0
    assert db.query(TransactionModel).count() == 0
    assert db.query(TaskModel).count() == 0


def test_filing_an_unfileable_line_is_refused(db, user):
    with pytest.raises(ValueError):
        file_it(db, user.id, "midterm 78/100")

    assert db.query(GradeModel).count() == 0


def test_another_users_course_is_never_matched(db, user):
    stranger = make_user(db, "stranger@example.com")
    make_course(db, stranger.id, "COSC 121")

    preview = build_preview(db, user.id, "cosc121 midterm 78/100")

    assert preview.can_create is False


def test_another_users_account_is_never_used(db, user):
    stranger = make_user(db, "stranger@example.com")
    make_account(db, stranger.id, "Theirs")

    preview = build_preview(db, user.id, "coffee 4.50 theirs")

    assert preview.can_create is False
