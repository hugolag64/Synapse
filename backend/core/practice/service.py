"""Orchestration des sessions IA et conversion des réponses structurées."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from typing import Any

from loguru import logger

from backend.core.ai.routing import AITask, model_for_task
from backend.core.ai.service import AIService
from backend.core.lisa.item_service import get_item_oics
from backend.core.qcm.items_mapping import resolve as resolve_item

from .models import GeneratedQuestion, PracticeDifficulty, PracticeKind, PracticeSessionSpec, QuestionKind


class PracticeGenerationError(ValueError):
    """Réponse IA absente, invalide ou incompatible avec la session."""


def _routed_model_label(spec: PracticeSessionSpec) -> str:
    """Modèle attendu d'après le routage, utilisé seulement à défaut de réponse."""
    return model_for_task(_task_for(spec.practice_kind), spec.difficulty).value


def _model_label(response: Any, spec: PracticeSessionSpec) -> str:
    """Libellé du modèle réellement utilisé, avec repli sur le routage attendu.

    Le fournisseur fait foi : un routage recalculé côté appelant pouvait annoncer
    un modèle différent de celui qui avait effectivement répondu.
    """
    model = getattr(response, "model", None)
    label = getattr(model, "value", model)
    return str(label) if label else _routed_model_label(spec)


def _task_for(kind: PracticeKind) -> AITask:
    return {
        PracticeKind.OIC: AITask.OIC,
        PracticeKind.QCM: AITask.QCM,
        PracticeKind.DP: AITask.DP,
        PracticeKind.KFP: AITask.KFP,
    }[kind]


_MAX_OBJECTIVES_IN_PROMPT = 12


def _item_identity(spec: PracticeSessionSpec) -> str:
    """Identifie l'item par son intitulé, pas seulement par son numéro.

    Le prompt ne portait que « ITEM 230 » : le modèle devait deviner de mémoire à
    quoi ce numéro correspond, alors que la numérotation EDN a changé entre
    versions du référentiel — d'où des dossiers hors sujet.
    """
    number = str(spec.item_number or "").strip()
    if not number:
        return "un ITEM non précisé"
    title, college = resolve_item(number)
    if not title:
        return f"l'ITEM {number} (intitulé inconnu du référentiel)"
    if college:
        return f"l'ITEM {number} — {title} (collège : {college})"
    return f"l'ITEM {number} — {title}"


def _format_objectives(rows) -> tuple[str, ...]:
    """Transforme des lignes OIC en libellés « code : intitulé » lisibles."""
    formatted: list[str] = []
    for row in rows or ():
        try:
            code = str(row["oic_code"] or "").strip()
            label = str(row["intitule"] or "").strip()
        except (TypeError, KeyError, IndexError):
            continue
        if not code and not label:
            continue
        formatted.append(f"{code} : {label}" if code and label else code or label)
        if len(formatted) >= _MAX_OBJECTIVES_IN_PROMPT:
            break
    return tuple(formatted)


def _prompt_for(
    spec: PracticeSessionSpec,
    context: str = "",
    objectives: tuple[str, ...] = (),
) -> str:
    distribution = (
        f"{spec.open_questions} ouverte(s) et {spec.closed_questions} fermée(s)"
    )
    difficulty_instructions = {
        PracticeDifficulty.STANDARD: "niveau Standard : vérifier les connaissances et les applications directes du cours",
        PracticeDifficulty.EDN: "niveau EDN : mobiliser le raisonnement clinique, des distracteurs plausibles et des pièges classiques",
        PracticeDifficulty.DIFFICULT: "niveau Difficile : ajouter des données parasites, des distracteurs plausibles et des décisions moins évidentes",
        PracticeDifficulty.CONCOURS: "niveau Concours : proposer des cas intégratifs, une hiérarchisation fine, de l'incertitude et des distracteurs très proches",
    }[spec.difficulty]
    objectives_block = (
        "Objectifs OIC de cet item :\n" + "\n".join(f"- {line}" for line in objectives)
        if objectives
        else f"Objectif OIC : {spec.objective_code or 'non précisé'}."
    )
    return f"""
Génère une session médicale fiable pour {_item_identity(spec)}.
Le sujet doit rester celui de cet item : n'aborde pas une autre pathologie.
Type : {spec.practice_kind.value}. Total : {spec.total_questions} questions ({distribution}).
Niveau de difficulté : {difficulty_instructions}.
{objectives_block}
Contexte de cours : fourni dans le bloc documentaire séparé.

Retourne uniquement ce JSON :
{{"questions":[{{"kind":"open|closed","prompt":"...","choices":["..."],"answer":"...","explanation":"...","source_refs":["..."]}}]}}

Contraintes :
- respecter exactement la répartition demandée ;
- vérifier avant l'envoi que la liste contient exactement {spec.total_questions} question(s) ;
- une question fermée contient au moins 2 choix ;
- chaque question contient obligatoirement sa réponse correcte et une explication pédagogique ;
- rester concis : énoncé inférieur à 280 caractères, explication inférieure à 500 caractères ;
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

    def _objectives_for(self, spec: PracticeSessionSpec) -> tuple[str, ...]:
        """Objectifs OIC de l'item, ou rien si la base est indisponible.

        Un enrichissement de prompt ne doit jamais empêcher de générer : en cas
        d'échec on retombe sur le prompt sans objectifs.
        """
        if not spec.course_id:
            return ()
        try:
            return _format_objectives(get_item_oics([spec.course_id]))
        except Exception:
            logger.warning("Objectifs OIC indisponibles pour {}", spec.course_id)
            return ()

    def generate_questions(
        self,
        spec: PracticeSessionSpec,
        context: str = "",
        *,
        max_attempts: int = 1,
        recover_partial: bool = False,
    ) -> list[dict]:
        questions, _model = self._generate_with_model(
            spec, context, max_attempts=max_attempts, recover_partial=recover_partial
        )
        return questions

    def _generate_with_model(
        self,
        spec: PracticeSessionSpec,
        context: str = "",
        *,
        max_attempts: int = 1,
        recover_partial: bool = False,
    ) -> tuple[list[dict], str]:
        """Génère les questions et remonte le modèle réellement utilisé.

        Le modèle est remonté plutôt que recalculé par l'appelant : recalculer le
        routage à part produisait un libellé qui pouvait diverger de l'appel réel.
        """
        if not 1 <= int(max_attempts) <= 3:
            raise ValueError("max_attempts doit être compris entre 1 et 3")
        task = _task_for(spec.practice_kind)
        ctx_label = context or (f"ITEM {spec.item_number}" if spec.item_number else spec.practice_kind.value.upper())
        objectives = self._objectives_for(spec)
        last_error: PracticeGenerationError | None = None
        for attempt in range(int(max_attempts)):
            retry_hint = ""
            if last_error is not None:
                retry_hint = (
                    "\nREPRISE OBLIGATOIRE : la réponse précédente était invalide "
                    f"({last_error}). Retourne exactement {spec.total_questions} question(s), "
                    "sans texte hors JSON."
                )
            response = self.ai_service.generate(
                task,
                _prompt_for(spec, context, objectives) + retry_hint,
                context=ctx_label,
                response_format="json",
                difficulty=spec.difficulty,
            )
            try:
                questions = _parse_questions(response, spec)
            except PracticeGenerationError as exc:
                last_error = exc
                continue
            return [asdict(q) for q in questions], _model_label(response, spec)
        assert last_error is not None
        if recover_partial and "nombre de questions" in str(last_error):
            return self._recover_partial_questions(spec, context, max_attempts=max_attempts)
        raise last_error

    def _recover_partial_questions(
        self,
        spec: PracticeSessionSpec,
        context: str,
        *,
        max_attempts: int,
    ) -> tuple[list[dict], str]:
        """Fallback borné : demande une question par appel si le lot est partiel."""
        single_spec = replace(spec, total_questions=1, open_questions=0, closed_questions=1)
        recovered: list[dict] = []
        model = _routed_model_label(spec)
        for position in range(spec.total_questions):
            single_context = (
                f"{context}\n\nLOT DE RATTRAPAGE : génère la question {position + 1} "
                f"sur {spec.total_questions}. Retourne exactement une question."
            )
            questions, model = self._generate_with_model(
                single_spec,
                single_context,
                max_attempts=max_attempts,
            )
            recovered.extend(questions)
        return recovered, model

    def create_new_session(
        self,
        spec: PracticeSessionSpec,
        context: str = "",
        *,
        max_attempts: int = 1,
        recover_partial: bool = False,
    ) -> int:
        questions, model = self._generate_with_model(
            spec,
            context,
            max_attempts=max_attempts,
            recover_partial=recover_partial,
        )
        return self.store.create_ai_practice_session(
            spec=spec,
            questions=questions,
            model=model,
        )

    def create_tutor_dp_session(
        self,
        *,
        item_number: str,
        course_id: str,
        course_title: str,
        dossier_context: str,
        errors: list[dict],
        gap_details: list[str],
        total_questions: int = 5,
        max_attempts: int = 2,
    ) -> int:
        """Génère une session DP ciblée sur l'historique pédagogique de l'item."""
        if not 1 <= int(total_questions) <= 10:
            raise ValueError("Le Tuteur DP doit contenir entre 1 et 10 questions")
        error_lines = [
            f"- {row.get('category', 'non_classe')}: {row.get('detail', '')}".strip()
            for row in errors
        ] or ["- aucune erreur catégorisée"]
        gap_lines = [f"- {detail}" for detail in gap_details] or ["- aucune lacune active"]
        context = "\n".join([
            f"DOSSIER PROGRESSIF : {dossier_context}",
            "ERREURS À CIBLER :",
            *error_lines,
            "LACUNES À CONSOLIDER :",
            *gap_lines,
        ])
        spec = PracticeSessionSpec(
            practice_kind=PracticeKind.DP,
            total_questions=total_questions,
            open_questions=0,
            closed_questions=total_questions,
            item_number=item_number,
            course_id=course_id,
            course_title=course_title,
            difficulty=PracticeDifficulty.EDN,
        )
        return self.create_new_session(
            spec,
            context=context,
            max_attempts=max_attempts,
            recover_partial=True,
        )

    def replay_session(self, session_id: int) -> int:
        return self.store.replay_ai_practice_session(session_id)
