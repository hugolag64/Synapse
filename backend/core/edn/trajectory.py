"""Progression, potentiel de gain et projection de trajectoire EDN."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressSnapshot:
    covered_items: int
    total_items: int
    average_mastery: float | None
    overdue_reviews: int
    remaining_reviews: int
    recent_items_per_week: float
    recent_minutes_per_day: float


@dataclass(frozen=True)
class ProjectionScenario:
    name: str
    projected_coverage: float
    projected_mastery: float | None
    remaining_items: int
    confidence: str


def _row_value(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def build_progress_snapshot(*, courses: list, tasks: list, history: dict, as_of: datetime.date) -> ProgressSnapshot:
    total_items = len(courses)
    covered_items = sum(1 for course in courses if _row_value(course, "date_1ere_lecture"))
    scores = [_row_value(task, "mastery_score") for task in tasks if _row_value(task, "mastery_score") is not None]
    average_mastery = round(sum(scores) / len(scores), 1) if scores else None
    overdue = sum(1 for task in tasks if (_row_value(task, "days_overdue", 0) or 0) > 0)
    cutoff = as_of - datetime.timedelta(days=27)
    recent_items = {
        str(_row_value(row, "course_id", ""))
        for row in history.values()
        if _row_value(row, "status") == "done"
        and str(_row_value(row, "completed_at", ""))[:10]
        and datetime.date.fromisoformat(str(_row_value(row, "completed_at"))[:10]) >= cutoff
    }
    recent_minutes = sum(
        float(_row_value(row, "duration_minutes", 0) or 0)
        for row in history.values()
        if _row_value(row, "status") == "done"
        and str(_row_value(row, "completed_at", ""))[:10]
        and datetime.date.fromisoformat(str(_row_value(row, "completed_at"))[:10]) >= cutoff
    )
    return ProgressSnapshot(
        covered_items=covered_items,
        total_items=total_items,
        average_mastery=average_mastery,
        overdue_reviews=overdue,
        remaining_reviews=len(tasks),
        recent_items_per_week=round(len(recent_items) / 4, 2),
        recent_minutes_per_day=round(recent_minutes / 28, 2),
    )


def project_to_exam(
    snapshot: ProgressSnapshot,
    *,
    target_date: datetime.date,
    daily_capacity_minutes: int,
    today: datetime.date | None = None,
) -> tuple[ProjectionScenario, ...]:
    today = today or datetime.date.today()
    weeks = max(0.0, (target_date - today).days / 7)
    capacity_factor = max(0.0, min(1.5, daily_capacity_minutes / 60))
    baseline = snapshot.recent_items_per_week or 0.0
    rates = (0.75, 1.0, 1.25)
    names = ("prudent", "central", "ambitieux")
    confidence = ("faible", "indicative", "haute")
    scenarios = []
    for name, factor, confidence_label in zip(names, rates, confidence, strict=True):
        projected_items = min(
            snapshot.total_items,
            snapshot.covered_items + baseline * factor * capacity_factor * weeks,
        )
        coverage = round(projected_items / snapshot.total_items * 100, 1) if snapshot.total_items else 0.0
        mastery = None if snapshot.average_mastery is None else round(
            min(100.0, snapshot.average_mastery + max(0.0, coverage - snapshot.covered_items / max(snapshot.total_items, 1) * 100) * 0.15),
            1,
        )
        scenarios.append(ProjectionScenario(
            name=name,
            projected_coverage=coverage,
            projected_mastery=mastery,
            remaining_items=max(0, snapshot.total_items - round(projected_items)),
            confidence=confidence_label,
        ))
    return tuple(scenarios)
