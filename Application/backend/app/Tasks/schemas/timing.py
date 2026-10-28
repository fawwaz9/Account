"""Response bodies for completion timing: how early or late tasks get finished.

`timing_service` compares each completed task's local completion date with its
due date, over a rolling week and over the calendar month to date.
"""

from datetime import date

from pydantic import BaseModel, Field


class TimingWindow(BaseModel):
    """How early or late the work finished within one window was.

    The signed mean and the on-time share come together because each hides what the
    other shows: one late fortnight can cancel an early one in the mean, while the
    share counts a day late the same as a month late.

    Attributes:
        label: "Past week" or "This month".
        starts_on: First day of the window.
        ends_on: Last day of the window, the user's today.
        counted: Dated tasks finished in the window.
        mean_days: Mean days from due date to completion, signed (positive is
            late, negative early), 1 dp; None when nothing was counted.
        on_time_percent: Share finished on or before the due date, as a
            percentage to 1 dp; None when nothing was counted.
        early_count: How many were finished before their due date.
        early_mean_days: Mean days early among those, as a positive number; None
            when there were none.
        late_count: How many were finished after their due date.
        late_mean_days: Mean days late among those, as a positive number; None
            when there were none.
    """

    label: str
    starts_on: date
    ends_on: date
    #: Completed tasks that carried a due date. Undated work is excluded: there
    #: is nothing to be early or late against.
    counted: int = 0
    #: Days from the due date, signed -- positive late, negative early. Null when
    #: nothing was completed in the window, rather than a zero that would read as
    #: a week of punctual work.
    mean_days: float | None = None
    #: Finished on or before the due date, as a percentage of `counted`.
    on_time_percent: float | None = None
    early_count: int = 0
    #: Days early, as a positive number, across the early ones only.
    early_mean_days: float | None = None
    late_count: int = 0
    #: Days late, as a positive number, across the late ones only.
    late_mean_days: float | None = None


class CompletionTiming(BaseModel):
    """The two timing windows the tasks page shows.

    Both bucket tasks by the local date they were finished, not the date they were
    due.

    Attributes:
        past_week: The last seven days, today included.
        this_month: The calendar month to date.
        undated_completed: Tasks with no due date finished in either window,
            which no figure above counts.
    """

    past_week: TimingWindow
    this_month: TimingWindow
    #: Completed tasks with no due date, which no figure above counts. Reported
    #: so a student whose tasks are mostly undated can see why the sample is
    #: small, rather than mistrusting the number.
    undated_completed: int = Field(default=0)
