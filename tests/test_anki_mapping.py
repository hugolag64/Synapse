from __future__ import annotations

from backend.core.anki.mapping import parse_item_numbers
from backend.core.anki.models import AnkiCard
from backend.core.anki.service import AnkiSyncService


def test_parse_item_numbers_supports_single_and_multi_item_decks():
    assert parse_item_numbers("Fiches EDN Notion::Cardiologie::221. Athérome") == ("221",)
    assert parse_item_numbers(
        "Fiches EDN Notion::Cardiologie::231, 232, 236, 237, 342. Rythmologie"
    ) == ("231", "232", "236", "237", "342")


def test_parse_item_numbers_rejects_unrelated_or_malformed_decks():
    assert parse_item_numbers("Médecine - EDN::Cardiologie::221. Athérome") == ()
    assert parse_item_numbers("Fiches EDN Notion::Cardiologie::Cardiologie") == ()


class FakeAnkiClient:
    def ping(self):
        return type("Status", (), {"connected": True, "reason": None})()

    def find_cards(self, query):
        assert query == 'deck:"Fiches EDN Notion"'
        return [1, 2, 3]

    def cards_info(self, card_ids):
        return [
            AnkiCard(1, 10, "Fiches EDN Notion::Cardiologie::221. Athérome", "Basic", {}, (), 0, 0, 0, 0, 0, 0),
            AnkiCard(2, 11, "Fiches EDN Notion::Cardiologie::231, 232. Rythmologie", "Basic", {}, (), 0, 0, 0, 0, 0, 0),
            AnkiCard(3, 12, "Médecine - EDN::Cardiologie::221. Athérome", "Basic", {}, (), 0, 0, 0, 0, 0, 0),
        ]


def test_sync_snapshot_maps_cards_once_and_reports_unmapped_cards():
    snapshot = AnkiSyncService(FakeAnkiClient()).sync_fiches_edn()

    assert snapshot.connected is True
    assert snapshot.total_cards == 3
    assert snapshot.mapped_cards == 2
    assert snapshot.item_card_ids["221"] == (1,)
    assert snapshot.item_card_ids["231"] == (2,)
    assert snapshot.item_card_ids["232"] == (2,)
    assert snapshot.unmapped_card_ids == (3,)
