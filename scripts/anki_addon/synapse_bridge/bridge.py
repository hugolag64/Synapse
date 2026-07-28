from __future__ import annotations

import time
from typing import Any


class AnkiBridgeError(RuntimeError):
    """Raised when a card cannot safely be answered by Anki."""


def answer_card(mw: Any, card_id: int, ease: int, reviewed_at_ms: int | None = None) -> dict[str, int]:
    """Answer one card through Anki's native collection scheduler.

    ``mw`` is Anki's main-window object. Keeping this function independent from
    the AnkiConnect registration layer makes the scheduler contract testable.
    """
    if ease not in (1, 2, 3, 4):
        raise AnkiBridgeError("ease must be between 1 and 4")
    collection = getattr(mw, "col", None)
    if collection is None:
        raise AnkiBridgeError("Anki collection is unavailable")
    card = collection.getCard(int(card_id))
    if card is None:
        raise AnkiBridgeError(f"card {card_id} not found")
    scheduler = getattr(collection, "sched", None)
    if scheduler is None or not hasattr(scheduler, "answerCard"):
        raise AnkiBridgeError("Anki scheduler is unavailable")
    scheduler.answerCard(card, ease)
    return {
        "cardId": int(card.id),
        "noteId": int(card.note.id),
        "ease": int(ease),
        "interval": int(card.interval),
        "queue": int(card.queue),
        "type": int(card.type),
        "due": int(card.due),
        "reps": int(card.reps),
        "lapses": int(card.lapses),
        "reviewedAt": int(reviewed_at_ms if reviewed_at_ms is not None else time.time() * 1000),
    }
