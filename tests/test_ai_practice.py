import json
from types import SimpleNamespace

import pytest

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.models import (
    GeneratedQuestion,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.practice.service import PracticeGenerationError, PracticeService
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "practice.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def spec(**overrides):
    values = dict(
        practice_kind=PracticeKind.QCM,
        total_questions=3,
        open_questions=1,
        closed_questions=2,
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
    )
    values.update(overrides)
    return PracticeSessionSpec(**values)


def test_spec_requires_exact_open_closed_distribution():
    with pytest.raises(ValueError, match="somme"):
        spec(total_questions=4)


def test_generated_question_requires_correction_and_explanation():
    with pytest.raises(ValueError, match="correction"):
        GeneratedQuestion("Question", QuestionKind.OPEN, "", "explication")


def test_practice_parser_keeps_mixed_distribution():
    payload = {"questions": [
        {"kind": "open", "prompt": "P1", "answer": "A1", "explanation": "E1"},
        {"kind": "closed", "prompt": "P2", "choices": ["A", "B"], "answer": "A", "explanation": "E2"},
        {"kind": "closed", "prompt": "P3", "choices": ["A", "B"], "answer": "B", "explanation": "E3"},
    ]}
    from backend.core.practice.service import _parse_questions
    parsed = _parse_questions(payload, spec())
    assert [q.kind for q in parsed] == [QuestionKind.OPEN, QuestionKind.CLOSED, QuestionKind.CLOSED]


def test_parser_rejects_wrong_distribution():
    from backend.core.practice.service import _parse_questions
    payload = {"questions": [
        {"kind": "closed", "prompt": "P1", "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"kind": "closed", "prompt": "P2", "choices": ["A", "B"], "answer": "A", "explanation": "E2"},
        {"kind": "closed", "prompt": "P3", "choices": ["A", "B"], "answer": "B", "explanation": "E3"},
    ]}
    with pytest.raises(PracticeGenerationError, match="répartition"):
        _parse_questions(payload, spec())


def test_create_replay_and_attempt_history(practice_db):
    questions = [
        {"prompt": "Question ouverte", "kind": QuestionKind.OPEN, "choices": [], "answer": "Réponse", "explanation": "Pourquoi"},
        {"prompt": "Question fermée", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "Correction"},
        {"prompt": "Question fermée 2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "Correction 2"},
    ]
    first = local_store.create_ai_practice_session(spec=spec(), questions=questions, model="gemini-3.1-flash-lite")
    first_rows = local_store.get_ai_practice_session(first)
    assert [row["prompt"] for row in first_rows] == [q["prompt"] for q in questions]

    local_store.record_ai_practice_attempt(
        session_id=first, question_id=first_rows[0]["id"], response="Réponse",
        is_correct=True, score_percent=100,
    )
    replay = local_store.replay_ai_practice_session(first)
    replay_rows = local_store.get_ai_practice_session(replay)
    assert [row["id"] for row in replay_rows] == [row["id"] for row in first_rows]
    assert replay_rows[0]["attempts"] == []

    history = local_store.get_ai_practice_history(item_number="115")
    assert len(history) == 2
    assert history[1]["questions"][0]["attempts"][0]["response"] == "Réponse"


def test_practice_service_routes_dp_to_flash_and_persists():
    class FakeAI:
        def __init__(self):
            self.calls = []

        def generate(self, task, prompt, *, response_format):
            self.calls.append((task, response_format))
            payload = {"questions": [
                {"kind": "open", "prompt": "P", "answer": "A", "explanation": "E"},
            ]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    svc = PracticeService(ai_service=fake, store=SimpleNamespace(
        create_ai_practice_session=lambda **kwargs: kwargs["spec"].total_questions,
    ))
    result = svc.create_new_session(spec(
        practice_kind=PracticeKind.DP,
        total_questions=1,
        open_questions=1,
        closed_questions=0,
    ))
    assert result == 1
    assert fake.calls[0][0].value == "dp"
    assert fake.calls[0][1] == "json"
