"""Modèles métier des sessions d'entraînement IA."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PracticeKind(StrEnum):
    OIC = "OIC"
    QCM = "QCM"
    DP = "DP"
    KFP = "KFP"


class PracticeDifficulty(StrEnum):
    STANDARD = "standard"
    EDN = "edn"
    DIFFICULT = "difficile"
    CONCOURS = "concours"


class QuestionKind(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class PracticeSessionSpec:
    """Paramètres validés d'une session, sans dépendance à l'interface."""

    practice_kind: PracticeKind
    total_questions: int
    open_questions: int = 0
    closed_questions: int = 0
    item_number: str = ""
    course_id: str = ""
    course_title: str = ""
    objective_code: str = ""
    difficulty: PracticeDifficulty = PracticeDifficulty.EDN

    def __post_init__(self) -> None:
        if self.total_questions <= 0:
            raise ValueError("Une session doit contenir au moins une question")
        if self.open_questions < 0 or self.closed_questions < 0:
            raise ValueError("Le nombre de questions ne peut pas être négatif")
        if self.open_questions + self.closed_questions != self.total_questions:
            raise ValueError(
                "La somme des questions ouvertes et fermées doit égaler le total"
            )
        if not isinstance(self.practice_kind, PracticeKind):
            raise ValueError("Type de session inconnu")
        if not isinstance(self.difficulty, PracticeDifficulty):
            raise ValueError("Niveau de difficulté inconnu")


@dataclass(frozen=True)
class GeneratedQuestion:
    prompt: str
    kind: QuestionKind
    answer: str
    explanation: str
    choices: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("Une question doit avoir un énoncé")
        if not self.answer.strip():
            raise ValueError("Une question doit avoir une correction")
        if not self.explanation.strip():
            raise ValueError("Une question doit avoir une explication")
        if self.kind is QuestionKind.CLOSED and len(self.choices) < 2:
            raise ValueError("Une question fermée doit avoir au moins deux choix")
