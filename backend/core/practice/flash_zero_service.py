"""
flash_zero_service.py — Synapse
--------------------------------
Service backend gérant le "Morning Flash-Zero Quiz" (5 min / 10 questions sur les zéros éliminatoires).
"""

from __future__ import annotations

import json
import random
import re
from datetime import date
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from backend.core.ai.routing import AITask
from backend.core.reviews import local_store
from backend.core.reviews.reentry import filter_post_resume_signals, get_study_resume_date
from backend.core.edn.error_profile import signals_since
from backend.state.store import data_store


def build_flash_zero_priority(signals, today=None) -> list[str]:
    """Classe les items par répétition puis par récence, sans dépendre de l'IA."""
    reference_date = today
    if not isinstance(reference_date, date):
        try:
            reference_date = date.fromisoformat(str(reference_date)[:10]) if reference_date else date.today()
        except ValueError:
            reference_date = date.today()

    grouped: dict[str, list[date]] = {}
    for signal in signals or []:
        item = str(signal.get("item_number") or "").strip().removeprefix("ITEM ")
        if item:
            try:
                occurred_at = date.fromisoformat(str(signal.get("occurred_at") or "")[:10])
            except ValueError:
                occurred_at = date.min
            grouped.setdefault(item, []).append(min(occurred_at, reference_date))
    return [
        item
        for item, dates in sorted(
            grouped.items(), key=lambda pair: (len(pair[1]), max(pair[1], default=date.min)), reverse=True
        )
    ]


@dataclass(frozen=True)
class FlashZeroQuestion:
    id: str
    item_number: str
    item_title: str
    question_text: str
    choices: tuple[str, ...]
    correct_idx: int
    explanation: str
    is_zero_eliminatoire: bool
    category: str  # ex: "Contre-indication", "Urgence vitale", "Erreur de rang A"
    source: str = "canonical"  # "canonical" | "ai"
    review_reason: str = ""  # non vide => badge "Généré par IA" dans le wizard
    source_ref: str = ""
    revised_at: str = ""


_FLASH_ZERO_BANK_PATH = Path(__file__).resolve().parents[3] / "data" / "flash_zero_bank.json"


def _load_canonical_flash_bank() -> list[FlashZeroQuestion]:
    """Charge la banque éditoriale versionnée hors du code Python."""
    try:
        rows = json.loads(_FLASH_ZERO_BANK_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        logger.error("Banque Flash-Zero indisponible: {}", exc)
        return []
    if not isinstance(rows, list):
        logger.error("Banque Flash-Zero invalide: la racine doit être une liste")
        return []

    result: list[FlashZeroQuestion] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            result.append(FlashZeroQuestion(
                id=str(row["id"]),
                item_number=str(row["item_number"]),
                item_title=str(row["item_title"]),
                question_text=str(row["question_text"]),
                choices=tuple(str(choice) for choice in row["choices"]),
                correct_idx=int(row["correct_idx"]),
                explanation=str(row["explanation"]),
                is_zero_eliminatoire=bool(row["is_zero_eliminatoire"]),
                category=str(row["category"]),
                source="canonical",
                source_ref=str(row["source"]),
                revised_at=str(row["revised_at"]),
            ))
        except (KeyError, TypeError, ValueError):
            logger.warning("Question Flash-Zero ignorée dans la banque: {}", row.get("id"))
    return result


def _latest_flash_zero_attempts(rows: list[dict] | None) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows or []:
        question_id = str(row.get("question_id") or "").strip()
        if not question_id:
            continue
        current = latest.get(question_id)
        if current is None or str(row.get("answered_at") or "") > str(current.get("answered_at") or ""):
            latest[question_id] = row
    return latest


def _is_flash_zero_due(question: FlashZeroQuestion, attempt: dict | None, quiz_date: date) -> bool:
    if attempt is None:
        return True
    try:
        answered_date = date.fromisoformat(str(attempt.get("answered_at") or "")[:10])
    except ValueError:
        return True
    elapsed_days = (quiz_date - answered_date).days
    required_days = 3 if bool(attempt.get("is_correct")) else 1
    return elapsed_days >= required_days


def _flash_zero_prompt(item_number: str) -> str:
    return f"""
Génère UNE question de type Flash-Zero (zéro éliminatoire ou erreur classique de Rang A) sur
l'ITEM {item_number} du programme EDN.

Ne génère cette question QUE si le fait clinique testé est un "toujours/jamais" bien établi,
non discutable (contre-indication absolue, geste vital immédiat, règle de sécurité obligatoire).
Ne propose jamais une nuance ou une controverse.

Retourne uniquement ce JSON :
{{"item_title":"...", "question_text":"...", "choices":["...","...","...","..."],
"correct_idx":0, "explanation":"...", "is_zero_eliminatoire":true, "category":"...",
"uncertain":false}}

Contraintes :
- "choices" contient exactement 4 propositions ;
- "correct_idx" est l'index (0-3) de la bonne réponse dans "choices" ;
- "explanation" est concise (moins de 400 caractères) et justifie le "toujours/jamais" ;
- "category" est courte (ex: "Contre-indication", "Urgence vitale", "Sécurité / Règle A") ;
- si tu as le moindre doute sur l'exactitude clinique, mets "uncertain":true plutôt que
  d'inventer un fait.
""".strip()


def _parse_flash_zero_question(response: Any, item_number: str) -> dict | None:
    payload = response.text if hasattr(response, "text") else response
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
            except json.JSONDecodeError:
                return None
    if not isinstance(payload, dict):
        return None

    choices = [str(c).strip() for c in (payload.get("choices") or []) if str(c).strip()]
    try:
        correct_idx = int(payload.get("correct_idx"))
    except (TypeError, ValueError):
        return None
    question_text = str(payload.get("question_text") or "").strip()
    explanation = str(payload.get("explanation") or "").strip()
    category = str(payload.get("category") or "").strip()
    item_title = str(payload.get("item_title") or "").strip()

    if len(choices) < 2 or not (0 <= correct_idx < len(choices)):
        return None
    if not question_text or not explanation or not category or not item_title:
        return None

    formatted_item = item_number if item_number.upper().startswith("ITEM") else f"ITEM {item_number}"
    return {
        "item_number": formatted_item,
        "item_title": item_title,
        "question_text": question_text,
        "choices": choices,
        "correct_idx": correct_idx,
        "explanation": explanation,
        "is_zero_eliminatoire": bool(payload.get("is_zero_eliminatoire", True)),
        "category": category,
        "review_reason": "Incertitude signalée par l'IA" if payload.get("uncertain") else "",
    }


class FlashZeroService:
    """Service d'entraînement rapide sur les zéros éliminatoires EDN."""

    def __init__(self, store=None, ai_service=None):
        self.store = store or local_store
        if ai_service is None:
            from backend.core.ai.gemini_client import GeminiClient
            from backend.core.ai.service import AIService
            ai_service = AIService(GeminiClient())
        self.ai_service = ai_service

    def _priority_signals(self, item_number: str | None = None) -> list[dict]:
        try:
            signals = list(signals_since(item_number=item_number, days=30, store=self.store))
        except Exception:
            signals = []
        try:
            signals.extend(self.store.get_ai_practice_error_signals(
                item_number=item_number, days=30, limit=200
            ))
        except (AttributeError, TypeError, RuntimeError):
            pass
        return filter_post_resume_signals(
            signals,
            get_study_resume_date(data_store.preferences),
        )

    def record_attempt(self, question: FlashZeroQuestion, is_correct: bool) -> int:
        """Enregistre une réponse et laisse le store calculer la prochaine échéance."""
        return self.store.record_flash_zero_attempt(
            question_id=question.id,
            item_number=question.item_number,
            source=question.source,
            is_correct=is_correct,
        )

    def generate_daily_questions(self, *, count: int = 3, item_number: str | None = None) -> list[dict]:
        """
        Génère jusqu'à `count` nouvelles questions Flash-Zero ciblées sur les items
        en tête de la priorité d'erreurs récentes. N'affecte jamais canonical_flash_bank ;
        chaque question invalide est écartée individuellement (best-effort, pas de lot
        tout-ou-rien).
        """
        signals = self._priority_signals(item_number)
        priority = build_flash_zero_priority(signals)[:count]
        if not priority:
            return []

        generated: list[dict] = []
        for item in priority:
            try:
                response = self.ai_service.generate(
                    AITask.FLASH_ZERO, _flash_zero_prompt(item), response_format="json",
                )
            except Exception:
                continue
            question = _parse_flash_zero_question(response, item)
            if question is not None:
                generated.append(question)

        if generated:
            self.store.save_flash_zero_ai_questions(generated)
        return generated

    def get_morning_quiz(
        self,
        count: int = 10,
        *,
        item_number: str | None = None,
        quiz_date: date | None = None,
    ) -> list[FlashZeroQuestion]:
        """
        Génère un quiz de `count` questions (par défaut 10) axé sur :
        1. Les lacunes / erreurs de Rang A récentes dans SQLite.
        2. Une banque de pièges et zéros éliminatoires prédéfinis EDN.
        """
        canonical_flash_bank = _load_canonical_flash_bank()
        ai_bank: list[FlashZeroQuestion] = []
        try:
            ai_rows = self.store.get_flash_zero_ai_questions()
        except Exception:
            ai_rows = []
        for row in ai_rows:
            try:
                ai_bank.append(FlashZeroQuestion(
                    id=f"fz-ai-{row['id']}",
                    item_number=row["item_number"],
                    item_title=row["item_title"],
                    question_text=row["question_text"],
                    choices=tuple(json.loads(row["choices_json"])),
                    correct_idx=row["correct_idx"],
                    explanation=row["explanation"],
                    is_zero_eliminatoire=bool(row["is_zero_eliminatoire"]),
                    category=row["category"],
                    source="ai",
                    review_reason=row["review_reason"] or "",
                    source_ref="ai_generated",
                    revised_at=str(row.get("generated_at") or ""),
                ))
            except Exception:
                continue

        full_bank = canonical_flash_bank + ai_bank

        signals = self._priority_signals(item_number)
        priority = build_flash_zero_priority(signals)
        rank = {item: index for index, item in enumerate(priority)}
        targeted = [q for q in full_bank if q.item_number.removeprefix("ITEM ") in rank]
        fallback = [q for q in full_bank if q not in targeted]
        targeted.sort(key=lambda q: rank[q.item_number.removeprefix("ITEM ")])
        effective_date = quiz_date or date.today()
        rng = random.Random(f"flash-zero:{effective_date.isoformat()}:{item_number or 'all'}")
        rng.shuffle(fallback)
        ordered = targeted + fallback
        try:
            attempts = self.store.get_flash_zero_attempts(
                question_ids=[question.id for question in ordered], limit=2_000
            )
        except (AttributeError, TypeError, RuntimeError):
            attempts = []
        latest_attempts = _latest_flash_zero_attempts(attempts)
        due = [
            question for question in ordered
            if _is_flash_zero_due(question, latest_attempts.get(question.id), effective_date)
        ]
        not_due = [question for question in ordered if question not in due]
        return (due + not_due)[:count]
