import json

import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store
from frontend.components import qcm_replay
from frontend.components.qcm_replay import (
    build_correction_rows,
    build_question_result,
    build_session_result,
    filter_question_results,
    format_correction_summary,
    latest_response_by_question,
    save_response_once,
)


@pytest.fixture()
def replay_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "qcm-replay.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def stored_spec() -> PracticeSessionSpec:
    return PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number="115",
        course_id="course-115",
        course_title="Cardiologie",
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
    assert build_question_result(question(), {"response": "", "is_correct": 0})["status"] == "unanswered"


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


def test_closed_choice_with_comma_round_trips_structurally(replay_db):
    choices = ["Douleur thoracique", "Douleur, nocturne", "Dyspnée"]
    stored = qcm_replay.serialize_closed_response(["Douleur, nocturne"])
    session_id = local_store.create_ai_practice_session(
        spec=stored_spec(),
        questions=[
            {
                "prompt": "Q1",
                "kind": QuestionKind.CLOSED,
                "choices": choices,
                "answer": "B",
                "explanation": "Because B.",
            }
        ],
        model="test-model",
    )
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response=stored,
        is_correct=True,
        score_percent=100,
        finalize_session=False,
    )
    restored_question = local_store.get_ai_practice_session(session_id)[0]

    assert json.loads(stored) == ["Douleur, nocturne"]
    assert restored_question["attempts"][0]["response"] == stored
    assert latest_response_by_question([restored_question]) == {question_id: stored}
    assert qcm_replay.deserialize_closed_response(stored, choices) == ["Douleur, nocturne"]
    assert qcm_replay._same_closed_answer(stored, "B", choices)
    assert qcm_replay.deserialize_closed_response("Douleur, nocturne", choices) == [
        "Douleur, nocturne"
    ]


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


def test_correction_rows_render_a_finished_two_out_of_three_session():
    questions = [
        question(id=10, prompt="Q1"),
        question(id=11, prompt="Q2", answer="B"),
        question(id=12, prompt="Q3"),
    ]
    summary = {
        "score_percent": 66.67,
        "correct_count": 2,
        "incorrect_count": 1,
        "unanswered_count": 0,
        "latest_attempts": [
            {"question_id": 10, "response": "A", "is_correct": 1},
            {"question_id": 11, "response": "B", "is_correct": 1},
            {"question_id": 12, "response": "B", "is_correct": 0},
        ],
    }

    rows = build_correction_rows(questions, summary)

    assert format_correction_summary(summary) == ("Note : 13,3/20 (66.67 %)", "2/3 bonnes réponses · 0 sans réponse")
    assert [row["status"] for row in rows] == ["correct", "correct", "incorrect"]
    assert [row["response"] for row in rows] == ["A", "B", "B"]


def test_correction_rows_include_persisted_proposition_text(replay_db):
    session_id = local_store.create_ai_practice_session(
        spec=stored_spec(),
        questions=[{
            "prompt": "Q1", "kind": QuestionKind.CLOSED, "choices": ["A", "B"],
            "answer": "A", "explanation": "E1",
        }],
        model="test-model",
    )
    stored_question = local_store.get_ai_practice_session(session_id)[0]
    attempt_id = local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=stored_question["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    local_store.replace_ai_practice_attempt_propositions(attempt_id, [{
        "proposition_id": "A", "selected": True, "expected": True,
        "rank": "A", "points": 1, "discordance": "correct",
    }])

    summary = local_store.get_ai_practice_session_summary(session_id)
    rows = build_correction_rows(local_store.get_ai_practice_session(session_id), summary)

    assert rows[0]["propositions"][0]["text"] == "A"


def test_qcm_correction_discloses_official_uness_correction(monkeypatch):
    """Catches the NiceGUI correction view dropping the stored official UNESS answer."""
    labels = []
    images = []
    expansion_titles = []

    class Element:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_value, _traceback):
            return False

        def classes(self, _value):
            return self

        def props(self, _value):
            return self

        def clear(self):
            return None

        def on_value_change(self, _callback):
            return None

        def open(self):
            return None

        def close(self):
            return None

    class FakeUI:
        def dialog(self):
            return Element()

        def card(self):
            return Element()

        def label(self, text=""):
            labels.append(str(text))
            return Element()

        def image(self, source):
            images.append(str(source))
            return Element()

        def checkbox(self, *_args, **_kwargs):
            return Element()

        def column(self):
            return Element()

        def expansion(self, *_args, **_kwargs):
            if _args:
                expansion_titles.append(str(_args[0]))
            return Element()

        def row(self):
            return Element()

        def button(self, *_args, **_kwargs):
            return Element()

    question = {
        "id": 7,
        "prompt": "Question UNESS",
        "question_kind": "closed",
        "answer": '["Réponse IA"]',
        "choices": ["Réponse IA", "Réponse officielle"],
        "explanation": "Explication IA.",
        "correction": {
            "official": {"source": "UNESS", "answer": ["Réponse officielle"], "available": True}
        },
        "uness": {
            "exam": {
                "faculty": "Université Paris Cité",
                "level": "DFASM3",
                "year": 2026,
            },
            "provenance": {
                "source_url": "https://entrainement.uness.example/review/42",
                "collected_at": "2026-07-30T09:15:00+02:00",
                "collection_status": "complete",
            },
            "question": {
                "images": [
                    {
                        "source_url": "images/scan.png",
                        "local_path": "imports/media/scan.png",
                        "alt_text": "Scanner cérébral",
                        "caption": "Coupe axiale",
                    }
                ],
                "support_visuel_seul": True,
                "verification_status": "unsupported",
            },
            "propositions": [
                {
                    "id": "A",
                    "statut": "desaccord",
                    "commentaire_desaccord": "Le cours local contredit la correction officielle.",
                }
            ],
        },
    }
    monkeypatch.setattr(qcm_replay, "ui", FakeUI())
    monkeypatch.setattr(qcm_replay.local_store, "get_ai_practice_session_summary", lambda _id: {
        "score_percent": 100, "correct_count": 1, "incorrect_count": 0,
        "unanswered_count": 0, "score_mode": "edn",
        "latest_attempts": [{"id": 1, "question_id": 7, "response": question["answer"], "is_correct": 1}],
    })
    monkeypatch.setattr(qcm_replay.local_store, "get_ai_practice_session", lambda _id: [question])
    monkeypatch.setattr(qcm_replay.local_store, "get_ai_practice_attempt_propositions", lambda _id: [{
        "proposition_id": "A", "text": "Réponse IA", "selected": 1, "expected": 1,
        "rank": "A", "points": 1, "discordance": "correct",
    }])

    qcm_replay.open_qcm_correction(4, on_back=lambda: None, on_replay=lambda _id: None)

    assert any("Correction officielle UNESS" in label for label in labels)
    assert "Barème EDN propositionnel" in labels
    assert any("Réponse IA" in label for label in labels)
    assert any("Sélectionnée" in label and "Attendue" in label and "Rang A" in label for label in labels)
    assert "Divergence avec la correction officielle UNESS" in labels
    assert "Le cours local contredit la correction officielle." in labels
    assert "Source : https://entrainement.uness.example/review/42" in labels
    assert "Université Paris Cité · DFASM3 · 2026" in labels
    assert "Collecté le 2026-07-30T09:15:00+02:00 · Statut : complete" in labels
    assert (
        "Support visuel uniquement : l’interaction UNESS originale n’est pas reconstruite."
        in labels
    )
    assert (
        "⚠️ Vérification IA non disponible pour cette question — seule la "
        "correction officielle UNESS est garantie exacte."
        in labels
    )
    assert images == ["imports/media/scan.png"]
    assert any("Divergence UNESS" in title for title in expansion_titles)


def test_correction_summary_counts_answered_open_questions_without_marking_them_correct():
    summary = {
        "total_questions": 3,
        "answered_count": 3,
        "scored_count": 2,
        "correct_count": 2,
        "incorrect_count": 0,
        "unanswered_count": 0,
        "score_percent": 100,
    }

    assert format_correction_summary(summary) == (
        "Note : 20/20 (100 %)",
        "2/3 bonnes réponses · 0 sans réponse · 1 réponse non évaluée",
    )


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


def test_retry_after_failed_completion_does_not_duplicate_saved_response():
    persisted = {}
    saved = []

    assert save_response_once(persisted, 10, "A", lambda: saved.append("A")) is True
    assert save_response_once(persisted, 10, "A", lambda: saved.append("A")) is False

    assert saved == ["A"]


def test_advancing_without_an_answer_keeps_question_unanswered():
    persisted = {}
    saved = []

    assert save_response_once(persisted, 10, "", lambda: saved.append("")) is False

    assert persisted == {}
    assert saved == []


def test_legacy_blank_attempt_is_not_counted_as_answered(replay_db):
    session_id = local_store.create_ai_practice_session(
        spec=stored_spec(),
        questions=[
            {
                "prompt": "Q1",
                "kind": QuestionKind.CLOSED,
                "choices": ["A", "B"],
                "answer": "A",
                "explanation": "Because A.",
            }
        ],
        model="test-model",
    )
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response="",
        is_correct=False,
        score_percent=0,
        finalize_session=False,
    )

    summary = local_store.get_ai_practice_session_summary(session_id)
    completed = local_store.finalize_ai_practice_session(session_id)

    assert summary["answered_count"] == 0
    assert summary["unanswered_count"] == 1
    assert summary["latest_attempts"] == []
    assert completed["completed_at"] is None
    assert local_store.get_ai_practice_session(session_id)[0]["attempts"] == []


def test_chained_dialog_refreshes_then_opens_under_stable_slot():
    events = []

    class StableSlot:
        active = False

        def __enter__(self):
            self.active = True
            events.append("enter-stable")

        def __exit__(self, _exc_type, _exc_value, _traceback):
            self.active = False
            events.append("exit-stable")

    stable_slot = StableSlot()
    refreshable_slot = {"deleted": False}

    def refresh() -> None:
        refreshable_slot["deleted"] = True
        events.append("refresh")

    def open_next() -> None:
        assert refreshable_slot["deleted"] is True
        assert stable_slot.active is True
        events.append("open-next")

    qcm_replay.open_chained_dialog(stable_slot, open_next, refresh=refresh)

    assert events == ["refresh", "enter-stable", "open-next", "exit-stable"]
