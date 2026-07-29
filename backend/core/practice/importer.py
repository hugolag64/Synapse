"""Import local de banques DP/KFP préparées hors de Synapse."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


class ImportValidationError(ValueError):
    """Fichier d'import incompatible avec le contrat Synapse."""


@dataclass(frozen=True)
class ImportedQuestion:
    prompt: str
    answer: str
    explanation: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportedCase:
    fingerprint: str
    external_id: str
    kind: str
    title: str
    stem: str
    item_numbers: tuple[str, ...]
    questions: tuple[ImportedQuestion, ...]
    status: str
    review_reason: str = ""


@dataclass(frozen=True)
class ImportBatch:
    source: str
    cases: tuple[ImportedCase, ...]


def _text(value: Any, field: str, *, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ImportValidationError(f"Champ obligatoire absent : {field}")
    return result


def _item_numbers(raw: Any, title: str, stem: str) -> tuple[str, ...]:
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    found = {str(value).strip() for value in values if str(value).strip().isdigit()}
    if not found:
        found.update(re.findall(r"\bitem\s*(\d{1,3})\b", f"{title} {stem}", re.I))
    return tuple(sorted(found, key=lambda value: int(value)))


def parse_practice_bank(payload: Any) -> ImportBatch:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ImportValidationError("Le fichier d'import n'est pas un JSON valide") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ImportValidationError("Le format d'import attendu est JSON version 1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ImportValidationError("Le fichier doit contenir au moins un cas")

    cases = []
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ImportValidationError(f"Cas {index} invalide")
        kind = _text(raw_case.get("kind"), f"cases[{index}].kind").lower()
        if kind not in {"dp", "kfp"}:
            raise ImportValidationError(f"Cas {index} : le type doit être DP ou KFP")
        title = _text(raw_case.get("title"), f"cases[{index}].title")
        stem = _text(raw_case.get("stem"), f"cases[{index}].stem")
        raw_questions = raw_case.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ImportValidationError(f"Cas {index} : questions absentes")
        questions = []
        for q_index, raw_question in enumerate(raw_questions, start=1):
            if not isinstance(raw_question, dict):
                raise ImportValidationError(f"Cas {index}, question {q_index} invalide")
            questions.append(ImportedQuestion(
                prompt=_text(raw_question.get("prompt"), f"cases[{index}].questions[{q_index}].prompt"),
                answer=_text(raw_question.get("answer"), f"cases[{index}].questions[{q_index}].answer"),
                explanation=_text(raw_question.get("explanation"), f"cases[{index}].questions[{q_index}].explanation"),
                choices=tuple(_text(choice, "choice") for choice in (raw_question.get("choices") or [])),
            ))
        item_numbers = _item_numbers(raw_case.get("item_numbers"), title, stem)
        external_id = str(raw_case.get("id") or f"case-{index}").strip()
        canonical = json.dumps({"kind": kind, "title": title, "stem": stem, "questions": [q.__dict__ for q in questions]}, sort_keys=True, ensure_ascii=False)
        cases.append(ImportedCase(
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            external_id=external_id,
            kind=kind,
            title=title,
            stem=stem,
            item_numbers=item_numbers,
            questions=tuple(questions),
            status="ready" if item_numbers else "needs_review",
            review_reason="" if item_numbers else "ITEM introuvable dans le cas",
        ))
    return ImportBatch(source=str(payload.get("source") or "Import local").strip(), cases=tuple(cases))
