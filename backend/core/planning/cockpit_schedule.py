"""Date-based task selection for the Planning cockpit."""
from __future__ import annotations

import datetime


def tasks_for_day(tasks: list, day: datetime.date, today: datetime.date) -> tuple[list, list]:
    """Split tasks into urgent and due lists without populating past columns."""
    if day < today:
        return [], []
    if day == today:
        return [task for task in tasks if task.days_overdue > 0], [
            task for task in tasks if task.days_overdue == 0 and task.due_date == day
        ]
    return [], [task for task in tasks if task.due_date == day]
