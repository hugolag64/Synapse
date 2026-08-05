"""EDNpro correction-to-JSON pipeline.

This module deliberately reuses Synapse's existing Gemini routing and canonical
exam JSON contract. It does not silently mark a source correction as official.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.core.ai.tasks import generate_uness_correction
from backend.core.prep.resources import upsert_prep_resource
from backend.core.uness import import_service
from backend.core.uness.json_io import load_exam, save_exam

from .normalizer import normalize_ednpro_payload


def condense_explanation(text: str, *, max_chars: int = 360) -> str:
    """Keep EDNpro's useful explanation while making it readable in Synapse."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"^(?:VRAI|FAUX)\s*[:.-]\s*", "", cleaned, flags=re.IGNORECASE)
    if len(cleaned) <= max_chars:
        return cleaned
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    selected = ""
    for sentence in sentences:
        candidate = f"{selected} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        selected = candidate
    if selected:
        return selected.rstrip(" .") + "…"
    return cleaned[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"


def apply_source_correction(source_payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Reuse complete EDNpro AI explanations before paying for a new pass.

    EDNpro already exposes a detailed, non-official correction. When every
    closed proposition has a source answer and explanation, we preserve the
    full text in the source JSON and use a compact version as Synapse's IA
    explanation. Incomplete sessions still go through the existing Lite model.
    """
    result = deepcopy(source_payload)
    closed_questions = [question for question in result.get("questions", []) if question.get("choices")]
    has_source_explanations = any(
        bool(choice.get("source_explanation") or choice.get("source_ai_explanation"))
        for question in closed_questions
        for choice in question.get("choices", [])
    )
    source_answers_complete = bool(closed_questions) and has_source_explanations and all(
        isinstance(choice.get("correct"), bool)
        for question in closed_questions
        for choice in question.get("choices", [])
    )
    if not source_answers_complete:
        return result, False

    for question in result.get("questions", []):
        question_has_missing_explanations = any(
            not (choice.get("source_explanation") or choice.get("source_ai_explanation"))
            for choice in question.get("choices", [])
        )
        question["verification_status"] = (
            "unsupported"
            if question.get("choices") and question_has_missing_explanations
            else "verified"
            if question.get("choices")
            else "unverified"
        )
        for choice in question.get("choices", []):
            source_explanation = choice.get("source_explanation") or choice.get("source_ai_explanation")
            if source_explanation:
                choice["ai_verdict"] = choice.get("correct")
                choice["ai_explanation"] = condense_explanation(str(source_explanation))
                choice["ai_confidence"] = 0.9
            else:
                # Keep EDNpro's source answer in `correct`, but do not claim
                # an IA verification without the corresponding explanation.
                choice["ai_verdict"] = None
                choice["ai_explanation"] = ""
                choice["ai_confidence"] = None
    result.setdefault("metadata", {})["ai_correction"] = "ednpro_source"
    return result, True


def build_correction_prompt(source_payload: dict[str, Any]) -> str:
    """Build a compact, deterministic prompt from EDNpro's structured questions."""
    questions = []
    for question in source_payload.get("questions", []):
        questions.append({
            "id": question.get("id", ""),
            "type": question.get("type", ""),
            "stem": question.get("stem", question.get("enonce", "")),
            "choices": [
                {"id": choice.get("id", ""), "text": choice.get("text", "")}
                for choice in question.get("choices", [])
            ],
        })
    body = json.dumps(
        {"title": source_payload.get("title", ""), "subject": source_payload.get("subject", ""), "questions": questions},
        ensure_ascii=False,
    )
    return f"""Tu vérifies une correction EDNpro, source tierce fiable mais non officielle.
Ne remplace jamais la correction source. Réponds uniquement en JSON avec :
{{"questions":[{{"id":"q-1","verification_status":"verified|unsupported","propositions":[{{"id":"a","verdict_ia":true,"explication":"...","confiance_ia":0.0}}]}}]}}
Reprends exactement les identifiants fournis. Une proposition doit recevoir un verdict IA,
une explication et une confiance entre 0 et 1.

DONNEES A VERIFIER:
{body}
"""


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    payload, _ = json.JSONDecoder().raw_decode(cleaned.strip())
    if not isinstance(payload, dict):
        raise ValueError("La correction IA doit être un objet JSON")
    return payload


def merge_ai_correction(source_payload: dict[str, Any], correction: dict[str, Any]) -> dict[str, Any]:
    """Merge AI verdicts into source questions without losing source answers."""
    result = deepcopy(source_payload)
    source_questions = {str(q.get("id")): q for q in result.get("questions", [])}
    ai_questions = {str(q.get("id")): q for q in correction.get("questions", [])}
    if set(source_questions) != set(ai_questions):
        missing = sorted(set(source_questions) - set(ai_questions))
        extra = sorted(set(ai_questions) - set(source_questions))
        raise ValueError(f"Questions IA incohérentes (manquantes={missing}, supplémentaires={extra})")

    for question in result.get("questions", []):
        ai_question = ai_questions[str(question.get("id"))]
        source_choices = {str(c.get("id")): c for c in question.get("choices", [])}
        ai_choices = {str(c.get("id")): c for c in ai_question.get("propositions", [])}
        if set(source_choices) != set(ai_choices):
            raise ValueError(f"Propositions IA incohérentes pour {question.get('id')}")
        for choice in question.get("choices", []):
            ai_choice = ai_choices[str(choice.get("id"))]
            choice["ai_verdict"] = ai_choice.get("verdict_ia")
            choice["ai_explanation"] = str(ai_choice.get("explication", ""))
            choice["ai_confidence"] = ai_choice.get("confiance_ia")
            if ai_choice.get("commentaire_desaccord"):
                choice["ai_disagreement"] = str(ai_choice["commentaire_desaccord"])
        question["verification_status"] = str(ai_question.get("verification_status", "verified"))
    result.setdefault("metadata", {})["ai_correction"] = True
    return result


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "ednpro-exam"


def generate_and_import_ednpro(
    source_payload: dict[str, Any],
    *,
    service: Any = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate correction JSON, reload it through the canonical contract, import it."""
    corrected_payload, used_source_correction = apply_source_correction(source_payload)
    response = None
    if not used_source_correction:
        response = generate_uness_correction(
            build_correction_prompt(source_payload),
            context=str(source_payload.get("title", "EDNpro")),
            service=service,
        )
        corrected_payload = merge_ai_correction(source_payload, _parse_json_response(response.text))
    exam = normalize_ednpro_payload(corrected_payload)
    target = output_path or (
        import_service.VERIFIED_DIR / f"{_safe_name(exam.title)}.json"
    )
    save_exam(exam, target)
    reloaded_exam = load_exam(target)
    for resource in reloaded_exam.metadata.get("resources", []):
        for item_number in resource.get("item_numbers", []):
            upsert_prep_resource(
                provider="EDNpro",
                resource_type=str(resource.get("type", "video")),
                title=str(resource.get("title", "Ressource EDNpro")),
                url=str(resource.get("url", "")),
                item_number=str(item_number),
                match_method="source",
                confidence=1.0,
                source_url=str(reloaded_exam.provenance.get("source_url", "")),
            )
    session_id = import_service.import_source_exam(
        reloaded_exam,
        source="EDNpro",
        matiere=str(reloaded_exam.metadata.get("subject", "")),
    )
    return {
        "session_id": session_id,
        "json_path": str(target),
        "ai_model": "EDNpro source" if used_source_correction else getattr(getattr(response, "model", None), "value", str(getattr(response, "model", ""))),
    }
