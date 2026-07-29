"""Logique domaine : génération/correction des questions OIC via AnythingLLM."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from backend.core.ai.routing import AITask
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


def _query(prompt: str, workspace_slug: str, ai_service=None) -> str:
    """Exécute une requête OIC via le routeur fourni ou le fallback RAG historique."""
    if ai_service is not None:
        return ai_service.generate(AITask.OIC, prompt, response_format="json").text
    return _client.query_workspace(workspace_slug, prompt)


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


def _extract_json(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def generate_questions(
    course_title: str,
    intitule: str,
    rang: str,
    workspace_slug: str,
    *,
    ai_service=None,
) -> list[Question]:
    """
    Appel query #1. Demande 3-5 questions mixtes QCM/ouvertes en JSON strict.
    Retry une fois si JSON invalide. Dégradé : une question ouverte générique si échec double.
    """
    prompt = (
        "Tu es un enseignant en médecine française (EDN/ECN).\n"
        f'Cours : "{course_title}"\n'
        f'OIC (Objectif Intermédiaire de Connaissance) : "{intitule}"\n'
        f"Rang : {rang}\n\n"
        "En te basant sur les documents de ce workspace concernant ce cours,\n"
        "génère entre 3 et 5 questions pour tester la maîtrise de cet OIC,\n"
        "en mélangeant QCM et questions ouvertes.\n\n"
        "Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :\n"
        "[\n"
        '  {"type": "qcm", "enonce": "...", "options": ["...", "...", "..."], "correct_index": 0, "explication": "..."},\n'
        '  {"type": "ouverte", "enonce": "...", "criteres": ["critère 1", "critère 2"]}\n'
        "]"
    )

    for _attempt in range(2):
        raw = _query(prompt, workspace_slug, ai_service)
        parsed = _extract_json(raw)
        if isinstance(parsed, list) and parsed:
            questions = []
            for item in parsed:
                q_type = item.get("type")
                if q_type not in ("qcm", "ouverte"):
                    continue
                questions.append(Question(
                    type=q_type,
                    enonce=item.get("enonce", ""),
                    options=item.get("options"),
                    correct_index=item.get("correct_index"),
                    explication=item.get("explication"),
                    criteres=item.get("criteres"),
                ))
            if questions:
                return questions

    return [Question(type="ouverte", enonce=f"Expliquez : {intitule}", criteres=[f"Connaître {intitule}"])]


def evaluate_open_answer(
    question: Question,
    student_response: str,
    workspace_slug: str,
    *,
    ai_service=None,
) -> EvalResult:
    """Appel query #2, un par question ouverte répondue. Retry une fois si JSON invalide."""
    criteres = question.criteres or []
    prompt = (
        "Tu es un correcteur médical pour l'EDN (Examen Classant National).\n"
        "Base-toi sur les documents de ce workspace pour vérifier l'exactitude.\n\n"
        f'Question : "{question.enonce}"\n'
        f"Critères attendus : {json.dumps(criteres, ensure_ascii=False)}\n"
        f'Réponse de l\'étudiant : "{student_response}"\n\n'
        "Évalue si la réponse couvre les critères attendus.\n"
        "Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :\n"
        "{\n"
        '  "verdict": "correct" | "partial" | "incorrect",\n'
        '  "score": <entier 0-100>,\n'
        '  "elements_corrects": ["..."],\n'
        '  "elements_manquants": ["..."],\n'
        '  "explication": "<phrase courte>",\n'
        '  "rappel_cours": "<rappel essentiel en 1-3 phrases>"\n'
        "}"
    )

    for _attempt in range(2):
        raw = _query(prompt, workspace_slug, ai_service)
        parsed = _extract_json(raw)
        if isinstance(parsed, dict) and "verdict" in parsed and "score" in parsed:
            try:
                verdict = parsed.get("verdict", "incorrect")
                if verdict not in ("correct", "partial", "incorrect"):
                    verdict = "incorrect"
                score = max(0, min(100, int(parsed.get("score", 0))))
                return EvalResult(
                    verdict=verdict,
                    score=score,
                    elements_corrects=parsed.get("elements_corrects") or [],
                    elements_manquants=parsed.get("elements_manquants") or [],
                    explication=parsed.get("explication", ""),
                    rappel_cours=parsed.get("rappel_cours", ""),
                )
            except (TypeError, ValueError):
                pass

    return EvalResult(verdict="incorrect", score=0, explication="Erreur de parsing IA")
