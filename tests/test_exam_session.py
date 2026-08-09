from __future__ import annotations


def test_exam_session_advances_without_showing_correction(monkeypatch):
    from backend.core.uness import exam_session

    monkeypatch.setattr(exam_session, "_parts_for_annale", lambda annale_id: [11, 12])
    session = exam_session.start_exam_session(annale_id=1)

    next_state = exam_session.advance_exam_session(session.session_id, response={"A"})

    assert next_state.current_index == 1
    assert next_state.mode == "exam"
    assert next_state.correction_visible is False
    assert next_state.completed_at is None


def test_exam_session_completion_unlocks_correction(monkeypatch):
    from backend.core.uness import exam_session

    monkeypatch.setattr(exam_session, "_parts_for_annale", lambda annale_id: [11])
    session = exam_session.start_exam_session(annale_id=1)
    exam_session.advance_exam_session(session.session_id, response={"A"})

    result = exam_session.complete_exam_session(session.session_id)

    assert result.status == "completed"
    assert result.correction_visible is True
