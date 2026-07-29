"""Pure presentation decisions shared by the session feedback panel."""

from __future__ import annotations

import datetime
from typing import Any


_CONFIDENCE_LABELS = {
    1: "Très incertain",
    2: "Incertain",
    3: "Correct",
    4: "Solide",
    5: "Très solide",
}


def confidence_label(value: int) -> str:
    """Return the readable label for a confidence value from one to five."""
    return _CONFIDENCE_LABELS.get(int(value), "Non renseigné")


def qcm_activity_ids() -> frozenset[str]:
    return frozenset({"qcm", "dp_kfp"})


def default_feedback_state(
    task: Any,
    initial_duration_minutes: int | None,
    manual_date: datetime.date | None,
) -> dict[str, Any]:
    """Build the initial state without rendering or persisting anything."""
    review_type = getattr(task, "review_type", "")
    if review_type == "bonus":
        activities, duration, confidence, difficulty, qcm_result = ["lecture"], 30, 3, "moyen", None
    elif review_type == "qcm_error":
        activities, duration, confidence, difficulty, qcm_result = ["qcm", "correction"], 20, 2, "difficile", "raté"
    elif review_type == "lacune":
        activities, duration, confidence, difficulty, qcm_result = ["correction"], 15, 3, "moyen", None
    else:
        activities, duration, confidence, difficulty, qcm_result = ["révision"], 20, 3, "moyen", None

    if initial_duration_minutes is not None:
        duration = max(1, int(initial_duration_minutes))

    return {
        "activity_types": activities,
        "duration": duration,
        "confidence": confidence,
        "difficulty": difficulty,
        "qcm_result": qcm_result,
        "weak_category": None,
        "weak_detail": "",
        "session_date": manual_date or datetime.date.today(),
    }
