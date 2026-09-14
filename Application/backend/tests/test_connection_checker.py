"""The diagnostic that reads the connection string and says what is wrong.

Not application code -- it runs by hand during a deploy. It is tested because
its whole value is being *right about the cause*, and a check that confidently
names the wrong one is worse than no check. That happened: the first version
reported a bracketed password as "these characters need percent-encoding",
which is true, useless, and sends you off editing a string that needed two
characters deleted.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "check_db_connection", BACKEND / "scripts" / "check_db_connection.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_db_connection", module)
    spec.loader.exec_module(module)
    return module


checker = load()


def diagnosis(password: str, capsys) -> str:
    assert checker.describe_password(password) == 1, "every branch here is a failure"
    return capsys.readouterr().out


def test_a_bracketed_password_is_diagnosed_as_brackets(capsys):
    """The case that actually happened, and the ordering that fixes it.

    `[` and `]` are reserved in a URL, so the percent-encoding branch matches
    this too -- and matches it first if the checks are in the wrong order. The
    advice it gives is technically correct and completely unhelpful.
    """
    out = diagnosis("[hunter2hunter2h]", capsys)

    assert "square brackets" in out
    assert "percent-encode" not in out.lower()
    # The fix has to be actionable without thinking: say how many characters
    # should be left.
    assert "15" in out


def test_an_untouched_placeholder_is_named_as_one(capsys):
    """Only the bare form reaches this branch.

    `[YOUR-PASSWORD]` is caught by the bracket check above it, which is the
    better message of the two -- it says exactly which characters to delete.
    Asserted here so that ordering is deliberate rather than incidental.
    """
    assert "square brackets" in diagnosis("[YOUR-PASSWORD]", capsys)
    assert "placeholder" in diagnosis("YOUR-PASSWORD", capsys)


def test_a_genuinely_reserved_character_still_gets_the_encoding_advice(capsys):
    """Narrowing the bracket case must not swallow the real one."""
    out = diagnosis("pa@ssw0rd", capsys)

    assert "reserved" in out
    assert "%40" in out, "it has to give the encoding, not just name the problem"


def test_an_empty_password_is_not_reported_as_a_wrong_one(capsys):
    out = diagnosis("", capsys)
    assert "no password" in out


def test_a_well_formed_password_is_reported_as_simply_wrong(capsys):
    """The one case where there is nothing clever to say.

    Saying so plainly matters: otherwise the reader keeps hunting for a
    formatting mistake that is not there.
    """
    out = diagnosis("perfectlyFine123", capsys)

    assert "not the password Supabase has" in out
    assert "Reset database password" in out


def test_the_password_itself_is_never_printed(capsys):
    """It is described -- length, character classes -- never shown.

    This output gets pasted into chat when someone asks for help.
    """
    secret = "sup3rs3cretvalue"
    for password in (secret, f"[{secret}]", f"{secret}@x"):
        out = diagnosis(password, capsys)
        assert secret not in out, f"leaked for {password!r}"
