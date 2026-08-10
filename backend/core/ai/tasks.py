"""Points d'entrée IA réutilisables par les futurs parcours métier."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from backend.core.ai.gemini_client import GeminiClient
from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask
from backend.core.ai.service import AIService


def _default_service() -> AIService:
    return AIService(GeminiClient())


def generate_qcm(
    prompt: str,
    *,
    rank: str | None = None,
    service: AIService | None = None,
) -> AIResponse:
    extra_instructions = ""
    if rank == "A":
        extra_instructions = "\nCONSIGNE RANG : Génère exclusivement des questions de RANG A (connaissances indispensables, diagnostics de première intention, urgences vitales)."
    elif rank == "B":
        extra_instructions = "\nCONSIGNE RANG : Génère exclusivement des questions de RANG B (spécialité approfondie, diagnostics de 2nde intention, détails experts)."

    full_prompt = (
        f"{prompt}{extra_instructions}\n"
        "Pour chaque question du JSON généré, inclus obligatoirement le champ \"rank\": \"A\" ou \"B\" selon la nature de la question."
    )
    return (service or _default_service()).generate(AITask.QCM, full_prompt, response_format="json")


def generate_ecos(
    prompt: str,
    *,
    complex_case: bool = False,
    service: AIService | None = None,
) -> AIResponse:
    task = AITask.ECOS_COMPLEX if complex_case else AITask.ECOS_SIMPLE
    return (service or _default_service()).generate(task, prompt, response_format="json")


def generate_dp(prompt: str, *, service: AIService | None = None) -> AIResponse:
    return (service or _default_service()).generate(AITask.DP, prompt, response_format="json")


def generate_kfp(prompt: str, *, service: AIService | None = None) -> AIResponse:
    return (service or _default_service()).generate(AITask.KFP, prompt, response_format="json")


def generate_uness_correction(
    prompt: str,
    *,
    images: Sequence[AIImageContent] = (),
    context: str | None = None,
    service: AIService | None = None,
) -> UnessCorrectionResult:
    # Only worth the pricier visual-reasoning model when there's actually an image
    # to analyze (DP/scanner questions) — plain text corrections stay on the cheap
    # Lite tier, which is most of a typical partiel's sub-parts.
    task = AITask.UNESS_CORRECTION_VISUAL if images else AITask.UNESS_CORRECTION
    response = (service or _default_service()).generate(
        task, prompt, response_format="json", images=images, context=context
    )
    return UnessCorrectionResult(
        response=response,
        requires_human_validation=bool(images),
        status="pending_human_validation" if images else "final",
    )


@dataclass(frozen=True)
class UnessCorrectionResult:
    response: AIResponse
    requires_human_validation: bool
    status: Literal["final", "pending_human_validation"]

    @property
    def text(self) -> str:
        return self.response.text

    @property
    def model(self) -> AIModel:
        return self.response.model

    @property
    def input_tokens(self) -> int | None:
        return self.response.input_tokens

    @property
    def output_tokens(self) -> int | None:
        return self.response.output_tokens


def classify_item(
    prompt: str, *, service: AIService | None = None, force_model: AIModel | None = None
) -> AIResponse:
    """Détermine le(s) item(s) EDN concernés par une annale/question, parmi une
    liste de candidats fournie dans le prompt. Modèle bon marché (flash-lite)
    par défaut — tâche de classification courte, pas de génération de contenu
    médical.

    `force_model` court-circuite le routage habituel (utile pour une passe de
    correction ciblée avec le modèle Flash, plus fiable sur les longues listes
    de candidats — flash-lite a tendance à recopier toute la liste au lieu de
    discriminer)."""
    svc = service or _default_service()
    if force_model is not None:
        return svc.client.generate(
            prompt, force_model, response_format="json",
            task_name=str(AITask.ITEM_CLASSIFICATION), context=None,
        )
    return svc.generate(AITask.ITEM_CLASSIFICATION, prompt, response_format="json")


def infer_ednpro_ranks(
    prompt: str,
    *,
    service: AIService | None = None,
) -> AIResponse:
    """Classify a batch of EDNpro questions against one item's OIC context."""
    return (service or _default_service()).generate(
        AITask.ITEM_CLASSIFICATION,
        prompt,
        response_format="json",
    )


@dataclass(frozen=True)
class GridExtractionResult:
    response: AIResponse
    requires_human_validation: bool = True


def extract_grid(prompt: str, *, service: AIService | None = None) -> GridExtractionResult:
    response = (service or _default_service()).generate(
        AITask.EXTRACTION_GRILLE,
        prompt,
        response_format="json",
    )
    return GridExtractionResult(response=response)
