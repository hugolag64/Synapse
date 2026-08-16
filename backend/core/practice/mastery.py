"""Pont entre les tentatives IA et le service d'évaluation/maîtrise."""

from __future__ import annotations

from backend.core.evaluation.models import EvaluationInput
from backend.core.evaluation.service import record_evaluation
from backend.core.practice.item_evidence import get_session_item_evidence
from backend.core.reviews import local_store


__all__ = ["get_session_item_evidence", "record_ai_practice_mastery"]


def record_ai_practice_mastery(session_id: int):
    """Envoie une session scorée au moteur de maîtrise une seule fois."""
    session = local_store.finalize_ai_practice_session(session_id)
    if (
        not session
        or session.get("completion_state") != "scored"
        or session.get("mastery_recorded_at")
        or session.get("score_percent") is None
    ):
        return None

    kind = str(session["practice_kind"]).lower()
    if kind == "oic":
        objective = str(session.get("objective_code") or "").strip()
        if not objective or not session.get("course_id"):
            return None
        evaluation = EvaluationInput(
            source="oic",
            course_id=session["course_id"],
            course_ids=(session["course_id"],),
            oic_code=objective,
            item_number=session["item_number"],
            score_percent=session["score_percent"],
            total_questions=session["total_questions"],
            session_type="OIC",
            platform="Synapse IA",
        )
    elif kind in {"qcm", "dp", "kfp"}:
        evidence = get_session_item_evidence(session_id)
        if not evidence:
            return None
        outcomes = []
        for item_number, item_evidence in sorted(evidence.items()):
            evaluation = EvaluationInput(
                source="qcm",
                course_id=str(session.get("course_id") or ""),
                item_number=item_number,
                course_title=session["course_title"],
                score_percent=item_evidence["score_percent"],
                total_questions=item_evidence["total_questions"],
                correct_answers=item_evidence["correct_answers"],
                wrong_answers=item_evidence["wrong_answers"],
                session_type=kind.upper(),
                platform="Synapse IA",
            )
            outcomes.append(record_evaluation(evaluation))
        local_store.mark_ai_practice_mastery_recorded(session_id)
        return outcomes[-1]
    else:
        return None

    outcome = record_evaluation(evaluation)
    local_store.mark_ai_practice_mastery_recorded(session_id)
    return outcome
