from backend.api import qcm


def test_session_payload_exposes_questions_and_restored_answers(monkeypatch):
    question = {
        "id": 7,
        "question_kind": "closed",
        "attempts": [{"id": 1, "response": '["B"]'}],
    }
    monkeypatch.setattr(
        qcm.local_store,
        "get_ai_practice_session_summary",
        lambda _session_id: {"id": 3, "latest_attempts": []},
    )
    monkeypatch.setattr(qcm.local_store, "get_ai_practice_session", lambda _session_id: [question])

    payload = qcm.get_session(3)

    assert payload["session"] == {"id": 3}
    assert payload["answers"] == {"7": '["B"]'}
    assert payload["questions"] == [question]


def test_attempt_endpoint_rejects_question_from_another_session(monkeypatch):
    monkeypatch.setattr(qcm.local_store, "get_ai_practice_session", lambda _session_id: [])

    try:
        qcm.save_attempt(3, qcm.AttemptPayload(question_id=7, response="B"))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected a 404 for a question outside the session")


def test_attempt_endpoint_scores_closed_question_on_the_server(monkeypatch):
    recorded = {}
    question = {
        "id": 7,
        "question_kind": "closed",
        "choices": ["A", "B"],
        "answer": "A",
    }
    monkeypatch.setattr(qcm.local_store, "get_ai_practice_session", lambda _session_id: [question])
    monkeypatch.setattr(
        qcm.local_store,
        "record_ai_practice_attempt",
        lambda **kwargs: recorded.update(kwargs),
    )

    qcm.save_attempt(3, qcm.AttemptPayload(question_id=7, response="A"))

    assert recorded["is_correct"] is True
    assert recorded["score_percent"] == 100.0
