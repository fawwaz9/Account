"""Schemas for the shared course catalogue as a course page sees it."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogueCourse(BaseModel):
    """A course as the university offers it; the same for everyone.

    Attributes:
        id: Catalogue course id.
        campus: "UBCV" or "UBCO".
        subject: Subject code, such as "CPSC".
        number: Course number as text, such as "210".
        title: Course title, or None.
        credits: Credit value, or None.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campus: str
    subject: str
    number: str
    title: str | None = None
    credits: float | None = None


class CatalogueLink(BaseModel):
    """Which catalogue course one of the student's courses is, and how that was decided.

    Attributes:
        how: "chosen" (picked by hand), "matched" (automatic by campus and code),
            "none_chosen" (the student said there is none) or "not_found" (automatic,
            no single match yet).
        course: The linked catalogue course; None for "none_chosen" and "not_found".
    """

    how: Literal["chosen", "matched", "none_chosen", "not_found"]
    course: CatalogueCourse | None = None


class CatalogueChoice(BaseModel):
    """Request body setting a course's catalogue link: automatic, chosen, or none.

    Attributes:
        mode: "auto", "chosen" or "none".
        catalogue_course_id: The chosen catalogue course; given exactly when `mode` is
            "chosen".
    """

    mode: Literal["auto", "chosen", "none"]
    catalogue_course_id: UUID | None = Field(default=None)

    @model_validator(mode="after")
    def id_only_when_chosen(self):
        """Require a catalogue course id exactly when the mode is "chosen".

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If an id comes with another mode, or "chosen" comes without one
                (a 422).
        """
        if (self.mode == "chosen") != (self.catalogue_course_id is not None):
            raise ValueError("A catalogue course is given exactly when the mode is 'chosen'")
        return self
