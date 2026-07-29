"""Regression coverage for the QCM cockpit replay workspace."""

import inspect

from frontend.components import qcm_replay


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
