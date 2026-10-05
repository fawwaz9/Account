from enum import Enum

from pydantic import BaseModel


class Module(str, Enum):
    """The rooms, as the sidebar names them. What a visit is a visit to."""

    DASHBOARD = "dashboard"
    GRADES = "grades"
    CALENDAR = "calendar"
    TASKS = "tasks"
    JOBS = "jobs"
    BUDGET = "budget"
    SETTINGS = "settings"


class VisitCreate(BaseModel):
    module: Module
    #: Opened from a notification (within half an hour of tapping one). The
    #: universe test needs a room visited unprompted, and a visit a notification
    #: caused is the metric manufacturing itself (account-vision.md §13.2).
    prompted: bool = False
