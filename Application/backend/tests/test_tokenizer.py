"""The tokenizer: one parser for what a student types in a hurry.

Pure text in, structured fields out, so every case here runs without a database.
The ones worth having are the collisions -- where two patterns could both claim
the same digits -- and the date words, where being wrong is a missed deadline
rather than a cosmetic slip.
"""
from datetime import date

import pytest

from app.shared.tokenizer import parse

#: A Wednesday, so "fri" is two days out and "mon" is five.
WEDNESDAY = date(2026, 9, 9)


def parsed(text, today=WEDNESDAY):
    return parse(text, today)


# ---------------------------------------------------------- the whole line --

def test_the_motivating_example(db=None):
    """"CS221 lab due fri" is the line the feature exists for."""
    result = parsed("CS221 lab due fri")

    assert result.course_code == "CS 221"
    assert result.on_date == date(2026, 9, 11)
    assert result.title == "lab"


def test_everything_at_once():
    result = parsed("CPSC_V 210 assignment 2 due sep 20 90m")

    assert result.course_code == "CPSC_V 210"
    assert result.on_date == date(2026, 9, 20)
    assert result.minutes == 90
    assert "assignment" in result.title


def test_plain_text_parses_to_a_title_and_nothing_else():
    result = parsed("buy milk")

    assert result.title == "buy milk"
    assert result.found_anything is False


# ---------------------------------------------------- collisions, resolved --

def test_a_score_is_not_two_numbers():
    result = parsed("midterm 78/100")

    assert (result.score, result.max_score) == (78.0, 100.0)
    assert result.amount is None
    assert result.course_code is None


def test_a_duration_is_not_an_amount():
    result = parsed("readings 1h30")

    assert result.minutes == 90
    assert result.amount is None


def test_a_course_number_is_not_an_amount():
    """The reason a bare integer never counts as money."""
    result = parsed("COSC 121 lab")

    assert result.course_code == "COSC 121"
    assert result.amount is None


def test_a_date_is_not_a_course_code():
    result = parsed("essay sep 12")

    assert result.on_date == date(2026, 9, 12)
    assert result.course_code is None


def test_money_needs_saying_so():
    assert parsed("coffee 4.50").amount == 4.50
    assert parsed("coffee $5").amount == 5.0
    assert parsed("12 readings").amount is None


# -------------------------------------------------------------- date words --

def test_a_weekday_means_the_next_one():
    assert parsed("fri").on_date == date(2026, 9, 11)
    assert parsed("mon").on_date == date(2026, 9, 14)


def test_a_weekday_typed_on_that_day_means_today():
    """Someone writing "wed" on a Wednesday means today, not a week away."""
    assert parsed("wed", WEDNESDAY).on_date == WEDNESDAY


def test_next_weekday_means_the_week_after():
    assert parsed("next wed", WEDNESDAY).on_date == date(2026, 9, 16)
    assert parsed("next fri", WEDNESDAY).on_date == date(2026, 9, 18)


def test_named_days():
    assert parsed("today").on_date == WEDNESDAY
    assert parsed("tomorrow").on_date == date(2026, 9, 10)
    assert parsed("tmr").on_date == date(2026, 9, 10)


def test_relative_days_and_weeks():
    assert parsed("in 3 days").on_date == date(2026, 9, 12)
    assert parsed("in 2 weeks").on_date == date(2026, 9, 23)


def test_explicit_dates_in_either_order():
    assert parsed("12 sep").on_date == date(2026, 9, 12)
    assert parsed("sep 12").on_date == date(2026, 9, 12)
    assert parsed("2026-10-02").on_date == date(2026, 10, 2)


def test_a_bare_month_and_day_never_means_the_past():
    """"sep 12" typed in November is next September, not ten months ago."""
    november = date(2026, 11, 20)
    assert parse("sep 12", november).on_date == date(2027, 9, 12)


def test_an_impossible_date_is_not_a_date():
    result = parsed("feb 31 essay")

    assert result.on_date is None
    assert "essay" in result.title


# ------------------------------------------------------------------ course --

def test_course_codes_in_the_shapes_this_app_stores():
    assert parsed("COSC 101 quiz").course_code == "COSC 101"
    assert parsed("CPSC_V 210 lab").course_code == "CPSC_V 210"
    assert parsed("ENG 109 essay").course_code == "ENG 109"


def test_a_code_typed_without_a_space():
    assert parsed("cs221 lab").course_code == "cs 221"


def test_a_code_with_a_trailing_letter():
    assert parsed("MATH 101A problem set").course_code == "MATH 101A"


# ---------------------------------------------------------------- duration --

def test_durations_in_the_forms_people_type():
    assert parsed("90m").minutes == 90
    assert parsed("90 mins").minutes == 90
    assert parsed("2h").minutes == 120
    assert parsed("2 hours").minutes == 120
    assert parsed("1h30").minutes == 90


# ------------------------------------------------------------------- title --

def test_what_is_left_becomes_the_title():
    assert parsed("CS221 write the lab report fri").title == "write the lab report"


def test_filler_around_a_date_is_dropped():
    assert parsed("essay due friday").title == "essay"
    assert parsed("reading by mon").title == "reading"


def test_filler_inside_the_title_is_kept():
    """Only the glue around a match goes; "the" in the middle is the student's."""
    assert parsed("read the handout fri").title == "read the handout"


def test_the_raw_text_always_survives():
    result = parsed("CS221 lab due fri")
    assert result.text == "CS221 lab due fri"


def test_an_empty_line_parses_to_nothing():
    result = parsed("")
    assert result.title == ""
    assert result.found_anything is False


def test_what_matched_is_reported():
    result = parsed("CS221 lab fri 90m")
    assert set(result.matched) == {"course", "date", "duration"}
