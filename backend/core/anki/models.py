from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnkiConnectionStatus:
    connected: bool
    reason: str | None = None


@dataclass(frozen=True)
class AnkiCard:
    card_id: int
    note_id: int | None
    deck_name: str
    model_name: str
    fields: dict[str, str]
    tags: tuple[str, ...]
    interval: int
    queue: int
    card_type: int
    due: int
    reps: int
    lapses: int
    question_html: str = ""
    answer_html: str = ""
    css: str = ""
