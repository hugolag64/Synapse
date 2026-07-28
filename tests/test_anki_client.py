from __future__ import annotations

import json
import base64
import urllib.error

import pytest

from backend.core.anki.client import AnkiClient, AnkiConnectError


def _install_response(monkeypatch, payload: dict) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())


def test_ping_and_find_cards_send_anki_connect_payload(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"result": [11, 12], "error": None}).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = AnkiClient(timeout_seconds=1.25)

    assert client.ping().connected is True
    assert client.find_cards('deck:"Fiches EDN Notion"') == [11, 12]
    assert json.loads(requests[0][0].data)["action"] == "version"
    assert json.loads(requests[1][0].data)["params"]["query"] == 'deck:"Fiches EDN Notion"'
    assert requests[0][1] == pytest.approx(1.25)


def test_cards_info_normalizes_card_fields_and_missing_tags(monkeypatch):
    _install_response(
        monkeypatch,
        {
            "result": [
                {
                    "cardId": 42,
                    "note": 99,
                    "deckName": "Fiches EDN Notion::Cardiologie::221. Athérome",
                    "modelName": "Image Occlusion Enhanced+",
                    "fields": {"ID (hidden)": {"value": "external-1"}},
                    "interval": 7,
                    "queue": 2,
                    "type": 2,
                    "due": 123,
                    "reps": 4,
                    "lapses": 1,
                    "question": "<div>question</div>",
                    "answer": "<div>answer</div>",
                    "css": ".card{}",
                }
            ],
            "error": None,
        },
    )

    card = AnkiClient().cards_info([42])[0]

    assert card.card_id == 42
    assert card.note_id == 99
    assert card.fields["ID (hidden)"] == "external-1"
    assert card.tags == ()
    assert card.interval == 7
    assert card.reps == 4
    assert card.question_html == "<div>question</div>"
    assert card.answer_html == "<div>answer</div>"


def test_anki_error_and_network_error_are_explicit(monkeypatch):
    _install_response(monkeypatch, {"result": None, "error": "unsupported action"})
    client = AnkiClient()

    with pytest.raises(AnkiConnectError, match="unsupported action"):
        client.find_cards("deck:Default")

    def fail(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    status = client.ping()
    assert status.connected is False
    assert "connection refused" in (status.reason or "")


def test_reviews_are_returned_by_card_id(monkeypatch):
    _install_response(
        monkeypatch,
        {
            "result": {"42": [{"id": 1700000000000, "ease": 3}]},
            "error": None,
        },
    )

    assert AnkiClient().get_reviews([42]) == {42: [{"id": 1700000000000, "ease": 3}]}


def test_answer_card_returns_native_scheduler_state(monkeypatch):
    _install_response(
        monkeypatch,
        {
            "result": {"cardId": 42, "ease": 3, "interval": 7, "reviewedAt": 1700000000000},
            "error": None,
        },
    )

    assert AnkiClient().answer_card(42, 3)["interval"] == 7


def test_retrieve_media_file_decodes_anki_media(monkeypatch):
    encoded = base64.b64encode(b"svg-data").decode("ascii")
    _install_response(monkeypatch, {"result": encoded, "error": None})

    assert AnkiClient().retrieve_media_file("answer.svg") == b"svg-data"
