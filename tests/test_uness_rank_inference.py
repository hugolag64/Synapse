import json
from unittest.mock import Mock

import pytest


def test_prompt_contains_item_oics_and_question_payload():
    from backend.core.uness.rank_inference import build_uness_rank_prompt

    prompt = build_uness_rank_prompt(
        "233",
        [
            {"id": "q1", "prompt": "Question 1", "choices": ["A", "B"]},
            {"id": "q2", "prompt": "Question 2", "choices": ["C", "D"]},
        ],
        [{"code": "OIC-233-01-A", "intitule": "OIC A", "rang": "A"}],
    )

    assert '"item_number":"233"' in prompt
    assert prompt.count("OIC-233-01-A") == 1
    assert "Question 1" in prompt
    assert "Question 2" in prompt
    assert '"rank":"A|B|null"' in prompt
    assert '"ambiguous":false' in prompt


def test_parser_keeps_only_confident_non_ambiguous_known_questions():
    from backend.core.uness.rank_inference import parse_uness_rank_response

    result = parse_uness_rank_response(
        json.dumps(
            {
                "questions": [
                    {"id": "q1", "rank": "A", "confidence": 0.85, "ambiguous": False},
                    {"id": "q2", "rank": "B", "confidence": 0.91, "ambiguous": True},
                    {"id": "q3", "rank": "B", "confidence": 0.84, "ambiguous": False},
                    {"id": "unknown", "rank": "A", "confidence": 0.99, "ambiguous": False},
                    {"id": "q4", "rank": "C", "confidence": 0.99, "ambiguous": False},
                ]
            }
        ),
        ["q1", "q2", "q3", "q4"],
    )

    assert result["q1"].rank == "A"
    assert result["q1"].confidence == pytest.approx(0.85)
    assert "q2" not in result
    assert "q3" not in result
    assert "unknown" not in result
    assert "q4" not in result


def test_parser_returns_empty_for_malformed_or_wrong_shape_payload():
    from backend.core.uness.rank_inference import parse_uness_rank_response

    assert parse_uness_rank_response("not-json", ["q1"]) == {}
    assert parse_uness_rank_response('{"items": []}', ["q1"]) == {}


def test_infer_uness_ranks_uses_json_lite_route():
    from backend.core.ai.routing import AIModel, AIResponse, AITask
    from backend.core.ai.tasks import infer_uness_ranks

    service = Mock()
    service.generate.return_value = AIResponse("{}", AIModel.FLASH_LITE)

    result = infer_uness_ranks("classe ce lot", service=service)

    assert result.text == "{}"
    service.generate.assert_called_once_with(
        AITask.UNESS_RANK,
        "classe ce lot",
        response_format="json",
    )
