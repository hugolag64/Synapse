"""Logique domaine : génération/correction des questions OIC via AnythingLLM."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from backend.core.lisa import anythingllm_client as _client


@dataclass
class Question:
    type: Literal["qcm", "ouverte"]
    enonce: str
    options: list[str] | None = None
    correct_index: int | None = None
    explication: str | None = None    # QCM uniquement, caché de l'UI jusqu'à réponse
    criteres: list[str] | None = None  # ouverte uniquement, caché de l'UI jusqu'à réponse


@dataclass
class EvalResult:
    verdict: Literal["correct", "partial", "incorrect"]
    score: int
    elements_corrects: list[str] = field(default_factory=list)
    elements_manquants: list[str] = field(default_factory=list)
    explication: str = ""
    rappel_cours: str = ""


def grade_qcm(question: Question, selected_index: int) -> EvalResult:
    """Correction locale instantanée d'une question QCM, pas d'appel réseau."""
    is_correct = selected_index == question.correct_index
    return EvalResult(
        verdict="correct" if is_correct else "incorrect",
        score=100 if is_correct else 0,
        explication=question.explication or "",
    )


def aggregate_session_score(results: list[EvalResult]) -> int:
    """Moyenne arrondie des scores par question de la session, 0-100."""
    if not results:
        return 0
    return round(sum(r.score for r in results) / len(results))


def next_oic_level(current_level: int, session_score: int, previous_scores: list[int]) -> int:
    """
    Fait évoluer le niveau de maîtrise (0-5) selon le score de la session courante.
    `previous_scores` : scores des 2 tentatives précédentes les plus récentes
    (plus récente en premier), utilisés uniquement pour confirmer le niveau 5
    (exige 3 tentatives consécutives >= 80%, celle-ci incluse).
    """
    if session_score >= 80:
        provisional = min(5, current_level + 1)
    elif session_score >= 50:
        provisional = current_level if current_level >= 3 else max(0, current_level - 1)
    else:
        provisional = max(0, current_level - 1)

    if provisional == 5:
        last_two = previous_scores[:2]
        if len(last_two) < 2 or any(s < 80 for s in last_two):
            provisional = 4

    return provisional
