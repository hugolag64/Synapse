from frontend.components.qcm_replay import (
    build_question_result,
    build_session_result,
    filter_question_results,
    latest_response_by_question,
)


def question(**overrides):
    value = {
        "question_kind": "closed",
        "answer": "A",
        "choices": ["A", "B"],
        "explanation": "Because A.",
    }
    value.update(overrides)
    return value


def test_build_question_result_marks_correct_and_preserves_correction():
    result = build_question_result(question(), {"response": "A", "is_correct": 1})

    assert result == {
        "status": "correct",
        "response": "A",
        "correct_answer": "A",
        "explanation": "Because A.",
        "choices": ["A", "B"],
        "is_open": False,
    }


def test_build_question_result_marks_incorrect_and_unanswered():
    assert build_question_result(question(), {"response": "B", "is_correct": 0})["status"] == "incorrect"
    assert build_question_result(question(), None)["status"] == "unanswered"


def test_open_question_has_no_automatic_status_and_missing_explanation_fallback():
    result = build_question_result(
        question(question_kind="open", answer="Expected", choices=[], explanation=""),
        {"response": "My answer", "is_correct": None},
    )

    assert result["status"] is None
    assert result["is_open"] is True
    assert result["correct_answer"] == "Expected"
    assert result["explanation"] == "Explication non disponible"


def test_closed_multiple_choice_answers_are_order_independent_when_unscored():
    result = build_question_result(
        question(answer="A, B", choices=["A", "B", "C"]),
        {"response": "B, A", "is_correct": None},
    )

    assert result["status"] == "correct"


def test_build_session_result_uses_latest_attempt_results_for_score():
    questions = [
        question(attempts=[{"id": 2, "response": "A", "is_correct": 1}, {"id": 1, "response": "B", "is_correct": 0}]),
        question(answer="B", attempts=[{"response": "A", "is_correct": 0}]),
        question(question_kind="open", choices=[], attempts=[]),
    ]

    assert build_session_result(questions) == {
        "total_count": 3,
        "answered_count": 2,
        "scored_count": 2,
        "correct_count": 1,
        "incorrect_count": 1,
        "unanswered_count": 1,
        "score_percent": 50.0,
    }


def test_filter_question_results_errors_only_keeps_non_correct_results():
    results = [{"status": "correct"}, {"status": "incorrect"}, {"status": "unanswered"}, {"status": None}]

    assert filter_question_results(results, errors_only=True) == results[1:]
    assert filter_question_results(results, errors_only=False) == results


def test_latest_response_by_question_restores_newest_and_leaves_unanswered_blank():
    questions = [
        question(id=10, attempts=[{"id": 1, "response": "Ancienne"}, {"id": 2, "response": "Nouvelle"}]),
        question(id=11, attempts=[]),
        question(id=12, attempts=[{"response": "Sans identifiant"}]),
    ]

    assert latest_response_by_question(questions) == {10: "Nouvelle", 11: "", 12: "Sans identifiant"}
