"""Types et règles pures des évaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvaluationSource = Literal["qcm", "auto_eval", "oic"]
EvaluationRecommendation = Literal[
    "none", "review_errors", "practice_oic", "consolidate"
]


@dataclass(frozen=True)
class EvaluationInput:
    source: EvaluationSource
    course_id: str
    item_number: str = ""
    course_title: str = ""
    context: str = "college"
    score_percent: float | None = None
    confidence: int | None = None
    error_types: tuple[str, ...] = ()
    detail: str | None = None
    platform: str | None = None
    session_date: str | None = None
    oic_code: str | None = None
    questions_json: str | None = None
    course_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationOutcome:
    source: EvaluationSource
    persisted_id: int
    gap_proposal_ids: tuple[int, ...] = ()
    recommendation: EvaluationRecommendation = "none"
    ignored_signals: tuple[str, ...] = ()


def recommend_evaluation(evaluation: EvaluationInput) -> EvaluationRecommendation:
    """Retourne un conseil consultatif sans modifier le planning ni la maîtrise."""
    if evaluation.source == "oic" and (evaluation.score_percent or 0) < 70:
        return "practice_oic"
    if evaluation.source == "auto_eval" and (evaluation.confidence or 5) <= 2:
        return "review_errors"
    if evaluation.source == "qcm" and (
        (evaluation.score_percent is not None and evaluation.score_percent < 70)
        or evaluation.error_types
    ):
        return "review_errors"
    if evaluation.score_percent is not None and evaluation.score_percent >= 70:
        return "consolidate"
    return "none"
