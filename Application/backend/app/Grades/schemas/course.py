"""Request and response schemas for courses, their links and their category weights."""

from datetime import date
from uuid import UUID, uuid4
from typing import List
from pydantic import BaseModel, Field, field_validator, model_validator

from app.Grades.schemas.grade import Grade
from app.Grades.utils.enums import GradeCategory, Semester
from app.Grades.utils.ordering import sorted_grades
from app.shared.errors import MAX_TOTAL_WEIGHT, weight_error

#: Schemes a course link may use. An allowlist rather than a denylist, because
#: the interesting ones are the ones nobody thought of.
#:
#: This is not theoretical tidiness: these are rendered as anchors on the course
#: page, and a stored `javascript:` URL is script execution on your own page the
#: next time you click your own link. `data:` is the same hole wearing a hat.
#: Checked here rather than only in the client, since the API is reachable
#: without it.
ALLOWED_LINK_SCHEMES: frozenset[str] = frozenset({"http", "https"})

#: Enough for a long Canvas deep link, short of somebody pasting a document into
#: the field.
MAX_LINK_URL = 500


class CourseLink(BaseModel):
    """One place a course lives online, such as Canvas or a syllabus.

    Attributes:
        title: Link name, 1-40 characters; stripped.
        url: Address, at most `MAX_LINK_URL` characters; a bare domain gets `https://`,
            and only http and https are accepted.
    """

    title: str = Field(..., min_length=1, max_length=40)
    url: str = Field(..., min_length=1, max_length=MAX_LINK_URL)

    @model_validator(mode="after")
    def validate_link(self):
        """Strip both fields, add `https://` to a bare domain, allow only http(s).

        Returns:
            The cleaned link.

        Raises:
            ValueError: If the name or address is blank, or the scheme is not http or
                https
                (a 422).
        """
        self.title = self.title.strip()
        self.url = self.url.strip()

        if not self.title:
            raise ValueError("A link needs a name")
        if not self.url:
            raise ValueError("A link needs an address")

        # A pasted bare domain is the likeliest mistake and the only unambiguous
        # one, so it is fixed rather than refused. Anything carrying a scheme is
        # taken at its word and checked -- "javascript:alert(1)" has a colon, so
        # it lands in the check below rather than becoming
        # "https://javascript:alert(1)".
        if ":" not in self.url:
            self.url = f"https://{self.url}"

        scheme, _, rest = self.url.partition(":")
        if not rest or scheme.lower() not in ALLOWED_LINK_SCHEMES:
            raise ValueError("A link must start with http:// or https://")

        return self


def clean_links(links: list["CourseLink"] | None) -> list[dict]:
    """Return links as plain dicts for the JSON column, dropping exact duplicates.

    Args:
        links: Validated links; None means none.

    Returns:
        `{"title", "url"}` dicts in order; a link whose title and url both match an
        earlier one, ignoring case, is dropped, while a repeated title alone is kept.
    """
    seen: set[tuple[str, str]] = set()
    cleaned: list[dict] = []
    for link in links or []:
        key = (link.title.lower(), link.url.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"title": link.title, "url": link.url})
    return cleaned


def clean_section(value: str | None) -> str | None:
    """Return a section stripped, or None when it is missing or blank.

    Args:
        value: The submitted section, such as "101"; may be None.

    Returns:
        The trimmed section, or None.
    """
    if value is None:
        return None
    value = value.strip()
    return value or None


def default_category_weights() -> dict[GradeCategory, float]:
    """Return every grade category with a weight of 0.

    Returns:
        A weight of 0.0 for every `GradeCategory`.
    """
    return dict.fromkeys(GradeCategory, 0.0)

def normalize_category_weights(
    weights: dict[GradeCategory, float] | None
) -> dict[GradeCategory, float]:
    """Return a checked weight for every category, the given ones over zeros.

    Args:
        weights: Category to weight percentage; None or missing categories get 0.

    Returns:
        Every `GradeCategory` mapped to its weight.

    Raises:
        ValueError: If a weight is outside 0-100 or the total exceeds
            `MAX_TOTAL_WEIGHT`.
    """
    normalized = default_category_weights()
    if weights:
        normalized.update(weights)

    for weight in normalized.values():
        if weight < 0 or weight > 100:
            raise ValueError(weight_error["invalid_weight_value"])

    total_weight = sum(normalized.values())
    if total_weight > MAX_TOTAL_WEIGHT:
        raise ValueError(weight_error["invalid_weights"])

    return normalized

class CourseBase(BaseModel):
    """A course's fields and the rules a complete course must satisfy.

    Attributes:
        code: Course code, 3-20 characters, not blank; unique per user.
        name: Course title, 1-100 characters, not blank.
        year: School year, 1-10.
        semester: The term of the school year.
        credits: Credit value, 0.5-10; 3 by default.
        required: True for a requirement, False for an elective.
        professor: Instructor's name, at most 100 characters.
        section: Section, at most 20 characters; blank is stored as null.
        final_grade: Final percentage, 0-100; 0 means none recorded, and a transfer
            credit may not carry one.
        target_grade: Target percentage, 0-100; null uses the account default.
        category_weights: Category to weight percentage, each 0-100, total at most
            `MAX_TOTAL_WEIGHT`; missing categories become 0.
        start_date: First day of the course.
        end_date: Last day of the course; not before `start_date`.
        no_final: The course has no final exam.
        transfer_credit: Credit granted without taking the course; counts credits only.
        archived: Kept and averaged, but not counted toward credits completed.
        links: At most 20 links.
    """
    code: str = Field(..., min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str = Field(..., min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int = Field(..., ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester = Field(..., description="The semester in which the course is offered")
    credits: float = Field(default=3.0, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool = Field(default=True, description="Indicates if the course is required or elective")
    professor: str | None = Field(default=None, max_length=100, description="The name of the professor teaching the course")
    section: str | None = Field(default=None, max_length=20, description="The section you are in, e.g. 101 or L2B")
    final_grade: float = Field(default=0.0, ge=0, le=100, description="The final grade for the course submitted by the professor")
    target_grade: float | None = Field(default=None, ge=0, le=100, description="The grade you are aiming for; null uses the account default")
    category_weights: dict[GradeCategory, float] = Field(default_factory=default_category_weights, description="Weights by grade category")
    # Typed as date, not str: the column is Column(Date), and Pydantic v2 will not
    # coerce a date into a str -- it raises. Serialization still emits ISO strings.
    start_date: date | None = Field(default=None, description="The date the course starts")
    end_date: date | None = Field(default=None, description="The date the course ends")
    # Three independent flags rather than one status, because they combine: a
    # transfer credit can also be archived.
    no_final: bool = Field(default=False, description="No final exam, so a missing final grade is not a problem to act on")
    transfer_credit: bool = Field(default=False, description="Credit granted without taking the course; contributes credits and no grade")
    archived: bool = Field(default=False, description="Still searchable and still in the average, but no longer counted toward credits completed")
    links: list[CourseLink] = Field(default_factory=list, max_length=20, description="Where this course lives: Canvas, Piazza, a syllabus")

    @model_validator(mode="after")
    def validate_course_logic(self):
        """Enforce the cross-field rules of a complete course and normalise its weights.

        Returns:
            The model with its section cleaned and every category weighted.

        Raises:
            ValueError: If the code or name is blank, the end date is before the start,
                a transfer credit has a final grade, or a weight is out of range (a
                422).
        """
        if self.code.strip() == "":
            raise ValueError("course code cannot be empty")

        if self.name.strip() == "":
            raise ValueError("course name cannot be empty")

        self.section = clean_section(self.section)

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end date cannot be before start date")

        # Nothing is marked in a transfer credit, so a final grade on one is a
        # contradiction rather than a value to store and then have to explain
        # every time an average leaves it out.
        if self.transfer_credit and self.final_grade:
            raise ValueError("A transfer credit carries credits, not a grade")

        self.category_weights = normalize_category_weights(self.category_weights)
        return self

class CourseCreate(CourseBase):
    """Request body for adding a course; the fields and rules of `CourseBase`."""
    pass

class CategoryWeightsUpdate(BaseModel):
    """Request body replacing a course's category weights.

    Attributes:
        category_weights: Category to weight percentage, each 0-100, total at most
            `MAX_TOTAL_WEIGHT`.
    """
    category_weights: dict[GradeCategory, float] = Field(..., description="Category weights to update")

    @model_validator(mode="after")
    def validate_category_weights(self):
        """Check each weight is 0-100 and the total is at most `MAX_TOTAL_WEIGHT`.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If a weight or the total is out of range (a 422).
        """
        total = 0.0
        for weight in self.category_weights.values():
            if weight < 0 or weight > 100:
                raise ValueError(weight_error["invalid_weight_value"])
            total += weight

        if total > MAX_TOTAL_WEIGHT:
            raise ValueError(weight_error["invalid_weights"])

        return self

class CourseUpdate(BaseModel):
    """Request body for editing a course; omitted fields stay as they are.

    Per-field limits only, plus the weights and a start and end date sent together;
    the merged course is not re-checked (see `CourseBase` for the full rules).

    Attributes:
        code: New code, 3-20 characters.
        name: New title, 1-100 characters.
        year: New school year, 1-10.
        semester: New term.
        credits: New credit value, 0.5-10.
        required: Requirement or elective.
        professor: New instructor name, at most 100 characters.
        section: New section; "" clears it.
        final_grade: New final percentage, 0-100.
        target_grade: New target, 0-100; null falls back to the account default.
        category_weights: New weights, each 0-100, total at most `MAX_TOTAL_WEIGHT`.
        start_date: New first day.
        end_date: New last day; checked against `start_date` only if both are sent.
        no_final: Whether the course has no final exam.
        transfer_credit: Whether the course is transfer credit.
        archived: Whether the course is archived.
        links: The whole new list of links, at most 20; replaces the old one.
    """
    code: str | None = Field(default=None, min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str | None = Field(default=None, min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int | None = Field(default=None, ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester | None = Field(default=None, description="The semester in which the course is offered")
    credits: float | None = Field(default=None, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool | None = Field(default=None, description="Indicates if the course is required or elective")
    professor: str | None = Field(default=None, max_length=100, description="The name of the professor teaching the course")
    section: str | None = Field(default=None, max_length=20, description="The section you are in, e.g. 101 or L2B")
    final_grade: float | None = Field(default=None, ge=0, le=100, description="The final grade for the course submitted by the professor")
    target_grade: float | None = Field(default=None, ge=0, le=100, description="The grade you are aiming for; null uses the account default")
    category_weights: dict[GradeCategory, float] | None = Field(default=None, description="Weights by grade category")
    start_date: date | None = Field(default=None, description="The date the course starts")
    end_date: date | None = Field(default=None, description="The date the course ends")
    no_final: bool | None = Field(default=None, description="No final exam, so a missing final grade is not a problem to act on")
    transfer_credit: bool | None = Field(default=None, description="Credit granted without taking the course; contributes credits and no grade")
    archived: bool | None = Field(default=None, description="Still searchable and still in the average, but no longer counted toward credits completed")
    #: Sent whole, never patched entry by entry. The list is small and ordered,
    #: and a per-entry API would need ids the JSON column does not carry.
    links: list[CourseLink] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_course_update(self):
        """Clean a sent section and check sent weights and a sent date pair.

        Returns:
            The model, with the section cleaned if it was sent.

        Raises:
            ValueError: If a weight or the total is out of range, or both dates are sent
                with the end before the start (a 422).
        """
        # Sent as "" to clear it, which is stored as null like any other unset
        # section. Only when sent: assigning a field marks it as set, and an
        # unsent section would then be cleared by every edit that omits it.
        if "section" in self.model_fields_set:
            self.section = clean_section(self.section)

        if self.category_weights is not None:
            total = 0.0
            for weight in self.category_weights.values():
                if weight < 0 or weight > 100:
                    raise ValueError(weight_error["invalid_weight_value"])
                total += weight

            if total > MAX_TOTAL_WEIGHT:
                raise ValueError(weight_error["invalid_weights"])

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end date cannot be before start date")

        return self

class Course(CourseBase):
    """A course as the API returns it, with figures the server computes.

    Inherits `CourseBase` and its validator, so every stored course is re-checked on
    the way out.

    Attributes:
        id: The course's id.
        average: Current average, read from the attached `reported_average`; null
            when nothing is marked.
        letter_grade: Letter grade for the average on the user's scale.
        grade_points: Grade points for the average on the user's scale.
        term_bucket: "past", "current" or "future" relative to the student's term.
        counting_scheme_id: The grading scheme picked as the grade; null uses the
            course's own weights.
        projected_before_final: The projection just before the final was marked; set by
            the server only.
        projected_on: The day that projection was taken.
    """
    id: UUID = Field(default_factory=uuid4)
    #: Null when the course has no marked work, rather than 0.0.
    #:
    #: Zero is a real grade and "not marked yet" is not, and reporting the
    #: second as the first makes a course you have not started read as a
    #: course you are failing. Same reason the cumulative average is nullable.
    #:
    #: Read from `reported_average`, which the service attaches, specifically so
    #: that deciding what to report never means assigning to the mapped
    #: `average` column -- a read that writes is one stray commit from a GET
    #: that changes data.
    average: float | None = Field(default=None, validation_alias="reported_average")
    # Both computed server-side so one grade scale and one term comparison
    # serve the list, the course page, and search alike.
    letter_grade: str = Field(default="", description="Letter grade for the current average")
    grade_points: float = Field(default=0.0, description="Grade points on the configured scale")
    term_bucket: str = Field(
        default="current",
        description="past, current, or future, relative to the student's term",
    )
    #: The grading scheme that is this course's grade, when one was picked
    #: (Phase 1 D25). Null: the course's own weights are the grade.
    counting_scheme_id: UUID | None = None
    #: The last projection before the final, and the day it stood (Phase 1
    #: D34). Set by the server only: not on CourseUpdate.
    projected_before_final: float | None = None
    projected_on: date | None = None

    class Config:
        """Pydantic v1-style settings: read attributes; accept `average` by name."""
        from_attributes = True
        # So `Course(average=...)` still works by field name alongside the alias.
        populate_by_name = True

class CourseDetail(Course):
    """A course with its grades and per-category figures, for the course page.

    Attributes:
        grades: The course's grades in display order (see `grade_sort_key`).
        category_averages: Point-weighted average per category, 0-100.
        category_points: Marks each category contributes, out of its weight.
    """
    grades: List[Grade] =  Field(default_factory=list)

    # Ordered here rather than at every call site that builds one of these, so a
    # new path cannot forget. See `grade_sort_key` for why it is not a plain
    # string sort: three names in use start lowercase, and a third are numbered.
    @field_validator("grades")
    @classmethod
    def order_grades(cls, grades: List[Grade]) -> List[Grade]:
        """Return the grades in display order.

        Args:
            grades: The course's grades as loaded.

        Returns:
            The same grades sorted by `sorted_grades`.
        """
        return sorted_grades(grades)
    # Point-weighted average per category, computed server-side so the client
    # renders one authoritative number instead of reimplementing the formula.
    # Defaults to empty so any path that does not populate it still serializes.
    category_averages: dict[GradeCategory, float] = Field(
        default_factory=dict,
        description="Current average per category, 0-100",
    )
    #: What each category contributes, in marks out of its weight. Sent rather
    #: than derived: deriving it meant multiplying the rounded average above by
    #: the weight, a second rounding that showed 11.82 for an exact 11.825.
    category_points: dict[GradeCategory, float] = Field(
        default_factory=dict,
        description="Marks each category contributes, out of its weight",
    )

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True
