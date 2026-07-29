"""Regression coverage for the QCM cockpit replay workspace."""

import inspect

import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store
from frontend.components import qcm_replay


@pytest.fixture()
def cockpit_practice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "cockpit-practice.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _stored_qcm_spec(course_title: str, item_number: str) -> PracticeSessionSpec:
    return PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number=item_number,
        course_id=f"course-{item_number}",
        course_title=course_title,
    )


def _stored_question() -> dict:
    return {
        "prompt": "Q1",
        "kind": QuestionKind.CLOSED,
        "choices": ["A", "B"],
        "answer": "A",
        "explanation": "Because A.",
    }


def test_cockpit_wires_existing_replay_reader_and_correction_actions():
    """Fails if a selected stored session can no longer open either workspace."""
    from frontend.pages import qcm_cockpit

    source = inspect.getsource(qcm_cockpit)

    assert "open_qcm_session" in source
    assert "open_qcm_correction" in source


def test_replay_action_returns_the_new_selected_session(monkeypatch):
    """Fails if replay stops returning the immutable session selected by the cockpit."""
    monkeypatch.setattr(qcm_replay.local_store, "replay_ai_practice_session", lambda _session_id: 73)

    assert qcm_replay.replay_qcm_session(12) == 73


def test_history_toggle_values_filter_pending_completed_and_query(cockpit_practice_db):
    """Fails if the UI toggle sends display labels instead of history status keys."""
    from frontend.pages import qcm_cockpit

    pending = local_store.create_ai_practice_session(
        spec=_stored_qcm_spec("Cardiology pending", "115"),
        questions=[_stored_question()],
        model="test-model",
    )
    completed = local_store.create_ai_practice_session(
        spec=_stored_qcm_spec("Neurology completed", "215"),
        questions=[_stored_question()],
        model="test-model",
    )
    question_id = local_store.get_ai_practice_session(completed)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=completed,
        question_id=question_id,
        response="A",
        is_correct=True,
        score_percent=100,
    )
    local_store.finalize_ai_practice_session(completed)

    options = qcm_cockpit.HISTORY_STATUS_OPTIONS
    pending_status = next(value for value, label in options.items() if label == "À faire")
    completed_status = next(value for value, label in options.items() if label == "Terminées")
    all_status = next(value for value, label in options.items() if label == "Toutes")
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status=pending_status)] == [
        pending
    ]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(status=completed_status)] == [
        completed
    ]
    assert [row["id"] for row in local_store.get_ai_practice_sessions_history(
        query="cardiology", status=all_status
    )] == [pending]


def test_cockpit_exposes_bounded_searchable_replay_history():
    """Fails if stored-question sessions lose their searchable history entry point."""
    from frontend.pages import qcm_cockpit

    source = inspect.getsource(qcm_cockpit)

    assert "Rechercher une session" in source
    assert "get_ai_practice_sessions_history" in source
    assert "_render_history" in source


def test_cockpit_keeps_pending_start_and_new_qcm_entry_actions():
    """Fails if the replay workspace displaces existing QCM entry flows."""
    from frontend.pages import qcm_cockpit

    source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)

    assert "SESSIONS \u00c0 FAIRE" in source
    assert "Commencer" in source
    assert "Nouvelle session" in source
    assert "QCM_ENTRY_LABEL" in source
