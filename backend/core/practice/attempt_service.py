"""Canonical persistence path for closed practice answers."""

from __future__ import annotations

import datetime
from typing import Any

from loguru import logger

from backend.core.edn.error_profile import map_discordance_to_error_category
from backend.core.practice.scoring import (
    ScoredAttempt,
    score_closed_attempt,
    score_qroc_response,
    score_tcs_attempt,
)
from backend.core.reviews import local_store


def _question_kind(question: dict[str, Any]) -> str:
    uness = question.get("uness")
    nested_question = uness.get("question") if isinstance(uness, dict) else None
    raw = (
        question.get("question_kind")
        or question.get("type_question")
        or (nested_question.get("type_question") if isinstance(nested_question, dict) else None)
        or (uness.get("type_question") if isinstance(uness, dict) else None)
        or question.get("kind")
        or "QRM"
    )
    normalized = str(raw).strip().upper()
    return "QRU" if normalized in {"QRU", "SINGLE"} else normalized


def _question_constraint(question: dict[str, Any], name: str) -> list[str]:
    values = question.get(name)
    if values is None and isinstance(question.get("uness"), dict):
        values = question["uness"].get(name)
        if values is None and isinstance(question["uness"].get("question"), dict):
            values = question["uness"]["question"].get(name)
    if isinstance(values, str):
        return [values]
    return [str(value) for value in (values or [])]


def _question_expected_count(question: dict[str, Any]) -> int | None:
    values = question.get("expected_choice_count")
    uness = question.get("uness")
    if values is None and isinstance(uness, dict):
        values = uness.get("expected_choice_count")
        if values is None and isinstance(uness.get("question"), dict):
            values = uness["question"].get("expected_choice_count")
    try:
        return int(values) if values is not None else None
    except (TypeError, ValueError):
        return None


def _question_uness_metadata(question: dict[str, Any]) -> dict[str, Any]:
    uness = question.get("uness") or (question.get("import_metadata") or {}).get("uness") or {}
    return uness.get("question") if isinstance(uness.get("question"), dict) else {}


def _visual_attempt_is_not_noted(question: dict[str, Any]) -> bool:
    return str(_question_uness_metadata(question).get("verification_status") or "").strip().lower() == "unsupported"


def score_and_record_closed_attempt(
    *,
    session_id: int,
    question_id: int,
    question: dict[str, Any],
    response: str,
    duration_seconds: int | None = None,
    finalize_session: bool = False,
) -> tuple[int, ScoredAttempt]:
    """Score a closed answer once and persist its official correction payload."""
    choices = (
        (question.get("uness") or {}).get("propositions")
        or question.get("choices")
        or []
    )
    kind = _question_kind(question)
    if _visual_attempt_is_not_noted(question):
        scored = ScoredAttempt(0.0, "not_noted", "support_visuel_manquant", [])
    else:
        scored = (
            score_tcs_attempt(response, choices)
            if kind == "TCS"
            else score_closed_attempt(
                response,
                choices,
                str(question.get("answer") or ""),
                question_kind=kind,
                indispensable_choices=_question_constraint(question, "indispensable_choices"),
                inacceptable_choices=_question_constraint(question, "inacceptable_choices"),
                expected_choice_count=_question_expected_count(question),
            )
        )
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response=response,
        is_correct=scored.score_percent == 100.0,
        score_percent=scored.score_percent,
        score_mode=scored.score_mode,
        score_reason=scored.score_reason,
        duration_seconds=duration_seconds,
        finalize_session=finalize_session,
    )
    if attempt_id is not None and scored.score_mode != "not_noted":
        local_store.replace_ai_practice_attempt_propositions(attempt_id, scored.propositions)
        record_error_signals_for_attempt(
            attempt_id=attempt_id,
            question_id=question_id,
            question=question,
            propositions=scored.propositions,
            session_id=session_id,
        )
    return attempt_id, scored


def score_and_record_open_attempt(
    *,
    session_id: int,
    question_id: int,
    question: dict[str, Any],
    response: str,
    duration_seconds: int | None = None,
) -> tuple[int, ScoredAttempt]:
    """Score a QROC from official exact/acceptable answer bands."""
    metadata = _question_uness_metadata(question)
    scored = (
        ScoredAttempt(0.0, "not_noted", "support_visuel_manquant", [])
        if _visual_attempt_is_not_noted(question)
        else score_qroc_response(
            response,
            exact_answers=metadata.get("qroc_exact_answers") or (),
            acceptable_answers=metadata.get("qroc_acceptable_answers") or (),
        )
    )
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response=response,
        is_correct=(scored.score_percent == 100.0) if scored.score_mode != "not_noted" else None,
        score_percent=scored.score_percent,
        score_mode=scored.score_mode,
        score_reason=scored.score_reason,
        duration_seconds=duration_seconds,
        finalize_session=False,
    )
    return attempt_id, scored


def _session_item_fallback(session_id: int | None) -> list[dict[str, Any]]:
    """Item de la session, sous la forme attendue pour un rattachement."""
    if session_id is None:
        return []
    try:
        summary = local_store.get_ai_practice_session_summary(int(session_id))
    except Exception:
        return []
    item_number = str((dict(summary) if summary else {}).get("item_number") or "").strip()
    if not item_number.isdigit():
        return []
    return [{"item_number": item_number, "source": "session-fallback", "confidence": 0.5}]


def record_error_signals_for_attempt(
    *,
    attempt_id: int,
    question_id: int,
    question: dict[str, Any] | None,
    propositions: list[dict[str, Any]],
    session_id: int | None = None,
) -> None:
    """Enregistre les signaux d'erreur d'une tentative scorée, sans doublon.

    La fonction s'arrêtait quand la question n'avait aucune classification par
    item. Sur les données réelles, aucune tentative n'a jamais réuni les deux
    conditions requises — question classée ET détail propositionnel — si bien
    que la table est restée vide depuis toujours, en silence.

    À défaut de classification propre, la question hérite de l'item de sa
    session : une question de dossier porte sur le dossier. Sans item nulle
    part, on trace au lieu de disparaître.
    """
    item_rows = local_store.get_ai_practice_question_items(question_id)
    if not item_rows:
        item_rows = _session_item_fallback(session_id)
    if not item_rows:
        logger.warning(
            "Signal d'erreur abandonné : ni la question {} ni sa session ne portent d'item",
            question_id,
        )
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
