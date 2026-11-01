"""Request and response bodies for the term simulator (Phase 4 item 9, §13.19).

The capstone: the three rooms' projections over one 168-hour week. The rule that
does not bend (§13.5, §13.19): moving the work slider reports time fit only, and
anything academic renders solely from study hours the student sets directly.
"""

from pydantic import BaseModel, Field

#: Hours in a week.
WEEK_HOURS = 168


class TermDefaults(BaseModel):
    """Where each slider starts: the student's own figures for the weeks ahead.

    Attributes:
        sleep_hours: A night; 8 unless changed.
        class_hours: Lectures, labs and discussions a week, averaged over the next
            four weeks.
        study_hours: Estimated work on tasks due a week, averaged the same way.
        work_hours: Scheduled shifts a week, averaged the same way.
        workouts_per_week: Activities a week over the last four weeks.
        workout_minutes: Their average length; 45 with none logged.
        overhead_hours: Meals, travel, chores a day; 3 unless changed.
        exertion_goal: The weekly exertion goal, if one is set.
    """
    sleep_hours: float = 8.0
    class_hours: float = 0.0
    study_hours: float = 0.0
    work_hours: float = 0.0
    workouts_per_week: float = 0.0
    workout_minutes: float = 45.0
    overhead_hours: float = 3.0
    exertion_goal: int | None = None


class TermIn(BaseModel):
    """One simulated week of the term.

    Attributes:
        sleep_hours: A night, 4 to 12.
        class_hours: A week, 0 to 60.
        study_hours: A week, 0 to 80, set directly; None means "not set", and then no
            academic figure renders (§13.19).
        work_hours: A week, 0 to 60; None means as scheduled.
        workouts_per_week: 0 to 14.
        workout_minutes: Each, 10 to 240.
        overhead_hours: A day, 0 to 12.
        monthly_spending_change: Dollars a month more or less, -10,000 to 10,000.
    """
    sleep_hours: float = Field(default=8.0, ge=4, le=12)
    class_hours: float = Field(default=0.0, ge=0, le=60)
    study_hours: float | None = Field(default=None, ge=0, le=80)
    work_hours: float | None = Field(default=None, ge=0, le=60)
    workouts_per_week: float = Field(default=0.0, ge=0, le=14)
    workout_minutes: float = Field(default=45.0, ge=10, le=240)
    overhead_hours: float = Field(default=3.0, ge=0, le=12)
    monthly_spending_change: float = Field(default=0.0, ge=-10_000, le=10_000)


class RoomHours(BaseModel):
    """One room's share of the week.

    Attributes:
        room: "academic", "money", "body" or "life".
        label: How it reads.
        hours: Hours a week.
    """
    room: str
    label: str
    hours: float


class TimeFit(BaseModel):
    """The 168-hour week.

    Attributes:
        rooms: Each room's hours.
        total: Their sum.
        fits: True when the total is at most 168.
        short_by: Hours over 168; 0 when it fits.
        spare: Hours under 168; 0 when it doesn't fit.
    """
    rooms: list[RoomHours]
    total: float
    fits: bool
    short_by: float = 0.0
    spare: float = 0.0


class MoneyFit(BaseModel):
    """The year plan with the work hours and spending of the scenario.

    Attributes:
        baseline_ending: The plan's ending balance as it stands.
        scenario_ending: With the scenario's hours and spending.
        difference: The second less the first.
        lowest: The scenario's lowest balance.
        negative_on: The scenario's first day below zero, if any.
        notes: Caps and assumptions from the money side.
    """
    baseline_ending: float
    scenario_ending: float
    difference: float
    lowest: float
    negative_on: str | None = None
    notes: list[str] = Field(default_factory=list)


class BodyFit(BaseModel):
    """Exertion from the scenario's workouts.

    Attributes:
        points_per_week: Points the workouts would earn, at your usual effort.
        goal: The weekly goal, if set.
        meets_goal: Whether they reach it; None with no goal.
    """
    points_per_week: int
    goal: int | None = None
    meets_goal: bool | None = None


class CourseBand(BaseModel):
    """Where a current course can still finish, as it stands today.

    Attributes:
        code: The course.
        current: Its grade now.
        best: With everything left at full marks.
        worst: With everything left at zero.
    """
    code: str
    current: float
    best: float
    worst: float


class AcademicFit(BaseModel):
    """What the study hours you set cover. Absent unless study hours are set directly.

    Attributes:
        study_hours: The hours you set.
        estimated_hours: What your tasks are estimated at a week, for the same weeks.
        coverage: Study over estimate, as a percentage; None with no estimate.
        reading: In words: covered, or how far short.
        bands: Each current course's band as it stands; the simulator never moves it.
    """
    study_hours: float
    estimated_hours: float
    coverage: float | None = None
    reading: str
    bands: list[CourseBand] = Field(default_factory=list)


class TermResult(BaseModel):
    """The simulated week across the rooms.

    Attributes:
        time: The 168-hour fit, per room.
        money: The year plan with this week's work and spending.
        body: Exertion from the workouts.
        academic: Present only when study hours were set directly (§13.19).
        assumptions: Every assumption, in words.
    """
    time: TimeFit
    money: MoneyFit | None = None
    body: BodyFit
    academic: AcademicFit | None = None
    assumptions: list[str] = Field(default_factory=list)
