"""Checking a whole stored row against its create schema, after an edit (audit H1).

An update schema checks only the fields sent. A row is only sound when the whole of it,
as it will be after the edit, passes the rules a new one must: otherwise one edit can store
a row its own response model refuses, and every read of it fails. These helpers run that
check and turn a refusal into the one sentence a 400 can carry.
"""
from typing import Any

from pydantic import BaseModel, ValidationError


def readable(exc: ValidationError) -> str:
    """Return a schema refusal as one sentence: the first problem, with its field.

    Args:
        exc: The refusal.

    Returns:
        For a field rule, "name: String should have at least 1 character"; for a
        cross-field rule, its own message, such as "end date cannot be before start date".
    """
    error = exc.errors()[0]
    message = error["msg"].removeprefix("Value error, ")
    field = ".".join(str(part) for part in error.get("loc", ()))
    return f"{field}: {message}" if field else message


def check_whole_row(schema: type[BaseModel], fields: dict[str, Any]) -> None:
    """Refuse a row, as it will be after an edit, that `schema` would refuse as new.

    Only checks: nothing is written back, so a schema that tidies its input (stripping
    spaces, say) never rewrites what is stored.

    Args:
        schema: The create schema whose rules a complete row must meet.
        fields: The row's fields, as the schema names them.

    Raises:
        ValueError: With `readable`'s sentence, when the schema refuses the row.
    """
    try:
        schema.model_validate(fields)
    except ValidationError as exc:
        raise ValueError(readable(exc)) from exc
