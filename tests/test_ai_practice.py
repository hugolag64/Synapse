import json
from types import SimpleNamespace

import pytest

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.practice.models import (
    GeneratedQuestion,
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.practice.service import PracticeGenerationError, PracticeService
from backend.core.reviews import local_store
from frontend.components.ai_practice_panel import _same_closed_answer


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


def test_practice_spec_defaults_to_edn_difficulty():
    session = spec()
    assert session.difficulty is PracticeDifficulty.EDN


def test_practice_spec_rejects_unknown_difficulty():
    with pytest.raises(ValueError, match="difficulté"):
        spec(difficulty="unknown")


def test_generation_dialog_uses_compact_centered_linear_controls():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "width: 620px" in source
    assert "border-radius: 8px" in source
    assert "max-width: calc(100vw - 32px)" in source
    assert "ai-practice-kind-toggle" in source
    assert "label-always" not in source
    assert "total_value_chip" in source


def test_generation_dialog_normalizes_qcm_toggle_value_to_enum():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "PracticeKind(str(kind.value).upper())" in source


def test_generation_dialog_exposes_edn_difficulty_by_default():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert '"Standard": PracticeDifficulty.STANDARD.value' in source
    assert '"EDN": PracticeDifficulty.EDN.value' in source
    assert '"Difficile": PracticeDifficulty.DIFFICULT.value' in source
    assert '"Concours": PracticeDifficulty.CONCOURS.value' in source
    assert "value=PracticeDifficulty.EDN.value" in source
    assert "difficulty=PracticeDifficulty(str(difficulty.value))" in source


def test_generation_dialog_can_open_or_only_conserve_the_session():
    import inspect

    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "open_after_generation" in source
    assert "Ouvrir directement la session pour répondre" in source
    assert "if open_after_generation.value" in source


def test_closed_qcm_accepts_multiple_correct_choices_in_any_order():
    choices = ["HTA", "Tabac", "Âge"]
    assert _same_closed_answer("Tabac, HTA", "A, B", choices)
    assert not _same_closed_answer("HTA", "A, B", choices)


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


def test_practice_parser_accepts_fenced_json_from_provider():
    from backend.core.practice.service import _parse_questions

    payload = '''Voici la session :
```json
{"questions":[{"kind":"open","prompt":"P1","answer":"A1","explanation":"E1"},{"kind":"closed","prompt":"P2","choices":["A","B"],"answer":"A","explanation":"E2"},{"kind":"closed","prompt":"P3","choices":["A","B"],"answer":"B","explanation":"E3"}]}
```
'''

    parsed = _parse_questions(payload, spec())

    assert len(parsed) == 3
    assert parsed[0].prompt == "P1"


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
    first = local_store.create_ai_practice_session(
        spec=spec(difficulty=PracticeDifficulty.CONCOURS),
        questions=questions,
        model="gemini-3.1-flash-lite",
    )
    assert local_store.get_ai_practice_sessions(limit=1)[0]["difficulty"] == "concours"
    first_rows = local_store.get_ai_practice_session(first)
    assert [row["prompt"] for row in first_rows] == [q["prompt"] for q in questions]

    local_store.record_ai_practice_attempt(
        session_id=first, question_id=first_rows[0]["id"], response="Réponse",
        is_correct=True, score_percent=100,
    )
    replay = local_store.replay_ai_practice_session(first)
    assert local_store.get_ai_practice_sessions(limit=1)[0]["difficulty"] == "concours"
    replay_rows = local_store.get_ai_practice_session(replay)
    assert [row["id"] for row in replay_rows] == [row["id"] for row in first_rows]
    assert replay_rows[0]["attempts"] == []

    history = local_store.get_ai_practice_history(item_number="115")
    assert len(history) == 2
    assert history[0]["session"]["difficulty"] == "concours"
    assert history[1]["questions"][0]["attempts"][0]["response"] == "Réponse"


def test_empty_ai_practice_session_cannot_be_replayed(practice_db):
    session_id = local_store.create_ai_practice_session(
        spec=spec(), questions=[], model="test-model",
    )

    with pytest.raises(ValueError, match="questions"):
        local_store.replay_ai_practice_session(session_id)

    assert [row["id"] for row in local_store.get_ai_practice_sessions(limit=10)] == [session_id]


def test_ai_practice_session_summary_uses_latest_attempt_per_question(practice_db):
    questions = [
        {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        {"prompt": "Q3", "kind": QuestionKind.OPEN, "choices": [], "answer": "C", "explanation": "E3"},
    ]
    session_id = local_store.create_ai_practice_session(
        spec=spec(), questions=questions, model="test-model",
    )
    rows = local_store.get_ai_practice_session(session_id)
    first_attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=False, score_percent=0,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=True, score_percent=100,
    )
    second_attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[1]["id"], response="A", is_correct=False, score_percent=0,
    )

    summary = local_store.get_ai_practice_session_summary(session_id)

    assert summary["answered_count"] == 2
    assert summary["scored_count"] == 2
    assert summary["correct_count"] == 1
    assert summary["incorrect_count"] == 1
    assert summary["unanswered_count"] == 1
    assert len(summary["latest_attempts"]) == 2
    assert {attempt["id"] for attempt in summary["latest_attempts"]} == {
        first_attempt_id + 1, second_attempt_id,
    }
    assert first_attempt_id not in {attempt["id"] for attempt in summary["latest_attempts"]}


def test_ai_practice_sessions_history_filter_matches_title_and_status(practice_db):
    pending = local_store.create_ai_practice_session(
        spec=spec(course_title="Cardio avancée", item_number="115"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )
    completed = local_store.create_ai_practice_session(
        spec=spec(course_title="Neurologie", item_number="215"),
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E"}],
        model="test-model",
    )
    completed_question_id = local_store.get_ai_practice_session(completed)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=completed, question_id=completed_question_id, response="A", is_correct=True, score_percent=100,
    )
    local_store.finalize_ai_practice_session(completed)

    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(query="CARDIO")] == [pending]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(query="215")] == [completed]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status="pending")] == [pending]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status="completed")] == [completed]


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


def test_practice_service_prompt_mentions_concours_difficulty():
    class FakeAI:
        def __init__(self):
            self.prompt = ""

        def generate(self, task, prompt, *, response_format):
            self.prompt = prompt
            payload = {"questions": [
                {"kind": "closed", "prompt": "P", "choices": ["A", "B"], "answer": "A", "explanation": "E"},
            ]}
            return AIResponse(json.dumps(payload), AIModel.FLASH, 10, 10)

    fake = FakeAI()
    service = PracticeService(ai_service=fake, store=SimpleNamespace(
        create_ai_practice_session=lambda **kwargs: 1,
    ))
    service.create_new_session(spec(
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        difficulty=PracticeDifficulty.CONCOURS,
    ))
    assert "niveau Concours" in fake.prompt
    assert "distracteurs très proches" in fake.prompt


def test_scored_ai_session_updates_mastery_evaluation_once(practice_db):
    questions = [
        {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
        {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
    ]
    session_id = local_store.create_ai_practice_session(
        spec=spec(total_questions=2, open_questions=0, closed_questions=2),
        questions=questions,
        model="gemini-3-flash-preview",
    )
    rows = local_store.get_ai_practice_session(session_id)
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A", is_correct=True, score_percent=100,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[1]["id"], response="A", is_correct=False, score_percent=0,
    )

    outcome = record_ai_practice_mastery(session_id)
    assert outcome is not None
    stored = local_store.get_qcm_sessions_all(course_id="course-115")
    assert stored[0]["session_type"] == "QCM"
    assert stored[0]["score_percent"] == 50
    assert record_ai_practice_mastery(session_id) is None
