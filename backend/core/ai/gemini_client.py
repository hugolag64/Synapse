"""Transport HTTP minimal vers la Gemini Developer API."""
from __future__ import annotations

import base64
import re
import time
from collections.abc import Sequence
from typing import Any

import requests

from backend.config.settings import settings
from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AIServiceError


class GeminiClientError(AIServiceError):
    """Erreur réseau, authentification ou contrat de réponse Gemini."""


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(error, requests.HTTPError):
        status_code = getattr(error.response, "status_code", None)
        return status_code == 429 or (status_code is not None and status_code >= 500)
    return False


def _redact_provider_secrets(message: str) -> str:
    """Remove provider API keys from URLs before errors reach logs or UI."""
    return re.sub(r"([?&]key=)[^&\s]+", r"\1***", str(message))


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
        response_schema: dict[str, Any] | None = None,
        images: Sequence[AIImageContent] = (),
        task_name: str | None = None,
        context: str | None = None,
    ) -> AIResponse:
        if not self.api_key:
            raise GeminiClientError("Aucune clé Gemini configurée")
        if model not in self.models:
            raise GeminiClientError(f"Modèle Gemini inconnu : {model!r}")

        t_name = task_name or "gemini_generate"
        generation_config: dict[str, Any] = {}
        if response_format == "json":
            generation_config["responseMimeType"] = "application/json"
            if response_schema:
                generation_config["responseSchema"] = response_schema
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
        start_time = time.perf_counter()
        response = None
        data = None
        for _attempt, delay in enumerate((0.5, 1.0, None)):
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": self.api_key},
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                break
            except Exception as exc:
                if delay is not None and _is_retryable_error(exc):
                    time.sleep(delay)
                    continue
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                from backend.core.ai.logger import log_ai_call
                safe_error = _redact_provider_secrets(str(exc))
                log_ai_call(task=t_name, model=model, input_tokens=0, output_tokens=0, duration_ms=duration_ms, error=safe_error, context=context)
                raise GeminiClientError(f"Gemini inaccessible : {safe_error}") from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        candidate = (data.get("candidates") or [{}])[0] if isinstance(data, dict) else {}
        finish_reason = str(candidate.get("finishReason") or "").upper()
        if finish_reason in {"MAX_TOKENS", "SAFETY"}:
            message = f"Réponse Gemini {finish_reason.lower()}"
            from backend.core.ai.logger import log_ai_call
            log_ai_call(
                task=t_name,
                model=model,
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                error=message,
                context=context,
            )
            raise GeminiClientError(message)

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            from backend.core.ai.logger import log_ai_call
            log_ai_call(task=t_name, model=model, input_tokens=0, output_tokens=0, duration_ms=duration_ms, error="Réponse Gemini invalide", context=context)
            raise GeminiClientError("Réponse Gemini invalide") from exc

        if not text:
            from backend.core.ai.logger import log_ai_call
            log_ai_call(task=t_name, model=model, input_tokens=0, output_tokens=0, duration_ms=duration_ms, error="Réponse Gemini vide", context=context)
            raise GeminiClientError("Réponse Gemini vide")

        usage = data.get("usageMetadata") or {}
        in_tok = usage.get("promptTokenCount")
        out_tok = usage.get("candidatesTokenCount")
        thoughts_tok = usage.get("thoughtsTokenCount")

        from backend.core.ai.logger import log_ai_call
        log_ai_call(task=t_name, model=model, input_tokens=in_tok, output_tokens=out_tok, duration_ms=duration_ms, context=context)

        return AIResponse(
            text=text,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            provider="gemini",
            finish_reason=finish_reason or None,
            thoughts_tokens=thoughts_tok,
        )
