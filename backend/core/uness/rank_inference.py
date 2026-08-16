"""Contracts for inferring missing UNESS question ranks with Gemini."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.core.practice.rank_service import INFERENCE_THRESHOLD

_VALID_RANKS = frozenset({"A", "B"})


@dataclass(frozen=True)
class UnessRankCandidate:
    rank: str
    confidence: float
    ambiguous: bool = False
    oic_codes: tuple[str, ...] = ()
    rationale: str = ""
    source: str = "gemini"


def _value(question: Any, key: str, default: Any = "") -> Any:
    if isinstance(question, Mapping):
        return question.get(key, default)
    return getattr(question, key, default)


def _question_id(question: Any) -> str:
    return str(
        _value(question, "id", "")
        or _value(question, "question_id", "")
        or _value(question, "external_question_id", "")
    ).strip()


def _serialize_question(question: Any) -> dict[str, Any]:
    choices = _value(question, "choices", ()) or ()
    serialized_choices = []
    for choice in choices:
        if isinstance(choice, Mapping):
            serialized_choices.append({
                "id": str(choice.get("id") or choice.get("label") or ""),
                "text": str(choice.get("text") or choice.get("texte") or choice.get("label") or ""),
            })
        else:
            serialized_choices.append({"id": "", "text": str(choice)})
    return {
        "id": _question_id(question),
        "prompt": str(_value(question, "prompt", "") or ""),
        "choices": serialized_choices,
        "answer": str(_value(question, "answer", "") or ""),
        "explanation": str(_value(question, "explanation", "") or ""),
    }


def _serialize_oic(oic: Mapping[str, Any]) -> dict[str, str]:
    return {
        "code": str(oic.get("code") or oic.get("oic_code") or "").strip(),
        "intitule": str(oic.get("intitule") or "").strip(),
        "rang": str(oic.get("rang") or "").strip().upper(),
    }


def build_uness_rank_prompt(
    item_number: str,
    questions: Iterable[Any],
    oics: Iterable[Mapping[str, Any]],
) -> str:
    """Build one strict JSON prompt for a batch of questions from one item."""
    body = {
        "item_number": str(item_number).strip(),
        "oics": [_serialize_oic(oic) for oic in oics],
        "questions": [_serialize_question(question) for question in questions],
    }
    return (
        "Tu classes le rang pédagogique EDN de questions d'annales UNESS. "
        "Utilise uniquement les OIC fournis comme contexte. Réponds A, B ou null, "
        "et marque ambiguous=true si le classement n'est pas suffisamment certain. "
        "La confiance est un nombre entre 0 et 1. Réponds uniquement avec cet objet JSON : "
        '{"questions":[{"id":"...","rank":"A|B|null",'
        '"confidence":0.0,"ambiguous":false,"oic_codes":["..."],"rationale":"..."}]}\n\n'
        "DONNEES:\n"
        + json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    )


def _decode_json(text: str) -> Any:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    return json.loads(cleaned)


def parse_uness_rank_response(
    text: str,
    question_ids: Iterable[str],
    *,
    threshold: float = INFERENCE_THRESHOLD,
) -> dict[str, UnessRankCandidate]:
    """Keep only valid, known and safe-to-use Gemini rank candidates."""
    known_ids = {str(question_id).strip() for question_id in question_ids if str(question_id).strip()}
    try:
        payload = _decode_json(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    rows = payload.get("questions") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return {}

    result: dict[str, UnessRankCandidate] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        question_id = str(row.get("id") or "").strip()
        rank = str(row.get("rank") or "").strip().upper()
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            continue
        ambiguous = bool(row.get("ambiguous", False))
        if (
            question_id not in known_ids
            or rank not in _VALID_RANKS
            or not 0.0 <= confidence <= 1.0
            or confidence < threshold
            or ambiguous
        ):
            continue
        raw_codes = row.get("oic_codes") or ()
        codes: list[str] = []
        for code in raw_codes if isinstance(raw_codes, (list, tuple)) else (raw_codes,):
            normalized = str(code or "").strip()
            if normalized and normalized not in codes:
                codes.append(normalized)
        result[question_id] = UnessRankCandidate(
            rank=rank,
            confidence=confidence,
            ambiguous=ambiguous,
            oic_codes=tuple(codes),
            rationale=str(row.get("rationale") or "").strip()[:500],
        )
    return result
