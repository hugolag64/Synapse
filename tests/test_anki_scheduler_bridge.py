from __future__ import annotations

import pytest

from scripts.anki_addon.synapse_bridge.bridge import AnkiBridgeError, answer_card


class FakeCard:
    def __init__(self):
        self.id = 42
        self.note = type("Note", (), {"id": 99})()
        self.interval = 0
        self.queue = 0
        self.type = 0
        self.due = 0
        self.reps = 0
        self.lapses = 0


class FakeScheduler:
    def __init__(self, card):
        self.card = card
        self.calls = []

    def answerCard(self, card, ease):
        self.calls.append((card.id, ease))
        card.interval = 7
        card.queue = 2
        card.type = 2
        card.due = 123
        card.reps = 4
        card.lapses = 1


class FakeCollection:
    def __init__(self, card):
        self.card = card
        self.sched = FakeScheduler(card)

    def getCard(self, card_id):
        return self.card if card_id == self.card.id else None


class FakeMw:
    def __init__(self):
        self.col = FakeCollection(FakeCard())


def test_answer_card_uses_native_scheduler_once():
    mw = FakeMw()

    result = answer_card(mw, 42, 3, reviewed_at_ms=1700000000000)

    assert mw.col.sched.calls == [(42, 3)]
    assert result == {
        "cardId": 42,
        "noteId": 99,
        "ease": 3,
        "interval": 7,
        "queue": 2,
        "type": 2,
        "due": 123,
        "reps": 4,
        "lapses": 1,
        "reviewedAt": 1700000000000,
    }


@pytest.mark.parametrize("ease", [0, 5, -1])
def test_answer_card_rejects_invalid_ease_without_mutation(ease):
    mw = FakeMw()

    with pytest.raises(AnkiBridgeError):
        answer_card(mw, 42, ease)
    assert mw.col.sched.calls == []


def test_answer_card_rejects_unknown_card_without_mutation():
    mw = FakeMw()

    with pytest.raises(AnkiBridgeError, match="not found"):
        answer_card(mw, 404, 3)
    assert mw.col.sched.calls == []
