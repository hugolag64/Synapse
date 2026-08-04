import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "question-items.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_new_questions_are_linked_only_to_their_primary_item(practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.DP,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="221",
        item_numbers=("221", "245"),
        course_id="course-221",
        course_title="Cardiologie",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"}],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    assert local_store.get_ai_practice_question_items(question["id"]) == [{
        "item_number": "221", "oic_code": "", "confidence": 1.0,
        "source": "rule", "classifier_version": "session-primary-v1",
    }]


def test_question_specific_items_override_session_primary_item(practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="221",
        item_numbers=("221",),
        course_id="ednpro-2023-p1",
        course_title="EDN 2023 — P1",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"],
            "answer": "A", "explanation": "E1", "item_numbers": ("245",),
            "item_classification_source": "source", "item_classification_confidence": 1.0,
            "item_classifier_version": "ednpro-source-v1",
        }],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    assert [row["item_number"] for row in local_store.get_ai_practice_question_items(question["id"])] == ["245"]


def test_unresolved_question_does_not_inherit_ednpro_session_item(practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="221",
        item_numbers=("221",),
        course_id="ednpro-2023-p1",
        course_title="EDN 2023 — P1",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"],
            "answer": "A", "explanation": "E1", "allow_session_item_fallback": False,
        }],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    assert local_store.get_ai_practice_question_items(question["id"]) == []
