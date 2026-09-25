from enum import Enum


class DisplayStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    STALE = "STALE"
    COMMITTED = "COMMITTED"
    CLEAN = "CLEAN"
    ERROR = "ERROR"


def classify_status(
    dirty: bool,
    age_seconds: float | None,
    ahead: int,
    git_error: bool,
    active_seconds: int = 60,
    stale_seconds: int = 600,
) -> DisplayStatus:
    if git_error:
        return DisplayStatus.ERROR
    if dirty:
        if age_seconds is None:
            return DisplayStatus.IDLE
        if age_seconds <= active_seconds:
            return DisplayStatus.ACTIVE
        if age_seconds <= stale_seconds:
            return DisplayStatus.IDLE
        return DisplayStatus.STALE
    if ahead > 0:
        return DisplayStatus.COMMITTED
    return DisplayStatus.CLEAN


STATUS_COLORS = {
    DisplayStatus.ACTIVE: "#B7E4C7",
    DisplayStatus.IDLE: "#FFE8A1",
    DisplayStatus.STALE: "#FFD6A5",
    DisplayStatus.COMMITTED: "#BDE0FE",
    DisplayStatus.CLEAN: "#E9ECEF",
    DisplayStatus.ERROR: "#FFADAD",
}
