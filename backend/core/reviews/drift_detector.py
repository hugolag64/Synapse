"""Détection locale de dérive sur les snapshots hebdomadaires de maîtrise."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict


@dataclass(frozen=True)
class MasteryDrift:
    course_id: str
    start_score: float
    end_score: float
    weekly_delta: float
    direction: str
    confidence: str
    sample_count: int


def _score(value) -> float | None:
    try:
        return max(0.0, min(100.0, float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def detect_mastery_drift(
    snapshots: list[dict], *, min_points: int = 3, threshold: float = 2.0
) -> list[MasteryDrift]:
    """Return meaningful weekly trends, ignoring incomplete short histories."""
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in snapshots:
        course_id = str(row.get("course_id") or "").strip()
        score = _score(row.get("mastery_score"))
        week = str(row.get("week") or "").strip()
        if course_id and week and score is not None:
            grouped[course_id].append((week, score))

    signals: list[MasteryDrift] = []
    for course_id, values in grouped.items():
        values = sorted(set(values), key=lambda value: value[0])
        if len(values) < min_points:
            continue
        start_score = values[0][1]
        end_score = values[-1][1]
        weekly_delta = (end_score - start_score) / max(len(values) - 1, 1)
        if weekly_delta > threshold:
            direction = "improving"
        elif weekly_delta < -threshold:
            direction = "regressing"
        else:
            direction = "stable"
        confidence = "faible" if len(values) < 4 else "indicative" if len(values) < 7 else "haute"
        signals.append(MasteryDrift(
            course_id=course_id,
            start_score=start_score,
            end_score=end_score,
            weekly_delta=round(weekly_delta, 2),
            direction=direction,
            confidence=confidence,
            sample_count=len(values),
        ))
    return sorted(signals, key=lambda signal: (abs(signal.weekly_delta), signal.course_id), reverse=True)
