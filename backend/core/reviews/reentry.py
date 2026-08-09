"""Pure rules for the study reentry boundary.

This module deliberately has no persistence or UI dependency. Callers provide
preferences and receive filtered copies of their in-memory data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date


DEFAULT_STUDY_RESUME_DATE = date(2026, 8, 20)


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def get_study_resume_date(
    preferences: Mapping[str, object] | None = None,
) -> date:
    """Return the configured resume date, or the safe default."""
    configured = preferences.get("study_resume_date") if preferences else None
    return _as_date(configured) or DEFAULT_STUDY_RESUME_DATE


def is_before_study_resume(
    value: date,
    resume_date: date | None = None,
) -> bool:
    """Return whether a date belongs to the neutralized pre-reentry period."""
    boundary = resume_date or DEFAULT_STUDY_RESUME_DATE
    return value < boundary


def filter_active_review_tasks(
    tasks: Iterable[object],
    resume_date: date | None = None,
) -> list[object]:
    """Keep tasks whose effective due date is on/after the reentry boundary."""
    boundary = resume_date or DEFAULT_STUDY_RESUME_DATE
    return [
        task
        for task in tasks
        if isinstance(getattr(task, "due_date", None), date)
        and getattr(task, "due_date") >= boundary
    ]


def filter_post_resume_signals(
    signals: Iterable[Mapping],
    resume_date: date | None = None,
) -> list[dict]:
    """Copy and keep error signals dated on/after the reentry boundary."""
    boundary = resume_date or DEFAULT_STUDY_RESUME_DATE
    result: list[dict] = []
    for signal in signals:
        occurred_at = _as_date(signal.get("occurred_at"))
        if occurred_at is not None and occurred_at >= boundary:
            result.append(dict(signal))
    return result
