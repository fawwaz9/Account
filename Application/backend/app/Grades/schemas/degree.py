"""The degree audit: requirements you enter, equivalences you map, and the result."""
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
    """A course code as (subject, number): campus suffix, case and spacing set aside."""
    match = CODE.match(text.strip())
    if match is None:
        return None
    return match.group(1).upper(), int(match.group(2))


def parse_item(text: str) -> list[tuple[str | None, int, int]] | None:
    """An item as alternatives, each (subject or None, lowest number, highest).

    "MATH 100 | MATH 180" is two exact alternatives; "CPSC 3xx" is CPSC 300-399;
    "300+" is any subject from 300 up; "CPSC" is any CPSC course. None when any
    part is unreadable.
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
    cleaned = [item.strip() for item in items if item.strip()]
    for item in cleaned:
        if parse_item(item) is None:
            raise ValueError(
                f'"{item}" is not a course code or pattern. Use e.g. CPSC 110, MATH 100 | MATH 180, '
                "CPSC 3xx, CPSC 300+, 300+ or CPSC"
            )
    return cleaned


class RequirementWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    kind: Literal["courses", "credits"]
    items: list[str] = Field(..., min_length=1, max_length=60)
    credits_needed: float | None = Field(default=None, gt=0, le=200)
    shares: bool = False

    @model_validator(mode="after")
    def _check(self):
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
    """A stored requirement, read as it is: never re-validated, so a rule
    tightened later can't make a saved row unreadable."""

    id: UUID
    name: str
    kind: str
    items: list[str]
    credits_needed: float | None = None
    shares: bool = False
    position: int
    created_at: datetime

    class Config:
        from_attributes = True


class EquivalenceWrite(BaseModel):
    from_codes: list[str] = Field(..., min_length=1, max_length=10)
    counts_as: list[str] = Field(..., min_length=1, max_length=10)
    credits: float | None = Field(default=None, gt=0, le=60)
    note: str | None = Field(default=None, max_length=200)

    @field_validator("from_codes", "counts_as")
    @classmethod
    def _codes(cls, codes: list[str]) -> list[str]:
        cleaned = [code.strip() for code in codes if code.strip()]
        for code in cleaned:
            if parse_code(code) is None:
                raise ValueError(f'"{code}" is not a course code, e.g. CPSC 110')
        if not cleaned:
            raise ValueError("Name at least one course")
        return cleaned


class Equivalence(BaseModel):
    """A stored equivalence, read as it is (see Requirement)."""

    id: UUID
    from_codes: list[str]
    counts_as: list[str]
    credits: float | None = None
    note: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


Status = Literal["completed", "in_progress", "planned"]


class Counted(BaseModel):
    """A course (or an equivalence standing in for courses) counted toward a requirement."""

    label: str
    credits: float
    status: Status


class ItemResult(BaseModel):
    item: str
    #: The course that meets it, or null when nothing does yet.
    met_by: Counted | None = None


class RequirementResult(BaseModel):
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
    requirements: list[RequirementResult]
    equivalences: list[Equivalence]
    credits_completed: float
    credits_in_progress: float
    credit_target: int
    #: Completed courses no requirement used: electives, or a mapping missing.
    not_counted: list[Counted] = Field(default_factory=list)
    #: Courses that did not pass, which count nowhere.
    failed: list[str] = Field(default_factory=list)
