"""Canonical persistence path for closed practice answers."""

from __future__ import annotations

import datetime
from typing import Any

from backend.core.edn.error_profile import map_discordance_to_error_category
from backend.core.practice.scoring import ScoredAttempt, score_closed_attempt
from backend.core.reviews import local_store


def _question_kind(question: dict[str, Any]) -> str:
    raw = str(question.get("question_kind") or question.get("kind") or "QRM").upper()
    return "QRU" if raw in {"QRU", "SINGLE"} else "QRM"


def _question_constraint(question: dict[str, Any], name: str) -> list[str]:
    values = question.get(name)
    if values is None and isinstance(question.get("uness"), dict):
        values = question["uness"].get(name)
    if isinstance(values, str):
        return [values]
    return [str(value) for value in (values or [])]


def score_and_record_closed_attempt(
    *,
    session_id: int,
    question_id: int,
    question: dict[str, Any],
    response: str,
    finalize_session: bool = False,
) -> tuple[int, ScoredAttempt]:
    """Score a closed answer once and persist its official correction payload."""
    choices = (
        (question.get("uness") or {}).get("propositions")
        or question.get("choices")
        or []
    )
    scored = score_closed_attempt(
        response,
        choices,
        str(question.get("answer") or ""),
        question_kind=_question_kind(question),
        indispensable_choices=_question_constraint(question, "indispensable_choices"),
        inacceptable_choices=_question_constraint(question, "inacceptable_choices"),
    )
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response=response,
        is_correct=scored.score_percent == 100.0,
        score_percent=scored.score_percent,
        score_mode=scored.score_mode,
        score_reason=scored.score_reason,
        finalize_session=finalize_session,
    )
    if attempt_id is not None:
        local_store.replace_ai_practice_attempt_propositions(attempt_id, scored.propositions)
        record_error_signals_for_attempt(
            attempt_id=attempt_id,
            question_id=question_id,
            question=question,
            propositions=scored.propositions,
        )
    return attempt_id, scored


def record_error_signals_for_attempt(
    *,
    attempt_id: int,
    question_id: int,
    question: dict[str, Any] | None,
    propositions: list[dict[str, Any]],
) -> None:
    """Persist idempotent cognitive error signals for a scored attempt."""
    item_rows = local_store.get_ai_practice_question_items(question_id)
    if not item_rows:
        return
    occurred_at = datetime.date.today().isoformat()
    for item_row in item_rows:
        item_number = str(item_row.get("item_number") or "").strip()
        if not item_number:
            continue
        for proposition in propositions:
            if proposition.get("discordance") == "correct":
                continue
            category = map_discordance_to_error_category(
                proposition,
                question or {},
                item_row,
            )
            local_store.insert_error_signal_once(
                item_number=item_number,
                category=category,
                occurred_at=occurred_at,
                source="qcm",
                evidence_id=str(attempt_id),
                detail=str(proposition.get("proposition_id") or ""),
            )
