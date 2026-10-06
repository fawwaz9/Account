"""The shared course catalogue as the course page sees it (Phase 2 item 3)."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogueCourse(BaseModel):
    """A course as the school offers it. World knowledge: the same for everyone."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campus: str
    subject: str
    number: str
    title: str | None = None
    credits: float | None = None


class CatalogueLink(BaseModel):
    """Which catalogue course a course of yours is, and how that was decided.

    * ``chosen`` -- you picked it.
    * ``matched`` -- automatic, by campus and code.
    * ``none_chosen`` -- you said there is none.
    * ``not_found`` -- automatic, and the catalogue has no single match yet.
    """

    how: Literal["chosen", "matched", "none_chosen", "not_found"]
    course: CatalogueCourse | None = None


class CatalogueChoice(BaseModel):
    """Set the link: back to automatic, to a course you pick, or to none."""

    mode: Literal["auto", "chosen", "none"]
    catalogue_course_id: UUID | None = Field(default=None)

    @model_validator(mode="after")
    def id_only_when_chosen(self):
        if (self.mode == "chosen") != (self.catalogue_course_id is not None):
            raise ValueError("A catalogue course is given exactly when the mode is 'chosen'")
        return self
