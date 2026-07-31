"""Points d'entrée IA réutilisables par les futurs parcours métier."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.core.ai.gemini_client import GeminiClient
from backend.core.ai.routing import AIImageContent, AIResponse, AITask
from backend.core.ai.service import AIService


def _default_service() -> AIService:
    return AIService(GeminiClient())


def generate_qcm(prompt: str, *, service: AIService | None = None) -> AIResponse:
    return (service or _default_service()).generate(AITask.QCM, prompt, response_format="json")


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
    service: AIService | None = None,
) -> AIResponse:
    # Only worth the pricier visual-reasoning model when there's actually an image
    # to analyze (DP/scanner questions) — plain text corrections stay on the cheap
    # Lite tier, which is most of a typical partiel's sub-parts.
    task = AITask.UNESS_CORRECTION_VISUAL if images else AITask.UNESS_CORRECTION
    return (service or _default_service()).generate(
        task, prompt, response_format="json", images=images
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
