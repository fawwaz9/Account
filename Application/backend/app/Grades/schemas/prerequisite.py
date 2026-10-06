"""Prerequisites on the course page: yours, the shared one, and met or not
(Phase 2 items 4 and 7)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.Grades.schemas.catalogue import CatalogueCourse, CatalogueLink

Kind = Literal["prerequisite", "corequisite"]
Status = Literal["met", "on_track", "not_met"]


class RuleWrite(BaseModel):
    """Your rule, typed ("CPSC 210 and one of MATH 200, MATH 217") or as a tree."""

    kind: Kind = "prerequisite"
    text: str | None = Field(default=None, max_length=300)
    rule: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def one_form(self):
        if (self.text is None) == (self.rule is None):
            raise ValueError("Give the rule as text or as a tree, not both")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class RuleText(BaseModel):
    text: str = Field(..., max_length=300)


class RuleChecked(BaseModel):
    """A typed rule read back: the tree, and how it will be shown."""

    rule: dict[str, Any]
    text: str


class RuleResult(BaseModel):
    status: Status
    text: str
    detail: str = ""
    parts: list[RuleResult] = []
    group: Literal["all", "any"] | None = None


class PrerequisiteSide(BaseModel):
    """One version of a rule, with where it came from and whether you meet it.

    ``source``: ``typed`` or ``syllabus`` for yours; ``reviewed`` or
    ``ubc-calendar`` for the shared one. ``review`` is where yours stands in
    the owner's review; None for the shared one. ``source_text`` is your own
    syllabus's sentence on yours, the calendar's on a ``ubc-calendar`` row,
    and never anyone else's.
    """

    source: Literal["typed", "syllabus", "reviewed", "ubc-calendar"]
    rule: dict[str, Any]
    text: str
    note: str | None = None
    session: str | None = None
    source_text: str | None = None
    review: Literal["pending", "accepted", "rejected"] | None = None
    result: RuleResult


class PrerequisiteKind(BaseModel):
    """One kind for one course. ``applies`` says which version counts for you:
    yours whenever you have one (§13.19), else the shared one."""

    kind: Kind
    yours: PrerequisiteSide | None = None
    shared: PrerequisiteSide | None = None
    applies: Literal["yours", "shared"] | None = None


class Prerequisites(BaseModel):
    """Advisory, always: nothing anywhere is disabled by an unmet rule (D3)."""

    course_id: str
    link: CatalogueLink
    kinds: list[PrerequisiteKind]


class PrerequisitePreview(BaseModel):
    """The shared rule for a course you are about to add, judged against your
    record (item 7). Empty for a past term: a course already taken needs no
    warning. Only the shared version: there is no course yet to have yours."""

    catalogue: CatalogueCourse | None = None
    kinds: list[PrerequisiteKind] = []
