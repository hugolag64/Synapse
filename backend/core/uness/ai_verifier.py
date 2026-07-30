"""Independent, structured AI verification for local UNESS propositions."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from io import BytesIO
from typing import Any

from PIL import Image

from backend.core.ai.routing import AIImageContent, AITask

from . import import_service
from .models import (
    UnessExam,
    UnessImage,
    UnessProposition,
    UnessQuestion,
    _assert_no_sensitive_data,
)

_CONTEXT_LIMITED_SOURCE = "Contexte limité : aucune source pédagogique fournie."
_REQUIRED_RESULT_KEYS = {
    "id",
    "verdict_ia",
    "explication_ia",
    "sources_ia",
    "confiance_ia",
    "commentaire_desaccord",
}
_MAX_IMAGE_COUNT = 4
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024
_SUPPORTED_IMAGE_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}
_UNSUPPORTED_VISUAL_EXPLANATION = (
    "Vérification IA indisponible : le support visuel requis n'a pas pu être "
    "fourni intégralement au modèle."
)


@dataclass(frozen=True)
class VerificationContext:
    """Context supplied by the existing course/Notion layer.

    ``course_text_loader`` is the permitted bridge to that layer.  It is invoked only
    when item references exist and the caller did not already provide course text, so
    callers can pass a deterministic local/Notion/Obsidian-backed loader without this
    verifier owning credentials or a network session.
    """

    course_text: str
    item_refs: list[str]
    external_refs: list[str]
    course_text_loader: Callable[[list[str]], str | None] | None = None

    @property
    def has_pedagogical_sources(self) -> bool:
        return bool(self.course_text.strip() or self.external_refs)

    def with_loaded_course_text(self) -> VerificationContext:
        if self.course_text.strip() or not self.item_refs or self.course_text_loader is None:
            return self
        try:
            course_text = self.course_text_loader(list(self.item_refs))
        except Exception:
            course_text = None
        if not isinstance(course_text, str) or not course_text.strip():
            return replace(self, course_text_loader=None)
        return replace(self, course_text=course_text.strip(), course_text_loader=None)


def _prompt(
    question: UnessQuestion,
    context: VerificationContext,
    exam_context: dict[str, Any] | None = None,
    image_statuses: tuple[str, ...] = (),
) -> str:
    propositions = "\n".join(
        f"- {proposition.id}: {proposition.texte}" for proposition in question.propositions
    )
    official_answers = "\n".join(
        f"- {proposition.id}: "
        f"{'vrai' if proposition.reponse_uness is True else 'faux' if proposition.reponse_uness is False else 'inconnu'}"
        for proposition in question.propositions
    )
    refs = ", ".join([*context.item_refs, *context.external_refs]) or "aucune"
    source_notice = (
        "Des sources pédagogiques sont disponibles ci-dessous."
        if context.has_pedagogical_sources
        else "CONTEXTE LIMITÉ : aucune source pédagogique n'est disponible; indiquez cette limite."
    )
    general_context = json.dumps(exam_context or {}, ensure_ascii=False, sort_keys=True)
    question_context = json.dumps(question.dp_context, ensure_ascii=False, sort_keys=True)
    images = json.dumps(
        [
            {
                "index": index,
                "delivery": image_statuses[index - 1],
            }
            for index, _image in enumerate(question.images, start=1)
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    visual_notices = []
    if any(status == "unsupported" for status in image_statuses):
        visual_notices.append(
            "Vérification visuelle non prise en charge pour les images non jointes. "
            "Ne prétends pas les avoir vues et ne fonde aucun verdict sur leur contenu."
        )
    elif image_statuses:
        visual_notices.append("Les contenus image locaux sont joints à cette requête.")
    if question.support_visuel_seul:
        visual_notices.append(
            "Cette question est conservée comme support visuel uniquement : "
            "l'interaction UNESS originale n'est pas reconstruite."
        )
    visual_warning = " ".join(visual_notices) or "Interaction standard."
    return f"""Vérifie indépendamment chaque proposition d'une question UNESS.
La correction officielle sert de comparaison non autoritative : produis d'abord ton
raisonnement indépendant, puis signale toute divergence sans la résoudre silencieusement.
Retourne exclusivement un objet JSON avec la clé `propositions`, contenant exactement un
résultat par identifiant de proposition. Chaque résultat doit contenir les clés : id,
verdict_ia (booléen), explication_ia (explication non vide), sources_ia (liste),
confiance_ia (nombre), commentaire_desaccord (chaîne, vide seulement sans désaccord).

Question {question.id} ({question.type_question}) : {question.enonce}
Propositions :
{propositions}
Correction officielle UNESS (comparaison non autoritative) :
{official_answers}
Contexte général du dossier : {general_context}
Contexte de cette question : {question_context}
Métadonnées des images : {images}
Contrainte visuelle : {visual_warning}
Références d'items ou externes : {refs}
Contexte : {source_notice}"""


def _detected_image_mime_type(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            mime_type = _SUPPORTED_IMAGE_FORMATS.get(image.format or "")
            if mime_type is None:
                return None
            image.verify()
        with Image.open(BytesIO(data)) as image:
            while True:
                image.load()
                try:
                    image.seek(image.tell() + 1)
                except EOFError:
                    break
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return None
    return mime_type


def _local_image_content(question: UnessQuestion) -> tuple[
    tuple[AIImageContent, ...],
    tuple[str, ...],
    tuple[UnessImage, ...],
]:
    parts: list[AIImageContent] = []
    statuses: list[str] = []
    images: list[UnessImage] = []
    total_bytes = 0
    for index, image in enumerate(question.images):
        status = "unsupported"
        if image.local_path and index < _MAX_IMAGE_COUNT:
            try:
                path = import_service.resolve_local_media_path(image.local_path)
                size = path.stat().st_size
                if (
                    0 < size <= _MAX_IMAGE_BYTES
                    and total_bytes + size <= _MAX_TOTAL_IMAGE_BYTES
                ):
                    data = path.read_bytes()
                    mime_type = _detected_image_mime_type(data)
                    if mime_type is not None and len(data) == size:
                        parts.append(AIImageContent(mime_type=mime_type, data=data))
                        total_bytes += size
                        status = "provided_to_ai"
            except (FileNotFoundError, OSError, PermissionError, ValueError):
                status = "unsupported"
        statuses.append(status)
        images.append(
            replace(
                image,
                metadata={**image.metadata, "verification_status": status},
            )
        )
    return tuple(parts), tuple(statuses), tuple(images)


def _unsupported_visual_question(
    question: UnessQuestion,
    images: tuple[UnessImage, ...],
) -> UnessQuestion:
    truthful_images = tuple(
        replace(
            image,
            metadata={
                **image.metadata,
                "verification_status": (
                    "not_provided_to_ai"
                    if image.metadata.get("verification_status") == "provided_to_ai"
                    else "unsupported"
                ),
            },
        )
        for image in images
    )
    propositions = tuple(
        replace(
            proposition,
            verdict_ia=None,
            explication_ia=_UNSUPPORTED_VISUAL_EXPLANATION,
            sources_ia=(),
            confiance_ia=None,
            commentaire_desaccord="",
            statut=(
                "valide_manuellement"
                if proposition.reponse_finale is not None
                else "incertain"
            ),
        )
        for proposition in question.propositions
    )
    return replace(
        question,
        propositions=propositions,
        images=truthful_images,
        verification_status="unsupported",
    )


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
        if not isinstance(result, dict) or not result.keys() >= _REQUIRED_RESULT_KEYS:
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
    if not isinstance(verdict, bool):
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
    normalized_comment = disagreement_comment.strip()
    if _status(proposition.reponse_uness, verdict) == "desaccord" and not normalized_comment:
        raise ValueError("commentaire_desaccord est requis en cas de désaccord")
    return replace(
        proposition,
        verdict_ia=verdict,
        explication_ia=explanation.strip(),
        sources_ia=normalized_sources,
        confiance_ia=_clamped_confidence(result["confiance_ia"]),
        commentaire_desaccord=normalized_comment,
        statut=_status(proposition.reponse_uness, verdict),
    )


def verify_question(
    question: UnessQuestion,
    context: VerificationContext,
    ai_service: Any,
    *,
    exam_context: dict[str, Any] | None = None,
) -> UnessQuestion:
    """Return a verified copy; the official UNESS answer is never changed."""
    resolved_context = context.with_loaded_course_text()
    _assert_no_sensitive_data(
        {
            "question": question.to_dict(),
            "exam_context": exam_context or {},
            "course_text": resolved_context.course_text,
            "item_refs": resolved_context.item_refs,
            "external_refs": resolved_context.external_refs,
        }
    )
    image_parts, image_statuses, verified_images = _local_image_content(question)
    visual_verification_unsupported = (
        bool(question.images) and "unsupported" in image_statuses
    ) or (question.support_visuel_seul and not question.images)
    if visual_verification_unsupported:
        return _unsupported_visual_question(question, verified_images)
    response = ai_service.generate(
        AITask.QCM,
        _prompt(question, resolved_context, exam_context, image_statuses),
        context=resolved_context.course_text or None,
        response_format="json",
        images=image_parts,
    )
    results = _result_by_id(_json_payload(response.text), question)
    return replace(
        question,
        propositions=tuple(
            _verified_proposition(proposition, results[proposition.id], resolved_context)
            for proposition in question.propositions
        ),
        images=verified_images,
        verification_status="verified",
    )


def verify_exam(exam: UnessExam, context: VerificationContext, ai_service: Any) -> UnessExam:
    """Verify every question of a local exam with the same source context."""
    resolved_context = context.with_loaded_course_text()
    return replace(
        exam,
        questions=tuple(
            verify_question(
                question,
                resolved_context,
                ai_service,
                exam_context=exam.dp_context,
            )
            for question in exam.questions
        ),
    )
