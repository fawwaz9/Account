"""Course-page prerequisite schemas: the student's rule, the shared one, the verdict."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.Grades.schemas.catalogue import CatalogueCourse, CatalogueLink

Kind = Literal["prerequisite", "corequisite"]
"""The kind of a rule: before the course, or alongside it."""
Status = Literal["met", "on_track", "not_met"]
"""A rule's verdict."""


class RuleWrite(BaseModel):
    """Request body for the student's own rule, typed or as a tree (exactly one).

    Attributes:
        kind: "prerequisite" or "corequisite".
        text: The typed form, such as "CPSC 210 and one of MATH 200, MATH 217"; at most
            300 characters.
        rule: The rule as a JSON tree.
        note: What the rule cannot say, such as year standing; at most 300 characters,
            blank becomes None.
    """

    kind: Kind = "prerequisite"
    text: str | None = Field(default=None, max_length=300)
    rule: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def one_form(self):
        """Require exactly one of `text` and `rule`; a blank note becomes None.

        Returns:
            The validated model.

        Raises:
            ValueError: If both or neither are given (a 422).
        """
        if (self.text is None) == (self.rule is None):
            raise ValueError("Give the rule as text or as a tree, not both")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class RuleText(BaseModel):
    """Request body for checking a typed rule without saving it.

    Attributes:
        text: The typed form, at most 300 characters.
    """
    text: str = Field(..., max_length=300)


class RuleChecked(BaseModel):
    """A typed rule read back: the tree, and the text it will be shown as.

    Attributes:
        rule: The validated tree.
        text: The tree rendered back into the typed form.
    """

    rule: dict[str, Any]
    text: str


class RuleResult(BaseModel):
    """The verdict on a rule or one of its parts.

    Attributes:
        status: "met", "on_track" or "not_met".
        text: The part in its typed form.
        detail: Why, for a leaf, such as "3 of 6 credits".
        parts: The verdicts of a group's parts.
        group: "all" or "any" for a group; None for a leaf.
    """
    status: Status
    text: str
    detail: str = ""
    parts: list[RuleResult] = []
    group: Literal["all", "any"] | None = None


class PrerequisiteSide(BaseModel):
    """One version of a rule, where it came from, and whether the student meets it.

    Attributes:
        source: "typed" or "syllabus" for the student's own; "reviewed" or
            "ubc-calendar" for the shared one.
        rule: The rule tree.
        text: The rule in its typed form.
        note: What the tree cannot say, or None.
        session: Calendar session the rule is from, such as "2026W", or None.
        source_text: The student's own syllabus sentence on theirs, the calendar's on a
            "ubc-calendar" row, never anyone else's.
        review: Where the student's rule stands in the owner's review; None for the
            shared one.
        result: The verdict against the student's record.
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
    """The prerequisite or co-requisite of one course, in both versions.

    Attributes:
        kind: "prerequisite" or "corequisite".
        yours: The student's own rule, or None.
        shared: The shared catalogue rule, or None.
        applies: Which version counts: "yours" whenever there is one, else "shared";
            None when neither exists.
    """

    kind: Kind
    yours: PrerequisiteSide | None = None
    shared: PrerequisiteSide | None = None
    applies: Literal["yours", "shared"] | None = None


class Prerequisites(BaseModel):
    """Every rule for one course; advisory only, nothing is ever blocked by it.

    Attributes:
        course_id: The course's id, as a string.
        link: The course's catalogue link.
        kinds: One entry per kind of rule.
    """

    course_id: str
    link: CatalogueLink
    kinds: list[PrerequisiteKind]


class PrerequisitePreview(BaseModel):
    """The shared rules for a course about to be added, judged against the record.

    Empty for a past term, and only the shared version, since there is no course yet to
    carry the student's own.

    Attributes:
        catalogue: The matching catalogue course, or None.
        kinds: One entry per kind of shared rule.
    """

    catalogue: CatalogueCourse | None = None
    kinds: list[PrerequisiteKind] = []
