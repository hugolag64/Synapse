from types import SimpleNamespace

import pytest

from backend.core.practice import mastery
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "practice-mastery.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _session(*, item_numbers=("115", "221")):
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.DP,
            total_questions=2,
            open_questions=0,
            closed_questions=2,
            item_numbers=item_numbers,
            course_id="course-115",
            course_title="Cas transversal",
        ),
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"},
            {"prompt": "Q2", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "B", "explanation": "E2"},
        ],
        model="test-model",
    )
    questions = local_store.get_ai_practice_session(session_id)
    return session_id, questions


def _link(question_id: int, item_number: str, confidence: float = 1.0) -> None:
    with local_store._conn() as con:
        con.execute(
            """INSERT INTO ai_practice_question_items
               (question_id, item_number, confidence, source, classifier_version)
               VALUES (?, ?, ?, ?, ?)""",
            (question_id, item_number, confidence, "manual", "test-v1"),
        )


def _get_evidence(session_id: int) -> dict:
    helper = getattr(mastery, "get_session_item_evidence", None)
    assert helper is not None
    return helper(session_id)


def test_mastery_aggregates_latest_attempts_per_linked_item(practice_db):
    session_id, questions = _session()
    _link(questions[0]["id"], "115")
    _link(questions[1]["id"], "221")
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[0]["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[1]["id"], response="A",
        is_correct=False, score_percent=0, finalize_session=False,
    )

    evidence = _get_evidence(session_id)

    assert evidence["115"]["score_percent"] == 100.0
    assert evidence["115"]["total_questions"] == 1
    assert evidence["221"]["score_percent"] == 0.0
    assert evidence["221"]["total_questions"] == 1


def test_session_item_list_alone_does_not_create_question_evidence(practice_db):
    session_id, questions = _session()
    for question, response in zip(questions, ("A", "B"), strict=True):
        local_store.record_ai_practice_attempt(
            session_id=session_id, question_id=question["id"], response=response,
            is_correct=True, score_percent=100, finalize_session=False,
        )

    assert _get_evidence(session_id) == {}


def test_record_ai_practice_mastery_persists_one_evaluation_per_item(practice_db, monkeypatch):
    session_id, questions = _session()
    _link(questions[0]["id"], "115")
    _link(questions[1]["id"], "221")
    for question, response, score in zip(questions, ("A", "A"), (100, 0), strict=True):
        local_store.record_ai_practice_attempt(
            session_id=session_id, question_id=question["id"], response=response,
            is_correct=score == 100, score_percent=score, finalize_session=False,
        )

    calls = []

    def fake_record_evaluation(evaluation):
        calls.append(evaluation)
        return SimpleNamespace(persisted_id=len(calls))

    monkeypatch.setattr(mastery, "record_evaluation", fake_record_evaluation)

    assert mastery.record_ai_practice_mastery(session_id) is not None
    assert [(call.item_number, call.score_percent) for call in calls] == [
        ("115", 100.0),
        ("221", 0.0),
    ]
    assert mastery.record_ai_practice_mastery(session_id) is None
    assert len(calls) == 2


def test_low_confidence_item_link_has_less_weight_in_item_score(practice_db):
    session_id, questions = _session(item_numbers=("115",))
    _link(questions[0]["id"], "115", confidence=1.0)
    _link(questions[1]["id"], "115", confidence=0.25)
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[0]["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[1]["id"], response="A",
        is_correct=False, score_percent=0, finalize_session=False,
    )

    evidence = _get_evidence(session_id)

    assert evidence["115"]["score_percent"] == 80.0


def test_qcm_mastery_does_not_require_course_id(practice_db, monkeypatch):
    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.QCM,
            total_questions=1,
            open_questions=0,
            closed_questions=1,
            item_numbers=("115",),
            course_id="",
            course_title="Annale UNESS",
        ),
        questions=[
            {"prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"], "answer": "A", "explanation": "E1"}
        ],
        model="test-model",
    )
    question = local_store.get_ai_practice_session(session_id)[0]
    _link(question["id"], "115")
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=question["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    calls = []
    monkeypatch.setattr(mastery, "record_evaluation", lambda evaluation: calls.append(evaluation) or SimpleNamespace(persisted_id=1))

    assert mastery.record_ai_practice_mastery(session_id) is not None
    assert calls[0].item_number == "115"


def test_multi_item_question_has_proportional_evidence_weight(practice_db):
    session_id, questions = _session(item_numbers=("115", "221"))
    _link(questions[0]["id"], "115")
    _link(questions[0]["id"], "221")
    _link(questions[1]["id"], "115")
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[0]["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=questions[1]["id"], response="A",
        is_correct=False, score_percent=0, finalize_session=False,
    )

    evidence = _get_evidence(session_id)

    assert evidence["115"]["score_percent"] == 33.33
    assert evidence["221"]["score_percent"] == 100.0
