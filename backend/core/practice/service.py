"""Orchestration des sessions IA et conversion des réponses structurées."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from backend.core.ai.routing import AITask, model_for_task
from backend.core.ai.service import AIService

from .models import GeneratedQuestion, PracticeKind, PracticeSessionSpec, QuestionKind


class PracticeGenerationError(ValueError):
    """Réponse IA absente, invalide ou incompatible avec la session."""


def _task_for(kind: PracticeKind) -> AITask:
    return {
        PracticeKind.OIC: AITask.OIC,
        PracticeKind.QCM: AITask.QCM,
        PracticeKind.DP: AITask.DP,
        PracticeKind.KFP: AITask.KFP,
    }[kind]


def _prompt_for(spec: PracticeSessionSpec, context: str = "") -> str:
    distribution = (
        f"{spec.open_questions} ouverte(s) et {spec.closed_questions} fermée(s)"
    )
    return f"""
Génère une session médicale fiable pour l'ITEM {spec.item_number or 'non précisé'}.
Type : {spec.practice_kind.value}. Total : {spec.total_questions} questions ({distribution}).
Objectif OIC : {spec.objective_code or 'non précisé'}.
Contexte de cours : {context or 'aucun contexte supplémentaire'}

Retourne uniquement ce JSON :
{{"questions":[{{"kind":"open|closed","prompt":"...","choices":["..."],"answer":"...","explanation":"...","source_refs":["..."]}}]}}

Contraintes :
- respecter exactement la répartition demandée ;
- une question fermée contient au moins 2 choix ;
- chaque question contient obligatoirement sa réponse correcte et une explication pédagogique ;
- ne jamais inventer une référence ; utiliser une liste vide si aucune source n'est fournie ;
- pour DP/KFP, conserver le raisonnement clinique et les pièges pertinents.
""".strip()


def _parse_questions(payload: Any, spec: PracticeSessionSpec) -> list[GeneratedQuestion]:
    if hasattr(payload, "text"):
        payload = payload.text
    if isinstance(payload, str):
        raw_text = payload.strip()
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, flags=re.IGNORECASE | re.DOTALL)
            candidate = fenced.group(1).strip() if fenced else raw_text
            if not fenced:
                start = candidate.find("{")
                end = candidate.rfind("}")
                candidate = candidate[start:end + 1] if start >= 0 and end > start else candidate
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise PracticeGenerationError("La réponse IA n'est pas un JSON valide") from exc
    raw_questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(raw_questions, list) or len(raw_questions) != spec.total_questions:
        raise PracticeGenerationError("La réponse IA ne respecte pas le nombre de questions demandé")

    result: list[GeneratedQuestion] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise PracticeGenerationError("Une question IA est mal formée")
        try:
            kind = QuestionKind(str(raw.get("kind", "")).lower())
            choices = tuple(str(v).strip() for v in (raw.get("choices") or []) if str(v).strip())
            refs = tuple(str(v).strip() for v in (raw.get("source_refs") or []) if str(v).strip())
            result.append(GeneratedQuestion(
                prompt=str(raw.get("prompt", "")),
                kind=kind,
                choices=choices,
                answer=str(raw.get("answer", "")),
                explanation=str(raw.get("explanation", "")),
                source_refs=refs,
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise PracticeGenerationError("Une question IA est invalide") from exc

    opens = sum(q.kind is QuestionKind.OPEN for q in result)
    closed = sum(q.kind is QuestionKind.CLOSED for q in result)
    if (opens, closed) != (spec.open_questions, spec.closed_questions):
        raise PracticeGenerationError("La réponse IA ne respecte pas la répartition ouverte/fermée")
    return result


class PracticeService:
    """Façade testable : génération IA puis persistance des questions immuables."""

    def __init__(self, ai_service: AIService | None = None, store=None):
        if ai_service is None:
            from backend.core.ai.gemini_client import GeminiClient
            ai_service = AIService(GeminiClient())
        self.ai_service = ai_service
        if store is None:
            from backend.core.reviews import local_store
            store = local_store
        self.store = store

    def generate_questions(self, spec: PracticeSessionSpec, context: str = "") -> list[dict]:
        task = _task_for(spec.practice_kind)
        response = self.ai_service.generate(
            task,
            _prompt_for(spec, context),
            response_format="json",
        )
        questions = _parse_questions(response, spec)
        return [asdict(q) for q in questions]

    def create_new_session(self, spec: PracticeSessionSpec, context: str = "") -> int:
        questions = self.generate_questions(spec, context)
        return self.store.create_ai_practice_session(
            spec=spec,
            questions=questions,
            model=model_for_task(_task_for(spec.practice_kind)).value,
        )

    def replay_session(self, session_id: int) -> int:
        return self.store.replay_ai_practice_session(session_id)
