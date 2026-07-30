"""Typed local inputs used to normalize a captured UNESS review."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExamMetadata:
    """Human-confirmed metadata kept alongside the captured public review content."""

    faculte: str
    niveau: str
    matiere: str
    type_epreuve: str
    annee: int | None
    titre: str
    source_url: str


@dataclass(frozen=True)
class RawMedia:
    """A downloaded visual asset, without browser or account state."""

    filename: str
    content: bytes
    mime_type: str
    question_number: int | None = None
    role: str = "support"


@dataclass(frozen=True)
class RawUnessArtifact:
    """Local HTML snapshots and media collected after the user has reviewed an attempt."""

    source_url: str
    html_by_content: dict[str, str]
    media: list[RawMedia]
    artifact_root: Path | None = field(default=None, compare=False)
