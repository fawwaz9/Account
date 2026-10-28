"""Schemas for recording that a module was visited."""

from enum import Enum

from pydantic import BaseModel


class Module(str, Enum):
    """The app's modules as the sidebar names them; what a visit is a visit to."""

    DASHBOARD = "dashboard"
    GRADES = "grades"
    CALENDAR = "calendar"
    TASKS = "tasks"
    JOBS = "jobs"
    BUDGET = "budget"
    SETTINGS = "settings"


class VisitCreate(BaseModel):
    """Request body recording one visit to a module.

    Attributes:
        module: The module visited.
        prompted: True when the visit came from a notification tapped in the last half
            hour; counted separately from an unprompted visit.
    """
    module: Module
    #: Opened from a notification (within half an hour of tapping one). The
    #: universe test needs a room visited unprompted, and a visit a notification
    #: caused is the metric manufacturing itself (account-vision.md §13.2).
    prompted: bool = False
