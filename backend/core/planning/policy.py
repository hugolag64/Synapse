"""Pure policy helpers for Planning capacity and temporary vacation modes."""
from __future__ import annotations

import datetime
from collections.abc import Iterable

MIN_CAPACITY_HOURS = 3
MAX_CAPACITY_HOURS = 12
DEFAULT_CAPACITY_HOURS = 6
DEFAULT_REDUCTION_RATIO = 0.5


def clamp_capacity_hours(value: object) -> int:
    try:
        hours = int(value)
    except (TypeError, ValueError):
        hours = DEFAULT_CAPACITY_HOURS
    return max(MIN_CAPACITY_HOURS, min(MAX_CAPACITY_HOURS, hours))


def capacity_hours_to_minutes(hours: object) -> int:
    return clamp_capacity_hours(hours) * 60


def vacation_end_date(start: datetime.date, duration_days: int) -> datetime.date:
    return start + datetime.timedelta(days=max(1, int(duration_days)) - 1)


def vacation_payload(
    start: datetime.date,
    duration_days: int,
    strategy: str = "reduced",
) -> dict[str, object]:
    return {
        "enabled": True,
        "start_date": start.isoformat(),
        "end_date": vacation_end_date(start, duration_days).isoformat(),
        "strategy": strategy if strategy in {"reduced", "diagnostic_only"} else "reduced",
        "reduction_ratio": DEFAULT_REDUCTION_RATIO,
    }


def _parse_date(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _vacation_bounds(vacation: object) -> tuple[datetime.date, datetime.date] | None:
    if not isinstance(vacation, dict) or not vacation.get("enabled"):
        return None
    start = _parse_date(vacation.get("start_date"))
    end = _parse_date(vacation.get("end_date"))
    if not start or not end or end < start:
        return None
    return start, end


def is_vacation_day(day: datetime.date, vacation: object) -> bool:
    bounds = _vacation_bounds(vacation)
    return bool(bounds and bounds[0] <= day <= bounds[1])


def vacation_is_expired(vacation: object, today: datetime.date) -> bool:
    bounds = _vacation_bounds(vacation)
    return bool(bounds and today > bounds[1])


def effective_capacity_minutes(base_minutes: int, vacation: object) -> int:
    if not isinstance(vacation, dict) or not vacation.get("enabled"):
        return max(0, int(base_minutes))
    if vacation.get("strategy") == "diagnostic_only":
        return 0
    try:
        ratio = float(vacation.get("reduction_ratio", DEFAULT_REDUCTION_RATIO))
    except (TypeError, ValueError):
        ratio = DEFAULT_REDUCTION_RATIO
    ratio = max(0.0, min(1.0, ratio))
    return max(MIN_CAPACITY_HOURS * 60, round(int(base_minutes) * ratio))


def capacity_from_preferences(preferences: dict, day_iso: str | None = None) -> int:
    if day_iso:
        targets = preferences.get("planning_targets", {})
        target = targets.get(day_iso, {}) if isinstance(targets, dict) else {}
        if isinstance(target, dict) and target.get("mode") == "minutes":
            try:
                return max(0, min(MAX_CAPACITY_HOURS * 60, int(target["value"])))
            except (TypeError, ValueError):
                pass
    raw = preferences.get("planning_capacity_minutes")
    try:
        minutes = int(raw) if raw is not None else DEFAULT_CAPACITY_HOURS * 60
    except (TypeError, ValueError):
        minutes = DEFAULT_CAPACITY_HOURS * 60
    return max(MIN_CAPACITY_HOURS * 60, min(MAX_CAPACITY_HOURS * 60, minutes))


def vacation_for_preferences(preferences: dict) -> dict:
    vacation = preferences.get("planning_vacation", {})
    return dict(vacation) if isinstance(vacation, dict) else {}


def target_for_day(day: datetime.date, preferences: dict) -> int:
    base = capacity_from_preferences(preferences, day.isoformat())
    vacation = vacation_for_preferences(preferences)
    return effective_capacity_minutes(base, vacation) if is_vacation_day(day, vacation) else base


def return_diagnostic_tasks(tasks: Iterable, vacation: object, today: datetime.date) -> list:
    if not isinstance(vacation, dict) or vacation.get("strategy") != "diagnostic_only":
        return []
    if not vacation_is_expired(vacation, today):
        return []
    bounds = _vacation_bounds(vacation)
    if not bounds:
        return []
    start, end = bounds
    selected = [task for task in tasks if start <= getattr(task, "due_date", None) <= end]
    return sorted(selected, key=lambda task: (task.due_date, -getattr(task, "priority_score", 0)))
