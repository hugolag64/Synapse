"""Contrat de données canonique et local des examens UNESS."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal
from urllib.parse import parse_qsl, unquote, urlparse

UnessStatus = Literal["concordant", "desaccord", "incertain", "valide_manuellement"]
UnessQuestionType = Literal["QRM", "QRU", "QRP/L", "DP", "KFP", "QROC", "TCS"]
UnessVerificationStatus = Literal["unverified", "verified", "unsupported"]

_STATUTS = {"concordant", "desaccord", "incertain", "valide_manuellement"}
_QUESTION_TYPES = {"QRM", "QRU", "QRP/L", "DP", "KFP", "QROC", "TCS"}
_VERIFICATION_STATUSES = {"unverified", "verified", "unsupported"}
UNSUPPORTED_VISUAL_EXPLANATION = (
    "Vérification IA indisponible : le support visuel requis n'a pas pu être "
    "fourni intégralement au modèle."
)
_SENSITIVE_KEYS = {
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "password",
    "clientsecret",
    "idtoken",
    "token",
    "authtoken",
    "localstorage",
    "sessionstorage",
    "sessiontoken",
    "sessiontokens",
    "accesstoken",
    "refreshtoken",
    "authorization",
    "apikey",
}
_SIGNED_URL_KEYS = {
    "awsaccesskeyid",
    "googleaccessid",
    "keypairid",
    "sig",
    "signature",
}
_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_URL_PARAMETER_PATTERN = re.compile(
    r"(?:[?&#;])\s*([A-Za-z0-9_.%+-]+)\s*=",
    re.IGNORECASE,
)
_MAX_URL_DECODE_ROUNDS = 6
_MAX_NESTED_URL_CANDIDATES = 64


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _is_sensitive_url_parameter(key: Any) -> bool:
    normalized = _normalized_key(key)
    return (
        normalized in _SENSITIVE_KEYS
        or normalized in _SIGNED_URL_KEYS
        or normalized.endswith(("credential", "secret", "signature", "token"))
    )


def _percent_decoded_candidates(value: str) -> tuple[tuple[str, ...], bool]:
    candidates = []
    current = value
    for _ in range(_MAX_URL_DECODE_ROUNDS):
        candidates.append(current)
        decoded = unquote(current)
        if decoded == current:
            return tuple(candidates), True
        current = decoded
    candidates.append(current)
    return tuple(candidates), unquote(current) == current


def _url_contains_sensitive_data(value: str) -> bool:
    pending = [value]
    seen: set[str] = set()
    while pending and len(seen) < _MAX_NESTED_URL_CANDIDATES:
        raw_candidate = pending.pop()
        decoded_candidates, reached_fixed_point = _percent_decoded_candidates(raw_candidate)
        if not reached_fixed_point:
            return True
        for candidate in decoded_candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if any(
                _is_sensitive_url_parameter(match.group(1))
                for match in _URL_PARAMETER_PATTERN.finditer(candidate)
            ):
                return True
            pending.extend(_HTTP_URL_PATTERN.findall(candidate))
            parsed = urlparse(candidate.rstrip(".,);]}"))
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
                and (parsed.username or parsed.password)
            ):
                return True
            # Do not parse arbitrary prose as a query string: parse_qsl(...,
            # keep_blank_values=True) treats the whole sentence as a key, so
            # an explanation ending in "secret" used to be misclassified as
            # a credential-bearing URL.
            query_candidates: list[str] = (
                [candidate]
                if any(marker in candidate for marker in ("?", "&", "#", "="))
                else []
            )
            for component in (parsed.query, parsed.fragment):
                if not component:
                    continue
                pending.append(component)
                query_candidates.append(component)
            for component in query_candidates:
                for key, nested_value in parse_qsl(component, keep_blank_values=True):
                    if _is_sensitive_url_parameter(key):
                        return True
                    if nested_value:
                        pending.append(nested_value)
    return bool(pending)


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field_name} doit être un booléen ou null")
    return value


def _assert_no_sensitive_data(value: Any) -> None:
    if isinstance(value, Mapping):
        for key in value:
            if _normalized_key(key) in _SENSITIVE_KEYS:
                raise ValueError(f"Donnée sensible interdite: {key}")
        for child in value.values():
            _assert_no_sensitive_data(child)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            _assert_no_sensitive_data(child)
    elif isinstance(value, str) and _url_contains_sensitive_data(value):
        raise ValueError(
            "Donnée sensible interdite dans une URL (source_url ou métadonnée)"
        )


def _assert_safe_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url doit être une URL HTTP(S) non vide")
    if _url_contains_sensitive_data(source_url):
        raise ValueError("source_url ne doit contenir aucune donnée sensible")


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
    explication_ia: str = ""
    sources_ia: tuple[str, ...] = ()
    confiance_ia: float | None = None
    commentaire_desaccord: str = ""
    reponse_finale: bool | None = None
    statut: UnessStatus = "incertain"
    validation_utilisateur: bool = False

    def __post_init__(self) -> None:
        for field_name in ("reponse_uness", "verdict_ia", "reponse_finale"):
            _optional_bool(getattr(self, field_name), field_name)
        if not isinstance(self.explication_ia, str):
            raise ValueError("explication_ia doit être une chaîne")
        if not all(isinstance(source, str) for source in self.sources_ia):
            raise ValueError("sources_ia doit contenir des chaînes")
        if self.confiance_ia is not None and (
            isinstance(self.confiance_ia, bool)
            or not isinstance(self.confiance_ia, (int, float))
        ):
            raise ValueError("confiance_ia doit être un nombre ou null")
        if not isinstance(self.commentaire_desaccord, str):
            raise ValueError("commentaire_desaccord doit être une chaîne")
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
            explication_ia=str(payload.get("explication_ia", "")),
            sources_ia=tuple(str(source) for source in payload.get("sources_ia", [])),
            confiance_ia=payload.get("confiance_ia"),
            commentaire_desaccord=str(payload.get("commentaire_desaccord", "")),
            reponse_finale=payload.get("reponse_finale"),
            statut=payload.get("statut", "incertain"),
            validation_utilisateur=payload.get("validation_utilisateur", False),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "texte": self.texte,
            "reponse_uness": self.reponse_uness,
            "verdict_ia": self.verdict_ia,
            "reponse_finale": self.reponse_finale,
            "statut": self.statut,
            "validation_utilisateur": self.validation_utilisateur,
        }
        if (
            self.explication_ia
            or self.sources_ia
            or self.confiance_ia is not None
            or self.commentaire_desaccord
        ):
            payload.update(
                {
                    "explication_ia": self.explication_ia,
                    "sources_ia": list(self.sources_ia),
                    "confiance_ia": self.confiance_ia,
                    "commentaire_desaccord": self.commentaire_desaccord,
                }
            )
        return payload


@dataclass(frozen=True)
class UnessQuestion:
    id: str
    type_question: UnessQuestionType
    enonce: str
    propositions: tuple[UnessProposition, ...] = ()
    images: tuple[UnessImage, ...] = ()
    support_visuel_seul: bool = False
    verification_status: UnessVerificationStatus = "unverified"
    dp_context: dict[str, Any] = field(default_factory=dict)
    item_numbers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.type_question not in _QUESTION_TYPES:
            raise ValueError(f"type_question inconnu: {self.type_question}")
        if not isinstance(self.support_visuel_seul, bool):
            raise ValueError("support_visuel_seul doit être un booléen")
        if self.verification_status not in _VERIFICATION_STATUSES:
            raise ValueError(f"verification_status inconnu: {self.verification_status}")
        if not all(isinstance(item, str) and item.strip() for item in self.item_numbers):
            raise ValueError("item_numbers doit contenir des chaînes non vides")

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
            verification_status=payload.get("verification_status", "unverified"),
            dp_context=dict(payload.get("dp_context", {})),
            item_numbers=tuple(dict.fromkeys(str(item).strip() for item in payload.get("item_numbers", []) if str(item).strip())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type_question": self.type_question,
            "enonce": self.enonce,
            "propositions": [item.to_dict() for item in self.propositions],
            "images": [item.to_dict() for item in self.images],
            "support_visuel_seul": self.support_visuel_seul,
            "verification_status": self.verification_status,
            "dp_context": self.dp_context,
            "item_numbers": list(self.item_numbers),
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
        for field_name in ("faculty", "level", "title"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} est requis")
        if self.year is None or isinstance(self.year, bool) or not isinstance(self.year, int):
            raise ValueError("year est requis et doit être un entier")
        required_provenance = ("source", "source_url", "collected_at", "collection_status")
        for field_name in required_provenance:
            value = self.provenance.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"provenance.{field_name} est requis")
        _assert_safe_source_url(str(self.provenance["source_url"]).strip())
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
            title=str(payload.get("title", payload.get("titre", ""))),
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
