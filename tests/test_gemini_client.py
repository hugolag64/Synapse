from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.core.ai.gemini_client import GeminiClient, GeminiClientError
from backend.core.ai.routing import AIImageContent, AIModel


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
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4, "thoughtsTokenCount": 2},
    }
    client = GeminiClient(api_key="secret", timeout_seconds=9)

    with patch("requests.post", return_value=_response(payload)) as post:
        result = client.generate("Prompt", AIModel.FLASH_LITE)

    assert result.text == "OK"
    assert result.model is AIModel.FLASH_LITE
    assert result.input_tokens == 11
    assert result.output_tokens == 4
    assert result.provider == "gemini"
    assert result.thoughts_tokens == 2
    url = post.call_args.args[0]
    assert "/models/gemini-3.1-flash-lite:generateContent" in url
    assert post.call_args.kwargs["headers"] == {"x-goog-api-key": "secret"}
    assert "params" not in post.call_args.kwargs
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


def test_generate_accepts_a_json_response_schema_for_structured_tasks():
    client = GeminiClient(api_key="secret")
    schema = {"type": "OBJECT", "properties": {"score": {"type": "NUMBER"}}}
    with patch("requests.post", return_value=_response({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})) as post:
        client.generate("Prompt", AIModel.FLASH, response_format="json", response_schema=schema)

    assert post.call_args.kwargs["json"]["generationConfig"]["responseSchema"] == schema


def test_generate_retries_transient_network_failure_with_bounded_backoff():
    payload = {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    client = GeminiClient(api_key="secret")

    with patch(
        "requests.post",
        side_effect=[requests.Timeout("temporary"), _response(payload)],
    ) as post, patch("time.sleep") as sleep:
        result = client.generate("Prompt", AIModel.FLASH)

    assert result.text == "OK"
    assert post.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_generate_serializes_image_bytes_as_inline_content_without_local_identifiers():
    """Catches local image paths or source URLs leaking into the provider payload."""
    client = GeminiClient(api_key="secret")
    response = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    with patch("requests.post", return_value=_response(response)) as post:
        client.generate(
            "Inspecte le support joint",
            AIModel.FLASH,
            response_format="json",
            images=(AIImageContent(mime_type="image/png", data=b"png-fixture"),),
        )

    parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
    assert parts == [
        {"text": "Inspecte le support joint"},
        {
            "inlineData": {
                "mimeType": "image/png",
                "data": "cG5nLWZpeHR1cmU=",
            }
        },
    ]
    assert "local_path" not in str(parts)
    assert "source_url" not in str(parts)


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


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY"])
def test_generate_distinguishes_truncated_or_filtered_provider_response(finish_reason):
    client = GeminiClient(api_key="secret")
    payload = {
        "candidates": [
            {"finishReason": finish_reason, "content": {"parts": [{"text": "partial"}]}}
        ]
    }

    with patch("requests.post", return_value=_response(payload)), pytest.raises(
        GeminiClientError, match="Réponse Gemini"
    ) as error:
        client.generate("Prompt", AIModel.FLASH)

    assert finish_reason.lower() in str(error.value).lower()
