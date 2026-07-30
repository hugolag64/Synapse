"""Independent, structured AI verification for local UNESS propositions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from backend.core.ai.routing import AITask

from .models import UnessExam, UnessProposition, UnessQuestion

_CONTEXT_LIMITED_SOURCE = "Contexte limité : aucune source pédagogique fournie."
_REQUIRED_RESULT_KEYS = {
    "id",
    "verdict_ia",
    "explication_ia",
    "sources_ia",
    "confiance_ia",
    "commentaire_desaccord",
}


@dataclass(frozen=True)
class VerificationContext:
    """Local pedagogical context supplied by the existing course/Notion layer."""

    course_text: str
    item_refs: list[str]
    external_refs: list[str]

    @property
    def has_pedagogical_sources(self) -> bool:
        return bool(self.course_text.strip() or self.item_refs or self.external_refs)


def _prompt(question: UnessQuestion, context: VerificationContext) -> str:
    propositions = "\n".join(
        f"- {proposition.id}: {proposition.texte}" for proposition in question.propositions
    )
    refs = ", ".join([*context.item_refs, *context.external_refs]) or "aucune"
    source_notice = (
        "Des sources pédagogiques sont disponibles ci-dessous."
        if context.has_pedagogical_sources
        else "CONTEXTE LIMITÉ : aucune source pédagogique n'est disponible; indiquez cette limite."
    )
    return f"""Vérifie indépendamment chaque proposition d'une question UNESS.
La correction officielle est informative uniquement : ne la recopie pas sans raisonnement.
Retourne exclusivement un objet JSON avec la clé `propositions`, contenant exactement un
résultat par identifiant de proposition. Chaque résultat doit contenir les clés : id,
verdict_ia (booléen ou null), explication_ia (explication non vide), sources_ia (liste),
confiance_ia (nombre), commentaire_desaccord (chaîne, vide seulement sans désaccord).

Question {question.id} ({question.type_question}) : {question.enonce}
Propositions :
{propositions}
Références d'items ou externes : {refs}
Contexte : {source_notice}"""


def _json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("réponse IA JSON invalide") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("propositions"), list):
        raise ValueError("réponse IA sans liste de propositions")
    return payload


def _clamped_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confiance_ia invalide")
    return max(0.0, min(1.0, float(value)))


def _status(official: bool | None, verdict: bool | None) -> str:
    if official is None or verdict is None:
        return "incertain"
    return "concordant" if official == verdict else "desaccord"


def _result_by_id(payload: dict[str, Any], question: UnessQuestion) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for result in payload["propositions"]:
        if not isinstance(result, dict) or not _REQUIRED_RESULT_KEYS <= result.keys():
            raise ValueError("résultat IA incomplet")
        identifier = result["id"]
        if not isinstance(identifier, str) or identifier in results:
            raise ValueError("identifiant de proposition IA invalide ou dupliqué")
        results[identifier] = result
    expected = {proposition.id for proposition in question.propositions}
    missing = expected - results.keys()
    unknown = results.keys() - expected
    if missing:
        raise ValueError(f"résultat IA manquant pour la proposition {sorted(missing)[0]}")
    if unknown:
        raise ValueError(f"résultat IA inattendu pour la proposition {sorted(unknown)[0]}")
    return results


def _verified_proposition(
    proposition: UnessProposition, result: dict[str, Any], context: VerificationContext
) -> UnessProposition:
    verdict = result["verdict_ia"]
    if verdict is not None and not isinstance(verdict, bool):
        raise ValueError("verdict_ia invalide")
    explanation = result["explication_ia"]
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("explication_ia est requise pour chaque proposition")
    sources = result["sources_ia"]
    if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
        raise ValueError("sources_ia invalide")
    normalized_sources = tuple(source.strip() for source in sources if source.strip())
    if not context.has_pedagogical_sources:
        normalized_sources = (*normalized_sources, _CONTEXT_LIMITED_SOURCE)
    disagreement_comment = result["commentaire_desaccord"]
    if not isinstance(disagreement_comment, str):
        raise ValueError("commentaire_desaccord invalide")
    return replace(
        proposition,
        verdict_ia=verdict,
        explication_ia=explanation.strip(),
        sources_ia=normalized_sources,
        confiance_ia=_clamped_confidence(result["confiance_ia"]),
        commentaire_desaccord=disagreement_comment.strip(),
        statut=_status(proposition.reponse_uness, verdict),
    )


def verify_question(
    question: UnessQuestion, context: VerificationContext, ai_service: Any
) -> UnessQuestion:
    """Return a verified copy; the official UNESS answer is never changed."""
    response = ai_service.generate(
        AITask.QCM, _prompt(question, context), context=context.course_text or None, response_format="json"
    )
    results = _result_by_id(_json_payload(response.text), question)
    return replace(
        question,
        propositions=tuple(
            _verified_proposition(proposition, results[proposition.id], context)
            for proposition in question.propositions
        ),
    )


def verify_exam(exam: UnessExam, context: VerificationContext, ai_service: Any) -> UnessExam:
    """Verify every question of a local exam with the same source context."""
    return replace(
        exam,
        questions=tuple(verify_question(question, context, ai_service) for question in exam.questions),
    )
