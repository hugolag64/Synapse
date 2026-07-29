from unittest.mock import MagicMock, patch

import pytest

from backend.core.ai.gemini_client import GeminiClient, GeminiClientError
from backend.core.ai.routing import AIModel


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.side_effect = (
        RuntimeError(f"HTTP {status_code}") if status_code >= 400 else None
    )
    return response


def test_generate_sends_selected_model_and_returns_usage():
    payload = {
        "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4},
    }
    client = GeminiClient(api_key="secret", timeout_seconds=9)

    with patch("requests.post", return_value=_response(payload)) as post:
        result = client.generate("Prompt", AIModel.FLASH_LITE)

    assert result.text == "OK"
    assert result.model is AIModel.FLASH_LITE
    assert result.input_tokens == 11
    assert result.output_tokens == 4
    url = post.call_args.args[0]
    assert "/models/gemini-3.1-flash-lite:generateContent" in url
    assert post.call_args.kwargs["params"] == {"key": "secret"}
    assert post.call_args.kwargs["json"] == {
        "contents": [{"parts": [{"text": "Prompt"}]}]
    }
    assert post.call_args.kwargs["timeout"] == 9


def test_generate_requests_json_response_format():
    client = GeminiClient(api_key="secret")
    with patch("requests.post", return_value=_response({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})) as post:
        client.generate("Prompt", AIModel.FLASH, response_format="json")

    config = post.call_args.kwargs["json"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"


def test_generate_wraps_http_errors_without_exposing_key():
    client = GeminiClient(api_key="super-secret")
    with patch("requests.post", side_effect=TimeoutError("network timeout")), pytest.raises(
        GeminiClientError, match="Gemini inaccessible"
    ) as error:
        client.generate("Prompt", AIModel.FLASH)
    assert "super-secret" not in str(error.value)


def test_generate_rejects_missing_api_key():
    with pytest.raises(GeminiClientError, match="clé Gemini"):
        GeminiClient(api_key="").generate("Prompt", AIModel.FLASH_LITE)


def test_generate_rejects_empty_provider_response():
    client = GeminiClient(api_key="secret")
    payload = {"candidates": [{"content": {"parts": []}}]}
    with patch("requests.post", return_value=_response(payload)), pytest.raises(
        GeminiClientError, match="Réponse Gemini vide"
    ):
        client.generate("Prompt", AIModel.FLASH)
