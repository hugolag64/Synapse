"""Transmission commune du retour détaillé d'une session d'étude."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def submit_session_feedback(
    on_done: Callable[..., Awaitable[None]] | None,
    task: Any,
    card: Any,
    *,
    activity_types: list | None = None,
    duration_minutes: int | None = None,
    confidence: int | None = None,
    difficulty: str | None = None,
    qcm_result: str | None = None,
    weak_category: str | None = None,
    weak_detail: str | None = None,
) -> None:
    """Délègue le résultat complet du wizard au callback de validation."""
    if on_done is None:
        return

    await on_done(
        task,
        card,
        activity_types=activity_types,
        duration_minutes=duration_minutes,
        confidence=confidence,
        difficulty=difficulty,
        qcm_result=qcm_result,
        weak_category=weak_category,
        weak_detail=weak_detail,
    )
