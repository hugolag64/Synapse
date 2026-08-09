import pytest

from backend.api import qcm
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "error-signals.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _closed_session() -> tuple[int, dict]:
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.QCM,
            total_questions=1,
            open_questions=0,
            closed_questions=1,
            item_number="221",
            course_id="course-221",
            course_title="Cardiologie",
        ),
        questions=[{
            "prompt": "Q1",
            "kind": QuestionKind.CLOSED,
            "choices": [
                {"id": "A", "label": "A", "is_correct": True, "rank": "A"},
                {"id": "B", "label": "B", "is_correct": False, "rank": "B"},
            ],
            "answer": "A",
            "explanation": "E1",
        }],
        model="test-model",
    )
    return session_id, local_store.get_ai_practice_session(session_id)[0]


def test_incorrect_linked_attempt_writes_error_signals(practice_db):
    session_id, question = _closed_session()

    qcm.save_attempt(session_id, qcm.AttemptPayload(question_id=question["id"], response="B"))

    signals = local_store.get_error_signals(item_number="221")
    assert {row["category"] for row in signals} == {"rang_a", "non_classe"}
    assert {row["source"] for row in signals} == {"qcm"}
    assert all(row["evidence_id"].isdigit() for row in signals)


def test_reingesting_attempt_is_idempotent(practice_db):
    session_id, question = _closed_session()
    scored = qcm.score_closed_attempt(
        "B",
        question["choices"],
        question["answer"],
    )
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question["id"],
        response="B",
        is_correct=False,
        score_percent=scored.score_percent,
        finalize_session=False,
    )

    qcm._record_error_signals(attempt_id, question["id"], scored.propositions)
    qcm._record_error_signals(attempt_id, question["id"], scored.propositions)

    assert len(local_store.get_error_signals(item_number="221")) == 2
