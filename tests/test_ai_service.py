from unittest.mock import Mock

import pytest

from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask
from backend.core.ai.service import MAX_CONTEXT_CHARS, AIService


def test_service_routes_task_and_returns_client_response():
    client = Mock()
    expected = AIResponse("réponse", AIModel.FLASH, 10, 3)
    client.generate.return_value = expected
    service = AIService(client)

    result = service.generate(AITask.DP, "Construis un DP", response_format="json")

    assert result is expected
    client.generate.assert_called_once_with(
        "Construis un DP", AIModel.FLASH, "json",
        task_name="dp", context=None,
    )


def test_service_adds_bounded_context_with_explicit_markers():
    client = Mock()
    client.generate.return_value = AIResponse("OK", AIModel.FLASH_LITE)
    service = AIService(client)
    context = "x" * (MAX_CONTEXT_CHARS + 20)

    service.generate(AITask.QCM, "Question", context=context)

    prompt = client.generate.call_args.args[0]
    assert prompt.startswith("Question\n\n--- CONTEXTE DOCUMENTAIRE ---\n")
    assert prompt.endswith("\n--- FIN CONTEXTE ---")
    assert len(prompt) < len(context) + 100


def test_service_forwards_local_image_content_without_a_path_or_url():
    """Catches multimodal verification silently dropping locally loaded image bytes."""
    client = Mock()
    client.generate.return_value = AIResponse("OK", AIModel.FLASH_LITE)
    service = AIService(client)
    image = AIImageContent(mime_type="image/png", data=b"local-image")

    service.generate(AITask.QCM, "Question", images=(image,))

    client.generate.assert_called_once_with(
        "Question",
        AIModel.FLASH_LITE,
        "text",
        images=(image,),
        task_name="qcm",
        context=None,
    )


def test_service_does_not_route_score_tasks():
    service = AIService(Mock())

    with pytest.raises(ValueError, match="ne passe pas par le service IA"):
        service.generate(AITask.SCORE, "Calcule 2 + 2")
