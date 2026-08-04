"""Normalize EDNpro's source/correction payload into Synapse's exam model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.uness.models import (
    UnessExam,
    UnessImage,
    UnessProposition,
    UnessQuestion,
    _assert_safe_source_url,
)

from .collector import normalize_stable_resource_url

_QUESTION_TYPES = {"QRM", "QRU", "QRP/L", "DP", "KFP", "QROC", "TCS"}


def _question_type(raw: Any, choices: list[dict]) -> str:
    candidate = str(raw or "").upper().strip()
    if candidate in _QUESTION_TYPES:
        return candidate
    correct_count = sum(bool(choice.get("correct")) for choice in choices)
    if not choices:
        return "QROC"
    return "QRU" if correct_count <= 1 else "QRM"


def _resource_rows(resources: list[dict] | None) -> list[dict]:
    rows = []
    for resource in resources or []:
        try:
            url = normalize_stable_resource_url(resource.get("url", ""))
        except ValueError:
            continue
        rows.append({
            "provider": "EDNpro",
            "type": str(resource.get("type", "video")),
            "title": str(resource.get("title", "Ressource EDNpro")),
            "url": url,
            "item_numbers": [str(item) for item in resource.get("item_numbers", []) if str(item).strip()],
        })
    return rows


def normalize_ednpro_payload(payload: dict[str, Any]) -> UnessExam:
    """Build a validated exam while preserving EDNpro as a non-official source."""
    title = str(payload.get("title", "")).strip()
    year = payload.get("year")
    raw_source_url = str(payload.get("url", ""))
    _assert_safe_source_url(raw_source_url)
    source_url = normalize_stable_resource_url(raw_source_url)
    if not title:
        raise ValueError("Titre EDNpro requis")
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError("Année EDNpro invalide")

    questions: list[UnessQuestion] = []
    for index, raw_question in enumerate(payload.get("questions", []), start=1):
        choices = list(raw_question.get("choices", []))
        propositions = tuple(
            UnessProposition(
                id=str(choice.get("id") or f"q{index}-p{choice_index}"),
                texte=str(choice.get("text", "")).strip(),
                reponse_uness=choice.get("correct"),
                verdict_ia=choice.get("ai_verdict"),
                explication_ia=str(choice.get("ai_explanation", "")),
                confiance_ia=choice.get("ai_confidence"),
                statut=(
                    "incertain"
                    if choice.get("ai_verdict") is None
                    else "concordant"
                    if choice.get("ai_verdict") == choice.get("correct")
                    else "desaccord"
                ),
                commentaire_desaccord=str(choice.get("ai_disagreement", "")),
            )
            for choice_index, choice in enumerate(choices, start=1)
        )
        questions.append(
            UnessQuestion(
                id=str(raw_question.get("id") or f"ednpro-q-{index}"),
                type_question=_question_type(raw_question.get("type"), choices),
                enonce=str(raw_question.get("stem", raw_question.get("enonce", ""))),
                propositions=propositions,
                images=tuple(UnessImage.from_dict(image) for image in raw_question.get("images", [])),
                verification_status=str(raw_question.get("verification_status", "unverified")),
                dp_context=dict(raw_question.get("dp_context", {})),
                item_numbers=tuple(dict.fromkeys(
                    str(item).strip() for item in raw_question.get("item_numbers", []) if str(item).strip()
                )),
            )
        )

    metadata = {
        "subject": str(payload.get("subject", "")),
        "exam_type": "edn_complet",
        "session_id": str(payload.get("session_id", "")),
        "correction_source": "ednpro",
        "correction_official": False,
        "dossiers": list(payload.get("dossiers", [])),
        "source_explanations": {
            str(question.get("id")): {
                "question": str(question.get("source_explanation", "")),
                "propositions": {
                    str(choice.get("id")): str(choice.get("source_explanation", ""))
                    for choice in question.get("choices", [])
                    if choice.get("source_explanation")
                },
            }
            for question in payload.get("questions", [])
            if any(choice.get("source_explanation") for choice in question.get("choices", []))
        },
        "resources": _resource_rows(payload.get("resources")),
    }
    return UnessExam(
        faculty="EDNpro",
        level="EDN",
        year=year,
        title=title,
        questions=tuple(questions),
        provenance={
            "source": "EDNpro",
            "source_url": source_url,
            "collected_at": str(payload.get("collected_at") or datetime.now(timezone.utc).isoformat()),
            "collection_status": str(payload.get("collection_status", "captured")),
            "external_exam_id": str(payload.get("exam_id", payload.get("session_id", ""))),
        },
        metadata=metadata,
    )
