from __future__ import annotations

import datetime

from backend.core.anki.models import AnkiCard, AnkiConnectionStatus
from backend.core.anki.review import AnkiReviewController


class FakeClient:
    def __init__(self):
        self.answered = []

    def ping(self):
        return AnkiConnectionStatus(True)

    def find_cards(self, query):
        assert query == 'deck:"Fiches EDN Notion::*221*"'
        return [1, 2]

    def cards_info(self, ids):
        return [
            AnkiCard(1, 11, "Fiches EDN Notion::Cardiologie::221. Athérome", "Basic", {"Front": "Q1"}, (), 0, 0, 0, 0, 0, 0),
            AnkiCard(2, 12, "Fiches EDN Notion::Cardiologie::221. Athérome", "Basic", {"Front": "Q2"}, (), 0, 0, 0, 0, 0, 0),
        ]

    def answer_card(self, card_id, ease):
        self.answered.append((card_id, ease))
        return {"cardId": card_id, "noteId": card_id + 10, "ease": ease, "interval": 7, "reviewedAt": 1700000000000}


class FakeStore:
    def __init__(self):
        self.events = []

    def record_anki_review(self, *args):
        self.events.append(args)
        return "event"


def test_controller_loads_cards_for_an_item():
    controller = AnkiReviewController(FakeClient(), FakeStore())

    card = controller.load_next("221")

    assert card.card_id == 1
    assert card.fields["Front"] == "Q1"


def test_controller_answers_with_anki_ease_and_records_evidence():
    client = FakeClient()
    store = FakeStore()
    controller = AnkiReviewController(client, store)
    controller.load_next("221")

    next_card = controller.answer_current(3)

    assert client.answered == [(1, 3)]
    assert store.events[0][0:4] == (1, 11, ("221",), "good")
    assert isinstance(store.events[0][4], datetime.datetime)
    assert next_card.card_id == 2
