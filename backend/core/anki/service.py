from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .mapping import parse_item_numbers
from .models import AnkiCard, AnkiConnectionStatus


class AnkiReadClient(Protocol):
    def ping(self) -> AnkiConnectionStatus: ...

    def find_cards(self, query: str) -> list[int]: ...

    def cards_info(self, card_ids: list[int]) -> list[AnkiCard]: ...


@dataclass(frozen=True)
class AnkiSyncSnapshot:
    connected: bool
    reason: str | None
    total_cards: int
    mapped_cards: int
    item_card_ids: dict[str, tuple[int, ...]]
    item_note_ids: dict[str, tuple[int, ...]]
    unmapped_card_ids: tuple[int, ...]
    synced_at: datetime


class AnkiSyncService:
    def __init__(self, client: AnkiReadClient) -> None:
        self.client = client

    def sync_fiches_edn(self) -> AnkiSyncSnapshot:
        status = self.client.ping()
        now = datetime.now(timezone.utc)
        if not status.connected:
            return AnkiSyncSnapshot(False, status.reason, 0, 0, {}, {}, (), now)

        card_ids = self.client.find_cards('deck:"Fiches EDN Notion"')
        cards = self.client.cards_info(card_ids)
        item_card_ids: dict[str, list[int]] = {}
        item_note_ids: dict[str, list[int]] = {}
        unmapped: list[int] = []
        for card in cards:
            items = parse_item_numbers(card.deck_name)
            if not items:
                unmapped.append(card.card_id)
                continue
            for item_number in items:
                item_card_ids.setdefault(item_number, []).append(card.card_id)
                if card.note_id is not None:
                    item_note_ids.setdefault(item_number, []).append(card.note_id)

        return AnkiSyncSnapshot(
            True,
            None,
            len(cards),
            len(cards) - len(unmapped),
            {key: tuple(dict.fromkeys(value)) for key, value in item_card_ids.items()},
            {key: tuple(dict.fromkeys(value)) for key, value in item_note_ids.items()},
            tuple(unmapped),
            now,
        )
