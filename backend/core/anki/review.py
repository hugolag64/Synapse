from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .client import AnkiClient
from .mapping import parse_item_numbers
from .models import AnkiCard


class AnkiEvidenceStore(Protocol):
    def record_anki_review(self, card_id, note_id, item_numbers, rating, reviewed_at, interval, source_review_id): ...


_EASE_TO_RATING = {1: "again", 2: "hard", 3: "good", 4: "easy"}


class AnkiReviewController:
    def __init__(self, client: AnkiClient, evidence_store: AnkiEvidenceStore) -> None:
        self.client = client
        self.evidence_store = evidence_store
        self.current_card: AnkiCard | None = None
        self.current_item: str | None = None

    def load_next(self, item_number: str | None = None, exclude_card_id: int | None = None) -> AnkiCard | None:
        query = (
            f'deck:"Fiches EDN Notion::*{item_number}*"'
            if item_number
            else 'deck:"Fiches EDN Notion"'
        )
        ids = self.client.find_cards(query)
        cards = self.client.cards_info(ids)
        candidates = [
            card for card in cards
            if card.card_id != exclude_card_id
            and card.queue not in (-1, -2)
            and (item_number is None or item_number in parse_item_numbers(card.deck_name))
        ]
        self.current_card = candidates[0] if candidates else None
        self.current_item = item_number or (
            parse_item_numbers(self.current_card.deck_name)[0] if self.current_card else None
        )
        return self.current_card

    def answer_current(self, ease: int) -> AnkiCard | None:
        if self.current_card is None:
            raise RuntimeError("No Anki card is currently loaded")
        if ease not in _EASE_TO_RATING:
            raise ValueError("ease must be between 1 and 4")
        card = self.current_card
        result = self.client.answer_card(card.card_id, ease)
        item_numbers = parse_item_numbers(card.deck_name)
        reviewed_at = datetime.fromtimestamp(
            int(result.get("reviewedAt", 0)) / 1000,
            tz=timezone.utc,
        )
        self.evidence_store.record_anki_review(
            card.card_id,
            card.note_id,
            item_numbers,
            _EASE_TO_RATING[ease],
            reviewed_at,
            result.get("interval"),
            None,
        )
        return self.load_next(self.current_item, exclude_card_id=card.card_id)
