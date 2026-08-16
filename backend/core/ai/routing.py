"""Contrats et politique pure de routage des tâches IA."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AITask(StrEnum):
    OIC = "oic"
    QCM = "qcm"
    ECOS_SIMPLE = "ecos_simple"
    DP = "dp"
    KFP = "kfp"
    FLASH_ZERO = "flash_zero"
    ECOS_COMPLEX = "ecos_complex"
    EXTRACTION_GRILLE = "extraction_grille"
    UNESS_CORRECTION = "uness_correction"
    UNESS_CORRECTION_VISUAL = "uness_correction_visual"
    UNESS_RANK = "uness_rank"
    ITEM_CLASSIFICATION = "item_classification"
    SCORE = "score"


class AIModel(StrEnum):
    FLASH_LITE = "flash_lite"
    FLASH = "flash"


class AIServiceError(RuntimeError):
    """Erreur contrôlée d'un service IA ou de son contrat de réponse."""


@dataclass(frozen=True)
class AIResponse:
    text: str
    model: AIModel
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str = "unknown"
    finish_reason: str | None = None
    thoughts_tokens: int | None = None


@dataclass(frozen=True)
class AIImageContent:
    """Local image bytes passed to a multimodal provider without filesystem metadata."""

    mime_type: str
    data: bytes

    def __post_init__(self) -> None:
        if not self.mime_type.startswith("image/"):
            raise ValueError("Le type MIME doit décrire une image")
        if not self.data:
            raise ValueError("Le contenu image ne peut pas être vide")


def model_for_task(task: AITask | str, difficulty=None) -> AIModel:
    try:
        normalized = task if isinstance(task, AITask) else AITask(task)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Tâche IA inconnue : {task!r}") from exc

    if normalized is AITask.SCORE:
        raise ValueError("Le calcul d'un score ne passe pas par le service IA")
    difficulty_value = getattr(difficulty, "value", difficulty)
    if difficulty_value in {"difficile", "concours"}:
        return AIModel.FLASH
    if normalized in (
        AITask.OIC, AITask.QCM, AITask.ECOS_SIMPLE, AITask.UNESS_CORRECTION,
        AITask.UNESS_RANK, AITask.ITEM_CLASSIFICATION,
    ):
        return AIModel.FLASH_LITE
    return AIModel.FLASH
