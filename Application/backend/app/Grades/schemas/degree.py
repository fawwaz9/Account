"""Schemas for the degree audit: requirements, course equivalences and the result.

Also the code and pattern readers the audit matches courses with.
"""
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

#: "CPSC 110", "CPSC_V 110", "cpsc110", "COSC 111A".
CODE = re.compile(r"^([A-Za-z]{2,5})(?:_[A-Za-z])?\s*(\d{3})([A-Za-z]?)$")
#: "CPSC 3xx", "3xx", "CPSC 300+", "300+", "CPSC".
PATTERN = re.compile(r"^(?:([A-Za-z]{2,5})(?:_[A-Za-z])?)?\s*(?:(\d)xx|(\d{3})\+)?$", re.IGNORECASE)


def parse_code(text: str) -> tuple[str, int] | None:
    """Return a course code as (subject, number), ignoring campus, case and spacing.

    Args:
        text: Text such as "CPSC 110", "cpsc_v110" or "COSC 111A".

    Returns:
        The upper-cased subject and the number as an int (a letter suffix is dropped),
        or None when the text is not a course code.
    """
    match = CODE.match(text.strip())
    if match is None:
        return None
    return match.group(1).upper(), int(match.group(2))


def parse_item(text: str) -> list[tuple[str | None, int, int]] | None:
    """Return a requirement item as alternatives: (subject or None, lowest, highest).

    "MATH 100 | MATH 180" (or "... or ...") is two exact alternatives; "CPSC 3xx" is
    CPSC 300-399; "300+" is any subject from 300 up; "CPSC" is any CPSC course.

    Args:
        text: One requirement item.

    Returns:
        One (subject, lowest number, highest number) per alternative, subject None for
        any subject; None when any part is unreadable.
    """
    parts = [part.strip() for part in re.split(r"\s*\|\s*|\s+or\s+", text.strip(), flags=re.IGNORECASE)]
    alternatives = []
    for part in parts:
        if not part:
            return None
        code = parse_code(part)
        if code is not None:
            alternatives.append((code[0], code[1], code[1]))
            continue
        match = PATTERN.match(part)
        if match is None or not any(match.groups()):
            return None
        subject, hundred, floor = match.groups()
        subject = subject.upper() if subject else None
        if hundred is not None:
            alternatives.append((subject, int(hundred) * 100, int(hundred) * 100 + 99))
        elif floor is not None:
            alternatives.append((subject, int(floor), 999))
        else:
            alternatives.append((subject, 0, 999))
    return alternatives


def _clean_items(items: list[str]) -> list[str]:
    """Return the non-blank items, stripped; raise ValueError if one is unreadable."""
    cleaned = [item.strip() for item in items if item.strip()]
    for item in cleaned:
        if parse_item(item) is None:
            raise ValueError(
                f'"{item}" is not a course code or pattern. Use e.g. CPSC 110, MATH 100 | MATH 180, '
                "CPSC 3xx, CPSC 300+, 300+ or CPSC"
            )
    return cleaned


class RequirementWrite(BaseModel):
    """Request body for creating or replacing a degree requirement.

    Attributes:
        name: Requirement name, 1-80 characters; stripped.
        kind: "courses" (every item must be met) or "credits" (`credits_needed` from
            matching courses).
        items: 1-60 codes or patterns (see `parse_item`); blanks are dropped.
        credits_needed: Credits required, above 0 and at most 200; required for
            "credits" and cleared for "courses".
        shares: True when a course counting here may count toward another requirement.
    """
    name: str = Field(..., min_length=1, max_length=80)
    kind: Literal["courses", "credits"]
    items: list[str] = Field(..., min_length=1, max_length=60)
    credits_needed: float | None = Field(default=None, gt=0, le=200)
    shares: bool = False

    @model_validator(mode="after")
    def _check(self):
        """Clean the name and items, and match `credits_needed` to the kind.

        Returns:
            The cleaned model.

        Raises:
            ValueError: If an item is unreadable, no item is left, or a "credits"
                requirement has no `credits_needed` (a 422).
        """
        self.name = self.name.strip()
        self.items = _clean_items(self.items)
        if not self.items:
            raise ValueError("A requirement needs at least one course or pattern")
        if self.kind == "credits" and self.credits_needed is None:
            raise ValueError("Say how many credits this requirement needs")
        if self.kind == "courses":
            self.credits_needed = None
        return self


class Requirement(BaseModel):
    """A stored degree requirement as the API returns it.

    Read back as stored and never re-validated, so a rule tightened later cannot make a
    saved row unreadable.

    Attributes:
        id: Requirement id.
        name: Requirement name.
        kind: "courses" or "credits".
        items: Codes or patterns, as stored.
        credits_needed: Credits required for a "credits" requirement; None otherwise.
        shares: Whether a course here may also count elsewhere.
        position: Display order.
        created_at: When it was created (naive UTC).
    """

    id: UUID
    name: str
    kind: str
    items: list[str]
    credits_needed: float | None = None
    shares: bool = False
    position: int
    created_at: datetime

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True


class EquivalenceWrite(BaseModel):
    """Request body for mapping courses taken onto the courses they count as.

    Attributes:
        from_codes: 1-10 course codes taken.
        counts_as: 1-10 course codes they count as.
        credits: Credits granted, above 0 and at most 60; None uses the sources' total.
        note: Free text, at most 200 characters.
    """
    from_codes: list[str] = Field(..., min_length=1, max_length=10)
    counts_as: list[str] = Field(..., min_length=1, max_length=10)
    credits: float | None = Field(default=None, gt=0, le=60)
    note: str | None = Field(default=None, max_length=200)

    @field_validator("from_codes", "counts_as")
    @classmethod
    def _codes(cls, codes: list[str]) -> list[str]:
        """Strip each code, drop blanks, and require at least one valid course code.

        Returns:
            The cleaned codes.

        Raises:
            ValueError: If a code is not a course code or none is left (a 422).
        """
        cleaned = [code.strip() for code in codes if code.strip()]
        for code in cleaned:
            if parse_code(code) is None:
                raise ValueError(f'"{code}" is not a course code, e.g. CPSC 110')
        if not cleaned:
            raise ValueError("Name at least one course")
        return cleaned


class Equivalence(BaseModel):
    """A stored course equivalence as the API returns it.

    Read back as stored and never re-validated, so a rule tightened later cannot make a
    saved row unreadable.

    Attributes:
        id: Equivalence id.
        from_codes: Codes taken.
        counts_as: Codes they count as.
        credits: Credits granted; None uses the sources' total.
        note: Free text, or None.
        created_at: When it was created (naive UTC).
    """

    id: UUID
    from_codes: list[str]
    counts_as: list[str]
    credits: float | None = None
    note: str | None = None
    created_at: datetime

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True


Status = Literal["completed", "in_progress", "planned"]
"""Where a counted course stands: done, under way, or planned for a later term."""


class Counted(BaseModel):
    """A course, or an equivalence for courses, counted toward a requirement.

    Attributes:
        label: How it is named, such as "CPSC 110".
        credits: Credits it carries.
        status: "completed", "in_progress" or "planned".
    """

    label: str
    credits: float
    status: Status


class ItemResult(BaseModel):
    """One item of a "courses" requirement and what meets it.

    Attributes:
        item: The item as entered.
        met_by: What meets it; None when nothing does yet.
    """
    item: str
    #: The course that meets it, or null when nothing does yet.
    met_by: Counted | None = None


class RequirementResult(BaseModel):
    """How far the student's record goes toward one requirement.

    Attributes:
        requirement: The requirement.
        items: For "courses": one line per item.
        counted: For "credits": everything counted, completed first.
        credits_completed: Counted credits from completed courses.
        credits_in_progress: Counted credits from courses under way.
        credits_planned: Counted credits from planned courses.
        done: Whether completed courses alone meet it.
    """
    requirement: Requirement
    #: "courses": one line per item.
    items: list[ItemResult] = Field(default_factory=list)
    #: "credits": everything counted, completed first.
    counted: list[Counted] = Field(default_factory=list)
    credits_completed: float = 0.0
    credits_in_progress: float = 0.0
    credits_planned: float = 0.0
    #: Met with completed courses alone.
    done: bool = False


class DegreeAudit(BaseModel):
    """The whole degree audit for one student.

    Attributes:
        requirements: Each requirement's result, in display order.
        equivalences: The student's course equivalences.
        credits_completed: Credits completed overall.
        credits_in_progress: Credits under way overall.
        credit_target: Credits the degree needs.
        not_counted: Completed courses no requirement used: electives, or a missing
            mapping.
        failed: Labels of courses that did not pass, which count nowhere.
    """
    requirements: list[RequirementResult]
    equivalences: list[Equivalence]
    credits_completed: float
    credits_in_progress: float
    credit_target: int
    #: Completed courses no requirement used: electives, or a mapping missing.
    not_counted: list[Counted] = Field(default_factory=list)
    #: Courses that did not pass, which count nowhere.
    failed: list[str] = Field(default_factory=list)
