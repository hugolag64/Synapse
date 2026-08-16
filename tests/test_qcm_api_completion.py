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
    payload = response.json()
    assert payload["session"]["score_mode"] == "edn"
    assert payload["rows"][0]["propositions"][0]["text"] == "A"
    assert payload["rows"][0]["propositions"][0]["selected"] == 1
    assert payload["rows"][0]["propositions"][0]["expected"] == 1
    assert payload["rows"][0]["propositions"][0]["discordance"] == "correct"


def test_attempt_api_persists_elapsed_duration(client, practice_db):
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

    response = client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={"question_id": question["id"], "response": "A", "duration_seconds": 37},
    )

    assert response.status_code == 200
    attempt = local_store.get_ai_practice_session(session_id)[0]["attempts"][-1]
    assert attempt["duration_seconds"] == 37


def test_timeout_completion_records_unanswered_questions_and_finalizes(client, practice_db):
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

    response = client.post(f"/api/qcm/sessions/{session_id}/complete", json={"timed_out": True})

    assert response.status_code == 200
    assert response.json()["session"]["completion_state"] == "scored"
    assert len(response.json()["rows"]) == 2


def test_completion_excludes_non_noted_question_from_session_score(client, practice_db):
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
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": [{"id": "A", "texte": "A", "reponse_uness": True}], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": [{"id": "A", "texte": "A", "reponse_uness": None}], "answer": "A", "explanation": "E2"},
        ],
        model="test-model",
    )
    questions = local_store.get_ai_practice_session(session_id)
    for question in questions:
        assert client.post(
            f"/api/qcm/sessions/{session_id}/attempts",
            json={"question_id": question["id"], "response": "A"},
        ).status_code == 200

    response = client.post(f"/api/qcm/sessions/{session_id}/complete")

    assert response.status_code == 200
    assert response.json()["session"]["score_percent"] == 100
    assert response.json()["session"]["score_mode"] == "edn"


def test_qroc_attempt_uses_official_exact_and_acceptable_answers(client, practice_db):
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=1,
        closed_questions=0,
        item_number="115",
        course_id="course-115",
        course_title="Insuffisance cardiaque",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Quel diagnostic ?",
            "kind": QuestionKind.OPEN,
            "choices": [],
            "answer": "Diagnostic exact",
            "explanation": "E1",
            "import_metadata": {
                "uness": {"question": {
                    "type_question": "QROC",
                    "qroc_exact_answers": ["Diagnostic exact"],
                    "qroc_acceptable_answers": ["Formulation acceptable"],
                }}
            },
        }],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    response = client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={"question_id": question["id"], "response": "Formulation acceptable"},
    )

    assert response.status_code == 200
    assert response.json()["score_mode"] == "edn"
    assert local_store.get_ai_practice_session(session_id)[0]["attempts"][-1]["score_percent"] == 50


def test_unsupported_visual_question_is_preserved_but_not_noted(client, practice_db):
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
        questions=[{
            "prompt": "Que montre l'image ?",
            "kind": QuestionKind.CLOSED,
            "choices": [{"id": "A", "texte": "Réponse", "reponse_uness": True}],
            "answer": "A",
            "explanation": "E1",
            "import_metadata": {
                "uness": {"question": {
                    "type_question": "QRU",
                    "verification_status": "unsupported",
                }}
            },
        }],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]

    response = client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={"question_id": question["id"], "response": "A"},
    )

    assert response.status_code == 200
    assert response.json()["score_mode"] == "not_noted"
    assert client.post(f"/api/qcm/sessions/{session_id}/complete").status_code == 200
    session = local_store.get_ai_practice_session_summary(session_id)
    assert session["score_mode"] == "not_noted"
    assert session["score_percent"] is None


def _answered_session(client) -> int:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="230",
        course_id="course-230",
        course_title="Douleur thoracique",
    )
    session_id = local_store.create_ai_practice_session(
        spec=spec,
        questions=[{
            "prompt": "Quelle cause évoquer ?",
            "kind": QuestionKind.CLOSED,
            "choices": ["SCA", "Entorse"],
            "answer": "SCA",
            "explanation": "Urgence vitale.",
        }],
        model="test-model",
    )
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={"question_id": question_id, "response": "SCA"},
    )
    client.post(f"/api/qcm/sessions/{session_id}/complete")
    return session_id


def test_correction_can_be_reopened_after_completion(client, practice_db):
    """La correction n'existait qu'en retour de POST /complete : la rouvrir
    depuis la fiche item exigeait de refinaliser la session."""
    session_id = _answered_session(client)

    response = client.get(f"/api/qcm/sessions/{session_id}/correction")

    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["session"]["id"] == session_id


def test_reopening_a_correction_has_no_side_effect(client, practice_db):
    """Une lecture ne doit ni refinaliser la session ni rejouer la maîtrise."""
    session_id = _answered_session(client)
    before = dict(local_store.get_ai_practice_session_summary(session_id))

    for _ in range(3):
        assert client.get(f"/api/qcm/sessions/{session_id}/correction").status_code == 200

    after = dict(local_store.get_ai_practice_session_summary(session_id))
    for field in ("completed_at", "score_percent", "mastery_recorded_at", "completion_state"):
        assert before[field] == after[field], f"{field} modifié par une simple lecture"


def test_reopening_an_unknown_correction_is_a_404(client, practice_db):
    assert client.get("/api/qcm/sessions/999999/correction").status_code == 404
