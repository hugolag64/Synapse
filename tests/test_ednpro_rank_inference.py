from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class FakeQuestion:
    external_question_id: str
    item_number: str
    prompt: str = "Question"
    rank: str = ""


def fake_question(
    question_id: str,
    item_number: str,
    *,
    rank: str = "",
    prompt: str = "Question",
) -> FakeQuestion:
    return FakeQuestion(question_id, item_number, prompt=prompt, rank=rank)


def test_groups_only_questions_without_official_rank_by_item():
    from backend.core.ednpro.rank_inference import group_missing_rank_questions

    questions = (
        fake_question("q1", "233"),
        fake_question("q2", "233", rank="B"),
        fake_question("q3", "75"),
        fake_question("q4", ""),
    )

    assert group_missing_rank_questions(questions) == {
        "233": (questions[0],),
        "75": (questions[2],),
    }


def test_prompt_contains_oics_once_and_all_missing_questions():
    from backend.core.ednpro.rank_inference import build_rank_inference_prompt

    prompt = build_rank_inference_prompt(
        "233",
        (fake_question("q1", "233", prompt="Question 1"), fake_question("q2", "233", prompt="Question 2")),
        (
            {"code": "OIC-1", "intitule": "OIC A", "rang": "A"},
            {"code": "OIC-2", "intitule": "OIC B", "rang": "B"},
        ),
    )

    assert prompt.count("OIC-1") == 1
    assert prompt.count("OIC-2") == 1
    assert "Question 1" in prompt
    assert "Question 2" in prompt
    assert '"rank":"A|B|null"' in prompt


def test_parser_rejects_threshold_boundary_and_unknown_rank():
    from backend.core.ednpro.rank_inference import parse_rank_inference_response

    result = parse_rank_inference_response(
        '{"questions":['
        '{"id":"q1","rank":"A","confidence":0.850}'
        ',{"id":"q2","rank":"B","confidence":0.91,"oic_codes":["OIC-2"],"rationale":"detail"}'
        ',{"id":"q3","rank":"C","confidence":0.99}'
        ']}'
        ,
        ("q1", "q2", "q3"),
    )

    assert "q1" not in result
    assert result["q2"].rank == "B"
    assert result["q2"].confidence == pytest.approx(0.91)
    assert result["q2"].oic_codes == ("OIC-2",)
    assert "q3" not in result


def test_parser_ignores_unknown_question_ids_and_malformed_payload():
    from backend.core.ednpro.rank_inference import parse_rank_inference_response

    assert parse_rank_inference_response(
        '{"questions":[{"id":"unknown","rank":"A","confidence":0.99}]}',
        ("q1",),
    ) == {}
    assert parse_rank_inference_response("not-json", ("q1",)) == {}
