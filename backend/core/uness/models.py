"""Contrat de données canonique et local des examens UNESS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

UnessStatus = Literal["concordant", "desaccord", "incertain", "valide_manuellement"]
UnessQuestionType = Literal["QRM", "QRU", "QRP/L", "DP", "KFP", "QROC"]

_STATUTS = {"concordant", "desaccord", "incertain", "valide_manuellement"}
_QUESTION_TYPES = {"QRM", "QRU", "QRP/L", "DP", "KFP", "QROC"}
_SENSITIVE_KEYS = {
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "localstorage",
    "sessiontoken",
    "sessiontokens",
}


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field_name} doit être un booléen ou null")
    return value


def _assert_no_sensitive_data(value: Any) -> None:
    if isinstance(value, dict):
        for key in value:
            normalized_key = "".join(character for character in key.lower() if character.isalnum())
            if normalized_key in _SENSITIVE_KEYS:
                raise ValueError(f"Donnée sensible interdite: {key}")
        for child in value.values():
            _assert_no_sensitive_data(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_sensitive_data(child)


@dataclass(frozen=True)
class UnessImage:
    source_url: str = ""
    local_path: str = ""
    alt_text: str = ""
    caption: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UnessImage:
        return cls(
            source_url=str(payload.get("source_url", "")),
            local_path=str(payload.get("local_path", "")),
            alt_text=str(payload.get("alt_text", "")),
            caption=str(payload.get("caption", "")),
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "local_path": self.local_path,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class UnessProposition:
    id: str
    texte: str
    reponse_uness: bool | None = None
    verdict_ia: bool | None = None
    reponse_finale: bool | None = None
    statut: UnessStatus = "incertain"
    validation_utilisateur: bool = False

    def __post_init__(self) -> None:
        for field_name in ("reponse_uness", "verdict_ia", "reponse_finale"):
            _optional_bool(getattr(self, field_name), field_name)
        if self.statut not in _STATUTS:
            raise ValueError(f"statut inconnu: {self.statut}")
        if not isinstance(self.validation_utilisateur, bool):
            raise ValueError("validation_utilisateur doit être un booléen")
        if self.reponse_finale is not None and (
            self.statut != "valide_manuellement" or not self.validation_utilisateur
        ):
            raise ValueError(
                "reponse_finale nécessite une validation utilisateur manuelle"
            )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UnessProposition:
        return cls(
            id=str(payload.get("id", payload.get("label", ""))),
            texte=str(payload.get("texte", payload.get("text", ""))),
            reponse_uness=payload.get("reponse_uness"),
            verdict_ia=payload.get("verdict_ia"),
            reponse_finale=payload.get("reponse_finale"),
            statut=payload.get("statut", "incertain"),
            validation_utilisateur=payload.get("validation_utilisateur", False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "texte": self.texte,
            "reponse_uness": self.reponse_uness,
            "verdict_ia": self.verdict_ia,
            "reponse_finale": self.reponse_finale,
            "statut": self.statut,
            "validation_utilisateur": self.validation_utilisateur,
        }


@dataclass(frozen=True)
class UnessQuestion:
    id: str
    type_question: UnessQuestionType
    enonce: str
    propositions: tuple[UnessProposition, ...] = ()
    images: tuple[UnessImage, ...] = ()
    support_visuel_seul: bool = False
    dp_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type_question not in _QUESTION_TYPES:
            raise ValueError(f"type_question inconnu: {self.type_question}")
        if not isinstance(self.support_visuel_seul, bool):
            raise ValueError("support_visuel_seul doit être un booléen")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UnessQuestion:
        return cls(
            id=str(payload.get("id", "")),
            type_question=payload.get("type_question", payload.get("question_type", "")),
            enonce=str(payload.get("enonce", payload.get("prompt", ""))),
            propositions=tuple(
                UnessProposition.from_dict(item) for item in payload.get("propositions", [])
            ),
            images=tuple(UnessImage.from_dict(item) for item in payload.get("images", [])),
            support_visuel_seul=payload.get("support_visuel_seul", False),
            dp_context=dict(payload.get("dp_context", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type_question": self.type_question,
            "enonce": self.enonce,
            "propositions": [item.to_dict() for item in self.propositions],
            "images": [item.to_dict() for item in self.images],
            "support_visuel_seul": self.support_visuel_seul,
            "dp_context": self.dp_context,
        }


@dataclass(frozen=True)
class UnessExam:
    """Un examen importé sans données de session et avec provenance locale."""

    schema_version: ClassVar[int] = 1
    faculty: str = ""
    level: str = ""
    year: int | None = None
    title: str = ""
    dp_context: dict[str, Any] = field(default_factory=dict)
    questions: tuple[UnessQuestion, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _assert_no_sensitive_data(self.to_dict())

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UnessExam:
        _assert_no_sensitive_data(payload)
        version = payload.get("schema_version", cls.schema_version)
        if version != cls.schema_version:
            raise ValueError(f"schema_version non supportée: {version}")
        year = payload.get("year", payload.get("annee"))
        if year is not None and (not isinstance(year, int) or isinstance(year, bool)):
            raise ValueError("year doit être un entier ou null")
        return cls(
            faculty=str(payload.get("faculty", payload.get("faculte", ""))),
            level=str(payload.get("level", payload.get("niveau", ""))),
            year=year,
            title=str(payload.get("title", "")),
            dp_context=dict(payload.get("dp_context", {})),
            questions=tuple(UnessQuestion.from_dict(item) for item in payload.get("questions", [])),
            provenance=dict(payload.get("provenance", {})),
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "faculty": self.faculty,
            "level": self.level,
            "year": self.year,
            "title": self.title,
            "dp_context": self.dp_context,
            "questions": [question.to_dict() for question in self.questions],
            "provenance": self.provenance,
            "metadata": self.metadata,
        }
