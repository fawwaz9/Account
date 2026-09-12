from datetime import date

from pydantic import BaseModel, Field


class TimingWindow(BaseModel):
    """How early or late work was finished over one stretch of time.

    Both headline readings are here on purpose, because each hides what the
    other shows. The signed mean carries magnitude but lets a fortnight late
    cancel against a fortnight early; the on-time share cannot be skewed by one
    forgotten task but counts a day late and a month late the same. Neither is
    the honest number on its own.
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
    """The two windows the tasks page shows.

    A rolling week answers "how am I doing right now" and a calendar month gives
    it something steadier to sit against, since one bad Tuesday moves a week a
    long way. Both are bucketed by when work was *finished*, not when it was
    due -- the question is about recent behaviour, and bucketing by due date
    would put a task finished today into last month.
    """

    past_week: TimingWindow
    this_month: TimingWindow
    #: Completed tasks with no due date, which no figure above counts. Reported
    #: so a student whose tasks are mostly undated can see why the sample is
    #: small, rather than mistrusting the number.
    undated_completed: int = Field(default=0)
