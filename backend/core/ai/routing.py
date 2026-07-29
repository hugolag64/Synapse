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
    ECOS_COMPLEX = "ecos_complex"
    EXTRACTION_GRILLE = "extraction_grille"
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
    if normalized in (AITask.OIC, AITask.QCM, AITask.ECOS_SIMPLE):
        return AIModel.FLASH_LITE
    return AIModel.FLASH
