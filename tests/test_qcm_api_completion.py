from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import qcm
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "practice-api.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(qcm.router)
    return TestClient(app)


def test_complete_rejects_incomplete_session(client, practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=2,
        open_questions=0,
        closed_questions=2,
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        ],
        model="test-model",
    )
    first = local_store.get_ai_practice_session(session_id)[0]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=first["id"],
        response="A",
        is_correct=True,
        score_percent=100,
        finalize_session=False,
    )

    response = client.post(f"/api/qcm/sessions/{session_id}/complete")

    assert response.status_code == 409
    assert response.json()["detail"]["missing_positions"] == [2]


def test_completed_closed_question_exposes_training_mode_and_propositions(client, practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"}],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    assert client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={"question_id": question["id"], "response": "A"},
    ).status_code == 200
    response = client.post(f"/api/qcm/sessions/{session_id}/complete")

    assert response.status_code == 200
    assert response.json()["session"]["score_mode"] == "training"
    assert response.json()["rows"][0]["propositions"][0]["discordance"] == "correct"
