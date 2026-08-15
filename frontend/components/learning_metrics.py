"""Shared, read-only learning metric contracts for the UI."""

from __future__ import annotations

from datetime import date


COLLEGE_PROGRESS_LEVELS = (
    (0, "Non commencé"),
    (1, "En cours"),
    (40, "Parcouru"),
    (70, "Consolidé"),
    (100, "Validé"),
)


def college_progress_level(percent: int | None, *, manually_validated: bool = False) -> str:
    """Return the five-level college progress vocabulary."""
    if manually_validated:
        return "Validé"
    if percent is None or percent <= 0:
        return "Non commencé"
    normalized = max(0, min(100, int(percent)))
    for threshold, label in reversed(COLLEGE_PROGRESS_LEVELS):
        if normalized >= threshold:
            return label
    return "Non commencé"


def build_advancement(
    done: int | None,
    total: int | None,
    *,
    college_validated: bool = False,
) -> dict[str, int | None]:
    """Build the read-over-total metric without fabricating an unknown value."""
    normalized_done = int(done) if done is not None else None
    normalized_total = int(total) if total is not None else None
    if college_validated and normalized_total is not None:
        normalized_done = normalized_total

    percent = None
    if normalized_done is not None and normalized_total is not None and normalized_total > 0:
        percent = round(normalized_done / normalized_total * 100)

    return {"done": normalized_done, "total": normalized_total, "percent": percent}


def build_learning_metrics(
    *,
    done: int | None,
    total: int | None,
    college_validated: bool = False,
    mastery_score: int | None = None,
    mastery_level: str | None = None,
    retention_score: int | None = None,
    retention_stability_days: float | None = None,
    retention_last_evidence: date | None = None,
) -> dict[str, dict[str, object]]:
    """Combine independent UI metrics without recalculating their sources."""
    return {
        "advancement": build_advancement(
            done,
            total,
            college_validated=college_validated,
        ),
        "mastery": {"score": mastery_score, "level": mastery_level},
        "retention": {
            "score": retention_score,
            "stability_days": retention_stability_days,
            "last_evidence": retention_last_evidence,
        },
    }
