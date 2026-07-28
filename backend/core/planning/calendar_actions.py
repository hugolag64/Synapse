"""Pure helpers for creating events from the Planning cockpit."""
from __future__ import annotations

import datetime


def event_duration_minutes(start: datetime.datetime, end: datetime.datetime) -> int:
    """Return a positive event duration, rejecting an invalid time range."""
    duration = int((end - start).total_seconds() / 60)
    if duration <= 0:
        raise ValueError("La fin doit être postérieure au début.")
    return duration
