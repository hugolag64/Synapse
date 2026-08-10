"""Pure contracts for the optional EDNpro question-rank inference pass."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


INFERENCE_THRESHOLD = 0.85
_VALID_RANKS = frozenset({"A", "B"})


@dataclass(frozen=True)
class RankInference:
    """Accepted rank inference for one question."""

    rank: str
    confidence: float
    oic_codes: tuple[str, ...] = ()
    rationale: str = ""
    source: str = "gemini"


def _value(question: Any, key: str, default: Any = "") -> Any:
    if isinstance(question, Mapping):
        return question.get(key, default)
    return getattr(question, key, default)


def _question_id(question: Any) -> str:
    return str(
        _value(question, "external_question_id", "")
        or _value(question, "question_id", "")
        or _value(question, "id", "")
    ).strip()


def _item_number(question: Any) -> str:
    return str(_value(question, "item_number", "") or "").strip()


def _rank(question: Any) -> str:
    return str(_value(question, "rank", "") or "").strip().upper()


def group_missing_rank_questions(questions: Iterable[Any]) -> dict[str, tuple[Any, ...]]:
    """Group only questions without an official A/B rank by item number."""
    groups: dict[str, list[Any]] = {}
    for question in questions:
        item_number = _item_number(question)
        if not item_number or _rank(question) in _VALID_RANKS or not _question_id(question):
            continue
        groups.setdefault(item_number, []).append(question)
    return {item: tuple(values) for item, values in groups.items()}


def _serialize_question(question: Any) -> dict[str, Any]:
    choices = _value(question, "choices", ()) or ()
    serialized_choices = []
    for choice in choices:
        if isinstance(choice, Mapping):
            serialized_choices.append({
                "id": str(choice.get("id") or choice.get("label") or ""),
                "text": str(choice.get("text") or choice.get("label") or ""),
                "correct": choice.get("correct"),
            })
        else:
            serialized_choices.append({"id": "", "text": str(choice), "correct": None})
    return {
        "id": _question_id(question),
        "prompt": str(_value(question, "prompt", "") or ""),
        "choices": serialized_choices,
        "correct_answers": list(_value(question, "correct_answers", ()) or ()),
        "explanation_simple": str(_value(question, "explanation_simple", "") or ""),
        "explanation_detailed": str(_value(question, "explanation_detailed", "") or ""),
        "score_percent": _value(question, "score_percent", None),
    }


def _serialize_oic(oic: Mapping[str, Any]) -> dict[str, str]:
    return {
        "code": str(oic.get("code") or oic.get("oic_code") or "").strip(),
        "intitule": str(oic.get("intitule") or "").strip(),
        "rang": str(oic.get("rang") or "").strip().upper(),
    }


def build_rank_inference_prompt(
    item_number: str,
    questions: Iterable[Any],
    oics: Iterable[Mapping[str, Any]],
) -> str:
    """Build one JSON-only prompt sharing OIC context across all questions."""
    body = {
        "item_number": str(item_number).strip(),
        "oics": [_serialize_oic(oic) for oic in oics],
        "questions": [_serialize_question(question) for question in questions],
    }
    return (
        "Tu classes le rang pédagogique EDN d'un lot de questions QCM. "
        "Le rang EDNpro officiel a déjà été retiré de ce lot. Utilise uniquement "
        "les OIC fournis comme contexte. Ne déduis jamais un rang C : réponds "
        "A, B ou null. La confiance est un nombre entre 0 et 1. "
        "Réponds uniquement avec cet objet JSON : "
        '{"questions":[{"id":"...","rank":"A|B|null",'
        '"confidence":0.0,"oic_codes":["..."],"rationale":"..."}]}\n\n'
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


def parse_rank_inference_response(
    text: str,
    question_ids: Iterable[str],
    *,
    threshold: float = INFERENCE_THRESHOLD,
) -> dict[str, RankInference]:
    """Keep only valid, known-question, strictly-above-threshold inferences."""
    known_ids = {str(question_id).strip() for question_id in question_ids if str(question_id).strip()}
    try:
        payload = _decode_json(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    rows = payload.get("questions") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return {}

    result: dict[str, RankInference] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        question_id = str(row.get("id") or "").strip()
        rank = str(row.get("rank") or "").strip().upper()
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            continue
        if (
            question_id not in known_ids
            or rank not in _VALID_RANKS
            or not 0.0 <= confidence <= 1.0
            or confidence <= threshold
        ):
            continue
        raw_codes = row.get("oic_codes") or ()
        codes: list[str] = []
        for code in raw_codes if isinstance(raw_codes, (list, tuple)) else (raw_codes,):
            normalized = str(code or "").strip()
            if normalized and normalized not in codes:
                codes.append(normalized)
        result[question_id] = RankInference(
            rank=rank,
            confidence=confidence,
            oic_codes=tuple(codes),
            rationale=str(row.get("rationale") or "").strip()[:500],
        )
    return result
