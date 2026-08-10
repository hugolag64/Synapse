"""Façade de persistance commune des évaluations."""

from __future__ import annotations

import datetime

from backend.core.evaluation.models import EvaluationInput, EvaluationOutcome, recommend_evaluation
from backend.core.lisa import item_service
from backend.core.reviews import local_store


def _pending_gap_ids(item_number: str, error_types: tuple[str, ...]) -> tuple[int, ...]:
    if not item_number or not error_types:
        return ()
    wanted = {error_type.casefold() for error_type in error_types}
    return tuple(int(row["id"]) for row in local_store.get_pending_proposals()
                 if row["item_number"] == item_number
                 and str(row["error_type"] or "").casefold() in wanted)


def record_evaluation(evaluation: EvaluationInput) -> EvaluationOutcome:
    """Persiste une évaluation et retourne ses conséquences consultatives."""
    if evaluation.source == "qcm":
        persisted_id = local_store.add_qcm_session_full(
            platform=evaluation.platform or "Synapse",
            session_date=evaluation.session_date or datetime.date.today().isoformat(),
            course_id=evaluation.course_id, course_title=evaluation.course_title,
            item_number=evaluation.item_number, score_percent=evaluation.score_percent,
            score_raw=evaluation.score_raw,
            session_type=evaluation.session_type,
            difficulty=evaluation.difficulty,
            total_questions=evaluation.total_questions,
            correct_answers=evaluation.correct_answers,
            wrong_answers=evaluation.wrong_answers,
            rank_a_questions=evaluation.rank_a_questions,
            rank_a_correct=evaluation.rank_a_correct,
            rank_b_questions=evaluation.rank_b_questions,
            rank_b_correct=evaluation.rank_b_correct,
            rank_unknown_questions=evaluation.rank_unknown_questions,
            error_types=list(evaluation.error_types), comments=evaluation.detail,
        )
        gap_proposal_ids = _pending_gap_ids(evaluation.item_number, evaluation.error_types)
    elif evaluation.source == "auto_eval":
        persisted_id = local_store.add_study_session(
            course_id=evaluation.course_id, course_title=evaluation.course_title,
            item_number=evaluation.item_number, context=evaluation.context,
            activity_types=list(evaluation.activity_types) or ["révision"],
            duration_minutes=evaluation.duration_minutes,
            confidence=evaluation.confidence,
            difficulty=evaluation.difficulty,
            qcm_result=evaluation.qcm_result,
            weak_category=evaluation.error_types[0] if evaluation.error_types else None,
            weak_detail=evaluation.detail,
            notes=evaluation.notes,
        )
        gap_proposal_ids = _pending_gap_ids(evaluation.item_number, evaluation.error_types)
    elif evaluation.source == "oic":
        if not evaluation.course_ids:
            raise ValueError("course_ids est requis pour une évaluation OIC")
        if not evaluation.oic_code:
            raise ValueError("oic_code est requis pour une évaluation OIC")
        persisted_id = item_service.save_item_oic_attempt(
            evaluation.course_ids, evaluation.oic_code, int(evaluation.score_percent or 0),
            evaluation.questions_json or "[]",
        )
        gap_proposal_ids = ()
    else:
        raise ValueError(f"Source d'évaluation inconnue: {evaluation.source!r}")

    return EvaluationOutcome(
        source=evaluation.source, persisted_id=persisted_id,
        gap_proposal_ids=gap_proposal_ids, recommendation=recommend_evaluation(evaluation),
    )
