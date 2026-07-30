"""Transport HTTP minimal vers la Gemini Developer API."""
from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import requests

from backend.config.settings import settings
from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AIServiceError


class GeminiClientError(AIServiceError):
    """Erreur réseau, authentification ou contrat de réponse Gemini."""


class GeminiClient:
    _base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        lite_model: str | None = None,
        flash_model: str | None = None,
    ) -> None:
        self.api_key = settings.gemini_api_key if api_key is None else api_key
        self.timeout_seconds = (
            settings.gemini_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        self.models = {
            AIModel.FLASH_LITE: lite_model or settings.gemini_lite_model,
            AIModel.FLASH: flash_model or settings.gemini_flash_model,
        }

    def generate(
        self,
        prompt: str,
        model: AIModel,
        response_format: str = "text",
        *,
        images: Sequence[AIImageContent] = (),
    ) -> AIResponse:
        if not self.api_key:
            raise GeminiClientError("Aucune clé Gemini configurée")
        if model not in self.models:
            raise GeminiClientError(f"Modèle Gemini inconnu : {model!r}")

        generation_config: dict[str, Any] = {}
        if response_format == "json":
            generation_config["responseMimeType"] = "application/json"
        parts: list[dict[str, Any]] = [{"text": prompt}]
        parts.extend(
            {
                "inlineData": {
                    "mimeType": image.mime_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                }
            }
            for image in images
        )
        payload: dict[str, Any] = {"contents": [{"parts": parts}]}
        if generation_config:
            payload["generationConfig"] = generation_config

        url = f"{self._base_url}/{self.models[model]}:generateContent"
        try:
            response = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise GeminiClientError(f"Gemini inaccessible : {exc}") from exc

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiClientError("Réponse Gemini invalide") from exc
        if not text:
            raise GeminiClientError("Réponse Gemini vide")

        usage = data.get("usageMetadata") or {}
        return AIResponse(
            text=text,
            model=model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )
