from __future__ import annotations

import json
import base64
import urllib.error
import urllib.request
from typing import Any

from .models import AnkiCard, AnkiConnectionStatus


class AnkiConnectError(RuntimeError):
    """Raised when AnkiConnect returns an API error or malformed response."""


class AnkiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout_seconds: float = 2.5) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        payload = {"action": action, "version": 6}
        if params:
            payload["params"] = params
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (OSError, urllib.error.URLError) as exc:
            raise AnkiConnectError(str(exc)) from exc
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AnkiConnectError("AnkiConnect returned invalid JSON") from exc
        if body.get("error") is not None:
            raise AnkiConnectError(str(body["error"]))
        return body.get("result")

    def ping(self) -> AnkiConnectionStatus:
        try:
            self._invoke("version")
        except AnkiConnectError as exc:
            return AnkiConnectionStatus(False, str(exc))
        return AnkiConnectionStatus(True)

    def find_cards(self, query: str) -> list[int]:
        return [int(card_id) for card_id in (self._invoke("findCards", {"query": query}) or [])]

    def cards_info(self, card_ids: list[int]) -> list[AnkiCard]:
        result = self._invoke("cardsInfo", {"cards": card_ids}) or []
        return [self._card_from_payload(payload) for payload in result]

    def get_reviews(self, card_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        result = self._invoke("getReviewsOfCards", {"cards": card_ids}) or {}
        return {int(card_id): list(reviews or []) for card_id, reviews in result.items()}

    def answer_card(self, card_id: int, ease: int) -> dict[str, Any]:
        if ease not in (1, 2, 3, 4):
            raise ValueError("ease must be between 1 and 4")
        result = self._invoke("synapseAnswerCard", {"cardId": int(card_id), "ease": int(ease)})
        if not isinstance(result, dict):
            raise AnkiConnectError("AnkiConnect returned an invalid answer state")
        return result

    def retrieve_media_file(self, filename: str) -> bytes | None:
        result = self._invoke("retrieveMediaFile", {"filename": filename})
        if result is False or result is None:
            return None
        try:
            return base64.b64decode(result)
        except (TypeError, ValueError) as exc:
            raise AnkiConnectError(f"Invalid media returned for {filename}") from exc

    @staticmethod
    def _card_from_payload(payload: dict[str, Any]) -> AnkiCard:
        fields: dict[str, str] = {}
        for name, value in (payload.get("fields") or {}).items():
            fields[name] = str(value.get("value", "") if isinstance(value, dict) else value)
        tags = tuple(str(tag) for tag in (payload.get("tags") or []) if tag)
        return AnkiCard(
            card_id=int(payload["cardId"]),
            note_id=int(payload["note"]) if payload.get("note") is not None else None,
            deck_name=str(payload.get("deckName", "")),
            model_name=str(payload.get("modelName", "")),
            fields=fields,
            tags=tags,
            interval=int(payload.get("interval", 0) or 0),
            queue=int(payload.get("queue", 0) or 0),
            card_type=int(payload.get("type", 0) or 0),
            due=int(payload.get("due", 0) or 0),
            reps=int(payload.get("reps", 0) or 0),
            lapses=int(payload.get("lapses", 0) or 0),
            question_html=str(payload.get("question", "") or ""),
            answer_html=str(payload.get("answer", "") or ""),
            css=str(payload.get("css", "") or ""),
        )
