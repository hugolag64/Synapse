from backend.core.practice import attempt_service


def test_score_and_record_closed_attempt_persists_official_score(monkeypatch):
    recorded = {}
    persisted_propositions = {}

    monkeypatch.setattr(
        attempt_service.local_store,
        "record_ai_practice_attempt",
        lambda **kwargs: recorded.update(kwargs) or 17,
    )
    monkeypatch.setattr(
        attempt_service.local_store,
        "replace_ai_practice_attempt_propositions",
        lambda attempt_id, propositions: persisted_propositions.update(
            {"attempt_id": attempt_id, "propositions": propositions}
        ),
    )

    attempt_id, scored = attempt_service.score_and_record_closed_attempt(
        session_id=3,
        question_id=7,
        question={
            "question_kind": "closed",
            "choices": [
                {"id": "A", "reponse_uness": True},
                {"id": "B", "reponse_uness": False},
            ],
            "answer": "A",
        },
        response="A, B",
        finalize_session=False,
    )

    assert attempt_id == 17
    assert scored.score_percent == 50.0
    assert recorded["score_percent"] == 50.0
    assert recorded["score_mode"] == "edn"
    assert persisted_propositions["attempt_id"] == 17
    assert persisted_propositions["propositions"]


def test_score_and_record_closed_attempt_persists_error_signals(monkeypatch):
    signals = []
    monkeypatch.setattr(
        attempt_service.local_store,
        "record_ai_practice_attempt",
        lambda **kwargs: 17,
    )
    monkeypatch.setattr(
        attempt_service.local_store,
        "replace_ai_practice_attempt_propositions",
        lambda attempt_id, propositions: None,
    )
    monkeypatch.setattr(
        attempt_service.local_store,
        "get_ai_practice_question_items",
        lambda question_id: [{"item_number": "93"}],
    )
    monkeypatch.setattr(
        attempt_service.local_store,
        "insert_error_signal_once",
        lambda **kwargs: signals.append(kwargs),
    )

    attempt_service.score_and_record_closed_attempt(
        session_id=3,
        question_id=7,
        question={
            "question_kind": "closed",
            "choices": [
                {"id": "A", "reponse_uness": True, "rank": "A"},
                {"id": "B", "reponse_uness": False, "rank": "B"},
            ],
            "answer": "A",
        },
        response="B",
        finalize_session=False,
    )

    assert {signal["category"] for signal in signals} == {"rang_a", "non_classe"}
