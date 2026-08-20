"""Workflow métier unique de validation d'une tâche de révision."""

from __future__ import annotations

from typing import Optional

from backend.core.reviews import local_store
from backend.core.evaluation.models import EvaluationInput
from backend.core.evaluation.service import record_evaluation
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.service import review_service


def complete_review(
    task: ReviewTask,
    *,
    activity_types: Optional[list] = None,
    duration_minutes: Optional[int] = None,
    confidence: Optional[int] = None,
    difficulty: Optional[str] = None,
    qcm_result: Optional[str] = None,
    weak_category: Optional[str] = None,
    weak_detail: Optional[str] = None,
) -> ReviewTask:
    """Valide ``task`` et enregistre exactement une session associée.

    Les trois familles de tâches gardent leurs écritures métier historiques :
    révision SM-2, consolidation SM-2 dédiée et résolution de lacune.
    """
    common = dict(
        course_id=task.course_id,
        course_title=task.course_title,
        item_number=task.item_number or "",
        context=task.context,
        activity_types=activity_types or ["révision"],
        duration_minutes=duration_minutes,
        confidence=confidence,
        difficulty=difficulty,
        qcm_result=qcm_result,
        weak_category=weak_category,
        weak_detail=weak_detail,
    )

    # Persist the session before changing the review state. If SQLite is
    # unavailable here, the task remains pending instead of becoming "done"
    # without the evidence that should explain that completion.
    evaluation_outcome = record_evaluation(EvaluationInput(
        source="auto_eval",
        course_id=common["course_id"],
        course_title=common["course_title"],
        item_number=common["item_number"],
        context=common["context"],
        activity_types=tuple(common["activity_types"]),
        duration_minutes=common["duration_minutes"],
        confidence=common["confidence"],
        difficulty=common["difficulty"],
        qcm_result=common["qcm_result"],
        error_types=(common["weak_category"],) if common["weak_category"] else (),
        detail=common["weak_detail"],
    ))

    try:
        if task.review_type == "consolidation":
            local_store.mark_consolidation_done(
                course_id=task.course_id,
                context=task.context,
                theoretical_due_date=task.theoretical_due_date,
                course_title=task.course_title,
                item_number=task.item_number or "",
                confidence=confidence or 3,
                difficulty=difficulty,
                mastery_level=task.mastery_level,
            )
        elif task.review_type == "lacune":
            try:
                weak_point_id = int(task.id.removeprefix("lacune_"))
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Identifiant de lacune invalide: {task.id!r}") from exc
            local_store.resolve_weak_point(weak_point_id)
        else:
            local_store.mark_done(
                task_id=task.id,
                course_id=task.course_id,
                context=task.context,
                review_type=task.review_type,
                theoretical_due_date=task.theoretical_due_date,
                course_title=task.course_title,
                item_number=task.item_number or "",
                difficulty=difficulty,
                confidence=confidence,
            )
    except Exception:
        # The session is the first durable side effect. Remove it if the
        # task-specific state transition fails, so a failed completion cannot
        # leave an orphaned learning record behind.
        persisted_id = getattr(evaluation_outcome, "persisted_id", None)
        if persisted_id is not None:
            local_store.delete_study_session(persisted_id)
        raise

    review_service.invalidate_cache()

    return task
